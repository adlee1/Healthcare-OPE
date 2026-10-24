#!/usr/bin/env python3
"""Offline replay of two selected APRIL baselines using unchanged numerical cores."""
from __future__ import annotations
import argparse
import gc
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import sys
import tempfile
from datetime import datetime, timezone

VERSION = 'april-selected-baselines-portable-v1'
BUDGETS = (0, 100, 200, 300, 400, 500)
SEED = 'april-cluster-bootstrap-v1'
TOLERANCE = 1e-12


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')
    path.chmod(0o600)


def inside(root, relative):
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts or not rel.parts:
        raise ValueError('Package paths must be relative and cannot escape the bundle')
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Package symlink escapes the bundle')
    return path


def verify(path, expected):
    if sha(path) != expected:
        raise ValueError('Source hash mismatch: ' + path.name)


def numbers(text, allowed):
    values = [int(x) for x in text.split(',')]
    if not values or len(set(values)) != len(values) or any(x not in allowed for x in values):
        raise ValueError('Invalid or repeated draw/budget selection')
    return sorted(values)


def check_close(actual, expected, label):
    if not (math.isfinite(actual) and math.isfinite(expected)
            and math.isclose(actual, expected, rel_tol=0, abs_tol=TOLERANCE)):
        raise ValueError('Numerical replay differs: ' + label)


def compare_tree(actual, expected, label='model'):
    if isinstance(actual, dict) and isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise ValueError('Replay field set differs: ' + label)
        for key in actual:
            compare_tree(actual[key], expected[key], label + '.' + key)
    elif isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError('Replay array length differs: ' + label)
        for a, b in zip(actual, expected):
            compare_tree(a, b, label)
    elif isinstance(actual, (float, int)) and not isinstance(actual, bool) and isinstance(expected, (float, int)) and not isinstance(expected, bool):
        check_close(actual, expected, label)
    elif actual != expected:
        raise ValueError('Replay metadata differs: ' + label)


def artifact(root, reference):
    directory = inside(root, reference['directory'])
    verify(directory / 'manifest.json', reference['manifest_sha256'])
    manifest = load(directory / 'manifest.json')
    if manifest.get('status') != 'complete':
        raise ValueError('Input artifact is not complete')
    return directory, manifest


def verify_sources(root, index, case):
    dirs, manifests = {}, {}
    for name in ('features', 'dm', 'point', 'dmplus'):
        dirs[name], manifests[name] = artifact(root, case[name])
    for budget, reference in case['budget_dmplus'].items():
        name = 'budget_' + budget
        dirs[name], manifests[name] = artifact(root, reference)
    task, split, model = (case[k] for k in ('task', 'split', 'model_key'))
    feature, dm, point = (manifests[k] for k in ('features', 'dm', 'point'))
    if (feature['task'] != task or dm['task'] != task or point['source_model_key'] != model
            or point['annotation_evidence']['selected_model_key'] != model
            or point['annotation_summary']['model_key'] != model):
        raise ValueError('Case source task/model identity differs')
    if dm['input']['manifest_sha256'] != case['features']['manifest_sha256']:
        raise ValueError('Original DM feature binding differs')
    point_input = point['tasks'][task]['input']
    if (point_input['manifest_sha256'] != case['features']['manifest_sha256']
            or point_input['outputs'] != feature['outputs']
            or Path(point_input['artifact_directory']) != Path(case['features']['original_directory'])):
        raise ValueError('Point feature binding differs')
    original_feature_path = Path(index['source_root']) / dm['input']['directory']
    if original_feature_path != Path(case['features']['original_directory']):
        raise ValueError('Original feature relocation differs')
    for name in ('features', 'point'):
        for relative, digest in manifests[name]['outputs'].items():
            verify(inside(dirs[name], relative), digest)
    if dm['protocol']['seed'] != SEED or dm['protocol']['bootstrap_datasets'] != 500:
        raise ValueError('Original DM bootstrap protocol differs')
    for name in ('dmplus', *('budget_' + str(b) for b in BUDGETS[1:-1])):
        m = manifests[name]
        budget = 500 if name == 'dmplus' else int(name.split('_')[1])
        if (m['task'] != task or m['model_key'] != model
                or m['protocol']['seed'] != SEED or m['protocol']['bootstrap_datasets'] != 500
                or m['protocol']['requested_annotation_budget'] != budget):
            raise ValueError('Cached case/budget/protocol identity differs')
        for key, target in (('dm_bootstrap', 'dm'), ('point', 'point')):
            if m['sources'][key] != {'directory': case[target]['original_directory'],
                                    'manifest_sha256': case[target]['manifest_sha256']}:
                raise ValueError('Original manifest source binding differs')
        if m['input'] != dm['input']:
            raise ValueError('Cached feature input differs')
    for m in manifests.values():
        for relative, digest in m.get('versions', {}).items():
            if relative.startswith('src/april_repro/'):
                if index['source_code_sha256'].get(relative) != digest:
                    raise ValueError('Original numerical source binding differs')
    return dirs, manifests


