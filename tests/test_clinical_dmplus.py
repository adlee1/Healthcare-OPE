"""Synthetic clinical points and synthetic provider receipts only; no services."""
import copy
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import april_repro
STAGE = Path(__file__).resolve().parents[1]
if str(STAGE / "src/april_repro") not in april_repro.__path__:
    april_repro.__path__.insert(0, str(STAGE / "src/april_repro"))
from april_repro import clinical_dmplus as dmplus
from april_repro.clinical_dataset import ClinicalDataset, ROLE_CODES, FOLD_CODES
from april_repro.clinical_models import fit_policy, fit_reward
from april_repro.cohort_splits import SPLITS
from april_repro.decision_features import FEATURES
from april_repro import llm_run_summary
import test_llm_run_summary as fixtures

AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "scipy", "sklearn", "threadpoolctl"))
if AVAILABLE:
    import numpy as np


def synthetic_dataset():
    events = tuple(hashlib.sha256(("potassium" + str(i)).encode()).hexdigest() for i in range(6))
    features = np.full((6, len(FEATURES)), np.nan)
    features[:, 0] = [20, 30, 80, 40, 45, 50]
    features[:, 1] = [0, 0, 0, 0, 1, 1]
    roles = np.full((6, len(SPLITS)), ROLE_CODES["behavior"], dtype=np.int8)
    roles[4:] = ROLE_CODES["target"]
    folds = np.array([FOLD_CODES["train"]] * 4 + [FOLD_CODES["validation"]] * 2)
    return ClinicalDataset("potassium", events, np.arange(1, 7), np.arange(11, 17), features,
        np.array([0, 10, 10, 40, 20, 40]), np.array([4.] * 6), np.array([.6, .7, .8, .9, .5, .7]),
        roles, folds, {}, {"manifest_sha256": "a" * 64})


