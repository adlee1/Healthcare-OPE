"""Validation and freeze gates for Query 202 lifecycle A v2.

The v1 file remains an immutable architecture record.  This module validates
the separately versioned, implementable v2 contract.  It supports exactly two
states: a fail-closed implementation draft and a fully pinned execution freeze.
Changing the root status or permission flag cannot satisfy the freeze gate.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import struct
import tomllib
from typing import Any, Mapping

from .database import _statement_body
from .query202_preadjudication_sql_v2 import (
    BOUNDARY_STAGES as SQL_BOUNDARY_STAGES,
    BUCKET_COUNT as SQL_BUCKET_COUNT,
    BUCKET_HASH_PREFIX as SQL_BUCKET_HASH_PREFIX,
    BUCKET_HASH_VERSION as SQL_BUCKET_HASH_VERSION,
    BUCKET_STATEMENTS as SQL_BUCKET_STATEMENTS,
    TUPLE_FIELDS as SQL_TUPLE_FIELDS,
    TUPLE_VALUE_ENUMS as SQL_TUPLE_VALUE_ENUMS,
    render_bucket_sql,
)


CONFIG_PATH = Path(
    "config/preregistrations/d005_potassium_query202_pre_adjudication_v2.toml"
)
COMPONENT_ID = "D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2"
PLACEHOLDER = "UNSET_REQUIRED_BEFORE_EXECUTION"
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
BUCKET_COUNT = 64
BUCKET_PREFIX = "D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2|"
BUCKET_EXPRESSION = (
    "CASE WHEN {subject_id} IS NULL THEN 0 ELSE mod(((\'x\' || "
    "substr(md5(\'D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2|\' || "
    "({subject_id})::bigint::text), 1, 15))::bit(60)::bigint), 64)::integer END"
)
BUNDLE_ENCODING = (
    "uint32be_path_length+path_utf8+uint64be_content_length+content"
)

SOURCE_FIELDS = [
    "mimiciv_hosp.emar.medication",
    "mimiciv_hosp.emar_detail.product_description",
    "mimiciv_hosp.pharmacy.medication",
    "mimiciv_hosp.prescriptions.drug",
    "mimiciv_hosp.emar_detail.product_description_other",
    "mimiciv_hosp.emar_detail.route",
    "mimiciv_hosp.pharmacy.route",
    "mimiciv_hosp.prescriptions.route",
    "mimiciv_hosp.prescriptions.ndc",
]
SEMANTIC_FIELDS = SOURCE_FIELDS[:5]
ROUTE_FIELDS = SOURCE_FIELDS[5:8]
AUXILIARY_FIELDS = SOURCE_FIELDS[5:]
ROUTE_HASHES = [
    "a3b0d5664ae2e89f08df97f45347a6d7ae7761cdb2d138da781681ed2edd0ea9",
    "2dad858bbbd41002d3a417faa302bda9bd0f85111d47cbd075a0802886ebd76b",
    "b75209f1e0acea76a8c9818936b389a972def151317ede76073fc51dd65f1c0e",
]
PDO_NDC_HASHES = [
    "0105f73cef307cc11b93e1d9d657d43a278c66c3c06ef31e5123db377e11dd4e",
    "10e5ff7bb578ca66aadfe274105ed94a53487ba05d7b80e0ebca8fb8c24bab9e",
]
NONNULL_SET_HASHES = [
    "f8bfd2a1c2d28ddd025bffad8e30f4ceec6d011398b4fa8bcd9958eeb5031845",
    "a88fb059e567bfe191c46615ba55e1c3e4f331093af2374d52a010b5d719fd59",
    "19e115fd0b35a6d9eb3985224c0593ae1813d7d6bffe64ef7874f2167f8a1630",
    "4767540954d4f661e9367600f4a890c75bfa54f03df22f62cc7e3287aef23815",
    "c58654e7a31bb9d30ed1a77751913aac4ea0e4ce89a4369c4317d15732b79b64",
    "82e5032b4e0b4f0114b0e3618028a9dc99118399ed27789a1dd6c068f4e89acc",
    "a4c620815db59fec1969dbc13e8134d30b0f38c2359eb5ea0ac3f217c7834839",
    "1f883ce55fa59f2e48c6bdd6fe6cc6dec185ed1513824f872213eb644e63b1ec",
    "0a83baa56732fb38fc0bf91db4e4d0d000de90fcc2c0439b1efdf1489857234d",
]
NONNULL_COUNTS = [5045, 6692, 11059, 10927, 842, 17, 108, 108, 6589]
PREFLIGHT_TYPED_HASHES = [
    "0105f73cef307cc11b93e1d9d657d43a278c66c3c06ef31e5123db377e11dd4e",
    "a3b0d5664ae2e89f08df97f45347a6d7ae7761cdb2d138da781681ed2edd0ea9",
    "2dad858bbbd41002d3a417faa302bda9bd0f85111d47cbd075a0802886ebd76b",
    "b75209f1e0acea76a8c9818936b389a972def151317ede76073fc51dd65f1c0e",
    "10e5ff7bb578ca66aadfe274105ed94a53487ba05d7b80e0ebca8fb8c24bab9e",
]
PREFLIGHT_TYPED_COUNTS = [843, 18, 109, 109, 6590]
SOURCE_KEYS = [
    "emar_medication",
    "detail_product_description",
    "pharmacy_medication",
    "prescription_drug",
    "detail_product_description_other",
    "emar_detail_route",
    "pharmacy_route",
    "prescriptions_route",
    "prescriptions_ndc",
]
SEMANTIC_SEED_SHA256 = (
    "cee42c49d4618e6c62e99dcea26c53166f21305231b3c35991d2c2534b94368a"
)
DETAIL_RECORD_KINDS = [
    "detail_product_context",
    "detail_seed_membership_bridge",
    "emar_medication_detail_bridge",
    "emar_medication_head_partition",
]
ORDER_RECORD_KINDS = [
    "pharmacy_product_context",
    "prescription_identifier_context",
    "pharmacy_prescription_bridge",
    "pharmacy_no_prescription_component",
    "head_pharmacy_prescription_bridge",
    "detail_pharmacy_prescription_bridge",
    "ndc_external_mapping_input",
]
DETAIL_HEAD_IDENTITY_STATES = ["missing", "conflict", "exact"]
DETAIL_BRIDGE_MATCH_STATES = ["with_detail"]
HEAD_PARTITION_MATCH_STATES = [
    "no_detail",
    "with_detail_exact_only",
    "with_detail_identity_missing_only",
    "with_detail_identity_conflict_only",
    "with_detail_exact_and_identity_missing",
    "with_detail_exact_and_identity_conflict",
    "with_detail_identity_missing_and_conflict",
    "with_detail_exact_identity_missing_and_conflict",
]
PHARMACY_PRESCRIPTION_LINK_STATES = [
    "pharmacy_missing", "subject_missing", "subject_conflict",
    "hadm_missing", "hadm_conflict", "exact",
]
HEAD_ORDER_LINK_STATES = [
    "pharmacy_missing", "prescription_missing",
    "pharmacy_subject_missing", "pharmacy_subject_conflict",
    "prescription_subject_missing", "prescription_subject_conflict",
    "pharmacy_hadm_missing", "pharmacy_hadm_conflict",
    "prescription_hadm_missing", "prescription_hadm_conflict", "exact",
]
DETAIL_ORDER_LINK_STATES = [
    "pharmacy_missing", "prescription_missing",
    "pharmacy_subject_missing", "pharmacy_subject_conflict",
    "prescription_subject_missing", "prescription_subject_conflict",
    "hadm_missing", "hadm_conflict", "exact",
]
POE_AUXILIARY_STATES = ["missing", "conflict", "exact"]
PRIVATE_OUTPUT_NAMES = [
    "typed_boundary_replay",
    "semantic_key_seed",
    "detail_product_crosswalk",
    "detail_seed_membership_bridge",
    "emar_medication_detail_bridge",
    "pharmacy_order_crosswalk",
    "prescription_component_crosswalk",
    "pharmacy_prescription_bridge",
    "head_pharmacy_prescription_bridge",
    "detail_pharmacy_prescription_bridge",
    "ndc_external_mapping_input",
]
PHYSICAL_BUCKET_PARTS = [
    {
        "label": "202b_context_seed",
        "logical_stage": "202b",
        "sql_path": "sql/profiling/202b1_potassium_query202_preadjudication_context_seed_bucket_v2.sql",
        "tuple_kinds": [
            "detail_product_context",
            "detail_seed_membership_bridge",
        ],
        "bucket_input_source": "mimiciv_hosp.emar_detail",
        "owns_bucket_input_controls": True,
    },
    {
        "label": "202b_detail_head_bridge",
        "logical_stage": "202b",
        "sql_path": "sql/profiling/202b2_potassium_query202_preadjudication_detail_head_bridge_bucket_v2.sql",
        "tuple_kinds": ["emar_medication_detail_bridge"],
        "bucket_input_source": "",
        "owns_bucket_input_controls": False,
    },
    {
        "label": "202b_head_partition",
        "logical_stage": "202b",
        "sql_path": "sql/profiling/202b3_potassium_query202_preadjudication_head_partition_bucket_v2.sql",
        "tuple_kinds": ["emar_medication_head_partition"],
        "bucket_input_source": "",
        "owns_bucket_input_controls": False,
    },
    {
        "label": "202c_pharmacy_context",
        "logical_stage": "202c",
        "sql_path": "sql/profiling/202c1_potassium_query202_preadjudication_pharmacy_context_bucket_v2.sql",
        "tuple_kinds": [
            "pharmacy_product_context",
            "pharmacy_no_prescription_component",
        ],
        "bucket_input_source": "mimiciv_hosp.pharmacy",
        "owns_bucket_input_controls": True,
    },
    {
        "label": "202c_prescription_context",
        "logical_stage": "202c",
        "sql_path": "sql/profiling/202c2_potassium_query202_preadjudication_prescription_context_bucket_v2.sql",
        "tuple_kinds": [
            "prescription_identifier_context",
            "pharmacy_prescription_bridge",
            "ndc_external_mapping_input",
        ],
        "bucket_input_source": "mimiciv_hosp.prescriptions",
        "owns_bucket_input_controls": True,
    },
    {
        "label": "202c_head_bridge",
        "logical_stage": "202c",
        "sql_path": "sql/profiling/202c3_potassium_query202_preadjudication_head_bridge_bucket_v2.sql",
        "tuple_kinds": ["head_pharmacy_prescription_bridge"],
        "bucket_input_source": "mimiciv_hosp.emar",
        "owns_bucket_input_controls": True,
    },
    {
        "label": "202c_detail_bridge",
        "logical_stage": "202c",
        "sql_path": "sql/profiling/202c4_potassium_query202_preadjudication_detail_bridge_bucket_v2.sql",
        "tuple_kinds": ["detail_pharmacy_prescription_bridge"],
        "bucket_input_source": "mimiciv_hosp.emar_detail",
        "owns_bucket_input_controls": True,
    },
]
REQUIRED_MUTATION_CLASSES = [
    "timeout_or_nonzero_exit",
    "rollback_or_snapshot_drift",
    "missing_duplicate_or_cross_bucket",
    "boundary_set_or_seed_drift",
    "tuple_or_multiplicity_tamper",
    "lineage_or_limit_tamper",
    "permission_or_gitignore_tamper",
    "public_privacy_leak",
    "implementation_bundle_drift",
]
EVIDENCE_LOCK = [
    (
        "product_mapping_preregistration",
        "config/preregistrations/d005_potassium_product_mapping.toml",
        "960e0e68d848613d2b75c0e2a5afa6db9c853bdbf24a3a2f214bdcccb94df9ee",
    ),
    (
        "query200_manifest",
        "artifacts/profiling/20261011T174457.657508Z/manifest.json",
        "76b9ae67d02081d634965906cb7c11a3671b2c69ac7e194252b996156ee099e6",
    ),
    (
        "query200_audit",
        "artifacts/profiling/20261011T174457.657508Z/audit-summary.json",
        "73ca31b9556165ccb79e3d278812b4d0aec39aa75498327f452ca46fe6b9a31c",
    ),
    (
        "query201_manifest",
        "artifacts/profiling/20261011T182244.083389Z/manifest.json",
        "fe13a910a590df49e26b8e71770735d100af7f9e474cf9769a619c0b2cc6fa44",
    ),
    (
        "query201_audit",
        "artifacts/profiling/20261011T182244.083389Z/audit-summary.json",
        "a7aa9b35d4e408bbeda6b4e024588e3083fc7f13b976492b624d21a390946428",
    ),
    (
        "query201_private_discovery",
        "artifacts/profiling/20261011T182244.083389Z/potassium_full_source_vocabulary_discovery.discovery.json",
        "62731e7dcadf82b95a55e3afd7f2790455320d1c642f9ca307b2574672760d18",
    ),
    (
        "mapping_preflight_manifest",
        "artifacts/profiling/20261011T190426.934406Z/manifest.json",
        "bdfcb78849eadb1b9eafca226fe49c7e70390f45ee0f3ef34c8e92899557c880",
    ),
    (
        "mapping_preflight_audit",
        "artifacts/profiling/20261011T190426.934406Z/audit-summary.json",
        "c96b7bed50a7b29ac7f8bfc14ed05b03394ad3c996d2c4b2c891ccbf964d024e",
    ),
    (
        "mapping_preflight_public_summary",
        "artifacts/profiling/20261011T190426.934406Z/potassium_mapping_preflight.aggregate-summary.json",
        "079a8b774773a039977d21aad88e128d0d3658483268ded38aa931842fa2a220",
    ),
]
SQL_PATHS = [
    "sql/profiling/202a1_potassium_query202_preadjudication_emar_medication_v2.sql",
    "sql/profiling/202a2_potassium_query202_preadjudication_detail_product_description_v2.sql",
    "sql/profiling/202a3_potassium_query202_preadjudication_pharmacy_medication_v2.sql",
    "sql/profiling/202a4_potassium_query202_preadjudication_prescription_drug_v2.sql",
    "sql/profiling/202a5_potassium_query202_preadjudication_detail_product_description_other_v2.sql",
    "sql/profiling/202a6_potassium_query202_preadjudication_emar_detail_route_v2.sql",
    "sql/profiling/202a7_potassium_query202_preadjudication_pharmacy_route_v2.sql",
    "sql/profiling/202a8_potassium_query202_preadjudication_prescriptions_route_v2.sql",
    "sql/profiling/202a9_potassium_query202_preadjudication_prescriptions_ndc_v2.sql",
    *(item["sql_path"] for item in PHYSICAL_BUCKET_PARTS),
]
RUNNER_PATHS = [
    "src/april_repro/query202_preadjudication_sql_v2.py",
    "src/april_repro/query202_pre_adjudication.py",
    "scripts/run_potassium_query202_pre_adjudication.py",
    "src/april_repro/database.py",
    "src/april_repro/staged_source_closure.py",
    "src/april_repro/query202_readonly_explain_attestation.py",
    "scripts/attest_potassium_query202_pre_adjudication_explain.py",
]
AUDITOR_PATHS = [
    "src/april_repro/query202_pre_adjudication_preregistration_v2.py",
    "src/april_repro/query202_pre_adjudication_audit.py",
    "scripts/audit_potassium_query202_pre_adjudication.py",
]
EXPLAIN_ATTESTER_PATHS = [
    "src/april_repro/query202_readonly_explain_attestation.py",
    "scripts/attest_potassium_query202_pre_adjudication_explain.py",
    "src/april_repro/database.py",
    "src/april_repro/staged_source_closure.py",
    "src/april_repro/query202_pre_adjudication.py",
    "src/april_repro/query202_preadjudication_sql_v2.py",
]
EXPLAIN_ATTESTATION_KEYS = frozenset({
    "schema_version", "component_id", "status", "mode", "started_at_utc",
    "finished_at_utc", "elapsed_seconds", "database_connection_opened",
    "synthetic_postgresql_fixture", "single_transaction",
    "transaction_read_only", "transaction_isolation",
    "database_controls_observed_before_explain", "database_control_checks",
    "database_control_elapsed_seconds", "statement_timeout_ms",
    "client_watchdog_seconds", "statement_count", "analyze_used",
    "explain_syntax", "database_writes_or_session_objects", "on_error_stop",
    "rollback_confirmed", "psql_returncode",
    "query_output_redirected_to_os_null", "stdout_control_frames_empty",
    "plan_output_discarded", "plan_output_persisted",
    "stderr_anonymous_unlinked", "stderr_persisted", "sql_text_persisted",
    "raw_values_persisted", "patient_or_event_identifiers_persisted",
    "query_plan_relation_or_column_details_persisted",
    "success_persisted_only_after_rollback_and_clean_exit",
    "sql_bundle_sha256", "attester_bundle_sha256", "attester_paths",
    "attester_files", "bundle_hash_encoding", "control_transcript_sha256",
    "control_transcript_hash_framing", "statement_elapsed_seconds",
    "statements", "rendered_statements", "artifact_directory_mode",
    "artifact_file_mode", "artifact_git_ignored",
})
REQUIRED_TEST_PATHS = [
    "tests/test_query202_pre_adjudication_preregistration_v2.py",
    "tests/test_query202_preadjudication_sql_v2.py",
    "tests/test_query202_pre_adjudication.py",
    "tests/test_query202_pre_adjudication_audit_v2.py",
    "tests/test_query202_readonly_explain_attestation.py",
]
FIXTURE_TEST_COMMAND = (
    "PYTHONPATH=src:. .venv/bin/python -m unittest "
    "tests.test_query202_pre_adjudication_preregistration_v2 "
    "tests.test_query202_preadjudication_sql_v2 "
    "tests.test_query202_pre_adjudication "
    "tests.test_query202_pre_adjudication_audit_v2 "
    "tests.test_query202_readonly_explain_attestation -v"
)
FIXTURE_TEST_COUNT = 59
FIXTURE_ATTESTATION_KEYS = frozenset({
    "schema_version", "component_id", "status", "test_command",
    "tests_run", "failures", "errors", "scientific_contract_sha256",
    "implementation_bundle_sha256", "test_files",
    "mutation_classes_passed",
})
FIXTURE_TEST_FILE_KEYS = frozenset({"path", "file_sha256"})


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and str(path) == value


def read_potassium_query202_pre_adjudication_v2_preregistration(
    root: Path,
) -> dict[str, Any]:
    with (root / CONFIG_PATH).open("rb") as handle:
        return tomllib.load(handle)


def _bundle(root: Path, paths: list[str]) -> dict[str, Any]:
    digest = hashlib.sha256()
    files: list[dict[str, Any]] = []
    missing: list[str] = []
    for relative in paths:
        if not _safe_relative(relative):
            missing.append(str(relative))
            continue
        candidate = root / relative
        if not candidate.is_file() or candidate.is_symlink():
            missing.append(relative)
            continue
        path_bytes = relative.encode("utf-8")
        content = candidate.read_bytes()
        digest.update(len(path_bytes).to_bytes(4, "big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        files.append(
            {
                "path": relative,
                "bytes": len(content),
                "file_sha256": _sha_bytes(content),
            }
        )
    return {
        "paths": paths,
        "bundle_sha256": digest.hexdigest() if not missing else None,
        "files": files,
        "missing": missing,
        "encoding": BUNDLE_ENCODING,
    }


def implementation_bundles(
    root: Path, config: Mapping[str, Any] | None = None
) -> dict[str, dict[str, Any]]:
    if config is None:
        config = read_potassium_query202_pre_adjudication_v2_preregistration(root)
    implementation = config.get("implementation", {})
    return {
        "sql": _bundle(root, list(implementation.get("sql_paths", []))),
        "runner": _bundle(root, list(implementation.get("runner_paths", []))),
        "offline_auditor": _bundle(
            root, list(implementation.get("auditor_paths", []))
        ),
    }


def _contract_projection(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return the scientific/engineering contract covered by fixture attestation.

    Mutable lifecycle state, implementation digests and the attestation's own
    location are excluded to avoid a circular hash.  Paths, limits and all
    scientific boundaries remain covered.
    """
    projection = json.loads(json.dumps(config))
    for key in (
        "status",
        "rule_version",
        "execution_status",
        "execution_permitted",
        "implementation_state",
    ):
        projection.pop(key, None)
    implementation = projection.get("implementation", {})
    for key in (
        "state",
        "sql_bundle_sha256",
        "runner_bundle_sha256",
        "auditor_bundle_sha256",
    ):
        implementation.pop(key, None)
    fixture = projection.get("fixture_gate", {})
    for key in (
        "status", "attestation_path", "attestation_sha256",
        "readonly_postgresql_explain_status",
        "readonly_postgresql_explain_attestation_path",
        "readonly_postgresql_explain_attestation_sha256",
    ):
        fixture.pop(key, None)
    gate = projection.get("execution_gate", {})
    gate.pop("unresolved_blockers", None)
    return projection


