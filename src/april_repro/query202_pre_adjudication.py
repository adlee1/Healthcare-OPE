"""Fail-closed runner for D005 Query-202 pre-adjudication evidence v2.

The database phase executes nine complete typed-boundary statements followed by
seven independently bounded physical statements for each of 64 subject
buckets in one PostgreSQL REPEATABLE READ READ ONLY transaction.  Database
frames are held only in an anonymous mode-0600 spool until an explicit rollback
and a clean psql exit have both been confirmed.  Only then may exact private
evidence be merged and persisted.

This component extracts local evidence.  It never decides product identity,
maps a route, accepts a source policy, constructs an action/episode/label/cohort,
or emits a patient, admission, event, order identifier, timestamp, raw local
value, NDC, or per-value hash in public metadata.
"""
from __future__ import annotations

import base64
import binascii
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import heapq
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import struct
import tempfile
import time
from typing import Any, Iterable, Mapping
import zlib

from .database import DatabaseError, PsqlClient, _statement_body
from .query202_preadjudication_sql_v2 import (
    BOUNDARY_FRAME_COLUMNS as SQL_BOUNDARY_FRAME_COLUMNS,
    BOUNDARY_STAGES as SQL_BOUNDARY_STAGES,
    BUCKET_COUNT as SQL_BUCKET_COUNT,
    BucketStatementSpec,
    BUCKET_STATEMENTS as SQL_BUCKET_STATEMENTS,
    BUCKET_STATEMENTS_BY_LOGICAL_STAGE as SQL_BUCKET_STATEMENTS_BY_LOGICAL_STAGE,
    BUCKET_STATEMENT_CONTROL_NAMES,
    CONTROL_NAMES,
    FRAME_COLUMNS as SQL_CROSSWALK_COLUMNS,
    TUPLE_FIELDS,
    decode_and_validate_tuple_payload,
    render_bucket_sql,
)
from .staged_source_closure import _PersistentPsql


QUERY_NAME = "potassium_query202_pre_adjudication"
COMPONENT_ID = "D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2"
CONFIG_PATH = "config/preregistrations/d005_potassium_query202_pre_adjudication_v2.toml"
BUCKET_COUNT = SQL_BUCKET_COUNT
STATEMENT_TIMEOUT_MS = 120_000
PROCESS_TIMEOUT_SECONDS = 135
PUBLIC_FAILURE_ERROR = (
    "Query-202 v2 failed before verified evidence could be produced."
)
BOUNDARY_SCHEMA_VERSION = "2"
CROSSWALK_SCHEMA_VERSION = "2"
MAX_STAGE_FRAME_BYTES = 512 * 1024 * 1024
MAX_BOUNDARY_FRAME_BYTES = 256 * 1024 * 1024
MAX_CUMULATIVE_RAW_FRAME_BYTES = 16 * 1024 * 1024 * 1024
MAX_CUMULATIVE_SPOOL_BYTES = 4 * 1024 * 1024 * 1024
MAX_ANONYMOUS_RUN_RAW_BYTES = 16 * 1024 * 1024 * 1024
MAX_ANONYMOUS_RUN_SPOOL_BYTES = 4 * 1024 * 1024 * 1024
MAX_PRIVATE_ARTIFACT_RAW_BYTES = 16 * 1024 * 1024 * 1024
MAX_PRIVATE_ARTIFACT_STORED_BYTES = 4 * 1024 * 1024 * 1024
MAX_PRIVATE_ARTIFACT_LINE_BYTES = 8 * 1024 * 1024
PRIVATE_ARTIFACT_ENCODING = "gzip+utf8+ndjson-v1"
DISK_FREE_SPACE_RESERVE_BYTES = 512 * 1024 * 1024
MIN_FREE_SPACE_BEFORE_DATABASE_BYTES = (
    max(
        MAX_CUMULATIVE_SPOOL_BYTES + MAX_ANONYMOUS_RUN_SPOOL_BYTES,
        MAX_ANONYMOUS_RUN_SPOOL_BYTES + MAX_PRIVATE_ARTIFACT_STORED_BYTES,
    )
    + DISK_FREE_SPACE_RESERVE_BYTES
)
MAX_EXECUTED_SQL_BYTES = 16 * 1024 * 1024
MAX_VALUE_UTF8_BYTES = 1024 * 1024
MAX_BOUNDARY_GROUPS = 1_000_000
MAX_TUPLE_GROUPS_PER_BUCKET = 5_000_000
MAX_EXACT_COUNT = (1 << 63) - 1
MAX_MERGED_COUNT = MAX_EXACT_COUNT
SNAPSHOT_PATTERN = re.compile(r"^[0-9]+:[0-9]+:[0-9,]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SAFE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")

BOUNDARY_SET_HASH_VERSION = b"typed-distinct-source-value-set-v1"
SEMANTIC_SEED_HASH_VERSION = b"source-field-nonnull-exact-value-set-v1"
TUPLE_ENCODING_VERSION = b"query202-pre-adjudication-exact-typed-tuple-v1"
TUPLE_SET_HASH_VERSION = b"query202-pre-adjudication-tuple-set-v1"
TUPLE_FREQUENCY_HASH_VERSION = b"query202-pre-adjudication-tuple-frequency-v1"

BOUNDARY_COLUMNS = SQL_BOUNDARY_FRAME_COLUMNS
CROSSWALK_COLUMNS = SQL_CROSSWALK_COLUMNS

