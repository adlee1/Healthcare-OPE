"""APRIL cohort labels and globally stable subject-held-out folds.

Paper facts: female -> male, no renal disease -> renal disease (K),
no cirrhosis -> cirrhosis (Na), and low -> high dosage (section 3.4, p5).
Project choices: K <=20 versus 40; Na <=200 versus >=300, including zero
in low dosage; SHA256 modulo five reserves approximately 20% of subjects.

The input must contain already eligible decisions. Retrospective diagnosis
flags are grouping labels only; this module creates no predictor features.
Roles are assigned per decision. Subjects can occur in both dosage roles or
have different diagnosis labels across admissions; their global fold never
changes, and role overlap is explicitly reported rather than hidden.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import re
from typing import Any


RULE_VERSION = "cohort-splits-v1"
DEFAULT_SEED = "april-subject-fold-v1"
SPLITS = ("gender", "comorbidity", "dosage")
FOLDS = ("train", "validation")
ROLES = ("behavior", "target", "excluded")
ACTIONS = {
    "potassium": (0, 10, 20, 40),
    "sodium": (0, 100, 200, 300, 400, 500),
}


def _identifier(value: Any, label: str) -> str:
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("Missing or invalid " + label)
    return value


def _flag(value: Any) -> bool | None:
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        value = value.strip().lower()
        if value in ("t", "true", "1"):
            return True
        if value in ("f", "false", "0"):
            return False
    return None


def subject_fold(subject_id: str | int, *, seed: str = DEFAULT_SEED) -> str:
    """Return a subject's global fold; task, action and cohort never enter it."""
    subject = _identifier(subject_id, "subject identifier")
    if not isinstance(seed, str) or not seed:
        raise ValueError("The split seed must be a nonempty string")
    payload = json.dumps([seed, subject], ensure_ascii=False, separators=(",", ":"))
    bucket = int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest(), "big") % 5
    return "validation" if bucket == 0 else "train"


def _action(value: Any, task: str) -> int:
    if isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]*", value):
        value = int(value)
    if type(value) is not int or value not in ACTIONS[task]:
        raise ValueError("Action is outside the task's declared paper action set")
    return value


def _role(row: dict, task: str, split: str, action: int) -> tuple[str, str]:
    if split == "gender":
        gender = row.get("gender")
        gender = gender.strip().upper() if isinstance(gender, str) else ""
        if gender in ("F", "FEMALE"):
            return "behavior", ""
        if gender in ("M", "MALE"):
            return "target", ""
        return "excluded", "missing_or_unrecognized_gender"
    if split == "comorbidity":
        field = "renal_disease" if task == "potassium" else "cirrhosis"
        flag = _flag(row.get(field))
        if flag is None:
            return "excluded", "missing_or_unrecognized_" + field
        return ("target" if flag else "behavior"), ""
    cutoff = 20 if task == "potassium" else 200
    return ("behavior" if action <= cutoff else "target"), ""


def _counts(rows: list[dict], task: str) -> dict:
    actions = Counter(row["action"] for row in rows)
    return {
        "events": len(rows),
        "subjects": len({row["subject_id"] for row in rows}),
        "admissions": len({(row["subject_id"], row["hadm_id"])
                           for row in rows if row["hadm_id"]}),
        "action_distribution": {str(action): actions[action] for action in sorted(actions)},
        "missing_action_support": [action for action in ACTIONS[task] if not actions[action]],
    }


def build_cohort_splits(
    rows: list[dict], task: str, *, seed: str = DEFAULT_SEED,
) -> tuple[list[dict], dict]:
    """Return private event assignments and a patient-identifier-free summary.

    Required: event_id, subject_id, action. Optional hadm_id supports admission
    counts. gender/renal_disease/cirrhosis may be missing: only that split is
    excluded. If eligible or task is supplied, it must agree with this call.
    """
    if task not in ACTIONS:
        raise ValueError("Unknown task")
    # Validate the seed even for an empty cohort.
    subject_fold("synthetic-seed-validation", seed=seed)
    assignments, seen = [], set()
    for row in rows:
        event_id = _identifier(row.get("event_id"), "event identifier")
        subject = _identifier(row.get("subject_id"), "subject identifier")
        if event_id in seen:
            raise ValueError("Duplicate decision event identifier")
        seen.add(event_id)
        if "task" in row and row["task"] != task:
            raise ValueError("Input task does not match the requested task")
        if "eligible" in row and _flag(row["eligible"]) is not True:
            raise ValueError("Only eligible decisions may enter cohort splitting")
        admission = row.get("hadm_id")
        admission = "" if admission in ("", None) else _identifier(admission, "admission identifier")
        action = _action(row.get("action"), task)
        fold = subject_fold(subject, seed=seed)
        for split in SPLITS:
            role, reason = _role(row, task, split, action)
            assignments.append({
                "event_id": event_id, "subject_id": subject, "hadm_id": admission,
                "task": task, "split": split, "cohort_role": role,
                "fold": fold, "action": action, "exclusion_reason": reason,
            })
    assignments.sort(key=lambda row: (row["event_id"], SPLITS.index(row["split"])))
    summary = {
        "rule_version": RULE_VERSION,
        "task": task,
        "input_events": len(rows),
        "input_subjects": len({row["subject_id"] for row in assignments}),
        "assignment_rows": len(assignments),
        "fold_rule": "sha256_json_seed_subject_modulo5_zero_is_validation",
        "fold_seed": seed,
        "validation_fraction_nominal": 0.2,
        "role_unit": "decision_event",
        "diagnosis_labels_are_retrospective": True,
        "diagnosis_labels_are_predictor_features": False,
        "models_trained": False,
        "splits": {},
    }
    for split in SPLITS:
        selected = [row for row in assignments if row["split"] == split]
        by_role = {role: [row for row in selected if row["cohort_role"] == role] for role in ROLES}
        train_subjects = {row["subject_id"] for row in selected if row["fold"] == "train"}
        validation_subjects = {row["subject_id"] for row in selected if row["fold"] == "validation"}
        behavior_subjects = {row["subject_id"] for row in by_role["behavior"]}
        target_subjects = {row["subject_id"] for row in by_role["target"]}
        groups = {}
        empty_groups = []
        for role, members in by_role.items():
            groups[role] = _counts(members, task)
            groups[role]["folds"] = {}
            for fold in FOLDS:
                subset = [row for row in members if row["fold"] == fold]
                groups[role]["folds"][fold] = _counts(subset, task)
                if role != "excluded" and not subset:
                    empty_groups.append(role + "/" + fold)
        summary["splits"][split] = {
            "groups": groups,
            "behavior_and_target_present": bool(by_role["behavior"] and by_role["target"]),
            "empty_model_groups": empty_groups,
            "role_subject_overlap": len(behavior_subjects & target_subjects),
            "train_validation_subject_overlap": len(train_subjects & validation_subjects),
            "exclusion_reasons": dict(sorted(Counter(
                row["exclusion_reason"] for row in by_role["excluded"]).items())),
        }
    return assignments, summary
