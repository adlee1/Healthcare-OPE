"""Synthetic checks for clinical input/outcome separation and exact identity joins."""
import copy
from pathlib import Path
import unittest

from april_repro.decision_features import (
    FEATURES, IDENTITY, OUTCOMES, assemble_features, render_decision_query,
)


def fixture():
    event = "a" * 64
    decision = {name: "" for name in OUTCOMES}
    decision.update(event_id=event, subject_id="1001", hadm_id="2001",
                    anchor_time="2000-01-02 12:00:00", task="potassium",
                    action="20", post_lab_value="4.2", pre_lab_value="3.1")
    identity = dict(event_id=event, subject_id="1001", hadm_id="2001",
                    decision_time="2000-01-02 12:00:00")
    context = {**identity, **{name: "" for name in FEATURES[:10]},
               "age": "52", "gender": "F", "creatinine": "1.2",
               "decision_key_valid": "t", "all_vital_ids_verified": "t",
               "creatinine_id_verified": "t", "dynamic_evidence": "{}",
               "static_evidence": "{}"}
    medication = {**identity, **{name: "0" for name in FEATURES[10:]}}
    group = {**identity, "renal_disease": "t", "cirrhosis": "f"}
    return [decision], [context], [medication], [group]


class DecisionFeatureTests(unittest.TestCase):
    def test_labels_actions_and_diagnoses_never_enter_feature_schema(self):
        features, outcomes, groups, summary = assemble_features(*fixture())
        self.assertEqual(tuple(features[0]), (*IDENTITY, *FEATURES))
        self.assertEqual(outcomes[0]["post_lab_value"], "4.2")
        self.assertEqual(groups[0]["renal_disease"], "t")
        self.assertNotIn("action", features[0])
        self.assertNotIn("post_lab_value", features[0])
        self.assertNotIn("renal_disease", features[0])
        self.assertFalse(summary["imputation_fitted"])

    def test_missing_values_preserved_and_counted(self):
        features, _, _, summary = assemble_features(*fixture())
        self.assertEqual(features[0]["heart_rate"], "")
        self.assertEqual(summary["coverage"]["heart_rate"]["missing"], 1)
        self.assertEqual(summary["all_features_observed_events"], 0)

    def test_bad_numeric_features_rejected(self):
        for name, value in (("creatinine", "NaN"), ("age", "-1"),
                            ("gender", "unknown"), (FEATURES[-1], "2")):
            rows = fixture()
            rows[2 if name in FEATURES[10:] else 1][0][name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                assemble_features(*rows)

    def test_missing_duplicate_and_wrong_identity_are_not_inner_joined_away(self):
        for source in (1, 2, 3):
            for mutation in ("missing", "duplicate", "patient", "time"):
                rows = list(fixture())
                if mutation == "missing":
                    rows[source] = []
                elif mutation == "duplicate":
                    rows[source] += copy.deepcopy(rows[source])
                else:
                    field, value = ("subject_id", "1002") if mutation == "patient" else (
                        "decision_time", "2000-01-02 13:00:00")
                    rows[source][0][field] = value
                with self.subTest(source=source, mutation=mutation), self.assertRaises(ValueError):
                    assemble_features(*rows)

    def test_timestamp_formatting_equivalence(self):
        rows = fixture()
        rows[1][0]["decision_time"] = "2000-01-02 12:00"
        self.assertEqual(len(assemble_features(*rows)[0]), 1)

    def test_future_storetime_and_same_day_omr_are_rejected(self):
        for column, evidence in (
            ("dynamic_evidence", '{"creatinine":{"status":"available",'
             '"charttime":"2000-01-02 11:00","latest_storetime":"2000-01-02 13:00"}}'),
            ("static_evidence", '{"weight_kg":{"status":"available_date_only_no_storetime",'
             '"chartdate":"2000-01-02"}}'),
        ):
            rows = fixture()
            rows[1][0][column] = evidence
            with self.subTest(column=column), self.assertRaises(ValueError):
                assemble_features(*rows)

    def test_unverified_dictionary_cannot_be_silent_all_missing_feature(self):
        rows = fixture()
        rows[1][0]["all_vital_ids_verified"] = "f"
        with self.assertRaises(ValueError):
            assemble_features(*rows)

    def test_render_uses_validated_identity_only(self):
        rows = fixture()[0]
        sql = render_decision_query("VALUES __DECISION_KEYS__", rows)
        self.assertIn("'2000-01-02 12:00:00'::timestamp", sql)
        self.assertNotIn("4.2", sql)
        for field, value in (("subject_id", "1);DROP TABLE x;--"),
                             ("event_id", "'bad'"), ("hadm_id", "2147483648"),
                             ("anchor_time", "2000-01-01T12:00:00+08:00")):
            candidate = copy.deepcopy(rows)
            candidate[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                render_decision_query("VALUES __DECISION_KEYS__", candidate)

    def test_render_rejects_repeated_events_or_unbounded_inputs(self):
        rows = fixture()[0]
        for candidate in ([], rows * 2, rows * 5001):
            with self.assertRaises(ValueError):
                render_decision_query("VALUES __DECISION_KEYS__", candidate)

    def test_real_query_templates_render_without_unresolved_tokens(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("307_decision_context.sql", "308_decision_medications.sql",
                     "309_decision_groups.sql"):
            with self.subTest(template=name):
                sql = render_decision_query((root / "sql/cohort" / name).read_text(), fixture()[0])
                self.assertNotIn("__DECISION_KEYS__", sql)
                self.assertIn("'2000-01-02 12:00:00'::timestamp", sql)


if __name__ == "__main__":
    unittest.main()
