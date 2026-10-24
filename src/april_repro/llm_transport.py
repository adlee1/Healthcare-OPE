"""Single-attempt HTTPS transport for the five explicitly configured models.

No automatic retry, redirect, model replacement or credential persistence.
Patient requests require the actual provider's configured data-handling state.
This module is tested with injected synthetic transports, not live services.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException, IncompleteRead
import json
import math
import os
from urllib import error, request
from zoneinfo import ZoneInfo

from april_repro.llm_five_requests import MODEL_REGISTRY, validate_request
from april_repro.llm_predictions import parse_prediction_response
from april_repro.llm_receipts import normalize_receipt


MAX_RECEIPT_BYTES = 4 * 1024 * 1024
DATA_FLAGS = ('patient_data_authorized', 'zero_retention_verified',
              'no_training_verified', 'no_human_review_verified')


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _retry_after_seconds(headers, received_at):
    """Extract a numeric wait only; never persist arbitrary response headers."""
    value = headers.get('Retry-After') if headers is not None else None
    if not isinstance(value, str) or len(value) > 128:
        return None
    value = value.strip()
    if value.isascii() and value.isdecimal():
        return int(value)
    try:
        moment = parsedate_to_datetime(value)
        if moment.tzinfo is None:
            return None
        return max(0.0, (moment - received_at).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def _read_body(response, buffer):
    # Keep bytes already returned if a later read times out or is truncated.
    while len(buffer) <= MAX_RECEIPT_BYTES:
        remaining = MAX_RECEIPT_BYTES + 1 - len(buffer)
        chunk = response.read(min(65536, remaining))
        if not chunk:
            break
        buffer.extend(chunk[:remaining])


def preflight(record, provider_settings=None, *, environ=None):
    """Return only non-secret local readiness; this does not probe an account."""
    validate_request(record)
    transport = record['transport']
    settings = provider_settings or {}
    env = os.environ if environ is None else environ
    reasons = []
    if settings.get('endpoint') != transport['endpoint']:
        reasons.append('provider_endpoint_not_confirmed')
    reasons.extend(flag + '_not_confirmed' for flag in DATA_FLAGS if settings.get(flag) is not True)
    key = env.get(transport['api_key_env'])
    key_present = isinstance(key, str) and bool(key.strip())
    if not key_present:
        reasons.append('api_key_missing')
    # A known shutdown is an execution condition, never a reason to replace a model.
    spec = MODEL_REGISTRY[record['metadata']['model_key']]
    shutdown = spec.get('shutdown_date')
    today = datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    if shutdown and today >= shutdown:
        reasons.append('announced_model_shutdown_reached')
    return {'model_key': record['metadata']['model_key'], 'provider': transport['provider'],
            'endpoint': transport['endpoint'], 'api_key_present': key_present,
            'ready': not reasons, 'reasons': reasons, 'account_access_verified': False,
            'external_calls': 0}


def execute_once(record, provider_settings, *, environ=None, timeout=120, opener=None):
    """Send one validated request after readiness checks; return receipt and raw bytes.

    Transport failures remain failed predictions. A timeout has unknown remote
    completion/billing status; this function never retries it automatically.
    """
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 300:
        raise ValueError('Timeout must be positive and at most 300 seconds')
    env = os.environ if environ is None else environ
    check = preflight(record, provider_settings, environ=env)
    if not check['ready']:
        raise ValueError('Provider is not ready: ' + ','.join(check['reasons']))
    key = env[record['transport']['api_key_env']]
    if '\n' in key or '\r' in key:
        raise ValueError('Invalid API key encoding')
    encoded = json.dumps(record['payload'], ensure_ascii=False, allow_nan=False,
                         separators=(',', ':')).encode('utf-8')
    http_request = request.Request(record['transport']['endpoint'], data=encoded,
                                   headers={'Authorization': 'Bearer ' + key,
                                            'Content-Type': 'application/json'}, method='POST')
    send = opener or request.build_opener(_NoRedirect()).open
    buffer = bytearray()
    status = None
    failure = None
    headers = None
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        try:
            with send(http_request, timeout=timeout) as response:
                status = response.status
                headers = getattr(response, 'headers', None)
                _read_body(response, buffer)
        except error.HTTPError as exc:
            status = exc.code
            headers = exc.headers
            try:
                _read_body(exc, buffer)
            finally:
                exc.close()
    except IncompleteRead as exc:
        buffer.extend(exc.partial[:MAX_RECEIPT_BYTES + 1 - len(buffer)])
        failure = 'network_error_remote_completion_unknown'
    except (error.URLError, TimeoutError, OSError, HTTPException):
        failure = 'network_error_remote_completion_unknown'
    received_moment = datetime.now(timezone.utc)
    received_at = received_moment.isoformat()
    raw = bytes(buffer)
    complete = failure is None and len(raw) <= MAX_RECEIPT_BYTES
    receipt = normalize_receipt(record, raw, http_status=status)
    if failure:
        receipt['status'] = 'invalid'
        receipt['reason'] = failure
        receipt['failure_layer'] = 'receipt'
        # A parseable prefix does not become a valid prediction after a read failure.
        receipt['parsed_prediction'] = parse_prediction_response(None, record['metadata']['task']).to_dict()
    receipt.update(transport_attempts=1, automatic_retries=0,
                   started_at_utc=started_at, received_at_utc=received_at,
                   raw_response_complete=complete, remote_completion_unknown=bool(failure))
    receipt['retry_after_seconds'] = _retry_after_seconds(headers, received_moment)
    return receipt, raw