FALSE_GUARDS = (
    "pre_adjudication_extraction_implemented",
    "pre_adjudication_extraction_executed",
    "reviewed_semantic_ledger_frozen",
    "route_mapping_frozen",
    "external_ndc_mapping_executed",
    "event_mapping_created",
    "product_identity_decided",
    "product_mapping_accepted",
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

# These names must never occur in a persisted tuple.  The SQL phase may use
# identifiers transiently to verify exact links and bucket assignment, but only
# aggregated identifier-free evidence is allowed across the rollback boundary.
FORBIDDEN_PRIVATE_TUPLE_FIELDS = frozenset({
    "subject_id",
    "hadm_id",
    "emar_id",
    "emar_seq",
    "pharmacy_id",
    "poe_id",
    "poe_seq",
    "order_id",
    "charttime",
    "scheduletime",
    "storetime",
    "entertime",
    "starttime",
    "stoptime",
    "endtime",
})


@dataclass(frozen=True)
class BoundarySpec:
    stage: str
    source_key: str
    source_field: str
    sql_file: str
    semantic_seed: bool


@dataclass(frozen=True)
class CrosswalkSpec:
    stage: str
    tuple_kinds: tuple[str, ...]


BOUNDARY_STAGES = tuple(
    BoundarySpec(
        item.stage,
        item.source_key,
        item.source_field,
        item.sql_path,
        item.semantic_seed_field,
    )
    for item in SQL_BOUNDARY_STAGES
)

CROSSWALK_STAGES = (
    CrosswalkSpec(
        "202b",
        tuple(TUPLE_FIELDS["202b"]),
    ),
    CrosswalkSpec(
        "202c",
        tuple(TUPLE_FIELDS["202c"]),
    ),
)

# ``CROSSWALK_STAGES`` remains the two-stage scientific output contract.
# These seven objects are only physical statement boundaries; their frames are
# recombined into one logical fragment per stage and bucket after rollback.
CROSSWALK_STATEMENTS = SQL_BUCKET_STATEMENTS
CROSSWALK_STATEMENTS_BY_LOGICAL_STAGE = SQL_BUCKET_STATEMENTS_BY_LOGICAL_STAGE
BUCKET_INPUT_SOURCE_BOUNDARY_KEY = {
    "mimiciv_hosp.emar": "emar_medication",
    "mimiciv_hosp.emar_detail": "detail_product_description",
    "mimiciv_hosp.pharmacy": "pharmacy_medication",
    "mimiciv_hosp.prescriptions": "prescription_drug",
}

BOUNDARY_BY_KEY = {item.source_key: item for item in BOUNDARY_STAGES}
CROSSWALK_BY_STAGE = {item.stage: item for item in CROSSWALK_STAGES}

IMPLEMENTATION_BUNDLE_PATHS = {
    "sql": (
        *(item.sql_file for item in BOUNDARY_STAGES),
        *(item.sql_path for item in CROSSWALK_STATEMENTS),
    ),
    "runner": (
        "src/april_repro/query202_preadjudication_sql_v2.py",
        "src/april_repro/query202_pre_adjudication.py",
        "scripts/run_potassium_query202_pre_adjudication.py",
        "src/april_repro/database.py",
        "src/april_repro/staged_source_closure.py",
        "src/april_repro/query202_readonly_explain_attestation.py",
        "scripts/attest_potassium_query202_pre_adjudication_explain.py",
    ),
    "offline_auditor": (
        "src/april_repro/query202_pre_adjudication_preregistration_v2.py",
        "src/april_repro/query202_pre_adjudication_audit.py",
        "scripts/audit_potassium_query202_pre_adjudication.py",
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _mode(path: Path) -> str:
    return format(stat.S_IMODE(path.stat().st_mode), "04o")


def _strict_uint(value: str, label: str, maximum: int = MAX_EXACT_COUNT) -> int:
    if not isinstance(value, str) or re.fullmatch(r"0|[1-9][0-9]*", value) is None:
        raise DatabaseError(f"{label} returned a malformed nonnegative integer.")
    number = int(value)
    if number > maximum:
        raise DatabaseError(f"{label} exceeded its integer limit.")
    return number


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


def _implementation_bundle(root: Path, paths: tuple[str, ...]) -> dict[str, Any]:
    digest = hashlib.sha256()
    files: list[dict[str, Any]] = []
    for relative_text in paths:
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise DatabaseError("A Query-202 v2 implementation path is unsafe.")
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise DatabaseError("A required Query-202 v2 implementation file is absent.")
        path_bytes = relative_text.encode("utf-8")
        data = path.read_bytes()
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


def _remove_values(paths: Iterable[Path]) -> bool:
    paths = list(paths)
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return not any(path.exists() for path in paths)


def _require_database_disk_headroom(directory: Path) -> int:
    """Fail closed unless the artifact filesystem can hold one bounded phase.

    Frame and sorted-run spools coexist while logical runs are built; the run
    spool and compressed private artifact coexist during external merge.  The
    reserve covers metadata, filesystem accounting, and concurrent activity.
    """
    try:
        free_bytes = shutil.disk_usage(directory).free
    except (OSError, ValueError) as exc:
        raise DatabaseError(
            "Query-202 could not verify free disk space before database execution."
        ) from exc
    if isinstance(free_bytes, bool) or not isinstance(free_bytes, int) or free_bytes < 0:
        raise DatabaseError(
            "Query-202 could not verify free disk space before database execution."
        )
    if free_bytes < MIN_FREE_SPACE_BEFORE_DATABASE_BYTES:
        raise DatabaseError(
            "Query-202 has insufficient free disk space before database execution."
        )
    return free_bytes


@dataclass(frozen=True)
class _CompressedFrameIndex:
    offset: int
    stored_bytes: int
    raw_bytes: int
    raw_sha256: bytes


class _AnonymousFrameSpool:
    """One unlinked mode-0600 file holding independent zlib frame members."""

    _COMPRESSION_LEVEL = 6
    _COMPRESSION_CHUNK_BYTES = 1024 * 1024

    def __init__(self, directory: Path):
        self._handle = tempfile.TemporaryFile(mode="w+b", dir=directory)
        os.fchmod(self._handle.fileno(), 0o600)
        observed = os.fstat(self._handle.fileno())
        if stat.S_IMODE(observed.st_mode) != 0o600 or observed.st_nlink != 0:
            self._handle.close()
            raise DatabaseError("The private frame spool is not anonymous mode 0600.")
        self._frames: dict[str, _CompressedFrameIndex] = {}
        self.total_raw_bytes = 0
        self.total_stored_bytes = 0
        self._closed = False

    def append(self, label: str, payload: bytes) -> int:
        if self._closed:
            raise DatabaseError("The private Query-202 frame spool is closed.")
        if label in self._frames:
            raise DatabaseError("A Query-202 frame label was repeated.")
        if not isinstance(payload, bytes) or not payload:
            raise DatabaseError("A Query-202 frame payload is malformed.")
        if (
            len(payload) > MAX_CUMULATIVE_RAW_FRAME_BYTES
            or self.total_raw_bytes
            > MAX_CUMULATIVE_RAW_FRAME_BYTES - len(payload)
        ):
            raise DatabaseError(
                "Query-202 cumulative raw frame output exceeded its limit."
            )
        self._handle.seek(0, os.SEEK_END)
        offset = self._handle.tell()
        compressor = zlib.compressobj(level=self._COMPRESSION_LEVEL)
        stored_bytes = 0

        def write_compressed(chunk: bytes) -> None:
            nonlocal stored_bytes
            if not chunk:
                return
            if (
                len(chunk) > MAX_CUMULATIVE_SPOOL_BYTES
                or self.total_stored_bytes
                > MAX_CUMULATIVE_SPOOL_BYTES - stored_bytes - len(chunk)
            ):
                raise DatabaseError(
                    "Query-202 cumulative anonymous spool output exceeded its limit."
                )
            written = self._handle.write(chunk)
            if written != len(chunk):
                raise OSError("The private Query-202 frame spool write was incomplete.")
            stored_bytes += written

        try:
            view = memoryview(payload)
            for start in range(0, len(payload), self._COMPRESSION_CHUNK_BYTES):
                write_compressed(
                    compressor.compress(
                        view[start:start + self._COMPRESSION_CHUNK_BYTES]
                    )
                )
            write_compressed(compressor.flush(zlib.Z_FINISH))
        except BaseException:
            try:
                self._handle.seek(offset)
                self._handle.truncate(offset)
            except OSError:
                pass
            raise
        if stored_bytes <= 0:
            try:
                self._handle.seek(offset)
                self._handle.truncate(offset)
            except OSError:
                pass
            raise DatabaseError("A Query-202 compressed frame is empty.")
        self._frames[label] = _CompressedFrameIndex(
            offset=offset,
            stored_bytes=stored_bytes,
            raw_bytes=len(payload),
            raw_sha256=hashlib.sha256(payload).digest(),
        )
        self.total_raw_bytes += len(payload)
        self.total_stored_bytes += stored_bytes
        return stored_bytes

    def read(self, label: str) -> bytes:
        if self._closed:
            raise DatabaseError("The private Query-202 frame spool is closed.")
        try:
            frame = self._frames[label]
        except KeyError as exc:
            raise DatabaseError("A Query-202 frame is absent from the private spool.") from exc
        self._handle.seek(frame.offset)
        compressed = self._handle.read(frame.stored_bytes)
        if len(compressed) != frame.stored_bytes:
            raise DatabaseError("The private Query-202 frame spool was truncated.")
        try:
            decompressor = zlib.decompressobj()
            payload = decompressor.decompress(compressed, frame.raw_bytes + 1)
        except zlib.error as exc:
            raise DatabaseError(
                "The private Query-202 compressed frame is corrupt."
            ) from exc
        if any((
            len(payload) > frame.raw_bytes,
            not decompressor.eof,
            bool(decompressor.unconsumed_tail),
            bool(decompressor.unused_data),
        )):
            raise DatabaseError(
                "The private Query-202 compressed frame failed integrity validation."
            )
        try:
            flushed = decompressor.flush()
        except zlib.error as exc:
            raise DatabaseError(
                "The private Query-202 compressed frame is corrupt."
            ) from exc
        if any((
            bool(flushed),
            len(payload) != frame.raw_bytes,
            hashlib.sha256(payload).digest() != frame.raw_sha256,
        )):
            raise DatabaseError(
                "The private Query-202 compressed frame failed integrity validation."
            )
        return payload

    @property
    def labels(self) -> set[str]:
        return set(self._frames)

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if not self._closed:
            self._frames.clear()
            self._handle.close()
            self._closed = True


@dataclass(frozen=True)
class _CompressedRunIndex:
    offset: int
    stored_bytes: int
    raw_bytes: int
    raw_sha256: bytes
    records: int


def _compact_json_line(value: Mapping[str, Any]) -> bytes:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise DatabaseError("A Query-202 private NDJSON record is malformed.") from exc
    if len(payload) > MAX_PRIVATE_ARTIFACT_LINE_BYTES:
        raise DatabaseError("A Query-202 private NDJSON record exceeded its line limit.")
    return payload


def _unique_json_object(payload: bytes, label: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise DatabaseError(f"A Query-202 {label} repeated a JSON key.")
            value[key] = item
        return value

    try:
        value = json.loads(payload, object_pairs_hook=unique)
    except DatabaseError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DatabaseError(f"A Query-202 {label} is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise DatabaseError(f"A Query-202 {label} is not a JSON object.")
    return value


class _AnonymousSortedRunSpool:
    """Anonymous compressed logical-bucket runs for bounded external merging."""

    _COMPRESSION_LEVEL = 6
    # Sixty-four iterators are live during each k-way merge.  Keep each
    # iterator's decoded batch small so the fixed merge working set remains
    # comfortably bounded even when records are short.
    _IO_CHUNK_BYTES = 128 * 1024

    def __init__(self, directory: Path):
        self._handle = tempfile.TemporaryFile(mode="w+b", dir=directory)
        os.fchmod(self._handle.fileno(), 0o600)
        observed = os.fstat(self._handle.fileno())
        if stat.S_IMODE(observed.st_mode) != 0o600 or observed.st_nlink != 0:
            self._handle.close()
            raise DatabaseError("The private Query-202 sorted-run spool is not anonymous mode 0600.")
        self._runs: dict[str, _CompressedRunIndex] = {}
        self.total_raw_bytes = 0
        self.total_stored_bytes = 0
        self._closed = False

    def append(self, label: str, records: Iterable[Mapping[str, Any]]) -> int:
        if self._closed:
            raise DatabaseError("The private Query-202 sorted-run spool is closed.")
        if label in self._runs:
            raise DatabaseError("A Query-202 sorted-run label was repeated.")
        self._handle.seek(0, os.SEEK_END)
        offset = self._handle.tell()
        compressor = zlib.compressobj(level=self._COMPRESSION_LEVEL)
        raw_digest = hashlib.sha256()
        raw_bytes = 0
        stored_bytes = 0
        record_count = 0
        previous: bytes | None = None
        raw_buffer = bytearray()

        def write_compressed(chunk: bytes) -> None:
            nonlocal stored_bytes
            if not chunk:
                return
            if (
                len(chunk) > MAX_ANONYMOUS_RUN_SPOOL_BYTES
                or self.total_stored_bytes
                > MAX_ANONYMOUS_RUN_SPOOL_BYTES - stored_bytes - len(chunk)
            ):
                raise DatabaseError(
                    "Query-202 cumulative anonymous sorted-run output exceeded its limit."
                )
            written = self._handle.write(chunk)
            if written != len(chunk):
                raise OSError("The private Query-202 sorted-run spool write was incomplete.")
            stored_bytes += written

        try:
            for record in records:
                encoded = record.get("encoded_tuple")
                kind = record.get("tuple_kind")
                value = record.get("tuple")
                multiplicity = record.get("multiplicity")
                if (
                    not isinstance(encoded, bytes)
                    or (previous is not None and encoded <= previous)
                    or not isinstance(kind, str)
                    or not isinstance(value, Mapping)
                    or type(multiplicity) is not int
                    or not 0 < multiplicity <= MAX_EXACT_COUNT
                ):
                    raise DatabaseError("A Query-202 logical sorted run is malformed.")
                line = _compact_json_line({
                    "multiplicity": multiplicity,
                    "tuple": dict(value),
                    "tuple_kind": kind,
                })
                if (
                    len(line) > MAX_ANONYMOUS_RUN_RAW_BYTES
                    or self.total_raw_bytes
                    > MAX_ANONYMOUS_RUN_RAW_BYTES - raw_bytes - len(line)
                ):
                    raise DatabaseError(
                        "Query-202 cumulative anonymous sorted-run raw output exceeded its limit."
                    )
                raw_digest.update(line)
                raw_bytes += len(line)
                record_count += 1
                previous = encoded
                raw_buffer.extend(line)
                if len(raw_buffer) >= self._IO_CHUNK_BYTES:
                    write_compressed(compressor.compress(raw_buffer))
                    raw_buffer.clear()
            if raw_buffer:
                write_compressed(compressor.compress(raw_buffer))
            write_compressed(compressor.flush(zlib.Z_FINISH))
            self._handle.flush()
        except BaseException:
            try:
                self._handle.seek(offset)
                self._handle.truncate(offset)
            except OSError:
                pass
            raise
        if stored_bytes <= 0:
            try:
                self._handle.seek(offset)
                self._handle.truncate(offset)
            except OSError:
                pass
            raise DatabaseError("A Query-202 compressed sorted run is empty.")
        self._runs[label] = _CompressedRunIndex(
            offset=offset,
            stored_bytes=stored_bytes,
            raw_bytes=raw_bytes,
            raw_sha256=raw_digest.digest(),
            records=record_count,
        )
        self.total_raw_bytes += raw_bytes
        self.total_stored_bytes += stored_bytes
        return stored_bytes

    def iter_records(
        self, label: str, spec: CrosswalkSpec
    ) -> Iterable[dict[str, Any]]:
        if self._closed:
            raise DatabaseError("The private Query-202 sorted-run spool is closed.")
        try:
            run = self._runs[label]
        except KeyError as exc:
            raise DatabaseError("A Query-202 logical sorted run is absent.") from exc
        descriptor = self._handle.fileno()
        decompressor = zlib.decompressobj()
        compressed_offset = run.offset
        compressed_remaining = run.stored_bytes
        raw_digest = hashlib.sha256()
        raw_bytes = 0
        record_count = 0
        buffer = bytearray()
        previous: bytes | None = None

        def consume(chunk: bytes) -> Iterable[dict[str, Any]]:
            nonlocal raw_bytes, record_count, previous
            if not chunk:
                return ()
            if raw_bytes > run.raw_bytes - len(chunk):
                raise DatabaseError("A Query-202 sorted run exceeded its indexed raw size.")
            raw_bytes += len(chunk)
            raw_digest.update(chunk)
            buffer.extend(chunk)
            output: list[dict[str, Any]] = []
            consumed = 0
            while True:
                newline = buffer.find(b"\n", consumed)
                if newline < 0:
                    if len(buffer) - consumed > MAX_PRIVATE_ARTIFACT_LINE_BYTES:
                        raise DatabaseError("A Query-202 sorted-run record exceeded its line limit.")
                    break
                line = bytes(buffer[consumed:newline])
                consumed = newline + 1
                if not line or len(line) + 1 > MAX_PRIVATE_ARTIFACT_LINE_BYTES:
                    raise DatabaseError("A Query-202 sorted-run record is malformed.")
                stored = _unique_json_object(line, "sorted-run record")
                if set(stored) != {"multiplicity", "tuple", "tuple_kind"}:
                    raise DatabaseError("A Query-202 sorted-run record has an invalid schema.")
                kind = stored["tuple_kind"]
                value = stored["tuple"]
                multiplicity = stored["multiplicity"]
                if (
                    kind not in spec.tuple_kinds
                    or type(multiplicity) is not int
                    or not 0 < multiplicity <= MAX_EXACT_COUNT
                ):
                    raise DatabaseError("A Query-202 sorted-run record has invalid values.")
                canonical, canonical_json = _canonical_tuple_object(value)
                if len(canonical_json) > MAX_VALUE_UTF8_BYTES:
                    raise DatabaseError("A Query-202 sorted-run tuple exceeded its JSON limit.")
                try:
                    validated = decode_and_validate_tuple_payload(
                        spec.stage,
                        kind,
                        base64.b64encode(canonical_json).decode("ascii"),
                    )
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                    raise DatabaseError("A Query-202 sorted-run tuple is invalid.") from exc
                if validated != canonical:
                    raise DatabaseError("A Query-202 sorted-run tuple changed canonical value.")
                encoded = encode_typed_tuple(spec.stage, kind, canonical)
                if previous is not None and encoded <= previous:
                    raise DatabaseError("A Query-202 logical sorted run is not strictly ordered.")
                previous = encoded
                record_count += 1
                output.append({
                    "tuple_kind": kind,
                    "tuple": canonical,
                    "tuple_canonical_json": canonical_json,
                    "encoded_tuple": encoded,
                    "multiplicity": multiplicity,
                })
            if consumed:
                del buffer[:consumed]
            return output

        try:
            while compressed_remaining:
                amount = min(self._IO_CHUNK_BYTES, compressed_remaining)
                compressed = os.pread(descriptor, amount, compressed_offset)
                if len(compressed) != amount:
                    raise DatabaseError("The private Query-202 sorted-run spool was truncated.")
                compressed_offset += amount
                compressed_remaining -= amount
                pending = compressed
                while pending:
                    output = decompressor.decompress(pending, self._IO_CHUNK_BYTES)
                    pending = decompressor.unconsumed_tail
                    for record in consume(output):
                        yield record
                    if decompressor.eof:
                        if pending or compressed_remaining or decompressor.unused_data:
                            raise DatabaseError("A Query-202 sorted run has trailing compressed data.")
                        break
            if not decompressor.eof:
                raise DatabaseError("A Query-202 sorted run failed integrity validation.")
            # At zlib EOF this is expected to be empty.  Cap the call anyway so
            # corrupt input can never turn finalization into an unbounded
            # allocation.
            flushed = decompressor.flush(self._IO_CHUNK_BYTES)
            if len(flushed) == self._IO_CHUNK_BYTES:
                raise DatabaseError("A Query-202 sorted run has an oversized compressed tail.")
            for record in consume(flushed):
                yield record
        except zlib.error as exc:
            raise DatabaseError("A Query-202 compressed sorted run is corrupt.") from exc
        if any((
            not decompressor.eof,
            bool(decompressor.unconsumed_tail),
            bool(decompressor.unused_data),
            bool(buffer),
            raw_bytes != run.raw_bytes,
            raw_digest.digest() != run.raw_sha256,
            record_count != run.records,
        )):
            raise DatabaseError("A Query-202 sorted run failed integrity validation.")

    @property
    def labels(self) -> set[str]:
        return set(self._runs)

    def stage_ledger(self) -> dict[str, dict[str, int]]:
        """Return an aggregate that can be persisted without exposing values."""
        if self._closed:
            raise DatabaseError("The private Query-202 sorted-run spool is closed.")
        ledger: dict[str, dict[str, int]] = {}
        for spec in CROSSWALK_STAGES:
            runs = [
                self._runs.get(f"{spec.stage}_bucket_{index}")
                for index in range(BUCKET_COUNT)
            ]
            if any(run is None for run in runs):
                raise DatabaseError("The Query-202 sorted-run spool has an incomplete inventory.")
            present = [run for run in runs if run is not None]
            ledger[spec.stage] = {
                "runs": len(present),
                "record_count": sum(run.records for run in present),
                "raw_bytes": sum(run.raw_bytes for run in present),
                "spool_bytes": sum(run.stored_bytes for run in present),
            }
        return ledger

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if not self._closed:
            self._runs.clear()
            self._handle.close()
            self._closed = True


class _BoundedStoredWriter:
    def __init__(self, handle: Any, limit: int):
        self._handle = handle
        self._limit = limit
        self.bytes_written = 0
        self.sha256 = hashlib.sha256()

    def write(self, payload: bytes) -> int:
        if len(payload) > self._limit or self.bytes_written > self._limit - len(payload):
            raise DatabaseError("Query-202 compressed private evidence exceeded its stored byte limit.")
        written = self._handle.write(payload)
        if written != len(payload):
            raise OSError("The Query-202 compressed private artifact write was incomplete.")
        self.sha256.update(payload)
        self.bytes_written += written
        return written

    def flush(self) -> None:
        self._handle.flush()

    def tell(self) -> int:
        return self.bytes_written


class _GzipNdjsonWriter:
    """Deterministic, bounded, mode-0600 gzip NDJSON artifact writer."""

    def __init__(self, path: Path):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        self.path = path
        self._raw_handle: Any | None = None
        self._gzip: gzip.GzipFile | None = None
        self._stored: _BoundedStoredWriter | None = None
        self.raw_bytes = 0
        self.raw_sha256 = hashlib.sha256()
        self.records = 0
        self._pending = bytearray()
        self._finished = False
        try:
            descriptor = os.open(path, flags, 0o600)
            self._raw_handle = os.fdopen(descriptor, "wb")
            os.fchmod(self._raw_handle.fileno(), 0o600)
            self._stored = _BoundedStoredWriter(
                self._raw_handle, MAX_PRIVATE_ARTIFACT_STORED_BYTES
            )
            self._gzip = gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=6,
                fileobj=self._stored,
                mtime=0,
            )
        except BaseException:
            self.abort()
            raise

    def write_record(self, value: Mapping[str, Any]) -> None:
        if self._finished or self._gzip is None:
            raise DatabaseError("The Query-202 private NDJSON writer is closed.")
        line = _compact_json_line(value)
        if (
            len(line) > MAX_PRIVATE_ARTIFACT_RAW_BYTES
            or self.raw_bytes > MAX_PRIVATE_ARTIFACT_RAW_BYTES - len(line)
        ):
            raise DatabaseError("Query-202 private evidence exceeded its raw byte limit.")
        self.raw_sha256.update(line)
        self.raw_bytes += len(line)
        self.records += 1
        self._pending.extend(line)
        if len(self._pending) >= 1024 * 1024:
            self._gzip.write(self._pending)
            self._pending.clear()

    def finish(self) -> dict[str, Any]:
        if self._finished or self._gzip is None or self._raw_handle is None or self._stored is None:
            raise DatabaseError("The Query-202 private NDJSON writer is closed.")
        try:
            if self._pending:
                self._gzip.write(self._pending)
                self._pending.clear()
            self._gzip.close()
            self._gzip = None
            self._raw_handle.flush()
            os.fsync(self._raw_handle.fileno())
            self._raw_handle.close()
            self._raw_handle = None
            self._finished = True
            return {
                "encoding": PRIVATE_ARTIFACT_ENCODING,
                "bytes": self._stored.bytes_written,
                "sha256": self._stored.sha256.hexdigest(),
                "raw_bytes": self.raw_bytes,
                "raw_sha256": self.raw_sha256.hexdigest(),
                "records": self.records,
            }
        except BaseException:
            self.abort()
            raise

    def abort(self) -> None:
        if self._finished:
            return
        if self._gzip is not None:
            try:
                self._gzip.close()
            except BaseException:
                pass
            self._gzip = None
        if self._raw_handle is not None:
            try:
                self._raw_handle.close()
            except BaseException:
                pass
            self._raw_handle = None
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass
        self._pending.clear()
        self._finished = True


def typed_boundary_set_sha256(
    source_field: str, records: Iterable[Mapping[str, Any]]
) -> str:
    records = list(records)
    field = source_field.encode("utf-8")
    null_seen = False
    nonnull: list[bytes] = []
    for record in records:
        if record.get("raw_is_null") is True and record.get("raw_value") is None:
            if null_seen:
                raise DatabaseError("A typed-boundary set repeats SQL NULL.")
            null_seen = True
        elif record.get("raw_is_null") is False and isinstance(record.get("raw_value"), str):
            encoded = record["raw_value"].encode("utf-8")
            if len(encoded) > MAX_VALUE_UTF8_BYTES or b"\x00" in encoded:
                raise DatabaseError("A typed-boundary value exceeds its byte contract.")
            nonnull.append(encoded)
        else:
            raise DatabaseError("A typed-boundary record is malformed.")
    if len(nonnull) != len(set(nonnull)):
        raise DatabaseError("A typed-boundary set repeats a non-NULL exact value.")
    nonnull.sort()
    digest = hashlib.sha256()
    digest.update(BOUNDARY_SET_HASH_VERSION)
    digest.update(struct.pack(">I", len(field)))
    digest.update(field)
    digest.update(struct.pack(">Q", len(nonnull) + int(null_seen)))
    if null_seen:
        digest.update(b"\x00")
    for encoded in nonnull:
        digest.update(b"\x01")
        digest.update(struct.pack(">Q", len(encoded)))
        digest.update(encoded)
    return digest.hexdigest()


def nonnull_source_set_sha256(
    source_field: str, records: Iterable[Mapping[str, Any]]
) -> str:
    """Hash one exact non-NULL source-field set using the Q201 seed framing."""
    source = source_field.encode("utf-8")
    values = sorted(
        record["raw_value"].encode("utf-8")
        for record in records
        if record.get("raw_is_null") is False
        and isinstance(record.get("raw_value"), str)
    )
    if len(values) != len(set(values)):
        raise DatabaseError("A boundary non-NULL exact set contains a duplicate.")
    digest = hashlib.sha256()
    digest.update(SEMANTIC_SEED_HASH_VERSION)
    digest.update(struct.pack(">Q", len(values)))
    for value in values:
        digest.update(struct.pack(">I", len(source)))
        digest.update(source)
        digest.update(struct.pack(">Q", len(value)))
        digest.update(value)
    return digest.hexdigest()


def _semantic_seed_records(
    boundaries: Mapping[str, Mapping[str, Any]]
) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    for spec in BOUNDARY_STAGES:
        if not spec.semantic_seed:
            continue
        source = boundaries.get(spec.source_key)
        if not isinstance(source, Mapping):
            raise DatabaseError("The semantic-seed boundary source is absent.")
        for record in source.get("records", []):
            if record.get("raw_is_null") is False:
                raw = record.get("raw_value")
                if not isinstance(raw, str):
                    raise DatabaseError("A semantic-seed exact value is malformed.")
                keys.append((spec.source_field, raw))
    keys.sort(key=lambda item: (item[0].encode("utf-8"), item[1].encode("utf-8")))
    if len(keys) != len(set(keys)):
        raise DatabaseError("The semantic-seed key set contains a duplicate key.")
    return keys


def semantic_seed_set_sha256(
    boundaries: Mapping[str, Mapping[str, Any]]
) -> tuple[int, str]:
    keys = _semantic_seed_records(boundaries)
    digest = hashlib.sha256()
    digest.update(SEMANTIC_SEED_HASH_VERSION)
    digest.update(struct.pack(">Q", len(keys)))
    for source, value in keys:
        source = source.encode("utf-8")
        value = value.encode("utf-8")
        digest.update(struct.pack(">I", len(source)))
        digest.update(source)
        digest.update(struct.pack(">Q", len(value)))
        digest.update(value)
    return len(keys), digest.hexdigest()


def _decode_boundary_frame(frame: bytes, spec: BoundarySpec) -> dict[str, Any]:
    if not isinstance(frame, bytes) or len(frame) > MAX_BOUNDARY_FRAME_BYTES:
        raise DatabaseError("A Query-202 boundary frame exceeded its byte limit.")
    try:
        text = frame.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise DatabaseError("A Query-202 boundary frame is malformed.") from exc
    if reader.fieldnames != list(BOUNDARY_COLUMNS) or not rows:
        raise DatabaseError("A Query-202 boundary frame has unexpected columns or no rows.")
    if len(rows) > MAX_BOUNDARY_GROUPS + 1:
        raise DatabaseError("A Query-202 boundary frame exceeded its group limit.")

    controls: tuple[str, str, str] | None = None
    records: list[dict[str, Any]] = []
    seen: set[tuple[bool, str | None]] = set()
    null_observations = 0
    sql_null_rows: int | None = None
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise DatabaseError("A Query-202 boundary row is malformed.")
        if (
            row["schema_version"] != BOUNDARY_SCHEMA_VERSION
            or row["stage"] != spec.stage
            or row["source_key"] != spec.source_key
            or row["source_field"] != spec.source_field
        ):
            raise DatabaseError("A Query-202 boundary row has invalid identity metadata.")
        observed_controls = (
            row["transaction_isolation"],
            row["transaction_read_only"],
            _snapshot_token(row["snapshot_token"], spec.stage),
        )
        if observed_controls[:2] != ("repeatable read", "on"):
            raise DatabaseError("A Query-202 boundary row did not confirm RR/RO controls.")
        if controls is None:
            controls = observed_controls
        elif controls != observed_controls:
            raise DatabaseError("A Query-202 boundary frame has inconsistent controls.")
        if row["raw_is_null"] not in ("t", "f"):
            raise DatabaseError("A Query-202 boundary row has an invalid typed-state flag.")
        is_null = row["raw_is_null"] == "t"
        count = _strict_uint(row["exact_row_count"], "Boundary exact_row_count")
        byte_count = _strict_uint(row["raw_utf8_bytes"], "Boundary raw_utf8_bytes", MAX_VALUE_UTF8_BYTES)
        if is_null:
            if row["raw_value_base64"] or byte_count != 0:
                raise DatabaseError("A Query-202 SQL-NULL boundary row is malformed.")
            raw: str | None = None
            null_observations += 1
            sql_null_rows = count
        else:
            if count == 0:
                raise DatabaseError("A non-NULL boundary group has zero frequency.")
            try:
                raw_bytes = base64.b64decode(row["raw_value_base64"], validate=True)
                raw = raw_bytes.decode("utf-8")
            except (binascii.Error, UnicodeDecodeError) as exc:
                raise DatabaseError("A Query-202 boundary value encoding is malformed.") from exc
            if len(raw_bytes) != byte_count or b"\x00" in raw_bytes:
                raise DatabaseError("A Query-202 boundary byte count is invalid.")
        identity = (is_null, raw)
        if identity in seen:
            raise DatabaseError("A Query-202 boundary frame repeated a typed value.")
        seen.add(identity)
        # The required zero SQL-NULL sentinel does not enter the typed set.
        if not (is_null and count == 0):
            records.append({
                "raw_is_null": is_null,
                "raw_value": raw,
                "raw_utf8_bytes": byte_count,
                "exact_row_count": count,
            })
    if controls is None or null_observations != 1 or sql_null_rows is None:
        raise DatabaseError("A Query-202 boundary lacks one SQL-NULL observation.")
    if len(records) > MAX_BOUNDARY_GROUPS:
        raise DatabaseError("A Query-202 boundary frame exceeded its group limit.")
    records.sort(key=lambda item: (
        not item["raw_is_null"],
        b"" if item["raw_is_null"] else item["raw_value"].encode("utf-8"),
    ))
    nonnull = sum(record["raw_is_null"] is False for record in records)
    source_rows = sum(record["exact_row_count"] for record in records)
    if source_rows > MAX_EXACT_COUNT:
        raise DatabaseError("A Query-202 boundary source denominator exceeded its limit.")
    return {
        "stage": spec.stage,
        "source_key": spec.source_key,
        "source_field": spec.source_field,
        "semantic_seed_field": spec.semantic_seed,
        "transaction_isolation": controls[0],
        "transaction_read_only": controls[1],
        "snapshot_token": controls[2],
        "sql_null_rows": sql_null_rows,
        "typed_distinct_values": len(records),
        "nonnull_distinct_values": nonnull,
        "source_rows": source_rows,
        "nonnull_set_sha256": nonnull_source_set_sha256(spec.source_field, records),
        "typed_set_sha256": typed_boundary_set_sha256(spec.source_field, records),
        "records": records,
    }


def _canonical_tuple_object(value: Any) -> tuple[dict[str, str | None], bytes]:
    if not isinstance(value, dict) or not value:
        raise DatabaseError("A Query-202 tuple JSON value must be a nonempty object.")
    if any(
        not isinstance(key, str)
        or SAFE_NAME_PATTERN.fullmatch(key) is None
        or key in FORBIDDEN_PRIVATE_TUPLE_FIELDS
        for key in value
    ):
        raise DatabaseError("A Query-202 tuple contains an unsafe or identifying field.")
    if any(item is not None and not isinstance(item, str) for item in value.values()):
        raise DatabaseError("A Query-202 tuple field must be exact text or SQL NULL.")
    canonical = {key: value[key] for key in sorted(value, key=lambda key: key.encode("utf-8"))}
    payload = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return canonical, payload


def encode_typed_tuple(stage: str, tuple_kind: str, value: Mapping[str, str | None]) -> bytes:
    output = bytearray(TUPLE_ENCODING_VERSION)
    for label in (stage, tuple_kind):
        encoded = label.encode("utf-8")
        output.extend(struct.pack(">I", len(encoded)))
        output.extend(encoded)
    items = sorted(value.items(), key=lambda item: item[0].encode("utf-8"))
    output.extend(struct.pack(">I", len(items)))
    for field, raw in items:
        field_bytes = field.encode("utf-8")
        type_bytes = b"text"
        output.extend(struct.pack(">I", len(field_bytes)))
        output.extend(field_bytes)
        output.extend(struct.pack(">H", len(type_bytes)))
        output.extend(type_bytes)
        if raw is None:
            output.extend(b"\x00")
        else:
            raw_bytes = raw.encode("utf-8")
            output.extend(b"\x01")
            output.extend(struct.pack(">Q", len(raw_bytes)))
            output.extend(raw_bytes)
    return bytes(output)


def _decode_crosswalk_frame(
    frame: bytes, spec: BucketStatementSpec, bucket_index: int
) -> dict[str, Any]:
    if not isinstance(frame, bytes) or len(frame) > MAX_STAGE_FRAME_BYTES:
        raise DatabaseError("A Query-202 crosswalk frame exceeded its byte limit.")
    try:
        text = frame.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise DatabaseError("A Query-202 crosswalk frame is malformed.") from exc
    if reader.fieldnames != list(CROSSWALK_COLUMNS) or not rows:
        raise DatabaseError("A Query-202 crosswalk frame has unexpected columns or no rows.")
    required_controls = BUCKET_STATEMENT_CONTROL_NAMES[spec.stage]
    if len(rows) > MAX_TUPLE_GROUPS_PER_BUCKET + len(required_controls):
        raise DatabaseError("A Query-202 crosswalk bucket exceeded its group limit.")
    controls: dict[str, int] = {}
    tuples: list[dict[str, Any]] = []
    seen: set[bytes] = set()
    transaction: tuple[str, str, str] | None = None
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise DatabaseError("A Query-202 crosswalk row is malformed.")
        if (
            row["schema_version"] != CROSSWALK_SCHEMA_VERSION
            or row["stage"] != spec.stage
            or _strict_uint(row["bucket_index"], "Crosswalk bucket_index", BUCKET_COUNT - 1) != bucket_index
        ):
            raise DatabaseError("A Query-202 crosswalk row has invalid stage or bucket metadata.")
        observed = (
            row["transaction_isolation"],
            row["transaction_read_only"],
            _snapshot_token(row["snapshot_token"], f"{spec.stage} bucket"),
        )
        if observed[:2] != ("repeatable read", "on"):
            raise DatabaseError("A Query-202 crosswalk row did not confirm RR/RO controls.")
        if transaction is None:
            transaction = observed
        elif transaction != observed:
            raise DatabaseError("A Query-202 crosswalk frame has inconsistent controls.")
        kind = row["record_kind"]
        if kind == "control":
            if (
                row["tuple_kind"]
                or row["tuple_json_base64"]
                or row["multiplicity"]
                or SAFE_NAME_PATTERN.fullmatch(row["control_name"]) is None
                or row["control_name"] in controls
            ):
                raise DatabaseError("A Query-202 crosswalk control row is malformed.")
            controls[row["control_name"]] = _strict_uint(
                row["control_value"], "Crosswalk control_value"
            )
        elif kind == "tuple":
            if (
                row["tuple_kind"] not in spec.tuple_kinds
                or row["control_name"]
                or row["control_value"]
            ):
                raise DatabaseError("A Query-202 crosswalk tuple row is malformed.")
            multiplicity = _strict_uint(row["multiplicity"], "Crosswalk multiplicity")
            if multiplicity == 0:
                raise DatabaseError("A Query-202 crosswalk tuple has zero multiplicity.")
            try:
                decoded = base64.b64decode(row["tuple_json_base64"], validate=True)
                if len(decoded) > MAX_VALUE_UTF8_BYTES:
                    raise DatabaseError("A Query-202 tuple JSON value exceeded its byte limit.")
                # The shared frozen SQL contract supplies the exact field set,
                # order and null/string type constraint for every tuple kind.
                parsed = decode_and_validate_tuple_payload(
                    spec.logical_stage, row["tuple_kind"], row["tuple_json_base64"]
                )
            except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                raise DatabaseError("A Query-202 tuple JSON encoding is malformed.") from exc
            value, canonical_json = _canonical_tuple_object(parsed)
            encoded = encode_typed_tuple(
                spec.logical_stage, row["tuple_kind"], value
            )
            if encoded in seen:
                raise DatabaseError("A Query-202 bucket repeated an exact typed tuple.")
            seen.add(encoded)
            tuples.append({
                "tuple_kind": row["tuple_kind"],
                "tuple": value,
                "tuple_canonical_json": canonical_json,
                "encoded_tuple": encoded,
                "multiplicity": multiplicity,
            })
        else:
            raise DatabaseError("A Query-202 crosswalk row has an unknown record kind.")
    if transaction is None:
        raise DatabaseError("A Query-202 crosswalk frame did not report controls.")
    if len(tuples) > MAX_TUPLE_GROUPS_PER_BUCKET:
        raise DatabaseError("A Query-202 crosswalk bucket exceeded its tuple-group limit.")
    required = set(required_controls)
    if set(controls) != required:
        raise DatabaseError("A Query-202 crosswalk frame has an incomplete control set.")
    if controls.get("bucket_assignment_violations", 0) != 0:
        raise DatabaseError("A Query-202 bucket reported an assignment violation.")
    if controls.get("null_subject_outside_bucket_zero", 0) != 0:
        raise DatabaseError("A Query-202 bucket reported a NULL-subject assignment violation.")
    if controls["bucket_output_multiplicity"] != sum(item["multiplicity"] for item in tuples):
        raise DatabaseError("A Query-202 bucket failed output multiplicity conservation.")
    for tuple_kind in spec.tuple_kinds:
        selected = [item for item in tuples if item["tuple_kind"] == tuple_kind]
        observed_multiplicity = sum(item["multiplicity"] for item in selected)
        if (
            controls[f"{tuple_kind}_input_rows"]
            != controls[f"{tuple_kind}_tuple_multiplicity"]
            or controls[f"{tuple_kind}_tuple_multiplicity"]
            != observed_multiplicity
        ):
            raise DatabaseError("A Query-202 tuple kind failed bucket multiplicity conservation.")
    tuples.sort(key=lambda item: item["encoded_tuple"])
    return {
        "stage": spec.logical_stage,
        "physical_stage": spec.stage,
        "bucket_input_source": spec.bucket_input_source,
        "bucket_index": bucket_index,
        "transaction_isolation": transaction[0],
        "transaction_read_only": transaction[1],
        "snapshot_token": transaction[2],
        "controls": controls,
        "records": tuples,
        "frame_bytes": len(frame),
    }


def combine_crosswalk_statement_fragments(
    spec: CrosswalkSpec,
    bucket_index: int,
    fragments: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Reconstruct one old-shape logical bucket from its physical frames.

    Physical SQL boundaries are an execution detail.  This function prevents
    them from changing the logical evidence contract by requiring the exact
    frozen part inventory, one snapshot, one disjoint owner for every tuple
    kind, and the original per-bucket size and group limits.
    """
    physical_specs = CROSSWALK_STATEMENTS_BY_LOGICAL_STAGE.get(spec.stage, ())
    expected_stages = tuple(item.stage for item in physical_specs)
    if (
        set(fragments) != set(expected_stages)
        or len(fragments) != len(expected_stages)
        or not physical_specs
    ):
        raise DatabaseError(
            "A Query-202 logical bucket lacks its exact physical statement set."
        )
    owned_kinds = tuple(
        kind for item in physical_specs for kind in item.tuple_kinds
    )
    if (
        set(owned_kinds) != set(spec.tuple_kinds)
        or len(owned_kinds) != len(spec.tuple_kinds)
    ):
        raise DatabaseError(
            "A Query-202 logical bucket has an invalid tuple-kind partition."
        )
    input_sources = tuple(
        item.bucket_input_source
        for item in physical_specs
        if item.bucket_input_source is not None
    )
    if not input_sources or len(set(input_sources)) != len(input_sources):
        raise DatabaseError(
            "A Query-202 logical bucket has an invalid input-control partition."
        )

    transaction: tuple[str, str, str] | None = None
    records: list[dict[str, Any]] = []
    seen: set[bytes] = set()
    controls: dict[str, int] = {
        "bucket_assignment_violations": 0,
        "null_subject_outside_bucket_zero": 0,
        "bucket_input_rows": 0,
        "bucket_output_multiplicity": 0,
    }
    total_frame_bytes = 0
    total_groups = 0

    def add_bounded(current: int, value: Any, label: str) -> int:
        if type(value) is not int or not 0 <= value <= MAX_EXACT_COUNT:
            raise DatabaseError(f"A Query-202 {label} is malformed.")
        if current > MAX_EXACT_COUNT - value:
            raise DatabaseError(f"A Query-202 {label} exceeded its integer limit.")
        return current + value

    for physical_spec in physical_specs:
        fragment = fragments[physical_spec.stage]
        if (
            fragment.get("stage") != spec.stage
            or fragment.get("physical_stage") != physical_spec.stage
            or fragment.get("bucket_input_source")
            != physical_spec.bucket_input_source
            or fragment.get("bucket_index") != bucket_index
        ):
            raise DatabaseError(
                "A Query-202 physical crosswalk fragment has invalid identity metadata."
            )
        observed = (
            fragment.get("transaction_isolation"),
            fragment.get("transaction_read_only"),
            _snapshot_token(
                fragment.get("snapshot_token"), physical_spec.stage
            ),
        )
        if observed[:2] != ("repeatable read", "on"):
            raise DatabaseError(
                "A Query-202 physical crosswalk fragment did not confirm RR/RO controls."
            )
        if transaction is None:
            transaction = observed
        elif transaction != observed:
            raise DatabaseError(
                "Query-202 physical statements did not share one bucket snapshot."
            )
        physical_controls = fragment.get("controls")
        physical_records = fragment.get("records")
        if (
            not isinstance(physical_controls, Mapping)
            or set(physical_controls)
            != set(BUCKET_STATEMENT_CONTROL_NAMES[physical_spec.stage])
            or not isinstance(physical_records, list)
        ):
            raise DatabaseError("A Query-202 physical crosswalk fragment is malformed.")
        frame_bytes = fragment.get("frame_bytes")
        if type(frame_bytes) is not int or frame_bytes <= 0:
            raise DatabaseError("A Query-202 physical frame byte count is malformed.")
        if total_frame_bytes > MAX_STAGE_FRAME_BYTES - frame_bytes:
            raise DatabaseError(
                "A Query-202 logical crosswalk bucket exceeded its frame byte limit."
            )
        total_frame_bytes += frame_bytes
        if total_groups > MAX_TUPLE_GROUPS_PER_BUCKET - len(physical_records):
            raise DatabaseError(
                "A Query-202 logical crosswalk bucket exceeded its tuple-group limit."
            )
        total_groups += len(physical_records)

        if physical_spec.bucket_input_source is not None:
            for name in (
                "bucket_assignment_violations",
                "null_subject_outside_bucket_zero",
                "bucket_input_rows",
            ):
                controls[name] = add_bounded(
                    controls[name], physical_controls[name], name
                )
        controls["bucket_output_multiplicity"] = add_bounded(
            controls["bucket_output_multiplicity"],
            physical_controls["bucket_output_multiplicity"],
            "bucket output multiplicity",
        )
        for kind in physical_spec.tuple_kinds:
            for suffix in ("input_rows", "tuple_multiplicity"):
                name = f"{kind}_{suffix}"
                if name in controls:
                    raise DatabaseError(
                        "A Query-202 tuple kind has more than one physical owner."
                    )
                value = physical_controls[name]
                if type(value) is not int or not 0 <= value <= MAX_EXACT_COUNT:
                    raise DatabaseError(
                        "A Query-202 physical tuple-kind control is malformed."
                    )
                controls[name] = value
        physical_output = 0
        physical_kind_outputs = {
            kind: 0 for kind in physical_spec.tuple_kinds
        }
        for record in physical_records:
            if record.get("tuple_kind") not in physical_spec.tuple_kinds:
                raise DatabaseError(
                    "A Query-202 tuple appeared outside its physical owner."
                )
            encoded = record.get("encoded_tuple")
            if not isinstance(encoded, bytes) or encoded in seen:
                raise DatabaseError(
                    "A Query-202 logical bucket repeated an exact typed tuple."
                )
            seen.add(encoded)
            multiplicity = record.get("multiplicity")
            if type(multiplicity) is not int or not 0 < multiplicity <= MAX_EXACT_COUNT:
                raise DatabaseError(
                    "A Query-202 physical tuple multiplicity is malformed."
                )
            physical_output = add_bounded(
                physical_output, multiplicity, "physical tuple multiplicity"
            )
            kind = record["tuple_kind"]
            physical_kind_outputs[kind] = add_bounded(
                physical_kind_outputs[kind],
                multiplicity,
                "physical tuple-kind multiplicity",
            )
            records.append(dict(record))
        if physical_output != physical_controls["bucket_output_multiplicity"]:
            raise DatabaseError(
                "A Query-202 physical statement failed output conservation."
            )
        for kind, output in physical_kind_outputs.items():
            if (
                output != physical_controls[f"{kind}_tuple_multiplicity"]
                or output != physical_controls[f"{kind}_input_rows"]
            ):
                raise DatabaseError(
                    "A Query-202 physical tuple kind failed multiplicity conservation."
                )

    if transaction is None or set(controls) != set(CONTROL_NAMES[spec.stage]):
        raise DatabaseError("A Query-202 logical bucket control set is incomplete.")
    if controls["bucket_assignment_violations"] != 0:
        raise DatabaseError("A Query-202 logical bucket reported an assignment violation.")
    if controls["null_subject_outside_bucket_zero"] != 0:
        raise DatabaseError(
            "A Query-202 logical bucket reported a NULL-subject assignment violation."
        )
    records.sort(key=lambda item: item["encoded_tuple"])
    if controls["bucket_output_multiplicity"] != sum(
        item["multiplicity"] for item in records
    ):
        raise DatabaseError(
            "A Query-202 logical bucket failed output multiplicity conservation."
        )
    return {
        "stage": spec.stage,
        "bucket_index": bucket_index,
        "transaction_isolation": transaction[0],
        "transaction_read_only": transaction[1],
        "snapshot_token": transaction[2],
        "controls": controls,
        "records": records,
    }


def _hash_merged_records(
    stage: str, records: list[Mapping[str, Any]]
) -> tuple[str, str]:
    set_digest = hashlib.sha256()
    frequency_digest = hashlib.sha256()
    stage_bytes = stage.encode("utf-8")
    for digest, version in (
        (set_digest, TUPLE_SET_HASH_VERSION),
        (frequency_digest, TUPLE_FREQUENCY_HASH_VERSION),
    ):
        digest.update(version)
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


def merge_crosswalk_fragments(
    spec: CrosswalkSpec,
    fragments: (
        Mapping[int, Mapping[str, Any]]
        | Iterable[tuple[int, Mapping[str, Any]]]
    ),
    *,
    expected_global_input_rows: int,
    bucket_count: int = BUCKET_COUNT,
) -> dict[str, Any]:
    """Strictly merge exact tuples; bucket hashes are never concatenated."""
    if bucket_count != BUCKET_COUNT:
        raise DatabaseError("A Query-202 crosswalk stage lacks the exact 64-bucket set.")
    if isinstance(fragments, Mapping):
        if set(fragments) != set(range(BUCKET_COUNT)):
            raise DatabaseError(
                "A Query-202 crosswalk stage lacks the exact 64-bucket set."
            )
        fragment_iterator = iter(
            (index, fragments[index]) for index in range(BUCKET_COUNT)
        )
    else:
        fragment_iterator = iter(fragments)
    snapshot: str | None = None
    if (
        type(expected_global_input_rows) is not int
        or not 0 <= expected_global_input_rows <= MAX_MERGED_COUNT
    ):
        raise DatabaseError("The Query-202 boundary-derived denominator is malformed.")
    input_sum = 0
    output_sum = 0
    per_kind_input_sums = {kind: 0 for kind in spec.tuple_kinds}
    per_kind_output_sums = {kind: 0 for kind in spec.tuple_kinds}
    merged: dict[bytes, dict[str, Any]] = {}
    for index in range(BUCKET_COUNT):
        try:
            observed_index, fragment = next(fragment_iterator)
        except StopIteration as exc:
            raise DatabaseError(
                "A Query-202 crosswalk stage lacks the exact 64-bucket set."
            ) from exc
        if (
            type(observed_index) is not int
            or observed_index != index
            or not isinstance(fragment, Mapping)
            or fragment.get("stage") != spec.stage
            or fragment.get("bucket_index") != index
        ):
            raise DatabaseError("A Query-202 crosswalk fragment has invalid identity metadata.")
        token = _snapshot_token(fragment.get("snapshot_token"), spec.stage)
        if snapshot is None:
            snapshot = token
        elif token != snapshot:
            raise DatabaseError("Query-202 crosswalk buckets did not share one snapshot.")
        controls = fragment.get("controls")
        records = fragment.get("records")
        if not isinstance(controls, Mapping) or not isinstance(records, list):
            raise DatabaseError("A Query-202 crosswalk fragment is malformed.")
        input_sum += controls["bucket_input_rows"]
        output_sum += controls["bucket_output_multiplicity"]
        for tuple_kind in spec.tuple_kinds:
            per_kind_input_sums[tuple_kind] += controls[f"{tuple_kind}_input_rows"]
            per_kind_output_sums[tuple_kind] += controls[f"{tuple_kind}_tuple_multiplicity"]
        for record in records:
            encoded = record.get("encoded_tuple")
            multiplicity = record.get("multiplicity")
            if not isinstance(encoded, bytes) or type(multiplicity) is not int:
                raise DatabaseError("A Query-202 merged tuple is malformed.")
            if encoded in merged:
                total = merged[encoded]["multiplicity"] + multiplicity
                if total > MAX_MERGED_COUNT:
                    raise DatabaseError("A Query-202 merged frequency exceeded its frozen limit.")
                merged[encoded]["multiplicity"] = total
            else:
                merged[encoded] = dict(record)
    try:
        next(fragment_iterator)
    except StopIteration:
        pass
    else:
        raise DatabaseError(
            "A Query-202 crosswalk stage has more than 64 bucket fragments."
        )
    if input_sum != expected_global_input_rows:
        raise DatabaseError("Query-202 buckets failed mutual-exclusion/completeness conservation.")
    ordered = [merged[key] for key in sorted(merged)]
    if sum(item["multiplicity"] for item in ordered) != output_sum:
        raise DatabaseError("Query-202 merged output failed multiplicity conservation.")
    set_hash, frequency_hash = _hash_merged_records(spec.stage, ordered)
    by_kind: dict[str, dict[str, Any]] = {}
    for tuple_kind in spec.tuple_kinds:
        selected = [item for item in ordered if item["tuple_kind"] == tuple_kind]
        kind_set_hash, kind_frequency_hash = _hash_merged_records(
            spec.stage + ":" + tuple_kind, selected
        )
        by_kind[tuple_kind] = {
            "unique_tuples": len(selected),
            "total_multiplicity": sum(item["multiplicity"] for item in selected),
            "summed_bucket_input_rows": per_kind_input_sums[tuple_kind],
            "summed_bucket_tuple_multiplicity": per_kind_output_sums[tuple_kind],
            "global_tuple_set_sha256": kind_set_hash,
            "global_tuple_frequency_sha256": kind_frequency_hash,
        }
        if by_kind[tuple_kind]["total_multiplicity"] != per_kind_output_sums[tuple_kind]:
            raise DatabaseError("A Query-202 tuple kind failed global multiplicity conservation.")
        if per_kind_input_sums[tuple_kind] != per_kind_output_sums[tuple_kind]:
            raise DatabaseError("A Query-202 tuple kind failed global input-row conservation.")
    return {
        "stage": spec.stage,
        "bucket_count": BUCKET_COUNT,
        "bucket_indices_complete": True,
        "assignment_unit": "subject_id",
        "sql_null_subject_bucket": 0,
        "bucket_assignment_violations": 0,
        "null_subject_outside_bucket_zero": 0,
        "global_input_rows": expected_global_input_rows,
        "global_input_rows_source": "same_snapshot_202a_boundary_source_rows",
        "summed_bucket_input_rows": input_sum,
        "global_output_multiplicity": output_sum,
        "mutual_exclusion_and_completeness_confirmed": True,
        "snapshot_token": snapshot,
        "unique_tuples": len(ordered),
        "global_tuple_set_sha256": set_hash,
        "global_tuple_frequency_sha256": frequency_hash,
        "tuple_kind_summaries": by_kind,
        "records": ordered,
    }


def _iter_merged_sorted_runs(
    spec: CrosswalkSpec,
    spool: _AnonymousSortedRunSpool,
) -> Iterable[dict[str, Any]]:
    """Merge 64 strictly sorted bucket runs while retaining one row per run."""
    expected_labels = {
        f"{item.stage}_bucket_{index}"
        for item in CROSSWALK_STAGES
        for index in range(BUCKET_COUNT)
    }
    if spool.labels != expected_labels:
        raise DatabaseError("The Query-202 sorted-run spool has an incomplete inventory.")
    iterators = [
        iter(spool.iter_records(f"{spec.stage}_bucket_{index}", spec))
        for index in range(BUCKET_COUNT)
    ]
    heap: list[tuple[bytes, int, dict[str, Any]]] = []

    def advance(index: int) -> None:
        try:
            record = next(iterators[index])
        except StopIteration:
            return
        heapq.heappush(heap, (record["encoded_tuple"], index, record))

    for index in range(BUCKET_COUNT):
        advance(index)
    previous: bytes | None = None
    while heap:
        encoded, index, record = heapq.heappop(heap)
        if previous is not None and encoded <= previous:
            raise DatabaseError("A Query-202 external merge lost strict tuple ordering.")
        multiplicity = record["multiplicity"]
        contributors = [index]
        while heap and heap[0][0] == encoded:
            _, other_index, other = heapq.heappop(heap)
            if (
                other["tuple_kind"] != record["tuple_kind"]
                or other["tuple"] != record["tuple"]
            ):
                raise DatabaseError("A Query-202 encoded tuple collision changed exact values.")
            if multiplicity > MAX_MERGED_COUNT - other["multiplicity"]:
                raise DatabaseError("A Query-202 merged frequency exceeded its frozen limit.")
            multiplicity += other["multiplicity"]
            contributors.append(other_index)
        merged = dict(record)
        merged["multiplicity"] = multiplicity
        previous = encoded
        yield merged
        for contributor in contributors:
            advance(contributor)


def _scan_external_crosswalk(
    spec: CrosswalkSpec,
    fragments: Mapping[int, Mapping[str, Any]],
    spool: _AnonymousSortedRunSpool,
    *,
    expected_global_input_rows: int,
) -> dict[str, Any]:
    """First external-merge pass: verify controls and count merged rows."""
    if set(fragments) != set(range(BUCKET_COUNT)):
        raise DatabaseError("A Query-202 crosswalk stage lacks the exact 64-bucket set.")
    if (
        type(expected_global_input_rows) is not int
        or not 0 <= expected_global_input_rows <= MAX_MERGED_COUNT
    ):
        raise DatabaseError("The Query-202 boundary-derived denominator is malformed.")
    snapshot: str | None = None
    input_sum = 0
    output_sum = 0
    per_kind_input_sums = {kind: 0 for kind in spec.tuple_kinds}
    per_kind_output_sums = {kind: 0 for kind in spec.tuple_kinds}

    def add(current: int, value: Any, label: str) -> int:
        if type(value) is not int or not 0 <= value <= MAX_MERGED_COUNT:
            raise DatabaseError(f"A Query-202 {label} is malformed.")
        if current > MAX_MERGED_COUNT - value:
            raise DatabaseError(f"A Query-202 {label} exceeded its frozen limit.")
        return current + value

    for index in range(BUCKET_COUNT):
        fragment = fragments[index]
        if (
            not isinstance(fragment, Mapping)
            or fragment.get("stage") != spec.stage
            or fragment.get("bucket_index") != index
            or "records" in fragment
        ):
            raise DatabaseError("A Query-202 sorted-run fragment has invalid identity metadata.")
        token = _snapshot_token(fragment.get("snapshot_token"), spec.stage)
        if snapshot is None:
            snapshot = token
        elif snapshot != token:
            raise DatabaseError("Query-202 crosswalk buckets did not share one snapshot.")
        controls = fragment.get("controls")
        if not isinstance(controls, Mapping) or set(controls) != set(CONTROL_NAMES[spec.stage]):
            raise DatabaseError("A Query-202 sorted-run fragment has incomplete controls.")
        input_sum = add(input_sum, controls["bucket_input_rows"], "bucket input sum")
        output_sum = add(
            output_sum,
            controls["bucket_output_multiplicity"],
            "bucket output sum",
        )
        for kind in spec.tuple_kinds:
            per_kind_input_sums[kind] = add(
                per_kind_input_sums[kind],
                controls[f"{kind}_input_rows"],
                "tuple-kind input sum",
            )
            per_kind_output_sums[kind] = add(
                per_kind_output_sums[kind],
                controls[f"{kind}_tuple_multiplicity"],
                "tuple-kind output sum",
            )
    if input_sum != expected_global_input_rows:
        raise DatabaseError("Query-202 buckets failed mutual-exclusion/completeness conservation.")

    unique = 0
    merged_multiplicity = 0
    kind_unique = {kind: 0 for kind in spec.tuple_kinds}
    kind_multiplicity = {kind: 0 for kind in spec.tuple_kinds}
    for record in _iter_merged_sorted_runs(spec, spool):
        unique = add(unique, 1, "merged tuple count")
        merged_multiplicity = add(
            merged_multiplicity, record["multiplicity"], "merged tuple multiplicity"
        )
        kind = record["tuple_kind"]
        kind_unique[kind] = add(kind_unique[kind], 1, "merged tuple-kind count")
        kind_multiplicity[kind] = add(
            kind_multiplicity[kind],
            record["multiplicity"],
            "merged tuple-kind multiplicity",
        )
    if merged_multiplicity != output_sum:
        raise DatabaseError("Query-202 external merge failed multiplicity conservation.")
    by_kind: dict[str, dict[str, Any]] = {}
    for kind in spec.tuple_kinds:
        if (
            kind_multiplicity[kind] != per_kind_output_sums[kind]
            or per_kind_input_sums[kind] != per_kind_output_sums[kind]
        ):
            raise DatabaseError("A Query-202 tuple kind failed global input-row conservation.")
        by_kind[kind] = {
            "unique_tuples": kind_unique[kind],
            "total_multiplicity": kind_multiplicity[kind],
            "summed_bucket_input_rows": per_kind_input_sums[kind],
            "summed_bucket_tuple_multiplicity": per_kind_output_sums[kind],
        }
    return {
        "stage": spec.stage,
        "bucket_count": BUCKET_COUNT,
        "bucket_indices_complete": True,
        "assignment_unit": "subject_id",
        "sql_null_subject_bucket": 0,
        "bucket_assignment_violations": 0,
        "null_subject_outside_bucket_zero": 0,
        "global_input_rows": expected_global_input_rows,
        "global_input_rows_source": "same_snapshot_202a_boundary_source_rows",
        "summed_bucket_input_rows": input_sum,
        "global_output_multiplicity": output_sum,
        "mutual_exclusion_and_completeness_confirmed": True,
        "snapshot_token": snapshot,
        "unique_tuples": unique,
        "tuple_kind_summaries": by_kind,
    }


def _new_tuple_hashers(stage: str, record_count: int) -> tuple[Any, Any]:
    stage_bytes = stage.encode("utf-8")
    set_digest = hashlib.sha256()
    frequency_digest = hashlib.sha256()
    for digest, version in (
        (set_digest, TUPLE_SET_HASH_VERSION),
        (frequency_digest, TUPLE_FREQUENCY_HASH_VERSION),
    ):
        digest.update(version)
        digest.update(struct.pack(">I", len(stage_bytes)))
        digest.update(stage_bytes)
        digest.update(struct.pack(">Q", record_count))
    return set_digest, frequency_digest


def _update_tuple_hashers(
    hashers: tuple[Any, Any], encoded: bytes, multiplicity: int
) -> None:
    set_digest, frequency_digest = hashers
    set_digest.update(struct.pack(">Q", len(encoded)))
    set_digest.update(encoded)
    frequency_digest.update(struct.pack(">Q", len(encoded)))
    frequency_digest.update(encoded)
    frequency_digest.update(struct.pack(">Q", multiplicity))


def crosswalk_global_denominators_from_boundaries(
    boundaries: Mapping[str, Mapping[str, Any]],
) -> dict[str, int]:
    """Derive the two global base-row controls from the same-snapshot 202a scans.

    Several boundary fields scan the same base relation.  Their row totals must
    agree before one representative total is reused, eliminating 64 repeated
    full-table counts from each bucketed SQL stage.
    """
    if set(boundaries) != set(BOUNDARY_BY_KEY):
        raise DatabaseError("Query-202 boundary denominators are incomplete.")

    relation_sources = {
        "emar": ("emar_medication",),
        "emar_detail": (
            "detail_product_description",
            "detail_product_description_other",
            "emar_detail_route",
        ),
        "pharmacy": ("pharmacy_medication", "pharmacy_route"),
        "prescriptions": (
            "prescription_drug", "prescriptions_route", "prescriptions_ndc",
        ),
    }
    relation_rows: dict[str, int] = {}
    for relation, keys in relation_sources.items():
        counts = []
        for key in keys:
            value = boundaries[key].get("source_rows")
            if type(value) is not int or not 0 <= value <= MAX_EXACT_COUNT:
                raise DatabaseError("A Query-202 boundary source denominator is malformed.")
            counts.append(value)
        if len(set(counts)) != 1:
            raise DatabaseError("Same-relation Query-202 boundary denominators disagree.")
        relation_rows[relation] = counts[0]

    order_total = sum(relation_rows.values())
    if order_total > MAX_MERGED_COUNT:
        raise DatabaseError("The Query-202 order-stage denominator exceeded its limit.")
    return {
        "202b": relation_rows["emar_detail"],
        "202c": order_total,
    }


def crosswalk_physical_input_denominators_from_boundaries(
    boundaries: Mapping[str, Mapping[str, Any]],
) -> dict[str, int]:
    """Return the separately conserved base-row total for every input owner."""
    # This validates the complete boundary inventory and same-relation row
    # agreement before representative source counts are reused.
    crosswalk_global_denominators_from_boundaries(boundaries)
    return {
        physical.stage: boundaries[
            BUCKET_INPUT_SOURCE_BOUNDARY_KEY[physical.bucket_input_source]
        ]["source_rows"]
        for physical in CROSSWALK_STATEMENTS
        if physical.bucket_input_source is not None
    }


def _assert_one_snapshot(
    boundaries: Mapping[str, Mapping[str, Any]],
    crosswalks: Mapping[str, Mapping[str, Any]],
) -> str:
    if set(boundaries) != set(BOUNDARY_BY_KEY) or set(crosswalks) != set(CROSSWALK_BY_STAGE):
        raise DatabaseError("Query-202 did not return all preregistered stages.")
    snapshots = {
        _snapshot_token(item.get("snapshot_token"), label)
        for label, item in list(boundaries.items()) + list(crosswalks.items())
    }
    if len(snapshots) != 1:
        raise DatabaseError("Query-202 stages did not share one database snapshot.")
    return next(iter(snapshots))


def _validate_boundary_expectations(
    boundaries: Mapping[str, Mapping[str, Any]], report: Mapping[str, Any]
) -> None:
    expected = report.get("boundary_expectations")
    if not isinstance(expected, Mapping) or set(expected) != set(BOUNDARY_BY_KEY):
        raise DatabaseError("The Query-202 boundary expectation report is incomplete.")
    for key, spec in BOUNDARY_BY_KEY.items():
        observed = boundaries[key]
        item = expected[key]
        if not isinstance(item, Mapping) or any((
            item.get("source_field") != spec.source_field,
            item.get("expected_nonnull_set_sha256") != observed.get("nonnull_set_sha256"),
            item.get("expected_nonnull_distinct_values") != observed.get("nonnull_distinct_values"),
        )):
            raise DatabaseError("A Query-202 typed boundary did not match frozen lineage.")
        expected_typed_hash = item.get("expected_typed_set_sha256")
        expected_typed_count = item.get("expected_typed_distinct_values")
        if (expected_typed_hash is None) is not (expected_typed_count is None):
            raise DatabaseError("A Query-202 typed-boundary expectation is incomplete.")
        if expected_typed_hash is not None and (
            expected_typed_hash != observed.get("typed_set_sha256")
            or expected_typed_count != observed.get("typed_distinct_values")
        ):
            raise DatabaseError("A Query-202 preflight typed boundary did not match lineage.")


def _load_preregistration_report(root: Path) -> dict[str, Any]:
    from .query202_pre_adjudication_preregistration_v2 import (
        potassium_query202_pre_adjudication_v2_preregistration_report,
    )

    return potassium_query202_pre_adjudication_v2_preregistration_report(root)


def _validate_preregistration_gate(report: Any) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise DatabaseError("The Query-202 v2 preregistration report is malformed.")
    if (
        report.get("valid") is not True
        or report.get("component_id") != COMPONENT_ID
        or report.get("status") != "frozen_for_execution"
        or report.get("execution_status") != "not_executed"
        or report.get("execution_permitted") is not True
        or report.get("implementation_state") != "frozen_for_execution"
        or report.get("implementation_hashes_verified") is not True
        or report.get("freeze_ready") is not True
        or report.get("fixture_attestation_verified") is not True
        or report.get("bucket_count") != BUCKET_COUNT
    ):
        raise DatabaseError("The Query-202 v2 preregistration execution gate is closed.")
    if report.get("formal_product_mapping_enabled") is not False or report.get("formal_source_policy_enabled") is not False:
        raise DatabaseError("Formal D005 mapping/source-policy guards must remain false.")
    guards = report.get("guards")
    if not isinstance(guards, Mapping) or set(guards) != set(FALSE_GUARDS) or any(
        guards[key] is not False for key in FALSE_GUARDS
    ):
        raise DatabaseError("All Query-202 v2 clinical and downstream guards must remain false.")
    if report.get("semantic_seed_expected_keys") != 34_565:
        raise DatabaseError("The Query-202 v2 semantic-seed denominator is not frozen.")
    if SHA256_PATTERN.fullmatch(str(report.get("semantic_seed_expected_sha256"))) is None:
        raise DatabaseError("The Query-202 v2 semantic-seed set hash is not frozen.")
    for key in ("config", "config_sha256"):
        if not isinstance(report.get(key), str) or not report[key]:
            raise DatabaseError("The Query-202 v2 preregistration lineage is incomplete.")
    if report["config"] != CONFIG_PATH or SHA256_PATTERN.fullmatch(report["config_sha256"]) is None:
        raise DatabaseError("The Query-202 v2 preregistration path or hash is invalid.")
    if type(report.get("evidence_files_checked")) is not int:
        raise DatabaseError("The Query-202 v2 evidence count is invalid.")
    bundles = report.get("implementation_bundles")
    if not isinstance(bundles, Mapping) or set(bundles) != set(IMPLEMENTATION_BUNDLE_PATHS):
        raise DatabaseError("The Query-202 v2 implementation bundle report is incomplete.")
    expectations = report.get("boundary_expectations")
    if not isinstance(expectations, Mapping) or set(expectations) != set(BOUNDARY_BY_KEY):
        raise DatabaseError("The Query-202 v2 boundary expectation report is incomplete.")
    return report


def _public_boundary_summary(source: Mapping[str, Any]) -> dict[str, Any]:
    null_distinct = int(source["sql_null_rows"] > 0)
    return {
        "source_field": source["source_field"],
        "source_rows": source["source_rows"],
        "typed_distinct_values": source["typed_distinct_values"],
        "nonnull_distinct_values": source["nonnull_distinct_values"],
        "sql_null_distinct_values": null_distinct,
        "sql_null_rows": source["sql_null_rows"],
        "nonnull_set_sha256": source["nonnull_set_sha256"],
        "typed_set_sha256": source["typed_set_sha256"],
        "lineage_match_confirmed": True,
    }


def _private_stream_header(
    preregistered: Mapping[str, Any], snapshot_token: str
) -> dict[str, Any]:
    return {
        "record_type": "header",
        "artifact_encoding": PRIVATE_ARTIFACT_ENCODING,
        "schema_version": 2,
        "query": QUERY_NAME,
        "created_at_utc": _now(),
        "component_lineage": {
            "component_id": preregistered["component_id"],
            "status_at_execution": preregistered["status"],
            "config": preregistered["config"],
            "config_sha256": preregistered["config_sha256"],
        },
        "transaction": {
            "isolation": "repeatable read",
            "read_only": True,
            "same_snapshot": True,
            "snapshot_token_sha256": _sha(snapshot_token.encode("utf-8")),
            "rollback_confirmed_before_persistence": True,
            "clean_psql_exit_confirmed_before_persistence": True,
        },
        "hash_contracts": {
            "typed_boundary_set": BOUNDARY_SET_HASH_VERSION.decode("ascii"),
            "semantic_seed_set": SEMANTIC_SEED_HASH_VERSION.decode("ascii"),
            "typed_tuple_encoding": TUPLE_ENCODING_VERSION.decode("ascii"),
            "global_tuple_set": TUPLE_SET_HASH_VERSION.decode("ascii"),
            "global_tuple_frequency": TUPLE_FREQUENCY_HASH_VERSION.decode("ascii"),
            "global_hashes_recomputed_from_merged_exact_tuples": True,
            "partition_hash_concatenation_allowed": False,
        },
        "privacy": {
            "contains_exact_raw_local_values": True,
            "contains_patient_admission_event_or_order_identifiers": False,
            "contains_event_or_order_timestamps": False,
            "external_api_called": False,
        },
        "guards": {key: False for key in FALSE_GUARDS},
    }


def _private_stream_view(
    header: Mapping[str, Any],
    boundaries: Mapping[str, Mapping[str, Any]],
    crosswalks: Mapping[str, Mapping[str, Any]],
    seed_count: int,
    seed_hash: str,
) -> dict[str, Any]:
    private_boundaries: dict[str, dict[str, Any]] = {}
    for spec in BOUNDARY_STAGES:
        source = boundaries[spec.source_key]
        private_boundaries[spec.source_key] = {
            "stage": spec.stage,
            "source_field": spec.source_field,
            "semantic_seed_field": spec.semantic_seed,
            "sql_null_rows": source["sql_null_rows"],
            "typed_distinct_values": source["typed_distinct_values"],
            "nonnull_distinct_values": source["nonnull_distinct_values"],
            "source_rows": source["source_rows"],
            "nonnull_set_sha256": source["nonnull_set_sha256"],
            "typed_set_sha256": source["typed_set_sha256"],
        }
    private_crosswalks: dict[str, dict[str, Any]] = {}
    for spec in CROSSWALK_STAGES:
        source = crosswalks[spec.stage]
        private_crosswalks[spec.stage] = {
            key: source[key]
            for key in (
                "bucket_count",
                "bucket_indices_complete",
                "assignment_unit",
                "sql_null_subject_bucket",
                "bucket_assignment_violations",
                "null_subject_outside_bucket_zero",
                "global_input_rows",
                "global_input_rows_source",
                "summed_bucket_input_rows",
                "global_output_multiplicity",
                "mutual_exclusion_and_completeness_confirmed",
                "unique_tuples",
                "global_tuple_set_sha256",
                "global_tuple_frequency_sha256",
                "tuple_kind_summaries",
            )
        }
    return {
        "schema_version": header["schema_version"],
        "query": header["query"],
        "created_at_utc": header["created_at_utc"],
        "component_lineage": dict(header["component_lineage"]),
        "transaction": dict(header["transaction"]),
        "hash_contracts": dict(header["hash_contracts"]),
        "boundaries": private_boundaries,
        "semantic_seed": {
            "key_count": seed_count,
            "key_set_sha256": seed_hash,
            "sql_null_keys_included": False,
            "review_decisions_included": False,
        },
        "crosswalks": private_crosswalks,
        "privacy": dict(header["privacy"]),
        "guards": dict(header["guards"]),
    }


def _write_private_ndjson(
    path: Path,
    boundaries: Mapping[str, Mapping[str, Any]],
    crosswalks: dict[str, dict[str, Any]],
    run_spool: _AnonymousSortedRunSpool,
    preregistered: Mapping[str, Any],
    snapshot_token: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Write exact evidence without constructing a global Python payload."""
    seed_count, seed_hash = semantic_seed_set_sha256(boundaries)
    if (
        seed_count != preregistered["semantic_seed_expected_keys"]
        or seed_hash != preregistered["semantic_seed_expected_sha256"]
    ):
        raise DatabaseError("The Query-202 semantic seed did not contain exactly 34,565 keys.")
    header = _private_stream_header(preregistered, snapshot_token)
    writer = _GzipNdjsonWriter(path)
    section_counts = {
        "boundary_values": 0,
        "semantic_seed_values": 0,
        "crosswalk_tuples": 0,
    }
    try:
        writer.write_record(header)
        for spec in BOUNDARY_STAGES:
            source = boundaries[spec.source_key]
            metadata = {
                "stage": spec.stage,
                "source_field": spec.source_field,
                "semantic_seed_field": spec.semantic_seed,
                "sql_null_rows": source["sql_null_rows"],
                "typed_distinct_values": source["typed_distinct_values"],
                "nonnull_distinct_values": source["nonnull_distinct_values"],
                "source_rows": source["source_rows"],
                "nonnull_set_sha256": source["nonnull_set_sha256"],
                "typed_set_sha256": source["typed_set_sha256"],
            }
            writer.write_record({
                "metadata": metadata,
                "record_type": "boundary_begin",
                "source_key": spec.source_key,
            })
            observed = 0
            for record in source["records"]:
                writer.write_record({
                    "record_type": "boundary_value",
                    "source_key": spec.source_key,
                    "value": dict(record),
                })
                observed += 1
                section_counts["boundary_values"] += 1
            if observed != source["typed_distinct_values"]:
                raise DatabaseError("A Query-202 streamed boundary count changed.")
            writer.write_record({
                "record_type": "boundary_end",
                "records": observed,
                "source_key": spec.source_key,
            })

        writer.write_record({
            "key_count": seed_count,
            "key_set_sha256": seed_hash,
            "record_type": "semantic_seed_begin",
            "review_decisions_included": False,
            "sql_null_keys_included": False,
        })
        for source_field, raw in _semantic_seed_records(boundaries):
            writer.write_record({
                "exact_raw_value": raw,
                "record_type": "semantic_seed_value",
                "source_field": source_field,
            })
            section_counts["semantic_seed_values"] += 1
        if section_counts["semantic_seed_values"] != seed_count:
            raise DatabaseError("The Query-202 streamed semantic-seed count changed.")
        writer.write_record({
            "record_type": "semantic_seed_end",
            "records": seed_count,
        })

        for spec in CROSSWALK_STAGES:
            source = crosswalks[spec.stage]
            begin_metadata = {
                key: source[key]
                for key in (
                    "bucket_count",
                    "bucket_indices_complete",
                    "assignment_unit",
                    "sql_null_subject_bucket",
                    "bucket_assignment_violations",
                    "null_subject_outside_bucket_zero",
                    "global_input_rows",
                    "global_input_rows_source",
                    "summed_bucket_input_rows",
                    "global_output_multiplicity",
                    "mutual_exclusion_and_completeness_confirmed",
                    "unique_tuples",
                )
            }
            begin_metadata["tuple_kind_summaries"] = {
                kind: dict(summary)
                for kind, summary in source["tuple_kind_summaries"].items()
            }
            writer.write_record({
                "metadata": begin_metadata,
                "record_type": "crosswalk_begin",
                "stage": spec.stage,
            })
            global_hashers = _new_tuple_hashers(
                spec.stage, source["unique_tuples"]
            )
            kind_hashers = {
                kind: _new_tuple_hashers(
                    spec.stage + ":" + kind,
                    source["tuple_kind_summaries"][kind]["unique_tuples"],
                )
                for kind in spec.tuple_kinds
            }
            observed_unique = 0
            observed_total = 0
            observed_kind_unique = {kind: 0 for kind in spec.tuple_kinds}
            observed_kind_total = {kind: 0 for kind in spec.tuple_kinds}
            for record in _iter_merged_sorted_runs(spec, run_spool):
                kind = record["tuple_kind"]
                multiplicity = record["multiplicity"]
                encoded = record["encoded_tuple"]
                _update_tuple_hashers(global_hashers, encoded, multiplicity)
                _update_tuple_hashers(kind_hashers[kind], encoded, multiplicity)
                observed_unique += 1
                observed_total += multiplicity
                observed_kind_unique[kind] += 1
                observed_kind_total[kind] += multiplicity
                writer.write_record({
                    "multiplicity": multiplicity,
                    "record_type": "crosswalk_tuple",
                    "stage": spec.stage,
                    "tuple": record["tuple"],
                    "tuple_kind": kind,
                })
                section_counts["crosswalk_tuples"] += 1
            if (
                observed_unique != source["unique_tuples"]
                or observed_total != source["global_output_multiplicity"]
            ):
                raise DatabaseError("A Query-202 streamed crosswalk total changed.")
            source["global_tuple_set_sha256"] = global_hashers[0].hexdigest()
            source["global_tuple_frequency_sha256"] = global_hashers[1].hexdigest()
            kind_hashes: dict[str, dict[str, str]] = {}
            for kind in spec.tuple_kinds:
                summary = source["tuple_kind_summaries"][kind]
                if (
                    observed_kind_unique[kind] != summary["unique_tuples"]
                    or observed_kind_total[kind] != summary["total_multiplicity"]
                ):
                    raise DatabaseError("A Query-202 streamed tuple-kind total changed.")
                summary["global_tuple_set_sha256"] = kind_hashers[kind][0].hexdigest()
                summary["global_tuple_frequency_sha256"] = kind_hashers[kind][1].hexdigest()
                kind_hashes[kind] = {
                    "global_tuple_set_sha256": summary["global_tuple_set_sha256"],
                    "global_tuple_frequency_sha256": summary[
                        "global_tuple_frequency_sha256"
                    ],
                }
            writer.write_record({
                "global_tuple_frequency_sha256": source[
                    "global_tuple_frequency_sha256"
                ],
                "global_tuple_set_sha256": source["global_tuple_set_sha256"],
                "record_type": "crosswalk_end",
                "records": observed_unique,
                "stage": spec.stage,
                "tuple_kind_hashes": kind_hashes,
            })

        writer.write_record({
            "record_type": "footer",
            "records_before_footer": writer.records,
            "section_records": section_counts,
        })
        artifact = writer.finish()
    except BaseException:
        writer.abort()
        raise
    private = _private_stream_view(
        header, boundaries, crosswalks, seed_count, seed_hash
    )
    return artifact, private


def build_aggregate_summary(private: Mapping[str, Any]) -> dict[str, Any]:
    boundaries = private["boundaries"]
    crosswalks = private["crosswalks"]
    return {
        "schema_version": 2,
        "query": QUERY_NAME,
        "created_at_utc": _now(),
        "scope": "complete_local_pre_adjudication_boundary_and_crosswalk_evidence",
        "component_lineage": dict(private["component_lineage"]),
        "boundary_summaries": {
            key: _public_boundary_summary(value) for key, value in boundaries.items()
        },
        "semantic_seed_summary": {
            key: private["semantic_seed"][key]
            for key in (
                "key_count",
                "key_set_sha256",
                "sql_null_keys_included",
                "review_decisions_included",
            )
        },
        "crosswalk_summaries": {
            stage: {key: value[key] for key in (
                "bucket_count",
                "bucket_indices_complete",
                "assignment_unit",
                "sql_null_subject_bucket",
                "bucket_assignment_violations",
                "null_subject_outside_bucket_zero",
                "global_input_rows",
                "global_input_rows_source",
                "summed_bucket_input_rows",
                "global_output_multiplicity",
                "mutual_exclusion_and_completeness_confirmed",
                "unique_tuples",
                "global_tuple_set_sha256",
                "global_tuple_frequency_sha256",
                "tuple_kind_summaries",
            )}
            for stage, value in crosswalks.items()
        },
        "transaction_controls": dict(private["transaction"]),
        "privacy": {
            "raw_values_emitted": False,
            "local_codes_or_ndcs_emitted": False,
            "patient_admission_event_or_order_identifiers_emitted": False,
            "event_or_order_timestamps_emitted": False,
            "per_value_or_per_tuple_hashes_emitted": False,
            "whole_set_and_whole_file_hashes_only": True,
        },
        "guards": {key: False for key in FALSE_GUARDS},
    }


def _assert_value_free_public_payload(
    payload: Mapping[str, Any], forbidden_values: Iterable[str]
) -> None:
    forbidden_keys = {
        "raw_value",
        "raw_value_base64",
        "exact_raw_value",
        "tuple",
        "tuple_json_base64",
        "records",
        "snapshot_token",
        "subject_id",
        "hadm_id",
        "emar_id",
        "pharmacy_id",
        "poe_id",
        "ndc",
    }

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            if forbidden_keys & set(value):
                raise DatabaseError("Query-202 public metadata has a private key.")
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    for raw in forbidden_values:
        if len(raw) >= 12 and raw in encoded:
            raise DatabaseError("Query-202 public metadata disclosed a private value.")


def _session_preamble() -> str:
    return (
        "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
        "SET LOCAL lock_timeout = '2000ms';\n"
        "SET LOCAL standard_conforming_strings = on;\n"
        "SET LOCAL client_encoding = 'UTF8';\n"
        "SET LOCAL DateStyle = 'ISO, YMD';\n"
        "SET LOCAL TimeZone = 'UTC';\n"
        "SET LOCAL IntervalStyle = 'postgres';\n"
        "SET LOCAL extra_float_digits = 3;\n"
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


def _render_bucket_statement(template: str, bucket_index: int) -> str:
    try:
        return _statement_body(render_bucket_sql(template, bucket_index))
    except (ValueError, TypeError) as exc:
        raise DatabaseError("A Query-202 bucket template failed its frozen renderer.") from exc


def _initial_stage(label: str, file: str, bucket_index: int | None = None) -> dict[str, Any]:
    return {
        "stage": label,
        "file": file,
        "bucket_index": bucket_index,
        "status": "pending",
        "rows": None,
        "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        "process_timeout_seconds": PROCESS_TIMEOUT_SECONDS,
    }


def run_query202_pre_adjudication(root: Path) -> dict[str, Any]:
    """Execute lifecycle A v2 and return terminal-safe metadata only."""
    preregistered = _validate_preregistration_gate(_load_preregistration_report(root))
    observed_bundles = implementation_bundles(root)
    for name, observed in observed_bundles.items():
        registered = preregistered["implementation_bundles"].get(name)
        if (
            not isinstance(registered, Mapping)
            or registered.get("paths") != observed["paths"]
            or registered.get("expected_sha256") != observed["bundle_sha256"]
            or registered.get("actual_sha256") != observed["bundle_sha256"]
        ):
            raise DatabaseError("A Query-202 v2 implementation bundle changed after freeze.")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = root / "artifacts" / "profiling" / stamp
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    try:
        destination.chmod(0o700)
        directory_mode = _mode(destination)
    except OSError as exc:
        try:
            destination.rmdir()
        except OSError:
            pass
        raise DatabaseError("The Query-202 artifact directory mode could not be verified.") from exc
    if directory_mode != "0700":
        try:
            destination.rmdir()
        except OSError:
            pass
        raise DatabaseError("The Query-202 artifact directory has an unsafe mode.")
    manifest_path = destination / "manifest.json"
    started = time.monotonic()
    stages: dict[str, dict[str, Any]] = {}
    for spec in BOUNDARY_STAGES:
        stages[spec.stage] = _initial_stage(spec.stage, spec.sql_file)
    for spec in CROSSWALK_STATEMENTS:
        for index in range(BUCKET_COUNT):
            label = f"{spec.stage}_bucket_{index}"
            stages[label] = _initial_stage(spec.stage, spec.sql_path, index)

    report: dict[str, Any] = {
        "schema_version": 2,
        "started_at_utc": _now(),
        "status": "running",
        "scope": "complete_local_pre_adjudication_boundary_and_crosswalk_evidence",
        "selected_queries": [QUERY_NAME],
        "requested_controls": {
            "read_only": True,
            "same_snapshot": True,
            "transaction_isolation": "repeatable read",
            "statement_timeout_ms_per_sql": STATEMENT_TIMEOUT_MS,
            "sql_statement_count": (
                len(BOUNDARY_STAGES) + len(CROSSWALK_STATEMENTS) * BUCKET_COUNT
            ),
            "boundary_statement_count": len(BOUNDARY_STAGES),
            "bucket_count_per_crosswalk_stage": BUCKET_COUNT,
            "explicit_rollback": True,
            "clean_psql_exit_before_value_persistence": True,
            "anonymous_frame_spool_before_rollback": True,
            "anonymous_sorted_run_spool_after_rollback": True,
            "database_stderr_persisted": False,
            "session_format_settings": {
                "client_encoding": "UTF8",
                "DateStyle": "ISO, YMD",
                "TimeZone": "UTC",
                "IntervalStyle": "postgres",
                "extra_float_digits": "3",
            },
            "database_writes_or_session_objects": False,
            "external_api_calls": False,
            "limits": {
                "boundary_frame_bytes": MAX_BOUNDARY_FRAME_BYTES,
                "crosswalk_frame_bytes": MAX_STAGE_FRAME_BYTES,
                "raw_frame_bytes": MAX_CUMULATIVE_RAW_FRAME_BYTES,
                "total_anonymous_spool_bytes": MAX_CUMULATIVE_SPOOL_BYTES,
                "merge_run_raw_bytes": MAX_ANONYMOUS_RUN_RAW_BYTES,
                "merge_run_spool_bytes": MAX_ANONYMOUS_RUN_SPOOL_BYTES,
                "private_artifact_raw_bytes": MAX_PRIVATE_ARTIFACT_RAW_BYTES,
                "private_artifact_stored_bytes": MAX_PRIVATE_ARTIFACT_STORED_BYTES,
                "private_artifact_line_bytes": MAX_PRIVATE_ARTIFACT_LINE_BYTES,
                "tuple_json_utf8_bytes": MAX_VALUE_UTF8_BYTES,
                "executed_sql_bytes": MAX_EXECUTED_SQL_BYTES,
                "boundary_groups_per_field": MAX_BOUNDARY_GROUPS,
                "tuple_groups_per_bucket": MAX_TUPLE_GROUPS_PER_BUCKET,
                "exact_count_or_multiplicity": MAX_EXACT_COUNT,
            },
        },
        "confirmed_controls": {
            "read_only": False,
            "same_snapshot": False,
            "transaction_isolation": None,
            "rollback": False,
            "clean_psql_exit": False,
            "anonymous_frame_spool": False,
            "anonymous_sorted_run_spool": False,
            "database_stderr_discarded": False,
            "session_format_settings_applied": False,
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
            "execution_permitted_at_start": True,
            "config": preregistered["config"],
            "config_sha256": preregistered["config_sha256"],
            "evidence_files_checked": preregistered["evidence_files_checked"],
            "implementation_hashes_verified": True,
            "guards": {key: False for key in FALSE_GUARDS},
        },
        "implementation_bundles": observed_bundles,
        "queries": [{
            "query": QUERY_NAME,
            "status": "running",
            "stage_order": list(stages),
            "stages": stages,
            "private_values_persisted": False,
            "executed_sql_persisted": False,
            "aggregate_summary_persisted": False,
            "psql_returncode": None,
        }],
        "guards": {key: False for key in FALSE_GUARDS},
        "limitations": (
            "Local pre-adjudication evidence only. No route or product mapping, "
            "external NDC lookup, source-policy acceptance, action, episode, "
            "zero action, label, non-ICU cohort, or LLM call is created."
        ),
    }
    entry = report["queries"][0]
    session: _PersistentPsql | None = None
    spool: _AnonymousFrameSpool | None = None
    run_spool: _AnonymousSortedRunSpool | None = None
    rollback_marker: str | None = None
    executed_controls: list[str] = []
    value_paths: list[Path] = []
    boundary_payloads: dict[str, dict[str, Any]] = {}
    crosswalk_controls: dict[str, dict[int, dict[str, Any]]] = {
        spec.stage: {} for spec in CROSSWALK_STATEMENTS
    }
    manifest_written = False
    cumulative_control_bytes = 0
    cumulative_frame_bytes = 0
    cumulative_spool_bytes = 0
    cumulative_merge_run_raw_bytes = 0
    cumulative_merge_run_spool_bytes = 0
    merge_run_ledger: dict[str, dict[str, int]] = {}
    try:
        statements: dict[str, str] = {}
        frozen_sql = {
            item["path"]: item["file_sha256"] for item in observed_bundles["sql"]["files"]
        }
        for spec in BOUNDARY_STAGES:
            raw = (root / spec.sql_file).read_bytes()
            if frozen_sql.get(spec.sql_file) != _sha(raw):
                raise DatabaseError("A Query-202 boundary SQL file changed after freeze.")
            statements[spec.stage] = _statement_body(raw.decode("utf-8"))
            stages[spec.stage].update(template_sha256=_sha(raw), template_bytes=len(raw))
        bucket_templates: dict[str, str] = {}
        for spec in CROSSWALK_STATEMENTS:
            raw = (root / spec.sql_path).read_bytes()
            if frozen_sql.get(spec.sql_path) != _sha(raw):
                raise DatabaseError("A Query-202 bucket SQL file changed after freeze.")
            template = raw.decode("utf-8")
            bucket_templates[spec.stage] = template
            for index in range(BUCKET_COUNT):
                stages[f"{spec.stage}_bucket_{index}"].update(
                    template_sha256=_sha(raw), template_bytes=len(raw)
                )

        # Check the destination filesystem before opening a database client or
        # starting any SQL.  Failure to determine free space is itself fatal.
        _require_database_disk_headroom(destination)
        spool = _AnonymousFrameSpool(destination)
        report["confirmed_controls"]["anonymous_frame_spool"] = True
        client = PsqlClient(root, STATEMENT_TIMEOUT_MS)
        session = _PersistentPsql(client, None)
        report["confirmed_controls"]["database_stderr_discarded"] = True
        rollback_marker = "__APRIL_QUERY202A_V2_ROLLBACK_" + secrets.token_hex(24) + "__"
        ordinal = 0
        for spec in BOUNDARY_STAGES:
            label = spec.stage
            marker = "__APRIL_QUERY202A_V2_" + label.upper() + "_" + secrets.token_hex(24) + "__"
            control = _stage_control(statements[label], marker, first=ordinal == 0)
            ordinal += 1
            encoded = control.encode("utf-8")
            if cumulative_control_bytes > MAX_EXECUTED_SQL_BYTES - len(encoded):
                raise DatabaseError("Query-202 executed SQL exceeded its byte limit.")
            cumulative_control_bytes += len(encoded)
            stages[label].update(control_sha256=_sha(encoded), control_bytes=len(encoded), status="running")
            began = time.monotonic()
            try:
                session.send(control)
                frame = session.frame(marker, PROCESS_TIMEOUT_SECONDS, MAX_BOUNDARY_FRAME_BYTES)
            finally:
                stages[label]["elapsed_seconds"] = round(time.monotonic() - began, 6)
            payload = _decode_boundary_frame(frame, spec)
            boundary_payloads[spec.source_key] = payload
            stored_bytes = spool.append(label, frame)
            cumulative_frame_bytes = spool.total_raw_bytes
            cumulative_spool_bytes = spool.total_stored_bytes
            stages[label].update(
                status="validated_in_anonymous_spool",
                rows=payload["typed_distinct_values"],
                frame_bytes=len(frame),
                spool_bytes=stored_bytes,
                source_rows=payload["source_rows"],
                typed_set_sha256=payload["typed_set_sha256"],
            )
            executed_controls.append(control)
            del frame

        for spec in CROSSWALK_STATEMENTS:
            for index in range(BUCKET_COUNT):
                label = f"{spec.stage}_bucket_{index}"
                statement = _render_bucket_statement(bucket_templates[spec.stage], index)
                marker = "__APRIL_QUERY202A_V2_" + spec.stage.upper() + "_" + str(index) + "_" + secrets.token_hex(24) + "__"
                control = _stage_control(statement, marker, first=False)
                encoded = control.encode("utf-8")
                if cumulative_control_bytes > MAX_EXECUTED_SQL_BYTES - len(encoded):
                    raise DatabaseError("Query-202 executed SQL exceeded its byte limit.")
                cumulative_control_bytes += len(encoded)
                stages[label].update(
                    control_sha256=_sha(encoded),
                    control_bytes=len(encoded),
                    rendered_statement_sha256=_sha(statement.encode("utf-8")),
                    status="running",
                )
                began = time.monotonic()
                try:
                    session.send(control)
                    frame = session.frame(marker, PROCESS_TIMEOUT_SECONDS, MAX_STAGE_FRAME_BYTES)
                finally:
                    stages[label]["elapsed_seconds"] = round(time.monotonic() - began, 6)
                payload = _decode_crosswalk_frame(frame, spec, index)
                # Retain controls only; exact tuple rows remain solely in the
                # anonymous spool until rollback and clean process exit.
                crosswalk_controls[spec.stage][index] = {
                    key: value for key, value in payload.items() if key != "records"
                }
                stored_bytes = spool.append(label, frame)
                cumulative_frame_bytes = spool.total_raw_bytes
                cumulative_spool_bytes = spool.total_stored_bytes
                stages[label].update(
                    status="validated_in_anonymous_spool",
                    rows=len(payload["records"]),
                    frame_bytes=len(frame),
                    spool_bytes=stored_bytes,
                    tuple_multiplicity=sum(item["multiplicity"] for item in payload["records"]),
                )
                if spec.bucket_input_source is not None:
                    stages[label].update(
                        bucket_input_rows=payload["controls"]["bucket_input_rows"],
                        bucket_assignment_violations=0,
                        null_subject_outside_bucket_zero=0,
                    )
                executed_controls.append(control)
                del payload, frame

        all_snapshot_tokens = {
            payload["snapshot_token"] for payload in boundary_payloads.values()
        } | {
            payload["snapshot_token"]
            for stage in crosswalk_controls.values()
            for payload in stage.values()
        }
        if len(all_snapshot_tokens) != 1:
            raise DatabaseError("Query-202 SQL statements did not share one snapshot.")
        snapshot_token = next(iter(all_snapshot_tokens))
        snapshot_sha256 = _sha(snapshot_token.encode("utf-8"))
        for stage in stages.values():
            stage.update(
                observed_transaction_isolation="repeatable read",
                observed_transaction_read_only="on",
                observed_snapshot_sha256=snapshot_sha256,
            )

        rollback_control = "ROLLBACK;\n\\echo " + rollback_marker + "\n"
        quit_control = "\\q\n"
        remaining = len(rollback_control.encode("utf-8")) + len(quit_control.encode("utf-8"))
        if cumulative_control_bytes > MAX_EXECUTED_SQL_BYTES - remaining:
            raise DatabaseError("Query-202 executed SQL exceeded its byte limit.")
        session.confirm_rollback(rollback_marker)
        executed_controls.append(rollback_control)
        cumulative_control_bytes += len(rollback_control.encode("utf-8"))
        report["confirmed_controls"]["rollback"] = True
        returncode = session.close()
        session = None
        cumulative_control_bytes += len(quit_control.encode("utf-8"))
        entry["psql_returncode"] = returncode
        if returncode != 0:
            raise DatabaseError("Query-202 psql did not exit cleanly after rollback.")
        report["confirmed_controls"].update({
            "read_only": True,
            "same_snapshot": True,
            "transaction_isolation": "repeatable read",
            "clean_psql_exit": True,
            "session_format_settings_applied": True,
        })

        # Decode again only after the database transaction and process are gone.
        replayed_boundaries = {
            spec.source_key: _decode_boundary_frame(spool.read(spec.stage), spec)
            for spec in BOUNDARY_STAGES
        }
        _validate_boundary_expectations(replayed_boundaries, preregistered)
        expected_global_inputs = crosswalk_global_denominators_from_boundaries(
            replayed_boundaries
        )
        expected_physical_inputs = (
            crosswalk_physical_input_denominators_from_boundaries(
                replayed_boundaries
            )
        )
        observed_physical_inputs = dict.fromkeys(expected_physical_inputs, 0)
        logical_fragments: dict[str, dict[int, dict[str, Any]]] = {
            spec.stage: {} for spec in CROSSWALK_STAGES
        }
        run_spool = _AnonymousSortedRunSpool(destination)
        report["confirmed_controls"]["anonymous_sorted_run_spool"] = True
        for spec in CROSSWALK_STAGES:
            physical_specs = CROSSWALK_STATEMENTS_BY_LOGICAL_STAGE[spec.stage]
            for index in range(BUCKET_COUNT):
                physical_fragments = {
                    physical.stage: _decode_crosswalk_frame(
                        spool.read(f"{physical.stage}_bucket_{index}"),
                        physical,
                        index,
                    )
                    for physical in physical_specs
                }
                for physical in physical_specs:
                    if physical.bucket_input_source is None:
                        continue
                    value = physical_fragments[physical.stage]["controls"][
                        "bucket_input_rows"
                    ]
                    current = observed_physical_inputs[physical.stage]
                    if current > MAX_EXACT_COUNT - value:
                        raise DatabaseError(
                            "A Query-202 physical input denominator exceeded its integer limit."
                        )
                    observed_physical_inputs[physical.stage] = current + value
                logical = combine_crosswalk_statement_fragments(
                    spec, index, physical_fragments
                )
                run_spool.append(
                    f"{spec.stage}_bucket_{index}", logical["records"]
                )
                logical_fragments[spec.stage][index] = {
                    key: value for key, value in logical.items() if key != "records"
                }
                del logical, physical_fragments
        if observed_physical_inputs != expected_physical_inputs:
            raise DatabaseError(
                "A Query-202 physical source denominator failed boundary conservation."
            )
        replayed_crosswalk_snapshots = {
            spec.stage: {
                "snapshot_token": logical_fragments[spec.stage][0]["snapshot_token"]
            }
            for spec in CROSSWALK_STAGES
        }
        verified_snapshot = _assert_one_snapshot(
            replayed_boundaries, replayed_crosswalk_snapshots
        )
        if verified_snapshot != snapshot_token:
            raise DatabaseError("Query-202 replayed frame snapshot lineage changed.")

        # Every raw frame has now been replayed into independently bounded,
        # anonymous, compressed logical-bucket runs.  Release the frame spool
        # before either external merge pass or value persistence.
        cumulative_frame_bytes = spool.total_raw_bytes
        cumulative_spool_bytes = spool.total_stored_bytes
        cumulative_merge_run_raw_bytes = run_spool.total_raw_bytes
        cumulative_merge_run_spool_bytes = run_spool.total_stored_bytes
        merge_run_ledger = run_spool.stage_ledger()
        try:
            spool.close()
        except Exception as exc:
            raise DatabaseError(
                "Query-202 could not release its anonymous frame spool."
            ) from exc
        spool = None

        crosswalk_summaries = {
            spec.stage: _scan_external_crosswalk(
                spec,
                logical_fragments[spec.stage],
                run_spool,
                expected_global_input_rows=expected_global_inputs[spec.stage],
            )
            for spec in CROSSWALK_STAGES
        }
        if any(
            source["snapshot_token"] != snapshot_token
            for source in crosswalk_summaries.values()
        ):
            raise DatabaseError("Query-202 external-merge snapshot lineage changed.")

        private_path = destination / (QUERY_NAME + ".private.jsonl.gz")
        value_paths.append(private_path)
        private_artifact, private_view = _write_private_ndjson(
            private_path,
            replayed_boundaries,
            crosswalk_summaries,
            run_spool,
            preregistered,
            snapshot_token,
        )
        if _mode(private_path) != "0600":
            raise DatabaseError("A Query-202 private artifact has an unsafe mode.")
        try:
            run_spool.close()
        except Exception as exc:
            raise DatabaseError(
                "Query-202 could not release its anonymous sorted-run spool."
            ) from exc
        run_spool = None

        summary = build_aggregate_summary(private_view)
        executed_sql = ("".join(executed_controls) + quit_control).encode("utf-8")
        if report["confirmed_controls"]["rollback"] is not True or returncode != 0:
            raise DatabaseError("Query-202 evidence cannot persist before rollback and clean exit.")
        if len(executed_sql) > MAX_EXECUTED_SQL_BYTES:
            raise DatabaseError("Query-202 executed SQL exceeded its byte limit.")
        summary["private_artifact_hashes"] = {
            "private_values_encoding": private_artifact["encoding"],
            "private_values_sha256": private_artifact["sha256"],
            "private_values_raw_sha256": private_artifact["raw_sha256"],
            "executed_sql_sha256": _sha(executed_sql),
        }
        _assert_value_free_public_payload(summary, [])
        summary_bytes = (
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        entry.update({
            "private_values_file": private_path.name,
            "private_values_encoding": private_artifact["encoding"],
            "private_values_sha256": private_artifact["sha256"],
            "private_values_bytes": private_artifact["bytes"],
            "private_values_raw_sha256": private_artifact["raw_sha256"],
            "private_values_raw_bytes": private_artifact["raw_bytes"],
            "private_values_records": private_artifact["records"],
            "private_values_persisted": True,
        })
        report["artifact_modes"]["value_files"][private_path.name] = "0600"
        artifacts = (
            (QUERY_NAME + ".executed.sql", executed_sql, "executed_sql"),
            (QUERY_NAME + ".aggregate-summary.json", summary_bytes, "aggregate_summary"),
        )
        for filename, payload, role in artifacts:
            path = destination / filename
            value_paths.append(path)
            _write_private(path, payload)
            if _mode(path) != "0600":
                raise DatabaseError("A Query-202 private artifact has an unsafe mode.")
            entry[role + "_file"] = filename
            entry[role + "_sha256"] = _sha(payload)
            entry[role + "_bytes"] = len(payload)
            entry[role + "_persisted"] = True
            report["artifact_modes"]["value_files"][filename] = "0600"
        entry["boundary_summaries"] = summary["boundary_summaries"]
        entry["semantic_seed_summary"] = summary["semantic_seed_summary"]
        entry["crosswalk_summaries"] = summary["crosswalk_summaries"]
        entry["snapshot_token_sha256"] = snapshot_sha256
        entry["status"] = "complete"
        for stage in stages.values():
            stage["status"] = "complete"
        report["status"] = "complete"
    except DatabaseError:
        report["status"] = "failed"
    except Exception:
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
        if spool is not None:
            cumulative_frame_bytes = spool.total_raw_bytes
            cumulative_spool_bytes = spool.total_stored_bytes
            try:
                spool.close()
            except BaseException:
                report["status"] = "failed"
        if run_spool is not None:
            cumulative_merge_run_raw_bytes = run_spool.total_raw_bytes
            cumulative_merge_run_spool_bytes = run_spool.total_stored_bytes
            try:
                run_spool.close()
            except BaseException:
                report["status"] = "failed"
        if report["status"] != "complete":
            for stage in stages.values():
                if stage["status"] in ("running", "validated_in_anonymous_spool"):
                    stage["status"] = "failed"
            entry["failure_value_cleanup_confirmed"] = _remove_values(value_paths)
            entry["private_values_persisted"] = False
            entry["executed_sql_persisted"] = False
            entry["aggregate_summary_persisted"] = False
            report["artifact_modes"]["value_files"] = {}
            report["error"] = PUBLIC_FAILURE_ERROR
            entry["status"] = "failed"
        entry["cumulative_frame_bytes"] = cumulative_frame_bytes
        entry["cumulative_spool_bytes"] = cumulative_spool_bytes
        entry["cumulative_merge_run_raw_bytes"] = cumulative_merge_run_raw_bytes
        entry["cumulative_merge_run_spool_bytes"] = cumulative_merge_run_spool_bytes
        entry["merge_run_ledger"] = merge_run_ledger
        entry["cumulative_control_bytes"] = cumulative_control_bytes
        entry["finished_at_utc"] = _now()
        entry["elapsed_seconds"] = round(time.monotonic() - started, 6)
        report["finished_at_utc"] = _now()
        report["elapsed_seconds"] = entry["elapsed_seconds"]
        boundary_payloads.clear()
        crosswalk_controls.clear()
        try:
            _assert_value_free_public_payload(report, [])
            _write_private(
                manifest_path,
                (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            )
            if _mode(manifest_path) != "0600":
                raise DatabaseError("The Query-202 manifest has an unsafe mode.")
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
            "boundary_summaries": entry["boundary_summaries"],
            "semantic_seed_summary": entry["semantic_seed_summary"],
            "crosswalk_summaries": entry["crosswalk_summaries"],
            "private_values_sha256": entry["private_values_sha256"],
            "private_values_raw_sha256": entry["private_values_raw_sha256"],
            "executed_sql_sha256": entry["executed_sql_sha256"],
            "aggregate_summary_sha256": entry["aggregate_summary_sha256"],
        })
    else:
        result["note"] = (
            "No raw Query-202 value artifact was retained unless rollback and a "
            "clean psql exit had both already been confirmed."
        )
    return result
