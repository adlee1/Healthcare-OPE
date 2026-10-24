"""Local DM+ point bridge for validated LLM review-pilot annotations.

This uses the adopted G3 numeric dose design and original behavior-training
preprocessing. It reuses the saved target policy and evaluation distribution.
It does not run bootstrap or claim the paper's 500-annotation comparison.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

from april_repro.clinical_models import RewardFit
from april_repro.cohort_splits import ACTIONS, SPLITS
from april_repro.llm_run_summary import SUMMARY_VERSION, _packet, summarize_runs
from april_repro.rewards import reward_from_lab

RULE_VERSION = "clinical-dmplus-point-pilot-v1"


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class AnnotationEvidence:
    summary: dict
    annotations: tuple[dict, ...]
    requests: dict
    provenance: dict


@dataclass(frozen=True)
class Counterfactual:
    request_id: str
    event_id: str
    event_index: int
    action: int
    reward: float
    model_key: str
    protocol_id: str


def load_verified_annotations(summary_directory):
    """Recreate the saved summary from packet/attempt raw evidence, offline.

    A JSONL plus an updated local checksum is insufficient: source requests,
    raw provider replies, receipts, retry chains, and the saved summary must
    agree with the existing collector's independent normalization.
    """
    folder = Path(summary_directory).resolve()
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    if (manifest.get("status") != "complete" or manifest.get("scope") != "offline_review_pilot"
            or manifest.get("summary_version") != SUMMARY_VERSION):
        raise ValueError("Expected a complete pilot annotation summary artifact")
    outputs = manifest.get("outputs", {})
    if set(outputs) != {"summary.json", "parsed-annotations.jsonl"}:
        raise ValueError("Annotation summary output set mismatch")
    for name, digest in outputs.items():
        if file_sha256(folder / name) != digest:
            raise ValueError("Annotation summary output hash mismatch")
    saved = json.loads((folder / "summary.json").read_bytes())
    saved_rows = [json.loads(line) for line in (folder / "parsed-annotations.jsonl").read_bytes().splitlines()]
    packet_paths = [item["directory"] for item in saved["packets"]]
    run_paths = [item["directory"] for item in saved["runs"]]
    reproduced, annotations = summarize_runs(packet_paths, run_paths)
    if reproduced != saved or annotations != saved_rows:
        raise ValueError("Saved annotation summary differs from verified raw source evidence")
    requests = {}
    for item in reproduced["packets"]:
        _, digest, rows, _ = _packet(item["directory"])
        if digest != item["manifest_sha256"] or set(rows) & set(requests):
            raise ValueError("Annotation packet identity changed during verification")
        requests.update(rows)
    return AnnotationEvidence(reproduced, tuple(annotations), requests,
        {"summary_directory": str(folder), "summary_manifest_sha256": file_sha256(manifest_path),
         "summary_outputs": outputs, "raw_receipts_revalidated": True,
         "packets": reproduced["packets"], "runs": reproduced["runs"]})


def select_counterfactuals(dataset, evidence, split, model_key, event_index=None):
    """Join one source/split's explicit CF consumers to original training rows."""
    if dataset.task not in ACTIONS or split not in SPLITS:
        raise ValueError("Unknown task or split")
    lookup = event_index if event_index is not None else {event: i for i, event in enumerate(dataset.event_ids)}
    behavior = dataset.mask(split, "behavior", "train")
    selected, requested, invalid, missing = [], 0, 0, 0
    protocols, keys = set(), set()
    for row in evidence.annotations:
        if row["task"] != dataset.task or row["model_key"] != model_key or row["mode"] != "counterfactual":
            continue
        consumers = [consumer for consumer in row["consumers"] if consumer["split"] == split]
        if not consumers:
            continue
        if len(consumers) != 1 or consumers[0]["mode"] != "counterfactual" or consumers[0]["fold"] != "train":
            raise ValueError("Invalid counterfactual training consumer")
        requested += 1
        request = evidence.requests[row["request_id"]]
        meta = request["metadata"]
        index = lookup.get(row["event_id"])
        if (meta["input_manifest_sha256"] != dataset.provenance["manifest_sha256"]
                or index is None or not behavior[index]
                or meta["task"] != dataset.task or meta["model_key"] != model_key
                or meta["mode"] != "counterfactual" or meta["event_id"] != row["event_id"]
                or meta["observed_action"] != int(dataset.actions[index])
                or row["action"] != meta["action"] or row["action"] not in ACTIONS[dataset.task]
                or row["action"] == int(dataset.actions[index])
                or row["protocol_id"] != request["protocol_id"]):
            raise ValueError("Counterfactual source, input, event, action, or training membership mismatch")
        key = (row["event_id"], row["action"])
        if key in keys:
            raise ValueError("Duplicate event/action annotation within a single source and split")
        keys.add(key)
        protocols.add(row["protocol_id"])
        if row["missing"] or row["status"] != "valid":
            invalid += 1
            missing += int(row["missing"])
            continue
        parsed = row["parsed_prediction"]
        value = parsed["predicted_lab_value"]
        if (type(value) not in (int, float) or not math.isfinite(value) or value <= 0
                or parsed["status"] != "valid" or parsed["task"] != dataset.task
                or parsed["reward_sigma"] != 2.5):
            raise ValueError("Invalid normalized counterfactual prediction")
        reward = reward_from_lab(value, dataset.task)
        if parsed["reward"] != reward:
            raise ValueError("Counterfactual reward differs from the adopted sigma=2.5 mapping")
        selected.append(Counterfactual(row["request_id"], row["event_id"], index,
            int(row["action"]), reward, model_key, row["protocol_id"]))
    if len(protocols) > 1:
        raise ValueError("One source/split cannot mix annotation protocols")
    selected.sort(key=lambda row: row.request_id)
    return tuple(selected), {"requested_annotations": requested, "valid_annotations": len(selected),
        "invalid_annotations_including_missing": invalid, "missing_annotations": missing,
        "source_model_key": model_key, "annotation_protocol_id": next(iter(protocols), None),
        "annotation_budget_is_pilot": True}


