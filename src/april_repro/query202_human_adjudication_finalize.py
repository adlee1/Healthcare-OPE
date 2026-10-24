"""Compile and separately freeze the Query-202 human adjudication artifact.

The compiler consumes only a formal workspace which the workspace validator
reports as ``human_review_complete_unfrozen``.  It emits a private, immutable
projection of the active human decisions.  The later freeze operation accepts
only an audit made by the independently bundled final-artifact auditor and
adds one file; it never edits an output that was audited.

This module is part of the generator lineage.  It may use the workspace
validator, but the independent auditor must not import this module or the
workspace generator/validator.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import ast
import ctypes
import errno
import gzip
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import struct
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence
import zlib

from . import query202_human_adjudication as workspace_api
from . import query202_human_adjudication_preregistration as prereg_api


CONFIG_PATH = workspace_api.CONFIG_PATH
COMPONENT_ID = workspace_api.COMPONENT_ID
FINAL_ARTIFACT_PARENT = Path("artifacts/query202-human-adjudication")
PLACEHOLDER = workspace_api.PLACEHOLDER

SEMANTIC_SCHEMA = "query202-reviewed-semantic-ledger-v1"
SEMANTIC_HASH_VERSION = "query202-semantic-decisions-v1"
GROUP_SCHEMA = "query202-semantic-mapping-groups-v1"
GROUP_HASH_VERSION = "query202-semantic-mapping-groups-v1"
ROUTE_SCHEMA = "query202-source-specific-exact-route-mapping-v1"
ROUTE_HASH_VERSION = "query202-source-specific-exact-route-mapping-v1"
ATTESTATION_SCHEMA = "query202-human-attestations-v1"
EVIDENCE_SCHEMA = "query202-evidence-registry-v1"
MANIFEST_SCHEMA = "query202-human-adjudication-final-manifest-v1"
AGGREGATE_SUMMARY_SCHEMA = "query202-human-adjudication-aggregate-summary-v1"
AUDIT_SCHEMA = "query202-human-adjudication-final-artifact-audit-v1"
AUDITOR_COMPONENT_ID = "D005-K-QUERY202-HUMAN-ADJUDICATION-FINAL-AUDITOR-v1"
AUDIT_METHOD = "independent-reimplementation-without-generator-imports-v1"
FREEZE_SCHEMA = "query202-human-adjudication-freeze-manifest-v1"
WORKSPACE_SNAPSHOT_HASH_VERSION = "query202-human-workspace-file-snapshot-v1"
DOCUMENT_SET_HASH_VERSION = "query202-human-versioned-document-set-v1"
GZIP_ENCODING = "gzip+utf8+ndjson-single-member-mtime0-v1"

PRE_AUDIT_OUTPUTS = (
    "reviewed-semantic-ledger.jsonl.gz",
    "semantic-mapping-groups.jsonl.gz",
    "source-specific-route-mapping.jsonl.gz",
    "human-attestations.jsonl.gz",
    "evidence-registry.jsonl.gz",
    "manifest.json",
    "aggregate-summary.json",
)
GZIP_OUTPUTS = PRE_AUDIT_OUTPUTS[:5]
AUDIT_FILE = "audit-summary.json"
FREEZE_FILE = "freeze-manifest.json"
POST_AUDIT_OUTPUTS = (*PRE_AUDIT_OUTPUTS, AUDIT_FILE)
POST_FREEZE_OUTPUTS = (*POST_AUDIT_OUTPUTS, FREEZE_FILE)

# These paths must be incorporated in implementation.generator_paths before a
# formal configuration is frozen.  Keeping the check here prevents an
# unbound compiler or freezer from creating a formal artifact.
FINALIZER_REQUIRED_GENERATOR_PATHS = (
    "src/april_repro/query202_human_adjudication_finalize.py",
    "scripts/compile_potassium_query202_human_adjudication.py",
    "scripts/freeze_potassium_query202_human_adjudication.py",
)
EXPECTED_AUDITOR_PATHS = (
    "src/april_repro/__init__.py",
    "src/april_repro/query202_human_adjudication_audit.py",
    "scripts/audit_potassium_query202_human_adjudication.py",
)
DOWNSTREAM_GUARDS = (
    "product_mapping_accepted",
    "event_mapping_created",
    "final_source_policy",
    "complete_intervention_coverage",
    "formal_action",
    "formal_episode",
    "zero_action_constructed",
    "formal_non_icu_rule",
    "formal_label",
    "formal_cohort",
    "patient_data_exported",
    "llm_called",
)

MAX_JSON_BYTES = 256 * 1024 * 1024
FailureHook = Callable[[str], None]


class HumanAdjudicationFinalizeError(RuntimeError):
    """Fail-closed compilation, audit-binding, or freeze error."""


def _fail(message: str) -> None:
    raise HumanAdjudicationFinalizeError(message)


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        _fail("A final-artifact record is not canonical JSON.")


def _pretty_json(value: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError):
        _fail("A final-artifact document is not strict JSON.")


def _strict_json(raw: bytes, label: str) -> Mapping[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(f"{label} contains a duplicate JSON key.")
            result[key] = value
        return result

    def reject(_: str) -> None:
        _fail(f"{label} contains a non-finite JSON value.")

    if not 0 < len(raw) <= MAX_JSON_BYTES:
        _fail(f"{label} has an invalid byte size.")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique,
            parse_constant=reject,
        )
    except HumanAdjudicationFinalizeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail(f"{label} is not strict UTF-8 JSON.")
    if not isinstance(value, Mapping):
        _fail(f"{label} is not one JSON object.")
    return value


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _require_utc(value: str | None, label: str) -> str:
    candidate = value or _now_utc()
    if not workspace_api._strict_utc(candidate):
        _fail(f"{label} is not a strict UTC timestamp.")
    return candidate


def _timestamp_directory(value: str) -> str:
    if not workspace_api._strict_utc(value):
        _fail("The artifact directory time is not strict UTC.")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    return parsed.strftime("%Y%m%dT%H%M%S.%fZ")


def _valid_artifact_leaf(value: str) -> bool:
    try:
        parsed = datetime.strptime(value, "%Y%m%dT%H%M%S.%fZ")
    except (TypeError, ValueError):
        return False
    return parsed.strftime("%Y%m%dT%H%M%S.%fZ") == value


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _record_hash(record: Mapping[str, Any]) -> str:
    return _sha(_canonical_json(record))


def _sequence_hash(version: str, records: Sequence[Mapping[str, Any]]) -> str:
    domain = version.encode("utf-8")
    digest = hashlib.sha256()
    digest.update(struct.pack(">I", len(domain)))
    digest.update(domain)
    digest.update(struct.pack(">Q", len(records)))
    for record in records:
        encoded = _canonical_json(record)
        digest.update(struct.pack(">Q", len(encoded)))
        digest.update(encoded)
    return digest.hexdigest()


def _ndjson(records: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(_canonical_json(record) + b"\n" for record in records)


def _single_member_gzip(raw: bytes) -> bytes:
    # Fixed header (mtime=0, no filename/comment) plus one raw-DEFLATE stream.
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    body = compressor.compress(raw) + compressor.flush()
    header = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff"
    trailer = struct.pack("<II", zlib.crc32(raw) & 0xFFFFFFFF, len(raw) & 0xFFFFFFFF)
    return header + body + trailer


def _verify_single_member_gzip(stored: bytes, raw: bytes, label: str) -> None:
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        decoded = inflater.decompress(stored) + inflater.flush()
    except zlib.error:
        _fail(f"{label} is not a valid gzip stream.")
    if (
        decoded != raw
        or not inflater.eof
        or inflater.unused_data
        or inflater.unconsumed_tail
    ):
        _fail(f"{label} is not exactly one closed gzip member.")


def _write_private(path: Path, payload: bytes) -> dict[str, Any]:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail("A private output write made no progress.")
            view = view[written:]
        os.fsync(descriptor)
        info = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        _fail("A final-artifact file does not have mode 0600 and link count 1.")
    return {"sha256": _sha(payload), "bytes": len(payload)}


def _write_private_at(
    directory_descriptor: int, name: str, payload: bytes
) -> dict[str, Any]:
    if Path(name).name != name or not name:
        _fail("A private output filename is unsafe.")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=directory_descriptor)
        os.fchmod(descriptor, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail("A private output write made no progress.")
            view = view[written:]
        os.fsync(descriptor)
        info = os.fstat(descriptor)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        _fail("A private output does not have mode 0600 and link count 1.")
    return {"sha256": _sha(payload), "bytes": len(payload)}


def _write_gzip(
    path: Path, records: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    raw = _ndjson(records)
    stored = _single_member_gzip(raw)
    _verify_single_member_gzip(stored, raw, path.name)
    result = _write_private(path, stored)
    return {
        **result,
        "raw_sha256": _sha(raw),
        "raw_bytes": len(raw),
        "records": len(records),
        "encoding": GZIP_ENCODING,
    }


def _write_gzip_at(
    directory_descriptor: int,
    name: str,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    raw = _ndjson(records)
    stored = _single_member_gzip(raw)
    _verify_single_member_gzip(stored, raw, name)
    result = _write_private_at(directory_descriptor, name, stored)
    return {
        **result,
        "raw_sha256": _sha(raw),
        "raw_bytes": len(raw),
        "records": len(records),
        "encoding": GZIP_ENCODING,
    }


def _snapshot_regular_at(
    directory_descriptor: int, name: str
) -> dict[str, Any]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    digest = hashlib.sha256()
    total = 0
    try:
        initial = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
        if not stat.S_ISREG(initial.st_mode):
            _fail("An anchored private output is not a regular file.")
        descriptor = os.open(name, flags, dir_fd=directory_descriptor)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or (before.st_dev, before.st_ino)
            != (initial.st_dev, initial.st_ino)
        ):
            _fail("An anchored private output changed before it was read.")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
        after = os.fstat(descriptor)
        if not workspace_api._same_open_snapshot(before, after):
            _fail("An anchored private output changed while it was read.")
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return {
        "identity": (after.st_dev, after.st_ino),
        "mode": stat.S_IMODE(after.st_mode),
        "nlink": after.st_nlink,
        "bytes": total,
        "sha256": digest.hexdigest(),
    }


def _new_private_directory_at(parent_descriptor: int, prefix: str) -> tuple[str, int]:
    for _ in range(128):
        name = prefix + secrets.token_hex(12)
        try:
            os.mkdir(name, 0o700, dir_fd=parent_descriptor)
        except FileExistsError:
            continue
        descriptor = os.open(name, workspace_api.DIRECTORY_OPEN_FLAGS, dir_fd=parent_descriptor)
        os.fchmod(descriptor, 0o700)
        return name, descriptor
    _fail("A collision-free private temporary directory could not be created.")


def _remove_tree_if_identity_at(
    parent_descriptor: int,
    name: str,
    expected_identity: tuple[int, int],
) -> None:
    """Remove only the controlled tree; preserve any raced-in replacement."""
    try:
        current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (current.st_dev, current.st_ino) != expected_identity:
        return
    workspace_api._remove_tree_at(parent_descriptor, name)


def _unlink_if_identity_at(
    parent_descriptor: int,
    name: str,
    expected_identity: tuple[int, int],
) -> None:
    try:
        current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (current.st_dev, current.st_ino) == expected_identity:
        os.unlink(name, dir_fd=parent_descriptor)


def _rename_directory_noreplace(
    source_parent_descriptor: int,
    source_name: str,
    destination_parent_descriptor: int,
    destination_name: str,
) -> None:
    """Atomically rename without ever replacing an existing destination."""
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if sys.platform == "darwin":
        function = getattr(library, "renameatx_np", None)
        flag = 0x00000004  # RENAME_EXCL
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
        flag = 0x00000001  # RENAME_NOREPLACE
    else:
        function = None
        flag = 0
    if function is None:
        _fail("This platform lacks an atomic no-replace directory rename.")
    function.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    function.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = function(
        source_parent_descriptor,
        source,
        destination_parent_descriptor,
        destination,
        flag,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        _fail("The final-artifact destination appeared before publication.")
    _fail("Atomic no-replace final-artifact publication failed.")


def _call_hook(hook: FailureHook | None, point: str) -> None:
    if hook is not None:
        hook(point)


def _assert_independent_auditor_imports(bundle: Mapping[str, Any]) -> None:
    snapshots = bundle.get("_snapshots")
    if not isinstance(snapshots, Mapping):
        _fail("The independent-auditor bundle payloads are unavailable.")
    banned_parts = {
        "query202_human_adjudication",
        "query202_human_adjudication_finalize",
    }

    def names_generator_helper(name: str) -> bool:
        return bool(banned_parts.intersection(name.split(".")))

    for relative, snapshot in snapshots.items():
        if not isinstance(relative, str) or Path(relative).suffix != ".py":
            continue
        payload = snapshot.get("payload") if isinstance(snapshot, Mapping) else None
        if not isinstance(payload, bytes):
            _fail("An independent-auditor Python payload is unavailable.")
        try:
            tree = ast.parse(payload.decode("utf-8"), filename=relative)
        except (UnicodeDecodeError, SyntaxError):
            _fail("An independent-auditor Python file is not parseable.")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                names_generator_helper(alias.name) for alias in node.names
            ):
                _fail("The independent-auditor bundle imports a generator helper.")
            if isinstance(node, ast.ImportFrom) and (
                names_generator_helper(node.module or "")
                or any(names_generator_helper(alias.name) for alias in node.names)
            ):
                _fail("The independent-auditor bundle imports a generator helper.")


def _load_contract(root: Path, config_path: Path) -> dict[str, Any]:
    try:
        contract = workspace_api._load_contract(
            root, config_path, allow_proposed=False
        )
    except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
        raise HumanAdjudicationFinalizeError(
            "The formal human-adjudication contract is not executable."
        ) from error
    try:
        workspace_api._require_formal_preregistration_ready(root, contract)
    except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
        raise HumanAdjudicationFinalizeError(
            "The formal preregistration and synthetic-test attestation are not ready."
        ) from error
    config = contract["config"]
    final = config.get("final_outputs")
    if not isinstance(final, Mapping):
        _fail("The final-output contract is absent.")
    expected = {
        "component_id": COMPONENT_ID,
        "artifact_parent": FINAL_ARTIFACT_PARENT.as_posix(),
        "artifact_directory_naming": "strict-utc-basic-with-fraction-v1",
        "private_directory_mode": "0700",
        "private_file_mode": "0600",
        "strict_inventory": list(PRE_AUDIT_OUTPUTS),
        "strict_inventory_after_audit": list(POST_AUDIT_OUTPUTS),
        "strict_inventory_after_freeze": list(POST_FREEZE_OUTPUTS),
        "independent_audit_adds_only": AUDIT_FILE,
        "separate_freeze_adds_only": FREEZE_FILE,
        "gzip_encoding": GZIP_ENCODING,
        "semantic_ledger_schema": SEMANTIC_SCHEMA,
        "semantic_decision_hash_version": SEMANTIC_HASH_VERSION,
        "mapping_group_schema": GROUP_SCHEMA,
        "mapping_group_hash_version": GROUP_HASH_VERSION,
        "route_mapping_schema": ROUTE_SCHEMA,
        "route_mapping_hash_version": ROUTE_HASH_VERSION,
        "attestation_schema": ATTESTATION_SCHEMA,
        "attestation_hash_version": ATTESTATION_SCHEMA,
        "evidence_registry_schema": EVIDENCE_SCHEMA,
        "evidence_registry_hash_version": EVIDENCE_SCHEMA,
        "manifest_schema": MANIFEST_SCHEMA,
        "aggregate_summary_schema": AGGREGATE_SUMMARY_SCHEMA,
        "audit_schema": AUDIT_SCHEMA,
        "audit_method": AUDIT_METHOD,
        "auditor_component_id": AUDITOR_COMPONENT_ID,
        "freeze_schema": FREEZE_SCHEMA,
        "workspace_snapshot_hash_version": WORKSPACE_SNAPSHOT_HASH_VERSION,
        "registered_document_set_hash_version": DOCUMENT_SET_HASH_VERSION,
        "retained_versioned_documents_location": "formal_workspace",
        "final_artifact_self_contained": False,
        "independent_audit_must_reopen_retained_documents": True,
        "freeze_must_reopen_retained_documents": True,
        "manifest_status_before_freeze": "human_review_complete_unfrozen",
        "audit_status_required_before_freeze": "passed",
        "audit_checks_total": 18,
        "freeze_manifest_status": "frozen",
    }
    for key, value in expected.items():
        if (
            key == "audit_checks_total"
            and type(final.get(key)) is not int
        ) or final.get(key) != value:
            _fail(f"final_outputs.{key} changed.")
    if (
        final.get("route_mapping_total_typed_memberships")
        != config["source_artifact"]["route_template"][
            "source_specific_typed_memberships"
        ]
        or final.get("final_artifact_review_complete_guards_true")
        != ["semantic_review_complete", "route_review_complete"]
        or final.get("final_freeze_guards_true")
        != ["reviewed_semantic_ledger_frozen", "route_mapping_frozen"]
        or final.get("downstream_scientific_guards_remain_false")
        != list(DOWNSTREAM_GUARDS)
    ):
        _fail("The final-output cardinality or guard contract changed.")
    for key in (
        "semantic_ledger_includes_exact_source_field_and_raw_value",
        "semantic_key_set_must_equal_source",
        "semantic_active_revision_projection_required",
        "route_mapping_expands_canonical_to_233_nonnull_memberships",
        "route_mapping_adds_3_sql_null_missing_memberships",
        "route_mapping_preserves_source_key_field_role_frequency_and_provenance",
        "freeze_manifest_binds_all_private_whole_file_hashes",
        "freeze_manifest_binds_semantic_and_route_decision_hashes",
        "freeze_manifest_binds_source_ndc_config_generator_auditor_and_audit_hashes",
    ):
        if final.get(key) is not True:
            _fail(f"final_outputs.{key} is not enabled.")
    implementation = config.get("implementation")
    if not isinstance(implementation, Mapping):
        _fail("The implementation lineage is absent.")
    generator_paths = implementation.get("generator_paths")
    if not isinstance(generator_paths, list) or not set(
        FINALIZER_REQUIRED_GENERATOR_PATHS
    ).issubset(generator_paths):
        _fail("The compiler and freezer are absent from the generator bundle.")
    auditor_paths = implementation.get("auditor_paths")
    if auditor_paths != list(EXPECTED_AUDITOR_PATHS):
        _fail("The independent-auditor bundle is absent.")
    try:
        auditor_bundle = workspace_api._bundle(root, tuple(auditor_paths))
    except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
        raise HumanAdjudicationFinalizeError(
            "The independent-auditor bundle cannot be snapshotted."
        ) from error
    configured_auditor = implementation.get("auditor_bundle_sha256")
    if (
        configured_auditor == PLACEHOLDER
        or configured_auditor != auditor_bundle["bundle_sha256"]
    ):
        _fail("The independent-auditor bundle hash is not frozen or changed.")
    _assert_independent_auditor_imports(auditor_bundle)
    test_gate_closure = _snapshot_test_gate_closure(root, contract)
    # The first readiness report validates the formal contract before the
    # finalizer reads it.  Re-run the independent semantic verifier after the
    # descriptor baseline exists, then immediately prove that the exact
    # attestation, execution files, and runtime locator/target it verified are
    # still the captured baseline.  This closes the report-to-snapshot gap.
    try:
        workspace_api._require_formal_preregistration_ready(root, contract)
        _finish_test_gate_closure(root, test_gate_closure)
    except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
        raise HumanAdjudicationFinalizeError(
            "The snapshotted preregistration test gate failed semantic revalidation."
        ) from error
    return {
        **contract,
        "auditor_bundle": auditor_bundle,
        "test_gate_closure": test_gate_closure,
    }


def _finish_auditor_closure(root: Path, bundle: Mapping[str, Any]) -> None:
    for relative, initial in bundle["_snapshots"].items():
        try:
            final = workspace_api._snapshot_file(
                workspace_api._project_path(root, relative, "auditor implementation"),
                "An independent-auditor implementation file",
            )
        except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
            raise HumanAdjudicationFinalizeError(
                "The independent-auditor bundle changed during the operation."
            ) from error
        if workspace_api._seal(final) != workspace_api._seal(initial):
            _fail("The independent-auditor bundle changed during the operation.")


def _snapshot_test_gate_closure(
    root: Path, contract: Mapping[str, Any]
) -> dict[str, Any]:
    """Independently retain descriptor snapshots of the attested execution closure.

    The preregistration report establishes the attestation semantics.  These
    snapshots keep the attestation, every project execution dependency, and
    the resolved interpreter stable until compile/freeze publication.  The
    interpreter may be installed outside the project and may have multiple
    hard links, so only project files receive the nlink==1 policy.
    """
    gate = contract["config"].get("test_attestation")
    if (
        not isinstance(gate, Mapping)
        or gate.get("status") != "passed"
        or gate.get("attestation_path") != prereg_api.TEST_ATTESTATION_PATH
        or gate.get("test_execution_paths")
        != list(prereg_api.TEST_EXECUTION_PATHS)
        or gate.get("python_runtime_path") != prereg_api.TEST_COMMAND_ARGV[0]
    ):
        _fail("The formal synthetic-test execution closure is not exact.")

    project_files: dict[str, dict[str, Any]] = {}
    attestation_path = workspace_api._project_path(
        root, prereg_api.TEST_ATTESTATION_PATH, "synthetic-test attestation"
    )
    attestation = workspace_api._snapshot_file(
        attestation_path, "The synthetic-test attestation"
    )
    if (
        attestation["mode"] != 0o644
        or attestation["nlink"] != 1
        or attestation["bytes"] > 64 * 1024
        or not isinstance(gate.get("attestation_sha256"), str)
        or len(gate["attestation_sha256"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in gate["attestation_sha256"]
        )
        or attestation["sha256"] != gate["attestation_sha256"]
    ):
        _fail("The synthetic-test attestation publication is unsafe.")
    project_files[prereg_api.TEST_ATTESTATION_PATH] = attestation

    for relative in prereg_api.TEST_EXECUTION_PATHS:
        path = workspace_api._project_path(
            root, relative, "synthetic-test execution dependency"
        )
        snapshot = workspace_api._snapshot_file(
            path, "A synthetic-test execution dependency"
        )
        if snapshot["mode"] & 0o022 or snapshot["nlink"] != 1:
            _fail("A synthetic-test execution dependency is unsafe.")
        project_files[relative] = snapshot

    try:
        runtime_locator, locked_runtime = _snapshot_runtime_locator(root)
        running_runtime = Path(sys.executable).resolve(strict=True)
        locked_stat = locked_runtime.stat()
        running_stat = running_runtime.stat()
    except OSError as error:
        raise HumanAdjudicationFinalizeError(
            "The locked synthetic-test interpreter is unavailable."
        ) from error
    if (locked_stat.st_dev, locked_stat.st_ino) != (
        running_stat.st_dev,
        running_stat.st_ino,
    ):
        _fail("The finalizer is not running under the locked test interpreter.")
    runtime = workspace_api._snapshot_file(
        locked_runtime, "The locked synthetic-test interpreter"
    )
    if runtime["mode"] & 0o022:
        _fail("The locked synthetic-test interpreter has unsafe permissions.")
    return {
        "project_files": project_files,
        "runtime_locator": runtime_locator,
        "runtime_path": locked_runtime,
        "runtime": runtime,
    }


def _snapshot_runtime_locator(root: Path) -> tuple[dict[str, Any], Path]:
    """Bind the project-local interpreter locator without following its leaf."""
    try:
        resolved_root = root.resolve(strict=True)
    except OSError:
        raise HumanAdjudicationFinalizeError(
            "The locked synthetic-test interpreter locator is unavailable."
        ) from None
    locator = resolved_root / prereg_api.TEST_COMMAND_ARGV[0]
    parent_descriptor: int | None = None
    fresh_descriptor: int | None = None
    try:
        parent_descriptor, parent_chain = workspace_api._open_directory_fd(
            locator.parent
        )
        initial = os.stat(
            locator.name, dir_fd=parent_descriptor, follow_symlinks=False
        )
        if not (stat.S_ISLNK(initial.st_mode) or stat.S_ISREG(initial.st_mode)):
            _fail("The locked synthetic-test interpreter locator is unsafe.")
        link_target = (
            os.readlink(locator.name, dir_fd=parent_descriptor)
            if stat.S_ISLNK(initial.st_mode)
            else None
        )
        resolved = locator.resolve(strict=True)
        after = os.stat(
            locator.name, dir_fd=parent_descriptor, follow_symlinks=False
        )
        fresh_descriptor, fresh_chain = workspace_api._open_directory_fd(
            locator.parent
        )
        final = os.stat(
            locator.name, dir_fd=fresh_descriptor, follow_symlinks=False
        )
    except HumanAdjudicationFinalizeError:
        raise
    except (workspace_api.HumanAdjudicationError, OSError, RuntimeError):
        raise HumanAdjudicationFinalizeError(
            "The locked synthetic-test interpreter locator is unavailable."
        ) from None
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        if fresh_descriptor is not None:
            os.close(fresh_descriptor)
    if (
        not workspace_api._same_open_snapshot(initial, after)
        or not workspace_api._same_open_snapshot(after, final)
        or parent_chain != fresh_chain
    ):
        _fail("The locked synthetic-test interpreter locator changed.")
    return {
        "path": locator,
        "parent_chain": parent_chain,
        "identity": (after.st_dev, after.st_ino),
        "full_mode": after.st_mode,
        "nlink": after.st_nlink,
        "bytes": after.st_size,
        "mtime_ns": after.st_mtime_ns,
        "ctime_ns": after.st_ctime_ns,
        "link_target": link_target,
        "resolved_path": resolved,
    }, resolved


def _runtime_locator_seal(snapshot: Mapping[str, Any]) -> tuple[object, ...]:
    return tuple(
        snapshot[key]
        for key in (
            "parent_chain",
            "identity",
            "full_mode",
            "nlink",
            "bytes",
            "mtime_ns",
            "ctime_ns",
            "link_target",
            "resolved_path",
        )
    )


def _finish_test_gate_closure(root: Path, closure: Mapping[str, Any]) -> None:
    project_files = closure.get("project_files")
    if not isinstance(project_files, Mapping):
        _fail("The synthetic-test execution closure is unavailable.")
    for relative, initial in project_files.items():
        try:
            final = workspace_api._snapshot_file(
                workspace_api._project_path(
                    root, relative, "synthetic-test execution dependency"
                ),
                "A synthetic-test execution dependency",
            )
        except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
            raise HumanAdjudicationFinalizeError(
                "The synthetic-test execution closure changed during the operation."
            ) from error
        if workspace_api._seal(final) != workspace_api._seal(initial):
            _fail("The synthetic-test execution closure changed during the operation.")
    initial_locator = closure.get("runtime_locator")
    runtime_path = closure.get("runtime_path")
    initial_runtime = closure.get("runtime")
    if (
        not isinstance(initial_locator, Mapping)
        or not isinstance(runtime_path, Path)
        or not isinstance(initial_runtime, Mapping)
    ):
        _fail("The locked synthetic-test interpreter closure is unavailable.")
    try:
        final_locator, resolved_runtime = _snapshot_runtime_locator(root)
        if (
            _runtime_locator_seal(final_locator)
            != _runtime_locator_seal(initial_locator)
            or resolved_runtime != runtime_path
        ):
            _fail("The locked synthetic-test interpreter locator changed.")
        final_runtime = workspace_api._snapshot_file(
            runtime_path, "The locked synthetic-test interpreter"
        )
    except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
        raise HumanAdjudicationFinalizeError(
            "The locked synthetic-test interpreter changed during the operation."
        ) from error
    if workspace_api._seal(final_runtime) != workspace_api._seal(initial_runtime):
        _fail("The locked synthetic-test interpreter changed during the operation.")


def _safe_project_directory(
    root: Path, relative: Path, label: str, *, must_exist: bool
) -> Path:
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        _fail(f"{label} is not a safe project-relative path.")
    path = root / relative
    if must_exist and (not path.exists() or path.is_symlink() or not path.is_dir()):
        _fail(f"{label} is absent or unsafe.")
    return path


def _snapshot_workspace(
    path: Path, *, retain_payload: bool
) -> dict[str, Any]:
    try:
        directory = workspace_api._snapshot_directory(
            path, "The human-adjudication workspace"
        )
        files, directories = workspace_api._walk_workspace_files(path)
        snapshots = {
            relative: workspace_api._snapshot_file(
                path / relative,
                "A human-adjudication workspace file",
                retain_payload=(
                    retain_payload
                    and (
                        relative.endswith(".jsonl")
                        or relative == "workspace-manifest.json"
                    )
                ),
            )
            for relative in sorted(files)
        }
        directory_snapshots = {
            directory_path.relative_to(path).as_posix():
            workspace_api._snapshot_directory(
                directory_path, "A human-adjudication workspace directory"
            )
            for directory_path in directories
        }
    except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
        raise HumanAdjudicationFinalizeError(
            "The workspace cannot be snapshotted safely."
        ) from error
    return {
        "directory": directory,
        "files": snapshots,
        "directories": directory_snapshots,
    }


def _same_snapshot(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    return workspace_api._seal(first) == workspace_api._seal(second)


def _assert_workspace_closure(
    path: Path, initial: Mapping[str, Any]
) -> None:
    final = _snapshot_workspace(path, retain_payload=False)
    if set(final["files"]) != set(initial["files"]):
        _fail("The workspace file inventory changed during compilation.")
    if set(final["directories"]) != set(initial["directories"]):
        _fail("The workspace directory inventory changed during compilation.")
    if workspace_api._directory_seal(
        initial["directory"]
    ) != workspace_api._directory_seal(final["directory"]):
        _fail("The workspace directory identity changed during compilation.")
    for relative, snapshot in initial["files"].items():
        if not _same_snapshot(snapshot, final["files"][relative]):
            _fail("A workspace file changed during compilation.")
    for relative, snapshot in initial["directories"].items():
        if workspace_api._directory_seal(snapshot) != workspace_api._directory_seal(
            final["directories"][relative]
        ):
            _fail("A workspace directory changed during compilation.")


def _records(snapshot: Mapping[str, Any], label: str) -> list[Mapping[str, Any]]:
    try:
        return workspace_api._read_ndjson_snapshot(snapshot, label)
    except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
        raise HumanAdjudicationFinalizeError(
            "A validated workspace ledger could not be re-read."
        ) from error


def _active(records: Sequence[Mapping[str, Any]], id_key: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for record in records[1:]:
        identifier = record.get(id_key)
        if not isinstance(identifier, str):
            _fail("A validated decision ledger lost its identifier.")
        existing = result.get(identifier)
        if existing is None or record.get("revision", 0) > existing.get("revision", 0):
            result[identifier] = record
        elif record.get("revision") == existing.get("revision") and record != existing:
            _fail("A validated decision ledger contains conflicting active revisions.")
    return result


def _workspace_projection(
    snapshots: Mapping[str, Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    batch_count = config["workspace"]["semantic_batch_count"]
    semantic_source: list[Mapping[str, Any]] = []
    semantic_active: dict[str, Mapping[str, Any]] = {}
    for index in range(1, batch_count + 1):
        source_name = f"semantic-source/semantic-source-batch-{index:04d}.jsonl"
        ledger_name = f"semantic-decisions/semantic-decisions-batch-{index:04d}.jsonl"
        source_records = _records(snapshots[source_name], "A semantic source batch")
        semantic_source.extend(source_records[1:-1])
        overlap = set(semantic_active).intersection(
            _active(_records(snapshots[ledger_name], "A semantic decision ledger"), "review_id")
        )
        if overlap:
            _fail("Semantic active revisions overlap across batches.")
        semantic_active.update(
            _active(_records(snapshots[ledger_name], "A semantic decision ledger"), "review_id")
        )
    if [item.get("review_id") for item in semantic_source] != list(semantic_active):
        _fail("Semantic source and active-decision order diverged.")
    if any(item.get("review_status") != "reviewed" for item in semantic_active.values()):
        _fail("The semantic projection contains an unreviewed item.")

    group_records = _records(
        snapshots["semantic-groups/mapping-groups.jsonl"],
        "The semantic mapping-group ledger",
    )
    groups = _active(group_records, "mapping_group_id")

    route_records = _records(
        snapshots["route-source/route-source-batch-0001.jsonl"],
        "The route source batch",
    )
    route_items = [
        record for record in route_records[1:-1]
        if record.get("record_type") == "route_source_item"
    ]
    route_memberships = [
        record for record in route_records[1:-1]
        if record.get("record_type") == "route_source_membership"
    ]
    route_active = _active(
        _records(
            snapshots["route-decisions/route-decisions-batch-0001.jsonl"],
            "The route decision ledger",
        ),
        "review_id",
    )
    if [item.get("review_id") for item in route_items] != list(route_active):
        _fail("Route source and active-decision order diverged.")
    if any(item.get("review_status") != "reviewed" for item in route_active.values()):
        _fail("The route projection contains an unreviewed item.")

    evidence = _records(
        snapshots["evidence-registry/evidence-registry.jsonl"],
        "The evidence registry",
    )
    attestations = _records(
        snapshots["attestations/batch-attestations.jsonl"],
        "The human-attestation ledger",
    )
    return {
        "semantic_source": semantic_source,
        "semantic_active": semantic_active,
        "groups": groups,
        "route_items": route_items,
        "route_memberships": route_memberships,
        "route_active": route_active,
        "evidence": evidence,
        "attestations": attestations,
    }


def _framed_records(
    begin: Mapping[str, Any],
    body: Sequence[Mapping[str, Any]],
    end_type: str,
    hash_version: str,
) -> tuple[list[Mapping[str, Any]], str]:
    digest = _sequence_hash(hash_version, body)
    return [
        dict(begin),
        *body,
        {
            "record_type": end_type,
            "records": len(body),
            "sequence_hash_version": hash_version,
            "sequence_sha256": digest,
        },
    ], digest


def _build_outputs(
    projection: Mapping[str, Any],
    contract: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    config = contract["config"]
    config_sha = contract["config_sha256"]
    source = config["source_artifact"]

    semantic_body: list[Mapping[str, Any]] = []
    for source_item in projection["semantic_source"]:
        review_id = source_item["review_id"]
        revision = projection["semantic_active"][review_id]
        semantic_body.append({
            "record_type": "reviewed_semantic_decision",
            "review_id": review_id,
            "source_field": source_item["source_field"],
            "exact_raw_value": source_item["exact_raw_value"],
            "exact_row_count": source_item["exact_row_count"],
            "active_revision_sha256": _record_hash(revision),
            "active_revision": revision,
        })
    semantic_records, semantic_hash = _framed_records(
        {
            "record_type": "reviewed_semantic_ledger_begin",
            "schema_version": 1,
            "component_id": COMPONENT_ID,
            "schema": SEMANTIC_SCHEMA,
            "config_sha256": config_sha,
            "semantic_key_set_sha256": source["semantic_template"]["semantic_key_set_sha256"],
            "semantic_items": len(semantic_body),
        },
        semantic_body,
        "reviewed_semantic_ledger_end",
        SEMANTIC_HASH_VERSION,
    )

    group_body = [
        {
            "record_type": "reviewed_semantic_mapping_group",
            "mapping_group_id": group_id,
            "active_revision_sha256": _record_hash(revision),
            "active_revision": revision,
        }
        for group_id, revision in sorted(projection["groups"].items())
    ]
    group_records, group_hash = _framed_records(
        {
            "record_type": "semantic_mapping_groups_begin",
            "schema_version": 1,
            "component_id": COMPONENT_ID,
            "schema": GROUP_SCHEMA,
            "config_sha256": config_sha,
            "mapping_groups": len(group_body),
        },
        group_body,
        "semantic_mapping_groups_end",
        GROUP_HASH_VERSION,
    )

    route_body: list[Mapping[str, Any]] = []
    used_route_ids: set[str] = set()
    for membership in projection["route_memberships"]:
        common = {
            "record_type": "source_specific_route_mapping",
            "source_key": membership["source_key"],
            "source_field": membership["source_field"],
            "field_role": membership["field_role"],
            "raw_value_state": membership["raw_value_state"],
            "exact_raw_value": membership["exact_raw_value"],
            "exact_row_count": membership["exact_row_count"],
            "canonical_review_id": membership["canonical_review_id"],
        }
        if membership["raw_value_state"] == "sql_null":
            route_body.append({
                **common,
                "decision": None,
                "route_state": "missing",
                "sets_has_unknown": False,
                "decision_provenance": "forced_sql_null_policy",
                "review_status": "not_required",
                "active_revision_sha256": None,
                "active_revision": None,
            })
            continue
        review_id = membership["canonical_review_id"]
        revision = projection["route_active"].get(review_id)
        if revision is None:
            _fail("A nonnull route membership lacks a canonical human decision.")
        used_route_ids.add(review_id)
        decision = revision["decision"]
        route_body.append({
            **common,
            "decision": decision,
            "route_state": decision,
            "sets_has_unknown": decision == "unknown",
            "decision_provenance": "human_canonical_exact_route_review",
            "review_status": "reviewed",
            "active_revision_sha256": _record_hash(revision),
            "active_revision": revision,
        })
    if used_route_ids != set(projection["route_active"]):
        _fail("The route mapping does not conserve all canonical decisions.")
    route_records, route_hash = _framed_records(
        {
            "record_type": "source_specific_route_mapping_begin",
            "schema_version": 1,
            "component_id": COMPONENT_ID,
            "schema": ROUTE_SCHEMA,
            "config_sha256": config_sha,
            "canonical_route_items": len(projection["route_active"]),
            "nonnull_memberships": sum(
                record["raw_value_state"] == "nonnull" for record in route_body
            ),
            "sql_null_memberships": sum(
                record["raw_value_state"] == "sql_null" for record in route_body
            ),
            "typed_memberships": len(route_body),
        },
        route_body,
        "source_specific_route_mapping_end",
        ROUTE_HASH_VERSION,
    )

    source_attestations = projection["attestations"]
    attestation_body = [dict(record) for record in source_attestations[1:]]
    attestation_records, attestation_hash = _framed_records(
        {
            "record_type": "human_attestations_begin",
            "schema_version": 1,
            "component_id": COMPONENT_ID,
            "schema": ATTESTATION_SCHEMA,
            "config_sha256": config_sha,
            "source_ledger_header": source_attestations[0],
            "attestation_records": len(attestation_body),
        },
        attestation_body,
        "human_attestations_end",
        ATTESTATION_SCHEMA,
    )

    source_evidence = projection["evidence"]
    evidence_body = [dict(record) for record in source_evidence[1:]]
    evidence_records, evidence_hash = _framed_records(
        {
            "record_type": "evidence_registry_begin",
            "schema_version": 1,
            "component_id": COMPONENT_ID,
            "schema": EVIDENCE_SCHEMA,
            "config_sha256": config_sha,
            "source_registry_header": source_evidence[0],
            "evidence_records": len(evidence_body),
        },
        evidence_body,
        "evidence_registry_end",
        EVIDENCE_SCHEMA,
    )

    semantic_statuses = {
        dimension: dict(Counter(
            record["active_revision"]["dimensions"][dimension]["status"]
            for record in semantic_body
        ))
        for dimension in workspace_api.SEMANTIC_DIMENSIONS
    }
    route_states = dict(Counter(record["route_state"] for record in route_body))
    namespaces = dict(Counter(record["namespace"] for record in evidence_body))
    summary = {
        "schema_version": 1,
        "aggregate_summary_schema": AGGREGATE_SUMMARY_SCHEMA,
        "component_id": COMPONENT_ID,
        "artifact_type": "potassium_query202_private_human_adjudication_summary",
        "status": "human_review_complete_unfrozen",
        "created_at_utc": created_at,
        "counts": {
            "semantic_items": len(semantic_body),
            "mapping_groups": len(group_body),
            "canonical_route_items": len(projection["route_active"]),
            "route_nonnull_memberships": route_states.get("iv", 0)
            + route_states.get("noniv", 0)
            + route_states.get("unknown", 0),
            "route_sql_null_memberships": route_states.get("missing", 0),
            "route_typed_memberships": len(route_body),
            "human_attestation_records": len(attestation_body),
            "evidence_registry_records": len(evidence_body),
        },
        "semantic_status_counts": semantic_statuses,
        "route_state_counts": route_states,
        "evidence_namespace_counts": namespaces,
        "decision_hashes": {
            "semantic_hash_version": SEMANTIC_HASH_VERSION,
            "semantic_sha256": semantic_hash,
            "mapping_group_hash_version": GROUP_HASH_VERSION,
            "mapping_group_sha256": group_hash,
            "route_hash_version": ROUTE_HASH_VERSION,
            "route_sha256": route_hash,
            "attestation_sha256": attestation_hash,
            "evidence_registry_sha256": evidence_hash,
        },
        "claims": {
            "clinical_correctness_established": False,
            "event_mapping_created": False,
            "formal_action_created": False,
            "formal_cohort_created": False,
        },
        "privacy": {
            "aggregate_only": True,
            "raw_values_in_summary": False,
            "database_connected": False,
            "external_api_called": False,
            "llm_called": False,
        },
    }
    return {
        "records": {
            GZIP_OUTPUTS[0]: semantic_records,
            GZIP_OUTPUTS[1]: group_records,
            GZIP_OUTPUTS[2]: route_records,
            GZIP_OUTPUTS[3]: attestation_records,
            GZIP_OUTPUTS[4]: evidence_records,
        },
        "summary": summary,
        "decision_hashes": summary["decision_hashes"],
    }


def _workspace_inventory_for_manifest(
    snapshots: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "file": relative,
            "sha256": snapshot["sha256"],
            "bytes": snapshot["bytes"],
            "mode": f"{snapshot['mode']:04o}",
            "nlink": snapshot["nlink"],
        }
        for relative, snapshot in sorted(snapshots.items())
    ]


def _inventory_hash(version: str, records: Sequence[Mapping[str, Any]]) -> str:
    return _sequence_hash(version, records)


def _workspace_lineage(
    workspace_relative: Path,
    snapshots: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    inventory = _workspace_inventory_for_manifest(snapshots)
    documents = [
        record
        for record in inventory
        if record["file"].startswith("evidence-registry/documents/")
    ]
    return {
        "directory": workspace_relative.as_posix(),
        "validated_status": "human_review_complete_unfrozen",
        "self_contained": False,
        "registered_documents_retained_in_workspace": True,
        "snapshot_hash_version": WORKSPACE_SNAPSHOT_HASH_VERSION,
        "snapshot_sha256": _inventory_hash(
            WORKSPACE_SNAPSHOT_HASH_VERSION, inventory
        ),
        "registered_document_set_hash_version": DOCUMENT_SET_HASH_VERSION,
        "registered_document_set_sha256": _inventory_hash(
            DOCUMENT_SET_HASH_VERSION, documents
        ),
        "registered_document_count": len(documents),
        "files": inventory,
    }


def _artifact_manifest(
    root: Path,
    destination: Path,
    workspace_relative: Path,
    workspace_snapshots: Mapping[str, Mapping[str, Any]],
    output_meta: Mapping[str, Mapping[str, Any]],
    summary_meta: Mapping[str, Any],
    decision_hashes: Mapping[str, Any],
    contract: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    config = contract["config"]
    source = config["source_artifact"]
    return {
        "schema_version": 1,
        "manifest_schema": MANIFEST_SCHEMA,
        "component_id": COMPONENT_ID,
        "artifact_type": "potassium_query202_private_human_adjudication",
        "status": "human_review_complete_unfrozen",
        "created_at_utc": created_at,
        "artifact_directory": destination.relative_to(root).as_posix(),
        "workspace": _workspace_lineage(workspace_relative, workspace_snapshots),
        "component_lineage": {
            "config": contract["path"].relative_to(root).as_posix(),
            "config_sha256": contract["config_sha256"],
            "rule_version": config["rule_version"],
            "generator_bundle_sha256": contract["bundle"]["bundle_sha256"],
            "auditor_bundle_sha256": contract["auditor_bundle"]["bundle_sha256"],
        },
        "source_lineage": {
            "component_id": source["component_id"],
            "artifact_directory": source["directory"],
            "source_config_sha256": source["source_config_sha256"],
            "manifest_sha256": source["manifest_sha256"],
            "aggregate_summary_sha256": source["aggregate_summary_sha256"],
            "audit_sha256": source["audit_sha256"],
            "semantic_template_stored_sha256": source["semantic_template"]["stored_sha256"],
            "semantic_template_raw_sha256": source["semantic_template"]["raw_sha256"],
            "semantic_key_set_sha256": source["semantic_template"]["semantic_key_set_sha256"],
            "route_template_stored_sha256": source["route_template"]["stored_sha256"],
            "route_template_raw_sha256": source["route_template"]["raw_sha256"],
            "local_evidence_stored_sha256": source["local_evidence"]["stored_sha256"],
            "local_evidence_raw_sha256": source["local_evidence"]["raw_sha256"],
            "ndc_decision_config_sha256": config["ndc_decision"]["config_sha256"],
            "ndc_validator_bundle_sha256": config["ndc_decision"]["validator_bundle_sha256"],
        },
        "outputs": {
            **{name: dict(output_meta[name]) for name in GZIP_OUTPUTS},
            "aggregate-summary.json": dict(summary_meta),
        },
        "decision_hashes": dict(decision_hashes),
        "conservation": {
            "semantic_items": source["semantic_template"]["semantic_keys"],
            "mapping_groups": None,
            "canonical_route_items": source["route_template"]["canonical_exact_nonnull_values"],
            "route_nonnull_memberships": source["route_template"]["source_specific_nonnull_memberships"],
            "route_sql_null_memberships": source["route_template"]["source_specific_sql_null_memberships"],
            "route_typed_memberships": source["route_template"]["source_specific_typed_memberships"],
        },
        "guards": {
            "semantic_review_complete": True,
            "route_review_complete": True,
            "reviewed_semantic_ledger_frozen": False,
            "route_mapping_frozen": False,
            **{
                key: False
                for key in config["final_outputs"]["downstream_scientific_guards_remain_false"]
            },
        },
        "claims": {
            "clinical_correctness_established": False,
            "independent_final_artifact_audit_completed": False,
            "frozen": False,
            "artifact_self_contained": False,
        },
        "privacy": {
            "directory_mode": "0700",
            "file_mode": "0600",
            "git_ignored": True,
            "raw_values_printed": False,
            "database_connected": False,
            "external_api_called": False,
            "llm_called": False,
        },
    }


def _assert_temporary_outputs_at(
    directory_descriptor: int,
    expected_meta: Mapping[str, Mapping[str, Any]],
) -> None:
    if set(os.listdir(directory_descriptor)) != set(PRE_AUDIT_OUTPUTS):
        _fail("The compiled pre-audit inventory changed before publication.")
    for name, declared in expected_meta.items():
        snapshot = _snapshot_regular_at(directory_descriptor, name)
        if (
            snapshot["mode"] != 0o600
            or snapshot["nlink"] != 1
            or snapshot["sha256"] != declared["sha256"]
            or snapshot["bytes"] != declared["bytes"]
        ):
            _fail("A compiled output changed before publication.")


def compile_human_adjudication_artifact(
    root: Path,
    workspace_directory: Path,
    config_path: Path = CONFIG_PATH,
    *,
    created_at_utc: str | None = None,
    _failure_hook: FailureHook | None = None,
) -> dict[str, Any]:
    """Compile a complete formal workspace into seven private outputs.

    Reports and raised errors contain no exact source values, rationales, or
    reviewer identifiers.  ``_failure_hook`` exists only for synthetic atomicity
    tests and is not exposed by the CLI.
    """
    try:
        root = root.resolve(strict=True)
    except OSError as error:
        raise HumanAdjudicationFinalizeError("The project root is unavailable.") from error
    contract = _load_contract(root, config_path)
    try:
        source_inventory = workspace_api._source_inventory(root, contract)
    except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
        raise HumanAdjudicationFinalizeError(
            "The frozen source lineage failed closed validation."
        ) from error
    workspace_relative = Path(workspace_directory)
    workspace = _safe_project_directory(
        root, workspace_relative, "The formal workspace", must_exist=True
    )
    if workspace_api._mode(workspace) != "0700" or not workspace_api._git_ignored(root, workspace):
        _fail("The formal workspace is not private and Git-ignored.")
    initial = _snapshot_workspace(workspace, retain_payload=True)
    _call_hook(_failure_hook, "after_initial_snapshot")
    try:
        validation = workspace_api.validate_human_adjudication_workspace(
            root, workspace_relative, config_path=config_path
        )
    except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
        raise HumanAdjudicationFinalizeError(
            "The formal workspace failed closed validation."
        ) from error
    if (
        validation.get("status") != "human_review_complete_unfrozen"
        or validation.get("formal_workspace") is not True
        or validation.get("semantic_review_complete") is not True
        or validation.get("route_review_complete") is not True
    ):
        _fail("The formal workspace has not reached human-review completion.")
    _assert_workspace_closure(workspace, initial)
    _call_hook(_failure_hook, "after_workspace_validation")
    projection = _workspace_projection(initial["files"], contract["config"])
    created_at = _require_utc(created_at_utc, "The compilation time")
    built = _build_outputs(projection, contract, created_at)
    workspace_lineage = _workspace_lineage(workspace_relative, initial["files"])
    built["summary"]["workspace_lineage"] = {
        "directory": workspace_lineage["directory"],
        "self_contained": workspace_lineage["self_contained"],
        "snapshot_hash_version": workspace_lineage["snapshot_hash_version"],
        "snapshot_sha256": workspace_lineage["snapshot_sha256"],
        "registered_document_set_hash_version": workspace_lineage[
            "registered_document_set_hash_version"
        ],
        "registered_document_set_sha256": workspace_lineage[
            "registered_document_set_sha256"
        ],
        "registered_document_count": workspace_lineage[
            "registered_document_count"
        ],
    }

    parent = root / FINAL_ARTIFACT_PARENT
    try:
        parent_descriptor, parent_chain = workspace_api._ensure_private_directory(
            root, FINAL_ARTIFACT_PARENT
        )
    except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
        raise HumanAdjudicationFinalizeError(
            "The final-artifact parent could not be opened safely."
        ) from error
    if not workspace_api._git_ignored(root, parent):
        os.close(parent_descriptor)
        _fail("The final-artifact parent is not private and Git-ignored.")
    destination_name = _timestamp_directory(created_at)
    destination = parent / destination_name
    try:
        os.stat(destination_name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        os.close(parent_descriptor)
        _fail("The final-artifact destination already exists.")
    try:
        temporary_name, temporary_descriptor = _new_private_directory_at(
            parent_descriptor, ".tmp-human-final-"
        )
    except BaseException as error:
        os.close(parent_descriptor)
        if isinstance(error, (HumanAdjudicationFinalizeError, KeyboardInterrupt, SystemExit)):
            raise
        if isinstance(error, (workspace_api.HumanAdjudicationError, OSError, ValueError)):
            raise HumanAdjudicationFinalizeError(
                "Final compilation failed closed while creating its private temporary directory."
            ) from error
        raise
    controlled_identity = (
        os.fstat(temporary_descriptor).st_dev,
        os.fstat(temporary_descriptor).st_ino,
    )
    renamed = False
    try:
        output_meta: dict[str, dict[str, Any]] = {}
        for name in GZIP_OUTPUTS:
            output_meta[name] = _write_gzip_at(
                temporary_descriptor, name, built["records"][name]
            )
        _call_hook(_failure_hook, "after_private_gzip_outputs")
        summary_raw = _pretty_json(built["summary"])
        summary_meta = _write_private_at(
            temporary_descriptor, "aggregate-summary.json", summary_raw
        )
        manifest = _artifact_manifest(
            root,
            destination,
            workspace_relative,
            initial["files"],
            output_meta,
            summary_meta,
            built["decision_hashes"],
            contract,
            created_at,
        )
        manifest["conservation"]["mapping_groups"] = len(projection["groups"])
        manifest_meta = _write_private_at(
            temporary_descriptor, "manifest.json", _pretty_json(manifest)
        )
        complete_meta = {
            **output_meta,
            "aggregate-summary.json": summary_meta,
            "manifest.json": manifest_meta,
        }
        _assert_temporary_outputs_at(temporary_descriptor, complete_meta)
        _call_hook(_failure_hook, "before_final_closure")
        workspace_api._finish_source_closure(source_inventory, contract)
        _finish_auditor_closure(root, contract["auditor_bundle"])
        _finish_test_gate_closure(root, contract["test_gate_closure"])
        _assert_workspace_closure(workspace, initial)
        _call_hook(_failure_hook, "before_atomic_publish")
        _assert_temporary_outputs_at(temporary_descriptor, complete_meta)
        workspace_api._finish_source_closure(source_inventory, contract)
        _finish_auditor_closure(root, contract["auditor_bundle"])
        _finish_test_gate_closure(root, contract["test_gate_closure"])
        _assert_workspace_closure(workspace, initial)
        fresh_parent_descriptor, fresh_parent_chain = workspace_api._open_directory_fd(
            parent
        )
        os.close(fresh_parent_descriptor)
        if fresh_parent_chain != parent_chain:
            _fail("The final-artifact parent changed before atomic publication.")
        os.fsync(temporary_descriptor)
        _rename_directory_noreplace(
            parent_descriptor,
            temporary_name,
            parent_descriptor,
            destination_name,
        )
        renamed = True
        os.fsync(parent_descriptor)
        published_stat = os.fstat(temporary_descriptor)
        if (
            stat.S_IMODE(published_stat.st_mode) != 0o700
            or (published_stat.st_dev, published_stat.st_ino)
            != controlled_identity
        ):
            _fail("The published final artifact lost mode 0700.")
        anchored_destination_descriptor = os.open(
            destination_name,
            workspace_api.DIRECTORY_OPEN_FLAGS,
            dir_fd=parent_descriptor,
        )
        try:
            anchored_destination = os.fstat(anchored_destination_descriptor)
            if (
                anchored_destination.st_dev,
                anchored_destination.st_ino,
            ) != controlled_identity:
                _fail("The published final-artifact leaf was replaced.")
        finally:
            os.close(anchored_destination_descriptor)
        post_parent_descriptor, post_parent_chain = workspace_api._open_directory_fd(
            parent
        )
        os.close(post_parent_descriptor)
        if post_parent_chain != parent_chain:
            _fail("The final-artifact parent changed during atomic publication.")
        post_destination_descriptor, post_destination_chain = (
            workspace_api._open_directory_fd(destination)
        )
        try:
            post_destination_stat = os.fstat(post_destination_descriptor)
            if (
                post_destination_chain[:-1] != parent_chain
                or (post_destination_stat.st_dev, post_destination_stat.st_ino)
                != controlled_identity
            ):
                _fail("The published final-artifact identity changed.")
        finally:
            os.close(post_destination_descriptor)
        _assert_temporary_outputs_at(temporary_descriptor, complete_meta)
        if not workspace_api._git_ignored(root, destination):
            _fail("The published final artifact is not Git-ignored.")
        final_destination_descriptor, final_destination_chain = (
            workspace_api._open_directory_fd(destination)
        )
        try:
            final_destination_stat = os.fstat(final_destination_descriptor)
            if (
                final_destination_chain[:-1] != parent_chain
                or (final_destination_stat.st_dev, final_destination_stat.st_ino)
                != controlled_identity
                or set(os.listdir(final_destination_descriptor))
                != set(PRE_AUDIT_OUTPUTS)
            ):
                _fail("The final-artifact leaf changed before return.")
        finally:
            os.close(final_destination_descriptor)
        _assert_temporary_outputs_at(temporary_descriptor, complete_meta)
        workspace_api._finish_source_closure(source_inventory, contract)
        _finish_auditor_closure(root, contract["auditor_bundle"])
        _finish_test_gate_closure(root, contract["test_gate_closure"])
        _assert_workspace_closure(workspace, initial)
        return {
            "status": "human_review_complete_unfrozen",
            "artifact": destination.relative_to(root).as_posix(),
            "manifest": (destination / "manifest.json").relative_to(root).as_posix(),
            "manifest_sha256": manifest_meta["sha256"],
            "semantic_items": len(projection["semantic_source"]),
            "mapping_groups": len(projection["groups"]),
            "route_typed_memberships": len(projection["route_memberships"]),
            "outputs": len(PRE_AUDIT_OUTPUTS),
            "independent_audit_completed": False,
            "frozen": False,
            "clinical_correctness_established": False,
            "database_connected": False,
            "external_api_called": False,
            "llm_called": False,
        }
    except BaseException as error:
        try:
            _remove_tree_if_identity_at(
                parent_descriptor,
                destination_name if renamed else temporary_name,
                controlled_identity,
            )
        except OSError:
            pass
        if isinstance(error, (HumanAdjudicationFinalizeError, KeyboardInterrupt, SystemExit)):
            raise
        if isinstance(error, (workspace_api.HumanAdjudicationError, OSError, ValueError)):
            raise HumanAdjudicationFinalizeError(
                "Final compilation failed closed during anchored publication."
            ) from error
        raise
    finally:
        os.close(temporary_descriptor)
        os.close(parent_descriptor)


def _snapshot_artifact(
    artifact: Path, expected: set[str]
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    try:
        directory = workspace_api._snapshot_directory(
            artifact, "The compiled human-adjudication artifact"
        )
    except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
        raise HumanAdjudicationFinalizeError(
            "The compiled artifact directory is unsafe."
        ) from error
    if directory["mode"] != 0o700:
        _fail("The compiled artifact directory does not have mode 0700.")
    names = {item.name for item in artifact.iterdir()}
    if names != expected:
        _fail("The compiled artifact inventory is not exact for this lifecycle state.")
    snapshots: dict[str, dict[str, Any]] = {}
    for name in sorted(expected):
        path = artifact / name
        if path.is_symlink() or not path.is_file():
            _fail("The compiled artifact contains an unsafe entry.")
        try:
            snapshot = workspace_api._snapshot_file(
                path, "A compiled human-adjudication file", retain_payload=True
            )
        except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
            raise HumanAdjudicationFinalizeError(
                "A compiled artifact file cannot be read safely."
            ) from error
        if snapshot["mode"] != 0o600 or snapshot["nlink"] != 1:
            _fail(
                "A compiled artifact file does not have mode 0600 and link count 1."
            )
        snapshots[name] = snapshot
    return directory, snapshots


def _assert_artifact_file_closure(
    artifact: Path,
    initial: Mapping[str, Mapping[str, Any]],
    expected: set[str],
) -> None:
    names = {item.name for item in artifact.iterdir()}
    if names != expected:
        _fail("The compiled artifact inventory changed during freeze validation.")
    for name, first in initial.items():
        try:
            final = workspace_api._snapshot_file(
                artifact / name, "A compiled human-adjudication file"
            )
        except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
            raise HumanAdjudicationFinalizeError(
                "A compiled artifact file changed during freeze validation."
            ) from error
        if not _same_snapshot(first, final):
            _fail("A compiled artifact file changed during freeze validation.")


def _expected_audited_files(
    snapshots: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    return {
        name: {"sha256": snapshots[name]["sha256"], "bytes": snapshots[name]["bytes"]}
        for name in PRE_AUDIT_OUTPUTS
    }


def _validate_retained_workspace(
    root: Path,
    manifest_workspace: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    if (
        set(manifest_workspace)
        != {
            "directory",
            "validated_status",
            "self_contained",
            "registered_documents_retained_in_workspace",
            "snapshot_hash_version",
            "snapshot_sha256",
            "registered_document_set_hash_version",
            "registered_document_set_sha256",
            "registered_document_count",
            "files",
        }
        or manifest_workspace.get("validated_status")
        != "human_review_complete_unfrozen"
        or manifest_workspace.get("self_contained") is not False
        or manifest_workspace.get("registered_documents_retained_in_workspace")
        is not True
        or manifest_workspace.get("snapshot_hash_version")
        != WORKSPACE_SNAPSHOT_HASH_VERSION
        or manifest_workspace.get("registered_document_set_hash_version")
        != DOCUMENT_SET_HASH_VERSION
    ):
        _fail("The retained-workspace lineage schema changed.")
    directory_value = manifest_workspace.get("directory")
    if not isinstance(directory_value, str):
        _fail("The retained workspace path is invalid.")
    relative = Path(directory_value)
    workspace_contract = contract["config"]["workspace"]
    expected_parent = Path(workspace_contract["artifact_parent"])
    if relative.parent != expected_parent or not _valid_artifact_leaf(relative.name):
        _fail(
            "The retained workspace is outside its exact configured parent or leaf contract."
        )
    retained = _safe_project_directory(
        root, relative, "The retained formal workspace", must_exist=True
    )
    if workspace_api._mode(retained) != "0700" or not workspace_api._git_ignored(root, retained):
        _fail("The retained formal workspace is not private and Git-ignored.")
    snapshot = _snapshot_workspace(retained, retain_payload=False)
    expected_directories = {
        ".",
        "semantic-source",
        "semantic-decisions",
        "semantic-groups",
        "route-source",
        "route-decisions",
        "evidence-registry",
        "evidence-registry/documents",
        "attestations",
        "revisions",
    }
    if (
        set(snapshot["directories"]) != expected_directories
        or any(
            directory_snapshot["mode"] != 0o700
            for directory_snapshot in snapshot["directories"].values()
        )
        or any(file_snapshot["nlink"] != 1 for file_snapshot in snapshot["files"].values())
    ):
        _fail("The retained formal workspace directory or link inventory changed.")
    inventory = _workspace_inventory_for_manifest(snapshot["files"])
    documents = [
        record
        for record in inventory
        if record["file"].startswith("evidence-registry/documents/")
    ]
    if (
        manifest_workspace.get("files") != inventory
        or manifest_workspace.get("snapshot_sha256")
        != _inventory_hash(WORKSPACE_SNAPSHOT_HASH_VERSION, inventory)
        or manifest_workspace.get("registered_document_count") != len(documents)
        or manifest_workspace.get("registered_document_set_sha256")
        != _inventory_hash(DOCUMENT_SET_HASH_VERSION, documents)
    ):
        _fail("The retained formal workspace or versioned documents changed.")
    return retained, snapshot


def _validate_audit(
    audit: Mapping[str, Any],
    artifact_relative: Path,
    snapshots: Mapping[str, Mapping[str, Any]],
    manifest: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> None:
    exact_keys = {
        "schema_version",
        "component_id",
        "auditor_component_id",
        "artifact_type",
        "audit_schema",
        "audit_method",
        "status",
        "audit_scope",
        "audited_at_utc",
        "artifact_directory",
        "audited_files",
        "manifest_sha256",
        "config_sha256",
        "source_manifest_sha256",
        "ndc_decision_config_sha256",
        "generator_bundle_sha256",
        "auditor_bundle_sha256",
        "workspace_snapshot_sha256",
        "retained_workspace_documents",
        "decision_hashes",
        "checks",
        "claims",
    }
    if set(audit) != exact_keys:
        _fail("The final-artifact audit schema is not exact.")
    checks = audit.get("checks")
    claims = audit.get("claims")
    lineage = manifest.get("component_lineage")
    source = manifest.get("source_lineage")
    workspace_lineage = manifest.get("workspace")
    if (
        audit.get("schema_version") != 1
        or audit.get("component_id") != COMPONENT_ID
        or audit.get("auditor_component_id") != AUDITOR_COMPONENT_ID
        or audit.get("artifact_type") != "potassium_query202_private_human_adjudication_final_audit"
        or audit.get("audit_schema") != AUDIT_SCHEMA
        or audit.get("audit_method") != AUDIT_METHOD
        or audit.get("status") != "passed"
        or audit.get("audit_scope") != "compiled_private_final_artifact"
        or not workspace_api._strict_utc(audit.get("audited_at_utc"))
        or audit.get("artifact_directory") != artifact_relative.as_posix()
        or audit.get("audited_files") != _expected_audited_files(snapshots)
        or audit.get("manifest_sha256") != snapshots["manifest.json"]["sha256"]
        or not isinstance(lineage, Mapping)
        or not isinstance(source, Mapping)
        or not isinstance(workspace_lineage, Mapping)
        or audit.get("config_sha256") != contract["config_sha256"]
        or audit.get("config_sha256") != lineage.get("config_sha256")
        or audit.get("source_manifest_sha256") != source.get("manifest_sha256")
        or audit.get("ndc_decision_config_sha256") != source.get("ndc_decision_config_sha256")
        or audit.get("generator_bundle_sha256") != contract["bundle"]["bundle_sha256"]
        or audit.get("generator_bundle_sha256") != lineage.get("generator_bundle_sha256")
        or audit.get("auditor_bundle_sha256") != contract["auditor_bundle"]["bundle_sha256"]
        or audit.get("auditor_bundle_sha256") != lineage.get("auditor_bundle_sha256")
        or audit.get("workspace_snapshot_sha256")
        != workspace_lineage.get("snapshot_sha256")
        or audit.get("retained_workspace_documents")
        != {
            "count": workspace_lineage.get("registered_document_count"),
            "hash_version": workspace_lineage.get(
                "registered_document_set_hash_version"
            ),
            "aggregate_sha256": workspace_lineage.get(
                "registered_document_set_sha256"
            ),
        }
        or audit.get("decision_hashes") != manifest.get("decision_hashes")
        or not isinstance(checks, Mapping)
        or set(checks) != {"total", "passed", "failed"}
        or type(checks.get("total")) is not int
        or checks.get("total") != contract["config"]["final_outputs"][
            "audit_checks_total"
        ]
        or type(checks.get("passed")) is not int
        or checks.get("passed") != contract["config"]["final_outputs"][
            "audit_checks_total"
        ]
        or type(checks.get("failed")) is not int
        or checks.get("failed") != 0
        or claims != {
            "generator_helpers_imported": False,
            "clinical_correctness_established": False,
        }
    ):
        _fail("The independent final-artifact audit is not passed and exactly bound.")


def freeze_human_adjudication_artifact(
    root: Path,
    artifact_directory: Path,
    config_path: Path = CONFIG_PATH,
    *,
    frozen_at_utc: str | None = None,
    _failure_hook: FailureHook | None = None,
) -> dict[str, Any]:
    """Add one freeze manifest after an exact independent final audit.

    Existing compiled files and the audit are read twice and never rewritten.
    The audit must bind the configured independent-auditor bundle and explicitly
    attest that generator helpers were not imported.
    """
    try:
        root = root.resolve(strict=True)
    except OSError as error:
        raise HumanAdjudicationFinalizeError("The project root is unavailable.") from error
    contract = _load_contract(root, config_path)
    try:
        source_inventory = workspace_api._source_inventory(root, contract)
    except (workspace_api.HumanAdjudicationError, OSError, ValueError) as error:
        raise HumanAdjudicationFinalizeError(
            "The frozen source lineage failed closed validation."
        ) from error
    artifact_relative = Path(artifact_directory)
    if (
        artifact_relative.parent != FINAL_ARTIFACT_PARENT
        or not _valid_artifact_leaf(artifact_relative.name)
    ):
        _fail("The compiled artifact is not one timestamped child of its frozen parent.")
    artifact = _safe_project_directory(
        root, artifact_relative, "The compiled artifact", must_exist=True
    )
    if not workspace_api._git_ignored(root, artifact):
        _fail("The compiled artifact is not Git-ignored.")
    expected = set(PRE_AUDIT_OUTPUTS) | {AUDIT_FILE}
    artifact_directory_snapshot, snapshots = _snapshot_artifact(artifact, expected)
    _call_hook(_failure_hook, "after_initial_snapshot")
    manifest = _strict_json(snapshots["manifest.json"]["payload"], "The manifest")
    summary = _strict_json(
        snapshots["aggregate-summary.json"]["payload"], "The aggregate summary"
    )
    audit = _strict_json(snapshots[AUDIT_FILE]["payload"], "The independent audit")
    manifest_workspace = manifest.get("workspace")
    summary_workspace = summary.get("workspace_lineage")
    if (
        manifest.get("manifest_schema") != MANIFEST_SCHEMA
        or summary.get("aggregate_summary_schema") != AGGREGATE_SUMMARY_SCHEMA
        or manifest.get("component_id") != COMPONENT_ID
        or manifest.get("status") != "human_review_complete_unfrozen"
        or manifest.get("artifact_directory") != artifact_relative.as_posix()
        or summary.get("status") != "human_review_complete_unfrozen"
        or manifest.get("decision_hashes") != summary.get("decision_hashes")
        or not isinstance(manifest_workspace, Mapping)
        or not isinstance(summary_workspace, Mapping)
        or manifest_workspace.get("self_contained") is not False
        or summary_workspace.get("snapshot_sha256")
        != manifest_workspace.get("snapshot_sha256")
        or summary_workspace.get(
            "registered_document_set_sha256"
        )
        != manifest_workspace.get("registered_document_set_sha256")
    ):
        _fail("The compiled artifact lifecycle or decision hashes changed.")
    assert isinstance(manifest_workspace, Mapping)
    retained_workspace, retained_workspace_snapshot = _validate_retained_workspace(
        root, manifest_workspace, contract
    )
    declared_outputs = manifest.get("outputs")
    if not isinstance(declared_outputs, Mapping) or set(declared_outputs) != set(
        PRE_AUDIT_OUTPUTS
    ) - {"manifest.json"}:
        _fail("The compiled artifact manifest output inventory changed.")
    for name, declared in declared_outputs.items():
        if (
            not isinstance(declared, Mapping)
            or declared.get("sha256") != snapshots[name]["sha256"]
            or declared.get("bytes") != snapshots[name]["bytes"]
        ):
            _fail("The compiled artifact manifest has a stale output binding.")
    _validate_audit(
        audit, artifact_relative, snapshots, manifest, contract
    )
    _assert_artifact_file_closure(artifact, snapshots, expected)
    _call_hook(_failure_hook, "before_final_closure")
    # The contract loader and these explicit closures bind config, generator,
    # source/NDC, and auditor implementations across the entire freeze step.
    workspace_api._finish_source_closure(source_inventory, contract)
    _finish_auditor_closure(root, contract["auditor_bundle"])
    _finish_test_gate_closure(root, contract["test_gate_closure"])
    _assert_artifact_file_closure(artifact, snapshots, expected)
    _assert_workspace_closure(retained_workspace, retained_workspace_snapshot)

    frozen_at = _require_utc(frozen_at_utc, "The freeze time")
    whole_files = {
        name: {"sha256": snapshot["sha256"], "bytes": snapshot["bytes"]}
        for name, snapshot in sorted(snapshots.items())
    }
    freeze_manifest = {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "artifact_type": "potassium_query202_private_human_adjudication_freeze",
        "freeze_schema": FREEZE_SCHEMA,
        "status": "frozen",
        "frozen_at_utc": frozen_at,
        "artifact_directory": artifact_relative.as_posix(),
        "whole_file_bindings": whole_files,
        "manifest_sha256": snapshots["manifest.json"]["sha256"],
        "audit_sha256": snapshots[AUDIT_FILE]["sha256"],
        # The config hash transitively binds the public test-attestation hash;
        # that attestation binds every test/execution dependency and the locked
        # runtime.  The descriptor closure above and immediately before/after
        # publication prevents this indirect binding from becoming stale.
        "config_sha256": contract["config_sha256"],
        "source_manifest_sha256": manifest["source_lineage"]["manifest_sha256"],
        "ndc_decision_config_sha256": manifest["source_lineage"]["ndc_decision_config_sha256"],
        "generator_bundle_sha256": contract["bundle"]["bundle_sha256"],
        "auditor_bundle_sha256": contract["auditor_bundle"]["bundle_sha256"],
        "workspace_snapshot_sha256": manifest["workspace"]["snapshot_sha256"],
        "registered_document_set_sha256": manifest["workspace"][
            "registered_document_set_sha256"
        ],
        "registered_document_count": manifest["workspace"][
            "registered_document_count"
        ],
        "decision_hashes": manifest["decision_hashes"],
        "guards": {
            "semantic_review_complete": True,
            "route_review_complete": True,
            "reviewed_semantic_ledger_frozen": True,
            "route_mapping_frozen": True,
            **{
                key: False
                for key in contract["config"]["final_outputs"]["downstream_scientific_guards_remain_false"]
            },
        },
        "claims": {
            "independent_final_artifact_audit_passed": True,
            "clinical_correctness_established": False,
            "event_mapping_created": False,
            "formal_action_created": False,
            "formal_cohort_created": False,
            "artifact_self_contained": False,
        },
        "privacy": {
            "raw_values_printed": False,
            "database_connected": False,
            "external_api_called": False,
            "llm_called": False,
        },
    }
    artifact_descriptor: int | None = None
    parent_descriptor: int | None = None
    temporary_name: str | None = None
    temporary_identity: tuple[int, int] | None = None
    published = False
    try:
        artifact_descriptor, artifact_chain = workspace_api._open_directory_fd(
            artifact
        )
        parent_descriptor, parent_chain = workspace_api._open_directory_fd(
            artifact.parent
        )
        if (
            artifact_chain != artifact_directory_snapshot["parent_chain"]
            or artifact_chain[:-1] != parent_chain
            or (os.fstat(artifact_descriptor).st_dev, os.fstat(artifact_descriptor).st_ino)
            != artifact_directory_snapshot["identity"]
        ):
            _fail("The compiled artifact ancestry changed before freeze publication.")
        payload = _pretty_json(freeze_manifest)
        for _ in range(128):
            candidate = ".tmp-human-freeze-" + secrets.token_hex(12)
            try:
                _write_private_at(parent_descriptor, candidate, payload)
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if temporary_name is None:
            _fail("A collision-free temporary freeze file could not be created.")
        temporary_snapshot = _snapshot_regular_at(
            parent_descriptor, temporary_name
        )
        temporary_identity = temporary_snapshot["identity"]
        if (
            temporary_snapshot["mode"] != 0o600
            or temporary_snapshot["nlink"] != 1
            or temporary_snapshot["sha256"] != _sha(payload)
            or temporary_snapshot["bytes"] != len(payload)
        ):
            _fail("The temporary freeze manifest failed anchored verification.")
        _call_hook(_failure_hook, "before_atomic_freeze")
        _assert_artifact_file_closure(artifact, snapshots, expected)
        workspace_api._finish_source_closure(source_inventory, contract)
        _finish_auditor_closure(root, contract["auditor_bundle"])
        _finish_test_gate_closure(root, contract["test_gate_closure"])
        _assert_workspace_closure(retained_workspace, retained_workspace_snapshot)
        fresh_artifact_descriptor, fresh_artifact_chain = (
            workspace_api._open_directory_fd(artifact)
        )
        os.close(fresh_artifact_descriptor)
        fresh_parent_descriptor, fresh_parent_chain = (
            workspace_api._open_directory_fd(artifact.parent)
        )
        os.close(fresh_parent_descriptor)
        if fresh_artifact_chain != artifact_chain or fresh_parent_chain != parent_chain:
            _fail("The compiled artifact ancestry changed before atomic freeze.")
        current_temporary = _snapshot_regular_at(parent_descriptor, temporary_name)
        if (
            current_temporary["identity"] != temporary_identity
            or current_temporary["mode"] != 0o600
            or current_temporary["nlink"] != 1
            or current_temporary["sha256"] != _sha(payload)
            or current_temporary["bytes"] != len(payload)
        ):
            _fail("The temporary freeze manifest changed before publication.")
        try:
            os.stat(FREEZE_FILE, dir_fd=artifact_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            _fail("The artifact already has a freeze manifest.")
        os.link(
            temporary_name,
            FREEZE_FILE,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=artifact_descriptor,
            follow_symlinks=False,
        )
        published = True
        post_link_descriptor, post_link_chain = workspace_api._open_directory_fd(
            artifact
        )
        os.close(post_link_descriptor)
        if post_link_chain != artifact_chain:
            _fail("The compiled artifact ancestry changed during atomic freeze.")
        _call_hook(_failure_hook, "before_temporary_freeze_cleanup")
        _unlink_if_identity_at(
            parent_descriptor, temporary_name, temporary_identity
        )
        try:
            os.stat(
                temporary_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            _fail("The temporary freeze path was replaced during cleanup.")
        temporary_name = None
        os.fsync(artifact_descriptor)
        os.fsync(parent_descriptor)
        final_snapshot = _snapshot_regular_at(artifact_descriptor, FREEZE_FILE)
        if (
            final_snapshot["mode"] != 0o600
            or final_snapshot["nlink"] != 1
            or final_snapshot["sha256"] != _sha(payload)
            or final_snapshot["bytes"] != len(payload)
        ):
            _fail("The atomically added freeze manifest failed verification.")
        if set(os.listdir(artifact_descriptor)) != expected | {FREEZE_FILE}:
            _fail("The frozen artifact inventory changed.")
        _assert_artifact_file_closure(
            artifact, snapshots, expected | {FREEZE_FILE}
        )
        workspace_api._finish_source_closure(source_inventory, contract)
        _finish_auditor_closure(root, contract["auditor_bundle"])
        _finish_test_gate_closure(root, contract["test_gate_closure"])
        _assert_workspace_closure(retained_workspace, retained_workspace_snapshot)
        return {
            "status": "frozen",
            "artifact": artifact_relative.as_posix(),
            "freeze_manifest": (artifact / FREEZE_FILE).relative_to(root).as_posix(),
            "freeze_manifest_sha256": final_snapshot["sha256"],
            "bound_private_files": len(whole_files),
            "semantic_review_complete": True,
            "route_review_complete": True,
            "reviewed_semantic_ledger_frozen": True,
            "route_mapping_frozen": True,
            "clinical_correctness_established": False,
            "database_connected": False,
            "external_api_called": False,
            "llm_called": False,
        }
    except BaseException as error:
        if (
            temporary_name is not None
            and temporary_identity is not None
            and parent_descriptor is not None
        ):
            try:
                _unlink_if_identity_at(
                    parent_descriptor, temporary_name, temporary_identity
                )
            except OSError:
                pass
        if published and artifact_descriptor is not None:
            try:
                assert temporary_identity is not None
                _unlink_if_identity_at(
                    artifact_descriptor, FREEZE_FILE, temporary_identity
                )
            except OSError:
                pass
        if isinstance(error, (HumanAdjudicationFinalizeError, KeyboardInterrupt, SystemExit)):
            raise
        if isinstance(error, (workspace_api.HumanAdjudicationError, OSError, ValueError)):
            raise HumanAdjudicationFinalizeError(
                "Separate freeze failed closed during anchored publication."
            ) from error
        raise
    finally:
        if artifact_descriptor is not None:
            os.close(artifact_descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


__all__ = [
    "AUDIT_METHOD",
    "AUDIT_SCHEMA",
    "AUDITOR_COMPONENT_ID",
    "CONFIG_PATH",
    "FINAL_ARTIFACT_PARENT",
    "FREEZE_SCHEMA",
    "HumanAdjudicationFinalizeError",
    "compile_human_adjudication_artifact",
    "freeze_human_adjudication_artifact",
]
