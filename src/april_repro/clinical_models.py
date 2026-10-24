"""G3 clinical models with training-only transforms and JSON coefficient export.

These are recorded project choices for undisclosed APRIL implementation details.
Inputs are numeric arrays in the fifteen-feature order; NaN means missing.
Gender is F=0/M=1. Fixed binary dictionaries do not depend on training support.
No patient identities, outcomes, or actions enter the context transformer.
"""
from __future__ import annotations

import copy
import json
import warnings

from .cohort_splits import ACTIONS
from .decision_features import FEATURES, MEDICATION_FEATURES

RULE_VERSION = "clinical-models-v1"
BINARY = {"gender", *MEDICATION_FEATURES}
POLICY_PARAMETERS = {"C": 1.0, "solver": "lbfgs", "tol": 1e-4,
                     "max_iter": 1000, "random_state": 0, "class_weight": None,
                     "penalty": "l2", "fit_intercept": True}


def _numpy():
    try:
        import numpy as np
    except ImportError:
        raise RuntimeError("Clinical models require the recorded optional modeling dependencies") from None
    return np


def _versions():
    import numpy
    import scipy
    import sklearn
    return {"numpy": numpy.__version__, "scipy": scipy.__version__, "scikit-learn": sklearn.__version__}


def _matrix(values):
    np = _numpy()
    array = np.asarray(values)
    if array.ndim != 2 or array.shape[1] != len(FEATURES) or array.dtype.kind not in "fiu":
        raise ValueError("Expected a numeric matrix with the fixed fifteen feature columns")
    array = np.asarray(array, dtype=np.float64)
    for index, name in enumerate(FEATURES):
        column = array[:, index]
        present = ~np.isnan(column)
        if np.any(~np.isfinite(column[present])):
            raise ValueError("Nonfinite nonmissing clinical feature: " + name)
        if name in BINARY:
            if np.any(present & (column != 0) & (column != 1)):
                raise ValueError("Clinical binary feature is outside its fixed dictionary: " + name)
        elif np.any(present & (column <= 0)):
            raise ValueError("Clinical continuous feature must be positive: " + name)
    return array


def _vector(values, length, label):
    np = _numpy()
    raw = np.asarray(values)
    if raw.ndim != 1 or len(raw) != length or raw.dtype.kind not in "fiu":
        raise ValueError("Invalid " + label + " vector")
    result = np.asarray(raw, dtype=np.float64)
    if np.any(~np.isfinite(result)):
        raise ValueError("Invalid " + label + " vector")
    return result


def _actions(values, length, task):
    np = _numpy()
    if task not in ACTIONS:
        raise ValueError("Unknown clinical task")
    values = _vector(values, length, "action")
    if np.any(~np.isin(values, ACTIONS[task])):
        raise ValueError("Action is outside the declared paper action space")
    return values.astype(np.int64)


def _json_copy(value):
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (ValueError, TypeError):
        raise ValueError("Model state must be finite JSON data") from None


