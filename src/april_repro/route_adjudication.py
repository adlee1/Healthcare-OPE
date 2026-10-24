"""Private exact-value route review and source-specific mapping compilation.

This module never connects to a database and never classifies route text.  It
builds a private human-review template from the audited mapping-preflight raw
artifact, then expands reviewed canonical exact values back to source-specific
keys.  Unreviewed values remain ``unknown`` and no output unlocks Query 202.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import tomllib
from typing import Any, Mapping, Sequence


CONFIG_PATH = Path("config/preregistrations/d005_potassium_route_adjudication.toml")
COMPONENT_ID = "D005-K-ROUTE-ADJUDICATION-v2"
TYPED_SET_HASH_VERSION = b"typed-distinct-source-value-set-v1"
CANONICAL_SET_HASH_VERSION = b"canonical-exact-nonnull-route-value-set-v1"
MAPPING_HASH_VERSION = b"source-specific-exact-route-mapping-v2"
DECISION_CODE = {"unknown": b"\x00", "iv": b"\x01", "noniv": b"\x02"}
ROUTE_STATE_CODE = {"missing": b"\x00", "unknown": b"\x01", "iv": b"\x02", "noniv": b"\x03"}
ALLOWED_DECISIONS = ("iv", "noniv", "unknown")
ALLOWED_REVIEW_STATUSES = ("unreviewed", "reviewed")
ALLOWED_DECISION_BASES = {
    "explicit_iv_route_semantics",
    "explicit_noniv_route_semantics",
    "ambiguous_or_insufficient_route_semantics",
    "other_documented_human_judgment",
}
REVIEWED_AT_RE = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z\Z"
)
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_RAW_UTF8_BYTES = 65_535
MAX_EXACT_COUNT = (1 << 63) - 1
MAX_REVIEWER_ID_BYTES = 128
SOURCE_SPECS = (
    ("emar_detail_route", "mimiciv_hosp.emar_detail.route", "direct_detail_route"),
    ("pharmacy_route", "mimiciv_hosp.pharmacy.route", "auxiliary_pharmacy_route"),
    (
        "prescriptions_route",
        "mimiciv_hosp.prescriptions.route",
        "auxiliary_prescriptions_route",
    ),
)
GENERATOR_PATHS = (
    "src/april_repro/route_adjudication.py",
    "scripts/create_potassium_route_review.py",
    "scripts/compile_potassium_route_review.py",
)
AUDITOR_PATHS = (
    "src/april_repro/route_adjudication_audit.py",
    "scripts/audit_potassium_route_mapping.py",
)
FALSE_GUARDS = {
    "formal_route_mapping_created": False,
    "route_mapping_frozen": False,
    "query202_unlocked": False,
    "database_connected": False,
    "external_api_called": False,
    "product_identity_decided": False,
    "event_mapping_created": False,
    "final_source_policy": False,
    "formal_action": False,
    "formal_episode": False,
    "formal_label": False,
    "formal_cohort": False,
    "llm_called": False,
}


class RouteAdjudicationError(RuntimeError):
    """A fail-closed structural, lineage, privacy, or review error."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


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


def _read_unique_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink():
        raise RouteAdjudicationError(f"{label} must be one regular file.")
    if not 0 < path.stat().st_size <= MAX_JSON_BYTES:
        raise RouteAdjudicationError(f"{label} exceeds its private JSON size contract.")
    raw = path.read_bytes()

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RouteAdjudicationError(f"{label} contains a duplicate JSON key.")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except RouteAdjudicationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RouteAdjudicationError(f"{label} is not valid unique-key JSON.") from exc
    if not isinstance(value, dict):
        raise RouteAdjudicationError(f"{label} must contain one JSON object.")
    return value, raw


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


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _bundle(root: Path, paths: Sequence[str]) -> dict[str, Any]:
    digest = hashlib.sha256()
    files: list[dict[str, Any]] = []
    for relative_text in paths:
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise RouteAdjudicationError("An implementation path is unsafe.")
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise RouteAdjudicationError("A required implementation file is absent.")
        path_bytes = relative_text.encode("utf-8")
        content = path.read_bytes()
        digest.update(struct.pack(">I", len(path_bytes)))
        digest.update(path_bytes)
        digest.update(struct.pack(">Q", len(content)))
        digest.update(content)
        files.append(
            {
                "path": relative_text,
                "bytes": len(content),
                "file_sha256": _sha(content),
            }
        )
    return {
        "paths": list(paths),
        "bundle_sha256": digest.hexdigest(),
        "files": files,
        "encoding": "uint32be_path_length+path_utf8+uint64be_content_length+content",
    }


def implementation_bundles(root: Path) -> dict[str, dict[str, Any]]:
    return {
        "generator": _bundle(root, GENERATOR_PATHS),
        "auditor": _bundle(root, AUDITOR_PATHS),
    }


