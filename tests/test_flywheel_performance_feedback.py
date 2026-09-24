from __future__ import annotations

import json
import hashlib
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

    def summary(self, run_id: str, digest: str, fps: float) -> dict:
        return {
            "schema": "agentlab.smartperf_summary.v1",
            "taskId": "case-ui-performance",
            "sourceIdentity": f"artifact-sha256:{digest}",
            "runId": run_id,
            "environmentIdentity": "hwlinux:emulator-26.0.0.400:class-a",
            "sampleCount": 3,
            "profileValid": True,
            "canonicalMetrics": {"fps": {"count": 3, "p50": fps}},
            "authority": {"absolutePowerThermal": "unavailable-on-emulator"},
        }

    def digest(self, value: dict) -> str:
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()

    def report(self, baseline: dict, candidate: dict) -> dict:
        return {
            "schema": "agentlab.smartperf_comparison.v1",
            "taskId": "case-ui-performance",
            "baselineRunId": "baseline",
            "baselineSourceIdentity": baseline["sourceIdentity"],
            "baselineSummarySha256": self.digest(baseline),
            "candidateRunId": "candidate",
            "candidateSourceIdentity": candidate["sourceIdentity"],
            "candidateSummarySha256": self.digest(candidate),
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

    def prepare(self, root: pathlib.Path, mutate=None) -> pathlib.Path:
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
        baseline = self.summary("baseline", "a" * 64, 60.0)
        candidate = self.summary("candidate", "b" * 64, 40.0)
        report = self.report(baseline, candidate)
        if mutate:
            mutate(report, baseline, candidate)
        (evidence / "smartperf-baseline-summary.json").write_text(json.dumps(baseline))
        (evidence / "smartperf-candidate-summary.json").write_text(json.dumps(candidate))
        (evidence / "smartperf-comparison.json").write_text(json.dumps(report))
        return evidence

    def test_performance_regression_becomes_review_only_durable_decision(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            output = root / "transaction.json"
            completed = self.run_builder(self.prepare(root), output)
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
            self.assertEqual(len(decisions[0]["baselineSummarySha256"]), 64)
            self.assertEqual(len(decisions[0]["evidenceIds"]), 3)
            self.assertTrue(
                any(
                    row["kind"] == "smartperf-comparison"
                    for row in tables["evidence_refs"]
                )
            )

    def test_tampered_decision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            def mutate(report, _baseline, _candidate):
                report["decision"] = "within-relative-guardrails"

            completed = self.run_builder(
                self.prepare(root, mutate), root / "transaction.json"
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("contradicts comparison metrics", completed.stderr)

    def test_tampered_candidate_summary_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)

            def mutate(_report, _baseline, candidate):
                candidate["canonicalMetrics"]["fps"]["p50"] = 55.0

            completed = self.run_builder(
                self.prepare(root, mutate), root / "transaction.json"
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("candidate SmartPerf summary digest differs", completed.stderr)


if __name__ == "__main__":
    unittest.main()
