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

    def test_truncated_sample_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unterminated"):
            summary(b"---Print START---\norder:0 fps=60\n", "artifact:x", "broken")


if __name__ == "__main__":
    unittest.main()
