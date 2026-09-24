from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class FlywheelPerformanceFeedbackTests(unittest.TestCase):
    def run_builder(self, evidence: pathlib.Path, output: pathlib.Path):
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build-cbgroom-flywheel-transaction.py"),
                "--evidence",
                str(evidence),
                "--revision",
                "2" * 40,
                "--run-id",
                "performance-run",
                "--github-repository",
                "example/agentlab",
                "--caller-person-id",
                "00000000-0000-0000-0000-000000000001",
                "--output",
                str(output),
            ],
            text=True,
            capture_output=True,
        )

    def report(self) -> dict:
        return {
            "schema": "agentlab.smartperf_comparison.v1",
            "taskId": "case-ui-performance",
            "baselineRunId": "baseline",
            "baselineSourceIdentity": "artifact:baseline",
            "baselineSummarySha256": "a" * 64,
            "candidateRunId": "candidate",
            "candidateSourceIdentity": "artifact:candidate",
            "candidateSummarySha256": "b" * 64,
            "environmentIdentity": "hwlinux:emulator-26.0.0.400:class-a",
            "comparable": True,
            "incomparabilityReasons": [],
            "metrics": [
                {
                    "metric": "fps",
                    "statistic": "p50",
                    "status": "regressed",
                    "baseline": 60.0,
                    "candidate": 40.0,
                    "candidateToBaselineRatio": 2 / 3,
                    "guardrail": {"minimumCandidateToBaselineRatio": 0.9},
                }
            ],
            "decision": "performance-regression-candidate",
            "policy": {
                "automaticPromotion": False,
                "absolutePowerThermalUsed": False,
                "interpretation": "relative emulator regression signal only",
            },
        }

    def prepare(self, root: pathlib.Path, report: dict) -> pathlib.Path:
        evidence = root / "evidence"
        evidence.mkdir()
        (evidence / "summary.json").write_text(
            json.dumps(
                {
                    "schema": "agentlab.subject.v1",
                    "sourceRevision": "1" * 40,
                    "taskId": "campaign",
                }
            )
        )
        (evidence / "smartperf-comparison.json").write_text(json.dumps(report))
        return evidence

    def test_performance_regression_becomes_review_only_durable_decision(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            output = root / "transaction.json"
            completed = self.run_builder(self.prepare(root, self.report()), output)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output.read_text())
            tables = {
                table["path"]: [operation["row"] for operation in table["operations"]]
                for table in payload["arguments"]["tables"]
            }
            decisions = [
                row
                for row in tables["decisions"]
                if row["schema"] == "agentlab.performance_feedback_decision.v1"
            ]
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]["decision"], "performance-regression-candidate")
            self.assertFalse(decisions[0]["automaticPromotion"])
            self.assertFalse(decisions[0]["absolutePowerThermalUsed"])
            self.assertEqual(decisions[0]["baselineSummarySha256"], "a" * 64)
            self.assertTrue(decisions[0]["evidenceIds"])
            self.assertTrue(
                any(
                    row["kind"] == "smartperf-comparison"
                    for row in tables["evidence_refs"]
                )
            )

    def test_tampered_decision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            report = self.report()
            report["decision"] = "within-relative-guardrails"
            completed = self.run_builder(
                self.prepare(root, report), root / "transaction.json"
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("contradicts comparison metrics", completed.stderr)


if __name__ == "__main__":
    unittest.main()
