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
        (root / 'participant.json').write_text(json.dumps({'model': model}))
        value = fixtures.reporter.build(root)
        out = root / 'report'; out.mkdir()
        (out / 'evaluation.html').write_text(fixtures.reporter.render(value))
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

    def test_tampered_verdict_or_model_is_rejected_even_if_evidence_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.assessment(root, True)
            original = json.loads(path.read_text())
            for field in ('resolved', 'model'):
                value = json.loads(json.dumps(original))
                if field == 'resolved': value['resolved'] = False
                else: value['participant']['model'] = 'different-model'
                path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    campaign.build([path])

    def test_reformatted_copy_cannot_be_counted_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.assessment(root, True)
            duplicate = path.with_name('copy.json')
            duplicate.write_text(json.dumps(json.loads(path.read_text()), indent=4, sort_keys=True))
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                campaign.build([path, duplicate])

    def test_tampered_html_is_not_linked_from_campaign(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = self.assessment(root, True)
            (path.parent / 'evaluation.html').write_text('tampered')
            with self.assertRaisesRegex(ValueError, 'HTML does not match'):
                campaign.build([path])


if __name__ == '__main__': unittest.main()
