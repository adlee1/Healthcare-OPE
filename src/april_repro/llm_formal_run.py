"""Durable, resumable execution of the explicitly approved formal annotation plan.

The plan/pilot are revalidated locally before network access. Unknown interrupted
attempts are held, never automatically posted again. Each model has one worker.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import threading

from april_repro import llm_formal_plan, llm_run_summary, llm_retries, llm_transport, llm_receipts
from april_repro.llm_five_requests import validate_request

RUN_VERSION = 'formal-main-execution-v1'
SCOPE = 'formal_main_annotation_run'


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _json(path):
    return json.loads(Path(path).read_bytes())


def _encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False) + '\n').encode()


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def private_write(path, raw, *, replace=False):
    """Persist bytes plus directory entry, with atomic replacement for status."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Private output cannot be a symlink')
    target = path.with_name('.' + path.name + '.' + secrets.token_hex(8)) if replace else path
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(target, path)
        _sync_directory(path.parent)
    except BaseException:
        # An incomplete non-atomic attempt file intentionally remains evidence.
        if replace and target.exists():
            target.unlink()
        raise


@dataclass(frozen=True)
class FormalPlan:
    directory: Path
    manifest: dict
    manifest_sha256: str
    requests: dict
    labels: dict
    reused: dict
    pilot_evidence: dict


def _check_bound(info):
    if _sha(info['path']) != info['sha256']:
        raise ValueError('Bound formal input changed')


def load_formal_plan(directory):
    """Verify immutable formal payloads, their inputs, and original pilot raw data."""
    directory = Path(directory).resolve()
    manifest = _json(directory / 'manifest.json')
    digest = _sha(directory / 'manifest.json')
    if (manifest.get('status') != 'complete' or manifest.get('scope') != llm_formal_plan.SCOPE
            or manifest.get('rule_version') != llm_formal_plan.RULE_VERSION
            or manifest.get('external_calls') != 0):
        raise ValueError('Expected complete offline formal plan')
    if manifest['code'] != llm_formal_plan._code_identity():
        raise ValueError('Formal planning code identity changed')
    for info in manifest['code'].values():
        _check_bound(info)
    config = manifest['config']
    actual_config = llm_formal_plan.load_config(config['path'],
        selection_config_path=config['selection_config']['path'],
        model_config_path=config['model_config']['path'])
    if actual_config != config:
        raise ValueError('Formal configuration changed')
    for item in manifest['inputs']:
        folder = Path(item['directory'])
        if _sha(folder / 'manifest.json') != item['manifest_sha256']:
            raise ValueError('Formal clinical input manifest changed')
        input_manifest = _json(folder / 'manifest.json')
        if input_manifest.get('outputs') != item['outputs']:
            raise ValueError('Formal clinical output bindings changed')
        for name, expected in item['outputs'].items():
            if Path(name).name != name or _sha(folder / name) != expected:
                raise ValueError('Formal clinical output changed')
    if set(manifest['outputs']) != {'requests.jsonl', 'factual-labels.jsonl'}:
        raise ValueError('Unexpected formal outputs')
    content = {}
    for name, expected in manifest['outputs'].items():
        if _sha(directory / name) != expected:
            raise ValueError('Formal output hash mismatch')
        content[name] = [json.loads(line) for line in (directory / name).read_bytes().splitlines()]
    requests, labels = {}, {}
    for row in content['requests.jsonl']:
        validate_request(row)
        rid, meta = row['request_id'], row['metadata']
        if rid in requests or meta['task'] not in manifest['tasks']:
            raise ValueError('Formal request identity is duplicated or unrelated')
        consumers = row.get('consumers')
        if not isinstance(consumers, list) or not consumers:
            raise ValueError('Formal consumers missing')
        seen = set()
        for consumer in consumers:
            if (consumer.get('split') not in llm_run_summary.SPLITS or consumer['split'] in seen
                    or consumer.get('mode') != meta['mode']
                    or consumer.get('fold') != ('validation' if meta['mode'] == 'factual' else 'train')
                    or type(consumer.get('rank')) is not int or not 1 <= consumer['rank'] <= 500):
                raise ValueError('Invalid formal consumer')
            seen.add(consumer['split'])
        requests[rid] = row
    if list(requests) != sorted(requests):
        raise ValueError('Formal request order differs from fixed sorted identity order')
    for row in content['factual-labels.jsonl']:
        rid, value = row['request_id'], row['post_lab_value']
        if rid not in requests or rid in labels or type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError('Invalid formal factual label')
        request = requests[rid]
        meta = request['metadata']
        expected = dict(request_id=rid, protocol_id=request['protocol_id'],
            prompt_sha256=request['prompt_sha256'], task=meta['task'], action=meta['action'],
            post_lab_value=value, input_manifest_sha256=meta['input_manifest_sha256'])
        if row != expected or meta['mode'] != 'factual':
            raise ValueError('Formal label identity mismatch')
        labels[rid] = value
    if set(labels) != {rid for rid, row in requests.items() if row['metadata']['mode'] == 'factual'}:
        raise ValueError('Formal factual label coverage mismatch')
    saved = manifest['pilot_reuse']
    pilot, evidence, _ = llm_formal_plan.verify_pilot(saved.get('directory'),
        [item['directory'] for item in saved.get('packets', [])])
    expected_evidence = {key: value for key, value in saved.items() if key not in
        ('matched_formal_request_ids', 'matched_formal_requests', 'formal_consumers_preserved')}
    if evidence != expected_evidence:
        raise ValueError('Formal pilot evidence changed')
    reused = {}
    for rid in sorted(set(requests) & set(pilot)):
        row, previous = requests[rid], pilot[rid]
        if ({k: v for k, v in row.items() if k != 'consumers'} !=
                {k: v for k, v in previous['request'].items() if k != 'consumers'}):
            raise ValueError('Pilot and formal payload differ')
        if rid in labels and previous['observed_lab'] != labels[rid]:
            raise ValueError('Pilot and formal labels differ')
        reused[rid] = {**previous['annotation'], 'consumers': row['consumers']}
    if (sorted(reused) != saved['matched_formal_request_ids'] or
            len(reused) != saved['matched_formal_requests'] or saved['formal_consumers_preserved'] is not True):
        raise ValueError('Formal verified reuse count changed')
    counts = manifest['summary']
    if (counts['unique_requests'] != len(requests) or counts['factual_label_rows'] != len(labels)
            or counts['verified_reusable_requests'] != len(reused)
            or counts['new_unique_requests'] != len(requests) - len(reused)
            or counts['request_consumers'] != sum(len(row['consumers']) for row in requests.values())):
        raise ValueError('Formal manifest counts mismatch')
    for model in config['model_config']['effective']['model_keys']:
        ids = [rid for rid, row in requests.items() if row['metadata']['model_key'] == model]
        actual = {'unique_requests': len(ids), 'verified_reusable': sum(rid in reused for rid in ids),
                  'new_unique_requests': sum(rid not in reused for rid in ids)}
        if any(counts['by_model'][model][key] != value for key, value in actual.items()):
            raise ValueError('Formal per-model counts mismatch')
    return FormalPlan(directory, manifest, digest, requests, labels, reused, evidence)


