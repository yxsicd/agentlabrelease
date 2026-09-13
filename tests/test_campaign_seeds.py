import importlib.util
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]

def load(path):
    spec=importlib.util.spec_from_file_location(path.stem,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class CampaignTests(unittest.TestCase):
    def test_swe_catalog_has_multiple_repositories_and_bound_baselines(self):
        catalog=json.loads((ROOT/'examples/swe-bench/catalog.json').read_text())
        self.assertEqual(len(catalog['cases']),4)
        self.assertEqual(len({r['repo'] for r in catalog['cases']}),3)
        self.assertTrue(all(len(r['baseCommit'])==40 and len(r['sourceRecordSha256'])==64 for r in catalog['cases']))

    def test_harmony_demands_reject_marker_only_edits_and_feature_loss(self):
        m=load(ROOT/'examples/harmony-build/scenarios.py')
        for name in ['counter','form']:
            base=m.render(name,0,'marker')
            self.assertFalse(m.verify(name,1,base)['passed'])
            self.assertTrue(m.verify(name,1,m.render(name,1,'marker'))['passed'])
            self.assertFalse(m.verify(name,2,m.render(name,1,'marker'))['passed'])
            self.assertTrue(m.verify(name,2,m.render(name,2,'marker'))['passed'])
