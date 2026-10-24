"""Bounded transient retries without changing a prompt or selecting its answer.

The caller must persist an attempt before this module waits or issues another
POST. Completed refusals, truncations, and prediction parsing failures are
terminal. Repeated POSTs can be billed even when a prior response was lost.
"""
from __future__ import annotations

import json
import math
import random
import time

from april_repro.llm_transport import execute_once


MAX_RETRIES = 2
MAX_RETRY_DELAY_SECONDS = 60
RETRY_POLICY_VERSION = 'transient-transport-retries-v1'
_TERMINAL_ERROR_MARKERS = (
    'insufficient_quota', 'quota', 'billing', 'credit', 'balance', 'payment',
    'invalid_api_key', 'authentication', 'permission', 'model_not_found',
    'model not found', 'model does not exist', 'invalid_request',
    'invalid request', 'invalid_parameter', 'invalid parameter',
    'context_length', 'context length', 'account_disabled', 'account disabled',
    'no_access', '余额', '欠费', '额度不足', '认证失败', '无权限',
    'arrearage', 'access_denied', 'not_authorized', 'unsupported_model',
    'bad_request', 'invalid_api_key', 'invalid_param',
)


def _terminal_service_error(raw):
    """Classify only the service error envelope, never generated answer text."""
    try:
        envelope = json.loads(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return False
    if not isinstance(envelope, dict):
        return False
    failure = envelope.get('error')
    fields = (failure,) if isinstance(failure, str) else (
        tuple(failure.get(key) for key in ('code', 'type', 'message'))
        if isinstance(failure, dict) else ())
    text = ' '.join(value[:10000].casefold() for value in fields if isinstance(value, str))
    # Providers vary between snake_case, CamelCase and spaced error names.
    compact = ''.join(character for character in text if character.isalnum())
    return any(''.join(character for character in marker if character.isalnum()) in compact
               for marker in _TERMINAL_ERROR_MARKERS)


def retry_decision(receipt, raw, *, attempt_number, max_retries=2, uniform=None):
    """Return a sanitized decision; Retry-After is a minimum, never shortened."""
    if isinstance(max_retries, bool) or not isinstance(max_retries, int) or not 0 <= max_retries <= MAX_RETRIES:
        raise ValueError('max_retries must be an integer from 0 to 2')
    if isinstance(attempt_number, bool) or not isinstance(attempt_number, int) or not 1 <= attempt_number <= max_retries + 1:
        raise ValueError('Invalid attempt number')
    decision = {'retry': False, 'delay_seconds': 0.0, 'reason': None,
                'remote_completion_unknown': bool(receipt.get('remote_completion_unknown'))}
    status = receipt.get('http_status')
    if receipt.get('status') == 'valid':
        decision['reason'] = 'first_valid_response'
    elif _terminal_service_error(raw):
        decision['reason'] = 'nonretryable_service_error'
    elif isinstance(status, int) and 300 <= status < 500 and status not in (408, 409, 429):
        decision['reason'] = 'nonretryable_http_status'
    elif not (status in (408, 409, 429) or isinstance(status, int) and 500 <= status <= 599
              or receipt.get('reason') == 'network_error_remote_completion_unknown'):
        decision['reason'] = 'completed_or_nonretryable_failure'
    elif attempt_number >= max_retries + 1:
        decision['reason'] = 'retry_limit_reached'
    else:
        retry_after = receipt.get('retry_after_seconds')
        if isinstance(retry_after, bool) or not isinstance(retry_after, (int, float)) or not math.isfinite(retry_after) or retry_after < 0:
            retry_after = 0.0
        if retry_after > MAX_RETRY_DELAY_SECONDS:
            decision.update(reason='retry_after_exceeds_run_wait_limit',
                            retry_after_seconds=retry_after, deferred=True)
        else:
            # Equal-jitter exponential backoff: 1-2s, then 2-4s, bounded at 60s.
            choose = random.uniform if uniform is None else uniform
            ceiling = min(MAX_RETRY_DELAY_SECONDS, 2 ** attempt_number)
            delay = max(float(retry_after), float(choose(ceiling / 2, ceiling)))
            if not math.isfinite(delay) or not 0 <= delay <= MAX_RETRY_DELAY_SECONDS:
                raise ValueError('Invalid retry delay')
            decision.update(retry=True, delay_seconds=delay, reason='transient_failure')
    return decision


def execute_with_retries(record, provider_settings, *, before_attempt, after_attempt,
                         environ=None, timeout=120, max_retries=2,
                         send=None, sleeper=None, uniform=None):
    """Return one annotation result plus all attempt references.

    before_attempt(number) persists intent before POST; after_attempt(number,
    receipt, raw, decision) must persist raw + receipt and returns their private
    references. A persistence error stops the entire operation before retry.
    """
    if isinstance(max_retries, bool) or not isinstance(max_retries, int) or not 0 <= max_retries <= MAX_RETRIES:
        raise ValueError('max_retries must be an integer from 0 to 2')
    attempt_send = execute_once if send is None else send
    wait = time.sleep if sleeper is None else sleeper
    attempts = []
    for number in range(1, max_retries + 2):
        before_attempt(number)
        receipt, raw = attempt_send(record, provider_settings, environ=environ, timeout=timeout)
        decision = retry_decision(receipt, raw, attempt_number=number,
                                  max_retries=max_retries, uniform=uniform)
        references = after_attempt(number, receipt, raw, decision)
        attempts.append({'attempt_number': number, 'status': receipt['status'],
                         'reason': receipt['reason'], 'retry_decision': decision,
                         'files': references})
        if not decision['retry']:
            return {'request_id': record['request_id'], 'status': receipt['status'],
                    'reason': receipt['reason'], 'attempt_count': number,
                    'automatic_retries': number - 1, 'final_attempt_number': number,
                    'final_receipt': references['receipt'], 'attempts': attempts,
                    'stop_reason': decision['reason'],
                    'remote_completion_unknown': any(item['retry_decision']['remote_completion_unknown'] for item in attempts)}
        wait(decision['delay_seconds'])
    raise AssertionError('Retry loop must finish within its limit')
