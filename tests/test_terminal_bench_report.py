import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('terminal_report',ROOT/'examples/terminal-bench/report.py')
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)


class TerminalReportTest(unittest.TestCase):
    def fixture(self, root):
        attempt=root/'attempt';trial=root/'trial';reference=root/'reference'
        def put(path,obj):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj)+'\n')
        put(attempt/'intent.json',{'benchmark':'terminal-bench-2','task':'fix-git','taskCommit':'abc','model':'fixture','teacherHelp':0})
        put(attempt/'participant-outcome.json',{'error':None})
        put(attempt/'container-binding.json',{'imageId':'sha256:image'})
        put(attempt/'evidence/usage-observation.json',{'inputOutputComplete':True})
        put(attempt/'evidence/participant.json',{'model':'fixture'})
        put(attempt/'evidence/terminal-task-lifecycle.json',{'participantExitStatus':'Submitted','toolErrors':1})
        events=[{'type':'tool_execution_end','result':{'returncode':0},'action':{'command':'git reflog'}},
                {'type':'tool_execution_end','result':{'returncode':0,'output':'CONFLICT (content)'},'action':{'command':'git merge branch; git status'}},
                {'type':'tool_execution_end','exceptionClass':'Submitted','action':{'command':'submit'}}]
        (attempt/'evidence/terminal-task-events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
        put(trial/'result.json',{'task_name':'terminal-bench/fix-git','task_checksum':'taskhash','agent_info':{'model_info':{'name':'fixture'}},'exception_info':None,'verifier_result':{'rewards':{'reward':1.0}}})
        put(trial/'verifier/ctrf.json',{'results':{'summary':{'tests':2,'passed':2,'failed':0,'skipped':0}}})
        put(reference/'result.json',{'result':'reference'})
        digest=hashlib.sha256((reference/'result.json').read_bytes()).hexdigest()
        put(reference/'reference-qualification.json',{'benchmark':'terminal-bench-2','task':'fix-git','qualification':'reference_passed_once','oracle':{'verifierReward':1.0,'exceptions':0},
            'taskChecksum':'taskhash','image':{'id':'sha256:image'},'sourceCommit':'abc','evidence':{'result.json':digest}})
        return attempt,trial,reference

    def test_submission_is_success_not_tool_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=self.fixture(Path(tmp));result=report.build(*args)
            self.assertEqual(result['qualification'],'qualified');self.assertIs(result['resolved'],True)
            self.assertEqual(result['execution']['toolCalls'],3);self.assertEqual(result['execution']['toolErrors'],0)
            self.assertEqual(result['execution']['originalLifecycleToolErrors'],1)
            self.assertTrue(result['execution']['observedCommands']['inspectedReflog'])
            self.assertTrue(result['execution']['observedCommands']['mergeConflictOutputObserved'])

    def test_incomplete_capture_does_not_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,t,r=self.fixture(Path(tmp));(a/'evidence/usage-observation.json').write_text('{"inputOutputComplete":false}')
            result=report.build(a,t,r);self.assertEqual(result['qualification'],'unscored');self.assertIsNone(result['resolved'])

    def test_reference_mismatch_or_changed_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,t,r=self.fixture(Path(tmp));(r/'result.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'digest mismatch'):report.build(a,t,r)
        with tempfile.TemporaryDirectory() as tmp:
            a,t,r=self.fixture(Path(tmp));(a/'container-binding.json').write_text('{"imageId":"different"}')
            with self.assertRaisesRegex(ValueError,'identity mismatch'):report.build(a,t,r)

    def test_contradictory_verifier_summary_is_unscored(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,t,r=self.fixture(Path(tmp))
            (t/'verifier/ctrf.json').write_text('{"results":{"summary":{"tests":2,"passed":1,"failed":1}}}')
            result=report.build(a,t,r)
            self.assertEqual(result['qualification'],'unscored');self.assertIsNone(result['resolved'])


if __name__=='__main__': unittest.main()
