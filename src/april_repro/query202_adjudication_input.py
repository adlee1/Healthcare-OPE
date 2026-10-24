"""Compile audited Query-202 A evidence into private adjudication inputs.

The compiler is deliberately offline.  It accepts only the frozen successful
Query-202 pre-adjudication artifact, validates the complete gzip/NDJSON stream,
and writes four deterministic private streams.  It never prints controlled
values and it does not make semantic, route, NDC, product, or event decisions.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import struct
import subprocess
import tempfile
from typing import Any, BinaryIO, Iterator, Mapping
import zlib

from .query202_adjudication_input_preregistration import (
    CONFIG_PATH as COMPONENT_CONFIG_PATH,
    query202_adjudication_input_preregistration_report,
)


COMPONENT_ID = "D005-K-QUERY202-ADJUDICATION-INPUT-v1"
INPUT_COMPONENT_ID = "D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2"
INPUT_QUERY = "potassium_query202_pre_adjudication"
ARTIFACT_ENCODING = "gzip+utf8+ndjson-v1"
DEFAULT_INPUT_DIRECTORY = Path("artifacts/profiling/20261012T152323.460063Z")
DEFAULT_OUTPUT_PARENT = Path("artifacts/query202-adjudication-input")
SOURCE_ARTIFACT_DIRECTORY = DEFAULT_INPUT_DIRECTORY

SEMANTIC_REVIEW_FILE = "semantic-review-template.jsonl.gz"
LOCAL_EVIDENCE_FILE = "local-evidence.jsonl.gz"
ROUTE_REVIEW_FILE = "route-review-template.jsonl.gz"
NDC_HANDOFF_FILE = "ndc-handoff.jsonl.gz"
AGGREGATE_SUMMARY_FILE = "aggregate-summary.json"
MANIFEST_FILE = "manifest.json"

STREAM_NAMES = (
    "semantic_review_template",
    "local_evidence",
    "route_review_template",
    "ndc_handoff",
)
STREAM_FILES = {
    "semantic_review_template": SEMANTIC_REVIEW_FILE,
    "local_evidence": LOCAL_EVIDENCE_FILE,
    "route_review_template": ROUTE_REVIEW_FILE,
    "ndc_handoff": NDC_HANDOFF_FILE,
}

# These production expectations are module constants on purpose.  Synthetic
# failure-injection fixtures may patch EXPECTED_* values without weakening the
# default production gate.
EXPECTED_INPUT_MANIFEST_SHA256 = (
    "3f8ecece96c5cb15e37ad8b7a539f6e3642cb2de8eac1bcec926b94c86579e30"
)
EXPECTED_INPUT_AUDIT_SHA256 = (
    "b44ec99e0499b7d427ad9ffb468bb73988bfb0d94d672736569831eb997992ec"
)
EXPECTED_INPUT_CONFIG_SHA256 = (
    "73004c1051970184b732b36a325e03c1f39e286356bcf56adbe799185e93ab73"
)
EXPECTED_PRIVATE_VALUES_SHA256 = (
    "4b9f389574b4a8aafc823a7f78a139563f63c092f8eb91af76a2175b082ae5bf"
)
EXPECTED_PRIVATE_VALUES_BYTES = 35_008_612
EXPECTED_PRIVATE_VALUES_RAW_SHA256 = (
    "ac39e21906c65e4186b2174298a880bd7cd5e8b30f8f3d79c79954e69c35103e"
)
EXPECTED_PRIVATE_VALUES_RAW_BYTES = 1_187_294_280
EXPECTED_PRIVATE_VALUES_RECORDS = 2_126_819
EXPECTED_SEMANTIC_KEY_COUNT = 34_565
EXPECTED_SEMANTIC_KEY_SET_SHA256 = (
    "cee42c49d4618e6c62e99dcea26c53166f21305231b3c35991d2c2534b94368a"
)
EXPECTED_ROUTE_CANONICAL_COUNT = 117
EXPECTED_ROUTE_NONNULL_MEMBERSHIPS = 233
EXPECTED_ROUTE_NULL_MEMBERSHIPS = 3
EXPECTED_ROUTE_TYPED_MEMBERSHIPS = 236
SOURCE_HASHES = {
    "manifest": EXPECTED_INPUT_MANIFEST_SHA256,
    "audit": EXPECTED_INPUT_AUDIT_SHA256,
    "config": EXPECTED_INPUT_CONFIG_SHA256,
    "private_values": EXPECTED_PRIVATE_VALUES_SHA256,
    "private_values_raw": EXPECTED_PRIVATE_VALUES_RAW_SHA256,
    "aggregate_summary": "b74dd5053fe8a81a33064500e1616de4eeaefed97192968a84ba102473c3c369",
    "executed_sql": "a98719c4b702fe9bde7aa877740ed0f6bb8305bd38d67072f8a5116bd4ed4fc3",
}
SOURCE_BYTES = {
    "private_values": EXPECTED_PRIVATE_VALUES_BYTES,
    "private_values_raw": EXPECTED_PRIVATE_VALUES_RAW_BYTES,
    "aggregate_summary": 13_527,
    "executed_sql": 9_607_756,
}

MAX_JSON_FILE_BYTES = 128 * 1024 * 1024
MAX_NDJSON_LINE_BYTES = 8 * 1024 * 1024
MAX_VALUE_UTF8_BYTES = 1024 * 1024
MAX_COUNT = (1 << 63) - 1
READ_CHUNK_BYTES = 1024 * 1024
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
ROUTE_CANONICAL_SET_VERSION = b"canonical-exact-nonnull-route-value-set-v1"

SEMANTIC_DIMENSIONS = (
    "product_identity",
    "dosage_form",
    "treatment_intent",
    "potassium_content",
    "meq_convertibility",
)

BOUNDARY_SPECS = (
    ("emar_medication", "mimiciv_hosp.emar.medication", "202a1", True),
    (
        "detail_product_description",
        "mimiciv_hosp.emar_detail.product_description",
        "202a2",
        True,
    ),
    ("pharmacy_medication", "mimiciv_hosp.pharmacy.medication", "202a3", True),
    ("prescription_drug", "mimiciv_hosp.prescriptions.drug", "202a4", True),
    (
        "detail_product_description_other",
        "mimiciv_hosp.emar_detail.product_description_other",
        "202a5",
        True,
    ),
    ("emar_detail_route", "mimiciv_hosp.emar_detail.route", "202a6", False),
    ("pharmacy_route", "mimiciv_hosp.pharmacy.route", "202a7", False),
    ("prescriptions_route", "mimiciv_hosp.prescriptions.route", "202a8", False),
    ("prescriptions_ndc", "mimiciv_hosp.prescriptions.ndc", "202a9", False),
)
SEMANTIC_SOURCE_FIELDS = tuple(item[1] for item in BOUNDARY_SPECS if item[3])
ROUTE_SOURCE_SPECS = (
    ("emar_detail_route", "mimiciv_hosp.emar_detail.route", "direct_detail_route"),
    ("pharmacy_route", "mimiciv_hosp.pharmacy.route", "auxiliary_pharmacy_route"),
    (
        "prescriptions_route",
        "mimiciv_hosp.prescriptions.route",
        "auxiliary_prescriptions_route",
    ),
)

EXPECTED_BOUNDARIES = {
    "emar_medication": (5046, 5045, "f8b16568bc8431d3d4e20414a04e821e64fd9c65fc075a199617c4d36fb3c136"),
    "detail_product_description": (6693, 6692, "6caa852c2492e068d59361a5349e1fc5f3006c0958298a9b49d3b808b834f4f3"),
    "pharmacy_medication": (11060, 11059, "652062b95888bc30ac3d9afb65897c4b546bba37b10b36cffda22dcbc4381ce0"),
    "prescription_drug": (10927, 10927, "937472a49fcf859e4077c0ee7ad1de8d9ffece89161c8277753bdb31e3efc247"),
    "detail_product_description_other": (843, 842, "0105f73cef307cc11b93e1d9d657d43a278c66c3c06ef31e5123db377e11dd4e"),
    "emar_detail_route": (18, 17, "a3b0d5664ae2e89f08df97f45347a6d7ae7761cdb2d138da781681ed2edd0ea9"),
    "pharmacy_route": (109, 108, "2dad858bbbd41002d3a417faa302bda9bd0f85111d47cbd075a0802886ebd76b"),
    "prescriptions_route": (109, 108, "b75209f1e0acea76a8c9818936b389a972def151317ede76073fc51dd65f1c0e"),
    "prescriptions_ndc": (6590, 6589, "10e5ff7bb578ca66aadfe274105ed94a53487ba05d7b80e0ebca8fb8c24bab9e"),
}

DETAIL_CONTEXT_FIELDS = (
    "row_role", "parent_field_ordinal", "administration_type",
    "complete_dose_not_given", "dose_due", "dose_due_unit", "dose_given",
    "dose_given_unit", "will_remainder_of_dose_be_given",
    "product_amount_given", "product_unit", "product_code",
    "product_description", "product_description_other", "prior_infusion_rate",
    "route", "infusion_rate", "infusion_rate_adjustment",
    "infusion_rate_adjustment_amount", "infusion_rate_unit",
    "infusion_complete", "completion_interval", "new_iv_bag_hung",
    "continued_infusion_in_other_location", "restart_interval",
    "non_formulary_visual_verification",
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
        "detail_pharmacy_prescription_bridge": (
            "link_identity_state", "poe_auxiliary_state", "row_role",
            "parent_field_ordinal", "product_description",
            "product_description_other", "product_code", "detail_route",
            "dose_due_unit", "dose_given_unit", "product_unit",
            "infusion_rate_unit", "pharmacy_medication", "pharmacy_route",
            *PRESCRIPTION_CONTEXT_FIELDS,
        ),
        "head_pharmacy_prescription_bridge": (
            "link_identity_state", "poe_auxiliary_state", "head_medication",
            "pharmacy_medication", "pharmacy_route", *PRESCRIPTION_CONTEXT_FIELDS,
        ),
        "ndc_external_mapping_input": PRESCRIPTION_CONTEXT_FIELDS,
        "pharmacy_no_prescription_component": (
            *PHARMACY_CONTEXT_FIELDS, "prescription_match_state"
        ),
        "pharmacy_prescription_bridge": (
            "link_identity_state", "poe_auxiliary_state", "pharmacy_medication",
            "pharmacy_route", *PRESCRIPTION_CONTEXT_FIELDS,
        ),
        "pharmacy_product_context": PHARMACY_CONTEXT_FIELDS,
        "prescription_identifier_context": PRESCRIPTION_CONTEXT_FIELDS,
    },
}
ALL_KIND_ORDER = tuple(
    (stage, kind)
    for stage in ("202b", "202c")
    for kind in sorted(
        TUPLE_FIELDS[stage],
        key=lambda value: (len(value.encode("utf-8")), value.encode("utf-8")),
    )
)
NDC_KIND = ("202c", "ndc_external_mapping_input")
LOCAL_KIND_ORDER = tuple(item for item in ALL_KIND_ORDER if item != NDC_KIND)

EXPECTED_KIND_SUMMARIES = {
    ("202b", "detail_product_context"): (137579, 84901924, "f955faa531cd72e172bacd99625dcd215cfe063e7a3bbd26f0cb7fffb34925d9", "6debef0d4d367acefe6061c1619c08b5aa46596361a788781921e89a8a37dd55"),
    ("202b", "detail_seed_membership_bridge"): (49648, 38250029, "498092fe0b3e1ecc73a985d51e46728114502e38c191f95b4b2f2f1445f4233e", "4228b5a06dd5bfa325bfecda2702fb67e0af007554b4e2f6712b3a51fcbce85e"),
    ("202b", "emar_medication_detail_bridge"): (48825, 84901924, "5ebcf437404b27bc4a97fff8733a62ad4433ddffc49af806c11be4b95c33d0d8", "cce944d7cff62c6ccf3cdc8dd653c1b4516294cf9a6b208831d9e5c54f6e0317"),
    ("202b", "emar_medication_head_partition"): (5045, 40687720, "810050005b995e2c5545b96a8f66588c9a8af9ed190490404557b115eee43e4b", "ba45eaacd8c36b947baa13d57d779eec34f5686ae5c02948ee3b188a47fdcdf6"),
    ("202c", "detail_pharmacy_prescription_bridge"): (285516, 46152769, "ae93a8ef4cc2323d446fa46d9d1906bd94ffdf72352258f421d62cf84f4a4ef9", "8299a39b27ed7f277a259a17eb2d9cbbd3002b7737c6ee4d003cbb6853bb385a"),
    ("202c", "head_pharmacy_prescription_bridge"): (172567, 38758346, "3f3cf1362c235846281be8ecb237c658917a924c30f87267e5b0e4b9973583ed", "1de3c43b69ec96fd90d43c5ce9c82d5af4184dc790c191b898e250f18842011f"),
    ("202c", "ndc_external_mapping_input"): (189348, 20259179, "37a0f1e6854c44ac805737bfdc777e4338c12e1a681c15e595945f0d1068f121", "0a9e17658c2b8db566289bef1a7729e573b3ed52f5bcfb6d05a280c1a6299c48"),
    ("202c", "pharmacy_no_prescription_component"): (89, 30504, "7c03bb9d1fab5db66641e5a840e542696d8368909c96a590daa7549c454cba6e", "e59e4db772a475ec8bb53634d5935eefc3b8f2e3e4fee7b6b72d56a5e2ce1ece"),
    ("202c", "pharmacy_prescription_bridge"): (236630, 20292611, "f149d62b86ddd726f7aa313f14414d2832bdfedad6e2d049f70202f18d36ab89", "b592b40eda6fadef369d8d5a970f434c7dfbe5b539dd822af358f1edf69d3c88"),
    ("202c", "pharmacy_product_context"): (717377, 17809529, "78c74457e5e5b7f33b6cadc078327b97be12145fc16636c234817283905dd3f9", "1db32cd0eb0c4cf81a5bc5aa1e43b91682682d2a7a9fa6cb4dae053c6410ab33"),
    ("202c", "prescription_identifier_context"): (208209, 20292611, "6832faad82b24e1be86484c24891e73d08c901359da1ec80ce609664179f01c1", "909f820e74e3524e49eae7285b41f6f89ce28298d47f03f851281f10512ef5f0"),
}
EXPECTED_STAGE_SUMMARIES = {
    "202b": (241097, 248741597, "9875e7157f1c4d453eb97c8a0d767a759e14bc7aeb93a00007421db749839048", "b323af112e6e4d992ca714a4a04e3225daf4b941d201ee3f9d8d9a4f81cfc4f6"),
    "202c": (1809736, 163595549, "b9a8a2ef7a15b8fb6fd2e82541b51cb26028859881fc379005e401bcdc0ed8ed", "a57edbba179631910f530dfddb288e1c992bd3ee940813020da9791386c7b0d0"),
}

SEMANTIC_BINDINGS = {
    ("202b", "detail_product_context"): (
        ("product_description", "mimiciv_hosp.emar_detail.product_description"),
        ("product_description_other", "mimiciv_hosp.emar_detail.product_description_other"),
    ),
    ("202b", "detail_seed_membership_bridge"): (
        ("product_description", "mimiciv_hosp.emar_detail.product_description"),
        ("product_description_other", "mimiciv_hosp.emar_detail.product_description_other"),
    ),
    ("202b", "emar_medication_detail_bridge"): (
        ("head_medication", "mimiciv_hosp.emar.medication"),
        ("product_description", "mimiciv_hosp.emar_detail.product_description"),
        ("product_description_other", "mimiciv_hosp.emar_detail.product_description_other"),
    ),
    ("202b", "emar_medication_head_partition"): (
        ("head_medication", "mimiciv_hosp.emar.medication"),
    ),
    ("202c", "detail_pharmacy_prescription_bridge"): (
        ("product_description", "mimiciv_hosp.emar_detail.product_description"),
        ("product_description_other", "mimiciv_hosp.emar_detail.product_description_other"),
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
    ("202b", "detail_product_context"): (("route", "mimiciv_hosp.emar_detail.route"),),
    ("202b", "detail_seed_membership_bridge"): (("route", "mimiciv_hosp.emar_detail.route"),),
    ("202b", "emar_medication_detail_bridge"): (("route", "mimiciv_hosp.emar_detail.route"),),
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
    ("202c", "ndc_external_mapping_input"): (("route", "mimiciv_hosp.prescriptions.route"),),
    ("202c", "pharmacy_no_prescription_component"): (("route", "mimiciv_hosp.pharmacy.route"),),
    ("202c", "pharmacy_prescription_bridge"): (
        ("pharmacy_route", "mimiciv_hosp.pharmacy.route"),
        ("route", "mimiciv_hosp.prescriptions.route"),
    ),
    ("202c", "pharmacy_product_context"): (("route", "mimiciv_hosp.pharmacy.route"),),
    ("202c", "prescription_identifier_context"): (("route", "mimiciv_hosp.prescriptions.route"),),
}
NDC_BINDINGS = {
    key: (("ndc", "mimiciv_hosp.prescriptions.ndc"),)
    for key in ALL_KIND_ORDER
    if "ndc" in TUPLE_FIELDS[key[0]][key[1]]
}

FALSE_GUARDS = {
    "adjudication_input_compiled": False,
    "adjudication_input_audited": False,
    "semantic_review_complete": False,
    "reviewed_semantic_ledger_frozen": False,
    "route_review_complete": False,
    "route_mapping_frozen": False,
    "ndc_mode_frozen": False,
    "external_ndc_mapping_executed": False,
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
    "llm_called": False,
}


class AdjudicationInputError(RuntimeError):
    """Fail-closed private input, lineage, schema, or conservation error."""


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(READ_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_snapshot(
    path: Path,
    label: str,
    expected_identity: tuple[int, int] | None = None,
) -> dict[str, Any]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise AdjudicationInputError(f"{label} is not one regular file.")
        digest = hashlib.sha256()
        byte_count = 0
        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            byte_count += len(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        linked = path.lstat()
    except AdjudicationInputError:
        raise
    except OSError:
        raise AdjudicationInputError(f"{label} could not be read safely.") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    stable_fields = (
        "st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns"
    )
    identity = (after.st_dev, after.st_ino)
    if (
        any(getattr(before, key) != getattr(after, key) for key in stable_fields)
        or not stat.S_ISREG(linked.st_mode)
        or (linked.st_dev, linked.st_ino) != identity
        or linked.st_size != after.st_size
        or byte_count != after.st_size
        or (expected_identity is not None and identity != expected_identity)
    ):
        raise AdjudicationInputError(f"{label} changed while it was checked.")
    return {
        "sha256": digest.hexdigest(),
        "bytes": byte_count,
        "mode": format(stat.S_IMODE(after.st_mode), "04o"),
        "identity": identity,
    }


def _mode(path: Path) -> str:
    return format(stat.S_IMODE(path.stat().st_mode), "04o")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AdjudicationInputError("A JSON object contains a duplicate key.")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> None:
    raise AdjudicationInputError("A JSON document contains a non-finite number.")


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if not path.is_file() or path.is_symlink():
        raise AdjudicationInputError(f"{label} is not one regular file.")
    if _mode(path) != "0600":
        raise AdjudicationInputError(f"{label} has an unsafe file mode.")
    size = path.stat().st_size
    if not 0 < size <= MAX_JSON_FILE_BYTES:
        raise AdjudicationInputError(f"{label} exceeds its byte contract.")
    raw = path.read_bytes()
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except AdjudicationInputError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdjudicationInputError(f"{label} is not unique-key JSON.") from None
    if not isinstance(value, dict):
        raise AdjudicationInputError(f"{label} is not one JSON object.")
    return value, raw


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise AdjudicationInputError(f"{label} has an unexpected schema.")
    return value


def _canonical_json_line(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _display_path(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _validated_time(value: str | None) -> str:
    result = _now() if value is None else value
    if not isinstance(result, str) or UTC_RE.fullmatch(result) is None:
        raise AdjudicationInputError("created_at_utc must be a strict UTC timestamp ending in Z.")
    try:
        parsed = datetime.fromisoformat(result[:-1] + "+00:00")
    except ValueError as exc:
        raise AdjudicationInputError("created_at_utc is not a real UTC timestamp.") from exc
    if parsed > datetime.now(timezone.utc):
        raise AdjudicationInputError("created_at_utc cannot be in the future.")
    return result


def _stamp(value: str) -> str:
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    return parsed.strftime("%Y%m%dT%H%M%S.%fZ")


class _PrivateNdjsonReader:
    """Single-member gzip reader with bounded lines and unique-key JSON."""

    def __init__(self, path: Path, expected_identity: tuple[int, int]):
        if not path.is_file() or path.is_symlink():
            raise AdjudicationInputError("The Query-202 private artifact is not regular.")
        self.path = path
        self.expected_identity = expected_identity
        self.stored_sha256 = hashlib.sha256()
        self.stored_bytes = 0
        self.raw_sha256 = hashlib.sha256()
        self.raw_bytes = 0
        self.records = 0

    def __iter__(self) -> Iterator[dict[str, Any]]:
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        buffer = bytearray()
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(self.path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or (before.st_dev, before.st_ino) != self.expected_identity
                or stat.S_IMODE(before.st_mode) != 0o600
            ):
                raise AdjudicationInputError(
                    "The Query-202 private artifact changed before streaming."
                )
            while True:
                chunk = handle.read(READ_CHUNK_BYTES)
                if not chunk:
                    break
                self.stored_sha256.update(chunk)
                self.stored_bytes += len(chunk)
                try:
                    output = decompressor.decompress(chunk)
                except zlib.error as exc:
                    raise AdjudicationInputError(
                        "The Query-202 private artifact has an invalid gzip stream."
                    ) from None
                if decompressor.unused_data:
                    raise AdjudicationInputError(
                        "The Query-202 private artifact has multiple members or trailing data."
                    )
                if output:
                    self.raw_sha256.update(output)
                    self.raw_bytes += len(output)
                    if self.raw_bytes > max(
                        SOURCE_BYTES["private_values_raw"], MAX_NDJSON_LINE_BYTES
                    ):
                        raise AdjudicationInputError(
                            "The Query-202 private artifact exceeds its raw byte contract."
                        )
                    buffer.extend(output)
                    while True:
                        position = buffer.find(b"\n")
                        if position < 0:
                            break
                        line = bytes(buffer[:position])
                        del buffer[: position + 1]
                        if not line or len(line) + 1 > MAX_NDJSON_LINE_BYTES:
                            raise AdjudicationInputError(
                                "The Query-202 private artifact has an invalid NDJSON line."
                            )
                        try:
                            value = json.loads(
                                line,
                                object_pairs_hook=_unique_object,
                                parse_constant=_reject_json_constant,
                            )
                        except AdjudicationInputError:
                            raise
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            raise AdjudicationInputError(
                                "The Query-202 private artifact is not unique-key NDJSON."
                            ) from None
                        if not isinstance(value, dict):
                            raise AdjudicationInputError(
                                "A Query-202 private record is not an object."
                            )
                        self.records += 1
                        if self.records > EXPECTED_PRIVATE_VALUES_RECORDS:
                            raise AdjudicationInputError(
                                "The Query-202 private artifact has too many records."
                            )
                        yield value
                    if len(buffer) > MAX_NDJSON_LINE_BYTES:
                        raise AdjudicationInputError(
                            "The Query-202 private artifact has an overlong NDJSON line."
                        )
            try:
                tail = decompressor.flush()
            except zlib.error as exc:
                raise AdjudicationInputError(
                    "The Query-202 private artifact has an invalid gzip trailer."
                ) from None
            if tail:
                self.raw_sha256.update(tail)
                self.raw_bytes += len(tail)
                buffer.extend(tail)
            if not decompressor.eof or decompressor.unused_data:
                raise AdjudicationInputError(
                    "The Query-202 private artifact is truncated or has trailing data."
                )
            after = os.fstat(handle.fileno())
            linked = self.path.lstat()
            stable_fields = (
                "st_dev", "st_ino", "st_mode", "st_size",
                "st_mtime_ns", "st_ctime_ns",
            )
            if (
                any(getattr(before, key) != getattr(after, key) for key in stable_fields)
                or not stat.S_ISREG(linked.st_mode)
                or (linked.st_dev, linked.st_ino) != self.expected_identity
                or self.stored_bytes != after.st_size
                or self.stored_bytes != SOURCE_BYTES["private_values"]
                or self.stored_sha256.hexdigest()
                != SOURCE_HASHES["private_values"]
            ):
                raise AdjudicationInputError(
                    "The Query-202 private artifact changed while streaming."
                )
        if buffer:
            raise AdjudicationInputError(
                "The Query-202 private artifact has an incomplete NDJSON line."
            )


class _RecordCursor:
    def __init__(self, reader: _PrivateNdjsonReader):
        self.reader = reader
        self.iterator = iter(reader)

    def take(self, record_type: str) -> dict[str, Any]:
        try:
            value = next(self.iterator)
        except StopIteration as exc:
            raise AdjudicationInputError(
                f"The Query-202 stream ended before {record_type}."
            ) from exc
        if value.get("record_type") != record_type:
            raise AdjudicationInputError(
                f"The Query-202 stream expected {record_type}."
            )
        return value

    def finish(self) -> None:
        try:
            next(self.iterator)
        except StopIteration:
            return
        raise AdjudicationInputError("The Query-202 stream has records after its footer.")


class _GzipNdjsonWriter:
    """Deterministic single-member gzip writer over one private temporary file."""

    def __init__(self, path: Path):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        self.path = path
        self._raw_handle: BinaryIO = os.fdopen(descriptor, "wb")
        os.fchmod(self._raw_handle.fileno(), 0o600)
        self._gzip = gzip.GzipFile(
            filename="", mode="wb", fileobj=self._raw_handle, compresslevel=6, mtime=0
        )
        self._raw_digest = hashlib.sha256()
        self.raw_bytes = 0
        self.records = 0
        self._finished = False

    def write(self, value: Mapping[str, Any]) -> None:
        if self._finished:
            raise AdjudicationInputError("A finished private stream was reused.")
        line = _canonical_json_line(value)
        if len(line) > MAX_NDJSON_LINE_BYTES:
            raise AdjudicationInputError("A compiled private NDJSON line is overlong.")
        self._gzip.write(line)
        self._raw_digest.update(line)
        self.raw_bytes += len(line)
        self.records += 1

    def finish(self) -> dict[str, Any]:
        if self._finished:
            raise AdjudicationInputError("A private stream was finished twice.")
        self._gzip.close()
        self._raw_handle.flush()
        os.fsync(self._raw_handle.fileno())
        written = os.fstat(self._raw_handle.fileno())
        written_identity = (written.st_dev, written.st_ino)
        self._raw_handle.close()
        self._finished = True
        snapshot = _file_snapshot(
            self.path,
            "A compiled private stream",
            expected_identity=written_identity,
        )
        if snapshot["mode"] != "0600":
            raise AdjudicationInputError("A compiled private stream has an unsafe mode.")
        return {
            "file": self.path.name,
            "encoding": ARTIFACT_ENCODING,
            "sha256": snapshot["sha256"],
            "bytes": snapshot["bytes"],
            "raw_sha256": self._raw_digest.hexdigest(),
            "raw_bytes": self.raw_bytes,
            "records": self.records,
            "_identity": snapshot["identity"],
        }

    def abort(self) -> None:
        if self._finished:
            return
        try:
            self._gzip.close()
        except BaseException:
            pass
        try:
            self._raw_handle.close()
        except BaseException:
            pass
        self._finished = True


def _write_json_file(path: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    raw = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    written_identity: tuple[int, int] | None = None
    try:
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
            written = os.fstat(handle.fileno())
            written_identity = (written.st_dev, written.st_ino)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    if written_identity is None:
        raise AdjudicationInputError("A compiled JSON artifact was not written.")
    snapshot = _file_snapshot(
        path,
        "A compiled JSON artifact",
        expected_identity=written_identity,
    )
    if (
        snapshot["mode"] != "0600"
        or snapshot["bytes"] != len(raw)
        or snapshot["sha256"] != hashlib.sha256(raw).hexdigest()
    ):
        raise AdjudicationInputError("A compiled JSON artifact changed after writing.")
    return {
        "file": path.name,
        "sha256": snapshot["sha256"],
        "bytes": snapshot["bytes"],
        "_identity": snapshot["identity"],
    }


def _typed_boundary_hash(source_field: str, records: list[dict[str, Any]]) -> str:
    field = source_field.encode("utf-8")
    null_seen = False
    nonnull: list[bytes] = []
    for record in records:
        if record["raw_is_null"] is True:
            if null_seen:
                raise AdjudicationInputError("A boundary repeats SQL NULL.")
            null_seen = True
        else:
            nonnull.append(record["raw_value"].encode("utf-8"))
    if len(nonnull) != len(set(nonnull)):
        raise AdjudicationInputError("A boundary repeats a nonnull exact value.")
    digest = hashlib.sha256(BOUNDARY_SET_VERSION)
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


def _semantic_hash(keys: list[tuple[str, str]]) -> str:
    ordered = sorted(keys, key=lambda item: (item[0].encode(), item[1].encode()))
    if len(ordered) != len(set(ordered)):
        raise AdjudicationInputError("The semantic seed contains duplicate keys.")
    digest = hashlib.sha256(SEMANTIC_SET_VERSION)
    digest.update(struct.pack(">Q", len(ordered)))
    for field, raw in ordered:
        field_bytes = field.encode("utf-8")
        raw_bytes = raw.encode("utf-8")
        digest.update(struct.pack(">I", len(field_bytes)))
        digest.update(field_bytes)
        digest.update(struct.pack(">Q", len(raw_bytes)))
        digest.update(raw_bytes)
    return digest.hexdigest()


def _route_canonical_hash(values: list[str]) -> str:
    encoded = sorted(value.encode("utf-8") for value in values)
    if len(encoded) != len(set(encoded)):
        raise AdjudicationInputError("The canonical route set has duplicate values.")
    digest = hashlib.sha256(ROUTE_CANONICAL_SET_VERSION)
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


def _tuple_hashers(stage_label: str, count: int) -> tuple[Any, Any]:
    label = stage_label.encode("utf-8")
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
    set_digest.update(struct.pack(">Q", len(encoded)))
    set_digest.update(encoded)
    frequency_digest.update(struct.pack(">Q", len(encoded)))
    frequency_digest.update(encoded)
    frequency_digest.update(struct.pack(">Q", multiplicity))


def _header(
    artifact_type: str,
    created: str,
    lineage: Mapping[str, Any],
    component_lineage: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "record_type": "header",
        "schema_version": 1,
        "artifact_type": artifact_type,
        "artifact_encoding": ARTIFACT_ENCODING,
        "created_at_utc": created,
        "component_id": COMPONENT_ID,
        "component_lineage": dict(component_lineage),
        "input_lineage": dict(lineage),
        "privacy": {
            "contains_exact_raw_local_values": True,
            "contains_patient_admission_event_or_order_identifiers": False,
            "contains_event_or_order_timestamps": False,
            "external_api_called": False,
        },
        "guards": dict(FALSE_GUARDS),
    }


def _privacy() -> dict[str, bool]:
    return {
        "private_raw_values_persisted": True,
        "public_raw_values_emitted": False,
        "patient_admission_event_or_order_identifiers_persisted": False,
        "event_or_order_timestamps_persisted": False,
        "external_api_called": False,
    }


def _resolve(root: Path, value: Path | str | None, default: Path) -> Path:
    candidate = default if value is None else Path(value)
    return candidate if candidate.is_absolute() else root / candidate


def _configured_project_path(root: Path, value: Path, label: str) -> Path:
    resolved_root = root.resolve()
    configured = Path(value)
    if configured.is_absolute():
        normalized = configured.resolve(strict=False)
        try:
            relative = normalized.relative_to(resolved_root)
        except ValueError as exc:
            raise AdjudicationInputError(f"{label} must remain inside the project root.") from exc
    else:
        if ".." in configured.parts:
            raise AdjudicationInputError(f"{label} contains a parent escape.")
        relative = configured
    current = resolved_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise AdjudicationInputError(f"{label} contains a symbolic link.")
    resolved = (resolved_root / relative).resolve(strict=False)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise AdjudicationInputError(f"{label} must remain inside the project root.") from exc
    return resolved


def _load_preregistration_report(root: Path) -> dict[str, Any]:
    return query202_adjudication_input_preregistration_report(root)


def _component_lineage(root: Path) -> dict[str, Any]:
    report = _load_preregistration_report(root)
    bundles = report.get("implementation_bundles")
    if (
        report.get("component_id") != COMPONENT_ID
        or report.get("status") != "frozen_for_execution"
        or report.get("execution_status") != "not_executed"
        or report.get("execution_permitted") is not True
        or report.get("valid") is not True
        or report.get("freeze_ready") is not True
        or not isinstance(report.get("config_sha256"), str)
        or not isinstance(bundles, dict)
        or not isinstance(bundles.get("compiler"), str)
        or not isinstance(bundles.get("auditor"), str)
    ):
        raise AdjudicationInputError(
            "The adjudication-input preregistration is not frozen for execution."
        )
    return {
        "component_id": COMPONENT_ID,
        "config": str(COMPONENT_CONFIG_PATH),
        "config_sha256": report["config_sha256"],
        "status_at_execution": "frozen_for_execution",
        "compiler_bundle_sha256": bundles["compiler"],
        "auditor_bundle_sha256": bundles["auditor"],
    }


def _is_git_ignored(root: Path, path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root.resolve())
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


def _validate_output_parent(root: Path, parent: Path) -> Path:
    resolved_root = root.resolve()
    unresolved = parent if parent.is_absolute() else root / parent
    try:
        normalized = unresolved.resolve(strict=False)
        relative = normalized.relative_to(resolved_root)
    except ValueError as exc:
        raise AdjudicationInputError(
            "The adjudication output parent must remain inside the project root."
        ) from exc
    if (
        not relative.parts
        or relative.parts[0] != "artifacts"
        or ".." in relative.parts
    ):
        raise AdjudicationInputError(
            "The adjudication output parent must be under project artifacts/."
        )
    frozen_parent = _configured_project_path(
        resolved_root,
        DEFAULT_OUTPUT_PARENT,
        "The frozen adjudication output parent",
    )
    if normalized != frozen_parent:
        raise AdjudicationInputError(
            "The adjudication output parent differs from the frozen contract."
        )
    current = resolved_root
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise AdjudicationInputError(
                "The adjudication output path contains a symbolic link."
            )
    normalized.mkdir(parents=True, exist_ok=True, mode=0o700)
    resolved = normalized.resolve()
    if not resolved.is_dir() or resolved.is_symlink():
        raise AdjudicationInputError("The adjudication output parent is unsafe.")
    resolved.chmod(0o700)
    if not _is_git_ignored(root, resolved):
        raise AdjudicationInputError(
            "The adjudication output parent is not excluded by Git."
        )
    return resolved


def _output_parent_identity(path: Path) -> tuple[int, int]:
    value = path.lstat()
    if (
        not stat.S_ISDIR(value.st_mode)
        or path.is_symlink()
        or stat.S_IMODE(value.st_mode) != 0o700
    ):
        raise AdjudicationInputError("The adjudication output parent is unsafe.")
    return value.st_dev, value.st_ino


def _recheck_output_parent(
    root: Path,
    parent: Path,
    expected_identity: tuple[int, int],
) -> None:
    frozen_parent = _configured_project_path(
        root,
        DEFAULT_OUTPUT_PARENT,
        "The frozen adjudication output parent",
    )
    if (
        parent.resolve(strict=False) != frozen_parent
        or _output_parent_identity(parent) != expected_identity
        or not _is_git_ignored(root, parent)
    ):
        raise AdjudicationInputError(
            "The adjudication output parent changed during compilation."
        )


def _validate_input_lineage(root: Path, directory: Path) -> dict[str, Any]:
    if not directory.is_dir() or directory.is_symlink() or _mode(directory) != "0700":
        raise AdjudicationInputError("The Query-202 input directory is unsafe.")
    manifest_path = directory / "manifest.json"
    audit_path = directory / "audit-summary.json"
    manifest, manifest_raw = _read_json(manifest_path, "Query-202 manifest")
    audit, audit_raw = _read_json(audit_path, "Query-202 audit")
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    audit_sha = hashlib.sha256(audit_raw).hexdigest()
    if manifest_sha != SOURCE_HASHES["manifest"]:
        raise AdjudicationInputError("The frozen Query-202 manifest hash changed.")
    if audit_sha != SOURCE_HASHES["audit"]:
        raise AdjudicationInputError("The frozen Query-202 audit hash changed.")
    if manifest.get("status") != "complete":
        raise AdjudicationInputError("The Query-202 manifest is not complete.")
    queries = manifest.get("queries")
    if not isinstance(queries, list) or len(queries) != 1 or not isinstance(queries[0], dict):
        raise AdjudicationInputError("The Query-202 manifest query inventory changed.")
    query = queries[0]
    if query.get("query") != INPUT_QUERY or query.get("status") != "complete":
        raise AdjudicationInputError("The Query-202 manifest query is incomplete.")
    preregistration = manifest.get("component_preregistration")
    if not isinstance(preregistration, dict):
        raise AdjudicationInputError("The Query-202 preregistration lineage is absent.")
    if (
        preregistration.get("component_id") != INPUT_COMPONENT_ID
        or preregistration.get("config_sha256") != SOURCE_HASHES["config"]
    ):
        raise AdjudicationInputError("The Query-202 preregistration lineage changed.")
    expected_query_values = {
        "private_values_persisted": True,
        "private_values_encoding": ARTIFACT_ENCODING,
        "private_values_sha256": SOURCE_HASHES["private_values"],
        "private_values_bytes": SOURCE_BYTES["private_values"],
        "private_values_raw_sha256": SOURCE_HASHES["private_values_raw"],
        "private_values_raw_bytes": SOURCE_BYTES["private_values_raw"],
        "private_values_records": EXPECTED_PRIVATE_VALUES_RECORDS,
    }
    if any(query.get(key) != value for key, value in expected_query_values.items()):
        raise AdjudicationInputError("The Query-202 private artifact manifest changed.")
    private_name = query.get("private_values_file")
    if not isinstance(private_name, str) or Path(private_name).name != private_name:
        raise AdjudicationInputError("The Query-202 private artifact name is unsafe.")
    private_path = directory / private_name
    private_snapshot = _file_snapshot(
        private_path, "The frozen Query-202 private artifact"
    )
    if (
        private_snapshot["mode"] != "0600"
        or private_snapshot["bytes"] != SOURCE_BYTES["private_values"]
        or private_snapshot["sha256"] != SOURCE_HASHES["private_values"]
    ):
        raise AdjudicationInputError("The frozen Query-202 private artifact changed.")
    if audit.get("status") != "passed" or audit.get("query") != INPUT_QUERY:
        raise AdjudicationInputError("The Query-202 independent audit did not pass.")
    checks = audit.get("checks")
    recomputed = audit.get("recomputed")
    if (
        not isinstance(checks, dict)
        or checks.get("failed") != 0
        or checks.get("failed_names") != []
        or not isinstance(recomputed, dict)
        or recomputed.get("manifest_sha256") != manifest_sha
        or recomputed.get("config_sha256") != SOURCE_HASHES["config"]
        or recomputed.get("semantic_seed_keys") != EXPECTED_SEMANTIC_KEY_COUNT
        or recomputed.get("semantic_seed_key_set_sha256")
        != EXPECTED_SEMANTIC_KEY_SET_SHA256
    ):
        raise AdjudicationInputError("The Query-202 independent audit lineage changed.")

    aggregate_name = query.get("aggregate_summary_file")
    if not isinstance(aggregate_name, str) or Path(aggregate_name).name != aggregate_name:
        raise AdjudicationInputError("The Query-202 aggregate summary name is unsafe.")
    aggregate_path = directory / aggregate_name
    aggregate, aggregate_raw = _read_json(aggregate_path, "Query-202 aggregate summary")
    if (
        query.get("aggregate_summary_persisted") is not True
        or query.get("aggregate_summary_bytes") != SOURCE_BYTES["aggregate_summary"]
        or len(aggregate_raw) != SOURCE_BYTES["aggregate_summary"]
        or query.get("aggregate_summary_sha256") != SOURCE_HASHES["aggregate_summary"]
        or hashlib.sha256(aggregate_raw).hexdigest() != SOURCE_HASHES["aggregate_summary"]
    ):
        raise AdjudicationInputError("The Query-202 aggregate summary changed.")

    config_name = preregistration.get("config")
    if not isinstance(config_name, str):
        raise AdjudicationInputError("The Query-202 config path is absent.")
    config_relative = Path(config_name)
    if config_relative.is_absolute() or ".." in config_relative.parts:
        raise AdjudicationInputError("The Query-202 config path is unsafe.")
    config_path = root / config_relative
    if (
        not config_path.is_file()
        or config_path.is_symlink()
        or _sha_file(config_path) != SOURCE_HASHES["config"]
    ):
        raise AdjudicationInputError("The frozen Query-202 config changed.")

    executed_name = query.get("executed_sql_file")
    if not isinstance(executed_name, str) or Path(executed_name).name != executed_name:
        raise AdjudicationInputError("The Query-202 executed SQL name is unsafe.")
    executed_path = directory / executed_name
    if (
        query.get("executed_sql_persisted") is not True
        or query.get("executed_sql_bytes") != SOURCE_BYTES["executed_sql"]
        or query.get("executed_sql_sha256") != SOURCE_HASHES["executed_sql"]
        or not executed_path.is_file()
        or executed_path.is_symlink()
        or _mode(executed_path) != "0600"
        or executed_path.stat().st_size != SOURCE_BYTES["executed_sql"]
        or _sha_file(executed_path) != SOURCE_HASHES["executed_sql"]
    ):
        raise AdjudicationInputError("The frozen Query-202 executed SQL changed.")
    seed_summary = aggregate.get("semantic_seed_summary")
    if (
        not isinstance(seed_summary, dict)
        or seed_summary.get("key_count") != EXPECTED_SEMANTIC_KEY_COUNT
        or seed_summary.get("key_set_sha256") != EXPECTED_SEMANTIC_KEY_SET_SHA256
    ):
        raise AdjudicationInputError("The Query-202 aggregate seed summary changed.")
    crosswalk = aggregate.get("crosswalk_summaries")
    if not isinstance(crosswalk, dict) or set(crosswalk) != {"202b", "202c"}:
        raise AdjudicationInputError("The Query-202 aggregate crosswalk inventory changed.")
    for stage, expected in EXPECTED_STAGE_SUMMARIES.items():
        item = crosswalk.get(stage)
        if not isinstance(item, dict) or (
            item.get("unique_tuples"),
            item.get("global_output_multiplicity"),
            item.get("global_tuple_set_sha256"),
            item.get("global_tuple_frequency_sha256"),
        ) != expected:
            raise AdjudicationInputError("A Query-202 stage aggregate changed.")
        kinds = item.get("tuple_kind_summaries")
        if not isinstance(kinds, dict) or set(kinds) != set(TUPLE_FIELDS[stage]):
            raise AdjudicationInputError("A Query-202 tuple-kind inventory changed.")
        for kind, summary in kinds.items():
            expected_kind = EXPECTED_KIND_SUMMARIES[(stage, kind)]
            if not isinstance(summary, dict) or (
                summary.get("unique_tuples"),
                summary.get("total_multiplicity"),
                summary.get("global_tuple_set_sha256"),
                summary.get("global_tuple_frequency_sha256"),
            ) != expected_kind:
                raise AdjudicationInputError("A Query-202 tuple-kind aggregate changed.")
    return {
        "manifest": manifest,
        "audit": audit,
        "aggregate": aggregate,
        "query": query,
        "private_path": private_path,
        "private_identity": private_snapshot["identity"],
        "input_lineage": {
            "component_id": INPUT_COMPONENT_ID,
            "config_sha256": SOURCE_HASHES["config"],
            "manifest_sha256": manifest_sha,
            "audit_sha256": audit_sha,
            "private_values_sha256": SOURCE_HASHES["private_values"],
            "private_values_raw_sha256": SOURCE_HASHES["private_values_raw"],
            "aggregate_summary_sha256": SOURCE_HASHES["aggregate_summary"],
            "executed_sql_sha256": SOURCE_HASHES["executed_sql"],
            "semantic_seed_key_set_sha256": EXPECTED_SEMANTIC_KEY_SET_SHA256,
        },
        "input_directory": _display_path(root, directory),
    }


def _parse_boundaries(cursor: _RecordCursor) -> dict[str, dict[str, Any]]:
    boundaries: dict[str, dict[str, Any]] = {}
    metadata_keys = {
        "stage", "source_field", "semantic_seed_field", "sql_null_rows",
        "typed_distinct_values", "nonnull_distinct_values", "source_rows",
        "nonnull_set_sha256", "typed_set_sha256",
    }
    record_keys = {"raw_is_null", "raw_value", "raw_utf8_bytes", "exact_row_count"}
    for source_key, source_field, stage, semantic in BOUNDARY_SPECS:
        begin = _exact_keys(
            cursor.take("boundary_begin"),
            {"record_type", "source_key", "metadata"},
            f"boundary {source_key} begin",
        )
        if begin["source_key"] != source_key:
            raise AdjudicationInputError("The boundary stream order changed.")
        metadata = _exact_keys(begin["metadata"], metadata_keys, "boundary metadata")
        if (
            metadata["stage"] != stage
            or metadata["source_field"] != source_field
            or metadata["semantic_seed_field"] is not semantic
        ):
            raise AdjudicationInputError("A boundary identity changed.")
        typed_count = metadata["typed_distinct_values"]
        if type(typed_count) is not int or typed_count < 0:
            raise AdjudicationInputError("A boundary count is invalid.")
        records: list[dict[str, Any]] = []
        previous: tuple[int, bytes] | None = None
        source_rows = 0
        nonnull = 0
        null_rows = 0
        for _ in range(typed_count):
            wrapper = _exact_keys(
                cursor.take("boundary_value"),
                {"record_type", "source_key", "value"},
                "boundary value wrapper",
            )
            if wrapper["source_key"] != source_key:
                raise AdjudicationInputError("A boundary value changed source.")
            value = _exact_keys(wrapper["value"], record_keys, "boundary value")
            count = value["exact_row_count"]
            byte_count = value["raw_utf8_bytes"]
            if type(count) is not int or not 1 <= count <= MAX_COUNT:
                raise AdjudicationInputError("A boundary frequency is invalid.")
            if value["raw_is_null"] is True:
                if value["raw_value"] is not None or byte_count != 0:
                    raise AdjudicationInputError("A boundary SQL NULL is malformed.")
                order_key = (0, b"")
                null_rows += count
            elif value["raw_is_null"] is False and isinstance(value["raw_value"], str):
                raw = value["raw_value"].encode("utf-8")
                if b"\x00" in raw or len(raw) > MAX_VALUE_UTF8_BYTES or byte_count != len(raw):
                    raise AdjudicationInputError("A boundary exact value is malformed.")
                order_key = (1, raw)
                nonnull += 1
            else:
                raise AdjudicationInputError("A boundary typed state is malformed.")
            if previous is not None and order_key <= previous:
                raise AdjudicationInputError("A boundary is not strictly sorted.")
            previous = order_key
            source_rows += count
            if source_rows > MAX_COUNT:
                raise AdjudicationInputError("A boundary denominator overflowed.")
            records.append(dict(value))
        end = _exact_keys(
            cursor.take("boundary_end"),
            {"record_type", "source_key", "records"},
            "boundary end",
        )
        typed_hash = _typed_boundary_hash(source_field, records)
        expected = EXPECTED_BOUNDARIES[source_key]
        if (
            end["source_key"] != source_key
            or end["records"] != typed_count
            or (typed_count, nonnull, typed_hash) != expected
            or metadata["nonnull_distinct_values"] != nonnull
            or metadata["sql_null_rows"] != null_rows
            or metadata["source_rows"] != source_rows
            or metadata["typed_set_sha256"] != typed_hash
        ):
            raise AdjudicationInputError(
                f"The frozen Query-202 boundary changed for {source_key}."
            )
        boundaries[source_key] = {
            "source_field": source_field,
            "records": records,
            "metadata": dict(metadata),
        }
    return boundaries


def _route_review_records(
    boundaries: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, dict[str, str]]:
    by_raw: dict[bytes, list[dict[str, Any]]] = {}
    null_inputs: list[dict[str, Any]] = []
    typed_hashes: dict[str, str] = {}
    for source_key, source_field, field_role in ROUTE_SOURCE_SPECS:
        source = boundaries[source_key]
        typed_hashes[source_key] = source["metadata"]["typed_set_sha256"]
        for record in source["records"]:
            if record["raw_is_null"]:
                null_inputs.append({
                    "source_key": source_key,
                    "source_field": source_field,
                    "field_role": field_role,
                    "exact_row_count": record["exact_row_count"],
                })
            else:
                raw = record["raw_value"].encode("utf-8")
                by_raw.setdefault(raw, []).append({
                    "source_key": source_key,
                    "source_field": source_field,
                    "field_role": field_role,
                    "exact_row_count": record["exact_row_count"],
                })
    canonical: list[dict[str, Any]] = []
    memberships: list[dict[str, Any]] = []
    for index, raw in enumerate(sorted(by_raw), start=1):
        review_id = f"R{index:06d}"
        canonical.append({
            "record_type": "canonical_route_review",
            "canonical_review_id": review_id,
            "exact_raw_value": raw.decode("utf-8"),
            "raw_utf8_bytes": len(raw),
            "decision": "unknown",
            "review_status": "unreviewed",
            "decision_basis": None,
            "reviewer_id": None,
            "reviewed_at_utc": None,
        })
        for membership in by_raw[raw]:
            memberships.append({
                "record_type": "route_source_membership",
                "source_key": membership["source_key"],
                "source_field": membership["source_field"],
                "field_role": membership["field_role"],
                "raw_value_state": "nonnull",
                "exact_raw_value": raw.decode("utf-8"),
                "exact_row_count": membership["exact_row_count"],
                "decision": "unknown",
                "route_state": "unknown",
                "sets_has_unknown": True,
                "decision_provenance": "default_unknown_unreviewed",
                "canonical_review_id": review_id,
                "review_status": "unreviewed",
                "decision_basis": None,
                "reviewer_id": None,
                "reviewed_at_utc": None,
            })
    for membership in null_inputs:
        memberships.append({
            "record_type": "route_source_membership",
            "source_key": membership["source_key"],
            "source_field": membership["source_field"],
            "field_role": membership["field_role"],
            "raw_value_state": "sql_null",
            "exact_raw_value": None,
            "exact_row_count": membership["exact_row_count"],
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
        b"" if item["exact_raw_value"] is None else item["exact_raw_value"].encode("utf-8"),
    ))
    canonical_hash = _route_canonical_hash(
        [item["exact_raw_value"] for item in canonical]
    )
    if (
        len(canonical) != EXPECTED_ROUTE_CANONICAL_COUNT
        or sum(item["raw_value_state"] == "nonnull" for item in memberships)
        != EXPECTED_ROUTE_NONNULL_MEMBERSHIPS
        or sum(item["raw_value_state"] == "sql_null" for item in memberships)
        != EXPECTED_ROUTE_NULL_MEMBERSHIPS
        or len(memberships) != EXPECTED_ROUTE_TYPED_MEMBERSHIPS
    ):
        raise AdjudicationInputError("The frozen route review universe changed.")
    return canonical, memberships, canonical_hash, typed_hashes


def _write_route_review(
    writer: _GzipNdjsonWriter,
    created: str,
    lineage: Mapping[str, Any],
    component_lineage: Mapping[str, Any],
    boundaries: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    canonical, memberships, canonical_hash, typed_hashes = _route_review_records(boundaries)
    writer.write(_header(
        "potassium_query202_route_review_template",
        created,
        lineage,
        component_lineage,
    ))
    writer.write({
        "record_type": "route_review_begin",
        "canonical_exact_nonnull_values": len(canonical),
        "source_specific_nonnull_memberships": sum(
            item["raw_value_state"] == "nonnull" for item in memberships
        ),
        "source_specific_sql_null_memberships": sum(
            item["raw_value_state"] == "sql_null" for item in memberships
        ),
        "source_specific_typed_memberships": len(memberships),
        "typed_set_sha256": typed_hashes,
    })
    for record in canonical:
        writer.write(record)
    for record in memberships:
        writer.write(record)
    writer.write({
        "record_type": "route_review_end",
        "canonical_records": len(canonical),
        "source_membership_records": len(memberships),
        "canonical_exact_set_sha256": canonical_hash,
    })
    writer.write({
        "record_type": "footer",
        "records_before_footer": writer.records,
        "section_counts": {
            "canonical_route_reviews": len(canonical),
            "route_source_memberships": len(memberships),
        },
    })
    artifact = writer.finish()
    summary = {
        "canonical_exact_nonnull_values": len(canonical),
        "source_specific_nonnull_memberships": EXPECTED_ROUTE_NONNULL_MEMBERSHIPS,
        "source_specific_sql_null_memberships": EXPECTED_ROUTE_NULL_MEMBERSHIPS,
        "source_specific_typed_memberships": EXPECTED_ROUTE_TYPED_MEMBERSHIPS,
        "canonical_exact_set_sha256": canonical_hash,
        "typed_set_sha256": typed_hashes,
    }
    return artifact, summary


def _validate_input_header(
    cursor: _RecordCursor, lineage: Mapping[str, Any]
) -> dict[str, Any]:
    header = _exact_keys(
        cursor.take("header"),
        {
            "record_type", "artifact_encoding", "schema_version", "query",
            "created_at_utc", "component_lineage", "transaction",
            "hash_contracts", "privacy", "guards",
        },
        "Query-202 header",
    )
    component = header["component_lineage"]
    transaction = header["transaction"]
    privacy = header["privacy"]
    guards = header["guards"]
    if (
        header["artifact_encoding"] != ARTIFACT_ENCODING
        or header["schema_version"] != 2
        or header["query"] != INPUT_QUERY
        or not isinstance(component, dict)
        or component.get("component_id") != INPUT_COMPONENT_ID
        or component.get("config_sha256") != lineage["config_sha256"]
        or not isinstance(transaction, dict)
        or transaction.get("isolation") != "repeatable read"
        or transaction.get("read_only") is not True
        or transaction.get("same_snapshot") is not True
        or transaction.get("rollback_confirmed_before_persistence") is not True
        or transaction.get("clean_psql_exit_confirmed_before_persistence") is not True
        or not isinstance(privacy, dict)
        or privacy.get("contains_patient_admission_event_or_order_identifiers") is not False
        or privacy.get("contains_event_or_order_timestamps") is not False
        or privacy.get("external_api_called") is not False
        or not isinstance(guards, dict)
        or any(value is not False for value in guards.values())
    ):
        raise AdjudicationInputError("The Query-202 private header changed.")
    return header


def _seed_keys(
    boundaries: Mapping[str, Mapping[str, Any]],
) -> tuple[list[tuple[str, str]], dict[tuple[str, str], int]]:
    keys: list[tuple[str, str]] = []
    counts: dict[tuple[str, str], int] = {}
    for source_key, source_field, _stage, semantic in BOUNDARY_SPECS:
        if not semantic:
            continue
        for record in boundaries[source_key]["records"]:
            if record["raw_is_null"]:
                continue
            key = (source_field, record["raw_value"])
            keys.append(key)
            counts[key] = record["exact_row_count"]
    keys.sort(key=lambda item: (item[0].encode("utf-8"), item[1].encode("utf-8")))
    if (
        len(keys) != EXPECTED_SEMANTIC_KEY_COUNT
        or _semantic_hash(keys) != EXPECTED_SEMANTIC_KEY_SET_SHA256
    ):
        raise AdjudicationInputError("The frozen semantic review universe changed.")
    return keys, counts


def _write_and_validate_semantic_seed(
    cursor: _RecordCursor,
    writer: _GzipNdjsonWriter,
    created: str,
    lineage: Mapping[str, Any],
    component_lineage: Mapping[str, Any],
    boundaries: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], set[tuple[str, str]]]:
    keys, exact_counts = _seed_keys(boundaries)
    begin = _exact_keys(
        cursor.take("semantic_seed_begin"),
        {
            "record_type", "key_count", "key_set_sha256",
            "sql_null_keys_included", "review_decisions_included",
        },
        "semantic seed begin",
    )
    if (
        begin["key_count"] != len(keys)
        or begin["key_set_sha256"] != EXPECTED_SEMANTIC_KEY_SET_SHA256
        or begin["sql_null_keys_included"] is not False
        or begin["review_decisions_included"] is not False
    ):
        raise AdjudicationInputError("The Query-202 semantic seed header changed.")
    writer.write(_header(
        "potassium_query202_semantic_review_template",
        created,
        lineage,
        component_lineage,
    ))
    writer.write({
        "record_type": "semantic_review_begin",
        "key_count": len(keys),
        "key_set_sha256": EXPECTED_SEMANTIC_KEY_SET_SHA256,
        "semantic_dimensions": list(SEMANTIC_DIMENSIONS),
    })
    for expected in keys:
        record = _exact_keys(
            cursor.take("semantic_seed_value"),
            {"record_type", "source_field", "exact_raw_value"},
            "semantic seed value",
        )
        observed = (record["source_field"], record["exact_raw_value"])
        if observed != expected:
            raise AdjudicationInputError("The Query-202 semantic seed records changed.")
        writer.write({
            "record_type": "semantic_review_key",
            "source_field": expected[0],
            "exact_raw_value": expected[1],
            "exact_row_count": exact_counts[expected],
            "review_status": "unreviewed",
            "semantic_decisions": {
                dimension: "uncertain" for dimension in SEMANTIC_DIMENSIONS
            },
            "mapping_group_id": None,
            "decision_basis": None,
            "reviewer_id": None,
            "reviewed_at_utc": None,
        })
    end = _exact_keys(
        cursor.take("semantic_seed_end"),
        {"record_type", "records"},
        "semantic seed end",
    )
    if end["records"] != len(keys):
        raise AdjudicationInputError("The Query-202 semantic seed footer changed.")
    writer.write({
        "record_type": "semantic_review_end",
        "records": len(keys),
        "key_set_sha256": EXPECTED_SEMANTIC_KEY_SET_SHA256,
    })
    writer.write({
        "record_type": "footer",
        "records_before_footer": writer.records,
        "section_counts": {"semantic_review_keys": len(keys)},
    })
    return writer.finish(), set(keys)


def _typed_boundary_sets(
    boundaries: Mapping[str, Mapping[str, Any]],
) -> dict[str, set[str | None]]:
    result: dict[str, set[str | None]] = {}
    for source_key, source_field, _stage, _semantic in BOUNDARY_SPECS:
        values: set[str | None] = set()
        for record in boundaries[source_key]["records"]:
            values.add(None if record["raw_is_null"] else record["raw_value"])
        result[source_field] = values
    return result


def _validate_tuple_bindings(
    stage: str,
    kind: str,
    value: Mapping[str, str | None],
    semantic_keys: set[tuple[str, str]],
    boundary_sets: Mapping[str, set[str | None]],
) -> None:
    binding_key = (stage, kind)
    for payload_field, source_field in SEMANTIC_BINDINGS[binding_key]:
        raw = value[payload_field]
        if raw is not None and (source_field, raw) not in semantic_keys:
            raise AdjudicationInputError(
                "A crosswalk semantic value is outside the frozen seed."
            )
    for payload_field, source_field in ROUTE_BINDINGS[binding_key]:
        if value[payload_field] not in boundary_sets[source_field]:
            raise AdjudicationInputError(
                "A crosswalk route value is outside its typed boundary."
            )
    for payload_field, source_field in NDC_BINDINGS.get(binding_key, ()):
        if value[payload_field] not in boundary_sets[source_field]:
            raise AdjudicationInputError(
                "A crosswalk NDC value is outside its typed boundary."
            )
    if binding_key == ("202b", "detail_seed_membership_bridge"):
        source_field = value["seed_source_field"]
        raw = value["seed_exact_raw_value"]
        expected_field = {
            "mimiciv_hosp.emar_detail.product_description": "product_description",
            "mimiciv_hosp.emar_detail.product_description_other":
                "product_description_other",
        }.get(source_field)
        if (
            expected_field is None
            or not isinstance(raw, str)
            or value[expected_field] != raw
            or (source_field, raw) not in semantic_keys
        ):
            raise AdjudicationInputError(
                "A detail seed-membership bridge is inconsistent."
            )
    if binding_key == NDC_KIND and not isinstance(value.get("ndc"), str):
        raise AdjudicationInputError("An external NDC handoff candidate is SQL NULL.")


def _kind_begin_record(stage: str, kind: str, ndc: bool = False) -> dict[str, Any]:
    unique, multiplicity, set_hash, frequency_hash = EXPECTED_KIND_SUMMARIES[(stage, kind)]
    return {
        "record_type": "ndc_handoff_begin" if ndc else "evidence_kind_begin",
        "stage": stage,
        "tuple_kind": kind,
        "unique_tuples": unique,
        "total_multiplicity": multiplicity,
        "global_tuple_set_sha256": set_hash,
        "global_tuple_frequency_sha256": frequency_hash,
    }


def _kind_end_record(
    stage: str, kind: str, records: int, total: int, ndc: bool = False
) -> dict[str, Any]:
    expected = EXPECTED_KIND_SUMMARIES[(stage, kind)]
    return {
        "record_type": "ndc_handoff_end" if ndc else "evidence_kind_end",
        "stage": stage,
        "tuple_kind": kind,
        "records": records,
        "total_multiplicity": total,
        "global_tuple_set_sha256": expected[2],
        "global_tuple_frequency_sha256": expected[3],
    }


def _process_crosswalks(
    cursor: _RecordCursor,
    local_writer: _GzipNdjsonWriter,
    ndc_writer: _GzipNdjsonWriter,
    created: str,
    lineage: Mapping[str, Any],
    component_lineage: Mapping[str, Any],
    semantic_keys: set[tuple[str, str]],
    boundaries: Mapping[str, Mapping[str, Any]],
    boundary_sets: Mapping[str, set[str | None]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    local_writer.write(
        _header(
            "potassium_query202_local_adjudication_evidence",
            created,
            lineage,
            component_lineage,
        )
    )
    ndc_writer.write(_header(
        "potassium_query202_ndc_handoff",
        created,
        lineage,
        component_lineage,
    ))
    ndc_boundary = boundaries["prescriptions_ndc"]
    ndc_nonnull = [
        record for record in ndc_boundary["records"] if not record["raw_is_null"]
    ]
    ndc_null = [
        record for record in ndc_boundary["records"] if record["raw_is_null"]
    ]
    if len(ndc_nonnull) != EXPECTED_BOUNDARIES["prescriptions_ndc"][1] or len(ndc_null) != 1:
        raise AdjudicationInputError("The NDC typed boundary changed.")
    ndc_writer.write({
        "record_type": "ndc_candidates_begin",
        "candidate_count": len(ndc_nonnull),
        "source_field": "mimiciv_hosp.prescriptions.ndc",
        "nonnull_set_sha256": ndc_boundary["metadata"]["nonnull_set_sha256"],
        "typed_set_sha256": ndc_boundary["metadata"]["typed_set_sha256"],
    })
    for record in ndc_nonnull:
        ndc_writer.write({
            "record_type": "ndc_candidate",
            "source_field": "mimiciv_hosp.prescriptions.ndc",
            "exact_raw_value": record["raw_value"],
            "raw_utf8_bytes": record["raw_utf8_bytes"],
            "exact_row_count": record["exact_row_count"],
        })
    ndc_writer.write({
        "record_type": "ndc_null_boundary",
        "source_field": "mimiciv_hosp.prescriptions.ndc",
        "sql_null_rows": ndc_null[0]["exact_row_count"],
    })
    ndc_writer.write({
        "record_type": "ndc_candidates_end",
        "candidate_records": len(ndc_nonnull),
        "null_boundary_records": 1,
    })
    begin_metadata_keys = {
        "bucket_count", "bucket_indices_complete", "assignment_unit",
        "sql_null_subject_bucket", "bucket_assignment_violations",
        "null_subject_outside_bucket_zero", "global_input_rows",
        "global_input_rows_source", "summed_bucket_input_rows",
        "global_output_multiplicity", "mutual_exclusion_and_completeness_confirmed",
        "unique_tuples", "tuple_kind_summaries",
    }
    begin_kind_keys = {
        "unique_tuples", "total_multiplicity", "summed_bucket_input_rows",
        "summed_bucket_tuple_multiplicity",
    }
    kind_summary_output: dict[str, dict[str, Any]] = {}
    local_unique = local_total = local_kind_count = 0
    ndc_unique = ndc_total = 0

    for stage in ("202b", "202c"):
        begin = _exact_keys(
            cursor.take("crosswalk_begin"),
            {"record_type", "stage", "metadata"},
            f"{stage} crosswalk begin",
        )
        if begin["stage"] != stage:
            raise AdjudicationInputError("The crosswalk stage order changed.")
        metadata = _exact_keys(begin["metadata"], begin_metadata_keys, "crosswalk metadata")
        stage_expected = EXPECTED_STAGE_SUMMARIES[stage]
        if (
            metadata["bucket_count"] != 64
            or metadata["bucket_indices_complete"] is not True
            or metadata["assignment_unit"] != "subject_id"
            or metadata["sql_null_subject_bucket"] != 0
            or metadata["bucket_assignment_violations"] != 0
            or metadata["null_subject_outside_bucket_zero"] != 0
            or metadata["global_output_multiplicity"] != stage_expected[1]
            or metadata["unique_tuples"] != stage_expected[0]
            or metadata["mutual_exclusion_and_completeness_confirmed"] is not True
        ):
            raise AdjudicationInputError("A frozen crosswalk stage control changed.")
        declared_kinds = metadata["tuple_kind_summaries"]
        if not isinstance(declared_kinds, dict) or set(declared_kinds) != set(TUPLE_FIELDS[stage]):
            raise AdjudicationInputError("A crosswalk tuple-kind inventory changed.")
        for kind, declared in declared_kinds.items():
            declared = _exact_keys(declared, begin_kind_keys, "tuple-kind metadata")
            expected = EXPECTED_KIND_SUMMARIES[(stage, kind)]
            if (
                declared["unique_tuples"] != expected[0]
                or declared["total_multiplicity"] != expected[1]
                or declared["summed_bucket_input_rows"] != expected[1]
                or declared["summed_bucket_tuple_multiplicity"] != expected[1]
            ):
                raise AdjudicationInputError("A tuple-kind declaration changed.")

        stage_hashers = _tuple_hashers(stage, stage_expected[0])
        kind_hashers = {
            kind: _tuple_hashers(stage + ":" + kind, EXPECTED_KIND_SUMMARIES[(stage, kind)][0])
            for kind in TUPLE_FIELDS[stage]
        }
        kind_counts = {kind: 0 for kind in TUPLE_FIELDS[stage]}
        kind_totals = {kind: 0 for kind in TUPLE_FIELDS[stage]}
        previous_encoded: bytes | None = None
        observed_order: list[str] = []
        active_kind: str | None = None

        def close_active() -> None:
            nonlocal active_kind
            if active_kind is None:
                return
            count = kind_counts[active_kind]
            total = kind_totals[active_kind]
            if (stage, active_kind) == NDC_KIND:
                ndc_writer.write(
                    _kind_end_record(stage, active_kind, count, total, ndc=True)
                )
            else:
                local_writer.write(
                    _kind_end_record(stage, active_kind, count, total, ndc=False)
                )
            active_kind = None

        for _ in range(stage_expected[0]):
            record = _exact_keys(
                cursor.take("crosswalk_tuple"),
                {"record_type", "stage", "tuple_kind", "tuple", "multiplicity"},
                "crosswalk tuple",
            )
            kind = record["tuple_kind"]
            value = record["tuple"]
            multiplicity = record["multiplicity"]
            if record["stage"] != stage or kind not in TUPLE_FIELDS[stage]:
                raise AdjudicationInputError("A crosswalk tuple identity changed.")
            expected_fields = TUPLE_FIELDS[stage][kind]
            if (
                not isinstance(value, dict)
                or set(value) != set(expected_fields)
                or list(value) != sorted(expected_fields, key=lambda item: item.encode("utf-8"))
                or not all(item is None or isinstance(item, str) for item in value.values())
                or type(multiplicity) is not int
                or not 1 <= multiplicity <= MAX_COUNT
            ):
                raise AdjudicationInputError("A crosswalk tuple is malformed.")
            encoded = _encode_tuple(stage, kind, value)
            if previous_encoded is not None and encoded <= previous_encoded:
                raise AdjudicationInputError("A crosswalk stage is not strictly sorted.")
            previous_encoded = encoded
            if active_kind != kind:
                close_active()
                if kind in observed_order:
                    raise AdjudicationInputError("A tuple kind is not contiguous.")
                observed_order.append(kind)
                active_kind = kind
                if (stage, kind) == NDC_KIND:
                    ndc_writer.write(_kind_begin_record(stage, kind, ndc=True))
                else:
                    local_writer.write(_kind_begin_record(stage, kind, ndc=False))
            if kind_counts[kind] >= EXPECTED_KIND_SUMMARIES[(stage, kind)][0]:
                raise AdjudicationInputError("A tuple kind has too many records.")
            if kind_totals[kind] > MAX_COUNT - multiplicity:
                raise AdjudicationInputError("A tuple-kind multiplicity overflowed.")
            _validate_tuple_bindings(
                stage, kind, value, semantic_keys, boundary_sets
            )
            _update_tuple_hashers(stage_hashers, encoded, multiplicity)
            _update_tuple_hashers(kind_hashers[kind], encoded, multiplicity)
            kind_counts[kind] += 1
            kind_totals[kind] += multiplicity
            if (stage, kind) == NDC_KIND:
                ndc_writer.write({
                    "record_type": "ndc_context",
                    "tuple": value,
                    "multiplicity": multiplicity,
                })
                ndc_unique += 1
                ndc_total += multiplicity
            else:
                local_writer.write({
                    "record_type": "evidence_tuple",
                    "stage": stage,
                    "tuple_kind": kind,
                    "tuple": value,
                    "multiplicity": multiplicity,
                })
                local_unique += 1
                local_total += multiplicity
        close_active()
        # The frozen tuple encoding length-prefixes tuple_kind before its bytes;
        # therefore bytewise encoded order compares the uint32 length first.
        expected_order = sorted(
            TUPLE_FIELDS[stage],
            key=lambda item: (len(item.encode("utf-8")), item.encode("utf-8")),
        )
        if observed_order != expected_order:
            raise AdjudicationInputError("The tuple-kind encoded order changed.")

        end = _exact_keys(
            cursor.take("crosswalk_end"),
            {
                "record_type", "stage", "records", "global_tuple_set_sha256",
                "global_tuple_frequency_sha256", "tuple_kind_hashes",
            },
            "crosswalk end",
        )
        observed_stage_hashes = (
            stage_hashers[0].hexdigest(), stage_hashers[1].hexdigest()
        )
        if (
            end["stage"] != stage
            or end["records"] != stage_expected[0]
            or observed_stage_hashes != stage_expected[2:]
            or end["global_tuple_set_sha256"] != observed_stage_hashes[0]
            or end["global_tuple_frequency_sha256"] != observed_stage_hashes[1]
        ):
            raise AdjudicationInputError("A frozen crosswalk stage hash changed.")
        stored_kind_hashes = end["tuple_kind_hashes"]
        if not isinstance(stored_kind_hashes, dict) or set(stored_kind_hashes) != set(TUPLE_FIELDS[stage]):
            raise AdjudicationInputError("A crosswalk end kind inventory changed.")
        for kind in expected_order:
            expected = EXPECTED_KIND_SUMMARIES[(stage, kind)]
            observed_hashes = (
                kind_hashers[kind][0].hexdigest(),
                kind_hashers[kind][1].hexdigest(),
            )
            stored = _exact_keys(
                stored_kind_hashes[kind],
                {"global_tuple_set_sha256", "global_tuple_frequency_sha256"},
                "tuple-kind end hashes",
            )
            if (
                kind_counts[kind] != expected[0]
                or kind_totals[kind] != expected[1]
                or observed_hashes != expected[2:]
                or stored["global_tuple_set_sha256"] != observed_hashes[0]
                or stored["global_tuple_frequency_sha256"] != observed_hashes[1]
            ):
                raise AdjudicationInputError("A frozen tuple-kind hash changed.")
            output_stream = "ndc_handoff" if (stage, kind) == NDC_KIND else "local_evidence"
            if output_stream == "local_evidence":
                local_kind_count += 1
            kind_summary_output[stage + ":" + kind] = {
                "stage": stage,
                "tuple_kind": kind,
                "unique_tuples": expected[0],
                "total_multiplicity": expected[1],
                "global_tuple_set_sha256": expected[2],
                "global_tuple_frequency_sha256": expected[3],
                "output_stream": output_stream,
            }

    expected_local_unique = sum(
        EXPECTED_KIND_SUMMARIES[item][0] for item in LOCAL_KIND_ORDER
    )
    expected_local_total = sum(
        EXPECTED_KIND_SUMMARIES[item][1] for item in LOCAL_KIND_ORDER
    )
    expected_ndc = EXPECTED_KIND_SUMMARIES[NDC_KIND]
    if (
        local_kind_count != len(LOCAL_KIND_ORDER)
        or local_unique != expected_local_unique
        or local_total != expected_local_total
        or ndc_unique != expected_ndc[0]
        or ndc_total != expected_ndc[1]
    ):
        raise AdjudicationInputError("Compiled stream conservation failed.")
    local_writer.write({
        "record_type": "footer",
        "records_before_footer": local_writer.records,
        "section_counts": {
            "tuple_kinds": local_kind_count,
            "evidence_tuples": local_unique,
            "total_multiplicity": local_total,
        },
    })
    ndc_writer.write({
        "record_type": "footer",
        "records_before_footer": ndc_writer.records,
        "section_counts": {
            "ndc_candidates": len(ndc_nonnull),
            "ndc_null_boundaries": 1,
            "ndc_contexts": ndc_unique,
            "total_multiplicity": ndc_total,
        },
    })
    return (
        local_writer.finish(),
        ndc_writer.finish(),
        kind_summary_output,
    )


def _conservation(
    route_summary: Mapping[str, Any], kind_summaries: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "semantic_review_keys": EXPECTED_SEMANTIC_KEY_COUNT,
        "semantic_seed_key_set_sha256": EXPECTED_SEMANTIC_KEY_SET_SHA256,
        "route_canonical_exact_nonnull_values": route_summary[
            "canonical_exact_nonnull_values"
        ],
        "route_source_specific_nonnull_memberships": route_summary[
            "source_specific_nonnull_memberships"
        ],
        "route_source_specific_sql_null_memberships": route_summary[
            "source_specific_sql_null_memberships"
        ],
        "route_source_specific_typed_memberships": route_summary[
            "source_specific_typed_memberships"
        ],
        "input_crosswalk_unique_tuples": {
            stage: EXPECTED_STAGE_SUMMARIES[stage][0] for stage in ("202b", "202c")
        },
        "input_crosswalk_total_multiplicity": {
            stage: EXPECTED_STAGE_SUMMARIES[stage][1] for stage in ("202b", "202c")
        },
        "local_evidence_unique_tuples": sum(
            EXPECTED_KIND_SUMMARIES[item][0] for item in LOCAL_KIND_ORDER
        ),
        "local_evidence_total_multiplicity": sum(
            EXPECTED_KIND_SUMMARIES[item][1] for item in LOCAL_KIND_ORDER
        ),
        "ndc_handoff_unique_tuples": EXPECTED_KIND_SUMMARIES[NDC_KIND][0],
        "ndc_handoff_total_multiplicity": EXPECTED_KIND_SUMMARIES[NDC_KIND][1],
        "ndc_candidate_values": EXPECTED_BOUNDARIES["prescriptions_ndc"][1],
        "ndc_null_boundaries": 1,
        "tuple_kind_summaries": dict(kind_summaries),
    }


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _install_termination_handlers() -> list[tuple[int, Any]]:
    installed: list[tuple[int, Any]] = []

    def interrupt(signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt(f"termination signal {signum}")

    try:
        for name in ("SIGTERM", "SIGHUP"):
            signum = getattr(signal, name, None)
            if signum is None:
                continue
            previous = signal.getsignal(signum)
            signal.signal(signum, interrupt)
            installed.append((signum, previous))
    except (OSError, ValueError):
        for signum, previous in reversed(installed):
            try:
                signal.signal(signum, previous)
            except (OSError, ValueError):
                pass
        return []
    return installed


def _restore_termination_handlers(installed: list[tuple[int, Any]]) -> None:
    for signum, previous in reversed(installed):
        try:
            signal.signal(signum, previous)
        except (OSError, ValueError):
            pass


def _validate_output_inventory(
    directory: Path,
    expected_artifacts: Mapping[str, Mapping[str, Any]],
    expected_directory_identity: tuple[int, int],
) -> None:
    directory_stat = directory.lstat()
    if (
        not stat.S_ISDIR(directory_stat.st_mode)
        or directory.is_symlink()
        or stat.S_IMODE(directory_stat.st_mode) != 0o700
        or (directory_stat.st_dev, directory_stat.st_ino)
        != expected_directory_identity
    ):
        raise AdjudicationInputError(
            "The adjudication output directory changed before commit."
        )
    entries = list(directory.iterdir())
    if (
        len(entries) != len(expected_artifacts)
        or {entry.name for entry in entries} != set(expected_artifacts)
    ):
        raise AdjudicationInputError("The adjudication output inventory changed.")
    for entry in entries:
        artifact = expected_artifacts[entry.name]
        identity = artifact.get("_identity")
        if (
            not isinstance(identity, tuple)
            or len(identity) != 2
            or any(type(item) is not int for item in identity)
        ):
            raise AdjudicationInputError(
                "An adjudication output lost its write identity."
            )
        snapshot = _file_snapshot(
            entry,
            "An adjudication output",
            expected_identity=identity,
        )
        if (
            snapshot["mode"] != "0600"
            or snapshot["bytes"] != artifact["bytes"]
            or snapshot["sha256"] != artifact["sha256"]
        ):
            raise AdjudicationInputError(
                "An adjudication output changed before atomic commit."
            )


def compile_adjudication_input(
    root: Path,
    input_directory: Path | str | None = None,
    output_parent: Path | str | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Compile one immutable, audited Query-202 A artifact into four streams.

    No database or network connection is opened.  The returned object contains
    aggregate metadata only; controlled values remain inside 0600 files under
    a 0700 artifact directory.
    """
    root = Path(root).resolve()
    component_lineage = _component_lineage(root)
    created = _validated_time(created_at_utc)
    expected_source_directory = _configured_project_path(
        root,
        SOURCE_ARTIFACT_DIRECTORY,
        "The frozen Query-202 input directory",
    )
    source_directory = _resolve(
        root, input_directory, SOURCE_ARTIFACT_DIRECTORY
    ).resolve()
    if source_directory != expected_source_directory:
        raise AdjudicationInputError(
            "The Query-202 input directory is not the frozen artifact directory."
        )
    input_state = _validate_input_lineage(root, source_directory)
    lineage = input_state["input_lineage"]

    parent = _validate_output_parent(
        root, _resolve(root, output_parent, DEFAULT_OUTPUT_PARENT)
    )
    parent_identity = _output_parent_identity(parent)
    final_directory = parent / _stamp(created)
    if final_directory.exists() or final_directory.is_symlink():
        raise AdjudicationInputError("The adjudication artifact directory already exists.")
    temporary_directory = Path(tempfile.mkdtemp(prefix=".compile-", dir=parent))
    temporary_directory.chmod(0o700)
    temporary_stat = temporary_directory.lstat()
    temporary_identity = (temporary_stat.st_dev, temporary_stat.st_ino)
    writers: list[_GzipNdjsonWriter] = []
    termination_handlers: list[tuple[int, Any]] = []
    try:
        termination_handlers = _install_termination_handlers()
        semantic_writer = _GzipNdjsonWriter(
            temporary_directory / SEMANTIC_REVIEW_FILE
        )
        local_writer = _GzipNdjsonWriter(temporary_directory / LOCAL_EVIDENCE_FILE)
        route_writer = _GzipNdjsonWriter(temporary_directory / ROUTE_REVIEW_FILE)
        ndc_writer = _GzipNdjsonWriter(temporary_directory / NDC_HANDOFF_FILE)
        writers.extend((semantic_writer, local_writer, route_writer, ndc_writer))

        reader = _PrivateNdjsonReader(
            input_state["private_path"], input_state["private_identity"]
        )
        cursor = _RecordCursor(reader)
        _validate_input_header(cursor, lineage)
        boundaries = _parse_boundaries(cursor)
        boundary_value_count = sum(
            len(boundaries[key]["records"]) for key, *_rest in BOUNDARY_SPECS
        )
        route_artifact, route_summary = _write_route_review(
            route_writer, created, lineage, component_lineage, boundaries
        )
        semantic_artifact, semantic_keys = _write_and_validate_semantic_seed(
            cursor,
            semantic_writer,
            created,
            lineage,
            component_lineage,
            boundaries,
        )
        local_artifact, ndc_artifact, kind_summaries = _process_crosswalks(
            cursor,
            local_writer,
            ndc_writer,
            created,
            lineage,
            component_lineage,
            semantic_keys,
            boundaries,
            _typed_boundary_sets(boundaries),
        )
        footer = _exact_keys(
            cursor.take("footer"),
            {"record_type", "records_before_footer", "section_records"},
            "Query-202 footer",
        )
        expected_section_records = {
            "boundary_values": boundary_value_count,
            "semantic_seed_values": EXPECTED_SEMANTIC_KEY_COUNT,
            "crosswalk_tuples": sum(
                EXPECTED_STAGE_SUMMARIES[stage][0] for stage in ("202b", "202c")
            ),
        }
        if (
            footer["records_before_footer"] != reader.records - 1
            or footer["section_records"] != expected_section_records
        ):
            raise AdjudicationInputError("The Query-202 stream footer changed.")
        cursor.finish()
        if (
            reader.records != EXPECTED_PRIVATE_VALUES_RECORDS
            or reader.raw_bytes != SOURCE_BYTES["private_values_raw"]
            or reader.raw_sha256.hexdigest() != SOURCE_HASHES["private_values_raw"]
        ):
            raise AdjudicationInputError("The Query-202 decompressed artifact changed.")

        outputs = {
            "semantic_review_template": semantic_artifact,
            "local_evidence": local_artifact,
            "route_review_template": route_artifact,
            "ndc_handoff": ndc_artifact,
        }
        conservation = _conservation(route_summary, kind_summaries)
        privacy = _privacy()
        output_hashes = {
            name: {
                key: outputs[name][key]
                for key in (
                    "file", "sha256", "bytes", "raw_sha256", "raw_bytes",
                    "records", "encoding"
                )
            }
            for name in STREAM_NAMES
        }
        summary = {
            "schema_version": 1,
            "component_id": COMPONENT_ID,
            "status": "complete",
            "created_at_utc": created,
            "scope": "private_query202_adjudication_inputs_without_decisions",
            "component_lineage": dict(component_lineage),
            "input_lineage": dict(lineage),
            "output_hashes": output_hashes,
            "conservation": conservation,
            "privacy": privacy,
            "guards": dict(FALSE_GUARDS),
        }
        summary_artifact = _write_json_file(
            temporary_directory / AGGREGATE_SUMMARY_FILE, summary
        )
        final_display = _display_path(root, final_directory)
        manifest_outputs = {
            name: {
                key: value
                for key, value in artifact.items()
                if not key.startswith("_")
            }
            for name, artifact in outputs.items()
        }
        manifest_outputs["aggregate_summary"] = {
            key: value
            for key, value in summary_artifact.items()
            if not key.startswith("_")
        }
        manifest = {
            "schema_version": 1,
            "component_id": COMPONENT_ID,
            "status": "complete",
            "created_at_utc": created,
            "finished_at_utc": _now(),
            "artifact_directory": final_display,
            "component_lineage": dict(component_lineage),
            "input_lineage": dict(lineage),
            "outputs": manifest_outputs,
            "conservation": conservation,
            "privacy": privacy,
            "guards": dict(FALSE_GUARDS),
        }
        manifest_artifact = _write_json_file(
            temporary_directory / MANIFEST_FILE, manifest
        )
        expected_artifacts = {
            artifact["file"]: artifact
            for artifact in (*outputs.values(), summary_artifact, manifest_artifact)
        }
        if set(expected_artifacts) != {
            SEMANTIC_REVIEW_FILE,
            LOCAL_EVIDENCE_FILE,
            ROUTE_REVIEW_FILE,
            NDC_HANDOFF_FILE,
            AGGREGATE_SUMMARY_FILE,
            MANIFEST_FILE,
        }:
            raise AdjudicationInputError("The adjudication output inventory changed.")
        _validate_output_inventory(
            temporary_directory, expected_artifacts, temporary_identity
        )
        rechecked = _validate_input_lineage(root, source_directory)
        if rechecked["input_lineage"] != lineage:
            raise AdjudicationInputError(
                "The Query-202 input lineage changed during compilation."
            )
        if _component_lineage(root) != component_lineage:
            raise AdjudicationInputError(
                "The adjudication-input component changed during compilation."
            )
        _validate_output_inventory(
            temporary_directory, expected_artifacts, temporary_identity
        )
        _recheck_output_parent(root, parent, parent_identity)
        _fsync_directory(temporary_directory)
        os.replace(temporary_directory, final_directory)
        _validate_output_inventory(
            final_directory, expected_artifacts, temporary_identity
        )
        _recheck_output_parent(root, parent, parent_identity)
        _fsync_directory(parent)
        return {
            "status": "complete",
            "component_id": COMPONENT_ID,
            "artifact_directory": final_display,
            "manifest": str(Path(final_display) / MANIFEST_FILE),
            "manifest_sha256": manifest_artifact["sha256"],
            "aggregate_summary": str(Path(final_display) / AGGREGATE_SUMMARY_FILE),
            "aggregate_summary_sha256": summary_artifact["sha256"],
            "semantic_review_keys": EXPECTED_SEMANTIC_KEY_COUNT,
            "local_evidence_unique_tuples": conservation[
                "local_evidence_unique_tuples"
            ],
            "ndc_handoff_unique_tuples": conservation["ndc_handoff_unique_tuples"],
            "route_canonical_exact_nonnull_values": conservation[
                "route_canonical_exact_nonnull_values"
            ],
            "guards": dict(FALSE_GUARDS),
        }
    except BaseException:
        for writer in writers:
            try:
                writer.abort()
            except BaseException:
                pass
        cleanup_target: Path | None = None
        unexpected_cleanup_entry = False
        for candidate in (temporary_directory, final_directory):
            try:
                candidate_stat = candidate.lstat()
            except FileNotFoundError:
                continue
            if (
                stat.S_ISDIR(candidate_stat.st_mode)
                and not candidate.is_symlink()
                and (candidate_stat.st_dev, candidate_stat.st_ino)
                == temporary_identity
            ):
                cleanup_target = candidate
                break
            unexpected_cleanup_entry = True
        if cleanup_target is not None:
            try:
                shutil.rmtree(cleanup_target)
                _fsync_directory(parent)
            except BaseException as cleanup_error:
                raise AdjudicationInputError(
                    "A failed adjudication compile could not remove private partial output."
                ) from cleanup_error
        elif unexpected_cleanup_entry:
            raise AdjudicationInputError(
                "A failed adjudication compile could not identify its private partial output."
            )
        raise
    finally:
        _restore_termination_handlers(termination_handlers)


__all__ = [
    "AdjudicationInputError",
    "ALL_KIND_ORDER",
    "BOUNDARY_SPECS",
    "COMPONENT_ID",
    "EXPECTED_BOUNDARIES",
    "EXPECTED_KIND_SUMMARIES",
    "EXPECTED_STAGE_SUMMARIES",
    "FALSE_GUARDS",
    "LOCAL_KIND_ORDER",
    "NDC_KIND",
    "SEMANTIC_DIMENSIONS",
    "SOURCE_ARTIFACT_DIRECTORY",
    "SOURCE_BYTES",
    "SOURCE_HASHES",
    "STREAM_FILES",
    "STREAM_NAMES",
    "TUPLE_FIELDS",
    "compile_adjudication_input",
]
