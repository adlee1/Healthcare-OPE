"""Four-hour observational decisions; no patient data or database side effects."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib

HOURS = timedelta(hours=4)
STARTS = frozenset({"Started", "Restarted", "Delayed Started"})
STOPS = frozenset({"Stopped", "Stopped - Unscheduled"})
NONADMIN = frozenset({"Not Given", "Not Administered"})
DOCUMENTED = STARTS | {"Administered", "Partial Administered", "Confirmed"}
EARLIEST = datetime.min
LATEST = datetime.max


@dataclass(frozen=True)
class Event:
    key: str
    subject: str
    admission: str
    stream: str
    time: datetime | None
    status: str
    relevant: bool
    supported: bool
    dose_meq: Decimal | None = None
    rate_ml_hr: Decimal | None = None


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime
    rate_ml_hr: Decimal | None  # None: exposure cannot be resolved.
    source: tuple[str, ...]


def timestamp(value: str) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def number(value: str) -> Decimal | None:
    if not value:
        return None
    try:
        result = Decimal(value)
    except ArithmeticError:
        return None
    return result if result.is_finite() else None


def overlap(interval: Interval, start: datetime, end: datetime) -> Decimal:
    delta = min(interval.end, end) - max(interval.start, start)
    return max(Decimal(0), Decimal(str(delta.total_seconds())) / Decimal(3600))


def normalize_events(rows: list[dict[str, str]], task: str) -> list[Event]:
    events = []
    seen = set()
    for row in rows:
        key = row["emar_id"]
        if not key or key in seen:
            raise ValueError("Missing or duplicate source event key")
        seen.add(key)
        if task == "potassium":
            relevant = row["possible_relevant_exposure"] == "t"
            supported = row["dose_usable"] == "t"
            dose = number(row.get("recorded_component_dose_meq", "")) if supported else None
            rate = None
        elif task == "sodium":
            relevant = row.get("head_source") != "known_other_head"
            supported = (row.get("identity_bad") == "f" and row.get("route_bad") == "f"
                         and int(row.get("pharmacy_identity_problem_heads") or 0) == 0
                         and row.get("head_source") in
                         {"missing_head_order_assumption", "exact_saline_head"})
            dose = number(row.get("single_administered_sodium_meq", "")) if supported else None
            rate = number(row.get("parent_rate_ml_per_hour", "")) if supported else None
        else:
            raise ValueError("Unknown task")
        raw_status = row.get("raw_administration_status", row["administration_status"])
        status = {s.lower(): s for s in
                  STARTS | STOPS | NONADMIN | DOCUMENTED}.get(raw_status.strip().lower(), raw_status)
        events.append(Event(key, row["subject_id"], row["hadm_id"],
                            row.get("pharmacy_id", "") or "unlinked:" + key,
                            timestamp(row.get("anchor_time", "")),
                            status, relevant, supported, dose, rate))
        order_key = (row.get("source_order_subject_id", ""), row.get("source_order_hadm_id", ""))
        sole_order = (task == "potassium" or
                      (row.get("order_subjects") == "1" and row.get("order_admissions") == "1"
                       and row.get("order_missing_ids") == "0"))
        if relevant and sole_order and all(order_key) and order_key != (row["subject_id"], row["hadm_id"]):
            # Keep the original identity and dose unresolved. A uniquely linked
            # order admission additionally receives an unknown blocker, not a
            # reassigned dose or a repaired clinical identity.
            events.append(Event("order-identity-block:" + key, *order_key,
                                row.get("pharmacy_id", "") or "unlinked:" + key,
                                timestamp(row.get("anchor_time", "")),
                                status, True, False))
    return events


def selected_admissions(events: list[Event]) -> list[tuple[str, str]]:
    """Treatment-source population, not a population selected by final action."""
    return sorted({(e.subject, e.admission) for e in events if e.subject and e.admission
                   and e.relevant and e.status in DOCUMENTED})


def infusion_intervals(events: list[Event], task: str) -> list[Interval]:
    """Closed start/confirmation/stop blocks; unresolved streams remain unknown.

    No interpolation across another start or unknown control. Orphan confirmations
    or stops conservatively make the interval since the preceding stop unknown.
    A missing stop never means zero. K infusions have no measured rates here.
    """
    streams = defaultdict(list)
    for event in events:
        if event.time is not None:
            streams[event.stream].append(event)
    result = []
    for stream in streams.values():
        stream.sort(key=lambda e: (e.time, e.key))
        counts = Counter(e.time for e in stream)
        covered = set()
        for i, event in enumerate(stream):
            if event.status not in STARTS or not event.relevant:
                continue
            j = i + 1
            while j < len(stream) and stream[j].status == "Confirmed":
                j += 1
            closed = j < len(stream) and stream[j].status in STOPS
            block = stream[i:j + 1] if closed else []
            valid = (closed and task == "sodium" and all(
                e.relevant and e.supported and counts[e.time] == 1 for e in block)
                and all(e.rate_ml_hr is not None and e.rate_ml_hr >= 0 for e in block[:-1]))
            if valid:
                for left, right in zip(block, block[1:]):
                    result.append(Interval(left.time, right.time, left.rate_ml_hr,
                                           (left.key, right.key)))
                covered.update(e.key for e in block)
            else:
                # A later supported stop bounds uncertainty; another start does not.
                stop = next((e for e in stream[i + 1:] if e.status in STOPS
                             and e.relevant and (e.supported or task == "potassium")), None)
                end = stop.time if stop else LATEST
                if end > event.time:
                    result.append(Interval(event.time, end, None, (event.key,)))
                # Tied start/stop cannot establish a zero-length treatment.
                elif end == event.time:
                    result.append(Interval(event.time, event.time + HOURS, None, (event.key,)))
                covered.update(e.key for e in stream[i:] if e.time <= end)
        last_stop = EARLIEST
        for event in stream:
            if event.status in (STOPS | {"Confirmed"}) and event.key not in covered and event.relevant:
                stop = next((e for e in stream if e.time >= event.time and e.status in STOPS
                             and e.relevant and (e.supported or task == "potassium")), None)
                end = stop.time if stop else LATEST
                if end > last_stop:
                    result.append(Interval(last_stop, end, None, (event.key,)))
            if event.status in STOPS and event.relevant and (event.supported or task == "potassium"):
                last_stop = event.time
        for event in stream:
            if (not event.relevant or
                    event.status in STARTS | STOPS | NONADMIN | {"Confirmed", "Administered"}):
                continue
            # Unknown controls, including partial/unspecified administration,
            # cannot be forgotten at the next window boundary.
            stop = next((e for e in stream if e.time > event.time and e.status in STOPS
                         and e.relevant and (e.supported or task == "potassium")), None)
            result.append(Interval(event.time, stop.time if stop else LATEST, None, (event.key,)))
    return result


def sodium_action(dose: Decimal) -> int | None:
    """Zero is absence, never a rounded small positive amount. No top clipping."""
    if not dose.is_finite() or dose < 0 or dose > 500:
        return None
    if dose == 0:
        return 0
    return min((100, 200, 300, 400, 500), key=lambda a: (abs(dose - a), a))


def build_decisions(opportunities: list[dict[str, str]], events: list[Event],
                    task: str) -> tuple[list[dict], dict]:
    if task not in ("potassium", "sodium"):
        raise ValueError("Unknown task")
    keys = [e.key for e in events]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise ValueError("Missing or duplicate source event key")
    grouped = defaultdict(list)
    for event in events:
        grouped[event.subject, event.admission].append(event)
    intervals = {key: infusion_intervals(items, task) for key, items in grouped.items()}
    outputs, seen = [], set()
    for row in opportunities:
        key = (row["subject_id"], row["hadm_id"])
        start, end = timestamp(row["anchor_time"]), timestamp(row["action_end"])
        post = timestamp(row.get("post_lab_time", ""))
        if start is None or end != start + HOURS:
            raise ValueError("Invalid common opportunity interval")
        identity = (*key, row["anchor_time"], task)
        if identity in seen:
            raise ValueError("Duplicate common opportunity")
        seen.add(identity)
        items = grouped.get(key, [])
        relevant = [e for e in items if e.relevant and e.status not in NONADMIN]
        spans = intervals.get(key, [])
        window = [e for e in relevant if e.time is not None and start <= e.time < end]
        dose, action_error, outcome_error = Decimal(0), "", ""
        if any(e.time is None for e in relevant):
            action_error = "unresolved_source_time"
        elif any(span.rate_ml_hr is None and overlap(span, start, end) > 0 for span in spans):
            action_error = "unresolved_active_infusion"
        elif task == "potassium" and any(
                e.time is not None and start - HOURS <= e.time < start for e in relevant):
            # Same carryover eligibility rule for positive and zero opportunities.
            action_error = "prior_four_hour_potassium_exposure"
        for event in window:
            if event.status == "Administered" and event.supported and event.dose_meq is not None:
                if event.dose_meq <= 0:
                    action_error = action_error or "unresolved_window_administration"
                else:
                    dose += event.dose_meq
            elif event.status not in STARTS | STOPS | {"Confirmed"}:
                action_error = action_error or "unresolved_window_administration"
            elif task == "potassium":
                action_error = action_error or "unresolved_window_administration"
        if task == "sodium":
            for span in spans:
                hours = overlap(span, start, end)
                if hours > 0 and span.rate_ml_hr is not None:
                    dose += hours * span.rate_ml_hr * Decimal("0.513")
            action = sodium_action(dose)
        else:
            action = int(dose) if dose in (0, 10, 20, 40) else None
        if action_error:
            action = None
        elif action is None:
            action_error = "outside_paper_action_support"
        if post is not None:
            if any(e.time is not None and end <= e.time <= post
                   and e.status not in (STARTS | STOPS | {"Confirmed"} if task == "sodium" else STOPS)
                   for e in relevant):
                outcome_error = "outcome_intervened"
            if any(overlap(span, end, post) > 0 and
                   (span.rate_ml_hr is None or span.rate_ml_hr > 0) for span in spans):
                outcome_error = "outcome_intervened"
            if task == "sodium" and any(
                    e.time == post and e.status in STARTS | {"Confirmed"}
                    and (not e.supported or e.rate_ml_hr is None or e.rate_ml_hr > 0)
                    for e in relevant):
                outcome_error = "outcome_intervened"
        clinical_error = row.get("clinical_exclusion", "")
        if row.get("clinical_eligible") != "t" and not clinical_error:
            clinical_error = "clinical_eligibility_not_established"
        exclusion = clinical_error or action_error or outcome_error
        event_id = hashlib.sha256("|".join(identity).encode()).hexdigest()
        outputs.append({
            **row, "task": task, "event_id": event_id,
            "window_source_event_keys": "|".join(e.key for e in window),
            "window_dose_meq": str(dose) if not action_error else "",
            "action": action, "action_exclusion": action_error,
            "outcome_exclusion": outcome_error, "exclusion_reason": exclusion,
            "eligible": not exclusion,
            "quantity_basis": "charted_rate_estimate_and_recorded_bolus" if task == "sodium"
                              else "recorded_component_dose_at_emar_time",
            "zero_basis": "no_recorded_exposure_in_declared_sources" if action == 0 else "",
            "prompt_target_time": (start + timedelta(hours=(action or 0) /
                                   (10 if task == "potassium" else 30) + 3)).isoformat()
                                  if action is not None else "",
        })
    eligible = [r for r in outputs if r["eligible"]]
    summary = {
        "task": task, "opportunities": len(outputs),
        "subjects": len({r["subject_id"] for r in outputs}),
        "admissions": len({(r["subject_id"], r["hadm_id"]) for r in outputs}),
        "eligible_decisions": len(eligible),
        "eligible_subjects": len({r["subject_id"] for r in eligible}),
        "eligible_admissions": len({(r["subject_id"], r["hadm_id"]) for r in eligible}),
        "action_distribution": dict(sorted(Counter(str(r["action"]) for r in eligible).items())),
        "first_exclusions": dict(sorted(Counter(r["exclusion_reason"] or "eligible" for r in outputs).items())),
        "action_exclusions": dict(sorted(Counter(r["action_exclusion"] or "none" for r in outputs).items())),
        "outcome_exclusions": dict(sorted(Counter(r["outcome_exclusion"] or "none" for r in outputs).items())),
        "order_identity_blockers": sum(e.key.startswith("order-identity-block:") for e in events),
        "formal_cohort_complete": False,
    }
    return outputs, summary
