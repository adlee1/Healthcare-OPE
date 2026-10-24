"""Paired DM/DM+ bootstrap arithmetic for the adopted D007 local protocol.

Inputs use the original clinical bootstrap record schema: ``draw_id``,
``status``, ``dm_value``, ``observed_reference_value``, and ``signed_error``.
The DM+ list also names its estimate ``dm_value`` for compatibility with the
existing single-method statistics helper. Pairing is by integer draw ID, never
list order. Complete pairs must have exactly matching references and matching
``pair_metadata``, ``population_draw_metadata``, ``task``, ``split`` and ``seed``
whenever either member supplies those fields. The caller binds the metadata to
the resampled populations, policy, preprocessing and input artifacts. This
module cannot independently verify those source artifacts.

Every planned ID remains in the denominator. Only all planned complete pairs
produce primary metrics; a failed member makes a pair failed, and any other
missing member makes it pending. Partial valid-pair arithmetic is explicitly
diagnostic and does not replace the complete experiment.

RMSE and its finite-B Monte Carlo SE reuse clinical_bootstrap_statistics.
The two-sided paired t-test compares per-draw squared errors, DM minus DM+.
It describes the conditional bootstrap distribution, not 500 independent new
patient cohorts or the undisclosed original APRIL Table 2 implementation.
The 95% percentile interval instead describes paired absolute-error gain;
it is not a confidence interval of the RMSE difference. Positive gain favors
DM+. The proportion of positive gains is descriptive, not a p-value.

All-zero squared-error differences have t=0,p=1. Constant nonzero differences
are explicitly degenerate with t/p=None. No patient-level data access,
resampling, fitting, LLM requests or multiple-testing adjustment occurs here.
"""

from collections.abc import Iterable, Mapping
import math
from numbers import Real
from typing import Any

from .clinical_bootstrap_statistics import summarize_bootstrap_draws


SCHEMA_VERSION = "clinical-dmplus-bootstrap-statistics-v1"
TEST_INTERPRETATION = "conditional_bootstrap_distribution_monte_carlo_comparison"
GAIN_INTERVAL_KIND = "approximate_percentile_interval_for_absolute_point_error_gain"


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a finite real number")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite real number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite real number")
    return result


def _mean(values: list[float]) -> float:
    # Divide before summing so representable means need not overflow in a sum.
    return _finite(math.fsum(value / len(values) for value in values), "mean")


