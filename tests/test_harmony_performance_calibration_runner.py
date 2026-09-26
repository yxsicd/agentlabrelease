from __future__ import annotations

import hashlib
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run-harmony-performance-calibration.py"
COMPARATOR = ROOT / "scripts/compare-smartperf.py"


SYNTHETIC_RUNNER = r'''#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import pathlib
import sys

parser = argparse.ArgumentParser()
parser.add_argument("command")
for name in ("tools-root", "image-root", "instance-path", "instance", "hdc-port",
             "hap", "bundle", "ability", "output", "ui-scenario", "task-id",
             "source-id", "profile-run-id", "environment-id", "performance-policy",
             "profile-workload", "boot-mode", "profile-samples"):
    parser.add_argument("--" + name, required=True)
parser.add_argument("--reset-app-data", action="store_true")
args = parser.parse_args()
if os.environ.get("SYNTHETIC_FAIL_RUN") == args.profile_run_id:
    print("synthetic requested failure", file=sys.stderr)
    raise SystemExit(19)

def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

output = pathlib.Path(args.output)
output.mkdir(parents=True)
policy = json.loads(pathlib.Path(args.performance_policy).read_text())
workload_id = next(
    line.split("\t", 1)[1]
    for line in pathlib.Path(args.profile_workload).read_text().splitlines()
    if line.startswith("workload\t")
)
policy_identity = {
    "id": policy["id"],
    "sha256": digest(args.performance_policy),
    "requiredMetrics": policy["requiredMetrics"],
}
workload_identity = {"id": workload_id, "sha256": digest(args.profile_workload)}
pss = 100.0 if "baseline" in args.profile_run_id else (140.0 if args.profile_run_id.endswith("v1") else 138.0)
summary = {
    "schema": "agentlab.smartperf_summary.v2",
    "taskId": args.task_id,
    "sourceIdentity": args.source_id,
    "runId": args.profile_run_id,
    "environmentIdentity": args.environment_id,
    "sampleCount": int(args.profile_samples),
    "profileValid": True,
    "canonicalMetrics": {
        "appCpuUsagePercent": {"mean": 5.0},
        "appPssKiB": {"mean": pss},
    },
    "performancePolicy": policy_identity,
    "profileWorkload": workload_identity,
    "authority": {"absolutePowerThermal": "unavailable-on-emulator"},
}
scenario_sha = digest(args.ui_scenario)
result = {
    "schema": "agentlab.harmony_emulator_case_result.v3",
    "status": "passed",
    "taskId": args.task_id,
    "sourceIdentity": args.source_id,
    "hapSha256": args.source_id.removeprefix("artifact-sha256:"),
    "scenarioId": "synthetic-oracle-v1",
    "scenarioSha256": scenario_sha,
    "oracleStatus": "passed",
    "assessmentStatus": "assessed",
    "infrastructureAvailable": True,
    "subjectTaskSucceeded": True,
    "failureClass": "none",
    "profileRunId": args.profile_run_id,
    "environmentIdentity": args.environment_id,
    "profileStatus": "collected",
    "profileSummaryStatus": "normalized",
    "powerThermalAuthority": "unavailable_on_emulator",
    "performancePolicyId": policy_identity["id"],
    "performancePolicySha256": policy_identity["sha256"],
    "profileWorkloadId": workload_identity["id"],
    "profileWorkloadSha256": workload_identity["sha256"],
}
(output / "smartperf-summary.json").write_text(json.dumps(summary))
(output / "result.json").write_text(json.dumps(result))
'''


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HarmonyPerformanceCalibrationRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.runner = self.root / "synthetic-runner.py"
        self.runner.write_text(SYNTHETIC_RUNNER, encoding="utf-8")
        self.runner.chmod(0o755)
        self.baseline = self.root / "baseline.hap"
        self.candidate = self.root / "candidate.hap"
        self.baseline.write_bytes(b"synthetic baseline")
        self.candidate.write_bytes(b"synthetic candidate")
        self.scenario = self.root / "scenario.ui"
        self.scenario.write_text("tap\t1\t1\n", encoding="utf-8")
        self.policy = self.root / "policy.json"
        self.policy.write_text(
            json.dumps(
                {
                    "schema": "agentlab.harmony_performance_policy.v1",
                    "id": "synthetic-cpu-memory-v1",
                    "requiredMetrics": [
                        {
                            "metric": "appCpuUsagePercent",
                            "statistic": "mean",
                            "direction": "lower",
                            "maximumRelativeIncrease": 0.2,
                        },
                        {
                            "metric": "appPssKiB",
                            "statistic": "mean",
                            "direction": "lower",
                            "maximumRelativeIncrease": 0.15,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.workload = self.root / "workload.tsv"
        self.workload.write_text(
            "schema\tagentlab.harmony_profile_workload.v1\nworkload\tsynthetic-workload-v1\n",
            encoding="utf-8",
        )
        for name in ("tools", "image", "instance"):
            (self.root / name).mkdir()
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps(self.plan_value()), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def plan_value(self) -> dict:
        return {
            "schema": "agentlab.harmony_performance_calibration_plan.v1",
            "id": "synthetic-controlled-regression-v1",
            "taskId": "synthetic-harmony-case",
            "harnessRevision": "a" * 40,
            "applicationSource": {
                "repository": "https://example.invalid/application.git",
                "revision": "b" * 40,
                "path": "entry/src/main/ets/pages/Index.ets",
            },
            "baseline": {
                "hap": str(self.baseline),
                "sourceIdentity": f"artifact-sha256:{digest(self.baseline)}",
            },
            "candidate": {
                "hap": str(self.candidate),
                "sourceIdentity": f"artifact-sha256:{digest(self.candidate)}",
                "controlledMutation": {
                    "id": "synthetic-retained-memory-v1",
                    "kind": "retained-memory",
                    "bytes": 67108864,
                    "sourcePath": "entry/src/main/ets/pages/Index.ets",
                    "baseSourceFileSha256": "c" * 64,
                    "candidateSourceFileSha256": "d" * 64,
                },
            },
            "functionalOracle": {
                "path": str(self.scenario),
                "scenarioId": "synthetic-oracle-v1",
                "scenarioSha256": digest(self.scenario),
            },
            "runtime": {
                "runner": str(self.runner),
                "comparator": str(COMPARATOR),
                "toolsRoot": str(self.root / "tools"),
                "imageRoot": str(self.root / "image"),
                "instancePath": str(self.root / "instance"),
                "instance": "synthetic-phone",
                "hdcPort": 15555,
                "bundle": "com.example.synthetic",
                "ability": "EntryAbility",
                "environmentIdentity": "synthetic:emulator:phone-x86",
                "bootMode": "coldboot",
                "profileSamples": 3,
            },
            "performancePolicy": str(self.policy),
            "profileWorkload": str(self.workload),
            "candidateRuns": 2,
            "expectedDecision": "performance-regression-candidate",
            "automaticPromotion": False,
        }

    def run_calibration(self, output: pathlib.Path, env: dict[str, str] | None = None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--plan", str(self.plan), "--output", str(output)],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **(env or {})},
        )

    def test_reproduced_regression_is_retained_without_promotion(self) -> None:
        output = self.root / "evidence"
        completed = self.run_calibration(output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        calibration = json.loads((output / "performance-calibration.json").read_text())
        receipt = json.loads((output / "calibration-run.json").read_text())
        self.assertEqual(calibration["repeatability"]["status"], "reproduced")
        self.assertEqual(
            calibration["repeatability"]["consistentRegressedMetrics"],
            ["appPssKiB"],
        )
        self.assertFalse(calibration["automaticPromotion"])
        self.assertFalse(receipt["automaticPromotion"])
        self.assertEqual(
            [row["exitCode"] for row in receipt["phases"]],
            [0, 0, 0, 0, 0, 0, 0],
        )
        self.assertEqual(receipt["phases"][1]["phase"], "port-release-after-baseline")
        self.assertEqual(receipt["phases"][3]["phase"], "port-release-after-candidate-1")
        self.assertTrue((output / "raw/candidate-02/result.json").is_file())

    def test_failed_candidate_retains_partial_stage_and_no_final_output(self) -> None:
        output = self.root / "failed-evidence"
        completed = self.run_calibration(
            output,
            {"SYNTHETIC_FAIL_RUN": "synthetic-harmony-case-candidate-v2"},
        )
        self.assertEqual(completed.returncode, 1)
        self.assertFalse(output.exists())
        stages = list(self.root.glob(".failed-evidence.stage-*"))
        self.assertEqual(len(stages), 1)
        failure = json.loads((stages[0] / "failure.json").read_text())
        self.assertEqual(failure["status"], "failed")
        self.assertEqual(
            [row["exitCode"] for row in failure["phases"]], [0, 0, 0, 0, 19]
        )
        self.assertTrue((stages[0] / "raw/baseline/result.json").is_file())
        self.assertTrue((stages[0] / "raw/candidate-01/result.json").is_file())

    def test_existing_output_is_never_overwritten(self) -> None:
        output = self.root / "existing"
        output.mkdir()
        marker = output / "marker"
        marker.write_text("keep", encoding="utf-8")
        completed = self.run_calibration(output)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
        self.assertEqual(list(self.root.glob(".existing.stage-*")), [])

    def test_hap_identity_drift_fails_before_any_runner_phase(self) -> None:
        value = self.plan_value()
        value["candidate"]["sourceIdentity"] = f"artifact-sha256:{'f' * 64}"
        self.plan.write_text(json.dumps(value), encoding="utf-8")
        output = self.root / "identity-drift"
        completed = self.run_calibration(output)
        self.assertEqual(completed.returncode, 1)
        stage = next(self.root.glob(".identity-drift.stage-*"))
        failure = json.loads((stage / "failure.json").read_text())
        self.assertIn("candidate sourceIdentity differs", failure["error"])
        self.assertEqual(failure["phases"], [])

    def test_bound_hdc_port_stops_the_next_cold_run(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            for port in range(16555, 14999, -1):
                try:
                    listener.bind(("127.0.0.1", port))
                    break
                except OSError:
                    continue
            else:
                self.fail("no test port available in the runner's HDC range")
            listener.listen()
            value = self.plan_value()
            value["runtime"]["hdcPort"] = port
            value["runtime"]["portReleaseTimeoutSeconds"] = 1
            self.plan.write_text(json.dumps(value), encoding="utf-8")
            output = self.root / "occupied-port"
            completed = self.run_calibration(output)
        self.assertEqual(completed.returncode, 1)
        stage = next(self.root.glob(".occupied-port.stage-*"))
        failure = json.loads((stage / "failure.json").read_text())
        self.assertIn("did not release", failure["error"])
        self.assertEqual(
            [row["phase"] for row in failure["phases"]],
            ["baseline", "port-release-after-baseline"],
        )
        self.assertEqual(failure["phases"][-1]["exitCode"], 1)


if __name__ == "__main__":
    unittest.main()
