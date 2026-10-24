"""Fail-closed freeze report for the Query-202 NDC evidence mode.

This component verifies whole-file and public-lineage evidence only.  It never
decompresses, parses, or emits a row from the private NDC handoff.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import tomllib
from typing import Any, Mapping, Sequence


CONFIG_PATH = Path(
    "config/preregistrations/d005_potassium_query202_ndc_evidence_mode.toml"
)
COMPONENT_ID = "D005-K-QUERY202-NDC-EVIDENCE-MODE-v1"
SOURCE_COMPONENT_ID = "D005-K-QUERY202-ADJUDICATION-INPUT-v1"
PLACEHOLDER = "UNSET_REQUIRED_BEFORE_FREEZE"
BUNDLE_ENCODING = "uint32be_path_length+path_utf8+uint64be_content_length+content"
EXPECTED_VALIDATOR_PATHS = (
    "src/april_repro/__init__.py",
    "src/april_repro/query202_ndc_evidence_mode_preregistration.py",
    "scripts/report_potassium_query202_ndc_evidence_mode.py",
)

EXPECTED_NDC_HANDOFF = {
    "file": "ndc-handoff.jsonl.gz",
    "encoding": "gzip+utf8+ndjson-v1",
    "stored_sha256": (
        "5a231724d29e163546c4c705459fe64bdc2448bedfac7205bb510fefeac7463d"
    ),
    "stored_bytes": 3_369_595,
    "raw_sha256": (
        "02861f388c49015796ea3a8149b666c3a5b31e23af99dc230b2b0db15c4c950b"
    ),
    "raw_bytes": 64_497_871,
    "records": 195_944,
}

EXPECTED_SOURCE = {
    "artifact_directory": (
        "artifacts/query202-adjudication-input/20261013T063022.591471Z"
    ),
    "component_id": SOURCE_COMPONENT_ID,
    "config_file": (
        "config/preregistrations/"
        "d005_potassium_query202_adjudication_input.toml"
    ),
    "config_sha256": (
        "ed3f656243adbbf0060731e0ef6323b5dadb58e5c614691dd67eda97cd638f3d"
    ),
    "manifest_file": "manifest.json",
    "manifest_sha256": (
        "cd99bafbf5b8567edae8de1c1430a2b1e3ecb4501eb238190f59270b0bd717d6"
    ),
    "aggregate_summary_file": "aggregate-summary.json",
    "aggregate_summary_sha256": (
        "a10198946acf86a3a327d95eaa5eff53952275495b7befa59f7087d72e98644f"
    ),
    "audit_file": "audit-summary.json",
    "audit_sha256": (
        "07a442689e6be15c98f05a817737a67ca6c0637f176a68e68c75a7d36cadb851"
    ),
    "component_status_required": "complete",
    "source_status_at_execution_required": "frozen_for_execution",
    "audit_status_required": "passed",
    "audit_failed_checks_required": 0,
    "ndc_handoff": EXPECTED_NDC_HANDOFF,
}

EXPECTED_DECISION_STATIC = {
    "mode": "not_used_frozen",
    "used_in_current_semantic_adjudication": False,
    "external_mapping_artifact_required": False,
    "external_mapping_artifact_created": False,
    "external_api_called": False,
    "normalization_performed": False,
    "mapping_performed": False,
    "establishes_product_identity": False,
    "establishes_route": False,
    "establishes_administration": False,
}

EXPECTED_EVIDENCE_BOUNDARY = {
    "complete_handoff_retained_unchanged": True,
    "private_handoff_rows_may_be_read": False,
    "private_handoff_rows_may_be_printed": False,
    "database_access_allowed": False,
    "network_access_allowed": False,
    "external_api_allowed": False,
    "normalization_allowed": False,
    "mapping_allowed": False,
    "semantic_adjudication_may_consume_ndc": False,
    "artifact_directory_mode": "0700",
    "evidence_file_mode": "0600",
    "git_ignored_required": True,
    "public_raw_values_allowed": False,
    "public_per_value_hashes_allowed": False,
}

EXPECTED_CHANGE_CONTROL = {
    "input_hash_change_requires_new_component_version": True,
    "mode_change_requires_new_component_version": True,
    "future_ndc_mapping_requires_new_component_version": True,
    "future_ndc_use_requires_separate_frozen_decision": True,
    "handoff_must_remain_available_for_future_version": True,
    "downstream_code_must_not_infer_product_route_or_administration_from_nonuse": True,
}

EXPECTED_DOWNSTREAM_CONTRACT = {
    "decision_manifest_is_this_config": True,
    "consumer_component_id": "D005-K-QUERY202-MAPPED-EVENT-APPLICATION-v1",
    "consumer_external_ndc_evidence_mode": "not_used_frozen",
    "consumer_must_bind_component_id": True,
    "consumer_must_bind_config_sha256": True,
    "consumer_must_bind_validator_bundle_sha256": True,
    "consumer_must_require_status_frozen": True,
    "consumer_must_require_decision_effective": True,
    "consumer_must_reverify_source_whole_file_hashes": True,
    "consumer_must_not_read_handoff_rows_for_current_semantic_adjudication": True,
}

EXPECTED_FALSE_GUARDS = {
    "external_ndc_mapping_executed": False,
    "semantic_review_complete": False,
    "reviewed_semantic_ledger_frozen": False,
    "route_mapping_frozen": False,
    "product_identity_decided": False,
    "product_mapping_accepted": False,
    "event_mapping_created": False,
    "final_source_policy": False,
    "complete_intervention_coverage": False,
    "formal_action": False,
    "formal_episode": False,
    "zero_action_constructed": False,
    "formal_non_icu_rule": False,
    "formal_label": False,
    "formal_cohort": False,
    "patient_data_exported": False,
    "llm_called": False,
}

EXPECTED_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "component_id",
        "decision_id",
        "status",
        "execution_status",
        "execution_permitted",
        "specified_on",
        "rule_version",
        "scope",
        "source",
        "decision",
        "evidence_boundary",
        "change_control",
        "downstream_contract",
        "implementation",
        "guards",
    }
)


class NdcEvidenceModeError(RuntimeError):
    """Raised when a safe, aggregate-only report cannot be produced."""


def _strict_equal(actual: object, expected: object) -> bool:
    if isinstance(expected, Mapping):
        return (
            isinstance(actual, Mapping)
            and set(actual) == set(expected)
            and all(_strict_equal(actual[key], value) for key, value in expected.items())
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _strict_equal(left, right)
                for left, right in zip(actual, expected)
            )
        )
    return type(actual) is type(expected) and actual == expected


def _validate_exact_mapping(
    actual: object,
    expected: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(actual, Mapping):
        errors.append(f"{label} must be a table")
        return
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    if missing or unexpected:
        errors.append(
            f"{label} keys changed: missing={missing!r}, unexpected={unexpected!r}"
        )
    for key, expected_value in expected.items():
        if key in actual and not _strict_equal(actual[key], expected_value):
            errors.append(f"{label}.{key} contract changed")


def _safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _project_path(root: Path, relative: object) -> Path:
    if not _safe_relative(relative) or root.is_symlink():
        raise OSError("unsafe project-relative path")
    resolved_root = root.resolve(strict=True)
    candidate = root
    for part in Path(str(relative)).parts:
        candidate /= part
        if candidate.is_symlink():
            raise OSError("symlink in project-relative path")
    candidate.resolve(strict=True).relative_to(resolved_root)
    return candidate


def _same_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_size,
        left.st_mtime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_size,
        right.st_mtime_ns,
    )


def _snapshot_regular_file(
    root: Path,
    relative: object,
    *,
    retain_payload: bool,
) -> dict[str, Any]:
    path = _project_path(root, relative)
    initial = path.lstat()
    if not stat.S_ISREG(initial.st_mode):
        raise OSError("expected a regular file")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    payload_parts: list[bytes] | None = [] if retain_payload else None
    digest = hashlib.sha256()
    total = 0
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not _same_snapshot(initial, before):
            raise OSError("file identity changed before hashing")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            if payload_parts is not None:
                payload_parts.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    final = path.lstat()
    if not (
        _same_snapshot(before, after)
        and _same_snapshot(after, final)
        and total == after.st_size
    ):
        raise OSError("file identity changed while hashing")
    return {
        "sha256": digest.hexdigest(),
        "bytes": total,
        "mode": stat.S_IMODE(after.st_mode),
        "identity": (after.st_dev, after.st_ino),
        "payload": b"".join(payload_parts) if payload_parts is not None else None,
    }


def _snapshot_seal(snapshot: Mapping[str, Any]) -> tuple[object, ...]:
    """Return the fields that must remain identical across the full report."""
    return tuple(
        snapshot.get(key) for key in ("identity", "mode", "sha256", "bytes")
    )


def _directory_seal(root: Path, relative: object) -> dict[str, Any]:
    """Bind directory identity and mode without relying on directory mtime."""
    path = _project_path(root, relative)
    value = path.lstat()
    if not stat.S_ISDIR(value.st_mode):
        raise OSError("expected a directory")
    return {
        "identity": (value.st_dev, value.st_ino),
        "mode": stat.S_IMODE(value.st_mode),
    }


def _strict_json(payload: bytes) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON object key")
            value[key] = item
        return value

    text = payload.decode("utf-8")
    return json.loads(text, object_pairs_hook=object_pairs)


def _read_config_snapshot(
    root: Path,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    snapshot = _snapshot_regular_file(root, str(CONFIG_PATH), retain_payload=True)
    payload = snapshot["payload"]
    if not isinstance(payload, bytes):
        raise NdcEvidenceModeError("configuration snapshot unavailable")
    try:
        config = tomllib.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise NdcEvidenceModeError("configuration is not valid UTF-8 TOML") from exc
    return config, str(snapshot["sha256"]), snapshot


def read_query202_ndc_evidence_mode_preregistration(root: Path) -> dict[str, Any]:
    config, _sha256, _snapshot = _read_config_snapshot(root)
    return config


def validate_query202_ndc_evidence_mode_preregistration(
    config: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    missing = sorted(EXPECTED_ROOT_KEYS - set(config))
    unexpected = sorted(set(config) - EXPECTED_ROOT_KEYS)
    if missing or unexpected:
        errors.append(
            f"root keys changed: missing={missing!r}, unexpected={unexpected!r}"
        )

    expected_scalars = {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "decision_id": "D005",
        "execution_status": "not_applicable",
        "execution_permitted": False,
        "specified_on": "2026-10-13",
        "scope": (
            "Freeze non-use of the complete Query 202 NDC handoff in current "
            "semantic adjudication"
        ),
    }
    for key, expected in expected_scalars.items():
        if key not in config or not _strict_equal(config[key], expected):
            errors.append(f"root.{key} must be {expected!r}")

    status = config.get("status")
    if status not in {"proposed", "frozen"}:
        errors.append("root.status must be proposed or frozen")
    frozen = status == "frozen"
    expected_rule = (
        "k-query202-ndc-evidence-mode-v1-frozen"
        if frozen
        else "k-query202-ndc-evidence-mode-v1-proposed"
    )
    if config.get("rule_version") != expected_rule:
        errors.append(f"root.rule_version must be {expected_rule!r}")

    _validate_exact_mapping(config.get("source"), EXPECTED_SOURCE, "source", errors)

    expected_decision = {
        "mode": EXPECTED_DECISION_STATIC["mode"],
        "lifecycle_state": "frozen" if frozen else "proposed",
        "effective": frozen,
        **{key: value for key, value in EXPECTED_DECISION_STATIC.items() if key != "mode"},
    }
    _validate_exact_mapping(
        config.get("decision"), expected_decision, "decision", errors
    )
    _validate_exact_mapping(
        config.get("evidence_boundary"),
        EXPECTED_EVIDENCE_BOUNDARY,
        "evidence_boundary",
        errors,
    )
    _validate_exact_mapping(
        config.get("change_control"),
        EXPECTED_CHANGE_CONTROL,
        "change_control",
        errors,
    )
    _validate_exact_mapping(
        config.get("downstream_contract"),
        EXPECTED_DOWNSTREAM_CONTRACT,
        "downstream_contract",
        errors,
    )

    expected_guards = {"ndc_mode_frozen": frozen, **EXPECTED_FALSE_GUARDS}
    _validate_exact_mapping(config.get("guards"), expected_guards, "guards", errors)

    implementation = config.get("implementation")
    if not isinstance(implementation, Mapping):
        errors.append("implementation must be a table")
    else:
        expected_keys = {
            "bundle_encoding",
            "validator_paths",
            "validator_bundle_sha256",
        }
        missing = sorted(expected_keys - set(implementation))
        unexpected = sorted(set(implementation) - expected_keys)
        if missing or unexpected:
            errors.append(
                "implementation keys changed: "
                f"missing={missing!r}, unexpected={unexpected!r}"
            )
        if not _strict_equal(
            implementation.get("bundle_encoding"), BUNDLE_ENCODING
        ):
            errors.append("implementation.bundle_encoding changed")
        if not _strict_equal(
            implementation.get("validator_paths"), list(EXPECTED_VALIDATOR_PATHS)
        ):
            errors.append("implementation.validator_paths changed")
        configured_hash = implementation.get("validator_bundle_sha256")
        if frozen:
            if not (
                isinstance(configured_hash, str)
                and len(configured_hash) == 64
                and all(character in "0123456789abcdef" for character in configured_hash)
            ):
                errors.append("implementation.validator_bundle_sha256 not frozen")
        elif configured_hash != PLACEHOLDER:
            errors.append(
                "implementation.validator_bundle_sha256 must be the proposal placeholder"
            )
    return errors


def _implementation_bundle_snapshot(
    root: Path,
    paths: Sequence[str],
) -> tuple[str, dict[str, tuple[str, dict[str, Any]]]]:
    digest = hashlib.sha256()
    snapshots: dict[str, tuple[str, dict[str, Any]]] = {}
    for relative in paths:
        snapshot = _snapshot_regular_file(root, relative, retain_payload=True)
        payload = snapshot["payload"]
        if not isinstance(payload, bytes):
            raise OSError("implementation snapshot unavailable")
        encoded_path = relative.encode("utf-8")
        digest.update(struct.pack(">I", len(encoded_path)))
        digest.update(encoded_path)
        digest.update(struct.pack(">Q", len(payload)))
        digest.update(payload)
        snapshots[f"bundle:{relative}"] = (relative, snapshot)
    return digest.hexdigest(), snapshots


def implementation_bundle_sha256(root: Path, paths: Sequence[str]) -> str:
    digest, _snapshots = _implementation_bundle_snapshot(root, paths)
    return digest


def _check_equal(
    checks: dict[str, bool],
    errors: list[str],
    label: str,
    actual: object,
    expected: object,
) -> None:
    passed = _strict_equal(actual, expected)
    checks[label] = passed
    if not passed:
        errors.append(f"source evidence {label} mismatch")


def _git_ignored(root: Path, relative: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", relative],
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
    )
    return result.returncode == 0


def _verify_source_evidence(
    root: Path,
    errors: list[str],
) -> tuple[
    dict[str, bool],
    dict[str, tuple[str, dict[str, Any]]],
    dict[str, Any] | None,
]:
    checks: dict[str, bool] = {}
    source = EXPECTED_SOURCE
    artifact_relative = source["artifact_directory"]
    try:
        directory_snapshot = _directory_seal(root, artifact_relative)
        directory_ok = directory_snapshot["mode"] == 0o700
    except (OSError, ValueError):
        directory_snapshot = None
        directory_ok = False
    checks["artifact_directory_private_mode"] = directory_ok
    if not directory_ok:
        errors.append("source evidence artifact directory check failed")

    snapshots: dict[str, dict[str, Any]] = {}
    closure_snapshots: dict[str, tuple[str, dict[str, Any]]] = {}
    file_specs = {
        "source_config": (
            source["config_file"],
            source["config_sha256"],
            None,
            True,
        ),
        "manifest": (
            str(Path(str(artifact_relative)) / str(source["manifest_file"])),
            source["manifest_sha256"],
            0o600,
            True,
        ),
        "aggregate_summary": (
            str(
                Path(str(artifact_relative))
                / str(source["aggregate_summary_file"])
            ),
            source["aggregate_summary_sha256"],
            0o600,
            True,
        ),
        "audit": (
            str(Path(str(artifact_relative)) / str(source["audit_file"])),
            source["audit_sha256"],
            0o600,
            True,
        ),
        "ndc_handoff": (
            str(
                Path(str(artifact_relative))
                / str(EXPECTED_NDC_HANDOFF["file"])
            ),
            EXPECTED_NDC_HANDOFF["stored_sha256"],
            0o600,
            False,
        ),
    }
    for label, (relative, expected_hash, expected_mode, retain) in file_specs.items():
        try:
            snapshot = _snapshot_regular_file(
                root, relative, retain_payload=bool(retain)
            )
            snapshots[label] = snapshot
            closure_snapshots[f"source:{label}"] = (str(relative), snapshot)
            matches = snapshot["sha256"] == expected_hash
            if expected_mode is not None:
                matches = matches and snapshot["mode"] == expected_mode
            if label == "ndc_handoff":
                matches = matches and snapshot["bytes"] == EXPECTED_NDC_HANDOFF["stored_bytes"]
        except (OSError, ValueError):
            matches = False
        checks[f"{label}_whole_file"] = matches
        if not matches:
            errors.append(f"source evidence {label} whole-file check failed")

    public_documents: dict[str, Any] = {}
    for label in ("manifest", "aggregate_summary", "audit"):
        try:
            payload = snapshots[label]["payload"]
            if not isinstance(payload, bytes):
                raise ValueError("missing public payload")
            document = _strict_json(payload)
            if not isinstance(document, Mapping):
                raise ValueError("public document is not an object")
            public_documents[label] = document
            ok = True
        except (KeyError, TypeError, UnicodeDecodeError, ValueError):
            ok = False
        checks[f"{label}_strict_json"] = ok
        if not ok:
            errors.append(f"source evidence {label} public JSON check failed")

    try:
        source_payload = snapshots["source_config"]["payload"]
        if not isinstance(source_payload, bytes):
            raise ValueError("missing source configuration payload")
        source_config = tomllib.loads(source_payload.decode("utf-8"))
        source_config_ok = (
            source_config.get("component_id") == SOURCE_COMPONENT_ID
            and source_config.get("status") == source["source_status_at_execution_required"]
            and source_config.get("ndc_mode", {}).get("mode_at_compilation") == "pending"
            and source_config.get("ndc_mode", {}).get("external_api_called") is False
            and source_config.get("ndc_mode", {}).get("mapping_establishes_product_identity") is False
            and source_config.get("output", {}).get("ndc_file") == EXPECTED_NDC_HANDOFF["file"]
            and source_config.get("output", {}).get("encoding") == EXPECTED_NDC_HANDOFF["encoding"]
        )
    except (KeyError, TypeError, UnicodeDecodeError, tomllib.TOMLDecodeError, ValueError):
        source_config_ok = False
    checks["source_config_contract"] = source_config_ok
    if not source_config_ok:
        errors.append("source evidence source configuration contract mismatch")

    ndc_public = {
        "file": EXPECTED_NDC_HANDOFF["file"],
        "encoding": EXPECTED_NDC_HANDOFF["encoding"],
        "sha256": EXPECTED_NDC_HANDOFF["stored_sha256"],
        "bytes": EXPECTED_NDC_HANDOFF["stored_bytes"],
        "raw_sha256": EXPECTED_NDC_HANDOFF["raw_sha256"],
        "raw_bytes": EXPECTED_NDC_HANDOFF["raw_bytes"],
        "records": EXPECTED_NDC_HANDOFF["records"],
    }
    if len(public_documents) == 3:
        manifest = public_documents["manifest"]
        summary = public_documents["aggregate_summary"]
        audit = public_documents["audit"]
        _check_equal(
            checks,
            errors,
            "manifest_component",
            (manifest.get("component_id"), manifest.get("status")),
            (SOURCE_COMPONENT_ID, source["component_status_required"]),
        )
        _check_equal(
            checks,
            errors,
            "manifest_artifact_directory",
            manifest.get("artifact_directory"),
            artifact_relative,
        )
        _check_equal(
            checks,
            errors,
            "manifest_ndc_metadata",
            manifest.get("outputs", {}).get("ndc_handoff"),
            ndc_public,
        )
        _check_equal(
            checks,
            errors,
            "summary_component",
            (summary.get("component_id"), summary.get("status")),
            (SOURCE_COMPONENT_ID, source["component_status_required"]),
        )
        _check_equal(
            checks,
            errors,
            "summary_ndc_metadata",
            summary.get("output_hashes", {}).get("ndc_handoff"),
            ndc_public,
        )
        _check_equal(
            checks,
            errors,
            "audit_component",
            (audit.get("component_id"), audit.get("status")),
            (SOURCE_COMPONENT_ID, source["audit_status_required"]),
        )
        _check_equal(
            checks,
            errors,
            "audit_failed_checks",
            audit.get("checks", {}).get("failed"),
            source["audit_failed_checks_required"],
        )
        _check_equal(
            checks,
            errors,
            "audit_ndc_metadata",
            audit.get("recomputed", {}).get("output_hashes", {}).get("ndc_handoff"),
            ndc_public,
        )
        _check_equal(
            checks,
            errors,
            "audit_public_lineage_hashes",
            (
                audit.get("recomputed", {}).get("manifest_sha256"),
                audit.get("recomputed", {}).get("aggregate_summary_sha256"),
            ),
            (source["manifest_sha256"], source["aggregate_summary_sha256"]),
        )
        lineage = manifest.get("component_lineage", {})
        _check_equal(
            checks,
            errors,
            "manifest_source_config_lineage",
            (
                lineage.get("component_id"),
                lineage.get("config"),
                lineage.get("config_sha256"),
                lineage.get("status_at_execution"),
            ),
            (
                SOURCE_COMPONENT_ID,
                source["config_file"],
                source["config_sha256"],
                source["source_status_at_execution_required"],
            ),
        )
        source_guard_subset = manifest.get("guards", {})
        _check_equal(
            checks,
            errors,
            "source_nonmapping_guards",
            (
                source_guard_subset.get("ndc_mode_frozen"),
                source_guard_subset.get("external_ndc_mapping_executed"),
                source_guard_subset.get("product_identity_decided"),
            ),
            (False, False, False),
        )
        _check_equal(
            checks,
            errors,
            "source_public_privacy",
            (
                manifest.get("privacy", {}).get("external_api_called"),
                manifest.get("privacy", {}).get("public_raw_values_emitted"),
                audit.get("external_api_called"),
                audit.get("raw_values_emitted"),
                audit.get("database_connection_opened"),
            ),
            (False, False, False, False, False),
        )

    try:
        ignored = _git_ignored(
            root,
            str(
                Path(str(artifact_relative))
                / str(EXPECTED_NDC_HANDOFF["file"])
            ),
        )
    except (OSError, subprocess.SubprocessError):
        ignored = False
    checks["ndc_handoff_git_ignored"] = ignored
    if not ignored:
        errors.append("source evidence NDC handoff is not Git ignored")

    return checks, closure_snapshots, directory_snapshot


def _verify_snapshot_closure(
    root: Path,
    initial_snapshots: Mapping[str, tuple[str, Mapping[str, Any]]],
    initial_artifact_directory: Mapping[str, Any] | None,
    errors: list[str],
) -> dict[str, bool]:
    """Re-hash every dependency after all first-pass validation is complete."""
    checks: dict[str, bool] = {}
    for label, (relative, initial) in initial_snapshots.items():
        try:
            final = _snapshot_regular_file(
                root, relative, retain_payload=False
            )
            stable = _snapshot_seal(final) == _snapshot_seal(initial)
        except (OSError, ValueError):
            stable = False
        checks[f"{label}:stable"] = stable
        if not stable:
            errors.append(f"snapshot closure {label} changed")

    try:
        final_directory = _directory_seal(
            root, EXPECTED_SOURCE["artifact_directory"]
        )
        directory_stable = (
            initial_artifact_directory is not None
            and _strict_equal(final_directory, initial_artifact_directory)
            and final_directory.get("mode") == 0o700
        )
    except (OSError, ValueError):
        directory_stable = False
    checks["source:artifact_directory:stable"] = directory_stable
    if not directory_stable:
        errors.append("snapshot closure source artifact directory changed")
    return checks


def query202_ndc_evidence_mode_preregistration_report(root: Path) -> dict[str, Any]:
    config, config_sha256, config_snapshot = _read_config_snapshot(root)
    errors = validate_query202_ndc_evidence_mode_preregistration(config)
    source_checks, source_snapshots, artifact_directory_snapshot = (
        _verify_source_evidence(root, errors)
    )

    actual_bundle: str | None = None
    bundle_snapshots: dict[str, tuple[str, dict[str, Any]]] = {}
    try:
        actual_bundle, bundle_snapshots = _implementation_bundle_snapshot(
            root, EXPECTED_VALIDATOR_PATHS
        )
    except OSError:
        errors.append("validator implementation bundle could not be read safely")
    implementation = config.get("implementation", {})
    configured_bundle = (
        implementation.get("validator_bundle_sha256")
        if isinstance(implementation, Mapping)
        else None
    )
    status = config.get("status")
    bundle_verified = actual_bundle is not None
    if status == "frozen":
        bundle_verified = bundle_verified and actual_bundle == configured_bundle
        if not bundle_verified:
            errors.append("validator implementation bundle hash mismatch")

    initial_snapshots: dict[str, tuple[str, Mapping[str, Any]]] = {
        "decision_config": (str(CONFIG_PATH), config_snapshot),
        **source_snapshots,
        **bundle_snapshots,
    }
    snapshot_closure_checks = _verify_snapshot_closure(
        root,
        initial_snapshots,
        artifact_directory_snapshot,
        errors,
    )
    snapshot_closure_verified = (
        len(initial_snapshots) == 9
        and len(snapshot_closure_checks) == 10
        and all(snapshot_closure_checks.values())
    )
    if not snapshot_closure_verified and not any(
        error.startswith("snapshot closure") for error in errors
    ):
        errors.append("snapshot closure inventory incomplete")

    source_verified = bool(source_checks) and all(source_checks.values())
    valid = (
        not errors
        and source_verified
        and bundle_verified
        and snapshot_closure_verified
    )
    effective = valid and status == "frozen"
    return {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "status": status,
        "execution_status": config.get("execution_status"),
        "execution_permitted": config.get("execution_permitted"),
        "valid": valid,
        "freeze_ready": valid,
        "decision_mode": config.get("decision", {}).get("mode")
        if isinstance(config.get("decision"), Mapping)
        else None,
        "decision_effective": effective,
        "ndc_used_in_current_semantic_adjudication": False,
        "source_evidence_verified": source_verified,
        "source_checks": source_checks,
        "snapshot_closure_verified": snapshot_closure_verified,
        "snapshot_closure_checks": snapshot_closure_checks,
        "input_lineage": {
            "artifact_directory": EXPECTED_SOURCE["artifact_directory"],
            "manifest_sha256": EXPECTED_SOURCE["manifest_sha256"],
            "aggregate_summary_sha256": EXPECTED_SOURCE["aggregate_summary_sha256"],
            "audit_sha256": EXPECTED_SOURCE["audit_sha256"],
            "source_config_sha256": EXPECTED_SOURCE["config_sha256"],
            "ndc_handoff_stored_sha256": EXPECTED_NDC_HANDOFF["stored_sha256"],
            "ndc_handoff_stored_bytes": EXPECTED_NDC_HANDOFF["stored_bytes"],
            "ndc_handoff_raw_sha256": EXPECTED_NDC_HANDOFF["raw_sha256"],
            "ndc_handoff_raw_bytes": EXPECTED_NDC_HANDOFF["raw_bytes"],
            "ndc_handoff_records": EXPECTED_NDC_HANDOFF["records"],
        },
        "implementation": {
            "bundle_encoding": BUNDLE_ENCODING,
            "validator_paths": list(EXPECTED_VALIDATOR_PATHS),
            "configured_bundle_sha256": configured_bundle,
            "actual_bundle_sha256": actual_bundle,
            "bundle_verified": bundle_verified,
        },
        "privacy": {
            "private_handoff_rows_decompressed": False,
            "private_handoff_rows_parsed": False,
            "private_handoff_rows_printed": False,
            "external_api_called": False,
            "database_connected": False,
            "network_accessed": False,
        },
        "guards": dict(config.get("guards", {}))
        if isinstance(config.get("guards"), Mapping)
        else {},
        "config": str(CONFIG_PATH),
        "config_sha256": config_sha256,
        "errors": errors,
    }


__all__ = [
    "BUNDLE_ENCODING",
    "COMPONENT_ID",
    "CONFIG_PATH",
    "EXPECTED_NDC_HANDOFF",
    "EXPECTED_SOURCE",
    "EXPECTED_VALIDATOR_PATHS",
    "NdcEvidenceModeError",
    "implementation_bundle_sha256",
    "query202_ndc_evidence_mode_preregistration_report",
    "read_query202_ndc_evidence_mode_preregistration",
    "validate_query202_ndc_evidence_mode_preregistration",
]
