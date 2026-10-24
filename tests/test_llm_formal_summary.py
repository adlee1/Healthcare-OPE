"""Synthetic formal/cache/raw replay only; no providers or patient data."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import april_repro
STAGE = Path(__file__).resolve().parents[1]
if str(STAGE / "src/april_repro") not in april_repro.__path__:
    april_repro.__path__.insert(0, str(STAGE / "src/april_repro"))
from april_repro import llm_formal_summary as summary
from april_repro.decision_features import FEATURES
from april_repro.llm_requests import build_request
from april_repro.llm_five_requests import build_five_request
from april_repro.llm_receipts import normalize_receipt
from april_repro.llm_retries import execute_with_retries


def write(path, value):
    path.write_bytes(summary._encoded(value))


class FormalSummaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="synthetic-formal-summary-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.rows, labels = [], {}
        for model in ("gpt-4o-mini", "kimi"):
            for index, mode in enumerate(("factual", "factual", "counterfactual")):
                base = build_request(event_id_sha256=hashlib.sha256(str(index).encode()).hexdigest(),
                    input_manifest_sha256="a" * 64, task="potassium", mode=mode,
                    observed_action=10, action=10 if mode == "factual" else 40,
                    model_key="gpt-4o-mini", features={name: None for name in FEATURES})
                row = build_five_request(base, model)
                row["consumers"] = [{"split": split, "mode": mode,
                    "fold": "validation" if mode == "factual" else "train",
                    "rank": index + 1 if mode == "factual" else 1}
                    for split in (("gender", "comorbidity") if index == 0 else ("gender",))]
                self.rows.append(row)
                if mode == "factual":
                    labels[row["request_id"]] = 4.0 + index
        directory = self.root / "formal"
        directory.mkdir()
        self.plan = SimpleNamespace(directory=directory, manifest_sha256="b" * 64,
            requests={row["request_id"]: row for row in self.rows}, labels=labels,
            reused={}, pilot_evidence={"raw_receipts_revalidated": True},
            manifest={"selection": {"counterfactual_budget_grid": [0, 100, 200, 300, 400, 500]}})
        patcher = mock.patch.object(summary, "load_formal_plan", return_value=self.plan)
        patcher.start()
        self.addCleanup(patcher.stop)
        source_patcher = mock.patch.object(summary, "execution_source_hashes", return_value={"synthetic.py": "c" * 64})
        source_patcher.start()
        self.addCleanup(source_patcher.stop)

    def result(self, folder, row, *, retry=False, invalid=False):
        folder.mkdir(parents=True, exist_ok=True)
        rid = row["request_id"]
        def stem(number):
            return rid if number == 1 else rid + f".attempt-{number:02d}"
        def before(number):
            write(folder / (stem(number) + ".started.json"), {"request_id": rid,
                "status": "attempt_started", "attempt_number": number})
        count = 0
        def send(request, settings, **kwargs):
            nonlocal count
            count += 1
            failed = retry and count == 1
            raw = summary._encoded({"error": {"message": "temporary"}}) if failed else summary._encoded({
                "model": row["payload"]["model"], "usage": {"total_tokens": 13},
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant",
                    "content": "bad json" if invalid else json.dumps({"predicted_lab_value": 4.0,
                    "justification": "Synthetic numerical example"})}}]})
            return normalize_receipt(request, raw, http_status=503 if failed else 200), raw
        def after(number, receipt, raw, decision):
            (folder / (stem(number) + ".raw")).write_bytes(raw)
            receipt.update(attempt_number=number, retry_decision=decision, raw_response_sha256=summary._sha(raw))
            path = folder / (stem(number) + ".receipt.json")
            write(path, receipt)
            return {"started": stem(number) + ".started.json", "raw": stem(number) + ".raw",
                "receipt": path.name, "receipt_sha256": summary._sha(path.read_bytes())}
        result = execute_with_retries(row, {}, before_attempt=before, after_attempt=after,
            send=send, sleeper=lambda _: None, uniform=lambda a, b: a)
        write(folder / (rid + ".annotation.json"), result)
        return result

    def cache_first(self):
        row = self.rows[0]
        folder = self.root / "pilot-run"
        result = self.result(folder, row)
        final, attempts = summary.pilot._annotation(folder, row, result)
        rid = row["request_id"]
        self.plan.reused[rid] = {"request_id": rid, "run_directory": str(folder),
            "consumers": copy.deepcopy(row["consumers"]), "missing": False, "status": "valid",
            "attempt_count": len(attempts), "parsed_prediction": final["parsed_prediction"],
            "response_model": final["response_model"]}
        return row

    def build_run(self, rows=(), *, retry=False, invalid=False, active=False):
        folder = self.root / "run"
        folder.mkdir()
        for model in {row["metadata"]["model_key"] for row in self.rows}:
            (folder / "requests" / model).mkdir(parents=True)
        write(folder / "plan.json", {"scope": "formal_main_annotation_run",
            "formal_plan_directory": str(self.plan.directory),
            "formal_manifest_sha256": self.plan.manifest_sha256,
            "request_ids": list(self.plan.requests), "reused_request_ids": list(self.plan.reused),
            "new_request_ids": sorted(set(self.plan.requests) - set(self.plan.reused)), "max_retries": 2,
            "source_sha256": {"synthetic.py": "c" * 64}})
        (folder / "reused-annotations.jsonl").write_bytes(b"".join(
            summary._encoded(row) for row in self.plan.reused.values()))
        for row in rows:
            self.result(folder / "requests" / row["metadata"]["model_key"], row, retry=retry, invalid=invalid)
        if active:
            write(folder / "status.json", {"status": "active"})
        return folder

    def collect(self, run=None):
        return summary.summarize_formal_run(self.plan.directory, run)

    def test_cache_uses_formal_consumers_and_unique_all_event_denominator(self):
        cached = self.cache_first()
        run = self.build_run(self.rows[1:])
        report, rows = self.collect(run)
        self.assertEqual(report["completed_annotations"], 6)
        self.assertEqual(report["reused_annotations"], 1)
        self.assertEqual(report["recorded_attempt_count"], 5)
        self.assertEqual(report["cached_pilot_attempt_count"], 1)
        row = next(row for row in rows if row["request_id"] == cached["request_id"])
        self.assertEqual(len(row["consumers"]), 2)
        cells = {row["split"]: row for row in report["factual_evaluations"] if row["model_key"] == "gpt-4o-mini"}
        self.assertEqual(cells["all_unique_events"]["requested_predictions"], 2)
        self.assertEqual(cells["comorbidity"]["valid_predictions"], 1)
        self.assertEqual(cells["all_unique_events"]["weighted_f1"], 1 / 3)
        self.assertEqual(cells["all_unique_events"]["lab_mae"], .5)
        self.assertEqual(report["counterfactual_500_cells_ready"], 0)

    def test_missing_invalid_and_short_budget_never_become_completed_500(self):
        run = self.build_run(self.rows[:1], invalid=True)
        report, rows = self.collect(run)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["missing_predictions"], 5)
        self.assertEqual(report["invalid_predictions_including_missing"], 6)
        self.assertEqual(report["invalid_completed_predictions"], 1)
        factual = next(r for r in report["factual_evaluations"] if r["split"] == "all_unique_events" and r["model_key"] == "gpt-4o-mini")
        self.assertEqual(factual["requested_predictions"], 2)
        self.assertEqual(factual["coverage"], 0)
        self.assertIsNone(factual["weighted_f1"])
        for cell in report["cells"]:
            for prefix in cell["budget_prefixes"]:
                if prefix["requested_budget"]:
                    self.assertFalse(prefix["annotation_budget_ready"])

    def test_retries_count_once_per_annotation_and_keep_attempt_failures(self):
        run = self.build_run(self.rows, retry=True)
        report, rows = self.collect(run)
        self.assertEqual(report["recorded_attempt_count"], 12)
        self.assertEqual(report["automatic_retries"], 6)
        self.assertEqual(report["valid_predictions"], 6)
        self.assertEqual(sum(row["failed_attempt_count"] for row in report["groups"]), 6)
        self.assertEqual(sum(row["token_usage_completed_annotations_all_attempts"].get("total_tokens", 0) for row in report["groups"]), 78)
        self.assertTrue(all(row["attempt_count"] == 2 for row in rows))

    def test_active_inflight_and_durable_hold_are_missing_with_distinct_counts(self):
        run = self.build_run(active=True)
        row = self.rows[0]
        folder, rid = run / "requests" / row["metadata"]["model_key"], row["request_id"]
        write(folder / (rid + ".started.json"), {"request_id": rid, "attempt_number": 1, "status": "attempt_started"})
        report, _ = self.collect(run)
        self.assertEqual(report["held_requests"], 0)
        self.assertEqual(report["pending_requests"], 6)
        self.assertEqual(report["attempts_without_final_annotation"], 1)
        write(folder / (rid + ".held.json"), {"request_id": rid, "status": "held", "reason": "unknown", "automatic_resend": False})
        report, _ = self.collect(run)
        self.assertEqual(report["held_requests"], 1)
        self.assertEqual(report["missing_predictions"], 6)

    def test_cache_and_new_duplicate_source_is_rejected(self):
        row = self.cache_first()
        run = self.build_run([row])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.collect(run)

    def test_raw_tampering_in_new_and_cached_results_is_rejected(self):
        row = self.cache_first()
        run = self.build_run(self.rows[1:2])
        path = Path(self.plan.reused[row["request_id"]]["run_directory"]) / (row["request_id"] + ".raw")
        before = path.read_bytes()
        path.write_bytes(before + b" ")
        with self.assertRaisesRegex(ValueError, "Raw response hash"):
            self.collect(run)
        path.write_bytes(before)
        row = self.rows[1]
        path = run / "requests" / row["metadata"]["model_key"] / (row["request_id"] + ".raw")
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "Raw response hash"):
            self.collect(run)

    def test_plan_partition_and_saved_cache_are_verified(self):
        self.cache_first()
        run = self.build_run()
        path = run / "reused-annotations.jsonl"
        path.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "cache"):
            self.collect(run)
        path.write_bytes(b"".join(summary._encoded(row) for row in self.plan.reused.values()))
        path = run / "plan.json"
        plan = json.loads(path.read_bytes())
        plan["new_request_ids"].append(plan["new_request_ids"][0])
        write(path, plan)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.collect(run)

    def test_false_complete_manifest_and_bad_rank_fail(self):
        run = self.build_run(self.rows)
        write(run / "manifest.json", {"status": "complete", "unique_requests": 999})
        with self.assertRaisesRegex(ValueError, "manifest counts"):
            self.collect(run)
        (run / "manifest.json").unlink()
        self.rows[1]["consumers"][0]["rank"] = 500
        with self.assertRaisesRegex(ValueError, "ranks"):
            self.collect(run)

    def test_execution_source_change_is_rejected_before_collection(self):
        run = self.build_run()
        path = run / "plan.json"
        saved = json.loads(path.read_bytes())
        saved["source_sha256"]["synthetic.py"] = "d" * 64
        write(path, saved)
        with self.assertRaisesRegex(ValueError, "source identity"):
            self.collect(run)

    def test_outputs_private_hashed_and_no_overwrite(self):
        run = self.build_run(self.rows)
        output = self.root / "summary"
        report = summary.write_summary(self.plan.directory, run, output)
        self.assertEqual(report["status"], "complete")
        self.assertFalse(report["paper_experiment_complete"])
        self.assertFalse(report["dm_plus_fitted"])
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
        manifest = json.loads((output / "manifest.json").read_bytes())
        for path in output.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        for name, digest in manifest["outputs"].items():
            self.assertEqual(summary._sha((output / name).read_bytes()), digest)
        with self.assertRaisesRegex(ValueError, "already exists"):
            summary.write_summary(self.plan.directory, run, output)

    def test_cli_only_emits_aggregate_counts_and_paths(self):
        spec = importlib.util.spec_from_file_location("formal_summary_cli", STAGE / "scripts/summarize_formal_llm_run.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            status = cli.main(["--plan-directory", str(self.plan.directory), "--output-directory", str(self.root / "cli")])
        self.assertEqual(status, 0)
        self.assertNotIn(self.rows[0]["request_id"], stream.getvalue())
        self.assertNotIn("Synthetic numerical", stream.getvalue())
        self.assertEqual(json.loads(stream.getvalue())["missing_predictions"], 6)


if __name__ == "__main__":
    unittest.main()
