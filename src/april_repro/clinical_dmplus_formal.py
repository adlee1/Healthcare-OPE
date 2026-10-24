"""Offline fixed-prefix DM+ bridge for one completed formal annotation source.

Invalid completed replies remain inside their preselected budget. The available
valid subset may yield a diagnostic point, but never becomes an exact B-valid-
annotation result. No provider calls or outcome-dependent replacement occur.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
import json
from pathlib import Path

from april_repro.clinical_dmplus import AnnotationEvidence, file_sha256, select_counterfactuals
from april_repro.cohort_splits import SPLITS
from april_repro.llm_formal_run import load_formal_plan, source_hashes, verify_request_result
from april_repro.llm_predictions import evaluate_factual_predictions
from april_repro.llm_receipts import factual_record_from_receipt
from april_repro.llm_run_summary import _annotation

RULE_VERSION = "clinical-dmplus-formal-prefix-point-v1"
BUDGETS = (0, 100, 200, 300, 400, 500)


def _id_set(value):
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value) or len(value) != len(set(value)):
        raise ValueError("Invalid or duplicate execution request identity")
    return set(value)


def load_model_evidence(plan_directory, run_directory, model_key):
    """Revalidate one model's complete immutable replies, irrespective of peers."""
    plan = load_formal_plan(plan_directory)
    folder = Path(run_directory).resolve()
    run_path = folder / "plan.json"
    run = json.loads(run_path.read_bytes())
    if (run.get("scope") != "formal_main_annotation_run"
            or run.get("formal_manifest_sha256") != plan.manifest_sha256
            or Path(run.get("formal_plan_directory", "")).resolve() != plan.directory
            or _id_set(run.get("request_ids")) != set(plan.requests)
            or _id_set(run.get("new_request_ids")) != set(plan.requests) - set(plan.reused)
            or _id_set(run.get("reused_request_ids")) != set(plan.reused)
            or run.get("source_sha256") != source_hashes()):
        raise ValueError("Formal execution provenance or partition differs")
    retries = run.get("max_retries")
    if type(retries) is not int or not 0 <= retries <= 2:
        raise ValueError("Formal retry bound is invalid")
    if tuple(plan.manifest["selection"]["counterfactual_budget_grid"]) != BUDGETS:
        raise ValueError("Formal annotation budget grid differs")
    requests = {rid: row for rid, row in plan.requests.items() if row["metadata"]["model_key"] == model_key}
    if not requests:
        raise ValueError("No formal requests for selected model")
    annotations, source_files, factual = [], {}, defaultdict(list)
    for rid, request in sorted(requests.items()):
        cached = rid in plan.reused
        source = Path(plan.reused[rid]["run_directory"]) if cached else folder / "requests" / model_key
        result_path = source / (rid + ".annotation.json")
        if not result_path.is_file() or result_path.is_symlink():
            raise ValueError("Selected model has unfinished or nonregular annotations")
        result = json.loads(result_path.read_bytes())
        if cached:
            final, attempts = _annotation(source, request, result)
            if final["status"] != "valid" or final["parsed_prediction"] != plan.reused[rid]["parsed_prediction"]:
                raise ValueError("Cached prediction differs from verified source")
        else:
            result, final, attempts = verify_request_result(source, request, result=result, max_retries=retries)
        source_files[str(result_path)] = file_sha256(result_path)
        for attempt in result["attempts"]:
            for kind in ("started", "raw", "receipt"):
                path = source / attempt["files"][kind]
                source_files[str(path)] = file_sha256(path)
        meta = request["metadata"]
        row = {"request_id": rid, "event_id": meta["event_id"], "task": meta["task"],
            "model_key": model_key, "mode": meta["mode"], "action": meta["action"],
            "protocol_id": request["protocol_id"], "prompt_sha256": request["prompt_sha256"],
            "consumers": request["consumers"], "run_directory": str(source),
            "annotation_source": "cached_pilot" if cached else "new_run", "execution_state": "completed",
            "missing": False, "status": final["status"], "reason": final["reason"],
            "attempt_count": len(attempts), "parsed_prediction": final["parsed_prediction"],
            "response_model": final["response_model"]}
        annotations.append(row)
        if meta["mode"] == "factual":
            record = factual_record_from_receipt(request, final, observed_lab_value=plan.labels[rid])
            factual[meta["task"], "all_unique_events"].append(record)
            for consumer in request["consumers"]:
                factual[meta["task"], consumer["split"]].append(record)
    summary = {"model_key": model_key, "unique_requests": len(annotations),
        "completed_annotations": len(annotations), "valid_predictions": sum(x["status"] == "valid" for x in annotations),
        "invalid_predictions": sum(x["status"] != "valid" for x in annotations),
        "missing_predictions": 0, "reused_annotations": sum(x["annotation_source"] == "cached_pilot" for x in annotations),
        "failure_reasons": dict(Counter(x["reason"] for x in annotations if x["status"] != "valid")),
        "factual_evaluations": [{"split": split, **evaluate_factual_predictions(task, rows)}
            for (task, split), rows in sorted(factual.items())]}
    provenance = {"formal_plan_directory": str(plan.directory), "formal_manifest_sha256": plan.manifest_sha256,
        "run_directory": str(folder), "run_plan_sha256": file_sha256(run_path),
        "selected_model_key": model_key, "source_files": source_files,
        "raw_receipts_revalidated": True, "all_selected_model_requests_complete": True,
        "other_model_completion_required": False, "fixed_budget_grid": list(BUDGETS)}
    return AnnotationEvidence(summary, tuple(annotations), requests, provenance)


