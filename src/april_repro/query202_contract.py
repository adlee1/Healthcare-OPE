"""Pure controls for the proposed D005 Query 202 extraction architecture.

This module does not connect to MIMIC, classify route values, or construct a
cohort.  It makes two execution controls testable before any database run:
the stable 64-way subject partition and the mutually exclusive event-to-order
link status.  The matching SQL contract is recorded in the Query 202
preregistration; changing either reducer requires a new component version.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping


QUERY202_BUCKET_COUNT = 64
QUERY202_BUCKET_HASH_VERSION = "d005-k-query202-subject-md5-v1"
QUERY202_BUCKET_HASH_PREFIX = "D005-K-QUERY202-v1|"

PRIMARY_LINK_STATUSES = (
    "identity_conflict",
    "identity_missing",
    "poe_conflict_auxiliary",
    "poe_missing_auxiliary",
    "exact_multiple_prescription_components",
    "exact_single_prescription_component",
)

IDENTITY_CONFLICT_FLAGS = (
    "detail_head_identity_conflict",
    "pharmacy_subject_conflict",
    "pharmacy_hadm_conflict",
    "prescription_subject_conflict",
    "prescription_hadm_conflict",
    "incompatible_pharmacy_match_multiplicity",
)

IDENTITY_MISSING_FLAGS = (
    "detail_head_identity_missing",
    "pharmacy_id_missing",
    "pharmacy_match_missing",
    "pharmacy_hadm_missing",
    "prescription_match_missing",
    "prescription_hadm_missing",
)

AUXILIARY_LINK_FLAGS = (
    "nonblank_poe_conflict",
    "poe_missing_on_any_linked_record",
)

ALL_LINK_FLAGS = (
    *IDENTITY_CONFLICT_FLAGS,
    *IDENTITY_MISSING_FLAGS,
    *AUXILIARY_LINK_FLAGS,
)


def query202_subject_bucket(subject_id: int | None) -> int:
    """Assign one subject to the preregistered 64-way Query 202 bucket.

    SQL parity is: NULL -> 0; otherwise take the first 15 hexadecimal digits
    of ``md5('D005-K-QUERY202-v1|' || subject_id::bigint::text)``, interpret
    them as an unsigned 60-bit integer, and take modulo 64.  Fifteen digits
    avoid signed bigint conversion differences in PostgreSQL.
    """
    if subject_id is None:
        return 0
    if isinstance(subject_id, bool) or not isinstance(subject_id, int):
        raise ValueError("subject_id must be an integer or None")
    payload = f"{QUERY202_BUCKET_HASH_PREFIX}{subject_id}".encode("ascii")
    digest = hashlib.md5(payload, usedforsecurity=False).hexdigest()
    return int(digest[:15], 16) % QUERY202_BUCKET_COUNT


def validate_query202_bucket_indices(indices: list[int] | tuple[int, ...]) -> None:
    """Reject an incomplete, duplicated, reordered, or non-integer plan."""
    if list(indices) != list(range(QUERY202_BUCKET_COUNT)):
        raise ValueError("Query 202 bucket indices must be the ordered integers 0..63")


def reduce_primary_link_status(
    flags: Mapping[str, bool],
    *,
    compatible_prescription_component_count: int,
) -> str:
    """Reduce overlapping diagnostics to one preregistered primary status.

    Precedence is identity conflict, identity missing, auxiliary nonblank POE
    conflict, auxiliary POE missing, exact multi-component, then exact
    single-component.  POE remains auxiliary: its two statuses retain an
    otherwise exact subject/admission/pharmacy chain.  A zero component count
    is an identity-missing chain even if the caller omitted the redundant
    ``prescription_match_missing`` flag.
    """
    if set(flags) != set(ALL_LINK_FLAGS):
        raise ValueError("link flags must contain the exact Query 202 flag set")
    if any(type(flags[name]) is not bool for name in ALL_LINK_FLAGS):
        raise ValueError("every link flag must be bool")
    if (
        isinstance(compatible_prescription_component_count, bool)
        or not isinstance(compatible_prescription_component_count, int)
        or compatible_prescription_component_count < 0
    ):
        raise ValueError("compatible prescription component count must be a nonnegative integer")

    if any(flags[name] for name in IDENTITY_CONFLICT_FLAGS):
        return "identity_conflict"
    if (
        any(flags[name] for name in IDENTITY_MISSING_FLAGS)
        or compatible_prescription_component_count == 0
    ):
        return "identity_missing"
    if flags["nonblank_poe_conflict"]:
        return "poe_conflict_auxiliary"
    if flags["poe_missing_on_any_linked_record"]:
        return "poe_missing_auxiliary"
    if compatible_prescription_component_count > 1:
        return "exact_multiple_prescription_components"
    return "exact_single_prescription_component"


def identity_chain_status(primary_link_status: str) -> str:
    """Collapse the primary partition to the mapping reducer's three states."""
    if primary_link_status not in PRIMARY_LINK_STATUSES:
        raise ValueError("unknown primary link status")
    if primary_link_status == "identity_conflict":
        return "conflict"
    if primary_link_status == "identity_missing":
        return "missing"
    return "exact"
