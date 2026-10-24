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
STAGE = Path(__file__).resolve().parents[1]
PROJECT = Path(os.environ.get('APRIL_BUDGET_BOOTSTRAP_PROJECT_ROOT', str(STAGE))).resolve()
os.environ['APRIL_BUDGET_BOOTSTRAP_PROJECT_ROOT'] = str(PROJECT)
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
    spec = importlib.util.spec_from_file_location("paired_bootstrap_models_runner_tested", STAGE / "scripts/run_clinical_dmplus_bootstrap_budgets.py")
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
            source = runner.source_path(relative)
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
            "results": {s: {"100": {"valid_annotations": 2,
                "dm": 0.65, "dm_plus": 0.66, "observed_reference": 0.655}} for s in SPLITS}}}}
        for split in SPLITS:
            folder = self.point_source / "potassium" / split / "100"
            folder.mkdir(parents=True)
            runner.save(folder / "annotations-used.json", {"source": "qwen", "requested_budget": 100, "annotations": [
                {"request_id": r.request_id, "event_id": r.event_id, "action": r.action, "reward": r.reward}
                for r in self.annotations]})
        self.output = self.root / "artifacts/clinical-dmplus-budget-bootstrap/synthetic-100"
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
            output_directory=str(self.output), max_new_draws=limit, model_key="qwen", annotation_budget=100)

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
        path=self.point_source / "potassium/gender/100/annotations-used.json"
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

    def test_budget_reaches_core_and_new_output_namespace(self):
        self.invoke()
        record=json.loads((self.output / "gender/draw-000/result.json").read_text())
        self.assertEqual(record["requested_annotation_budget"],100)
        self.assertEqual(self.manifest()["requested_annotation_budget"],100)
        self.assertEqual(self.manifest()["protocol"]["requested_annotation_budget"],100)
        self.assertEqual(self.manifest()["results"]["gender"]["requested_annotation_budget"],100)
        self.assertEqual(record["population_draw_metadata"],self.originals["gender"][0]["population_draw_metadata"])
        self.assertEqual(record["original_dm_value"],self.originals["gender"][0]["dm_value"])
        self.assertEqual({c.args[4] for c in self.prefix.call_args_list},{100})

    def test_each_fixed_budget_uses_its_own_point_cache_and_record_binding(self):
        for budget in (200,300,400,500):
            for split in SPLITS:
                self.points["tasks"]["potassium"]["results"][split][str(budget)]=dict(
                    self.points["tasks"]["potassium"]["results"][split]["100"])
                folder=self.point_source / "potassium" / split / str(budget)
                folder.mkdir()
                runner.save(folder / "annotations-used.json",{"source":"qwen","requested_budget":budget,
                    "annotations":[{"request_id":a.request_id,"event_id":a.event_id,"action":a.action,"reward":a.reward}
                        for a in self.annotations]})
            output=self.output.parent / ("synthetic-"+str(budget))
            runner.run(dm_bootstrap_directory=str(self.source),point_directory=str(self.point_source),
                output_directory=str(output),model_key="qwen",annotation_budget=budget,max_new_draws=1)
            record=json.loads((output / "gender/draw-000/result.json").read_text())
            self.assertEqual(record["requested_annotation_budget"],budget)
            self.assertEqual(record["unique_cachevalid_annotations"],2)
            self.assertEqual(record["original_dm_value"],self.originals["gender"][0]["dm_value"])

    def test_new_budget_must_be_explicit_supported_integer(self):
        for value in (None,0,1,99,101,-100,True,"100"):
            with self.subTest(budget=value), self.assertRaisesRegex(ValueError,"Explicit annotation budget"):
                runner.run(dm_bootstrap_directory=str(self.source),point_directory=str(self.point_source),
                    output_directory=str(self.output),model_key="qwen",annotation_budget=value,max_new_draws=1)
        self.assertFalse(self.output.exists())

    def test_resume_cannot_change_requested_budget(self):
        self.invoke()
        with self.assertRaisesRegex(ValueError,"original recorded inputs"):
            runner.run(resume_directory=str(self.output),annotation_budget=200,max_new_draws=1)

    def test_committed_budget_mix_is_rejected_even_if_hash_is_rebound(self):
        self.invoke()
        path=self.output / "gender/draw-000/result.json"
        data=json.loads(path.read_text());data["requested_annotation_budget"]=200
        runner.save(path,data)
        manifest=self.manifest();manifest["committed_result_hashes"]["gender/draw-000/result.json"]=runner.sha(path)
        runner.save(self.output / "manifest.json",manifest)
        with self.assertRaisesRegex(ValueError,"draw identity mismatch"):
            self.invoke(resume=True)

    def test_wrong_budget_cache_is_rejected_before_fit(self):
        path=self.point_source / "potassium/gender/100/annotations-used.json"
        data=json.loads(path.read_text());data["requested_budget"]=200
        runner.save(path,data)
        with mock.patch.object(runner,"run_paired_draw",side_effect=self.track):
            with self.assertRaisesRegex(ValueError,"prefix changed"):self.invoke()
        self.assertEqual(self.calls,[])

    def test_zero_budget_exactly_reuses_original_dm_and_payload(self):
        split="gender";original=self.originals[split][0];folder=self.source / split / "draw-000"
        payload=json.loads((folder / "models.json").read_text())
        with np.load(folder / "patient-counts.npz",allow_pickle=False) as data:counts={k:data[k] for k in data.files}
        record,fitted=self.engine(self.dataset,self.populations[split],original,payload,counts,(),requested_budget=0)
        for key in ("dm_value","signed_error","squared_error","observed_reference_value"):
            self.assertEqual(record[key],original[key])
        self.assertEqual(fitted["reward_model_plus"],payload["reward_model"])
        self.assertTrue(record["zero_selected_annotation_identity"])

    def test_suffix_must_match_budget_and_existing_namespace_is_rejected(self):
        for name in ("artifacts/clinical-dmplus-budget-bootstrap/wrong-200","artifacts/clinical-dmplus-bootstrap/wrong-100"):
            with self.subTest(name=name),self.assertRaises(ValueError):
                runner.run(dm_bootstrap_directory=str(self.source),point_directory=str(self.point_source),
                    output_directory=str(self.root / name),model_key="qwen",annotation_budget=100,max_new_draws=1)
            self.assertFalse((self.root / name).exists())

    def test_verification_output_requires_finite_draw_limit(self):
        with self.assertRaisesRegex(ValueError,"bounded draw limit"):
            runner.run(dm_bootstrap_directory=str(self.source),point_directory=str(self.point_source),
                output_directory=str(self.root / "verify-100"),model_key="qwen",annotation_budget=100,
                verification_root=str(self.root))


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

    def test_protocol_keeps_math_settings_and_exposes_only_fixed_prefix_budgets(self):
        import tomllib
        old=tomllib.loads((repository / "config/clinical-dmplus-bootstrap-models.toml").read_text())
        new=tomllib.loads(runner.source_path(runner.PROTOCOL).read_text())
        runner.validate_protocol(new)
        changed={"rule_version","status","requested_annotation_budget","budget_selection","annotation_draw_count"}
        for key,value in old.items():
            if key not in changed: self.assertEqual(new[key],value,key)
        self.assertEqual(new["requested_annotation_budgets"],[100,200,300,400,500])



if __name__ == "__main__":
    unittest.main()
