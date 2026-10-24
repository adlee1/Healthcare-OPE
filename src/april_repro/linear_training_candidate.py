"""Small, dependency-free weighted OLS candidate for synthetic validation.

This module does not select features, add an intercept, scale an input design
semantically, or define a clinical cohort. Callers supply the complete design
matrix and explicit weights and rank tolerance. Internal column equilibration
is reversed before coefficients are returned.

The solver uses column-pivoted, reorthogonalized modified Gram--Schmidt QR,
not normal equations. It rejects a numerically rank-deficient design instead
of computing a pseudoinverse. This is a small synthetic numerical candidate;
it is not a production rank-deficiency policy or a frozen experiment method.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Set
from dataclasses import dataclass
import math
from numbers import Real


_ERROR = "Invalid or numerically unsupported linear training input."


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(_ERROR)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(_ERROR)
    return result


def _items(values: object) -> tuple:
    if isinstance(values, (str, bytes, bytearray, Mapping, Set)):
        raise ValueError(_ERROR)
    return tuple(values)  # type: ignore[arg-type]


def _matrix(design: object) -> tuple[tuple[float, ...], ...]:
    rows = tuple(tuple(_number(value) for value in _items(row))
                 for row in _items(design))
    if not rows or not rows[0]:
        raise ValueError(_ERROR)
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError(_ERROR)
    return rows


def _finite(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError(_ERROR)
    return value


def _dot(left: Iterable[float], right: Iterable[float]) -> float:
    return _finite(math.fsum(_finite(a * b) for a, b in zip(left, right)))


def _norm(values: list[float]) -> float:
    return _finite(math.hypot(*values))


def _remove_projection(
    vector: list[float], direction: list[float], coefficient: float
) -> list[float]:
    return [_finite(value - _finite(coefficient * basis))
            for value, basis in zip(vector, direction)]


def _unscale(value: float, norm: float, scale: float) -> float:
    """Compute value / (norm * scale) without a large intermediate product."""
    if value == 0.0:
        return 0.0
    value_mantissa, value_exponent = math.frexp(value)
    norm_mantissa, norm_exponent = math.frexp(norm)
    scale_mantissa, scale_exponent = math.frexp(scale)
    result = _finite(math.ldexp(
        value_mantissa / (norm_mantissa * scale_mantissa),
        value_exponent - norm_exponent - scale_exponent,
    ))
    if result == 0.0:
        # A nonzero coefficient outside the floating-point range is unsupported.
        raise ValueError(_ERROR)
    return result


@dataclass(frozen=True)
class LinearFit:
    """OLS coefficients in the caller's original design-column order.

    ``n_rows`` counts supplied rows, not the sum of their weights.
    Predictions intentionally retain values outside the training reward range.
    """

    coefficients: tuple[float, ...]
    n_rows: int
    n_columns: int

    def __post_init__(self) -> None:
        try:
            coefficients = tuple(_number(value) for value in _items(self.coefficients))
            if (isinstance(self.n_rows, bool)
                    or isinstance(self.n_columns, bool)
                    or not isinstance(self.n_rows, int)
                    or not isinstance(self.n_columns, int)
                    or self.n_columns < 1
                    or self.n_rows < self.n_columns
                    or len(coefficients) != self.n_columns):
                raise ValueError(_ERROR)
            object.__setattr__(self, "coefficients", coefficients)
        except (ArithmeticError, TypeError, ValueError):
            raise ValueError(_ERROR) from None

    def predict(self, design: Iterable[Iterable[float]]) -> tuple[float, ...]:
        """Predict from a nonempty matrix with exactly ``n_columns`` columns."""
        try:
            rows = _matrix(design)
            if len(rows[0]) != self.n_columns:
                raise ValueError(_ERROR)
            return tuple(_dot(row, self.coefficients) for row in rows)
        except (ArithmeticError, TypeError, ValueError):
            raise ValueError(_ERROR) from None


def fit_ols(
    design: Iterable[Iterable[float]],
    rewards: Iterable[float],
    *,
    sample_weights: Iterable[float],
    rank_tolerance: float,
) -> LinearFit:
    """Fit explicit-design weighted least squares to rewards in ``[0, 1]``.

    All weights must be finite and positive. Uniformly rescaling weights does
    not alter the objective's minimizer. A multiplicity weight can therefore
    stand for repeated identical rows, while ``n_rows`` remains the input count.

    ``rank_tolerance`` must be finite with ``0 < tolerance < 1``. It is an
    absolute residual-column-norm threshold after every weighted design column
    has been equilibrated to unit norm. Tolerances below machine epsilon times
    ``max(n_rows, n_columns)`` are rejected: the solver does not silently replace
    an explicit tolerance with a safer value. Rank deficiency, unsupported
    numerical range, and invalid inputs raise a value-free ``ValueError``.
    """
    try:
        rows = _matrix(design)
        response = tuple(_number(value) for value in _items(rewards))
        weights = tuple(_number(value) for value in _items(sample_weights))
        tolerance = _number(rank_tolerance)
        n_rows, n_columns = len(rows), len(rows[0])
        if (n_rows < n_columns
                or len(response) != n_rows
                or len(weights) != n_rows
                or any(value < 0.0 or value > 1.0 for value in response)
                or any(value <= 0.0 for value in weights)
                or not 0.0 < tolerance < 1.0
                or tolerance < math.ulp(1.0) * max(n_rows, n_columns)):
            raise ValueError(_ERROR)

        # Square roots before division avoid underflow of a tiny w / max(w).
        max_weight_root = math.sqrt(max(weights))
        weight_roots = tuple(math.sqrt(weight) / max_weight_root for weight in weights)
        weighted_response = tuple(value * root
                                  for value, root in zip(response, weight_roots))
        scales: list[float] = []
        norms: list[float] = []
        columns: list[list[float]] = []
        for column_index in range(n_columns):
            scale = max(abs(row[column_index]) for row in rows)
            if scale == 0.0:
                raise ValueError(_ERROR)
            weighted_column = [
                (row[column_index] / scale) * root
                for row, root in zip(rows, weight_roots)
            ]
            norm = _norm(weighted_column)
            if norm == 0.0:
                raise ValueError(_ERROR)
            scales.append(scale)
            norms.append(norm)
            columns.append([_finite(value / norm) for value in weighted_column])

        order = list(range(n_columns))
        upper = [[0.0] * n_columns for _ in range(n_columns)]
        orthogonal: list[list[float]] = []
        transformed_response: list[float] = []
        for column_index in range(n_columns):
            pivot = max(range(column_index, n_columns),
                        key=lambda index: _norm(columns[index]))
            columns[column_index], columns[pivot] = columns[pivot], columns[column_index]
            order[column_index], order[pivot] = order[pivot], order[column_index]
            for previous in range(column_index):
                upper[previous][column_index], upper[previous][pivot] = (
                    upper[previous][pivot], upper[previous][column_index]
                )

            current = columns[column_index]
            # Reorthogonalize the selected residual against all prior columns.
            for previous, basis in enumerate(orthogonal):
                correction = _dot(basis, current)
                current = _remove_projection(current, basis, correction)
                upper[previous][column_index] = _finite(
                    upper[previous][column_index] + correction
                )
            diagonal = _norm(current)
            if diagonal <= tolerance:
                raise ValueError(_ERROR)
            upper[column_index][column_index] = diagonal
            basis = [_finite(value / diagonal) for value in current]
            orthogonal.append(basis)
            transformed_response.append(_dot(basis, weighted_response))

            for remaining in range(column_index + 1, n_columns):
                first = _dot(basis, columns[remaining])
                residual = _remove_projection(columns[remaining], basis, first)
                second = _dot(basis, residual)
                columns[remaining] = _remove_projection(residual, basis, second)
                upper[column_index][remaining] = _finite(first + second)

        pivoted_coefficients = [0.0] * n_columns
        for row_index in range(n_columns - 1, -1, -1):
            products = [
                _finite(upper[row_index][column_index]
                        * pivoted_coefficients[column_index])
                for column_index in range(row_index + 1, n_columns)
            ]
            remainder = _finite(math.fsum(
                [transformed_response[row_index], *(-value for value in products)]
            ))
            pivoted_coefficients[row_index] = _finite(
                remainder / upper[row_index][row_index]
            )

        coefficients = [0.0] * n_columns
        for pivot_index, original_index in enumerate(order):
            coefficients[original_index] = _unscale(
                pivoted_coefficients[pivot_index],
                norms[original_index],
                scales[original_index],
            )
        return LinearFit(tuple(coefficients), n_rows, n_columns)
    except (ArithmeticError, TypeError, ValueError):
        raise ValueError(_ERROR) from None
