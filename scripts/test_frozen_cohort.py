import copy,importlib.util,json,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('report',str(Path(__file__).with_name('enrich-process-audit.py')));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
P={'schema':'agentlab.public-evaluation.v4','agentReport':{},'provenance':{},'operations':[{'historical':True}]*31,'runRecords':[{'old':True}]}
protocol={'taskSHA256':'a'*64,'initialStateRevision':'seed','agent':'Pi1.4.0','model':'glm-5.3-flash','thinking':'high','nativeBudgetMs':1800000,'gatewaySHA256':'b'*64,'oracleSHA256':'c'*64,'secret':'neverexport'}
def row(label):
 return {'label':label,'status':'running','freeze':{'taskSHA256':'a'*64,'nativeBudgetMs':1800000,'gatewaySHA256':'b'*64},'qualifiedStart':{'forkCommit':'seed','priorContextFiles':[]},'nativeAcceptance':{'taskSHA256':'a'*64,'configurationObserved':[{'modelId':'glm-5.3-flash'},{'thinkingLevel':'high'}],'freshParticipantContext':True,'newHelpEvents':0,'recipient':{'operationId':'private-operation','sessionId':'private-session','requestDigest':'private-digest'}}}
I={'schema':'agentlab.frozen-review-intake.v1','protocol':protocol,'attempts':[row('A2'),row('B2')]}
review={'schema':'agentlab.independent-frozen-task-review.v1','producer':'teacher_evaluator','taskSHA256':'a'*64,'teacherSolutionHelpEvents':0,'wholeTaskPassed':False,'canonicalPublished':False,'wholeTaskVerdict':'pending','originalOperationId':'private-operation','sessionId':'private-session','requestDigest':'private-digest','functionalChecks':[{'id':'restart','status':'incomplete','finding':'numeric process identity not captured','evidence':[{'toolCallId':'private-tool'}]}]}
class FrozenBoundaries(unittest.TestCase):
 def test_old_population_and_null_rate(self):
  out=m.frozen_cohort(P,I);self.assertEqual(out['operations'],P['operations']);self.assertEqual(out['runRecords'],P['runRecords']);self.assertIsNone(out['frozenCohort']['wholeTaskPassRate']);self.assertFalse(out['frozenCohort']['statisticalStabilityClaim']);self.assertEqual(P['schema'],'agentlab.public-evaluation.v4')
 def test_review_refs_and_extra_protocol_not_exported(self):
  i=copy.deepcopy(I);i['attempts'][0]['review']=review;t=json.dumps(m.frozen_cohort(P,i)['frozenCohort']);self.assertNotIn('private-operation',t);self.assertNotIn('private-tool',t);self.assertNotIn('neverexport',t);self.assertIn('numeric process identity not captured',t)
 def test_unqualified_pass_refused(self):
  i=copy.deepcopy(I);i['attempts'][0]['review']={**review,'wholeTaskPassed':True};self.assertRaises(ValueError,m.frozen_cohort,P,i)
 def test_mismatch_refused(self):
  for target,key,value in [('freeze','taskSHA256','f'*64),('qualifiedStart','forkCommit','other'),('freeze','nativeBudgetMs',180000),('freeze','gatewaySHA256','other'),('qualifiedStart','priorContextFiles',['prior-solution'])]:
   with self.subTest(key=key):
    i=copy.deepcopy(I);i['attempts'][0][target][key]=value;self.assertRaises(ValueError,m.frozen_cohort,P,i)
 def test_model_thinking_mismatch_refused(self):
  for change in [{'modelId':'other'},{'thinkingLevel':'off'}]:
   i=copy.deepcopy(I);i['attempts'][0]['nativeAcceptance']['configurationObserved']=[change];self.assertRaises(ValueError,m.frozen_cohort,P,i)
 def test_student_or_wrong_operation_rejected(self):
  for change in [{'producer':'student'},{'originalOperationId':'other'},{'teacherSolutionHelpEvents':1}]:
   i=copy.deepcopy(I);i['attempts'][0]['review']={**review,**change};self.assertRaises(ValueError,m.frozen_cohort,P,i)
 def test_both_attempts_retained(self):
  i=copy.deepcopy(I);i['attempts']=i['attempts'][:1];self.assertRaises(ValueError,m.frozen_cohort,P,i)
 def test_page_escapes_review(self):
  i=copy.deepcopy(I);i['attempts'][0]['review']=copy.deepcopy(review);i['attempts'][0]['review']['functionalChecks'][0]['finding']='<script>alert(1)</script>';page=m.render_frozen(m.frozen_cohort(P,i),'<p class="links"></p><section id="process"></section>');self.assertNotIn('<script>',page);self.assertIn('&lt;script&gt;',page)
 def metric_input(self):
  i=copy.deepcopy(I);r=i['attempts'][0];r['review']={**review,'canonicalPublished':True,'publishedCheckpoint':'cp'};r['freeze']['requestId']='request';r['publishedMetrics']={'publishedOriginalQualified':True,'originalOperation':{'operationId':'private-operation','sessionId':'private-session','requestId':'request','checkpoint':'cp','traceExpected':2,'traceVerified':2,'durationMs':100,'runtimeStatus':'failed'},'maintainedReaderProof':{'kind':'owning_runtime_fact','records':2,'proofSHA256':'d'*64,'toolActivity':{'unknownResultCalls':0,'orphanTerminalCalls':0,'malformedEvents':0,'conflictingCalls':0,'toolCallCount':1,'returnedWithoutError':1,'returnedWithError':0}},'nativeUsageFieldTotals':{'input':3,'output':5,'reasoning':2,'cacheRead':10,'cacheWrite':0,'totalTokens':18}};return i
 def test_metrics_are_not_rates_or_billing(self):
  out=m.frozen_cohort(P,self.metric_input());r=out['frozenCohort']['attempts'][0]['processMetrics'];self.assertEqual(r['nativeUsageFields']['totalTokens'],18);self.assertEqual(r['nativeUsageFields']['reasoning'],2);self.assertIsNone(r['billingCost']);self.assertIsNone(r['globalUsefulCallRate']);self.assertNotIn('private-operation',json.dumps(out))
 def test_metric_wrong_binding_and_unpublished_refused(self):
  i=self.metric_input();i['attempts'][0]['publishedMetrics']['originalOperation']['checkpoint']='other';self.assertRaises(ValueError,m.frozen_cohort,P,i)
  i=self.metric_input();i['attempts'][0]['review']['canonicalPublished']=False;self.assertRaises(ValueError,m.frozen_cohort,P,i)
 def test_metric_incomplete_trace_refused(self):
  i=self.metric_input();i['attempts'][0]['publishedMetrics']['maintainedReaderProof']['toolActivity']['unknownResultCalls']=1;self.assertRaises(ValueError,m.frozen_cohort,P,i)
 def test_current_summary_scope_and_public_version(self):
  page='<section id="process"></section><p>没有同配置、同起点、无额外帮助的整题独立重复，不能估计整题通过率、pass@k/pass^k或置信区间。</p><p>本公开视图未核定完整OS、SDK、模拟器和工具版本</p>'
  out=m.render_frozen(m.frozen_cohort(P,I),page);self.assertNotIn('没有同配置',out);self.assertIn('A2/B2已完成',out);self.assertIn('构建125',out)
  spec=importlib.util.spec_from_file_location('scan',str(Path(__file__).with_name('export-public-evaluation.py')));scan=importlib.util.module_from_spec(spec);spec.loader.exec_module(scan);scan.scan_public(out)
unittest.main()
