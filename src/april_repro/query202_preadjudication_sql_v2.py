"""Pure SQL/render/merge contract for Query 202 pre-adjudication v2.

This module does not connect to PostgreSQL.  It freezes the closed SQL file
inventory, the lifecycle-A subject partition, and the private tuple schemas so
the runner and independent auditor can reject drift before any MIMIC query.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence


COMPONENT_ID = "D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2"
BUCKET_COUNT = 64
BUCKET_MARKER = "__BUCKET_INDEX__"
BUCKET_HASH_PREFIX = "D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2|"
BUCKET_HASH_VERSION = "d005-k-query202-preadjudication-subject-md5-v2"

FRAME_COLUMNS = (
    "schema_version",
    "stage",
    "bucket_index",
    "record_kind",
    "tuple_kind",
    "tuple_json_base64",
    "multiplicity",
    "control_name",
    "control_value",
    "transaction_isolation",
    "transaction_read_only",
    "snapshot_token",
)

BOUNDARY_FRAME_COLUMNS = (
    "schema_version",
    "stage",
    "source_key",
    "source_field",
    "transaction_isolation",
    "transaction_read_only",
    "snapshot_token",
    "raw_is_null",
    "raw_value_base64",
    "exact_row_count",
    "raw_utf8_bytes",
)


@dataclass(frozen=True)
class BoundaryStage:
    stage: str
    source_key: str
    source_field: str
    sql_path: str
    semantic_seed_field: bool


@dataclass(frozen=True)
class BucketStatementSpec:
    """One independently bounded physical statement of a logical bucket stage."""

    stage: str
    logical_stage: str
    sql_path: str
    tuple_kinds: tuple[str, ...]
    bucket_input_source: str | None


BOUNDARY_STAGES = (
    BoundaryStage(
        "202a1",
        "emar_medication",
        "mimiciv_hosp.emar.medication",
        "sql/profiling/202a1_potassium_query202_preadjudication_emar_medication_v2.sql",
        True,
    ),
    BoundaryStage(
        "202a2",
        "detail_product_description",
        "mimiciv_hosp.emar_detail.product_description",
        "sql/profiling/202a2_potassium_query202_preadjudication_detail_product_description_v2.sql",
        True,
    ),
    BoundaryStage(
        "202a3",
        "pharmacy_medication",
        "mimiciv_hosp.pharmacy.medication",
        "sql/profiling/202a3_potassium_query202_preadjudication_pharmacy_medication_v2.sql",
        True,
    ),
    BoundaryStage(
        "202a4",
        "prescription_drug",
        "mimiciv_hosp.prescriptions.drug",
        "sql/profiling/202a4_potassium_query202_preadjudication_prescription_drug_v2.sql",
        True,
    ),
    BoundaryStage(
        "202a5",
        "detail_product_description_other",
        "mimiciv_hosp.emar_detail.product_description_other",
        "sql/profiling/202a5_potassium_query202_preadjudication_detail_product_description_other_v2.sql",
        True,
    ),
    BoundaryStage(
        "202a6",
        "emar_detail_route",
        "mimiciv_hosp.emar_detail.route",
        "sql/profiling/202a6_potassium_query202_preadjudication_emar_detail_route_v2.sql",
        False,
    ),
    BoundaryStage(
        "202a7",
        "pharmacy_route",
        "mimiciv_hosp.pharmacy.route",
        "sql/profiling/202a7_potassium_query202_preadjudication_pharmacy_route_v2.sql",
        False,
    ),
    BoundaryStage(
        "202a8",
        "prescriptions_route",
        "mimiciv_hosp.prescriptions.route",
        "sql/profiling/202a8_potassium_query202_preadjudication_prescriptions_route_v2.sql",
        False,
    ),
    BoundaryStage(
        "202a9",
        "prescriptions_ndc",
        "mimiciv_hosp.prescriptions.ndc",
        "sql/profiling/202a9_potassium_query202_preadjudication_prescriptions_ndc_v2.sql",
        False,
    ),
)

DETAIL_CONTEXT_FIELDS = (
    "row_role",
    "parent_field_ordinal",
    "administration_type",
    "complete_dose_not_given",
    "dose_due",
    "dose_due_unit",
    "dose_given",
    "dose_given_unit",
    "will_remainder_of_dose_be_given",
    "product_amount_given",
    "product_unit",
    "product_code",
    "product_description",
    "product_description_other",
    "prior_infusion_rate",
    "route",
    "infusion_rate",
    "infusion_rate_adjustment",
    "infusion_rate_adjustment_amount",
    "infusion_rate_unit",
    "infusion_complete",
    "completion_interval",
    "new_iv_bag_hung",
    "continued_infusion_in_other_location",
    "restart_interval",
    "non_formulary_visual_verification",
)

DETAIL_BRIDGE_FIELDS = (
    "head_medication",
    "detail_head_identity_state",
    "detail_match_state",
    "row_role",
    "parent_field_ordinal",
    "administration_type",
    "product_description",
    "product_description_other",
    "product_code",
    "route",
    "dose_due_unit",
    "dose_given_unit",
    "product_unit",
    "infusion_rate_unit",
)

PHARMACY_CONTEXT_FIELDS = (
    "medication",
    "proc_type",
    "status",
    "route",
    "frequency",
    "disp_sched",
    "infusion_type",
    "sliding_scale",
    "lockout_interval",
    "basal_rate",
    "one_hr_max",
    "doses_per_24_hrs",
    "duration",
    "duration_interval",
    "expiration_value",
    "expiration_unit",
    "dispensation",
    "fill_quantity",
)

PRESCRIPTION_CONTEXT_FIELDS = (
    "drug_type",
    "drug",
    "formulary_drug_cd",
    "gsn",
    "ndc",
    "prod_strength",
    "form_rx",
    "dose_val_rx",
    "dose_unit_rx",
    "form_val_disp",
    "form_unit_disp",
    "doses_per_24_hrs",
    "route",
)

TUPLE_FIELDS = {
    "202b": {
        "detail_product_context": DETAIL_CONTEXT_FIELDS,
        "detail_seed_membership_bridge": (
            *DETAIL_CONTEXT_FIELDS,
            "seed_source_field",
            "seed_exact_raw_value",
        ),
        "emar_medication_detail_bridge": DETAIL_BRIDGE_FIELDS,
        "emar_medication_head_partition": (
            "head_medication",
            "detail_match_state",
        ),
    },
    "202c": {
        "pharmacy_product_context": PHARMACY_CONTEXT_FIELDS,
        "prescription_identifier_context": PRESCRIPTION_CONTEXT_FIELDS,
        "pharmacy_prescription_bridge": (
            "link_identity_state",
            "poe_auxiliary_state",
            "pharmacy_medication",
            "pharmacy_route",
            *PRESCRIPTION_CONTEXT_FIELDS,
        ),
        "pharmacy_no_prescription_component": (
            *PHARMACY_CONTEXT_FIELDS,
            "prescription_match_state",
        ),
        "head_pharmacy_prescription_bridge": (
            "link_identity_state",
            "poe_auxiliary_state",
            "head_medication",
            "pharmacy_medication",
            "pharmacy_route",
            *PRESCRIPTION_CONTEXT_FIELDS,
        ),
        "detail_pharmacy_prescription_bridge": (
            "link_identity_state",
            "poe_auxiliary_state",
            "row_role",
            "parent_field_ordinal",
            "product_description",
            "product_description_other",
            "product_code",
            "detail_route",
            "dose_due_unit",
            "dose_given_unit",
            "product_unit",
            "infusion_rate_unit",
            "pharmacy_medication",
            "pharmacy_route",
            *PRESCRIPTION_CONTEXT_FIELDS,
        ),
        "ndc_external_mapping_input": PRESCRIPTION_CONTEXT_FIELDS,
    },
}


# Physical statement boundaries are frozen independently from the two logical
# crosswalk stages.  Every tuple kind has exactly one owner.  A non-NULL
# ``bucket_input_source`` means that the statement also owns one additive base
# relation denominator for the logical bucket.  The runner adds those owner
# controls when it reconstructs the logical 202b/202c fragment.
BUCKET_STATEMENTS = (
    BucketStatementSpec(
        "202b_context_seed",
        "202b",
        "sql/profiling/202b1_potassium_query202_preadjudication_context_seed_bucket_v2.sql",
        ("detail_product_context", "detail_seed_membership_bridge"),
        "mimiciv_hosp.emar_detail",
    ),
    BucketStatementSpec(
        "202b_detail_head_bridge",
        "202b",
        "sql/profiling/202b2_potassium_query202_preadjudication_detail_head_bridge_bucket_v2.sql",
        ("emar_medication_detail_bridge",),
        None,
    ),
    BucketStatementSpec(
        "202b_head_partition",
        "202b",
        "sql/profiling/202b3_potassium_query202_preadjudication_head_partition_bucket_v2.sql",
        ("emar_medication_head_partition",),
        None,
    ),
    BucketStatementSpec(
        "202c_pharmacy_context",
        "202c",
        "sql/profiling/202c1_potassium_query202_preadjudication_pharmacy_context_bucket_v2.sql",
        ("pharmacy_product_context", "pharmacy_no_prescription_component"),
        "mimiciv_hosp.pharmacy",
    ),
    BucketStatementSpec(
        "202c_prescription_context",
        "202c",
        "sql/profiling/202c2_potassium_query202_preadjudication_prescription_context_bucket_v2.sql",
        (
            "prescription_identifier_context",
            "pharmacy_prescription_bridge",
            "ndc_external_mapping_input",
        ),
        "mimiciv_hosp.prescriptions",
    ),
    BucketStatementSpec(
        "202c_head_bridge",
        "202c",
        "sql/profiling/202c3_potassium_query202_preadjudication_head_bridge_bucket_v2.sql",
        ("head_pharmacy_prescription_bridge",),
        "mimiciv_hosp.emar",
    ),
    BucketStatementSpec(
        "202c_detail_bridge",
        "202c",
        "sql/profiling/202c4_potassium_query202_preadjudication_detail_bridge_bucket_v2.sql",
        ("detail_pharmacy_prescription_bridge",),
        "mimiciv_hosp.emar_detail",
    ),
)

BUCKET_STATEMENT_BY_STAGE = {item.stage: item for item in BUCKET_STATEMENTS}
BUCKET_STATEMENTS_BY_LOGICAL_STAGE = {
    logical_stage: tuple(
        item for item in BUCKET_STATEMENTS if item.logical_stage == logical_stage
    )
    for logical_stage in ("202b", "202c")
}
BUCKET_SQL_PATHS = {item.stage: item.sql_path for item in BUCKET_STATEMENTS}

# Closed categorical values emitted by the static SQL.  Exact clinical/local
# text fields remain unconstrained strings; only implementation-created state
# labels belong here.  Keeping these enums beside the tuple schemas prevents a
# typo or an unreachable fallback label from silently entering a frozen
# private artifact.
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
    ("202b", "emar_medication_detail_bridge", "detail_match_state"): ("with_detail",),
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
    ("202c", "detail_pharmacy_prescription_bridge", "row_role"): ("parent", "product"),
}


def _control_names(stage: str) -> tuple[str, ...]:
    common = (
        "bucket_assignment_violations",
        "null_subject_outside_bucket_zero",
        "bucket_input_rows",
        "bucket_output_multiplicity",
    )
    per_kind = tuple(
        value
        for kind in TUPLE_FIELDS[stage]
        for value in (f"{kind}_input_rows", f"{kind}_tuple_multiplicity")
    )
    return (*common, *per_kind)


CONTROL_NAMES = {stage: _control_names(stage) for stage in ("202b", "202c")}


def _physical_control_names(spec: BucketStatementSpec) -> tuple[str, ...]:
    common = (
        (
            "bucket_assignment_violations",
            "null_subject_outside_bucket_zero",
            "bucket_input_rows",
        )
        if spec.bucket_input_source is not None
        else ()
    )
    per_kind = tuple(
        value
        for kind in spec.tuple_kinds
        for value in (f"{kind}_input_rows", f"{kind}_tuple_multiplicity")
    )
    return (*common, "bucket_output_multiplicity", *per_kind)


PHYSICAL_CONTROL_NAMES = {
    spec.stage: _physical_control_names(spec) for spec in BUCKET_STATEMENTS
}
BUCKET_STATEMENT_CONTROL_NAMES = PHYSICAL_CONTROL_NAMES


def subject_bucket(subject_id: int | None) -> int:
    """Return the lifecycle-A v2 bucket without importing lifecycle B."""
    if subject_id is None:
        return 0
    if isinstance(subject_id, bool) or not isinstance(subject_id, int):
        raise ValueError("subject_id must be an integer or None")
    digest = hashlib.md5(
        f"{BUCKET_HASH_PREFIX}{subject_id}".encode("ascii"), usedforsecurity=False
    ).hexdigest()
    return int(digest[:15], 16) % BUCKET_COUNT


def validate_bucket_indices(indices: Sequence[int]) -> None:
    if list(indices) != list(range(BUCKET_COUNT)):
        raise ValueError("pre-adjudication v2 buckets must be ordered integers 0..63")


def render_bucket_sql(template: str, bucket_index: int) -> str:
    """Render the only permitted SQL marker after closed-range validation."""
    if isinstance(bucket_index, bool) or not isinstance(bucket_index, int):
        raise ValueError("bucket index must be an integer")
    if not 0 <= bucket_index < BUCKET_COUNT:
        raise ValueError("bucket index outside 0..63")
    if template.count(BUCKET_MARKER) != 1:
        raise ValueError("bucket SQL must contain exactly one bucket marker")
    rendered = template.replace(BUCKET_MARKER, str(bucket_index))
    if "__" in rendered:
        raise ValueError("unresolved SQL template marker")
    return rendered


def read_and_render_bucket_sql(root: Path, stage: str, bucket_index: int) -> str:
    """Read and render one frozen physical bucket statement."""
    try:
        relative = BUCKET_SQL_PATHS[stage]
    except KeyError as exc:
        raise ValueError("unknown physical bucket stage") from exc
    return render_bucket_sql((root / relative).read_text(encoding="utf-8"), bucket_index)


def decode_and_validate_tuple_payload(stage: str, kind: str, value: str) -> dict[str, str | None]:
    """Decode one private tuple and require the exact frozen null/string schema."""
    try:
        expected = TUPLE_FIELDS[stage][kind]
    except KeyError as exc:
        raise ValueError("unknown tuple stage or kind") from exc
    def exact_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        output: dict[str, object] = {}
        for key, item in pairs:
            if key in output:
                raise ValueError("tuple JSON repeats a field")
            output[key] = item
        return output
    try:
        raw = base64.b64decode(value, validate=True)
        decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=exact_object)
    except Exception as exc:  # exact exception type is not part of the contract
        raise ValueError("invalid base64 UTF-8 JSON tuple") from exc
    if not isinstance(decoded, dict) or set(decoded) != set(expected):
        raise ValueError("tuple fields differ from frozen schema")
    if any(item is not None and not isinstance(item, str) for item in decoded.values()):
        raise ValueError("tuple values must be JSON null or exact strings")
    for field in expected:
        allowed = TUPLE_VALUE_ENUMS.get((stage, kind, field))
        if allowed is not None and decoded[field] not in allowed:
            raise ValueError("tuple categorical value differs from frozen enum")
    return {name: decoded[name] for name in expected}


def merge_tuple_partitions(
    stage: str,
    partitions: Mapping[int, Iterable[tuple[str, bytes, int]]],
) -> list[tuple[str, bytes, int]]:
    """Reference merge: sum equal private tuples, then globally byte-sort.

    The runner may stream this operation, but may not concatenate or combine
    partition hashes.  ``payload`` is the decoded canonical JSON byte string.
    """
    if stage not in TUPLE_FIELDS:
        raise ValueError("unknown tuple stage")
    validate_bucket_indices(tuple(partitions))
    merged: dict[tuple[str, bytes], int] = {}
    merged_multiplicity_max = (1 << 63) - 1
    allowed = set(TUPLE_FIELDS[stage])
    for bucket_index in range(BUCKET_COUNT):
        for kind, payload, multiplicity in partitions[bucket_index]:
            if kind not in allowed:
                raise ValueError("unknown tuple kind")
            if not isinstance(payload, bytes):
                raise ValueError("tuple payload must be bytes")
            if (
                isinstance(multiplicity, bool)
                or not isinstance(multiplicity, int)
                or not 0 < multiplicity <= merged_multiplicity_max
            ):
                raise ValueError("multiplicity must be a positive signed-bigint value")
            key = (kind, payload)
            total = merged.get(key, 0) + multiplicity
            if total > merged_multiplicity_max:
                raise OverflowError("merged multiplicity exceeds the frozen limit")
            merged[key] = total
    return [(*key, merged[key]) for key in sorted(merged)]
