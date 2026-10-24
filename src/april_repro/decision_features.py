"""Assemble pre-decision features separately from outcomes and cohort labels."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import re

FEATURES = (
    "age", "gender", "weight_kg", "height_cm", "heart_rate",
    "respiratory_rate", "spo2", "sbp", "dbp", "creatinine",
    "administered_nacl_09", "administered_dextrose_5",
    "administered_propofol", "administered_norepinephrine", "administered_insulin",
)
MEDICATION_FEATURES = FEATURES[10:]
IDENTITY = ("event_id", "subject_id", "hadm_id", "decision_time")
OUTCOMES = (
    "event_id", "subject_id", "hadm_id", "task", "anchor_time", "action_end",
    "action", "window_dose_meq", "quantity_basis", "zero_basis",
    "pre_lab_value", "pre_lab_time", "pre_latest_storetime", "pre_labevent_ids",
    "post_lab_value", "post_lab_time", "post_latest_storetime",
    "post_labevent_ids", "post_gap_from_action_end_hours", "prompt_target_time",
)


def parse_time(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError("Invalid decision time") from None
    if result.tzinfo is not None:
        raise ValueError("MIMIC decision time must be timezone-naive")
    return result


def decision_keys(rows: list[dict[str, str]]) -> list[tuple[str, str, str, str]]:
    """Validate identifiers before rendering private, bounded VALUES inputs."""
    result, seen = [], set()
    for row in rows:
        event = row["event_id"]
        if not re.fullmatch(r"[0-9a-f]{64}", event) or event in seen:
            raise ValueError("Invalid or repeated decision event ID")
        seen.add(event)
        for field in ("subject_id", "hadm_id"):
            value = row[field]
            if not re.fullmatch(r"[1-9][0-9]{0,9}", value) or int(value) > 2147483647:
                raise ValueError("Invalid decision identity")
        when = parse_time(row["anchor_time"]).isoformat(sep=" ")
        result.append((event, row["subject_id"], row["hadm_id"], when))
    return result


def render_decision_query(template: str, rows: list[dict[str, str]]) -> str:
    keys = decision_keys(rows)
    if not keys or len(keys) > 5000 or template.count("__DECISION_KEYS__") != 1:
        raise ValueError("Invalid bounded feature query")
    # The validated values contain only hex, digits, and datetime punctuation.
    values = ",".join(
        f"('{e}'::text,{s}::integer,{h}::integer,'{t}'::timestamp)"
        for e, s, h, t in keys
    )
    return template.replace("__DECISION_KEYS__", values)


def _indexed(rows: list[dict[str, str]], expected: dict, kind: str) -> dict:
    indexed = {}
    for row in rows:
        key = row["event_id"]
        if key not in expected or key in indexed:
            raise ValueError(f"{kind} contains a duplicate or unexpected event")
        reference = expected[key]
        if any(row[f] != reference[f] for f in ("subject_id", "hadm_id")):
            raise ValueError(f"{kind} identity mismatch")
        if parse_time(row["decision_time"]) != parse_time(reference["anchor_time"]):
            raise ValueError(f"{kind} decision time mismatch")
        indexed[key] = row
    if set(indexed) != set(expected):
        raise ValueError(f"{kind} is missing events")
    return indexed


def _feature_value(name: str, value: str | None):
    if value in (None, ""):
        return ""
    if name == "gender":
        if value not in ("F", "M"):
            raise ValueError("Unexpected nonmissing gender")
        return value
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError("Invalid feature number") from None
    if not number.is_finite():
        raise ValueError("Nonfinite feature number")
    if name in MEDICATION_FEATURES:
        if number not in (0, 1):
            raise ValueError("Medication feature must be binary or missing")
    elif number <= 0:
        raise ValueError("Clinical measurement must be positive or missing")
    return value


def assemble_features(decisions, contexts, medications, groups):
    """No outcome, action, diagnosis label or future time enters features.csv."""
    decision_keys(decisions)
    expected = {r["event_id"]: r for r in decisions}
    by_context = _indexed(contexts, expected, "Context")
    by_medication = _indexed(medications, expected, "Medication")
    by_group = _indexed(groups, expected, "Group")
    features, outcomes, split_inputs = [], [], []
    for decision in decisions:
        key = decision["event_id"]
        context, medication, group = by_context[key], by_medication[key], by_group[key]
        if any(context[name] != "t" for name in (
            "decision_key_valid", "all_vital_ids_verified", "creatinine_id_verified"
        )):
            raise ValueError("Feature source dictionary or input key check failed")
        cutoff = parse_time(decision["anchor_time"])
        for evidence in json.loads(context["dynamic_evidence"]).values():
            if evidence["status"] == "available":
                chart = parse_time(evidence["charttime"])
                stored = parse_time(evidence["latest_storetime"])
                if not cutoff - timedelta(hours=4) <= chart <= stored <= cutoff:
                    raise ValueError("Dynamic feature is not available in its declared window")
        for evidence in json.loads(context["static_evidence"]).values():
            if evidence["status"] == "available_date_only_no_storetime":
                if datetime.fromisoformat(evidence["chartdate"]).date() >= cutoff.date():
                    raise ValueError("Static date-only feature is not prior history")
        output = {k: context[k] for k in IDENTITY}
        for name in FEATURES:
            source = medication if name in MEDICATION_FEATURES else context
            output[name] = _feature_value(name, source[name])
        features.append(output)
        outcomes.append({name: decision[name] for name in OUTCOMES})
        split_inputs.append({
            "event_id": key, "subject_id": decision["subject_id"],
            "hadm_id": decision["hadm_id"], "action": decision["action"],
            "gender": output["gender"], "renal_disease": group["renal_disease"],
            "cirrhosis": group["cirrhosis"],
        })
    n = len(features)
    coverage = {}
    for name in FEATURES:
        present = sum(row[name] != "" for row in features)
        coverage[name] = {
            "observed": present, "missing": n - present,
            "observed_fraction": present / n if n else None,
        }
        if name in MEDICATION_FEATURES:
            coverage[name]["value_counts"] = dict(sorted(Counter(
                row[name] if row[name] != "" else "missing" for row in features).items()))
    summary = {
        "events": n, "subjects": len({r["subject_id"] for r in features}),
        "admissions": len({(r["subject_id"], r["hadm_id"]) for r in features}),
        "feature_columns": list(FEATURES), "coverage": coverage,
        "all_features_observed_events": sum(all(r[f] != "" for f in FEATURES) for r in features),
        "raw_missing_values_preserved": True, "imputation_fitted": False,
        "diagnoses_are_retrospective_group_labels_only": True,
    }
    return features, outcomes, split_inputs, summary
