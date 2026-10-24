"""Same-snapshot event runner for query-200 source closure.

The runner keeps the two discovery SELECTs, three global aggregate SELECTs,
and either one unbucketed event SELECT or every subject-hash event bucket in one
persistent PostgreSQL session and one REPEATABLE READ READ ONLY transaction.
Database-derived values remain in memory until the transaction has explicitly
rolled back and psql has exited cleanly.  Only then are the private discovery,
executed SQL, and merged public CSV written to disk.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time
from typing import Any, Mapping

from .database import DatabaseError, PsqlClient, _safe_error, _statement_body
from .source_closure_merge import (
    MergeResult,
    MergeValidationErrorCode,
    SourceClosureMergeError,
    merge_source_closure_fragments,
    validate_source_closure_fragment,
)
from .staged_source_closure import (
    MAX_DISCOVERY_BYTES,
    MAX_RESULT_BYTES,
    MAX_ROWS,
    QUERY_NAME,
    _PersistentPsql,
    _assert_same_snapshot_controls,
    _constant_array,
    _decode_unique_json,
    _merge_discovery,
    _parse_detail_seed_frame,
    _parse_names_frame,
    _parse_result_frame,
    _sha,
    _unicode_literal,
    _values_indexed,
    _values_one,
    _values_seeds,
    _write_private,
    render_detail_seed_discovery,
)


NAMES_DISCOVERY_FILE = "sql/profiling/200a_potassium_product_source_discovery.sql"
DETAIL_SEED_DISCOVERY_FILE = (
    "sql/profiling/200a2_potassium_product_detail_seed_discovery.sql"
)
GLOBAL_HEAD_FILE = "sql/profiling/200d_potassium_product_source_global_head.sql"
GLOBAL_DETAIL_FILE = "sql/profiling/200e_potassium_product_source_global_detail.sql"
GLOBAL_ORDER_FILE = "sql/profiling/200f_potassium_product_source_global_order.sql"
UNBUCKETED_EVENT_FILE = "sql/profiling/200c0_potassium_product_source_event.sql"
EVENT_BUCKET_FILE = "sql/profiling/200c_potassium_product_source_event_bucket.sql"

UNBUCKETED_EXECUTION_MODE = "unbucketed_event"
SHARDED_EXECUTION_MODE = "subject_buckets"
DEFAULT_EXECUTION_MODE = SHARDED_EXECUTION_MODE
EXECUTION_MODES = frozenset({UNBUCKETED_EXECUTION_MODE, SHARDED_EXECUTION_MODE})
DEFAULT_BUCKET_COUNT = 8
MIN_BUCKET_COUNT = 2
MAX_BUCKET_COUNT = 64
STATEMENT_TIMEOUT_MS = 120000
# psql needs a small interval to deliver PostgreSQL's timeout error/control
# frame after the server-side statement deadline.
PROCESS_TIMEOUT_SECONDS = 130
MAX_CUMULATIVE_FRAME_BYTES = 256 * 1024 * 1024
MAX_EXECUTED_SQL_BYTES = 32 * 1024 * 1024
MARKER_PATTERN = re.compile(r"__[A-Z][A-Z0-9_]*__")

COMMON_DISCOVERY_MARKERS = {
    "__DISCOVERY_COUNTS__",
    "__INDEXED_LEXICAL_NAMES__",
}
EXPECTED_MARKERS: dict[str, frozenset[str]] = {
    "global_head": frozenset(COMMON_DISCOVERY_MARKERS | {
        "__EMAR_NAME_ARRAY__",
    }),
    "global_detail": frozenset(COMMON_DISCOVERY_MARKERS | {
        "__SEED_PRODUCT_CODES__",
        "__DETAIL_NAME_ARRAY__",
        "__SEED_PRODUCT_CODE_ARRAY__",
    }),
    "global_order": frozenset(COMMON_DISCOVERY_MARKERS | {
        "__PRESCRIPTION_NAMES__",
        "__PHARMACY_NAME_ARRAY__",
        "__PRESCRIPTION_NAME_ARRAY__",
    }),
    "unbucketed_event": frozenset(COMMON_DISCOVERY_MARKERS | {
        "__PRESCRIPTION_NAMES__",
        "__SEED_PRODUCT_CODES__",
        "__EMAR_NAME_ARRAY__",
        "__DETAIL_NAME_ARRAY__",
        "__PHARMACY_NAME_ARRAY__",
        "__PRESCRIPTION_NAME_ARRAY__",
        "__SEED_PRODUCT_CODE_ARRAY__",
        "__DETAIL_CODE_NAME_FLAGS__",
    }),
    "event_bucket": frozenset(COMMON_DISCOVERY_MARKERS | {
        "__PRESCRIPTION_NAMES__",
        "__SEED_PRODUCT_CODES__",
        "__EMAR_NAME_ARRAY__",
        "__DETAIL_NAME_ARRAY__",
        "__PHARMACY_NAME_ARRAY__",
        "__PRESCRIPTION_NAME_ARRAY__",
        "__SEED_PRODUCT_CODE_ARRAY__",
        "__DETAIL_CODE_NAME_FLAGS__",
        "__BUCKET_INDEX__",
        "__BUCKET_COUNT__",
    }),
}

SESSION_SETTINGS = {
    "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
    "lock_timeout_ms": 2000,
    "standard_conforming_strings": "on",
    "work_mem": "128MB",
    "jit": "off",
    "enable_mergejoin": "off",
    "max_parallel_workers_per_gather": 4,
    "min_parallel_table_scan_size": 0,
    "min_parallel_index_scan_size": 0,
    "parallel_setup_cost": 0,
    "parallel_tuple_cost": 0,
}

ADMISSION_MERGE_SUMMARY_FIELDS = {
    "null_subject_candidate_heads",
    "admission_exact_match_heads",
    "admission_missing_subject_and_hadm_heads",
    "admission_missing_subject_id_heads",
    "admission_missing_hadm_id_heads",
    "admission_hadm_absent_from_admissions_heads",
    "admission_subject_mismatch_heads",
    "nonexact_admission_link_heads",
    "nonexact_admission_link_subjects",
    "nonexact_admission_link_pairs",
    "admissions_hadm_id_primary_key_confirmed",
}
ADMISSION_STATUS_SUMMARY_FIELDS = {
    "admission_exact_match_heads",
    "admission_missing_subject_and_hadm_heads",
    "admission_missing_subject_id_heads",
    "admission_missing_hadm_id_heads",
    "admission_hadm_absent_from_admissions_heads",
    "admission_subject_mismatch_heads",
}

BUCKET_MERGE_SUMMARY_FIELDS = {
    "merge_protocol_version",
    "execution_mode",
    "bucket_count",
    "candidate_emar_heads",
    "query199_head_scope_distinct_heads",
    "bucket_assignment_violations",
    "detail_subject_partition_groups_checked",
    "detail_subject_partition_identity_violations",
    "order_detail_subject_partition_groups_checked",
    "order_detail_subject_partition_identity_violations",
    "duplicate_candidate_emar_heads",
    "emar_id_primary_key_confirmed",
    "pharmacy_id_primary_key_confirmed",
    "pharmacy_id_integer_types_confirmed",
    "selected_detail_rows",
    "detail_text_rows",
    "detail_code_rows",
    "order_detail_link_rows",
    "detail_code_dictionary_names",
} | ADMISSION_MERGE_SUMMARY_FIELDS
UNBUCKETED_MERGE_SUMMARY_FIELDS = {
    "merge_protocol_version",
    "execution_mode",
    "candidate_emar_heads",
    "query199_head_scope_distinct_heads",
    "duplicate_candidate_emar_heads",
    "emar_id_primary_key_confirmed",
    "pharmacy_id_primary_key_confirmed",
    "pharmacy_id_integer_types_confirmed",
    "selected_detail_rows",
    "detail_text_rows",
    "detail_code_rows",
    "order_detail_link_rows",
    "detail_code_dictionary_names",
    "event_aggregation_unbucketed",
} | ADMISSION_MERGE_SUMMARY_FIELDS

DETAIL_CODE_FLAG_FIELDS = {
    "raw_name",
    "focal_kcl_hint",
    "phosphate_or_acetate_hint",
    "other_potassium_salt_hint",
    "active_drug_hint",
    "unresolved_hint",
}
DETAIL_CODE_BOOLEAN_FIELDS = DETAIL_CODE_FLAG_FIELDS - {"raw_name"}
DETAIL_CODE_CONTROL_COUNTERS = {
    "private_control_dictionary": True,
    "dictionary_value_is_patient_text": False,
}
EVENT_METADATA_FIELDS = {
    "candidate_emar_heads",
    "subjects",
    "admissions",
    "query199_head_scope_distinct_heads",
    "null_subject_candidate_heads",
    "admission_exact_match_heads",
    "admission_missing_subject_and_hadm_heads",
    "admission_missing_subject_id_heads",
    "admission_missing_hadm_id_heads",
    "admission_hadm_absent_from_admissions_heads",
    "admission_subject_mismatch_heads",
    "nonexact_admission_link_heads",
    "nonexact_admission_link_subjects",
    "nonexact_admission_link_pairs",
    "duplicate_candidate_emar_heads",
    "detail_text_dictionary_miss_rows",
    "detail_code_dictionary_miss_rows",
    "supplied_detail_code_dictionary_names",
    "selected_detail_rows",
    "detail_text_rows",
    "detail_code_rows",
    "order_detail_link_rows",
    "emar_id_primary_key_confirmed",
    "pharmacy_id_primary_key_confirmed",
    "pharmacy_id_integer_types_confirmed",
    "admissions_hadm_id_primary_key_confirmed",
    "event_aggregation_unbucketed",
    "admission_count_uses_nonnull_subject_hadm_pairs",
    "admission_link_status_partition_complete",
    "admission_link_anomalies_reported_not_repaired",
    "raw_identifiers_times_or_patient_text_emitted",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_bucket_count(bucket_count: Any) -> int:
    if (
        type(bucket_count) is not int
        or bucket_count < MIN_BUCKET_COUNT
        or bucket_count > MAX_BUCKET_COUNT
    ):
        raise DatabaseError(
            f"Query-200 bucket_count must be an integer from {MIN_BUCKET_COUNT} "
            f"through {MAX_BUCKET_COUNT}."
        )
    return bucket_count


def _validate_execution_mode(execution_mode: Any) -> str:
    if not isinstance(execution_mode, str) or execution_mode not in EXECUTION_MODES:
        raise DatabaseError(
            "Query-200 execution_mode must be 'unbucketed_event' or "
            "'subject_buckets'."
        )
    return execution_mode


def _validate_detail_code_name(value: Any) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) > 255
        or any(character in value for character in ("\x00", "\n", "\r"))
    ):
        raise DatabaseError(
            "The private detail-code dictionary contains an invalid name."
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise DatabaseError(
            "The private detail-code dictionary contains non-UTF-8 text."
        ) from exc
    return value


def _parse_json_object(raw: Any, label: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise DatabaseError(f"{label} is not a JSON string.")
    try:
        encoded = raw.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise DatabaseError(f"{label} is not valid UTF-8.") from exc
    return _decode_unique_json(encoded, label)


def _expected_review_stratum(item: Mapping[str, Any]) -> str:
    if item["active_drug_hint"]:
        return "non_repletion_active_drug_hint"
    if item["focal_kcl_hint"]:
        return "focal_kcl_repletion_hint"
    if item["phosphate_or_acetate_hint"]:
        return "broader_phosphate_or_acetate_repletion_hint"
    if item["other_potassium_salt_hint"]:
        return "other_potassium_salt_review"
    return "unresolved_name_or_local_code_review"


def _extract_detail_code_dictionary(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Validate and remove 200e's private code-description flag handoff."""
    public_rows: list[dict[str, str]] = []
    dictionary: list[dict[str, Any]] = []
    closure_vocabulary: dict[str | None, dict[str, Any]] = {}
    for number, row in enumerate(rows, start=1):
        if row["section"] == "closure_detail_code_dictionary":
            if row["records"] != "0":
                raise DatabaseError(
                    "The private detail-code dictionary must use zero public records."
                )
            dimensions = _parse_json_object(
                row["dimensions"], f"Detail-code dictionary row {number} dimensions"
            )
            counters = _parse_json_object(
                row["counters"], f"Detail-code dictionary row {number} counters"
            )
            if set(dimensions) != DETAIL_CODE_FLAG_FIELDS:
                raise DatabaseError(
                    "The private detail-code dictionary has an unexpected schema."
                )
            if counters != DETAIL_CODE_CONTROL_COUNTERS:
                raise DatabaseError(
                    "The private detail-code dictionary has invalid control counters."
                )
            raw_name = _validate_detail_code_name(dimensions["raw_name"])
            if any(
                type(dimensions[key]) is not bool
                for key in DETAIL_CODE_BOOLEAN_FIELDS
            ):
                raise DatabaseError(
                    "The private detail-code dictionary flags must be booleans."
                )
            item = dict(dimensions)
            item["raw_name"] = raw_name
            if item["unresolved_hint"] != (
                not any(item[key] for key in (
                    "focal_kcl_hint",
                    "phosphate_or_acetate_hint",
                    "other_potassium_salt_hint",
                    "active_drug_hint",
                ))
            ):
                raise DatabaseError(
                    "The private detail-code dictionary flags are inconsistent."
                )
            if raw_name is None and item != {
                "raw_name": None,
                "focal_kcl_hint": False,
                "phosphate_or_acetate_hint": False,
                "other_potassium_salt_hint": False,
                "active_drug_hint": False,
                "unresolved_hint": True,
            }:
                raise DatabaseError(
                    "The NULL detail-code dictionary row has invalid default flags."
                )
            dictionary.append(item)
        else:
            public_rows.append(row)
            if row["section"] == "source_vocabulary":
                dimensions = _parse_json_object(
                    row["dimensions"],
                    f"Global-detail vocabulary row {number} dimensions",
                )
                if (
                    dimensions.get("source_type")
                    == "detail_product_description"
                    and dimensions.get("evidence_path")
                    == "detail_local_code_closure"
                ):
                    raw_name = _validate_detail_code_name(dimensions.get("raw_name"))
                    if raw_name in closure_vocabulary:
                        raise DatabaseError(
                            "Global-detail closure vocabulary contains a duplicate name."
                        )
                    closure_vocabulary[raw_name] = dimensions

    names = [item["raw_name"] for item in dictionary]
    if len(names) != len(set(names)):
        raise DatabaseError("The private detail-code dictionary contains duplicate names.")
    if set(names) != set(closure_vocabulary) or len(names) != len(closure_vocabulary):
        raise DatabaseError(
            "The private detail-code dictionary does not exactly cover closure vocabulary."
        )
    for item in dictionary:
        dimensions = closure_vocabulary[item["raw_name"]]
        for key in (
            "focal_kcl_hint", "broader_repletion_hint",
            "non_repletion_active_drug_hint",
        ):
            if dimensions.get(key) is not None and type(dimensions.get(key)) is not bool:
                raise DatabaseError(
                    "Global-detail vocabulary hint fields must be boolean or null."
                )
        if (dimensions.get("focal_kcl_hint") is True) != item["focal_kcl_hint"]:
            raise DatabaseError(
                "The private detail-code dictionary disagrees with focal vocabulary flags."
            )
        if (dimensions.get("broader_repletion_hint") is True) != (
            item["focal_kcl_hint"] or item["phosphate_or_acetate_hint"]
        ):
            raise DatabaseError(
                "The private detail-code dictionary disagrees with broader vocabulary flags."
            )
        if (dimensions.get("non_repletion_active_drug_hint") is True) != item[
            "active_drug_hint"
        ]:
            raise DatabaseError(
                "The private detail-code dictionary disagrees with active-drug flags."
            )
        if dimensions.get("source_review_stratum") != _expected_review_stratum(item):
            raise DatabaseError(
                "The private detail-code dictionary disagrees with review strata."
            )
    dictionary.sort(key=lambda item: (
        item["raw_name"] is not None,
        "" if item["raw_name"] is None else item["raw_name"],
    ))
    return public_rows, dictionary


