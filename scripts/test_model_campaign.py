import copy,hashlib,importlib.util,json,unittest
from pathlib import Path
sp=importlib.util.spec_from_file_location('report',Path(__file__).with_name('enrich-process-audit.py'));m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
ORACLE={'functionalChecks':[{'id':'behavior'}],'deliveryChecks':['delivery'],'independenceConditions':['context']};RAW=json.dumps(ORACLE);OH=hashlib.sha256(RAW.encode()).hexdigest();P={'operations':[{'historical':True}],'frozenCohort':{'attempts':['old']}}
def intake():
 p={'models':['a','b','c'],'taskSHA256':'a'*64,'oracleSHA256':OH,'gatewaySHA256':'b'*64,'runnerSHA256':'c'*64,'initialStateRevision':'seed','agent':'Pi','thinking':'high','nativeBudgetMs':1800000};rows=[]
 for model in p['models']:
  rows.append({'model':model,'freeze':{'taskSHA256':p['taskSHA256'],'nativeBudgetMs':p['nativeBudgetMs'],'gatewaySHA256':p['gatewaySHA256'],'requestId':model,'sessionId':'session-'+model,'baseRef':'workspace-'+model},'qualifiedStart':{'forkCommit':'seed','priorContextFiles':[],'sessionId':'session-'+model,'workspaceRevision':'workspace-'+model},'nativeAcceptance':{'taskSHA256':p['taskSHA256'],'freshParticipantContext':True,'configurationObserved':[{'modelId':model},{'thinkingLevel':'high'}],'newHelpEvents':0,'recipient':{'operationId':'private-'+model,'sessionId':'session-'+model,'requestDigest':'digest-'+model,'baseRef':'workspace-'+model}},'actualRuntimeBinding':{'boundValues':{'--llm-model-id':model,'--timeout-ms':'1800000','--session-id':'session-'+model}},'actualRunnerSHA256':'c'*64})
 return {'schema':'agentlab.model-campaign-intake.v1','publicVersion':'2026-10-25-v8','protocol':p,'oracleRawUTF8':RAW,'attempts':rows}
def reviewed():
 i=intake();r=i['attempts'][0];r['review']={'schema':'agentlab.independent-frozen-task-review.v1','producer':'teacher_evaluator','operationId':'private-a','sessionId':'session-a','requestDigest':'digest-a','taskSHA256':'a'*64,'teacherSolutionHelpEvents':0,'canonicalPublicationQualified':True,'wholeTaskPassed':True,'oracleSHA256':OH,'publishedCheckpoint':'checkpoint','criteria':[{'category':k,'id':v,'passed':True,'proofRefs':[{'path':'private-proof','sha256':'f'*64}]} for k,v in [('functional','behavior'),('delivery','delivery'),('context','context')]]};r['publishedMetrics']={'publishedOriginalQualified':True,'originalOperation':{'operationId':'private-a','sessionId':'session-a','requestId':'a','modelId':'a','checkpoint':'checkpoint','traceExpected':2,'traceVerified':2,'durationMs':1234,'runtimeStatus':'completed'},'maintainedReaderProof':{'kind':'owning_runtime_fact','records':2,'proofSHA256':'d'*64,'toolActivity':{'unknownResultCalls':0,'orphanTerminalCalls':0,'malformedEvents':0,'conflictingCalls':0,'toolCallCount':2,'returnedWithoutError':1,'returnedWithError':1}},'nativeUsageFieldTotals':{'input':4,'output':6,'cacheRead':10,'cacheWrite':0,'reasoning':None,'totalTokens':20}};return i
