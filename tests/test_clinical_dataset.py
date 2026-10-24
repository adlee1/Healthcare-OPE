"""Synthetic private-artifact loader tests; no database or patient data."""
import csv
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

try:
    import numpy as np
except ImportError:
    np = None

from april_repro.clinical_dataset import FOLD_CODES, ROLE_CODES, SPLIT_COLUMNS, load_clinical_dataset
from april_repro.cohort_patient_splits import build_patient_cohort_splits
from april_repro.cohort_splits import SPLITS
from april_repro.decision_features import FEATURES, IDENTITY, OUTCOMES
from april_repro.rewards import reward_from_lab


@unittest.skipIf(np is None, "NumPy model dependency is not installed")
class ClinicalDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-clinical-dataset-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.make_fixture()

    def write_csv(self, name, columns, rows):
        with (self.path / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def make_fixture(self, task="potassium", *, excluded_gender=False):
        self.features, self.outcomes, split_inputs = [], [], []
        actions = (0, 10, 20, 40, 0, 20) if task == "potassium" else (0, 100, 200, 300, 0, 500)
        for i, action in enumerate(actions):
            subject = str(1001 + i // 2)
            event = hashlib.sha256(("synthetic-" + str(i)).encode()).hexdigest()
            when = f"2100-01-02 {12 + i:02d}:00:00"
            gender = ("F", "M", "F")[i // 2]
            if excluded_gender and i >= 4:
                gender = ""
            feature = {"event_id": event, "subject_id": subject,
                       "hadm_id": str(2001 + i // 2), "decision_time": when}
            feature.update({name: str(20 + i) for name in FEATURES})
            feature["gender"] = gender
            for j, name in enumerate(FEATURES[10:]):
                feature[name] = str((i + j) % 2)
            if i == 0:
                feature["weight_kg"] = ""
                feature["administered_insulin"] = ""
            outcome = {name: "" for name in OUTCOMES}
            outcome.update({"event_id": event, "subject_id": subject, "hadm_id": feature["hadm_id"],
                            "task": task, "anchor_time": when.replace(" ", "T"), "action": str(action),
                            "post_lab_value": str(3.0 + i * 0.6 if task == "potassium" else 130 + i * 4)})
            split_inputs.append({"event_id": event, "subject_id": subject, "hadm_id": feature["hadm_id"],
                                 "gender": gender, "action": action, "renal_disease": i // 2 == 1,
                                 "cirrhosis": i // 2 == 1})
            self.features.append(feature)
            self.outcomes.append(outcome)
        assignments, split_summary = build_patient_cohort_splits(split_inputs, task)
        self.write_csv("features.csv", (*IDENTITY, *FEATURES), self.features)
        self.write_csv("outcomes.csv", OUTCOMES, list(reversed(self.outcomes)))
        self.write_csv("splits.csv", SPLIT_COLUMNS, list(reversed(assignments)))
        # Deliberately not a group table: the loader must hash, never parse it.
        (self.path / "groups.csv").write_text("synthetic-unused-group-content\n")
        coverage = {}
        for name in FEATURES:
            count = sum(row[name] != "" for row in self.features)
            coverage[name] = {"observed": count, "missing": 6 - count, "observed_fraction": count / 6}
            if name in FEATURES[10:]:
                coverage[name]["value_counts"] = dict(Counter(row[name] or "missing" for row in self.features))
        summary = {"task": task, "events": 6, "subjects": 3, "admissions": 3,
                   "feature_columns": list(FEATURES), "coverage": coverage,
                   "all_features_observed_events": sum(all(row[name] != "" for name in FEATURES) for row in self.features),
                   "raw_missing_values_preserved": True, "imputation_fitted": False, "splits": split_summary}
        self.manifest = {"status": "complete", "task": task, "completed_events": 6,
                         "rule_version": "treatment-features-scoped-v1",
                         "patient_split_rule_version": "cohort-patient-splits-v1", "summary": summary}
        self.refresh()

    def refresh(self):
        (self.path / "summary.json").write_text(json.dumps(self.manifest["summary"], sort_keys=True))
        self.manifest["outputs"] = {
            name: hashlib.sha256((self.path / name).read_bytes()).hexdigest()
            for name in ("features.csv", "outcomes.csv", "groups.csv", "splits.csv", "summary.json")}
        (self.path / "manifest.json").write_text(json.dumps(self.manifest, sort_keys=True))

    def change_csv(self, name, function):
        with (self.path / name).open(newline="") as handle:
            reader = csv.DictReader(handle)
            columns, rows = reader.fieldnames, list(reader)
        function(rows)
        self.write_csv(name, columns, rows)
        self.refresh()

    def test_event_id_join_with_independently_reordered_outcomes_and_splits(self):
        data = load_clinical_dataset(self.path)
        self.assertEqual(data.event_ids, tuple(row["event_id"] for row in self.features))
        np.testing.assert_array_equal(data.actions, [0, 10, 20, 40, 0, 20])
        np.testing.assert_array_equal(data.post_labs, [3.0 + i * 0.6 for i in range(6)])
        np.testing.assert_allclose(data.rewards, [reward_from_lab(3.0 + i * 0.6, "potassium") for i in range(6)])
        self.assertFalse(data.provenance["groups_csv_used_as_predictors"])
        self.assertIs(data.X, data.features)

    def test_compact_types_feature_order_and_missing_preservation(self):
        data = load_clinical_dataset(self.path)
        self.assertEqual(data.features.shape, (6, 15))
        self.assertEqual(data.feature_names, FEATURES)
        self.assertEqual(data.features.dtype, np.float64)
        self.assertEqual(data.subject_ids.dtype, np.int64)
        self.assertEqual(data.hadm_ids.dtype, np.int64)
        self.assertEqual(data.roles.dtype, np.int8)
        self.assertEqual(data.roles.shape, (6, 3))
        self.assertEqual(data.folds.dtype, np.int8)
        self.assertTrue(np.isnan(data.features[0, FEATURES.index("weight_kg")]))
        self.assertTrue(np.isnan(data.features[0, FEATURES.index("administered_insulin")]))
        np.testing.assert_array_equal(data.features[:, FEATURES.index("gender")], [0, 0, 1, 1, 0, 0])

    def test_masks_select_declared_patient_role_and_fold(self):
        data = load_clinical_dataset(self.path)
        for split in SPLITS:
            for role, code in ROLE_CODES.items():
                expected = data.roles[:, SPLITS.index(split)] == code
                np.testing.assert_array_equal(data.mask(split, role), expected)
                for fold, fold_code in FOLD_CODES.items():
                    np.testing.assert_array_equal(data.mask(split, role, fold), expected & (data.folds == fold_code))
        for values in (("unknown", "target"), ("gender", "unknown"), ("gender", "target", "test")):
            with self.assertRaises(ValueError):
                data.mask(*values)

    def test_sodium_actions_and_rewards(self):
        self.make_fixture("sodium")
        data = load_clinical_dataset(self.path)
        np.testing.assert_array_equal(data.actions, [0, 100, 200, 300, 0, 500])
        np.testing.assert_allclose(data.rewards, [reward_from_lab(130 + i * 4, "sodium") for i in range(6)])

    def test_valid_excluded_role_and_missing_gender_preserved(self):
        self.make_fixture(excluded_gender=True)
        data = load_clinical_dataset(self.path)
        self.assertEqual(int(data.mask("gender", "excluded").sum()), 2)
        self.assertTrue(np.isnan(data.features[4:, FEATURES.index("gender")]).all())

    def test_incomplete_or_unsupported_artifact_rejected(self):
        for field, value in (("status", "running"), ("task", "unknown"), ("rule_version", "legacy"),
                             ("patient_split_rule_version", "cohort-splits-v1")):
            original = self.manifest[field]
            self.manifest[field] = value
            self.refresh()
            with self.subTest(field=field), self.assertRaises(ValueError):
                load_clinical_dataset(self.path)
            self.manifest[field] = original

    def test_modified_csv_without_updated_hash_rejected(self):
        with (self.path / "outcomes.csv").open("a") as handle:
            handle.write("\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            load_clinical_dataset(self.path)

    def test_groups_hash_checked_without_parsing_groups(self):
        (self.path / "groups.csv").write_text("changed synthetic groups\n")
        with self.assertRaisesRegex(ValueError, "groups.csv"):
            load_clinical_dataset(self.path)

    def test_duplicate_feature_keys_rejected(self):
        self.change_csv("features.csv", lambda rows: rows.__setitem__(1, dict(rows[0])))
        with self.assertRaisesRegex(ValueError, "Duplicate feature"):
            load_clinical_dataset(self.path)

    def test_duplicate_outcome_keys_rejected(self):
        self.change_csv("outcomes.csv", lambda rows: rows.__setitem__(1, dict(rows[0])))
        with self.assertRaisesRegex(ValueError, "Duplicate outcome"):
            load_clinical_dataset(self.path)

    def test_outcome_identity_or_unknown_key_rejected(self):
        for field, value in (("subject_id", "9999"), ("hadm_id", "9999"), ("task", "sodium"),
                             ("event_id", "f" * 64)):
            self.make_fixture()
            self.change_csv("outcomes.csv", lambda rows: rows[0].update({field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                load_clinical_dataset(self.path)

    def test_outcome_missing_event_rejected(self):
        self.change_csv("outcomes.csv", lambda rows: rows.pop())
        with self.assertRaisesRegex(ValueError, "Missing outcome"):
            load_clinical_dataset(self.path)

    def test_outcome_anchor_must_match_feature_clock(self):
        self.change_csv("outcomes.csv", lambda rows: rows[0].update(anchor_time="2100-02-01T12:00:00"))
        with self.assertRaisesRegex(ValueError, "decision times differ"):
            load_clinical_dataset(self.path)

    def test_action_support_and_finite_post_lab_enforced(self):
        for field, value in (("action", "30"), ("action", "20.0"), ("post_lab_value", "NaN"),
                             ("post_lab_value", "Infinity"), ("post_lab_value", "")):
            self.make_fixture()
            self.change_csv("outcomes.csv", lambda rows: rows[0].update({field: value}))
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                load_clinical_dataset(self.path)

    def test_feature_unknown_categories_and_explicit_nonfinite_rejected(self):
        for field, value in (("gender", "X"), ("administered_insulin", "yes"),
                             ("administered_propofol", "2"), ("age", "NaN"), ("weight_kg", "inf")):
            self.make_fixture()
            self.change_csv("features.csv", lambda rows: rows[0].update({field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                load_clinical_dataset(self.path)

    def test_all_fifteen_feature_columns_required(self):
        columns = [name for name in (*IDENTITY, *FEATURES) if name != "creatinine"]
        self.write_csv("features.csv", columns, [{k: v for k, v in row.items() if k in columns} for row in self.features])
        self.refresh()
        with self.assertRaisesRegex(ValueError, "columns"):
            load_clinical_dataset(self.path)

    def test_unknown_split_role_and_fold_labels_rejected(self):
        for field in ("split", "cohort_role", "fold"):
            self.make_fixture()
            self.change_csv("splits.csv", lambda rows: rows[0].update({field: "unknown"}))
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Unknown split"):
                load_clinical_dataset(self.path)

    def test_split_identity_and_action_mismatch_rejected(self):
        for field, value in (("subject_id", "9999"), ("hadm_id", "9999"), ("action", "10")):
            self.make_fixture()
            self.change_csv("splits.csv", lambda rows: rows[0].update({field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                load_clinical_dataset(self.path)

    def test_duplicate_event_split_pair_rejected(self):
        self.change_csv("splits.csv", lambda rows: rows.__setitem__(1, dict(rows[0])))
        with self.assertRaisesRegex(ValueError, "Duplicate event and split"):
            load_clinical_dataset(self.path)

    def test_missing_split_assignment_rejected(self):
        self.change_csv("splits.csv", lambda rows: rows.pop())
        with self.assertRaisesRegex(ValueError, "Incomplete three-split"):
            load_clinical_dataset(self.path)

    def test_patient_role_leakage_rejected(self):
        def change(rows):
            chosen = next(row for row in rows if row["subject_id"] == "1001" and row["split"] == "gender")
            chosen["cohort_role"] = "target"
        self.change_csv("splits.csv", change)
        with self.assertRaisesRegex(ValueError, "multiple roles"):
            load_clinical_dataset(self.path)

    def test_patient_fold_leakage_rejected(self):
        def change(rows):
            rows[0]["fold"] = "validation" if rows[0]["fold"] == "train" else "train"
        self.change_csv("splits.csv", change)
        with self.assertRaisesRegex(ValueError, "fold leakage"):
            load_clinical_dataset(self.path)

    def test_manifest_population_and_split_counts_checked(self):
        for mutation in (
            lambda m: m["summary"].update(subjects=4),
            lambda m: m["summary"].update(admissions=4),
            lambda m: m["summary"]["splits"]["splits"]["gender"]["groups"]["behavior"].update(events=999),
            lambda m: m["summary"]["coverage"]["age"].update(observed=5),
        ):
            self.make_fixture()
            mutation(self.manifest)
            self.refresh()
            with self.assertRaisesRegex(ValueError, "count mismatch"):
                load_clinical_dataset(self.path)


if __name__ == "__main__":
    unittest.main()
