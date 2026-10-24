"""Load private treatment features into compact arrays without positional joins.

Only the fifteen declared pretreatment features enter the model matrix. Patient
groups are already represented by splits.csv and are never predictor inputs.
CSV parsing is streaming: the largest Python mapping contains event IDs and
integer array offsets, not patient row dictionaries. Empty features become NaN;
all fitting and imputation remain the responsibility of training-only code.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

try:
    import numpy as np
except ImportError:  # The standard-library foundation suite can still import.
    np = None

from april_repro.cohort_splits import ACTIONS, FOLDS, ROLES, SPLITS, subject_fold
from april_repro.decision_features import FEATURES, IDENTITY, OUTCOMES
from april_repro.rewards import reward_from_lab


ROLE_CODES = {name: index for index, name in enumerate(ROLES)}
FOLD_CODES = {name: index for index, name in enumerate(FOLDS)}
SPLIT_COLUMNS = ("event_id", "subject_id", "hadm_id", "task", "split", "cohort_role",
                 "fold", "action", "exclusion_reason")
OUTPUT_NAMES = {"features.csv", "outcomes.csv", "splits.csv", "groups.csv", "summary.json"}
FEATURE_RULES = {"treatment-features-batched-v1", "treatment-features-scoped-v1"}


@dataclass(frozen=True)
class ClinicalDataset:
    task: str
    event_ids: tuple[str, ...]
    subject_ids: np.ndarray
    hadm_ids: np.ndarray
    features: np.ndarray
    actions: np.ndarray
    post_labs: np.ndarray
    rewards: np.ndarray
    roles: np.ndarray  # N x len(SPLITS), ROLE_CODES
    folds: np.ndarray  # N, FOLD_CODES; globally identical for each subject
    summary: dict
    provenance: dict
    feature_names: tuple[str, ...] = FEATURES
    split_names: tuple[str, ...] = SPLITS

    @property
    def X(self):
        return self.features

    def mask(self, split, role, fold=None):
        """Return one boolean event mask without copying rows or feature data."""
        if split not in SPLITS or role not in ROLE_CODES or (fold is not None and fold not in FOLD_CODES):
            raise ValueError("Unknown split, role, or fold")
        selected = self.roles[:, SPLITS.index(split)] == ROLE_CODES[role]
        if fold is not None:
            selected &= self.folds == FOLD_CODES[fold]
        return selected


def _sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rows(path, columns, expected_hash):
    """Parse and hash the same byte stream, including CSV quoted multiline fields."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        def lines():
            for raw in handle:
                digest.update(raw)
                yield raw.decode("utf-8")
        reader = csv.DictReader(lines())
        header = reader.fieldnames
        if header is None or len(header) != len(set(header)) or set(header) != set(columns):
            raise ValueError("Unexpected columns in " + path.name)
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Malformed CSV row in " + path.name)
            yield row
    if digest.hexdigest() != expected_hash:
        raise ValueError("Output hash mismatch in " + path.name)


def _identifier(value):
    if not re.fullmatch(r"[1-9][0-9]{0,9}", value) or int(value) > 2147483647:
        raise ValueError("Invalid patient or admission identifier")
    return int(value)


def _event(value):
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Invalid decision event identifier")
    return value


