import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cbgroom-refresh-claims.py"
SPEC = importlib.util.spec_from_file_location("cbgroom_refresh_claims", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class ClaimEnvironmentIndependenceTest(unittest.TestCase):
    def test_one_evidence_run_can_have_multiple_explicit_environments(self):
        checkpoints = [{
            "row": {
                "id": "checkpoint-35030815942-turn-1",
                "sourceCut": "cut",
                "nativeSessionSha256": "session",
                "nativeThreadId": "thread",
            }
        }]
        environments = [
            {"row": {
                "id": "environment-35030815942-github",
                "runId": "35030815942",
                "runnerIdentity": "gha|Linux|X64|x86_64",
                "runnerName": "gha",
                "runnerOs": "Linux",
                "runnerArch": "X64",
                "metadata": {},
            }},
            {"row": {
                "id": "environment-35030815942-hwlinux",
                "runId": "35030815942",
                "runnerIdentity": "hwlinux|Linux|X64|x86_64",
                "runnerName": "hwlinux",
                "runnerOs": "Linux",
                "runnerArch": "X64",
                "metadata": {"claimIndependenceEligible": True},
            }},
            {"row": {
                "id": "environment-35030815942-diagnostic-only",
                "runId": "35030815942",
                "runnerIdentity": "diagnostic|Linux|X64|x86_64",
                "runnerName": "diagnostic",
                "runnerOs": "Linux",
                "runnerArch": "X64",
                "metadata": {"claimIndependenceEligible": False},
            }},
        ]

        summary, rows = MODULE.classify_evidence(
            "claim",
            ["decision-35030815942-compiler-feedback"],
            [],
            checkpoints,
            environments,
            "rev",
        )

        self.assertEqual(summary["uniqueExecutionEnvironments"], 2)
        self.assertEqual(summary["runnerIndependence"], "multiple-recorded-runner-environments")
        self.assertEqual(rows[0]["runnerIndependence"], "multiple-environments-on-evidence")
        self.assertEqual(
            rows[0]["metadata"]["runnerIdentities"],
            ["gha|Linux|X64|x86_64", "hwlinux|Linux|X64|x86_64"],
        )
        self.assertEqual(
            rows[0]["metadata"]["executionEnvironmentIds"],
            ["environment-35030815942-github", "environment-35030815942-hwlinux"],
        )


if __name__ == "__main__":
    unittest.main()
