"""Independent sodium treatment-dose candidates, without a cohort or zero action.

APRIL section 3.1 describes the four hours BEFORE treatment as context. This
candidate branch integrates a fully observed start/confirmation/stop sequence;
it does not truncate dose to a four-hour action window. A complete episode is a
project interpretation, not an assertion that the authors used this algorithm.

Input is the existing normalized Event interface. Identity, route, product and
unit decisions remain upstream. A known single Administered quantity is kept
separate: its charttime is not an observed infusion start or end.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
import hashlib
import json

from april_repro.decision_opportunities import NONADMIN, STARTS, STOPS


RULE_VERSION = "sodium-complete-treatment-candidates-v1"
MEQ_PER_ML = Decimal("0.513")


def _time(value):
    return value.isoformat() if value is not None else ""


def _finite(value):
    return isinstance(value, Decimal) and value.is_finite()


def _decimal(value):
    return format(value, "f") if value is not None else ""


def build_sodium_episodes(events):
    """Return private candidate rows and an aggregate summary.

    Accepts normalized Event objects; does not mutate them. Complete infusions
    and recorded single administrations are positive-dose candidates only.
    Unknown controls, missing times, tied records and unclosed tails do not
    become complete treatments, doses, or zero actions.
    """
    events = list(events)
    keys = [e.key for e in events]
    if any(not isinstance(key, str) or not key for key in keys) or len(set(keys)) != len(keys):
        raise ValueError("Missing or duplicate source event key")
    for e in events:
        if e.time is not None and (not isinstance(e.time, datetime) or e.time.tzinfo is not None):
            raise ValueError("Candidate times must be naive datetimes or missing")
    grouped = defaultdict(list)
    for e in events:
        grouped[e.subject, e.admission, e.stream].append(e)
    rows = []

    def emit(block, kind, reason, *, closed=False, dose=None, segments=None):
        first = block[0]
        accepted = not reason and dose is not None and dose > 0
        source = [e.key for e in block]
        payload = [RULE_VERSION, kind, first.subject, first.admission, first.stream, source]
        rows.append({
            "episode_id": hashlib.sha256(json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(),
            "subject_id": first.subject, "hadm_id": first.admission,
            "pharmacy_id": first.stream if not first.stream.startswith("unlinked:") else "",
            "candidate_kind": kind,
            "start_time": _time(first.time),
            "end_time": _time(block[-1].time) if closed else "",
            "timing_basis": ("observed_start_and_stop" if closed else
                             "single_emar_charttime_no_observed_infusion_end" if kind == "single_administered"
                             else "incomplete_or_unresolved_control"),
            "treatment_end_observed": closed,
            "dose_meq": _decimal(dose) if accepted else "",
            "quantity_basis": ("recorded_single_administration" if kind == "single_administered"
                               else "estimated_from_charted_piecewise_rate"),
            "eligible_positive_candidate": accepted,
            "exclusion_reason": reason,
            "source_event_keys": source,
            "segments": segments or [],
        })

    for identity in sorted(grouped):
        stream = sorted(grouped[identity], key=lambda e: (e.time is None, e.time or datetime.max, e.key))
        counts = Counter(e.time for e in stream if e.time is not None)
        missing_time = any(e.relevant and e.status not in NONADMIN and e.time is None for e in stream)
        unresolved = False

        def trusted_stop(event):
            return (event.status in STOPS and event.relevant and event.supported
                    and event.time is not None and counts[event.time] == 1)

        def base_reason(block):
            if not identity[0] or not identity[1]:
                return "missing_patient_or_admission"
            if missing_time:
                return "unresolved_stream_time"
            if any(e.time is None for e in block):
                return "missing_control_time"
            if any(counts[e.time] != 1 for e in block):
                return "tied_control_time"
            if any(not e.relevant or not e.supported for e in block):
                return "unsupported_identity_route_or_product"
            if unresolved:
                return "unresolved_prior_stream"
            return ""

        i = 0
        while i < len(stream):
            event = stream[i]
            if not event.relevant or event.status in NONADMIN:
                i += 1
                continue
            if event.status in STARTS:
                j = i + 1
                while j < len(stream) and stream[j].status == "Confirmed":
                    j += 1
                closed = j < len(stream) and stream[j].status in STOPS
                block = stream[i:j + 1] if closed else stream[i:j]
                reason = base_reason(block)
                if not closed:
                    reason = reason or ("unclosed_infusion" if j == len(stream)
                                        else "interrupted_before_stop")
                dose, segments = Decimal(0), []
                if closed and not reason:
                    for left, right in zip(block, block[1:]):
                        rate = left.rate_ml_hr
                        if not _finite(rate) or rate < 0:
                            reason = "missing_or_invalid_segment_rate"
                            break
                        delta = right.time - left.time
                        # Exact timedelta arithmetic avoids binary float integration.
                        seconds = (Decimal(delta.days * 86400 + delta.seconds)
                                   + Decimal(delta.microseconds) / Decimal(1000000))
                        if seconds <= 0:
                            reason = "nonpositive_segment_duration"
                            break
                        volume = rate * seconds / Decimal(3600)
                        segment_dose = volume * MEQ_PER_ML
                        dose += segment_dose
                        segments.append({
                            "start_time": _time(left.time), "end_time": _time(right.time),
                            "rate_ml_hr": _decimal(rate), "volume_ml": _decimal(volume),
                            "dose_meq": _decimal(segment_dose),
                            "source_event_keys": [left.key, right.key],
                        })
                    if not reason and dose <= 0:
                        reason = "zero_integral_not_positive_candidate"
                emit(block, "complete_infusion" if closed else "incomplete_infusion",
                     reason, closed=closed, dose=dose if not reason else None,
                     segments=segments if not reason else [])
                # An observed, unambiguous stop bounds uncertainty even if the
                # preceding dose is not calculable. A new start does not do so.
                unresolved = not (closed and trusted_stop(block[-1]))
                i = j + 1 if closed else j
                continue
            if event.status == "Administered":
                reason = base_reason([event])
                if not _finite(event.dose_meq) or event.dose_meq <= 0:
                    reason = reason or "missing_or_invalid_recorded_quantity"
                emit([event], "single_administered", reason,
                     dose=event.dose_meq if not reason else None)
                i += 1
                continue
            reason = base_reason([event])
            if event.status == "Confirmed":
                reason = reason or "orphan_confirmation"
                unresolved = True
            elif event.status in STOPS:
                reason = reason or "orphan_stop"
                if trusted_stop(event):
                    unresolved = False
                else:
                    unresolved = True
            else:
                reason = reason or "unresolved_control"
                unresolved = True
            emit([event], "unresolved_control", reason)
            i += 1
    rows.sort(key=lambda r: (r["subject_id"], r["hadm_id"], r["start_time"], r["episode_id"]))
    eligible = [row for row in rows if row["eligible_positive_candidate"]]
    positive_keys = [key for row in eligible for key in row["source_event_keys"]]
    if len(positive_keys) != len(set(positive_keys)):
        raise ValueError("A source event was counted in multiple positive candidates")
    summary = {
        "rule_version": RULE_VERSION,
        "source_events": len(events),
        "candidate_rows": len(rows),
        "subjects": len({r["subject_id"] for r in rows if r["subject_id"]}),
        "admissions": len({(r["subject_id"], r["hadm_id"]) for r in rows
                           if r["subject_id"] and r["hadm_id"]}),
        "eligible_positive_candidates": len(eligible),
        "eligible_subjects": len({r["subject_id"] for r in eligible}),
        "eligible_admissions": len({(r["subject_id"], r["hadm_id"]) for r in eligible}),
        "candidate_kinds": dict(sorted(Counter(r["candidate_kind"] for r in rows).items())),
        "eligible_candidate_kinds": dict(sorted(Counter(r["candidate_kind"] for r in eligible).items())),
        "first_exclusions": dict(sorted(Counter(r["exclusion_reason"] or "eligible" for r in rows).items())),
        "four_hour_dose_truncation": False,
        "zero_action_constructed": False,
        "outcome_labels_constructed": False,
        "formal_cohort_complete": False,
        "author_episode_rule_recovered": False,
    }
    return rows, summary
