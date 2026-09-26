from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import grp
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PREPARE = ROOT / "scripts/prepare-harmony-assessed-handoff.py"
RESOLVE = ROOT / "scripts/resolve-harmony-assessed-handoff.py"


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class HarmonyAssessedHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)
        self.static = self.base / "static"
        self.static.mkdir()
        self.source_set = "a" * 64
        self.authoring = {
            "receiptSha256": "1" * 64,
            "draftManifestSha256": "2" * 64,
            "participantId": "independent-evaluator",
            "participantSha256": "3" * 64,
            "methodRevision": "4" * 40,
        }
        self.write_json(
            self.static / "multi-repo-evaluation-case.json",
            {
                "schema": "agentlab.multi_repo_evaluation_case.v1",
                "id": "portable-case",
                "status": "frozen-calibrated",
                "sourceSetSha256": self.source_set,
                "calibration": {
                    "qualified": True,
                    "executableBundle": {"calibrationAuthoring": self.authoring},
                },
                "automaticPromotion": False,
            },
        )
        calibration = {"schema": "agentlab.multi_repo_calibration.v1", "sourceSetSha256": self.source_set, "qualified": True}
        self.write_json(self.static / "multi-repo-calibration.json", calibration)
        self.write_json(self.static / "case/calibration/summary.json", calibration)
        self.execution_protocol = {
            "schema": "agentlab.participant_execution_protocol.v1",
            "agentImplementation": "pi",
            "agentPackage": "@mariozechner/pi-coding-agent",
            "agentPackageVersion": "0.73.1",
        }
        self.experiment_profiles = [
            {"ordinal": 0, "participantId": "weak", "model": "model-weak"},
            {"ordinal": 1, "participantId": "middle", "model": "model-middle"},
            {"ordinal": 2, "participantId": "strong", "model": "model-strong"},
        ]
        self.experiment_plan = {
            "schema": "agentlab.participant_experiment_plan.v1",
            "status": "predeclared-before-attempts",
            "caseId": "portable-case",
            "sourceSetSha256": self.source_set,
            "methodRevision": "b" * 40,
            "providerRoute": "provider-route",
            "trialsPerParticipant": 1,
            "participantProfileCount": 3,
            "participantProfiles": self.experiment_profiles,
            "executionProtocol": self.execution_protocol,
            "automaticPromotion": False,
        }
        self.write_json(
            self.static / "participant-experiment-plan.json", self.experiment_plan
        )
        self.experiment_plan_sha256 = digest(
            self.static / "participant-experiment-plan.json"
        )
        attempts = []
        for attempt_id, participant in (
            ("weak-1", "weak"),
            ("middle-1", "middle"),
            ("strong-1", "strong"),
        ):
            self.assessment(attempt_id, participant)
            attempts.append({"attemptId": attempt_id, "participantId": participant, "producerRun": "8123", "evidence": f"runs/{attempt_id}"})
        self.write_json(
            self.static / "attempts.json",
            {
                "schema": "agentlab.case_attempt_collection.v2",
                "sourceSetSha256": self.source_set,
                "methodRevision": "b" * 40,
                "cases": [{"id": "portable-case", "calibration": "case/calibration/summary.json", "attempts": attempts}],
            },
        )
        self.handoff = self.static / "harmony-device-handoff.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_json(self, path: pathlib.Path, value) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def assessment(self, attempt_id: str, participant: str) -> None:
        root = self.static / "runs" / attempt_id
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
        common = {"taskId": "portable-case", "sourceSetSha256": self.source_set, "participantId": participant, "assessmentStatus": "assessed", "infrastructureAvailable": True, "subjectTaskSucceeded": True}
        profile = next(
            row for row in self.experiment_profiles if row["participantId"] == participant
        )
        experiment = {
            "planSha256": self.experiment_plan_sha256,
            "participantOrdinal": profile["ordinal"],
            "participantId": participant,
            "model": profile["model"],
            "providerRoute": self.experiment_plan["providerRoute"],
            "executionProtocol": self.execution_protocol,
            "nativeParticipantEvidence": {
                "path": "participant.json",
                "sha256": "9" * 64,
                "identityQualified": True,
            },
        }
        self.write_json(root / "final-source-state.json", state)
        self.write_json(root / "summary.json", {**common, "schema": "agentlab.multi_repo_assessment_summary.v1", "finalWorkspaceSha256": canonical(state), "participantExperiment": experiment})
        self.write_json(root / "decision-package.json", {**common, "schema": "agentlab.harness_decision_package.v1", "automaticPromotion": False, "participantExperiment": experiment})

    def execute(self, *arguments: pathlib.Path | str):
        return subprocess.run([sys.executable, *map(str, arguments)], text=True, capture_output=True, check=False)

    def prepare(self):
        completed = self.execute(PREPARE, "--root", self.static, "--output", self.handoff)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def host_profile(self, host: pathlib.Path) -> pathlib.Path:
        host.mkdir()
        program = host / "program.py"
        program.write_text("#!/usr/bin/env python3\n")
        program.chmod(0o755)
        oracle = host / "scenario.ui"; oracle.write_text("check text ready\n")
        policy = host / "policy.json"; policy.write_text("{}\n")
        workload = host / "workload.tsv"; workload.write_text("0\ttap\t1\t1\n")
        for directory in ("tools", "image", "instance"):
            (host / directory).mkdir()
        binding = lambda path: {"path": path.relative_to(host).as_posix(), "sha256": digest(path)}
        value = {
            "schema": "agentlab.harmony_assessed_host_profile.v1",
            "profileId": "hwlinux-test",
            "sourceMaterialization": [{"sourceId": "app", "sourcePath": ".", "targetPath": "entry"}],
            "build": {"executable": binding(program), "arguments": [], "workingDirectory": ".", "artifactPath": "build/output.hap", "timeoutSeconds": 30, "environment": {}},
            "standardTest": {
                "sourceExecutor": binding(program),
                "configuration": {
                    "hvigorw": binding(program), "hdc": binding(program),
                    "buildModule": "entry", "appHap": "app.hap", "testHap": "test.hap",
                    "target": "device", "bundle": "com.example.app", "testModule": "entry_test",
                },
            },
            "device": {
                "subjectOutcomePolicy": "retain-assessed-failure",
                "functionalOracle": {**binding(oracle), "scenarioId": "ready"},
                "runtime": {"runner": binding(program), "toolsRoot": "tools", "imageRoot": "image", "instancePath": "instance", "instance": "phone", "hdcPort": 15555, "bundle": "com.example.app", "ability": "EntryAbility", "environmentIdentity": "hwlinux:test", "bootMode": "coldboot", "profileSamples": 3},
                "performance": {"policy": binding(policy), "workload": binding(workload)},
            },
            "programs": {name: binding(program) for name in ("build", "standardTest", "loop", "run", "compose", "collect", "score", "feedback")},
            "requiredTrials": 1,
            "eligibilityThreshold": 0.6,
            "automaticPromotion": False,
        }
        profile = host / "profile.json"
        self.write_json(profile, value)
        return profile

    def test_relocated_handoff_resolves_to_existing_campaign_plan(self) -> None:
        self.prepare()
        relocated = self.base / "relocated"
        shutil.copytree(self.static, relocated)
        host = self.base / "host"
        profile = self.host_profile(host)
        plan = self.base / "plan.json"
        completed = self.execute(RESOLVE, "--handoff", relocated / self.handoff.name, "--host-profile", profile, "--host-root", host, "--output", plan)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(plan.read_text())
        self.assertEqual(value["schema"], "agentlab.harmony_assessed_campaign_plan.v1")
        self.assertEqual(len(value["attempts"]), 3)
        self.assertEqual(
            value["participantExperimentPlan"]["sha256"],
            self.experiment_plan_sha256,
        )
        self.assertEqual(value["calibrationAuthoring"], self.authoring)
        self.assertTrue(all(pathlib.Path(row["assessment"]["path"]).is_absolute() for row in value["attempts"]))
        spec = importlib.util.spec_from_file_location("campaign", ROOT / "scripts/run-harmony-assessed-campaign.py")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        validated = module.validate_plan(plan)
        self.assertEqual(validated["caseId"], "portable-case")
        self.assertEqual(validated["calibrationAuthoring"], self.authoring)

    def test_v2_schema_requires_predeclared_experiment_and_producer_run(self) -> None:
        schema = json.loads(
            (
                ROOT
                / "schemas/harmony-assessed-campaign-handoff-v2.schema.json"
            ).read_text()
        )
        self.assertEqual(
            schema["properties"]["schema"]["const"],
            "agentlab.harmony_assessed_campaign_handoff.v2",
        )
        self.assertIn("participantExperimentPlan", schema["required"])
        self.assertIn(
            "producerRun",
            schema["properties"]["attempts"]["items"]["required"],
        )

    def test_v1_handoff_remains_readable_as_historical_evidence(self) -> None:
        self.prepare()
        value = json.loads(self.handoff.read_text())
        value["schema"] = "agentlab.harmony_assessed_campaign_handoff.v1"
        value.pop("participantExperimentPlan")
        self.handoff.write_text(json.dumps(value))
        host = self.base / "host"
        profile = self.host_profile(host)
        plan = self.base / "legacy-plan.json"
        completed = self.execute(
            RESOLVE,
            "--handoff",
            self.handoff,
            "--host-profile",
            profile,
            "--host-root",
            host,
            "--output",
            plan,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("participantExperimentPlan", json.loads(plan.read_text()))

    def test_authoring_lineage_tampering_is_rejected_before_host_resolution(self) -> None:
        self.prepare()
        value = json.loads(self.handoff.read_text())
        value["calibrationAuthoring"]["receiptSha256"] = "f" * 64
        self.handoff.write_text(json.dumps(value))
        host = self.base / "host"
        profile = self.host_profile(host)
        completed = self.execute(
            RESOLVE,
            "--handoff",
            self.handoff,
            "--host-profile",
            profile,
            "--host-root",
            host,
            "--output",
            self.base / "plan.json",
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("authoring lineage differs", completed.stderr)

    def test_participant_experiment_tampering_is_rejected_before_handoff(self) -> None:
        path = self.static / "runs/strong-1/summary.json"
        value = json.loads(path.read_text())
        value["participantExperiment"]["model"] = "model-weak"
        path.write_text(json.dumps(value))
        completed = self.execute(
            PREPARE,
            "--root",
            self.static,
            "--output",
            self.handoff,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("participant experiment evidence differs", completed.stderr)

    def test_participant_experiment_plan_drift_is_rejected_on_host(self) -> None:
        self.prepare()
        path = self.static / "participant-experiment-plan.json"
        value = json.loads(path.read_text())
        value["providerRoute"] = "changed-route"
        path.write_text(json.dumps(value))
        host = self.base / "host"
        profile = self.host_profile(host)
        completed = self.execute(
            RESOLVE,
            "--handoff",
            self.handoff,
            "--host-profile",
            profile,
            "--host-root",
            host,
            "--output",
            self.base / "plan.json",
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("participant experiment plan", completed.stderr)

    def test_workspace_mutation_after_transfer_is_rejected(self) -> None:
        self.prepare()
        (self.static / "runs/strong-1/workspace/app/Index.ets").write_text("mutated\n")
        host = self.base / "host"
        profile = self.host_profile(host)
        completed = self.execute(RESOLVE, "--handoff", self.handoff, "--host-profile", profile, "--host-root", host, "--output", self.base / "plan.json")
        self.assertEqual(completed.returncode, 1)
        self.assertIn("workspace tree differs", completed.stderr)

    def test_relative_path_escape_is_rejected(self) -> None:
        self.prepare()
        value = json.loads(self.handoff.read_text())
        value["evaluationCase"]["path"] = "../outside.json"
        self.handoff.write_text(json.dumps(value))
        host = self.base / "host"
        profile = self.host_profile(host)
        completed = self.execute(RESOLVE, "--handoff", self.handoff, "--host-profile", profile, "--host-root", host, "--output", self.base / "plan.json")
        self.assertEqual(completed.returncode, 1)
        self.assertIn("safe relative path", completed.stderr)

    def test_host_file_digest_drift_is_rejected(self) -> None:
        self.prepare()
        host = self.base / "host"
        profile = self.host_profile(host)
        (host / "program.py").write_text("#!/usr/bin/env python3\nprint('changed')\n")
        completed = self.execute(RESOLVE, "--handoff", self.handoff, "--host-profile", profile, "--host-root", host, "--output", self.base / "plan.json")
        self.assertEqual(completed.returncode, 1)
        self.assertIn("SHA256 differs", completed.stderr)

    def test_kvm_profile_without_execution_preflight_is_rejected(self) -> None:
        self.prepare()
        host = self.base / "host"
        profile = self.host_profile(host)
        value = json.loads(profile.read_text())
        value["device"]["runtime"]["environmentIdentity"] = "hwlinux:harmonyos:x86:kvm"
        profile.write_text(json.dumps(value))
        completed = self.execute(
            RESOLVE,
            "--handoff",
            self.handoff,
            "--host-profile",
            profile,
            "--host-root",
            host,
            "--output",
            self.base / "plan.json",
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("requires executionPreflight", completed.stderr)

    def test_kvm_profile_carries_valid_execution_preflight(self) -> None:
        self.prepare()
        host = self.base / "host"
        profile = self.host_profile(host)
        value = json.loads(profile.read_text())
        value["device"]["runtime"]["environmentIdentity"] = "hwlinux:harmonyos:x86:kvm"
        value["executionPreflight"] = {
            "requiredGroups": [grp.getgrgid(os.getegid()).gr_name],
            "requiredDevices": [{"path": "/dev/null", "read": True, "write": True}],
        }
        profile.write_text(json.dumps(value))
        plan = self.base / "plan.json"
        completed = self.execute(
            RESOLVE,
            "--handoff",
            self.handoff,
            "--host-profile",
            profile,
            "--host-root",
            host,
            "--output",
            plan,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        resolved = json.loads(plan.read_text())
        self.assertEqual(resolved["executionPreflight"], value["executionPreflight"])

    def test_real_hwlinux_qualification_retains_review_boundary(self) -> None:
        receipt = json.loads(
            (
                ROOT
                / "release/qualifications/harmony-portable-handoff-hwlinux-2be1911/summary.json"
            ).read_text()
        )
        self.assertEqual(
            receipt["schema"], "agentlab.harmony_portable_handoff_qualification.v1"
        )
        self.assertEqual(receipt["status"], "assessed-review-required")
        self.assertEqual(receipt["assessment"]["deviceAttemptCount"], 2)
        self.assertEqual(receipt["assessment"]["discriminationScore"], 1.0)
        self.assertTrue(receipt["assessment"]["strongOutcome"])
        self.assertFalse(receipt["assessment"]["weakOutcome"])
        self.assertEqual(receipt["assessment"]["weakFailureClass"], "oracle")
        self.assertEqual(receipt["outputs"]["evidenceFileCount"], 202)
        self.assertFalse(receipt["automaticPromotion"])

    def test_real_hwlinux_ohostest_qualification_retains_empirical_boundary(self) -> None:
        receipt = json.loads(
            (
                ROOT
                / "release/qualifications/harmony-assessed-ohostest-hwlinux-aa799f9/summary.json"
            ).read_text()
        )
        self.assertEqual(
            receipt["schema"], "agentlab.harmony_assessed_ohostest_qualification.v1"
        )
        self.assertEqual(receipt["status"], "assessed-review-required")
        self.assertFalse(receipt["automaticPromotion"])
        self.assertEqual(receipt["assessment"]["deviceAttemptCount"], 2)
        self.assertEqual(receipt["assessment"]["discriminationScore"], 1.0)
        self.assertFalse(receipt["assessment"]["extremePassRateWilson95Separated"])
        for attempt in ("strong-ohostest-1", "weak-ohostest-1"):
            self.assertTrue(
                receipt["attempts"][attempt]["standardTest"]["subjectTaskSucceeded"]
            )
        self.assertEqual(
            receipt["attempts"]["weak-ohostest-1"]["device"]["failureClass"],
            "oracle",
        )
        self.assertEqual(
            receipt["attempts"]["strong-ohostest-1"]["performance"]["sampleCount"],
            3,
        )
        self.assertFalse(receipt["feedback"]["caseReady"])
        self.assertEqual(
            receipt["qualificationBoundary"]["sourcePopulation"],
            "controlled strong and weak fixture variants, not external model submissions",
        )
        self.assertIn(
            "absolute power or thermal measurement",
            receipt["qualificationBoundary"]["notQualified"],
        )


if __name__ == "__main__":
    unittest.main()
