"""Refit and evaluate one paired, patient-bootstrap clinical DM draw.

The target policy and behavior reward model each fit their own preprocessing on
their resampled training events. DM and its observed-reward proxy use exactly
the same resampled target-validation event distribution. No patient means,
prediction clipping, behavior policy refitting, or rare-action redrawing occur.
"""
from __future__ import annotations

import math
from numbers import Integral

try:
    import numpy as np
except ImportError:
    np = None

from april_repro.clinical_models import fit_policy, fit_reward
from april_repro.cluster_bootstrap import DEFAULT_SEED, POPULATIONS
from april_repro.cohort_splits import ACTIONS


RULE_VERSION = "clinical-dm-bootstrap-draw-v1"


def _usable_policy(model, state):
    converged = getattr(model, "converged", state.get("metadata", {}).get("converged", state.get("converged")))
    return model.status == "complete" and (converged is True or
                                            (converged is None and state.get("link") == "constant"))


def _action_counts(values, task):
    return {str(action): int(np.count_nonzero(values == action)) for action in ACTIONS[task]}


def _diagnostics(payload):
    result = {}
    policy, reward = payload["target_policy"], payload["reward_model"]
    if policy is not None:
        meta = policy["metadata"]
        result["target_policy"] = {
            "status": policy["status"], "link": policy["link"],
            "converged": meta.get("converged"), "n_iter": meta.get("n_iter", []),
            "training_rows": meta["training_rows"],
            "missing_training_actions": meta["missing_training_actions"],
            "retained_context_columns": len(policy["preprocessor"]["output_columns"]),
        }
    if reward is not None:
        meta = reward["metadata"]
        result["reward_model"] = {
            "status": reward["status"], "training_rows": meta["training_rows"],
            "rank": meta.get("rank"), "rank_deficient": meta.get("rank_deficient"),
            "constant_action_effect_unidentified": meta.get("constant_action_effect_unidentified"),
            "missing_training_actions": meta["missing_training_actions"],
            "retained_context_columns": len(reward["preprocessor"]["output_columns"]),
        }
    return result


