#!/usr/bin/env python3
"""Fixed-budget prefixes with unchanged paired DM+ patient-bootstrap fits.

New artifacts only. The saved DM draws, OLS, factual preprocessing, patient
multiplicities and conditional squared-error t-test are unchanged. Budget 0
reuses original DM; existing budget 500 artifacts remain the authoritative
endpoints. Budget 500 here is supported for bounded equivalence checks.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import time
import tomllib

BUNDLE_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('APRIL_BUDGET_BOOTSTRAP_PROJECT_ROOT', str(BUNDLE_ROOT))).resolve()
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
import numpy as np
from threadpoolctl import threadpool_limits
from april_repro.clinical_dataset import load_clinical_dataset
from april_repro.clinical_dmplus_formal import load_model_evidence, select_prefix
from april_repro.clinical_dmplus_bootstrap import run_paired_draw
from april_repro.clinical_dmplus_bootstrap_statistics import summarize_paired_bootstrap_draws
from april_repro.cluster_bootstrap import POPULATIONS, build_cluster_population
from april_repro.cohort_splits import SPLITS
import run_clinical_bootstrap as dm_runner
import run_clinical_dmplus_formal as point_runner

RULE_VERSION = 'clinical-dmplus-paired-bootstrap-budgets-v1'
ANNOTATION_BUDGETS = (100, 200, 300, 400, 500)
MODEL_KEYS = ('gpt-4o-mini', 'o3-mini', 'kimi', 'deepseek', 'qwen')
PROTOCOL = 'config/clinical-dmplus-bootstrap-budgets.toml'
ENTRYPOINT = 'scripts/run_clinical_dmplus_bootstrap_budgets.py'
CODE_PATHS = tuple(dict.fromkeys((*dm_runner.CODE_PATHS, *point_runner.CODE_PATHS,
    'src/april_repro/clinical_dmplus_bootstrap.py',
    'src/april_repro/clinical_dmplus_bootstrap_statistics.py',
    ENTRYPOINT, PROTOCOL)))
sha, save, now = dm_runner.sha, dm_runner.save, dm_runner.now


def source_path(name):
    return (BUNDLE_ROOT if name in (ENTRYPOINT, PROTOCOL) else ROOT) / name


def validate_annotation_budget(value):
    if type(value) is not int or value not in ANNOTATION_BUDGETS:
        raise ValueError('Explicit annotation budget must be 100, 200, 300, 400 or 500')
    return value


def validate_protocol(value):
    required = {'rule_version': RULE_VERSION, 'model_keys': list(MODEL_KEYS),
        'requested_annotation_budgets': list(ANNOTATION_BUDGETS), 'bootstrap_datasets': 500,
        'seed': 'april-cluster-bootstrap-v1', 'sampling_unit': 'patient_cluster',
        'reuse_completed_dm_draws': True, 'nested_bootstrap': False,
        'annotation_resampling': 'fixed available annotation cache; same source behavior-patient multiplicity as factual rows',
        'paired_test_scores': 'per-draw squared errorDM minus squared errorDMplus',
        'alpha': 0.05, 'blas_threads': 1, 'external_llm_calls': False,
        'database_queries': False}
    if any(value.get(k) != v for k, v in required.items()):
        raise ValueError('Paired bootstrap protocol differs from implementation')


def load_dm_source(folder):
    manifest = json.loads((folder / 'manifest.json').read_bytes())
    if (manifest.get('rule_version') != dm_runner.RULE_VERSION
            or manifest.get('status') != 'complete'
            or manifest.get('dependencies') != dm_runner.DEPENDENCIES):
        raise ValueError('Expected complete original clinical DM bootstrap')
    dm_runner.validate_protocol(manifest['protocol'])
    expected_versions = {p: sha(ROOT / p) for p in dm_runner.CODE_PATHS}
    if manifest['versions'] != expected_versions:
        raise ValueError('Original DM implementation changed')
    for name, digest in expected_versions.items():
        if sha(folder / 'code' / name) != digest:
            raise ValueError('Original DM code copy changed')
    records = {split: dm_runner.read_committed(folder / split, manifest['task'], split) for split in SPLITS}
    actual_hashes = {str((folder / split / f'draw-{r["draw_id"]:03d}' / 'result.json').relative_to(folder)):
                    sha(folder / split / f'draw-{r["draw_id"]:03d}' / 'result.json')
                    for split, rows in records.items() for r in rows}
    if actual_hashes != manifest['committed_result_hashes']:
        raise ValueError('Original DM committed result identity changed')
    for split in SPLITS:
        result = manifest['results'][split]
        rows = records[split]
        if result['status'] == 'not_estimable':
            if rows:
                raise ValueError('Empty original split has draws')
        elif (result['status'] != 'complete' or len(rows) != 500
              or any(r['status'] != 'complete' for r in rows)
              or dm_runner.summarize_bootstrap_draws(rows) != result):
            raise ValueError('Original DM must have all500 valid draws')
    return manifest, records


def validate_model_key(model_key):
    if not isinstance(model_key, str) or model_key not in MODEL_KEYS:
        raise ValueError('Explicit supported model key is required')
    return model_key


def load_point_source(folder, task, model_key):
    validate_model_key(model_key)
    m = json.loads((folder / 'manifest.json').read_bytes())
    if (m.get('status') != 'complete' or m.get('scope') != 'formal_fixed_prefix_dmplus_point'
            or m.get('source_model_key') != model_key or task not in m.get('tasks', {})
            or m.get('annotation_evidence', {}).get('selected_model_key') != model_key
            or m.get('annotation_summary', {}).get('model_key') != model_key):
        raise ValueError('Expected completed formal points for the selected model')
    for name, digest in m['outputs'].items():
        rel = Path(name)
        if rel.is_absolute() or '..' in rel.parts or sha(folder / rel) != digest:
            raise ValueError('Point artifact output identity mismatch')
    for name, digest in m['versions'].items():
        if sha(ROOT / name) != digest or sha(folder / 'code' / name) != digest:
            raise ValueError('Point implementation changed')
    return m


def read_committed(dest, task, originals, dm_source=None, *, model_key, annotation_budget):
    validate_model_key(model_key)
    rows = {split: [] for split in SPLITS}
    for split in SPLITS:
        original_map = {r['draw_id']: r for r in originals[split]}
        for directory in sorted((dest / split).glob('draw-*')):
            r = json.loads((directory / 'result.json').read_bytes())
            if (r.get('task') != task or r.get('split') != split
                    or r.get('source_model_key') != model_key
                    or r.get('requested_annotation_budget') != annotation_budget
                    or type(r.get('draw_id')) is not int or not 0 <= r['draw_id'] < 500
                    or directory.name != f'draw-{r["draw_id"]:03d}'
                    or r.get('status') not in ('complete', 'failed')):
                raise ValueError('DM+ committed draw identity mismatch')
            if set(r.get('outputs', {})) != {'models.json'}:
                raise ValueError('DM+ committed model identity missing')
            if sha(directory / 'models.json') != r['outputs']['models.json']:
                raise ValueError('DM+ committed model changed')
            original = original_map.get(r['draw_id'])
            if (original is None or r.get('original_model_sha256') != original['outputs']['models.json']
                    or r.get('original_patient_counts_sha256') != original['outputs']['patient-counts.npz']
                    or dm_source is not None and r.get('original_result_sha256') != sha(
                        dm_source / split / directory.name / 'result.json')):
                raise ValueError('Saved DM+ original draw identity changed')
            rows[split].append(r)
        if originals[split]:
            summarize_paired_bootstrap_draws(originals[split], rows[split])
        elif rows[split]:
            raise ValueError('Not estimable split unexpectedly fitted')
    return rows


def commit_draw(folder, record, payload):
    final = folder / f'draw-{record["draw_id"]:03d}'
    if final.exists():
        raise ValueError('Refusing to overwrite a committed DM+ draw')
    temporary = Path(tempfile.mkdtemp(prefix='.uncommitted-', dir=folder))
    save(temporary / 'models.json', payload)
    record = dict(record, outputs={'models.json': sha(temporary / 'models.json')})
    save(temporary / 'result.json', record)
    temporary.rename(final)
    return record


def summarize(originals, records, point, annotation_budget):
    result = {}
    for split in SPLITS:
        p = point['results'][split][str(annotation_budget)]
        if not originals[split]:
            result[split] = {'status': 'not_estimable', 'reason': 'empty_original_population',
                'planned_draws': 500, 'completed_pairs': 0,
                'requested_annotation_budget': annotation_budget, 'valid_unique_cached_annotations': p['valid_annotations']}
        else:
            result[split] = summarize_paired_bootstrap_draws(originals[split], records[split],
                full_point={'dm_value': p['dm'], 'dmplus_value': p['dm_plus'],
                            'observed_reference_value': p['observed_reference']})
            result[split].update(requested_annotation_budget=annotation_budget,
                valid_unique_cached_annotations=p['valid_annotations'],
                exact_requested_annotation_budget=p['valid_annotations'] == annotation_budget)
    return result


def _run(dm_bootstrap_directory=None, point_directory=None, output_directory=None,
         resume_directory=None, max_new_draws=None, model_key=None, annotation_budget=None, verification_root=None):
    if max_new_draws is not None and (type(max_new_draws) is not int or max_new_draws < 1):
        raise ValueError('max_new_draws must be positive')
    if resume_directory and any(x is not None for x in (dm_bootstrap_directory, point_directory, output_directory, model_key, annotation_budget, verification_root)):
        raise ValueError('Resume uses only its original recorded inputs')
    if not resume_directory and any(x is None for x in (dm_bootstrap_directory, point_directory, output_directory)):
        raise ValueError('New run requires DM source, point source and new output')
    if not resume_directory:
        validate_model_key(model_key)
        validate_annotation_budget(annotation_budget)
    dependencies = {k: importlib.metadata.version(k) for k in dm_runner.DEPENDENCIES}
    if dependencies != dm_runner.DEPENDENCIES:
        raise ValueError('Numerical dependencies differ')
    protocol = tomllib.loads(source_path(PROTOCOL).read_text())
    validate_protocol(protocol)
    versions = {name: sha(source_path(name)) for name in CODE_PATHS}
    runtime = {'python': platform.python_version(), 'machine': platform.machine()}
    if resume_directory:
        dest = Path(resume_directory).resolve()
        old = json.loads((dest / 'manifest.json').read_bytes())
        model_key = validate_model_key(old.get('model_key'))
        annotation_budget = validate_annotation_budget(old.get('requested_annotation_budget'))
        verification_root = old.get('verification_root')
        dm_source = Path(old['sources']['dm_bootstrap']['directory'])
        point_source = Path(old['sources']['point']['directory'])
    else:
        dest = Path(output_directory).resolve()
        if dest.exists():
            raise ValueError('Output already exists; use resume without replacing it')
        dm_source, point_source = Path(dm_bootstrap_directory).resolve(), Path(point_directory).resolve()
        old = None
    protocol = dict(protocol, requested_annotation_budget=annotation_budget)
    parent = (ROOT / 'artifacts/clinical-dmplus-budget-bootstrap').resolve()
    if verification_root is not None:
        parent = Path(verification_root).resolve()
        tmp = Path('/private/tmp').resolve()
        if parent == tmp or not parent.is_relative_to(tmp) or max_new_draws is None:
            raise ValueError('Verification output requires a private /tmp subdirectory and a bounded draw limit')
        verification_root = str(parent)
    if not dest.is_relative_to(parent) or dest == parent:
        raise ValueError('Output must be inside the separate private budget-bootstrap artifacts')
    if not dest.name.endswith('-' + str(annotation_budget)):
        raise ValueError('Output directory must end with its annotation budget suffix')
    if not old:
        dest.mkdir(parents=True, mode=0o700)
    with dm_runner.exclusive_run(dest):
        if old and (old['versions'] != versions or old['protocol'] != protocol
                    or old['dependencies'] != dependencies or old['runtime'] != runtime
                    or old['rule_version'] != RULE_VERSION):
            raise ValueError('Resume requires unchanged code/protocol/runtime')
        dm, originals = load_dm_source(dm_source)
        points = load_point_source(point_source, dm['task'], model_key)
        point = points['tasks'][dm['task']]
        sources = {'dm_bootstrap': {'directory': str(dm_source), 'manifest_sha256': sha(dm_source / 'manifest.json')},
                   'point': {'directory': str(point_source), 'manifest_sha256': sha(point_source / 'manifest.json')}}
        if old and old['sources'] != sources:
            raise ValueError('Resume scientific source identity changed')
        if old:
            for name, digest in versions.items():
                if sha(dest / 'code' / name) != digest:
                    raise ValueError('Saved DM+ code copy changed')
            for name, digest in old['committed_result_hashes'].items():
                rel = Path(name)
                if rel.is_absolute() or '..' in rel.parts or sha(dest / rel) != digest:
                    raise ValueError('Saved committed DM+ result changed')
        else:
            for name in CODE_PATHS:
                target = dest / 'code' / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(source_path(name), target)
                target.chmod(0o600)
            for split in SPLITS:
                (dest / split).mkdir(mode=0o700)
        print(json.dumps({'phase': 'validating_annotations_and_loading_dataset', 'task': dm['task']}), flush=True)
        ann_source = points['annotation_evidence']
        evidence = load_model_evidence(ann_source['formal_plan_directory'], ann_source['run_directory'], model_key)
        if evidence.provenance != ann_source:
            raise ValueError('Selected annotation source changed since point fit')
        dataset = load_clinical_dataset((ROOT / dm['input']['directory']).resolve())
        if (dataset.task != dm['task'] or dataset.provenance['manifest_sha256'] != dm['input']['manifest_sha256']
                or dataset.provenance != point['input']):
            raise ValueError('Paired input differs from original DM or point input')
        populations = {s: {name: build_cluster_population(dataset, s, name) for name in POPULATIONS} for s in SPLITS}
        if {s: {name: p.metadata for name, p in pops.items()} for s, pops in populations.items()} != dm['populations']:
            raise ValueError('Original patient populations changed')
        index = {event: i for i, event in enumerate(dataset.event_ids)}
        annotations = {}
        for split in SPLITS:
            selected, coverage = select_prefix(dataset, evidence, split, model_key, annotation_budget, index)
            saved = json.loads((point_source / dataset.task / split / str(annotation_budget) / 'annotations-used.json').read_bytes())
            reproduced = [{'request_id': r.request_id, 'event_id': r.event_id, 'action': r.action, 'reward': r.reward} for r in selected]
            if (saved.get('source') != model_key or saved.get('requested_budget') != annotation_budget
                    or saved['annotations'] != reproduced
                    or coverage['valid_annotations'] != point['results'][split][str(annotation_budget)]['valid_annotations']):
                raise ValueError('Fixed annotation prefix changed')
            annotations[split] = selected
        del index, evidence
        records = read_committed(dest, dataset.task, originals, dm_source, model_key=model_key, annotation_budget=annotation_budget)
        original_maps = {s: {r['draw_id']: r for r in rows} for s, rows in originals.items()}
        finished = {s: {r['draw_id'] for r in rows} for s, rows in records.items()}
        result_hashes = {f'{s}/draw-{r["draw_id"]:03d}/result.json':
            sha(dest / s / f'draw-{r["draw_id"]:03d}' / 'result.json') for s, rows in records.items() for r in rows}
        manifest = dict(old) if old else {'rule_version': RULE_VERSION, 'scope': 'paired_dm_dmplus_patient_bootstrap',
            'task': dataset.task, 'model_key': model_key, 'requested_annotation_budget': annotation_budget,
            'verification_root': verification_root, 'verification_only': verification_root is not None,
            'started_at_utc': now(), 'sources': sources,
            'versions': versions, 'protocol': protocol, 'dependencies': dependencies, 'runtime': runtime,
            'input': dm['input'], 'llm_called': False, 'database_queried': False,
            'paper_hidden_statistical_algorithm_recovered': False}

        def checkpoint(status):
            manifest.update(status=status, updated_at_utc=now(), results=summarize(originals, records, point, annotation_budget),
                committed_result_hashes=dict(result_hashes))
            save(dest / 'manifest.json', manifest)

        checkpoint('running')
        added = 0
        started = time.monotonic()
        try:
            with threadpool_limits(limits=1):
                for draw_id in range(500):
                    for split in SPLITS:
                        if not originals[split] or draw_id in finished[split]:
                            continue
                        source = dm_source / split / f'draw-{draw_id:03d}'
                        original = original_maps[split][draw_id]
                        payload = json.loads((source / 'models.json').read_bytes())
                        with np.load(source / 'patient-counts.npz', allow_pickle=False) as values:
                            counts = {k: values[k] for k in values.files}
                        draw_error = None
                        try:
                            record, fitted = run_paired_draw(dataset, populations[split], original, payload, counts, annotations[split],
                                requested_budget=annotation_budget)
                        except Exception as error:
                            draw_error = error
                            record = {'rule_version': RULE_VERSION, 'task': dataset.task, 'split': split,
                                'draw_id': draw_id, 'seed': original['seed'], 'status': 'failed',
                                'reason': 'local_pairing_or_numerical_failure', 'error_type': type(error).__name__,
                                'population_draw_metadata': original['population_draw_metadata'],
                                'requested_annotation_budget': annotation_budget, 'unique_cachevalid_annotations': len(annotations[split])}
                            fitted = {'status': 'failed', 'error_type': type(error).__name__,
                                'metadata': {'task': dataset.task, 'split': split, 'draw_id': draw_id}}
                        record.update(source_model_key=model_key, original_result_sha256=sha(source / 'result.json'),
                            original_model_sha256=original['outputs']['models.json'],
                            original_patient_counts_sha256=original['outputs']['patient-counts.npz'])
                        record = commit_draw(dest / split, record, fitted)
                        records[split].append(record)
                        finished[split].add(draw_id)
                        result_hashes[f'{split}/draw-{draw_id:03d}/result.json'] = sha(dest / split / f'draw-{draw_id:03d}' / 'result.json')
                        added += 1
                        checkpoint('running')
                        if draw_error is not None:
                            raise draw_error
                        if added == 1 or added % 25 == 0:
                            print(json.dumps({'phase': 'paired_bootstrap', 'task': dataset.task,
                                'completed_draws': sum(len(r) for r in records.values()),
                                'new_draws': added, 'seconds': round(time.monotonic() - started, 2)}), flush=True)
                        if max_new_draws is not None and added >= max_new_draws:
                            checkpoint('partial')
                            return dest
            if any(sha(Path(source['directory']) / 'manifest.json') != source['manifest_sha256'] for source in sources.values()):
                raise ValueError('Scientific source changed during fitting')
            if any(sha(source_path(name)) != digest for name, digest in versions.items()):
                raise ValueError('Implementation changed during fitting')
            checkpoint('complete' if all(not originals[s] or len(records[s]) == 500
                and all(r['status'] == 'complete' for r in records[s]) for s in SPLITS) else 'partial')
        except BaseException:
            checkpoint('interrupted')
            raise
        return dest


def run(dm_bootstrap_directory=None, point_directory=None, output_directory=None,
        resume_directory=None, max_new_draws=None, model_key=None, annotation_budget=None, verification_root=None):
    previous_umask = os.umask(0o077)
    try:
        return _run(dm_bootstrap_directory, point_directory, output_directory,
                    resume_directory, max_new_draws, model_key, annotation_budget, verification_root)
    finally:
        os.umask(previous_umask)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dm-bootstrap-directory')
    parser.add_argument('--point-directory')
    parser.add_argument('--output-directory')
    parser.add_argument('--resume-directory')
    parser.add_argument('--max-new-draws', type=int)
    parser.add_argument('--model-key', choices=MODEL_KEYS, help='Required for a new run; resume uses its saved model')
    parser.add_argument('--annotation-budget', type=int, choices=ANNOTATION_BUDGETS,
        help='Required for a new run; resume uses its saved budget; zero reuses original DM')
    parser.add_argument('--verification-root', help='Bounded verification only: a private /tmp output root')
    args = parser.parse_args(argv)
    try:
        result = run(**vars(args))
        print(json.dumps({'phase': 'finished', 'artifact': str(result)}), flush=True)
        return 0
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__,
            'details': 'Local input or numerical verification failed; no external calls.'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
