"""Pair DM+ with an already committed patient-bootstrap DM draw.

The fixed annotation cache follows each source behavior patient's *same*
multiplicity as the factual rows. This module performs no I/O or new sampling
experiment: deterministic draw replay verifies the supplied original counts.
The saved factual preprocessor and target policy are never refitted.
"""
from __future__ import annotations

import math
from numbers import Integral

try:
    import numpy as np
except ImportError:
    np = None

from april_repro.clinical_models import PolicyFit, RewardFit
from april_repro.cluster_bootstrap import DEFAULT_SEED, POPULATIONS
from april_repro.cohort_splits import ACTIONS

RULE_VERSION = "clinical-dmplus-paired-bootstrap-draw-v1"
REPLAY_ABSOLUTE_TOLERANCE = 1e-12


def replay_original_draw(dataset, populations, original_record, original_payload, saved_counts):
    """Verify and return the original three ClusterDraw objects.

    ``saved_counts`` contains the six arrays from the original private npz:
    ``<population>_subject_ids`` and ``<population>_patient_counts``. Nothing is
    inferred from a new seed, resampled on failure, or silently realigned.
    """
    if set(populations) != set(POPULATIONS) or dataset.task not in ACTIONS:
        raise ValueError("Pairing requires the three original bootstrap populations")
    if (original_record.get("status") != "complete" or original_record.get("task") != dataset.task
            or original_record.get("seed") != DEFAULT_SEED):
        raise ValueError("Pairing requires a complete same-task original DM draw and seed")
    draw_id, split = original_record.get("draw_id"), original_record.get("split")
    expected_keys = {name + suffix for name in POPULATIONS for suffix in ("_subject_ids", "_patient_counts")}
    if set(saved_counts) != expected_keys:
        raise ValueError("Original saved patient-count array set differs")
    draws = {}
    for name, population in populations.items():
        if (population.population != name or population.task != dataset.task or population.split != split
                or population.feature_manifest_sha256 != dataset.provenance.get("manifest_sha256")
                or not population.n_subjects):
            raise ValueError("Original population identity differs or is not estimable")
        draw = population.draw(draw_id, seed=original_record["seed"])
        counts, subjects = np.asarray(saved_counts[name + "_patient_counts"]), np.asarray(saved_counts[name + "_subject_ids"])
        if (counts.dtype.kind not in "iu" or subjects.dtype.kind not in "iu"
                or not np.array_equal(counts, draw.patient_counts)
                or not np.array_equal(subjects, draw.subject_ids)
                or original_record.get("population_draw_metadata", {}).get(name) != draw.metadata):
            raise ValueError("Original saved patient counts or draw metadata differ from deterministic replay")
        draws[name] = draw
    metadata = original_payload.get("metadata", {})
    expected = {"task": dataset.task, "split": split, "draw_id": draw_id,
                "seed": original_record["seed"],
                "feature_manifest_sha256": dataset.provenance["manifest_sha256"],
                "population_draw_sha256": {name: draw.draw_sha256 for name, draw in draws.items()}}
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("Original model payload does not belong to this paired draw")
    if original_record.get("evaluation_events") != len(draws["target_validation"].event_indices):
        raise ValueError("Original evaluation event count differs from replay")
    for field in ("dm_value", "observed_reference_value", "signed_error", "squared_error"):
        value = original_record.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Original DM draw has a nonfinite result")
    error = original_record["dm_value"] - original_record["observed_reference_value"]
    if (not math.isclose(error, original_record["signed_error"], rel_tol=0, abs_tol=REPLAY_ABSOLUTE_TOLERANCE)
            or not math.isclose(error * error, original_record["squared_error"], rel_tol=0,
                                abs_tol=REPLAY_ABSOLUTE_TOLERANCE)):
        raise ValueError("Original DM error fields are inconsistent")
    return draws


def annotation_multiplicities(dataset, population, draw, annotations):
    """One integer weight per unique cached CF, inherited from its patient."""
    if population.population != "behavior_train" or population.task != dataset.task:
        raise ValueError("Annotations require the original behavior-training population")
    if not np.array_equal(population.subject_ids, draw.subject_ids):
        raise ValueError("Annotation patient count order differs from the original population")
    # Validate even cache rows whose source patient receives zero multiplicity.
    behavior = dataset.mask(population.split, "behavior", "train")
    request_ids, event_actions, protocols = set(), set(), set()
    weights = []
    for row in annotations:
        index = row.event_index
        if (isinstance(index, bool) or not isinstance(index, Integral) or not 0 <= index < len(dataset.event_ids)
                or not behavior[index] or dataset.event_ids[index] != row.event_id
                or row.action not in ACTIONS[dataset.task] or row.action == dataset.actions[index]
                or not math.isfinite(row.reward) or not 0 <= row.reward <= 1):
            raise ValueError("Invalid cached annotation source, membership, action or reward")
        if row.request_id in request_ids or (row.event_id, row.action) in event_actions:
            raise ValueError("Duplicate cached counterfactual annotation")
        request_ids.add(row.request_id)
        event_actions.add((row.event_id, row.action))
        protocols.add((row.model_key, row.protocol_id))
        position = int(np.searchsorted(population.subject_ids, dataset.subject_ids[index]))
        if position >= population.n_subjects or population.subject_ids[position] != dataset.subject_ids[index]:
            raise ValueError("Annotation source patient is absent from behavior training")
        weights.append(int(draw.patient_counts[position]))
    if len(protocols) > 1:
        raise ValueError("Cached annotations mix model sources or protocols")
    return np.asarray(weights, dtype=np.int64)


