"""Synthetic candidate for paired DM/DM+ reward training (D006/D007/D011).

The caller supplies the complete design matrix, action order, source/protocol,
weights and fixed evaluation policy/d0. No clinical schema, policy fitting,
preprocessing, bootstrap, clipping or formal experiment is implemented here.
"""
from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import dataclass
import math
from typing import Iterable

from .estimators import direct_method
from .linear_training_candidate import LinearFit, fit_ols
from .rewards import _finite_real


@dataclass(frozen=True)
class FactualRow:
    event_id: str
    subject_id: str
    action: int
    design: tuple[float, ...]
    reward: float
    weight: float


@dataclass(frozen=True)
class AnnotationRow:
    annotation_id: str
    event_id: str
    action: int
    source_id: str
    protocol_id: str
    design: tuple[float, ...]
    reward: float
    weight: float


@dataclass(frozen=True)
class EvaluationRow:
    context_id: str
    subject_id: str
    action_designs: tuple[tuple[float, ...], ...]
    policy_probabilities: tuple[float, ...]
    weight: float


@dataclass(frozen=True)
class BudgetResult:
    annotation_budget: int
    annotation_ids: tuple[str, ...]
    unique_event_action_pairs: int
    annotation_rows: int
    source_count: int
    training_rows: int
    training_weight_sum: float
    dm_value: float
    dm_plus_value: float
    dm_plus_model: LinearFit


@dataclass(frozen=True)
class PairedCandidateRun:
    baseline_model: LinearFit
    results: tuple[BudgetResult, ...]
    factual_event_ids: tuple[str, ...]
    evaluation_context_ids: tuple[str, ...]
    design_columns: tuple[str, ...]
    actions: tuple[int, ...]
    annotation_source_id: str
    annotation_protocol_id: str


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Identifiers must be nonempty strings")
    return value


def _sequence(value: Iterable) -> tuple:
    if isinstance(value, (str, bytes, bytearray, Mapping, Set)):
        raise ValueError("An ordered iterable is required")
    try:
        return tuple(value)
    except TypeError:
        raise ValueError("An iterable of rows or values is required") from None


def _design(value: Iterable, width: int) -> tuple[float, ...]:
    result = tuple(_finite_real(x, "design value") for x in _sequence(value))
    if len(result) != width:
        raise ValueError("Design width does not match the declared columns")
    return result


def _reward_weight(reward: float, weight: float) -> tuple[float, float]:
    y = _finite_real(reward, "reward")
    w = _finite_real(weight, "training weight")
    if not 0 <= y <= 1 or w <= 0:
        raise ValueError("Rewards must be in [0,1] and training weights positive")
    return y, w


def _weight_sum(weights: Iterable[float]) -> float:
    try:
        result = math.fsum(weights)
    except OverflowError:
        raise ValueError("Total training weight must be finite") from None
    if not math.isfinite(result):
        raise ValueError("Total training weight must be finite")
    return result


