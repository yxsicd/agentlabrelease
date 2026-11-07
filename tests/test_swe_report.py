import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('swe_report', ROOT / 'examples/swe-bench/report.py')
reporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporter)


class SweReportTest(unittest.TestCase):
    def make_evidence(self, root, reference=True):
        def write(path, value):
            file = root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(value))
        write('summary.json', {'schema': 'agentlab.swe_acceptance.v1', 'instanceId': 'case',
                               'harnessHealthy': True, 'agentResolved': True, 'status': 'completed'})
        write('swe-task-lifecycle.json', {'exitCode': -15, 'durationMs': 5, 'toolErrors': 1})
        write('participant.json', {'model': '<script>alert(1)</script>'})
        write('usage-observation.json', {'exchanges': 1, 'inputOutputComplete': False,
                                        'totalsObserved': {'input': 20, 'output': None}})
        def evaluation(resolved):
            return {'case': {'resolved': resolved, 'tests_status': {
                'FAIL_TO_PASS': {'success': ['a'], 'failure': []},
                'PASS_TO_PASS': {'success': ['b', 'c'], 'failure': []}}}}
        write('logs/run_evaluation/agent/model/case/report.json', evaluation(True))
        if reference is not None:
            write('logs/run_evaluation/reference/model/case/report.json', evaluation(reference))

    def test_passing_patch_is_not_normal_submission_and_missing_fields_stay_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.make_evidence(root)
            result = reporter.build(root)
            self.assertEqual(result['qualification'], 'qualified')
            self.assertIs(result['resolved'], True)
            self.assertIs(result['normalSubmission'], False)
            self.assertIsNone(result['participant']['teacherHelp'])
            self.assertIsNone(result['usage']['totalsObserved']['output'])
            self.assertEqual(result['agentEvaluation']['tests']['PASS_TO_PASS']['passed'], 2)
            self.assertTrue(all(len(item['sha256']) == 64 for item in result['evidence']))
            page = reporter.render(result)
            self.assertNotIn('<script>alert', page)
            self.assertIn('&lt;script&gt;', page)
            linked = reporter.render(result, '../../../final-report/index.html')
            self.assertIn('href="../../../final-report/index.html"', linked)

    def test_reference_failure_never_scores_student(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.make_evidence(root, reference=False)
            result = reporter.build(root)
            self.assertEqual(result['qualification'], 'harness_failure')
            self.assertIsNone(result['resolved'])
            self.assertIs(result['agentEvaluation']['resolved'], True)

    def test_missing_reference_never_scores_student(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.make_evidence(root, reference=None)
            result = reporter.build(root)
            self.assertEqual(result['qualification'], 'unknown')
            self.assertIsNone(result['resolved'])


if __name__ == '__main__':
    unittest.main()
