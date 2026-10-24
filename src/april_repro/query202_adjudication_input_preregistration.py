"""Freeze validation for the offline Query-202 adjudication-input compiler."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct
import tomllib
from typing import Any, Mapping, Sequence


CONFIG_PATH = Path(
    "config/preregistrations/d005_potassium_query202_adjudication_input.toml"
)
COMPONENT_ID = "D005-K-QUERY202-ADJUDICATION-INPUT-v1"
BUNDLE_ENCODING = "uint32be_path_length+path_utf8+uint64be_content_length+content"
PLACEHOLDER = "UNSET_REQUIRED_BEFORE_EXECUTION"
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")

EXPECTED_COMPILER_PATHS = (
    "src/april_repro/__init__.py",
    "src/april_repro/query202_adjudication_input_preregistration.py",
    "src/april_repro/query202_adjudication_input.py",
    "scripts/compile_potassium_query202_adjudication_input.py",
)
EXPECTED_AUDITOR_PATHS = (
    "src/april_repro/__init__.py",
    "src/april_repro/query202_adjudication_input_audit.py",
    "scripts/audit_potassium_query202_adjudication_input.py",
)
EXPECTED_IMPLEMENTATION_PATHS = {
    "compiler": EXPECTED_COMPILER_PATHS,
    "auditor": EXPECTED_AUDITOR_PATHS,
}

EXPECTED_INPUT_HASHES = {
    "config_sha256": "73004c1051970184b732b36a325e03c1f39e286356bcf56adbe799185e93ab73",
    "manifest_sha256": "3f8ecece96c5cb15e37ad8b7a539f6e3642cb2de8eac1bcec926b94c86579e30",
    "audit_sha256": "b44ec99e0499b7d427ad9ffb468bb73988bfb0d94d672736569831eb997992ec",
    "aggregate_summary_sha256": "b74dd5053fe8a81a33064500e1616de4eeaefed97192968a84ba102473c3c369",
    "executed_sql_sha256": "a98719c4b702fe9bde7aa877740ed0f6bb8305bd38d67072f8a5116bd4ed4fc3",
    "private_stored_sha256": "4b9f389574b4a8aafc823a7f78a139563f63c092f8eb91af76a2175b082ae5bf",
    "private_raw_sha256": "ac39e21906c65e4186b2174298a880bd7cd5e8b30f8f3d79c79954e69c35103e",
}

EXPECTED_OUTPUT = {
    "semantic_records": 34_565,
    "local_evidence_tuples": 1_861_485,
    "local_evidence_multiplicity": 392_077_967,
    "route_canonical_nonnull_values": 117,
    "route_nonnull_memberships": 233,
    "route_sql_null_memberships": 3,
    "route_typed_memberships": 236,
    "ndc_candidates": 6_589,
    "ndc_sql_null_boundary_records": 1,
    "ndc_context_tuples": 189_348,
    "ndc_context_multiplicity": 20_259_179,
}

EXPECTED_OUTPUT_FILES = {
    "semantic_file": "semantic-review-template.jsonl.gz",
    "local_evidence_file": "local-evidence.jsonl.gz",
    "route_file": "route-review-template.jsonl.gz",
    "ndc_file": "ndc-handoff.jsonl.gz",
    "summary_file": "aggregate-summary.json",
    "manifest_file": "manifest.json",
    "audit_file": "audit-summary.json",
}

EXPECTED_SEMANTIC_SEED = {
    "records": 34_565,
    "key_set_sha256": (
        "cee42c49d4618e6c62e99dcea26c53166f21305231b3c35991d2c2534b94368a"
    ),
    "sql_null_keys": 0,
}

EXPECTED_CROSSWALK = {
    "unique_tuples": 2_050_833,
    "total_multiplicity": 412_337_146,
    "stage_202b_unique_tuples": 241_097,
    "stage_202b_total_multiplicity": 248_741_597,
    "stage_202b_set_sha256": (
        "9875e7157f1c4d453eb97c8a0d767a759e14bc7aeb93a00007421db749839048"
    ),
    "stage_202b_frequency_sha256": (
        "b323af112e6e4d992ca714a4a04e3225daf4b941d201ee3f9d8d9a4f81cfc4f6"
    ),
    "stage_202c_unique_tuples": 1_809_736,
    "stage_202c_total_multiplicity": 163_595_549,
    "stage_202c_set_sha256": (
        "b9a8a2ef7a15b8fb6fd2e82541b51cb26028859881fc379005e401bcdc0ed8ed"
    ),
    "stage_202c_frequency_sha256": (
        "a57edbba179631910f530dfddb288e1c992bd3ee940813020da9791386c7b0d0"
    ),
}

EXPECTED_INPUT = {
    "artifact_directory": "artifacts/profiling/20261012T152323.460063Z",
    "component_id": "D005-K-QUERY202-PREADJUDICATION-EVIDENCE-v2",
    "config_file": (
        "config/preregistrations/"
        "d005_potassium_query202_pre_adjudication_v2.toml"
    ),
    "manifest_file": "manifest.json",
    "audit_file": "audit-summary.json",
    "aggregate_summary_file": (
        "potassium_query202_pre_adjudication.aggregate-summary.json"
    ),
    "executed_sql_file": "potassium_query202_pre_adjudication.executed.sql",
    "private_file": "potassium_query202_pre_adjudication.private.jsonl.gz",
    "private_stored_bytes": 35_008_612,
    "private_raw_bytes": 1_187_294_280,
    "private_records": 2_126_819,
    "audit_checks_total": 26_403,
    "audit_checks_passed": 26_403,
    "audit_checks_failed": 0,
    **EXPECTED_INPUT_HASHES,
    "semantic_seed": EXPECTED_SEMANTIC_SEED,
    "crosswalk": EXPECTED_CROSSWALK,
}

EXPECTED_TUPLE_KINDS = [
    {
        "stage": "202b",
        "name": "detail_product_context",
        "unique_tuples": 137_579,
        "total_multiplicity": 84_901_924,
        "set_sha256": (
            "f955faa531cd72e172bacd99625dcd215cfe063e7a3bbd26f0cb7fffb34925d9"
        ),
        "frequency_sha256": (
            "6debef0d4d367acefe6061c1619c08b5aa46596361a788781921e89a8a37dd55"
        ),
        "output_partition": "local_evidence",
    },
    {
        "stage": "202b",
        "name": "detail_seed_membership_bridge",
        "unique_tuples": 49_648,
        "total_multiplicity": 38_250_029,
        "set_sha256": (
            "498092fe0b3e1ecc73a985d51e46728114502e38c191f95b4b2f2f1445f4233e"
        ),
        "frequency_sha256": (
            "4228b5a06dd5bfa325bfecda2702fb67e0af007554b4e2f6712b3a51fcbce85e"
        ),
        "output_partition": "local_evidence",
    },
    {
        "stage": "202b",
        "name": "emar_medication_detail_bridge",
        "unique_tuples": 48_825,
        "total_multiplicity": 84_901_924,
        "set_sha256": (
            "5ebcf437404b27bc4a97fff8733a62ad4433ddffc49af806c11be4b95c33d0d8"
        ),
        "frequency_sha256": (
            "cce944d7cff62c6ccf3cdc8dd653c1b4516294cf9a6b208831d9e5c54f6e0317"
        ),
        "output_partition": "local_evidence",
    },
    {
        "stage": "202b",
        "name": "emar_medication_head_partition",
        "unique_tuples": 5_045,
        "total_multiplicity": 40_687_720,
        "set_sha256": (
            "810050005b995e2c5545b96a8f66588c9a8af9ed190490404557b115eee43e4b"
        ),
        "frequency_sha256": (
            "ba45eaacd8c36b947baa13d57d779eec34f5686ae5c02948ee3b188a47fdcdf6"
        ),
        "output_partition": "local_evidence",
    },
    {
        "stage": "202c",
        "name": "detail_pharmacy_prescription_bridge",
        "unique_tuples": 285_516,
        "total_multiplicity": 46_152_769,
        "set_sha256": (
            "ae93a8ef4cc2323d446fa46d9d1906bd94ffdf72352258f421d62cf84f4a4ef9"
        ),
        "frequency_sha256": (
            "8299a39b27ed7f277a259a17eb2d9cbbd3002b7737c6ee4d003cbb6853bb385a"
        ),
        "output_partition": "local_evidence",
    },
    {
        "stage": "202c",
        "name": "head_pharmacy_prescription_bridge",
        "unique_tuples": 172_567,
        "total_multiplicity": 38_758_346,
        "set_sha256": (
            "3f3cf1362c235846281be8ecb237c658917a924c30f87267e5b0e4b9973583ed"
        ),
        "frequency_sha256": (
            "1de3c43b69ec96fd90d43c5ce9c82d5af4184dc790c191b898e250f18842011f"
        ),
        "output_partition": "local_evidence",
    },
    {
        "stage": "202c",
        "name": "ndc_external_mapping_input",
        "unique_tuples": 189_348,
        "total_multiplicity": 20_259_179,
        "set_sha256": (
            "37a0f1e6854c44ac805737bfdc777e4338c12e1a681c15e595945f0d1068f121"
        ),
        "frequency_sha256": (
            "0a9e17658c2b8db566289bef1a7729e573b3ed52f5bcfb6d05a280c1a6299c48"
        ),
        "output_partition": "ndc_handoff",
    },
    {
        "stage": "202c",
        "name": "pharmacy_no_prescription_component",
        "unique_tuples": 89,
        "total_multiplicity": 30_504,
        "set_sha256": (
            "7c03bb9d1fab5db66641e5a840e542696d8368909c96a590daa7549c454cba6e"
        ),
        "frequency_sha256": (
            "e59e4db772a475ec8bb53634d5935eefc3b8f2e3e4fee7b6b72d56a5e2ce1ece"
        ),
        "output_partition": "local_evidence",
    },
    {
        "stage": "202c",
        "name": "pharmacy_prescription_bridge",
        "unique_tuples": 236_630,
        "total_multiplicity": 20_292_611,
        "set_sha256": (
            "f149d62b86ddd726f7aa313f14414d2832bdfedad6e2d049f70202f18d36ab89"
        ),
        "frequency_sha256": (
            "b592b40eda6fadef369d8d5a970f434c7dfbe5b539dd822af358f1edf69d3c88"
        ),
        "output_partition": "local_evidence",
    },
    {
        "stage": "202c",
        "name": "pharmacy_product_context",
        "unique_tuples": 717_377,
        "total_multiplicity": 17_809_529,
        "set_sha256": (
            "78c74457e5e5b7f33b6cadc078327b97be12145fc16636c234817283905dd3f9"
        ),
        "frequency_sha256": (
            "1db32cd0eb0c4cf81a5bc5aa1e43b91682682d2a7a9fa6cb4dae053c6410ab33"
        ),
        "output_partition": "local_evidence",
    },
    {
        "stage": "202c",
        "name": "prescription_identifier_context",
        "unique_tuples": 208_209,
        "total_multiplicity": 20_292_611,
        "set_sha256": (
            "6832faad82b24e1be86484c24891e73d08c901359da1ec80ce609664179f01c1"
        ),
        "frequency_sha256": (
            "909f820e74e3524e49eae7285b41f6f89ce28298d47f03f851281f10512ef5f0"
        ),
        "output_partition": "local_evidence",
    },
]

EXPECTED_OUTPUT_CONTRACT = {
    "artifact_parent": "artifacts/query202-adjudication-input",
    **EXPECTED_OUTPUT_FILES,
    "encoding": "gzip+utf8+ndjson-v1",
    "gzip_members": 1,
    "gzip_mtime": 0,
    "private_ndjson_canonical_json": (
        "sort_keys=true,separators=comma-colon,ensure_ascii=false,newline=true"
    ),
    **EXPECTED_OUTPUT,
}

EXPECTED_REVIEW_CONTRACT = {
    "semantic_dimensions": [
        "product_identity",
        "dosage_form",
        "treatment_intent",
        "potassium_content",
        "meq_convertibility",
    ],
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

EXPECTED_EXECUTION = {
    "database_access_allowed": False,
    "network_access_allowed": False,
    "external_api_allowed": False,
    "input_and_output_hashes_rechecked_before_success": True,
    "atomic_private_writes_required": True,
    "failure_keeps_private_partial_outputs": False,
}

EXPECTED_PRIVACY = {
    "directory_mode": "0700",
    "file_mode": "0600",
    "git_ignored_required": True,
    "private_raw_values_allowed": True,
    "public_raw_values_allowed": False,
    "public_per_value_hashes_allowed": False,
    "patient_admission_event_order_identifiers_allowed": False,
    "event_or_order_timestamps_allowed": False,
}

EXPECTED_GUARDS = {
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

EXPECTED_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "component_id",
        "decision_id",
        "status",
        "execution_status",
        "execution_permitted",
        "specified_on",
        "rule_version",
        "scope",
        "input",
        "tuple_kind",
        "output",
        "review_contract",
        "ndc_mode",
        "execution",
        "privacy",
        "implementation",
        "guards",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def implementation_bundle_sha256(root: Path, paths: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for relative in paths:
        encoded_path = relative.encode("utf-8")
        path = _project_regular_file(root, relative)
        if path is None:
            raise OSError(
                f"implementation path is not a regular project file: {relative}"
            )
        payload = path.read_bytes()
        digest.update(struct.pack(">I", len(encoded_path)))
        digest.update(encoded_path)
        digest.update(struct.pack(">Q", len(payload)))
        digest.update(payload)
    return digest.hexdigest()


def _parse_query202_adjudication_input_preregistration(
    payload: bytes,
) -> dict[str, Any]:
    return tomllib.loads(payload.decode("utf-8"))


def _read_query202_adjudication_input_preregistration_snapshot(
    root: Path,
) -> tuple[dict[str, Any], str]:
    path = _project_regular_file(root, str(CONFIG_PATH))
    if path is None:
        raise OSError("preregistration config is not a regular project file")
    payload = path.read_bytes()
    config = _parse_query202_adjudication_input_preregistration(payload)
    return config, hashlib.sha256(payload).hexdigest()


def read_query202_adjudication_input_preregistration(root: Path) -> dict[str, Any]:
    config, _config_sha256 = (
        _read_query202_adjudication_input_preregistration_snapshot(root)
    )
    return config


def _safe_relative(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _project_regular_file(root: Path, relative: object) -> Path | None:
    if not _safe_relative(relative) or root.is_symlink():
        return None
    try:
        resolved_root = root.resolve(strict=True)
    except OSError:
        return None
    candidate = root
    for part in Path(str(relative)).parts:
        candidate /= part
        if candidate.is_symlink():
            return None
    try:
        candidate.resolve(strict=True).relative_to(resolved_root)
    except (OSError, ValueError):
        return None
    return candidate if candidate.is_file() else None


def _strict_value_equal(actual: object, expected: object) -> bool:
    """Compare TOML contract values without bool/int type coercion."""
    if isinstance(expected, Mapping):
        return (
            isinstance(actual, Mapping)
            and set(actual) == set(expected)
            and all(
                _strict_value_equal(actual[key], value)
                for key, value in expected.items()
            )
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _strict_value_equal(actual_value, expected_value)
                for actual_value, expected_value in zip(actual, expected)
            )
        )
    return type(actual) is type(expected) and actual == expected


def _validate_exact_keys(
    actual: Mapping[str, Any],
    expected_keys: Sequence[str] | frozenset[str],
    label: str,
    errors: list[str],
) -> None:
    expected = set(expected_keys)
    present = set(actual)
    missing = sorted(expected - present)
    unexpected = sorted(present - expected)
    if missing or unexpected:
        errors.append(
            f"{label} keys changed: missing={missing!r}, "
            f"unexpected={unexpected!r}"
        )


def _validate_exact_mapping(
    actual: object,
    expected: Mapping[str, Any],
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(actual, Mapping):
        errors.append(f"{label} must be a table")
        return
    _validate_exact_keys(actual, tuple(expected), label, errors)
    for key, expected_value in expected.items():
        if key in actual and not _strict_value_equal(actual[key], expected_value):
            errors.append(f"{label}.{key} contract changed")


def validate_query202_adjudication_input_preregistration(
    config: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []

    _validate_exact_keys(config, EXPECTED_ROOT_KEYS, "root", errors)
    expected_root_scalars = {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "decision_id": "D005",
        "execution_status": "not_executed",
        "specified_on": "2026-10-13",
        "scope": (
            "Offline lossless compilation of audited Query 202 A into private "
            "adjudication inputs"
        ),
    }
    for key, expected in expected_root_scalars.items():
        if key not in config or not _strict_value_equal(config[key], expected):
            errors.append(f"root.{key} must be {expected!r}")
    status = config.get("status")
    frozen = status == "frozen_for_execution"
    if status not in {"proposed", "frozen_for_execution"}:
        errors.append("root.status must be proposed or frozen_for_execution")
    if config.get("execution_permitted") is not frozen:
        errors.append("root.execution_permitted must exactly follow frozen status")
    expected_rule = (
        "k-query202-adjudication-input-v1-frozen"
        if frozen
        else "k-query202-adjudication-input-v1-proposed"
    )
    if config.get("rule_version") != expected_rule:
        errors.append(f"root.rule_version must be {expected_rule!r}")

    source = config.get("input")
    _validate_exact_mapping(source, EXPECTED_INPUT, "input", errors)
    if isinstance(source, Mapping):
        for key in (
            "artifact_directory", "config_file", "manifest_file", "audit_file",
            "aggregate_summary_file", "executed_sql_file", "private_file",
        ):
            if not _safe_relative(source.get(key)):
                errors.append(f"input.{key} must be safe and project-relative")

    kinds = config.get("tuple_kind")
    if not isinstance(kinds, list):
        errors.append("tuple_kind must be a list")
    elif len(kinds) != len(EXPECTED_TUPLE_KINDS):
        errors.append("tuple_kind must contain exactly 11 entries")
    else:
        for index, (actual, expected) in enumerate(
            zip(kinds, EXPECTED_TUPLE_KINDS)
        ):
            _validate_exact_mapping(
                actual, expected, f"tuple_kind[{index}]", errors
            )

    _validate_exact_mapping(
        config.get("output"), EXPECTED_OUTPUT_CONTRACT, "output", errors
    )
    _validate_exact_mapping(
        config.get("review_contract"),
        EXPECTED_REVIEW_CONTRACT,
        "review_contract",
        errors,
    )
    _validate_exact_mapping(
        config.get("ndc_mode"), EXPECTED_NDC_MODE, "ndc_mode", errors
    )
    _validate_exact_mapping(
        config.get("execution"), EXPECTED_EXECUTION, "execution", errors
    )
    _validate_exact_mapping(
        config.get("privacy"), EXPECTED_PRIVACY, "privacy", errors
    )
    _validate_exact_mapping(
        config.get("guards"), EXPECTED_GUARDS, "guards", errors
    )

    implementation = config.get("implementation")
    if not isinstance(implementation, Mapping):
        errors.append("implementation must be a table")
    else:
        _validate_exact_keys(
            implementation,
            (
                "bundle_encoding",
                "compiler_paths",
                "auditor_paths",
                "compiler_bundle_sha256",
                "auditor_bundle_sha256",
            ),
            "implementation",
            errors,
        )
        if not _strict_value_equal(
            implementation.get("bundle_encoding"), BUNDLE_ENCODING
        ):
            errors.append("implementation.bundle_encoding changed")
        for name, expected_paths in EXPECTED_IMPLEMENTATION_PATHS.items():
            paths = implementation.get(f"{name}_paths")
            digest = implementation.get(f"{name}_bundle_sha256")
            if not _strict_value_equal(paths, list(expected_paths)):
                errors.append(
                    f"implementation.{name}_paths must exactly equal "
                    f"{list(expected_paths)!r}"
                )
            if frozen:
                if not isinstance(digest, str) or not HEX_SHA256.fullmatch(digest):
                    errors.append(f"implementation.{name}_bundle_sha256 not frozen")
            elif digest != PLACEHOLDER:
                errors.append(f"implementation.{name}_bundle_sha256 must be placeholder")
    return errors


def query202_adjudication_input_preregistration_report(root: Path) -> dict[str, Any]:
    config, config_sha256 = (
        _read_query202_adjudication_input_preregistration_snapshot(root)
    )
    errors = validate_query202_adjudication_input_preregistration(config)
    source = config.get("input", {})
    checked: dict[str, bool] = {}
    file_specs = {
        "config": (source.get("config_file"), source.get("config_sha256")),
        "manifest": (
            str(Path(str(source.get("artifact_directory", ""))) / str(source.get("manifest_file", ""))),
            source.get("manifest_sha256"),
        ),
        "audit": (
            str(Path(str(source.get("artifact_directory", ""))) / str(source.get("audit_file", ""))),
            source.get("audit_sha256"),
        ),
        "aggregate_summary": (
            str(Path(str(source.get("artifact_directory", ""))) / str(source.get("aggregate_summary_file", ""))),
            source.get("aggregate_summary_sha256"),
        ),
        "executed_sql": (
            str(Path(str(source.get("artifact_directory", ""))) / str(source.get("executed_sql_file", ""))),
            source.get("executed_sql_sha256"),
        ),
        "private": (
            str(Path(str(source.get("artifact_directory", ""))) / str(source.get("private_file", ""))),
            source.get("private_stored_sha256"),
        ),
    }
    for label, (relative, expected) in file_specs.items():
        ok = False
        if _safe_relative(relative) and isinstance(expected, str):
            path = _project_regular_file(root, relative)
            ok = path is not None and _sha256(path) == expected
        checked[label] = ok
        if not ok:
            errors.append(f"input file {label} hash mismatch")

    bundles: dict[str, str | None] = {}
    implementation = config.get("implementation", {})
    if isinstance(implementation, Mapping):
        for name in EXPECTED_IMPLEMENTATION_PATHS:
            paths = implementation.get(f"{name}_paths")
            expected = implementation.get(f"{name}_bundle_sha256")
            actual: str | None = None
            try:
                if isinstance(paths, list) and all(_safe_relative(p) for p in paths):
                    actual = implementation_bundle_sha256(root, paths)
            except OSError:
                pass
            bundles[name] = actual
            if config.get("status") == "frozen_for_execution" and actual != expected:
                errors.append(f"implementation {name} bundle hash mismatch")

    return {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "status": config.get("status"),
        "execution_status": config.get("execution_status"),
        "execution_permitted": config.get("execution_permitted"),
        "valid": not errors,
        "freeze_ready": (
            not errors
            and config.get("status") == "frozen_for_execution"
            and config.get("execution_permitted") is True
        ),
        "errors": errors,
        "input_files": checked,
        "implementation_bundles": bundles,
        "semantic_records": EXPECTED_OUTPUT["semantic_records"],
        "crosswalk_unique_tuples": 2_050_833,
        "route_typed_memberships": EXPECTED_OUTPUT["route_typed_memberships"],
        "ndc_candidates": EXPECTED_OUTPUT["ndc_candidates"],
        "database_access_allowed": False,
        "external_api_allowed": False,
        "guards": dict(config.get("guards", {})) if isinstance(config.get("guards"), Mapping) else {},
        "config_sha256": config_sha256,
    }


__all__ = [
    "BUNDLE_ENCODING",
    "COMPONENT_ID",
    "CONFIG_PATH",
    "EXPECTED_AUDITOR_PATHS",
    "EXPECTED_COMPILER_PATHS",
    "EXPECTED_INPUT_HASHES",
    "EXPECTED_IMPLEMENTATION_PATHS",
    "EXPECTED_OUTPUT",
    "EXPECTED_OUTPUT_FILES",
    "implementation_bundle_sha256",
    "query202_adjudication_input_preregistration_report",
    "read_query202_adjudication_input_preregistration",
    "validate_query202_adjudication_input_preregistration",
]
