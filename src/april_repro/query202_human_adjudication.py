"""Create and validate the private Query-202 human-adjudication workspace.

The workspace is an offline, exact-value handoff.  It separates immutable
source views from append-only human decision ledgers.  Initialization assigns
stable review identifiers and writes only ``unreviewed``/``uncertain`` or
``unreviewed``/``unknown`` decisions; it never classifies a medication or
route.  All returned reports are aggregate-only.

This module deliberately does not import the upstream compiler.  The frozen
gzip streams are validated from their own bytes and from the hashes and
cardinalities in the component configuration.
"""
from __future__ import annotations

from collections import Counter
import ctypes
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import struct
import subprocess
import sys
import tomllib
from typing import Any, Iterable, Mapping, Sequence
import zlib


CONFIG_PATH = Path(
    "config/preregistrations/d005_potassium_query202_human_adjudication.toml"
)
COMPONENT_ID = "D005-K-QUERY202-HUMAN-ADJUDICATION-v1"
SOURCE_COMPONENT_ID = "D005-K-QUERY202-ADJUDICATION-INPUT-v1"
NDC_COMPONENT_ID = "D005-K-QUERY202-NDC-EVIDENCE-MODE-v1"
PLACEHOLDER = "UNSET_REQUIRED_BEFORE_FREEZE"
ARTIFACT_ENCODING = "gzip+utf8+ndjson-v1"
BUNDLE_ENCODING = "uint32be_path_length+path_utf8+uint64be_content_length+content"
GENERATOR_PATHS = (
    "src/april_repro/__init__.py",
    "src/april_repro/query202_human_adjudication_preregistration.py",
    "src/april_repro/query202_human_adjudication.py",
    "src/april_repro/query202_human_adjudication_writer.py",
    "scripts/initialize_potassium_query202_human_adjudication.py",
    "scripts/validate_potassium_query202_human_adjudication.py",
    "scripts/apply_potassium_query202_human_adjudication_transaction.py",
    "scripts/attest_potassium_query202_human_adjudication_tests.py",
    "src/april_repro/query202_human_adjudication_finalize.py",
    "scripts/compile_potassium_query202_human_adjudication.py",
    "scripts/freeze_potassium_query202_human_adjudication.py",
)

LOCAL_EVIDENCE_INDEX_FILE = "evidence-registry/local-evidence-bridge-index.bin"
LOCAL_EVIDENCE_INDEX_ENCODING = (
    "u8-member-count+4xu32be-review-sequence-zero-padded-v1"
)
LOCAL_EVIDENCE_INDEX_RECORD_BYTES = 17

SEMANTIC_DIMENSIONS = (
    "product_identity",
    "dosage_form",
    "treatment_intent",
    "potassium_content",
    "meq_convertibility",
)
SEMANTIC_STATUSES = ("supported", "refuted", "uncertain")
ROUTE_DECISIONS = ("iv", "noniv", "unknown")
ROUTE_BASES = (
    "explicit_iv_route_semantics",
    "explicit_noniv_route_semantics",
    "ambiguous_or_insufficient_route_semantics",
    "other_documented_human_judgment",
)
UNCERTAINTY_BASES = ("insufficient_evidence", "conflicting_evidence")
REVIEW_STATUSES = ("unreviewed", "reviewed")

SEMANTIC_SET_VERSION = b"source-field-nonnull-exact-value-set-v1"
ROUTE_SET_VERSION = b"canonical-exact-nonnull-route-value-set-v1"
ACTIVE_BATCH_VERSION = b"query202-human-adjudication-active-batch-v1"
ACTIVE_WORKSPACE_STATE_VERSION = (
    b"query202-human-adjudication-active-workspace-state-v1"
)

LOCAL_SEMANTIC_BINDINGS = {
    ("202b", "detail_seed_membership_bridge"): (
        ("product_description", "mimiciv_hosp.emar_detail.product_description"),
        ("product_description_other", "mimiciv_hosp.emar_detail.product_description_other"),
    ),
    ("202b", "emar_medication_detail_bridge"): (
        ("head_medication", "mimiciv_hosp.emar.medication"),
        ("product_description", "mimiciv_hosp.emar_detail.product_description"),
        ("product_description_other", "mimiciv_hosp.emar_detail.product_description_other"),
    ),
    ("202c", "detail_pharmacy_prescription_bridge"): (
        ("product_description", "mimiciv_hosp.emar_detail.product_description"),
        ("product_description_other", "mimiciv_hosp.emar_detail.product_description_other"),
        ("pharmacy_medication", "mimiciv_hosp.pharmacy.medication"),
        ("drug", "mimiciv_hosp.prescriptions.drug"),
    ),
    ("202c", "head_pharmacy_prescription_bridge"): (
        ("head_medication", "mimiciv_hosp.emar.medication"),
        ("pharmacy_medication", "mimiciv_hosp.pharmacy.medication"),
        ("drug", "mimiciv_hosp.prescriptions.drug"),
    ),
    ("202c", "pharmacy_prescription_bridge"): (
        ("pharmacy_medication", "mimiciv_hosp.pharmacy.medication"),
        ("drug", "mimiciv_hosp.prescriptions.drug"),
    ),
}

GENERAL_LOCAL_STAGE_KINDS = (
    "202b:detail_product_context",
    "202b:detail_seed_membership_bridge",
    "202b:emar_medication_detail_bridge",
    "202b:emar_medication_head_partition",
    "202c:detail_pharmacy_prescription_bridge",
    "202c:head_pharmacy_prescription_bridge",
    "202c:pharmacy_no_prescription_component",
    "202c:pharmacy_prescription_bridge",
    "202c:pharmacy_product_context",
    "202c:prescription_identifier_context",
)
SOURCE_LOCAL_STAGE_KIND_ORDER = (
    "202b:detail_product_context",
    "202b:detail_seed_membership_bridge",
    "202b:emar_medication_detail_bridge",
    "202b:emar_medication_head_partition",
    "202c:pharmacy_product_context",
    "202c:pharmacy_prescription_bridge",
    "202c:prescription_identifier_context",
    "202c:head_pharmacy_prescription_bridge",
    "202c:pharmacy_no_prescription_component",
    "202c:detail_pharmacy_prescription_bridge",
)
GROUP_LOCAL_STAGE_KINDS = tuple(
    f"{stage}:{kind}" for stage, kind in LOCAL_SEMANTIC_BINDINGS
)
SOURCE_BRIDGE_STAGE_KIND_ORDER = tuple(
    stage_kind
    for stage_kind in SOURCE_LOCAL_STAGE_KIND_ORDER
    if stage_kind in GROUP_LOCAL_STAGE_KINDS
)
WORKSPACE_EVENT_TYPES = (
    "initialized",
    "batch_submitted",
    "batch_revised",
    "group_registry_revised",
    "attestation_added",
    "validation_failed",
    "human_review_complete_unfrozen",
    "abandoned",
)
STRUCTURAL_PREVIEW_POLICY = {
    "enabled_for_internal_api": True,
    "cli_entry_allowed": False,
    "requires_explicit_allow_proposed": True,
    "artifact_parent": (
        "artifacts/query202-human-adjudication-workspace/_structural-previews"
    ),
    "formal_workspace": False,
    "workspace_initialized": False,
    "resume_or_upgrade_to_formal_allowed": False,
    "compile_audit_or_freeze_allowed": False,
    "config_or_bundle_change_invalidates_preview": True,
    "private_directory_mode": "0700",
    "private_file_mode": "0600",
    "git_ignored_required": True,
    "raw_values_on_stdout_allowed": False,
}
REVIEW_WRITER_POLICY = {
    "schema_version": 1,
    "transaction_schema_version": 1,
    "transaction_type": "human_adjudication_update",
    "transaction_exact_schema_required": True,
    "workspace_snapshot_hash_version": (
        "query202-human-workspace-file-snapshot-v1"
    ),
    "max_transaction_bytes": 16 * 1024 * 1024,
    "max_evidence_document_bytes": 128 * 1024 * 1024,
    "max_imported_document_bytes_per_transaction": 256 * 1024 * 1024,
    "max_workspace_versioned_document_bytes": 2 * 1024 * 1024 * 1024,
    "transaction_path_project_relative_required": True,
    "transaction_path_git_ignored_required": True,
    "transaction_file_mode": "0600",
    "transaction_file_nlink": 1,
    "versioned_document_source_path_project_relative_required": True,
    "versioned_document_source_path_git_ignored_required": True,
    "versioned_document_source_file_mode": "0600",
    "versioned_document_source_file_nlink": 1,
    "versioned_document_nonempty_required": True,
    "bounded_descriptor_inputs": [
        "transaction_request",
        "versioned_document_source",
        "workspace_versioned_document",
    ],
    "named_stat_and_open_fstat_before_read_required": True,
    "bounded_read_loop_maximum_plus_one_hard_stop_required": True,
    "final_path_inode_parent_mode_size_nlink_hash_closure_required": True,
    "semantic_route_and_group_explicit_review_status": "reviewed",
    "human_supplied_fields": [
        "semantic_route_and_mapping_group_decisions",
        "explicit_review_status",
        "rationale_and_revision_reason",
        "reviewer_identity",
        "review_and_attestation_times",
        "evidence_references_and_document_bindings",
        "batch_attestation_confirmations",
        "terminal_event_confirmation",
    ],
    "software_derived_fields": [
        "revision_numbers",
        "supersedes_sha256",
        "revision_event_records",
        "workspace_event_records",
        "canonical_record_and_chain_hashes",
        "batch_and_group_registry_hash_bindings",
        "completion_active_workspace_state_hash",
    ],
    "software_derivation_restricted_to_listed_mechanics": True,
    "full_private_sibling_stage_copy_required": True,
    "document_byte_preflight_required": True,
    "stage_document_bytes_before_import_must_equal_live_preflight": True,
    "stage_document_bytes_after_import_must_conserve_existing_plus_imported": True,
    "full_staged_workspace_validation_required": True,
    "two_pass_workspace_snapshot_hash_required": True,
    "external_nonblocking_flock_required": True,
    "named_lock_inode_mode_nlink_closure_before_and_after_exchange_required": True,
    "darwin_atomic_exchange": "renameatx_np(RENAME_SWAP)",
    "linux_atomic_exchange": "renameat2(RENAME_EXCHANGE)",
    "nonatomic_exchange_fallback_allowed": False,
    "stale_workspace_snapshot_base_fails_closed": True,
    "transaction_replay_after_success_fails_closed": True,
    "exact_duplicate_ledger_revision_resubmission_is_idempotent": True,
    "invalid_live_with_stale_stage_policy": (
        "retain_both_fail_closed_manual_recovery"
    ),
    "crash_after_exchange_before_acknowledgement_is_ambiguous": True,
    "retry_after_ambiguous_crash_requires_current_snapshot_inspection": True,
    "mapping_group_tombstone_supported": False,
    "unreplaceable_mapping_group_policy": (
        "abandon_current_workspace_and_reinitialize_new_workspace"
    ),
    "aggregate_only_output_required": True,
    "private_values_in_output_allowed": False,
    "database_access_allowed": False,
    "network_access_allowed": False,
    "external_api_access_allowed": False,
    "llm_access_allowed": False,
}
EVENT_HEADER_FIELDS = (
    "record_type",
    "schema_version",
    "component_id",
    "config_sha256",
    "initial_event_count",
)
REVISION_EVENT_FIELDS = (
    "record_type",
    "event_index",
    "previous_event_sha256",
    "revision_kind",
    "subject_id",
    "batch_index",
    "revision",
    "revision_sha256",
    "supersedes_sha256",
    "reviewer_id",
    "recorded_at_utc",
)
REVISION_EVENT_KEYS = frozenset(REVISION_EVENT_FIELDS)
WORKSPACE_EVENT_FIELDS = (
    "record_type",
    "event_index",
    "previous_event_sha256",
    "event_type",
    "event_at_utc",
    "actor_id",
    "subject_kind",
    "subject_id",
    "subject_sha256",
)
WORKSPACE_EVENT_KEYS = frozenset(WORKSPACE_EVENT_FIELDS)
REVISION_EVENT_LOG_POLICY = {
    "file": "revisions/revision-events.jsonl",
    "header_record_type": "revision_event_ledger_begin",
    "header_exact_fields": list(EVENT_HEADER_FIELDS),
    "header_schema_version": 1,
    "header_initial_event_count": 0,
    "record_type": "revision_event",
    "record_exact_fields": list(REVISION_EVENT_FIELDS),
    "allowed_revision_kinds": [
        "semantic_decision",
        "route_decision",
        "mapping_group",
    ],
    "event_index_starts_at": 1,
    "event_index_contiguous": True,
    "first_previous_event_sha256_is_null": True,
    "later_previous_event_sha256_is_prior_canonical_record_sha256": True,
    "canonical_record_hash": (
        "sha256-canonical-json-utf8-sort-keys-no-whitespace-v1"
    ),
    "nondecreasing_strict_utc_time_required": True,
    "one_event_per_unique_noninitial_item_revision": True,
    "one_event_per_unique_mapping_group_revision": True,
    "exact_duplicate_ledger_resubmission_adds_no_event": True,
    "item_revision_after_first_must_be_reviewed": True,
    "record_must_bind_ledger_revision_sha_supersedes_reviewer_and_time": True,
    "semantic_and_route_batch_index_required": True,
    "mapping_group_batch_index_is_null": True,
}
WORKSPACE_EVENT_LOG_POLICY = {
    "file": "workspace-events.jsonl",
    "header_record_type": "workspace_event_ledger_begin",
    "header_exact_fields": list(EVENT_HEADER_FIELDS),
    "header_schema_version": 1,
    "header_initial_event_count": 0,
    "record_type": "workspace_event",
    "record_exact_fields": list(WORKSPACE_EVENT_FIELDS),
    "event_index_starts_at": 1,
    "event_index_contiguous": True,
    "first_previous_event_sha256_is_null": True,
    "later_previous_event_sha256_is_prior_canonical_record_sha256": True,
    "canonical_record_hash": (
        "sha256-canonical-json-utf8-sort-keys-no-whitespace-v1"
    ),
    "nondecreasing_strict_utc_time_required": True,
    "formal_first_event": "initialized",
    "preview_initialized_event_allowed": False,
    "one_event_per_revision_event": True,
    "one_event_per_unique_attestation": True,
    "validation_failed_never_advances_state": True,
    "human_review_complete_requires_current_review_and_attestation_closure": True,
    "abandoned_is_terminal": True,
}
ACTIVE_STATE_HASH_POLICY = {
    "version": "query202-human-adjudication-active-workspace-state-v1",
    "encoding": (
        "sha256(version-utf8 || "
        "canonical-json-utf8-sort-keys-no-whitespace-v1)"
    ),
    "object_exact_keys": ["batches", "mapping_groups", "current_attestations"],
    "batches_sorted_by": ["review_kind", "batch_index"],
    "batch_exact_fields": [
        "review_kind",
        "batch_index",
        "item_count",
        "active_decisions_sha256",
        "decision_ledger_sha256",
    ],
    "mapping_groups_sorted_by": ["mapping_group_id"],
    "mapping_group_exact_fields": [
        "mapping_group_id",
        "active_revision_sha256",
    ],
    "attestations_sorted_by": ["review_kind", "batch_index"],
    "attestation_exact_fields": [
        "review_kind",
        "batch_index",
        "attestation_sha256",
    ],
}

SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
UTC_RE = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,6})?Z\Z"
)
SEMANTIC_ID_RE = re.compile(r"S[0-9]{6}\Z")
ROUTE_ID_RE = re.compile(r"R[0-9]{6}\Z")
GROUP_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
EVIDENCE_ID_RE = re.compile(r"E[0-9]{6}\Z")

READ_CHUNK_BYTES = 1024 * 1024
MAX_JSON_LINE_BYTES = 8 * 1024 * 1024
MAX_JSON_FILE_BYTES = 128 * 1024 * 1024
MAX_VALUE_UTF8_BYTES = 1024 * 1024
MAX_TEXT_BYTES = 16 * 1024
MAX_REFERENCE_BYTES = 4096
MAX_COUNT = (1 << 63) - 1

DIRECTORY_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
if hasattr(os, "O_NOFOLLOW"):
    DIRECTORY_OPEN_FLAGS |= os.O_NOFOLLOW


class HumanAdjudicationError(RuntimeError):
    """Fail-closed lineage, privacy, schema, or conservation error."""


def _formal_preregistration_report(root: Path) -> Mapping[str, Any]:
    """Load the independently implemented formal-readiness report.

    Keeping this call behind a small private boundary lets synthetic tests
    substitute a synthetic readiness report without adding a production
    execution override to initialization or validation.
    """
    from .query202_human_adjudication_preregistration import (
        query202_human_adjudication_preregistration_report,
    )

    return query202_human_adjudication_preregistration_report(root)


def _require_formal_preregistration_ready(
    root: Path, contract: Mapping[str, Any]
) -> None:
    """Require the exact frozen preregistration gate for formal workspaces."""
    if contract.get("proposed") is True:
        return
    try:
        report = _formal_preregistration_report(root)
    except (OSError, RuntimeError, ValueError) as error:
        raise HumanAdjudicationError(
            "The formal preregistration readiness report failed closed."
        ) from error
    implementation = report.get("implementation") if isinstance(report, Mapping) else None
    if (
        not isinstance(report, Mapping)
        or report.get("schema_version") != 1
        or report.get("component_id") != COMPONENT_ID
        or report.get("status") != "frozen_for_execution"
        or report.get("execution_status") != "not_initialized"
        or report.get("execution_permitted") is not True
        or report.get("implementation_state") != "implemented_and_tested"
        or report.get("valid") is not True
        or report.get("frozen_contract_effective") is not True
        or report.get("initialization_ready") is not True
        or report.get("source_evidence_verified") is not True
        or report.get("ndc_decision_verified") is not True
        or report.get("snapshot_closure_verified") is not True
        or report.get("full_snapshot_closure_verified") is not True
        or report.get("config_sha256") != contract.get("config_sha256")
        or report.get("errors") != []
        or report.get("configured_blockers") != []
        or report.get("readiness_blockers") != []
        or not isinstance(implementation, Mapping)
        or set(implementation) != {"generator", "auditor"}
        or any(
            not isinstance(implementation[name], Mapping)
            or implementation[name].get("bundle_frozen_and_verified") is not True
            for name in ("generator", "auditor")
        )
    ):
        raise HumanAdjudicationError(
            "The formal preregistration is not exactly ready for initialization."
        )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HumanAdjudicationError("A JSON object contains a duplicate key.")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise HumanAdjudicationError("A JSON value contains a non-finite number.")


