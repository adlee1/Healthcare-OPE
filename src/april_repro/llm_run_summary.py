"""Offline pilot annotation collection; no provider calls or clinical CSV reads.

One request contributes one final annotation even if transport was retried.
Missing requests remain invalid in coverage denominators. Factual evaluation
uses the existing Appendix A bins and only valid predictions for F1/lab errors.
These small review packets are not the formal 500-annotation experiment.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

from april_repro.llm_five_requests import validate_request
from april_repro.llm_predictions import evaluate_factual_predictions, parse_prediction_response
from april_repro.llm_receipts import factual_record_from_receipt, normalize_receipt


SUMMARY_VERSION = "five-llm-pilot-summary-v1"
SPLITS = ("gender", "comorbidity", "dosage")


def _encoded(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False) + "\n").encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read_json(path):
    raw = path.read_bytes()
    return json.loads(raw), _sha(raw)


def _file(folder, name):
    if not isinstance(name, str) or not name or Path(name).name != name or name in (".", ".."):
        raise ValueError("Run artifact must be a local filename")
    path = folder / name
    if path.is_symlink():
        raise ValueError("Run artifacts cannot be symlinks")
    return path


def _packet(directory):
    folder = Path(directory).resolve()
    manifest, digest = _read_json(folder / "manifest.json")
    if (manifest.get("status") != "complete" or manifest.get("scope") != "offline_review_pilot"
            or manifest.get("rule_version") != "llm-five-review-packet-v1"):
        raise ValueError("Expected complete five-model review packet")
    content = {}
    for name in ("requests.jsonl", "factual-labels.jsonl"):
        raw = (folder / name).read_bytes()
        if _sha(raw) != manifest.get("outputs", {}).get(name):
            raise ValueError("Packet output hash mismatch")
        content[name] = [json.loads(line) for line in raw.splitlines()]
    requests = {}
    for record in content["requests.jsonl"]:
        validate_request(record)
        rid, meta = record["request_id"], record["metadata"]
        if rid in requests or meta["task"] != manifest["task"]:
            raise ValueError("Duplicate request or packet task mismatch")
        consumers = record.get("consumers")
        if not isinstance(consumers, list) or not consumers:
            raise ValueError("Request requires explicit evaluation consumers")
        seen = set()
        for consumer in consumers:
            split = consumer.get("split")
            if (split not in SPLITS or split in seen or consumer.get("mode") != meta["mode"]
                    or consumer.get("fold") != ("validation" if meta["mode"] == "factual" else "train")):
                raise ValueError("Invalid or duplicate request consumer")
            seen.add(split)
        requests[rid] = record
    labels = {}
    for label in content["factual-labels.jsonl"]:
        rid = label.get("request_id")
        if rid not in requests or rid in labels:
            raise ValueError("Duplicate or unrelated factual label")
        record, value = requests[rid], label.get("post_lab_value")
        meta = record["metadata"]
        if (meta["mode"] != "factual" or type(value) not in (int, float)
                or not math.isfinite(value) or value <= 0):
            raise ValueError("Invalid factual label")
        expected = {"request_id": rid, "protocol_id": record["protocol_id"],
                    "prompt_sha256": record["prompt_sha256"], "task": meta["task"],
                    "action": meta["action"], "post_lab_value": value,
                    "input_manifest_sha256": meta["input_manifest_sha256"]}
        if label != expected:
            raise ValueError("Factual label identity mismatch")
        labels[rid] = value
    if set(labels) != {rid for rid, row in requests.items() if row["metadata"]["mode"] == "factual"}:
        raise ValueError("Factual label coverage mismatch")
    return folder, digest, requests, labels


def _receipt(folder, request, attempt, number):
    refs = attempt.get("files", {})
    receipt_path = _file(folder, refs.get("receipt"))
    receipt, receipt_sha = _read_json(receipt_path)
    if receipt_sha != refs.get("receipt_sha256"):
        raise ValueError("Receipt hash mismatch")
    raw = _file(folder, refs.get("raw")).read_bytes()
    if _sha(raw) != receipt.get("raw_response_sha256"):
        raise ValueError("Raw response hash mismatch")
    started, _ = _read_json(_file(folder, refs.get("started")))
    if (started.get("request_id") != request["request_id"] or started.get("attempt_number") != number
            or started.get("status") != "attempt_started" or receipt.get("attempt_number") != number
            or attempt.get("attempt_number") != number):
        raise ValueError("Attempt identity mismatch")
    regenerated = normalize_receipt(request, raw, http_status=receipt.get("http_status"))
    # Transport read failures can contain a parseable but incomplete prefix.
    # Their saved failure marker deliberately overrides content normalization.
    if receipt.get("reason") == "network_error_remote_completion_unknown":
        if receipt.get("raw_response_complete") is not False or receipt.get("remote_completion_unknown") is not True:
            raise ValueError("Network failure lacks explicit transport markers")
        regenerated.update(status="invalid", reason="network_error_remote_completion_unknown", failure_layer="receipt",
                           parsed_prediction=parse_prediction_response(None, request["metadata"]["task"]).to_dict())
    if any(receipt.get(key) != value for key, value in regenerated.items()):
        raise ValueError("Saved receipt disagrees with raw response normalization")
    if (attempt.get("status") != receipt["status"] or attempt.get("reason") != receipt["reason"]
            or attempt.get("retry_decision") != receipt.get("retry_decision")):
        raise ValueError("Attempt summary and receipt disagree")
    return receipt


def _annotation(folder, request, result):
    rid = request["request_id"]
    if result.get("request_id") != rid:
        raise ValueError("Annotation request identity mismatch")
    attempts = result.get("attempts")
    if (not isinstance(attempts, list) or not 1 <= len(attempts) <= 3
            or result.get("attempt_count") != len(attempts)
            or result.get("automatic_retries") != len(attempts) - 1
            or result.get("final_attempt_number") != len(attempts)):
        raise ValueError("Annotation attempt count mismatch")
    receipts = []
    for number, attempt in enumerate(attempts, 1):
        receipt = _receipt(folder, request, attempt, number)
        decision = receipt.get("retry_decision", {})
        final = number == len(attempts)
        if decision.get("retry") is not (not final) or (not final and receipt["status"] == "valid"):
            raise ValueError("Invalid retry sequence or ignored valid response")
        receipts.append(receipt)
    final = receipts[-1]
    if (result.get("final_receipt") != attempts[-1]["files"]["receipt"]
            or result.get("status") != final["status"] or result.get("reason") != final["reason"]
            or result.get("stop_reason") != final["retry_decision"].get("reason")
            or result.get("remote_completion_unknown") != any(bool(r.get("remote_completion_unknown")) for r in receipts)):
        raise ValueError("Final annotation and attempt disagree")
    return final, receipts


def _usage(value, result, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            path = prefix + "." + key if prefix else key
            if isinstance(item, dict):
                _usage(item, result, path)
            elif type(item) in (int, float) and math.isfinite(item):
                result[path] += item


def summarize_runs(packet_directories, run_directories):
    """Return (aggregate summary, private annotation rows) for all packet requests.

    Multiple disjoint runs may reference each packet, including warmups. A run
    with no final manifest can contribute durable annotation files; unfinished
    requests remain explicitly missing. No automatic retry or resume occurs.
    """
    requests, labels, packets, packet_info = {}, {}, {}, []
    for directory in packet_directories:
        folder, digest, rows, values = _packet(directory)
        if digest in packets or set(rows) & set(requests):
            raise ValueError("Duplicate packet or annotation request")
        packets[digest] = (folder, rows)
        requests.update(rows)
        labels.update(values)
        packet_info.append({"directory": str(folder), "manifest_sha256": digest, "unique_requests": len(rows)})
    if not requests:
        raise ValueError("At least one nonempty review packet is required")
    assigned, completed, run_info = set(), {}, []
    for directory in run_directories:
        folder = Path(directory).resolve()
        plan, plan_sha = _read_json(folder / "plan.json")
        binding = packets.get(plan.get("packet_manifest_sha256"))
        if binding is None or Path(plan.get("packet_directory", "")).resolve() != binding[0]:
            raise ValueError("Run plan packet provenance mismatch")
        ids = plan.get("request_ids")
        if (not isinstance(ids, list) or not ids or any(not isinstance(rid, str) for rid in ids)
                or len(set(ids)) != len(ids) or not set(ids) <= set(binding[1]) or set(ids) & assigned):
            raise ValueError("Duplicate or unrelated requests across run plans")
        assigned.update(ids)
        manifest_path = folder / "manifest.json"
        report, report_sha = _read_json(manifest_path) if manifest_path.exists() else (None, None)
        results = {}
        if report is not None:
            if report.get("status") != "complete" or not isinstance(report.get("results"), list):
                raise ValueError("Invalid complete run manifest")
            for result in report["results"]:
                rid = result.get("request_id")
                if rid not in ids or rid in results:
                    raise ValueError("Duplicate or unrelated result in run manifest")
                results[rid] = result
            if set(results) != set(ids):
                raise ValueError("Complete run does not cover its plan")
        for rid in ids:
            path = folder / (rid + ".annotation.json")
            if not path.exists():
                if report is not None:
                    raise ValueError("Complete run lacks durable annotation")
                continue
            result, _ = _read_json(path)
            if report is not None and results[rid] != result:
                raise ValueError("Annotation and run manifest disagree")
            final, attempts = _annotation(folder, requests[rid], result)
            if len(attempts) > plan.get("max_retries", 0) + 1:
                raise ValueError("Attempt count exceeds run retry limit")
            completed[rid] = (final, attempts, str(folder))
        actual = [completed[rid] for rid in ids if rid in completed]
        counts = {"external_calls": sum(len(row[1]) for row in actual), "unique_annotation_requests": len(actual),
                  "automatic_retries": sum(len(row[1]) - 1 for row in actual),
                  "valid_predictions": sum(row[0]["status"] == "valid" for row in actual),
                  "invalid_predictions": sum(row[0]["status"] != "valid" for row in actual)}
        if report is not None and any(report.get(key) != value for key, value in counts.items()):
            raise ValueError("Run manifest counts disagree with receipts")
        run_info.append({"directory": str(folder), "plan_sha256": plan_sha, "manifest_sha256": report_sha,
                         "status": "complete" if report is not None else "interrupted_or_in_progress",
                         "planned_requests": len(ids), **counts})
    factual, grouped, annotations = defaultdict(list), defaultdict(list), []
    for rid, request in requests.items():
        meta = request["metadata"]
        task, model, mode = meta["task"], meta["model_key"], meta["mode"]
        final, attempts, run = completed.get(rid, (None, [], None))
        missing = final is None
        if missing:
            final = normalize_receipt(request, b"", http_status=None)
            final["reason"] = "missing_receipt"
        annotation = {"request_id": rid, "event_id": meta["event_id"], "task": task, "model_key": model,
                      "mode": mode, "action": meta["action"], "protocol_id": request["protocol_id"],
                      "prompt_sha256": request["prompt_sha256"], "consumers": request["consumers"],
                      "run_directory": run, "missing": missing, "status": final["status"], "reason": final["reason"],
                      "attempt_count": len(attempts), "automatic_retries": max(0, len(attempts) - 1),
                      "parsed_prediction": final["parsed_prediction"], "response_model": final["response_model"]}
        annotations.append(annotation)
        grouped[task, model, mode].append((annotation, attempts))
        if mode == "factual":
            factual_record = factual_record_from_receipt(request, final, observed_lab_value=labels[rid])
            factual[task, model, "all_unique_events"].append(factual_record)
            for consumer in request["consumers"]:
                factual[task, model, consumer["split"]].append(factual_record)
    evaluations = []
    for (task, model, split), rows in sorted(factual.items()):
        evaluations.append({"split": split, **evaluate_factual_predictions(task, rows)})
    groups = []
    for (task, model, mode), rows in sorted(grouped.items()):
        counts, tokens, attempt_failures = Counter(), Counter(), Counter()
        for row, attempts in rows:
            counts[row["status"]] += 1
            if row["reason"]:
                counts["failure:" + row["reason"]] += 1
            for receipt in attempts:
                _usage(receipt.get("usage"), tokens)
                if receipt["status"] != "valid":
                    attempt_failures[receipt["reason"]] += 1
        groups.append({"task": task, "model_key": model, "mode": mode, "requested_predictions": len(rows),
                       "valid_predictions": counts["valid"], "invalid_predictions": counts["invalid"],
                       "missing_predictions": sum(row["missing"] for row, _ in rows),
                       "coverage": counts["valid"] / len(rows),
                       "attempt_count": sum(len(attempts) for _, attempts in rows),
                       "automatic_retries": sum(max(0, len(attempts) - 1) for _, attempts in rows),
                       "failed_attempt_count": sum(attempt_failures.values()),
                       "attempt_failure_reasons": dict(sorted(attempt_failures.items())),
                       "failure_reasons": {key[8:]: value for key, value in sorted(counts.items()) if key.startswith("failure:")},
                       "token_usage_all_attempts": dict(sorted(tokens.items()))})
    valid = sum(row["status"] == "valid" for row in annotations)
    missing_count = sum(row["missing"] for row in annotations)
    summary = {"summary_version": SUMMARY_VERSION, "scope": "offline_review_pilot",
               "status": "complete" if not missing_count else "partial", "formal_paper_annotation_budget": False,
               "paper_experiment_complete": False, "dm_plus_fitted": False, "collector_external_calls": 0,
               "unique_requests": len(requests), "completed_annotations": len(completed),
               "valid_predictions": valid, "invalid_predictions_including_missing": len(requests) - valid,
               "missing_predictions": missing_count, "coverage": valid / len(requests),
               "recorded_attempt_count": sum(row["attempt_count"] for row in annotations),
               "attempt_counts_cover_completed_annotations_only": True,
               "planned_requests_without_final_annotation": len(assigned - set(completed)),
               "unresolved_requests_may_have_remote_attempts": bool(assigned - set(completed)),
               "automatic_retries": sum(row["automatic_retries"] for row in annotations),
               "groups": groups, "factual_evaluations": evaluations, "packets": packet_info, "runs": run_info,
               "token_usage_is_observed_response_usage_not_billing": True,
               "metrics_are_pilot_descriptive_not_formal_paper_results": True}
    return summary, annotations


def write_summary(packet_directories, run_directories, output_directory):
    """Validate first, then persist private parsed annotations and aggregate metrics."""
    output = Path(output_directory).resolve()
    if output.exists():
        raise ValueError("Summary output directory already exists")
    summary, annotations = summarize_runs(packet_directories, run_directories)
    output.mkdir(mode=0o700, parents=True)
    outputs = {}
    for name, raw in (("parsed-annotations.jsonl", b"".join(_encoded(row) for row in annotations)),
                      ("summary.json", _encoded(summary))):
        fd = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
        outputs[name] = _sha(raw)
    manifest = {"summary_version": SUMMARY_VERSION, "status": "complete", "scope": "offline_review_pilot",
                "created_at_utc": datetime.now(timezone.utc).isoformat(), "outputs": outputs,
                "source_sha256": _sha(Path(__file__).read_bytes()), "external_calls": 0,
                "aggregation_status": summary["status"], "unique_requests": len(annotations)}
    fd = os.open(output / "manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(_encoded(manifest))
    return summary
