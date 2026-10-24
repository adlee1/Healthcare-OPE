"""Synthetic same-patient CF bootstrap and saved-DM replay checks."""
import copy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import april_repro
STAGE = Path(__file__).resolve().parents[1]
if str(STAGE / "src/april_repro") not in april_repro.__path__:
    april_repro.__path__.insert(0, str(STAGE / "src/april_repro"))

from april_repro import clinical_dmplus_bootstrap as paired
from april_repro.clinical_bootstrap import run_dm_draw
from april_repro.clinical_dmplus import Counterfactual
from april_repro.clinical_models import PolicyFit, RewardFit
from april_repro.cluster_bootstrap import POPULATIONS, build_cluster_population
from test_clinical_bootstrap import Dataset, FixedPopulation

AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "scipy", "sklearn", "threadpoolctl"))
if AVAILABLE:
    import numpy as np


@unittest.skipUnless(AVAILABLE, "Pinned numerical dependencies unavailable")
class ClinicalDMPlusBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.data = Dataset()
        raw = {name: build_cluster_population(self.data, "gender", name) for name in POPULATIONS}
        self.populations = {name: FixedPopulation(pop, [2, 0, 1] if name == "behavior_train" else [1, 1, 1])
                            for name, pop in raw.items()}
        self.old, self.old_models, self.draws = run_dm_draw(self.data, self.populations, 7)
        self.saved = {name + suffix: getattr(draw, attr).copy()
            for name, draw in self.draws.items()
            for suffix, attr in (("_subject_ids", "subject_ids"), ("_patient_counts", "patient_counts"))}
        # First two are source patient10 (multiplicity2) and20 (multiplicity0).
        # Last two share patient30 and retain the same multiplicity1.
        self.annotations = tuple(Counterfactual("request" + str(i), self.data.event_ids[i], i,
            40 if self.data.actions[i] != 40 else 10, .83 + i * .01, "deepseek", "protocol1")
            for i in (0, 1, 3, 4))

    def execute(self, annotations=None, **kwargs):
        return paired.run_paired_draw(self.data, self.populations, self.old, self.old_models,
            self.saved, self.annotations if annotations is None else annotations, **kwargs)

    def test_cf_follows_patient_multiplicity_and_no_redraw_or_policy_fit(self):
        with patch("april_repro.clinical_models.fit_policy", side_effect=AssertionError("new policy fit")):
            actual, _ = self.execute()
        self.assertEqual(actual["draw_annotation_rows"], 4)
        self.assertEqual(actual["draw_annotation_unique"], 3)
        self.assertEqual(actual["unique_cachevalid_annotations"], 4)
        self.assertEqual(actual["draw_annotation_patient_counts"], {"0": 1, "1": 2, "2": 1})
        self.assertEqual(actual["requested_annotation_budget"], 500)
        self.assertEqual(actual["population_draw_metadata"], self.old["population_draw_metadata"])
        self.assertEqual(actual["factual_training_events"], 5)
        self.assertFalse(actual["target_policy_refitted"])
        self.assertFalse(actual["factual_preprocessor_refitted"])

    def test_expanded_equal_weight_ols_matches_independent_row_oracle(self):
        from sklearn.linear_model import LinearRegression
        from threadpoolctl import threadpool_limits
        original = copy.deepcopy(self.old_models)
        record, payload = self.execute()
        baseline = RewardFit.from_dict(self.old_models["reward_model"])
        indices = [0, 0, 3, 4, 5, 0, 0, 3, 4]
        context = baseline.preprocessor.transform(self.data.features[indices])
        actions = np.r_[self.data.actions[[0, 0, 3, 4, 5]], [40, 40, 10, 40]]
        rewards = np.r_[self.data.rewards[[0, 0, 3, 4, 5]], [.83, .83, .86, .87]]
        with threadpool_limits(limits=1):
            oracle = LinearRegression(fit_intercept=True, positive=False).fit(np.column_stack((context, actions / 40)), rewards)
        model = payload["reward_model_plus"]
        np.testing.assert_allclose(model["coefficients"], oracle.coef_, rtol=0, atol=1e-13)
        self.assertAlmostEqual(model["intercept"], oracle.intercept_, places=13)
        self.assertEqual(model["preprocessor"], baseline.to_dict()["preprocessor"])
        self.assertEqual(model["metadata"]["training_rows"], 9)
        self.assertEqual(model["metadata"]["annotation_training_rows"], 4)
        self.assertEqual(self.old_models, original)
        policy = PolicyFit.from_dict(self.old_models["target_policy"])
        evaluation = self.draws["target_validation"].event_indices
        expected = np.mean(np.sum(policy.predict_proba(self.data.features[evaluation]) *
            RewardFit.from_dict(model).predict_action_values(self.data.features[evaluation]), axis=1))
        self.assertAlmostEqual(record["dm_value"], expected, places=13)

    def test_empty_cache_budget_zero_preserves_exact_original_dm_and_model(self):
        record, payload = self.execute((), requested_budget=0)
        for field in ("dm_value", "observed_reference_value", "signed_error", "squared_error"):
            self.assertEqual(record[field], self.old[field])
        self.assertEqual(payload["reward_model_plus"], self.old_models["reward_model"])
        self.assertTrue(record["zero_selected_annotation_identity"])
        self.assertEqual(record["draw_annotation_rows"], 0)

    def test_unselected_source_patient_adds_no_annotation_and_no_refit(self):
        record, payload = self.execute((self.annotations[1],))
        self.assertEqual(record["unique_cachevalid_annotations"], 1)
        self.assertEqual(record["draw_annotation_rows"], 0)
        self.assertEqual(record["dm_value"], self.old["dm_value"])
        self.assertEqual(payload["reward_model_plus"], self.old_models["reward_model"])

    def test_original_counts_order_or_metadata_change_rejected(self):
        mutations = []
        changed = copy.deepcopy(self.saved)
        changed["behavior_train_patient_counts"] = np.array([1, 1, 1])
        mutations.append(changed)
        changed = copy.deepcopy(self.saved)
        changed["behavior_train_subject_ids"] = changed["behavior_train_subject_ids"][::-1]
        mutations.append(changed)
        changed = copy.deepcopy(self.saved)
        changed["behavior_train_patient_counts"] = changed["behavior_train_patient_counts"].astype(float)
        mutations.append(changed)
        changed = copy.deepcopy(self.saved)
        changed.pop("target_train_subject_ids")
        mutations.append(changed)
        for changed in mutations:
            with self.subTest(keys=list(changed)), self.assertRaises(ValueError):
                paired.run_paired_draw(self.data, self.populations, self.old, self.old_models, changed, self.annotations)
        changed_old = copy.deepcopy(self.old)
        changed_old["population_draw_metadata"]["behavior_train"]["redraws"] = 1
        with self.assertRaises(ValueError):
            paired.run_paired_draw(self.data, self.populations, changed_old, self.old_models, self.saved, self.annotations)

    def test_wrong_saved_policy_baseline_or_draw_source_rejected(self):
        for field in ("target_policy", "reward_model"):
            state = copy.deepcopy(self.old_models)
            if field == "reward_model":
                state[field]["intercept"] += .1
            else:
                state[field]["metadata"]["converged"] = False
            with self.subTest(model=field), self.assertRaises(ValueError):
                paired.run_paired_draw(self.data, self.populations, self.old, state, self.saved, self.annotations)
        changed = copy.deepcopy(self.old_models)
        changed["metadata"]["draw_id"] += 1
        with self.assertRaises(ValueError):
            paired.run_paired_draw(self.data, self.populations, self.old, changed, self.saved, self.annotations)

    def test_cache_validation_checks_even_patient_not_sampled(self):
        row = self.annotations[1]
        invalids = (replace(row, action=int(self.data.actions[1])), replace(row, reward=1.1),
            replace(row, event_index=12, event_id=self.data.event_ids[12]), replace(row, event_id="wrong"))
        for invalid in invalids:
            with self.subTest(action=invalid.action), self.assertRaises(ValueError):
                self.execute((invalid,))
        with self.assertRaises(ValueError):
            self.execute((row, row))
        with self.assertRaises(ValueError):
            self.execute((row, replace(self.annotations[0], model_key="other")))

    def test_canonical_shared_reference_and_finite_json(self):
        record, payload = self.execute(batch_size=1)
        self.assertEqual(record["observed_reference_value"], self.old["observed_reference_value"])
        self.assertEqual(record["original_dm_value"], self.old["dm_value"])
        self.assertEqual(record["signed_error"], record["dm_value"] - self.old["observed_reference_value"])
        json.dumps(record, allow_nan=False)
        json.dumps(payload, allow_nan=False)

    def test_invalid_budget_batch_and_original_failed_draw_rejected(self):
        for budget in (-1, 501, True, 1.5, 3):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                self.execute(requested_budget=budget)
        for batch in (0, -1, True, 1.5):
            with self.subTest(batch=batch), self.assertRaises(ValueError):
                self.execute(batch_size=batch)
        self.old["status"] = "failed"
        with self.assertRaises(ValueError):
            self.execute()

    def test_changed_original_result_rejected_including_matching_fake_error(self):
        for key in ("dm_value", "observed_reference_value", "signed_error", "evaluation_events"):
            changed = copy.deepcopy(self.old)
            changed[key] += .1
            if key in ("dm_value", "observed_reference_value"):
                changed["signed_error"] = changed["dm_value"] - changed["observed_reference_value"]
                changed["squared_error"] = changed["signed_error"] ** 2
            with self.subTest(key=key), self.assertRaises(ValueError):
                paired.run_paired_draw(self.data, self.populations, changed, self.old_models, self.saved, self.annotations)

    def test_real_keyed_draw_sodium_action_scale_and_six_action_evaluation(self):
        from sklearn.linear_model import LinearRegression
        from threadpoolctl import threadpool_limits
        self.data.task = "sodium"
        mapping = {0: 0, 10: 100, 20: 200, 40: 500}
        self.data.actions = np.asarray([mapping[int(a)] for a in self.data.actions], dtype=float)
        self.populations = {name: build_cluster_population(self.data, "gender", name) for name in POPULATIONS}
        self.old, self.old_models, self.draws = run_dm_draw(self.data, self.populations, 6)
        self.saved = {name + suffix: getattr(draw, attr).copy()
            for name, draw in self.draws.items()
            for suffix, attr in (("_subject_ids", "subject_ids"), ("_patient_counts", "patient_counts"))}
        self.annotations = tuple(replace(row, action=400) for row in self.annotations)
        actual, payload = self.execute()
        baseline = RewardFit.from_dict(self.old_models["reward_model"])
        factual = self.draws["behavior_train"].event_indices.tolist()
        patient_counts = dict(zip(self.draws["behavior_train"].subject_ids.tolist(),
                                 self.draws["behavior_train"].patient_counts.tolist()))
        cf = [row for row in self.annotations for _ in range(patient_counts[int(self.data.subject_ids[row.event_index])])]
        indices = factual + [row.event_index for row in cf]
        actions = self.data.actions[factual].tolist() + [row.action for row in cf]
        rewards = self.data.rewards[factual].tolist() + [row.reward for row in cf]
        with threadpool_limits(limits=1):
            oracle = LinearRegression().fit(np.column_stack((baseline.preprocessor.transform(self.data.features[indices]),
                np.asarray(actions) / 500)), rewards)
        np.testing.assert_allclose(payload["reward_model_plus"]["coefficients"], oracle.coef_, rtol=0, atol=1e-13)
        self.assertEqual(payload["reward_model_plus"]["actions"], [0, 100, 200, 300, 400, 500])
        self.assertEqual(actual["draw_annotation_rows"], len(cf))

    def test_batching_changes_neither_paired_membership_nor_value(self):
        first, _ = self.execute(batch_size=1)
        second, _ = self.execute(batch_size=5000)
        self.assertEqual(first["population_draw_metadata"], second["population_draw_metadata"])
        for field in ("dm_value", "observed_reference_value", "signed_error"):
            self.assertAlmostEqual(first[field], second[field], places=13)


if __name__ == "__main__":
    unittest.main()
