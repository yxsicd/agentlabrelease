from __future__ import annotations

import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "case_discrimination", ROOT / "scripts/score-case-discrimination.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class CaseDiscriminationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.value = json.loads(
            (ROOT / "examples/case-discrimination/fixture.json").read_text()
        )

    def test_repeatable_separation_ranks_first(self) -> None:
        report = MODULE.build_report(self.value, 3, 0.6)
        first = report["ranking"][0]
        self.assertEqual(first["caseId"], "case-strong-separation")
        self.assertEqual(first["metrics"]["passRateSeparation"], 1.0)
        self.assertEqual(first["metrics"]["withinProfileDeterminism"], 1.0)
        self.assertEqual(first["metrics"]["trialConfidence"], 1.0)
        self.assertEqual(first["metrics"]["discriminationScore"], 1.0)
        self.assertFalse(first["metrics"]["observedExtremePassRateWilson95Separated"])
        self.assertFalse(first["processMeasurement"]["coverageQualified"])
        self.assertFalse(first["processAwareEligible"])
        self.assertTrue(first["eligible"])
        self.assertFalse(report["policy"]["automaticPromotion"])

    def test_everyone_passing_is_not_discriminating(self) -> None:
        report = MODULE.build_report(self.value, 3, 0.6)
        row = next(r for r in report["ranking"] if r["caseId"] == "case-everyone-passes")
        self.assertEqual(row["metrics"]["passRateSeparation"], 0.0)
        self.assertFalse(row["eligible"])
        self.assertEqual(row["decision"], "low-discrimination-candidate")

    def test_infrastructure_failure_is_excluded_not_scored_as_inability(self) -> None:
        report = MODULE.build_report(self.value, 3, 0.6)
        row = next(r for r in report["ranking"] if r["caseId"] == "case-infrastructure-excluded")
        self.assertEqual(row["excludedAttemptCount"], 1)
        self.assertEqual(row["validAttemptCount"], 2)
        self.assertEqual(row["decision"], "collect-more-evidence")

    def test_failed_negative_calibration_rejects_case(self) -> None:
        case = self.value["cases"][0]
        case["calibration"]["negativeVariants"][0]["observedPass"] = True
        row = MODULE.score_case(case, 3, 0.6)
        self.assertFalse(row["calibrationPassed"])
        self.assertFalse(row["eligible"])
        self.assertEqual(row["decision"], "reject-oracle-calibration")

    def test_duplicate_attempt_identity_is_rejected(self) -> None:
        case = self.value["cases"][0]
        case["attempts"][1]["attemptId"] = case["attempts"][0]["attemptId"]
        with self.assertRaisesRegex(ValueError, "attemptId must be unique"):
            MODULE.score_case(case, 3, 0.6)

    def test_unfenced_source_revision_is_rejected(self) -> None:
        self.value["sourceRevision"] = "main"
        with self.assertRaisesRegex(ValueError, "sourceRevision must be"):
            MODULE.build_report(self.value, 3, 0.6)

    def test_operator_process_coverage_and_statistical_separation_are_explicit(self) -> None:
        process = {
            "schema": "agentlab.assessment_process_measurement.v1",
            "stageCount": 2,
            "participantCompletedStageCount": 2,
            "oracleExecutedStageCount": 2,
            "oraclePassedStageCount": 2,
            "scopeViolationStageCount": 0,
            "changedPathCount": 2,
            "unauthorizedPathCount": 0,
            "oracleRecoveryCount": 0,
            "oracleRegressionCount": 0,
            "participantDurationMs": 10,
            "oracleDurationMs": 4,
            "stageDurationMs": 16,
            "attemptDurationMs": 20,
            "processMeasurementQualified": True,
            "participantSelfAssessment": {
                "schema": "agentlab.participant_self_assessment_summary.v1",
                "stageCount": 2,
                "reportedStageCount": 2,
                "comparableStageCount": 2,
                "agreementCount": 2,
                "coverageRate": 1.0,
                "agreementRate": 1.0,
                "meanBrierScore": 0.04,
                "coverageQualified": True,
                "authority": "participant-claim-compared-with-operator-oracle-not-a-verdict",
            },
            "dependencyDiscovery": {
                "schema": "agentlab.dependency_discovery_summary.v1",
                "stageCount": 2,
                "measuredStageCount": 2,
                "missingStageCount": 0,
                "invalidStageCount": 0,
                "claimCount": 3,
                "obligationCount": 2,
                "coveredObligationCount": 2,
                "requiredObligationCoverage": 1.0,
                "coverageQualified": True,
                "unadjudicatedClaimCount": 1,
                "precisionClaimed": False,
                "authority": "hidden-revision-bound-program-fact-obligations-not-gold-path-imitation",
            },
        }
        case = self.value["cases"][0]
        case["attempts"] = []
        for participant, passed in (("strong", True), ("weak", False)):
            for trial in range(5):
                case["attempts"].append(
                    {
                        "attemptId": f"{participant}-{trial}",
                        "participantId": participant,
                        "infrastructureValid": True,
                        "taskPassed": passed,
                        "processMeasurement": process,
                    }
                )
        row = MODULE.score_case(case, 5, 0.6)
        self.assertTrue(row["eligible"])
        self.assertTrue(row["processAwareEligible"])
        self.assertTrue(row["processMeasurement"]["coverageQualified"])
        self.assertTrue(
            row["processMeasurement"]["participantSelfAssessment"]["coverageQualified"]
        )
        self.assertEqual(
            row["processMeasurement"]["participantSelfAssessment"]["agreementRate"],
            1.0,
        )
        self.assertEqual(
            row["processMeasurement"]["participantSelfAssessment"]["meanBrierScore"],
            0.04,
        )
        dependency = row["processMeasurement"]["dependencyDiscovery"]
        self.assertTrue(dependency["measurementCoverageQualified"])
        self.assertTrue(dependency["coverageQualified"])
        self.assertEqual(dependency["requiredObligationCoverage"], 1.0)
        self.assertEqual(dependency["unadjudicatedClaimCount"], 10)
        self.assertFalse(dependency["precisionClaimed"])
        self.assertTrue(row["metrics"]["observedExtremePassRateWilson95Separated"])
        strong = next(
            profile
            for profile in row["participantProfiles"]
            if profile["participantId"] == "strong"
        )
        weak = next(
            profile
            for profile in row["participantProfiles"]
            if profile["participantId"] == "weak"
        )
        self.assertGreater(
            strong["passRateWilson95"]["lower"],
            weak["passRateWilson95"]["upper"],
        )


if __name__ == "__main__":
    unittest.main()
