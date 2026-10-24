"""Synthetic paired arithmetic, denominator and identity regression tests."""
from copy import deepcopy
import importlib.util
import json
import math
from pathlib import Path
import statistics
import unittest

import april_repro
STAGE = Path(__file__).resolve().parents[1]
if str(STAGE / "src/april_repro") not in april_repro.__path__:
    april_repro.__path__.insert(0, str(STAGE / "src/april_repro"))
from april_repro import clinical_dmplus_bootstrap_statistics as stats

AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "scipy"))


def draw(draw_id, value, reference=0.0, **extra):
    return {"draw_id": draw_id, "status": "complete", "dm_value": value,
            "observed_reference_value": reference, "signed_error": value - reference, **extra}


@unittest.skipUnless(AVAILABLE, "Pinned numerical dependencies unavailable")
class PairedBootstrapStatisticsTests(unittest.TestCase):
    def summary(self, dm, plus, **kwargs):
        return stats.summarize_paired_bootstrap_draws(
            [draw(i, e) for i, e in enumerate(dm)],
            [draw(i, e) for i, e in enumerate(plus)], len(dm), **kwargs)

    def test_rmse_uses_all_squared_errors_and_existing_delta_mcse(self):
        result = self.summary([1.0, 3.0], [0.0, 1.0])["primary_metrics"]
        self.assertAlmostEqual(result["dm"]["rmse"], math.sqrt(5))
        self.assertAlmostEqual(result["dmplus"]["rmse"], math.sqrt(0.5))
        self.assertAlmostEqual(result["rmse_gain"], math.sqrt(5) - math.sqrt(0.5))
        expected_mcse = statistics.stdev([1, 9]) / (2 * math.sqrt(2) * math.sqrt(5))
        self.assertAlmostEqual(result["dm"]["rmse_mc_se_delta"], expected_mcse)
        self.assertEqual(result["dm"]["rmse_error_bar_kind"], "finite_B_monte_carlo_standard_error_delta")

    def test_t_uses_squared_errors_with_analytic_two_draw_answer(self):
        result = self.summary([1.0, 3.0], [0.0, 1.0])["primary_metrics"]
        test = result["paired_t_test"]
        # Squared-error differences are 1 and 8: mean 4.5, sample SD 7/sqrt(2).
        expected_t = 9 / 7
        expected_p = 1 - 2 * math.atan(expected_t) / math.pi  # df=1 Cauchy.
        self.assertAlmostEqual(test["statistic"], expected_t)
        self.assertAlmostEqual(test["pvalue"], expected_p)
        self.assertEqual(test["df"], 1)
        self.assertEqual(test["alternative"], "two-sided")
        self.assertEqual(test["positive_statistic_favors"], "dmplus")
        self.assertAlmostEqual(result["squared_error_gain"]["mean"], 4.5)

    def test_swapping_methods_negates_t_and_gains_but_preserves_p(self):
        first = self.summary([1.0, 3.0, -2.0], [0.0, 1.0, 2.5])["primary_metrics"]
        second = self.summary([0.0, 1.0, 2.5], [1.0, 3.0, -2.0])["primary_metrics"]
        self.assertAlmostEqual(first["paired_t_test"]["statistic"], -second["paired_t_test"]["statistic"])
        self.assertEqual(first["paired_t_test"]["pvalue"], second["paired_t_test"]["pvalue"])
        self.assertAlmostEqual(first["rmse_gain"], -second["rmse_gain"])

    def test_percentile_linear_interval_is_absolute_gain_not_rmse_ci(self):
        result = self.summary([0.0, 1.0, -2.0, 3.0], [0.0] * 4)["primary_metrics"]["absolute_error_gain"]
        self.assertAlmostEqual(result["percentile_95_lower"], 0.075)
        self.assertAlmostEqual(result["percentile_95_upper"], 2.925)
        self.assertEqual(result["median"], 1.5)
        self.assertEqual(result["positive_gain_fraction"], 0.75)
        self.assertFalse(result["positive_gain_fraction_is_pvalue"])
        self.assertFalse(result["interval_is_rmse_difference_ci"])
        self.assertEqual(result["percentile_method"], "linear")

    def test_zero_differences_include_equal_magnitudes_with_opposite_signs(self):
        result = self.summary([1.0, -3.0], [-1.0, 3.0])["primary_metrics"]
        self.assertEqual(result["paired_t_test"]["status"], "all_zero_difference")
        self.assertEqual(result["paired_t_test"]["statistic"], 0.0)
        self.assertEqual(result["paired_t_test"]["pvalue"], 1.0)
        self.assertEqual(result["absolute_error_gain"]["positive_gain_fraction"], 0.0)
        self.assertFalse(result["paired_t_test"]["reject_null_at_alpha"])

    def test_constant_nonzero_difference_is_degenerate_not_p_zero(self):
        for dm, plus, mean in (([2.0, 2.0], [1.0, 1.0], 3.0), ([1.0, 1.0], [2.0, 2.0], -3.0)):
            with self.subTest(mean=mean):
                result = self.summary(dm, plus)["primary_metrics"]
                test = result["paired_t_test"]
                self.assertEqual(test["status"], "degenerate_constant_nonzero_difference")
                self.assertIsNone(test["statistic"])
                self.assertIsNone(test["pvalue"])
                self.assertIsNone(test["reject_null_at_alpha"])
                self.assertEqual(result["squared_error_gain"]["mean"], mean)

    def test_one_pair_has_no_t_statistic(self):
        result = self.summary([2.0], [1.0])["primary_metrics"]
        self.assertEqual(result["paired_t_test"]["status"], "insufficient_draws")
        self.assertIsNone(result["paired_t_test"]["pvalue"])
        self.assertIsNone(result["dm"]["rmse_mc_se_delta"])

    def test_pairing_uses_ids_not_order_and_does_not_mutate(self):
        dm = [draw(1, 3.0), draw(0, 1.0)]
        plus = [draw(0, 0.0), draw(1, 1.0)]
        originals = deepcopy((dm, plus))
        result = stats.summarize_paired_bootstrap_draws(iter(dm), iter(plus), 2)
        self.assertEqual(result["completed_draw_ids"], [0, 1])
        self.assertAlmostEqual(result["primary_metrics"]["paired_t_test"]["statistic"], 9 / 7)
        self.assertEqual((dm, plus), originals)

    def test_missing_and_failed_pairs_remain_in_denominator(self):
        dm = [draw(i, float(i + 1)) for i in range(5)]
        plus = [draw(0, 0.0), {"draw_id": 1, "status": "failed"}, draw(3, 1.0)]
        result = stats.summarize_paired_bootstrap_draws(dm, plus, 5)
        self.assertEqual(result["status"], "incomplete")
        self.assertIsNone(result["primary_metrics"])
        self.assertEqual(result["completed_draw_ids"], [0, 3])
        self.assertEqual(result["failed_draw_ids"], [1])
        self.assertEqual(result["pending_draw_ids"], [2, 4])
        self.assertEqual(sum(result[k] for k in ("completed_draws", "failed_draws", "pending_draws")), 5)
        self.assertEqual(result["diagnostic_valid_pair_metrics"]["draw_count"], 2)
        self.assertEqual(result["diagnostic_valid_pair_metrics_label"], "partial_valid_pairs_only_not_primary")

    def test_failure_on_either_side_wins_over_missing_other_side(self):
        result = stats.summarize_paired_bootstrap_draws(
            [{"draw_id": 0, "status": "failed"}], [{"draw_id": 1, "status": "failed"}], 3)
        self.assertEqual(result["failed_draw_ids"], [0, 1])
        self.assertEqual(result["pending_draw_ids"], [2])
        self.assertIsNone(result["diagnostic_valid_pair_metrics"])

    def test_default_requires_all_500_even_if_499_pairs_complete(self):
        records = [draw(i, float(i % 3)) for i in range(499)]
        result = stats.summarize_paired_bootstrap_draws(records, records)
        self.assertIsNone(result["primary_metrics"])
        self.assertEqual(result["pending_draw_ids"], [499])
        result = stats.summarize_paired_bootstrap_draws(records + [draw(499, 1)], records + [draw(499, 1)])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["primary_metrics"]["draw_count"], 500)

    def test_reference_must_be_identical_not_merely_similar(self):
        with self.assertRaisesRegex(ValueError, "references"):
            stats.summarize_paired_bootstrap_draws([draw(0, 1.0, 0.0)], [draw(0, 1.0, 1e-15)], 1)

    def test_pair_metadata_mismatch_or_asymmetry_rejected(self):
        for other in ({"pair_metadata": {"task": "sodium"}}, {}):
            with self.subTest(other=other), self.assertRaisesRegex(ValueError, "pair_metadata"):
                stats.summarize_paired_bootstrap_draws(
                    [draw(0, 1.0, pair_metadata={"task": "potassium"})], [draw(0, 0.0, **other)], 1)
        result = stats.summarize_paired_bootstrap_draws(
            [draw(0, 1.0, pair_metadata={"draw": "synthetic"})],
            [draw(0, 0.0, pair_metadata={"draw": "synthetic"})], 1)
        self.assertEqual(result["status"], "complete")

    def test_population_task_split_seed_and_original_dm_must_match(self):
        for field, value in (("population_draw_metadata", {"sha": "synthetic"}),
                             ("task", "potassium"), ("split", "gender"), ("seed", "synthetic-seed")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                stats.summarize_paired_bootstrap_draws([draw(0, 1.0, **{field: value})], [draw(0, 0.0)], 1)
        for field in ("original_dm_value", "original_dm_signed_error"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                stats.summarize_paired_bootstrap_draws([draw(0, 1.0)], [draw(0, 0.0, **{field: 2.0})], 1)
        self.assertEqual(stats.summarize_paired_bootstrap_draws(
            [draw(0, 1.0)], [draw(0, 0.0, original_dm_value=1.0, original_dm_signed_error=1.0)], 1)["status"], "complete")

    def test_failed_record_can_lack_pair_metadata_without_hiding_failure(self):
        result = stats.summarize_paired_bootstrap_draws(
            [draw(0, 1.0, task="potassium", population_draw_metadata={"sha": "synthetic"})],
            [{"draw_id": 0, "status": "failed", "reason": "synthetic_exception"}], 1)
        self.assertEqual(result["failed_draw_ids"], [0])
        self.assertIsNone(result["primary_metrics"])

    def test_invalid_records_use_shared_validator(self):
        invalid = [
            [draw(0, 1.0), draw(0, 2.0)], [draw(2, 1.0)], [draw(True, 1.0)],
            [{"draw_id": 0, "status": "complete", "dm_value": float("nan"), "observed_reference_value": 0, "signed_error": 1}],
            [dict(draw(0, 1.0), signed_error=2.0)],
            [{"draw_id": 0, "status": "failed", "dm_value": 1}],
            [{"draw_id": 0, "status": "not_estimable"}],
        ]
        for records in invalid:
            with self.subTest(records=records), self.assertRaises(ValueError):
                stats.summarize_paired_bootstrap_draws(records, [draw(0, 0.0)], 2)

    def test_invalid_planned_count_alpha_and_overflow_rejected(self):
        for count in (False, 0, -1, 1.2):
            with self.subTest(count=count), self.assertRaises(ValueError):
                stats.summarize_paired_bootstrap_draws([], [], count)
        for alpha in (False, 0, 1, float("nan"), "0.05"):
            with self.subTest(alpha=alpha), self.assertRaises(ValueError):
                self.summary([1.0, 3.0], [0.0, 1.0], alpha=alpha)
        with self.assertRaises(ValueError):
            self.summary([1e200, 1e200], [0.0, 0.0])

    def test_full_point_is_separate_gain_not_bootstrap_mean(self):
        result = self.summary([1.0, 3.0], [0.0, 1.0],
            full_point={"dm_value": 0.9, "dmplus_value": 0.8, "observed_reference_value": 0.5})
        self.assertAlmostEqual(result["full_point_metrics"]["absolute_error_gain"], 0.1)
        self.assertNotAlmostEqual(result["full_point_metrics"]["absolute_error_gain"],
                                  result["primary_metrics"]["absolute_error_gain"]["mean"])
        for point in ([], {"dm_value": 1}, {"dm_value": 1, "dmplus_value": float("inf"), "observed_reference_value": 0}):
            with self.subTest(point=point), self.assertRaises(ValueError):
                self.summary([1.0, 3.0], [0.0, 1.0], full_point=point)

    def test_conditional_interpretation_and_json_serialization(self):
        result = self.summary([1.0, 3.0], [0.0, 1.0])
        self.assertEqual(result["paired_test_interpretation"], "conditional_bootstrap_distribution_monte_carlo_comparison")
        self.assertFalse(result["author_table2_algorithm_recovered"])
        self.assertFalse(result["reference_is_causal_ground_truth"])
        self.assertEqual(result["primary_metrics"]["paired_t_test"]["multiple_testing_adjustment"], "none")
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
