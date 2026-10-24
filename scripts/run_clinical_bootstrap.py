#!/usr/bin/env python3
"""Resumable, local-only 500-draw patient bootstrap for clinical DM.

Each committed draw is immutable. Interrupted uncommitted draws can be replayed
under their original key; failed draws are never replaced by new random draws.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import numpy as np
from threadpoolctl import threadpool_info, threadpool_limits
from april_repro.clinical_dataset import load_clinical_dataset
from april_repro.cluster_bootstrap import POPULATIONS, DEFAULT_SEED, build_cluster_population
from april_repro.clinical_bootstrap import run_dm_draw
from april_repro.clinical_bootstrap_statistics import summarize_bootstrap_draws
from april_repro.cohort_splits import SPLITS

RULE_VERSION = 'clinical-bootstrap-v1'
DEPENDENCIES = {'numpy':'2.2.6', 'scipy':'1.15.3', 'scikit-learn':'1.7.2',
                'joblib':'1.5.2', 'threadpoolctl':'3.6.0'}
CODE_PATHS = ('scripts/run_clinical_bootstrap.py',
              'src/april_repro/cluster_bootstrap.py',
              'src/april_repro/clinical_bootstrap.py',
              'src/april_repro/clinical_bootstrap_statistics.py',
              'src/april_repro/clinical_dataset.py', 'src/april_repro/clinical_models.py',
              'src/april_repro/rewards.py', 'src/april_repro/decision_features.py',
              'src/april_repro/cohort_splits.py', 'src/april_repro/cohort_patient_splits.py',
              'config/clinical-bootstrap.toml', 'config/clinical-baseline.toml',
              'requirements-g3.lock')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    temporary.chmod(0o600)
    temporary.replace(path)


@contextmanager
def exclusive_run(dest):
    with (dest / '.lock').open('a') as handle:
        (dest / '.lock').chmod(0o600)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Another process is running this bootstrap artifact') from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def validate_protocol(protocol):
    expected = {'rule_version': RULE_VERSION, 'bootstrap_datasets': 500,
                'seed': DEFAULT_SEED, 'sampling_unit': 'patient_cluster',
                'fixed_roles_and_folds': True, 'populations': list(POPULATIONS),
                'patient_draws': 'original population subject count with replacement',
                'event_weighting': 'equal_per_repeated_event',
                'refit': ['target_policy_and_its_preprocessor', 'behavior_OLS_and_its_preprocessor'],
                'behavior_clone_refitted': False, 'models': 'config/clinical-baseline.toml',
                'd0': 'resampled_target_validation_events',
                'reference': 'observed_reward_mean_on_same_resampled_target_validation_events_proxy',
                'rmse': 'sqrt(mean((dm_value-observed_reference_value)^2)) over 500 draws',
                'rmse_error_bar': 'finite_B_Monte_Carlo_SE_delta_method_not_patient_sampling_SE',
                'bootstrap_se_value': 'sample_SD(dm_value), ddof1',
                'bootstrap_sd_error': 'sample_SD(signed_error), ddof1',
                'rmse_mc_se_delta': 'sample_SD(squared_error)/(2*sqrt(B)*RMSE)',
                'empty_population': 'not_estimable; preserve original fold; do not draw',
                'missing_action_class': 'retain natural draw; existing constant/absent-action model rules',
                'failed_draw': 'retain draw ID and reason; no replacement draws; no primary RMSE until all500 valid',
                'nested_bootstrap': False, 'blas_threads': 1, 'prediction_batch_size': 5000,
                'patient_rows_local_only': True, 'external_llm_calls': False, 'database_queries': False}
    if any(protocol.get(key) != value for key, value in expected.items()):
        raise ValueError('Recorded bootstrap settings differ from the fixed implementation')


def validate_model_protocol(protocol):
    # Same actual fitter and scientific settings as the existing point baseline.
    from april_repro.clinical_models import POLICY_PARAMETERS
    expected = dict(POLICY_PARAMETERS, class_weight='none')
    if any(protocol.get('policy', {}).get(key) != value for key, value in expected.items()):
        raise ValueError('Recorded policy settings differ from the model implementation')
    if (protocol.get('reward', {}).get('clip_predictions') is not False
            or protocol.get('reward', {}).get('context_action_interactions') is not False
            or protocol.get('reward', {}).get('model') != 'sklearn.linear_model.LinearRegression'
            or protocol.get('reward', {}).get('fit_intercept') is not True
            or protocol.get('reward', {}).get('penalty') != 'none'
            or protocol.get('reward', {}).get('action_encoding') != 'discrete paper action divided by40 forK or500 forNa'
            or protocol.get('reward', {}).get('reward_formula') != 'main text sigma=2.5'):
        raise ValueError('Recorded OLS settings differ from the model implementation')


def commit_draw(dest, record, payload, draws):
    """Publish the complete private draw directory with one atomic rename."""
    final = dest / f'draw-{record["draw_id"]:03d}'
    if final.exists():
        raise ValueError('Refusing to replace an existing bootstrap draw')
    temporary = Path(tempfile.mkdtemp(prefix='.uncommitted-', dir=dest))
    arrays = {}
    for name, draw in draws.items():
        arrays[name + '_subject_ids'] = draw.subject_ids
        arrays[name + '_patient_counts'] = draw.patient_counts
    np.savez_compressed(temporary / 'patient-counts.npz', **arrays)
    (temporary / 'patient-counts.npz').chmod(0o600)
    save(temporary / 'models.json', payload)
    record = dict(record, outputs={name: sha(temporary / name)
                                 for name in ('patient-counts.npz', 'models.json')})
    save(temporary / 'result.json', record)
    temporary.rename(final)
    return record


def read_committed(dest, task, split):
    records = []
    for directory in sorted(dest.glob('draw-*')):
        if not directory.is_dir() or directory.name not in {f'draw-{i:03d}' for i in range(500)}:
            raise ValueError('Unexpected committed draw path')
        record = json.loads((directory / 'result.json').read_text())
        if (directory.name != f'draw-{record["draw_id"]:03d}'
                or record.get('task') != task or record.get('split') != split
                or record.get('status') not in ('complete', 'failed')):
            raise ValueError('Committed draw identity mismatch')
        if set(record.get('outputs', {})) != {'models.json', 'patient-counts.npz'}:
            raise ValueError('Missing draw output identity')
        for name, digest in record['outputs'].items():
            if sha(directory / name) != digest:
                raise ValueError('Committed draw output hash mismatch')
        records.append(record)
    # Also rejects nonfinite values, duplicate IDs and inconsistent differences.
    summarize_bootstrap_draws(records, planned_draws=500)
    return records


def summarize_results(populations, records):
    result = {}
    for split in SPLITS:
        empty = [name for name, pop in populations[split].items() if not pop.n_subjects]
        if empty:
            if records[split]:
                raise ValueError('Empty original population unexpectedly has committed draws')
            result[split] = {'status': 'not_estimable', 'reason': 'empty_original_population',
                             'empty_populations': empty, 'planned_draws': 500, 'attempted_draws': 0,
                             'completed_draws': 0, 'primary_metrics': None}
        else:
            result[split] = summarize_bootstrap_draws(records[split], planned_draws=500)
    return result


def run(input_directory=None, resume_directory=None, max_new_draws=None):
    if max_new_draws is not None and max_new_draws < 1:
        raise ValueError('max_new_draws must be positive; the planned repetition count remains500')
    if (input_directory is None) == (resume_directory is None):
        raise ValueError('Choose exactly one of input_directory and resume_directory')
    os.umask(0o077)
    dependencies = {name: importlib.metadata.version(name) for name in DEPENDENCIES}
    if dependencies != DEPENDENCIES:
        raise ValueError('Numerical backend does not match requirements-g3.lock')
    protocol = tomllib.loads((ROOT / 'config/clinical-bootstrap.toml').read_text())
    validate_protocol(protocol)
    validate_model_protocol(tomllib.loads((ROOT / 'config/clinical-baseline.toml').read_text()))
    versions = {rel: sha(ROOT / rel) for rel in CODE_PATHS}
    parent = ROOT / 'artifacts/clinical-bootstrap'
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if subprocess.run(['git', 'check-ignore', '--quiet', 'artifacts/clinical-bootstrap/probe'],
                      cwd=ROOT, capture_output=True).returncode:
        raise ValueError('Clinical output must be Git ignored')
    if resume_directory:
        dest = (ROOT / resume_directory).resolve()
        if not dest.is_relative_to(parent.resolve()) or dest == parent.resolve():
            raise ValueError('Resume must be a clinical-bootstrap artifact')
    else:
        dest = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-'), dir=parent))
    with exclusive_run(dest):
        old = json.loads((dest / 'manifest.json').read_text()) if resume_directory else None
        if old and (old['versions'] != versions or old['dependencies'] != dependencies
                    or old['protocol'] != protocol or old['rule_version'] != RULE_VERSION
                    or old['runtime']['python'] != platform.python_version()
                    or old['runtime']['machine'] != platform.machine()):
            raise ValueError('Resume requires identical code, protocol and numerical environment')
        if old:
            for rel, digest in versions.items():
                if sha(dest / 'code' / rel) != digest:
                    raise ValueError('Saved code copy hash mismatch')
            for rel, digest in old.get('committed_result_hashes', {}).items():
                if (Path(rel).is_absolute() or '..' in Path(rel).parts
                        or sha(dest / rel) != digest):
                    raise ValueError('Committed result hash mismatch')
        source = (ROOT / (old['input']['directory'] if old else input_directory)).resolve()
        if not source.is_relative_to((ROOT / 'artifacts/treatment-features').resolve()):
            raise ValueError('Input must be a local treatment-features artifact')
        input_manifest_hash = sha(source / 'manifest.json')
        if old and old['input']['manifest_sha256'] != input_manifest_hash:
            raise ValueError('Resume input manifest changed')
        print(json.dumps({'phase': 'loading_validated_dataset', 'directory': str(dest.relative_to(ROOT))}), flush=True)
        dataset = load_clinical_dataset(source)
        populations = {split: {name: build_cluster_population(dataset, split, name)
                               for name in POPULATIONS} for split in SPLITS}
        population_metadata = {split: {name: pop.metadata for name, pop in pops.items()}
                               for split, pops in populations.items()}
        if old and (old['populations'] != population_metadata or old['task'] != dataset.task):
            raise ValueError('Resume populations changed')
        if not old:
            for rel in versions:
                target = dest / 'code' / rel
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(ROOT / rel, target)
                target.chmod(0o600)
        for split in SPLITS:
            (dest / split).mkdir(exist_ok=True, mode=0o700)
        records = {split: read_committed(dest / split, dataset.task, split) for split in SPLITS}
        manifest = old or {
            'rule_version': RULE_VERSION, 'task': dataset.task, 'started_at_utc': now(),
            'input': {'directory': str(source.relative_to(ROOT)), 'manifest_sha256': input_manifest_hash},
            'protocol': protocol, 'versions': versions, 'dependencies': dependencies,
            'runtime': {'python': platform.python_version(), 'machine': platform.machine()},
            'populations': population_metadata, 'database_queried': False, 'llm_called': False,
            'full_paper_reproduction_complete': False, 'execution_sessions': [],
        }
        session = {'started_at_utc': now(), 'max_new_draws': max_new_draws, 'new_draws': 0}
        manifest['execution_sessions'].append(session)
        manifest['status'] = 'running'
        manifest['results'] = summarize_results(populations, records)
        manifest['updated_at_utc'] = now()
        save(dest / 'manifest.json', manifest)
        terminal = {split: {record['draw_id'] for record in rows} for split, rows in records.items()}
        try:
            with threadpool_limits(limits=1):
                manifest['runtime']['threadpools'] = threadpool_info()
                stop = False
                # Round robin makes short pilots cover each estimable shift.
                for draw_id in range(500):
                    for split in SPLITS:
                        if draw_id in terminal[split] or any(not pop.n_subjects for pop in populations[split].values()):
                            continue
                        start = time.monotonic()
                        unexpected = None
                        try:
                            record, payload, draws = run_dm_draw(dataset, populations[split], draw_id,
                                seed=protocol['seed'], batch_size=protocol['prediction_batch_size'])
                        except Exception as exc:
                            unexpected = exc
                            draws = {name: pop.draw(draw_id, seed=protocol['seed']) for name, pop in populations[split].items()}
                            record = {'draw_id': draw_id, 'status': 'failed',
                                      'reason': 'unexpected_exception_' + type(exc).__name__,
                                      'population_draw_metadata': {name: draw.metadata for name, draw in draws.items()}}
                            payload = {'status': 'failed', 'exception_type': type(exc).__name__}
                        record.update(task=dataset.task, split=split, elapsed_seconds=time.monotonic()-start,
                                      completed_at_utc=now())
                        record = commit_draw(dest / split, record, payload, draws)
                        records[split].append(record)
                        result_path = dest / split / f'draw-{draw_id:03d}' / 'result.json'
                        manifest.setdefault('committed_result_hashes', {})[str(result_path.relative_to(dest))] = sha(result_path)
                        session['new_draws'] += 1
                        manifest['results'] = summarize_results(populations, records)
                        manifest['updated_at_utc'] = now()
                        save(dest / 'manifest.json', manifest)
                        if session['new_draws'] <= 6 or session['new_draws'] % 10 == 0:
                            print(json.dumps({'task': dataset.task, 'split': split, 'draw_id': draw_id,
                                'status': record['status'], 'elapsed_seconds': record['elapsed_seconds'],
                                'attempted_draws': sum(len(rows) for rows in records.values())}), flush=True)
                        if unexpected is not None:
                            raise RuntimeError('Unexpected draw exception; failed ID retained, see private artifact') from unexpected
                        if max_new_draws and session['new_draws'] >= max_new_draws:
                            stop = True
                            break
                    if stop:
                        break
            if any(sha(ROOT / rel) != digest for rel, digest in versions.items()):
                raise ValueError('Code changed during execution')
            eligible = [value for value in manifest['results'].values() if value['status'] != 'not_estimable']
            done = all(not value['pending_draws'] for value in eligible)
            failures = sum(value['failed_draws'] for value in eligible)
            manifest['status'] = ('complete_with_failures' if failures else 'complete') if done else 'in_progress'
        except BaseException as exc:
            manifest['status'] = 'interrupted'
            session['interruption_type'] = type(exc).__name__
            raise
        finally:
            session['ended_at_utc'] = now()
            manifest['updated_at_utc'] = now()
            manifest['results'] = summarize_results(populations, records)
            manifest['committed_result_hashes'] = {
                str(path.relative_to(dest)): sha(path) for split in SPLITS
                for path in sorted((dest / split).glob('draw-*/result.json'))}
            save(dest / 'manifest.json', manifest)
        print(json.dumps({'directory': str(dest.relative_to(ROOT)), 'status': manifest['status'],
                          'completed_draws': {split: value['completed_draws']
                                              for split, value in manifest['results'].items()}}, ensure_ascii=False), flush=True)
        return dest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--input-directory')
    group.add_argument('--resume-directory')
    parser.add_argument('--max-new-draws', type=int,
                        help='Stop this session after N new draws; planned count stays500 per estimable split')
    args = parser.parse_args()
    run(args.input_directory, args.resume_directory, args.max_new_draws)
