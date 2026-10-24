"""Synthetic integrity tests for the portable adapter; no MIMIC records."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('portable_runner', Path(__file__).resolve().parents[1] / 'run_reproduction.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class AdapterIntegrityTests(unittest.TestCase):
    def test_relative_paths_block_traversal_absolute_and_external_symlink(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            root = Path(a)
            for value in ('../outside', '/etc/passwd'):
                with self.assertRaises(ValueError): r.inside(root, value)
            (root/'alias').symlink_to(Path(b), target_is_directory=True)
            with self.assertRaises(ValueError): r.inside(root, 'alias/anything')

    def test_committed_pair_rejects_wrong_run_identity(self):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t)/'draw-000'; identity={'case':'synthetic','draw_id':0,'seed':'fixed','run_plan_sha256':'a'*64}
            r.commit_fit(folder, {'value':1}, {'coef':[0.1]}, identity)
            self.assertEqual(r.read_fit(folder,identity)[0],{'value':1})
            with self.assertRaises(ValueError): r.read_fit(folder,dict(identity,draw_id=1))
            with self.assertRaises(ValueError): r.read_fit(folder,dict(identity,run_plan_sha256='b'*64))

    def test_committed_result_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t)/'draw-000';identity={'case':'synthetic'}
            r.commit_fit(folder,{'value':1},{'coef':[0.1]},identity)
            (folder/'result.json').write_text('{"value":2}')
            with self.assertRaises(ValueError):r.read_fit(folder,identity)

    def test_committed_model_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t)/'draw-000';identity={'case':'synthetic'}
            r.commit_fit(folder,{'value':1},{'coef':[0.1]},identity)
            (folder/'models.json').write_text('{"coef":[0.2]}')
            with self.assertRaises(ValueError):r.read_fit(folder,identity)

    def test_committed_draw_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t)/'draw-000'
            r.commit_fit(folder,{'value':1},{'coef':[0.1]}, {})
            with self.assertRaises(ValueError):r.commit_fit(folder,{'value':2},{'coef':[0.1]}, {})

    def test_selection_rejects_repeated_and_out_of_range_ids(self):
        for text in ('0,0','-1','500'):
            with self.assertRaises(ValueError):r.numbers(text,range(500))
        self.assertEqual(r.numbers('7,0',range(500)),[0,7])

    def test_numerical_comparison_preserves_declared_tolerance(self):
        r.compare_tree({'coef':[1.0+1e-13]}, {'coef':[1.0]})
        with self.assertRaises(ValueError):r.compare_tree({'coef':[1.0+1e-8]}, {'coef':[1.0]})
        with self.assertRaises(ValueError):r.compare_tree({'task':'sodium'}, {'task':'potassium'})


if __name__=='__main__':unittest.main()
