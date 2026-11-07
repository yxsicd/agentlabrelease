import importlib.util
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('completion', Path(__file__).parents[1] / 'examples/swe-bench/finalize.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ROOT = Path(__file__).parents[1]
report_fixture_spec = importlib.util.spec_from_file_location('report_fixture', ROOT / 'tests/test_swe_report.py')
report_fixture = importlib.util.module_from_spec(report_fixture_spec)
report_fixture_spec.loader.exec_module(report_fixture)


class CompletionTest(unittest.TestCase):
    def test_harmony_summary_is_diagnostic_and_bound_to_scenario(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / 'real-agent/evidence'
            evidence.mkdir(parents=True)
            (evidence / 'summary.json').write_text(json.dumps({
                'schema': 'agentlab.harmony_build_demo.v1', 'ok': True, 'evaluationMode': 'diagnostic'}))
            (evidence / 'scenario.json').write_text(json.dumps({
                'schema': 'agentlab.harmony_scenario.v1', 'scenario': 'counter'}))
            result = module.make_status(root, 'failure', '123', 'counter', False, kind='harmony')
            self.assertEqual(result['diagnosticSummary'], 'available')
            self.assertIs(result['diagnosticOutcome'], True)
            self.assertEqual(result['studentAssessment'], 'not_generated')
            self.assertEqual(result['captureRecovery'], 'failed')
            self.assertEqual(result['formalAttemptCapture'], 'not_qualified')
            result = module.make_status(root, 'skipped', '123', 'form', False, kind='harmony')
            self.assertEqual(result['diagnosticSummary'], 'task_mismatch')
            self.assertNotIn('diagnosticOutcome', result)

    def test_system_reports_link_and_preserve_student_result_after_storage_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / 'real-agent/evidence'
            report_fixture.SweReportTest().make_evidence(evidence)
            subprocess.run([sys.executable, str(ROOT / 'examples/swe-bench/report.py'),
                            '--evidence', str(evidence), '--output', str(evidence / 'report'),
                            '--completion-link', '../../../final-report/index.html'], check=True)
            subprocess.run([sys.executable, str(ROOT / 'examples/swe-bench/finalize.py'),
                            '--root', str(root), '--run-id', '123', '--task', 'case',
                            '--persistence-outcome', 'failure'], check=True)
            assessment = json.loads((evidence / 'report/assessment.json').read_text())
            completion = json.loads((root / 'final-report/completion.json').read_text())
            self.assertIs(assessment['resolved'], True)
            self.assertEqual(completion['captureRecovery'], 'failed')
            self.assertEqual(completion['studentAssessment'], 'available')
            self.assertEqual(completion['formalAttemptCapture'], 'not_qualified')
            link = evidence / 'report/../../../final-report/index.html'
            self.assertTrue(link.is_file())
            self.assertIn('final-report/index.html', (evidence / 'report/evaluation.html').read_text())

    def test_recovery_is_separate_from_student_and_formal_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assessment = root / 'real-agent/evidence/report/assessment.json'
            assessment.parent.mkdir(parents=True)
            assessment.write_text(json.dumps({'schema': 'agentlab.swe_report.v1', 'task': 'task'}))
            result = module.make_status(root, 'failure', '123', 'task', False)
            self.assertEqual(result['studentAssessment'], 'available')
            self.assertEqual(result['captureRecovery'], 'failed')
            self.assertEqual(result['formalAttemptCapture'], 'not_qualified')
            evidence = root / 'real-tablegit/evidence-one'
            evidence.mkdir(parents=True)
            capture = {'revision': 'abc', 'exactRows': True, 'exactPayloads': True, 'exactFiles': True,
                       'rowCount': 1, 'observationCount': 1, 'fileCount': 1, 'byteCount': 3}
            (evidence / 'summary.json').write_text(json.dumps({'ok': True, 'capture': capture}))
            (evidence / 'capture-recovery.json').write_text(json.dumps(capture))
            (evidence / 'capture-commit-manifest.json').write_text(json.dumps({'captureRevision': 'abc'}))
            (evidence / 'tablegit-capture.bundle').write_bytes(b'abc')
            bundle = {'restoredHead': 'abc', 'expectedCaptureRevision': 'abc', 'exportRevision': 'abc',
                      'historyExported': True, 'captureHistoryPresent': True, 'byteLength': 3,
                      'sha256': hashlib.sha256(b'abc').hexdigest()}
            (evidence / 'bundle-recovery.json').write_text(json.dumps(bundle))
            result = module.make_status(root, 'success', '123', 'task', True,
                                        run_attempt='2', source_run_id='99', subject_outcome='skipped')
            self.assertEqual(result['captureRecovery'], 'reported_exact')
            self.assertEqual(result['formalAttemptCapture'], 'not_qualified')
            self.assertTrue(result['captureReplay'])
            self.assertEqual(result['sourceWorkflowRunId'], '99')
            self.assertEqual(result['workflowRunAttempt'], '2')
            self.assertEqual(result['subjectStep'], 'skipped')
            (evidence / 'tablegit-capture.bundle').write_bytes(b'bad')
            self.assertEqual(module.make_status(root, 'success', '123', 'task', True)['captureRecovery'], 'inconsistent')

    def test_wrong_or_invalid_assessment_is_not_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assessment = root / 'real-agent/evidence/report/assessment.json'
            assessment.parent.mkdir(parents=True)
            assessment.write_text(json.dumps({'schema': 'agentlab.swe_report.v1', 'task': 'another'}))
            self.assertEqual(module.make_status(root, 'skipped', '1', 'task', False)['studentAssessment'], 'task_mismatch')
            assessment.write_text('{')
            self.assertEqual(module.make_status(root, 'skipped', '1', 'task', False)['studentAssessment'], 'invalid')

    def test_missing_or_ambiguous_receipt_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(module.make_status(root, 'success', '1', 't', False)['captureRecovery'], 'unknown')
            for name in ('one', 'two'):
                path = root / 'real-tablegit' / ('evidence-' + name)
                path.mkdir(parents=True)
                (path / 'summary.json').write_text('{}')
            self.assertEqual(module.make_status(root, 'success', '1', 't', False)['captureRecovery'], 'unknown')


if __name__ == '__main__':
    unittest.main()
