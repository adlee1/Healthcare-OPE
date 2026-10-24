"""Repartition complete source events before constructing common opportunities."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import json
from decimal import Decimal

from april_repro.decision_opportunities import Event, timestamp


def event_owner(event: Event, count: int = 20) -> int:
    """Use the final identity, including the distinct order-identity blocker."""
    if type(count) is not int or count <= 0:
        raise ValueError("Invalid owner count")
    return int(event.subject) % count if event.subject else 0


def event_json(event: Event) -> str:
    row = asdict(event)
    row["time"] = event.time.isoformat() if event.time else None
    for key in ("dose_meq", "rate_ml_hr"):
        row[key] = str(row[key]) if row[key] is not None else None
    return json.dumps(row, separators=(",", ":")) + "\n"


def event_from_json(text: str) -> Event:
    row = json.loads(text)
    row["time"] = timestamp(row["time"])
    for key in ("dose_meq", "rate_ml_hr"):
        row[key] = Decimal(row[key]) if row[key] is not None else None
    return Event(**row)


class DecisionCounts:
    """Count without retaining every excluded opportunity in memory."""
    def __init__(self):
        self.opportunities = self.eligible = 0
        self.subjects, self.admissions = set(), set()
        self.eligible_subjects, self.eligible_admissions = set(), set()
        self.actions, self.first, self.action_errors, self.outcome_errors = (
            Counter(), Counter(), Counter(), Counter())

    def add(self, rows):
        for row in rows:
            self.opportunities += 1
            self.subjects.add(row["subject_id"])
            self.admissions.add((row["subject_id"], row["hadm_id"]))
            self.first[row["exclusion_reason"] or "eligible"] += 1
            self.action_errors[row["action_exclusion"] or "none"] += 1
            self.outcome_errors[row["outcome_exclusion"] or "none"] += 1
            if row["eligible"]:
                self.eligible += 1
                self.eligible_subjects.add(row["subject_id"])
                self.eligible_admissions.add((row["subject_id"], row["hadm_id"]))
                self.actions[str(row["action"])] += 1

    def summary(self):
        return {
            "task": "potassium", "opportunities": self.opportunities,
            "subjects": len(self.subjects), "admissions": len(self.admissions),
            "eligible_decisions": self.eligible,
            "eligible_subjects": len(self.eligible_subjects),
            "eligible_admissions": len(self.eligible_admissions),
            "action_distribution": dict(sorted(self.actions.items())),
            "first_exclusions": dict(sorted(self.first.items())),
            "action_exclusions": dict(sorted(self.action_errors.items())),
            "outcome_exclusions": dict(sorted(self.outcome_errors.items())),
            "formal_cohort_complete": False,
        }


def combine_owner_summaries(summaries):
    """Owners partition by subject, so patient/admission totals are additive."""
    counters = ("action_distribution", "first_exclusions", "action_exclusions", "outcome_exclusions")
    counts = ("opportunities", "subjects", "admissions", "eligible_decisions",
              "eligible_subjects", "eligible_admissions", "selected_source_admissions",
              "admissions_without_constructible_grid", "order_identity_blockers")
    result = {"task": "potassium", "formal_cohort_complete": False}
    for field in counts:
        result[field] = sum(s[field] for s in summaries)
    for field in counters:
        total = Counter()
        for summary in summaries:
            total.update(summary[field])
        result[field] = dict(sorted(total.items()))
    return result
