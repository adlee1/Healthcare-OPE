"""Independent structural audit of a formal Query-202 review workspace.

This module intentionally does not import the workspace generator or validator.
It re-parses the frozen source streams and the private workspace with its own
schema, hashing, revision-chain, evidence-resolution, and snapshot-closure
logic.  The resulting report is aggregate-only.

The workspace entry point has deliberately narrow scope: it audits a workspace
after human review, does not establish clinical correctness, and cannot make
the workspace eligible for the later separate freeze.  A separate entry point
independently audits the compiled artifact and writes the only audit eligible
for the freeze operation.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import tomllib
from typing import Any, Callable, Iterable, Mapping, Sequence
import zlib


CONFIG_PATH = Path(
    "config/preregistrations/d005_potassium_query202_human_adjudication.toml"
)
COMPONENT_ID = "D005-K-QUERY202-HUMAN-ADJUDICATION-v1"
SOURCE_COMPONENT_ID = "D005-K-QUERY202-ADJUDICATION-INPUT-v1"
NDC_COMPONENT_ID = "D005-K-QUERY202-NDC-EVIDENCE-MODE-v1"
BUNDLE_ENCODING = "uint32be_path_length+path_utf8+uint64be_content_length+content"
PLACEHOLDER = "UNSET_REQUIRED_BEFORE_FREEZE"
LOCAL_EVIDENCE_INDEX_FILE = "evidence-registry/local-evidence-bridge-index.bin"
LOCAL_EVIDENCE_INDEX_ENCODING = (
    "u8-member-count+4xu32be-review-sequence-zero-padded-v1"
)
LOCAL_EVIDENCE_INDEX_RECORD_BYTES = 17
TEST_ATTESTATION_PATH = "config/attestations/query202-human-adjudication-tests.json"
REQUIRED_TEST_PATHS = (
    "tests/test_query202_human_adjudication_preregistration.py",
    "tests/test_query202_human_adjudication_control_plane.py",
    "tests/test_query202_human_adjudication.py",
    "tests/test_query202_human_adjudication_writer.py",
    "tests/test_query202_human_adjudication_audit.py",
    "tests/test_query202_human_adjudication_finalize.py",
)
TEST_COMMAND_ARGV = (
    ".venv/bin/python",
    "-m",
    "unittest",
    "tests.test_query202_human_adjudication_preregistration",
    "tests.test_query202_human_adjudication_control_plane",
    "tests.test_query202_human_adjudication",
    "tests.test_query202_human_adjudication_writer",
    "tests.test_query202_human_adjudication_audit",
    "tests.test_query202_human_adjudication_finalize",
    "-v",
)
TEST_COMMAND_ENV = (
    ("HOME", ".attestation-home"),
    ("LC_ALL", "C"),
    ("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
    ("PYTHONDONTWRITEBYTECODE", "1"),
    ("PYTHONHASHSEED", "0"),
    ("PYTHONNOUSERSITE", "1"),
    ("PYTHONPATH", "src:."),
    ("PYTHONUTF8", "1"),
    ("TMPDIR", ".attestation-tmp"),
)
TEST_COMMAND = " ".join(
    [*(f"{key}={value}" for key, value in TEST_COMMAND_ENV), *TEST_COMMAND_ARGV]
)
TEST_EXECUTION_SNAPSHOT_ENCODING = (
    "ordered-path+normalized-config-or-file-sha256+size+mode+nlink-v2"
)
ORDERED_TEST_IDS_ENCODING = "uint32be-id-length+id-utf8-v1"
MUTATION_TEST_IDS_ENCODING = "canonical-json-utf8-sort-keys-no-whitespace-v1"
EXPECTED_TEST_COUNT = 135
EXPECTED_ORDERED_TEST_IDS_SHA256 = (
    "21016a33a706a060279241c5b0ecba304369de3d7fda5cc5b9ba45512797abc9"
)
EXPECTED_MUTATION_TEST_IDS_SHA256 = (
    "a6e147692a23ea83eba3c8f1cc2e090f58d656ec9202436c0ef70fdde0892ff5"
)
REQUIRED_MUTATION_CLASSES = (
    "missing_duplicate_or_conflicting_review_records",
    "stale_base_or_revision_chain_tamper",
    "forged_or_ineligible_evidence_reference",
    "reviewer_identity_or_human_attestation_tamper",
    "privacy_permission_or_gitignore_tamper",
    "symlink_parent_swap_or_toctou_tamper",
    "final_output_audit_or_freeze_inventory_tamper",
    "implementation_bundle_drift",
    "test_command_file_order_count_or_result_drift",
    "scientific_contract_or_lifecycle_gate_drift",
)
TEST_ATTESTATION_KEYS = {
    "schema_version",
    "component_id",
    "status",
    "test_command",
    "test_command_argv",
    "test_command_environment",
    "tests_run",
    "failures",
    "errors",
    "scientific_contract_sha256",
    "implementation_bundles",
    "test_files",
    "mutation_classes_passed",
    "ordered_test_ids_sha256",
    "mutation_test_ids_sha256",
    "execution_snapshot",
    "python_runtime",
}

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
AUDITOR_PATHS = (
    "src/april_repro/__init__.py",
    "src/april_repro/query202_human_adjudication_audit.py",
    "scripts/audit_potassium_query202_human_adjudication.py",
)
STATIC_TEST_SUPPORT_PATHS = (
    "tests/__init__.py",
    "Makefile",
    "scripts/report_potassium_query202_human_adjudication.py",
    "src/april_repro/cli.py",
    "src/april_repro/preregistration.py",
    "config/preregistrations/d005_potassium_query202_human_adjudication.toml",
    "config/preregistrations/d005_potassium_query202_adjudication_input.toml",
    "config/preregistrations/d005_potassium_query202_ndc_evidence_mode.toml",
)
TEST_EXECUTION_PATHS = tuple(
    dict.fromkeys(
        (*GENERATOR_PATHS, *AUDITOR_PATHS, *REQUIRED_TEST_PATHS, *STATIC_TEST_SUPPORT_PATHS)
    )
)

SEMANTIC_SCHEMA = "query202-reviewed-semantic-ledger-v1"
SEMANTIC_HASH_VERSION = "query202-semantic-decisions-v1"
GROUP_SCHEMA = "query202-semantic-mapping-groups-v1"
GROUP_HASH_VERSION = "query202-semantic-mapping-groups-v1"
ROUTE_SCHEMA = "query202-source-specific-exact-route-mapping-v1"
ROUTE_HASH_VERSION = "query202-source-specific-exact-route-mapping-v1"
ATTESTATION_SCHEMA = "query202-human-attestations-v1"
EVIDENCE_SCHEMA = "query202-evidence-registry-v1"
FINAL_MANIFEST_SCHEMA = "query202-human-adjudication-final-manifest-v1"
AGGREGATE_SUMMARY_SCHEMA = "query202-human-adjudication-aggregate-summary-v1"
FINAL_AUDIT_SCHEMA = "query202-human-adjudication-final-artifact-audit-v1"
FINAL_AUDITOR_COMPONENT_ID = "D005-K-QUERY202-HUMAN-ADJUDICATION-FINAL-AUDITOR-v1"
FINAL_AUDIT_METHOD = "independent-reimplementation-without-generator-imports-v1"
FINAL_ARTIFACT_PARENT = Path("artifacts/query202-human-adjudication")
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
FINAL_AUDIT_FILE = "audit-summary.json"
FINAL_FREEZE_FILE = "freeze-manifest.json"
FINAL_GZIP_ENCODING = "gzip+utf8+ndjson-single-member-mtime0-v1"
WORKSPACE_SNAPSHOT_VERSION = "query202-human-workspace-file-snapshot-v1"
REGISTERED_DOCUMENT_SET_VERSION = "query202-human-versioned-document-set-v1"
FINALIZER_GENERATOR_PATHS = (
    "src/april_repro/query202_human_adjudication_finalize.py",
    "scripts/compile_potassium_query202_human_adjudication.py",
    "scripts/freeze_potassium_query202_human_adjudication.py",
)
FINAL_DOWNSTREAM_FALSE_GUARDS = (
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

SEMANTIC_DIMENSIONS = (
    "product_identity",
    "dosage_form",
    "treatment_intent",
    "potassium_content",
    "meq_convertibility",
)
SEMANTIC_STATUSES = {"supported", "refuted", "uncertain"}
ROUTE_DECISIONS = {"iv", "noniv", "unknown"}
ROUTE_BASES = {
    "explicit_iv_route_semantics",
    "explicit_noniv_route_semantics",
    "ambiguous_or_insufficient_route_semantics",
    "other_documented_human_judgment",
}
UNCERTAINTY_BASES = {"insufficient_evidence", "conflicting_evidence"}

GENERAL_LOCAL_KINDS = {
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
}
GROUP_LOCAL_KINDS = {
    "202b:detail_seed_membership_bridge",
    "202b:emar_medication_detail_bridge",
    "202c:detail_pharmacy_prescription_bridge",
    "202c:head_pharmacy_prescription_bridge",
    "202c:pharmacy_prescription_bridge",
}
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
SOURCE_BRIDGE_STAGE_KIND_ORDER = tuple(
    item for item in SOURCE_LOCAL_STAGE_KIND_ORDER if item in GROUP_LOCAL_KINDS
)
GROUP_TUPLE_BINDINGS = {
    ("202b", "detail_seed_membership_bridge"): (
        ("product_description", "mimiciv_hosp.emar_detail.product_description"),
        (
            "product_description_other",
            "mimiciv_hosp.emar_detail.product_description_other",
        ),
    ),
    ("202b", "emar_medication_detail_bridge"): (
        ("head_medication", "mimiciv_hosp.emar.medication"),
        ("product_description", "mimiciv_hosp.emar_detail.product_description"),
        (
            "product_description_other",
            "mimiciv_hosp.emar_detail.product_description_other",
        ),
    ),
    ("202c", "detail_pharmacy_prescription_bridge"): (
        ("product_description", "mimiciv_hosp.emar_detail.product_description"),
        (
            "product_description_other",
            "mimiciv_hosp.emar_detail.product_description_other",
        ),
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

SEMANTIC_SET_VERSION = b"source-field-nonnull-exact-value-set-v1"
ROUTE_SET_VERSION = b"canonical-exact-nonnull-route-value-set-v1"
ACTIVE_BATCH_VERSION = b"query202-human-adjudication-active-batch-v1"
ACTIVE_WORKSPACE_STATE_VERSION = (
    b"query202-human-adjudication-active-workspace-state-v1"
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
REVISION_EVENT_KEYS = {
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
}
WORKSPACE_EVENT_KEYS = {
    "record_type",
    "event_index",
    "previous_event_sha256",
    "event_type",
    "event_at_utc",
    "actor_id",
    "subject_kind",
    "subject_id",
    "subject_sha256",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
SEMANTIC_ID_RE = re.compile(r"S[0-9]{6}\Z")
ROUTE_ID_RE = re.compile(r"R[0-9]{6}\Z")
EVIDENCE_ID_RE = re.compile(r"E[0-9]{6}\Z")
GROUP_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
UTC_RE = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,6})?Z\Z"
)
FINAL_DIRECTORY_RE = re.compile(r"[0-9]{8}T[0-9]{6}\.[0-9]{6}Z\Z")
READ_CHUNK_BYTES = 1024 * 1024
MAX_JSON_LINE_BYTES = 8 * 1024 * 1024
MAX_JSON_FILE_BYTES = 128 * 1024 * 1024
MAX_VALUE_UTF8_BYTES = 1024 * 1024
MAX_TEXT_BYTES = 16 * 1024
MAX_COUNT = (1 << 63) - 1


class HumanAdjudicationAuditError(RuntimeError):
    """Fail-closed structural-audit error with no private value content."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise HumanAdjudicationAuditError("A JSON object contains a duplicate key.")
        output[key] = value
    return output


def _reject_constant(_: str) -> None:
    raise HumanAdjudicationAuditError("A JSON value contains a non-finite number.")


def _json_loads(raw: bytes, label: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except HumanAdjudicationAuditError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HumanAdjudicationAuditError(
            f"{label} is not strict UTF-8 JSON."
        ) from None


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _record_sha(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(record)).hexdigest()


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
        raise HumanAdjudicationAuditError(
            "An audit document is not strict JSON."
        ) from None


def _sequence_hash(version: str, records: Sequence[Mapping[str, Any]]) -> str:
    encoded_version = version.encode("utf-8")
    digest = hashlib.sha256()
    digest.update(struct.pack(">I", len(encoded_version)))
    digest.update(encoded_version)
    digest.update(struct.pack(">Q", len(records)))
    for record in records:
        encoded = _canonical_json(record)
        digest.update(struct.pack(">Q", len(encoded)))
        digest.update(encoded)
    return digest.hexdigest()


def _audit_time(value: str | None) -> str:
    candidate = value or datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    if not _strict_utc(candidate):
        raise HumanAdjudicationAuditError("The final-audit time is invalid.")
    return candidate


def _exact_keys(value: object, keys: Iterable[str], label: str) -> Mapping[str, Any]:
    expected = set(keys)
    if not isinstance(value, Mapping) or set(value) != expected:
        raise HumanAdjudicationAuditError(f"{label} schema changed.")
    return value


def _positive_int(value: object, label: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if type(value) is not int or not minimum <= value <= MAX_COUNT:
        raise HumanAdjudicationAuditError(f"{label} is invalid.")
    return value


def _nonempty_text(value: object, label: str, maximum: int = MAX_TEXT_BYTES) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.encode("utf-8")) > maximum
    ):
        raise HumanAdjudicationAuditError(f"{label} is invalid.")
    return value


