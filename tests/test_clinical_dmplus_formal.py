"""Synthetic fixed-prefix and raw provider evidence only; no external calls."""
from copy import deepcopy
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
from april_repro import clinical_dmplus_formal as formal
from april_repro.clinical_dmplus import AnnotationEvidence
from april_repro.clinical_dataset import ClinicalDataset, ROLE_CODES, FOLD_CODES
from april_repro.cohort_splits import SPLITS
from april_repro.decision_features import FEATURES
from april_repro.rewards import reward_from_lab
import test_llm_formal_summary as raw_fixtures

AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "scipy", "sklearn", "threadpoolctl"))
if AVAILABLE:
    import numpy as np


@unittest.skipUnless(AVAILABLE, "Pinned clinical numerical dependencies unavailable")
class FormalPrefixTests(unittest.TestCase):
    def setUp(self):
        events = tuple(hashlib.sha256(str(i).encode()).hexdigest() for i in range(502))
        roles = np.full((502, len(SPLITS)), ROLE_CODES["behavior"], dtype=np.int8)
        roles[500:] = ROLE_CODES["target"]
        folds = np.array([FOLD_CODES["train"]] * 500 + [FOLD_CODES["validation"]] * 2)
        self.data = ClinicalDataset("potassium", events, np.arange(502), np.arange(502),
            np.zeros((502, len(FEATURES))), np.zeros(502), np.full(502, 4.), np.ones(502),
            roles, folds, {}, {"manifest_sha256": "a" * 64})
        rows, requests = [], {}
        for index in range(500):
            rid = hashlib.sha256(("request" + str(index)).encode()).hexdigest()
            row = {"request_id": rid, "event_id": events[index], "task": "potassium",
                "model_key": "deepseek", "mode": "counterfactual", "action": 40,
                "protocol_id": "synthetic-protocol", "missing": False, "status": "valid",
                "parsed_prediction": {"predicted_lab_value": 4., "status": "valid", "task": "potassium",
                    "reward_sigma": 2.5, "reward": reward_from_lab(4., "potassium")},
                "consumers": [{"split": split, "mode": "counterfactual", "fold": "train",
                    "rank": index + 1 if split != "dosage" else 500 - index} for split in SPLITS]}
            rows.append(row)
            requests[rid] = {"protocol_id": row["protocol_id"], "metadata": {"input_manifest_sha256": "a" * 64,
                "task": "potassium", "model_key": "deepseek", "mode": "counterfactual", "event_id": events[index],
                "observed_action": 0, "action": 40}}
        self.evidence = AnnotationEvidence({}, tuple(reversed(rows)), requests, {})

    def select(self, budget, split="gender", evidence=None, data=None):
        return formal.select_prefix(data or self.data, evidence or self.evidence, split, "deepseek", budget)

    def test_prefix_uses_consumer_rank_not_input_order_or_request_identity(self):
        selected, counts = self.select(100)
        self.assertEqual({r.event_id for r in selected}, set(self.data.event_ids[:100]))
        self.assertEqual(counts["requested_annotations"], 100)
        self.assertTrue(counts["exact_valid_annotation_budget"])
        self.assertFalse(counts["annotation_budget_is_pilot"])
        dosage, _ = self.select(100, "dosage")
        self.assertEqual({r.event_id for r in dosage}, set(self.data.event_ids[400:500]))

    def test_invalid_inside_prefix_is_not_replaced_by_later_valid_row(self):
        rows = deepcopy(self.evidence.annotations)
        rows[-1]["status"] = "invalid"
        rows[-1]["parsed_prediction"] = None
        evidence = replace(self.evidence, annotations=rows)
        selected, counts = self.select(100, evidence=evidence)
        self.assertEqual(len(selected), 99)
        self.assertEqual(counts["invalid_annotations_including_missing"], 1)
        self.assertFalse(counts["exact_valid_annotation_budget"])
        self.assertEqual(counts["analysis_status"], "available_valid_subset_of_fixed_requested_budget")
        self.assertNotIn(self.data.event_ids[100], {r.event_id for r in selected})

    def test_zero_budget_preserves_zero_denominator(self):
        selected, counts = self.select(0)
        self.assertFalse(selected)
        self.assertEqual(counts["requested_budget"], 0)
        self.assertTrue(counts["exact_valid_annotation_budget"])

    def test_missing_model_results_do_not_become_available_valid_diagnostics(self):
        rows = deepcopy(self.evidence.annotations)
        rows[-1]["missing"] = True
        with self.assertRaisesRegex(ValueError, "missing results"):
            self.select(100, evidence=replace(self.evidence, annotations=rows))

    def test_rank_duplicates_gaps_and_bool_are_rejected(self):
        for rank in (2, 501, True):
            rows = deepcopy(self.evidence.annotations)
            rows[-1]["consumers"][0]["rank"] = rank
            with self.subTest(rank=rank), self.assertRaises(ValueError):
                self.select(100, evidence=replace(self.evidence, annotations=rows))

    def test_prefix_reuses_original_training_membership_and_input_identity_checks(self):
        folds = self.data.folds.copy()
        folds[0] = FOLD_CODES["validation"]
        for data in (replace(self.data, folds=folds), replace(self.data, provenance={"manifest_sha256": "b" * 64})):
            with self.assertRaises(ValueError):
                self.select(100, data=data)

    def test_unsupported_budget_never_selects_arbitrary_prefix(self):
        for value in (1, 99, 600, True, 100.):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.select(value)

    def test_cli_keeps_partial_budget_diagnostic_and_empty_validation_unestimable(self):
        from april_repro.clinical_models import fit_reward, fit_policy
        from april_repro.clinical_dmplus import evaluate_pair, file_sha256
        repository_scripts = Path(raw_fixtures.__file__).resolve().parents[1] / "scripts"
        sys.path.insert(0, str(repository_scripts))
        self.addCleanup(lambda: sys.path.remove(str(repository_scripts)))
        spec = importlib.util.spec_from_file_location("formal_dmplus_test_runner", STAGE / "scripts/run_clinical_dmplus_formal.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory(prefix="synthetic-formal-dmplus-") as directory:
            root = Path(directory)
            source, baseline_folder = root / "features", root / "baseline"
            source.mkdir()
            baseline_folder.mkdir()
            (source / "manifest.json").write_text("{}")
            digest = file_sha256(source / "manifest.json")
            roles = self.data.roles.copy()
            roles[500:, SPLITS.index("dosage")] = ROLE_CODES["excluded"]
            features = np.full_like(self.data.features, np.nan)
            features[:, 0] = 40
            features[:, 1] = 0
            data = replace(self.data, roles=roles, features=features, provenance={"manifest_sha256": digest, "outputs": {}})
            evidence = deepcopy(self.evidence)
            for row in evidence.requests.values():
                row["metadata"]["input_manifest_sha256"] = digest
            evidence.annotations[-1]["status"] = "invalid"
            evidence.annotations[-1]["parsed_prediction"] = None
            train = data.mask("gender", "behavior", "train")
            reward = fit_reward(data.features[train], data.actions[train], data.rewards[train], data.task)
            policy = fit_policy(data.features[train], data.actions[train], data.task)
            saved = {"task": "potassium", "input": {"directory": str(source), "manifest_sha256": digest, "outputs": {}},
                "results": {split: {"dm": evaluate_pair(data, split, policy, reward, reward)} for split in SPLITS}}
            (baseline_folder / "manifest.json").write_text(json.dumps(saved))
            for split in SPLITS:
                (baseline_folder / split).mkdir()
                (baseline_folder / split / "reward-model.json").write_text(json.dumps(reward.to_dict()))
                (baseline_folder / split / "target-policy.json").write_text(json.dumps(policy.to_dict()))
            (root / "synthetic.py").write_text("# synthetic source\n")
            with mock.patch.object(runner, "ROOT", root), mock.patch.object(runner, "CODE_PATHS", ("synthetic.py",)), \
                    mock.patch.object(runner.pilot_runner, "load_baseline", return_value=saved), \
                    mock.patch.object(runner, "load_model_evidence", return_value=evidence), \
                    mock.patch.object(runner, "load_clinical_dataset", return_value=data), \
                    mock.patch.object(runner, "verify_evidence_unchanged"):
                report = runner.run("synthetic-plan", "synthetic-run", [baseline_folder], root / "output", "deepseek")
            self.assertEqual(report["estimated_points"], 12)
            self.assertEqual(report["not_estimable_points"], 6)
            point = json.loads((root / "output/potassium/gender/100/summary.json").read_bytes())
            self.assertEqual(point["requested_budget"], 100)
            self.assertEqual(point["annotation_rows_added"], 99)
            self.assertFalse(point["exact_valid_annotation_budget"])
            self.assertIsNone(point["rmse"])
            empty = json.loads((root / "output/potassium/dosage/500/summary.json").read_bytes())
            self.assertEqual(empty["reason"], "empty_target_validation")
            self.assertEqual(empty["annotation_rows_added"], 0)
            self.assertEqual(empty["selected_valid_annotations"], 499)
            self.assertTrue(all((path.stat().st_mode & 0o777) == 0o600 for path in (root / "output").rglob("*") if path.is_file()))


class FormalModelEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = raw_fixtures.FormalSummaryTests("test_cache_uses_formal_consumers_and_unique_all_event_denominator")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.selected = [row for row in self.fixture.rows if row["metadata"]["model_key"] == "gpt-4o-mini"]
        patcher = mock.patch.object(formal, "load_formal_plan", return_value=self.fixture.plan)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(formal, "source_hashes", return_value={"synthetic.py": "c" * 64})
        patcher.start()
        self.addCleanup(patcher.stop)

    def collect(self, run):
        return formal.load_model_evidence(self.fixture.plan.directory, run, "gpt-4o-mini")

    def test_complete_selected_model_does_not_wait_for_unfinished_other_model(self):
        run = self.fixture.build_run(self.selected)
        evidence = self.collect(run)
        self.assertEqual(evidence.summary["unique_requests"], 3)
        self.assertEqual(evidence.summary["valid_predictions"], 3)
        self.assertTrue(evidence.provenance["raw_receipts_revalidated"])
        self.assertFalse(evidence.provenance["other_model_completion_required"])

    def test_cached_reply_uses_formal_overlap_consumers_and_counts_once(self):
        cached = self.fixture.cache_first()
        run = self.fixture.build_run(self.selected[1:])
        evidence = self.collect(run)
        self.assertEqual(evidence.summary["reused_annotations"], 1)
        row = next(r for r in evidence.annotations if r["request_id"] == cached["request_id"])
        self.assertEqual(len(row["consumers"]), 2)
        all_events = next(r for r in evidence.summary["factual_evaluations"] if r["split"] == "all_unique_events")
        self.assertEqual(all_events["requested_predictions"], 2)

    def test_invalid_completed_responses_stay_in_full_model_denominator(self):
        run = self.fixture.build_run(self.selected, invalid=True)
        evidence = self.collect(run)
        self.assertEqual(evidence.summary["completed_annotations"], 3)
        self.assertEqual(evidence.summary["invalid_predictions"], 3)
        self.assertEqual(evidence.summary["missing_predictions"], 0)

    def test_selected_model_missing_result_is_rejected(self):
        run = self.fixture.build_run(self.selected[:-1])
        with self.assertRaisesRegex(ValueError, "unfinished"):
            self.collect(run)

    def test_modified_raw_provider_reply_is_rejected(self):
        run = self.fixture.build_run(self.selected)
        path = run / "requests/gpt-4o-mini" / (self.selected[0]["request_id"] + ".raw")
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            self.collect(run)

    def test_duplicate_execution_ids_are_rejected(self):
        import json
        run = self.fixture.build_run(self.selected)
        path = run / "plan.json"
        value = json.loads(path.read_bytes())
        value["request_ids"].append(value["request_ids"][0])
        raw_fixtures.write(path, value)
        with self.assertRaises(ValueError):
            self.collect(run)


if __name__ == "__main__":
    unittest.main()
