from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run-harmony-evaluation-case.py"


SYNTHETIC_RUNNER = r'''#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import pathlib

parser = argparse.ArgumentParser()
parser.add_argument("command")
for name in ("tools-root", "image-root", "instance-path", "instance", "hdc-port",
             "hap", "bundle", "ability", "output", "ui-scenario", "task-id",
             "source-id", "profile-run-id", "environment-id", "performance-policy",
             "profile-workload", "boot-mode", "profile-samples"):
    parser.add_argument("--" + name, required=True)
parser.add_argument("--reset-app-data", action="store_true")
args = parser.parse_args()
marker = os.environ.get("SYNTHETIC_MARKER")
if marker:
    pathlib.Path(marker).write_text("called")

def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

source_id = "source-set-sha256:" + "f" * 64 if os.environ.get("SYNTHETIC_BAD_SOURCE") else args.source_id
output = pathlib.Path(args.output)
output.mkdir(parents=True)
result = {
    "schema": "agentlab.harmony_emulator_case_result.v3",
    "status": "passed",
    "taskId": args.task_id,
    "sourceIdentity": source_id,
    "hapSha256": digest(args.hap),
    "scenarioId": "synthetic-harmony-oracle-v1",
    "scenarioSha256": digest(args.ui_scenario),
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
    "performancePolicySha256": digest(args.performance_policy),
    "profileWorkloadSha256": digest(args.profile_workload),
}
summary = {
    "schema": "agentlab.smartperf_summary.v2",
    "taskId": args.task_id,
    "sourceIdentity": source_id,
    "runId": args.profile_run_id,
    "environmentIdentity": args.environment_id,
    "profileValid": True,
    "sampleCount": int(args.profile_samples),
    "canonicalMetrics": {"appCpuUsagePercent": {"mean": 4.0}, "appPssKiB": {"mean": 100.0}},
    "performancePolicy": {"sha256": digest(args.performance_policy)},
    "profileWorkload": {"sha256": digest(args.profile_workload)},
    "authority": {"absolutePowerThermal": "unavailable-on-emulator"},
}
(output / "result.json").write_text(json.dumps(result))
(output / "smartperf-summary.json").write_text(json.dumps(summary))
'''


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HarmonyEvaluationCaseRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        for name in ("tools", "image", "instance"):
            (self.root / name).mkdir()
        self.runner = self.root / "runner.py"
        self.runner.write_text(SYNTHETIC_RUNNER, encoding="utf-8")
        self.runner.chmod(0o755)
        self.hap = self.root / "case.hap"
        self.hap.write_bytes(b"receipt-bound synthetic Harmony artifact")
        self.scenario = self.root / "scenario.ui"
        self.scenario.write_text("tap\t100\t100\nassert-layout-text\tReady\n", encoding="utf-8")
        self.policy = self.root / "policy.json"
        self.policy.write_text(
            json.dumps({"schema": "agentlab.harmony_performance_policy.v1", "id": "synthetic-policy"}),
            encoding="utf-8",
        )
        self.workload = self.root / "workload.tsv"
        self.workload.write_text(
            "schema\tagentlab.harmony_profile_workload.v1\nworkload\tsynthetic-workload\n",
            encoding="utf-8",
        )
        self.sources = [
            {"id": "app", "repository": "https://example.invalid/app.git", "revision": "a" * 40},
            {"id": "contracts", "repository": "https://example.invalid/contracts.git", "revision": "b" * 40},
        ]
        self.source_set = "c" * 64
        self.case = self.root / "case.json"
        self.case.write_text(
            json.dumps(
                {
                    "schema": "agentlab.multi_repo_evaluation_case.v1",
                    "id": "synthetic-multi-repo-harmony-case",
                    "status": "frozen-calibrated",
                    "sourceSetSha256": self.source_set,
                    "sources": self.sources,
                    "oracle": {"authority": "independent-executable-oracle"},
                    "calibration": {"qualified": True},
                    "automaticPromotion": False,
                }
            ),
            encoding="utf-8",
        )
        self.build = self.root / "build-receipt.json"
        self.build.write_text(
            json.dumps(
                {
                    "schema": "agentlab.harmony_case_build_receipt.v1",
                    "status": "passed",
                    "caseId": "synthetic-multi-repo-harmony-case",
                    "evaluationCaseSha256": digest(self.case),
                    "sourceSetSha256": self.source_set,
                    "sources": self.sources,
                    "hapSha256": digest(self.hap),
                    "buildToolSha256": "d" * 64,
                    "sourceMaterializationSha256": "e" * 64,
                    "buildAuthority": "independent-harmony-build",
                    "automaticPromotion": False,
                }
            ),
            encoding="utf-8",
        )
        self.plan = self.root / "plan.json"
        self.write_plan()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_plan(self, **overrides) -> None:
        value = {
            "schema": "agentlab.harmony_evaluation_run_plan.v1",
            "evaluationCase": {"path": str(self.case), "sha256": digest(self.case)},
            "buildReceipt": {"path": str(self.build), "sha256": digest(self.build)},
            "artifact": {"path": str(self.hap), "sha256": digest(self.hap)},
            "functionalOracle": {
                "path": str(self.scenario),
                "scenarioId": "synthetic-harmony-oracle-v1",
                "sha256": digest(self.scenario),
            },
            "runtime": {
                "runner": str(self.runner),
                "runnerSha256": digest(self.runner),
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
            "performance": {
                "policy": str(self.policy),
                "policySha256": digest(self.policy),
                "workload": str(self.workload),
                "workloadSha256": digest(self.workload),
            },
            "runId": "synthetic-harmony-evaluation-v1",
            "automaticPromotion": False,
        }
        value.update(overrides)
        self.plan.write_text(json.dumps(value), encoding="utf-8")

    def run_case(self, output: pathlib.Path, env: dict[str, str] | None = None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--plan", str(self.plan), "--output", str(output)],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **(env or {})},
        )

    def test_frozen_multi_repo_case_runs_through_bound_hap(self) -> None:
        output = self.root / "evidence"
        completed = self.run_case(output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        binding = json.loads((output / "evaluation-binding.json").read_text())
        result = json.loads((output / "execution/result.json").read_text())
        self.assertEqual(binding["status"], "passed-review-required")
        self.assertEqual(binding["sourceSetSha256"], self.source_set)
        self.assertEqual(binding["hapSha256"], digest(self.hap))
        self.assertEqual(binding["buildReceiptSha256"], digest(self.build))
        self.assertFalse(binding["automaticPromotion"])
        self.assertEqual(
            result["sourceIdentity"],
            f"source-set-sha256:{self.source_set}",
        )

    def test_hap_drift_is_rejected_before_runner(self) -> None:
        plan = json.loads(self.plan.read_text())
        plan["artifact"]["sha256"] = "f" * 64
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        marker = self.root / "runner-called"
        output = self.root / "evidence"
        completed = self.run_case(output, {"SYNTHETIC_MARKER": str(marker)})
        self.assertEqual(completed.returncode, 1)
        self.assertFalse(marker.exists())
        self.assertFalse(output.exists())
        stage = next(self.root.glob(".evidence.stage-*"))
        failure = json.loads((stage / "failure.json").read_text())
        self.assertIn("HAP SHA256 differs from run plan", failure["error"])

    def test_result_source_set_drift_retains_failed_execution(self) -> None:
        output = self.root / "evidence"
        completed = self.run_case(output, {"SYNTHETIC_BAD_SOURCE": "1"})
        self.assertEqual(completed.returncode, 1)
        self.assertFalse(output.exists())
        stage = next(self.root.glob(".evidence.stage-*"))
        failure = json.loads((stage / "failure.json").read_text())
        self.assertIn("sourceIdentity differs", failure["error"])
        self.assertTrue((stage / "execution/result.json").is_file())

    def test_existing_output_is_never_overwritten(self) -> None:
        output = self.root / "evidence"
        output.mkdir()
        marker = output / "marker"
        marker.write_text("keep", encoding="utf-8")
        completed = self.run_case(output)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(marker.read_text(), "keep")
        self.assertEqual(list(self.root.glob(".evidence.stage-*")), [])


if __name__ == "__main__":
    unittest.main()