def _strict_utc(value: object) -> bool:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def _valid_strict_timestamp_leaf(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.strptime(value, "%Y%m%dT%H%M%S.%fZ")
    except ValueError:
        return False
    return parsed.strftime("%Y%m%dT%H%M%S.%fZ") == value


def _safe_relative(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise HumanAdjudicationAuditError(f"{label} path is invalid.")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise HumanAdjudicationAuditError(f"{label} path is unsafe.")
    return path


def _project_path(root: Path, value: object, label: str) -> Path:
    relative = _safe_relative(value, label)
    try:
        descriptor, _, _ = _open_beneath(root, root / relative, label)
    except HumanAdjudicationAuditError:
        raise
    except OSError:
        raise HumanAdjudicationAuditError(
            f"{label} is absent or escapes the project."
        ) from None
    else:
        os.close(descriptor)
    return root / relative


def _open_beneath(
    root: Path, path: Path, label: str
) -> tuple[int, os.stat_result, tuple[tuple[int, int, int], ...]]:
    """Open ``path`` through root-anchored, no-follow directory descriptors."""

    try:
        relative = path.relative_to(root)
    except ValueError:
        raise HumanAdjudicationAuditError(
            f"{label} escapes the project root."
        ) from None
    if not relative.parts:
        raise HumanAdjudicationAuditError(f"{label} must identify a child path.")
    root_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        root_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        root_flags |= os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        current = os.open(root, root_flags)
        descriptors.append(current)
        root_stat = os.fstat(current)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise HumanAdjudicationAuditError(
                "The project root is not a real directory."
            )
        parents: list[tuple[int, int, int]] = [
            (root_stat.st_dev, root_stat.st_ino, root_stat.st_mode)
        ]
        for index, part in enumerate(relative.parts):
            last = index == len(relative.parts) - 1
            flags = os.O_RDONLY
            if not last and hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            child = os.open(part, flags, dir_fd=current)
            descriptors.append(child)
            child_stat = os.fstat(child)
            if not last:
                if not stat.S_ISDIR(child_stat.st_mode):
                    raise HumanAdjudicationAuditError(
                        f"{label} has a non-directory parent component."
                    )
                parents.append(
                    (child_stat.st_dev, child_stat.st_ino, child_stat.st_mode)
                )
            current = child
        final_descriptor = descriptors.pop()
        final_stat = os.fstat(final_descriptor)
        return final_descriptor, final_stat, tuple(parents)
    except HumanAdjudicationAuditError:
        raise
    except OSError:
        raise HumanAdjudicationAuditError(
            f"{label} is absent, unsafe, or traverses a symlink."
        ) from None
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _same_stat(left: os.stat_result, right: os.stat_result) -> bool:
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


def _snapshot_file(
    path: Path,
    label: str,
    *,
    retain_payload: bool = False,
    root: Path | None = None,
    maximum_bytes: int | None = None,
) -> dict[str, Any]:
    descriptor: int | None = None
    pieces: list[bytes] | None = [] if retain_payload else None
    digest = hashlib.sha256()
    total = 0
    try:
        if root is not None:
            descriptor, before, parents = _open_beneath(root, path, label)
        else:
            initial = path.lstat()
            if not stat.S_ISREG(initial.st_mode):
                raise HumanAdjudicationAuditError(f"{label} must be a regular file.")
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(path, flags)
            before = os.fstat(descriptor)
            parents = ()
            if not _same_stat(initial, before):
                raise HumanAdjudicationAuditError(f"{label} changed before audit read.")
        if not stat.S_ISREG(before.st_mode):
            raise HumanAdjudicationAuditError(f"{label} must be a regular file.")
        if maximum_bytes is not None and before.st_size > maximum_bytes:
            raise HumanAdjudicationAuditError(f"{label} exceeds its size bound.")
        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            if maximum_bytes is not None and total > maximum_bytes:
                raise HumanAdjudicationAuditError(
                    f"{label} grew beyond its size bound."
                )
            if pieces is not None:
                pieces.append(chunk)
        after = os.fstat(descriptor)
    except HumanAdjudicationAuditError:
        raise
    except OSError:
        raise HumanAdjudicationAuditError(
            f"{label} could not be read safely."
        ) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    final_descriptor: int | None = None
    try:
        if root is not None:
            final_descriptor, final, final_parents = _open_beneath(root, path, label)
        else:
            final = path.lstat()
            final_parents = ()
    except (OSError, HumanAdjudicationAuditError):
        raise HumanAdjudicationAuditError(
            f"{label} changed during audit read."
        ) from None
    finally:
        if final_descriptor is not None:
            os.close(final_descriptor)
    if (
        not _same_stat(before, after)
        or not _same_stat(after, final)
        or total != after.st_size
    ):
        raise HumanAdjudicationAuditError(f"{label} changed during audit read.")
    if parents != final_parents:
        raise HumanAdjudicationAuditError(
            f"{label} parent chain changed during audit read."
        )
    return {
        "identity": (after.st_dev, after.st_ino),
        "full_mode": after.st_mode,
        "mode": stat.S_IMODE(after.st_mode),
        "nlink": after.st_nlink,
        "bytes": total,
        "mtime_ns": after.st_mtime_ns,
        "ctime_ns": after.st_ctime_ns,
        "parents": parents,
        "sha256": digest.hexdigest(),
        "payload": b"".join(pieces) if pieces is not None else None,
    }


def _snapshot_directory(
    path: Path, label: str, *, root: Path | None = None
) -> dict[str, Any]:
    descriptor: int | None = None
    try:
        if root is not None and path != root:
            descriptor, current, parents = _open_beneath(root, path, label)
        else:
            current = path.lstat()
            parents = ()
        if not stat.S_ISDIR(current.st_mode):
            raise HumanAdjudicationAuditError(f"{label} must be a real directory.")
        entries = tuple(
            sorted(
                os.listdir(descriptor) if descriptor is not None else os.listdir(path)
            )
        )
        if descriptor is not None:
            after = os.fstat(descriptor)
            if not _same_stat(current, after):
                raise HumanAdjudicationAuditError(
                    f"{label} changed during directory inventory."
                )
    except HumanAdjudicationAuditError:
        raise
    except OSError:
        raise HumanAdjudicationAuditError(
            f"{label} could not be inventoried."
        ) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return {
        "identity": (current.st_dev, current.st_ino),
        "full_mode": current.st_mode,
        "mode": stat.S_IMODE(current.st_mode),
        "mtime_ns": current.st_mtime_ns,
        "ctime_ns": current.st_ctime_ns,
        "parents": parents,
        "entries": entries,
    }


def _file_seal(value: Mapping[str, Any]) -> tuple[object, ...]:
    return tuple(
        value[key]
        for key in (
            "identity",
            "full_mode",
            "nlink",
            "bytes",
            "mtime_ns",
            "ctime_ns",
            "parents",
            "sha256",
        )
    )


def _directory_seal(value: Mapping[str, Any]) -> tuple[object, ...]:
    return tuple(
        value[key]
        for key in (
            "identity",
            "full_mode",
            "mtime_ns",
            "ctime_ns",
            "parents",
            "entries",
        )
    )


def _require_hash(snapshot: Mapping[str, Any], expected: object, label: str) -> None:
    if not isinstance(expected, str) or SHA256_RE.fullmatch(expected) is None:
        raise HumanAdjudicationAuditError(f"{label} configured hash is invalid.")
    if snapshot["sha256"] != expected:
        raise HumanAdjudicationAuditError(f"{label} hash changed.")


def _read_json(snapshot: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    raw = snapshot.get("payload")
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_JSON_FILE_BYTES:
        raise HumanAdjudicationAuditError(f"{label} size is invalid.")
    value = _json_loads(raw, label)
    if not isinstance(value, Mapping):
        raise HumanAdjudicationAuditError(f"{label} must contain one object.")
    return value


def _read_ndjson(raw: bytes, label: str) -> list[Mapping[str, Any]]:
    if not raw or not raw.endswith(b"\n"):
        raise HumanAdjudicationAuditError(f"{label} must be newline-terminated NDJSON.")
    records: list[Mapping[str, Any]] = []
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b"\n") or len(line) > MAX_JSON_LINE_BYTES:
            raise HumanAdjudicationAuditError(f"{label} has an invalid line boundary.")
        value = _json_loads(line[:-1], label)
        if not isinstance(value, Mapping):
            raise HumanAdjudicationAuditError(f"{label} contains a non-object.")
        records.append(value)
    return records


def _snapshot_records(
    snapshot: Mapping[str, Any], label: str
) -> list[Mapping[str, Any]]:
    raw = snapshot.get("payload")
    if not isinstance(raw, bytes):
        raise HumanAdjudicationAuditError(f"{label} payload is unavailable.")
    return _read_ndjson(raw, label)


def _one_gzip(stored: bytes, label: str) -> bytes:
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        raw = decoder.decompress(stored) + decoder.flush()
    except zlib.error:
        raise HumanAdjudicationAuditError(f"{label} gzip stream is invalid.") from None
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise HumanAdjudicationAuditError(f"{label} has extra or truncated gzip data.")
    return raw


def _stream_records(
    snapshot: Mapping[str, Any], section: Mapping[str, Any], label: str
) -> list[Mapping[str, Any]]:
    stored = snapshot.get("payload")
    if not isinstance(stored, bytes):
        raise HumanAdjudicationAuditError(f"{label} payload is unavailable.")
    raw = _one_gzip(stored, label)
    if len(raw) != section.get("raw_bytes") or hashlib.sha256(
        raw
    ).hexdigest() != section.get("raw_sha256"):
        raise HumanAdjudicationAuditError(f"{label} raw closure failed.")
    records = _read_ndjson(raw, label)
    if len(records) != section.get("records"):
        raise HumanAdjudicationAuditError(f"{label} record count changed.")
    return records


def _bundle(root: Path, paths: Sequence[str], label: str) -> dict[str, Any]:
    digest = hashlib.sha256()
    snapshots: dict[str, dict[str, Any]] = {}
    for relative_text in paths:
        relative = _safe_relative(relative_text, label)
        path = _project_path(root, relative.as_posix(), label)
        snapshot = _snapshot_file(path, label, retain_payload=True, root=root)
        raw = snapshot["payload"]
        assert isinstance(raw, bytes)
        encoded_path = relative_text.encode("utf-8")
        digest.update(struct.pack(">I", len(encoded_path)))
        digest.update(encoded_path)
        digest.update(struct.pack(">Q", len(raw)))
        digest.update(raw)
        snapshots[relative_text] = {**snapshot, "path": path}
    return {"sha256": digest.hexdigest(), "snapshots": snapshots}


def _git_ignored(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", relative.as_posix()],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _local_index_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    evidence = config.get("evidence_registry")
    source = config.get("source_artifact")
    value = evidence.get("local_tuple_index") if isinstance(evidence, Mapping) else None
    local = source.get("local_evidence") if isinstance(source, Mapping) else None
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
        or not isinstance(local, Mapping)
        or value.get("file") != LOCAL_EVIDENCE_INDEX_FILE
        or value.get("encoding") != LOCAL_EVIDENCE_INDEX_ENCODING
        or value.get("source_local_evidence_raw_sha256") != local.get("raw_sha256")
        or value.get("record_bytes") != LOCAL_EVIDENCE_INDEX_RECORD_BYTES
        or not isinstance(value.get("index_sha256"), str)
        or SHA256_RE.fullmatch(value["index_sha256"]) is None
        or value.get("all_stage_kind_order") != list(SOURCE_LOCAL_STAGE_KIND_ORDER)
        or value.get("bridge_stage_kind_order")
        != list(SOURCE_BRIDGE_STAGE_KIND_ORDER)
    ):
        raise HumanAdjudicationAuditError(
            "The local-evidence ordinal-index contract changed."
        )
    counts = value.get("all_stage_kind_ordinal_counts")
    offsets = value.get("bridge_block_offsets")
    bridge_counts = value.get("bridge_block_counts")
    if (
        not isinstance(counts, list)
        or len(counts) != len(SOURCE_LOCAL_STAGE_KIND_ORDER)
        or any(type(item) is not int or item < 0 for item in counts)
        or sum(counts) != local.get("unique_tuples")
        or not isinstance(offsets, list)
        or not isinstance(bridge_counts, list)
        or len(offsets) != len(SOURCE_BRIDGE_STAGE_KIND_ORDER)
        or len(bridge_counts) != len(SOURCE_BRIDGE_STAGE_KIND_ORDER)
        or any(type(item) is not int or item < 0 for item in offsets)
        or any(type(item) is not int or item < 0 for item in bridge_counts)
    ):
        raise HumanAdjudicationAuditError(
            "The local-evidence ordinal-index cardinalities changed."
        )
    by_kind = dict(zip(SOURCE_LOCAL_STAGE_KIND_ORDER, counts, strict=True))
    expected_counts = [by_kind[item] for item in SOURCE_BRIDGE_STAGE_KIND_ORDER]
    expected_offsets: list[int] = []
    running = 0
    for count in expected_counts:
        expected_offsets.append(running)
        running += count
    if (
        bridge_counts != expected_counts
        or offsets != expected_offsets
        or value.get("index_records") != running
        or value.get("index_bytes") != running * LOCAL_EVIDENCE_INDEX_RECORD_BYTES
    ):
        raise HumanAdjudicationAuditError(
            "The local-evidence ordinal-index block layout changed."
        )
    return {
        **dict(value),
        "kind_counts": by_kind,
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


def _contract_projection(config: Mapping[str, Any]) -> dict[str, Any]:
    projection = json.loads(json.dumps(config, ensure_ascii=False))
    for key in (
        "status",
        "rule_version",
        "execution_status",
        "execution_permitted",
        "implementation_state",
    ):
        projection.pop(key, None)
    implementation = projection.get("implementation")
    if isinstance(implementation, dict):
        implementation.pop("generator_bundle_sha256", None)
        implementation.pop("auditor_bundle_sha256", None)
    gate = projection.get("execution_gate")
    if isinstance(gate, dict):
        gate.pop("unresolved_blockers", None)
    attestation = projection.get("test_attestation")
    if isinstance(attestation, dict):
        for key in (
            "status",
            "attestation_path",
            "attestation_sha256",
        ):
            attestation.pop(key, None)
    return projection


def _scientific_contract_sha256(config: Mapping[str, Any]) -> str:
    payload = json.dumps(
        _contract_projection(config),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _execution_snapshot_summary(
    config: Mapping[str, Any], snapshots: Mapping[str, Mapping[str, Any]]
) -> dict[str, object]:
    digest = hashlib.sha256()
    normalized_config = json.dumps(
        _contract_projection(config),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    for relative in TEST_EXECUTION_PATHS:
        encoded_path = relative.encode("utf-8")
        snapshot = snapshots[relative]
        if relative == CONFIG_PATH.as_posix():
            content_sha256 = hashlib.sha256(normalized_config).digest()
            content_bytes = len(normalized_config)
        else:
            content_sha256 = bytes.fromhex(str(snapshot["sha256"]))
            content_bytes = int(snapshot["bytes"])
        digest.update(struct.pack(">I", len(encoded_path)))
        digest.update(encoded_path)
        digest.update(struct.pack(">Q", content_bytes))
        digest.update(content_sha256)
        digest.update(struct.pack(">I", int(snapshot["mode"])))
        digest.update(struct.pack(">Q", int(snapshot["nlink"])))
    return {
        "encoding": TEST_EXECUTION_SNAPSHOT_ENCODING,
        "file_count": len(TEST_EXECUTION_PATHS),
        "aggregate_sha256": digest.hexdigest(),
    }


def _python_runtime_snapshot(
    root: Path,
) -> tuple[dict[str, object], dict[str, Any], Path]:
    locator_snapshot, locked = _snapshot_runtime_locator(root)
    running = Path(sys.executable).resolve(strict=True)
    locked_stat = locked.stat()
    running_stat = running.stat()
    if (locked_stat.st_dev, locked_stat.st_ino) != (
        running_stat.st_dev,
        running_stat.st_ino,
    ):
        raise HumanAdjudicationAuditError(
            "The auditor is not running under the locked test interpreter."
        )
    snapshot = _snapshot_file(locked, "The locked Python runtime")
    if int(snapshot["mode"]) & 0o022:
        raise HumanAdjudicationAuditError(
            "The locked Python runtime has unsafe write permissions."
        )
    summary = {
        "binding": "resolved-regular-file-sha256+bytes+implementation+version-v1",
        "implementation": sys.implementation.name,
        "version": ".".join(str(item) for item in sys.version_info[:3]),
        "executable_sha256": snapshot["sha256"],
        "executable_bytes": snapshot["bytes"],
    }
    return summary, {**snapshot, "runtime_locator": locator_snapshot}, locked


def _snapshot_runtime_locator(root: Path) -> tuple[dict[str, Any], Path]:
    """Snapshot the locked interpreter locator separately from its target."""
    relative = _safe_relative(TEST_COMMAND_ARGV[0], "locked Python runtime locator")
    locator = root / relative
    descriptor: int | None = None
    fresh_descriptor: int | None = None
    try:
        descriptor, parent_stat, parent_ancestors = _open_beneath(
            root, locator.parent, "locked Python runtime locator parent"
        )
        parent_chain = parent_ancestors + (
            (parent_stat.st_dev, parent_stat.st_ino, parent_stat.st_mode),
        )
        initial = os.stat(locator.name, dir_fd=descriptor, follow_symlinks=False)
        if not (stat.S_ISLNK(initial.st_mode) or stat.S_ISREG(initial.st_mode)):
            raise HumanAdjudicationAuditError(
                "The locked Python runtime locator is unsafe."
            )
        link_target = (
            os.readlink(locator.name, dir_fd=descriptor)
            if stat.S_ISLNK(initial.st_mode)
            else None
        )
        resolved = locator.resolve(strict=True)
        after = os.stat(locator.name, dir_fd=descriptor, follow_symlinks=False)
        fresh_descriptor, fresh_parent_stat, fresh_ancestors = _open_beneath(
            root, locator.parent, "locked Python runtime locator parent"
        )
        fresh_chain = fresh_ancestors + (
            (
                fresh_parent_stat.st_dev,
                fresh_parent_stat.st_ino,
                fresh_parent_stat.st_mode,
            ),
        )
        final = os.stat(
            locator.name, dir_fd=fresh_descriptor, follow_symlinks=False
        )
    except HumanAdjudicationAuditError:
        raise
    except (OSError, RuntimeError):
        raise HumanAdjudicationAuditError(
            "The locked Python runtime locator is unavailable."
        ) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if fresh_descriptor is not None:
            os.close(fresh_descriptor)
    if (
        not _same_stat(initial, after)
        or not _same_stat(after, final)
        or parent_chain != fresh_chain
    ):
        raise HumanAdjudicationAuditError(
            "The locked Python runtime locator changed during audit."
        )
    return {
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


def _python_runtime_summary(root: Path) -> dict[str, object]:
    summary, _snapshot, _path = _python_runtime_snapshot(root)
    return summary


def _verify_test_attestation(
    root: Path,
    config: Mapping[str, Any],
    generator_sha256: str,
    auditor_sha256: str,
) -> dict[str, dict[str, Any]]:
    gate = config.get("test_attestation")
    expected_gate_keys = {
        "schema_version",
        "status",
        "attestation_path",
        "attestation_sha256",
        "project_local_path_when_passed",
        "project_local_public_evidence_required",
        "canonical_encoding",
        "test_command",
        "test_command_argv",
        "test_command_environment",
        "required_test_paths",
        "test_execution_paths",
        "execution_snapshot_encoding",
        "ordered_test_ids_encoding",
        "ordered_test_ids_sha256",
        "mutation_test_ids_encoding",
        "mutation_test_ids",
        "mutation_test_ids_sha256",
        "required_test_count",
        "failures_required",
        "errors_required",
        "required_mutation_classes",
        "attestation_contains_private_values",
        "attestation_contains_test_output",
        "private_safe_exact_schema_required",
        "builder_must_run_exact_test_command",
        "builder_must_execute_private_staged_snapshot",
        "every_test_id_must_report_ok",
        "python_runtime_path",
        "python_runtime_binding",
        "project_local_execution_closure_non_hermetic",
        "status_change_alone_may_enable_execution",
    }
    mutation_test_ids = gate.get("mutation_test_ids") if isinstance(gate, Mapping) else None
    mutation_test_ids_digest = None
    if isinstance(mutation_test_ids, Mapping):
        mutation_test_ids_digest = hashlib.sha256(
            json.dumps(
                mutation_test_ids, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
    if (
        not isinstance(gate, Mapping)
        or set(gate) != expected_gate_keys
        or gate.get("schema_version") != 2
        or gate.get("status") != "passed"
        or gate.get("attestation_path") != TEST_ATTESTATION_PATH
        or gate.get("project_local_path_when_passed") != TEST_ATTESTATION_PATH
        or gate.get("project_local_public_evidence_required") is not True
        or gate.get("canonical_encoding")
        != "canonical-json-utf8-sort-keys-no-whitespace-newline-v1"
        or gate.get("test_command") != TEST_COMMAND
        or gate.get("test_command_argv") != list(TEST_COMMAND_ARGV)
        or gate.get("test_command_environment")
        != [f"{key}={value}" for key, value in TEST_COMMAND_ENV]
        or gate.get("required_test_paths") != list(REQUIRED_TEST_PATHS)
        or gate.get("test_execution_paths") != list(TEST_EXECUTION_PATHS)
        or gate.get("execution_snapshot_encoding")
        != TEST_EXECUTION_SNAPSHOT_ENCODING
        or gate.get("ordered_test_ids_encoding") != ORDERED_TEST_IDS_ENCODING
        or gate.get("ordered_test_ids_sha256")
        != EXPECTED_ORDERED_TEST_IDS_SHA256
        or gate.get("mutation_test_ids_encoding")
        != MUTATION_TEST_IDS_ENCODING
        or not isinstance(mutation_test_ids, Mapping)
        or set(mutation_test_ids) != set(REQUIRED_MUTATION_CLASSES)
        or any(
            not isinstance(ids, list)
            or not ids
            or any(not isinstance(test_id, str) or not test_id for test_id in ids)
            for ids in mutation_test_ids.values()
        )
        or mutation_test_ids_digest != EXPECTED_MUTATION_TEST_IDS_SHA256
        or gate.get("mutation_test_ids_sha256")
        != EXPECTED_MUTATION_TEST_IDS_SHA256
        or gate.get("required_test_count") != EXPECTED_TEST_COUNT
        or gate.get("failures_required") != 0
        or gate.get("errors_required") != 0
        or gate.get("required_mutation_classes")
        != list(REQUIRED_MUTATION_CLASSES)
        or gate.get("attestation_contains_private_values") is not False
        or gate.get("attestation_contains_test_output") is not False
        or gate.get("private_safe_exact_schema_required") is not True
        or gate.get("builder_must_run_exact_test_command") is not True
        or gate.get("builder_must_execute_private_staged_snapshot") is not True
        or gate.get("every_test_id_must_report_ok") is not True
        or gate.get("python_runtime_path") != TEST_COMMAND_ARGV[0]
        or gate.get("python_runtime_binding")
        != "resolved-regular-file-sha256+bytes+implementation+version-v1"
        or gate.get("project_local_execution_closure_non_hermetic") is not True
        or gate.get("status_change_alone_may_enable_execution") is not False
        or not isinstance(gate.get("attestation_sha256"), str)
        or SHA256_RE.fullmatch(gate["attestation_sha256"]) is None
    ):
        raise HumanAdjudicationAuditError(
            "The frozen synthetic-test attestation contract changed."
        )
    snapshots: dict[str, dict[str, Any]] = {}
    attestation_path = _project_path(root, TEST_ATTESTATION_PATH, "test attestation")
    attestation_snapshot = _snapshot_file(
        attestation_path,
        "The synthetic-test attestation",
        retain_payload=True,
        root=root,
        maximum_bytes=64 * 1024,
    )
    snapshots[TEST_ATTESTATION_PATH] = {**attestation_snapshot, "path": attestation_path}
    payload = attestation_snapshot.get("payload")
    if (
        attestation_snapshot["sha256"] != gate["attestation_sha256"]
        or attestation_snapshot["bytes"] > 64 * 1024
        or attestation_snapshot["mode"] != 0o644
        or attestation_snapshot["nlink"] != 1
        or not isinstance(payload, bytes)
    ):
        raise HumanAdjudicationAuditError(
            "The synthetic-test attestation file changed."
        )
    value = _json_loads(payload, "The synthetic-test attestation")
    canonical = (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    if not isinstance(value, Mapping) or canonical != payload or set(value) != TEST_ATTESTATION_KEYS:
        raise HumanAdjudicationAuditError(
            "The synthetic-test attestation schema or encoding changed."
        )
    expected_test_files: list[dict[str, str]] = []
    for relative in REQUIRED_TEST_PATHS:
        path = _project_path(root, relative, "attested test file")
        snapshot = _snapshot_file(path, "An attested test file", root=root)
        if snapshot["mode"] & 0o022 or snapshot["nlink"] != 1:
            raise HumanAdjudicationAuditError(
                "An attested test file has an unsafe mode or link count."
            )
        snapshots[relative] = {**snapshot, "path": path}
        expected_test_files.append(
            {"path": relative, "file_sha256": snapshot["sha256"]}
        )
    expected_bundles = [
        {"name": "generator", "bundle_sha256": generator_sha256},
        {"name": "auditor", "bundle_sha256": auditor_sha256},
    ]
    execution_snapshots: dict[str, dict[str, Any]] = {}
    for relative in TEST_EXECUTION_PATHS:
        path = _project_path(root, relative, "test execution dependency")
        snapshot = _snapshot_file(path, "A test execution dependency", root=root)
        if snapshot["mode"] & 0o022 or snapshot["nlink"] != 1:
            raise HumanAdjudicationAuditError(
                "A test execution dependency has an unsafe mode or link count."
            )
        execution_snapshots[relative] = snapshot
        snapshots[relative] = {**snapshot, "path": path}
    expected_execution_snapshot = _execution_snapshot_summary(
        config, execution_snapshots
    )
    execution_snapshot = value.get("execution_snapshot")
    python_runtime = value.get("python_runtime")
    runtime_summary, runtime_snapshot, runtime_path = _python_runtime_snapshot(root)
    if (
        value.get("schema_version") != 2
        or value.get("component_id") != COMPONENT_ID
        or value.get("status") != "passed"
        or value.get("test_command") != TEST_COMMAND
        or value.get("test_command_argv") != list(TEST_COMMAND_ARGV)
        or value.get("test_command_environment")
        != [f"{key}={item}" for key, item in TEST_COMMAND_ENV]
        or value.get("tests_run") != EXPECTED_TEST_COUNT
        or value.get("failures") != 0
        or value.get("errors") != 0
        or value.get("scientific_contract_sha256")
        != _scientific_contract_sha256(config)
        or value.get("implementation_bundles") != expected_bundles
        or value.get("test_files") != expected_test_files
        or value.get("mutation_classes_passed")
        != list(REQUIRED_MUTATION_CLASSES)
        or value.get("ordered_test_ids_sha256")
        != EXPECTED_ORDERED_TEST_IDS_SHA256
        or value.get("mutation_test_ids_sha256")
        != EXPECTED_MUTATION_TEST_IDS_SHA256
        or not isinstance(execution_snapshot, Mapping)
        or set(execution_snapshot)
        != {"encoding", "file_count", "aggregate_sha256"}
        or execution_snapshot != expected_execution_snapshot
        or not isinstance(python_runtime, Mapping)
        or set(python_runtime)
        != {
            "binding",
            "implementation",
            "version",
            "executable_sha256",
            "executable_bytes",
        }
        or python_runtime != runtime_summary
    ):
        raise HumanAdjudicationAuditError(
            "The synthetic-test attestation does not bind the formal contract."
        )
    # The resolved interpreter may live outside the project and may legitimately
    # have multiple hard links.  Bind its full descriptor snapshot for TOCTOU
    # stability without applying the project-file nlink==1 policy.
    snapshots["<locked-python-runtime>"] = {
        **runtime_snapshot,
        "path": runtime_path,
        "project_root_anchored": False,
    }
    return snapshots


def _reopen_test_attestation_closure_file(
    root: Path, initial: Mapping[str, Any]
) -> dict[str, Any]:
    initial_locator = initial.get("runtime_locator")
    if isinstance(initial_locator, Mapping):
        final_locator, resolved = _snapshot_runtime_locator(root)
        if (
            _runtime_locator_seal(final_locator)
            != _runtime_locator_seal(initial_locator)
            or resolved != initial.get("path")
        ):
            raise HumanAdjudicationAuditError(
                "The locked Python runtime locator changed during audit."
            )
    project_root = root if initial.get("project_root_anchored", True) else None
    return _snapshot_file(
        initial["path"],
        "A synthetic-test attestation closure file",
        root=project_root,
    )


def _load_contract(root: Path, config_path: Path) -> dict[str, Any]:
    path = _project_path(root, config_path.as_posix(), "audit config")
    snapshot = _snapshot_file(
        path, "The human-adjudication config", retain_payload=True, root=root
    )
    raw = snapshot["payload"]
    assert isinstance(raw, bytes)
    try:
        config = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise HumanAdjudicationAuditError(
            "The human-adjudication config is invalid."
        ) from None
    if config.get("schema_version") != 1 or config.get("component_id") != COMPONENT_ID:
        raise HumanAdjudicationAuditError("The audit component identity changed.")
    if (
        config.get("status") != "frozen_for_execution"
        or config.get("rule_version") != "k-query202-human-adjudication-v1-frozen"
        or config.get("execution_status") != "not_initialized"
        or config.get("execution_permitted") is not True
        or config.get("implementation_state") != "implemented_and_tested"
    ):
        raise HumanAdjudicationAuditError(
            "The exact formal execution contract is not frozen and auditable."
        )
    execution_gate = config.get("execution_gate")
    if execution_gate != {
        "unresolved_blockers": [],
        "status_change_alone_may_enable_execution": False,
    }:
        raise HumanAdjudicationAuditError(
            "The formal execution gate still has blockers or changed schema."
        )
    preview = config.get("structural_preview")
    if not isinstance(preview, Mapping) or any(
        preview.get(key) is not False
        for key in (
            "cli_entry_allowed",
            "formal_workspace",
            "workspace_initialized",
            "resume_or_upgrade_to_formal_allowed",
            "compile_audit_or_freeze_allowed",
            "raw_values_on_stdout_allowed",
        )
    ):
        raise HumanAdjudicationAuditError(
            "The structural-preview non-audit boundary changed."
        )

    workspace = config.get("workspace")
    semantic = config.get("semantic_review")
    route = config.get("route_review")
    groups = config.get("mapping_groups")
    evidence = config.get("evidence_registry")
    human = config.get("human_review_policy")
    revisions = config.get("revisions")
    review_writer = config.get("review_writer")
    closure = config.get("snapshot_closure")
    implementation = config.get("implementation")
    source = config.get("source_artifact")
    ndc = config.get("ndc_decision")
    workspace_state = config.get("workspace_state")
    sections = (
        workspace,
        semantic,
        route,
        groups,
        evidence,
        human,
        revisions,
        review_writer,
        closure,
        implementation,
        source,
        ndc,
        workspace_state,
    )
    if not all(isinstance(section, Mapping) for section in sections):
        raise HumanAdjudicationAuditError(
            "The audit contract lacks a required section."
        )
    assert isinstance(workspace, Mapping)
    assert isinstance(semantic, Mapping)
    assert isinstance(route, Mapping)
    assert isinstance(groups, Mapping)
    assert isinstance(evidence, Mapping)
    assert isinstance(human, Mapping)
    assert isinstance(revisions, Mapping)
    assert isinstance(review_writer, Mapping)
    assert isinstance(closure, Mapping)
    assert isinstance(implementation, Mapping)
    assert isinstance(workspace_state, Mapping)

    if (
        workspace.get("private_directory_mode") != "0700"
        or workspace.get("private_file_mode") != "0600"
        or workspace.get("git_ignored_required") is not True
        or workspace.get("strict_workspace_inventory_required") is not True
        or workspace.get("batch_overlap_allowed") is not False
        or workspace.get("batch_omission_allowed") is not False
        or workspace.get("last_write_wins_allowed") is not False
        or workspace.get("immutable_source_fields_may_be_edited") is not False
    ):
        raise HumanAdjudicationAuditError("The private workspace contract changed.")
    if dict(review_writer) != REVIEW_WRITER_POLICY:
        raise HumanAdjudicationAuditError("The human review-writer contract changed.")
    _positive_int(workspace.get("semantic_batch_size"), "semantic batch size")
    _positive_int(workspace.get("semantic_batch_count"), "semantic batch count")
    if workspace.get("route_batch_count") != 1:
        raise HumanAdjudicationAuditError("The route batch contract changed.")
    expected_top = {
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
    if set(workspace.get("allowed_top_level_entries", ())) != expected_top:
        raise HumanAdjudicationAuditError("The workspace inventory contract changed.")
    if (
        semantic.get("dimensions") != list(SEMANTIC_DIMENSIONS)
        or set(semantic.get("status_values", ())) != SEMANTIC_STATUSES
        or semantic.get("review_status_values") != ["unreviewed", "reviewed"]
    ):
        raise HumanAdjudicationAuditError("The semantic controlled vocabulary changed.")
    values = semantic.get("values")
    if not isinstance(values, Mapping):
        raise HumanAdjudicationAuditError("The semantic value contract is absent.")
    for dimension in SEMANTIC_DIMENSIONS:
        item = values.get(dimension)
        if not isinstance(item, Mapping) or any(
            not isinstance(item.get(state + "_code"), str)
            or not item.get(state + "_code")
            for state in SEMANTIC_STATUSES
        ):
            raise HumanAdjudicationAuditError("A semantic value code is invalid.")
    if (
        set(route.get("decision_values", ())) != ROUTE_DECISIONS
        or set(route.get("allowed_decision_bases", ())) != ROUTE_BASES
        or route.get("sql_null_route_state") != "missing"
        or route.get("sql_null_requires_human_review") is not False
        or route.get("source_specific_override_allowed") is not False
    ):
        raise HumanAdjudicationAuditError("The route controlled vocabulary changed.")
    if (
        human.get("reviewer_model") != "single_reviewer_with_full_attestation"
        or human.get("batch_attestation_required") is not True
        or human.get("automated_attestation_allowed") is not False
        or revisions.get("append_only") is not True
        or revisions.get("active_revision_per_item") != 1
        or revisions.get("last_write_wins_allowed") is not False
    ):
        raise HumanAdjudicationAuditError("The reviewer or revision policy changed.")
    local_policy = evidence.get("local_tuple")
    group_policy = groups.get("local_evidence_eligibility")
    if (
        set(evidence.get("allowed_namespaces", ()))
        != {"local_tuple", "source_template", "versioned_document"}
        or not isinstance(local_policy, Mapping)
        or set(local_policy.get("allowed_stage_kind", ())) != GENERAL_LOCAL_KINDS
        or not isinstance(group_policy, Mapping)
        or set(group_policy.get("allowed_stage_kind", ())) != GROUP_LOCAL_KINDS
    ):
        raise HumanAdjudicationAuditError("The local-evidence namespace split changed.")
    _local_index_contract(config)
    closure_true = (
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
    if (
        any(closure.get(key) is not True for key in closure_true)
        or closure.get("symlink_input_allowed") is not False
    ):
        raise HumanAdjudicationAuditError("The two-pass closure contract changed.")
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
        "revision_event_log": {
            "file": "revisions/revision-events.jsonl",
            "header_record_type": "revision_event_ledger_begin",
            "header_exact_fields": [
                "record_type",
                "schema_version",
                "component_id",
                "config_sha256",
                "initial_event_count",
            ],
            "header_schema_version": 1,
            "header_initial_event_count": 0,
            "record_type": "revision_event",
            "record_exact_fields": [
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
            ],
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
        },
        "workspace_event_log": {
            "file": "workspace-events.jsonl",
            "header_record_type": "workspace_event_ledger_begin",
            "header_exact_fields": [
                "record_type",
                "schema_version",
                "component_id",
                "config_sha256",
                "initial_event_count",
            ],
            "header_schema_version": 1,
            "header_initial_event_count": 0,
            "record_type": "workspace_event",
            "record_exact_fields": [
                "record_type",
                "event_index",
                "previous_event_sha256",
                "event_type",
                "event_at_utc",
                "actor_id",
                "subject_kind",
                "subject_id",
                "subject_sha256",
            ],
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
        },
        "active_state_hash": {
            "version": "query202-human-adjudication-active-workspace-state-v1",
            "encoding": (
                "sha256(version-utf8 || "
                "canonical-json-utf8-sort-keys-no-whitespace-v1)"
            ),
            "object_exact_keys": [
                "batches",
                "mapping_groups",
                "current_attestations",
            ],
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
        },
    }
    if dict(workspace_state) != expected_workspace_state:
        raise HumanAdjudicationAuditError("The workspace-event policy changed.")
    guards = config.get("guards")
    if not isinstance(guards, Mapping) or any(
        value is not False for value in guards.values()
    ):
        raise HumanAdjudicationAuditError(
            "A static downstream scientific guard was enabled before audit."
        )

    if implementation.get("bundle_encoding") != BUNDLE_ENCODING:
        raise HumanAdjudicationAuditError("The implementation bundle encoding changed.")
    generator_paths = implementation.get("generator_paths")
    auditor_paths = implementation.get("auditor_paths")
    if generator_paths != list(GENERATOR_PATHS) or auditor_paths != list(AUDITOR_PATHS):
        raise HumanAdjudicationAuditError("The implementation path inventory changed.")
    generator_bundle = _bundle(root, generator_paths, "generator implementation")
    auditor_bundle = _bundle(root, AUDITOR_PATHS, "auditor implementation")
    configured_generator = implementation.get("generator_bundle_sha256")
    configured_auditor = implementation.get("auditor_bundle_sha256")
    if (
        configured_generator == PLACEHOLDER
        or configured_auditor == PLACEHOLDER
        or configured_generator != generator_bundle["sha256"]
        or configured_auditor != auditor_bundle["sha256"]
    ):
        raise HumanAdjudicationAuditError(
            "A frozen implementation bundle is unbound or changed."
        )
    attestation_snapshots = _verify_test_attestation(
        root,
        config,
        generator_bundle["sha256"],
        auditor_bundle["sha256"],
    )
    return {
        "root": root,
        "config": config,
        "path": path,
        "snapshot": snapshot,
        "config_sha256": snapshot["sha256"],
        "generator_bundle": generator_bundle,
        "auditor_bundle": auditor_bundle,
        "test_attestation_snapshots": attestation_snapshots,
    }


def _artifact_file(directory: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).name != value:
        raise HumanAdjudicationAuditError(f"{label} filename is unsafe.")
    return directory / value


def _source_inventory(root: Path, contract: Mapping[str, Any]) -> dict[str, Any]:
    source = contract["config"]["source_artifact"]
    directory = _project_path(root, source.get("directory"), "source artifact")
    directory_snapshot = _snapshot_directory(
        directory, "The source artifact directory", root=root
    )
    if (
        directory_snapshot["mode"] != 0o700
        or source.get("component_id") != SOURCE_COMPONENT_ID
    ):
        raise HumanAdjudicationAuditError(
            "The source artifact privacy or identity changed."
        )
    specs = {
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
        "summary": (
            _artifact_file(
                directory, source.get("aggregate_summary_file"), "source summary"
            ),
            source.get("aggregate_summary_sha256"),
            True,
        ),
        "audit": (
            _artifact_file(directory, source.get("audit_file"), "source audit"),
            source.get("audit_sha256"),
            True,
        ),
        "semantic": (
            _artifact_file(
                directory, source["semantic_template"].get("file"), "semantic source"
            ),
            source["semantic_template"].get("stored_sha256"),
            True,
        ),
        "route": (
            _artifact_file(
                directory, source["route_template"].get("file"), "route source"
            ),
            source["route_template"].get("stored_sha256"),
            True,
        ),
        "local": (
            _artifact_file(
                directory, source["local_evidence"].get("file"), "local evidence"
            ),
            source["local_evidence"].get("stored_sha256"),
            False,
        ),
    }
    snapshots: dict[str, dict[str, Any]] = {}
    for key, (path, expected_hash, retain) in specs.items():
        snapshot = _snapshot_file(
            path, f"The source {key}", retain_payload=retain, root=root
        )
        _require_hash(snapshot, expected_hash, f"The source {key}")
        if path.parent == directory and (
            snapshot["mode"] != 0o600 or snapshot["nlink"] != 1
        ):
            raise HumanAdjudicationAuditError(
                "A private source file has an unsafe mode or link count."
            )
        if key in {"semantic", "route", "local"}:
            section_name = {
                "semantic": "semantic_template",
                "route": "route_template",
                "local": "local_evidence",
            }[key]
            if snapshot["bytes"] != source[section_name].get("stored_bytes"):
                raise HumanAdjudicationAuditError("A source stream size changed.")
        snapshots[key] = {**snapshot, "path": path}

    manifest = _read_json(snapshots["manifest"], "The source manifest")
    summary = _read_json(snapshots["summary"], "The source summary")
    audit = _read_json(snapshots["audit"], "The source audit")
    outputs = manifest.get("outputs")
    conservation = manifest.get("conservation")
    checks = audit.get("checks")
    if (
        manifest.get("component_id") != SOURCE_COMPONENT_ID
        or manifest.get("status") != "complete"
        or not isinstance(summary, Mapping)
        or not isinstance(outputs, Mapping)
        or not isinstance(conservation, Mapping)
        or audit.get("status") != source.get("audit_status")
        or not isinstance(checks, Mapping)
        or checks.get("failed") != source.get("audit_failed_checks")
    ):
        raise HumanAdjudicationAuditError("The source public lineage is incomplete.")
    output_map = {
        "semantic_review_template": "semantic_template",
        "route_review_template": "route_template",
        "local_evidence": "local_evidence",
    }
    for output_name, section_name in output_map.items():
        declared = outputs.get(output_name)
        configured = source[section_name]
        if not isinstance(declared, Mapping) or any(
            declared.get(left) != configured.get(right)
            for left, right in (
                ("file", "file"),
                ("sha256", "stored_sha256"),
                ("bytes", "stored_bytes"),
                ("raw_sha256", "raw_sha256"),
                ("raw_bytes", "raw_bytes"),
                ("records", "records"),
            )
        ):
            raise HumanAdjudicationAuditError(
                "A source manifest stream binding changed."
            )
    if (
        conservation.get("semantic_review_keys")
        != source["semantic_template"].get("semantic_keys")
        or conservation.get("semantic_seed_key_set_sha256")
        != source["semantic_template"].get("semantic_key_set_sha256")
        or conservation.get("route_canonical_exact_nonnull_values")
        != source["route_template"].get("canonical_exact_nonnull_values")
        or conservation.get("route_source_specific_nonnull_memberships")
        != source["route_template"].get("source_specific_nonnull_memberships")
        or conservation.get("route_source_specific_sql_null_memberships")
        != source["route_template"].get("source_specific_sql_null_memberships")
        or conservation.get("route_source_specific_typed_memberships")
        != source["route_template"].get("source_specific_typed_memberships")
    ):
        raise HumanAdjudicationAuditError(
            "The source conservation declaration changed."
        )

    ndc_contract = contract["config"]["ndc_decision"]
    ndc_path = _project_path(root, ndc_contract.get("config_path"), "NDC decision")
    ndc_snapshot = _snapshot_file(
        ndc_path, "The NDC decision", retain_payload=True, root=root
    )
    _require_hash(ndc_snapshot, ndc_contract.get("config_sha256"), "The NDC decision")
    try:
        ndc = tomllib.loads(ndc_snapshot["payload"].decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise HumanAdjudicationAuditError("The NDC decision is invalid.") from None
    decision = ndc.get("decision")
    if (
        ndc.get("component_id") != NDC_COMPONENT_ID
        or ndc.get("status") != ndc_contract.get("required_status")
        or not isinstance(decision, Mapping)
        or decision.get("mode") != ndc_contract.get("required_mode")
        or decision.get("effective") is not ndc_contract.get("required_effective")
        or ndc_contract.get("ndc_handoff_rows_may_be_read") is not False
    ):
        raise HumanAdjudicationAuditError("The frozen NDC non-use decision changed.")
    snapshots["ndc"] = {**ndc_snapshot, "path": ndc_path}
    return {
        "root": root,
        "directory": directory,
        "directory_snapshot": directory_snapshot,
        "snapshots": snapshots,
    }


def _semantic_set_hash(items: Sequence[Mapping[str, Any]]) -> str:
    pairs = sorted(
        (
            item["source_field"].encode("utf-8"),
            item["exact_raw_value"].encode("utf-8"),
        )
        for item in items
    )
    if len(pairs) != len(set(pairs)):
        raise HumanAdjudicationAuditError("The semantic source repeats an exact key.")
    digest = hashlib.sha256(SEMANTIC_SET_VERSION)
    digest.update(struct.pack(">Q", len(pairs)))
    for field, value in pairs:
        digest.update(struct.pack(">I", len(field)))
        digest.update(field)
        digest.update(struct.pack(">Q", len(value)))
        digest.update(value)
    return digest.hexdigest()


def _route_set_hash(items: Sequence[Mapping[str, Any]]) -> str:
    values = sorted(item["exact_raw_value"].encode("utf-8") for item in items)
    if len(values) != len(set(values)):
        raise HumanAdjudicationAuditError("The route source repeats a canonical value.")
    digest = hashlib.sha256(ROUTE_SET_VERSION)
    digest.update(struct.pack(">Q", len(values)))
    for value in values:
        digest.update(struct.pack(">Q", len(value)))
        digest.update(value)
    return digest.hexdigest()


def _parse_semantic_template(
    records: Sequence[Mapping[str, Any]], section: Mapping[str, Any]
) -> list[dict[str, Any]]:
    count = _positive_int(section.get("semantic_keys"), "semantic key count")
    if len(records) != count + 4 or records[0].get("record_type") != "header":
        raise HumanAdjudicationAuditError("The semantic source framing changed.")
    begin = _exact_keys(
        records[1],
        {"record_type", "key_count", "key_set_sha256", "semantic_dimensions"},
        "semantic source begin",
    )
    if begin != {
        "record_type": "semantic_review_begin",
        "key_count": count,
        "key_set_sha256": section.get("semantic_key_set_sha256"),
        "semantic_dimensions": list(SEMANTIC_DIMENSIONS),
    }:
        raise HumanAdjudicationAuditError("The semantic source declaration changed.")
    keys = {
        "record_type",
        "source_field",
        "exact_raw_value",
        "exact_row_count",
        "review_status",
        "semantic_decisions",
        "mapping_group_id",
        "decision_basis",
        "reviewer_id",
        "reviewed_at_utc",
    }
    items: list[dict[str, Any]] = []
    previous: tuple[bytes, bytes] | None = None
    for index, raw_record in enumerate(records[2:-2], start=1):
        record = _exact_keys(raw_record, keys, "semantic source item")
        field = record["source_field"]
        value = record["exact_raw_value"]
        if not isinstance(field, str) or not field or not isinstance(value, str):
            raise HumanAdjudicationAuditError("A semantic source key is malformed.")
        encoded = value.encode("utf-8")
        order = field.encode("utf-8"), encoded
        if (
            b"\x00" in encoded
            or len(encoded) > MAX_VALUE_UTF8_BYTES
            or (previous is not None and order <= previous)
        ):
            raise HumanAdjudicationAuditError("The semantic source ordering changed.")
        previous = order
        row_count = _positive_int(record["exact_row_count"], "semantic row count")
        if (
            record["record_type"] != "semantic_review_key"
            or record["review_status"] != "unreviewed"
            or record["semantic_decisions"]
            != {dimension: "uncertain" for dimension in SEMANTIC_DIMENSIONS}
            or any(
                record[name] is not None
                for name in (
                    "mapping_group_id",
                    "decision_basis",
                    "reviewer_id",
                    "reviewed_at_utc",
                )
            )
        ):
            raise HumanAdjudicationAuditError(
                "The semantic source contains a decision."
            )
        items.append(
            {
                "record_type": "semantic_source_item",
                "review_id": f"S{index:06d}",
                "source_field": field,
                "exact_raw_value": value,
                "exact_row_count": row_count,
            }
        )
    end = records[-2]
    footer = records[-1]
    if (
        end
        != {
            "record_type": "semantic_review_end",
            "records": count,
            "key_set_sha256": section.get("semantic_key_set_sha256"),
        }
        or footer
        != {
            "record_type": "footer",
            "records_before_footer": len(records) - 1,
            "section_counts": {"semantic_review_keys": count},
        }
        or _semantic_set_hash(items) != section.get("semantic_key_set_sha256")
    ):
        raise HumanAdjudicationAuditError(
            "The semantic source conservation check failed."
        )
    return items


def _parse_route_template(
    records: Sequence[Mapping[str, Any]], section: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    canonical_count = _positive_int(
        section.get("canonical_exact_nonnull_values"), "route canonical count"
    )
    membership_count = _positive_int(
        section.get("source_specific_typed_memberships"), "route membership count"
    )
    if (
        len(records) != canonical_count + membership_count + 4
        or records[0].get("record_type") != "header"
    ):
        raise HumanAdjudicationAuditError("The route source framing changed.")
    begin = _exact_keys(
        records[1],
        {
            "record_type",
            "canonical_exact_nonnull_values",
            "source_specific_nonnull_memberships",
            "source_specific_sql_null_memberships",
            "source_specific_typed_memberships",
            "typed_set_sha256",
        },
        "route source begin",
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
        raise HumanAdjudicationAuditError("The route source declaration changed.")
    canonical_keys = {
        "record_type",
        "canonical_review_id",
        "exact_raw_value",
        "raw_utf8_bytes",
        "decision",
        "review_status",
        "decision_basis",
        "reviewer_id",
        "reviewed_at_utc",
    }
    canonical: list[dict[str, Any]] = []
    by_id: dict[str, str] = {}
    previous: bytes | None = None
    for index, raw_record in enumerate(records[2 : 2 + canonical_count], start=1):
        record = _exact_keys(raw_record, canonical_keys, "route canonical item")
        review_id = f"R{index:06d}"
        value = record["exact_raw_value"]
        if not isinstance(value, str):
            raise HumanAdjudicationAuditError("A route canonical value is malformed.")
        encoded = value.encode("utf-8")
        if (
            record["record_type"] != "canonical_route_review"
            or record["canonical_review_id"] != review_id
            or record["raw_utf8_bytes"] != len(encoded)
            or b"\x00" in encoded
            or len(encoded) > MAX_VALUE_UTF8_BYTES
            or (previous is not None and encoded <= previous)
            or record["decision"] != "unknown"
            or record["review_status"] != "unreviewed"
            or any(
                record[name] is not None
                for name in ("decision_basis", "reviewer_id", "reviewed_at_utc")
            )
        ):
            raise HumanAdjudicationAuditError("A route canonical source item changed.")
        previous = encoded
        canonical.append(
            {
                "record_type": "route_source_item",
                "review_id": review_id,
                "exact_raw_value": value,
                "raw_utf8_bytes": len(encoded),
            }
        )
        by_id[review_id] = value

    membership_keys = {
        "record_type",
        "source_key",
        "source_field",
        "field_role",
        "raw_value_state",
        "exact_raw_value",
        "exact_row_count",
        "decision",
        "route_state",
        "sets_has_unknown",
        "decision_provenance",
        "canonical_review_id",
        "review_status",
        "decision_basis",
        "reviewer_id",
        "reviewed_at_utc",
    }
    memberships: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None]] = set()
    nonnull = nulls = 0
    start = 2 + canonical_count
    for raw_record in records[start : start + membership_count]:
        record = _exact_keys(raw_record, membership_keys, "route source membership")
        row_count = _positive_int(record["exact_row_count"], "route row count")
        common = {
            "record_type": "route_source_membership",
            "source_key": record["source_key"],
            "source_field": record["source_field"],
            "field_role": record["field_role"],
            "raw_value_state": record["raw_value_state"],
            "exact_raw_value": record["exact_raw_value"],
            "exact_row_count": row_count,
            "canonical_review_id": record["canonical_review_id"],
        }
        if not all(
            isinstance(common[key], str) and common[key]
            for key in ("source_key", "source_field", "field_role")
        ):
            raise HumanAdjudicationAuditError("A route membership identity changed.")
        if record["raw_value_state"] == "nonnull":
            review_id = record["canonical_review_id"]
            if (
                review_id not in by_id
                or record["exact_raw_value"] != by_id[review_id]
                or record["decision"] != "unknown"
                or record["route_state"] != "unknown"
                or record["sets_has_unknown"] is not True
                or record["decision_provenance"] != "default_unknown_unreviewed"
                or record["review_status"] != "unreviewed"
                or any(
                    record[name] is not None
                    for name in ("decision_basis", "reviewer_id", "reviewed_at_utc")
                )
            ):
                raise HumanAdjudicationAuditError("A nonnull route membership changed.")
            common.update(route_state="unknown", sets_has_unknown=True)
            nonnull += 1
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
                raise HumanAdjudicationAuditError(
                    "A SQL-NULL route membership changed."
                )
            common.update(route_state="missing", sets_has_unknown=False)
            nulls += 1
        else:
            raise HumanAdjudicationAuditError("A route membership state is invalid.")
        identity = (
            common["source_field"],
            common["raw_value_state"],
            common["exact_raw_value"],
        )
        if identity in seen:
            raise HumanAdjudicationAuditError("The route source repeats a membership.")
        seen.add(identity)
        memberships.append(common)
    if (
        nonnull != section.get("source_specific_nonnull_memberships")
        or nulls != section.get("source_specific_sql_null_memberships")
        or records[-2]
        != {
            "record_type": "route_review_end",
            "canonical_records": canonical_count,
            "source_membership_records": membership_count,
            "canonical_exact_set_sha256": section.get("canonical_exact_set_sha256"),
        }
        or records[-1]
        != {
            "record_type": "footer",
            "records_before_footer": len(records) - 1,
            "section_counts": {
                "canonical_route_reviews": canonical_count,
                "route_source_memberships": membership_count,
            },
        }
        or _route_set_hash(canonical) != section.get("canonical_exact_set_sha256")
    ):
        raise HumanAdjudicationAuditError("The route source conservation check failed.")
    return canonical, memberships


def _semantic_default(review_id: str, semantic: Mapping[str, Any]) -> dict[str, Any]:
    values = semantic["values"]
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


def _route_default(review_id: str) -> dict[str, Any]:
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


def _source_batch_expected(
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


def _validate_source_batch(
    records: Sequence[Mapping[str, Any]],
    kind: str,
    batch_index: int,
    batch_count: int,
    items: Sequence[Mapping[str, Any]],
    memberships: Sequence[Mapping[str, Any]] = (),
) -> None:
    expected = _source_batch_expected(
        kind, batch_index, batch_count, items, memberships
    )
    if list(records) != expected:
        raise HumanAdjudicationAuditError(
            "An immutable source batch changed or lost source conservation."
        )


def _evidence_refs(
    value: object,
    registry: Mapping[str, Mapping[str, Any]],
    *,
    required: bool,
    review_id: str | None = None,
) -> list[str]:
    if not isinstance(value, list) or (required and not value):
        raise HumanAdjudicationAuditError("A decision has invalid evidence references.")
    output: list[str] = []
    for reference in value:
        if (
            not isinstance(reference, str)
            or EVIDENCE_ID_RE.fullmatch(reference) is None
            or reference not in registry
        ):
            raise HumanAdjudicationAuditError("A decision cites unregistered evidence.")
        entry = registry[reference]
        if (
            review_id is not None
            and entry["namespace"] == "source_template"
            and entry["locator"].get("private_review_id") != review_id
        ):
            raise HumanAdjudicationAuditError(
                "A source-template evidence reference is bound to another item."
            )
        output.append(reference)
    if len(output) != len(set(output)):
        raise HumanAdjudicationAuditError("A decision repeats an evidence reference.")
    return output


def _revision_common(
    record: Mapping[str, Any], expected_type: str, pattern: re.Pattern[str]
) -> tuple[str, int, str | None]:
    if record.get("record_type") != expected_type:
        raise HumanAdjudicationAuditError("A decision revision type changed.")
    review_id = record.get("review_id")
    revision = record.get("revision")
    supersedes = record.get("supersedes_sha256")
    if not isinstance(review_id, str) or pattern.fullmatch(review_id) is None:
        raise HumanAdjudicationAuditError("A decision revision ID is invalid.")
    _positive_int(revision, "revision number")
    if supersedes is not None and (
        not isinstance(supersedes, str) or SHA256_RE.fullmatch(supersedes) is None
    ):
        raise HumanAdjudicationAuditError("A revision predecessor hash is invalid.")
    _nonempty_text(record.get("revision_reason"), "revision reason")
    return review_id, revision, supersedes


def _validate_dimensions(
    dimensions: object,
    semantic: Mapping[str, Any],
    registry: Mapping[str, Mapping[str, Any]],
    review_status: str,
    review_id: str | None,
) -> None:
    if not isinstance(dimensions, Mapping) or set(dimensions) != set(
        SEMANTIC_DIMENSIONS
    ):
        raise HumanAdjudicationAuditError("A semantic dimension set changed.")
    values = semantic["values"]
    for dimension in SEMANTIC_DIMENSIONS:
        item = _exact_keys(
            dimensions[dimension],
            {"status", "value", "evidence_refs", "uncertainty_basis"},
            "semantic dimension",
        )
        decision = item["status"]
        if decision not in SEMANTIC_STATUSES:
            raise HumanAdjudicationAuditError("A semantic decision state is invalid.")
        controlled = _exact_keys(
            item["value"], {"code", "candidates"}, "semantic value"
        )
        candidates = controlled["candidates"]
        if controlled["code"] != values[dimension][
            decision + "_code"
        ] or not isinstance(candidates, list):
            raise HumanAdjudicationAuditError("A semantic controlled value is invalid.")
        for candidate in candidates:
            _nonempty_text(candidate, "semantic candidate")
        if review_status == "unreviewed":
            if item != {
                "status": "uncertain",
                "value": {
                    "code": values[dimension]["uncertain_code"],
                    "candidates": [],
                },
                "evidence_refs": [],
                "uncertainty_basis": None,
            }:
                raise HumanAdjudicationAuditError(
                    "An unreviewed semantic decision is not its exact default."
                )
        elif decision == "uncertain":
            if item["uncertainty_basis"] not in UNCERTAINTY_BASES:
                raise HumanAdjudicationAuditError(
                    "A reviewed uncertain decision lacks its controlled basis."
                )
            _evidence_refs(
                item["evidence_refs"],
                registry,
                required=False,
                review_id=review_id,
            )
        else:
            if item["uncertainty_basis"] is not None:
                raise HumanAdjudicationAuditError(
                    "A non-uncertain decision has an uncertainty basis."
                )
            _evidence_refs(
                item["evidence_refs"],
                registry,
                required=True,
                review_id=review_id,
            )


def _validate_semantic_revision(
    raw_record: Mapping[str, Any],
    semantic: Mapping[str, Any],
    registry: Mapping[str, Mapping[str, Any]],
    *,
    bind_source: bool = True,
) -> tuple[str, int, str | None]:
    record = _exact_keys(
        raw_record,
        {
            "record_type",
            "review_id",
            "revision",
            "supersedes_sha256",
            "revision_reason",
            "review_status",
            "dimensions",
            "mapping_group_id",
            "rationale",
            "reviewer_id",
            "reviewed_at_utc",
        },
        "semantic revision",
    )
    review_id, revision, supersedes = _revision_common(
        record, "semantic_decision_revision", SEMANTIC_ID_RE
    )
    review_status = record["review_status"]
    if review_status not in {"unreviewed", "reviewed"}:
        raise HumanAdjudicationAuditError("A semantic review state is invalid.")
    _validate_dimensions(
        record["dimensions"],
        semantic,
        registry,
        review_status,
        review_id if bind_source else None,
    )
    group_id = record["mapping_group_id"]
    if group_id is not None and (
        not isinstance(group_id, str) or GROUP_ID_RE.fullmatch(group_id) is None
    ):
        raise HumanAdjudicationAuditError("A semantic group ID is invalid.")
    if review_status == "unreviewed":
        if group_id is not None or any(
            record[key] is not None
            for key in ("rationale", "reviewer_id", "reviewed_at_utc")
        ):
            raise HumanAdjudicationAuditError(
                "An unreviewed semantic revision contains human provenance."
            )
    else:
        _nonempty_text(record["rationale"], "semantic rationale")
        _nonempty_text(record["reviewer_id"], "semantic reviewer", 256)
        if not _strict_utc(record["reviewed_at_utc"]):
            raise HumanAdjudicationAuditError("A semantic review time is invalid.")
    return review_id, revision, supersedes


def _validate_route_revision(
    raw_record: Mapping[str, Any], registry: Mapping[str, Mapping[str, Any]]
) -> tuple[str, int, str | None]:
    record = _exact_keys(
        raw_record,
        {
            "record_type",
            "review_id",
            "revision",
            "supersedes_sha256",
            "revision_reason",
            "review_status",
            "decision",
            "decision_basis",
            "evidence_refs",
            "rationale",
            "reviewer_id",
            "reviewed_at_utc",
        },
        "route revision",
    )
    review_id, revision, supersedes = _revision_common(
        record, "route_decision_revision", ROUTE_ID_RE
    )
    review_status = record["review_status"]
    decision = record["decision"]
    if (
        review_status not in {"unreviewed", "reviewed"}
        or decision not in ROUTE_DECISIONS
    ):
        raise HumanAdjudicationAuditError("A route decision state is invalid.")
    _evidence_refs(
        record["evidence_refs"],
        registry,
        required=review_status == "reviewed",
        review_id=review_id,
    )
    if review_status == "unreviewed":
        if (
            decision != "unknown"
            or record["decision_basis"] is not None
            or record["evidence_refs"] != []
            or any(
                record[key] is not None
                for key in ("rationale", "reviewer_id", "reviewed_at_utc")
            )
        ):
            raise HumanAdjudicationAuditError(
                "An unreviewed route revision is not its exact default."
            )
    else:
        if record["decision_basis"] not in ROUTE_BASES or (
            decision == "unknown"
            and record["decision_basis"] != "ambiguous_or_insufficient_route_semantics"
        ):
            raise HumanAdjudicationAuditError("A route decision basis is invalid.")
        _nonempty_text(record["rationale"], "route rationale")
        _nonempty_text(record["reviewer_id"], "route reviewer", 256)
        if not _strict_utc(record["reviewed_at_utc"]):
            raise HumanAdjudicationAuditError("A route review time is invalid.")
    return review_id, revision, supersedes


def _active_batch_hash(
    kind: str, batch_index: int, active: Mapping[str, Mapping[str, Any]]
) -> str:
    digest = hashlib.sha256(ACTIVE_BATCH_VERSION)
    encoded_kind = kind.encode("ascii")
    digest.update(struct.pack(">I", len(encoded_kind)))
    digest.update(encoded_kind)
    digest.update(struct.pack(">I", batch_index))
    digest.update(struct.pack(">Q", len(active)))
    for review_id in sorted(active):
        encoded_id = review_id.encode("ascii")
        digest.update(struct.pack(">I", len(encoded_id)))
        digest.update(encoded_id)
        digest.update(bytes.fromhex(_record_sha(active[review_id])))
    return digest.hexdigest()


def _validate_decision_ledger(
    records: Sequence[Mapping[str, Any]],
    kind: str,
    batch_index: int,
    batch_count: int,
    source_relative: str,
    source_snapshot: Mapping[str, Any],
    expected_ids: Sequence[str],
    contract: Mapping[str, Any],
    registry: Mapping[str, Mapping[str, Any]],
) -> tuple[
    dict[str, Mapping[str, Any]],
    str,
    set[str],
    dict[tuple[str, str, int], Mapping[str, Any]],
]:
    if not records:
        raise HumanAdjudicationAuditError("A decision ledger is empty.")
    header = _exact_keys(
        records[0],
        {
            "record_type",
            "schema_version",
            "component_id",
            "config_sha256",
            "batch_index",
            "batch_count",
            "item_count",
            "immutable_source_file",
            "immutable_source_sha256",
            "immutable_source_bytes",
            "append_only_revisions",
        },
        "decision ledger header",
    )
    if header != {
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
    }:
        raise HumanAdjudicationAuditError(
            "A decision ledger lost its immutable-source binding."
        )
    expected = set(expected_ids)
    histories: dict[str, dict[int, tuple[str, Mapping[str, Any]]]] = {
        review_id: {} for review_id in expected_ids
    }
    active: dict[str, Mapping[str, Any]] = {}
    active_hash: dict[str, str] = {}
    reviewers: set[str] = set()
    revision_events: dict[tuple[str, str, int], Mapping[str, Any]] = {}
    for raw_record in records[1:]:
        if kind == "semantic":
            review_id, revision, supersedes = _validate_semantic_revision(
                raw_record,
                contract["config"]["semantic_review"],
                registry,
            )
        else:
            review_id, revision, supersedes = _validate_route_revision(
                raw_record, registry
            )
        if raw_record["review_status"] == "reviewed":
            reviewers.add(raw_record["reviewer_id"])
        if review_id not in expected:
            raise HumanAdjudicationAuditError(
                "A revision is missing, duplicated across batches, or misplaced."
            )
        digest = _record_sha(raw_record)
        existing = histories[review_id].get(revision)
        if existing is not None:
            if existing[0] != digest:
                raise HumanAdjudicationAuditError(
                    "Conflicting revisions share one revision number."
                )
            continue
        if revision != len(histories[review_id]) + 1:
            raise HumanAdjudicationAuditError("A revision chain has a gap or branch.")
        if revision == 1:
            default = (
                _semantic_default(review_id, contract["config"]["semantic_review"])
                if kind == "semantic"
                else _route_default(review_id)
            )
            if supersedes is not None or raw_record != default:
                raise HumanAdjudicationAuditError(
                    "An initial revision is not the exact software default."
                )
        else:
            if raw_record["review_status"] != "reviewed":
                raise HumanAdjudicationAuditError(
                    "A noninitial decision revision lacks human review."
                )
            if supersedes != active_hash[review_id]:
                raise HumanAdjudicationAuditError(
                    "A revision does not bind its unique predecessor."
                )
            revision_kind = f"{kind}_decision"
            revision_events[(revision_kind, review_id, revision)] = {
                "revision_kind": revision_kind,
                "subject_id": review_id,
                "batch_index": batch_index,
                "revision": revision,
                "revision_sha256": digest,
                "supersedes_sha256": supersedes,
                "reviewer_id": raw_record["reviewer_id"],
                "recorded_at_utc": raw_record["reviewed_at_utc"],
            }
        histories[review_id][revision] = digest, raw_record
        active[review_id] = raw_record
        active_hash[review_id] = digest
    if set(active) != expected or any(not history for history in histories.values()):
        raise HumanAdjudicationAuditError("A decision ledger omits a source item.")
    if any(record["review_status"] != "reviewed" for record in active.values()):
        raise HumanAdjudicationAuditError(
            "The workspace is not human-review complete and cannot receive this audit."
        )
    return (
        active,
        _active_batch_hash(kind, batch_index, active),
        reviewers,
        revision_events,
    )


def _validate_evidence_registry(
    records: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
    all_review_ids: set[str],
    workspace_snapshots: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    if not records:
        raise HumanAdjudicationAuditError("The evidence registry is empty.")
    expected_header = {
        "record_type": "evidence_registry_begin",
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "config_sha256": contract["config_sha256"],
        "initial_evidence_count": 0,
    }
    if records[0] != expected_header:
        raise HumanAdjudicationAuditError("The evidence registry header changed.")
    source = contract["config"]["source_artifact"]
    registry: dict[str, dict[str, Any]] = {}
    document_paths: set[str] = set()
    previous: str | None = None
    for raw_record in records[1:]:
        record = _exact_keys(
            raw_record,
            {"record_type", "evidence_id", "namespace", "locator"},
            "evidence registry entry",
        )
        evidence_id = record["evidence_id"]
        namespace = record["namespace"]
        locator = record["locator"]
        if (
            record["record_type"] != "evidence_registry_entry"
            or not isinstance(evidence_id, str)
            or EVIDENCE_ID_RE.fullmatch(evidence_id) is None
            or evidence_id in registry
            or (previous is not None and evidence_id <= previous)
            or namespace not in {"local_tuple", "source_template", "versioned_document"}
            or not isinstance(locator, Mapping)
        ):
            raise HumanAdjudicationAuditError(
                "An evidence registry identity is invalid."
            )
        previous = evidence_id
        if namespace == "local_tuple":
            locator = _exact_keys(
                locator,
                {
                    "local_evidence_raw_sha256",
                    "stage",
                    "tuple_kind",
                    "ordinal_within_kind",
                },
                "local evidence locator",
            )
            stage = locator["stage"]
            kind = locator["tuple_kind"]
            stage_kind = f"{stage}:{kind}"
            if (
                locator["local_evidence_raw_sha256"]
                != source["local_evidence"]["raw_sha256"]
                or not isinstance(stage, str)
                or not isinstance(kind, str)
                or stage_kind not in GENERAL_LOCAL_KINDS
            ):
                raise HumanAdjudicationAuditError(
                    "A local evidence locator is invalid."
                )
            _positive_int(locator["ordinal_within_kind"], "local evidence ordinal")
        elif namespace == "source_template":
            locator = _exact_keys(
                locator,
                {"source_template_raw_sha256", "private_review_id"},
                "source template locator",
            )
            review_id = locator["private_review_id"]
            expected_hash = (
                source["semantic_template"]["raw_sha256"]
                if isinstance(review_id, str) and SEMANTIC_ID_RE.fullmatch(review_id)
                else (
                    source["route_template"]["raw_sha256"]
                    if isinstance(review_id, str) and ROUTE_ID_RE.fullmatch(review_id)
                    else None
                )
            )
            if (
                review_id not in all_review_ids
                or locator["source_template_raw_sha256"] != expected_hash
            ):
                raise HumanAdjudicationAuditError(
                    "A source-template evidence locator is forged or stale."
                )
        else:
            locator = _exact_keys(
                locator,
                {
                    "evidence_id",
                    "document_sha256",
                    "document_version",
                    "accessed_at_utc",
                    "private_local_path",
                },
                "versioned document locator",
            )
            if (
                locator["evidence_id"] != evidence_id
                or not isinstance(locator["document_sha256"], str)
                or SHA256_RE.fullmatch(locator["document_sha256"]) is None
                or not _strict_utc(locator["accessed_at_utc"])
            ):
                raise HumanAdjudicationAuditError(
                    "A versioned-document evidence locator is invalid."
                )
            _nonempty_text(locator["document_version"], "document version", 1024)
            relative = _safe_relative(
                locator["private_local_path"], "private evidence document"
            ).as_posix()
            if (
                not relative.startswith("evidence-registry/documents/")
                or len(Path(relative).parts) != 3
                or relative in document_paths
            ):
                raise HumanAdjudicationAuditError(
                    "A private evidence document path is invalid."
                )
            document = workspace_snapshots.get(relative)
            if (
                document is None
                or document["mode"] != 0o600
                or document["nlink"] != 1
                or document["sha256"] != locator["document_sha256"]
            ):
                raise HumanAdjudicationAuditError(
                    "A private evidence document is absent or changed."
                )
            document_paths.add(relative)
        registry[evidence_id] = {
            "namespace": namespace,
            "locator": dict(locator),
        }
    return registry, document_paths


def _scan_local_evidence_index(
    snapshot: Mapping[str, Any],
    config: Mapping[str, Any],
    registry: dict[str, dict[str, Any]],
    semantic_count: int,
) -> None:
    """Independently hash, decode, and resolve the entire private index."""
    index = _local_index_contract(config)
    payload = snapshot.get("payload")
    if (
        not isinstance(payload, bytes)
        or snapshot.get("mode") != 0o600
        or snapshot.get("nlink") != 1
    ):
        raise HumanAdjudicationAuditError(
            "The private local-evidence ordinal index is unavailable or unsafe."
        )
    digest = hashlib.sha256()
    total = 0
    for position in range(0, len(payload), READ_CHUNK_BYTES):
        chunk = payload[position : position + READ_CHUNK_BYTES]
        digest.update(chunk)
        total += len(chunk)
    if (
        total != index["index_bytes"]
        or digest.hexdigest() != index["index_sha256"]
        or len(payload) % LOCAL_EVIDENCE_INDEX_RECORD_BYTES
    ):
        raise HumanAdjudicationAuditError(
            "The private local-evidence ordinal index hash or size changed."
        )

    targets: dict[int, list[str]] = {}
    for evidence_id, entry in registry.items():
        if entry["namespace"] != "local_tuple":
            continue
        locator = entry["locator"]
        stage_kind = f"{locator['stage']}:{locator['tuple_kind']}"
        ordinal = locator["ordinal_within_kind"]
        maximum = index["kind_counts"].get(stage_kind)
        if type(ordinal) is not int or ordinal <= 0 or maximum is None or ordinal > maximum:
            raise HumanAdjudicationAuditError(
                "A local-evidence ordinal is outside its frozen kind block."
            )
        block = index["bridge_blocks"].get(stage_kind)
        if block is not None:
            targets.setdefault(block[0] + ordinal - 1, []).append(evidence_id)

    found: set[int] = set()
    for record_index in range(index["index_records"]):
        start = record_index * LOCAL_EVIDENCE_INDEX_RECORD_BYTES
        member_count, *sequences = struct.unpack(
            ">B4I", payload[start : start + LOCAL_EVIDENCE_INDEX_RECORD_BYTES]
        )
        active = sequences[:member_count] if member_count <= 4 else []
        padding = sequences[member_count:] if member_count <= 4 else sequences
        if (
            member_count > 4
            or any(value == 0 or value > semantic_count for value in active)
            or any(left >= right for left, right in zip(active, active[1:]))
            or any(value != 0 for value in padding)
        ):
            raise HumanAdjudicationAuditError(
                "A local-evidence ordinal-index record is invalid."
            )
        evidence_ids = targets.get(record_index)
        if evidence_ids is None:
            continue
        found.add(record_index)
        members = frozenset(f"S{sequence:06d}" for sequence in active)
        for evidence_id in evidence_ids:
            registry[evidence_id]["resolved"] = True
            registry[evidence_id]["semantic_members"] = members
    if found != set(targets):
        raise HumanAdjudicationAuditError(
            "A local-evidence ordinal-index reference was not resolved."
        )


def _audit_local_evidence_source_to_index(
    source_inventory: Mapping[str, Any],
    config: Mapping[str, Any],
    semantic_items: Sequence[Mapping[str, Any]],
    index_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently derive and compare every private bridge-index record.

    The local-evidence gzip is opened through the project-root descriptor chain
    and parsed as a stream. Each bridge tuple is converted directly to its
    expected 17-byte record and compared with the already anchored workspace
    snapshot. No second index is accumulated in memory or written to disk.
    """

    root = source_inventory["root"]
    initial = source_inventory["snapshots"]["local"]
    source_section = config["source_artifact"]["local_evidence"]
    index = _local_index_contract(config)
    payload = index_snapshot.get("payload")
    if (
        not isinstance(payload, bytes)
        or index_snapshot.get("mode") != 0o600
        or index_snapshot.get("nlink") != 1
        or len(payload) != index["index_bytes"]
    ):
        raise HumanAdjudicationAuditError(
            "The private local-evidence ordinal index is unavailable or unsafe."
        )

    semantic_lookup: dict[tuple[str, str], int] = {}
    for sequence, item in enumerate(semantic_items, start=1):
        key = (item.get("source_field"), item.get("exact_raw_value"))
        if (
            not isinstance(key[0], str)
            or not isinstance(key[1], str)
            or key in semantic_lookup
        ):
            raise HumanAdjudicationAuditError(
                "The semantic source cannot define the ordinal index."
            )
        semantic_lookup[key] = sequence

    begin_keys = {
        "record_type",
        "stage",
        "tuple_kind",
        "unique_tuples",
        "total_multiplicity",
        "global_tuple_set_sha256",
        "global_tuple_frequency_sha256",
    }
    tuple_keys = {"record_type", "stage", "tuple_kind", "tuple", "multiplicity"}
    end_keys = {
        "record_type",
        "stage",
        "tuple_kind",
        "records",
        "total_multiplicity",
        "global_tuple_set_sha256",
        "global_tuple_frequency_sha256",
    }
    production_header_keys = {
        "record_type",
        "schema_version",
        "artifact_type",
        "artifact_encoding",
        "component_id",
        "created_at_utc",
        "input_lineage",
        "component_lineage",
        "privacy",
        "guards",
    }
    production_footer_keys = {
        "record_type",
        "records_before_footer",
        "section_counts",
    }

    raw_digest = hashlib.sha256()
    stored_digest = hashlib.sha256()
    index_digest = hashlib.sha256()
    raw_bytes = stored_bytes = record_count = tuple_count = multiplicity = 0
    index_bytes = index_records = 0
    kind_position = 0
    saw_header = False
    saw_footer = False
    production_stream = False
    active: dict[str, Any] | None = None
    observed_kind_counts: list[int] = []
    observed_bridge_counts: list[int] = []
    line_buffer = bytearray()
    stream_decoder = json.JSONDecoder(
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
    )

    def _valid_stream_hash(value: object) -> bool:
        return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None

    def _compare_bridge_record(record: Mapping[str, Any]) -> None:
        nonlocal index_bytes, index_records
        assert active is not None
        binding = GROUP_TUPLE_BINDINGS.get((active["stage"], active["kind"]))
        if binding is None:
            return
        value = record["tuple"]
        members: set[int] = set()
        for tuple_field, source_field in binding:
            if tuple_field not in value:
                raise HumanAdjudicationAuditError(
                    "A bridge tuple is missing a semantic binding."
                )
            raw_value = value[tuple_field]
            if raw_value is None:
                continue
            if (
                not isinstance(raw_value, str)
                or b"\x00" in raw_value.encode("utf-8")
                or len(raw_value.encode("utf-8")) > MAX_VALUE_UTF8_BYTES
            ):
                raise HumanAdjudicationAuditError(
                    "A bridge tuple has an invalid semantic value."
                )
            sequence = semantic_lookup.get((source_field, raw_value))
            if sequence is None:
                raise HumanAdjudicationAuditError(
                    "A bridge tuple escaped the frozen semantic universe."
                )
            members.add(sequence)
        ordered = sorted(members)
        if len(ordered) > 4:
            raise HumanAdjudicationAuditError(
                "A bridge tuple exceeds the fixed ordinal-index width."
            )
        expected = struct.pack(
            ">B4I", len(ordered), *(ordered + [0] * (4 - len(ordered)))
        )
        end = index_bytes + LOCAL_EVIDENCE_INDEX_RECORD_BYTES
        if end > len(payload):
            raise HumanAdjudicationAuditError(
                "The private local-evidence ordinal index is truncated."
            )
        actual = payload[index_bytes:end]
        index_digest.update(actual)
        index_bytes = end
        index_records += 1
        if actual != expected:
            raise HumanAdjudicationAuditError(
                "A private ordinal-index record differs from its frozen source tuple."
            )

    def _handle(record: Mapping[str, Any]) -> None:
        nonlocal active, kind_position, saw_header, saw_footer, production_stream
        nonlocal tuple_count, multiplicity
        record_type = record.get("record_type")
        if record_type == "header":
            if saw_header or active is not None or kind_position or saw_footer:
                raise HumanAdjudicationAuditError(
                    "The local-evidence header is misplaced."
                )
            if set(record) not in ({"record_type"}, production_header_keys):
                raise HumanAdjudicationAuditError(
                    "The local-evidence header schema changed."
                )
            production_stream = set(record) == production_header_keys
            saw_header = True
            return
        if record_type == "evidence_kind_begin":
            if production_stream:
                record = _exact_keys(
                    record, begin_keys, "local-evidence kind begin"
                )
            else:
                record = _exact_keys(
                    record,
                    {"record_type", "stage", "tuple_kind"},
                    "synthetic local-evidence kind begin",
                )
            stage = record["stage"]
            kind = record["tuple_kind"]
            stage_kind = f"{stage}:{kind}"
            if (
                not saw_header
                or saw_footer
                or active is not None
                or kind_position >= len(SOURCE_LOCAL_STAGE_KIND_ORDER)
                or stage_kind != SOURCE_LOCAL_STAGE_KIND_ORDER[kind_position]
                or (
                    production_stream
                    and (
                        record["unique_tuples"] != index["kind_counts"][stage_kind]
                        or type(record["total_multiplicity"]) is not int
                        or record["total_multiplicity"] < 0
                        or not _valid_stream_hash(
                            record["global_tuple_set_sha256"]
                        )
                        or not _valid_stream_hash(
                            record["global_tuple_frequency_sha256"]
                        )
                    )
                )
            ):
                raise HumanAdjudicationAuditError(
                    "A local-evidence kind declaration changed."
                )
            active = {
                "stage": stage,
                "kind": kind,
                "count": 0,
                "multiplicity": 0,
                "declared_count": index["kind_counts"][stage_kind],
                "declared_multiplicity": record.get("total_multiplicity"),
                "set_sha256": record.get("global_tuple_set_sha256"),
                "frequency_sha256": record.get("global_tuple_frequency_sha256"),
                "bridge_start": index_records,
            }
            return
        if record_type == "evidence_tuple":
            record = _exact_keys(record, tuple_keys, "local-evidence tuple")
            if (
                active is None
                or saw_footer
                or record["stage"] != active["stage"]
                or record["tuple_kind"] != active["kind"]
                or type(record["multiplicity"]) is not int
                or not 1 <= record["multiplicity"] <= MAX_COUNT
                or not isinstance(record["tuple"], Mapping)
                or not record["tuple"]
            ):
                raise HumanAdjudicationAuditError(
                    "A local-evidence tuple is malformed."
                )
            if (
                active["count"] >= active["declared_count"]
                or active["multiplicity"] > MAX_COUNT - record["multiplicity"]
            ):
                raise HumanAdjudicationAuditError(
                    "A local-evidence tuple payload is malformed."
                )
            active["count"] += 1
            active["multiplicity"] += record["multiplicity"]
            tuple_count += 1
            multiplicity += record["multiplicity"]
            if multiplicity > MAX_COUNT:
                raise HumanAdjudicationAuditError(
                    "The local-evidence multiplicity overflowed."
                )
            _compare_bridge_record(record)
            return
        if record_type == "evidence_kind_end":
            if production_stream:
                record = _exact_keys(record, end_keys, "local-evidence kind end")
            else:
                record = _exact_keys(
                    record,
                    {"record_type", "stage", "tuple_kind"},
                    "synthetic local-evidence kind end",
                )
            if (
                active is None
                or (record["stage"], record["tuple_kind"])
                != (active["stage"], active["kind"])
                or active["count"] != active["declared_count"]
                or (
                    production_stream
                    and (
                        record["records"] != active["count"]
                        or record["total_multiplicity"]
                        != active["multiplicity"]
                        or record["total_multiplicity"]
                        != active["declared_multiplicity"]
                        or record["global_tuple_set_sha256"]
                        != active["set_sha256"]
                        or record["global_tuple_frequency_sha256"]
                        != active["frequency_sha256"]
                    )
                )
            ):
                raise HumanAdjudicationAuditError(
                    "A local-evidence kind failed count conservation."
                )
            observed_kind_counts.append(active["count"])
            if (active["stage"], active["kind"]) in GROUP_TUPLE_BINDINGS:
                observed_bridge_counts.append(index_records - active["bridge_start"])
            kind_position += 1
            active = None
            return
        if record_type == "footer":
            if (
                not saw_header
                or saw_footer
                or active is not None
                or kind_position != len(SOURCE_LOCAL_STAGE_KIND_ORDER)
            ):
                raise HumanAdjudicationAuditError(
                    "The local-evidence footer is misplaced."
                )
            if set(record) == production_footer_keys:
                if (
                    record["records_before_footer"] != record_count - 1
                    or record["section_counts"]
                    != {
                        "tuple_kinds": len(SOURCE_LOCAL_STAGE_KIND_ORDER),
                        "evidence_tuples": tuple_count,
                        "total_multiplicity": multiplicity,
                    }
                ):
                    raise HumanAdjudicationAuditError(
                        "The local-evidence footer failed conservation."
                    )
            elif set(record) != {"record_type"}:
                raise HumanAdjudicationAuditError(
                    "The local-evidence footer schema changed."
                )
            saw_footer = True
            return
        raise HumanAdjudicationAuditError(
            "The local-evidence stream contains an unexpected record."
        )

    def _consume(raw: bytes) -> None:
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
                    raise HumanAdjudicationAuditError(
                        "A local-evidence record exceeds its byte limit."
                    )
                return
            if newline + 1 > MAX_JSON_LINE_BYTES:
                raise HumanAdjudicationAuditError(
                    "A local-evidence record exceeds its byte limit."
                )
            line = bytes(line_buffer[:newline])
            del line_buffer[: newline + 1]
            try:
                value = stream_decoder.decode(line.decode("utf-8"))
            except HumanAdjudicationAuditError:
                raise
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise HumanAdjudicationAuditError(
                    "The local-evidence stream is not strict UTF-8 JSON."
                ) from None
            if not isinstance(value, Mapping):
                raise HumanAdjudicationAuditError(
                    "The local-evidence stream contains a non-object."
                )
            record_count += 1
            _handle(value)

    descriptor: int | None = None
    final_descriptor: int | None = None
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        descriptor, before, parents = _open_beneath(
            root, initial["path"], "The source local evidence"
        )
        if (
            not stat.S_ISREG(before.st_mode)
            or (before.st_dev, before.st_ino) != initial["identity"]
            or before.st_mode != initial["full_mode"]
            or before.st_size != initial["bytes"]
            or before.st_mtime_ns != initial["mtime_ns"]
            or before.st_ctime_ns != initial["ctime_ns"]
            or parents != initial["parents"]
        ):
            raise HumanAdjudicationAuditError(
                "The source local evidence changed before derivation."
            )
        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            stored_digest.update(chunk)
            stored_bytes += len(chunk)
            try:
                _consume(decompressor.decompress(chunk))
            except zlib.error:
                raise HumanAdjudicationAuditError(
                    "The local-evidence gzip stream is invalid."
                ) from None
            if decompressor.unused_data or decompressor.unconsumed_tail:
                raise HumanAdjudicationAuditError(
                    "The local-evidence gzip stream has extra members or tails."
                )
        try:
            _consume(decompressor.flush())
        except zlib.error:
            raise HumanAdjudicationAuditError(
                "The local-evidence gzip stream is invalid."
            ) from None
        after = os.fstat(descriptor)
        final_descriptor, final, final_parents = _open_beneath(
            root, initial["path"], "The source local evidence"
        )
    except HumanAdjudicationAuditError:
        raise
    except OSError:
        raise HumanAdjudicationAuditError(
            "The source local evidence could not be read safely."
        ) from None
    finally:
        if final_descriptor is not None:
            os.close(final_descriptor)
        if descriptor is not None:
            os.close(descriptor)

    if (
        not _same_stat(before, after)
        or not _same_stat(after, final)
        or parents != final_parents
        or not decompressor.eof
        or decompressor.unused_data
        or decompressor.unconsumed_tail
        or line_buffer
        or not saw_header
        or not saw_footer
        or active is not None
        or kind_position != len(SOURCE_LOCAL_STAGE_KIND_ORDER)
        or stored_bytes != source_section.get("stored_bytes")
        or stored_digest.hexdigest() != source_section.get("stored_sha256")
        or raw_bytes != source_section.get("raw_bytes")
        or raw_digest.hexdigest() != source_section.get("raw_sha256")
        or record_count != source_section.get("records")
        or tuple_count != source_section.get("unique_tuples")
        or multiplicity != source_section.get("total_multiplicity")
        or observed_kind_counts != index["all_stage_kind_ordinal_counts"]
        or observed_bridge_counts != index["bridge_block_counts"]
        or index_records != index["index_records"]
        or index_bytes != index["index_bytes"]
        or index_bytes != len(payload)
        or index_digest.hexdigest() != index["index_sha256"]
    ):
        raise HumanAdjudicationAuditError(
            "The frozen local-evidence source-to-index derivation failed conservation."
        )
    return {
        "source_raw_sha256": raw_digest.hexdigest(),
        "source_raw_bytes": raw_bytes,
        "source_records": record_count,
        "source_tuples": tuple_count,
        "source_total_multiplicity": multiplicity,
        "per_kind_counts": observed_kind_counts,
        "bridge_block_counts": observed_bridge_counts,
        "index_sha256": index_digest.hexdigest(),
        "index_bytes": index_bytes,
        "index_records": index_records,
    }

def _validate_group_ledger(
    records: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
    semantic_active: Mapping[str, Mapping[str, Any]],
    registry: Mapping[str, Mapping[str, Any]],
) -> tuple[
    dict[str, Mapping[str, Any]],
    set[str],
    dict[tuple[str, str, int], Mapping[str, Any]],
]:
    if not records or records[0] != {
        "record_type": "mapping_group_ledger_begin",
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "config_sha256": contract["config_sha256"],
        "append_only_revisions": True,
        "initial_group_count": 0,
    }:
        raise HumanAdjudicationAuditError("The mapping-group ledger header changed.")
    all_ids = set(semantic_active)
    histories: dict[str, dict[int, tuple[str, Mapping[str, Any]]]] = {}
    active: dict[str, Mapping[str, Any]] = {}
    active_hash: dict[str, str] = {}
    reviewers: set[str] = set()
    revision_events: dict[tuple[str, str, int], Mapping[str, Any]] = {}
    for raw_record in records[1:]:
        record = _exact_keys(
            raw_record,
            {
                "record_type",
                "mapping_group_id",
                "revision",
                "supersedes_sha256",
                "revision_reason",
                "review_status",
                "member_review_ids",
                "local_evidence_refs",
                "dimensions",
                "rationale",
                "reviewer_id",
                "reviewed_at_utc",
            },
            "mapping group revision",
        )
        group_id = record["mapping_group_id"]
        revision = record["revision"]
        supersedes = record["supersedes_sha256"]
        members = record["member_review_ids"]
        if (
            record["record_type"] != "mapping_group_revision"
            or not isinstance(group_id, str)
            or GROUP_ID_RE.fullmatch(group_id) is None
            or record["review_status"] != "reviewed"
        ):
            raise HumanAdjudicationAuditError("A mapping-group identity is invalid.")
        _positive_int(revision, "mapping-group revision")
        _nonempty_text(record["revision_reason"], "mapping-group revision reason")
        if supersedes is not None and (
            not isinstance(supersedes, str) or SHA256_RE.fullmatch(supersedes) is None
        ):
            raise HumanAdjudicationAuditError(
                "A mapping-group predecessor hash is invalid."
            )
        if (
            not isinstance(members, list)
            or len(members) < 2
            or members != sorted(members)
            or len(members) != len(set(members))
            or any(member not in all_ids for member in members)
        ):
            raise HumanAdjudicationAuditError("A mapping-group member set is invalid.")
        local_refs = _evidence_refs(
            record["local_evidence_refs"], registry, required=True
        )
        if any(
            registry[reference]["namespace"] != "local_tuple"
            or f"{registry[reference]['locator']['stage']}:"
            f"{registry[reference]['locator']['tuple_kind']}" not in GROUP_LOCAL_KINDS
            for reference in local_refs
        ):
            raise HumanAdjudicationAuditError(
                "A mapping group cites ineligible local evidence."
            )
        member_set = set(members)
        if not any(
            member_set.issubset(set(registry[reference].get("semantic_members", ())))
            for reference in local_refs
        ):
            raise HumanAdjudicationAuditError(
                "No exact eligible local tuple covers a mapping group."
            )
        _validate_dimensions(
            record["dimensions"],
            contract["config"]["semantic_review"],
            registry,
            "reviewed",
            None,
        )
        product_refs = record["dimensions"]["product_identity"]["evidence_refs"]
        if not any(
            registry[reference]["namespace"] != "local_tuple"
            for reference in product_refs
        ):
            raise HumanAdjudicationAuditError(
                "A mapping group lacks identity evidence beyond co-occurrence."
            )
        _nonempty_text(record["rationale"], "mapping-group rationale")
        _nonempty_text(record["reviewer_id"], "mapping-group reviewer", 256)
        if not _strict_utc(record["reviewed_at_utc"]):
            raise HumanAdjudicationAuditError("A mapping-group review time is invalid.")
        digest = _record_sha(record)
        history = histories.setdefault(group_id, {})
        existing = history.get(revision)
        if existing is not None:
            if existing[0] != digest:
                raise HumanAdjudicationAuditError(
                    "Conflicting mapping-group revisions share one number."
                )
            continue
        if revision != len(history) + 1:
            raise HumanAdjudicationAuditError(
                "A mapping-group revision chain has a gap or branch."
            )
        if (revision == 1 and supersedes is not None) or (
            revision > 1 and supersedes != active_hash[group_id]
        ):
            raise HumanAdjudicationAuditError(
                "A mapping-group revision does not bind its predecessor."
            )
        history[revision] = digest, record
        active[group_id] = record
        active_hash[group_id] = digest
        reviewers.add(record["reviewer_id"])
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
    for review_id, decision in semantic_active.items():
        group_id = decision["mapping_group_id"]
        if group_id is not None:
            assignments.setdefault(group_id, set()).add(review_id)
    if set(assignments) != set(active):
        raise HumanAdjudicationAuditError(
            "The mapping-group registry and item assignments differ."
        )
    for group_id, group in active.items():
        if assignments[group_id] != set(group["member_review_ids"]):
            raise HumanAdjudicationAuditError(
                "A mapping-group active member set differs from assignments."
            )
        for review_id in group["member_review_ids"]:
            references = semantic_active[review_id]["dimensions"]["product_identity"][
                "evidence_refs"
            ]
            if not any(
                registry[reference]["namespace"] != "local_tuple"
                for reference in references
            ):
                raise HumanAdjudicationAuditError(
                    "A grouped member lacks independent identity evidence."
                )
    return active, reviewers, revision_events


def _validate_attestations(
    records: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
    bindings: Mapping[tuple[str, int], Mapping[str, Any]],
    group_sha256: str,
) -> tuple[
    set[str],
    dict[str, Mapping[str, Any]],
    dict[tuple[str, int], str],
]:
    if not records or records[0] != {
        "record_type": "batch_attestation_ledger_begin",
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "config_sha256": contract["config_sha256"],
        "initial_attestation_count": 0,
    }:
        raise HumanAdjudicationAuditError("The batch-attestation header changed.")
    current: set[tuple[str, int]] = set()
    reviewers: set[str] = set()
    exact_seen: set[bytes] = set()
    attestation_bindings: dict[str, Mapping[str, Any]] = {}
    current_hashes: dict[tuple[str, int], str] = {}
    for raw_record in records[1:]:
        record = _exact_keys(
            raw_record,
            {
                "record_type",
                "review_kind",
                "batch_index",
                "item_count",
                "active_decisions_sha256",
                "decision_ledger_sha256",
                "mapping_group_registry_sha256",
                "review_policy_version",
                "attestation_method",
                "reviewer_id",
                "attested_at_utc",
            },
            "batch attestation",
        )
        kind = record["review_kind"]
        index = record["batch_index"]
        key = kind, index
        if (
            record["record_type"] != "batch_attestation"
            or kind not in {"semantic", "route"}
            or type(index) is not int
            or key not in bindings
            or record["review_policy_version"] != contract["config"].get("rule_version")
            or record["attestation_method"] != "human"
        ):
            raise HumanAdjudicationAuditError(
                "A batch attestation identity is invalid."
            )
        if (
            any(
                not isinstance(record[field], str)
                or SHA256_RE.fullmatch(record[field]) is None
                for field in ("active_decisions_sha256", "decision_ledger_sha256")
            )
            or (
                kind == "semantic"
                and (
                    not isinstance(record["mapping_group_registry_sha256"], str)
                    or SHA256_RE.fullmatch(record["mapping_group_registry_sha256"])
                    is None
                )
            )
            or (kind == "route" and record["mapping_group_registry_sha256"] is not None)
        ):
            raise HumanAdjudicationAuditError("A batch attestation hash is invalid.")
        _positive_int(record["item_count"], "attestation item count")
        _nonempty_text(record["reviewer_id"], "attestation reviewer", 256)
        if not _strict_utc(record["attested_at_utc"]):
            raise HumanAdjudicationAuditError("A batch attestation time is invalid.")
        reviewers.add(record["reviewer_id"])
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
        binding = bindings[key]
        expected_group = group_sha256 if kind == "semantic" else None
        if (
            record["item_count"] == binding["item_count"]
            and record["active_decisions_sha256"] == binding["active_hash"]
            and record["decision_ledger_sha256"] == binding["ledger_sha256"]
            and record["mapping_group_registry_sha256"] == expected_group
        ):
            if key in current_hashes:
                raise HumanAdjudicationAuditError(
                    "A batch has multiple distinct current attestations."
                )
            current.add(key)
            current_hashes[key] = record_hash
    if current != set(bindings):
        raise HumanAdjudicationAuditError(
            "One or more batches lack a current human attestation."
        )
    return reviewers, attestation_bindings, current_hashes


def _walk_workspace(
    workspace: Path, *, root: Path | None = None
) -> tuple[set[str], list[Path]]:
    """Inventory a private tree through no-follow directory descriptors."""

    anchor = root if root is not None else workspace.parent
    descriptor: int | None = None
    files: set[str] = set()
    directories: list[Path] = [workspace]
    try:
        descriptor, workspace_stat, _ = _open_beneath(
            anchor, workspace, "The private workspace"
        )
        if not stat.S_ISDIR(workspace_stat.st_mode):
            raise HumanAdjudicationAuditError(
                "The private workspace is not a real directory."
            )

        def visit(current: int, relative_parts: tuple[str, ...]) -> None:
            try:
                names = sorted(os.listdir(current))
            except OSError:
                raise HumanAdjudicationAuditError(
                    "The private workspace cannot be inventoried safely."
                ) from None
            for name in names:
                if not isinstance(name, str) or name in {"", ".", ".."} or "/" in name:
                    raise HumanAdjudicationAuditError(
                        "The private workspace contains an unsafe entry name."
                    )
                try:
                    item = os.stat(name, dir_fd=current, follow_symlinks=False)
                except OSError:
                    raise HumanAdjudicationAuditError(
                        "The private workspace changed during inventory."
                    ) from None
                parts = (*relative_parts, name)
                relative = Path(*parts).as_posix()
                if stat.S_ISREG(item.st_mode):
                    files.add(relative)
                    continue
                if not stat.S_ISDIR(item.st_mode):
                    raise HumanAdjudicationAuditError(
                        "The private workspace contains a symlink or special file."
                    )
                flags = os.O_RDONLY
                if hasattr(os, "O_DIRECTORY"):
                    flags |= os.O_DIRECTORY
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                child: int | None = None
                try:
                    child = os.open(name, flags, dir_fd=current)
                    opened = os.fstat(child)
                    if not _same_stat(item, opened):
                        raise HumanAdjudicationAuditError(
                            "The private workspace changed during inventory."
                        )
                    directories.append(workspace.joinpath(*parts))
                    visit(child, parts)
                    after = os.fstat(child)
                    if not _same_stat(opened, after):
                        raise HumanAdjudicationAuditError(
                            "A private directory changed during inventory."
                        )
                except HumanAdjudicationAuditError:
                    raise
                except OSError:
                    raise HumanAdjudicationAuditError(
                        "The private workspace contains an unsafe directory."
                    ) from None
                finally:
                    if child is not None:
                        os.close(child)

        visit(descriptor, ())
        if not _same_stat(workspace_stat, os.fstat(descriptor)):
            raise HumanAdjudicationAuditError(
                "The private workspace changed during inventory."
            )
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return files, directories


def _workspace_paths(batch_count: int) -> dict[str, list[str]]:
    return {
        "semantic_source": [
            f"semantic-source/semantic-source-batch-{index:04d}.jsonl"
            for index in range(1, batch_count + 1)
        ],
        "semantic_decisions": [
            f"semantic-decisions/semantic-decisions-batch-{index:04d}.jsonl"
            for index in range(1, batch_count + 1)
        ],
        "route_source": ["route-source/route-source-batch-0001.jsonl"],
        "route_decisions": ["route-decisions/route-decisions-batch-0001.jsonl"],
        "groups": ["semantic-groups/mapping-groups.jsonl"],
        "events": ["workspace-events.jsonl"],
        "evidence": ["evidence-registry/evidence-registry.jsonl"],
        "local_index": [LOCAL_EVIDENCE_INDEX_FILE],
        "attestations": ["attestations/batch-attestations.jsonl"],
        "revisions": ["revisions/revision-events.jsonl"],
        "manifest": ["workspace-manifest.json"],
    }


def _utc_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _revision_event_subject(binding: Mapping[str, Any]) -> str:
    if binding["revision_kind"] == "mapping_group":
        return f"mapping_group:{binding['subject_id']}:{binding['revision']}"
    return (
        f"{binding['revision_kind']}:{binding['batch_index']:04d}:"
        f"{binding['subject_id']}:{binding['revision']}"
    )


def _attestation_event_subject(binding: Mapping[str, Any]) -> str:
    return f"{binding['review_kind']}:{binding['batch_index']:04d}"


def _validate_revision_events(
    records: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
    expected: Mapping[tuple[str, str, int], Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], set[str]]:
    if not records or records[0] != {
        "record_type": "revision_event_ledger_begin",
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "config_sha256": contract["config_sha256"],
        "initial_event_count": 0,
    }:
        raise HumanAdjudicationAuditError("The revision-event ledger header changed.")
    seen: set[tuple[str, str, int]] = set()
    by_hash: dict[str, Mapping[str, Any]] = {}
    reviewers: set[str] = set()
    previous_hash: str | None = None
    previous_time: datetime | None = None
    for event_index, raw_record in enumerate(records[1:], start=1):
        record = _exact_keys(raw_record, REVISION_EVENT_KEYS, "revision event")
        key = (
            record["revision_kind"],
            record["subject_id"],
            record["revision"],
        )
        binding = expected.get(key)
        if (
            record["record_type"] != "revision_event"
            or record["event_index"] != event_index
            or record["previous_event_sha256"] != previous_hash
            or binding is None
            or key in seen
        ):
            raise HumanAdjudicationAuditError(
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
                raise HumanAdjudicationAuditError(
                    "A revision event does not bind its ledger revision."
                )
        if not _strict_utc(record["recorded_at_utc"]):
            raise HumanAdjudicationAuditError("A revision-event time is invalid.")
        current_time = _utc_datetime(record["recorded_at_utc"])
        if previous_time is not None and current_time < previous_time:
            raise HumanAdjudicationAuditError("Revision-event times move backwards.")
        _nonempty_text(record["reviewer_id"], "revision-event reviewer", 256)
        reviewers.add(record["reviewer_id"])
        event_hash = _record_sha(record)
        by_hash[event_hash] = binding
        previous_hash = event_hash
        previous_time = current_time
        seen.add(key)
    if seen != set(expected):
        raise HumanAdjudicationAuditError(
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
            for (kind, index), attestation_hash in sorted(current_attestations.items())
        ],
    }
    return hashlib.sha256(
        ACTIVE_WORKSPACE_STATE_VERSION + _canonical_json(state)
    ).hexdigest()


def _validate_workspace_events(
    records: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
    manifest: Mapping[str, Any],
    revision_events: Mapping[str, Mapping[str, Any]],
    attestations: Mapping[str, Mapping[str, Any]],
    active_state_sha256: str,
    reviewer_id: str,
) -> int:
    if not records or records[0] != {
        "record_type": "workspace_event_ledger_begin",
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "config_sha256": contract["config_sha256"],
        "initial_event_count": 0,
    }:
        raise HumanAdjudicationAuditError("The workspace-event ledger header changed.")
    consumed_revisions: set[str] = set()
    consumed_attestations: set[str] = set()
    previous_hash: str | None = None
    previous_time: datetime | None = None
    initialized = completion = abandoned = False
    for event_index, raw_record in enumerate(records[1:], start=1):
        record = _exact_keys(raw_record, WORKSPACE_EVENT_KEYS, "workspace event")
        if (
            record["record_type"] != "workspace_event"
            or record["event_index"] != event_index
            or record["previous_event_sha256"] != previous_hash
            or record["event_type"] not in WORKSPACE_EVENT_TYPES
            or not _strict_utc(record["event_at_utc"])
        ):
            raise HumanAdjudicationAuditError(
                "A workspace event breaks schema, sequence, or hash chain."
            )
        current_time = _utc_datetime(record["event_at_utc"])
        if previous_time is not None and current_time < previous_time:
            raise HumanAdjudicationAuditError("Workspace-event times move backwards.")
        _nonempty_text(record["actor_id"], "workspace-event actor", 256)
        subject_hash = record["subject_sha256"]
        if (
            not isinstance(subject_hash, str)
            or SHA256_RE.fullmatch(subject_hash) is None
        ):
            raise HumanAdjudicationAuditError(
                "A workspace-event subject hash is invalid."
            )
        if abandoned:
            raise HumanAdjudicationAuditError(
                "An abandoned workspace has a later event."
            )
        event_type = record["event_type"]
        if event_type == "initialized":
            if (
                event_index != 1
                or initialized
                or record["actor_id"] != "workspace_initializer"
                or record["event_at_utc"] != manifest.get("created_at_utc")
                or record["subject_kind"] != "component_config"
                or record["subject_id"] != COMPONENT_ID
                or subject_hash != contract["config_sha256"]
            ):
                raise HumanAdjudicationAuditError(
                    "The initialization event is invalid."
                )
            initialized = True
        elif event_type in {
            "batch_submitted",
            "batch_revised",
            "group_registry_revised",
        }:
            binding = revision_events.get(subject_hash)
            if (
                binding is None
                or subject_hash in consumed_revisions
                or record["subject_kind"] != "revision_event"
                or record["subject_id"] != _revision_event_subject(binding)
                or record["actor_id"] != binding["reviewer_id"]
                or record["event_at_utc"] != binding["recorded_at_utc"]
                or completion
            ):
                raise HumanAdjudicationAuditError(
                    "A workspace revision event lacks its unique bound revision."
                )
            expected_type = (
                "group_registry_revised"
                if binding["revision_kind"] == "mapping_group"
                else "batch_submitted" if binding["revision"] == 2 else "batch_revised"
            )
            if event_type != expected_type:
                raise HumanAdjudicationAuditError(
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
                or completion
            ):
                raise HumanAdjudicationAuditError(
                    "An attestation event lacks its unique bound attestation."
                )
            consumed_attestations.add(subject_hash)
        elif event_type == "validation_failed":
            if (
                record["subject_kind"] != "component_config"
                or record["subject_id"] != COMPONENT_ID
                or subject_hash != contract["config_sha256"]
            ):
                raise HumanAdjudicationAuditError(
                    "A validation-failed event has an invalid contract binding."
                )
        elif event_type == "human_review_complete_unfrozen":
            if (
                completion
                or consumed_revisions != set(revision_events)
                or consumed_attestations != set(attestations)
                or record["actor_id"] != reviewer_id
                or record["subject_kind"] != "active_workspace_state"
                or record["subject_id"] != COMPONENT_ID
                or subject_hash != active_state_sha256
            ):
                raise HumanAdjudicationAuditError(
                    "A completion event precedes validated workspace completion."
                )
            completion = True
        elif event_type == "abandoned":
            if (
                record["subject_kind"] != "component_config"
                or record["subject_id"] != COMPONENT_ID
                or subject_hash != contract["config_sha256"]
            ):
                raise HumanAdjudicationAuditError("An abandoned event is invalid.")
            abandoned = True
        else:  # pragma: no cover - frozen vocabulary is exhaustive
            raise HumanAdjudicationAuditError("A workspace event type is unsupported.")
        previous_hash = _record_sha(record)
        previous_time = current_time
    if (
        not initialized
        or not completion
        or abandoned
        or consumed_revisions != set(revision_events)
        or consumed_attestations != set(attestations)
    ):
        raise HumanAdjudicationAuditError(
            "The workspace-event ledger does not establish formal human completion."
        )
    return len(records) - 1


def _validate_manifest(
    manifest: Mapping[str, Any],
    root: Path,
    workspace: Path,
    config_path: Path,
    contract: Mapping[str, Any],
    semantic_count: int,
    route_count: int,
    membership_count: int,
) -> tuple[dict[str, Mapping[str, Any]], set[str]]:
    config = contract["config"]
    source = config["source_artifact"]
    index_contract = _local_index_contract(config)
    if (
        manifest.get("schema_version") != 1
        or manifest.get("component_id") != COMPONENT_ID
        or manifest.get("artifact_type")
        != "potassium_query202_private_human_adjudication_workspace"
        or manifest.get("status") != "initialized"
        or manifest.get("formal_workspace") is not True
        or manifest.get("preview_cannot_be_upgraded") is not False
        or manifest.get("artifact_directory") != workspace.relative_to(root).as_posix()
        or not _strict_utc(manifest.get("created_at_utc"))
    ):
        raise HumanAdjudicationAuditError(
            "The workspace is not an initialized formal artifact."
        )
    if "_structural-previews" in workspace.parts:
        raise HumanAdjudicationAuditError(
            "Structural-preview artifacts are explicitly non-auditable."
        )
    lineage = manifest.get("component_lineage")
    if (
        not isinstance(lineage, Mapping)
        or lineage.get("config") != config_path.as_posix()
        or lineage.get("config_sha256") != contract["config_sha256"]
        or lineage.get("status_at_initialization") != "frozen_for_execution"
        or lineage.get("generator_bundle_sha256")
        != contract["generator_bundle"]["sha256"]
    ):
        raise HumanAdjudicationAuditError("The workspace component lineage changed.")
    source_lineage = manifest.get("source_lineage")
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
        "ndc_decision_config_sha256": config["ndc_decision"]["config_sha256"],
    }
    if source_lineage != expected_source_lineage:
        raise HumanAdjudicationAuditError("The workspace source lineage changed.")
    cardinality = manifest.get("cardinality")
    if cardinality != {
        "semantic_items": semantic_count,
        "semantic_batches": config["workspace"]["semantic_batch_count"],
        "semantic_batch_size": config["workspace"]["semantic_batch_size"],
        "route_items": route_count,
        "route_batches": 1,
        "route_nonnull_memberships": source["route_template"][
            "source_specific_nonnull_memberships"
        ],
        "route_sql_null_memberships": source["route_template"][
            "source_specific_sql_null_memberships"
        ],
        "route_typed_memberships": membership_count,
        "local_evidence_bridge_index_records": index_contract["index_records"],
        "mapping_groups": 0,
    }:
        raise HumanAdjudicationAuditError(
            "The workspace cardinality declaration changed."
        )
    privacy = manifest.get("privacy")
    if privacy != {
        "directory_mode": "0700",
        "file_mode": "0600",
        "git_ignored": True,
        "raw_values_printed": False,
        "database_connected": False,
        "external_api_called": False,
        "llm_called": False,
    }:
        raise HumanAdjudicationAuditError("The workspace privacy declaration changed.")
    guards = manifest.get("guards")
    if (
        not isinstance(guards, Mapping)
        or guards.get("workspace_initialized") is not True
    ):
        raise HumanAdjudicationAuditError("The workspace initialization guard changed.")
    if any(
        guards.get(key) is not False
        for key in (
            "semantic_review_complete",
            "reviewed_semantic_ledger_frozen",
            "route_review_complete",
            "route_mapping_frozen",
            "product_identity_decided",
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
            "database_connected",
            "external_api_called",
            "llm_called",
        )
    ):
        raise HumanAdjudicationAuditError(
            "A workspace scientific guard was pre-enabled."
        )
    immutable = manifest.get("immutable_source_files")
    if not isinstance(immutable, list):
        raise HumanAdjudicationAuditError("The immutable-source manifest is absent.")
    immutable_by_path: dict[str, Mapping[str, Any]] = {}
    for item in immutable:
        if not isinstance(item, Mapping) or not isinstance(item.get("file"), str):
            raise HumanAdjudicationAuditError(
                "An immutable-source declaration is invalid."
            )
        path = item["file"]
        if path in immutable_by_path:
            raise HumanAdjudicationAuditError(
                "The immutable-source manifest repeats a file."
            )
        immutable_by_path[path] = item
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
    if (
        len(immutable_by_path) != config["workspace"]["semantic_batch_count"] + 2
        or immutable_by_path.get(LOCAL_EVIDENCE_INDEX_FILE)
        != expected_index_manifest
    ):
        raise HumanAdjudicationAuditError(
            "The immutable local-evidence index manifest binding changed."
        )
    editable = manifest.get("editable_ledger_files_at_initialization")
    editable_paths: set[str] = set()
    if not isinstance(editable, list):
        raise HumanAdjudicationAuditError("The editable-ledger manifest is absent.")
    for item in editable:
        if (
            not isinstance(item, Mapping)
            or not isinstance(item.get("file"), str)
            or item["file"] in editable_paths
            or not isinstance(item.get("sha256"), str)
            or SHA256_RE.fullmatch(item["sha256"]) is None
            or item.get("mode") != "0600"
        ):
            raise HumanAdjudicationAuditError(
                "An initialization ledger declaration is invalid."
            )
        editable_paths.add(item["file"])
    return immutable_by_path, editable_paths


def _finish_closure(
    contract: Mapping[str, Any],
    source_inventory: Mapping[str, Any],
    workspace: Path,
    workspace_directory_snapshot: Mapping[str, Any],
    directory_snapshots: Mapping[str, Mapping[str, Any]],
    file_snapshots: Mapping[str, Mapping[str, Any]],
) -> None:
    final_source_directory = _snapshot_directory(
        source_inventory["directory"],
        "The source artifact directory",
        root=contract["root"],
    )
    if _directory_seal(final_source_directory) != _directory_seal(
        source_inventory["directory_snapshot"]
    ):
        raise HumanAdjudicationAuditError("The source inventory changed during audit.")
    for initial in source_inventory["snapshots"].values():
        final = _snapshot_file(
            initial["path"], "A source closure file", root=contract["root"]
        )
        if _file_seal(final) != _file_seal(initial):
            raise HumanAdjudicationAuditError("A source file changed during audit.")
    final_config = _snapshot_file(
        contract["path"], "The audit config", root=contract["root"]
    )
    if _file_seal(final_config) != _file_seal(contract["snapshot"]):
        raise HumanAdjudicationAuditError("The audit config changed during audit.")
    for bundle_name in ("generator_bundle", "auditor_bundle"):
        for initial in contract[bundle_name]["snapshots"].values():
            final = _snapshot_file(
                initial["path"],
                "An implementation closure file",
                root=contract["root"],
            )
            if _file_seal(final) != _file_seal(initial):
                raise HumanAdjudicationAuditError(
                    "An implementation file changed during audit."
                )
    for initial in contract["test_attestation_snapshots"].values():
        final = _reopen_test_attestation_closure_file(contract["root"], initial)
        if _file_seal(final) != _file_seal(initial):
            raise HumanAdjudicationAuditError(
                "A synthetic-test attestation closure file changed during audit."
            )
    final_files, final_directories = _walk_workspace(workspace, root=contract["root"])
    if final_files != set(file_snapshots):
        raise HumanAdjudicationAuditError(
            "The workspace file inventory changed during audit."
        )
    final_directory_map = {
        path.relative_to(workspace).as_posix(): _snapshot_directory(
            path, "A workspace directory", root=contract["root"]
        )
        for path in final_directories
    }
    if set(final_directory_map) != set(directory_snapshots):
        raise HumanAdjudicationAuditError(
            "The workspace directory inventory changed during audit."
        )
    for relative, initial in directory_snapshots.items():
        if _directory_seal(final_directory_map[relative]) != _directory_seal(initial):
            raise HumanAdjudicationAuditError(
                "A workspace directory changed during audit."
            )
    final_workspace = _snapshot_directory(
        workspace, "The human-review workspace", root=contract["root"]
    )
    if _directory_seal(final_workspace) != _directory_seal(
        workspace_directory_snapshot
    ):
        raise HumanAdjudicationAuditError("The workspace changed during audit.")
    for relative, initial in file_snapshots.items():
        final = _snapshot_file(
            workspace / relative,
            "A workspace closure file",
            root=contract["root"],
        )
        if _file_seal(final) != _file_seal(initial):
            raise HumanAdjudicationAuditError("A workspace file changed during audit.")


def audit_human_adjudication_workspace(
    root: Path,
    workspace_directory: Path,
    config_path: Path = CONFIG_PATH,
) -> dict[str, Any]:
    """Independently audit a formal, human-complete private workspace.

    The returned report deliberately cannot serve as the independent audit of
    a compiled artifact.  It writes no artifact and exposes no exact
    source value, evidence locator, reviewer identity, or per-value hash.
    """

    root = root.resolve(strict=True)
    contract = _load_contract(root, config_path)
    source_inventory = _source_inventory(root, contract)
    source = contract["config"]["source_artifact"]
    semantic_records = _stream_records(
        source_inventory["snapshots"]["semantic"],
        source["semantic_template"],
        "The semantic source stream",
    )
    route_records = _stream_records(
        source_inventory["snapshots"]["route"],
        source["route_template"],
        "The route source stream",
    )
    semantic_items = _parse_semantic_template(
        semantic_records, source["semantic_template"]
    )
    route_items, route_memberships = _parse_route_template(
        route_records, source["route_template"]
    )

    if workspace_directory.is_absolute() or ".." in workspace_directory.parts:
        raise HumanAdjudicationAuditError("The workspace path is unsafe.")
    workspace_config = contract["config"]["workspace"]
    expected_workspace_parent = _safe_relative(
        workspace_config.get("artifact_parent"), "formal workspace parent"
    )
    if (
        workspace_directory.parent != expected_workspace_parent
        or not _valid_strict_timestamp_leaf(workspace_directory.name)
    ):
        raise HumanAdjudicationAuditError(
            "The formal workspace is outside its exact configured parent or leaf contract."
        )
    workspace = _project_path(
        root, workspace_directory.as_posix(), "human-adjudication workspace"
    )
    if "_structural-previews" in workspace.relative_to(root).parts:
        raise HumanAdjudicationAuditError(
            "Structural-preview artifacts are explicitly non-auditable."
        )
    workspace_initial = _snapshot_directory(
        workspace, "The human-review workspace", root=root
    )
    if workspace_initial["mode"] != 0o700 or not _git_ignored(root, workspace):
        raise HumanAdjudicationAuditError(
            "The human-review workspace is not private and Git-ignored."
        )
    batch_size = workspace_config["semantic_batch_size"]
    batch_count = workspace_config["semantic_batch_count"]
    if (len(semantic_items) + batch_size - 1) // batch_size != batch_count:
        raise HumanAdjudicationAuditError("The fixed semantic partition changed.")
    paths = _workspace_paths(batch_count)
    core_files = {relative for group in paths.values() for relative in group}
    actual_files, directories = _walk_workspace(workspace, root=root)
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
    directory_map = {
        path.relative_to(workspace).as_posix(): _snapshot_directory(
            path, "A workspace directory", root=root
        )
        for path in directories
    }
    if (
        set(workspace_initial["entries"])
        != set(workspace_config["allowed_top_level_entries"])
        or set(directory_map) != expected_directories
        or any(snapshot["mode"] != 0o700 for snapshot in directory_map.values())
        or not core_files.issubset(actual_files)
        or any(
            relative not in core_files
            and not relative.startswith("evidence-registry/documents/")
            for relative in actual_files
        )
    ):
        raise HumanAdjudicationAuditError(
            "The strict private workspace inventory changed."
        )
    snapshots: dict[str, dict[str, Any]] = {}
    for relative in sorted(actual_files):
        snapshot = _snapshot_file(
            workspace / relative,
            "A workspace file",
            retain_payload=True,
            root=root,
        )
        if snapshot["mode"] != 0o600 or snapshot["nlink"] != 1:
            raise HumanAdjudicationAuditError(
                "A private workspace file has an unsafe mode or link count."
            )
        snapshots[relative] = snapshot

    manifest = _read_json(
        snapshots["workspace-manifest.json"], "The workspace manifest"
    )
    immutable_manifest, editable_manifest = _validate_manifest(
        manifest,
        root,
        workspace,
        config_path,
        contract,
        len(semantic_items),
        len(route_items),
        len(route_memberships),
    )
    expected_editable = (
        set(paths["semantic_decisions"])
        | set(paths["route_decisions"])
        | set(paths["groups"])
        | set(paths["events"])
        | set(paths["evidence"])
        | set(paths["attestations"])
        | set(paths["revisions"])
    )
    if editable_manifest != expected_editable:
        raise HumanAdjudicationAuditError(
            "The initialization editable-ledger inventory changed."
        )
    all_review_ids = {item["review_id"] for item in [*semantic_items, *route_items]}
    registry, documents = _validate_evidence_registry(
        _snapshot_records(
            snapshots["evidence-registry/evidence-registry.jsonl"],
            "The evidence registry",
        ),
        contract,
        all_review_ids,
        snapshots,
    )
    if actual_files != core_files | documents:
        raise HumanAdjudicationAuditError(
            "The private evidence-document inventory differs from the registry."
        )
    _audit_local_evidence_source_to_index(
        source_inventory,
        contract["config"],
        semantic_items,
        snapshots[LOCAL_EVIDENCE_INDEX_FILE],
    )
    _scan_local_evidence_index(
        snapshots[LOCAL_EVIDENCE_INDEX_FILE],
        contract["config"],
        registry,
        len(semantic_items),
    )

    semantic_active: dict[str, Mapping[str, Any]] = {}
    batch_bindings: dict[tuple[str, int], dict[str, Any]] = {}
    reviewers: set[str] = set()
    expected_revision_events: dict[tuple[str, str, int], Mapping[str, Any]] = {}
    for index in range(1, batch_count + 1):
        source_relative = paths["semantic_source"][index - 1]
        ledger_relative = paths["semantic_decisions"][index - 1]
        source_snapshot = snapshots[source_relative]
        expected_items = semantic_items[(index - 1) * batch_size : index * batch_size]
        declared = immutable_manifest.get(source_relative)
        if (
            not isinstance(declared, Mapping)
            or declared.get("sha256") != source_snapshot["sha256"]
            or declared.get("bytes") != source_snapshot["bytes"]
            or declared.get("mode") != "0600"
            or declared.get("items") != len(expected_items)
            or declared.get("memberships") != 0
        ):
            raise HumanAdjudicationAuditError(
                "An immutable semantic source lost its manifest binding."
            )
        _validate_source_batch(
            _snapshot_records(source_snapshot, "An immutable semantic source batch"),
            "semantic",
            index,
            batch_count,
            expected_items,
        )
        active, active_hash, batch_reviewers, batch_revision_events = (
            _validate_decision_ledger(
                _snapshot_records(
                    snapshots[ledger_relative], "A semantic decision ledger"
                ),
                "semantic",
                index,
                batch_count,
                source_relative,
                source_snapshot,
                [item["review_id"] for item in expected_items],
                contract,
                registry,
            )
        )
        if set(semantic_active).intersection(active):
            raise HumanAdjudicationAuditError(
                "Semantic review IDs overlap across batches."
            )
        semantic_active.update(active)
        reviewers.update(batch_reviewers)
        if set(expected_revision_events).intersection(batch_revision_events):
            raise HumanAdjudicationAuditError(
                "Revision-event identities overlap across decision ledgers."
            )
        expected_revision_events.update(batch_revision_events)
        batch_bindings[("semantic", index)] = {
            "item_count": len(expected_items),
            "active_hash": active_hash,
            "ledger_sha256": snapshots[ledger_relative]["sha256"],
        }
    if len(semantic_active) != len(semantic_items):
        raise HumanAdjudicationAuditError(
            "The semantic workspace lost source conservation."
        )

    route_source_relative = paths["route_source"][0]
    route_ledger_relative = paths["route_decisions"][0]
    route_source_snapshot = snapshots[route_source_relative]
    declared_route = immutable_manifest.get(route_source_relative)
    if (
        not isinstance(declared_route, Mapping)
        or declared_route.get("sha256") != route_source_snapshot["sha256"]
        or declared_route.get("bytes") != route_source_snapshot["bytes"]
        or declared_route.get("mode") != "0600"
        or declared_route.get("items") != len(route_items)
        or declared_route.get("memberships") != len(route_memberships)
    ):
        raise HumanAdjudicationAuditError(
            "The immutable route source lost its manifest binding."
        )
    if set(immutable_manifest) != set(paths["semantic_source"]) | {
        route_source_relative,
        LOCAL_EVIDENCE_INDEX_FILE,
    }:
        raise HumanAdjudicationAuditError("The immutable-source inventory changed.")
    _validate_source_batch(
        _snapshot_records(route_source_snapshot, "The immutable route source batch"),
        "route",
        1,
        1,
        route_items,
        route_memberships,
    )
    (
        route_active,
        route_active_hash,
        route_reviewers,
        route_revision_events,
    ) = _validate_decision_ledger(
        _snapshot_records(
            snapshots[route_ledger_relative], "The route decision ledger"
        ),
        "route",
        1,
        1,
        route_source_relative,
        route_source_snapshot,
        [item["review_id"] for item in route_items],
        contract,
        registry,
    )
    reviewers.update(route_reviewers)
    if set(expected_revision_events).intersection(route_revision_events):
        raise HumanAdjudicationAuditError(
            "Revision-event identities overlap across decision ledgers."
        )
    expected_revision_events.update(route_revision_events)
    batch_bindings[("route", 1)] = {
        "item_count": len(route_items),
        "active_hash": route_active_hash,
        "ledger_sha256": snapshots[route_ledger_relative]["sha256"],
    }
    group_relative = paths["groups"][0]
    groups, group_reviewers, group_revision_events = _validate_group_ledger(
        _snapshot_records(snapshots[group_relative], "The mapping-group ledger"),
        contract,
        semantic_active,
        registry,
    )
    reviewers.update(group_reviewers)
    if set(expected_revision_events).intersection(group_revision_events):
        raise HumanAdjudicationAuditError(
            "Revision-event identities overlap with mapping groups."
        )
    expected_revision_events.update(group_revision_events)
    (
        attestation_reviewers,
        attestation_bindings,
        current_attestation_hashes,
    ) = _validate_attestations(
        _snapshot_records(
            snapshots[paths["attestations"][0]], "The batch-attestation ledger"
        ),
        contract,
        batch_bindings,
        snapshots[group_relative]["sha256"],
    )
    reviewers.update(attestation_reviewers)
    revision_events_by_hash, revision_event_reviewers = _validate_revision_events(
        _snapshot_records(
            snapshots["revisions/revision-events.jsonl"],
            "The revision-event ledger",
        ),
        contract,
        expected_revision_events,
    )
    reviewers.update(revision_event_reviewers)
    if len(reviewers) != 1:
        raise HumanAdjudicationAuditError(
            "The single-reviewer contract has inconsistent reviewer identities."
        )
    single_reviewer = next(iter(reviewers))
    active_state_sha256 = _active_workspace_state_hash(
        batch_bindings, groups, current_attestation_hashes
    )
    workspace_event_count = _validate_workspace_events(
        _snapshot_records(
            snapshots["workspace-events.jsonl"], "The workspace-event ledger"
        ),
        contract,
        manifest,
        revision_events_by_hash,
        attestation_bindings,
        active_state_sha256,
        single_reviewer,
    )

    _finish_closure(
        contract,
        source_inventory,
        workspace,
        workspace_initial,
        directory_map,
        snapshots,
    )
    return {
        "status": "workspace_structural_audit_passed",
        "audit_scope": "formal_private_workspace_structure_only",
        "workspace": workspace.relative_to(root).as_posix(),
        "formal_workspace": True,
        "human_review_complete": True,
        "semantic_items": len(semantic_items),
        "semantic_batches": batch_count,
        "route_items": len(route_items),
        "route_typed_memberships": len(route_memberships),
        "mapping_groups": len(groups),
        "registered_evidence_items": len(registry),
        "reviewer_count": 1,
        "revision_events": len(expected_revision_events),
        "workspace_events": workspace_event_count,
        "checks": {"passed": 12, "failed": 0},
        "clinical_correctness_assessed": False,
        "final_compiled_artifact_audit_implemented": True,
        "final_compiled_artifact_audited": False,
        "eligible_for_audited_unfrozen_state": False,
        "eligible_for_separate_freeze": False,
        "audit_artifact_written": False,
        "database_connected": False,
        "external_api_called": False,
        "llm_called": False,
    }


def _validate_final_contract(contract: Mapping[str, Any]) -> None:
    config = contract["config"]
    final = config.get("final_outputs")
    if not isinstance(final, Mapping):
        raise HumanAdjudicationAuditError("The final-output contract is absent.")
    exact_values = {
        "component_id": COMPONENT_ID,
        "artifact_parent": FINAL_ARTIFACT_PARENT.as_posix(),
        "artifact_directory_naming": "strict-utc-basic-with-fraction-v1",
        "private_directory_mode": "0700",
        "private_file_mode": "0600",
        "strict_inventory": list(PRE_AUDIT_OUTPUTS),
        "strict_inventory_after_audit": [
            *PRE_AUDIT_OUTPUTS,
            FINAL_AUDIT_FILE,
        ],
        "strict_inventory_after_freeze": [
            *PRE_AUDIT_OUTPUTS,
            FINAL_AUDIT_FILE,
            FINAL_FREEZE_FILE,
        ],
        "independent_audit_adds_only": FINAL_AUDIT_FILE,
        "separate_freeze_adds_only": FINAL_FREEZE_FILE,
        "gzip_encoding": FINAL_GZIP_ENCODING,
        "semantic_ledger_schema": SEMANTIC_SCHEMA,
        "semantic_decision_hash_version": SEMANTIC_HASH_VERSION,
        "semantic_key_set_hash_version": "source-field-nonnull-exact-value-set-v1",
        "mapping_group_schema": GROUP_SCHEMA,
        "mapping_group_hash_version": GROUP_HASH_VERSION,
        "route_mapping_schema": ROUTE_SCHEMA,
        "route_mapping_hash_version": ROUTE_HASH_VERSION,
        "route_mapping_total_typed_memberships": config["source_artifact"][
            "route_template"
        ]["source_specific_typed_memberships"],
        "attestation_schema": ATTESTATION_SCHEMA,
        "attestation_hash_version": ATTESTATION_SCHEMA,
        "evidence_registry_schema": EVIDENCE_SCHEMA,
        "evidence_registry_hash_version": EVIDENCE_SCHEMA,
        "manifest_schema": FINAL_MANIFEST_SCHEMA,
        "aggregate_summary_schema": AGGREGATE_SUMMARY_SCHEMA,
        "audit_schema": FINAL_AUDIT_SCHEMA,
        "audit_method": FINAL_AUDIT_METHOD,
        "auditor_component_id": FINAL_AUDITOR_COMPONENT_ID,
        "freeze_schema": "query202-human-adjudication-freeze-manifest-v1",
        "workspace_snapshot_hash_version": WORKSPACE_SNAPSHOT_VERSION,
        "registered_document_set_hash_version": (REGISTERED_DOCUMENT_SET_VERSION),
        "retained_versioned_documents_location": "formal_workspace",
        "final_artifact_self_contained": False,
        "manifest_status_before_freeze": "human_review_complete_unfrozen",
        "audit_status_required_before_freeze": "passed",
        "audit_checks_total": 18,
        "freeze_manifest_status": "frozen",
        "final_artifact_review_complete_guards_true": [
            "semantic_review_complete",
            "route_review_complete",
        ],
        "final_freeze_guards_true": [
            "reviewed_semantic_ledger_frozen",
            "route_mapping_frozen",
        ],
        "downstream_scientific_guards_remain_false": list(
            FINAL_DOWNSTREAM_FALSE_GUARDS
        ),
    }
    if (
        type(final.get("audit_checks_total")) is not int
        or any(final.get(key) != value for key, value in exact_values.items())
    ):
        raise HumanAdjudicationAuditError("The final-output contract changed.")
    required_true = (
        "semantic_ledger_includes_exact_source_field_and_raw_value",
        "semantic_key_set_must_equal_source",
        "semantic_active_revision_projection_required",
        "route_mapping_expands_canonical_to_233_nonnull_memberships",
        "route_mapping_adds_3_sql_null_missing_memberships",
        "route_mapping_preserves_source_key_field_role_frequency_and_provenance",
        "independent_audit_must_reopen_retained_documents",
        "freeze_must_reopen_retained_documents",
        "freeze_manifest_binds_all_private_whole_file_hashes",
        "freeze_manifest_binds_semantic_and_route_decision_hashes",
        "freeze_manifest_binds_source_ndc_config_generator_auditor_and_audit_hashes",
    )
    if set(final) != set(exact_values) | set(required_true):
        raise HumanAdjudicationAuditError("The final-output schema changed.")
    if any(final.get(key) is not True for key in required_true):
        raise HumanAdjudicationAuditError("A final-output closure rule is disabled.")
    implementation = config["implementation"]
    generator_paths = implementation.get("generator_paths")
    if (
        not isinstance(generator_paths, list)
        or tuple(generator_paths[-len(FINALIZER_GENERATOR_PATHS) :])
        != FINALIZER_GENERATOR_PATHS
    ):
        raise HumanAdjudicationAuditError(
            "The compiler and freezer are outside the frozen generator bundle."
        )


def _snapshot_flat_artifact(
    root: Path,
    artifact: Path,
    expected: set[str],
    *,
    retain_payload: bool,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    directory = _snapshot_directory(artifact, "The compiled final artifact", root=root)
    if directory["mode"] != 0o700 or set(directory["entries"]) != expected:
        raise HumanAdjudicationAuditError(
            "The compiled final-artifact inventory or directory mode is invalid."
        )
    snapshots: dict[str, dict[str, Any]] = {}
    for name in sorted(expected):
        if Path(name).name != name:
            raise HumanAdjudicationAuditError(
                "The compiled final-artifact filename inventory is unsafe."
            )
        snapshot = _snapshot_file(
            artifact / name,
            "A compiled final-artifact file",
            retain_payload=retain_payload,
            root=root,
        )
        if snapshot["mode"] != 0o600 or snapshot["nlink"] != 1:
            raise HumanAdjudicationAuditError(
                "A compiled final-artifact file has an unsafe mode or link count."
            )
        snapshots[name] = snapshot
    return directory, snapshots


def _artifact_gzip_records(
    snapshot: Mapping[str, Any], label: str
) -> tuple[bytes, list[Mapping[str, Any]]]:
    stored = snapshot.get("payload")
    if not isinstance(stored, bytes) or not stored.startswith(
        b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff"
    ):
        raise HumanAdjudicationAuditError(
            f"{label} is not the contracted deterministic gzip encoding."
        )
    raw = _one_gzip(stored, label)
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    deterministic = (
        b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff"
        + compressor.compress(raw)
        + compressor.flush()
        + struct.pack("<II", zlib.crc32(raw) & 0xFFFFFFFF, len(raw) & 0xFFFFFFFF)
    )
    if stored != deterministic:
        raise HumanAdjudicationAuditError(
            f"{label} is not the deterministic single-member encoding."
        )
    return raw, _read_ndjson(raw, label)


def _framed_projection(
    begin: Mapping[str, Any],
    body: Sequence[Mapping[str, Any]],
    end_type: str,
    hash_version: str,
) -> tuple[list[Mapping[str, Any]], str]:
    sequence_sha256 = _sequence_hash(hash_version, body)
    return [
        dict(begin),
        *body,
        {
            "record_type": end_type,
            "records": len(body),
            "sequence_hash_version": hash_version,
            "sequence_sha256": sequence_sha256,
        },
    ], sequence_sha256


def _active_projection(
    records: Sequence[Mapping[str, Any]], identifier_key: str
) -> dict[str, Mapping[str, Any]]:
    active: dict[str, Mapping[str, Any]] = {}
    revisions: dict[str, int] = {}
    for record in records[1:]:
        identifier = record.get(identifier_key)
        revision = record.get("revision")
        if not isinstance(identifier, str) or type(revision) is not int:
            raise HumanAdjudicationAuditError(
                "A structurally audited workspace ledger lost its identity."
            )
        prior = revisions.get(identifier)
        if prior is None or revision > prior:
            active[identifier] = record
            revisions[identifier] = revision
        elif revision == prior and record != active[identifier]:
            raise HumanAdjudicationAuditError(
                "A structurally audited workspace ledger became conflicting."
            )
    return active


def _workspace_projection_for_final(
    root: Path,
    workspace_relative: Path,
    declared_files: object,
    batch_count: int,
) -> dict[str, Any]:
    workspace = _project_path(
        root, workspace_relative.as_posix(), "The compiled artifact workspace"
    )
    if not isinstance(declared_files, list):
        raise HumanAdjudicationAuditError(
            "The compiled artifact lacks its workspace file closure."
        )
    declared: dict[str, Mapping[str, Any]] = {}
    previous: str | None = None
    for raw_item in declared_files:
        item = _exact_keys(
            raw_item,
            {"file", "sha256", "bytes", "mode", "nlink"},
            "workspace file binding",
        )
        relative = _safe_relative(item["file"], "workspace file binding").as_posix()
        if (
            relative in declared
            or (previous is not None and relative <= previous)
            or item["mode"] != "0600"
            or item["nlink"] != 1
            or not isinstance(item["sha256"], str)
            or SHA256_RE.fullmatch(item["sha256"]) is None
        ):
            raise HumanAdjudicationAuditError(
                "A compiled workspace file binding is invalid."
            )
        _positive_int(item["bytes"], "workspace file byte count", allow_zero=True)
        declared[relative] = item
        previous = relative
    actual_files, directories = _walk_workspace(workspace, root=root)
    if actual_files != set(declared):
        raise HumanAdjudicationAuditError(
            "The compiled artifact workspace inventory is stale."
        )
    directory_snapshot = _snapshot_directory(
        workspace, "The compiled artifact workspace", root=root
    )
    directory_snapshots = {
        path.relative_to(workspace).as_posix(): _snapshot_directory(
            path, "A compiled artifact workspace directory", root=root
        )
        for path in directories
    }
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
        set(directory_snapshots) != expected_directories
        or directory_snapshot["mode"] != 0o700
        or any(value["mode"] != 0o700 for value in directory_snapshots.values())
    ):
        raise HumanAdjudicationAuditError(
            "The compiled artifact workspace is no longer private."
        )
    needed: set[str] = {
        "semantic-groups/mapping-groups.jsonl",
        "route-source/route-source-batch-0001.jsonl",
        "route-decisions/route-decisions-batch-0001.jsonl",
        "evidence-registry/evidence-registry.jsonl",
        "attestations/batch-attestations.jsonl",
    }
    for index in range(1, batch_count + 1):
        needed.add(f"semantic-source/semantic-source-batch-{index:04d}.jsonl")
        needed.add(f"semantic-decisions/semantic-decisions-batch-{index:04d}.jsonl")
    if not needed.issubset(declared):
        raise HumanAdjudicationAuditError(
            "The compiled artifact workspace lacks a projection input."
        )
    snapshots: dict[str, dict[str, Any]] = {}
    for relative, item in declared.items():
        snapshot = _snapshot_file(
            workspace / relative,
            "A compiled artifact workspace file",
            retain_payload=relative in needed,
            root=root,
        )
        if (
            snapshot["mode"] != 0o600
            or snapshot["nlink"] != 1
            or snapshot["sha256"] != item["sha256"]
            or snapshot["bytes"] != item["bytes"]
        ):
            raise HumanAdjudicationAuditError(
                "A compiled artifact workspace file binding is stale."
            )
        snapshots[relative] = snapshot

    semantic_source: list[Mapping[str, Any]] = []
    semantic_active: dict[str, Mapping[str, Any]] = {}
    for index in range(1, batch_count + 1):
        source_name = f"semantic-source/semantic-source-batch-{index:04d}.jsonl"
        decision_name = f"semantic-decisions/semantic-decisions-batch-{index:04d}.jsonl"
        source_records = _snapshot_records(
            snapshots[source_name], "A semantic workspace source batch"
        )
        semantic_source.extend(source_records[1:-1])
        active = _active_projection(
            _snapshot_records(
                snapshots[decision_name], "A semantic workspace decision ledger"
            ),
            "review_id",
        )
        if set(active).intersection(semantic_active):
            raise HumanAdjudicationAuditError(
                "Semantic projection identities overlap across batches."
            )
        semantic_active.update(active)
    group_records = _snapshot_records(
        snapshots["semantic-groups/mapping-groups.jsonl"],
        "The mapping-group workspace ledger",
    )
    route_source = _snapshot_records(
        snapshots["route-source/route-source-batch-0001.jsonl"],
        "The route workspace source batch",
    )
    route_decisions = _snapshot_records(
        snapshots["route-decisions/route-decisions-batch-0001.jsonl"],
        "The route workspace decision ledger",
    )
    projection = {
        "workspace": workspace,
        "directory_snapshot": directory_snapshot,
        "directory_snapshots": directory_snapshots,
        "snapshots": snapshots,
        "semantic_source": semantic_source,
        "semantic_active": semantic_active,
        "groups": _active_projection(group_records, "mapping_group_id"),
        "route_items": [
            record
            for record in route_source[1:-1]
            if record.get("record_type") == "route_source_item"
        ],
        "route_memberships": [
            record
            for record in route_source[1:-1]
            if record.get("record_type") == "route_source_membership"
        ],
        "route_active": _active_projection(route_decisions, "review_id"),
        "evidence": _snapshot_records(
            snapshots["evidence-registry/evidence-registry.jsonl"],
            "The workspace evidence registry",
        ),
        "attestations": _snapshot_records(
            snapshots["attestations/batch-attestations.jsonl"],
            "The workspace attestation ledger",
        ),
        "workspace_snapshot_sha256": _sequence_hash(
            WORKSPACE_SNAPSHOT_VERSION,
            [dict(declared[relative]) for relative in sorted(declared)],
        ),
    }
    document_bindings = [
        dict(declared[relative])
        for relative in sorted(declared)
        if relative.startswith("evidence-registry/documents/")
    ]
    projection["registered_document_count"] = len(document_bindings)
    projection["registered_document_set_sha256"] = _sequence_hash(
        REGISTERED_DOCUMENT_SET_VERSION, document_bindings
    )
    return projection


def _expected_compiled_outputs(
    projection: Mapping[str, Any],
    contract: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    config = contract["config"]
    source = config["source_artifact"]
    config_sha256 = contract["config_sha256"]

    semantic_body: list[Mapping[str, Any]] = []
    for source_item in projection["semantic_source"]:
        review_id = source_item["review_id"]
        revision = projection["semantic_active"].get(review_id)
        if not isinstance(revision, Mapping):
            raise HumanAdjudicationAuditError(
                "A compiled semantic source item lacks its active revision."
            )
        semantic_body.append(
            {
                "record_type": "reviewed_semantic_decision",
                "review_id": review_id,
                "source_field": source_item["source_field"],
                "exact_raw_value": source_item["exact_raw_value"],
                "exact_row_count": source_item["exact_row_count"],
                "active_revision_sha256": _record_sha(revision),
                "active_revision": revision,
            }
        )
    if len(semantic_body) != len(projection["semantic_active"]):
        raise HumanAdjudicationAuditError(
            "The compiled semantic projection does not conserve active decisions."
        )
    semantic_records, semantic_hash = _framed_projection(
        {
            "record_type": "reviewed_semantic_ledger_begin",
            "schema_version": 1,
            "component_id": COMPONENT_ID,
            "schema": SEMANTIC_SCHEMA,
            "config_sha256": config_sha256,
            "semantic_key_set_sha256": source["semantic_template"][
                "semantic_key_set_sha256"
            ],
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
            "active_revision_sha256": _record_sha(revision),
            "active_revision": revision,
        }
        for group_id, revision in sorted(projection["groups"].items())
    ]
    group_records, group_hash = _framed_projection(
        {
            "record_type": "semantic_mapping_groups_begin",
            "schema_version": 1,
            "component_id": COMPONENT_ID,
            "schema": GROUP_SCHEMA,
            "config_sha256": config_sha256,
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
            route_body.append(
                {
                    **common,
                    "decision": None,
                    "route_state": "missing",
                    "sets_has_unknown": False,
                    "decision_provenance": "forced_sql_null_policy",
                    "review_status": "not_required",
                    "active_revision_sha256": None,
                    "active_revision": None,
                }
            )
            continue
        review_id = membership["canonical_review_id"]
        revision = projection["route_active"].get(review_id)
        if not isinstance(revision, Mapping):
            raise HumanAdjudicationAuditError(
                "A compiled nonnull route membership lacks its active decision."
            )
        used_route_ids.add(review_id)
        decision = revision["decision"]
        route_body.append(
            {
                **common,
                "decision": decision,
                "route_state": decision,
                "sets_has_unknown": decision == "unknown",
                "decision_provenance": "human_canonical_exact_route_review",
                "review_status": "reviewed",
                "active_revision_sha256": _record_sha(revision),
                "active_revision": revision,
            }
        )
    if used_route_ids != set(projection["route_active"]):
        raise HumanAdjudicationAuditError(
            "The compiled route projection does not conserve active decisions."
        )
    route_records, route_hash = _framed_projection(
        {
            "record_type": "source_specific_route_mapping_begin",
            "schema_version": 1,
            "component_id": COMPONENT_ID,
            "schema": ROUTE_SCHEMA,
            "config_sha256": config_sha256,
            "canonical_route_items": len(projection["route_active"]),
            "nonnull_memberships": sum(
                item["raw_value_state"] == "nonnull" for item in route_body
            ),
            "sql_null_memberships": sum(
                item["raw_value_state"] == "sql_null" for item in route_body
            ),
            "typed_memberships": len(route_body),
        },
        route_body,
        "source_specific_route_mapping_end",
        ROUTE_HASH_VERSION,
    )

    source_attestations = projection["attestations"]
    if not source_attestations:
        raise HumanAdjudicationAuditError(
            "The compiled workspace has no attestation source ledger."
        )
    attestation_body = [dict(record) for record in source_attestations[1:]]
    attestation_records, attestation_hash = _framed_projection(
        {
            "record_type": "human_attestations_begin",
            "schema_version": 1,
            "component_id": COMPONENT_ID,
            "schema": ATTESTATION_SCHEMA,
            "config_sha256": config_sha256,
            "source_ledger_header": source_attestations[0],
            "attestation_records": len(attestation_body),
        },
        attestation_body,
        "human_attestations_end",
        ATTESTATION_SCHEMA,
    )

    source_evidence = projection["evidence"]
    if not source_evidence:
        raise HumanAdjudicationAuditError(
            "The compiled workspace has no evidence source registry."
        )
    evidence_body = [dict(record) for record in source_evidence[1:]]
    evidence_records, evidence_hash = _framed_projection(
        {
            "record_type": "evidence_registry_begin",
            "schema_version": 1,
            "component_id": COMPONENT_ID,
            "schema": EVIDENCE_SCHEMA,
            "config_sha256": config_sha256,
            "source_registry_header": source_evidence[0],
            "evidence_records": len(evidence_body),
        },
        evidence_body,
        "evidence_registry_end",
        EVIDENCE_SCHEMA,
    )

    semantic_statuses = {
        dimension: dict(
            Counter(
                item["active_revision"]["dimensions"][dimension]["status"]
                for item in semantic_body
            )
        )
        for dimension in SEMANTIC_DIMENSIONS
    }
    route_states = dict(Counter(item["route_state"] for item in route_body))
    namespaces = dict(Counter(item["namespace"] for item in evidence_body))
    decision_hashes = {
        "semantic_hash_version": SEMANTIC_HASH_VERSION,
        "semantic_sha256": semantic_hash,
        "mapping_group_hash_version": GROUP_HASH_VERSION,
        "mapping_group_sha256": group_hash,
        "route_hash_version": ROUTE_HASH_VERSION,
        "route_sha256": route_hash,
        "attestation_sha256": attestation_hash,
        "evidence_registry_sha256": evidence_hash,
    }
    summary = {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "artifact_type": "potassium_query202_private_human_adjudication_summary",
        "aggregate_summary_schema": AGGREGATE_SUMMARY_SCHEMA,
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
        "decision_hashes": decision_hashes,
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
        "workspace_lineage": {
            "directory": projection["workspace"]
            .relative_to(contract["root"])
            .as_posix(),
            "self_contained": False,
            "snapshot_hash_version": WORKSPACE_SNAPSHOT_VERSION,
            "snapshot_sha256": projection["workspace_snapshot_sha256"],
            "registered_document_set_hash_version": (REGISTERED_DOCUMENT_SET_VERSION),
            "registered_document_set_sha256": projection[
                "registered_document_set_sha256"
            ],
            "registered_document_count": projection["registered_document_count"],
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
        "decision_hashes": decision_hashes,
    }


def _workspace_inventory_records(
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


def _expected_final_manifest(
    root: Path,
    artifact_relative: Path,
    projection: Mapping[str, Any],
    contract: Mapping[str, Any],
    output_metadata: Mapping[str, Mapping[str, Any]],
    summary_metadata: Mapping[str, Any],
    decision_hashes: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    config = contract["config"]
    source = config["source_artifact"]
    workspace_inventory = _workspace_inventory_records(projection["snapshots"])
    workspace_snapshot_sha256 = _sequence_hash(
        WORKSPACE_SNAPSHOT_VERSION, workspace_inventory
    )
    document_inventory = [
        item
        for item in workspace_inventory
        if item["file"].startswith("evidence-registry/documents/")
    ]
    document_set_sha256 = _sequence_hash(
        REGISTERED_DOCUMENT_SET_VERSION, document_inventory
    )
    if (
        workspace_snapshot_sha256 != projection["workspace_snapshot_sha256"]
        or document_set_sha256 != projection["registered_document_set_sha256"]
        or len(document_inventory) != projection["registered_document_count"]
    ):
        raise HumanAdjudicationAuditError(
            "The retained workspace inventory changed during final projection."
        )
    return {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "artifact_type": "potassium_query202_private_human_adjudication",
        "manifest_schema": FINAL_MANIFEST_SCHEMA,
        "status": "human_review_complete_unfrozen",
        "created_at_utc": created_at,
        "artifact_directory": artifact_relative.as_posix(),
        "workspace": {
            "directory": projection["workspace"].relative_to(root).as_posix(),
            "validated_status": "human_review_complete_unfrozen",
            "self_contained": False,
            "registered_documents_retained_in_workspace": True,
            "snapshot_hash_version": WORKSPACE_SNAPSHOT_VERSION,
            "snapshot_sha256": workspace_snapshot_sha256,
            "registered_document_set_hash_version": (REGISTERED_DOCUMENT_SET_VERSION),
            "registered_document_set_sha256": document_set_sha256,
            "registered_document_count": len(document_inventory),
            "files": workspace_inventory,
        },
        "component_lineage": {
            "config": contract["path"].relative_to(root).as_posix(),
            "config_sha256": contract["config_sha256"],
            "rule_version": config["rule_version"],
            "generator_bundle_sha256": contract["generator_bundle"]["sha256"],
            "auditor_bundle_sha256": contract["auditor_bundle"]["sha256"],
        },
        "source_lineage": {
            "component_id": source["component_id"],
            "artifact_directory": source["directory"],
            "source_config_sha256": source["source_config_sha256"],
            "manifest_sha256": source["manifest_sha256"],
            "aggregate_summary_sha256": source["aggregate_summary_sha256"],
            "audit_sha256": source["audit_sha256"],
            "semantic_template_stored_sha256": source["semantic_template"][
                "stored_sha256"
            ],
            "semantic_template_raw_sha256": source["semantic_template"]["raw_sha256"],
            "semantic_key_set_sha256": source["semantic_template"][
                "semantic_key_set_sha256"
            ],
            "route_template_stored_sha256": source["route_template"]["stored_sha256"],
            "route_template_raw_sha256": source["route_template"]["raw_sha256"],
            "local_evidence_stored_sha256": source["local_evidence"]["stored_sha256"],
            "local_evidence_raw_sha256": source["local_evidence"]["raw_sha256"],
            "ndc_decision_config_sha256": config["ndc_decision"]["config_sha256"],
            "ndc_validator_bundle_sha256": config["ndc_decision"][
                "validator_bundle_sha256"
            ],
        },
        "outputs": {
            **{name: dict(output_metadata[name]) for name in GZIP_OUTPUTS},
            "aggregate-summary.json": dict(summary_metadata),
        },
        "decision_hashes": dict(decision_hashes),
        "conservation": {
            "semantic_items": source["semantic_template"]["semantic_keys"],
            "mapping_groups": len(projection["groups"]),
            "canonical_route_items": source["route_template"][
                "canonical_exact_nonnull_values"
            ],
            "route_nonnull_memberships": source["route_template"][
                "source_specific_nonnull_memberships"
            ],
            "route_sql_null_memberships": source["route_template"][
                "source_specific_sql_null_memberships"
            ],
            "route_typed_memberships": source["route_template"][
                "source_specific_typed_memberships"
            ],
        },
        "guards": {
            "semantic_review_complete": True,
            "route_review_complete": True,
            "reviewed_semantic_ledger_frozen": False,
            "route_mapping_frozen": False,
            **{key: False for key in FINAL_DOWNSTREAM_FALSE_GUARDS},
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


def _finish_final_dependency_closure(
    contract: Mapping[str, Any],
    source_inventory: Mapping[str, Any],
    projection: Mapping[str, Any],
    artifact: Path,
    artifact_files: Mapping[str, Mapping[str, Any]],
    expected_artifact_names: set[str],
) -> None:
    final_source_directory = _snapshot_directory(
        source_inventory["directory"],
        "The source artifact directory",
        root=contract["root"],
    )
    if _directory_seal(final_source_directory) != _directory_seal(
        source_inventory["directory_snapshot"]
    ):
        raise HumanAdjudicationAuditError(
            "The source inventory changed during final-artifact audit."
        )
    for initial in source_inventory["snapshots"].values():
        final = _snapshot_file(
            initial["path"], "A source closure file", root=contract["root"]
        )
        if _file_seal(final) != _file_seal(initial):
            raise HumanAdjudicationAuditError(
                "A source file changed during final-artifact audit."
            )
    final_config = _snapshot_file(
        contract["path"], "The final-audit config", root=contract["root"]
    )
    if _file_seal(final_config) != _file_seal(contract["snapshot"]):
        raise HumanAdjudicationAuditError(
            "The config changed during final-artifact audit."
        )
    for bundle_name in ("generator_bundle", "auditor_bundle"):
        for initial in contract[bundle_name]["snapshots"].values():
            final = _snapshot_file(
                initial["path"],
                "An implementation closure file",
                root=contract["root"],
            )
            if _file_seal(final) != _file_seal(initial):
                raise HumanAdjudicationAuditError(
                    "An implementation file changed during final-artifact audit."
                )
    for initial in contract["test_attestation_snapshots"].values():
        final = _reopen_test_attestation_closure_file(contract["root"], initial)
        if _file_seal(final) != _file_seal(initial):
            raise HumanAdjudicationAuditError(
                "A synthetic-test attestation closure file changed during final-artifact audit."
            )

    workspace = projection["workspace"]
    final_workspace_files, final_directories = _walk_workspace(
        workspace, root=contract["root"]
    )
    if final_workspace_files != set(projection["snapshots"]):
        raise HumanAdjudicationAuditError(
            "The retained workspace inventory changed during final-artifact audit."
        )
    final_directory_map = {
        path.relative_to(workspace).as_posix(): _snapshot_directory(
            path, "A retained workspace directory", root=contract["root"]
        )
        for path in final_directories
    }
    if set(final_directory_map) != set(projection["directory_snapshots"]):
        raise HumanAdjudicationAuditError(
            "The retained workspace directory inventory changed."
        )
    for relative, initial in projection["directory_snapshots"].items():
        if _directory_seal(final_directory_map[relative]) != _directory_seal(initial):
            raise HumanAdjudicationAuditError(
                "A retained workspace directory changed during final-artifact audit."
            )
    for relative, initial in projection["snapshots"].items():
        final = _snapshot_file(
            workspace / relative,
            "A retained workspace closure file",
            root=contract["root"],
        )
        if _file_seal(final) != _file_seal(initial):
            raise HumanAdjudicationAuditError(
                "A retained workspace file changed during final-artifact audit."
            )

    _, final_artifact_files = _snapshot_flat_artifact(
        contract["root"],
        artifact,
        expected_artifact_names,
        retain_payload=False,
    )
    if set(final_artifact_files) != set(artifact_files):
        raise HumanAdjudicationAuditError(
            "The compiled final-artifact file inventory changed."
        )
    for name, initial in artifact_files.items():
        if _file_seal(final_artifact_files[name]) != _file_seal(initial):
            raise HumanAdjudicationAuditError(
                "A compiled final-artifact file changed during audit."
            )


def _snapshot_regular_at(
    directory_descriptor: int, name: str, label: str
) -> dict[str, Any]:
    descriptor: int | None = None
    digest = hashlib.sha256()
    total = 0
    try:
        initial = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
        if not stat.S_ISREG(initial.st_mode):
            raise HumanAdjudicationAuditError(f"{label} is not a regular file.")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(name, flags, dir_fd=directory_descriptor)
        before = os.fstat(descriptor)
        if not _same_stat(initial, before):
            raise HumanAdjudicationAuditError(f"{label} changed before read.")
        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
        after = os.fstat(descriptor)
        final = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    except HumanAdjudicationAuditError:
        raise
    except OSError:
        raise HumanAdjudicationAuditError(
            f"{label} could not be snapshotted safely."
        ) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        not _same_stat(before, after)
        or not _same_stat(after, final)
        or total != after.st_size
    ):
        raise HumanAdjudicationAuditError(f"{label} changed during read.")
    return {
        "identity": (after.st_dev, after.st_ino),
        "full_mode": after.st_mode,
        "mode": stat.S_IMODE(after.st_mode),
        "nlink": after.st_nlink,
        "bytes": total,
        "mtime_ns": after.st_mtime_ns,
        "ctime_ns": after.st_ctime_ns,
        "sha256": digest.hexdigest(),
    }


def _unlink_if_identity_at(
    directory_descriptor: int, name: str, expected_identity: tuple[int, int]
) -> None:
    try:
        current = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (current.st_dev, current.st_ino) == expected_identity:
        os.unlink(name, dir_fd=directory_descriptor)


def _atomic_add_final_audit(
    root: Path,
    artifact: Path,
    payload: bytes,
    initial_directory: Mapping[str, Any],
    verify_published: Callable[[], None],
    failure_hook: Callable[[str], None] | None = None,
) -> None:
    parent_descriptor: int | None = None
    artifact_descriptor: int | None = None
    temporary_descriptor: int | None = None
    temporary_identity: tuple[int, int] | None = None
    temporary_name = f".tmp-query202-final-audit-{os.urandom(16).hex()}"
    published = False
    completed = False
    try:
        parent_descriptor, parent_stat, _ = _open_beneath(
            root, artifact.parent, "The final-artifact parent"
        )
        artifact_descriptor, artifact_stat, _ = _open_beneath(
            root, artifact, "The compiled final artifact"
        )
        if (
            not stat.S_ISDIR(parent_stat.st_mode)
            or not stat.S_ISDIR(artifact_stat.st_mode)
            or (artifact_stat.st_dev, artifact_stat.st_ino)
            != initial_directory["identity"]
            or artifact_stat.st_mode != initial_directory["full_mode"]
            or set(os.listdir(artifact_descriptor)) != set(PRE_AUDIT_OUTPUTS)
        ):
            raise HumanAdjudicationAuditError(
                "The compiled final artifact changed before audit publication."
            )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        temporary_descriptor = os.open(
            temporary_name, flags, 0o600, dir_fd=parent_descriptor
        )
        os.fchmod(temporary_descriptor, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(temporary_descriptor, view)
            if written <= 0:
                raise HumanAdjudicationAuditError(
                    "The private final-audit write made no progress."
                )
            view = view[written:]
        os.fsync(temporary_descriptor)
        temporary_stat = os.fstat(temporary_descriptor)
        if (
            not stat.S_ISREG(temporary_stat.st_mode)
            or stat.S_IMODE(temporary_stat.st_mode) != 0o600
            or temporary_stat.st_nlink != 1
            or temporary_stat.st_size != len(payload)
        ):
            raise HumanAdjudicationAuditError(
                "The private final-audit temporary file is unsafe."
            )
        os.close(temporary_descriptor)
        temporary_descriptor = None
        temporary_snapshot = _snapshot_regular_at(
            parent_descriptor,
            temporary_name,
            "The temporary independent audit",
        )
        temporary_identity = temporary_snapshot["identity"]
        if (
            temporary_snapshot["mode"] != 0o600
            or temporary_snapshot["nlink"] != 1
            or temporary_snapshot["sha256"] != hashlib.sha256(payload).hexdigest()
            or temporary_snapshot["bytes"] != len(payload)
        ):
            raise HumanAdjudicationAuditError(
                "The temporary independent audit failed anchored verification."
            )
        if failure_hook is not None:
            failure_hook("before_atomic_audit_publish")
        current_temporary = _snapshot_regular_at(
            parent_descriptor,
            temporary_name,
            "The temporary independent audit",
        )
        if (
            current_temporary["identity"] != temporary_identity
            or current_temporary["full_mode"] != temporary_snapshot["full_mode"]
            or current_temporary["nlink"] != 1
            or current_temporary["sha256"] != temporary_snapshot["sha256"]
            or current_temporary["bytes"] != temporary_snapshot["bytes"]
        ):
            raise HumanAdjudicationAuditError(
                "The temporary independent audit changed before publication."
            )
        try:
            os.stat(
                FINAL_AUDIT_FILE,
                dir_fd=artifact_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise HumanAdjudicationAuditError(
                "The compiled artifact already has an audit file."
            )
        os.link(
            temporary_name,
            FINAL_AUDIT_FILE,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=artifact_descriptor,
            follow_symlinks=False,
        )
        published = True
        linked_snapshot = _snapshot_regular_at(
            artifact_descriptor,
            FINAL_AUDIT_FILE,
            "The atomically linked independent audit",
        )
        if (
            linked_snapshot["identity"] != temporary_identity
            or linked_snapshot["mode"] != 0o600
            or linked_snapshot["nlink"] != 2
            or linked_snapshot["sha256"] != temporary_snapshot["sha256"]
            or linked_snapshot["bytes"] != temporary_snapshot["bytes"]
        ):
            raise HumanAdjudicationAuditError(
                "The atomically linked independent audit changed during publication."
            )
        os.fsync(artifact_descriptor)
        _unlink_if_identity_at(parent_descriptor, temporary_name, temporary_identity)
        try:
            os.stat(
                temporary_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise HumanAdjudicationAuditError(
                "The temporary audit leaf was replaced during publication."
            )
        os.fsync(parent_descriptor)
        if failure_hook is not None:
            failure_hook("after_atomic_audit_publish")
        verify_published()
        completed = True
    except HumanAdjudicationAuditError:
        raise
    except OSError:
        raise HumanAdjudicationAuditError(
            "The independent final audit could not be published atomically."
        ) from None
    finally:
        if temporary_descriptor is not None:
            os.close(temporary_descriptor)
        if (
            published
            and not completed
            and artifact_descriptor is not None
            and temporary_identity is not None
        ):
            try:
                _unlink_if_identity_at(
                    artifact_descriptor,
                    FINAL_AUDIT_FILE,
                    temporary_identity,
                )
                os.fsync(artifact_descriptor)
            except OSError:
                pass
        if parent_descriptor is not None:
            try:
                if temporary_identity is not None:
                    _unlink_if_identity_at(
                        parent_descriptor,
                        temporary_name,
                        temporary_identity,
                    )
            except OSError:
                pass
            os.close(parent_descriptor)
        if artifact_descriptor is not None:
            os.close(artifact_descriptor)


def audit_compiled_human_adjudication_artifact(
    root: Path,
    artifact_directory: Path,
    config_path: Path = CONFIG_PATH,
    *,
    audited_at_utc: str | None = None,
    _failure_hook: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Audit seven compiled outputs and atomically add ``audit-summary.json``.

    This is the independent final-artifact audit used by the separate freeze.
    It is distinct from :func:`audit_human_adjudication_workspace`, reopens the
    retained formal workspace and registered private documents, and emits only
    aggregate metadata.  It never evaluates clinical correctness.
    """

    try:
        root = root.resolve(strict=True)
    except OSError:
        raise HumanAdjudicationAuditError("The project root is unavailable.") from None
    contract = _load_contract(root, config_path)
    _validate_final_contract(contract)
    source_inventory = _source_inventory(root, contract)
    source = contract["config"]["source_artifact"]
    semantic_items = _parse_semantic_template(
        _stream_records(
            source_inventory["snapshots"]["semantic"],
            source["semantic_template"],
            "The semantic source stream",
        ),
        source["semantic_template"],
    )
    route_items, route_memberships = _parse_route_template(
        _stream_records(
            source_inventory["snapshots"]["route"],
            source["route_template"],
            "The route source stream",
        ),
        source["route_template"],
    )

    artifact_relative = _safe_relative(
        artifact_directory.as_posix(), "compiled final artifact"
    )
    parent_parts = FINAL_ARTIFACT_PARENT.parts
    if (
        artifact_relative.parts[: len(parent_parts)] != parent_parts
        or len(artifact_relative.parts) != len(parent_parts) + 1
        or FINAL_DIRECTORY_RE.fullmatch(artifact_relative.name) is None
    ):
        raise HumanAdjudicationAuditError(
            "The compiled final artifact is outside its contracted parent."
        )
    artifact = _project_path(
        root, artifact_relative.as_posix(), "compiled final artifact"
    )
    if not _git_ignored(root, artifact):
        raise HumanAdjudicationAuditError(
            "The compiled final artifact is not Git-ignored."
        )
    artifact_directory_snapshot, artifact_snapshots = _snapshot_flat_artifact(
        root,
        artifact,
        set(PRE_AUDIT_OUTPUTS),
        retain_payload=True,
    )
    manifest = _read_json(
        artifact_snapshots["manifest.json"], "The compiled artifact manifest"
    )
    if (
        manifest.get("component_id") != COMPONENT_ID
        or manifest.get("artifact_type")
        != "potassium_query202_private_human_adjudication"
        or manifest.get("manifest_schema") != FINAL_MANIFEST_SCHEMA
        or manifest.get("status") != "human_review_complete_unfrozen"
        or manifest.get("artifact_directory") != artifact_relative.as_posix()
        or not _strict_utc(manifest.get("created_at_utc"))
    ):
        raise HumanAdjudicationAuditError(
            "The compiled final-artifact lifecycle declaration is invalid."
        )
    workspace_lineage = manifest.get("workspace")
    if not isinstance(workspace_lineage, Mapping):
        raise HumanAdjudicationAuditError(
            "The compiled artifact lacks retained-workspace lineage."
        )
    workspace_relative = _safe_relative(
        workspace_lineage.get("directory"), "retained formal workspace"
    )
    structural_report = audit_human_adjudication_workspace(
        root, workspace_relative, config_path=config_path
    )
    if (
        structural_report.get("status") != "workspace_structural_audit_passed"
        or structural_report.get("human_review_complete") is not True
        or structural_report.get("final_compiled_artifact_audit_implemented")
        is not True
        or structural_report.get("final_compiled_artifact_audited") is not False
    ):
        raise HumanAdjudicationAuditError(
            "The retained formal workspace did not pass its separate structural audit."
        )
    projection = _workspace_projection_for_final(
        root,
        workspace_relative,
        workspace_lineage.get("files"),
        contract["config"]["workspace"]["semantic_batch_count"],
    )
    if (
        projection["semantic_source"] != semantic_items
        or projection["route_items"] != route_items
        or projection["route_memberships"] != route_memberships
    ):
        raise HumanAdjudicationAuditError(
            "The retained workspace no longer conserves the frozen source universe."
        )

    created_at = manifest["created_at_utc"]
    expected = _expected_compiled_outputs(projection, contract, created_at)
    output_metadata: dict[str, dict[str, Any]] = {}
    for name in GZIP_OUTPUTS:
        raw, records = _artifact_gzip_records(
            artifact_snapshots[name], "A compiled private NDJSON stream"
        )
        if records != expected["records"][name]:
            raise HumanAdjudicationAuditError(
                "A compiled private projection differs from its independent reconstruction."
            )
        output_metadata[name] = {
            "sha256": artifact_snapshots[name]["sha256"],
            "bytes": artifact_snapshots[name]["bytes"],
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_bytes": len(raw),
            "records": len(records),
            "encoding": FINAL_GZIP_ENCODING,
        }
    summary_snapshot = artifact_snapshots["aggregate-summary.json"]
    summary = _read_json(summary_snapshot, "The compiled aggregate summary")
    if summary != expected["summary"] or summary_snapshot.get(
        "payload"
    ) != _pretty_json(expected["summary"]):
        raise HumanAdjudicationAuditError(
            "The compiled aggregate summary differs from recomputed aggregates."
        )
    summary_metadata = {
        "sha256": summary_snapshot["sha256"],
        "bytes": summary_snapshot["bytes"],
    }
    expected_manifest = _expected_final_manifest(
        root,
        artifact_relative,
        projection,
        contract,
        output_metadata,
        summary_metadata,
        expected["decision_hashes"],
        created_at,
    )
    if manifest != expected_manifest or artifact_snapshots["manifest.json"].get(
        "payload"
    ) != _pretty_json(expected_manifest):
        raise HumanAdjudicationAuditError(
            "The compiled final-artifact manifest differs from independent reconstruction."
        )

    if _failure_hook is not None:
        _failure_hook("before_initial_final_closure")
    _finish_final_dependency_closure(
        contract,
        source_inventory,
        projection,
        artifact,
        artifact_snapshots,
        set(PRE_AUDIT_OUTPUTS),
    )
    audited_at = _audit_time(audited_at_utc)
    audited_files = {
        name: {
            "sha256": artifact_snapshots[name]["sha256"],
            "bytes": artifact_snapshots[name]["bytes"],
        }
        for name in PRE_AUDIT_OUTPUTS
    }
    audit_document = {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "auditor_component_id": FINAL_AUDITOR_COMPONENT_ID,
        "artifact_type": ("potassium_query202_private_human_adjudication_final_audit"),
        "audit_schema": FINAL_AUDIT_SCHEMA,
        "audit_method": FINAL_AUDIT_METHOD,
        "status": "passed",
        "audit_scope": "compiled_private_final_artifact",
        "audited_at_utc": audited_at,
        "artifact_directory": artifact_relative.as_posix(),
        "audited_files": audited_files,
        "manifest_sha256": artifact_snapshots["manifest.json"]["sha256"],
        "config_sha256": contract["config_sha256"],
        "source_manifest_sha256": source["manifest_sha256"],
        "ndc_decision_config_sha256": contract["config"]["ndc_decision"][
            "config_sha256"
        ],
        "generator_bundle_sha256": contract["generator_bundle"]["sha256"],
        "auditor_bundle_sha256": contract["auditor_bundle"]["sha256"],
        "workspace_snapshot_sha256": projection["workspace_snapshot_sha256"],
        "retained_workspace_documents": {
            "count": projection["registered_document_count"],
            "hash_version": REGISTERED_DOCUMENT_SET_VERSION,
            "aggregate_sha256": projection["registered_document_set_sha256"],
        },
        "decision_hashes": dict(expected["decision_hashes"]),
        "checks": {"total": 18, "passed": 18, "failed": 0},
        "claims": {
            "generator_helpers_imported": False,
            "clinical_correctness_established": False,
        },
    }
    payload = _pretty_json(audit_document)
    published_snapshot: dict[str, Any] = {}

    def verify_published() -> None:
        final_directory, final_files = _snapshot_flat_artifact(
            root,
            artifact,
            set(PRE_AUDIT_OUTPUTS) | {FINAL_AUDIT_FILE},
            retain_payload=True,
        )
        if (
            final_directory["identity"] != artifact_directory_snapshot["identity"]
            or final_directory["full_mode"] != artifact_directory_snapshot["full_mode"]
        ):
            raise HumanAdjudicationAuditError(
                "The final-artifact directory identity changed during publication."
            )
        for name in PRE_AUDIT_OUTPUTS:
            if _file_seal(final_files[name]) != _file_seal(artifact_snapshots[name]):
                raise HumanAdjudicationAuditError(
                    "A compiled output changed during audit publication."
                )
        final_audit = final_files[FINAL_AUDIT_FILE]
        if (
            final_audit["payload"] != payload
            or final_audit["sha256"] != hashlib.sha256(payload).hexdigest()
            or final_audit["mode"] != 0o600
        ):
            raise HumanAdjudicationAuditError(
                "The published independent audit differs from its verified payload."
            )
        _finish_final_dependency_closure(
            contract,
            source_inventory,
            projection,
            artifact,
            final_files,
            set(PRE_AUDIT_OUTPUTS) | {FINAL_AUDIT_FILE},
        )
        published_snapshot.update(final_audit)

    _atomic_add_final_audit(
        root,
        artifact,
        payload,
        artifact_directory_snapshot,
        verify_published,
        _failure_hook,
    )
    if not published_snapshot:
        raise HumanAdjudicationAuditError(
            "The independent final audit publication was not verified."
        )
    return {
        "status": "passed",
        "audit_scope": "compiled_private_final_artifact",
        "artifact": artifact_relative.as_posix(),
        "audit_file": (artifact_relative / FINAL_AUDIT_FILE).as_posix(),
        "audit_sha256": published_snapshot["sha256"],
        "audited_files": len(PRE_AUDIT_OUTPUTS),
        "semantic_items": len(semantic_items),
        "mapping_groups": len(projection["groups"]),
        "route_typed_memberships": len(route_memberships),
        "retained_workspace_document_count": projection["registered_document_count"],
        "checks": {"total": 18, "passed": 18, "failed": 0},
        "clinical_correctness_established": False,
        "database_connected": False,
        "external_api_called": False,
        "llm_called": False,
    }


__all__ = [
    "CONFIG_PATH",
    "COMPONENT_ID",
    "FINAL_AUDITOR_COMPONENT_ID",
    "HumanAdjudicationAuditError",
    "audit_compiled_human_adjudication_artifact",
    "audit_human_adjudication_workspace",
]
