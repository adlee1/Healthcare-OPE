"""Machine report for the proposed D005 exact route-adjudication workflow."""
from __future__ import annotations

from pathlib import Path
import re
import tomllib
from typing import Any, Mapping

from .route_adjudication import (
    ALLOWED_DECISIONS,
    COMPONENT_ID,
    CONFIG_PATH,
    FALSE_GUARDS,
    RouteAdjudicationError,
    _load_config,
    _validate_preflight,
)


SHA_RE = re.compile(r"[0-9a-f]{64}\Z")


def read_potassium_route_adjudication_preregistration(root: Path) -> dict[str, Any]:
    with (root / CONFIG_PATH).open("rb") as handle:
        return tomllib.load(handle)


def validate_potassium_route_adjudication_preregistration(
    config: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []

    def expect(table: Any, key: str, value: Any, section: str) -> None:
        if not isinstance(table, Mapping) or table.get(key) != value:
            errors.append(f"{section}.{key} changed")

    expect(config, "schema_version", 1, "root")
    expect(config, "component_id", COMPONENT_ID, "root")
    expect(config, "status", "proposed", "root")
    expect(config, "execution_status", "not_executed", "root")
    review = config.get("review_contract")
    for key, value in {
        "allowed_decisions": list(ALLOWED_DECISIONS),
        "default_decision": "unknown",
        "sql_null_has_nonnull_decision": False,
        "sql_null_route_state": "missing",
        "sql_null_sets_has_unknown": False,
        "source_specific_overrides_allowed": False,
    }.items():
        expect(review, key, value, "review_contract")
    cardinality = config.get("cardinality")
    for key, value in {
        "source_specific_typed_memberships": 236,
        "source_specific_nonnull_memberships": 233,
        "source_specific_sql_null_memberships": 3,
        "canonical_exact_nonnull_values": 117,
        "sql_null_requires_human_review": False,
    }.items():
        expect(cardinality, key, value, "cardinality")
    hashing = config.get("mapping_hash_contract")
    for key, value in {
        "version": "source-specific-exact-route-mapping-v2",
        "entry_key": [
            "source_field",
            "raw_value_state",
            "exact_raw_value_when_nonnull",
        ],
        "route_state_encoding": "missing=0x00, unknown=0x01, iv=0x02, noniv=0x03",
        "includes_route_state": True,
        "per_value_hash_publication_allowed": False,
    }.items():
        expect(hashing, key, value, "mapping_hash_contract")
    boundary = config.get("boundary")
    for key in (
        "database_access_allowed",
        "external_api_allowed",
        "product_or_event_mapping_allowed",
        "source_policy_decision_allowed",
        "formal_action_episode_label_or_cohort_allowed",
        "automatic_lexical_or_fuzzy_classification_allowed",
        "normalization_allowed",
        "query202_unlock_allowed",
        "formal_route_mapping_freeze_allowed",
    ):
        expect(boundary, key, False, "boundary")
    guards = config.get("guards")
    if not isinstance(guards, Mapping):
        errors.append("guards must be a table")
    else:
        for key, value in FALSE_GUARDS.items():
            expect(guards, key, value, "guards")
    input_config = config.get("input")
    if not isinstance(input_config, Mapping):
        errors.append("input must be a table")
    else:
        path = input_config.get("artifact_directory")
        if (
            not isinstance(path, str)
            or Path(path).is_absolute()
            or ".." in Path(path).parts
        ):
            errors.append("input.artifact_directory must be project-relative")
        for key in (
            "manifest_sha256",
            "audit_sha256",
            "private_values_sha256",
            "aggregate_summary_sha256",
            "preflight_config_sha256",
        ):
            if SHA_RE.fullmatch(str(input_config.get(key))) is None:
                errors.append(f"input.{key} must be a lowercase SHA-256")
    implementation = config.get("implementation_hashes")
    if not isinstance(implementation, Mapping):
        errors.append("implementation_hashes must be a table")
    else:
        for key in ("generator_bundle_sha256", "auditor_bundle_sha256"):
            if SHA_RE.fullmatch(str(implementation.get(key))) is None:
                errors.append(f"implementation_hashes.{key} must be a lowercase SHA-256")
    return errors


def potassium_route_adjudication_preregistration_report(root: Path) -> dict[str, Any]:
    config = read_potassium_route_adjudication_preregistration(root)
    errors = validate_potassium_route_adjudication_preregistration(config)
    report: dict[str, Any] | None = None
    preflight_checked = False
    try:
        report = _load_config(root)
        _validate_preflight(root, report["data"])
        preflight_checked = True
    except (RouteAdjudicationError, OSError, ValueError) as exc:
        errors.append(str(exc))
    guards = config.get("guards", {})
    return {
        "component_id": config.get("component_id"),
        "status": config.get("status"),
        "execution_status": config.get("execution_status"),
        "config": str(CONFIG_PATH),
        "config_sha256": report.get("config_sha256") if report else None,
        "valid": not errors,
        "errors": errors,
        "warnings": [],
        "implementation_hashes_verified": report is not None,
        "implementation_bundles": report.get("implementation_bundles", {}) if report else {},
        "preflight_exact_sets_verified": preflight_checked,
        "canonical_exact_nonnull_values": config.get("cardinality", {}).get(
            "canonical_exact_nonnull_values"
        ),
        "source_specific_typed_memberships": config.get("cardinality", {}).get(
            "source_specific_typed_memberships"
        ),
        "sql_null_route_state": config.get("review_contract", {}).get(
            "sql_null_route_state"
        ),
        "human_route_review_complete": guards.get("human_route_review_complete"),
        "route_mapping_frozen": guards.get("route_mapping_frozen"),
        "query202_unlocked": guards.get("query202_unlocked"),
        "database_connected": False,
        "external_api_called": False,
    }


__all__ = [
    "potassium_route_adjudication_preregistration_report",
    "read_potassium_route_adjudication_preregistration",
    "validate_potassium_route_adjudication_preregistration",
]
