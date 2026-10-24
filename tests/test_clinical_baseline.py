import csv
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

AVAILABLE=all(importlib.util.find_spec(name) is not None for name in ('numpy','scipy','sklearn'))
if AVAILABLE:
    import numpy as np
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    import run_clinical_baseline as baseline


@unittest.skipUnless(AVAILABLE,'Optional G3 numerical dependencies not installed')
class ClinicalBaselineTests(unittest.TestCase):
    def test_majority_accuracy_does_not_hide_positive_action_failure(self):
        y=np.array([0,0,20,40]);p=np.zeros((4,4));p[:,0]=1
        report=baseline.classification_report(y,p,np.array([0,0,0,20]),'potassium')
        self.assertEqual(report['accuracy'],.5)
        self.assertEqual(report['always_zero_accuracy'],.5)
        self.assertEqual(report['recall_by_action']['20'],0)
        self.assertEqual(report['recall_by_action']['40'],0)
        self.assertIsNone(report['recall_by_action']['10'])
        self.assertEqual(report['absent_training_actions'],[10,40])
        self.assertEqual(report['confusion_matrix'],[[2,0,0,0],[0,0,0,0],[1,0,0,0],[1,0,0,0]])

    def test_empty_validation_has_no_accuracy(self):
        report=baseline.classification_report(np.array([]),np.empty((0,6)),np.array([0]),'sodium')
        self.assertEqual(report['status'],'not_estimable')
        self.assertIsNone(report['accuracy'])
        self.assertEqual(report['validation_events'],0)

    def test_invalid_probability_and_unknown_action_rejected(self):
        for p in [np.array([[.5,.5,.5,.5]]),np.array([[np.nan,0,0,1]]),np.array([[-1,0,0,2]])]:
            with self.assertRaises(ValueError):baseline.classification_report(np.array([0]),p,np.array([0]),'potassium')
        with self.assertRaises(ValueError):
            baseline.classification_report(np.array([30]),np.array([[1,0,0,0]]),np.array([0]),'potassium')

    def test_point_dm_uses_raw_context_separately_and_does_not_clip(self):
        class Data:
            task='potassium'
            features=np.array([[3.],[7.],[11.]])
            actions=np.array([0,0,40])
            rewards=np.array([.9,.3,.5])
            subject_ids=np.array([1,2,3]);hadm_ids=np.array([11,22,33])
            event_ids=('synthetic-a','synthetic-b','synthetic-c')
        class Policy:
            status='complete'
            def to_dict(self):return {'converged':True}
            def predict_proba(self,X):
                np.testing.assert_equal(X,[[7.],[11.]])
                return np.tile([.25,0,0,.75],(len(X),1))
        class Reward:
            status='complete'
            def predict_action_values(self,X):
                np.testing.assert_equal(X,[[7.],[11.]])
                return np.tile([-.2,.2,.6,1.4],(len(X),1))
        with tempfile.TemporaryDirectory() as tmp:
            result=baseline.point_dm(Policy(),Reward(),Data(),np.array([False,True,True]),np.array([True,False,False]),Path(tmp))
            self.assertAlmostEqual(result['dm'],1.0)
            self.assertAlmostEqual(result['observed_reference'],.4)
            self.assertAlmostEqual(result['signed_difference'],.6)
            self.assertAlmostEqual(result['target_probability_mass_on_behavior_unseen_actions'],.75)
            self.assertEqual(result['ols_action_predictions_outside_unit_interval'],4)
            self.assertIsNone(result['rmse']);self.assertIsNone(result['standard_error'])
            with (Path(tmp)/'dm-evaluation.csv').open() as f:rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),2)
            self.assertEqual(float(rows[0]['reward_40']),1.4)

    def test_empty_target_and_nonconverged_policy_are_not_estimable(self):
        class Data:
            task='potassium';subject_ids=np.array([1]);features=np.array([[0.]])
            actions=np.array([0]);rewards=np.array([1.])
        class Policy:
            status='complete'
            def to_dict(self):return {'converged':False}
        class Reward:status='complete'
        with tempfile.TemporaryDirectory() as tmp:
            for mask,reason in [(np.array([False]),'empty_target_validation'),(np.array([True]),'dependent_model_unavailable_or_not_converged')]:
                result=baseline.point_dm(Policy(),Reward(),Data(),mask,np.array([True]),Path(tmp))
                self.assertEqual(result['status'],'not_estimable');self.assertEqual(result['reason'],reason)
                self.assertIsNone(result['dm'])

    def test_recorded_parameter_change_cannot_silently_run_different_model(self):
        import tomllib
        rules=tomllib.loads((Path(__file__).resolve().parents[1]/'config/clinical-baseline.toml').read_text())
        baseline.validate_protocol(rules)
        rules['policy']['C']=3
        with self.assertRaises(ValueError):baseline.validate_protocol(rules)

    def test_nested_nonconvergence_is_respected_and_constant_needs_no_solver(self):
        class Model:
            status='complete'
            def __init__(self,state):self.state=state
            def to_dict(self):return self.state
        self.assertFalse(baseline.usable_policy(Model({'metadata':{'converged':False},'link':'softmax'})))
        self.assertTrue(baseline.usable_policy(Model({'metadata':{'converged':None},'link':'constant'})))


if __name__=='__main__':unittest.main()
