"""Offline validation of OpenAI-compatible chat completion receipts.

The caller verifies the request ledger, stores/hashes the original response,
and handles transport. This module never calls a service, retries, repairs a
reply, or parses reasoning text as a lab prediction. The 4 MiB response bound
and strict single completed choice are implementation choices, not paper facts.
Only a separately supplied observed label enters the factual evaluation bridge.
"""
from __future__ import annotations

import json
import math

from april_repro.llm_predictions import parse_prediction_response


RECEIPT_VERSION = "chat-completion-receipt-v1"
MAX_RECEIPT_BYTES = 4 * 1024 * 1024


class _InvalidJSON(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidJSON("duplicate_json_key")
        result[key] = value
    return result


def _constant(_value):
    raise _InvalidJSON("nonfinite_json_constant")


def _body(response_body):
    if not isinstance(response_body, (str, bytes, dict)):
        raise _InvalidJSON("invalid_response_type")
    try:
        if isinstance(response_body, dict):
            response_body = json.dumps(response_body, ensure_ascii=False,
                                       allow_nan=False, separators=(",", ":"))
        if len(response_body) > MAX_RECEIPT_BYTES:
            raise _InvalidJSON("response_too_large")
        raw = (response_body.encode("utf-8")
               if isinstance(response_body, str) else response_body)
        if len(raw) > MAX_RECEIPT_BYTES:
            raise _InvalidJSON("response_too_large")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_constant)
        # Escaped lone surrogates and overflowing JSON numbers must not make
        # an accepted receipt impossible to persist as finite UTF-8 JSON.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except _InvalidJSON:
        raise
    except (UnicodeEncodeError, UnicodeDecodeError):
        raise _InvalidJSON("invalid_utf8") from None
    except RecursionError:
        raise _InvalidJSON("json_nesting_limit") from None
    except (TypeError, ValueError, OverflowError):
        raise _InvalidJSON("invalid_json") from None
    if not isinstance(value, dict):
        raise _InvalidJSON("top_level_not_object")
    return value


def _text(value, field):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("Missing or invalid request " + field)
    return value


def _request(record):
    if not isinstance(record, dict):
        raise ValueError("Request must be a dictionary")
    metadata, payload = record.get("metadata"), record.get("payload")
    if not isinstance(metadata, dict) or not isinstance(payload, dict):
        raise ValueError("Request lacks metadata or payload")
    task = _text(metadata.get("task"), "task")
    invalid_prediction = parse_prediction_response(None, task).to_dict()
    requested = _text(payload.get("model"), "model")
    snapshot = _text(metadata.get("model_snapshot"), "model_snapshot")
    if snapshot != requested:
        raise ValueError("Request metadata and payload models disagree")
    transport = record.get("transport", {})
    if not isinstance(transport, dict):
        raise ValueError("Invalid request transport")
    accepted = transport.get("accepted_response_models", [requested])
    if (not isinstance(accepted, list) or not accepted
            or any(not isinstance(item, str) or not item or item != item.strip()
                   for item in accepted) or len(set(accepted)) != len(accepted)):
        raise ValueError("Accepted response models must be an explicit nonempty unique list")
    return {
        "request_id": _text(record.get("request_id"), "request_id"),
        "prompt_sha256": _text(record.get("prompt_sha256"), "prompt_sha256"),
        "task": task, "model_key": _text(metadata.get("model_key"), "model_key"),
        "requested_model": requested,
    }, accepted, invalid_prediction


def _numeric_usage(value):
    """Keep numeric token accounting, never arbitrary response or credential text."""
    if not isinstance(value, dict):
        return None
    result = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if type(item) is int or type(item) is float and math.isfinite(item):
            result[key] = item
        elif isinstance(item, dict):
            nested = _numeric_usage(item)
            if nested:
                result[key] = nested
    return result


