"""Synthetic oracle for the proposed D003 potassium outcome rule.

This module implements ``k-observed-outcome-v1-proposed``.  It is a project
proposal whose upstream episode, action, decision-anchor, and non-ICU rules
remain unresolved; accepting a synthetic event here does not construct a
formal study label or recover the paper authors' undisclosed selector.

The primary clock is the eMAR administration-record anchor.  The prompt-only
proxy end (dose / 10 mEq per hour) and proxy target (three hours later) never
participate in this selector.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
from typing import Iterable


PROPOSED_POTASSIUM_OUTCOME_RULE = "k-observed-outcome-v1-proposed"
PROPOSED_RULE_STATUS = "proposed"
SUPPORTED_POTASSIUM_ITEMIDS = frozenset({50971, 52610})
NORMALIZED_POTASSIUM_UNIT = "mEq/L"
MAXIMUM_ANCHOR_LAG = timedelta(hours=24)


@dataclass(frozen=True)
class PotassiumLabRow:
    """One synthetic serum-potassium result row considered by the oracle.

    ``source_id`` is retained only for lineage.  It is deliberately excluded
    from equality, ordering, timestamp selection, and every quality decision.
    """

    itemid: int
    charttime: datetime
    valuenum: object
    valueuom: object
    storetime: datetime | None = None
    source_id: object = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class PotassiumOutcomeSelection:
    """Auditable result of applying the proposed rule to one synthetic event."""

    rule_version: str
    rule_status: str
    formal_label_constructed: bool
    prompt_proxy_target_used: bool
    anchor: datetime
    window_end: datetime
    selected_time: datetime | None
    selected_rows: tuple[PotassiumLabRow, ...]
    distinct_supported_finite_values: tuple[float, ...]
    candidate_normalized_value: float | None
    exclusion_reasons: tuple[str, ...]
    flags: frozenset[str]

    @property
    def accepted(self) -> bool:
        """Whether this event satisfies the proposal, not a formal protocol."""

        return self.selected_time is not None and not self.exclusion_reasons

    @property
    def normalized_value(self) -> float | None:
        """Expose a value only when the complete proposed rule accepts it."""

        return self.candidate_normalized_value if self.accepted else None


def _require_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{name} must be a datetime")
    return value


def _compare(left: datetime, right: datetime, *, names: str) -> int:
    """Compare datetimes while turning naive/aware mismatches into clear input errors."""

    try:
        if left < right:
            return -1
        if left > right:
            return 1
    except TypeError as error:
        raise ValueError(f"{names} must use mutually comparable datetimes") from error
    return 0


def _normalized_unit(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    compact = "".join(value.split()).casefold()
    return NORMALIZED_POTASSIUM_UNIT if compact == "meq/l" else None


def _finite_number(value: object) -> float | None:
    # valuenum is a numeric source field.  In particular, do not parse text or
    # accept booleans merely because float() would coerce them.
    if value is None or isinstance(value, (bool, str, bytes, bytearray, complex)):
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return normalized if math.isfinite(normalized) else None


def _row_sort_key(row: PotassiumLabRow) -> tuple[object, ...]:
    """Canonical presentation order that never consults the source row ID."""

    value = _finite_number(row.valuenum)
    if value is not None:
        value_key: tuple[object, ...] = (0, value)
    elif row.valuenum is None:
        value_key = (1, "")
    else:
        value_key = (2, type(row.valuenum).__name__, repr(row.valuenum))
    storetime_key = "" if row.storetime is None else row.storetime.isoformat()
    return (
        row.itemid,
        _normalized_unit(row.valueuom) or "",
        repr(row.valueuom),
        value_key,
        storetime_key,
    )


def select_proposed_potassium_outcome(
    anchor: datetime,
    labs: Iterable[PotassiumLabRow],
    *,
    additional_treatment_times: Iterable[datetime] = (),
    same_anchor_distinct_event: bool = False,
) -> PotassiumOutcomeSelection:
    """Apply the proposed D003-K rule to one synthetic positive-dose event.

    The selector first chooses the earliest supported potassium timestamp in
    ``(anchor, anchor + 24 hours]``.  Only then does it assess every supported
    row at that timestamp.  A bad first group is excluded rather than replaced
    by a later group.  Additional potassium treatment in
    ``(anchor, selected_time]`` also excludes the focal event.

    ``same_anchor_distinct_event`` is supplied by the still-unresolved episode
    layer.  Passing another-treatment timestamp equal to the anchor sets the
    same condition.  Either path marks the episode dependency and excludes the
    event; source row IDs are never used to resolve it.

    This synthetic oracle assumes that its inputs have already been restricted
    to the focal subject and admission.  It cannot establish that identity or
    whether the supplied treatment times cover the final accepted D005 drug
    universe.
    """

    anchor = _require_datetime(anchor, "anchor")
    if not isinstance(same_anchor_distinct_event, bool):
        raise ValueError("same_anchor_distinct_event must be a boolean")
    try:
        window_end = anchor + MAXIMUM_ANCHOR_LAG
    except OverflowError as error:
        raise ValueError("anchor cannot represent a closed 24-hour window") from error

    lab_rows = tuple(labs)
    for index, row in enumerate(lab_rows):
        if not isinstance(row, PotassiumLabRow):
            raise ValueError(f"labs[{index}] must be a PotassiumLabRow")
        if isinstance(row.itemid, bool) or not isinstance(row.itemid, int):
            raise ValueError(f"labs[{index}].itemid must be an integer")
        _require_datetime(row.charttime, f"labs[{index}].charttime")
        _compare(row.charttime, anchor, names=f"labs[{index}].charttime and anchor")
        if row.storetime is not None:
            _require_datetime(row.storetime, f"labs[{index}].storetime")
            _compare(
                row.storetime,
                row.charttime,
                names=f"labs[{index}].storetime and charttime",
            )

    treatment_times = tuple(additional_treatment_times)
    for index, timestamp in enumerate(treatment_times):
        _require_datetime(timestamp, f"additional_treatment_times[{index}]")
        _compare(
            timestamp,
            anchor,
            names=f"additional_treatment_times[{index}] and anchor",
        )

    candidate_times = {
        row.charttime
        for row in lab_rows
        if row.itemid in SUPPORTED_POTASSIUM_ITEMIDS
        and _compare(row.charttime, anchor, names="lab charttime and anchor") > 0
        and _compare(row.charttime, window_end, names="lab charttime and window end") <= 0
    }
    selected_time = min(candidate_times) if candidate_times else None
    selected_rows = tuple(
        sorted(
            (
                row
                for row in lab_rows
                if row.itemid in SUPPORTED_POTASSIUM_ITEMIDS
                and selected_time is not None
                and row.charttime == selected_time
            ),
            key=_row_sort_key,
        )
    )

    reasons: list[str] = []
    flags: set[str] = set()

    same_anchor_from_times = any(timestamp == anchor for timestamp in treatment_times)
    if same_anchor_distinct_event or same_anchor_from_times:
        reasons.append("episode_overlap_unresolved")
        flags.update(
            {"same_anchor_distinct_event", "same_anchor_episode_rule_required"}
        )

    if selected_time is None:
        reasons.append("no_lab_within_24h")
        return PotassiumOutcomeSelection(
            rule_version=PROPOSED_POTASSIUM_OUTCOME_RULE,
            rule_status=PROPOSED_RULE_STATUS,
            formal_label_constructed=False,
            prompt_proxy_target_used=False,
            anchor=anchor,
            window_end=window_end,
            selected_time=None,
            selected_rows=(),
            distinct_supported_finite_values=(),
            candidate_normalized_value=None,
            exclusion_reasons=tuple(reasons),
            flags=frozenset(flags),
        )

    flags.add("timestamp_selected_before_quality")

    treatments_in_interval = [
        timestamp
        for timestamp in treatment_times
        if _compare(timestamp, anchor, names="treatment time and anchor") > 0
        and _compare(
            timestamp,
            selected_time,
            names="treatment time and selected lab time",
        )
        <= 0
    ]
    if treatments_in_interval:
        reasons.append("additional_treatment_before_outcome")
        flags.add("additional_treatment_in_interval")
    if any(timestamp == selected_time for timestamp in treatments_in_interval):
        reasons.append("same_time_treatment_lab_order_unknown")
        flags.add("additional_treatment_at_selected_time")

    finite_supported: list[float] = []
    finite_unsupported_unit = False
    for row in selected_rows:
        finite_value = _finite_number(row.valuenum)
        if row.valuenum is None:
            flags.add("selected_group_has_missing_value")
        elif finite_value is None:
            flags.add("selected_group_has_nonfinite_value")
        elif _normalized_unit(row.valueuom) is None:
            finite_unsupported_unit = True
            flags.add("selected_group_has_finite_unsupported_unit")
        else:
            finite_supported.append(finite_value)

        if row.storetime is None:
            flags.add("selected_group_has_missing_storetime")
        elif _compare(
            row.storetime,
            row.charttime,
            names="selected lab storetime and charttime",
        ) < 0:
            flags.add("selected_group_has_reversed_storetime")

    distinct_values = tuple(sorted(set(finite_supported)))
    if not finite_supported:
        reasons.append("selected_group_no_finite_supported_value")
    if finite_unsupported_unit:
        reasons.append("selected_group_unit_unrecognized")
    if len(distinct_values) > 1:
        reasons.append("selected_group_value_conflict")
    if "selected_group_has_reversed_storetime" in flags:
        reasons.append("reversed_storetime")
    if len(finite_supported) > 1 and len(distinct_values) == 1:
        flags.add("selected_group_has_duplicate_agreeing_value")

    candidate_value = distinct_values[0] if len(distinct_values) == 1 else None
    return PotassiumOutcomeSelection(
        rule_version=PROPOSED_POTASSIUM_OUTCOME_RULE,
        rule_status=PROPOSED_RULE_STATUS,
        formal_label_constructed=False,
        prompt_proxy_target_used=False,
        anchor=anchor,
        window_end=window_end,
        selected_time=selected_time,
        selected_rows=selected_rows,
        distinct_supported_finite_values=distinct_values,
        candidate_normalized_value=candidate_value,
        exclusion_reasons=tuple(reasons),
        flags=frozenset(flags),
    )
