import copy,importlib.util,json,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('b',str(Path(__file__).with_name('enrich-process-audit.py')));b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
P={'cases':[{'operations':[{'operationId':str(i),'phase':'stage','durationMs':100,'traceEvidence':{'failureAttribution':{'kind':'explicit_runtime_timeout','studentCapabilityFailureEstablished':False}}} if i==12 else {'operationId':str(i),'phase':'stage','durationMs':100} for i in range(31)],'reviewedLearning':{'actions':[{'id':'a'+str(i),'operationId':str(i),'kind':['preparation','validation_progress','informative_failure','state_recovery','validation_progress','repeated_check_no_new_requirement','goal_action','validation_progress'][i],'finding':'review','reportedIsError':False,'requestSHA256':'a'*64,'resultSHA256':'b'*64,**({'recoveryOf':'a2'} if i==3 else {})} for i in range(8)]}}]}
U={'schema':'agentlab.public-evaluation.v3','operations':[{'phase':'stage','durationMs':100,'runtimeStatus':'timeout','outcome':'partial'} for i in range(31)],'runRecords':[],'agentReport':{},'provenance':{'privateReportSHA256':b.hashlib.sha256(json.dumps(P,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()}}
class Boundaries(unittest.TestCase):
 def test_population_and_grades_preserved(self):
  r=b.project(P,U);self.assertEqual(r['operations'],U['operations']);self.assertEqual(r['runRecords'],U['runRecords'])
 def test_no_global_rate_from_selected_sample(self):
  a=b.project(P,U)['processAudit'];self.assertIsNone(a['globalUsefulCallRate']);self.assertEqual(a['unreviewedCalls'],365)
 def test_error_and_recovery_preserved(self):
  rows=b.project(P,U)['processAudit']['rows'];self.assertFalse(rows[2]['reportedIsError']);self.assertEqual(rows[2]['kind'],'informative_failure');self.assertEqual(rows[3]['recoveryOf'],'A03')
 def test_missing_attribution_unknown(self):
  j=b.project(P,U)['processAudit']['judgments'];self.assertIsNone(j[0]['recordedFailureKind']);self.assertIsNone(j[0]['studentCapabilityFailureEstablished']);self.assertIs(j[12]['studentCapabilityFailureEstablished'],False)
 def test_integrity_not_invented(self):
  a=b.project(P,U)['processAudit'];self.assertIsNone(a['integrity']['misconductVerdict']);self.assertIsNone(a['adjustedPassRate'])
 def test_mismatched_evidence_rejected(self):
  p=copy.deepcopy(P);p['new']='changed';self.assertRaises(ValueError,b.project,p,U)
 def test_not_mutating_source(self):
  p=copy.deepcopy(P);u=copy.deepcopy(U);b.project(p,u);self.assertEqual(p,P);self.assertEqual(u,U)
 def test_public_allowlist(self):
  a=b.project(P,U)['processAudit'];t=json.dumps(a);self.assertNotIn('operationId',t);self.assertNotIn('toolCallId',t);self.assertTrue(all('sequence' not in x for x in a['rows']))
unittest.main()
