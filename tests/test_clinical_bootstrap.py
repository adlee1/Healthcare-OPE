"""Synthetic clinical draw tests with the actual declared fitting backend."""
import hashlib
import json
import unittest
from unittest.mock import Mock, patch

try:
    import numpy as np
    import scipy
    import sklearn
    import threadpoolctl
    BACKEND = True
except ImportError:
    BACKEND = False

from april_repro.clinical_bootstrap import run_dm_draw
from april_repro.clinical_models import PolicyFit, RewardFit, fit_policy, fit_reward
from april_repro.clinical_dataset import FOLD_CODES, ROLE_CODES
from april_repro.cluster_bootstrap import ClusterDraw, POPULATIONS, build_cluster_population
from april_repro.cohort_splits import SPLITS
from april_repro.decision_features import FEATURES


class Dataset:
    def __init__(self):
        self.task = "potassium"
        self.subject_ids = np.asarray([10, 20, 20, 30, 30, 30, 40, 40, 50, 60, 60, 60,
                                      70, 80, 80, 90, 90, 90], dtype=np.int64)
        n = len(self.subject_ids)
        self.event_ids = tuple(hashlib.sha256(("synthetic-draw-" + str(i)).encode()).hexdigest() for i in range(n))
        self.features = np.ones((n, 15), dtype=np.float64)
        self.features[:, 0] = np.arange(1, n + 1)
        self.features[:, 1] = 0
        self.features[:, 10:] = 0
        self.features[::5, 2] = np.nan
        self.actions = np.asarray([0, 10, 20, 40, 0, 20, 0, 10, 20, 40, 0, 40,
                                   0, 10, 20, 40, 0, 20], dtype=np.float64)
        self.rewards = 0.1 + np.arange(n, dtype=np.float64) * 0.02
        self.rewards[12:] = [0.2, 0.8, 0.8, 0.9, 0.9, 0.9]
        self.roles = np.full((n, 3), ROLE_CODES["target"], dtype=np.int8)
        self.roles[:6] = ROLE_CODES["behavior"]
        self.folds = np.zeros(n, dtype=np.int8)
        self.folds[12:] = FOLD_CODES["validation"]
        self.provenance = {"manifest_sha256": hashlib.sha256(b"synthetic-model-draw").hexdigest()}

    def mask(self, split, role, fold=None):
        result = self.roles[:, SPLITS.index(split)] == ROLE_CODES[role]
        return result if fold is None else result & (self.folds == FOLD_CODES[fold])


class FixedPopulation:
    """Only synthetic tests supply known cluster multiplicities."""
    def __init__(self, original, counts):
        self.original = original
        self.counts = np.asarray(counts, dtype=np.int64)

    def __getattr__(self, name):
        return getattr(self.original, name)

    def draw(self, draw_id, *, seed):
        template = self.original.draw(draw_id, seed=seed)
        indices = self.original.indices_from_counts(self.counts)
        metadata = dict(template.metadata, sampled_events=len(indices),
                        unique_sampled_subjects=int(np.count_nonzero(self.counts)),
                        draw_sha256=hashlib.sha256(self.counts.tobytes()).hexdigest())
        return ClusterDraw(indices, self.original.subject_ids, self.counts, metadata)