def fit_paired_augmented_reward(dataset, behavior_indices, baseline, annotations, multiplicities):
    """Actual repeated-row OLS; no Gram approximation or independent CF draw."""
    indices = np.asarray(behavior_indices)
    counts = np.asarray(multiplicities)
    if (indices.ndim != 1 or indices.dtype.kind not in "iu" or not len(indices)
            or np.any(indices < 0) or np.any(indices >= len(dataset.event_ids))
            or counts.shape != (len(annotations),) or counts.dtype.kind not in "iu" or np.any(counts < 0)):
        raise ValueError("Invalid factual indices or annotation multiplicities")
    if (baseline.task != dataset.task or baseline.status != "complete"
            or baseline.metadata["training_rows"] != len(indices)
            or baseline.preprocessor.to_dict()["training_rows"] != len(indices)):
        raise ValueError("Saved factual model does not match this bootstrap training draw")
    expanded = np.repeat(np.arange(len(annotations), dtype=np.int64), counts)
    if not len(expanded):
        return baseline
    from sklearn.linear_model import LinearRegression
    from threadpoolctl import threadpool_limits
    annotation_indices = np.asarray([row.event_index for row in annotations], dtype=np.int64)[expanded]
    cf_actions = np.asarray([row.action for row in annotations], dtype=np.float64)[expanded]
    cf_rewards = np.asarray([row.reward for row in annotations], dtype=np.float64)[expanded]
    context = baseline.preprocessor.transform(dataset.features[indices])
    cf_context = baseline.preprocessor.transform(dataset.features[annotation_indices])
    actions = np.concatenate((dataset.actions[indices], cf_actions))
    rewards = np.concatenate((dataset.rewards[indices], cf_rewards))
    design = np.column_stack((np.concatenate((context, cf_context)), actions / max(ACTIONS[dataset.task])))
    with threadpool_limits(limits=1):
        estimator = LinearRegression(fit_intercept=True, positive=False).fit(design, rewards)
    state = baseline.to_dict()
    classes, action_counts = np.unique(actions.astype(int), return_counts=True)
    state.update(coefficients=estimator.coef_.tolist(), intercept=float(estimator.intercept_), classes=classes.tolist())
    state["metadata"].update(training_rows=len(rewards), factual_training_rows=len(indices),
        annotation_training_rows=len(expanded), unique_cachevalid_annotations=len(annotations),
        draw_annotation_unique=int(np.count_nonzero(counts)),
        training_weights="one per repeated factual or repeated annotation row",
        preprocessing_fit_population="same paired saved DM factual bootstrap draw only",
        observed_action_counts={str(a): int(c) for a, c in zip(classes, action_counts)},
        missing_training_actions=[a for a in ACTIONS[dataset.task] if a not in classes],
        action_varies_in_training=len(classes) >= 2, constant_action_effect_unidentified=len(classes) == 1,
        rank=int(estimator.rank_), singular_values=estimator.singular_.tolist(),
        rank_deficient=int(estimator.rank_) < design.shape[1], dmplus_rule_version=RULE_VERSION)
    return RewardFit.from_dict(state)


def _evaluate(dataset, evaluation, policy, baseline, augmented, batch_size):
    sums = {"dm": [], "plus": [], "reference": []}
    outside = {"dm": 0, "plus": 0}
    for start in range(0, len(evaluation), batch_size):
        selected = evaluation[start:start + batch_size]
        x = dataset.features[selected]
        probabilities = np.asarray(policy.predict_proba(x), dtype=np.float64)
        shape = (len(selected), len(ACTIONS[dataset.task]))
        if (probabilities.shape != shape or not np.isfinite(probabilities).all()
                or np.any((probabilities < 0) | (probabilities > 1))
                or not np.allclose(probabilities.sum(axis=1), 1, rtol=0, atol=1e-10)):
            raise ValueError("Saved target policy has invalid probabilities")
        for name, model in (("dm", baseline), ("plus", augmented)):
            values = np.asarray(model.predict_action_values(x), dtype=np.float64)
            if values.shape != shape or not np.isfinite(values).all():
                raise ValueError("Reward model predictions are invalid")
            sums[name].append(float((probabilities * values).sum(axis=1).sum()))
            outside[name] += int(np.count_nonzero((values < 0) | (values > 1)))
        observed = dataset.rewards[selected]
        if not np.isfinite(observed).all() or np.any((observed < 0) | (observed > 1)):
            raise ValueError("Observed reward proxy is invalid")
        sums["reference"].append(float(observed.sum()))
    values = {name: math.fsum(items) / len(evaluation) for name, items in sums.items()}
    if not all(math.isfinite(value) for value in values.values()):
        raise ValueError("Nonfinite paired OPE result")
    return values, outside


