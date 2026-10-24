"""Lab rewards and evaluation categories transcribed from APRIL.

Source: Mandyam et al., APRIL, main-text Section 3.1 (PDF p. 4) and
Appendix A / Figure 4 (PDF p. 17). The printed formula uses sigma=2.5
for both tasks. The plotted potassium curve appears inconsistent with
that scale; this module follows the printed formula, not the plot.

The F1 categories differ from the reward reference ranges. All lab
values and reference boundaries are in mEq/L.
"""

import math
from numbers import Real
from typing import Literal


Task = Literal["potassium", "sodium"]
PAPER_REWARD_SIGMA = 2.5
REFERENCE_RANGES = {"potassium": (3.5, 4.5), "sodium": (135.0, 145.0)}
F1_BOUNDARIES = {
    "potassium": (3.2, 5.0, 6.0),
    "sodium": (118.0, 135.0, 152.0, 169.0),
}


def _finite_real(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{name} must be a finite real number") from error
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite real number")
    return result


def _validate_task(task: Task) -> None:
    if not isinstance(task, str) or task not in REFERENCE_RANGES:
        raise ValueError("task must be 'potassium' or 'sodium'")


def reward_from_lab(
    value: Real, task: Task, *, sigma: Real = PAPER_REWARD_SIGMA
) -> float:
    """Return the bounded reward from the paper's piecewise formula.

    sigma=2.5 is the published main-text specification. A different
    sigma is an explicit sensitivity-analysis setting, not a verified
    reconstruction of the conflicting potassium figure.
    """
    _validate_task(task)
    lab = _finite_real(value, "value")
    scale = _finite_real(sigma, "sigma")
    if scale <= 0:
        raise ValueError("sigma must be positive")
    lower, upper = REFERENCE_RANGES[task]
    if lower <= lab <= upper:
        return 1.0
    distance = lower - lab if lab < lower else lab - upper
    scaled_distance = distance / scale
    # Multiplication permits natural underflow to zero for distant finite
    # lab values, without the OverflowError caused by float exponentiation.
    return math.exp(-0.5 * scaled_distance * scaled_distance)


def bin_lab_value(value: Real, task: Task) -> int:
    """Return the zero-based Appendix A F1 class; thresholds go right.

    Potassium: <3.2, [3.2,5), [5,6), >=6.
    Sodium: <118, [118,135), [135,152), [152,169), >=169.
    """
    _validate_task(task)
    lab = _finite_real(value, "value")
    return sum(lab >= boundary for boundary in F1_BOUNDARIES[task])
