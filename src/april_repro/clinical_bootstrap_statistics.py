"""Summarize one layer of bootstrap errors without inventing sampling SEs.

``summarize_bootstrap_draws(records, planned_draws=500)`` accepts an iterable
of mappings. ``draw_id`` is a zero-based integer in ``[0, planned_draws)``;
``status`` is ``complete``, ``failed`` or ``pending``. Complete records require
finite real numbers in ``dm_value``, ``observed_reference_value``, and
``signed_error``. The latter must equal DM minus reference within relative
tolerance 1e-10 and absolute tolerance 1e-12. Incomplete records must omit those
three numeric fields or set them to None. Additional fields (e.g. a failure
reason) are allowed and do not affect arithmetic. Inputs are never modified.

Return schema (all values are JSON-safe):
* schema_version: ``clinical-bootstrap-statistics-v1``;
* status: ``complete`` only if all planned draws completed, else ``incomplete``;
* planned_draws / completed_draws / failed_draws / pending_draws: integer counts;
* completed_draw_ids / failed_draw_ids / pending_draw_ids: sorted integer lists.
  Missing records count as pending, as do explicit pending records;
* primary_metrics: metrics object only when every planned draw completed,
  otherwise None. A failed draw is never silently removed from its denominator;
* diagnostic_valid_draw_metrics: metrics over completed draws only when the
  run is incomplete and at least one draw completed, otherwise None;
* diagnostic_valid_draw_metrics_label: ``partial_valid_draws_only_not_primary``
  when diagnostic metrics exist, otherwise None.

Each metrics object contains ``draw_count``, ``rmse = sqrt(mean(e**2))``,
``bootstrap_se_value = sample_sd(dm_value)``, ``bootstrap_sd_error =
sample_sd(e)``, ``rmse_mc_se_delta = sample_sd(e**2)/(2*sqrt(B)*rmse)``,
``rmse_mc_se_lower_bound = max(0, rmse-rmse_mc_se_delta)``, and
``rmse_mc_se_upper_bound = rmse+rmse_mc_se_delta``. The SDs use ddof=1;
``standard_deviation_ddof`` is 1. For B<2 the SDs, MC-SE and bounds are None.
For B>=2 with every error zero, RMSE and its empirical MC-SE/bounds are zero.
``rmse_error_bar_kind`` is ``finite_B_monte_carlo_standard_error_delta``.

The delta MC-SE measures finite-B numerical uncertainty conditional on the
observed dataset and chosen bootstrap scheme. It is NOT a sampling standard
error of RMSE and does not claim to recover APRIL's undisclosed error-bar
implementation. The observed reference remains a proxy, not causal truth.
This module knows no populations: an empty population is the caller's
``not_estimable`` condition; an empty records iterable here means all pending.
No p-values, Table 2 tests, resampling, fitting, or data access occur here.
"""

from collections.abc import Iterable, Mapping
import math
from numbers import Integral, Real
from typing import Any


SCHEMA_VERSION = "clinical-bootstrap-statistics-v1"
ERROR_BAR_KIND = "finite_B_monte_carlo_standard_error_delta"
ERROR_REL_TOLERANCE = 1e-10
ERROR_ABS_TOLERANCE = 1e-12
_NUMERIC_FIELDS = ("dm_value", "observed_reference_value", "signed_error")


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite real number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite real number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite real number")
    return result


