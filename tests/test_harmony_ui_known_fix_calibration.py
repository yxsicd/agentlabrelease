from __future__ import annotations

import copy
import hashlib
import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate-harmony-ui-known-fix-calibration.py"
SPEC = importlib.util.spec_from_file_location("harmony_ui_known_fix_calibration", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def fixture(root: pathlib.Path) -> dict:
    patch = root / "known-fix.patch"
    patch.write_text("one-line calibration patch\n", encoding="utf-8")
    patch_sha = hashlib.sha256(patch.read_bytes()).hexdigest()
    scenario = root / "target.ui"
    scenario.write_text(
        "schema\tagentlab.harmony_ui_scenario.v1\n"
        "case\ttarget\n"
        "wait-text\tvisible\t30\tUserAgent_four\n"
        "tap\t628\t1606\n"
        "assert-text\ttarget-visible\tExample Domain\n",
        encoding="utf-8",
    )
    scenario_sha = hashlib.sha256(scenario.read_bytes()).hexdigest()
    preservation = root / "preservation.ui"
    preservation.write_text(
        "schema\tagentlab.harmony_ui_scenario.v1\n"
        "case\tpreservation\n"
        "wait-text\tdom-visible\t30\tDomStorage\n"
        "tap\t628\t1256\n"
        "assert-no-text\tindex-absent\tCache_two\n",
        encoding="utf-8",
    )
    preservation_sha = hashlib.sha256(preservation.read_bytes()).hexdigest()
    baseline_hap, fixed_hap = "a" * 64, "b" * 64
    authority = {"routeDecision": "peer_direct", "targetPeerId": "lgw_" + "1" * 32, "operationId": "exec-1", "traceIds": ["trace"]}
    def attempt(hap: str, scenario_digest: str, passed: bool, check_field: str = "repairCheckPassed") -> dict:
        status = "passed" if passed else "failed"
        return {
            "executionAuthority": copy.deepcopy(authority),
            "result": {
                "schema": "agentlab.harmony_emulator_case_result.v2", "status": status,
                "oracleStatus": status, "assessmentStatus": "assessed", "infrastructureAvailable": True,
                "subjectTaskSucceeded": passed, "failureClass": "none" if passed else "oracle",
                "hapSha256": hap, "scenarioSha256": scenario_digest,
            },
            "resultSha256": "c" * 64, "actionsSha256": "d" * 64, "checksSha256": "e" * 64,
            "layoutBeforeSha256": "f" * 64, "layoutAfterSha256": "0" * 64,
            check_field: passed,
        }
    baseline = attempt(baseline_hap, scenario_sha, False)
    baseline["observedPagePathAfter"] = "pages/Index"
    fixed = attempt(fixed_hap, scenario_sha, True)
    fixed["observedPagePathAfter"] = "pages/UserAgent_four"
    fixed["observedVisibleTextAfter"] = "Example Domain"
    baseline_preservation = attempt(baseline_hap, preservation_sha, True, "preservationCheckPassed")
    baseline_preservation["observedPagePathAfter"] = "pages/DomStorage"
    fixed_preservation = attempt(fixed_hap, preservation_sha, True, "preservationCheckPassed")
    fixed_preservation["observedPagePathAfter"] = "pages/DomStorage"
    return {
        "schema": "agentlab.harmony_ui_known_fix_calibration.v1",
        "status": "controlled-fail-to-pass-observed",
        "automaticPromotion": False,
        "baselineSource": {"revision": "1" * 40, "hapSha256": baseline_hap, "sourceIdentity": f"artifact-sha256:{baseline_hap}"},
        "knownFix": {
            "classification": "controlled-calibration-variant-not-gold", "revision": "2" * 40,
            "parentRevision": "1" * 40, "changedFiles": 1, "insertions": 1, "deletions": 0,
            "path": "project/entry/src/main/resources/base/profile/main_pages.json",
            "patchPath": "known-fix.patch", "patchSha256": patch_sha,
            "beforeFileSha256": "4" * 64, "afterFileSha256": "5" * 64,
            "hapSha256": fixed_hap, "hapBytes": 123, "sourceIdentity": f"artifact-sha256:{fixed_hap}",
        },
        "transfer": {"transport": "LAN HTTP", "verifiedSha256": fixed_hap, "verifiedBytes": 123},
        "scenario": {
            "path": "target.ui", "id": "target", "sha256": scenario_sha, "tap": [628, 1606],
            "repairAssertion": "Example Domain is visible after selecting UserAgent_four.",
        },
        "preservationScenario": {
            "path": "preservation.ui", "id": "preservation", "sha256": preservation_sha,
            "tap": [628, 1256], "preservationAssertion": "Index control is absent after DomStorage route.",
        },
        "supersededOracleFinding": {
            "falseFailure": True, "observedPagePath": "pages/UserAgent_four", "observedVisibleText": "Example Domain",
            "cause": "matched pagePath= metadata", "scenarioSha256": "6" * 64, "knownFixResultSha256": "7" * 64,
        },
        "rejectedPreservationAttempt": {
            "status": "failed", "infrastructureAvailable": True, "observedPagePath": "pages/DomStorage",
            "rejectionReason": "network assertion was environment-sensitive", "scenarioSha256": "8" * 64,
            "resultSha256": "9" * 64,
        },
        "baselineAttempt": baseline,
        "knownFixAttempt": fixed,
        "baselinePreservationAttempt": baseline_preservation,
        "knownFixPreservationAttempt": fixed_preservation,
        "qualificationMatrix": {
            "repairChecks": {"failToPassObserved": True, "sameScenario": True, "sameEnvironment": True},
            "preservationChecks": {"defined": True, "passToPassObserved": True, "sameScenario": True, "sameEnvironment": True},
            "review": {"independent": False, "knownFixAcceptedAsReference": False},
        },
        "qualificationScope": {
            "controlledKnownFix": True, "businessSemanticAssertionObserved": True, "candidateFailToPass": True,
            "businessUiOracleQualified": False, "independentReview": False, "referenceRepair": False,
            "preservationPassToPass": True, "performanceComparison": False,
        },
    }


class HarmonyUiKnownFixCalibrationTests(unittest.TestCase):
    def test_controlled_fail_to_pass_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.assertEqual(MODULE.validate(fixture(root), root)["status"], "controlled-fail-to-pass-observed")

    def test_same_scenario_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            value["knownFixAttempt"]["result"]["scenarioSha256"] = "8" * 64
            with self.assertRaisesRegex(MODULE.CalibrationError, "scenario differs"):
                MODULE.validate(value, root)

    def test_infrastructure_failure_is_not_fail_to_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            value["baselineAttempt"]["result"]["infrastructureAvailable"] = False
            with self.assertRaisesRegex(MODULE.CalibrationError, "infrastructure must be available"):
                MODULE.validate(value, root)

    def test_known_fix_cannot_be_promoted_to_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            value["qualificationMatrix"]["review"]["knownFixAcceptedAsReference"] = True
            with self.assertRaisesRegex(MODULE.CalibrationError, "non-reference"):
                MODULE.validate(value, root)

    def test_preservation_cannot_be_dropped_after_pass_to_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            value["qualificationScope"]["preservationPassToPass"] = False
            with self.assertRaisesRegex(MODULE.CalibrationError, "must be observed"):
                MODULE.validate(value, root)


if __name__ == "__main__":
    unittest.main()
