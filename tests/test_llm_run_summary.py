"""Synthetic receipts only: no clinical rows, credentials, or network access."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest

import april_repro
STAGE = Path(__file__).resolve().parents[1]
if str(STAGE / "src/april_repro") not in april_repro.__path__:
    april_repro.__path__.insert(0, str(STAGE / "src/april_repro"))
from april_repro import llm_run_summary as summary
from april_repro.decision_features import FEATURES
from april_repro.llm_requests import build_request
from april_repro.llm_five_requests import build_five_request
from april_repro.llm_receipts import normalize_receipt
from april_repro.llm_retries import execute_with_retries


def write(path, value):
    path.write_bytes(summary._encoded(value))


class RunSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-llm-summary-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.packet, self.rows, self.labels = self.make_packet("potassium")

    def make_packet(self, task):
        folder = self.root / task
        folder.mkdir()
        rows, labels = [], []
        for index, mode in enumerate(("factual", "factual", "counterfactual")):
            observed, alternative = (10, 40) if task == "potassium" else (100, 300)
            event = hashlib.sha256((task + str(index)).encode()).hexdigest()
            base = build_request(event_id_sha256=event, input_manifest_sha256="a" * 64,
                mode=mode, task=task, observed_action=observed,
                action=observed if mode == "factual" else alternative,
                model_key="gpt-4o-mini", features={key: None for key in FEATURES})
            base["consumers"] = [{"split": split, "mode": mode,
                "fold": "validation" if mode == "factual" else "train", "rank": index + 1}
                for split in (("gender", "comorbidity") if index == 0 else ("gender",))]
            for model in ("gpt-4o-mini", "kimi"):
                row = build_five_request(base, model)
                rows.append(row)
                if mode == "factual":
                    labels.append({"request_id": row["request_id"], "protocol_id": row["protocol_id"],
                        "prompt_sha256": row["prompt_sha256"], "task": task, "action": observed,
                        "post_lab_value": (4.0 + index if task == "potassium" else 140.0 + index),
                        "input_manifest_sha256": "a" * 64})
        for name, values in (("requests.jsonl", rows), ("factual-labels.jsonl", labels)):
            (folder / name).write_bytes(b"".join(summary._encoded(row) for row in values))
        write(folder / "manifest.json", {"status": "complete", "scope": "offline_review_pilot",
            "rule_version": "llm-five-review-packet-v1", "task": task,
            "outputs": {name: summary._sha((folder / name).read_bytes())
                        for name in ("requests.jsonl", "factual-labels.jsonl")}})
        return folder, rows, labels

    def make_run(self, name, rows=None, *, packet=None, retry_first=False, malformed=False, complete=True):
        rows = self.rows if rows is None else rows
        packet = self.packet if packet is None else packet
        folder = self.root / name
        folder.mkdir()
        write(folder / "plan.json", {"packet_directory": str(packet),
            "packet_manifest_sha256": summary._sha((packet / "manifest.json").read_bytes()),
            "request_ids": [row["request_id"] for row in rows], "max_retries": 2})
        results = []
        for row in rows:
            rid = row["request_id"]
            count = 0
            def send(record, settings, **kwargs):
                nonlocal count
                count += 1
                failed = retry_first and count == 1
                raw = summary._encoded({"error": {"message": "temporary"}}) if failed else summary._encoded({
                    "model": row["payload"]["model"], "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
                    "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant",
                        "content": "not json" if malformed else json.dumps({"predicted_lab_value":
                            4.0 if row["metadata"]["task"] == "potassium" else 140.0,
                            "justification": "Synthetic numerical example"})}}]})
                receipt = normalize_receipt(record, raw, http_status=503 if failed else 200)
                receipt.update(raw_response_complete=True, remote_completion_unknown=False)
                return receipt, raw
            def stem(number):
                return rid if number == 1 else rid + f".attempt-{number:02d}"
            def before(number):
                write(folder / (stem(number) + ".started.json"), {
                    "request_id": rid, "attempt_number": number, "status": "attempt_started"})
            def after(number, receipt, raw, decision):
                (folder / (stem(number) + ".raw")).write_bytes(raw)
                receipt.update(raw_response_sha256=summary._sha(raw), attempt_number=number, retry_decision=decision)
                write(folder / (stem(number) + ".receipt.json"), receipt)
                return {"started": stem(number) + ".started.json", "raw": stem(number) + ".raw",
                    "receipt": stem(number) + ".receipt.json",
                    "receipt_sha256": summary._sha((folder / (stem(number) + ".receipt.json")).read_bytes())}
            result = execute_with_retries(row, {}, before_attempt=before, after_attempt=after,
                send=send, sleeper=lambda _: None, uniform=lambda a, b: a)
            write(folder / (rid + ".annotation.json"), result)
            results.append(result)
        if complete:
            write(folder / "manifest.json", {"status": "complete", "results": results,
                "external_calls": sum(r["attempt_count"] for r in results), "unique_annotation_requests": len(results),
                "automatic_retries": sum(r["automatic_retries"] for r in results),
                "valid_predictions": sum(r["status"] == "valid" for r in results),
                "invalid_predictions": sum(r["status"] != "valid" for r in results)})
        return folder

    def collect(self, *runs):
        return summary.summarize_runs([self.packet], runs)

    def rebind_receipt(self, run, result):
        write(run / (result["request_id"] + ".annotation.json"), result)
        manifest = json.loads((run / "manifest.json").read_bytes())
        manifest["results"] = [result if r["request_id"] == result["request_id"] else r for r in manifest["results"]]
        write(run / "manifest.json", manifest)

    def test_disjoint_warmup_and_remaining_runs_have_unique_event_metrics(self):
        left = self.make_run("warmup", self.rows[:1])
        right = self.make_run("remaining", self.rows[1:])
        report, rows = self.collect(left, right)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["valid_predictions"], 6)
        self.assertEqual(report["recorded_attempt_count"], 6)
        self.assertEqual(len(rows), 6)
        for model in ("gpt-4o-mini", "kimi"):
            all_events = next(r for r in report["factual_evaluations"] if r["model_key"] == model and r["split"] == "all_unique_events")
            self.assertEqual(all_events["requested_predictions"], 2)
            self.assertEqual(all_events["lab_mae"], .5)
            self.assertAlmostEqual(all_events["lab_rmse"], .5 ** .5)
            self.assertEqual(all_events["weighted_f1"], 1 / 3)
            subgroup = next(r for r in report["factual_evaluations"] if r["model_key"] == model and r["split"] == "comorbidity")
            self.assertEqual(subgroup["requested_predictions"], 1)
        self.assertTrue(all(r["parsed_prediction"]["reward"] is not None for r in rows if r["mode"] == "counterfactual"))

    def test_retry_attempts_do_not_duplicate_annotations_or_tokens(self):
        run = self.make_run("retry", retry_first=True)
        report, rows = self.collect(run)
        self.assertEqual(report["completed_annotations"], 6)
        self.assertEqual(report["recorded_attempt_count"], 12)
        self.assertEqual(report["automatic_retries"], 6)
        self.assertEqual(sum(r["failed_attempt_count"] for r in report["groups"]), 6)
        self.assertEqual(sum(r["token_usage_all_attempts"].get("total_tokens", 0) for r in report["groups"]), 78)
        self.assertTrue(all(r["attempt_count"] == 2 for r in rows))

    def test_missing_and_invalid_remain_in_factual_denominator(self):
        run = self.make_run("invalid", self.rows[:1], malformed=True)
        report, rows = self.collect(run)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["missing_predictions"], 5)
        self.assertEqual(report["valid_predictions"], 0)
        overall = next(r for r in report["factual_evaluations"] if r["model_key"] == "gpt-4o-mini" and r["split"] == "all_unique_events")
        self.assertEqual(overall["requested_predictions"], 2)
        self.assertEqual(overall["coverage"], 0)
        self.assertIsNone(overall["weighted_f1"])
        self.assertEqual(sum(r["reason"] == "missing_receipt" for r in rows), 5)

    def test_interrupted_run_preserves_saved_results_and_missing(self):
        run = self.make_run("interrupted", self.rows[:1], complete=False)
        plan = json.loads((run / "plan.json").read_bytes())
        plan["request_ids"] = [row["request_id"] for row in self.rows]
        write(run / "plan.json", plan)
        report, _ = self.collect(run)
        self.assertEqual(report["completed_annotations"], 1)
        self.assertEqual(report["missing_predictions"], 5)
        self.assertEqual(report["runs"][0]["status"], "interrupted_or_in_progress")
        self.assertEqual(report["planned_requests_without_final_annotation"], 5)
        self.assertTrue(report["unresolved_requests_may_have_remote_attempts"])

    def test_duplicate_runs_requests_and_packets_are_rejected(self):
        run = self.make_run("first", self.rows[:1])
        duplicate = self.make_run("second", self.rows[:1])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.collect(run, duplicate)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            summary.summarize_runs([self.packet, self.packet], [])

    def test_packet_hash_label_identity_and_plan_binding_are_validated(self):
        run = self.make_run("run")
        path = self.packet / "factual-labels.jsonl"
        old = path.read_bytes()
        path.write_bytes(old + b"\n")
        with self.assertRaisesRegex(ValueError, "hash"):
            self.collect(run)
        path.write_bytes(old)
        plan = json.loads((run / "plan.json").read_bytes())
        plan["packet_manifest_sha256"] = "0" * 64
        write(run / "plan.json", plan)
        with self.assertRaisesRegex(ValueError, "provenance"):
            self.collect(run)

    def test_raw_and_receipt_tampering_is_rejected(self):
        run = self.make_run("run")
        path = run / (self.rows[0]["request_id"] + ".raw")
        old = path.read_bytes()
        path.write_bytes(old + b" ")
        with self.assertRaisesRegex(ValueError, "Raw response hash"):
            self.collect(run)
        path.write_bytes(old)
        path = run / (self.rows[0]["request_id"] + ".receipt.json")
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "Receipt hash"):
            self.collect(run)

    def test_rehashed_forged_prediction_is_rejected_by_raw_renormalization(self):
        run = self.make_run("run")
        rid = self.rows[0]["request_id"]
        result = json.loads((run / (rid + ".annotation.json")).read_bytes())
        path = run / result["final_receipt"]
        receipt = json.loads(path.read_bytes())
        receipt["parsed_prediction"]["predicted_lab_value"] = 99
        write(path, receipt)
        result["attempts"][0]["files"]["receipt_sha256"] = summary._sha(path.read_bytes())
        self.rebind_receipt(run, result)
        with self.assertRaisesRegex(ValueError, "normalization"):
            self.collect(run)

    def test_path_traversal_and_attempt_count_mismatch_are_rejected(self):
        run = self.make_run("run")
        rid = self.rows[0]["request_id"]
        result = json.loads((run / (rid + ".annotation.json")).read_bytes())
        result["attempts"][0]["files"]["raw"] = "../secret"
        self.rebind_receipt(run, result)
        with self.assertRaisesRegex(ValueError, "local filename"):
            self.collect(run)
        result["attempt_count"] = 3
        self.rebind_receipt(run, result)
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            self.collect(run)

    def test_both_tasks_are_separate_and_cf_never_enters_factual_metrics(self):
        sodium, rows, _ = self.make_packet("sodium")
        krun = self.make_run("k")
        nrun = self.make_run("na", rows, packet=sodium)
        report, annotations = summary.summarize_runs([self.packet, sodium], [krun, nrun])
        self.assertEqual(report["valid_predictions"], 12)
        self.assertEqual(len(report["groups"]), 8)
        self.assertEqual({r["task"] for r in report["factual_evaluations"]}, {"potassium", "sodium"})
        self.assertEqual(sum(r["requested_predictions"] for r in report["factual_evaluations"] if r["split"] == "all_unique_events"), 8)

    def test_private_outputs_hashes_and_no_overwrite(self):
        run = self.make_run("run")
        output = self.root / "summary"
        report = summary.write_summary([self.packet], [run], output)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
        for path in output.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        manifest = json.loads((output / "manifest.json").read_bytes())
        for name, digest in manifest["outputs"].items():
            self.assertEqual(digest, summary._sha((output / name).read_bytes()))
        self.assertFalse(report["formal_paper_annotation_budget"])
        self.assertFalse(report["dm_plus_fitted"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            summary.write_summary([self.packet], [run], output)

    def test_cli_prints_only_aggregate_counts_and_paths(self):
        spec = importlib.util.spec_from_file_location("summary_cli", STAGE / "scripts/summarize_five_llm_runs.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = cli.main(["--packet-directory", str(self.packet), "--output-directory", str(self.root / "cli")])
        self.assertEqual(result, 0)
        printed = output.getvalue()
        self.assertNotIn(self.rows[0]["request_id"], printed)
        self.assertNotIn("Synthetic numerical", printed)
        self.assertEqual(json.loads(printed)["missing_predictions"], 6)


if __name__ == "__main__":
    unittest.main()