@unittest.skipUnless(AVAILABLE, "Optional pinned clinical numerical dependencies are not installed")
class ClinicalDMPlusTests(unittest.TestCase):
    def setUp(self):
        self.data = synthetic_dataset()
        self.train = self.data.mask("gender", "behavior", "train")
        self.baseline = fit_reward(self.data.features[self.train], self.data.actions[self.train],
            self.data.rewards[self.train], self.data.task)
        self.policy = fit_policy(self.data.features[self.train], self.data.actions[self.train], self.data.task)
        self.cf = dmplus.Counterfactual("request1", self.data.event_ids[2], 2, 40, .95, "gpt-4o-mini", "protocol1")

    def test_zero_budget_is_exact_saved_model_identity(self):
        actual = dmplus.fit_augmented_reward(self.data, self.train, self.baseline, ())
        self.assertIs(actual, self.baseline)

    def test_equal_weight_ols_matches_oracle_with_fixed_factual_transform(self):
        from sklearn.linear_model import LinearRegression
        from threadpoolctl import threadpool_limits
        before = self.baseline.to_dict()
        actual = dmplus.fit_augmented_reward(self.data, self.train, self.baseline, (self.cf,))
        indices = [0, 1, 2, 3, 2]
        transformed = self.baseline.preprocessor.transform(self.data.features[indices])
        design = np.column_stack((transformed, np.array([0, 10, 10, 40, 40]) / 40))
        with threadpool_limits(limits=1):
            oracle = LinearRegression(fit_intercept=True, positive=False).fit(design, [.6, .7, .8, .9, .95])
        np.testing.assert_allclose(actual.to_dict()["coefficients"], oracle.coef_, atol=1e-14)
        self.assertAlmostEqual(actual.to_dict()["intercept"], oracle.intercept_)
        self.assertEqual(actual.preprocessor.to_dict(), before["preprocessor"])
        self.assertEqual(self.baseline.to_dict(), before)
        self.assertEqual(actual.metadata["training_rows"], 5)
        self.assertEqual(actual.metadata["factual_training_rows"], 4)
        self.assertEqual(actual.metadata["annotation_training_rows"], 1)
        self.assertFalse(actual.metadata["interactions"])
        self.assertFalse(actual.metadata["prediction_clipping"])

    def test_point_pair_uses_same_policy_and_same_target_events(self):
        augmented = dmplus.fit_augmented_reward(self.data, self.train, self.baseline, (self.cf,))
        before = self.policy.to_dict()
        actual = dmplus.evaluate_pair(self.data, "gender", self.policy, self.baseline, augmented, batch_size=1)
        values = self.data.features[4:]
        probabilities = self.policy.predict_proba(values)
        self.assertAlmostEqual(actual["dm"], np.mean(np.sum(probabilities * self.baseline.predict_action_values(values), axis=1)))
        self.assertAlmostEqual(actual["dm_plus"], np.mean(np.sum(probabilities * augmented.predict_action_values(values), axis=1)))
        self.assertEqual(actual["observed_reference"], .6)
        self.assertEqual(actual["evaluation_events"], 2)
        self.assertEqual(actual["evaluation_subjects"], 2)
        self.assertEqual(self.policy.to_dict(), before)
        self.assertIsNone(actual["rmse"])
        self.assertEqual(actual["bootstrap_datasets"], 0)

    def test_saved_dm_replay_rejects_changed_point_and_population(self):
        actual = dmplus.evaluate_pair(self.data, "gender", self.policy, self.baseline, self.baseline)
        saved = {key: actual[key] for key in ("status", "evaluation_events", "dm", "observed_reference")}
        self.assertTrue(dmplus.verify_saved_dm(actual, saved)["dm_exactly_equal"])
        for key in ("dm", "observed_reference", "evaluation_events"):
            changed = dict(saved)
            changed[key] += .1
            with self.subTest(key=key), self.assertRaises(ValueError):
                dmplus.verify_saved_dm(actual, changed)

    def test_empty_validation_stays_not_estimable(self):
        folds = self.data.folds.copy()
        folds[4:] = FOLD_CODES["train"]
        data = replace(self.data, folds=folds)
        result = dmplus.evaluate_pair(data, "gender", self.policy, self.baseline, self.baseline)
        self.assertEqual(result["status"], "not_estimable")
        self.assertEqual(result["reason"], "empty_target_validation")
        self.assertEqual(result["evaluation_events"], 0)
        self.assertIsNone(result["dm_plus"])

    def test_augmentation_rejects_duplicate_source_leakage_and_observed_action(self):
        invalid_sets = ((self.cf, self.cf), (replace(self.cf, event_index=4, event_id=self.data.event_ids[4]),),
            (replace(self.cf, action=10),), (replace(self.cf, reward=1.1),),
            (replace(self.cf, event_id="wrong"),),
            (self.cf, replace(self.cf, request_id="request2", action=20, protocol_id="another")))
        for rows in invalid_sets:
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                dmplus.fit_augmented_reward(self.data, self.train, self.baseline, rows)

    def fixture_evidence(self, *, malformed=False):
        fixture = fixtures.RunSummaryTests("test_disjoint_warmup_and_remaining_runs_have_unique_event_metrics")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        run = fixture.make_run("run", malformed=malformed)
        dest = fixture.root / "summary"
        llm_run_summary.write_summary([fixture.packet], [run], dest)
        return fixture, run, dest, dmplus.load_verified_annotations(dest)

    def test_verified_receipts_join_only_cf_training_consumer_and_recompute_reward(self):
        _, _, _, evidence = self.fixture_evidence()
        rows, coverage = dmplus.select_counterfactuals(self.data, evidence, "gender", "gpt-4o-mini")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].event_index, 2)
        self.assertEqual(rows[0].action, 40)
        self.assertEqual(rows[0].reward, 1)
        self.assertEqual(coverage["requested_annotations"], 1)
        self.assertTrue(evidence.provenance["raw_receipts_revalidated"])
        absent, coverage = dmplus.select_counterfactuals(self.data, evidence, "dosage", "gpt-4o-mini")
        self.assertFalse(absent)
        self.assertEqual(coverage["requested_annotations"], 0)

    def test_invalid_predictions_preserve_annotation_denominator(self):
        _, _, _, evidence = self.fixture_evidence(malformed=True)
        rows, coverage = dmplus.select_counterfactuals(self.data, evidence, "gender", "gpt-4o-mini")
        self.assertFalse(rows)
        self.assertEqual(coverage["requested_annotations"], 1)
        self.assertEqual(coverage["invalid_annotations_including_missing"], 1)

    def test_forged_parsed_jsonl_even_with_rehashed_manifest_is_rejected(self):
        _, _, dest, _ = self.fixture_evidence()
        path = dest / "parsed-annotations.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        rows[-1]["parsed_prediction"]["reward"] = .123
        path.write_bytes(b"".join(llm_run_summary._encoded(row) for row in rows))
        manifest_path = dest / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest["outputs"][path.name] = dmplus.file_sha256(path)
        fixtures.write(manifest_path, manifest)
        with self.assertRaisesRegex(ValueError, "verified raw source"):
            dmplus.load_verified_annotations(dest)

    def test_modified_raw_reply_is_rejected_before_training(self):
        fixture, run, dest, _ = self.fixture_evidence()
        path = run / (fixture.rows[0]["request_id"] + ".raw")
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            dmplus.load_verified_annotations(dest)

    def test_join_rejects_other_dataset_observed_action_and_validation_membership(self):
        _, _, _, evidence = self.fixture_evidence()
        changed_action = self.data.actions.copy()
        changed_action[2] = 20
        changed_folds = self.data.folds.copy()
        changed_folds[2] = FOLD_CODES["validation"]
        for data in (replace(self.data, provenance={"manifest_sha256": "b" * 64}),
                     replace(self.data, actions=changed_action), replace(self.data, folds=changed_folds)):
            with self.assertRaises(ValueError):
                dmplus.select_counterfactuals(data, evidence, "gender", "gpt-4o-mini")

    def test_cli_writes_private_local_artifacts_and_explicit_pilot_scope(self):
        spec = importlib.util.spec_from_file_location("dmplus_runner_tested", STAGE / "scripts/run_clinical_dmplus.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory(prefix="synthetic-dmplus-cli-") as directory:
            root = Path(directory)
            baseline_dir = root / "artifacts/clinical-baselines/synthetic"
            source_dir = root / "artifacts/treatment-features/synthetic"
            summary_dir = root / "artifacts/llm-summaries/synthetic"
            for folder in (baseline_dir, source_dir, summary_dir):
                folder.mkdir(parents=True)
            (source_dir / "manifest.json").write_text("{}")
            data = replace(self.data, provenance={"manifest_sha256": dmplus.file_sha256(source_dir / "manifest.json"),
                "outputs": {}})
            point = dmplus.evaluate_pair(data, "gender", self.policy, self.baseline, self.baseline)
            saved = {"task": "potassium", "input": {"directory": str(source_dir.relative_to(root)),
                "manifest_sha256": data.provenance["manifest_sha256"], "outputs": {}},
                "results": {split: {"dm": point} for split in SPLITS}}
            fixtures.write(baseline_dir / "manifest.json", saved)
            for split in SPLITS:
                (baseline_dir / split).mkdir()
                fixtures.write(baseline_dir / split / "reward-model.json", self.baseline.to_dict())
                fixtures.write(baseline_dir / split / "target-policy.json", self.policy.to_dict())
            (root / "synthetic-source.py").write_text("# no patient data\n")
            evidence = dmplus.AnnotationEvidence({}, ({"task": "potassium", "model_key": "gpt-4o-mini",
                "mode": "counterfactual"},), {}, {"raw_receipts_revalidated": True})
            def selected(dataset, evidence, split, model, index):
                incomplete = split == "dosage"
                return (() if incomplete else (self.cf,)), {"requested_annotations": 1,
                    "valid_annotations": 0 if incomplete else 1, "invalid_annotations_including_missing": int(incomplete),
                    "missing_annotations": 0, "source_model_key": model, "annotation_protocol_id": "protocol1",
                    "annotation_budget_is_pilot": True}
            with mock.patch.object(runner, "ROOT", root), mock.patch.object(runner, "CODE_PATHS", ("synthetic-source.py",)), \
                    mock.patch.object(runner, "load_baseline", return_value=saved), \
                    mock.patch.object(runner, "load_clinical_dataset", return_value=data), \
                    mock.patch.object(runner, "load_verified_annotations", return_value=evidence), \
                    mock.patch.object(runner, "select_counterfactuals", side_effect=selected):
                result = runner.run(str(baseline_dir), str(summary_dir))
            self.assertEqual(result["estimated_cells"], 2)
            self.assertEqual(result["not_estimable_cells"], 1)
            self.assertEqual(result["llm_calls"], 0)
            folder = root / result["artifact"]
            manifest = json.loads((folder / "manifest.json").read_bytes())
            self.assertEqual(manifest["status"], "complete")
            self.assertFalse(manifest["formal_500_annotation_experiment"])
            self.assertEqual(manifest["bootstrap_datasets"], 0)
            self.assertEqual(manifest["results"]["dosage"]["gpt-4o-mini"]["reason"], "empty_or_incomplete_annotation_cell")
            self.assertIsNone(manifest["results"]["dosage"]["gpt-4o-mini"]["dm_plus"])
            self.assertEqual(manifest["results"]["gender"]["gpt-4o-mini"]["annotation_rows_added"], 1)
            for path in folder.rglob("*"):
                if path.is_file():
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
