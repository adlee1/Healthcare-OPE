"""Machine validation for the split D005 Query 202 lifecycles.

The original all-in-one architecture is retained only as a superseded record.
Neither replacement component is executable: this module validates architecture
and existing evidence, never promotes placeholders into an execution gate.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tomllib

from .query202_contract import QUERY202_BUCKET_COUNT, validate_query202_bucket_indices


POTASSIUM_QUERY202_EXTRACTION_PATH = Path(
    "config/preregistrations/d005_potassium_query202_extraction.toml"
)
POTASSIUM_QUERY202_PRE_ADJUDICATION_PATH = Path(
    "config/preregistrations/d005_potassium_query202_pre_adjudication.toml"
)
POTASSIUM_QUERY202_MAPPED_EVENT_APPLICATION_PATH = Path(
    "config/preregistrations/d005_potassium_query202_mapped_event_application.toml"
)

_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PLACEHOLDER = "UNSET_REQUIRED_BEFORE_EXECUTION"
_EXPECTED_ROUTE_CONFIG_SHA256 = (
    "447a89548d21da739fb386fbcacab31f746747d5960386071a648009c1001e57"
)
_EXPECTED_ROUTE_FIELDS = [
    "mimiciv_hosp.emar_detail.route",
    "mimiciv_hosp.pharmacy.route",
    "mimiciv_hosp.prescriptions.route",
]
_EXPECTED_ROUTE_HASHES = [
    "a3b0d5664ae2e89f08df97f45347a6d7ae7761cdb2d138da781681ed2edd0ea9",
    "2dad858bbbd41002d3a417faa302bda9bd0f85111d47cbd075a0802886ebd76b",
    "b75209f1e0acea76a8c9818936b389a972def151317ede76073fc51dd65f1c0e",
]
_EXPECTED_ROUTE_TYPED_COUNTS = [18, 109, 109]
_EXPECTED_ROUTE_NONNULL_COUNTS = [17, 108, 108]

# Canonical TOML-object locks. These cover every architecture field while the
# explicit checks below give useful errors for the scientific invariants.
_EXPECTED_CANONICAL_SHA256 = {
    "superseded": "a0fa88868ba37f0574f547366d6472502cf8611c429884e64da574282d6150ea",
    "pre_adjudication": "107bfc6197203fb0ddf835c56972894d11ff51d47202a4e1c3cf8d797092f708",
    "mapped_application": "54c1b5a83363c681942debe7f7ba753268ec03b25e353365215374ddb8582892",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(config: dict) -> str:
    payload = json.dumps(
        config, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read(root: Path, relative: Path) -> dict:
    with (root / relative).open("rb") as handle:
        return tomllib.load(handle)


def read_potassium_query202_extraction_preregistration(root: Path) -> dict:
    """Read the superseded single-lifecycle record."""
    return _read(root, POTASSIUM_QUERY202_EXTRACTION_PATH)


def read_potassium_query202_pre_adjudication_preregistration(root: Path) -> dict:
    return _read(root, POTASSIUM_QUERY202_PRE_ADJUDICATION_PATH)


def read_potassium_query202_mapped_event_application_preregistration(
    root: Path,
) -> dict:
    return _read(root, POTASSIUM_QUERY202_MAPPED_EVENT_APPLICATION_PATH)


def _validate_false_guards(config: dict, errors: list[str]) -> None:
    guards = config.get("guards")
    if not isinstance(guards, dict) or not guards:
        errors.append("guards must be a nonempty table")
        return
    enabled = sorted(key for key, value in guards.items() if value is not False)
    if enabled:
        errors.append(f"all formal and execution guards must remain false: {enabled}")


def _validate_safe_evidence(config: dict, errors: list[str]) -> None:
    evidence = config.get("evidence")
    if not isinstance(evidence, list):
        errors.append("evidence must be an array of tables")
        return
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            errors.append(f"evidence[{index}] must be a table")
            continue
        relative = item.get("path")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            errors.append(f"evidence[{index}].path must be safe and project-relative")
        digest = item.get("file_sha256")
        if not isinstance(digest, str) or not _HEX_SHA256.fullmatch(digest):
            errors.append(f"evidence[{index}].file_sha256 must be lowercase SHA-256")


def _validate_transaction(
    transaction: object,
    snapshot_key: str,
    timeout_scope_key: str,
    errors: list[str],
) -> None:
    if not isinstance(transaction, dict):
        errors.append("transaction must be a table")
        return
    expected = {
        "transaction_isolation": "repeatable read",
        "transaction_read_only": True,
        snapshot_key: True,
        "statement_timeout_ms": 120000,
        timeout_scope_key: True,
        "explicit_rollback_required": True,
        "clean_psql_exit_required": True,
        "database_mutation_allowed": False,
        "temporary_tables_allowed": False,
        "temporary_views_allowed": False,
        "indexes_allowed": False,
        "functions_or_procedures_allowed": False,
        "session_database_objects_allowed": False,
        "artifacts_persist_only_after_rollback_and_clean_exit": True,
        "any_statement_timeout_or_failure_discards_entire_run": True,
        "cross_lifecycle_same_snapshot_claim_allowed": False,
    }
    for key, value in expected.items():
        if transaction.get(key) != value:
            errors.append(f"transaction.{key} must be {value!r}")


def _validate_architecture_root(
    config: dict, component_id: str, rule_version: str, errors: list[str]
) -> None:
    expected = {
        "schema_version": 1,
        "component_id": component_id,
        "decision_id": "D005",
        "status": "proposed",
        "rule_version": rule_version,
        "specified_on": "2026-10-12",
        "execution_status": "not_executed",
        "execution_permitted": False,
        "implementation_state": "architecture_only",
        "author_setting_recovered": False,
        "formal_product_mapping_enabled": False,
        "formal_source_policy_enabled": False,
    }
    for key, value in expected.items():
        if config.get(key) != value:
            errors.append(f"root.{key} must be {value!r}")


def _validate_bucket_plan(config: dict, expected_stages: list[str], errors: list[str]) -> None:
    plan = config.get("bucket_plan")
    if not isinstance(plan, dict):
        errors.append("bucket_plan must be a table")
        return
    if plan.get("bucket_count") != QUERY202_BUCKET_COUNT:
        errors.append("bucket_plan.bucket_count must be 64")
    try:
        validate_query202_bucket_indices(plan.get("bucket_indices", []))
    except ValueError as exc:
        errors.append(str(exc))
    if plan.get("bucketed_stages") != expected_stages:
        errors.append(f"bucket_plan.bucketed_stages must be {expected_stages!r}")
    if plan.get("all_indices_required_once") is not True:
        errors.append("bucket_plan.all_indices_required_once must be true")


def _validate_architecture_only_implementation(config: dict, errors: list[str]) -> None:
    implementation = config.get("implementation")
    if not isinstance(implementation, dict):
        errors.append("implementation must be a table")
        return
    if implementation.get("state") != "architecture_only":
        errors.append("implementation.state must be architecture_only")
    for key in ("sql_bundle_sha256", "runner_bundle_sha256", "auditor_bundle_sha256"):
        if implementation.get(key) != _PLACEHOLDER:
            errors.append(f"implementation.{key} must remain unset")
    for key in ("planned_sql_paths", "planned_runner_paths", "planned_auditor_paths"):
        paths = implementation.get(key)
        if not isinstance(paths, list) or not paths:
            errors.append(f"implementation.{key} must list future project-relative paths")
        elif any(
            not isinstance(value, str)
            or not value
            or Path(value).is_absolute()
            or ".." in Path(value).parts
            for value in paths
        ):
            errors.append(f"implementation.{key} contains an unsafe path")


def validate_potassium_query202_extraction_preregistration(config: dict) -> list[str]:
    """Validate that the old component is inert and explicitly superseded."""
    errors: list[str] = []
    expected = {
        "schema_version": 1,
        "component_id": "D005-K-QUERY202-EXTRACTION-v1",
        "decision_id": "D005",
        "status": "superseded",
        "execution_status": "never_executed",
        "execution_permitted": False,
        "formal_product_mapping_enabled": False,
        "formal_source_policy_enabled": False,
        "cross_lifecycle_same_snapshot_claim_allowed": False,
    }
    for key, value in expected.items():
        if config.get(key) != value:
            errors.append(f"root.{key} must be {value!r}")
    if config.get("superseded_by") != [
        "D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v1",
        "D005-K-QUERY202-MAPPED-EVENT-APPLICATION-v1",
    ]:
        errors.append("superseded_by must name the two replacement lifecycles")
    _validate_false_guards(config, errors)
    if _canonical_sha256(config) != _EXPECTED_CANONICAL_SHA256["superseded"]:
        errors.append("superseded Query 202 record differs from its v1 lock")
    return errors


def validate_potassium_query202_pre_adjudication_preregistration(
    config: dict,
) -> list[str]:
    """Validate lifecycle A without treating it as implemented or executable."""
    errors: list[str] = []
    _validate_architecture_root(
        config,
        "D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v1",
        "k-query202-pre-adjudication-evidence-v1-proposed",
        errors,
    )
    lifecycle = config.get("lifecycle", {})
    if lifecycle.get("reviewed_semantic_ledger_is_input") is not False:
        errors.append("lifecycle A cannot require the reviewed semantic ledger")
    if lifecycle.get("frozen_route_mapping_is_input") is not False:
        errors.append("lifecycle A cannot require the frozen route mapping")
    if lifecycle.get("same_snapshot_with_post_adjudication_lifecycle_claim_allowed") is not False:
        errors.append("lifecycle A cannot claim a shared snapshot with lifecycle B")
    upstream = config.get("upstream_boundaries", {})
    if (
        upstream.get("query201_source_field_memberships") != 33723
        or upstream.get("product_description_other_nonnull_exact_values") != 842
        or upstream.get("semantic_seed_expected_keys") != 34565
    ):
        errors.append("lifecycle A semantic seed must be 33,723 + 842 = 34,565 keys")
    if upstream.get("query201_expected_nonnull_distinct_counts") != [
        5045, 6692, 11059, 10927
    ] or upstream.get("query201_exact_set_match_required_per_source_field") is not True:
        errors.append("Query 201 four-field exact boundary replay is not locked")
    for key in (
        "query200_is_candidate_ceiling",
        "query200_only_filter_allowed",
    ):
        if upstream.get(key) is not False:
            errors.append(f"upstream_boundaries.{key} must be false")
    for key in (
        "q201_values_outside_query200_must_be_retained",
        "all_product_description_other_values_must_be_retained",
        "query200_null_description_local_code_evidence_must_be_retained",
    ):
        if upstream.get(key) is not True:
            errors.append(f"upstream_boundaries.{key} must be true")
    _validate_transaction(
        config.get("transaction"),
        "all_pre_adjudication_sql_statements_share_one_snapshot",
        "per_statement_timeout_applies_to_every_unpartitioned_and_partitioned_sql",
        errors,
    )
    stages = config.get("stages", {})
    if list(stages) != ["202a", "202b", "202c"]:
        errors.append("lifecycle A stages must be exactly 202a, 202b and 202c")
    if stages.get("202b", {}).get("selection_may_use_query200_scope") is not False:
        errors.append("202b cannot use Query 200 as a filter")
    for key in (
        "nonnull_emar_medication_heads_partition_into_with_detail_and_no_detail",
        "emar_medication_to_detail_bridge_required",
    ):
        if stages.get("202b", {}).get(key) is not True:
            errors.append(f"stages.202b.{key} must be true")
    if stages.get("202c", {}).get("selection_may_use_query200_scope") is not False:
        errors.append("202c cannot use Query 200 as a filter")
    for key in (
        "head_pharmacy_prescription_bridge_required",
        "detail_pharmacy_prescription_bridge_required",
        "head_and_detail_pharmacy_keys_are_separate_link_paths",
    ):
        if stages.get("202c", {}).get(key) is not True:
            errors.append(f"stages.202c.{key} must be true")
    if stages.get("202c", {}).get("head_and_detail_pharmacy_keys_may_be_coalesced") is not False:
        errors.append("head and detail pharmacy-key paths cannot be coalesced")
    lineage = config.get("semantic_seed_lineage", {})
    if (
        lineage.get("expected_key_count") != 34565
        or lineage.get("later_reviewed_ledger_may_add_or_drop_keys") is not False
        or lineage.get("sql_null_creates_semantic_seed_key") is not False
    ):
        errors.append("semantic seed-to-reviewed-ledger key conservation is not locked")
    ndc_handoff = config.get("external_ndc_handoff", {})
    if ndc_handoff.get("private_ndc_export_required_after_success") is not True:
        errors.append("private NDC export must be required after successful extraction")
    if ndc_handoff.get("private_ndc_export_created") is not False:
        errors.append("not-executed lifecycle A cannot claim an NDC export exists")
    merge = config.get("offline_merge", {})
    if merge.get("uses_typed_exact_tuple_k_way_merge_across_all_preregistered_partitions") is not True:
        errors.append("offline merge must cover every preregistered partition")
    if merge.get("partition_set_or_frequency_hashes_may_be_added_concatenated_or_used_as_global_hash") is not False:
        errors.append("partition hashes cannot be added or concatenated into a global hash")
    route = config.get("route_boundary_reference", {})
    if (
        route.get("route_fields") != _EXPECTED_ROUTE_FIELDS
        or route.get("expected_typed_set_sha256") != _EXPECTED_ROUTE_HASHES
        or route.get("expected_typed_distinct_counts") != _EXPECTED_ROUTE_TYPED_COUNTS
        or route.get("expected_nonnull_distinct_counts") != _EXPECTED_ROUTE_NONNULL_COUNTS
    ):
        errors.append("route boundary reference differs from the audited preflight")
    auxiliary = config.get("auxiliary_boundary_reference", {})
    if (
        auxiliary.get("source_fields")
        != [
            "mimiciv_hosp.emar_detail.product_description_other",
            "mimiciv_hosp.prescriptions.ndc",
        ]
        or auxiliary.get("expected_typed_set_sha256")
        != [
            "0105f73cef307cc11b93e1d9d657d43a278c66c3c06ef31e5123db377e11dd4e",
            "10e5ff7bb578ca66aadfe274105ed94a53487ba05d7b80e0ebca8fb8c24bab9e",
        ]
        or auxiliary.get("expected_typed_distinct_counts") != [843, 6590]
        or auxiliary.get("expected_nonnull_distinct_counts") != [842, 6589]
    ):
        errors.append("PDO/NDC typed boundaries differ from the audited preflight")
    outputs = config.get("private_outputs")
    if not isinstance(outputs, list) or [item.get("name") for item in outputs] != [
        "typed_boundary_replay",
        "semantic_key_seed",
        "detail_product_crosswalk",
        "detail_seed_membership_bridge",
        "emar_medication_detail_bridge",
        "pharmacy_order_crosswalk",
        "prescription_component_crosswalk",
        "pharmacy_prescription_bridge",
        "head_pharmacy_prescription_bridge",
        "detail_pharmacy_prescription_bridge",
        "ndc_external_mapping_input",
    ]:
        errors.append("lifecycle A must retain the exact eleven private evidence outputs")
    partition = config.get("partition_plan", {})
    if partition.get("status") != "unfrozen":
        errors.append("lifecycle A partition plan must remain explicitly unfrozen")
    for key in ("assignment_unit", "partition_count", "assignment_expression"):
        if partition.get(key) != _PLACEHOLDER:
            errors.append(f"partition_plan.{key} must remain unset")
    if partition.get("partition_plan_requires_new_component_version_before_implementation") is not True:
        errors.append("lifecycle A needs a new component version before partition implementation")
    if partition.get("mapped_event_application_64_bucket_plan_may_be_reused_implicitly") is not False:
        errors.append("lifecycle A cannot implicitly inherit lifecycle B's 64 buckets")
    _validate_architecture_only_implementation(config, errors)
    _validate_false_guards(config, errors)
    _validate_safe_evidence(config, errors)
    if _canonical_sha256(config) != _EXPECTED_CANONICAL_SHA256["pre_adjudication"]:
        errors.append("pre-adjudication architecture differs from its v1 lock")
    return errors


def validate_potassium_query202_mapped_event_application_preregistration(
    config: dict,
) -> list[str]:
    """Validate lifecycle B while all frozen-input and implementation gates are shut."""
    errors: list[str] = []
    _validate_architecture_root(
        config,
        "D005-K-QUERY202-MAPPED-EVENT-APPLICATION-v1",
        "k-query202-mapped-event-application-v1-proposed",
        errors,
    )
    lifecycle = config.get("lifecycle", {})
    for key in (
        "requires_completed_independently_audited_predecessor",
        "requires_frozen_reviewed_semantic_ledger",
        "requires_frozen_route_mapping_v2",
        "uses_new_repeatable_read_read_only_snapshot",
    ):
        if lifecycle.get(key) is not True:
            errors.append(f"lifecycle.{key} must be true")
    for key in (
        "same_snapshot_with_pre_adjudication_lifecycle_claim_allowed",
        "cross_lifecycle_row_count_equality_implies_same_snapshot",
    ):
        if lifecycle.get(key) is not False:
            errors.append(f"lifecycle.{key} must be false")
    _validate_transaction(
        config.get("transaction"),
        "all_post_adjudication_sql_statements_share_one_snapshot",
        "per_statement_timeout_applies_to_every_unsharded_and_bucketed_sql",
        errors,
    )
    frozen = config.get("frozen_input_contract", {})
    placeholder_keys = [
        key
        for key in frozen
        if key.endswith("_path") or key.endswith("_sha256") or key == "external_ndc_evidence_mode"
    ]
    if any(frozen.get(key) != _PLACEHOLDER for key in placeholder_keys):
        errors.append("lifecycle B frozen input paths, hashes and mode must remain unset")
    if frozen.get("reviewed_semantic_ledger_expected_keys") != 34565:
        errors.append("lifecycle B must require the reviewed 34,565-key ledger")
    if frozen.get("reviewed_semantic_ledger_review_complete") is not False:
        errors.append("reviewed semantic ledger cannot be claimed complete")
    if frozen.get("reviewed_semantic_ledger_frozen") is not False:
        errors.append("reviewed semantic ledger cannot be claimed frozen")
    if frozen.get("route_mapping_review_complete") is not False:
        errors.append("route mapping cannot be claimed complete")
    if frozen.get("route_mapping_frozen") is not False:
        errors.append("route mapping cannot be claimed frozen")
    route = config.get("route_mapping_dependency", {})
    if (
        route.get("component_id") != "D005-K-ROUTE-ADJUDICATION-v2"
        or route.get("config_sha256") != _EXPECTED_ROUTE_CONFIG_SHA256
        or route.get("typed_null_maps_to_event_missing_not_unknown") is not True
    ):
        errors.append("lifecycle B route v2 dependency differs from its lock")
    replay = config.get("input_replay", {})
    if replay.get("expected_semantic_keys") != 34565:
        errors.append("input replay must require 34,565 semantic keys")
    for key in (
        "semantic_key_set_must_match_frozen_reviewed_ledger",
        "semantic_key_set_must_match_pre_adjudication_seed",
        "route_typed_sets_must_match_frozen_route_mapping",
        "route_typed_sets_must_match_pre_adjudication_boundaries",
        "ndc_typed_set_must_match_pre_adjudication_boundary",
        "detail_crosswalk_set_hash_must_match_pre_adjudication_output",
        "order_crosswalk_set_hash_must_match_pre_adjudication_output",
        "new_missing_or_changed_input_fails_closed",
        "matching_hashes_do_not_establish_same_snapshot",
    ):
        if replay.get(key) is not True:
            errors.append(f"input_replay.{key} must be true")
    candidates = config.get("candidate_event_universe", {})
    if candidates.get("q200_only_event_scan_allowed") is not False:
        errors.append("lifecycle B cannot restrict event scanning to Query 200")
    if candidates.get("q201_supported_or_uncertain_keys_outside_q200_must_be_scanned") is not True:
        errors.append("lifecycle B must scan eligible Q201 keys outside Query 200")
    stages = config.get("stages", {})
    if list(stages) != ["202d", "202e"]:
        errors.append("lifecycle B stages must be exactly 202d and 202e")
    if stages.get("202d", {}).get("pre_adjudication_patient_rows_are_not_reused_as_current_snapshot") is not True:
        errors.append("202d must re-extract current-snapshot components")
    _validate_bucket_plan(config, ["202d", "202e"], errors)
    _validate_architecture_only_implementation(config, errors)
    _validate_false_guards(config, errors)
    _validate_safe_evidence(config, errors)
    if _canonical_sha256(config) != _EXPECTED_CANONICAL_SHA256["mapped_application"]:
        errors.append("mapped-event application architecture differs from its v1 lock")
    return errors


def _check_evidence_files(root: Path, config: dict, errors: list[str]) -> int:
    checked = 0
    for item in config.get("evidence", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            continue
        candidate = root / relative
        if not candidate.is_file():
            errors.append(f"Required local evidence file is absent: {relative}")
            continue
        checked += 1
        if _sha256(candidate) != item.get("file_sha256"):
            errors.append(f"Evidence hash mismatch: {relative}")
    return checked


def _verify_route_preflight_summary(root: Path, config: dict) -> bool:
    evidence = config.get("evidence", [])
    item = next(
        (
            value
            for value in evidence
            if isinstance(value, dict)
            and value.get("name") == "mapping_preflight_public_summary"
        ),
        None,
    )
    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
        return False
    try:
        summary = json.loads((root / item["path"]).read_text(encoding="utf-8"))
        by_field = {
            value["source_field"]: value
            for value in summary["source_summaries"].values()
            if isinstance(value, dict) and isinstance(value.get("source_field"), str)
        }
        return all(
            by_field[field]["typed_set_sha256"] == digest
            and by_field[field]["typed_distinct_values"] == typed
            and by_field[field]["typed_state_distinct_counts"]
            == {"nonnull": nonnull, "sql_null": 1}
            for field, digest, typed, nonnull in zip(
                _EXPECTED_ROUTE_FIELDS,
                _EXPECTED_ROUTE_HASHES,
                _EXPECTED_ROUTE_TYPED_COUNTS,
                _EXPECTED_ROUTE_NONNULL_COUNTS,
                strict=True,
            )
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        return False


def _verify_pre_adjudication_seed_references(root: Path, config: dict) -> bool:
    evidence = config.get("evidence", [])
    q201_item = next(
        (
            value
            for value in evidence
            if isinstance(value, dict)
            and value.get("name") == "query201_private_discovery"
        ),
        None,
    )
    preflight_item = next(
        (
            value
            for value in evidence
            if isinstance(value, dict)
            and value.get("name") == "mapping_preflight_public_summary"
        ),
        None,
    )
    if not isinstance(q201_item, dict) or not isinstance(preflight_item, dict):
        return False
    try:
        q201 = json.loads((root / q201_item["path"]).read_text(encoding="utf-8"))
        expected_q201 = {
            "emar_medication": ("mimiciv_hosp.emar.medication", 5045),
            "detail_product_description": (
                "mimiciv_hosp.emar_detail.product_description",
                6692,
            ),
            "pharmacy_medication": ("mimiciv_hosp.pharmacy.medication", 11059),
            "prescription_drug": ("mimiciv_hosp.prescriptions.drug", 10927),
        }
        sources = q201["sources"]
        if set(sources) != set(expected_q201):
            return False
        for name, (field, count) in expected_q201.items():
            source = sources[name]
            if (
                source["source_field"] != field
                or source["distinct_nonnull_values"] != count
                or not isinstance(source["values"], list)
                or len(source["values"]) != count
            ):
                return False
        preflight = json.loads(
            (root / preflight_item["path"]).read_text(encoding="utf-8")
        )
        pdo = preflight["source_summaries"]["detail_product_description_other"]
        return (
            sum(value[1] for value in expected_q201.values()) == 33723
            and pdo["source_field"]
            == "mimiciv_hosp.emar_detail.product_description_other"
            and pdo["typed_set_sha256"]
            == "0105f73cef307cc11b93e1d9d657d43a278c66c3c06ef31e5123db377e11dd4e"
            and pdo["typed_distinct_values"] == 843
            and pdo["typed_state_distinct_counts"]
            == {"nonnull": 842, "sql_null": 1}
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
        return False


def potassium_query202_extraction_preregistration_report(root: Path) -> dict:
    """Report the old component only as an inert superseded record."""
    path = root / POTASSIUM_QUERY202_EXTRACTION_PATH
    config = read_potassium_query202_extraction_preregistration(root)
    errors = validate_potassium_query202_extraction_preregistration(config)
    return {
        "component_id": config.get("component_id"),
        "status": config.get("status"),
        "execution_status": config.get("execution_status"),
        "execution_permitted": config.get("execution_permitted"),
        "superseded_by": config.get("superseded_by", []),
        "config": str(POTASSIUM_QUERY202_EXTRACTION_PATH),
        "config_sha256": _sha256(path),
        "valid": not errors,
        "errors": errors,
        "warnings": [],
        "evidence_files_checked": 0,
    }


def potassium_query202_pre_adjudication_preregistration_report(root: Path) -> dict:
    path = root / POTASSIUM_QUERY202_PRE_ADJUDICATION_PATH
    config = read_potassium_query202_pre_adjudication_preregistration(root)
    errors = validate_potassium_query202_pre_adjudication_preregistration(config)
    checked = _check_evidence_files(root, config, errors)
    route_reference_verified = _verify_route_preflight_summary(root, config)
    if not route_reference_verified:
        errors.append("Per-field route references do not match audited preflight summary")
    seed_references_verified = _verify_pre_adjudication_seed_references(root, config)
    if not seed_references_verified:
        errors.append("Q201 plus PDO semantic-seed references are not exact")
    return {
        "component_id": config.get("component_id"),
        "status": config.get("status"),
        "execution_status": config.get("execution_status"),
        "execution_permitted": config.get("execution_permitted"),
        "implementation_state": config.get("implementation", {}).get("state"),
        "reviewed_semantic_ledger_is_input": config.get("lifecycle", {}).get(
            "reviewed_semantic_ledger_is_input"
        ),
        "frozen_route_mapping_is_input": config.get("lifecycle", {}).get(
            "frozen_route_mapping_is_input"
        ),
        "semantic_seed_expected_keys": config.get("semantic_seed_lineage", {}).get(
            "expected_key_count"
        ),
        "private_output_count": len(config.get("private_outputs", [])),
        "partition_plan_status": config.get("partition_plan", {}).get("status"),
        "route_preflight_reference_verified": route_reference_verified,
        "semantic_seed_references_verified": seed_references_verified,
        "planned_sql_bundle_frozen": False,
        "unresolved_blockers": config.get("execution_gate", {}).get(
            "unresolved_blockers", []
        ),
        "config": str(POTASSIUM_QUERY202_PRE_ADJUDICATION_PATH),
        "config_sha256": _sha256(path),
        "valid": not errors,
        "errors": errors,
        "warnings": [],
        "evidence_files_checked": checked,
    }


def potassium_query202_mapped_event_application_preregistration_report(
    root: Path,
) -> dict:
    path = root / POTASSIUM_QUERY202_MAPPED_EVENT_APPLICATION_PATH
    config = read_potassium_query202_mapped_event_application_preregistration(root)
    errors = validate_potassium_query202_mapped_event_application_preregistration(config)
    checked = _check_evidence_files(root, config, errors)
    route_reference_verified = _verify_route_preflight_summary(root, config)
    if not route_reference_verified:
        errors.append("Per-field route references do not match audited preflight summary")
    route_dependency = config.get("route_mapping_dependency", {})
    route_relative = Path(str(route_dependency.get("config_path", "")))
    route_dependency_verified = (
        not route_relative.is_absolute()
        and ".." not in route_relative.parts
        and (root / route_relative).is_file()
        and _sha256(root / route_relative) == route_dependency.get("config_sha256")
    )
    if not route_dependency_verified:
        errors.append("Route adjudication v2 config hash mismatch")
    reducer_relative = Path(
        str(config.get("primary_link_partition", {}).get("reducer_path", ""))
    )
    reducer_verified = (
        not reducer_relative.is_absolute()
        and ".." not in reducer_relative.parts
        and (root / reducer_relative).is_file()
        and _sha256(root / reducer_relative)
        == config.get("primary_link_partition", {}).get("reducer_sha256")
    )
    if not reducer_verified:
        errors.append("Mapped-event primary-link reducer hash mismatch")
    frozen = config.get("frozen_input_contract", {})
    frozen_inputs_populated = all(
        value != _PLACEHOLDER
        for key, value in frozen.items()
        if key.endswith("_path")
        or key.endswith("_sha256")
        or key == "external_ndc_evidence_mode"
    )
    return {
        "component_id": config.get("component_id"),
        "status": config.get("status"),
        "execution_status": config.get("execution_status"),
        "execution_permitted": config.get("execution_permitted"),
        "implementation_state": config.get("implementation", {}).get("state"),
        "uses_new_snapshot": config.get("lifecycle", {}).get(
            "uses_new_repeatable_read_read_only_snapshot"
        ),
        "reviewed_semantic_ledger_frozen": frozen.get(
            "reviewed_semantic_ledger_frozen"
        ),
        "route_mapping_frozen": frozen.get("route_mapping_frozen"),
        "frozen_inputs_populated": frozen_inputs_populated,
        "route_dependency_config_verified": route_dependency_verified,
        "route_preflight_reference_verified": route_reference_verified,
        "primary_link_reducer_verified": reducer_verified,
        "planned_sql_bundle_frozen": False,
        "bucket_count": config.get("bucket_plan", {}).get("bucket_count"),
        "unresolved_blockers": config.get("execution_gate", {}).get(
            "unresolved_blockers", []
        ),
        "config": str(POTASSIUM_QUERY202_MAPPED_EVENT_APPLICATION_PATH),
        "config_sha256": _sha256(path),
        "valid": not errors,
        "errors": errors,
        "warnings": [],
        "evidence_files_checked": checked,
    }
