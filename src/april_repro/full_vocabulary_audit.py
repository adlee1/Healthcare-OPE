"""Offline, value-safe audit for the private Query-201 vocabulary artifact.

This module never opens a database connection.  It independently recomputes
the normalization, lexical review classification, Query-200 subset membership,
and all published aggregate counters from the saved private dictionary.  Audit
output contains only counts, hashes, boolean controls, and safe check names.
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
from typing import Any, Iterable, Mapping

from .preregistration import (
    potassium_source_discovery_preregistration_report,
    read_potassium_source_discovery_preregistration,
)


QUERY_NAME = "potassium_full_source_vocabulary_discovery"
AUDIT_NAME = "potassium_full_source_vocabulary_discovery_offline_audit"
STATEMENT_TIMEOUT_MS = 120_000
PROCESS_TIMEOUT_SECONDS = 130
EXPECTED_D005_CONFIG_SHA256 = (
    "a0e41d661075ac578cfa6d14313582872c19b6bc8aa7158051d2216e38230cf1"
)
Q200_MANIFEST = Path("artifacts/profiling/20261011T174457.657508Z/manifest.json")
Q200_HASHES = {
    "manifest": "76b9ae67d02081d634965906cb7c11a3671b2c69ac7e194252b996156ee099e6",
    "audit": "73ca31b9556165ccb79e3d278812b4d0aec39aa75498327f452ca46fe6b9a31c",
    "discovery": "316861627d7ec0bf3eb3b61873c3b94578ab949572751c8da280e1b925bb826a",
    "output": "32995ac27f49e5fc9bac3893669f159916868382201a8a35197402f70bf7b66d",
    "executed_sql": "7f04d0d67d6e97b3ab20a026c3c8edb98e47fd42aae4e7e617f359a6e0e04df2",
}
Q200_VALUE_COUNTS = {
    "emar_names": 23,
    "detail_names": 79,
    "pharmacy_names": 45,
    "prescription_names": 52,
    "seed_product_codes": 27,
    "detail_code_name_flags": 38,
}
Q200_AUDIT_CHECKS = 18_952
Q200_FIXED_COUNTS = {
    "candidate_emar_heads": 719_059,
    "query199_head_scope_distinct_heads": 559_191,
    "heads_new_beyond_direct_name": 159_868,
}


@dataclass(frozen=True)
class SourceSpec:
    key: str
    field: str
    method: str
    sql_file: str
    q200_key: str


SOURCES = (
    SourceSpec(
        "emar_medication",
        "mimiciv_hosp.emar.medication",
        "recursive_index_walk",
        "sql/profiling/201a_full_emar_medication_vocabulary.sql",
        "emar_names",
    ),
    SourceSpec(
        "detail_product_description",
        "mimiciv_hosp.emar_detail.product_description",
        "recursive_index_walk",
        "sql/profiling/201b_full_detail_product_description_vocabulary.sql",
        "detail_names",
    ),
    SourceSpec(
        "pharmacy_medication",
        "mimiciv_hosp.pharmacy.medication",
        "recursive_index_walk",
        "sql/profiling/201c_full_pharmacy_medication_vocabulary.sql",
        "pharmacy_names",
    ),
    SourceSpec(
        "prescription_drug",
        "mimiciv_hosp.prescriptions.drug",
        "full_distinct_scan",
        "sql/profiling/201d_full_prescription_drug_vocabulary.sql",
        "prescription_names",
    ),
)
SOURCE_BY_KEY = {source.key: source for source in SOURCES}

REVIEW_STRATA = (
    "blank_after_trim",
    "focal_kcl_repletion_hint",
    "broader_phosphate_or_acetate_repletion_hint",
    "other_potassium_salt_review",
    "non_repletion_active_drug_hint",
    "unresolved_potassium_lexical_review",
    "no_declared_potassium_lexical_signal",
)
CLASSIFICATION_PRECEDENCE = (
    "blank_after_trim",
    "non_repletion_active_drug_hint",
    "focal_kcl_repletion_hint",
    "broader_phosphate_or_acetate_repletion_hint",
    "other_potassium_salt_review",
    "unresolved_potassium_lexical_review",
    "no_declared_potassium_lexical_signal",
)
HINT_KEYS = (
    "blank_after_trim",
    "focal_kcl_hint",
    "phosphate_or_acetate_hint",
    "other_potassium_salt_hint",
    "non_repletion_active_drug_hint",
    "declared_potassium_lexical_signal",
    "unresolved_potassium_lexical_hint",
    "no_declared_potassium_lexical_signal",
)
POLICY_GUARDS = (
    "product_identity_decided",
    "final_source_policy",
    "complete_intervention_coverage",
    "review_strata_are_inclusion_rules",
    "formal_action",
    "formal_episode",
    "zero_action_constructed",
    "formal_non_icu_rule",
    "formal_label",
    "formal_cohort",
)

# Kept separate from the production classifier so the audit can detect drift.
_FOCAL = re.compile(
    r"potassium[\s-]+(?:chloride|chl)(?:[^A-Za-z]|$)|"
    r"(?:^|[^A-Za-z0-9])kcl(?:[^A-Za-z0-9]|$)", re.I
)
_PHOSPHATE = re.compile(
    r"potassium[\s-]+phosph|(?:^|[^A-Za-z0-9])k[ -]?phos(?:[^A-Za-z0-9]|$)",
    re.I,
)
_ACETATE = re.compile(r"potassium[\s-]+acetate", re.I)
_OTHER_SALT = re.compile(
    r"potassium[\s-]+(?:citrate|bicarbonate|gluconate|iodide|"
    r"permanganate|perchlorate|tartrate)", re.I
)
_ACTIVE = re.compile(
    r"losartan|penicillin|amoxicillin|clavulan|diclofenac|clorazepate", re.I
)
_DECLARED = re.compile(
    r"potassium|(?:^|[^A-Za-z0-9])k[ -]?phos(?:[^A-Za-z0-9]|$)|"
    r"(?:^|[^A-Za-z0-9])kcl(?:[^A-Za-z0-9]|$)", re.I
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MARKER_HEX = r"[0-9a-f]{48}"


class AuditContractError(RuntimeError):
    """A safe audit failure that contains no controlled-vocabulary value."""


class Checks:
    def __init__(self) -> None:
        self.total = 0
        self.failed: list[str] = []

    def require(self, condition: bool, name: str) -> None:
        self.total += 1
        if not condition:
            if name not in self.failed:
                self.failed.append(name)
            raise AuditContractError(name)

    def check(self, condition: bool, name: str) -> None:
        self.total += 1
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


def _read_unique_json(path: Path, limit: int, label: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) > limit:
        raise AuditContractError(label + ".byte_limit")

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
    return value


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


def _independent_classify(raw: str) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", raw.strip()).lower()
    blank = normalized == ""
    focal = _FOCAL.search(raw) is not None
    broader = _PHOSPHATE.search(raw) is not None or _ACETATE.search(raw) is not None
    other = _OTHER_SALT.search(raw) is not None
    active = _ACTIVE.search(raw) is not None
    declared = _DECLARED.search(raw) is not None
    unresolved = declared and not focal and not broader and not other and not active
    no_signal = not declared
    if blank:
        stratum = "blank_after_trim"
    elif active:
        stratum = "non_repletion_active_drug_hint"
    elif focal:
        stratum = "focal_kcl_repletion_hint"
    elif broader:
        stratum = "broader_phosphate_or_acetate_repletion_hint"
    elif other:
        stratum = "other_potassium_salt_review"
    elif unresolved:
        stratum = "unresolved_potassium_lexical_review"
    else:
        stratum = "no_declared_potassium_lexical_signal"
    return {
        "normalized_name": normalized,
        "review_stratum": stratum,
        "hints": {
            "blank_after_trim": blank,
            "focal_kcl_hint": focal,
            "phosphate_or_acetate_hint": broader,
            "other_potassium_salt_hint": other,
            "non_repletion_active_drug_hint": active,
            "declared_potassium_lexical_signal": declared,
            "unresolved_potassium_lexical_hint": unresolved,
            "no_declared_potassium_lexical_signal": no_signal,
        },
    }


def _expected_lineage(*, summary: bool = False, manifest: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "manifest_path": str(Q200_MANIFEST),
        "hashes": dict(Q200_HASHES),
        "audit_checks": Q200_AUDIT_CHECKS,
        "value_counts": dict(Q200_VALUE_COUNTS),
    }
    if summary:
        result["all_four_vocabulary_arrays_are_exact_subsets"] = True
    if manifest:
        result.update(Q200_FIXED_COUNTS)
    return result


def _load_q200(root: Path, checks: Checks) -> dict[str, set[str]]:
    manifest_path = root / Q200_MANIFEST
    checks.require(manifest_path.is_file() and not manifest_path.is_symlink(), "q200.manifest.present")
    checks.require(_sha_file(manifest_path) == Q200_HASHES["manifest"], "q200.manifest.frozen_hash")
    manifest = _read_unique_json(manifest_path, 4 * 1024 * 1024, "q200.manifest")
    queries = manifest.get("queries")
    checks.require(
        manifest.get("status") == "complete"
        and isinstance(queries, list) and len(queries) == 1
        and isinstance(queries[0], dict),
        "q200.manifest.complete",
    )
    entry = queries[0]
    role_files = {
        "discovery": entry.get("discovery_file"),
        "output": entry.get("output_file"),
        "executed_sql": entry.get("executed_sql_file"),
        "audit": "audit-summary.json",
    }
    paths: dict[str, Path] = {}
    for role, filename in role_files.items():
        path = _safe_file(manifest_path.parent, filename, "q200." + role)
        paths[role] = path
        checks.require(_sha_file(path) == Q200_HASHES[role], f"q200.{role}.frozen_hash")
        checks.require(_mode(path) == "0600", f"q200.{role}.private_mode")
    audit = _read_unique_json(paths["audit"], 4 * 1024 * 1024, "q200.audit")
    checks.require(
        audit.get("status") == "passed"
        and isinstance(audit.get("audit_checks"), dict)
        and audit["audit_checks"].get("total") == Q200_AUDIT_CHECKS
        and audit["audit_checks"].get("failed") == [],
        "q200.audit.passed",
    )
    discovery = _read_unique_json(paths["discovery"], 8 * 1024 * 1024, "q200.discovery")
    vocabulary: dict[str, set[str]] = {}
    for spec in SOURCES:
        values = discovery.get(spec.q200_key)
        checks.require(
            isinstance(values, list)
            and all(isinstance(item, str) for item in values)
            and len(values) == Q200_VALUE_COUNTS[spec.q200_key]
            and len(values) == len(set(values)),
            f"q200.{spec.key}.fixed_vocabulary_count",
        )
        vocabulary[spec.key] = set(values)
    for key in ("seed_product_codes", "detail_code_name_flags"):
        values = discovery.get(key)
        checks.require(
            isinstance(values, list) and len(values) == Q200_VALUE_COUNTS[key],
            f"q200.{key}.fixed_count",
        )
    merge = entry.get("merge_validation")
    checks.require(isinstance(merge, dict), "q200.merge_validation.schema")
    checks.require(
        merge.get("candidate_emar_heads") == Q200_FIXED_COUNTS["candidate_emar_heads"]
        and merge.get("query199_head_scope_distinct_heads")
        == Q200_FIXED_COUNTS["query199_head_scope_distinct_heads"],
        "q200.fixed_head_counts",
    )
    return vocabulary


def _audit_preregistration(root: Path, manifest: Mapping[str, Any], checks: Checks) -> None:
    report = potassium_source_discovery_preregistration_report(root)
    checks.require(report.get("valid") is True, "d005.preregistration.valid")
    checks.require(
        report.get("config_sha256") == EXPECTED_D005_CONFIG_SHA256,
        "d005.preregistration.frozen_hash",
    )
    checks.require(report.get("status") == "proposed", "d005.preregistration.proposed")
    component = manifest.get("component_preregistration")
    checks.require(
        isinstance(component, dict)
        and set(component) == {
            "component_id", "status", "config", "config_sha256",
            "evidence_files_checked", "formal_source_policy_enabled",
            "formal_product_identity_enabled",
        },
        "d005.manifest_component.exact_schema",
    )
    checks.require(
        component == {
            "component_id": "D005-K-SOURCE-DISCOVERY-v1",
            "status": "proposed",
            "config": "config/preregistrations/d005_potassium_source_discovery.toml",
            "config_sha256": EXPECTED_D005_CONFIG_SHA256,
            "evidence_files_checked": 12,
            "formal_source_policy_enabled": False,
            "formal_product_identity_enabled": False,
        },
        "d005.manifest_component.frozen_values",
    )
    config = read_potassium_source_discovery_preregistration(root)
    guards = config.get("guards")
    checks.require(
        isinstance(guards, dict) and guards
        and all(value is False for value in guards.values()),
        "d005.config.all_guards_false",
    )
    checks.require(
        config.get("formal_source_policy_enabled") is False
        and config.get("formal_product_identity_enabled") is False,
        "d005.config.formal_product_source_false",
    )


def _audit_public_payload(
    payload: Mapping[str, Any], private_values: set[str], label: str, checks: Checks
) -> None:
    public_strings: list[str] = []
    forbidden = {"raw_name", "normalized_name", "product_code"}
    forbidden_seen = False

    def walk(value: Any) -> None:
        nonlocal forbidden_seen
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key).casefold() in forbidden:
                    forbidden_seen = True
                public_strings.append(str(key))
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            public_strings.append(value)

    walk(payload)
    checks.require(not forbidden_seen, label + ".forbidden_private_keys_absent")
    public_set = set(public_strings)
    checks.require(not (private_values & public_set), label + ".exact_private_values_absent")
    long_values = [value for value in private_values if len(value) >= 12]
    checks.require(
        not any(value and value in public for value in long_values for public in public_strings),
        label + ".embedded_private_values_absent",
    )


def _audit_dictionary(
    discovery: Mapping[str, Any],
    summary: Mapping[str, Any],
    q200_vocabulary: Mapping[str, set[str]],
    checks: Checks,
) -> tuple[dict[str, int], dict[str, int], set[str]]:
    checks.require(
        set(discovery) == {
            "schema_version", "query", "created_at_utc", "classification_version",
            "normalization", "review_strata", "classification_precedence",
            "transaction", "query200_lineage", "sources",
            "dictionary_value_is_patient_text", "all_source_policy_statuses",
            "policy_guards",
        },
        "q201.discovery.exact_schema",
    )
    checks.require(
        discovery.get("schema_version") == 1
        and discovery.get("query") == QUERY_NAME
        and discovery.get("classification_version") == "D005-K-SOURCE-DISCOVERY-v1"
        and discovery.get("normalization")
        == "strip_then_collapse_unicode_whitespace_then_lowercase"
        and discovery.get("review_strata") == list(REVIEW_STRATA)
        and discovery.get("classification_precedence") == list(CLASSIFICATION_PRECEDENCE),
        "q201.discovery.frozen_contract",
    )
    transaction = discovery.get("transaction")
    checks.require(
        isinstance(transaction, dict)
        and set(transaction) == {
            "isolation", "read_only", "same_snapshot", "snapshot_token_sha256",
            "rollback_confirmed_before_persistence",
            "clean_psql_exit_confirmed_before_persistence",
        }
        and transaction.get("isolation") == "repeatable read"
        and transaction.get("read_only") is True
        and transaction.get("same_snapshot") is True
        and transaction.get("rollback_confirmed_before_persistence") is True
        and transaction.get("clean_psql_exit_confirmed_before_persistence") is True
        and isinstance(transaction.get("snapshot_token_sha256"), str)
        and _SHA256.fullmatch(transaction["snapshot_token_sha256"]) is not None,
        "q201.discovery.transaction_controls",
    )
    checks.require(
        discovery.get("query200_lineage") == _expected_lineage(),
        "q201.discovery.q200_fixed_lineage",
    )
    checks.require(
        discovery.get("dictionary_value_is_patient_text") is False
        and discovery.get("all_source_policy_statuses") == "unresolved",
        "q201.discovery.neutral_status",
    )
    guards = discovery.get("policy_guards")
    checks.require(
        isinstance(guards, dict) and set(guards) == set(POLICY_GUARDS)
        and all(guards[key] is False for key in POLICY_GUARDS),
        "q201.discovery.all_policy_guards_false",
    )
    sources = discovery.get("sources")
    checks.require(
        isinstance(sources, dict) and set(sources) == set(SOURCE_BY_KEY),
        "q201.discovery.four_sources_exact",
    )

    source_totals: dict[str, int] = {}
    source_negatives: dict[str, int] = {}
    private_values: set[str] = set()
    composite_raw_keys: set[tuple[str, str]] = set()
    derived_source: dict[str, dict[str, Any]] = {}
    for spec in SOURCES:
        source = sources[spec.key]
        checks.require(
            isinstance(source, dict)
            and set(source) == {
                "source_field", "enumeration_method", "distinct_nonnull_values",
                "q200_dictionary_values", "values",
            },
            f"q201.{spec.key}.exact_source_schema",
        )
        values = source.get("values")
        checks.require(isinstance(values, list), f"q201.{spec.key}.values_array")
        checks.require(
            source.get("source_field") == spec.field
            and source.get("enumeration_method") == spec.method,
            f"q201.{spec.key}.source_contract",
        )
        raw_seen: set[str] = set()
        overlap = 0
        strata = Counter({key: 0 for key in REVIEW_STRATA})
        hints = Counter({key: 0 for key in HINT_KEYS})
        q200_set = q200_vocabulary[spec.key]
        q200_true: set[str] = set()
        ordered_raw: list[str] = []
        for index, record in enumerate(values):
            prefix = f"q201.{spec.key}.record_{index}"
            checks.require(
                isinstance(record, dict)
                and set(record) == {
                    "raw_name", "normalized_name", "q200_member", "review_stratum",
                    "hints", "source_policy_status",
                    "source_review_stratum_is_final_policy",
                },
                prefix + ".exact_schema",
            )
            raw = record.get("raw_name")
            checks.require(isinstance(raw, str), prefix + ".raw_text")
            checks.require(raw not in raw_seen, f"q201.{spec.key}.raw_keys_unique")
            raw_seen.add(raw)
            composite = (spec.field, raw)
            checks.require(composite not in composite_raw_keys, "q201.composite_raw_keys_unique")
            composite_raw_keys.add(composite)
            ordered_raw.append(raw)
            expected = _independent_classify(raw)
            checks.require(
                record.get("normalized_name") == expected["normalized_name"],
                prefix + ".normalization_recomputed",
            )
            checks.require(
                record.get("review_stratum") == expected["review_stratum"],
                prefix + ".seven_strata_recomputed",
            )
            record_hints = record.get("hints")
            checks.require(
                isinstance(record_hints, dict)
                and set(record_hints) == set(HINT_KEYS)
                and record_hints == expected["hints"]
                and all(type(record_hints[key]) is bool for key in HINT_KEYS),
                prefix + ".independent_hints_recomputed",
            )
            expected_member = raw in q200_set
            checks.require(
                type(record.get("q200_member")) is bool
                and record["q200_member"] is expected_member,
                prefix + ".q200_membership_recomputed",
            )
            checks.require(
                record.get("source_policy_status") == "unresolved"
                and record.get("source_review_stratum_is_final_policy") is False,
                prefix + ".policy_unresolved",
            )
            if expected_member:
                overlap += 1
                q200_true.add(raw)
            strata[expected["review_stratum"]] += 1
            for key in HINT_KEYS:
                hints[key] += int(expected["hints"][key])
            private_values.add(raw)
            private_values.add(expected["normalized_name"])
        checks.require(ordered_raw == sorted(ordered_raw), f"q201.{spec.key}.deterministic_order")
        checks.require(q200_true == q200_set, f"q201.{spec.key}.q200_exact_subset")
        total = len(values)
        negative = total - overlap
        checks.require(
            source.get("distinct_nonnull_values") == total
            and source.get("q200_dictionary_values") == len(q200_set),
            f"q201.{spec.key}.source_counts",
        )
        checks.require(
            sum(strata.values()) == total and overlap + negative == total,
            f"q201.{spec.key}.source_conservation",
        )
        source_totals[spec.key] = total
        source_negatives[spec.key] = negative
        derived_source[spec.key] = {
            "source_field": spec.field,
            "enumeration_method": spec.method,
            "distinct_nonnull_values": total,
            "query200_dictionary_values": len(q200_set),
            "query200_overlap_values": overlap,
            "negative_space_values": negative,
            "review_strata_counts": {key: strata[key] for key in REVIEW_STRATA},
            "independent_hint_counts": {key: hints[key] for key in HINT_KEYS},
            "seven_strata_conservation_confirmed": True,
            "overlap_negative_space_conservation_confirmed": True,
            "query200_exact_subset_confirmed": True,
        }

    checks.require(
        set(summary) == {
            "schema_version", "query", "scope", "status", "source_summaries",
            "global_source_value_memberships", "query200_lineage", "privacy",
            "all_source_policy_statuses", "policy_guards", "limitations",
            "private_artifact_hashes",
        },
        "q201.summary.exact_schema",
    )
    checks.require(
        summary.get("schema_version") == 1 and summary.get("query") == QUERY_NAME
        and summary.get("scope") == "four_complete_nonnull_distinct_source_vocabularies"
        and summary.get("status") == "complete",
        "q201.summary.complete_contract",
    )
    actual_summaries = summary.get("source_summaries")
    checks.require(
        isinstance(actual_summaries, dict) and set(actual_summaries) == set(SOURCE_BY_KEY),
        "q201.summary.four_sources_exact",
    )
    for spec in SOURCES:
        checks.require(
            actual_summaries[spec.key] == derived_source[spec.key],
            f"q201.{spec.key}.summary_recomputed",
        )
    global_strata = Counter({key: 0 for key in REVIEW_STRATA})
    global_hints = Counter({key: 0 for key in HINT_KEYS})
    for source in derived_source.values():
        global_strata.update(source["review_strata_counts"])
        global_hints.update(source["independent_hint_counts"])
    total = sum(source_totals.values())
    overlap = sum(Q200_VALUE_COUNTS[spec.q200_key] for spec in SOURCES)
    negative = sum(source_negatives.values())
    expected_global = {
        "distinct_nonnull_source_value_memberships": total,
        "query200_overlap_source_value_memberships": overlap,
        "negative_space_source_value_memberships": negative,
        "review_strata_counts": {key: global_strata[key] for key in REVIEW_STRATA},
        "independent_hint_counts": {key: global_hints[key] for key in HINT_KEYS},
        "seven_strata_conservation_confirmed": True,
        "overlap_negative_space_conservation_confirmed": True,
    }
    checks.require(
        summary.get("global_source_value_memberships") == expected_global,
        "q201.summary.global_conservation_recomputed",
    )
    checks.require(total == overlap + negative, "q201.global.overlap_negative_equals_total")
    checks.require(
        summary.get("query200_lineage") == _expected_lineage(summary=True),
        "q201.summary.q200_fixed_lineage",
    )
    checks.require(
        summary.get("privacy") == {
            "controlled_vocabulary_values_emitted": False,
            "patient_identifiers_or_timestamps_emitted": False,
            "private_dictionary_required_for_value_review": True,
        },
        "q201.summary.privacy_guards",
    )
    summary_guards = summary.get("policy_guards")
    checks.require(
        isinstance(summary_guards, dict) and set(summary_guards) == set(POLICY_GUARDS)
        and all(summary_guards[key] is False for key in POLICY_GUARDS)
        and summary.get("all_source_policy_statuses") == "unresolved",
        "q201.summary.all_policy_guards_false",
    )
    _audit_public_payload(summary, private_values, "q201.summary", checks)
    return source_totals, source_negatives, private_values


def _template_body(raw: bytes) -> str:
    text = raw.decode("utf-8").strip()
    if not text.endswith(";"):
        raise AuditContractError("q201.sql_template.single_statement_terminator")
    return text[:-1].rstrip()


def _audit_executed_sql(
    root: Path, raw: bytes, stages: Mapping[str, Any], checks: Checks
) -> None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuditContractError("q201.executed_sql.utf8") from exc
    position = 0
    preamble = (
        "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
        "SET LOCAL statement_timeout = '120000ms';\n"
        "SET LOCAL lock_timeout = '2000ms';\n"
        "SET LOCAL standard_conforming_strings = on;\n"
        "SET LOCAL work_mem = '128MB';\n"
        "SET LOCAL jit = off;\n"
    )
    for index, spec in enumerate(SOURCES):
        token = spec.key.upper()
        marker_re = re.compile(
            r"\\echo (__APRIL_Q201_" + re.escape(token) + r"_" + _MARKER_HEX + r"__)\n"
        )
        match = marker_re.search(text, position)
        checks.require(match is not None, f"q201.executed_sql.{spec.key}.marker")
        chunk = text[position:match.end()]
        template_raw = (root / spec.sql_file).read_bytes()
        expected = (
            (preamble if index == 0 else "")
            + _template_body(template_raw)
            + ";\n\\echo " + match.group(1) + "\n"
        )
        checks.require(chunk == expected, f"q201.executed_sql.{spec.key}.exact_control")
        stage = stages[spec.key]
        encoded = chunk.encode("utf-8")
        checks.require(
            stage.get("control_sha256") == _sha_bytes(encoded)
            and stage.get("control_bytes") == len(encoded),
            f"q201.executed_sql.{spec.key}.control_hash",
        )
        position = match.end()
    tail = text[position:]
    checks.require(
        re.fullmatch(
            r"ROLLBACK;\n\\echo __APRIL_Q201_ROLLBACK_" + _MARKER_HEX + r"__\n\\q\n",
            tail,
        ) is not None,
        "q201.executed_sql.explicit_rollback_and_clean_quit",
    )


def _audit_manifest_and_files(
    root: Path,
    directory: Path,
    manifest: Mapping[str, Any],
    discovery_raw: bytes,
    summary_raw: bytes,
    executed_raw: bytes,
    source_totals: Mapping[str, int],
    source_negatives: Mapping[str, int],
    checks: Checks,
) -> None:
    checks.require(
        set(manifest) == {
            "schema_version", "started_at_utc", "status", "scope",
            "selected_queries", "requested_controls", "confirmed_controls",
            "artifact_modes", "component_preregistration", "query200_lineage",
            "queries", "limitations", "finished_at_utc", "elapsed_seconds",
        },
        "q201.manifest.exact_schema",
    )
    checks.require(
        manifest.get("schema_version") == 1 and manifest.get("status") == "complete"
        and manifest.get("scope") == "private_full_source_vocabulary_negative_space_discovery"
        and manifest.get("selected_queries") == [QUERY_NAME],
        "q201.manifest.complete",
    )
    checks.require(
        manifest.get("requested_controls") == {
            "read_only": True, "same_snapshot": True,
            "transaction_isolation": "repeatable read",
            "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
            "explicit_rollback": True,
            "clean_psql_exit_before_value_persistence": True,
        },
        "q201.manifest.requested_controls",
    )
    checks.require(
        manifest.get("confirmed_controls") == {
            "read_only": True, "same_snapshot": True,
            "transaction_isolation": "repeatable read", "rollback": True,
            "clean_psql_exit": True,
        },
        "q201.manifest.confirmed_controls",
    )
    checks.require(
        manifest.get("query200_lineage") == _expected_lineage(manifest=True),
        "q201.manifest.q200_fixed_lineage",
    )
    queries = manifest.get("queries")
    checks.require(
        isinstance(queries, list) and len(queries) == 1 and isinstance(queries[0], dict),
        "q201.manifest.single_query",
    )
    entry = queries[0]
    checks.require(
        entry.get("query") == QUERY_NAME and entry.get("status") == "complete"
        and entry.get("psql_returncode") == 0
        and entry.get("private_discovery_persisted") is True
        and entry.get("executed_sql_persisted") is True
        and entry.get("aggregate_summary_persisted") is True
        and entry.get("query200_exact_subset_confirmed") is True
        and entry.get("seven_strata_conservation_confirmed") is True,
        "q201.manifest.query_complete",
    )
    checks.require(entry.get("source_counts") == dict(source_totals), "q201.manifest.source_counts")
    checks.require(
        entry.get("negative_space_counts") == dict(source_negatives),
        "q201.manifest.negative_space_counts",
    )
    checks.require(
        entry.get("discovery_sha256") == _sha_bytes(discovery_raw)
        and entry.get("discovery_bytes") == len(discovery_raw)
        and entry.get("aggregate_summary_sha256") == _sha_bytes(summary_raw)
        and entry.get("aggregate_summary_bytes") == len(summary_raw)
        and entry.get("executed_sql_sha256") == _sha_bytes(executed_raw)
        and entry.get("executed_sql_bytes") == len(executed_raw),
        "q201.manifest.private_file_hashes_and_bytes",
    )
    stages = entry.get("stages")
    checks.require(
        isinstance(stages, dict) and set(stages) == set(SOURCE_BY_KEY),
        "q201.manifest.four_stages_exact",
    )
    snapshot_hash = entry.get("snapshot_token_sha256")
    checks.require(
        isinstance(snapshot_hash, str) and _SHA256.fullmatch(snapshot_hash) is not None,
        "q201.manifest.snapshot_hash",
    )
    for spec in SOURCES:
        stage = stages[spec.key]
        sql_path = root / spec.sql_file
        checks.require(
            isinstance(stage, dict)
            and stage.get("status") == "complete" and stage.get("rows") == 1
            and stage.get("source_key") == spec.key
            and stage.get("source_field") == spec.field
            and stage.get("enumeration_method") == spec.method
            and stage.get("file") == spec.sql_file,
            f"q201.manifest.{spec.key}.complete_contract",
        )
        checks.require(
            stage.get("statement_timeout_ms") == STATEMENT_TIMEOUT_MS
            and stage.get("process_timeout_seconds") == PROCESS_TIMEOUT_SECONDS
            and stage.get("observed_transaction_isolation") == "repeatable read"
            and stage.get("observed_transaction_read_only") == "on"
            and stage.get("observed_snapshot_sha256") == snapshot_hash,
            f"q201.manifest.{spec.key}.same_snapshot_read_only_timeout",
        )
        checks.require(
            stage.get("distinct_nonnull_values") == source_totals[spec.key],
            f"q201.manifest.{spec.key}.source_count",
        )
        checks.require(
            stage.get("template_sha256") == _sha_file(sql_path)
            and stage.get("template_bytes") == sql_path.stat().st_size,
            f"q201.manifest.{spec.key}.current_template_hash",
        )
    checks.require(
        entry.get("cumulative_control_bytes")
        == sum(stages[spec.key]["control_bytes"] for spec in SOURCES)
        and entry.get("cumulative_frame_bytes")
        == sum(stages[spec.key]["frame_bytes"] for spec in SOURCES),
        "q201.manifest.cumulative_bytes",
    )
    _audit_executed_sql(root, executed_raw, stages, checks)
    modes = manifest.get("artifact_modes")
    expected_value_modes = {
        entry["discovery_file"]: "0600",
        entry["executed_sql_file"]: "0600",
        entry["aggregate_summary_file"]: "0600",
    }
    checks.require(
        modes == {
            "directory": "0700", "manifest": "0600", "stderr": "0600",
            "value_files": expected_value_modes,
        },
        "q201.manifest.private_modes_declared",
    )
    checks.require(_mode(directory) == "0700", "q201.files.directory_mode_0700")
    for filename in expected_value_modes:
        checks.require(_mode(_safe_file(directory, filename, "q201.private_file")) == "0600", "q201.files.private_mode_0600")
    checks.require(_mode(directory / "manifest.json") == "0600", "q201.files.manifest_mode_0600")
    stderr_path = _safe_file(directory, entry.get("stderr_file"), "q201.stderr")
    checks.require(
        _mode(stderr_path) == "0600" and stderr_path.read_bytes() == b""
        and entry.get("stderr_bytes") == 0
        and entry.get("stderr_sha256") == _sha_bytes(b""),
        "q201.files.stderr_empty_private",
    )


def audit_artifact(
    directory: Path, root: Path
) -> tuple[dict[str, Any], Path]:
    """Audit one Query-201 directory and write a private aggregate-only report."""
    directory = directory.resolve()
    root = root.resolve()
    checks = Checks()
    private_values: set[str] = set()
    integrity: dict[str, Any] = {}
    source_totals: dict[str, int] = {}
    source_negatives: dict[str, int] = {}
    try:
        checks.require(directory.is_dir() and not directory.is_symlink(), "q201.files.directory")
        checks.require(_mode(directory) == "0700", "q201.files.directory_private")
        manifest_path = _safe_file(directory, "manifest.json", "q201.manifest")
        checks.require(_mode(manifest_path) == "0600", "q201.manifest.private_mode")
        manifest_raw = manifest_path.read_bytes()
        manifest = _read_unique_json(manifest_path, 4 * 1024 * 1024, "q201.manifest")
        queries = manifest.get("queries")
        checks.require(
            isinstance(queries, list) and len(queries) == 1 and isinstance(queries[0], dict),
            "q201.manifest.query_entry",
        )
        entry = queries[0]
        discovery_path = _safe_file(directory, entry.get("discovery_file"), "q201.discovery")
        summary_path = _safe_file(directory, entry.get("aggregate_summary_file"), "q201.summary")
        executed_path = _safe_file(directory, entry.get("executed_sql_file"), "q201.executed_sql")
        discovery_raw = discovery_path.read_bytes()
        summary_raw = summary_path.read_bytes()
        executed_raw = executed_path.read_bytes()
        discovery = _read_unique_json(discovery_path, 96 * 1024 * 1024, "q201.discovery")
        summary = _read_unique_json(summary_path, 4 * 1024 * 1024, "q201.summary")
        q200_vocabulary = _load_q200(root, checks)
        _audit_preregistration(root, manifest, checks)
        source_totals, source_negatives, private_values = _audit_dictionary(
            discovery, summary, q200_vocabulary, checks
        )
        _audit_manifest_and_files(
            root, directory, manifest, discovery_raw, summary_raw, executed_raw,
            source_totals, source_negatives, checks,
        )
        checks.require(
            summary.get("private_artifact_hashes") == {
                "discovery_sha256": _sha_bytes(discovery_raw),
                "executed_sql_sha256": _sha_bytes(executed_raw),
            },
            "q201.summary.private_artifact_hashes",
        )
        _audit_public_payload(manifest, private_values, "q201.manifest", checks)
        integrity = {
            "manifest_sha256": _sha_bytes(manifest_raw),
            "discovery_sha256": _sha_bytes(discovery_raw),
            "aggregate_summary_sha256": _sha_bytes(summary_raw),
            "executed_sql_sha256": _sha_bytes(executed_raw),
            "directory_mode": _mode(directory),
            "private_file_mode": "0600",
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
            "four_stages_required": True,
            "same_snapshot_required": True,
            "read_only_required": True,
            "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
            "rollback_and_clean_exit_required": True,
        },
        "content_contract": {
            "source_count": len(source_totals),
            "source_value_memberships_checked": sum(source_totals.values()),
            "negative_space_memberships_checked": sum(source_negatives.values()),
            "normalization_and_classification_recomputed": not checks.failed,
            "query200_exact_subset_recomputed": not checks.failed,
            "all_source_policy_statuses_unresolved": not checks.failed,
        },
        "query200_contract": {
            "fixed_hashes_checked": not checks.failed,
            "fixed_value_counts": dict(Q200_VALUE_COUNTS),
            "fixed_audit_checks": Q200_AUDIT_CHECKS,
        },
        "privacy": {
            "controlled_vocabulary_values_emitted": False,
            "raw_or_normalized_name_keys_emitted": False,
            "product_code_keys_emitted": False,
            "patient_identifiers_or_timestamps_emitted": False,
        },
        "formal_guards": {key: False for key in POLICY_GUARDS},
        "audit_checks": {
            "total": checks.total,
            "passed": checks.total - len(checks.failed),
            "failed": checks.failed,
        },
        "limitations": (
            "This offline audit validates the saved discovery boundary. It does not "
            "decide product identity, source inclusion, action, episode, label, or cohort."
        ),
    }
    # The audit report itself must remain aggregate-only.
    if private_values:
        secondary = Checks()
        try:
            _audit_public_payload(result, private_values, "q201.audit_summary", secondary)
        except AuditContractError:
            result["status"] = "failed"
            result["audit_checks"]["total"] += secondary.total
            result["audit_checks"]["failed"].append("q201.audit_summary.value_free")
            result["audit_checks"]["passed"] = (
                result["audit_checks"]["total"]
                - len(result["audit_checks"]["failed"])
            )
    output = directory / "audit-summary.json"
    payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = directory / ".audit-summary.json.tmp"
    try:
        temporary.unlink(missing_ok=True)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        output.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)
    return result, output

