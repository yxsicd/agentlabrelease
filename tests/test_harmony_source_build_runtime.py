from __future__ import annotations

import copy
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate-harmony-source-build-runtime.py"
SPEC = importlib.util.spec_from_file_location("source_build_runtime", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def fixture() -> dict:
    first = "a" * 64
    return {
        "schema": "agentlab.harmony_source_build_runtime_qualification.v1",
        "status": "baseline-build-runtime-qualified",
        "automaticPromotion": False,
        "source": {"repositoryId": "guide", "revision": "1" * 40, "projectRoot": "sample", "buildModule": "entry"},
        "build": {
            "status": "successful",
            "cleanBuilds": 2,
            "rawArchiveReproducible": False,
            "memberContentReproducible": True,
            "attempts": [
                {"hapSha256": first, "hapBytes": 10, "canonicalMemberSha256": "c" * 64, "memberCount": 2, "buildLogSha256": None},
                {"hapSha256": "b" * 64, "hapBytes": 10, "canonicalMemberSha256": "c" * 64, "memberCount": 2, "buildLogSha256": "d" * 64},
            ],
        },
        "linuxRuntime": {
            "executionAuthority": {"routeDecision": "peer_direct", "targetPeerId": "lgw_" + "2" * 32, "operationId": "exec-1", "traceIds": ["trace"]},
            "result": {"schema": "agentlab.harmony_emulator_case_result.v1", "status": "passed", "hapSha256": first, "resultSha256": "e" * 64, "screenshotSha256": "f" * 64, "installSucceeded": True, "launchSucceeded": True, "processAlive": True},
        },
        "qualificationScope": {"baselineBuild": True, "linuxInstallLaunchProcess": True, "businessUiOracle": False, "referenceRepair": False, "performanceComparison": False},
    }


class HarmonySourceBuildRuntimeTests(unittest.TestCase):
    def test_qualified_cross_host_baseline_is_accepted(self) -> None:
        self.assertEqual(MODULE.validate(fixture())["status"], "baseline-build-runtime-qualified")

    def test_runtime_must_use_one_exact_build_artifact(self) -> None:
        value = fixture()
        value["linuxRuntime"]["result"]["hapSha256"] = "9" * 64
        with self.assertRaisesRegex(MODULE.QualificationError, "one of the clean-build artifacts"):
            MODULE.validate(value)

    def test_member_drift_is_rejected(self) -> None:
        value = fixture()
        value["build"]["attempts"][1]["canonicalMemberSha256"] = "8" * 64
        with self.assertRaisesRegex(MODULE.QualificationError, "identical member content"):
            MODULE.validate(value)

    def test_raw_reproducibility_must_match_archive_digests(self) -> None:
        value = fixture()
        value["build"]["rawArchiveReproducible"] = True
        with self.assertRaisesRegex(MODULE.QualificationError, "does not match"):
            MODULE.validate(value)

    def test_v1_smoke_cannot_claim_business_oracle(self) -> None:
        value = copy.deepcopy(fixture())
        value["qualificationScope"]["businessUiOracle"] = True
        with self.assertRaisesRegex(MODULE.QualificationError, "cannot qualify"):
            MODULE.validate(value)


if __name__ == "__main__":
    unittest.main()
