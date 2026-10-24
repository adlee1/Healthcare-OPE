"""Treatment-anchored decisions plus independent four-hour zero selection cells.

These are declared implementation choices for APRIL, not recovered author code.
Four hours describes pretreatment context; it never truncates a positive dose.
Missing pretreatment labs are retained. Clinical SQL selects the first post lab
and makes its own eligibility decision, which this module cannot override.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json

from april_repro.decision_opportunities import (
    HOURS, NONADMIN, infusion_intervals, sodium_action,
)
from april_repro.sodium_episodes import build_sodium_episodes


RULE_VERSION = "treatment-decisions-v1"
CLINICAL_COLUMNS = (
    "extraction_version", "admittime", "dischtime", "admission_rows", "subject_match_rows",
    "outcome_deadline", "input_parse_problem", "context_exclusion",
    "episode_context_exclusion", "decision_context_exclusion", "lab_item_id",
    "anchor_location_class", "start_location_class", "location_class", "active_transfer_rows", "active_icu_rows",
    "active_named_non_icu_rows", "invalid_transfer_rows",
    "pre_lab_class", "pre_labevent_ids", "pre_lab_rows", "pre_valid_rows",
    "pre_distinct_values", "pre_lab_time", "pre_latest_storetime", "pre_lab_value",
    "post_lab_class", "post_labevent_ids", "post_lab_rows", "post_valid_rows",
    "post_distinct_values", "post_lab_time", "post_latest_storetime", "post_lab_value",
    "post_missing_storetime_rows", "post_reversed_storetime_rows",
    "clinical_exclusion", "clinical_eligible",
)
DECISION_COLUMNS = (
    "event_id", "decision_id", "task", "rule_version", "subject_id", "hadm_id",
    "anchor_time", "outcome_after_time", "action_end", "zero_cell_end",
    "candidate_kind", "timing_basis", "treatment_end_observed", "source_event_keys",
    "window_source_event_keys", "interference_source_event_keys", "active_infusion_source_event_keys",
    "full_dose_meq", "window_dose_meq", "action", "quantity_basis", "zero_basis",
    "action_exclusion", "outcome_exclusion", "exclusion_reason", "eligible",
    "post_gap_from_action_end_hours", "prompt_target_time",
) + CLINICAL_COLUMNS


def _time(value):
    if value in ("", None):
        return None
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError("Invalid treatment decision time") from None
    if result.tzinfo is not None:
        raise ValueError("Treatment times must be timezone-naive")
    return result


def _iso(value):
    return value.isoformat() if value is not None else ""


def _true(value):
    return value is True or value == "t" or value == "True"


def _dose(value):
    try:
        result = Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None
    return result if result.is_finite() else None


def _decimal(value):
    # Canonical fixed-point spelling keeps IDs independent of decimal scale.
    return format(value, "f").rstrip("0").rstrip(".") if value.as_tuple().exponent < 0 else format(value, "f")


def _id(*parts):
    return hashlib.sha256(json.dumps([RULE_VERSION, *parts], ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def _validate_events(events, task):
    if task not in ("potassium", "sodium"):
        raise ValueError("Unknown task")
    events = list(events)
    keys = [e.key for e in events]
    if any(not isinstance(key, str) or not key or "|" in key for key in keys) or len(set(keys)) != len(keys):
        raise ValueError("Missing, duplicate, or invalid source event key")
    for event in events:
        if event.time is not None and not isinstance(event.time, datetime):
            raise ValueError("Normalized source times must be datetimes or missing")
        _time(event.time)
    return events


def _candidate(task, kind, subject, admission, start, end, dose, sources,
               quantity_basis, timing_basis, observed=False, segments=None):
    action = sodium_action(dose) if task == "sodium" else int(dose)
    result = {
        "subject_id": subject, "hadm_id": admission, "task": task,
        "anchor_time": _iso(start), "outcome_after_time": _iso(end),
        "full_dose_meq": _decimal(dose), "action": action,
        "candidate_kind": kind, "source_event_keys": list(sources),
        "quantity_basis": quantity_basis, "timing_basis": timing_basis,
        "treatment_end_observed": observed, "segments": segments or [],
    }
    result["decision_id"] = _id(task, kind, subject, admission, _iso(start), _iso(end),
                                _decimal(dose), list(sources))
    return result


def make_positive_candidates(events, task):
    """Return usable positive source candidates; clinical eligibility is separate.

    K uses each distinct administered head, without addition across heads. Na
    integrates each complete observed episode and retains measured single doses.
    Positive Na doses use nearest action, lower tie; >500 is excluded, not clipped.
    """
    events = _validate_events(events, task)
    candidates, exclusions = [], Counter()
    source_summary = {}
    if task == "sodium":
        episodes, source_summary = build_sodium_episodes(events)
        for row in episodes:
            if not row["eligible_positive_candidate"]:
                exclusions[row["exclusion_reason"]] += 1
                continue
            dose = _dose(row["dose_meq"])
            if sodium_action(dose) is None:
                exclusions["outside_paper_action_support"] += 1
                continue
            start = _time(row["start_time"])
            end = _time(row["end_time"]) if row["treatment_end_observed"] else start
            candidates.append(_candidate(
                task, row["candidate_kind"], row["subject_id"], row["hadm_id"],
                start, end, dose, row["source_event_keys"], row["quantity_basis"],
                row["timing_basis"], row["treatment_end_observed"], row["segments"]))
    else:
        for event in events:
            if not event.relevant or event.status != "Administered":
                continue
            dose = _dose(event.dose_meq)
            reason = ("missing_patient_or_admission" if not event.subject or not event.admission else
                      "missing_administration_time" if event.time is None else
                      "unsupported_identity_route_or_product" if not event.supported else
                      "outside_paper_action_support" if dose not in (10, 20, 40) else "")
            if reason:
                exclusions[reason] += 1
                continue
            candidates.append(_candidate(
                task, "single_administered", event.subject, event.admission,
                event.time, event.time, dose, [event.key],
                "recorded_component_dose_at_emar_time", "single_emar_charttime_no_observed_infusion_end"))
    candidates.sort(key=lambda r: (r["subject_id"], r["hadm_id"], r["anchor_time"], r["decision_id"]))
    summary = {
        "rule_version": RULE_VERSION, "task": task, "source_events": len(events),
        "positive_candidates": len(candidates),
        "subjects": len({r["subject_id"] for r in candidates}),
        "admissions": len({(r["subject_id"], r["hadm_id"]) for r in candidates}),
        "action_distribution": dict(sorted(Counter(str(r["action"]) for r in candidates).items())),
        "candidate_exclusions": dict(sorted(exclusions.items())),
        "candidate_kinds": dict(sorted(Counter(r["candidate_kind"] for r in candidates).items())),
        "four_hour_dose_truncation": False, "clinical_eligibility_assessed": False,
    }
    if source_summary:
        summary["sodium_episode_summary"] = source_summary
    return candidates, summary


def _checked_candidate(candidate, source_index, task):
    if candidate.get("task", task) != task:
        raise ValueError("Candidate task mismatch")
    subject, admission = candidate["subject_id"], candidate["hadm_id"]
    start, end = _time(candidate["anchor_time"]), _time(candidate["outcome_after_time"])
    sources = candidate["source_event_keys"]
    dose = _dose(candidate["full_dose_meq"])
    if (not subject or not admission or start is None or end is None or end < start
            or not isinstance(sources, list) or not sources or len(sources) != len(set(sources))
            or dose is None or dose <= 0):
        raise ValueError("Invalid positive candidate")
    expected_action = sodium_action(dose) if task == "sodium" else int(dose) if dose in (10, 20, 40) else None
    if expected_action is None or candidate["action"] != expected_action:
        raise ValueError("Candidate action differs from declared dose rule")
    for key in sources:
        event = source_index.get(key)
        if (event is None or (event.subject, event.admission) != (subject, admission)
                or not event.relevant or not event.supported or event.time is None
                or not start <= event.time <= end or event.status in NONADMIN):
            raise ValueError("Candidate source identity or timing mismatch")
    expected_id = _id(task, candidate["candidate_kind"], subject, admission,
                      _iso(start), _iso(end), _decimal(dose), sources)
    if candidate["decision_id"] != expected_id:
        raise ValueError("Candidate ID differs from source definition")
    return start, end


def build_treatment_decisions(clinical_positive_rows, positive_candidates,
                              zero_clinical_rows, events, task):
    """Join complete clinical batches and apply source-aware co-treatment rules.

    Caller may use admission batches, passing their complete source timelines.
    Positive candidates and clinical rows must match exactly within that batch.
    Every provided zero grid row is evaluated, including clinically excluded
    rows. No historical pilot-eligibility flag or prior-four-hour K veto is used.
    """
    events = _validate_events(events, task)
    source_index = {e.key: e for e in events}
    # Candidate artifacts are not authority for dose, timing, or source exemption.
    # Recompute from each complete admission batch before excluding focal keys.
    rebuilt, _ = make_positive_candidates(events, task)
    canonical = {r["decision_id"]: r for r in rebuilt}
    grouped = defaultdict(list)
    for event in events:
        if event.relevant and event.status not in NONADMIN:
            grouped[event.subject, event.admission].append(event)
    # The legacy helper groups only by pharmacy stream, so invoke per admission.
    intervals = {key: infusion_intervals(items, task) for key, items in grouped.items()}
    candidates = {}
    used_sources = set()
    for candidate in positive_candidates:
        _checked_candidate(candidate, source_index, task)
        key = candidate["decision_id"]
        reference = canonical.get(key)
        if reference is None or any(candidate.get(field) != value for field, value in reference.items()):
            raise ValueError("Candidate differs from original source events")
        if key in candidates or used_sources.intersection(candidate["source_event_keys"]):
            raise ValueError("Duplicate positive candidate or reused source event")
        used_sources.update(candidate["source_event_keys"])
        candidates[key] = candidate
    clinical = {}
    for row in clinical_positive_rows:
        key = row["decision_id"]
        if key in clinical or key not in candidates:
            raise ValueError("Duplicate or unexpected positive clinical row")
        candidate = candidates[key]
        if (any(row[f] != candidate[f] for f in ("subject_id", "hadm_id"))
                or _time(row["anchor_time"]) != _time(candidate["anchor_time"])
                or _time(row["outcome_after_time"]) != _time(candidate["outcome_after_time"])):
            raise ValueError("Positive clinical identity or clock mismatch")
        clinical[key] = row
    if set(clinical) != set(candidates):
        raise ValueError("Missing positive clinical rows")

    outputs, zero_seen = [], set()

    def emit(row, candidate=None):
        subject, admission = row["subject_id"], row["hadm_id"]
        start = _time(row["anchor_time"])
        if not subject or not admission or start is None:
            raise ValueError("Invalid treatment decision identity")
        after = _time(candidate["outcome_after_time"]) if candidate else start
        selection_end = None if candidate else _time(row.get("zero_cell_end") or row.get("action_end"))
        if candidate is None and selection_end != start + HOURS:
            raise ValueError("Zero selection cell must span exactly four hours")
        if candidate is None and row.get("outcome_after_time") and _time(row["outcome_after_time"]) != start:
            raise ValueError("Zero clinical outcome clock must equal anchor")
        post = _time(row.get("post_lab_time"))
        clinical_error = row.get("clinical_exclusion") or ""
        if not _true(row.get("clinical_eligible")) and not clinical_error:
            clinical_error = "clinical_eligibility_not_established"
        if not clinical_error and (post is None or not after < post <= after + timedelta(hours=24)):
            raise ValueError("Clinically eligible first post lab has invalid time")
        focal = set(candidate["source_event_keys"]) if candidate else set()
        relevant = grouped.get((subject, admission), [])
        others = [e for e in relevant if e.key not in focal]
        missing_keys = {e.key for e in others if e.time is None}
        horizon = post if post is not None and post >= start else after
        direct = {e.key for e in others if e.time is not None and start <= e.time <= horizon}
        window = {e.key for e in others if e.time is not None and selection_end is not None
                  and start <= e.time < selection_end}
        active = set()
        for span in intervals.get((subject, admission), []):
            if set(span.source).issubset(focal) or (span.rate_ml_hr is not None and span.rate_ml_hr <= 0):
                continue
            if span.end > start and (span.start <= horizon or
                                    (selection_end is not None and span.start < selection_end)):
                active.update(span.source)
        action_error = "unresolved_source_time" if missing_keys else ""
        outcome_error = ""
        if candidate is None:
            if window:
                action_error = action_error or "treatment_evidence_in_zero_selection_cell"
            if active:
                action_error = action_error or "active_or_unresolved_infusion"
            if direct - window:
                outcome_error = "additional_treatment_before_outcome"
        elif active or direct:
            outcome_error = "additional_treatment_before_outcome"
        exclusion = clinical_error or action_error or outcome_error
        dose = candidate["full_dose_meq"] if candidate else "0"
        action = candidate["action"] if candidate else 0
        decision_id = candidate["decision_id"] if candidate else _id(task, "zero_grid", subject, admission, _iso(start))
        item = {column: "" if row.get(column) is None else row.get(column, "") for column in CLINICAL_COLUMNS}
        item.update({
            "event_id": decision_id, "decision_id": decision_id, "task": task,
            "rule_version": RULE_VERSION, "subject_id": subject, "hadm_id": admission,
            "anchor_time": _iso(start), "outcome_after_time": _iso(after), "action_end": _iso(after),
            "zero_cell_end": _iso(selection_end),
            "candidate_kind": candidate["candidate_kind"] if candidate else "zero_grid",
            "timing_basis": candidate["timing_basis"] if candidate else "admission_aligned_grid_anchor",
            "treatment_end_observed": candidate["treatment_end_observed"] if candidate else False,
            "source_event_keys": "|".join(sorted(focal)),
            "window_source_event_keys": "|".join(sorted(focal if candidate else window)),
            "interference_source_event_keys": "|".join(sorted(missing_keys | direct | window | active)),
            "active_infusion_source_event_keys": "|".join(sorted(active)),
            "full_dose_meq": dose, "window_dose_meq": dose,
            "action": action, "quantity_basis": candidate["quantity_basis"] if candidate else "no_recorded_treatment_in_selection_cell",
            "zero_basis": "no_recorded_exposure_in_declared_sources_and_observation_interval" if candidate is None else "",
            "action_exclusion": action_error, "outcome_exclusion": outcome_error,
            "clinical_exclusion": clinical_error, "exclusion_reason": exclusion, "eligible": not exclusion,
            "post_gap_from_action_end_hours": str((post - after).total_seconds() / 3600) if post is not None else "",
            "prompt_target_time": _iso(start + timedelta(hours=action / (10 if task == "potassium" else 30) + 3)),
        })
        outputs.append({column: item[column] for column in DECISION_COLUMNS})

    for key in sorted(candidates):
        emit(clinical[key], candidates[key])
    for row in zero_clinical_rows:
        identity = (row["subject_id"], row["hadm_id"], _time(row["anchor_time"]))
        if identity in zero_seen:
            raise ValueError("Duplicate zero selection cell")
        zero_seen.add(identity)
        emit(row)
    outputs.sort(key=lambda r: (r["subject_id"], r["hadm_id"], r["anchor_time"], r["event_id"]))
    if len({r["event_id"] for r in outputs}) != len(outputs):
        raise ValueError("Duplicate treatment decision ID")
    eligible = [r for r in outputs if r["eligible"]]
    summary = {
        "rule_version": RULE_VERSION, "task": task, "decisions": len(outputs),
        "positive_candidates": len(candidates), "zero_candidates": len(zero_seen),
        "subjects": len({r["subject_id"] for r in outputs}),
        "admissions": len({(r["subject_id"], r["hadm_id"]) for r in outputs}),
        "eligible_decisions": len(eligible),
        "eligible_subjects": len({r["subject_id"] for r in eligible}),
        "eligible_admissions": len({(r["subject_id"], r["hadm_id"]) for r in eligible}),
        "action_distribution": dict(sorted(Counter(str(r["action"]) for r in eligible).items())),
        "first_exclusions": dict(sorted(Counter(r["exclusion_reason"] or "eligible" for r in outputs).items())),
        "action_exclusions": dict(sorted(Counter(r["action_exclusion"] or "none" for r in outputs).items())),
        "outcome_exclusions": dict(sorted(Counter(r["outcome_exclusion"] or "none" for r in outputs).items())),
        "missing_pre_lab_retained": sum(r["pre_lab_class"] != "usable" for r in eligible),
        "order_identity_blockers": sum(e.key.startswith("order-identity-block:") for e in events),
        "four_hour_dose_truncation": False, "author_rules_recovered": False,
    }
    return outputs, summary
