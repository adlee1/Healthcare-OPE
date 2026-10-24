"""Supplemental checks of disclosed APRIL facts, outside the frozen CLI.

This checks draft configuration metadata, not clinical data or experiment
fidelity. The original validator and its frozen execution snapshot stay intact.
"""
from __future__ import annotations

from .cli import validate_protocol


# User-supplied mandyam26a.pdf: section 4 p6, Appendix A p17.
PAPER_MODELS = frozenset((
    "o1", "gpt-4o-mini", "o3-mini", "Gemini 1.5", "Claude 3.7 Sonnet",
))
PAPER_FEATURES = frozenset((
    "age", "gender", "weight", "height", "heart_rate", "respiratory_rate",
    "spo2", "systolic_bp", "diastolic_bp", "creatinine", "nacl_0_9",
    "dextrose_5", "propofol", "norepinephrine", "insulin",
))
# Section 3.2 p5. Keep the legacy display label consistent with structured facts.
OUTCOME_TIME_LABEL = (
    "3 hours after infusion concludes (p.5); zero-dose convention unresolved"
)


def _exact_members(value: object, expected: frozenset[str]) -> bool:
    return (
        isinstance(value, list)
        and all(type(item) is str for item in value)
        and len(value) == len(expected)
        and set(value) == expected
    )


def _exact_number(value: object, expected: int) -> bool:
    # Equality with these finite constants also rejects NaN and infinities;
    # exact built-in types prevent bool from masquerading as a number.
    return type(value) in (int, float) and value == expected


def validate_paper_alignment(config: dict) -> list[str]:
    """Return old draft-validation errors plus field-specific paper-fact errors.

    Lists of named facts are sets, not feature-column order commitments.
    Unreported model snapshots, input aggregation and zero-dose timing remain
    unresolved. No patient data are inspected and no protocol is frozen here.
    """
    if not isinstance(config, dict):
        return ["config: expected a draft protocol dictionary"]
    errors = list(validate_protocol(config))
    sections = {
        name: config[name] if isinstance(config.get(name), dict) else {}
        for name in ("potassium", "sodium", "inputs", "llm")
    }
    for task, rate in (("potassium", 10), ("sodium", 30)):
        field = "infusion_rate_as_printed_meq_per_hour"
        if not _exact_number(sections[task].get(field), rate):
            errors.append(f"{task}.{field}: expected {rate} (section 3.2 pp4-5)")

    for section, field, expected, citation in (
        ("llm", "paper_model_names", PAPER_MODELS, "section 4 p6"),
        ("inputs", "paper_appendix_a_features", PAPER_FEATURES, "Appendix A p17"),
        ("llm", "response_keys_as_printed",
         frozenset(("predicted_lab_value", "justification")), "Figure 5 p18"),
    ):
        if not _exact_members(sections[section].get(field), expected):
            errors.append(
                f"{section}.{field}: expected the exact paper names without "
                f"duplicates ({citation})"
            )

    inputs = sections["inputs"]
    if inputs.get("llm_outcome_time") != OUTCOME_TIME_LABEL:
        errors.append(
            "inputs.llm_outcome_time: canonical label must say infusion end + "
            "3 hours; zero-dose convention remains unresolved (section 3.2 p5)"
        )
    if inputs.get("llm_outcome_anchor_as_printed") != "infusion_end":
        errors.append(
            "inputs.llm_outcome_anchor_as_printed: expected infusion_end "
            "(section 3.2 p5)"
        )
    if not _exact_number(inputs.get("llm_outcome_offset_hours_as_printed"), 3):
        errors.append(
            "inputs.llm_outcome_offset_hours_as_printed: expected 3 "
            "(section 3.2 p5)"
        )
    if sections["llm"].get("predicted_lab_format_as_printed") != "single_number_without_units":
        errors.append(
            "llm.predicted_lab_format_as_printed: expected "
            "single_number_without_units (Figure 5 p18)"
        )
    return errors