class Preprocessor:
    def __init__(self, state):
        self._state = _json_copy(state)
        if (state.get("rule_version") != RULE_VERSION or state.get("kind") != "preprocessor"
                or state.get("input_columns") != list(FEATURES)
                or state.get("status") not in ("complete", "not_estimable")):
            raise ValueError("Unsupported preprocessing state")
        if len(state.get("statistics", [])) != len(FEATURES):
            raise ValueError("Incomplete preprocessing statistics")
        expected = []
        for index, record in enumerate(state["statistics"]):
            if record.get("name") != FEATURES[index] or record.get("kind") != (
                    "binary" if FEATURES[index] in BINARY else "continuous"):
                raise ValueError("Preprocessing column order or type changed")
            if not record["omitted_reason"]:
                if record["impute"] is None or (record["kind"] == "continuous" and record["scale"] <= 0):
                    raise ValueError("Invalid retained preprocessing column")
                expected.append(record["name"])
            elif record["omitted_reason"] not in ("all_missing_in_training", "constant_after_training_imputation"):
                raise ValueError("Unknown preprocessing omission reason")
        if state.get("output_columns") != expected:
            raise ValueError("Preprocessing output columns do not match statistics")

    @property
    def status(self):
        return self._state["status"]

    @property
    def columns(self):
        return tuple(self._state["output_columns"])

    def to_dict(self):
        return copy.deepcopy(self._state)

    @classmethod
    def from_dict(cls, state):
        return cls(state)

    def transform(self, values):
        np = _numpy()
        array = _matrix(values)
        if self.status != "complete":
            raise ValueError("Preprocessor is not estimable from empty training data")
        result = np.empty((len(array), len(self.columns)), dtype=np.float64)
        out = 0
        for index, record in enumerate(self._state["statistics"]):
            if record["omitted_reason"]:
                continue
            column = array[:, index]
            result[:, out] = np.where(np.isnan(column), record["impute"], column)
            if record["kind"] == "continuous":
                result[:, out] = (result[:, out] - record["mean"]) / record["scale"]
            out += 1
        if not np.all(np.isfinite(result)):
            raise ValueError("Clinical transformation exceeded numerical range")
        return result


def fit_preprocessor(values):
    np = _numpy()
    array = _matrix(values)
    records, columns = [], []
    for index, name in enumerate(FEATURES):
        column = array[:, index]
        observed = column[~np.isnan(column)]
        binary = name in BINARY
        record = {"name": name, "kind": "binary" if binary else "continuous",
                  "observed": int(len(observed)), "missing": int(len(array)-len(observed)),
                  "impute": None, "mean": None, "scale": None,
                  "observed_binary_values": np.unique(observed).tolist() if binary else None,
                  "omitted_reason": "all_missing_in_training"}
        if len(observed):
            impute = float(int(np.count_nonzero(observed == 1) > np.count_nonzero(observed == 0))) if binary else float(np.median(observed))
            filled = np.where(np.isnan(column), impute, column)
            record.update(impute=impute, omitted_reason="")
            constant = bool(np.all(filled == filled[0]))
            if binary:
                record.update(mean=0.0, scale=1.0)
            else:
                record.update(mean=float(np.mean(filled)), scale=float(np.std(filled, ddof=0)))
                if not np.isfinite(record["mean"]) or not np.isfinite(record["scale"]):
                    raise ValueError("Training feature statistics exceeded numerical range")
                if not constant and record["scale"] == 0:
                    raise ValueError("Training feature scale is numerically unsupported")
            if constant:
                record["omitted_reason"] = "constant_after_training_imputation"
            else:
                columns.append(name)
        records.append(record)
    return Preprocessor({"kind": "preprocessor", "rule_version": RULE_VERSION,
                         "status": "complete" if len(array) else "not_estimable",
                         "training_rows": len(array), "input_columns": list(FEATURES),
                         "output_columns": columns, "statistics": records,
                         "binary_mode_tie_break": 0, "continuous_std_ddof": 0,
                         "statistics_fit_population": "supplied training rows only"})


class _Model:
    kind = ""

    def __init__(self, state):
        self._state = _json_copy(state)
        if (state.get("kind") != self.kind or state.get("rule_version") != RULE_VERSION
                or state.get("task") not in ACTIONS
                or state.get("actions") != list(ACTIONS[state["task"]])
                or state.get("status") not in ("complete", "not_estimable")):
            raise ValueError("Unsupported clinical model state")
        self.preprocessor = Preprocessor.from_dict(state["preprocessor"])

    @property
    def status(self):
        return self._state["status"]

    @property
    def task(self):
        return self._state["task"]

    @property
    def actions(self):
        return tuple(self._state["actions"])

    @property
    def metadata(self):
        return copy.deepcopy(self._state["metadata"])

    def to_dict(self):
        return copy.deepcopy(self._state)

    @classmethod
    def from_dict(cls, state):
        return cls(state)

    def _context(self, values):
        if self.status != "complete":
            raise ValueError("Clinical model is not estimable from empty training data")
        return self.preprocessor.transform(values)