def read_draws(directory, manifest, split, task, *, model=None, originals=None, dm_directory=None):
    rows = []
    for draw_id in range(500):
        relative = f'{split}/draw-{draw_id:03d}/result.json'
        path = inside(directory, relative)
        verify(path, manifest['committed_result_hashes'][relative])
        row = load(path)
        if (row['status'] != 'complete' or row['draw_id'] != draw_id or row['task'] != task
                or row['split'] != split or row['seed'] != SEED):
            raise ValueError('Committed draw identity differs')
        wanted = {'models.json', 'patient-counts.npz'} if model is None else {'models.json'}
        if set(row['outputs']) != wanted:
            raise ValueError('Committed draw outputs differ')
        for filename, digest in row['outputs'].items():
            verify(inside(path.parent, filename), digest)
        if model is not None:
            original = originals[draw_id]
            legacy_deepseek = (model == 'deepseek' and manifest.get('rule_version') == 'clinical-dmplus-paired-bootstrap-v1')
            if (row.get('source_model_key', model if legacy_deepseek else None) != model
                    or row['original_result_sha256'] != sha(dm_directory / relative)
                    or row['original_model_sha256'] != original['outputs']['models.json']
                    or row['original_patient_counts_sha256'] != original['outputs']['patient-counts.npz']):
                raise ValueError('Paired original draw binding differs')
            metadata = load(path.parent / 'models.json')['metadata']
            if (metadata['task'] != task or metadata['split'] != split or metadata['draw_id'] != draw_id
                    or metadata['seed'] != SEED
                    or metadata.get('source_model_key') != (model if row['unique_cachevalid_annotations'] else None)):
                raise ValueError('Paired model metadata differs')
        rows.append(row)
    return rows


def full_point(point, task, split, budget):
    p = point['tasks'][task]['results'][split][str(budget)]
    return {'dm_value': p['dm'], 'dmplus_value': p['dm_plus'],
            'observed_reference_value': p['observed_reference']}


def zero_records(originals):
    # Budget zero is the exact saved DM identity, with no fitting or new draw.
    return [dict(r, original_dm_value=r['dm_value'], original_dm_signed_error=r['signed_error'],
                 requested_annotation_budget=0, unique_cachevalid_annotations=0) for r in originals]


