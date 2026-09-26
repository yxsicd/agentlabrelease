from __future__ import annotations

import copy
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate-harmony-source-build-preflight.py"
SPEC = importlib.util.spec_from_file_location("source_build_preflight", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def fixture() -> dict:
    return {
        "schema": "agentlab.harmony_source_build_preflight.v1",
        "status": "blocked-missing-toolchain",
        "qualified": False,
        "automaticPromotion": False,
        "executionAuthority": {
            "routeDecision": "peer_direct",
            "targetPeerId": "lgw_" + "a" * 32,
            "traceIds": ["trace-1"],
        },
        "toolchain": [
            {"name": "git", "required": True, "available": True},
            {"name": "hvigorw", "required": True, "available": False},
        ],
        "projects": [
            {
                "repositoryId": "sample",
                "revision": "b" * 40,
                "projectRoot": ".",
                "buildModule": "phone",
                "sourceBindings": [{"path": "build-profile.json5", "sha256": "c" * 64}],
            }
        ],
        "buildReceipt": None,
    }


class HarmonySourceBuildPreflightTests(unittest.TestCase):
    def test_missing_toolchain_is_valid_infrastructure_result(self) -> None:
        self.assertFalse(MODULE.validate(fixture())["qualified"])

    def test_blocked_status_cannot_hide_complete_toolchain(self) -> None:
        value = fixture()
        value["toolchain"][1]["available"] = True
        with self.assertRaisesRegex(MODULE.PreflightError, "requires a missing required tool"):
            MODULE.validate(value)

    def test_ready_status_cannot_hide_missing_toolchain(self) -> None:
        value = fixture()
        value["status"] = "build-ready"
        value["qualified"] = True
        with self.assertRaisesRegex(MODULE.PreflightError, "cannot have missing required tools"):
            MODULE.validate(value)

    def test_remote_evidence_requires_exact_direct_peer(self) -> None:
        value = fixture()
        value["executionAuthority"]["routeDecision"] = "fallback"
        with self.assertRaisesRegex(MODULE.PreflightError, "peer_direct"):
            MODULE.validate(value)

    def test_preflight_cannot_claim_build_receipt(self) -> None:
        value = copy.deepcopy(fixture())
        value["buildReceipt"] = {"artifact": "entry.hap"}
        with self.assertRaisesRegex(MODULE.PreflightError, "must not claim"):
            MODULE.validate(value)


if __name__ == "__main__":
    unittest.main()
