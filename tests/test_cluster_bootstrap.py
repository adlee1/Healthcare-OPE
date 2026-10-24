"""Synthetic patient-cluster bootstrap; never fit models or query patient data."""
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

try:
    import numpy as np
except ImportError:
    np = None

from april_repro.clinical_dataset import FOLD_CODES, ROLE_CODES
from april_repro.cluster_bootstrap import DEFAULT_SEED, POPULATIONS, build_cluster_population
from april_repro.cohort_splits import SPLITS


class SyntheticDataset:
    def __init__(self, subjects=(30, 10, 30, 20, 20, 30), *, task="potassium"):
        self.task = task
        self.subject_ids = np.asarray(subjects, dtype=np.int64)
        self.event_ids = tuple(hashlib.sha256(("synthetic-" + str(i)).encode()).hexdigest() for i in range(len(subjects)))
        self.roles = np.zeros((len(subjects), 3), dtype=np.int8)
        self.folds = np.zeros(len(subjects), dtype=np.int8)
        self.provenance = {"manifest_sha256": hashlib.sha256(b"synthetic-manifest").hexdigest()}

    def mask(self, split, role, fold=None):
        mask = self.roles[:, SPLITS.index(split)] == ROLE_CODES[role]
        return mask if fold is None else mask & (self.folds == FOLD_CODES[fold])


