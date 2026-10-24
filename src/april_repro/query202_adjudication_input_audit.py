"""Independent, value-safe audit for the Query-202 adjudication-input handoff.

The module deliberately imports neither the adjudication-input compiler nor any
Query-202 runner/auditor helper.  It reimplements the framing and hashing
contracts needed to prove that four private streams are a lossless, review-
neutral projection of the frozen Query-202 lifecycle-A artifact.

Only aggregate counts and whole-file/set hashes are returned.  Exact local
values, tuples, NDCs, and per-record hashes never enter errors or the public
audit summary.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import tempfile
import tomllib
from typing import Any, Callable, Iterator, Mapping
import zlib


AUDIT_NAME = "potassium_query202_adjudication_input_offline_audit"
COMPONENT_ID = "D005-K-QUERY202-ADJUDICATION-INPUT-v1"
COMPONENT_CONFIG_PATH = Path(
    "config/preregistrations/d005_potassium_query202_adjudication_input.toml"
)
COMPONENT_BUNDLE_ENCODING = (
    "uint32be_path_length+path_utf8+uint64be_content_length+content"
)
COMPILER_IMPLEMENTATION_PATHS = (
    "src/april_repro/__init__.py",
    "src/april_repro/query202_adjudication_input_preregistration.py",
    "src/april_repro/query202_adjudication_input.py",
    "scripts/compile_potassium_query202_adjudication_input.py",
)
AUDITOR_IMPLEMENTATION_PATHS = (
    "src/april_repro/__init__.py",
    "src/april_repro/query202_adjudication_input_audit.py",
    "scripts/audit_potassium_query202_adjudication_input.py",
)
SOURCE_COMPONENT_ID = "D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2"
SOURCE_ARTIFACT_DIRECTORY = Path(
    "artifacts/profiling/20261012T152323.460063Z"
)
SOURCE_FILES = {
    "manifest": "manifest.json",
    "audit": "audit-summary.json",
    "private_values": "potassium_query202_pre_adjudication.private.jsonl.gz",
    "aggregate_summary": "potassium_query202_pre_adjudication.aggregate-summary.json",
    "executed_sql": "potassium_query202_pre_adjudication.executed.sql",
}
SOURCE_HASHES = {
    "config": "73004c1051970184b732b36a325e03c1f39e286356bcf56adbe799185e93ab73",
    "manifest": "3f8ecece96c5cb15e37ad8b7a539f6e3642cb2de8eac1bcec926b94c86579e30",
    "audit": "b44ec99e0499b7d427ad9ffb468bb73988bfb0d94d672736569831eb997992ec",
    "private_values": "4b9f389574b4a8aafc823a7f78a139563f63c092f8eb91af76a2175b082ae5bf",
    "private_values_raw": "ac39e21906c65e4186b2174298a880bd7cd5e8b30f8f3d79c79954e69c35103e",
    "aggregate_summary": "b74dd5053fe8a81a33064500e1616de4eeaefed97192968a84ba102473c3c369",
    "executed_sql": "a98719c4b702fe9bde7aa877740ed0f6bb8305bd38d67072f8a5116bd4ed4fc3",
}
SOURCE_BYTES = {
    "private_values": 35_008_612,
    "private_values_raw": 1_187_294_280,
    "aggregate_summary": 13_527,
    "executed_sql": 9_607_756,
}
SOURCE_PRIVATE_RECORDS = 2_126_819
SOURCE_AUDIT_CHECKS = 26_403
EXPECTED_SEMANTIC_KEY_SET_SHA256 = (
    "cee42c49d4618e6c62e99dcea26c53166f21305231b3c35991d2c2534b94368a"
)

MANIFEST_FILENAME = "manifest.json"
SUMMARY_FILENAME = "aggregate-summary.json"
AUDIT_FILENAME = "audit-summary.json"
STREAM_FILES = {
    "semantic_review_template": "semantic-review-template.jsonl.gz",
    "local_evidence": "local-evidence.jsonl.gz",
    "route_review_template": "route-review-template.jsonl.gz",
    "ndc_handoff": "ndc-handoff.jsonl.gz",
}
STREAM_ARTIFACT_TYPES = {
    "semantic_review_template": "potassium_query202_semantic_review_template",
    "local_evidence": "potassium_query202_local_adjudication_evidence",
    "route_review_template": "potassium_query202_route_review_template",
    "ndc_handoff": "potassium_query202_ndc_handoff",
}
PRIVATE_ENCODING = "gzip+utf8+ndjson-v1"

MAX_STORED_BYTES = 4 * 1024 * 1024 * 1024
MAX_RAW_BYTES = 16 * 1024 * 1024 * 1024
MAX_LINE_BYTES = 8 * 1024 * 1024
MAX_JSON_BYTES = 128 * 1024 * 1024
MAX_TUPLE_JSON_BYTES = 1024 * 1024
MAX_COUNT = (1 << 63) - 1
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
UTC_RE = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,6})?Z\Z"
)

BOUNDARY_SET_VERSION = b"typed-distinct-source-value-set-v1"
SEMANTIC_SET_VERSION = b"source-field-nonnull-exact-value-set-v1"
TUPLE_ENCODING_VERSION = b"query202-pre-adjudication-exact-typed-tuple-v1"
TUPLE_SET_VERSION = b"query202-pre-adjudication-tuple-set-v1"
TUPLE_FREQUENCY_VERSION = b"query202-pre-adjudication-tuple-frequency-v1"
CANONICAL_ROUTE_SET_VERSION = b"canonical-exact-nonnull-route-value-set-v1"

SEMANTIC_DIMENSIONS = (
    "product_identity",
    "dosage_form",
    "treatment_intent",
    "potassium_content",
    "meq_convertibility",
)
FALSE_GUARDS = (
    "adjudication_input_compiled",
    "adjudication_input_audited",
    "semantic_review_complete",
    "reviewed_semantic_ledger_frozen",
    "route_review_complete",
    "route_mapping_frozen",
    "ndc_mode_frozen",
    "external_ndc_mapping_executed",
    "product_identity_decided",
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
)
EXPECTED_PRIVACY = {
    "contains_exact_raw_local_values": True,
    "contains_patient_admission_event_or_order_identifiers": False,
    "contains_event_or_order_timestamps": False,
    "external_api_called": False,
}
EXPECTED_PUBLIC_PRIVACY = {
    "private_raw_values_persisted": True,
    "public_raw_values_emitted": False,
    "patient_admission_event_or_order_identifiers_persisted": False,
    "event_or_order_timestamps_persisted": False,
    "external_api_called": False,
}

SOURCE_KEYS = (
    "emar_medication",
    "detail_product_description",
    "pharmacy_medication",
    "prescription_drug",
    "detail_product_description_other",
    "emar_detail_route",
    "pharmacy_route",
    "prescriptions_route",
    "prescriptions_ndc",
)
SOURCE_FIELDS = (
    "mimiciv_hosp.emar.medication",
    "mimiciv_hosp.emar_detail.product_description",
    "mimiciv_hosp.pharmacy.medication",
    "mimiciv_hosp.prescriptions.drug",
    "mimiciv_hosp.emar_detail.product_description_other",
    "mimiciv_hosp.emar_detail.route",
    "mimiciv_hosp.pharmacy.route",
    "mimiciv_hosp.prescriptions.route",
    "mimiciv_hosp.prescriptions.ndc",
)
BOUNDARY_STAGES = tuple(f"202a{index}" for index in range(1, 10))
SEMANTIC_SOURCE_KEYS = frozenset(SOURCE_KEYS[:5])
EXPECTED_NONNULL_COUNTS = (5_045, 6_692, 11_059, 10_927, 842, 17, 108, 108, 6_589)
EXPECTED_TYPED_HASHES = {
    "emar_detail_route": "a3b0d5664ae2e89f08df97f45347a6d7ae7761cdb2d138da781681ed2edd0ea9",
    "pharmacy_route": "2dad858bbbd41002d3a417faa302bda9bd0f85111d47cbd075a0802886ebd76b",
    "prescriptions_route": "b75209f1e0acea76a8c9818936b389a972def151317ede76073fc51dd65f1c0e",
    "prescriptions_ndc": "10e5ff7bb578ca66aadfe274105ed94a53487ba05d7b80e0ebca8fb8c24bab9e",
}
ROUTE_SOURCES = (
    (
        "emar_detail_route",
        "mimiciv_hosp.emar_detail.route",
        "direct_detail_route",
    ),
    (
        "pharmacy_route",
        "mimiciv_hosp.pharmacy.route",
        "auxiliary_pharmacy_route",
    ),
    (
        "prescriptions_route",
        "mimiciv_hosp.prescriptions.route",
        "auxiliary_prescriptions_route",
    ),
)

DETAIL_CONTEXT_FIELDS = (
    "row_role", "parent_field_ordinal", "administration_type",
    "complete_dose_not_given",
    "dose_due", "dose_due_unit", "dose_given", "dose_given_unit",
    "will_remainder_of_dose_be_given", "product_amount_given", "product_unit",
    "product_code", "product_description", "product_description_other",
    "prior_infusion_rate", "route", "infusion_rate",
    "infusion_rate_adjustment", "infusion_rate_adjustment_amount",
    "infusion_rate_unit", "infusion_complete", "completion_interval",
    "new_iv_bag_hung", "continued_infusion_in_other_location",
    "restart_interval", "non_formulary_visual_verification",
)
DETAIL_BRIDGE_FIELDS = (
    "head_medication", "detail_head_identity_state", "detail_match_state",
    "row_role", "parent_field_ordinal", "administration_type",
    "product_description", "product_description_other", "product_code", "route",
    "dose_due_unit", "dose_given_unit", "product_unit", "infusion_rate_unit",
)
PHARMACY_CONTEXT_FIELDS = (
    "medication", "proc_type", "status", "route", "frequency", "disp_sched",
    "infusion_type", "sliding_scale", "lockout_interval", "basal_rate",
    "one_hr_max", "doses_per_24_hrs", "duration", "duration_interval",
    "expiration_value", "expiration_unit", "dispensation", "fill_quantity",
)
PRESCRIPTION_CONTEXT_FIELDS = (
    "drug_type", "drug", "formulary_drug_cd", "gsn", "ndc", "prod_strength",
    "form_rx", "dose_val_rx", "dose_unit_rx", "form_val_disp",
    "form_unit_disp", "doses_per_24_hrs", "route",
)
TUPLE_FIELDS = {
    "202b": {
        "detail_product_context": DETAIL_CONTEXT_FIELDS,
        "detail_seed_membership_bridge": (
            *DETAIL_CONTEXT_FIELDS, "seed_source_field", "seed_exact_raw_value"
        ),
        "emar_medication_detail_bridge": DETAIL_BRIDGE_FIELDS,
        "emar_medication_head_partition": ("head_medication", "detail_match_state"),
    },
    "202c": {
        "pharmacy_product_context": PHARMACY_CONTEXT_FIELDS,
        "prescription_identifier_context": PRESCRIPTION_CONTEXT_FIELDS,
        "pharmacy_prescription_bridge": (
            "link_identity_state", "poe_auxiliary_state", "pharmacy_medication",
            "pharmacy_route", *PRESCRIPTION_CONTEXT_FIELDS,
        ),
        "pharmacy_no_prescription_component": (
            *PHARMACY_CONTEXT_FIELDS, "prescription_match_state"
        ),
        "head_pharmacy_prescription_bridge": (
            "link_identity_state", "poe_auxiliary_state", "head_medication",
            "pharmacy_medication", "pharmacy_route", *PRESCRIPTION_CONTEXT_FIELDS,
        ),
        "detail_pharmacy_prescription_bridge": (
            "link_identity_state", "poe_auxiliary_state", "row_role",
            "parent_field_ordinal", "product_description",
            "product_description_other", "product_code", "detail_route",
            "dose_due_unit", "dose_given_unit", "product_unit",
            "infusion_rate_unit", "pharmacy_medication", "pharmacy_route",
            *PRESCRIPTION_CONTEXT_FIELDS,
        ),
        "ndc_external_mapping_input": PRESCRIPTION_CONTEXT_FIELDS,
    },
}
LOCAL_KIND_ORDER = (
    ("202b", "detail_product_context"),
    ("202b", "detail_seed_membership_bridge"),
    ("202b", "emar_medication_detail_bridge"),
    ("202b", "emar_medication_head_partition"),
    ("202c", "pharmacy_product_context"),
    ("202c", "pharmacy_prescription_bridge"),
    ("202c", "prescription_identifier_context"),
    ("202c", "head_pharmacy_prescription_bridge"),
    ("202c", "pharmacy_no_prescription_component"),
    ("202c", "detail_pharmacy_prescription_bridge"),
)
NDC_KIND = ("202c", "ndc_external_mapping_input")
SEMANTIC_BINDINGS = {
    ("202b", "detail_product_context"): (
        ("product_description", "mimiciv_hosp.emar_detail.product_description"),
        (
            "product_description_other",
            "mimiciv_hosp.emar_detail.product_description_other",
        ),
    ),
    ("202b", "detail_seed_membership_bridge"): (
        ("product_description", "mimiciv_hosp.emar_detail.product_description"),
        (
            "product_description_other",
            "mimiciv_hosp.emar_detail.product_description_other",
        ),
    ),
    ("202b", "emar_medication_detail_bridge"): (
        ("head_medication", "mimiciv_hosp.emar.medication"),
        ("product_description", "mimiciv_hosp.emar_detail.product_description"),
        (
            "product_description_other",
            "mimiciv_hosp.emar_detail.product_description_other",
        ),
    ),
    ("202b", "emar_medication_head_partition"): (
        ("head_medication", "mimiciv_hosp.emar.medication"),
    ),
    ("202c", "detail_pharmacy_prescription_bridge"): (
        ("product_description", "mimiciv_hosp.emar_detail.product_description"),
        (
            "product_description_other",
            "mimiciv_hosp.emar_detail.product_description_other",
        ),
        ("pharmacy_medication", "mimiciv_hosp.pharmacy.medication"),
        ("drug", "mimiciv_hosp.prescriptions.drug"),
    ),
    ("202c", "head_pharmacy_prescription_bridge"): (
        ("head_medication", "mimiciv_hosp.emar.medication"),
        ("pharmacy_medication", "mimiciv_hosp.pharmacy.medication"),
        ("drug", "mimiciv_hosp.prescriptions.drug"),
    ),
    ("202c", "ndc_external_mapping_input"): (
        ("drug", "mimiciv_hosp.prescriptions.drug"),
    ),
    ("202c", "pharmacy_no_prescription_component"): (
        ("medication", "mimiciv_hosp.pharmacy.medication"),
    ),
    ("202c", "pharmacy_prescription_bridge"): (
        ("pharmacy_medication", "mimiciv_hosp.pharmacy.medication"),
        ("drug", "mimiciv_hosp.prescriptions.drug"),
    ),
    ("202c", "pharmacy_product_context"): (
        ("medication", "mimiciv_hosp.pharmacy.medication"),
    ),
    ("202c", "prescription_identifier_context"): (
        ("drug", "mimiciv_hosp.prescriptions.drug"),
    ),
}
ROUTE_BINDINGS = {
    ("202b", "detail_product_context"): (
        ("route", "mimiciv_hosp.emar_detail.route"),
    ),
    ("202b", "detail_seed_membership_bridge"): (
        ("route", "mimiciv_hosp.emar_detail.route"),
    ),
    ("202b", "emar_medication_detail_bridge"): (
        ("route", "mimiciv_hosp.emar_detail.route"),
    ),
    ("202b", "emar_medication_head_partition"): (),
    ("202c", "detail_pharmacy_prescription_bridge"): (
        ("detail_route", "mimiciv_hosp.emar_detail.route"),
        ("pharmacy_route", "mimiciv_hosp.pharmacy.route"),
        ("route", "mimiciv_hosp.prescriptions.route"),
    ),
    ("202c", "head_pharmacy_prescription_bridge"): (
        ("pharmacy_route", "mimiciv_hosp.pharmacy.route"),
        ("route", "mimiciv_hosp.prescriptions.route"),
    ),
    ("202c", "ndc_external_mapping_input"): (
        ("route", "mimiciv_hosp.prescriptions.route"),
    ),
    ("202c", "pharmacy_no_prescription_component"): (
        ("route", "mimiciv_hosp.pharmacy.route"),
    ),
    ("202c", "pharmacy_prescription_bridge"): (
        ("pharmacy_route", "mimiciv_hosp.pharmacy.route"),
        ("route", "mimiciv_hosp.prescriptions.route"),
    ),
    ("202c", "pharmacy_product_context"): (
        ("route", "mimiciv_hosp.pharmacy.route"),
    ),
    ("202c", "prescription_identifier_context"): (
        ("route", "mimiciv_hosp.prescriptions.route"),
    ),
}
NDC_BINDINGS = {
    key: (("ndc", "mimiciv_hosp.prescriptions.ndc"),)
    for key in (*LOCAL_KIND_ORDER, NDC_KIND)
    if "ndc" in TUPLE_FIELDS[key[0]][key[1]]
}

EXPECTED_SEMANTIC_KEYS = 34_565
EXPECTED_ROUTE_CANONICAL = 117
EXPECTED_ROUTE_NONNULL_MEMBERSHIPS = 233
EXPECTED_ROUTE_NULL_MEMBERSHIPS = 3
EXPECTED_ROUTE_TYPED_MEMBERSHIPS = 236
EXPECTED_LOCAL_UNIQUE = 1_861_485
EXPECTED_LOCAL_MULTIPLICITY = 392_077_967
EXPECTED_NDC_UNIQUE = 189_348
EXPECTED_NDC_MULTIPLICITY = 20_259_179
EXPECTED_NDC_CANDIDATES = 6_589
EXPECTED_NDC_NULL_BOUNDARIES = 1
EXPECTED_INPUT_UNIQUE = {"202b": 241_097, "202c": 1_809_736}
EXPECTED_INPUT_MULTIPLICITY = {"202b": 248_741_597, "202c": 163_595_549}
EXPECTED_STREAM_RECORDS = {
    "semantic_review_template": EXPECTED_SEMANTIC_KEYS + 4,
    "local_evidence": EXPECTED_LOCAL_UNIQUE + 22,
    "route_review_template": (
        EXPECTED_ROUTE_CANONICAL + EXPECTED_ROUTE_TYPED_MEMBERSHIPS + 4
    ),
    "ndc_handoff": (
        EXPECTED_NDC_CANDIDATES + EXPECTED_NDC_NULL_BOUNDARIES
        + EXPECTED_NDC_UNIQUE + 6
    ),
}

EXPECTED_COMPONENT_INPUT = {
    "artifact_directory": "artifacts/profiling/20261012T152323.460063Z",
    "component_id": SOURCE_COMPONENT_ID,
    "config_file": (
        "config/preregistrations/"
        "d005_potassium_query202_pre_adjudication_v2.toml"
    ),
    "config_sha256": SOURCE_HASHES["config"],
    "manifest_file": SOURCE_FILES["manifest"],
    "manifest_sha256": SOURCE_HASHES["manifest"],
    "audit_file": SOURCE_FILES["audit"],
    "audit_sha256": SOURCE_HASHES["audit"],
    "aggregate_summary_file": SOURCE_FILES["aggregate_summary"],
    "aggregate_summary_sha256": SOURCE_HASHES["aggregate_summary"],
    "executed_sql_file": SOURCE_FILES["executed_sql"],
    "executed_sql_sha256": SOURCE_HASHES["executed_sql"],
    "private_file": SOURCE_FILES["private_values"],
    "private_stored_sha256": SOURCE_HASHES["private_values"],
    "private_raw_sha256": SOURCE_HASHES["private_values_raw"],
    "private_stored_bytes": SOURCE_BYTES["private_values"],
    "private_raw_bytes": SOURCE_BYTES["private_values_raw"],
    "private_records": SOURCE_PRIVATE_RECORDS,
    "audit_checks_total": SOURCE_AUDIT_CHECKS,
    "audit_checks_passed": SOURCE_AUDIT_CHECKS,
    "audit_checks_failed": 0,
    "semantic_seed": {
        "records": EXPECTED_SEMANTIC_KEYS,
        "key_set_sha256": EXPECTED_SEMANTIC_KEY_SET_SHA256,
        "sql_null_keys": 0,
    },
    "crosswalk": {
        "unique_tuples": 2_050_833,
        "total_multiplicity": 412_337_146,
        "stage_202b_unique_tuples": EXPECTED_INPUT_UNIQUE["202b"],
        "stage_202b_total_multiplicity": EXPECTED_INPUT_MULTIPLICITY["202b"],
        "stage_202b_set_sha256": (
            "9875e7157f1c4d453eb97c8a0d767a759e14bc7aeb93a00007421db749839048"
        ),
        "stage_202b_frequency_sha256": (
            "b323af112e6e4d992ca714a4a04e3225daf4b941d201ee3f9d8d9a4f81cfc4f6"
        ),
        "stage_202c_unique_tuples": EXPECTED_INPUT_UNIQUE["202c"],
        "stage_202c_total_multiplicity": EXPECTED_INPUT_MULTIPLICITY["202c"],
        "stage_202c_set_sha256": (
            "b9a8a2ef7a15b8fb6fd2e82541b51cb26028859881fc379005e401bcdc0ed8ed"
        ),
        "stage_202c_frequency_sha256": (
            "a57edbba179631910f530dfddb288e1c992bd3ee940813020da9791386c7b0d0"
        ),
    },
}

EXPECTED_TUPLE_KIND_CONFIG = [
    {
        "stage": "202b",
        "name": "detail_product_context",
        "unique_tuples": 137_579,
        "total_multiplicity": 84_901_924,
        "set_sha256": "f955faa531cd72e172bacd99625dcd215cfe063e7a3bbd26f0cb7fffb34925d9",
        "frequency_sha256": "6debef0d4d367acefe6061c1619c08b5aa46596361a788781921e89a8a37dd55",
        "output_partition": "local_evidence",
    },
    {
        "stage": "202b",
        "name": "detail_seed_membership_bridge",
        "unique_tuples": 49_648,
        "total_multiplicity": 38_250_029,
        "set_sha256": "498092fe0b3e1ecc73a985d51e46728114502e38c191f95b4b2f2f1445f4233e",
        "frequency_sha256": "4228b5a06dd5bfa325bfecda2702fb67e0af007554b4e2f6712b3a51fcbce85e",
        "output_partition": "local_evidence",
    },
    {
        "stage": "202b",
        "name": "emar_medication_detail_bridge",
        "unique_tuples": 48_825,
        "total_multiplicity": 84_901_924,
        "set_sha256": "5ebcf437404b27bc4a97fff8733a62ad4433ddffc49af806c11be4b95c33d0d8",
        "frequency_sha256": "cce944d7cff62c6ccf3cdc8dd653c1b4516294cf9a6b208831d9e5c54f6e0317",
        "output_partition": "local_evidence",
    },
    {
        "stage": "202b",
        "name": "emar_medication_head_partition",
        "unique_tuples": 5_045,
        "total_multiplicity": 40_687_720,
        "set_sha256": "810050005b995e2c5545b96a8f66588c9a8af9ed190490404557b115eee43e4b",
        "frequency_sha256": "ba45eaacd8c36b947baa13d57d779eec34f5686ae5c02948ee3b188a47fdcdf6",
        "output_partition": "local_evidence",
    },
    {
        "stage": "202c",
        "name": "detail_pharmacy_prescription_bridge",
        "unique_tuples": 285_516,
        "total_multiplicity": 46_152_769,
        "set_sha256": "ae93a8ef4cc2323d446fa46d9d1906bd94ffdf72352258f421d62cf84f4a4ef9",
        "frequency_sha256": "8299a39b27ed7f277a259a17eb2d9cbbd3002b7737c6ee4d003cbb6853bb385a",
        "output_partition": "local_evidence",
    },
    {
        "stage": "202c",
        "name": "head_pharmacy_prescription_bridge",
        "unique_tuples": 172_567,
        "total_multiplicity": 38_758_346,
        "set_sha256": "3f3cf1362c235846281be8ecb237c658917a924c30f87267e5b0e4b9973583ed",
        "frequency_sha256": "1de3c43b69ec96fd90d43c5ce9c82d5af4184dc790c191b898e250f18842011f",
        "output_partition": "local_evidence",
    },
    {
        "stage": "202c",
        "name": "ndc_external_mapping_input",
        "unique_tuples": EXPECTED_NDC_UNIQUE,
        "total_multiplicity": EXPECTED_NDC_MULTIPLICITY,
        "set_sha256": "37a0f1e6854c44ac805737bfdc777e4338c12e1a681c15e595945f0d1068f121",
        "frequency_sha256": "0a9e17658c2b8db566289bef1a7729e573b3ed52f5bcfb6d05a280c1a6299c48",
        "output_partition": "ndc_handoff",
    },
    {
        "stage": "202c",
        "name": "pharmacy_no_prescription_component",
        "unique_tuples": 89,
        "total_multiplicity": 30_504,
        "set_sha256": "7c03bb9d1fab5db66641e5a840e542696d8368909c96a590daa7549c454cba6e",
        "frequency_sha256": "e59e4db772a475ec8bb53634d5935eefc3b8f2e3e4fee7b6b72d56a5e2ce1ece",
        "output_partition": "local_evidence",
    },
    {
        "stage": "202c",
        "name": "pharmacy_prescription_bridge",
        "unique_tuples": 236_630,
        "total_multiplicity": 20_292_611,
        "set_sha256": "f149d62b86ddd726f7aa313f14414d2832bdfedad6e2d049f70202f18d36ab89",
        "frequency_sha256": "b592b40eda6fadef369d8d5a970f434c7dfbe5b539dd822af358f1edf69d3c88",
        "output_partition": "local_evidence",
    },
    {
        "stage": "202c",
        "name": "pharmacy_product_context",
        "unique_tuples": 717_377,
        "total_multiplicity": 17_809_529,
        "set_sha256": "78c74457e5e5b7f33b6cadc078327b97be12145fc16636c234817283905dd3f9",
        "frequency_sha256": "1db32cd0eb0c4cf81a5bc5aa1e43b91682682d2a7a9fa6cb4dae053c6410ab33",
        "output_partition": "local_evidence",
    },
    {
        "stage": "202c",
        "name": "prescription_identifier_context",
        "unique_tuples": 208_209,
        "total_multiplicity": 20_292_611,
        "set_sha256": "6832faad82b24e1be86484c24891e73d08c901359da1ec80ce609664179f01c1",
        "frequency_sha256": "909f820e74e3524e49eae7285b41f6f89ce28298d47f03f851281f10512ef5f0",
        "output_partition": "local_evidence",
    },
]

EXPECTED_COMPONENT_OUTPUT = {
    "artifact_parent": "artifacts/query202-adjudication-input",
    "semantic_file": STREAM_FILES["semantic_review_template"],
    "local_evidence_file": STREAM_FILES["local_evidence"],
    "route_file": STREAM_FILES["route_review_template"],
    "ndc_file": STREAM_FILES["ndc_handoff"],
    "summary_file": SUMMARY_FILENAME,
    "manifest_file": MANIFEST_FILENAME,
    "audit_file": AUDIT_FILENAME,
    "encoding": PRIVATE_ENCODING,
    "gzip_members": 1,
    "gzip_mtime": 0,
    "private_ndjson_canonical_json": (
        "sort_keys=true,separators=comma-colon,ensure_ascii=false,newline=true"
    ),
    "semantic_records": EXPECTED_SEMANTIC_KEYS,
    "local_evidence_tuples": EXPECTED_LOCAL_UNIQUE,
    "local_evidence_multiplicity": EXPECTED_LOCAL_MULTIPLICITY,
    "route_canonical_nonnull_values": EXPECTED_ROUTE_CANONICAL,
    "route_nonnull_memberships": EXPECTED_ROUTE_NONNULL_MEMBERSHIPS,
    "route_sql_null_memberships": EXPECTED_ROUTE_NULL_MEMBERSHIPS,
    "route_typed_memberships": EXPECTED_ROUTE_TYPED_MEMBERSHIPS,
    "ndc_candidates": EXPECTED_NDC_CANDIDATES,
    "ndc_sql_null_boundary_records": EXPECTED_NDC_NULL_BOUNDARIES,
    "ndc_context_tuples": EXPECTED_NDC_UNIQUE,
    "ndc_context_multiplicity": EXPECTED_NDC_MULTIPLICITY,
}

EXPECTED_REVIEW_CONTRACT = {
    "semantic_dimensions": list(SEMANTIC_DIMENSIONS),
    "semantic_initial_status": "uncertain",
    "semantic_initial_review_status": "unreviewed",
    "semantic_mapping_group_initially_null": True,
    "route_allowed_decisions": ["iv", "noniv", "unknown"],
    "route_nonnull_initial_decision": "unknown",
    "route_nonnull_initial_review_status": "unreviewed",
    "route_sql_null_state": "missing",
    "route_sql_null_is_unknown": False,
    "normalization_allowed": False,
    "automatic_classification_allowed": False,
    "cooccurrence_establishes_identity": False,
}

EXPECTED_NDC_MODE = {
    "handoff_required": True,
    "mode_at_compilation": "pending",
    "allowed_frozen_modes": ["mapped_frozen", "not_used_frozen"],
    "sql_null_is_candidate": False,
    "normalization_allowed": False,
    "external_api_allowed": False,
    "external_api_called": False,
    "mapping_establishes_product_identity": False,
}

EXPECTED_EXECUTION_CONTRACT = {
    "database_access_allowed": False,
    "network_access_allowed": False,
    "external_api_allowed": False,
    "input_and_output_hashes_rechecked_before_success": True,
    "atomic_private_writes_required": True,
    "failure_keeps_private_partial_outputs": False,
}

EXPECTED_PRIVACY_CONTRACT = {
    "directory_mode": "0700",
    "file_mode": "0600",
    "git_ignored_required": True,
    "private_raw_values_allowed": True,
    "public_raw_values_allowed": False,
    "public_per_value_hashes_allowed": False,
    "patient_admission_event_order_identifiers_allowed": False,
    "event_or_order_timestamps_allowed": False,
}

TUPLE_VALUE_ENUMS = {
    ("202b", "detail_product_context", "row_role"): ("parent", "product"),
    ("202b", "detail_seed_membership_bridge", "row_role"): ("parent", "product"),
    ("202b", "detail_seed_membership_bridge", "seed_source_field"): (
        "mimiciv_hosp.emar_detail.product_description",
        "mimiciv_hosp.emar_detail.product_description_other",
    ),
    ("202b", "emar_medication_detail_bridge", "detail_head_identity_state"): (
        "missing", "conflict", "exact",
    ),
    ("202b", "emar_medication_detail_bridge", "detail_match_state"): ("with_detail",),
    ("202b", "emar_medication_detail_bridge", "row_role"): ("parent", "product"),
    ("202b", "emar_medication_head_partition", "detail_match_state"): (
        "no_detail", "with_detail_exact_only", "with_detail_identity_missing_only",
        "with_detail_identity_conflict_only", "with_detail_exact_and_identity_missing",
        "with_detail_exact_and_identity_conflict",
        "with_detail_identity_missing_and_conflict",
        "with_detail_exact_identity_missing_and_conflict",
    ),
    ("202c", "pharmacy_prescription_bridge", "link_identity_state"): (
        "pharmacy_missing", "subject_missing", "subject_conflict",
        "hadm_missing", "hadm_conflict", "exact",
    ),
    ("202c", "pharmacy_prescription_bridge", "poe_auxiliary_state"): (
        "missing", "conflict", "exact",
    ),
    ("202c", "pharmacy_no_prescription_component", "prescription_match_state"): (
        "no_prescription_component",
    ),
    ("202c", "head_pharmacy_prescription_bridge", "link_identity_state"): (
        "pharmacy_missing", "prescription_missing", "pharmacy_subject_missing",
        "pharmacy_subject_conflict", "prescription_subject_missing",
        "prescription_subject_conflict", "pharmacy_hadm_missing",
        "pharmacy_hadm_conflict", "prescription_hadm_missing",
        "prescription_hadm_conflict", "exact",
    ),
    ("202c", "head_pharmacy_prescription_bridge", "poe_auxiliary_state"): (
        "missing", "conflict", "exact",
    ),
    ("202c", "detail_pharmacy_prescription_bridge", "link_identity_state"): (
        "pharmacy_missing", "prescription_missing", "pharmacy_subject_missing",
        "pharmacy_subject_conflict", "prescription_subject_missing",
        "prescription_subject_conflict", "hadm_missing", "hadm_conflict", "exact",
    ),
    ("202c", "detail_pharmacy_prescription_bridge", "poe_auxiliary_state"): (
        "missing", "conflict", "exact",
    ),
    ("202c", "detail_pharmacy_prescription_bridge", "row_role"): ("parent", "product"),
}
ENUM_FIELDS_BY_KIND: dict[tuple[str, str], dict[str, tuple[str, ...]]] = {}
for (_stage, _kind, _field), _values in TUPLE_VALUE_ENUMS.items():
    ENUM_FIELDS_BY_KIND.setdefault((_stage, _kind), {})[_field] = _values

FORBIDDEN_TUPLE_FIELDS = {
    "subject_id", "hadm_id", "stay_id", "emar_id", "emar_seq", "pharmacy_id",
    "poe_id", "poe_seq", "order_id", "charttime", "scheduletime", "storetime",
    "entertime", "starttime", "stoptime", "endtime",
}
FORBIDDEN_PUBLIC_KEYS = FORBIDDEN_TUPLE_FIELDS | {
    "raw_value", "exact_raw_value", "tuple", "ndc", "local_code",
    "canonical_review_id", "source_memberships", "per_value_hash", "per_tuple_hash",
}


class AdjudicationInputAuditError(RuntimeError):
    """A fixed-name audit failure that never contains a private value."""


class Checks:
    def __init__(self) -> None:
        self.total = 0
        self.by_category: Counter[str] = Counter()
        self.failed: list[str] = []

    def require(self, condition: bool, name: str) -> None:
        self.total += 1
        self.by_category[name.split(".", 1)[0]] += 1
        if not condition:
            if name not in self.failed:
                self.failed.append(name)
            raise AdjudicationInputAuditError(name)

    def record_exception(self, name: str) -> None:
        if name in self.failed:
            return
        self.total += 1
        self.by_category[name.split(".", 1)[0]] += 1
        self.failed.append(name)


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _path_has_symlink(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _regular_project_file(root: Path, relative: str) -> Path | None:
    if not _safe_relative(relative):
        return None
    candidate = root / relative
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            return None
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


def _regular_project_directory(root: Path, relative: str) -> Path | None:
    if not _safe_relative(relative):
        return None
    candidate = root / relative
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            return None
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if resolved != candidate or not candidate.is_dir():
        return None
    return candidate


def _implementation_bundle_sha256(root: Path, paths: tuple[str, ...]) -> str:
    """Recompute the ordered implementation bundle without shared helpers."""
    digest = hashlib.sha256()
    for relative in paths:
        path = _regular_project_file(root, relative)
        if path is None:
            raise AdjudicationInputAuditError(
                "component.implementation_regular_file"
            )
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise AdjudicationInputAuditError(
                "component.implementation_read"
            ) from exc
        encoded_path = relative.encode("utf-8")
        digest.update(struct.pack(">I", len(encoded_path)))
        digest.update(encoded_path)
        digest.update(struct.pack(">Q", len(payload)))
        digest.update(payload)
    return digest.hexdigest()


def _load_component_lineage(
    root: Path, checks: Checks
) -> tuple[dict[str, Any], Path]:
    """Independently validate this component's frozen preregistration."""
    config_path = _regular_project_file(root, str(COMPONENT_CONFIG_PATH))
    checks.require(config_path is not None, "component.config_regular_file")
    assert config_path is not None
    try:
        payload = config_path.read_bytes()
        config = tomllib.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise AdjudicationInputAuditError("component.config_valid_toml") from exc
    checks.require(
        set(config)
        == {
            "schema_version", "component_id", "decision_id", "status",
            "execution_status", "execution_permitted", "specified_on",
            "rule_version", "scope", "input", "tuple_kind", "output",
            "review_contract", "ndc_mode", "execution", "privacy",
            "implementation", "guards",
        },
        "component.config_schema",
    )
    expected_root = {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "decision_id": "D005",
        "status": "frozen_for_execution",
        "execution_status": "not_executed",
        "execution_permitted": True,
        "specified_on": "2026-10-13",
        "rule_version": "k-query202-adjudication-input-v1-frozen",
        "scope": (
            "Offline lossless compilation of audited Query 202 A into private "
            "adjudication inputs"
        ),
    }
    for key, expected in expected_root.items():
        checks.require(
            _strict_equal(config.get(key), expected),
            "component.root_" + key,
        )
    checks.require(
        _strict_equal(config.get("input"), EXPECTED_COMPONENT_INPUT),
        "component.input_contract",
    )
    checks.require(
        _strict_equal(config.get("tuple_kind"), EXPECTED_TUPLE_KIND_CONFIG),
        "component.tuple_kind_contract",
    )
    checks.require(
        _strict_equal(config.get("output"), EXPECTED_COMPONENT_OUTPUT),
        "component.output_contract",
    )
    checks.require(
        _strict_equal(config.get("review_contract"), EXPECTED_REVIEW_CONTRACT),
        "component.review_contract",
    )
    checks.require(
        _strict_equal(config.get("ndc_mode"), EXPECTED_NDC_MODE),
        "component.ndc_mode_contract",
    )
    checks.require(
        _strict_equal(config.get("execution"), EXPECTED_EXECUTION_CONTRACT),
        "component.execution_contract",
    )
    checks.require(
        _strict_equal(config.get("privacy"), EXPECTED_PRIVACY_CONTRACT),
        "component.privacy_contract",
    )
    checks.require(
        _strict_equal(
            config.get("guards"),
            {key: False for key in FALSE_GUARDS},
        ),
        "component.guards_false",
    )

    implementation = config.get("implementation")
    checks.require(
        isinstance(implementation, dict),
        "component.implementation_table",
    )
    assert isinstance(implementation, dict)
    checks.require(
        implementation.get("bundle_encoding") == COMPONENT_BUNDLE_ENCODING,
        "component.bundle_encoding",
    )
    checks.require(
        _strict_equal(
            implementation.get("compiler_paths"),
            list(COMPILER_IMPLEMENTATION_PATHS),
        ),
        "component.compiler_paths",
    )
    checks.require(
        _strict_equal(
            implementation.get("auditor_paths"),
            list(AUDITOR_IMPLEMENTATION_PATHS),
        ),
        "component.auditor_paths",
    )
    compiler_expected = implementation.get("compiler_bundle_sha256")
    auditor_expected = implementation.get("auditor_bundle_sha256")
    checks.require(
        isinstance(compiler_expected, str)
        and SHA256_RE.fullmatch(compiler_expected) is not None,
        "component.compiler_bundle_format",
    )
    checks.require(
        isinstance(auditor_expected, str)
        and SHA256_RE.fullmatch(auditor_expected) is not None,
        "component.auditor_bundle_format",
    )
    checks.require(
        _strict_equal(
            implementation,
            {
                "bundle_encoding": COMPONENT_BUNDLE_ENCODING,
                "compiler_paths": list(COMPILER_IMPLEMENTATION_PATHS),
                "auditor_paths": list(AUDITOR_IMPLEMENTATION_PATHS),
                "compiler_bundle_sha256": compiler_expected,
                "auditor_bundle_sha256": auditor_expected,
            },
        ),
        "component.implementation_contract",
    )
    compiler_actual = _implementation_bundle_sha256(
        root, COMPILER_IMPLEMENTATION_PATHS
    )
    auditor_actual = _implementation_bundle_sha256(root, AUDITOR_IMPLEMENTATION_PATHS)
    checks.require(
        compiler_actual == compiler_expected,
        "component.compiler_bundle_hash",
    )
    checks.require(
        auditor_actual == auditor_expected,
        "component.auditor_bundle_hash",
    )
    artifact_parent = _regular_project_directory(
        root, str(config["output"]["artifact_parent"])
    )
    checks.require(artifact_parent is not None, "component.artifact_parent")
    assert artifact_parent is not None
    return (
        {
            "component_id": COMPONENT_ID,
            "config": str(COMPONENT_CONFIG_PATH),
            "config_sha256": _sha_bytes(payload),
            "status_at_execution": "frozen_for_execution",
            "compiler_bundle_sha256": compiler_actual,
            "auditor_bundle_sha256": auditor_actual,
        },
        artifact_parent,
    )