def prepare_case(root, index, case, budgets):
    from april_repro.clinical_bootstrap_statistics import summarize_bootstrap_draws
    from april_repro.clinical_dmplus_bootstrap_statistics import summarize_paired_bootstrap_draws
    dirs, manifests = verify_sources(root, index, case)
    task, split, model = (case[k] for k in ('task', 'split', 'model_key'))
    originals = read_draws(dirs['dm'], manifests['dm'], split, task)
    if summarize_bootstrap_draws(originals) != manifests['dm']['results'][split]:
        raise ValueError('Original DM cached statistics differ')
    cached, summaries = {}, {}
    for budget in budgets:
        if budget == 0:
            rows = zero_records(originals)
        else:
            name = 'dmplus' if budget == 500 else 'budget_' + str(budget)
            rows = read_draws(dirs[name], manifests[name], split, task, model=model,
                              originals=originals, dm_directory=dirs['dm'])
        summary = summarize_paired_bootstrap_draws(originals, rows, planned_draws=500,
            full_point=full_point(manifests['point'], task, split, budget))
        if budget:
            saved = manifests[name]['results'][split]
            if any(saved.get(k) != value for k, value in summary.items()):
                raise ValueError('Recomputed cached paired statistics differ')
        p = manifests['point']['tasks'][task]['results'][split][str(budget)]
        if (p['requested_annotations'] != budget or p['missing_annotations'] != 0
                or p['valid_annotations'] + p['invalid_annotations_including_missing'] != budget):
            raise ValueError('Fixed annotation prefix accounting differs')
        cached[budget] = rows
        summaries[str(budget)] = dict(summary, requested_annotation_budget=budget,
            valid_unique_cached_annotations=p['valid_annotations'],
            exact_requested_valid_annotation_budget=p['valid_annotations'] == budget,
            computation='recomputed_from_original_cached_draws' if budget else 'exact_budget_zero_DM_identity')
    return dirs, manifests, originals, cached, summaries


def annotations_for(dataset, point_dir, point, case, budget, event_index):
    from april_repro.clinical_dmplus import Counterfactual
    task, split, model = (case[k] for k in ('task', 'split', 'model_key'))
    relative = f'{task}/{split}/{budget}/annotations-used.json'
    verify(point_dir / relative, point['outputs'][relative])
    saved = load(point_dir / relative)
    p = point['tasks'][task]['results'][split][str(budget)]
    if (saved['source'] != model or saved['requested_budget'] != budget
            or saved['protocol_id'] != p['annotation_protocol_id']
            or len(saved['annotations']) != p['valid_annotations']):
        raise ValueError('Annotation cache source/prefix differs')
    return tuple(Counterfactual(row['request_id'], row['event_id'], event_index[row['event_id']],
        row['action'], row['reward'], model, saved['protocol_id']) for row in saved['annotations'])


def commit_fit(directory, record, models, identity):
    """Commit both files and their hashes atomically; never overwrite a draw."""
    directory.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.exists():
        raise ValueError('Refusing to overwrite a committed fresh draw')
    temporary = Path(tempfile.mkdtemp(prefix='.uncommitted-', dir=directory.parent))
    save(temporary / 'models.json', models)
    save(temporary / 'result.json', record)
    save(temporary / 'commit.json', {'identity': identity, 'outputs': {
        name: sha(temporary / name) for name in ('result.json', 'models.json')}})
    temporary.rename(directory)


def read_fit(directory, identity):
    commit = load(directory / 'commit.json')
    if commit.get('identity') != identity or set(commit.get('outputs', {})) != {'result.json', 'models.json'}:
        raise ValueError('Fresh resume draw identity differs')
    for name, digest in commit['outputs'].items():
        verify(directory / name, digest)
    return load(directory / 'result.json'), load(directory / 'models.json')