def normalize_receipt(record, response_body, *, http_status=200):
    """Validate one receipt and parse only its completed assistant content.

    Invalid response envelopes are data (status='invalid'), not exceptions.
    Malformed request configuration raises ValueError. Model matching is exact:
    the requested snapshot, or only transport.accepted_response_models if set.
    A dict body cannot establish whether its original JSON had duplicate keys;
    use original bytes for that check. No raw body or reasoning text is retained.
    """
    identity, accepted, invalid_prediction = _request(record)
    if http_status is not None and (type(http_status) is not int or not 100 <= http_status <= 599):
        raise ValueError("HTTP status must be an integer status code or None")
    result = {
        "receipt_version": RECEIPT_VERSION, **identity,
        "http_status": http_status, "response_model": None,
        "finish_reason": None, "usage": None,
        "status": "invalid", "failure_layer": "receipt", "reason": "",
        "parsed_prediction": invalid_prediction,
    }

    def invalid(reason):
        result["reason"] = reason
        return result

    if http_status is None:
        return invalid("no_http_response")
    try:
        body = _body(response_body)
    except _InvalidJSON as exc:
        return invalid("http_status_not_200" if http_status != 200 else str(exc))
    model = body.get("model")
    result["response_model"] = model if isinstance(model, str) else None
    result["usage"] = _numeric_usage(body.get("usage"))
    choices = body.get("choices")
    if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict):
        finish = choices[0].get("finish_reason")
        result["finish_reason"] = finish if isinstance(finish, str) else None
    if http_status != 200:
        return invalid("http_status_not_200")
    if body.get("error") is not None:
        return invalid("response_error")
    if not isinstance(model, str) or not model or model != model.strip():
        return invalid("missing_or_invalid_response_model")
    if model not in accepted:
        return invalid("response_model_mismatch")
    if not isinstance(choices, list) or len(choices) != 1:
        return invalid("expected_single_choice")
    choice = choices[0]
    if not isinstance(choice, dict):
        return invalid("invalid_choice")
    finish = choice.get("finish_reason")
    if type(choice.get("index")) is not int or choice["index"] != 0:
        return invalid("choice_index_not_zero")
    if choice.get("error") is not None:
        return invalid("response_error")
    if finish != "stop":
        return invalid("finish_reason_not_stop")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return invalid("expected_assistant_message")
    if message.get("error") is not None:
        return invalid("response_error")
    if message.get("refusal") not in (None, ""):
        return invalid("assistant_refusal")
    if message.get("tool_calls") not in (None, []) or message.get("function_call") is not None:
        return invalid("assistant_tool_call")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return invalid("missing_or_empty_content")
    parsed = parse_prediction_response(content, identity["task"]).to_dict()
    result["parsed_prediction"] = parsed
    result["status"] = parsed["status"]
    result["failure_layer"] = "prediction" if parsed["status"] == "invalid" else None
    result["reason"] = parsed["reason"]
    return result


def factual_record_from_receipt(record, receipt, *, observed_lab_value):
    """Bridge a factual receipt to evaluate_factual_predictions without dropping failures.

    Receipt-level errors use the parser's existing invalid-response sentinel;
    their specific causes remain in receipt_failure_reason, outside its reason
    vocabulary. The evaluator validates observed labels and parsed predictions.
    """
    identity, _, invalid_prediction = _request(record)
    if record["metadata"].get("mode") != "factual":
        raise ValueError("Only factual requests can enter factual evaluation")
    if (not isinstance(receipt, dict) or receipt.get("receipt_version") != RECEIPT_VERSION
            or any(receipt.get(key) != value for key, value in identity.items())):
        raise ValueError("Receipt and request identities disagree")
    status, layer = receipt.get("status"), receipt.get("failure_layer")
    if ((status == "valid" and (layer is not None or receipt.get("reason") != ""))
            or (status == "invalid" and (layer not in ("receipt", "prediction")
                                         or not isinstance(receipt.get("reason"), str)
                                         or not receipt["reason"]))
            or status not in ("valid", "invalid")):
        raise ValueError("Invalid normalized receipt status")
    prediction = invalid_prediction if layer == "receipt" else receipt.get("parsed_prediction")
    if not isinstance(prediction, dict) or prediction.get("status") != status:
        raise ValueError("Receipt and parsed prediction status disagree")
    return {
        "request_id": identity["request_id"],
        "event_id": _text(record["metadata"].get("event_id"), "event_id"),
        "mode": "factual", "model_key": identity["model_key"],
        "protocol_id": _text(record.get("protocol_id"), "protocol_id"),
        "prompt_hash": identity["prompt_sha256"],
        "observed_lab_value": observed_lab_value,
        "parsed_prediction": prediction,
        "receipt_status": status,
        "receipt_failure_reason": receipt["reason"] if layer == "receipt" else None,
    }
