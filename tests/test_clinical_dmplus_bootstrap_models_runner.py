"""Explicit model, source binding and resume checks; synthetic data, no API/DB."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import april_repro
PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT / "src/april_repro") not in april_repro.__path__:
    april_repro.__path__.insert(0, str(PROJECT / "src/april_repro"))
AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "scipy", "sklearn", "threadpoolctl"))
if AVAILABLE:
    import numpy as np
    from april_repro import clinical_models
    from april_repro.clinical_dataset import ClinicalDataset, ROLE_CODES, FOLD_CODES
    from april_repro.clinical_dmplus import Counterfactual
    from april_repro.cluster_bootstrap import POPULATIONS, build_cluster_population
    from april_repro.clinical_bootstrap import run_dm_draw
    from april_repro.cohort_splits import SPLITS
    from april_repro.decision_features import FEATURES
    repository = Path(clinical_models.__file__).resolve().parents[2]
    sys.path.insert(0, str(repository / "scripts"))
    spec = importlib.util.spec_from_file_location("paired_bootstrap_models_runner_tested", PROJECT / "scripts/run_clinical_dmplus_bootstrap_models.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)


@unittest.skipUnless(AVAILABLE, "Optional pinned modeling dependencies unavailable")
class ModelBootstrapRunnerTests(unittest.TestCase):
    def setUp(self):
        original_umask = os.umask(0o077)
        os.umask(original_umask)
        self.addCleanup(os.umask, original_umask)
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-paired-bootstrap-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for relative in runner.CODE_PATHS:
            source = PROJECT / relative
            if not source.exists():
                source = repository / relative
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        self.features = self.root / "artifacts/treatment-features/synthetic"
        self.features.mkdir(parents=True)
        (self.features / "manifest.json").write_text('{"synthetic":true}\n')
        self.dataset = self.make_dataset()
        self.populations = {s: {name: build_cluster_population(self.dataset, s, name) for name in POPULATIONS} for s in SPLITS}
        self.source = self.root / "original-dm"
        self.source.mkdir()
        (self.source / "manifest.json").write_text('{"synthetic_dm":true}\n')
        self.originals = {s: [] for s in SPLITS}
        for split in SPLITS:
            (self.source / split).mkdir()
            if split == "dosage":
                continue
            for draw_id in range(3):
                record, payload, draws = run_dm_draw(self.dataset, self.populations[split], draw_id)
                self.originals[split].append(runner.dm_runner.commit_draw(self.source / split, record, payload, draws))
        self.dm = {"task": "potassium", "input": {
            "directory": str(self.features.relative_to(self.root)),
            "manifest_sha256": self.dataset.provenance["manifest_sha256"], "outputs": {}},
            "populations": {s: {name: p.metadata for name, p in pops.items()} for s, pops in self.populations.items()}}
        self.annotations = tuple(Counterfactual("request" + str(i), self.dataset.event_ids[i], i,
            10, 0.8, "qwen", "synthetic-protocol") for i in (0, 2))
        self.point_source = self.root / "original-points"
        self.point_source.mkdir()
        (self.point_source / "manifest.json").write_text('{"synthetic_points":true}\n')
        ann_source = {"formal_plan_directory": "synthetic-plan", "run_directory": "synthetic-annotation-run", "selected_model_key": "qwen"}
        self.points = {"source_model_key": "qwen", "annotation_summary": {"model_key": "qwen"}, "annotation_evidence": ann_source, "tasks": {"potassium": {
            "input": self.dataset.provenance,
            "results": {s: {"500": {"valid_annotations": 2,
                "dm": 0.65, "dm_plus": 0.66, "observed_reference": 0.655}} for s in SPLITS}}}}
        for split in SPLITS:
            folder = self.point_source / "potassium" / split / "500"
            folder.mkdir(parents=True)
            runner.save(folder / "annotations-used.json", {"source": "qwen", "requested_budget": 500, "annotations": [
                {"request_id": r.request_id, "event_id": r.event_id, "action": r.action, "reward": r.reward}
                for r in self.annotations]})
        self.output = self.root / "artifacts/clinical-dmplus-bootstrap/synthetic"
        self.calls = []
        self.engine = runner.run_paired_draw
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(runner, "ROOT", self.root))
        self.stack.enter_context(mock.patch.object(runner, "load_dm_source", return_value=(self.dm, self.originals)))
        self.stack.enter_context(mock.patch.object(runner, "load_point_source", return_value=self.points))
        self.evidence_loader = self.stack.enter_context(mock.patch.object(runner, "load_model_evidence", return_value=SimpleNamespace(provenance=ann_source)))
        self.stack.enter_context(mock.patch.object(runner, "load_clinical_dataset", return_value=self.dataset))
        self.prefix = self.stack.enter_context(mock.patch.object(runner, "select_prefix", return_value=(self.annotations, {"valid_annotations": 2})))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def make_dataset(self):
        subjects = np.array([1, 1, 2, 3, 3, 4, 5, 5, 6], dtype=np.int64)
        roles = np.empty((len(subjects), len(SPLITS)), dtype=np.int8)
        folds = np.empty(len(subjects), dtype=np.int8)
        for i, subject in enumerate(subjects):
            roles[i, :] = ROLE_CODES["behavior" if subject <= 2 else "target"]
            folds[i] = FOLD_CODES["train" if subject <= 4 else "validation"]
            if subject >= 5:
                roles[i, SPLITS.index("dosage")] = ROLE_CODES["excluded"]
        features = np.full((len(subjects), len(FEATURES)), np.nan)
        features[:, 0] = 25 + subjects * 4
        features[:, 1] = subjects % 2
        return ClinicalDataset("potassium", tuple(hashlib.sha256(f"synthetic-event-{i}".encode()).hexdigest() for i in range(len(subjects))),
            subjects, subjects + 100, features, np.zeros(len(subjects), dtype=np.int64),
            np.full(len(subjects), 4.0), 0.6 + subjects / 100, roles, folds, {},
            {"manifest_sha256": runner.sha(self.features / "manifest.json"), "outputs": {}})

    def invoke(self, *, resume=False, limit=1):
        return runner.run(resume_directory=str(self.output), max_new_draws=limit) if resume else runner.run(
            dm_bootstrap_directory=str(self.source), point_directory=str(self.point_source),
            output_directory=str(self.output), max_new_draws=limit, model_key="qwen")

    def track(self, dataset, populations, original, *args, **kwargs):
        self.calls.append((original["split"], original["draw_id"]))
        return self.engine(dataset, populations, original, *args, **kwargs)

    def manifest(self):
        return json.loads((self.output / "manifest.json").read_text())

    def test_partial_resume_preserves_commits_and_skips_empty_split(self):
        with mock.patch.object(runner, "run_paired_draw", side_effect=self.track):
            self.invoke(limit=2)
            before = {str(p.relative_to(self.output)): p.read_bytes() for p in self.output.glob("*/draw-*/*")}
            first = self.manifest()
            self.assertEqual(first["status"], "partial")
            self.assertIsNone(first["results"]["gender"]["primary_metrics"])
            self.assertEqual(first["results"]["dosage"]["status"], "not_estimable")
            self.invoke(resume=True, limit=2)
        self.assertEqual(self.calls, [("gender", 0), ("comorbidity", 0), ("gender", 1), ("comorbidity", 1)])
        for relative, contents in before.items():
            self.assertEqual((self.output / relative).read_bytes(), contents)
        self.assertFalse(list((self.output / "dosage").glob("draw-*")))
        final = self.manifest()
        self.assertEqual(final["results"]["gender"]["completed_draws"], 2)
        self.assertEqual(len(final["committed_result_hashes"]), 4)

    def test_resume_rejects_source_manifests_and_bound_code_drift_before_fit(self):
        with mock.patch.object(runner, "run_paired_draw", side_effect=self.track):
            self.invoke()
            cases = [(self.source / "manifest.json", "source identity"),
                (self.point_source / "manifest.json", "source identity"),
                (self.root / "src/april_repro/clinical_dmplus_bootstrap.py", "unchanged code"),
                (self.output / "code/src/april_repro/clinical_dmplus_bootstrap.py", "code copy")]
            for path, message in cases:
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"\n ")
                    with self.subTest(path=str(path)), self.assertRaisesRegex(ValueError, message):
                        self.invoke(resume=True)
                finally:
                    path.write_bytes(original)
        self.assertEqual(self.calls, [("gender", 0)])

    def test_existing_output_and_committed_model_cannot_be_replaced(self):
        with mock.patch.object(runner, "run_paired_draw", side_effect=self.track):
            self.invoke()
            with self.assertRaisesRegex(ValueError, "Output already exists"):
                self.invoke()
            result = self.output / "gender/draw-000/result.json"
            record = json.loads(result.read_text())
            with self.assertRaisesRegex(ValueError, "overwrite"):
                runner.commit_draw(result.parent.parent, record, {})
            model = result.parent / "models.json"
            original = model.read_bytes()
            model.write_bytes(original + b" ")
            with self.assertRaisesRegex(ValueError, "model changed"):
                self.invoke(resume=True)
        self.assertEqual(self.calls, [("gender", 0)])

    def test_failed_draw_identity_survives_resume_without_refit(self):
        def broken(dataset, populations, original, *args, **kwargs):
            self.calls.append((original["split"], original["draw_id"]))
            raise ArithmeticError("synthetic numerical failure")
        with mock.patch.object(runner, "run_paired_draw", side_effect=broken):
            with self.assertRaises(Exception):
                self.invoke()
        first = self.manifest()
        self.assertEqual(first["status"], "interrupted")
        self.assertEqual(first["results"]["gender"]["failed_draw_ids"], [0])
        with mock.patch.object(runner, "run_paired_draw", side_effect=self.track):
            self.invoke(resume=True)
        self.assertEqual(self.calls, [("gender", 0), ("comorbidity", 0)])
        self.assertEqual(self.manifest()["results"]["gender"]["failed_draw_ids"], [0])
        self.assertIsNone(self.manifest()["results"]["gender"]["primary_metrics"])

    def test_atomic_commit_before_checkpoint_is_recovered_without_refit(self):
        with mock.patch.object(runner, "run_paired_draw", side_effect=self.track):
            self.invoke()
            old = self.manifest()
            old["committed_result_hashes"] = {}
            runner.save(self.output / "manifest.json", old)
            self.invoke(resume=True)
        self.assertEqual(self.calls, [("gender", 0), ("comorbidity", 0)])
        self.assertEqual(len(self.manifest()["committed_result_hashes"]), 2)

    def test_changed_fixed_annotation_cache_is_rejected_before_fit(self):
        self.prefix.return_value = (self.annotations[:1], {"valid_annotations": 1})
        with mock.patch.object(runner, "run_paired_draw", side_effect=self.track):
            with self.assertRaisesRegex(ValueError, "prefix changed"):
                self.invoke()
        self.assertEqual(self.calls, [])


    def test_selected_model_flows_to_evidence_prefix_manifest_and_draws(self):
        self.invoke()
        self.evidence_loader.assert_called_once_with("synthetic-plan", "synthetic-annotation-run", "qwen")
        self.assertEqual({c.args[3] for c in self.prefix.call_args_list}, {"qwen"})
        self.assertEqual(self.manifest()["model_key"], "qwen")
        record=json.loads((self.output / "gender/draw-000/result.json").read_text())
        payload=json.loads((self.output / "gender/draw-000/models.json").read_text())
        self.assertEqual(record["source_model_key"], "qwen")
        self.assertEqual(payload["metadata"]["source_model_key"], "qwen")

    def test_new_run_requires_supported_explicit_model_before_creating_output(self):
        for value in (None, "", "other", True):
            with self.subTest(model=value), self.assertRaisesRegex(ValueError, "supported model"):
                runner.run(dm_bootstrap_directory=str(self.source), point_directory=str(self.point_source),
                    output_directory=str(self.output), max_new_draws=1, model_key=value)
            self.assertFalse(self.output.exists())

    def test_resume_rejects_explicit_model_override(self):
        self.invoke()
        with self.assertRaisesRegex(ValueError, "original recorded inputs"):
            runner.run(resume_directory=str(self.output), max_new_draws=1, model_key="gpt-4o-mini")
        self.assertEqual(self.manifest()["model_key"], "qwen")

    def test_wrong_cached_source_model_rejected_before_fitting(self):
        path=self.point_source / "potassium/gender/500/annotations-used.json"
        saved=json.loads(path.read_text()); saved["source"]="gpt-4o-mini"
        runner.save(path,saved)
        with mock.patch.object(runner, "run_paired_draw", side_effect=self.track):
            with self.assertRaisesRegex(ValueError,"prefix changed"):
                self.invoke()
        self.assertEqual(self.calls,[])

    def test_committed_draw_from_another_model_rejected_even_with_rebound_hash(self):
        self.invoke()
        path=self.output / "gender/draw-000/result.json"
        saved=json.loads(path.read_text()); saved["source_model_key"]="gpt-4o-mini"
        runner.save(path,saved)
        manifest=self.manifest(); manifest["committed_result_hashes"]["gender/draw-000/result.json"]=runner.sha(path)
        runner.save(self.output / "manifest.json",manifest)
        with mock.patch.object(runner, "run_paired_draw", side_effect=self.track):
            with self.assertRaisesRegex(ValueError,"draw identity mismatch"):
                self.invoke(resume=True)
        self.assertEqual(self.calls,[])


@unittest.skipUnless(AVAILABLE, "Optional pinned modeling dependencies unavailable")
class ModelPointSourceTests(unittest.TestCase):
    def test_completed_point_requires_matching_declared_and_evidence_models(self):
        with tempfile.TemporaryDirectory(prefix="synthetic-model-point-") as temporary:
            folder=Path(temporary)
            for selected in runner.MODEL_KEYS:
                valid={"status":"complete","scope":"formal_fixed_prefix_dmplus_point",
                    "source_model_key":selected,"annotation_evidence":{"selected_model_key":selected},
                    "annotation_summary":{"model_key":selected},"tasks":{"potassium":{}},"outputs":{},"versions":{}}
                runner.save(folder / "manifest.json",valid)
                self.assertEqual(runner.load_point_source(folder,"potassium",selected),valid)
                for location in ("source_model_key","annotation_evidence","annotation_summary"):
                    bad=json.loads(json.dumps(valid))
                    if location=="source_model_key": bad[location]="wrong"
                    elif location=="annotation_evidence": bad[location]["selected_model_key"]="wrong"
                    else: bad[location]["model_key"]="wrong"
                    runner.save(folder / "manifest.json",bad)
                    with self.subTest(model=selected,location=location), self.assertRaisesRegex(ValueError,"selected model"):
                        runner.load_point_source(folder,"potassium",selected)

    def test_protocol_changes_only_model_dispatch_and_version_metadata(self):
        import tomllib
        legacy=tomllib.loads((repository / "config/clinical-dmplus-bootstrap.toml").read_text())
        current=tomllib.loads((PROJECT / runner.PROTOCOL).read_text())
        runner.validate_protocol(current)
        for key in ("rule_version","recorded_on","status","model_key"): legacy.pop(key)
        for key in ("rule_version","recorded_on","status","model_keys"): current.pop(key)
        self.assertEqual(current,legacy)


if __name__ == "__main__":
    unittest.main()
