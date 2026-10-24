"""Independent offline audit for the D005 five-field mapping preflight.

The auditor uses only Python's standard library and never opens a database
connection.  It deliberately reimplements typed-value classification, set
hashing, implementation-bundle hashing, SQL-control reconstruction, and JSON
validation rather than importing the production runner.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tomllib
from typing import Any, Mapping
import unicodedata


QUERY_NAME = "potassium_mapping_preflight"
AUDIT_NAME = "potassium_mapping_preflight_offline_audit"
CONFIG_PATH = Path("config/preregistrations/d005_potassium_mapping_preflight.toml")
HASH_VERSION = b"typed-distinct-source-value-set-v1"
STATEMENT_TIMEOUT_MS = 120_000
PROCESS_TIMEOUT_SECONDS = 135
MAX_JSON_BYTES = 320 * 1024 * 1024
MAX_SQL_BYTES = 2 * 1024 * 1024
MAX_VALUE_UTF8_BYTES = 65_535
MAX_EXACT_ROW_COUNT = (1 << 63) - 1
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
MARKER_HEX = r"[0-9a-f]{48}"


@dataclass(frozen=True)
class SourceSpec:
    key: str
    field: str
    role: str
    sql_file: str


SOURCES = (
    SourceSpec(
        "emar_detail_route",
        "mimiciv_hosp.emar_detail.route",
        "route",
        "sql/profiling/202p1_potassium_emar_detail_route_vocabulary.sql",
    ),
    SourceSpec(
        "pharmacy_route",
        "mimiciv_hosp.pharmacy.route",
        "route",
        "sql/profiling/202p2_potassium_pharmacy_route_vocabulary.sql",
    ),
    SourceSpec(
        "prescriptions_route",
        "mimiciv_hosp.prescriptions.route",
        "route",
        "sql/profiling/202p3_potassium_prescriptions_route_vocabulary.sql",
    ),
    SourceSpec(
        "detail_product_description_other",
        "mimiciv_hosp.emar_detail.product_description_other",
        "product_description_other",
        "sql/profiling/202p4_potassium_product_description_other_vocabulary.sql",
    ),
    SourceSpec(
        "prescriptions_ndc",
        "mimiciv_hosp.prescriptions.ndc",
        "ndc",
        "sql/profiling/202p5_potassium_prescriptions_ndc_vocabulary.sql",
    ),
)
SOURCE_BY_KEY = {source.key: source for source in SOURCES}
SQL_PATHS = tuple(source.sql_file for source in SOURCES)
RUNNER_PATHS = (
    "src/april_repro/mapping_preflight.py",
    "scripts/run_potassium_mapping_preflight.py",
)
AUDITOR_PATHS = (
    "src/april_repro/mapping_preflight_audit.py",
    "scripts/audit_potassium_mapping_preflight.py",
)
BUNDLE_PATHS = {
    "sql": SQL_PATHS,
    "runner": RUNNER_PATHS,
    "offline_auditor": AUDITOR_PATHS,
}
BUNDLE_DIGEST_KEYS = {
    "sql": "sql_bundle_sha256",
    "runner": "runner_bundle_sha256",
    "offline_auditor": "offline_auditor_bundle_sha256",
}

PRIVATE_TOP_KEYS = {
    "schema_version", "query", "created_at_utc", "component_lineage",
    "typed_set_hash_contract", "nonnull_substate_classification_runtime",
    "transaction", "sources", "raw_values_are_exact_and_unnormalized",
    "contains_patient_or_event_identifiers", "contains_event_timestamps",
    "route_mapping_created", "external_api_called", "product_identity_decided",
    "final_source_policy",
}
PRIVATE_SOURCE_KEYS = {
    "source_field", "field_role", "sql_null_rows", "sql_null_present",
    "typed_distinct_values", "nonnull_distinct_values", "typed_set_sha256",
    "records",
}
PRIVATE_RECORD_KEYS = {
    "raw_is_null", "raw_value", "exact_row_count", "raw_utf8_bytes",
    "nonnull_substate",
}
SUMMARY_TOP_KEYS = {
    "schema_version", "query", "created_at_utc", "scope", "component_lineage",
    "source_summaries", "global_counts", "transaction_controls",
    "nonnull_substate_classification_runtime", "privacy", "boundary_guards",
    "private_artifact_hashes",
}
SUMMARY_SOURCE_KEYS = {
    "source_field", "field_role", "source_rows", "typed_distinct_values",
    "typed_state_row_counts", "typed_state_distinct_counts",
    "nonnull_substate_row_counts", "nonnull_substate_distinct_counts",
    "typed_set_sha256", "row_conservation_confirmed",
    "distinct_conservation_confirmed",
}
BOUNDARY_GUARDS = (
    "route_mapping_created", "external_api_called", "product_identity_decided",
    "event_mapping_created", "final_source_policy", "formal_action",
    "formal_episode", "formal_label", "formal_cohort",
)
MANIFEST_KEYS = {
    "schema_version", "started_at_utc", "status", "scope", "selected_queries",
    "requested_controls", "confirmed_controls", "artifact_modes",
    "component_preregistration", "implementation_bundles",
    "nonnull_substate_classification_runtime", "queries", "limitations",
    "sql_bundle_sha256", "finished_at_utc", "elapsed_seconds",
}
MANIFEST_ENTRY_KEYS = {
    "query", "status", "stages", "private_values_persisted",
    "executed_sql_persisted", "aggregate_summary_persisted", "psql_returncode",
    "private_values_file", "private_values_sha256", "private_values_bytes",
    "executed_sql_file", "executed_sql_sha256", "executed_sql_bytes",
    "aggregate_summary_file", "aggregate_summary_sha256",
    "aggregate_summary_bytes", "source_counts", "snapshot_token_sha256",
    "cumulative_frame_bytes", "cumulative_control_bytes", "stderr_file",
    "stderr_sha256", "stderr_bytes", "finished_at_utc", "elapsed_seconds",
}
MANIFEST_STAGE_KEYS = {
    "source_key", "source_field", "field_role", "file", "status", "rows",
    "statement_timeout_ms", "process_timeout_seconds", "template_sha256",
    "template_bytes", "control_sha256", "control_bytes", "elapsed_seconds",
    "frame_bytes", "source_rows", "typed_distinct_values",
    "nonnull_distinct_values", "sql_null_rows", "typed_set_sha256",
    "observed_transaction_isolation", "observed_transaction_read_only",
    "observed_snapshot_sha256",
}
MANIFEST_COMPONENT_KEYS = {
    "component_id", "status_at_start", "execution_status_at_start", "config",
    "config_sha256", "evidence_files_checked", "implementation_hashes_verified",
    "implementation_bundles", "formal_product_mapping_enabled",
    "formal_source_policy_enabled", "route_mapping_frozen",
    "external_ndc_mapping_executed",
}
RUNNER_LIMITATIONS = (
    "This preflight only enumerates five exact typed local fields and their "
    "frequencies. It does not map routes, normalize NDCs, call external "
    "services, identify products, link events, accept a source policy, or "
    "construct actions, episodes, labels, or a cohort."
)
FORBIDDEN_PUBLIC_KEYS = {
    "raw_value", "raw_value_base64", "records", "snapshot_token",
    "per_value_hash", "subject_id", "hadm_id", "stay_id", "emar_id",
    "emar_seq", "pharmacy_id", "poe_id", "charttime", "storetime",
    "scheduletime", "starttime", "stoptime", "ordertime",
}


class AuditContractError(RuntimeError):
    """A fail-closed audit error whose message contains no private value."""


class Checks:
    def __init__(self) -> None:
        self.total = 0
        self.by_category: Counter[str] = Counter()
        self.failed: list[str] = []

    def require(self, condition: bool, name: str) -> None:
        self.total += 1
        category = name.split(".", 1)[0]
        self.by_category[category] += 1
        if not condition:
            if name not in self.failed:
                self.failed.append(name)
            raise AuditContractError(name)

    def check(self, condition: bool, name: str) -> None:
        self.total += 1
        category = name.split(".", 1)[0]
        self.by_category[category] += 1
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


def _runtime_contract() -> dict[str, str]:
    return {
        "python_version": ".".join(str(item) for item in sys.version_info[:3]),
        "unicodedata_version": unicodedata.unidata_version,
    }


def _read_unique_json(path: Path, byte_limit: int, label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink():
        raise AuditContractError(label + ".regular_file")
    size = path.stat().st_size
    if not 0 < size <= byte_limit:
        raise AuditContractError(label + ".byte_limit")
    raw = path.read_bytes()

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AuditContractError(label + ".duplicate_json_key")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except AuditContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditContractError(label + ".valid_json") from exc
    if not isinstance(value, dict):
        raise AuditContractError(label + ".object")
    return value, raw


def _safe_file(directory: Path, filename: Any, label: str) -> Path:
    if (
        not isinstance(filename, str)
        or not filename
        or Path(filename).name != filename
        or filename in {".", ".."}
    ):
        raise AuditContractError(label + ".safe_filename")
    path = directory / filename
    if not path.is_file() or path.is_symlink():
        raise AuditContractError(label + ".regular_file")
    return path


def _safe_relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise AuditContractError(label + ".string")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value:
        raise AuditContractError(label + ".safe_relative")
    return value


def _implementation_bundle(root: Path, paths: tuple[str, ...]) -> dict[str, Any]:
    """Independently hash an ordered path/content bundle."""
    digest = hashlib.sha256()
    files: list[dict[str, Any]] = []
    for index, relative_text in enumerate(paths):
        _safe_relative_path(relative_text, f"bundle.path_{index}")
        path = root / relative_text
        if not path.is_file() or path.is_symlink():
            raise AuditContractError(f"bundle.path_{index}.regular_file")
        path_bytes = relative_text.encode("utf-8")
        content = path.read_bytes()
        if len(path_bytes) > 0xFFFFFFFF or len(content) > 0xFFFFFFFFFFFFFFFF:
            raise AuditContractError(f"bundle.path_{index}.byte_limit")
        digest.update(len(path_bytes).to_bytes(4, "big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        files.append({
            "path": relative_text,
            "bytes": len(content),
            "file_sha256": _sha_bytes(content),
        })
    return {
        "paths": list(paths),
        "bundle_sha256": digest.hexdigest(),
        "files": files,
        "encoding": "uint32be_path_length+path_utf8+uint64be_content_length+content",
    }


def _all_bundles(root: Path) -> dict[str, dict[str, Any]]:
    return {name: _implementation_bundle(root, paths) for name, paths in BUNDLE_PATHS.items()}


def _typed_set_sha256(source_field: str, records: list[Mapping[str, Any]]) -> str:
    """Recompute the registered hash without using runner code."""
    try:
        field_bytes = source_field.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise AuditContractError("content.source_field.utf8") from exc
    if len(field_bytes) > 0xFFFFFFFF:
        raise AuditContractError("content.source_field.byte_limit")
    null_seen = False
    values: list[bytes] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise AuditContractError("content.record.mapping")
        is_null = record.get("raw_is_null")
        raw = record.get("raw_value")
        count = record.get("exact_row_count")
        if type(count) is not int or not 1 <= count <= MAX_EXACT_ROW_COUNT:
            raise AuditContractError("content.record.positive_frequency")
        if is_null is True and raw is None:
            if null_seen:
                raise AuditContractError("content.record.single_null")
            null_seen = True
        elif is_null is False and isinstance(raw, str):
            try:
                raw_bytes = raw.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise AuditContractError("content.record.utf8") from exc
            if b"\x00" in raw_bytes or len(raw_bytes) > MAX_VALUE_UTF8_BYTES:
                raise AuditContractError("content.record.byte_contract")
            values.append(raw_bytes)
        else:
            raise AuditContractError("content.record.typed_state")
    if len(values) != len(set(values)):
        raise AuditContractError("content.record.unique_nonnull")
    values.sort()
    record_count = len(values) + int(null_seen)
    digest = hashlib.sha256()
    digest.update(HASH_VERSION)
    digest.update(len(field_bytes).to_bytes(4, "big"))
    digest.update(field_bytes)
    digest.update(record_count.to_bytes(8, "big"))
    if null_seen:
        digest.update(b"\x00")
    for raw_bytes in values:
        digest.update(b"\x01")
        digest.update(len(raw_bytes).to_bytes(8, "big"))
        digest.update(raw_bytes)
    return digest.hexdigest()


def _nonnull_substate(raw: str) -> str:
    if raw == "":
        return "empty_string"
    if raw.isspace():
        return "whitespace_only"
    return "nonblank"


def _audit_config(
    root: Path,
    manifest: Mapping[str, Any],
    bundles: Mapping[str, Mapping[str, Any]],
    checks: Checks,
) -> tuple[dict[str, Any], str]:
    path = root / CONFIG_PATH
    checks.require(path.is_file() and not path.is_symlink(), "config.regular_file")
    raw = path.read_bytes()
    try:
        config = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise AuditContractError("config.valid_toml") from exc
    config_sha = _sha_bytes(raw)
    checks.require(
        config.get("component_id") == "D005-K-MAPPING-PREFLIGHT-v1"
        and config.get("status") == "proposed"
        and config.get("formal_mapping_enabled") is False
        and config.get("formal_source_policy_enabled") is False,
        "config.proposed_neutral_component",
    )
    execution = config.get("execution")
    checks.require(
        isinstance(execution, dict)
        and execution.get("status") == "not_executed"
        and execution.get("transaction_isolation") == "repeatable read"
        and execution.get("transaction_read_only") is True
        and execution.get("statement_timeout_ms") == STATEMENT_TIMEOUT_MS
        and execution.get("all_five_sql_statements_share_one_snapshot") is True
        and execution.get("explicit_rollback_required") is True
        and execution.get("clean_psql_exit_required") is True
        and execution.get("database_mutation_allowed") is False
        and execution.get("temporary_database_objects_allowed") is False,
        "config.execution_contract",
    )
    universe = config.get("discovery_universe")
    checks.require(
        isinstance(universe, dict)
        and universe.get("source_fields") == [source.field for source in SOURCES]
        and universe.get("route_fields") == [source.field for source in SOURCES[:3]]
        and universe.get("sampling") is False
        and universe.get("lexical_filtering") is False
        and universe.get("product_filtering") is False
        and universe.get("event_link_filtering") is False
        and universe.get("normalization_establishes_identity") is False
        and universe.get("ndc_syntax_normalization_in_preflight") is False,
        "config.exact_unfiltered_five_field_universe",
    )
    implementation = config.get("implementation_hashes")
    checks.require(isinstance(implementation, dict), "config.implementation_hashes")
    checks.require(
        implementation.get("sql_paths") == list(SQL_PATHS)
        and implementation.get("runner_paths") == list(RUNNER_PATHS)
        and implementation.get("offline_auditor_paths") == list(AUDITOR_PATHS),
        "config.implementation_paths_exact_order",
    )
    checks.require(
        implementation.get("bundle_hash_encoding")
        == "for each configured path in order: uint32 big-endian path UTF-8 byte length, path UTF-8 bytes, uint64 big-endian content length, exact file bytes",
        "config.bundle_encoding",
    )
    for name, observed in bundles.items():
        expected = implementation.get(BUNDLE_DIGEST_KEYS[name])
        checks.require(
            isinstance(expected, str)
            and SHA256_RE.fullmatch(expected) is not None
            and expected == observed["bundle_sha256"],
            f"config.{name}_bundle_hash",
        )
    guards = config.get("guards")
    checks.require(
        isinstance(guards, dict) and bool(guards)
        and all(value is False for value in guards.values()),
        "config.all_formal_guards_false",
    )
    component = manifest.get("component_preregistration")
    checks.require(
        isinstance(component, dict) and set(component) == MANIFEST_COMPONENT_KEYS,
        "config.manifest_component",
    )
    checks.require(
        component.get("component_id") == config["component_id"]
        and component.get("status_at_start") == "proposed"
        and component.get("execution_status_at_start") == "not_executed"
        and component.get("config") == str(CONFIG_PATH)
        and component.get("config_sha256") == config_sha
        and component.get("implementation_hashes_verified") is True,
        "config.manifest_lineage",
    )
    for key in (
        "formal_product_mapping_enabled", "formal_source_policy_enabled",
        "route_mapping_frozen", "external_ndc_mapping_executed",
    ):
        checks.require(component.get(key) is False, f"config.manifest_{key}_false")
    return config, config_sha


def _audit_manifest_bundles(
    manifest: Mapping[str, Any],
    bundles: Mapping[str, Mapping[str, Any]],
    checks: Checks,
) -> None:
    observed_top = manifest.get("implementation_bundles")
    checks.require(
        isinstance(observed_top, dict) and set(observed_top) == set(BUNDLE_PATHS),
        "bundle.manifest_exact_set",
    )
    component = manifest.get("component_preregistration")
    registered = component.get("implementation_bundles") if isinstance(component, dict) else None
    checks.require(
        isinstance(registered, dict) and set(registered) == set(BUNDLE_PATHS),
        "bundle.component_exact_set",
    )
    for name, expected in bundles.items():
        checks.require(observed_top.get(name) == expected, f"bundle.{name}_manifest_exact")
        registered_item = registered.get(name)
        expected_registered_files = [
            {"path": item["path"], "file_sha256": item["file_sha256"]}
            for item in expected["files"]
        ]
        checks.require(
            isinstance(registered_item, dict)
            and registered_item.get("paths") == expected["paths"]
            and registered_item.get("expected_sha256") == expected["bundle_sha256"]
            and registered_item.get("actual_sha256") == expected["bundle_sha256"]
            and registered_item.get("missing") in (None, [])
            and registered_item.get("files") in (expected_registered_files, expected["files"]),
            f"bundle.{name}_component_exact",
        )


def _audit_public_payload(
    payload: Mapping[str, Any],
    private_values: set[str],
    label: str,
    checks: Checks,
) -> None:
    strings: list[str] = []
    forbidden_seen = False

    def walk(value: Any) -> None:
        nonlocal forbidden_seen
        if isinstance(value, Mapping):
            for key, item in value.items():
                key_text = str(key)
                if key_text.casefold() in FORBIDDEN_PUBLIC_KEYS:
                    forbidden_seen = True
                strings.append(key_text)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            strings.append(value)

    walk(payload)
    checks.require(not forbidden_seen, label + ".forbidden_private_keys_absent")
    # Low-entropy route strings can legitimately equal fixed public schema words
    # (for example, "complete").  Exact public schemas below rule out additional
    # value-bearing fields; literal matching is reserved for sufficiently long
    # values where a match is evidence of disclosure rather than coincidence.
    long_values = [value for value in private_values if len(value) >= 12]
    checks.require(
        not (set(strings) & set(long_values)),
        label + ".exact_private_values_absent",
    )
    checks.require(
        not any(value in public for value in long_values for public in strings),
        label + ".embedded_private_values_absent",
    )


def _audit_private_and_summary(
    private: Mapping[str, Any],
    summary: Mapping[str, Any],
    *,
    config_sha: str,
    checks: Checks,
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    checks.require(set(private) == PRIVATE_TOP_KEYS, "content.private_exact_schema")
    checks.require(set(summary) == SUMMARY_TOP_KEYS, "content.summary_exact_schema")
    checks.require(
        private.get("schema_version") == 1 and private.get("query") == QUERY_NAME
        and summary.get("schema_version") == 1 and summary.get("query") == QUERY_NAME
        and summary.get("scope") == "exact_five_field_typed_vocabulary_preflight",
        "content.top_contract",
    )
    expected_lineage = {
        "component_id": "D005-K-MAPPING-PREFLIGHT-v1",
        "status_at_execution": "proposed",
        "config": str(CONFIG_PATH),
        "config_sha256": config_sha,
    }
    checks.require(private.get("component_lineage") == expected_lineage, "content.private_lineage")
    checks.require(summary.get("component_lineage") == expected_lineage, "content.summary_lineage")
    expected_runtime = _runtime_contract()
    checks.require(
        private.get("nonnull_substate_classification_runtime") == expected_runtime
        and summary.get("nonnull_substate_classification_runtime") == expected_runtime,
        "runtime.python_and_unicode_exact",
    )
    checks.require(
        private.get("typed_set_hash_contract") == {
            "algorithm": "sha256",
            "version": HASH_VERSION.decode("ascii"),
            "frequencies_included": False,
            "source_field_included": True,
            "null_token": "00",
            "nonnull_token": "01",
            "integer_encoding": "unsigned_big_endian",
        },
        "content.typed_hash_contract",
    )
    expected_transaction = {
        "isolation": "repeatable read", "read_only": True, "same_snapshot": True,
        "snapshot_token_sha256": private.get("transaction", {}).get("snapshot_token_sha256")
        if isinstance(private.get("transaction"), dict) else None,
        "rollback_confirmed_before_persistence": True,
        "clean_psql_exit_confirmed_before_persistence": True,
    }
    snapshot_hash = expected_transaction["snapshot_token_sha256"]
    checks.require(
        isinstance(snapshot_hash, str) and SHA256_RE.fullmatch(snapshot_hash) is not None
        and private.get("transaction") == expected_transaction
        and summary.get("transaction_controls") == expected_transaction,
        "snapshot.private_summary_controls",
    )
    checks.require(
        private.get("raw_values_are_exact_and_unnormalized") is True
        and private.get("contains_patient_or_event_identifiers") is False
        and private.get("contains_event_timestamps") is False
        and private.get("route_mapping_created") is False
        and private.get("external_api_called") is False
        and private.get("product_identity_decided") is False
        and private.get("final_source_policy") is False,
        "content.private_boundaries",
    )
    private_sources = private.get("sources")
    summary_sources = summary.get("source_summaries")
    checks.require(
        isinstance(private_sources, dict) and set(private_sources) == set(SOURCE_BY_KEY)
        and isinstance(summary_sources, dict) and set(summary_sources) == set(SOURCE_BY_KEY),
        "content.exact_five_sources",
    )
    source_results: dict[str, dict[str, Any]] = {}
    private_values: set[str] = set()
    grand_rows = 0
    grand_distinct = 0
    for spec in SOURCES:
        source = private_sources[spec.key]
        public = summary_sources[spec.key]
        checks.require(
            isinstance(source, dict) and set(source) == PRIVATE_SOURCE_KEYS
            and isinstance(public, dict) and set(public) == SUMMARY_SOURCE_KEYS,
            f"content.{spec.key}.exact_schema",
        )
        records = source.get("records")
        checks.require(isinstance(records, list), f"content.{spec.key}.records_list")
        null_count = 0
        nonnull_count = 0
        typed_rows = {"sql_null": 0, "nonnull": 0}
        typed_distinct = {"sql_null": 0, "nonnull": 0}
        substate_rows = {"empty_string": 0, "whitespace_only": 0, "nonblank": 0}
        substate_distinct = {"empty_string": 0, "whitespace_only": 0, "nonblank": 0}
        identities: set[tuple[bool, str | None]] = set()
        observed_order: list[tuple[int, bytes]] = []
        for index, record in enumerate(records):
            checks.require(
                isinstance(record, dict) and set(record) == PRIVATE_RECORD_KEYS,
                f"content.{spec.key}.record_{index}.exact_schema",
            )
            is_null = record.get("raw_is_null")
            raw = record.get("raw_value")
            count = record.get("exact_row_count")
            byte_count = record.get("raw_utf8_bytes")
            substate = record.get("nonnull_substate")
            checks.require(
                type(count) is int and 1 <= count <= MAX_EXACT_ROW_COUNT,
                f"content.{spec.key}.record_{index}.positive_frequency",
            )
            if is_null is True:
                checks.require(
                    raw is None and byte_count == 0 and substate is None,
                    f"content.{spec.key}.record_{index}.null_contract",
                )
                null_count += 1
                state = "sql_null"
                observed_order.append((0, b""))
            elif is_null is False and isinstance(raw, str):
                try:
                    encoded = raw.encode("utf-8")
                except UnicodeEncodeError as exc:
                    raise AuditContractError(
                        f"content.{spec.key}.record_{index}.utf8"
                    ) from exc
                checks.require(
                    len(encoded) <= MAX_VALUE_UTF8_BYTES and b"\x00" not in encoded
                    and byte_count == len(encoded)
                    and substate == _nonnull_substate(raw),
                    f"content.{spec.key}.record_{index}.raw_and_substate_recomputed",
                )
                nonnull_count += 1
                state = "nonnull"
                substate_rows[substate] += count
                substate_distinct[substate] += 1
                observed_order.append((1, encoded))
                private_values.add(raw)
            else:
                raise AuditContractError(f"content.{spec.key}.record_{index}.typed_state")
            identity = (is_null, raw)
            checks.require(
                identity not in identities,
                f"content.{spec.key}.record_{index}.typed_value_unique",
            )
            identities.add(identity)
            typed_rows[state] += count
            typed_distinct[state] += 1
        checks.require(null_count <= 1, f"content.{spec.key}.single_null")
        checks.require(
            observed_order == sorted(observed_order),
            f"content.{spec.key}.canonical_record_order",
        )
        typed_hash = _typed_set_sha256(spec.field, records)
        source_rows = sum(typed_rows.values())
        checks.require(source_rows <= MAX_EXACT_ROW_COUNT, f"content.{spec.key}.row_limit")
        checks.require(
            source.get("source_field") == spec.field
            and source.get("field_role") == spec.role
            and source.get("sql_null_rows") == typed_rows["sql_null"]
            and source.get("sql_null_present") is (typed_rows["sql_null"] > 0)
            and source.get("typed_distinct_values") == len(records)
            and source.get("nonnull_distinct_values") == nonnull_count
            and source.get("typed_set_sha256") == typed_hash,
            f"content.{spec.key}.private_counts_and_hash",
        )
        expected_public = {
            "source_field": spec.field,
            "field_role": spec.role,
            "source_rows": source_rows,
            "typed_distinct_values": len(records),
            "typed_state_row_counts": typed_rows,
            "typed_state_distinct_counts": typed_distinct,
            "nonnull_substate_row_counts": substate_rows,
            "nonnull_substate_distinct_counts": substate_distinct,
            "typed_set_sha256": typed_hash,
            "row_conservation_confirmed": True,
            "distinct_conservation_confirmed": True,
        }
        checks.require(public == expected_public, f"content.{spec.key}.summary_recomputed")
        checks.require(
            sum(substate_rows.values()) == typed_rows["nonnull"]
            and sum(substate_distinct.values()) == typed_distinct["nonnull"],
            f"content.{spec.key}.nonnull_substate_conservation",
        )
        source_results[spec.key] = {
            "source_rows": source_rows,
            "typed_distinct_values": len(records),
            "typed_set_sha256": typed_hash,
        }
        grand_rows += source_rows
        grand_distinct += len(records)
    checks.require(
        summary.get("global_counts") == {
            "source_fields": 5,
            "route_fields": 3,
            "source_rows_across_fields": grand_rows,
            "typed_distinct_source_value_memberships": grand_distinct,
        },
        "content.global_conservation",
    )
    checks.require(
        summary.get("privacy") == {
            "raw_values_emitted": False,
            "local_ndc_values_emitted": False,
            "per_value_hashes_emitted": False,
            "patient_or_event_data_emitted": False,
        },
        "privacy.summary_guards",
    )
    guards = summary.get("boundary_guards")
    checks.require(
        isinstance(guards, dict) and set(guards) == set(BOUNDARY_GUARDS)
        and all(guards[key] is False for key in BOUNDARY_GUARDS),
        "content.all_summary_guards_false",
    )
    return source_results, private_values


def _template_body(raw: bytes, label: str) -> str:
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise AuditContractError(label + ".utf8") from exc
    if not text.endswith(";") or text[:-1].rstrip().endswith(";"):
        raise AuditContractError(label + ".single_trailing_terminator")
    return text[:-1].rstrip()


def _visible_sql(text: str, label: str) -> str:
    """Mask comments and quoted strings for a conservative read-only scan."""
    visible = list(text)
    index = 0
    while index < len(text):
        start = index
        if text.startswith("--", index):
            end = text.find("\n", index + 2)
            index = len(text) if end == -1 else end
        elif text.startswith("/*", index):
            depth = 1
            index += 2
            while index < len(text) and depth:
                if text.startswith("/*", index):
                    depth += 1
                    index += 2
                elif text.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise AuditContractError(label + ".closed_comment")
        elif text[index] in {"'", '"'}:
            quote = text[index]
            index += 1
            closed = False
            while index < len(text):
                if text[index] == quote:
                    if index + 1 < len(text) and text[index + 1] == quote:
                        index += 2
                    else:
                        index += 1
                        closed = True
                        break
                elif quote == "'" and text[index] == "\\":
                    index += 2
                else:
                    index += 1
            if not closed:
                raise AuditContractError(label + ".closed_quote")
        else:
            index += 1
            continue
        for position in range(start, min(index, len(visible))):
            if visible[position] != "\n":
                visible[position] = " "
    return "".join(visible)


def _audit_sql_template(root: Path, spec: SourceSpec, checks: Checks) -> bytes:
    path = root / spec.sql_file
    checks.require(path.is_file() and not path.is_symlink(), f"sql.{spec.key}.regular_file")
    raw = path.read_bytes()
    body = _template_body(raw, f"sql.{spec.key}")
    visible = _visible_sql(body, f"sql.{spec.key}")
    upper = visible.upper()
    forbidden = re.compile(
        r"\b(?:INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|COPY|CALL|DO|GRANT|REVOKE|VACUUM|ANALYZE|REFRESH|LOCK|LIMIT|TABLESAMPLE)\b"
    )
    checks.require(forbidden.search(upper) is None, f"sql.{spec.key}.read_only_unfiltered")
    checks.require(
        upper.lstrip().startswith("WITH ")
        and "COUNT(*)::BIGINT AS EXACT_ROW_COUNT" in upper
        and "GROUP BY" in upper
        and "PG_CURRENT_SNAPSHOT()" in upper
        and upper.count(";") == 0,
        f"sql.{spec.key}.complete_grouped_single_select",
    )
    table, column = spec.field.rsplit(".", 1)
    checks.require(
        re.search(r"\bFROM\s+" + re.escape(table.upper()) + r"\b", upper) is not None
        and re.search(
            r"\bCONVERT_TO\s*\(\s*" + re.escape(column.upper())
            + r"::TEXT\s*,\s*\s+\)\s+AS\s+RAW_BYTES\b",
            upper,
        ) is not None,
        f"sql.{spec.key}.exact_source_field",
    )
    checks.require(
        "SELECT true, ''::text, 0::bigint" in body
        and "raw_bytes IS NULL" in body
        and "encode(raw_bytes, 'base64')" in body,
        f"sql.{spec.key}.typed_null_and_lossless_utf8",
    )
    return raw


def _audit_executed_sql(
    root: Path,
    raw: bytes,
    stages: Mapping[str, Any],
    checks: Checks,
) -> None:
    if len(raw) > MAX_SQL_BYTES:
        raise AuditContractError("sql.executed.byte_limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuditContractError("sql.executed.utf8") from exc
    position = 0
    preamble = (
        "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
        "SET LOCAL lock_timeout = '2000ms';\n"
        "SET LOCAL standard_conforming_strings = on;\n"
        "SET LOCAL work_mem = '128MB';\n"
        "SET LOCAL jit = off;\n"
    )
    for index, spec in enumerate(SOURCES):
        template = _audit_sql_template(root, spec, checks)
        marker_re = re.compile(
            r"\\echo (__APRIL_MAPPING_PREFLIGHT_" + re.escape(spec.key.upper())
            + r"_" + MARKER_HEX + r"__)\n"
        )
        match = marker_re.search(text, position)
        checks.require(match is not None, f"sql.{spec.key}.marker")
        chunk = text[position:match.end()]
        expected = (
            (preamble if index == 0 else "")
            + "SET LOCAL statement_timeout = '120000ms';\n"
            + _template_body(template, f"sql.{spec.key}")
            + ";\n\\echo " + match.group(1) + "\n"
        )
        checks.require(chunk == expected, f"sql.{spec.key}.exact_executed_control")
        stage = stages.get(spec.key)
        checks.require(isinstance(stage, dict), f"sql.{spec.key}.stage")
        encoded = chunk.encode("utf-8")
        checks.require(
            stage.get("control_sha256") == _sha_bytes(encoded)
            and stage.get("control_bytes") == len(encoded),
            f"sql.{spec.key}.control_hash_and_bytes",
        )
        position = match.end()
    checks.require(
        re.fullmatch(
            r"ROLLBACK;\n\\echo __APRIL_MAPPING_PREFLIGHT_ROLLBACK_"
            + MARKER_HEX + r"__\n\\q\n",
            text[position:],
        ) is not None,
        "sql.explicit_rollback_and_clean_quit",
    )


def _audit_manifest_and_files(
    root: Path,
    directory: Path,
    manifest: Mapping[str, Any],
    private_raw: bytes,
    summary_raw: bytes,
    executed_raw: bytes,
    source_results: Mapping[str, Mapping[str, Any]],
    bundles: Mapping[str, Mapping[str, Any]],
    checks: Checks,
) -> None:
    checks.require(set(manifest) == MANIFEST_KEYS, "manifest.exact_schema")
    checks.require(
        manifest.get("schema_version") == 1
        and manifest.get("status") == "complete"
        and manifest.get("scope") == "exact_five_field_typed_vocabulary_preflight"
        and manifest.get("selected_queries") == [QUERY_NAME],
        "manifest.complete_contract",
    )
    checks.require(
        manifest.get("requested_controls") == {
            "read_only": True, "same_snapshot": True,
            "transaction_isolation": "repeatable read",
            "statement_timeout_ms_per_stage": STATEMENT_TIMEOUT_MS,
            "explicit_rollback": True,
            "clean_psql_exit_before_value_persistence": True,
            "external_api_calls": False,
        },
        "manifest.requested_controls",
    )
    checks.require(
        manifest.get("confirmed_controls") == {
            "read_only": True, "same_snapshot": True,
            "transaction_isolation": "repeatable read", "rollback": True,
            "clean_psql_exit": True, "external_api_calls": False,
        },
        "manifest.confirmed_controls",
    )
    checks.require(
        manifest.get("limitations") == RUNNER_LIMITATIONS,
        "manifest.fixed_aggregate_only_limitations",
    )
    checks.require(
        manifest.get("nonnull_substate_classification_runtime") == _runtime_contract(),
        "runtime.manifest_python_and_unicode_exact",
    )
    queries = manifest.get("queries")
    checks.require(
        isinstance(queries, list) and len(queries) == 1 and isinstance(queries[0], dict),
        "manifest.single_query",
    )
    entry = queries[0]
    checks.require(set(entry) == MANIFEST_ENTRY_KEYS, "manifest.query_exact_schema")
    checks.require(
        entry.get("query") == QUERY_NAME and entry.get("status") == "complete"
        and entry.get("psql_returncode") == 0
        and entry.get("private_values_persisted") is True
        and entry.get("executed_sql_persisted") is True
        and entry.get("aggregate_summary_persisted") is True,
        "manifest.query_complete_clean_exit",
    )
    checks.require(entry.get("source_counts") == dict(source_results), "manifest.source_counts")
    checks.require(
        entry.get("private_values_sha256") == _sha_bytes(private_raw)
        and entry.get("private_values_bytes") == len(private_raw)
        and entry.get("aggregate_summary_sha256") == _sha_bytes(summary_raw)
        and entry.get("aggregate_summary_bytes") == len(summary_raw)
        and entry.get("executed_sql_sha256") == _sha_bytes(executed_raw)
        and entry.get("executed_sql_bytes") == len(executed_raw),
        "manifest.artifact_hashes_and_bytes",
    )
    stages = entry.get("stages")
    checks.require(
        isinstance(stages, dict) and set(stages) == set(SOURCE_BY_KEY),
        "manifest.exact_five_stages",
    )
    snapshot_hash = entry.get("snapshot_token_sha256")
    checks.require(
        isinstance(snapshot_hash, str) and SHA256_RE.fullmatch(snapshot_hash) is not None,
        "snapshot.manifest_hash",
    )
    frame_bytes = 0
    control_bytes = 0
    for spec in SOURCES:
        stage = stages[spec.key]
        source = source_results[spec.key]
        sql_path = root / spec.sql_file
        elapsed = stage.get("elapsed_seconds")
        checks.require(
            isinstance(stage, dict) and set(stage) == MANIFEST_STAGE_KEYS,
            f"manifest.{spec.key}.exact_schema",
        )
        checks.require(
            stage.get("source_key") == spec.key
            and stage.get("source_field") == spec.field
            and stage.get("field_role") == spec.role
            and stage.get("file") == spec.sql_file
            and stage.get("status") == "complete"
            and stage.get("rows") == source["typed_distinct_values"]
            and stage.get("source_rows") == source["source_rows"]
            and stage.get("typed_distinct_values") == source["typed_distinct_values"]
            and stage.get("typed_set_sha256") == source["typed_set_sha256"],
            f"manifest.{spec.key}.source_contract",
        )
        checks.require(
            stage.get("statement_timeout_ms") == STATEMENT_TIMEOUT_MS
            and stage.get("process_timeout_seconds") == PROCESS_TIMEOUT_SECONDS
            and stage.get("observed_transaction_isolation") == "repeatable read"
            and stage.get("observed_transaction_read_only") == "on"
            and stage.get("observed_snapshot_sha256") == snapshot_hash
            and type(elapsed) in {int, float} and 0 <= elapsed <= PROCESS_TIMEOUT_SECONDS,
            f"manifest.{spec.key}.read_only_snapshot_timeout",
        )
        checks.require(
            stage.get("template_sha256") == _sha_file(sql_path)
            and stage.get("template_bytes") == sql_path.stat().st_size,
            f"manifest.{spec.key}.template_hash_and_bytes",
        )
        checks.require(
            "frame_sha256" not in stage
            and type(stage.get("frame_bytes")) is int and stage["frame_bytes"] > 0,
            f"manifest.{spec.key}.frame_metadata",
        )
        frame_bytes += stage["frame_bytes"]
        control_bytes += stage.get("control_bytes", -MAX_SQL_BYTES)
    checks.require(
        entry.get("cumulative_frame_bytes") == frame_bytes
        and entry.get("cumulative_control_bytes") == control_bytes,
        "manifest.cumulative_bytes",
    )
    checks.require(
        manifest.get("sql_bundle_sha256") == bundles["sql"]["bundle_sha256"],
        "bundle.manifest_sql_alias",
    )
    _audit_executed_sql(root, executed_raw, stages, checks)
    modes = manifest.get("artifact_modes")
    expected_value_modes = {
        entry.get("private_values_file"): "0600",
        entry.get("executed_sql_file"): "0600",
        entry.get("aggregate_summary_file"): "0600",
    }
    checks.require(
        None not in expected_value_modes
        and modes == {
            "directory": "0700", "manifest": "0600", "stderr": "0600",
            "value_files": expected_value_modes,
        },
        "files.declared_modes",
    )
    checks.require(_mode(directory) == "0700", "files.directory_mode_0700")
    for filename in expected_value_modes:
        checks.require(
            _mode(_safe_file(directory, filename, "files.value")) == "0600",
            "files.value_mode_0600",
        )
    manifest_path = _safe_file(directory, "manifest.json", "files.manifest")
    checks.require(_mode(manifest_path) == "0600", "files.manifest_mode_0600")
    stderr_path = _safe_file(directory, entry.get("stderr_file"), "files.stderr")
    checks.require(
        _mode(stderr_path) == "0600" and stderr_path.read_bytes() == b""
        and entry.get("stderr_bytes") == 0
        and entry.get("stderr_sha256") == _sha_bytes(b""),
        "files.stderr_empty_private",
    )
    try:
        relative = directory.relative_to(root)
    except ValueError as exc:
        raise AuditContractError("files.directory_inside_project") from exc
    ignore_path = root / ".gitignore"
    checks.require(
        relative.parts[:2] == ("artifacts", "profiling")
        and ignore_path.is_file()
        and "artifacts/*" in ignore_path.read_text(encoding="utf-8").splitlines(),
        "files.git_ignored_artifact_tree",
    )


def _write_audit(path: Path, result: Mapping[str, Any]) -> None:
    payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.unlink(missing_ok=True)
    descriptor: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def audit_artifact(directory: Path, root: Path) -> tuple[dict[str, Any], Path]:
    """Audit a persisted preflight without connecting to PostgreSQL."""
    directory = directory.resolve()
    root = root.resolve()
    checks = Checks()
    integrity: dict[str, Any] = {}
    source_results: dict[str, dict[str, Any]] = {}
    private_values: set[str] = set()
    config_digest: str | None = None
    try:
        checks.require(directory.is_dir() and not directory.is_symlink(), "files.directory")
        checks.require(_mode(directory) == "0700", "files.directory_private")
        manifest, manifest_raw = _read_unique_json(
            _safe_file(directory, "manifest.json", "manifest"),
            8 * 1024 * 1024,
            "manifest",
        )
        queries = manifest.get("queries")
        checks.require(
            isinstance(queries, list) and len(queries) == 1 and isinstance(queries[0], dict),
            "manifest.query_entry",
        )
        entry = queries[0]
        private_path = _safe_file(directory, entry.get("private_values_file"), "private")
        summary_path = _safe_file(directory, entry.get("aggregate_summary_file"), "summary")
        executed_path = _safe_file(directory, entry.get("executed_sql_file"), "executed_sql")
        private, private_raw = _read_unique_json(private_path, MAX_JSON_BYTES, "private")
        summary, summary_raw = _read_unique_json(summary_path, 8 * 1024 * 1024, "summary")
        executed_raw = executed_path.read_bytes()
        checks.require(len(executed_raw) <= MAX_SQL_BYTES, "sql.executed_size")
        bundles = _all_bundles(root)
        _config, config_sha = _audit_config(root, manifest, bundles, checks)
        config_digest = config_sha
        _audit_manifest_bundles(manifest, bundles, checks)
        source_results, private_values = _audit_private_and_summary(
            private, summary, config_sha=config_sha, checks=checks
        )
        checks.require(
            summary.get("private_artifact_hashes") == {
                "private_values_sha256": _sha_bytes(private_raw),
                "executed_sql_sha256": _sha_bytes(executed_raw),
            },
            "content.summary_private_artifact_hashes",
        )
        private_snapshot = private["transaction"]["snapshot_token_sha256"]
        checks.require(
            entry.get("snapshot_token_sha256") == private_snapshot,
            "snapshot.manifest_private_match",
        )
        _audit_public_payload(summary, private_values, "privacy.summary", checks)
        _audit_public_payload(manifest, private_values, "privacy.manifest", checks)
        _audit_manifest_and_files(
            root, directory, manifest, private_raw, summary_raw, executed_raw,
            source_results, bundles, checks,
        )
        integrity = {
            "manifest_sha256": _sha_bytes(manifest_raw),
            "private_values_sha256": _sha_bytes(private_raw),
            "aggregate_summary_sha256": _sha_bytes(summary_raw),
            "executed_sql_sha256": _sha_bytes(executed_raw),
            "directory_mode": _mode(directory),
            "private_file_mode": "0600",
            "config_sha256": config_digest,
            "implementation_bundle_sha256": {
                name: bundle["bundle_sha256"] for name, bundle in bundles.items()
            },
        }
    except AuditContractError as exc:
        if str(exc) not in checks.failed:
            checks.check(False, str(exc))
    except Exception:
        checks.check(False, "audit.internal_failure")

    result: dict[str, Any] = {
        "schema_version": 1,
        "audit": AUDIT_NAME,
        "status": "passed" if not checks.failed else "failed",
        "input_integrity": integrity,
        "execution_contract": {
            "database_connection_used": False,
            "five_stages_required": True,
            "same_snapshot_required": True,
            "read_only_repeatable_read_required": True,
            "statement_timeout_ms_per_stage": STATEMENT_TIMEOUT_MS,
            "rollback_and_clean_exit_required": True,
        },
        "content_contract": {
            "source_fields_checked": len(source_results),
            "source_rows_checked": sum(
                item["source_rows"] for item in source_results.values()
            ),
            "typed_distinct_source_value_memberships_checked": sum(
                item["typed_distinct_values"] for item in source_results.values()
            ),
            "runtime_whitespace_classification_recomputed": not checks.failed,
            "typed_set_hashes_recomputed": not checks.failed,
            "row_and_distinct_conservation_recomputed": not checks.failed,
        },
        "privacy": {
            "raw_values_emitted": False,
            "local_ndc_values_emitted": False,
            "patient_or_event_data_emitted": False,
            "per_value_hashes_emitted": False,
        },
        "formal_guards": {key: False for key in BOUNDARY_GUARDS},
        "audit_checks": {
            "total": checks.total,
            "passed": checks.total - len(checks.failed),
            "failed": checks.failed,
            "by_category": dict(sorted(checks.by_category.items())),
        },
        "limitations": (
            "This offline audit verifies the saved five-field discovery boundary. "
            "It does not adjudicate route semantics, normalize or query NDCs, "
            "identify products, link events, accept a source policy, or construct "
            "actions, episodes, labels, or a cohort."
        ),
    }
    if private_values:
        secondary = Checks()
        try:
            _audit_public_payload(result, private_values, "privacy.audit_summary", secondary)
        except AuditContractError:
            result["status"] = "failed"
            result["audit_checks"]["total"] += secondary.total
            result["audit_checks"]["failed"].append("privacy.audit_summary.value_free")
            result["audit_checks"]["passed"] = (
                result["audit_checks"]["total"] - len(result["audit_checks"]["failed"])
            )
    output = directory / "audit-summary.json"
    _write_audit(output, result)
    return result, output
