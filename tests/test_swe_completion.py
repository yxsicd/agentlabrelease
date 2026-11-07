import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('completion', Path(__file__).parents[1] / 'examples/swe-bench/finalize.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CompletionTest(unittest.TestCase):
    def test_recovery_is_separate_from_student_and_formal_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assessment = root / 'real-agent/evidence/report/assessment.json'
            assessment.parent.mkdir(parents=True)
            assessment.write_text('{}')
            result = module.make_status(root, 'failure', '123', 'task', False)
            self.assertEqual(result['studentAssessment'], 'available')
            self.assertEqual(result['captureRecovery'], 'failed')
            self.assertEqual(result['formalAttemptCapture'], 'not_qualified')
            evidence = root / 'real-tablegit/evidence-one'
            evidence.mkdir(parents=True)
            (evidence / 'summary.json').write_text(json.dumps({'ok': True, 'capture': {
                'revision': 'abc', 'exactRows': True, 'exactPayloads': True, 'exactFiles': True}}))
            result = module.make_status(root, 'success', '123', 'task', True)
            self.assertEqual(result['captureRecovery'], 'reported_exact')
            self.assertEqual(result['formalAttemptCapture'], 'not_qualified')
            self.assertTrue(result['captureReplay'])

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
