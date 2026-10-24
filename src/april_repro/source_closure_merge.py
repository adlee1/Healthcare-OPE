"""Strict, deterministic merge for partitioned query-200 aggregate output.

The database runner executes four kinds of SELECTs in one read-only snapshot:

``global_head``
    ``closure_global_head_metadata`` plus head ``source_vocabulary`` rows.
``global_detail``
    ``closure_global_detail_metadata``, detail ``source_vocabulary`` rows, and
    ``local_product_code_shape`` rows.
``global_order``
    ``closure_global_order_metadata`` plus pharmacy/prescription vocabulary.
``unbucketed_event`` (preferred)
    One ``closure_event_metadata`` control row, two safe admission diagnostic
    sections, and the four public event
    sections from the unbucketed event-only query.
``event_bucket_N`` (fallback)
    One ``closure_bucket_metadata`` control row, two safe admission diagnostic
    sections, and the four additive event sections for subject-hash bucket ``N``.

This module accepts only the four CSV columns produced by those SELECTs.  It
parses JSON with duplicate-key rejection, validates every internal schema, and
then constructs the public closure rows.  It deliberately knows the internal
metadata counter names: changing a SQL output is therefore a contract change,
not a silently accepted extra field.

Bucket event rows are additive by exact dimensions.  Integer counters are
summed, except the fixed query-199 reference; boolean and string counters must
match exactly.  Global dictionary/code-shape rows are a disjoint union.  The
returned CSV has a stable section/records-descending/canonical-dimensions order.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import csv
from enum import StrEnum
import io
import json
import re
from typing import Any, Iterable, Iterator, Mapping, Sequence


EXPECTED_COLUMNS = ("section", "dimensions", "records", "counters")
KNOWN_QUERY199_HEADS = 559_191
BUCKET_ORIGIN = re.compile(r"^event_bucket_(0|[1-9][0-9]*)$")
NONNEGATIVE_INTEGER = re.compile(r"0|[1-9][0-9]*")

# These are forbidden JSON keys at every depth.  Aggregate names such as
# ``local_product_codes`` are intentionally different: they contain counts,
# not identifier values.
RAW_IDENTIFIER_OR_TIME_KEYS = {
    "emar_id", "subject_id", "hadm_id", "pharmacy_id", "poe_id",
    "emar_seq", "charttime", "storetime", "scheduletime", "product_code",
}

DISCOVERY_COUNTERS = {
    "non_null_emar_medication_names",
    "non_null_detail_product_descriptions",
    "non_null_pharmacy_medication_names",
}

ADMISSION_STATUS_COUNTERS = {
    "admission_exact_match_heads",
    "admission_missing_subject_and_hadm_heads",
    "admission_missing_subject_id_heads",
    "admission_missing_hadm_id_heads",
    "admission_hadm_absent_from_admissions_heads",
    "admission_subject_mismatch_heads",
}
ADMISSION_ANOMALY_COUNTERS = {
    "nonexact_admission_link_heads",
    "nonexact_admission_link_subjects",
    "nonexact_admission_link_pairs",
}
ADMISSION_LINK_STATUSES = {
    "missing_subject_and_hadm",
    "missing_subject_id",
    "missing_hadm_id",
    "nonnull_hadm_absent_from_admissions",
    "hadm_subject_mismatch",
    "exact_subject_hadm_match",
}
ADMISSION_STATUS_FIELD = {
    "missing_subject_and_hadm": "admission_missing_subject_and_hadm_heads",
    "missing_subject_id": "admission_missing_subject_id_heads",
    "missing_hadm_id": "admission_missing_hadm_id_heads",
    "nonnull_hadm_absent_from_admissions":
        "admission_hadm_absent_from_admissions_heads",
    "hadm_subject_mismatch": "admission_subject_mismatch_heads",
    "exact_subject_hadm_match": "admission_exact_match_heads",
}

HEAD_METADATA_INTS = DISCOVERY_COUNTERS | {
    "selected_indexed_source_names", "direct_head_evidence_heads",
    "query199_head_scope_distinct_heads",
    "query199_prior_real_audit_reference_heads",
}
HEAD_METADATA_BOOLS = {
    "query199_reference_requires_real_audit_comparison": True,
    "raw_identifiers_times_or_patient_text_emitted": False,
}

DETAIL_METADATA_INTS = DISCOVERY_COUNTERS | {
    "selected_indexed_source_names", "seed_local_product_codes",
    "largest_one_hop_code_detail_rows", "raw_lexical_detail_product_rows",
    "identity_consistent_lexical_detail_product_rows",
    "identity_consistent_lexical_detail_events",
    "detail_code_dictionary_names", "selected_detail_rows",
    "detail_text_rows", "detail_code_rows",
}
DETAIL_METADATA_BOOLS = {
    "declared_scope_exact": True,
    "raw_identifiers_times_or_patient_text_emitted": False,
}
DETAIL_METADATA_STRINGS = {
    "lexical_scope": "query 199 potassium/bounded-KCl scope plus K-Phos/KPhos",
    "local_product_code_scope": "one exact-value hop from lexical detail product rows",
    "product_code_interpretation": "MIMIC-local linkage token, not NDC",
}

ORDER_METADATA_INTS = DISCOVERY_COUNTERS | {
    "selected_indexed_source_names", "selected_prescription_drug_names",
    "order_linked_detail_product_rows", "selected_pharmacy_keys",
    "selected_pharmacy_full_component_rows", "selected_prescription_keys",
    "selected_prescription_full_component_rows",
    "identity_consistent_lexical_detail_events",
    "global_order_prescription_lexical_pass_count",
    "global_order_prescription_component_pass_count",
}
ORDER_METADATA_BOOLS = {
    "declared_scope_exact": True,
    "pharmacy_id_primary_key_confirmed": True,
    "pharmacy_id_integer_types_confirmed": True,
    "raw_identifiers_times_or_patient_text_emitted": False,
}
ORDER_METADATA_STRINGS = {
    "lexical_scope": "query 199 potassium/bounded-KCl scope plus K-Phos/KPhos",
}

BUCKET_METADATA_INTS = {
    "merge_protocol_version", "bucket_index", "bucket_count",
    "null_subject_bucket", "candidate_emar_heads", "subjects", "admissions",
    "query199_head_scope_distinct_heads", "bucket_assignment_violations",
    "detail_subject_partition_groups_checked",
    "detail_subject_partition_identity_violations",
    "order_detail_subject_partition_groups_checked",
    "order_detail_subject_partition_identity_violations",
    "null_subject_candidate_heads",
    *ADMISSION_STATUS_COUNTERS, *ADMISSION_ANOMALY_COUNTERS,
    "duplicate_candidate_emar_heads", "selected_pharmacy_keys_global",
    "selected_pharmacy_full_component_rows_global",
    "selected_prescription_keys_global",
    "selected_prescription_full_component_rows_global",
    "non_null_emar_medication_names",
    "non_null_detail_product_descriptions",
    "non_null_pharmacy_medication_names",
    "identity_consistent_lexical_detail_product_rows",
    "identity_consistent_lexical_detail_events", "seed_local_product_codes",
    "selected_detail_rows_in_bucket", "detail_text_rows_in_bucket",
    "detail_code_rows_in_bucket", "order_detail_link_rows_in_bucket",
    "detail_code_dictionary_miss_names",
    "supplied_detail_code_dictionary_names",
}
BUCKET_METADATA_BOOLS = {
    "bucket_parameters_valid": True,
    "emar_id_primary_key_confirmed": True,
    "pharmacy_id_primary_key_confirmed": True,
    "pharmacy_id_integer_types_confirmed": True,
    "admissions_hadm_id_primary_key_confirmed": True,
    "event_sections_additive_by_exact_dimensions": True,
    "missing_dimension_rows_merge_as_zero": True,
    "constant_fields_require_exact_equality": True,
    "admission_count_uses_nonnull_subject_hadm_pairs": True,
    "logical_admission_pairs_additive_by_subject_partition": True,
    "admission_link_status_partition_complete": True,
    "admission_link_anomalies_reported_not_repaired": True,
    "raw_identifiers_times_or_patient_text_emitted": False,
}
BUCKET_METADATA_STRINGS = {
    "bucket_assignment_basis": "emar_head_subject_id",
    "bucket_hash_function": "hashint8extended(subject_id::bigint,0)",
    "bucket_remainder_normalization": "((hash % count)+count)%count",
}

EVENT_METADATA_INTS = {
    "candidate_emar_heads", "subjects", "admissions",
    "query199_head_scope_distinct_heads", "null_subject_candidate_heads",
    "duplicate_candidate_emar_heads",
    "detail_text_dictionary_miss_rows", "detail_code_dictionary_miss_rows",
    "supplied_detail_code_dictionary_names",
    "selected_detail_rows", "detail_text_rows", "detail_code_rows",
    "order_detail_link_rows",
} | ADMISSION_STATUS_COUNTERS | ADMISSION_ANOMALY_COUNTERS
EVENT_METADATA_BOOLS = {
    "emar_id_primary_key_confirmed": True,
    "pharmacy_id_primary_key_confirmed": True,
    "pharmacy_id_integer_types_confirmed": True,
    "admissions_hadm_id_primary_key_confirmed": True,
    "event_aggregation_unbucketed": True,
    "admission_count_uses_nonnull_subject_hadm_pairs": True,
    "admission_link_status_partition_complete": True,
    "admission_link_anomalies_reported_not_repaired": True,
    "raw_identifiers_times_or_patient_text_emitted": False,
}

ADMISSION_SUMMARY_INTS = {
    "candidate_emar_heads", "subjects", "admissions",
    "nonexact_admission_link_hadm_ids_within_partition",
} | ADMISSION_STATUS_COUNTERS | ADMISSION_ANOMALY_COUNTERS
ADMISSION_SUMMARY_BOOLS = {"formal_cohort": False}
ADMISSION_EVIDENCE_INTS = {"candidate_emar_heads"}
ADMISSION_EVIDENCE_BOOLS = {"formal_cohort": False}

VOCAB_DIMENSIONS = {
    "source_type", "evidence_path", "raw_name", "normalized_name",
    "source_review_stratum", "focal_kcl_hint", "broader_repletion_hint",
    "non_repletion_active_drug_hint",
}
VOCAB_INTS = {
    "source_rows", "emar_events", "pharmacy_keys",
    "distinct_local_product_codes", "rows_missing_local_product_code",
}
VOCAB_BOOLS = {
    "dictionary_value_is_patient_text": False,
    "source_review_stratum_is_final_policy": False,
}
SOURCE_PATHS_BY_ORIGIN = {
    "global_head": {("emar_medication", "head_text")},
    "global_detail": {
        ("detail_product_description", "detail_text_seed"),
        ("detail_product_description", "detail_local_code_closure"),
    },
    "global_order": {
        ("pharmacy_medication", "pharmacy_name"),
        ("prescription_drug", "prescription_name"),
    },
}
REVIEW_STRATA = {
    "focal_kcl_repletion_hint",
    "broader_phosphate_or_acetate_repletion_hint",
    "other_potassium_salt_review",
    "non_repletion_active_drug_hint",
    "unresolved_name_or_local_code_review",
}

CODE_DIMENSIONS = {
    "description_shape", "review_shape", "unresolved_description_present",
    "active_drug_description_present", "missing_description_present",
}
CODE_INTS = {
    "local_product_codes", "lexical_seed_detail_rows", "closure_detail_rows",
    "lexical_seed_event_memberships", "closure_event_memberships",
}
CODE_BOOLS = {
    "event_memberships_are_additive_across_codes": True,
    "local_product_code_is_ndc": False,
    "local_product_code_used_for_final_product_identity": False,
}

EVENT_DIMENSIONS = {
    "raw_source_mask", "identity_valid_source_mask", "strict_poe_source_mask",
    "coarse_raw_source_mask", "coarse_identity_valid_source_mask",
    "coarse_strict_poe_source_mask", "valid_review_family_mask",
    "head_name_pattern", "recovery_pattern", "review_pattern",
}
STATUS_COUNTERS = {
    "administered_exact_heads", "partial_administered_heads",
    "delayed_administered_heads", "start_or_restart_control_heads",
    "not_given_or_hold_heads", "other_control_record_heads",
    "missing_status_heads", "other_status_heads",
}
EVENT_INTS = {
    "emar_heads", "subjects", "admissions", "head_raw_heads",
    "detail_text_raw_heads", "detail_code_raw_heads", "pharmacy_raw_heads",
    "prescription_raw_heads", "detail_text_identity_valid_heads",
    "detail_code_identity_valid_heads", "pharmacy_identity_valid_heads",
    "prescription_identity_valid_heads", "pharmacy_strict_poe_valid_heads",
    "prescription_strict_poe_valid_heads",
} | STATUS_COUNTERS
EVENT_BOOLS = {"formal_action": False}

RECOVERED_DIMENSIONS = {
    "raw_head_medication", "normalized_head_medication", "head_name_pattern",
}
RECOVERED_INTS = {
    "emar_heads", "subjects", "admissions", "administered_exact_heads",
    "detail_text_identity_valid_heads", "detail_code_identity_valid_heads",
    "pharmacy_identity_valid_heads", "prescription_identity_valid_heads",
    "focal_kcl_review_heads", "broader_phosphate_or_acetate_review_heads",
    "non_repletion_active_review_heads", "mixed_or_unresolved_review_heads",
}
RECOVERED_BOOLS = {
    "dictionary_value_is_patient_text": False,
    "head_name_adopted_as_source_policy": False,
}

CONSERVATION_INTS = {
    "candidate_emar_heads", "subjects", "admissions",
    "direct_head_evidence_heads", "query199_head_scope_distinct_heads",
    "query199_prior_real_audit_reference_heads", "detail_text_evidence_heads",
    "detail_code_evidence_heads", "pharmacy_name_evidence_heads",
    "prescription_name_evidence_heads", "pharmacy_name_evidence_via_head_key",
    "pharmacy_name_evidence_via_detail_key",
    "prescription_name_evidence_via_head_key",
    "prescription_name_evidence_via_detail_key",
    "pharmacy_strict_poe_valid_heads", "prescription_strict_poe_valid_heads",
    "heads_new_beyond_direct_name",
    "missing_head_name_recovered_by_valid_nondirect_evidence",
    "nonlexical_head_name_recovered_by_valid_nondirect_evidence",
    "identity_unresolved_only_heads",
}
CONSERVATION_CONSTANT_INTS = {"query199_prior_real_audit_reference_heads"}
CONSERVATION_BOOLS = {
    "source_memberships_overlap_and_are_not_additive": True,
    "formal_cohort": False,
}

PUBLIC_GUARD_VALUES: dict[str, bool | str] = {
    "declared_lexical_and_one_hop_code_scope_exact": True,
    "source_bits": "head=1, detail_text=2, detail_code=4, pharmacy=8, prescription=16",
    "coarse_source_bits": "head=1, any_detail=2, any_order=4",
    "review_family_bits":
        "kcl=1, phosphate_or_acetate=2, other_salt=4, active_drug=8, unresolved=16",
    "many_sides_preaggregated_before_event_join": True,
    "order_identity_and_poe_gates_use_all_selected_key_components": True,
    "null_subject_admission_or_sequence_fails_identity_validation": True,
    "detail_rows_examined": True,
    "detail_product_rows_require_subject_and_emar_seq_before_code_seed": True,
    "order_links_include_head_and_product_detail_pharmacy_keys": True,
    "strict_order_poe_mask_computed": True,
    "admission_count_uses_nonnull_subject_hadm_pairs": True,
    "admission_link_status_partition_complete": True,
    "admission_link_anomalies_reported_not_repaired": True,
    "admission_table_link_requires_exact_subject_hadm_pair": True,
    "admissions_hadm_id_primary_key_must_be_confirmed": True,
    "pharmacy_id_primary_key_must_be_confirmed": True,
    "pharmacy_id_integer_types_must_be_confirmed": True,
    "detail_code_dictionary_matches_global_private_flags": True,
    "product_code_is_ndc": False,
    "product_code_used_for_final_product_identity": False,
    "product_identity_decided": False,
    "product_description_other_examined": False,
    "unseeded_brand_vocabulary_exhausted": False,
    "complete_intervention_coverage": False,
    "final_source_policy": False,
    "review_strata_are_inclusion_rules": False,
    "route_is_administration_proof": False,
    "delivered_dose_defined": False,
    "formal_action": False,
    "zero_action_constructed": False,
    "formal_episode": False,
    "formal_label": False,
    "formal_non_icu_rule": False,
    "formal_cohort": False,
    "raw_identifiers_times_or_patient_text_emitted": False,
}
BUCKET_GUARD_VALUES: dict[str, bool | str] = {
    **PUBLIC_GUARD_VALUES,
    "subject_partitioned_event_shard": True,
    "bucket_assignment_uses_emar_head_subject_id": True,
    "detail_scan_partition_uses_emar_detail_subject_id": True,
    "detail_subject_partition_identity_violations_must_sum_to_zero": True,
    "order_detail_scan_partition_uses_emar_detail_subject_id": True,
    "order_detail_subject_partition_identity_violations_must_sum_to_zero": True,
    "null_head_subject_assigned_to_bucket_zero": True,
    "pharmacy_and_prescription_full_components_unbucketed": True,
    "event_sections_additive_by_exact_dimensions": True,
    "logical_admission_pairs_additive_by_subject_partition": True,
    "emar_id_primary_key_must_be_confirmed": True,
}

FORMAL_FALSE_GUARDS = {
    key for key, value in BUCKET_GUARD_VALUES.items()
    if value is False and (
        key.startswith("formal_")
        or key in {
            "product_identity_decided", "final_source_policy",
            "complete_intervention_coverage", "route_is_administration_proof",
            "delivered_dose_defined", "zero_action_constructed",
        }
    )
}

HEAD_PATTERNS = {
    "missing_head_name", "blank_head_name", "declared_lexical_head_name",
    "nonlexical_head_name",
}
RECOVERY_PATTERNS = {
    "direct_head_evidence_present", "recovered_without_direct_head_evidence",
    "linked_evidence_identity_unresolved",
}
REVIEW_PATTERNS = REVIEW_STRATA | {
    "identity_unresolved_only", "mixed_repletion_and_nonrepletion_hints",
    "mixed_repletion_or_unresolved_hints",
}

FINAL_SCAN_COUNTERS = {
    "names_discovery_prescription_lexical_pass_count",
    "global_order_prescription_lexical_pass_count",
    "global_order_prescription_component_pass_count",
    "event_closure_prescription_lexical_pass_count",
    "event_closure_prescription_component_pass_count",
    "total_prescription_lexical_pass_count",
    "total_prescription_component_pass_count",
}

GLOBAL_FRAGMENT_SPECIFICATIONS = {
    "global_head": (
        "closure_global_head_metadata", HEAD_METADATA_INTS,
        HEAD_METADATA_BOOLS, {}, {"source_vocabulary"},
    ),
    "global_detail": (
        "closure_global_detail_metadata", DETAIL_METADATA_INTS,
        DETAIL_METADATA_BOOLS, DETAIL_METADATA_STRINGS,
        {"source_vocabulary", "local_product_code_shape"},
    ),
    "global_order": (
        "closure_global_order_metadata", ORDER_METADATA_INTS,
        ORDER_METADATA_BOOLS, ORDER_METADATA_STRINGS, {"source_vocabulary"},
    ),
}


class MergeValidationErrorCode(StrEnum):
    """Terminal-safe location of a query-200 merge-contract rejection.

    These fixed tokens are the only merge diagnostic persisted by the runner.
    Detailed exception messages remain useful to unit tests and local debugging,
    but may contain fragment labels or controlled-vocabulary values and must not
    be copied into a manifest or terminal summary.
    """

    INPUT_CONTRACT_REJECTED = "Q200_MERGE_INPUT_CONTRACT_REJECTED"
    JSON_CONTRACT_REJECTED = "Q200_MERGE_JSON_CONTRACT_REJECTED"
    FORBIDDEN_RAW_FIELD_REJECTED = "Q200_MERGE_FORBIDDEN_RAW_FIELD_REJECTED"
    GLOBAL_CONTRACT_REJECTED = "Q200_MERGE_GLOBAL_CONTRACT_REJECTED"
    EVENT_CONTRACT_REJECTED = "Q200_MERGE_EVENT_CONTRACT_REJECTED"
    ADDITIVE_CONTRACT_REJECTED = "Q200_MERGE_ADDITIVE_CONTRACT_REJECTED"
    METADATA_CONTRACT_REJECTED = "Q200_MERGE_METADATA_CONTRACT_REJECTED"
    POSTMERGE_CONTRACT_REJECTED = "Q200_MERGE_POSTMERGE_CONTRACT_REJECTED"
    RESULT_CONTRACT_REJECTED = "Q200_MERGE_RESULT_CONTRACT_REJECTED"
    UNCLASSIFIED_CONTRACT_REJECTED = (
        "Q200_MERGE_UNCLASSIFIED_CONTRACT_REJECTED"
    )


class SourceClosureMergeError(ValueError):
    """A fragment violates the strict query-200 merge contract."""

    def __init__(
        self,
        message: str,
        *,
        code: MergeValidationErrorCode = (
            MergeValidationErrorCode.UNCLASSIFIED_CONTRACT_REJECTED
        ),
    ) -> None:
        if not isinstance(code, MergeValidationErrorCode):
            raise TypeError("code must be a MergeValidationErrorCode")
        super().__init__(message)
        self._code = code

    @property
    def code(self) -> MergeValidationErrorCode:
        return self._code

    def _assign_phase_code(self, code: MergeValidationErrorCode) -> None:
        if self._code is MergeValidationErrorCode.UNCLASSIFIED_CONTRACT_REJECTED:
            self._code = code


@dataclass(frozen=True)
class MergeResult:
    """Validated public rows, deterministic CSV, and merge-control evidence."""

    rows: list[dict[str, Any]]
    csv_text: str
    validation_summary: dict[str, Any]


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fail(
    message: str,
    *,
    code: MergeValidationErrorCode = (
        MergeValidationErrorCode.UNCLASSIFIED_CONTRACT_REJECTED
    ),
) -> None:
    raise SourceClosureMergeError(message, code=code)


@contextmanager
def _validation_phase(code: MergeValidationErrorCode) -> Iterator[None]:
    """Attach a safe phase code while preserving the detailed local error."""
    try:
        yield
    except SourceClosureMergeError as exc:
        exc._assign_phase_code(code)
        raise


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(
                f"JSON contains duplicate key {key!r}",
                code=MergeValidationErrorCode.JSON_CONTRACT_REJECTED,
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    _fail(
        f"JSON contains non-finite constant {value!r}",
        code=MergeValidationErrorCode.JSON_CONTRACT_REJECTED,
    )


def _parse_object(raw: Any, label: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        _fail(f"{label} must be a JSON string")
    try:
        value = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_reject_json_constant
        )
    except SourceClosureMergeError:
        raise
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise SourceClosureMergeError(
            f"{label} is not valid JSON",
            code=MergeValidationErrorCode.JSON_CONTRACT_REJECTED,
        ) from exc
    if not isinstance(value, dict):
        _fail(
            f"{label} must decode to a JSON object",
            code=MergeValidationErrorCode.JSON_CONTRACT_REJECTED,
        )
    _reject_raw_keys(value, label)
    return value


def _reject_raw_keys(value: Any, label: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                _fail(
                    f"{label} contains a non-string key",
                    code=MergeValidationErrorCode.JSON_CONTRACT_REJECTED,
                )
            if key.lower() in RAW_IDENTIFIER_OR_TIME_KEYS:
                _fail(
                    f"{label} contains forbidden raw identifier/time key {key!r}",
                    code=MergeValidationErrorCode.FORBIDDEN_RAW_FIELD_REJECTED,
                )
            _reject_raw_keys(child, label)
    elif isinstance(value, list):
        for child in value:
            _reject_raw_keys(child, label)


def _parse_row(raw: Mapping[str, Any], origin: str, number: int) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != set(EXPECTED_COLUMNS):
        _fail(f"{origin} row {number} must contain exactly {EXPECTED_COLUMNS!r}")
    section = raw["section"]
    if not isinstance(section, str) or not section:
        _fail(f"{origin} row {number} has an invalid section")
    records_raw = raw["records"]
    if not isinstance(records_raw, str) or NONNEGATIVE_INTEGER.fullmatch(records_raw) is None:
        _fail(f"{origin} row {number} records must be a canonical nonnegative integer string")
    return {
        "section": section,
        "dimensions": _parse_object(raw["dimensions"], f"{origin} row {number} dimensions"),
        "records": int(records_raw),
        "counters": _parse_object(raw["counters"], f"{origin} row {number} counters"),
        "_origin": origin,
        "_row": number,
    }


def _normalise_one_fragment(
    origin: Any, raw_rows: Sequence[Mapping[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(origin, str):
        _fail("fragment origins must be strings")
    if isinstance(raw_rows, (str, bytes)):
        _fail(f"{origin} rows must be a sequence of row mappings")
    try:
        rows = [
            _parse_row(row, origin, number)
            for number, row in enumerate(raw_rows, start=1)
        ]
    except TypeError as exc:
        raise SourceClosureMergeError(
            f"{origin} rows are not iterable mappings"
        ) from exc
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["section"], _canonical(row["dimensions"]))
        if key in seen:
            _fail(f"{origin} repeats dimensions in section {row['section']!r}")
        seen.add(key)
    return origin, rows


def _normalise_fragments(
    fragments: Mapping[str, Sequence[Mapping[str, Any]]]
    | Iterable[tuple[str, Sequence[Mapping[str, Any]]]],
    *, execution_mode: str, bucket_count: int | None,
) -> dict[str, list[dict[str, Any]]]:
    try:
        items = list(fragments.items()) if isinstance(fragments, Mapping) else list(fragments)
    except TypeError as exc:
        raise SourceClosureMergeError("fragments must be a mapping or iterable of pairs") from exc
    parsed: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            _fail("each fragment must be an (origin, rows) pair")
        origin, raw_rows = item
        if isinstance(origin, str) and origin in parsed:
            _fail("fragment origins must be unique strings")
        parsed_origin, rows = _normalise_one_fragment(origin, raw_rows)
        parsed[parsed_origin] = rows

    expected = {"global_head", "global_detail", "global_order"}
    if execution_mode == "subject_buckets":
        assert bucket_count is not None
        expected |= {f"event_bucket_{index}" for index in range(bucket_count)}
    else:
        expected.add("unbucketed_event")
    if set(parsed) != expected:
        missing = sorted(expected - set(parsed))
        extra = sorted(set(parsed) - expected)
        _fail(f"fragment origin set is incomplete or unexpected; missing={missing}, extra={extra}")
    return parsed


def _resolve_execution_mode(
    execution_mode: str | None, bucket_count: int | None,
) -> tuple[str, int | None]:
    mode = execution_mode
    if mode is None:
        mode = "subject_buckets" if bucket_count is not None else "unbucketed_event"
    if mode not in {"subject_buckets", "unbucketed_event"}:
        _fail("execution_mode must be 'subject_buckets' or 'unbucketed_event'")
    if mode == "subject_buckets":
        if type(bucket_count) is not int or bucket_count <= 0:
            _fail("subject_buckets mode requires a positive integer bucket_count")
        return mode, bucket_count
    if bucket_count is not None:
        _fail("unbucketed_event mode requires bucket_count=None")
    return mode, None


def _check_schema(
    value: dict[str, Any], *, ints: set[str] = frozenset(),
    bools: Mapping[str, bool] = {}, strings: Mapping[str, str] = {}, label: str,
) -> None:
    expected = set(ints) | set(bools) | set(strings)
    if set(value) != expected:
        _fail(f"{label} has unexpected keys: expected {sorted(expected)!r}, got {sorted(value)!r}")
    for key in ints:
        if type(value[key]) is not int or value[key] < 0:
            _fail(f"{label}.{key} must be a nonnegative integer, not boolean")
    for key, expected_value in bools.items():
        if type(value[key]) is not bool or value[key] is not expected_value:
            _fail(f"{label}.{key} must be exactly {expected_value!r}")
    for key, expected_value in strings.items():
        if not isinstance(value[key], str) or value[key] != expected_value:
            _fail(f"{label}.{key} must be exactly {expected_value!r}")


def _single(rows: list[dict[str, Any]], section: str, origin: str) -> dict[str, Any]:
    selected = [row for row in rows if row["section"] == section]
    if len(selected) != 1:
        _fail(f"{origin} must contain exactly one {section!r} row")
    return selected[0]


def _empty_dimensions(row: dict[str, Any]) -> None:
    if row["dimensions"] != {}:
        _fail(f"{row['_origin']} {row['section']} dimensions must be empty")


def _validate_metadata_row(
    row: dict[str, Any], ints: set[str], bools: Mapping[str, bool],
    strings: Mapping[str, str] = {},
) -> None:
    _empty_dimensions(row)
    _check_schema(row["counters"], ints=ints, bools=bools, strings=strings,
                  label=f"{row['_origin']} {row['section']} counters")


def _validate_controlled_name(value: Any, label: str, *, nullable: bool = True) -> None:
    if value is None and nullable:
        return
    if (not isinstance(value, str) or len(value) > 512
            or any(character in value for character in ("\x00", "\n", "\r"))):
        _fail(f"{label} is not a bounded controlled-vocabulary value")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise SourceClosureMergeError(
            f"{label} is not valid UTF-8 controlled-vocabulary text"
        ) from exc


def _validate_vocabulary(row: dict[str, Any], origin: str) -> None:
    dimensions = row["dimensions"]
    if set(dimensions) != VOCAB_DIMENSIONS:
        _fail(f"{origin} source_vocabulary has an unexpected dimension schema")
    if (not isinstance(dimensions["source_type"], str)
            or not isinstance(dimensions["evidence_path"], str)):
        _fail(f"{origin} source_type/evidence_path must be strings")
    pair = (dimensions["source_type"], dimensions["evidence_path"])
    if pair not in SOURCE_PATHS_BY_ORIGIN[origin]:
        _fail(f"{origin} emitted source/path pair {pair!r} outside its designation")
    _validate_controlled_name(dimensions["raw_name"], f"{origin} raw_name")
    _validate_controlled_name(dimensions["normalized_name"], f"{origin} normalized_name")
    if dimensions["raw_name"] is None and pair != (
        "detail_product_description", "detail_local_code_closure"
    ):
        _fail(f"{origin} emitted NULL raw_name outside local-code closure")
    expected_normalized = (
        re.sub(r"\s+", " ", dimensions["raw_name"].strip()).lower()
        if isinstance(dimensions["raw_name"], str) else None
    )
    if dimensions["normalized_name"] != expected_normalized:
        _fail(f"{origin} source_vocabulary normalized_name is inconsistent")
    if (not isinstance(dimensions["source_review_stratum"], str)
            or dimensions["source_review_stratum"] not in REVIEW_STRATA):
        _fail(f"{origin} source_vocabulary has an invalid review stratum")
    hint_keys = (
        "focal_kcl_hint", "broader_repletion_hint",
        "non_repletion_active_drug_hint",
    )
    if dimensions["raw_name"] is None:
        if dimensions["source_review_stratum"] != "unresolved_name_or_local_code_review":
            _fail(f"{origin} NULL source name must retain unresolved review stratum")
        if any(dimensions[key] is not None for key in hint_keys):
            _fail(f"{origin} NULL source name must retain SQL NULL hint dimensions")
    else:
        for key in hint_keys:
            if type(dimensions[key]) is not bool:
                _fail(f"{origin} source_vocabulary.{key} must be boolean")
    _check_schema(row["counters"], ints=VOCAB_INTS, bools=VOCAB_BOOLS,
                  label=f"{origin} source_vocabulary counters")
    if row["records"] != row["counters"]["source_rows"]:
        _fail(f"{origin} source_vocabulary records do not equal source_rows")
    for key in (
        "emar_events", "pharmacy_keys", "distinct_local_product_codes",
        "rows_missing_local_product_code",
    ):
        if row["counters"][key] > row["records"]:
            _fail(f"{origin} source_vocabulary.{key} exceeds records")


def _validate_code_shape(row: dict[str, Any]) -> None:
    dimensions = row["dimensions"]
    if set(dimensions) != CODE_DIMENSIONS:
        _fail("global_detail local_product_code_shape has an unexpected dimension schema")
    if (not isinstance(dimensions["description_shape"], str)
            or dimensions["description_shape"] not in {
        "no_nonnull_description", "one_nonnull_description", "multiple_nonnull_descriptions"
    }):
        _fail("local_product_code_shape has an invalid description_shape")
    if (not isinstance(dimensions["review_shape"], str)
            or dimensions["review_shape"] not in {
                "one_review_stratum", "multiple_review_strata"
            }):
        _fail("local_product_code_shape has an invalid review_shape")
    for key in CODE_DIMENSIONS - {"description_shape", "review_shape"}:
        if type(dimensions[key]) is not bool:
            _fail(f"local_product_code_shape.{key} must be boolean")
    _check_schema(row["counters"], ints=CODE_INTS, bools=CODE_BOOLS,
                  label="global_detail local_product_code_shape counters")
    if row["records"] != row["counters"]["local_product_codes"]:
        _fail("local_product_code_shape records do not equal local_product_codes")
    if row["counters"]["lexical_seed_detail_rows"] > row["counters"][
        "closure_detail_rows"
    ]:
        _fail("local-product-code closure detail rows do not contain seed rows")
    if row["counters"]["lexical_seed_event_memberships"] > row["counters"][
        "closure_event_memberships"
    ]:
        _fail("local-product-code closure events do not contain seed events")


def _coarse(mask: int) -> int:
    return (1 if mask & 1 else 0) + (2 if mask & 6 else 0) + (4 if mask & 24 else 0)


def _expected_review(mask: int, valid_mask: int) -> str:
    if valid_mask == 0:
        return "identity_unresolved_only"
    kcl, broader, other, active, unresolved = (
        bool(mask & bit) for bit in (1, 2, 4, 8, 16)
    )
    if active and (kcl or broader or other):
        return "mixed_repletion_and_nonrepletion_hints"
    if sum((kcl, broader, other, unresolved)) > 1:
        return "mixed_repletion_or_unresolved_hints"
    if kcl:
        return "focal_kcl_repletion_hint"
    if broader:
        return "broader_phosphate_or_acetate_repletion_hint"
    if active:
        return "non_repletion_active_drug_hint"
    if other:
        return "other_potassium_salt_review"
    return "unresolved_name_or_local_code_review"


def _validate_event_row(row: dict[str, Any]) -> None:
    dimensions = row["dimensions"]
    if set(dimensions) != EVENT_DIMENSIONS:
        _fail("event_evidence_mask has an unexpected dimension schema")
    for key in (
        "raw_source_mask", "identity_valid_source_mask", "strict_poe_source_mask",
        "coarse_raw_source_mask", "coarse_identity_valid_source_mask",
        "coarse_strict_poe_source_mask", "valid_review_family_mask",
    ):
        if type(dimensions[key]) is not int:
            _fail(f"event_evidence_mask.{key} must be an integer, not boolean")
    raw = dimensions["raw_source_mask"]
    valid = dimensions["identity_valid_source_mask"]
    strict = dimensions["strict_poe_source_mask"]
    family = dimensions["valid_review_family_mask"]
    if not 1 <= raw <= 31 or not 0 <= valid <= 31 or not 0 <= strict <= 31:
        _fail("event source masks are outside their allowed ranges")
    if not 0 <= family <= 31:
        _fail("event valid_review_family_mask is outside its allowed range")
    for key in ("coarse_raw_source_mask", "coarse_identity_valid_source_mask",
                "coarse_strict_poe_source_mask"):
        if not 0 <= dimensions[key] <= 7:
            _fail(f"{key} is outside its allowed range")
    if (valid & ~raw or strict & ~valid or (strict & 7) != (valid & 7)
            or (raw & 1) != (valid & 1)):
        _fail("event valid/strict source masks violate subset rules")
    if bool(valid) != bool(family):
        _fail("event valid-source and review-family masks must be zero together")
    if (dimensions["coarse_raw_source_mask"] != _coarse(raw)
            or dimensions["coarse_identity_valid_source_mask"] != _coarse(valid)
            or dimensions["coarse_strict_poe_source_mask"] != _coarse(strict)):
        _fail("event coarse masks do not derive from fine masks")
    if (not isinstance(dimensions["head_name_pattern"], str)
            or dimensions["head_name_pattern"] not in HEAD_PATTERNS):
        _fail("event head_name_pattern is invalid")
    if (not isinstance(dimensions["recovery_pattern"], str)
            or dimensions["recovery_pattern"] not in RECOVERY_PATTERNS):
        _fail("event recovery_pattern is invalid")
    expected_recovery = (
        "direct_head_evidence_present" if raw & 1
        else "recovered_without_direct_head_evidence" if valid
        else "linked_evidence_identity_unresolved"
    )
    if dimensions["recovery_pattern"] != expected_recovery:
        _fail("event recovery_pattern disagrees with source masks")
    if raw & 1 and dimensions["head_name_pattern"] != "declared_lexical_head_name":
        _fail("direct head evidence requires declared_lexical_head_name")
    if (not isinstance(dimensions["review_pattern"], str)
            or dimensions["review_pattern"] not in REVIEW_PATTERNS):
        _fail("event review_pattern is invalid")
    if dimensions["review_pattern"] != _expected_review(family, valid):
        _fail("event review_pattern disagrees with valid review-family mask")
    _check_schema(row["counters"], ints=EVENT_INTS, bools=EVENT_BOOLS,
                  label="event_evidence_mask counters")
    counters = row["counters"]
    if counters["emar_heads"] != row["records"]:
        _fail("event_evidence_mask emar_heads must equal records")
    for key in EVENT_INTS:
        if counters[key] > row["records"]:
            _fail(f"event_evidence_mask.{key} exceeds records")
    bit_counters = {
        "head_raw_heads": (raw, 1), "detail_text_raw_heads": (raw, 2),
        "detail_code_raw_heads": (raw, 4), "pharmacy_raw_heads": (raw, 8),
        "prescription_raw_heads": (raw, 16),
        "detail_text_identity_valid_heads": (valid, 2),
        "detail_code_identity_valid_heads": (valid, 4),
        "pharmacy_identity_valid_heads": (valid, 8),
        "prescription_identity_valid_heads": (valid, 16),
        "pharmacy_strict_poe_valid_heads": (strict, 8),
        "prescription_strict_poe_valid_heads": (strict, 16),
    }
    for key, (mask, bit) in bit_counters.items():
        if counters[key] != (row["records"] if mask & bit else 0):
            _fail(f"event_evidence_mask.{key} disagrees with its mask bit")
    if sum(counters[key] for key in STATUS_COUNTERS) != row["records"]:
        _fail("event status counters do not partition records")


def _validate_recovered_row(row: dict[str, Any]) -> None:
    dimensions = row["dimensions"]
    if set(dimensions) != RECOVERED_DIMENSIONS:
        _fail("recovered_head_vocabulary has an unexpected dimension schema")
    _validate_controlled_name(dimensions["raw_head_medication"], "raw_head_medication")
    _validate_controlled_name(
        dimensions["normalized_head_medication"], "normalized_head_medication"
    )
    expected_normalized = (
        re.sub(r"\s+", " ", dimensions["raw_head_medication"].strip()).lower()
        if isinstance(dimensions["raw_head_medication"], str) else None
    )
    if dimensions["normalized_head_medication"] != expected_normalized:
        _fail("recovered_head_vocabulary normalized name is inconsistent")
    expected_pattern = (
        "missing_head_name" if dimensions["raw_head_medication"] is None
        else "blank_head_name"
        if not dimensions["raw_head_medication"].strip()
        else "nonlexical_head_name"
    )
    if dimensions["head_name_pattern"] != expected_pattern:
        _fail("recovered_head_vocabulary head-name pattern disagrees with raw name")
    if (not isinstance(dimensions["head_name_pattern"], str)
            or dimensions["head_name_pattern"]
            not in HEAD_PATTERNS - {"declared_lexical_head_name"}):
        _fail("recovered_head_vocabulary has an invalid head_name_pattern")
    _check_schema(row["counters"], ints=RECOVERED_INTS, bools=RECOVERED_BOOLS,
                  label="recovered_head_vocabulary counters")
    counters = row["counters"]
    if counters["emar_heads"] != row["records"]:
        _fail("recovered_head_vocabulary emar_heads must equal records")
    for key in RECOVERED_INTS:
        if counters[key] > row["records"]:
            _fail(f"recovered_head_vocabulary.{key} exceeds records")
    if sum(counters[key] for key in (
        "focal_kcl_review_heads", "broader_phosphate_or_acetate_review_heads",
        "non_repletion_active_review_heads", "mixed_or_unresolved_review_heads",
    )) != row["records"]:
        _fail("recovered-head review counters do not partition records")


def _validate_conservation_row(row: dict[str, Any]) -> None:
    _empty_dimensions(row)
    _check_schema(row["counters"], ints=CONSERVATION_INTS, bools=CONSERVATION_BOOLS,
                  label="event_conservation counters")
    counters = row["counters"]
    if counters["candidate_emar_heads"] != row["records"]:
        _fail("event_conservation candidate_emar_heads must equal records")
    if counters["query199_prior_real_audit_reference_heads"] != KNOWN_QUERY199_HEADS:
        _fail("event_conservation query-199 reference is not 559191")
    for key in CONSERVATION_INTS - CONSERVATION_CONSTANT_INTS:
        if counters[key] > row["records"]:
            _fail(f"event_conservation.{key} exceeds records")
    for source in ("pharmacy", "prescription"):
        total = counters[f"{source}_name_evidence_heads"]
        via_head = counters[f"{source}_name_evidence_via_head_key"]
        via_detail = counters[f"{source}_name_evidence_via_detail_key"]
        if not max(via_head, via_detail) <= total <= via_head + via_detail:
            _fail(f"event_conservation {source} head/detail-key union bounds fail")


def _validate_guard_row(
    row: dict[str, Any], expected: Mapping[str, bool | str] = BUCKET_GUARD_VALUES,
) -> None:
    _empty_dimensions(row)
    _validate_exact_values(
        row["counters"], expected, "scope_guards counters"
    )


def _validate_admission_diagnostics(
    rows: list[dict[str, Any]], metadata: dict[str, Any],
    *, bucket_index: int | None = None, bucket_count: int | None = None,
) -> None:
    """Validate the aggregate admission-link partition without exposing IDs."""
    origin = metadata["_origin"]
    summary = _single(rows, "admission_link_status", origin)
    expected_summary_dimensions = (
        {} if bucket_index is None else {
            "bucket_index": bucket_index,
            "bucket_count": bucket_count,
        }
    )
    if summary["dimensions"] != expected_summary_dimensions:
        _fail(f"{origin} admission_link_status dimensions are invalid")
    _check_schema(
        summary["counters"], ints=ADMISSION_SUMMARY_INTS,
        bools=ADMISSION_SUMMARY_BOOLS,
        label=f"{origin} admission_link_status counters",
    )
    candidate = metadata["records"]
    counters = summary["counters"]
    if summary["records"] != candidate or counters["candidate_emar_heads"] != candidate:
        _fail(f"{origin} admission-link summary candidate totals disagree")
    for key in {"subjects", "admissions"} | ADMISSION_STATUS_COUNTERS | ADMISSION_ANOMALY_COUNTERS:
        if counters[key] > candidate:
            _fail(f"{origin} admission-link summary {key} exceeds candidates")
    if counters["nonexact_admission_link_hadm_ids_within_partition"] > counters[
        "nonexact_admission_link_heads"
    ]:
        _fail(f"{origin} nonexact admission hadm count exceeds heads")
    if sum(counters[key] for key in ADMISSION_STATUS_COUNTERS) != candidate:
        _fail(f"{origin} admission-link statuses do not partition candidates")
    if counters["nonexact_admission_link_heads"] != candidate - counters[
        "admission_exact_match_heads"
    ]:
        _fail(f"{origin} nonexact admission heads disagree with status partition")
    if counters["nonexact_admission_link_subjects"] > counters["subjects"]:
        _fail(f"{origin} nonexact admission subjects exceed all subjects")
    if counters["nonexact_admission_link_pairs"] > counters["admissions"]:
        _fail(f"{origin} nonexact admission pairs exceed all admission pairs")

    control = metadata["counters"]
    compared = {
        "candidate_emar_heads", "subjects", "admissions",
        *ADMISSION_STATUS_COUNTERS, *ADMISSION_ANOMALY_COUNTERS,
    }
    for key in compared:
        if counters[key] != control[key]:
            _fail(f"{origin} admission-link summary disagrees with metadata.{key}")
    if control["null_subject_candidate_heads"] != (
        counters["admission_missing_subject_and_hadm_heads"]
        + counters["admission_missing_subject_id_heads"]
    ):
        _fail(f"{origin} null-subject count disagrees with admission statuses")

    evidence = [row for row in rows if row["section"] == "admission_link_evidence"]
    status_totals = {status: 0 for status in ADMISSION_LINK_STATUSES}
    for row in evidence:
        expected_dimension_keys = {
            "admission_link_status", "recovery_pattern", "coarse_raw_source_mask",
        }
        if bucket_index is not None:
            expected_dimension_keys |= {"bucket_index", "bucket_count"}
        dimensions = row["dimensions"]
        if set(dimensions) != expected_dimension_keys:
            _fail(f"{origin} admission_link_evidence dimensions are invalid")
        if bucket_index is not None and (
            dimensions["bucket_index"] != bucket_index
            or dimensions["bucket_count"] != bucket_count
        ):
            _fail(f"{origin} admission-link evidence bucket dimensions are invalid")
        status = dimensions["admission_link_status"]
        if status not in ADMISSION_LINK_STATUSES:
            _fail(f"{origin} admission-link evidence status is invalid")
        if dimensions["recovery_pattern"] not in RECOVERY_PATTERNS:
            _fail(f"{origin} admission-link evidence recovery pattern is invalid")
        coarse = dimensions["coarse_raw_source_mask"]
        if type(coarse) is not int or not 1 <= coarse <= 7:
            _fail(f"{origin} admission-link evidence coarse mask is invalid")
        _check_schema(
            row["counters"], ints=ADMISSION_EVIDENCE_INTS,
            bools=ADMISSION_EVIDENCE_BOOLS,
            label=f"{origin} admission_link_evidence counters",
        )
        if row["records"] != row["counters"]["candidate_emar_heads"]:
            _fail(f"{origin} admission-link evidence records disagree with counters")
        status_totals[status] += row["records"]
    if sum(status_totals.values()) != candidate:
        _fail(f"{origin} admission-link evidence does not partition candidates")
    for status, key in ADMISSION_STATUS_FIELD.items():
        if status_totals[status] != counters[key]:
            _fail(f"{origin} admission-link evidence disagrees with {key}")


def _validate_exact_values(
    actual: Mapping[str, Any], expected: Mapping[str, Any], label: str,
) -> None:
    if set(actual) != set(expected):
        _fail(f"{label} has an unexpected key schema")
    for key, expected_value in expected.items():
        value = actual[key]
        if type(value) is not type(expected_value) or value != expected_value:
            _fail(f"{label}.{key} must be exactly {expected_value!r}")


def _validate_recovered_against_masks(
    recovered_rows: list[dict[str, Any]], mask_rows: list[dict[str, Any]], label: str,
) -> None:
    keys = {
        "emar_heads", "administered_exact_heads",
        "detail_text_identity_valid_heads", "detail_code_identity_valid_heads",
        "pharmacy_identity_valid_heads", "prescription_identity_valid_heads",
        "focal_kcl_review_heads", "broader_phosphate_or_acetate_review_heads",
        "non_repletion_active_review_heads", "mixed_or_unresolved_review_heads",
    }
    actual = {
        key: sum(row["counters"][key] for row in recovered_rows) for key in keys
    }
    expected = {key: 0 for key in keys}
    for row in mask_rows:
        if row["dimensions"]["raw_source_mask"] & 1:
            continue
        records = row["records"]
        expected["emar_heads"] += records
        for key in (
            "administered_exact_heads", "detail_text_identity_valid_heads",
            "detail_code_identity_valid_heads", "pharmacy_identity_valid_heads",
            "prescription_identity_valid_heads",
        ):
            expected[key] += row["counters"][key]
        review = row["dimensions"]["review_pattern"]
        review_key = {
            "focal_kcl_repletion_hint": "focal_kcl_review_heads",
            "broader_phosphate_or_acetate_repletion_hint":
                "broader_phosphate_or_acetate_review_heads",
            "non_repletion_active_drug_hint": "non_repletion_active_review_heads",
        }.get(review, "mixed_or_unresolved_review_heads")
        expected[review_key] += records
    for key in keys:
        if actual[key] != expected[key]:
            _fail(f"{label} recovered {key} disagrees with non-direct event masks")


def _validate_one_bucket_conservation(
    rows: list[dict[str, Any]], metadata: dict[str, Any],
    conservation: dict[str, Any], guards: dict[str, Any],
) -> None:
    candidate = metadata["records"]
    mask_rows = [row for row in rows if row["section"] == "event_evidence_mask"]
    if sum(row["records"] for row in mask_rows) != candidate:
        _fail(f"{metadata['_origin']} event-mask rows do not partition candidates")
    counters = conservation["counters"]
    if (conservation["records"] != candidate
            or guards["records"] != candidate
            or counters["candidate_emar_heads"] != candidate):
        _fail(f"{metadata['_origin']} control-section candidate totals disagree")
    control = metadata["counters"]
    if (counters["subjects"] != control["subjects"]
            or counters["admissions"] != control["admissions"]
            or counters["query199_head_scope_distinct_heads"]
            != control["query199_head_scope_distinct_heads"]):
        _fail(f"{metadata['_origin']} conservation disagrees with bucket metadata")

    marginals = {
        "direct_head_evidence_heads": 0,
        "heads_new_beyond_direct_name": 0,
        "detail_text_evidence_heads": 0,
        "detail_code_evidence_heads": 0,
        "pharmacy_name_evidence_heads": 0,
        "prescription_name_evidence_heads": 0,
        "pharmacy_strict_poe_valid_heads": 0,
        "prescription_strict_poe_valid_heads": 0,
        "identity_unresolved_only_heads": 0,
        "missing_head_name_recovered_by_valid_nondirect_evidence": 0,
        "nonlexical_head_name_recovered_by_valid_nondirect_evidence": 0,
    }
    for row in mask_rows:
        dimensions, records = row["dimensions"], row["records"]
        raw = dimensions["raw_source_mask"]
        valid = dimensions["identity_valid_source_mask"]
        strict = dimensions["strict_poe_source_mask"]
        marginals["direct_head_evidence_heads"] += records if raw & 1 else 0
        marginals["heads_new_beyond_direct_name"] += records if not raw & 1 else 0
        marginals["detail_text_evidence_heads"] += records if raw & 2 else 0
        marginals["detail_code_evidence_heads"] += records if raw & 4 else 0
        marginals["pharmacy_name_evidence_heads"] += records if raw & 8 else 0
        marginals["prescription_name_evidence_heads"] += records if raw & 16 else 0
        marginals["pharmacy_strict_poe_valid_heads"] += records if strict & 8 else 0
        marginals["prescription_strict_poe_valid_heads"] += records if strict & 16 else 0
        marginals["identity_unresolved_only_heads"] += records if valid == 0 else 0
        if (not raw & 1 and valid
                and dimensions["head_name_pattern"] == "missing_head_name"):
            marginals["missing_head_name_recovered_by_valid_nondirect_evidence"] += records
        if (not raw & 1 and valid
                and dimensions["head_name_pattern"] == "nonlexical_head_name"):
            marginals[
                "nonlexical_head_name_recovered_by_valid_nondirect_evidence"
            ] += records
    for key, value in marginals.items():
        if counters[key] != value:
            _fail(f"{metadata['_origin']} conservation.{key} disagrees with masks")
    if counters["direct_head_evidence_heads"] + counters[
        "heads_new_beyond_direct_name"
    ] != candidate:
        _fail(f"{metadata['_origin']} direct/recovered heads do not partition candidates")
    recovered_rows = [
        row for row in rows if row["section"] == "recovered_head_vocabulary"
    ]
    if sum(row["records"] for row in recovered_rows) != counters[
        "heads_new_beyond_direct_name"
    ]:
        _fail(f"{metadata['_origin']} recovered vocabulary does not conserve heads")
    _validate_recovered_against_masks(recovered_rows, mask_rows, metadata["_origin"])


def _merge_additive_rows(
    bucket_rows: list[list[dict[str, Any]]], section: str, int_keys: set[str],
    constant_int_keys: set[str] = frozenset(),
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for rows in bucket_rows:
        for row in rows:
            if row["section"] != section:
                continue
            key = _canonical(row["dimensions"])
            if key not in merged:
                merged[key] = {
                    "section": section,
                    "dimensions": dict(row["dimensions"]),
                    "records": 0,
                    "counters": {},
                }
            target = merged[key]
            target["records"] += row["records"]
            for counter, value in row["counters"].items():
                if counter in int_keys - constant_int_keys:
                    target["counters"][counter] = target["counters"].get(counter, 0) + value
                elif counter in target["counters"] and target["counters"][counter] != value:
                    _fail(f"{section}.{counter} is not identical across buckets")
                else:
                    target["counters"][counter] = value
    return list(merged.values())


def _validate_one_global_fragment(
    origin: str, rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    (
        metadata_section,
        ints,
        bools,
        strings,
        allowed_other,
    ) = GLOBAL_FRAGMENT_SPECIFICATIONS[origin]
    allowed = {metadata_section} | allowed_other
    if any(row["section"] not in allowed for row in rows):
        _fail(f"{origin} emitted a section outside {sorted(allowed)!r}")
    metadata_row = _single(rows, metadata_section, origin)
    _validate_metadata_row(metadata_row, ints, bools, strings)
    vocabulary: list[dict[str, Any]] = []
    code_shapes: list[dict[str, Any]] = []
    for row in rows:
        if row["section"] == "source_vocabulary":
            _validate_vocabulary(row, origin)
            vocabulary.append(row)
        elif row["section"] == "local_product_code_shape":
            _validate_code_shape(row)
            code_shapes.append(row)
    return metadata_row, vocabulary, code_shapes


def _validate_global_fragments(
    fragments: dict[str, list[dict[str, Any]]]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    metadata: dict[str, dict[str, Any]] = {}
    vocabulary: list[dict[str, Any]] = []
    code_shapes: list[dict[str, Any]] = []
    for origin in GLOBAL_FRAGMENT_SPECIFICATIONS:
        metadata_row, fragment_vocabulary, fragment_code_shapes = (
            _validate_one_global_fragment(origin, fragments[origin])
        )
        metadata[origin] = metadata_row
        vocabulary.extend(fragment_vocabulary)
        code_shapes.extend(fragment_code_shapes)

    for section, rows in (("source_vocabulary", vocabulary),
                          ("local_product_code_shape", code_shapes)):
        seen: set[str] = set()
        for row in rows:
            key = _canonical(row["dimensions"])
            if key in seen:
                _fail(f"global fragments duplicate a {section} dimension row")
            seen.add(key)
    semantic_vocabulary_keys: set[tuple[Any, Any, Any]] = set()
    for row in vocabulary:
        dimensions = row["dimensions"]
        semantic_key = (
            dimensions["source_type"],
            dimensions["evidence_path"],
            dimensions["raw_name"],
        )
        if semantic_key in semantic_vocabulary_keys:
            _fail("global fragments duplicate a source_vocabulary semantic key")
        semantic_vocabulary_keys.add(semantic_key)
    return metadata, vocabulary, code_shapes


def _validate_one_bucket_fragment(
    origin: str,
    rows: list[dict[str, Any]],
    index: int,
    bucket_count: int,
) -> dict[str, Any]:
    allowed = {
        "closure_bucket_metadata", "event_evidence_mask",
        "recovered_head_vocabulary", "event_conservation", "scope_guards",
        "admission_link_status", "admission_link_evidence",
    }
    if any(row["section"] not in allowed for row in rows):
        _fail(f"{origin} emitted an unexpected section")
    metadata = _single(rows, "closure_bucket_metadata", origin)
    conservation = _single(rows, "event_conservation", origin)
    guards = _single(rows, "scope_guards", origin)
    if metadata["dimensions"] != {
        "bucket_index": index,
        "bucket_count": bucket_count,
    }:
        _fail(f"{origin} metadata dimensions do not match its origin")
    _check_schema(
        metadata["counters"], ints=BUCKET_METADATA_INTS,
        bools=BUCKET_METADATA_BOOLS, strings=BUCKET_METADATA_STRINGS,
        label=f"{origin} closure_bucket_metadata counters",
    )
    counters = metadata["counters"]
    if (counters["merge_protocol_version"] != 1
            or counters["bucket_index"] != index
            or counters["bucket_count"] != bucket_count
            or counters["null_subject_bucket"] != 0):
        _fail(f"{origin} metadata control integers are invalid")
    if metadata["records"] != counters["candidate_emar_heads"]:
        _fail(f"{origin} records do not equal candidate_emar_heads")
    if counters["null_subject_candidate_heads"] > metadata["records"]:
        _fail(f"{origin}.null_subject_candidate_heads exceeds candidates")
    if index != 0 and counters["null_subject_candidate_heads"] != 0:
        _fail(f"{origin} cannot contain null-subject heads outside bucket zero")
    for key in ("subjects", "admissions", "query199_head_scope_distinct_heads"):
        if counters[key] > metadata["records"]:
            _fail(f"{origin}.{key} exceeds candidate_emar_heads")
    # Null head subjects are intentionally assigned to bucket zero by the SQL
    # contract and are reported, not treated as a merge violation.
    for key in (
        "bucket_assignment_violations",
        "detail_subject_partition_identity_violations",
        "order_detail_subject_partition_identity_violations",
        "duplicate_candidate_emar_heads",
        "detail_code_dictionary_miss_names",
    ):
        if counters[key] != 0:
            _fail(f"{origin}.{key} must be zero before merge")

    _validate_conservation_row(conservation)
    _validate_guard_row(guards)
    _validate_admission_diagnostics(
        rows, metadata, bucket_index=index, bucket_count=bucket_count
    )
    for row in rows:
        if row["section"] == "event_evidence_mask":
            _validate_event_row(row)
        elif row["section"] == "recovered_head_vocabulary":
            _validate_recovered_row(row)
    _validate_one_bucket_conservation(rows, metadata, conservation, guards)
    return counters


def _validate_bucket_fragments(
    fragments: dict[str, list[dict[str, Any]]], bucket_count: int,
) -> tuple[list[list[dict[str, Any]]], dict[str, Any], dict[str, Any]]:
    bucket_rows: list[list[dict[str, Any]]] = []
    controls: list[dict[str, Any]] = []
    for index in range(bucket_count):
        origin = f"event_bucket_{index}"
        rows = fragments[origin]
        counters = _validate_one_bucket_fragment(
            origin, rows, index, bucket_count
        )
        bucket_rows.append(rows)
        controls.append(counters)

    identical_keys = (
        DISCOVERY_COUNTERS
        | {
            "selected_pharmacy_keys_global",
            "selected_pharmacy_full_component_rows_global",
            "selected_prescription_keys_global",
            "selected_prescription_full_component_rows_global",
            "identity_consistent_lexical_detail_product_rows",
            "identity_consistent_lexical_detail_events", "seed_local_product_codes",
            "supplied_detail_code_dictionary_names",
        }
    )
    common = {key: controls[0][key] for key in identical_keys}
    for index, control in enumerate(controls[1:], start=1):
        for key, value in common.items():
            if control[key] != value:
                _fail(f"event_bucket_{index}.{key} does not match other buckets")

    totals = {
        key: sum(control[key] for control in controls)
        for key in (
            "candidate_emar_heads", "subjects", "admissions",
            "query199_head_scope_distinct_heads", "bucket_assignment_violations",
            "detail_subject_partition_groups_checked",
            "detail_subject_partition_identity_violations",
            "order_detail_subject_partition_groups_checked",
            "order_detail_subject_partition_identity_violations",
            "null_subject_candidate_heads", *ADMISSION_STATUS_COUNTERS,
            *ADMISSION_ANOMALY_COUNTERS,
            "duplicate_candidate_emar_heads",
        )
    }
    totals.update({
        "selected_detail_rows": sum(
            control["selected_detail_rows_in_bucket"] for control in controls
        ),
        "detail_text_rows": sum(
            control["detail_text_rows_in_bucket"] for control in controls
        ),
        "detail_code_rows": sum(
            control["detail_code_rows_in_bucket"] for control in controls
        ),
        "order_detail_link_rows": sum(
            control["order_detail_link_rows_in_bucket"] for control in controls
        ),
        "detail_code_dictionary_miss_names": sum(
            control["detail_code_dictionary_miss_names"] for control in controls
        ),
    })
    if totals["query199_head_scope_distinct_heads"] != KNOWN_QUERY199_HEADS:
        _fail("bucket query-199 counts do not sum to 559191")
    summary = {
        "merge_protocol_version": 1,
        "execution_mode": "subject_buckets",
        "bucket_count": bucket_count,
        "candidate_emar_heads": totals["candidate_emar_heads"],
        "query199_head_scope_distinct_heads": totals["query199_head_scope_distinct_heads"],
        "bucket_assignment_violations": totals["bucket_assignment_violations"],
        "detail_subject_partition_groups_checked":
            totals["detail_subject_partition_groups_checked"],
        "detail_subject_partition_identity_violations":
            totals["detail_subject_partition_identity_violations"],
        "order_detail_subject_partition_groups_checked":
            totals["order_detail_subject_partition_groups_checked"],
        "order_detail_subject_partition_identity_violations":
            totals["order_detail_subject_partition_identity_violations"],
        "null_subject_candidate_heads": totals["null_subject_candidate_heads"],
        **{key: totals[key] for key in ADMISSION_STATUS_COUNTERS},
        **{key: totals[key] for key in ADMISSION_ANOMALY_COUNTERS},
        "duplicate_candidate_emar_heads": totals["duplicate_candidate_emar_heads"],
        "selected_detail_rows": totals["selected_detail_rows"],
        "detail_text_rows": totals["detail_text_rows"],
        "detail_code_rows": totals["detail_code_rows"],
        "order_detail_link_rows": totals["order_detail_link_rows"],
        "detail_code_dictionary_names":
            common["supplied_detail_code_dictionary_names"],
        "emar_id_primary_key_confirmed": all(
            control["emar_id_primary_key_confirmed"] for control in controls
        ),
        "pharmacy_id_primary_key_confirmed": all(
            control["pharmacy_id_primary_key_confirmed"] for control in controls
        ),
        "pharmacy_id_integer_types_confirmed": all(
            control["pharmacy_id_integer_types_confirmed"] for control in controls
        ),
        "admissions_hadm_id_primary_key_confirmed": all(
            control["admissions_hadm_id_primary_key_confirmed"] for control in controls
        ),
    }
    return bucket_rows, {**common, **totals}, summary


def _validate_unbucketed_fragment(
    fragments: dict[str, list[dict[str, Any]]],
) -> tuple[list[list[dict[str, Any]]], dict[str, Any], dict[str, Any]]:
    origin = "unbucketed_event"
    rows = fragments[origin]
    allowed = {
        "closure_event_metadata", "event_evidence_mask",
        "recovered_head_vocabulary", "event_conservation", "scope_guards",
        "admission_link_status", "admission_link_evidence",
    }
    if any(row["section"] not in allowed for row in rows):
        _fail(f"{origin} emitted an unexpected section")
    metadata = _single(rows, "closure_event_metadata", origin)
    conservation = _single(rows, "event_conservation", origin)
    guards = _single(rows, "scope_guards", origin)
    _validate_metadata_row(metadata, EVENT_METADATA_INTS, EVENT_METADATA_BOOLS)
    counters = metadata["counters"]
    if metadata["records"] != counters["candidate_emar_heads"]:
        _fail("unbucketed event records do not equal candidate_emar_heads")
    if counters["query199_head_scope_distinct_heads"] != KNOWN_QUERY199_HEADS:
        _fail("unbucketed event query-199 count is not 559191")
    if counters["query199_head_scope_distinct_heads"] > metadata["records"]:
        _fail("unbucketed event query-199 count exceeds candidates")
    if counters["duplicate_candidate_emar_heads"] != 0:
        _fail("unbucketed event duplicate_candidate_emar_heads must be zero")
    for key in (
        "detail_text_dictionary_miss_rows", "detail_code_dictionary_miss_rows",
    ):
        if counters[key] != 0:
            _fail(f"unbucketed event {key} must be zero")

    _validate_conservation_row(conservation)
    _validate_guard_row(guards, PUBLIC_GUARD_VALUES)
    _validate_admission_diagnostics(rows, metadata)
    for row in rows:
        if row["section"] == "event_evidence_mask":
            _validate_event_row(row)
        elif row["section"] == "recovered_head_vocabulary":
            _validate_recovered_row(row)
    synthetic_control = {
        **metadata,
        "counters": {
            **counters,
            "subjects": counters["subjects"],
            "admissions": counters["admissions"],
        },
    }
    _validate_one_bucket_conservation(
        rows, synthetic_control, conservation, guards
    )
    totals = {
        "candidate_emar_heads": counters["candidate_emar_heads"],
        "subjects": counters["subjects"],
        "admissions": counters["admissions"],
        "null_subject_candidate_heads": counters["null_subject_candidate_heads"],
        **{key: counters[key] for key in ADMISSION_STATUS_COUNTERS},
        **{key: counters[key] for key in ADMISSION_ANOMALY_COUNTERS},
        "query199_head_scope_distinct_heads":
            counters["query199_head_scope_distinct_heads"],
        "duplicate_candidate_emar_heads": counters["duplicate_candidate_emar_heads"],
        "selected_detail_rows": counters["selected_detail_rows"],
        "detail_text_rows": counters["detail_text_rows"],
        "detail_code_rows": counters["detail_code_rows"],
        "order_detail_link_rows": counters["order_detail_link_rows"],
        "supplied_detail_code_dictionary_names":
            counters["supplied_detail_code_dictionary_names"],
    }
    summary = {
        "merge_protocol_version": 1,
        "execution_mode": "unbucketed_event",
        "candidate_emar_heads": counters["candidate_emar_heads"],
        "query199_head_scope_distinct_heads":
            counters["query199_head_scope_distinct_heads"],
        "null_subject_candidate_heads": counters["null_subject_candidate_heads"],
        **{key: counters[key] for key in ADMISSION_STATUS_COUNTERS},
        **{key: counters[key] for key in ADMISSION_ANOMALY_COUNTERS},
        "duplicate_candidate_emar_heads": counters["duplicate_candidate_emar_heads"],
        "selected_detail_rows": counters["selected_detail_rows"],
        "detail_text_rows": counters["detail_text_rows"],
        "detail_code_rows": counters["detail_code_rows"],
        "order_detail_link_rows": counters["order_detail_link_rows"],
        "detail_code_dictionary_names":
            counters["supplied_detail_code_dictionary_names"],
        "emar_id_primary_key_confirmed": counters["emar_id_primary_key_confirmed"],
        "pharmacy_id_primary_key_confirmed":
            counters["pharmacy_id_primary_key_confirmed"],
        "pharmacy_id_integer_types_confirmed":
            counters["pharmacy_id_integer_types_confirmed"],
        "admissions_hadm_id_primary_key_confirmed":
            counters["admissions_hadm_id_primary_key_confirmed"],
        "event_aggregation_unbucketed": counters["event_aggregation_unbucketed"],
    }
    return [rows], totals, summary


def validate_source_closure_fragment(
    origin: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    execution_mode: str,
    bucket_count: int | None,
) -> None:
    """Validate one query-200 fragment before the next SQL stage executes.

    This performs the same parsing and within-fragment validation used by the
    final merge.  It intentionally does not attempt cross-global comparisons,
    cross-bucket constants, aggregate conservation across buckets, or output
    construction; the final merge remains authoritative for those checks.
    """
    with _validation_phase(MergeValidationErrorCode.INPUT_CONTRACT_REJECTED):
        mode, resolved_bucket_count = _resolve_execution_mode(
            execution_mode, bucket_count
        )
        if origin in GLOBAL_FRAGMENT_SPECIFICATIONS:
            fragment_kind = "global"
            bucket_index = None
        elif origin == "unbucketed_event" and mode == "unbucketed_event":
            fragment_kind = "event"
            bucket_index = None
        else:
            match = BUCKET_ORIGIN.fullmatch(origin) if isinstance(origin, str) else None
            if match is None or mode != "subject_buckets":
                _fail("fragment origin is not valid for the execution mode")
            assert resolved_bucket_count is not None
            bucket_index = int(match.group(1))
            if bucket_index >= resolved_bucket_count:
                _fail("event bucket origin is outside the configured bucket count")
            fragment_kind = "event_bucket"
        _, parsed_rows = _normalise_one_fragment(origin, rows)

    if fragment_kind == "global":
        with _validation_phase(MergeValidationErrorCode.GLOBAL_CONTRACT_REJECTED):
            _validate_one_global_fragment(origin, parsed_rows)
    elif fragment_kind == "event_bucket":
        assert bucket_index is not None
        assert resolved_bucket_count is not None
        with _validation_phase(MergeValidationErrorCode.EVENT_CONTRACT_REJECTED):
            _validate_one_bucket_fragment(
                origin, parsed_rows, bucket_index, resolved_bucket_count
            )
    else:
        with _validation_phase(MergeValidationErrorCode.EVENT_CONTRACT_REJECTED):
            _validate_unbucketed_fragment({origin: parsed_rows})


def _require_equal(values: Iterable[tuple[str, Any]], label: str) -> Any:
    items = list(values)
    first_label, first = items[0]
    for item_label, value in items[1:]:
        if value != first:
            _fail(f"{label} differs between {first_label} and {item_label}")
    return first


def _assemble_metadata(
    metadata_rows: dict[str, dict[str, Any]], event_control: dict[str, Any],
    event_scan_count: int, metadata_constants: Mapping[str, Any] | None,
) -> dict[str, Any]:
    head = metadata_rows["global_head"]["counters"]
    detail = metadata_rows["global_detail"]["counters"]
    order = metadata_rows["global_order"]["counters"]

    for key in DISCOVERY_COUNTERS:
        values = [("head", head[key]), ("detail", detail[key]), ("order", order[key])]
        if key in event_control:
            values.append(("event", event_control[key]))
        _require_equal(values, key)
    _require_equal(
        (("head", head["selected_indexed_source_names"]),
         ("detail", detail["selected_indexed_source_names"]),
         ("order", order["selected_indexed_source_names"])),
        "selected_indexed_source_names",
    )
    identity_event_values = [
        ("detail", detail["identity_consistent_lexical_detail_events"]),
        ("order", order["identity_consistent_lexical_detail_events"]),
    ]
    if "identity_consistent_lexical_detail_events" in event_control:
        identity_event_values.append(
            ("event", event_control["identity_consistent_lexical_detail_events"])
        )
    _require_equal(identity_event_values, "identity_consistent_lexical_detail_events")
    for key in (
        "identity_consistent_lexical_detail_product_rows", "seed_local_product_codes",
    ):
        if key in event_control and detail[key] != event_control[key]:
            _fail(f"global detail {key} does not match bucket metadata")
    for global_key, bucket_key in (
        ("selected_pharmacy_keys", "selected_pharmacy_keys_global"),
        ("selected_pharmacy_full_component_rows",
         "selected_pharmacy_full_component_rows_global"),
        ("selected_prescription_keys", "selected_prescription_keys_global"),
        ("selected_prescription_full_component_rows",
         "selected_prescription_full_component_rows_global"),
    ):
        if bucket_key in event_control and order[global_key] != event_control[bucket_key]:
            _fail(f"global order {global_key} does not match bucket metadata")
    if (head["query199_head_scope_distinct_heads"]
            != event_control["query199_head_scope_distinct_heads"]):
        _fail("global-head and bucket query-199 counts differ")
    if head["query199_prior_real_audit_reference_heads"] != KNOWN_QUERY199_HEADS:
        _fail("global-head query-199 reference is not 559191")
    if head["direct_head_evidence_heads"] != metadata_rows["global_head"]["records"]:
        _fail("global-head records do not equal direct_head_evidence_heads")
    if detail["raw_lexical_detail_product_rows"] > metadata_rows["global_detail"]["records"]:
        _fail("raw lexical detail rows exceed selected global detail rows")
    if detail["selected_detail_rows"] != metadata_rows["global_detail"]["records"]:
        _fail("global-detail records do not equal selected_detail_rows")
    if order["order_linked_detail_product_rows"] != metadata_rows["global_order"]["records"]:
        _fail("global-order records do not equal order_linked_detail_product_rows")
    for detail_key in (
        "selected_detail_rows", "detail_text_rows", "detail_code_rows",
    ):
        if detail[detail_key] != event_control[detail_key]:
            _fail(f"global detail {detail_key} does not match event coverage")
    if order["order_linked_detail_product_rows"] != event_control["order_detail_link_rows"]:
        _fail("global order detail links do not match event coverage")
    if (detail["detail_code_dictionary_names"]
            != event_control["supplied_detail_code_dictionary_names"]):
        _fail("global detail-code dictionary does not match event handoff")
    if order["global_order_prescription_lexical_pass_count"] != 1:
        _fail("global-order prescription lexical pass count must be one")
    if order["global_order_prescription_component_pass_count"] != 1:
        _fail("global-order prescription component pass count must be one")

    derived_scans = {
        "names_discovery_prescription_lexical_pass_count": 1,
        "global_order_prescription_lexical_pass_count": 1,
        "global_order_prescription_component_pass_count": 1,
        "event_closure_prescription_lexical_pass_count": event_scan_count,
        "event_closure_prescription_component_pass_count": event_scan_count,
        "total_prescription_lexical_pass_count": event_scan_count + 2,
        "total_prescription_component_pass_count": event_scan_count + 1,
    }
    supplied = {} if metadata_constants is None else dict(metadata_constants)
    if set(supplied) - FINAL_SCAN_COUNTERS:
        _fail("metadata_constants contains unsupported keys")
    for key, value in supplied.items():
        if type(value) is not int or value < 0 or value != derived_scans[key]:
            _fail(f"metadata_constants.{key} does not match the derived scan count")

    final = {
        **{key: head[key] for key in DISCOVERY_COUNTERS},
        "selected_indexed_source_names": head["selected_indexed_source_names"],
        "selected_prescription_drug_names": order["selected_prescription_drug_names"],
        "query199_head_scope_distinct_heads":
            event_control["query199_head_scope_distinct_heads"],
        "query199_prior_real_audit_reference_heads":
            head["query199_prior_real_audit_reference_heads"],
        "query199_reference_requires_real_audit_comparison":
            head["query199_reference_requires_real_audit_comparison"],
        "seed_local_product_codes": detail["seed_local_product_codes"],
        "largest_one_hop_code_detail_rows": detail["largest_one_hop_code_detail_rows"],
        "raw_lexical_detail_product_rows": detail["raw_lexical_detail_product_rows"],
        "identity_consistent_lexical_detail_product_rows":
            detail["identity_consistent_lexical_detail_product_rows"],
        "order_linked_detail_product_rows": order["order_linked_detail_product_rows"],
        "order_detail_link_rows": event_control["order_detail_link_rows"],
        "selected_detail_rows": detail["selected_detail_rows"],
        "detail_text_rows": detail["detail_text_rows"],
        "detail_code_rows": detail["detail_code_rows"],
        "detail_code_dictionary_names": detail["detail_code_dictionary_names"],
        "selected_pharmacy_keys": order["selected_pharmacy_keys"],
        "selected_pharmacy_full_component_rows":
            order["selected_pharmacy_full_component_rows"],
        "selected_prescription_keys": order["selected_prescription_keys"],
        "selected_prescription_full_component_rows":
            order["selected_prescription_full_component_rows"],
        "candidate_emar_heads": event_control["candidate_emar_heads"],
        **{key: event_control[key] for key in ADMISSION_STATUS_COUNTERS},
        **{key: event_control[key] for key in ADMISSION_ANOMALY_COUNTERS},
        "declared_scope_exact": detail["declared_scope_exact"],
        "lexical_scope": detail["lexical_scope"],
        "local_product_code_scope": detail["local_product_code_scope"],
        "product_code_interpretation": detail["product_code_interpretation"],
        "pharmacy_id_integer_types_confirmed":
            order["pharmacy_id_integer_types_confirmed"],
        **derived_scans,
        "raw_identifiers_times_or_patient_text_emitted": False,
    }
    return final


def _postmerge_invariants(
    rows: list[dict[str, Any]], metadata_rows: dict[str, dict[str, Any]],
    bucket_totals: dict[str, Any],
) -> None:
    by_section: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_section.setdefault(row["section"], []).append(row)
    metadata = by_section["closure_metadata"][0]
    conservation = by_section["event_conservation"][0]
    guards = by_section["scope_guards"][0]
    candidates = metadata["records"]
    if not (metadata["counters"]["candidate_emar_heads"] == candidates
            == conservation["records"]
            == conservation["counters"]["candidate_emar_heads"]
            == guards["records"]
            == bucket_totals["candidate_emar_heads"]):
        _fail("post-merge candidate totals do not agree")
    if (conservation["counters"]["subjects"] != bucket_totals["subjects"]
            or conservation["counters"]["admissions"] != bucket_totals["admissions"]):
        _fail("post-merge subject/admission totals do not agree with bucket controls")

    admission_summaries = by_section.get("admission_link_status", [])
    if not admission_summaries:
        _fail("post-merge admission-link summary is missing")
    for key in {
        "candidate_emar_heads", "subjects", "admissions",
        *ADMISSION_STATUS_COUNTERS, *ADMISSION_ANOMALY_COUNTERS,
    }:
        if sum(row["counters"][key] for row in admission_summaries) != bucket_totals[key]:
            _fail(f"post-merge admission-link summary {key} is not additive")
    if sum(row["records"] for row in admission_summaries) != candidates:
        _fail("post-merge admission-link summaries do not partition candidates")
    evidence_status_totals = {status: 0 for status in ADMISSION_LINK_STATUSES}
    for row in by_section.get("admission_link_evidence", []):
        if row["counters"].get("formal_cohort") is not False:
            _fail("post-merge admission-link evidence changed formal_cohort")
        status = row["dimensions"].get("admission_link_status")
        if status not in evidence_status_totals:
            _fail("post-merge admission-link evidence status is invalid")
        evidence_status_totals[status] += row["records"]
    if sum(evidence_status_totals.values()) != candidates:
        _fail("post-merge admission-link evidence does not partition candidates")
    for status, key in ADMISSION_STATUS_FIELD.items():
        if evidence_status_totals[status] != bucket_totals[key]:
            _fail(f"post-merge admission-link evidence disagrees with {key}")
    for location in (metadata["counters"], conservation["counters"]):
        if (location["query199_head_scope_distinct_heads"] != KNOWN_QUERY199_HEADS
                or location["query199_prior_real_audit_reference_heads"]
                != KNOWN_QUERY199_HEADS):
            _fail("post-merge query-199 regression is not 559191")

    marginals = {
        "candidate_emar_heads": 0, "direct_head_evidence_heads": 0,
        "heads_new_beyond_direct_name": 0, "detail_text_evidence_heads": 0,
        "detail_code_evidence_heads": 0, "pharmacy_name_evidence_heads": 0,
        "prescription_name_evidence_heads": 0,
        "pharmacy_strict_poe_valid_heads": 0,
        "prescription_strict_poe_valid_heads": 0,
        "identity_unresolved_only_heads": 0,
        "missing_head_name_recovered_by_valid_nondirect_evidence": 0,
        "nonlexical_head_name_recovered_by_valid_nondirect_evidence": 0,
    }
    for row in by_section.get("event_evidence_mask", []):
        _validate_event_row(row)
        d, count = row["dimensions"], row["records"]
        raw, valid, strict = (
            d["raw_source_mask"], d["identity_valid_source_mask"],
            d["strict_poe_source_mask"],
        )
        marginals["candidate_emar_heads"] += count
        marginals["direct_head_evidence_heads"] += count if raw & 1 else 0
        marginals["heads_new_beyond_direct_name"] += count if not raw & 1 else 0
        marginals["detail_text_evidence_heads"] += count if raw & 2 else 0
        marginals["detail_code_evidence_heads"] += count if raw & 4 else 0
        marginals["pharmacy_name_evidence_heads"] += count if raw & 8 else 0
        marginals["prescription_name_evidence_heads"] += count if raw & 16 else 0
        marginals["pharmacy_strict_poe_valid_heads"] += count if strict & 8 else 0
        marginals["prescription_strict_poe_valid_heads"] += count if strict & 16 else 0
        marginals["identity_unresolved_only_heads"] += count if valid == 0 else 0
        if not raw & 1 and valid and d["head_name_pattern"] == "missing_head_name":
            marginals["missing_head_name_recovered_by_valid_nondirect_evidence"] += count
        if not raw & 1 and valid and d["head_name_pattern"] == "nonlexical_head_name":
            marginals["nonlexical_head_name_recovered_by_valid_nondirect_evidence"] += count
    for key, value in marginals.items():
        if conservation["counters"][key] != value:
            _fail(f"post-merge conservation.{key} disagrees with event masks")
    if (conservation["counters"]["direct_head_evidence_heads"]
            + conservation["counters"]["heads_new_beyond_direct_name"] != candidates):
        _fail("direct and recovered heads do not partition candidates")

    recovered = by_section.get("recovered_head_vocabulary", [])
    for row in recovered:
        _validate_recovered_row(row)
    if sum(row["records"] for row in recovered) != conservation["counters"][
        "heads_new_beyond_direct_name"
    ]:
        _fail("recovered vocabulary does not partition non-direct heads")
    _validate_recovered_against_masks(
        recovered, by_section.get("event_evidence_mask", []), "post-merge"
    )

    vocabulary = by_section.get("source_vocabulary", [])
    head_source_rows = sum(
        row["records"] for row in vocabulary
        if row["dimensions"]["evidence_path"] == "head_text"
    )
    if head_source_rows != conservation["counters"]["direct_head_evidence_heads"]:
        _fail("head vocabulary rows do not equal direct head evidence")
    detail_text_rows = sum(
        row["records"] for row in vocabulary
        if row["dimensions"]["evidence_path"] == "detail_text_seed"
    )
    if detail_text_rows != metadata["counters"]["raw_lexical_detail_product_rows"]:
        _fail("detail text vocabulary rows do not equal raw lexical detail rows")
    code_rows = by_section.get("local_product_code_shape", [])
    if sum(row["records"] for row in code_rows) != metadata["counters"][
        "seed_local_product_codes"
    ]:
        _fail("code-shape groups do not partition seed local product codes")
    if code_rows:
        closure_total = sum(row["counters"]["closure_detail_rows"] for row in code_rows)
        if metadata["counters"]["largest_one_hop_code_detail_rows"] > closure_total:
            _fail("largest one-hop code group exceeds closure detail rows")
        closure_vocabulary_total = sum(
            row["records"] for row in vocabulary
            if row["dimensions"]["evidence_path"] == "detail_local_code_closure"
        )
        if closure_total != closure_vocabulary_total:
            _fail("code shapes do not conserve local-code closure vocabulary rows")
        lexical_seed_rows = sum(
            row["counters"]["lexical_seed_detail_rows"] for row in code_rows
        )
        if lexical_seed_rows > metadata["counters"][
            "identity_consistent_lexical_detail_product_rows"
        ]:
            _fail("coded lexical seed rows exceed identity-consistent lexical rows")
    if metadata["counters"]["identity_consistent_lexical_detail_product_rows"] > (
        metadata["counters"]["raw_lexical_detail_product_rows"]
    ):
        _fail("identity-consistent lexical detail rows exceed raw lexical rows")

    indexed_vocabulary_names = sum(
        1 for row in vocabulary
        if row["dimensions"]["evidence_path"]
        in {"head_text", "detail_text_seed", "pharmacy_name"}
    )
    if indexed_vocabulary_names != metadata["counters"]["selected_indexed_source_names"]:
        _fail("indexed source-name count does not match global vocabulary rows")
    prescription_vocabulary_names = sum(
        1 for row in vocabulary
        if row["dimensions"]["evidence_path"] == "prescription_name"
    )
    if prescription_vocabulary_names != metadata["counters"][
        "selected_prescription_drug_names"
    ]:
        _fail("prescription-name count does not match global vocabulary rows")
    for source in ("pharmacy", "prescription"):
        keys = metadata["counters"][f"selected_{source}_keys"]
        components = metadata["counters"][f"selected_{source}_full_component_rows"]
        if keys > components:
            _fail(f"selected {source} keys exceed full-component rows")
        source_rows = sum(
            row["records"] for row in vocabulary
            if row["dimensions"]["evidence_path"] == f"{source}_name"
        )
        if source_rows > components:
            _fail(f"selected {source} vocabulary rows exceed full-component rows")

    if metadata_rows["global_head"]["counters"]["direct_head_evidence_heads"] != (
        conservation["counters"]["direct_head_evidence_heads"]
    ):
        _fail("global-head count disagrees with merged event conservation")
    if any(guards["counters"][key] is not False for key in FORMAL_FALSE_GUARDS):
        _fail("a formal/policy guard became true")


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "section": row["section"], "dimensions": dict(row["dimensions"]),
        "records": row["records"], "counters": dict(row["counters"]),
    }


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (
        0 if row["section"] == "closure_metadata" else 1,
        row["section"], -row["records"], _canonical(row["dimensions"]),
    ))


def _to_csv(rows: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(EXPECTED_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "section": row["section"],
            "dimensions": _canonical(row["dimensions"]),
            "records": str(row["records"]),
            "counters": _canonical(row["counters"]),
        })
    return output.getvalue()


def merge_source_closure_fragments(
    fragments: Mapping[str, Sequence[Mapping[str, Any]]]
    | Iterable[tuple[str, Sequence[Mapping[str, Any]]]],
    *, bucket_count: int | None = None, execution_mode: str | None = None,
    metadata_constants: Mapping[str, Any] | None = None,
) -> MergeResult:
    """Validate and merge query-200 global and subject-bucket CSV rows.

    Origins always include ``global_head``, ``global_detail``, and
    ``global_order``.  ``subject_buckets`` mode additionally requires
    ``event_bucket_0`` through ``event_bucket_{bucket_count-1}``;
    ``unbucketed_event`` mode requires exactly ``unbucketed_event`` and no
    bucket count.  Every row contains exactly ``section``, ``dimensions``,
    ``records``, and ``counters`` as strings.

    ``metadata_constants`` may contain only the public prescription lexical and
    component pass counters in :data:`FINAL_SCAN_COUNTERS`; supplied values
    must equal the deterministic values derived from the execution mode.
    """
    with _validation_phase(MergeValidationErrorCode.INPUT_CONTRACT_REJECTED):
        mode, resolved_bucket_count = _resolve_execution_mode(
            execution_mode, bucket_count
        )
        parsed = _normalise_fragments(
            fragments, execution_mode=mode, bucket_count=resolved_bucket_count
        )

    with _validation_phase(MergeValidationErrorCode.GLOBAL_CONTRACT_REJECTED):
        metadata_rows, vocabulary, code_shapes = _validate_global_fragments(parsed)

    with _validation_phase(MergeValidationErrorCode.EVENT_CONTRACT_REJECTED):
        if mode == "subject_buckets":
            assert resolved_bucket_count is not None
            event_rows_by_fragment, event_totals, validation_summary = (
                _validate_bucket_fragments(parsed, resolved_bucket_count)
            )
            event_scan_count = resolved_bucket_count
        else:
            event_rows_by_fragment, event_totals, validation_summary = (
                _validate_unbucketed_fragment(parsed)
            )
            event_scan_count = 1

    with _validation_phase(MergeValidationErrorCode.ADDITIVE_CONTRACT_REJECTED):
        event_rows = _merge_additive_rows(
            event_rows_by_fragment, "event_evidence_mask", EVENT_INTS
        )
        recovered_rows = _merge_additive_rows(
            event_rows_by_fragment, "recovered_head_vocabulary", RECOVERED_INTS
        )
        admission_status_rows = _merge_additive_rows(
            event_rows_by_fragment, "admission_link_status",
            ADMISSION_SUMMARY_INTS,
        )
        admission_evidence_rows = _merge_additive_rows(
            event_rows_by_fragment, "admission_link_evidence",
            ADMISSION_EVIDENCE_INTS,
        )
        conservation_rows = _merge_additive_rows(
            event_rows_by_fragment, "event_conservation", CONSERVATION_INTS,
            CONSERVATION_CONSTANT_INTS,
        )
        guard_rows = _merge_additive_rows(
            event_rows_by_fragment, "scope_guards", set()
        )
        if len(conservation_rows) != 1 or len(guard_rows) != 1:
            _fail(
                "merged event_conservation and scope_guards must each have one row"
            )

    with _validation_phase(MergeValidationErrorCode.METADATA_CONTRACT_REJECTED):
        closure_counters = _assemble_metadata(
            metadata_rows, event_totals, event_scan_count, metadata_constants
        )

    with _validation_phase(MergeValidationErrorCode.POSTMERGE_CONTRACT_REJECTED):
        public_rows = [
            {
                "section": "closure_metadata", "dimensions": {},
                "records": event_totals["candidate_emar_heads"],
                "counters": closure_counters,
            },
            *(_public_row(row) for row in vocabulary),
            *(_public_row(row) for row in code_shapes),
            *event_rows, *recovered_rows,
            *admission_status_rows, *admission_evidence_rows,
            *conservation_rows, *guard_rows,
        ]
        public_rows = _sort_rows(public_rows)
        _postmerge_invariants(public_rows, metadata_rows, event_totals)
        csv_text = _to_csv(public_rows)
    return MergeResult(
        rows=public_rows,
        csv_text=csv_text,
        validation_summary=validation_summary,
    )