def _safe_relative(root: Path, relative_text: Any, label: str) -> Path:
    if not isinstance(relative_text, str) or not relative_text:
        raise RouteAdjudicationError(f"{label} path is invalid.")
    relative = Path(relative_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise RouteAdjudicationError(f"{label} path is unsafe.")
    path = root / relative
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise RouteAdjudicationError(f"{label} path escapes the project root.") from exc
    return path


def _load_config(root: Path, *, require_frozen_hashes: bool = True) -> dict[str, Any]:
    path = root / CONFIG_PATH
    if not path.is_file() or path.is_symlink():
        raise RouteAdjudicationError("The route-adjudication config is absent.")
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise RouteAdjudicationError("The route-adjudication config is invalid.") from exc
    if (
        config.get("schema_version") != 1
        or config.get("component_id") != COMPONENT_ID
        or config.get("status") != "proposed"
        or config.get("execution_status") != "not_executed"
    ):
        raise RouteAdjudicationError("The route-adjudication component gate is invalid.")
    review = config.get("review_contract")
    cardinality = config.get("cardinality")
    private = config.get("private_artifact")
    public = config.get("public_artifact")
    boundary = config.get("boundary")
    guards = config.get("guards")
    if not all(isinstance(item, Mapping) for item in (review, cardinality, private, public, boundary, guards)):
        raise RouteAdjudicationError("The route-adjudication config lacks a contract section.")
    if (
        review.get("allowed_decisions") != list(ALLOWED_DECISIONS)
        or review.get("default_decision") != "unknown"
        or review.get("allowed_review_statuses") != list(ALLOWED_REVIEW_STATUSES)
        or review.get("sql_null_has_nonnull_decision") is not False
        or review.get("sql_null_route_state") != "missing"
        or review.get("sql_null_sets_has_unknown") is not False
        or review.get("source_specific_overrides_allowed") is not False
    ):
        raise RouteAdjudicationError("The exact route decision contract changed.")
    if (
        cardinality.get("source_specific_typed_memberships") != 236
        or cardinality.get("source_specific_nonnull_memberships") != 233
        or cardinality.get("source_specific_sql_null_memberships") != 3
        or cardinality.get("canonical_exact_nonnull_values") != 117
    ):
        raise RouteAdjudicationError("The preregistered route cardinality changed.")
    if (
        private.get("directory_mode") != "0700"
        or private.get("file_mode") != "0600"
        or private.get("git_ignored_required") is not True
        or public.get("raw_route_values_allowed") is not False
        or public.get("per_value_hashes_allowed") is not False
    ):
        raise RouteAdjudicationError("The route-adjudication privacy contract changed.")
    required_false_boundary = (
        "database_access_allowed",
        "external_api_allowed",
        "product_or_event_mapping_allowed",
        "source_policy_decision_allowed",
        "formal_action_episode_label_or_cohort_allowed",
        "automatic_lexical_or_fuzzy_classification_allowed",
        "normalization_allowed",
        "query202_unlock_allowed",
        "formal_route_mapping_freeze_allowed",
    )
    if any(boundary.get(key) is not False for key in required_false_boundary):
        raise RouteAdjudicationError("A prohibited route-adjudication boundary was enabled.")
    if any(guards.get(key) is not value for key, value in FALSE_GUARDS.items()):
        raise RouteAdjudicationError("A formal route-adjudication guard was enabled.")
    sources = config.get("route_source")
    if not isinstance(sources, list) or len(sources) != len(SOURCE_SPECS):
        raise RouteAdjudicationError("The route source configuration is invalid.")
    for configured, expected in zip(sources, SOURCE_SPECS, strict=True):
        if not isinstance(configured, Mapping):
            raise RouteAdjudicationError("A route source configuration is invalid.")
        if tuple(configured.get(key) for key in ("source_key", "source_field", "field_role")) != expected:
            raise RouteAdjudicationError("The route source order or role changed.")
        if not isinstance(configured.get("typed_distinct_values"), int):
            raise RouteAdjudicationError("A route source cardinality is invalid.")
        if not isinstance(configured.get("nonnull_distinct_values"), int):
            raise RouteAdjudicationError("A route source cardinality is invalid.")
        if SHA256_RE.fullmatch(str(configured.get("typed_set_sha256"))) is None:
            raise RouteAdjudicationError("A route source set hash is invalid.")
    hashes = config.get("implementation_hashes")
    if not isinstance(hashes, Mapping):
        raise RouteAdjudicationError("Implementation hashes are absent.")
    if hashes.get("generator_paths") != list(GENERATOR_PATHS) or hashes.get(
        "auditor_paths"
    ) != list(AUDITOR_PATHS):
        raise RouteAdjudicationError("Implementation bundle paths changed.")
    bundles = implementation_bundles(root)
    for name in ("generator", "auditor"):
        expected = hashes.get(name + "_bundle_sha256")
        if require_frozen_hashes and SHA256_RE.fullmatch(str(expected)) is None:
            raise RouteAdjudicationError("Implementation hashes are not frozen.")
        if require_frozen_hashes and expected != bundles[name]["bundle_sha256"]:
            raise RouteAdjudicationError("An implementation bundle hash changed.")
    return {
        "data": config,
        "path": path,
        "config_sha256": _sha_file(path),
        "implementation_bundles": bundles,
    }


def _typed_set_sha256(source_field: str, records: Sequence[Mapping[str, Any]]) -> str:
    field = source_field.encode("utf-8")
    null_seen = False
    nonnull: list[bytes] = []
    for record in records:
        is_null = record.get("raw_is_null")
        raw_value = record.get("raw_value")
        count = record.get("exact_row_count")
        if type(count) is not int or not 1 <= count <= MAX_EXACT_COUNT:
            raise RouteAdjudicationError("A preflight route frequency is invalid.")
        if is_null is True and raw_value is None:
            if null_seen:
                raise RouteAdjudicationError("A preflight route set repeats SQL NULL.")
            null_seen = True
        elif is_null is False and isinstance(raw_value, str):
            try:
                raw = raw_value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise RouteAdjudicationError("A preflight route value is not UTF-8.") from exc
            if b"\x00" in raw or len(raw) > MAX_RAW_UTF8_BYTES:
                raise RouteAdjudicationError("A preflight route value exceeds its byte contract.")
            if record.get("raw_utf8_bytes") != len(raw):
                raise RouteAdjudicationError("A preflight route byte count is inconsistent.")
            expected_substate = (
                "empty_string"
                if raw_value == ""
                else "whitespace_only"
                if raw_value.isspace()
                else "nonblank"
            )
            if record.get("nonnull_substate") != expected_substate:
                raise RouteAdjudicationError("A preflight route substate is inconsistent.")
            nonnull.append(raw)
        else:
            raise RouteAdjudicationError("A preflight route typed state is invalid.")
    if len(nonnull) != len(set(nonnull)):
        raise RouteAdjudicationError("A preflight route exact set has duplicates.")
    digest = hashlib.sha256()
    digest.update(TYPED_SET_HASH_VERSION)
    digest.update(struct.pack(">I", len(field)))
    digest.update(field)
    digest.update(struct.pack(">Q", len(nonnull) + int(null_seen)))
    if null_seen:
        digest.update(b"\x00")
    for raw in sorted(nonnull):
        digest.update(b"\x01")
        digest.update(struct.pack(">Q", len(raw)))
        digest.update(raw)
    return digest.hexdigest()


def _canonical_set_sha256(raw_values: Sequence[str]) -> str:
    encoded = sorted(value.encode("utf-8") for value in raw_values)
    if len(encoded) != len(set(encoded)):
        raise RouteAdjudicationError("The canonical exact-value set has duplicates.")
    digest = hashlib.sha256()
    digest.update(CANONICAL_SET_HASH_VERSION)
    digest.update(struct.pack(">Q", len(encoded)))
    for raw in encoded:
        digest.update(struct.pack(">Q", len(raw)))
        digest.update(raw)
    return digest.hexdigest()


def _mapping_sha256(private_input_sha256: str, entries: Sequence[Mapping[str, Any]]) -> str:
    if SHA256_RE.fullmatch(private_input_sha256) is None:
        raise RouteAdjudicationError("The mapping input hash is invalid.")

    def key(entry: Mapping[str, Any]) -> tuple[bytes, int, bytes]:
        field = entry.get("source_field")
        state = entry.get("raw_value_state")
        raw_value = entry.get("exact_raw_value")
        if not isinstance(field, str):
            raise RouteAdjudicationError("A mapping source field is invalid.")
        if state == "sql_null" and raw_value is None:
            return field.encode("utf-8"), 0, b""
        if state == "nonnull" and isinstance(raw_value, str):
            return field.encode("utf-8"), 1, raw_value.encode("utf-8")
        raise RouteAdjudicationError("A mapping typed key is invalid.")

    ordered = sorted(entries, key=key)
    if len({key(entry) for entry in ordered}) != len(ordered):
        raise RouteAdjudicationError("The source-specific mapping contains duplicate keys.")
    digest = hashlib.sha256()
    digest.update(MAPPING_HASH_VERSION)
    digest.update(bytes.fromhex(private_input_sha256))
    digest.update(struct.pack(">Q", len(ordered)))
    for entry in ordered:
        field, state, raw = key(entry)
        decision = entry.get("decision")
        route_state = entry.get("route_state")
        if state == 0:
            if decision is not None or route_state != "missing":
                raise RouteAdjudicationError("A SQL-NULL mapping state is invalid.")
        elif decision not in DECISION_CODE or route_state != decision:
            raise RouteAdjudicationError("A nonnull mapping decision is invalid.")
        digest.update(struct.pack(">I", len(field)))
        digest.update(field)
        digest.update(bytes((state,)))
        if state == 1:
            digest.update(struct.pack(">Q", len(raw)))
            digest.update(raw)
        digest.update(ROUTE_STATE_CODE[str(route_state)])
    return digest.hexdigest()


def _validate_preflight(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    input_config = config.get("input")
    sources_config = config.get("route_source")
    if not isinstance(input_config, Mapping) or not isinstance(sources_config, list):
        raise RouteAdjudicationError("The preflight lineage configuration is invalid.")
    directory = _safe_relative(root, input_config.get("artifact_directory"), "preflight")
    if not directory.is_dir() or directory.is_symlink() or _mode(directory) != "0700":
        raise RouteAdjudicationError("The preflight artifact directory is unsafe.")
    files: dict[str, tuple[Path, bytes | None]] = {}
    for role in ("manifest", "audit", "private_values", "aggregate_summary"):
        path = directory / str(input_config.get(role + "_file"))
        if path.parent != directory or not path.is_file() or path.is_symlink():
            raise RouteAdjudicationError("A preregistered preflight evidence file is absent.")
        if _mode(path) != "0600":
            raise RouteAdjudicationError("A preflight evidence file has an unsafe mode.")
        observed = _sha_file(path)
        if observed != input_config.get(role + "_sha256"):
            raise RouteAdjudicationError("A preregistered preflight evidence hash changed.")
        files[role] = (path, None)
    manifest, _ = _read_unique_json(files["manifest"][0], "preflight manifest")
    audit, _ = _read_unique_json(files["audit"][0], "preflight audit")
    private, private_raw = _read_unique_json(
        files["private_values"][0], "preflight private values"
    )
    if manifest.get("status") != "complete":
        raise RouteAdjudicationError("The preflight manifest is not complete.")
    if audit.get("status") != input_config.get("preflight_audit_status_required"):
        raise RouteAdjudicationError("The preflight independent audit did not pass.")
    checks = audit.get("audit_checks")
    if (
        not isinstance(checks, Mapping)
        or checks.get("failed") != []
        or len(checks.get("failed", [])) != input_config.get("preflight_audit_failures_required")
    ):
        raise RouteAdjudicationError("The preflight independent audit has failures.")
    lineage = private.get("component_lineage")
    if (
        not isinstance(lineage, Mapping)
        or lineage.get("component_id") != input_config.get("preflight_component_id")
        or lineage.get("config_sha256") != input_config.get("preflight_config_sha256")
        or private.get("route_mapping_created") is not False
        or private.get("external_api_called") is not False
        or private.get("product_identity_decided") is not False
        or private.get("final_source_policy") is not False
    ):
        raise RouteAdjudicationError("The preflight private lineage or guards are invalid.")
    private_sources = private.get("sources")
    if not isinstance(private_sources, Mapping):
        raise RouteAdjudicationError("The preflight private source object is invalid.")
    validated: dict[str, dict[str, Any]] = {}
    all_nonnull: dict[bytes, str] = {}
    typed_total = nonnull_total = null_total = 0
    for configured, expected_spec in zip(sources_config, SOURCE_SPECS, strict=True):
        source_key, source_field, field_role = expected_spec
        source = private_sources.get(source_key)
        if not isinstance(source, Mapping) or source.get("source_field") != source_field:
            raise RouteAdjudicationError("A preflight route source is invalid.")
        records = source.get("records")
        if not isinstance(records, list):
            raise RouteAdjudicationError("A preflight route record collection is invalid.")
        typed_hash = _typed_set_sha256(source_field, records)
        nonnull_records = [item for item in records if item.get("raw_is_null") is False]
        null_records = [item for item in records if item.get("raw_is_null") is True]
        if (
            typed_hash != configured.get("typed_set_sha256")
            or source.get("typed_set_sha256") != typed_hash
            or len(records) != configured.get("typed_distinct_values")
            or len(nonnull_records) != configured.get("nonnull_distinct_values")
            or len(null_records) != 1
        ):
            raise RouteAdjudicationError("A preflight route set does not match preregistration.")
        copied: list[dict[str, Any]] = []
        for record in records:
            raw_value = record["raw_value"]
            if raw_value is not None:
                raw_bytes = raw_value.encode("utf-8")
                all_nonnull.setdefault(raw_bytes, raw_value)
            copied.append(dict(record))
        validated[source_key] = {
            "source_key": source_key,
            "source_field": source_field,
            "field_role": field_role,
            "typed_set_sha256": typed_hash,
            "records": copied,
        }
        typed_total += len(records)
        nonnull_total += len(nonnull_records)
        null_total += len(null_records)
    cardinality = config.get("cardinality")
    if (
        typed_total != cardinality.get("source_specific_typed_memberships")
        or nonnull_total != cardinality.get("source_specific_nonnull_memberships")
        or null_total != cardinality.get("source_specific_sql_null_memberships")
        or len(all_nonnull) != cardinality.get("canonical_exact_nonnull_values")
    ):
        raise RouteAdjudicationError("The route exact-set cardinality is not conserved.")
    return {
        "directory": directory,
        "manifest_sha256": input_config["manifest_sha256"],
        "audit_sha256": input_config["audit_sha256"],
        "private_values_sha256": _sha(private_raw),
        "aggregate_summary_sha256": input_config["aggregate_summary_sha256"],
        "sources": validated,
        "canonical_values": [all_nonnull[key] for key in sorted(all_nonnull)],
    }


def _lineage(root: Path, config_report: Mapping[str, Any], preflight: Mapping[str, Any]) -> dict[str, Any]:
    config = config_report["data"]
    return {
        "component_id": COMPONENT_ID,
        "rule_version": config["rule_version"],
        "config": str(CONFIG_PATH),
        "config_sha256": config_report["config_sha256"],
        "preflight_artifact_directory": str(preflight["directory"].relative_to(root)),
        "preflight_component_id": config["input"]["preflight_component_id"],
        "preflight_config_sha256": config["input"]["preflight_config_sha256"],
        "preflight_manifest_sha256": preflight["manifest_sha256"],
        "preflight_audit_sha256": preflight["audit_sha256"],
        "preflight_private_values_sha256": preflight["private_values_sha256"],
        "preflight_aggregate_summary_sha256": preflight["aggregate_summary_sha256"],
        "route_typed_set_sha256": {
            key: value["typed_set_sha256"] for key, value in preflight["sources"].items()
        },
    }


def _destination(root: Path, family: str) -> Path:
    base = root / "artifacts" / family
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    base.chmod(0o700)
    destination = base / _stamp()
    destination.mkdir(mode=0o700)
    destination.chmod(0o700)
    return destination


def _review_template(
    root: Path, config_report: Mapping[str, Any], preflight: Mapping[str, Any]
) -> dict[str, Any]:
    memberships_by_raw: dict[bytes, list[dict[str, Any]]] = {}
    null_mappings: list[dict[str, Any]] = []
    for source_key, source in preflight["sources"].items():
        for record in source["records"]:
            if record["raw_is_null"]:
                null_mappings.append(
                    {
                        "source_key": source_key,
                        "source_field": source["source_field"],
                        "field_role": source["field_role"],
                        "raw_value_state": "sql_null",
                        "exact_raw_value": None,
                        "exact_row_count": record["exact_row_count"],
                        "decision": None,
                        "route_state": "missing",
                        "sets_has_unknown": False,
                        "decision_provenance": "forced_sql_null_policy",
                    }
                )
                continue
            raw_value = record["raw_value"]
            raw_bytes = raw_value.encode("utf-8")
            memberships_by_raw.setdefault(raw_bytes, []).append(
                {
                    "source_key": source_key,
                    "source_field": source["source_field"],
                    "field_role": source["field_role"],
                    "exact_row_count": record["exact_row_count"],
                }
            )
    reviews: list[dict[str, Any]] = []
    for index, raw_bytes in enumerate(sorted(memberships_by_raw), start=1):
        memberships = sorted(
            memberships_by_raw[raw_bytes], key=lambda item: item["source_field"].encode()
        )
        reviews.append(
            {
                "canonical_review_id": f"R{index:06d}",
                "raw_value_state": "nonnull",
                "exact_raw_value": raw_bytes.decode("utf-8"),
                "raw_utf8_bytes": len(raw_bytes),
                "decision": "unknown",
                "review_status": "unreviewed",
                "decision_basis": None,
                "reviewer_id": None,
                "reviewed_at_utc": None,
                "source_memberships": memberships,
            }
        )
    return {
        "schema_version": 1,
        "artifact_type": "potassium_route_exact_value_review_template",
        "created_at_utc": _now(),
        "status": "draft_unreviewed",
        "lineage": _lineage(root, config_report, preflight),
        "decision_contract": {
            "allowed_decisions": list(ALLOWED_DECISIONS),
            "default_decision": "unknown",
            "allowed_review_statuses": list(ALLOWED_REVIEW_STATUSES),
            "allowed_decision_bases": sorted(ALLOWED_DECISION_BASES),
            "canonical_bridge": "byte_exact_nonnull_raw_value_only",
            "source_specific_overrides_allowed": False,
            "sql_null_has_nonnull_decision": False,
            "sql_null_route_state": "missing",
            "sql_null_sets_has_unknown": False,
        },
        "cardinality": {
            "canonical_exact_nonnull_values": len(reviews),
            "source_specific_nonnull_memberships": sum(
                len(item["source_memberships"]) for item in reviews
            ),
            "source_specific_sql_null_memberships": len(null_mappings),
            "source_specific_typed_memberships": sum(
                len(item["source_memberships"]) for item in reviews
            )
            + len(null_mappings),
        },
        "canonical_exact_set_sha256": _canonical_set_sha256(
            [item["exact_raw_value"] for item in reviews]
        ),
        "canonical_reviews": reviews,
        "sql_null_mappings": sorted(
            null_mappings, key=lambda item: item["source_field"].encode()
        ),
        "formal_guards": dict(FALSE_GUARDS),
        "limitations": (
            "This is a private review template. All nonnull values are unreviewed "
            "and default to unknown. It does not freeze a route mapping or unlock Query 202."
        ),
    }


def _summary_from_review(review: Mapping[str, Any], review_sha256: str) -> dict[str, Any]:
    reviews = review["canonical_reviews"]
    nulls = review["sql_null_mappings"]
    return {
        "schema_version": 1,
        "artifact_type": "potassium_route_review_aggregate_summary",
        "status": review["status"],
        "component_lineage": review["lineage"],
        "cardinality": review["cardinality"],
        "review_status_counts": dict(Counter(item["review_status"] for item in reviews)),
        "canonical_decision_counts": dict(Counter(item["decision"] for item in reviews)),
        "source_membership_route_state_counts": {
            "missing": len(nulls),
            "unknown": sum(len(item["source_memberships"]) for item in reviews),
            "iv": 0,
            "noniv": 0,
        },
        "canonical_exact_set_sha256": review["canonical_exact_set_sha256"],
        "private_review_sha256": review_sha256,
        "privacy": {
            "raw_route_values_emitted": False,
            "per_value_hashes_emitted": False,
            "patient_or_event_data_emitted": False,
        },
        "formal_guards": dict(FALSE_GUARDS),
        "limitations": review["limitations"],
    }


def create_review_template(root: Path) -> dict[str, Any]:
    """Create one private all-unknown review template from the frozen preflight."""
    config_report = _load_config(root)
    preflight = _validate_preflight(root, config_report["data"])
    review = _review_template(root, config_report, preflight)
    review_bytes = _json_bytes(review)
    summary = _summary_from_review(review, _sha(review_bytes))
    summary_bytes = _json_bytes(summary)
    destination = _destination(root, "route-adjudication")
    review_path = destination / "potassium_route_review.private.json"
    summary_path = destination / "potassium_route_review.aggregate-summary.json"
    manifest_path = destination / "manifest.json"
    _write_private(review_path, review_bytes)
    _write_private(summary_path, summary_bytes)
    manifest = {
        "schema_version": 1,
        "artifact_type": "potassium_route_review_manifest",
        "status": "complete",
        "created_at_utc": _now(),
        "component_lineage": review["lineage"],
        "implementation_bundles": config_report["implementation_bundles"],
        "files": {
            "private_review": {
                "name": review_path.name,
                "sha256": _sha(review_bytes),
                "bytes": len(review_bytes),
                "mode": "0600",
            },
            "aggregate_summary": {
                "name": summary_path.name,
                "sha256": _sha(summary_bytes),
                "bytes": len(summary_bytes),
                "mode": "0600",
            },
        },
        "directory_mode": "0700",
        "database_connected": False,
        "external_api_called": False,
        "formal_guards": dict(FALSE_GUARDS),
        "limitations": review["limitations"],
    }
    manifest_bytes = _json_bytes(manifest)
    _write_private(manifest_path, manifest_bytes)
    if _mode(destination) != "0700" or any(
        _mode(path) != "0600" for path in (review_path, summary_path, manifest_path)
    ):
        raise RouteAdjudicationError("A review artifact has an unsafe mode.")
    return {
        "status": "complete",
        "review_status": "draft_unreviewed",
        "manifest": str(manifest_path.relative_to(root)),
        "private_review": str(review_path.relative_to(root)),
        "aggregate_summary": str(summary_path.relative_to(root)),
        "canonical_exact_nonnull_values": review["cardinality"][
            "canonical_exact_nonnull_values"
        ],
        "source_specific_typed_memberships": review["cardinality"][
            "source_specific_typed_memberships"
        ],
        "private_review_sha256": _sha(review_bytes),
        "canonical_exact_set_sha256": review["canonical_exact_set_sha256"],
        "route_mapping_frozen": False,
        "query202_unlocked": False,
    }


def _expected_review(root: Path, config_report: Mapping[str, Any], preflight: Mapping[str, Any]) -> dict[str, Any]:
    expected = _review_template(root, config_report, preflight)
    expected.pop("created_at_utc", None)
    return expected


def _validate_review(
    review: Mapping[str, Any], expected: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    required_top = set(expected)
    required_top.add("created_at_utc")
    if set(review) != required_top:
        raise RouteAdjudicationError("The private review top-level schema changed.")
    for key in (
        "schema_version",
        "artifact_type",
        "status",
        "lineage",
        "decision_contract",
        "cardinality",
        "canonical_exact_set_sha256",
        "sql_null_mappings",
        "formal_guards",
        "limitations",
    ):
        if review.get(key) != expected.get(key):
            raise RouteAdjudicationError("A non-editable private review field changed.")
    if not isinstance(review.get("created_at_utc"), str):
        raise RouteAdjudicationError("The private review creation time is invalid.")
    reviews = review.get("canonical_reviews")
    expected_reviews = expected.get("canonical_reviews")
    if not isinstance(reviews, list) or not isinstance(expected_reviews, list):
        raise RouteAdjudicationError("The canonical review collection is invalid.")
    if len(reviews) != len(expected_reviews):
        raise RouteAdjudicationError("The canonical review cardinality changed.")
    compiled: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    for position, (item, expected_item) in enumerate(
        zip(reviews, expected_reviews, strict=True), start=1
    ):
        if not isinstance(item, Mapping):
            raise RouteAdjudicationError("A canonical review entry is invalid.")
        if set(item) != set(expected_item):
            raise RouteAdjudicationError("A canonical review entry schema changed.")
        immutable = (
            "canonical_review_id",
            "raw_value_state",
            "exact_raw_value",
            "raw_utf8_bytes",
            "source_memberships",
        )
        if any(item.get(key) != expected_item.get(key) for key in immutable):
            raise RouteAdjudicationError(
                f"Canonical review entry {position} changed a non-editable exact-set field."
            )
        decision = item.get("decision")
        review_status = item.get("review_status")
        basis = item.get("decision_basis")
        reviewer = item.get("reviewer_id")
        reviewed_at = item.get("reviewed_at_utc")
        if decision not in ALLOWED_DECISIONS or review_status not in ALLOWED_REVIEW_STATUSES:
            raise RouteAdjudicationError(
                f"Canonical review entry {position} has an invalid controlled state."
            )
        if review_status == "unreviewed":
            if decision != "unknown" or any(
                value is not None for value in (basis, reviewer, reviewed_at)
            ):
                raise RouteAdjudicationError(
                    f"Canonical review entry {position} violates the default-unknown contract."
                )
            provenance = "default_unknown_unreviewed"
        else:
            if basis not in ALLOWED_DECISION_BASES:
                raise RouteAdjudicationError(
                    f"Canonical review entry {position} lacks a controlled decision basis."
                )
            if not isinstance(reviewer, str) or not reviewer.strip():
                raise RouteAdjudicationError(
                    f"Canonical review entry {position} lacks a reviewer id."
                )
            try:
                reviewer_bytes = reviewer.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise RouteAdjudicationError(
                    f"Canonical review entry {position} has an invalid reviewer id."
                ) from exc
            if len(reviewer_bytes) > MAX_REVIEWER_ID_BYTES:
                raise RouteAdjudicationError(
                    f"Canonical review entry {position} has an overlong reviewer id."
                )
            if not isinstance(reviewed_at, str) or REVIEWED_AT_RE.fullmatch(reviewed_at) is None:
                raise RouteAdjudicationError(
                    f"Canonical review entry {position} lacks a strict UTC review time."
                )
            basis_by_decision = {
                "iv": {"explicit_iv_route_semantics", "other_documented_human_judgment"},
                "noniv": {
                    "explicit_noniv_route_semantics",
                    "other_documented_human_judgment",
                },
                "unknown": {
                    "ambiguous_or_insufficient_route_semantics",
                    "other_documented_human_judgment",
                },
            }
            if basis not in basis_by_decision[decision]:
                raise RouteAdjudicationError(
                    f"Canonical review entry {position} has an inconsistent decision basis."
                )
            provenance = "human_reviewed_exact_canonical_value"
        status_counts[str(review_status)] += 1
        for membership in item["source_memberships"]:
            compiled.append(
                {
                    "source_key": membership["source_key"],
                    "source_field": membership["source_field"],
                    "field_role": membership["field_role"],
                    "raw_value_state": "nonnull",
                    "exact_raw_value": item["exact_raw_value"],
                    "exact_row_count": membership["exact_row_count"],
                    "decision": decision,
                    "route_state": decision,
                    "sets_has_unknown": decision == "unknown",
                    "decision_provenance": provenance,
                    "canonical_review_id": item["canonical_review_id"],
                    "review_status": review_status,
                    "decision_basis": basis,
                    "reviewer_id": reviewer,
                    "reviewed_at_utc": reviewed_at,
                }
            )
    for null_entry in review["sql_null_mappings"]:
        compiled.append(
            {
                **null_entry,
                "canonical_review_id": None,
                "review_status": "not_required",
                "decision_basis": "forced_sql_null_policy",
                "reviewer_id": None,
                "reviewed_at_utc": None,
            }
        )
    return compiled, dict(status_counts)


def _mapping_summary(mapping: Mapping[str, Any], mapping_bytes: bytes) -> dict[str, Any]:
    entries = mapping["entries"]
    canonical_counts = mapping["review_status_counts"]
    by_source: dict[str, dict[str, Any]] = {}
    for source_key, source_field, field_role in SOURCE_SPECS:
        source_entries = [item for item in entries if item["source_key"] == source_key]
        by_source[source_key] = {
            "source_field": source_field,
            "field_role": field_role,
            "typed_memberships": len(source_entries),
            "nonnull_memberships": sum(
                item["raw_value_state"] == "nonnull" for item in source_entries
            ),
            "sql_null_memberships": sum(
                item["raw_value_state"] == "sql_null" for item in source_entries
            ),
            "nonnull_decision_counts": dict(
                Counter(
                    item["decision"]
                    for item in source_entries
                    if item["decision"] is not None
                )
            ),
            "route_state_counts": dict(Counter(item["route_state"] for item in source_entries)),
            "has_unknown_evidence_memberships": sum(
                item["sets_has_unknown"] is True for item in source_entries
            ),
        }
    return {
        "schema_version": 1,
        "artifact_type": "potassium_route_mapping_aggregate_summary",
        "status": mapping["status"],
        "component_lineage": mapping["lineage"],
        "private_review_sha256": mapping["private_review_sha256"],
        "private_mapping_sha256": _sha(mapping_bytes),
        "source_specific_mapping_sha256": mapping["source_specific_mapping_sha256"],
        "canonical_exact_set_sha256": mapping["canonical_exact_set_sha256"],
        "cardinality": mapping["cardinality"],
        "review_status_counts": canonical_counts,
        "human_review_complete": mapping["human_review_complete"],
        "source_summaries": by_source,
        "aggregate_nonnull_decision_counts": dict(
            Counter(item["decision"] for item in entries if item["decision"] is not None)
        ),
        "aggregate_route_state_counts": dict(Counter(item["route_state"] for item in entries)),
        "has_unknown_evidence_memberships": sum(
            item["sets_has_unknown"] is True for item in entries
        ),
        "privacy": {
            "raw_route_values_emitted": False,
            "per_value_hashes_emitted": False,
            "patient_or_event_data_emitted": False,
        },
        "formal_guards": dict(FALSE_GUARDS),
        "limitations": mapping["limitations"],
    }


def compile_review(root: Path, review_path: Path) -> dict[str, Any]:
    """Validate a private human review and compile all source-specific keys."""
    config_report = _load_config(root)
    preflight = _validate_preflight(root, config_report["data"])
    try:
        resolved_review = review_path.resolve(strict=True)
        resolved_review.relative_to((root / "artifacts").resolve())
    except (OSError, ValueError) as exc:
        raise RouteAdjudicationError("The private review path is outside artifacts.") from exc
    if review_path.is_symlink() or _mode(review_path) != "0600":
        raise RouteAdjudicationError("The private review file has an unsafe mode.")
    review, review_bytes = _read_unique_json(review_path, "private route review")
    expected = _expected_review(root, config_report, preflight)
    entries, review_status_counts = _validate_review(review, expected)
    cardinality = config_report["data"]["cardinality"]
    if (
        len(entries) != cardinality["source_specific_typed_memberships"]
        or sum(item["raw_value_state"] == "nonnull" for item in entries)
        != cardinality["source_specific_nonnull_memberships"]
        or sum(item["raw_value_state"] == "sql_null" for item in entries)
        != cardinality["source_specific_sql_null_memberships"]
    ):
        raise RouteAdjudicationError("Compiled source-specific membership counts changed.")
    human_complete = review_status_counts.get("reviewed", 0) == cardinality[
        "canonical_exact_nonnull_values"
    ]
    status = (
        "human_review_complete_unfrozen"
        if human_complete
        else "draft_with_unreviewed_defaults"
    )
    mapping_hash = _mapping_sha256(preflight["private_values_sha256"], entries)
    mapping = {
        "schema_version": 1,
        "artifact_type": "potassium_route_source_specific_exact_mapping",
        "created_at_utc": _now(),
        "status": status,
        "lineage": _lineage(root, config_report, preflight),
        "private_review_path": str(review_path.resolve().relative_to(root.resolve())),
        "private_review_sha256": _sha(review_bytes),
        "canonical_exact_set_sha256": review["canonical_exact_set_sha256"],
        "source_specific_mapping_sha256": mapping_hash,
        "mapping_hash_contract": {
            "version": MAPPING_HASH_VERSION.decode("ascii"),
            "route_state_encoding": "missing=0x00,unknown=0x01,iv=0x02,noniv=0x03",
            "frequency_included": False,
        },
        "cardinality": dict(review["cardinality"]),
        "review_status_counts": review_status_counts,
        "human_review_complete": human_complete,
        "entries": entries,
        "formal_guards": dict(FALSE_GUARDS),
        "limitations": (
            "This structurally validated private mapping is not formally frozen and "
            "does not unlock Query 202. Human clinical correctness is not established "
            "by compilation or audit."
        ),
    }
    mapping_bytes = _json_bytes(mapping)
    summary = _mapping_summary(mapping, mapping_bytes)
    summary_bytes = _json_bytes(summary)
    destination = _destination(root, "route-mapping")
    mapping_path = destination / "potassium_route_mapping.private.json"
    summary_path = destination / "potassium_route_mapping.aggregate-summary.json"
    manifest_path = destination / "manifest.json"
    _write_private(mapping_path, mapping_bytes)
    _write_private(summary_path, summary_bytes)
    manifest = {
        "schema_version": 1,
        "artifact_type": "potassium_route_mapping_manifest",
        "status": "complete",
        "mapping_status": status,
        "created_at_utc": _now(),
        "component_lineage": mapping["lineage"],
        "private_review_path": mapping["private_review_path"],
        "private_review_sha256": mapping["private_review_sha256"],
        "implementation_bundles": config_report["implementation_bundles"],
        "files": {
            "private_mapping": {
                "name": mapping_path.name,
                "sha256": _sha(mapping_bytes),
                "bytes": len(mapping_bytes),
                "mode": "0600",
            },
            "aggregate_summary": {
                "name": summary_path.name,
                "sha256": _sha(summary_bytes),
                "bytes": len(summary_bytes),
                "mode": "0600",
            },
        },
        "directory_mode": "0700",
        "database_connected": False,
        "external_api_called": False,
        "formal_guards": dict(FALSE_GUARDS),
        "limitations": mapping["limitations"],
    }
    manifest_bytes = _json_bytes(manifest)
    _write_private(manifest_path, manifest_bytes)
    if _mode(destination) != "0700" or any(
        _mode(path) != "0600" for path in (mapping_path, summary_path, manifest_path)
    ):
        raise RouteAdjudicationError("A compiled route mapping artifact has an unsafe mode.")
    return {
        "status": "complete",
        "mapping_status": status,
        "manifest": str(manifest_path.relative_to(root)),
        "private_mapping": str(mapping_path.relative_to(root)),
        "aggregate_summary": str(summary_path.relative_to(root)),
        "source_specific_typed_memberships": len(entries),
        "canonical_exact_nonnull_values": cardinality["canonical_exact_nonnull_values"],
        "review_status_counts": review_status_counts,
        "source_specific_mapping_sha256": mapping_hash,
        "private_mapping_sha256": _sha(mapping_bytes),
        "route_mapping_frozen": False,
        "query202_unlocked": False,
    }


__all__ = [
    "RouteAdjudicationError",
    "create_review_template",
    "compile_review",
    "implementation_bundles",
]