def select_prefix(dataset, evidence, split, model_key, budget, event_index=None):
    """Use planned consumer rank, preserving failures inside every prefix."""
    if type(budget) is not int or budget not in BUDGETS or split not in SPLITS:
        raise ValueError("Unsupported formal split or budget")
    ranked = []
    for row in evidence.annotations:
        if row["task"] != dataset.task or row["model_key"] != model_key or row["mode"] != "counterfactual":
            continue
        consumers = [c for c in row["consumers"] if c["split"] == split]
        if not consumers:
            continue
        if len(consumers) != 1 or consumers[0]["mode"] != "counterfactual" or consumers[0]["fold"] != "train":
            raise ValueError("Formal counterfactual training consumer mismatch")
        consumer = consumers[0]
        if type(consumer.get("rank")) is not int:
            raise ValueError("Formal prefix rank is not an integer")
        ranked.append((consumer["rank"], {**row, "consumers": [consumer]}))
    ranked.sort(key=lambda pair: pair[0])
    if [rank for rank, _ in ranked] != list(range(1, 501)):
        raise ValueError("Formal cell must contain exactly contiguous 500 planned ranks")
    subset = tuple(row for rank, row in ranked if rank <= budget)
    selected, coverage = select_counterfactuals(dataset, replace(evidence, annotations=subset), split, model_key, event_index)
    if coverage["requested_annotations"] != budget:
        raise ValueError("Fixed annotation prefix denominator changed")
    if coverage["missing_annotations"]:
        raise ValueError("Selected model has missing results within its fixed budget")
    coverage.update(requested_budget=budget, planned_cell_budget=500,
        annotation_budget_is_pilot=False, exact_valid_annotation_budget=len(selected) == budget,
        fixed_prefix_complete=True, selection_rule="formal consumer.rank <= requested_budget",
        invalid_handling="retain planned denominator; fit available valid rows; no replacement",
        analysis_status="exact_requested_budget" if len(selected) == budget else "available_valid_subset_of_fixed_requested_budget")
    return selected, coverage


def verify_evidence_unchanged(evidence):
    for name, digest in evidence.provenance["source_files"].items():
        if file_sha256(name) != digest:
            raise ValueError("Selected model source evidence changed during fitting")
    if file_sha256(Path(evidence.provenance["formal_plan_directory"]) / "manifest.json") != evidence.provenance["formal_manifest_sha256"]:
        raise ValueError("Formal plan changed during fitting")
    if file_sha256(Path(evidence.provenance["run_directory"]) / "plan.json") != evidence.provenance["run_plan_sha256"]:
        raise ValueError("Formal execution plan changed during fitting")
