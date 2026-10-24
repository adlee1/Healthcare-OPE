"""Build a private formal annotation plan without network or credential access.

Clinical selection and prompt identity are reused verbatim from the pilot. The
larger cell limit extends deterministic prefixes; it does not resample or use
observed outcomes. Existing annotations are reusable only after raw receipt
revalidation. This plan is not an executable legacy review packet or a result.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tomllib

from april_repro import llm_packet, llm_requests, llm_five_requests
from april_repro import llm_run_summary, llm_receipts, llm_predictions
from april_repro.clinical_dataset import load_clinical_dataset, ROLE_CODES, FOLD_CODES
from april_repro.cohort_splits import ACTIONS, SPLITS


RULE_VERSION = "llm-formal-main-plan-v1"
SCOPE = "formal_main_annotation_plan"
BUDGETS = [0, 100, 200, 300, 400, 500]
MODES = llm_packet.MODES
_sha, _encoded, _write = llm_packet._sha, llm_packet._encoded, llm_packet._write_private


def load_config(path, *, selection_config_path, model_config_path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    config = tomllib.loads(raw.decode("utf-8"))
    old = llm_packet.load_config(selection_config_path)
    models = llm_five_requests.validate_five_config(model_config_path)
    expected = {
        "rule_version": RULE_VERSION, "scope": SCOPE, "network_calls": False,
        "selection_seed": old["effective"]["selection_seed"],
        "factual_pairs_per_cell": 500, "counterfactual_pairs_per_cell": 500,
        "counterfactual_budget_grid": BUDGETS,
        "factual_population": "behavior_validation",
        "counterfactual_population": "behavior_train",
        "selection_method": "ascending_sha256_without_outcome_or_model",
        "same_pairs_across_models": True, "reuse_validated_pilot_requests": True,
        "model_adapted": True, "historical_author_snapshot_recovered": False,
        "full_five_paper_models": False, "formal_paper_annotation_budget": True,
        "paper_experiment_complete": False,
    }
    if _encoded(config) != _encoded(expected):
        raise ValueError("Formal configuration differs from the declared main plan")
    if models["effective"]["registry_version"] != llm_five_requests.QWEN_DOMESTIC_REGISTRY_VERSION:
        raise ValueError("Formal main plan requires the existing explicit domestic Qwen profile")
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
            "effective": expected, "selection_config": old, "model_config": models}


def _code_identity():
    code = llm_packet._code_identity()
    for module in (llm_five_requests, llm_run_summary, llm_receipts, llm_predictions):
        path = Path(module.__file__).resolve()
        code["src/april_repro/" + path.name] = {"path": str(path), "sha256": _sha(path)}
    here = Path(__file__).resolve()
    code["src/april_repro/llm_formal_plan.py"] = {"path": str(here), "sha256": _sha(here)}
    cli = here.parents[2] / "scripts/prepare_formal_llm_plan.py"
    if cli.is_file():
        code["scripts/prepare_formal_llm_plan.py"] = {"path": str(cli), "sha256": _sha(cli)}
    return code


def _jsonl(path):
    return [json.loads(row) for row in Path(path).read_bytes().splitlines()]


def verify_pilot(summary_directory, packet_directories):
    """Recompute saved pilot summary from its original requests and raw receipts.

    Hashing parsed output alone does not establish a successful annotation.
    Missing or invalid requests remain non-reusable even if the summary artifact
    itself has status=complete (meaning its write operation completed).
    """
    if summary_directory is None:
        if packet_directories:
            raise ValueError("Pilot packets require their summary directory")
        return {}, {"provided": False, "verified_valid_requests": 0}, {}
    folder = Path(summary_directory).resolve()
    if not packet_directories:
        raise ValueError("Pilot summary requires explicit packet directories")
    manifest = json.loads((folder / "manifest.json").read_bytes())
    if (manifest.get("status") != "complete" or
            manifest.get("summary_version") != llm_run_summary.SUMMARY_VERSION or
            manifest.get("scope") != "offline_review_pilot" or
            set(manifest.get("outputs", {})) != {"summary.json", "parsed-annotations.jsonl"}):
        raise ValueError("Unsupported pilot summary artifact")
    bindings = {folder / "manifest.json": _sha(folder / "manifest.json")}
    for name, digest in manifest["outputs"].items():
        path = folder / name
        if _sha(path) != digest:
            raise ValueError("Pilot summary output hash mismatch")
        bindings[path] = digest
    if manifest.get("source_sha256") != _sha(Path(llm_run_summary.__file__)):
        raise ValueError("Pilot summary collector source changed")
    saved = json.loads((folder / "summary.json").read_bytes())
    explicit = [str(Path(path).resolve()) for path in packet_directories]
    if (len(set(explicit)) != len(explicit) or
            set(explicit) != {entry["directory"] for entry in saved["packets"]}):
        raise ValueError("Explicit pilot packets differ from saved summary")
    # Preserve saved ordering for exact, reproducible content comparison.
    packets = [entry["directory"] for entry in saved["packets"]]
    report, annotations = llm_run_summary.summarize_runs(
        packets, [entry["directory"] for entry in saved["runs"]])
    if report != saved or annotations != _jsonl(folder / "parsed-annotations.jsonl"):
        raise ValueError("Pilot summary differs from freshly verified raw receipts")
    if (manifest.get("aggregation_status") != report["status"] or
            manifest.get("unique_requests") != len(annotations)):
        raise ValueError("Pilot summary manifest counts mismatch")
    requests, labels = {}, {}
    for entry in report["packets"]:
        directory = Path(entry["directory"])
        bindings[directory / "manifest.json"] = entry["manifest_sha256"]
        _, digest, packet_requests, packet_labels = llm_run_summary._packet(directory)
        if digest != entry["manifest_sha256"]:
            raise ValueError("Pilot packet changed during revalidation")
        requests.update(packet_requests)
        labels.update(packet_labels)
        packet_manifest = json.loads((directory / "manifest.json").read_bytes())
        for name in ("requests.jsonl", "factual-labels.jsonl"):
            bindings[directory / name] = packet_manifest["outputs"][name]
    reusable = {}
    for annotation in annotations:
        if annotation["status"] == "valid" and not annotation["missing"]:
            rid = annotation["request_id"]
            reusable[rid] = {"request": requests[rid], "annotation": annotation,
                             "observed_lab": labels.get(rid)}
    return reusable, {"provided": True, "directory": str(folder),
        "manifest_sha256": bindings[folder / "manifest.json"],
        "raw_receipts_revalidated": True, "saved_parsed_output_compared": True,
        "summary_status": report["status"], "verified_valid_requests": len(reusable),
        "missing_requests": report["missing_predictions"],
        "invalid_requests_including_missing": report["invalid_predictions_including_missing"],
        "packets": report["packets"], "runs": report["runs"]}, bindings


def _cells(dataset, selected, counts):
    """Only identity, roles and folds are used to describe support and prefixes."""
    result = []
    for count in counts:
        split, mode = count["split"], count["mode"]
        column = SPLITS.index(split)
        chosen = sorted((row for row in selected if row["split"] == split and row["mode"] == mode),
                        key=lambda row: row["rank"])
        ranks = [row["rank"] for row in chosen]
        if ranks != list(range(1, len(chosen) + 1)):
            raise ValueError("Noncontiguous formal selection ranks")
        fold = FOLD_CODES[count["fold"]]
        candidate_subjects, target_subjects, target_events = set(), set(), 0
        for index, subject in enumerate(dataset.subject_ids):
            role = int(dataset.roles[index, column])
            if role == ROLE_CODES["behavior"] and int(dataset.folds[index]) == fold:
                candidate_subjects.add(int(subject))
            if role == ROLE_CODES["target"] and int(dataset.folds[index]) == FOLD_CODES["validation"]:
                target_events += 1
                target_subjects.add(int(subject))
        prefixes = []
        for budget in BUDGETS if mode == "counterfactual" else [500]:
            pairs = chosen[:budget]
            prefixes.append({"requested_pairs": budget, "selected_pairs": len(pairs),
                "budget_supported": len(pairs) == budget,
                "event_action_prefix_sha256": hashlib.sha256(_encoded(
                    [[row["event_id"], row["action"]] for row in pairs])).hexdigest()})
        result.append({"task": dataset.task, **count, "requested_pairs": 500,
            "selected_not_exceed_candidates": len(chosen) <= count["candidate_pairs"],
            "requested_budget_supported": count["candidate_pairs"] >= 500,
            "shortfall_pairs": 500 - len(chosen),
            "candidate_subjects": len(candidate_subjects),
            "selected_unique_events": len({row["event_id"] for row in chosen}),
            "selected_subjects": len({int(dataset.subject_ids[row["index"]]) for row in chosen}),
            "target_validation_events": target_events,
            "target_validation_subjects": len(target_subjects),
            "ope_target_reference_status": "available" if target_events else "not_estimable",
            "ope_target_reference_reason": None if target_events else "empty_target_validation",
            "annotation_preparation_retained_if_target_empty": True,
            "budget_prefixes": prefixes, "strict_nested_rank_prefixes": True})
    return result


def prepare_formal_plan(input_directories, output_directory, *, config_path,
                        selection_config_path, model_config_path,
                        pilot_summary_directory=None, pilot_packet_directories=()):
    """Prepare one or both tasks. No provider requests, credentials, or fitting."""
    output = Path(output_directory).resolve()
    if output.exists():
        raise ValueError("Formal plan output directory already exists")
    directories = [Path(path).resolve() for path in input_directories]
    if not directories or len(set(directories)) != len(directories):
        raise ValueError("Expected distinct clinical input directories")
    config = load_config(config_path, selection_config_path=selection_config_path,
                         model_config_path=model_config_path)
    code = _code_identity()
    pilot, reuse_evidence, bindings = verify_pilot(pilot_summary_directory, pilot_packet_directories)
    for info in (config, config["selection_config"], config["model_config"]):
        bindings[Path(info["path"])] = info["sha256"]
    records, labels, inputs, cells, tasks, subjects, events = {}, {}, [], [], set(), set(), set()
    models = config["model_config"]["effective"]["model_keys"]
    registry = config["model_config"]["effective"]["registry_version"]
    for directory in directories:
        dataset = load_clinical_dataset(directory)
        if dataset.task in tasks:
            raise ValueError("Only one clinical input is permitted per task")
        tasks.add(dataset.task)
        source_sha = dataset.provenance["manifest_sha256"]
        bindings[directory / "manifest.json"] = source_sha
        selected, counts = llm_packet.select_pairs(dataset,
            seed=config["effective"]["selection_seed"], pairs_per_cell=500)
        contexts, values = llm_packet._selected_contexts(directory, dataset, selected)
        cells.extend(_cells(dataset, selected, counts))
        inputs.append({"task": dataset.task, "directory": str(directory),
            "manifest_sha256": source_sha, "outputs": dict(dataset.provenance["outputs"])})
        for pair in selected:
            event = pair["event_id"]
            subjects.add(int(dataset.subject_ids[pair["index"]]))
            events.add((dataset.task, event))
            base = llm_requests.build_request(event_id_sha256=event,
                input_manifest_sha256=source_sha, task=dataset.task, mode=pair["mode"],
                observed_action=int(dataset.actions[pair["index"]]), action=pair["action"],
                model_key="gpt-4o-mini", **contexts[event])
            for model in models:
                record = llm_five_requests.build_five_request(base, model, registry_version=registry)
                rid = record["request_id"]
                if rid not in records:
                    records[rid] = {**record, "consumers": []}
                elif {k: v for k, v in records[rid].items() if k != "consumers"} != record:
                    raise ValueError("Duplicate request identity has different content")
                consumer = {key: pair[key] for key in ("split", "mode", "fold", "rank")}
                if any(old["split"] == pair["split"] for old in records[rid]["consumers"]):
                    raise ValueError("Duplicate formal consumer cell")
                records[rid]["consumers"].append(consumer)
                if pair["mode"] == "factual":
                    labels[rid] = {"request_id": rid, "protocol_id": record["protocol_id"],
                        "prompt_sha256": record["prompt_sha256"], "task": dataset.task,
                        "action": pair["action"], "post_lab_value": values[event],
                        "input_manifest_sha256": source_sha}
        del dataset, contexts, values
    reusable_ids = set()
    for rid, record in records.items():
        if rid in pilot:
            old = pilot[rid]["request"]
            if {key: value for key, value in old.items() if key != "consumers"} != {
                    key: value for key, value in record.items() if key != "consumers"}:
                raise ValueError("Pilot reuse identity content mismatch")
            if rid in labels and pilot[rid]["observed_lab"] != labels[rid]["post_lab_value"]:
                raise ValueError("Pilot factual label differs from the validated clinical input")
            reusable_ids.add(rid)
        llm_five_requests.validate_request(record)
    reuse_evidence["matched_formal_request_ids"] = sorted(reusable_ids)
    reuse_evidence["matched_formal_requests"] = len(reusable_ids)
    reuse_evidence["formal_consumers_preserved"] = True
    # Recheck bound code/config/manifest identities before publishing a complete plan.
    for path, digest in bindings.items():
        if _sha(path) != digest:
            raise ValueError("Bound input, configuration or pilot summary changed during planning")
    if _code_identity() != code:
        raise ValueError("Source code changed during formal planning")
    by_model = {}
    for model in models:
        rows = [row for row in records.values() if row["metadata"]["model_key"] == model]
        new = [row for row in rows if row["request_id"] not in reusable_ids]
        by_model[model] = {"unique_requests": len(rows),
            "verified_reusable": len(rows) - len(new), "new_unique_requests": len(new),
            "unique_by_mode": dict(Counter(row["metadata"]["mode"] for row in rows)),
            "payload_utf8_bytes": sum(len(_encoded(row["payload"])) for row in rows),
            "message_text_characters": sum(len(row["payload"]["messages"][0]["content"]) for row in rows),
            "new_payload_utf8_bytes": sum(len(_encoded(row["payload"])) for row in new),
            "new_message_text_characters": sum(len(row["payload"]["messages"][0]["content"]) for row in new)}
    output.mkdir(mode=0o700, parents=True)
    _write(output / "requests.jsonl", (records[key] for key in sorted(records)))
    _write(output / "factual-labels.jsonl", (labels[key] for key in sorted(labels)))
    manifest = {"status": "complete", "rule_version": RULE_VERSION, "scope": SCOPE,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "tasks": sorted(tasks),
        "external_calls": 0, "protocol_id": llm_requests.PROTOCOL_ID,
        "registry_version": registry,
        "registry_sha256": config["model_config"]["effective"]["registry_sha256"],
        "formal_paper_annotation_budget": True, "paper_experiment_complete": False,
        "model_adapted": True, "full_five_paper_models": False,
        "historical_author_snapshot_recovered": False,
        "formal_factual_cell_size_is_local_choice": True,
        "config": config, "code": code, "inputs": inputs, "pilot_reuse": reuse_evidence,
        "selection": {"algorithm": "ascending_sha256(seed,task,split,mode,event,action)",
            "outcomes_used": False, "same_pairs_across_models": True,
            "counterfactual_budget_grid": BUDGETS, "selection_seed": config["effective"]["selection_seed"],
            "no_replacement_when_candidates_insufficient": True, "cell_counts": cells},
        "summary": {"unique_requests": len(records), "selected_unique_events": len(events),
            "selected_unique_subjects_across_tasks": len(subjects), "factual_label_rows": len(labels),
            "selected_pairs_across_cells": sum(cell["selected_pairs"] for cell in cells),
            "request_consumers": sum(len(row["consumers"]) for row in records.values()),
            "unique_event_action_pairs": len(records) // len(models),
            "unique_requests_by_mode": dict(Counter(row["metadata"]["mode"] for row in records.values())),
            "verified_reusable_requests": len(reusable_ids),
            "new_unique_requests": len(records) - len(reusable_ids), "by_model": by_model},
        "cost_inputs": {"payload_text_lengths_are_not_token_or_billing_estimates": True,
                        "actual_future_attempt_count_unknown": True},
        "outputs": {name: _sha(output / name) for name in ("requests.jsonl", "factual-labels.jsonl")}}
    _write(output / "manifest.json", [manifest])
    return manifest