class PolicyFit(_Model):
    kind = "policy"

    @property
    def converged(self):
        return self._state["metadata"]["converged"]

    @property
    def n_iter(self):
        return tuple(self._state["metadata"]["n_iter"])

    def predict_proba(self, values):
        np = _numpy()
        context = self._context(values)
        probabilities = np.zeros((len(context), len(self.actions)), dtype=np.float64)
        classes = self._state["classes"]
        if not classes or len(set(classes)) != len(classes) or any(c not in self.actions for c in classes):
            raise ValueError("Invalid serialized policy classes")
        if len(classes) == 1:
            probabilities[:, self.actions.index(classes[0])] = 1.0
            return probabilities
        if self._state["link"] == "class_frequency":
            if context.shape[1] != 0:
                raise ValueError("Invalid intercept-only policy design")
            fitted = np.asarray(self._state["class_probabilities"], dtype=np.float64)
            if fitted.shape != (len(classes),) or np.any(fitted < 0) or not np.isclose(fitted.sum(), 1):
                raise ValueError("Invalid serialized class-frequency probabilities")
            for index, action in enumerate(classes):
                probabilities[:, self.actions.index(action)] = fitted[index]
            return probabilities
        if self._state["link"] not in ("binary_logit", "softmax"):
            raise ValueError("Invalid serialized policy link")
        coefficients = np.asarray(self._state["coefficients"], dtype=np.float64)
        intercept = np.asarray(self._state["intercept"], dtype=np.float64)
        binary = self._state["link"] == "binary_logit"
        expected = (1 if binary else len(classes), context.shape[1])
        if coefficients.shape != expected or intercept.shape != (expected[0],) or (binary and len(classes) != 2):
            raise ValueError("Invalid serialized policy coefficient shape")
        logits = context @ coefficients.T + intercept
        if not np.all(np.isfinite(logits)):
            raise ValueError("Policy prediction exceeded numerical range")
        if binary:
            exp = np.exp(-np.abs(logits[:, 0]))
            positive = np.where(logits[:, 0] >= 0, 1/(1+exp), exp/(1+exp))
            fitted = np.column_stack((1-positive, positive))
        else:
            exp = np.exp(logits - np.max(logits, axis=1, keepdims=True))
            fitted = exp / np.sum(exp, axis=1, keepdims=True)
        for index, action in enumerate(classes):
            probabilities[:, self.actions.index(action)] = fitted[:, index]
        return probabilities

    def predict(self, values):
        np = _numpy()
        return np.asarray(self.actions)[np.argmax(self.predict_proba(values), axis=1)]


class RewardFit(_Model):
    kind = "reward"

    def _base(self, values):
        np = _numpy()
        context = self._context(values)
        coefficients = np.asarray(self._state["coefficients"], dtype=np.float64)
        if coefficients.shape != (context.shape[1]+1,):
            raise ValueError("Invalid serialized reward coefficient shape")
        base = context @ coefficients[:-1] + self._state["intercept"]
        return base, coefficients[-1]

    def predict(self, values, actions):
        np = _numpy()
        base, action_coefficient = self._base(values)
        actions = _actions(actions, len(base), self.task)
        result = base + action_coefficient * actions / max(self.actions)
        if not np.all(np.isfinite(result)):
            raise ValueError("Reward prediction exceeded numerical range")
        return result

    def predict_action_values(self, values):
        np = _numpy()
        base, action_coefficient = self._base(values)
        result = base[:, None] + action_coefficient * np.asarray(self.actions)[None, :] / max(self.actions)
        if not np.all(np.isfinite(result)):
            raise ValueError("Reward prediction exceeded numerical range")
        return result


