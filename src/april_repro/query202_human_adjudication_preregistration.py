"""Fail-closed proposal report for Query-202 human adjudication.

The report authenticates the public lineage documents and hashes the three
private source streams as opaque files.  It never decompresses or parses those
streams.  A valid proposal is deliberately distinct from permission to create
an adjudication workspace.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import tomllib
from typing import Any, Mapping, Sequence


CONFIG_PATH = Path(
    "config/preregistrations/d005_potassium_query202_human_adjudication.toml"
)
COMPONENT_ID = "D005-K-QUERY202-HUMAN-ADJUDICATION-v1"
SOURCE_COMPONENT_ID = "D005-K-QUERY202-ADJUDICATION-INPUT-v1"
NDC_COMPONENT_ID = "D005-K-QUERY202-NDC-EVIDENCE-MODE-v1"
PLACEHOLDER = "UNSET_REQUIRED_BEFORE_FREEZE"
BUNDLE_ENCODING = "uint32be_path_length+path_utf8+uint64be_content_length+content"
PREREGISTRATION_VALIDATOR_PATH = (
    "src/april_repro/query202_human_adjudication_preregistration.py"
)

EXPECTED_GENERATOR_PATHS = (
    "src/april_repro/__init__.py",
    PREREGISTRATION_VALIDATOR_PATH,
    "src/april_repro/query202_human_adjudication.py",
    "src/april_repro/query202_human_adjudication_writer.py",
    "scripts/initialize_potassium_query202_human_adjudication.py",
    "scripts/validate_potassium_query202_human_adjudication.py",
    "scripts/apply_potassium_query202_human_adjudication_transaction.py",
    "scripts/attest_potassium_query202_human_adjudication_tests.py",
    "src/april_repro/query202_human_adjudication_finalize.py",
    "scripts/compile_potassium_query202_human_adjudication.py",
    "scripts/freeze_potassium_query202_human_adjudication.py",
)
EXPECTED_AUDITOR_PATHS = (
    "src/april_repro/__init__.py",
    "src/april_repro/query202_human_adjudication_audit.py",
    "scripts/audit_potassium_query202_human_adjudication.py",
)
EXPECTED_IMPLEMENTATION_PATHS = {
    "generator": EXPECTED_GENERATOR_PATHS,
    "auditor": EXPECTED_AUDITOR_PATHS,
}

TEST_ATTESTATION_PATH = (
    "config/attestations/query202-human-adjudication-tests.json"
)
REQUIRED_TEST_PATHS = (
    "tests/test_query202_human_adjudication_preregistration.py",
    "tests/test_query202_human_adjudication_control_plane.py",
    "tests/test_query202_human_adjudication.py",
    "tests/test_query202_human_adjudication_writer.py",
    "tests/test_query202_human_adjudication_audit.py",
    "tests/test_query202_human_adjudication_finalize.py",
)
TEST_COMMAND_ARGV = (
    ".venv/bin/python",
    "-m",
    "unittest",
    "tests.test_query202_human_adjudication_preregistration",
    "tests.test_query202_human_adjudication_control_plane",
    "tests.test_query202_human_adjudication",
    "tests.test_query202_human_adjudication_writer",
    "tests.test_query202_human_adjudication_audit",
    "tests.test_query202_human_adjudication_finalize",
    "-v",
)
TEST_COMMAND_ENV = (
    ("HOME", ".attestation-home"),
    ("LC_ALL", "C"),
    ("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
    ("PYTHONDONTWRITEBYTECODE", "1"),
    ("PYTHONHASHSEED", "0"),
    ("PYTHONNOUSERSITE", "1"),
    ("PYTHONPATH", "src:."),
    ("PYTHONUTF8", "1"),
    ("TMPDIR", ".attestation-tmp"),
)
TEST_COMMAND = " ".join(
    [*(f"{key}={value}" for key, value in TEST_COMMAND_ENV), *TEST_COMMAND_ARGV]
)
TEST_EXECUTION_SNAPSHOT_ENCODING = (
    "ordered-path+normalized-config-or-file-sha256+size+mode+nlink-v2"
)
ORDERED_TEST_IDS_ENCODING = "uint32be-id-length+id-utf8-v1"
MUTATION_TEST_IDS_ENCODING = "canonical-json-utf8-sort-keys-no-whitespace-v1"
STATIC_TEST_SUPPORT_PATHS = (
    "tests/__init__.py",
    "Makefile",
    "scripts/report_potassium_query202_human_adjudication.py",
    "src/april_repro/cli.py",
    "src/april_repro/preregistration.py",
    "config/preregistrations/d005_potassium_query202_human_adjudication.toml",
    "config/preregistrations/d005_potassium_query202_adjudication_input.toml",
    "config/preregistrations/d005_potassium_query202_ndc_evidence_mode.toml",
)
TEST_EXECUTION_PATHS = tuple(
    dict.fromkeys(
        (
            *EXPECTED_GENERATOR_PATHS,
            *EXPECTED_AUDITOR_PATHS,
            *REQUIRED_TEST_PATHS,
            *STATIC_TEST_SUPPORT_PATHS,
        )
    )
)
EXPECTED_TEST_COUNT = 135
EXPECTED_ORDERED_TEST_IDS_SHA256 = (
    "21016a33a706a060279241c5b0ecba304369de3d7fda5cc5b9ba45512797abc9"
)
REQUIRED_MUTATION_CLASSES = (
    "missing_duplicate_or_conflicting_review_records",
    "stale_base_or_revision_chain_tamper",
    "forged_or_ineligible_evidence_reference",
    "reviewer_identity_or_human_attestation_tamper",
    "privacy_permission_or_gitignore_tamper",
    "symlink_parent_swap_or_toctou_tamper",
    "final_output_audit_or_freeze_inventory_tamper",
    "implementation_bundle_drift",
    "test_command_file_order_count_or_result_drift",
    "scientific_contract_or_lifecycle_gate_drift",
)
EXPECTED_MUTATION_TEST_IDS = {
    "missing_duplicate_or_conflicting_review_records": [
        "tests.test_query202_human_adjudication.HumanAdjudicationWorkspaceTests.test_missing_cross_batch_and_conflicting_revision_fail_closed",
        "tests.test_query202_human_adjudication_writer.HumanAdjudicationWriterTests.test_duplicate_revision_operation_and_invalid_reference_fail_closed",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_unsafe_permission_and_conflicting_revision_fail_closed",
    ],
    "stale_base_or_revision_chain_tamper": [
        "tests.test_query202_human_adjudication_writer.HumanAdjudicationWriterTests.test_stale_base_and_reviewer_mismatch_fail_without_mutation",
        "tests.test_query202_human_adjudication.HumanAdjudicationWorkspaceTests.test_noninitial_unreviewed_revision_is_rejected",
        "tests.test_query202_human_adjudication.HumanAdjudicationWorkspaceTests.test_nested_event_serialization_policy_is_exact",
    ],
    "forged_or_ineligible_evidence_reference": [
        "tests.test_query202_human_adjudication.HumanAdjudicationWorkspaceTests.test_invalid_mapping_group_member_fails_closed",
        "tests.test_query202_human_adjudication.HumanAdjudicationWorkspaceTests.test_reviewed_schema_requires_registered_evidence_and_cannot_complete_without_attestation",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_forged_general_local_tuple_reference_fails_closed",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_source_derivation_rejects_valid_but_semantically_wrong_index",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_source_derivation_rejects_truncation_and_member_mismatch",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_source_derivation_detects_in_read_source_toctou",
    ],
    "reviewer_identity_or_human_attestation_tamper": [
        "tests.test_query202_human_adjudication_writer.HumanAdjudicationWriterTests.test_full_human_decision_attestation_and_completion_flow",
        "tests.test_query202_human_adjudication.HumanAdjudicationWorkspaceTests.test_all_reviewed_requires_current_batch_attestations",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_single_global_reviewer_mismatch_fails_closed",
    ],
    "privacy_permission_or_gitignore_tamper": [
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_private_streams_are_only_hashed_as_opaque_files",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_report_contains_only_public_aggregate_facts",
        "tests.test_query202_human_adjudication_control_plane.HumanAdjudicationControlPlaneTests.test_test_attestation_command_emits_only_aggregate_status",
        "tests.test_query202_human_adjudication_control_plane.HumanAdjudicationControlPlaneTests.test_test_attestation_rejects_oversized_existing_file_before_read",
        "tests.test_query202_human_adjudication_writer.HumanAdjudicationWriterTests.test_cli_failure_output_is_aggregate_only",
        "tests.test_query202_human_adjudication_writer.HumanAdjudicationWriterTests.test_transaction_byte_bound_is_exact_prechecked_and_hard_limited",
        "tests.test_query202_human_adjudication_writer.HumanAdjudicationWriterTests.test_document_cumulative_limits_hold_before_and_after_stage_import",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_candidate_rejects_unsafe_attestation_dependency_and_source_links",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_in_place_chmod_during_read_fails_closed",
        "tests.test_query202_human_adjudication_writer.HumanAdjudicationWriterTests.test_hard_linked_private_request_is_rejected",
        "tests.test_query202_human_adjudication_writer.HumanAdjudicationWriterTests.test_transaction_hard_link_added_during_run_fails_closure",
        "tests.test_query202_human_adjudication_writer.HumanAdjudicationWriterTests.test_versioned_document_import_checks_hash_mode_and_tamper",
        "tests.test_query202_human_adjudication_writer.HumanAdjudicationWriterTests.test_versioned_document_size_and_final_link_closure",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_mode_mutation_during_snapshot_closure_is_detected",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_source_and_workspace_private_hardlinks_fail_independent_audit",
    ],
    "symlink_parent_swap_or_toctou_tamper": [
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_parent_directory_swap_to_symlink_fails_closed",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_builder_executes_staged_snapshot_despite_live_test_parent_aba",
        "tests.test_query202_human_adjudication_control_plane.HumanAdjudicationControlPlaneTests.test_test_attestation_publish_rejects_raced_temporary_replacement",
        "tests.test_query202_human_adjudication_control_plane.HumanAdjudicationControlPlaneTests.test_test_attestation_cleanup_preserves_raced_replacement",
        "tests.test_query202_human_adjudication.HumanAdjudicationWorkspaceTests.test_root_anchored_traversal_rejects_parent_symlink_swap",
        "tests.test_query202_human_adjudication.HumanAdjudicationWorkspaceTests.test_initialization_temp_leaf_replacement_cannot_redirect_private_writes",
        "tests.test_query202_human_adjudication_writer.HumanAdjudicationWriterTests.test_workspace_parent_swap_before_stage_validation_fails_closed",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_parent_directory_symlink_swap_is_detected",
        "tests.test_query202_human_adjudication_finalize.HumanAdjudicationFinalizeTests.test_compile_rejects_final_parent_symlink_swap_and_cleans_temp",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_builder_rejects_runtime_locator_retarget_to_same_target",
        "tests.test_query202_human_adjudication_writer.HumanAdjudicationWriterTests.test_lock_inode_replacement_before_exchange_fails_and_rolls_back",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_final_audit_artifact_ancestor_swap_fails_without_audit",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_final_audit_workspace_ancestor_swap_rolls_back_audit",
        "tests.test_query202_human_adjudication_finalize.HumanAdjudicationFinalizeTests.test_freeze_rejects_hardlink_directory_swap_and_cleans_temp",
        "tests.test_query202_human_adjudication_finalize.HumanAdjudicationFinalizeTests.test_freeze_preserves_raced_temp_replacement_and_rolls_back_link",
    ],
    "final_output_audit_or_freeze_inventory_tamper": [
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_final_audit_rejects_inventory_mode_and_workspace_document_tamper",
        "tests.test_query202_human_adjudication_finalize.HumanAdjudicationFinalizeTests.test_failed_or_rebound_audit_cannot_freeze",
        "tests.test_query202_human_adjudication_finalize.HumanAdjudicationFinalizeTests.test_separate_freeze_binds_audit_and_never_mutates_existing_outputs",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_final_audit_rejects_compiled_output_hardlink",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_final_audit_rejects_noncontracted_directory_name_without_mutation",
        "tests.test_query202_human_adjudication_finalize.HumanAdjudicationFinalizeTests.test_compile_keeps_test_execution_closure_through_publication",
        "tests.test_query202_human_adjudication_finalize.HumanAdjudicationFinalizeTests.test_freeze_requires_exact_final_audit_check_summary",
        "tests.test_query202_human_adjudication_finalize.HumanAdjudicationFinalizeTests.test_freeze_rejects_post_audit_gate_workspace_and_output_link_tamper",
        "tests.test_query202_human_adjudication_finalize.HumanAdjudicationFinalizeTests.test_freeze_closure_rejects_deleted_replaced_chmoded_and_mutated_test_file",
        "tests.test_query202_human_adjudication_finalize.HumanAdjudicationFinalizeTests.test_freeze_post_link_closure_rolls_back_all_dependency_tamper",
    ],
    "implementation_bundle_drift": [
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_available_generator_in_place_mutation_breaks_global_closure",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_registered_bundle_paths_are_exact_ordered_and_symlink_safe",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_generator_inventory_matches_workspace_and_independent_auditor",
        "tests.test_query202_human_adjudication_finalize.HumanAdjudicationFinalizeTests.test_compile_rejects_contaminated_auditor_cli_bundle",
    ],
    "test_command_file_order_count_or_result_drift": [
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_builder_runs_the_exact_suite_and_accepts_no_claimed_result",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_attestation_verifier_rejects_every_bound_field_mutation",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_builder_rejects_skipped_expected_failure_and_unexpected_success_results",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_execution_dependency_manifest_rejects_drift",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_builder_rejects_python_runtime_drift_across_staged_execution",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_attestation_and_test_file_are_in_two_pass_snapshot_closure",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_execution_snapshot_matches_independent_auditor_and_binds_mode_nlink",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_auditor_requires_attestation_and_every_attested_test_file",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_auditor_runtime_closure_rejects_locator_retarget_to_same_target",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_test_attestation_or_bound_test_file_tamper_fails_independent_audit",
    ],
    "scientific_contract_or_lifecycle_gate_drift": [
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_freeze_candidate_and_frozen_lifecycle_are_separate",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_status_flip_or_hash_fill_alone_cannot_enable_execution",
        "tests.test_query202_human_adjudication_preregistration.Query202HumanAdjudicationPreregistrationTests.test_implemented_state_without_verified_attestation_fails_closed",
        "tests.test_query202_human_adjudication_control_plane.HumanAdjudicationControlPlaneTests.test_test_attestation_command_refuses_candidate_and_frozen_rewrite",
        "tests.test_query202_human_adjudication.HumanAdjudicationWorkspaceTests.test_formal_initialization_and_validation_require_exact_preregistration_readiness",
        "tests.test_query202_human_adjudication_audit.IndependentHumanAdjudicationAuditTests.test_exact_formal_root_and_empty_execution_gate_are_required",
        "tests.test_query202_human_adjudication_finalize.HumanAdjudicationFinalizeTests.test_contract_capture_rejects_attestation_changed_around_semantic_report",
    ],
}
EXPECTED_MUTATION_TEST_IDS_SHA256 = hashlib.sha256(
    json.dumps(
        EXPECTED_MUTATION_TEST_IDS,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()
TEST_ATTESTATION_KEYS = frozenset(
    {
        "schema_version",
        "component_id",
        "status",
        "test_command",
        "test_command_argv",
        "test_command_environment",
        "tests_run",
        "failures",
        "errors",
        "scientific_contract_sha256",
        "implementation_bundles",
        "test_files",
        "mutation_classes_passed",
        "ordered_test_ids_sha256",
        "mutation_test_ids_sha256",
        "execution_snapshot",
        "python_runtime",
    }
)
TEST_ATTESTATION_FILE_KEYS = frozenset({"path", "file_sha256"})
TEST_ATTESTATION_BUNDLE_KEYS = frozenset({"name", "bundle_sha256"})
TEST_ATTESTATION_EXECUTION_SNAPSHOT_KEYS = frozenset(
    {"encoding", "file_count", "aggregate_sha256"}
)
TEST_ATTESTATION_PYTHON_RUNTIME_KEYS = frozenset(
    {"binding", "implementation", "version", "executable_sha256", "executable_bytes"}
)

EXPECTED_SEMANTIC_TEMPLATE = {
    "file": "semantic-review-template.jsonl.gz",
    "stored_sha256": "7c049c4f946525436c5a26f004930f4bccfc83aa035da29c3349b1890d72e1b4",
    "stored_bytes": 412_019,
    "raw_sha256": "983be02615aaf9ca3582d2e1b02bf6567d0bf02303dc6a486857de68dac3d887",
    "raw_bytes": 15_439_475,
    "records": 34_569,
    "semantic_keys": 34_565,
    "semantic_key_set_sha256": "cee42c49d4618e6c62e99dcea26c53166f21305231b3c35991d2c2534b94368a",
}
EXPECTED_LOCAL_EVIDENCE = {
    "file": "local-evidence.jsonl.gz",
    "stored_sha256": "5305cf33885d7afc42d9ac01fda060d453026de6c13b0c3aa0e11bdeeb1a228d",
    "stored_bytes": 30_753_881,
    "raw_sha256": "271acbbfc99fe81cc8e23f998023a6abe5f118176b28bc4e30a81e8408345468",
    "raw_bytes": 1_098_608_356,
    "records": 1_861_507,
    "unique_tuples": 1_861_485,
    "total_multiplicity": 392_077_967,
}
EXPECTED_LOCAL_EVIDENCE_INDEX = {
    "file": "evidence-registry/local-evidence-bridge-index.bin",
    "encoding": "u8-member-count+4xu32be-review-sequence-zero-padded-v1",
    "source_local_evidence_raw_sha256": EXPECTED_LOCAL_EVIDENCE["raw_sha256"],
    "record_bytes": 17,
    "index_records": 793_186,
    "index_bytes": 13_484_162,
    "index_sha256": "49b1098ace57f3f897a61e3a73b8777ecfe8e507c79cf26c8cae5355ee716322",
    "all_stage_kind_order": [
        "202b:detail_product_context",
        "202b:detail_seed_membership_bridge",
        "202b:emar_medication_detail_bridge",
        "202b:emar_medication_head_partition",
        "202c:pharmacy_product_context",
        "202c:pharmacy_prescription_bridge",
        "202c:prescription_identifier_context",
        "202c:head_pharmacy_prescription_bridge",
        "202c:pharmacy_no_prescription_component",
        "202c:detail_pharmacy_prescription_bridge",
    ],
    "all_stage_kind_ordinal_counts": [
        137_579,
        49_648,
        48_825,
        5_045,
        717_377,
        236_630,
        208_209,
        172_567,
        89,
        285_516,
    ],
    "bridge_stage_kind_order": [
        "202b:detail_seed_membership_bridge",
        "202b:emar_medication_detail_bridge",
        "202c:pharmacy_prescription_bridge",
        "202c:head_pharmacy_prescription_bridge",
        "202c:detail_pharmacy_prescription_bridge",
    ],
    "bridge_block_offsets": [0, 49_648, 98_473, 335_103, 507_670],
    "bridge_block_counts": [49_648, 48_825, 236_630, 172_567, 285_516],
}
EXPECTED_ROUTE_TEMPLATE = {
    "file": "route-review-template.jsonl.gz",
    "stored_sha256": "8ac9d80b9f085af9354960afe0005652075a5f4dbfd46bb574cbe335831f608a",
    "stored_bytes": 6_900,
    "raw_sha256": "06425be639eda2691dfc05c0c1703420b58a28cbe1a09f0c75b0169eec426bde",
    "raw_bytes": 145_193,
    "records": 357,
    "canonical_exact_nonnull_values": 117,
    "source_specific_nonnull_memberships": 233,
    "source_specific_sql_null_memberships": 3,
    "source_specific_typed_memberships": 236,
    "canonical_exact_set_sha256": "86092716757590b14e190c2967016b7428c01837a60dc7a8965300e2853030b5",
}
EXPECTED_SOURCE_ARTIFACT = {
    "directory": "artifacts/query202-adjudication-input/20261013T063022.591471Z",
    "component_id": SOURCE_COMPONENT_ID,
    "source_config_path": "config/preregistrations/d005_potassium_query202_adjudication_input.toml",
    "source_config_sha256": "ed3f656243adbbf0060731e0ef6323b5dadb58e5c614691dd67eda97cd638f3d",
    "manifest_file": "manifest.json",
    "manifest_sha256": "cd99bafbf5b8567edae8de1c1430a2b1e3ecb4501eb238190f59270b0bd717d6",
    "aggregate_summary_file": "aggregate-summary.json",
    "aggregate_summary_sha256": "a10198946acf86a3a327d95eaa5eff53952275495b7befa59f7087d72e98644f",
    "audit_file": "audit-summary.json",
    "audit_sha256": "07a442689e6be15c98f05a817737a67ca6c0637f176a68e68c75a7d36cadb851",
    "audit_status": "passed",
    "audit_failed_checks": 0,
    "semantic_template": EXPECTED_SEMANTIC_TEMPLATE,
    "local_evidence": EXPECTED_LOCAL_EVIDENCE,
    "route_template": EXPECTED_ROUTE_TEMPLATE,
}
EXPECTED_NDC_DECISION = {
    "config_path": "config/preregistrations/d005_potassium_query202_ndc_evidence_mode.toml",
    "config_sha256": "6f31bd22a21e36b506d84e68dd8d03bcbfe62df857f82812f6057ecd2cab2216",
    "validator_bundle_sha256": "257300995bbae47a3fa3fd26b223b0842031de3093044f4ce9c0ae8e0b7c88bc",
    "required_status": "frozen",
    "required_mode": "not_used_frozen",
    "required_effective": True,
    "ndc_handoff_rows_may_be_read": False,
}

EXPECTED_LIFECYCLE = {
    "phase": "post_extraction_human_adjudication",
    "predecessor_component_id": SOURCE_COMPONENT_ID,
    "predecessor_must_be_complete_and_independently_audited": True,
    "ndc_mode_component_id": NDC_COMPONENT_ID,
    "ndc_mode_must_be_frozen_and_effective": True,
    "allowed_states": [
        "not_initialized",
        "initialized",
        "review_in_progress",
        "human_review_complete_unfrozen",
        "audited_unfrozen",
        "separately_frozen",
    ],
    "initialization_makes_scientific_decisions": False,
    "all_items_reviewed_implies_frozen": False,
    "independent_audit_implies_clinical_correctness": False,
    "separate_freeze_required": True,
}
EXPECTED_WORKSPACE = {
    "artifact_parent": "artifacts/query202-human-adjudication-workspace",
    "semantic_batch_size": 250,
    "semantic_batch_count": 139,
    "route_batch_count": 1,
    "semantic_id_format": "S%06d",
    "route_id_format": "R%06d",
    "id_sequence_starts_at": 1,
    "ids_are_private_references_not_canonical_keys": True,
    "batch_assignment": "source-template-order contiguous fixed-size partition",
    "immutable_source_views_separate_from_editable_decision_ledgers": True,
    "each_editable_batch_binds_immutable_base_sha256": True,
    "batch_overlap_allowed": False,
    "batch_omission_allowed": False,
    "last_write_wins_allowed": False,
    "immutable_source_fields_may_be_edited": False,
    "private_directory_mode": "0700",
    "private_file_mode": "0600",
    "git_ignored_required": True,
    "public_raw_values_allowed": False,
    "public_per_value_hashes_allowed": False,
    "stdout_raw_values_allowed": False,
    "strict_workspace_inventory_required": True,
    "allowed_top_level_entries": [
        "workspace-manifest.json",
        "workspace-events.jsonl",
        "semantic-source",
        "semantic-decisions",
        "semantic-groups",
        "route-source",
        "route-decisions",
        "evidence-registry",
        "attestations",
        "revisions",
    ],
}
EXPECTED_SEMANTIC_REVIEW = {
    "dimensions": [
        "product_identity",
        "dosage_form",
        "treatment_intent",
        "potassium_content",
        "meq_convertibility",
    ],
    "status_values": ["supported", "refuted", "uncertain"],
    "review_status_values": ["unreviewed", "reviewed"],
    "initial_status": "uncertain",
    "initial_review_status": "unreviewed",
    "reviewed_uncertain_allowed": True,
    "nonuncertain_requires_evidence_refs": True,
    "reviewed_requires_human_reviewer_id": True,
    "reviewed_requires_strict_utc_time": True,
    "reviewed_requires_nonempty_rationale": True,
    "reviewed_uncertain_requires_insufficiency_or_conflict_rationale": True,
    "software_may_set_reviewed": False,
    "llm_may_set_reviewed": False,
    "normalization_may_establish_semantics": False,
    "string_similarity_may_establish_semantics": False,
    "propositions": {
        "product_identity": "The exact source-field value has an adequately evidenced medication product or ingredient identity for later component interpretation.",
        "dosage_form": "The exact source-field value supports or refutes an intravenously compatible dosage form; event-level route remains a separate decision.",
        "treatment_intent": "The exact source-field value supports or refutes compatibility with potassium repletion at the vocabulary level; it does not decide the intent of a specific event.",
        "potassium_content": "The exact source-field value supports or refutes therapeutically relevant potassium content.",
        "meq_convertibility": "The exact source-field value supports or refutes that a later context-specific recorded-dose rule can convert the product amount to potassium mEq using documented evidence; this review does not calculate an action dose.",
    },
    "values": {
        "field": "value",
        "type": "private object with exact keys code and candidates",
        "code_type": "controlled UTF-8 string",
        "candidates_type": "ordered list of private nonempty UTF-8 strings",
        "candidates_preserve_conflicts_and_one_to_many_results": True,
        "supported_or_refuted_requires_evidence_refs": True,
        "uncertain_may_preserve_candidate_values": True,
        "value_is_not_a_status": True,
        "value_is_not_an_action_dose": True,
        "product_identity": {
            "supported_code": "identified_medication_product_or_ingredient",
            "refuted_code": "not_medication_product_or_ingredient",
            "uncertain_code": "unresolved_or_conflicting_product_identity",
        },
        "dosage_form": {
            "supported_code": "iv_compatible_dosage_form",
            "refuted_code": "not_iv_compatible_dosage_form",
            "uncertain_code": "unresolved_or_conflicting_iv_compatibility",
        },
        "treatment_intent": {
            "supported_code": "potassium_repletion_compatible",
            "refuted_code": "not_potassium_repletion_compatible",
            "uncertain_code": "unresolved_or_conflicting_repletion_compatibility",
        },
        "potassium_content": {
            "supported_code": "therapeutic_potassium_present",
            "refuted_code": "therapeutic_potassium_absent",
            "uncertain_code": "unresolved_or_conflicting_potassium_content",
        },
        "meq_convertibility": {
            "supported_code": "contextually_convertible_to_potassium_meq",
            "refuted_code": "not_convertible_to_potassium_meq",
            "uncertain_code": "unresolved_or_conflicting_meq_convertibility",
            "actual_conversion_factor_deferred_to_recorded_dose_component": True,
        },
    },
}
EXPECTED_HUMAN_REVIEW_POLICY = {
    "reviewer_model": "single_reviewer_with_full_attestation",
    "allowed_models": [
        "single_reviewer_with_full_attestation",
        "dual_independent_with_conflict_adjudication",
    ],
    "selection_is_project_choice_not_paper_fact": True,
    "single_reviewer_identity_must_match_all_item_group_revision_and_batch_attestation_records": True,
    "dual_review_requires_new_component_version": True,
    "batch_attestation_required": True,
    "attestation_binds_batch_sha256": True,
    "attestation_binds_review_policy_version": True,
    "attestation_requires_reviewer_id_and_strict_utc_time": True,
    "automated_attestation_allowed": False,
}
EXPECTED_REVISIONS = {
    "append_only": True,
    "active_revision_per_item": 1,
    "supersedes_sha256_required_after_first_revision": True,
    "revision_reason_required": True,
    "identical_resubmission_is_idempotent": True,
    "conflicting_active_revisions_fail_closed": True,
    "last_write_wins_allowed": False,
    "canonical_revision_serialization": "canonical-json-utf8-sort-keys-no-whitespace-v1",
    "revision_sha256_binds_item_id_base_sha256_decision_provenance_and_previous_revision": True,
    "group_registry_change_invalidates_affected_batch_attestations": True,
}
EXPECTED_REVIEW_WRITER = {
    "schema_version": 1,
    "transaction_schema_version": 1,
    "transaction_type": "human_adjudication_update",
    "transaction_exact_schema_required": True,
    "workspace_snapshot_hash_version": (
        "query202-human-workspace-file-snapshot-v1"
    ),
    "max_transaction_bytes": 16 * 1024 * 1024,
    "max_evidence_document_bytes": 128 * 1024 * 1024,
    "max_imported_document_bytes_per_transaction": 256 * 1024 * 1024,
    "max_workspace_versioned_document_bytes": 2 * 1024 * 1024 * 1024,
    "transaction_path_project_relative_required": True,
    "transaction_path_git_ignored_required": True,
    "transaction_file_mode": "0600",
    "transaction_file_nlink": 1,
    "versioned_document_source_path_project_relative_required": True,
    "versioned_document_source_path_git_ignored_required": True,
    "versioned_document_source_file_mode": "0600",
    "versioned_document_source_file_nlink": 1,
    "versioned_document_nonempty_required": True,
    "bounded_descriptor_inputs": [
        "transaction_request",
        "versioned_document_source",
        "workspace_versioned_document",
    ],
    "named_stat_and_open_fstat_before_read_required": True,
    "bounded_read_loop_maximum_plus_one_hard_stop_required": True,
    "final_path_inode_parent_mode_size_nlink_hash_closure_required": True,
    "semantic_route_and_group_explicit_review_status": "reviewed",
    "human_supplied_fields": [
        "semantic_route_and_mapping_group_decisions",
        "explicit_review_status",
        "rationale_and_revision_reason",
        "reviewer_identity",
        "review_and_attestation_times",
        "evidence_references_and_document_bindings",
        "batch_attestation_confirmations",
        "terminal_event_confirmation",
    ],
    "software_derived_fields": [
        "revision_numbers",
        "supersedes_sha256",
        "revision_event_records",
        "workspace_event_records",
        "canonical_record_and_chain_hashes",
        "batch_and_group_registry_hash_bindings",
        "completion_active_workspace_state_hash",
    ],
    "software_derivation_restricted_to_listed_mechanics": True,
    "full_private_sibling_stage_copy_required": True,
    "document_byte_preflight_required": True,
    "stage_document_bytes_before_import_must_equal_live_preflight": True,
    "stage_document_bytes_after_import_must_conserve_existing_plus_imported": True,
    "full_staged_workspace_validation_required": True,
    "two_pass_workspace_snapshot_hash_required": True,
    "external_nonblocking_flock_required": True,
    "named_lock_inode_mode_nlink_closure_before_and_after_exchange_required": True,
    "darwin_atomic_exchange": "renameatx_np(RENAME_SWAP)",
    "linux_atomic_exchange": "renameat2(RENAME_EXCHANGE)",
    "nonatomic_exchange_fallback_allowed": False,
    "stale_workspace_snapshot_base_fails_closed": True,
    "transaction_replay_after_success_fails_closed": True,
    "exact_duplicate_ledger_revision_resubmission_is_idempotent": True,
    "invalid_live_with_stale_stage_policy": (
        "retain_both_fail_closed_manual_recovery"
    ),
    "crash_after_exchange_before_acknowledgement_is_ambiguous": True,
    "retry_after_ambiguous_crash_requires_current_snapshot_inspection": True,
    "mapping_group_tombstone_supported": False,
    "unreplaceable_mapping_group_policy": (
        "abandon_current_workspace_and_reinitialize_new_workspace"
    ),
    "aggregate_only_output_required": True,
    "private_values_in_output_allowed": False,
    "database_access_allowed": False,
    "network_access_allowed": False,
    "external_api_access_allowed": False,
    "llm_access_allowed": False,
}
EXPECTED_MAPPING_GROUPS = {
    "registry_required_for_every_nonnull_group_id": True,
    "minimum_members": 2,
    "members_are_exact_semantic_review_ids": True,
    "member_set_must_equal_key_assignments": True,
    "group_level_five_dimension_decision_required": True,
    "group_level_nonuncertain_requires_evidence_refs": True,
    "group_level_human_review_provenance_required": True,
    "normalization_or_string_similarity_may_create_group": False,
    "implicit_transitive_merge_allowed": False,
    "conflicting_duplicate_group_definition_allowed": False,
    "eligible_group_members_must_be_linked_by_bound_local_evidence": True,
    "local_evidence_cooccurrence_alone_establishes_group": False,
    "group_decision_authoritative_only_for_multimembership_component_with_exact_common_group": True,
    "member_decision_authoritative_for_single_membership_component": True,
    "group_and_member_decisions_may_differ_with_explicit_evidence": True,
    "local_evidence_eligibility": {
        "allowed_stage_kind": [
            "202b:detail_seed_membership_bridge",
            "202b:emar_medication_detail_bridge",
            "202c:detail_pharmacy_prescription_bridge",
            "202c:head_pharmacy_prescription_bridge",
            "202c:pharmacy_prescription_bridge",
        ],
        "group_member_set_must_be_subset_of_one_tuple_nonnull_semantic_membership_set": True,
        "group_membership_requires_human_identity_evidence_beyond_cooccurrence": True,
        "local_tuple_ordinal_is_one_based_within_stage_kind_data_records": True,
        "unsupported_or_unlinked_group_fails_closed": True,
    },
}
EXPECTED_COMPONENT_ROLE = {
    "level": "physical component during mapped-event application",
    "derived_from_effective_product_identity_status": True,
    "supported_maps_to": "product",
    "refuted_maps_to": "nonproduct",
    "uncertain_maps_to": "uncertain",
    "allowed_values": ["product", "nonproduct", "uncertain"],
    "human_workspace_does_not_assign_event_components": True,
}
EXPECTED_ROUTE_REVIEW = {
    "decision_values": ["iv", "noniv", "unknown"],
    "review_status_values": ["unreviewed", "reviewed"],
    "initial_decision": "unknown",
    "initial_review_status": "unreviewed",
    "reviewed_unknown_allowed": True,
    "allowed_decision_bases": [
        "explicit_iv_route_semantics",
        "explicit_noniv_route_semantics",
        "ambiguous_or_insufficient_route_semantics",
        "other_documented_human_judgment",
    ],
    "sql_null_route_state": "missing",
    "sql_null_requires_human_review": False,
    "sql_null_sets_unknown": False,
    "source_specific_override_allowed": False,
    "normalization_or_string_similarity_may_classify_route": False,
    "software_may_set_reviewed": False,
    "llm_may_set_reviewed": False,
    "reviewed_requires_human_reviewer_id": True,
    "reviewed_requires_strict_utc_time": True,
    "reviewed_requires_nonempty_rationale": True,
    "reviewed_requires_evidence_refs": True,
    "reviewed_unknown_requires_ambiguity_or_insufficiency_rationale": True,
}
EXPECTED_EVIDENCE_REGISTRY = {
    "private_registry_required": True,
    "allowed_namespaces": [
        "local_tuple",
        "source_template",
        "versioned_document",
    ],
    "local_tuple_reference_fields": [
        "local_evidence_raw_sha256",
        "stage",
        "tuple_kind",
        "ordinal_within_kind",
    ],
    "source_template_reference_fields": [
        "source_template_raw_sha256",
        "private_review_id",
    ],
    "versioned_document_reference_fields": [
        "evidence_id",
        "document_sha256",
        "document_version",
        "accessed_at_utc",
        "private_local_path",
    ],
    "external_document_must_be_saved_as_private_local_evidence": True,
    "unversioned_url_or_free_text_reference_allowed": False,
    "evidence_registry_files_in_snapshot_closure": True,
    "network_access_by_workspace_tools_allowed": False,
    "external_api_access_by_workspace_tools_allowed": False,
    "local_tuple": {
        "allowed_stage_kind": [
            "202b:detail_product_context",
            "202b:detail_seed_membership_bridge",
            "202b:emar_medication_detail_bridge",
            "202b:emar_medication_head_partition",
            "202c:detail_pharmacy_prescription_bridge",
            "202c:head_pharmacy_prescription_bridge",
            "202c:pharmacy_no_prescription_component",
            "202c:pharmacy_prescription_bridge",
            "202c:pharmacy_product_context",
            "202c:prescription_identifier_context",
        ],
        "ordinal_is_one_based_within_stage_kind_data_records": True,
        "must_resolve_to_exact_record_in_bound_local_evidence_stream": True,
        "ordinary_decision_relevance_is_human_judgment_not_structural_validation": True,
    },
    "local_tuple_index": EXPECTED_LOCAL_EVIDENCE_INDEX,
}
EXPECTED_WORKSPACE_STATE = {
    "event_log_file": "workspace-events.jsonl",
    "event_log_append_only": True,
    "event_log_canonical_serialization": "canonical-json-utf8-sort-keys-no-whitespace-v1",
    "allowed_events": [
        "initialized",
        "batch_submitted",
        "batch_revised",
        "group_registry_revised",
        "attestation_added",
        "validation_failed",
        "human_review_complete_unfrozen",
        "abandoned",
    ],
    "state_is_derived_from_validated_event_log_and_current_active_revision_set": True,
    "configuration_execution_status_is_not_rewritten": True,
    "failed_validation_never_advances_state": True,
    "resume_requires_revalidation_of_all_active_inputs": True,
    "abandoned_workspace_cannot_be_reactivated": True,
    "revision_event_log": {
        "file": "revisions/revision-events.jsonl",
        "header_record_type": "revision_event_ledger_begin",
        "header_exact_fields": [
            "record_type", "schema_version", "component_id", "config_sha256",
            "initial_event_count",
        ],
        "header_schema_version": 1,
        "header_initial_event_count": 0,
        "record_type": "revision_event",
        "record_exact_fields": [
            "record_type", "event_index", "previous_event_sha256",
            "revision_kind", "subject_id", "batch_index", "revision",
            "revision_sha256", "supersedes_sha256", "reviewer_id",
            "recorded_at_utc",
        ],
        "allowed_revision_kinds": [
            "semantic_decision", "route_decision", "mapping_group",
        ],
        "event_index_starts_at": 1,
        "event_index_contiguous": True,
        "first_previous_event_sha256_is_null": True,
        "later_previous_event_sha256_is_prior_canonical_record_sha256": True,
        "canonical_record_hash": (
            "sha256-canonical-json-utf8-sort-keys-no-whitespace-v1"
        ),
        "nondecreasing_strict_utc_time_required": True,
        "one_event_per_unique_noninitial_item_revision": True,
        "one_event_per_unique_mapping_group_revision": True,
        "exact_duplicate_ledger_resubmission_adds_no_event": True,
        "item_revision_after_first_must_be_reviewed": True,
        "record_must_bind_ledger_revision_sha_supersedes_reviewer_and_time": True,
        "semantic_and_route_batch_index_required": True,
        "mapping_group_batch_index_is_null": True,
    },
    "workspace_event_log": {
        "file": "workspace-events.jsonl",
        "header_record_type": "workspace_event_ledger_begin",
        "header_exact_fields": [
            "record_type", "schema_version", "component_id", "config_sha256",
            "initial_event_count",
        ],
        "header_schema_version": 1,
        "header_initial_event_count": 0,
        "record_type": "workspace_event",
        "record_exact_fields": [
            "record_type", "event_index", "previous_event_sha256",
            "event_type", "event_at_utc", "actor_id", "subject_kind",
            "subject_id", "subject_sha256",
        ],
        "event_index_starts_at": 1,
        "event_index_contiguous": True,
        "first_previous_event_sha256_is_null": True,
        "later_previous_event_sha256_is_prior_canonical_record_sha256": True,
        "canonical_record_hash": (
            "sha256-canonical-json-utf8-sort-keys-no-whitespace-v1"
        ),
        "nondecreasing_strict_utc_time_required": True,
        "formal_first_event": "initialized",
        "preview_initialized_event_allowed": False,
        "one_event_per_revision_event": True,
        "one_event_per_unique_attestation": True,
        "validation_failed_never_advances_state": True,
        "human_review_complete_requires_current_review_and_attestation_closure": True,
        "abandoned_is_terminal": True,
    },
    "active_state_hash": {
        "version": "query202-human-adjudication-active-workspace-state-v1",
        "encoding": (
            "sha256(version-utf8 || canonical-json-utf8-sort-keys-no-whitespace-v1)"
        ),
        "object_exact_keys": [
            "batches", "mapping_groups", "current_attestations",
        ],
        "batches_sorted_by": ["review_kind", "batch_index"],
        "batch_exact_fields": [
            "review_kind", "batch_index", "item_count",
            "active_decisions_sha256", "decision_ledger_sha256",
        ],
        "mapping_groups_sorted_by": ["mapping_group_id"],
        "mapping_group_exact_fields": [
            "mapping_group_id", "active_revision_sha256",
        ],
        "attestations_sorted_by": ["review_kind", "batch_index"],
        "attestation_exact_fields": [
            "review_kind", "batch_index", "attestation_sha256",
        ],
    },
}
EXPECTED_STRUCTURAL_PREVIEW = {
    "enabled_for_internal_api": True,
    "cli_entry_allowed": False,
    "requires_explicit_allow_proposed": True,
    "artifact_parent": "artifacts/query202-human-adjudication-workspace/_structural-previews",
    "formal_workspace": False,
    "workspace_initialized": False,
    "resume_or_upgrade_to_formal_allowed": False,
    "compile_audit_or_freeze_allowed": False,
    "config_or_bundle_change_invalidates_preview": True,
    "private_directory_mode": "0700",
    "private_file_mode": "0600",
    "git_ignored_required": True,
    "raw_values_on_stdout_allowed": False,
}
EXPECTED_FINAL_OUTPUTS = {
    "component_id": COMPONENT_ID,
    "artifact_parent": "artifacts/query202-human-adjudication",
    "artifact_directory_naming": "strict-utc-basic-with-fraction-v1",
    "private_directory_mode": "0700",
    "private_file_mode": "0600",
    "strict_inventory": [
        "reviewed-semantic-ledger.jsonl.gz",
        "semantic-mapping-groups.jsonl.gz",
        "source-specific-route-mapping.jsonl.gz",
        "human-attestations.jsonl.gz",
        "evidence-registry.jsonl.gz",
        "manifest.json",
        "aggregate-summary.json",
    ],
    "strict_inventory_after_audit": [
        "reviewed-semantic-ledger.jsonl.gz",
        "semantic-mapping-groups.jsonl.gz",
        "source-specific-route-mapping.jsonl.gz",
        "human-attestations.jsonl.gz",
        "evidence-registry.jsonl.gz",
        "manifest.json",
        "aggregate-summary.json",
        "audit-summary.json",
    ],
    "strict_inventory_after_freeze": [
        "reviewed-semantic-ledger.jsonl.gz",
        "semantic-mapping-groups.jsonl.gz",
        "source-specific-route-mapping.jsonl.gz",
        "human-attestations.jsonl.gz",
        "evidence-registry.jsonl.gz",
        "manifest.json",
        "aggregate-summary.json",
        "audit-summary.json",
        "freeze-manifest.json",
    ],
    "independent_audit_adds_only": "audit-summary.json",
    "separate_freeze_adds_only": "freeze-manifest.json",
    "gzip_encoding": "gzip+utf8+ndjson-single-member-mtime0-v1",
    "semantic_ledger_schema": "query202-reviewed-semantic-ledger-v1",
    "semantic_decision_hash_version": "query202-semantic-decisions-v1",
    "semantic_ledger_includes_exact_source_field_and_raw_value": True,
    "semantic_key_set_hash_version": "source-field-nonnull-exact-value-set-v1",
    "semantic_key_set_must_equal_source": True,
    "semantic_active_revision_projection_required": True,
    "mapping_group_schema": "query202-semantic-mapping-groups-v1",
    "mapping_group_hash_version": "query202-semantic-mapping-groups-v1",
    "route_mapping_schema": "query202-source-specific-exact-route-mapping-v1",
    "route_mapping_hash_version": "query202-source-specific-exact-route-mapping-v1",
    "route_mapping_expands_canonical_to_233_nonnull_memberships": True,
    "route_mapping_adds_3_sql_null_missing_memberships": True,
    "route_mapping_total_typed_memberships": 236,
    "route_mapping_preserves_source_key_field_role_frequency_and_provenance": True,
    "attestation_schema": "query202-human-attestations-v1",
    "attestation_hash_version": "query202-human-attestations-v1",
    "evidence_registry_schema": "query202-evidence-registry-v1",
    "evidence_registry_hash_version": "query202-evidence-registry-v1",
    "manifest_schema": "query202-human-adjudication-final-manifest-v1",
    "aggregate_summary_schema": "query202-human-adjudication-aggregate-summary-v1",
    "audit_schema": "query202-human-adjudication-final-artifact-audit-v1",
    "audit_method": "independent-reimplementation-without-generator-imports-v1",
    "auditor_component_id": "D005-K-QUERY202-HUMAN-ADJUDICATION-FINAL-AUDITOR-v1",
    "freeze_schema": "query202-human-adjudication-freeze-manifest-v1",
    "workspace_snapshot_hash_version": "query202-human-workspace-file-snapshot-v1",
    "registered_document_set_hash_version": "query202-human-versioned-document-set-v1",
    "retained_versioned_documents_location": "formal_workspace",
    "final_artifact_self_contained": False,
    "independent_audit_must_reopen_retained_documents": True,
    "freeze_must_reopen_retained_documents": True,
    "manifest_status_before_freeze": "human_review_complete_unfrozen",
    "audit_status_required_before_freeze": "passed",
    "audit_checks_total": 18,
    "freeze_manifest_status": "frozen",
    "freeze_manifest_binds_all_private_whole_file_hashes": True,
    "freeze_manifest_binds_semantic_and_route_decision_hashes": True,
    "freeze_manifest_binds_source_ndc_config_generator_auditor_and_audit_hashes": True,
    "final_artifact_review_complete_guards_true": [
        "semantic_review_complete",
        "route_review_complete",
    ],
    "final_freeze_guards_true": [
        "reviewed_semantic_ledger_frozen",
        "route_mapping_frozen",
    ],
    "downstream_scientific_guards_remain_false": [
        "product_mapping_accepted",
        "event_mapping_created",
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
    ],
}
EXPECTED_DOWNSTREAM_BINDING = {
    "mapped_event_application_config": "config/preregistrations/d005_potassium_query202_mapped_event_application.toml",
    "current_mapped_event_application_is_stale_and_must_not_execute": True,
    "required_future_predecessor_component_id": "D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2",
    "required_future_human_component_id": COMPONENT_ID,
    "old_route_component_id_must_be_replaced": "D005-K-ROUTE-ADJUDICATION-v2",
    "required_route_mapping_hash_version": "query202-source-specific-exact-route-mapping-v1",
    "mapped_event_application_must_be_revised_and_refrozen_after_human_artifact_freeze": True,
}
EXPECTED_SNAPSHOT_CLOSURE = {
    "two_pass_required_for_validation_and_compile": True,
    "compare_device_inode_mode_size_sha256": True,
    "source_public_files_included": True,
    "source_semantic_route_and_local_evidence_files_included": True,
    "workspace_local_evidence_index_included": True,
    "ndc_decision_config_included": True,
    "all_batch_and_group_files_included": True,
    "config_and_implementation_bundles_included": True,
    "test_attestation_and_test_files_included": True,
    "in_place_mutation_fails_closed": True,
    "symlink_input_allowed": False,
}
EXPECTED_TEST_ATTESTATION_STATIC = {
    "schema_version": 2,
    "project_local_path_when_passed": TEST_ATTESTATION_PATH,
    "project_local_public_evidence_required": True,
    "canonical_encoding": (
        "canonical-json-utf8-sort-keys-no-whitespace-newline-v1"
    ),
    "test_command": TEST_COMMAND,
    "test_command_argv": list(TEST_COMMAND_ARGV),
    "test_command_environment": [
        f"{key}={value}" for key, value in TEST_COMMAND_ENV
    ],
    "required_test_paths": list(REQUIRED_TEST_PATHS),
    "test_execution_paths": list(TEST_EXECUTION_PATHS),
    "execution_snapshot_encoding": TEST_EXECUTION_SNAPSHOT_ENCODING,
    "ordered_test_ids_encoding": ORDERED_TEST_IDS_ENCODING,
    "ordered_test_ids_sha256": EXPECTED_ORDERED_TEST_IDS_SHA256,
    "mutation_test_ids_encoding": MUTATION_TEST_IDS_ENCODING,
    "mutation_test_ids": EXPECTED_MUTATION_TEST_IDS,
    "mutation_test_ids_sha256": EXPECTED_MUTATION_TEST_IDS_SHA256,
    "failures_required": 0,
    "errors_required": 0,
    "required_mutation_classes": list(REQUIRED_MUTATION_CLASSES),
    "attestation_contains_private_values": False,
    "attestation_contains_test_output": False,
    "private_safe_exact_schema_required": True,
    "builder_must_run_exact_test_command": True,
    "builder_must_execute_private_staged_snapshot": True,
    "every_test_id_must_report_ok": True,
    "python_runtime_path": TEST_COMMAND_ARGV[0],
    "python_runtime_binding": (
        "resolved-regular-file-sha256+bytes+implementation+version-v1"
    ),
    "project_local_execution_closure_non_hermetic": True,
    "status_change_alone_may_enable_execution": False,
}
EXPECTED_EXECUTION_GATE = {
    "unresolved_blockers": [
        "generator validator and independent auditor implementation",
        "synthetic missing duplicate conflict stale-base privacy and TOCTOU tests",
        "local-evidence index and exact evidence-reference validation including forged-reference tests",
        "implementation bundle hashes",
        "frozen evidence registry and revision serialization contracts",
        "final output compiler audit and separate freeze implementation",
        "machine-bound synthetic test attestation",
        "explicit freeze of this machine contract before workspace initialization",
    ],
    "status_change_alone_may_enable_execution": False,
}
EXPECTED_GUARDS = {
    "workspace_initialized": False,
    "semantic_review_complete": False,
    "reviewed_semantic_ledger_frozen": False,
    "route_review_complete": False,
    "route_mapping_frozen": False,
    "product_identity_decided": False,
    "product_mapping_accepted": False,
    "event_mapping_created": False,
    "final_source_policy": False,
    "complete_intervention_coverage": False,
    "formal_action": False,
    "formal_episode": False,
    "zero_action_constructed": False,
    "formal_non_icu_rule": False,
    "formal_label": False,
    "formal_cohort": False,
    "patient_data_exported": False,
    "database_connected": False,
    "external_api_called": False,
    "llm_called": False,
}
EXPECTED_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "component_id",
        "decision_id",
        "status",
        "scope",
        "rule_version",
        "specified_on",
        "execution_status",
        "execution_permitted",
        "implementation_state",
        "author_setting_recovered",
        "lifecycle",
        "source_artifact",
        "ndc_decision",
        "workspace",
        "semantic_review",
        "human_review_policy",
        "revisions",
        "review_writer",
        "mapping_groups",
        "route_review",
        "component_role",
        "evidence_registry",
        "workspace_state",
        "structural_preview",
        "final_outputs",
        "downstream_binding",
        "snapshot_closure",
        "implementation",
        "test_attestation",
        "execution_gate",
        "guards",
    }
)


class HumanAdjudicationPreregistrationError(RuntimeError):
    """Raised when the proposal cannot be read without ambiguity."""


def _strict_equal(actual: object, expected: object) -> bool:
    if isinstance(expected, Mapping):
        return (
            isinstance(actual, Mapping)
            and set(actual) == set(expected)
            and all(_strict_equal(actual[key], value) for key, value in expected.items())
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_strict_equal(left, right) for left, right in zip(actual, expected))
        )
    return type(actual) is type(expected) and actual == expected


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _validate_exact_mapping(
    actual: object,
    expected: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(actual, Mapping):
        errors.append(f"{label} must be a table")
        return
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    if missing or unexpected:
        errors.append(
            f"{label} keys changed: missing={missing!r}, unexpected={unexpected!r}"
        )
    for key, expected_value in expected.items():
        if key in actual and not _strict_equal(actual[key], expected_value):
            errors.append(f"{label}.{key} contract changed")


def _safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _relative_parts(relative: object) -> tuple[str, ...]:
    if not _safe_relative(relative):
        raise OSError("unsafe project-relative path")
    parts = Path(str(relative)).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise OSError("unsafe project-relative path")
    return tuple(parts)


def _directory_open_flags() -> int:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise OSError("safe descriptor-relative traversal is unavailable")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _open_directory_chain(root: Path, parts: Sequence[str]) -> list[int]:
    """Open each directory from a trusted root without following symlinks."""
    if root.is_symlink():
        raise OSError("project root must not be a symlink")
    resolved_root = root.resolve(strict=True)
    root_entry = resolved_root.lstat()
    if not stat.S_ISDIR(root_entry.st_mode):
        raise OSError("project root is not a directory")
    descriptors: list[int] = []
    try:
        root_descriptor = os.open(resolved_root, _directory_open_flags())
        descriptors.append(root_descriptor)
        root_open = os.fstat(root_descriptor)
        if (
            not stat.S_ISDIR(root_open.st_mode)
            or (root_entry.st_dev, root_entry.st_ino)
            != (root_open.st_dev, root_open.st_ino)
        ):
            raise OSError("project root identity changed while opening")
        for part in parts:
            parent = descriptors[-1]
            before = os.stat(part, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                raise OSError("path component is not a directory")
            descriptor = os.open(
                part,
                _directory_open_flags(),
                dir_fd=parent,
            )
            descriptors.append(descriptor)
            opened = os.fstat(descriptor)
            after = os.stat(part, dir_fd=parent, follow_symlinks=False)
            if not (
                stat.S_ISDIR(opened.st_mode)
                and _same_snapshot(before, opened)
                and _same_snapshot(opened, after)
            ):
                raise OSError("directory identity changed while traversing")
        return descriptors
    except BaseException:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def _same_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_mode,
        left.st_nlink,
        left.st_size,
        left.st_mtime_ns,
        left.st_ctime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_mode,
        right.st_nlink,
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )


def _snapshot_regular_file(
    root: Path,
    relative: object,
    *,
    retain_payload: bool,
    maximum_bytes: int | None = None,
) -> dict[str, Any]:
    parts = _relative_parts(relative)
    directory_descriptors = _open_directory_chain(root, parts[:-1])
    parent = directory_descriptors[-1]
    descriptor: int | None = None
    payload_parts: list[bytes] | None = [] if retain_payload else None
    digest = hashlib.sha256()
    total = 0
    try:
        initial = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(initial.st_mode):
            raise OSError("expected a regular file")
        if maximum_bytes is not None and initial.st_size > maximum_bytes:
            raise OSError("regular file exceeds its size bound")
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=parent,
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not _same_snapshot(initial, before):
            raise OSError("file identity changed before hashing")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            if maximum_bytes is not None and total > maximum_bytes:
                raise OSError("regular file grew beyond its size bound")
            if payload_parts is not None:
                payload_parts.append(chunk)
        after = os.fstat(descriptor)
        final = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if not (
            _same_snapshot(before, after)
            and _same_snapshot(after, final)
            and total == after.st_size
        ):
            raise OSError("file identity changed while hashing")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        for directory_descriptor in reversed(directory_descriptors):
            os.close(directory_descriptor)
    return {
        "sha256": digest.hexdigest(),
        "bytes": total,
        "mode": stat.S_IMODE(after.st_mode),
        "nlink": after.st_nlink,
        "identity": (after.st_dev, after.st_ino),
        "mtime_ns": after.st_mtime_ns,
        "ctime_ns": after.st_ctime_ns,
        "payload": b"".join(payload_parts) if payload_parts is not None else None,
    }


def _snapshot_seal(snapshot: Mapping[str, Any]) -> tuple[object, ...]:
    base = tuple(
        snapshot.get(key)
        for key in (
            "identity",
            "mode",
            "nlink",
            "sha256",
            "bytes",
            "mtime_ns",
            "ctime_ns",
        )
    )
    locator = snapshot.get("runtime_locator")
    return base + (
        _runtime_locator_seal(locator) if isinstance(locator, Mapping) else None,
    )


def _directory_seal(root: Path, relative: object) -> dict[str, Any]:
    parts = _relative_parts(relative)
    descriptors = _open_directory_chain(root, parts)
    try:
        value = os.fstat(descriptors[-1])
        if not stat.S_ISDIR(value.st_mode):
            raise OSError("expected a directory")
        return {
            "identity": (value.st_dev, value.st_ino),
            "mode": stat.S_IMODE(value.st_mode),
        }
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _strict_json(payload: bytes) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    return json.loads(payload.decode("utf-8"), object_pairs_hook=object_pairs)


def _read_config_snapshot(root: Path) -> tuple[dict[str, Any], str, dict[str, Any]]:
    snapshot = _snapshot_regular_file(root, str(CONFIG_PATH), retain_payload=True)
    payload = snapshot["payload"]
    if not isinstance(payload, bytes):
        raise HumanAdjudicationPreregistrationError("configuration snapshot unavailable")
    try:
        config = tomllib.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise HumanAdjudicationPreregistrationError(
            "configuration is not valid UTF-8 TOML"
        ) from exc
    return config, str(snapshot["sha256"]), snapshot


def read_query202_human_adjudication_preregistration(root: Path) -> dict[str, Any]:
    config, _sha256, _snapshot = _read_config_snapshot(root)
    return config


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_test_attestation_contract(
    value: object,
    *,
    candidate_contract: bool,
    errors: list[str],
) -> None:
    if not isinstance(value, Mapping):
        errors.append("test_attestation must be a table")
        return
    expected_keys = set(EXPECTED_TEST_ATTESTATION_STATIC) | {
        "status",
        "attestation_path",
        "attestation_sha256",
        "required_test_count",
    }
    missing = sorted(expected_keys - set(value))
    unexpected = sorted(set(value) - expected_keys)
    if missing or unexpected:
        errors.append(
            "test_attestation keys changed: "
            f"missing={missing!r}, unexpected={unexpected!r}"
        )
    for key, expected in EXPECTED_TEST_ATTESTATION_STATIC.items():
        if key in value and not _strict_equal(value[key], expected):
            errors.append(f"test_attestation.{key} contract changed")
    if value.get("required_test_count") != EXPECTED_TEST_COUNT:
        errors.append(
            "test_attestation.required_test_count differs from its exact lock"
        )
    if candidate_contract:
        if value.get("status") != "passed":
            errors.append(
                "test_attestation.status must be passed for an implemented contract"
            )
        if value.get("attestation_path") != TEST_ATTESTATION_PATH:
            errors.append(
                "test_attestation.attestation_path must equal its project-local path"
            )
        if not _is_sha256(value.get("attestation_sha256")):
            errors.append(
                "test_attestation.attestation_sha256 must be a pinned SHA-256"
            )
    else:
        pending = {
            "status": "pending",
            "attestation_path": PLACEHOLDER,
            "attestation_sha256": PLACEHOLDER,
        }
        for key, expected in pending.items():
            if key in value and not _strict_equal(value[key], expected):
                errors.append(
                    f"test_attestation.{key} must remain {expected!r} in proposal state"
                )


def validate_query202_human_adjudication_preregistration(
    config: Mapping[str, Any],
) -> list[str]:
    """Validate the exact v1 proposal, freeze candidate, or frozen contract."""
    errors: list[str] = []
    missing = sorted(EXPECTED_ROOT_KEYS - set(config))
    unexpected = sorted(set(config) - EXPECTED_ROOT_KEYS)
    if missing or unexpected:
        errors.append(f"root keys changed: missing={missing!r}, unexpected={unexpected!r}")

    root_values = {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "decision_id": "D005",
        "scope": "Private human adjudication of the frozen Query 202 potassium semantic and route universes",
        "specified_on": "2026-10-13",
        "execution_status": "not_initialized",
        "author_setting_recovered": False,
    }
    for key, expected in root_values.items():
        if key not in config or not _strict_equal(config[key], expected):
            errors.append(f"root.{key} must be {expected!r}")

    status = config.get("status")
    if status not in {"proposed", "frozen_for_execution"}:
        errors.append("root.status must be proposed or frozen_for_execution")
    frozen = status == "frozen_for_execution"
    expected_rule_version = (
        "k-query202-human-adjudication-v1-frozen"
        if frozen
        else "k-query202-human-adjudication-v1-proposed"
    )
    if config.get("rule_version") != expected_rule_version:
        errors.append(f"root.rule_version must be {expected_rule_version!r}")
    if config.get("execution_permitted") is not frozen:
        errors.append("root.execution_permitted must exactly follow frozen status")

    implementation_state = config.get("implementation_state")
    if implementation_state not in {
        "architecture_specified",
        "implemented_and_tested",
    }:
        errors.append(
            "root.implementation_state must be architecture_specified or "
            "implemented_and_tested"
        )
    candidate_contract = implementation_state == "implemented_and_tested"
    if frozen and not candidate_contract:
        errors.append(
            "frozen status requires implementation_state implemented_and_tested"
        )

    exact_tables = {
        "lifecycle": EXPECTED_LIFECYCLE,
        "source_artifact": EXPECTED_SOURCE_ARTIFACT,
        "ndc_decision": EXPECTED_NDC_DECISION,
        "workspace": EXPECTED_WORKSPACE,
        "semantic_review": EXPECTED_SEMANTIC_REVIEW,
        "human_review_policy": EXPECTED_HUMAN_REVIEW_POLICY,
        "revisions": EXPECTED_REVISIONS,
        "review_writer": EXPECTED_REVIEW_WRITER,
        "mapping_groups": EXPECTED_MAPPING_GROUPS,
        "component_role": EXPECTED_COMPONENT_ROLE,
        "route_review": EXPECTED_ROUTE_REVIEW,
        "evidence_registry": EXPECTED_EVIDENCE_REGISTRY,
        "workspace_state": EXPECTED_WORKSPACE_STATE,
        "structural_preview": EXPECTED_STRUCTURAL_PREVIEW,
        "final_outputs": EXPECTED_FINAL_OUTPUTS,
        "downstream_binding": EXPECTED_DOWNSTREAM_BINDING,
        "snapshot_closure": EXPECTED_SNAPSHOT_CLOSURE,
        "guards": EXPECTED_GUARDS,
    }
    for label, expected in exact_tables.items():
        _validate_exact_mapping(config.get(label), expected, label, errors)

    expected_gate = {
        "unresolved_blockers": []
        if candidate_contract
        else EXPECTED_EXECUTION_GATE["unresolved_blockers"],
        "status_change_alone_may_enable_execution": False,
    }
    _validate_exact_mapping(
        config.get("execution_gate"), expected_gate, "execution_gate", errors
    )
    _validate_test_attestation_contract(
        config.get("test_attestation"),
        candidate_contract=candidate_contract,
        errors=errors,
    )

    implementation = config.get("implementation")
    expected_implementation_keys = {
        "bundle_encoding",
        "generator_paths",
        "generator_bundle_sha256",
        "auditor_paths",
        "auditor_bundle_sha256",
    }
    if not isinstance(implementation, Mapping):
        errors.append("implementation must be a table")
    else:
        missing = sorted(expected_implementation_keys - set(implementation))
        unexpected = sorted(set(implementation) - expected_implementation_keys)
        if missing or unexpected:
            errors.append(
                "implementation keys changed: "
                f"missing={missing!r}, unexpected={unexpected!r}"
            )
        for key, expected in (
            ("bundle_encoding", BUNDLE_ENCODING),
            ("generator_paths", list(EXPECTED_GENERATOR_PATHS)),
            ("auditor_paths", list(EXPECTED_AUDITOR_PATHS)),
        ):
            if key in implementation and not _strict_equal(
                implementation[key], expected
            ):
                errors.append(f"implementation.{key} contract changed")
        for name in EXPECTED_IMPLEMENTATION_PATHS:
            digest = implementation.get(f"{name}_bundle_sha256")
            digest_is_sha256 = _is_sha256(digest)
            if candidate_contract:
                if not digest_is_sha256:
                    errors.append(
                        f"implementation.{name}_bundle_sha256 must be frozen"
                    )
            elif digest != PLACEHOLDER:
                errors.append(
                    f"implementation.{name}_bundle_sha256 must be the proposal placeholder"
                )

    safe_paths = (
        EXPECTED_SOURCE_ARTIFACT["directory"],
        EXPECTED_SOURCE_ARTIFACT["source_config_path"],
        EXPECTED_NDC_DECISION["config_path"],
        *EXPECTED_GENERATOR_PATHS,
        *EXPECTED_AUDITOR_PATHS,
        *REQUIRED_TEST_PATHS,
        *TEST_EXECUTION_PATHS,
        TEST_ATTESTATION_PATH,
    )
    if not all(_safe_relative(value) for value in safe_paths):
        errors.append("registered paths must be safe and project-relative")
    return errors


def _implementation_bundle_snapshot(
    root: Path,
    paths: Sequence[str],
) -> tuple[str, dict[str, tuple[str, dict[str, Any]]]]:
    digest = hashlib.sha256()
    snapshots: dict[str, tuple[str, dict[str, Any]]] = {}
    for relative in paths:
        snapshot = _snapshot_regular_file(root, relative, retain_payload=True)
        payload = snapshot["payload"]
        if not isinstance(payload, bytes):
            raise OSError("implementation snapshot unavailable")
        encoded_path = relative.encode("utf-8")
        digest.update(struct.pack(">I", len(encoded_path)))
        digest.update(encoded_path)
        digest.update(struct.pack(">Q", len(payload)))
        digest.update(payload)
        snapshots[relative] = (relative, snapshot)
    return digest.hexdigest(), snapshots


def implementation_bundle_sha256(root: Path, paths: Sequence[str]) -> str:
    digest, _snapshots = _implementation_bundle_snapshot(root, paths)
    return digest


def _contract_projection(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable contract covered by the synthetic-test attestation.

    Lifecycle switches, generated hashes, and the attestation's own locator are
    excluded so that a passed attestation can be pinned without changing the
    contract it signs.  Scientific rules, path inventories, exact test count,
    test command/path locks, and mutation-class requirements stay in the
    projection.
    """
    projection = json.loads(json.dumps(config, ensure_ascii=False))
    for key in (
        "status",
        "rule_version",
        "execution_status",
        "execution_permitted",
        "implementation_state",
    ):
        projection.pop(key, None)
    implementation = _as_mapping(projection.get("implementation"))
    if isinstance(implementation, dict):
        implementation.pop("generator_bundle_sha256", None)
        implementation.pop("auditor_bundle_sha256", None)
    execution_gate = _as_mapping(projection.get("execution_gate"))
    if isinstance(execution_gate, dict):
        execution_gate.pop("unresolved_blockers", None)
    attestation = _as_mapping(projection.get("test_attestation"))
    if isinstance(attestation, dict):
        for key in (
            "status",
            "attestation_path",
            "attestation_sha256",
        ):
            attestation.pop(key, None)
    return projection


