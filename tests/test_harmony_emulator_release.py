from __future__ import annotations

import json
import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release/alharmony/harmony-emulator-linux-x64-26.0.0.821.json"
INSTALLER = ROOT / "scripts/agentlab-harmony-emulator.sh"
SCENARIO = ROOT / "examples/harmony-emulator/tutu-cookie-dismiss.ui"
PROFILE_WORKLOAD = ROOT / "examples/harmony-emulator/tutu-scroll.profile"
PERFORMANCE_POLICY = ROOT / "examples/harmony-emulator/emulator-cpu-memory-relative.performance.json"
ASSET_MODEL = ROOT / "crates/agentlab_code_analysis/src/asset_model.rs"
CONTROLLED_REGRESSION = (
    ROOT / "release/qualifications/harmony-performance-controlled-regression-v1"
)


class HarmonyEmulatorReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.value = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_vendor_assets_are_exactly_scoped_for_authorized_publication(self) -> None:
        self.assertEqual(
            self.value["schema"], "agentlab.harmony_emulator_external_bundle.v1"
        )
        distribution = self.value["distribution"]
        self.assertTrue(distribution["publicBinaryRedistribution"])
        self.assertEqual(
            distribution["status"], "authorized-for-internal-use-release"
        )
        self.assertEqual(self.value["publicationMode"], "authorized-release-assets")

    def test_verified_asset_identities_are_exact(self) -> None:
        assets = {item["id"]: item for item in self.value["assets"]}
        self.assertEqual(assets["command-line-tools"]["bytes"], 932070897)
        self.assertEqual(
            assets["command-line-tools"]["sha256"],
            "ad1eb9a255b6fc6f022a646bd536ef230d66e47aea1f9177a793924b83ebb649",
        )
        self.assertEqual(assets["phone-system-image"]["bytes"], 1568108769)
        self.assertEqual(
            assets["phone-system-image"]["sha256"],
            "75c537cb6dc62291f96f0f247c148de653c9c6633c4dc5b0c34cc254909ae671",
        )
        for asset in assets.values():
            self.assertIn("--long=31", asset["compression"])
            self.assertNotIn("url", asset)

    def test_scope_is_x86_kvm_and_does_not_claim_arm_translation(self) -> None:
        self.assertEqual(self.value["platform"], "linux-x64")
        self.assertEqual(self.value["capabilities"]["imageAbi"], "x86")
        self.assertEqual(self.value["capabilities"]["acceleration"], "KVM")
        limitations = " ".join(self.value["limitations"])
        self.assertIn("ARM native", limitations)
        self.assertIn("application-specific semantic Oracle calibration", limitations)
        self.assertIn("Absolute power and thermal", limitations)

    def test_installer_is_fail_closed(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("zstd -t --long=31", source)
        self.assertIn("--acknowledge-vendor-agreements", source)
        self.assertIn("refusing to overwrite existing install root", source)
        self.assertIn("/dev/kvm", source)

    def test_run_case_emits_functional_and_profile_evidence(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("agentlab.harmony_emulator_case_result.v1", source)
        self.assertIn("shell uitest dumpLayout", source)
        self.assertIn('! grep -iF "failed"', source)
        self.assertIn('install -r "$hap"', source)
        self.assertIn('shell bm dump -n "$bundle"', source)
        self.assertIn("shell uitest uiInput swipe 630 2400 630 600 1000", source)
        self.assertIn('shell aa start -a "$ability" -b "$bundle"', source)
        self.assertIn('grep -F "start ability successfully"', source)
        self.assertIn('shell ps -A', source)
        self.assertIn('process_hint=${bundle#com.}', source)
        self.assertIn('process_attempt" -le 15', source)
        self.assertIn("-screenshot", source)
        self.assertIn('screenshot_attempt" -le 10', source)
        self.assertIn("SP_daemon", source)
        self.assertIn('"powerThermalAuthority":"unavailable_on_emulator"', source)
        self.assertIn("refusing to overwrite existing output", source)

    def test_run_case_supports_bounded_ui_oracles(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        scenario = SCENARIO.read_text(encoding="utf-8")
        self.assertTrue(scenario.startswith("schema\tagentlab.harmony_ui_scenario.v1\n"))
        for operation in ["wait-text", "tap", "sleep", "assert-text", "assert-no-text"]:
            self.assertIn(operation, scenario)
        self.assertIn("agentlab.harmony_emulator_case_result.v2", source)
        self.assertIn("--ui-scenario", source)
        self.assertIn("--reset-app-data", source)
        self.assertIn("ui-actions.tsv", source)
        self.assertIn("ui-checks.tsv", source)
        self.assertIn('"oracleStatus":"%s"', source)
        self.assertIn('"assessmentStatus":"%s"', source)
        self.assertIn('"infrastructureAvailable":%s', source)
        self.assertIn('"subjectTaskSucceeded":%s', source)
        self.assertIn("--profile-run-id", source)
        self.assertIn("--environment-id", source)
        self.assertIn("summarize-smartperf.py", source)
        self.assertIn('[ "$source_id" = "artifact-sha256:$hap_sha" ]', source)
        self.assertIn('"profileRunId":"%s"', source)
        self.assertIn('"environmentIdentity":"%s"', source)
        self.assertIn('"profileSummaryStatus":"%s"', source)
        self.assertIn('infrastructure_failure "UI layout dump failed"', source)
        self.assertIn('oracle_failure "UI oracle check failed: $a"', source)

    def test_run_case_binds_policy_and_dynamic_workload_to_profile_window(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        workload = PROFILE_WORKLOAD.read_text(encoding="utf-8")
        policy = json.loads(PERFORMANCE_POLICY.read_text(encoding="utf-8"))
        self.assertIn("--performance-policy", source)
        self.assertIn("--profile-workload", source)
        self.assertIn("run_profile_workload", source)
        self.assertIn("profile-workload-actions.tsv", source)
        self.assertIn("agentlab.harmony_emulator_case_result.v3", source)
        self.assertTrue(workload.startswith("schema\tagentlab.harmony_profile_workload.v1\n"))
        self.assertIn("swipe\t", workload)
        self.assertEqual(policy["schema"], "agentlab.harmony_performance_policy.v1")
        self.assertEqual(
            [row["metric"] for row in policy["requiredMetrics"]],
            ["appCpuUsagePercent", "appPssKiB"],
        )
        self.assertIn("fps", policy["observedOnlyMetrics"])
        self.assertEqual(
            policy["authority"]["absolutePowerThermal"],
            "unavailable-on-emulator",
        )

    def test_asset_model_exports_harmony_evaluation_instances(self) -> None:
        source = ASSET_MODEL.read_text(encoding="utf-8")
        self.assertIn("agentlab.harmony_emulator_case_result.v2", source)
        self.assertIn('"device_assessments"', source)
        self.assertIn('"subjectTaskSucceeded":result["subjectTaskSucceeded"]', source)
        self.assertIn("operator-owned-device-runner", source)
        self.assertIn("operator-owned-ui-oracle", source)
        self.assertIn("sourceIdentity must bind the exact HAP", source)
        self.assertIn('"evidence_files"', source)

    def test_manifest_claims_only_the_newly_qualified_case_scope(self) -> None:
        operations = self.value["capabilities"]["validatedOperations"]
        for operation in [
            "hdc-connect",
            "hap-install",
            "bundle-query",
            "ability-launch",
            "process-check",
            "screenshot",
            "smartperf-proxy-profile",
            "declarative-ui-actions",
            "layout-text-oracle",
            "agentlab-evaluation-instance-export",
        ]:
            self.assertIn(operation, operations)
        self.assertNotIn("absolute-power", operations)
        self.assertNotIn("thermal", operations)

    def test_real_controlled_regression_replays_into_non_ready_difficulty(self) -> None:
        comparison_path = CONTROLLED_REGRESSION / "smartperf-comparison.json"
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        calibration = json.loads(
            (CONTROLLED_REGRESSION / "performance-calibration.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            hashlib.sha256(comparison_path.read_bytes()).hexdigest(),
            "eb875ee462cfc3ce6cac1dcf73a35cbf1e509f8c14d3e3579c02819e056cee10",
        )
        self.assertEqual(comparison["decision"], "performance-regression-candidate")
        self.assertTrue(comparison["functionalGate"]["passed"])
        self.assertEqual(
            next(row for row in comparison["metrics"] if row["metric"] == "appPssKiB")[
                "status"
            ],
            "regressed",
        )
        self.assertEqual(
            calibration["candidate"]["controlledMutation"]["bytes"],
            64 * 1024 * 1024,
        )
        repeat_comparison_path = CONTROLLED_REGRESSION / "smartperf-repeat-comparison.json"
        repeat_comparison = json.loads(repeat_comparison_path.read_text(encoding="utf-8"))
        self.assertEqual(
            hashlib.sha256(repeat_comparison_path.read_bytes()).hexdigest(),
            "707432cefa5db06b5642bb52ace25f68c5e5edeb4c0e33e8025154da27188097",
        )
        self.assertEqual(repeat_comparison["decision"], "performance-regression-candidate")
        self.assertTrue(repeat_comparison["functionalGate"]["passed"])
        self.assertEqual(
            next(
                row
                for row in repeat_comparison["metrics"]
                if row["metric"] == "appPssKiB"
            )["status"],
            "regressed",
        )
        with tempfile.TemporaryDirectory() as raw:
            output = pathlib.Path(raw) / "transaction.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/build-cbgroom-flywheel-transaction.py"),
                    "--evidence",
                    str(CONTROLLED_REGRESSION),
                    "--revision",
                    "0" * 40,
                    "--run-id",
                    "controlled-regression-replay",
                    "--github-repository",
                    "example/agentlab",
                    "--caller-person-id",
                    "person-test",
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output.read_text())
            rows = [
                operation["row"]
                for table in payload["arguments"]["tables"]
                for operation in table["operations"]
            ]
            difficulty = next(
                row
                for row in rows
                if row.get("dimensionId") == "functionally-correct-performance-regression"
            )
            self.assertFalse(difficulty["verificationContract"]["caseReady"])
            self.assertFalse(difficulty["automaticPromotion"])
            self.assertEqual(
                difficulty["performanceCalibration"]["id"],
                "tutu-retained-memory-64m-v1",
            )
            self.assertEqual(
                difficulty["verificationContract"]["verified"],
                ["repeatable-emulator-regression"],
            )
            self.assertNotIn(
                "repeatable-emulator-regression",
                difficulty["verificationContract"]["required"],
            )
            self.assertEqual(
                difficulty["performanceCalibration"]["repeatability"][
                    "consistentRegressedMetrics"
                ],
                ["appPssKiB"],
            )
            self.assertEqual(len(difficulty["evidenceIds"]), 11)

    def test_real_repeatability_evidence_fails_closed_when_tampered(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            evidence = pathlib.Path(raw) / "evidence"
            shutil.copytree(CONTROLLED_REGRESSION, evidence)
            repeat_summary_path = evidence / "smartperf-candidate-repeat-summary.json"
            repeat_summary = json.loads(repeat_summary_path.read_text(encoding="utf-8"))
            repeat_summary["canonicalMetrics"]["appPssKiB"]["mean"] = 170392.0
            repeat_summary_path.write_text(json.dumps(repeat_summary), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/build-cbgroom-flywheel-transaction.py"),
                    "--evidence",
                    str(evidence),
                    "--revision",
                    "0" * 40,
                    "--run-id",
                    "tampered-repeatability-replay",
                    "--github-repository",
                    "example/agentlab",
                    "--caller-person-id",
                    "person-test",
                    "--output",
                    str(pathlib.Path(raw) / "transaction.json"),
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("repeat summary digest differs", completed.stderr)


if __name__ == "__main__":
    unittest.main()
