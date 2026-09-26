from __future__ import annotations

import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


SUMMARY = load_module("smartperf_summary", ROOT / "scripts/summarize-smartperf.py")
COMPARE = load_module("smartperf_compare", ROOT / "scripts/compare-smartperf.py")
POLICY_PATH = ROOT / "examples/harmony-emulator/emulator-cpu-memory-relative.performance.json"
WORKLOAD_PATH = ROOT / "examples/harmony-emulator/tutu-scroll.profile"


def raw_profile(fps: float, cpu: float, pss: float, jitter_ms: float) -> bytes:
    blocks = []
    for ordinal in range(3):
        timestamp = 1000 + ordinal * 1000
        jitter_ns = int(jitter_ms * 1_000_000)
        blocks.append(
            "\n".join(
                [
                    "----------------Print START----------------",
                    f"order:0 timestamp={timestamp}",
                    "order:1 ProcAppName=com.example.app",
                    f"order:2 ProcCpuUsage={cpu + ordinal * 0.1}",
                    "order:3 gpuload=30",
                    "order:4 currentNow=250",
                    "order:5 voltageNow=4200000",
                    "order:6 soc_thermal=48",
                    "order:7 gpuTemp=50",
                    f"order:8 fps={fps - ordinal}",
                    f"order:9 fpsJitters={jitter_ns};;{jitter_ns + 100000}",
                    f"order:10 pss={pss + ordinal}",
                    "order:11 futureMetric=7",
                    "----------------Print END----------------",
                ]
            )
        )
    return ("\n".join(blocks) + "\n").encode()


def summary(
    raw: bytes,
    source: str,
    run: str,
    environment: str = "hwlinux:emulator-26.0.0.400:instance-class-a",
):
    return SUMMARY.build_summary(
        raw,
        "case-ui-performance",
        source,
        run,
        environment,
        3,
    )


def functional_result(source: str, run_id: str, passed: bool = True):
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
        "environmentIdentity": "hwlinux:emulator-26.0.0.400:instance-class-a",
        "profileStatus": "collected",
        "profileSummaryStatus": "normalized",
        "powerThermalAuthority": "unavailable_on_emulator",
    }


def policy_summary(raw: bytes, source: str, run: str):
    policy, policy_sha = SUMMARY.load_policy(POLICY_PATH)
    workload_id, workload_sha = SUMMARY.load_workload(WORKLOAD_PATH)
    return SUMMARY.build_summary(
        raw,
        "case-ui-performance",
        source,
        run,
        "hwlinux:emulator-26.0.0.400:instance-class-a",
        3,
        policy,
        policy_sha,
        workload_id,
        workload_sha,
    )


def policy_functional_result(source: str, run_id: str):
    value = functional_result(source, run_id)
    policy, policy_sha = SUMMARY.load_policy(POLICY_PATH)
    workload_id, workload_sha = SUMMARY.load_workload(WORKLOAD_PATH)
    value.update(
        {
            "schema": "agentlab.harmony_emulator_case_result.v3",
            "performancePolicyId": policy["id"],
            "performancePolicySha256": policy_sha,
            "profileWorkloadId": workload_id,
            "profileWorkloadSha256": workload_sha,
        }
    )
    return value


