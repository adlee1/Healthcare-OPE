"""Evaluate the direct-method equation; do not choose a training protocol.

APRIL Section 3.3 (PDF p. 5) specifies a learned linear reward model but
omits important fitting/encoding details. This module takes supplied
action values and target-policy probabilities; it does not silently pick
those missing details, clone a policy, or train a reward model.
"""

import math
from numbers import Real
from typing import Iterable, List, Optional

from .rewards import _finite_real


PROBABILITY_SUM_TOLERANCE = 1e-9


def _finite_matrix(values: Iterable[Iterable[Real]], name: str) -> List[List[float]]:
    try:
        rows = [[_finite_real(value, name) for value in row] for row in values]
    except TypeError as error:
        raise ValueError(f"{name} must be a rectangular matrix") from error
    if not rows or not rows[0]:
        raise ValueError(f"{name} must have at least one context and one action")
    if any(len(row) != len(rows[0]) for row in rows):
        raise ValueError(f"{name} must be rectangular")
    return rows


def _validate_probabilities(probabilities: List[float], name: str) -> None:
    if any(probability < 0 or probability > 1 for probability in probabilities):
        raise ValueError(f"{name} must be in [0, 1]")
    if not math.isclose(
        math.fsum(probabilities),
        1.0,
        rel_tol=0.0,
        abs_tol=PROBABILITY_SUM_TOLERANCE,
    ):
        raise ValueError(f"{name} must sum to 1")


def direct_method(
    policy_probabilities: Iterable[Iterable[Real]],
    action_values: Iterable[Iterable[Real]],
    context_weights: Optional[Iterable[Real]] = None,
) -> float:
    """Return sum_s d0(s) sum_a pi(a|s) Q(s,a).

    Both matrices use matching context rows and matching action columns.
    The caller supplies contexts from the explicitly chosen evaluation
    population. Missing weights mean the empirical uniform distribution
    over those rows. Supplied weights must already be probabilities and
    are never silently normalized. Finite Q predictions outside [0,1]
    remain unchanged: reward-model clipping is an unresolved protocol
    choice, not part of the direct-method equation.
    """
    probabilities = _finite_matrix(policy_probabilities, "policy_probabilities")
    values = _finite_matrix(action_values, "action_values")
    if len(probabilities) != len(values) or len(probabilities[0]) != len(values[0]):
        raise ValueError("policy_probabilities and action_values must have identical shapes")
    for row in probabilities:
        _validate_probabilities(row, "policy probabilities in each context")
    if context_weights is None:
        weights = [1.0 / len(values)] * len(values)
    else:
        weights = [_finite_real(weight, "context weight") for weight in context_weights]
        if len(weights) != len(values):
            raise ValueError("context_weights must match the number of contexts")
        _validate_probabilities(weights, "context_weights")
    try:
        result = math.fsum(
            weight * math.fsum(probability * value for probability, value in zip(row, q_row))
            for weight, row, q_row in zip(weights, probabilities, values)
        )
    except OverflowError as error:
        raise ValueError("direct-method result must be finite") from error
    if not math.isfinite(result):
        raise ValueError("direct-method result must be finite")
    return result
