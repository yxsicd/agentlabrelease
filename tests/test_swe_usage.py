import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('swe_usage', Path(__file__).resolve().parents[1] / 'examples/swe-bench/usage.py')
usage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage)


class SweUsageTest(unittest.TestCase):
    def test_json_stream_subsets_and_missing_exchange(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            completed = {'status': 200, 'outcome': 'completed', 'upstreamEof': True}
            for n in ('0001', '0002', '0003'):
                (root / f'{n}.status.json').write_text(json.dumps(completed))
            (root / '0001.response').write_text(json.dumps({'usage': {
                'prompt_tokens': 100, 'completion_tokens': 20,
                'prompt_tokens_details': {'cached_tokens': 80},
                'completion_tokens_details': {'reasoning_tokens': 5}}}))
            (root / '0002.response').write_text('data: {"choices": []}\n\n'
                'data: {"usage": {"prompt_tokens": 40, "completion_tokens": 3}}\n\n'
                'data: [DONE]\n\n')
            (root / '0003.response').write_text('{}')
            result = usage.summarize(root)
            self.assertEqual(result['exchanges'], 3)
            self.assertFalse(result['inputOutputComplete'])
            self.assertEqual(result['totalsObserved'], {'input': 140, 'output': 23,
                             'cached_input': 80, 'reasoning_output': 5})
            self.assertEqual(result['fieldCoverage']['input'], 2)
            self.assertEqual(result['fieldCoverage']['cached_input'], 1)
            self.assertTrue(result['cachedInputIncludedInInput'])
            self.assertFalse(result['tokenBudgetEnforced'])

    def test_partial_exchange_and_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '0001.status.json').write_text(json.dumps({'status': 200, 'outcome': 'incomplete_stream', 'upstreamEof': True}))
            (root / '0001.response').write_text('data: {"usage": {"input_tokens": 7, "output_tokens": 2}}\n\n')
            result = usage.summarize(root)
            self.assertFalse(result['inputOutputComplete'])
            self.assertIsNone(result['totalsObserved']['cached_input'])
            self.assertEqual(result['totalsObserved']['input'], 7)

    def test_request_without_status_keeps_coverage_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '0001.request.json').write_text('{}')
            result = usage.summarize(root)
            self.assertEqual(result['exchanges'], 1)
            self.assertFalse(result['inputOutputComplete'])
            self.assertIsNone(result['totalsObserved']['input'])


if __name__ == '__main__':
    unittest.main()