def source_hashes():
    paths = [Path(__file__), Path(llm_retries.__file__), Path(llm_transport.__file__),
             Path(llm_run_summary.__file__), Path(llm_receipts.__file__)]
    base = Path(llm_formal_plan.__file__).resolve().parents[2]
    for name in ('scripts/run_formal_llm_requests.py',
                 'src/april_repro/llm_credentials.py',
                 'src/april_repro/llm_formal_summary.py'):
        path = base / name
        if path.is_file():
            paths.append(path)
    return {str(path.resolve()): _sha(path) for path in paths}


def _stem(rid, number):
    return rid if number == 1 else rid + f'.attempt-{number:02d}'


def _result(rid, attempts):
    last = attempts[-1]
    return {'request_id': rid, 'status': last['status'], 'reason': last['reason'],
        'attempt_count': len(attempts), 'automatic_retries': len(attempts) - 1,
        'final_attempt_number': len(attempts), 'final_receipt': last['files']['receipt'],
        'attempts': attempts, 'stop_reason': last['retry_decision']['reason'],
        'remote_completion_unknown': any(row['retry_decision']['remote_completion_unknown'] for row in attempts)}


def verify_request_result(folder, record, *, result=None, max_retries=2):
    """Validate annotation against every durable raw response, including retry policy."""
    folder = Path(folder)
    result = _json(folder / (record['request_id'] + '.annotation.json')) if result is None else result
    final, receipts = llm_run_summary._annotation(folder, record, result)
    if len(receipts) > max_retries + 1:
        raise ValueError('Formal attempt budget exceeded')
    for number, (attempt, receipt) in enumerate(zip(result['attempts'], receipts), 1):
        raw = (folder / attempt['files']['raw']).read_bytes()
        saved = receipt['retry_decision']
        # Jitter is not regenerated: validate allowed interval and all other decisions.
        delay = saved.get('delay_seconds')
        check = llm_retries.retry_decision(receipt, raw, attempt_number=number,
            max_retries=max_retries, uniform=lambda lo, hi: lo)
        if check['retry']:
            upper = llm_retries.retry_decision(receipt, raw, attempt_number=number,
                max_retries=max_retries, uniform=lambda lo, hi: hi)['delay_seconds']
            if type(delay) not in (int, float) or not check['delay_seconds'] <= delay <= upper:
                raise ValueError('Saved retry delay outside policy')
            check['delay_seconds'] = delay
        if check != saved:
            raise ValueError('Saved retry decision differs from policy')
    return result, final, receipts