def _sample_sd(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    scale = max(abs(value) for value in values)
    if scale == 0:
        return 0.0
    scaled = [value / scale for value in values]
    center = _mean(scaled)
    variance = math.fsum((value - center) ** 2 for value in scaled) / (len(values) - 1)
    return _finite(scale * math.sqrt(variance), "sample standard deviation")


def _test(dm_squares: list[float], plus_squares: list[float], gains: list[float], alpha: float) -> dict[str, Any]:
    import numpy as np
    from scipy.stats import ttest_rel

    count = len(gains)
    base = {
        "scores": "per_draw_squared_error_dm_minus_dmplus",
        "alternative": "two-sided",
        "positive_statistic_favors": "dmplus",
        "interpretation": TEST_INTERPRETATION,
        "alpha": alpha,
        "multiple_testing_adjustment": "none",
        "df": count - 1,
    }
    if count < 2:
        status, statistic, pvalue = "insufficient_draws", None, None
    elif all(gain == 0.0 for gain in gains):
        status, statistic, pvalue = "all_zero_difference", 0.0, 1.0
    elif all(gain == gains[0] for gain in gains):
        status, statistic, pvalue = "degenerate_constant_nonzero_difference", None, None
    else:
        # Scaling both samples by a common positive constant leaves t and p
        # unchanged and avoids variance underflow for very small errors.
        scale = max(max(dm_squares), max(plus_squares))
        result = ttest_rel(
            np.asarray(dm_squares, dtype=float) / scale,
            np.asarray(plus_squares, dtype=float) / scale,
            alternative="two-sided", nan_policy="raise",
        )
        statistic = _finite(result.statistic, "paired t statistic")
        pvalue = _finite(result.pvalue, "paired t p value")
        if not 0 <= pvalue <= 1:
            raise ValueError("paired t p value must be in [0, 1]")
        status = "complete"
    return {
        **base, "status": status, "statistic": statistic, "pvalue": pvalue,
        "reject_null_at_alpha": None if pvalue is None else pvalue < alpha,
    }


def _metrics(dm: list[dict[str, Any]], plus: list[dict[str, Any]], planned_draws: int, alpha: float) -> dict[str, Any]:
    import numpy as np

    method_metrics = []
    for records in (dm, plus):
        single = summarize_bootstrap_draws(records, planned_draws)
        method_metrics.append(single["primary_metrics"] or single["diagnostic_valid_draw_metrics"])
    dm_errors = [float(record["signed_error"]) for record in dm]
    plus_errors = [float(record["signed_error"]) for record in plus]
    dm_squares = [_finite(error * error, "DM squared error") for error in dm_errors]
    plus_squares = [_finite(error * error, "DM+ squared error") for error in plus_errors]
    squared_gains = [_finite(a - b, "squared-error gain") for a, b in zip(dm_squares, plus_squares)]
    absolute_gains = [_finite(abs(a) - abs(b), "absolute-error gain") for a, b in zip(dm_errors, plus_errors)]
    lower, median, upper = [
        _finite(value, "absolute-error gain percentile")
        for value in np.percentile(absolute_gains, [2.5, 50.0, 97.5], method="linear")
    ]
    return {
        "draw_count": len(dm),
        "dm": method_metrics[0],
        "dmplus": method_metrics[1],
        "rmse_gain": _finite(method_metrics[0]["rmse"] - method_metrics[1]["rmse"], "RMSE gain"),
        "rmse_gain_direction": "positive_favors_dmplus",
        "squared_error_gain": {"mean": _mean(squared_gains), "sample_sd": _sample_sd(squared_gains)},
        "paired_t_test": _test(dm_squares, plus_squares, squared_gains, alpha),
        "absolute_error_gain": {
            "mean": _mean(absolute_gains), "median": median,
            "sample_sd": _sample_sd(absolute_gains),
            "percentile_95_lower": lower, "percentile_95_upper": upper,
            "percentile_levels": [2.5, 97.5], "percentile_method": "linear",
            "interval_kind": GAIN_INTERVAL_KIND,
            "interval_is_rmse_difference_ci": False,
            "positive_gain_fraction": sum(gain > 0 for gain in absolute_gains) / len(absolute_gains),
            "positive_gain_fraction_is_pvalue": False,
            "positive_gain_favors": "dmplus",
        },
    }


def _full_point(full_point: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if full_point is None:
        return None
    if not isinstance(full_point, Mapping):
        raise ValueError("full_point must be a mapping or None")
    dm, plus, reference = (
        _finite(full_point.get(key), f"full_point {key}")
        for key in ("dm_value", "dmplus_value", "observed_reference_value")
    )
    dm_error = _finite(dm - reference, "full_point DM error")
    plus_error = _finite(plus - reference, "full_point DM+ error")
    return {
        "dm_value": dm, "dmplus_value": plus, "observed_reference_value": reference,
        "dm_signed_error": dm_error, "dmplus_signed_error": plus_error,
        "absolute_error_gain": _finite(abs(dm_error) - abs(plus_error), "full_point absolute-error gain"),
        "positive_gain_favors": "dmplus",
    }


def summarize_paired_bootstrap_draws(
    dm_records: Iterable[Mapping[str, Any]],
    dmplus_records: Iterable[Mapping[str, Any]],
    planned_draws: int = 500,
    *,
    full_point: Mapping[str, Any] | None = None,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Validate and summarize all planned pairs without dropping failures.

    Pair metadata is optional only because historical original DM records lack
    it; the runner attaches its verified metadata to both transformed lists.
    Mismatched complete-pair metadata (including missing on one side) and
    references raise. Incomplete pairs preserve failures even if a failed
    record lacks metadata after an unexpected exception.
    Incomplete numeric records, duplicate/out-of-range IDs, nonfinite values
    and inconsistent signed errors are rejected by the shared validator.
    """
    alpha = _finite(alpha, "alpha")
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    methods = []
    accounting = []
    for records in (dm_records, dmplus_records):
        materialized = list(records)
        summary = summarize_bootstrap_draws(materialized, planned_draws)
        accounting.append({
            key: summary[key] for key in (
                "completed_draws", "failed_draws", "pending_draws",
                "completed_draw_ids", "failed_draw_ids", "pending_draw_ids",
            )
        })
        methods.append({int(record["draw_id"]): dict(record) for record in materialized})
    planned_draws = int(planned_draws)
    complete_dm, complete_plus = [], []
    complete_ids, failed_ids, pending_ids = [], [], []
    for draw_id in range(planned_draws):
        dm, plus = (method.get(draw_id, {"draw_id": draw_id, "status": "pending"}) for method in methods)
        statuses = (dm["status"], plus["status"])
        if statuses == ("complete", "complete"):
            for field in ("pair_metadata", "population_draw_metadata", "task", "split", "seed"):
                if field in dm or field in plus:
                    if field not in dm or field not in plus or dm[field] != plus[field]:
                        raise ValueError(f"draw {draw_id}: {field} does not match")
            if float(dm["observed_reference_value"]) != float(plus["observed_reference_value"]):
                raise ValueError(f"draw {draw_id}: paired observed references do not match exactly")
            for original_field, dm_field in (("original_dm_value", "dm_value"), ("original_dm_signed_error", "signed_error")):
                if original_field in plus and _finite(plus[original_field], original_field) != float(dm[dm_field]):
                    raise ValueError(f"draw {draw_id}: {original_field} does not match original DM")
            complete_ids.append(draw_id)
            complete_dm.append(dm)
            complete_plus.append(plus)
        elif "failed" in statuses:
            failed_ids.append(draw_id)
        else:
            pending_ids.append(draw_id)
    complete = len(complete_ids) == planned_draws
    metrics = _metrics(complete_dm, complete_plus, planned_draws, alpha) if complete_ids else None
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete" if complete else "incomplete",
        "planned_draws": planned_draws, "completed_draws": len(complete_ids),
        "failed_draws": len(failed_ids), "pending_draws": len(pending_ids),
        "completed_draw_ids": complete_ids, "failed_draw_ids": failed_ids, "pending_draw_ids": pending_ids,
        "method_draw_accounting": {"dm": accounting[0], "dmplus": accounting[1]},
        "primary_metrics": metrics if complete else None,
        "diagnostic_valid_pair_metrics": metrics if not complete else None,
        "diagnostic_valid_pair_metrics_label": "partial_valid_pairs_only_not_primary" if metrics and not complete else None,
        "full_point_metrics": _full_point(full_point),
        "paired_test_interpretation": TEST_INTERPRETATION,
        "author_table2_algorithm_recovered": False,
        "reference_is_causal_ground_truth": False,
    }
