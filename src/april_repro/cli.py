"""Checkout-oriented command line for audit and database discovery."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tomllib

from . import __version__
from .database import DatabaseError, PsqlClient, QUERY_FILES, connection_environment, connection_status
from .profiling import run_profiles
from .preregistration import (
    potassium_mapping_preflight_preregistration_report,
    potassium_outcome_preregistration_report,
    potassium_product_mapping_preregistration_report,
    potassium_query202_extraction_preregistration_report,
    potassium_query202_mapped_event_application_preregistration_report,
    potassium_query202_pre_adjudication_preregistration_report,
    potassium_query202_pre_adjudication_v2_preregistration_report,
    query202_adjudication_input_preregistration_report,
    query202_human_adjudication_preregistration_report,
    query202_ndc_evidence_mode_preregistration_report,
    potassium_route_adjudication_preregistration_report,
    potassium_source_discovery_preregistration_report,
)
from .rewards import F1_BOUNDARIES, PAPER_REWARD_SIGMA, REFERENCE_RANGES


def project_root(explicit: str | None = None) -> Path:
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not (root / "config" / "protocol.toml").is_file():
            raise ValueError("Project root must contain config/protocol.toml")
        return root
    for root in (Path.cwd(), *Path.cwd().parents, Path(__file__).resolve().parents[2]):
        if (root / "config" / "protocol.toml").is_file():
            return root
    raise ValueError("Run from the project checkout or supply --project-root")


def emit(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def read_protocol(root: Path) -> dict:
    with (root / "config" / "protocol.toml").open("rb") as handle:
        return tomllib.load(handle)


def validate_protocol(config: dict) -> list[str]:
    errors = []
    if type(config.get("schema_version")) is not int or config.get("schema_version") != 1:
        errors.append("Unsupported schema_version")
    if config.get("status") != "draft":
        errors.append("Foundation supports draft protocols only; evidence-backed freezing is not implemented yet")
    for section in ("potassium", "sodium", "inputs", "evaluation", "llm"):
        if not isinstance(config.get(section), dict):
            errors.append(f"Missing or invalid section: {section}")
    if errors:
        return errors
    for task, actions in (
        ("potassium", [0, 10, 20, 40]),
        ("sodium", [0, 100, 200, 300, 400, 500]),
    ):
        settings = config.get(task, {})
        if settings.get("actions") != actions:
            errors.append(f"{task}: action space differs from the paper specification")
        if settings.get("f1_thresholds") != list(F1_BOUNDARIES[task]):
            errors.append(f"{task}: F1 thresholds differ from Appendix A")
        if settings.get("reward_reference_range") != list(REFERENCE_RANGES[task]):
            errors.append(f"{task}: reward reference range differs from the implemented paper formula")
        if settings.get("reward_sigma_as_printed") != PAPER_REWARD_SIGMA:
            errors.append(f"{task}: reward sigma differs from the implemented paper-formula candidate")
    if config.get("dataset_version_verified") is not False:
        errors.append("Foundation has no verified dataset version; keep dataset_version_verified=false")
    if config["llm"].get("patient_data_calls_enabled") is not False:
        errors.append("Foundation does not implement patient-data LLM calls")
    if config["evaluation"].get("bootstrap_repetitions") != 500:
        errors.append("Paper specification requires 500 bootstrap repetitions")
    if config["evaluation"].get("paired_comparison_annotation_budget") != 500:
        errors.append("Paper Table 2 comparison specifies 500 annotations")
    if config["evaluation"].get("main_annotation_budgets") != [0, 100, 200, 300, 400, 500]:
        errors.append("Main figure annotation budgets differ from the recorded paper specification")
    expected_decisions = [f"D{index:03d}" for index in range(1, 13)]
    if config.get("unresolved_decisions") != expected_decisions:
        errors.append("Foundation requires the complete D001-D012 register; decision resolution is not implemented yet")
    return errors


def doctor(root: Path) -> int:
    config = read_protocol(root)
    potassium_outcome = potassium_outcome_preregistration_report(root)
    potassium_source_discovery = potassium_source_discovery_preregistration_report(root)
    potassium_product_mapping = potassium_product_mapping_preregistration_report(root)
    potassium_mapping_preflight = potassium_mapping_preflight_preregistration_report(root)
    potassium_query202_extraction = potassium_query202_extraction_preregistration_report(root)
    potassium_query202_pre_adjudication = (
        potassium_query202_pre_adjudication_preregistration_report(root)
    )
    potassium_query202_pre_adjudication_v2 = (
        potassium_query202_pre_adjudication_v2_preregistration_report(root)
    )
    potassium_query202_adjudication_input = (
        query202_adjudication_input_preregistration_report(root)
    )
    potassium_query202_ndc_evidence_mode = (
        query202_ndc_evidence_mode_preregistration_report(root)
    )
    potassium_query202_human_adjudication = (
        query202_human_adjudication_preregistration_report(root)
    )
    potassium_query202_mapped_event_application = (
        potassium_query202_mapped_event_application_preregistration_report(root)
    )
    potassium_route_adjudication = potassium_route_adjudication_preregistration_report(root)
    component_preregistrations = [
        potassium_outcome,
        potassium_source_discovery,
        potassium_product_mapping,
        potassium_mapping_preflight,
        potassium_route_adjudication,
        potassium_query202_extraction,
        potassium_query202_pre_adjudication,
        potassium_query202_pre_adjudication_v2,
        potassium_query202_adjudication_input,
        potassium_query202_ndc_evidence_mode,
        potassium_query202_human_adjudication,
        potassium_query202_mapped_event_application,
    ]
    protocol_errors = validate_protocol(config) + [
        error
        for component in component_preregistrations
        for error in component["errors"]
    ]
    psql = shutil.which("psql")
    client_version = None
    if psql:
        result = subprocess.run([psql, "--version"], text=True, capture_output=True, timeout=5)
        client_version = result.stdout.strip() if result.returncode == 0 else "unavailable"
    emit({
        "project": str(root), "package_version": __version__, "python": platform.python_version(),
        "python_executable": sys.executable, "platform": platform.platform(),
        "core_third_party_dependencies": [], "psql": client_version,
        "connection": connection_status(connection_environment(root)),
        "protocol_status": config.get("status"), "protocol_errors": protocol_errors,
        "component_preregistrations": component_preregistrations,
        "unresolved_decisions": config.get("unresolved_decisions"),
        "database_queried": False, "llm_called": False,
    })
    return 0 if not protocol_errors else 1


def protocol_check(root: Path, require_frozen: bool) -> int:
    config = read_protocol(root)
    potassium_outcome = potassium_outcome_preregistration_report(root)
    potassium_source_discovery = potassium_source_discovery_preregistration_report(root)
    potassium_product_mapping = potassium_product_mapping_preregistration_report(root)
    potassium_mapping_preflight = potassium_mapping_preflight_preregistration_report(root)
    potassium_query202_extraction = potassium_query202_extraction_preregistration_report(root)
    potassium_query202_pre_adjudication = (
        potassium_query202_pre_adjudication_preregistration_report(root)
    )
    potassium_query202_pre_adjudication_v2 = (
        potassium_query202_pre_adjudication_v2_preregistration_report(root)
    )
    potassium_query202_adjudication_input = (
        query202_adjudication_input_preregistration_report(root)
    )
    potassium_query202_ndc_evidence_mode = (
        query202_ndc_evidence_mode_preregistration_report(root)
    )
    potassium_query202_human_adjudication = (
        query202_human_adjudication_preregistration_report(root)
    )
    potassium_query202_mapped_event_application = (
        potassium_query202_mapped_event_application_preregistration_report(root)
    )
    potassium_route_adjudication = potassium_route_adjudication_preregistration_report(root)
    component_preregistrations = [
        potassium_outcome,
        potassium_source_discovery,
        potassium_product_mapping,
        potassium_mapping_preflight,
        potassium_route_adjudication,
        potassium_query202_extraction,
        potassium_query202_pre_adjudication,
        potassium_query202_pre_adjudication_v2,
        potassium_query202_adjudication_input,
        potassium_query202_ndc_evidence_mode,
        potassium_query202_human_adjudication,
        potassium_query202_mapped_event_application,
    ]
    errors = validate_protocol(config) + [
        error
        for component in component_preregistrations
        for error in component["errors"]
    ]
    if require_frozen and config.get("status") != "frozen":
        errors.append("Protocol is draft: dependent full experiments must not be treated as a frozen reproduction")
    emit({"status": config.get("status"), "valid_structure": not errors,
          "unresolved_decisions": config.get("unresolved_decisions"),
          "component_preregistrations": component_preregistrations, "errors": errors})
    return 2 if errors else 0


def db_run(root: Path, inspect: bool, timeout_ms: int) -> int:
    client = PsqlClient(root, timeout_ms)
    filenames = QUERY_FILES if inspect else QUERY_FILES[:1]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = root / "artifacts" / "db" / stamp
    destination.mkdir(parents=True, exist_ok=False)
    report = {"started_at_utc": stamp, "scope": "database_metadata_only", "read_only": True,
              "dataset_version_verified": False, "queries": [], "status": "running"}
    report_path = destination / "manifest.json"
    try:
        for filename in filenames:
            csv_text, rows, sql_sha256 = client.query(filename)
            output = destination / (Path(filename).stem + ".csv")
            output.write_text(csv_text)
            report["queries"].append({"query": filename, "rows": len(rows),
                "sql_sha256": sql_sha256,
                "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest()})
        report["status"] = "complete"
    except (DatabaseError, ValueError, OSError) as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        raise
    finally:
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    emit({"status": report["status"], "report": str(report_path), "queries": report["queries"],
          "note": "Schema names do not independently verify the MIMIC release. No patient rows were exported."})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="APRIL independent reproduction: protocol audit and read-only database discovery")
    parser.add_argument("--project-root")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check the local environment without connecting")
    protocol = commands.add_parser("protocol").add_subparsers(dest="protocol_command", required=True)
    check = protocol.add_parser("check", help="Validate the draft specification")
    check.add_argument("--require-frozen", action="store_true")
    db = commands.add_parser("db").add_subparsers(dest="db_command", required=True)
    for name in ("check", "inspect"):
        command = db.add_parser(name, help="Read-only identity check" if name == "check" else "Read-only metadata inventory")
        command.add_argument("--timeout-ms", type=int, choices=range(100, 120001), metavar="100..120000", default=10000)
    profile = db.add_parser("profile", help="Run registered, bounded aggregate and dictionary profiling queries")
    profile.add_argument("--query", action="append", dest="queries", metavar="NAME", help="Select a registered query; repeat for multiple queries (default: all)")
    profile.add_argument("--timeout-ms", type=int, choices=range(100, 120001), metavar="100..120000", default=10000)
    args = parser.parse_args(argv)
    try:
        root = project_root(args.project_root)
        if args.command == "doctor":
            return doctor(root)
        if args.command == "protocol":
            return protocol_check(root, args.require_frozen)
        if args.db_command == "profile":
            summary = run_profiles(root, args.queries, args.timeout_ms)
            emit(summary)
            return 0 if summary["status"] == "complete" else 2
        return db_run(root, args.db_command == "inspect", args.timeout_ms)
    except (DatabaseError, ValueError, FileNotFoundError, tomllib.TOMLDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
