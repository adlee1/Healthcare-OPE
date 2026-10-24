"""Transparent metrics for the APRIL reproduction, using standard Python.

RMSE is sqrt(mean(squared signed errors)), never mean absolute error.
Entropy is the empirical marginal action entropy in natural-log units;
it is not a measure of annotation quality or conditional coverage.
"""

import math
from numbers import Integral, Real
from typing import Iterable, List, Union

from .rewards import F1_BOUNDARIES, Task, _finite_real, _validate_task, bin_lab_value


def weighted_f1(
    true_labels: Iterable[int],
    predicted_labels: Iterable[int],
    *,
    num_classes: int,
) -> float:
    """Support-weighted multiclass F1 with explicit fixed class count.

    Classes absent from the truth have zero weight. A class with no true
    or predicted instances has F1=0 (zero-division convention). Predictions
    in an absent class still create false negatives for their true class.
    """
    if isinstance(num_classes, bool) or not isinstance(num_classes, Integral):
        raise ValueError("num_classes must be a positive integer")
    if num_classes <= 0:
        raise ValueError("num_classes must be a positive integer")
    truth, prediction = list(true_labels), list(predicted_labels)
    if not truth or len(truth) != len(prediction):
        raise ValueError("true and predicted labels must have equal nonzero lengths")
    for label in truth + prediction:
        if (
            isinstance(label, bool)
            or not isinstance(label, Integral)
            or not 0 <= label < num_classes
        ):
            raise ValueError("labels must be integers in [0, num_classes)")
    support = [0] * num_classes
    predicted_count = [0] * num_classes
    true_positive = [0] * num_classes
    for actual, predicted in zip(truth, prediction):
        support[actual] += 1
        predicted_count[predicted] += 1
        if actual == predicted:
            true_positive[actual] += 1
    sample_count = len(truth)
    return math.fsum(
        (support[label] / sample_count)
        * (2 * true_positive[label] / (support[label] + predicted_count[label]))
        for label in range(num_classes)
        if support[label] + predicted_count[label] > 0
    )


def lab_weighted_f1(
    observed: Iterable[Real], predicted: Iterable[Real], task: Task
) -> float:
    """Bin observed and predicted labs using Appendix A, then compute F1."""
    _validate_task(task)
    return weighted_f1(
        [bin_lab_value(value, task) for value in observed],
        [bin_lab_value(value, task) for value in predicted],
        num_classes=len(F1_BOUNDARIES[task]) + 1,
    )


def _paired_errors(
    estimates: Iterable[Real], references: Union[Real, Iterable[Real]]
) -> List[float]:
    estimates_list = [_finite_real(value, "estimate") for value in estimates]
    if not estimates_list:
        raise ValueError("estimates must be nonempty")
    if isinstance(references, Real):
        reference = _finite_real(references, "reference")
        references_list = [reference] * len(estimates_list)
    else:
        references_list = [_finite_real(value, "reference") for value in references]
    if len(estimates_list) != len(references_list):
        raise ValueError("estimates and references must have equal lengths")
    errors = [estimate - reference for estimate, reference in zip(estimates_list, references_list)]
    if not all(math.isfinite(error) for error in errors):
        raise ValueError("signed errors must be finite")
    return errors


def rmse(estimates: Iterable[Real], references: Union[Real, Iterable[Real]]) -> float:
    """Root mean squared error against one reference or paired references."""
    errors = _paired_errors(estimates, references)
    # Divide before the norm so representable RMSEs do not overflow simply
    # because the unnormalized sum of squares would overflow.
    denominator = math.sqrt(len(errors))
    return math.hypot(*(error / denominator for error in errors))


def bias(estimates: Iterable[Real], references: Union[Real, Iterable[Real]]) -> float:
    """Mean signed error, with sign estimate minus reference."""
    errors = _paired_errors(estimates, references)
    return math.fsum(error / len(errors) for error in errors)


def marginal_entropy(action_counts: Iterable[int]) -> float:
    """Compute -sum(p * ln(p)) from nonnegative integer action counts.

    Include zero counts for unobserved actions if retaining the full action
    space. At least one observed action is required. Duplicated rows count
    as rows; the caller must distinguish them from unique annotations.
    """
    counts = list(action_counts)
    if not counts:
        raise ValueError("action_counts must be nonempty")
    if any(
        isinstance(count, bool) or not isinstance(count, Integral) or count < 0
        for count in counts
    ):
        raise ValueError("action counts must be nonnegative integers")
    total = sum(counts)
    if total == 0:
        raise ValueError("at least one action count must be positive")
    probabilities = [count / total for count in counts if count]
    return -math.fsum(probability * math.log(probability) for probability in probabilities)