def scientific_contract_sha256(config: Mapping[str, Any]) -> str:
    payload = json.dumps(
        _contract_projection(config),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return _sha_bytes(payload)


def _expect(
    table: Mapping[str, Any], key: str, expected: Any, label: str, errors: list[str]
) -> None:
    if table.get(key) != expected:
        errors.append(f"{label}.{key} must be {expected!r}")


def _validate_guards(config: Mapping[str, Any], frozen: bool, errors: list[str]) -> None:
    del frozen
    guards = config.get("guards")
    if not isinstance(guards, dict) or not guards:
        errors.append("guards must be a nonempty table")
        return
    for key, value in guards.items():
        expected = False
        if value is not expected:
            errors.append(f"guards.{key} must be {expected!r}")


def _validate_state(config: Mapping[str, Any], errors: list[str]) -> bool:
    frozen = config.get("status") == "frozen_for_execution"
    if frozen:
        expected = {
            "rule_version": "k-query202-pre-adjudication-evidence-v2-frozen",
            "execution_status": "not_executed",
            "execution_permitted": True,
            "implementation_state": "frozen_for_execution",
        }
    else:
        expected = {
            "status": "proposed",
            "rule_version": "k-query202-pre-adjudication-evidence-v2-draft",
            "execution_status": "not_executed",
            "execution_permitted": False,
            "implementation_state": "implementation_in_progress",
        }
    for key, value in expected.items():
        _expect(config, key, value, "root", errors)
    return frozen


def _validate_contract(config: Mapping[str, Any], errors: list[str]) -> None:
    root_expected = {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "decision_id": "D005",
        "specified_on": "2026-10-12",
        "author_setting_recovered": False,
        "formal_product_mapping_enabled": False,
        "formal_source_policy_enabled": False,
    }
    for key, value in root_expected.items():
        _expect(config, key, value, "root", errors)

    lifecycle = config.get("lifecycle", {})
    lifecycle_expected = {
        "supersedes_architecture_component_id": (
            "D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v1"
        ),
        "reviewed_semantic_ledger_is_input": False,
        "frozen_route_mapping_is_input": False,
        "external_ndc_lookup_is_input": False,
        "output_may_support_later_external_ndc_lookup": True,
        "event_mapping_or_clinical_selection_allowed": False,
        "same_snapshot_with_post_adjudication_lifecycle_claim_allowed": False,
        "v1_architecture_record_remains_immutable": True,
    }
    for key, value in lifecycle_expected.items():
        _expect(lifecycle, key, value, "lifecycle", errors)

    upstream = config.get("upstream_boundaries", {})
    upstream_expected = {
        "query201_source_field_memberships": 33723,
        "query201_source_fields": SOURCE_FIELDS[:4],
        "query201_expected_nonnull_distinct_counts": [5045, 6692, 11059, 10927],
        "query201_expected_nonnull_set_sha256": NONNULL_SET_HASHES[:4],
        "query201_exact_set_match_required_per_source_field": True,
        "product_description_other_nonnull_exact_values": 842,
        "semantic_seed_expected_keys": 34565,
        "query200_is_candidate_ceiling": False,
        "query200_only_filter_allowed": False,
        "q201_values_outside_query200_must_be_retained": True,
        "all_product_description_other_values_must_be_retained": True,
        "query200_null_description_local_code_evidence_must_be_retained": True,
    }
    for key, value in upstream_expected.items():
        _expect(upstream, key, value, "upstream_boundaries", errors)

    transaction = config.get("transaction", {})
    transaction_expected = {
        "transaction_isolation": "repeatable read",
        "transaction_read_only": True,
        "all_pre_adjudication_sql_statements_share_one_snapshot": True,
        "statement_timeout_ms": 120000,
        "per_statement_timeout_applies_to_every_unpartitioned_and_bucketed_sql": True,
        "explicit_rollback_required": True,
        "clean_psql_exit_required": True,
        "database_mutation_allowed": False,
        "temporary_tables_allowed": False,
        "temporary_views_allowed": False,
        "indexes_allowed": False,
        "functions_or_procedures_allowed": False,
        "session_database_objects_allowed": False,
        "artifacts_persist_only_after_rollback_and_clean_exit": True,
        "any_statement_timeout_or_failure_discards_entire_run": True,
        "cross_lifecycle_same_snapshot_claim_allowed": False,
    }
    for key, value in transaction_expected.items():
        _expect(transaction, key, value, "transaction", errors)

    stages = config.get("stages", {})
    if list(stages) != ["202a", "202b", "202c"]:
        errors.append("stages must be exactly 202a, 202b and 202c")
    stage_a = stages.get("202a", {})
    for key, value in {
        "source_fields": SOURCE_FIELDS,
        "statement_count": 9,
        "typed_null_and_nonnull_remain_distinct": True,
        "normalization_before_hash_allowed": False,
        "sampling_allowed": False,
        "semantic_filtering_allowed": False,
        "semantic_seed_fields": SEMANTIC_FIELDS,
        "semantic_seed_contains_only_nonnull_exact_values": True,
        "semantic_seed_contains_review_decisions": False,
        "auxiliary_boundary_fields": AUXILIARY_FIELDS,
        "product_description_other_sql_null_is_missing_evidence_not_semantic_key": True,
        "hash_match_unit": "each source field separately",
    }.items():
        _expect(stage_a, key, value, "stages.202a", errors)
    stage_b = stages.get("202b", {})
    for key, value in {
        "bucketed": True,
        "bucket_count": 64,
        "physical_statement_count_per_bucket": 3,
        "physical_parts": [
            item for item in PHYSICAL_BUCKET_PARTS
            if item["logical_stage"] == "202b"
        ],
        "selection_may_use_query200_scope": False,
        "record_kinds": DETAIL_RECORD_KINDS,
        "detail_head_identity_states": DETAIL_HEAD_IDENTITY_STATES,
        "detail_bridge_match_states": DETAIL_BRIDGE_MATCH_STATES,
        "head_partition_detail_match_states": HEAD_PARTITION_MATCH_STATES,
        "no_detail_and_detail_head_identity_conflict_counts_retained": True,
        "nonnull_emar_medication_heads_partition_into_with_detail_and_no_detail": True,
        "emar_medication_to_detail_bridge_required": True,
        "global_input_denominator_boundary_fields": [
            SOURCE_FIELDS[1], SOURCE_FIELDS[4], SOURCE_FIELDS[5]
        ],
        "global_input_denominator_boundary_source_rows_must_agree": True,
        "per_bucket_global_input_rows_control_allowed": False,
        "private_crosswalk_contains_patient_or_event_ids": False,
        "private_crosswalk_contains_timestamps": False,
        "head_cooccurrence_establishes_product_equivalence": False,
        "local_product_code_is_ndc": False,
        "patient_or_event_level_clinical_eligibility_may_be_inferred": False,
    }.items():
        _expect(stage_b, key, value, "stages.202b", errors)
    stage_c = stages.get("202c", {})
    for key, value in {
        "bucketed": True,
        "bucket_count": 64,
        "physical_statement_count_per_bucket": 4,
        "physical_parts": [
            item for item in PHYSICAL_BUCKET_PARTS
            if item["logical_stage"] == "202c"
        ],
        "selection_may_use_query200_scope": False,
        "retain_all_main_base_additive_components": True,
        "raw_ndc_retained_without_normalization_validation_or_external_lookup": True,
        "sql_null_ndc_excluded_from_external_mapping_input": True,
        "record_kinds": ORDER_RECORD_KINDS,
        "private_crosswalk_contains_patient_order_ids_or_timestamps": False,
        "pharmacy_without_prescription_component_retained": True,
        "head_pharmacy_prescription_bridge_required": True,
        "detail_pharmacy_prescription_bridge_required": True,
        "head_and_detail_pharmacy_keys_are_separate_link_paths": True,
        "head_and_detail_pharmacy_keys_may_be_coalesced": False,
        "pharmacy_prescription_link_identity_states": PHARMACY_PRESCRIPTION_LINK_STATES,
        "head_pharmacy_prescription_link_identity_states": HEAD_ORDER_LINK_STATES,
        "detail_pharmacy_prescription_link_identity_states": DETAIL_ORDER_LINK_STATES,
        "poe_auxiliary_states": POE_AUXILIARY_STATES,
        "global_input_denominator_boundary_fields": SOURCE_FIELDS[:4],
        "same_relation_boundary_source_rows_must_agree": True,
        "per_bucket_global_input_rows_control_allowed": False,
    }.items():
        _expect(stage_c, key, value, "stages.202c", errors)

    route = config.get("route_boundary_reference", {})
    for key, value in {
        "route_fields": ROUTE_FIELDS,
        "expected_typed_set_sha256": ROUTE_HASHES,
        "expected_typed_distinct_counts": [18, 109, 109],
        "expected_nonnull_distinct_counts": [17, 108, 108],
        "expected_nonnull_set_sha256": NONNULL_SET_HASHES[5:8],
        "hash_match_required_per_source_field": True,
        "cross_field_union_hash_may_substitute": False,
        "typed_sql_null_is_missing_not_unknown": True,
        "route_categories_are_not_assigned_in_this_lifecycle": True,
    }.items():
        _expect(route, key, value, "route_boundary_reference", errors)
    auxiliary = config.get("auxiliary_boundary_reference", {})
    for key, value in {
        "source_fields": [SOURCE_FIELDS[4], SOURCE_FIELDS[8]],
        "expected_typed_set_sha256": PDO_NDC_HASHES,
        "expected_typed_distinct_counts": [843, 6590],
        "expected_nonnull_distinct_counts": [842, 6589],
        "expected_nonnull_set_sha256": [NONNULL_SET_HASHES[4], NONNULL_SET_HASHES[8]],
        "hash_match_required_per_source_field": True,
        "product_description_other_sql_null_is_missing_evidence": True,
        "ndc_normalization_before_hash_allowed": False,
    }.items():
        _expect(auxiliary, key, value, "auxiliary_boundary_reference", errors)

    seed = config.get("semantic_seed_lineage", {})
    for key, value in {
        "key": ["source_field", "exact_raw_value"],
        "expected_key_count": 34565,
        "q201_key_count": 33723,
        "product_description_other_key_count": 842,
        "expected_key_set_sha256": SEMANTIC_SEED_SHA256,
        "later_reviewed_ledger_may_add_or_drop_keys": False,
        "sql_null_creates_semantic_seed_key": False,
    }.items():
        _expect(seed, key, value, "semantic_seed_lineage", errors)
    ndc = config.get("external_ndc_handoff", {})
    for key, value in {
        "enabled_during_this_lifecycle": False,
        "private_ndc_export_required_after_success": True,
        "private_ndc_export_created": False,
        "ndc_export_preserves_typed_exact_local_value_and_order_context": True,
        "external_mapping_may_rewrite_local_exact_values": False,
        "external_mapping_result_is_not_a_database_snapshot": True,
        "external_mapping_result_does_not_accept_product_identity": True,
    }.items():
        _expect(ndc, key, value, "external_ndc_handoff", errors)

    outputs = config.get("private_outputs")
    if not isinstance(outputs, list) or [item.get("name") for item in outputs] != PRIVATE_OUTPUT_NAMES:
        errors.append("private_outputs must retain the exact eleven registered outputs")
    elif any(item.get("contains_raw_values") is not True for item in outputs):
        errors.append("every private output must declare contains_raw_values=true")

    artifact = config.get("artifact_policy", {})
    for key, value in {
        "private_directory_mode": "0700",
        "private_file_mode": "0600",
        "git_ignored_required": True,
        "public_raw_values_allowed": False,
        "public_patient_event_order_identifiers_allowed": False,
        "public_per_value_or_per_event_hashes_allowed": False,
        "public_whole_private_file_hashes_allowed": True,
        "public_aggregate_counts_and_set_hashes_allowed": True,
    }.items():
        _expect(artifact, key, value, "artifact_policy", errors)

    plan = config.get("bucket_plan", {})
    for key, value in {
        "status": "frozen",
        "bucket_count": 64,
        "bucket_indices": list(range(64)),
        "bucketed_stages": ["202b", "202c"],
        "physical_bucket_template_count": 7,
        "physical_bucket_statements_per_bucket": 7,
        "physical_bucket_statement_labels": [
            item["label"] for item in PHYSICAL_BUCKET_PARTS
        ],
        "bucket_input_control_owner_labels": [
            item["label"] for item in PHYSICAL_BUCKET_PARTS
            if item["owns_bucket_input_controls"]
        ],
        "hash_prefix": BUCKET_PREFIX,
        "sql_expression": BUCKET_EXPRESSION,
        "null_subject_bucket": 0,
        "all_indices_required_once": True,
        "selection_uses_only_upstream_performance_evidence": True,
        "selection_does_not_use_product_review_or_downstream_results": True,
        "missing_duplicate_or_cross_bucket_row_fails_closed": True,
        "bucket_counts_and_global_merges_must_cover_all_64_buckets": True,
        "independent_from_mapped_event_application_bucket_plan": True,
    }.items():
        _expect(plan, key, value, "bucket_plan", errors)
    sql_enum_expectations = {
        ("202b", "emar_medication_detail_bridge", "detail_head_identity_state"):
            DETAIL_HEAD_IDENTITY_STATES,
        ("202b", "emar_medication_detail_bridge", "detail_match_state"):
            DETAIL_BRIDGE_MATCH_STATES,
        ("202b", "emar_medication_head_partition", "detail_match_state"):
            HEAD_PARTITION_MATCH_STATES,
        ("202c", "pharmacy_prescription_bridge", "link_identity_state"):
            PHARMACY_PRESCRIPTION_LINK_STATES,
        ("202c", "head_pharmacy_prescription_bridge", "link_identity_state"):
            HEAD_ORDER_LINK_STATES,
        ("202c", "detail_pharmacy_prescription_bridge", "link_identity_state"):
            DETAIL_ORDER_LINK_STATES,
        ("202c", "pharmacy_prescription_bridge", "poe_auxiliary_state"):
            POE_AUXILIARY_STATES,
        ("202c", "head_pharmacy_prescription_bridge", "poe_auxiliary_state"):
            POE_AUXILIARY_STATES,
        ("202c", "detail_pharmacy_prescription_bridge", "poe_auxiliary_state"):
            POE_AUXILIARY_STATES,
    }
    executable_parts = [
        {
            "label": item.stage,
            "logical_stage": item.logical_stage,
            "sql_path": item.sql_path,
            "tuple_kinds": list(item.tuple_kinds),
            "bucket_input_source": item.bucket_input_source or "",
            "owns_bucket_input_controls": item.bucket_input_source is not None,
        }
        for item in SQL_BUCKET_STATEMENTS
    ]
    sql_contract_ok = (
        SQL_BUCKET_COUNT == BUCKET_COUNT
        and SQL_BUCKET_HASH_PREFIX == BUCKET_PREFIX
        and SQL_BUCKET_HASH_VERSION == plan.get("version")
        and [item.source_field for item in SQL_BOUNDARY_STAGES] == SOURCE_FIELDS
        and [item.sql_path for item in SQL_BOUNDARY_STAGES] == SQL_PATHS[:9]
        and executable_parts == PHYSICAL_BUCKET_PARTS
        and [item["sql_path"] for item in executable_parts] == SQL_PATHS[9:]
        and list(SQL_TUPLE_FIELDS.get("202b", {})) == DETAIL_RECORD_KINDS
        and list(SQL_TUPLE_FIELDS.get("202c", {})) == ORDER_RECORD_KINDS
        and all(
            list(SQL_TUPLE_VALUE_ENUMS.get(key, ())) == expected
            for key, expected in sql_enum_expectations.items()
        )
    )
    if not sql_contract_ok:
        errors.append("executable SQL contract differs from the v2 preregistration")

    merge = config.get("offline_merge", {})
    for key, value in {
        "occurs_only_after_rollback_and_clean_exit": True,
        "uses_typed_exact_tuple_k_way_merge_across_all_preregistered_buckets": True,
        "same_exact_raw_tuple_across_buckets_is_merged_by_summing_int64_bounded_multiplicity": True,
        "typed_null_and_nonnull_empty_string_remain_distinct": True,
        "global_tuple_set_sha256_recomputed_from_merged_unique_tuples": True,
        "global_tuple_frequency_sha256_recomputed_from_merged_tuples_and_uint64_multiplicity": True,
        "global_input_rows_must_be_derived_from_same_snapshot_boundary_source_rows": True,
        "summed_bucket_input_rows_must_equal_boundary_derived_global_input_rows": True,
        "per_kind_input_rows_must_equal_tuple_multiplicity": True,
        "per_bucket_global_input_rows_control_allowed": False,
        "bucket_set_or_frequency_hashes_may_be_added_concatenated_or_used_as_global_hash": False,
        "private_whole_file_hashes_recomputed": True,
        "public_per_value_per_tuple_or_per_event_hashes_allowed": False,
        "public_output_contains_only_named_denominators_set_hashes_whole_file_hashes_and_controls": True,
        "physical_frames_independently_zlib_compressed": True,
        "external_merge_uses_anonymous_sorted_logical_bucket_runs": True,
        "anonymous_sorted_runs_per_logical_stage": 64,
        "external_merge_pass_count": 2,
        "private_artifact_encoding": "gzip+utf8+ndjson-v1",
        "private_artifact_single_gzip_member_required": True,
        "private_artifact_strict_record_order_required": True,
        "private_artifact_stream_validation_required": True,
    }.items():
        _expect(merge, key, value, "offline_merge", errors)

    limits = config.get("limits", {})
    for key, value in {
        "boundary_statement_count": 9,
        "bucketed_statement_count": 448,
        "total_scientific_statement_count": 457,
        "statement_timeout_ms": 120000,
        "client_watchdog_seconds": 135,
        "max_boundary_frame_bytes": 268435456,
        "max_crosswalk_frame_bytes": 536870912,
        "max_crosswalk_frame_bytes_applies_to_combined_physical_frames_per_logical_bucket": True,
        "max_cumulative_raw_frame_bytes": 17179869184,
        "max_total_anonymous_spool_bytes": 4294967296,
        "max_merge_run_raw_bytes": 17179869184,
        "max_merge_run_spool_bytes": 4294967296,
        "max_private_artifact_raw_bytes": 17179869184,
        "max_private_artifact_stored_bytes": 4294967296,
        "max_private_artifact_line_bytes": 8388608,
        "max_tuple_json_utf8_bytes": 1048576,
        "max_executed_sql_bytes": 16777216,
        "max_boundary_groups_per_field": 1000000,
        "max_tuple_groups_per_bucket": 5000000,
        "max_tuple_groups_per_bucket_applies_to_combined_physical_parts": True,
        "max_exact_multiplicity": 9223372036854775807,
    }.items():
        _expect(limits, key, value, "limits", errors)

    evidence = config.get("evidence")
    observed = []
    if isinstance(evidence, list):
        observed = [
            (item.get("name"), item.get("path"), item.get("file_sha256"))
            for item in evidence
            if isinstance(item, dict)
        ]
    if observed != EVIDENCE_LOCK:
        errors.append("evidence paths and hashes differ from the nine-file lock")


def _validate_implementation(
    config: Mapping[str, Any], frozen: bool, errors: list[str]
) -> None:
    implementation = config.get("implementation", {})
    if implementation.get("bundle_hash_encoding") != BUNDLE_ENCODING:
        errors.append("implementation.bundle_hash_encoding differs from its lock")
    expected_paths = {
        "sql_paths": SQL_PATHS,
        "runner_paths": RUNNER_PATHS,
        "auditor_paths": AUDITOR_PATHS,
    }
    for key, registered in expected_paths.items():
        paths = implementation.get(key)
        if paths != registered:
            errors.append(f"implementation.{key} differs from the exact path lock")
        elif len(set(paths)) != len(paths) or any(not _safe_relative(path) for path in paths):
            errors.append(f"implementation.{key} contains duplicate or unsafe paths")
    expected_state = "frozen_for_execution" if frozen else "implementation_in_progress"
    _expect(implementation, "state", expected_state, "implementation", errors)
    for key in ("sql_bundle_sha256", "runner_bundle_sha256", "auditor_bundle_sha256"):
        value = implementation.get(key)
        if frozen:
            if not isinstance(value, str) or HEX_SHA256.fullmatch(value) is None:
                errors.append(f"implementation.{key} must be a pinned SHA-256")
        elif value != PLACEHOLDER:
            errors.append(f"implementation.{key} must remain unset in draft state")


def _validate_fixture_gate(
    config: Mapping[str, Any], frozen: bool, errors: list[str]
) -> None:
    fixture = config.get("fixture_gate", {})
    if fixture.get("required_test_paths") != REQUIRED_TEST_PATHS:
        errors.append("fixture_gate.required_test_paths differs from its exact lock")
    if fixture.get("required_mutation_classes") != REQUIRED_MUTATION_CLASSES:
        errors.append("fixture_gate.required_mutation_classes differs from its lock")
    if fixture.get("failures_required") != 0:
        errors.append("fixture_gate.failures_required must be zero")
    if fixture.get("synthetic_postgresql_fixture_passed") is not False:
        errors.append("fixture_gate.synthetic_postgresql_fixture_passed must remain false")
    if fixture.get("status_change_alone_may_enable_execution") is not False:
        errors.append("fixture status alone cannot enable execution")
    if frozen:
        if fixture.get("status") != "passed":
            errors.append("fixture_gate.status must be passed when frozen")
        if not _safe_relative(fixture.get("attestation_path")):
            errors.append("fixture_gate.attestation_path must be safe and project-relative")
        if not isinstance(fixture.get("attestation_sha256"), str) or HEX_SHA256.fullmatch(
            fixture.get("attestation_sha256", "")
        ) is None:
            errors.append("fixture_gate.attestation_sha256 must be pinned")
        if fixture.get("readonly_postgresql_explain_status") != "passed":
            errors.append("fixture_gate.readonly_postgresql_explain_status must be passed when frozen")
        if not _safe_relative(
            fixture.get("readonly_postgresql_explain_attestation_path")
        ):
            errors.append(
                "fixture_gate.readonly_postgresql_explain_attestation_path must be safe and project-relative"
            )
        if not isinstance(
            fixture.get("readonly_postgresql_explain_attestation_sha256"), str
        ) or HEX_SHA256.fullmatch(
            fixture.get("readonly_postgresql_explain_attestation_sha256", "")
        ) is None:
            errors.append(
                "fixture_gate.readonly_postgresql_explain_attestation_sha256 must be pinned"
            )
    else:
        for key, value in {
            "status": "pending",
            "attestation_path": PLACEHOLDER,
            "attestation_sha256": PLACEHOLDER,
            "readonly_postgresql_explain_status": "pending",
            "readonly_postgresql_explain_attestation_path": PLACEHOLDER,
            "readonly_postgresql_explain_attestation_sha256": PLACEHOLDER,
        }.items():
            _expect(fixture, key, value, "fixture_gate", errors)


def validate_potassium_query202_pre_adjudication_v2_preregistration(
    config: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    frozen = _validate_state(config, errors)
    _validate_contract(config, errors)
    _validate_implementation(config, frozen, errors)
    _validate_fixture_gate(config, frozen, errors)
    _validate_guards(config, frozen, errors)
    gate = config.get("execution_gate", {})
    for key in (
        "status_change_alone_may_enable_execution",
        "database_execution_before_all_blockers_clear_fails_closed",
        "freeze_requires_all_implementation_paths_and_bundle_hashes_verified",
        "freeze_requires_fixture_attestation_verified",
    ):
        expected = key != "status_change_alone_may_enable_execution"
        if gate.get(key) is not expected:
            errors.append(f"execution_gate.{key} must be {expected!r}")
    blockers = gate.get("unresolved_blockers")
    if frozen and blockers != []:
        errors.append("execution_gate.unresolved_blockers must be empty when frozen")
    if not frozen and (not isinstance(blockers, list) or not blockers):
        errors.append("draft execution_gate.unresolved_blockers must be nonempty")
    return errors


def _verify_evidence(root: Path, config: Mapping[str, Any], errors: list[str]) -> int:
    checked = 0
    for item in config.get("evidence", []):
        if not isinstance(item, dict) or not _safe_relative(item.get("path")):
            continue
        path = root / item["path"]
        if not path.is_file() or path.is_symlink():
            errors.append(f"Required evidence file is absent: {item['path']}")
            continue
        checked += 1
        if _sha_file(path) != item.get("file_sha256"):
            errors.append(f"Evidence hash mismatch: {item['path']}")
    return checked


def _read_unique_json(path: Path) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("attestation is not an object")
    return value


def _nonnull_set_hash(source_field: str, values: list[str]) -> str:
    source = source_field.encode("utf-8")
    encoded = sorted(value.encode("utf-8") for value in values)
    if len(encoded) != len(set(encoded)):
        raise ValueError("duplicate exact nonnull value")
    digest = hashlib.sha256(b"source-field-nonnull-exact-value-set-v1")
    digest.update(struct.pack(">Q", len(encoded)))
    for value in encoded:
        digest.update(struct.pack(">I", len(source)))
        digest.update(source)
        digest.update(struct.pack(">Q", len(value)))
        digest.update(value)
    return digest.hexdigest()


def _typed_set_hash(source_field: str, records: list[Mapping[str, Any]]) -> str:
    source = source_field.encode("utf-8")
    null_seen = False
    nonnull: list[bytes] = []
    for record in records:
        is_null = record.get("raw_is_null")
        raw = record.get("raw_value")
        if is_null is True and raw is None:
            if null_seen:
                raise ValueError("duplicate SQL NULL")
            null_seen = True
        elif is_null is False and isinstance(raw, str):
            nonnull.append(raw.encode("utf-8"))
        else:
            raise ValueError("malformed typed record")
    if len(nonnull) != len(set(nonnull)):
        raise ValueError("duplicate typed value")
    nonnull.sort()
    digest = hashlib.sha256(b"typed-distinct-source-value-set-v1")
    digest.update(struct.pack(">I", len(source)))
    digest.update(source)
    digest.update(struct.pack(">Q", len(nonnull) + int(null_seen)))
    if null_seen:
        digest.update(b"\x00")
    for value in nonnull:
        digest.update(b"\x01")
        digest.update(struct.pack(">Q", len(value)))
        digest.update(value)
    return digest.hexdigest()


def _semantic_seed_hash(items: list[tuple[str, str]]) -> str:
    encoded = sorted((field.encode("utf-8"), value.encode("utf-8")) for field, value in items)
    if len(encoded) != len(set(encoded)):
        raise ValueError("duplicate semantic seed key")
    digest = hashlib.sha256(b"source-field-nonnull-exact-value-set-v1")
    digest.update(struct.pack(">Q", len(encoded)))
    for source, value in encoded:
        digest.update(struct.pack(">I", len(source)))
        digest.update(source)
        digest.update(struct.pack(">Q", len(value)))
        digest.update(value)
    return digest.hexdigest()


def _verify_boundary_lineage(root: Path) -> tuple[bool, str | None]:
    """Independently rebuild all nine frozen nonnull boundaries from evidence."""
    try:
        q201 = _read_unique_json(
            root
            / "artifacts/profiling/20261011T182244.083389Z/"
            "potassium_full_source_vocabulary_discovery.discovery.json"
        )
        q201_sources = q201["sources"]
        values_by_key: dict[str, tuple[str, list[str]]] = {}
        for key in SOURCE_KEYS[:4]:
            source = q201_sources[key]
            values = [record["raw_name"] for record in source["values"]]
            if not all(isinstance(value, str) for value in values):
                raise ValueError("Q201 value type")
            values_by_key[key] = (source["source_field"], values)

        manifest_path = (
            root / "artifacts/profiling/20261011T190426.934406Z/manifest.json"
        )
        manifest = _read_unique_json(manifest_path)
        entries = manifest.get("queries")
        if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
            raise ValueError("preflight manifest query")
        entry = entries[0]
        filename = entry.get("private_values_file")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError("preflight private filename")
        private_path = manifest_path.parent / filename
        if _sha_file(private_path) != entry.get("private_values_sha256"):
            raise ValueError("preflight private hash")
        preflight = _read_unique_json(private_path)
        preflight_sources = preflight["sources"]
        for key in SOURCE_KEYS[4:]:
            source = preflight_sources[key]
            records = source["records"]
            values = [
                record["raw_value"]
                for record in records
                if record.get("raw_is_null") is False
            ]
            if not all(isinstance(value, str) for value in values):
                raise ValueError("preflight value type")
            values_by_key[key] = (source["source_field"], values)
            preflight_index = SOURCE_KEYS[4:].index(key)
            if (
                _typed_set_hash(source["source_field"], records)
                != PREFLIGHT_TYPED_HASHES[preflight_index]
                or len(records) != PREFLIGHT_TYPED_COUNTS[preflight_index]
            ):
                raise ValueError("preflight typed boundary")

        if list(values_by_key) != SOURCE_KEYS:
            raise ValueError("nine-field order")
        for index, key in enumerate(SOURCE_KEYS):
            field, values = values_by_key[key]
            if (
                field != SOURCE_FIELDS[index]
                or len(values) != NONNULL_COUNTS[index]
                or _nonnull_set_hash(field, values) != NONNULL_SET_HASHES[index]
            ):
                raise ValueError("nonnull boundary")
        seed = [
            (values_by_key[key][0], value)
            for key in SOURCE_KEYS[:5]
            for value in values_by_key[key][1]
        ]
        if len(seed) != 34_565 or _semantic_seed_hash(seed) != SEMANTIC_SEED_SHA256:
            raise ValueError("semantic seed")
    except (OSError, UnicodeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False, "Frozen Q201/preflight evidence does not rebuild the nine boundaries"
    return True, None


def _verify_attestation(
    root: Path,
    config: Mapping[str, Any],
    bundles: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, list[str]]:
    fixture = config.get("fixture_gate", {})
    if fixture.get("status") != "passed" or not _safe_relative(
        fixture.get("attestation_path")
    ):
        return False, []
    path = root / fixture["attestation_path"]
    problems: list[str] = []
    try:
        if not path.is_file() or path.is_symlink():
            return False, ["fixture attestation is absent"]
        if _sha_file(path) != fixture.get("attestation_sha256"):
            return False, ["fixture attestation hash mismatch"]
        value = _read_unique_json(path)
        expected_bundles = {
            name: item.get("bundle_sha256") for name, item in bundles.items()
        }
        files = value.get("test_files")
        exact_file_schema = (
            isinstance(files, list)
            and len(files) == len(REQUIRED_TEST_PATHS)
            and all(
                isinstance(item, dict) and set(item) == FIXTURE_TEST_FILE_KEYS
                for item in files
            )
        )
        expected_test_files = [
            {"path": relative, "file_sha256": _sha_file(root / relative)}
            for relative in REQUIRED_TEST_PATHS
            if _safe_relative(relative)
            and (root / relative).is_file()
            and not (root / relative).is_symlink()
        ]
        checks = {
            "exact schema": set(value) == FIXTURE_ATTESTATION_KEYS,
            "schema version": type(value.get("schema_version")) is int
            and value.get("schema_version") == 1,
            "component_id": value.get("component_id") == COMPONENT_ID,
            "status": value.get("status") == "passed",
            "test command": value.get("test_command") == FIXTURE_TEST_COMMAND,
            "contract": value.get("scientific_contract_sha256")
            == scientific_contract_sha256(config),
            "bundles": value.get("implementation_bundle_sha256") == expected_bundles,
            "configured tests": fixture.get("required_test_paths")
            == REQUIRED_TEST_PATHS,
            "test file schema": exact_file_schema,
            "tests": exact_file_schema
            and len(expected_test_files) == len(REQUIRED_TEST_PATHS)
            and files == expected_test_files,
            "mutations": value.get("mutation_classes_passed")
            == REQUIRED_MUTATION_CLASSES,
            "tests_run": type(value.get("tests_run")) is int
            and value.get("tests_run") == FIXTURE_TEST_COUNT,
            "failures": type(value.get("failures")) is int
            and value.get("failures") == 0,
            "errors": type(value.get("errors")) is int
            and value.get("errors") == 0,
        }
        problems.extend(
            f"fixture attestation {name} mismatch"
            for name, passed in checks.items()
            if not passed
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return False, ["fixture attestation is malformed"]
    return not problems, problems


def _finite_nonnegative(value: Any, maximum: float | None = None) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    number = float(value)
    return math.isfinite(number) and number >= 0 and (
        maximum is None or number <= maximum
    )


def _utc_attestation_interval(value: Mapping[str, Any]) -> bool:
    try:
        started = datetime.fromisoformat(value["started_at_utc"])
        finished = datetime.fromisoformat(value["finished_at_utc"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        started.tzinfo is not None
        and finished.tzinfo is not None
        and started.utcoffset() == timedelta(0)
        and finished.utcoffset() == timedelta(0)
        and finished >= started
    )


def _expected_explain_statements(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    statements: list[dict[str, Any]] = []
    rendered: list[dict[str, Any]] = []
    for index, relative in enumerate(SQL_PATHS):
        raw = (root / relative).read_bytes()
        template = raw.decode("utf-8")
        bucket_index = None if index < 9 else 0
        sql = template if bucket_index is None else render_bucket_sql(template, 0)
        body = _statement_body(sql)
        control = (
            "SET LOCAL statement_timeout = '120000ms';\n"
            "EXPLAIN (FORMAT JSON)\n"
            + body
            + ";\n"
        ).encode("utf-8")
        statements.append({
            "path": relative,
            "template_sha256": _sha_bytes(raw),
            "rendered_bucket_index": bucket_index,
            "explain_only": True,
            "analyze": False,
            "status": "passed",
            "statement_timeout_ms": 120000,
        })
        rendered.append({
            "ordinal": index,
            "path": relative,
            "rendered_bucket_index": bucket_index,
            "rendered_statement_sha256": _sha_bytes(body.encode("utf-8")),
            "explain_control_sha256": _sha_bytes(control),
        })
    return statements, rendered


def _verify_readonly_explain_attestation(
    root: Path,
    config: Mapping[str, Any],
    bundles: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, list[str]]:
    """Verify the separate real-PostgreSQL EXPLAIN-only execution gate."""
    fixture = config.get("fixture_gate", {})
    if fixture.get("readonly_postgresql_explain_status") != "passed" or not _safe_relative(
        fixture.get("readonly_postgresql_explain_attestation_path")
    ):
        return False, []
    path = root / fixture["readonly_postgresql_explain_attestation_path"]
    problems: list[str] = []
    try:
        if not path.is_file() or path.is_symlink():
            return False, ["read-only EXPLAIN attestation is absent"]
        if _sha_file(path) != fixture.get(
            "readonly_postgresql_explain_attestation_sha256"
        ):
            return False, ["read-only EXPLAIN attestation hash mismatch"]
        value = _read_unique_json(path)
        expected_statements, expected_rendered = _expected_explain_statements(root)
        expected_attester = _bundle(root, EXPLAIN_ATTESTER_PATHS)
        elapsed = value.get("statement_elapsed_seconds")
        relative_path = Path(fixture["readonly_postgresql_explain_attestation_path"])
        ignored = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
        checks = {
            "exact_schema": set(value) == EXPLAIN_ATTESTATION_KEYS,
            "schema": value.get("schema_version") == 1,
            "component": value.get("component_id") == COMPONENT_ID,
            "status": value.get("status") == "passed",
            "mode": value.get("mode")
            == "real_postgresql_read_only_explain_without_analyze",
            "database": value.get("database_connection_opened") is True,
            "not_synthetic": value.get("synthetic_postgresql_fixture") is False,
            "single_transaction": value.get("single_transaction") is True,
            "read_only": value.get("transaction_read_only") is True,
            "isolation": value.get("transaction_isolation") == "repeatable read",
            "controls_observed": value.get("database_controls_observed_before_explain") is True,
            "control_checks": value.get("database_control_checks") == {
                "transaction_read_only_on": True,
                "transaction_isolation_repeatable_read": True,
                "statement_timeout_120000ms": True,
            },
            "control_elapsed": _finite_nonnegative(
                value.get("database_control_elapsed_seconds"), 136
            ),
            "timeout": value.get("statement_timeout_ms") == 120000,
            "watchdog": value.get("client_watchdog_seconds") == 135,
            "statement_count": value.get("statement_count") == 16,
            "no_analyze": value.get("analyze_used") is False,
            "explain_syntax": value.get("explain_syntax") == "EXPLAIN (FORMAT JSON)",
            "no_write": value.get("database_writes_or_session_objects") is False,
            "on_error_stop": value.get("on_error_stop") is True,
            "rollback": value.get("rollback_confirmed") is True,
            "psql": value.get("psql_returncode") == 0,
            "query_output_null": value.get("query_output_redirected_to_os_null") is True,
            "stdout_empty": value.get("stdout_control_frames_empty") is True,
            "plan_discarded": value.get("plan_output_discarded") is True
            and value.get("plan_output_persisted") is False,
            "stderr_private": value.get("stderr_anonymous_unlinked") is True
            and value.get("stderr_persisted") is False,
            "sql_not_persisted": value.get("sql_text_persisted") is False,
            "plan_details_not_persisted": value.get(
                "query_plan_relation_or_column_details_persisted"
            ) is False,
            "persistence_order": value.get(
                "success_persisted_only_after_rollback_and_clean_exit"
            ) is True,
            "sql_bundle": value.get("sql_bundle_sha256")
            == bundles["sql"].get("bundle_sha256"),
            "statements": value.get("statements") == expected_statements,
            "rendered_statements": value.get("rendered_statements") == expected_rendered,
            "attester_paths": value.get("attester_paths") == EXPLAIN_ATTESTER_PATHS,
            "attester_files": value.get("attester_files") == expected_attester["files"],
            "attester_bundle": value.get("attester_bundle_sha256")
            == expected_attester["bundle_sha256"],
            "bundle_encoding": value.get("bundle_hash_encoding") == BUNDLE_ENCODING,
            "transcript_hash": isinstance(value.get("control_transcript_sha256"), str)
            and HEX_SHA256.fullmatch(value["control_transcript_sha256"]) is not None,
            "transcript_framing": value.get("control_transcript_hash_framing")
            == "uint64be_control_utf8_length+control_utf8",
            "elapsed_list": isinstance(elapsed, list)
            and len(elapsed) == 16
            and all(_finite_nonnegative(item, 136) for item in elapsed),
            "elapsed_total": _finite_nonnegative(value.get("elapsed_seconds")),
            "utc_interval": _utc_attestation_interval(value),
            "privacy": value.get("raw_values_persisted") is False
            and value.get("patient_or_event_identifiers_persisted") is False,
            "artifact_claims": value.get("artifact_directory_mode") == "0700"
            and value.get("artifact_file_mode") == "0600"
            and value.get("artifact_git_ignored") is True,
            "artifact_modes": stat.S_IMODE(path.stat().st_mode) == 0o600
            and path.parent.is_dir()
            and not path.parent.is_symlink()
            and stat.S_IMODE(path.parent.stat().st_mode) == 0o700,
            "artifact_location": bool(relative_path.parts)
            and relative_path.parts[0] == "artifacts"
            and any(line.strip() in {"artifacts/*", "artifacts/"} for line in ignored),
        }
        problems.extend(
            f"read-only EXPLAIN attestation {name} mismatch"
            for name, passed in checks.items()
            if not passed
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return False, ["read-only EXPLAIN attestation is malformed"]
    return not problems, problems


def potassium_query202_pre_adjudication_v2_preregistration_report(
    root: Path,
) -> dict[str, Any]:
    path = root / CONFIG_PATH
    config = read_potassium_query202_pre_adjudication_v2_preregistration(root)
    errors = validate_potassium_query202_pre_adjudication_v2_preregistration(config)
    evidence_checked = _verify_evidence(root, config, errors)
    boundary_lineage_verified, boundary_lineage_error = _verify_boundary_lineage(root)
    if not boundary_lineage_verified and boundary_lineage_error:
        errors.append(boundary_lineage_error)
    bundles = implementation_bundles(root, config)
    implementation = config.get("implementation", {})
    bundle_report: dict[str, Any] = {}
    hashes_verified = True
    for name, digest_key in (
        ("sql", "sql_bundle_sha256"),
        ("runner", "runner_bundle_sha256"),
        ("offline_auditor", "auditor_bundle_sha256"),
    ):
        item = bundles[name]
        expected = implementation.get(digest_key)
        actual = item.get("bundle_sha256")
        matches = not item["missing"] and actual == expected
        if config.get("execution_permitted") is True and not matches:
            errors.append(f"{name} implementation bundle does not match its freeze")
        hashes_verified = hashes_verified and matches
        bundle_report[name] = {
            "paths": item["paths"],
            "expected_sha256": expected,
            "actual_sha256": actual,
            "files": item["files"],
            "missing": item["missing"],
            "verified": matches,
        }
    fixture_verified, fixture_problems = _verify_attestation(root, config, bundles)
    explain_verified, explain_problems = _verify_readonly_explain_attestation(
        root, config, bundles
    )
    if config.get("execution_permitted") is True and not fixture_verified:
        errors.extend(fixture_problems or ["fixture attestation is not verified"])
    if config.get("execution_permitted") is True and not explain_verified:
        errors.extend(
            explain_problems or ["real PostgreSQL read-only EXPLAIN attestation is not verified"]
        )
    freeze_ready = (
        config.get("status") == "frozen_for_execution"
        and config.get("execution_status") == "not_executed"
        and config.get("execution_permitted") is True
        and hashes_verified
        and fixture_verified
        and explain_verified
        and boundary_lineage_verified
        and evidence_checked == len(EVIDENCE_LOCK)
        and not errors
    )
    boundary_expectations: dict[str, dict[str, Any]] = {}
    typed_by_index = {
        4: (PREFLIGHT_TYPED_HASHES[0], PREFLIGHT_TYPED_COUNTS[0]),
        5: (PREFLIGHT_TYPED_HASHES[1], PREFLIGHT_TYPED_COUNTS[1]),
        6: (PREFLIGHT_TYPED_HASHES[2], PREFLIGHT_TYPED_COUNTS[2]),
        7: (PREFLIGHT_TYPED_HASHES[3], PREFLIGHT_TYPED_COUNTS[3]),
        8: (PREFLIGHT_TYPED_HASHES[4], PREFLIGHT_TYPED_COUNTS[4]),
    }
    for index, (source_key, source_field) in enumerate(
        zip(SOURCE_KEYS, SOURCE_FIELDS, strict=True)
    ):
        expected_typed_hash, expected_typed_count = typed_by_index.get(
            index, (None, None)
        )
        boundary_expectations[source_key] = {
            "source_field": source_field,
            "expected_nonnull_set_sha256": NONNULL_SET_HASHES[index],
            "expected_nonnull_distinct_values": NONNULL_COUNTS[index],
            "expected_typed_set_sha256": expected_typed_hash,
            "expected_typed_distinct_values": expected_typed_count,
        }
    return {
        "component_id": config.get("component_id"),
        "status": config.get("status"),
        "execution_status": config.get("execution_status"),
        "execution_permitted": config.get("execution_permitted"),
        "implementation_state": config.get("implementation_state"),
        "config": str(CONFIG_PATH),
        "config_sha256": _sha_file(path),
        "scientific_contract_sha256": scientific_contract_sha256(config),
        "valid": not errors,
        "errors": errors,
        "warnings": [],
        "evidence_files_checked": evidence_checked,
        "boundary_lineage_verified": boundary_lineage_verified,
        "implementation_hashes_verified": hashes_verified,
        "implementation_bundles": bundle_report,
        "fixture_attestation_verified": fixture_verified,
        "fixture_attestation_problems": fixture_problems,
        "readonly_postgresql_explain_attestation_verified": explain_verified,
        "readonly_postgresql_explain_attestation_problems": explain_problems,
        "freeze_ready": freeze_ready,
        "boundary_expectations": boundary_expectations,
        "bucket_count": config.get("bucket_plan", {}).get("bucket_count"),
        "boundary_statement_count": config.get("limits", {}).get(
            "boundary_statement_count"
        ),
        "total_scientific_statement_count": config.get("limits", {}).get(
            "total_scientific_statement_count"
        ),
        "semantic_seed_expected_keys": config.get("semantic_seed_lineage", {}).get(
            "expected_key_count"
        ),
        "semantic_seed_expected_sha256": config.get(
            "semantic_seed_lineage", {}
        ).get("expected_key_set_sha256"),
        "guards": dict(config.get("guards", {})),
        "formal_product_mapping_enabled": config.get(
            "formal_product_mapping_enabled"
        ),
        "formal_source_policy_enabled": config.get("formal_source_policy_enabled"),
    }


def build_fixture_attestation(
    root: Path,
    *,
    tests_run: int,
    test_command: str,
) -> dict[str, Any]:
    """Build the deterministic content that a successful fixture run may sign.

    The caller is responsible for running the tests and for writing the file.
    This helper never interprets a request to build content as proof tests ran.
    """
    if type(tests_run) is not int or tests_run != FIXTURE_TEST_COUNT:
        raise ValueError(f"tests_run must be exactly {FIXTURE_TEST_COUNT}")
    if test_command != FIXTURE_TEST_COMMAND:
        raise ValueError("test_command differs from the exact fixture command")
    config = read_potassium_query202_pre_adjudication_v2_preregistration(root)
    bundles = implementation_bundles(root, config)
    if any(item["missing"] for item in bundles.values()):
        raise ValueError("implementation bundles are incomplete")
    tests = config.get("fixture_gate", {}).get("required_test_paths", [])
    if tests != REQUIRED_TEST_PATHS:
        raise ValueError("required test paths differ from the exact fixture inventory")
    if (
        config.get("fixture_gate", {}).get("required_mutation_classes")
        != REQUIRED_MUTATION_CLASSES
    ):
        raise ValueError("required mutation classes differ from the exact fixture lock")
    test_files = []
    for relative in tests:
        if not _safe_relative(relative):
            raise ValueError("unsafe test path")
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError("required test file is absent")
        test_files.append({"path": relative, "file_sha256": _sha_file(path)})
    return {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "status": "passed",
        "test_command": test_command,
        "tests_run": tests_run,
        "failures": 0,
        "errors": 0,
        "scientific_contract_sha256": scientific_contract_sha256(config),
        "implementation_bundle_sha256": {
            name: item["bundle_sha256"] for name, item in bundles.items()
        },
        "test_files": test_files,
        "mutation_classes_passed": list(REQUIRED_MUTATION_CLASSES),
    }
