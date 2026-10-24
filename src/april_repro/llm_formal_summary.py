"""Offline formal annotations, with strict raw replay and full planned denominators.

No API calls or clinical feature reconstruction occur here; the bound input
files are read only to verify their hashes. Cached pilot replies use the
formal request consumers, so an overlapping split never loses its annotation.
Completed calls, outstanding attempts and usable annotation budgets are separate.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from april_repro import llm_run_summary as pilot
from april_repro.llm_formal_run import load_formal_plan, inspect_request, verify_request_result
from april_repro.llm_formal_run import source_hashes as execution_source_hashes
from april_repro.llm_predictions import evaluate_factual_predictions
from april_repro.llm_receipts import factual_record_from_receipt, normalize_receipt


SUMMARY_VERSION = "formal-llm-summary-v1"
SCOPE = "formal_main_annotation_summary"
_encoded, _sha, _read_json = pilot._encoded, pilot._sha, pilot._read_json


def _ids(value, label):
    if (not isinstance(value, list) or any(not isinstance(rid, str) for rid in value)
            or len(set(value)) != len(value)):
        raise ValueError("Invalid or duplicate " + label)
    return set(value)


def _cached(plan):
    results = {}
    for rid, annotation in plan.reused.items():
        request = plan.requests[rid]
        folder = Path(annotation["run_directory"])
        result, _ = _read_json(folder / (rid + ".annotation.json"))
        final, attempts = pilot._annotation(folder, request, result)
        if (final["status"] != "valid" or annotation["status"] != "valid"
                or annotation["missing"] or annotation["attempt_count"] != len(attempts)
                or annotation["parsed_prediction"] != final["parsed_prediction"]
                or annotation["response_model"] != final["response_model"]):
            raise ValueError("Cached annotation differs from verified raw receipts")
        results[rid] = (final, attempts, str(folder), "cached_pilot", "completed")
    return results


def _new_results(plan, run_directory):
    if run_directory is None:
        return {}, {}, None
    folder = Path(run_directory).resolve()
    run, digest = _read_json(folder / "plan.json")
    expected_new = set(plan.requests) - set(plan.reused)
    if (run.get("scope") != "formal_main_annotation_run"
            or run.get("formal_manifest_sha256") != plan.manifest_sha256
            or Path(run.get("formal_plan_directory", "")).resolve() != plan.directory
            or _ids(run.get("request_ids"), "run request IDs") != set(plan.requests)
            or _ids(run.get("new_request_ids"), "new request IDs") != expected_new
            or _ids(run.get("reused_request_ids"), "reused request IDs") != set(plan.reused)):
        raise ValueError("Formal run plan provenance or request partition mismatch")
    maximum = run.get("max_retries")
    if type(maximum) is not int or not 0 <= maximum <= 2:
        raise ValueError("Invalid formal run retry bound")
    if run.get("source_sha256") != execution_source_hashes():
        raise ValueError("Formal execution source identity changed")
    cached_path = folder / "reused-annotations.jsonl"
    cached = [json.loads(line) for line in cached_path.read_bytes().splitlines()]
    cached_ids = _ids([row.get("request_id") for row in cached], "cached request IDs")
    if cached_ids != set(plan.reused) or {row["request_id"]: row for row in cached} != plan.reused:
        raise ValueError("Saved cache differs from revalidated formal cache")
    status_path = folder / "status.json"
    live_status, _ = _read_json(status_path) if status_path.exists() else ({}, None)
    active = live_status.get("status") == "active"
    # Index each model folder once: per-request globbing becomes quadratic for
    # tens of thousands of attempt files. Reject unplanned or cached sources.
    artifacts = defaultdict(list)
    for model_folder in (folder / "requests").iterdir():
        if not model_folder.is_dir() or model_folder.is_symlink():
            raise ValueError("Unexpected formal request directory")
        for path in model_folder.iterdir():
            if path.name.startswith("."):
                continue  # A writer may be replacing an atomic status file.
            rid = path.name.split(".")[0]
            if (rid not in expected_new
                    or model_folder.name != plan.requests[rid]["metadata"]["model_key"]):
                raise ValueError("Duplicate or unrelated new annotation source")
            artifacts[rid].append(path)
    results, states = {}, {}
    started_count = 0
    for rid in sorted(expected_new):
        request = plan.requests[rid]
        model_folder = folder / "requests" / request["metadata"]["model_key"]
        state = inspect_request(model_folder, request, max_retries=maximum) if rid in artifacts else {"state": "new"}
        if (state["state"] == "held" and active
                and not (model_folder / (rid + ".held.json")).exists()):
            state = {"state": "in_progress"}
        states[rid] = state["state"]
        if state["state"] == "completed":
            result, final, attempts = verify_request_result(model_folder, request, max_retries=maximum)
            if len(attempts) > maximum + 1:
                raise ValueError("Annotation exceeds formal run retry bound")
            results[rid] = (final, attempts, str(model_folder), "new_run", "completed")
        elif state["state"] not in ("new", "held", "recoverable", "in_progress"):
            raise ValueError("Unknown formal request execution state")
        # .started is persisted before POST. It may represent a request whose
        # remote completion is unknown, and must not be erased from counts.
        started = [path for path in artifacts[rid] if path.name.endswith(".started.json")]
        if len(started) > maximum + 1:
            raise ValueError("Started attempt count exceeds formal retry bound")
        for path in started:
            row, _ = _read_json(path)
            number = row.get("attempt_number")
            stem = rid if number == 1 else rid + f".attempt-{number:02d}" if type(number) is int else ""
            if (row.get("request_id") != rid or row.get("status") != "attempt_started"
                    or type(number) is not int or not 1 <= number <= maximum + 1
                    or path.name != stem + ".started.json"):
                raise ValueError("Invalid started attempt identity")
        started_count += max(len(started), len(results[rid][1]) if rid in results else 0)
    final_path = folder / "manifest.json"
    manifest, manifest_sha = _read_json(final_path) if final_path.exists() else (None, None)
    valid = sum(row[0]["status"] == "valid" for row in results.values())
    held = sum(value == "held" for value in states.values())
    counts = {"unique_requests": len(plan.requests), "reused_annotations": len(plan.reused),
        "new_completed_annotations": len(results), "completed_annotations": len(plan.reused) + len(results),
        "valid_predictions": len(plan.reused) + valid, "invalid_predictions": len(results) - valid,
        "held_requests": held, "pending_requests": len(expected_new) - len(results) - held,
        "recorded_attempt_count": started_count,
        "automatic_retries": sum(len(row[1]) - 1 for row in results.values())}
    if manifest is not None and not active:
        if (manifest.get("status") not in ("complete", "partial")
                or any(manifest.get(key) != value for key, value in counts.items())
                or (manifest["status"] == "complete" and (counts["pending_requests"] or held))):
            raise ValueError("Formal run manifest counts disagree with durable results")
    info = {"directory": str(folder), "plan_sha256": digest, "manifest_sha256": manifest_sha,
        "status": manifest["status"] if manifest else "in_progress_or_interrupted", **counts}
    return results, states, info


def _group(rows):
    reasons, failures, tokens = Counter(), Counter(), Counter()
    for row, attempts in rows:
        if row["reason"]:
            reasons[row["reason"]] += 1
        for receipt in attempts:
            pilot._usage(receipt.get("usage"), tokens)
            if receipt["status"] != "valid":
                failures[receipt["reason"]] += 1
    valid = sum(row["status"] == "valid" for row, _ in rows)
    return {"requested_predictions": len(rows), "valid_predictions": valid,
        "invalid_predictions_including_missing": len(rows) - valid,
        "completed_annotations": sum(not row["missing"] for row, _ in rows),
        "missing_predictions": sum(row["missing"] for row, _ in rows),
        "held_requests": sum(row["execution_state"] == "held" for row, _ in rows),
        "reused_annotations": sum(row["annotation_source"] == "cached_pilot" for row, _ in rows),
        "coverage": valid / len(rows) if rows else None,
        "completed_annotation_attempt_count": sum(len(attempts) for _, attempts in rows),
        "automatic_retries": sum(max(0, len(attempts) - 1) for _, attempts in rows),
        "failed_attempt_count": sum(failures.values()),
        "attempt_failure_reasons": dict(sorted(failures.items())),
        "failure_reasons": dict(sorted(reasons.items())),
        "token_usage_completed_annotations_all_attempts": dict(sorted(tokens.items()))}


def summarize_formal_run(plan_directory, run_directory=None):
    """Revalidate inputs and return (aggregate summary, private annotation rows)."""
    plan = load_formal_plan(plan_directory)
    completed = _cached(plan)
    new, states, run = _new_results(plan, run_directory)
    if set(new) & set(completed):
        raise ValueError("Duplicate annotation across cache and new run")
    completed.update(new)
    factual, grouped, cells, annotations = defaultdict(list), defaultdict(list), defaultdict(list), []
    for rid, request in sorted(plan.requests.items()):
        meta = request["metadata"]
        task, model, mode = meta["task"], meta["model_key"], meta["mode"]
        final, attempts, source_folder, source, state = completed.get(rid,
            (None, [], None, "missing", states.get(rid, "new")))
        missing = final is None
        if missing:
            final = normalize_receipt(request, b"", http_status=None)
            final["reason"] = "held_without_final_annotation" if state == "held" else "missing_receipt"
        annotation = {"request_id": rid, "event_id": meta["event_id"], "task": task,
            "model_key": model, "mode": mode, "action": meta["action"],
            "protocol_id": request["protocol_id"], "prompt_sha256": request["prompt_sha256"],
            "consumers": request["consumers"], "run_directory": source_folder,
            "annotation_source": source, "execution_state": state, "missing": missing,
            "status": final["status"], "reason": final["reason"], "attempt_count": len(attempts),
            "automatic_retries": max(0, len(attempts) - 1),
            "parsed_prediction": final["parsed_prediction"], "response_model": final["response_model"]}
        annotations.append(annotation)
        grouped[task, model, mode].append((annotation, attempts))
        for consumer in request["consumers"]:
            cells[task, model, consumer["split"], mode].append((consumer["rank"], annotation, attempts))
        if mode == "factual":
            record = factual_record_from_receipt(request, final, observed_lab_value=plan.labels[rid])
            factual[task, model, "all_unique_events"].append(record)
            for consumer in request["consumers"]:
                factual[task, model, consumer["split"]].append(record)
    evaluations = [{"split": split, **evaluate_factual_predictions(task, rows)}
        for (task, model, split), rows in sorted(factual.items())]
    groups = [{"task": task, "model_key": model, "mode": mode, **_group(rows)}
        for (task, model, mode), rows in sorted(grouped.items())]
    cell_summaries = []
    budgets = plan.manifest["selection"]["counterfactual_budget_grid"]
    for (task, model, split, mode), ranked in sorted(cells.items()):
        ranked.sort(key=lambda row: row[0])
        if [row[0] for row in ranked] != list(range(1, len(ranked) + 1)):
            raise ValueError("Formal cell ranks are not a contiguous unique prefix")
        prefixes = []
        for budget in budgets if mode == "counterfactual" else [500]:
            selected = [(row, attempts) for rank, row, attempts in ranked if rank <= budget]
            stats = _group(selected)
            prefixes.append({"requested_budget": budget, "selected_predictions": len(selected),
                "budget_supported": len(selected) == budget,
                "annotation_budget_ready": len(selected) == budget and stats["valid_predictions"] == budget,
                **stats})
        cell_summaries.append({"task": task, "model_key": model, "split": split, "mode": mode,
            **_group([(row, attempts) for _, row, attempts in ranked]), "budget_prefixes": prefixes})
    missing = sum(row["missing"] for row in annotations)
    valid = sum(row["status"] == "valid" for row in annotations)
    held = sum(row["execution_state"] == "held" for row in annotations)
    cached_attempts = sum(row["attempt_count"] for row in annotations if row["annotation_source"] == "cached_pilot")
    new_attempts = sum(row["attempt_count"] for row in annotations if row["annotation_source"] == "new_run")
    started = run["recorded_attempt_count"] if run else 0
    summary = {"summary_version": SUMMARY_VERSION, "scope": SCOPE,
        "status": "partial" if missing else "complete", "collector_external_calls": 0,
        "formal_paper_annotation_budget": True, "paper_experiment_complete": False, "dm_plus_fitted": False,
        "model_adapted": True, "full_five_paper_models": False,
        "unique_requests": len(annotations), "completed_annotations": len(completed),
        "reused_annotations": len(plan.reused), "new_completed_annotations": len(new),
        "valid_predictions": valid, "invalid_completed_predictions": len(completed) - valid,
        "invalid_predictions_including_missing": len(annotations) - valid,
        "missing_predictions": missing, "held_requests": held, "pending_requests": missing - held,
        "coverage": valid / len(annotations), "recorded_attempt_count": started,
        "recorded_attempt_count_scope": "new_run_started_attempts_including_unfinished",
        "cached_pilot_attempt_count": cached_attempts,
        "new_completed_annotation_attempt_count": new_attempts,
        "completed_annotation_attempt_count_including_cache": cached_attempts + new_attempts,
        "automatic_retries": sum(row["automatic_retries"] for row in annotations if row["annotation_source"] == "new_run"),
        "cached_pilot_automatic_retries": sum(row["automatic_retries"] for row in annotations if row["annotation_source"] == "cached_pilot"),
        "attempts_without_final_annotation": started - new_attempts,
        "unresolved_requests_may_have_remote_attempts": started > new_attempts,
        "counterfactual_500_cells_ready": sum(prefix["annotation_budget_ready"] for cell in cell_summaries
            if cell["mode"] == "counterfactual" for prefix in cell["budget_prefixes"] if prefix["requested_budget"] == 500),
        "counterfactual_500_cells_planned": sum(cell["mode"] == "counterfactual" for cell in cell_summaries),
        "groups": groups, "cells": cell_summaries, "factual_evaluations": evaluations,
        "formal_plan": {"directory": str(plan.directory), "manifest_sha256": plan.manifest_sha256},
        "run": run, "pilot_reuse": plan.pilot_evidence,
        "token_usage_is_observed_response_usage_not_billing": True,
        "factual_metrics_use_valid_predictions_with_full_coverage_denominators": True}
    return summary, annotations


def write_summary(plan_directory, run_directory, output_directory):
    """Write immutable private results only after raw and request validation."""
    output = Path(output_directory).resolve()
    if output.exists():
        raise ValueError("Formal summary output directory already exists")
    summary, annotations = summarize_formal_run(plan_directory, run_directory)
    output.mkdir(mode=0o700, parents=True)
    outputs = {}
    for name, raw in (("parsed-annotations.jsonl", b"".join(_encoded(row) for row in annotations)),
                      ("summary.json", _encoded(summary))):
        fd = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
        outputs[name] = _sha(raw)
    manifest = {"summary_version": SUMMARY_VERSION, "scope": SCOPE, "status": "complete",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "outputs": outputs,
        "source_sha256": _sha(Path(__file__).read_bytes()), "external_calls": 0,
        "aggregation_status": summary["status"], "unique_requests": len(annotations)}
    fd = os.open(output / "manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(_encoded(manifest))
    return summary
