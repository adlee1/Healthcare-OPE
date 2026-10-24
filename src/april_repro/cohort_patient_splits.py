"""Patient-disjoint APRIL subgroup candidates, preserving all eligible events.

Section 3.4, p5 describes disjoint behavior/target sub-cohorts and separates
patients by dosage. The paper does not specify how repeated decisions determine
a patient's group. Here any high dose or any positive disease flag determines
the corresponding patient-level target group. This is a retrospective project
choice, not an inferred decision-time predictor or a recovered author rule.

The event-level v1 module and its artifacts remain unchanged. Its input
validation and global subject_fold are reused before patient roles replace the
event roles. Outcome values never enter the calculation.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from april_repro.cohort_splits import (
    ACTIONS, DEFAULT_SEED, FOLDS, ROLES, SPLITS, build_cohort_splits,
)


RULE_VERSION = "cohort-patient-splits-v1"


def _gender(value):
    if not isinstance(value, str):
        return None
    value = value.strip().upper()
    if value in ("F", "FEMALE"):
        return "F"
    if value in ("M", "MALE"):
        return "M"
    return None


def _flag(value):
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


def _counts(rows, task):
    actions = Counter(r["action"] for r in rows)
    return {
        "events": len(rows),
        "subjects": len({r["subject_id"] for r in rows}),
        "admissions": len({(r["subject_id"], r["hadm_id"]) for r in rows if r["hadm_id"]}),
        "action_distribution": {str(a): actions[a] for a in sorted(actions)},
        "missing_action_support": [a for a in ACTIONS[task] if not actions[a]],
    }


def build_patient_cohort_splits(rows, task, *, seed=DEFAULT_SEED):
    """Return private event assignments and aggregate patient-group summaries.

    Supply ALL eligible decisions in the declared task population together,
    not one admission/bucket at a time. A patient's any-high/any-positive role
    can change when new eligible data are added, so extending the population
    requires regrouping all its decisions. Its subject fold remains unchanged.

    Input fields and validation match build_cohort_splits v1. Missing or
    inconsistent group information only excludes the corresponding split.
    Every event remains in the returned assignments three times.
    """
    rows = list(rows)
    assignments, base = build_cohort_splits(rows, task, seed=seed)
    originals = {str(r["event_id"]): r for r in rows}
    by_subject = defaultdict(list)
    for assignment in assignments:
        if assignment["split"] == "gender":
            original = originals[assignment["event_id"]]
            by_subject[assignment["subject_id"]].append((assignment, original))
    disease = "renal_disease" if task == "potassium" else "cirrhosis"
    low_cutoff = 20 if task == "potassium" else 200
    roles = {}
    for subject, records in by_subject.items():
        gender_values = {_gender(original.get("gender")) for _, original in records}
        if len(gender_values - {None}) > 1:
            gender_role = ("excluded", "conflicting_gender_within_subject")
        elif None in gender_values:
            gender_role = ("excluded", "missing_or_unrecognized_gender_for_subject")
        else:
            gender_role = ("behavior" if gender_values == {"F"} else "target", "")
        disease_values = [_flag(original.get(disease)) for _, original in records]
        if True in disease_values:
            disease_role = ("target", "")
        elif None in disease_values:
            disease_role = ("excluded", "missing_or_unrecognized_" + disease + "_without_positive")
        else:
            disease_role = ("behavior", "")
        dosage_role = ("target" if any(
            validated["action"] > low_cutoff for validated, _ in records) else "behavior", "")
        roles[subject] = {
            "gender": gender_role, "comorbidity": disease_role, "dosage": dosage_role,
        }
    for assignment in assignments:
        role, reason = roles[assignment["subject_id"]][assignment["split"]]
        assignment["cohort_role"] = role
        assignment["exclusion_reason"] = reason
    summary = {
        "rule_version": RULE_VERSION, "task": task,
        "input_events": len(rows), "input_subjects": len(by_subject),
        "assignment_rows": len(assignments),
        "fold_rule": base["fold_rule"], "fold_seed": seed,
        "validation_fraction_nominal": base["validation_fraction_nominal"],
        "role_unit": "subject",
        "grouping_population": "all supplied eligible decisions for the task",
        "patient_group_rules": {
            "gender": "all known and consistent F versus M; unknown or conflict excludes this split",
            "comorbidity": "any positive is target; all known negative is behavior; otherwise excluded",
            "dosage": "any high action is target; otherwise behavior; retain all patient events",
        },
        "all_eligible_events_retained": True,
        "diagnosis_labels_are_retrospective": True,
        "diagnosis_labels_are_predictor_features": False,
        "dosage_group_labels_are_retrospective": True,
        "group_labels_are_predictor_features": False,
        "outcomes_used_for_grouping": False,
        "author_patient_aggregation_recovered": False,
        "models_trained": False,
        "splits": {},
    }
    for split in SPLITS:
        selected = [r for r in assignments if r["split"] == split]
        members = {role: [r for r in selected if r["cohort_role"] == role] for role in ROLES}
        subject_sets = {role: {r["subject_id"] for r in group} for role, group in members.items()}
        if any(subject_sets[left] & subject_sets[right]
               for i, left in enumerate(ROLES) for right in ROLES[i + 1:]):
            raise ValueError("A patient occupies multiple roles within one split")
        train = {r["subject_id"] for r in selected if r["fold"] == "train"}
        validation = {r["subject_id"] for r in selected if r["fold"] == "validation"}
        if train & validation:
            raise ValueError("A patient crosses training and validation")
        groups, empty = {}, []
        for role, group in members.items():
            groups[role] = _counts(group, task)
            groups[role]["folds"] = {}
            for fold in FOLDS:
                subset = [r for r in group if r["fold"] == fold]
                groups[role]["folds"][fold] = _counts(subset, task)
                if role != "excluded" and not subset:
                    empty.append(role + "/" + fold)
        summary["splits"][split] = {
            "groups": groups,
            "behavior_and_target_present": bool(members["behavior"] and members["target"]),
            "empty_model_groups": empty,
            "role_subject_overlap": 0,
            "train_validation_subject_overlap": 0,
            "exclusion_reasons": dict(sorted(Counter(
                r["exclusion_reason"] for r in members["excluded"]).items())),
            "excluded_subjects_by_reason": dict(sorted(Counter(
                roles[subject][split][1] for subject in subject_sets["excluded"]).items())),
        }
        if split == "dosage":
            target_low = [r for r in members["target"] if r["action"] <= low_cutoff]
            summary["splits"][split].update(
                target_low_dose_events=len(target_low),
                target_low_dose_subjects=len({r["subject_id"] for r in target_low}),
                target_low_dose_events_by_fold={
                    fold: sum(r["fold"] == fold for r in target_low) for fold in FOLDS},
                target_high_dose_events=sum(r["action"] > low_cutoff for r in members["target"]),
            )
    return assignments, summary