def _finite_result(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise ValueError(f"{label} exceeds finite floating-point range")
    return value


def _sample_sd(values: list[float]) -> float | None:
    """Scaled ddof=1 SD; avoid squaring otherwise representable large values."""
    if len(values) < 2:
        return None
    scale = max(abs(value) for value in values)
    if scale == 0:
        return 0.0
    scaled = [value / scale for value in values]
    mean = math.fsum(scaled) / len(scaled)
    variance = math.fsum((value - mean) ** 2 for value in scaled) / (len(scaled) - 1)
    return _finite_result(scale * math.sqrt(variance), "sample standard deviation")


def _metrics(complete: list[tuple[int, float, float]]) -> dict[str, Any]:
    count = len(complete)
    values = [value for _, value, _ in complete]
    errors = [error for _, _, error in complete]
    scale = max(abs(error) for error in errors)
    if scale == 0:
        rmse = 0.0
        mc_se = 0.0 if count >= 2 else None
    else:
        squared_scaled_errors = [(error / scale) ** 2 for error in errors]
        root_mean_scaled_square = math.sqrt(math.fsum(squared_scaled_errors) / count)
        rmse = _finite_result(scale * root_mean_scaled_square, "RMSE")
        if count < 2:
            mc_se = None
        else:
            # Algebraically identical to sd(e**2)/(2*sqrt(B)*RMSE), without
            # forming e**2, which could overflow or underflow first.
            square_sd = _sample_sd(squared_scaled_errors)
            factor = square_sd / (2 * math.sqrt(count) * root_mean_scaled_square)
            mc_se = _finite_result(scale * factor, "RMSE Monte Carlo SE")
    lower = None if mc_se is None else max(0.0, rmse - mc_se)
    upper = None if mc_se is None else _finite_result(rmse + mc_se, "RMSE upper bound")
    return {
        "draw_count": count,
        "rmse": rmse,
        "bootstrap_se_value": _sample_sd(values),
        "bootstrap_sd_error": _sample_sd(errors),
        "rmse_mc_se_delta": mc_se,
        "rmse_mc_se_lower_bound": lower,
        "rmse_mc_se_upper_bound": upper,
        "rmse_error_bar_kind": ERROR_BAR_KIND,
        "standard_deviation_ddof": 1,
    }


def summarize_bootstrap_draws(
    records: Iterable[Mapping[str, Any]], planned_draws: int = 500
) -> dict[str, Any]:
    """Validate draw identities/results and report primary or partial metrics.

    Invalid records raise ValueError. A valid failed/pending record is counted
    without raising. Completion requires exactly the planned unique draw IDs,
    all with status complete; no invalid/failed draw is replaced or dropped.
    """
    if isinstance(planned_draws, bool) or not isinstance(planned_draws, Integral) or planned_draws <= 0:
        raise ValueError("planned_draws must be a positive integer")
    planned_draws = int(planned_draws)
    seen: set[int] = set()
    complete: list[tuple[int, float, float]] = []
    failed: list[int] = []
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("each draw record must be a mapping")
        draw_id = record.get("draw_id")
        if isinstance(draw_id, bool) or not isinstance(draw_id, Integral):
            raise ValueError("draw_id must be a zero-based integer")
        draw_id = int(draw_id)
        if not 0 <= draw_id < planned_draws:
            raise ValueError("draw_id is outside the planned range")
        if draw_id in seen:
            raise ValueError(f"duplicate draw_id: {draw_id}")
        seen.add(draw_id)
        status = record.get("status")
        if status not in ("complete", "failed", "pending"):
            raise ValueError(f"draw {draw_id}: unrecognized status")
        if status != "complete":
            if any(record.get(field) is not None for field in _NUMERIC_FIELDS):
                raise ValueError(f"draw {draw_id}: incomplete records cannot carry numeric results")
            if status == "failed":
                failed.append(draw_id)
            continue
        value, reference, error = (
            _finite_number(record.get(field), f"draw {draw_id}: {field}")
            for field in _NUMERIC_FIELDS
        )
        expected_error = _finite_result(value - reference, f"draw {draw_id}: value minus reference")
        if not math.isclose(
            error, expected_error, rel_tol=ERROR_REL_TOLERANCE, abs_tol=ERROR_ABS_TOLERANCE
        ):
            raise ValueError(f"draw {draw_id}: signed_error is inconsistent with value minus reference")
        complete.append((draw_id, value, error))
    complete.sort()
    failed.sort()
    completed_ids = [draw_id for draw_id, _, _ in complete]
    terminal_ids = set(completed_ids) | set(failed)
    pending_ids = sorted(set(range(planned_draws)) - terminal_ids)
    finished = len(complete) == planned_draws
    metrics = _metrics(complete) if complete else None
    partial = metrics if complete and not finished else None
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete" if finished else "incomplete",
        "planned_draws": planned_draws,
        "completed_draws": len(complete),
        "failed_draws": len(failed),
        "pending_draws": len(pending_ids),
        "completed_draw_ids": completed_ids,
        "failed_draw_ids": failed,
        "pending_draw_ids": pending_ids,
        "primary_metrics": metrics if finished else None,
        "diagnostic_valid_draw_metrics": partial,
        "diagnostic_valid_draw_metrics_label": "partial_valid_draws_only_not_primary" if partial else None,
    }
