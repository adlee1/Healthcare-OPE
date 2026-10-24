"""Synthetic checks for clinical model inputs, train-only transforms and JSON replay."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import warnings

AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "scipy", "sklearn", "threadpoolctl"))
if AVAILABLE:
    import numpy as np
else:
    np = None

STAGE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("april_repro.clinical_models_tested", STAGE / "src/april_repro/clinical_models.py")
models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models)


def context(n):
    return np.full((n, len(models.FEATURES)), np.nan, dtype=np.float64)


@unittest.skipUnless(AVAILABLE, "Optional pinned modeling dependencies are not installed")
class ClinicalModelTests(unittest.TestCase):
    def test_training_median_population_scale_and_binary_tie_rule(self):
        X = context(3)
        X[:, 0] = [20, 40, np.nan]
        X[:, 1] = [0, 1, np.nan]
        X[:, -1] = [1, 0, np.nan]
        X[:, 2] = [60, 60, np.nan]
        original = X.copy()
        processor = models.fit_preprocessor(X)
        state = processor.to_dict()
        self.assertEqual(processor.columns, ("age", "gender", "administered_insulin"))
        self.assertEqual(state["statistics"][0]["impute"], 30)
        self.assertEqual(state["statistics"][0]["mean"], 30)
        self.assertAlmostEqual(state["statistics"][0]["scale"], np.sqrt(200/3))
        self.assertEqual(state["statistics"][1]["impute"], 0)
        self.assertEqual(state["statistics"][2]["omitted_reason"], "constant_after_training_imputation")
        self.assertEqual(state["statistics"][3]["omitted_reason"], "all_missing_in_training")
        np.testing.assert_allclose(processor.transform(X), [[-np.sqrt(1.5), 0, 1], [np.sqrt(1.5), 1, 0], [0, 0, 0]])
        np.testing.assert_equal(X, original)

    def test_evaluation_cannot_fit_statistics_or_restore_omitted_columns(self):
        X = context(3)
        X[:, 0] = [20, 40, np.nan]
        X[:, 1] = 0
        processor = models.fit_preprocessor(X)
        original = processor.to_dict()
        evaluation = context(2)
        evaluation[:, 0] = [1000, np.nan]
        evaluation[:, 1] = 1  # Valid globally, absent in this training subset.
        evaluation[:, 2] = [50, 90]  # This column was entirely absent in training.
        result = processor.transform(evaluation)
        self.assertEqual(result.shape, (2, 1))
        self.assertAlmostEqual(result[0, 0], (1000-30)/np.sqrt(200/3))
        self.assertEqual(result[1, 0], 0)
        self.assertEqual(processor.to_dict(), original)
        roundtrip = models.Preprocessor.from_dict(json.loads(json.dumps(original, allow_nan=False)))
        np.testing.assert_array_equal(roundtrip.transform(evaluation), result)

    def test_invalid_values_rejected_even_in_omitted_features(self):
        processor = models.fit_preprocessor(context(2))
        for index, value in ((0, 0), (0, -1), (0, np.inf), (1, 2), (10, -1), (14, 0.3)):
            X = context(1)
            X[0, index] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                processor.transform(X)
            with self.assertRaises(ValueError):
                models.fit_preprocessor(X)
        for X in (np.ones((3, 14)), np.ones((3, 16)), np.ones((3, 15), dtype=bool), np.array([[{}]*15], dtype=object)):
            with self.assertRaises(ValueError):
                models.fit_preprocessor(X)

    def test_policy_binary_and_multiclass_probabilities_match_sklearn(self):
        from sklearn.linear_model import LogisticRegression
        from threadpoolctl import threadpool_limits
        X = context(12)
        X[:, 0] = np.arange(20, 32)
        X[:, 1] = np.arange(12) % 2
        for y in (np.array([0, 20]*6), np.array([0, 20, 40]*4)):
            fitted = models.fit_policy(X, y, "potassium")
            Z = fitted.preprocessor.transform(X)
            with threadpool_limits(limits=1):
                oracle = LogisticRegression(**models.POLICY_PARAMETERS).fit(Z, y)
            actual = fitted.predict_proba(X)
            self.assertEqual(actual.shape, (12, 4))
            np.testing.assert_allclose(actual.sum(axis=1), 1, atol=1e-14)
            self.assertTrue(np.all(actual[:, 1] == 0))  # 10 never appears in training.
            positions = [models.ACTIONS["potassium"].index(int(a)) for a in oracle.classes_]
            np.testing.assert_allclose(actual[:, positions], oracle.predict_proba(Z), atol=1e-14)
            replay = models.PolicyFit.from_dict(json.loads(json.dumps(fitted.to_dict(), allow_nan=False)))
            np.testing.assert_array_equal(replay.predict_proba(X), actual)
            self.assertTrue(fitted.converged)
            self.assertTrue(fitted.n_iter)

    def test_no_context_multiclass_is_exact_empirical_intercept_policy(self):
        X = context(4)
        fitted = models.fit_policy(X, np.array([0, 0, 100, 500]), "sodium")
        expected = np.array([[0.5, 0.25, 0, 0, 0, 0.25]]*4)
        np.testing.assert_array_equal(fitted.predict_proba(X), expected)
        self.assertEqual(fitted.metadata["fitting_method"], "intercept_only_class_frequency_multinomial_MLE")
        self.assertTrue(fitted.converged)
        self.assertEqual(fitted.n_iter, ())
        replay = models.PolicyFit.from_dict(json.loads(json.dumps(fitted.to_dict())))
        np.testing.assert_array_equal(replay.predict_proba(X), expected)

    def test_single_class_and_empty_training_are_explicit(self):
        X = context(3)
        fitted = models.fit_policy(X, np.array([40, 40, 40]), "potassium")
        np.testing.assert_array_equal(fitted.predict_proba(X), [[0, 0, 0, 1]]*3)
        self.assertEqual(fitted.metadata["fitting_method"], "constant_single_observed_class")
        self.assertIsNone(fitted.converged)
        for fitted in (models.fit_policy(context(0), np.array([]), "sodium"),
                       models.fit_reward(context(0), np.array([]), np.array([]), "sodium")):
            self.assertEqual(fitted.status, "not_estimable")
            self.assertEqual(fitted.metadata["reason"], "empty_training_set")
            json.dumps(fitted.to_dict(), allow_nan=False)
            with self.assertRaises(ValueError):
                fitted.preprocessor.transform(X)

    def test_known_linear_reward_solution_and_counterfactual_action_order(self):
        X = context(8)
        X[:, 0] = [20, 30, 20, 30, 20, 30, 20, 30]
        actions = np.repeat([0, 10, 20, 40], 2)
        standardized_age = (X[:, 0]-25)/5
        rewards = 0.4 + 0.1*standardized_age + 0.2*actions/40
        fitted = models.fit_reward(X, actions, rewards, "potassium")
        state = fitted.to_dict()
        np.testing.assert_allclose(state["coefficients"], [0.1, 0.2], atol=1e-14)
        self.assertAlmostEqual(state["intercept"], 0.4)
        np.testing.assert_allclose(fitted.predict(X, actions), rewards, atol=1e-14)
        expected = 0.4 + 0.1*standardized_age[:, None] + 0.2*np.array([0, 10, 20, 40])[None, :]/40
        np.testing.assert_allclose(fitted.predict_action_values(X), expected, atol=1e-14)
        self.assertEqual(state["metadata"]["rank"], 2)
        self.assertFalse(state["metadata"]["rank_deficient"])
        replay = models.RewardFit.from_dict(json.loads(json.dumps(state, allow_nan=False)))
        np.testing.assert_array_equal(replay.predict_action_values(X), fitted.predict_action_values(X))

    def test_rank_deficiency_and_constant_action_are_recorded_without_omission(self):
        X = context(4)
        X[:, 0] = [20, 30, 40, 50]
        X[:, 2] = [40, 60, 80, 100]  # Exactly collinear after scaling.
        fitted = models.fit_reward(X, np.array([20]*4), np.array([0.1, 0.3, 0.5, 0.7]), "potassium")
        state = fitted.to_dict()
        self.assertTrue(fitted.metadata["rank_deficient"])
        self.assertFalse(fitted.metadata["action_varies_in_training"])
        self.assertTrue(fitted.metadata["constant_action_effect_unidentified"])
        self.assertTrue(fitted.metadata["action_column_retained"])
        self.assertEqual(state["metadata"]["design_columns"][-1], "action_over_maximum")
        self.assertEqual(len(state["coefficients"]), 3)
        self.assertEqual(len(state["metadata"]["singular_values"]), 3)
        np.testing.assert_allclose(fitted.predict(X, np.array([20]*4)), [0.1, 0.3, 0.5, 0.7], atol=1e-14)

    def test_reward_predictions_are_not_clipped(self):
        X = context(2)
        X[:, 0] = [20, 30]
        fitted = models.fit_reward(X, np.array([0, 0]), np.array([0.2, 0.8]), "potassium")
        future = context(1)
        future[:, 0] = 50
        self.assertGreater(fitted.predict(future, np.array([40]))[0], 1)

    def test_invalid_targets_or_tasks_are_rejected(self):
        X = context(2)
        for actions, rewards, task in (([0, 99], [0, 1], "potassium"), ([0], [0, 1], "potassium"),
                                      ([0, 10], [0, 2], "potassium"), ([0, 10], [0, np.nan], "potassium"),
                                      ([0, 10], [0, 1], "unknown")):
            with self.subTest(task=task, actions=actions), self.assertRaises(ValueError):
                models.fit_reward(X, np.asarray(actions), np.asarray(rewards), task)

    def test_convergence_warning_is_recorded_without_changing_parameters(self):
        from sklearn.linear_model import LogisticRegression
        from sklearn.exceptions import ConvergenceWarning
        original = LogisticRegression.fit
        def forced_warning(estimator, *args, **kwargs):
            result = original(estimator, *args, **kwargs)
            warnings.warn("synthetic convergence warning", ConvergenceWarning)
            return result
        X = context(4)
        X[:, 0] = [20, 30, 40, 50]
        with mock.patch.object(LogisticRegression, "fit", forced_warning):
            fitted = models.fit_policy(X, np.array([0, 20, 0, 20]), "potassium")
        self.assertFalse(fitted.converged)
        self.assertIn("ConvergenceWarning", fitted.metadata["warning_categories"])
        self.assertEqual(fitted.metadata["parameters"], models.POLICY_PARAMETERS)
        self.assertNotIn("synthetic convergence warning", json.dumps(fitted.to_dict()))

    def test_models_fit_independent_preprocessors_and_reject_reordered_schema(self):
        first, second = context(4), context(4)
        first[:, 0] = [20, 30, 40, 50]
        second[:, 0] = [60, 70, 80, 90]
        policy = models.fit_policy(first, np.array([0, 10, 20, 40]), "potassium")
        reward = models.fit_reward(second, np.array([0, 10, 20, 40]), np.array([0.1, 0.2, 0.3, 0.4]), "potassium")
        self.assertEqual(policy.preprocessor.to_dict()["statistics"][0]["mean"], 35)
        self.assertEqual(reward.preprocessor.to_dict()["statistics"][0]["mean"], 75)
        state = policy.preprocessor.to_dict()
        state["input_columns"].reverse()
        with self.assertRaises(ValueError):
            models.Preprocessor.from_dict(state)


if __name__ == "__main__":
    unittest.main()
