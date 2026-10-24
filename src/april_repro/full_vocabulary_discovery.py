"""Fail-closed Query-201 discovery of the four complete medication vocabularies.

The database portion consists only of four reviewed SELECT statements.  They
run in one persistent PostgreSQL session and one REPEATABLE READ READ ONLY
transaction.  Database values remain in memory until an explicit rollback has
been observed and psql has exited with status zero.  The full vocabulary and
the executed SQL are then written as private files; the summary and manifest
contain counts and hashes only.
"""
from __future__ import annotations

import base64
import binascii
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time
from typing import Any, Mapping

from .database import DatabaseError, PsqlClient, _safe_error, _statement_body
from .preregistration import potassium_source_discovery_preregistration_report
from .staged_source_closure import _PersistentPsql


QUERY_NAME = "potassium_full_source_vocabulary_discovery"
STATEMENT_TIMEOUT_MS = 120_000
PROCESS_TIMEOUT_SECONDS = 130
MAX_STAGE_FRAME_BYTES = 128 * 1024 * 1024
MAX_CUMULATIVE_FRAME_BYTES = 256 * 1024 * 1024
MAX_EXECUTED_SQL_BYTES = 2 * 1024 * 1024
MAX_PAYLOAD_BYTES = 96 * 1024 * 1024
MAX_VALUES_PER_SOURCE = 100_000
MAX_VALUE_UTF8_BYTES = 16 * 1024
MAX_TOTAL_VALUE_UTF8_BYTES = 64 * 1024 * 1024
SNAPSHOT_PATTERN = re.compile(r"^[0-9]+:[0-9]+:[0-9,]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

DEFAULT_Q200_MANIFEST = Path(
    "artifacts/profiling/20261011T174457.657508Z/manifest.json"
)
EXPECTED_Q200_HASHES = {
    "manifest": "76b9ae67d02081d634965906cb7c11a3671b2c69ac7e194252b996156ee099e6",
    "audit": "73ca31b9556165ccb79e3d278812b4d0aec39aa75498327f452ca46fe6b9a31c",
    "discovery": "316861627d7ec0bf3eb3b61873c3b94578ab949572751c8da280e1b925bb826a",
    "output": "32995ac27f49e5fc9bac3893669f159916868382201a8a35197402f70bf7b66d",
    "executed_sql": "7f04d0d67d6e97b3ab20a026c3c8edb98e47fd42aae4e7e617f359a6e0e04df2",
}
EXPECTED_Q200_VALUE_COUNTS = {
    "emar_names": 23,
    "detail_names": 79,
    "pharmacy_names": 45,
    "prescription_names": 52,
    "seed_product_codes": 27,
    "detail_code_name_flags": 38,
}
EXPECTED_Q200_AUDIT_CHECKS = 18_952


@dataclass(frozen=True)
class StageSpec:
    source_key: str
    source_field: str
    enumeration_method: str
    sql_file: str
    q200_discovery_key: str


STAGES = (
    StageSpec(
        "emar_medication",
        "mimiciv_hosp.emar.medication",
        "recursive_index_walk",
        "sql/profiling/201a_full_emar_medication_vocabulary.sql",
        "emar_names",
    ),
    StageSpec(
        "detail_product_description",
        "mimiciv_hosp.emar_detail.product_description",
        "recursive_index_walk",
        "sql/profiling/201b_full_detail_product_description_vocabulary.sql",
        "detail_names",
    ),
    StageSpec(
        "pharmacy_medication",
        "mimiciv_hosp.pharmacy.medication",
        "recursive_index_walk",
        "sql/profiling/201c_full_pharmacy_medication_vocabulary.sql",
        "pharmacy_names",
    ),
    StageSpec(
        "prescription_drug",
        "mimiciv_hosp.prescriptions.drug",
        "full_distinct_scan",
        "sql/profiling/201d_full_prescription_drug_vocabulary.sql",
        "prescription_names",
    ),
)
STAGE_BY_KEY = {stage.source_key: stage for stage in STAGES}

# This is the stable presentation order requested for Query 201.  The
# classifier retains query-200's active-drug-first precedence for overlapping
# nonblank hints; all independent booleans remain visible in the private file.
REVIEW_STRATA = (
    "blank_after_trim",
    "focal_kcl_repletion_hint",
    "broader_phosphate_or_acetate_repletion_hint",
    "other_potassium_salt_review",
    "non_repletion_active_drug_hint",
    "unresolved_potassium_lexical_review",
    "no_declared_potassium_lexical_signal",
)

_FOCAL_KCL = re.compile(
    r"potassium[\s-]+(?:chloride|chl)(?:[^A-Za-z]|$)|"
    r"(?:^|[^A-Za-z0-9])kcl(?:[^A-Za-z0-9]|$)",
    re.IGNORECASE,
)
_PHOSPHATE = re.compile(
    r"potassium[\s-]+phosph|"
    r"(?:^|[^A-Za-z0-9])k[ -]?phos(?:[^A-Za-z0-9]|$)",
    re.IGNORECASE,
)
_ACETATE = re.compile(r"potassium[\s-]+acetate", re.IGNORECASE)
_OTHER_POTASSIUM_SALT = re.compile(
    r"potassium[\s-]+(?:citrate|bicarbonate|gluconate|iodide|"
    r"permanganate|perchlorate|tartrate)",
    re.IGNORECASE,
)
_ACTIVE_DRUG = re.compile(
    r"losartan|penicillin|amoxicillin|clavulan|diclofenac|clorazepate",
    re.IGNORECASE,
)
_DECLARED_POTASSIUM_LEXICAL = re.compile(
    r"potassium|(?:^|[^A-Za-z0-9])k[ -]?phos(?:[^A-Za-z0-9]|$)|"
    r"(?:^|[^A-Za-z0-9])kcl(?:[^A-Za-z0-9]|$)",
    re.IGNORECASE,
)

HINT_KEYS = (
    "blank_after_trim",
    "focal_kcl_hint",
    "phosphate_or_acetate_hint",
    "other_potassium_salt_hint",
    "non_repletion_active_drug_hint",
    "declared_potassium_lexical_signal",
    "unresolved_potassium_lexical_hint",
    "no_declared_potassium_lexical_signal",
)

FALSE_POLICY_GUARDS = (
    "product_identity_decided",
    "final_source_policy",
    "complete_intervention_coverage",
    "review_strata_are_inclusion_rules",
    "formal_action",
    "formal_episode",
    "zero_action_constructed",
    "formal_non_icu_rule",
    "formal_label",
    "formal_cohort",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mode(path: Path) -> str:
    return format(stat.S_IMODE(path.stat().st_mode), "04o")


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
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _remove_values(paths: list[Path]) -> bool:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return not any(path.exists() for path in paths)


def _unique_json(payload: bytes, label: str, byte_limit: int) -> dict[str, Any]:
    if len(payload) > byte_limit:
        raise DatabaseError(f"{label} exceeded its private payload byte limit.")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise DatabaseError(f"{label} JSON contains a duplicate object key.")
            result[key] = item
        return result

    try:
        value = json.loads(payload, object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DatabaseError(f"{label} returned malformed private JSON.") from exc
    if not isinstance(value, dict):
        raise DatabaseError(f"{label} returned a non-object JSON payload.")
    return value


def _snapshot_token(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 4096
        or SNAPSHOT_PATTERN.fullmatch(value) is None
    ):
        raise DatabaseError(f"{label} returned an invalid PostgreSQL snapshot token.")
    active = value.split(":", 2)[2]
    if active and any(not item for item in active.split(",")):
        raise DatabaseError(f"{label} returned an invalid PostgreSQL snapshot token.")
    return value


def _decode_frame(frame: bytes, spec: StageSpec) -> dict[str, Any]:
    label = f"Query-201 {spec.source_key} discovery"
    # The selected value is strict base64, so psql's CSV encoder never needs
    # quoting.  Parsing the exact two-line frame directly avoids Python's
    # process-global 128 KiB csv.field_size_limit while keeping the contract
    # narrower than a generic CSV parser.
    lines = frame.splitlines()
    if (
        len(lines) != 2
        or lines[0] != b"vocabulary_payload"
        or not lines[1]
    ):
        raise DatabaseError(f"{label} must return exactly one payload row.")
    try:
        payload = base64.b64decode(lines[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise DatabaseError(f"{label} returned malformed payload encoding.") from exc
    return _validate_stage_payload(payload, spec)


def _validate_stage_payload(payload: bytes, spec: StageSpec) -> dict[str, Any]:
    label = f"Query-201 {spec.source_key} discovery"
    value = _unique_json(payload, label, MAX_PAYLOAD_BYTES)
    expected_keys = {
        "schema_version",
        "stage",
        "source_key",
        "source_field",
        "enumeration_method",
        "transaction_isolation",
        "transaction_read_only",
        "snapshot_token",
        "distinct_nonnull_values",
        "values",
    }
    if set(value) != expected_keys:
        raise DatabaseError(f"{label} returned an unexpected schema.")
    if (
        value["schema_version"] != 1
        or type(value["schema_version"]) is not int
        or value["stage"] != spec.source_key
        or value["source_key"] != spec.source_key
        or value["source_field"] != spec.source_field
        or value["enumeration_method"] != spec.enumeration_method
    ):
        raise DatabaseError(f"{label} returned an invalid source contract.")
    if (
        value["transaction_isolation"] != "repeatable read"
        or value["transaction_read_only"] != "on"
    ):
        raise DatabaseError(
            f"{label} did not confirm the required read-only repeatable-read transaction."
        )
    _snapshot_token(value["snapshot_token"], label)
    values = value["values"]
    if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
        raise DatabaseError(f"{label} returned an invalid vocabulary array.")
    if (
        type(value["distinct_nonnull_values"]) is not int
        or value["distinct_nonnull_values"] < 0
        or value["distinct_nonnull_values"] != len(values)
    ):
        raise DatabaseError(f"{label} returned an inconsistent distinct-value count.")
    if len(values) > MAX_VALUES_PER_SOURCE:
        raise DatabaseError(f"{label} exceeded its vocabulary row limit.")
    if len(values) != len(set(values)):
        raise DatabaseError(f"{label} returned duplicate vocabulary values.")
    total_bytes = 0
    for item in values:
        try:
            encoded = item.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise DatabaseError(f"{label} returned invalid UTF-8 text.") from exc
        if b"\x00" in encoded or len(encoded) > MAX_VALUE_UTF8_BYTES:
            raise DatabaseError(f"{label} returned an over-limit vocabulary value.")
        total_bytes += len(encoded)
        if total_bytes > MAX_TOTAL_VALUE_UTF8_BYTES:
            raise DatabaseError(f"{label} exceeded its vocabulary byte limit.")
    # PostgreSQL collation is deployment-specific.  Sorting the validated raw
    # strings here gives the private artifact deterministic Python ordering
    # without changing exact membership.
    value["values"] = sorted(values)
    return value


def _assert_one_snapshot(payloads: Mapping[str, Mapping[str, Any]]) -> str:
    if set(payloads) != set(STAGE_BY_KEY):
        raise DatabaseError("Query-201 did not return all four source vocabularies.")
    snapshots = {
        _snapshot_token(payload["snapshot_token"], source_key)
        for source_key, payload in payloads.items()
    }
    if len(snapshots) != 1:
        raise DatabaseError("Query-201 stages did not observe one identical snapshot.")
    return next(iter(snapshots))


def _local_artifact(directory: Path, filename: Any, label: str) -> Path:
    if (
        not isinstance(filename, str)
        or not filename
        or Path(filename).name != filename
        or filename in {".", ".."}
    ):
        raise DatabaseError(f"The accepted query-200 {label} filename is invalid.")
    path = directory / filename
    if not path.is_file() or path.is_symlink():
        raise DatabaseError(f"The accepted query-200 {label} artifact is unavailable.")
    return path


def _validate_hash_map(value: Mapping[str, str]) -> dict[str, str]:
    expected_keys = {"manifest", "audit", "discovery", "output", "executed_sql"}
    if set(value) != expected_keys or any(
        not isinstance(item, str) or SHA256_PATTERN.fullmatch(item) is None
        for item in value.values()
    ):
        raise DatabaseError("The query-200 expected-hash contract is invalid.")
    return dict(value)


def load_q200_evidence(
    root: Path,
    *,
    manifest_path: Path | None = None,
    expected_hashes: Mapping[str, str] = EXPECTED_Q200_HASHES,
    expected_value_counts: Mapping[str, int] = EXPECTED_Q200_VALUE_COUNTS,
    expected_audit_checks: int = EXPECTED_Q200_AUDIT_CHECKS,
) -> dict[str, Any]:
    """Load the accepted Query-200 bundle without exposing dictionary values."""
    hashes = _validate_hash_map(expected_hashes)
    manifest_path = manifest_path or root / DEFAULT_Q200_MANIFEST
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise DatabaseError("The accepted query-200 manifest is unavailable.")
    directory = manifest_path.parent
    audit_path = directory / "audit-summary.json"
    if not audit_path.is_file() or audit_path.is_symlink():
        raise DatabaseError("The accepted query-200 audit summary is unavailable.")
    if _sha_file(manifest_path) != hashes["manifest"]:
        raise DatabaseError("The accepted query-200 manifest hash changed.")
    if _sha_file(audit_path) != hashes["audit"]:
        raise DatabaseError("The accepted query-200 audit hash changed.")
    if _mode(manifest_path) != "0600" or _mode(audit_path) != "0600":
        raise DatabaseError("The accepted query-200 evidence files are not private.")

    manifest = _unique_json(
        manifest_path.read_bytes(), "Query-200 manifest", 4 * 1024 * 1024
    )
    audit = _unique_json(
        audit_path.read_bytes(), "Query-200 audit summary", 4 * 1024 * 1024
    )
    queries = manifest.get("queries")
    if (
        manifest.get("status") != "complete"
        or manifest.get("selected_queries") != ["potassium_product_source_closure"]
        or manifest.get("rollback_confirmed") is not True
        or manifest.get("read_only_confirmed") is not True
        or manifest.get("same_snapshot_confirmed") is not True
        or manifest.get("transaction_isolation_confirmed") != "repeatable read"
        or not isinstance(queries, list)
        or len(queries) != 1
        or not isinstance(queries[0], dict)
    ):
        raise DatabaseError("The accepted query-200 manifest controls did not pass.")
    entry = queries[0]
    if (
        entry.get("query") != "potassium_product_source_closure"
        or entry.get("status") != "complete"
        or entry.get("psql_returncode") != 0
        or entry.get("private_discovery_persisted") is not True
        or entry.get("executed_sql_persisted") is not True
        or entry.get("output_persisted") is not True
    ):
        raise DatabaseError("The accepted query-200 query entry did not pass.")

    discovery_path = _local_artifact(directory, entry.get("discovery_file"), "discovery")
    output_path = _local_artifact(directory, entry.get("output_file"), "output")
    executed_path = _local_artifact(
        directory, entry.get("executed_sql_file"), "executed SQL"
    )
    for path, role in (
        (discovery_path, "discovery"),
        (output_path, "output"),
        (executed_path, "executed_sql"),
    ):
        actual = _sha_file(path)
        if actual != hashes[role] or entry.get(role + "_sha256") != actual:
            raise DatabaseError(f"The accepted query-200 {role} hash changed.")
        if _mode(path) != "0600":
            raise DatabaseError(f"The accepted query-200 {role} artifact is not private.")

    checks = audit.get("audit_checks")
    integrity = audit.get("input_integrity")
    staged = audit.get("staged_execution")
    guards = audit.get("global_guard_flags")
    if (
        audit.get("status") != "passed"
        or not isinstance(checks, dict)
        or checks.get("total") != expected_audit_checks
        or checks.get("failed") != []
        or not isinstance(integrity, dict)
        or integrity.get("manifest_sha256") != hashes["manifest"]
        or integrity.get("discovery_sha256") != hashes["discovery"]
        or integrity.get("output_sha256") != hashes["output"]
        or integrity.get("executed_sql_sha256") != hashes["executed_sql"]
        or not isinstance(staged, dict)
        or not staged
        or any(item is not True for item in staged.values())
        or not isinstance(guards, dict)
        or guards.get("all_rows_match") is not True
    ):
        raise DatabaseError("The accepted query-200 audit controls did not pass.")

    if set(expected_value_counts) != set(EXPECTED_Q200_VALUE_COUNTS) or any(
        type(item) is not int or item < 0 for item in expected_value_counts.values()
    ):
        raise DatabaseError("The query-200 expected vocabulary-count contract is invalid.")
    discovery = _unique_json(
        discovery_path.read_bytes(), "Query-200 private discovery", 4 * 1024 * 1024
    )
    vocabulary: dict[str, list[str]] = {}
    for spec in STAGES:
        values = discovery.get(spec.q200_discovery_key)
        expected_count = expected_value_counts[spec.q200_discovery_key]
        if (
            not isinstance(values, list)
            or len(values) != expected_count
            or any(not isinstance(item, str) for item in values)
            or len(values) != len(set(values))
        ):
            raise DatabaseError("The accepted query-200 vocabulary contract changed.")
        vocabulary[spec.source_key] = sorted(values)
    for key in ("seed_product_codes", "detail_code_name_flags"):
        values = discovery.get(key)
        if not isinstance(values, list) or len(values) != expected_value_counts[key]:
            raise DatabaseError("The accepted query-200 private dictionary counts changed.")
    if entry.get("discovery_value_counts") != dict(expected_value_counts):
        raise DatabaseError("The accepted query-200 manifest vocabulary counts changed.")

    merge = entry.get("merge_validation")
    if (
        not isinstance(merge, dict)
        or merge.get("candidate_emar_heads") != 719_059
        or merge.get("query199_head_scope_distinct_heads") != 559_191
        or merge.get("detail_code_dictionary_names") != 38
    ):
        raise DatabaseError("The accepted query-200 aggregate regressions changed.")
    return {
        "manifest_path": str(manifest_path.relative_to(root)),
        "hashes": hashes,
        "audit_checks": expected_audit_checks,
        "value_counts": dict(expected_value_counts),
        "vocabulary": vocabulary,
        "candidate_emar_heads": 719_059,
        "query199_head_scope_distinct_heads": 559_191,
        "heads_new_beyond_direct_name": 159_868,
    }


def classify_name(raw_name: str) -> dict[str, Any]:
    """Classify one controlled name into a neutral review stratum."""
    if not isinstance(raw_name, str):
        raise DatabaseError("Query-201 classification requires a text value.")
    normalized = re.sub(r"\s+", " ", raw_name.strip()).lower()
    blank = normalized == ""
    focal = _FOCAL_KCL.search(raw_name) is not None
    phosphate_or_acetate = (
        _PHOSPHATE.search(raw_name) is not None
        or _ACETATE.search(raw_name) is not None
    )
    other_salt = _OTHER_POTASSIUM_SALT.search(raw_name) is not None
    active_drug = _ACTIVE_DRUG.search(raw_name) is not None
    declared_signal = _DECLARED_POTASSIUM_LEXICAL.search(raw_name) is not None
    unresolved_signal = (
        declared_signal
        and not focal
        and not phosphate_or_acetate
        and not other_salt
        and not active_drug
    )
    no_signal = not declared_signal
    # Keep query-200's active-drug-first precedence so its already-discovered
    # nonblank values do not silently change semantic strata.
    if blank:
        stratum = "blank_after_trim"
    elif active_drug:
        stratum = "non_repletion_active_drug_hint"
    elif focal:
        stratum = "focal_kcl_repletion_hint"
    elif phosphate_or_acetate:
        stratum = "broader_phosphate_or_acetate_repletion_hint"
    elif other_salt:
        stratum = "other_potassium_salt_review"
    elif unresolved_signal:
        stratum = "unresolved_potassium_lexical_review"
    else:
        stratum = "no_declared_potassium_lexical_signal"
    hints = {
        "blank_after_trim": blank,
        "focal_kcl_hint": focal,
        "phosphate_or_acetate_hint": phosphate_or_acetate,
        "other_potassium_salt_hint": other_salt,
        "non_repletion_active_drug_hint": active_drug,
        "declared_potassium_lexical_signal": declared_signal,
        "unresolved_potassium_lexical_hint": unresolved_signal,
        "no_declared_potassium_lexical_signal": no_signal,
    }
    return {
        "normalized_name": normalized,
        "review_stratum": stratum,
        "hints": hints,
    }


def build_private_discovery(
    payloads: Mapping[str, Mapping[str, Any]],
    q200: Mapping[str, Any],
    *,
    snapshot_token: str,
) -> dict[str, Any]:
    """Create the full private review dictionary and enforce exact Q200 subset."""
    if set(payloads) != set(STAGE_BY_KEY):
        raise DatabaseError("Query-201 did not supply all source payloads.")
    q200_vocabulary = q200.get("vocabulary")
    if not isinstance(q200_vocabulary, Mapping):
        raise DatabaseError("Query-200 vocabulary lineage is unavailable.")
    sources: dict[str, Any] = {}
    for spec in STAGES:
        payload = payloads[spec.source_key]
        values = payload.get("values")
        if not isinstance(values, list):
            raise DatabaseError("Query-201 source payload is invalid.")
        q200_values = q200_vocabulary.get(spec.source_key)
        if not isinstance(q200_values, list):
            raise DatabaseError("Query-200 source vocabulary lineage is invalid.")
        full_set = set(values)
        q200_set = set(q200_values)
        if not q200_set.issubset(full_set):
            raise DatabaseError(
                "An accepted query-200 source vocabulary is not a subset of query 201."
            )
        records: list[dict[str, Any]] = []
        for raw_name in values:
            classification = classify_name(raw_name)
            records.append({
                "raw_name": raw_name,
                "normalized_name": classification["normalized_name"],
                "q200_member": raw_name in q200_set,
                "review_stratum": classification["review_stratum"],
                "hints": classification["hints"],
                "source_policy_status": "unresolved",
                "source_review_stratum_is_final_policy": False,
            })
        sources[spec.source_key] = {
            "source_field": spec.source_field,
            "enumeration_method": spec.enumeration_method,
            "distinct_nonnull_values": len(records),
            "q200_dictionary_values": len(q200_set),
            "values": records,
        }
    return {
        "schema_version": 1,
        "query": QUERY_NAME,
        "created_at_utc": _now(),
        "classification_version": "D005-K-SOURCE-DISCOVERY-v1",
        "normalization": "strip_then_collapse_unicode_whitespace_then_lowercase",
        "review_strata": list(REVIEW_STRATA),
        "classification_precedence": [
            "blank_after_trim",
            "non_repletion_active_drug_hint",
            "focal_kcl_repletion_hint",
            "broader_phosphate_or_acetate_repletion_hint",
            "other_potassium_salt_review",
            "unresolved_potassium_lexical_review",
            "no_declared_potassium_lexical_signal",
        ],
        "transaction": {
            "isolation": "repeatable read",
            "read_only": True,
            "same_snapshot": True,
            "snapshot_token_sha256": _sha(snapshot_token.encode("utf-8")),
            "rollback_confirmed_before_persistence": True,
            "clean_psql_exit_confirmed_before_persistence": True,
        },
        "query200_lineage": {
            "manifest_path": q200["manifest_path"],
            "hashes": dict(q200["hashes"]),
            "audit_checks": q200["audit_checks"],
            "value_counts": dict(q200["value_counts"]),
        },
        "sources": sources,
        "dictionary_value_is_patient_text": False,
        "all_source_policy_statuses": "unresolved",
        "policy_guards": {key: False for key in FALSE_POLICY_GUARDS},
    }


def build_aggregate_summary(discovery: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce the private dictionary to a value-free conservation summary."""
    sources = discovery.get("sources")
    if not isinstance(sources, Mapping) or set(sources) != set(STAGE_BY_KEY):
        raise DatabaseError("Query-201 private discovery has an invalid source schema.")
    source_summaries: dict[str, Any] = {}
    global_strata = Counter({key: 0 for key in REVIEW_STRATA})
    global_hints = Counter({key: 0 for key in HINT_KEYS})
    global_total = 0
    global_overlap = 0
    global_negative = 0
    for spec in STAGES:
        source = sources[spec.source_key]
        if not isinstance(source, Mapping) or not isinstance(source.get("values"), list):
            raise DatabaseError("Query-201 private discovery source is invalid.")
        records = source["values"]
        strata = Counter({key: 0 for key in REVIEW_STRATA})
        hints = Counter({key: 0 for key in HINT_KEYS})
        overlap = 0
        for record in records:
            if not isinstance(record, Mapping):
                raise DatabaseError("Query-201 private discovery record is invalid.")
            stratum = record.get("review_stratum")
            record_hints = record.get("hints")
            if stratum not in REVIEW_STRATA or not isinstance(record_hints, Mapping):
                raise DatabaseError("Query-201 review classification is invalid.")
            if (
                set(record_hints) != set(HINT_KEYS)
                or any(type(record_hints[key]) is not bool for key in HINT_KEYS)
                or record.get("source_policy_status") != "unresolved"
                or record.get("source_review_stratum_is_final_policy") is not False
                or type(record.get("q200_member")) is not bool
            ):
                raise DatabaseError("Query-201 fail-closed review record is invalid.")
            strata[stratum] += 1
            for key in HINT_KEYS:
                hints[key] += int(record_hints[key])
            overlap += int(record["q200_member"])
        total = len(records)
        q200_count = source.get("q200_dictionary_values")
        negative = total - overlap
        if (
            type(q200_count) is not int
            or overlap != q200_count
            or sum(strata.values()) != total
            or negative < 0
            or overlap + negative != total
        ):
            raise DatabaseError("Query-201 source conservation failed.")
        source_summaries[spec.source_key] = {
            "source_field": spec.source_field,
            "enumeration_method": spec.enumeration_method,
            "distinct_nonnull_values": total,
            "query200_dictionary_values": q200_count,
            "query200_overlap_values": overlap,
            "negative_space_values": negative,
            "review_strata_counts": {key: strata[key] for key in REVIEW_STRATA},
            "independent_hint_counts": {key: hints[key] for key in HINT_KEYS},
            "seven_strata_conservation_confirmed": sum(strata.values()) == total,
            "overlap_negative_space_conservation_confirmed": (
                overlap + negative == total
            ),
            "query200_exact_subset_confirmed": overlap == q200_count,
        }
        global_strata.update(strata)
        global_hints.update(hints)
        global_total += total
        global_overlap += overlap
        global_negative += negative
    if (
        sum(global_strata.values()) != global_total
        or global_overlap + global_negative != global_total
    ):
        raise DatabaseError("Query-201 global conservation failed.")
    lineage = discovery.get("query200_lineage")
    if not isinstance(lineage, Mapping):
        raise DatabaseError("Query-201 query-200 lineage is invalid.")
    return {
        "schema_version": 1,
        "query": QUERY_NAME,
        "scope": "four_complete_nonnull_distinct_source_vocabularies",
        "status": "complete",
        "source_summaries": source_summaries,
        "global_source_value_memberships": {
            "distinct_nonnull_source_value_memberships": global_total,
            "query200_overlap_source_value_memberships": global_overlap,
            "negative_space_source_value_memberships": global_negative,
            "review_strata_counts": {
                key: global_strata[key] for key in REVIEW_STRATA
            },
            "independent_hint_counts": {key: global_hints[key] for key in HINT_KEYS},
            "seven_strata_conservation_confirmed": (
                sum(global_strata.values()) == global_total
            ),
            "overlap_negative_space_conservation_confirmed": (
                global_overlap + global_negative == global_total
            ),
        },
        "query200_lineage": {
            "manifest_path": lineage["manifest_path"],
            "hashes": dict(lineage["hashes"]),
            "audit_checks": lineage["audit_checks"],
            "value_counts": dict(lineage["value_counts"]),
            "all_four_vocabulary_arrays_are_exact_subsets": True,
        },
        "privacy": {
            "controlled_vocabulary_values_emitted": False,
            "patient_identifiers_or_timestamps_emitted": False,
            "private_dictionary_required_for_value_review": True,
        },
        "all_source_policy_statuses": "unresolved",
        "policy_guards": {key: False for key in FALSE_POLICY_GUARDS},
        "limitations": (
            "Complete local string enumeration does not decide product identity, "
            "route, delivered dose, action, episode, label, non-ICU eligibility, "
            "or cohort membership. Every value remains unresolved for source policy."
        ),
    }


def _assert_value_free_public_payload(
    payload: Mapping[str, Any], raw_values: list[str]
) -> None:
    """Reject accidental raw-name fields or byte-for-byte name disclosure."""
    forbidden_keys = {"raw_name", "normalized_name", "values", "product_code"}

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            if forbidden_keys & set(value):
                raise DatabaseError("Query-201 public metadata contains a private-value key.")
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    # Only long sentinels can be checked without false positives against fixed
    # words such as "complete" or source labels.
    for raw_name in raw_values:
        if len(raw_name) >= 12 and raw_name in encoded:
            raise DatabaseError("Query-201 public metadata disclosed a vocabulary value.")


def _success_payloads(
    discovery: dict[str, Any],
    summary: dict[str, Any],
    executed_sql: bytes,
    *,
    rollback_confirmed: bool,
    psql_returncode: int | None,
) -> tuple[bytes, bytes, bytes]:
    """Serialization gate: private values cannot cross it before clean rollback."""
    if rollback_confirmed is not True or psql_returncode != 0:
        raise DatabaseError(
            "Query-201 values cannot be persisted before rollback and clean psql exit."
        )
    if len(executed_sql) > MAX_EXECUTED_SQL_BYTES:
        raise DatabaseError("Query-201 executed SQL exceeded its byte limit.")
    discovery_bytes = (
        json.dumps(discovery, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    summary = dict(summary)
    summary["private_artifact_hashes"] = {
        "discovery_sha256": _sha(discovery_bytes),
        "executed_sql_sha256": _sha(executed_sql),
    }
    raw_values = [
        record["raw_name"]
        for source in discovery["sources"].values()
        for record in source["values"]
    ]
    _assert_value_free_public_payload(summary, raw_values)
    summary_bytes = (
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return discovery_bytes, executed_sql, summary_bytes


def _session_preamble() -> str:
    return (
        "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
        f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms';\n"
        "SET LOCAL lock_timeout = '2000ms';\n"
        "SET LOCAL standard_conforming_strings = on;\n"
        "SET LOCAL work_mem = '128MB';\n"
        "SET LOCAL jit = off;\n"
    )


def _initial_stage(spec: StageSpec) -> dict[str, Any]:
    return {
        "source_key": spec.source_key,
        "source_field": spec.source_field,
        "enumeration_method": spec.enumeration_method,
        "file": spec.sql_file,
        "status": "pending",
        "rows": None,
        "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        "process_timeout_seconds": PROCESS_TIMEOUT_SECONDS,
    }


def _record_frame(
    session: _PersistentPsql,
    stage: dict[str, Any],
    control: str,
    marker: str,
) -> bytes:
    encoded = control.encode("utf-8")
    stage["control_sha256"] = _sha(encoded)
    stage["control_bytes"] = len(encoded)
    stage["status"] = "running"
    started = time.monotonic()
    try:
        session.send(control)
        frame = session.frame(
            marker, PROCESS_TIMEOUT_SECONDS, MAX_STAGE_FRAME_BYTES
        )
    finally:
        stage["elapsed_seconds"] = round(time.monotonic() - started, 6)
    stage["frame_sha256"] = _sha(frame)
    stage["frame_bytes"] = len(frame)
    return frame


def run_full_vocabulary_discovery(root: Path) -> dict[str, Any]:
    """Run Query 201 and return only terminal-safe metadata."""
    preregistration = potassium_source_discovery_preregistration_report(root)
    if not preregistration["valid"]:
        raise DatabaseError(
            "The D005 potassium source-discovery preregistration is invalid."
        )
    if (
        preregistration["status"] != "proposed"
        or preregistration["formal_source_policy_enabled"] is not False
        or preregistration["formal_product_identity_enabled"] is not False
    ):
        raise DatabaseError(
            "Query-201 requires the proposed discovery-only D005 contract."
        )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = root / "artifacts" / "profiling" / stamp
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    destination.chmod(0o700)
    manifest_path = destination / "manifest.json"
    stderr_path = destination / "psql.stderr"
    started = time.monotonic()
    stages = {spec.source_key: _initial_stage(spec) for spec in STAGES}
    report: dict[str, Any] = {
        "schema_version": 1,
        "started_at_utc": _now(),
        "status": "running",
        "scope": "private_full_source_vocabulary_negative_space_discovery",
        "selected_queries": [QUERY_NAME],
        "requested_controls": {
            "read_only": True,
            "same_snapshot": True,
            "transaction_isolation": "repeatable read",
            "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
            "explicit_rollback": True,
            "clean_psql_exit_before_value_persistence": True,
        },
        "confirmed_controls": {
            "read_only": False,
            "same_snapshot": False,
            "transaction_isolation": None,
            "rollback": False,
            "clean_psql_exit": False,
        },
        "artifact_modes": {
            "directory": "0700",
            "manifest": "0600",
            "stderr": None,
            "value_files": {},
        },
        "component_preregistration": {
            "component_id": preregistration["component_id"],
            "status": preregistration["status"],
            "config": preregistration["config"],
            "config_sha256": preregistration["config_sha256"],
            "evidence_files_checked": preregistration["evidence_files_checked"],
            "formal_source_policy_enabled": False,
            "formal_product_identity_enabled": False,
        },
        "query200_lineage": None,
        "queries": [{
            "query": QUERY_NAME,
            "status": "running",
            "stages": stages,
            "private_discovery_persisted": False,
            "executed_sql_persisted": False,
            "aggregate_summary_persisted": False,
            "psql_returncode": None,
        }],
        "limitations": (
            "This run enumerates four local controlled-vocabulary fields and "
            "computes neutral lexical review counts only. It does not define "
            "product policy, events, actions, labels, non-ICU eligibility, or cohort."
        ),
    }
    entry = report["queries"][0]
    session: _PersistentPsql | None = None
    rollback_marker: str | None = None
    executed_controls: list[str] = []
    value_paths: list[Path] = []
    pending_error: str | None = None
    manifest_written = False
    cumulative_frame_bytes = 0
    cumulative_control_bytes = 0
    try:
        q200 = load_q200_evidence(root)
        report["query200_lineage"] = {
            "manifest_path": q200["manifest_path"],
            "hashes": dict(q200["hashes"]),
            "audit_checks": q200["audit_checks"],
            "value_counts": dict(q200["value_counts"]),
            "candidate_emar_heads": q200["candidate_emar_heads"],
            "query199_head_scope_distinct_heads": q200[
                "query199_head_scope_distinct_heads"
            ],
            "heads_new_beyond_direct_name": q200["heads_new_beyond_direct_name"],
        }

        statements: dict[str, str] = {}
        for spec in STAGES:
            path = root / spec.sql_file
            raw = path.read_bytes()
            stages[spec.source_key]["template_sha256"] = _sha(raw)
            stages[spec.source_key]["template_bytes"] = len(raw)
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise DatabaseError("A query-201 SQL template is not valid UTF-8.") from exc
            statements[spec.source_key] = _statement_body(text)

        client = PsqlClient(root, STATEMENT_TIMEOUT_MS)
        session = _PersistentPsql(client, stderr_path)
        rollback_marker = "__APRIL_Q201_ROLLBACK_" + secrets.token_hex(24) + "__"
        payloads: dict[str, dict[str, Any]] = {}
        for index, spec in enumerate(STAGES):
            marker = (
                "__APRIL_Q201_" + spec.source_key.upper() + "_"
                + secrets.token_hex(24) + "__"
            )
            control = (
                (_session_preamble() if index == 0 else "")
                + statements[spec.source_key]
                + ";\n\\echo "
                + marker
                + "\n"
            )
            control_bytes = len(control.encode("utf-8"))
            if cumulative_control_bytes > MAX_EXECUTED_SQL_BYTES - control_bytes:
                raise DatabaseError("Query-201 executed SQL exceeded its byte limit.")
            cumulative_control_bytes += control_bytes
            executed_controls.append(control)
            frame = _record_frame(session, stages[spec.source_key], control, marker)
            if cumulative_frame_bytes > MAX_CUMULATIVE_FRAME_BYTES - len(frame):
                raise DatabaseError("Query-201 cumulative frame output exceeded its limit.")
            cumulative_frame_bytes += len(frame)
            payload = _decode_frame(frame, spec)
            payloads[spec.source_key] = payload
            stages[spec.source_key].update(
                status="validated_in_memory",
                rows=1,
                distinct_nonnull_values=payload["distinct_nonnull_values"],
            )

        snapshot_token = _assert_one_snapshot(payloads)
        snapshot_hash = _sha(snapshot_token.encode("utf-8"))
        for stage in stages.values():
            stage["observed_transaction_isolation"] = "repeatable read"
            stage["observed_transaction_read_only"] = "on"
            stage["observed_snapshot_sha256"] = snapshot_hash

        rollback_control = "ROLLBACK;\n\\echo " + rollback_marker + "\n"
        quit_control = "\\q\n"
        rollback_size = len(rollback_control.encode("utf-8"))
        quit_size = len(quit_control.encode("utf-8"))
        if cumulative_control_bytes > MAX_EXECUTED_SQL_BYTES - rollback_size - quit_size:
            raise DatabaseError("Query-201 executed SQL exceeded its byte limit.")
        session.confirm_rollback(rollback_marker)
        executed_controls.append(rollback_control)
        report["confirmed_controls"]["rollback"] = True
        returncode = session.close()
        session = None
        entry["psql_returncode"] = returncode
        if returncode != 0:
            raise DatabaseError(
                "Query-201 psql did not exit cleanly after confirmed rollback."
            )
        report["confirmed_controls"].update({
            "read_only": True,
            "same_snapshot": True,
            "transaction_isolation": "repeatable read",
            "clean_psql_exit": True,
        })

        discovery = build_private_discovery(
            payloads, q200, snapshot_token=snapshot_token
        )
        summary = build_aggregate_summary(discovery)
        executed_sql = ("".join(executed_controls) + quit_control).encode("utf-8")
        discovery_bytes, executed_sql, summary_bytes = _success_payloads(
            discovery,
            summary,
            executed_sql,
            rollback_confirmed=report["confirmed_controls"]["rollback"],
            psql_returncode=returncode,
        )
        artifacts = (
            (
                QUERY_NAME + ".discovery.json",
                discovery_bytes,
                "discovery",
                "private_discovery_persisted",
            ),
            (
                QUERY_NAME + ".executed.sql",
                executed_sql,
                "executed_sql",
                "executed_sql_persisted",
            ),
            (
                QUERY_NAME + ".aggregate-summary.json",
                summary_bytes,
                "aggregate_summary",
                "aggregate_summary_persisted",
            ),
        )
        for filename, data, role, persisted_key in artifacts:
            path = destination / filename
            value_paths.append(path)
            _write_private(path, data)
            if _mode(path) != "0600":
                raise DatabaseError("A query-201 artifact has an unsafe file mode.")
            entry[role + "_file"] = filename
            entry[role + "_sha256"] = _sha(data)
            entry[role + "_bytes"] = len(data)
            entry[persisted_key] = True
            report["artifact_modes"]["value_files"][filename] = "0600"

        source_counts = {
            key: value["distinct_nonnull_values"]
            for key, value in summary["source_summaries"].items()
        }
        negative_counts = {
            key: value["negative_space_values"]
            for key, value in summary["source_summaries"].items()
        }
        entry.update({
            "status": "complete",
            "source_counts": source_counts,
            "negative_space_counts": negative_counts,
            "query200_exact_subset_confirmed": True,
            "seven_strata_conservation_confirmed": True,
            "snapshot_token_sha256": snapshot_hash,
            "cumulative_frame_bytes": cumulative_frame_bytes,
            "cumulative_control_bytes": cumulative_control_bytes,
        })
        for stage in stages.values():
            stage["status"] = "complete"
        report["status"] = "complete"
    except DatabaseError as exc:
        pending_error = str(exc)
        report["status"] = "failed"
    except Exception:
        pending_error = "Query-201 failed before verified evidence could be produced."
        report["status"] = "failed"
    finally:
        if report["status"] != "complete" and session is not None and rollback_marker:
            try:
                session.confirm_rollback(rollback_marker)
                report["confirmed_controls"]["rollback"] = True
            except BaseException:
                pass
        if session is not None:
            try:
                entry["psql_returncode"] = session.close()
            except BaseException:
                entry["psql_returncode"] = None
        if report["status"] != "complete":
            for stage in stages.values():
                if stage["status"] == "running":
                    stage["status"] = "failed"
            entry["failure_value_cleanup_confirmed"] = _remove_values(value_paths)
            entry["private_discovery_persisted"] = False
            entry["executed_sql_persisted"] = False
            entry["aggregate_summary_persisted"] = False
            report["artifact_modes"]["value_files"] = {}
            raw_error = ""
            if stderr_path.is_file():
                try:
                    raw_error = stderr_path.read_text(errors="replace")[-16_384:]
                except OSError:
                    pass
            report["error"] = (
                _safe_error(raw_error)
                if raw_error.strip()
                else pending_error or "Query-201 failed."
            )
            entry["status"] = "failed"
        if stderr_path.is_file():
            try:
                report["artifact_modes"]["stderr"] = _mode(stderr_path)
                entry["stderr_file"] = stderr_path.name
                entry["stderr_sha256"] = _sha_file(stderr_path)
                entry["stderr_bytes"] = stderr_path.stat().st_size
            except OSError:
                pass
        entry["cumulative_frame_bytes"] = cumulative_frame_bytes
        entry["cumulative_control_bytes"] = cumulative_control_bytes
        entry["finished_at_utc"] = _now()
        entry["elapsed_seconds"] = round(time.monotonic() - started, 6)
        report["finished_at_utc"] = _now()
        report["elapsed_seconds"] = entry["elapsed_seconds"]
        try:
            _assert_value_free_public_payload(report, [])
            _write_private(
                manifest_path,
                (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
                .encode("utf-8"),
            )
            manifest_written = True
        except BaseException:
            report["status"] = "failed"
            entry["status"] = "failed"
            entry["private_discovery_persisted"] = False
            entry["executed_sql_persisted"] = False
            entry["aggregate_summary_persisted"] = False
            entry["failure_value_cleanup_confirmed"] = _remove_values(value_paths)
            try:
                manifest_path.unlink(missing_ok=True)
            except OSError:
                pass
        if manifest_written and _mode(manifest_path) != "0600":
            report["status"] = "failed"

    relative_manifest = str(manifest_path.relative_to(root)) if manifest_written else None
    result: dict[str, Any] = {
        "status": report["status"],
        "query": QUERY_NAME,
        "manifest": relative_manifest,
    }
    if report["status"] == "complete":
        result.update({
            "aggregate_summary": str(
                (destination / entry["aggregate_summary_file"]).relative_to(root)
            ),
            "source_counts": entry["source_counts"],
            "negative_space_counts": entry["negative_space_counts"],
            "query200_exact_subset_confirmed": True,
            "seven_strata_conservation_confirmed": True,
        })
    else:
        result["note"] = (
            "Query-201 did not persist any vocabulary value artifact unless both "
            "rollback and a clean psql exit had already been confirmed."
        )
    return result

