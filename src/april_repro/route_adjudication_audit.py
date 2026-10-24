"""Independent offline audit for a compiled exact-value route mapping.

The auditor intentionally does not import the generator/compiler module.  It
rebuilds the three route sets, the canonical exact bridge, source-specific
mapping decisions, byte hashes, aggregate summaries, privacy checks, and modes
from the saved private artifacts.  It never opens a database or prints a raw
route value.
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
import tempfile
import tomllib
from typing import Any, Mapping, Sequence


CONFIG_PATH = Path("config/preregistrations/d005_potassium_route_adjudication.toml")
COMPONENT_ID = "D005-K-ROUTE-ADJUDICATION-v2"
TYPED_VERSION = b"typed-distinct-source-value-set-v1"
CANONICAL_VERSION = b"canonical-exact-nonnull-route-value-set-v1"
MAPPING_VERSION = b"source-specific-exact-route-mapping-v2"
DECISION_CODE = {"unknown": b"\x00", "iv": b"\x01", "noniv": b"\x02"}
ROUTE_STATE_CODE = {"missing": b"\x00", "unknown": b"\x01", "iv": b"\x02", "noniv": b"\x03"}
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
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
TIME_RE = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z\Z"
)
ALLOWED_BASES = {
    "explicit_iv_route_semantics",
    "explicit_noniv_route_semantics",
    "ambiguous_or_insufficient_route_semantics",
    "other_documented_human_judgment",
}
MAX_BYTES = 16 * 1024 * 1024
BUNDLE_ENCODING = "uint32be_path_length+path_utf8+uint64be_content_length+content"
MAPPING_LIMITATIONS = (
    "This structurally validated private mapping is not formally frozen and "
    "does not unlock Query 202. Human clinical correctness is not established "
    "by compilation or audit."
)
PUBLIC_PRIVACY = {
    "raw_route_values_emitted": False,
    "per_value_hashes_emitted": False,
    "patient_or_event_data_emitted": False,
}
MAPPING_HASH_CONTRACT = {
    "version": MAPPING_VERSION.decode("ascii"),
    "route_state_encoding": "missing=0x00,unknown=0x01,iv=0x02,noniv=0x03",
    "frequency_included": False,
}
CONFIG_FALSE_GUARDS = {
    "route_review_template_created": False,
    "human_route_review_complete": False,
    **FALSE_GUARDS,
}


class AuditError(RuntimeError):
    pass


class Checks:
    def __init__(self) -> None:
        self.total = 0
        self.failed: list[str] = []
        self.by_category: Counter[str] = Counter()

    def check(self, category: str, name: str, condition: bool) -> None:
        self.total += 1
        self.by_category[category] += 1
        if not condition and name not in self.failed:
            self.failed.append(name)


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


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise AuditError(label + ".regular_bounded_file")
    raw = path.read_bytes()

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AuditError(label + ".duplicate_json_key")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except AuditError:
        raise
    except Exception as exc:
        raise AuditError(label + ".valid_json") from exc
    if not isinstance(value, dict):
        raise AuditError(label + ".object")
    return value, raw


def _write_private(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _replace_private(path: Path, payload: bytes) -> None:
    """Atomically persist a deterministic re-audit without following symlinks."""
    if path.is_symlink() or (path.exists() and (not path.is_file() or _mode(path) != "0600")):
        raise AuditError("audit.output_safety")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".audit-summary.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _bundle_report(root: Path, paths: Sequence[str]) -> dict[str, Any]:
    digest = hashlib.sha256()
    files: list[dict[str, Any]] = []
    for relative_text in paths:
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise AuditError("implementation.path")
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise AuditError("implementation.file")
        name = relative_text.encode("utf-8")
        content = path.read_bytes()
        digest.update(struct.pack(">I", len(name)))
        digest.update(name)
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
        "encoding": BUNDLE_ENCODING,
    }


def _bundle(root: Path, paths: Sequence[str]) -> str:
    return _bundle_report(root, paths)["bundle_sha256"]


def _strict_utc_iso(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(None)


def _artifacts_are_git_ignored(root: Path) -> bool:
    try:
        lines = [line.strip() for line in (root / ".gitignore").read_text().splitlines()]
    except (OSError, UnicodeError):
        return False
    try:
        pattern_index = lines.index("artifacts/*")
    except ValueError:
        return False
    later_negations = {
        line for line in lines[pattern_index + 1 :] if line.startswith("!artifacts/")
    }
    return later_negations <= {"!artifacts/.gitkeep"}


def _typed_hash(field: str, records: Sequence[Mapping[str, Any]]) -> str:
    null_seen = False
    nonnull: list[bytes] = []
    for record in records:
        is_null = record.get("raw_is_null")
        raw = record.get("raw_value")
        count = record.get("exact_row_count")
        if type(count) is not int or not 1 <= count < (1 << 63):
            raise AuditError("preflight.frequency")
        if is_null is True and raw is None:
            if null_seen:
                raise AuditError("preflight.duplicate_null")
            null_seen = True
        elif is_null is False and isinstance(raw, str):
            encoded = raw.encode("utf-8")
            if b"\x00" in encoded or len(encoded) > 65_535:
                raise AuditError("preflight.value_bytes")
            expected = "empty_string" if raw == "" else "whitespace_only" if raw.isspace() else "nonblank"
            if record.get("raw_utf8_bytes") != len(encoded) or record.get("nonnull_substate") != expected:
                raise AuditError("preflight.value_metadata")
            nonnull.append(encoded)
        else:
            raise AuditError("preflight.typed_state")
    if len(nonnull) != len(set(nonnull)):
        raise AuditError("preflight.duplicate_nonnull")
    field_bytes = field.encode("utf-8")
    digest = hashlib.sha256()
    digest.update(TYPED_VERSION)
    digest.update(struct.pack(">I", len(field_bytes)))
    digest.update(field_bytes)
    digest.update(struct.pack(">Q", len(nonnull) + int(null_seen)))
    if null_seen:
        digest.update(b"\x00")
    for encoded in sorted(nonnull):
        digest.update(b"\x01")
        digest.update(struct.pack(">Q", len(encoded)))
        digest.update(encoded)
    return digest.hexdigest()


def _canonical_hash(values: Sequence[str]) -> str:
    raw = sorted(value.encode("utf-8") for value in values)
    if len(raw) != len(set(raw)):
        raise AuditError("canonical.duplicate")
    digest = hashlib.sha256(CANONICAL_VERSION)
    digest.update(struct.pack(">Q", len(raw)))
    for item in raw:
        digest.update(struct.pack(">Q", len(item)))
        digest.update(item)
    return digest.hexdigest()


def _mapping_hash(input_sha: str, entries: Sequence[Mapping[str, Any]]) -> str:
    if SHA_RE.fullmatch(input_sha) is None:
        raise AuditError("mapping.input_hash")

    def key(entry: Mapping[str, Any]) -> tuple[bytes, int, bytes]:
        field = entry.get("source_field")
        state = entry.get("raw_value_state")
        raw = entry.get("exact_raw_value")
        if not isinstance(field, str):
            raise AuditError("mapping.field")
        if state == "sql_null" and raw is None:
            return field.encode("utf-8"), 0, b""
        if state == "nonnull" and isinstance(raw, str):
            return field.encode("utf-8"), 1, raw.encode("utf-8")
        raise AuditError("mapping.key")

    ordered = sorted(entries, key=key)
    if len({key(item) for item in ordered}) != len(ordered):
        raise AuditError("mapping.duplicate_key")
    digest = hashlib.sha256(MAPPING_VERSION)
    digest.update(bytes.fromhex(input_sha))
    digest.update(struct.pack(">Q", len(ordered)))
    for item in ordered:
        field, state, raw = key(item)
        decision = item.get("decision")
        route_state = item.get("route_state")
        if state == 0:
            if decision is not None or route_state != "missing":
                raise AuditError("mapping.null_state")
        elif decision not in DECISION_CODE or route_state != decision:
            raise AuditError("mapping.nonnull_state")
        digest.update(struct.pack(">I", len(field)))
        digest.update(field)
        digest.update(bytes((state,)))
        if state:
            digest.update(struct.pack(">Q", len(raw)))
            digest.update(raw)
        digest.update(ROUTE_STATE_CODE[route_state])
    return digest.hexdigest()


def _safe_child(directory: Path, name: Any, label: str) -> Path:
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise AuditError(label + ".filename")
    path = directory / name
    if path.parent != directory:
        raise AuditError(label + ".path")
    return path


def _load_config(root: Path) -> dict[str, Any]:
    path = root / CONFIG_PATH
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AuditError("config.valid") from exc
    if (
        config.get("schema_version") != 1
        or config.get("component_id") != COMPONENT_ID
        or config.get("status") != "proposed"
        or config.get("execution_status") != "not_executed"
    ):
        raise AuditError("config.component")
    review = config.get("review_contract")
    cardinality = config.get("cardinality")
    boundary = config.get("boundary")
    private = config.get("private_artifact")
    public = config.get("public_artifact")
    guards = config.get("guards")
    if not all(
        isinstance(item, Mapping)
        for item in (review, cardinality, boundary, private, public, guards)
    ):
        raise AuditError("config.contract_sections")
    if (
        review.get("allowed_decisions") != ["iv", "noniv", "unknown"]
        or review.get("default_decision") != "unknown"
        or review.get("allowed_review_statuses") != ["unreviewed", "reviewed"]
        or review.get("sql_null_has_nonnull_decision") is not False
        or review.get("sql_null_route_state") != "missing"
        or review.get("sql_null_sets_has_unknown") is not False
        or review.get("source_specific_overrides_allowed") is not False
    ):
        raise AuditError("config.review_contract")
    if cardinality != {
        "source_specific_typed_memberships": 236,
        "source_specific_nonnull_memberships": 233,
        "source_specific_sql_null_memberships": 3,
        "canonical_exact_nonnull_values": 117,
        "sql_null_requires_human_review": False,
    }:
        raise AuditError("config.cardinality")
    prohibited = (
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
    if any(boundary.get(key) is not False for key in prohibited):
        raise AuditError("config.boundary")
    if guards != CONFIG_FALSE_GUARDS:
        raise AuditError("config.guards")
    if (
        private.get("directory_mode") != "0700"
        or private.get("file_mode") != "0600"
        or private.get("git_ignored_required") is not True
        or public.get("raw_route_values_allowed") is not False
        or public.get("per_value_hashes_allowed") is not False
    ):
        raise AuditError("config.privacy")
    hashes = config.get("implementation_hashes")
    if not isinstance(hashes, Mapping):
        raise AuditError("config.implementation")
    if hashes.get("generator_paths") != list(GENERATOR_PATHS) or hashes.get("auditor_paths") != list(AUDITOR_PATHS):
        raise AuditError("config.bundle_paths")
    generator_bundle = _bundle_report(root, GENERATOR_PATHS)
    auditor_bundle = _bundle_report(root, AUDITOR_PATHS)
    if hashes.get("generator_bundle_sha256") != generator_bundle["bundle_sha256"]:
        raise AuditError("config.generator_hash")
    if hashes.get("auditor_bundle_sha256") != auditor_bundle["bundle_sha256"]:
        raise AuditError("config.auditor_hash")
    config["_audit_config_sha256"] = _sha(path.read_bytes())
    config["_audit_implementation_bundles"] = {
        "generator": generator_bundle,
        "auditor": auditor_bundle,
    }
    return config


def _preflight(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    input_config = config.get("input")
    if not isinstance(input_config, Mapping):
        raise AuditError("config.input")
    relative = Path(str(input_config.get("artifact_directory")))
    if relative.is_absolute() or ".." in relative.parts:
        raise AuditError("preflight.directory")
    directory = root / relative
    if not directory.is_dir() or directory.is_symlink() or _mode(directory) != "0700":
        raise AuditError("preflight.directory_mode")
    loaded: dict[str, tuple[dict[str, Any], bytes]] = {}
    for role in ("manifest", "audit", "private_values", "aggregate_summary"):
        path = _safe_child(directory, input_config.get(role + "_file"), "preflight." + role)
        if _mode(path) != "0600" or _sha_file(path) != input_config.get(role + "_sha256"):
            raise AuditError("preflight." + role + "_integrity")
        loaded[role] = _read_json(path, "preflight." + role)
    if loaded["manifest"][0].get("status") != "complete" or loaded["audit"][0].get("status") != "passed":
        raise AuditError("preflight.acceptance")
    if loaded["audit"][0].get("audit_checks", {}).get("failed") != []:
        raise AuditError("preflight.audit_failures")
    private = loaded["private_values"][0]
    if any(private.get(key) is not False for key in ("route_mapping_created", "external_api_called", "product_identity_decided", "final_source_policy")):
        raise AuditError("preflight.guards")
    sources = private.get("sources")
    configured_sources = config.get("route_source")
    if not isinstance(sources, Mapping) or not isinstance(configured_sources, list):
        raise AuditError("preflight.sources")
    expected_memberships: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    canonical: dict[bytes, str] = {}
    for spec, registered in zip(SOURCE_SPECS, configured_sources, strict=True):
        source_key, source_field, field_role = spec
        if tuple(registered.get(key) for key in ("source_key", "source_field", "field_role")) != spec:
            raise AuditError("config.source_spec")
        source = sources.get(source_key)
        if not isinstance(source, Mapping) or source.get("source_field") != source_field:
            raise AuditError("preflight.source")
        records = source.get("records")
        if not isinstance(records, list):
            raise AuditError("preflight.records")
        observed_hash = _typed_hash(source_field, records)
        if observed_hash != registered.get("typed_set_sha256") or source.get("typed_set_sha256") != observed_hash:
            raise AuditError("preflight.typed_hash")
        if len(records) != registered.get("typed_distinct_values"):
            raise AuditError("preflight.typed_count")
        if sum(item.get("raw_is_null") is False for item in records) != registered.get("nonnull_distinct_values"):
            raise AuditError("preflight.nonnull_count")
        for item in records:
            state = "sql_null" if item["raw_is_null"] else "nonnull"
            raw = item["raw_value"]
            key = (source_field, state, raw)
            expected_memberships[key] = {
                "source_key": source_key,
                "source_field": source_field,
                "field_role": field_role,
                "raw_value_state": state,
                "exact_raw_value": raw,
                "exact_row_count": item["exact_row_count"],
            }
            if raw is not None:
                canonical.setdefault(raw.encode("utf-8"), raw)
    cardinality = config.get("cardinality")
    if (
        len(expected_memberships) != cardinality.get("source_specific_typed_memberships")
        or sum(key[1] == "nonnull" for key in expected_memberships) != cardinality.get("source_specific_nonnull_memberships")
        or sum(key[1] == "sql_null" for key in expected_memberships) != cardinality.get("source_specific_sql_null_memberships")
        or len(canonical) != cardinality.get("canonical_exact_nonnull_values")
    ):
        raise AuditError("preflight.cardinality")
    return {
        "private_sha256": input_config["private_values_sha256"],
        "memberships": expected_memberships,
        "canonical_values": [canonical[key] for key in sorted(canonical)],
        "route_typed_set_sha256": {
            source_key: str(registered["typed_set_sha256"])
            for (source_key, _source_field, _field_role), registered in zip(
                SOURCE_SPECS, configured_sources, strict=True
            )
        },
    }


def _expected_lineage(config: Mapping[str, Any], preflight: Mapping[str, Any]) -> dict[str, Any]:
    input_config = config["input"]
    return {
        "component_id": COMPONENT_ID,
        "rule_version": config["rule_version"],
        "config": str(CONFIG_PATH),
        "config_sha256": config["_audit_config_sha256"],
        "preflight_artifact_directory": input_config["artifact_directory"],
        "preflight_component_id": input_config["preflight_component_id"],
        "preflight_config_sha256": input_config["preflight_config_sha256"],
        "preflight_manifest_sha256": input_config["manifest_sha256"],
        "preflight_audit_sha256": input_config["audit_sha256"],
        "preflight_private_values_sha256": input_config["private_values_sha256"],
        "preflight_aggregate_summary_sha256": input_config["aggregate_summary_sha256"],
        "route_typed_set_sha256": preflight["route_typed_set_sha256"],
    }


def _rebuild_from_review(
    review: Mapping[str, Any], preflight: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, int], bool]:
    reviews = review.get("canonical_reviews")
    nulls = review.get("sql_null_mappings")
    if not isinstance(reviews, list) or not isinstance(nulls, list):
        raise AuditError("review.collections")
    canonical_values = preflight["canonical_values"]
    if len(reviews) != len(canonical_values):
        raise AuditError("review.canonical_count")
    entries: list[dict[str, Any]] = []
    statuses: Counter[str] = Counter()
    seen_memberships: set[tuple[str, str, str | None]] = set()
    for index, (item, raw) in enumerate(zip(reviews, canonical_values, strict=True), start=1):
        if not isinstance(item, Mapping):
            raise AuditError("review.entry")
        if (
            item.get("canonical_review_id") != f"R{index:06d}"
            or item.get("raw_value_state") != "nonnull"
            or item.get("exact_raw_value") != raw
            or item.get("raw_utf8_bytes") != len(raw.encode("utf-8"))
        ):
            raise AuditError("review.exact_key")
        decision = item.get("decision")
        status = item.get("review_status")
        basis = item.get("decision_basis")
        reviewer = item.get("reviewer_id")
        reviewed_at = item.get("reviewed_at_utc")
        if decision not in DECISION_CODE or status not in ("unreviewed", "reviewed"):
            raise AuditError("review.controlled_state")
        if status == "unreviewed":
            if decision != "unknown" or any(value is not None for value in (basis, reviewer, reviewed_at)):
                raise AuditError("review.default_unknown")
            provenance = "default_unknown_unreviewed"
        else:
            if basis not in ALLOWED_BASES or not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer.encode("utf-8")) > 128:
                raise AuditError("review.review_metadata")
            if not isinstance(reviewed_at, str) or TIME_RE.fullmatch(reviewed_at) is None:
                raise AuditError("review.review_time")
            compatible = {
                "iv": {"explicit_iv_route_semantics", "other_documented_human_judgment"},
                "noniv": {"explicit_noniv_route_semantics", "other_documented_human_judgment"},
                "unknown": {"ambiguous_or_insufficient_route_semantics", "other_documented_human_judgment"},
            }
            if basis not in compatible[decision]:
                raise AuditError("review.basis")
            provenance = "human_reviewed_exact_canonical_value"
        statuses[status] += 1
        memberships = item.get("source_memberships")
        if not isinstance(memberships, list) or not memberships:
            raise AuditError("review.memberships")
        for membership in memberships:
            if not isinstance(membership, Mapping):
                raise AuditError("review.membership")
            key = (membership.get("source_field"), "nonnull", raw)
            expected = preflight["memberships"].get(key)
            if expected is None or any(membership.get(k) != expected[k] for k in ("source_key", "source_field", "field_role", "exact_row_count")):
                raise AuditError("review.membership_lineage")
            if key in seen_memberships:
                raise AuditError("review.duplicate_membership")
            seen_memberships.add(key)
            entries.append(
                {
                    **expected,
                    "decision": decision,
                    "route_state": decision,
                    "sets_has_unknown": decision == "unknown",
                    "decision_provenance": provenance,
                    "canonical_review_id": item["canonical_review_id"],
                    "review_status": status,
                    "decision_basis": basis,
                    "reviewer_id": reviewer,
                    "reviewed_at_utc": reviewed_at,
                }
            )
    for item in nulls:
        if not isinstance(item, Mapping):
            raise AuditError("review.null_membership")
        key = (item.get("source_field"), "sql_null", None)
        expected = preflight["memberships"].get(key)
        if expected is None or any(item.get(k) != expected[k] for k in expected):
            raise AuditError("review.null_lineage")
        if (
            item.get("decision") is not None
            or item.get("route_state") != "missing"
            or item.get("sets_has_unknown") is not False
            or item.get("decision_provenance") != "forced_sql_null_policy"
            or key in seen_memberships
        ):
            raise AuditError("review.null_policy")
        seen_memberships.add(key)
        entries.append(
            {
                **expected,
                "decision": None,
                "route_state": "missing",
                "sets_has_unknown": False,
                "decision_provenance": "forced_sql_null_policy",
                "canonical_review_id": None,
                "review_status": "not_required",
                "decision_basis": "forced_sql_null_policy",
                "reviewer_id": None,
                "reviewed_at_utc": None,
            }
        )
    if seen_memberships != set(preflight["memberships"]):
        raise AuditError("review.membership_completeness")
    complete = statuses.get("reviewed", 0) == len(reviews)
    return entries, dict(statuses), complete


def audit_mapping_artifact(directory: Path, root: Path) -> tuple[dict[str, Any], Path]:
    checks = Checks()
    try:
        resolved = directory.resolve(strict=True)
        resolved.relative_to((root / "artifacts").resolve())
        checks.check("filesystem", "artifact.directory_scope", True)
        checks.check("filesystem", "artifact.directory_mode", _mode(directory) == "0700")
        checks.check("privacy", "artifact.git_ignored_scope", _artifacts_are_git_ignored(root))
        config = _load_config(root)
        checks.check("lineage", "config.valid", True)
        preflight = _preflight(root, config)
        checks.check("lineage", "preflight.exact_sets_rebuilt", True)
        expected_lineage = _expected_lineage(config, preflight)
        manifest, manifest_raw = _read_json(directory / "manifest.json", "manifest")
        manifest_keys = {
            "schema_version", "artifact_type", "status", "mapping_status",
            "created_at_utc", "component_lineage", "private_review_path",
            "private_review_sha256", "implementation_bundles", "files",
            "directory_mode", "database_connected", "external_api_called",
            "formal_guards", "limitations",
        }
        checks.check("privacy", "manifest.strict_public_schema", set(manifest) == manifest_keys)
        files = manifest.get("files")
        if not isinstance(files, Mapping):
            raise AuditError("manifest.files")
        checks.check(
            "integrity", "manifest.file_roles",
            set(files) == {"private_mapping", "aggregate_summary"},
        )
        mapping_path = _safe_child(directory, files.get("private_mapping", {}).get("name"), "mapping")
        summary_path = _safe_child(directory, files.get("aggregate_summary", {}).get("name"), "summary")
        mapping, mapping_raw = _read_json(mapping_path, "mapping")
        summary, summary_raw = _read_json(summary_path, "summary")
        mapping_keys = {
            "schema_version", "artifact_type", "created_at_utc", "status",
            "lineage", "private_review_path", "private_review_sha256",
            "canonical_exact_set_sha256", "source_specific_mapping_sha256",
            "mapping_hash_contract", "cardinality", "review_status_counts",
            "human_review_complete", "entries", "formal_guards", "limitations",
        }
        summary_keys = {
            "schema_version", "artifact_type", "status", "component_lineage",
            "private_review_sha256", "private_mapping_sha256",
            "source_specific_mapping_sha256", "canonical_exact_set_sha256",
            "cardinality", "review_status_counts", "human_review_complete",
            "source_summaries", "aggregate_nonnull_decision_counts",
            "aggregate_route_state_counts", "has_unknown_evidence_memberships", "privacy",
            "formal_guards", "limitations",
        }
        checks.check("content", "mapping.strict_schema", set(mapping) == mapping_keys)
        checks.check("privacy", "summary.strict_public_schema", set(summary) == summary_keys)
        checks.check("content", "mapping.schema_version", mapping.get("schema_version") == 1)
        checks.check(
            "content",
            "mapping.artifact_type",
            mapping.get("artifact_type")
            == "potassium_route_source_specific_exact_mapping",
        )
        checks.check("content", "mapping.created_at_utc", _strict_utc_iso(mapping.get("created_at_utc")))
        checks.check(
            "content",
            "mapping.hash_contract",
            mapping.get("mapping_hash_contract") == MAPPING_HASH_CONTRACT,
        )
        checks.check(
            "content", "mapping.limitations", mapping.get("limitations") == MAPPING_LIMITATIONS
        )
        checks.check("filesystem", "manifest.mode", _mode(directory / "manifest.json") == "0600")
        checks.check("filesystem", "mapping.mode", _mode(mapping_path) == "0600")
        checks.check("filesystem", "summary.mode", _mode(summary_path) == "0600")
        checks.check("integrity", "mapping.file_hash", files["private_mapping"].get("sha256") == _sha(mapping_raw))
        checks.check("integrity", "summary.file_hash", files["aggregate_summary"].get("sha256") == _sha(summary_raw))
        review_relative = mapping.get("private_review_path")
        if not isinstance(review_relative, str):
            raise AuditError("mapping.review_path")
        review_path = root / review_relative
        review_path.resolve(strict=True).relative_to((root / "artifacts").resolve())
        review, review_raw = _read_json(review_path, "review")
        checks.check("filesystem", "review.mode", _mode(review_path) == "0600")
        checks.check("integrity", "review.file_hash", mapping.get("private_review_sha256") == _sha(review_raw))
        entries, status_counts, human_complete = _rebuild_from_review(review, preflight)
        checks.check("content", "membership.count", len(entries) == 236)
        checks.check("content", "membership.nonnull", sum(item["raw_value_state"] == "nonnull" for item in entries) == 233)
        checks.check("content", "membership.sql_null", sum(item["raw_value_state"] == "sql_null" for item in entries) == 3)
        checks.check(
            "content", "sql_null.is_missing_not_unknown",
            all(
                item["route_state"] == "missing"
                and item["decision"] is None
                and item["sets_has_unknown"] is False
                for item in entries
                if item["raw_value_state"] == "sql_null"
            ),
        )
        checks.check(
            "content", "nonnull.unknown_evidence_exact",
            all(
                item["sets_has_unknown"] is (item["decision"] == "unknown")
                and item["route_state"] == item["decision"]
                for item in entries
                if item["raw_value_state"] == "nonnull"
            ),
        )
        checks.check("content", "canonical.count", len(review["canonical_reviews"]) == 117)
        checks.check("content", "canonical.hash", review.get("canonical_exact_set_sha256") == _canonical_hash(preflight["canonical_values"]))
        checks.check("content", "mapping.entries", mapping.get("entries") == entries)
        mapping_hash = _mapping_hash(preflight["private_sha256"], entries)
        checks.check("integrity", "mapping.semantic_hash", mapping.get("source_specific_mapping_sha256") == mapping_hash)
        checks.check("content", "review.status_counts", mapping.get("review_status_counts") == status_counts)
        checks.check("content", "review.complete", mapping.get("human_review_complete") is human_complete)
        expected_status = "human_review_complete_unfrozen" if human_complete else "draft_with_unreviewed_defaults"
        checks.check("content", "mapping.status", mapping.get("status") == expected_status)
        checks.check("lineage", "mapping.exact_lineage", mapping.get("lineage") == expected_lineage)
        checks.check("lineage", "review.mapping_lineage", review.get("lineage") == expected_lineage)
        checks.check("lineage", "manifest.mapping_lineage", manifest.get("component_lineage") == expected_lineage)
        checks.check("lineage", "summary.mapping_lineage", summary.get("component_lineage") == expected_lineage)
        checks.check(
            "lineage", "config.hash_lineage",
            expected_lineage.get("config_sha256") == config.get("_audit_config_sha256"),
        )
        checks.check(
            "lineage", "preflight.hash_lineage",
            expected_lineage.get("preflight_private_values_sha256") == preflight["private_sha256"],
        )
        checks.check("guards", "mapping.false_guards", mapping.get("formal_guards") == FALSE_GUARDS)
        checks.check("guards", "manifest.false_guards", manifest.get("formal_guards") == FALSE_GUARDS)
        checks.check("guards", "summary.false_guards", summary.get("formal_guards") == FALSE_GUARDS)
        checks.check("execution", "database.not_used", manifest.get("database_connected") is False)
        checks.check("execution", "external_api.not_used", manifest.get("external_api_called") is False)
        checks.check("privacy", "summary.privacy_contract", summary.get("privacy") == PUBLIC_PRIVACY)
        checks.check("integrity", "summary.private_mapping_hash", summary.get("private_mapping_sha256") == _sha(mapping_raw))
        checks.check("integrity", "summary.mapping_hash", summary.get("source_specific_mapping_sha256") == mapping_hash)
        checks.check("integrity", "summary.review_hash", summary.get("private_review_sha256") == _sha(review_raw))
        checks.check("integrity", "summary.canonical_hash", summary.get("canonical_exact_set_sha256") == review.get("canonical_exact_set_sha256"))
        checks.check("content", "summary.cardinality", summary.get("cardinality") == mapping.get("cardinality"))
        checks.check("content", "summary.status", summary.get("status") == expected_status)
        checks.check("content", "summary.review_counts", summary.get("review_status_counts") == status_counts)
        checks.check("content", "summary.review_complete", summary.get("human_review_complete") is human_complete)
        checks.check(
            "content", "summary.aggregate_nonnull_decisions",
            summary.get("aggregate_nonnull_decision_counts")
            == dict(Counter(item["decision"] for item in entries if item["decision"] is not None)),
        )
        checks.check(
            "content", "summary.aggregate_route_states",
            summary.get("aggregate_route_state_counts")
            == dict(Counter(item["route_state"] for item in entries)),
        )
        checks.check(
            "content", "summary.has_unknown_evidence",
            summary.get("has_unknown_evidence_memberships")
            == sum(item["sets_has_unknown"] is True for item in entries),
        )
        expected_source_summaries: dict[str, dict[str, Any]] = {}
        for source_key, source_field, field_role in SOURCE_SPECS:
            subset = [item for item in entries if item["source_key"] == source_key]
            expected_source_summaries[source_key] = {
                "source_field": source_field,
                "field_role": field_role,
                "typed_memberships": len(subset),
                "nonnull_memberships": sum(item["raw_value_state"] == "nonnull" for item in subset),
                "sql_null_memberships": sum(item["raw_value_state"] == "sql_null" for item in subset),
                "nonnull_decision_counts": dict(
                    Counter(item["decision"] for item in subset if item["decision"] is not None)
                ),
                "route_state_counts": dict(Counter(item["route_state"] for item in subset)),
                "has_unknown_evidence_memberships": sum(
                    item["sets_has_unknown"] is True for item in subset
                ),
            }
        checks.check("content", "summary.source_summaries", summary.get("source_summaries") == expected_source_summaries)
        expected_summary = {
            "schema_version": 1,
            "artifact_type": "potassium_route_mapping_aggregate_summary",
            "status": expected_status,
            "component_lineage": expected_lineage,
            "private_review_sha256": _sha(review_raw),
            "private_mapping_sha256": _sha(mapping_raw),
            "source_specific_mapping_sha256": mapping_hash,
            "canonical_exact_set_sha256": review.get("canonical_exact_set_sha256"),
            "cardinality": mapping.get("cardinality"),
            "review_status_counts": status_counts,
            "human_review_complete": human_complete,
            "source_summaries": expected_source_summaries,
            "aggregate_nonnull_decision_counts": dict(
                Counter(item["decision"] for item in entries if item["decision"] is not None)
            ),
            "aggregate_route_state_counts": dict(
                Counter(item["route_state"] for item in entries)
            ),
            "has_unknown_evidence_memberships": sum(
                item["sets_has_unknown"] is True for item in entries
            ),
            "privacy": PUBLIC_PRIVACY,
            "formal_guards": dict(FALSE_GUARDS),
            "limitations": MAPPING_LIMITATIONS,
        }
        checks.check(
            "privacy", "summary.complete_public_contract", summary == expected_summary
        )
        checks.check("lineage", "manifest.component", manifest.get("component_lineage", {}).get("component_id") == COMPONENT_ID)
        checks.check("lineage", "mapping.component", mapping.get("lineage", {}).get("component_id") == COMPONENT_ID)
        checks.check("lineage", "summary.component", summary.get("component_lineage", {}).get("component_id") == COMPONENT_ID)
        checks.check("integrity", "manifest.status", manifest.get("status") == "complete")
        checks.check("integrity", "manifest.mapping_status", manifest.get("mapping_status") == expected_status)
        checks.check("integrity", "manifest.review_hash", manifest.get("private_review_sha256") == _sha(review_raw))
        bundles = manifest.get("implementation_bundles")
        checks.check(
            "integrity", "manifest.implementation_bundles",
            bundles == config["_audit_implementation_bundles"],
        )
        expected_files = {
            "private_mapping": {
                "name": mapping_path.name,
                "sha256": _sha(mapping_raw),
                "bytes": len(mapping_raw),
                "mode": "0600",
            },
            "aggregate_summary": {
                "name": summary_path.name,
                "sha256": _sha(summary_raw),
                "bytes": len(summary_raw),
                "mode": "0600",
            },
        }
        checks.check("integrity", "manifest.file_metadata", files == expected_files)
        expected_manifest = {
            "schema_version": 1,
            "artifact_type": "potassium_route_mapping_manifest",
            "status": "complete",
            "mapping_status": expected_status,
            "component_lineage": expected_lineage,
            "private_review_path": mapping.get("private_review_path"),
            "private_review_sha256": _sha(review_raw),
            "implementation_bundles": config["_audit_implementation_bundles"],
            "files": expected_files,
            "directory_mode": "0700",
            "database_connected": False,
            "external_api_called": False,
            "formal_guards": dict(FALSE_GUARDS),
            "limitations": MAPPING_LIMITATIONS,
        }
        manifest_without_time = dict(manifest)
        manifest_created_at = manifest_without_time.pop("created_at_utc", None)
        checks.check("integrity", "manifest.created_at_utc", _strict_utc_iso(manifest_created_at))
        checks.check(
            "privacy",
            "manifest.complete_public_contract",
            manifest_without_time == expected_manifest,
        )
        checks.check("privacy", "manifest.has_no_entry_payload", "entries" not in manifest and "canonical_reviews" not in manifest)
        checks.check("privacy", "summary.has_no_entry_payload", "entries" not in summary and "canonical_reviews" not in summary)
        checks.check("integrity", "manifest.hash_recorded", SHA_RE.fullmatch(_sha(manifest_raw)) is not None)
    except (AuditError, OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        checks.check("fatal", str(exc) if isinstance(exc, AuditError) else "audit.structural_error", False)
        human_complete = False
        mapping_hash = None
        manifest_raw = b""
        mapping_raw = b""
        summary_raw = b""
    passed = not checks.failed
    result = {
        "schema_version": 1,
        "audit": "potassium_route_mapping_independent_offline_audit",
        "status": "passed" if passed else "failed",
        "audit_checks": {
            "total": checks.total,
            "passed": checks.total - len(checks.failed),
            "failed": checks.failed,
            "by_category": dict(checks.by_category),
        },
        "input_integrity": {
            "manifest_sha256": _sha(manifest_raw) if manifest_raw else None,
            "private_mapping_sha256": _sha(mapping_raw) if mapping_raw else None,
            "aggregate_summary_sha256": _sha(summary_raw) if summary_raw else None,
            "source_specific_mapping_sha256": mapping_hash,
        },
        "content_contract": {
            "source_specific_typed_memberships_checked": 236 if passed else None,
            "canonical_exact_nonnull_values_checked": 117 if passed else None,
            "human_review_complete": human_complete if passed else None,
            "default_unknown_and_review_metadata_checked": passed,
            "source_roles_and_frequencies_checked": passed,
        },
        "execution_contract": {
            "database_connection_used": False,
            "external_api_used": False,
        },
        "privacy": {
            "raw_route_values_emitted": False,
            "per_value_hashes_emitted": False,
            "patient_or_event_data_emitted": False,
        },
        "formal_guards": dict(FALSE_GUARDS),
        "limitations": (
            "A passing audit verifies exact-set lineage, structural human-review "
            "provenance, mapping expansion, hashes, modes and false guards. It does "
            "not validate clinical route judgments, freeze the map or unlock Query 202."
        ),
    }
    output = directory / "audit-summary.json"
    _replace_private(output, (json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
    return result, output


__all__ = ["audit_mapping_artifact"]