def fresh_case(case_id, case, index, dirs, manifests, originals, cached, budgets, draw_ids, refit_dm, output,
               resume, plan_sha256):
    import numpy as np
    from threadpoolctl import threadpool_limits
    from april_repro.clinical_dataset import load_clinical_dataset
    from april_repro.cluster_bootstrap import POPULATIONS, build_cluster_population
    from april_repro.clinical_bootstrap import run_dm_draw
    from april_repro.clinical_dmplus_bootstrap import run_paired_draw
    from april_repro.clinical_dmplus_bootstrap_statistics import summarize_paired_bootstrap_draws
    task, split, model = (case[k] for k in ('task', 'split', 'model_key'))
    dataset = load_clinical_dataset(dirs['features'])
    if dataset.provenance['manifest_sha256'] != case['features']['manifest_sha256']:
        raise ValueError('Loaded feature manifest differs')
    populations = {name: build_cluster_population(dataset, split, name) for name in POPULATIONS}
    if {k: p.metadata for k, p in populations.items()} != manifests['dm']['populations'][split]:
        raise ValueError('Original selected patient population differs')
    event_index = {event: i for i, event in enumerate(dataset.event_ids)}
    annotations = {b: annotations_for(dataset, dirs['point'], manifests['point'], case, b, event_index) for b in budgets}
    del event_index
    results = {b: [] for b in budgets}
    compared = []
    working_originals = [dict(r) for r in originals]
    with threadpool_limits(limits=1):
        for draw_id in draw_ids:
            reused_fits = 0
            identity = {'run_plan_sha256': plan_sha256, 'case': case_id, 'task': task,
                        'split': split, 'model_key': model, 'draw_id': draw_id, 'seed': SEED}
            folder = dirs['dm'] / split / f'draw-{draw_id:03d}'
            original = originals[draw_id]
            payload = load(folder / 'models.json')
            with np.load(folder / 'patient-counts.npz', allow_pickle=False) as archive:
                counts = {k: archive[k] for k in archive.files}
            if refit_dm:
                refit_dir = output / case_id / 'refitted_dm' / f'draw-{draw_id:03d}'
                refit_identity = dict(identity, stage='refitted_original_DM')
                if resume and refit_dir.exists():
                    rebuilt, fitted = read_fit(refit_dir, refit_identity)
                    draws = {name: population.draw(draw_id, seed=SEED) for name, population in populations.items()}
                else:
                    rebuilt, fitted, draws = run_dm_draw(dataset, populations, draw_id, seed=SEED,
                        batch_size=manifests['dm']['protocol']['prediction_batch_size'])
                if rebuilt['status'] != 'complete':
                    raise ValueError('Fresh original DM refit failed; no replacement draw')
                for field in ('dm_value', 'observed_reference_value', 'signed_error', 'squared_error'):
                    check_close(rebuilt[field], original[field], 'refitted_DM.' + field)
                if rebuilt['population_draw_metadata'] != original['population_draw_metadata']:
                    raise ValueError('Refitted DM patient draw metadata differs')
                compare_tree(fitted, payload, 'refitted_original_models')
                for name, draw in draws.items():
                    if (not np.array_equal(counts[name + '_subject_ids'], draw.subject_ids)
                            or not np.array_equal(counts[name + '_patient_counts'], draw.patient_counts)):
                        raise ValueError('Refitted DM patient counts differ')
                original, payload = rebuilt, fitted
                working_originals[draw_id] = original
                if not refit_dir.exists():
                    commit_fit(refit_dir, rebuilt, fitted, refit_identity)
                del draws
            for budget in budgets:
                dest = output / case_id / str(budget) / f'draw-{draw_id:03d}'
                paired_identity = dict(identity, stage='paired_DMplus', requested_budget=budget)
                if resume and dest.exists():
                    record, fitted_plus = read_fit(dest, paired_identity)
                    reused_fits += 1
                else:
                    record, fitted_plus = run_paired_draw(dataset, populations, original, payload, counts,
                        annotations[budget], requested_budget=budget)
                    record.update(source_model_key=model,
                        portable_run_mode='refit_DM_and_target_then_refit_DMplus' if refit_dm else 'reuse_saved_DM_target_then_refit_DMplus')
                expected = cached[budget][draw_id]
                if (record['task'] != task or record['split'] != split or record['draw_id'] != draw_id
                        or record['seed'] != SEED or record['source_model_key'] != model
                        or record['requested_annotation_budget'] != budget
                        or record['population_draw_metadata'] != original['population_draw_metadata']):
                    raise ValueError('Fresh/resumed paired draw identity differs')
                meta = fitted_plus['metadata']
                if (meta['task'] != task or meta['split'] != split or meta['draw_id'] != draw_id
                        or meta['seed'] != SEED or meta['feature_manifest_sha256'] != case['features']['manifest_sha256']
                        or meta['source_model_key'] != (model if annotations[budget] else None)):
                    raise ValueError('Fresh/resumed model identity differs')
                for field in ('dm_value', 'observed_reference_value', 'signed_error', 'squared_error'):
                    check_close(record[field], expected[field], 'DMplus.' + field)
                if budget == 0 and record['dm_value'] != original['dm_value']:
                    raise ValueError('Budget zero is not exact DM identity')
                if budget:
                    for field in ('population_draw_metadata', 'unique_cachevalid_annotations',
                                  'draw_annotation_rows', 'draw_annotation_unique', 'factual_training_events',
                                  'evaluation_events', 'evaluation_unique_subjects'):
                        if record[field] != expected[field]:
                            raise ValueError('Fresh paired draw accounting differs: ' + field)
                if not dest.exists():
                    commit_fit(dest, record, fitted_plus, paired_identity)
                results[budget].append(record)
            compared.append(draw_id)
            print(json.dumps({'phase': 'fresh_draw_verified', 'case': case_id, 'draw_id': draw_id,
                'completed_selected_draws': len(compared), 'requested_selected_draws': len(draw_ids),
                'reused_committed_budget_fits': reused_fits}, ensure_ascii=False), flush=True)
    summaries = {}
    for budget in budgets:
        summary = summarize_paired_bootstrap_draws(working_originals, results[budget], planned_draws=500,
            full_point=full_point(manifests['point'], task, split, budget))
        summaries[str(budget)] = dict(summary, requested_annotation_budget=budget,
            valid_unique_cached_annotations=len(annotations[budget]),
            computation='fresh_refit_DM_and_target_then_DMplus' if refit_dm else 'fresh_DMplus_using_saved_DM_and_target',
            cached_draw_numeric_match_absolute_tolerance=TOLERANCE)
    del dataset, populations
    gc.collect()
    return summaries


