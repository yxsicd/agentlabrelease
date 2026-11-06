import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
alignment=load('alignment',ROOT/'examples/benchmark-report/harmony_alignment.py')
swe=load('swe_fixture',ROOT/'tests/test_swe_campaign_report.py')
terminal=load('terminal_fixture',ROOT/'tests/test_terminal_bench_report.py')


class HarmonyAlignmentTest(unittest.TestCase):
    def fixture(self,root):
        s=root/'swe';s.mkdir();t=root/'terminal';t.mkdir();h=root/'harmony';h.mkdir()
        assessment=swe.CampaignTest().assessment(s,True)
        attempt,trial,reference=terminal.TerminalReportTest().fixture(t)
        original=h/'evidence.json';original.write_text('{"observed":true}')
        digest=hashlib.sha256(original.read_bytes()).hexdigest()
        sup={'schema':'agentlab.calendar.assessment-supplement.v1','provenance':{'original':{'path':'evidence.json','sha256':digest}},
             'evaluation':{'verdict':'pending','numericalScore':None},'assistance':{'teacherHelpCount':2},
             'harness':{'classification':'infrastructure failure, not student failure'},'limits':['historical only']}
        (h/'supplement.json').write_text(json.dumps(sup));(h/'marker.json').write_text(json.dumps({'at':'2026-01-01','teacherHelpCount':2}))
        data=gzip.compress(json.dumps({'actor':'system evaluator; not student','remainingCases':[{'pass':True},{'pass':False}]}).encode());(h/'device.json.gz').write_bytes(data)
        (h/'device-summary.json').write_text(json.dumps({'actor':'system evaluator; not student','sha256':hashlib.sha256(data).hexdigest(),'publicAcceptance':'system observed','scopeLimit':'not student'}))
        repeat=root/'repeat';repeat.mkdir();(repeat/'result.json').write_text(json.dumps({'finished_at':'now','n_total_trials':1}))
        q=repeat/'trial';q.mkdir();(q/'result.json').write_text(json.dumps({'id':'new-id','task_checksum':'taskhash','agent_info':{'name':'oracle'},'verifier_result':{'rewards':{'reward':1.0}},'exception_info':None}))
        return [assessment],attempt,trial,reference,h/'supplement.json',h/'marker.json',h/'device-summary.json',h/'device.json.gz',repeat

    def test_historical_help_and_system_device_are_not_student_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.fixture(Path(tmp));d=alignment.build(*args)
            self.assertEqual(d['mature']['terminal']['referenceRuns'],2);self.assertEqual(d['mature']['terminal']['referencePasses'],2)
            self.assertEqual(d['harmonyHistorical']['teacherHelpRecorded'],2)
            self.assertEqual(d['harmonyHistorical']['verdict'],'pending');self.assertIsNone(d['harmonyHistorical']['numericalScore'])
            self.assertEqual(d['harmonyHistorical']['systemEvaluator']['actor'],'system evaluator; not student')
            self.assertEqual(d['harmonyHistorical']['systemEvaluator']['rawRemainingCaseCounts'],{'observed':2,'passed':1,'failed':1,'unknown':0})
            self.assertEqual(next(x['status'] for x in d['gaps'] if x['id']=='checkpoint-fork'),'unqualified')

    def test_changed_historical_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.fixture(Path(tmp));(args[4].parent/'evidence.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'missing or changed'):alignment.build(*args)

    def test_wrong_repeated_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.fixture(Path(tmp));p=args[-1]/'trial/result.json';d=json.loads(p.read_text());d['task_checksum']='different';p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,'identity differs'):alignment.build(*args)

    def test_negative_control_is_separate_from_student_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);args=self.fixture(root);job=root/'nop';job.mkdir()
            (job/'result.json').write_text(json.dumps({'finished_at':'now','n_total_trials':1}))
            trial=job/'trial';trial.mkdir();p=trial/'result.json'
            p.write_text(json.dumps({'id':'negative-id','task_checksum':'taskhash','agent_info':{'name':'nop'},
                                     'verifier_result':{'rewards':{'reward':0.0}},'exception_info':None}))
            result=alignment.build(*args,nop_job=job)
            self.assertTrue(result['mature']['terminal']['negativeControl']['passed'])
            self.assertTrue(result['mature']['terminal']['resolved'])
            data=json.loads(p.read_text());data['verifier_result']['rewards']['reward']=1.0;p.write_text(json.dumps(data))
            self.assertFalse(alignment.build(*args,nop_job=job)['mature']['terminal']['negativeControl']['passed'])
            data['verifier_result']['rewards']['reward']=False;p.write_text(json.dumps(data))
            self.assertFalse(alignment.build(*args,nop_job=job)['mature']['terminal']['negativeControl']['passed'])

    def test_live_timeout_is_not_a_student_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);args=self.fixture(root);host=root/'host.json';device=root/'device.json'
            host.write_text(json.dumps({'schema':'agentlab.harmony-live-readback.v1','targetPeerId':'peer','routeDecision':'peer_direct'}))
            device.write_text(json.dumps({'schema':'agentlab.harmony-device-readback.v1','targetPeerId':'peer','routeDecision':'peer_direct',
                                          'versionRead':'timed out','deviceReady':None,'readinessQualification':'not established'}))
            result=alignment.build(*args,live_host=host,live_device=device)
            self.assertIsNone(result['harmonyLive']['deviceReady'])
            self.assertIsNone(result['harmonyHistorical']['numericalScore'])
            data=json.loads(device.read_text());data['targetPeerId']='other';device.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'identity or route differs'):
                alignment.build(*args,live_host=host,live_device=device)


if __name__=='__main__':unittest.main()