def _detail_code_flag_values(values: list[dict[str, Any]]) -> str:
    if not values:
        return (
            "    SELECT NULL::varchar(255) AS raw_name,false::boolean AS "
            "focal_kcl_hint,false::boolean AS phosphate_or_acetate_hint,"
            "false::boolean AS other_potassium_salt_hint,false::boolean AS "
            "active_drug_hint,true::boolean AS unresolved_hint WHERE false"
        )
    rendered_rows: list[str] = []
    for item in values:
        raw_name = item["raw_name"]
        if raw_name is None:
            name_sql = "NULL::varchar(255)"
        elif raw_name == "":
            name_sql = "U&''::varchar(255)"
        else:
            name_sql = _unicode_literal(raw_name, "varchar(255)")
        flags = ",".join(
            "true" if item[key] else "false"
            for key in (
                "focal_kcl_hint",
                "phosphate_or_acetate_hint",
                "other_potassium_salt_hint",
                "active_drug_hint",
                "unresolved_hint",
            )
        )
        rendered_rows.append(f"      ({name_sql},{flags})")
    return "    VALUES\n" + ",\n".join(rendered_rows)


DISCOVERY_VOCABULARY_PATHS = {
    ("emar_medication", "head_text"): "emar_names",
    ("detail_product_description", "detail_text_seed"): "detail_names",
    ("pharmacy_medication", "pharmacy_name"): "pharmacy_names",
    ("prescription_drug", "prescription_name"): "prescription_names",
}