@unittest.skipUnless(BACKEND, "Declared NumPy/scipy/scikit-learn backend is not installed")
class ClinicalBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.dataset = Dataset()

    def populations(self, counts=None):
        values = {name: build_cluster_population(self.dataset, "gender", name) for name in POPULATIONS}
        if counts is not None:
            values = {name: FixedPopulation(pop, counts.get(name, [1, 1, 1])) for name, pop in values.items()}
        return values

    def test_success_reconstructs_dm_from_saved_models_and_same_evaluation(self):
        record, payload, draws = run_dm_draw(self.dataset, self.populations(), 7, batch_size=2)
        self.assertEqual(record["status"], "complete")
        policy = PolicyFit.from_dict(payload["target_policy"])
        reward = RewardFit.from_dict(payload["reward_model"])
        indices = draws["target_validation"].event_indices
        x = self.dataset.features[indices]
        expected = float((policy.predict_proba(x) * reward.predict_action_values(x)).sum(axis=1).mean())
        reference = float(self.dataset.rewards[indices].mean())
        self.assertAlmostEqual(record["dm_value"], expected, places=13)
        self.assertAlmostEqual(record["observed_reference_value"], reference, places=13)
        self.assertAlmostEqual(record["signed_error"], expected - reference, places=13)
        self.assertAlmostEqual(record["squared_error"], (expected - reference) ** 2, places=13)
        self.assertEqual(record["evaluation_events"], len(indices))
        self.assertEqual(record["population_draw_metadata"]["target_validation"], draws["target_validation"].metadata)
        self.assertFalse(payload["metadata"]["behavior_policy_refitted"])
        json.dumps(record, allow_nan=False)
        json.dumps(payload, allow_nan=False)

    def test_unequal_clusters_use_repeated_event_mean_not_patient_mean(self):
        counts = {"target_validation": [2, 0, 1]}
        record, _, draws = run_dm_draw(self.dataset, self.populations(counts), 0)
        self.assertEqual(len(draws["target_validation"].event_indices), 5)
        self.assertAlmostEqual(record["observed_reference_value"], (0.2 * 2 + 0.9 * 3) / 5)
        self.assertNotAlmostEqual(record["observed_reference_value"], (0.2 * 2 + 0.9) / 3)

    def test_sodium_uses_all_six_paper_action_columns_with_missing_actions(self):
        self.dataset.task = "sodium"
        mapping = {0: 0, 10: 100, 20: 200, 40: 500}
        self.dataset.actions = np.asarray([mapping[int(a)] for a in self.dataset.actions], dtype=float)
        record, payload, draws = run_dm_draw(self.dataset, self.populations({}), 0)
        self.assertEqual(record["status"], "complete")
        self.assertEqual(payload["target_policy"]["actions"], [0, 100, 200, 300, 400, 500])
        self.assertEqual(record["ols_action_prediction_cells"], len(draws["target_validation"].event_indices) * 6)
        self.assertEqual(record["action_counts"]["target_train"]["400"], 0)
        self.assertEqual(record["action_counts"]["behavior_train"]["300"], 0)

    def test_each_model_refits_preprocessing_on_its_resampled_train_only(self):
        counts = {"target_train": [3, 0, 0], "behavior_train": [0, 3, 0]}
        self.dataset.features[12:, 0] = 1000
        record, payload, draws = run_dm_draw(self.dataset, self.populations(counts), 0)
        self.assertEqual(record["status"], "complete")
        for model_name, population in (("target_policy", "target_train"), ("reward_model", "behavior_train")):
            indices = draws[population].event_indices
            state = payload[model_name]["preprocessor"]
            self.assertEqual(state["training_rows"], len(indices))
            self.assertEqual(state["statistics"][0]["name"], FEATURES[0])
            self.assertEqual(state["statistics"][0]["impute"], float(np.median(self.dataset.features[indices, 0])))
            self.assertLess(state["statistics"][0]["impute"], 1000)
        self.assertNotEqual(payload["target_policy"]["preprocessor"]["statistics"][0]["impute"],
                            payload["reward_model"]["preprocessor"]["statistics"][0]["impute"])

    def test_no_behavior_clone_and_one_reward_fit(self):
        with patch("april_repro.clinical_bootstrap.fit_policy", wraps=fit_policy) as policy_call, \
             patch("april_repro.clinical_bootstrap.fit_reward", wraps=fit_reward) as reward_call:
            record, _, _ = run_dm_draw(self.dataset, self.populations(), 0)
        self.assertEqual(record["status"], "complete")
        self.assertEqual(policy_call.call_count, 1)
        self.assertEqual(reward_call.call_count, 1)

    def test_constant_policy_and_missing_actions_are_accepted_without_redraw(self):
        self.dataset.actions[6:12] = 0
        self.dataset.actions[:6] = 20
        record, payload, draws = run_dm_draw(self.dataset, self.populations(), 0)
        self.assertEqual(record["status"], "complete")
        self.assertEqual(payload["target_policy"]["link"], "constant")
        self.assertIsNone(payload["target_policy"]["metadata"]["converged"])
        self.assertEqual(payload["target_policy"]["metadata"]["missing_training_actions"], [10, 20, 40])
        self.assertTrue(record["model_diagnostics"]["reward_model"]["constant_action_effect_unidentified"])
        self.assertEqual(record["target_probability_mass_on_behavior_unseen_actions"], 1)
        self.assertTrue(all(draw.metadata["redraws"] == 0 for draw in draws.values()))

    def test_policy_nonconvergence_retains_model_and_omits_numeric_result(self):
        model = fit_policy(self.dataset.features[6:12], self.dataset.actions[6:12], "potassium")
        state = model.to_dict()
        state["metadata"]["converged"] = False
        with patch("april_repro.clinical_bootstrap.fit_policy", return_value=PolicyFit.from_dict(state)), \
             patch("april_repro.clinical_bootstrap.fit_reward") as reward_call:
            record, payload, draws = run_dm_draw(self.dataset, self.populations(), 0)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["reason"], "target_policy_unavailable_or_not_converged")
        self.assertNotIn("dm_value", record)
        self.assertNotIn("observed_reference_value", record)
        self.assertNotIn("squared_error", record)
        self.assertEqual(payload["target_policy"], state)
        self.assertIsNone(payload["reward_model"])
        self.assertEqual(reward_call.call_count, 0)
        self.assertEqual(set(draws), set(POPULATIONS))

    def test_reward_unavailable_is_failed_with_both_fitted_states(self):
        empty = fit_reward(np.empty((0, 15)), np.empty(0), np.empty(0), "potassium")
        with patch("april_repro.clinical_bootstrap.fit_reward", return_value=empty):
            record, payload, _ = run_dm_draw(self.dataset, self.populations(), 0)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["reason"], "behavior_reward_model_unavailable")
        self.assertIsNotNone(payload["target_policy"])
        self.assertEqual(payload["reward_model"]["status"], "not_estimable")
        self.assertNotIn("signed_error", record)

    def test_empty_original_population_rejected_before_training(self):
        self.dataset.folds[:] = 0
        with patch("april_repro.clinical_bootstrap.fit_policy") as call, self.assertRaisesRegex(ValueError, "empty"):
            run_dm_draw(self.dataset, self.populations(), 0)
        self.assertEqual(call.call_count, 0)

    def test_invalid_probability_does_not_return_partial_numeric_result(self):
        def invalid(model, values):
            result = np.zeros((len(values), 4))
            result[:, 0] = 2
            return result
        with patch.object(PolicyFit, "predict_proba", invalid):
            record, payload, _ = run_dm_draw(self.dataset, self.populations(), 0)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["reason"], "invalid_policy_probabilities")
        self.assertNotIn("dm_value", record)
        self.assertIsNotNone(payload["reward_model"])

    def test_ols_predictions_are_counted_outside_range_and_never_clipped(self):
        self.dataset.rewards[:6] = self.dataset.features[:6, 0] * 0.1
        self.dataset.features[12:, 0] = np.arange(100, 106)
        record, _, _ = run_dm_draw(self.dataset, self.populations({}), 0)
        self.assertEqual(record["status"], "complete")
        self.assertGreater(record["dm_value"], 1)
        self.assertEqual(record["ols_action_predictions_outside_unit_interval"], record["ols_action_prediction_cells"])
        self.assertFalse(record["ols_predictions_clipped"])

    def test_prediction_batch_size_changes_neither_population_nor_estimator(self):
        populations = self.populations({"target_validation": [2, 0, 1]})
        first, _, draws1 = run_dm_draw(self.dataset, populations, 3, batch_size=1)
        second, _, draws2 = run_dm_draw(self.dataset, populations, 3, batch_size=5000)
        for field in ("dm_value", "observed_reference_value", "signed_error", "squared_error"):
            self.assertAlmostEqual(first[field], second[field], places=13)
        self.assertEqual(first["evaluation_events"], second["evaluation_events"])
        for name in POPULATIONS:
            np.testing.assert_array_equal(draws1[name].patient_counts, draws2[name].patient_counts)

    def test_mixed_input_populations_and_invalid_batches_rejected(self):
        for batch in (0, -1, 0.5, True):
            with self.subTest(batch=batch), self.assertRaises(ValueError):
                run_dm_draw(self.dataset, self.populations(), 0, batch_size=batch)
        populations = self.populations()
        populations.pop("target_train")
        with self.assertRaises(ValueError):
            run_dm_draw(self.dataset, populations, 0)
        populations = self.populations()
        self.dataset.provenance["manifest_sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "supplied dataset"):
            run_dm_draw(self.dataset, populations, 0)

    def test_unexpected_fit_exception_propagates_to_driver(self):
        with patch("april_repro.clinical_bootstrap.fit_policy", side_effect=RuntimeError("synthetic fit exception")):
            with self.assertRaises(RuntimeError):
                run_dm_draw(self.dataset, self.populations(), 0)


if __name__ == "__main__":
    unittest.main()
