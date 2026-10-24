"""Independent offline audit for the private product-semantic review ledger.

The auditor intentionally does not import the generator or its validator.  It
recomputes the typed keys, exact Query-201 membership sequence, all-uncertain
initial state, aggregate summary, input hashes, modes, and false guards.
Audit output contains no controlled-vocabulary value or per-record hash.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any


AUDIT_NAME = "potassium_product_semantic_review_ledger_offline_audit"
ARTIFACT_NAME = "potassium_product_semantic_review"
LEDGER_FILENAME = ARTIFACT_NAME + ".initial-ledger.json"
SUMMARY_FILENAME = ARTIFACT_NAME + ".aggregate-summary.json"
AUDIT_FILENAME = "audit-summary.json"
LEDGER_SCHEMA_VERSION = "k-product-review-ledger-v1"
COMPONENT_ID = "D005-K-PRODUCT-MAPPING-v1"

Q201_DIRECTORY = Path("artifacts/profiling/20261011T182244.083389Z")
Q201_FILES = {
    "manifest": "manifest.json",
    "audit": "audit-summary.json",
    "summary": "potassium_full_source_vocabulary_discovery.aggregate-summary.json",
    "discovery": "potassium_full_source_vocabulary_discovery.discovery.json",
}
Q201_HASHES = {
    "manifest": "fe13a910a590df49e26b8e71770735d100af7f9e474cf9769a619c0b2cc6fa44",
    "audit": "a7aa9b35d4e408bbeda6b4e024588e3083fc7f13b976492b624d21a390946428",
    "summary": "784c618be25f4e243f5bda89619bbb6d004c8eee10fc40b6327e311c83fc30ea",
    "discovery": "62731e7dcadf82b95a55e3afd7f2790455320d1c642f9ca307b2574672760d18",
}
PREFLIGHT_DIRECTORY = Path("artifacts/profiling/20261011T190426.934406Z")
PREFLIGHT_FILES = {
    "manifest": "manifest.json",
    "audit": "audit-summary.json",
    "summary": "potassium_mapping_preflight.aggregate-summary.json",
    "private_values": "potassium_mapping_preflight.private-values.json",
}
PREFLIGHT_HASHES = {
    "manifest": "bdfcb78849eadb1b9eafca226fe49c7e70390f45ee0f3ef34c8e92899557c880",
    "audit": "c96b7bed50a7b29ac7f8bfc14ed05b03394ad3c996d2c4b2c891ccbf964d024e",
    "summary": "079a8b774773a039977d21aad88e128d0d3658483268ded38aa931842fa2a220",
    "private_values": "82e7d89cca2d756d5af85c038618f880fb88c378ee8b271e43181989faabcc83",
}
PRODUCT_OTHER_TYPED_SET_SHA256 = (
    "0105f73cef307cc11b93e1d9d657d43a278c66c3c06ef31e5123db377e11dd4e"
)
MAPPING_CONFIG = Path("config/preregistrations/d005_potassium_product_mapping.toml")
MAPPING_REDUCER = Path("src/april_repro/product_mapping_contract.py")
MAPPING_CONFIG_SHA256 = (
    "960e0e68d848613d2b75c0e2a5afa6db9c853bdbf24a3a2f214bdcccb94df9ee"
)
MAPPING_REDUCER_SHA256 = (
    "27bd346a740eb2578431f2cda997d76439e2f5772a94bd8d9b0c060a26f0b11e"
)

SEMANTIC_DIMENSIONS = (
    "product_identity",
    "dosage_form",
    "treatment_intent",
    "potassium_content",
    "meq_convertibility",
)
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
SOURCES = (
    (
        "emar_medication",
        "mimiciv_hosp.emar.medication",
        "query201/emar_medication/full_nonnull_distinct",
    ),
    (
        "detail_product_description",
        "mimiciv_hosp.emar_detail.product_description",
        "query201/detail_product_description/full_nonnull_distinct",
    ),
    (
        "pharmacy_medication",
        "mimiciv_hosp.pharmacy.medication",
        "query201/pharmacy_medication/full_nonnull_distinct",
    ),
    (
        "prescription_drug",
        "mimiciv_hosp.prescriptions.drug",
        "query201/prescription_drug/full_nonnull_distinct",
    ),
)
PRODUCT_OTHER_SOURCE = (
    "detail_product_description_other",
    "mimiciv_hosp.emar_detail.product_description_other",
    "mapping_preflight/detail_product_description_other/full_typed_distinct",
)
EXTENDED_SOURCES = SOURCES + (PRODUCT_OTHER_SOURCE,)
SOURCE_COUNTS = {
    "emar_medication": 5_045,
    "detail_product_description": 6_692,
    "pharmacy_medication": 11_059,
    "prescription_drug": 10_927,
}
Q200_COUNTS = {
    "emar_medication": 23,
    "detail_product_description": 79,
    "pharmacy_medication": 45,
    "prescription_drug": 52,
}
TOTAL = 33_723
Q200_OVERLAP = 199
NEGATIVE_SPACE = 33_524
PRODUCT_OTHER_NONNULL = 842
PRODUCT_OTHER_SQL_NULL_TYPED_PRESENCE = 1
EXTENDED_TOTAL = 34_565
MAX_JSON_BYTES = 256 * 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ProductReviewLedgerAuditError(RuntimeError):
    """A safe audit failure containing no private value."""


class Checks:
    def __init__(self) -> None:
        self.total = 0
        self.failed: list[str] = []

    def require(self, condition: bool, name: str) -> None:
        self.total += 1
        if not condition:
            if name not in self.failed:
                self.failed.append(name)
            raise ProductReviewLedgerAuditError(name)


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


def _valid_timestamp(value: Any) -> bool:
    """Require an ISO-8601 timestamp with an explicit timezone."""
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _git_ignored(root: Path, path: Path) -> bool:
    """Ask Git whether a private artifact path is ignored without echoing it."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    try:
        completed = subprocess.run(
            ["git", "check-ignore", "--quiet", "--", str(relative)],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _read_unique_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink():
        raise ProductReviewLedgerAuditError(label + ".regular_file")
    raw = path.read_bytes()
    if len(raw) > MAX_JSON_BYTES:
        raise ProductReviewLedgerAuditError(label + ".byte_limit")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ProductReviewLedgerAuditError(label + ".duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(_: str) -> None:
        raise ProductReviewLedgerAuditError(label + ".nonfinite_number")

    try:
        value = json.loads(
            raw,
            object_pairs_hook=unique,
            parse_constant=invalid_constant,
        )
    except ProductReviewLedgerAuditError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductReviewLedgerAuditError(label + ".valid_json") from exc
    if not isinstance(value, dict):
        raise ProductReviewLedgerAuditError(label + ".object")
    return value, raw


def _hash_parts(parts: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        if not isinstance(part, str):
            raise ProductReviewLedgerAuditError("audit.hash_parts.text")
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


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


def _input_hashes() -> dict[str, str]:
    return {
        "q201_manifest_sha256": Q201_HASHES["manifest"],
        "q201_audit_sha256": Q201_HASHES["audit"],
        "q201_summary_sha256": Q201_HASHES["summary"],
        "q201_discovery_sha256": Q201_HASHES["discovery"],
        "preflight_manifest_sha256": PREFLIGHT_HASHES["manifest"],
        "preflight_audit_sha256": PREFLIGHT_HASHES["audit"],
        "preflight_summary_sha256": PREFLIGHT_HASHES["summary"],
        "preflight_private_values_sha256": PREFLIGHT_HASHES["private_values"],
        "product_description_other_typed_set_sha256": (
            PRODUCT_OTHER_TYPED_SET_SHA256
        ),
        "mapping_config_sha256": MAPPING_CONFIG_SHA256,
        "mapping_reducer_sha256": MAPPING_REDUCER_SHA256,
    }


def _typed_set_sha256(source_field: str, records: Sequence[Mapping[str, Any]]) -> str:
    field_bytes = source_field.encode("utf-8")
    null_seen = False
    values: list[bytes] = []
    for record in records:
        is_null = record.get("raw_is_null")
        raw = record.get("raw_value")
        count = record.get("exact_row_count")
        if type(count) is not int or count < 1:
            raise ProductReviewLedgerAuditError("preflight.record.positive_frequency")
        if is_null is True and raw is None:
            if null_seen:
                raise ProductReviewLedgerAuditError("preflight.record.single_null")
            null_seen = True
        elif is_null is False and isinstance(raw, str):
            encoded = raw.encode("utf-8")
            if b"\x00" in encoded or len(encoded) > 16 * 1024:
                raise ProductReviewLedgerAuditError("preflight.record.raw_bounds")
            values.append(encoded)
        else:
            raise ProductReviewLedgerAuditError("preflight.record.typed_state")
    if len(values) != len(set(values)):
        raise ProductReviewLedgerAuditError("preflight.record.unique_nonnull")
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


def _preflight_product_other(
    private_values: Mapping[str, Any], checks: Checks, *, expected_nonnull: int,
    expected_typed_set_sha256: str,
) -> dict[str, Any]:
    sources = private_values.get("sources")
    source = (
        sources.get(PRODUCT_OTHER_SOURCE[0])
        if isinstance(sources, Mapping)
        else None
    )
    checks.require(
        private_values.get("query") == "potassium_mapping_preflight"
        and private_values.get("product_identity_decided") is False
        and private_values.get("final_source_policy") is False
        and private_values.get("route_mapping_created") is False
        and isinstance(source, Mapping),
        "preflight.private_neutral_product_other_present",
    )
    records = source.get("records")
    checks.require(
        source.get("source_field") == PRODUCT_OTHER_SOURCE[1]
        and source.get("field_role") == "product_description_other"
        and source.get("typed_distinct_values") == expected_nonnull + 1
        and source.get("nonnull_distinct_values") == expected_nonnull
        and source.get("sql_null_present") is True
        and isinstance(records, list)
        and len(records) == expected_nonnull + 1,
        "preflight.product_other.842_plus_1_contract",
    )
    nulls = [item for item in records if isinstance(item, Mapping) and item.get("raw_is_null") is True]
    nonnull = [item for item in records if isinstance(item, Mapping) and item.get("raw_is_null") is False]
    checks.require(
        len(nulls) == 1 and len(nonnull) == expected_nonnull,
        "preflight.product_other.typed_partition",
    )
    checks.require(
        nulls[0].get("raw_value") is None
        and nulls[0].get("nonnull_substate") is None
        and nulls[0].get("raw_utf8_bytes") == 0
        and nulls[0].get("exact_row_count") == source.get("sql_null_rows"),
        "preflight.product_other.null_is_boundary_metadata",
    )
    typed_hash = _typed_set_sha256(PRODUCT_OTHER_SOURCE[1], records)
    checks.require(
        typed_hash == expected_typed_set_sha256
        and source.get("typed_set_sha256") == typed_hash,
        "preflight.product_other.typed_set_hash_recomputed",
    )
    validated: list[dict[str, Any]] = []
    for index, record in enumerate(nonnull):
        raw = record.get("raw_value")
        count = record.get("exact_row_count")
        substate = record.get("nonnull_substate")
        expected_substate = (
            "empty_string" if raw == ""
            else "whitespace_only" if isinstance(raw, str) and raw.isspace()
            else "nonblank"
        )
        checks.require(
            isinstance(raw, str)
            and type(count) is int and count > 0
            and record.get("raw_utf8_bytes") == len(raw.encode("utf-8"))
            and substate == expected_substate,
            f"preflight.product_other.record_{index}.exact_nonnull",
        )
        validated.append({
            "raw_name": raw,
            "nonnull_substate": substate,
            "exact_row_count": count,
        })
    checks.require(
        [item["raw_name"] for item in validated]
        == sorted(item["raw_name"] for item in validated),
        "preflight.product_other.deterministic_order",
    )
    return {
        "records": validated,
        "nonnull": len(validated),
        "sql_null_typed_presence": 1,
        "typed_set_sha256": typed_hash,
    }


def _audit_initial_payloads(
    ledger: Mapping[str, Any],
    summary: Mapping[str, Any],
    q201: Mapping[str, Any],
    preflight_private_values: Mapping[str, Any],
    ledger_sha256: str,
    checks: Checks,
    *,
    input_hashes: Mapping[str, str],
    source_counts: Mapping[str, int],
    q200_counts: Mapping[str, int],
    product_other_nonnull: int = PRODUCT_OTHER_NONNULL,
) -> dict[str, Any]:
    """Pure independent recomputation used by the real audit and tests."""
    checks.require(
        set(ledger) == {
            "schema_version", "ledger_schema_version", "component_id",
            "artifact_role", "created_at_utc", "input_hashes", "source_contract",
            "typed_missing_boundary", "semantic_contract", "records", "formal_guards",
        },
        "ledger.exact_top_level_schema",
    )
    checks.require(
        ledger.get("schema_version") == 1
        and ledger.get("ledger_schema_version") == LEDGER_SCHEMA_VERSION
        and ledger.get("component_id") == COMPONENT_ID
        and ledger.get("artifact_role")
        == "private_extended_product_semantic_review_ledger"
        and _valid_timestamp(ledger.get("created_at_utc"))
        and ledger.get("input_hashes") == dict(input_hashes),
        "ledger.frozen_contract_and_input_hashes",
    )
    product_other = _preflight_product_other(
        preflight_private_values,
        checks,
        expected_nonnull=product_other_nonnull,
        expected_typed_set_sha256=input_hashes[
            "product_description_other_typed_set_sha256"
        ],
    )
    checks.require(
        ledger.get("source_contract") == {
            "q201_baseline_memberships": sum(source_counts.values()),
            "preflight_product_description_other_nonnull_memberships": product_other[
                "nonnull"
            ],
            "extended_nonnull_semantic_memberships": (
                sum(source_counts.values()) + product_other["nonnull"]
            ),
            "raw_value_state_required": "nonnull",
            "sql_null_records_allowed": False,
            "sql_null_string_sentinel_allowed": False,
            "empty_string_is_nonnull": True,
            "normalization_establishes_identity": False,
            "lexical_review_stratum_is_inclusion_rule": False,
            "all_q201_memberships_retained": True,
            "all_preflight_product_other_nonnull_memberships_retained": True,
        },
        "ledger.typed_nonnull_source_contract",
    )
    checks.require(
        ledger.get("typed_missing_boundary") == {
            "source_field": PRODUCT_OTHER_SOURCE[1],
            "typed_set_sha256": product_other["typed_set_sha256"],
            "sql_null_typed_distinct_presence": 1,
            "sql_null_semantic_rows_created": 0,
            "sql_null_string_sentinel_created": False,
            "physical_null_contexts_deferred_to_query202": True,
        },
        "ledger.typed_missing_boundary_exact",
    )
    checks.require(
        ledger.get("semantic_contract") == {
            "dimensions": list(SEMANTIC_DIMENSIONS),
            "status_values": ["refuted", "supported", "uncertain"],
            "initial_status": "uncertain",
            "review_status_values": ["reviewed", "unreviewed"],
            "mapping_group_requires_explicit_evidence": True,
            "evidence_path_creates_separate_semantic_decision": False,
        },
        "ledger.semantic_contract",
    )
    guards = ledger.get("formal_guards")
    checks.require(
        isinstance(guards, dict)
        and set(guards) == set(FORMAL_GUARDS)
        and all(guards[key] is False for key in FORMAL_GUARDS),
        "ledger.all_formal_guards_false",
    )
    sources = q201.get("sources")
    checks.require(
        q201.get("query") == "potassium_full_source_vocabulary_discovery"
        and q201.get("all_source_policy_statuses") == "unresolved"
        and isinstance(sources, dict)
        and set(sources) == {item[0] for item in SOURCES},
        "q201.fixed_source_contract",
    )
    records = ledger.get("records")
    expected_total = sum(source_counts.values()) + product_other["nonnull"]
    checks.require(
        isinstance(records, list) and len(records) == expected_total,
        "ledger.membership_count",
    )

    cursor = 0
    overlap = 0
    derived_source_counts: dict[str, int] = {}
    private_ledger_keys: set[str] = set()
    private_semantic_keys: set[str] = set()
    for source_key, source_field, evidence_path in SOURCES:
        source = sources[source_key]
        values = source.get("values") if isinstance(source, Mapping) else None
        checks.require(
            isinstance(source, Mapping)
            and source.get("source_field") == source_field
            and isinstance(values, list)
            and len(values) == source_counts[source_key]
            and source.get("distinct_nonnull_values") == len(values)
            and source.get("q200_dictionary_values") == q200_counts[source_key],
            f"q201.{source_key}.source_contract",
        )
        raw_seen: set[str] = set()
        source_overlap = 0
        for local_index, q201_record in enumerate(values):
            prefix = f"ledger.record_{cursor}"
            checks.require(isinstance(q201_record, Mapping), prefix + ".q201_record")
            raw = q201_record.get("raw_name")
            checks.require(isinstance(raw, str), prefix + ".q201_raw_text")
            checks.require(raw not in raw_seen, f"q201.{source_key}.raw_unique")
            raw_seen.add(raw)
            q200_member = q201_record.get("q200_member")
            stratum = q201_record.get("review_stratum")
            checks.require(type(q200_member) is bool, prefix + ".q200_boolean")
            checks.require(
                q201_record.get("source_policy_status") == "unresolved"
                and q201_record.get("source_review_stratum_is_final_policy") is False,
                prefix + ".q201_lexical_not_policy",
            )
            record = records[cursor]
            checks.require(
                isinstance(record, dict)
                and set(record) == {
                    "lineage", "raw_value", "private_keys", "semantic_decisions",
                    "review", "mapping_group",
                },
                prefix + ".exact_schema",
            )
            checks.require(
                record.get("lineage") == {
                    "source_type": "query201_full_nonnull_vocabulary",
                    "evidence_path": evidence_path,
                    "source_field": source_field,
                    "source_key": source_key,
                    "origin_component": "D005-K-SOURCE-DISCOVERY-v1",
                    "q201_review_stratum": stratum,
                    "q201_q200_member": q200_member,
                    "preflight_nonnull_substate": None,
                    "preflight_exact_row_count": None,
                    "source_policy_status": "unresolved",
                    "lexical_review_stratum_is_inclusion_rule": False,
                },
                prefix + ".exact_q201_lineage",
            )
            raw_value = record.get("raw_value")
            checks.require(
                isinstance(raw_value, dict)
                and set(raw_value) == {"state", "exact_raw_name"}
                and raw_value.get("state") == "nonnull"
                and raw_value.get("exact_raw_name") == raw,
                prefix + ".typed_exact_nonnull_raw",
            )
            expected_ledger_key = _hash_parts((
                LEDGER_SCHEMA_VERSION,
                "query201_full_nonnull_vocabulary",
                evidence_path,
                raw,
            ))
            expected_semantic_key = _hash_parts((
                "k-product-canonical-semantic-key-v1",
                source_field,
                raw,
            ))
            checks.require(
                record.get("private_keys") == {
                    "ledger_key_sha256": expected_ledger_key,
                    "canonical_semantic_key_sha256": expected_semantic_key,
                },
                prefix + ".private_keys_recomputed",
            )
            checks.require(
                expected_ledger_key not in private_ledger_keys,
                "ledger.private_ledger_keys_unique",
            )
            checks.require(
                expected_semantic_key not in private_semantic_keys,
                "ledger.canonical_semantic_keys_unique",
            )
            private_ledger_keys.add(expected_ledger_key)
            private_semantic_keys.add(expected_semantic_key)
            semantics = record.get("semantic_decisions")
            checks.require(
                isinstance(semantics, dict)
                and set(semantics) == set(SEMANTIC_DIMENSIONS),
                prefix + ".five_dimensions_exact",
            )
            for dimension in SEMANTIC_DIMENSIONS:
                checks.require(
                    semantics[dimension] == {
                        "status": "uncertain", "value": None, "evidence_refs": []
                    },
                    prefix + "." + dimension + ".initial_uncertain",
                )
            checks.require(
                record.get("review") == {
                    "status": "unreviewed",
                    "reviewer_or_method": None,
                    "reviewed_at_utc": None,
                    "rationale": None,
                },
                prefix + ".initial_unreviewed",
            )
            checks.require(
                record.get("mapping_group") == {"id": None, "evidence_refs": []},
                prefix + ".initial_no_mapping_group",
            )
            source_overlap += int(q200_member)
            overlap += int(q200_member)
            cursor += 1
        checks.require(
            source_overlap == q200_counts[source_key],
            f"q201.{source_key}.q200_overlap_conserved",
        )
        derived_source_counts[source_key] = len(values)
    q201_total = cursor
    negative = q201_total - overlap
    source_key, source_field, evidence_path = PRODUCT_OTHER_SOURCE
    for preflight_record in product_other["records"]:
        prefix = f"ledger.record_{cursor}"
        raw = preflight_record["raw_name"]
        record = records[cursor]
        checks.require(
            isinstance(record, dict)
            and set(record) == {
                "lineage", "raw_value", "private_keys", "semantic_decisions",
                "review", "mapping_group",
            },
            prefix + ".exact_schema",
        )
        checks.require(
            record.get("lineage") == {
                "source_type": "mapping_preflight_full_typed_vocabulary",
                "evidence_path": evidence_path,
                "source_field": source_field,
                "source_key": source_key,
                "origin_component": "D005-K-MAPPING-PREFLIGHT-v1",
                "q201_review_stratum": None,
                "q201_q200_member": None,
                "preflight_nonnull_substate": preflight_record[
                    "nonnull_substate"
                ],
                "preflight_exact_row_count": preflight_record[
                    "exact_row_count"
                ],
                "source_policy_status": "unresolved",
                "lexical_review_stratum_is_inclusion_rule": False,
            },
            prefix + ".exact_preflight_lineage",
        )
        checks.require(
            record.get("raw_value") == {
                "state": "nonnull", "exact_raw_name": raw
            },
            prefix + ".typed_exact_nonnull_raw",
        )
        expected_ledger_key = _hash_parts((
            LEDGER_SCHEMA_VERSION,
            "mapping_preflight_full_typed_vocabulary",
            evidence_path,
            raw,
        ))
        expected_semantic_key = _hash_parts((
            "k-product-canonical-semantic-key-v1", source_field, raw
        ))
        checks.require(
            record.get("private_keys") == {
                "ledger_key_sha256": expected_ledger_key,
                "canonical_semantic_key_sha256": expected_semantic_key,
            },
            prefix + ".private_keys_recomputed",
        )
        checks.require(
            expected_ledger_key not in private_ledger_keys,
            "ledger.private_ledger_keys_unique",
        )
        checks.require(
            expected_semantic_key not in private_semantic_keys,
            "ledger.canonical_semantic_keys_unique",
        )
        private_ledger_keys.add(expected_ledger_key)
        private_semantic_keys.add(expected_semantic_key)
        semantics = record.get("semantic_decisions")
        checks.require(
            isinstance(semantics, dict)
            and set(semantics) == set(SEMANTIC_DIMENSIONS),
            prefix + ".five_dimensions_exact",
        )
        for dimension in SEMANTIC_DIMENSIONS:
            checks.require(
                semantics[dimension] == {
                    "status": "uncertain", "value": None, "evidence_refs": []
                },
                prefix + "." + dimension + ".initial_uncertain",
            )
        checks.require(
            record.get("review") == {
                "status": "unreviewed",
                "reviewer_or_method": None,
                "reviewed_at_utc": None,
                "rationale": None,
            },
            prefix + ".initial_unreviewed",
        )
        checks.require(
            record.get("mapping_group") == {"id": None, "evidence_refs": []},
            prefix + ".initial_no_mapping_group",
        )
        cursor += 1
    derived_source_counts[source_key] = product_other["nonnull"]
    checks.require(cursor == expected_total, "ledger.extended_total_conserved")
    checks.require(
        len(private_ledger_keys) == expected_total
        and len(private_semantic_keys) == expected_total,
        "ledger.extended_private_keys_unique",
    )
    counts = {
        "q201_baseline_source_value_memberships": q201_total,
        "q201_query200_overlap_memberships": overlap,
        "q201_negative_space_memberships": negative,
        "preflight_product_description_other_nonnull_memberships": product_other[
            "nonnull"
        ],
        "preflight_product_description_other_sql_null_typed_presence": 1,
        "extended_nonnull_semantic_memberships": cursor,
        "source_counts": derived_source_counts,
    }

    expected_summary = {
        "schema_version": 1,
        "artifact": ARTIFACT_NAME,
        "component_id": COMPONENT_ID,
        "status": "initial_review_ledger_created",
        "aggregate_counts": {
            "q201_baseline": {
                "source_value_memberships": q201_total,
                "query200_overlap_memberships": overlap,
                "negative_space_memberships": negative,
            },
            "preflight_extension": {
                "product_description_other_nonnull_memberships": product_other[
                    "nonnull"
                ],
                "product_description_other_sql_null_typed_presence": 1,
                "sql_null_semantic_rows_created": 0,
            },
            "extended_nonnull_semantic_memberships": cursor,
            "source_counts": derived_source_counts,
            "raw_value_state_counts": {"nonnull": cursor, "null": 0},
            "semantic_status_counts": {
                dimension: {
                    "supported": 0,
                    "refuted": 0,
                    "uncertain": cursor,
                }
                for dimension in SEMANTIC_DIMENSIONS
            },
            "review_status_counts": {"reviewed": 0, "unreviewed": cursor},
            "mapping_group_memberships": 0,
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
            **dict(input_hashes),
            "private_ledger_sha256": ledger_sha256,
        },
        "formal_guards": {guard: False for guard in FORMAL_GUARDS},
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
    checks.require(summary == expected_summary, "summary.independently_recomputed_exact")
    checks.require(
        overlap + negative == q201_total,
        "ledger.q201_overlap_negative_conservation",
    )
    checks.require(
        q201_total + product_other["nonnull"] == cursor,
        "ledger.extended_conservation",
    )
    return counts


def audit_artifact(directory: Path, root: Path) -> tuple[dict[str, Any], Path]:
    """Audit one generated artifact directory and write a private safe report."""
    root = root.resolve()
    if not directory.is_absolute():
        directory = root / directory
    if directory.is_symlink():
        raise ProductReviewLedgerAuditError("artifact.directory")
    try:
        directory = directory.resolve(strict=True)
    except OSError as exc:
        raise ProductReviewLedgerAuditError("artifact.directory") from exc
    try:
        directory.relative_to(root)
    except ValueError as exc:
        raise ProductReviewLedgerAuditError("artifact.directory_within_repository") from exc
    if not directory.is_dir() or directory.is_symlink():
        raise ProductReviewLedgerAuditError("artifact.directory")
    checks = Checks()
    checks.require(_mode(directory) == "0700", "artifact.directory_mode_0700")
    ledger_path = directory / LEDGER_FILENAME
    summary_path = directory / SUMMARY_FILENAME
    output = directory / AUDIT_FILENAME
    entry_names = {entry.name for entry in directory.iterdir()}
    expected_without_audit = {LEDGER_FILENAME, SUMMARY_FILENAME}
    expected_with_audit = expected_without_audit | {AUDIT_FILENAME}
    checks.require(
        entry_names in (expected_without_audit, expected_with_audit),
        "artifact.exact_private_file_inventory",
    )
    checks.require(
        all(_git_ignored(root, path) for path in (directory, ledger_path, summary_path, output)),
        "artifact.paths_git_ignored",
    )
    checks.require(
        ledger_path.is_file() and not ledger_path.is_symlink(),
        "artifact.ledger_regular_file",
    )
    checks.require(
        summary_path.is_file() and not summary_path.is_symlink(),
        "artifact.summary_regular_file",
    )
    checks.require(_mode(ledger_path) == "0600", "artifact.ledger_mode_0600")
    checks.require(_mode(summary_path) == "0600", "artifact.summary_mode_0600")

    q201_documents: dict[str, dict[str, Any]] = {}
    for role, filename in Q201_FILES.items():
        path = root / Q201_DIRECTORY / filename
        checks.require(path.is_file() and not path.is_symlink(), f"q201.{role}.regular_file")
        checks.require(_mode(path) == "0600", f"q201.{role}.mode_0600")
        checks.require(_sha_file(path) == Q201_HASHES[role], f"q201.{role}.frozen_hash")
        q201_documents[role], _ = _read_unique_json(path, "q201." + role)
    checks.require(
        q201_documents["manifest"].get("status") == "complete",
        "q201.manifest.complete",
    )
    audit_checks = q201_documents["audit"].get("audit_checks")
    checks.require(
        q201_documents["audit"].get("status") == "passed"
        and isinstance(audit_checks, dict)
        and audit_checks.get("total") == 303_641
        and audit_checks.get("failed") == [],
        "q201.audit.passed",
    )
    preflight_documents: dict[str, dict[str, Any]] = {}
    for role, filename in PREFLIGHT_FILES.items():
        path = root / PREFLIGHT_DIRECTORY / filename
        checks.require(
            path.is_file() and not path.is_symlink(),
            f"preflight.{role}.regular_file",
        )
        checks.require(_mode(path) == "0600", f"preflight.{role}.mode_0600")
        checks.require(
            _sha_file(path) == PREFLIGHT_HASHES[role],
            f"preflight.{role}.frozen_hash",
        )
        preflight_documents[role], _ = _read_unique_json(
            path, "preflight." + role
        )
    preflight_checks = preflight_documents["audit"].get("audit_checks")
    checks.require(
        preflight_documents["manifest"].get("status") == "complete"
        and preflight_documents["audit"].get("status") == "passed"
        and isinstance(preflight_checks, dict)
        and preflight_checks.get("total") == 30_860
        and preflight_checks.get("failed") == [],
        "preflight.execution_and_audit_passed",
    )
    checks.require(
        _sha_file(root / MAPPING_CONFIG) == MAPPING_CONFIG_SHA256,
        "mapping.config.frozen_hash",
    )
    checks.require(
        _sha_file(root / MAPPING_REDUCER) == MAPPING_REDUCER_SHA256,
        "mapping.reducer.frozen_hash",
    )

    ledger, ledger_raw = _read_unique_json(ledger_path, "artifact.ledger")
    summary, summary_raw = _read_unique_json(summary_path, "artifact.summary")
    ledger_hash = _sha_bytes(ledger_raw)
    counts = _audit_initial_payloads(
        ledger,
        summary,
        q201_documents["discovery"],
        preflight_documents["private_values"],
        ledger_hash,
        checks,
        input_hashes=_input_hashes(),
        source_counts=SOURCE_COUNTS,
        q200_counts=Q200_COUNTS,
    )
    checks.require(
        counts["q201_baseline_source_value_memberships"] == TOTAL,
        "fixed.q201_total_33723",
    )
    checks.require(
        counts["q201_query200_overlap_memberships"] == Q200_OVERLAP,
        "fixed.q201_overlap_199",
    )
    checks.require(
        counts["q201_negative_space_memberships"] == NEGATIVE_SPACE,
        "fixed.q201_negative_33524",
    )
    checks.require(
        counts["preflight_product_description_other_nonnull_memberships"]
        == PRODUCT_OTHER_NONNULL,
        "fixed.product_other_nonnull_842",
    )
    checks.require(
        counts["preflight_product_description_other_sql_null_typed_presence"]
        == PRODUCT_OTHER_SQL_NULL_TYPED_PRESENCE,
        "fixed.product_other_sql_null_typed_presence_1",
    )
    checks.require(
        counts["extended_nonnull_semantic_memberships"] == EXTENDED_TOTAL,
        "fixed.extended_total_34565",
    )

    result = {
        "schema_version": 1,
        "audit": AUDIT_NAME,
        "status": "passed",
        "audit_checks": {
            "total": checks.total,
            "passed": checks.total,
            "failed": [],
        },
        "input_integrity": {
            **_input_hashes(),
            "private_ledger_sha256": ledger_hash,
            "aggregate_summary_sha256": _sha_bytes(summary_raw),
            "directory_mode": "0700",
            "private_file_mode": "0600",
        },
        "content_contract": {
            **counts,
            "semantic_raw_value_states": {"nonnull": EXTENDED_TOTAL, "null": 0},
            "typed_missing_boundary_presence": 1,
            "semantic_dimensions": len(SEMANTIC_DIMENSIONS),
            "all_initial_semantic_statuses_uncertain": True,
            "all_initial_review_statuses_unreviewed": True,
            "mapping_group_memberships": 0,
            "lexical_review_strata_used_for_selection": False,
        },
        "formal_guards": {guard: False for guard in FORMAL_GUARDS},
        "privacy": {
            "database_connection_used": False,
            "external_api_used": False,
            "controlled_vocabulary_values_emitted": False,
            "per_record_hashes_emitted": False,
            "patient_data_emitted": False,
        },
        "limitations": (
            "The audit validates an initial review ledger only. It makes no "
            "product, route, source-policy, action, episode, label, or cohort decision."
        ),
    }
    payload = _json_payload(result)
    if output.exists():
        if output.is_symlink() or not output.is_file() or _mode(output) != "0600":
            raise ProductReviewLedgerAuditError("audit_output.existing_private_file")
        if output.read_bytes() != payload:
            raise ProductReviewLedgerAuditError("audit_output.existing_content_match")
    else:
        _write_private(output, payload)
    return result, output