def _validate_discovery_vocabulary_sets(
    fragments: Mapping[str, list[dict[str, str]]],
    discovery: Mapping[str, Any],
) -> None:
    """Require public lexical vocabulary to equal all four private dictionaries."""
    actual: dict[tuple[str, str], list[str]] = {
        path: [] for path in DISCOVERY_VOCABULARY_PATHS
    }
    for rows in fragments.values():
        for number, row in enumerate(rows, start=1):
            if row["section"] != "source_vocabulary":
                continue
            dimensions = _parse_json_object(
                row["dimensions"],
                f"Global source-vocabulary row {number} dimensions",
            )
            path = (
                dimensions.get("source_type"), dimensions.get("evidence_path")
            )
            if path in actual:
                raw_name = dimensions.get("raw_name")
                if not isinstance(raw_name, str):
                    raise DatabaseError(
                        "A lexical source-vocabulary row has an invalid raw name."
                    )
                actual[path].append(raw_name)

    for path, discovery_key in DISCOVERY_VOCABULARY_PATHS.items():
        values = actual[path]
        if len(values) != len(set(values)):
            raise DatabaseError(
                "A lexical source-vocabulary semantic key is duplicated."
            )
        expected = discovery[discovery_key]
        if len(values) != len(expected) or set(values) != set(expected):
            raise DatabaseError(
                "The public lexical vocabulary does not exactly match discovery."
            )


def _validate_event_dictionary_guard(
    rows: list[dict[str, str]], dictionary_count: int
) -> dict[str, int]:
    metadata = [row for row in rows if row["section"] == "closure_event_metadata"]
    if len(metadata) != 1:
        raise DatabaseError(
            "The unbucketed event query must return one metadata row."
        )
    row = metadata[0]
    if _parse_json_object(row["dimensions"], "Event metadata dimensions") != {}:
        raise DatabaseError("The unbucketed event metadata dimensions must be empty.")
    counters = _parse_json_object(row["counters"], "Event metadata counters")
    if set(counters) != EVENT_METADATA_FIELDS:
        raise DatabaseError("The unbucketed event metadata schema changed.")
    for key in (
        "candidate_emar_heads",
        "query199_head_scope_distinct_heads",
        "duplicate_candidate_emar_heads",
        "detail_text_dictionary_miss_rows",
        "detail_code_dictionary_miss_rows",
        "supplied_detail_code_dictionary_names",
        "selected_detail_rows",
        "detail_text_rows",
        "detail_code_rows",
        "order_detail_link_rows",
    ):
        if type(counters[key]) is not int or counters[key] < 0:
            raise DatabaseError("The unbucketed event metadata counters are invalid.")
    for key, expected in (
        ("emar_id_primary_key_confirmed", True),
        ("pharmacy_id_primary_key_confirmed", True),
        ("pharmacy_id_integer_types_confirmed", True),
        ("event_aggregation_unbucketed", True),
        ("raw_identifiers_times_or_patient_text_emitted", False),
    ):
        if counters[key] is not expected:
            raise DatabaseError("The unbucketed event metadata guards are invalid.")
    if (
        counters["detail_text_dictionary_miss_rows"] != 0
        or counters["detail_code_dictionary_miss_rows"] != 0
        or counters["supplied_detail_code_dictionary_names"] != dictionary_count
    ):
        raise DatabaseError(
            "The unbucketed event dictionary handoff failed exact coverage checks."
        )
    return {
        "detail_text_dictionary_miss_rows": 0,
        "detail_code_dictionary_miss_rows": 0,
        "supplied_detail_code_dictionary_names": dictionary_count,
    }