def execute(args):
    root = Path(args.package_root).resolve()
    index = load(inside(root, args.index))
    if (index['schema_version'] != VERSION or index['seed'] != SEED
            or index['planned_draws'] != 500 or tuple(index['budgets']) != BUDGETS):
        raise ValueError('Unsupported selected-baseline index/protocol')
    for relative, digest in index['source_code_sha256'].items():
        verify(inside(root, relative), digest)
    actual_dependencies = {name: importlib.metadata.version(name) for name in index['dependencies']}
    if actual_dependencies != index['dependencies']:
        raise ValueError('Install the pinned numerical dependencies before replay')
    sys.path.insert(0, str(inside(root, 'src')))
    for name, module in list(sys.modules.items()):
        if name == 'april_repro' or name.startswith('april_repro.'):
            raise ValueError('Run in a fresh Python process; original modules are already imported')
    selected = list(index['cases']) if args.case == 'all' else [args.case]
    if any(case not in index['cases'] for case in selected):
        raise ValueError('Unknown selected case')
    budgets = numbers(args.budgets, BUDGETS) if args.budgets else list(BUDGETS if args.mode == 'cached' else (500,))
    if args.mode == 'cached' and (args.refit_dm or args.full500 or args.draws is not None or args.resume):
        raise ValueError('Draw/refit options apply only to fresh mode')
    if args.full500 and args.draws is not None:
        raise ValueError('--full500 and --draws are mutually exclusive')
    draw_ids = list(range(500)) if args.full500 else numbers(args.draws or '0', range(500))
    if args.mode == 'fresh' and len(draw_ids) == 500 and not args.full500:
        raise ValueError('A full 500-draw fresh rerun requires --full500')
    if args.resume and not args.output:
        raise ValueError('--resume requires the existing --output directory')
    output = Path(args.output).resolve() if args.output else root / 'results' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    if output == root or output.is_relative_to(root / 'data') or output.is_relative_to(root / 'src'):
        raise ValueError('Output must not overlap original inputs')
    if args.resume:
        if not output.is_dir():
            raise ValueError('Resume output directory does not exist')
    else:
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
    lock = (output / '.run.lock').open('a+b')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    run_plan = {'runner_version': VERSION, 'runner_sha256': sha(Path(__file__)),
        'cases_index_sha256': sha(inside(root, args.index)), 'mode': args.mode,
        'selected_cases': selected, 'selected_budgets': budgets,
        'draw_ids': draw_ids if args.mode == 'fresh' else None, 'full500': args.full500,
        'refit_dm': args.refit_dm, 'seed': SEED, 'planned_draws': 500,
        'dependencies': actual_dependencies,
        'runtime': {'python': platform.python_version(), 'machine': platform.machine()}}
    if args.resume:
        if load(output / 'run-plan.json') != run_plan:
            raise ValueError('Resume requires unchanged sources/code/case/budgets/draws/settings/runtime')
    else:
        save(output / 'run-plan.json', run_plan)
    plan_sha256 = sha(output / 'run-plan.json')
    report = {'runner_version': VERSION, 'status': 'running', 'mode': args.mode,
        'started_at_utc': datetime.now(timezone.utc).isoformat(), 'cases_index_sha256': sha(inside(root, args.index)),
        'runner_sha256': sha(Path(__file__)), 'runtime': {'python': platform.python_version(), 'machine': platform.machine()},
        'dependencies': actual_dependencies, 'selected_cases': selected, 'selected_budgets': budgets,
        'fresh_selected_draw_ids': draw_ids if args.mode == 'fresh' else None,
        'refit_original_DM_and_target_policy': bool(args.refit_dm), 'planned_bootstrap_draws_per_budget': 500,
        'resumed': args.resume, 'run_plan_sha256': plan_sha256,
        'interpretation': index['interpretation'], 'cases': {}, 'database_queried': False, 'llm_called': False,
        'full_paper_reproduction_complete': False, 'raw_provider_receipts_revalidated': False}
    try:
        for case_id in selected:
            case = index['cases'][case_id]
            print(json.dumps({'phase': 'verifying_sources', 'case': case_id}), flush=True)
            dirs, manifests, originals, cached, summaries = prepare_case(root, index, case, budgets)
            if args.mode == 'fresh':
                summaries = fresh_case(case_id, case, index, dirs, manifests, originals, cached,
                    budgets, draw_ids, args.refit_dm, output, args.resume, plan_sha256)
            report['cases'][case_id] = {'task': case['task'], 'split': case['split'], 'model_key': case['model_key'],
                'original_manifest_sha256': {name: case[name]['manifest_sha256'] for name in ('features','dm','point','dmplus')},
                'budgets': summaries}
            # Sources are read only, including original manifests with historical absolute paths.
            for name in ('features', 'dm', 'point', 'dmplus'):
                verify(dirs[name] / 'manifest.json', case[name]['manifest_sha256'])
        report['status'] = 'complete_cached_reconstruction' if args.mode == 'cached' else (
            'complete_selected_500_draw_rerun' if args.full500 else 'partial_fresh_check_not_full500')
        report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        summary_path = output / 'summary.json'
        if summary_path.exists():
            summary_path = output / ('summary-resume-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '.json')
        save(summary_path, report)
        print(json.dumps({'status': report['status'], 'output': str(output), 'cases': selected,
                          'budgets': budgets, 'primary_metrics_only_when_all500_complete': True}), flush=True)
        return 0
    except BaseException as error:
        report.update(status='failed', error_type=type(error).__name__, finished_at_utc=datetime.now(timezone.utc).isoformat())
        save(output / ('failed-summary-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '.json'), report)
        raise
    finally:
        lock.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-root', default=str(Path(__file__).resolve().parent))
    parser.add_argument('--index', default='cases.json')
    parser.add_argument('--mode', choices=['cached', 'fresh'], default='cached')
    parser.add_argument('--case', default='all', help='all, sodium_gender_deepseek, or potassium_dosage_gpt4omini')
    parser.add_argument('--budgets', help='Comma-separated request budgets from 0,100,200,300,400,500')
    parser.add_argument('--draws', help='Comma-separated original draw IDs 0..499; fresh default: 0')
    parser.add_argument('--full500', action='store_true', help='Explicitly rerun all 500 draws for each selected budget')
    parser.add_argument('--refit-dm', action='store_true', help='Also refit original DM and target policy with unchanged core')
    parser.add_argument('--resume', action='store_true', help='Resume an unchanged fresh run; repeat its exact settings and --output')
    parser.add_argument('--output', help='New output directory; never overwrite existing results')
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        return execute(args)
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'reason': str(error)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
