from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CLOSURE = ROOT / "release/closures/v0.1.0-alpha.12.json"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PREPARE = load_module("prepare_release_harmony_acceptance", ROOT / "scripts/prepare-release-harmony-acceptance.py")
VALIDATE = load_module("validate_release_harmony_acceptance", ROOT / "scripts/validate-release-harmony-acceptance.py")


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReleaseHarmonyAcceptanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.template = self.root / "template.json"
        self.plan_path = self.root / "plan.json"
        self.output = self.root / "campaign-output"
        self.cleanup = self.root / "cleanup.json"
        template = {
            "schema": "agentlab.harmony_assessed_campaign_plan.v1",
            "campaignId": "old-campaign",
            "methodRevision": "d" * 40,
            "automaticPromotion": False,
            "attempts": [
                {"attemptId": "strong", "participantId": "strong", "assessment": {}},
                {"attemptId": "weak", "participantId": "weak", "assessment": {}},
            ],
            "programs": {},
            "standardTest": {"sourceExecutor": {}, "configuration": {}},
            "device": {
                "runtime": {"environmentIdentity": "hwlinux:harmonyos-7.0.0:x86:kvm"},
                "functionalOracle": {"path": "/old/multi-repo-ready.ui", "scenarioId": "multi-repo-ready"},
            },
        }
        self.template.write_text(json.dumps(template))
        plan = PREPARE.prepare(CLOSURE, self.template, ROOT, "alpha12-release-acceptance")
        self.plan_path.write_text(json.dumps(plan, sort_keys=True))
        self.plan = plan
        self.make_campaign()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_json(self, path: pathlib.Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True))

    def make_attempt(self, attempt_id: str, passed: bool) -> None:
        root = self.output / "attempts" / attempt_id / "harmony-loop"
        self.write_json(
            root / "standard-test/receipt.json",
            {
                "framework": "instrument-test-ohosTest-hypium",
                "status": "passed-review-required",
                "subjectTaskSucceeded": True,
                "automaticPromotion": False,
            },
        )
        result = {
            "environmentIdentity": "hwlinux:harmonyos-7.0.0:x86:kvm",
            "infrastructureAvailable": True,
            "assessmentStatus": "assessed",
            "powerThermalAuthority": "unavailable_on_emulator",
            "status": "passed" if passed else "failed",
            "oracleStatus": "passed" if passed else "failed",
            "failureClass": "none" if passed else "oracle",
            "subjectTaskSucceeded": passed,
            "profileStatus": "collected" if passed else "not-run",
        }
        self.write_json(root / "assessment/execution/result.json", result)
        if passed:
            self.write_json(
                root / "assessment/execution/smartperf-summary.json",
                {
                    "profileValid": True,
                    "sampleCount": 3,
                    "authority": {
                        "relativePerformance": "smartperf-emulator-proxy",
                        "absolutePowerThermal": "unavailable-on-emulator",
                    },
                },
            )

    def make_campaign(self) -> None:
        closure = json.loads(CLOSURE.read_text())
        self.write_json(
            self.output / "summary.json",
            {
                "schema": "agentlab.harmony_assessed_campaign_summary.v1",
                "campaignId": self.plan["campaignId"],
                "planSha256": digest(self.plan_path),
                "methodRevision": closure["sources"]["releaseGitSha"],
                "status": "assessed-review-required",
                "automaticPromotion": False,
                "attemptCount": 2,
                "deviceAttemptCount": 2,
                "caseId": "case-1",
                "sourceSetSha256": "a" * 64,
                "eligibleCaseIds": ["case-1"],
                "feedbackCandidateCount": 1,
            },
        )
        self.make_attempt("strong", True)
        self.make_attempt("weak", False)
        self.write_json(
            self.cleanup,
            {
                "schema": "agentlab.harmony_emulator_cleanup.v1",
                "emulatorProcessCount": 0,
                "hdcTargets": [],
                "remoteInspection": {
                    "routeDecision": "peer_direct",
                    "targetPeerId": "lgw_abc",
                    "operationIds": ["exec-1"],
                },
            },
        )

    def test_prepare_binds_current_programs_closure_and_assets(self) -> None:
        closure = json.loads(CLOSURE.read_text())
        release = self.plan["releaseAcceptance"]
        self.assertEqual(release["releaseTag"], "v0.1.0-alpha.12")
        self.assertEqual(self.plan["methodRevision"], closure["sources"]["releaseGitSha"])
        self.assertEqual(release["closure"]["sha256"], digest(CLOSURE))
        self.assertEqual(len(release["requiredAssets"]), 5)
        self.assertEqual(
            pathlib.Path(self.plan["programs"]["run"]["path"]).name,
            "run-harmony-evaluation-case.py",
        )

    def test_validator_accepts_release_bound_positive_and_negative_attempts(self) -> None:
        receipt = VALIDATE.validate(CLOSURE, self.plan_path, self.output, self.cleanup)
        self.assertEqual(receipt["schema"], "agentlab.release_harmony_acceptance.v1")
        self.assertEqual(receipt["status"], "accepted-developer-preview-review-required")
        self.assertEqual(receipt["attempts"][0]["performance"]["sampleCount"], 3)
        self.assertEqual(receipt["attempts"][1]["performance"]["status"], "not-run")
        self.assertFalse(receipt["automaticPromotion"])

    def test_old_campaign_revision_cannot_qualify_current_release(self) -> None:
        summary_path = self.output / "summary.json"
        summary = json.loads(summary_path.read_text())
        summary["methodRevision"] = "d" * 40
        self.write_json(summary_path, summary)
        with self.assertRaisesRegex(ValueError, "method revision differs"):
            VALIDATE.validate(CLOSURE, self.plan_path, self.output, self.cleanup)

    def test_functional_pass_requires_valid_smartperf(self) -> None:
        performance = self.output / "attempts/strong/harmony-loop/assessment/execution/smartperf-summary.json"
        value = json.loads(performance.read_text())
        value["profileValid"] = False
        self.write_json(performance, value)
        with self.assertRaisesRegex(ValueError, "SmartPerf profile is invalid"):
            VALIDATE.validate(CLOSURE, self.plan_path, self.output, self.cleanup)

    def test_cleanup_must_prove_no_emulator_or_hdc_target(self) -> None:
        value = json.loads(self.cleanup.read_text())
        value["hdcTargets"] = ["127.0.0.1:10100"]
        self.write_json(self.cleanup, value)
        with self.assertRaisesRegex(ValueError, "HDC targets remain"):
            VALIDATE.validate(CLOSURE, self.plan_path, self.output, self.cleanup)

    def test_prepare_rejects_closure_without_required_image(self) -> None:
        closure = json.loads(CLOSURE.read_text())
        closure["assets"] = [row for row in closure["assets"] if row["id"] != "HarmonyOS-7.0.0-phone_all_x86.tar.zst"]
        broken = self.root / "broken-closure.json"
        self.write_json(broken, closure)
        with self.assertRaisesRegex(ValueError, "missing required Harmony asset"):
            PREPARE.prepare(broken, self.template, ROOT, "broken")


if __name__ == "__main__":
    unittest.main()
