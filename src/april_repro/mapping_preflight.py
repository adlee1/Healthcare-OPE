"""Fail-closed D005 five-field mapping-preflight runner.

Five reviewed SELECT statements enumerate exact typed values and frequencies in
one PostgreSQL REPEATABLE READ READ ONLY transaction.  Raw route, product and
NDC values remain in memory until an explicit rollback and clean psql exit have
both been observed.  Public metadata contains aggregate counts and whole-set
hashes only.
"""
from __future__ import annotations

import base64
import binascii
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import stat
import struct
import sys
import time
from typing import Any, Mapping
import unicodedata

from . import preregistration
from .database import DatabaseError, PsqlClient, _safe_error, _statement_body
from .staged_source_closure import _PersistentPsql


QUERY_NAME = "potassium_mapping_preflight"
HASH_VERSION = b"typed-distinct-source-value-set-v1"
STATEMENT_TIMEOUT_MS = 120_000
PROCESS_TIMEOUT_SECONDS = 135
MAX_STAGE_FRAME_BYTES = 192 * 1024 * 1024
MAX_CUMULATIVE_FRAME_BYTES = 384 * 1024 * 1024
MAX_EXECUTED_SQL_BYTES = 2 * 1024 * 1024
MAX_PRIVATE_PAYLOAD_BYTES = 256 * 1024 * 1024
MAX_GROUPS_PER_SOURCE = 500_000
MAX_VALUE_UTF8_BYTES = 65_535
MAX_TOTAL_VALUE_UTF8_BYTES_PER_SOURCE = 128 * 1024 * 1024
MAX_EXACT_ROW_COUNT = (1 << 63) - 1
SNAPSHOT_PATTERN = re.compile(r"^[0-9]+:[0-9]+:[0-9,]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

FRAME_COLUMNS = (
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

PREFLIGHT_FALSE_FIELDS = (
    "formal_product_mapping_enabled",
    "formal_source_policy_enabled",
    "route_mapping_frozen",
    "external_ndc_mapping_executed",
)


@dataclass(frozen=True)
class StageSpec:
    source_key: str
    source_field: str
    sql_file: str
    field_role: str


STAGES = (
    StageSpec(
        "emar_detail_route",
        "mimiciv_hosp.emar_detail.route",
        "sql/profiling/202p1_potassium_emar_detail_route_vocabulary.sql",
        "route",
    ),
    StageSpec(
        "pharmacy_route",
        "mimiciv_hosp.pharmacy.route",
        "sql/profiling/202p2_potassium_pharmacy_route_vocabulary.sql",
        "route",
    ),
    StageSpec(
        "prescriptions_route",
        "mimiciv_hosp.prescriptions.route",
        "sql/profiling/202p3_potassium_prescriptions_route_vocabulary.sql",
        "route",
    ),
    StageSpec(
        "detail_product_description_other",
        "mimiciv_hosp.emar_detail.product_description_other",
        "sql/profiling/202p4_potassium_product_description_other_vocabulary.sql",
        "product_description_other",
    ),
    StageSpec(
        "prescriptions_ndc",
        "mimiciv_hosp.prescriptions.ndc",
        "sql/profiling/202p5_potassium_prescriptions_ndc_vocabulary.sql",
        "ndc",
    ),
)
STAGE_BY_KEY = {stage.source_key: stage for stage in STAGES}
IMPLEMENTATION_BUNDLE_PATHS = {
    "sql": tuple(stage.sql_file for stage in STAGES),
    "runner": (
        "src/april_repro/mapping_preflight.py",
        "scripts/run_potassium_mapping_preflight.py",
    ),
    "offline_auditor": (
        "src/april_repro/mapping_preflight_audit.py",
        "scripts/audit_potassium_mapping_preflight.py",
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _classification_runtime() -> dict[str, str]:
    return {
        "python_version": ".".join(str(item) for item in sys.version_info[:3]),
        "unicodedata_version": unicodedata.unidata_version,
    }


def _implementation_bundle(root: Path, paths: tuple[str, ...]) -> dict[str, Any]:
    """Hash one ordered implementation bundle with path/content lengths."""
    digest = hashlib.sha256()
    files: list[dict[str, Any]] = []
    for relative_text in paths:
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise DatabaseError("A mapping-preflight implementation path is unsafe.")
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise DatabaseError(
                f"A required mapping-preflight implementation file is absent: {relative_text}"
            )
        path_bytes = relative_text.encode("utf-8")
        data = path.read_bytes()
        if len(path_bytes) > 0xFFFFFFFF or len(data) > 0xFFFFFFFFFFFFFFFF:
            raise DatabaseError("A mapping-preflight implementation file is over limit.")
        digest.update(struct.pack(">I", len(path_bytes)))
        digest.update(path_bytes)
        digest.update(struct.pack(">Q", len(data)))
        digest.update(data)
        files.append({
            "path": relative_text,
            "bytes": len(data),
            "file_sha256": _sha(data),
        })
    return {
        "paths": list(paths),
        "bundle_sha256": digest.hexdigest(),
        "files": files,
        "encoding": "uint32be_path_length+path_utf8+uint64be_content_length+content",
    }


def implementation_bundles(root: Path) -> dict[str, dict[str, Any]]:
    return {
        name: _implementation_bundle(root, paths)
        for name, paths in IMPLEMENTATION_BUNDLE_PATHS.items()
    }


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


def _strict_uint(value: str, label: str, maximum: int) -> int:
    if not isinstance(value, str) or re.fullmatch(r"0|[1-9][0-9]*", value) is None:
        raise DatabaseError(f"{label} returned a malformed nonnegative integer.")
    number = int(value)
    if number > maximum:
        raise DatabaseError(f"{label} exceeded its integer limit.")
    return number


def _value_substate(raw_value: str) -> str:
    if raw_value == "":
        return "empty_string"
    if raw_value.isspace():
        return "whitespace_only"
    return "nonblank"


def typed_set_sha256(
    source_field: str,
    records: list[Mapping[str, Any]],
) -> str:
    """Hash a field's typed distinct set using the preregistered byte protocol.

    Frequencies are deliberately excluded.  A SQL-NULL record is present only
    when its observed source-row count is positive.  Non-NULL values are sorted
    by unsigned UTF-8 bytes, independent of database collation.
    """
    try:
        field_bytes = source_field.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise DatabaseError("The preflight source field is not valid UTF-8.") from exc
    if len(field_bytes) > 0xFFFFFFFF:
        raise DatabaseError("The preflight source field exceeds its hash length limit.")

    null_seen = False
    nonnull: list[bytes] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise DatabaseError("A preflight typed-set record is malformed.")
        is_null = record.get("raw_is_null")
        raw_value = record.get("raw_value")
        count = record.get("exact_row_count")
        if type(count) is not int or not 1 <= count <= MAX_EXACT_ROW_COUNT:
            raise DatabaseError("A preflight typed-set record has an invalid frequency.")
        if is_null is True:
            if null_seen or raw_value is not None:
                raise DatabaseError("A preflight typed set has an invalid SQL-NULL record.")
            null_seen = True
        elif is_null is False and isinstance(raw_value, str):
            try:
                raw_bytes = raw_value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise DatabaseError("A preflight raw value is not valid UTF-8.") from exc
            if b"\x00" in raw_bytes or len(raw_bytes) > MAX_VALUE_UTF8_BYTES:
                raise DatabaseError("A preflight raw value exceeds its byte contract.")
            nonnull.append(raw_bytes)
        else:
            raise DatabaseError("A preflight typed-set record has an invalid typed state.")
    if len(nonnull) != len(set(nonnull)):
        raise DatabaseError("A preflight typed set contains duplicate non-NULL values.")
    nonnull.sort()
    record_count = len(nonnull) + int(null_seen)
    digest = hashlib.sha256()
    digest.update(HASH_VERSION)
    digest.update(struct.pack(">I", len(field_bytes)))
    digest.update(field_bytes)
    digest.update(struct.pack(">Q", record_count))
    if null_seen:
        digest.update(b"\x00")
    for raw_bytes in nonnull:
        digest.update(b"\x01")
        digest.update(struct.pack(">Q", len(raw_bytes)))
        digest.update(raw_bytes)
    return digest.hexdigest()


def _decode_frame(frame: bytes, spec: StageSpec) -> dict[str, Any]:
    """Decode a row-streamed base64 CSV frame without logging raw values."""
    label = f"Mapping preflight {spec.source_key}"
    if len(frame) > MAX_STAGE_FRAME_BYTES:
        raise DatabaseError(f"{label} exceeded its private frame byte limit.")
    try:
        text = frame.decode("utf-8")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader)
        if tuple(header) != FRAME_COLUMNS:
            raise DatabaseError(f"{label} returned an unexpected CSV schema.")
        rows = list(reader)
    except StopIteration as exc:
        raise DatabaseError(f"{label} returned no CSV header.") from exc
    except (UnicodeDecodeError, csv.Error) as exc:
        raise DatabaseError(f"{label} returned malformed CSV framing.") from exc
    if not rows:
        raise DatabaseError(f"{label} returned no typed-value rows.")
    if len(rows) > MAX_GROUPS_PER_SOURCE + 1:
        raise DatabaseError(f"{label} exceeded its typed-value row limit.")

    controls: dict[str, str] | None = None
    records: list[dict[str, Any]] = []
    seen: set[tuple[bool, str | None]] = set()
    null_observations = 0
    sql_null_rows: int | None = None
    total_value_bytes = 0
    for row in rows:
        if len(row) != len(FRAME_COLUMNS):
            raise DatabaseError(f"{label} returned a malformed CSV row.")
        item = dict(zip(FRAME_COLUMNS, row, strict=True))
        if (
            item["schema_version"] != "1"
            or item["stage"] != spec.source_key
            or item["source_key"] != spec.source_key
            or item["source_field"] != spec.source_field
            or item["transaction_isolation"] != "repeatable read"
            or item["transaction_read_only"] != "on"
        ):
            raise DatabaseError(f"{label} returned an invalid source or transaction contract.")
        _snapshot_token(item["snapshot_token"], label)
        row_controls = {key: item[key] for key in FRAME_COLUMNS[:7]}
        if controls is None:
            controls = row_controls
        elif row_controls != controls:
            raise DatabaseError(f"{label} changed controls within one result frame.")

        if item["raw_is_null"] not in {"t", "f"}:
            raise DatabaseError(f"{label} returned an invalid typed-state flag.")
        is_null = item["raw_is_null"] == "t"
        exact_count = _strict_uint(
            item["exact_row_count"], label, MAX_EXACT_ROW_COUNT
        )
        declared_bytes = _strict_uint(
            item["raw_utf8_bytes"], label, MAX_VALUE_UTF8_BYTES
        )
        encoded = item["raw_value_base64"]
        if len(encoded) > ((MAX_VALUE_UTF8_BYTES + 2) // 3) * 4:
            raise DatabaseError(f"{label} returned an over-limit encoded value.")

        if is_null:
            null_observations += 1
            if null_observations != 1 or encoded != "" or declared_bytes != 0:
                raise DatabaseError(f"{label} returned an invalid SQL-NULL observation.")
            sql_null_rows = exact_count
            raw_value: str | None = None
        else:
            if exact_count == 0:
                raise DatabaseError(f"{label} returned a zero-frequency non-NULL value.")
            try:
                raw_bytes = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise DatabaseError(f"{label} returned malformed base64 value data.") from exc
            if base64.b64encode(raw_bytes).decode("ascii") != encoded:
                raise DatabaseError(f"{label} returned noncanonical base64 value data.")
            if len(raw_bytes) != declared_bytes or b"\x00" in raw_bytes:
                raise DatabaseError(f"{label} returned an invalid raw-value byte count.")
            try:
                raw_value = raw_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise DatabaseError(f"{label} returned non-UTF-8 raw-value data.") from exc
            total_value_bytes += len(raw_bytes)
            if total_value_bytes > MAX_TOTAL_VALUE_UTF8_BYTES_PER_SOURCE:
                raise DatabaseError(f"{label} exceeded its cumulative raw-value byte limit.")

        identity = (is_null, raw_value)
        if identity in seen:
            raise DatabaseError(f"{label} returned a duplicate typed exact value.")
        seen.add(identity)
        # The SQL emits one zero-count NULL observation when NULL is absent.
        # It proves the NULL count was measured but is not a typed-set member.
        if not is_null or exact_count > 0:
            records.append({
                "raw_is_null": is_null,
                "raw_value": raw_value,
                "exact_row_count": exact_count,
                "raw_utf8_bytes": declared_bytes,
                "nonnull_substate": (
                    None if is_null else _value_substate(raw_value)
                ),
            })

    if controls is None or null_observations != 1 or sql_null_rows is None:
        raise DatabaseError(f"{label} did not return exactly one SQL-NULL count observation.")
    nonnull_records = [record for record in records if not record["raw_is_null"]]
    if len(nonnull_records) > MAX_GROUPS_PER_SOURCE:
        raise DatabaseError(f"{label} exceeded its non-NULL distinct-value limit.")
    records.sort(
        key=lambda record: (
            not record["raw_is_null"],
            b"" if record["raw_is_null"] else record["raw_value"].encode("utf-8"),
        )
    )
    typed_hash = typed_set_sha256(spec.source_field, records)
    return {
        "schema_version": 1,
        "stage": spec.source_key,
        "source_key": spec.source_key,
        "source_field": spec.source_field,
        "field_role": spec.field_role,
        "transaction_isolation": controls["transaction_isolation"],
        "transaction_read_only": controls["transaction_read_only"],
        "snapshot_token": controls["snapshot_token"],
        "sql_null_observation_emitted": True,
        "sql_null_rows": sql_null_rows,
        "typed_distinct_values": len(records),
        "nonnull_distinct_values": len(nonnull_records),
        "typed_set_sha256": typed_hash,
        "records": records,
    }


def _assert_one_snapshot(payloads: Mapping[str, Mapping[str, Any]]) -> str:
    if set(payloads) != set(STAGE_BY_KEY):
        raise DatabaseError("The mapping preflight did not return all five fields.")
    snapshots = {
        _snapshot_token(payload["snapshot_token"], source_key)
        for source_key, payload in payloads.items()
    }
    if len(snapshots) != 1:
        raise DatabaseError("The mapping-preflight fields did not share one snapshot.")
    return next(iter(snapshots))


def _validate_preregistration_gate(report: Any) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise DatabaseError("The mapping-preflight preregistration report is malformed.")
    if (
        report.get("valid") is not True
        or report.get("status") != "proposed"
        or report.get("execution_status") != "not_executed"
    ):
        raise DatabaseError(
            "The D005 mapping-preflight preregistration is not a valid unexecuted proposal."
        )
    if any(report.get(key) is not False for key in PREFLIGHT_FALSE_FIELDS):
        raise DatabaseError(
            "The D005 mapping-preflight formal guards must remain false before execution."
        )
    # The preregistration validator supplies this only after all three pinned
    # implementation digests are lowercase SHA-256 values and match disk.
    if report.get("implementation_hashes_verified") is not True:
        raise DatabaseError(
            "The D005 mapping-preflight implementation hashes are not frozen."
        )
    bundles = report.get("implementation_bundles")
    if not isinstance(bundles, dict) or set(bundles) != set(IMPLEMENTATION_BUNDLE_PATHS):
        raise DatabaseError("The mapping-preflight implementation bundle report is incomplete.")
    for key in ("component_id", "config", "config_sha256"):
        if not isinstance(report.get(key), str) or not report[key]:
            raise DatabaseError("The mapping-preflight preregistration lineage is incomplete.")
    if SHA256_PATTERN.fullmatch(report["config_sha256"]) is None:
        raise DatabaseError("The mapping-preflight config hash is invalid.")
    if type(report.get("evidence_files_checked")) is not int:
        raise DatabaseError("The mapping-preflight evidence count is invalid.")
    return report


def build_private_preflight(
    payloads: Mapping[str, Mapping[str, Any]],
    preregistered: Mapping[str, Any],
    *,
    snapshot_token: str,
) -> dict[str, Any]:
    if set(payloads) != set(STAGE_BY_KEY):
        raise DatabaseError("The mapping preflight private artifact lacks a source field.")
    sources: dict[str, Any] = {}
    for spec in STAGES:
        payload = payloads[spec.source_key]
        if (
            payload.get("source_field") != spec.source_field
            or payload.get("field_role") != spec.field_role
            or not isinstance(payload.get("records"), list)
        ):
            raise DatabaseError("A mapping-preflight source payload is malformed.")
        sources[spec.source_key] = {
            "source_field": spec.source_field,
            "field_role": spec.field_role,
            "sql_null_rows": payload["sql_null_rows"],
            "sql_null_present": payload["sql_null_rows"] > 0,
            "typed_distinct_values": payload["typed_distinct_values"],
            "nonnull_distinct_values": payload["nonnull_distinct_values"],
            "typed_set_sha256": payload["typed_set_sha256"],
            "records": [dict(record) for record in payload["records"]],
        }
    return {
        "schema_version": 1,
        "query": QUERY_NAME,
        "created_at_utc": _now(),
        "component_lineage": {
            "component_id": preregistered["component_id"],
            "status_at_execution": preregistered["status"],
            "config": preregistered["config"],
            "config_sha256": preregistered["config_sha256"],
        },
        "typed_set_hash_contract": {
            "algorithm": "sha256",
            "version": HASH_VERSION.decode("ascii"),
            "frequencies_included": False,
            "source_field_included": True,
            "null_token": "00",
            "nonnull_token": "01",
            "integer_encoding": "unsigned_big_endian",
        },
        "nonnull_substate_classification_runtime": _classification_runtime(),
        "transaction": {
            "isolation": "repeatable read",
            "read_only": True,
            "same_snapshot": True,
            "snapshot_token_sha256": _sha(snapshot_token.encode("utf-8")),
            "rollback_confirmed_before_persistence": True,
            "clean_psql_exit_confirmed_before_persistence": True,
        },
        "sources": sources,
        "raw_values_are_exact_and_unnormalized": True,
        "contains_patient_or_event_identifiers": False,
        "contains_event_timestamps": False,
        "route_mapping_created": False,
        "external_api_called": False,
        "product_identity_decided": False,
        "final_source_policy": False,
    }


def build_aggregate_summary(private: Mapping[str, Any]) -> dict[str, Any]:
    sources = private.get("sources")
    if not isinstance(sources, Mapping) or set(sources) != set(STAGE_BY_KEY):
        raise DatabaseError("The mapping-preflight private source collection is invalid.")
    summaries: dict[str, Any] = {}
    grand_rows = 0
    grand_typed_distinct = 0
    for spec in STAGES:
        source = sources[spec.source_key]
        records = source.get("records") if isinstance(source, Mapping) else None
        if not isinstance(records, list):
            raise DatabaseError("A mapping-preflight private source is invalid.")
        typed_rows = {"sql_null": 0, "nonnull": 0}
        typed_distinct = {"sql_null": 0, "nonnull": 0}
        substates_rows = {
            "empty_string": 0,
            "whitespace_only": 0,
            "nonblank": 0,
        }
        substates_distinct = dict.fromkeys(substates_rows, 0)
        seen: set[tuple[bool, str | None]] = set()
        for record in records:
            if not isinstance(record, Mapping):
                raise DatabaseError("A mapping-preflight private record is invalid.")
            is_null = record.get("raw_is_null")
            raw = record.get("raw_value")
            count = record.get("exact_row_count")
            byte_count = record.get("raw_utf8_bytes")
            substate = record.get("nonnull_substate")
            if type(count) is not int or not 1 <= count <= MAX_EXACT_ROW_COUNT:
                raise DatabaseError("A mapping-preflight frequency is invalid.")
            if is_null is True:
                if raw is not None or byte_count != 0 or substate is not None:
                    raise DatabaseError("A mapping-preflight SQL-NULL record is invalid.")
                state = "sql_null"
            elif is_null is False and isinstance(raw, str):
                encoded = raw.encode("utf-8")
                if byte_count != len(encoded) or b"\x00" in encoded:
                    raise DatabaseError("A mapping-preflight non-NULL record is invalid.")
                if substate != _value_substate(raw):
                    raise DatabaseError("A mapping-preflight non-NULL substate is invalid.")
                state = "nonnull"
                substates_rows[substate] += count
                substates_distinct[substate] += 1
            else:
                raise DatabaseError("A mapping-preflight typed state is invalid.")
            identity = (is_null, raw)
            if identity in seen:
                raise DatabaseError("A mapping-preflight private source has duplicate values.")
            seen.add(identity)
            typed_rows[state] += count
            typed_distinct[state] += 1

        total_rows = sum(typed_rows.values())
        if total_rows > MAX_EXACT_ROW_COUNT:
            raise DatabaseError("A mapping-preflight source row total exceeds bigint.")
        recomputed_hash = typed_set_sha256(spec.source_field, records)
        if (
            source.get("source_field") != spec.source_field
            or source.get("field_role") != spec.field_role
            or source.get("sql_null_rows") != typed_rows["sql_null"]
            or source.get("sql_null_present") is not (typed_rows["sql_null"] > 0)
            or source.get("typed_distinct_values") != len(records)
            or source.get("nonnull_distinct_values") != typed_distinct["nonnull"]
            or source.get("typed_set_sha256") != recomputed_hash
            or sum(substates_rows.values()) != typed_rows["nonnull"]
            or sum(substates_distinct.values()) != typed_distinct["nonnull"]
        ):
            raise DatabaseError("A mapping-preflight source failed count conservation.")
        summaries[spec.source_key] = {
            "source_field": spec.source_field,
            "field_role": spec.field_role,
            "source_rows": total_rows,
            "typed_distinct_values": len(records),
            "typed_state_row_counts": typed_rows,
            "typed_state_distinct_counts": typed_distinct,
            "nonnull_substate_row_counts": substates_rows,
            "nonnull_substate_distinct_counts": substates_distinct,
            "typed_set_sha256": recomputed_hash,
            "row_conservation_confirmed": True,
            "distinct_conservation_confirmed": True,
        }
        grand_rows += total_rows
        grand_typed_distinct += len(records)
    return {
        "schema_version": 1,
        "query": QUERY_NAME,
        "created_at_utc": _now(),
        "scope": "exact_five_field_typed_vocabulary_preflight",
        "component_lineage": dict(private["component_lineage"]),
        "source_summaries": summaries,
        "global_counts": {
            "source_fields": len(STAGES),
            "route_fields": sum(spec.field_role == "route" for spec in STAGES),
            "source_rows_across_fields": grand_rows,
            "typed_distinct_source_value_memberships": grand_typed_distinct,
        },
        "transaction_controls": dict(private["transaction"]),
        "nonnull_substate_classification_runtime": dict(
            private["nonnull_substate_classification_runtime"]
        ),
        "privacy": {
            "raw_values_emitted": False,
            "local_ndc_values_emitted": False,
            "per_value_hashes_emitted": False,
            "patient_or_event_data_emitted": False,
        },
        "boundary_guards": {
            "route_mapping_created": False,
            "external_api_called": False,
            "product_identity_decided": False,
            "event_mapping_created": False,
            "final_source_policy": False,
            "formal_action": False,
            "formal_episode": False,
            "formal_label": False,
            "formal_cohort": False,
        },
    }


def _assert_value_free_public_payload(
    payload: Mapping[str, Any], raw_values: list[str]
) -> None:
    forbidden_keys = {
        "raw_value",
        "raw_value_base64",
        "records",
        "snapshot_token",
        "per_value_hash",
    }

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            if forbidden_keys & set(value):
                raise DatabaseError("Mapping-preflight public metadata has a private key.")
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    for raw_value in raw_values:
        if len(raw_value) >= 12 and raw_value in encoded:
            raise DatabaseError("Mapping-preflight public metadata disclosed a raw value.")


def _success_payloads(
    private: dict[str, Any],
    summary: dict[str, Any],
    executed_sql: bytes,
    *,
    rollback_confirmed: bool,
    psql_returncode: int | None,
) -> tuple[bytes, bytes, bytes]:
    if rollback_confirmed is not True or psql_returncode != 0:
        raise DatabaseError(
            "Mapping-preflight values cannot persist before rollback and clean exit."
        )
    if len(executed_sql) > MAX_EXECUTED_SQL_BYTES:
        raise DatabaseError("Mapping-preflight executed SQL exceeded its byte limit.")
    private_bytes = (
        json.dumps(private, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(private_bytes) > MAX_PRIVATE_PAYLOAD_BYTES:
        raise DatabaseError("Mapping-preflight private artifact exceeded its byte limit.")
    summary = dict(summary)
    summary["private_artifact_hashes"] = {
        "private_values_sha256": _sha(private_bytes),
        "executed_sql_sha256": _sha(executed_sql),
    }
    raw_values = [
        record["raw_value"]
        for source in private["sources"].values()
        for record in source["records"]
        if record["raw_value"] is not None
    ]
    _assert_value_free_public_payload(summary, raw_values)
    summary_bytes = (
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return private_bytes, executed_sql, summary_bytes


def _session_preamble() -> str:
    return (
        "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
        "SET LOCAL lock_timeout = '2000ms';\n"
        "SET LOCAL standard_conforming_strings = on;\n"
        "SET LOCAL work_mem = '128MB';\n"
        "SET LOCAL jit = off;\n"
    )


def _stage_control(statement: str, marker: str, *, first: bool) -> str:
    return (
        (_session_preamble() if first else "")
        + f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms';\n"
        + statement
        + ";\n\\echo "
        + marker
        + "\n"
    )


def _initial_stage(spec: StageSpec) -> dict[str, Any]:
    return {
        "source_key": spec.source_key,
        "source_field": spec.source_field,
        "field_role": spec.field_role,
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
        frame = session.frame(marker, PROCESS_TIMEOUT_SECONDS, MAX_STAGE_FRAME_BYTES)
    finally:
        stage["elapsed_seconds"] = round(time.monotonic() - started, 6)
    stage["frame_bytes"] = len(frame)
    return frame


def run_mapping_preflight(root: Path) -> dict[str, Any]:
    """Execute the five-field preflight and return terminal-safe metadata only."""
    report_function = getattr(
        preregistration,
        "potassium_mapping_preflight_preregistration_report",
        None,
    )
    if report_function is None:
        raise DatabaseError("The mapping-preflight preregistration validator is absent.")
    preregistered = _validate_preregistration_gate(report_function(root))
    observed_implementation_bundles = implementation_bundles(root)
    for name, observed in observed_implementation_bundles.items():
        registered = preregistered["implementation_bundles"].get(name)
        if (
            not isinstance(registered, Mapping)
            or registered.get("paths") != observed["paths"]
            or registered.get("actual_sha256") != observed["bundle_sha256"]
            or registered.get("expected_sha256") != observed["bundle_sha256"]
        ):
            raise DatabaseError(
                "A mapping-preflight implementation bundle changed after validation."
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
        "scope": "exact_five_field_typed_vocabulary_preflight",
        "selected_queries": [QUERY_NAME],
        "requested_controls": {
            "read_only": True,
            "same_snapshot": True,
            "transaction_isolation": "repeatable read",
            "statement_timeout_ms_per_stage": STATEMENT_TIMEOUT_MS,
            "explicit_rollback": True,
            "clean_psql_exit_before_value_persistence": True,
            "external_api_calls": False,
        },
        "confirmed_controls": {
            "read_only": False,
            "same_snapshot": False,
            "transaction_isolation": None,
            "rollback": False,
            "clean_psql_exit": False,
            "external_api_calls": False,
        },
        "artifact_modes": {
            "directory": "0700",
            "manifest": "0600",
            "stderr": None,
            "value_files": {},
        },
        "component_preregistration": {
            "component_id": preregistered["component_id"],
            "status_at_start": preregistered["status"],
            "execution_status_at_start": preregistered["execution_status"],
            "config": preregistered["config"],
            "config_sha256": preregistered["config_sha256"],
            "evidence_files_checked": preregistered["evidence_files_checked"],
            "implementation_hashes_verified": True,
            "implementation_bundles": preregistered["implementation_bundles"],
            **{key: False for key in PREFLIGHT_FALSE_FIELDS},
        },
        "implementation_bundles": observed_implementation_bundles,
        "nonnull_substate_classification_runtime": _classification_runtime(),
        "queries": [{
            "query": QUERY_NAME,
            "status": "running",
            "stages": stages,
            "private_values_persisted": False,
            "executed_sql_persisted": False,
            "aggregate_summary_persisted": False,
            "psql_returncode": None,
        }],
        "limitations": (
            "This preflight only enumerates five exact typed local fields and "
            "their frequencies. It does not map routes, normalize NDCs, call "
            "external services, identify products, link events, accept a source "
            "policy, or construct actions, episodes, labels, or a cohort."
        ),
    }
    entry = report["queries"][0]
    session: _PersistentPsql | None = None
    rollback_marker: str | None = None
    executed_controls: list[str] = []
    value_paths: list[Path] = []
    payloads: dict[str, dict[str, Any]] = {}
    private: dict[str, Any] | None = None
    pending_error: str | None = None
    manifest_written = False
    cumulative_frame_bytes = 0
    cumulative_control_bytes = 0
    try:
        statements: dict[str, str] = {}
        frozen_sql_files = {
            item["path"]: item["file_sha256"]
            for item in observed_implementation_bundles["sql"]["files"]
        }
        for spec in STAGES:
            path = root / spec.sql_file
            raw = path.read_bytes()
            template_sha256 = _sha(raw)
            if frozen_sql_files.get(spec.sql_file) != template_sha256:
                raise DatabaseError(
                    "A mapping-preflight SQL template changed after bundle validation."
                )
            stages[spec.source_key]["template_sha256"] = template_sha256
            stages[spec.source_key]["template_bytes"] = len(raw)
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise DatabaseError("A mapping-preflight SQL template is not UTF-8.") from exc
            statements[spec.source_key] = _statement_body(text)
        report["sql_bundle_sha256"] = observed_implementation_bundles[
            "sql"
        ]["bundle_sha256"]

        client = PsqlClient(root, STATEMENT_TIMEOUT_MS)
        rollback_marker = "__APRIL_MAPPING_PREFLIGHT_ROLLBACK_" + secrets.token_hex(24) + "__"
        session = _PersistentPsql(client, stderr_path)
        for index, spec in enumerate(STAGES):
            marker = (
                "__APRIL_MAPPING_PREFLIGHT_"
                + spec.source_key.upper()
                + "_"
                + secrets.token_hex(24)
                + "__"
            )
            control = _stage_control(
                statements[spec.source_key], marker, first=index == 0
            )
            control_bytes = len(control.encode("utf-8"))
            if cumulative_control_bytes > MAX_EXECUTED_SQL_BYTES - control_bytes:
                raise DatabaseError("Mapping-preflight executed SQL exceeded its byte limit.")
            cumulative_control_bytes += control_bytes
            executed_controls.append(control)
            frame = _record_frame(session, stages[spec.source_key], control, marker)
            if cumulative_frame_bytes > MAX_CUMULATIVE_FRAME_BYTES - len(frame):
                raise DatabaseError("Mapping-preflight cumulative output exceeded its limit.")
            cumulative_frame_bytes += len(frame)
            payload = _decode_frame(frame, spec)
            payloads[spec.source_key] = payload
            stages[spec.source_key].update(
                status="validated_in_memory",
                rows=payload["typed_distinct_values"],
                source_rows=sum(
                    record["exact_row_count"] for record in payload["records"]
                ),
                typed_distinct_values=payload["typed_distinct_values"],
                nonnull_distinct_values=payload["nonnull_distinct_values"],
                sql_null_rows=payload["sql_null_rows"],
                typed_set_sha256=payload["typed_set_sha256"],
            )

        snapshot_token = _assert_one_snapshot(payloads)
        snapshot_hash = _sha(snapshot_token.encode("utf-8"))
        for stage in stages.values():
            stage["observed_transaction_isolation"] = "repeatable read"
            stage["observed_transaction_read_only"] = "on"
            stage["observed_snapshot_sha256"] = snapshot_hash

        rollback_control = "ROLLBACK;\n\\echo " + rollback_marker + "\n"
        quit_control = "\\q\n"
        remaining = len(rollback_control.encode("utf-8")) + len(quit_control.encode("utf-8"))
        if cumulative_control_bytes > MAX_EXECUTED_SQL_BYTES - remaining:
            raise DatabaseError("Mapping-preflight executed SQL exceeded its byte limit.")
        session.confirm_rollback(rollback_marker)
        executed_controls.append(rollback_control)
        report["confirmed_controls"]["rollback"] = True
        returncode = session.close()
        session = None
        entry["psql_returncode"] = returncode
        if returncode != 0:
            raise DatabaseError(
                "Mapping-preflight psql did not exit cleanly after confirmed rollback."
            )
        report["confirmed_controls"].update({
            "read_only": True,
            "same_snapshot": True,
            "transaction_isolation": "repeatable read",
            "clean_psql_exit": True,
        })

        private = build_private_preflight(
            payloads, preregistered, snapshot_token=snapshot_token
        )
        summary = build_aggregate_summary(private)
        executed_sql = ("".join(executed_controls) + quit_control).encode("utf-8")
        private_bytes, executed_sql, summary_bytes = _success_payloads(
            private,
            summary,
            executed_sql,
            rollback_confirmed=report["confirmed_controls"]["rollback"],
            psql_returncode=returncode,
        )
        artifacts = (
            (
                QUERY_NAME + ".private-values.json",
                private_bytes,
                "private_values",
                "private_values_persisted",
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
                raise DatabaseError("A mapping-preflight artifact has an unsafe mode.")
            entry[role + "_file"] = filename
            entry[role + "_sha256"] = _sha(data)
            entry[role + "_bytes"] = len(data)
            entry[persisted_key] = True
            report["artifact_modes"]["value_files"][filename] = "0600"

        entry.update({
            "status": "complete",
            "source_counts": {
                key: {
                    "source_rows": value["source_rows"],
                    "typed_distinct_values": value["typed_distinct_values"],
                    "typed_set_sha256": value["typed_set_sha256"],
                }
                for key, value in summary["source_summaries"].items()
            },
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
        pending_error = "Mapping preflight failed before verified evidence could be produced."
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
            entry["private_values_persisted"] = False
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
                else pending_error or "Mapping preflight failed."
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
        payloads.clear()
        if private is not None:
            private.clear()
        try:
            _assert_value_free_public_payload(report, [])
            _write_private(
                manifest_path,
                (
                    json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                ).encode("utf-8"),
            )
            manifest_written = True
        except BaseException:
            report["status"] = "failed"
            entry["status"] = "failed"
            entry["private_values_persisted"] = False
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
            "private_values_sha256": entry["private_values_sha256"],
            "executed_sql_sha256": entry["executed_sql_sha256"],
            "aggregate_summary_sha256": entry["aggregate_summary_sha256"],
            "implementation_bundle_sha256": {
                name: bundle["bundle_sha256"]
                for name, bundle in observed_implementation_bundles.items()
            },
        })
    else:
        result["note"] = (
            "No raw preflight value artifact was retained unless rollback and a "
            "clean psql exit had both already been confirmed."
        )
    return result

