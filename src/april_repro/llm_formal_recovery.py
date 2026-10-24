"""Explicitly recorded recovery after an acknowledged account credit interruption.

Completed quota failures remain failed observations. Only untouched request IDs
may be sent; the original run plan, transport, retry policy and payloads remain
unchanged. Every continuation binds its predecessor and extra execution source.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import threading

from april_repro import llm_formal_run as original
from april_repro import llm_retries, llm_transport
from april_repro.llm_formal_run import (
    RUN_VERSION, SCOPE, _sha, _json, _encoded, _sync_directory,
    private_write, exclusive_run_lock, inspect_request, source_hashes,
    _provider_stop, _stem,
)

RECOVERY_VERSION = 'formal-quota-recovery-v1'


def recovery_source_hashes():
    paths = [Path(__file__).resolve()]
    base = Path(original.__file__).resolve().parents[2]
    cli = base / 'scripts/resume_formal_llm_requests.py'
    if cli.is_file():
        paths.append(cli)
    return {str(path): _sha(path) for path in paths}


def _quota_evidence(output, plan, rid, *, max_retries):
    if rid not in plan.requests or rid in plan.reused:
        raise ValueError('Quota acknowledgement must be a new planned request')
    row = plan.requests[rid]
    folder = output / 'requests' / row['metadata']['model_key']
    state = inspect_request(folder, row, max_retries=max_retries)
    if state['state'] != 'completed':
        raise ValueError('Quota acknowledgement must have a complete verified annotation')
    result, final = state['result'], state['final']
    raw_path = folder / result['attempts'][-1]['files']['raw']
    try:
        body = json.loads(raw_path.read_bytes())
    except (ValueError, UnicodeError):
        raise ValueError('Quota acknowledgement requires an exact error envelope') from None
    error = body.get('error', {}) if isinstance(body, dict) else {}
    if (row['transport']['provider'] != 'openai' or final.get('http_status') != 429
            or result['stop_reason'] != 'nonretryable_service_error'
            or result['status'] == 'valid' or not isinstance(error, dict)
            or error.get('code') != 'credit_balance_exhausted'
            or error.get('type') != 'insufficient_quota'):
        raise ValueError('Acknowledged request is not the specified exhausted-credit stop')
    names = {rid + '.annotation.json'}
    for attempt in result['attempts']:
        names.update(value for key, value in attempt['files'].items() if key != 'receipt_sha256')
    return {'request_id': rid, 'model_key': row['metadata']['model_key'],
        'provider': 'openai', 'failed_request_will_be_resent': False,
        'files_sha256': {str((folder / name).relative_to(output)): _sha(folder / name)
                          for name in sorted(names)}}


def _verify_segment(output, segment_id, plan, visited):
    if segment_id in visited or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', segment_id):
        raise ValueError('Invalid or cyclic recovery segment')
    visited.add(segment_id)
    directory = output / 'continuations' / segment_id
    if directory.is_symlink() or (directory / 'plan.json').is_symlink():
        raise ValueError('Recovery segment cannot be a symlink')
    binding = _json(directory / 'plan.json')
    root = _json(output / 'plan.json')
    if (binding.get('recovery_version') != RECOVERY_VERSION
            or binding.get('recovery_id') != segment_id
            or binding.get('root_plan_sha256') != _sha(output / 'plan.json')
            or binding.get('formal_manifest_sha256') != plan.manifest_sha256
            or binding.get('original_source_sha256') != root['source_sha256']
            or root['source_sha256'] != source_hashes()
            or binding.get('recovery_source_sha256') != recovery_source_hashes()
            or binding.get('runtime_config_sha256') != root['runtime_config_sha256']
            or binding.get('max_retries') != root['max_retries']
            or binding.get('failed_quota_requests_resent') is not False):
        raise ValueError('Recovery execution binding changed')
    ids = binding.get('acknowledged_quota_stop_ids')
    if not isinstance(ids, list) or not ids or ids != sorted(set(ids)):
        raise ValueError('Invalid recovery acknowledgement list')
    evidence = [_quota_evidence(output, plan, rid, max_retries=root['max_retries']) for rid in ids]
    if evidence != binding.get('acknowledgements'):
        raise ValueError('Quota acknowledgement evidence changed')
    predecessor_path = directory / 'predecessor-manifest.json'
    if _sha(predecessor_path) != binding.get('predecessor_manifest_sha256'):
        raise ValueError('Recovery predecessor changed')
    predecessor = _json(predecessor_path)
    if (predecessor.get('status') not in ('complete', 'partial')
            or predecessor.get('plan_sha256') != binding['root_plan_sha256']
            or predecessor.get('formal_manifest_sha256') != plan.manifest_sha256
            or predecessor.get('source_sha256') != root['source_sha256']):
        raise ValueError('Recovery predecessor is not a closed original run')
    previous = predecessor.get('recovery_provenance')
    if previous is not None:
        expected = _verify_segment(output, previous['recovery_id'], plan, visited)
        if previous != expected:
            raise ValueError('Previous recovery chain differs')
        prior = _json(output / 'continuations' / previous['recovery_id'] / 'plan.json')
        if not set(prior['acknowledged_quota_stop_ids']) <= set(ids):
            raise ValueError('Recovery acknowledgement chain lost an earlier stop')
    if binding.get('previous_recovery_id') != (previous['recovery_id'] if previous else None):
        raise ValueError('Recovery predecessor identity differs')
    return {'recovery_version': RECOVERY_VERSION, 'recovery_id': segment_id,
        'segment_plan_sha256': _sha(directory / 'plan.json'),
        'root_plan_sha256': binding['root_plan_sha256'],
        'predecessor_manifest_sha256': binding['predecessor_manifest_sha256'],
        'recovery_source_sha256': binding['recovery_source_sha256'],
        'acknowledged_quota_stop_count': len(ids), 'failed_quota_requests_resent': False}


def verify_recovery_provenance(output_directory, plan=None):
    """Verify the closed continuation chain before collecting its annotations."""
    output = Path(output_directory).resolve()
    root = _json(output / 'plan.json')
    if plan is None:
        plan = original.load_formal_plan(root['formal_plan_directory'])
    final = _json(output / 'manifest.json')
    provenance = final.get('recovery_provenance')
    if not isinstance(provenance, dict):
        raise ValueError('Expected closed recovery provenance')
    expected = _verify_segment(output, provenance['recovery_id'], plan, set())
    if provenance != expected or final.get('plan_sha256') != expected['root_plan_sha256']:
        raise ValueError('Final recovery provenance differs')
    segment_manifest = output / 'continuations' / provenance['recovery_id'] / 'manifest.json'
    if _json(segment_manifest) != final:
        raise ValueError('Final recovery segment manifest differs')
    return expected


def _begin_segment(output, plan, recovery_id, acknowledged, binding):
    if not isinstance(recovery_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', recovery_id):
        raise ValueError('Invalid recovery ID')
    if (not isinstance(acknowledged, (list, tuple)) or not acknowledged
            or any(not isinstance(rid, str) for rid in acknowledged)
            or len(set(acknowledged)) != len(acknowledged)):
        raise ValueError('Expected explicit unique quota stop IDs')
    acknowledged = sorted(acknowledged)
    directory = output / 'continuations' / recovery_id
    path = directory / 'plan.json'
    if path.exists():
        provenance = _verify_segment(output, recovery_id, plan, set())
        if _json(path)['acknowledged_quota_stop_ids'] != acknowledged:
            raise ValueError('Resume acknowledgements differ')
        final_path = output / 'manifest.json'
        if final_path.exists():
            previous = _json(final_path).get('recovery_provenance')
            if previous is not None and previous['recovery_id'] != recovery_id:
                raise ValueError('Cannot resume an earlier recovery after a later segment')
        return provenance
    final_path = output / 'manifest.json'
    if not final_path.is_file() or final_path.is_symlink():
        raise ValueError('Recovery requires a durably closed predecessor run')
    predecessor = _json(final_path)
    if (predecessor.get('status') not in ('complete', 'partial')
            or predecessor.get('plan_sha256') != _sha(output / 'plan.json')
            or predecessor.get('source_sha256') != binding['source_sha256']):
        raise ValueError('Recovery predecessor is not closed or bound')
    previous = predecessor.get('recovery_provenance')
    if previous is not None:
        verify_recovery_provenance(output, plan)
    existing_segments = list((output / 'continuations').glob('*/plan.json'))
    if existing_segments and previous is None:
        raise ValueError('Existing recovery segment requires resume before a new segment')
    evidence = [_quota_evidence(output, plan, rid, max_retries=binding['max_retries'])
                for rid in acknowledged]
    segment = {'recovery_version': RECOVERY_VERSION, 'recovery_id': recovery_id,
        'formal_manifest_sha256': plan.manifest_sha256,
        'root_plan_sha256': _sha(output / 'plan.json'),
        'original_source_sha256': binding['source_sha256'],
        'recovery_source_sha256': recovery_source_hashes(),
        'runtime_config_sha256': binding['runtime_config_sha256'],
        'max_retries': binding['max_retries'],
        'predecessor_manifest_sha256': _sha(final_path),
        'previous_recovery_id': previous['recovery_id'] if previous else None,
        'acknowledged_quota_stop_ids': acknowledged, 'acknowledgements': evidence,
        'failed_quota_requests_resent': False,
        'created_at_utc': datetime.now(timezone.utc).isoformat()}
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    private_write(directory / 'predecessor-manifest.json', final_path.read_bytes())
    private_write(path, _encoded(segment))
    return _verify_segment(output, recovery_id, plan, set())


def run_recovery(plan, output_directory, *, provider_settings, environ,
                 runtime_sha256, recovery_id, acknowledged_quota_stop_ids,
                 max_retries=2, timeout=120, workers=5, stop_event=None,
                 send=None, sleeper=None):
    """Resume untouched requests after exactly acknowledged exhausted-credit errors."""
    if type(max_retries) is not int or not 0 <= max_retries <= 2:
        raise ValueError('Formal retry limit must be from zero to two')
    if type(workers) is not int or not 1 <= workers <= 5:
        raise ValueError('Formal workers must be from one to five')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300:
        raise ValueError('Invalid formal request timeout')
    output = Path(output_directory).resolve()
    stop_event = threading.Event() if stop_event is None else stop_event
    sender = llm_transport.execute_once if send is None else send
    with exclusive_run_lock(output, plan.manifest_sha256,
                            lock_root=plan.directory.parent.parent / 'llm-formal-runs'):
        ids = sorted(plan.requests)
        new_ids = [rid for rid in ids if rid not in plan.reused]
        model_keys = sorted({row['metadata']['model_key'] for row in plan.requests.values()},
                            key=lambda value: (value != 'o3-mini', value))
        binding = {'run_version': RUN_VERSION, 'scope': SCOPE,
            'formal_plan_directory': str(plan.directory), 'formal_manifest_sha256': plan.manifest_sha256,
            'request_ids': ids, 'new_request_ids': new_ids, 'reused_request_ids': sorted(plan.reused),
            'max_retries': max_retries, 'timeout_seconds': timeout, 'workers': workers,
            'runtime_config_sha256': runtime_sha256, 'source_sha256': source_hashes(),
            'retry_policy_version': llm_retries.RETRY_POLICY_VERSION,
            'fixed_request_order': 'ascending_request_id_within_model',
            'paper_experiment_complete': False}
        plan_path = output / 'plan.json'
        if not plan_path.is_file() or _json(plan_path) != binding:
            raise ValueError('Recovery binding differs from original run')
        provenance = _begin_segment(output, plan, recovery_id, acknowledged_quota_stop_ids, binding)
        acknowledged = set(acknowledged_quota_stop_ids)
        cache = b''.join(_encoded(plan.reused[rid]) for rid in sorted(plan.reused))
        cache_path = output / 'reused-annotations.jsonl'
        if cache_path.exists():
            if cache_path.read_bytes() != cache:
                raise ValueError('Run reuse cache differs from revalidated original pilot')
        else:
            private_write(cache_path, cache)
        states, model_status = {}, {model: {'state': 'pending', 'stop_reason': None} for model in model_keys}
        counts_lock = threading.Lock()
        (output / 'requests').mkdir(mode=0o700, exist_ok=True)
        model_ids = {model: [rid for rid in ids if plan.requests[rid]['metadata']['model_key'] == model]
                     for model in model_keys}
        model_new_ids = {model: [rid for rid in model_ids[model] if rid not in plan.reused] for model in model_keys}
        existing_ids = set()
        for model in model_keys:
            folder = output / 'requests' / model
            folder.mkdir(mode=0o700, exist_ok=True)
            existing_ids.update(path.name.split('.')[0] for path in folder.iterdir())
        # Reconstruct from durable data before any API, not from an optimistic status file.
        for rid in new_ids:
            row = plan.requests[rid]
            folder = output / 'requests' / row['metadata']['model_key']
            state = inspect_request(folder, row, max_retries=max_retries) if rid in existing_ids else {'state': 'new'}
            if state['state'] == 'recoverable':
                private_write(folder / (rid + '.annotation.json'), _encoded(state['result']))
                state['state'] = 'completed'
            if state['state'] == 'held' and not (folder / (rid + '.held.json')).exists():
                private_write(folder / (rid + '.held.json'), _encoded({'request_id': rid,
                    'status': 'held', 'reason': state['reason'], 'automatic_resend': False}))
            states[rid] = state
            if state['state'] == 'completed' and _provider_stop(state['result']) and rid not in acknowledged:
                model_status[row['metadata']['model_key']].update(state='stopped', stop_reason=state['result']['stop_reason'])
        started_count = Counter()
        for model in model_keys:
            folder = output / 'requests' / model
            known = set(model_new_ids[model])
            for path in folder.glob('*.started.json'):
                if path.name.split('.')[0] not in known:
                    raise ValueError('Unrelated started request in formal output')
                started_count[model] += 1
        model_counts = {}
        for model in model_keys:
            selected, new = model_ids[model], model_new_ids[model]
            completed = [states[rid]['result'] for rid in new if states[rid]['state'] == 'completed']
            reused = len(selected) - len(new)
            held = sum(states[rid]['state'] == 'held' for rid in new)
            model_counts[model] = {'unique_requests': len(selected), 'reused_annotations': reused,
                'new_completed_annotations': len(completed), 'completed_annotations': len(completed) + reused,
                'valid_predictions': reused + sum(row['status'] == 'valid' for row in completed),
                'invalid_predictions': sum(row['status'] != 'valid' for row in completed),
                'held_requests': held, 'pending_requests': len(new) - len(completed) - held,
                'automatic_retries': sum(row['automatic_retries'] for row in completed)}
        def aggregate(status='active'):
            by_model = {model: {**model_counts[model], 'recorded_attempt_count': started_count[model],
                                **model_status[model]} for model in model_keys}
            total = {key: sum(row[key] for row in by_model.values()) for key in (
                'unique_requests', 'reused_annotations', 'new_completed_annotations', 'completed_annotations',
                'valid_predictions', 'invalid_predictions', 'held_requests', 'pending_requests',
                'recorded_attempt_count', 'automatic_retries')}
            return {'run_version': RUN_VERSION, 'scope': SCOPE, 'status': status,
                'updated_at_utc': datetime.now(timezone.utc).isoformat(),
                'formal_manifest_sha256': plan.manifest_sha256, 'by_model': by_model, **total,
                'recovery_provenance': provenance,
                'recorded_attempt_count_includes_unresolved_started': True,
                'recorded_attempt_count_excludes_reused_pilot': True,
                'attempt_started_does_not_prove_remote_completion': True,
                'paper_experiment_complete': False}
        def publish():
            private_write(output / 'status.json', _encoded(aggregate()), replace=True)
        if (output / 'manifest.json').exists():
            closed = _json(output / 'manifest.json')
            reconstructed = aggregate()
            count_keys = ('unique_requests', 'reused_annotations', 'new_completed_annotations',
                'completed_annotations', 'valid_predictions', 'invalid_predictions', 'held_requests',
                'pending_requests', 'recorded_attempt_count', 'automatic_retries')
            if (any(closed.get(key) != reconstructed[key] for key in count_keys)
                    or set(closed.get('by_model', {})) != set(reconstructed['by_model'])
                    or any(closed['by_model'][model].get(key) != reconstructed['by_model'][model][key]
                           for model in model_keys for key in count_keys)):
                raise ValueError('Closed predecessor counts differ from durable raw reconstruction')
            previous = output / ('manifest.previous-' + secrets.token_hex(8) + '.json')
            os.replace(output / 'manifest.json', previous)
            _sync_directory(output)
        with counts_lock:
            publish()
        def worker(model):
            selected = model_new_ids[model]
            if model_status[model]['state'] == 'stopped':
                return
            with counts_lock:
                model_status[model]['state'] = 'active'
                publish()
            for rid in selected:
                if stop_event.is_set():
                    with counts_lock:
                        model_status[model].update(state='stopped', stop_reason='stop_requested')
                        publish()
                    return
                if states[rid]['state'] != 'new':
                    continue
                row = plan.requests[rid]
                provider = provider_settings.get(row['transport']['provider'], {})
                readiness = llm_transport.preflight(row, provider, environ=environ)
                if not readiness['ready']:
                    with counts_lock:
                        model_status[model].update(state='stopped', stop_reason='local_preflight_failed')
                        publish()
                    return
                folder = output / 'requests' / model
                def before_attempt(number):
                    private_write(folder / (_stem(rid, number) + '.started.json'), _encoded({
                        'request_id': rid, 'status': 'attempt_started', 'attempt_number': number,
                        'started_at_utc': datetime.now(timezone.utc).isoformat()}))
                    with counts_lock:
                        started_count[model] += 1
                        publish()
                def after_attempt(number, receipt, raw, decision):
                    stem = _stem(rid, number)
                    raw_name, receipt_name = stem + '.raw', stem + '.receipt.json'
                    private_write(folder / raw_name, raw)
                    receipt = {**receipt, 'raw_response_sha256': hashlib.sha256(raw).hexdigest(),
                               'attempt_number': number, 'retry_decision': decision}
                    private_write(folder / receipt_name, _encoded(receipt))
                    return {'started': stem + '.started.json', 'raw': raw_name, 'receipt': receipt_name,
                            'receipt_sha256': _sha(folder / receipt_name)}
                try:
                    result = llm_retries.execute_with_retries(row, provider, environ=environ, timeout=timeout,
                        max_retries=max_retries, before_attempt=before_attempt, after_attempt=after_attempt,
                        send=sender, sleeper=sleeper)
                    private_write(folder / (rid + '.annotation.json'), _encoded(result))
                    with counts_lock:
                        states[rid] = {'state': 'completed', 'result': result}
                        model_counts[model]['new_completed_annotations'] += 1
                        model_counts[model]['completed_annotations'] += 1
                        model_counts[model]['pending_requests'] -= 1
                        model_counts[model]['valid_predictions' if result['status'] == 'valid' else 'invalid_predictions'] += 1
                        model_counts[model]['automatic_retries'] += result['automatic_retries']
                        if _provider_stop(result):
                            model_status[model].update(state='stopped', stop_reason=result['stop_reason'])
                        publish()
                    if _provider_stop(result):
                        return
                except Exception:
                    # No exception text, payload, URL, response or key enters public status.
                    with counts_lock:
                        if states[rid]['state'] == 'new':
                            model_counts[model]['held_requests'] += 1
                            model_counts[model]['pending_requests'] -= 1
                            states[rid] = {'state': 'held', 'reason': 'worker_interrupted_attempt'}
                        model_status[model].update(state='stopped', stop_reason='local_worker_error')
                        try:
                            path = folder / (rid + '.held.json')
                            if not path.exists():
                                private_write(path, _encoded({'request_id': rid, 'status': 'held',
                                    'reason': 'worker_interrupted_attempt', 'automatic_resend': False}))
                            publish()
                        except OSError:
                            pass
                    return
            with counts_lock:
                model_status[model]['state'] = 'finished'
                publish()
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='formal-llm') as pool:
            futures = [pool.submit(worker, model) for model in model_keys]
            for future in futures:
                future.result()
        with counts_lock:
            final = aggregate()
            final['status'] = 'complete' if not final['held_requests'] and not final['pending_requests'] else 'partial'
            final['source_sha256'] = binding['source_sha256']
            final['plan_sha256'] = _sha(plan_path)
            final['reused_annotations_sha256'] = _sha(cache_path)
            private_write(output / 'status.json', _encoded(final), replace=True)
            private_write(output / 'continuations' / recovery_id / 'manifest.json', _encoded(final), replace=True)
            private_write(output / 'manifest.json', _encoded(final), replace=True)
        return final