def _validate_bucket_dictionary_guard(
    rows: list[dict[str, str]], dictionary_count: int,
    bucket_index: int, bucket_count: int,
) -> dict[str, int]:
    metadata = [row for row in rows if row["section"] == "closure_bucket_metadata"]
    if len(metadata) != 1:
        raise DatabaseError("An event bucket must return one metadata row.")
    row = metadata[0]
    if _parse_json_object(row["dimensions"], "Bucket metadata dimensions") != {
        "bucket_index": bucket_index,
        "bucket_count": bucket_count,
    }:
        raise DatabaseError("The event bucket metadata dimensions changed.")
    counters = _parse_json_object(row["counters"], "Bucket metadata counters")
    for key in (
        "detail_code_dictionary_miss_names",
        "supplied_detail_code_dictionary_names",
    ):
        if type(counters.get(key)) is not int or counters[key] < 0:
            raise DatabaseError("The event bucket dictionary controls are invalid.")
    if (
        counters["detail_code_dictionary_miss_names"] != 0
        or counters["supplied_detail_code_dictionary_names"] != dictionary_count
    ):
        raise DatabaseError(
            "The event bucket dictionary handoff failed exact coverage checks."
        )
    return {
        "detail_code_dictionary_miss_names": 0,
        "supplied_detail_code_dictionary_names": dictionary_count,
    }


def _discovery_replacements(discovery: Mapping[str, Any]) -> dict[str, str]:
    replacements = {
        "__DISCOVERY_COUNTS__": ",".join(
            str(discovery[key]) for key in (
                "non_null_emar_medication_names",
                "non_null_detail_product_descriptions",
                "non_null_pharmacy_medication_names",
                "identity_consistent_lexical_detail_product_rows",
                "identity_consistent_lexical_detail_events",
            )
        ),
        "__INDEXED_LEXICAL_NAMES__": _values_indexed(dict(discovery)),
        "__PRESCRIPTION_NAMES__": _values_one(
            list(discovery["prescription_names"]), "raw_name"
        ),
        "__SEED_PRODUCT_CODES__": _values_seeds(
            list(discovery["seed_product_codes"])
        ),
        "__EMAR_NAME_ARRAY__": _constant_array(
            list(discovery["emar_names"]), "text"
        ),
        "__DETAIL_NAME_ARRAY__": _constant_array(
            list(discovery["detail_names"]), "varchar"
        ),
        "__PHARMACY_NAME_ARRAY__": _constant_array(
            list(discovery["pharmacy_names"]), "text"
        ),
        "__PRESCRIPTION_NAME_ARRAY__": _constant_array(
            list(discovery["prescription_names"]), "varchar"
        ),
        "__SEED_PRODUCT_CODE_ARRAY__": _constant_array(
            [item["product_code"] for item in discovery["seed_product_codes"]],
            "varchar",
        ),
    }
    if "detail_code_name_flags" in discovery:
        replacements["__DETAIL_CODE_NAME_FLAGS__"] = _detail_code_flag_values(
            list(discovery["detail_code_name_flags"])
        )
    return replacements


def render_known_template(
    template: str,
    discovery: Mapping[str, Any],
    template_kind: str,
    *,
    bucket_index: int | None = None,
    bucket_count: int | None = None,
) -> str:
    """Render one reviewed template with its exact, single-use marker set."""
    if template_kind not in EXPECTED_MARKERS:
        raise DatabaseError("Unknown query-200 sharded template kind.")
    expected = EXPECTED_MARKERS[template_kind]
    observed = MARKER_PATTERN.findall(template)
    if set(observed) != set(expected) or any(
        observed.count(marker) != 1 for marker in expected
    ):
        raise DatabaseError(
            f"The {template_kind} template marker contract changed or is ambiguous."
        )

    replacements = _discovery_replacements(discovery)
    if template_kind == "event_bucket":
        validated_count = _validate_bucket_count(bucket_count)
        if (
            type(bucket_index) is not int
            or bucket_index < 0
            or bucket_index >= validated_count
        ):
            raise DatabaseError("Query-200 bucket index is outside the requested range.")
        # These strings come only from strictly validated Python integers.
        replacements["__BUCKET_INDEX__"] = str(bucket_index)
        replacements["__BUCKET_COUNT__"] = str(validated_count)
    elif bucket_index is not None or bucket_count is not None:
        raise DatabaseError("Bucket parameters were supplied to a global template.")

    rendered = template
    for marker in sorted(expected):
        if marker not in replacements:
            raise DatabaseError("A reviewed query-200 marker has no safe renderer.")
        rendered = rendered.replace(marker, replacements[marker])
    if MARKER_PATTERN.search(rendered) or "__" in rendered:
        raise DatabaseError("A query-200 template contains an unresolved marker.")
    return _statement_body(rendered)


def _session_preamble() -> str:
    return (
        "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
        f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms';\n"
        "SET LOCAL lock_timeout = '2000ms';\n"
        "SET LOCAL standard_conforming_strings = on;\n"
        "SET LOCAL work_mem = '128MB';\n"
        "SET LOCAL jit = off;\n"
        "SET LOCAL enable_mergejoin = off;\n"
        "SET LOCAL max_parallel_workers_per_gather = 4;\n"
        "SET LOCAL min_parallel_table_scan_size = 0;\n"
        "SET LOCAL min_parallel_index_scan_size = 0;\n"
        "SET LOCAL parallel_setup_cost = 0;\n"
        "SET LOCAL parallel_tuple_cost = 0;\n"
    )


def _aggregate_control(rendered: str, marker: str) -> str:
    return (
        "SELECT section,dimensions,records,counters,\n"
        "       current_setting('transaction_isolation') AS transaction_isolation,\n"
        "       current_setting('transaction_read_only') AS transaction_read_only,\n"
        "       pg_current_snapshot()::text AS snapshot_token\n"
        "FROM (\n"
        + rendered
        + f"\n) AS april_profile_rows LIMIT {MAX_ROWS + 1};\n"
        "\\echo "
        + marker
        + "\n"
    )


def _mode(path: Path) -> str:
    return format(stat.S_IMODE(path.stat().st_mode), "04o")


def _remove_private_values(paths: list[Path]) -> bool:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return not any(path.exists() for path in paths)


def _bounded_add(current: int, addition: int, limit: int, label: str) -> int:
    if (
        type(current) is not int
        or type(addition) is not int
        or type(limit) is not int
        or current < 0
        or addition < 0
        or limit <= 0
        or current > limit - addition
    ):
        raise DatabaseError(f"Query-200 cumulative {label} exceeded its byte limit.")
    return current + addition


def _initial_stage(file: str) -> dict[str, Any]:
    return {
        "file": file,
        "status": "pending",
        "rows": None,
        "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        "process_timeout_seconds": PROCESS_TIMEOUT_SECONDS,
    }


def _record_template(stage: dict[str, Any], raw: bytes) -> str:
    stage["template_sha256"] = _sha(raw)
    stage["template_bytes"] = len(raw)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DatabaseError("A query-200 SQL template is not valid UTF-8.") from exc


def _record_render(stage: dict[str, Any], rendered: str) -> None:
    encoded = rendered.encode("utf-8")
    stage["rendered_sha256"] = _sha(encoded)
    stage["rendered_bytes"] = len(encoded)


def _record_control(stage: dict[str, Any], control: str) -> None:
    encoded = control.encode("utf-8")
    stage["control_sha256"] = _sha(encoded)
    stage["control_bytes"] = len(encoded)


