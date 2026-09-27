from __future__ import annotations

import grp
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run-harmony-assessed-campaign.py"


BUILDER = r'''#!/usr/bin/env python3
import argparse, pathlib
p=argparse.ArgumentParser(); p.add_argument("--workspace"); p.add_argument("--artifact"); a=p.parse_args()
root=pathlib.Path(a.workspace); out=pathlib.Path(a.artifact); out.parent.mkdir(parents=True)
out.write_bytes((root/"entry/Index.ets").read_bytes() + (root/"shared/policy.ets").read_bytes())
'''


RUNNER = r'''#!/usr/bin/env python3
import argparse, hashlib, json, os, pathlib
p=argparse.ArgumentParser(); p.add_argument("--plan"); p.add_argument("--output"); a=p.parse_args()
plan=json.loads(pathlib.Path(a.plan).read_text()); build_path=pathlib.Path(plan["buildReceipt"]["path"]); build=json.loads(build_path.read_text())
out=pathlib.Path(a.output); execution=out/"execution"; execution.mkdir(parents=True)
digest=lambda path: hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
passed=build["participantId"] == "strong"
hap=digest(plan["artifact"]["path"]); case=json.loads(pathlib.Path(plan["evaluationCase"]["path"]).read_text())
result={"schema":"agentlab.harmony_emulator_case_result.v3","status":"passed" if passed else "failed",
 "taskId":case["id"],"sourceSetSha256":case["sourceSetSha256"],"sourceIdentity":"artifact-sha256:"+hap,
 "hapSha256":hap,"oracleStatus":"passed" if passed else "failed","assessmentStatus":"assessed",
 "infrastructureAvailable":True,"subjectTaskSucceeded":passed,"failureClass":"none" if passed else "oracle",
 "powerThermalAuthority":"unavailable_on_emulator"}
(execution/"result.json").write_text(json.dumps(result))
(execution/"ui-actions.tsv").write_text("1\tlaunch\tapp\n")
(execution/"ui-checks.tsv").write_text("ready\t%s\ttext\tready\n" % str(passed).lower())
if passed: (execution/"profile-workload-actions.tsv").write_text("1\tswipe\t1,2,3,4,5\n")
if passed: (execution/"smartperf-summary.json").write_text(json.dumps({"profileValid":True,"sampleCount":3}))
process_evidence={
 "uiActions":{"sha256":digest(execution/"ui-actions.tsv"),"rowCount":1},
 "uiChecks":{"sha256":digest(execution/"ui-checks.tsv"),"rowCount":1},
 "profileWorkloadActions":{"sha256":digest(execution/"profile-workload-actions.tsv"),"rowCount":1} if passed else None}
assessed={key:build[key] for key in ("participantId","subjectWorkspaceSha256","assessmentSummarySha256","assessmentDecisionSha256","finalSourceStateSha256")}
binding={"schema":"agentlab.harmony_evaluation_binding.v1","status":"passed-review-required" if passed else "assessed-failure-review-required",
 "caseId":case["id"],"sourceSetSha256":case["sourceSetSha256"],"evaluationCaseSha256":plan["evaluationCase"]["sha256"],
 "buildReceiptSha256":digest(build_path),"buildAuthority":build["buildAuthority"],"hapSha256":hap,
 "subjectTaskSucceeded":passed,"failureClass":"none" if passed else "oracle","assessedWorkspace":assessed,
 "resultSha256":digest(execution/"result.json"),"environmentIdentity":"hwlinux:test",
 "performancePolicySha256":plan["performance"]["policySha256"],"profileWorkloadSha256":plan["performance"]["workloadSha256"],
 "smartperfSummarySha256":digest(execution/"smartperf-summary.json") if passed else None,
 "deviceProcessMeasurement":{"schema":"agentlab.harmony_device_process_measurement.v1","runnerDurationMs":0,
  "uiActionCount":1,"uiCheckCount":1,"profileWorkloadActionCount":1 if passed else 0,
  "smartPerfSampleCount":3 if passed else 0,"functionalOraclePass":passed,"profileCollected":passed,
  "evidence":process_evidence},"automaticPromotion":False}
(out/"evaluation-binding.json").write_text(json.dumps(binding))
'''


