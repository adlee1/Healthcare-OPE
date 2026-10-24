"""Machine checks for research sub-protocols that remain short of a full freeze."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import tomllib

from .query202_preregistration import (
    potassium_query202_extraction_preregistration_report,
    potassium_query202_mapped_event_application_preregistration_report,
    potassium_query202_pre_adjudication_preregistration_report,
    read_potassium_query202_extraction_preregistration,
    read_potassium_query202_mapped_event_application_preregistration,
    read_potassium_query202_pre_adjudication_preregistration,
    validate_potassium_query202_extraction_preregistration,
    validate_potassium_query202_mapped_event_application_preregistration,
    validate_potassium_query202_pre_adjudication_preregistration,
)
from .query202_pre_adjudication_preregistration_v2 import (
    potassium_query202_pre_adjudication_v2_preregistration_report,
    read_potassium_query202_pre_adjudication_v2_preregistration,
    validate_potassium_query202_pre_adjudication_v2_preregistration,
)
from .query202_adjudication_input_preregistration import (
    query202_adjudication_input_preregistration_report,
    read_query202_adjudication_input_preregistration,
    validate_query202_adjudication_input_preregistration,
)
from .query202_ndc_evidence_mode_preregistration import (
    query202_ndc_evidence_mode_preregistration_report,
    read_query202_ndc_evidence_mode_preregistration,
    validate_query202_ndc_evidence_mode_preregistration,
)
from .query202_human_adjudication_preregistration import (
    query202_human_adjudication_preregistration_report,
    read_query202_human_adjudication_preregistration,
    validate_query202_human_adjudication_preregistration,
)
from .route_adjudication_preregistration import (
    potassium_route_adjudication_preregistration_report,
    read_potassium_route_adjudication_preregistration,
    validate_potassium_route_adjudication_preregistration,
)


POTASSIUM_OUTCOME_PATH = Path("config/preregistrations/d003_potassium_outcome.toml")
POTASSIUM_SOURCE_DISCOVERY_PATH = Path(
    "config/preregistrations/d005_potassium_source_discovery.toml"
)
POTASSIUM_PRODUCT_MAPPING_PATH = Path(
    "config/preregistrations/d005_potassium_product_mapping.toml"
)
POTASSIUM_MAPPING_PREFLIGHT_PATH = Path(
    "config/preregistrations/d005_potassium_mapping_preflight.toml"
)
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

_POTASSIUM_MAPPING_PREFLIGHT_SQL_PATHS = (
    Path("sql/profiling/202p1_potassium_emar_detail_route_vocabulary.sql"),
    Path("sql/profiling/202p2_potassium_pharmacy_route_vocabulary.sql"),
    Path("sql/profiling/202p3_potassium_prescriptions_route_vocabulary.sql"),
    Path("sql/profiling/202p4_potassium_product_description_other_vocabulary.sql"),
    Path("sql/profiling/202p5_potassium_prescriptions_ndc_vocabulary.sql"),
)
_POTASSIUM_MAPPING_PREFLIGHT_RUNNER_PATHS = (
    Path("src/april_repro/mapping_preflight.py"),
    Path("scripts/run_potassium_mapping_preflight.py"),
)
_POTASSIUM_MAPPING_PREFLIGHT_AUDITOR_PATHS = (
    Path("src/april_repro/mapping_preflight_audit.py"),
    Path("scripts/audit_potassium_mapping_preflight.py"),
)

_POTASSIUM_PRODUCT_MAPPING_EVIDENCE = (
    (
        "paper_metadata",
        "config/paper.toml",
        "6653d2d6ef24815a244988dbbba76cf1967eb780941d2c53f608c1765422f2a5",
    ),
    (
        "local_column_inventory",
        "artifacts/db/20261011T091753.638203Z/020_column_inventory.csv",
        "d0e486474f375c582a66c1bf08ec2a80557ce0dc22a9457aaee06764d820bc5b",
    ),
    (
        "source_semantics",
        "docs/source-semantics.md",
        "6f2432408dbb78b29433b226e45caf36ec271ada1a49032519001b50bae815c1",
    ),
    (
        "query200_manifest",
        "artifacts/profiling/20261011T174457.657508Z/manifest.json",
        "76b9ae67d02081d634965906cb7c11a3671b2c69ac7e194252b996156ee099e6",
    ),
    (
        "query200_audit",
        "artifacts/profiling/20261011T174457.657508Z/audit-summary.json",
        "73ca31b9556165ccb79e3d278812b4d0aec39aa75498327f452ca46fe6b9a31c",
    ),
    (
        "query201_manifest",
        "artifacts/profiling/20261011T182244.083389Z/manifest.json",
        "fe13a910a590df49e26b8e71770735d100af7f9e474cf9769a619c0b2cc6fa44",
    ),
    (
        "query201_audit",
        "artifacts/profiling/20261011T182244.083389Z/audit-summary.json",
        "a7aa9b35d4e408bbeda6b4e024588e3083fc7f13b976492b624d21a390946428",
    ),
    (
        "query201_public_summary",
        "artifacts/profiling/20261011T182244.083389Z/"
        "potassium_full_source_vocabulary_discovery.aggregate-summary.json",
        "784c618be25f4e243f5bda89619bbb6d004c8eee10fc40b6327e311c83fc30ea",
    ),
    (
        "query201_private_discovery",
        "artifacts/profiling/20261011T182244.083389Z/"
        "potassium_full_source_vocabulary_discovery.discovery.json",
        "62731e7dcadf82b95a55e3afd7f2790455320d1c642f9ca307b2574672760d18",
    ),
)

_POTASSIUM_MAPPING_PREFLIGHT_EVIDENCE = (
    (
        "local_column_inventory",
        "artifacts/db/20261011T091753.638203Z/020_column_inventory.csv",
        "d0e486474f375c582a66c1bf08ec2a80557ce0dc22a9457aaee06764d820bc5b",
        "Local existence, types and SELECT access for all five preflight fields",
    ),
    (
        "query201_manifest",
        "artifacts/profiling/20261011T182244.083389Z/manifest.json",
        "fe13a910a590df49e26b8e71770735d100af7f9e474cf9769a619c0b2cc6fa44",
        "Completed same-snapshot Query 201 execution and controls",
    ),
    (
        "query201_audit",
        "artifacts/profiling/20261011T182244.083389Z/audit-summary.json",
        "a7aa9b35d4e408bbeda6b4e024588e3083fc7f13b976492b624d21a390946428",
        "Independent Query 201 aggregate, privacy and conservation audit",
    ),
    (
        "query201_public_summary",
        "artifacts/profiling/20261011T182244.083389Z/"
        "potassium_full_source_vocabulary_discovery.aggregate-summary.json",
        "784c618be25f4e243f5bda89619bbb6d004c8eee10fc40b6327e311c83fc30ea",
        "Stable Query 201 source counts, boundaries and private-input hash",
    ),
    (
        "query201_private_discovery",
        "artifacts/profiling/20261011T182244.083389Z/"
        "potassium_full_source_vocabulary_discovery.discovery.json",
        "62731e7dcadf82b95a55e3afd7f2790455320d1c642f9ca307b2574672760d18",
        (
            "Stable private exact Query 201 vocabulary evidence; content was not "
            "read while drafting this component"
        ),
    ),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _implementation_bundle(root: Path, paths: tuple[Path, ...]) -> dict:
    """Hash a fixed ordered code bundle with unambiguous path/content framing."""
    digest = hashlib.sha256()
    files: list[dict[str, object]] = []
    missing: list[str] = []
    for relative in paths:
        candidate = root / relative
        if not candidate.is_file() or candidate.is_symlink():
            missing.append(str(relative))
            continue
        path_bytes = str(relative).encode("utf-8")
        content = candidate.read_bytes()
        digest.update(len(path_bytes).to_bytes(4, "big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
        files.append({
            "path": str(relative),
            "bytes": len(content),
            "file_sha256": hashlib.sha256(content).hexdigest(),
        })
    return {
        "paths": [str(relative) for relative in paths],
        "actual_sha256": None if missing else digest.hexdigest(),
        "files": files,
        "missing": missing,
        "encoding": "uint32be_path_length+path_utf8+uint64be_content_length+content",
    }


def read_potassium_outcome_preregistration(root: Path) -> dict:
    with (root / POTASSIUM_OUTCOME_PATH).open("rb") as handle:
        return tomllib.load(handle)


def validate_potassium_outcome_preregistration(config: dict) -> list[str]:
    """Reject silent changes to the proposed D003 potassium outcome contract."""
    errors: list[str] = []

    def expect(container: dict, key: str, value: object, prefix: str) -> None:
        if container.get(key) != value:
            errors.append(f"{prefix}.{key} must be {value!r}")

    expect(config, "schema_version", 1, "root")
    expect(config, "component_id", "D003-K-OUTCOME-v1", "root")
    expect(config, "decision_id", "D003", "root")
    expect(config, "status", "proposed", "root")
    expect(config, "rule_version", "k-observed-outcome-v1-proposed", "root")
    expect(config, "author_setting_recovered", False, "root")
    expect(config, "formal_label_enabled", False, "root")

    facts = config.get("paper_facts")
    if not isinstance(facts, dict):
        errors.append("paper_facts must be a table")
        facts = {}
    expect(facts, "prompt_assumed_rate_meq_per_hour", 10, "paper_facts")
    expect(facts, "prompt_prediction_hours_after_infusion", 3, "paper_facts")
    for key in (
        "observed_infusion_endpoint_disclosed",
        "observed_label_selector_disclosed",
        "maximum_label_lag_disclosed",
        "concurrent_treatment_rule_disclosed",
        "duplicate_lab_rule_disclosed",
    ):
        expect(facts, key, False, "paper_facts")

    primary = config.get("primary_rule")
    if not isinstance(primary, dict):
        errors.append("primary_rule must be a table")
        primary = {}
    expected_primary = {
        "rule_id": "first-k-after-administration-anchor-within-24h-v1",
        "anchor": "emar_administration_record_charttime",
        "anchor_is_observed_infusion_start": False,
        "anchor_is_observed_infusion_end": False,
        "identity_scope": "same_subject_and_hadm",
        "selector": "first_serum_potassium_specimen_timestamp_group_strictly_after_anchor",
        "lower_bound": "open",
        "upper_bound": "closed",
        "maximum_anchor_lag_hours": 24,
        "choose_timestamp_before_quality_assessment": True,
        "skip_invalid_first_timestamp_group": False,
        "supported_itemids": [50971, 52610],
        "normalized_unit": "mEq/L",
        "require_at_least_one_finite_supported_value": True,
        "require_one_distinct_finite_normalized_value": True,
        "allow_duplicate_rows_when_normalized_values_agree": True,
        "allow_conflicting_finite_values": False,
        "allow_finite_values_with_unsupported_units": False,
        "storetime_selects_timestamp": False,
        "allow_missing_storetime": True,
        "allow_storetime_before_charttime": False,
        "selected_lab_group_may_serve_multiple_events": False,
        "lab_reuse_collision": "exclude",
    }
    for key, value in expected_primary.items():
        expect(primary, key, value, "primary_rule")
    expected_exclusions = [
        "decision_time_unresolved",
        "episode_overlap_unresolved",
        "actual_action_unresolved",
        "missing_or_cross_admission_identity",
        "no_lab_within_24h",
        "additional_treatment_before_outcome",
        "same_time_treatment_lab_order_unknown",
        "selected_group_no_finite_supported_value",
        "selected_group_unit_unrecognized",
        "selected_group_value_conflict",
        "reversed_storetime",
        "lab_reuse_collision",
    ]
    expect(primary, "exclusion_reasons", expected_exclusions, "primary_rule")

    treatment = config.get("concurrent_treatment")
    if not isinstance(treatment, dict):
        errors.append("concurrent_treatment must be a table")
        treatment = {}
    expect(treatment, "exclude_distinct_candidate_at_same_anchor", True, "concurrent_treatment")
    expect(treatment, "exclude_additional_candidate_after_anchor_through_selected_lab", True, "concurrent_treatment")
    expect(treatment, "interval", "(anchor, selected_lab_time]", "concurrent_treatment")
    expect(treatment, "current_sample_coverage_is_complete", False, "concurrent_treatment")

    proxy = config.get("prompt_proxy")
    if not isinstance(proxy, dict):
        errors.append("prompt_proxy must be a table")
        proxy = {}
    expect(proxy, "positive_dose_proxy_end", "anchor + normalized_positive_dose_meq / 10 hours", "prompt_proxy")
    expect(proxy, "positive_dose_prediction_target", "proxy_end + 3 hours", "prompt_proxy")
    expect(proxy, "proxy_end_is_observed", False, "prompt_proxy")
    expect(proxy, "prediction_target_selects_primary_factual_label", False, "prompt_proxy")
    expect(proxy, "zero_dose_clock_defined", False, "prompt_proxy")

    expected_sensitivities = [
        {
            "rule_id": "first-k-after-anchor-within-6h",
            "selector": "first_serum_potassium_specimen_timestamp_group_strictly_after_anchor",
            "maximum_anchor_lag_hours": 6,
        },
        {
            "rule_id": "first-k-after-anchor-within-12h",
            "selector": "first_serum_potassium_specimen_timestamp_group_strictly_after_anchor",
            "maximum_anchor_lag_hours": 12,
        },
        {
            "rule_id": "first-k-after-proxy-end-within-anchor-24h",
            "selector": "first_serum_potassium_specimen_timestamp_group_strictly_after_proxy_end",
            "maximum_anchor_lag_hours": 24,
        },
        {
            "rule_id": "nearest-k-to-proxy-target-strictly-post-proxy-end-within-3h",
            "selector": "nearest_serum_potassium_timestamp_group_to_proxy_target_strictly_after_proxy_end",
            "maximum_absolute_target_lag_hours": 3,
            "equidistant_distinct_timestamp_groups": "exclude_as_ambiguous",
        },
    ]
    expect(config, "sensitivity_rules", expected_sensitivities, "root")

    controls = config.get("change_control")
    if not isinstance(controls, dict):
        errors.append("change_control must be a table")
        controls = {}
    expect(controls, "downstream_artifacts_must_record", ["component_id", "rule_version", "config_sha256"], "change_control")
    expected_dependencies = [
        "D005 accepted IV potassium medication universe",
        "D005 source rows to actual delivered action",
        "D005 same-anchor episode composition",
        "D005 zero-action opportunity",
        "D003 formal decision anchor",
        "D003 formal non-ICU interval",
    ]
    expect(controls, "unresolved_dependencies", expected_dependencies, "change_control")

    guards = config.get("guards")
    expected_guards = {
        "formal_cohort_constructed",
        "formal_label_constructed",
        "actual_action_defined",
        "zero_action_defined",
        "episode_rule_defined",
        "non_icu_rule_defined",
        "patient_data_exported",
        "llm_called",
    }
    if not isinstance(guards, dict):
        errors.append("guards must be a table")
    else:
        if set(guards) != expected_guards:
            errors.append("guards must contain the exact proposed-scope guard set")
        for key in sorted(expected_guards):
            expect(guards, key, False, "guards")

    evidence = config.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("evidence must be a non-empty array of tables")
    else:
        names: set[str] = set()
        for index, item in enumerate(evidence):
            prefix = f"evidence[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix} must be a table")
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name:
                errors.append(f"{prefix}.name must be non-empty")
            elif name in names:
                errors.append(f"{prefix}.name is duplicated")
            else:
                names.add(name)
            path = item.get("path")
            if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
                errors.append(f"{prefix}.path must be a safe project-relative path")
            digest = item.get("file_sha256")
            if not isinstance(digest, str) or not _HEX_SHA256.fullmatch(digest):
                errors.append(f"{prefix}.file_sha256 must be a lowercase SHA-256")
    return errors


def potassium_outcome_preregistration_report(root: Path) -> dict:
    """Validate the lock and, when present locally, its ignored evidence files."""
    path = root / POTASSIUM_OUTCOME_PATH
    config = read_potassium_outcome_preregistration(root)
    errors = validate_potassium_outcome_preregistration(config)
    warnings: list[str] = []
    checked_evidence = 0
    for item in config.get("evidence", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            continue
        evidence_path = root / relative
        if not evidence_path.is_file():
            warnings.append(f"Local evidence file is absent: {relative}")
            continue
        checked_evidence += 1
        expected = item.get("file_sha256")
        if isinstance(expected, str) and _sha256(evidence_path) != expected:
            errors.append(f"Evidence hash mismatch: {relative}")
    return {
        "component_id": config.get("component_id"),
        "status": config.get("status"),
        "formal_label_enabled": config.get("formal_label_enabled"),
        "config": str(POTASSIUM_OUTCOME_PATH),
        "config_sha256": _sha256(path),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "evidence_files_checked": checked_evidence,
    }


def read_potassium_source_discovery_preregistration(root: Path) -> dict:
    with (root / POTASSIUM_SOURCE_DISCOVERY_PATH).open("rb") as handle:
        return tomllib.load(handle)


def validate_potassium_source_discovery_preregistration(config: dict) -> list[str]:
    """Reject drift in the proposed D005 potassium source-discovery contract."""
    errors: list[str] = []

    def expect(container: dict, key: str, value: object, prefix: str) -> None:
        if container.get(key) != value:
            errors.append(f"{prefix}.{key} must be {value!r}")

    expect(config, "schema_version", 1, "root")
    expect(config, "component_id", "D005-K-SOURCE-DISCOVERY-v1", "root")
    expect(config, "decision_id", "D005", "root")
    expect(config, "status", "proposed", "root")
    expect(
        config,
        "rule_version",
        "k-source-vocabulary-negative-space-v1-proposed",
        "root",
    )
    expect(config, "author_setting_recovered", False, "root")
    expect(config, "formal_source_policy_enabled", False, "root")
    expect(config, "formal_product_identity_enabled", False, "root")

    facts = config.get("paper_facts")
    if not isinstance(facts, dict):
        errors.append("paper_facts must be a table")
        facts = {}
    expect(facts, "target_intervention", "IV potassium", "paper_facts")
    expect(facts, "action_values_meq", [0, 10, 20, 40], "paper_facts")
    expect(facts, "salt_or_product_scope_disclosed", False, "paper_facts")
    expect(facts, "source_fields_disclosed", False, "paper_facts")
    expect(facts, "product_identity_rule_disclosed", False, "paper_facts")
    expect(facts, "episode_rule_disclosed", False, "paper_facts")
    expect(facts, "zero_action_rule_disclosed", False, "paper_facts")
    expect(facts, "kcl_is_complete_paper_scope", False, "paper_facts")

    universe = config.get("discovery_universe")
    if not isinstance(universe, dict):
        errors.append("discovery_universe must be a table")
        universe = {}
    expected_fields = [
        "mimiciv_hosp.emar.medication",
        "mimiciv_hosp.emar_detail.product_description",
        "mimiciv_hosp.pharmacy.medication",
        "mimiciv_hosp.prescriptions.drug",
    ]
    expect(universe, "source_fields", expected_fields, "discovery_universe")
    expect(
        universe,
        "enumerate_all_non_null_distinct_values",
        True,
        "discovery_universe",
    )
    expect(universe, "sampling", False, "discovery_universe")
    expect(
        universe,
        "normalization",
        "trim-collapse-whitespace-lowercase-for-review-only",
        "discovery_universe",
    )
    expect(
        universe,
        "normalization_establishes_product_identity",
        False,
        "discovery_universe",
    )
    expect(
        universe,
        "local_product_code_is_ndc",
        False,
        "discovery_universe",
    )
    expect(
        universe,
        "complete_text_vocabulary_proves_intervention_coverage",
        False,
        "discovery_universe",
    )

    execution = config.get("execution")
    if not isinstance(execution, dict):
        errors.append("execution must be a table")
        execution = {}
    expected_execution = {
        "transaction_isolation": "repeatable read",
        "transaction_read_only": True,
        "statement_timeout_ms": 120000,
        "same_snapshot_required": True,
        "explicit_rollback_required": True,
        "clean_psql_exit_required": True,
        "persist_private_values_only_after_rollback": True,
        "private_file_mode": "0600",
        "print_controlled_vocabulary_values": False,
        "emit_patient_identifiers_or_times": False,
    }
    for key, value in expected_execution.items():
        expect(execution, key, value, "execution")

    lexical = config.get("lexical_review")
    if not isinstance(lexical, dict):
        errors.append("lexical_review must be a table")
        lexical = {}
    expected_strata = [
        "blank_after_trim",
        "focal_kcl_repletion_hint",
        "broader_phosphate_or_acetate_repletion_hint",
        "other_potassium_salt_review",
        "non_repletion_active_drug_hint",
        "unresolved_potassium_lexical_review",
        "no_declared_potassium_lexical_signal",
    ]
    expect(lexical, "mutually_exclusive_strata", expected_strata, "lexical_review")
    expect(lexical, "retain_independent_boolean_hints", True, "lexical_review")
    expect(lexical, "strata_are_inclusion_rules", False, "lexical_review")
    expect(lexical, "no_lexical_signal_is_exclusion", False, "lexical_review")
    expect(lexical, "focal_kcl_hint_is_product_identity", False, "lexical_review")

    baseline = config.get("q200_baseline")
    if not isinstance(baseline, dict):
        errors.append("q200_baseline must be a table")
        baseline = {}
    expected_baseline = {
        "candidate_emar_heads": 719059,
        "query199_direct_head_scope": 559191,
        "heads_new_beyond_direct_name": 159868,
        "identity_unresolved_only_heads": 472,
        "source_vocabulary_rows": 237,
        "seed_local_product_codes": 27,
        "detail_code_dictionary_names": 38,
        "nonexact_admission_link_heads": 16523,
        "q200_audit_checks": 18952,
        "q200_audit_failures": 0,
    }
    for key, value in expected_baseline.items():
        expect(baseline, key, value, "q200_baseline")
    expect(
        baseline,
        "discovery_array_lengths",
        [23, 79, 45, 52],
        "q200_baseline",
    )

    acceptance = config.get("acceptance")
    if not isinstance(acceptance, dict):
        errors.append("acceptance must be a table")
        acceptance = {}
    expected_acceptance_true = (
        "q200_discovery_arrays_are_exact_source_subsets",
        "q200_artifact_hashes_must_match",
        "source_values_unique_within_each_field",
        "every_value_has_exactly_one_review_stratum",
        "strata_conserve_each_source_and_global_totals",
        "private_vocabulary_artifact_required",
        "public_summary_aggregate_only",
        "unknown_or_conflicting_identity_fails_closed",
    )
    for key in expected_acceptance_true:
        expect(acceptance, key, True, "acceptance")

    controls = config.get("change_control")
    if not isinstance(controls, dict):
        errors.append("change_control must be a table")
        controls = {}
    expect(
        controls,
        "selection_must_not_depend_on",
        [
            "paper_sample_size",
            "action_distribution",
            "label_coverage",
            "model_accuracy",
            "ope_error",
            "agreement_with_paper_figures",
        ],
        "change_control",
    )
    expect(
        controls,
        "downstream_artifacts_must_record",
        ["component_id", "rule_version", "config_sha256"],
        "change_control",
    )

    expected_dependencies = [
        "D005 semantic-key product adjudication",
        "D005 accepted IV potassium source policy",
        "D005 source rows to recorded delivered action",
        "D005 same-anchor and adjacent episode rule",
        "D005 zero-action opportunity",
        "D003 formal non-ICU interval",
        "D003 formal label",
    ]
    expect(config, "unresolved_dependencies", expected_dependencies, "root")

    guards = config.get("guards")
    expected_guards = {
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
    }
    if not isinstance(guards, dict):
        errors.append("guards must be a table")
    else:
        if set(guards) != expected_guards:
            errors.append("guards must contain the exact discovery-scope guard set")
        for key in sorted(expected_guards):
            expect(guards, key, False, "guards")

    evidence = config.get("evidence")
    expected_evidence_names = {
        "paper_metadata",
        "query200_manifest",
        "query200_audit",
        "query200_output",
        "query200_private_discovery",
        "query200_executed_sql",
        "query201_emar_sql",
        "query201_detail_sql",
        "query201_pharmacy_sql",
        "query201_prescription_sql",
        "query201_runner_module",
        "query201_entrypoint",
    }
    if not isinstance(evidence, list) or not evidence:
        errors.append("evidence must be a non-empty array of tables")
    else:
        names: set[str] = set()
        for index, item in enumerate(evidence):
            prefix = f"evidence[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix} must be a table")
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name:
                errors.append(f"{prefix}.name must be non-empty")
            elif name in names:
                errors.append(f"{prefix}.name is duplicated")
            else:
                names.add(name)
            path = item.get("path")
            if (
                not isinstance(path, str)
                or not path
                or Path(path).is_absolute()
                or ".." in Path(path).parts
            ):
                errors.append(f"{prefix}.path must be a safe project-relative path")
            digest = item.get("file_sha256")
            if not isinstance(digest, str) or not _HEX_SHA256.fullmatch(digest):
                errors.append(f"{prefix}.file_sha256 must be a lowercase SHA-256")
        if names != expected_evidence_names:
            errors.append("evidence must contain the exact D005 discovery evidence set")

    return errors


def potassium_source_discovery_preregistration_report(root: Path) -> dict:
    """Validate the D005 discovery proposal and all locally present evidence."""
    path = root / POTASSIUM_SOURCE_DISCOVERY_PATH
    config = read_potassium_source_discovery_preregistration(root)
    errors = validate_potassium_source_discovery_preregistration(config)
    warnings: list[str] = []
    checked_evidence = 0
    for item in config.get("evidence", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            continue
        evidence_path = root / relative
        if not evidence_path.is_file():
            warnings.append(f"Local evidence file is absent: {relative}")
            continue
        checked_evidence += 1
        expected = item.get("file_sha256")
        if isinstance(expected, str) and _sha256(evidence_path) != expected:
            errors.append(f"Evidence hash mismatch: {relative}")
    return {
        "component_id": config.get("component_id"),
        "status": config.get("status"),
        "formal_source_policy_enabled": config.get("formal_source_policy_enabled"),
        "formal_product_identity_enabled": config.get("formal_product_identity_enabled"),
        "config": str(POTASSIUM_SOURCE_DISCOVERY_PATH),
        "config_sha256": _sha256(path),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "evidence_files_checked": checked_evidence,
    }


def read_potassium_product_mapping_preregistration(root: Path) -> dict:
    with (root / POTASSIUM_PRODUCT_MAPPING_PATH).open("rb") as handle:
        return tomllib.load(handle)


def validate_potassium_product_mapping_preregistration(config: dict) -> list[str]:
    """Reject drift in the proposed D005 product-mapping contract."""
    errors: list[str] = []

    def expect(container: dict, key: str, value: object, prefix: str) -> None:
        if container.get(key) != value:
            errors.append(f"{prefix}.{key} must be {value!r}")

    root_values = {
        "schema_version": 1,
        "component_id": "D005-K-PRODUCT-MAPPING-v1",
        "decision_id": "D005",
        "status": "proposed",
        "scope": "Private potassium product mapping and dual source-universe evidence after Query 201",
        "rule_version": "k-product-mapping-dual-universe-v1-proposed",
        "specified_on": "2026-10-12",
        "specified_after": (
            "Completed and independently audited Query 201 four-field local "
            "vocabulary discovery"
        ),
        "specified_before": [
            "real Query 202 database execution",
            "external NDC mapping execution",
            "D005 source-policy acceptance",
            "recorded-dose or episode extraction",
            "formal cohort",
            "model training",
            "LLM patient-data calls",
            "downstream performance metrics",
        ],
        "author_setting_recovered": False,
        "validator_integration": (
            "april_repro.preregistration:"
            "validate_potassium_product_mapping_preregistration"
        ),
        "formal_product_mapping_enabled": False,
        "formal_source_policy_enabled": False,
    }
    for key, value in root_values.items():
        expect(config, key, value, "root")

    facts = config.get("paper_facts")
    if not isinstance(facts, dict):
        errors.append("paper_facts must be a table")
        facts = {}
    for key, value in {
        "target_intervention": "all IV potassium",
        "action_values_meq": [0, 10, 20, 40],
        "salt_or_product_scope_disclosed": False,
        "product_mapping_rule_disclosed": False,
        "event_route_rule_disclosed": False,
        "kcl_is_complete_paper_scope": False,
    }.items():
        expect(facts, key, value, "paper_facts")

    baseline = config.get("q201_baseline")
    if not isinstance(baseline, dict):
        errors.append("q201_baseline must be a table")
        baseline = {}
    for key, value in {
        "source_value_memberships": 33723,
        "query200_overlap_memberships": 199,
        "negative_space_memberships": 33524,
        "all_source_policy_statuses": "unresolved",
        "product_description_other_examined": False,
        "neutral_review_strata_are_inclusion_rules": False,
    }.items():
        expect(baseline, key, value, "q201_baseline")

    schema = config.get("local_schema")
    if not isinstance(schema, dict):
        errors.append("local_schema must be a table")
        schema = {}
    for key, value in {
        "inventory_path": "artifacts/db/20261011T091753.638203Z/020_column_inventory.csv",
        "verified_relations": [
            "mimiciv_hosp.emar",
            "mimiciv_hosp.emar_detail",
            "mimiciv_hosp.pharmacy",
            "mimiciv_hosp.prescriptions",
        ],
        "verified_mapping_fields": [
            "mimiciv_hosp.emar.medication",
            "mimiciv_hosp.emar_detail.product_code",
            "mimiciv_hosp.emar_detail.product_description",
            "mimiciv_hosp.emar_detail.product_description_other",
            "mimiciv_hosp.emar_detail.route",
            "mimiciv_hosp.pharmacy.medication",
            "mimiciv_hosp.pharmacy.route",
            "mimiciv_hosp.prescriptions.drug_type",
            "mimiciv_hosp.prescriptions.drug",
            "mimiciv_hosp.prescriptions.formulary_drug_cd",
            "mimiciv_hosp.prescriptions.gsn",
            "mimiciv_hosp.prescriptions.ndc",
            "mimiciv_hosp.prescriptions.prod_strength",
            "mimiciv_hosp.prescriptions.form_rx",
            "mimiciv_hosp.prescriptions.route",
        ],
        "local_emar_product_code_is_ndc": False,
        "formulary_drug_cd_is_ndc": False,
        "prescriptions_ndc_is_external_ndc_candidate": True,
    }.items():
        expect(schema, key, value, "local_schema")

    ledger = config.get("private_ledger")
    if not isinstance(ledger, dict):
        errors.append("private_ledger must be a table")
        ledger = {}
    for key, value in {
        "schema_version": "k-product-ledger-v1",
        "record_role": "source_evidence_lineage",
        "primary_key": ["source_type", "evidence_path", "raw_name"],
        "raw_key_is_exact": True,
        "normalization_establishes_identity": False,
        "canonical_semantic_key": ["source_field", "raw_name"],
        "lineage_bridge_required": True,
        "evidence_path_creates_separate_semantic_decision": False,
        "query200_query201_same_source_field_raw_name_share_semantic_key": True,
        "cross_key_equivalence_requires_explicit_mapping_group_and_evidence": True,
        "initial_semantic_status": "uncertain",
        "semantic_status_values": ["supported", "refuted", "uncertain"],
        "vocabulary_semantic_dimensions": [
            "product_identity",
            "dosage_form",
            "treatment_intent",
            "potassium_content",
            "meq_convertibility",
        ],
        "event_route_is_vocabulary_dimension": False,
        "separate_review_status_from_semantic_status": True,
        "private_file_mode": "0600",
        "private_directory_mode": "0700",
        "public_raw_values_allowed": False,
        "public_local_codes_or_ndcs_allowed": False,
    }.items():
        expect(ledger, key, value, "private_ledger")

    missing_evidence = config.get("private_missing_value_evidence")
    if not isinstance(missing_evidence, dict):
        errors.append("private_missing_value_evidence must be a table")
        missing_evidence = {}
    for key, value in {
        "role": (
            "typed SQL NULL evidence that does not create a vocabulary semantic row"
        ),
        "raw_value_states": ["nonnull", "null"],
        "empty_string_state": "nonnull",
        "null_string_sentinel_allowed": False,
        "null_creates_canonical_semantic_decision": False,
        "primary_key": [
            "source_type",
            "evidence_path",
            "source_field",
            "context_key_sha256",
        ],
        "context_key_input": "typed full private physical-row tuple plus multiplicity",
        "context_key_is_private": True,
        "query200_null_detail_description_must_be_conserved": True,
    }.items():
        expect(missing_evidence, key, value, "private_missing_value_evidence")

    component_bridge = config.get("private_event_component_bridge")
    if not isinstance(component_bridge, dict):
        errors.append("private_event_component_bridge must be a table")
        component_bridge = {}
    for key, value in {
        "detail_component_key": [
            "subject_id",
            "emar_id",
            "emar_seq",
            "detail_reference_sha256",
        ],
        "semantic_membership_key": [
            "subject_id",
            "emar_id",
            "emar_seq",
            "detail_reference_sha256",
            "source_field",
            "raw_name",
        ],
        "detail_reference_hash_is_private": True,
        "multiple_semantic_keys_per_detail_retained": True,
        "semantic_memberships_are_separate_administered_components": False,
        "single_membership_uses_its_semantic_decision": True,
        "multiple_memberships_require_one_explicit_mapping_group": True,
        "mapping_group_requires_explicit_evidence": True,
        "normalization_or_string_similarity_establishes_mapping_group": False,
        "group_level_five_dimension_decision_required": True,
        "unresolved_or_conflicting_memberships_component_semantics": (
            "all five dimensions uncertain"
        ),
        "cross_membership_dimension_cherry_pick_allowed": False,
        "component_role_status_values": ["product", "nonproduct", "uncertain"],
        "uncertain_role_is_possible_product_component": True,
        "nonproduct_component_domain_status": "no",
        "component_role_conflict_fails_audit": True,
        "component_domain_status_values": ["yes", "no", "uncertain"],
        "focal_component_yes_requires_all_required_dimensions_supported": True,
        "focal_component_no_requires_any_required_dimension_refuted": True,
        "focal_component_uncertain_otherwise": True,
        "head_reducer_unit": (
            "physical detail component, never semantic membership row"
        ),
        "no_possible_components_head_status": "uncertain",
        "focal_head_yes_rule": (
            "one or more focal-yes components and every other possible component "
            "is focal-yes or potassium-content-refuted"
        ),
        "focal_head_no_rule": (
            "one or more possible components, no focal-yes component, and every "
            "possible component is focal-no"
        ),
        "focal_head_uncertain_rule": "all other component combinations",
        "interference_head_yes_rule": (
            "one or more interference-yes components"
        ),
        "interference_head_no_rule": (
            "one or more possible components and every possible component is "
            "interference-no"
        ),
        "interference_head_uncertain_rule": "all other component combinations",
        "focal_subset_of_interference_checked_at_component_and_head_levels": True,
    }.items():
        expect(component_bridge, key, value, "private_event_component_bridge")

    event_evidence = config.get("private_event_evidence")
    if not isinstance(event_evidence, dict):
        errors.append("private_event_evidence must be a table")
        event_evidence = {}
    for key, value in {
        "head_key": ["subject_id", "emar_id", "emar_seq"],
        "head_key_is_private": True,
        "parent_field_ordinal_alone_is_unique_detail_key": False,
        "detail_reference_requires_full_raw_tuple_and_multiplicity": True,
        "route_evidence_categories": [
            "missing",
            "unknown_only",
            "iv_only",
            "iv_plus_unknown",
            "noniv_only",
            "noniv_plus_unknown",
            "iv_noniv_conflict",
            "iv_noniv_unknown_conflict",
        ],
        "event_route_supported_categories": ["iv_only"],
        "event_route_refuted_categories": ["noniv_only"],
        "event_route_uncertain_categories": [
            "missing",
            "unknown_only",
            "iv_plus_unknown",
            "noniv_plus_unknown",
            "iv_noniv_conflict",
            "iv_noniv_unknown_conflict",
        ],
        "event_route_status_values": ["supported", "refuted", "uncertain"],
        "identity_chain_status_values": ["exact", "missing", "conflict"],
        "administration_evidence_required_separately": True,
        "interference_candidate_is_administered_treatment": False,
        "domain_status_values": ["yes", "no", "uncertain"],
        "dual_universe_statuses_are_not_vocabulary_level": True,
        "dual_universe_status_levels": ["physical_component", "event_head"],
        "public_event_identifiers_allowed": False,
    }.items():
        expect(event_evidence, key, value, "private_event_evidence")

    universes = config.get("dual_source_universes")
    if not isinstance(universes, dict):
        errors.append("dual_source_universes must be a table")
        universes = {}
    for key, value in {
        "focal_name": "focal_action_eligible",
        "focal_role": "Strict product and event candidates for later recorded-dose audit",
        "focal_requires_supported_product_identity": True,
        "focal_requires_supported_iv_compatible_dosage_form": True,
        "focal_requires_supported_repletion_intent": True,
        "focal_requires_supported_potassium_content": True,
        "focal_requires_explicit_event_level_iv_route": True,
        "focal_requires_identity_valid_record_chain": True,
        "focal_requires_supported_meq_convertibility": True,
        "focal_uncertain_enters_primary_action_domain": False,
        "focal_yes_requires_all_required_dimensions_supported": True,
        "focal_no_requires_any_required_dimension_refuted": True,
        "focal_uncertain_otherwise": True,
        "interference_name": "interference_candidate",
        "interference_role": (
            "Broad possible IV potassium universe for same-anchor and "
            "(anchor,label] treatment checks"
        ),
        "interference_retains_possible_and_uncertain_iv_potassium": True,
        "interference_no_requires_affirmative_nonpotassium_or_event_noniv_evidence": True,
        "interference_yes_requires_supported_potassium_and_event_iv_evidence": True,
        "interference_yes_requires_identity_valid_record_chain": True,
        "interference_noniv_refutation_requires_identity_valid_record_chain": True,
        "interference_nonpotassium_refutation_requires_identity_valid_record_chain": False,
        "interference_uncertain_otherwise": True,
        "focal_must_be_subset_of_interference_per_event": True,
        "kcl_only_result_must_be_named_strict_kcl_subdomain": True,
    }.items():
        expect(universes, key, value, "dual_source_universes")

    reducer = config.get("executable_reducer_contract")
    if not isinstance(reducer, dict):
        errors.append("executable_reducer_contract must be a table")
        reducer = {}
    for key, value in {
        "status": "proposed_offline_only",
        "path": "src/april_repro/product_mapping_contract.py",
        "file_sha256": (
            "27bd346a740eb2578431f2cda997d76439e2f5772a94bd8d9b0c060a26f0b11e"
        ),
        "database_queried": False,
        "formal_mapping_enabled": False,
        "route_partition_states": 8,
        "semantic_dimensions": 5,
        "cross_membership_cherry_pick_allowed": False,
        "component_and_head_subset_invariant_enforced": True,
    }.items():
        expect(reducer, key, value, "executable_reducer_contract")

    execution = config.get("query202_execution")
    if not isinstance(execution, dict):
        errors.append("query202_execution must be a table")
        execution = {}
    for key, value in {
        "status": "not_executed",
        "local_sql_same_snapshot_only": True,
        "transaction_isolation": "repeatable read",
        "transaction_read_only": True,
        "statement_timeout_ms": 120000,
        "same_snapshot_required": True,
        "explicit_rollback_required": True,
        "clean_psql_exit_required": True,
        "persist_private_values_only_after_rollback": True,
        "database_mutation_allowed": False,
        "temporary_database_objects_allowed": False,
        "print_controlled_vocabulary_values": False,
        "emit_patient_identifiers_or_timestamps": False,
        "phases": [
            "complete product_description_other vocabulary and linkage",
            (
                "detail text-local-code crosswalk with parent/product structure "
                "and typed NULL evidence"
            ),
            "identity-valid prescription identifier and component crosswalk",
            "private per-event route evidence and canonical-semantic-key aggregate matrix",
            "Q200/Q201 lineage and source-event conservation",
        ],
        "detail_crosswalk_association_unit": "same physical emar_detail row",
        "head_cooccurrence_establishes_product_equivalence": False,
        "detail_to_emar_identity_fields": ["subject_id", "emar_id", "emar_seq"],
        "event_to_order_requires_subject_match": True,
        "nonnull_hadm_must_match": True,
        "missing_hadm_is_separate_status": True,
        "poe_id_is_auxiliary_consistency_evidence": True,
        "prescription_components_must_all_be_retained": True,
        "link_flags_may_overlap": True,
        "mutually_exclusive_primary_link_status_required": True,
        "primary_link_status_unit": "emar head",
        "primary_link_status_precedence_must_be_frozen_before_execution": True,
        "route_mapping_frozen": False,
        "route_mapping_and_normalization_hash_required_before_execution": True,
        "direct_detail_route_only_can_support_focal_iv": True,
        "pharmacy_or_prescription_route_can_support_focal_iv": False,
        "deterministic_bucket_plan_must_be_preregistered_if_needed": True,
        "bucket_plan_may_not_depend_on_downstream_results": True,
        "statement_timeout_failure_saves_no_private_values": True,
    }.items():
        expect(execution, key, value, "query202_execution")

    ndc = config.get("external_ndc_mapping")
    if not isinstance(ndc, dict):
        errors.append("external_ndc_mapping must be a table")
        ndc = {}
    for key, value in {
        "status": "not_executed",
        "only_candidate_local_field": "mimiciv_hosp.prescriptions.ndc",
        "local_extraction_universe": "all distinct nonnull raw values",
        "local_extraction_may_depend_on_text_or_link_success": False,
        "external_request_requires_preregistered_syntax_normalization": True,
        "invalid_format_status": "not_requested_invalid_format",
        "rxnorm_get_ndc_properties_url": "https://rxnav.nlm.nih.gov/REST/ndcproperties",
        "rxnorm_get_ndc_status_url": "https://rxnav.nlm.nih.gov/REST/ndcstatus",
        "include_current_and_historical": True,
        "get_ndc_properties_format": "json",
        "get_ndc_properties_ndcstatus": "ALL",
        "get_ndc_status_format": "json",
        "get_ndc_status_history": 0,
        "get_ndc_status_altpkg": 0,
        "record_request_utc_time": True,
        "record_release_or_response_version": True,
        "record_response_hash": True,
        "retain_zero_results": True,
        "retain_errors_and_retries": True,
        "retain_one_to_many_results": True,
        "patient_identifiers_or_event_times_exported": False,
        "drug_name_text_exported": False,
        "local_product_code_exported": False,
        "formulary_drug_cd_exported": False,
        "external_mapping_establishes_event_route": False,
        "external_mapping_establishes_administration": False,
    }.items():
        expect(ndc, key, value, "external_ndc_mapping")

    boundaries = config.get("episode_and_dose_boundaries")
    if not isinstance(boundaries, dict):
        errors.append("episode_and_dose_boundaries must be a table")
        boundaries = {}
    for key, value in {
        "different_emar_heads_may_be_dose_merged": False,
        "same_anchor_multiple_possible_heads": "collision",
        "shared_pharmacy_or_poe_proves_one_episode": False,
        "four_hour_lag_is_episode_threshold": False,
        "four_hour_lag_role": "diagnostic_distribution_only",
        "dose_given_component_sum_is_dose_due": False,
        "dose_due_plan_consistency_proves_completion": False,
        "completion_evidence_proves_component_dose": False,
    }.items():
        expect(boundaries, key, value, "episode_and_dose_boundaries")

    acceptance = config.get("acceptance")
    if not isinstance(acceptance, dict):
        errors.append("acceptance must be a table")
        acceptance = {}
    for key in (
        "query201_baseline_must_conserve",
        "product_description_other_full_nonnull_vocabulary_required",
        "every_ledger_key_unique",
        "every_canonical_semantic_key_unique",
        "evidence_lineage_to_semantic_key_complete",
        "nonnull_text_lineage_to_semantic_key_complete",
        "sql_null_evidence_never_creates_text_semantic_key",
        "sql_null_and_empty_string_remain_distinct",
        "query200_null_detail_description_must_conserve",
        "every_unresolved_value_remains_uncertain",
        "five_vocabulary_semantic_dimensions_must_remain_separate",
        "event_route_must_remain_in_private_event_table",
        "event_component_bridge_must_retain_all_semantic_memberships",
        "head_domain_reducers_must_use_physical_components",
        "multiple_semantic_memberships_must_not_count_as_multiple_components",
        "route_mapping_must_be_frozen_before_query202",
        "overlapping_link_flags_and_primary_partition_both_required",
        "link_multiplicity_and_identity_conflicts_retained",
        "external_mapping_version_time_failures_and_cardinality_required",
        "local_product_codes_never_treated_as_ndc",
        "dual_universes_recomputable_from_semantic_component_and_event_tables",
        "focal_subset_of_interference_checked_per_event",
        "administration_status_gate_required_after_mapping",
        "mapping_gate_pass_does_not_accept_source_policy",
        "separate_source_policy_acceptance_artifact_required",
    ):
        expect(acceptance, key, True, "acceptance")
    expect(
        acceptance,
        "independent_offline_audit_failures_required",
        0,
        "acceptance",
    )

    controls = config.get("change_control")
    if not isinstance(controls, dict):
        errors.append("change_control must be a table")
        controls = {}
    expect(
        controls,
        "selection_must_not_depend_on",
        [
            "paper sample size",
            "action distribution",
            "label coverage",
            "model accuracy",
            "ope error",
            "agreement with paper figures",
        ],
        "change_control",
    )
    expect(
        controls,
        "query202_before_execution_must_freeze",
        [
            "SQL templates",
            "runner",
            "evidence_path enumeration",
            (
                "private source-ledger, missing-value, canonical-semantic, "
                "event-component-bridge and event-evidence schemas"
            ),
            "executable reducer contract and hash",
            "bucket plan if used",
            "offline auditor",
        ],
        "change_control",
    )
    expect(
        controls,
        "downstream_artifacts_must_record",
        ["component_id", "rule_version", "config_sha256"],
        "change_control",
    )
    expect(
        controls,
        "changing_mapping_contract_invalidates",
        [
            "Query 202 mapping artifact",
            "source-policy acceptance",
            "episode and action extraction",
            "cohort flow",
            "labels",
            "models",
            "OPE results",
        ],
        "change_control",
    )

    guards = config.get("guards")
    expected_guards = {
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
    }
    if not isinstance(guards, dict):
        errors.append("guards must be a table")
    else:
        if set(guards) != expected_guards:
            errors.append("guards must contain the exact mapping-scope guard set")
        for key in sorted(expected_guards):
            expect(guards, key, False, "guards")

    evidence = config.get("evidence")
    if not isinstance(evidence, list):
        errors.append("evidence must be an array of exactly nine tables")
    else:
        observed: list[tuple[object, object, object]] = []
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                errors.append(f"evidence[{index}] must be a table")
                continue
            observed.append(
                (item.get("name"), item.get("path"), item.get("file_sha256"))
            )
            path = item.get("path")
            if (
                not isinstance(path, str)
                or not path
                or Path(path).is_absolute()
                or ".." in Path(path).parts
            ):
                errors.append(f"evidence[{index}].path must be a safe project-relative path")
            digest = item.get("file_sha256")
            if not isinstance(digest, str) or not _HEX_SHA256.fullmatch(digest):
                errors.append(
                    f"evidence[{index}].file_sha256 must be a lowercase SHA-256"
                )
        if observed != list(_POTASSIUM_PRODUCT_MAPPING_EVIDENCE):
            errors.append(
                "evidence must contain the exact ordered D005 mapping baseline set"
            )

    return errors


def potassium_product_mapping_preregistration_report(root: Path) -> dict:
    """Validate the mapping proposal and hashes of its nine existing inputs."""
    path = root / POTASSIUM_PRODUCT_MAPPING_PATH
    config = read_potassium_product_mapping_preregistration(root)
    errors = validate_potassium_product_mapping_preregistration(config)
    checked_evidence = 0
    for item in config.get("evidence", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            continue
        evidence_path = root / relative
        if not evidence_path.is_file():
            errors.append(f"Required local evidence file is absent: {relative}")
            continue
        checked_evidence += 1
        expected = item.get("file_sha256")
        if isinstance(expected, str) and _sha256(evidence_path) != expected:
            errors.append(f"Evidence hash mismatch: {relative}")
    reducer = config.get("executable_reducer_contract", {})
    reducer_verified = False
    if isinstance(reducer, dict) and isinstance(reducer.get("path"), str):
        relative = Path(reducer["path"])
        if relative.is_absolute() or ".." in relative.parts:
            errors.append("Executable reducer path must be a safe project-relative path")
        elif not (root / relative).is_file():
            errors.append(f"Required executable reducer is absent: {relative}")
        else:
            actual = _sha256(root / relative)
            expected = reducer.get("file_sha256")
            reducer_verified = actual == expected
            if not reducer_verified:
                errors.append(f"Executable reducer hash mismatch: {relative}")
    return {
        "component_id": config.get("component_id"),
        "status": config.get("status"),
        "formal_product_mapping_enabled": config.get(
            "formal_product_mapping_enabled"
        ),
        "formal_source_policy_enabled": config.get("formal_source_policy_enabled"),
        "query202_status": config.get("query202_execution", {}).get("status"),
        "executable_reducer_verified": reducer_verified,
        "config": str(POTASSIUM_PRODUCT_MAPPING_PATH),
        "config_sha256": _sha256(path),
        "valid": not errors,
        "errors": errors,
        "warnings": [],
        "evidence_files_checked": checked_evidence,
    }


def read_potassium_mapping_preflight_preregistration(root: Path) -> dict:
    with (root / POTASSIUM_MAPPING_PREFLIGHT_PATH).open("rb") as handle:
        return tomllib.load(handle)


def validate_potassium_mapping_preflight_preregistration(config: dict) -> list[str]:
    """Reject drift in the proposed five-field mapping preflight contract."""
    errors: list[str] = []

    def expect(container: dict, key: str, value: object, prefix: str) -> None:
        if container.get(key) != value:
            errors.append(f"{prefix}.{key} must be {value!r}")

    def table(name: str) -> dict:
        value = config.get(name)
        if not isinstance(value, dict):
            errors.append(f"{name} must be a table")
            return {}
        return value

    for key, value in {
        "schema_version": 1,
        "component_id": "D005-K-MAPPING-PREFLIGHT-v1",
        "decision_id": "D005",
        "status": "proposed",
        "scope": (
            "Exact five-field local vocabulary preflight before potassium "
            "product and route mapping"
        ),
        "rule_version": "k-mapping-five-field-preflight-v1-proposed",
        "specified_on": "2026-10-12",
        "specified_after": (
            "Completed and independently audited Query 201 four-field "
            "vocabulary discovery"
        ),
        "specified_before": [
            "real mapping-preflight database execution",
            "human route-value adjudication",
            "real Query 202 database execution",
            "external NDC requests",
            "product or event mapping",
            "D005 source-policy acceptance",
            "recorded-dose or episode extraction",
            "formal cohort",
            "model training",
            "LLM patient-data calls",
        ],
        "author_setting_recovered": False,
        "formal_mapping_enabled": False,
        "formal_source_policy_enabled": False,
    }.items():
        expect(config, key, value, "root")

    boundary = table("boundary")
    for key, value in {
        "purpose": (
            "Discover the complete exact raw-value sets needed to freeze a "
            "later mapping contract"
        ),
        "creates_route_mapping": False,
        "calls_external_api": False,
        "decides_product_identity": False,
        "links_events": False,
        "decides_source_inclusion": False,
        "constructs_actions_or_episodes": False,
        "constructs_cohort_or_labels": False,
        "query201_four_field_scope_is_unchanged": True,
        "private_query201_values_read_while_drafting": False,
    }.items():
        expect(boundary, key, value, "boundary")

    source_fields = [
        "mimiciv_hosp.emar_detail.route",
        "mimiciv_hosp.pharmacy.route",
        "mimiciv_hosp.prescriptions.route",
        "mimiciv_hosp.emar_detail.product_description_other",
        "mimiciv_hosp.prescriptions.ndc",
    ]
    route_fields = source_fields[:3]
    universe = table("discovery_universe")
    for key, value in {
        "source_fields": source_fields,
        "route_fields": route_fields,
        "product_description_other_field": (
            "mimiciv_hosp.emar_detail.product_description_other"
        ),
        "ndc_field": "mimiciv_hosp.prescriptions.ndc",
        "enumerate_all_typed_distinct_values": True,
        "retain_exact_nonnull_raw_values": True,
        "retain_source_row_count_per_typed_value": True,
        "sampling": False,
        "lexical_filtering": False,
        "product_filtering": False,
        "event_link_filtering": False,
        "normalization_establishes_identity": False,
        "ndc_syntax_normalization_in_preflight": False,
    }.items():
        expect(universe, key, value, "discovery_universe")

    typed = table("typed_value_contract")
    for key, value in {
        "primary_states": ["sql_null", "nonnull"],
        "nonnull_substates": [
            "empty_string",
            "whitespace_only",
            "nonblank",
        ],
        "sql_null_and_nonnull_are_distinct": True,
        "sql_null_has_no_raw_text_payload": True,
        "empty_string_is_nonnull": True,
        "whitespace_only_is_nonnull_and_nonempty": True,
        "whitespace_only_definition": (
            "every Unicode code point in the exact nonempty decoded value "
            "satisfies runtime str.isspace(); Python and Unicode database "
            "versions are recorded"
        ),
        "raw_text_encoding": (
            "database UTF-8 decoded losslessly to Unicode and re-encoded as "
            "UTF-8 for hashing"
        ),
        "trimming_allowed": False,
        "case_folding_allowed": False,
        "whitespace_collapsing_allowed": False,
        "string_sentinel_for_null_allowed": False,
        "distinctness_unit": [
            "source_field",
            "typed_state",
            "exact_raw_value_when_nonnull",
        ],
    }.items():
        expect(typed, key, value, "typed_value_contract")

    private = table("private_artifact")
    for key, value in {
        "raw_values_allowed": True,
        "patient_identifiers_allowed": False,
        "event_identifiers_allowed": False,
        "event_timestamps_allowed": False,
        "directory_mode": "0700",
        "file_mode": "0600",
        "git_ignored_required": True,
        "persist_only_after_explicit_rollback_and_clean_exit": True,
        "per_value_hashes_may_be_published": False,
    }.items():
        expect(private, key, value, "private_artifact")

    public = table("public_artifact")
    for key, value in {
        "raw_values_allowed": False,
        "local_ndc_values_allowed": False,
        "patient_or_event_data_allowed": False,
        "allowed_content": [
            "per-field aggregate counts",
            "typed-state and nonnull-substate aggregate counts",
            "per-field whole typed-distinct-set SHA-256",
            "whole private artifact SHA-256",
            "execution controls, durations and audit totals",
        ],
    }.items():
        expect(public, key, value, "public_artifact")

    execution = table("execution")
    for key, value in {
        "status": "not_executed",
        "transaction_isolation": "repeatable read",
        "transaction_read_only": True,
        "statement_timeout_ms": 120000,
        "all_five_sql_statements_share_one_snapshot": True,
        "explicit_rollback_required": True,
        "clean_psql_exit_required": True,
        "buffer_results_until_rollback_and_clean_exit": True,
        "persist_private_results_after_rollback_and_clean_exit_only": True,
        "database_mutation_allowed": False,
        "temporary_database_objects_allowed": False,
        "print_controlled_raw_values": False,
        "emit_patient_identifiers_or_times": False,
        "any_statement_failure_discards_all_results": True,
    }.items():
        expect(execution, key, value, "execution")

    typed_hash = table("typed_set_hash_contract")
    for key, value in {
        "algorithm": "sha256",
        "version": "typed-distinct-source-value-set-v1",
        "unit": "one independent hash per source_field",
        "includes_frequencies": False,
        "includes_source_field": True,
        "includes_sql_null_presence": True,
        "includes_every_exact_nonnull_value": True,
        "record_order": (
            "sql_null token first when present, then nonnull records sorted by "
            "unsigned raw UTF-8 bytes"
        ),
        "field_prefix_encoding": (
            "uint32 big-endian byte length followed by source_field UTF-8 bytes"
        ),
        "sql_null_record_encoding": "single byte 0x00",
        "nonnull_record_encoding": (
            "single byte 0x01, uint64 big-endian raw UTF-8 byte length, then "
            "exact raw UTF-8 bytes"
        ),
        "hash_input_encoding": (
            "ASCII version bytes, field prefix, uint64 big-endian record count, "
            "then ordered typed records"
        ),
        "empty_string_unambiguous": True,
        "whitespace_preserved_exactly": True,
    }.items():
        expect(typed_hash, key, value, "typed_set_hash_contract")

    replay = table("cross_run_route_replay")
    for key, value in {
        "preflight_and_query202_are_separate_database_runs": True,
        "each_run_has_its_own_internal_single_snapshot": True,
        "cross_lifecycle_same_snapshot_claim_allowed": False,
        "human_route_adjudication_occurs_between_runs": True,
        "human_route_adjudication_is_output_of_this_component": False,
        "separate_versioned_route_mapping_artifact_required": True,
        "route_mapping_must_be_frozen_before_query202": True,
        "formal_query202_must_replay_all_three_route_fields": True,
        "formal_query202_must_recompute_hash_per_source_field": True,
        "formal_query202_requires_exact_preflight_hash_match": True,
        "new_route_value_fails_closed": True,
        "missing_preflight_route_value_fails_closed": True,
        "null_presence_change_fails_closed": True,
        "hash_mismatch_discards_query202_outputs": True,
        "hash_mismatch_requires_new_preflight_and_route_adjudication_version": True,
    }.items():
        expect(replay, key, value, "cross_run_route_replay")

    acceptance = table("acceptance")
    for key, value in {
        "exactly_five_source_fields_required": True,
        "exactly_three_route_fields_required": True,
        "every_source_field_scanned_without_sampling_or_semantic_filter": True,
        "typed_null_nonnull_empty_whitespace_nonblank_conserve_source_rows": True,
        "typed_distinct_values_unique_within_source_field": True,
        "private_raw_artifact_required": True,
        "public_summary_aggregate_and_whole_set_hash_only": True,
        "single_read_only_repeatable_read_snapshot_required": True,
        "every_statement_completes_within_120_seconds": True,
        "explicit_rollback_and_clean_exit_required": True,
        "independent_offline_audit_failures_required": 0,
        "route_mapping_absent": True,
        "external_requests_absent": True,
        "product_event_and_source_policy_absent": True,
        "query202_route_replay_contract_frozen": True,
    }.items():
        expect(acceptance, key, value, "acceptance")

    implementation = table("implementation_hashes")
    for key, value in {
        "bundle_hash_encoding": (
            "for each configured path in order: uint32 big-endian path UTF-8 "
            "byte length, path UTF-8 bytes, uint64 big-endian content length, "
            "exact file bytes"
        ),
        "sql_paths": [str(path) for path in _POTASSIUM_MAPPING_PREFLIGHT_SQL_PATHS],
        "runner_paths": [
            str(path) for path in _POTASSIUM_MAPPING_PREFLIGHT_RUNNER_PATHS
        ],
        "offline_auditor_paths": [
            str(path) for path in _POTASSIUM_MAPPING_PREFLIGHT_AUDITOR_PATHS
        ],
    }.items():
        expect(implementation, key, value, "implementation_hashes")
    for key in (
        "sql_bundle_sha256",
        "runner_bundle_sha256",
        "offline_auditor_bundle_sha256",
    ):
        digest = implementation.get(key)
        if not isinstance(digest, str) or not _HEX_SHA256.fullmatch(digest):
            errors.append(
                f"implementation_hashes.{key} must be a lowercase SHA-256; "
                "execution placeholders are not a runnable preregistration"
            )
    expect(
        implementation,
        "placeholders_allowed_only_while_not_executed",
        True,
        "implementation_hashes",
    )
    expect(
        implementation,
        "execution_requires_lowercase_64_hex_hashes",
        True,
        "implementation_hashes",
    )

    controls = table("change_control")
    for key, value in {
        "selection_must_not_depend_on": [
            "paper sample size",
            "action distribution",
            "label coverage",
            "model accuracy",
            "OPE error",
            "agreement with paper figures",
        ],
        "changing_any_field_or_hash_contract_requires_new_component_version": True,
        "downstream_artifacts_must_record": [
            "component_id",
            "rule_version",
            "config_sha256",
        ],
    }.items():
        expect(controls, key, value, "change_control")

    guards = config.get("guards")
    expected_guards = {
        "preflight_executed",
        "route_mapping_created",
        "route_mapping_frozen",
        "external_api_called",
        "product_identity_decided",
        "event_mapping_created",
        "final_source_policy",
        "formal_action",
        "formal_episode",
        "zero_action_constructed",
        "formal_non_icu_rule",
        "formal_label",
        "formal_cohort",
        "patient_data_exported",
        "llm_called",
    }
    if not isinstance(guards, dict):
        errors.append("guards must be a table")
        guards = {}
    elif set(guards) != expected_guards:
        errors.append("guards must contain the exact preflight guard set")
    for key in sorted(expected_guards):
        expect(guards, key, False, "guards")

    evidence = config.get("evidence")
    if not isinstance(evidence, list):
        errors.append("evidence must be an array of exactly five tables")
    else:
        observed: list[tuple[object, object, object, object]] = []
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                errors.append(f"evidence[{index}] must be a table")
                continue
            observed.append(
                (
                    item.get("name"),
                    item.get("path"),
                    item.get("file_sha256"),
                    item.get("supports"),
                )
            )
            path = item.get("path")
            if (
                not isinstance(path, str)
                or not path
                or Path(path).is_absolute()
                or ".." in Path(path).parts
            ):
                errors.append(
                    f"evidence[{index}].path must be a safe project-relative path"
                )
            digest = item.get("file_sha256")
            if not isinstance(digest, str) or not _HEX_SHA256.fullmatch(digest):
                errors.append(
                    f"evidence[{index}].file_sha256 must be a lowercase SHA-256"
                )
        if observed != list(_POTASSIUM_MAPPING_PREFLIGHT_EVIDENCE):
            errors.append(
                "evidence must contain the exact ordered D005 preflight baseline set"
            )

    return errors


def potassium_mapping_preflight_preregistration_report(root: Path) -> dict:
    """Validate preflight boundaries, evidence, and executable input hashes."""
    path = root / POTASSIUM_MAPPING_PREFLIGHT_PATH
    config = read_potassium_mapping_preflight_preregistration(root)
    errors = validate_potassium_mapping_preflight_preregistration(config)
    checked_evidence = 0
    for item in config.get("evidence", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            continue
        evidence_path = root / relative
        if not evidence_path.is_file():
            errors.append(f"Required local evidence file is absent: {relative}")
            continue
        checked_evidence += 1
        expected = item.get("file_sha256")
        if isinstance(expected, str) and _sha256(evidence_path) != expected:
            errors.append(f"Evidence hash mismatch: {relative}")

    implementation = config.get("implementation_hashes", {})
    implementation_bundles: dict[str, dict] = {}
    bundles_verified = isinstance(implementation, dict)
    if isinstance(implementation, dict):
        for name, paths, digest_key in (
            (
                "sql",
                _POTASSIUM_MAPPING_PREFLIGHT_SQL_PATHS,
                "sql_bundle_sha256",
            ),
            (
                "runner",
                _POTASSIUM_MAPPING_PREFLIGHT_RUNNER_PATHS,
                "runner_bundle_sha256",
            ),
            (
                "offline_auditor",
                _POTASSIUM_MAPPING_PREFLIGHT_AUDITOR_PATHS,
                "offline_auditor_bundle_sha256",
            ),
        ):
            bundle = _implementation_bundle(root, paths)
            expected = implementation.get(digest_key)
            bundle["expected_sha256"] = expected
            implementation_bundles[name] = bundle
            if bundle["missing"]:
                bundles_verified = False
                errors.append(
                    f"Required preflight {name} files are absent: "
                    + ", ".join(bundle["missing"])
                )
            if bundle["actual_sha256"] != expected:
                bundles_verified = False
                errors.append(f"Implementation bundle hash mismatch: {name}")

    guards = config.get("guards", {})
    return {
        "component_id": config.get("component_id"),
        "status": config.get("status"),
        "execution_status": config.get("execution", {}).get("status"),
        "formal_product_mapping_enabled": config.get("formal_mapping_enabled"),
        "formal_source_policy_enabled": config.get("formal_source_policy_enabled"),
        "route_mapping_frozen": guards.get("route_mapping_frozen"),
        "external_ndc_mapping_executed": guards.get("external_api_called"),
        "implementation_hashes_verified": bundles_verified,
        "implementation_bundles": implementation_bundles,
        "config": str(POTASSIUM_MAPPING_PREFLIGHT_PATH),
        "config_sha256": _sha256(path),
        "valid": not errors,
        "errors": errors,
        "warnings": [],
        "evidence_files_checked": checked_evidence,
    }
