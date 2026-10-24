"""Independent offline audit for Query-202 pre-adjudication lifecycle A v2.

This module intentionally imports neither the database runner nor any of its
hashing, tuple, SQL-rendering, or preregistration helpers.  It reimplements the
byte contracts and validates saved artifacts without opening a database
connection.  Audit failures expose only fixed check names, never local values.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import tomllib
from typing import Any, Iterable, Iterator, Mapping
import zlib


QUERY_NAME = "potassium_query202_pre_adjudication"
AUDIT_NAME = "potassium_query202_pre_adjudication_offline_audit"
COMPONENT_ID = "D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2"
CONFIG_PATH = Path(
    "config/preregistrations/d005_potassium_query202_pre_adjudication_v2.toml"
)
BUCKET_COUNT = 64
STATEMENT_COUNT = 457
STATEMENT_TIMEOUT_MS = 120_000
PROCESS_TIMEOUT_SECONDS = 135
MAX_BOUNDARY_FRAME_BYTES = 256 * 1024 * 1024
MAX_CROSSWALK_FRAME_BYTES = 512 * 1024 * 1024
MAX_CUMULATIVE_RAW_FRAME_BYTES = 16 * 1024 * 1024 * 1024
MAX_CUMULATIVE_SPOOL_BYTES = 4 * 1024 * 1024 * 1024
MAX_MERGE_RUN_RAW_BYTES = 16 * 1024 * 1024 * 1024
MAX_MERGE_RUN_SPOOL_BYTES = 4 * 1024 * 1024 * 1024
MAX_PRIVATE_RAW_BYTES = 16 * 1024 * 1024 * 1024
MAX_PRIVATE_STORED_BYTES = 4 * 1024 * 1024 * 1024
MAX_PRIVATE_LINE_BYTES = 8 * 1024 * 1024
PRIVATE_ARTIFACT_ENCODING = "gzip+utf8+ndjson-v1"
MAX_EXECUTED_SQL_BYTES = 16 * 1024 * 1024
MAX_TUPLE_JSON_BYTES = 1024 * 1024
MAX_BOUNDARY_GROUPS = 1_000_000
MAX_TUPLE_GROUPS_PER_BUCKET = 5_000_000
MAX_COUNT = (1 << 63) - 1
MAX_JSON_BYTES = 128 * 1024 * 1024
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

BOUNDARY_SET_VERSION = b"typed-distinct-source-value-set-v1"
SEMANTIC_SET_VERSION = b"source-field-nonnull-exact-value-set-v1"
TUPLE_ENCODING_VERSION = b"query202-pre-adjudication-exact-typed-tuple-v1"
TUPLE_SET_VERSION = b"query202-pre-adjudication-tuple-set-v1"
TUPLE_FREQUENCY_VERSION = b"query202-pre-adjudication-tuple-frequency-v1"
BUNDLE_ENCODING = "uint32be_path_length+path_utf8+uint64be_content_length+content"
BUCKET_MARKER = "__BUCKET_INDEX__"
BUCKET_PREFIX = "D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2|"
BUCKET_VERSION = "d005-k-query202-preadjudication-subject-md5-v2"

SOURCE_KEYS = (
    "emar_medication",
    "detail_product_description",
    "pharmacy_medication",
    "prescription_drug",
    "detail_product_description_other",
    "emar_detail_route",
    "pharmacy_route",
    "prescriptions_route",
    "prescriptions_ndc",
)
SOURCE_FIELDS = (
    "mimiciv_hosp.emar.medication",
    "mimiciv_hosp.emar_detail.product_description",
    "mimiciv_hosp.pharmacy.medication",
    "mimiciv_hosp.prescriptions.drug",
    "mimiciv_hosp.emar_detail.product_description_other",
    "mimiciv_hosp.emar_detail.route",
    "mimiciv_hosp.pharmacy.route",
    "mimiciv_hosp.prescriptions.route",
    "mimiciv_hosp.prescriptions.ndc",
)
BOUNDARY_STAGES = tuple(f"202a{index}" for index in range(1, 10))
SEMANTIC_KEYS = frozenset(SOURCE_KEYS[:5])
NONNULL_COUNTS = (5045, 6692, 11059, 10927, 842, 17, 108, 108, 6589)
NONNULL_HASHES = (
    "f8bfd2a1c2d28ddd025bffad8e30f4ceec6d011398b4fa8bcd9958eeb5031845",
    "a88fb059e567bfe191c46615ba55e1c3e4f331093af2374d52a010b5d719fd59",
    "19e115fd0b35a6d9eb3985224c0593ae1813d7d6bffe64ef7874f2167f8a1630",
    "4767540954d4f661e9367600f4a890c75bfa54f03df22f62cc7e3287aef23815",
    "c58654e7a31bb9d30ed1a77751913aac4ea0e4ce89a4369c4317d15732b79b64",
    "82e5032b4e0b4f0114b0e3618028a9dc99118399ed27789a1dd6c068f4e89acc",
    "a4c620815db59fec1969dbc13e8134d30b0f38c2359eb5ea0ac3f217c7834839",
    "1f883ce55fa59f2e48c6bdd6fe6cc6dec185ed1513824f872213eb644e63b1ec",
    "0a83baa56732fb38fc0bf91db4e4d0d000de90fcc2c0439b1efdf1489857234d",
)
TYPED_HASHES = {
    "detail_product_description_other": (
        "0105f73cef307cc11b93e1d9d657d43a278c66c3c06ef31e5123db377e11dd4e",
        843,
    ),
    "emar_detail_route": (
        "a3b0d5664ae2e89f08df97f45347a6d7ae7761cdb2d138da781681ed2edd0ea9",
        18,
    ),
    "pharmacy_route": (
        "2dad858bbbd41002d3a417faa302bda9bd0f85111d47cbd075a0802886ebd76b",
        109,
    ),
    "prescriptions_route": (
        "b75209f1e0acea76a8c9818936b389a972def151317ede76073fc51dd65f1c0e",
        109,
    ),
    "prescriptions_ndc": (
        "10e5ff7bb578ca66aadfe274105ed94a53487ba05d7b80e0ebca8fb8c24bab9e",
        6590,
    ),
}
SEMANTIC_SEED_HASH = (
    "cee42c49d4618e6c62e99dcea26c53166f21305231b3c35991d2c2534b94368a"
)

BOUNDARY_SQL_PATHS = (
    "sql/profiling/202a1_potassium_query202_preadjudication_emar_medication_v2.sql",
    "sql/profiling/202a2_potassium_query202_preadjudication_detail_product_description_v2.sql",
    "sql/profiling/202a3_potassium_query202_preadjudication_pharmacy_medication_v2.sql",
    "sql/profiling/202a4_potassium_query202_preadjudication_prescription_drug_v2.sql",
    "sql/profiling/202a5_potassium_query202_preadjudication_detail_product_description_other_v2.sql",
    "sql/profiling/202a6_potassium_query202_preadjudication_emar_detail_route_v2.sql",
    "sql/profiling/202a7_potassium_query202_preadjudication_pharmacy_route_v2.sql",
    "sql/profiling/202a8_potassium_query202_preadjudication_prescriptions_route_v2.sql",
    "sql/profiling/202a9_potassium_query202_preadjudication_prescriptions_ndc_v2.sql",
)
BUCKET_STATEMENT_SPECS = (
    {
        "stage": "202b_context_seed",
        "logical_stage": "202b",
        "path": "sql/profiling/202b1_potassium_query202_preadjudication_context_seed_bucket_v2.sql",
        "tuple_kinds": ("detail_product_context", "detail_seed_membership_bridge"),
        "bucket_input_source": "mimiciv_hosp.emar_detail",
    },
    {
        "stage": "202b_detail_head_bridge",
        "logical_stage": "202b",
        "path": "sql/profiling/202b2_potassium_query202_preadjudication_detail_head_bridge_bucket_v2.sql",
        "tuple_kinds": ("emar_medication_detail_bridge",),
        "bucket_input_source": None,
    },
    {
        "stage": "202b_head_partition",
        "logical_stage": "202b",
        "path": "sql/profiling/202b3_potassium_query202_preadjudication_head_partition_bucket_v2.sql",
        "tuple_kinds": ("emar_medication_head_partition",),
        "bucket_input_source": None,
    },
    {
        "stage": "202c_pharmacy_context",
        "logical_stage": "202c",
        "path": "sql/profiling/202c1_potassium_query202_preadjudication_pharmacy_context_bucket_v2.sql",
        "tuple_kinds": ("pharmacy_product_context", "pharmacy_no_prescription_component"),
        "bucket_input_source": "mimiciv_hosp.pharmacy",
    },
    {
        "stage": "202c_prescription_context",
        "logical_stage": "202c",
        "path": "sql/profiling/202c2_potassium_query202_preadjudication_prescription_context_bucket_v2.sql",
        "tuple_kinds": (
            "prescription_identifier_context",
            "pharmacy_prescription_bridge",
            "ndc_external_mapping_input",
        ),
        "bucket_input_source": "mimiciv_hosp.prescriptions",
    },
    {
        "stage": "202c_head_bridge",
        "logical_stage": "202c",
        "path": "sql/profiling/202c3_potassium_query202_preadjudication_head_bridge_bucket_v2.sql",
        "tuple_kinds": ("head_pharmacy_prescription_bridge",),
        "bucket_input_source": "mimiciv_hosp.emar",
    },
    {
        "stage": "202c_detail_bridge",
        "logical_stage": "202c",
        "path": "sql/profiling/202c4_potassium_query202_preadjudication_detail_bridge_bucket_v2.sql",
        "tuple_kinds": ("detail_pharmacy_prescription_bridge",),
        "bucket_input_source": "mimiciv_hosp.emar_detail",
    },
)
SQL_PATHS = BOUNDARY_SQL_PATHS + tuple(
    item["path"] for item in BUCKET_STATEMENT_SPECS
)
RUNNER_PATHS = (
    "src/april_repro/query202_preadjudication_sql_v2.py",
    "src/april_repro/query202_pre_adjudication.py",
    "scripts/run_potassium_query202_pre_adjudication.py",
    "src/april_repro/database.py",
    "src/april_repro/staged_source_closure.py",
    "src/april_repro/query202_readonly_explain_attestation.py",
    "scripts/attest_potassium_query202_pre_adjudication_explain.py",
)
AUDITOR_PATHS = (
    "src/april_repro/query202_pre_adjudication_preregistration_v2.py",
    "src/april_repro/query202_pre_adjudication_audit.py",
    "scripts/audit_potassium_query202_pre_adjudication.py",
)
BUNDLE_PATHS = {
    "sql": SQL_PATHS,
    "runner": RUNNER_PATHS,
    "offline_auditor": AUDITOR_PATHS,
}
EXPLAIN_ATTESTER_PATHS = (
    "src/april_repro/query202_readonly_explain_attestation.py",
    "scripts/attest_potassium_query202_pre_adjudication_explain.py",
    "src/april_repro/database.py",
    "src/april_repro/staged_source_closure.py",
    "src/april_repro/query202_pre_adjudication.py",
    "src/april_repro/query202_preadjudication_sql_v2.py",
)
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
REQUIRED_TEST_PATHS = (
    "tests/test_query202_pre_adjudication_preregistration_v2.py",
    "tests/test_query202_preadjudication_sql_v2.py",
    "tests/test_query202_pre_adjudication.py",
    "tests/test_query202_pre_adjudication_audit_v2.py",
    "tests/test_query202_readonly_explain_attestation.py",
)
FIXTURE_TEST_COMMAND = (
    "PYTHONPATH=src:. .venv/bin/python -m unittest "
    "tests.test_query202_pre_adjudication_preregistration_v2 "
    "tests.test_query202_preadjudication_sql_v2 "
    "tests.test_query202_pre_adjudication "
    "tests.test_query202_pre_adjudication_audit_v2 "
    "tests.test_query202_readonly_explain_attestation -v"
)
FIXTURE_TEST_COUNT = 59
REQUIRED_MUTATION_CLASSES = (
    "timeout_or_nonzero_exit",
    "rollback_or_snapshot_drift",
    "missing_duplicate_or_cross_bucket",
    "boundary_set_or_seed_drift",
    "tuple_or_multiplicity_tamper",
    "lineage_or_limit_tamper",
    "permission_or_gitignore_tamper",
    "public_privacy_leak",
    "implementation_bundle_drift",
)
FIXTURE_ATTESTATION_KEYS = frozenset({
    "schema_version", "component_id", "status", "test_command",
    "tests_run", "failures", "errors", "scientific_contract_sha256",
    "implementation_bundle_sha256", "test_files",
    "mutation_classes_passed",
})
FIXTURE_TEST_FILE_KEYS = frozenset({"path", "file_sha256"})

DETAIL_CONTEXT_FIELDS = (
    "row_role", "parent_field_ordinal", "administration_type",
    "complete_dose_not_given", "dose_due", "dose_due_unit", "dose_given",
    "dose_given_unit", "will_remainder_of_dose_be_given",
    "product_amount_given", "product_unit", "product_code",
    "product_description", "product_description_other", "prior_infusion_rate",
    "route", "infusion_rate", "infusion_rate_adjustment",
    "infusion_rate_adjustment_amount", "infusion_rate_unit",
    "infusion_complete", "completion_interval", "new_iv_bag_hung",
    "continued_infusion_in_other_location", "restart_interval",
    "non_formulary_visual_verification",
)
DETAIL_BRIDGE_FIELDS = (
    "head_medication", "detail_head_identity_state", "detail_match_state",
    "row_role", "parent_field_ordinal", "administration_type",
    "product_description", "product_description_other", "product_code", "route",
    "dose_due_unit", "dose_given_unit", "product_unit", "infusion_rate_unit",
)
PHARMACY_CONTEXT_FIELDS = (
    "medication", "proc_type", "status", "route", "frequency", "disp_sched",
    "infusion_type", "sliding_scale", "lockout_interval", "basal_rate",
    "one_hr_max", "doses_per_24_hrs", "duration", "duration_interval",
    "expiration_value", "expiration_unit", "dispensation", "fill_quantity",
)
PRESCRIPTION_CONTEXT_FIELDS = (
    "drug_type", "drug", "formulary_drug_cd", "gsn", "ndc", "prod_strength",
    "form_rx", "dose_val_rx", "dose_unit_rx", "form_val_disp",
    "form_unit_disp", "doses_per_24_hrs", "route",
)
TUPLE_FIELDS = {
    "202b": {
        "detail_product_context": DETAIL_CONTEXT_FIELDS,
        "detail_seed_membership_bridge": (
            *DETAIL_CONTEXT_FIELDS, "seed_source_field", "seed_exact_raw_value"
        ),
        "emar_medication_detail_bridge": DETAIL_BRIDGE_FIELDS,
        "emar_medication_head_partition": (
            "head_medication", "detail_match_state"
        ),
    },
    "202c": {
        "pharmacy_product_context": PHARMACY_CONTEXT_FIELDS,
        "prescription_identifier_context": PRESCRIPTION_CONTEXT_FIELDS,
        "pharmacy_prescription_bridge": (
            "link_identity_state", "poe_auxiliary_state", "pharmacy_medication",
            "pharmacy_route", *PRESCRIPTION_CONTEXT_FIELDS,
        ),
        "pharmacy_no_prescription_component": (
            *PHARMACY_CONTEXT_FIELDS, "prescription_match_state"
        ),
        "head_pharmacy_prescription_bridge": (
            "link_identity_state", "poe_auxiliary_state", "head_medication",
            "pharmacy_medication", "pharmacy_route", *PRESCRIPTION_CONTEXT_FIELDS,
        ),
        "detail_pharmacy_prescription_bridge": (
            "link_identity_state", "poe_auxiliary_state", "row_role",
            "parent_field_ordinal", "product_description",
            "product_description_other", "product_code", "detail_route",
            "dose_due_unit", "dose_given_unit", "product_unit",
            "infusion_rate_unit", "pharmacy_medication", "pharmacy_route",
            *PRESCRIPTION_CONTEXT_FIELDS,
        ),
        "ndc_external_mapping_input": PRESCRIPTION_CONTEXT_FIELDS,
    },
}

# Independent copy of every implementation-created categorical value.  Local
# clinical text remains unconstrained; these labels are part of the frozen
# extraction contract and must never drift silently in a private artifact.
TUPLE_VALUE_ENUMS = {
    ("202b", "detail_product_context", "row_role"): ("parent", "product"),
    ("202b", "detail_seed_membership_bridge", "row_role"): ("parent", "product"),
    ("202b", "detail_seed_membership_bridge", "seed_source_field"): (
        "mimiciv_hosp.emar_detail.product_description",
        "mimiciv_hosp.emar_detail.product_description_other",
    ),
    ("202b", "emar_medication_detail_bridge", "detail_head_identity_state"): (
        "missing", "conflict", "exact",
    ),
    ("202b", "emar_medication_detail_bridge", "detail_match_state"): (
        "with_detail",
    ),
    ("202b", "emar_medication_detail_bridge", "row_role"): ("parent", "product"),
    ("202b", "emar_medication_head_partition", "detail_match_state"): (
        "no_detail",
        "with_detail_exact_only",
        "with_detail_identity_missing_only",
        "with_detail_identity_conflict_only",
        "with_detail_exact_and_identity_missing",
        "with_detail_exact_and_identity_conflict",
        "with_detail_identity_missing_and_conflict",
        "with_detail_exact_identity_missing_and_conflict",
    ),
    ("202c", "pharmacy_prescription_bridge", "link_identity_state"): (
        "pharmacy_missing", "subject_missing", "subject_conflict",
        "hadm_missing", "hadm_conflict", "exact",
    ),
    ("202c", "pharmacy_prescription_bridge", "poe_auxiliary_state"): (
        "missing", "conflict", "exact",
    ),
    ("202c", "pharmacy_no_prescription_component", "prescription_match_state"): (
        "no_prescription_component",
    ),
    ("202c", "head_pharmacy_prescription_bridge", "link_identity_state"): (
        "pharmacy_missing", "prescription_missing",
        "pharmacy_subject_missing", "pharmacy_subject_conflict",
        "prescription_subject_missing", "prescription_subject_conflict",
        "pharmacy_hadm_missing", "pharmacy_hadm_conflict",
        "prescription_hadm_missing", "prescription_hadm_conflict", "exact",
    ),
    ("202c", "head_pharmacy_prescription_bridge", "poe_auxiliary_state"): (
        "missing", "conflict", "exact",
    ),
    ("202c", "detail_pharmacy_prescription_bridge", "link_identity_state"): (
        "pharmacy_missing", "prescription_missing",
        "pharmacy_subject_missing", "pharmacy_subject_conflict",
        "prescription_subject_missing", "prescription_subject_conflict",
        "hadm_missing", "hadm_conflict", "exact",
    ),
    ("202c", "detail_pharmacy_prescription_bridge", "poe_auxiliary_state"): (
        "missing", "conflict", "exact",
    ),
    ("202c", "detail_pharmacy_prescription_bridge", "row_role"): (
        "parent", "product",
    ),
}
ENUM_FIELDS_BY_KIND: dict[tuple[str, str], dict[str, tuple[str, ...]]] = {}
for (enum_stage, enum_kind, enum_field), enum_values in TUPLE_VALUE_ENUMS.items():
    ENUM_FIELDS_BY_KIND.setdefault((enum_stage, enum_kind), {})[enum_field] = enum_values
CONTROL_NAMES = {
    stage: (
        "bucket_assignment_violations",
        "null_subject_outside_bucket_zero",
        "bucket_input_rows",
        "bucket_output_multiplicity",
        *(
            name
            for kind in TUPLE_FIELDS[stage]
            for name in (f"{kind}_input_rows", f"{kind}_tuple_multiplicity")
        ),
    )
    for stage in ("202b", "202c")
}


def _physical_control_names(spec: Mapping[str, Any]) -> tuple[str, ...]:
    """Independent exact control inventory for one physical bucket statement."""
    source_controls = (
        (
            "bucket_assignment_violations",
            "null_subject_outside_bucket_zero",
            "bucket_input_rows",
        )
        if spec["bucket_input_source"] is not None
        else ()
    )
    return (
        *source_controls,
        "bucket_output_multiplicity",
        *(
            name
            for kind in spec["tuple_kinds"]
            for name in (f"{kind}_input_rows", f"{kind}_tuple_multiplicity")
        ),
    )


PHYSICAL_CONTROL_NAMES = {
    spec["stage"]: _physical_control_names(spec)
    for spec in BUCKET_STATEMENT_SPECS
}
BUCKET_STATEMENT_BY_STAGE = {
    spec["stage"]: spec for spec in BUCKET_STATEMENT_SPECS
}
BUCKET_STATEMENTS_BY_LOGICAL_STAGE = {
    logical_stage: tuple(
        spec
        for spec in BUCKET_STATEMENT_SPECS
        if spec["logical_stage"] == logical_stage
    )
    for logical_stage in ("202b", "202c")
}
INPUT_SOURCE_BOUNDARY_KEY = {
    "mimiciv_hosp.emar": "emar_medication",
    "mimiciv_hosp.emar_detail": "detail_product_description",
    "mimiciv_hosp.pharmacy": "pharmacy_medication",
    "mimiciv_hosp.prescriptions": "prescription_drug",
}

COMMON_STAGE_KEYS = frozenset({
    "stage", "file", "bucket_index", "status", "rows",
    "statement_timeout_ms", "process_timeout_seconds", "template_sha256",
    "template_bytes", "control_sha256", "control_bytes", "elapsed_seconds",
    "frame_bytes", "spool_bytes", "observed_transaction_isolation",
    "observed_transaction_read_only", "observed_snapshot_sha256",
})
BOUNDARY_STAGE_KEYS = COMMON_STAGE_KEYS | {
    "source_rows", "typed_set_sha256",
}
PHYSICAL_BUCKET_STAGE_KEYS = COMMON_STAGE_KEYS | {
    "rendered_statement_sha256", "tuple_multiplicity",
}
PHYSICAL_BUCKET_OWNER_STAGE_KEYS = PHYSICAL_BUCKET_STAGE_KEYS | {
    "bucket_assignment_violations", "null_subject_outside_bucket_zero",
    "bucket_input_rows",
}

FALSE_GUARDS = (
    "pre_adjudication_extraction_implemented", "pre_adjudication_extraction_executed",
    "reviewed_semantic_ledger_frozen", "route_mapping_frozen",
    "external_ndc_mapping_executed", "event_mapping_created",
    "product_identity_decided", "product_mapping_accepted", "final_source_policy",
    "complete_intervention_coverage", "formal_action", "formal_episode",
    "zero_action_constructed", "formal_non_icu_rule", "formal_label",
    "formal_cohort", "patient_data_exported", "llm_called",
)
FORBIDDEN_TUPLE_FIELDS = {
    "subject_id", "hadm_id", "stay_id", "emar_id", "emar_seq", "pharmacy_id",
    "poe_id", "poe_seq", "order_id", "charttime", "scheduletime", "storetime",
    "entertime", "starttime", "stoptime", "endtime",
}
FORBIDDEN_PUBLIC_KEYS = FORBIDDEN_TUPLE_FIELDS | {
    "raw_value", "raw_value_base64", "tuple", "tuple_json_base64", "records",
    "snapshot_token", "per_value_hash", "per_tuple_hash",
}


class AuditContractError(RuntimeError):
    """A value-safe audit failure identified only by a fixed check name."""


class Checks:
    def __init__(self) -> None:
        self.total = 0
        self.by_category: Counter[str] = Counter()
        self.failed: list[str] = []

    def require(self, condition: bool, name: str) -> None:
        self.total += 1
        self.by_category[name.split(".", 1)[0]] += 1
        if not condition:
            if name not in self.failed:
                self.failed.append(name)
            raise AuditContractError(name)

    def check(self, condition: bool, name: str) -> None:
        self.total += 1
        self.by_category[name.split(".", 1)[0]] += 1
        if not condition and name not in self.failed:
            self.failed.append(name)


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mode(path: Path) -> str:
    return format(stat.S_IMODE(path.stat().st_mode), "04o")


def _read_json(path: Path, limit: int, label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink():
        raise AuditContractError(label + ".regular_file")
    size = path.stat().st_size
    if not 0 < size <= limit:
        raise AuditContractError(label + ".byte_limit")
    payload = path.read_bytes()

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AuditContractError(label + ".duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(_: str) -> Any:
        raise AuditContractError(label + ".nonfinite_json_number")

    try:
        value = json.loads(
            payload,
            object_pairs_hook=unique,
            parse_constant=invalid_constant,
        )
    except AuditContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditContractError(label + ".valid_json") from exc
    if not isinstance(value, dict):
        raise AuditContractError(label + ".object")
    return value, payload


def _safe_filename(directory: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or Path(value).name != value or value in {"", ".", ".."}:
        raise AuditContractError(label + ".safe_filename")
    path = directory / value
    if not path.is_file() or path.is_symlink():
        raise AuditContractError(label + ".regular_file")
    return path


def _safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and str(path) == value


def _write_private(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _bundle(root: Path, paths: tuple[str, ...]) -> dict[str, Any]:
    digest = hashlib.sha256()
    files: list[dict[str, Any]] = []
    for index, relative in enumerate(paths):
        if not _safe_relative(relative):
            raise AuditContractError(f"bundle.path_{index}.safe")
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise AuditContractError(f"bundle.path_{index}.regular_file")
        path_bytes = relative.encode("utf-8")
        content = path.read_bytes()
        digest.update(struct.pack(">I", len(path_bytes)))
        digest.update(path_bytes)
        digest.update(struct.pack(">Q", len(content)))
        digest.update(content)
        files.append({
            "path": relative,
            "bytes": len(content),
            "file_sha256": _sha_bytes(content),
        })
    return {
        "paths": list(paths),
        "bundle_sha256": digest.hexdigest(),
        "files": files,
        "encoding": BUNDLE_ENCODING,
    }


def implementation_bundles(root: Path) -> dict[str, dict[str, Any]]:
    return {name: _bundle(root, paths) for name, paths in BUNDLE_PATHS.items()}


def _finite_nonnegative(value: Any, maximum: float | None = None) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    number = float(value)
    return math.isfinite(number) and number >= 0 and (
        maximum is None or number <= maximum
    )


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed


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


def _expected_explain_metadata(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    statements: list[dict[str, Any]] = []
    rendered: list[dict[str, Any]] = []
    for index, relative in enumerate(SQL_PATHS):
        raw = (root / relative).read_bytes()
        template = raw.decode("utf-8")
        bucket_index = None if index < 9 else 0
        if bucket_index is not None:
            if template.count(BUCKET_MARKER) != 1:
                raise AuditContractError("explain.bucket_marker")
            template = template.replace(BUCKET_MARKER, "0")
        body = _statement_body(template)
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
            "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        })
        rendered.append({
            "ordinal": index,
            "path": relative,
            "rendered_bucket_index": bucket_index,
            "rendered_statement_sha256": _sha_bytes(body.encode("utf-8")),
            "explain_control_sha256": _sha_bytes(control),
        })
    return statements, rendered


def _typed_hash(field: str, records: list[Mapping[str, Any]]) -> str:
    field_bytes = field.encode("utf-8")
    null_seen = False
    values: list[bytes] = []
    for record in records:
        if record.get("raw_is_null") is True and record.get("raw_value") is None:
            if null_seen:
                raise AuditContractError("boundary.duplicate_null")
            null_seen = True
        elif record.get("raw_is_null") is False and isinstance(record.get("raw_value"), str):
            values.append(record["raw_value"].encode("utf-8"))
        else:
            raise AuditContractError("boundary.typed_state")
    if len(values) != len(set(values)):
        raise AuditContractError("boundary.duplicate_nonnull")
    values.sort()
    digest = hashlib.sha256(BOUNDARY_SET_VERSION)
    digest.update(struct.pack(">I", len(field_bytes)))
    digest.update(field_bytes)
    digest.update(struct.pack(">Q", len(values) + int(null_seen)))
    if null_seen:
        digest.update(b"\x00")
    for value in values:
        digest.update(b"\x01")
        digest.update(struct.pack(">Q", len(value)))
        digest.update(value)
    return digest.hexdigest()


def _nonnull_hash(field: str, records: list[Mapping[str, Any]]) -> str:
    field_bytes = field.encode("utf-8")
    values = sorted(
        record["raw_value"].encode("utf-8")
        for record in records
        if record.get("raw_is_null") is False
    )
    if len(values) != len(set(values)):
        raise AuditContractError("boundary.duplicate_nonnull")
    digest = hashlib.sha256(SEMANTIC_SET_VERSION)
    digest.update(struct.pack(">Q", len(values)))
    for value in values:
        digest.update(struct.pack(">I", len(field_bytes)))
        digest.update(field_bytes)
        digest.update(struct.pack(">Q", len(value)))
        digest.update(value)
    return digest.hexdigest()


def _seed_records(
    boundaries: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, str]]:
    keys: list[tuple[bytes, bytes]] = []
    for key, field in zip(SOURCE_KEYS[:5], SOURCE_FIELDS[:5], strict=True):
        for record in boundaries[key]["records"]:
            if record["raw_is_null"] is False:
                keys.append((field.encode("utf-8"), record["raw_value"].encode("utf-8")))
    keys.sort()
    if len(keys) != len(set(keys)):
        raise AuditContractError("seed.duplicate_key")
    return [
        {
            "source_field": field.decode("utf-8"),
            "exact_raw_value": value.decode("utf-8"),
        }
        for field, value in keys
    ]


def _seed_hash(boundaries: Mapping[str, Mapping[str, Any]]) -> tuple[int, str]:
    records = _seed_records(boundaries)
    digest = hashlib.sha256(SEMANTIC_SET_VERSION)
    digest.update(struct.pack(">Q", len(records)))
    for record in records:
        field = record["source_field"].encode("utf-8")
        value = record["exact_raw_value"].encode("utf-8")
        digest.update(struct.pack(">I", len(field)))
        digest.update(field)
        digest.update(struct.pack(">Q", len(value)))
        digest.update(value)
    return len(records), digest.hexdigest()


def _encode_tuple(stage: str, kind: str, value: Mapping[str, str | None]) -> bytes:
    output = bytearray(TUPLE_ENCODING_VERSION)
    for label in (stage, kind):
        encoded = label.encode("utf-8")
        output.extend(struct.pack(">I", len(encoded)))
        output.extend(encoded)
    items = sorted(value.items(), key=lambda item: item[0].encode("utf-8"))
    output.extend(struct.pack(">I", len(items)))
    for field, raw in items:
        field_bytes = field.encode("utf-8")
        output.extend(struct.pack(">I", len(field_bytes)))
        output.extend(field_bytes)
        output.extend(struct.pack(">H", 4))
        output.extend(b"text")
        if raw is None:
            output.extend(b"\x00")
        else:
            raw_bytes = raw.encode("utf-8")
            output.extend(b"\x01")
            output.extend(struct.pack(">Q", len(raw_bytes)))
            output.extend(raw_bytes)
    return bytes(output)


def _tuple_hashes(stage: str, records: list[Mapping[str, Any]]) -> tuple[str, str]:
    set_digest = hashlib.sha256(TUPLE_SET_VERSION)
    frequency_digest = hashlib.sha256(TUPLE_FREQUENCY_VERSION)
    stage_bytes = stage.encode("utf-8")
    for digest in (set_digest, frequency_digest):
        digest.update(struct.pack(">I", len(stage_bytes)))
        digest.update(stage_bytes)
        digest.update(struct.pack(">Q", len(records)))
    for record in records:
        encoded = record["encoded_tuple"]
        set_digest.update(struct.pack(">Q", len(encoded)))
        set_digest.update(encoded)
        frequency_digest.update(struct.pack(">Q", len(encoded)))
        frequency_digest.update(encoded)
        frequency_digest.update(struct.pack(">Q", record["multiplicity"]))
    return set_digest.hexdigest(), frequency_digest.hexdigest()


def _public_strings(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            result.add(str(key))
            result.update(_public_strings(item))
    elif isinstance(value, list):
        for item in value:
            result.update(_public_strings(item))
    elif isinstance(value, str):
        result.add(value)
    return result


class _PrivateNdjsonReader:
    """One-pass, independently bounded gzip/NDJSON reader."""

    _IO_CHUNK_BYTES = 1024 * 1024

    def __init__(self, path: Path):
        if not path.is_file() or path.is_symlink():
            raise AuditContractError("private.regular_file")
        self.path = path
        self.stored_bytes = path.stat().st_size
        if not 0 < self.stored_bytes <= MAX_PRIVATE_STORED_BYTES:
            raise AuditContractError("private.stored_byte_limit")
        self.stored_sha256 = hashlib.sha256()
        self.raw_bytes = 0
        self.raw_sha256 = hashlib.sha256()
        self.records = 0
        self._started = False

    @staticmethod
    def _decode_record(line: bytes) -> dict[str, Any]:
        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            value: dict[str, Any] = {}
            for key, item in pairs:
                if key in value:
                    raise AuditContractError("private.duplicate_json_key")
                value[key] = item
            return value

        def invalid_constant(_: str) -> Any:
            raise AuditContractError("private.nonfinite_json_number")

        try:
            value = json.loads(
                line,
                object_pairs_hook=unique,
                parse_constant=invalid_constant,
            )
        except AuditContractError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise AuditContractError("private.valid_ndjson") from exc
        if not isinstance(value, dict):
            raise AuditContractError("private.record_object")
        return value

    def __iter__(self) -> Iterator[dict[str, Any]]:
        if self._started:
            raise AuditContractError("private.single_pass")
        self._started = True
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        buffer = bytearray()
        observed_stored = 0

        def consume(chunk: bytes) -> list[dict[str, Any]]:
            if not chunk:
                return []
            if (
                len(chunk) > MAX_PRIVATE_RAW_BYTES
                or self.raw_bytes > MAX_PRIVATE_RAW_BYTES - len(chunk)
            ):
                raise AuditContractError("private.raw_byte_limit")
            self.raw_bytes += len(chunk)
            self.raw_sha256.update(chunk)
            buffer.extend(chunk)
            output: list[dict[str, Any]] = []
            consumed = 0
            while True:
                newline = buffer.find(b"\n", consumed)
                if newline < 0:
                    if len(buffer) - consumed >= MAX_PRIVATE_LINE_BYTES:
                        raise AuditContractError("private.line_byte_limit")
                    break
                line = bytes(buffer[consumed:newline])
                consumed = newline + 1
                if not line or len(line) + 1 > MAX_PRIVATE_LINE_BYTES:
                    raise AuditContractError("private.line_byte_limit")
                output.append(self._decode_record(line))
            if consumed:
                del buffer[:consumed]
            return output

        try:
            with self.path.open("rb") as handle:
                while True:
                    compressed = handle.read(self._IO_CHUNK_BYTES)
                    if not compressed:
                        break
                    if decompressor.eof:
                        raise AuditContractError("private.trailing_compressed_data")
                    observed_stored += len(compressed)
                    if observed_stored > MAX_PRIVATE_STORED_BYTES:
                        raise AuditContractError("private.stored_byte_limit")
                    self.stored_sha256.update(compressed)
                    pending = compressed
                    while pending:
                        output = decompressor.decompress(
                            pending, self._IO_CHUNK_BYTES
                        )
                        pending = decompressor.unconsumed_tail
                        for record in consume(output):
                            self.records += 1
                            yield record
                        if decompressor.unused_data:
                            raise AuditContractError(
                                "private.trailing_compressed_data"
                            )
                        if decompressor.eof:
                            if pending:
                                raise AuditContractError(
                                    "private.trailing_compressed_data"
                                )
                            break
            if observed_stored != self.stored_bytes:
                raise AuditContractError("private.stored_size_changed")
            if not decompressor.eof:
                raise AuditContractError("private.truncated_gzip")
            flushed = decompressor.flush(self._IO_CHUNK_BYTES)
            if len(flushed) == self._IO_CHUNK_BYTES:
                raise AuditContractError("private.oversized_gzip_tail")
            for record in consume(flushed):
                self.records += 1
                yield record
        except zlib.error as exc:
            raise AuditContractError("private.valid_gzip") from exc
        if buffer:
            raise AuditContractError("private.incomplete_ndjson_line")


class _PrivateRecordCursor:
    def __init__(self, reader: _PrivateNdjsonReader):
        self.reader = reader
        self._iterator = iter(reader)

    def take(self, record_type: str) -> dict[str, Any]:
        try:
            record = next(self._iterator)
        except StopIteration as exc:
            raise AuditContractError("private.truncated_record_stream") from exc
        if record.get("record_type") != record_type:
            raise AuditContractError("private.record_state_" + record_type)
        return record

    def finish(self) -> None:
        try:
            next(self._iterator)
        except StopIteration:
            return
        raise AuditContractError("private.records_after_footer")


def _exact_record_keys(
    value: Any, expected: set[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise AuditContractError(label)
    return value


def _strict_json_equal(observed: Any, expected: Any) -> bool:
    """JSON equality that does not equate booleans with integers."""
    if type(observed) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(observed) == set(expected) and all(
            _strict_json_equal(observed[key], item)
            for key, item in expected.items()
        )
    if isinstance(expected, list):
        return len(observed) == len(expected) and all(
            _strict_json_equal(left, right)
            for left, right in zip(observed, expected, strict=True)
        )
    return observed == expected


def _new_stream_tuple_hashers(stage: str, count: int) -> tuple[Any, Any]:
    stage_bytes = stage.encode("utf-8")
    set_digest = hashlib.sha256(TUPLE_SET_VERSION)
    frequency_digest = hashlib.sha256(TUPLE_FREQUENCY_VERSION)
    for digest in (set_digest, frequency_digest):
        digest.update(struct.pack(">I", len(stage_bytes)))
        digest.update(stage_bytes)
        digest.update(struct.pack(">Q", count))
    return set_digest, frequency_digest


def _update_stream_tuple_hashers(
    hashers: tuple[Any, Any], encoded: bytes, multiplicity: int
) -> None:
    set_digest, frequency_digest = hashers
    set_digest.update(struct.pack(">Q", len(encoded)))
    set_digest.update(encoded)
    frequency_digest.update(struct.pack(">Q", len(encoded)))
    frequency_digest.update(encoded)
    frequency_digest.update(struct.pack(">Q", multiplicity))


def _stream_private_artifact(
    path: Path,
    entry: Mapping[str, Any],
    public_strings: set[str],
    checks: Checks,
) -> dict[str, Any]:
    """Validate the complete private record protocol with bounded memory."""
    reader = _PrivateNdjsonReader(path)
    cursor = _PrivateRecordCursor(reader)
    header = _exact_record_keys(cursor.take("header"), {
        "record_type", "artifact_encoding", "schema_version", "query",
        "created_at_utc", "component_lineage", "transaction",
        "hash_contracts", "privacy", "guards",
    }, "private.header_schema")
    checks.require(
        header.get("artifact_encoding") == PRIVATE_ARTIFACT_ENCODING,
        "private.encoding",
    )
    checks.require(
        type(header.get("schema_version")) is int
        and header.get("schema_version") == 2
        and type(header.get("query")) is str
        and header.get("query") == QUERY_NAME,
        "private.identity",
    )
    checks.require(_parse_utc(header.get("created_at_utc")) is not None,
                   "private.created_at_utc")
    private: dict[str, Any] = {
        key: header[key]
        for key in (
            "schema_version", "query", "created_at_utc", "component_lineage",
            "transaction", "hash_contracts", "privacy", "guards",
        )
    }
    boundaries: dict[str, dict[str, Any]] = {}
    boundary_summary: dict[str, dict[str, Any]] = {}
    expected_seed: list[tuple[bytes, bytes]] = []
    private_value_leaked = False
    boundary_value_records = 0
    metadata_keys = {
        "stage", "source_field", "semantic_seed_field", "sql_null_rows",
        "typed_distinct_values", "nonnull_distinct_values", "source_rows",
        "nonnull_set_sha256", "typed_set_sha256",
    }
    value_keys = {
        "raw_is_null", "raw_value", "raw_utf8_bytes", "exact_row_count"
    }
    for index, (key, field, stage) in enumerate(
        zip(SOURCE_KEYS, SOURCE_FIELDS, BOUNDARY_STAGES, strict=True)
    ):
        begin = _exact_record_keys(cursor.take("boundary_begin"), {
            "record_type", "source_key", "metadata",
        }, f"boundary.{key}_begin_schema")
        if begin.get("source_key") != key:
            raise AuditContractError(f"boundary.{key}_stream_order")
        metadata = _exact_record_keys(
            begin.get("metadata"), metadata_keys, f"boundary.{key}_schema"
        )
        checks.require(
            metadata.get("stage") == stage
            and metadata.get("source_field") == field,
            f"boundary.{key}_identity",
        )
        checks.require(
            metadata.get("semantic_seed_field") is (key in SEMANTIC_KEYS),
            f"boundary.{key}_semantic_role",
        )
        typed_count = metadata.get("typed_distinct_values")
        declared_nonnull = metadata.get("nonnull_distinct_values")
        declared_null_rows = metadata.get("sql_null_rows")
        declared_source_rows = metadata.get("source_rows")
        if (
            type(typed_count) is not int
            or not 0 <= typed_count <= MAX_BOUNDARY_GROUPS + 1
            or type(declared_nonnull) is not int
            or not 0 <= declared_nonnull <= MAX_BOUNDARY_GROUPS
            or type(declared_null_rows) is not int
            or not 0 <= declared_null_rows <= MAX_COUNT
            or type(declared_source_rows) is not int
            or not 0 <= declared_source_rows <= MAX_COUNT
        ):
            raise AuditContractError(f"boundary.{key}_declared_counts")
        field_bytes = field.encode("utf-8")
        typed_digest = hashlib.sha256(BOUNDARY_SET_VERSION)
        typed_digest.update(struct.pack(">I", len(field_bytes)))
        typed_digest.update(field_bytes)
        typed_digest.update(struct.pack(">Q", typed_count))
        nonnull_digest = hashlib.sha256(SEMANTIC_SET_VERSION)
        nonnull_digest.update(struct.pack(">Q", declared_nonnull))
        previous: tuple[bool, bytes] | None = None
        source_rows = 0
        null_rows = 0
        nonnull = 0
        for record_index in range(typed_count):
            wrapper = _exact_record_keys(cursor.take("boundary_value"), {
                "record_type", "source_key", "value",
            }, f"boundary.{key}_value_schema")
            if wrapper.get("source_key") != key:
                raise AuditContractError(f"boundary.{key}_value_source")
            value = _exact_record_keys(
                wrapper.get("value"), value_keys,
                f"boundary.{key}_record_schema",
            )
            count = value.get("exact_row_count")
            if type(count) is not int or not 1 <= count <= MAX_COUNT:
                raise AuditContractError(f"boundary.{key}_record_count")
            raw = value.get("raw_value")
            is_null = value.get("raw_is_null")
            byte_count = value.get("raw_utf8_bytes")
            if (
                type(byte_count) is not int
                or not 0 <= byte_count <= MAX_TUPLE_JSON_BYTES
            ):
                raise AuditContractError(f"boundary.{key}_record_bytes")
            if is_null is True:
                if raw is not None or byte_count != 0:
                    raise AuditContractError(f"boundary.{key}_record_null")
                order_key = (False, b"")
                typed_digest.update(b"\x00")
                null_rows += count
            elif is_null is False and isinstance(raw, str):
                raw_bytes = raw.encode("utf-8")
                if b"\x00" in raw_bytes or byte_count != len(raw_bytes):
                    raise AuditContractError(f"boundary.{key}_record_bytes")
                order_key = (True, raw_bytes)
                typed_digest.update(b"\x01")
                typed_digest.update(struct.pack(">Q", len(raw_bytes)))
                typed_digest.update(raw_bytes)
                nonnull_digest.update(struct.pack(">I", len(field_bytes)))
                nonnull_digest.update(field_bytes)
                nonnull_digest.update(struct.pack(">Q", len(raw_bytes)))
                nonnull_digest.update(raw_bytes)
                nonnull += 1
                if key in SEMANTIC_KEYS:
                    expected_seed.append((field_bytes, raw_bytes))
                if len(raw) >= 12 and raw in public_strings:
                    private_value_leaked = True
            else:
                raise AuditContractError(f"boundary.{key}_record_typed")
            if previous is not None and order_key <= previous:
                raise AuditContractError(f"boundary.{key}_sort")
            previous = order_key
            if source_rows > MAX_COUNT - count:
                raise AuditContractError(f"boundary.{key}_source_rows_limit")
            source_rows += count
            boundary_value_records += 1
        end = _exact_record_keys(cursor.take("boundary_end"), {
            "record_type", "records", "source_key",
        }, f"boundary.{key}_end_schema")
        checks.require(
            end.get("source_key") == key
            and type(end.get("records")) is int
            and end.get("records") == typed_count,
            f"boundary.{key}_end_count",
        )
        typed_hash = typed_digest.hexdigest()
        nonnull_hash = nonnull_digest.hexdigest()
        checks.require(nonnull == NONNULL_COUNTS[index],
                       f"boundary.{key}_nonnull_count")
        checks.require(nonnull_hash == NONNULL_HASHES[index],
                       f"boundary.{key}_nonnull_hash")
        if key in TYPED_HASHES:
            expected_hash, expected_count = TYPED_HASHES[key]
            checks.require(
                typed_hash == expected_hash and typed_count == expected_count,
                f"boundary.{key}_typed_lineage",
            )
        checks.require(metadata.get("sql_null_rows") == null_rows,
                       f"boundary.{key}_null_rows")
        checks.require(declared_nonnull == nonnull,
                       f"boundary.{key}_stored_nonnull")
        checks.require(metadata.get("source_rows") == source_rows,
                       f"boundary.{key}_source_rows")
        checks.require(metadata.get("nonnull_set_sha256") == nonnull_hash,
                       f"boundary.{key}_stored_nonnull_hash")
        checks.require(metadata.get("typed_set_sha256") == typed_hash,
                       f"boundary.{key}_stored_typed_hash")
        boundaries[key] = dict(metadata)
        boundary_summary[key] = {
            "source_field": field,
            "source_rows": source_rows,
            "typed_distinct_values": typed_count,
            "nonnull_distinct_values": nonnull,
            "sql_null_distinct_values": int(null_rows > 0),
            "sql_null_rows": null_rows,
            "nonnull_set_sha256": nonnull_hash,
            "typed_set_sha256": typed_hash,
            "lineage_match_confirmed": True,
        }
    checks.require(
        boundaries["detail_product_description_other"]["sql_null_rows"] > 0,
        "boundary.pdo_sql_null_present",
    )

    expected_seed.sort()
    if len(expected_seed) != len(set(expected_seed)):
        raise AuditContractError("seed.duplicate_key")
    expected_seed_digest = hashlib.sha256(SEMANTIC_SET_VERSION)
    expected_seed_digest.update(struct.pack(">Q", len(expected_seed)))
    for field_bytes, raw_bytes in expected_seed:
        expected_seed_digest.update(struct.pack(">I", len(field_bytes)))
        expected_seed_digest.update(field_bytes)
        expected_seed_digest.update(struct.pack(">Q", len(raw_bytes)))
        expected_seed_digest.update(raw_bytes)
    seed_hash = expected_seed_digest.hexdigest()
    checks.require(len(expected_seed) == 34_565, "seed.count")
    checks.require(seed_hash == SEMANTIC_SEED_HASH, "seed.hash")
    seed_begin = _exact_record_keys(cursor.take("semantic_seed_begin"), {
        "record_type", "key_count", "key_set_sha256",
        "sql_null_keys_included", "review_decisions_included",
    }, "seed.begin_schema")
    seed_summary = {
        "key_count": len(expected_seed),
        "key_set_sha256": seed_hash,
        "sql_null_keys_included": False,
        "review_decisions_included": False,
    }
    checks.require(
        _strict_json_equal(
            {key: seed_begin.get(key) for key in seed_summary}, seed_summary
        ),
        "seed.private_summary",
    )
    seed_records_match = True
    observed_seed_digest = hashlib.sha256(SEMANTIC_SET_VERSION)
    observed_seed_digest.update(struct.pack(">Q", len(expected_seed)))
    previous_seed: tuple[bytes, bytes] | None = None
    for index, expected in enumerate(expected_seed):
        record = _exact_record_keys(cursor.take("semantic_seed_value"), {
            "record_type", "source_field", "exact_raw_value",
        }, "seed.value_schema")
        source_field = record.get("source_field")
        raw = record.get("exact_raw_value")
        if not isinstance(source_field, str) or not isinstance(raw, str):
            raise AuditContractError("seed.value_types")
        observed = (source_field.encode("utf-8"), raw.encode("utf-8"))
        if previous_seed is not None and observed <= previous_seed:
            raise AuditContractError("seed.value_sort")
        previous_seed = observed
        seed_records_match = seed_records_match and observed == expected
        observed_seed_digest.update(struct.pack(">I", len(observed[0])))
        observed_seed_digest.update(observed[0])
        observed_seed_digest.update(struct.pack(">Q", len(observed[1])))
        observed_seed_digest.update(observed[1])
        if len(raw) >= 12 and raw in public_strings:
            private_value_leaked = True
    seed_end = _exact_record_keys(cursor.take("semantic_seed_end"), {
        "record_type", "records",
    }, "seed.end_schema")
    checks.require(
        type(seed_end.get("records")) is int
        and seed_end.get("records") == len(expected_seed),
                   "seed.end_count")
    checks.require(
        seed_records_match and observed_seed_digest.hexdigest() == seed_hash,
        "seed.private_records",
    )

    emar_rows = boundaries["emar_medication"]["source_rows"]
    detail_rows = boundaries["detail_product_description"]["source_rows"]
    pharmacy_rows = boundaries["pharmacy_medication"]["source_rows"]
    prescription_rows = boundaries["prescription_drug"]["source_rows"]
    checks.require(
        detail_rows
        == boundaries["detail_product_description_other"]["source_rows"]
        == boundaries["emar_detail_route"]["source_rows"],
        "crosswalk.emar_detail_boundary_denominator",
    )
    checks.require(
        pharmacy_rows == boundaries["pharmacy_route"]["source_rows"],
        "crosswalk.pharmacy_boundary_denominator",
    )
    checks.require(
        prescription_rows
        == boundaries["prescriptions_route"]["source_rows"]
        == boundaries["prescriptions_ndc"]["source_rows"],
        "crosswalk.prescriptions_boundary_denominator",
    )
    expected_inputs = {
        "202b": detail_rows,
        "202c": emar_rows + detail_rows + pharmacy_rows + prescription_rows,
    }
    checks.require(expected_inputs["202c"] <= MAX_COUNT,
                   "crosswalk.boundary_denominator_limit")
    crosswalks: dict[str, dict[str, Any]] = {}
    crosswalk_summary: dict[str, dict[str, Any]] = {}
    crosswalk_tuple_records = 0
    begin_metadata_keys = {
        "bucket_count", "bucket_indices_complete", "assignment_unit",
        "sql_null_subject_bucket", "bucket_assignment_violations",
        "null_subject_outside_bucket_zero", "global_input_rows",
        "global_input_rows_source", "summed_bucket_input_rows",
        "global_output_multiplicity",
        "mutual_exclusion_and_completeness_confirmed", "unique_tuples",
        "tuple_kind_summaries",
    }
    begin_kind_keys = {
        "unique_tuples", "total_multiplicity", "summed_bucket_input_rows",
        "summed_bucket_tuple_multiplicity",
    }
    for stage in ("202b", "202c"):
        begin = _exact_record_keys(cursor.take("crosswalk_begin"), {
            "record_type", "stage", "metadata",
        }, f"crosswalk.{stage}_begin_schema")
        if begin.get("stage") != stage:
            raise AuditContractError(f"crosswalk.{stage}_stream_order")
        metadata = _exact_record_keys(
            begin.get("metadata"), begin_metadata_keys,
            f"crosswalk.{stage}_schema",
        )
        for name, expected in {
            "bucket_count": BUCKET_COUNT,
            "bucket_indices_complete": True,
            "assignment_unit": "subject_id",
            "sql_null_subject_bucket": 0,
            "bucket_assignment_violations": 0,
            "null_subject_outside_bucket_zero": 0,
            "global_input_rows_source": "same_snapshot_202a_boundary_source_rows",
            "mutual_exclusion_and_completeness_confirmed": True,
        }.items():
            observed = metadata.get(name)
            checks.require(
                (observed is expected if isinstance(expected, bool)
                 else type(observed) is type(expected) and observed == expected),
                           f"crosswalk.{stage}_{name}")
        global_input = metadata.get("global_input_rows")
        summed_input = metadata.get("summed_bucket_input_rows")
        unique_count = metadata.get("unique_tuples")
        declared_total = metadata.get("global_output_multiplicity")
        if (
            type(global_input) is not int or not 0 <= global_input <= MAX_COUNT
            or type(summed_input) is not int
            or not 0 <= summed_input <= MAX_COUNT
            or type(unique_count) is not int
            or not 0 <= unique_count
            <= BUCKET_COUNT * MAX_TUPLE_GROUPS_PER_BUCKET
            or type(declared_total) is not int or not 0 <= declared_total <= MAX_COUNT
        ):
            raise AuditContractError(f"crosswalk.{stage}_declared_counts")
        checks.require(global_input == expected_inputs[stage],
                       f"crosswalk.{stage}_boundary_denominator")
        checks.require(summed_input == global_input,
                       f"crosswalk.{stage}_bucket_conservation")
        kinds = TUPLE_FIELDS[stage]
        declared_kinds = metadata.get("tuple_kind_summaries")
        if not isinstance(declared_kinds, dict) or set(declared_kinds) != set(kinds):
            raise AuditContractError(f"crosswalk.{stage}_kind_inventory")
        kind_state: dict[str, dict[str, Any]] = {}
        for kind in kinds:
            declared = _exact_record_keys(
                declared_kinds[kind], begin_kind_keys,
                f"crosswalk.{stage}_{kind}_begin_schema",
            )
            if any(
                type(declared.get(name)) is not int
                or not 0 <= declared[name] <= MAX_COUNT
                for name in begin_kind_keys
            ):
                raise AuditContractError(f"crosswalk.{stage}_{kind}_counts")
            checks.require(
                declared["total_multiplicity"]
                == declared["summed_bucket_input_rows"]
                == declared["summed_bucket_tuple_multiplicity"],
                f"crosswalk.{stage}_{kind}_conservation",
            )
            kind_state[kind] = {
                "declared": dict(declared),
                "hashers": _new_stream_tuple_hashers(
                    stage + ":" + kind, declared["unique_tuples"]
                ),
                "unique": 0,
                "total": 0,
            }
        global_hashers = _new_stream_tuple_hashers(stage, unique_count)
        previous_encoded: bytes | None = None
        total = 0
        for record_index in range(unique_count):
            record = _exact_record_keys(cursor.take("crosswalk_tuple"), {
                "record_type", "stage", "tuple_kind", "tuple", "multiplicity",
            }, f"crosswalk.{stage}_tuple_schema")
            if record.get("stage") != stage:
                raise AuditContractError(f"crosswalk.{stage}_tuple_stage")
            kind = record.get("tuple_kind")
            value = record.get("tuple")
            multiplicity = record.get("multiplicity")
            if kind not in kinds:
                raise AuditContractError(f"crosswalk.{stage}_tuple_kind")
            if (
                not isinstance(value, dict)
                or list(value) != sorted(
                    kinds[kind], key=lambda item: item.encode("utf-8")
                )
                or set(value) != set(kinds[kind])
                or set(value) & FORBIDDEN_TUPLE_FIELDS
            ):
                raise AuditContractError(f"crosswalk.{stage}_tuple_fields")
            if not all(item is None or isinstance(item, str) for item in value.values()):
                raise AuditContractError(f"crosswalk.{stage}_tuple_types")
            categorical = ENUM_FIELDS_BY_KIND.get((stage, kind), {})
            if not all(value.get(field) in allowed for field, allowed in categorical.items()):
                raise AuditContractError(f"crosswalk.{stage}_tuple_enums")
            if kind == "ndc_external_mapping_input" and not isinstance(value.get("ndc"), str):
                raise AuditContractError(f"crosswalk.{stage}_nonnull_ndc")
            if type(multiplicity) is not int or not 1 <= multiplicity <= MAX_COUNT:
                raise AuditContractError(f"crosswalk.{stage}_multiplicity")
            canonical = json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            if len(canonical) > MAX_TUPLE_JSON_BYTES:
                raise AuditContractError(f"crosswalk.{stage}_tuple_json_limit")
            encoded = _encode_tuple(stage, kind, value)
            if previous_encoded is not None and encoded <= previous_encoded:
                raise AuditContractError(f"crosswalk.{stage}_global_sort")
            previous_encoded = encoded
            if total > MAX_COUNT - multiplicity:
                raise AuditContractError(f"crosswalk.{stage}_total_limit")
            total += multiplicity
            _update_stream_tuple_hashers(global_hashers, encoded, multiplicity)
            state = kind_state[kind]
            state["unique"] += 1
            if state["total"] > MAX_COUNT - multiplicity:
                raise AuditContractError(f"crosswalk.{stage}_{kind}_total_limit")
            state["total"] += multiplicity
            _update_stream_tuple_hashers(state["hashers"], encoded, multiplicity)
            for field, item in value.items():
                if (
                    field not in categorical
                    and isinstance(item, str)
                    and len(item) >= 12
                    and item in public_strings
                ):
                    private_value_leaked = True
            crosswalk_tuple_records += 1
        end = _exact_record_keys(cursor.take("crosswalk_end"), {
            "record_type", "stage", "records", "global_tuple_set_sha256",
            "global_tuple_frequency_sha256", "tuple_kind_hashes",
        }, f"crosswalk.{stage}_end_schema")
        checks.require(
            end.get("stage") == stage
            and type(end.get("records")) is int
            and end.get("records") == unique_count,
            f"crosswalk.{stage}_end_count",
        )
        set_hash = global_hashers[0].hexdigest()
        frequency_hash = global_hashers[1].hexdigest()
        checks.require(total == declared_total,
                       f"crosswalk.{stage}_output_total")
        checks.require(end.get("global_tuple_set_sha256") == set_hash,
                       f"crosswalk.{stage}_set_hash")
        checks.require(end.get("global_tuple_frequency_sha256") == frequency_hash,
                       f"crosswalk.{stage}_frequency_hash")
        end_kind_hashes = end.get("tuple_kind_hashes")
        if not isinstance(end_kind_hashes, dict) or set(end_kind_hashes) != set(kinds):
            raise AuditContractError(f"crosswalk.{stage}_end_kind_inventory")
        kind_summaries: dict[str, dict[str, Any]] = {}
        for kind in kinds:
            state = kind_state[kind]
            declared = state["declared"]
            kind_set = state["hashers"][0].hexdigest()
            kind_frequency = state["hashers"][1].hexdigest()
            observed_hashes = _exact_record_keys(
                end_kind_hashes[kind], {
                    "global_tuple_set_sha256", "global_tuple_frequency_sha256"
                }, f"crosswalk.{stage}_{kind}_end_schema",
            )
            checks.require(
                state["unique"] == declared["unique_tuples"]
                and state["total"] == declared["total_multiplicity"],
                f"crosswalk.{stage}_{kind}_conservation",
            )
            checks.require(
                observed_hashes == {
                    "global_tuple_set_sha256": kind_set,
                    "global_tuple_frequency_sha256": kind_frequency,
                },
                f"crosswalk.{stage}_{kind}_hashes",
            )
            kind_summaries[kind] = {
                **declared,
                "global_tuple_set_sha256": kind_set,
                "global_tuple_frequency_sha256": kind_frequency,
            }
        rebuilt = {
            key: metadata[key]
            for key in begin_metadata_keys - {"tuple_kind_summaries"}
        }
        rebuilt.update({
            "global_tuple_set_sha256": set_hash,
            "global_tuple_frequency_sha256": frequency_hash,
            "tuple_kind_summaries": kind_summaries,
        })
        crosswalks[stage] = rebuilt
        crosswalk_summary[stage] = dict(rebuilt)

    footer = _exact_record_keys(cursor.take("footer"), {
        "record_type", "records_before_footer", "section_records",
    }, "private.footer_schema")
    section_records = {
        "boundary_values": boundary_value_records,
        "semantic_seed_values": len(expected_seed),
        "crosswalk_tuples": crosswalk_tuple_records,
    }
    checks.require(_strict_json_equal(footer.get("section_records"), section_records),
                   "private.footer_sections")
    checks.require(
        type(footer.get("records_before_footer")) is int
        and footer.get("records_before_footer") == reader.records - 1,
                   "private.footer_count")
    cursor.finish()
    checks.require(reader.records == entry.get("private_values_records"),
                   "files.private_records")
    checks.require(reader.stored_bytes == entry.get("private_values_bytes"),
                   "files.private_bytes")
    checks.require(
        reader.stored_sha256.hexdigest() == entry.get("private_values_sha256"),
        "files.private_sha256",
    )
    checks.require(reader.raw_bytes == entry.get("private_values_raw_bytes"),
                   "files.private_raw_bytes")
    checks.require(
        reader.raw_sha256.hexdigest() == entry.get("private_values_raw_sha256"),
        "files.private_raw_sha256",
    )
    checks.require(
        entry.get("private_values_encoding") == PRIVATE_ARTIFACT_ENCODING,
        "files.private_encoding",
    )
    checks.require(not private_value_leaked, "privacy.no_exact_private_leaf")
    private["boundaries"] = boundaries
    private["semantic_seed"] = seed_summary
    private["crosswalks"] = crosswalks
    return {
        "private": private,
        "boundary_summary": boundary_summary,
        "seed_summary": seed_summary,
        "crosswalk_summary": crosswalk_summary,
        "stored_bytes": reader.stored_bytes,
        "stored_sha256": reader.stored_sha256.hexdigest(),
        "raw_bytes": reader.raw_bytes,
        "raw_sha256": reader.raw_sha256.hexdigest(),
        "records": reader.records,
    }


def _check_public_keys(value: Any, checks: Checks, label: str) -> None:
    if isinstance(value, Mapping):
        checks.require(not (set(value) & FORBIDDEN_PUBLIC_KEYS), label + ".forbidden_keys")
        for key, item in value.items():
            lowered = key.lower()
            checks.require(
                key == "per_value_or_per_tuple_hashes_emitted"
                or ("per_value" not in lowered and "per_tuple" not in lowered),
                label + ".no_per_item_hash",
            )
            _check_public_keys(item, checks, label)
    elif isinstance(value, list):
        for item in value:
            _check_public_keys(item, checks, label)


def _contract_projection(config: Mapping[str, Any]) -> dict[str, Any]:
    projection = json.loads(json.dumps(config))
    for key in ("status", "rule_version", "execution_status", "execution_permitted", "implementation_state"):
        projection.pop(key, None)
    implementation = projection.get("implementation", {})
    for key in ("state", "sql_bundle_sha256", "runner_bundle_sha256", "auditor_bundle_sha256"):
        implementation.pop(key, None)
    fixture = projection.get("fixture_gate", {})
    for key in (
        "status", "attestation_path", "attestation_sha256",
        "readonly_postgresql_explain_status",
        "readonly_postgresql_explain_attestation_path",
        "readonly_postgresql_explain_attestation_sha256",
    ):
        fixture.pop(key, None)
    projection.get("execution_gate", {}).pop("unresolved_blockers", None)
    return projection


def _contract_hash(config: Mapping[str, Any]) -> str:
    return _sha_bytes(json.dumps(
        _contract_projection(config), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8"))


def _validate_config(
    root: Path,
    config: Mapping[str, Any],
    bundles: Mapping[str, Mapping[str, Any]],
    checks: Checks,
) -> None:
    checks.require(
        type(config.get("schema_version")) is int
        and config.get("schema_version") == 1,
        "config.schema_version",
    )
    checks.require(config.get("component_id") == COMPONENT_ID, "config.component_id")
    checks.require(config.get("status") == "frozen_for_execution", "config.frozen_status")
    checks.require(config.get("execution_status") == "not_executed", "config.not_executed")
    checks.require(config.get("execution_permitted") is True, "config.execution_permitted")
    checks.require(
        config.get("implementation_state") == "frozen_for_execution",
        "config.implementation_state",
    )
    checks.require(config.get("formal_product_mapping_enabled") is False,
                   "config.product_mapping_false")
    checks.require(config.get("formal_source_policy_enabled") is False,
                   "config.source_policy_false")
    transaction = config.get("transaction")
    checks.require(isinstance(transaction, dict), "config.transaction_table")
    expected_transaction = {
        "transaction_isolation": "repeatable read",
        "transaction_read_only": True,
        "all_pre_adjudication_sql_statements_share_one_snapshot": True,
        "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
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
    for key, expected in expected_transaction.items():
        checks.require(transaction.get(key) == expected, "config.transaction_" + key)
    plan = config.get("bucket_plan")
    checks.require(isinstance(plan, dict), "config.bucket_plan_table")
    for key, expected in {
        "version": BUCKET_VERSION,
        "status": "frozen",
        "bucket_count": BUCKET_COUNT,
        "bucket_indices": list(range(BUCKET_COUNT)),
        "bucketed_stages": ["202b", "202c"],
        "physical_bucket_template_count": len(BUCKET_STATEMENT_SPECS),
        "physical_bucket_statements_per_bucket": len(BUCKET_STATEMENT_SPECS),
        "physical_bucket_statement_labels": [
            spec["stage"] for spec in BUCKET_STATEMENT_SPECS
        ],
        "bucket_input_control_owner_labels": [
            spec["stage"]
            for spec in BUCKET_STATEMENT_SPECS
            if spec["bucket_input_source"] is not None
        ],
        "hash_prefix": BUCKET_PREFIX,
        "null_subject_bucket": 0,
        "all_indices_required_once": True,
        "missing_duplicate_or_cross_bucket_row_fails_closed": True,
        "independent_from_mapped_event_application_bucket_plan": True,
    }.items():
        checks.require(plan.get(key) == expected, "config.bucket_" + key)
    stages = config.get("stages")
    checks.require(isinstance(stages, dict) and list(stages) == ["202a", "202b", "202c"],
                   "config.stage_inventory")
    checks.require(stages["202a"].get("source_fields") == list(SOURCE_FIELDS),
                   "config.boundary_fields")
    checks.require(stages["202a"].get("statement_count") == 9,
                   "config.boundary_count")
    checks.require(
        stages["202b"].get("bucketed") is True
        and stages["202b"].get("bucket_count") == BUCKET_COUNT,
        "config.202b_bucket_shape",
    )
    checks.require(
        stages["202c"].get("bucketed") is True
        and stages["202c"].get("bucket_count") == BUCKET_COUNT,
        "config.202c_bucket_shape",
    )
    checks.require(stages["202b"].get("selection_may_use_query200_scope") is False,
                   "config.q200_not_filter_202b")
    checks.require(stages["202c"].get("selection_may_use_query200_scope") is False,
                   "config.q200_not_filter_202c")
    checks.require(stages["202b"].get("record_kinds") == list(TUPLE_FIELDS["202b"]),
                   "config.detail_kinds")
    checks.require(stages["202c"].get("record_kinds") == list(TUPLE_FIELDS["202c"]),
                   "config.order_kinds")
    for logical_stage, expected_parts in BUCKET_STATEMENTS_BY_LOGICAL_STAGE.items():
        observed_stage = stages[logical_stage]
        checks.require(
            observed_stage.get("physical_statement_count_per_bucket")
            == len(expected_parts),
            f"config.{logical_stage}_physical_statement_count",
        )
        expected_part_tables = [
            {
                "label": part["stage"],
                "logical_stage": part["logical_stage"],
                "sql_path": part["path"],
                "tuple_kinds": list(part["tuple_kinds"]),
                "bucket_input_source": part["bucket_input_source"] or "",
                "owns_bucket_input_controls": (
                    part["bucket_input_source"] is not None
                ),
            }
            for part in expected_parts
        ]
        checks.require(
            observed_stage.get("physical_parts") == expected_part_tables,
            f"config.{logical_stage}_physical_parts",
        )
    for key, expected in {
        "detail_head_identity_states": list(TUPLE_VALUE_ENUMS[
            ("202b", "emar_medication_detail_bridge", "detail_head_identity_state")
        ]),
        "detail_bridge_match_states": list(TUPLE_VALUE_ENUMS[
            ("202b", "emar_medication_detail_bridge", "detail_match_state")
        ]),
        "head_partition_detail_match_states": list(TUPLE_VALUE_ENUMS[
            ("202b", "emar_medication_head_partition", "detail_match_state")
        ]),
        "global_input_denominator_boundary_fields": [
            SOURCE_FIELDS[1], SOURCE_FIELDS[4], SOURCE_FIELDS[5]
        ],
        "global_input_denominator_boundary_source_rows_must_agree": True,
        "per_bucket_global_input_rows_control_allowed": False,
    }.items():
        checks.require(stages["202b"].get(key) == expected, "config.202b_" + key)
    for key, expected in {
        "pharmacy_prescription_link_identity_states": list(TUPLE_VALUE_ENUMS[
            ("202c", "pharmacy_prescription_bridge", "link_identity_state")
        ]),
        "head_pharmacy_prescription_link_identity_states": list(TUPLE_VALUE_ENUMS[
            ("202c", "head_pharmacy_prescription_bridge", "link_identity_state")
        ]),
        "detail_pharmacy_prescription_link_identity_states": list(TUPLE_VALUE_ENUMS[
            ("202c", "detail_pharmacy_prescription_bridge", "link_identity_state")
        ]),
        "poe_auxiliary_states": list(TUPLE_VALUE_ENUMS[
            ("202c", "pharmacy_prescription_bridge", "poe_auxiliary_state")
        ]),
        "global_input_denominator_boundary_fields": list(SOURCE_FIELDS[:4]),
        "same_relation_boundary_source_rows_must_agree": True,
        "per_bucket_global_input_rows_control_allowed": False,
    }.items():
        checks.require(stages["202c"].get(key) == expected, "config.202c_" + key)
    checks.require(stages["202b"].get(
        "nonnull_emar_medication_heads_partition_into_with_detail_and_no_detail"
    ) is True, "config.no_detail_partition")
    checks.require(stages["202c"].get(
        "head_and_detail_pharmacy_keys_are_separate_link_paths"
    ) is True, "config.two_order_paths")
    checks.require(stages["202c"].get("head_and_detail_pharmacy_keys_may_be_coalesced") is False,
                   "config.no_order_path_coalesce")
    checks.require(stages["202c"].get(
        "raw_ndc_retained_without_normalization_validation_or_external_lookup"
    ) is True, "config.ndc_exact_handoff")
    checks.require(stages["202c"].get(
        "sql_null_ndc_excluded_from_external_mapping_input"
    ) is True, "config.ndc_null_not_external_candidate")
    checks.require(config.get("semantic_seed_lineage", {}).get("expected_key_count") == 34565,
                   "config.seed_count")
    checks.require(config.get("semantic_seed_lineage", {}).get(
        "expected_key_set_sha256"
    ) == SEMANTIC_SEED_HASH, "config.seed_hash")
    checks.require(config.get("stages", {}).get("202a", {}).get(
        "product_description_other_sql_null_is_missing_evidence_not_semantic_key"
    ) is True, "config.pdo_null_boundary")
    merge = config.get("offline_merge", {})
    expected_merge = {
        "occurs_only_after_rollback_and_clean_exit": True,
        "uses_typed_exact_tuple_k_way_merge_across_all_preregistered_buckets": True,
        "same_exact_raw_tuple_across_buckets_is_merged_by_summing_int64_bounded_multiplicity": True,
        "typed_null_and_nonnull_empty_string_remain_distinct": True,
        "tuple_hash_framing": (
            "fixed domain and version plus record count plus field name, type tag, "
            "SQL NULL marker or exact UTF-8 length and bytes, ordered by encoded tuple bytes"
        ),
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
        "anonymous_sorted_runs_per_logical_stage": BUCKET_COUNT,
        "external_merge_pass_count": 2,
        "private_artifact_encoding": PRIVATE_ARTIFACT_ENCODING,
        "private_artifact_single_gzip_member_required": True,
        "private_artifact_strict_record_order_required": True,
        "private_artifact_stream_validation_required": True,
    }
    checks.require(
        isinstance(merge, dict) and set(merge) == set(expected_merge),
        "config.merge_exact_schema",
    )
    for key, expected in expected_merge.items():
        checks.require(merge.get(key) == expected, "config.merge_" + key)
    guards = config.get("guards")
    checks.require(isinstance(guards, dict) and set(guards) == set(FALSE_GUARDS),
                   "config.guard_inventory")
    checks.require(all(guards[key] is False for key in FALSE_GUARDS),
                   "config.guards_false")
    artifact = config.get("artifact_policy")
    checks.require(isinstance(artifact, dict), "config.artifact_policy_table")
    for key, expected in {
        "private_directory_mode": "0700", "private_file_mode": "0600",
        "git_ignored_required": True, "public_raw_values_allowed": False,
        "public_patient_event_order_identifiers_allowed": False,
        "public_per_value_or_per_event_hashes_allowed": False,
    }.items():
        checks.require(artifact.get(key) == expected, "config.artifact_" + key)
    limits = config.get("limits")
    checks.require(isinstance(limits, dict), "config.limits_table")
    expected_limits = {
        "boundary_statement_count": 9,
        "bucketed_statement_count": 448,
        "total_scientific_statement_count": STATEMENT_COUNT,
        "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        "client_watchdog_seconds": PROCESS_TIMEOUT_SECONDS,
        "max_boundary_frame_bytes": MAX_BOUNDARY_FRAME_BYTES,
        "max_crosswalk_frame_bytes": MAX_CROSSWALK_FRAME_BYTES,
        "max_crosswalk_frame_bytes_applies_to_combined_physical_frames_per_logical_bucket": True,
        "max_cumulative_raw_frame_bytes": MAX_CUMULATIVE_RAW_FRAME_BYTES,
        "max_total_anonymous_spool_bytes": MAX_CUMULATIVE_SPOOL_BYTES,
        "max_merge_run_raw_bytes": MAX_MERGE_RUN_RAW_BYTES,
        "max_merge_run_spool_bytes": MAX_MERGE_RUN_SPOOL_BYTES,
        "max_private_artifact_raw_bytes": MAX_PRIVATE_RAW_BYTES,
        "max_private_artifact_stored_bytes": MAX_PRIVATE_STORED_BYTES,
        "max_private_artifact_line_bytes": MAX_PRIVATE_LINE_BYTES,
        "max_tuple_json_utf8_bytes": MAX_TUPLE_JSON_BYTES,
        "max_executed_sql_bytes": MAX_EXECUTED_SQL_BYTES,
        "max_boundary_groups_per_field": MAX_BOUNDARY_GROUPS,
        "max_tuple_groups_per_bucket": MAX_TUPLE_GROUPS_PER_BUCKET,
        "max_tuple_groups_per_bucket_applies_to_combined_physical_parts": True,
        "max_exact_multiplicity": MAX_COUNT,
    }
    checks.require(
        isinstance(limits, dict) and set(limits) == set(expected_limits),
        "config.limits_exact_schema",
    )
    for key, expected in expected_limits.items():
        checks.require(limits.get(key) == expected, "config.limit_" + key)
    implementation = config.get("implementation")
    checks.require(isinstance(implementation, dict), "config.implementation_table")
    checks.require(implementation.get("state") == "frozen_for_execution",
                   "config.implementation_frozen")
    checks.require(implementation.get("bundle_hash_encoding") == BUNDLE_ENCODING,
                   "config.bundle_encoding")
    for name, path_key, digest_key in (
        ("sql", "sql_paths", "sql_bundle_sha256"),
        ("runner", "runner_paths", "runner_bundle_sha256"),
        ("offline_auditor", "auditor_paths", "auditor_bundle_sha256"),
    ):
        checks.require(implementation.get(path_key) == list(BUNDLE_PATHS[name]),
                       "config.bundle_paths_" + name)
        checks.require(implementation.get(digest_key) == bundles[name]["bundle_sha256"],
                       "config.bundle_hash_" + name)
    gate = config.get("execution_gate")
    checks.require(isinstance(gate, dict) and gate.get("unresolved_blockers") == [],
                   "config.no_blockers")
    checks.require(gate.get("status_change_alone_may_enable_execution") is False,
                   "config.status_not_sufficient")

    evidence = config.get("evidence")
    checks.require(isinstance(evidence, list) and len(evidence) == 9,
                   "lineage.evidence_inventory")
    for index, item in enumerate(evidence):
        checks.require(isinstance(item, dict) and _safe_relative(item.get("path")),
                       f"lineage.evidence_{index}_path")
        path = root / item["path"]
        checks.require(path.is_file() and not path.is_symlink(),
                       f"lineage.evidence_{index}_present")
        checks.require(_sha_file(path) == item.get("file_sha256"),
                       f"lineage.evidence_{index}_hash")

    fixture = config.get("fixture_gate")
    checks.require(isinstance(fixture, dict) and fixture.get("status") == "passed",
                   "fixture.status")
    checks.require(_safe_relative(fixture.get("attestation_path")), "fixture.path")
    attestation_path = root / fixture["attestation_path"]
    checks.require(attestation_path.is_file() and not attestation_path.is_symlink(),
                   "fixture.present")
    checks.require(_sha_file(attestation_path) == fixture.get("attestation_sha256"),
                   "fixture.hash")
    attestation, _ = _read_json(attestation_path, 4 * 1024 * 1024, "fixture.json")
    checks.require(set(attestation) == FIXTURE_ATTESTATION_KEYS,
                   "fixture.exact_schema")
    checks.require(type(attestation.get("schema_version")) is int
                   and attestation.get("schema_version") == 1,
                   "fixture.schema_version")
    checks.require(attestation.get("component_id") == COMPONENT_ID, "fixture.component")
    checks.require(attestation.get("status") == "passed", "fixture.passed")
    checks.require(attestation.get("test_command") == FIXTURE_TEST_COMMAND,
                   "fixture.test_command")
    checks.require(type(attestation.get("tests_run")) is int
                   and attestation.get("tests_run") == FIXTURE_TEST_COUNT,
                   "fixture.test_count")
    checks.require(attestation.get("scientific_contract_sha256") == _contract_hash(config),
                   "fixture.contract_hash")
    checks.require(attestation.get("implementation_bundle_sha256") == {
        name: item["bundle_sha256"] for name, item in bundles.items()
    }, "fixture.bundle_hashes")
    checks.require(type(attestation.get("failures")) is int
                   and type(attestation.get("errors")) is int
                   and attestation.get("failures") == 0
                   and attestation.get("errors") == 0,
                   "fixture.zero_failures")
    tests = fixture.get("required_test_paths")
    files = attestation.get("test_files")
    checks.require(isinstance(tests, list) and isinstance(files, list),
                   "fixture.test_inventory")
    checks.require(tests == list(REQUIRED_TEST_PATHS), "fixture.test_path_lock")
    checks.require(
        len(files) == len(REQUIRED_TEST_PATHS)
        and all(
            isinstance(item, dict) and set(item) == FIXTURE_TEST_FILE_KEYS
            for item in files
        ),
        "fixture.test_file_schema",
    )
    expected_test_files = []
    for relative in REQUIRED_TEST_PATHS:
        path = root / relative
        checks.require(
            _safe_relative(relative) and path.is_file() and not path.is_symlink(),
            "fixture.test_file_present",
        )
        expected_test_files.append({
            "path": relative,
            "file_sha256": _sha_file(path),
        })
    checks.require(files == expected_test_files,
                   "fixture.test_hashes")
    checks.require(
        fixture.get("required_mutation_classes") == list(REQUIRED_MUTATION_CLASSES),
        "fixture.mutation_class_lock",
    )
    checks.require(
        attestation.get("mutation_classes_passed") == list(REQUIRED_MUTATION_CLASSES),
        "fixture.mutation_classes",
    )
    checks.require(fixture.get("failures_required") == 0,
                   "fixture.failures_required")
    checks.require(fixture.get("synthetic_postgresql_fixture_passed") is False,
                   "fixture.synthetic_postgresql_false")
    checks.require(fixture.get("readonly_postgresql_explain_status") == "passed",
                   "explain.status")
    checks.require(_safe_relative(
        fixture.get("readonly_postgresql_explain_attestation_path")
    ), "explain.path")
    explain_path = root / fixture["readonly_postgresql_explain_attestation_path"]
    checks.require(explain_path.is_file() and not explain_path.is_symlink(),
                   "explain.present")
    checks.require(_sha_file(explain_path) == fixture.get(
        "readonly_postgresql_explain_attestation_sha256"
    ), "explain.hash")
    explain, _ = _read_json(explain_path, 4 * 1024 * 1024, "explain.json")
    expected_explain_statements, expected_rendered = _expected_explain_metadata(root)
    expected_attester = _bundle(root, EXPLAIN_ATTESTER_PATHS)
    for key, expected in {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "status": "passed",
        "mode": "real_postgresql_read_only_explain_without_analyze",
        "database_connection_opened": True,
        "synthetic_postgresql_fixture": False,
        "single_transaction": True,
        "transaction_read_only": True,
        "transaction_isolation": "repeatable read",
        "database_controls_observed_before_explain": True,
        "database_control_checks": {
            "transaction_read_only_on": True,
            "transaction_isolation_repeatable_read": True,
            "statement_timeout_120000ms": True,
        },
        "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        "client_watchdog_seconds": PROCESS_TIMEOUT_SECONDS,
        "statement_count": 16,
        "analyze_used": False,
        "explain_syntax": "EXPLAIN (FORMAT JSON)",
        "database_writes_or_session_objects": False,
        "on_error_stop": True,
        "rollback_confirmed": True,
        "psql_returncode": 0,
        "query_output_redirected_to_os_null": True,
        "stdout_control_frames_empty": True,
        "plan_output_discarded": True,
        "plan_output_persisted": False,
        "stderr_anonymous_unlinked": True,
        "stderr_persisted": False,
        "sql_text_persisted": False,
        "query_plan_relation_or_column_details_persisted": False,
        "success_persisted_only_after_rollback_and_clean_exit": True,
        "sql_bundle_sha256": bundles["sql"]["bundle_sha256"],
        "statements": expected_explain_statements,
        "rendered_statements": expected_rendered,
        "attester_bundle_sha256": expected_attester["bundle_sha256"],
        "attester_paths": list(EXPLAIN_ATTESTER_PATHS),
        "attester_files": expected_attester["files"],
        "bundle_hash_encoding": BUNDLE_ENCODING,
        "control_transcript_hash_framing": "uint64be_control_utf8_length+control_utf8",
        "raw_values_persisted": False,
        "patient_or_event_identifiers_persisted": False,
        "artifact_directory_mode": "0700",
        "artifact_file_mode": "0600",
        "artifact_git_ignored": True,
    }.items():
        checks.require(explain.get(key) == expected, "explain." + key)
    checks.require(set(explain) == EXPLAIN_ATTESTATION_KEYS, "explain.exact_schema")
    checks.require(_finite_nonnegative(
        explain.get("database_control_elapsed_seconds"), 136
    ), "explain.control_elapsed")
    elapsed = explain.get("statement_elapsed_seconds")
    checks.require(
        isinstance(elapsed, list)
        and len(elapsed) == 16
        and all(_finite_nonnegative(item, 136) for item in elapsed),
        "explain.statement_elapsed",
    )
    checks.require(_finite_nonnegative(explain.get("elapsed_seconds")),
                   "explain.total_elapsed")
    checks.require(_utc_attestation_interval(explain), "explain.utc_interval")
    checks.require(
        isinstance(explain.get("control_transcript_sha256"), str)
        and SHA256_RE.fullmatch(explain["control_transcript_sha256"]) is not None,
        "explain.transcript_hash",
    )
    checks.require(_mode(explain_path) == "0600", "explain.file_0600")
    checks.require(
        explain_path.parent.is_dir()
        and not explain_path.parent.is_symlink()
        and _mode(explain_path.parent) == "0700",
        "explain.directory_0700",
    )
    try:
        explain_relative = explain_path.relative_to(root)
    except ValueError as exc:
        raise AuditContractError("explain.inside_root") from exc
    checks.require(
        bool(explain_relative.parts) and explain_relative.parts[0] == "artifacts",
        "explain.under_artifacts",
    )
    ignore = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    checks.require(any(line.strip() in {"artifacts/*", "artifacts/"} for line in ignore),
                   "explain.gitignored")


def _validate_boundaries(
    boundaries: Any,
    checks: Checks,
) -> tuple[dict[str, dict[str, Any]], set[str], dict[str, Any]]:
    checks.require(isinstance(boundaries, dict) and set(boundaries) == set(SOURCE_KEYS),
                   "boundary.inventory")
    rebuilt: dict[str, dict[str, Any]] = {}
    private_strings: set[str] = set()
    for index, (key, field, stage) in enumerate(
        zip(SOURCE_KEYS, SOURCE_FIELDS, BOUNDARY_STAGES, strict=True)
    ):
        source = boundaries[key]
        checks.require(isinstance(source, dict), f"boundary.{key}_table")
        checks.require(set(source) == {
            "stage", "source_field", "semantic_seed_field", "sql_null_rows",
            "typed_distinct_values", "nonnull_distinct_values", "source_rows",
            "nonnull_set_sha256", "typed_set_sha256", "records",
        }, f"boundary.{key}_schema")
        checks.require(source.get("stage") == stage and source.get("source_field") == field,
                       f"boundary.{key}_identity")
        checks.require(source.get("semantic_seed_field") is (key in SEMANTIC_KEYS),
                       f"boundary.{key}_semantic_role")
        records = source.get("records")
        checks.require(isinstance(records, list) and len(records) <= MAX_BOUNDARY_GROUPS + 1,
                       f"boundary.{key}_records")
        observed_order: list[tuple[bool, bytes]] = []
        source_rows = 0
        null_rows = 0
        nonnull = 0
        for record_index, record in enumerate(records):
            label = f"boundary.{key}_record_{record_index}"
            checks.require(isinstance(record, dict) and set(record) == {
                "raw_is_null", "raw_value", "raw_utf8_bytes", "exact_row_count"
            }, label + "_schema")
            count = record.get("exact_row_count")
            checks.require(type(count) is int and 1 <= count <= MAX_COUNT,
                           label + "_count")
            raw = record.get("raw_value")
            is_null = record.get("raw_is_null")
            byte_count = record.get("raw_utf8_bytes")
            if is_null is True:
                checks.require(raw is None and byte_count == 0, label + "_null")
                null_rows += count
                observed_order.append((False, b""))
            else:
                checks.require(is_null is False and isinstance(raw, str), label + "_nonnull")
                raw_bytes = raw.encode("utf-8")
                checks.require(b"\x00" not in raw_bytes and byte_count == len(raw_bytes),
                               label + "_bytes")
                nonnull += 1
                observed_order.append((True, raw_bytes))
                if len(raw) >= 12:
                    private_strings.add(raw)
            source_rows += count
        checks.require(observed_order == sorted(observed_order), f"boundary.{key}_sort")
        checks.require(len(observed_order) == len(set(observed_order)),
                       f"boundary.{key}_unique")
        typed_hash = _typed_hash(field, records)
        nonnull_hash = _nonnull_hash(field, records)
        checks.require(nonnull == NONNULL_COUNTS[index], f"boundary.{key}_nonnull_count")
        checks.require(nonnull_hash == NONNULL_HASHES[index], f"boundary.{key}_nonnull_hash")
        if key in TYPED_HASHES:
            expected_hash, expected_count = TYPED_HASHES[key]
            checks.require(typed_hash == expected_hash and len(records) == expected_count,
                           f"boundary.{key}_typed_lineage")
        checks.require(source.get("sql_null_rows") == null_rows,
                       f"boundary.{key}_null_rows")
        checks.require(source.get("typed_distinct_values") == len(records),
                       f"boundary.{key}_typed_count")
        checks.require(source.get("nonnull_distinct_values") == nonnull,
                       f"boundary.{key}_stored_nonnull")
        checks.require(source.get("source_rows") == source_rows,
                       f"boundary.{key}_source_rows")
        checks.require(source.get("nonnull_set_sha256") == nonnull_hash,
                       f"boundary.{key}_stored_nonnull_hash")
        checks.require(source.get("typed_set_sha256") == typed_hash,
                       f"boundary.{key}_stored_typed_hash")
        rebuilt[key] = {
            "source_field": field,
            "source_rows": source_rows,
            "typed_distinct_values": len(records),
            "nonnull_distinct_values": nonnull,
            "sql_null_distinct_values": int(null_rows > 0),
            "sql_null_rows": null_rows,
            "nonnull_set_sha256": nonnull_hash,
            "typed_set_sha256": typed_hash,
            "lineage_match_confirmed": True,
        }
    checks.require(boundaries["detail_product_description_other"]["sql_null_rows"] > 0,
                   "boundary.pdo_sql_null_present")
    seed_count, seed_hash = _seed_hash(boundaries)
    checks.require(seed_count == 34_565, "seed.count")
    checks.require(seed_hash == SEMANTIC_SEED_HASH, "seed.hash")
    return rebuilt, private_strings, {
        "key_count": seed_count,
        "key_set_sha256": seed_hash,
        "sql_null_keys_included": False,
        "review_decisions_included": False,
    }


def _validate_crosswalks(
    crosswalks: Any,
    boundaries: Mapping[str, Mapping[str, Any]],
    checks: Checks,
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    checks.require(isinstance(crosswalks, dict) and list(crosswalks) == ["202b", "202c"],
                   "crosswalk.inventory")
    emar_rows = boundaries["emar_medication"]["source_rows"]
    detail_rows = boundaries["detail_product_description"]["source_rows"]
    pharmacy_rows = boundaries["pharmacy_medication"]["source_rows"]
    prescription_rows = boundaries["prescription_drug"]["source_rows"]
    checks.require(
        detail_rows
        == boundaries["detail_product_description_other"]["source_rows"]
        == boundaries["emar_detail_route"]["source_rows"],
        "crosswalk.emar_detail_boundary_denominator",
    )
    checks.require(
        pharmacy_rows == boundaries["pharmacy_route"]["source_rows"],
        "crosswalk.pharmacy_boundary_denominator",
    )
    checks.require(
        prescription_rows
        == boundaries["prescriptions_route"]["source_rows"]
        == boundaries["prescriptions_ndc"]["source_rows"],
        "crosswalk.prescriptions_boundary_denominator",
    )
    expected_global_inputs = {
        "202b": detail_rows,
        "202c": emar_rows + detail_rows + pharmacy_rows + prescription_rows,
    }
    checks.require(expected_global_inputs["202c"] <= MAX_COUNT,
                   "crosswalk.boundary_denominator_limit")
    rebuilt: dict[str, dict[str, Any]] = {}
    private_strings: set[str] = set()
    top_keys = {
        "bucket_count", "bucket_indices_complete", "assignment_unit",
        "sql_null_subject_bucket", "bucket_assignment_violations",
        "null_subject_outside_bucket_zero", "global_input_rows",
        "global_input_rows_source",
        "summed_bucket_input_rows", "global_output_multiplicity",
        "mutual_exclusion_and_completeness_confirmed", "unique_tuples",
        "global_tuple_set_sha256", "global_tuple_frequency_sha256",
        "tuple_kind_summaries", "records",
    }
    summary_keys = {
        "unique_tuples", "total_multiplicity", "summed_bucket_input_rows",
        "summed_bucket_tuple_multiplicity", "global_tuple_set_sha256",
        "global_tuple_frequency_sha256",
    }
    for stage in ("202b", "202c"):
        source = crosswalks[stage]
        checks.require(isinstance(source, dict) and set(source) == top_keys,
                       f"crosswalk.{stage}_schema")
        for key, expected in {
            "bucket_count": BUCKET_COUNT,
            "bucket_indices_complete": True,
            "assignment_unit": "subject_id",
            "sql_null_subject_bucket": 0,
            "bucket_assignment_violations": 0,
            "null_subject_outside_bucket_zero": 0,
            "global_input_rows_source": "same_snapshot_202a_boundary_source_rows",
            "mutual_exclusion_and_completeness_confirmed": True,
        }.items():
            checks.require(source.get(key) == expected, f"crosswalk.{stage}_{key}")
        global_input = source.get("global_input_rows")
        summed_input = source.get("summed_bucket_input_rows")
        checks.require(type(global_input) is int and 0 <= global_input <= MAX_COUNT,
                       f"crosswalk.{stage}_global_input")
        checks.require(global_input == expected_global_inputs[stage],
                       f"crosswalk.{stage}_boundary_denominator")
        checks.require(summed_input == global_input,
                       f"crosswalk.{stage}_bucket_conservation")
        records = source.get("records")
        checks.require(isinstance(records, list), f"crosswalk.{stage}_records")
        kinds = TUPLE_FIELDS[stage]
        rebuilt_records: list[dict[str, Any]] = []
        observed_encoded: list[bytes] = []
        for record_index, record in enumerate(records):
            label = f"crosswalk.{stage}_record_{record_index}"
            checks.require(isinstance(record, dict) and set(record) == {
                "tuple_kind", "tuple", "multiplicity"
            }, label + "_schema")
            kind = record.get("tuple_kind")
            value = record.get("tuple")
            multiplicity = record.get("multiplicity")
            checks.require(kind in kinds, label + "_kind")
            checks.require(isinstance(value, dict) and list(value) == sorted(
                kinds[kind], key=lambda item: item.encode("utf-8")
            ), label + "_field_order")
            checks.require(set(value) == set(kinds[kind]), label + "_field_set")
            checks.require(not (set(value) & FORBIDDEN_TUPLE_FIELDS), label + "_privacy")
            checks.require(all(item is None or isinstance(item, str) for item in value.values()),
                           label + "_typed_values")
            checks.require(all(
                value.get(field) in allowed
                for field, allowed in ENUM_FIELDS_BY_KIND.get((stage, kind), {}).items()
            ), label + "_categorical_values")
            if kind == "ndc_external_mapping_input":
                checks.require(isinstance(value.get("ndc"), str),
                               label + "_nonnull_ndc_candidate")
            checks.require(type(multiplicity) is int and 1 <= multiplicity <= MAX_COUNT,
                           label + "_multiplicity")
            canonical_json = json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            checks.require(len(canonical_json) <= MAX_TUPLE_JSON_BYTES,
                           label + "_json_limit")
            encoded = _encode_tuple(stage, kind, value)
            observed_encoded.append(encoded)
            rebuilt_records.append({
                "tuple_kind": kind,
                "tuple": value,
                "multiplicity": multiplicity,
                "encoded_tuple": encoded,
            })
            categorical_fields = ENUM_FIELDS_BY_KIND.get((stage, kind), {})
            for field, item in value.items():
                if (
                    field not in categorical_fields
                    and isinstance(item, str)
                    and len(item) >= 12
                ):
                    private_strings.add(item)
        checks.require(observed_encoded == sorted(observed_encoded),
                       f"crosswalk.{stage}_global_sort")
        checks.require(len(observed_encoded) == len(set(observed_encoded)),
                       f"crosswalk.{stage}_unique")
        set_hash, frequency_hash = _tuple_hashes(stage, rebuilt_records)
        total = sum(item["multiplicity"] for item in rebuilt_records)
        checks.require(total <= MAX_COUNT, f"crosswalk.{stage}_total_limit")
        checks.require(source.get("unique_tuples") == len(rebuilt_records),
                       f"crosswalk.{stage}_unique_count")
        checks.require(source.get("global_output_multiplicity") == total,
                       f"crosswalk.{stage}_output_total")
        checks.require(source.get("global_tuple_set_sha256") == set_hash,
                       f"crosswalk.{stage}_set_hash")
        checks.require(source.get("global_tuple_frequency_sha256") == frequency_hash,
                       f"crosswalk.{stage}_frequency_hash")
        observed_summaries = source.get("tuple_kind_summaries")
        checks.require(isinstance(observed_summaries, dict)
                       and set(observed_summaries) == set(kinds),
                       f"crosswalk.{stage}_kind_inventory")
        kind_summaries: dict[str, dict[str, Any]] = {}
        for kind in kinds:
            selected = [item for item in rebuilt_records if item["tuple_kind"] == kind]
            kind_set, kind_frequency = _tuple_hashes(stage + ":" + kind, selected)
            kind_total = sum(item["multiplicity"] for item in selected)
            observed = observed_summaries[kind]
            checks.require(isinstance(observed, dict) and set(observed) == summary_keys,
                           f"crosswalk.{stage}_{kind}_schema")
            expected = {
                "unique_tuples": len(selected),
                "total_multiplicity": kind_total,
                "summed_bucket_input_rows": kind_total,
                "summed_bucket_tuple_multiplicity": kind_total,
                "global_tuple_set_sha256": kind_set,
                "global_tuple_frequency_sha256": kind_frequency,
            }
            checks.require(observed == expected,
                           f"crosswalk.{stage}_{kind}_conservation")
            kind_summaries[kind] = expected
        rebuilt[stage] = {
            "bucket_count": BUCKET_COUNT,
            "bucket_indices_complete": True,
            "assignment_unit": "subject_id",
            "sql_null_subject_bucket": 0,
            "bucket_assignment_violations": 0,
            "null_subject_outside_bucket_zero": 0,
            "global_input_rows": global_input,
            "global_input_rows_source": "same_snapshot_202a_boundary_source_rows",
            "summed_bucket_input_rows": summed_input,
            "global_output_multiplicity": total,
            "mutual_exclusion_and_completeness_confirmed": True,
            "unique_tuples": len(rebuilt_records),
            "global_tuple_set_sha256": set_hash,
            "global_tuple_frequency_sha256": frequency_hash,
            "tuple_kind_summaries": kind_summaries,
        }
    return rebuilt, private_strings


def _statement_body(sql: str) -> str:
    """Independently remove the sole terminal semicolon from reviewed SQL."""
    stripped = sql.strip()
    if not stripped.endswith(";"):
        raise AuditContractError("sql.template_terminator")
    return stripped[:-1].rstrip()


def _template_control_names(sql: str) -> tuple[str, ...]:
    """Extract only literal control names from the frozen controls CTE."""
    start = "controls(control_name, control_value) AS MATERIALIZED (\n"
    end = "\n)\nSELECT 2"
    if sql.count(start) != 1:
        raise AuditContractError("sql.controls_cte_start")
    tail = sql.split(start, 1)[1]
    if tail.count(end) != 1:
        raise AuditContractError("sql.controls_cte_end")
    body = tail.split(end, 1)[0]
    return tuple(re.findall(r"(?m)^\s*SELECT '([^']+)'", body))


def _validate_executed_sql(
    root: Path,
    payload: bytes,
    checks: Checks,
) -> list[bytes]:
    checks.require(0 < len(payload) <= MAX_EXECUTED_SQL_BYTES, "sql.byte_limit")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuditContractError("sql.utf8") from exc
    checks.require(text.count("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;") == 1,
                   "sql.one_readonly_rr_begin")
    checks.require(text.count("SET LOCAL statement_timeout = '120000ms';") == STATEMENT_COUNT,
                   "sql.timeout_count")
    checks.require(text.count("ROLLBACK;") == 1, "sql.one_rollback")
    checks.require(text.rstrip().endswith("\\q"), "sql.clean_quit")
    checks.require(BUCKET_MARKER not in text, "sql.no_unresolved_marker")
    for setting in (
        "SET LOCAL client_encoding = 'UTF8';",
        "SET LOCAL DateStyle = 'ISO, YMD';",
        "SET LOCAL TimeZone = 'UTC';",
        "SET LOCAL IntervalStyle = 'postgres';",
        "SET LOCAL extra_float_digits = 3;",
    ):
        checks.require(text.count(setting) == 1, "sql.session_setting")
    for index, relative in enumerate(BOUNDARY_SQL_PATHS):
        body = _statement_body((root / relative).read_text(encoding="utf-8"))
        checks.require(text.count(body) == 1, f"sql.boundary_body_{index}")
    for stage_offset, spec in enumerate(BUCKET_STATEMENT_SPECS):
        template = (root / spec["path"]).read_text(encoding="utf-8")
        physical_stage = spec["stage"]
        logical_stage = spec["logical_stage"]
        checks.require(template.count(BUCKET_MARKER) == 1,
                       f"sql.bucket_template_{stage_offset}")
        checks.require("global_input_rows" not in template,
                       f"sql.{physical_stage}_no_repeated_global_input")
        checks.require(
            template.count("'" + physical_stage + "'") == 2,
            f"sql.{physical_stage}_stage_identity",
        )
        expected_controls = set(PHYSICAL_CONTROL_NAMES[physical_stage])
        checks.require(
            _template_control_names(template)
            == PHYSICAL_CONTROL_NAMES[physical_stage],
            f"sql.{physical_stage}_exact_control_inventory",
        )
        for control_name in CONTROL_NAMES[logical_stage]:
            checks.require(
                template.count("'" + control_name + "'")
                == (1 if control_name in expected_controls else 0),
                f"sql.{physical_stage}_control_inventory",
            )
        for bucket in range(BUCKET_COUNT):
            rendered = _statement_body(template.replace(BUCKET_MARKER, str(bucket)))
            checks.require(text.count(rendered) == 1,
                           f"sql.bucket_body_{stage_offset}_{bucket}")
    lowered = text.lower()
    for token in ("create ", "insert ", "update ", "delete ", "merge ", "alter ",
                  "drop ", "truncate ", "copy ", "temporary ", "tablesample"):
        checks.require(token not in lowered, "sql.no_mutation_or_sampling")
    echo_matches = list(re.finditer(rb"(?m)^\\echo [^\r\n]+\n", payload))
    checks.require(
        len(echo_matches) == STATEMENT_COUNT + 1,
        "sql.control_marker_count",
    )
    if len(echo_matches) != STATEMENT_COUNT + 1:
        return []
    controls: list[bytes] = []
    start = 0
    for marker in echo_matches[:STATEMENT_COUNT]:
        controls.append(payload[start:marker.end()])
        start = marker.end()
    rollback = payload[start:echo_matches[-1].end()]
    checks.require(rollback.startswith(b"ROLLBACK;\n"), "sql.rollback_control")
    checks.require(
        payload[echo_matches[-1].end():] == b"\\q\n",
        "sql.exact_quit_control",
    )
    return controls


def _validate_manifest_stages(
    root: Path,
    manifest: Mapping[str, Any],
    entry: Mapping[str, Any],
    private: Mapping[str, Any],
    executed_controls: list[bytes],
    checks: Checks,
) -> None:
    stages = entry.get("stages")
    order = entry.get("stage_order")
    expected_order = [*BOUNDARY_STAGES]
    for spec in BUCKET_STATEMENT_SPECS:
        expected_order.extend(
            f"{spec['stage']}_bucket_{index}"
            for index in range(BUCKET_COUNT)
        )
    checks.require(isinstance(stages, dict) and set(stages) == set(expected_order),
                   "manifest.stage_inventory")
    checks.require(order == expected_order, "manifest.stage_order")
    snapshot = private["transaction"]["snapshot_token_sha256"]
    input_sums = {"202b": 0, "202c": 0}
    output_sums = {"202b": 0, "202c": 0}
    physical_input_sums = {
        spec["stage"]: 0
        for spec in BUCKET_STATEMENT_SPECS
        if spec["bucket_input_source"] is not None
    }
    physical_output_sums = {
        spec["stage"]: 0 for spec in BUCKET_STATEMENT_SPECS
    }
    logical_bucket_frame_bytes = {
        (logical_stage, bucket): 0
        for logical_stage in ("202b", "202c")
        for bucket in range(BUCKET_COUNT)
    }
    logical_bucket_groups = dict.fromkeys(logical_bucket_frame_bytes, 0)
    logical_bucket_multiplicity = dict.fromkeys(logical_bucket_frame_bytes, 0)
    checks.require(len(executed_controls) == len(expected_order),
                   "manifest.control_inventory")
    for ordinal, label in enumerate(expected_order):
        stage = stages[label]
        checks.require(isinstance(stage, dict), "manifest.stage_table")
        checks.require(stage.get("status") == "complete", "manifest.stage_complete")
        checks.require(stage.get("statement_timeout_ms") == STATEMENT_TIMEOUT_MS,
                       "manifest.stage_timeout")
        checks.require(stage.get("process_timeout_seconds") == PROCESS_TIMEOUT_SECONDS,
                       "manifest.stage_watchdog")
        elapsed = stage.get("elapsed_seconds")
        checks.require(isinstance(elapsed, (int, float)) and 0 <= elapsed <= PROCESS_TIMEOUT_SECONDS,
                       "manifest.stage_elapsed")
        checks.require(stage.get("observed_transaction_isolation") == "repeatable read",
                       "manifest.stage_rr")
        checks.require(stage.get("observed_transaction_read_only") == "on",
                       "manifest.stage_ro")
        checks.require(stage.get("observed_snapshot_sha256") == snapshot,
                       "manifest.stage_snapshot")
        checks.require(isinstance(stage.get("template_sha256"), str)
                       and SHA256_RE.fullmatch(stage["template_sha256"]) is not None,
                       "manifest.stage_template_hash")
        checks.require(isinstance(stage.get("control_sha256"), str)
                       and SHA256_RE.fullmatch(stage["control_sha256"]) is not None,
                       "manifest.stage_control_hash")
        if ordinal < len(executed_controls):
            checks.require(
                stage.get("control_sha256")
                == _sha_bytes(executed_controls[ordinal]),
                "manifest.stage_control_hash_exact",
            )
            checks.require(
                stage.get("control_bytes") == len(executed_controls[ordinal]),
                "manifest.stage_control_bytes_exact",
            )
        checks.require(
            type(stage.get("template_bytes")) is int
            and stage["template_bytes"] > 0,
            "manifest.stage_template_bytes",
        )
        checks.require(
            type(stage.get("control_bytes")) is int
            and 0 < stage["control_bytes"] <= MAX_EXECUTED_SQL_BYTES,
            "manifest.stage_control_bytes",
        )
        checks.require(
            type(stage.get("spool_bytes")) is int
            and 0 < stage["spool_bytes"] <= MAX_CUMULATIVE_SPOOL_BYTES,
            "manifest.stage_spool_bytes",
        )
        if "_bucket_" in label:
            physical_stage, bucket_text = label.rsplit("_bucket_", 1)
            bucket = int(bucket_text)
            spec = BUCKET_STATEMENT_BY_STAGE[physical_stage]
            logical_stage = spec["logical_stage"]
            expected_stage_keys = (
                PHYSICAL_BUCKET_OWNER_STAGE_KEYS
                if spec["bucket_input_source"] is not None
                else PHYSICAL_BUCKET_STAGE_KEYS
            )
            checks.require(set(stage) == expected_stage_keys,
                           "manifest.bucket_exact_schema")
            checks.require(
                stage.get("stage") == physical_stage
                and stage.get("bucket_index") == bucket,
                           "manifest.bucket_identity")
            checks.require(stage.get("file") == spec["path"],
                           "manifest.bucket_file")
            template_path = root / spec["path"]
            checks.require(stage.get("template_sha256") == _sha_file(template_path),
                           "manifest.bucket_template_hash")
            checks.require(
                stage.get("template_bytes") == template_path.stat().st_size,
                "manifest.bucket_template_bytes",
            )
            template = template_path.read_text(encoding="utf-8")
            rendered = _statement_body(template.replace(BUCKET_MARKER, str(bucket)))
            checks.require(
                stage.get("rendered_statement_sha256")
                == _sha_bytes(rendered.encode("utf-8")),
                "manifest.bucket_rendered_hash",
            )
            rows = stage.get("rows")
            frame_bytes = stage.get("frame_bytes")
            multiplicity = stage.get("tuple_multiplicity")
            checks.require(
                type(rows) is int and 0 <= rows <= MAX_TUPLE_GROUPS_PER_BUCKET,
                "manifest.bucket_rows",
            )
            checks.require(
                type(frame_bytes) is int
                and 0 < frame_bytes <= MAX_CROSSWALK_FRAME_BYTES,
                "manifest.bucket_frame_bytes",
            )
            checks.require(
                type(multiplicity) is int and 0 <= multiplicity <= MAX_COUNT,
                "manifest.bucket_multiplicity",
            )
            checks.require(
                type(rows) is int
                and type(multiplicity) is int
                and rows <= multiplicity
                and ((rows == 0) == (multiplicity == 0)),
                "manifest.bucket_group_multiplicity_relation",
            )
            bucket_key = (logical_stage, bucket)
            safe_frame_bytes = (
                frame_bytes if type(frame_bytes) is int and frame_bytes > 0
                else MAX_CROSSWALK_FRAME_BYTES + 1
            )
            safe_rows = (
                rows if type(rows) is int and rows >= 0
                else MAX_TUPLE_GROUPS_PER_BUCKET + 1
            )
            safe_multiplicity = (
                multiplicity if type(multiplicity) is int and multiplicity >= 0
                else MAX_COUNT + 1
            )
            logical_bucket_frame_bytes[bucket_key] += safe_frame_bytes
            logical_bucket_groups[bucket_key] += safe_rows
            logical_bucket_multiplicity[bucket_key] += safe_multiplicity
            checks.require(
                logical_bucket_frame_bytes[bucket_key]
                <= MAX_CROSSWALK_FRAME_BYTES,
                "manifest.logical_bucket_frame_bytes",
            )
            checks.require(
                logical_bucket_groups[bucket_key]
                <= MAX_TUPLE_GROUPS_PER_BUCKET,
                "manifest.logical_bucket_groups",
            )
            checks.require(
                logical_bucket_multiplicity[bucket_key] <= MAX_COUNT,
                "manifest.logical_bucket_multiplicity",
            )
            if spec["bucket_input_source"] is not None:
                checks.require(stage.get("bucket_assignment_violations") == 0,
                               "manifest.bucket_assignment")
                checks.require(stage.get("null_subject_outside_bucket_zero") == 0,
                               "manifest.null_bucket")
                bucket_input = stage.get("bucket_input_rows")
                checks.require(
                    type(bucket_input) is int and 0 <= bucket_input <= MAX_COUNT,
                    "manifest.bucket_input_rows",
                )
                input_sums[logical_stage] += (
                    bucket_input
                    if type(bucket_input) is int and bucket_input >= 0
                    else MAX_COUNT + 1
                )
                physical_input_sums[physical_stage] += (
                    bucket_input
                    if type(bucket_input) is int and bucket_input >= 0
                    else MAX_COUNT + 1
                )
            else:
                checks.require(
                    all(name not in stage for name in (
                        "bucket_assignment_violations",
                        "null_subject_outside_bucket_zero",
                        "bucket_input_rows",
                    )),
                    "manifest.nonowner_input_controls_absent",
                )
            output_sums[logical_stage] += safe_multiplicity
            physical_output_sums[physical_stage] += safe_multiplicity
        else:
            index = BOUNDARY_STAGES.index(label)
            boundary = private["boundaries"][SOURCE_KEYS[index]]
            checks.require(set(stage) == BOUNDARY_STAGE_KEYS,
                           "manifest.boundary_exact_schema")
            checks.require(stage.get("stage") == label and stage.get("bucket_index") is None,
                           "manifest.boundary_identity")
            checks.require(stage.get("file") == BOUNDARY_SQL_PATHS[index],
                           "manifest.boundary_file")
            checks.require(
                stage.get("template_sha256")
                == _sha_file(root / BOUNDARY_SQL_PATHS[index]),
                "manifest.boundary_template_hash",
            )
            checks.require(
                stage.get("template_bytes")
                == (root / BOUNDARY_SQL_PATHS[index]).stat().st_size,
                "manifest.boundary_template_bytes",
            )
            checks.require(stage.get("rows") == boundary["typed_distinct_values"],
                           "manifest.boundary_rows")
            checks.require(stage.get("source_rows") == boundary["source_rows"],
                           "manifest.boundary_source_rows")
            checks.require(stage.get("typed_set_sha256") == boundary["typed_set_sha256"],
                           "manifest.boundary_hash")
            checks.require(
                type(stage.get("frame_bytes")) is int
                and 0 < stage["frame_bytes"] <= MAX_BOUNDARY_FRAME_BYTES,
                "manifest.boundary_frame_bytes",
            )
    for stage in ("202b", "202c"):
        source = private["crosswalks"][stage]
        checks.require(input_sums[stage] == source["summed_bucket_input_rows"],
                       f"manifest.{stage}_input_sum")
        checks.require(output_sums[stage] == source["global_output_multiplicity"],
                       f"manifest.{stage}_output_sum")
    for spec in BUCKET_STATEMENT_SPECS:
        physical_stage = spec["stage"]
        logical_stage = spec["logical_stage"]
        expected_output = sum(
            private["crosswalks"][logical_stage]["tuple_kind_summaries"][kind][
                "summed_bucket_tuple_multiplicity"
            ]
            for kind in spec["tuple_kinds"]
        )
        checks.require(
            physical_output_sums[physical_stage] == expected_output,
            f"manifest.{physical_stage}_output_sum",
        )
        if spec["bucket_input_source"] is not None:
            boundary_key = INPUT_SOURCE_BOUNDARY_KEY[spec["bucket_input_source"]]
            expected_input = private["boundaries"][boundary_key]["source_rows"]
            checks.require(
                physical_input_sums[physical_stage] == expected_input,
                f"manifest.{physical_stage}_input_sum",
            )
    checks.require(manifest.get("elapsed_seconds") == entry.get("elapsed_seconds"),
                   "manifest.elapsed_match")


def _validate_git_ignore(root: Path, directory: Path, checks: Checks) -> None:
    try:
        relative = directory.relative_to(root)
    except ValueError as exc:
        raise AuditContractError("privacy.artifact_inside_root") from exc
    checks.require(relative.parts and relative.parts[0] == "artifacts",
                   "privacy.artifact_under_artifacts")
    ignore = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    checks.require(any(line.strip() in {"artifacts/*", "artifacts/"} for line in ignore),
                   "privacy.gitignored")


def _audit_complete_artifact(root: Path, directory: Path, checks: Checks) -> dict[str, Any]:
    checks.require(directory.is_dir() and not directory.is_symlink(),
                   "permissions.directory_regular")
    checks.require(_mode(directory) == "0700", "permissions.directory_0700")
    _validate_git_ignore(root, directory, checks)

    manifest_path = directory / "manifest.json"
    manifest, manifest_bytes = _read_json(
        manifest_path, 64 * 1024 * 1024, "manifest"
    )
    checks.require(_mode(manifest_path) == "0600", "permissions.manifest_0600")
    checks.require(
        type(manifest.get("schema_version")) is int
        and manifest.get("schema_version") == 2,
        "manifest.schema_version",
    )
    checks.require(manifest.get("status") == "complete", "manifest.complete")
    checks.require(manifest.get("selected_queries") == [QUERY_NAME],
                   "manifest.query_inventory")
    checks.require(manifest.get("scope") ==
                   "complete_local_pre_adjudication_boundary_and_crosswalk_evidence",
                   "manifest.scope")
    checks.require(set(manifest) == {
        "schema_version", "started_at_utc", "finished_at_utc",
        "elapsed_seconds", "status", "scope", "selected_queries",
        "requested_controls", "confirmed_controls", "artifact_modes",
        "component_preregistration", "implementation_bundles", "queries",
        "guards", "limitations",
    }, "manifest.exact_schema")
    queries = manifest.get("queries")
    checks.require(isinstance(queries, list) and len(queries) == 1
                   and isinstance(queries[0], dict), "manifest.one_query")
    entry = queries[0]
    checks.require(set(entry) == {
        "query", "status", "stage_order", "stages", "psql_returncode",
        "private_values_persisted", "executed_sql_persisted",
        "aggregate_summary_persisted", "private_values_file",
        "private_values_encoding", "private_values_sha256",
        "private_values_bytes", "private_values_raw_sha256",
        "private_values_raw_bytes", "private_values_records",
        "executed_sql_file", "executed_sql_sha256", "executed_sql_bytes",
        "aggregate_summary_file", "aggregate_summary_sha256",
        "aggregate_summary_bytes", "boundary_summaries",
        "semantic_seed_summary", "crosswalk_summaries",
        "snapshot_token_sha256", "cumulative_frame_bytes",
        "cumulative_spool_bytes", "cumulative_merge_run_raw_bytes",
        "cumulative_merge_run_spool_bytes", "merge_run_ledger",
        "cumulative_control_bytes", "finished_at_utc", "elapsed_seconds",
    }, "manifest.query_exact_schema")
    checks.require(entry.get("query") == QUERY_NAME and entry.get("status") == "complete",
                   "manifest.query_complete")
    checks.require(entry.get("psql_returncode") == 0, "manifest.psql_zero")
    for key in ("private_values_persisted", "executed_sql_persisted",
                "aggregate_summary_persisted"):
        checks.require(entry.get(key) is True, "manifest." + key)

    paths = {
        "private": _safe_filename(directory, entry.get("private_values_file"),
                                  "manifest.private"),
        "executed": _safe_filename(directory, entry.get("executed_sql_file"),
                                   "manifest.executed"),
        "summary": _safe_filename(directory, entry.get("aggregate_summary_file"),
                                  "manifest.summary"),
    }
    entry_prefix = {
        "private": "private_values",
        "executed": "executed_sql",
        "summary": "aggregate_summary",
    }
    checks.require(
        not ({"stderr_file", "stderr_sha256", "stderr_bytes"} & set(entry)),
        "manifest.no_database_stderr_artifact",
    )
    for role, path in paths.items():
        prefix = entry_prefix[role]
        checks.require(_mode(path) == "0600", f"permissions.{role}_0600")
        checks.require(path.stat().st_size == entry.get(prefix + "_bytes"),
                       f"files.{role}_bytes")
        # The private gzip is hashed during its bounded decompression pass;
        # avoid rereading a potentially 4 GiB file solely for the same digest.
        if role != "private":
            checks.require(_sha_file(path) == entry.get(prefix + "_sha256"),
                           f"files.{role}_sha256")
    checks.require(paths["private"].stat().st_size <= MAX_PRIVATE_STORED_BYTES,
                   "files.private_limit")
    checks.require(paths["private"].name.endswith(".private.jsonl.gz"),
                   "files.private_filename")
    checks.require(paths["executed"].stat().st_size <= MAX_EXECUTED_SQL_BYTES,
                   "files.executed_limit")
    expected_artifact_names = {
        "manifest.json", *(path.name for path in paths.values())
    }
    checks.require(
        all(item.is_file() and not item.is_symlink() for item in directory.iterdir())
        and {item.name for item in directory.iterdir()} == expected_artifact_names,
        "files.exact_inventory",
    )

    summary, summary_bytes = _read_json(paths["summary"], 128 * 1024 * 1024, "summary")
    executed_bytes = paths["executed"].read_bytes()

    streamed_private = _stream_private_artifact(
        paths["private"],
        entry,
        _public_strings(summary) | _public_strings(manifest),
        checks,
    )
    private = streamed_private["private"]

    expected_private_keys = {
        "schema_version", "query", "created_at_utc", "component_lineage",
        "transaction", "hash_contracts", "boundaries", "semantic_seed",
        "crosswalks", "privacy", "guards",
    }
    checks.require(set(private) == expected_private_keys, "private.schema")
    checks.require(type(private.get("schema_version")) is int
                   and private.get("schema_version") == 2
                   and type(private.get("query")) is str
                   and private.get("query") == QUERY_NAME,
                   "private.identity")
    expected_summary_keys = {
        "schema_version", "query", "created_at_utc", "scope", "component_lineage",
        "boundary_summaries", "semantic_seed_summary", "crosswalk_summaries",
        "transaction_controls", "privacy", "guards", "private_artifact_hashes",
    }
    checks.require(set(summary) == expected_summary_keys, "summary.schema")
    checks.require(type(summary.get("schema_version")) is int
                   and summary.get("schema_version") == 2
                   and type(summary.get("query")) is str
                   and summary.get("query") == QUERY_NAME,
                   "summary.identity")
    timeline = tuple(_parse_utc(value) for value in (
        manifest.get("started_at_utc"),
        private.get("created_at_utc"),
        summary.get("created_at_utc"),
        entry.get("finished_at_utc"),
        manifest.get("finished_at_utc"),
    ))
    checks.require(all(value is not None for value in timeline), "time.utc_timestamps")
    checks.require(
        all(value is not None for value in timeline)
        and all(
            left <= right
            for left, right in zip(timeline, timeline[1:])
        ),
        "time.lifecycle_order",
    )
    checks.require(
        _finite_nonnegative(entry.get("elapsed_seconds"))
        and _finite_nonnegative(manifest.get("elapsed_seconds"))
        and type(entry.get("elapsed_seconds"))
        is type(manifest.get("elapsed_seconds"))
        and entry.get("elapsed_seconds") == manifest.get("elapsed_seconds"),
        "time.elapsed_seconds",
    )

    config_path = root / CONFIG_PATH
    checks.require(config_path.is_file() and not config_path.is_symlink(),
                   "config.present")
    with config_path.open("rb") as handle:
        config = tomllib.load(handle)
    config_hash = _sha_file(config_path)
    bundles = implementation_bundles(root)
    _validate_config(root, config, bundles, checks)

    lineage = private.get("component_lineage")
    checks.require(
        isinstance(lineage, dict)
        and _strict_json_equal(lineage, summary.get("component_lineage")),
                   "lineage.private_summary")
    checks.require(_strict_json_equal(lineage, {
        "component_id": COMPONENT_ID,
        "status_at_execution": "frozen_for_execution",
        "config": str(CONFIG_PATH),
        "config_sha256": config_hash,
    }), "lineage.config")
    manifest_lineage = manifest.get("component_preregistration")
    checks.require(isinstance(manifest_lineage, dict), "lineage.manifest_table")
    checks.require(manifest_lineage.get("component_id") == COMPONENT_ID,
                   "lineage.manifest_component")
    checks.require(manifest_lineage.get("status_at_start") == "frozen_for_execution",
                   "lineage.manifest_status")
    checks.require(manifest_lineage.get("execution_status_at_start") == "not_executed",
                   "lineage.manifest_not_executed")
    checks.require(manifest_lineage.get("execution_permitted_at_start") is True,
                   "lineage.manifest_permitted")
    checks.require(manifest_lineage.get("config") == str(CONFIG_PATH)
                   and manifest_lineage.get("config_sha256") == config_hash,
                   "lineage.manifest_config")
    checks.require(manifest_lineage.get("implementation_hashes_verified") is True,
                   "lineage.manifest_bundles_verified")
    checks.require(manifest.get("implementation_bundles") == bundles,
                   "lineage.manifest_bundle_details")

    transaction = private.get("transaction")
    expected_transaction = {
        "isolation": "repeatable read", "read_only": True, "same_snapshot": True,
        "rollback_confirmed_before_persistence": True,
        "clean_psql_exit_confirmed_before_persistence": True,
    }
    checks.require(isinstance(transaction, dict), "transaction.private_table")
    snapshot_hash = transaction.get("snapshot_token_sha256") if isinstance(
        transaction, dict
    ) else None
    checks.require(isinstance(snapshot_hash, str)
                   and SHA256_RE.fullmatch(snapshot_hash) is not None,
                   "transaction.snapshot_hash")
    checks.require(
        isinstance(transaction, dict)
        and set(transaction) == {*expected_transaction, "snapshot_token_sha256"},
        "transaction.private_exact_schema",
    )
    for key, expected in expected_transaction.items():
        checks.require(
            isinstance(transaction, dict)
            and _strict_json_equal(transaction.get(key), expected),
            "transaction." + key,
        )
    checks.require(entry.get("snapshot_token_sha256") == snapshot_hash,
                   "transaction.manifest_snapshot")
    checks.require(_strict_json_equal(summary.get("transaction_controls"), transaction),
                   "transaction.summary_match")
    requested = manifest.get("requested_controls")
    confirmed = manifest.get("confirmed_controls")
    checks.require(isinstance(requested, dict) and isinstance(confirmed, dict),
                   "transaction.manifest_controls")
    expected_requested = {
        "read_only": True, "same_snapshot": True,
        "transaction_isolation": "repeatable read",
        "statement_timeout_ms_per_sql": STATEMENT_TIMEOUT_MS,
        "sql_statement_count": STATEMENT_COUNT,
        "boundary_statement_count": 9,
        "bucket_count_per_crosswalk_stage": BUCKET_COUNT,
        "explicit_rollback": True,
        "clean_psql_exit_before_value_persistence": True,
        "anonymous_frame_spool_before_rollback": True,
        "anonymous_sorted_run_spool_after_rollback": True,
        "database_stderr_persisted": False,
        "database_writes_or_session_objects": False,
        "external_api_calls": False,
    }
    checks.require(
        isinstance(requested, dict)
        and set(requested) == {
            *expected_requested, "session_format_settings", "limits"
        },
        "transaction.requested_schema",
    )
    for key, expected in expected_requested.items():
        checks.require(
            _strict_json_equal(requested.get(key), expected),
            "transaction.requested_" + key,
        )
    checks.require(_strict_json_equal(requested.get("session_format_settings"), {
        "client_encoding": "UTF8",
        "DateStyle": "ISO, YMD",
        "TimeZone": "UTC",
        "IntervalStyle": "postgres",
        "extra_float_digits": "3",
    }), "transaction.requested_session_settings")
    checks.require(_strict_json_equal(requested.get("limits"), {
        "boundary_frame_bytes": MAX_BOUNDARY_FRAME_BYTES,
        "crosswalk_frame_bytes": MAX_CROSSWALK_FRAME_BYTES,
        "raw_frame_bytes": MAX_CUMULATIVE_RAW_FRAME_BYTES,
        "total_anonymous_spool_bytes": MAX_CUMULATIVE_SPOOL_BYTES,
        "merge_run_raw_bytes": MAX_MERGE_RUN_RAW_BYTES,
        "merge_run_spool_bytes": MAX_MERGE_RUN_SPOOL_BYTES,
        "private_artifact_raw_bytes": MAX_PRIVATE_RAW_BYTES,
        "private_artifact_stored_bytes": MAX_PRIVATE_STORED_BYTES,
        "private_artifact_line_bytes": MAX_PRIVATE_LINE_BYTES,
        "tuple_json_utf8_bytes": MAX_TUPLE_JSON_BYTES,
        "executed_sql_bytes": MAX_EXECUTED_SQL_BYTES,
        "boundary_groups_per_field": MAX_BOUNDARY_GROUPS,
        "tuple_groups_per_bucket": MAX_TUPLE_GROUPS_PER_BUCKET,
        "exact_count_or_multiplicity": MAX_COUNT,
    }), "transaction.requested_limits")
    expected_confirmed = {
        "read_only": True, "same_snapshot": True,
        "transaction_isolation": "repeatable read", "rollback": True,
        "clean_psql_exit": True, "anonymous_frame_spool": True,
        "anonymous_sorted_run_spool": True,
        "database_stderr_discarded": True,
        "session_format_settings_applied": True,
        "external_api_calls": False,
    }
    checks.require(isinstance(confirmed, dict) and set(confirmed) == set(expected_confirmed),
                   "transaction.confirmed_schema")
    for key, expected in expected_confirmed.items():
        checks.require(
            _strict_json_equal(confirmed.get(key), expected),
            "transaction.confirmed_" + key,
        )

    hashes = private.get("hash_contracts")
    checks.require(_strict_json_equal(hashes, {
        "typed_boundary_set": BOUNDARY_SET_VERSION.decode("ascii"),
        "semantic_seed_set": SEMANTIC_SET_VERSION.decode("ascii"),
        "typed_tuple_encoding": TUPLE_ENCODING_VERSION.decode("ascii"),
        "global_tuple_set": TUPLE_SET_VERSION.decode("ascii"),
        "global_tuple_frequency": TUPLE_FREQUENCY_VERSION.decode("ascii"),
        "global_hashes_recomputed_from_merged_exact_tuples": True,
        "partition_hash_concatenation_allowed": False,
    }), "hash.contracts")

    boundary_summary = streamed_private["boundary_summary"]
    seed_summary = streamed_private["seed_summary"]
    crosswalk_summary = streamed_private["crosswalk_summary"]
    private_seed = private.get("semantic_seed")
    checks.require(isinstance(private_seed, dict) and set(private_seed) == set(seed_summary),
                   "seed.private_schema")
    checks.require(
        isinstance(private_seed, dict)
        and _strict_json_equal(
            {key: private_seed.get(key) for key in seed_summary}, seed_summary
        ),
        "seed.private_summary",
    )
    checks.require(_strict_json_equal(
        summary.get("boundary_summaries"), boundary_summary
    ),
                   "summary.boundaries_rebuilt")
    checks.require(_strict_json_equal(
        summary.get("semantic_seed_summary"), seed_summary
    ),
                   "summary.seed_rebuilt")
    checks.require(_strict_json_equal(
        summary.get("crosswalk_summaries"), crosswalk_summary
    ),
                   "summary.crosswalks_rebuilt")
    checks.require(_strict_json_equal(entry.get("boundary_summaries"), boundary_summary),
                   "manifest.boundaries_rebuilt")
    checks.require(_strict_json_equal(entry.get("semantic_seed_summary"), seed_summary),
                   "manifest.seed_rebuilt")
    checks.require(_strict_json_equal(entry.get("crosswalk_summaries"), crosswalk_summary),
                   "manifest.crosswalks_rebuilt")

    privacy = private.get("privacy")
    checks.require(_strict_json_equal(privacy, {
        "contains_exact_raw_local_values": True,
        "contains_patient_admission_event_or_order_identifiers": False,
        "contains_event_or_order_timestamps": False,
        "external_api_called": False,
    }), "privacy.private_declaration")
    checks.require(_strict_json_equal(summary.get("privacy"), {
        "raw_values_emitted": False,
        "local_codes_or_ndcs_emitted": False,
        "patient_admission_event_or_order_identifiers_emitted": False,
        "event_or_order_timestamps_emitted": False,
        "per_value_or_per_tuple_hashes_emitted": False,
        "whole_set_and_whole_file_hashes_only": True,
    }), "privacy.public_declaration")
    expected_guards = {key: False for key in FALSE_GUARDS}
    checks.require(_strict_json_equal(private.get("guards"), expected_guards),
                   "guards.private_false")
    checks.require(_strict_json_equal(summary.get("guards"), expected_guards),
                   "guards.summary_false")
    checks.require(_strict_json_equal(manifest.get("guards"), expected_guards),
                   "guards.manifest_false")
    checks.require(_strict_json_equal(manifest_lineage.get("guards"), expected_guards),
                   "guards.manifest_lineage_false")

    expected_private_hashes = {
        "private_values_encoding": PRIVATE_ARTIFACT_ENCODING,
        "private_values_sha256": streamed_private["stored_sha256"],
        "private_values_raw_sha256": streamed_private["raw_sha256"],
        "executed_sql_sha256": _sha_bytes(executed_bytes),
    }
    checks.require(_strict_json_equal(
        summary.get("private_artifact_hashes"), expected_private_hashes
    ),
                   "files.summary_private_hashes")
    checks.require(_sha_bytes(summary_bytes) == entry.get("aggregate_summary_sha256"),
                   "files.summary_hash")
    executed_controls = _validate_executed_sql(root, executed_bytes, checks)
    _validate_manifest_stages(
        root, manifest, entry, private, executed_controls, checks
    )
    checks.require(
        type(entry.get("cumulative_frame_bytes")) is int
        and 0 < entry["cumulative_frame_bytes"]
        <= MAX_CUMULATIVE_RAW_FRAME_BYTES,
        "limits.raw_frame_bytes",
    )
    checks.require(
        type(entry.get("cumulative_spool_bytes")) is int
        and 0 < entry["cumulative_spool_bytes"]
        <= MAX_CUMULATIVE_SPOOL_BYTES,
        "limits.spool_bytes",
    )
    checks.require(
        type(entry.get("cumulative_merge_run_raw_bytes")) is int
        and 0 < entry["cumulative_merge_run_raw_bytes"]
        <= MAX_MERGE_RUN_RAW_BYTES,
        "limits.merge_run_raw_bytes",
    )
    checks.require(
        type(entry.get("cumulative_merge_run_spool_bytes")) is int
        and 0 < entry["cumulative_merge_run_spool_bytes"]
        <= MAX_MERGE_RUN_SPOOL_BYTES,
        "limits.merge_run_spool_bytes",
    )
    checks.require(
        type(entry.get("private_values_raw_bytes")) is int
        and 0 < entry["private_values_raw_bytes"] <= MAX_PRIVATE_RAW_BYTES,
        "limits.private_raw_bytes",
    )
    checks.require(
        type(entry.get("private_values_bytes")) is int
        and 0 < entry["private_values_bytes"] <= MAX_PRIVATE_STORED_BYTES,
        "limits.private_stored_bytes",
    )
    checks.require(
        type(entry.get("private_values_records")) is int
        and entry["private_values_records"] > 0,
        "limits.private_records",
    )
    checks.require(entry.get("cumulative_control_bytes") <= MAX_EXECUTED_SQL_BYTES,
                   "limits.control_bytes")
    stage_tables = entry.get("stages", {})
    observed_frame_sizes = [
        value.get("frame_bytes")
        for value in stage_tables.values()
        if isinstance(value, Mapping)
    ]
    checks.require(
        len(observed_frame_sizes) == STATEMENT_COUNT
        and all(type(value) is int and value > 0 for value in observed_frame_sizes)
        and entry.get("cumulative_frame_bytes") == sum(observed_frame_sizes),
        "limits.raw_frame_bytes_exact",
    )
    observed_spool_sizes = [
        value.get("spool_bytes")
        for value in stage_tables.values()
        if isinstance(value, Mapping)
    ]
    checks.require(
        len(observed_spool_sizes) == STATEMENT_COUNT
        and all(type(value) is int and value > 0 for value in observed_spool_sizes)
        and entry.get("cumulative_spool_bytes") == sum(observed_spool_sizes),
        "limits.spool_bytes_exact",
    )
    merge_ledger = entry.get("merge_run_ledger")
    checks.require(
        isinstance(merge_ledger, dict)
        and list(merge_ledger) == ["202b", "202c"],
        "limits.merge_run_ledger_inventory",
    )
    ledger_keys = {"runs", "record_count", "raw_bytes", "spool_bytes"}
    valid_ledger = isinstance(merge_ledger, dict)
    if valid_ledger:
        for stage in ("202b", "202c"):
            value = merge_ledger.get(stage)
            expected_run_records = sum(
                stage_tables[
                    f"{physical['stage']}_bucket_{bucket_index}"
                ]["rows"]
                for physical in BUCKET_STATEMENT_SPECS
                if physical["logical_stage"] == stage
                for bucket_index in range(BUCKET_COUNT)
            )
            stage_valid = (
                isinstance(value, dict)
                and set(value) == ledger_keys
                and value.get("runs") == BUCKET_COUNT
                and type(value.get("record_count")) is int
                and 0 <= value["record_count"]
                <= BUCKET_COUNT * MAX_TUPLE_GROUPS_PER_BUCKET
                and value["record_count"] == expected_run_records
                and value["record_count"]
                >= crosswalk_summary[stage]["unique_tuples"]
                and type(value.get("raw_bytes")) is int
                and 0 <= value["raw_bytes"] <= MAX_MERGE_RUN_RAW_BYTES
                and type(value.get("spool_bytes")) is int
                and 0 < value["spool_bytes"] <= MAX_MERGE_RUN_SPOOL_BYTES
                and value["raw_bytes"] >= value["record_count"]
                and value["raw_bytes"]
                <= value["record_count"] * MAX_PRIVATE_LINE_BYTES
                and (value["record_count"] == 0) == (value["raw_bytes"] == 0)
                and value["spool_bytes"] >= value["runs"] * 8
            )
            checks.require(stage_valid, f"limits.merge_run_ledger_{stage}")
            valid_ledger = valid_ledger and stage_valid
    checks.require(
        valid_ledger
        and entry.get("cumulative_merge_run_raw_bytes")
        == sum(merge_ledger[stage]["raw_bytes"] for stage in ("202b", "202c"))
        and entry.get("cumulative_merge_run_spool_bytes")
        == sum(merge_ledger[stage]["spool_bytes"] for stage in ("202b", "202c")),
        "limits.merge_run_bytes_exact",
    )
    checks.require(
        entry.get("cumulative_control_bytes") == len(executed_bytes),
        "limits.control_bytes_exact",
    )

    _check_public_keys(summary, checks, "privacy.summary")
    _check_public_keys(manifest, checks, "privacy.manifest")

    artifact_modes = manifest.get("artifact_modes")
    checks.require(isinstance(artifact_modes, dict), "permissions.mode_manifest")
    checks.require(set(artifact_modes) == {
        "directory", "manifest", "stderr", "value_files"
    } and artifact_modes.get("directory") == "0700"
                   and artifact_modes.get("manifest") == "0600"
                   and artifact_modes.get("stderr") is None,
                   "permissions.mode_declarations")
    checks.require(set(artifact_modes.get("value_files", {})) == {
        paths["private"].name, paths["executed"].name, paths["summary"].name
    } and all(value == "0600" for value in artifact_modes["value_files"].values()),
                   "permissions.value_mode_declarations")

    return {
        "manifest_sha256": _sha_bytes(manifest_bytes),
        "config_sha256": config_hash,
        "scientific_contract_sha256": _contract_hash(config),
        "implementation_bundle_sha256": {
            name: value["bundle_sha256"] for name, value in bundles.items()
        },
        "boundary_source_count": len(boundary_summary),
        "semantic_seed_keys": seed_summary["key_count"],
        "semantic_seed_key_set_sha256": seed_summary["key_set_sha256"],
        "crosswalk_stage_count": len(crosswalk_summary),
        "crosswalk_unique_tuples": {
            stage: value["unique_tuples"] for stage, value in crosswalk_summary.items()
        },
        "crosswalk_total_multiplicity": {
            stage: value["global_output_multiplicity"]
            for stage, value in crosswalk_summary.items()
        },
        "same_snapshot_confirmed": True,
        "rollback_confirmed": True,
        "clean_psql_exit_confirmed": True,
        "all_457_statements_bounded": True,
        "private_modes_confirmed": True,
        "git_ignored_confirmed": True,
        "public_privacy_confirmed": True,
        "all_guards_false": True,
    }


def audit_query202_pre_adjudication(root: Path, artifact_directory: Path) -> dict[str, Any]:
    """Audit one completed artifact and persist a value-safe audit summary."""
    root = root.resolve()
    directory = artifact_directory
    if not directory.is_absolute():
        directory = root / directory
    directory = directory.resolve()
    checks = Checks()
    status = "failed"
    recomputed: dict[str, Any] = {}
    try:
        recomputed = _audit_complete_artifact(root, directory, checks)
        status = "passed" if not checks.failed else "failed"
    except AuditContractError as exc:
        if str(exc) not in checks.failed:
            checks.failed.append(str(exc))
    except Exception:
        if "audit.unexpected_failure" not in checks.failed:
            checks.failed.append("audit.unexpected_failure")
    result = {
        "schema_version": 2,
        "audit": AUDIT_NAME,
        "query": QUERY_NAME,
        "status": status,
        "artifact_directory": str(directory.relative_to(root))
        if directory.is_relative_to(root) else "outside_project_root",
        "checks": {
            "total": checks.total,
            "failed": len(checks.failed),
            "failed_names": sorted(checks.failed),
            "by_category": dict(sorted(checks.by_category.items())),
        },
        "recomputed": recomputed,
        "database_connection_opened": False,
        "raw_values_emitted": False,
        "patient_or_event_identifiers_emitted": False,
    }
    audit_path = directory / "audit-summary.json"
    if audit_path.exists():
        raise AuditContractError("audit.output_already_exists")
    payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _write_private(audit_path, payload)
    if _mode(audit_path) != "0600":
        raise AuditContractError("audit.output_mode")
    result["audit_summary"] = str(audit_path.relative_to(root))
    result["audit_summary_sha256"] = _sha_bytes(payload)
    return result