def scientific_contract_sha256(config: Mapping[str, Any]) -> str:
    payload = json.dumps(
        _contract_projection(config),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _verify_test_attestation(
    root: Path,
    config: Mapping[str, Any],
    actual_bundle_hashes: Mapping[str, object],
) -> tuple[
    bool,
    list[str],
    dict[str, Any],
    dict[str, tuple[str, dict[str, Any]]],
]:
    """Verify the project-local attestation without exposing per-test details."""
    gate = _as_mapping(config.get("test_attestation"))
    summary: dict[str, Any] = {
        "configured_status": gate.get("status"),
        "verified": False,
        "configured_sha256": gate.get("attestation_sha256"),
        "actual_sha256": None,
        "scientific_contract_sha256": scientific_contract_sha256(config),
        "tests_run": None,
        "test_file_count": 0,
        "mutation_class_count": 0,
        "execution_snapshot_file_count": 0,
        "python_runtime_bound": False,
        "project_local_execution_closure_non_hermetic": True,
        "problem_count": 0,
    }
    if gate.get("status") != "passed":
        return False, [], summary, {}
    if gate.get("attestation_path") != TEST_ATTESTATION_PATH:
        problems = ["test attestation path mismatch"]
        summary["problem_count"] = len(problems)
        return False, problems, summary, {}

    closure: dict[str, tuple[str, dict[str, Any]]] = {}
    problems: list[str] = []
    try:
        attestation_snapshot = _snapshot_regular_file(
            root,
            TEST_ATTESTATION_PATH,
            retain_payload=True,
            maximum_bytes=64 * 1024,
        )
        closure["test_attestation:file"] = (
            TEST_ATTESTATION_PATH,
            attestation_snapshot,
        )
        summary["actual_sha256"] = attestation_snapshot["sha256"]
        if attestation_snapshot["sha256"] != gate.get("attestation_sha256"):
            problems.append("test attestation whole-file hash mismatch")
        if (
            attestation_snapshot["mode"] != 0o644
            or attestation_snapshot["nlink"] != 1
        ):
            problems.append("test attestation mode or link count is unsafe")
        if attestation_snapshot["bytes"] > 64 * 1024:
            problems.append("test attestation exceeds its public size bound")
        payload = attestation_snapshot["payload"]
        if not isinstance(payload, bytes):
            raise ValueError("test attestation payload unavailable")
        value = _strict_json(payload)
        if not isinstance(value, Mapping):
            raise ValueError("test attestation is not an object")
        if _canonical_json_bytes(value) != payload:
            problems.append("test attestation canonical encoding mismatch")

        files = value.get("test_files")
        exact_file_schema = (
            isinstance(files, list)
            and len(files) == len(REQUIRED_TEST_PATHS)
            and all(
                isinstance(item, Mapping)
                and set(item) == TEST_ATTESTATION_FILE_KEYS
                for item in files
            )
        )
        expected_files: list[dict[str, str]] = []
        for index, relative in enumerate(REQUIRED_TEST_PATHS):
            snapshot = _snapshot_regular_file(root, relative, retain_payload=False)
            closure[f"test_attestation:test:{index:03d}"] = (relative, snapshot)
            if int(snapshot["mode"]) & 0o022 or int(snapshot["nlink"]) != 1:
                problems.append(
                    f"attested test file {index + 1} mode or link count is unsafe"
                )
            expected_files.append(
                {"path": relative, "file_sha256": str(snapshot["sha256"])}
            )
        bundles = value.get("implementation_bundles")
        exact_bundle_schema = (
            isinstance(bundles, list)
            and len(bundles) == len(EXPECTED_IMPLEMENTATION_PATHS)
            and all(
                isinstance(item, Mapping)
                and set(item) == TEST_ATTESTATION_BUNDLE_KEYS
                for item in bundles
            )
        )
        expected_bundles = [
            {
                "name": name,
                "bundle_sha256": actual_bundle_hashes.get(name),
            }
            for name in EXPECTED_IMPLEMENTATION_PATHS
        ]
        execution_snapshots: dict[str, dict[str, Any]] = {}
        for index, relative in enumerate(TEST_EXECUTION_PATHS):
            snapshot = _snapshot_regular_file(root, relative, retain_payload=False)
            execution_snapshots[relative] = snapshot
            closure[f"test_attestation:execution:{index:03d}"] = (
                relative,
                snapshot,
            )
            if int(snapshot["mode"]) & 0o022 or int(snapshot["nlink"]) != 1:
                problems.append(
                    f"test execution dependency {index + 1} mode or link count is unsafe"
                )
        execution_snapshot = value.get("execution_snapshot")
        python_runtime = value.get("python_runtime")
        checks = {
            "exact schema": set(value) == TEST_ATTESTATION_KEYS,
            "schema version": type(value.get("schema_version")) is int
            and value.get("schema_version") == 2,
            "component": value.get("component_id") == COMPONENT_ID,
            "status": value.get("status") == "passed",
            "test command": value.get("test_command") == TEST_COMMAND,
            "test command argv": value.get("test_command_argv")
            == list(TEST_COMMAND_ARGV),
            "test command environment": value.get("test_command_environment")
            == [f"{key}={item}" for key, item in TEST_COMMAND_ENV],
            "test file schema": exact_file_schema,
            "test files": exact_file_schema and files == expected_files,
            "bundle schema": exact_bundle_schema,
            "ordered bundles": exact_bundle_schema
            and bundles == expected_bundles
            and all(_is_sha256(item["bundle_sha256"]) for item in expected_bundles),
            "scientific contract": value.get("scientific_contract_sha256")
            == scientific_contract_sha256(config),
            "test count": type(value.get("tests_run")) is int
            and value.get("tests_run") == gate.get("required_test_count")
            and value.get("tests_run", 0) > 0,
            "failures": type(value.get("failures")) is int
            and value.get("failures") == 0,
            "errors": type(value.get("errors")) is int
            and value.get("errors") == 0,
            "mutation classes": value.get("mutation_classes_passed")
            == list(REQUIRED_MUTATION_CLASSES),
            "ordered test IDs": value.get("ordered_test_ids_sha256")
            == EXPECTED_ORDERED_TEST_IDS_SHA256,
            "mutation test IDs": value.get("mutation_test_ids_sha256")
            == EXPECTED_MUTATION_TEST_IDS_SHA256,
            "execution snapshot schema": isinstance(execution_snapshot, Mapping)
            and set(execution_snapshot) == TEST_ATTESTATION_EXECUTION_SNAPSHOT_KEYS,
            "execution snapshot": execution_snapshot
            == _execution_snapshot_summary(config, execution_snapshots),
            "python runtime schema": isinstance(python_runtime, Mapping)
            and set(python_runtime) == TEST_ATTESTATION_PYTHON_RUNTIME_KEYS,
            "python runtime": python_runtime == _python_runtime_summary(root),
        }
        problems.extend(
            f"test attestation {label} mismatch"
            for label, passed in checks.items()
            if not passed
        )
        summary.update(
            tests_run=value.get("tests_run")
            if type(value.get("tests_run")) is int
            else None,
            test_file_count=len(files) if isinstance(files, list) else 0,
            mutation_class_count=len(value.get("mutation_classes_passed", []))
            if isinstance(value.get("mutation_classes_passed"), list)
            else 0,
            execution_snapshot_file_count=execution_snapshot.get("file_count", 0)
            if isinstance(execution_snapshot, Mapping)
            and type(execution_snapshot.get("file_count")) is int
            else 0,
            python_runtime_bound=isinstance(python_runtime, Mapping)
            and python_runtime == _python_runtime_summary(root),
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        problems.append("test attestation is absent or malformed")
    summary["problem_count"] = len(problems)
    summary["verified"] = not problems
    return not problems, problems, summary, closure


def _ordered_test_ids_sha256(test_ids: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for test_id in test_ids:
        encoded = test_id.encode("utf-8")
        digest.update(struct.pack(">I", len(encoded)))
        digest.update(encoded)
    return digest.hexdigest()


def _execution_snapshot_summary(
    config: Mapping[str, Any],
    snapshots: Mapping[str, Mapping[str, Any]],
) -> dict[str, object]:
    digest = hashlib.sha256()
    normalized_config = json.dumps(
        _contract_projection(config),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    for relative in TEST_EXECUTION_PATHS:
        encoded_path = relative.encode("utf-8")
        snapshot = snapshots[relative]
        if relative == str(CONFIG_PATH):
            content_sha256 = hashlib.sha256(normalized_config).digest()
            content_bytes = len(normalized_config)
        else:
            content_sha256 = bytes.fromhex(str(snapshot["sha256"]))
            content_bytes = int(snapshot["bytes"])
        digest.update(struct.pack(">I", len(encoded_path)))
        digest.update(encoded_path)
        digest.update(struct.pack(">Q", content_bytes))
        digest.update(content_sha256)
        digest.update(struct.pack(">I", int(snapshot["mode"])))
        digest.update(struct.pack(">Q", int(snapshot["nlink"])))
    return {
        "encoding": TEST_EXECUTION_SNAPSHOT_ENCODING,
        "file_count": len(TEST_EXECUTION_PATHS),
        "aggregate_sha256": digest.hexdigest(),
    }


def _python_runtime_snapshot(
    root: Path,
) -> tuple[dict[str, object], dict[str, Any]]:
    locator_snapshot, locked = _snapshot_runtime_locator(root)
    running = Path(sys.executable).resolve(strict=True)
    locked_stat = locked.stat()
    running_stat = running.stat()
    if (locked_stat.st_dev, locked_stat.st_ino) != (
        running_stat.st_dev,
        running_stat.st_ino,
    ):
        raise HumanAdjudicationPreregistrationError(
            "the attestation builder is not running under the locked test interpreter"
        )
    snapshot = _snapshot_regular_file(
        locked.parent, locked.name, retain_payload=False
    )
    if int(snapshot["mode"]) & 0o022:
        raise HumanAdjudicationPreregistrationError(
            "the locked test interpreter is writable by group or other"
        )
    summary = {
        "binding": "resolved-regular-file-sha256+bytes+implementation+version-v1",
        "implementation": sys.implementation.name,
        "version": ".".join(str(item) for item in sys.version_info[:3]),
        "executable_sha256": snapshot["sha256"],
        "executable_bytes": snapshot["bytes"],
    }
    return summary, {**snapshot, "runtime_locator": locator_snapshot}


def _snapshot_runtime_locator(root: Path) -> tuple[dict[str, Any], Path]:
    """Bind the project-local runtime locator without following its leaf."""
    parts = _relative_parts(TEST_COMMAND_ARGV[0])
    descriptors = _open_directory_chain(root, parts[:-1])
    parent_chain = tuple(
        (value.st_dev, value.st_ino, value.st_mode)
        for value in (os.fstat(descriptor) for descriptor in descriptors)
    )
    try:
        initial = os.stat(parts[-1], dir_fd=descriptors[-1], follow_symlinks=False)
        if not (stat.S_ISLNK(initial.st_mode) or stat.S_ISREG(initial.st_mode)):
            raise OSError("locked runtime locator is neither a symlink nor a file")
        link_target = (
            os.readlink(parts[-1], dir_fd=descriptors[-1])
            if stat.S_ISLNK(initial.st_mode)
            else None
        )
        resolved = (root.resolve(strict=True) / Path(*parts)).resolve(strict=True)
        after = os.stat(parts[-1], dir_fd=descriptors[-1], follow_symlinks=False)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    fresh_descriptors = _open_directory_chain(root, parts[:-1])
    fresh_chain = tuple(
        (value.st_dev, value.st_ino, value.st_mode)
        for value in (os.fstat(descriptor) for descriptor in fresh_descriptors)
    )
    try:
        final = os.stat(
            parts[-1], dir_fd=fresh_descriptors[-1], follow_symlinks=False
        )
    finally:
        for descriptor in reversed(fresh_descriptors):
            os.close(descriptor)
    if (
        not _same_snapshot(initial, after)
        or not _same_snapshot(after, final)
        or parent_chain != fresh_chain
    ):
        raise OSError("locked runtime locator changed while it was snapshotted")
    return {
        "parent_chain": parent_chain,
        "identity": (after.st_dev, after.st_ino),
        "full_mode": after.st_mode,
        "nlink": after.st_nlink,
        "bytes": after.st_size,
        "mtime_ns": after.st_mtime_ns,
        "ctime_ns": after.st_ctime_ns,
        "link_target": link_target,
        "resolved_path": resolved,
    }, resolved


def _runtime_locator_seal(snapshot: Mapping[str, Any]) -> tuple[object, ...]:
    return tuple(
        snapshot.get(key)
        for key in (
            "parent_chain",
            "identity",
            "full_mode",
            "nlink",
            "bytes",
            "mtime_ns",
            "ctime_ns",
            "link_target",
            "resolved_path",
        )
    )


def _python_runtime_summary(root: Path) -> dict[str, object]:
    summary, _snapshot = _python_runtime_snapshot(root)
    return summary


def _resolved_runtime_identity(path: Path) -> tuple[int, int]:
    resolved = path.resolve(strict=True)
    current = resolved.stat()
    if not stat.S_ISREG(current.st_mode):
        raise OSError("the staged test interpreter target is not regular")
    return current.st_dev, current.st_ino


def _copy_execution_snapshot(
    root: Path,
    snapshots: Mapping[str, Mapping[str, Any]],
    *,
    runtime_identity: tuple[int, int],
) -> tuple[Path, dict[str, dict[str, Any]]]:
    stage = Path(tempfile.mkdtemp(prefix="query202-human-test-attestation-"))
    os.chmod(stage, 0o700)
    staged_snapshots: dict[str, dict[str, Any]] = {}
    try:
        for relative in TEST_EXECUTION_PATHS:
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            for parent in destination.parents:
                if parent == stage.parent:
                    break
                if parent == stage or stage in parent.parents:
                    os.chmod(parent, 0o700)
            payload = snapshots[relative].get("payload")
            if not isinstance(payload, bytes):
                raise HumanAdjudicationPreregistrationError(
                    "an execution dependency snapshot is unavailable"
                )
            descriptor = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise OSError("short staged snapshot write")
                    view = view[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            staged_snapshots[relative] = _snapshot_regular_file(
                stage, relative, retain_payload=False
            )

        interpreter = (root / TEST_COMMAND_ARGV[0]).resolve(strict=True)
        if not interpreter.is_file():
            raise OSError("the locked test interpreter is unavailable")
        staged_interpreter = stage / TEST_COMMAND_ARGV[0]
        staged_interpreter.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(staged_interpreter.parent, 0o700)
        os.symlink(interpreter, staged_interpreter)
        if _resolved_runtime_identity(staged_interpreter) != runtime_identity:
            raise OSError("the staged interpreter resolves to a different runtime")
        for relative in (".attestation-home", ".attestation-tmp"):
            path = stage / relative
            path.mkdir(mode=0o700)
        return stage, staged_snapshots
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _parse_successful_unittest_result(
    result: subprocess.CompletedProcess[str],
) -> tuple[int, tuple[str, ...]]:
    if result.returncode != 0:
        raise HumanAdjudicationPreregistrationError(
            "the exact synthetic test command did not pass"
        )
    combined = f"{result.stdout}\n{result.stderr}"
    matches = re.findall(r"^Ran ([0-9]+) tests? in [0-9.]+s$", combined, re.MULTILINE)
    ok = re.findall(r"^OK$", combined, re.MULTILINE)
    result_lines = re.findall(
        r"^(test[^ ]*) \(([^\r\n()]+)\) \.\.\. ([^\r\n]+)$",
        combined,
        re.MULTILINE,
    )
    if len(matches) != 1 or len(ok) != 1:
        raise HumanAdjudicationPreregistrationError(
            "the exact synthetic test command did not emit one successful unittest summary"
        )
    count = int(matches[0])
    if count <= 0 or len(result_lines) != count:
        raise HumanAdjudicationPreregistrationError(
            "the exact synthetic test command did not report every test result"
        )
    if any(status != "ok" for _method, _test_id, status in result_lines):
        raise HumanAdjudicationPreregistrationError(
            "every locked synthetic test must report exactly ok"
        )
    test_ids = tuple(test_id for _method, test_id, _status in result_lines)
    if len(set(test_ids)) != len(test_ids):
        raise HumanAdjudicationPreregistrationError(
            "the exact synthetic test command reported a duplicate test ID"
        )
    return count, test_ids


def _parse_successful_unittest_count(result: subprocess.CompletedProcess[str]) -> int:
    """Compatibility wrapper retained for callers that only need the count."""
    count, _test_ids = _parse_successful_unittest_result(result)
    return count


def build_test_attestation(root: Path) -> dict[str, Any]:
    """Run the locked suite and return deterministic, private-safe evidence."""
    config, _config_sha256, config_snapshot = _read_config_snapshot(root)
    validation_errors = validate_query202_human_adjudication_preregistration(config)
    if validation_errors:
        raise HumanAdjudicationPreregistrationError(
            "the human-adjudication machine contract is invalid"
        )
    gate = _as_mapping(config.get("test_attestation"))
    if gate.get("required_test_paths") != list(REQUIRED_TEST_PATHS):
        raise HumanAdjudicationPreregistrationError(
            "the required test inventory differs from its exact lock"
        )
    if gate.get("required_mutation_classes") != list(REQUIRED_MUTATION_CLASSES):
        raise HumanAdjudicationPreregistrationError(
            "the required mutation classes differ from their exact lock"
        )
    if (
        gate.get("required_test_count") != EXPECTED_TEST_COUNT
        or gate.get("ordered_test_ids_sha256") != EXPECTED_ORDERED_TEST_IDS_SHA256
        or gate.get("mutation_test_ids") != EXPECTED_MUTATION_TEST_IDS
        or gate.get("mutation_test_ids_sha256")
        != EXPECTED_MUTATION_TEST_IDS_SHA256
        or gate.get("test_command_argv") != list(TEST_COMMAND_ARGV)
        or gate.get("test_command_environment")
        != [f"{key}={value}" for key, value in TEST_COMMAND_ENV]
        or gate.get("test_execution_paths") != list(TEST_EXECUTION_PATHS)
    ):
        raise HumanAdjudicationPreregistrationError(
            "the exact test IDs, mutation mapping, command, or execution closure are not locked"
        )
    if EXPECTED_ORDERED_TEST_IDS_SHA256 == "0" * 64:
        raise HumanAdjudicationPreregistrationError(
            "the ordered test-ID digest is not locked"
        )

    execution_snapshots: dict[str, dict[str, Any]] = {}
    for relative in TEST_EXECUTION_PATHS:
        snapshot = _snapshot_regular_file(root, relative, retain_payload=True)
        if int(snapshot["mode"]) & 0o022 or int(snapshot["nlink"]) != 1:
            raise HumanAdjudicationPreregistrationError(
                "an execution dependency has an unsafe mode or link count"
            )
        execution_snapshots[relative] = snapshot
    python_runtime, runtime_snapshot = _python_runtime_snapshot(root)

    bundle_hashes: dict[str, str] = {}
    for name, paths in EXPECTED_IMPLEMENTATION_PATHS.items():
        digest = hashlib.sha256()
        for relative in paths:
            payload = execution_snapshots[relative]["payload"]
            assert isinstance(payload, bytes)
            encoded_path = relative.encode("utf-8")
            digest.update(struct.pack(">I", len(encoded_path)))
            digest.update(encoded_path)
            digest.update(struct.pack(">Q", len(payload)))
            digest.update(payload)
        bundle_hashes[name] = digest.hexdigest()

    test_files: list[dict[str, str]] = []
    for relative in REQUIRED_TEST_PATHS:
        snapshot = execution_snapshots[relative]
        test_files.append(
            {"path": relative, "file_sha256": str(snapshot["sha256"])}
        )

    stage: Path | None = None
    try:
        stage, staged_snapshots = _copy_execution_snapshot(
            root,
            execution_snapshots,
            runtime_identity=tuple(runtime_snapshot["identity"]),
        )
        result = subprocess.run(
            list(TEST_COMMAND_ARGV),
            cwd=stage,
            env=dict(TEST_COMMAND_ENV),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=1200,
        )
        tests_run, test_ids = _parse_successful_unittest_result(result)
        if _resolved_runtime_identity(stage / TEST_COMMAND_ARGV[0]) != tuple(
            runtime_snapshot["identity"]
        ):
            raise HumanAdjudicationPreregistrationError(
                "the staged interpreter target changed while tests ran"
            )
        runtime_after, runtime_snapshot_after = _python_runtime_snapshot(root)
        if (
            runtime_after != python_runtime
            or _snapshot_seal(runtime_snapshot_after)
            != _snapshot_seal(runtime_snapshot)
        ):
            raise HumanAdjudicationPreregistrationError(
                "the locked Python runtime changed while tests ran"
            )
        for relative, initial in staged_snapshots.items():
            final = _snapshot_regular_file(stage, relative, retain_payload=False)
            if _snapshot_seal(final) != _snapshot_seal(initial):
                raise HumanAdjudicationPreregistrationError(
                    "the private staged execution snapshot changed while tests ran"
                )
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise HumanAdjudicationPreregistrationError(
            "the exact synthetic test command could not complete"
        ) from exc
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)

    if tests_run != EXPECTED_TEST_COUNT:
        raise HumanAdjudicationPreregistrationError(
            "the observed test count differs from the pinned exact count"
        )
    ordered_test_ids_sha256 = _ordered_test_ids_sha256(test_ids)
    if ordered_test_ids_sha256 != EXPECTED_ORDERED_TEST_IDS_SHA256:
        raise HumanAdjudicationPreregistrationError(
            "the observed ordered test IDs differ from their exact lock"
        )
    observed_test_ids = set(test_ids)
    if any(
        not ids or any(test_id not in observed_test_ids for test_id in ids)
        for ids in EXPECTED_MUTATION_TEST_IDS.values()
    ):
        raise HumanAdjudicationPreregistrationError(
            "a required mutation class is not backed by its exact passing test IDs"
        )

    for relative, initial in execution_snapshots.items():
        try:
            final = _snapshot_regular_file(root, relative, retain_payload=False)
        except (OSError, ValueError) as exc:
            raise HumanAdjudicationPreregistrationError(
                "the machine contract, implementation, or tests changed during execution"
            ) from exc
        if _snapshot_seal(final) != _snapshot_seal(initial):
            raise HumanAdjudicationPreregistrationError(
                "the machine contract, implementation, or tests changed during execution"
            )

    return {
        "schema_version": 2,
        "component_id": COMPONENT_ID,
        "status": "passed",
        "test_command": TEST_COMMAND,
        "test_command_argv": list(TEST_COMMAND_ARGV),
        "test_command_environment": [
            f"{key}={value}" for key, value in TEST_COMMAND_ENV
        ],
        "tests_run": tests_run,
        "failures": 0,
        "errors": 0,
        "scientific_contract_sha256": scientific_contract_sha256(config),
        "implementation_bundles": [
            {"name": name, "bundle_sha256": bundle_hashes[name]}
            for name in EXPECTED_IMPLEMENTATION_PATHS
        ],
        "test_files": test_files,
        "mutation_classes_passed": list(REQUIRED_MUTATION_CLASSES),
        "ordered_test_ids_sha256": ordered_test_ids_sha256,
        "mutation_test_ids_sha256": EXPECTED_MUTATION_TEST_IDS_SHA256,
        "execution_snapshot": _execution_snapshot_summary(
            config, execution_snapshots
        ),
        "python_runtime": python_runtime,
    }


def _check_equal(
    checks: dict[str, bool],
    errors: list[str],
    label: str,
    actual: object,
    expected: object,
) -> None:
    passed = _strict_equal(actual, expected)
    checks[label] = passed
    if not passed:
        errors.append(f"source evidence {label} mismatch")


def _git_ignored(root: Path, relative: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", relative],
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
    )
    return result.returncode == 0


def _public_stream_metadata(spec: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "file": spec["file"],
        "encoding": "gzip+utf8+ndjson-v1",
        "sha256": spec["stored_sha256"],
        "bytes": spec["stored_bytes"],
        "raw_sha256": spec["raw_sha256"],
        "raw_bytes": spec["raw_bytes"],
        "records": spec["records"],
    }


def _verify_source_evidence(
    root: Path,
    errors: list[str],
) -> tuple[
    dict[str, bool],
    dict[str, tuple[str, dict[str, Any]]],
    dict[str, Any] | None,
]:
    checks: dict[str, bool] = {}
    source = EXPECTED_SOURCE_ARTIFACT
    artifact_relative = str(source["directory"])
    try:
        directory_snapshot = _directory_seal(root, artifact_relative)
        directory_ok = directory_snapshot["mode"] == 0o700
    except (OSError, ValueError):
        directory_snapshot = None
        directory_ok = False
    checks["artifact_directory_private_mode"] = directory_ok
    if not directory_ok:
        errors.append("source evidence artifact directory check failed")

    file_specs = {
        "source_config": (
            source["source_config_path"],
            source["source_config_sha256"],
            None,
            None,
            True,
        ),
        "manifest": (
            str(Path(artifact_relative) / str(source["manifest_file"])),
            source["manifest_sha256"],
            None,
            0o600,
            True,
        ),
        "aggregate_summary": (
            str(Path(artifact_relative) / str(source["aggregate_summary_file"])),
            source["aggregate_summary_sha256"],
            None,
            0o600,
            True,
        ),
        "audit": (
            str(Path(artifact_relative) / str(source["audit_file"])),
            source["audit_sha256"],
            None,
            0o600,
            True,
        ),
        "semantic_template": (
            str(Path(artifact_relative) / str(EXPECTED_SEMANTIC_TEMPLATE["file"])),
            EXPECTED_SEMANTIC_TEMPLATE["stored_sha256"],
            EXPECTED_SEMANTIC_TEMPLATE["stored_bytes"],
            0o600,
            False,
        ),
        "local_evidence": (
            str(Path(artifact_relative) / str(EXPECTED_LOCAL_EVIDENCE["file"])),
            EXPECTED_LOCAL_EVIDENCE["stored_sha256"],
            EXPECTED_LOCAL_EVIDENCE["stored_bytes"],
            0o600,
            False,
        ),
        "route_template": (
            str(Path(artifact_relative) / str(EXPECTED_ROUTE_TEMPLATE["file"])),
            EXPECTED_ROUTE_TEMPLATE["stored_sha256"],
            EXPECTED_ROUTE_TEMPLATE["stored_bytes"],
            0o600,
            False,
        ),
    }
    snapshots: dict[str, dict[str, Any]] = {}
    closure: dict[str, tuple[str, dict[str, Any]]] = {}
    for label, (relative, expected_hash, expected_bytes, expected_mode, retain) in file_specs.items():
        try:
            snapshot = _snapshot_regular_file(root, relative, retain_payload=retain)
            snapshots[label] = snapshot
            closure[f"source:{label}"] = (str(relative), snapshot)
            matches = snapshot["sha256"] == expected_hash
            if expected_bytes is not None:
                matches = matches and snapshot["bytes"] == expected_bytes
            if expected_mode is not None:
                matches = (
                    matches
                    and snapshot["mode"] == expected_mode
                    and snapshot["nlink"] == 1
                )
        except (OSError, ValueError):
            matches = False
        checks[f"{label}_whole_file"] = matches
        if not matches:
            errors.append(f"source evidence {label} whole-file check failed")

    documents: dict[str, Mapping[str, Any]] = {}
    for label in ("manifest", "aggregate_summary", "audit"):
        try:
            payload = snapshots[label]["payload"]
            if not isinstance(payload, bytes):
                raise ValueError("public document payload unavailable")
            document = _strict_json(payload)
            if not isinstance(document, Mapping):
                raise ValueError("public document is not an object")
            documents[label] = document
            passed = True
        except (KeyError, TypeError, UnicodeDecodeError, ValueError):
            passed = False
        checks[f"{label}_strict_json"] = passed
        if not passed:
            errors.append(f"source evidence {label} public JSON check failed")

    try:
        source_payload = snapshots["source_config"]["payload"]
        if not isinstance(source_payload, bytes):
            raise ValueError("source configuration payload unavailable")
        source_config = tomllib.loads(source_payload.decode("utf-8"))
        implementation = _as_mapping(source_config.get("implementation"))
        output = _as_mapping(source_config.get("output"))
        source_config_ok = (
            source_config.get("component_id") == SOURCE_COMPONENT_ID
            and source_config.get("status") == "frozen_for_execution"
            and source_config.get("execution_permitted") is True
            and implementation.get("compiler_bundle_sha256")
            == "0e9ae039b3c3484baf3cbcdd3665ebd7f07fc37d31406921f20e6d6cede163aa"
            and implementation.get("auditor_bundle_sha256")
            == "931263c491aa4d3b24bdc8acf40d22ef282d9aa819f1ebd9ed37e04c0838c065"
            and output.get("semantic_file") == EXPECTED_SEMANTIC_TEMPLATE["file"]
            and output.get("local_evidence_file") == EXPECTED_LOCAL_EVIDENCE["file"]
            and output.get("route_file") == EXPECTED_ROUTE_TEMPLATE["file"]
            and output.get("semantic_records") == EXPECTED_SEMANTIC_TEMPLATE["semantic_keys"]
            and output.get("local_evidence_tuples") == EXPECTED_LOCAL_EVIDENCE["unique_tuples"]
            and output.get("local_evidence_multiplicity") == EXPECTED_LOCAL_EVIDENCE["total_multiplicity"]
            and output.get("route_canonical_nonnull_values")
            == EXPECTED_ROUTE_TEMPLATE["canonical_exact_nonnull_values"]
            and output.get("route_typed_memberships")
            == EXPECTED_ROUTE_TEMPLATE["source_specific_typed_memberships"]
        )
    except (KeyError, TypeError, UnicodeDecodeError, tomllib.TOMLDecodeError, ValueError):
        source_config_ok = False
    checks["source_config_contract"] = source_config_ok
    if not source_config_ok:
        errors.append("source evidence source configuration contract mismatch")

    if len(documents) == 3:
        manifest = documents["manifest"]
        summary = documents["aggregate_summary"]
        audit = documents["audit"]
        semantic_public = _public_stream_metadata(EXPECTED_SEMANTIC_TEMPLATE)
        local_public = _public_stream_metadata(EXPECTED_LOCAL_EVIDENCE)
        route_public = _public_stream_metadata(EXPECTED_ROUTE_TEMPLATE)
        _check_equal(checks, errors, "manifest_component", (manifest.get("component_id"), manifest.get("status")), (SOURCE_COMPONENT_ID, "complete"))
        _check_equal(checks, errors, "manifest_artifact_directory", manifest.get("artifact_directory"), artifact_relative)
        lineage = _as_mapping(manifest.get("component_lineage"))
        _check_equal(
            checks,
            errors,
            "manifest_component_lineage",
            (
                lineage.get("component_id"),
                lineage.get("config"),
                lineage.get("config_sha256"),
                lineage.get("status_at_execution"),
                lineage.get("compiler_bundle_sha256"),
                lineage.get("auditor_bundle_sha256"),
            ),
            (
                SOURCE_COMPONENT_ID,
                source["source_config_path"],
                source["source_config_sha256"],
                "frozen_for_execution",
                "0e9ae039b3c3484baf3cbcdd3665ebd7f07fc37d31406921f20e6d6cede163aa",
                "931263c491aa4d3b24bdc8acf40d22ef282d9aa819f1ebd9ed37e04c0838c065",
            ),
        )
        outputs = _as_mapping(manifest.get("outputs"))
        _check_equal(checks, errors, "manifest_semantic_metadata", outputs.get("semantic_review_template"), semantic_public)
        _check_equal(checks, errors, "manifest_local_metadata", outputs.get("local_evidence"), local_public)
        _check_equal(checks, errors, "manifest_route_metadata", outputs.get("route_review_template"), route_public)
        _check_equal(checks, errors, "summary_component", (summary.get("component_id"), summary.get("status")), (SOURCE_COMPONENT_ID, "complete"))
        summary_outputs = _as_mapping(summary.get("output_hashes"))
        _check_equal(checks, errors, "summary_semantic_metadata", summary_outputs.get("semantic_review_template"), semantic_public)
        _check_equal(checks, errors, "summary_local_metadata", summary_outputs.get("local_evidence"), local_public)
        _check_equal(checks, errors, "summary_route_metadata", summary_outputs.get("route_review_template"), route_public)
        _check_equal(checks, errors, "audit_component", (audit.get("component_id"), audit.get("status")), (SOURCE_COMPONENT_ID, source["audit_status"]))
        _check_equal(checks, errors, "audit_failed_checks", _as_mapping(audit.get("checks")).get("failed"), source["audit_failed_checks"])
        recomputed = _as_mapping(audit.get("recomputed"))
        _check_equal(checks, errors, "audit_public_lineage_hashes", (recomputed.get("manifest_sha256"), recomputed.get("aggregate_summary_sha256")), (source["manifest_sha256"], source["aggregate_summary_sha256"]))
        _check_equal(checks, errors, "audit_component_lineage", recomputed.get("component_lineage"), lineage)
        audit_outputs = _as_mapping(recomputed.get("output_hashes"))
        _check_equal(checks, errors, "audit_semantic_metadata", audit_outputs.get("semantic_review_template"), semantic_public)
        _check_equal(checks, errors, "audit_local_metadata", audit_outputs.get("local_evidence"), local_public)
        _check_equal(checks, errors, "audit_route_metadata", audit_outputs.get("route_review_template"), route_public)
        _check_equal(
            checks,
            errors,
            "audit_semantic_universe",
            (recomputed.get("semantic_review_keys"), recomputed.get("semantic_seed_key_set_sha256")),
            (EXPECTED_SEMANTIC_TEMPLATE["semantic_keys"], EXPECTED_SEMANTIC_TEMPLATE["semantic_key_set_sha256"]),
        )
        _check_equal(
            checks,
            errors,
            "audit_local_universe",
            (recomputed.get("local_evidence_unique_tuples"), recomputed.get("local_evidence_total_multiplicity")),
            (EXPECTED_LOCAL_EVIDENCE["unique_tuples"], EXPECTED_LOCAL_EVIDENCE["total_multiplicity"]),
        )
        _check_equal(
            checks,
            errors,
            "audit_route_universe",
            (
                recomputed.get("route_canonical_exact_nonnull_values"),
                recomputed.get("route_source_specific_typed_memberships"),
                recomputed.get("route_canonical_exact_set_sha256"),
            ),
            (
                EXPECTED_ROUTE_TEMPLATE["canonical_exact_nonnull_values"],
                EXPECTED_ROUTE_TEMPLATE["source_specific_typed_memberships"],
                EXPECTED_ROUTE_TEMPLATE["canonical_exact_set_sha256"],
            ),
        )
        _check_equal(
            checks,
            errors,
            "source_privacy_and_audit",
            (
                _as_mapping(manifest.get("privacy")).get("public_raw_values_emitted"),
                _as_mapping(manifest.get("privacy")).get("external_api_called"),
                audit.get("raw_values_emitted"),
                audit.get("external_api_called"),
                audit.get("database_connection_opened"),
                recomputed.get("private_modes_confirmed"),
                recomputed.get("public_privacy_confirmed"),
                recomputed.get("four_stream_conservation_confirmed"),
            ),
            (False, False, False, False, False, True, True, True),
        )

    for label, spec in (
        ("semantic_template", EXPECTED_SEMANTIC_TEMPLATE),
        ("local_evidence", EXPECTED_LOCAL_EVIDENCE),
        ("route_template", EXPECTED_ROUTE_TEMPLATE),
    ):
        relative = str(Path(artifact_relative) / str(spec["file"]))
        try:
            ignored = _git_ignored(root, relative)
        except (OSError, subprocess.SubprocessError):
            ignored = False
        checks[f"{label}_git_ignored"] = ignored
        if not ignored:
            errors.append(f"source evidence {label} is not Git ignored")
    return checks, closure, directory_snapshot


def _verify_ndc_decision(
    root: Path,
    errors: list[str],
) -> tuple[dict[str, bool], dict[str, tuple[str, dict[str, Any]]]]:
    checks: dict[str, bool] = {}
    closure: dict[str, tuple[str, dict[str, Any]]] = {}
    relative = str(EXPECTED_NDC_DECISION["config_path"])
    try:
        snapshot = _snapshot_regular_file(root, relative, retain_payload=True)
        closure["ndc:decision_config"] = (relative, snapshot)
        checks["config_whole_file"] = snapshot["sha256"] == EXPECTED_NDC_DECISION["config_sha256"]
        payload = snapshot["payload"]
        if not isinstance(payload, bytes):
            raise ValueError("NDC configuration payload unavailable")
        ndc = tomllib.loads(payload.decode("utf-8"))
        checks["config_strict_toml"] = True
    except (OSError, ValueError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        ndc = {}
        checks.setdefault("config_whole_file", False)
        checks["config_strict_toml"] = False
    decision = _as_mapping(ndc.get("decision"))
    boundary = _as_mapping(ndc.get("evidence_boundary"))
    implementation = _as_mapping(ndc.get("implementation"))
    guards = _as_mapping(ndc.get("guards"))
    source = _as_mapping(ndc.get("source"))
    expected_checks = {
        "component_and_status": (
            (ndc.get("component_id"), ndc.get("status")),
            (NDC_COMPONENT_ID, EXPECTED_NDC_DECISION["required_status"]),
        ),
        "nonexecuting_decision": (
            (ndc.get("execution_status"), ndc.get("execution_permitted")),
            ("not_applicable", False),
        ),
        "mode_frozen_effective": (
            (
                decision.get("mode"),
                decision.get("lifecycle_state"),
                decision.get("effective"),
            ),
            (EXPECTED_NDC_DECISION["required_mode"], "frozen", True),
        ),
        "handoff_rows_forbidden": (
            (
                boundary.get("private_handoff_rows_may_be_read"),
                boundary.get("private_handoff_rows_may_be_printed"),
                boundary.get("semantic_adjudication_may_consume_ndc"),
            ),
            (False, False, False),
        ),
        "validator_bundle_bound": (
            implementation.get("validator_bundle_sha256"),
            EXPECTED_NDC_DECISION["validator_bundle_sha256"],
        ),
        "frozen_guard_only": (
            (
                guards.get("ndc_mode_frozen"),
                guards.get("external_ndc_mapping_executed"),
                guards.get("product_identity_decided"),
            ),
            (True, False, False),
        ),
        "source_artifact_binding": (
            (
                source.get("artifact_directory"),
                source.get("config_sha256"),
                source.get("manifest_sha256"),
                source.get("aggregate_summary_sha256"),
                source.get("audit_sha256"),
            ),
            (
                EXPECTED_SOURCE_ARTIFACT["directory"],
                EXPECTED_SOURCE_ARTIFACT["source_config_sha256"],
                EXPECTED_SOURCE_ARTIFACT["manifest_sha256"],
                EXPECTED_SOURCE_ARTIFACT["aggregate_summary_sha256"],
                EXPECTED_SOURCE_ARTIFACT["audit_sha256"],
            ),
        ),
    }
    for label, (actual, expected) in expected_checks.items():
        checks[label] = _strict_equal(actual, expected)
    for label, passed in checks.items():
        if not passed:
            errors.append(f"NDC decision {label} check failed")
    return checks, closure


def _verify_snapshot_closure(
    root: Path,
    initial_snapshots: Mapping[str, tuple[str, Mapping[str, Any]]],
    initial_artifact_directory: Mapping[str, Any] | None,
    errors: list[str],
) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    for label, (relative, initial) in initial_snapshots.items():
        try:
            final = _snapshot_regular_file(root, relative, retain_payload=False)
            stable = _snapshot_seal(final) == _snapshot_seal(initial)
        except (OSError, ValueError):
            stable = False
        checks[f"{label}:stable"] = stable
        if not stable:
            errors.append(f"snapshot closure {label} changed")
    try:
        final_directory = _directory_seal(root, EXPECTED_SOURCE_ARTIFACT["directory"])
        directory_stable = (
            initial_artifact_directory is not None
            and _strict_equal(final_directory, initial_artifact_directory)
            and final_directory.get("mode") == 0o700
        )
    except (OSError, ValueError):
        directory_stable = False
    checks["source:artifact_directory:stable"] = directory_stable
    if not directory_stable:
        errors.append("snapshot closure source artifact directory changed")
    return checks


def query202_human_adjudication_preregistration_report(root: Path) -> dict[str, Any]:
    config, config_sha256, config_snapshot = _read_config_snapshot(root)
    errors = validate_query202_human_adjudication_preregistration(config)
    source_checks, source_snapshots, artifact_directory_snapshot = _verify_source_evidence(root, errors)
    ndc_checks, ndc_snapshots = _verify_ndc_decision(root, errors)

    configured_implementation = _as_mapping(config.get("implementation"))
    implementation_report: dict[str, dict[str, Any]] = {}
    implementation_snapshots: dict[str, tuple[str, dict[str, Any]]] = {}
    for name, paths in EXPECTED_IMPLEMENTATION_PATHS.items():
        try:
            actual, snapshots = _implementation_bundle_snapshot(root, paths)
            available = True
            for relative, value in snapshots.items():
                implementation_snapshots[f"implementation:{name}:{relative}"] = value
        except OSError:
            actual = None
            available = False
        configured = configured_implementation.get(f"{name}_bundle_sha256")
        implementation_report[name] = {
            "paths": list(paths),
            "configured_bundle_sha256": configured,
            "actual_bundle_sha256": actual,
            "bundle_available": available,
            "bundle_frozen_and_verified": (
                available
                and isinstance(configured, str)
                and configured != PLACEHOLDER
                and actual == configured
            ),
        }
        if (
            config.get("implementation_state") == "implemented_and_tested"
            and not implementation_report[name]["bundle_frozen_and_verified"]
        ):
            errors.append(f"implementation {name} bundle hash mismatch")

    actual_bundle_hashes = {
        name: state["actual_bundle_sha256"]
        for name, state in implementation_report.items()
    }
    (
        test_attestation_verified,
        test_attestation_problems,
        test_attestation_report,
        test_attestation_snapshots,
    ) = _verify_test_attestation(root, config, actual_bundle_hashes)
    candidate_contract = config.get("implementation_state") == "implemented_and_tested"
    if candidate_contract and not test_attestation_verified:
        errors.extend(
            test_attestation_problems
            or ["machine-bound synthetic test attestation is not verified"]
        )

    initial_snapshots: dict[str, tuple[str, Mapping[str, Any]]] = {
        "proposal_config": (str(CONFIG_PATH), config_snapshot),
        **source_snapshots,
        **ndc_snapshots,
        **implementation_snapshots,
        **test_attestation_snapshots,
    }
    closure_checks = _verify_snapshot_closure(
        root, initial_snapshots, artifact_directory_snapshot, errors
    )
    required_closure_labels = {
        "proposal_config:stable",
        "source:source_config:stable",
        "source:manifest:stable",
        "source:aggregate_summary:stable",
        "source:audit:stable",
        "source:semantic_template:stable",
        "source:local_evidence:stable",
        "source:route_template:stable",
        "ndc:decision_config:stable",
        "source:artifact_directory:stable",
    }
    required_closure_verified = (
        required_closure_labels.issubset(closure_checks)
        and all(closure_checks[label] for label in required_closure_labels)
    )
    snapshot_closure_verified = required_closure_verified and all(closure_checks.values())
    implementation_snapshot_inventory_complete = all(
        implementation_report[name]["bundle_available"]
        for name in EXPECTED_IMPLEMENTATION_PATHS
    )
    full_snapshot_closure_verified = (
        snapshot_closure_verified and implementation_snapshot_inventory_complete
    )
    if not required_closure_verified and not any(
        error.startswith("snapshot closure") for error in errors
    ):
        errors.append("snapshot closure source/config inventory incomplete")

    source_verified = bool(source_checks) and all(source_checks.values())
    ndc_verified = bool(ndc_checks) and all(ndc_checks.values())
    valid = not errors and source_verified and ndc_verified and snapshot_closure_verified

    execution_gate = _as_mapping(config.get("execution_gate"))
    blocker_value = execution_gate.get("unresolved_blockers")
    configured_blockers = list(blocker_value) if isinstance(blocker_value, list) else []
    freeze_candidate_blockers = list(configured_blockers)
    human_review_policy = _as_mapping(config.get("human_review_policy"))
    if (
        human_review_policy.get("reviewer_model")
        != "single_reviewer_with_full_attestation"
        or human_review_policy.get(
            "single_reviewer_identity_must_match_all_item_group_revision_and_batch_attestation_records"
        )
        is not True
    ):
        freeze_candidate_blockers.append(
            "single-reviewer model and global identity invariant are not locked"
        )
    for name in EXPECTED_IMPLEMENTATION_PATHS:
        state = implementation_report[name]
        if not state["bundle_available"]:
            freeze_candidate_blockers.append(
                f"{name} implementation bundle is unavailable"
            )
        if state["configured_bundle_sha256"] == PLACEHOLDER:
            freeze_candidate_blockers.append(
                f"{name} implementation bundle hash is unset"
            )
        elif not state["bundle_frozen_and_verified"]:
            freeze_candidate_blockers.append(
                f"{name} implementation bundle hash does not match"
            )
    if config.get("implementation_state") != "implemented_and_tested":
        freeze_candidate_blockers.append(
            "implementation state is not implemented_and_tested"
        )
    if not test_attestation_verified:
        freeze_candidate_blockers.append(
            "machine-bound synthetic test attestation is not verified"
        )
    if not full_snapshot_closure_verified:
        freeze_candidate_blockers.append(
            "full config source NDC and implementation snapshot closure is incomplete"
        )
    if not valid:
        freeze_candidate_blockers.append(
            "preregistration or bound evidence validation failed"
        )

    freeze_candidate_ready = (
        valid
        and config.get("status") == "proposed"
        and not freeze_candidate_blockers
        and all(
            implementation_report[name]["bundle_frozen_and_verified"]
            for name in EXPECTED_IMPLEMENTATION_PATHS
        )
        and test_attestation_verified
        and full_snapshot_closure_verified
    )
    readiness_blockers = list(freeze_candidate_blockers)
    if config.get("status") != "frozen_for_execution":
        readiness_blockers.append("preregistration is not frozen for execution")
    if config.get("execution_permitted") is not True:
        readiness_blockers.append("workspace initialization is not permitted")

    initialization_ready = (
        valid
        and config.get("status") == "frozen_for_execution"
        and config.get("execution_permitted") is True
        and not readiness_blockers
        and all(
            implementation_report[name]["bundle_frozen_and_verified"]
            for name in EXPECTED_IMPLEMENTATION_PATHS
        )
        and test_attestation_verified
        and full_snapshot_closure_verified
    )
    return {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "status": config.get("status"),
        "execution_status": config.get("execution_status"),
        "execution_permitted": config.get("execution_permitted"),
        "implementation_state": config.get("implementation_state"),
        "valid": valid,
        "proposal_valid": valid and config.get("status") == "proposed",
        "freeze_candidate_ready": freeze_candidate_ready,
        "freeze_ready": freeze_candidate_ready,
        "frozen_contract_effective": initialization_ready,
        "initialization_ready": initialization_ready,
        "source_evidence_verified": source_verified,
        "source_checks": source_checks,
        "ndc_decision_verified": ndc_verified,
        "ndc_checks": ndc_checks,
        "snapshot_closure_verified": snapshot_closure_verified,
        "source_config_snapshot_closure_verified": required_closure_verified,
        "implementation_snapshot_inventory_complete": (
            implementation_snapshot_inventory_complete
        ),
        "full_snapshot_closure_verified": full_snapshot_closure_verified,
        "required_source_config_closure_count": len(required_closure_labels),
        "snapshot_closure_checks": closure_checks,
        "implementation": implementation_report,
        "test_attestation": test_attestation_report,
        "configured_blockers": configured_blockers,
        "freeze_candidate_blockers": freeze_candidate_blockers,
        "readiness_blockers": readiness_blockers,
        "structural_preview": {
            "policy_verified": _strict_equal(
                config.get("structural_preview"), EXPECTED_STRUCTURAL_PREVIEW
            ),
            "enabled_for_internal_api": True,
            "cli_entry_allowed": False,
            "formal_workspace": False,
            "resume_or_upgrade_to_formal_allowed": False,
            "compile_audit_or_freeze_allowed": False,
        },
        "privacy": {
            "private_source_streams_decompressed": False,
            "private_source_records_parsed": False,
            "private_raw_values_printed": False,
            "ndc_handoff_opened": False,
            "ndc_handoff_decompressed": False,
            "external_api_called": False,
            "database_connected": False,
            "network_accessed": False,
        },
        "counts": {
            "semantic_keys": EXPECTED_SEMANTIC_TEMPLATE["semantic_keys"],
            "local_evidence_unique_tuples": EXPECTED_LOCAL_EVIDENCE["unique_tuples"],
            "local_evidence_total_multiplicity": EXPECTED_LOCAL_EVIDENCE["total_multiplicity"],
            "route_canonical_exact_nonnull_values": EXPECTED_ROUTE_TEMPLATE["canonical_exact_nonnull_values"],
            "route_source_specific_typed_memberships": EXPECTED_ROUTE_TEMPLATE["source_specific_typed_memberships"],
            "semantic_batch_size": EXPECTED_WORKSPACE["semantic_batch_size"],
            "semantic_batch_count": EXPECTED_WORKSPACE["semantic_batch_count"],
        },
        "guards": dict(config.get("guards", {}))
        if isinstance(config.get("guards"), Mapping)
        else {},
        "config": str(CONFIG_PATH),
        "config_sha256": config_sha256,
        "errors": errors,
    }


__all__ = [
    "BUNDLE_ENCODING",
    "COMPONENT_ID",
    "CONFIG_PATH",
    "EXPECTED_AUDITOR_PATHS",
    "EXPECTED_GENERATOR_PATHS",
    "EXPECTED_IMPLEMENTATION_PATHS",
    "EXPECTED_LOCAL_EVIDENCE",
    "EXPECTED_NDC_DECISION",
    "EXPECTED_REVIEW_WRITER",
    "EXPECTED_ROUTE_TEMPLATE",
    "EXPECTED_SEMANTIC_TEMPLATE",
    "EXPECTED_SOURCE_ARTIFACT",
    "HumanAdjudicationPreregistrationError",
    "REQUIRED_MUTATION_CLASSES",
    "REQUIRED_TEST_PATHS",
    "TEST_ATTESTATION_PATH",
    "TEST_COMMAND",
    "build_test_attestation",
    "implementation_bundle_sha256",
    "query202_human_adjudication_preregistration_report",
    "read_query202_human_adjudication_preregistration",
    "scientific_contract_sha256",
    "validate_query202_human_adjudication_preregistration",
]