@unittest.skipIf(np is None, "NumPy model dependency is not installed")
class ClusterBootstrapTests(unittest.TestCase):
    def population(self, dataset=None, split="gender", population="behavior_train"):
        return build_cluster_population(dataset or SyntheticDataset(), split, population)

    def test_unsorted_input_clusters_all_patient_events(self):
        pop = self.population()
        np.testing.assert_array_equal(pop.subject_ids, [10, 20, 30])
        np.testing.assert_array_equal(pop.cluster_sizes, [1, 2, 3])
        np.testing.assert_array_equal(pop.event_indices, [1, 3, 4, 0, 2, 5])
        self.assertEqual(pop.metadata["source_subjects"], 3)
        self.assertEqual(pop.metadata["source_events"], 6)

    def test_known_counts_preserve_multiplicity_and_variable_event_n(self):
        pop = self.population()
        rows = pop.indices_from_counts([2, 0, 1])
        np.testing.assert_array_equal(rows, [1, 1, 0, 2, 5])
        np.testing.assert_array_equal(np.bincount(rows, minlength=6), [1, 2, 1, 0, 0, 1])
        self.assertEqual(len(pop.indices_from_counts([0, 0, 3])), 9)
        # Two copies of a one-event patient and one of a three-event patient:
        # event-equal = 4, whereas patient-mean averaging would give 20/3.
        outcomes = np.asarray([0, 10, 0, 99, 99, 0], dtype=float)
        self.assertEqual(float(outcomes[rows].mean()), 4.0)
        self.assertNotEqual(float(outcomes[rows].mean()), 20 / 3)

    def test_seed_draw_reentrancy_and_call_order_independence(self):
        pop = self.population()
        first = pop.draw(17)
        for draw_id in (499, 0, 33, 17, 2):
            pop.draw(draw_id)
        second = pop.draw(17)
        np.testing.assert_array_equal(first.event_indices, second.event_indices)
        np.testing.assert_array_equal(first.patient_counts, second.patient_counts)
        self.assertEqual(first.draw_sha256, second.draw_sha256)
        self.assertEqual(first.metadata["seed"], DEFAULT_SEED)
        self.assertEqual(first.status, "complete")
        self.assertEqual(first.metadata["sampled_patient_draws"], 3)

    def test_population_evaluation_order_does_not_change_draw(self):
        dataset = SyntheticDataset((1, 1, 2, 3, 3, 4, 5, 5, 6))
        dataset.roles[dataset.subject_ids >= 3, :] = ROLE_CODES["target"]
        dataset.folds[dataset.subject_ids >= 5] = FOLD_CODES["validation"]
        direct = {name: self.population(dataset, population=name).draw(8) for name in POPULATIONS}
        reverse = {name: self.population(dataset, population=name).draw(8) for name in reversed(POPULATIONS)}
        for name in POPULATIONS:
            np.testing.assert_array_equal(direct[name].patient_counts, reverse[name].patient_counts)
            self.assertEqual(direct[name].draw_sha256, reverse[name].draw_sha256)
        keys = {draw.metadata["sampling_key_sha256"] for draw in direct.values()}
        self.assertEqual(len(keys), 3)

    def test_task_split_seed_draw_id_are_distinct_rng_keys(self):
        baseline = self.population().draw(0)
        alternatives = [self.population().draw(1), self.population().draw(0, seed="other"),
                        self.population(split="dosage").draw(0),
                        self.population(SyntheticDataset(task="sodium")).draw(0)]
        self.assertEqual(len({d.metadata["sampling_key_sha256"] for d in [baseline, *alternatives]}), 5)

    def test_only_original_selected_patients_are_drawn_with_all_events(self):
        dataset = SyntheticDataset((1, 2, 1, 3, 4, 3, 4, 5))
        dataset.roles[np.isin(dataset.subject_ids, [3, 4, 5]), :] = ROLE_CODES["target"]
        dataset.folds[dataset.subject_ids == 5] = FOLD_CODES["validation"]
        for name in POPULATIONS:
            pop = self.population(dataset, population=name)
            draw = pop.draw(4)
            role, fold = POPULATIONS[name]
            self.assertTrue(dataset.mask("gender", role, fold)[draw.event_indices].all())
            actual = np.bincount(draw.event_indices, minlength=len(dataset.event_ids))
            for subject, count in zip(draw.subject_ids, draw.patient_counts):
                np.testing.assert_array_equal(actual[dataset.subject_ids == subject],
                                              np.full((dataset.subject_ids == subject).sum(), count))
            self.assertEqual(draw.metadata["sampled_events"], len(draw.event_indices))

    def test_input_reordering_keeps_same_patient_counts(self):
        left = self.population(SyntheticDataset((30, 10, 30, 20, 20, 30))).draw(29)
        right = self.population(SyntheticDataset((20, 30, 10, 20, 30, 30))).draw(29)
        np.testing.assert_array_equal(left.subject_ids, right.subject_ids)
        np.testing.assert_array_equal(left.patient_counts, right.patient_counts)
        self.assertEqual(left.metadata["sampled_events"], right.metadata["sampled_events"])

    def test_empty_population_remains_not_estimable(self):
        pop = self.population(population="target_validation")
        self.assertEqual(pop.n_subjects, 0)
        draw = pop.draw(0)
        self.assertEqual(draw.status, "not_estimable")
        self.assertEqual(draw.metadata["reason"], "empty_population")
        self.assertEqual(draw.metadata["redraws"], 0)
        self.assertEqual(draw.metadata["sampled_patient_draws"], 0)
        self.assertEqual(draw.metadata["sampled_events"], 0)
        self.assertEqual(draw.event_indices.dtype, np.int64)
        self.assertEqual(pop.indices_from_counts([]).size, 0)

    def test_empty_dataset_is_well_defined(self):
        draw = self.population(SyntheticDataset(())).draw(499)
        self.assertEqual(draw.status, "not_estimable")
        self.assertEqual(draw.subject_ids.size, 0)

    def test_no_redraw_to_recover_omitted_patient_or_rare_action(self):
        pop = self.population()
        rng = SimpleNamespace(integers=Mock(return_value=np.asarray([0, 0, 0], dtype=np.int64)),
                              bit_generator=SimpleNamespace())
        with patch("april_repro.cluster_bootstrap.np.random.default_rng", return_value=rng):
            draw = pop.draw(0)
        self.assertEqual(rng.integers.call_count, 1)
        np.testing.assert_array_equal(draw.patient_counts, [3, 0, 0])
        np.testing.assert_array_equal(draw.event_indices, [1, 1, 1])
        self.assertEqual(draw.metadata["redraws"], 0)

    def test_single_patient_repeats_once_without_splitting_its_events(self):
        pop = self.population(SyntheticDataset((7, 7, 7)))
        draw = pop.draw(32)
        np.testing.assert_array_equal(draw.patient_counts, [1])
        np.testing.assert_array_equal(draw.event_indices, [0, 1, 2])

    def test_invalid_draw_ids_and_seeds_fail(self):
        pop = self.population()
        for value in (-1, 500, 1.0, True, "1", None):
            with self.subTest(draw_id=value), self.assertRaises(ValueError):
                pop.draw(value)
        for value in ("", 123, None):
            with self.subTest(seed=value), self.assertRaises(ValueError):
                pop.draw(0, seed=value)
        self.assertEqual(pop.draw(np.int64(499)).metadata["draw_id"], 499)

    def test_invalid_counts_fail_instead_of_altering_bootstrap_n(self):
        pop = self.population()
        for counts in ([1, 1], [1, 1, 0], [-1, 2, 2], [1.0, 1.0, 1.0],
                       [True, True, True], [[1, 1, 1]], [4, 0, 0]):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                pop.indices_from_counts(counts)
        with self.assertRaises(ValueError):
            self.population(population="target_validation").indices_from_counts([0])

    def test_original_role_or_fold_leakage_is_rejected(self):
        for field in ("role", "fold"):
            dataset = SyntheticDataset()
            if field == "role":
                dataset.roles[0, 0] = ROLE_CODES["target"]
            else:
                dataset.folds[0] = FOLD_CODES["validation"]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "crosses original"):
                self.population(dataset)

    def test_wrong_mask_cannot_select_other_population(self):
        dataset = SyntheticDataset()
        dataset.mask = lambda *args: np.ones(len(dataset.event_ids), dtype=bool)
        with self.assertRaisesRegex(ValueError, "mask differs"):
            self.population(dataset, population="target_validation")

    def test_invalid_population_split_and_codes_rejected(self):
        with self.assertRaises(ValueError):
            self.population(population="behavior_validation")
        with self.assertRaises(ValueError):
            self.population(split="unknown")
        dataset = SyntheticDataset()
        dataset.roles[0, 0] = 99
        with self.assertRaises(ValueError):
            self.population(dataset)
        dataset = SyntheticDataset()
        dataset.folds = dataset.folds.astype(float)
        with self.assertRaises(ValueError):
            self.population(dataset)

    def test_population_digest_binds_feature_input_and_membership(self):
        dataset = SyntheticDataset()
        original = self.population(dataset)
        dataset.provenance["manifest_sha256"] = "f" * 64
        changed = self.population(dataset)
        self.assertNotEqual(original.population_sha256, changed.population_sha256)
        self.assertNotEqual(original.draw(0).draw_sha256, changed.draw(0).draw_sha256)
        # Membership binding changes, but the keyed random patient positions do not.
        np.testing.assert_array_equal(original.draw(0).patient_counts, changed.draw(0).patient_counts)

    def test_private_counts_replay_and_metadata_are_compact_json(self):
        pop = self.population()
        draw = pop.draw(12)
        np.testing.assert_array_equal(pop.indices_from_counts(draw.patient_counts), draw.event_indices)
        self.assertEqual(len(draw.patient_counts), pop.n_subjects)
        json.dumps(pop.metadata)
        json.dumps(draw.metadata)
        self.assertNotIn("subject_ids", draw.metadata)
        self.assertEqual(len(draw.draw_sha256), 64)
        self.assertFalse(draw.patient_counts.flags.writeable)
        self.assertFalse(pop.event_indices.flags.writeable)


if __name__ == "__main__":
    unittest.main()
