import importlib.util,copy,unittest
from pathlib import Path
script=Path(__file__).with_name('build-difficulty-report.py')
if not script.exists():script=Path('/tmp/al07-558-build.py')
spec=importlib.util.spec_from_file_location('difficulty_builder',script);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Boundaries(unittest.TestCase):
 def record(self):return {'mode':'independent_task','assistanceCondition':'independently_audited_no_help','frozenComparisonInputs':{k:'synthetic-evidence-binding' for k in m.REQUIRED}}
 def review(self):return {'rows':[{'state':'assisted_progress','exposure':'reached','runs':[14],'helpEvents':['H04'],'confidence':'case_observation'}]}
 def validate(self,r):return m.validate_review(r,{14},{'H04'},{'performance'})
 def test_missing_budget_rejects_ready(self):
  r=self.record();r['frozenComparisonInputs']['budgetManifest']=None;self.assertFalse(m.readiness(r)['reportingMetadataReady'])
 def test_complete_metadata_not_enough_for_exploration(self):
  r=self.record();r['mode']='assisted_exploration';self.assertFalse(m.readiness(r)['reportingMetadataReady'])
 def test_inherited_assistance_blocks_independent_queue(self):
  r=self.record();r['assistanceCondition']='mixed_or_inherited_context';self.assertFalse(m.readiness(r)['reportingMetadataReady'])
 def test_declared_complete_is_only_metadata(self):
  self.assertTrue(m.readiness(self.record())['reportingMetadataReady']);self.assertIn('不授予执行权限',m.readiness(self.record())['meaning'])
 def test_missing_run_evidence_rejects(self):
  r=self.review();r['rows'][0]['runs']=[99]
  with self.assertRaises(ValueError):self.validate(r)
 def test_local_observation_cannot_claim_whole_task(self):
  r=self.review();r['rows'][0]['wholeTaskIndependentPass']=True
  with self.assertRaises(ValueError):self.validate(r)
 def test_assistance_cannot_be_erased(self):
  r=self.review();r['rows'][0]['helpEvents']=[]
  with self.assertRaises(ValueError):self.validate(r)
 def test_unknown_measurement_requires_scope_evidence(self):
  r=self.review();r['rows'][0].update(state='not_assessed',dimensionEvidence='missing',confidence='not_assessed')
  with self.assertRaises(ValueError):self.validate(r)
 def test_valid_review_preserves_hypothesis(self):
  r=self.review();r['rows'][0]['confidence']='hypothesis';self.validate(r);self.assertEqual(r['rows'][0]['confidence'],'hypothesis')
if __name__=='__main__':unittest.main()
