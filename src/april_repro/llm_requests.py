"""Local APRIL prompt/request construction; no network or patient-file access.

The paper prints a placeholder UpToDate paragraph, not its source text. The
guidance below is explicitly reconstructed from Appendix A / Figure 5. Snapshot
IDs, zero-action timing, missing-value wording and request limits are project
choices, not recovered historical settings. Only ``payload`` is an API body;
the surrounding identity and provenance must remain in the private ledger.
"""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
import hashlib
import json
import math
import re

from april_repro.cohort_splits import ACTIONS
from april_repro.decision_features import FEATURES, MEDICATION_FEATURES


PROTOCOL_VERSION = "april-llm-prompts-v1"
MODEL_SPECS = {
    "gpt-4o-mini": {
        "model": "gpt-4o-mini-2024-07-18", "temperature": 0,
        "max_completion_tokens": 4096, "store": False,
    },
    "o3-mini": {
        "model": "o3-mini-2025-01-31", "max_completion_tokens": 4096,
        "store": False,
    },
}
TASK_SPECS = {
    "potassium": {"lab": "serum potassium", "drug": "IV potassium", "rate": 10},
    "sodium": {"lab": "serum sodium", "drug": "IV NaCl 3% (hypertonic saline)", "rate": 30},
}
DOMAIN_GUIDANCE = (
    "Reconstructed domain guidance from APRIL Appendix A and Figure 5: relevant "
    "information includes age, sex, body size (weight and height), heart rate, "
    "respiratory rate, oxygen saturation, systolic and diastolic blood pressure, "
    "serum creatinine, recorded administration of NaCl 0.9%, dextrose 5%, "
    "propofol, norepinephrine and insulin, and the latest corresponding "
    "electrolyte measurement. The paper's original UpToDate paragraph was not "
    "published; this is a reconstruction of its disclosed feature guidance, "
    "not an UpToDate quotation. Unknown values are unavailable information, "
    "not normal values or evidence of absence."
)
PROMPT_TEMPLATE = """Predict a patient's {lab} concentration in a blood sample following the specified treatment decision. The clinical information below is available at the decision anchor t=0. All times are relative to that anchor; no absolute dates are supplied. Dynamic information describes the preceding four hours. Static covariates are available historical values and need not have been measured within those four hours.

## Reason for Admission
Admission time: unknown.
Reason for admission: unknown.

## Static Covariates
Age: {age} years.
Gender: {gender}.
Weight: {weight_kg} kg.
Height: {height_cm} cm.
Comorbidities: unknown.

## Labs / Vitals / Procedures During the Preceding Four Hours
Heart rate: {heart_rate} beats/minute.
Respiratory rate: {respiratory_rate} breaths/minute.
Oxygen saturation by pulse oximetry: {spo2} percent.
Systolic blood pressure: {sbp} mmHg.
Diastolic blood pressure: {dbp} mmHg.
Serum creatinine: {creatinine} mg/dL.
Procedures: unknown.

## Medications During the Preceding Four Hours
NaCl 0.9%: {administered_nacl_09}.
Dextrose 5%: {administered_dextrose_5}.
Propofol: {administered_propofol}.
Norepinephrine: {administered_norepinephrine}.
Insulin: {administered_insulin}.

## Domain Guidance
{guidance}

## Latest Pretreatment Electrolyte
Latest {lab}: {pre_lab_value} mEq/L.
Measurement time before the decision anchor: {pre_lab_hours} hours.

## Specified Treatment and Prediction Query
{treatment}
Use the clinical information above to predict the most likely single numeric {lab} value at the specified prediction time. Do not assume missing clinical measurements are normal.
Return only a JSON object with exactly two keys: "predicted_lab_value" (one finite number in mEq/L, with no unit text and no range) and "justification" (a brief explanation). Do not return a treatment recommendation.
"""


