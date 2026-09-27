from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/compose-case-performance-calibration.py"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


COMPARE = load_module("case_performance_compare", ROOT / "scripts/compare-smartperf.py")


class CasePerformanceCalibrationTests(unittest.TestCase):
    case_id = "performance-derived-case"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.policy_sha = "7" * 64
        self.workload_sha = "8" * 64
        self.environment = "hwlinux:phone-x86"
        self.baseline_identity = f"artifact-sha256:{'a' * 64}"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, path: pathlib.Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def summary(self, run_id: str, identity: str, cpu: float) -> dict:
        return {
            "schema": "agentlab.smartperf_summary.v2",
            "taskId": self.case_id,
            "sourceIdentity": identity,
            "runId": run_id,
            "environmentIdentity": self.environment,
            "sampleCount": 3,
            "minimumSampleCount": 3,
            "profileValid": True,
            "canonicalMetrics": {
                "appCpuUsagePercent": {
                    "count": 3,
                    "min": cpu,
                    "max": cpu,
                    "mean": cpu,
                    "p50": cpu,
                    "p95": cpu,
                    "unit": "reported-percent",
                }
            },
            "performancePolicy": {
                "id": "cpu-v1",
                "sha256": self.policy_sha,
                "requiredMetrics": [
                    {
                        "metric": "appCpuUsagePercent",
                        "statistic": "mean",
                        "direction": "lower",
                        "maximumRelativeIncrease": 0.2,
                    }
                ],
                "observedOnlyMetrics": [],
            },
            "profileWorkload": {"id": "scroll-v1", "sha256": self.workload_sha},
            "authority": {
                "functional": "none",
                "relativePerformance": "smartperf-emulator-proxy",
                "absolutePowerThermal": "unavailable-on-emulator",
            },
        }

    def result(self, run_id: str, identity: str) -> dict:
        hap = identity.removeprefix("artifact-sha256:")
        return {
            "schema": "agentlab.harmony_emulator_case_result.v3",
            "status": "passed",
            "taskId": self.case_id,
            "sourceIdentity": identity,
            "hapSha256": hap,
            "oracleStatus": "passed",
            "assessmentStatus": "assessed",
            "infrastructureAvailable": True,
            "subjectTaskSucceeded": True,
            "failureClass": "none",
            "powerThermalAuthority": "unavailable_on_emulator",
            "scenarioId": "case-oracle",
            "scenarioSha256": "6" * 64,
            "profileRunId": run_id,
            "environmentIdentity": self.environment,
            "profileStatus": "collected",
            "profileSummaryStatus": "normalized",
            "performancePolicyId": "cpu-v1",
            "performancePolicySha256": self.policy_sha,
            "profileWorkloadId": "scroll-v1",
            "profileWorkloadSha256": self.workload_sha,
        }

    def observation(
        self, role: str, ordinal: int, cpu: float, identity: str
    ) -> dict:
        root = self.root / role / str(ordinal)
        baseline_run = f"baseline-{role}-{ordinal}"
        candidate_run = f"{role}-{ordinal}"
        baseline = self.summary(baseline_run, self.baseline_identity, 10.0)
        candidate = self.summary(candidate_run, identity, cpu)
        baseline_result = self.result(baseline_run, self.baseline_identity)
        candidate_result = self.result(candidate_run, identity)
        comparison = COMPARE.build_comparison(
            baseline,
            candidate,
            0.90,
            0.20,
            0.15,
            0.20,
            baseline_result,
            candidate_result,
        )
        paths = {
            "baselineSummary": root / "baseline-summary.json",
            "candidateSummary": root / "candidate-summary.json",
            "baselineResult": root / "baseline-result.json",
            "candidateResult": root / "candidate-result.json",
            "comparison": root / "comparison.json",
        }
        for name, value in (
            ("baselineSummary", baseline),
            ("candidateSummary", candidate),
            ("baselineResult", baseline_result),
            ("candidateResult", candidate_result),
            ("comparison", comparison),
        ):
            self.write(paths[name], value)
        return {name: path.relative_to(self.root).as_posix() for name, path in paths.items()}

    def manifest(self) -> pathlib.Path:
        identities = {
            "baseline": f"artifact-sha256:{'b' * 64}",
            "reference": f"artifact-sha256:{'c' * 64}",
            "wrong": f"artifact-sha256:{'d' * 64}",
        }
        cpu = {"baseline": 20.0, "reference": 11.0, "wrong": 18.0}
        variants = {
            role: [
                self.observation(role, ordinal, cpu[role], identities[role])
                for ordinal in (1, 2)
            ]
            for role in ("baseline", "reference", "wrong")
        }
        value = {
            "schema": "agentlab.case_performance_calibration_manifest.v1",
            "caseId": self.case_id,
            "sourceSetSha256": "e" * 64,
            "functionalCalibrationSha256": "f" * 64,
            "feedbackPerformanceEvidence": {
                "environmentIdentity": self.environment,
                "performancePolicySha256": self.policy_sha,
                "profileWorkloadSha256": self.workload_sha,
                "metric": "appCpuUsagePercent",
                "statistic": "mean",
                "unit": "reported-percent",
                "direction": "lower",
                "bestParticipantId": "strong",
                "worstParticipantId": "medium",
                "meanDifference": 20.0,
                "rangesSeparated": True,
                "authority": {
                    "functional": "none",
                    "relativePerformance": "smartperf-emulator-proxy",
                    "absolutePowerThermal": "unavailable-on-emulator",
                },
            },
            "variants": variants,
            "automaticPromotion": False,
        }
        path = self.root / "manifest.json"
        self.write(path, value)
        return path

    def run_composer(self, manifest: pathlib.Path, output: pathlib.Path):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--manifest", str(manifest), "--output", str(output)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_repeatable_functional_and_performance_variants_qualify(self) -> None:
        manifest = self.manifest()
        output = self.root / "case-performance-calibration.json"
        completed = self.run_composer(manifest, output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(output.read_text())
        self.assertEqual(value["schema"], "agentlab.case_performance_calibration.v1")
        self.assertTrue(value["functionalOracleQualified"])
        self.assertTrue(value["repeatabilityQualified"])
        self.assertEqual(
            {row["role"]: row["expectedDecision"] for row in value["variants"]},
            {
                "baseline": "performance-regression-candidate",
                "reference": "within-relative-guardrails",
                "wrong": "performance-regression-candidate",
            },
        )
        self.assertFalse(value["automaticPromotion"])

    def test_changed_raw_summary_is_rejected(self) -> None:
        manifest = self.manifest()
        path = self.root / "baseline/1/candidate-summary.json"
        value = json.loads(path.read_text())
        value["canonicalMetrics"]["appCpuUsagePercent"]["mean"] = 10.0
        self.write(path, value)
        completed = self.run_composer(manifest, self.root / "output.json")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("comparison differs from raw evidence", completed.stderr)

    def test_single_observation_per_role_is_rejected(self) -> None:
        manifest = self.manifest()
        value = json.loads(manifest.read_text())
        value["variants"]["wrong"] = value["variants"]["wrong"][:1]
        self.write(manifest, value)
        completed = self.run_composer(manifest, self.root / "output.json")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("requires at least two observations", completed.stderr)

    def test_symlinked_raw_evidence_is_rejected(self) -> None:
        manifest = self.manifest()
        path = self.root / "baseline/1/candidate-summary.json"
        retained = self.root / "retained-candidate-summary.json"
        path.rename(retained)
        path.symlink_to(retained)
        completed = self.run_composer(manifest, self.root / "output.json")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("must be a regular file", completed.stderr)

    def test_output_must_share_portable_manifest_directory(self) -> None:
        manifest = self.manifest()
        output = self.root / "nested/output.json"
        completed = self.run_composer(manifest, output)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("must share the manifest directory", completed.stderr)

    def test_candidate_cannot_equal_performance_baseline(self) -> None:
        self.baseline_identity = f"artifact-sha256:{'c' * 64}"
        manifest = self.manifest()
        completed = self.run_composer(manifest, self.root / "output.json")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("candidate artifact equals the performance baseline", completed.stderr)

    def test_public_schemas_identify_manifest_requirement_and_output(self) -> None:
        expected = {
            "case-performance-calibration-manifest.schema.json":
                "agentlab.case_performance_calibration_manifest.v1",
            "case-performance-requirement.schema.json":
                "agentlab.case_performance_requirement.v1",
            "case-performance-calibration.schema.json":
                "agentlab.case_performance_calibration.v1",
        }
        for filename, schema_name in expected.items():
            value = json.loads((ROOT / "schemas" / filename).read_text())
            self.assertEqual(value["properties"]["schema"]["const"], schema_name)


if __name__ == "__main__":
    unittest.main()
