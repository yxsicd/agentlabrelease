from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PLAN = load_module(
    "participant_experiment_plan_test",
    ROOT / "scripts/participant-experiment-plan.py",
)


class ParticipantExperimentPlanTests(unittest.TestCase):
    def case(self, root: Path) -> Path:
        path = root / "case.json"
        path.write_text(json.dumps({
            "id": "case-one",
            "sourceSetSha256": "a" * 64,
        }, sort_keys=True) + "\n")
        return path

    def profiles(self) -> list[dict]:
        return [
            {"participantId": "weak", "model": "glm-5.3-flash"},
            {"participantId": "middle", "model": "glm-5.3"},
            {"participantId": "strong", "model": "glm-5.3-pro"},
        ]

    def protocol(self) -> dict:
        return {
            "schema": "agentlab.participant_execution_protocol.v1",
            "agentImplementation": "pi",
            "agentPackage": "@mariozechner/pi-coding-agent",
            "agentPackageVersion": "0.73.1",
            "participantAdapter": {"path": "examples/multi-repo-case/pi-assessed-agent.py", "sha256": "1" * 64},
            "participantDriver": {"path": "examples/real-code-agent/participant.py", "sha256": "2" * 64},
            "participantPackageLockSha256": "3" * 64,
            "participantRuntimeConfigSha256": "4" * 64,
            "runtimeImageId": "sha256:" + "5" * 64,
            "participantManifestSha256": "6" * 64,
            "promptAuthority": "digest-bound-adapter-driver-and-blind-case-manifest",
            "sessionPolicy": "fresh-per-attempt-persistent-across-case-stages",
            "thinkingMode": "off",
            "reasoningEffort": None,
            "extensionPolicy": "disabled",
            "skillsPolicy": "disabled",
            "contextFilePolicy": "disabled",
            "turnTimeoutSeconds": 420,
            "samplingPolicy": "provider-default-stochastic-repeated-trials",
            "withinCampaignExecutionProtocolQualified": True,
            "crossCampaignProviderReproducibilityQualified": False,
        }

    def test_plan_freezes_three_ordered_profiles_before_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = self.case(root)
            value = PLAN.derive(case, self.profiles(), "glm", 20, "b" * 40, 1234, self.protocol())
            self.assertEqual(value["status"], "predeclared-before-attempts")
            self.assertEqual(value["participantProfileCount"], 3)
            self.assertEqual(
                [row["ordinal"] for row in value["participantProfiles"]],
                [0, 1, 2],
            )
            self.assertEqual(value["trialsPerParticipant"], 20)
            self.assertFalse(value["automaticPromotion"])
            path = root / "plan.json"
            path.write_text(json.dumps(value, sort_keys=True) + "\n")
            self.assertEqual(PLAN.validate_plan(path), value)

    def test_plan_rejects_duplicate_models_and_posthoc_reordering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = self.case(root)
            profiles = self.profiles()
            profiles[1]["model"] = profiles[0]["model"]
            with self.assertRaisesRegex(PLAN.ExperimentPlanError, "model profile is duplicated"):
                PLAN.derive(case, profiles, "glm", 5, "b" * 40, 1234, self.protocol())

            value = PLAN.derive(case, self.profiles(), "glm", 5, "b" * 40, 1234, self.protocol())
            value["participantProfiles"][0], value["participantProfiles"][1] = (
                value["participantProfiles"][1],
                value["participantProfiles"][0],
            )
            path = root / "tampered-plan.json"
            path.write_text(json.dumps(value) + "\n")
            with self.assertRaisesRegex(PLAN.ExperimentPlanError, "order or ordinals differ"):
                PLAN.validate_plan(path)

    def test_execution_protocol_binds_actual_agent_runtime_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = ROOT / "examples/real-code-agent/participant/package-lock.json"
            runtime = root / "runtime.json"
            runtime.write_text(json.dumps({
                "schema": "agentlab.participant_docker_runtime.v1",
                "executor": "docker",
                "imageId": "sha256:" + "7" * 64,
                "piPackageLockSha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
                "participantManifestSha256": "8" * 64,
            }))
            value = PLAN.build_execution_protocol(
                ROOT / "examples/multi-repo-case/pi-assessed-agent.py",
                ROOT / "examples/real-code-agent/participant.py",
                lock,
                runtime,
            )
            self.assertTrue(value["withinCampaignExecutionProtocolQualified"])
            self.assertFalse(value["crossCampaignProviderReproducibilityQualified"])
            self.assertEqual(value["thinkingMode"], "off")
            self.assertEqual(value["turnTimeoutSeconds"], 420)

    def test_schema_and_workflows_bind_plan_before_outcomes(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/participant-experiment-plan.schema.json").read_text()
        )
        self.assertEqual(schema["properties"]["schema"]["const"], PLAN.SCHEMA)
        campaign = (ROOT / ".github/workflows/multi-repo-assessed-campaign.yml").read_text()
        scorecard = (ROOT / ".github/workflows/agent-suite-scorecard.yml").read_text()
        device_import = (ROOT / ".github/workflows/harmony-device-campaign-import.yml").read_text()
        self.assertIn("participant_profiles_json", campaign)
        self.assertIn("participant-experiment-plan.py create", campaign)
        self.assertIn("--participant-adapter", campaign)
        self.assertIn("--participant-driver", campaign)
        self.assertIn("--participant-package-lock", campaign)
        self.assertIn("--runtime-config", campaign)
        self.assertIn('--experiment-plan "$AGENTLAB_ROOT/participant-experiment-plan.json"', campaign)
        self.assertLess(
            campaign.index("Sign the pre-outcome participant experiment plan"),
            campaign.index("Run fresh staged attempts for every predeclared capability tier"),
        )
        self.assertNotIn("model_a:", campaign)
        self.assertNotIn("model_b:", campaign)
        self.assertNotIn("participant_order:", scorecard)
        self.assertIn("plan-attestation-verification.json", scorecard)
        self.assertIn("participant-experiment-plan.json", device_import)
        self.assertIn("Re-attest the pre-outcome participant experiment plan", device_import)


if __name__ == "__main__":
    unittest.main()
