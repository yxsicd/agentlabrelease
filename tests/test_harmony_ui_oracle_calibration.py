from __future__ import annotations

import copy
import hashlib
import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate-harmony-ui-oracle-calibration.py"
SPEC = importlib.util.spec_from_file_location("harmony_ui_oracle_calibration", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def fixture(root: pathlib.Path) -> dict:
    scenario = root / "route.ui"
    scenario.write_text(
        "schema\tagentlab.harmony_ui_scenario.v1\ncase\troute\ntap\t628\t1606\nassert-no-text\tleft\tUserAgent_four\n",
        encoding="utf-8",
    )
    scenario_sha = hashlib.sha256(scenario.read_bytes()).hexdigest()
    hap = "a" * 64
    return {
        "schema": "agentlab.harmony_ui_oracle_calibration.v1",
        "status": "candidate-baseline-failure-observed",
        "automaticPromotion": False,
        "source": {"revision": "1" * 40, "hapSha256": hap, "sourceIdentity": f"artifact-sha256:{hap}"},
        "scenario": {"path": "route.ui", "id": "route", "sha256": scenario_sha, "intendedControl": "UserAgent_four", "tap": [628, 1606]},
        "layoutCalibration": {
            "decoyControl": "DomStorage",
            "controls": [
                {"label": "DomStorage", "bounds": [410, 1186, 847, 1326]},
                {"label": "UserAgent_four", "bounds": [369, 1536, 887, 1676]},
            ],
        },
        "rejectedAttempt": {
            "tap": [468, 1190], "observedPagePath": "pages/DomStorage", "runnerVerdict": "passed",
            "qualificationAccepted": False, "resultSha256": "b" * 64,
            "layoutBeforeSha256": "c" * 64, "layoutAfterSha256": "d" * 64,
        },
        "correctedBaselineAttempt": {
            "executionAuthority": {"routeDecision": "peer_direct", "targetPeerId": "lgw_" + "2" * 32, "operationId": "exec-1", "traceIds": ["trace"]},
            "result": {
                "schema": "agentlab.harmony_emulator_case_result.v2", "status": "failed",
                "oracleStatus": "failed", "assessmentStatus": "assessed", "infrastructureAvailable": True,
                "subjectTaskSucceeded": False, "failureClass": "oracle", "hapSha256": hap,
                "scenarioSha256": scenario_sha,
            },
            "resultSha256": "e" * 64, "layoutBeforeSha256": "f" * 64, "layoutAfterSha256": "f" * 64,
        },
        "qualificationScope": {
            "coordinateCalibration": True, "candidateFailToPass": True, "businessUiOracle": False,
            "independentReview": False, "referenceRepair": False, "performanceComparison": False,
        },
    }


class HarmonyUiOracleCalibrationTests(unittest.TestCase):
    def test_calibrated_candidate_baseline_failure_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.assertEqual(MODULE.validate(fixture(root), root)["status"], "candidate-baseline-failure-observed")

    def test_decoy_tap_cannot_be_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            value["rejectedAttempt"]["qualificationAccepted"] = True
            with self.assertRaisesRegex(MODULE.CalibrationError, "must not qualify"):
                MODULE.validate(value, root)

    def test_scenario_must_hit_intended_control(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            value["scenario"]["tap"] = [468, 1190]
            with self.assertRaisesRegex(MODULE.CalibrationError, "scenario file tap differs"):
                MODULE.validate(value, root)

    def test_infrastructure_failure_is_not_fail_to_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            value["correctedBaselineAttempt"]["result"]["infrastructureAvailable"] = False
            with self.assertRaisesRegex(MODULE.CalibrationError, "infrastructure must be available"):
                MODULE.validate(value, root)

    def test_candidate_cannot_claim_independent_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = copy.deepcopy(fixture(root))
            value["qualificationScope"]["independentReview"] = True
            with self.assertRaisesRegex(MODULE.CalibrationError, "must remain unqualified"):
                MODULE.validate(value, root)


if __name__ == "__main__":
    unittest.main()
