#!/usr/bin/env python3
"""Fit local pilot DM+ points using saved G3 models and verified LLM receipts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from april_repro.clinical_dataset import load_clinical_dataset
from april_repro.clinical_models import PolicyFit, RewardFit
from april_repro.clinical_dmplus import (RULE_VERSION, evaluate_pair, file_sha256,
    fit_augmented_reward, load_verified_annotations, select_counterfactuals, verify_saved_dm)
from april_repro.cohort_splits import SPLITS

DEPENDENCIES = {"numpy": "2.2.6", "scipy": "1.15.3", "scikit-learn": "1.7.2",
                "joblib": "1.5.2", "threadpoolctl": "3.6.0"}
CODE_PATHS = ("scripts/run_clinical_dmplus.py", "src/april_repro/clinical_dmplus.py",
    "src/april_repro/clinical_models.py", "src/april_repro/clinical_dataset.py",
    "src/april_repro/llm_run_summary.py", "src/april_repro/llm_receipts.py",
    "src/april_repro/llm_predictions.py", "src/april_repro/llm_five_requests.py",
    "src/april_repro/rewards.py", "src/april_repro/cohort_splits.py",
    "src/april_repro/decision_features.py", "requirements-g3.lock")


def save(path, value):
    raw = (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(raw)
    temporary.chmod(0o600)
    temporary.replace(path)


def local_path(value, parent):
    path = (ROOT / value).resolve()
    if not path.is_relative_to((ROOT / parent).resolve()):
        raise ValueError("Input/output must be in its declared private artifact directory")
    return path


def load_baseline(folder):
    manifest = json.loads((folder / "manifest.json").read_bytes())
    if manifest.get("status") != "complete" or manifest.get("rule_version") != "clinical-baseline-v1":
        raise ValueError("Expected a complete original clinical DM baseline")
    if manifest.get("dependencies") != DEPENDENCIES:
        raise ValueError("Saved baseline numerical dependency versions differ")
    for rel, expected in manifest["outputs"].items():
        path = (folder / rel).resolve()
        if not path.is_relative_to(folder) or file_sha256(path) != expected:
            raise ValueError("Saved baseline output identity mismatch")
    # Same G3 implementation is required for exact coefficient replay. New files
    # are recorded separately; no baseline snapshot or original packet is edited.
    for rel in ("src/april_repro/clinical_models.py", "src/april_repro/clinical_dataset.py",
                "src/april_repro/rewards.py", "config/clinical-baseline.toml"):
        if file_sha256(ROOT / rel) != manifest["versions"][rel]:
            raise ValueError("Current adopted G3 implementation differs from the saved baseline")
    return manifest


def run(baseline_directory, summary_directory, output_directory=None):
    if {key: importlib.metadata.version(key) for key in DEPENDENCIES} != DEPENDENCIES:
        raise ValueError("Numerical environment differs from requirements-g3.lock")
    baseline_folder = local_path(baseline_directory, "artifacts/clinical-baselines")
    summary_folder = local_path(summary_directory, "artifacts/llm-summaries")
    saved_baseline = load_baseline(baseline_folder)
    baseline_digest = file_sha256(baseline_folder / "manifest.json")
    source = local_path(saved_baseline["input"]["directory"], "artifacts/treatment-features")
    evidence = load_verified_annotations(summary_folder)
    dataset = load_clinical_dataset(source)
    if (dataset.task != saved_baseline["task"]
            or dataset.provenance["manifest_sha256"] != saved_baseline["input"]["manifest_sha256"]
            or dataset.provenance["outputs"] != saved_baseline["input"]["outputs"]):
        raise ValueError("Clinical data differ from saved DM baseline inputs")
    model_keys = sorted({row["model_key"] for row in evidence.annotations
        if row["task"] == dataset.task and row["mode"] == "counterfactual"})
    if not model_keys:
        raise ValueError("No counterfactual model sources for the baseline task")
    versions = {rel: file_sha256(ROOT / rel) for rel in CODE_PATHS}
    parent = ROOT / "artifacts/clinical-dmplus"
    parent.mkdir(exist_ok=True, parents=True, mode=0o700)
    if output_directory is None:
        dest = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-")
            + dataset.task + "-", dir=parent))
    else:
        dest = local_path(output_directory, "artifacts/clinical-dmplus")
        dest.mkdir(mode=0o700, parents=True, exist_ok=False)
    for rel in CODE_PATHS:
        target = dest / "code" / rel
        target.parent.mkdir(exist_ok=True, parents=True, mode=0o700)
        shutil.copyfile(ROOT / rel, target)
        target.chmod(0o600)
    manifest = {"rule_version": RULE_VERSION, "scope": "local_review_pilot_dmplus_point",
        "status": "running", "task": dataset.task, "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": dataset.provenance, "saved_baseline": {"directory": str(baseline_folder),
            "manifest_sha256": baseline_digest}, "annotation_evidence": evidence.provenance,
        "dependencies": DEPENDENCIES, "versions": versions, "results": {},
        "settings": {"factual_and_annotation_row_weight": 1, "preprocessing": "saved behavior train only",
            "reward_model": "ordinary least squares", "context_action_interactions": False,
            "action_encoding": "paper discrete action divided by task maximum", "clip_predictions": False,
            "target_policy": "saved original G3 target policy", "d0": "original target validation events",
            "invalid_annotations": "report denominators; incomplete cell not estimable"},
        "database_queried": False, "llm_called": False, "bootstrap_datasets": 0,
        "formal_500_annotation_experiment": False, "full_paper_reproduction_complete": False}
    save(dest / "manifest.json", manifest)
    from threadpoolctl import threadpool_limits
    try:
        index = {event: i for i, event in enumerate(dataset.event_ids)}
        with threadpool_limits(limits=1):
            for split in SPLITS:
                baseline = RewardFit.from_dict(json.loads((baseline_folder / split / "reward-model.json").read_bytes()))
                policy = PolicyFit.from_dict(json.loads((baseline_folder / split / "target-policy.json").read_bytes()))
                replay = evaluate_pair(dataset, split, policy, baseline, baseline)
                verification = verify_saved_dm(replay, saved_baseline["results"][split]["dm"])
                behavior = dataset.mask(split, "behavior", "train")
                cells = {}
                for model_key in model_keys:
                    annotations, coverage = select_counterfactuals(dataset, evidence, split, model_key, index)
                    out = dest / split / model_key
                    out.mkdir(parents=True, mode=0o700)
                    if coverage["requested_annotations"] == 0 or coverage["valid_annotations"] != coverage["requested_annotations"]:
                        result = dict(replay, status="not_estimable", reason="empty_or_incomplete_annotation_cell", dm_plus=None,
                            dm_plus_signed_difference=None, dm_plus_absolute_difference=None, dm_plus_minus_dm=None)
                    elif replay["status"] != "estimated":
                        result = dict(replay)
                    else:
                        augmented = fit_augmented_reward(dataset, behavior, baseline, annotations)
                        result = evaluate_pair(dataset, split, policy, baseline, augmented)
                        verify_saved_dm(result, saved_baseline["results"][split]["dm"])
                        save(out / "reward-model-plus.json", augmented.to_dict())
                    result.update(coverage, **verification, factual_training_events=int(behavior.sum()),
                        annotation_rows_added=len(annotations) if result["status"] == "estimated" else 0,
                        selected_valid_annotations=len(annotations), fixed_target_policy_sha256=file_sha256(
                            baseline_folder / split / "target-policy.json"))
                    save(out / "annotations-used.json", {"source": model_key, "protocol_id": coverage["annotation_protocol_id"],
                        "fit_executed": result["status"] == "estimated", "annotations": [
                            {"request_id": row.request_id, "event_id": row.event_id, "action": row.action,
                             "reward": row.reward} for row in annotations]})
                    save(out / "summary.json", result)
                    cells[model_key] = result
                manifest["results"][split] = cells
                save(dest / "manifest.json", manifest)
        if file_sha256(baseline_folder / "manifest.json") != baseline_digest:
            raise ValueError("Baseline manifest changed during DM+ fitting")
        if file_sha256(source / "manifest.json") != dataset.provenance["manifest_sha256"]:
            raise ValueError("Feature manifest changed during DM+ fitting")
        if any(file_sha256(ROOT / rel) != digest for rel, digest in versions.items()):
            raise ValueError("Source code changed during DM+ fitting")
        manifest["status"] = "complete"
    except Exception as error:
        manifest.update(status="failed", error_type=type(error).__name__,
            error="Local input integrity or numerical fitting failed; no external requests were made.")
        save(dest / "manifest.json", manifest)
        raise
    finally:
        manifest["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        save(dest / "manifest.json", manifest)
    manifest["outputs"] = {str(path.relative_to(dest)): file_sha256(path)
        for path in dest.rglob("*") if path.is_file() and path.name != "manifest.json"
        and "code" not in path.relative_to(dest).parts}
    save(dest / "manifest.json", manifest)
    return {"status": "complete", "artifact": str(dest.relative_to(ROOT)), "task": dataset.task,
        "estimated_cells": sum(row["status"] == "estimated" for cells in manifest["results"].values() for row in cells.values()),
        "not_estimable_cells": sum(row["status"] == "not_estimable" for cells in manifest["results"].values() for row in cells.values()),
        "llm_calls": 0, "formal_500_annotation_experiment": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-directory", required=True)
    parser.add_argument("--summary-directory", required=True)
    parser.add_argument("--output-directory")
    args = parser.parse_args(argv)
    old = os.umask(0o077)
    try:
        result = run(args.baseline_directory, args.summary_directory, args.output_directory)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__,
            "details": "Inspect local artifact integrity and fitting; no patient values printed and no API calls made."}), file=sys.stderr)
        return 1
    finally:
        os.umask(old)


if __name__ == "__main__":
    raise SystemExit(main())
