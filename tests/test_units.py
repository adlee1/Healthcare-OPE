"""Synthetic physical-unit checks; no clinical cohort or dosing advice."""
import unittest

from april_repro.units import sodium_meq_from_3pct_saline_ml


class SalineUnitTests(unittest.TestCase):
    def test_label_concentration_and_volume_scaling(self):
        self.assertEqual(sodium_meq_from_3pct_saline_ml(1000), 513)
        self.assertEqual(sodium_meq_from_3pct_saline_ml(500), 256.5)
        self.assertEqual(sodium_meq_from_3pct_saline_ml(100), 51.3)
        self.assertEqual(sodium_meq_from_3pct_saline_ml(0), 0)
        self.assertAlmostEqual(sodium_meq_from_3pct_saline_ml(12.5), 6.4125)

    def test_milliliters_are_not_copied_or_binned_as_actions(self):
        converted = sodium_meq_from_3pct_saline_ml(500)
        self.assertNotEqual(converted, 500)
        self.assertNotIn(converted, (0, 100, 200, 300, 400, 500))

    def test_invalid_or_ambiguous_source_amounts_fail(self):
        for value in (None, True, False, "500", "100-200", -1,
                      float("nan"), float("inf"), float("-inf"), 10**400):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                sodium_meq_from_3pct_saline_ml(value)


if __name__ == "__main__":
    unittest.main()