def _run_frame(
    session: _PersistentPsql,
    stage: dict[str, Any],
    control: str,
    marker: str,
    byte_limit: int,
) -> bytes:
    _record_control(stage, control)
    stage["status"] = "running"
    started = time.monotonic()
    try:
        session.send(control)
        frame = session.frame(marker, PROCESS_TIMEOUT_SECONDS, byte_limit)
    finally:
        # Retain timing for a timed-out/interrupted statement as well as a
        # successful frame; the failure finalizer makes its stage terminal.
        stage["elapsed_seconds"] = round(time.monotonic() - started, 6)
    stage["frame_sha256"] = _sha(frame)
    stage["frame_bytes"] = len(frame)
    return frame


def _validate_merge_result(
    result: MergeResult,
    execution_mode: str,
    bucket_count: int | None,
) -> tuple[bytes, dict[str, Any]]:
    if not isinstance(result, MergeResult):
        raise DatabaseError("Query-200 merge returned an unexpected result type.")
    summary = result.validation_summary
    expected_fields = (
        UNBUCKETED_MERGE_SUMMARY_FIELDS
        if execution_mode == UNBUCKETED_EXECUTION_MODE
        else BUCKET_MERGE_SUMMARY_FIELDS
    )
    if not isinstance(summary, dict) or set(summary) != expected_fields:
        raise DatabaseError("Query-200 merge returned an unexpected validation summary.")
    noninteger_fields = {
        "execution_mode",
        "emar_id_primary_key_confirmed",
        "pharmacy_id_primary_key_confirmed",
        "pharmacy_id_integer_types_confirmed",
        "admissions_hadm_id_primary_key_confirmed",
        "event_aggregation_unbucketed",
    }
    integer_fields = expected_fields - noninteger_fields
    if any(type(summary[key]) is not int or summary[key] < 0 for key in integer_fields):
        raise DatabaseError("Query-200 merge validation counters are invalid.")
    if (
        summary["merge_protocol_version"] != 1
        or summary["execution_mode"] != execution_mode
        or summary["query199_head_scope_distinct_heads"] != 559_191
        or summary["duplicate_candidate_emar_heads"] != 0
        or summary["emar_id_primary_key_confirmed"] is not True
        or summary["pharmacy_id_primary_key_confirmed"] is not True
        or summary["pharmacy_id_integer_types_confirmed"] is not True
        or summary["admissions_hadm_id_primary_key_confirmed"] is not True
    ):
        raise DatabaseError("Query-200 merge controls did not pass fail-closed validation.")
    if (
        sum(summary[key] for key in ADMISSION_STATUS_SUMMARY_FIELDS)
        != summary["candidate_emar_heads"]
        or summary["nonexact_admission_link_heads"]
        != summary["candidate_emar_heads"] - summary["admission_exact_match_heads"]
        or summary["null_subject_candidate_heads"]
        != summary["admission_missing_subject_and_hadm_heads"]
           + summary["admission_missing_subject_id_heads"]
        or summary["nonexact_admission_link_subjects"]
        > summary["nonexact_admission_link_heads"]
        or summary["nonexact_admission_link_pairs"]
        > summary["nonexact_admission_link_heads"]
    ):
        raise DatabaseError("Query-200 admission-link summary is inconsistent.")
    if execution_mode == UNBUCKETED_EXECUTION_MODE:
        if summary["event_aggregation_unbucketed"] is not True:
            raise DatabaseError(
                "Query-200 unbucketed merge did not confirm its event aggregation."
            )
    elif (
        summary["bucket_count"] != bucket_count
        or summary["bucket_assignment_violations"] != 0
        or summary["detail_subject_partition_identity_violations"] != 0
        or summary["order_detail_subject_partition_identity_violations"] != 0
    ):
        raise DatabaseError("Query-200 bucket merge controls did not pass validation.")
    if not isinstance(result.rows, list) or not result.rows or len(result.rows) > MAX_ROWS:
        raise DatabaseError("Query-200 merge returned an invalid public row count.")
    if not isinstance(result.csv_text, str):
        raise DatabaseError("Query-200 merge did not return deterministic CSV text.")
    output = result.csv_text.encode("utf-8")
    if len(output) > MAX_RESULT_BYTES:
        raise DatabaseError("Query-200 merged output exceeded its private byte limit.")
    return output, dict(summary)


def _safe_scan_counts(
    execution_mode: str, bucket_count: int | None
) -> dict[str, int]:
    event_scans = 1 if execution_mode == UNBUCKETED_EXECUTION_MODE else int(bucket_count)
    return {
        "names_discovery_prescription_lexical_pass_count": 1,
        "global_order_prescription_lexical_pass_count": 1,
        "global_order_prescription_component_pass_count": 1,
        "event_closure_prescription_lexical_pass_count": event_scans,
        "event_closure_prescription_component_pass_count": event_scans,
        "total_prescription_lexical_pass_count": event_scans + 2,
        "total_prescription_component_pass_count": event_scans + 1,
    }


def _record_merge_validation_failure(
    entry: dict[str, Any],
    stages: Mapping[str, Any],
    origin: str,
    code: MergeValidationErrorCode,
) -> None:
    """Record only a closed error token and a runner-controlled origin."""
    allowed_origins = {
        "global_head", "global_detail", "global_order", "unbucketed_event",
        "final_merge", "final_result",
    } | {
        name for name in stages
        if re.fullmatch(r"event_bucket_(0|[1-9][0-9]*)", name)
    }
    safe_origin = origin if origin in allowed_origins else "final_merge"
    safe_code = (
        code
        if isinstance(code, MergeValidationErrorCode)
        else MergeValidationErrorCode.UNCLASSIFIED_CONTRACT_REJECTED
    )
    entry["merge_validation_error_origin"] = safe_origin
    entry["merge_validation_error_code"] = safe_code.value