class Campaign(unittest.TestCase):
 def test_preserve_history_and_pending_no_rate(self):
  o=m.model_campaign(P,intake());self.assertEqual(o['operations'],P['operations']);self.assertEqual(o['frozenCohort'],P['frozenCohort']);self.assertIsNone(o['modelCampaign']['wholeTaskPassRate']);self.assertEqual(o['modelCampaign']['finishedReviews'],0)
 def test_qualified_pass_and_private_bindings_not_exported(self):
  o=m.model_campaign(P,reviewed());self.assertTrue(o['modelCampaign']['attempts'][0]['wholeTaskPassed']);s=json.dumps(o);self.assertNotIn('private-a',s);self.assertNotIn('private-proof',s);self.assertNotIn('session-a',s)
 def test_claim_without_criteria_or_publication_rejected(self):
  for change in [{'criteria':[]},{'canonicalPublicationQualified':False},{'producer':'student'}]:
   i=reviewed();i['attempts'][0]['review'].update(change);self.assertRaises(ValueError,m.model_campaign,P,i)
 def test_original_digest_model_and_checkpoint_fences(self):
  for key in ['operationId','requestDigest']:
   i=reviewed();i['attempts'][0]['review'][key]='other';self.assertRaises(ValueError,m.model_campaign,P,i)
  for key in ['modelId','checkpoint']:
   i=reviewed();i['attempts'][0]['publishedMetrics']['originalOperation'][key]='other';self.assertRaises(ValueError,m.model_campaign,P,i)
 def test_thinking_off_or_later_drift_rejected(self):
  for v in [{'thinkingLevel':'off'},{'modelId':'other'}]:
   i=intake();i['attempts'][0]['nativeAcceptance']['configurationObserved'].append(v);self.assertRaises(ValueError,m.model_campaign,P,i)
 def test_initial_state_and_actual_runtime_mismatch(self):
  i=intake();i['attempts'][0]['qualifiedStart']['priorContextFiles']=['solution'];self.assertRaises(ValueError,m.model_campaign,P,i)
  i=intake();i['attempts'][0]['actualRuntimeBinding']['boundValues']['--timeout-ms']='180000';self.assertRaises(ValueError,m.model_campaign,P,i)
 def test_source_recipient_mismatch_refused(self):
  i=intake();i['attempts'][0]['qualifiedStart']['workspaceRevision']='other';self.assertRaises(ValueError,m.model_campaign,P,i)
 def test_missing_or_duplicate_attempt_rejected(self):
  i=intake();i['attempts'].pop();self.assertRaises(ValueError,m.model_campaign,P,i)
  i=intake();i['attempts'][1]['nativeAcceptance']['recipient']['operationId']='private-a';self.assertRaises(ValueError,m.model_campaign,P,i)
 def test_nullable_usage_and_zero_not_free(self):
  i=reviewed();o=m.model_campaign(P,i);self.assertIsNone(o['modelCampaign']['attempts'][0]['processMetrics']['qualifiedNativeUsageFields']['reasoning'])
  i['attempts'][0]['publishedMetrics']['nativeUsageFieldTotals']={k:0 for k in i['attempts'][0]['publishedMetrics']['nativeUsageFieldTotals']};o=m.model_campaign(P,i);self.assertIsNone(o['modelCampaign']['attempts'][0]['processMetrics']['qualifiedNativeUsageFields']);self.assertIsNone(o['modelCampaign']['attempts'][0]['processMetrics']['billingCost'])
 def test_orphaned_tools_and_partial_fact_rejected(self):
  i=reviewed();i['attempts'][0]['publishedMetrics']['maintainedReaderProof']['toolActivity']['unknownResultCalls']=1;self.assertRaises(ValueError,m.model_campaign,P,i)
 def test_current_pass_not_contradicted_by_old_summary(self):
  o=m.model_campaign(P,reviewed());page=m.render_model_campaign(o,'局部自主纠错已有证据；完整任务的独立完成尚未证明。<section id="frozen-cohort"></section>版本 2026-10-25-v6');self.assertNotIn('独立完成尚未证明',page);self.assertIn('新队列整题验收通过',page);self.assertIn('版本 2026-10-25-v8',page)
 def test_page_escapes_and_assistance_disclosed(self):
  i=reviewed();i['attempts'][0]['publicFindings']=['<script>bad</script>'];i['attempts'][0]['review']['teacherSolutionHelpEvents']=1;i['attempts'][0]['nativeAcceptance']['newHelpEvents']=1;o=m.model_campaign(P,i);page=m.render_model_campaign(o,'<p class="links"></p><section id="frozen-cohort"></section>');self.assertNotIn('<script>',page);self.assertIn('&lt;script&gt;',page);self.assertIn('passed_assisted',json.dumps(o));self.assertIn('有解题帮助',page)
unittest.main()
