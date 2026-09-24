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
SCRIPT = ROOT / "scripts/compose-harmony-assessed-decision.py"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


COLLECTOR = load_module("compound_collect", ROOT / "scripts/collect-case-attempts.py")
SCORER = load_module("compound_score", ROOT / "scripts/score-case-discrimination.py")
FEEDBACK = load_module("compound_feedback", ROOT / "scripts/derive-assessment-feedback.py")


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class HarmonyCompoundAssessmentTests(unittest.TestCase):
    case_id = "compound-harmony-case"
    source_set = "a" * 64

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_json(self, path: pathlib.Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n")

    def make_static(self, name: str, participant: str) -> pathlib.Path:
        root = self.root / name / "static"
        state = {"app/Index.ets": {"sha256": "1" * 64, "byteLength": 1, "unixMode": 420}}
        self.write_json(root / "final-source-state.json", state)
        common = {
            "taskId": self.case_id,
            "sourceSetSha256": self.source_set,
            "participantId": participant,
            "assessmentStatus": "assessed",
            "infrastructureAvailable": True,
            "subjectTaskSucceeded": True,
        }
        phases = [
            {
                "stageId": "static",
                "participantCompleted": True,
                "changedPaths": ["app/Index.ets"],
                "changedPathCount": 1,
                "unauthorizedPaths": [],
                "unauthorizedPathCount": 0,
                "scopeValid": True,
                "oraclePass": True,
                "participantDurationMs": 10,
                "oracleDurationMs": 2,
                "stageDurationMs": 13,
                "cumulativeCheckCount": 1,
            }
        ]
        process = {
            "schema": "agentlab.assessment_process_measurement.v1",
            "stageCount": 1,
            "participantCompletedStageCount": 1,
            "oracleExecutedStageCount": 1,
            "oraclePassedStageCount": 1,
            "scopeViolationStageCount": 0,
            "changedPathCount": 1,
            "unauthorizedPathCount": 0,
            "oracleRecoveryCount": 0,
            "oracleRegressionCount": 0,
            "participantDurationMs": 10,
            "oracleDurationMs": 2,
            "stageDurationMs": 13,
            "attemptDurationMs": 15,
            "processMeasurementQualified": True,
        }
        self.write_json(
            root / "summary.json",
            {
                **common,
                "schema": "agentlab.multi_repo_assessment_summary.v1",
                "finalWorkspaceSha256": canonical(state),
                "stages": phases,
                "durationMs": 15,
                "processMeasurement": process,
            },
        )
        self.write_json(
            root / "decision-package.json",
            {
                **common,
                "schema": "agentlab.harness_decision_package.v1",
                "phaseVerdicts": phases,
                "processMeasurement": process,
                "automaticPromotion": False,
            },
        )
        return root

    def make_loop(self, name: str, static: pathlib.Path, participant: str, passed: bool) -> pathlib.Path:
        root = self.root / name / "loop"
        result_path = root / "assessment/execution/result.json"
        hap = "3" * 64
        self.write_json(
            result_path,
            {
                "schema": "agentlab.harmony_emulator_case_result.v3",
                "status": "passed" if passed else "failed",
                "taskId": self.case_id,
                "sourceSetSha256": self.source_set,
                "sourceIdentity": f"artifact-sha256:{hap}",
                "hapSha256": hap,
                "oracleStatus": "passed" if passed else "failed",
                "assessmentStatus": "assessed",
                "infrastructureAvailable": True,
                "subjectTaskSucceeded": passed,
                "failureClass": "none" if passed else "oracle",
                "powerThermalAuthority": "unavailable_on_emulator",
            },
        )
        execution = root / "assessment/execution"
        (execution / "ui-actions.tsv").write_text("1\tlaunch\tapp\n")
        (execution / "ui-checks.tsv").write_text(
            f"ready\t{str(passed).lower()}\ttext\tready\n"
        )
        if passed:
            (execution / "profile-workload-actions.tsv").write_text(
                "1\tswipe\t1,2,3,4,5\n"
            )
            self.write_json(
                execution / "smartperf-summary.json",
                {"profileValid": True, "sampleCount": 3},
            )
        evidence = {
            "uiActions": {
                "sha256": digest(execution / "ui-actions.tsv"),
                "rowCount": 1,
            },
            "uiChecks": {
                "sha256": digest(execution / "ui-checks.tsv"),
                "rowCount": 1,
            },
            "profileWorkloadActions": (
                {
                    "sha256": digest(execution / "profile-workload-actions.tsv"),
                    "rowCount": 1,
                }
                if passed
                else None
            ),
        }
        assessed = {
            "participantId": participant,
            "subjectWorkspaceSha256": json.loads((static / "summary.json").read_text())["finalWorkspaceSha256"],
            "assessmentSummarySha256": digest(static / "summary.json"),
            "assessmentDecisionSha256": digest(static / "decision-package.json"),
            "finalSourceStateSha256": digest(static / "final-source-state.json"),
        }
        status = "passed-review-required" if passed else "assessed-failure-review-required"
        binding_path = root / "assessment/evaluation-binding.json"
        self.write_json(
            binding_path,
            {
                "schema": "agentlab.harmony_evaluation_binding.v1",
                "status": status,
                "caseId": self.case_id,
                "sourceSetSha256": self.source_set,
                "buildAuthority": "independent-harmony-assessed-workspace-build",
                "subjectTaskSucceeded": passed,
                "failureClass": "none" if passed else "oracle",
                "hapSha256": hap,
                "resultSha256": digest(result_path),
                "environmentIdentity": "hwlinux:phone-x86",
                "performancePolicySha256": "4" * 64,
                "profileWorkloadSha256": "5" * 64,
                "smartperfSummarySha256": (
                    digest(execution / "smartperf-summary.json") if passed else None
                ),
                "deviceProcessMeasurement": {
                    "schema": "agentlab.harmony_device_process_measurement.v1",
                    "runnerDurationMs": 20,
                    "uiActionCount": 1,
                    "uiCheckCount": 1,
                    "profileWorkloadActionCount": 1 if passed else 0,
                    "smartPerfSampleCount": 3 if passed else 0,
                    "functionalOraclePass": passed,
                    "profileCollected": passed,
                    "evidence": evidence,
                },
                "assessedWorkspace": assessed,
                "automaticPromotion": False,
            },
        )
        self.write_json(
            root / "loop-receipt.json",
            {
                "schema": "agentlab.harmony_evaluation_loop_receipt.v1",
                "status": status,
                "caseId": self.case_id,
                "sourceSetSha256": self.source_set,
                "buildAuthority": "independent-harmony-assessed-workspace-build",
                "subjectTaskSucceeded": passed,
                "failureClass": "none" if passed else "oracle",
                "hapSha256": hap,
                "evaluationBindingSha256": digest(binding_path),
                "assessedWorkspace": assessed,
                "processMeasurement": {
                    "schema": "agentlab.harmony_evaluation_loop_process_measurement.v1",
                    "buildDurationMs": 5,
                    "emulatorAssessmentDurationMs": 25,
                    "runnerDurationMs": 20,
                    "totalDurationMs": 30,
                },
                "automaticPromotion": False,
            },
        )
        return root

    def compose(self, name: str, participant: str, passed: bool) -> pathlib.Path:
        static = self.make_static(name, participant)
        loop = self.make_loop(name, static, participant, passed)
        output = self.root / "compound" / name
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--static-assessment",
                str(static),
                "--harmony-loop",
                str(loop),
                "--output",
                str(output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return output

    def calibration(self) -> dict:
        def variant(first: bool, second: bool) -> dict:
            return {
                "sourceSha256": "7" * 64,
                "stages": {
                    "static": {"pass": first},
                    "harmony-device": {"pass": second},
                },
            }

        return {
            "schema": "agentlab.multi_repo_calibration.v1",
            "candidateId": "difficulty-compound",
            "sourceSetSha256": self.source_set,
            "oracleSha256": "8" * 64,
            "infrastructureAvailable": True,
            "variants": {
                "baseline": variant(False, False),
                "reference": variant(True, True),
                "wrong-device": variant(True, False),
            },
        }

    def test_device_oracle_failure_is_valid_compound_agent_failure(self) -> None:
        output = self.compose("weak", "weak", False)
        decision = json.loads((output / "decision-package.json").read_text())
        receipt = json.loads((output / "composition-receipt.json").read_text())
        self.assertFalse(decision["subjectTaskSucceeded"])
        self.assertEqual(decision["phaseVerdicts"][-1]["stageId"], "harmony-device")
        self.assertFalse(decision["phaseVerdicts"][-1]["oraclePass"])
        self.assertEqual(decision["processMeasurement"]["stageCount"], 2)
        self.assertEqual(decision["processMeasurement"]["oracleRegressionCount"], 1)
        self.assertEqual(receipt["status"], "assessed-review-required")
        self.assertFalse(receipt["automaticPromotion"])

    def test_compound_attempts_score_and_derive_device_difficulty(self) -> None:
        strong = self.compose("strong", "strong", True)
        weak = self.compose("weak", "weak", False)
        calibration_path = self.root / "calibration.json"
        self.write_json(calibration_path, self.calibration())
        manifest = {
            "schema": "agentlab.case_attempt_collection.v2",
            "sourceSetSha256": self.source_set,
            "methodRevision": "9" * 40,
            "cases": [
                {
                    "id": self.case_id,
                    "calibration": "calibration.json",
                    "attempts": [
                        {"attemptId": "strong-1", "participantId": "strong", "evidence": strong.relative_to(self.root).as_posix()},
                        {"attemptId": "weak-1", "participantId": "weak", "evidence": weak.relative_to(self.root).as_posix()},
                    ],
                }
            ],
        }
        collected = COLLECTOR.build_input(manifest, self.root.resolve())
        report = SCORER.build_report(collected, 1, 0.6)
        self.assertTrue(report["ranking"][0]["eligible"])
        self.assertTrue(report["ranking"][0]["processAwareEligible"])
        case = {
            "schema": "agentlab.multi_repo_evaluation_case.v1",
            "id": self.case_id,
            "status": "frozen-calibrated",
            "sourceSetSha256": self.source_set,
            "difficultyId": "difficulty-compound",
            "calibration": {"qualified": True},
            "automaticPromotion": False,
        }
        feedback = FEEDBACK.build_feedback(case, collected, report, self.root)
        candidates = [row for row in feedback["candidates"] if row["stageId"] == "harmony-device"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["failureMode"], "oracle-failure")
        self.assertFalse(candidates[0]["verificationContract"]["caseReady"])

    def test_static_decision_digest_drift_is_rejected(self) -> None:
        static = self.make_static("drift", "weak")
        loop = self.make_loop("drift", static, "weak", False)
        decision = json.loads((static / "decision-package.json").read_text())
        decision["participantId"] = "tampered"
        self.write_json(static / "decision-package.json", decision)
        output = self.root / "compound/drift"
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--static-assessment", str(static), "--harmony-loop", str(loop), "--output", str(output)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 1)
        failure = json.loads(next((self.root / "compound").glob(".drift.stage-*/failure.json")).read_text())
        self.assertIn("exact statically passing attempt", failure["error"])

    def test_device_process_evidence_drift_is_rejected(self) -> None:
        static = self.make_static("process-drift", "strong")
        loop = self.make_loop("process-drift", static, "strong", True)
        (loop / "assessment/execution/ui-checks.tsv").write_text(
            "ready\tfalse\ttext\ttampered\n"
        )
        output = self.root / "compound/process-drift"
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--static-assessment",
                str(static),
                "--harmony-loop",
                str(loop),
                "--output",
                str(output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 1)
        failure = json.loads(
            next((self.root / "compound").glob(".process-drift.stage-*/failure.json")).read_text()
        )
        self.assertIn("uiChecks evidence differs", failure["error"])


if __name__ == "__main__":
    unittest.main()