def run_dm_draw(dataset, populations, draw_id, seed=DEFAULT_SEED, batch_size=5000):
    """Return (aggregate record, model-state payload, private ClusterDraw objects).

    Expected model nonconvergence returns a failed record with no numeric OPE
    result fields. Unexpected fitting/transform exceptions propagate to the
    driver's sanitized failure handler. The caller skips splits with an empty
    original population before scheduling; passing one here is an error.
    """
    if np is None:
        raise RuntimeError("Clinical bootstrap requires the declared modeling dependencies")
    if isinstance(batch_size, bool) or not isinstance(batch_size, Integral) or batch_size <= 0:
        raise ValueError("Prediction batch size must be a positive integer")
    if set(populations) != set(POPULATIONS) or dataset.task not in ACTIONS:
        raise ValueError("Bootstrap requires the three declared training/evaluation populations")
    splits = {population.split for population in populations.values()}
    if len(splits) != 1:
        raise ValueError("Bootstrap populations belong to different cohort splits")
    for name, population in populations.items():
        if (population.population != name or population.task != dataset.task
                or population.feature_manifest_sha256 != dataset.provenance.get("manifest_sha256")):
            raise ValueError("Bootstrap population does not match the supplied dataset")
        if population.n_subjects == 0:
            raise ValueError("Original bootstrap population is empty and not estimable")
    split = next(iter(splits))
    draws = {name: populations[name].draw(draw_id, seed=seed) for name in POPULATIONS}
    metadata = {name: draw.metadata for name, draw in draws.items()}
    record = {"rule_version": RULE_VERSION, "task": dataset.task, "split": split,
              "draw_id": int(draw_id), "seed": seed, "population_draw_metadata": metadata}
    payload = {"target_policy": None, "reward_model": None,
               "metadata": {"rule_version": RULE_VERSION, "task": dataset.task, "split": split,
                            "draw_id": int(draw_id), "seed": seed,
                            "population_draw_sha256": {name: draw.draw_sha256 for name, draw in draws.items()},
                            "feature_manifest_sha256": dataset.provenance["manifest_sha256"],
                            "behavior_policy_refitted": False}}

    def fail(reason):
        return dict(record, status="failed", reason=reason, model_diagnostics=_diagnostics(payload)), payload, draws

    train = draws["target_train"].event_indices
    behavior = draws["behavior_train"].event_indices
    evaluation = draws["target_validation"].event_indices
    action_counts = {name: _action_counts(dataset.actions[draw.event_indices], dataset.task)
                     for name, draw in draws.items()}
    record["action_counts"] = action_counts
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=1):
        target_policy = fit_policy(dataset.features[train], dataset.actions[train], dataset.task)
        payload["target_policy"] = target_policy.to_dict()
        if not _usable_policy(target_policy, payload["target_policy"]):
            return fail("target_policy_unavailable_or_not_converged")
        reward_model = fit_reward(dataset.features[behavior], dataset.actions[behavior],
                                  dataset.rewards[behavior], dataset.task)
        payload["reward_model"] = reward_model.to_dict()
        if reward_model.status != "complete":
            return fail("behavior_reward_model_unavailable")
        expected_shape_columns = len(ACTIONS[dataset.task])
        unsupported = np.asarray([action_counts["behavior_train"][str(a)] == 0 for a in ACTIONS[dataset.task]])
        dm_sums, reference_sums, unsupported_sums = [], [], []
        outside = 0
        for start in range(0, len(evaluation), int(batch_size)):
            selected = evaluation[start:start + int(batch_size)]
            values = dataset.features[selected]
            # Each model transforms raw context with its own fitted training state.
            probabilities = np.asarray(target_policy.predict_proba(values), dtype=np.float64)
            predictions = np.asarray(reward_model.predict_action_values(values), dtype=np.float64)
            expected_shape = (len(selected), expected_shape_columns)
            if (probabilities.shape != expected_shape or predictions.shape != expected_shape
                    or not np.isfinite(probabilities).all() or not np.isfinite(predictions).all()):
                return fail("invalid_policy_or_reward_prediction_dimensions_or_values")
            if (np.any((probabilities < 0) | (probabilities > 1))
                    or not np.allclose(probabilities.sum(axis=1), 1, rtol=0, atol=1e-10)):
                return fail("invalid_policy_probabilities")
            expected = (probabilities * predictions).sum(axis=1)
            reference = dataset.rewards[selected]
            if (not np.isfinite(expected).all() or not np.isfinite(reference).all()
                    or np.any((reference < 0) | (reference > 1))):
                return fail("invalid_expected_reward_or_observed_reference")
            dm_sums.append(float(expected.sum()))
            reference_sums.append(float(reference.sum()))
            unsupported_sums.append(float(probabilities[:, unsupported].sum()))
            outside += int(np.count_nonzero((predictions < 0) | (predictions > 1)))
    dm = math.fsum(dm_sums) / len(evaluation)
    reference = math.fsum(reference_sums) / len(evaluation)
    error = dm - reference
    squared = error * error
    if not all(math.isfinite(value) for value in (dm, reference, error, squared)):
        return fail("nonfinite_scalar_ope_result")
    record.update(
        status="complete", reason="", dm_value=dm, observed_reference_value=reference,
        signed_error=error, squared_error=squared, evaluation_events=len(evaluation),
        evaluation_unique_subjects=metadata["target_validation"]["unique_sampled_subjects"],
        model_diagnostics=_diagnostics(payload),
        ols_action_predictions_outside_unit_interval=outside,
        ols_action_prediction_cells=len(evaluation) * len(ACTIONS[dataset.task]),
        ols_predictions_clipped=False,
        target_probability_mass_on_behavior_unseen_actions=math.fsum(unsupported_sums) / len(evaluation),
        d0="resampled_target_validation_empirical_event_distribution",
        reference="same_resampled_target_validation_observed_reward_mean_proxy",
        event_weighting="equal_per_repeated_event",
    )
    return record, payload, draws