def fit_augmented_reward(dataset, behavior_train, baseline, annotations):
    """Equal-weight factual + CF OLS with the saved factual preprocessor fixed."""
    if not annotations:
        return baseline  # The zero-annotation identity is exact, with no refit.
    if baseline.task != dataset.task or baseline.status != "complete":
        raise ValueError("Augmentation requires an estimable same-task baseline reward model")
    indices = np.flatnonzero(behavior_train)
    if not len(indices) or baseline.metadata["training_rows"] != len(indices):
        raise ValueError("Baseline factual training population mismatch")
    if baseline.preprocessor.to_dict()["training_rows"] != len(indices):
        raise ValueError("Baseline preprocessor training population mismatch")
    cf_indices = np.asarray([row.event_index for row in annotations], dtype=np.int64)
    if np.any(cf_indices < 0) or np.any(cf_indices >= len(dataset.event_ids)) or not behavior_train[cf_indices].all():
        raise ValueError("Augmentation contains an event outside original behavior training")
    if (len({row.request_id for row in annotations}) != len(annotations)
            or len({(row.event_id, row.action) for row in annotations}) != len(annotations)
            or len({(row.model_key, row.protocol_id) for row in annotations}) != 1):
        raise ValueError("Augmentation must contain unique annotations from one source/protocol")
    for row in annotations:
        if (dataset.event_ids[row.event_index] != row.event_id or row.action not in ACTIONS[dataset.task]
                or row.action == dataset.actions[row.event_index]
                or not math.isfinite(row.reward) or not 0 <= row.reward <= 1):
            raise ValueError("Invalid augmentation event/action/reward")
    from sklearn.linear_model import LinearRegression
    from threadpoolctl import threadpool_limits
    context = baseline.preprocessor.transform(dataset.features[indices])
    cf_context = baseline.preprocessor.transform(dataset.features[cf_indices])
    actions = np.concatenate((dataset.actions[indices], [row.action for row in annotations]))
    rewards = np.concatenate((dataset.rewards[indices], [row.reward for row in annotations]))
    design = np.column_stack((np.concatenate((context, cf_context)), actions / max(ACTIONS[dataset.task])))
    estimator = LinearRegression(fit_intercept=True, positive=False)
    with threadpool_limits(limits=1):
        estimator.fit(design, rewards)
    state = baseline.to_dict()
    classes, counts = np.unique(actions.astype(int), return_counts=True)
    state.update(coefficients=estimator.coef_.tolist(), intercept=float(estimator.intercept_), classes=classes.tolist())
    state["metadata"].update(training_rows=len(rewards), factual_training_rows=len(indices),
        annotation_training_rows=len(annotations), training_weights="one per factual or annotation row",
        preprocessing_fit_population="original behavior train only; fixed saved DM preprocessor",
        observed_action_counts={str(a): int(c) for a, c in zip(classes, counts)},
        missing_training_actions=[a for a in ACTIONS[dataset.task] if a not in classes],
        action_varies_in_training=len(classes) >= 2, constant_action_effect_unidentified=len(classes) == 1,
        rank=int(estimator.rank_), singular_values=estimator.singular_.tolist(),
        rank_deficient=int(estimator.rank_) < design.shape[1], dmplus_rule_version=RULE_VERSION)
    return RewardFit(state)