def inspect_request(folder, record, *, max_retries=2):
    """Read state without writing. Recover only a complete terminal receipt chain."""
    folder, rid = Path(folder), record['request_id']
    annotation = folder / (rid + '.annotation.json')
    if annotation.exists():
        result, final, receipts = verify_request_result(folder, record, max_retries=max_retries)
        return {'state': 'completed', 'result': result, 'final': final, 'receipts': receipts}
    artifacts = list(folder.glob(rid + '.*'))
    if not artifacts:
        return {'state': 'new'}
    if any(path.name.endswith('.held.json') for path in artifacts):
        return {'state': 'held', 'reason': 'previously_held_interrupted_attempt'}
    attempts = []
    try:
        for number in range(1, max_retries + 2):
            stem = _stem(rid, number)
            paths = {kind: folder / (stem + suffix) for kind, suffix in
                     (('started', '.started.json'), ('raw', '.raw'), ('receipt', '.receipt.json'))}
            if not all(path.is_file() and not path.is_symlink() for path in paths.values()):
                return {'state': 'held', 'reason': 'incomplete_interrupted_attempt'}
            receipt = _json(paths['receipt'])
            refs = {kind: path.name for kind, path in paths.items()}
            refs['receipt_sha256'] = _sha(paths['receipt'])
            attempts.append({'attempt_number': number, 'status': receipt['status'], 'reason': receipt['reason'],
                'retry_decision': receipt['retry_decision'], 'files': refs})
            if not receipt['retry_decision']['retry']:
                expected_files = {reference for attempt in attempts for key, reference in attempt['files'].items()
                                  if key != 'receipt_sha256'}
                if {path.name for path in artifacts} != expected_files:
                    return {'state': 'held', 'reason': 'unexpected_interrupted_attempt_files'}
                result, final, receipts = verify_request_result(folder, record,
                    result=_result(rid, attempts), max_retries=max_retries)
                return {'state': 'recoverable', 'result': result, 'final': final, 'receipts': receipts}
        return {'state': 'held', 'reason': 'unfinished_retry_chain'}
    except (ValueError, KeyError, TypeError, OSError):
        return {'state': 'held', 'reason': 'unverifiable_interrupted_attempt'}


@contextmanager
def exclusive_run_lock(output_directory, formal_manifest_sha256=None, *, lock_root=None):
    """Prevent parallel writers, including different outputs for the same plan."""
    output = Path(output_directory)
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    if output.is_symlink():
        raise ValueError('Output directory cannot be a symlink')
    lock_path = output / '.run.lock'
    locks = [lock_path]
    if formal_manifest_sha256 is not None:
        if len(formal_manifest_sha256) != 64 or any(c not in '0123456789abcdef' for c in formal_manifest_sha256):
            raise ValueError('Invalid formal manifest digest')
        shared = Path(lock_root) if lock_root is not None else output.parent
        shared.mkdir(mode=0o700, parents=True, exist_ok=True)
        locks.insert(0, shared / ('.formal-' + formal_manifest_sha256 + '.lock'))
    descriptors = []
    try:
        for path in locks:
            if path.is_symlink():
                raise ValueError('Lock cannot be a symlink')
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            descriptors.append(fd)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Formal annotation run is already active') from None
        if formal_manifest_sha256 is not None:
            owner = shared / ('.formal-' + formal_manifest_sha256 + '.owner.json')
            claim = {'formal_manifest_sha256': formal_manifest_sha256, 'output_directory': str(output.resolve())}
            if owner.exists():
                if _json(owner) != claim:
                    raise ValueError('Formal plan already belongs to a different output directory')
            else:
                private_write(owner, _encoded(claim))
        yield
    finally:
        for fd in reversed(descriptors):
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _provider_stop(result):
    return result['stop_reason'] in ('nonretryable_service_error', 'nonretryable_http_status')


def run_formal_plan(plan, output_directory, *, provider_settings, environ,
                    runtime_sha256, max_retries=2, timeout=120, send=None,
                    sleeper=None, workers=5, stop_event=None):
    """Execute immutable new requests; cache reuse and safe resume make no POSTs."""
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
        if plan_path.exists():
            if _json(plan_path) != binding:
                raise ValueError('Resume execution binding differs from original run')
        else:
            if any(output.glob('requests/*/*')) or (output / 'manifest.json').exists():
                raise ValueError('Unbound existing run artifacts')
            private_write(plan_path, _encoded(binding))
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
            if state['state'] == 'completed' and _provider_stop(state['result']):
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
                'recorded_attempt_count_includes_unresolved_started': True,
                'recorded_attempt_count_excludes_reused_pilot': True,
                'attempt_started_does_not_prove_remote_completion': True,
                'paper_experiment_complete': False}
        def publish():
            private_write(output / 'status.json', _encoded(aggregate()), replace=True)
        if (output / 'manifest.json').exists():
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
            private_write(output / 'manifest.json', _encoded(final), replace=True)
        return final