def _initial_state(kind, array, actions, task):
    np = _numpy()
    preprocessor = fit_preprocessor(array)
    classes, counts = np.unique(actions, return_counts=True)
    return {"kind": kind, "rule_version": RULE_VERSION, "task": task,
            "actions": list(ACTIONS[task]), "status": "complete" if len(array) else "not_estimable",
            "preprocessor": preprocessor.to_dict(), "coefficients": [], "intercept": [],
            "classes": classes.tolist(), "metadata": {
                "training_rows": len(array), "observed_action_counts": {str(a): int(c) for a, c in zip(classes, counts)},
                "missing_training_actions": [a for a in ACTIONS[task] if a not in classes],
                "versions": _versions(), "reason": "" if len(array) else "empty_training_set"}}


def fit_policy(values, actions, task):
    np = _numpy()
    from sklearn.linear_model import LogisticRegression
    from sklearn.exceptions import ConvergenceWarning
    from threadpoolctl import threadpool_limits
    array = _matrix(values)
    actions = _actions(actions, len(array), task)
    state = _initial_state("policy", array, actions, task)
    state["metadata"].update(parameters=dict(POLICY_PARAMETERS),
                             n_iter=[], converged=None)
    state["link"] = "constant"
    if len(state["classes"]) <= 1:
        state["metadata"]["fitting_method"] = "constant_single_observed_class" if len(array) else "not_estimable"
        return PolicyFit(state)
    context = Preprocessor.from_dict(state["preprocessor"]).transform(array)
    if context.shape[1] == 0:
        state["link"] = "class_frequency"
        state["class_probabilities"] = [state["metadata"]["observed_action_counts"][str(a)] / len(array)
                                        for a in state["classes"]]
        state["metadata"].update(fitting_method="intercept_only_class_frequency_multinomial_MLE", converged=True)
        return PolicyFit(state)
    estimator = LogisticRegression(**POLICY_PARAMETERS)
    with threadpool_limits(limits=1), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        estimator.fit(context, actions)
    state.update(coefficients=estimator.coef_.tolist(), intercept=estimator.intercept_.tolist(),
                 classes=estimator.classes_.tolist(),
                 link="binary_logit" if estimator.coef_.shape[0] == 1 else "softmax")
    state["metadata"].update(fitting_method="sklearn_LogisticRegression",
                             converged=not any(issubclass(w.category, ConvergenceWarning) for w in caught),
                             n_iter=estimator.n_iter_.tolist(), warning_categories=sorted({w.category.__name__ for w in caught}))
    return PolicyFit(state)


def fit_reward(values, actions, rewards, task):
    np = _numpy()
    from sklearn.linear_model import LinearRegression
    from threadpoolctl import threadpool_limits
    array = _matrix(values)
    actions = _actions(actions, len(array), task)
    rewards = _vector(rewards, len(array), "reward")
    if np.any((rewards < 0) | (rewards > 1)):
        raise ValueError("Training rewards must lie in the declared reward range [0,1]")
    state = _initial_state("reward", array, actions, task)
    state["metadata"].update(parameters={"fit_intercept": True, "positive": False},
                             action_encoding="action/max(paper_actions)", interactions=False,
                             prediction_clipping=False, action_column_retained=True,
                             action_varies_in_training=len(state["classes"]) >= 2,
                             constant_action_effect_unidentified=len(state["classes"]) == 1,
                             rank=None, singular_values=[], rank_deficient=None,
                             rank_basis="centered design excluding separately fitted intercept",
                             rank_deficiency_solution="minimum-norm least-squares coefficients on centered design")
    if not len(array):
        return RewardFit(state)
    context = Preprocessor.from_dict(state["preprocessor"]).transform(array)
    design = np.column_stack((context, actions / max(ACTIONS[task])))
    estimator = LinearRegression(fit_intercept=True, positive=False)
    with threadpool_limits(limits=1):
        estimator.fit(design, rewards)
    state.update(coefficients=estimator.coef_.tolist(), intercept=float(estimator.intercept_))
    state["metadata"].update(rank=int(estimator.rank_), singular_values=estimator.singular_.tolist(),
                             rank_deficient=int(estimator.rank_) < design.shape[1],
                             design_columns=[*state["preprocessor"]["output_columns"], "action_over_maximum"])
    return RewardFit(state)
