"""Private Query-201 to D005 product-semantic review ledger workflow.

This module is deliberately offline.  It copies the accepted Query-201 raw
vocabulary memberships into a private review ledger without making a product
identity decision.  Query-201 review strata remain lineage only: every source
membership is retained and all five semantic dimensions start ``uncertain``.

The validator also supports later reviewed copies of the ledger, while keeping
the exact Query-201 membership universe fixed.  It never treats a SQL NULL as
text.  A literal text value such as ``"NULL"`` remains an ordinary non-NULL
value only when that exact string was present in Query 201.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tomllib
from typing import Any


ARTIFACT_NAME = "potassium_product_semantic_review"
LEDGER_FILENAME = ARTIFACT_NAME + ".initial-ledger.json"
SUMMARY_FILENAME = ARTIFACT_NAME + ".aggregate-summary.json"
LEDGER_SCHEMA_VERSION = "k-product-review-ledger-v1"
COMPONENT_ID = "D005-K-PRODUCT-MAPPING-v1"

DEFAULT_Q201_DIRECTORY = Path("artifacts/profiling/20261011T182244.083389Z")
DEFAULT_PREFLIGHT_DIRECTORY = Path("artifacts/profiling/20261011T190426.934406Z")
DEFAULT_OUTPUT_PARENT = Path("artifacts/product-mapping")
Q201_FILES = {
    "manifest": "manifest.json",
    "audit": "audit-summary.json",
    "summary": "potassium_full_source_vocabulary_discovery.aggregate-summary.json",
    "discovery": "potassium_full_source_vocabulary_discovery.discovery.json",
}
EXPECTED_Q201_HASHES = {
    "manifest": "fe13a910a590df49e26b8e71770735d100af7f9e474cf9769a619c0b2cc6fa44",
    "audit": "a7aa9b35d4e408bbeda6b4e024588e3083fc7f13b976492b624d21a390946428",
    "summary": "784c618be25f4e243f5bda89619bbb6d004c8eee10fc40b6327e311c83fc30ea",
    "discovery": "62731e7dcadf82b95a55e3afd7f2790455320d1c642f9ca307b2574672760d18",
}
PREFLIGHT_FILES = {
    "manifest": "manifest.json",
    "audit": "audit-summary.json",
    "summary": "potassium_mapping_preflight.aggregate-summary.json",
    "private_values": "potassium_mapping_preflight.private-values.json",
}
EXPECTED_PREFLIGHT_HASHES = {
    "manifest": "bdfcb78849eadb1b9eafca226fe49c7e70390f45ee0f3ef34c8e92899557c880",
    "audit": "c96b7bed50a7b29ac7f8bfc14ed05b03394ad3c996d2c4b2c891ccbf964d024e",
    "summary": "079a8b774773a039977d21aad88e128d0d3658483268ded38aa931842fa2a220",
    "private_values": "82e7d89cca2d756d5af85c038618f880fb88c378ee8b271e43181989faabcc83",
}
PRODUCT_OTHER_TYPED_SET_SHA256 = (
    "0105f73cef307cc11b93e1d9d657d43a278c66c3c06ef31e5123db377e11dd4e"
)
MAPPING_CONFIG_PATH = Path("config/preregistrations/d005_potassium_product_mapping.toml")
MAPPING_REDUCER_PATH = Path("src/april_repro/product_mapping_contract.py")
EXPECTED_MAPPING_CONFIG_SHA256 = (
    "960e0e68d848613d2b75c0e2a5afa6db9c853bdbf24a3a2f214bdcccb94df9ee"
)
EXPECTED_MAPPING_REDUCER_SHA256 = (
    "27bd346a740eb2578431f2cda997d76439e2f5772a94bd8d9b0c060a26f0b11e"
)

SEMANTIC_DIMENSIONS = (
    "product_identity",
    "dosage_form",
    "treatment_intent",
    "potassium_content",
    "meq_convertibility",
)
SEMANTIC_STATUSES = frozenset({"supported", "refuted", "uncertain"})
REVIEW_STATUSES = frozenset({"unreviewed", "reviewed"})

REVIEW_STRATA = frozenset({
    "blank_after_trim",
    "focal_kcl_repletion_hint",
    "broader_phosphate_or_acetate_repletion_hint",
    "other_potassium_salt_review",
    "non_repletion_active_drug_hint",
    "unresolved_potassium_lexical_review",
    "no_declared_potassium_lexical_signal",
})

FORMAL_GUARDS = (
    "query202_executed",
    "product_mapping_accepted",
    "route_mapping_frozen",
    "administration_status_gate_frozen",
    "interference_candidate_is_administered_treatment",
    "product_identity_decided",
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


class ProductReviewLedgerError(RuntimeError):
    """A value-safe contract failure."""


class SourceSpec(tuple):
    """Small immutable source description without a dataclass dependency."""

    __slots__ = ()

    def __new__(cls, key: str, field: str, evidence_path: str):
        return tuple.__new__(cls, (key, field, evidence_path))

    @property
    def key(self) -> str:
        return self[0]

    @property
    def field(self) -> str:
        return self[1]

    @property
    def evidence_path(self) -> str:
        return self[2]


SOURCES = (
    SourceSpec(
        "emar_medication",
        "mimiciv_hosp.emar.medication",
        "query201/emar_medication/full_nonnull_distinct",
    ),
    SourceSpec(
        "detail_product_description",
        "mimiciv_hosp.emar_detail.product_description",
        "query201/detail_product_description/full_nonnull_distinct",
    ),
    SourceSpec(
        "pharmacy_medication",
        "mimiciv_hosp.pharmacy.medication",
        "query201/pharmacy_medication/full_nonnull_distinct",
    ),
    SourceSpec(
        "prescription_drug",
        "mimiciv_hosp.prescriptions.drug",
        "query201/prescription_drug/full_nonnull_distinct",
    ),
)
SOURCE_BY_KEY = {source.key: source for source in SOURCES}
PRODUCT_OTHER_SOURCE = SourceSpec(
    "detail_product_description_other",
    "mimiciv_hosp.emar_detail.product_description_other",
    "mapping_preflight/detail_product_description_other/full_typed_distinct",
)
EXTENDED_SOURCES = SOURCES + (PRODUCT_OTHER_SOURCE,)
EXPECTED_SOURCE_COUNTS = {
    "emar_medication": 5_045,
    "detail_product_description": 6_692,
    "pharmacy_medication": 11_059,
    "prescription_drug": 10_927,
}
EXPECTED_Q200_COUNTS = {
    "emar_medication": 23,
    "detail_product_description": 79,
    "pharmacy_medication": 45,
    "prescription_drug": 52,
}
EXPECTED_TOTAL = 33_723
EXPECTED_Q200_OVERLAP = 199
EXPECTED_NEGATIVE_SPACE = 33_524
EXPECTED_PRODUCT_OTHER_NONNULL = 842
EXPECTED_PRODUCT_OTHER_SQL_NULL_TYPED_PRESENCE = 1
EXPECTED_EXTENDED_TOTAL = 34_565

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_JSON_BYTES = 256 * 1024 * 1024
MAX_RAW_UTF8_BYTES = 16 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _strict_json_bytes(payload: bytes, label: str) -> dict[str, Any]:
    if len(payload) > MAX_JSON_BYTES:
        raise ProductReviewLedgerError(label + ".byte_limit")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ProductReviewLedgerError(label + ".duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(_: str) -> None:
        raise ProductReviewLedgerError(label + ".nonfinite_number")

    try:
        value = json.loads(
            payload,
            object_pairs_hook=unique,
            parse_constant=invalid_constant,
        )
    except ProductReviewLedgerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductReviewLedgerError(label + ".valid_json") from exc
    if not isinstance(value, dict):
        raise ProductReviewLedgerError(label + ".object")
    return value


def _read_private_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink():
        raise ProductReviewLedgerError(label + ".regular_file")
    if _mode(path) != "0600":
        raise ProductReviewLedgerError(label + ".private_mode")
    raw = path.read_bytes()
    return _strict_json_bytes(raw, label), raw


def _write_private(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        path.unlink(missing_ok=True)
        raise


def _json_payload(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _hash_parts(parts: Sequence[str]) -> str:
    """Hash exact UTF-8 parts with an unsigned 64-bit length prefix."""
    digest = hashlib.sha256()
    for part in parts:
        if not isinstance(part, str):
            raise ProductReviewLedgerError("ledger.hash_parts.text_only")
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _validated_raw(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ProductReviewLedgerError(label + ".exact_raw_text")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ProductReviewLedgerError(label + ".utf8") from exc
    if b"\x00" in encoded or len(encoded) > MAX_RAW_UTF8_BYTES:
        raise ProductReviewLedgerError(label + ".raw_text_bounds")
    return value


def _validate_q201_discovery(
    discovery: Mapping[str, Any],
    *,
    expected_source_counts: Mapping[str, int],
    expected_q200_counts: Mapping[str, int],
) -> dict[str, Any]:
    if (
        discovery.get("schema_version") != 1
        or discovery.get("query") != "potassium_full_source_vocabulary_discovery"
        or discovery.get("all_source_policy_statuses") != "unresolved"
        or discovery.get("dictionary_value_is_patient_text") is not False
    ):
        raise ProductReviewLedgerError("q201.discovery.fixed_contract")
    guards = discovery.get("policy_guards")
    if not isinstance(guards, Mapping) or not guards or any(
        value is not False for value in guards.values()
    ):
        raise ProductReviewLedgerError("q201.discovery.formal_guards_false")
    transaction = discovery.get("transaction")
    if (
        not isinstance(transaction, Mapping)
        or transaction.get("isolation") != "repeatable read"
        or transaction.get("read_only") is not True
        or transaction.get("same_snapshot") is not True
        or transaction.get("rollback_confirmed_before_persistence") is not True
        or transaction.get("clean_psql_exit_confirmed_before_persistence") is not True
    ):
        raise ProductReviewLedgerError("q201.discovery.execution_controls")
    sources = discovery.get("sources")
    if not isinstance(sources, Mapping) or set(sources) != set(SOURCE_BY_KEY):
        raise ProductReviewLedgerError("q201.discovery.four_sources_exact")
    if set(expected_source_counts) != set(SOURCE_BY_KEY) or set(
        expected_q200_counts
    ) != set(SOURCE_BY_KEY):
        raise ProductReviewLedgerError("q201.expected_counts.schema")

    validated: dict[str, Any] = {}
    total = 0
    overlap = 0
    for spec in SOURCES:
        source = sources[spec.key]
        if not isinstance(source, Mapping):
            raise ProductReviewLedgerError(f"q201.{spec.key}.source_object")
        records = source.get("values")
        if (
            source.get("source_field") != spec.field
            or not isinstance(records, list)
            or source.get("distinct_nonnull_values") != len(records)
            or len(records) != expected_source_counts[spec.key]
            or source.get("q200_dictionary_values") != expected_q200_counts[spec.key]
        ):
            raise ProductReviewLedgerError(f"q201.{spec.key}.source_contract")
        raw_seen: set[str] = set()
        ordered: list[str] = []
        source_overlap = 0
        validated_records: list[dict[str, Any]] = []
        for index, record in enumerate(records):
            label = f"q201.{spec.key}.record_{index}"
            if not isinstance(record, Mapping):
                raise ProductReviewLedgerError(label + ".object")
            raw = _validated_raw(record.get("raw_name"), label)
            if raw in raw_seen:
                raise ProductReviewLedgerError(f"q201.{spec.key}.raw_unique")
            raw_seen.add(raw)
            ordered.append(raw)
            q200_member = record.get("q200_member")
            stratum = record.get("review_stratum")
            if type(q200_member) is not bool:
                raise ProductReviewLedgerError(label + ".q200_boolean")
            if stratum not in REVIEW_STRATA:
                raise ProductReviewLedgerError(label + ".known_review_stratum")
            if (
                record.get("source_policy_status") != "unresolved"
                or record.get("source_review_stratum_is_final_policy") is not False
            ):
                raise ProductReviewLedgerError(label + ".lexical_not_policy")
            source_overlap += int(q200_member)
            validated_records.append({
                "raw_name": raw,
                "q200_member": q200_member,
                "review_stratum": stratum,
            })
        if ordered != sorted(ordered):
            raise ProductReviewLedgerError(f"q201.{spec.key}.deterministic_order")
        if source_overlap != expected_q200_counts[spec.key]:
            raise ProductReviewLedgerError(f"q201.{spec.key}.q200_overlap")
        validated[spec.key] = validated_records
        total += len(records)
        overlap += source_overlap
    return {
        "sources": validated,
        "total": total,
        "q200_overlap": overlap,
        "negative_space": total - overlap,
    }


def _typed_set_sha256(source_field: str, records: Sequence[Mapping[str, Any]]) -> str:
    """Recompute the preflight typed-set hash from exact typed values."""
    field_bytes = source_field.encode("utf-8")
    null_seen = False
    values: list[bytes] = []
    for record in records:
        is_null = record.get("raw_is_null")
        raw = record.get("raw_value")
        count = record.get("exact_row_count")
        if type(count) is not int or count < 1:
            raise ProductReviewLedgerError("preflight.product_other.positive_frequency")
        if is_null is True and raw is None:
            if null_seen:
                raise ProductReviewLedgerError("preflight.product_other.single_sql_null")
            null_seen = True
        elif is_null is False and isinstance(raw, str):
            encoded = raw.encode("utf-8")
            if b"\x00" in encoded or len(encoded) > MAX_RAW_UTF8_BYTES:
                raise ProductReviewLedgerError("preflight.product_other.raw_text_bounds")
            values.append(encoded)
        else:
            raise ProductReviewLedgerError("preflight.product_other.typed_state")
    if len(values) != len(set(values)):
        raise ProductReviewLedgerError("preflight.product_other.unique_nonnull")
    values.sort()
    digest = hashlib.sha256()
    digest.update(b"typed-distinct-source-value-set-v1")
    digest.update(len(field_bytes).to_bytes(4, "big"))
    digest.update(field_bytes)
    digest.update((len(values) + int(null_seen)).to_bytes(8, "big"))
    if null_seen:
        digest.update(b"\x00")
    for encoded in values:
        digest.update(b"\x01")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _validate_preflight_product_other(
    private_values: Mapping[str, Any],
    *,
    expected_nonnull_count: int = EXPECTED_PRODUCT_OTHER_NONNULL,
    expected_typed_set_sha256: str = PRODUCT_OTHER_TYPED_SET_SHA256,
) -> dict[str, Any]:
    if (
        private_values.get("schema_version") != 1
        or private_values.get("query") != "potassium_mapping_preflight"
        or private_values.get("raw_values_are_exact_and_unnormalized") is not True
        or private_values.get("contains_patient_or_event_identifiers") is not False
        or private_values.get("contains_event_timestamps") is not False
        or private_values.get("external_api_called") is not False
        or private_values.get("final_source_policy") is not False
        or private_values.get("product_identity_decided") is not False
        or private_values.get("route_mapping_created") is not False
    ):
        raise ProductReviewLedgerError("preflight.private_values.neutral_contract")
    sources = private_values.get("sources")
    source = (
        sources.get(PRODUCT_OTHER_SOURCE.key)
        if isinstance(sources, Mapping)
        else None
    )
    if not isinstance(source, Mapping):
        raise ProductReviewLedgerError("preflight.product_other.source_present")
    records = source.get("records")
    if (
        source.get("source_field") != PRODUCT_OTHER_SOURCE.field
        or source.get("field_role") != "product_description_other"
        or source.get("typed_distinct_values") != expected_nonnull_count + 1
        or source.get("nonnull_distinct_values") != expected_nonnull_count
        or source.get("sql_null_present") is not True
        or type(source.get("sql_null_rows")) is not int
        or source["sql_null_rows"] < 1
        or source.get("typed_set_sha256") != expected_typed_set_sha256
        or not isinstance(records, list)
        or len(records) != expected_nonnull_count + 1
    ):
        raise ProductReviewLedgerError("preflight.product_other.fixed_contract")
    null_records = [item for item in records if isinstance(item, Mapping) and item.get("raw_is_null") is True]
    nonnull_records = [item for item in records if isinstance(item, Mapping) and item.get("raw_is_null") is False]
    if len(null_records) != 1 or len(nonnull_records) != expected_nonnull_count:
        raise ProductReviewLedgerError("preflight.product_other.typed_842_plus_1")
    null_record = null_records[0]
    if (
        null_record.get("raw_value") is not None
        or null_record.get("nonnull_substate") is not None
        or null_record.get("raw_utf8_bytes") != 0
        or null_record.get("exact_row_count") != source.get("sql_null_rows")
    ):
        raise ProductReviewLedgerError("preflight.product_other.sql_null_boundary_only")
    validated: list[dict[str, Any]] = []
    raw_seen: set[str] = set()
    for index, record in enumerate(nonnull_records):
        label = f"preflight.product_other.record_{index}"
        raw = _validated_raw(record.get("raw_value"), label)
        encoded = raw.encode("utf-8")
        count = record.get("exact_row_count")
        substate = record.get("nonnull_substate")
        expected_substate = (
            "empty_string" if raw == ""
            else "whitespace_only" if raw.isspace()
            else "nonblank"
        )
        if (
            raw in raw_seen
            or type(count) is not int
            or count < 1
            or record.get("raw_utf8_bytes") != len(encoded)
            or substate != expected_substate
        ):
            raise ProductReviewLedgerError(label + ".exact_nonnull_contract")
        raw_seen.add(raw)
        validated.append({
            "raw_name": raw,
            "nonnull_substate": substate,
            "exact_row_count": count,
        })
    if [item["raw_name"] for item in validated] != sorted(
        item["raw_name"] for item in validated
    ):
        raise ProductReviewLedgerError("preflight.product_other.deterministic_order")
    if _typed_set_sha256(PRODUCT_OTHER_SOURCE.field, records) != expected_typed_set_sha256:
        raise ProductReviewLedgerError("preflight.product_other.typed_set_hash_recomputed")
    return {
        "records": validated,
        "nonnull_distinct_values": len(validated),
        "sql_null_typed_presence": 1,
        "sql_null_rows": source["sql_null_rows"],
        "typed_set_sha256": expected_typed_set_sha256,
    }


def _validate_mapping_contract(root: Path) -> dict[str, str]:
    config_path = root / MAPPING_CONFIG_PATH
    reducer_path = root / MAPPING_REDUCER_PATH
    if not config_path.is_file() or config_path.is_symlink():
        raise ProductReviewLedgerError("mapping.config.regular_file")
    if not reducer_path.is_file() or reducer_path.is_symlink():
        raise ProductReviewLedgerError("mapping.reducer.regular_file")
    config_hash = _sha_file(config_path)
    reducer_hash = _sha_file(reducer_path)
    if config_hash != EXPECTED_MAPPING_CONFIG_SHA256:
        raise ProductReviewLedgerError("mapping.config.frozen_hash")
    if reducer_hash != EXPECTED_MAPPING_REDUCER_SHA256:
        raise ProductReviewLedgerError("mapping.reducer.frozen_hash")
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ProductReviewLedgerError("mapping.config.valid_toml") from exc
    ledger = config.get("private_ledger")
    baseline = config.get("q201_baseline")
    executable = config.get("executable_reducer_contract")
    guards = config.get("guards")
    if (
        config.get("component_id") != COMPONENT_ID
        or config.get("status") != "proposed"
        or config.get("formal_product_mapping_enabled") is not False
        or config.get("formal_source_policy_enabled") is not False
        or not isinstance(ledger, Mapping)
        or ledger.get("schema_version") != "k-product-ledger-v1"
        or ledger.get("initial_semantic_status") != "uncertain"
        or ledger.get("vocabulary_semantic_dimensions") != list(SEMANTIC_DIMENSIONS)
        or ledger.get("normalization_establishes_identity") is not False
        or ledger.get("separate_review_status_from_semantic_status") is not True
        or not isinstance(baseline, Mapping)
        or baseline.get("source_value_memberships") != EXPECTED_TOTAL
        or baseline.get("query200_overlap_memberships") != EXPECTED_Q200_OVERLAP
        or baseline.get("negative_space_memberships") != EXPECTED_NEGATIVE_SPACE
        or baseline.get("neutral_review_strata_are_inclusion_rules") is not False
        or not isinstance(executable, Mapping)
        or executable.get("file_sha256") != reducer_hash
        or not isinstance(guards, Mapping)
        or set(guards) != set(FORMAL_GUARDS)
        or any(value is not False for value in guards.values())
    ):
        raise ProductReviewLedgerError("mapping.config.review_ledger_contract")
    return {
        "mapping_config_sha256": config_hash,
        "mapping_reducer_sha256": reducer_hash,
    }


def load_accepted_inputs(
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load accepted Q201, preflight product-other and mapping contracts."""
    q201_directory = root / DEFAULT_Q201_DIRECTORY
    if not q201_directory.is_dir() or q201_directory.is_symlink():
        raise ProductReviewLedgerError("q201.directory.private_directory")
    if _mode(q201_directory) != "0700":
        raise ProductReviewLedgerError("q201.directory.mode_0700")
    documents: dict[str, dict[str, Any]] = {}
    actual_hashes: dict[str, str] = {}
    for role, filename in Q201_FILES.items():
        path = q201_directory / filename
        document, raw = _read_private_json(path, "q201." + role)
        actual = _sha_bytes(raw)
        if actual != EXPECTED_Q201_HASHES[role]:
            raise ProductReviewLedgerError("q201." + role + ".frozen_hash")
        documents[role] = document
        actual_hashes[role] = actual
    manifest = documents["manifest"]
    audit = documents["audit"]
    summary = documents["summary"]
    if manifest.get("status") != "complete" or manifest.get("selected_queries") != [
        "potassium_full_source_vocabulary_discovery"
    ]:
        raise ProductReviewLedgerError("q201.manifest.complete")
    checks = audit.get("audit_checks")
    if (
        audit.get("status") != "passed"
        or not isinstance(checks, Mapping)
        or checks.get("failed") != []
        or checks.get("total") != 303_641
    ):
        raise ProductReviewLedgerError("q201.audit.passed")
    global_counts = summary.get("global_source_value_memberships")
    private_hashes = summary.get("private_artifact_hashes")
    if (
        summary.get("status") != "complete"
        or not isinstance(global_counts, Mapping)
        or global_counts.get("distinct_nonnull_source_value_memberships")
        != EXPECTED_TOTAL
        or global_counts.get("query200_overlap_source_value_memberships")
        != EXPECTED_Q200_OVERLAP
        or global_counts.get("negative_space_source_value_memberships")
        != EXPECTED_NEGATIVE_SPACE
        or not isinstance(private_hashes, Mapping)
        or private_hashes.get("discovery_sha256") != actual_hashes["discovery"]
    ):
        raise ProductReviewLedgerError("q201.summary.fixed_counts_and_hash")
    validated = _validate_q201_discovery(
        documents["discovery"],
        expected_source_counts=EXPECTED_SOURCE_COUNTS,
        expected_q200_counts=EXPECTED_Q200_COUNTS,
    )
    if (
        validated["total"] != EXPECTED_TOTAL
        or validated["q200_overlap"] != EXPECTED_Q200_OVERLAP
        or validated["negative_space"] != EXPECTED_NEGATIVE_SPACE
    ):
        raise ProductReviewLedgerError("q201.discovery.global_conservation")

    preflight_directory = root / DEFAULT_PREFLIGHT_DIRECTORY
    if not preflight_directory.is_dir() or preflight_directory.is_symlink():
        raise ProductReviewLedgerError("preflight.directory.private_directory")
    if _mode(preflight_directory) != "0700":
        raise ProductReviewLedgerError("preflight.directory.mode_0700")
    preflight_documents: dict[str, dict[str, Any]] = {}
    preflight_hashes: dict[str, str] = {}
    for role, filename in PREFLIGHT_FILES.items():
        path = preflight_directory / filename
        document, raw = _read_private_json(path, "preflight." + role)
        actual = _sha_bytes(raw)
        if actual != EXPECTED_PREFLIGHT_HASHES[role]:
            raise ProductReviewLedgerError("preflight." + role + ".frozen_hash")
        preflight_documents[role] = document
        preflight_hashes[role] = actual
    preflight_audit_checks = preflight_documents["audit"].get("audit_checks")
    if (
        preflight_documents["manifest"].get("status") != "complete"
        or preflight_documents["audit"].get("status") != "passed"
        or not isinstance(preflight_audit_checks, Mapping)
        or preflight_audit_checks.get("total") != 30_860
        or preflight_audit_checks.get("failed") != []
    ):
        raise ProductReviewLedgerError("preflight.execution_and_audit_passed")
    product_other = _validate_preflight_product_other(
        preflight_documents["private_values"]
    )
    mapping_hashes = _validate_mapping_contract(root)
    lineage = {
        "q201_manifest_sha256": actual_hashes["manifest"],
        "q201_audit_sha256": actual_hashes["audit"],
        "q201_summary_sha256": actual_hashes["summary"],
        "q201_discovery_sha256": actual_hashes["discovery"],
        "preflight_manifest_sha256": preflight_hashes["manifest"],
        "preflight_audit_sha256": preflight_hashes["audit"],
        "preflight_summary_sha256": preflight_hashes["summary"],
        "preflight_private_values_sha256": preflight_hashes["private_values"],
        "product_description_other_typed_set_sha256": product_other[
            "typed_set_sha256"
        ],
        **mapping_hashes,
    }
    return documents["discovery"], preflight_documents["private_values"], lineage