def _mode(path: Path) -> str:
    return format(stat.S_IMODE(path.stat().st_mode), "04o")


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed


def _exact_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise AdjudicationInputAuditError(label)
    return value


def _strict_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(right, dict):
        return set(left) == set(right) and all(
            _strict_equal(left[key], item) for key, item in right.items()
        )
    if isinstance(right, list):
        return len(left) == len(right) and all(
            _strict_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _exact_int(value: Any, expected: int) -> bool:
    return type(value) is int and value == expected


def _unique_json(payload: bytes, label: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AdjudicationInputAuditError(label + ".duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(_: str) -> None:
        raise AdjudicationInputAuditError(label + ".nonfinite_number")

    try:
        value = json.loads(
            payload,
            object_pairs_hook=unique,
            parse_constant=invalid_constant,
        )
    except AdjudicationInputAuditError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdjudicationInputAuditError(label + ".valid_json") from exc
    if not isinstance(value, dict):
        raise AdjudicationInputAuditError(label + ".object")
    return value


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink():
        raise AdjudicationInputAuditError(label + ".regular_file")
    size = path.stat().st_size
    if not 0 < size <= MAX_JSON_BYTES:
        raise AdjudicationInputAuditError(label + ".byte_limit")
    payload = path.read_bytes()
    return _unique_json(payload, label), payload


def _git_ignored(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    try:
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", "--", str(relative)],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _file_snapshot(path: Path, label: str) -> dict[str, Any]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise AdjudicationInputAuditError(label + ".regular_file")
        digest = hashlib.sha256()
        byte_count = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            byte_count += len(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        linked = path.lstat()
    except AdjudicationInputAuditError:
        raise
    except OSError as exc:
        raise AdjudicationInputAuditError(label + ".snapshot_read") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    stable_fields = (
        "st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns"
    )
    if any(getattr(before, key) != getattr(after, key) for key in stable_fields):
        raise AdjudicationInputAuditError(label + ".changed_while_reading")
    if (
        not stat.S_ISREG(linked.st_mode)
        or linked.st_dev != after.st_dev
        or linked.st_ino != after.st_ino
        or linked.st_size != after.st_size
        or byte_count != after.st_size
    ):
        raise AdjudicationInputAuditError(label + ".path_changed")
    return {
        "bytes": byte_count,
        "sha256": digest.hexdigest(),
        "mode": format(stat.S_IMODE(after.st_mode), "04o"),
        "device": after.st_dev,
        "inode": after.st_ino,
    }


def _recheck_directory_snapshot(
    directory: Path,
    expected: Mapping[str, Mapping[str, Any]],
    label: str,
    checks: Checks | None,
    allowed_extra: set[str] | None = None,
) -> None:
    expected_names = set(expected) | (allowed_extra or set())

    def require(condition: bool, name: str) -> None:
        if checks is not None:
            checks.require(condition, name)
        elif not condition:
            raise AdjudicationInputAuditError(name)

    try:
        before = directory.lstat()
        entries = list(directory.iterdir())
    except OSError as exc:
        raise AdjudicationInputAuditError(label + ".directory_read") from exc
    require(
        stat.S_ISDIR(before.st_mode) and not directory.is_symlink(),
        label + ".directory",
    )
    require(
        format(stat.S_IMODE(before.st_mode), "04o") == "0700",
        label + ".directory_mode",
    )
    require(
        {entry.name for entry in entries} == expected_names,
        label + ".inventory",
    )
    for filename, expected_file in expected.items():
        actual = _file_snapshot(directory / filename, label + ".file")
        require(actual["mode"] == "0600", label + ".file_mode")
        require(
            actual["bytes"] == expected_file["bytes"],
            label + ".file_bytes",
        )
        require(
            actual["sha256"] == expected_file["sha256"],
            label + ".file_hash",
        )
    try:
        after = directory.lstat()
        final_names = {entry.name for entry in directory.iterdir()}
    except OSError as exc:
        raise AdjudicationInputAuditError(label + ".directory_reread") from exc
    require(
        before.st_dev == after.st_dev
        and before.st_ino == after.st_ino
        and before.st_mode == after.st_mode
        and before.st_mtime_ns == after.st_mtime_ns,
        label + ".directory_stable",
    )
    require(final_names == expected_names, label + ".inventory_recheck")


def _recheck_file_snapshot(
    path: Path,
    expected: Mapping[str, Any],
    label: str,
    checks: Checks | None,
) -> None:
    actual = _file_snapshot(path, label)

    def require(condition: bool, name: str) -> None:
        if checks is not None:
            checks.require(condition, name)
        elif not condition:
            raise AdjudicationInputAuditError(name)

    require(actual["mode"] == expected["mode"], label + ".mode")
    require(actual["bytes"] == expected["bytes"], label + ".bytes")
    require(actual["sha256"] == expected["sha256"], label + ".hash")


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_private_atomic(
    path: Path,
    payload: bytes,
    expected_directory_entries: set[str],
    publication_guard: Callable[[set[str]], None],
) -> dict[str, Any]:
    """Publish one complete private file atomically without overwriting a peer."""
    if path.exists() or path.is_symlink():
        raise AdjudicationInputAuditError("audit.output_already_exists")
    descriptor: int | None = None
    temporary_path: Path | None = None
    published_identity: tuple[int, int] | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".audit-summary-",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary = _file_snapshot(temporary_path, "audit.temporary")
        if (
            temporary["mode"] != "0600"
            or temporary["bytes"] != len(payload)
            or temporary["sha256"] != _sha_bytes(payload)
        ):
            raise AdjudicationInputAuditError("audit.temporary_content")
        published_identity = (temporary["device"], temporary["inode"])
        publication_guard({temporary_path.name})
        if path.exists() or path.is_symlink():
            raise AdjudicationInputAuditError("audit.output_already_exists")
        try:
            os.link(temporary_path, path, follow_symlinks=False)
        except FileExistsError as exc:
            raise AdjudicationInputAuditError(
                "audit.output_already_exists"
            ) from exc
        temporary_path.unlink()
        temporary_path = None
        _fsync_directory(path.parent)
        final = _file_snapshot(path, "audit.final")
        if (
            final["mode"] != "0600"
            or final["bytes"] != len(payload)
            or final["sha256"] != _sha_bytes(payload)
            or (final["device"], final["inode"]) != published_identity
        ):
            raise AdjudicationInputAuditError("audit.final_content")
        if (
            format(stat.S_IMODE(path.parent.lstat().st_mode), "04o") != "0700"
            or {item.name for item in path.parent.iterdir()}
            != expected_directory_entries
        ):
            raise AdjudicationInputAuditError("audit.final_inventory")
        publication_guard({path.name})
        return {"bytes": final["bytes"], "sha256": final["sha256"]}
    except BaseException as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        cleanup_failed = False
        cleanup_candidates = [path]
        if temporary_path is not None:
            cleanup_candidates.append(temporary_path)
        for cleanup_path in cleanup_candidates:
            try:
                current = cleanup_path.lstat()
                if (
                    cleanup_path == temporary_path
                    and published_identity is None
                ) or published_identity == (current.st_dev, current.st_ino):
                    cleanup_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                cleanup_failed = True
        try:
            _fsync_directory(path.parent)
        except OSError:
            cleanup_failed = True
        if cleanup_failed:
            raise AdjudicationInputAuditError("audit.atomic_cleanup") from exc
        if isinstance(exc, AdjudicationInputAuditError):
            raise
        raise AdjudicationInputAuditError("audit.atomic_write") from exc


class _GzipNdjsonReader:
    """Bounded single-member gzip+NDJSON reader with duplicate-key checks."""

    _INPUT_CHUNK = 256 * 1024
    _OUTPUT_CHUNK = 1024 * 1024

    def __init__(self, path: Path, label: str):
        if not path.is_file() or path.is_symlink():
            raise AdjudicationInputAuditError(label + ".regular_file")
        if not 0 < path.stat().st_size <= MAX_STORED_BYTES:
            raise AdjudicationInputAuditError(label + ".stored_byte_limit")
        self.path = path
        self.label = label
        self.stored_bytes = 0
        self.raw_bytes = 0
        self.records = 0
        self.stored_sha256 = hashlib.sha256()
        self.raw_sha256 = hashlib.sha256()
        self._finished = False

    def __iter__(self) -> Iterator[dict[str, Any]]:
        if self._finished:
            raise AdjudicationInputAuditError(self.label + ".reader_reused")
        self._finished = True
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        line_buffer = bytearray()

        def feed(raw: bytes) -> Iterator[dict[str, Any]]:
            if not raw:
                return
            self.raw_bytes += len(raw)
            if self.raw_bytes > MAX_RAW_BYTES:
                raise AdjudicationInputAuditError(self.label + ".raw_byte_limit")
            self.raw_sha256.update(raw)
            line_buffer.extend(raw)
            while True:
                newline = line_buffer.find(b"\n")
                if newline < 0:
                    if len(line_buffer) > MAX_LINE_BYTES:
                        raise AdjudicationInputAuditError(self.label + ".line_byte_limit")
                    break
                if newline == 0 or newline > MAX_LINE_BYTES:
                    raise AdjudicationInputAuditError(self.label + ".line_byte_limit")
                line = bytes(line_buffer[:newline])
                del line_buffer[: newline + 1]
                self.records += 1
                record = _unique_json(line, self.label + ".record")
                try:
                    canonical = json.dumps(
                        record,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ).encode("utf-8")
                except (TypeError, ValueError, UnicodeEncodeError) as exc:
                    raise AdjudicationInputAuditError(
                        self.label + ".canonical_json"
                    ) from exc
                if line != canonical:
                    raise AdjudicationInputAuditError(
                        self.label + ".canonical_json"
                    )
                yield record

        with self.path.open("rb") as handle:
            compressed = handle.read(self._INPUT_CHUNK)
            if len(compressed) < 10 or compressed[:3] != b"\x1f\x8b\x08":
                raise AdjudicationInputAuditError(self.label + ".gzip_header")
            if compressed[4:8] != b"\x00\x00\x00\x00":
                raise AdjudicationInputAuditError(self.label + ".gzip_mtime")
            while compressed:
                self.stored_bytes += len(compressed)
                if self.stored_bytes > MAX_STORED_BYTES:
                    raise AdjudicationInputAuditError(
                        self.label + ".stored_byte_limit"
                    )
                self.stored_sha256.update(compressed)
                pending = compressed
                while pending:
                    output = decompressor.decompress(pending, self._OUTPUT_CHUNK)
                    pending = decompressor.unconsumed_tail
                    yield from feed(output)
                    if decompressor.unused_data:
                        raise AdjudicationInputAuditError(
                            self.label + ".multiple_members_or_trailing_data"
                        )
                    if decompressor.eof:
                        if pending:
                            raise AdjudicationInputAuditError(
                                self.label + ".multiple_members_or_trailing_data"
                            )
                        # Any later physical byte is also trailing data.
                        extra = handle.read(1)
                        if extra:
                            self.stored_bytes += 1
                            self.stored_sha256.update(extra)
                            raise AdjudicationInputAuditError(
                                self.label + ".multiple_members_or_trailing_data"
                            )
                        break
                if decompressor.eof:
                    break
                compressed = handle.read(self._INPUT_CHUNK)
        if not decompressor.eof:
            raise AdjudicationInputAuditError(self.label + ".truncated_gzip")
        flushed = decompressor.flush()
        yield from feed(flushed)
        if line_buffer:
            raise AdjudicationInputAuditError(self.label + ".missing_final_newline")


class _Cursor:
    def __init__(self, reader: _GzipNdjsonReader):
        self.reader = reader
        self.iterator = iter(reader)

    def take(self, record_type: str, label: str) -> dict[str, Any]:
        try:
            record = next(self.iterator)
        except StopIteration as exc:
            raise AdjudicationInputAuditError(label + ".truncated") from exc
        if record.get("record_type") != record_type:
            raise AdjudicationInputAuditError(label + ".record_order")
        return record

    def finish(self, label: str) -> None:
        try:
            next(self.iterator)
        except StopIteration:
            return
        raise AdjudicationInputAuditError(label + ".records_after_footer")


def _semantic_seed_hash(keys: list[tuple[bytes, bytes]]) -> str:
    ordered = sorted(keys)
    if len(ordered) != len(set(ordered)):
        raise AdjudicationInputAuditError("seed.duplicate_key")
    digest = hashlib.sha256(SEMANTIC_SET_VERSION)
    digest.update(struct.pack(">Q", len(ordered)))
    for field, raw in ordered:
        digest.update(struct.pack(">I", len(field)))
        digest.update(field)
        digest.update(struct.pack(">Q", len(raw)))
        digest.update(raw)
    return digest.hexdigest()


def _typed_boundary_hash(
    source_field: str, records: list[dict[str, Any]]
) -> str:
    field = source_field.encode("utf-8")
    digest = hashlib.sha256(BOUNDARY_SET_VERSION)
    digest.update(struct.pack(">I", len(field)))
    digest.update(field)
    digest.update(struct.pack(">Q", len(records)))
    for record in records:
        if record["raw_is_null"]:
            digest.update(b"\x00")
        else:
            raw = record["raw_value"].encode("utf-8")
            digest.update(b"\x01")
            digest.update(struct.pack(">Q", len(raw)))
            digest.update(raw)
    return digest.hexdigest()


def _canonical_route_hash(values: list[str]) -> str:
    encoded = sorted(value.encode("utf-8") for value in values)
    if len(encoded) != len(set(encoded)):
        raise AdjudicationInputAuditError("route.duplicate_canonical_value")
    digest = hashlib.sha256(CANONICAL_ROUTE_SET_VERSION)
    digest.update(struct.pack(">Q", len(encoded)))
    for raw in encoded:
        digest.update(struct.pack(">Q", len(raw)))
        digest.update(raw)
    return digest.hexdigest()


def _encode_tuple(stage: str, kind: str, value: Mapping[str, str | None]) -> bytes:
    output = bytearray(TUPLE_ENCODING_VERSION)
    for label in (stage, kind):
        encoded = label.encode("utf-8")
        output.extend(struct.pack(">I", len(encoded)))
        output.extend(encoded)
    items = sorted(value.items(), key=lambda item: item[0].encode("utf-8"))
    output.extend(struct.pack(">I", len(items)))
    for field, raw in items:
        field_bytes = field.encode("utf-8")
        output.extend(struct.pack(">I", len(field_bytes)))
        output.extend(field_bytes)
        output.extend(struct.pack(">H", 4))
        output.extend(b"text")
        if raw is None:
            output.extend(b"\x00")
        else:
            raw_bytes = raw.encode("utf-8")
            output.extend(b"\x01")
            output.extend(struct.pack(">Q", len(raw_bytes)))
            output.extend(raw_bytes)
    return bytes(output)


def _new_tuple_hashers(stage_and_kind: str, count: int) -> tuple[Any, Any]:
    label = stage_and_kind.encode("utf-8")
    set_digest = hashlib.sha256(TUPLE_SET_VERSION)
    frequency_digest = hashlib.sha256(TUPLE_FREQUENCY_VERSION)
    for digest in (set_digest, frequency_digest):
        digest.update(struct.pack(">I", len(label)))
        digest.update(label)
        digest.update(struct.pack(">Q", count))
    return set_digest, frequency_digest


def _update_tuple_hashers(
    hashers: tuple[Any, Any], encoded: bytes, multiplicity: int
) -> None:
    set_digest, frequency_digest = hashers
    for digest in (set_digest, frequency_digest):
        digest.update(struct.pack(">Q", len(encoded)))
        digest.update(encoded)
    frequency_digest.update(struct.pack(">Q", multiplicity))


def _validate_tuple(
    stage: str,
    kind: str,
    value: Any,
    multiplicity: Any,
    label: str,
) -> bytes:
    expected_fields = TUPLE_FIELDS.get(stage, {}).get(kind)
    if (
        expected_fields is None
        or not isinstance(value, dict)
        or set(value) != set(expected_fields)
        or set(value) & FORBIDDEN_TUPLE_FIELDS
        or not all(item is None or isinstance(item, str) for item in value.values())
    ):
        raise AdjudicationInputAuditError(label + ".tuple_schema")
    for field, raw in value.items():
        if isinstance(raw, str):
            encoded = raw.encode("utf-8")
            if b"\x00" in encoded:
                raise AdjudicationInputAuditError(label + ".tuple_text")
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if len(canonical) > MAX_TUPLE_JSON_BYTES:
        raise AdjudicationInputAuditError(label + ".tuple_byte_limit")
    enums = ENUM_FIELDS_BY_KIND.get((stage, kind), {})
    if any(value.get(field) not in allowed for field, allowed in enums.items()):
        raise AdjudicationInputAuditError(label + ".tuple_enum")
    if kind == "ndc_external_mapping_input" and not isinstance(value.get("ndc"), str):
        raise AdjudicationInputAuditError(label + ".nonnull_ndc")
    if type(multiplicity) is not int or not 1 <= multiplicity <= MAX_COUNT:
        raise AdjudicationInputAuditError(label + ".multiplicity")
    return _encode_tuple(stage, kind, value)


def _validate_tuple_bindings(
    stage: str,
    kind: str,
    value: Mapping[str, str | None],
    source: Mapping[str, Any],
    label: str,
    checks: Checks,
) -> None:
    binding_key = (stage, kind)
    semantic_keys = source["semantic_seed_set"]
    boundary_sets = source["boundary_sets"]
    for payload_field, source_field in SEMANTIC_BINDINGS[binding_key]:
        raw = value[payload_field]
        checks.require(
            raw is None or (source_field, raw) in semantic_keys,
            label + ".semantic_binding",
        )
    for payload_field, source_field in ROUTE_BINDINGS[binding_key]:
        checks.require(
            value[payload_field] in boundary_sets[source_field],
            label + ".route_binding",
        )
    for payload_field, source_field in NDC_BINDINGS.get(binding_key, ()):
        checks.require(
            value[payload_field] in boundary_sets[source_field],
            label + ".ndc_binding",
        )
    if binding_key == ("202b", "detail_seed_membership_bridge"):
        source_field = value["seed_source_field"]
        raw = value["seed_exact_raw_value"]
        expected_field = {
            "mimiciv_hosp.emar_detail.product_description": (
                "product_description"
            ),
            "mimiciv_hosp.emar_detail.product_description_other": (
                "product_description_other"
            ),
        }.get(source_field)
        checks.require(
            expected_field is not None
            and isinstance(raw, str)
            and value[expected_field] == raw
            and (source_field, raw) in semantic_keys,
            label + ".detail_seed_binding",
        )


def _expected_input_lineage() -> dict[str, Any]:
    return {
        "component_id": SOURCE_COMPONENT_ID,
        "config_sha256": SOURCE_HASHES["config"],
        "manifest_sha256": SOURCE_HASHES["manifest"],
        "audit_sha256": SOURCE_HASHES["audit"],
        "private_values_sha256": SOURCE_HASHES["private_values"],
        "private_values_raw_sha256": SOURCE_HASHES["private_values_raw"],
        "aggregate_summary_sha256": SOURCE_HASHES["aggregate_summary"],
        "executed_sql_sha256": SOURCE_HASHES["executed_sql"],
        "semantic_seed_key_set_sha256": EXPECTED_SEMANTIC_KEY_SET_SHA256,
    }


def _validate_header(
    cursor: _Cursor,
    stream_name: str,
    created_at_utc: str,
    component_lineage: Mapping[str, Any],
    checks: Checks,
) -> dict[str, Any]:
    header = _exact_keys(
        cursor.take("header", f"{stream_name}.header"),
        {
            "record_type", "schema_version", "artifact_type", "artifact_encoding",
            "created_at_utc", "component_id", "component_lineage",
            "input_lineage", "privacy", "guards",
        },
        f"{stream_name}.header_schema",
    )
    checks.require(
        _exact_int(header["schema_version"], 1),
        f"{stream_name}.schema_version",
    )
    checks.require(
        header["artifact_type"] == STREAM_ARTIFACT_TYPES[stream_name],
        f"{stream_name}.artifact_type",
    )
    checks.require(
        header["artifact_encoding"] == PRIVATE_ENCODING,
        f"{stream_name}.encoding",
    )
    checks.require(header["component_id"] == COMPONENT_ID, f"{stream_name}.component")
    checks.require(
        _strict_equal(header["component_lineage"], component_lineage),
        f"{stream_name}.component_lineage",
    )
    checks.require(
        header["created_at_utc"] == created_at_utc
        and _parse_utc(header["created_at_utc"]) is not None,
        f"{stream_name}.created_at",
    )
    checks.require(
        _strict_equal(header["input_lineage"], _expected_input_lineage()),
        f"{stream_name}.lineage",
    )
    checks.require(
        _strict_equal(header["privacy"], EXPECTED_PRIVACY),
        f"{stream_name}.privacy",
    )
    checks.require(
        _strict_equal(header["guards"], {key: False for key in FALSE_GUARDS}),
        f"{stream_name}.guards",
    )
    return header


def _load_source_documents(
    root: Path, checks: Checks
) -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], Path,
    dict[str, dict[str, Any]], dict[str, Any],
]:
    source_value = Path(SOURCE_ARTIFACT_DIRECTORY)
    if source_value.is_absolute():
        source_directory = Path(os.path.abspath(source_value))
        if (
            not source_directory.is_relative_to(root)
            or _path_has_symlink(root, source_directory)
            or not source_directory.is_dir()
        ):
            source_directory = None
    else:
        source_directory = _regular_project_directory(root, str(source_value))
    checks.require(source_directory is not None, "source.path_within_root")
    assert source_directory is not None
    checks.require(
        source_directory.is_dir() and not source_directory.is_symlink(),
        "source.directory",
    )
    checks.require(_mode(source_directory) == "0700", "source.directory_mode")
    checks.require(_git_ignored(root, source_directory), "source.git_ignored")
    documents: dict[str, Any] = {}
    source_snapshot: dict[str, dict[str, Any]] = {}
    for role in ("manifest", "audit", "aggregate_summary"):
        path = source_directory / SOURCE_FILES[role]
        document, payload = _read_json(path, "source." + role)
        checks.require(_mode(path) == "0600", f"source.{role}_mode")
        checks.require(
            _sha_bytes(payload) == SOURCE_HASHES[role],
            f"source.{role}_hash",
        )
        documents[role] = document
        source_snapshot[path.name] = {
            "bytes": len(payload),
            "sha256": SOURCE_HASHES[role],
        }
    checks.require(
        len((source_directory / SOURCE_FILES["aggregate_summary"]).read_bytes())
        == SOURCE_BYTES["aggregate_summary"],
        "source.aggregate_summary_bytes",
    )
    sql_path = source_directory / SOURCE_FILES["executed_sql"]
    checks.require(sql_path.is_file() and not sql_path.is_symlink(), "source.sql_file")
    checks.require(_mode(sql_path) == "0600", "source.sql_mode")
    checks.require(
        sql_path.stat().st_size == SOURCE_BYTES["executed_sql"],
        "source.sql_bytes",
    )
    checks.require(_sha_file(sql_path) == SOURCE_HASHES["executed_sql"], "source.sql_hash")
    source_snapshot[sql_path.name] = {
        "bytes": SOURCE_BYTES["executed_sql"],
        "sha256": SOURCE_HASHES["executed_sql"],
    }
    private_path = source_directory / SOURCE_FILES["private_values"]
    checks.require(private_path.is_file() and not private_path.is_symlink(), "source.private_file")
    checks.require(_mode(private_path) == "0600", "source.private_mode")
    checks.require(
        private_path.stat().st_size == SOURCE_BYTES["private_values"],
        "source.private_bytes",
    )
    checks.require(_sha_file(private_path) == SOURCE_HASHES["private_values"], "source.private_hash")
    source_snapshot[private_path.name] = {
        "bytes": SOURCE_BYTES["private_values"],
        "sha256": SOURCE_HASHES["private_values"],
    }

    manifest = documents["manifest"]
    audit = documents["audit"]
    summary = documents["aggregate_summary"]
    checks.require(manifest.get("status") == "complete", "source.manifest_complete")
    queries = manifest.get("queries")
    checks.require(
        isinstance(queries, list)
        and len(queries) == 1
        and isinstance(queries[0], dict),
        "source.one_query",
    )
    query = queries[0]
    preregistration = manifest.get("component_preregistration")
    checks.require(
        isinstance(preregistration, dict)
        and preregistration.get("component_id") == SOURCE_COMPONENT_ID
        and preregistration.get("config_sha256") == SOURCE_HASHES["config"],
        "source.preregistration_lineage",
    )
    config_name = preregistration.get("config")
    checks.require(
        config_name == EXPECTED_COMPONENT_INPUT["config_file"],
        "source.config_name",
    )
    config_relative = Path(config_name)
    checks.require(
        not config_relative.is_absolute() and ".." not in config_relative.parts,
        "source.config_path",
    )
    config_path = _regular_project_file(root, str(config_relative))
    checks.require(
        config_path is not None
        and _sha_file(config_path) == SOURCE_HASHES["config"],
        "source.config_hash",
    )
    assert config_path is not None
    source_config_snapshot = _file_snapshot(config_path, "source.config")
    checks.require(
        source_config_snapshot["sha256"] == SOURCE_HASHES["config"],
        "source.config_snapshot_hash",
    )
    checks.require(
        isinstance(query, dict)
        and query.get("status") == "complete"
        and query.get("query") == "potassium_query202_pre_adjudication"
        and query.get("private_values_sha256") == SOURCE_HASHES["private_values"]
        and query.get("private_values_raw_sha256") == SOURCE_HASHES["private_values_raw"]
        and _exact_int(
            query.get("private_values_bytes"), SOURCE_BYTES["private_values"]
        )
        and _exact_int(
            query.get("private_values_raw_bytes"),
            SOURCE_BYTES["private_values_raw"],
        )
        and _exact_int(query.get("private_values_records"), SOURCE_PRIVATE_RECORDS),
        "source.manifest_private_contract",
    )
    checks.require(
        query.get("aggregate_summary_file") == SOURCE_FILES["aggregate_summary"]
        and query.get("aggregate_summary_persisted") is True
        and query.get("aggregate_summary_sha256")
        == SOURCE_HASHES["aggregate_summary"]
        and _exact_int(
            query.get("aggregate_summary_bytes"),
            SOURCE_BYTES["aggregate_summary"],
        ),
        "source.manifest_aggregate_contract",
    )
    checks.require(
        query.get("executed_sql_file") == SOURCE_FILES["executed_sql"]
        and query.get("executed_sql_persisted") is True
        and query.get("executed_sql_sha256") == SOURCE_HASHES["executed_sql"]
        and _exact_int(
            query.get("executed_sql_bytes"), SOURCE_BYTES["executed_sql"]
        ),
        "source.manifest_sql_contract",
    )
    audit_checks = audit.get("checks")
    checks.require(
        audit.get("status") == "passed"
        and isinstance(audit_checks, dict)
        and _exact_int(audit_checks.get("total"), SOURCE_AUDIT_CHECKS)
        and _exact_int(audit_checks.get("failed"), 0)
        and _strict_equal(audit_checks.get("failed_names"), []),
        "source.audit_passed",
    )
    checks.require(
        audit.get("database_connection_opened") is False
        and audit.get("patient_or_event_identifiers_emitted") is False
        and audit.get("raw_values_emitted") is False,
        "source.audit_privacy",
    )
    seed_summary = summary.get("semantic_seed_summary")
    checks.require(
        isinstance(seed_summary, dict)
        and _exact_int(
            seed_summary.get("key_count"), EXPECTED_SEMANTIC_KEYS
        )
        and seed_summary.get("key_set_sha256") == EXPECTED_SEMANTIC_KEY_SET_SHA256,
        "source.summary_seed",
    )
    return (
        manifest,
        audit,
        summary,
        private_path,
        source_snapshot,
        {
            "path": config_path,
            "bytes": source_config_snapshot["bytes"],
            "sha256": source_config_snapshot["sha256"],
            "mode": source_config_snapshot["mode"],
        },
    )


def _stream_source_private(
    path: Path, summary: Mapping[str, Any], checks: Checks
) -> dict[str, Any]:
    """Read the pinned A stream and recover exact review universes."""
    reader = _GzipNdjsonReader(path, "source.private")
    cursor = _Cursor(reader)
    header = cursor.take("header", "source.header")
    checks.require(
        _exact_int(header.get("schema_version"), 2)
        and header.get("artifact_encoding") == PRIVATE_ENCODING
        and header.get("query") == "potassium_query202_pre_adjudication",
        "source.header_contract",
    )

    boundaries: dict[str, dict[str, Any]] = {}
    boundary_values = 0
    seed_from_boundaries: list[tuple[bytes, bytes]] = []
    for index, (source_key, source_field, stage) in enumerate(
        zip(SOURCE_KEYS, SOURCE_FIELDS, BOUNDARY_STAGES, strict=True)
    ):
        begin = _exact_keys(
            cursor.take("boundary_begin", f"source.boundary_{index}_begin"),
            {"record_type", "source_key", "metadata"},
            f"source.boundary_{index}_begin_schema",
        )
        checks.require(begin["source_key"] == source_key, f"source.boundary_{index}_order")
        metadata = _exact_keys(
            begin["metadata"],
            {
                "stage", "source_field", "semantic_seed_field", "sql_null_rows",
                "typed_distinct_values", "nonnull_distinct_values", "source_rows",
                "nonnull_set_sha256", "typed_set_sha256",
            },
            f"source.boundary_{index}_metadata_schema",
        )
        checks.require(
            metadata["stage"] == stage
            and metadata["source_field"] == source_field
            and metadata["semantic_seed_field"] is (source_key in SEMANTIC_SOURCE_KEYS),
            f"source.boundary_{index}_identity",
        )
        typed_count = metadata["typed_distinct_values"]
        checks.require(
            type(typed_count) is int and 0 < typed_count <= 1_000_001,
            f"source.boundary_{index}_count",
        )
        records: list[dict[str, Any]] = []
        previous: tuple[bool, bytes] | None = None
        total_rows = 0
        null_rows = 0
        for _ in range(typed_count):
            wrapper = _exact_keys(
                cursor.take("boundary_value", f"source.boundary_{index}_value"),
                {"record_type", "source_key", "value"},
                f"source.boundary_{index}_value_schema",
            )
            checks.require(wrapper["source_key"] == source_key, f"source.boundary_{index}_value_source")
            value = _exact_keys(
                wrapper["value"],
                {"raw_is_null", "raw_value", "raw_utf8_bytes", "exact_row_count"},
                f"source.boundary_{index}_typed_schema",
            )
            count = value["exact_row_count"]
            checks.require(
                type(count) is int and 1 <= count <= MAX_COUNT,
                f"source.boundary_{index}_frequency",
            )
            is_null = value["raw_is_null"]
            raw = value["raw_value"]
            raw_bytes_count = value["raw_utf8_bytes"]
            if is_null is True:
                checks.require(
                    raw is None and _exact_int(raw_bytes_count, 0),
                    f"source.boundary_{index}_null",
                )
                order = (False, b"")
                null_rows += count
            elif is_null is False and isinstance(raw, str):
                raw_bytes = raw.encode("utf-8")
                checks.require(
                    b"\x00" not in raw_bytes
                    and _exact_int(raw_bytes_count, len(raw_bytes)),
                    f"source.boundary_{index}_text",
                )
                order = (True, raw_bytes)
                if source_key in SEMANTIC_SOURCE_KEYS:
                    seed_from_boundaries.append((source_field.encode("utf-8"), raw_bytes))
            else:
                raise AdjudicationInputAuditError(f"source.boundary_{index}_typed_state")
            checks.require(
                previous is None or order > previous,
                f"source.boundary_{index}_sort",
            )
            previous = order
            checks.require(total_rows <= MAX_COUNT - count, f"source.boundary_{index}_row_limit")
            total_rows += count
            records.append(dict(value))
            boundary_values += 1
        end = _exact_keys(
            cursor.take("boundary_end", f"source.boundary_{index}_end"),
            {"record_type", "records", "source_key"},
            f"source.boundary_{index}_end_schema",
        )
        checks.require(
            end["source_key"] == source_key
            and _exact_int(end["records"], typed_count),
            f"source.boundary_{index}_end_count",
        )
        nonnull_count = sum(not record["raw_is_null"] for record in records)
        typed_hash = _typed_boundary_hash(source_field, records)
        checks.require(
            nonnull_count == EXPECTED_NONNULL_COUNTS[index],
            f"source.boundary_{index}_nonnull_count",
        )
        checks.require(
            _exact_int(metadata["nonnull_distinct_values"], nonnull_count)
            and _exact_int(metadata["sql_null_rows"], null_rows)
            and _exact_int(metadata["source_rows"], total_rows)
            and metadata["typed_set_sha256"] == typed_hash,
            f"source.boundary_{index}_conservation",
        )
        if source_key in EXPECTED_TYPED_HASHES:
            checks.require(
                typed_hash == EXPECTED_TYPED_HASHES[source_key],
                f"source.boundary_{index}_typed_hash",
            )
        boundaries[source_key] = {
            "source_field": source_field,
            "metadata": dict(metadata),
            "records": records,
        }

    seed_from_boundaries.sort()
    checks.require(
        len(seed_from_boundaries) == EXPECTED_SEMANTIC_KEYS
        and _semantic_seed_hash(seed_from_boundaries)
        == EXPECTED_SEMANTIC_KEY_SET_SHA256,
        "source.seed_from_boundaries",
    )
    seed_begin = _exact_keys(
        cursor.take("semantic_seed_begin", "source.seed_begin"),
        {
            "record_type", "key_count", "key_set_sha256",
            "sql_null_keys_included", "review_decisions_included",
        },
        "source.seed_begin_schema",
    )
    checks.require(
        _strict_equal(seed_begin, {
            "record_type": "semantic_seed_begin",
            "key_count": EXPECTED_SEMANTIC_KEYS,
            "key_set_sha256": EXPECTED_SEMANTIC_KEY_SET_SHA256,
            "sql_null_keys_included": False,
            "review_decisions_included": False,
        }),
        "source.seed_begin_contract",
    )
    observed_seed: list[tuple[bytes, bytes]] = []
    for expected in seed_from_boundaries:
        record = _exact_keys(
            cursor.take("semantic_seed_value", "source.seed_value"),
            {"record_type", "source_field", "exact_raw_value"},
            "source.seed_value_schema",
        )
        if not isinstance(record["source_field"], str) or not isinstance(record["exact_raw_value"], str):
            raise AdjudicationInputAuditError("source.seed_value_type")
        observed = (
            record["source_field"].encode("utf-8"),
            record["exact_raw_value"].encode("utf-8"),
        )
        checks.require(observed == expected, "source.seed_value_match")
        observed_seed.append(observed)
    seed_end = _exact_keys(
        cursor.take("semantic_seed_end", "source.seed_end"),
        {"record_type", "records"},
        "source.seed_end_schema",
    )
    checks.require(
        _exact_int(seed_end["records"], EXPECTED_SEMANTIC_KEYS),
        "source.seed_end_count",
    )

    source_crosswalk_records = 0
    for stage in ("202b", "202c"):
        begin = cursor.take("crosswalk_begin", f"source.{stage}_begin")
        checks.require(begin.get("stage") == stage, f"source.{stage}_order")
        metadata = begin.get("metadata")
        checks.require(isinstance(metadata, dict), f"source.{stage}_metadata")
        unique = metadata.get("unique_tuples")
        total = metadata.get("global_output_multiplicity")
        checks.require(
            _exact_int(unique, EXPECTED_INPUT_UNIQUE[stage])
            and _exact_int(total, EXPECTED_INPUT_MULTIPLICITY[stage]),
            f"source.{stage}_totals",
        )
        for _ in range(unique):
            record = cursor.take("crosswalk_tuple", f"source.{stage}_tuple")
            checks.require(record.get("stage") == stage, f"source.{stage}_tuple_stage")
            source_crosswalk_records += 1
        end = cursor.take("crosswalk_end", f"source.{stage}_end")
        checks.require(
            end.get("stage") == stage
            and _exact_int(end.get("records"), unique),
            f"source.{stage}_end_count",
        )
    footer = _exact_keys(
        cursor.take("footer", "source.footer"),
        {"record_type", "records_before_footer", "section_records"},
        "source.footer_schema",
    )
    checks.require(
        _strict_equal(footer["section_records"], {
            "boundary_values": boundary_values,
            "semantic_seed_values": EXPECTED_SEMANTIC_KEYS,
            "crosswalk_tuples": source_crosswalk_records,
        }),
        "source.footer_sections",
    )
    cursor.finish("source.private")
    checks.require(reader.records == SOURCE_PRIVATE_RECORDS, "source.private_record_count")
    checks.require(
        reader.stored_bytes == SOURCE_BYTES["private_values"],
        "source.private_stored_bytes",
    )
    checks.require(
        reader.raw_bytes == SOURCE_BYTES["private_values_raw"],
        "source.private_raw_bytes",
    )
    checks.require(reader.stored_sha256.hexdigest() == SOURCE_HASHES["private_values"], "source.private_stored_hash")
    checks.require(reader.raw_sha256.hexdigest() == SOURCE_HASHES["private_values_raw"], "source.private_raw_hash")

    crosswalk_summary = summary.get("crosswalk_summaries")
    checks.require(isinstance(crosswalk_summary, dict), "source.summary_crosswalk")
    kind_summaries: dict[str, dict[str, Any]] = {}
    for stage in ("202b", "202c"):
        stage_summary = crosswalk_summary.get(stage)
        checks.require(isinstance(stage_summary, dict), f"source.summary_{stage}")
        checks.require(
            _exact_int(
                stage_summary.get("unique_tuples"), EXPECTED_INPUT_UNIQUE[stage]
            )
            and _exact_int(
                stage_summary.get("global_output_multiplicity"),
                EXPECTED_INPUT_MULTIPLICITY[stage],
            ),
            f"source.summary_{stage}_totals",
        )
        kinds = stage_summary.get("tuple_kind_summaries")
        checks.require(
            isinstance(kinds, dict) and set(kinds) == set(TUPLE_FIELDS[stage]),
            f"source.summary_{stage}_kinds",
        )
        for kind, value in kinds.items():
            checks.require(isinstance(value, dict), f"source.summary_{stage}_kind")
            kind_summaries[f"{stage}:{kind}"] = {
                "stage": stage,
                "tuple_kind": kind,
                "unique_tuples": value.get("unique_tuples"),
                "total_multiplicity": value.get("total_multiplicity"),
                "global_tuple_set_sha256": value.get("global_tuple_set_sha256"),
                "global_tuple_frequency_sha256": value.get("global_tuple_frequency_sha256"),
                "output_stream": (
                    "ndc_handoff" if (stage, kind) == NDC_KIND else "local_evidence"
                ),
            }
            checks.require(
                all(
                    type(kind_summaries[f"{stage}:{kind}"][name]) is int
                    for name in ("unique_tuples", "total_multiplicity")
                )
                and all(
                    SHA256_RE.fullmatch(str(kind_summaries[f"{stage}:{kind}"][name]))
                    for name in (
                        "global_tuple_set_sha256", "global_tuple_frequency_sha256"
                    )
                ),
                f"source.summary_{stage}_{kind}_contract",
            )
    checks.require(
        sum(kind_summaries[f"{stage}:{kind}"]["unique_tuples"] for stage, kind in LOCAL_KIND_ORDER)
        == EXPECTED_LOCAL_UNIQUE,
        "source.local_unique",
    )
    checks.require(
        sum(kind_summaries[f"{stage}:{kind}"]["total_multiplicity"] for stage, kind in LOCAL_KIND_ORDER)
        == EXPECTED_LOCAL_MULTIPLICITY,
        "source.local_multiplicity",
    )
    ndc_summary = kind_summaries["202c:ndc_external_mapping_input"]
    checks.require(
        ndc_summary["unique_tuples"] == EXPECTED_NDC_UNIQUE
        and ndc_summary["total_multiplicity"] == EXPECTED_NDC_MULTIPLICITY,
        "source.ndc_totals",
    )
    boundary_sets = {
        boundary["source_field"]: {
            None if record["raw_is_null"] else record["raw_value"]
            for record in boundary["records"]
        }
        for boundary in boundaries.values()
    }
    return {
        "boundaries": boundaries,
        "semantic_seed": observed_seed,
        "semantic_seed_set": {
            (field.decode("utf-8"), raw.decode("utf-8"))
            for field, raw in observed_seed
        },
        "boundary_sets": boundary_sets,
        "kind_summaries": kind_summaries,
    }


def _stream_result(reader: _GzipNdjsonReader) -> dict[str, Any]:
    return {
        "encoding": PRIVATE_ENCODING,
        "sha256": reader.stored_sha256.hexdigest(),
        "bytes": reader.stored_bytes,
        "raw_sha256": reader.raw_sha256.hexdigest(),
        "raw_bytes": reader.raw_bytes,
        "records": reader.records,
    }


def _finish_stream(
    cursor: _Cursor,
    reader: _GzipNdjsonReader,
    stream_name: str,
    section_counts: Mapping[str, Any],
    checks: Checks,
) -> dict[str, Any]:
    footer = _exact_keys(
        cursor.take("footer", f"{stream_name}.footer"),
        {"record_type", "records_before_footer", "section_counts"},
        f"{stream_name}.footer_schema",
    )
    checks.require(
        _exact_int(footer["records_before_footer"], reader.records - 1),
        f"{stream_name}.footer_count",
    )
    checks.require(
        _strict_equal(footer["section_counts"], dict(section_counts)),
        f"{stream_name}.footer_sections",
    )
    cursor.finish(stream_name)
    checks.require(
        reader.records == EXPECTED_STREAM_RECORDS[stream_name],
        f"{stream_name}.record_count",
    )
    return _stream_result(reader)


def _audit_semantic_stream(
    path: Path,
    source: Mapping[str, Any],
    created_at_utc: str,
    component_lineage: Mapping[str, Any],
    checks: Checks,
) -> dict[str, Any]:
    stream = "semantic_review_template"
    reader = _GzipNdjsonReader(path, stream)
    cursor = _Cursor(reader)
    _validate_header(cursor, stream, created_at_utc, component_lineage, checks)
    begin = _exact_keys(
        cursor.take("semantic_review_begin", "semantic.begin"),
        {"record_type", "key_count", "key_set_sha256", "semantic_dimensions"},
        "semantic.begin_schema",
    )
    checks.require(
        _strict_equal(begin, {
            "record_type": "semantic_review_begin",
            "key_count": EXPECTED_SEMANTIC_KEYS,
            "key_set_sha256": EXPECTED_SEMANTIC_KEY_SET_SHA256,
            "semantic_dimensions": list(SEMANTIC_DIMENSIONS),
        }),
        "semantic.begin_contract",
    )
    frequencies: dict[tuple[bytes, bytes], int] = {}
    for source_key in SOURCE_KEYS[:5]:
        boundary = source["boundaries"][source_key]
        field = boundary["source_field"].encode("utf-8")
        for value in boundary["records"]:
            if value["raw_is_null"] is False:
                frequencies[(field, value["raw_value"].encode("utf-8"))] = value[
                    "exact_row_count"
                ]
    observed_keys: list[tuple[bytes, bytes]] = []
    item_keys = {
        "record_type", "source_field", "exact_raw_value", "exact_row_count",
        "review_status", "semantic_decisions", "mapping_group_id",
        "decision_basis", "reviewer_id", "reviewed_at_utc",
    }
    for expected in source["semantic_seed"]:
        item = _exact_keys(
            cursor.take("semantic_review_key", "semantic.item"),
            item_keys,
            "semantic.item_schema",
        )
        if not isinstance(item["source_field"], str) or not isinstance(item["exact_raw_value"], str):
            raise AdjudicationInputAuditError("semantic.item_text")
        observed = (
            item["source_field"].encode("utf-8"),
            item["exact_raw_value"].encode("utf-8"),
        )
        checks.require(observed == expected, "semantic.item_key")
        checks.require(
            _exact_int(item["exact_row_count"], frequencies[expected]),
            "semantic.item_frequency",
        )
        checks.require(item["review_status"] == "unreviewed", "semantic.item_review_status")
        checks.require(
            _strict_equal(
                item["semantic_decisions"],
                {dimension: "uncertain" for dimension in SEMANTIC_DIMENSIONS},
            ),
            "semantic.item_decisions",
        )
        checks.require(
            item["mapping_group_id"] is None
            and item["decision_basis"] is None
            and item["reviewer_id"] is None
            and item["reviewed_at_utc"] is None,
            "semantic.item_neutral",
        )
        observed_keys.append(observed)
    end = _exact_keys(
        cursor.take("semantic_review_end", "semantic.end"),
        {"record_type", "records", "key_set_sha256"},
        "semantic.end_schema",
    )
    observed_hash = _semantic_seed_hash(observed_keys)
    checks.require(
        _exact_int(end["records"], EXPECTED_SEMANTIC_KEYS)
        and end["key_set_sha256"] == observed_hash
        and observed_hash == EXPECTED_SEMANTIC_KEY_SET_SHA256,
        "semantic.end_contract",
    )
    return _finish_stream(
        cursor,
        reader,
        stream,
        {"semantic_review_keys": EXPECTED_SEMANTIC_KEYS},
        checks,
    )


def _audit_route_stream(
    path: Path,
    source: Mapping[str, Any],
    created_at_utc: str,
    component_lineage: Mapping[str, Any],
    checks: Checks,
) -> dict[str, Any]:
    stream = "route_review_template"
    reader = _GzipNdjsonReader(path, stream)
    cursor = _Cursor(reader)
    _validate_header(cursor, stream, created_at_utc, component_lineage, checks)
    by_raw: dict[bytes, list[dict[str, Any]]] = {}
    null_inputs: list[dict[str, Any]] = []
    typed_hashes: dict[str, str] = {}
    for source_key, source_field, field_role in ROUTE_SOURCES:
        boundary = source["boundaries"][source_key]
        typed_hashes[source_key] = boundary["metadata"]["typed_set_sha256"]
        for value in boundary["records"]:
            if value["raw_is_null"]:
                null_inputs.append(
                    {
                        "source_key": source_key,
                        "source_field": source_field,
                        "field_role": field_role,
                        "exact_row_count": value["exact_row_count"],
                    }
                )
            else:
                raw = value["raw_value"].encode("utf-8")
                by_raw.setdefault(raw, []).append(
                    {
                        "source_key": source_key,
                        "source_field": source_field,
                        "field_role": field_role,
                        "exact_row_count": value["exact_row_count"],
                    }
                )
    canonical = sorted(by_raw)
    canonical_ids = {
        raw: f"R{index:06d}" for index, raw in enumerate(canonical, start=1)
    }
    memberships: list[dict[str, Any]] = []
    for raw in canonical:
        for membership in by_raw[raw]:
            memberships.append({
                "record_type": "route_source_membership",
                **membership,
                "raw_value_state": "nonnull",
                "exact_raw_value": raw.decode("utf-8"),
                "decision": "unknown",
                "route_state": "unknown",
                "sets_has_unknown": True,
                "decision_provenance": "default_unknown_unreviewed",
                "canonical_review_id": canonical_ids[raw],
                "review_status": "unreviewed",
                "decision_basis": None,
                "reviewer_id": None,
                "reviewed_at_utc": None,
            })
    for membership in null_inputs:
        memberships.append({
            "record_type": "route_source_membership",
            **membership,
            "raw_value_state": "sql_null",
            "exact_raw_value": None,
            "decision": None,
            "route_state": "missing",
            "sets_has_unknown": False,
            "decision_provenance": "forced_sql_null_policy",
            "canonical_review_id": None,
            "review_status": "not_required",
            "decision_basis": "forced_sql_null_policy",
            "reviewer_id": None,
            "reviewed_at_utc": None,
        })
    memberships.sort(key=lambda item: (
        item["source_field"].encode("utf-8"),
        0 if item["raw_value_state"] == "sql_null" else 1,
        b"" if item["exact_raw_value"] is None
        else item["exact_raw_value"].encode("utf-8"),
    ))
    checks.require(len(canonical) == EXPECTED_ROUTE_CANONICAL, "route.canonical_count")
    checks.require(
        sum(item["raw_value_state"] == "nonnull" for item in memberships)
        == EXPECTED_ROUTE_NONNULL_MEMBERSHIPS,
        "route.nonnull_memberships",
    )
    checks.require(
        sum(item["raw_value_state"] == "sql_null" for item in memberships)
        == EXPECTED_ROUTE_NULL_MEMBERSHIPS,
        "route.null_memberships",
    )
    checks.require(
        len(memberships) == EXPECTED_ROUTE_TYPED_MEMBERSHIPS,
        "route.typed_memberships",
    )
    begin = _exact_keys(
        cursor.take("route_review_begin", "route.begin"),
        {
            "record_type", "canonical_exact_nonnull_values",
            "source_specific_nonnull_memberships",
            "source_specific_sql_null_memberships",
            "source_specific_typed_memberships", "typed_set_sha256",
        },
        "route.begin_schema",
    )
    checks.require(
        _strict_equal(begin, {
            "record_type": "route_review_begin",
            "canonical_exact_nonnull_values": EXPECTED_ROUTE_CANONICAL,
            "source_specific_nonnull_memberships": EXPECTED_ROUTE_NONNULL_MEMBERSHIPS,
            "source_specific_sql_null_memberships": EXPECTED_ROUTE_NULL_MEMBERSHIPS,
            "source_specific_typed_memberships": EXPECTED_ROUTE_TYPED_MEMBERSHIPS,
            "typed_set_sha256": typed_hashes,
        }),
        "route.begin_contract",
    )
    canonical_keys = {
        "record_type", "canonical_review_id", "exact_raw_value", "raw_utf8_bytes",
        "decision", "review_status", "decision_basis", "reviewer_id",
        "reviewed_at_utc",
    }
    for index, raw in enumerate(canonical, start=1):
        item = _exact_keys(
            cursor.take("canonical_route_review", "route.canonical"),
            canonical_keys,
            "route.canonical_schema",
        )
        checks.require(
            item["canonical_review_id"] == canonical_ids[raw],
            "route.canonical_id",
        )
        checks.require(
            isinstance(item["exact_raw_value"], str)
            and item["exact_raw_value"].encode("utf-8") == raw
            and _exact_int(item["raw_utf8_bytes"], len(raw)),
            "route.canonical_value",
        )
        checks.require(
            item["decision"] == "unknown"
            and item["review_status"] == "unreviewed"
            and item["decision_basis"] is None
            and item["reviewer_id"] is None
            and item["reviewed_at_utc"] is None,
            "route.canonical_neutral",
        )
    membership_keys = {
        "record_type", "source_key", "source_field", "field_role",
        "raw_value_state", "exact_raw_value", "exact_row_count", "decision",
        "route_state", "sets_has_unknown", "decision_provenance",
        "canonical_review_id", "review_status", "decision_basis",
        "reviewer_id", "reviewed_at_utc",
    }
    for expected in memberships:
        item = _exact_keys(
            cursor.take("route_source_membership", "route.membership"),
            membership_keys,
            "route.membership_schema",
        )
        checks.require(
            _strict_equal(item, expected),
            "route.membership_contract",
        )
    end = _exact_keys(
        cursor.take("route_review_end", "route.end"),
        {
            "record_type", "canonical_records", "source_membership_records",
            "canonical_exact_set_sha256",
        },
        "route.end_schema",
    )
    route_hash = _canonical_route_hash([raw.decode("utf-8") for raw in canonical])
    checks.require(
        _strict_equal(end, {
            "record_type": "route_review_end",
            "canonical_records": EXPECTED_ROUTE_CANONICAL,
            "source_membership_records": EXPECTED_ROUTE_TYPED_MEMBERSHIPS,
            "canonical_exact_set_sha256": route_hash,
        }),
        "route.end_contract",
    )
    result = _finish_stream(
        cursor,
        reader,
        stream,
        {
            "canonical_route_reviews": EXPECTED_ROUTE_CANONICAL,
            "route_source_memberships": EXPECTED_ROUTE_TYPED_MEMBERSHIPS,
        },
        checks,
    )
    result["canonical_exact_set_sha256"] = route_hash
    return result


def _audit_local_stream(
    path: Path,
    source: Mapping[str, Any],
    created_at_utc: str,
    component_lineage: Mapping[str, Any],
    checks: Checks,
) -> dict[str, Any]:
    stream = "local_evidence"
    reader = _GzipNdjsonReader(path, stream)
    cursor = _Cursor(reader)
    _validate_header(cursor, stream, created_at_utc, component_lineage, checks)
    total_unique = 0
    total_multiplicity = 0
    observed_summaries: dict[str, dict[str, Any]] = {}
    begin_keys = {
        "record_type", "stage", "tuple_kind", "unique_tuples",
        "total_multiplicity", "global_tuple_set_sha256",
        "global_tuple_frequency_sha256",
    }
    end_keys = {
        "record_type", "stage", "tuple_kind", "records",
        "total_multiplicity", "global_tuple_set_sha256",
        "global_tuple_frequency_sha256",
    }
    tuple_keys = {"record_type", "stage", "tuple_kind", "tuple", "multiplicity"}
    for stage, kind in LOCAL_KIND_ORDER:
        key = f"{stage}:{kind}"
        expected = source["kind_summaries"][key]
        begin = _exact_keys(
            cursor.take("evidence_kind_begin", f"local.{key}_begin"),
            begin_keys,
            f"local.{key}_begin_schema",
        )
        expected_section = {
            "record_type": "evidence_kind_begin",
            "stage": stage,
            "tuple_kind": kind,
            "unique_tuples": expected["unique_tuples"],
            "total_multiplicity": expected["total_multiplicity"],
            "global_tuple_set_sha256": expected["global_tuple_set_sha256"],
            "global_tuple_frequency_sha256": expected["global_tuple_frequency_sha256"],
        }
        checks.require(
            _strict_equal(begin, expected_section),
            f"local.{key}_begin_contract",
        )
        hashers = _new_tuple_hashers(key, expected["unique_tuples"])
        previous: bytes | None = None
        kind_total = 0
        for _ in range(expected["unique_tuples"]):
            item = _exact_keys(
                cursor.take("evidence_tuple", f"local.{key}_tuple"),
                tuple_keys,
                f"local.{key}_tuple_schema",
            )
            checks.require(
                item["stage"] == stage and item["tuple_kind"] == kind,
                f"local.{key}_tuple_identity",
            )
            encoded = _validate_tuple(
                stage, kind, item["tuple"], item["multiplicity"], f"local.{key}"
            )
            _validate_tuple_bindings(
                stage,
                kind,
                item["tuple"],
                source,
                f"local.{key}",
                checks,
            )
            checks.require(previous is None or encoded > previous, f"local.{key}_sort")
            previous = encoded
            checks.require(kind_total <= MAX_COUNT - item["multiplicity"], f"local.{key}_total_limit")
            kind_total += item["multiplicity"]
            _update_tuple_hashers(hashers, encoded, item["multiplicity"])
        set_hash = hashers[0].hexdigest()
        frequency_hash = hashers[1].hexdigest()
        checks.require(
            kind_total == expected["total_multiplicity"]
            and set_hash == expected["global_tuple_set_sha256"]
            and frequency_hash == expected["global_tuple_frequency_sha256"],
            f"local.{key}_hashes",
        )
        end = _exact_keys(
            cursor.take("evidence_kind_end", f"local.{key}_end"),
            end_keys,
            f"local.{key}_end_schema",
        )
        checks.require(
            _strict_equal(end, {
                "record_type": "evidence_kind_end",
                "stage": stage,
                "tuple_kind": kind,
                "records": expected["unique_tuples"],
                "total_multiplicity": expected["total_multiplicity"],
                "global_tuple_set_sha256": expected["global_tuple_set_sha256"],
                "global_tuple_frequency_sha256": expected[
                    "global_tuple_frequency_sha256"
                ],
            }),
            f"local.{key}_end_contract",
        )
        total_unique += expected["unique_tuples"]
        total_multiplicity += kind_total
        observed_summaries[key] = dict(expected)
    checks.require(total_unique == EXPECTED_LOCAL_UNIQUE, "local.total_unique")
    checks.require(total_multiplicity == EXPECTED_LOCAL_MULTIPLICITY, "local.total_multiplicity")
    result = _finish_stream(
        cursor,
        reader,
        stream,
        {
            "tuple_kinds": len(LOCAL_KIND_ORDER),
            "evidence_tuples": EXPECTED_LOCAL_UNIQUE,
            "total_multiplicity": EXPECTED_LOCAL_MULTIPLICITY,
        },
        checks,
    )
    result["tuple_kind_summaries"] = observed_summaries
    return result


def _audit_ndc_stream(
    path: Path,
    source: Mapping[str, Any],
    created_at_utc: str,
    component_lineage: Mapping[str, Any],
    checks: Checks,
) -> dict[str, Any]:
    stream = "ndc_handoff"
    reader = _GzipNdjsonReader(path, stream)
    cursor = _Cursor(reader)
    _validate_header(cursor, stream, created_at_utc, component_lineage, checks)

    boundary = source["boundaries"]["prescriptions_ndc"]
    nonnull = [item for item in boundary["records"] if not item["raw_is_null"]]
    nulls = [item for item in boundary["records"] if item["raw_is_null"]]
    checks.require(
        len(nonnull) == EXPECTED_NDC_CANDIDATES
        and len(nulls) == EXPECTED_NDC_NULL_BOUNDARIES,
        "ndc.boundary_partition",
    )
    candidate_begin = _exact_keys(
        cursor.take("ndc_candidates_begin", "ndc.candidates_begin"),
        {
            "record_type", "candidate_count", "source_field",
            "nonnull_set_sha256", "typed_set_sha256",
        },
        "ndc.candidates_begin_schema",
    )
    expected_candidate_begin = {
        "record_type": "ndc_candidates_begin",
        "candidate_count": EXPECTED_NDC_CANDIDATES,
        "source_field": "mimiciv_hosp.prescriptions.ndc",
        "nonnull_set_sha256": boundary["metadata"]["nonnull_set_sha256"],
        "typed_set_sha256": boundary["metadata"]["typed_set_sha256"],
    }
    checks.require(
        _strict_equal(candidate_begin, expected_candidate_begin),
        "ndc.candidates_begin_contract",
    )
    candidate_keys = {
        "record_type", "source_field", "exact_raw_value", "raw_utf8_bytes",
        "exact_row_count",
    }
    expected_frequency: dict[bytes, int] = {}
    for expected in nonnull:
        item = _exact_keys(
            cursor.take("ndc_candidate", "ndc.candidate"),
            candidate_keys,
            "ndc.candidate_schema",
        )
        raw = expected["raw_value"]
        expected_item = {
            "record_type": "ndc_candidate",
            "source_field": "mimiciv_hosp.prescriptions.ndc",
            "exact_raw_value": raw,
            "raw_utf8_bytes": expected["raw_utf8_bytes"],
            "exact_row_count": expected["exact_row_count"],
        }
        checks.require(
            _strict_equal(item, expected_item),
            "ndc.candidate_contract",
        )
        expected_frequency[raw.encode("utf-8")] = expected["exact_row_count"]
    null_item = _exact_keys(
        cursor.take("ndc_null_boundary", "ndc.null_boundary"),
        {"record_type", "source_field", "sql_null_rows"},
        "ndc.null_boundary_schema",
    )
    checks.require(
        _strict_equal(null_item, {
            "record_type": "ndc_null_boundary",
            "source_field": "mimiciv_hosp.prescriptions.ndc",
            "sql_null_rows": nulls[0]["exact_row_count"],
        }),
        "ndc.null_boundary_contract",
    )
    candidate_end = _exact_keys(
        cursor.take("ndc_candidates_end", "ndc.candidates_end"),
        {"record_type", "candidate_records", "null_boundary_records"},
        "ndc.candidates_end_schema",
    )
    checks.require(
        _strict_equal(candidate_end, {
            "record_type": "ndc_candidates_end",
            "candidate_records": EXPECTED_NDC_CANDIDATES,
            "null_boundary_records": EXPECTED_NDC_NULL_BOUNDARIES,
        }),
        "ndc.candidates_end_contract",
    )

    expected = source["kind_summaries"]["202c:ndc_external_mapping_input"]
    begin_keys = {
        "record_type", "stage", "tuple_kind", "unique_tuples",
        "total_multiplicity", "global_tuple_set_sha256",
        "global_tuple_frequency_sha256",
    }
    begin = _exact_keys(
        cursor.take("ndc_handoff_begin", "ndc.handoff_begin"),
        begin_keys,
        "ndc.handoff_begin_schema",
    )
    checks.require(
        _strict_equal(begin, {
            "record_type": "ndc_handoff_begin",
            "stage": "202c",
            "tuple_kind": "ndc_external_mapping_input",
            "unique_tuples": expected["unique_tuples"],
            "total_multiplicity": expected["total_multiplicity"],
            "global_tuple_set_sha256": expected["global_tuple_set_sha256"],
            "global_tuple_frequency_sha256": expected[
                "global_tuple_frequency_sha256"
            ],
        }),
        "ndc.handoff_begin_contract",
    )
    hashers = _new_tuple_hashers(
        "202c:ndc_external_mapping_input", expected["unique_tuples"]
    )
    observed_frequency: dict[bytes, int] = {}
    previous: bytes | None = None
    total = 0
    context_keys = {"record_type", "tuple", "multiplicity"}
    for _ in range(expected["unique_tuples"]):
        item = _exact_keys(
            cursor.take("ndc_context", "ndc.context"),
            context_keys,
            "ndc.context_schema",
        )
        encoded = _validate_tuple(
            "202c",
            "ndc_external_mapping_input",
            item["tuple"],
            item["multiplicity"],
            "ndc.context",
        )
        _validate_tuple_bindings(
            "202c",
            "ndc_external_mapping_input",
            item["tuple"],
            source,
            "ndc.context",
            checks,
        )
        checks.require(previous is None or encoded > previous, "ndc.context_sort")
        previous = encoded
        multiplicity = item["multiplicity"]
        checks.require(total <= MAX_COUNT - multiplicity, "ndc.total_limit")
        total += multiplicity
        ndc_raw = item["tuple"]["ndc"].encode("utf-8")
        checks.require(ndc_raw in expected_frequency, "ndc.context_candidate_membership")
        prior = observed_frequency.get(ndc_raw, 0)
        checks.require(prior <= MAX_COUNT - multiplicity, "ndc.frequency_limit")
        observed_frequency[ndc_raw] = prior + multiplicity
        _update_tuple_hashers(hashers, encoded, multiplicity)
    set_hash = hashers[0].hexdigest()
    frequency_hash = hashers[1].hexdigest()
    checks.require(
        total == expected["total_multiplicity"]
        and set_hash == expected["global_tuple_set_sha256"]
        and frequency_hash == expected["global_tuple_frequency_sha256"],
        "ndc.context_hashes",
    )
    checks.require(
        observed_frequency == expected_frequency,
        "ndc.candidate_context_frequency_conservation",
    )
    end = _exact_keys(
        cursor.take("ndc_handoff_end", "ndc.handoff_end"),
        {
            "record_type", "stage", "tuple_kind", "records",
            "total_multiplicity", "global_tuple_set_sha256",
            "global_tuple_frequency_sha256",
        },
        "ndc.handoff_end_schema",
    )
    checks.require(
        _strict_equal(end, {
            "record_type": "ndc_handoff_end",
            "stage": "202c",
            "tuple_kind": "ndc_external_mapping_input",
            "records": expected["unique_tuples"],
            "total_multiplicity": expected["total_multiplicity"],
            "global_tuple_set_sha256": set_hash,
            "global_tuple_frequency_sha256": frequency_hash,
        }),
        "ndc.handoff_end_contract",
    )
    result = _finish_stream(
        cursor,
        reader,
        stream,
        {
            "ndc_candidates": EXPECTED_NDC_CANDIDATES,
            "ndc_null_boundaries": EXPECTED_NDC_NULL_BOUNDARIES,
            "ndc_contexts": EXPECTED_NDC_UNIQUE,
            "total_multiplicity": EXPECTED_NDC_MULTIPLICITY,
        },
        checks,
    )
    result["tuple_kind_summary"] = dict(expected)
    result["candidate_nonnull_set_sha256"] = boundary["metadata"][
        "nonnull_set_sha256"
    ]
    result["candidate_typed_set_sha256"] = boundary["metadata"][
        "typed_set_sha256"
    ]
    return result


def _check_public_keys(value: Any, checks: Checks, label: str) -> None:
    if isinstance(value, dict):
        checks.require(
            not (set(value) & FORBIDDEN_PUBLIC_KEYS),
            label + ".forbidden_key",
        )
        for nested in value.values():
            _check_public_keys(nested, checks, label)
    elif isinstance(value, list):
        for nested in value:
            _check_public_keys(nested, checks, label)


def _expected_conservation(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "semantic_review_keys": EXPECTED_SEMANTIC_KEYS,
        "semantic_seed_key_set_sha256": EXPECTED_SEMANTIC_KEY_SET_SHA256,
        "route_canonical_exact_nonnull_values": EXPECTED_ROUTE_CANONICAL,
        "route_source_specific_nonnull_memberships": (
            EXPECTED_ROUTE_NONNULL_MEMBERSHIPS
        ),
        "route_source_specific_sql_null_memberships": (
            EXPECTED_ROUTE_NULL_MEMBERSHIPS
        ),
        "route_source_specific_typed_memberships": EXPECTED_ROUTE_TYPED_MEMBERSHIPS,
        "input_crosswalk_unique_tuples": dict(EXPECTED_INPUT_UNIQUE),
        "input_crosswalk_total_multiplicity": dict(EXPECTED_INPUT_MULTIPLICITY),
        "local_evidence_unique_tuples": EXPECTED_LOCAL_UNIQUE,
        "local_evidence_total_multiplicity": EXPECTED_LOCAL_MULTIPLICITY,
        "ndc_handoff_unique_tuples": EXPECTED_NDC_UNIQUE,
        "ndc_handoff_total_multiplicity": EXPECTED_NDC_MULTIPLICITY,
        "ndc_candidate_values": EXPECTED_NDC_CANDIDATES,
        "ndc_null_boundaries": EXPECTED_NDC_NULL_BOUNDARIES,
        "tuple_kind_summaries": dict(source["kind_summaries"]),
    }


def _standard_stream_result(
    stream_name: str, result: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "file": STREAM_FILES[stream_name],
        "encoding": result["encoding"],
        "sha256": result["sha256"],
        "bytes": result["bytes"],
        "raw_sha256": result["raw_sha256"],
        "raw_bytes": result["raw_bytes"],
        "records": result["records"],
    }


def _validate_stream_metadata(
    value: Any,
    expected: Mapping[str, Any],
    label: str,
    checks: Checks,
) -> None:
    metadata = _exact_keys(
        value,
        set(expected),
        label + ".schema",
    )
    checks.require(_strict_equal(metadata, dict(expected)), label + ".content")
    checks.require(
        isinstance(metadata["file"], str)
        and Path(metadata["file"]).name == metadata["file"],
        label + ".filename",
    )
    checks.require(
        SHA256_RE.fullmatch(metadata["sha256"]) is not None
        and SHA256_RE.fullmatch(metadata["raw_sha256"]) is not None,
        label + ".hash_format",
    )
    checks.require(
        type(metadata["bytes"]) is int
        and 0 < metadata["bytes"] <= MAX_STORED_BYTES
        and type(metadata["raw_bytes"]) is int
        and 0 < metadata["raw_bytes"] <= MAX_RAW_BYTES
        and type(metadata["records"]) is int
        and metadata["records"] > 0,
        label + ".bounds",
    )


def _load_target_documents(
    root: Path,
    directory: Path,
    checks: Checks,
) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes]:
    checks.require(directory.is_relative_to(root), "artifact.path_within_root")
    checks.require(
        directory.is_dir() and not directory.is_symlink(),
        "artifact.directory",
    )
    checks.require(_mode(directory) == "0700", "artifact.directory_mode")
    checks.require(_git_ignored(root, directory), "artifact.git_ignored")
    expected_files = {
        MANIFEST_FILENAME,
        SUMMARY_FILENAME,
        *STREAM_FILES.values(),
    }
    entries = list(directory.iterdir())
    checks.require(
        all(item.is_file() and not item.is_symlink() for item in entries),
        "artifact.regular_files",
    )
    checks.require(
        {item.name for item in entries} == expected_files,
        "artifact.file_inventory",
    )
    for item in entries:
        checks.require(_mode(item) == "0600", "artifact.file_mode")
    manifest, manifest_raw = _read_json(
        directory / MANIFEST_FILENAME, "manifest"
    )
    summary, summary_raw = _read_json(directory / SUMMARY_FILENAME, "summary")
    return manifest, manifest_raw, summary, summary_raw


def _audit_complete_artifact(
    root: Path,
    directory: Path,
    checks: Checks,
) -> tuple[dict[str, Any], dict[str, Any]]:
    component_lineage, artifact_parent = _load_component_lineage(root, checks)
    checks.require(
        directory.parent == artifact_parent,
        "artifact.configured_parent",
    )
    manifest, manifest_raw, summary, summary_raw = _load_target_documents(
        root, directory, checks
    )
    manifest = _exact_keys(
        manifest,
        {
            "schema_version", "component_id", "status", "created_at_utc",
            "finished_at_utc", "artifact_directory", "component_lineage",
            "input_lineage", "outputs", "conservation", "privacy", "guards",
        },
        "manifest.schema",
    )
    summary = _exact_keys(
        summary,
        {
            "schema_version", "component_id", "status", "created_at_utc",
            "scope", "component_lineage", "input_lineage", "output_hashes",
            "conservation", "privacy", "guards",
        },
        "summary.schema",
    )
    created = manifest["created_at_utc"]
    created_time = _parse_utc(created)
    finished_time = _parse_utc(manifest["finished_at_utc"])
    checks.require(
        isinstance(created, str) and created.endswith("Z")
        and created_time is not None,
        "manifest.created_at",
    )
    checks.require(
        isinstance(manifest["finished_at_utc"], str)
        and manifest["finished_at_utc"].endswith("Z")
        and finished_time is not None
        and created_time is not None
        and finished_time >= created_time,
        "manifest.finished_at",
    )
    audit_started_at = datetime.now(timezone.utc)
    checks.require(
        created_time is not None and created_time <= audit_started_at,
        "manifest.created_at_not_future",
    )
    checks.require(
        finished_time is not None and finished_time <= audit_started_at,
        "manifest.finished_at_not_future",
    )
    checks.require(
        created_time is not None
        and directory.name
        == created_time.strftime("%Y%m%dT%H%M%S.%fZ"),
        "artifact.timestamp_directory",
    )
    common = {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "status": "complete",
        "created_at_utc": created,
        "component_lineage": component_lineage,
        "input_lineage": _expected_input_lineage(),
        "privacy": EXPECTED_PUBLIC_PRIVACY,
        "guards": {key: False for key in FALSE_GUARDS},
    }
    for name, expected in common.items():
        checks.require(
            _strict_equal(manifest[name], expected),
            "manifest." + name,
        )
        checks.require(
            _strict_equal(summary[name], expected),
            "summary." + name,
        )
    display_directory = str(directory.relative_to(root))
    checks.require(
        manifest["artifact_directory"] == display_directory,
        "manifest.artifact_directory",
    )
    checks.require(
        summary["scope"]
        == "private_query202_adjudication_inputs_without_decisions",
        "summary.scope",
    )
    _check_public_keys(manifest, checks, "privacy.manifest")
    _check_public_keys(summary, checks, "privacy.summary")

    (
        _source_manifest,
        _source_audit,
        source_summary,
        source_path,
        source_snapshot,
        source_config_snapshot,
    ) = (
        _load_source_documents(root, checks)
    )
    source = _stream_source_private(source_path, source_summary, checks)
    conservation = _expected_conservation(source)
    checks.require(
        _strict_equal(manifest["conservation"], conservation),
        "manifest.conservation",
    )
    checks.require(
        _strict_equal(summary["conservation"], conservation),
        "summary.conservation",
    )

    stream_results = {
        "semantic_review_template": _audit_semantic_stream(
            directory / STREAM_FILES["semantic_review_template"],
            source,
            created,
            component_lineage,
            checks,
        ),
        "local_evidence": _audit_local_stream(
            directory / STREAM_FILES["local_evidence"],
            source,
            created,
            component_lineage,
            checks,
        ),
        "route_review_template": _audit_route_stream(
            directory / STREAM_FILES["route_review_template"],
            source,
            created,
            component_lineage,
            checks,
        ),
        "ndc_handoff": _audit_ndc_stream(
            directory / STREAM_FILES["ndc_handoff"],
            source,
            created,
            component_lineage,
            checks,
        ),
    }
    manifest_outputs = _exact_keys(
        manifest["outputs"],
        {*STREAM_FILES, "aggregate_summary"},
        "manifest.outputs_schema",
    )
    summary_hashes = _exact_keys(
        summary["output_hashes"],
        set(STREAM_FILES),
        "summary.output_hashes_schema",
    )
    public_output_hashes: dict[str, dict[str, Any]] = {}
    for stream_name, result in stream_results.items():
        expected = _standard_stream_result(stream_name, result)
        _validate_stream_metadata(
            manifest_outputs[stream_name],
            expected,
            "manifest.output_" + stream_name,
            checks,
        )
        _validate_stream_metadata(
            summary_hashes[stream_name],
            expected,
            "summary.output_" + stream_name,
            checks,
        )
        public_output_hashes[stream_name] = expected
    aggregate_metadata = _exact_keys(
        manifest_outputs["aggregate_summary"],
        {"file", "sha256", "bytes"},
        "manifest.aggregate_summary_schema",
    )
    expected_aggregate = {
        "file": SUMMARY_FILENAME,
        "sha256": _sha_bytes(summary_raw),
        "bytes": len(summary_raw),
    }
    checks.require(
        _strict_equal(aggregate_metadata, expected_aggregate),
        "manifest.aggregate_summary_content",
    )
    checks.require(
        _sha_file(directory / SUMMARY_FILENAME) == expected_aggregate["sha256"],
        "summary.file_hash",
    )
    target_snapshot: dict[str, dict[str, Any]] = {
        MANIFEST_FILENAME: {
            "bytes": len(manifest_raw),
            "sha256": _sha_bytes(manifest_raw),
        },
        SUMMARY_FILENAME: {
            "bytes": len(summary_raw),
            "sha256": _sha_bytes(summary_raw),
        },
    }
    for stream_name, result in stream_results.items():
        target_snapshot[STREAM_FILES[stream_name]] = {
            "bytes": result["bytes"],
            "sha256": result["sha256"],
        }
    source_directory = source_path.parent
    checks.require(
        not _path_has_symlink(root, source_directory),
        "source.final_path",
    )
    checks.require(_git_ignored(root, source_directory), "source.final_git_ignored")
    _recheck_directory_snapshot(
        source_directory,
        source_snapshot,
        "source.final",
        checks,
    )
    source_config_path = Path(source_config_snapshot["path"])
    checks.require(
        not _path_has_symlink(root, source_config_path),
        "source.final_config_path",
    )
    _recheck_file_snapshot(
        source_config_path,
        source_config_snapshot,
        "source.final_config",
        checks,
    )
    checks.require(
        directory.parent == artifact_parent
        and not _path_has_symlink(root, directory),
        "artifact.final_path",
    )
    checks.require(_git_ignored(root, directory), "artifact.final_git_ignored")
    _recheck_directory_snapshot(
        directory,
        target_snapshot,
        "artifact.final",
        checks,
    )
    config_path = _regular_project_file(root, str(COMPONENT_CONFIG_PATH))
    checks.require(
        config_path is not None
        and _sha_file(config_path) == component_lineage["config_sha256"],
        "component.config_hash_recheck",
    )
    checks.require(
        _implementation_bundle_sha256(root, COMPILER_IMPLEMENTATION_PATHS)
        == component_lineage["compiler_bundle_sha256"],
        "component.compiler_bundle_recheck",
    )
    checks.require(
        _implementation_bundle_sha256(root, AUDITOR_IMPLEMENTATION_PATHS)
        == component_lineage["auditor_bundle_sha256"],
        "component.auditor_bundle_recheck",
    )

    route_result = stream_results["route_review_template"]
    ndc_result = stream_results["ndc_handoff"]
    recomputed = {
        "manifest_sha256": _sha_bytes(manifest_raw),
        "aggregate_summary_sha256": _sha_bytes(summary_raw),
        "component_lineage": component_lineage,
        "input_lineage": _expected_input_lineage(),
        "output_hashes": public_output_hashes,
        "semantic_review_keys": EXPECTED_SEMANTIC_KEYS,
        "semantic_seed_key_set_sha256": EXPECTED_SEMANTIC_KEY_SET_SHA256,
        "route_canonical_exact_nonnull_values": EXPECTED_ROUTE_CANONICAL,
        "route_source_specific_typed_memberships": EXPECTED_ROUTE_TYPED_MEMBERSHIPS,
        "route_canonical_exact_set_sha256": route_result[
            "canonical_exact_set_sha256"
        ],
        "local_evidence_unique_tuples": EXPECTED_LOCAL_UNIQUE,
        "local_evidence_total_multiplicity": EXPECTED_LOCAL_MULTIPLICITY,
        "ndc_candidate_values": EXPECTED_NDC_CANDIDATES,
        "ndc_null_boundaries": EXPECTED_NDC_NULL_BOUNDARIES,
        "ndc_handoff_unique_tuples": EXPECTED_NDC_UNIQUE,
        "ndc_handoff_total_multiplicity": EXPECTED_NDC_MULTIPLICITY,
        "ndc_candidate_nonnull_set_sha256": ndc_result[
            "candidate_nonnull_set_sha256"
        ],
        "source_a_manifest_audit_private_hashes_confirmed": True,
        "private_modes_confirmed": True,
        "git_ignored_confirmed": True,
        "public_privacy_confirmed": True,
        "all_guards_false": True,
        "four_stream_conservation_confirmed": True,
    }
    publication_contract = {
        "artifact_parent": artifact_parent,
        "target_directory": directory,
        "target_snapshot": target_snapshot,
        "source_directory": source_directory,
        "source_snapshot": source_snapshot,
        "source_config_snapshot": source_config_snapshot,
        "component_lineage": component_lineage,
    }
    return recomputed, publication_contract


def _publication_guard(
    root: Path,
    contract: Mapping[str, Any],
    allowed_target_entries: set[str],
) -> None:
    source_directory = contract["source_directory"]
    target_directory = contract["target_directory"]
    artifact_parent = contract["artifact_parent"]
    source_config = contract["source_config_snapshot"]
    component_lineage = contract["component_lineage"]
    if (
        not isinstance(source_directory, Path)
        or not isinstance(target_directory, Path)
        or not isinstance(artifact_parent, Path)
        or target_directory.parent != artifact_parent
        or _path_has_symlink(root, source_directory)
        or _path_has_symlink(root, target_directory)
        or not _git_ignored(root, source_directory)
        or not _git_ignored(root, target_directory)
    ):
        raise AdjudicationInputAuditError("publication.path_contract")
    _recheck_directory_snapshot(
        source_directory,
        contract["source_snapshot"],
        "publication.source",
        None,
    )
    source_config_path = source_config.get("path")
    if (
        not isinstance(source_config_path, Path)
        or _path_has_symlink(root, source_config_path)
    ):
        raise AdjudicationInputAuditError("publication.source_config_path")
    _recheck_file_snapshot(
        source_config_path,
        source_config,
        "publication.source_config",
        None,
    )
    _recheck_directory_snapshot(
        target_directory,
        contract["target_snapshot"],
        "publication.target",
        None,
        allowed_extra=allowed_target_entries,
    )
    component_config = _regular_project_file(root, str(COMPONENT_CONFIG_PATH))
    if (
        component_config is None
        or _sha_file(component_config) != component_lineage["config_sha256"]
        or _implementation_bundle_sha256(root, COMPILER_IMPLEMENTATION_PATHS)
        != component_lineage["compiler_bundle_sha256"]
        or _implementation_bundle_sha256(root, AUDITOR_IMPLEMENTATION_PATHS)
        != component_lineage["auditor_bundle_sha256"]
    ):
        raise AdjudicationInputAuditError("publication.component_lineage")


def audit_query202_adjudication_input(
    root: Path, artifact_directory: Path
) -> dict[str, Any]:
    """Audit one compiled handoff offline and persist a value-safe result."""
    # Keep the caller's lexical root long enough to map an absolute artifact
    # path through macOS's system ``/var`` -> ``/private/var`` alias.  Only the
    # trusted root prefix is normalized this way; project-relative components
    # are reconstructed below and still undergo the per-component symlink
    # rejection before any target file is opened.
    lexical_root = Path(os.path.abspath(Path(root)))
    root = lexical_root.resolve()
    requested_directory = Path(artifact_directory)
    if ".." in requested_directory.parts:
        raise AdjudicationInputAuditError("audit.unsafe_output_directory")
    if requested_directory.is_absolute():
        lexical_requested = Path(os.path.abspath(requested_directory))
        try:
            relative_requested = lexical_requested.relative_to(lexical_root)
        except ValueError:
            try:
                relative_requested = lexical_requested.relative_to(root)
            except ValueError as exc:
                raise AdjudicationInputAuditError(
                    "audit.unsafe_output_directory"
                ) from exc
    else:
        relative_requested = requested_directory
    directory = root / relative_requested
    if (
        not directory.is_relative_to(root)
        or _path_has_symlink(root, directory)
    ):
        raise AdjudicationInputAuditError("audit.unsafe_output_directory")
    checks = Checks()
    recomputed: dict[str, Any] = {}
    publication_contract: dict[str, Any] = {}
    status = "failed"
    expected_pre_audit_files = {
        MANIFEST_FILENAME,
        SUMMARY_FILENAME,
        *STREAM_FILES.values(),
    }
    try:
        recomputed, publication_contract = _audit_complete_artifact(
            root, directory, checks
        )
        checks.require(
            directory.is_dir()
            and not directory.is_symlink()
            and _mode(directory) == "0700"
            and {item.name for item in directory.iterdir()}
            == expected_pre_audit_files,
            "audit.pre_write_inventory",
        )
        status = "passed"
    except AdjudicationInputAuditError as exc:
        checks.record_exception(str(exc))
    except Exception:
        checks.record_exception("audit.unexpected_failure")
    result = {
        "schema_version": 1,
        "audit": AUDIT_NAME,
        "component_id": COMPONENT_ID,
        "status": status,
        "artifact_directory": (
            str(directory.relative_to(root))
            if directory.is_relative_to(root) else "outside_project_root"
        ),
        "checks": {
            "total": checks.total,
            "passed": checks.total - len(checks.failed),
            "failed": len(checks.failed),
            "failed_names": sorted(checks.failed),
            "by_category": dict(sorted(checks.by_category.items())),
        },
        "recomputed": recomputed,
        "database_connection_opened": False,
        "external_api_called": False,
        "raw_values_emitted": False,
        "patient_admission_event_or_order_identifiers_emitted": False,
        "event_or_order_timestamps_emitted": False,
    }
    if (
        not directory.is_relative_to(root)
        or not directory.is_dir()
        or directory.is_symlink()
        or _path_has_symlink(root, directory)
        or _mode(directory) != "0700"
        or {item.name for item in directory.iterdir()}
        != expected_pre_audit_files
    ):
        raise AdjudicationInputAuditError("audit.unsafe_output_directory")
    audit_path = directory / AUDIT_FILENAME
    if audit_path.exists() or audit_path.is_symlink():
        raise AdjudicationInputAuditError("audit.output_already_exists")
    payload = (
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    expected_post_audit_files = expected_pre_audit_files | {AUDIT_FILENAME}
    publication_guard = (
        lambda extra: _publication_guard(root, publication_contract, extra)
        if status == "passed"
        else None
    )
    persisted = _write_private_atomic(
        audit_path,
        payload,
        expected_post_audit_files,
        publication_guard,
    )
    result["audit_summary"] = str(audit_path.relative_to(root))
    result["audit_summary_sha256"] = persisted["sha256"]
    result["audit_summary_bytes"] = persisted["bytes"]
    return result


__all__ = [
    "AdjudicationInputAuditError",
    "audit_query202_adjudication_input",
]




