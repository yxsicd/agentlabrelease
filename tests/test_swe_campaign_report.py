import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('campaign', ROOT / 'examples/swe-bench/campaign_report.py')
campaign = importlib.util.module_from_spec(spec); spec.loader.exec_module(campaign)
spec = importlib.util.spec_from_file_location('report_tests', ROOT / 'tests/test_swe_report.py')
fixtures = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixtures)


class CampaignTest(unittest.TestCase):
    def assessment(self, root, reference, model='model'):
        fixtures.SweReportTest().make_evidence(root, reference=reference)
        value = fixtures.reporter.build(root)
        value['participant']['model'] = model
        out = root / 'report'; out.mkdir()
        path = out / 'assessment.json'; path.write_text(json.dumps(value))
        return path

    def test_harness_failures_do_not_enter_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / 'a'; a.mkdir(); b = Path(tmp) / 'b'; b.mkdir()
            result = campaign.build([self.assessment(a, True), self.assessment(b, False)])
            group = result['groups'][0]
            self.assertEqual(group['counts'], {'total': 2, 'scored': 1, 'resolved': 1,
                             'unresolved': 0, 'harnessFailure': 1, 'unknownOrUnscored': 0})
            self.assertEqual(group['passRate'], 1.0)

    def test_missing_reference_and_separate_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / 'a'; a.mkdir(); b = Path(tmp) / 'b'; b.mkdir()
            groups = campaign.build([self.assessment(a, None, 'one'), self.assessment(b, True, 'two')])['groups']
            self.assertEqual(len(groups), 2)
            missing = next(g for g in groups if g['configuration']['model'] == 'one')
            self.assertEqual(missing['counts']['unknownOrUnscored'], 1)
            self.assertIsNone(missing['passRate'])

    def test_duplicate_or_changed_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.assessment(root, True)
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                campaign.build([path, path])
            (root / 'summary.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'changed'):
                campaign.build([path])


if __name__ == '__main__': unittest.main()
