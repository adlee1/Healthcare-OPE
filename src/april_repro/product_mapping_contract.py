"""Pure reducers for the proposed D005 potassium product-mapping contract.

These functions do not read MIMIC, decide product identities, or enable a
source policy.  They make the preregistered three-state logic executable so
Query 202 cannot silently choose favorable evidence across memberships or
physical components.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import product
from typing import Any


SEMANTIC_DIMENSIONS = (
    "product_identity",
    "dosage_form",
    "treatment_intent",
    "potassium_content",
    "meq_convertibility",
)
SEMANTIC_STATUSES = frozenset({"supported", "refuted", "uncertain"})
DOMAIN_STATUSES = frozenset({"yes", "no", "uncertain"})
COMPONENT_ROLES = frozenset({"product", "nonproduct", "uncertain"})
IDENTITY_CHAIN_STATUSES = frozenset({"exact", "missing", "conflict"})

ROUTE_CATEGORIES = {
    (False, False, False): "missing",
    (False, False, True): "unknown_only",
    (True, False, False): "iv_only",
    (True, False, True): "iv_plus_unknown",
    (False, True, False): "noniv_only",
    (False, True, True): "noniv_plus_unknown",
    (True, True, False): "iv_noniv_conflict",
    (True, True, True): "iv_noniv_unknown_conflict",
}


def _semantic_decision(value: Mapping[str, Any]) -> dict[str, str]:
    if set(value) != set(SEMANTIC_DIMENSIONS):
        raise ValueError("semantic decision must contain the exact five dimensions")
    result: dict[str, str] = {}
    for dimension in SEMANTIC_DIMENSIONS:
        status = value[dimension]
        if status not in SEMANTIC_STATUSES:
            raise ValueError(f"invalid status for {dimension}")
        result[dimension] = str(status)
    return result


def uncertain_semantics() -> dict[str, str]:
    return {dimension: "uncertain" for dimension in SEMANTIC_DIMENSIONS}


def route_category(*, has_iv: bool, has_noniv: bool, has_unknown: bool) -> str:
    """Return the complete three-presence-bit direct-detail route partition."""
    if any(type(item) is not bool for item in (has_iv, has_noniv, has_unknown)):
        raise ValueError("route presence flags must be bool")
    return ROUTE_CATEGORIES[(has_iv, has_noniv, has_unknown)]


def event_route_status(category: str) -> str:
    """Map a direct-detail route category to supported/refuted/uncertain."""
    if category not in ROUTE_CATEGORIES.values():
        raise ValueError("unknown route category")
    if category == "iv_only":
        return "supported"
    if category == "noniv_only":
        return "refuted"
    return "uncertain"


def reduce_component_semantics(
    membership_decisions: Sequence[Mapping[str, Any]],
    *,
    mapping_group_ids: Sequence[str | None] | None = None,
    group_decision: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Reduce semantic memberships without cross-membership cherry-picking.

    A single membership is copied.  Multiple memberships use a group-level
    decision only when every membership names the same explicit, nonblank
    mapping group.  Every unresolved multi-membership case becomes uncertain
    in all five dimensions.
    """
    decisions = [_semantic_decision(item) for item in membership_decisions]
    if not decisions:
        return uncertain_semantics()
    if len(decisions) == 1:
        if group_decision is not None:
            raise ValueError("single membership must not be replaced by a group decision")
        return decisions[0]
    if mapping_group_ids is None or len(mapping_group_ids) != len(decisions):
        if group_decision is not None:
            raise ValueError("group decision requires one group id per membership")
        return uncertain_semantics()
    explicit = [
        item if isinstance(item, str) and item.strip() else None
        for item in mapping_group_ids
    ]
    one_group = explicit[0] is not None and all(item == explicit[0] for item in explicit)
    if not one_group:
        if group_decision is not None:
            raise ValueError("group decision requires one explicit common mapping group")
        return uncertain_semantics()
    if group_decision is None:
        return uncertain_semantics()
    return _semantic_decision(group_decision)


def reduce_component_domains(
    semantics: Mapping[str, Any],
    *,
    event_route: str,
    identity_chain: str,
    component_role: str,
) -> dict[str, str]:
    """Compute component-level focal and interference statuses."""
    decision = _semantic_decision(semantics)
    if event_route not in SEMANTIC_STATUSES:
        raise ValueError("invalid event route status")
    if identity_chain not in IDENTITY_CHAIN_STATUSES:
        raise ValueError("invalid identity-chain status")
    if component_role not in COMPONENT_ROLES:
        raise ValueError("invalid component role")
    if component_role == "nonproduct":
        return {"focal": "no", "interference": "no"}

    required = [decision[key] for key in SEMANTIC_DIMENSIONS]
    required.append(event_route)
    required.append(
        "supported" if identity_chain == "exact"
        else "refuted" if identity_chain == "conflict"
        else "uncertain"
    )
    if all(item == "supported" for item in required):
        focal = "yes"
    elif any(item == "refuted" for item in required):
        focal = "no"
    else:
        focal = "uncertain"

    potassium = decision["potassium_content"]
    if potassium == "refuted":
        interference = "no"
    elif identity_chain == "exact" and event_route == "refuted":
        interference = "no"
    elif (
        potassium == "supported"
        and identity_chain == "exact"
        and event_route == "supported"
    ):
        interference = "yes"
    else:
        interference = "uncertain"
    if focal == "yes" and interference != "yes":
        raise ValueError("component focal domain is not a subset of interference")
    return {"focal": focal, "interference": interference}


def reduce_head_domains(components: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Reduce physical components to event-head focal/interference domains."""
    possible: list[Mapping[str, Any]] = []
    for component in components:
        role = component.get("component_role")
        focal = component.get("focal")
        interference = component.get("interference")
        potassium = component.get("potassium_content")
        if role not in COMPONENT_ROLES:
            raise ValueError("invalid component role")
        if focal not in DOMAIN_STATUSES or interference not in DOMAIN_STATUSES:
            raise ValueError("invalid component domain status")
        if potassium not in SEMANTIC_STATUSES:
            raise ValueError("invalid component potassium-content status")
        if focal == "yes" and interference != "yes":
            raise ValueError("component focal domain is not a subset of interference")
        if role == "nonproduct":
            if focal != "no" or interference != "no":
                raise ValueError("nonproduct component cannot enter either domain")
            continue
        possible.append(component)

    if not possible:
        return {"focal": "uncertain", "interference": "uncertain"}

    if any(item["focal"] == "yes" for item in possible) and all(
        item["focal"] == "yes" or item["potassium_content"] == "refuted"
        for item in possible
    ):
        focal = "yes"
    elif not any(item["focal"] == "yes" for item in possible) and all(
        item["focal"] == "no" for item in possible
    ):
        focal = "no"
    else:
        focal = "uncertain"

    if any(item["interference"] == "yes" for item in possible):
        interference = "yes"
    elif all(item["interference"] == "no" for item in possible):
        interference = "no"
    else:
        interference = "uncertain"
    if focal == "yes" and interference != "yes":
        raise ValueError("head focal domain is not a subset of interference")
    return {"focal": focal, "interference": interference}


def enumerate_route_partition() -> tuple[str, ...]:
    """Return all eight categories through the production reducer."""
    return tuple(route_category(has_iv=a, has_noniv=b, has_unknown=c)
                 for a, b, c in product((False, True), repeat=3))