def evaluate_pair(dataset, split, target_policy, baseline, augmented, batch_size=5000):
    """Use exactly one saved target policy/d0 for both OPE point estimates."""
    if type(batch_size) is not int or batch_size <= 0:
        raise ValueError("Prediction batch size must be a positive integer")
    evaluation = dataset.mask(split, "target", "validation")
    indices = np.flatnonzero(evaluation)
    result = {"evaluation_events": len(indices),
        "evaluation_subjects": int(len(np.unique(dataset.subject_ids[indices]))),
        "d0": "target_validation_empirical_event_distribution",
        "reference": "same_target_validation_observed_reward_mean_proxy",
        "dm": None, "dm_plus": None, "observed_reference": None,
        "dm_signed_difference": None, "dm_plus_signed_difference": None,
        "dm_absolute_difference": None, "dm_plus_absolute_difference": None,
        "dm_plus_minus_dm": None, "bootstrap_datasets": 0, "rmse": None,
        "standard_error": None, "p_value": None}
    if not len(indices):
        return dict(result, status="not_estimable", reason="empty_target_validation")
    policy_state = target_policy.to_dict()
    usable = target_policy.status == "complete" and (target_policy.converged is True or
        (target_policy.converged is None and policy_state["link"] == "constant"))
    if not usable or baseline.status != "complete" or augmented.status != "complete":
        return dict(result, status="not_estimable", reason="dependent_model_unavailable_or_not_converged")
    if any(model.task != dataset.task for model in (target_policy, baseline, augmented)):
        raise ValueError("Evaluation model task mismatch")
    sums = {"dm": [], "dm_plus": [], "reference": []}
    outside = {"dm": 0, "dm_plus": 0}
    for start in range(0, len(indices), batch_size):
        selected = indices[start:start + batch_size]
        values = dataset.features[selected]
        probabilities = target_policy.predict_proba(values)
        expected_shape = (len(selected), len(ACTIONS[dataset.task]))
        if (probabilities.shape != expected_shape or not np.isfinite(probabilities).all()
                or np.any((probabilities < 0) | (probabilities > 1))
                or not np.allclose(probabilities.sum(axis=1), 1, rtol=0, atol=1e-10)):
            raise ValueError("Invalid fixed target policy probabilities")
        for label, model in (("dm", baseline), ("dm_plus", augmented)):
            predicted = model.predict_action_values(values)
            if predicted.shape != expected_shape or not np.isfinite(predicted).all():
                raise ValueError("Invalid reward action prediction")
            sums[label].append(float((probabilities * predicted).sum(axis=1).sum()))
            outside[label] += int(np.count_nonzero((predicted < 0) | (predicted > 1)))
        sums["reference"].append(float(dataset.rewards[selected].sum()))
    dm, plus, reference = (math.fsum(sums[key]) / len(indices) for key in ("dm", "dm_plus", "reference"))
    if not all(math.isfinite(v) for v in (dm, plus, reference)):
        raise ValueError("Nonfinite OPE point estimate")
    return dict(result, status="estimated", reason="", dm=dm, dm_plus=plus, observed_reference=reference,
        dm_signed_difference=dm-reference, dm_plus_signed_difference=plus-reference,
        dm_absolute_difference=abs(dm-reference), dm_plus_absolute_difference=abs(plus-reference),
        dm_plus_minus_dm=plus-dm, ols_predictions_outside_unit_interval=outside,
        ols_predictions_clipped=False, target_policy_refitted=False)


def verify_saved_dm(result, saved):
    """Reject a changed target policy, evaluation population, or baseline value."""
    if result["status"] != saved["status"] or result["evaluation_events"] != saved["evaluation_events"]:
        raise ValueError("Replayed DM status or evaluation population differs from saved baseline")
    if result["status"] == "estimated":
        for key in ("dm", "observed_reference"):
            if not math.isclose(result[key], saved[key], rel_tol=0, abs_tol=1e-12):
                raise ValueError("Replayed DM value differs from saved baseline")
    elif result["reason"] != saved["reason"]:
        raise ValueError("Replayed DM non-estimability differs from saved baseline")
    return {"baseline_point_verified": True, "absolute_tolerance": 1e-12,
        "dm_exactly_equal": result["dm"] == saved["dm"],
        "observed_reference_exactly_equal": result["observed_reference"] == saved["observed_reference"]}
