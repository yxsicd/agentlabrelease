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
    alternative_patch = root / "alternative.patch"
    alternative_patch.write_text("structurally distinct named-route patch\n", encoding="utf-8")
    alternative_patch_sha = hashlib.sha256(alternative_patch.read_bytes()).hexdigest()
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
    user_agent_one = root / "user-agent-one.ui"
    user_agent_one.write_text(
        "schema\tagentlab.harmony_ui_scenario.v1\n"
        "case\tuser-agent-one\n"
        "wait-text\tvisible\t30\tUserAgent_one\n"
        "tap\t628\t206\n"
        "assert-text\tbutton-visible\tgetUserAgent\n",
        encoding="utf-8",
    )
    user_agent_one_sha = hashlib.sha256(user_agent_one.read_bytes()).hexdigest()
    cache_two = root / "cache-two.ui"
    cache_two.write_text(
        "schema\tagentlab.harmony_ui_scenario.v1\n"
        "case\tcache-two\n"
        "wait-text\tvisible\t30\tCache_two\n"
        "tap\t628\t1081\n"
        "assert-text\tbutton-visible\tremoveCache\n",
        encoding="utf-8",
    )
    cache_two_sha = hashlib.sha256(cache_two.read_bytes()).hexdigest()
    baseline_hap, fixed_hap, alternative_hap = "a" * 64, "b" * 64, "3" * 64
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
    alternative = attempt(alternative_hap, scenario_sha, True)
    alternative["observedPagePathAfter"] = "pages/UserAgent_four"
    alternative["observedVisibleTextAfter"] = "Example Domain"
    baseline_preservation = attempt(baseline_hap, preservation_sha, True, "preservationCheckPassed")
    baseline_preservation["observedPagePathAfter"] = "pages/DomStorage"
    fixed_preservation = attempt(fixed_hap, preservation_sha, True, "preservationCheckPassed")
    fixed_preservation["observedPagePathAfter"] = "pages/DomStorage"
    alternative_preservation = attempt(alternative_hap, preservation_sha, True, "preservationCheckPassed")
    alternative_preservation["observedPagePathAfter"] = "pages/DomStorage"
    def preservation_case(
        case_id: str,
        path: str,
        scenario_digest: str,
        tap: list[int],
        text: str,
        page: str,
        assertion_kind: str = "assert-text",
    ) -> dict:
        baseline_attempt = attempt(baseline_hap, scenario_digest, True, "preservationCheckPassed")
        baseline_attempt.update(observedPagePathAfter=page, observedVisibleTextAfter=text)
        fixed_attempt = attempt(fixed_hap, scenario_digest, True, "preservationCheckPassed")
        fixed_attempt.update(observedPagePathAfter=page, observedVisibleTextAfter=text)
        alternative_attempt = attempt(alternative_hap, scenario_digest, True, "preservationCheckPassed")
        alternative_attempt.update(observedPagePathAfter=page, observedVisibleTextAfter=text)
        return {
            "id": case_id,
            "scenario": {
                "path": path, "id": case_id, "sha256": scenario_digest, "tap": tap,
                "assertionKind": assertion_kind, "assertionText": text, "expectedPagePath": page,
            },
            "baselineAttempt": baseline_attempt,
            "knownFixAttempt": fixed_attempt,
            "alternativeValidAttempt": alternative_attempt,
        }
    extra_cases = []
    for case_id, filename, tap, assertion_kind, text, page in [
        ("user-agent-two", "user-agent-two.ui", [628, 381], "assert-no-text", "Cache_two", "pages/UserAgent_two"),
        ("user-agent-three", "user-agent-three.ui", [628, 556], "assert-text", "getCustomUserAgent", "pages/UserAgent_three"),
        ("cookie-management", "cookie-management.ui", [628, 731], "assert-text", "configCookieSync", "pages/CookieManagement"),
        ("cache-one", "cache-one.ui", [628, 906], "assert-no-text", "Cache_two", "pages/Cache_one"),
        ("use-motion-dir-sensor", "use-motion.ui", [628, 1431], "assert-no-text", "Cache_two", "pages/UseMotionDirSensor"),
    ]:
        path = root / filename
        path.write_text(
            "schema\tagentlab.harmony_ui_scenario.v1\n"
            f"case\t{case_id}\n"
            f"wait-text\tvisible\t30\t{case_id}\n"
            f"tap\t{tap[0]}\t{tap[1]}\n"
            f"{assertion_kind}\tsemantic\t{text}\n",
            encoding="utf-8",
        )
        extra_cases.append(
            preservation_case(
                case_id,
                filename,
                hashlib.sha256(path.read_bytes()).hexdigest(),
                tap,
                text,
                page,
                assertion_kind,
            )
        )
    return {
        "schema": "agentlab.harmony_ui_known_fix_calibration.v3",
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
        "alternativeValid": {
            "id": "named-route", "classification": "controlled-alternative-valid-not-gold",
            "sourceRevision": "1" * 40, "changedFiles": 2, "insertions": 5, "deletions": 5,
            "paths": ["project/entry/src/main/ets/pages/Index.ets", "project/entry/src/main/ets/pages/UserAgent_four.ets"],
            "referenceOverlapPaths": [], "patchPath": "alternative.patch", "patchSha256": alternative_patch_sha,
            "routeMechanism": "ArkUI named route", "baselineMainPagesSha256": "4" * 64,
            "alternativeMainPagesSha256": "4" * 64,
            "afterFileSha256": {
                "project/entry/src/main/ets/pages/Index.ets": "6" * 64,
                "project/entry/src/main/ets/pages/UserAgent_four.ets": "7" * 64,
            },
            "hapSha256": alternative_hap, "hapBytes": 124,
            "sourceIdentity": f"artifact-sha256:{alternative_hap}",
            "build": {"status": "successful"},
            "transfer": {
                "transport": "AWMCP RGW HTTP binary stream", "fromPeerId": "lgw_" + "2" * 32,
                "toPeerId": "lgw_" + "1" * 32, "verifiedSha256": alternative_hap, "verifiedBytes": 124,
            },
        },
        "transfer": {"transport": "LAN HTTP", "verifiedSha256": fixed_hap, "verifiedBytes": 123},
        "scenario": {
            "path": "target.ui", "id": "target", "sha256": scenario_sha, "tap": [628, 1606],
            "repairAssertion": "Example Domain is visible after selecting UserAgent_four.",
        },
        "preservationScenario": {
            "path": "preservation.ui", "id": "preservation", "sha256": preservation_sha,
            "tap": [628, 1256], "assertionKind": "assert-no-text", "assertionText": "Cache_two",
            "expectedPagePath": "pages/DomStorage", "preservationAssertion": "Index control is absent after DomStorage route.",
        },
        "additionalPreservationCases": [
            preservation_case("user-agent-one", "user-agent-one.ui", user_agent_one_sha, [628, 206], "getUserAgent", "pages/UserAgent_one"),
            preservation_case("cache-two", "cache-two.ui", cache_two_sha, [628, 1081], "removeCache", "pages/Cache_two"),
            *extra_cases,
        ],
        "expandedPreservationCampaign": {
            "executedAt": "2026-09-25",
            "runner": {
                "path": "/home/huawei/agentlab-source-builds/agentlab-harmony-emulator-stop-ready-7f7a9b00.sh",
                "sha256": "7f7a9b005d6d86ca0ef0f9d5778ec7056ec3f2faed9c020fbe6436379bcc8d26",
            },
            "oldRunnerFailure": {
                "operationId": "exec-000000000000027b", "passed": 8, "infrastructureFailed": 7,
                "classification": "emulator-stop-readiness",
            },
            "fixedRunner": {
                "operationId": "exec-000000000000028b", "traceIds": ["trace-a", "trace-b"],
                "passed": 15, "failed": 0, "durationMs": 647982, "allConsecutive": True,
            },
            "scenarioCount": 5,
            "variantCount": 3,
        },
        "freshness": {
            "schema": "agentlab.case_freshness.v1", "constructionMode": "synthetic-controlled-calibration",
            "sourceRepositoryVisibility": "public", "sourceRevisionCommittedAt": "2026-09-12T15:18:36+08:00",
            "caseConstructedAt": "2026-09-24", "historicalIssueMined": False, "historicalFixMined": False,
            "controlledFixCreatedForCalibration": True, "controlledFixPublishedInReleasePr": True,
            "assessedParticipantRun": False, "hiddenOracleDuringCalibration": True,
            "modelTrainingExclusionKnown": False, "contaminationRisk": "unknown-after-publication",
            "eligibleForUnseenAgentDiscrimination": False,
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
        "alternativeValidAttempt": alternative,
        "baselinePreservationAttempt": baseline_preservation,
        "knownFixPreservationAttempt": fixed_preservation,
        "alternativeValidPreservationAttempt": alternative_preservation,
        "qualificationMatrix": {
            "repairChecks": {"failToPassObserved": True, "sameScenario": True, "sameEnvironment": True},
            "preservationChecks": {
                "defined": True, "passToPassObserved": True, "sameScenario": True, "sameEnvironment": True,
                "caseCount": 8, "positiveVisibleSemanticCaseCount": 4,
                "caseIds": [
                    "preservation", "user-agent-one", "cache-two", "user-agent-two",
                    "user-agent-three", "cookie-management", "cache-one", "use-motion-dir-sensor",
                ],
            },
            "routeCoverage": {
                "indexRouteCount": 9, "targetRouteCount": 1, "preservationRouteCount": 8,
                "allIndexRoutesCovered": True, "variantPreservationRuns": 24,
                "routeIds": [
                    "UserAgent_one", "UserAgent_two", "UserAgent_three", "CookieManagement",
                    "Cache_one", "Cache_two", "DomStorage", "UseMotionDirSensor", "UserAgent_four",
                ],
                "baselineIndexSha256": "a" * 64,
                "knownFixIndexSha256": "a" * 64,
                "alternativeIndexSha256": "6" * 64,
            },
            "oracleBreadth": {
                "alternativeValidDefined": True, "structurallyDistinctFromKnownFix": True,
                "referenceOverlapPathCount": 0, "baselineMainPagesUnchanged": True,
                "repairPassed": True, "preservationPassed": True, "preservationCaseCount": 8,
                "deviceScenarioCount": 9, "allDeviceScenariosPassed": True,
            },
            "review": {"independent": False, "knownFixAcceptedAsReference": False},
        },
        "qualificationScope": {
            "controlledKnownFix": True, "businessSemanticAssertionObserved": True, "candidateFailToPass": True,
            "businessUiOracleQualified": False, "independentReview": False, "referenceRepair": False,
            "preservationPassToPass": True, "completeExistingRoutePreservation": True,
            "freshnessDeclared": True,
            "alternativeValidQualified": True,
            "unseenAgentDiscrimination": False, "performanceComparison": False,
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

    def test_preservation_case_ids_must_be_unique(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            value["additionalPreservationCases"][1]["id"] = "user-agent-one"
            value["additionalPreservationCases"][1]["scenario"]["id"] = "user-agent-one"
            with self.assertRaisesRegex(MODULE.CalibrationError, "case id differs|ids must be unique"):
                MODULE.validate(value, root)

    def test_public_calibration_cannot_claim_unseen_discrimination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            value["freshness"]["eligibleForUnseenAgentDiscrimination"] = True
            with self.assertRaisesRegex(MODULE.CalibrationError, "unseen-Agent discrimination"):
                MODULE.validate(value, root)

    def test_alternative_valid_target_failure_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            value["alternativeValidAttempt"]["result"]["status"] = "failed"
            with self.assertRaisesRegex(MODULE.CalibrationError, "status must be passed"):
                MODULE.validate(value, root)

    def test_alternative_valid_cannot_overlap_known_fix_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            known_path = value["knownFix"]["path"]
            original = value["alternativeValid"]["paths"][0]
            value["alternativeValid"]["paths"][0] = known_path
            value["alternativeValid"]["afterFileSha256"][known_path] = value["alternativeValid"]["afterFileSha256"].pop(original)
            with self.assertRaisesRegex(MODULE.CalibrationError, "must not overlap"):
                MODULE.validate(value, root)

    def test_alternative_valid_must_leave_main_pages_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            value["alternativeValid"]["alternativeMainPagesSha256"] = "8" * 64
            with self.assertRaisesRegex(MODULE.CalibrationError, "byte-identical"):
                MODULE.validate(value, root)

    def test_alternative_valid_preservation_failure_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            del value["additionalPreservationCases"][0]["alternativeValidAttempt"]
            with self.assertRaisesRegex(MODULE.CalibrationError, "alternative valid is required"):
                MODULE.validate(value, root)

    def test_scenario_assertion_must_match_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            value["additionalPreservationCases"][0]["scenario"]["assertionText"] = "forged"
            with self.assertRaisesRegex(MODULE.CalibrationError, "assertion text differs"):
                MODULE.validate(value, root)

    def test_fixed_runner_replay_must_retain_all_fifteen_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            value = fixture(root)
            value["expandedPreservationCampaign"]["fixedRunner"]["passed"] = 14
            with self.assertRaisesRegex(MODULE.CalibrationError, "fixed-runner result counts differ"):
                MODULE.validate(value, root)


if __name__ == "__main__":
    unittest.main()