STANDARD = r'''#!/usr/bin/env python3
import argparse, hashlib, json, os, pathlib
p=argparse.ArgumentParser(); p.add_argument("--plan"); p.add_argument("--output"); a=p.parse_args()
plan=json.loads(pathlib.Path(a.plan).read_text()); build_path=pathlib.Path(plan["buildReceipt"]["path"]); build=json.loads(build_path.read_text())
out=pathlib.Path(a.output); out.mkdir(); digest=lambda path: hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
assessed={key:build[key] for key in ("participantId","subjectWorkspaceSha256","assessmentSummarySha256","assessmentDecisionSha256","finalSourceStateSha256")}
passed=build["participantId"] != os.environ.get("CAMPAIGN_STANDARD_FAIL_PARTICIPANT")
receipt={"schema":"agentlab.harmony_assessed_standard_test_receipt.v1","status":"passed-review-required" if passed else "assessed-failure-review-required",
 "caseId":"campaign-case","evaluationCaseSha256":plan["evaluationCase"]["sha256"],"sourceSetSha256":"a"*64,
 "buildReceiptSha256":digest(build_path),"subjectTaskSucceeded":passed,"failureClass":"none" if passed else "standard-test",
 "assessedWorkspace":assessed,"automaticPromotion":False}
(out/"receipt.json").write_text(json.dumps(receipt))
'''


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class HarmonyAssessedCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.case = self.root / "case.json"
        self.source_set = "a" * 64
        self.authoring = {
            "receiptSha256": "1" * 64,
            "draftManifestSha256": "2" * 64,
            "participantId": "independent-evaluator",
            "participantSha256": "3" * 64,
            "methodRevision": "4" * 40,
        }
        self.case.write_text(
            json.dumps(
                {
                    "schema": "agentlab.multi_repo_evaluation_case.v1",
                    "id": "campaign-case",
                    "status": "frozen-calibrated",
                    "sourceSetSha256": self.source_set,
                    "sources": [
                        {"id": "app", "repository": "https://example.invalid/app", "revision": "b" * 40},
                        {"id": "contracts", "repository": "https://example.invalid/contracts", "revision": "c" * 40},
                    ],
                    "oracle": {"authority": "independent-executable-oracle"},
                    "calibration": {
                        "qualified": True,
                        "executableBundle": {"calibrationAuthoring": self.authoring},
                    },
                    "automaticPromotion": False,
                }
            )
        )
        self.calibration = self.root / "calibration.json"
        self.calibration.write_text(
            json.dumps(
                {
                    "schema": "agentlab.multi_repo_calibration.v1",
                    "candidateId": "campaign-difficulty",
                    "sourceSetSha256": self.source_set,
                    "infrastructureAvailable": True,
                    "variants": {
                        "baseline": {"stages": {"static": {"pass": False}, "harmony-device": {"pass": False}}},
                        "reference": {"stages": {"static": {"pass": True}, "harmony-device": {"pass": True}}},
                        "wrong-device": {"stages": {"static": {"pass": True}, "harmony-device": {"pass": False}}},
                    },
                }
            )
        )
        self.builder = self.executable("builder.py", BUILDER)
        self.standard = self.executable("standard.py", STANDARD)
        self.runner = self.executable("runner.py", RUNNER)
        self.scenario = self.file("scenario.ui", "check text ready\n")
        self.policy = self.file("policy.json", "{}\n")
        self.workload = self.file("workload.tsv", "0\ttap\t1\t1\n")
        self.tools = self.root / "tools"; self.tools.mkdir()
        self.image = self.root / "image"; self.image.mkdir()
        self.instance = self.root / "instance"; self.instance.mkdir()
        self.execution_protocol = {
            "schema": "agentlab.participant_execution_protocol.v1",
            "agentImplementation": "pi",
            "agentPackageVersion": "0.73.1",
        }
        self.experiment_profiles = [
            {"ordinal": 0, "participantId": "weak", "model": "model-weak"},
            {"ordinal": 1, "participantId": "strong", "model": "model-strong"},
        ]
        self.experiment_plan = self.root / "participant-experiment-plan.json"
        self.experiment_plan.write_text(
            json.dumps(
                {
                    "schema": "agentlab.participant_experiment_plan.v1",
                    "status": "predeclared-before-attempts",
                    "caseId": "campaign-case",
                    "sourceSetSha256": self.source_set,
                    "methodRevision": "d" * 40,
                    "providerRoute": "provider-route",
                    "trialsPerParticipant": 1,
                    "participantProfileCount": 2,
                    "participantProfiles": self.experiment_profiles,
                    "executionProtocol": self.execution_protocol,
                    "automaticPromotion": False,
                }
            )
        )
        self.strong = self.assessment("strong")
        self.weak = self.assessment("weak")
        self.plan = self.root / "campaign-plan.json"
        self.write_plan()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def file(self, name: str, value: str) -> pathlib.Path:
        path = self.root / name; path.write_text(value); return path

    def executable(self, name: str, value: str) -> pathlib.Path:
        path = self.file(name, value); path.chmod(0o755); return path

    def bind(self, path: pathlib.Path) -> dict:
        return {"path": str(path), "sha256": digest(path)}

    def assessment(self, participant: str) -> pathlib.Path:
        root = self.root / f"static-{participant}"
        workspace = root / "workspace"
        (workspace / "app").mkdir(parents=True)
        (workspace / "contracts/src").mkdir(parents=True)
        (workspace / "app/Index.ets").write_text(f"Text('{participant}')\n")
        (workspace / "contracts/src/policy.ets").write_text("export const policy = true\n")
        state = {}
        for path in sorted(item for item in workspace.rglob("*") if item.is_file()):
            state[path.relative_to(workspace).as_posix()] = {
                "sha256": digest(path),
                "byteLength": path.stat().st_size,
                "unixMode": path.stat().st_mode & 0o777,
            }
        (root / "final-source-state.json").write_text(json.dumps(state))
        common = {
            "taskId": "campaign-case",
            "sourceSetSha256": self.source_set,
            "participantId": participant,
            "assessmentStatus": "assessed",
            "infrastructureAvailable": True,
            "subjectTaskSucceeded": True,
        }
        profile = next(
            row for row in self.experiment_profiles if row["participantId"] == participant
        )
        experiment = {
            "planSha256": digest(self.experiment_plan),
            "participantOrdinal": profile["ordinal"],
            "participantId": participant,
            "model": profile["model"],
            "providerRoute": "provider-route",
            "executionProtocol": self.execution_protocol,
            "nativeParticipantEvidence": {
                "path": "participant.json",
                "sha256": "9" * 64,
                "identityQualified": True,
            },
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
        (root / "summary.json").write_text(
            json.dumps({**common, "schema": "agentlab.multi_repo_assessment_summary.v1", "finalWorkspaceSha256": canonical(state), "stages": phases, "durationMs": 15, "processMeasurement": process, "participantExperiment": experiment})
        )
        (root / "decision-package.json").write_text(
            json.dumps({**common, "schema": "agentlab.harness_decision_package.v1", "phaseVerdicts": phases, "processMeasurement": process, "participantExperiment": experiment, "automaticPromotion": False})
        )
        return root

    def write_plan(self) -> None:
        programs = {
            "build": ROOT / "scripts/build-harmony-assessed-workspace.py",
            "standardTest": self.standard,
            "loop": ROOT / "scripts/run-harmony-evaluation-loop.py",
            "run": self.runner,
            "compose": ROOT / "scripts/compose-harmony-assessed-decision.py",
            "collect": ROOT / "scripts/collect-case-attempts.py",
            "score": ROOT / "scripts/score-case-discrimination.py",
            "feedback": ROOT / "scripts/derive-assessment-feedback.py",
        }
        value = {
            "schema": "agentlab.harmony_assessed_campaign_plan.v1",
            "campaignId": "campaign-r1",
            "evaluationCase": self.bind(self.case),
            "calibration": self.bind(self.calibration),
            "participantExperimentPlan": self.bind(self.experiment_plan),
            "calibrationAuthoring": self.authoring,
            "methodRevision": "d" * 40,
            "attempts": [
                {"attemptId": "strong-1", "participantId": "strong", "producerRun": 424242, "assessment": self.assessment_binding(self.strong)},
                {"attemptId": "weak-1", "participantId": "weak", "producerRun": 424242, "assessment": self.assessment_binding(self.weak)},
            ],
            "sourceMaterialization": [
                {"sourceId": "app", "sourcePath": ".", "targetPath": "entry"},
                {"sourceId": "contracts", "sourcePath": "src", "targetPath": "shared"},
            ],
            "build": {
                "executable": str(self.builder), "executableSha256": digest(self.builder),
                "arguments": ["--workspace", "{workspace}", "--artifact", "{artifact}"],
                "workingDirectory": ".", "artifactPath": "build/output.hap", "timeoutSeconds": 30, "environment": {},
            },
            "standardTest": {
                "sourceExecutor": self.bind(self.standard),
                "configuration": {},
            },
            "device": {
                "subjectOutcomePolicy": "retain-assessed-failure",
                "functionalOracle": {"path": str(self.scenario), "sha256": digest(self.scenario), "scenarioId": "ready"},
                "runtime": {"runner": str(self.runner), "runnerSha256": digest(self.runner), "toolsRoot": str(self.tools),
                            "imageRoot": str(self.image), "instancePath": str(self.instance), "instance": "phone",
                            "hdcPort": 15555, "bundle": "com.example.app", "ability": "EntryAbility",
                            "environmentIdentity": "hwlinux:test", "bootMode": "coldboot", "profileSamples": 3},
                "performance": {"policy": str(self.policy), "policySha256": digest(self.policy),
                                "workload": str(self.workload), "workloadSha256": digest(self.workload)},
            },
            "programs": {key: self.bind(path) for key, path in programs.items()},
            "requiredTrials": 1,
            "eligibilityThreshold": 0.6,
            "automaticPromotion": False,
        }
        self.plan.write_text(json.dumps(value))

    def assessment_binding(self, root: pathlib.Path) -> dict:
        return {
            "path": str(root),
            "summarySha256": digest(root / "summary.json"),
            "decisionPackageSha256": digest(root / "decision-package.json"),
            "finalSourceStateSha256": digest(root / "final-source-state.json"),
        }

    def execute(self, output: pathlib.Path, env=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--plan", str(self.plan), "--output", str(output)],
            text=True, capture_output=True, check=False, env={**os.environ, **(env or {})},
        )

    def test_static_passes_run_device_and_close_feedback_loop(self) -> None:
        output = self.root / "campaign-output"
        completed = self.execute(output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        summary = json.loads((output / "summary.json").read_text())
        report = json.loads((output / "case-discrimination-report.json").read_text())
        feedback = json.loads((output / "assessment-feedback-candidates.json").read_text())
        state = json.loads((output / "campaign-state.json").read_text())
        self.assertEqual(summary["deviceAttemptCount"], 2)
        self.assertEqual(summary["calibrationAuthoring"], self.authoring)
        self.assertEqual(
            summary["participantExperimentPlanSha256"],
            digest(self.experiment_plan),
        )
        self.assertEqual(summary["eligibleCaseIds"], ["campaign-case"])
        self.assertEqual(report["ranking"][0]["metrics"]["discriminationScore"], 1.0)
        self.assertTrue(report["ranking"][0]["processAwareEligible"])
        candidates = [row for row in feedback["candidates"] if row["stageId"] == "harmony-device"]
        self.assertEqual(len(candidates), 1)
        self.assertFalse(candidates[0]["verificationContract"]["caseReady"])
        self.assertEqual(state["status"], "assessed-review-required")
        self.assertFalse(summary["automaticPromotion"])
        repeated = self.execute(output)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(json.loads((output / "summary.json").read_text()), summary)

    def test_standard_failure_enters_scoring_and_skips_device_performance(self) -> None:
        output = self.root / "standard-failure-output"
        completed = self.execute(
            output, {"CAMPAIGN_STANDARD_FAIL_PARTICIPANT": "weak"}
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        decision = json.loads(
            (output / "attempts/weak-1/evidence/decision-package.json").read_text()
        )
        loop_state = json.loads(
            (output / "attempts/weak-1/harmony-loop/loop-state.json").read_text()
        )
        self.assertEqual(decision["phaseVerdicts"][-1]["stageId"], "harmony-standard-test")
        self.assertFalse(decision["subjectTaskSucceeded"])
        self.assertEqual(loop_state["stages"]["emulatorAssessment"]["status"], "pending")
        self.assertFalse((output / "attempts/weak-1/harmony-loop/assessment").exists())

    def test_plan_drift_is_rejected_on_resume(self) -> None:
        output = self.root / "campaign-output"
        self.assertEqual(self.execute(output).returncode, 0)
        plan = json.loads(self.plan.read_text())
        plan["campaignId"] = "campaign-r2"
        self.plan.write_text(json.dumps(plan))
        rejected = self.execute(output)
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("existing campaign state", rejected.stderr)

    def test_static_failure_skips_device_capacity_but_still_enters_scoring(self) -> None:
        summary = json.loads((self.weak / "summary.json").read_text())
        decision = json.loads((self.weak / "decision-package.json").read_text())
        summary["subjectTaskSucceeded"] = False
        decision["subjectTaskSucceeded"] = False
        summary["stages"][0]["oraclePass"] = False
        decision["phaseVerdicts"][0]["oraclePass"] = False
        summary["processMeasurement"]["oraclePassedStageCount"] = 0
        decision["processMeasurement"]["oraclePassedStageCount"] = 0
        (self.weak / "summary.json").write_text(json.dumps(summary))
        (self.weak / "decision-package.json").write_text(json.dumps(decision))
        self.write_plan()
        output = self.root / "static-failure-output"
        completed = self.execute(output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        campaign = json.loads((output / "summary.json").read_text())
        state = json.loads((output / "campaign-state.json").read_text())
        feedback = json.loads((output / "assessment-feedback-candidates.json").read_text())
        self.assertEqual(campaign["deviceAttemptCount"], 1)
        self.assertEqual(state["attempts"]["weak-1"]["status"], "static-terminal")
        self.assertFalse((output / "attempts/weak-1/harmony-loop").exists())
        self.assertIn("static", {row["stageId"] for row in feedback["candidates"]})

    def test_static_evidence_drift_is_rejected_before_campaign_output(self) -> None:
        summary = json.loads((self.strong / "summary.json").read_text())
        summary["durationMs"] = 99
        (self.strong / "summary.json").write_text(json.dumps(summary))
        output = self.root / "drift-output"
        completed = self.execute(output)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("summary differs from campaign plan", completed.stderr)
        self.assertFalse(output.exists())

    def test_authoring_lineage_drift_is_rejected_before_campaign_output(self) -> None:
        plan = json.loads(self.plan.read_text())
        plan["calibrationAuthoring"]["receiptSha256"] = "f" * 64
        self.plan.write_text(json.dumps(plan))
        output = self.root / "authoring-drift-output"
        completed = self.execute(output)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("authoring lineage differs", completed.stderr)
        self.assertFalse(output.exists())

    def test_kvm_campaign_requires_explicit_execution_preflight(self) -> None:
        plan = json.loads(self.plan.read_text())
        plan["device"]["runtime"]["environmentIdentity"] = "hwlinux:harmonyos:x86:kvm"
        self.plan.write_text(json.dumps(plan))
        output = self.root / "missing-kvm-preflight"
        rejected = self.execute(output)
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("KVM campaign requires executionPreflight", rejected.stderr)
        self.assertFalse(output.exists())

    def test_kvm_campaign_accepts_active_group_and_device(self) -> None:
        plan = json.loads(self.plan.read_text())
        plan["device"]["runtime"]["environmentIdentity"] = "hwlinux:harmonyos:x86:kvm"
        plan["executionPreflight"] = {
            "requiredGroups": [grp.getgrgid(os.getegid()).gr_name],
            "requiredDevices": [{"path": "/dev/null", "read": True, "write": True}],
        }
        self.plan.write_text(json.dumps(plan))
        completed = self.execute(self.root / "valid-kvm-preflight")
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
