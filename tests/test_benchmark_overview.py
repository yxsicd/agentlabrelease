import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
compose=load('overview',ROOT/'examples/benchmark-report/compose.py')
swe=load('swe_fixture',ROOT/'tests/test_swe_campaign_report.py')
terminal=load('terminal_fixture',ROOT/'tests/test_terminal_bench_report.py')


class OverviewTest(unittest.TestCase):
    def test_benchmarks_remain_separate_and_evidence_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s=root/'swe';s.mkdir();t=root/'terminal';t.mkdir()
            assessment=swe.CampaignTest().assessment(s,True)
            attempt,trial,reference=terminal.TerminalReportTest().fixture(t)
            result=compose.build([assessment],attempt,trial,reference)
            self.assertEqual(result['swe']['groups'][0]['counts']['resolved'],1)
            self.assertTrue(result['terminal']['resolved'])
            self.assertNotIn('passRate',result)
            (s/'summary.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'changed'):
                compose.build([assessment],attempt,trial,reference)


if __name__=='__main__':unittest.main()