def _clock(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("Invalid feature or outcome decision time") from None
    if parsed.tzinfo is not None:
        raise ValueError("Decision time must be timezone-naive")
    return np.datetime64(parsed, "us")


def _finite(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Invalid numeric " + label) from None
    if not math.isfinite(result):
        raise ValueError("Nonfinite " + label)
    return result


def _feature(value, name):
    if value == "":
        return math.nan
    if name == "gender":
        if value not in ("F", "M"):
            raise ValueError("Unknown gender feature encoding")
        return float(value == "M")
    if name in FEATURES[10:]:
        if value not in ("0", "1"):
            raise ValueError("Unknown medication feature encoding")
        return float(value)
    return _finite(value, "feature " + name)


def _action(value, task):
    if value not in {str(action) for action in ACTIONS[task]}:
        raise ValueError("Action outside declared paper support")
    return int(value)


def _count(actual, expected, label):
    if type(expected) is not int or actual != expected:
        raise ValueError("Manifest count mismatch: " + label)


def _check_counts(expected, events, subjects, admissions, actions, task):
    for label, actual in (("events", events), ("subjects", subjects), ("admissions", admissions)):
        _count(int(actual), expected.get(label), "split " + label)
    distribution = {str(a): int(actions[i]) for i, a in enumerate(ACTIONS[task]) if actions[i]}
    if expected.get("action_distribution") != distribution:
        raise ValueError("Manifest split action distribution mismatch")
    if expected.get("missing_action_support") != [a for i, a in enumerate(ACTIONS[task]) if not actions[i]]:
        raise ValueError("Manifest missing action support mismatch")


def load_clinical_dataset(artifact_directory):
    """Load a complete treatment feature artifact; never access DBs or services.

    Feature rows determine array order. Outcomes and all three split assignments
    are joined by event_id and checked against patient/admission identity. Groups
    and summary outputs are hash-checked but groups.csv is never parsed.
    """
    if np is None:
        raise RuntimeError("Clinical model loading requires the declared NumPy dependency")
    directory = Path(artifact_directory).resolve()
    manifest_bytes = (directory / "manifest.json").read_bytes()
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = json.loads(manifest_bytes)
    task, summary = manifest.get("task"), manifest.get("summary")
    if (manifest.get("status") != "complete" or task not in ACTIONS
            or manifest.get("rule_version") not in FEATURE_RULES
            or manifest.get("patient_split_rule_version") != "cohort-patient-splits-v1"
            or not isinstance(summary, dict)):
        raise ValueError("Artifact is not a complete supported patient-split treatment feature run")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != OUTPUT_NAMES:
        raise ValueError("Feature artifact output set is incomplete or unexpected")
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in outputs.values()):
        raise ValueError("Invalid output hash declaration")
    for name in ("groups.csv", "summary.json"):
        if _sha(directory / name) != outputs[name]:
            raise ValueError("Output hash mismatch in " + name)
    if json.loads((directory / "summary.json").read_bytes()) != summary:
        raise ValueError("Summary file and manifest disagree")
    n = summary.get("events")
    if type(n) is not int or n <= 0:
        raise ValueError("Dataset must have a positive declared event count")
    split_summary = summary.get("splits", {})
    if (summary.get("task") != task or summary.get("feature_columns") != list(FEATURES)
            or summary.get("raw_missing_values_preserved") is not True
            or summary.get("imputation_fitted") is not False
            or split_summary.get("task") != task
            or split_summary.get("rule_version") != "cohort-patient-splits-v1"
            or split_summary.get("role_unit") != "subject"):
        raise ValueError("Feature or patient-split declaration mismatch")
    _count(n, manifest.get("completed_events"), "completed events")
    _count(n, split_summary.get("input_events"), "split input events")
    _count(n * len(SPLITS), split_summary.get("assignment_rows"), "split assignment rows")
    seed = split_summary.get("fold_seed")
    if not isinstance(seed, str) or not seed:
        raise ValueError("Missing patient fold seed")

    features = np.empty((n, len(FEATURES)), dtype=np.float64)
    subjects, admissions = np.empty(n, dtype=np.int64), np.empty(n, dtype=np.int64)
    clocks = np.empty(n, dtype="datetime64[us]")
    index, admission_keys, patient_states = {}, set(), {}
    feature_rows = 0
    for i, row in enumerate(_rows(directory / "features.csv", (*IDENTITY, *FEATURES), outputs["features.csv"])):
        if i >= n:
            raise ValueError("More feature rows than declared")
        key = _event(row["event_id"])
        if key in index:
            raise ValueError("Duplicate feature event identifier")
        index[key] = i
        subject, admission = _identifier(row["subject_id"]), _identifier(row["hadm_id"])
        subjects[i], admissions[i] = subject, admission
        admission_keys.add((subject, admission))
        if subject not in patient_states:
            patient_states[subject] = [FOLD_CODES[subject_fold(str(subject), seed=seed)], -1, -1, -1]
        clocks[i] = _clock(row["decision_time"])
        features[i] = [_feature(row[name], name) for name in FEATURES]
        feature_rows += 1
    _count(feature_rows, n, "feature rows")
    _count(len(patient_states), summary.get("subjects"), "subjects")
    _count(len(admission_keys), summary.get("admissions"), "admissions")
    _count(len(patient_states), split_summary.get("input_subjects"), "split input subjects")
    missing = np.isnan(features)
    observed = n - missing.sum(axis=0)
    _count(int((~missing.any(axis=1)).sum()), summary.get("all_features_observed_events"), "complete features")
    del missing
    for j, name in enumerate(FEATURES):
        declared = summary.get("coverage", {}).get(name, {})
        _count(int(observed[j]), declared.get("observed"), "observed " + name)
        _count(n - int(observed[j]), declared.get("missing"), "missing " + name)
        if name in FEATURES[10:]:
            counts = {"0": int((features[:, j] == 0).sum()), "1": int((features[:, j] == 1).sum()),
                      "missing": n - int(observed[j])}
            if declared.get("value_counts") != {key: value for key, value in counts.items() if value}:
                raise ValueError("Manifest medication feature counts mismatch")

    actions, labs, rewards = (np.empty(n, dtype=np.float64) for _ in range(3))
    outcome_seen = np.zeros(n, dtype=bool)

    def joined(row, kind):
        key = row["event_id"]
        i = index.get(key)
        if i is None:
            raise ValueError("Unknown event identifier in " + kind)
        if (_identifier(row["subject_id"]) != subjects[i]
                or _identifier(row["hadm_id"]) != admissions[i]
                or row["task"] != task):
            raise ValueError("Patient, admission, or task mismatch in " + kind)
        return i

    for row in _rows(directory / "outcomes.csv", OUTCOMES, outputs["outcomes.csv"]):
        i = joined(row, "outcomes")
        if outcome_seen[i]:
            raise ValueError("Duplicate outcome event identifier")
        if _clock(row["anchor_time"]) != clocks[i]:
            raise ValueError("Feature and outcome decision times differ")
        action, lab = _action(row["action"], task), _finite(row["post_lab_value"], "post lab")
        if lab <= 0:
            raise ValueError("Post lab must be positive")
        actions[i], labs[i], rewards[i] = action, lab, reward_from_lab(lab, task)
        outcome_seen[i] = True
    if not outcome_seen.all():
        raise ValueError("Missing outcome event identifiers")
    del outcome_seen, clocks

    roles = np.full((n, len(SPLITS)), -1, dtype=np.int8)
    folds = np.full(n, -1, dtype=np.int8)
    event_counts = np.zeros((len(SPLITS), len(ROLES), len(FOLDS)), dtype=np.int64)
    action_counts = np.zeros((*event_counts.shape, len(ACTIONS[task])), dtype=np.int64)
    action_positions = {action: i for i, action in enumerate(ACTIONS[task])}
    assignment_rows = 0
    for row in _rows(directory / "splits.csv", SPLIT_COLUMNS, outputs["splits.csv"]):
        i = joined(row, "splits")
        if row["split"] not in SPLITS or row["cohort_role"] not in ROLE_CODES or row["fold"] not in FOLD_CODES:
            raise ValueError("Unknown split, role, or fold label")
        split = SPLITS.index(row["split"])
        role, fold = ROLE_CODES[row["cohort_role"]], FOLD_CODES[row["fold"]]
        if roles[i, split] != -1:
            raise ValueError("Duplicate event and split assignment")
        action = _action(row["action"], task)
        if action != actions[i]:
            raise ValueError("Split action differs from outcome action")
        if (row["cohort_role"] == "excluded") != bool(row["exclusion_reason"]):
            raise ValueError("Split exclusion reason disagrees with role")
        state = patient_states[int(subjects[i])]
        if fold != state[0] or (folds[i] != -1 and folds[i] != fold):
            raise ValueError("Patient fold leakage or declared fold rule mismatch")
        if state[split + 1] not in (-1, role):
            raise ValueError("Patient occupies multiple roles within a split")
        state[split + 1] = role
        roles[i, split], folds[i] = role, fold
        event_counts[split, role, fold] += 1
        action_counts[split, role, fold, action_positions[action]] += 1
        assignment_rows += 1
    if (roles < 0).any() or (folds < 0).any() or assignment_rows != n * len(SPLITS):
        raise ValueError("Incomplete three-split event coverage")

    subject_counts, admission_counts = np.zeros_like(event_counts), np.zeros_like(event_counts)
    for state in patient_states.values():
        for split, role in enumerate(state[1:]):
            subject_counts[split, role, state[0]] += 1
    for subject, _ in admission_keys:
        state = patient_states[subject]
        for split, role in enumerate(state[1:]):
            admission_counts[split, role, state[0]] += 1
    for s, split in enumerate(SPLITS):
        declared = split_summary.get("splits", {}).get(split, {})
        if declared.get("role_subject_overlap") != 0 or declared.get("train_validation_subject_overlap") != 0:
            raise ValueError("Manifest declares patient overlap")
        for r, role in enumerate(ROLES):
            group = declared.get("groups", {}).get(role, {})
            _check_counts(group, event_counts[s, r].sum(), subject_counts[s, r].sum(),
                          admission_counts[s, r].sum(), action_counts[s, r].sum(axis=0), task)
            for f, fold in enumerate(FOLDS):
                _check_counts(group.get("folds", {}).get(fold, {}), event_counts[s, r, f],
                              subject_counts[s, r, f], admission_counts[s, r, f], action_counts[s, r, f], task)
    if _sha(directory / "manifest.json") != manifest_digest:
        raise ValueError("Manifest changed during dataset loading")
    return ClinicalDataset(
        task=task, event_ids=tuple(index), subject_ids=subjects, hadm_ids=admissions,
        features=features, actions=actions, post_labs=labs, rewards=rewards, roles=roles, folds=folds,
        summary=summary,
        provenance={"artifact_directory": str(directory), "manifest_sha256": manifest_digest,
                    "outputs": dict(outputs), "feature_rule_version": manifest["rule_version"],
                    "patient_split_rule_version": manifest["patient_split_rule_version"],
                    "gender_encoding": {"F": 0, "M": 1}, "missing_encoding": "NaN",
                    "only_declared_fifteen_features": True, "groups_csv_used_as_predictors": False},
    )