def fit_paired_candidate(
    factual: Iterable[FactualRow],
    annotations: Iterable[AnnotationRow],
    evaluation: Iterable[EvaluationRow],
    *,
    actions: Iterable[int],
    budgets: Iterable[int],
    design_columns: Iterable[str],
    annotation_source_id: str,
    annotation_protocol_id: str,
    rank_tolerance: float,
) -> PairedCandidateRun:
    """Fit one baseline and single-source DM+ models on nested pool prefixes.

    The loss is sum_i weight_i * (reward_i - design_i @ beta)^2 over all
    selected rows, without separately normalizing factual/annotation blocks.
    Multiplicity changes weights, not the count of unique annotations.
    Evaluation weights/probabilities must already sum to one; both methods
    use exactly the same declared evaluation rows, action order and policy.

    Each original training subject must be absent from evaluation. This
    ID check cannot establish feature-time validity or clinical eligibility.
    All inputs, including unused annotation-pool rows, are validated first.
    Any failure aborts the run; there is no skipping or replacement draw.
    """
    factual, annotations, evaluation = map(_sequence, (factual, annotations, evaluation))
    actions, budgets, columns = map(_sequence, (actions, budgets, design_columns))
    if not factual or not evaluation:
        raise ValueError("Nonempty factual and evaluation sets are required")
    if (not actions or any(type(a) is not int for a in actions)
            or len(set(actions)) != len(actions)):
        raise ValueError("Actions must be distinct declared integers")
    if (not budgets or any(type(b) is not int for b in budgets)
            or budgets[0] != 0 or any(b < 0 or b > len(annotations) for b in budgets)
            or any(left >= right for left, right in zip(budgets, budgets[1:]))):
        raise ValueError("Budgets must start at zero and strictly increase within pool size")
    if not columns:
        raise ValueError("The caller must declare design columns")
    columns = tuple(_identifier(c) for c in columns)
    if len(set(columns)) != len(columns):
        raise ValueError("Design column names must be unique")
    source_id = _identifier(annotation_source_id)
    protocol_id = _identifier(annotation_protocol_id)
    width = len(columns)

    by_event: dict[str, FactualRow] = {}
    train_subjects: set[str] = set()
    factual_design, factual_rewards, factual_weights = [], [], []
    for row in factual:
        if not isinstance(row, FactualRow):
            raise ValueError("Factual rows must use the declared record type")
        event_id, subject_id = _identifier(row.event_id), _identifier(row.subject_id)
        if event_id in by_event or type(row.action) is not int or row.action not in actions:
            raise ValueError("Factual event IDs must be unique and actions declared")
        by_event[event_id] = row
        train_subjects.add(subject_id)
        factual_design.append(_design(row.design, width))
        reward, weight = _reward_weight(row.reward, row.weight)
        factual_rewards.append(reward)
        factual_weights.append(weight)

    annotation_ids, annotation_keys = set(), set()
    annotation_design, annotation_rewards, annotation_weights = [], [], []
    for row in annotations:
        if not isinstance(row, AnnotationRow):
            raise ValueError("Annotation rows must use the declared record type")
        annotation_id = _identifier(row.annotation_id)
        event_id = _identifier(row.event_id)
        if (annotation_id in annotation_ids or event_id not in by_event
                or type(row.action) is not int or row.action not in actions
                or row.action == by_event[event_id].action):
            raise ValueError("Annotations must be unique counterfactuals of training events")
        if row.source_id != source_id or row.protocol_id != protocol_id:
            raise ValueError("A run must use one explicitly bound source and protocol")
        key = (event_id, row.action, row.source_id, row.protocol_id)
        if key in annotation_keys:
            raise ValueError("An event/action/source/protocol annotation cannot repeat")
        annotation_ids.add(annotation_id)
        annotation_keys.add(key)
        annotation_design.append(_design(row.design, width))
        reward, weight = _reward_weight(row.reward, row.weight)
        annotation_rewards.append(reward)
        annotation_weights.append(weight)

    context_ids = set()
    evaluation_design, probabilities, context_weights = [], [], []
    for row in evaluation:
        if not isinstance(row, EvaluationRow):
            raise ValueError("Evaluation rows must use the declared record type")
        context_id, subject_id = _identifier(row.context_id), _identifier(row.subject_id)
        if context_id in context_ids or subject_id in train_subjects:
            raise ValueError("Evaluation IDs must be unique and original subjects held out")
        context_ids.add(context_id)
        designs = _sequence(row.action_designs)
        policy = _sequence(row.policy_probabilities)
        if len(designs) != len(actions) or len(policy) != len(actions):
            raise ValueError("Evaluation columns must follow the declared action order")
        evaluation_design.append(tuple(_design(x, width) for x in designs))
        probabilities.append(tuple(_finite_real(x, "policy probability") for x in policy))
        context_weights.append(_finite_real(row.weight, "context weight"))
    # Reuse the existing equation's probability checks, before starting any fit.
    direct_method(probabilities, [[0.0] * len(actions) for _ in evaluation], context_weights)

    baseline = fit_ols(
        factual_design, factual_rewards, sample_weights=factual_weights,
        rank_tolerance=rank_tolerance,
    )

    def evaluate(model: LinearFit) -> float:
        predictions = [model.predict(rows) for rows in evaluation_design]
        return direct_method(probabilities, predictions, context_weights)

    dm_value = evaluate(baseline)
    results = []
    for budget in budgets:
        selected = annotations[:budget]
        weights = factual_weights + annotation_weights[:budget]
        total_weight = _weight_sum(weights)
        if budget == 0:
            model, plus_value = baseline, dm_value
        else:
            model = fit_ols(
                factual_design + annotation_design[:budget],
                factual_rewards + annotation_rewards[:budget],
                sample_weights=weights, rank_tolerance=rank_tolerance,
            )
            plus_value = evaluate(model)
        results.append(BudgetResult(
            annotation_budget=budget,
            annotation_ids=tuple(row.annotation_id for row in selected),
            unique_event_action_pairs=len({(row.event_id, row.action) for row in selected}),
            annotation_rows=budget,
            source_count=int(budget > 0),
            training_rows=len(factual) + budget,
            training_weight_sum=total_weight,
            dm_value=dm_value,
            dm_plus_value=plus_value,
            dm_plus_model=model,
        ))
    return PairedCandidateRun(
        baseline_model=baseline, results=tuple(results),
        factual_event_ids=tuple(row.event_id for row in factual),
        evaluation_context_ids=tuple(row.context_id for row in evaluation),
        design_columns=columns, actions=actions,
        annotation_source_id=source_id, annotation_protocol_id=protocol_id,
    )
