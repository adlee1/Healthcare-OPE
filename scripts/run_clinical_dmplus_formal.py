#!/usr/bin/env python3
"""Fit one completed formal LLM's fixed 0--500-prefix DM+ points, entirely locally."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from april_repro.clinical_dataset import load_clinical_dataset
from april_repro.clinical_models import PolicyFit, RewardFit
from april_repro.clinical_dmplus import evaluate_pair, file_sha256, fit_augmented_reward, verify_saved_dm
from april_repro.clinical_dmplus_formal import BUDGETS, RULE_VERSION, load_model_evidence, select_prefix, verify_evidence_unchanged
from april_repro.cohort_splits import SPLITS
import run_clinical_dmplus as pilot_runner

CODE_PATHS = tuple(dict.fromkeys((*pilot_runner.CODE_PATHS,
    "src/april_repro/clinical_dmplus_formal.py", "scripts/run_clinical_dmplus_formal.py",
    "src/april_repro/llm_formal_run.py", "src/april_repro/llm_formal_plan.py")))


def run(plan_directory, run_directory, baseline_directories, output_directory, model_key="deepseek"):
    if {name: importlib.metadata.version(name) for name in pilot_runner.DEPENDENCIES} != pilot_runner.DEPENDENCIES:
        raise ValueError("Numerical environment differs from adopted dependencies")
    dest = Path(output_directory).resolve()
    if dest.exists():
        raise ValueError("Formal DM+ output already exists")
    evidence = load_model_evidence(plan_directory, run_directory, model_key)
    versions = {name: file_sha256(ROOT / name) for name in CODE_PATHS}
    dest.mkdir(parents=True, mode=0o700)
    for name in CODE_PATHS:
        target = dest / "code" / name
        target.parent.mkdir(exist_ok=True, parents=True, mode=0o700)
        shutil.copyfile(ROOT / name, target)
        target.chmod(0o600)
    manifest = {"rule_version": RULE_VERSION, "scope": "formal_fixed_prefix_dmplus_point",
        "status": "running", "source_model_key": model_key, "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "annotation_evidence": evidence.provenance, "annotation_summary": evidence.summary,
        "dependencies": pilot_runner.DEPENDENCIES, "versions": versions, "tasks": {},
        "settings": {"requested_budgets": list(BUDGETS), "factual_and_annotation_row_weight": 1,
            "preprocessing": "original saved behavior train only", "reward_model": "ordinary least squares",
            "context_action_interactions": False, "action_encoding": "paper discrete action divided by task maximum",
            "clip_predictions": False, "target_policy": "saved original G3 target policy",
            "d0": "original target validation events", "invalid_annotations": "fixed planned prefixes; available valid subset; no refill",
            "incomplete_valid_budget_interpretation": "diagnostic point only; not exact B-valid-annotation comparison"},
        "database_queried": False, "llm_called": False, "bootstrap_datasets": 0,
        "formal_500_annotation_experiment_complete": False, "full_paper_reproduction_complete": False}
    save = pilot_runner.save
    save(dest / "manifest.json", manifest)
    descriptor = os.open(dest / "verified-annotations.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        for row in evidence.annotations:
            handle.write((json.dumps(row, sort_keys=True, allow_nan=False) + "\n").encode())
    from threadpoolctl import threadpool_limits
    try:
        for directory in baseline_directories:
            baseline_folder = Path(directory).resolve()
            saved_baseline = pilot_runner.load_baseline(baseline_folder)
            digest = file_sha256(baseline_folder / "manifest.json")
            source = (ROOT / saved_baseline["input"]["directory"]).resolve()
            dataset = load_clinical_dataset(source)
            if (dataset.task != saved_baseline["task"] or dataset.task in manifest["tasks"]
                    or dataset.provenance["manifest_sha256"] != saved_baseline["input"]["manifest_sha256"]
                    or dataset.provenance["outputs"] != saved_baseline["input"]["outputs"]):
                raise ValueError("Original clinical DM input identity mismatch")
            task = {"input": dataset.provenance, "saved_baseline": {"directory": str(baseline_folder),
                "manifest_sha256": digest}, "results": {}}
            manifest["tasks"][dataset.task] = task
            index = {event: i for i, event in enumerate(dataset.event_ids)}
            with threadpool_limits(limits=1):
                for split in SPLITS:
                    baseline = RewardFit.from_dict(json.loads((baseline_folder / split / "reward-model.json").read_bytes()))
                    policy = PolicyFit.from_dict(json.loads((baseline_folder / split / "target-policy.json").read_bytes()))
                    replay = evaluate_pair(dataset, split, policy, baseline, baseline)
                    verification = verify_saved_dm(replay, saved_baseline["results"][split]["dm"])
                    behavior = dataset.mask(split, "behavior", "train")
                    cells = {}
                    for budget in BUDGETS:
                        annotations, coverage = select_prefix(dataset, evidence, split, model_key, budget, index)
                        out = dest / dataset.task / split / str(budget)
                        out.mkdir(parents=True, mode=0o700)
                        if replay["status"] != "estimated":
                            result = dict(replay)
                        else:
                            augmented = fit_augmented_reward(dataset, behavior, baseline, annotations)
                            result = evaluate_pair(dataset, split, policy, baseline, augmented)
                            verify_saved_dm(result, saved_baseline["results"][split]["dm"])
                            save(out / "reward-model-plus.json", augmented.to_dict())
                        result.update(coverage, **verification, factual_training_events=int(behavior.sum()),
                            annotation_rows_added=len(annotations) if result["status"] == "estimated" else 0,
                            selected_valid_annotations=len(annotations), fixed_target_policy_sha256=file_sha256(
                                baseline_folder / split / "target-policy.json"),
                            formal_500_annotation_experiment_complete=False)
                        save(out / "annotations-used.json", {"source": model_key, "requested_budget": budget,
                            "protocol_id": coverage["annotation_protocol_id"], "fit_executed": result["status"] == "estimated",
                            "annotations": [{"request_id": row.request_id, "event_id": row.event_id, "action": row.action,
                                "reward": row.reward} for row in annotations]})
                        save(out / "summary.json", result)
                        cells[str(budget)] = result
                    task["results"][split] = cells
                    save(dest / "manifest.json", manifest)
            if file_sha256(baseline_folder / "manifest.json") != digest:
                raise ValueError("Baseline manifest changed during fitting")
            if file_sha256(source / "manifest.json") != dataset.provenance["manifest_sha256"]:
                raise ValueError("Feature manifest changed during fitting")
            del index, dataset
        verify_evidence_unchanged(evidence)
        if any(file_sha256(ROOT / name) != digest for name, digest in versions.items()):
            raise ValueError("DM+ implementation changed during fitting")
        manifest["status"] = "complete"
    except Exception as error:
        manifest.update(status="failed", error_type=type(error).__name__,
            error="Local input integrity or numerical fitting failed; no external calls.")
        raise
    finally:
        manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        save(dest / "manifest.json", manifest)
    manifest["outputs"] = {str(path.relative_to(dest)): file_sha256(path) for path in dest.rglob("*")
        if path.is_file() and path.name != "manifest.json" and "code" not in path.relative_to(dest).parts}
    save(dest / "manifest.json", manifest)
    points = [point for task in manifest["tasks"].values() for cells in task["results"].values() for point in cells.values()]
    return {"status": "complete", "artifact": str(dest), "source_model_key": model_key,
        "estimated_points": sum(point["status"] == "estimated" for point in points),
        "not_estimable_points": sum(point["status"] == "not_estimable" for point in points),
        "incomplete_valid_annotation_budget_points": sum(not point["exact_valid_annotation_budget"] for point in points),
        "bootstrap_datasets": 0, "external_calls": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-directory", required=True)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--baseline-directory", action="append", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--model-key", default="deepseek")
    args = parser.parse_args(argv)
    previous = os.umask(0o077)
    try:
        result = run(args.plan_directory, args.run_directory, args.baseline_directory, args.output_directory, args.model_key)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__,
            "details": "Inspect local artifact integrity and fitting; no patient values or external calls."}), file=sys.stderr)
        return 1
    finally:
        os.umask(previous)


if __name__ == "__main__":
    raise SystemExit(main())