def _initial_semantics() -> dict[str, dict[str, Any]]:
    return {
        dimension: {"status": "uncertain", "value": None, "evidence_refs": []}
        for dimension in SEMANTIC_DIMENSIONS
    }


def build_initial_review_ledger(
    q201_discovery: Mapping[str, Any],
    preflight_private_values: Mapping[str, Any],
    input_hashes: Mapping[str, str],
    *,
    expected_source_counts: Mapping[str, int] = EXPECTED_SOURCE_COUNTS,
    expected_q200_counts: Mapping[str, int] = EXPECTED_Q200_COUNTS,
    expected_product_other_nonnull: int = EXPECTED_PRODUCT_OTHER_NONNULL,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the all-uncertain Q201 plus product-other review universe."""
    if set(input_hashes) != {
        "q201_manifest_sha256",
        "q201_audit_sha256",
        "q201_summary_sha256",
        "q201_discovery_sha256",
        "preflight_manifest_sha256",
        "preflight_audit_sha256",
        "preflight_summary_sha256",
        "preflight_private_values_sha256",
        "product_description_other_typed_set_sha256",
        "mapping_config_sha256",
        "mapping_reducer_sha256",
    } or any(
        not isinstance(value, str) or _SHA256.fullmatch(value) is None
        for value in input_hashes.values()
    ):
        raise ProductReviewLedgerError("ledger.input_hashes.exact_schema")
    validated = _validate_q201_discovery(
        q201_discovery,
        expected_source_counts=expected_source_counts,
        expected_q200_counts=expected_q200_counts,
    )
    product_other = _validate_preflight_product_other(
        preflight_private_values,
        expected_nonnull_count=expected_product_other_nonnull,
        expected_typed_set_sha256=input_hashes[
            "product_description_other_typed_set_sha256"
        ],
    )
    created = created_at_utc or _now()
    if not _valid_timestamp(created):
        raise ProductReviewLedgerError("ledger.created_at.timestamp")
    records: list[dict[str, Any]] = []

    def append_record(
        *,
        spec: SourceSpec,
        raw: str,
        source_type: str,
        origin_component: str,
        q201_review_stratum: str | None,
        q201_q200_member: bool | None,
        preflight_nonnull_substate: str | None,
        preflight_exact_row_count: int | None,
    ) -> None:
        records.append({
            "lineage": {
                "source_type": source_type,
                "evidence_path": spec.evidence_path,
                "source_field": spec.field,
                "source_key": spec.key,
                "origin_component": origin_component,
                "q201_review_stratum": q201_review_stratum,
                "q201_q200_member": q201_q200_member,
                "preflight_nonnull_substate": preflight_nonnull_substate,
                "preflight_exact_row_count": preflight_exact_row_count,
                "source_policy_status": "unresolved",
                "lexical_review_stratum_is_inclusion_rule": False,
            },
            "raw_value": {
                "state": "nonnull",
                "exact_raw_name": raw,
            },
            "private_keys": {
                "ledger_key_sha256": _hash_parts((
                    LEDGER_SCHEMA_VERSION,
                    source_type,
                    spec.evidence_path,
                    raw,
                )),
                "canonical_semantic_key_sha256": _hash_parts((
                    "k-product-canonical-semantic-key-v1",
                    spec.field,
                    raw,
                )),
            },
            "semantic_decisions": _initial_semantics(),
            "review": {
                "status": "unreviewed",
                "reviewer_or_method": None,
                "reviewed_at_utc": None,
                "rationale": None,
            },
            "mapping_group": {
                "id": None,
                "evidence_refs": [],
            },
        })

    for spec in SOURCES:
        for q201_record in validated["sources"][spec.key]:
            append_record(
                spec=spec,
                raw=q201_record["raw_name"],
                source_type="query201_full_nonnull_vocabulary",
                origin_component="D005-K-SOURCE-DISCOVERY-v1",
                q201_review_stratum=q201_record["review_stratum"],
                q201_q200_member=q201_record["q200_member"],
                preflight_nonnull_substate=None,
                preflight_exact_row_count=None,
            )
    for preflight_record in product_other["records"]:
        append_record(
            spec=PRODUCT_OTHER_SOURCE,
            raw=preflight_record["raw_name"],
            source_type="mapping_preflight_full_typed_vocabulary",
            origin_component="D005-K-MAPPING-PREFLIGHT-v1",
            q201_review_stratum=None,
            q201_q200_member=None,
            preflight_nonnull_substate=preflight_record["nonnull_substate"],
            preflight_exact_row_count=preflight_record["exact_row_count"],
        )
    return {
        "schema_version": 1,
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "component_id": COMPONENT_ID,
        "artifact_role": "private_extended_product_semantic_review_ledger",
        "created_at_utc": created,
        "input_hashes": dict(input_hashes),
        "source_contract": {
            "q201_baseline_memberships": validated["total"],
            "preflight_product_description_other_nonnull_memberships": product_other[
                "nonnull_distinct_values"
            ],
            "extended_nonnull_semantic_memberships": len(records),
            "raw_value_state_required": "nonnull",
            "sql_null_records_allowed": False,
            "sql_null_string_sentinel_allowed": False,
            "empty_string_is_nonnull": True,
            "normalization_establishes_identity": False,
            "lexical_review_stratum_is_inclusion_rule": False,
            "all_q201_memberships_retained": True,
            "all_preflight_product_other_nonnull_memberships_retained": True,
        },
        "typed_missing_boundary": {
            "source_field": PRODUCT_OTHER_SOURCE.field,
            "typed_set_sha256": product_other["typed_set_sha256"],
            "sql_null_typed_distinct_presence": product_other[
                "sql_null_typed_presence"
            ],
            "sql_null_semantic_rows_created": 0,
            "sql_null_string_sentinel_created": False,
            "physical_null_contexts_deferred_to_query202": True,
        },
        "semantic_contract": {
            "dimensions": list(SEMANTIC_DIMENSIONS),
            "status_values": sorted(SEMANTIC_STATUSES),
            "initial_status": "uncertain",
            "review_status_values": sorted(REVIEW_STATUSES),
            "mapping_group_requires_explicit_evidence": True,
            "evidence_path_creates_separate_semantic_decision": False,
        },
        "records": records,
        "formal_guards": {guard: False for guard in FORMAL_GUARDS},
    }


def _validate_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ) or len(value) != len(set(value)):
        raise ProductReviewLedgerError(label + ".unique_nonblank_string_list")
    return value


def _validate_review_record(
    record: Any,
    spec: SourceSpec,
    expected_raw: str,
    expected_lineage: Mapping[str, Any],
    source_type: str,
    index: int,
    *,
    require_initial: bool,
) -> tuple[str, str]:
    label = f"ledger.record_{index}"
    if not isinstance(record, Mapping) or set(record) != {
        "lineage", "raw_value", "private_keys", "semantic_decisions",
        "review", "mapping_group",
    }:
        raise ProductReviewLedgerError(label + ".exact_schema")
    lineage = record["lineage"]
    if lineage != dict(expected_lineage):
        raise ProductReviewLedgerError(label + ".exact_source_lineage")
    raw_value = record["raw_value"]
    if not isinstance(raw_value, Mapping) or set(raw_value) != {
        "state", "exact_raw_name"
    } or raw_value.get("state") != "nonnull":
        raise ProductReviewLedgerError(label + ".typed_nonnull_only")
    raw = _validated_raw(raw_value.get("exact_raw_name"), label)
    if raw != expected_raw:
        raise ProductReviewLedgerError(label + ".exact_source_raw_membership")
    private_keys = record["private_keys"]
    expected_keys = {
        "ledger_key_sha256": _hash_parts((
            LEDGER_SCHEMA_VERSION,
            source_type,
            spec.evidence_path,
            raw,
        )),
        "canonical_semantic_key_sha256": _hash_parts((
            "k-product-canonical-semantic-key-v1", spec.field, raw
        )),
    }
    if private_keys != expected_keys:
        raise ProductReviewLedgerError(label + ".private_keys_recomputed")

    semantics = record["semantic_decisions"]
    if not isinstance(semantics, Mapping) or set(semantics) != set(
        SEMANTIC_DIMENSIONS
    ):
        raise ProductReviewLedgerError(label + ".five_semantic_dimensions")
    nonuncertain = False
    for dimension in SEMANTIC_DIMENSIONS:
        decision = semantics[dimension]
        if not isinstance(decision, Mapping) or set(decision) != {
            "status", "value", "evidence_refs"
        }:
            raise ProductReviewLedgerError(label + f".{dimension}.exact_schema")
        status = decision.get("status")
        if status not in SEMANTIC_STATUSES:
            raise ProductReviewLedgerError(label + f".{dimension}.known_status")
        evidence_refs = _validate_string_list(
            decision.get("evidence_refs"), label + f".{dimension}.evidence_refs"
        )
        if status != "uncertain":
            nonuncertain = True
            if not evidence_refs:
                raise ProductReviewLedgerError(label + f".{dimension}.evidence_required")
        if require_initial and (
            status != "uncertain" or decision.get("value") is not None or evidence_refs
        ):
            raise ProductReviewLedgerError(label + ".initial_all_uncertain")

    review = record["review"]
    if not isinstance(review, Mapping) or set(review) != {
        "status", "reviewer_or_method", "reviewed_at_utc", "rationale"
    } or review.get("status") not in REVIEW_STATUSES:
        raise ProductReviewLedgerError(label + ".review_schema")
    review_status = review["status"]
    if review_status == "unreviewed":
        if (
            review.get("reviewer_or_method") is not None
            or review.get("reviewed_at_utc") is not None
            or review.get("rationale") is not None
            or nonuncertain
        ):
            raise ProductReviewLedgerError(label + ".unreviewed_is_untouched")
    else:
        if (
            not isinstance(review.get("reviewer_or_method"), str)
            or not review["reviewer_or_method"].strip()
            or not _valid_timestamp(review.get("reviewed_at_utc"))
            or not isinstance(review.get("rationale"), str)
            or not review["rationale"].strip()
        ):
            raise ProductReviewLedgerError(label + ".review_provenance_complete")
    if require_initial and review_status != "unreviewed":
        raise ProductReviewLedgerError(label + ".initial_unreviewed")

    mapping_group = record["mapping_group"]
    if not isinstance(mapping_group, Mapping) or set(mapping_group) != {
        "id", "evidence_refs"
    }:
        raise ProductReviewLedgerError(label + ".mapping_group_schema")
    group_id = mapping_group.get("id")
    group_refs = _validate_string_list(
        mapping_group.get("evidence_refs"), label + ".mapping_group.evidence_refs"
    )
    if group_id is None:
        if group_refs:
            raise ProductReviewLedgerError(label + ".mapping_group_null_without_refs")
    elif not isinstance(group_id, str) or not group_id.strip() or not group_refs:
        raise ProductReviewLedgerError(label + ".mapping_group_explicit_evidence")
    if require_initial and (group_id is not None or group_refs):
        raise ProductReviewLedgerError(label + ".initial_no_mapping_group")
    return review_status, "present" if group_id is not None else "absent"


def validate_review_ledger(
    ledger: Mapping[str, Any],
    q201_discovery: Mapping[str, Any],
    preflight_private_values: Mapping[str, Any],
    expected_input_hashes: Mapping[str, str],
    *,
    expected_source_counts: Mapping[str, int] = EXPECTED_SOURCE_COUNTS,
    expected_q200_counts: Mapping[str, int] = EXPECTED_Q200_COUNTS,
    expected_product_other_nonnull: int = EXPECTED_PRODUCT_OTHER_NONNULL,
    require_initial: bool = False,
) -> dict[str, Any]:
    """Validate the 33,723 Q201 baseline and 34,565 extended universe."""
    if set(ledger) != {
        "schema_version", "ledger_schema_version", "component_id",
        "artifact_role", "created_at_utc", "input_hashes", "source_contract",
        "typed_missing_boundary", "semantic_contract", "records", "formal_guards",
    }:
        raise ProductReviewLedgerError("ledger.exact_top_level_schema")
    if (
        ledger.get("schema_version") != 1
        or ledger.get("ledger_schema_version") != LEDGER_SCHEMA_VERSION
        or ledger.get("component_id") != COMPONENT_ID
        or ledger.get("artifact_role")
        != "private_extended_product_semantic_review_ledger"
        or not _valid_timestamp(ledger.get("created_at_utc"))
        or ledger.get("input_hashes") != dict(expected_input_hashes)
    ):
        raise ProductReviewLedgerError("ledger.frozen_contract_and_inputs")
    validated_q201 = _validate_q201_discovery(
        q201_discovery,
        expected_source_counts=expected_source_counts,
        expected_q200_counts=expected_q200_counts,
    )
    product_other = _validate_preflight_product_other(
        preflight_private_values,
        expected_nonnull_count=expected_product_other_nonnull,
        expected_typed_set_sha256=expected_input_hashes[
            "product_description_other_typed_set_sha256"
        ],
    )
    expected_source_contract = {
        "q201_baseline_memberships": validated_q201["total"],
        "preflight_product_description_other_nonnull_memberships": product_other[
            "nonnull_distinct_values"
        ],
        "extended_nonnull_semantic_memberships": (
            validated_q201["total"] + product_other["nonnull_distinct_values"]
        ),
        "raw_value_state_required": "nonnull",
        "sql_null_records_allowed": False,
        "sql_null_string_sentinel_allowed": False,
        "empty_string_is_nonnull": True,
        "normalization_establishes_identity": False,
        "lexical_review_stratum_is_inclusion_rule": False,
        "all_q201_memberships_retained": True,
        "all_preflight_product_other_nonnull_memberships_retained": True,
    }
    expected_semantic_contract = {
        "dimensions": list(SEMANTIC_DIMENSIONS),
        "status_values": sorted(SEMANTIC_STATUSES),
        "initial_status": "uncertain",
        "review_status_values": sorted(REVIEW_STATUSES),
        "mapping_group_requires_explicit_evidence": True,
        "evidence_path_creates_separate_semantic_decision": False,
    }
    if ledger.get("source_contract") != expected_source_contract:
        raise ProductReviewLedgerError("ledger.typed_nonnull_source_contract")
    if ledger.get("typed_missing_boundary") != {
        "source_field": PRODUCT_OTHER_SOURCE.field,
        "typed_set_sha256": product_other["typed_set_sha256"],
        "sql_null_typed_distinct_presence": 1,
        "sql_null_semantic_rows_created": 0,
        "sql_null_string_sentinel_created": False,
        "physical_null_contexts_deferred_to_query202": True,
    }:
        raise ProductReviewLedgerError("ledger.typed_sql_null_boundary_metadata")
    if ledger.get("semantic_contract") != expected_semantic_contract:
        raise ProductReviewLedgerError("ledger.semantic_contract")
    guards = ledger.get("formal_guards")
    if (
        not isinstance(guards, Mapping)
        or set(guards) != set(FORMAL_GUARDS)
        or any(guards[key] is not False for key in FORMAL_GUARDS)
    ):
        raise ProductReviewLedgerError("ledger.all_formal_guards_false")

    records = ledger.get("records")
    extended_total = validated_q201["total"] + product_other["nonnull_distinct_values"]
    if not isinstance(records, list) or len(records) != extended_total:
        raise ProductReviewLedgerError("ledger.all_extended_memberships_conserved")
    review_counts: Counter[str] = Counter()
    group_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    overlap = 0
    cursor = 0
    ledger_keys: set[str] = set()
    semantic_keys: set[str] = set()
    for spec in SOURCES:
        for q201_record in validated_q201["sources"][spec.key]:
            expected_lineage = {
                "source_type": "query201_full_nonnull_vocabulary",
                "evidence_path": spec.evidence_path,
                "source_field": spec.field,
                "source_key": spec.key,
                "origin_component": "D005-K-SOURCE-DISCOVERY-v1",
                "q201_review_stratum": q201_record["review_stratum"],
                "q201_q200_member": q201_record["q200_member"],
                "preflight_nonnull_substate": None,
                "preflight_exact_row_count": None,
                "source_policy_status": "unresolved",
                "lexical_review_stratum_is_inclusion_rule": False,
            }
            review_status, group_status = _validate_review_record(
                records[cursor], spec, q201_record["raw_name"], expected_lineage,
                "query201_full_nonnull_vocabulary", cursor,
                require_initial=require_initial,
            )
            review_counts[review_status] += 1
            group_counts[group_status] += 1
            source_counts[spec.key] += 1
            overlap += int(q201_record["q200_member"])
            ledger_keys.add(records[cursor]["private_keys"]["ledger_key_sha256"])
            semantic_keys.add(
                records[cursor]["private_keys"]["canonical_semantic_key_sha256"]
            )
            cursor += 1
    q201_total = cursor
    negative = q201_total - overlap
    for preflight_record in product_other["records"]:
        expected_lineage = {
            "source_type": "mapping_preflight_full_typed_vocabulary",
            "evidence_path": PRODUCT_OTHER_SOURCE.evidence_path,
            "source_field": PRODUCT_OTHER_SOURCE.field,
            "source_key": PRODUCT_OTHER_SOURCE.key,
            "origin_component": "D005-K-MAPPING-PREFLIGHT-v1",
            "q201_review_stratum": None,
            "q201_q200_member": None,
            "preflight_nonnull_substate": preflight_record["nonnull_substate"],
            "preflight_exact_row_count": preflight_record["exact_row_count"],
            "source_policy_status": "unresolved",
            "lexical_review_stratum_is_inclusion_rule": False,
        }
        review_status, group_status = _validate_review_record(
            records[cursor], PRODUCT_OTHER_SOURCE, preflight_record["raw_name"],
            expected_lineage, "mapping_preflight_full_typed_vocabulary", cursor,
            require_initial=require_initial,
        )
        review_counts[review_status] += 1
        group_counts[group_status] += 1
        source_counts[PRODUCT_OTHER_SOURCE.key] += 1
        ledger_keys.add(records[cursor]["private_keys"]["ledger_key_sha256"])
        semantic_keys.add(
            records[cursor]["private_keys"]["canonical_semantic_key_sha256"]
        )
        cursor += 1
    if (
        q201_total != validated_q201["total"]
        or overlap != validated_q201["q200_overlap"]
        or negative != validated_q201["negative_space"]
        or cursor != extended_total
        or len(ledger_keys) != extended_total
        or len(semantic_keys) != extended_total
    ):
        raise ProductReviewLedgerError("ledger.global_conservation")
    return {
        "q201_baseline_source_value_memberships": q201_total,
        "q201_query200_overlap_memberships": overlap,
        "q201_negative_space_memberships": negative,
        "preflight_product_description_other_nonnull_memberships": product_other[
            "nonnull_distinct_values"
        ],
        "preflight_product_description_other_sql_null_typed_presence": product_other[
            "sql_null_typed_presence"
        ],
        "extended_nonnull_semantic_memberships": cursor,
        "source_counts": {
            spec.key: source_counts[spec.key] for spec in EXTENDED_SOURCES
        },
        "review_status_counts": {
            status: review_counts[status] for status in sorted(REVIEW_STATUSES)
        },
        "mapping_group_memberships": group_counts["present"],
    }


def build_aggregate_summary(
    ledger: Mapping[str, Any],
    counts: Mapping[str, Any],
    *,
    ledger_sha256: str,
) -> dict[str, Any]:
    """Create a strict aggregate-only summary of a validated initial ledger."""
    if not isinstance(ledger_sha256, str) or _SHA256.fullmatch(ledger_sha256) is None:
        raise ProductReviewLedgerError("summary.ledger_hash")
    total = counts["extended_nonnull_semantic_memberships"]
    return {
        "schema_version": 1,
        "artifact": ARTIFACT_NAME,
        "component_id": COMPONENT_ID,
        "status": "initial_review_ledger_created",
        "aggregate_counts": {
            "q201_baseline": {
                "source_value_memberships": counts[
                    "q201_baseline_source_value_memberships"
                ],
                "query200_overlap_memberships": counts[
                    "q201_query200_overlap_memberships"
                ],
                "negative_space_memberships": counts[
                    "q201_negative_space_memberships"
                ],
            },
            "preflight_extension": {
                "product_description_other_nonnull_memberships": counts[
                    "preflight_product_description_other_nonnull_memberships"
                ],
                "product_description_other_sql_null_typed_presence": counts[
                    "preflight_product_description_other_sql_null_typed_presence"
                ],
                "sql_null_semantic_rows_created": 0,
            },
            "extended_nonnull_semantic_memberships": total,
            "source_counts": dict(counts["source_counts"]),
            "raw_value_state_counts": {"nonnull": total, "null": 0},
            "semantic_status_counts": {
                dimension: {
                    "supported": 0,
                    "refuted": 0,
                    "uncertain": total,
                }
                for dimension in SEMANTIC_DIMENSIONS
            },
            "review_status_counts": dict(counts["review_status_counts"]),
            "mapping_group_memberships": counts["mapping_group_memberships"],
        },
        "conservation": {
            "all_q201_memberships_retained": True,
            "all_preflight_product_description_other_nonnull_memberships_retained": True,
            "query200_overlap_plus_negative_equals_total": True,
            "q201_baseline_not_redefined_by_extension": True,
            "extended_total_equals_q201_plus_product_other_nonnull": True,
            "five_semantic_dimensions_separate": True,
            "all_initial_semantic_statuses_uncertain": True,
            "all_initial_review_statuses_unreviewed": True,
            "lexical_review_strata_used_for_selection": False,
            "sql_null_semantic_records_created": False,
            "sql_null_typed_presence_retained_as_boundary_metadata": True,
            "string_sentinel_used_for_sql_null": False,
        },
        "whole_file_hashes": {
            **dict(ledger["input_hashes"]),
            "private_ledger_sha256": ledger_sha256,
        },
        "formal_guards": dict(ledger["formal_guards"]),
        "privacy": {
            "aggregate_only": True,
            "raw_values_emitted": False,
            "per_record_hashes_emitted": False,
            "patient_identifiers_or_timestamps_emitted": False,
            "private_ledger_required_for_review": True,
        },
        "limitations": (
            "This artifact prepares an all-uncertain private review ledger. "
            "It does not decide product identity, route, source policy, action, "
            "episode, label, or cohort."
        ),
    }


def create_initial_review_artifact(root: Path) -> dict[str, Any]:
    """Generate, validate and persist the accepted initial ledger privately."""
    q201, preflight, lineage = load_accepted_inputs(root)
    ledger = build_initial_review_ledger(q201, preflight, lineage)
    counts = validate_review_ledger(
        ledger, q201, preflight, lineage, require_initial=True
    )
    ledger_raw = _json_payload(ledger)
    ledger_hash = _sha_bytes(ledger_raw)
    summary = build_aggregate_summary(ledger, counts, ledger_sha256=ledger_hash)
    summary_raw = _json_payload(summary)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    parent = root / DEFAULT_OUTPUT_PARENT
    parent.mkdir(parents=True, exist_ok=True)
    os.chmod(parent, 0o700)
    directory = parent / timestamp
    directory.mkdir(mode=0o700)
    os.chmod(directory, 0o700)
    ledger_path = directory / LEDGER_FILENAME
    summary_path = directory / SUMMARY_FILENAME
    try:
        _write_private(ledger_path, ledger_raw)
        _write_private(summary_path, summary_raw)
    except BaseException:
        ledger_path.unlink(missing_ok=True)
        summary_path.unlink(missing_ok=True)
        try:
            directory.rmdir()
        except OSError:
            pass
        raise
    return {
        "status": "complete",
        "artifact_directory": str(directory.relative_to(root)),
        "private_ledger": str(ledger_path.relative_to(root)),
        "aggregate_summary": str(summary_path.relative_to(root)),
        "q201_baseline_source_value_memberships": counts[
            "q201_baseline_source_value_memberships"
        ],
        "q201_query200_overlap_memberships": counts[
            "q201_query200_overlap_memberships"
        ],
        "q201_negative_space_memberships": counts[
            "q201_negative_space_memberships"
        ],
        "preflight_product_description_other_nonnull_memberships": counts[
            "preflight_product_description_other_nonnull_memberships"
        ],
        "preflight_product_description_other_sql_null_typed_presence": counts[
            "preflight_product_description_other_sql_null_typed_presence"
        ],
        "extended_nonnull_semantic_memberships": counts[
            "extended_nonnull_semantic_memberships"
        ],
        "private_ledger_sha256": ledger_hash,
        "aggregate_summary_sha256": _sha_bytes(summary_raw),
        "formal_guards_all_false": True,
    }


def validate_review_ledger_file(
    root: Path,
    path: Path,
    *,
    require_initial: bool = False,
) -> dict[str, Any]:
    """Validate a private initial or later reviewed ledger without raw output."""
    q201, preflight, lineage = load_accepted_inputs(root)
    ledger, raw = _read_private_json(path, "ledger")
    counts = validate_review_ledger(
        ledger, q201, preflight, lineage, require_initial=require_initial
    )
    return {
        "status": "passed",
        "ledger_sha256": _sha_bytes(raw),
        **counts,
        "formal_guards_all_false": True,
    }