def run_source_closure(
    root: Path,
    *,
    execution_mode: str = DEFAULT_EXECUTION_MODE,
    bucket_count: int | None = None,
) -> dict[str, Any]:
    """Run exact query 200 and return terminal-safe metadata only."""
    execution_mode = _validate_execution_mode(execution_mode)
    if execution_mode == SHARDED_EXECUTION_MODE:
        bucket_count = _validate_bucket_count(
            DEFAULT_BUCKET_COUNT if bucket_count is None else bucket_count
        )
    elif bucket_count is not None:
        raise DatabaseError(
            "bucket_count is only valid for the subject_buckets execution mode."
        )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = root / "artifacts" / "profiling" / stamp
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    destination.chmod(0o700)
    manifest_path = destination / "manifest.json"
    stderr_path = destination / "psql.stderr"
    started = time.monotonic()

    stages: dict[str, dict[str, Any]] = {
        "names_discovery": _initial_stage(NAMES_DISCOVERY_FILE),
        "detail_seed_discovery": _initial_stage(DETAIL_SEED_DISCOVERY_FILE),
        "global_head": _initial_stage(GLOBAL_HEAD_FILE),
        "global_detail": _initial_stage(GLOBAL_DETAIL_FILE),
        "global_order": _initial_stage(GLOBAL_ORDER_FILE),
    }
    if execution_mode == UNBUCKETED_EXECUTION_MODE:
        stages["unbucketed_event"] = _initial_stage(UNBUCKETED_EVENT_FILE)
    else:
        for index in range(bucket_count):
            stages[f"event_bucket_{index}"] = _initial_stage(EVENT_BUCKET_FILE)

    scan_counts = _safe_scan_counts(execution_mode, bucket_count)
    report: dict[str, Any] = {
        "schema_version": 3,
        "started_at_utc": _now(),
        "status": "running",
        "scope": "aggregate_private_event_source_closure",
        "dataset_version_verified": False,
        "selected_queries": [QUERY_NAME],
        "execution_mode": execution_mode,
        "bucket_count": bucket_count,
        "requested_controls": {
            "read_only": True,
            "same_snapshot": True,
            "transaction_isolation": "repeatable read",
            **SESSION_SETTINGS,
        },
        "confirmed_controls": {
            "read_only": False,
            "same_snapshot": False,
            "transaction_isolation": None,
            "session_settings_applied": False,
            "rollback": False,
        },
        # Compatibility fields retained for the evidence/audit layer.
        "requested_read_only": True,
        "read_only_confirmed": False,
        "requested_same_snapshot": True,
        "same_snapshot_confirmed": False,
        "requested_transaction_isolation": "repeatable read",
        "transaction_isolation_confirmed": None,
        "requested_jit": "off",
        "rollback_confirmed": False,
        "timeout_ms_per_statement": STATEMENT_TIMEOUT_MS,
        "cumulative_frame_byte_limit": MAX_CUMULATIVE_FRAME_BYTES,
        "executed_sql_byte_limit": MAX_EXECUTED_SQL_BYTES,
        "source_scan_counts": scan_counts,
        "artifact_modes": {
            "directory": _mode(destination),
            "manifest": "0600",
            "stderr": None,
            "value_files": {},
        },
        "queries": [],
        "limitations": (
            "Exact source closure within one read-only repeatable-read snapshot; "
            "controlled dictionaries remain private and no cohort is validated."
        ),
    }
    entry: dict[str, Any] = {
        "query": QUERY_NAME,
        "file": (
            UNBUCKETED_EVENT_FILE
            if execution_mode == UNBUCKETED_EXECUTION_MODE
            else EVENT_BUCKET_FILE
        ),
        "scope": "aggregate",
        "status": "running",
        "started_at_utc": _now(),
        "max_rows_per_stage": MAX_ROWS,
        "bucket_count": bucket_count,
        "rows": None,
        "output_sha256": None,
        "output_persisted": False,
        "private_discovery_persisted": False,
        "executed_sql_persisted": False,
        "completeness_status": "not_evaluated",
        "failure_value_cleanup_confirmed": None,
        "execution": (
            "names_seed_globals_unbucketed_event_same_snapshot"
            if execution_mode == UNBUCKETED_EXECUTION_MODE
            else "names_seed_globals_subject_buckets_same_snapshot"
        ),
        "stage_order": list(stages),
        "stages": stages,
    }
    report["queries"].append(entry)

    session: _PersistentPsql | None = None
    pending_error: str | None = None
    deferred_exception: BaseException | None = None
    rollback_marker: str | None = None
    controls: dict[str, dict[str, Any]] = {}
    executed_controls: list[str] = []
    cumulative_frame_bytes = 0
    cumulative_control_bytes = 0
    value_paths: list[Path] = []
    manifest_persisted = False
    manifest_cleanup_confirmed: bool | None = None

    try:
        paths = {
            "names_discovery": root / NAMES_DISCOVERY_FILE,
            "detail_seed_discovery": root / DETAIL_SEED_DISCOVERY_FILE,
            "global_head": root / GLOBAL_HEAD_FILE,
            "global_detail": root / GLOBAL_DETAIL_FILE,
            "global_order": root / GLOBAL_ORDER_FILE,
            "event_template": root / (
                UNBUCKETED_EVENT_FILE
                if execution_mode == UNBUCKETED_EXECUTION_MODE
                else EVENT_BUCKET_FILE
            ),
        }
        templates: dict[str, str] = {}
        for label, path in paths.items():
            raw = path.read_bytes()
            if label == "event_template":
                try:
                    template = raw.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise DatabaseError(
                        "The query-200 event SQL template is not valid UTF-8."
                    ) from exc
                if execution_mode == UNBUCKETED_EXECUTION_MODE:
                    _record_template(stages["unbucketed_event"], raw)
                else:
                    # One reviewed bucket template is executed repeatedly;
                    # each bucket records its own render/control/frame evidence.
                    for index in range(bucket_count):
                        _record_template(stages[f"event_bucket_{index}"], raw)
                templates[label] = template
            else:
                templates[label] = _record_template(stages[label], raw)

        names_sql = _statement_body(templates["names_discovery"])
        _record_render(stages["names_discovery"], names_sql)
        client = PsqlClient(root, STATEMENT_TIMEOUT_MS)
        session = _PersistentPsql(client, stderr_path)

        rollback_marker = "__APRIL_ROLLBACK_" + secrets.token_hex(24) + "__"
        marker = "__APRIL_NAMES_" + secrets.token_hex(24) + "__"
        names_control = _session_preamble() + names_sql + ";\n\\echo " + marker + "\n"
        cumulative_control_bytes = _bounded_add(
            cumulative_control_bytes,
            len(names_control.encode("utf-8")),
            MAX_EXECUTED_SQL_BYTES,
            "executed SQL",
        )
        executed_controls.append(names_control)
        names_frame = _run_frame(
            session,
            stages["names_discovery"],
            names_control,
            marker,
            MAX_DISCOVERY_BYTES * 2,
        )
        cumulative_frame_bytes = _bounded_add(
            cumulative_frame_bytes,
            len(names_frame),
            MAX_CUMULATIVE_FRAME_BYTES,
            "PostgreSQL frame output",
        )
        names = _parse_names_frame(names_frame)
        stages["names_discovery"].update(status="validated_in_memory", rows=1)
        controls["names_discovery"] = names

        seed_sql = render_detail_seed_discovery(
            templates["detail_seed_discovery"], names
        )
        _record_render(stages["detail_seed_discovery"], seed_sql)
        marker = "__APRIL_SEED_" + secrets.token_hex(24) + "__"
        seed_control = seed_sql + ";\n\\echo " + marker + "\n"
        cumulative_control_bytes = _bounded_add(
            cumulative_control_bytes,
            len(seed_control.encode("utf-8")),
            MAX_EXECUTED_SQL_BYTES,
            "executed SQL",
        )
        executed_controls.append(seed_control)
        seed_frame = _run_frame(
            session,
            stages["detail_seed_discovery"],
            seed_control,
            marker,
            MAX_DISCOVERY_BYTES * 2,
        )
        cumulative_frame_bytes = _bounded_add(
            cumulative_frame_bytes,
            len(seed_frame),
            MAX_CUMULATIVE_FRAME_BYTES,
            "PostgreSQL frame output",
        )
        seeds = _parse_detail_seed_frame(seed_frame, names)
        stages["detail_seed_discovery"].update(
            status="validated_in_memory", rows=1
        )
        controls["detail_seed_discovery"] = seeds
        discovery = _merge_discovery(names, seeds)

        fragments: dict[str, list[dict[str, str]]] = {}
        detail_code_name_flags: list[dict[str, Any]] = []
        for label in ("global_head", "global_detail", "global_order"):
            rendered = render_known_template(templates[label], discovery, label)
            _record_render(stages[label], rendered)
            marker = "__APRIL_" + label.upper() + "_" + secrets.token_hex(24) + "__"
            control = _aggregate_control(rendered, marker)
            cumulative_control_bytes = _bounded_add(
                cumulative_control_bytes,
                len(control.encode("utf-8")),
                MAX_EXECUTED_SQL_BYTES,
                "executed SQL",
            )
            executed_controls.append(control)
            frame = _run_frame(
                session, stages[label], control, marker, MAX_RESULT_BYTES
            )
            cumulative_frame_bytes = _bounded_add(
                cumulative_frame_bytes,
                len(frame),
                MAX_CUMULATIVE_FRAME_BYTES,
                "PostgreSQL frame output",
            )
            _, rows, stage_controls = _parse_result_frame(frame)
            frame_rows = len(rows)
            if label == "global_detail":
                rows, detail_code_name_flags = _extract_detail_code_dictionary(rows)
                canonical_dictionary = json.dumps(
                    detail_code_name_flags,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                stages[label]["private_dictionary_rows"] = len(
                    detail_code_name_flags
                )
                stages[label]["private_dictionary_sha256"] = _sha(
                    canonical_dictionary
                )
                stages[label]["merge_rows"] = len(rows)
            try:
                validate_source_closure_fragment(
                    label,
                    rows,
                    execution_mode=execution_mode,
                    bucket_count=bucket_count,
                )
            except SourceClosureMergeError as exc:
                _record_merge_validation_failure(
                    entry, stages, label, exc.code
                )
                raise DatabaseError(
                    "Query-200 fragment failed its strict validation contract."
                ) from exc
            fragments[label] = rows
            controls[label] = stage_controls
            stages[label].update(status="validated_in_memory", rows=frame_rows)

        try:
            _validate_discovery_vocabulary_sets(fragments, discovery)
        except DatabaseError as exc:
            _record_merge_validation_failure(
                entry, stages, "global_order",
                MergeValidationErrorCode.GLOBAL_CONTRACT_REJECTED,
            )
            raise DatabaseError(
                "Query-200 global vocabulary failed its strict validation contract."
            ) from exc
        discovery["detail_code_name_flags"] = detail_code_name_flags

        event_indexes: list[int | None] = (
            [None]
            if execution_mode == UNBUCKETED_EXECUTION_MODE
            else list(range(bucket_count))
        )
        for index in event_indexes:
            label = (
                "unbucketed_event" if index is None else f"event_bucket_{index}"
            )
            rendered = render_known_template(
                templates["event_template"],
                discovery,
                (
                    "unbucketed_event"
                    if execution_mode == UNBUCKETED_EXECUTION_MODE
                    else "event_bucket"
                ),
                bucket_index=index if execution_mode == SHARDED_EXECUTION_MODE else None,
                bucket_count=(
                    bucket_count if execution_mode == SHARDED_EXECUTION_MODE else None
                ),
            )
            _record_render(stages[label], rendered)
            marker = (
                "__APRIL_EVENT_" if index is None else "__APRIL_BUCKET_" + str(index) + "_"
            ) + secrets.token_hex(24) + "__"
            control = _aggregate_control(rendered, marker)
            cumulative_control_bytes = _bounded_add(
                cumulative_control_bytes,
                len(control.encode("utf-8")),
                MAX_EXECUTED_SQL_BYTES,
                "executed SQL",
            )
            executed_controls.append(control)
            frame = _run_frame(
                session, stages[label], control, marker, MAX_RESULT_BYTES
            )
            cumulative_frame_bytes = _bounded_add(
                cumulative_frame_bytes,
                len(frame),
                MAX_CUMULATIVE_FRAME_BYTES,
                "PostgreSQL frame output",
            )
            _, rows, stage_controls = _parse_result_frame(frame)
            if execution_mode == UNBUCKETED_EXECUTION_MODE:
                stages[label]["detail_dictionary_guard"] = (
                    _validate_event_dictionary_guard(
                        rows, len(detail_code_name_flags)
                    )
                )
            else:
                assert index is not None
                stages[label]["detail_dictionary_guard"] = (
                    _validate_bucket_dictionary_guard(
                        rows, len(detail_code_name_flags), index, bucket_count
                    )
                )
            try:
                validate_source_closure_fragment(
                    label,
                    rows,
                    execution_mode=execution_mode,
                    bucket_count=bucket_count,
                )
            except SourceClosureMergeError as exc:
                _record_merge_validation_failure(
                    entry, stages, label, exc.code
                )
                raise DatabaseError(
                    "Query-200 fragment failed its strict validation contract."
                ) from exc
            fragments[label] = rows
            controls[label] = stage_controls
            stages[label].update(status="validated_in_memory", rows=len(rows))

        snapshot_token = _assert_same_snapshot_controls(controls)
        snapshot_sha256 = _sha(snapshot_token.encode("utf-8"))
        for stage in stages.values():
            stage["observed_transaction_isolation"] = "repeatable read"
            stage["observed_transaction_read_only"] = "on"
            stage["observed_snapshot_sha256"] = snapshot_sha256

        try:
            merged = merge_source_closure_fragments(
                fragments,
                bucket_count=bucket_count,
                execution_mode=execution_mode,
                metadata_constants=scan_counts,
            )
        except SourceClosureMergeError as exc:
            # Persist only the closed enum token.  The detailed local message
            # may name a dimension or controlled-vocabulary value and is never
            # copied into the manifest or returned terminal summary.
            _record_merge_validation_failure(
                entry, stages, "final_merge", exc.code
            )
            raise DatabaseError(
                "Query-200 fragment merge failed its strict validation contract."
            ) from exc
        try:
            output, merge_summary = _validate_merge_result(
                merged, execution_mode, bucket_count
            )
        except DatabaseError:
            _record_merge_validation_failure(
                entry,
                stages,
                "final_result",
                MergeValidationErrorCode.RESULT_CONTRACT_REJECTED,
            )
            raise
        entry["merge_validation"] = merge_summary
        entry["merged_rows"] = len(merged.rows)

        rollback_control = "ROLLBACK;\n\\echo " + rollback_marker + "\n"
        rollback_bytes = rollback_control.encode("utf-8")
        quit_control = "\\q\n"
        executed_sql_budget_bytes = _bounded_add(
            cumulative_control_bytes,
            len(rollback_bytes),
            MAX_EXECUTED_SQL_BYTES,
            "executed SQL",
        )
        executed_sql_budget_bytes = _bounded_add(
            executed_sql_budget_bytes,
            len(quit_control.encode("utf-8")),
            MAX_EXECUTED_SQL_BYTES,
            "executed SQL",
        )
        entry["rollback_control_sha256"] = _sha(rollback_bytes)
        entry["rollback_control_bytes"] = len(rollback_bytes)
        session.confirm_rollback(rollback_marker)
        executed_controls.append(rollback_control)
        report["rollback_confirmed"] = True
        report["confirmed_controls"]["rollback"] = True
        returncode = session.close()
        session = None
        entry["psql_returncode"] = returncode
        if returncode != 0:
            raise DatabaseError(
                "PostgreSQL session did not exit cleanly after confirmed rollback."
            )

        report["read_only_confirmed"] = True
        report["transaction_isolation_confirmed"] = "repeatable read"
        report["same_snapshot_confirmed"] = True
        report["snapshot_token_sha256"] = snapshot_sha256
        report["confirmed_controls"].update({
            "read_only": True,
            "same_snapshot": True,
            "transaction_isolation": "repeatable read",
            # ON_ERROR_STOP plus a clean psql exit confirms every SET LOCAL in
            # the recorded preamble was accepted for this transaction.
            "session_settings_applied": True,
        })

        private_dictionary = (
            json.dumps(discovery, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        executed = ("".join(executed_controls) + quit_control).encode("utf-8")
        if len(executed) != executed_sql_budget_bytes:
            raise DatabaseError(
                "Query-200 executed SQL accounting did not match its byte total."
            )
        artifacts = (
            (QUERY_NAME + ".discovery.json", private_dictionary, "discovery"),
            (QUERY_NAME + ".executed.sql", executed, "executed_sql"),
            (QUERY_NAME + ".csv", output, "output"),
        )
        for filename, payload, role in artifacts:
            path = destination / filename
            value_paths.append(path)
            _write_private(path, payload)
            if _mode(path) != "0600":
                raise DatabaseError("A private query-200 artifact has an unsafe mode.")
            report["artifact_modes"]["value_files"][filename] = "0600"
            entry[role + "_file"] = filename
            entry[role + "_sha256"] = _sha(payload)
            entry[role + "_bytes"] = len(payload)
            if role == "discovery":
                entry["private_discovery_persisted"] = True
            else:
                entry[role + "_persisted"] = True

        entry["discovery_value_counts"] = {
            key: len(discovery[key]) for key in (
                "emar_names",
                "detail_names",
                "pharmacy_names",
                "prescription_names",
                "seed_product_codes",
                "detail_code_name_flags",
            )
        }
        for stage in stages.values():
            stage["status"] = "complete"
        entry.update(
            status="complete",
            rows=len(merged.rows),
            output_sha256=_sha(output),
            output_persisted=True,
            completeness_status="complete_within_declared_scope",
        )
        report["status"] = "complete"
    except DatabaseError as exc:
        report["status"] = "failed"
        pending_error = str(exc)
    except Exception:
        report["status"] = "failed"
        pending_error = (
            "Sharded PostgreSQL inspection failed before it could produce "
            "verified evidence."
        )
    except BaseException as exc:
        report["status"] = "failed"
        pending_error = "Query-200 execution was interrupted before completion."
        deferred_exception = exc
    finally:
        if report["status"] != "complete" and session is not None and rollback_marker:
            try:
                session.confirm_rollback(rollback_marker)
                report["rollback_confirmed"] = True
                report["confirmed_controls"]["rollback"] = True
            except BaseException as exc:
                if deferred_exception is None and not isinstance(exc, Exception):
                    deferred_exception = exc
        if session is not None:
            try:
                entry["psql_returncode"] = session.close()
            except BaseException as exc:
                entry["psql_returncode"] = None
                if deferred_exception is None and not isinstance(exc, Exception):
                    deferred_exception = exc
        if report["status"] != "complete":
            for stage in stages.values():
                if stage["status"] == "running":
                    stage["status"] = "failed"
            # A filesystem error after rollback must not leave a partial
            # dictionary, executed SQL file, or result CSV behind.
            entry["failure_value_cleanup_confirmed"] = _remove_private_values(
                value_paths
            )
            if not entry["failure_value_cleanup_confirmed"]:
                report["value_artifact_cleanup_error"] = (
                    "One or more private value artifacts could not be removed "
                    "after a filesystem failure."
                )
            report["artifact_modes"]["value_files"] = {}
            entry["private_discovery_persisted"] = False
            entry["executed_sql_persisted"] = False
            entry["output_persisted"] = False
            if stderr_path.is_file():
                try:
                    raw_error = stderr_path.read_text(errors="replace")[-16384:]
                except OSError:
                    raw_error = ""
            else:
                raw_error = ""
            report["error"] = _safe_error(raw_error) if raw_error.strip() else (
                pending_error or "Sharded PostgreSQL inspection failed."
            )
            entry["status"] = "failed"
            entry["error"] = report["error"]
        if stderr_path.is_file():
            try:
                stderr_bytes = stderr_path.read_bytes()
                entry["stderr_file"] = stderr_path.name
                entry["stderr_bytes"] = len(stderr_bytes)
                entry["stderr_sha256"] = _sha(stderr_bytes)
                report["artifact_modes"]["stderr"] = _mode(stderr_path)
            except OSError:
                pass
        entry["finished_at_utc"] = _now()
        entry["elapsed_seconds"] = round(time.monotonic() - started, 6)
        entry["cumulative_frame_bytes"] = cumulative_frame_bytes
        entry["cumulative_control_bytes"] = cumulative_control_bytes
        report["finished_at_utc"] = _now()
        try:
            _write_private(
                manifest_path,
                (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
            manifest_persisted = True
        except BaseException as exc:
            # A completed run without its manifest is not reviewable evidence.
            # Remove all value-bearing files, including any partial manifest,
            # and return only terminal-safe in-memory failure metadata.
            report["status"] = "failed"
            entry["status"] = "failed"
            entry["rows"] = None
            entry["completeness_status"] = "not_evaluated"
            entry["private_discovery_persisted"] = False
            entry["executed_sql_persisted"] = False
            entry["output_persisted"] = False
            entry["failure_value_cleanup_confirmed"] = _remove_private_values(
                value_paths
            )
            try:
                manifest_path.unlink(missing_ok=True)
            except OSError:
                pass
            try:
                manifest_cleanup_confirmed = not manifest_path.exists()
            except OSError:
                manifest_cleanup_confirmed = False

            if deferred_exception is None and not isinstance(exc, Exception):
                deferred_exception = exc

    if deferred_exception is not None:
        raise deferred_exception

    summary_query = {key: entry.get(key) for key in (
        "query",
        "scope",
        "status",
        "rows",
        "completeness_status",
    )}
    if "merge_validation_error_code" in entry:
        summary_query["merge_validation_error_code"] = entry[
            "merge_validation_error_code"
        ]
        summary_query["merge_validation_error_origin"] = entry[
            "merge_validation_error_origin"
        ]
    summary = {
        "status": report["status"],
        "report": str(manifest_path) if manifest_persisted else None,
        "artifact_directory": str(destination),
        "value_artifact_cleanup_confirmed": entry.get(
            "failure_value_cleanup_confirmed"
        ),
        "manifest_cleanup_confirmed": manifest_cleanup_confirmed,
        "queries": [summary_query],
    }
    if not manifest_persisted:
        summary["note"] = (
            "The terminal-safe manifest could not be persisted; private value "
            "artifact and manifest cleanup status are reported separately."
        )
    return summary


def run_sharded_source_closure(
    root: Path, bucket_count: int = DEFAULT_BUCKET_COUNT
) -> dict[str, Any]:
    """Compatibility entry point for the subject-bucket production mode."""
    return run_source_closure(
        root,
        execution_mode=SHARDED_EXECUTION_MODE,
        bucket_count=bucket_count,
    )