def _json_sha(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# Common to every task, patient and model; data/model parameters bind separately.
PROTOCOL_ID = PROTOCOL_VERSION + ":" + _json_sha({
    "version": PROTOCOL_VERSION, "features": FEATURES,
    "tasks": TASK_SPECS, "template": PROMPT_TEMPLATE, "guidance": DOMAIN_GUIDANCE,
    "zero_action_timing": "no infusion; anchor plus three hours",
    "numbers": "finite float64; repr; integer values rendered without decimal",
    "missing": "None or empty string rendered as unknown",
    "medication_zero": "no recorded administration in the four-hour window",
})


def _number(value, field, *, minimum=0, maximum=None, inclusive=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Invalid numeric " + field)
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise ValueError("Invalid numeric " + field) from None
    if (not math.isfinite(number) or number < minimum or
            (not inclusive and number == minimum) or
            (maximum is not None and number > maximum)):
        raise ValueError("Out-of-range or nonfinite " + field)
    return number


def _display(number):
    return str(int(number)) if number.is_integer() else repr(number)


def _missing(value):
    return value is None or isinstance(value, str) and value == ""


def _action(value, task):
    if not isinstance(task, str) or task not in ACTIONS:
        raise ValueError("Unknown electrolyte task")
    number = _number(value, "action", inclusive=True)
    if number not in ACTIONS[task]:
        raise ValueError("Action outside the task's discrete action set")
    return int(number)


def _features(features):
    if not isinstance(features, Mapping) or set(features) != set(FEATURES):
        raise ValueError("Features must contain exactly the fifteen declared keys")
    rendered = {}
    for name in FEATURES:
        value = features[name]
        if _missing(value):
            rendered[name] = "unknown"
        elif name == "gender":
            if not isinstance(value, str) or value not in ("F", "M"):
                raise ValueError("Gender must be F, M, or missing")
            rendered[name] = {"F": "female", "M": "male"}[value]
        elif name in MEDICATION_FEATURES:
            number = _number(value, name, inclusive=True, maximum=1)
            if number not in (0, 1):
                raise ValueError("Medication feature must be binary or missing")
            rendered[name] = ("recorded as administered" if number == 1 else
                              "no recorded administration in the four-hour window")
        else:
            rendered[name] = _display(_number(value, name))
    return rendered


def render_prompt(*, task, action, features, pre_lab_value=None,
                  pre_lab_hours_before_anchor=None):
    """Render only declared pretreatment values; identities/labels are not inputs.

    A present pre-lab may have unknown measurement age. An age without a value
    is rejected as inconsistent. The caller must establish pretreatment
    availability; this function only validates a supplied relative age in [0,4].
    """
    action = _action(action, task)
    values = _features(features)
    pre_lab = ("unknown" if _missing(pre_lab_value) else
               _display(_number(pre_lab_value, "pre_lab_value")))
    pre_hours = "unknown"
    if not _missing(pre_lab_hours_before_anchor):
        if pre_lab == "unknown":
            raise ValueError("Pre-lab time supplied without a pre-lab value")
        pre_hours = _display(_number(pre_lab_hours_before_anchor,
                                    "pre_lab_hours_before_anchor",
                                    inclusive=True, maximum=4))
    spec = TASK_SPECS[task]
    duration = action / spec["rate"]
    target = duration + 3
    if action == 0:
        treatment = (
            f"The specified dose is 0 mEq of {spec['drug']}: no infusion is "
            "administered at t=0. For this no-infusion decision, predict the lab "
            "at t=3 hours (three hours after the decision anchor)."
        )
    else:
        treatment = (
            f"Starting at t=0, a total dose of {action} mEq of {spec['drug']} "
            f"is administered intravenously at the assumed constant rate of "
            f"{spec['rate']} mEq/hour. The assumed infusion duration is "
            f"{_display(duration)} hours and ends at t={_display(duration)} hours. "
            f"Predict the lab three hours after this infusion ends, at "
            f"t={_display(target)} hours (= 0 + {action}/{spec['rate']} + 3 hours)."
        )
    return PROMPT_TEMPLATE.format(
        **values, lab=spec["lab"], guidance=DOMAIN_GUIDANCE, treatment=treatment,
        pre_lab_value=pre_lab, pre_lab_hours=pre_hours)


def _sha_identity(value, field):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Invalid SHA256 " + field)
    return value


def build_request(*, event_id_sha256, input_manifest_sha256, mode, task,
                  observed_action, action, model_key, features,
                  pre_lab_value=None, pre_lab_hours_before_anchor=None):
    """Return a private ledger record with a separately isolated API payload.

    Retries reuse request_id/cache_key. Identical clinical text can share a
    prompt hash across events, but never an event-bound request cache key.
    No network operation or file access is performed.
    """
    event = _sha_identity(event_id_sha256, "event identifier")
    source = _sha_identity(input_manifest_sha256, "input manifest")
    action, observed = _action(action, task), _action(observed_action, task)
    if mode not in ("factual", "counterfactual"):
        raise ValueError("Mode must be factual or counterfactual")
    if (mode == "factual") != (action == observed):
        raise ValueError("Requested action is inconsistent with annotation mode")
    if not isinstance(model_key, str) or model_key not in MODEL_SPECS:
        raise ValueError("Unknown fixed model key")
    prompt = render_prompt(task=task, action=action, features=features,
                           pre_lab_value=pre_lab_value,
                           pre_lab_hours_before_anchor=pre_lab_hours_before_anchor)
    payload = {**MODEL_SPECS[model_key],
               "messages": [{"role": "user", "content": prompt}]}
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    payload_sha = _json_sha(payload)
    metadata = {
        "event_id": event, "input_manifest_sha256": source,
        "mode": mode, "task": task, "observed_action": observed,
        "action": action, "model_key": model_key,
        "model_snapshot": payload["model"], "historical_snapshot_recovered": False,
    }
    request_id = _json_sha({"metadata": metadata, "protocol_id": PROTOCOL_ID,
                            "payload_sha256": payload_sha})
    return {
        "request_id": request_id, "cache_key": request_id,
        "protocol_version": PROTOCOL_VERSION, "protocol_id": PROTOCOL_ID,
        "prompt_sha256": prompt_sha, "payload_sha256": payload_sha,
        "metadata": metadata, "payload": payload,
    }
