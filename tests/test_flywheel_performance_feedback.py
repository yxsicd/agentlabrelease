from __future__ import annotations

import json
import hashlib
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "examples/harmony-emulator/emulator-cpu-memory-relative.performance.json"
WORKLOAD_PATH = ROOT / "examples/harmony-emulator/tutu-scroll.profile"


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

    def functional_result(self, source: str, run_id: str, passed: bool = True) -> dict:
        return {
            "schema": "agentlab.harmony_emulator_case_result.v2",
            "status": "passed" if passed else "failed",
            "taskId": "case-ui-performance",
            "sourceIdentity": source,
            "hapSha256": source.removeprefix("artifact-sha256:"),
            "scenarioId": "bounded-ui-case",
            "scenarioSha256": "c" * 64,
            "oracleStatus": "passed" if passed else "failed",
            "assessmentStatus": "assessed",
            "infrastructureAvailable": True,
            "subjectTaskSucceeded": passed,
            "failureClass": "none" if passed else "oracle",
            "profileRunId": run_id,
            "environmentIdentity": "hwlinux:emulator-26.0.0.400:class-a",
            "profileStatus": "collected",
            "profileSummaryStatus": "normalized",
            "powerThermalAuthority": "unavailable_on_emulator",
        }

    def prepare(
        self,
        root: pathlib.Path,
        mutate=None,
        v2: bool = False,
        v3: bool = False,
        controlled_calibration: bool = False,
    ) -> pathlib.Path:
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
        if v3:
            policy = json.loads(POLICY_PATH.read_text())
            policy_sha = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
            workload_sha = hashlib.sha256(WORKLOAD_PATH.read_bytes()).hexdigest()
            policy_binding = {
                "id": policy["id"],
                "sha256": policy_sha,
                "requiredMetrics": policy["requiredMetrics"],
                "observedOnlyMetrics": policy["observedOnlyMetrics"],
            }
            workload_binding = {"id": "tutu-scroll-v1", "sha256": workload_sha}
            for profile, cpu in ((baseline, 10.0), (candidate, 30.0)):
                profile["schema"] = "agentlab.smartperf_summary.v2"
                profile["canonicalMetrics"] = {
                    "appCpuUsagePercent": {"count": 3, "mean": cpu},
                    "appPssKiB": {"count": 3, "mean": 100000.0},
                }
                profile["performancePolicy"] = policy_binding
                profile["profileWorkload"] = workload_binding
                profile["metricAvailability"] = {
                    "appCpuUsagePercent": True,
                    "appPssKiB": True,
                    "fps": False,
                    "frameIntervalMs": False,
                    "gpuLoadPercent": False,
                }
            report = self.report(baseline, candidate)
            report["schema"] = "agentlab.smartperf_comparison.v3"
            report["baselineSummarySha256"] = self.digest(baseline)
            report["candidateSummarySha256"] = self.digest(candidate)
            report["metrics"] = [
                {
                    "metric": "appCpuUsagePercent",
                    "statistic": "mean",
                    "status": "regressed",
                    "baseline": 10.0,
                    "candidate": 30.0,
                    "candidateToBaselineRatio": 3.0,
                    "guardrail": {"maximumRelativeIncrease": 0.2},
                },
                {
                    "metric": "appPssKiB",
                    "statistic": "mean",
                    "status": "passed",
                    "baseline": 100000.0,
                    "candidate": 100000.0,
                    "candidateToBaselineRatio": 1.0,
                    "guardrail": {"maximumRelativeIncrease": 0.15},
                },
            ]
            report["performancePolicy"] = {"id": policy["id"], "sha256": policy_sha}
            report["profileWorkload"] = workload_binding
            baseline_result = self.functional_result(baseline["sourceIdentity"], "baseline")
            candidate_result = self.functional_result(candidate["sourceIdentity"], "candidate")
            for result in (baseline_result, candidate_result):
                result.update({
                    "schema": "agentlab.harmony_emulator_case_result.v3",
                    "performancePolicyId": policy["id"],
                    "performancePolicySha256": policy_sha,
                    "profileWorkloadId": "tutu-scroll-v1",
                    "profileWorkloadSha256": workload_sha,
                })
            (evidence / "performance-policy.json").write_bytes(POLICY_PATH.read_bytes())
            (evidence / "profile-workload.tsv").write_bytes(WORKLOAD_PATH.read_bytes())
        elif v2:
            baseline_result = self.functional_result(baseline["sourceIdentity"], "baseline")
            candidate_result = self.functional_result(candidate["sourceIdentity"], "candidate")
            report["schema"] = "agentlab.smartperf_comparison.v2"
            report["functionalGate"] = {
                "baseline": {
                    "resultSha256": self.digest(baseline_result),
                    "sourceIdentity": baseline["sourceIdentity"],
                    "assessmentStatus": "assessed",
                    "infrastructureAvailable": True,
                    "subjectTaskSucceeded": True,
                    "oracleStatus": "passed",
                    "scenarioId": "bounded-ui-case",
                    "scenarioSha256": "c" * 64,
                    "profileRunId": "baseline",
                    "environmentIdentity": "hwlinux:emulator-26.0.0.400:class-a",
                    "passed": True,
                },
                "candidate": {
                    "resultSha256": self.digest(candidate_result),
                    "sourceIdentity": candidate["sourceIdentity"],
                    "assessmentStatus": "assessed",
                    "infrastructureAvailable": True,
                    "subjectTaskSucceeded": True,
                    "oracleStatus": "passed",
                    "scenarioId": "bounded-ui-case",
                    "scenarioSha256": "c" * 64,
                    "profileRunId": "candidate",
                    "environmentIdentity": "hwlinux:emulator-26.0.0.400:class-a",
                    "passed": True,
                },
                "passed": True,
            }
        if v2 or v3:
            report["functionalGate"] = {
                "baseline": {
                    "resultSha256": self.digest(baseline_result),
                    "sourceIdentity": baseline["sourceIdentity"],
                    "assessmentStatus": "assessed",
                    "infrastructureAvailable": True,
                    "subjectTaskSucceeded": True,
                    "oracleStatus": "passed",
                    "scenarioId": "bounded-ui-case",
                    "scenarioSha256": "c" * 64,
                    "profileRunId": "baseline",
                    "environmentIdentity": "hwlinux:emulator-26.0.0.400:class-a",
                    "passed": True,
                },
                "candidate": {
                    "resultSha256": self.digest(candidate_result),
                    "sourceIdentity": candidate["sourceIdentity"],
                    "assessmentStatus": "assessed",
                    "infrastructureAvailable": True,
                    "subjectTaskSucceeded": True,
                    "oracleStatus": "passed",
                    "scenarioId": "bounded-ui-case",
                    "scenarioSha256": "c" * 64,
                    "profileRunId": "candidate",
                    "environmentIdentity": "hwlinux:emulator-26.0.0.400:class-a",
                    "passed": True,
                },
                "passed": True,
            }
            (evidence / "harmony-baseline-result.json").write_text(json.dumps(baseline_result))
            (evidence / "harmony-candidate-result.json").write_text(json.dumps(candidate_result))
        if mutate:
            mutate(report, baseline, candidate)
        (evidence / "smartperf-baseline-summary.json").write_text(json.dumps(baseline))
        (evidence / "smartperf-candidate-summary.json").write_text(json.dumps(candidate))
        (evidence / "smartperf-comparison.json").write_text(json.dumps(report))
        if controlled_calibration:
            comparison_sha = hashlib.sha256(
                (evidence / "smartperf-comparison.json").read_bytes()
            ).hexdigest()
            (evidence / "performance-calibration.json").write_text(
                json.dumps(
                    {
                        "schema": "agentlab.performance_calibration.v1",
                        "id": "retained-memory-64m-v1",
                        "taskId": report["taskId"],
                        "harnessRevision": "1" * 40,
                        "applicationSource": {
                            "repository": "https://example.invalid/application.git",
                            "revision": "3" * 40,
                            "path": "entry/src/main/ets/pages/Template.ets",
                        },
                        "baseline": {"sourceIdentity": baseline["sourceIdentity"]},
                        "candidate": {
                            "sourceIdentity": candidate["sourceIdentity"],
                            "baseSourceIdentity": baseline["sourceIdentity"],
                            "controlledMutation": {
                                "id": "retain-64m",
                                "kind": "retained-memory",
                                "bytes": 64 * 1024 * 1024,
                                "sourcePath": "entry/src/main/ets/pages/Template.ets",
                                "baseSourceFileSha256": "4" * 64,
                                "candidateSourceFileSha256": "5" * 64,
                            },
                        },
                        "functionalOracle": {
                            "scenarioId": "bounded-ui-case",
                            "scenarioSha256": "c" * 64,
                            "expected": "passed-both",
                        },
                        "environmentIdentity": report["environmentIdentity"],
                        "performancePolicy": report["performancePolicy"],
                        "profileWorkload": report["profileWorkload"],
                        "comparisonSha256": comparison_sha,
                        "expectedDecision": report["decision"],
                        "authority": {
                            "relativePerformance": "smartperf-emulator-proxy",
                            "absolutePowerThermal": "unavailable-on-emulator",
                        },
                        "automaticPromotion": False,
                    }
                )
            )
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

    def test_functionally_passing_regression_becomes_difficulty_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            output = root / "transaction.json"
            completed = self.run_builder(self.prepare(root, v2=True), output)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output.read_text())
            difficulties = [
                operation["row"]
                for table in payload["arguments"]["tables"]
                if table["path"] == "difficulty_points"
                for operation in table["operations"]
            ]
            self.assertEqual(len(difficulties), 1)
            self.assertEqual(
                difficulties[0]["dimensionId"],
                "functionally-correct-performance-regression",
            )
            self.assertFalse(difficulties[0]["verificationContract"]["caseReady"])
            self.assertFalse(difficulties[0]["automaticPromotion"])
            self.assertEqual(len(difficulties[0]["evidenceIds"]), 5)

    def test_tampered_functional_result_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            evidence = self.prepare(root, v2=True)
            result_path = evidence / "harmony-candidate-result.json"
            result = json.loads(result_path.read_text())
            result["subjectTaskSucceeded"] = False
            result_path.write_text(json.dumps(result))
            completed = self.run_builder(evidence, root / "transaction.json")
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("functional result digest differs", completed.stderr)

    def test_policy_bound_regression_retains_workload_and_policy_identities(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            output = root / "transaction.json"
            completed = self.run_builder(self.prepare(root, v3=True), output)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output.read_text())
            rows = [
                operation["row"]
                for table in payload["arguments"]["tables"]
                for operation in table["operations"]
            ]
            decision = next(row for row in rows if row.get("schema") == "agentlab.performance_feedback_decision.v1")
            difficulty = next(row for row in rows if row.get("dimensionId") == "functionally-correct-performance-regression")
            self.assertEqual(decision["performancePolicy"]["id"], "emulator-cpu-memory-relative-v1")
            self.assertEqual(decision["profileWorkload"]["id"], "tutu-scroll-v1")
            self.assertEqual(len(decision["evidenceIds"]), 7)
            self.assertEqual(
                difficulty["profileWorkload"]["sha256"],
                hashlib.sha256(WORKLOAD_PATH.read_bytes()).hexdigest(),
            )

    def test_controlled_calibration_is_bound_to_decision_and_difficulty(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            output = root / "transaction.json"
            completed = self.run_builder(
                self.prepare(root, v3=True, controlled_calibration=True), output
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output.read_text())
            rows = [
                operation["row"]
                for table in payload["arguments"]["tables"]
                for operation in table["operations"]
            ]
            decision = next(
                row
                for row in rows
                if row.get("schema") == "agentlab.performance_feedback_decision.v1"
            )
            difficulty = next(
                row
                for row in rows
                if row.get("dimensionId") == "functionally-correct-performance-regression"
            )
            for row in (decision, difficulty):
                self.assertEqual(
                    row["performanceCalibration"]["id"], "retained-memory-64m-v1"
                )
                self.assertEqual(
                    row["performanceCalibration"]["controlledMutation"]["bytes"],
                    64 * 1024 * 1024,
                )
                self.assertEqual(len(row["evidenceIds"]), 8)

    def test_tampered_controlled_calibration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            evidence = self.prepare(root, v3=True, controlled_calibration=True)
            path = evidence / "performance-calibration.json"
            calibration = json.loads(path.read_text())
            calibration["candidate"]["controlledMutation"]["bytes"] = 0
            path.write_text(json.dumps(calibration))
            completed = self.run_builder(evidence, root / "transaction.json")
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("positive byte count", completed.stderr)

    def test_tampered_retained_policy_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            evidence = self.prepare(root, v3=True)
            policy = json.loads((evidence / "performance-policy.json").read_text())
            policy["id"] = "tampered"
            (evidence / "performance-policy.json").write_text(json.dumps(policy))
            completed = self.run_builder(evidence, root / "transaction.json")
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("retained performance policy differs", completed.stderr)

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
