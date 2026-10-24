"""Prepare small private APRIL review packets locally; never call an API.

Selection uses only event identity, action, role and fold. Full artifacts are
validated by ClinicalDataset; selected raw inputs are then joined and hash-read
again without retaining the unselected CSV rows. Labels remain a separate file.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import tomllib

from april_repro import clinical_dataset, cohort_splits, decision_features, llm_requests, rewards
from april_repro.clinical_dataset import FOLD_CODES, ROLE_CODES, load_clinical_dataset
from april_repro.cohort_splits import ACTIONS, SPLITS
from april_repro.decision_features import FEATURES, IDENTITY, OUTCOMES, parse_time
from april_repro.llm_requests import MODEL_SPECS, PROTOCOL_ID, build_request


RULE_VERSION = "llm-review-packet-v1"
MODES = ("factual", "counterfactual")


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _limit(value):
    if type(value) is not int or not 1 <= value <= 1000:
        raise ValueError("Review pilot pairs per cell must be an integer from 1 to 1000")
    return value


def load_config(path, *, pairs_per_cell=None):
    """Check operational fields against the actual fixed request builder."""
    path = Path(path).resolve()
    raw = path.read_bytes()
    config = tomllib.loads(raw.decode("utf-8"))
    if config.get("scope") != "offline_review_pilot" or config.get("network_calls") is not False:
        raise ValueError("Configuration must declare an offline review pilot with no network calls")
    seed, models = config.get("selection_seed"), config.get("model_keys")
    if not isinstance(seed, str) or not seed:
        raise ValueError("Missing deterministic selection seed")
    if (not isinstance(models, list) or any(not isinstance(key, str) for key in models)
            or len(models) != 2 or set(models) != set(MODEL_SPECS)):
        raise ValueError("Configuration must select the two declared OpenAI model keys")
    configured_limit = _limit(config.get("pilot_pairs_per_cell", 5))
    if config.get("max_completion_tokens") != 4096 or config.get("store") is not False:
        raise ValueError("Configuration differs from the request token/store parameters")
    specs = config.get("models", {})
    for key in models:
        declared = specs.get(key, {})
        if declared.get("snapshot") != MODEL_SPECS[key]["model"]:
            raise ValueError("Configured model snapshot differs from request builder")
        if (MODEL_SPECS[key].get("max_completion_tokens") != config["max_completion_tokens"]
                or MODEL_SPECS[key].get("store") is not config["store"]):
            raise ValueError("Configured request defaults differ from model defaults")
    if specs["gpt-4o-mini"].get("temperature") != MODEL_SPECS["gpt-4o-mini"].get("temperature"):
        raise ValueError("Configured gpt-4o-mini temperature differs from request builder")
    o3 = specs["o3-mini"]
    if (o3.get("temperature_policy") != "omit_use_service_default"
            or o3.get("reasoning_effort_policy") != "omit_use_service_default"
            or any(key in o3 or key in MODEL_SPECS["o3-mini"]
                   for key in ("temperature", "reasoning_effort", "top_p", "seed"))):
        raise ValueError("o3-mini optional generation parameters must be omitted")
    for name, expected in (("factual_population", "behavior_validation"),
                           ("counterfactual_population", "behavior_train")):
        if config.get(name, expected) != expected:
            raise ValueError("Configured selection population differs from review protocol")
    return {
        "path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
        "effective": {
            "scope": "offline_review_pilot", "network_calls": False,
            "selection_seed": seed, "model_keys": list(models),
            "configured_pairs_per_cell": configured_limit,
            "pairs_per_cell": configured_limit if pairs_per_cell is None else _limit(pairs_per_cell),
            "factual_population": "behavior_validation",
            "counterfactual_population": "behavior_train",
        },
    }


def select_pairs(dataset, *, seed, pairs_per_cell=5):
    """Bottom-K SHA256(seed,task,split,mode,event,action), O(6*K) heap space.

    Returns small selected records (including local array offsets) and aggregate
    cell counts. No features, post-treatment labs or rewards are accessed.
    """
    k = _limit(pairs_per_cell)
    if not isinstance(seed, str) or not seed or dataset.task not in ACTIONS:
        raise ValueError("Invalid review selection seed or task")
    cells = {(split, mode): {"heap": [], "candidate_pairs": 0, "candidate_events": 0}
             for split in SPLITS for mode in MODES}
    for index, event in enumerate(dataset.event_ids):
        fold = int(dataset.folds[index])
        if fold not in FOLD_CODES.values():
            raise ValueError("Unknown patient fold in review selection")
        mode = "factual" if fold == FOLD_CODES["validation"] else "counterfactual"
        observed = int(dataset.actions[index])
        actions = (observed,) if mode == "factual" else (a for a in ACTIONS[dataset.task] if a != observed)
        actions = tuple(actions)
        for column, split in enumerate(SPLITS):
            if int(dataset.roles[index, column]) != ROLE_CODES["behavior"]:
                continue
            cell = cells[split, mode]
            cell["candidate_events"] += 1
            for action in actions:
                key = [seed, dataset.task, split, mode, event, action]
                score = int.from_bytes(hashlib.sha256(_encoded(key)).digest(), "big")
                # Negative keys implement a max heap; event/action resolve hash ties.
                entry = (-score, -int(event, 16), -action, index)
                cell["candidate_pairs"] += 1
                if len(cell["heap"]) < k:
                    heapq.heappush(cell["heap"], entry)
                elif entry[:3] > cell["heap"][0][:3]:
                    heapq.heapreplace(cell["heap"], entry)
    selected, summaries = [], []
    for (split, mode), cell in cells.items():
        ordered = sorted(cell["heap"], key=lambda row: (-row[0], -row[1], -row[2]))
        fold = "validation" if mode == "factual" else "train"
        summaries.append({"split": split, "mode": mode, "fold": fold,
                          "candidate_events": cell["candidate_events"],
                          "candidate_pairs": cell["candidate_pairs"],
                          "selected_pairs": len(ordered)})
        selected.extend({"index": row[3], "event_id": dataset.event_ids[row[3]],
                         "action": -row[2], "split": split, "mode": mode,
                         "fold": fold, "rank": rank}
                        for rank, row in enumerate(ordered, 1))
    return selected, summaries


def _selected_contexts(directory, dataset, selected):
    indexes = {row["event_id"]: row["index"] for row in selected}
    factual_events = {row["event_id"] for row in selected if row["mode"] == "factual"}
    hashes = dataset.provenance["outputs"]
    contexts, labels = {}, {}

    def check_identity(row, index):
        if (int(row["subject_id"]) != int(dataset.subject_ids[index]) or
                int(row["hadm_id"]) != int(dataset.hadm_ids[index])):
            raise ValueError("Selected raw row patient/admission identity mismatch")

    # Exhaust both generators, even after all selected IDs were found: _rows
    # validates the entire file SHA only at EOF.
    for row in clinical_dataset._rows(directory / "features.csv", (*IDENTITY, *FEATURES), hashes["features.csv"]):
        event = row["event_id"]
        if event not in indexes:
            continue
        if event in contexts:
            raise ValueError("Duplicate selected feature event")
        check_identity(row, indexes[event])
        contexts[event] = {"features": {key: row[key] for key in FEATURES},
                           "anchor": parse_time(row["decision_time"])}
    seen = set()
    for row in clinical_dataset._rows(directory / "outcomes.csv", OUTCOMES, hashes["outcomes.csv"]):
        event = row["event_id"]
        if event not in indexes:
            continue
        if event in seen or event not in contexts:
            raise ValueError("Selected outcome is duplicated or lacks features")
        seen.add(event)
        index, context = indexes[event], contexts[event]
        check_identity(row, index)
        if row["task"] != dataset.task or row["action"] != str(int(dataset.actions[index])):
            raise ValueError("Selected raw outcome task/action mismatch")
        anchor = parse_time(row["anchor_time"])
        if anchor != context.pop("anchor"):
            raise ValueError("Selected feature and outcome anchors differ")
        pre_lab = row["pre_lab_value"] or None
        pre_hours = None
        if pre_lab is not None:
            chart = parse_time(row["pre_lab_time"])
            stored = parse_time(row["pre_latest_storetime"])
            if not anchor - timedelta(hours=4) <= chart <= stored <= anchor:
                raise ValueError("Selected pre-lab was not available in the pretreatment window")
            pre_hours = (anchor - chart).total_seconds() / 3600
        context.update(pre_lab_value=pre_lab, pre_lab_hours_before_anchor=pre_hours)
        if event in factual_events:
            lab = float(row["post_lab_value"])
            if not math.isfinite(lab) or lab <= 0:
                raise ValueError("Invalid selected factual label")
            labels[event] = lab
    if set(contexts) != set(indexes) or seen != set(indexes):
        raise ValueError("Selected raw input rows are incomplete")
    return contexts, labels


def _code_identity():
    paths = {"src/april_repro/llm_packet.py": Path(__file__)}
    for module in (clinical_dataset, cohort_splits, decision_features, llm_requests, rewards):
        paths["src/april_repro/" + module.__name__.split(".")[-1] + ".py"] = Path(module.__file__)
    cli = Path(__file__).resolve().parents[2] / "scripts/prepare_llm_requests.py"
    if cli.is_file():
        paths["scripts/prepare_llm_requests.py"] = cli
    return {name: {"path": str(path.resolve()), "sha256": _sha(path)} for name, path in paths.items()}


def _write_private(path, rows):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        for row in rows:
            handle.write(_encoded(row) + b"\n")


def prepare_packet(input_directory, output_directory, *, config_path, pairs_per_cell=None):
    """Create one task's offline pilot artifact, or fail without a complete manifest."""
    directory, output = Path(input_directory).resolve(), Path(output_directory).resolve()
    if output.exists():
        raise ValueError("Review packet output directory already exists")
    config = load_config(config_path, pairs_per_cell=pairs_per_cell)
    code = _code_identity()
    dataset = load_clinical_dataset(directory)
    source_sha = dataset.provenance["manifest_sha256"]
    effective = config["effective"]
    selected, cells = select_pairs(dataset, seed=effective["selection_seed"],
                                   pairs_per_cell=effective["pairs_per_cell"])
    contexts, labs = _selected_contexts(directory, dataset, selected)
    records, factual_labels = {}, {}
    for pair in selected:
        event = pair["event_id"]
        for model_key in effective["model_keys"]:
            record = build_request(
                event_id_sha256=event, input_manifest_sha256=source_sha,
                mode=pair["mode"], task=dataset.task,
                observed_action=int(dataset.actions[pair["index"]]), action=pair["action"],
                model_key=model_key, **contexts[event])
            key = record["request_id"]
            if key not in records:
                records[key] = {**record, "consumers": []}
            records[key]["consumers"].append({name: pair[name] for name in ("split", "mode", "fold", "rank")})
            if pair["mode"] == "factual":
                factual_labels[key] = {
                    "request_id": key, "protocol_id": record["protocol_id"],
                    "prompt_sha256": record["prompt_sha256"], "task": dataset.task,
                    "action": pair["action"], "post_lab_value": labs[event],
                    "input_manifest_sha256": source_sha,
                }
    if (_sha(directory / "manifest.json") != source_sha or
            _sha(config["path"]) != config["sha256"] or _code_identity() != code):
        raise ValueError("Input manifest, configuration or source code changed during preparation")
    output.mkdir(mode=0o700)
    _write_private(output / "requests.jsonl", (records[key] for key in sorted(records)))
    _write_private(output / "factual-labels.jsonl", (factual_labels[key] for key in sorted(factual_labels)))
    manifest = {
        "status": "complete", "rule_version": RULE_VERSION, "protocol_id": PROTOCOL_ID,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "task": dataset.task,
        "scope": "offline_review_pilot", "external_calls": 0,
        "formal_paper_annotation_budget": False,
        "input": {"directory": str(directory), "manifest_sha256": source_sha,
                  "outputs": dict(dataset.provenance["outputs"])},
        "config": config, "code": code,
        "selection": {"algorithm": "ascending_sha256(seed,task,split,mode,event,action)",
                      "outcomes_used": False, "same_pairs_across_models": True,
                      "cell_counts": cells},
        "summary": {"selected_pairs_across_cells": len(selected),
                    "selected_unique_events": len(contexts), "unique_requests": len(records),
                    "factual_label_rows": len(factual_labels),
                    "request_consumers": sum(len(record["consumers"]) for record in records.values()),
                    "unique_requests_by_mode": {mode: sum(record["metadata"]["mode"] == mode
                                                          for record in records.values()) for mode in MODES}},
        "outputs": {name: _sha(output / name) for name in ("requests.jsonl", "factual-labels.jsonl")},
    }
    _write_private(output / "manifest.json", [manifest])
    return manifest
