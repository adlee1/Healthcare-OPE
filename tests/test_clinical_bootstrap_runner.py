"""Tiny synthetic fit/commit/resume checks; no database or clinical files."""

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


AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "scipy", "sklearn", "threadpoolctl"))
PROJECT = Path(__file__).resolve().parents[1]
if AVAILABLE:
    import numpy as np
    from april_repro.clinical_dataset import ClinicalDataset, FOLD_CODES, ROLE_CODES
    from april_repro import clinical_models
    from april_repro.cohort_splits import SPLITS
    from april_repro.decision_features import FEATURES

    spec = importlib.util.spec_from_file_location("clinical_bootstrap_runner_tested", PROJECT / "scripts/run_clinical_bootstrap.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)


@unittest.skipUnless(AVAILABLE, "Optional pinned modeling dependencies are not installed")
class ClinicalBootstrapRunnerTests(unittest.TestCase):
    def setUp(self):
        original_umask = os.umask(0o077)
        os.umask(original_umask)
        self.addCleanup(os.umask, original_umask)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        model_repo = Path(clinical_models.__file__).resolve().parents[2]
        for relative in runner.CODE_PATHS:
            source = PROJECT / relative
            if not source.exists():
                if relative.startswith("src/april_repro/"):
                    module_name = "april_repro." + Path(relative).stem
                    module = sys.modules.get(module_name)
                    source = Path(module.__file__) if module else model_repo / relative
                else:
                    source = model_repo / relative
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        self.source = self.root / "artifacts/treatment-features/synthetic"
        self.source.mkdir(parents=True)
        self.input_manifest = self.source / "manifest.json"
        self.input_manifest.write_text('{"synthetic_fixture": true}\n')
        self.dataset = self.synthetic_dataset()
        self.calls = []
        self.original_engine = runner.run_dm_draw
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(runner, "ROOT", self.root))
        self.loader = self.stack.enter_context(mock.patch.object(runner, "load_clinical_dataset", return_value=self.dataset))
        self.git = self.stack.enter_context(mock.patch.object(runner.subprocess, "run", return_value=SimpleNamespace(returncode=0)))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def synthetic_dataset(self):
        # Two train subjects per role, two target-validation subjects, plus
        # behavior-validation/excluded rows that must never enter these draws.
        subjects = np.array([1, 1, 2, 3, 3, 4, 5, 5, 6, 7, 8], dtype=np.int64)
        roles = np.empty((len(subjects), len(SPLITS)), dtype=np.int8)
        folds = np.empty(len(subjects), dtype=np.int8)
        for i, subject in enumerate(subjects):
            role = "behavior" if subject in (1, 2, 7) else "target" if subject <= 6 else "excluded"
            roles[i, :] = ROLE_CODES[role]
            folds[i] = FOLD_CODES["train" if subject <= 4 else "validation"]
            if subject in (5, 6):
                roles[i, SPLITS.index("dosage")] = ROLE_CODES["excluded"]
        features = np.full((len(subjects), len(FEATURES)), np.nan)
        features[:, 0] = 25 + subjects * 4
        features[:, 1] = subjects % 2
        return ClinicalDataset(
            task="potassium", event_ids=tuple(hashlib.sha256(f"synthetic-event-{i}".encode()).hexdigest() for i in range(len(subjects))),
            subject_ids=subjects, hadm_ids=subjects + 100, features=features,
            actions=np.zeros(len(subjects), dtype=np.int64),
            post_labs=np.full(len(subjects), 4.0), rewards=0.6 + subjects / 100,
            roles=roles, folds=folds, summary={},
            provenance={"manifest_sha256": runner.sha(self.input_manifest)},
        )

    def invoke(self, *, resume=None, limit=1):
        return runner.run(
            input_directory=str(self.source.relative_to(self.root)) if resume is None else None,
            resume_directory=str(resume.relative_to(self.root)) if resume else None,
            max_new_draws=limit,
        )

    def manifest(self, artifact):
        return json.loads((artifact / "manifest.json").read_text())

    def engine(self, dataset, populations, draw_id, **kwargs):
        split = next(iter(populations.values())).split
        self.calls.append((split, draw_id))
        return self.original_engine(dataset, populations, draw_id, **kwargs)

    def test_pilot_resume_preserves_failed_draws_and_skips_empty_population(self):
        def engine(dataset, populations, draw_id, **kwargs):
            record, payload, draws = self.engine(dataset, populations, draw_id, **kwargs)
            if record["split"] == "comorbidity" and draw_id == 0:
                record = {key: value for key, value in record.items() if key not in
                          ("dm_value", "observed_reference_value", "signed_error", "squared_error")}
                record.update(status="failed", reason="synthetic_nonconvergence")
            return record, payload, draws
        with mock.patch.object(runner, "run_dm_draw", side_effect=engine):
            artifact = self.invoke(limit=3)
            first = self.manifest(artifact)
            self.assertEqual(self.calls, [("gender", 0), ("comorbidity", 0), ("gender", 1)])
            self.assertEqual(first["status"], "in_progress")
            self.assertEqual(first["results"]["gender"]["completed_draws"], 2)
            self.assertEqual(first["results"]["comorbidity"]["failed_draws"], 1)
            self.assertEqual(first["results"]["dosage"]["status"], "not_estimable")
            self.assertEqual(first["results"]["dosage"]["empty_populations"], ["target_validation"])
            self.assertEqual(first["results"]["dosage"]["attempted_draws"], 0)
            self.assertIsNone(first["results"]["gender"]["primary_metrics"])
            original_files = {str(path.relative_to(artifact)): path.read_bytes() for path in artifact.glob("*/draw-*/*")}
            resumed = self.invoke(resume=artifact, limit=2)
        self.assertEqual(resumed, artifact)
        self.assertEqual(self.calls, [("gender", 0), ("comorbidity", 0), ("gender", 1), ("comorbidity", 1), ("gender", 2)])
        final = self.manifest(artifact)
        self.assertEqual([session["new_draws"] for session in final["execution_sessions"]], [3, 2])
        self.assertEqual(final["results"]["gender"]["completed_draws"], 3)
        self.assertEqual(final["results"]["comorbidity"]["completed_draws"], 1)
        self.assertEqual(final["results"]["comorbidity"]["failed_draw_ids"], [0])
        self.assertEqual(final["results"]["comorbidity"]["pending_draws"], 498)
        self.assertEqual(len(final["committed_result_hashes"]), 5)
        for relative, content in original_files.items():
            self.assertEqual((artifact / relative).read_bytes(), content)
        for relative, digest in final["committed_result_hashes"].items():
            self.assertEqual(runner.sha(artifact / relative), digest)
        with np.load(artifact / "gender/draw-000/patient-counts.npz") as counts:
            np.testing.assert_array_equal(counts["behavior_train_subject_ids"], [1, 2])
            np.testing.assert_array_equal(counts["target_train_subject_ids"], [3, 4])
            np.testing.assert_array_equal(counts["target_validation_subject_ids"], [5, 6])
            for population in runner.POPULATIONS:
                self.assertEqual(int(counts[population + "_patient_counts"].sum()), 2)

    def test_resume_rejects_changed_input_code_and_saved_code_before_new_fit(self):
        with mock.patch.object(runner, "run_dm_draw", side_effect=self.engine):
            artifact = self.invoke()
            cases = [
                (self.input_manifest, "Resume input manifest changed"),
                (self.root / "src/april_repro/clinical_models.py", "identical code"),
                (artifact / "code/src/april_repro/clinical_models.py", "Saved code copy hash mismatch"),
            ]
            for path, message in cases:
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"\n ")
                    with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, message):
                        self.invoke(resume=artifact)
                finally:
                    path.write_bytes(original)
        self.assertEqual(self.calls, [("gender", 0)])

    def test_resume_rejects_committed_payload_and_consistently_altered_result(self):
        with mock.patch.object(runner, "run_dm_draw", side_effect=self.engine):
            artifact = self.invoke()
            for name in ("models.json", "patient-counts.npz"):
                path = artifact / "gender/draw-000" / name
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b" ")
                    with self.subTest(name=name), self.assertRaisesRegex(ValueError, "output hash mismatch"):
                        self.invoke(resume=artifact)
                finally:
                    path.write_bytes(original)
            path = artifact / "gender/draw-000/result.json"
            record = json.loads(path.read_text())
            record["dm_value"] += 0.1
            record["signed_error"] = record["dm_value"] - record["observed_reference_value"]
            record["squared_error"] = record["signed_error"] ** 2
            runner.save(path, record)
            with self.assertRaisesRegex(ValueError, "[Rr]esult.*hash|[Cc]ommitted.*changed"):
                self.invoke(resume=artifact)
        self.assertEqual(self.calls, [("gender", 0)])

    def test_atomic_draw_committed_before_manifest_checkpoint_is_recovered_without_replacement(self):
        with mock.patch.object(runner, "run_dm_draw", side_effect=self.engine):
            artifact = self.invoke()
            old = self.manifest(artifact)
            old["committed_result_hashes"] = {}
            # Simulate power loss after atomic draw publication but before its
            # manifest checkpoint. The directory remains complete and valid.
            old["results"]["gender"]["completed_draws"] = 0
            runner.save(artifact / "manifest.json", old)
            self.invoke(resume=artifact)
        self.assertEqual(self.calls, [("gender", 0), ("comorbidity", 0)])
        final = self.manifest(artifact)
        self.assertEqual(final["results"]["gender"]["completed_draws"], 1)
        self.assertEqual(final["results"]["comorbidity"]["completed_draws"], 1)
        self.assertEqual(len(final["committed_result_hashes"]), 2)

    def test_unexpected_exception_retains_failed_id_and_resume_moves_forward(self):
        def broken(dataset, populations, draw_id, **kwargs):
            self.calls.append((next(iter(populations.values())).split, draw_id))
            raise ArithmeticError("synthetic unexpected error")
        with mock.patch.object(runner, "run_dm_draw", side_effect=broken):
            with self.assertRaisesRegex(RuntimeError, "failed ID retained"):
                self.invoke()
        artifact, = (self.root / "artifacts/clinical-bootstrap").iterdir()
        interrupted = self.manifest(artifact)
        self.assertEqual(interrupted["status"], "interrupted")
        self.assertEqual(interrupted["results"]["gender"]["failed_draw_ids"], [0])
        self.assertEqual(len(interrupted["committed_result_hashes"]), 1)
        with mock.patch.object(runner, "run_dm_draw", side_effect=self.engine):
            self.invoke(resume=artifact)
        self.assertEqual(self.calls, [("gender", 0), ("comorbidity", 0)])
        self.assertEqual(self.manifest(artifact)["results"]["gender"]["failed_draw_ids"], [0])


if __name__ == "__main__":
    unittest.main()