def run_paired_draw(dataset, populations, original_record, original_payload, saved_counts,
                    annotations, *, requested_budget=500, batch_size=5000):
    """Return a DM+-schema aggregate record and its fitted reward state.

    DM+ uses ``dm_value`` so the existing bootstrap statistics record contract
    applies. ``original_dm_value`` retains the paired saved DM result. All
    original draws/counts/models must have been hash verified by the caller.
    Integrity/numerical errors raise ValueError; the driver retains that failed
    draw ID. Budget zero is available for identity tests, not a second run.
    """
    if np is None:
        raise RuntimeError("Paired bootstrap requires the pinned modeling dependencies")
    if type(batch_size) is not int or batch_size <= 0:
        raise ValueError("Prediction batch size must be a positive integer")
    if (type(requested_budget) is not int or not 0 <= requested_budget <= 500
            or len(annotations) > requested_budget):
        raise ValueError("Requested budget must cover the fixed unique annotation cache")
    draws = replay_original_draw(dataset, populations, original_record, original_payload, saved_counts)
    policy = PolicyFit.from_dict(original_payload["target_policy"])
    baseline = RewardFit.from_dict(original_payload["reward_model"])
    if (policy.task != dataset.task or baseline.task != dataset.task or policy.status != "complete"
            or baseline.status != "complete" or not (policy.converged is True
                or (policy.converged is None and original_payload["target_policy"]["link"] == "constant"))):
        raise ValueError("Saved paired policy or reward model is unavailable")
    counts = annotation_multiplicities(dataset, populations["behavior_train"], draws["behavior_train"], annotations)
    augmented = fit_paired_augmented_reward(dataset, draws["behavior_train"].event_indices, baseline, annotations, counts)
    values, outside = _evaluate(dataset, draws["target_validation"].event_indices, policy, baseline, augmented, batch_size)
    for name, original in (("dm", "dm_value"), ("reference", "observed_reference_value")):
        if not math.isclose(values[name], original_record[original], rel_tol=0, abs_tol=REPLAY_ABSOLUTE_TOLERANCE):
            raise ValueError("Replayed saved DM or observed reference differs from original result")
    # Canonical original reference guarantees exact pairing. For no selected CF
    # rows, preserve the saved zero-augmentation identity bit for bit as well.
    reference = original_record["observed_reference_value"]
    plus = original_record["dm_value"] if augmented is baseline else values["plus"]
    error = plus - reference
    record = {"rule_version": RULE_VERSION, "task": dataset.task, "split": original_record["split"],
        "draw_id": original_record["draw_id"], "seed": original_record["seed"], "status": "complete", "reason": "",
        "dm_value": plus, "observed_reference_value": reference, "signed_error": error, "squared_error": error * error,
        "original_dm_value": original_record["dm_value"], "original_dm_signed_error": original_record["signed_error"],
        "dm_plus_minus_dm": plus - original_record["dm_value"],
        "requested_annotation_budget": requested_budget, "unique_cachevalid_annotations": len(annotations),
        "draw_annotation_rows": int(counts.sum()), "draw_annotation_unique": int(np.count_nonzero(counts)),
        "draw_annotation_patient_counts": {str(int(weight)): int(np.count_nonzero(counts == weight))
                                           for weight in np.unique(counts)},
        "annotation_sampling": "same source behavior patient multiplicity; fixed cache; no independent resampling",
        "factual_training_events": len(draws["behavior_train"].event_indices),
        "evaluation_events": len(draws["target_validation"].event_indices),
        "evaluation_unique_subjects": draws["target_validation"].metadata["unique_sampled_subjects"],
        "population_draw_metadata": original_record["population_draw_metadata"],
        "d0": "same_paired_resampled_target_validation_empirical_event_distribution",
        "reference": "same_paired_resampled_target_validation_observed_reward_mean_proxy",
        "event_weighting": "equal_per_repeated_event", "target_policy_refitted": False,
        "factual_preprocessor_refitted": False, "ols_predictions_clipped": False,
        "ols_action_predictions_outside_unit_interval": outside,
        "original_dm_replay_verified": True, "replay_absolute_tolerance": REPLAY_ABSOLUTE_TOLERANCE,
        "original_dm_exactly_equal": values["dm"] == original_record["dm_value"],
        "original_reference_exactly_equal": values["reference"] == reference,
        "zero_selected_annotation_identity": augmented is baseline}
    payload = {"reward_model_plus": augmented.to_dict(), "metadata": {
        "rule_version": RULE_VERSION, "task": dataset.task, "split": original_record["split"],
        "draw_id": original_record["draw_id"], "seed": original_record["seed"],
        "feature_manifest_sha256": dataset.provenance["manifest_sha256"],
        "population_draw_sha256": {name: draw.draw_sha256 for name, draw in draws.items()},
        "source_model_key": annotations[0].model_key if annotations else None,
        "annotation_protocol_id": annotations[0].protocol_id if annotations else None,
        "target_policy_refitted": False, "factual_preprocessor_refitted": False}}
    return record, payload
