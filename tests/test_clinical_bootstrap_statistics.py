"""Synthetic arithmetic and draw-accounting checks; no clinical data access."""

import copy
import importlib.util
import json
import math
from pathlib import Path
import statistics
import unittest


MODULE = Path(__file__).resolve().parents[1] / "src/april_repro/clinical_bootstrap_statistics.py"
spec = importlib.util.spec_from_file_location("clinical_bootstrap_statistics_tested", MODULE)
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)


def draw(draw_id, value, reference):
    return {
        "draw_id": draw_id,
        "status": "complete",
        "dm_value": value,
        "observed_reference_value": reference,
        "signed_error": value - reference,
    }


class BootstrapStatisticsTests(unittest.TestCase):
    def test_rmse_not_mae_and_sample_sd_not_mean_se(self):
        summary = stats.summarize_bootstrap_draws([draw(0, 2, 1), draw(1, 6, 3)], 2)
        self.assertEqual(summary["status"], "complete")
        result = summary["primary_metrics"]
        self.assertAlmostEqual(result["rmse"], math.sqrt(5))
        self.assertNotAlmostEqual(result["rmse"], 2)  # MAE would be 2.
        self.assertAlmostEqual(result["bootstrap_se_value"], math.sqrt(8))
        self.assertAlmostEqual(result["bootstrap_sd_error"], math.sqrt(2))
        self.assertNotAlmostEqual(result["bootstrap_sd_error"], 1)  # SD / sqrt(B).
        self.assertEqual(result["standard_deviation_ddof"], 1)
        self.assertIsNone(summary["diagnostic_valid_draw_metrics"])

    def test_delta_mcse_formula_and_labeled_one_se_bounds(self):
        result = stats.summarize_bootstrap_draws([draw(0, 2, 1), draw(1, 6, 3)], 2)["primary_metrics"]
        expected = statistics.stdev([1, 9]) / (2 * math.sqrt(2) * math.sqrt(5))
        self.assertAlmostEqual(result["rmse_mc_se_delta"], expected)
        self.assertAlmostEqual(result["rmse_mc_se_lower_bound"], math.sqrt(5) - expected)
        self.assertAlmostEqual(result["rmse_mc_se_upper_bound"], math.sqrt(5) + expected)
        self.assertEqual(result["rmse_error_bar_kind"], "finite_B_monte_carlo_standard_error_delta")

    def test_equal_squared_errors_have_zero_mcse_but_nonzero_error_sd(self):
        result = stats.summarize_bootstrap_draws([draw(0, -1, 0), draw(1, 1, 0)], 2)["primary_metrics"]
        self.assertEqual(result["rmse"], 1)
        self.assertEqual(result["rmse_mc_se_delta"], 0)
        self.assertAlmostEqual(result["bootstrap_sd_error"], math.sqrt(2))

    def test_all_zero_errors_have_zero_mcse_even_with_varying_values(self):
        result = stats.summarize_bootstrap_draws([draw(0, 1, 1), draw(1, 3, 3)], 2)["primary_metrics"]
        for key in ("rmse", "bootstrap_sd_error", "rmse_mc_se_delta", "rmse_mc_se_lower_bound", "rmse_mc_se_upper_bound"):
            self.assertEqual(result[key], 0)
        self.assertAlmostEqual(result["bootstrap_se_value"], math.sqrt(2))

    def test_one_draw_has_rmse_but_no_sd_mcse_or_bounds_including_zero_error(self):
        for value in (0, 3):
            with self.subTest(value=value):
                result = stats.summarize_bootstrap_draws([draw(0, value, 0)], 1)["primary_metrics"]
                self.assertEqual(result["rmse"], value)
                for key in ("bootstrap_se_value", "bootstrap_sd_error", "rmse_mc_se_delta", "rmse_mc_se_lower_bound", "rmse_mc_se_upper_bound"):
                    self.assertIsNone(result[key])

    def test_partial_metrics_never_become_primary_and_missing_draws_are_pending(self):
        summary = stats.summarize_bootstrap_draws([draw(3, 3, 0), draw(1, 1, 0)], 5)
        self.assertEqual(summary["status"], "incomplete")
        self.assertIsNone(summary["primary_metrics"])
        self.assertEqual(summary["completed_draws"], 2)
        self.assertEqual(summary["failed_draws"], 0)
        self.assertEqual(summary["pending_draws"], 3)
        self.assertEqual(summary["completed_draw_ids"], [1, 3])
        self.assertEqual(summary["pending_draw_ids"], [0, 2, 4])
        self.assertAlmostEqual(summary["diagnostic_valid_draw_metrics"]["rmse"], math.sqrt(5))
        self.assertEqual(summary["diagnostic_valid_draw_metrics_label"], "partial_valid_draws_only_not_primary")

    def test_failed_and_pending_are_separate_and_null_results_allowed(self):
        summary = stats.summarize_bootstrap_draws([
            {"draw_id": 3, "status": "pending", "dm_value": None},
            draw(1, 1, 0),
            {"draw_id": 0, "status": "failed", "failure_reason": "nonconverged"},
        ], 5)
        self.assertIsNone(summary["primary_metrics"])
        self.assertEqual(summary["completed_draws"], 1)
        self.assertEqual(summary["failed_draws"], 1)
        self.assertEqual(summary["pending_draws"], 3)
        self.assertEqual(summary["failed_draw_ids"], [0])
        self.assertEqual(summary["pending_draw_ids"], [2, 3, 4])
        self.assertEqual(sum(summary[key] for key in ("completed_draws", "failed_draws", "pending_draws")), 5)

    def test_all_terminal_with_failure_is_still_incomplete(self):
        summary = stats.summarize_bootstrap_draws([draw(0, 1, 0), {"draw_id": 1, "status": "failed"}], 2)
        self.assertEqual(summary["status"], "incomplete")
        self.assertEqual(summary["pending_draws"], 0)
        self.assertIsNone(summary["primary_metrics"])

    def test_empty_records_are_all_pending_not_a_population_diagnosis(self):
        summary = stats.summarize_bootstrap_draws([])
        self.assertEqual(summary["planned_draws"], 500)
        self.assertEqual(summary["pending_draws"], 500)
        self.assertEqual(summary["failed_draws"], 0)
        self.assertEqual(summary["status"], "incomplete")
        self.assertIsNone(summary["primary_metrics"])
        self.assertIsNone(summary["diagnostic_valid_draw_metrics"])
        self.assertIsNone(summary["diagnostic_valid_draw_metrics_label"])

    def test_no_completed_records_never_produce_diagnostic_metrics(self):
        summary = stats.summarize_bootstrap_draws([{"draw_id": 0, "status": "failed"}], 1)
        self.assertEqual(summary["failed_draws"], 1)
        self.assertIsNone(summary["diagnostic_valid_draw_metrics"])

    def test_duplicate_ids_rejected_across_statuses_instead_of_resume_overwrite(self):
        for second in (draw(0, 1, 0), {"draw_id": 0, "status": "failed"}, {"draw_id": 0, "status": "pending"}):
            with self.subTest(second=second), self.assertRaisesRegex(ValueError, "duplicate draw_id"):
                stats.summarize_bootstrap_draws([draw(0, 1, 0), second], 2)

    def test_out_of_range_and_noninteger_draw_ids_rejected(self):
        for draw_id in (-1, 2, 1.0, "1", True, None):
            with self.subTest(draw_id=draw_id), self.assertRaises(ValueError):
                stats.summarize_bootstrap_draws([draw(draw_id, 1, 0)], 2)

    def test_planned_draw_count_must_be_positive_integer(self):
        for count in (-1, 0, 1.0, "1", True, None):
            with self.subTest(count=count), self.assertRaises(ValueError):
                stats.summarize_bootstrap_draws([], count)

    def test_unknown_status_and_nonmapping_records_rejected(self):
        for record in ({"draw_id": 0}, {"draw_id": 0, "status": "success"}, [], None):
            with self.subTest(record=record), self.assertRaises(ValueError):
                stats.summarize_bootstrap_draws([record], 1)

    def test_all_three_complete_fields_must_be_finite_real_numbers(self):
        for field in ("dm_value", "observed_reference_value", "signed_error"):
            for value in (float("nan"), float("inf"), -float("inf"), True, None, "1", 1 + 0j):
                record = draw(0, 1, 0)
                record[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    stats.summarize_bootstrap_draws([record], 1)
            record = draw(0, 1, 0)
            del record[field]
            with self.assertRaises(ValueError):
                stats.summarize_bootstrap_draws([record], 1)

    def test_failed_or_pending_cannot_smuggle_numeric_results(self):
        for status in ("failed", "pending"):
            for field in ("dm_value", "observed_reference_value", "signed_error"):
                with self.subTest(status=status, field=field), self.assertRaises(ValueError):
                    stats.summarize_bootstrap_draws([{"draw_id": 0, "status": status, field: 0.0}], 1)

    def test_signed_error_consistency_and_normal_float_roundoff(self):
        record = draw(0, 0.3, 0.2)
        record["signed_error"] = 0.1
        self.assertEqual(stats.summarize_bootstrap_draws([record], 1)["status"], "complete")
        for wrong in (-0.1, 0.100001):
            record["signed_error"] = wrong
            with self.assertRaisesRegex(ValueError, "inconsistent"):
                stats.summarize_bootstrap_draws([record], 1)

    def test_sorting_generator_json_serializability_and_no_input_mutation(self):
        records = [draw(1, 3, 2), draw(0, 2, 1)]
        original = copy.deepcopy(records)
        summary = stats.summarize_bootstrap_draws(iter(records), 2)
        self.assertEqual(records, original)
        self.assertEqual(summary, stats.summarize_bootstrap_draws(reversed(records), 2))
        self.assertEqual(json.loads(json.dumps(summary, allow_nan=False)), summary)

    def test_large_and_small_finite_errors_do_not_square_overflow_or_underflow(self):
        for scale in (1e200, 1e-200):
            with self.subTest(scale=scale):
                result = stats.summarize_bootstrap_draws([draw(0, scale, 0), draw(1, 3 * scale, 0)], 2)["primary_metrics"]
                self.assertAlmostEqual(result["rmse"] / scale, math.sqrt(5))
                self.assertAlmostEqual(result["rmse_mc_se_delta"] / scale, 2 / math.sqrt(5))
                self.assertAlmostEqual(result["bootstrap_sd_error"] / scale, math.sqrt(2))
                json.dumps(result, allow_nan=False)

    def test_mathematically_unrepresentable_difference_or_sd_is_rejected(self):
        with self.assertRaises(ValueError):
            stats.summarize_bootstrap_draws([{
                "draw_id": 0, "status": "complete", "dm_value": 1.7e308,
                "observed_reference_value": -1.7e308, "signed_error": 1.7e308,
            }], 1)
        with self.assertRaises(ValueError):
            stats.summarize_bootstrap_draws([draw(0, -1.7e308, -1.7e308), draw(1, 1.7e308, 1.7e308)], 2)


if __name__ == "__main__":
    unittest.main()
