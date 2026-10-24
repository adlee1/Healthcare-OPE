"""Hand-calculated scientific invariants, independent of model training."""

import math
import unittest

from april_repro.estimators import direct_method
from april_repro.metrics import bias, lab_weighted_f1, marginal_entropy, rmse, weighted_f1
from april_repro.rewards import bin_lab_value, reward_from_lab


class RewardTests(unittest.TestCase):
    def test_reference_ranges_and_published_scale(self):
        for task, lower, upper in (("potassium", 3.5, 4.5), ("sodium", 135, 145)):
            for value in (lower, (lower + upper) / 2, upper):
                self.assertEqual(reward_from_lab(value, task), 1.0)
            self.assertAlmostEqual(reward_from_lab(lower - 2.5, task), math.exp(-0.5))
            self.assertAlmostEqual(reward_from_lab(upper + 2.5, task), math.exp(-0.5))
            near = reward_from_lab(lower - 1e-6, task)
            far = reward_from_lab(lower - 5, task)
            self.assertAlmostEqual(near, 1.0, places=10)
            self.assertGreater(near, far)
            self.assertGreaterEqual(far, 0.0)
        # This assertion deliberately locks the printed sigma, not a
        # visually inferred potassium-figure bandwidth.
        self.assertAlmostEqual(reward_from_lab(1, "potassium"), math.exp(-0.5))
        self.assertEqual(reward_from_lab(-1e308, "potassium"), 0.0)

    def test_all_f1_boundaries_are_left_closed(self):
        for task, boundaries in (
            ("potassium", [3.2, 5, 6]),
            ("sodium", [118, 135, 152, 169]),
        ):
            for index, boundary in enumerate(boundaries):
                self.assertEqual(bin_lab_value(boundary - 1e-6, task), index)
                self.assertEqual(bin_lab_value(boundary, task), index + 1)
        # A normal-range boundary is not automatically an F1 threshold.
        self.assertEqual(bin_lab_value(145, "sodium"), 2)

    def test_invalid_lab_task_and_scale(self):
        for value in (math.nan, math.inf, -math.inf, True, "4.0"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    reward_from_lab(value, "potassium")
                with self.assertRaises(ValueError):
                    bin_lab_value(value, "potassium")
        with self.assertRaises(ValueError):
            reward_from_lab(4, "chloride")
        for scale in (0, -1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                reward_from_lab(4, "potassium", sigma=scale)


class MetricTests(unittest.TestCase):
    def test_f1_by_hand_and_missing_classes(self):
        # Class 0 F1=4/5 and support=3; class 1 F1=2/3 and support=1.
        expected = (3 / 4) * (4 / 5) + (1 / 4) * (2 / 3)
        self.assertAlmostEqual(weighted_f1([0, 0, 0, 1], [0, 0, 1, 1], num_classes=4), expected)
        self.assertEqual(weighted_f1([1, 1], [1, 1], num_classes=5), 1.0)
        self.assertEqual(weighted_f1([0, 0], [2, 2], num_classes=4), 0.0)
        self.assertAlmostEqual(
            lab_weighted_f1([3, 3, 3, 4], [3, 3, 4, 4], "potassium"), expected
        )

    def test_rmse_is_not_mean_absolute_error_and_bias_keeps_sign(self):
        self.assertAlmostEqual(rmse([1, 3], 0), math.sqrt(5))
        self.assertNotAlmostEqual(rmse([1, 3], 0), 2)
        self.assertAlmostEqual(rmse([2, 2], [1, 5]), math.sqrt(5))
        self.assertEqual(bias([2, 2], [1, 5]), -1)
        self.assertEqual(bias([2, 4], 3), 0)
        self.assertAlmostEqual(rmse([1e200, 1e200], 0) / 1e200, 1.0)

    def test_entropy_by_hand_and_full_action_spaces(self):
        self.assertEqual(marginal_entropy([5, 0, 0, 0]), 0.0)
        self.assertAlmostEqual(marginal_entropy([1] * 4), math.log(4))
        self.assertAlmostEqual(marginal_entropy([2] * 6), math.log(6))
        expected = -0.25 * math.log(0.25) - 0.75 * math.log(0.75)
        self.assertAlmostEqual(marginal_entropy([1, 3, 0]), expected)
        self.assertAlmostEqual(marginal_entropy([10, 30, 0]), expected)

    def test_invalid_metric_inputs(self):
        for truth, prediction, classes in (
            ([], [], 4), ([0], [], 4), ([0], [4], 4),
            ([0], [-1], 4), ([True], [0], 4), ([0.0], [0], 4),
            ([0], [0], 0), ([0], [0], 4.0),
        ):
            with self.assertRaises(ValueError):
                weighted_f1(truth, prediction, num_classes=classes)
        for metric in (rmse, bias):
            for estimates, references in (([], 0), ([1], []), ([math.nan], 0), ([1], math.inf)):
                with self.assertRaises(ValueError):
                    metric(estimates, references)
        for counts in ([], [0, 0], [1, -1], [1, 0.5], [True], [math.nan]):
            with self.assertRaises(ValueError):
                marginal_entropy(counts)


class DirectMethodTests(unittest.TestCase):
    def test_stochastic_and_deterministic_policies_by_hand(self):
        probabilities = [[0.25, 0.75], [1, 0]]
        values = [[0, 1], [0.2, 0.9]]
        self.assertAlmostEqual(direct_method(probabilities, values), (0.75 + 0.2) / 2)
        self.assertAlmostEqual(direct_method(probabilities, values, [0.8, 0.2]), 0.64)
        self.assertEqual(direct_method([[0, 1]], [[0.1, 0.9]]), 0.9)

    def test_unclipped_values_and_zero_mass_context(self):
        self.assertEqual(direct_method([[1, 0]], [[1.5, -0.5]]), 1.5)
        self.assertEqual(direct_method([[1], [1]], [[7], [3]], [0, 1]), 3)

    def test_shape_probability_and_finite_validation(self):
        invalid_cases = [
            ([], [], None), ([[]], [[]], None),
            ([[1], [0.5, 0.5]], [[1], [1]], None),
            ([[1]], [[1, 2]], None), ([[1]], [[1], [2]], None),
            ([[0.2, 0.2]], [[1, 2]], None),
            ([[-0.1, 1.1]], [[1, 2]], None),
            ([[math.nan, 0]], [[1, 2]], None),
            ([[1]], [[math.inf]], None),
            ([[1]], [[1]], [2]), ([[1]], [[1]], []),
            ([[1], [1]], [[1], [2]], [-1, 2]),
            ([[1]], [[1]], [math.nan]),
        ]
        for probabilities, values, weights in invalid_cases:
            with self.subTest(probabilities=probabilities, values=values, weights=weights):
                with self.assertRaises(ValueError):
                    direct_method(probabilities, values, weights)


if __name__ == "__main__":
    unittest.main()
