import copy
import importlib.util
import json
from pathlib import Path
import unittest

from april_repro.cohort_splits import subject_fold


spec = importlib.util.spec_from_file_location(
    "staged_patient_cohort_splits", Path(__file__).resolve().parents[1]
    / "src/april_repro/cohort_patient_splits.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
build = module.build_patient_cohort_splits


def row(event, subject, action=0, **extra):
    result = {
        "event_id": event, "subject_id": subject, "hadm_id": "same-admission",
        "action": action, "gender": "F", "renal_disease": False, "cirrhosis": False,
        "eligible": True,
    }
    result.update(extra)
    return result


def selected(assignments, split):
    return [r for r in assignments if r["split"] == split]


class PatientCohortSplitTests(unittest.TestCase):
    def test_any_high_k_patient_retains_all_low_zero_and_high_events(self):
        source = [row("a", "mixed", 0), row("b", "mixed", 20),
                  row("c", "mixed", 40), row("d", "low", 10)]
        original = copy.deepcopy(source)
        assignments, summary = build(source, "potassium")
        dosage = selected(assignments, "dosage")
        self.assertEqual({r["cohort_role"] for r in dosage if r["subject_id"] == "mixed"}, {"target"})
        self.assertEqual(len(assignments), 12)
        self.assertEqual(summary["splits"]["dosage"]["target_low_dose_events"], 2)
        self.assertEqual(summary["splits"]["dosage"]["target_high_dose_events"], 1)
        self.assertEqual(summary["splits"]["dosage"]["role_subject_overlap"], 0)
        self.assertEqual(source, original)

    def test_sodium_threshold_and_multiple_high_values(self):
        source = [row("a", "high", 100), row("b", "high", 300),
                  row("c", "high", 500), row("d", "low", 200), row("e", "low", 0)]
        assignments, summary = build(source, "sodium")
        roles = {r["subject_id"]: r["cohort_role"] for r in selected(assignments, "dosage")}
        self.assertEqual(roles, {"high": "target", "low": "behavior"})
        self.assertEqual(summary["splits"]["dosage"]["groups"]["target"]["action_distribution"],
                         {"100": 1, "300": 1, "500": 1})

    def test_disease_positive_wins_unknown_negative_and_across_admissions(self):
        source = [
            row("a", "positive", renal_disease="", hadm_id="one"),
            row("b", "positive", renal_disease="t", hadm_id="two"),
            row("c", "negative", renal_disease="f"),
            row("d", "negative", renal_disease=False),
            row("e", "unknown", renal_disease=None),
            row("f", "unknown", renal_disease="0"),
        ]
        assignments, summary = build(source, "potassium")
        roles = {r["subject_id"]: r["cohort_role"] for r in selected(assignments, "comorbidity")}
        self.assertEqual(roles, {"positive": "target", "negative": "behavior", "unknown": "excluded"})
        self.assertEqual(summary["splits"]["comorbidity"]["groups"]["target"]["events"], 2)
        self.assertEqual(summary["splits"]["comorbidity"]["groups"]["excluded"]["subjects"], 1)
        self.assertTrue(all(r["cohort_role"] != "excluded" for r in selected(assignments, "dosage")))
        sodium = [row("s", "sodium", cirrhosis=True, renal_disease=False)]
        self.assertEqual(selected(build(sodium, "sodium")[0], "comorbidity")[0]["cohort_role"], "target")

    def test_gender_conflict_or_unknown_excludes_only_gender(self):
        source = [row("a", "conflict", gender="F"), row("b", "conflict", gender="M"),
                  row("c", "unknown", gender="F"), row("d", "unknown", gender=""),
                  row("e", "known", gender="female"), row("f", "known", gender="F")]
        assignments, summary = build(source, "potassium")
        roles = {r["subject_id"]: r["cohort_role"] for r in selected(assignments, "gender")}
        self.assertEqual(roles, {"conflict": "excluded", "unknown": "excluded", "known": "behavior"})
        self.assertEqual(summary["splits"]["gender"]["groups"]["excluded"]["events"], 4)
        self.assertEqual(sum(summary["splits"]["gender"]["excluded_subjects_by_reason"].values()), 2)
        self.assertFalse(any(r["cohort_role"] == "excluded" for r in selected(assignments, "comorbidity")))

    def test_global_fold_matches_v1_across_tasks_and_roles(self):
        outputs = []
        for task, high in (("potassium", 40), ("sodium", 500)):
            source = [row(f"{task}-{i}", f"subject-{i}", high if i % 2 else 0,
                          gender="M" if i % 3 else "F") for i in range(30)]
            assignments, summary = build(source, task)
            outputs.extend(assignments)
            for r in assignments:
                self.assertEqual(r["fold"], subject_fold(r["subject_id"]))
            for split in summary["splits"].values():
                self.assertEqual(split["role_subject_overlap"], 0)
                self.assertEqual(split["train_validation_subject_overlap"], 0)
        train = {r["subject_id"] for r in outputs if r["fold"] == "train"}
        val = {r["subject_id"] for r in outputs if r["fold"] == "validation"}
        self.assertFalse(train & val)

    def test_shuffle_invariance_and_composite_admission_counts(self):
        source = [row("c", "two", 0), row("a", "one", 0), row("b", "one", 40)]
        first = build(source, "potassium")
        self.assertEqual(first, build(list(reversed(source)), "potassium"))
        genders = first[1]["splits"]["gender"]["groups"]["behavior"]
        self.assertEqual(genders["subjects"], 2)
        self.assertEqual(genders["admissions"], 2)

    def test_grouping_never_uses_outcome_values(self):
        source = [row("a", "one", 0, post_lab_value="3.1", reward=0.1),
                  row("b", "one", 40, post_lab_value="8.7", reward=0.9)]
        changed = copy.deepcopy(source)
        for r in changed:
            r["post_lab_value"], r["reward"] = "synthetic-secret-outcome", -999
        self.assertEqual(build(source, "potassium"), build(changed, "potassium"))

    def test_rejects_duplicates_ineligible_and_invalid_action_or_task(self):
        bad_inputs = [
            [row("a", "one"), row("a", "two")],
            [row("a", "one", eligible=False)],
            [row("a", "one", True)], [row("a", "one", 20.0)],
            [row("a", "one", 300)], [row("a", "one", task="sodium")],
        ]
        for source in bad_inputs:
            with self.subTest(case=len(source)):
                with self.assertRaises(ValueError):
                    build(source, "potassium")

    def test_summary_has_no_identity_strings_and_counts_conserve_events(self):
        source = [row("event-private-a", "subject-private-a", 40, hadm_id="admission-private"),
                  row("event-private-b", "subject-private-a", 0, hadm_id="admission-private"),
                  row("event-private-c", "subject-private-b", 20)]
        assignments, summary = build(source, "potassium")
        serialized = json.dumps(summary)
        for value in ("event-private", "subject-private", "admission-private"):
            self.assertNotIn(value, serialized)
        self.assertEqual(summary["assignment_rows"], 3 * summary["input_events"])
        self.assertEqual(summary["role_unit"], "subject")
        for split in summary["splits"].values():
            self.assertEqual(sum(g["events"] for g in split["groups"].values()), len(source))
            self.assertEqual(sum(g["subjects"] for g in split["groups"].values()), 2)
            for g in split["groups"].values():
                self.assertEqual(sum(f["events"] for f in g["folds"].values()), g["events"])
                self.assertEqual(sum(g["action_distribution"].values()), g["events"])

    def test_empty_input_and_invalid_seed(self):
        assignments, summary = build([], "sodium")
        self.assertEqual(assignments, [])
        self.assertEqual(summary["input_subjects"], 0)
        self.assertEqual(summary["assignment_rows"], 0)
        with self.assertRaises(ValueError):
            build([], "sodium", seed="")


if __name__ == "__main__":
    unittest.main()