class SmartPerfFeedbackTests(unittest.TestCase):
    def test_official_order_format_is_normalized_without_power_claim(self) -> None:
        value = summary(raw_profile(60, 10, 100000, 16.0), "artifact:base", "base")
        self.assertTrue(value["profileValid"])
        self.assertEqual(value["sampleCount"], 3)
        self.assertEqual(value["canonicalMetrics"]["fps"]["count"], 3)
        self.assertEqual(value["canonicalMetrics"]["frameIntervalMs"]["count"], 6)
        self.assertEqual(
            value["authority"]["absolutePowerThermal"], "unavailable-on-emulator"
        )
        self.assertIn("currentNow", value["authority"]["nonGatingPowerThermalMetrics"])
        self.assertIn("soc_thermal", value["authority"]["nonGatingPowerThermalMetrics"])
        self.assertIn("gpuTemp", value["authority"]["nonGatingPowerThermalMetrics"])
        self.assertIn("futureMetric", value["unknownNumericMetricNames"])

    def test_markerless_device_stream_uses_order_zero_as_sample_boundary(self) -> None:
        raw = b"""\
order:0 ProcCpuUsage=1.0
order:1 fps=0
order:2 fpsJitters=
order:3 pss=174551
order:0 ProcCpuUsage=2.0
order:1 fps=0
order:2 fpsJitters=
order:3 pss=174552
order:0 ProcCpuUsage=3.0
order:1 fps=0
order:2 fpsJitters=
order:3 pss=174553
"""
        value = summary(raw, "artifact:device", "device")
        self.assertTrue(value["profileValid"])
        self.assertEqual(value["sampleCount"], 3)
        self.assertEqual(value["canonicalMetrics"]["appCpuUsagePercent"]["mean"], 2.0)
        self.assertNotIn("frameIntervalMs", value["canonicalMetrics"])

    def test_policy_bound_profile_accepts_cpu_pss_without_frame_telemetry(self) -> None:
        raw = b"""\
order:0 ProcCpuUsage=5.0
order:1 fps=0
order:2 fpsJitters=
order:3 pss=170000
order:0 ProcCpuUsage=6.0
order:1 fps=0
order:2 fpsJitters=
order:3 pss=171000
order:0 ProcCpuUsage=7.0
order:1 fps=0
order:2 fpsJitters=
order:3 pss=172000
"""
        value = policy_summary(raw, f"artifact-sha256:{'a' * 64}", "policy-run")
        self.assertEqual(value["schema"], "agentlab.smartperf_summary.v2")
        self.assertTrue(value["profileValid"])
        self.assertEqual(value["profileWorkload"]["id"], "tutu-scroll-v1")
        self.assertFalse(value["metricAvailability"]["frameIntervalMs"])
        self.assertTrue(value["metricAvailability"]["appCpuUsagePercent"])

    def test_policy_bound_cpu_pss_profiles_are_comparable_without_fps(self) -> None:
        def device(cpu: float, pss: float) -> bytes:
            return "".join(
                f"order:0 ProcCpuUsage={cpu + index}\norder:1 fps=0\norder:2 fpsJitters=\norder:3 pss={pss + index}\n"
                for index in range(3)
            ).encode()

        baseline_source = f"artifact-sha256:{'a' * 64}"
        candidate_source = f"artifact-sha256:{'b' * 64}"
        baseline = policy_summary(device(5, 170000), baseline_source, "base")
        candidate = policy_summary(device(5.5, 175000), candidate_source, "candidate")
        report = COMPARE.build_comparison(
            baseline,
            candidate,
            0.90,
            0.20,
            0.15,
            0.20,
            policy_functional_result(baseline_source, "base"),
            policy_functional_result(candidate_source, "candidate"),
        )
        self.assertEqual(report["schema"], "agentlab.smartperf_comparison.v3")
        self.assertTrue(report["comparable"])
        self.assertEqual(report["decision"], "within-relative-guardrails")
        self.assertEqual(
            [row["metric"] for row in report["metrics"]],
            ["appCpuUsagePercent", "appPssKiB"],
        )
        self.assertEqual(report["performancePolicy"]["id"], "emulator-cpu-memory-relative-v1")

    def test_policy_or_workload_mismatch_is_not_comparable(self) -> None:
        baseline_source = f"artifact-sha256:{'a' * 64}"
        candidate_source = f"artifact-sha256:{'b' * 64}"
        baseline = policy_summary(raw_profile(60, 10, 100000, 16), baseline_source, "base")
        candidate = policy_summary(raw_profile(60, 10, 100000, 16), candidate_source, "candidate")
        candidate["profileWorkload"]["sha256"] = "f" * 64
        candidate_result = policy_functional_result(candidate_source, "candidate")
        candidate_result["profileWorkloadSha256"] = "f" * 64
        report = COMPARE.build_comparison(
            baseline,
            candidate,
            0.90,
            0.20,
            0.15,
            0.20,
            policy_functional_result(baseline_source, "base"),
            candidate_result,
        )
        self.assertFalse(report["comparable"])
        self.assertIn("profile-workload-mismatch", report["incomparabilityReasons"])

    def test_relative_guardrails_accept_stable_candidate(self) -> None:
        baseline = summary(raw_profile(60, 10, 100000, 16.0), "artifact:base", "base")
        candidate = summary(
            raw_profile(58, 11, 105000, 17.0), "artifact:candidate", "candidate"
        )
        report = COMPARE.build_comparison(baseline, candidate, 0.90, 0.20, 0.15, 0.20)
        self.assertTrue(report["comparable"])
        self.assertEqual(report["decision"], "within-relative-guardrails")
        self.assertTrue(all(row["status"] == "passed" for row in report["metrics"]))
        self.assertFalse(report["policy"]["absolutePowerThermalUsed"])
        self.assertFalse(report["policy"]["automaticPromotion"])
        self.assertEqual(len(report["baselineSummarySha256"]), 64)
        self.assertEqual(len(report["candidateSummarySha256"]), 64)

    def test_regression_is_evidence_candidate_not_automatic_rejection(self) -> None:
        baseline = summary(raw_profile(60, 10, 100000, 16.0), "artifact:base", "base")
        candidate = summary(
            raw_profile(40, 30, 200000, 40.0), "artifact:slow", "candidate"
        )
        report = COMPARE.build_comparison(baseline, candidate, 0.90, 0.20, 0.15, 0.20)
        self.assertEqual(report["decision"], "performance-regression-candidate")
        self.assertTrue(any(row["status"] == "regressed" for row in report["metrics"]))
        self.assertFalse(report["policy"]["automaticPromotion"])

    def test_v2_regression_requires_both_functional_gates(self) -> None:
        baseline_source = f"artifact-sha256:{'a' * 64}"
        candidate_source = f"artifact-sha256:{'b' * 64}"
        baseline = summary(raw_profile(60, 10, 100000, 16.0), baseline_source, "base")
        candidate = summary(raw_profile(40, 30, 200000, 40.0), candidate_source, "candidate")
        report = COMPARE.build_comparison(
            baseline,
            candidate,
            0.90,
            0.20,
            0.15,
            0.20,
            functional_result(baseline_source, "base"),
            functional_result(candidate_source, "candidate"),
        )
        self.assertEqual(report["schema"], "agentlab.smartperf_comparison.v2")
        self.assertTrue(report["functionalGate"]["passed"])
        self.assertEqual(report["decision"], "performance-regression-candidate")

    def test_failed_functional_candidate_cannot_be_a_performance_regression(self) -> None:
        baseline_source = f"artifact-sha256:{'a' * 64}"
        candidate_source = f"artifact-sha256:{'b' * 64}"
        baseline = summary(raw_profile(60, 10, 100000, 16.0), baseline_source, "base")
        candidate = summary(raw_profile(40, 30, 200000, 40.0), candidate_source, "candidate")
        report = COMPARE.build_comparison(
            baseline,
            candidate,
            0.90,
            0.20,
            0.15,
            0.20,
            functional_result(baseline_source, "base"),
            functional_result(candidate_source, "candidate", passed=False),
        )
        self.assertFalse(report["functionalGate"]["passed"])
        self.assertFalse(report["comparable"])
        self.assertEqual(report["decision"], "insufficient-comparable-evidence")
        self.assertIn("candidate-functional-gate-failed", report["incomparabilityReasons"])

    def test_functional_hap_mismatch_is_rejected(self) -> None:
        baseline_source = f"artifact-sha256:{'a' * 64}"
        candidate_source = f"artifact-sha256:{'b' * 64}"
        baseline = summary(raw_profile(60, 10, 100000, 16.0), baseline_source, "base")
        candidate = summary(raw_profile(40, 30, 200000, 40.0), candidate_source, "candidate")
        wrong = functional_result(candidate_source, "candidate")
        wrong["hapSha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "HAP digest"):
            COMPARE.build_comparison(
                baseline,
                candidate,
                0.90,
                0.20,
                0.15,
                0.20,
                functional_result(baseline_source, "base"),
                wrong,
            )

    def test_different_functional_scenarios_are_not_comparable(self) -> None:
        baseline_source = f"artifact-sha256:{'a' * 64}"
        candidate_source = f"artifact-sha256:{'b' * 64}"
        baseline = summary(raw_profile(60, 10, 100000, 16.0), baseline_source, "base")
        candidate = summary(raw_profile(40, 30, 200000, 40.0), candidate_source, "candidate")
        candidate_result = functional_result(candidate_source, "candidate")
        candidate_result["scenarioSha256"] = "d" * 64
        report = COMPARE.build_comparison(
            baseline,
            candidate,
            0.90,
            0.20,
            0.15,
            0.20,
            functional_result(baseline_source, "base"),
            candidate_result,
        )
        self.assertFalse(report["comparable"])
        self.assertEqual(report["decision"], "insufficient-comparable-evidence")
        self.assertIn("functional-scenario-mismatch", report["incomparabilityReasons"])

    def test_environment_mismatch_is_not_compared(self) -> None:
        baseline = summary(raw_profile(60, 10, 100000, 16.0), "artifact:base", "base")
        candidate = summary(
            raw_profile(40, 30, 200000, 40.0),
            "artifact:other",
            "other",
            "different-host",
        )
        report = COMPARE.build_comparison(baseline, candidate, 0.90, 0.20, 0.15, 0.20)
        self.assertFalse(report["comparable"])
        self.assertEqual(report["decision"], "insufficient-comparable-evidence")
        self.assertIn("environment-mismatch", report["incomparabilityReasons"])

    def test_zero_fps_baseline_is_unusable_not_a_regression(self) -> None:
        baseline = summary(raw_profile(0, 10, 100000, 16.0), "artifact:base", "base")
        candidate = summary(raw_profile(0, 9, 99000, 15.0), "artifact:candidate", "candidate")
        report = COMPARE.build_comparison(baseline, candidate, 0.90, 0.20, 0.15, 0.20)
        fps = next(row for row in report["metrics"] if row["metric"] == "fps")
        self.assertEqual(fps["status"], "unusable-baseline")
        self.assertFalse(report["comparable"])
        self.assertEqual(report["decision"], "insufficient-comparable-evidence")
        self.assertIn(
            "required-metric-unusable-baseline", report["incomparabilityReasons"]
        )
        self.assertFalse(any(row["status"] == "regressed" for row in report["metrics"]))

    def test_truncated_sample_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unterminated"):
            summary(b"---Print START---\norder:0 fps=60\n", "artifact:x", "broken")


if __name__ == "__main__":
    unittest.main()
