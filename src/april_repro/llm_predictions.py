"""Strict, offline LLM lab-response parsing and factual-only evaluation.

No model calls, retries, repair, prose extraction, or raw-response rewriting.
The caller preserves and hashes raw replies in private storage. Invalid replies
remain in coverage denominators; F1 and lab errors use valid predictions only.
Observed labels belong to this evaluator, never to the prompt constructor.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
from numbers import Real
import re

from april_repro.metrics import rmse, weighted_f1
from april_repro.rewards import F1_BOUNDARIES, PAPER_REWARD_SIGMA, bin_lab_value, reward_from_lab


PARSER_VERSION = "strict-lab-response-v1"
EVALUATION_VERSION = "factual-prediction-evaluation-v1"
MAX_RESPONSE_BYTES = 1024 * 1024
NORMALIZATIONS = {"removed_complete_json_code_fence"}
FAILURE_REASONS = {
    "invalid_response_type", "response_too_large", "invalid_utf8",
    "json_fence_not_allowed", "malformed_json_fence", "invalid_json",
    "json_nesting_limit", "duplicate_json_key", "nonfinite_json_constant",
    "top_level_not_object", "unexpected_json_keys", "prediction_not_json_number",
    "prediction_not_finite", "prediction_not_positive", "justification_not_nonempty_string",
}
PARSED_FIELDS = {"parser_version", "task", "status", "reason", "normalizations",
                 "predicted_lab_value", "justification", "reward", "reward_sigma", "f1_class"}


@dataclass(frozen=True, repr=False)
class ParsedPrediction:
    task: str
    status: str
    reason: str
    normalizations: tuple[str, ...] = ()
    predicted_lab_value: float | None = None
    justification: str | None = None
    reward: float | None = None
    f1_class: int | None = None

    def to_dict(self):
        return {"parser_version": PARSER_VERSION, "task": self.task,
                "status": self.status, "reason": self.reason,
                "normalizations": list(self.normalizations),
                "predicted_lab_value": self.predicted_lab_value, "justification": self.justification,
                "reward": self.reward, "reward_sigma": PAPER_REWARD_SIGMA, "f1_class": self.f1_class}


class _RejectedJSON(ValueError):
    pass


def _task(task):
    if not isinstance(task, str) or task not in F1_BOUNDARIES:
        raise ValueError("Unknown electrolyte prediction task")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _RejectedJSON("duplicate_json_key")
        result[key] = value
    return result


def _constant(_value):
    raise _RejectedJSON("nonfinite_json_constant")


def parse_prediction_response(raw_response, task, *, allow_json_fence=True):
    """Parse exactly the two paper response keys, returning explicit invalids."""
    _task(task)
    if type(allow_json_fence) is not bool:
        raise ValueError("allow_json_fence must be a boolean")
    normalizations = ()

    def invalid(reason):
        return ParsedPrediction(task, "invalid", reason, normalizations)

    if not isinstance(raw_response, (str, bytes)):
        return invalid("invalid_response_type")
    if len(raw_response) > MAX_RESPONSE_BYTES:
        return invalid("response_too_large")
    try:
        raw = raw_response.encode("utf-8") if isinstance(raw_response, str) else raw_response
        if len(raw) > MAX_RESPONSE_BYTES:
            return invalid("response_too_large")
        text = raw.decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return invalid("invalid_utf8")
    body = text.strip(" \t\r\n")
    if body.startswith("```"):
        if not allow_json_fence:
            return invalid("json_fence_not_allowed")
        match = re.fullmatch(r"```(?:json)?[ \t]*\r?\n([\s\S]*)\r?\n```", body)
        if match is None:
            return invalid("malformed_json_fence")
        text = match.group(1)
        normalizations = ("removed_complete_json_code_fence",)
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except _RejectedJSON as exc:
        return invalid(str(exc))
    except RecursionError:
        return invalid("json_nesting_limit")
    except (json.JSONDecodeError, ValueError):
        return invalid("invalid_json")
    if not isinstance(value, dict):
        return invalid("top_level_not_object")
    if set(value) != {"predicted_lab_value", "justification"}:
        return invalid("unexpected_json_keys")
    predicted = value["predicted_lab_value"]
    if type(predicted) not in (int, float):
        return invalid("prediction_not_json_number")
    try:
        predicted = float(predicted)
    except (ValueError, OverflowError):
        return invalid("prediction_not_finite")
    if not math.isfinite(predicted):
        return invalid("prediction_not_finite")
    if predicted <= 0:
        return invalid("prediction_not_positive")
    justification = value["justification"]
    if not isinstance(justification, str) or not justification.strip():
        return invalid("justification_not_nonempty_string")
    # JSON escapes can decode to lone surrogates despite valid UTF-8 input.
    # Reject them before a valid result can fail during private UTF-8 storage.
    try:
        justification.encode("utf-8")
    except UnicodeEncodeError:
        return invalid("invalid_utf8")
    return ParsedPrediction(task, "valid", "", normalizations, predicted, justification,
                            reward_from_lab(predicted, task), bin_lab_value(predicted, task))


def _nonempty(value, label):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError("Missing or invalid " + label)
    return value


def _observed(value):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("Observed lab must be a finite positive number")
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise ValueError("Observed lab must be a finite positive number") from None
    if not math.isfinite(result) or result <= 0:
        raise ValueError("Observed lab must be a finite positive number")
    return result


def _validated_prediction(prediction, task):
    value = prediction.to_dict() if isinstance(prediction, ParsedPrediction) else prediction
    if not isinstance(value, dict) or set(value) != PARSED_FIELDS:
        raise ValueError("Invalid parsed prediction schema")
    if (value["parser_version"] != PARSER_VERSION or value["task"] != task
            or type(value["reward_sigma"]) not in (int, float) or value["reward_sigma"] != PAPER_REWARD_SIGMA):
        raise ValueError("Parsed prediction task or protocol mismatch")
    normalizations = value["normalizations"]
    if (not isinstance(normalizations, (list, tuple)) or len(normalizations) > 1
            or any(not isinstance(item, str) or item not in NORMALIZATIONS for item in normalizations)):
        raise ValueError("Unknown prediction normalization")
    if value["status"] == "invalid":
        if (not isinstance(value["reason"], str) or value["reason"] not in FAILURE_REASONS
                or any(value[field] is not None for field in ("predicted_lab_value", "justification", "reward", "f1_class"))):
            raise ValueError("Invalid predictions must retain null values and a declared reason")
        return value
    if value["status"] != "valid" or value["reason"] != "":
        raise ValueError("Unknown parsed prediction status")
    predicted = value["predicted_lab_value"]
    if type(predicted) not in (int, float):
        raise ValueError("Parsed predicted lab must remain a JSON number")
    predicted = _observed(predicted)
    if not isinstance(value["justification"], str) or not value["justification"].strip():
        raise ValueError("Parsed prediction lacks its justification")
    try:
        value["justification"].encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("Parsed prediction justification is not valid UTF-8") from None
    if (type(value["reward"]) not in (int, float) or value["reward"] != reward_from_lab(predicted, task)
            or type(value["f1_class"]) is not int or value["f1_class"] != bin_lab_value(predicted, task)):
        raise ValueError("Parsed reward or F1 class differs from the declared lab mapping")
    return value


def evaluate_factual_predictions(task, records):
    """Evaluate one model/protocol batch; individual rendered prompt hashes vary.

    Each record requires request_id, event_id, mode='factual', model_key,
    protocol_id, prompt_hash, observed_lab_value, and parsed_prediction.
    Duplicate requests/events are rejected, including repeated invalid replies.
    This endpoint does not pool models or count counterfactual annotations.
    Callers must supply failed/missing responses as invalid records rather than
    omitting requests; the denominator is all supplied unique factual records.
    """
    _task(task)
    seen_requests, seen_events = set(), set()
    model_key = protocol_id = None
    failures, normalizations = Counter(), Counter()
    observed_all, truth_valid, predicted_valid = Counter(), [], []
    observed_labs, predicted_labs = [], []
    requested = 0
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Factual records must be dictionaries")
        request = _nonempty(record.get("request_id"), "request_id")
        event = _nonempty(record.get("event_id"), "event_id")
        if request in seen_requests or event in seen_events:
            raise ValueError("Duplicate factual request or event within a model batch")
        seen_requests.add(request)
        seen_events.add(event)
        if record.get("mode") != "factual":
            raise ValueError("Only factual predictions can enter factual evaluation")
        model = _nonempty(record.get("model_key"), "model_key")
        protocol = _nonempty(record.get("protocol_id"), "protocol_id")
        if requested and (model != model_key or protocol != protocol_id):
            raise ValueError("Factual evaluation requires one common model and protocol")
        model_key, protocol_id = model, protocol
        prompt_hash = record.get("prompt_hash")
        if not isinstance(prompt_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", prompt_hash):
            raise ValueError("Each factual record must retain a valid rendered prompt hash")
        observed = _observed(record.get("observed_lab_value"))
        actual_class = bin_lab_value(observed, task)
        prediction = _validated_prediction(record.get("parsed_prediction"), task)
        requested += 1
        observed_all[actual_class] += 1
        normalizations.update(prediction["normalizations"])
        if prediction["status"] == "invalid":
            failures[prediction["reason"]] += 1
            continue
        truth_valid.append(actual_class)
        predicted_valid.append(prediction["f1_class"])
        observed_labs.append(observed)
        predicted_labs.append(float(prediction["predicted_lab_value"]))
    valid = len(truth_valid)
    classes = len(F1_BOUNDARIES[task]) + 1
    support, predicted_support = Counter(truth_valid), Counter(predicted_valid)
    confusion = [[0] * classes for _ in range(classes)]
    for actual, predicted in zip(truth_valid, predicted_valid):
        confusion[actual][predicted] += 1
    report = {
        "evaluation_version": EVALUATION_VERSION, "parser_version": PARSER_VERSION,
        "task": task, "model_key": model_key, "protocol_id": protocol_id,
        "status": "complete" if valid else "not_estimable",
        "reason": "" if valid else "no_valid_predictions" if requested else "no_factual_requests",
        "requested_predictions": requested, "valid_predictions": valid,
        "invalid_predictions": requested - valid,
        "coverage": valid / requested if requested else None,
        "failure_reasons": dict(sorted(failures.items())),
        "normalization_counts": dict(sorted(normalizations.items())),
        "metric_population": "valid_predictions_only",
        "invalid_predictions_retained_in_coverage_denominator": True,
        "f1_boundaries": list(F1_BOUNDARIES[task]), "f1_threshold_values_go_to_right_bin": True,
        "observed_class_support_all_requested": [observed_all[i] for i in range(classes)],
        "observed_class_support_valid_predictions": [support[i] for i in range(classes)],
        "predicted_class_support_valid_predictions": [predicted_support[i] for i in range(classes)],
        "confusion_matrix_valid_predictions": confusion,
        "weighted_f1": None, "lab_mae": None, "lab_rmse": None,
        "lab_error_metrics_are_ope": False,
    }
    if valid:
        report["weighted_f1"] = weighted_f1(truth_valid, predicted_valid, num_classes=classes)
        report["lab_mae"] = math.fsum(abs(predicted - observed) / valid
                                      for observed, predicted in zip(observed_labs, predicted_labs))
        report["lab_rmse"] = rmse(predicted_labs, observed_labs)
        if not all(math.isfinite(report[key]) for key in ("weighted_f1", "lab_mae", "lab_rmse")):
            raise ValueError("Factual metrics exceeded finite numerical range")
    return report
