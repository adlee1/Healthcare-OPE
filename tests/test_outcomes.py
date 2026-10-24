"""Synthetic boundary tests for the proposed D003 potassium outcome oracle."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import unittest

from april_repro.outcomes import (
    PROPOSED_POTASSIUM_OUTCOME_RULE,
    PotassiumLabRow,
    select_proposed_potassium_outcome,
)


ANCHOR = datetime(2035, 1, 2, 8, 0, tzinfo=timezone.utc)


def lab(
    hours: float,
    value: object = 4.0,
    *,
    itemid: int = 50971,
    unit: object = "mEq/L",
    stored_after_hours: float | None = 0.25,
    source_id: object = None,
) -> PotassiumLabRow:
    charttime = ANCHOR + timedelta(hours=hours)
    storetime = (
        None
        if stored_after_hours is None
        else charttime + timedelta(hours=stored_after_hours)
    )
    return PotassiumLabRow(
        itemid=itemid,
        charttime=charttime,
        valuenum=value,
        valueuom=unit,
        storetime=storetime,
        source_id=source_id,
    )


class ProposedPotassiumOutcomeTests(unittest.TestCase):
    def test_open_anchor_closed_24_hour_window_and_supported_items(self):
        result = select_proposed_potassium_outcome(
            ANCHOR,
            [
                lab(0, 1),
                lab(0.5, 2, itemid=99999),
                lab(24, 4.2, itemid=52610),
                lab(24.0001, 3),
            ],
        )
        self.assertTrue(result.accepted)
        self.assertEqual(result.selected_time, ANCHOR + timedelta(hours=24))
        self.assertEqual(result.normalized_value, 4.2)
        self.assertEqual(len(result.selected_rows), 1)

        no_match = select_proposed_potassium_outcome(
            ANCHOR, [lab(0), lab(24.0001)]
        )
        self.assertFalse(no_match.accepted)
        self.assertEqual(no_match.exclusion_reasons, ("no_lab_within_24h",))

    def test_first_timestamp_is_chosen_before_quality_and_never_skipped(self):
        result = select_proposed_potassium_outcome(
            ANCHOR,
            [lab(2, 4.1), lab(1, None), lab(1, math.inf)],
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.selected_time, ANCHOR + timedelta(hours=1))
        self.assertEqual(len(result.selected_rows), 2)
        self.assertIn(
            "selected_group_no_finite_supported_value", result.exclusion_reasons
        )
        self.assertIsNone(result.normalized_value)

    def test_same_time_duplicates_and_quality_siblings_are_retained(self):
        rows = [
            lab(1, 4, itemid=50971, unit=" meQ / l ", source_id="z"),
            lab(1, 4.0, itemid=52610, unit="MEQ/L", source_id="a"),
            lab(1, None, unit="not-used-for-a-missing-value", source_id="m"),
            lab(1, math.nan, unit=None, stored_after_hours=None, source_id="n"),
        ]
        result = select_proposed_potassium_outcome(ANCHOR, rows)
        self.assertTrue(result.accepted)
        self.assertEqual(result.normalized_value, 4.0)
        self.assertEqual(len(result.selected_rows), 4)
        self.assertEqual(result.distinct_supported_finite_values, (4.0,))
        self.assertIn("selected_group_has_duplicate_agreeing_value", result.flags)
        self.assertIn("selected_group_has_missing_value", result.flags)
        self.assertIn("selected_group_has_nonfinite_value", result.flags)
        self.assertIn("selected_group_has_missing_storetime", result.flags)

    def test_conflicting_supported_values_exclude_the_whole_group(self):
        result = select_proposed_potassium_outcome(
            ANCHOR, [lab(1, 3.9), lab(1, 4.0, itemid=52610), lab(2, 4.1)]
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.selected_time, ANCHOR + timedelta(hours=1))
        self.assertEqual(result.distinct_supported_finite_values, (3.9, 4.0))
        self.assertIn("selected_group_value_conflict", result.exclusion_reasons)

    def test_any_finite_unrecognized_unit_excludes_without_conversion(self):
        mixed = select_proposed_potassium_outcome(
            ANCHOR, [lab(1, 4.0), lab(1, 4.0, unit="mmol/L")]
        )
        self.assertFalse(mixed.accepted)
        self.assertIn("selected_group_unit_unrecognized", mixed.exclusion_reasons)
        self.assertEqual(mixed.candidate_normalized_value, 4.0)
        self.assertIsNone(mixed.normalized_value)

        unsupported_only = select_proposed_potassium_outcome(
            ANCHOR, [lab(1, 4.0, unit="mmol/L")]
        )
        self.assertEqual(
            unsupported_only.exclusion_reasons,
            (
                "selected_group_no_finite_supported_value",
                "selected_group_unit_unrecognized",
            ),
        )

    def test_storetime_does_not_select_but_reversed_nonmissing_time_excludes(self):
        late_first = lab(1, 4.0, stored_after_hours=20)
        early_later = lab(2, 4.1, stored_after_hours=0)
        result = select_proposed_potassium_outcome(ANCHOR, [early_later, late_first])
        self.assertTrue(result.accepted)
        self.assertEqual(result.selected_time, late_first.charttime)

        missing = select_proposed_potassium_outcome(
            ANCHOR, [lab(1, 4.0, stored_after_hours=None)]
        )
        self.assertTrue(missing.accepted)
        self.assertIn("selected_group_has_missing_storetime", missing.flags)

        reversed_time = select_proposed_potassium_outcome(
            ANCHOR, [lab(1, 4.0, stored_after_hours=-0.01), lab(2, 4.1)]
        )
        self.assertFalse(reversed_time.accepted)
        self.assertEqual(reversed_time.selected_time, ANCHOR + timedelta(hours=1))
        self.assertIn("reversed_storetime", reversed_time.exclusion_reasons)

    def test_additional_treatment_interval_has_open_start_and_closed_end(self):
        selected_time = ANCHOR + timedelta(hours=2)
        at_anchor_and_after_lab = select_proposed_potassium_outcome(
            ANCHOR,
            [lab(2)],
            additional_treatment_times=[ANCHOR + timedelta(hours=3)],
        )
        self.assertTrue(at_anchor_and_after_lab.accepted)

        between = select_proposed_potassium_outcome(
            ANCHOR,
            [lab(2)],
            additional_treatment_times=[ANCHOR + timedelta(hours=1)],
        )
        self.assertFalse(between.accepted)
        self.assertIn("additional_treatment_before_outcome", between.exclusion_reasons)

        tied = select_proposed_potassium_outcome(
            ANCHOR, [lab(2)], additional_treatment_times=[selected_time]
        )
        self.assertFalse(tied.accepted)
        self.assertIn("additional_treatment_before_outcome", tied.exclusion_reasons)
        self.assertIn(
            "same_time_treatment_lab_order_unknown", tied.exclusion_reasons
        )

    def test_same_anchor_distinct_event_requires_episode_rule_and_excludes(self):
        explicit = select_proposed_potassium_outcome(
            ANCHOR, [lab(1)], same_anchor_distinct_event=True
        )
        inferred = select_proposed_potassium_outcome(
            ANCHOR, [lab(1)], additional_treatment_times=[ANCHOR]
        )
        for result in (explicit, inferred):
            self.assertFalse(result.accepted)
            self.assertIn("episode_overlap_unresolved", result.exclusion_reasons)
            self.assertIn("same_anchor_distinct_event", result.flags)
            self.assertIn("same_anchor_episode_rule_required", result.flags)

    def test_input_order_and_source_ids_cannot_change_scientific_result(self):
        first = [
            lab(2, 5.0, source_id=999),
            lab(1, 4.0, itemid=52610, unit=" MEQ / L ", source_id=7),
            lab(1, 4, itemid=50971, unit="mEq/L", source_id=8),
        ]
        second = [
            lab(1, 4, itemid=50971, unit="mEq/L", source_id="renamed-b"),
            lab(2, 5.0, source_id="renamed-c"),
            lab(1, 4.0, itemid=52610, unit=" MEQ / L ", source_id="renamed-a"),
        ]
        left = select_proposed_potassium_outcome(ANCHOR, first)
        right = select_proposed_potassium_outcome(ANCHOR, second)
        self.assertEqual(left, right)
        self.assertTrue(left.accepted)

    def test_result_explicitly_remains_a_proposal_and_ignores_proxy_target(self):
        result = select_proposed_potassium_outcome(ANCHOR, [lab(1)])
        self.assertEqual(result.rule_version, PROPOSED_POTASSIUM_OUTCOME_RULE)
        self.assertEqual(result.rule_status, "proposed")
        self.assertFalse(result.formal_label_constructed)
        self.assertFalse(result.prompt_proxy_target_used)

    def test_malformed_times_and_rows_are_rejected(self):
        with self.assertRaises(ValueError):
            select_proposed_potassium_outcome("2035-01-02", [])
        with self.assertRaises(ValueError):
            select_proposed_potassium_outcome(ANCHOR, [object()])
        with self.assertRaises(ValueError):
            select_proposed_potassium_outcome(
                ANCHOR,
                [
                    PotassiumLabRow(
                        50971,
                        datetime(2035, 1, 2, 9),
                        4.0,
                        "mEq/L",
                    )
                ],
            )
        with self.assertRaises(ValueError):
            select_proposed_potassium_outcome(
                ANCHOR, [lab(1)], same_anchor_distinct_event=1
            )


if __name__ == "__main__":
    unittest.main()
