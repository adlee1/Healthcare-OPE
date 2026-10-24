"""Expand a validated two-model offline packet without selecting new events.

Only the small source packet and its provenance files are read. Clinical CSVs
are neither opened nor reselected. Factual labels stay outside API payloads.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

from april_repro import llm_five_requests, llm_requests
from april_repro.cohort_splits import ACTIONS, SPLITS


RULE_VERSION = "llm-five-review-packet-v1"
SOURCE_RULE_VERSION = "llm-review-packet-v1"
MODES = ("factual", "counterfactual")
OUTPUT_NAMES = ("requests.jsonl", "factual-labels.jsonl")


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_file(path, digest, bindings):
    path = Path(path).resolve()
    llm_requests._sha_identity(digest, "file")
    if _sha(path) != digest:
        raise ValueError("Source packet provenance hash mismatch")
    if path in bindings and bindings[path] != digest:
        raise ValueError("Conflicting provenance hashes")
    bindings[path] = digest


def _jsonl(path):
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def _consumer_key(consumer, mode):
    if not isinstance(consumer, dict) or set(consumer) != {"split", "mode", "fold", "rank"}:
        raise ValueError("Malformed source request consumer")
    fold = "validation" if mode == "factual" else "train"
    if (consumer["split"] not in SPLITS or consumer["mode"] != mode or
            consumer["fold"] != fold or type(consumer["rank"]) is not int or
            consumer["rank"] < 1):
        raise ValueError("Invalid source request consumer population")
    return consumer["split"], mode


def _summary(records, labels, pairs):
    return {
        "selected_pairs_across_cells": sum(len(group[0]["consumers"]) for group in pairs.values()),
        "selected_unique_events": len({key[1] for key in pairs}),
        "unique_requests": len(records), "factual_label_rows": len(labels),
        "request_consumers": sum(len(record["consumers"]) for record in records),
        "unique_requests_by_mode": {mode: sum(record["metadata"]["mode"] == mode
                                              for record in records) for mode in MODES},
    }


def _load_source(directory):
    bindings = {}
    manifest_path = directory / "manifest.json"
    manifest_sha = _sha(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _check_file(manifest_path, manifest_sha, bindings)
    if (manifest.get("status") != "complete" or manifest.get("rule_version") != SOURCE_RULE_VERSION
            or manifest.get("scope") != "offline_review_pilot" or manifest.get("external_calls") != 0
            or manifest.get("formal_paper_annotation_budget") is not False
            or manifest.get("protocol_id") != llm_requests.PROTOCOL_ID
            or manifest.get("task") not in ACTIONS):
        raise ValueError("Source must be a complete original two-model offline pilot packet")
    if set(manifest.get("outputs", {})) != set(OUTPUT_NAMES):
        raise ValueError("Source packet output set mismatch")
    for name in OUTPUT_NAMES:
        _check_file(directory / name, manifest["outputs"][name], bindings)
    code = manifest.get("code", {})
    if not code or not {"src/april_repro/llm_packet.py", "src/april_repro/llm_requests.py"} <= set(code):
        raise ValueError("Source packet lacks source-code provenance")
    for info in code.values():
        _check_file(info["path"], info["sha256"], bindings)
    config = manifest["config"]
    _check_file(config["path"], config["sha256"], bindings)
    source = manifest["input"]
    _check_file(Path(source["directory"]) / "manifest.json", source["manifest_sha256"], bindings)
    records = _jsonl(directory / "requests.jsonl")
    labels = _jsonl(directory / "factual-labels.jsonl")
    pairs, by_id = {}, {}
    for record in records:
        # The new builder validates legacy parameters, metadata and all hashes.
        llm_five_requests.validate_base_request(record)
        rid, meta = record["request_id"], record["metadata"]
        if rid in by_id:
            raise ValueError("Duplicate source request identity")
        if meta["task"] != manifest["task"] or meta["input_manifest_sha256"] != source["manifest_sha256"]:
            raise ValueError("Source request task or input identity mismatch")
        consumers = record.get("consumers")
        if not isinstance(consumers, list) or not consumers:
            raise ValueError("Source request requires consumers")
        consumer_keys = [_consumer_key(row, meta["mode"]) for row in consumers]
        if len(set(consumer_keys)) != len(consumer_keys):
            raise ValueError("Duplicate source consumer cell")
        by_id[rid] = record
        key = (meta["task"], meta["event_id"], meta["mode"], meta["action"])
        pairs.setdefault(key, []).append(record)
    ranks = {(split, mode): [] for split in SPLITS for mode in MODES}
    for group in pairs.values():
        if len(group) != 2 or {r["metadata"]["model_key"] for r in group} != set(llm_requests.MODEL_SPECS):
            raise ValueError("Each source event/action must have exactly the two original models")
        left, right = group
        ignored = {"model_key", "model_snapshot"}
        if ({k: v for k, v in left["metadata"].items() if k not in ignored} !=
                {k: v for k, v in right["metadata"].items() if k not in ignored}
                or left["payload"]["messages"] != right["payload"]["messages"]
                or left["consumers"] != right["consumers"]):
            raise ValueError("Source models do not share identical clinical prompts and consumers")
        for consumer in left["consumers"]:
            ranks[consumer["split"], consumer["mode"]].append(consumer["rank"])
    selection = manifest["selection"]
    if selection.get("outcomes_used") is not False or selection.get("same_pairs_across_models") is not True:
        raise ValueError("Source selection does not preserve independent paired sampling")
    seen_cells = set()
    for cell in selection["cell_counts"]:
        key = cell["split"], cell["mode"]
        if key not in ranks or key in seen_cells:
            raise ValueError("Duplicate or unknown source selection cell")
        seen_cells.add(key)
        expected_fold = "validation" if key[1] == "factual" else "train"
        count = len(ranks[key])
        if (cell["fold"] != expected_fold or type(cell["selected_pairs"]) is not int
                or cell["selected_pairs"] != count or sorted(ranks[key]) != list(range(1, count + 1))
                or type(cell["candidate_pairs"]) is not int or cell["candidate_pairs"] < count
                or type(cell["candidate_events"]) is not int or cell["candidate_events"] < 0):
            raise ValueError("Source selection cell counts or ranks mismatch")
    if seen_cells != set(ranks):
        raise ValueError("Source selection cells are incomplete")
    label_by_id = {}
    for label in labels:
        rid = label["request_id"]
        if rid in label_by_id or rid not in by_id:
            raise ValueError("Duplicate or unassociated source factual label")
        record, value = by_id[rid], label["post_lab_value"]
        meta = record["metadata"]
        if (meta["mode"] != "factual" or type(value) not in (int, float)
                or not math.isfinite(value) or value <= 0):
            raise ValueError("Invalid source factual label")
        expected = {"request_id": rid, "protocol_id": record["protocol_id"],
                    "prompt_sha256": record["prompt_sha256"], "task": meta["task"],
                    "action": meta["action"], "post_lab_value": value,
                    "input_manifest_sha256": meta["input_manifest_sha256"]}
        if label != expected:
            raise ValueError("Source factual label identity mismatch")
        label_by_id[rid] = label
    if set(label_by_id) != {r["request_id"] for r in records if r["metadata"]["mode"] == "factual"}:
        raise ValueError("Source factual label coverage mismatch")
    for group in pairs.values():
        if group[0]["metadata"]["mode"] == "factual":
            if len({label_by_id[r["request_id"]]["post_lab_value"] for r in group}) != 1:
                raise ValueError("Paired source models have different factual labels")
    summary = _summary(records, labels, pairs)
    if any(manifest["summary"].get(key) != value for key, value in summary.items()):
        raise ValueError("Source packet summary differs from records")
    return manifest, manifest_sha, pairs, label_by_id, bindings


def _code_identity():
    paths = {"src/april_repro/llm_five_packet.py": Path(__file__)}
    for module in (llm_five_requests, llm_requests):
        paths["src/april_repro/" + module.__name__.split(".")[-1] + ".py"] = Path(module.__file__)
    cli = Path(__file__).resolve().parents[2] / "scripts/prepare_five_llm_requests.py"
    if cli.is_file():
        paths["scripts/prepare_five_llm_requests.py"] = cli
    return {name: {"path": str(path.resolve()), "sha256": _sha(path)} for name, path in paths.items()}


def _write_private(path, rows):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        for row in rows:
            handle.write(_encoded(row) + b"\n")


def prepare_five_packet(source_packet_directory, output_directory, *, config_path):
    """Return a complete private five-model manifest; never issue network calls."""
    directory, output = Path(source_packet_directory).resolve(), Path(output_directory).resolve()
    if output.exists():
        raise ValueError("Five-model output directory already exists")
    config = llm_five_requests.validate_five_config(config_path)
    code = _code_identity()
    old, source_sha, pairs, source_labels, bindings = _load_source(directory)
    _check_file(config["path"], config["sha256"], bindings)
    records, labels = [], []
    for key in sorted(pairs):
        base = sorted(pairs[key], key=lambda row: row["metadata"]["model_key"])[0]
        for model_key in config["effective"]["model_keys"]:
            record = llm_five_requests.build_five_request(
                base, model_key, registry_version=config["effective"]["registry_version"])
            records.append(record)
            if key[2] == "factual":
                label = copy.deepcopy(source_labels[base["request_id"]])
                label.update(request_id=record["request_id"], protocol_id=record["protocol_id"],
                             prompt_sha256=record["prompt_sha256"])
                labels.append(label)
    if len({r["request_id"] for r in records}) != len(records):
        raise ValueError("Duplicate expanded request identity")
    for path, digest in bindings.items():
        if _sha(path) != digest:
            raise ValueError("Source packet or configuration changed during expansion")
    if _code_identity() != code:
        raise ValueError("Source code changed during expansion")
    output.mkdir(mode=0o700)
    _write_private(output / "requests.jsonl", sorted(records, key=lambda row: row["request_id"]))
    _write_private(output / "factual-labels.jsonl", sorted(labels, key=lambda row: row["request_id"]))
    summary = _summary(records, labels, pairs)
    summary["unique_event_action_pairs"] = len(pairs)
    summary["unique_requests_by_model"] = {model: sum(r["metadata"]["model_key"] == model for r in records)
                                            for model in config["effective"]["model_keys"]}
    manifest = {
        "status": "complete", "rule_version": RULE_VERSION, "protocol_id": old["protocol_id"],
        "registry_version": config["effective"]["registry_version"],
        "registry_sha256": config["effective"]["registry_sha256"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "task": old["task"],
        "scope": "offline_review_pilot", "external_calls": 0,
        "formal_paper_annotation_budget": False, "full_five_paper_models": False,
        "input": copy.deepcopy(old["input"]), "config": config, "code": code,
        "source_packet": {"directory": str(directory), "manifest_sha256": source_sha,
                          "rule_version": old["rule_version"], "outputs": copy.deepcopy(old["outputs"]),
                          "config": copy.deepcopy(old["config"]), "code": copy.deepcopy(old["code"]),
                          "summary": copy.deepcopy(old["summary"])},
        "selection": {**copy.deepcopy(old["selection"]), "resampled": False,
                      "source_packet_cell_counts_preserved": True},
        "summary": summary,
        "outputs": {name: _sha(output / name) for name in OUTPUT_NAMES},
    }
    _write_private(output / "manifest.json", [manifest])
    return manifest
