"""Three-stage, same-snapshot runner for potassium product source closure.

The first SELECT discovers controlled source names.  The second uses the exact
detail-name set to derive identity-consistent local product-code seeds.  The
third computes aggregate closure evidence.  All three SELECTs execute in one
persistent psql session and one REPEATABLE READ READ ONLY transaction.  Values
discovered from MIMIC-IV are persisted only after an explicit rollback.
"""
from __future__ import annotations

import base64
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import subprocess
import time
from typing import Any

from .database import DatabaseError, PsqlClient, _safe_error, _statement_body


QUERY_NAME = "potassium_product_source_closure"
NAMES_DISCOVERY_FILE = "sql/profiling/200a_potassium_product_source_discovery.sql"
DETAIL_SEED_DISCOVERY_FILE = (
    "sql/profiling/200a2_potassium_product_detail_seed_discovery.sql"
)
CLOSURE_TEMPLATE_FILE = "sql/profiling/200b_potassium_product_source_closure.sql"
MAX_ROWS = 10_000
MAX_DISCOVERY_BYTES = 8 * 1024 * 1024
MAX_RESULT_BYTES = 128 * 1024 * 1024
MAX_DISCOVERY_VALUES = 20_000
MAX_DISCOVERY_VALUE_BYTES = 4 * 1024 * 1024
EXPECTED_OUTPUT_COLUMNS = ["section", "dimensions", "records", "counters"]
CLOSURE_CONTROL_COLUMNS = [
    "transaction_isolation", "transaction_read_only", "snapshot_token",
]
SNAPSHOT_PATTERN = re.compile(r"^[0-9]+:[0-9]+:[0-9,]*$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_private(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex_text(value: str) -> str:
    """Produce a SQL expression without placing text inside a SQL literal."""
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise DatabaseError(
            "Staged discovery contained a controlled-vocabulary value that is not valid UTF-8."
        ) from exc
    if not encoded or len(encoded) > 2048 or b"\x00" in encoded:
        raise DatabaseError("Staged discovery contained an invalid controlled-vocabulary value.")
    return "convert_from(decode('" + encoded.hex() + "','hex'),'UTF8')"


def _unicode_literal(value: str, sql_type: str) -> str:
    """Return a constant-foldable PostgreSQL literal with no raw source text."""
    if sql_type not in {"text", "varchar", "varchar(30)", "varchar(255)"}:
        raise DatabaseError("An unsupported native SQL type was requested for a private value.")
    _hex_text(value)  # Reuse UTF-8, NUL, emptiness and byte-length validation.
    escaped = "".join(
        f"\\{ord(character):04X}"
        if ord(character) <= 0xFFFF
        else f"\\+{ord(character):06X}"
        for character in value
    )
    return f"U&'{escaped}'::{sql_type}"


def _constant_array(values: list[str], sql_type: str) -> str:
    if not values:
        return f"ARRAY[]::{sql_type}[]"
    return (
        "ARRAY[" + ",".join(_unicode_literal(value, sql_type) for value in values)
        + f"]::{sql_type}[]"
    )


def _values_one(values: list[str], column: str) -> str:
    if not values:
        return f"    SELECT NULL::varchar AS {column} WHERE false"
    return "    VALUES\n" + ",\n".join(
        f"      ({_hex_text(value)}::varchar)" for value in values
    )


def _native_values_one(values: list[str], column: str, sql_type: str) -> str:
    """Render exact constant VALUES using the source column's native type."""
    if not values:
        return f"    SELECT NULL::{sql_type} AS {column} WHERE false"
    return "    VALUES\n" + ",\n".join(
        f"      ({_unicode_literal(value, sql_type)})" for value in values
    )


def _values_seeds(values: list[dict[str, Any]]) -> str:
    if not values:
        return (
            "    SELECT NULL::varchar AS product_code,0::bigint AS lexical_detail_rows,"
            "0::bigint AS lexical_emar_events,0::bigint AS lexical_descriptions WHERE false"
        )
    return "    VALUES\n" + ",\n".join(
        "      (" + _hex_text(item["product_code"]) + "::varchar,"
        + str(item["lexical_detail_rows"]) + "::bigint,"
        + str(item["lexical_emar_events"]) + "::bigint,"
        + str(item["lexical_descriptions"]) + "::bigint)"
        for item in values
    )


def _values_indexed(discovery: dict[str, Any]) -> str:
    rows: list[tuple[str, str]] = []
    for key, source in (
        ("emar_names", "emar_medication"),
        ("detail_names", "detail_product_description"),
        ("pharmacy_names", "pharmacy_medication"),
    ):
        rows.extend((source, value) for value in discovery[key])
    if not rows:
        return "    SELECT NULL::text AS source_type,NULL::varchar AS raw_name WHERE false"
    return "    VALUES\n" + ",\n".join(
        "      ('" + source + "'::text," + _hex_text(value) + "::varchar)"
        for source, value in rows
    )


def _decode_unique_json(payload: bytes, stage_label: str) -> dict[str, Any]:
    if len(payload) > MAX_DISCOVERY_BYTES:
        raise DatabaseError(f"{stage_label} exceeded its private payload byte limit.")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise DatabaseError(f"{stage_label} JSON contains a duplicate object key.")
            result[key] = item
        return result

    try:
        value = json.loads(payload, object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DatabaseError(f"{stage_label} returned malformed private JSON.") from exc
    if not isinstance(value, dict):
        raise DatabaseError(f"{stage_label} returned a non-object JSON payload.")
    return value


def _validate_snapshot_token(value: Any, stage_label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 4096
        or SNAPSHOT_PATTERN.fullmatch(value) is None
    ):
        raise DatabaseError(f"{stage_label} returned an invalid PostgreSQL snapshot token.")
    active = value.split(":", 2)[2]
    if active and any(not item for item in active.split(",")):
        raise DatabaseError(f"{stage_label} returned an invalid PostgreSQL snapshot token.")
    return value


def _validate_common_controls(
    value: dict[str, Any], expected_stage: str, stage_label: str
) -> None:
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise DatabaseError(f"{stage_label} returned an unsupported schema version.")
    if value.get("stage") != expected_stage:
        raise DatabaseError(f"{stage_label} returned the wrong stage identity.")
    if (
        value.get("transaction_isolation") != "repeatable read"
        or value.get("transaction_read_only") != "on"
    ):
        raise DatabaseError(
            f"{stage_label} did not confirm the required read-only repeatable-read transaction."
        )
    _validate_snapshot_token(value.get("snapshot_token"), stage_label)


def _validate_names_discovery(payload: bytes) -> dict[str, Any]:
    stage_label = "Names discovery"
    value = _decode_unique_json(payload, stage_label)
    expected = {
        "schema_version", "stage", "transaction_isolation",
        "transaction_read_only", "snapshot_token",
        "non_null_emar_medication_names",
        "non_null_detail_product_descriptions",
        "non_null_pharmacy_medication_names", "emar_names", "detail_names",
        "pharmacy_names", "prescription_names",
    }
    if set(value) != expected:
        raise DatabaseError("Names discovery returned an unexpected schema.")
    _validate_common_controls(value, "names_discovery", stage_label)
    for key in (
        "non_null_emar_medication_names",
        "non_null_detail_product_descriptions",
        "non_null_pharmacy_medication_names",
    ):
        if type(value[key]) is not int or value[key] < 0:
            raise DatabaseError("Names discovery returned an invalid aggregate count.")

    total_values = 0
    total_bytes = 0
    for key in ("emar_names", "detail_names", "pharmacy_names", "prescription_names"):
        items = value[key]
        if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
            raise DatabaseError("Names discovery returned an invalid vocabulary array.")
        if len(items) != len(set(items)):
            raise DatabaseError("Names discovery vocabulary arrays must be unique.")
        for item in items:
            _hex_text(item)
            total_bytes += len(item.encode("utf-8"))
        total_values += len(items)
        # Database collation is deployment-specific.  Sorting after validating
        # uniqueness gives deterministic rendering without changing membership.
        value[key] = sorted(items)
    for values_key, count_key in (
        ("emar_names", "non_null_emar_medication_names"),
        ("detail_names", "non_null_detail_product_descriptions"),
        ("pharmacy_names", "non_null_pharmacy_medication_names"),
    ):
        if len(value[values_key]) > value[count_key]:
            raise DatabaseError("Names discovery vocabulary count violates its source bound.")
    if total_values > MAX_DISCOVERY_VALUES:
        raise DatabaseError("Names discovery exceeded its vocabulary row limit.")
    if total_bytes > MAX_DISCOVERY_VALUE_BYTES:
        raise DatabaseError("Names discovery exceeded its vocabulary byte limit.")
    return value


def _validate_detail_seed_discovery(
    payload: bytes, names: dict[str, Any]
) -> dict[str, Any]:
    stage_label = "Detail-seed discovery"
    value = _decode_unique_json(payload, stage_label)
    expected = {
        "schema_version", "stage", "transaction_isolation",
        "transaction_read_only", "snapshot_token",
        "identity_consistent_lexical_detail_product_rows",
        "identity_consistent_lexical_detail_events", "seed_product_codes",
    }
    if set(value) != expected:
        raise DatabaseError("Detail-seed discovery returned an unexpected schema.")
    _validate_common_controls(value, "detail_seed_discovery", stage_label)
    for key in (
        "identity_consistent_lexical_detail_product_rows",
        "identity_consistent_lexical_detail_events",
    ):
        if type(value[key]) is not int or value[key] < 0:
            raise DatabaseError("Detail-seed discovery returned an invalid aggregate count.")
    if (
        value["identity_consistent_lexical_detail_product_rows"]
        < value["identity_consistent_lexical_detail_events"]
    ):
        raise DatabaseError("Detail-seed discovery counts violate event-row conservation.")

    seeds = value["seed_product_codes"]
    seed_keys = {
        "product_code", "lexical_detail_rows", "lexical_emar_events",
        "lexical_descriptions",
    }
    if not isinstance(seeds, list) or any(
        not isinstance(item, dict) or set(item) != seed_keys for item in seeds
    ):
        raise DatabaseError("Detail-seed discovery returned an invalid seed array.")
    if any(not isinstance(item["product_code"], str) for item in seeds):
        raise DatabaseError("Detail-seed discovery product codes must be text.")
    if len(seeds) != len({item["product_code"] for item in seeds}):
        raise DatabaseError("Detail-seed discovery product codes must be unique.")
    total_bytes = 0
    for item in seeds:
        _hex_text(item["product_code"])
        total_bytes += len(item["product_code"].encode("utf-8"))
        for key in seed_keys - {"product_code"}:
            if type(item[key]) is not int or item[key] <= 0:
                raise DatabaseError("Detail-seed counts must be positive integers.")
        if (
            item["lexical_emar_events"] > item["lexical_detail_rows"]
            or item["lexical_descriptions"] > item["lexical_detail_rows"]
            or item["lexical_emar_events"]
            > value["identity_consistent_lexical_detail_events"]
            or item["lexical_descriptions"] > len(names["detail_names"])
        ):
            raise DatabaseError("Detail-seed aggregates violate discovery bounds.")
    if (
        sum(item["lexical_detail_rows"] for item in seeds)
        > value["identity_consistent_lexical_detail_product_rows"]
    ):
        raise DatabaseError("Detail-seed rows violate discovery conservation.")
    if len(seeds) > MAX_DISCOVERY_VALUES:
        raise DatabaseError("Detail-seed discovery exceeded its seed row limit.")
    if total_bytes > MAX_DISCOVERY_VALUE_BYTES:
        raise DatabaseError("Detail-seed discovery exceeded its seed byte limit.")
    value["seed_product_codes"] = sorted(seeds, key=lambda item: item["product_code"])
    return value


def _assert_same_snapshot_controls(stages: dict[str, dict[str, Any]]) -> str:
    if not stages:
        raise DatabaseError("No staged PostgreSQL controls were available for validation.")
    snapshots: set[str] = set()
    for stage_label, value in stages.items():
        if (
            value.get("transaction_isolation") != "repeatable read"
            or value.get("transaction_read_only") != "on"
        ):
            raise DatabaseError(
                f"{stage_label} did not remain in the required read-only transaction."
            )
        snapshots.add(_validate_snapshot_token(value.get("snapshot_token"), stage_label))
    if len(snapshots) != 1:
        raise DatabaseError("Query-200 stages did not observe one identical snapshot token.")
    return next(iter(snapshots))


def _merge_discovery(
    names: dict[str, Any], seeds: dict[str, Any]
) -> dict[str, Any]:
    _assert_same_snapshot_controls({
        "names_discovery": names,
        "detail_seed_discovery": seeds,
    })
    return {
        "schema_version": 2,
        "stage": "merged_discovery",
        "transaction_isolation": names["transaction_isolation"],
        "transaction_read_only": names["transaction_read_only"],
        "snapshot_token": names["snapshot_token"],
        "non_null_emar_medication_names": names["non_null_emar_medication_names"],
        "non_null_detail_product_descriptions": names[
            "non_null_detail_product_descriptions"
        ],
        "non_null_pharmacy_medication_names": names[
            "non_null_pharmacy_medication_names"
        ],
        "identity_consistent_lexical_detail_product_rows": seeds[
            "identity_consistent_lexical_detail_product_rows"
        ],
        "identity_consistent_lexical_detail_events": seeds[
            "identity_consistent_lexical_detail_events"
        ],
        "emar_names": names["emar_names"],
        "detail_names": names["detail_names"],
        "pharmacy_names": names["pharmacy_names"],
        "prescription_names": names["prescription_names"],
        "seed_product_codes": seeds["seed_product_codes"],
    }


def render_detail_seed_discovery(template: str, names: dict[str, Any]) -> str:
    marker = "__DETAIL_NAME_VALUES__"
    if template.count(marker) != 1:
        raise DatabaseError("Detail-seed template marker is missing or repeated.")
    rendered = template.replace(
        marker,
        _native_values_one(names["detail_names"], "raw_name", "varchar(255)"),
    )
    if "__" in rendered:
        raise DatabaseError("Detail-seed template contains an unresolved marker.")
    return _statement_body(rendered)


def render_stage_b(template: str, discovery: dict[str, Any]) -> str:
    replacements = {
        "__DISCOVERY_COUNTS__": ",".join(str(discovery[key]) for key in (
            "non_null_emar_medication_names", "non_null_detail_product_descriptions",
            "non_null_pharmacy_medication_names",
            "identity_consistent_lexical_detail_product_rows",
            "identity_consistent_lexical_detail_events",
        )),
        "__INDEXED_LEXICAL_NAMES__": _values_indexed(discovery),
        "__PRESCRIPTION_NAMES__": _values_one(discovery["prescription_names"], "raw_name"),
        "__SEED_PRODUCT_CODES__": _values_seeds(discovery["seed_product_codes"]),
        "__EMAR_NAME_ARRAY__": _constant_array(discovery["emar_names"], "text"),
        "__DETAIL_NAME_ARRAY__": _constant_array(discovery["detail_names"], "varchar"),
        "__PHARMACY_NAME_ARRAY__": _constant_array(discovery["pharmacy_names"], "text"),
        "__PRESCRIPTION_NAME_ARRAY__": _constant_array(
            discovery["prescription_names"], "varchar"
        ),
        "__SEED_PRODUCT_CODE_ARRAY__": _constant_array(
            [item["product_code"] for item in discovery["seed_product_codes"]],
            "varchar",
        ),
    }
    rendered = template
    for marker, replacement in replacements.items():
        if rendered.count(marker) != 1:
            raise DatabaseError("Closure template markers are missing or repeated.")
        rendered = rendered.replace(marker, replacement)
    if "__" in rendered:
        raise DatabaseError("Closure template contains an unresolved marker.")
    return _statement_body(rendered)


class _PersistentPsql:
    def __init__(self, client: PsqlClient, stderr_path: Path | None):
        self._stderr: io.BufferedWriter | None = None
        stderr_target: int | io.BufferedWriter
        if stderr_path is None:
            # Some formal evidence lifecycles must never put raw PostgreSQL
            # diagnostics on disk.  DEVNULL also keeps an unbounded stderr
            # stream from competing with their bounded private artifacts.
            stderr_target = subprocess.DEVNULL
        else:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(stderr_path, flags, 0o600)
            self._stderr = os.fdopen(descriptor, "wb")
            os.fchmod(self._stderr.fileno(), 0o600)
            stderr_target = self._stderr
        command = [
            client.psql, "-X", "--no-password", "--quiet", "--csv",
            "--set=ON_ERROR_STOP=1", "--set=VERBOSITY=verbose", "--file=-",
        ]
        try:
            self.process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=stderr_target, env=client.env,
            )
        except BaseException:
            if self._stderr is not None:
                self._stderr.close()
            raise
        self._buffer = bytearray()

    def send(self, sql: str) -> None:
        if self.process.stdin is None or self.process.poll() is not None:
            raise DatabaseError("Persistent PostgreSQL session ended before the next stage.")
        self.process.stdin.write(sql.encode("utf-8"))
        self.process.stdin.flush()

    def frame(self, marker: str, timeout: float, byte_limit: int) -> bytes:
        if self.process.stdout is None:
            raise DatabaseError("Persistent PostgreSQL session has no output channel.")
        target = marker.encode("ascii")
        selector = selectors.DefaultSelector()
        selector.register(self.process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        scan = 0
        in_quotes = False
        try:
            while True:
                while True:
                    newline = self._buffer.find(b"\n", scan)
                    if newline < 0:
                        break
                    line_start, line_end = scan, newline + 1
                    line = self._buffer[line_start:line_end]
                    outside_at_start = not in_quotes
                    index = 0
                    content = line.rstrip(b"\r\n")
                    while index < len(content):
                        if content[index] == 34:
                            if in_quotes and index + 1 < len(content) and content[index + 1] == 34:
                                index += 2
                                continue
                            in_quotes = not in_quotes
                        index += 1
                    scan = line_end
                    if outside_at_start and not in_quotes and content == target:
                        frame = bytes(self._buffer[:line_start])
                        del self._buffer[:line_end]
                        if len(frame) > byte_limit:
                            raise DatabaseError("PostgreSQL stage output exceeded its private byte limit.")
                        return frame
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DatabaseError("PostgreSQL staged inspection exceeded its process timeout.")
                ready = selector.select(remaining)
                if not ready:
                    raise DatabaseError("PostgreSQL staged inspection exceeded its process timeout.")
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise DatabaseError("Persistent PostgreSQL session ended before its control frame.")
                self._buffer.extend(chunk)
                if len(self._buffer) > byte_limit + 4096:
                    raise DatabaseError("PostgreSQL stage output exceeded its private byte limit.")
        finally:
            selector.close()

    def confirm_rollback(self, marker: str, timeout: float = 10) -> None:
        self.send("ROLLBACK;\n\\echo " + marker + "\n")
        frame = self.frame(marker, timeout, 4096)
        if frame.strip():
            raise DatabaseError("PostgreSQL returned unexpected output while confirming rollback.")

    def close(self) -> int:
        try:
            if self.process.poll() is None and self.process.stdin is not None:
                try:
                    self.process.stdin.write(b"\\q\n")
                    self.process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
        finally:
            if self._stderr is not None:
                self._stderr.close()
        return self.process.returncode if self.process.returncode is not None else -1


def _decode_payload_frame(frame: bytes, column: str, stage_label: str) -> bytes:
    try:
        text = frame.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text), strict=True)
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise DatabaseError(f"{stage_label} returned malformed CSV framing.") from exc
    if (
        reader.fieldnames != [column]
        or len(rows) != 1
        or set(rows[0]) != {column}
        or None in rows[0]
        or rows[0].get(column) is None
    ):
        raise DatabaseError(f"{stage_label} must return exactly one payload row.")
    try:
        return base64.b64decode(rows[0][column], validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise DatabaseError(f"{stage_label} returned malformed payload encoding.") from exc


def _parse_names_frame(frame: bytes) -> dict[str, Any]:
    return _validate_names_discovery(
        _decode_payload_frame(frame, "names_payload", "Names discovery")
    )


def _parse_detail_seed_frame(
    frame: bytes, names: dict[str, Any]
) -> dict[str, Any]:
    return _validate_detail_seed_discovery(
        _decode_payload_frame(
            frame, "detail_seed_payload", "Detail-seed discovery"
        ),
        names,
    )


def _parse_result_frame(
    frame: bytes,
) -> tuple[str, list[dict[str, str]], dict[str, str]]:
    try:
        text = frame.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text), strict=True)
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise DatabaseError("Aggregate closure returned malformed CSV data.") from exc
    expected = EXPECTED_OUTPUT_COLUMNS + CLOSURE_CONTROL_COLUMNS
    if reader.fieldnames != expected:
        raise DatabaseError("Aggregate closure returned unexpected columns.")
    if (
        not rows
        or len(rows) > MAX_ROWS
        or any(None in row or any(v is None for v in row.values()) for row in rows)
    ):
        raise DatabaseError(
            "Aggregate closure exceeded its row limit or returned malformed rows."
        )
    controls = {
        key: rows[0][key] for key in CLOSURE_CONTROL_COLUMNS
    }
    _assert_same_snapshot_controls({"aggregate_closure": controls})
    if any(
        any(row[key] != controls[key] for key in CLOSURE_CONTROL_COLUMNS)
        for row in rows
    ):
        raise DatabaseError("Aggregate closure rows reported inconsistent controls.")
    aggregate_rows = [
        {key: row[key] for key in EXPECTED_OUTPUT_COLUMNS} for row in rows
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output, fieldnames=EXPECTED_OUTPUT_COLUMNS, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(aggregate_rows)
    return output.getvalue(), aggregate_rows, controls


def run_staged_source_closure(root: Path) -> dict[str, Any]:
    """Run query 200 and return terminal-safe execution metadata only."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = root / "artifacts" / "profiling" / stamp
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    destination.chmod(0o700)
    manifest_path = destination / "manifest.json"
    stderr_path = destination / "psql.stderr"
    started = time.monotonic()
    report: dict[str, Any] = {
        "schema_version": 2, "started_at_utc": _now(), "status": "running",
        "requested_read_only": True, "read_only_confirmed": False,
        "requested_same_snapshot": True, "same_snapshot_confirmed": False,
        "requested_transaction_isolation": "repeatable read",
        "transaction_isolation_confirmed": None,
        "requested_jit": "off",
        "rollback_confirmed": False, "timeout_ms_per_statement": 60000,
        "scope": "aggregate_private_staged_source_closure",
        "dataset_version_verified": False,
        "selected_queries": [QUERY_NAME], "queries": [],
        "limitations": "Three-SELECT exact-value source closure inside one read-only repeatable-read snapshot. Controlled dictionaries remain private; no cohort is validated.",
        "source_scan_counts": {
            "prescriptions_drug_names_discovery": 1,
            "prescriptions_drug_aggregate_closure": 1,
            "prescriptions_drug_total": 2,
        },
    }
    entry: dict[str, Any] = {
        "query": QUERY_NAME, "file": CLOSURE_TEMPLATE_FILE, "scope": "aggregate",
        "status": "running", "started_at_utc": _now(), "max_rows": MAX_ROWS,
        "work_mem_mb": 128, "rows": None, "output_sha256": None,
        "output_persisted": False, "completeness_status": "not_evaluated",
        "private_discovery_persisted": False,
        "execution": "staged_names_seed_closure_same_snapshot",
        "stages": {
            "names_discovery": {
                "file": NAMES_DISCOVERY_FILE, "status": "pending",
            },
            "detail_seed_discovery": {
                "file": DETAIL_SEED_DISCOVERY_FILE, "status": "pending",
            },
            "aggregate_closure": {
                "file": CLOSURE_TEMPLATE_FILE, "status": "pending",
            },
        },
    }
    report["queries"].append(entry)
    session: _PersistentPsql | None = None
    pending_error: str | None = None
    try:
        names_path = root / NAMES_DISCOVERY_FILE
        seed_path = root / DETAIL_SEED_DISCOVERY_FILE
        closure_path = root / CLOSURE_TEMPLATE_FILE
        names_bytes = names_path.read_bytes()
        seed_bytes = seed_path.read_bytes()
        closure_bytes = closure_path.read_bytes()
        names_sql = _statement_body(names_bytes.decode("utf-8"))
        seed_template = seed_bytes.decode("utf-8")
        closure_template = closure_bytes.decode("utf-8")
        names_stage = entry["stages"]["names_discovery"]
        seed_stage = entry["stages"]["detail_seed_discovery"]
        closure_stage = entry["stages"]["aggregate_closure"]
        names_stage["template_sha256"] = _sha(names_bytes)
        names_stage["rendered_sha256"] = _sha(names_sql.encode())
        names_stage["rendered_bytes"] = len(names_sql.encode())
        seed_stage["template_sha256"] = _sha(seed_bytes)
        closure_stage["template_sha256"] = _sha(closure_bytes)
        client = PsqlClient(root, 60000)
        session = _PersistentPsql(client, stderr_path)

        marker_names = "__APRIL_NAMES_" + secrets.token_hex(24) + "__"
        marker_seed = "__APRIL_SEED_" + secrets.token_hex(24) + "__"
        marker_closure = "__APRIL_CLOSURE_" + secrets.token_hex(24) + "__"
        marker_rollback = "__APRIL_ROLLBACK_" + secrets.token_hex(24) + "__"
        names_control = (
            "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
            "SET LOCAL statement_timeout = '60000ms';\n"
            "SET LOCAL lock_timeout = '2000ms';\n"
            "SET LOCAL standard_conforming_strings = on;\n"
            "SET LOCAL work_mem = '128MB';\n"
            "SET LOCAL jit = off;\n" + names_sql + ";\n"
            "\\echo " + marker_names + "\n"
        )
        names_stage["control_sha256"] = _sha(names_control.encode())
        names_stage["status"] = "running"
        names_started = time.monotonic()
        session.send(names_control)
        names_frame = session.frame(
            marker_names, 70, MAX_DISCOVERY_BYTES * 2
        )
        names_stage["elapsed_seconds"] = round(
            time.monotonic() - names_started, 6
        )
        names_stage["frame_sha256"] = _sha(names_frame)
        names_stage["frame_bytes"] = len(names_frame)
        names = _parse_names_frame(names_frame)
        names_stage["status"] = "validated_in_memory"

        rendered_seed = render_detail_seed_discovery(seed_template, names)
        seed_stage["rendered_sha256"] = _sha(rendered_seed.encode())
        seed_stage["rendered_bytes"] = len(rendered_seed.encode())
        seed_control = (
            rendered_seed + ";\n\\echo " + marker_seed + "\n"
        )
        seed_stage["control_sha256"] = _sha(seed_control.encode())
        seed_stage["status"] = "running"
        seed_started = time.monotonic()
        session.send(seed_control)
        seed_frame = session.frame(marker_seed, 70, MAX_DISCOVERY_BYTES * 2)
        seed_stage["elapsed_seconds"] = round(time.monotonic() - seed_started, 6)
        seed_stage["frame_sha256"] = _sha(seed_frame)
        seed_stage["frame_bytes"] = len(seed_frame)
        seeds = _parse_detail_seed_frame(seed_frame, names)
        seed_stage["status"] = "validated_in_memory"

        discovery = _merge_discovery(names, seeds)
        rendered_closure = render_stage_b(closure_template, discovery)
        closure_stage["rendered_sha256"] = _sha(rendered_closure.encode())
        closure_stage["rendered_bytes"] = len(rendered_closure.encode())
        bounded = (
            "SELECT section,dimensions,records,counters,\n"
            "       current_setting('transaction_isolation') AS transaction_isolation,\n"
            "       current_setting('transaction_read_only') AS transaction_read_only,\n"
            "       pg_current_snapshot()::text AS snapshot_token\n"
            "FROM (\n" + rendered_closure
            + f"\n) AS april_profile_rows LIMIT {MAX_ROWS + 1};"
        )
        closure_control = bounded + "\n\\echo " + marker_closure + "\n"
        rollback_control = "ROLLBACK;\n\\echo " + marker_rollback + "\n"
        closure_stage["control_sha256"] = _sha(closure_control.encode())
        entry["rollback_control_sha256"] = _sha(rollback_control.encode())

        closure_stage["status"] = "running"
        closure_started = time.monotonic()
        session.send(closure_control)
        closure_frame = session.frame(marker_closure, 70, MAX_RESULT_BYTES)
        closure_stage["elapsed_seconds"] = round(
            time.monotonic() - closure_started, 6
        )
        closure_stage["frame_sha256"] = _sha(closure_frame)
        closure_stage["frame_bytes"] = len(closure_frame)
        csv_text, rows, closure_controls = _parse_result_frame(closure_frame)
        closure_stage["status"] = "validated_in_memory"

        snapshot_token = _assert_same_snapshot_controls({
            "names_discovery": names,
            "detail_seed_discovery": seeds,
            "aggregate_closure": closure_controls,
        })
        snapshot_sha256 = _sha(snapshot_token.encode())
        for stage in (names_stage, seed_stage, closure_stage):
            stage["observed_transaction_isolation"] = "repeatable read"
            stage["observed_transaction_read_only"] = "on"
            stage["observed_snapshot_sha256"] = snapshot_sha256

        session.confirm_rollback(marker_rollback)
        report["rollback_confirmed"] = True
        returncode = session.close()
        session = None
        entry["psql_returncode"] = returncode
        if returncode != 0:
            raise DatabaseError("PostgreSQL session did not exit cleanly after confirmed rollback.")
        report["read_only_confirmed"] = True
        report["transaction_isolation_confirmed"] = "repeatable read"
        report["same_snapshot_confirmed"] = True
        report["snapshot_token_sha256"] = snapshot_sha256

        # Persist controlled values and aggregate output only after the database
        # transaction has explicitly rolled back and psql has exited cleanly.
        private_dictionary = (
            json.dumps(discovery, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode()
        dictionary_file = QUERY_NAME + ".discovery.json"
        _write_private(destination / dictionary_file, private_dictionary)
        entry["discovery_file"] = dictionary_file
        entry["discovery_sha256"] = _sha(private_dictionary)
        entry["private_discovery_persisted"] = True
        entry["discovery_value_counts"] = {
            key: len(discovery[key]) for key in (
                "emar_names", "detail_names", "pharmacy_names",
                "prescription_names", "seed_product_codes",
            )
        }

        executed = (
            names_control + seed_control + closure_control
            + rollback_control + "\\q\n"
        ).encode()
        executed_file = QUERY_NAME + ".executed.sql"
        _write_private(destination / executed_file, executed)
        entry["executed_sql_file"] = executed_file
        entry["executed_sql_sha256"] = _sha(executed)
        output = csv_text.encode("utf-8")
        output_file = QUERY_NAME + ".csv"
        _write_private(destination / output_file, output)
        for stage in (names_stage, seed_stage, closure_stage):
            stage["status"] = "complete"
        entry.update(
            status="complete", rows=len(rows), output_file=output_file,
            output_sha256=_sha(output), output_persisted=True,
            completeness_status="complete_within_declared_scope",
        )
        report["status"] = "complete"
    except DatabaseError as exc:
        report["status"] = "failed"
        pending_error = str(exc)
    except Exception:
        report["status"] = "failed"
        pending_error = "Staged PostgreSQL inspection failed before it could produce verified evidence."
    finally:
        if session is not None:
            try:
                entry["psql_returncode"] = session.close()
            except Exception:
                entry["psql_returncode"] = None
        if report["status"] != "complete":
            if stderr_path.is_file():
                try:
                    raw_error = stderr_path.read_text(errors="replace")[-16384:]
                except OSError:
                    raw_error = ""
            else:
                raw_error = ""
            report["error"] = _safe_error(raw_error) if raw_error.strip() else (
                pending_error or "Staged PostgreSQL inspection failed."
            )
            entry["status"] = "failed"
            entry["error"] = report["error"]
        if stderr_path.is_file():
            try:
                stderr_bytes = stderr_path.read_bytes()
                entry["stderr_file"] = stderr_path.name
                entry["stderr_bytes"] = len(stderr_bytes)
                entry["stderr_sha256"] = _sha(stderr_bytes)
            except OSError:
                pass
        entry["finished_at_utc"] = _now()
        entry["elapsed_seconds"] = round(time.monotonic() - started, 6)
        report["finished_at_utc"] = _now()
        _write_private(manifest_path, (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())
    summary = {
        "status": report["status"], "report": str(manifest_path),
        "queries": [{key: entry.get(key) for key in (
            "query", "scope", "status", "rows", "completeness_status",
        )}],
        "note": "Only execution metadata is printed. Staged dictionaries and closure aggregates remain in private local artifacts.",
    }
    if "error" in report:
        summary["error"] = report["error"]
    return summary