def _json_loads(raw: bytes, label: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except HumanAdjudicationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HumanAdjudicationError(f"{label} is not strict UTF-8 JSON.") from None


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _json_line(value: Mapping[str, Any]) -> bytes:
    return _canonical_json(value) + b"\n"


def _pretty_json(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _record_sha(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(record)).hexdigest()


def _absolute_parts(path: Path) -> tuple[str, ...]:
    absolute = Path(os.path.abspath(path))
    if not absolute.is_absolute():  # pragma: no cover - defensive on unusual hosts
        raise HumanAdjudicationError("A filesystem path is not absolute.")
    return absolute.parts


def _open_directory_fd(path: Path) -> tuple[int, tuple[tuple[int, int], ...]]:
    """Open every directory component without following symlinks.

    The returned identity chain lets callers detect a parent-directory swap on
    a fresh second traversal.  All project/source/workspace I/O uses this
    root-anchored openat walk instead of resolving a pathname and reopening it.
    """
    parts = _absolute_parts(path)
    descriptor: int | None = None
    identities: list[tuple[int, int]] = []
    try:
        descriptor = os.open(parts[0], DIRECTORY_OPEN_FLAGS)
        current = os.fstat(descriptor)
        if not stat.S_ISDIR(current.st_mode):
            raise HumanAdjudicationError("A path root is not a directory.")
        identities.append((current.st_dev, current.st_ino))
        for part in parts[1:]:
            next_descriptor = os.open(
                part, DIRECTORY_OPEN_FLAGS, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = next_descriptor
            current = os.fstat(descriptor)
            if not stat.S_ISDIR(current.st_mode):
                raise HumanAdjudicationError(
                    "A filesystem path contains a non-directory parent."
                )
            identities.append((current.st_dev, current.st_ino))
        return descriptor, tuple(identities)
    except HumanAdjudicationError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        raise HumanAdjudicationError(
            "A filesystem path is absent, unsafe, or traverses a symlink."
        ) from None


def _open_parent_fd(path: Path) -> tuple[int, str, tuple[tuple[int, int], ...]]:
    absolute = Path(os.path.abspath(path))
    if absolute.name == "":
        raise HumanAdjudicationError("A file path has no leaf name.")
    descriptor, identities = _open_directory_fd(absolute.parent)
    return descriptor, absolute.name, identities


def _lstat_nofollow(
    path: Path,
) -> tuple[os.stat_result, tuple[tuple[int, int], ...]]:
    descriptor: int | None = None
    try:
        descriptor, name, identities = _open_parent_fd(path)
        value = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if stat.S_ISLNK(value.st_mode):
            raise HumanAdjudicationError("A filesystem path is a symlink.")
        return value, identities
    except HumanAdjudicationError:
        raise
    except OSError:
        raise HumanAdjudicationError("A filesystem path is absent or unsafe.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _ensure_private_directory(
    root: Path, relative: Path
) -> tuple[int, tuple[tuple[int, int], ...]]:
    """Create/open a root-relative directory through one anchored fd chain."""
    descriptor, identities = _open_directory_fd(root)
    chain = list(identities)
    try:
        for part in relative.parts:
            try:
                os.mkdir(part, 0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            next_descriptor = os.open(
                part, DIRECTORY_OPEN_FLAGS, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = next_descriptor
            value = os.fstat(descriptor)
            if not stat.S_ISDIR(value.st_mode):
                raise HumanAdjudicationError(
                    "The private output parent contains a non-directory."
                )
            chain.append((value.st_dev, value.st_ino))
        os.fchmod(descriptor, 0o700)
        return descriptor, tuple(chain)
    except HumanAdjudicationError:
        os.close(descriptor)
        raise
    except OSError:
        os.close(descriptor)
        raise HumanAdjudicationError(
            "The private output parent could not be created safely."
        ) from None


def _remove_tree_at(parent_descriptor: int, name: str) -> None:
    """Remove one controlled temporary tree without reopening its parents."""
    try:
        value = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(value.st_mode):
        os.unlink(name, dir_fd=parent_descriptor)
        return
    descriptor = os.open(name, DIRECTORY_OPEN_FLAGS, dir_fd=parent_descriptor)
    try:
        for child in os.listdir(descriptor):
            _remove_tree_at(descriptor, child)
    finally:
        os.close(descriptor)
    os.rmdir(name, dir_fd=parent_descriptor)


def _remove_tree_if_identity_at(
    parent_descriptor: int,
    name: str,
    expected_identity: tuple[int, int],
) -> None:
    """Remove a controlled workspace tree without deleting a raced-in leaf."""
    try:
        current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (current.st_dev, current.st_ino) != expected_identity:
        return
    _remove_tree_at(parent_descriptor, name)


def _open_relative_parent_at(
    root_descriptor: int,
    relative: str,
    label: str,
) -> tuple[int, str]:
    """Open an existing parent strictly beneath one already-open directory."""
    path = _safe_relative(relative, label)
    if path.parts in {(), (".",)}:
        raise HumanAdjudicationError(f"{label} must name a private leaf.")
    descriptor = os.dup(root_descriptor)
    try:
        root_stat = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or stat.S_IMODE(root_stat.st_mode) != 0o700
        ):
            raise HumanAdjudicationError(
                "The anchored private workspace root is unsafe."
            )
        for part in path.parts[:-1]:
            next_descriptor = os.open(
                part,
                DIRECTORY_OPEN_FLAGS,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
            current = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(current.st_mode)
                or stat.S_IMODE(current.st_mode) != 0o700
            ):
                raise HumanAdjudicationError(
                    "An anchored private workspace directory is unsafe."
                )
        return descriptor, path.name
    except HumanAdjudicationError:
        os.close(descriptor)
        raise
    except OSError:
        os.close(descriptor)
        raise HumanAdjudicationError(
            f"{label} parent is absent, unsafe, or traverses a symlink."
        ) from None


def _unlink_file_if_identity_at(
    parent_descriptor: int,
    name: str,
    expected_identity: tuple[int, int],
) -> None:
    """Remove only the still-named regular file created by this process."""
    try:
        current = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISREG(current.st_mode)
        or (current.st_dev, current.st_ino) != expected_identity
    ):
        return
    os.unlink(name, dir_fd=parent_descriptor)


def _mkdir_private_at(root_descriptor: int, relative: str) -> tuple[int, int]:
    """Create one 0700 directory through the held temporary-workspace fd."""
    parent_descriptor: int | None = None
    child_descriptor: int | None = None
    identity: tuple[int, int] | None = None
    completed = False
    try:
        parent_descriptor, name = _open_relative_parent_at(
            root_descriptor, relative, "Private workspace directory"
        )
        os.mkdir(name, 0o700, dir_fd=parent_descriptor)
        child_descriptor = os.open(
            name, DIRECTORY_OPEN_FLAGS, dir_fd=parent_descriptor
        )
        os.fchmod(child_descriptor, 0o700)
        current = os.fstat(child_descriptor)
        identity = (current.st_dev, current.st_ino)
        named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (
            not stat.S_ISDIR(current.st_mode)
            or stat.S_IMODE(current.st_mode) != 0o700
            or not _same_open_snapshot(current, named)
        ):
            raise HumanAdjudicationError(
                "A generated private workspace directory is unsafe."
            )
        os.fsync(child_descriptor)
        os.fsync(parent_descriptor)
        completed = True
        return identity
    except HumanAdjudicationError:
        raise
    except OSError:
        raise HumanAdjudicationError(
            "A private workspace directory could not be created safely."
        ) from None
    finally:
        if child_descriptor is not None:
            os.close(child_descriptor)
        if parent_descriptor is not None:
            if identity is not None and not completed:
                try:
                    _remove_tree_if_identity_at(
                        parent_descriptor, name, identity
                    )
                except OSError:
                    pass
            os.close(parent_descriptor)


def _clear_controlled_directory_fd(descriptor: int) -> None:
    """Scrub the contents of the held controlled directory after failure."""
    for name in os.listdir(descriptor):
        try:
            initial = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            continue
        identity = (initial.st_dev, initial.st_ino)
        if stat.S_ISDIR(initial.st_mode):
            child: int | None = None
            try:
                child = os.open(name, DIRECTORY_OPEN_FLAGS, dir_fd=descriptor)
                opened = os.fstat(child)
                if (opened.st_dev, opened.st_ino) != identity:
                    continue
                _clear_controlled_directory_fd(child)
                os.fsync(child)
            except OSError:
                continue
            finally:
                if child is not None:
                    os.close(child)
            try:
                current = os.stat(
                    name, dir_fd=descriptor, follow_symlinks=False
                )
                if (
                    stat.S_ISDIR(current.st_mode)
                    and (current.st_dev, current.st_ino) == identity
                ):
                    os.rmdir(name, dir_fd=descriptor)
            except OSError:
                pass
        elif stat.S_ISREG(initial.st_mode):
            child = None
            try:
                flags = os.O_WRONLY
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                child = os.open(name, flags, dir_fd=descriptor)
                opened = os.fstat(child)
                if (opened.st_dev, opened.st_ino) != identity:
                    continue
                os.ftruncate(child, 0)
                os.fsync(child)
            except OSError:
                continue
            finally:
                if child is not None:
                    os.close(child)
            try:
                _unlink_file_if_identity_at(descriptor, name, identity)
            except OSError:
                pass
    os.fsync(descriptor)


def _scrub_and_remove_controlled_directory_at(
    parent_descriptor: int,
    controlled_descriptor: int,
    expected_identity: tuple[int, int],
) -> None:
    """Scrub the held tree and remove any same-parent name still binding it."""
    current = os.fstat(controlled_descriptor)
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != expected_identity
    ):
        return
    _clear_controlled_directory_fd(controlled_descriptor)
    for name in os.listdir(parent_descriptor):
        try:
            candidate = os.stat(
                name, dir_fd=parent_descriptor, follow_symlinks=False
            )
        except FileNotFoundError:
            continue
        if (
            stat.S_ISDIR(candidate.st_mode)
            and (candidate.st_dev, candidate.st_ino) == expected_identity
        ):
            try:
                os.rmdir(name, dir_fd=parent_descriptor)
            except OSError:
                pass
    os.fsync(parent_descriptor)


def _rename_directory_noreplace(
    source_parent_descriptor: int,
    source_name: str,
    destination_parent_descriptor: int,
    destination_name: str,
) -> None:
    """Atomically publish a directory without replacing an existing leaf."""
    library = ctypes.CDLL(None, use_errno=True)
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
        raise HumanAdjudicationError(
            "This platform lacks atomic no-replace workspace publication."
        )
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
        os.fsencode(source_name),
        destination_parent_descriptor,
        os.fsencode(destination_name),
        flag,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise HumanAdjudicationError(
            "The workspace destination appeared before atomic publication."
        )
    raise HumanAdjudicationError(
        "Atomic no-replace workspace publication failed."
    )


def _mode(path: Path) -> str:
    value, _ = _lstat_nofollow(path)
    return format(stat.S_IMODE(value.st_mode), "04o")


def _safe_relative(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise HumanAdjudicationError(f"{label} path is invalid.")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or str(path) != path.as_posix():
        raise HumanAdjudicationError(f"{label} path is unsafe.")
    return path


def _project_path(root: Path, value: object, label: str, *, must_exist: bool = True) -> Path:
    relative = _safe_relative(value, label)
    try:
        resolved_root = root.resolve(strict=True)
    except OSError:
        raise HumanAdjudicationError("The project root is absent or unsafe.") from None
    root_descriptor: int | None = None
    try:
        root_descriptor, _ = _open_directory_fd(resolved_root)
    finally:
        if root_descriptor is not None:
            os.close(root_descriptor)
    candidate = resolved_root / relative
    try:
        if must_exist:
            _lstat_nofollow(candidate)
        else:
            parent_descriptor, _ = _open_directory_fd(candidate.parent)
            os.close(parent_descriptor)
    except HumanAdjudicationError:
        raise HumanAdjudicationError(f"{label} escapes or is absent from the project.") from None
    return candidate


def _same_open_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    return all(getattr(left, field) == getattr(right, field) for field in fields)


def _snapshot_file(path: Path, label: str, *, retain_payload: bool = False) -> dict[str, Any]:
    parent_descriptor: int | None = None
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    payload: list[bytes] | None = [] if retain_payload else None
    digest = hashlib.sha256()
    total = 0
    try:
        parent_descriptor, name, parent_chain = _open_parent_fd(path)
        initial = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if not stat.S_ISREG(initial.st_mode):
            raise HumanAdjudicationError(f"{label} must be one regular file.")
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not _same_open_snapshot(initial, before):
            raise HumanAdjudicationError(f"{label} changed before it was read.")
        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            if payload is not None:
                payload.append(chunk)
        after = os.fstat(descriptor)
        final_at_parent = os.stat(
            name, dir_fd=parent_descriptor, follow_symlinks=False
        )
    except HumanAdjudicationError:
        raise
    except OSError:
        raise HumanAdjudicationError(f"{label} could not be read safely.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)
    try:
        final, final_parent_chain = _lstat_nofollow(path)
    except HumanAdjudicationError:
        raise HumanAdjudicationError(f"{label} changed while it was read.") from None
    if (
        not _same_open_snapshot(before, after)
        or not _same_open_snapshot(after, final_at_parent)
        or not _same_open_snapshot(final_at_parent, final)
        or parent_chain != final_parent_chain
        or total != after.st_size
    ):
        raise HumanAdjudicationError(f"{label} changed while it was read.")
    return {
        "sha256": digest.hexdigest(),
        "bytes": total,
        "mode": stat.S_IMODE(after.st_mode),
        "nlink": after.st_nlink,
        "identity": (after.st_dev, after.st_ino),
        "parent_chain": parent_chain,
        "payload": b"".join(payload) if payload is not None else None,
    }


def _seal(snapshot: Mapping[str, Any]) -> tuple[object, ...]:
    return tuple(
        snapshot[key]
        for key in (
            "parent_chain",
            "identity",
            "mode",
            "nlink",
            "bytes",
            "sha256",
        )
    )


def _snapshot_directory(path: Path, label: str) -> dict[str, Any]:
    descriptor: int | None = None
    fresh_descriptor: int | None = None
    try:
        descriptor, parent_chain = _open_directory_fd(path)
        before = os.fstat(descriptor)
        entries = tuple(sorted(os.listdir(descriptor)))
        after = os.fstat(descriptor)
        fresh_descriptor, fresh_chain = _open_directory_fd(path)
        fresh = os.fstat(fresh_descriptor)
        fresh_entries = tuple(sorted(os.listdir(fresh_descriptor)))
    except HumanAdjudicationError:
        raise HumanAdjudicationError(f"{label} is absent or unsafe.") from None
    except OSError:
        raise HumanAdjudicationError(f"{label} could not be read safely.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if fresh_descriptor is not None:
            os.close(fresh_descriptor)
    if (
        not _same_open_snapshot(before, after)
        or not _same_open_snapshot(after, fresh)
        or parent_chain != fresh_chain
        or entries != fresh_entries
    ):
        raise HumanAdjudicationError(f"{label} changed while it was read.")
    return {
        "identity": (after.st_dev, after.st_ino),
        "parent_chain": parent_chain,
        "mode": stat.S_IMODE(after.st_mode),
        "entries": entries,
    }


def _directory_seal(snapshot: Mapping[str, Any]) -> tuple[object, ...]:
    return (
        snapshot["parent_chain"],
        snapshot["identity"],
        snapshot["mode"],
        snapshot["entries"],
    )


def _require_hash(snapshot: Mapping[str, Any], expected: object, label: str) -> None:
    if not isinstance(expected, str) or SHA256_RE.fullmatch(expected) is None:
        raise HumanAdjudicationError(f"{label} configured SHA-256 is invalid.")
    if snapshot["sha256"] != expected:
        raise HumanAdjudicationError(f"{label} hash changed.")


def _require_positive_int(value: object, label: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if type(value) is not int or not minimum <= value <= MAX_COUNT:
        raise HumanAdjudicationError(f"{label} is invalid.")
    return value


def _exact_keys(value: object, keys: Iterable[str], label: str) -> Mapping[str, Any]:
    expected = set(keys)
    if not isinstance(value, Mapping) or set(value) != expected:
        raise HumanAdjudicationError(f"{label} schema changed.")
    return value


def _strict_utc(value: object) -> bool:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _timestamp_directory(value: str) -> str:
    if not _strict_utc(value):
        raise HumanAdjudicationError("The workspace creation time is not strict UTC.")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    return parsed.strftime("%Y%m%dT%H%M%S.%fZ")


def _write_private_at(
    root_descriptor: int,
    relative: str,
    payload: bytes,
) -> dict[str, Any]:
    """Create and durably verify one private file beneath an anchored fd."""
    parent_descriptor: int | None = None
    descriptor: int | None = None
    identity: tuple[int, int] | None = None
    completed = False
    try:
        parent_descriptor, name = _open_relative_parent_at(
            root_descriptor, relative, "Private workspace file"
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(name, flags, 0o600, dir_fd=parent_descriptor)
        os.fchmod(descriptor, 0o600)
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise HumanAdjudicationError(
                    "A private workspace write made no progress."
                )
            view = view[written:]
        os.fsync(descriptor)
        current = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (
            not stat.S_ISREG(current.st_mode)
            or stat.S_IMODE(current.st_mode) != 0o600
            or current.st_nlink != 1
            or current.st_size != len(payload)
            or not _same_open_snapshot(current, named)
        ):
            raise HumanAdjudicationError(
                "A generated private workspace file is unsafe."
            )
        os.fsync(parent_descriptor)
        completed = True
        return {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "mode": "0600",
        }
    except HumanAdjudicationError:
        raise
    except OSError:
        raise HumanAdjudicationError(
            "A private workspace file could not be created safely."
        ) from None
    finally:
        if descriptor is not None:
            if not completed and identity is not None:
                try:
                    os.ftruncate(descriptor, 0)
                    os.fsync(descriptor)
                except OSError:
                    pass
            os.close(descriptor)
        if parent_descriptor is not None:
            if not completed and identity is not None:
                try:
                    _unlink_file_if_identity_at(
                        parent_descriptor, name, identity
                    )
                    os.fsync(parent_descriptor)
                except OSError:
                    pass
            os.close(parent_descriptor)


def _write_ndjson_at(
    root_descriptor: int,
    relative: str,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return _write_private_at(
        root_descriptor,
        relative,
        b"".join(_json_line(record) for record in records),
    )


def _write_private(path: Path, payload: bytes) -> dict[str, Any]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    parent_descriptor: int | None = None
    identity: tuple[int, int] | None = None
    try:
        parent_descriptor, name, _ = _open_parent_fd(path)
        descriptor = os.open(
            name, flags, 0o600, dir_fd=parent_descriptor
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            current = os.fstat(handle.fileno())
            identity = (current.st_dev, current.st_ino)
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        if parent_descriptor is not None:
            try:
                os.unlink(path.name, dir_fd=parent_descriptor)
            except OSError:
                pass
        raise
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)
            parent_descriptor = None
    snapshot = _snapshot_file(path, "A generated private workspace file")
    if (
        snapshot["mode"] != 0o600
        or snapshot["nlink"] != 1
        or snapshot["identity"] != identity
    ):
        try:
            parent_descriptor, name, _ = _open_parent_fd(path)
            os.unlink(name, dir_fd=parent_descriptor)
        except (HumanAdjudicationError, OSError):
            pass
        finally:
            if parent_descriptor is not None:
                os.close(parent_descriptor)
                parent_descriptor = None
        raise HumanAdjudicationError("A generated private file has an unsafe identity or mode.")
    return {"sha256": snapshot["sha256"], "bytes": snapshot["bytes"], "mode": "0600"}


def _write_ndjson(path: Path, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return _write_private(path, b"".join(_json_line(record) for record in records))


def _read_ndjson_payload(raw: bytes, label: str) -> list[Mapping[str, Any]]:
    if not raw or not raw.endswith(b"\n"):
        raise HumanAdjudicationError(f"{label} must be newline-terminated NDJSON.")
    output: list[Mapping[str, Any]] = []
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b"\n") or len(line) > MAX_JSON_LINE_BYTES:
            raise HumanAdjudicationError(f"{label} contains an invalid line boundary.")
        value = _json_loads(line[:-1], label)
        if not isinstance(value, Mapping):
            raise HumanAdjudicationError(f"{label} contains a non-object record.")
        output.append(value)
    return output


def _read_ndjson_snapshot(snapshot: Mapping[str, Any], label: str) -> list[Mapping[str, Any]]:
    raw = snapshot.get("payload")
    if not isinstance(raw, bytes):
        raise HumanAdjudicationError(f"{label} payload is unavailable.")
    return _read_ndjson_payload(raw, label)


def _decompress_one_gzip(stored: bytes, label: str) -> bytes:
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        raw = decompressor.decompress(stored) + decompressor.flush()
    except zlib.error:
        raise HumanAdjudicationError(f"{label} is not one valid gzip member.") from None
    if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
        raise HumanAdjudicationError(f"{label} is concatenated or truncated gzip.")
    return raw


def _bundle(root: Path, paths: Sequence[str]) -> dict[str, Any]:
    digest = hashlib.sha256()
    files: list[dict[str, Any]] = []
    snapshots: dict[str, dict[str, Any]] = {}
    for relative_text in paths:
        path = _project_path(root, relative_text, "implementation")
        snapshot = _snapshot_file(path, "An implementation file", retain_payload=True)
        content = snapshot["payload"]
        assert isinstance(content, bytes)
        encoded_path = relative_text.encode("utf-8")
        digest.update(struct.pack(">I", len(encoded_path)))
        digest.update(encoded_path)
        digest.update(struct.pack(">Q", len(content)))
        digest.update(content)
        files.append({
            "path": relative_text,
            "sha256": snapshot["sha256"],
            "bytes": snapshot["bytes"],
        })
        snapshots[relative_text] = snapshot
    return {
        "encoding": BUNDLE_ENCODING,
        "paths": list(paths),
        "bundle_sha256": digest.hexdigest(),
        "files": files,
        "_snapshots": snapshots,
    }


def _git_ignored(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", str(relative)],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _local_index_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    evidence = config.get("evidence_registry")
    source = config.get("source_artifact")
    if not isinstance(evidence, Mapping) or not isinstance(source, Mapping):
        raise HumanAdjudicationError("The local-evidence index contract is absent.")
    value = evidence.get("local_tuple_index")
    local_source = source.get("local_evidence")
    expected_keys = {
        "file",
        "encoding",
        "source_local_evidence_raw_sha256",
        "record_bytes",
        "index_records",
        "index_bytes",
        "index_sha256",
        "all_stage_kind_order",
        "all_stage_kind_ordinal_counts",
        "bridge_stage_kind_order",
        "bridge_block_offsets",
        "bridge_block_counts",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != expected_keys
        or not isinstance(local_source, Mapping)
        or value.get("file") != LOCAL_EVIDENCE_INDEX_FILE
        or value.get("encoding") != LOCAL_EVIDENCE_INDEX_ENCODING
        or value.get("source_local_evidence_raw_sha256")
        != local_source.get("raw_sha256")
        or value.get("record_bytes") != LOCAL_EVIDENCE_INDEX_RECORD_BYTES
        or not isinstance(value.get("index_sha256"), str)
        or SHA256_RE.fullmatch(value["index_sha256"]) is None
        or value.get("all_stage_kind_order") != list(SOURCE_LOCAL_STAGE_KIND_ORDER)
        or value.get("bridge_stage_kind_order")
        != list(SOURCE_BRIDGE_STAGE_KIND_ORDER)
    ):
        raise HumanAdjudicationError("The local-evidence index contract changed.")
    counts = value.get("all_stage_kind_ordinal_counts")
    offsets = value.get("bridge_block_offsets")
    bridge_counts = value.get("bridge_block_counts")
    if (
        not isinstance(counts, list)
        or len(counts) != len(SOURCE_LOCAL_STAGE_KIND_ORDER)
        or any(type(item) is not int or item < 0 for item in counts)
        or sum(counts) != local_source.get("unique_tuples")
        or not isinstance(offsets, list)
        or not isinstance(bridge_counts, list)
        or len(offsets) != len(SOURCE_BRIDGE_STAGE_KIND_ORDER)
        or len(bridge_counts) != len(SOURCE_BRIDGE_STAGE_KIND_ORDER)
        or any(type(item) is not int or item < 0 for item in offsets)
        or any(type(item) is not int or item < 0 for item in bridge_counts)
    ):
        raise HumanAdjudicationError("The local-evidence index cardinalities changed.")
    all_counts = dict(zip(SOURCE_LOCAL_STAGE_KIND_ORDER, counts, strict=True))
    expected_bridge_counts = [
        all_counts[stage_kind] for stage_kind in SOURCE_BRIDGE_STAGE_KIND_ORDER
    ]
    running = 0
    expected_offsets: list[int] = []
    for count in expected_bridge_counts:
        expected_offsets.append(running)
        running += count
    if (
        bridge_counts != expected_bridge_counts
        or offsets != expected_offsets
        or value.get("index_records") != running
        or value.get("index_bytes") != running * LOCAL_EVIDENCE_INDEX_RECORD_BYTES
    ):
        raise HumanAdjudicationError("The local-evidence index block layout changed.")
    return {
        **dict(value),
        "kind_counts": all_counts,
        "bridge_blocks": {
            stage_kind: (offset, count)
            for stage_kind, offset, count in zip(
                SOURCE_BRIDGE_STAGE_KIND_ORDER,
                offsets,
                bridge_counts,
                strict=True,
            )
        },
    }


def _load_contract(root: Path, config_path: Path, *, allow_proposed: bool) -> dict[str, Any]:
    path = _project_path(root, config_path.as_posix(), "component config")
    config_snapshot = _snapshot_file(path, "The human-adjudication config", retain_payload=True)
    try:
        config = tomllib.loads(config_snapshot["payload"].decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise HumanAdjudicationError("The human-adjudication config is invalid TOML.") from None
    if config.get("schema_version") != 1 or config.get("component_id") != COMPONENT_ID:
        raise HumanAdjudicationError("The human-adjudication component identity changed.")
    status = config.get("status")
    proposed = status == "proposed"
    if proposed:
        if not allow_proposed or config.get("execution_permitted") is not False:
            raise HumanAdjudicationError(
                "The proposed component requires an explicit structural-preview override."
            )
    elif status not in {"frozen", "frozen_for_execution"} or config.get("execution_permitted") is not True:
        raise HumanAdjudicationError("The human-adjudication execution gate is closed.")

    source = config.get("source_artifact")
    workspace = config.get("workspace")
    semantic = config.get("semantic_review")
    route = config.get("route_review")
    groups = config.get("mapping_groups")
    revisions = config.get("revisions")
    review_writer = config.get("review_writer")
    human = config.get("human_review_policy")
    ndc = config.get("ndc_decision")
    closure = config.get("snapshot_closure")
    implementation = config.get("implementation")
    guards = config.get("guards")
    evidence = config.get("evidence_registry")
    workspace_state = config.get("workspace_state")
    preview = config.get("structural_preview")
    final_outputs = config.get("final_outputs")
    sections = (
        source, workspace, semantic, route, groups, revisions, review_writer,
        human, ndc,
        closure, implementation, guards, evidence, workspace_state, preview,
        final_outputs,
    )
    if not all(isinstance(item, Mapping) for item in sections):
        raise HumanAdjudicationError("The human-adjudication config lacks a required section.")
    if (
        type(final_outputs.get("audit_checks_total")) is not int
        or final_outputs.get("audit_checks_total") != 18
    ):
        raise HumanAdjudicationError(
            "The independent final-audit check-count contract changed."
        )

    required_workspace = {
        "semantic_id_format": "S%06d",
        "route_id_format": "R%06d",
        "id_sequence_starts_at": 1,
        "ids_are_private_references_not_canonical_keys": True,
        "batch_assignment": "source-template-order contiguous fixed-size partition",
        "immutable_source_views_separate_from_editable_decision_ledgers": True,
        "each_editable_batch_binds_immutable_base_sha256": True,
        "batch_overlap_allowed": False,
        "batch_omission_allowed": False,
        "last_write_wins_allowed": False,
        "immutable_source_fields_may_be_edited": False,
        "private_directory_mode": "0700",
        "private_file_mode": "0600",
        "git_ignored_required": True,
        "public_raw_values_allowed": False,
        "public_per_value_hashes_allowed": False,
        "stdout_raw_values_allowed": False,
        "strict_workspace_inventory_required": True,
    }
    for key, expected in required_workspace.items():
        if workspace.get(key) != expected:
            raise HumanAdjudicationError(f"workspace.{key} contract changed.")
    _require_positive_int(workspace.get("semantic_batch_size"), "semantic batch size")
    _require_positive_int(workspace.get("semantic_batch_count"), "semantic batch count")
    if workspace.get("route_batch_count") != 1:
        raise HumanAdjudicationError("The route batch count changed.")
    expected_top_level = {
        "workspace-manifest.json",
        "workspace-events.jsonl",
        "semantic-source",
        "semantic-decisions",
        "semantic-groups",
        "route-source",
        "route-decisions",
        "evidence-registry",
        "attestations",
        "revisions",
    }
    if set(workspace.get("allowed_top_level_entries", [])) != expected_top_level:
        raise HumanAdjudicationError("The strict workspace top-level inventory changed.")
    if dict(preview) != STRUCTURAL_PREVIEW_POLICY:
        raise HumanAdjudicationError("The structural-preview isolation policy changed.")
    if dict(review_writer) != REVIEW_WRITER_POLICY:
        raise HumanAdjudicationError("The human review-writer contract changed.")
    if semantic.get("dimensions") != list(SEMANTIC_DIMENSIONS):
        raise HumanAdjudicationError("The semantic dimension order changed.")
    if (
        semantic.get("status_values") != list(SEMANTIC_STATUSES)
        or semantic.get("review_status_values") != list(REVIEW_STATUSES)
        or semantic.get("initial_status") != "uncertain"
        or semantic.get("initial_review_status") != "unreviewed"
        or semantic.get("software_may_set_reviewed") is not False
        or semantic.get("llm_may_set_reviewed") is not False
    ):
        raise HumanAdjudicationError("The semantic human-review gate changed.")
    semantic_values = semantic.get("values")
    if not isinstance(semantic_values, Mapping):
        raise HumanAdjudicationError("The semantic value contract is absent.")
    for dimension in SEMANTIC_DIMENSIONS:
        value_contract = semantic_values.get(dimension)
        if not isinstance(value_contract, Mapping):
            raise HumanAdjudicationError("A semantic controlled-value contract is absent.")
        for state in SEMANTIC_STATUSES:
            code = value_contract.get(state + "_code")
            if not isinstance(code, str) or not code:
                raise HumanAdjudicationError("A semantic controlled-value code is invalid.")
    if (
        route.get("decision_values") != list(ROUTE_DECISIONS)
        or route.get("review_status_values") != list(REVIEW_STATUSES)
        or route.get("initial_decision") != "unknown"
        or route.get("initial_review_status") != "unreviewed"
        or route.get("allowed_decision_bases") != list(ROUTE_BASES)
        or route.get("sql_null_route_state") != "missing"
        or route.get("sql_null_requires_human_review") is not False
        or route.get("source_specific_override_allowed") is not False
        or route.get("software_may_set_reviewed") is not False
        or route.get("llm_may_set_reviewed") is not False
    ):
        raise HumanAdjudicationError("The route human-review gate changed.")
    if (
        groups.get("minimum_members") != 2
        or groups.get("member_set_must_equal_key_assignments") is not True
        or revisions.get("append_only") is not True
        or revisions.get("active_revision_per_item") != 1
        or revisions.get("supersedes_sha256_required_after_first_revision") is not True
        or revisions.get("last_write_wins_allowed") is not False
        or human.get("batch_attestation_required") is not True
        or human.get("automated_attestation_allowed") is not False
        or human.get("reviewer_model")
        != "single_reviewer_with_full_attestation"
        or human.get("allowed_models")
        != [
            "single_reviewer_with_full_attestation",
            "dual_independent_with_conflict_adjudication",
        ]
        or human.get(
            "single_reviewer_identity_must_match_all_item_group_revision_and_batch_attestation_records"
        ) is not True
        or human.get("dual_review_requires_new_component_version") is not True
    ):
        raise HumanAdjudicationError("The revision, group, or attestation contract changed.")
    local_policy = evidence.get("local_tuple")
    if (
        not isinstance(local_policy, Mapping)
        or set(local_policy) != {
            "allowed_stage_kind",
            "ordinal_is_one_based_within_stage_kind_data_records",
            "must_resolve_to_exact_record_in_bound_local_evidence_stream",
            "ordinary_decision_relevance_is_human_judgment_not_structural_validation",
        }
        or local_policy.get("allowed_stage_kind")
        != list(GENERAL_LOCAL_STAGE_KINDS)
        or local_policy.get(
            "ordinal_is_one_based_within_stage_kind_data_records"
        ) is not True
        or local_policy.get(
            "must_resolve_to_exact_record_in_bound_local_evidence_stream"
        ) is not True
        or local_policy.get(
            "ordinary_decision_relevance_is_human_judgment_not_structural_validation"
        ) is not True
    ):
        raise HumanAdjudicationError("The general local-tuple evidence policy changed.")
    group_local_policy = groups.get("local_evidence_eligibility")
    if (
        not isinstance(group_local_policy, Mapping)
        or group_local_policy.get("allowed_stage_kind")
        != list(GROUP_LOCAL_STAGE_KINDS)
        or group_local_policy.get(
            "group_member_set_must_be_subset_of_one_tuple_nonnull_semantic_membership_set"
        ) is not True
        or group_local_policy.get(
            "group_membership_requires_human_identity_evidence_beyond_cooccurrence"
        ) is not True
        or group_local_policy.get(
            "local_tuple_ordinal_is_one_based_within_stage_kind_data_records"
        ) is not True
        or group_local_policy.get("unsupported_or_unlinked_group_fails_closed")
        is not True
    ):
        raise HumanAdjudicationError("The mapping-group local-evidence policy changed.")
    _local_index_contract(config)
    expected_workspace_state = {
        "event_log_file": "workspace-events.jsonl",
        "event_log_append_only": True,
        "event_log_canonical_serialization": (
            "canonical-json-utf8-sort-keys-no-whitespace-v1"
        ),
        "allowed_events": list(WORKSPACE_EVENT_TYPES),
        "state_is_derived_from_validated_event_log_and_current_active_revision_set": True,
        "configuration_execution_status_is_not_rewritten": True,
        "failed_validation_never_advances_state": True,
        "resume_requires_revalidation_of_all_active_inputs": True,
        "abandoned_workspace_cannot_be_reactivated": True,
        "revision_event_log": REVISION_EVENT_LOG_POLICY,
        "workspace_event_log": WORKSPACE_EVENT_LOG_POLICY,
        "active_state_hash": ACTIVE_STATE_HASH_POLICY,
    }
    if dict(workspace_state) != expected_workspace_state:
        raise HumanAdjudicationError("The append-only workspace-state policy changed.")
    required_closure_true = (
        "two_pass_required_for_validation_and_compile",
        "compare_device_inode_mode_size_sha256",
        "source_public_files_included",
        "source_semantic_route_and_local_evidence_files_included",
        "workspace_local_evidence_index_included",
        "test_attestation_and_test_files_included",
        "ndc_decision_config_included",
        "all_batch_and_group_files_included",
        "config_and_implementation_bundles_included",
        "in_place_mutation_fails_closed",
    )
    if any(closure.get(key) is not True for key in required_closure_true) or closure.get("symlink_input_allowed") is not False:
        raise HumanAdjudicationError("The global snapshot-closure contract changed.")
    if any(value is not False for value in guards.values()):
        raise HumanAdjudicationError("A downstream scientific guard was enabled.")

    configured_paths = implementation.get("generator_paths")
    if implementation.get("bundle_encoding") != BUNDLE_ENCODING or configured_paths != list(GENERATOR_PATHS):
        raise HumanAdjudicationError("The generator bundle contract changed.")
    bundle = _bundle(root, GENERATOR_PATHS)
    configured_bundle = implementation.get("generator_bundle_sha256")
    if proposed:
        if configured_bundle != PLACEHOLDER and configured_bundle != bundle["bundle_sha256"]:
            raise HumanAdjudicationError("The proposed generator bundle hash is inconsistent.")
    elif configured_bundle != bundle["bundle_sha256"]:
        raise HumanAdjudicationError("The frozen generator bundle hash changed.")

    return {
        "root": root,
        "config": config,
        "path": path,
        "snapshot": config_snapshot,
        "config_sha256": config_snapshot["sha256"],
        "proposed": proposed,
        "bundle": bundle,
    }


def _validate_public_json(snapshot: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    raw = snapshot.get("payload")
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_JSON_FILE_BYTES:
        raise HumanAdjudicationError(f"{label} has an invalid size.")
    value = _json_loads(raw, label)
    if not isinstance(value, Mapping):
        raise HumanAdjudicationError(f"{label} must contain one object.")
    return value


def _artifact_file(directory: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).name != value:
        raise HumanAdjudicationError(f"{label} filename is unsafe.")
    return directory / value


def _source_inventory(root: Path, contract: Mapping[str, Any]) -> dict[str, Any]:
    config = contract["config"]
    source = config["source_artifact"]
    directory = _project_path(root, source.get("directory"), "source artifact")
    directory_snapshot = _snapshot_directory(directory, "The source artifact directory")
    if directory_snapshot["mode"] != 0o700:
        raise HumanAdjudicationError("The source artifact directory mode is unsafe.")
    if source.get("component_id") != SOURCE_COMPONENT_ID:
        raise HumanAdjudicationError("The source component identity changed.")

    specifications = {
        "source_config": (
            _project_path(root, source.get("source_config_path"), "source config"),
            source.get("source_config_sha256"),
            True,
        ),
        "manifest": (
            _artifact_file(directory, source.get("manifest_file"), "source manifest"),
            source.get("manifest_sha256"),
            True,
        ),
        "aggregate_summary": (
            _artifact_file(directory, source.get("aggregate_summary_file"), "source aggregate summary"),
            source.get("aggregate_summary_sha256"),
            True,
        ),
        "audit": (
            _artifact_file(directory, source.get("audit_file"), "source audit"),
            source.get("audit_sha256"),
            True,
        ),
        "semantic_template": (
            _artifact_file(directory, source["semantic_template"].get("file"), "semantic template"),
            source["semantic_template"].get("stored_sha256"),
            True,
        ),
        "route_template": (
            _artifact_file(directory, source["route_template"].get("file"), "route template"),
            source["route_template"].get("stored_sha256"),
            True,
        ),
        "local_evidence": (
            _artifact_file(directory, source["local_evidence"].get("file"), "local evidence"),
            source["local_evidence"].get("stored_sha256"),
            False,
        ),
    }
    snapshots: dict[str, dict[str, Any]] = {}
    for key, (path, expected_hash, retain) in specifications.items():
        snapshot = _snapshot_file(path, f"The source {key}", retain_payload=retain)
        _require_hash(snapshot, expected_hash, f"The source {key}")
        if path.parent == directory and (
            snapshot["mode"] != 0o600 or snapshot["nlink"] != 1
        ):
            raise HumanAdjudicationError(
                f"The source {key} mode or link count is unsafe."
            )
        section = source.get(key)
        if key in {"semantic_template", "route_template", "local_evidence"}:
            assert isinstance(section, Mapping)
            if snapshot["bytes"] != section.get("stored_bytes"):
                raise HumanAdjudicationError(f"The source {key} size changed.")
        snapshots[key] = {**snapshot, "path": path}

    manifest = _validate_public_json(snapshots["manifest"], "The source manifest")
    summary = _validate_public_json(snapshots["aggregate_summary"], "The source aggregate summary")
    audit = _validate_public_json(snapshots["audit"], "The source audit")
    outputs = manifest.get("outputs")
    conservation = manifest.get("conservation")
    if (
        manifest.get("component_id") != SOURCE_COMPONENT_ID
        or manifest.get("status") != "complete"
        or not isinstance(outputs, Mapping)
        or not isinstance(conservation, Mapping)
        or audit.get("status") != source.get("audit_status")
    ):
        raise HumanAdjudicationError("The source public lineage is incomplete.")
    audit_checks = audit.get("checks")
    if not isinstance(audit_checks, Mapping) or audit_checks.get("failed") != source.get("audit_failed_checks"):
        raise HumanAdjudicationError("The source independent audit has failures.")
    expected_output_names = {
        "semantic_review_template": "semantic_template",
        "route_review_template": "route_template",
        "local_evidence": "local_evidence",
    }
    for output_key, section_key in expected_output_names.items():
        declared = outputs.get(output_key)
        expected = source[section_key]
        if not isinstance(declared, Mapping) or any(
            declared.get(left) != expected.get(right)
            for left, right in (
                ("file", "file"),
                ("sha256", "stored_sha256"),
                ("bytes", "stored_bytes"),
                ("raw_sha256", "raw_sha256"),
                ("raw_bytes", "raw_bytes"),
                ("records", "records"),
            )
        ):
            raise HumanAdjudicationError(f"The source {section_key} manifest binding changed.")
    if (
        conservation.get("semantic_review_keys") != source["semantic_template"].get("semantic_keys")
        or conservation.get("semantic_seed_key_set_sha256") != source["semantic_template"].get("semantic_key_set_sha256")
        or conservation.get("route_canonical_exact_nonnull_values") != source["route_template"].get("canonical_exact_nonnull_values")
        or conservation.get("route_source_specific_nonnull_memberships") != source["route_template"].get("source_specific_nonnull_memberships")
        or conservation.get("route_source_specific_sql_null_memberships") != source["route_template"].get("source_specific_sql_null_memberships")
        or conservation.get("route_source_specific_typed_memberships") != source["route_template"].get("source_specific_typed_memberships")
    ):
        raise HumanAdjudicationError("The source conservation declaration changed.")
    if not isinstance(summary, Mapping):  # kept explicit for the closure contract
        raise HumanAdjudicationError("The source aggregate summary is invalid.")

    ndc_cfg = config["ndc_decision"]
    ndc_path = _project_path(root, ndc_cfg.get("config_path"), "NDC decision config")
    ndc_snapshot = _snapshot_file(ndc_path, "The NDC decision config", retain_payload=True)
    _require_hash(ndc_snapshot, ndc_cfg.get("config_sha256"), "The NDC decision config")
    try:
        ndc = tomllib.loads(ndc_snapshot["payload"].decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise HumanAdjudicationError("The NDC decision config is invalid.") from None
    decision = ndc.get("decision")
    if (
        ndc.get("component_id") != NDC_COMPONENT_ID
        or ndc.get("status") != ndc_cfg.get("required_status")
        or not isinstance(decision, Mapping)
        or decision.get("mode") != ndc_cfg.get("required_mode")
        or decision.get("effective") is not ndc_cfg.get("required_effective")
        or ndc_cfg.get("ndc_handoff_rows_may_be_read") is not False
    ):
        raise HumanAdjudicationError("The frozen NDC non-use decision changed.")
    snapshots["ndc_config"] = {**ndc_snapshot, "path": ndc_path}
    return {
        "directory": directory,
        "directory_snapshot": directory_snapshot,
        "snapshots": snapshots,
        "manifest": manifest,
    }


def _finish_source_closure(source_inventory: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    directory = source_inventory["directory"]
    final_directory = _snapshot_directory(directory, "The source artifact directory")
    if _directory_seal(final_directory) != _directory_seal(source_inventory["directory_snapshot"]):
        raise HumanAdjudicationError("The source artifact directory changed during the operation.")
    for key, initial in source_inventory["snapshots"].items():
        final = _snapshot_file(initial["path"], f"The source {key}")
        if _seal(final) != _seal(initial):
            raise HumanAdjudicationError(f"The source {key} changed during the operation.")
    final_config = _snapshot_file(contract["path"], "The human-adjudication config")
    if _seal(final_config) != _seal(contract["snapshot"]):
        raise HumanAdjudicationError("The human-adjudication config changed during the operation.")
    for relative, initial in contract["bundle"]["_snapshots"].items():
        final = _snapshot_file(
            _project_path(contract["root"], relative, "implementation"),
            "An implementation file",
        )
        if _seal(final) != _seal(initial):
            raise HumanAdjudicationError("The generator implementation changed during the operation.")


def _stream_records(
    snapshot: Mapping[str, Any], section: Mapping[str, Any], label: str
) -> list[Mapping[str, Any]]:
    stored = snapshot.get("payload")
    if not isinstance(stored, bytes):
        raise HumanAdjudicationError(f"{label} payload is unavailable.")
    raw = _decompress_one_gzip(stored, label)
    if (
        len(raw) != section.get("raw_bytes")
        or hashlib.sha256(raw).hexdigest() != section.get("raw_sha256")
    ):
        raise HumanAdjudicationError(f"{label} raw stream hash or size changed.")
    records = _read_ndjson_payload(raw, label)
    if len(records) != section.get("records"):
        raise HumanAdjudicationError(f"{label} record count changed.")
    return records


def _semantic_set_hash(items: Sequence[Mapping[str, Any]]) -> str:
    keys = sorted(
        ((item["source_field"].encode("utf-8"), item["exact_raw_value"].encode("utf-8")) for item in items),
    )
    if len(keys) != len(set(keys)):
        raise HumanAdjudicationError("The semantic source contains duplicate exact keys.")
    digest = hashlib.sha256(SEMANTIC_SET_VERSION)
    digest.update(struct.pack(">Q", len(keys)))
    for field, raw in keys:
        digest.update(struct.pack(">I", len(field)))
        digest.update(field)
        digest.update(struct.pack(">Q", len(raw)))
        digest.update(raw)
    return digest.hexdigest()


def _route_set_hash(items: Sequence[Mapping[str, Any]]) -> str:
    values = sorted(item["exact_raw_value"].encode("utf-8") for item in items)
    if len(values) != len(set(values)):
        raise HumanAdjudicationError("The route source contains duplicate canonical values.")
    digest = hashlib.sha256(ROUTE_SET_VERSION)
    digest.update(struct.pack(">Q", len(values)))
    for raw in values:
        digest.update(struct.pack(">Q", len(raw)))
        digest.update(raw)
    return digest.hexdigest()


def _parse_semantic_template(records: Sequence[Mapping[str, Any]], section: Mapping[str, Any]) -> list[dict[str, Any]]:
    expected_count = _require_positive_int(section.get("semantic_keys"), "semantic key count")
    if len(records) != expected_count + 4:
        raise HumanAdjudicationError("The semantic template framing count changed.")
    if records[0].get("record_type") != "header":
        raise HumanAdjudicationError("The semantic template header changed.")
    begin = _exact_keys(
        records[1],
        {"record_type", "key_count", "key_set_sha256", "semantic_dimensions"},
        "semantic template begin",
    )
    if (
        begin["record_type"] != "semantic_review_begin"
        or begin["key_count"] != expected_count
        or begin["key_set_sha256"] != section.get("semantic_key_set_sha256")
        or begin["semantic_dimensions"] != list(SEMANTIC_DIMENSIONS)
    ):
        raise HumanAdjudicationError("The semantic template declaration changed.")
    items: list[dict[str, Any]] = []
    previous: tuple[bytes, bytes] | None = None
    item_keys = {
        "record_type", "source_field", "exact_raw_value", "exact_row_count",
        "review_status", "semantic_decisions", "mapping_group_id",
        "decision_basis", "reviewer_id", "reviewed_at_utc",
    }
    for index, raw_record in enumerate(records[2:-2], start=1):
        record = _exact_keys(raw_record, item_keys, "semantic template item")
        source_field = record["source_field"]
        raw_value = record["exact_raw_value"]
        if not isinstance(source_field, str) or not source_field or not isinstance(raw_value, str):
            raise HumanAdjudicationError("A semantic exact key is malformed.")
        encoded = raw_value.encode("utf-8")
        if b"\x00" in encoded or len(encoded) > MAX_VALUE_UTF8_BYTES:
            raise HumanAdjudicationError("A semantic exact value violates its byte contract.")
        order = (source_field.encode("utf-8"), encoded)
        if previous is not None and order <= previous:
            raise HumanAdjudicationError("The semantic exact keys are not strictly ordered.")
        previous = order
        count = _require_positive_int(record["exact_row_count"], "semantic exact-row count")
        if (
            record["review_status"] != "unreviewed"
            or record["semantic_decisions"] != {key: "uncertain" for key in SEMANTIC_DIMENSIONS}
            or any(record[key] is not None for key in ("mapping_group_id", "decision_basis", "reviewer_id", "reviewed_at_utc"))
        ):
            raise HumanAdjudicationError("The source semantic template contains a decision.")
        items.append({
            "record_type": "semantic_source_item",
            "review_id": f"S{index:06d}",
            "source_field": source_field,
            "exact_raw_value": raw_value,
            "exact_row_count": count,
        })
    end = _exact_keys(records[-2], {"record_type", "records", "key_set_sha256"}, "semantic template end")
    footer = _exact_keys(records[-1], {"record_type", "records_before_footer", "section_counts"}, "semantic template footer")
    if (
        end["record_type"] != "semantic_review_end"
        or end["records"] != expected_count
        or end["key_set_sha256"] != section.get("semantic_key_set_sha256")
        or footer["record_type"] != "footer"
        or footer["records_before_footer"] != len(records) - 1
        or footer["section_counts"] != {"semantic_review_keys": expected_count}
        or _semantic_set_hash(items) != section.get("semantic_key_set_sha256")
    ):
        raise HumanAdjudicationError("The semantic template conservation check failed.")
    return items


def _parse_route_template(
    records: Sequence[Mapping[str, Any]], section: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    canonical_count = _require_positive_int(section.get("canonical_exact_nonnull_values"), "route canonical count")
    membership_count = _require_positive_int(section.get("source_specific_typed_memberships"), "route membership count")
    if len(records) != canonical_count + membership_count + 4 or records[0].get("record_type") != "header":
        raise HumanAdjudicationError("The route template framing changed.")
    begin = _exact_keys(
        records[1],
        {
            "record_type", "canonical_exact_nonnull_values",
            "source_specific_nonnull_memberships",
            "source_specific_sql_null_memberships",
            "source_specific_typed_memberships", "typed_set_sha256",
        },
        "route template begin",
    )
    if (
        begin["record_type"] != "route_review_begin"
        or any(
            begin[key] != section.get(key)
            for key in (
                "canonical_exact_nonnull_values",
                "source_specific_nonnull_memberships",
                "source_specific_sql_null_memberships",
                "source_specific_typed_memberships",
            )
        )
        or not isinstance(begin["typed_set_sha256"], Mapping)
    ):
        raise HumanAdjudicationError("The route template declaration changed.")
    canonical: list[dict[str, Any]] = []
    canonical_by_id: dict[str, str] = {}
    canonical_keys = {
        "record_type", "canonical_review_id", "exact_raw_value", "raw_utf8_bytes",
        "decision", "review_status", "decision_basis", "reviewer_id", "reviewed_at_utc",
    }
    previous_value: bytes | None = None
    offset = 2
    for index, raw_record in enumerate(records[offset:offset + canonical_count], start=1):
        record = _exact_keys(raw_record, canonical_keys, "canonical route template item")
        review_id = f"R{index:06d}"
        value = record["exact_raw_value"]
        if record["canonical_review_id"] != review_id or not isinstance(value, str):
            raise HumanAdjudicationError("A canonical route identity changed.")
        encoded = value.encode("utf-8")
        if b"\x00" in encoded or len(encoded) > MAX_VALUE_UTF8_BYTES or record["raw_utf8_bytes"] != len(encoded):
            raise HumanAdjudicationError("A canonical route value violates its byte contract.")
        if previous_value is not None and encoded <= previous_value:
            raise HumanAdjudicationError("Canonical route values are not strictly ordered.")
        previous_value = encoded
        if (
            record["decision"] != "unknown"
            or record["review_status"] != "unreviewed"
            or any(record[key] is not None for key in ("decision_basis", "reviewer_id", "reviewed_at_utc"))
        ):
            raise HumanAdjudicationError("The source route template contains a decision.")
        canonical.append({
            "record_type": "route_source_item",
            "review_id": review_id,
            "exact_raw_value": value,
            "raw_utf8_bytes": len(encoded),
        })
        canonical_by_id[review_id] = value

    membership_keys = {
        "record_type", "source_key", "source_field", "field_role", "raw_value_state",
        "exact_raw_value", "exact_row_count", "decision", "route_state",
        "sets_has_unknown", "decision_provenance", "canonical_review_id",
        "review_status", "decision_basis", "reviewer_id", "reviewed_at_utc",
    }
    memberships: list[dict[str, Any]] = []
    nonnull = nulls = 0
    seen_memberships: set[tuple[str, str, str | None]] = set()
    offset += canonical_count
    for raw_record in records[offset:offset + membership_count]:
        record = _exact_keys(raw_record, membership_keys, "route source membership")
        count = _require_positive_int(record["exact_row_count"], "route membership count")
        common = {
            "record_type": "route_source_membership",
            "source_key": record["source_key"],
            "source_field": record["source_field"],
            "field_role": record["field_role"],
            "raw_value_state": record["raw_value_state"],
            "exact_raw_value": record["exact_raw_value"],
            "exact_row_count": count,
            "canonical_review_id": record["canonical_review_id"],
        }
        if not all(isinstance(common[key], str) and common[key] for key in ("source_key", "source_field", "field_role")):
            raise HumanAdjudicationError("A route membership identity is invalid.")
        if record["raw_value_state"] == "nonnull":
            review_id = record["canonical_review_id"]
            value = record["exact_raw_value"]
            if (
                review_id not in canonical_by_id
                or value != canonical_by_id[review_id]
                or record["decision"] != "unknown"
                or record["route_state"] != "unknown"
                or record["sets_has_unknown"] is not True
                or record["decision_provenance"] != "default_unknown_unreviewed"
                or record["review_status"] != "unreviewed"
                or any(record[key] is not None for key in ("decision_basis", "reviewer_id", "reviewed_at_utc"))
            ):
                raise HumanAdjudicationError("A nonnull route membership is inconsistent.")
            nonnull += 1
            common["route_state"] = "unknown"
            common["sets_has_unknown"] = True
        elif record["raw_value_state"] == "sql_null":
            if (
                record["exact_raw_value"] is not None
                or record["canonical_review_id"] is not None
                or record["decision"] is not None
                or record["route_state"] != "missing"
                or record["sets_has_unknown"] is not False
                or record["decision_provenance"] != "forced_sql_null_policy"
                or record["review_status"] != "not_required"
                or record["decision_basis"] != "forced_sql_null_policy"
                or record["reviewer_id"] is not None
                or record["reviewed_at_utc"] is not None
            ):
                raise HumanAdjudicationError("A SQL-NULL route boundary is inconsistent.")
            nulls += 1
            common["route_state"] = "missing"
            common["sets_has_unknown"] = False
        else:
            raise HumanAdjudicationError("A route membership typed state is invalid.")
        identity = (common["source_field"], common["raw_value_state"], common["exact_raw_value"])
        if identity in seen_memberships:
            raise HumanAdjudicationError("The route source repeats a typed membership.")
        seen_memberships.add(identity)
        memberships.append(common)
    end = _exact_keys(records[-2], {"record_type", "canonical_records", "source_membership_records", "canonical_exact_set_sha256"}, "route template end")
    footer = _exact_keys(records[-1], {"record_type", "records_before_footer", "section_counts"}, "route template footer")
    if (
        nonnull != section.get("source_specific_nonnull_memberships")
        or nulls != section.get("source_specific_sql_null_memberships")
        or end["record_type"] != "route_review_end"
        or end["canonical_records"] != canonical_count
        or end["source_membership_records"] != membership_count
        or end["canonical_exact_set_sha256"] != section.get("canonical_exact_set_sha256")
        or footer["record_type"] != "footer"
        or footer["records_before_footer"] != len(records) - 1
        or footer["section_counts"] != {"canonical_route_reviews": canonical_count, "route_source_memberships": membership_count}
        or _route_set_hash(canonical) != section.get("canonical_exact_set_sha256")
    ):
        raise HumanAdjudicationError("The route template conservation check failed.")
    return canonical, memberships


def _build_local_evidence_index(
    destination_descriptor: int,
    destination_relative: str,
    source_inventory: Mapping[str, Any],
    config: Mapping[str, Any],
    semantic_items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Scan the frozen local stream once and write the immutable bridge index."""
    index = _local_index_contract(config)
    source_section = config["source_artifact"]["local_evidence"]
    semantic_lookup = {
        (item["source_field"], item["exact_raw_value"]): sequence
        for sequence, item in enumerate(semantic_items, start=1)
    }
    initial = source_inventory["snapshots"]["local_evidence"]
    path = initial["path"]
    descriptor: int | None = None
    parent_descriptor: int | None = None
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    raw_digest = hashlib.sha256()
    raw_bytes = compressed_bytes = record_count = tuple_count = multiplicity = 0
    line_buffer = bytearray()
    index_payload = bytearray()
    active_kind: tuple[str, str] | None = None
    active_count = 0
    kind_position = 0
    saw_header = False
    saw_footer = False

    def handle_record(record: Mapping[str, Any]) -> None:
        nonlocal active_kind, active_count, kind_position, saw_header, saw_footer
        nonlocal tuple_count, multiplicity
        record_type = record.get("record_type")
        if record_type == "header":
            if saw_header or active_kind is not None or kind_position or saw_footer:
                raise HumanAdjudicationError(
                    "The local-evidence header is misplaced during index creation."
                )
            saw_header = True
            return
        if record_type == "evidence_kind_begin":
            stage = record.get("stage")
            kind = record.get("tuple_kind")
            stage_kind = f"{stage}:{kind}"
            if (
                not saw_header
                or saw_footer
                or active_kind is not None
                or kind_position >= len(SOURCE_LOCAL_STAGE_KIND_ORDER)
                or stage_kind != SOURCE_LOCAL_STAGE_KIND_ORDER[kind_position]
            ):
                raise HumanAdjudicationError(
                    "A local-evidence kind boundary changed during index creation."
                )
            active_kind = (stage, kind)
            active_count = 0
            return
        if record_type == "evidence_tuple":
            if (
                active_kind is None
                or saw_footer
                or (record.get("stage"), record.get("tuple_kind")) != active_kind
            ):
                raise HumanAdjudicationError(
                    "A local-evidence tuple escaped its kind during index creation."
                )
            value_multiplicity = record.get("multiplicity")
            if type(value_multiplicity) is not int or value_multiplicity <= 0:
                raise HumanAdjudicationError(
                    "A local-evidence tuple has invalid multiplicity."
                )
            active_count += 1
            tuple_count += 1
            multiplicity += value_multiplicity
            bindings = LOCAL_SEMANTIC_BINDINGS.get(active_kind)
            if bindings is None:
                return
            value = record.get("tuple")
            if not isinstance(value, Mapping):
                raise HumanAdjudicationError(
                    "A bridge tuple is malformed during index creation."
                )
            members: set[int] = set()
            for tuple_field, source_field in bindings:
                if tuple_field not in value:
                    raise HumanAdjudicationError(
                        "A bridge tuple lacks a semantic field during index creation."
                    )
                raw_value = value[tuple_field]
                if raw_value is None:
                    continue
                if not isinstance(raw_value, str):
                    raise HumanAdjudicationError(
                        "A bridge tuple has a non-text semantic value."
                    )
                sequence = semantic_lookup.get((source_field, raw_value))
                if sequence is None:
                    raise HumanAdjudicationError(
                        "A bridge tuple escaped the frozen semantic universe."
                    )
                members.add(sequence)
            ordered = sorted(members)
            if len(ordered) > 4:
                raise HumanAdjudicationError(
                    "A bridge tuple cannot be encoded in the ordinal index."
                )
            index_payload.extend(
                struct.pack(">B4I", len(ordered), *(ordered + [0] * (4 - len(ordered))))
            )
            return
        if record_type == "evidence_kind_end":
            if (
                active_kind is None
                or (record.get("stage"), record.get("tuple_kind")) != active_kind
            ):
                raise HumanAdjudicationError(
                    "A local-evidence kind end changed during index creation."
                )
            stage_kind = f"{active_kind[0]}:{active_kind[1]}"
            if active_count != index["kind_counts"][stage_kind]:
                raise HumanAdjudicationError(
                    "A local-evidence kind count changed during index creation."
                )
            kind_position += 1
            active_kind = None
            active_count = 0
            return
        if record_type == "footer":
            if (
                not saw_header
                or saw_footer
                or active_kind is not None
                or kind_position != len(SOURCE_LOCAL_STAGE_KIND_ORDER)
            ):
                raise HumanAdjudicationError(
                    "The local-evidence footer is misplaced during index creation."
                )
            saw_footer = True
            return
        raise HumanAdjudicationError(
            "The local-evidence stream contains an unexpected record."
        )

    def consume(raw: bytes) -> None:
        nonlocal raw_bytes, record_count
        if not raw:
            return
        raw_digest.update(raw)
        raw_bytes += len(raw)
        line_buffer.extend(raw)
        while True:
            newline = line_buffer.find(b"\n")
            if newline < 0:
                if len(line_buffer) > MAX_JSON_LINE_BYTES:
                    raise HumanAdjudicationError(
                        "A local-evidence record exceeds its byte limit."
                    )
                break
            line = bytes(line_buffer[:newline])
            del line_buffer[: newline + 1]
            if len(line) + 1 > MAX_JSON_LINE_BYTES:
                raise HumanAdjudicationError(
                    "A local-evidence record exceeds its byte limit."
                )
            value = _json_loads(line, "The local-evidence stream")
            if not isinstance(value, Mapping):
                raise HumanAdjudicationError(
                    "The local-evidence stream contains a non-object."
                )
            record_count += 1
            handle_record(value)

    try:
        parent_descriptor, name, parent_chain = _open_parent_fd(path)
        if parent_chain != initial["parent_chain"]:
            raise HumanAdjudicationError(
                "The local-evidence parent changed before index creation."
            )
        flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or (before.st_dev, before.st_ino) != initial["identity"]
            or stat.S_IMODE(before.st_mode) != initial["mode"]
            or before.st_size != initial["bytes"]
        ):
            raise HumanAdjudicationError(
                "The local-evidence file changed before index creation."
            )
        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            compressed_bytes += len(chunk)
            try:
                consume(decompressor.decompress(chunk))
            except zlib.error:
                raise HumanAdjudicationError(
                    "The local-evidence gzip stream is invalid."
                ) from None
            if decompressor.unused_data or decompressor.unconsumed_tail:
                raise HumanAdjudicationError(
                    "The local-evidence gzip stream has extra members or tails."
                )
        try:
            consume(decompressor.flush())
        except zlib.error:
            raise HumanAdjudicationError(
                "The local-evidence gzip stream is invalid."
            ) from None
        after = os.fstat(descriptor)
        final_at_parent = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)
    final, final_parent_chain = _lstat_nofollow(path)
    payload_sha256 = hashlib.sha256(index_payload).hexdigest()
    if (
        not _same_open_snapshot(before, after)
        or not _same_open_snapshot(after, final_at_parent)
        or not _same_open_snapshot(final_at_parent, final)
        or parent_chain != final_parent_chain
        or compressed_bytes != initial["bytes"]
        or not decompressor.eof
        or decompressor.unused_data
        or decompressor.unconsumed_tail
        or line_buffer
        or active_kind is not None
        or not saw_header
        or not saw_footer
        or kind_position != len(SOURCE_LOCAL_STAGE_KIND_ORDER)
        or raw_bytes != source_section["raw_bytes"]
        or raw_digest.hexdigest() != source_section["raw_sha256"]
        or record_count != source_section["records"]
        or tuple_count != source_section["unique_tuples"]
        or multiplicity != source_section["total_multiplicity"]
        or len(index_payload) != index["index_bytes"]
        or payload_sha256 != index["index_sha256"]
    ):
        raise HumanAdjudicationError(
            "The local-evidence stream or derived index failed conservation."
        )
    meta = _write_private_at(
        destination_descriptor,
        destination_relative,
        bytes(index_payload),
    )
    return {
        **meta,
        "encoding": LOCAL_EVIDENCE_INDEX_ENCODING,
        "records": index["index_records"],
        "source_local_evidence_raw_sha256": source_section["raw_sha256"],
        "bridge_blocks": [
            {
                "stage_kind": stage_kind,
                "offset_records": index["bridge_blocks"][stage_kind][0],
                "records": index["bridge_blocks"][stage_kind][1],
            }
            for stage_kind in SOURCE_BRIDGE_STAGE_KIND_ORDER
        ],
    }


def _semantic_default_revision(
    review_id: str, semantic_config: Mapping[str, Any]
) -> dict[str, Any]:
    values = semantic_config["values"]
    return {
        "record_type": "semantic_decision_revision",
        "review_id": review_id,
        "revision": 1,
        "supersedes_sha256": None,
        "revision_reason": "workspace_initialization",
        "review_status": "unreviewed",
        "dimensions": {
            dimension: {
                "status": "uncertain",
                "value": {
                    "code": values[dimension]["uncertain_code"],
                    "candidates": [],
                },
                "evidence_refs": [],
                "uncertainty_basis": None,
            }
            for dimension in SEMANTIC_DIMENSIONS
        },
        "mapping_group_id": None,
        "rationale": None,
        "reviewer_id": None,
        "reviewed_at_utc": None,
    }


def _route_default_revision(review_id: str) -> dict[str, Any]:
    return {
        "record_type": "route_decision_revision",
        "review_id": review_id,
        "revision": 1,
        "supersedes_sha256": None,
        "revision_reason": "workspace_initialization",
        "review_status": "unreviewed",
        "decision": "unknown",
        "decision_basis": None,
        "evidence_refs": [],
        "rationale": None,
        "reviewer_id": None,
        "reviewed_at_utc": None,
    }


def _source_batch_records(
    kind: str,
    batch_index: int,
    batch_count: int,
    items: Sequence[Mapping[str, Any]],
    memberships: Sequence[Mapping[str, Any]] = (),
) -> list[Mapping[str, Any]]:
    return [
        {
            "record_type": f"{kind}_source_batch_begin",
            "schema_version": 1,
            "component_id": COMPONENT_ID,
            "batch_index": batch_index,
            "batch_count": batch_count,
            "item_count": len(items),
            "membership_count": len(memberships),
        },
        *items,
        *memberships,
        {
            "record_type": f"{kind}_source_batch_end",
            "batch_index": batch_index,
            "item_count": len(items),
            "membership_count": len(memberships),
        },
    ]


def _decision_batch_records(
    kind: str,
    batch_index: int,
    batch_count: int,
    source_relative: str,
    source_meta: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    config_sha256: str,
    semantic_config: Mapping[str, Any] | None = None,
) -> list[Mapping[str, Any]]:
    header = {
        "record_type": f"{kind}_decision_ledger_begin",
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "config_sha256": config_sha256,
        "batch_index": batch_index,
        "batch_count": batch_count,
        "item_count": len(items),
        "immutable_source_file": source_relative,
        "immutable_source_sha256": source_meta["sha256"],
        "immutable_source_bytes": source_meta["bytes"],
        "append_only_revisions": True,
    }
    defaults = (
        [_semantic_default_revision(item["review_id"], semantic_config) for item in items]
        if kind == "semantic"
        else [_route_default_revision(item["review_id"]) for item in items]
    )
    return [header, *defaults]


def _manifest_relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        raise HumanAdjudicationError("A workspace path escaped the project root.") from None


def _initial_workspace_guards(*, proposed: bool) -> dict[str, bool]:
    return {
        "workspace_initialized": not proposed,
        "semantic_review_complete": False,
        "reviewed_semantic_ledger_frozen": False,
        "route_review_complete": False,
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
        "database_connected": False,
        "external_api_called": False,
        "llm_called": False,
    }


def _initial_manifest(
    root: Path,
    destination: Path,
    created_at: str,
    contract: Mapping[str, Any],
    source_inventory: Mapping[str, Any],
    immutable_files: Sequence[Mapping[str, Any]],
    editable_files: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    source = contract["config"]["source_artifact"]
    preview = contract["config"]["structural_preview"]
    return {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "artifact_type": "potassium_query202_private_human_adjudication_workspace",
        "status": "structural_preview" if contract["proposed"] else "initialized",
        "formal_workspace": (
            preview["formal_workspace"] if contract["proposed"] else True
        ),
        "preview_cannot_be_upgraded": (
            not preview["resume_or_upgrade_to_formal_allowed"]
            if contract["proposed"]
            else False
        ),
        "created_at_utc": created_at,
        "artifact_directory": _manifest_relative(root, destination),
        "component_lineage": {
            "config": contract["path"].relative_to(root).as_posix(),
            "config_sha256": contract["config_sha256"],
            "status_at_initialization": contract["config"]["status"],
            "generator_bundle_sha256": contract["bundle"]["bundle_sha256"],
        },
        "source_lineage": {
            "artifact_directory": source["directory"],
            "component_id": source["component_id"],
            "manifest_sha256": source["manifest_sha256"],
            "aggregate_summary_sha256": source["aggregate_summary_sha256"],
            "audit_sha256": source["audit_sha256"],
            "semantic_template_sha256": source["semantic_template"]["stored_sha256"],
            "route_template_sha256": source["route_template"]["stored_sha256"],
            "local_evidence_sha256": source["local_evidence"]["stored_sha256"],
            "local_evidence_bridge_index_sha256": contract["config"]
            ["evidence_registry"]["local_tuple_index"]["index_sha256"],
            "ndc_decision_config_sha256": contract["config"]["ndc_decision"]["config_sha256"],
        },
        "cardinality": {
            "semantic_items": source["semantic_template"]["semantic_keys"],
            "semantic_batches": contract["config"]["workspace"]["semantic_batch_count"],
            "semantic_batch_size": contract["config"]["workspace"]["semantic_batch_size"],
            "route_items": source["route_template"]["canonical_exact_nonnull_values"],
            "route_batches": contract["config"]["workspace"]["route_batch_count"],
            "route_nonnull_memberships": source["route_template"]["source_specific_nonnull_memberships"],
            "route_sql_null_memberships": source["route_template"]["source_specific_sql_null_memberships"],
            "route_typed_memberships": source["route_template"]["source_specific_typed_memberships"],
            "local_evidence_bridge_index_records": contract["config"]
            ["evidence_registry"]["local_tuple_index"]["index_records"],
            "mapping_groups": 0,
        },
        "immutable_source_files": list(immutable_files),
        "editable_ledger_files_at_initialization": list(editable_files),
        "privacy": {
            "directory_mode": "0700",
            "file_mode": "0600",
            "git_ignored": True,
            "raw_values_printed": False,
            "database_connected": False,
            "external_api_called": False,
            "llm_called": False,
        },
        "guards": _initial_workspace_guards(proposed=contract["proposed"]),
    }


def initialize_human_adjudication_workspace(
    root: Path,
    config_path: Path = CONFIG_PATH,
    output_parent: Path | None = None,
    *,
    created_at_utc: str | None = None,
    allow_proposed: bool = False,
) -> dict[str, Any]:
    """Initialize a private all-unreviewed workspace atomically.

    A proposed component is rejected unless the Python-only ``allow_proposed``
    test hook is explicit.  That hook creates a segregated structural preview;
    it is not evidence, cannot be upgraded to a formal workspace, cannot be
    compiled or frozen, and is intentionally unavailable from the CLI.
    """
    root = root.resolve(strict=True)
    contract = _load_contract(root, config_path, allow_proposed=allow_proposed)
    _require_formal_preregistration_ready(root, contract)
    source_inventory = _source_inventory(root, contract)
    source_cfg = contract["config"]["source_artifact"]
    semantic_records = _stream_records(
        source_inventory["snapshots"]["semantic_template"],
        source_cfg["semantic_template"],
        "The semantic review template",
    )
    route_records = _stream_records(
        source_inventory["snapshots"]["route_template"],
        source_cfg["route_template"],
        "The route review template",
    )
    semantic_items = _parse_semantic_template(semantic_records, source_cfg["semantic_template"])
    route_items, route_memberships = _parse_route_template(route_records, source_cfg["route_template"])

    workspace_cfg = contract["config"]["workspace"]
    batch_size = workspace_cfg["semantic_batch_size"]
    semantic_batches = (len(semantic_items) + batch_size - 1) // batch_size
    if semantic_batches != workspace_cfg["semantic_batch_count"] or workspace_cfg["route_batch_count"] != 1:
        raise HumanAdjudicationError("The configured batch cardinality does not conserve the source universe.")

    configured_parent = _safe_relative(
        (
            contract["config"]["structural_preview"]["artifact_parent"]
            if contract["proposed"]
            else workspace_cfg["artifact_parent"]
        ),
        "workspace parent",
    )
    parent_relative = configured_parent if output_parent is None else output_parent
    if (
        parent_relative.is_absolute()
        or ".." in parent_relative.parts
        or parent_relative != configured_parent
    ):
        raise HumanAdjudicationError("The workspace parent is unsafe.")
    parent = root / parent_relative
    parent_descriptor, parent_chain = _ensure_private_directory(
        root, parent_relative
    )
    if _mode(parent) != "0700" or not _git_ignored(root, parent):
        os.close(parent_descriptor)
        raise HumanAdjudicationError("The workspace parent is not private and Git-ignored.")

    created = created_at_utc or _now_utc()
    destination_name = _timestamp_directory(created)
    destination = parent / destination_name
    try:
        os.stat(
            destination_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        pass
    else:
        os.close(parent_descriptor)
        raise HumanAdjudicationError("The workspace destination already exists.")
    for _ in range(100):
        temporary_name = ".tmp-human-adjudication-" + secrets.token_hex(12)
        try:
            os.mkdir(temporary_name, 0o700, dir_fd=parent_descriptor)
            break
        except FileExistsError:
            continue
    else:
        os.close(parent_descriptor)
        raise HumanAdjudicationError(
            "A unique temporary workspace directory could not be allocated."
        )
    temporary_descriptor: int | None = None
    controlled_identity: tuple[int, int] | None = None
    try:
        temporary_descriptor = os.open(
            temporary_name,
            DIRECTORY_OPEN_FLAGS,
            dir_fd=parent_descriptor,
        )
        temporary_stat = os.fstat(temporary_descriptor)
        controlled_identity = (temporary_stat.st_dev, temporary_stat.st_ino)
        os.fchmod(temporary_descriptor, 0o700)
        current_temporary = os.fstat(temporary_descriptor)
        named_temporary = os.stat(
            temporary_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(current_temporary.st_mode)
            or stat.S_IMODE(current_temporary.st_mode) != 0o700
            or not _same_open_snapshot(current_temporary, named_temporary)
        ):
            raise HumanAdjudicationError(
                "The temporary workspace is not a real directory."
            )
        os.fsync(temporary_descriptor)
        os.fsync(parent_descriptor)
    except BaseException:
        if temporary_descriptor is not None:
            os.close(temporary_descriptor)
        try:
            if controlled_identity is not None:
                _remove_tree_if_identity_at(
                    parent_descriptor, temporary_name, controlled_identity
                )
        except OSError:
            pass
        finally:
            os.close(parent_descriptor)
        raise
    assert controlled_identity is not None
    temporary = parent / temporary_name
    renamed = False
    try:
        for relative in (
            "semantic-source",
            "semantic-decisions",
            "semantic-groups",
            "route-source",
            "route-decisions",
            "evidence-registry",
            "attestations",
            "revisions",
        ):
            _mkdir_private_at(temporary_descriptor, relative)
        _mkdir_private_at(
            temporary_descriptor, "evidence-registry/documents"
        )

        immutable_inventory: list[dict[str, Any]] = []
        editable_inventory: list[dict[str, Any]] = []
        local_index_meta = _build_local_evidence_index(
            temporary_descriptor,
            LOCAL_EVIDENCE_INDEX_FILE,
            source_inventory,
            contract["config"],
            semantic_items,
        )
        immutable_inventory.append(
            {"file": LOCAL_EVIDENCE_INDEX_FILE, **local_index_meta}
        )
        for batch_index in range(1, semantic_batches + 1):
            start = (batch_index - 1) * batch_size
            items = semantic_items[start:start + batch_size]
            source_relative = f"semantic-source/semantic-source-batch-{batch_index:04d}.jsonl"
            source_meta = _write_ndjson_at(
                temporary_descriptor,
                source_relative,
                _source_batch_records("semantic", batch_index, semantic_batches, items),
            )
            immutable_inventory.append({"file": source_relative, **source_meta, "items": len(items), "memberships": 0})
            ledger_relative = f"semantic-decisions/semantic-decisions-batch-{batch_index:04d}.jsonl"
            ledger_meta = _write_ndjson_at(
                temporary_descriptor,
                ledger_relative,
                _decision_batch_records(
                    "semantic", batch_index, semantic_batches, source_relative,
                    source_meta, items, contract["config_sha256"],
                    contract["config"]["semantic_review"],
                ),
            )
            editable_inventory.append({"file": ledger_relative, **ledger_meta, "items": len(items), "initial_revisions": len(items)})

        route_source_relative = "route-source/route-source-batch-0001.jsonl"
        route_source_meta = _write_ndjson_at(
            temporary_descriptor,
            route_source_relative,
            _source_batch_records("route", 1, 1, route_items, route_memberships),
        )
        immutable_inventory.append({
            "file": route_source_relative, **route_source_meta,
            "items": len(route_items), "memberships": len(route_memberships),
        })
        route_ledger_relative = "route-decisions/route-decisions-batch-0001.jsonl"
        route_ledger_meta = _write_ndjson_at(
            temporary_descriptor,
            route_ledger_relative,
            _decision_batch_records(
                "route", 1, 1, route_source_relative, route_source_meta,
                route_items, contract["config_sha256"], None,
            ),
        )
        editable_inventory.append({
            "file": route_ledger_relative, **route_ledger_meta,
            "items": len(route_items), "initial_revisions": len(route_items),
        })
        group_relative = "semantic-groups/mapping-groups.jsonl"
        group_meta = _write_ndjson_at(
            temporary_descriptor,
            group_relative,
            [{
                "record_type": "mapping_group_ledger_begin",
                "schema_version": 1,
                "component_id": COMPONENT_ID,
                "config_sha256": contract["config_sha256"],
                "append_only_revisions": True,
                "initial_group_count": 0,
            }],
        )
        editable_inventory.append({
            "file": group_relative, **group_meta, "items": 0, "initial_revisions": 0,
        })

        workspace_event_records: list[Mapping[str, Any]] = [
            {
                "record_type": "workspace_event_ledger_begin",
                "schema_version": 1,
                "component_id": COMPONENT_ID,
                "config_sha256": contract["config_sha256"],
                "initial_event_count": 0,
            }
        ]
        if not contract["proposed"]:
            workspace_event_records.append({
                "record_type": "workspace_event",
                "event_index": 1,
                "previous_event_sha256": None,
                "event_type": "initialized",
                "event_at_utc": created,
                "actor_id": "workspace_initializer",
                "subject_kind": "component_config",
                "subject_id": COMPONENT_ID,
                "subject_sha256": contract["config_sha256"],
            })
        registry_specs = (
            (
                "workspace-events.jsonl",
                workspace_event_records,
            ),
            (
                "evidence-registry/evidence-registry.jsonl",
                [{
                    "record_type": "evidence_registry_begin",
                    "schema_version": 1,
                    "component_id": COMPONENT_ID,
                    "config_sha256": contract["config_sha256"],
                    "initial_evidence_count": 0,
                }],
            ),
            (
                "attestations/batch-attestations.jsonl",
                [{
                    "record_type": "batch_attestation_ledger_begin",
                    "schema_version": 1,
                    "component_id": COMPONENT_ID,
                    "config_sha256": contract["config_sha256"],
                    "initial_attestation_count": 0,
                }],
            ),
            (
                "revisions/revision-events.jsonl",
                [{
                    "record_type": "revision_event_ledger_begin",
                    "schema_version": 1,
                    "component_id": COMPONENT_ID,
                    "config_sha256": contract["config_sha256"],
                    "initial_event_count": 0,
                }],
            ),
        )
        for registry_relative, registry_records in registry_specs:
            registry_meta = _write_ndjson_at(
                temporary_descriptor,
                registry_relative,
                registry_records,
            )
            editable_inventory.append({
                "file": registry_relative,
                **registry_meta,
                "items": len(registry_records) - 1,
                "initial_revisions": 0,
            })

        manifest = _initial_manifest(
            root,
            destination,
            created,
            contract,
            source_inventory,
            immutable_inventory,
            editable_inventory,
        )
        manifest_meta = _write_private_at(
            temporary_descriptor,
            "workspace-manifest.json",
            _pretty_json(manifest),
        )
        fresh_parent_descriptor, fresh_parent_chain = _open_directory_fd(parent)
        os.close(fresh_parent_descriptor)
        if fresh_parent_chain != parent_chain:
            raise HumanAdjudicationError(
                "The workspace parent changed before atomic publication."
            )
        named_temporary = os.stat(
            temporary_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(named_temporary.st_mode)
            or (named_temporary.st_dev, named_temporary.st_ino)
            != controlled_identity
        ):
            raise HumanAdjudicationError(
                "The temporary workspace changed before publication."
            )
        os.fsync(temporary_descriptor)
        _rename_directory_noreplace(
            parent_descriptor,
            temporary_name,
            parent_descriptor,
            destination_name,
        )
        renamed = True
        os.fsync(parent_descriptor)
        anchored_destination_descriptor = os.open(
            destination_name,
            DIRECTORY_OPEN_FLAGS,
            dir_fd=parent_descriptor,
        )
        try:
            anchored_destination = os.fstat(anchored_destination_descriptor)
            if (
                anchored_destination.st_dev,
                anchored_destination.st_ino,
            ) != controlled_identity:
                raise HumanAdjudicationError(
                    "The published workspace leaf was replaced."
                )
        finally:
            os.close(anchored_destination_descriptor)
        destination_snapshot = _snapshot_directory(
            destination, "The generated workspace"
        )
        if (
            destination_snapshot["parent_chain"][:-1] != parent_chain
            or destination_snapshot["identity"] != controlled_identity
        ):
            raise HumanAdjudicationError(
                "The workspace identity changed during atomic publication."
            )
        if not _git_ignored(root, destination):
            raise HumanAdjudicationError("The generated workspace is not Git-ignored.")
        _finish_source_closure(source_inventory, contract)
        report = validate_human_adjudication_workspace(
            root,
            destination.relative_to(root),
            config_path=config_path,
            allow_proposed=allow_proposed,
        )
        if not report["valid"] or report["reviewed_semantic_items"] != 0 or report["reviewed_route_items"] != 0:
            raise HumanAdjudicationError("The initialized workspace did not validate as all-unreviewed.")
        return {
            "status": manifest["status"],
            "formal_workspace": manifest["formal_workspace"],
            "workspace": destination.relative_to(root).as_posix(),
            "manifest": (destination / "workspace-manifest.json").relative_to(root).as_posix(),
            "manifest_sha256": manifest_meta["sha256"],
            "semantic_items": len(semantic_items),
            "semantic_batches": semantic_batches,
            "route_items": len(route_items),
            "route_batches": 1,
            "route_typed_memberships": len(route_memberships),
            "mapping_groups": 0,
            "reviewed_semantic_items": 0,
            "reviewed_route_items": 0,
            "database_connected": False,
            "external_api_called": False,
            "llm_called": False,
        }
    except BaseException:
        try:
            if temporary_descriptor is not None:
                _scrub_and_remove_controlled_directory_at(
                    parent_descriptor,
                    temporary_descriptor,
                    controlled_identity,
                )
            else:
                _remove_tree_if_identity_at(
                    parent_descriptor,
                    destination_name if renamed else temporary_name,
                    controlled_identity,
                )
        except OSError:
            pass
        raise
    finally:
        if temporary_descriptor is not None:
            os.close(temporary_descriptor)
        os.close(parent_descriptor)


def _nonempty_text(value: object, label: str, maximum: int = MAX_TEXT_BYTES) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > maximum:
        raise HumanAdjudicationError(f"{label} must be nonempty bounded text.")
    return value


def _evidence_refs(
    value: object,
    label: str,
    evidence_registry: Mapping[str, Mapping[str, Any]],
    *,
    required: bool,
    review_id: str | None = None,
) -> list[str]:
    if not isinstance(value, list) or (required and not value):
        raise HumanAdjudicationError(f"{label} evidence references are invalid.")
    output: list[str] = []
    for item in value:
        if (
            not isinstance(item, str)
            or EVIDENCE_ID_RE.fullmatch(item) is None
            or item not in evidence_registry
        ):
            raise HumanAdjudicationError(f"{label} contains an invalid evidence reference.")
        output.append(item)
        registered = evidence_registry[item]
        if (
            review_id is not None
            and registered.get("namespace") == "source_template"
            and registered.get("locator", {}).get("private_review_id") != review_id
        ):
            raise HumanAdjudicationError(
                f"{label} uses a source-template reference for another review item."
            )
    if len(output) != len(set(output)):
        raise HumanAdjudicationError(f"{label} contains duplicate evidence references.")
    return output


def _validate_revision_common(
    record: Mapping[str, Any],
    expected_type: str,
    id_pattern: re.Pattern[str],
) -> tuple[str, int, str | None, str]:
    if record.get("record_type") != expected_type:
        raise HumanAdjudicationError("A decision ledger contains an invalid record type.")
    review_id = record.get("review_id")
    revision = record.get("revision")
    supersedes = record.get("supersedes_sha256")
    reason = record.get("revision_reason")
    if not isinstance(review_id, str) or id_pattern.fullmatch(review_id) is None:
        raise HumanAdjudicationError("A decision revision has an invalid review ID.")
    _require_positive_int(revision, "revision number")
    if supersedes is not None and (not isinstance(supersedes, str) or SHA256_RE.fullmatch(supersedes) is None):
        raise HumanAdjudicationError("A decision revision has an invalid supersedes hash.")
    _nonempty_text(reason, "revision reason")
    return review_id, revision, supersedes, reason


def _validate_semantic_revision(
    record: Mapping[str, Any],
    semantic_config: Mapping[str, Any],
    evidence_registry: Mapping[str, Mapping[str, Any]],
    *,
    bind_source_template_to_item: bool = True,
) -> tuple[str, int, str | None]:
    keys = {
        "record_type", "review_id", "revision", "supersedes_sha256", "revision_reason",
        "review_status", "dimensions", "mapping_group_id", "rationale",
        "reviewer_id", "reviewed_at_utc",
    }
    record = _exact_keys(record, keys, "semantic decision revision")
    review_id, revision, supersedes, _ = _validate_revision_common(record, "semantic_decision_revision", SEMANTIC_ID_RE)
    status = record["review_status"]
    dimensions = record["dimensions"]
    if status not in REVIEW_STATUSES or not isinstance(dimensions, Mapping) or set(dimensions) != set(SEMANTIC_DIMENSIONS):
        raise HumanAdjudicationError("A semantic decision has an invalid controlled state.")
    value_contracts = semantic_config["values"]
    for dimension in SEMANTIC_DIMENSIONS:
        item = _exact_keys(
            dimensions[dimension],
            {"status", "value", "evidence_refs", "uncertainty_basis"},
            "semantic dimension decision",
        )
        decision = item["status"]
        if decision not in SEMANTIC_STATUSES:
            raise HumanAdjudicationError("A semantic dimension status is invalid.")
        value = _exact_keys(item["value"], {"code", "candidates"}, "semantic controlled value")
        expected_code = value_contracts[dimension][decision + "_code"]
        candidates = value["candidates"]
        if value["code"] != expected_code or not isinstance(candidates, list):
            raise HumanAdjudicationError("A semantic controlled-value code or candidate list is invalid.")
        for candidate in candidates:
            _nonempty_text(candidate, "semantic controlled-value candidate")
        if status == "unreviewed":
            if item != {
                "status": "uncertain",
                "value": {
                    "code": value_contracts[dimension]["uncertain_code"],
                    "candidates": [],
                },
                "evidence_refs": [],
                "uncertainty_basis": None,
            }:
                raise HumanAdjudicationError("An unreviewed semantic dimension is not at its exact default.")
        elif decision == "uncertain":
            if item["uncertainty_basis"] not in UNCERTAINTY_BASES:
                raise HumanAdjudicationError("A reviewed uncertain dimension lacks its explicit basis.")
            _evidence_refs(
                item["evidence_refs"],
                "semantic dimension",
                evidence_registry,
                required=False,
                review_id=review_id if bind_source_template_to_item else None,
            )
        else:
            if item["uncertainty_basis"] is not None:
                raise HumanAdjudicationError("A non-uncertain semantic dimension has an uncertainty basis.")
            _evidence_refs(
                item["evidence_refs"],
                "semantic dimension",
                evidence_registry,
                required=True,
                review_id=review_id if bind_source_template_to_item else None,
            )
    group_id = record["mapping_group_id"]
    if group_id is not None and (not isinstance(group_id, str) or GROUP_ID_RE.fullmatch(group_id) is None):
        raise HumanAdjudicationError("A semantic mapping-group ID is invalid.")
    if status == "unreviewed":
        if group_id is not None or any(record[key] is not None for key in ("rationale", "reviewer_id", "reviewed_at_utc")):
            raise HumanAdjudicationError("An unreviewed semantic revision contains human decisions.")
    else:
        _nonempty_text(record["rationale"], "semantic rationale")
        _nonempty_text(record["reviewer_id"], "semantic reviewer ID", 256)
        if not _strict_utc(record["reviewed_at_utc"]):
            raise HumanAdjudicationError("A semantic reviewed time is not strict UTC.")
    return review_id, revision, supersedes


def _validate_route_revision(
    record: Mapping[str, Any],
    evidence_registry: Mapping[str, Mapping[str, Any]],
) -> tuple[str, int, str | None]:
    keys = {
        "record_type", "review_id", "revision", "supersedes_sha256", "revision_reason",
        "review_status", "decision", "decision_basis", "evidence_refs", "rationale",
        "reviewer_id", "reviewed_at_utc",
    }
    record = _exact_keys(record, keys, "route decision revision")
    review_id, revision, supersedes, _ = _validate_revision_common(record, "route_decision_revision", ROUTE_ID_RE)
    status = record["review_status"]
    decision = record["decision"]
    if status not in REVIEW_STATUSES or decision not in ROUTE_DECISIONS:
        raise HumanAdjudicationError("A route decision has an invalid controlled state.")
    _evidence_refs(
        record["evidence_refs"],
        "route decision",
        evidence_registry,
        required=status == "reviewed",
        review_id=review_id,
    )
    if status == "unreviewed":
        if (
            decision != "unknown"
            or record["decision_basis"] is not None
            or record["evidence_refs"] != []
            or any(record[key] is not None for key in ("rationale", "reviewer_id", "reviewed_at_utc"))
        ):
            raise HumanAdjudicationError("An unreviewed route revision is not at its exact default.")
    else:
        if record["decision_basis"] not in ROUTE_BASES:
            raise HumanAdjudicationError("A reviewed route decision basis is invalid.")
        if decision == "unknown" and record["decision_basis"] != "ambiguous_or_insufficient_route_semantics":
            raise HumanAdjudicationError("A reviewed unknown route lacks an ambiguity or insufficiency basis.")
        _nonempty_text(record["rationale"], "route rationale")
        _nonempty_text(record["reviewer_id"], "route reviewer ID", 256)
        if not _strict_utc(record["reviewed_at_utc"]):
            raise HumanAdjudicationError("A route reviewed time is not strict UTC.")
    return review_id, revision, supersedes


def _active_batch_hash(kind: str, batch_index: int, active: Mapping[str, Mapping[str, Any]]) -> str:
    digest = hashlib.sha256(ACTIVE_BATCH_VERSION)
    kind_bytes = kind.encode("ascii")
    digest.update(struct.pack(">I", len(kind_bytes)))
    digest.update(kind_bytes)
    digest.update(struct.pack(">I", batch_index))
    digest.update(struct.pack(">Q", len(active)))
    for review_id in sorted(active):
        encoded_id = review_id.encode("ascii")
        digest.update(struct.pack(">I", len(encoded_id)))
        digest.update(encoded_id)
        digest.update(bytes.fromhex(_record_sha(active[review_id])))
    return digest.hexdigest()


def _validate_attestation_ledger(
    records: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
    batch_bindings: Mapping[tuple[str, int], Mapping[str, Any]],
    group_registry_sha256: str,
) -> tuple[
    set[tuple[str, int]],
    set[str],
    dict[str, Mapping[str, Any]],
    dict[tuple[str, int], str],
]:
    if not records:
        raise HumanAdjudicationError("The batch-attestation ledger is empty.")
    expected_header = {
        "record_type": "batch_attestation_ledger_begin",
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "config_sha256": contract["config_sha256"],
        "initial_attestation_count": 0,
    }
    if records[0] != expected_header:
        raise HumanAdjudicationError("The batch-attestation ledger header changed.")
    policy = contract["config"]["human_review_policy"]
    effective_model = policy.get("reviewer_model")
    current: set[tuple[str, int]] = set()
    exact_seen: set[bytes] = set()
    human_reviewers: set[str] = set()
    attestation_bindings: dict[str, Mapping[str, Any]] = {}
    current_hashes: dict[tuple[str, int], str] = {}
    for raw_record in records[1:]:
        record = _exact_keys(
            raw_record,
            {
                "record_type", "review_kind", "batch_index", "item_count",
                "active_decisions_sha256", "decision_ledger_sha256",
                "mapping_group_registry_sha256", "review_policy_version",
                "attestation_method", "reviewer_id", "attested_at_utc",
            },
            "batch attestation",
        )
        kind = record["review_kind"]
        index = record["batch_index"]
        key = (kind, index)
        if (
            record["record_type"] != "batch_attestation"
            or kind not in {"semantic", "route"}
            or type(index) is not int
            or type(record["item_count"]) is not int
            or record["item_count"] < 0
            or record["item_count"] > MAX_COUNT
            or key not in batch_bindings
            or record["review_policy_version"] != contract["config"].get("rule_version")
            or record["attestation_method"] != "human"
        ):
            raise HumanAdjudicationError("A batch attestation identity or policy binding is invalid.")
        if any(
            not isinstance(record[field], str)
            or SHA256_RE.fullmatch(record[field]) is None
            for field in ("active_decisions_sha256", "decision_ledger_sha256")
        ) or (
            kind == "semantic"
            and (
                not isinstance(record["mapping_group_registry_sha256"], str)
                or SHA256_RE.fullmatch(record["mapping_group_registry_sha256"])
                is None
            )
        ) or (kind == "route" and record["mapping_group_registry_sha256"] is not None):
            raise HumanAdjudicationError("A batch attestation hash binding is invalid.")
        _nonempty_text(record["reviewer_id"], "attestation reviewer ID", 256)
        human_reviewers.add(record["reviewer_id"])
        if not _strict_utc(record["attested_at_utc"]):
            raise HumanAdjudicationError("A batch attestation time is not strict UTC.")
        encoded = _canonical_json(record)
        if encoded in exact_seen:
            continue
        exact_seen.add(encoded)
        record_hash = hashlib.sha256(encoded).hexdigest()
        attestation_bindings[record_hash] = {
            "review_kind": kind,
            "batch_index": index,
            "reviewer_id": record["reviewer_id"],
            "recorded_at_utc": record["attested_at_utc"],
        }
        binding = batch_bindings[key]
        expected_group_hash = group_registry_sha256 if kind == "semantic" else None
        if (
            record["item_count"] == binding["item_count"]
            and record["active_decisions_sha256"] == binding["active_hash"]
            and record["decision_ledger_sha256"] == binding["ledger_sha256"]
            and record["mapping_group_registry_sha256"] == expected_group_hash
            and effective_model in policy.get("allowed_models", [])
        ):
            if key in current_hashes:
                raise HumanAdjudicationError(
                    "A batch has multiple distinct current attestations."
                )
            current.add(key)
            current_hashes[key] = record_hash
    return current, human_reviewers, attestation_bindings, current_hashes


def _validate_source_batch(
    records: Sequence[Mapping[str, Any]], kind: str, batch_index: int, batch_count: int,
    expected_items: Sequence[Mapping[str, Any]], expected_memberships: Sequence[Mapping[str, Any]],
) -> None:
    if len(records) != len(expected_items) + len(expected_memberships) + 2:
        raise HumanAdjudicationError("An immutable source batch cardinality changed.")
    begin = _exact_keys(
        records[0],
        {"record_type", "schema_version", "component_id", "batch_index", "batch_count", "item_count", "membership_count"},
        "source batch begin",
    )
    end = _exact_keys(
        records[-1],
        {"record_type", "batch_index", "item_count", "membership_count"},
        "source batch end",
    )
    if begin != _source_batch_records(kind, batch_index, batch_count, expected_items, expected_memberships)[0] or end != _source_batch_records(kind, batch_index, batch_count, expected_items, expected_memberships)[-1]:
        raise HumanAdjudicationError("An immutable source batch framing changed.")
    if list(records[1:-1]) != [*expected_items, *expected_memberships]:
        raise HumanAdjudicationError("An immutable source value, order, or batch assignment changed.")


def _validate_decision_ledger(
    records: Sequence[Mapping[str, Any]], kind: str, batch_index: int, batch_count: int,
    source_relative: str, source_snapshot: Mapping[str, Any], expected_ids: Sequence[str],
    contract: Mapping[str, Any],
    evidence_registry: Mapping[str, Mapping[str, Any]],
) -> tuple[
    dict[str, Mapping[str, Any]],
    bool,
    int,
    str,
    set[str],
    dict[tuple[str, str, int], Mapping[str, Any]],
]:
    if not records:
        raise HumanAdjudicationError("A decision ledger is empty.")
    header = _exact_keys(
        records[0],
        {
            "record_type", "schema_version", "component_id", "config_sha256", "batch_index",
            "batch_count", "item_count", "immutable_source_file", "immutable_source_sha256",
            "immutable_source_bytes", "append_only_revisions",
        },
        "decision ledger begin",
    )
    expected_header = {
        "record_type": f"{kind}_decision_ledger_begin",
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "config_sha256": contract["config_sha256"],
        "batch_index": batch_index,
        "batch_count": batch_count,
        "item_count": len(expected_ids),
        "immutable_source_file": source_relative,
        "immutable_source_sha256": source_snapshot["sha256"],
        "immutable_source_bytes": source_snapshot["bytes"],
        "append_only_revisions": True,
    }
    if header != expected_header:
        raise HumanAdjudicationError("A decision ledger lost its immutable source binding.")
    expected_set = set(expected_ids)
    revisions: dict[str, dict[int, tuple[str, Mapping[str, Any]]]] = {key: {} for key in expected_ids}
    active: dict[str, Mapping[str, Any]] = {}
    active_hashes: dict[str, str] = {}
    human_reviewers: set[str] = set()
    revision_events: dict[tuple[str, str, int], Mapping[str, Any]] = {}
    for record in records[1:]:
        if kind == "semantic":
            review_id, revision, supersedes = _validate_semantic_revision(
                record,
                contract["config"]["semantic_review"],
                evidence_registry,
            )
        else:
            review_id, revision, supersedes = _validate_route_revision(
                record, evidence_registry
            )
        if record["review_status"] == "reviewed":
            human_reviewers.add(record["reviewer_id"])
        if review_id not in expected_set:
            raise HumanAdjudicationError("A decision revision is missing, duplicated across, or assigned to the wrong batch.")
        digest = _record_sha(record)
        existing = revisions[review_id].get(revision)
        if existing is not None:
            if existing[0] != digest:
                raise HumanAdjudicationError("Conflicting revisions share one item and revision number.")
            continue  # exact resubmission is idempotent
        expected_revision = len(revisions[review_id]) + 1
        if revision != expected_revision:
            raise HumanAdjudicationError("A decision revision sequence has a gap or branch.")
        if revision == 1:
            if supersedes is not None or record != (
                _semantic_default_revision(
                    review_id, contract["config"]["semantic_review"]
                ) if kind == "semantic" else _route_default_revision(review_id)
            ):
                raise HumanAdjudicationError("An initial decision revision is not the exact all-unreviewed default.")
        else:
            if record["review_status"] != "reviewed":
                raise HumanAdjudicationError(
                    "A noninitial decision revision lacks human review."
                )
            if supersedes != active_hashes[review_id]:
                raise HumanAdjudicationError("A decision revision does not supersede its unique active predecessor.")
            revision_kind = f"{kind}_decision"
            revision_events[(revision_kind, review_id, revision)] = {
                "revision_kind": revision_kind,
                "subject_id": review_id,
                "batch_index": batch_index,
                "revision": revision,
                "revision_sha256": digest,
                "supersedes_sha256": supersedes,
                "reviewer_id": record["reviewer_id"],
                "recorded_at_utc": record["reviewed_at_utc"],
            }
        revisions[review_id][revision] = (digest, record)
        active[review_id] = record
        active_hashes[review_id] = digest
    if set(active) != expected_set or any(len(value) < 1 for value in revisions.values()):
        raise HumanAdjudicationError("A decision ledger omits an exact source item.")
    reviewed = sum(record["review_status"] == "reviewed" for record in active.values())
    all_reviewed = reviewed == len(expected_ids)
    return (
        active,
        all_reviewed,
        reviewed,
        _active_batch_hash(kind, batch_index, active),
        human_reviewers,
        revision_events,
    )


def _validate_group_revision(
    record: Mapping[str, Any],
    all_ids: set[str],
    semantic_config: Mapping[str, Any],
    group_config: Mapping[str, Any],
    evidence_registry: Mapping[str, Mapping[str, Any]],
) -> tuple[str, int, str | None]:
    keys = {
        "record_type", "mapping_group_id", "revision", "supersedes_sha256", "revision_reason",
        "review_status", "member_review_ids", "local_evidence_refs", "dimensions",
        "rationale", "reviewer_id", "reviewed_at_utc",
    }
    record = _exact_keys(record, keys, "mapping-group revision")
    group_id = record["mapping_group_id"]
    if not isinstance(group_id, str) or GROUP_ID_RE.fullmatch(group_id) is None:
        raise HumanAdjudicationError("A mapping-group ID is invalid.")
    revision = _require_positive_int(record["revision"], "mapping-group revision")
    supersedes = record["supersedes_sha256"]
    if supersedes is not None and (not isinstance(supersedes, str) or SHA256_RE.fullmatch(supersedes) is None):
        raise HumanAdjudicationError("A mapping-group supersedes hash is invalid.")
    _nonempty_text(record["revision_reason"], "mapping-group revision reason")
    if record["review_status"] != "reviewed":
        raise HumanAdjudicationError("A mapping-group definition lacks human review.")
    members = record["member_review_ids"]
    if (
        not isinstance(members, list)
        or len(members) < 2
        or members != sorted(members)
        or len(members) != len(set(members))
        or any(member not in all_ids for member in members)
    ):
        raise HumanAdjudicationError("A mapping-group member set is invalid.")
    local_refs = _evidence_refs(
        record["local_evidence_refs"],
        "mapping group",
        evidence_registry,
        required=True,
    )
    if any(evidence_registry[reference]["namespace"] != "local_tuple" for reference in local_refs):
        raise HumanAdjudicationError("A mapping group lacks bound local-tuple evidence.")
    allowed_group_kinds = set(
        group_config["local_evidence_eligibility"]["allowed_stage_kind"]
    )
    if any(
        (
            f"{evidence_registry[reference]['locator']['stage']}:"
            f"{evidence_registry[reference]['locator']['tuple_kind']}"
        ) not in allowed_group_kinds
        for reference in local_refs
    ):
        raise HumanAdjudicationError(
            "A mapping group uses a local-tuple kind that is ineligible for grouping."
        )
    member_set = set(members)
    if not any(
        member_set.issubset(
            set(evidence_registry[reference].get("semantic_members", ()))
        )
        for reference in local_refs
    ):
        raise HumanAdjudicationError(
            "No bound local tuple links every mapping-group member."
        )
    dimensions = record["dimensions"]
    if not isinstance(dimensions, Mapping) or set(dimensions) != set(SEMANTIC_DIMENSIONS):
        raise HumanAdjudicationError("A mapping-group dimension schema is invalid.")
    synthetic = {
        "record_type": "semantic_decision_revision",
        "review_id": "S000001",
        "revision": 1,
        "supersedes_sha256": None,
        "revision_reason": "mapping_group_validation",
        "review_status": "reviewed",
        "dimensions": dimensions,
        "mapping_group_id": None,
        "rationale": record["rationale"],
        "reviewer_id": record["reviewer_id"],
        "reviewed_at_utc": record["reviewed_at_utc"],
    }
    _validate_semantic_revision(
        synthetic,
        semantic_config,
        evidence_registry,
        bind_source_template_to_item=False,
    )
    product_refs = dimensions["product_identity"]["evidence_refs"]
    if not any(
        evidence_registry[reference]["namespace"] != "local_tuple"
        for reference in product_refs
    ):
        raise HumanAdjudicationError(
            "A mapping group lacks human identity evidence beyond co-occurrence."
        )
    return group_id, revision, supersedes


def _validate_group_ledger(
    records: Sequence[Mapping[str, Any]], contract: Mapping[str, Any], all_ids: set[str],
    semantic_active: Mapping[str, Mapping[str, Any]],
    evidence_registry: Mapping[str, Mapping[str, Any]],
) -> tuple[
    dict[str, Mapping[str, Any]],
    set[str],
    dict[tuple[str, str, int], Mapping[str, Any]],
]:
    if not records:
        raise HumanAdjudicationError("The mapping-group registry is empty.")
    header = _exact_keys(
        records[0],
        {"record_type", "schema_version", "component_id", "config_sha256", "append_only_revisions", "initial_group_count"},
        "mapping-group ledger begin",
    )
    if header != {
        "record_type": "mapping_group_ledger_begin",
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "config_sha256": contract["config_sha256"],
        "append_only_revisions": True,
        "initial_group_count": 0,
    }:
        raise HumanAdjudicationError("The mapping-group ledger header changed.")
    revisions: dict[str, dict[int, tuple[str, Mapping[str, Any]]]] = {}
    active: dict[str, Mapping[str, Any]] = {}
    active_hashes: dict[str, str] = {}
    human_reviewers: set[str] = set()
    revision_events: dict[tuple[str, str, int], Mapping[str, Any]] = {}
    for record in records[1:]:
        group_id, revision, supersedes = _validate_group_revision(
            record,
            all_ids,
            contract["config"]["semantic_review"],
            contract["config"]["mapping_groups"],
            evidence_registry,
        )
        group_revisions = revisions.setdefault(group_id, {})
        digest = _record_sha(record)
        existing = group_revisions.get(revision)
        if existing is not None:
            if existing[0] != digest:
                raise HumanAdjudicationError("Conflicting mapping-group revisions share one revision number.")
            continue
        if revision != len(group_revisions) + 1:
            raise HumanAdjudicationError("A mapping-group revision sequence has a gap or branch.")
        if (revision == 1 and supersedes is not None) or (revision > 1 and supersedes != active_hashes[group_id]):
            raise HumanAdjudicationError("A mapping-group revision does not bind its predecessor.")
        group_revisions[revision] = (digest, record)
        active[group_id] = record
        active_hashes[group_id] = digest
        human_reviewers.add(record["reviewer_id"])
        revision_events[("mapping_group", group_id, revision)] = {
            "revision_kind": "mapping_group",
            "subject_id": group_id,
            "batch_index": None,
            "revision": revision,
            "revision_sha256": digest,
            "supersedes_sha256": supersedes,
            "reviewer_id": record["reviewer_id"],
            "recorded_at_utc": record["reviewed_at_utc"],
        }
    assignments: dict[str, set[str]] = {}
    for review_id, record in semantic_active.items():
        group_id = record["mapping_group_id"]
        if group_id is not None:
            if record["review_status"] != "reviewed":
                raise HumanAdjudicationError("An unreviewed semantic item has a mapping group.")
            assignments.setdefault(group_id, set()).add(review_id)
    if set(assignments) != set(active):
        raise HumanAdjudicationError("The mapping-group registry and semantic assignments differ.")
    for group_id, group in active.items():
        if assignments[group_id] != set(group["member_review_ids"]):
            raise HumanAdjudicationError("A mapping-group member set does not equal its key assignments.")
        for member in group["member_review_ids"]:
            product_refs = semantic_active[member]["dimensions"]["product_identity"][
                "evidence_refs"
            ]
            if not any(
                evidence_registry[reference]["namespace"] != "local_tuple"
                for reference in product_refs
            ):
                raise HumanAdjudicationError(
                    "A grouped member lacks human identity evidence beyond co-occurrence."
                )
    return active, human_reviewers, revision_events


def _workspace_paths(workspace: Path, semantic_batches: int) -> dict[str, list[tuple[str, Path]]]:
    semantic_source = [
        (f"semantic-source/semantic-source-batch-{index:04d}.jsonl", workspace / f"semantic-source/semantic-source-batch-{index:04d}.jsonl")
        for index in range(1, semantic_batches + 1)
    ]
    semantic_decisions = [
        (f"semantic-decisions/semantic-decisions-batch-{index:04d}.jsonl", workspace / f"semantic-decisions/semantic-decisions-batch-{index:04d}.jsonl")
        for index in range(1, semantic_batches + 1)
    ]
    return {
        "semantic_source": semantic_source,
        "semantic_decisions": semantic_decisions,
        "route_source": [("route-source/route-source-batch-0001.jsonl", workspace / "route-source/route-source-batch-0001.jsonl")],
        "route_decisions": [("route-decisions/route-decisions-batch-0001.jsonl", workspace / "route-decisions/route-decisions-batch-0001.jsonl")],
        "groups": [("semantic-groups/mapping-groups.jsonl", workspace / "semantic-groups/mapping-groups.jsonl")],
        "events": [("workspace-events.jsonl", workspace / "workspace-events.jsonl")],
        "evidence": [("evidence-registry/evidence-registry.jsonl", workspace / "evidence-registry/evidence-registry.jsonl")],
        "local_index": [(LOCAL_EVIDENCE_INDEX_FILE, workspace / LOCAL_EVIDENCE_INDEX_FILE)],
        "attestations": [("attestations/batch-attestations.jsonl", workspace / "attestations/batch-attestations.jsonl")],
        "revisions": [("revisions/revision-events.jsonl", workspace / "revisions/revision-events.jsonl")],
        "manifest": [("workspace-manifest.json", workspace / "workspace-manifest.json")],
    }


def _expected_workspace_entries(paths: Mapping[str, Sequence[tuple[str, Path]]]) -> set[str]:
    return {relative for values in paths.values() for relative, _ in values}


def _revision_event_subject(binding: Mapping[str, Any]) -> str:
    kind = binding["revision_kind"]
    if kind == "mapping_group":
        return f"mapping_group:{binding['subject_id']}:{binding['revision']}"
    return (
        f"{kind}:{binding['batch_index']:04d}:"
        f"{binding['subject_id']}:{binding['revision']}"
    )


def _attestation_event_subject(binding: Mapping[str, Any]) -> str:
    return f"{binding['review_kind']}:{binding['batch_index']:04d}"


def _utc_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _validate_revision_event_ledger(
    records: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
    expected_revisions: Mapping[tuple[str, str, int], Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], set[str]]:
    if not records:
        raise HumanAdjudicationError("The revision-event ledger is empty.")
    header = _exact_keys(
        records[0], EVENT_HEADER_FIELDS, "revision-event ledger header"
    )
    expected_header = {
        "record_type": "revision_event_ledger_begin",
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "config_sha256": contract["config_sha256"],
        "initial_event_count": 0,
    }
    if (
        type(header["schema_version"]) is not int
        or type(header["initial_event_count"]) is not int
        or header != expected_header
    ):
        raise HumanAdjudicationError("The revision-event ledger header changed.")
    seen: set[tuple[str, str, int]] = set()
    by_hash: dict[str, Mapping[str, Any]] = {}
    reviewers: set[str] = set()
    previous_hash: str | None = None
    previous_time: datetime | None = None
    for event_index, raw_record in enumerate(records[1:], start=1):
        record = _exact_keys(
            raw_record, REVISION_EVENT_KEYS, "revision-event record"
        )
        kind = record["revision_kind"]
        subject_id = record["subject_id"]
        revision = record["revision"]
        key = (kind, subject_id, revision)
        binding = expected_revisions.get(key)
        if (
            record["record_type"] != "revision_event"
            or type(record["event_index"]) is not int
            or record["event_index"] != event_index
            or record["previous_event_sha256"] != previous_hash
            or type(revision) is not int
            or revision < 1
            or (
                kind == "mapping_group"
                and record["batch_index"] is not None
            )
            or (
                kind != "mapping_group"
                and (
                    type(record["batch_index"]) is not int
                    or record["batch_index"] < 1
                )
            )
            or binding is None
            or key in seen
        ):
            raise HumanAdjudicationError(
                "A revision event breaks sequence, chain, or conservation."
            )
        for field in (
            "revision_kind",
            "subject_id",
            "batch_index",
            "revision",
            "revision_sha256",
            "supersedes_sha256",
            "reviewer_id",
            "recorded_at_utc",
        ):
            if record[field] != binding[field]:
                raise HumanAdjudicationError(
                    "A revision event does not bind its ledger revision."
                )
        if not _strict_utc(record["recorded_at_utc"]):
            raise HumanAdjudicationError("A revision-event time is not strict UTC.")
        current_time = _utc_datetime(record["recorded_at_utc"])
        if previous_time is not None and current_time < previous_time:
            raise HumanAdjudicationError("Revision-event times move backwards.")
        _nonempty_text(record["reviewer_id"], "revision-event reviewer ID", 256)
        reviewers.add(record["reviewer_id"])
        event_hash = _record_sha(record)
        by_hash[event_hash] = binding
        previous_hash = event_hash
        previous_time = current_time
        seen.add(key)
    if seen != set(expected_revisions):
        raise HumanAdjudicationError(
            "The revision-event ledger omits or adds a ledger revision."
        )
    return by_hash, reviewers


def _active_workspace_state_hash(
    batch_bindings: Mapping[tuple[str, int], Mapping[str, Any]],
    groups: Mapping[str, Mapping[str, Any]],
    current_attestations: Mapping[tuple[str, int], str],
) -> str:
    state = {
        "batches": [
            {
                "review_kind": kind,
                "batch_index": index,
                "item_count": binding["item_count"],
                "active_decisions_sha256": binding["active_hash"],
                "decision_ledger_sha256": binding["ledger_sha256"],
            }
            for (kind, index), binding in sorted(batch_bindings.items())
        ],
        "mapping_groups": [
            {
                "mapping_group_id": group_id,
                "active_revision_sha256": _record_sha(record),
            }
            for group_id, record in sorted(groups.items())
        ],
        "current_attestations": [
            {
                "review_kind": kind,
                "batch_index": index,
                "attestation_sha256": attestation_hash,
            }
            for (kind, index), attestation_hash in sorted(
                current_attestations.items()
            )
        ],
    }
    return hashlib.sha256(
        ACTIVE_WORKSPACE_STATE_VERSION + _canonical_json(state)
    ).hexdigest()


def _validate_workspace_event_ledger(
    records: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    revision_events: Mapping[str, Mapping[str, Any]],
    attestations: Mapping[str, Mapping[str, Any]],
    *,
    data_complete: bool,
    active_state_sha256: str,
    single_reviewer_id: str | None,
) -> dict[str, Any]:
    if not records:
        raise HumanAdjudicationError("The workspace-event ledger is empty.")
    header = _exact_keys(
        records[0], EVENT_HEADER_FIELDS, "workspace-event ledger header"
    )
    expected_header = {
        "record_type": "workspace_event_ledger_begin",
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "config_sha256": contract["config_sha256"],
        "initial_event_count": 0,
    }
    if (
        type(header["schema_version"]) is not int
        or type(header["initial_event_count"]) is not int
        or header != expected_header
    ):
        raise HumanAdjudicationError("The workspace-event ledger header changed.")
    consumed_revisions: set[str] = set()
    consumed_attestations: set[str] = set()
    previous_hash: str | None = None
    previous_time: datetime | None = None
    completion_seen = False
    abandoned = False
    initialized_seen = False
    for event_index, raw_record in enumerate(records[1:], start=1):
        record = _exact_keys(
            raw_record, WORKSPACE_EVENT_KEYS, "workspace-event record"
        )
        if (
            record["record_type"] != "workspace_event"
            or type(record["event_index"]) is not int
            or record["event_index"] != event_index
            or record["previous_event_sha256"] != previous_hash
            or record["event_type"] not in WORKSPACE_EVENT_TYPES
            or not _strict_utc(record["event_at_utc"])
        ):
            raise HumanAdjudicationError(
                "A workspace event breaks schema, sequence, or hash chain."
            )
        current_time = _utc_datetime(record["event_at_utc"])
        if previous_time is not None and current_time < previous_time:
            raise HumanAdjudicationError("Workspace-event times move backwards.")
        _nonempty_text(record["actor_id"], "workspace-event actor ID", 256)
        event_type = record["event_type"]
        subject_hash = record["subject_sha256"]
        if not isinstance(subject_hash, str) or SHA256_RE.fullmatch(subject_hash) is None:
            raise HumanAdjudicationError("A workspace-event subject hash is invalid.")
        if abandoned:
            raise HumanAdjudicationError(
                "An abandoned workspace has a later event."
            )
        if event_type == "initialized":
            if (
                contract["proposed"]
                or event_index != 1
                or initialized_seen
                or record["actor_id"] != "workspace_initializer"
                or record["event_at_utc"] != manifest.get("created_at_utc")
                or record["subject_kind"] != "component_config"
                or record["subject_id"] != COMPONENT_ID
                or subject_hash != contract["config_sha256"]
            ):
                raise HumanAdjudicationError(
                    "The formal initialization event is invalid."
                )
            initialized_seen = True
        elif event_type in {"batch_submitted", "batch_revised", "group_registry_revised"}:
            binding = revision_events.get(subject_hash)
            if (
                binding is None
                or subject_hash in consumed_revisions
                or record["subject_kind"] != "revision_event"
                or record["subject_id"] != _revision_event_subject(binding)
                or record["actor_id"] != binding["reviewer_id"]
                or record["event_at_utc"] != binding["recorded_at_utc"]
                or completion_seen
            ):
                raise HumanAdjudicationError(
                    "A workspace revision event lacks its unique bound revision."
                )
            expected_type = (
                "group_registry_revised"
                if binding["revision_kind"] == "mapping_group"
                else "batch_submitted"
                if binding["revision"] == 2
                else "batch_revised"
            )
            if event_type != expected_type:
                raise HumanAdjudicationError(
                    "A workspace revision event has the wrong transition type."
                )
            consumed_revisions.add(subject_hash)
        elif event_type == "attestation_added":
            binding = attestations.get(subject_hash)
            if (
                binding is None
                or subject_hash in consumed_attestations
                or record["subject_kind"] != "batch_attestation"
                or record["subject_id"] != _attestation_event_subject(binding)
                or record["actor_id"] != binding["reviewer_id"]
                or record["event_at_utc"] != binding["recorded_at_utc"]
                or completion_seen
            ):
                raise HumanAdjudicationError(
                    "An attestation-added event lacks its unique attestation."
                )
            consumed_attestations.add(subject_hash)
        elif event_type == "validation_failed":
            if (
                record["subject_kind"] != "component_config"
                or record["subject_id"] != COMPONENT_ID
                or subject_hash != contract["config_sha256"]
            ):
                raise HumanAdjudicationError(
                    "A validation-failed event has an invalid contract binding."
                )
        elif event_type == "human_review_complete_unfrozen":
            if (
                contract["proposed"]
                or completion_seen
                or not data_complete
                or consumed_revisions != set(revision_events)
                or consumed_attestations != set(attestations)
                or single_reviewer_id is None
                or record["actor_id"] != single_reviewer_id
                or record["subject_kind"] != "active_workspace_state"
                or record["subject_id"] != COMPONENT_ID
                or subject_hash != active_state_sha256
            ):
                raise HumanAdjudicationError(
                    "A human-review-complete event precedes validated completion."
                )
            completion_seen = True
        elif event_type == "abandoned":
            if (
                record["subject_kind"] != "component_config"
                or record["subject_id"] != COMPONENT_ID
                or subject_hash != contract["config_sha256"]
            ):
                raise HumanAdjudicationError(
                    "An abandoned event has an invalid contract binding."
                )
            abandoned = True
        else:  # pragma: no cover - exhaustive over the frozen tuple
            raise HumanAdjudicationError("A workspace event is unsupported.")
        previous_hash = _record_sha(record)
        previous_time = current_time
    if not contract["proposed"] and not initialized_seen:
        raise HumanAdjudicationError("A formal workspace lacks initialization.")
    if consumed_revisions != set(revision_events):
        raise HumanAdjudicationError(
            "Workspace events do not conserve revision events."
        )
    if consumed_attestations != set(attestations):
        raise HumanAdjudicationError(
            "Workspace events do not conserve attestation records."
        )
    return {
        "completion_seen": completion_seen,
        "abandoned": abandoned,
        "event_count": len(records) - 1,
    }


def _validate_evidence_registry(
    snapshot: Mapping[str, Any],
    contract: Mapping[str, Any],
    workspace: Path,
    all_review_ids: set[str],
    file_snapshots: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], set[str]]:
    records = _read_ndjson_snapshot(snapshot, "The evidence registry")
    if not records:
        raise HumanAdjudicationError("The evidence registry is empty.")
    expected_header = {
        "record_type": "evidence_registry_begin",
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "config_sha256": contract["config_sha256"],
        "initial_evidence_count": 0,
    }
    if records[0] != expected_header:
        raise HumanAdjudicationError("The evidence-registry header changed.")
    registry_config = contract["config"].get("evidence_registry")
    if not isinstance(registry_config, Mapping):
        # A synthetic or early proposal may omit the policy only while empty.
        if len(records) != 1:
            raise HumanAdjudicationError("Evidence entries require a frozen registry policy.")
        return {}, set()
    allowed_namespaces = registry_config.get("allowed_namespaces")
    if not isinstance(allowed_namespaces, list):
        raise HumanAdjudicationError("The evidence namespace policy is invalid.")
    registry: dict[str, Mapping[str, Any]] = {}
    document_paths: set[str] = set()
    previous_id: str | None = None
    source_cfg = contract["config"]["source_artifact"]
    for raw_record in records[1:]:
        record = _exact_keys(
            raw_record,
            {"record_type", "evidence_id", "namespace", "locator"},
            "evidence-registry entry",
        )
        evidence_id = record["evidence_id"]
        namespace = record["namespace"]
        locator = record["locator"]
        if (
            record["record_type"] != "evidence_registry_entry"
            or not isinstance(evidence_id, str)
            or EVIDENCE_ID_RE.fullmatch(evidence_id) is None
            or evidence_id in registry
            or (previous_id is not None and evidence_id <= previous_id)
            or namespace not in allowed_namespaces
            or not isinstance(locator, Mapping)
        ):
            raise HumanAdjudicationError("An evidence-registry identity is invalid.")
        previous_id = evidence_id
        if namespace == "local_tuple":
            locator = _exact_keys(
                locator,
                {
                    "local_evidence_raw_sha256", "stage", "tuple_kind",
                    "ordinal_within_kind",
                },
                "local-tuple evidence locator",
            )
            local_policy = contract["config"]["evidence_registry"][
                "local_tuple"
            ]
            allowed_stage_kind = set(local_policy["allowed_stage_kind"])
            stage_kind = f"{locator['stage']}:{locator['tuple_kind']}"
            if (
                locator["local_evidence_raw_sha256"]
                != source_cfg["local_evidence"]["raw_sha256"]
                or not isinstance(locator["stage"], str)
                or not locator["stage"]
                or not isinstance(locator["tuple_kind"], str)
                or not locator["tuple_kind"]
                or stage_kind not in allowed_stage_kind
            ):
                raise HumanAdjudicationError("A local-tuple evidence locator is invalid.")
            _require_positive_int(
                locator["ordinal_within_kind"], "local-tuple ordinal"
            )
        elif namespace == "source_template":
            locator = _exact_keys(
                locator,
                {"source_template_raw_sha256", "private_review_id"},
                "source-template evidence locator",
            )
            review_id = locator["private_review_id"]
            expected_template_hash = (
                source_cfg["semantic_template"]["raw_sha256"]
                if isinstance(review_id, str) and SEMANTIC_ID_RE.fullmatch(review_id)
                else source_cfg["route_template"]["raw_sha256"]
                if isinstance(review_id, str) and ROUTE_ID_RE.fullmatch(review_id)
                else None
            )
            if review_id not in all_review_ids or locator["source_template_raw_sha256"] != expected_template_hash:
                raise HumanAdjudicationError("A source-template evidence locator is invalid.")
        elif namespace == "versioned_document":
            locator = _exact_keys(
                locator,
                {
                    "evidence_id", "document_sha256", "document_version",
                    "accessed_at_utc", "private_local_path",
                },
                "versioned-document evidence locator",
            )
            if (
                locator["evidence_id"] != evidence_id
                or not isinstance(locator["document_sha256"], str)
                or SHA256_RE.fullmatch(locator["document_sha256"]) is None
                or not _strict_utc(locator["accessed_at_utc"])
            ):
                raise HumanAdjudicationError("A versioned-document locator is invalid.")
            _nonempty_text(locator["document_version"], "document version", 1024)
            relative_path = _safe_relative(
                locator["private_local_path"], "private evidence document"
            ).as_posix()
            if (
                not relative_path.startswith("evidence-registry/documents/")
                or len(Path(relative_path).parts) != 3
                or relative_path in document_paths
            ):
                raise HumanAdjudicationError("A private evidence-document path is invalid.")
            document_snapshot = file_snapshots.get(relative_path)
            if (
                document_snapshot is None
                or document_snapshot["mode"] != 0o600
                or document_snapshot["nlink"] != 1
                or document_snapshot["sha256"] != locator["document_sha256"]
            ):
                raise HumanAdjudicationError("A private evidence document is absent or changed.")
            document_paths.add(relative_path)
        else:
            raise HumanAdjudicationError("An evidence namespace is unsupported.")
        registry[evidence_id] = {
            "namespace": namespace,
            "locator": dict(locator),
        }
    return registry, document_paths


def _resolve_local_tuple_evidence(
    index_snapshot: Mapping[str, Any],
    config: Mapping[str, Any],
    evidence_registry: dict[str, Mapping[str, Any]],
    semantic_items: Sequence[Mapping[str, Any]],
) -> None:
    """Resolve local locators from the immutable private ordinal index."""
    index = _local_index_contract(config)
    payload = index_snapshot.get("payload")
    if (
        not isinstance(payload, bytes)
        or index_snapshot.get("mode") != 0o600
        or index_snapshot.get("nlink") != 1
        or index_snapshot.get("bytes") != index["index_bytes"]
        or index_snapshot.get("sha256") != index["index_sha256"]
    ):
        raise HumanAdjudicationError(
            "The private local-evidence ordinal index changed."
        )
    semantic_count = len(semantic_items)
    targets: dict[tuple[str, int], list[str]] = {}
    for evidence_id, entry in evidence_registry.items():
        if entry["namespace"] != "local_tuple":
            continue
        locator = entry["locator"]
        stage_kind = f"{locator['stage']}:{locator['tuple_kind']}"
        ordinal = locator["ordinal_within_kind"]
        maximum = index["kind_counts"].get(stage_kind)
        if type(ordinal) is not int or ordinal <= 0 or maximum is None or ordinal > maximum:
            raise HumanAdjudicationError(
                "A local-evidence ordinal is outside its frozen kind block."
            )
        if stage_kind in index["bridge_blocks"]:
            targets.setdefault((stage_kind, ordinal), []).append(evidence_id)

    for (stage_kind, ordinal), evidence_ids in targets.items():
        block_offset, _ = index["bridge_blocks"][stage_kind]
        record_offset = (
            block_offset + ordinal - 1
        ) * LOCAL_EVIDENCE_INDEX_RECORD_BYTES
        raw = payload[record_offset : record_offset + LOCAL_EVIDENCE_INDEX_RECORD_BYTES]
        if len(raw) != LOCAL_EVIDENCE_INDEX_RECORD_BYTES:
            raise HumanAdjudicationError(
                "A bridge index lookup escaped the immutable index."
            )
        member_count, *sequences = struct.unpack(">B4I", raw)
        active = sequences[:member_count] if member_count <= 4 else []
        padding = sequences[member_count:] if member_count <= 4 else sequences
        if (
            member_count > 4
            or any(value == 0 or value > semantic_count for value in active)
            or any(left >= right for left, right in zip(active, active[1:]))
            or any(value != 0 for value in padding)
        ):
            raise HumanAdjudicationError(
                "A bridge index record violates its fixed binary encoding."
            )
        members = frozenset(f"S{sequence:06d}" for sequence in active)
        for evidence_id in evidence_ids:
            evidence_registry[evidence_id] = {
                **evidence_registry[evidence_id],
                "semantic_members": members,
            }

def _walk_workspace_files(workspace: Path) -> tuple[set[str], list[Path]]:
    files: set[str] = set()
    directories: list[Path] = []

    def visit(descriptor: int, relative: Path) -> None:
        before = os.fstat(descriptor)
        if not stat.S_ISDIR(before.st_mode):
            raise HumanAdjudicationError(
                "The workspace contains a non-directory traversal node."
            )
        directories.append(workspace / relative)
        try:
            names = sorted(os.listdir(descriptor))
        except OSError:
            raise HumanAdjudicationError(
                "The workspace inventory could not be read safely."
            ) from None
        for name in names:
            if name in {".", ".."} or "/" in name:
                raise HumanAdjudicationError(
                    "The workspace contains an unsafe entry name."
                )
            try:
                value = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except OSError:
                raise HumanAdjudicationError(
                    "The workspace inventory changed during traversal."
                ) from None
            child_relative = relative / name
            if stat.S_ISDIR(value.st_mode):
                child_descriptor: int | None = None
                try:
                    child_descriptor = os.open(
                        name, DIRECTORY_OPEN_FLAGS, dir_fd=descriptor
                    )
                    opened = os.fstat(child_descriptor)
                    if not _same_open_snapshot(value, opened):
                        raise HumanAdjudicationError(
                            "A workspace directory changed before traversal."
                        )
                    visit(child_descriptor, child_relative)
                except HumanAdjudicationError:
                    raise
                except OSError:
                    raise HumanAdjudicationError(
                        "The workspace contains a symlink or unsafe directory."
                    ) from None
                finally:
                    if child_descriptor is not None:
                        os.close(child_descriptor)
            elif stat.S_ISREG(value.st_mode):
                files.add(child_relative.as_posix())
            else:
                raise HumanAdjudicationError(
                    "The workspace contains a symlink or non-regular file."
                )
        after = os.fstat(descriptor)
        if not _same_open_snapshot(before, after):
            raise HumanAdjudicationError(
                "The workspace directory changed during inventory traversal."
            )

    descriptor: int | None = None
    try:
        descriptor, _ = _open_directory_fd(workspace)
        visit(descriptor, Path("."))
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return files, directories


def validate_human_adjudication_workspace(
    root: Path,
    workspace_directory: Path,
    config_path: Path = CONFIG_PATH,
    *,
    allow_proposed: bool = False,
    _logical_workspace_directory: Path | None = None,
) -> dict[str, Any]:
    """Validate source conservation, immutable views, ledgers, and closure.

    ``allow_proposed`` is a Python-only synthetic-test hook.  A preview accepted
    through it remains non-formal and becomes invalid when the config is frozen.
    """
    root = root.resolve(strict=True)
    contract = _load_contract(root, config_path, allow_proposed=allow_proposed)
    _require_formal_preregistration_ready(root, contract)
    source_inventory = _source_inventory(root, contract)
    workspace_relative = _safe_relative(
        workspace_directory.as_posix(), "human-adjudication workspace"
    )
    workspace = _project_path(
        root, workspace_relative.as_posix(), "human-adjudication workspace"
    )
    logical_workspace_relative = workspace_relative
    if _logical_workspace_directory is not None:
        logical_workspace_relative = _safe_relative(
            _logical_workspace_directory.as_posix(),
            "logical human-adjudication workspace",
        )
        if (
            workspace_relative.parent != logical_workspace_relative.parent
            or not workspace_relative.name.startswith(
                ".txn-human-adjudication-"
            )
            or workspace_relative == logical_workspace_relative
        ):
            raise HumanAdjudicationError(
                "The staged workspace logical-path binding is invalid."
            )
    workspace_initial = _snapshot_directory(workspace, "The human-adjudication workspace")
    if workspace_initial["mode"] != 0o700 or not _git_ignored(root, workspace):
        raise HumanAdjudicationError("The human-adjudication workspace is not private and Git-ignored.")

    source_cfg = contract["config"]["source_artifact"]
    semantic_template = _stream_records(
        source_inventory["snapshots"]["semantic_template"], source_cfg["semantic_template"], "The semantic review template"
    )
    route_template = _stream_records(
        source_inventory["snapshots"]["route_template"], source_cfg["route_template"], "The route review template"
    )
    semantic_items = _parse_semantic_template(semantic_template, source_cfg["semantic_template"])
    route_items, route_memberships = _parse_route_template(route_template, source_cfg["route_template"])
    batch_size = contract["config"]["workspace"]["semantic_batch_size"]
    batch_count = contract["config"]["workspace"]["semantic_batch_count"]
    if (len(semantic_items) + batch_size - 1) // batch_size != batch_count:
        raise HumanAdjudicationError("The semantic source no longer fits the fixed batch partition.")
    paths = _workspace_paths(workspace, batch_count)
    actual_files, directories = _walk_workspace_files(workspace)
    core_files = _expected_workspace_entries(paths)
    if not core_files.issubset(actual_files) or any(
        relative not in core_files
        and not relative.startswith("evidence-registry/documents/")
        for relative in actual_files
    ):
        raise HumanAdjudicationError("The workspace file inventory has an omission or unexpected file.")
    allowed_top_level = set(
        contract["config"]["workspace"]["allowed_top_level_entries"]
    )
    if set(workspace_initial["entries"]) != allowed_top_level:
        raise HumanAdjudicationError("The strict workspace top-level inventory changed.")
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
    if {path.relative_to(workspace).as_posix() for path in directories} != expected_directories:
        raise HumanAdjudicationError("The strict workspace directory inventory changed.")
    if any(_mode(directory) != "0700" for directory in directories):
        raise HumanAdjudicationError("A workspace directory has an unsafe mode.")

    initial_snapshots: dict[str, dict[str, Any]] = {}
    for relative in sorted(actual_files):
        snapshot = _snapshot_file(
            workspace / relative,
            f"Workspace file {relative}",
            retain_payload=True,
        )
        if snapshot["mode"] != 0o600 or snapshot["nlink"] != 1:
            raise HumanAdjudicationError(
                "A workspace file has an unsafe mode or link count."
            )
        initial_snapshots[relative] = snapshot
    manifest = _validate_public_json(
        initial_snapshots["workspace-manifest.json"], "The workspace manifest"
    )
    expected_status = "structural_preview" if contract["proposed"] else "initialized"
    expected_parent = _safe_relative(
        (
            contract["config"]["structural_preview"]["artifact_parent"]
            if contract["proposed"]
            else contract["config"]["workspace"]["artifact_parent"]
        ),
        "configured workspace parent",
    )
    if (
        manifest.get("component_id") != COMPONENT_ID
        or manifest.get("status") != expected_status
        or manifest.get("formal_workspace") is contract["proposed"]
        or manifest.get("preview_cannot_be_upgraded") is not contract["proposed"]
        or manifest.get("artifact_directory")
        != logical_workspace_relative.as_posix()
        or workspace.parent.relative_to(root) != expected_parent
        or manifest.get("guards")
        != _initial_workspace_guards(proposed=contract["proposed"])
    ):
        raise HumanAdjudicationError("The workspace manifest lifecycle or identity changed.")
    lineage = manifest.get("component_lineage")
    if (
        not isinstance(lineage, Mapping)
        or lineage.get("config") != config_path.as_posix()
        or lineage.get("config_sha256") != contract["config_sha256"]
        or lineage.get("generator_bundle_sha256") != contract["bundle"]["bundle_sha256"]
    ):
        raise HumanAdjudicationError("The workspace component lineage changed.")
    source = contract["config"]["source_artifact"]
    index_contract = _local_index_contract(contract["config"])
    expected_source_lineage = {
        "artifact_directory": source["directory"],
        "component_id": source["component_id"],
        "manifest_sha256": source["manifest_sha256"],
        "aggregate_summary_sha256": source["aggregate_summary_sha256"],
        "audit_sha256": source["audit_sha256"],
        "semantic_template_sha256": source["semantic_template"]["stored_sha256"],
        "route_template_sha256": source["route_template"]["stored_sha256"],
        "local_evidence_sha256": source["local_evidence"]["stored_sha256"],
        "local_evidence_bridge_index_sha256": index_contract["index_sha256"],
        "ndc_decision_config_sha256": contract["config"]["ndc_decision"][
            "config_sha256"
        ],
    }
    if manifest.get("source_lineage") != expected_source_lineage:
        raise HumanAdjudicationError("The workspace source lineage changed.")
    expected_cardinality = {
        "semantic_items": len(semantic_items),
        "semantic_batches": batch_count,
        "semantic_batch_size": batch_size,
        "route_items": len(route_items),
        "route_batches": 1,
        "route_nonnull_memberships": source["route_template"][
            "source_specific_nonnull_memberships"
        ],
        "route_sql_null_memberships": source["route_template"][
            "source_specific_sql_null_memberships"
        ],
        "route_typed_memberships": len(route_memberships),
        "local_evidence_bridge_index_records": index_contract["index_records"],
        "mapping_groups": 0,
    }
    if manifest.get("cardinality") != expected_cardinality:
        raise HumanAdjudicationError("The workspace cardinality changed.")

    workspace_event_records = _read_ndjson_snapshot(
        initial_snapshots["workspace-events.jsonl"],
        "The workspace-event ledger",
    )
    revision_event_records = _read_ndjson_snapshot(
        initial_snapshots["revisions/revision-events.jsonl"],
        "The revision-event ledger",
    )
    all_review_ids = {
        item["review_id"] for item in [*semantic_items, *route_items]
    }
    evidence_registry, document_paths = _validate_evidence_registry(
        initial_snapshots["evidence-registry/evidence-registry.jsonl"],
        contract,
        workspace,
        all_review_ids,
        initial_snapshots,
    )
    if actual_files != core_files | document_paths:
        raise HumanAdjudicationError(
            "The workspace document inventory differs from the evidence registry."
        )
    _resolve_local_tuple_evidence(
        initial_snapshots[LOCAL_EVIDENCE_INDEX_FILE],
        contract["config"],
        evidence_registry,
        semantic_items,
    )
    immutable_manifest = manifest.get("immutable_source_files")
    if not isinstance(immutable_manifest, list) or len(immutable_manifest) != batch_count + 2:
        raise HumanAdjudicationError("The immutable source manifest inventory changed.")
    immutable_by_file = {
        item.get("file"): item for item in immutable_manifest if isinstance(item, Mapping)
    }
    if len(immutable_by_file) != len(immutable_manifest):
        raise HumanAdjudicationError("The immutable source manifest repeats a file.")
    expected_index_manifest = {
        "file": LOCAL_EVIDENCE_INDEX_FILE,
        "sha256": index_contract["index_sha256"],
        "bytes": index_contract["index_bytes"],
        "mode": "0600",
        "encoding": LOCAL_EVIDENCE_INDEX_ENCODING,
        "records": index_contract["index_records"],
        "source_local_evidence_raw_sha256": index_contract[
            "source_local_evidence_raw_sha256"
        ],
        "bridge_blocks": [
            {
                "stage_kind": stage_kind,
                "offset_records": index_contract["bridge_blocks"][stage_kind][0],
                "records": index_contract["bridge_blocks"][stage_kind][1],
            }
            for stage_kind in SOURCE_BRIDGE_STAGE_KIND_ORDER
        ],
    }
    if immutable_by_file.get(LOCAL_EVIDENCE_INDEX_FILE) != expected_index_manifest:
        raise HumanAdjudicationError(
            "The immutable local-evidence index manifest binding changed."
        )

    semantic_active: dict[str, Mapping[str, Any]] = {}
    semantic_all_reviewed = True
    semantic_reviewed = 0
    batch_bindings: dict[tuple[str, int], dict[str, Any]] = {}
    human_reviewers: set[str] = set()
    expected_revision_events: dict[
        tuple[str, str, int], Mapping[str, Any]
    ] = {}
    for batch_index, ((source_relative, _), (ledger_relative, _)) in enumerate(
        zip(paths["semantic_source"], paths["semantic_decisions"], strict=True), start=1
    ):
        expected_items = semantic_items[(batch_index - 1) * batch_size:batch_index * batch_size]
        source_snapshot = initial_snapshots[source_relative]
        declared = immutable_by_file.get(source_relative)
        if not isinstance(declared, Mapping) or declared.get("sha256") != source_snapshot["sha256"] or declared.get("bytes") != source_snapshot["bytes"]:
            raise HumanAdjudicationError("An immutable semantic source file changed from its manifest binding.")
        _validate_source_batch(
            _read_ndjson_snapshot(source_snapshot, "An immutable semantic source batch"),
            "semantic", batch_index, batch_count, expected_items, (),
        )
        (
            active,
            all_reviewed,
            reviewed,
            active_hash,
            batch_reviewers,
            batch_revision_events,
        ) = _validate_decision_ledger(
            _read_ndjson_snapshot(initial_snapshots[ledger_relative], "A semantic decision ledger"),
            "semantic", batch_index, batch_count, source_relative, source_snapshot,
            [item["review_id"] for item in expected_items], contract,
            evidence_registry,
        )
        overlap = set(semantic_active).intersection(active)
        if overlap:
            raise HumanAdjudicationError("Semantic review IDs overlap across batches.")
        semantic_active.update(active)
        semantic_all_reviewed = semantic_all_reviewed and all_reviewed
        semantic_reviewed += reviewed
        human_reviewers.update(batch_reviewers)
        overlap_revisions = set(expected_revision_events).intersection(
            batch_revision_events
        )
        if overlap_revisions:
            raise HumanAdjudicationError(
                "Decision revision-event identities overlap across batches."
            )
        expected_revision_events.update(batch_revision_events)
        batch_bindings[("semantic", batch_index)] = {
            "item_count": len(expected_items),
            "active_hash": active_hash,
            "ledger_sha256": initial_snapshots[ledger_relative]["sha256"],
        }
    if len(semantic_active) != len(semantic_items):
        raise HumanAdjudicationError("The semantic decision ledgers do not conserve the source universe.")

    route_source_relative = paths["route_source"][0][0]
    route_ledger_relative = paths["route_decisions"][0][0]
    route_source_snapshot = initial_snapshots[route_source_relative]
    declared = immutable_by_file.get(route_source_relative)
    if not isinstance(declared, Mapping) or declared.get("sha256") != route_source_snapshot["sha256"] or declared.get("bytes") != route_source_snapshot["bytes"]:
        raise HumanAdjudicationError("The immutable route source file changed from its manifest binding.")
    _validate_source_batch(
        _read_ndjson_snapshot(route_source_snapshot, "The immutable route source batch"),
        "route", 1, 1, route_items, route_memberships,
    )
    (
        route_active,
        route_all_reviewed,
        route_reviewed,
        route_active_hash,
        route_reviewers,
        route_revision_events,
    ) = _validate_decision_ledger(
        _read_ndjson_snapshot(initial_snapshots[route_ledger_relative], "The route decision ledger"),
        "route", 1, 1, route_source_relative, route_source_snapshot,
        [item["review_id"] for item in route_items], contract,
        evidence_registry,
    )
    batch_bindings[("route", 1)] = {
        "item_count": len(route_items),
        "active_hash": route_active_hash,
        "ledger_sha256": initial_snapshots[route_ledger_relative]["sha256"],
    }
    human_reviewers.update(route_reviewers)
    expected_revision_events.update(route_revision_events)
    groups, group_reviewers, group_revision_events = _validate_group_ledger(
        _read_ndjson_snapshot(
            initial_snapshots["semantic-groups/mapping-groups.jsonl"],
            "The mapping-group ledger",
        ),
        contract,
        set(semantic_active),
        semantic_active,
        evidence_registry,
    )
    human_reviewers.update(group_reviewers)
    expected_revision_events.update(group_revision_events)
    (
        current_attestations,
        attestation_reviewers,
        attestation_bindings,
        current_attestation_hashes,
    ) = _validate_attestation_ledger(
        _read_ndjson_snapshot(
            initial_snapshots["attestations/batch-attestations.jsonl"],
            "The batch-attestation ledger",
        ),
        contract,
        batch_bindings,
        initial_snapshots["semantic-groups/mapping-groups.jsonl"]["sha256"],
    )
    human_reviewers.update(attestation_reviewers)
    revision_events_by_hash, revision_event_reviewers = (
        _validate_revision_event_ledger(
            revision_event_records,
            contract,
            expected_revision_events,
        )
    )
    human_reviewers.update(revision_event_reviewers)
    human_records_present = bool(expected_revision_events or attestation_bindings)
    if human_records_present and len(human_reviewers) != 1:
        raise HumanAdjudicationError(
            "The single-reviewer contract has inconsistent human reviewer IDs."
        )
    semantic_complete = semantic_all_reviewed and all(
        ("semantic", index) in current_attestations
        for index in range(1, batch_count + 1)
    )
    route_complete = route_all_reviewed and ("route", 1) in current_attestations
    data_complete = semantic_complete and route_complete
    active_state_sha256 = _active_workspace_state_hash(
        batch_bindings,
        groups,
        current_attestation_hashes,
    )
    event_state = _validate_workspace_event_ledger(
        workspace_event_records,
        contract,
        manifest,
        revision_events_by_hash,
        attestation_bindings,
        data_complete=data_complete,
        active_state_sha256=active_state_sha256,
        single_reviewer_id=(
            next(iter(human_reviewers)) if len(human_reviewers) == 1 else None
        ),
    )

    # Close every source, config, implementation, workspace file, and inventory.
    _finish_source_closure(source_inventory, contract)
    for relative, initial in initial_snapshots.items():
        final = _snapshot_file(workspace / relative, f"Workspace file {relative}")
        if _seal(final) != _seal(initial):
            raise HumanAdjudicationError("A workspace file changed during validation.")
    final_files, final_directories = _walk_workspace_files(workspace)
    workspace_final = _snapshot_directory(workspace, "The human-adjudication workspace")
    if (
        final_files != actual_files
        or _directory_seal(workspace_final) != _directory_seal(workspace_initial)
        or [path.relative_to(workspace).as_posix() for path in final_directories]
        != [path.relative_to(workspace).as_posix() for path in directories]
    ):
        raise HumanAdjudicationError("The workspace inventory changed during validation.")

    review_started = (
        semantic_reviewed > 0
        or route_reviewed > 0
        or bool(groups)
        or bool(attestation_bindings)
    )
    if contract["proposed"]:
        lifecycle = "structural_preview"
        report_semantic_complete = False
        report_route_complete = False
    elif event_state["abandoned"]:
        lifecycle = "abandoned"
        report_semantic_complete = False
        report_route_complete = False
    elif data_complete and event_state["completion_seen"]:
        lifecycle = "human_review_complete_unfrozen"
        report_semantic_complete = True
        report_route_complete = True
    else:
        lifecycle = "review_in_progress" if review_started else expected_status
        report_semantic_complete = False
        report_route_complete = False
    return {
        "valid": True,
        "status": lifecycle,
        "formal_workspace": not contract["proposed"],
        "workspace": logical_workspace_relative.as_posix(),
        "semantic_items": len(semantic_items),
        "semantic_batches": batch_count,
        "reviewed_semantic_items": semantic_reviewed,
        "semantic_review_complete": report_semantic_complete,
        "route_items": len(route_items),
        "route_batches": 1,
        "route_typed_memberships": len(route_memberships),
        "route_sql_null_memberships": sum(item["raw_value_state"] == "sql_null" for item in route_memberships),
        "reviewed_route_items": route_reviewed,
        "route_review_complete": report_route_complete,
        "mapping_groups": len(groups),
        "reviewed_semantic_ledger_frozen": False,
        "route_mapping_frozen": False,
        "database_connected": False,
        "external_api_called": False,
        "llm_called": False,
    }


__all__ = [
    "CONFIG_PATH",
    "COMPONENT_ID",
    "GENERATOR_PATHS",
    "HumanAdjudicationError",
    "initialize_human_adjudication_workspace",
    "validate_human_adjudication_workspace",
]
