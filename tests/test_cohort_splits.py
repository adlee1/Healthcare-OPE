"""Synthetic checks of APRIL group directions and global subject separation."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "src/april_repro/cohort_splits.py"
SPEC = importlib.util.spec_from_file_location("cohort_split_subject", PATH)
assert SPEC is not None and SPEC.loader is not None
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def row(event="synthetic-event", subject="synthetic-subject", action=20, **changes):
    return {
        "event_id": event, "subject_id": subject, "hadm_id": "synthetic-admission",
        "action": action, "gender": "F", "renal_disease": False, "cirrhosis": False,
        "eligible": True, **changes,
    }


def roles(assignments, split):
    return {item["event_id"]: item["cohort_role"] for item in assignments if item["split"] == split}


class CohortSplitTests(unittest.TestCase):
    def test_female_to_male_and_task_specific_comorbidity_directions(self):
        rows = [
            row("female", "s-a", gender="F", renal_disease=False, cirrhosis=True),
            row("male", "s-b", gender="M", renal_disease=True, cirrhosis=False),
        ]
        potassium, _ = m.build_cohort_splits(rows, "potassium")
        sodium, _ = m.build_cohort_splits(
            [{**item, "action": 100} for item in rows], "sodium",
        )
        self.assertEqual(roles(potassium, "gender"), {"female": "behavior", "male": "target"})
        self.assertEqual(roles(sodium, "gender"), roles(potassium, "gender"))
        self.assertEqual(roles(potassium, "comorbidity"), {"female": "behavior", "male": "target"})
        self.assertEqual(roles(sodium, "comorbidity"), {"female": "target", "male": "behavior"})

    def test_all_action_boundaries_including_zero_follow_declared_thresholds(self):
        for task, actions, low in (
            ("potassium", (0, 10, 20, 40), {0, 10, 20}),
            ("sodium", (0, 100, 200, 300, 400, 500), {0, 100, 200}),
        ):
            with self.subTest(task=task):
                assignments, _ = m.build_cohort_splits(
                    [row(str(action), str(action), action) for action in actions], task,
                )
                self.assertEqual(roles(assignments, "dosage"), {
                    str(action): "behavior" if action in low else "target"
                    for action in actions
                })

    def test_global_fold_is_identical_across_roles_tasks_admissions_and_order(self):
        rows = [
            row("low", "same-subject", 0, hadm_id="a1"),
            row("high", "same-subject", 40, hadm_id="a2", gender="M", renal_disease=True),
        ]
        potassium, summary = m.build_cohort_splits(rows, "potassium")
        sodium, _ = m.build_cohort_splits(
            [{**item, "action": 0 if item["action"] == 0 else 500} for item in rows[::-1]],
            "sodium",
        )
        self.assertEqual(len({item["fold"] for item in potassium + sodium}), 1)
        self.assertEqual(summary["splits"]["dosage"]["role_subject_overlap"], 1)
        self.assertEqual(summary["splits"]["dosage"]["train_validation_subject_overlap"], 0)
        shuffled, _ = m.build_cohort_splits(rows[::-1], "potassium")
        self.assertEqual(shuffled, potassium)

    def test_fold_does_not_depend_on_dataset_membership(self):
        original, _ = m.build_cohort_splits([row()], "potassium")
        expanded, _ = m.build_cohort_splits(
            [row(), row("extra", "other-subject", 40)], "potassium",
        )
        self.assertEqual(original, [item for item in expanded if item["event_id"] == "synthetic-event"])
        self.assertEqual(m.subject_fold(12345), m.subject_fold("12345"))

    def test_train_and_validation_subjects_never_overlap(self):
        inputs = [
            row("event-" + str(i), "subject-" + str(i // 2), (0, 40)[i % 2])
            for i in range(1000)
        ]
        assignments, summary = m.build_cohort_splits(inputs, "potassium")
        train = {item["subject_id"] for item in assignments if item["fold"] == "train"}
        validation = {item["subject_id"] for item in assignments if item["fold"] == "validation"}
        self.assertFalse(train & validation)
        self.assertEqual(len(train | validation), 500)
        self.assertGreater(len(validation), 50)
        self.assertLess(len(validation), 150)
        self.assertTrue(all(
            report["train_validation_subject_overlap"] == 0
            for report in summary["splits"].values()
        ))

    def test_missing_group_flag_is_not_imputed_to_no_disease(self):
        for missing in (None, "", "unknown", "NULL", 2):
            with self.subTest(missing=missing):
                assignments, summary = m.build_cohort_splits(
                    [row(renal_disease=missing)], "potassium",
                )
                self.assertEqual(roles(assignments, "comorbidity"), {"synthetic-event": "excluded"})
                self.assertEqual(roles(assignments, "gender"), {"synthetic-event": "behavior"})
                self.assertEqual(roles(assignments, "dosage"), {"synthetic-event": "behavior"})
                self.assertEqual(summary["splits"]["comorbidity"]["groups"]["behavior"]["events"], 0)

    def test_sql_boolean_spellings_and_native_flags_are_equivalent(self):
        for flag in (False, 0, "f", "false", "0"):
            assignments, _ = m.build_cohort_splits([row(renal_disease=flag)], "potassium")
            self.assertEqual(roles(assignments, "comorbidity"), {"synthetic-event": "behavior"})
        for flag in (True, 1, "t", "true", "1"):
            assignments, _ = m.build_cohort_splits([row(renal_disease=flag)], "potassium")
            self.assertEqual(roles(assignments, "comorbidity"), {"synthetic-event": "target"})

    def test_unsupported_action_task_and_ineligible_rows_are_rejected(self):
        for action in (True, 20.0, "20.0", "NaN", "30", None):
            with self.subTest(action=action), self.assertRaises(ValueError):
                m.build_cohort_splits([row(action=action)], "potassium")
        for item, task in (
            (row(eligible=False), "potassium"),
            (row(eligible=""), "potassium"),
            (row(task="sodium"), "potassium"),
            (row(), "unsupported"),
        ):
            with self.subTest(task=task), self.assertRaises(ValueError):
                m.build_cohort_splits([item], task)

    def test_duplicate_or_missing_event_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            m.build_cohort_splits([row(), row()], "potassium")
        for changes in ({"event_id": ""}, {"subject_id": None}, {"subject_id": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                m.build_cohort_splits([row(**changes)], "potassium")

    def test_group_counts_conserve_events_and_track_action_support(self):
        inputs = [
            row("one", "s-one", 0, hadm_id="shared"),
            row("two", "s-two", 40, hadm_id="shared", gender="M"),
            row("three", "s-one", 20, hadm_id="shared", gender="unknown"),
        ]
        assignments, summary = m.build_cohort_splits(inputs, "potassium")
        self.assertEqual(len(assignments), 9)
        for report in summary["splits"].values():
            self.assertEqual(sum(group["events"] for group in report["groups"].values()), 3)
            for group in report["groups"].values():
                self.assertEqual(sum(group["action_distribution"].values()), group["events"])
                self.assertEqual(sum(fold["events"] for fold in group["folds"].values()), group["events"])
        groups = summary["splits"]["dosage"]["groups"]
        self.assertEqual(groups["behavior"]["action_distribution"], {"0": 1, "20": 1})
        self.assertEqual(groups["target"]["missing_action_support"], [0, 10, 20])
        self.assertEqual(summary["splits"]["comorbidity"]["groups"]["behavior"]["admissions"], 2)

    def test_summary_has_no_patient_event_admission_values_and_inputs_are_unchanged(self):
        secret = "SYNTHETIC-PRIVATE-SPLIT-MARKER"
        inputs = [row(secret + "-event", secret + "-subject", hadm_id=secret + "-admission")]
        before = copy.deepcopy(inputs)
        _, summary = m.build_cohort_splits(inputs, "potassium")
        self.assertNotIn(secret, json.dumps(summary))
        self.assertEqual(inputs, before)
        self.assertFalse(summary["diagnosis_labels_are_predictor_features"])
        self.assertFalse(summary["models_trained"])

    def test_empty_cohort_reports_missing_groups_without_fabricating_support(self):
        assignments, summary = m.build_cohort_splits([], "sodium")
        self.assertEqual(assignments, [])
        self.assertEqual(summary["input_subjects"], 0)
        for report in summary["splits"].values():
            self.assertFalse(report["behavior_and_target_present"])
            self.assertEqual(set(report["empty_model_groups"]), {
                "behavior/train", "behavior/validation", "target/train", "target/validation",
            })


if __name__ == "__main__":
    unittest.main()
