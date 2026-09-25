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


SCORER = load_module("suite_fixture_discrimination", ROOT / "scripts/score-case-discrimination.py")
SUITE = load_module("agent_suite_scorecard", ROOT / "scripts/compose-agent-suite-scorecard.py")


def process(*, self_assessment: bool = False, dependency_discovery: bool = False) -> dict:
    value = {
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
        "participantDurationMs": 20,
        "oracleDurationMs": 4,
        "stageDurationMs": 26,
        "attemptDurationMs": 30,
        "processMeasurementQualified": True,
    }
    if self_assessment:
        value["participantSelfAssessment"] = {
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
        }
    if dependency_discovery:
        value["dependencyDiscovery"] = {
            "schema": "agentlab.dependency_discovery_summary.v1",
            "stageCount": 2,
            "measuredStageCount": 2,
            "missingStageCount": 0,
            "invalidStageCount": 0,
            "claimCount": 2,
            "obligationCount": 2,
            "coveredObligationCount": 2,
            "requiredObligationCoverage": 1.0,
            "coverageQualified": True,
            "unadjudicatedClaimCount": 0,
            "precisionClaimed": False,
            "authority": "hidden-revision-bound-program-fact-obligations-not-gold-path-imitation",
        }
    return value


def harmony_stage_coverage(passed: bool) -> dict:
    return {
        "schema": "agentlab.assessment_stage_coverage.v1",
        "stageIds": ["static", "harmony-device"],
        "harmonyDevice": {
            "executed": True,
            "oraclePass": passed,
            "profileCollected": passed,
            "smartPerfSampleCount": 3 if passed else 0,
        },
    }


class AgentSuiteScorecardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source_sets = {"case-a": "a" * 64, "case-b": "b" * 64}
        self.population = self.root / "population.json"
        self.write_population()
        self.population_attestation = self.root / "population-attestation.json"
        self.write_attestation(self.population_attestation, self.population, 9001)
        self.reports = {}
        self.report_attestations = {}
        for index, case_id in enumerate(self.source_sets, 1):
            self.reports[case_id] = self.write_discrimination(case_id, index)
            verification = self.root / f"report-{index}-attestation.json"
            self.write_attestation(verification, self.reports[case_id], 2000 + index)
            self.report_attestations[case_id] = verification
        self.manifest = self.root / "manifest.json"
        self.write_manifest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_population(self, *, unqualified: str | None = None) -> None:
        cases = []
        for index, (case_id, source_set) in enumerate(self.source_sets.items(), 1):
            qualified = case_id != unqualified
            cases.append(
                {
                    "caseId": case_id,
                    "sourceSetSha256": source_set,
                    "adjudicationRunId": 1000 + index,
                    "blindPilotReviewQualified": qualified,
                    "modelTrainingExclusionQualified": False,
                    "eligibleForUnseenAgentDiscrimination": False,
                    "bundleEvidence": {
                        "adjudication": {
                            "path": "authenticated-adjudication.json",
                            "sha256": f"{index:064x}",
                            "byteLength": 100,
                        }
                    },
                }
            )
        value = {
            "schema": "agentlab.blind_review_population_report.v1",
            "cohortId": "reviewed-cohort",
            "methodRevision": "f" * 40,
            "caseMembershipSha256": "c" * 64,
            "denominators": {"caseCount": len(cases)},
            "cases": cases,
            "qualification": {
                "allCasesAuthenticatedAndAttested": True,
                "populationRepresentativenessQualified": False,
                "modelTrainingExclusionQualified": False,
                "eligibleForUnseenAgentDiscrimination": False,
            },
            "policy": {"automaticPromotion": False},
        }
        self.population.write_text(json.dumps(value, indent=2))

    def write_cohort_bound_population(self) -> None:
        cohort_evidence = self.root / "candidate-cohort.json"
        cohort_evidence.write_text('{"schema":"agentlab.multi_repo_candidate_cohort.v1"}\n')
        value = json.loads(self.population.read_text())
        value["schema"] = "agentlab.blind_review_population_report.v2"
        for index, row in enumerate(value["cases"]):
            row["candidateId"] = f"candidate-{'ab'[index]}"
        value["denominators"].update({
            "selectedCandidateCount": 3,
            "adjudicatedCandidateCount": 2,
            "unadjudicatedCandidateCount": 1,
            "caseYieldRate": 2 / 3,
        })
        value["qualification"]["candidateCohortMembershipQualified"] = True
        value["candidateCohort"] = {
            "cohortId": value["cohortId"],
            "sourceSetSha256": "a" * 64,
            "methodRevision": value["methodRevision"],
            "selectedCandidateIds": ["candidate-a", "candidate-b", "candidate-c"],
            "adjudicatedCandidateIds": ["candidate-a", "candidate-b"],
            "unadjudicatedCandidateIds": ["candidate-c"],
            "evidence": {
                "path": cohort_evidence.name,
                "sha256": hashlib.sha256(cohort_evidence.read_bytes()).hexdigest(),
                "byteLength": cohort_evidence.stat().st_size,
            },
            "declaredRepresentative": False,
        }
        self.population.write_text(json.dumps(value, indent=2))

    def write_attestation(self, output: Path, subject: Path, run_id: int) -> None:
        output.write_text(
            json.dumps(
                [
                    {
                        "verificationResult": {
                            "statement": {
                                "predicateType": "https://slsa.dev/provenance/v1",
                                "subject": [
                                    {
                                        "name": subject.name,
                                        "digest": {
                                            "sha256": hashlib.sha256(
                                                subject.read_bytes()
                                            ).hexdigest()
                                        },
                                    }
                                ],
                                "predicate": {
                                    "runDetails": {
                                        "metadata": {
                                            "invocationId": f"https://github.com/example/agentlab/actions/runs/{run_id}/attempts/1"
                                        }
                                    }
                                },
                            }
                        }
                    }
                ]
            )
        )

    def write_discrimination(
        self,
        case_id: str,
        ordinal: int,
        *,
        reverse: bool = False,
        process_evidence: bool = True,
        self_assessment: bool = False,
        dependency_discovery: bool = False,
        tier_outcomes: dict[str, list[bool]] | None = None,
    ) -> Path:
        calibration = {
            "infrastructureValid": True,
            "baselineExpectedPass": False,
            "baselineObservedPass": False,
            "referenceExpectedPass": True,
            "referenceObservedPass": True,
            "negativeVariants": [
                {
                    "id": "wrong-repair",
                    "expectedPass": False,
                    "observedPass": False,
                    "infrastructureValid": True,
                }
            ],
        }
        attempts = []
        if tier_outcomes is None:
            tier_outcomes = {
                "weak": [True if reverse else False] * 5,
                "strong": [False if reverse else True] * 5,
            }
        for participant, outcomes in tier_outcomes.items():
            for trial, passed in enumerate(outcomes):
                attempt = {
                    "attemptId": f"{case_id}-{participant}-{trial}",
                    "participantId": participant,
                    "infrastructureValid": True,
                    "taskPassed": passed,
                }
                if process_evidence:
                    attempt["processMeasurement"] = process(
                        self_assessment=self_assessment,
                        dependency_discovery=dependency_discovery,
                    )
                    attempt["stageCoverage"] = harmony_stage_coverage(passed)
                attempts.append(attempt)
        report = SCORER.build_report(
            {
                "schema": "agentlab.case_discrimination_input.v2",
                "sourceSetSha256": self.source_sets[case_id],
                "methodRevision": "d" * 40,
                "cases": [{"id": case_id, "calibration": calibration, "attempts": attempts}],
            },
            5,
            0.6,
        )
        path = self.root / f"report-{ordinal}.json"
        path.write_text(json.dumps(report, indent=2))
        return path

    def write_manifest(self, *, case_ids: list[str] | None = None) -> None:
        selected = case_ids or list(self.source_sets)
        value = {
            "schema": "agentlab.agent_suite_scorecard_manifest.v1",
            "suiteId": "suite-one",
            "methodRevision": "e" * 40,
            "reviewPopulation": {
                "workflowRunId": 9001,
                "workflowRunAttempt": 1,
                "workflowHeadSha": "f" * 40,
                "report": self.population.name,
                "attestationVerification": self.population_attestation.name,
            },
            "participantOrder": ["weak", "strong"],
            "cases": [
                {
                    "caseId": case_id,
                    "assessedCampaignRunId": 2000 + index,
                    "assessedCampaignRunAttempt": 1,
                    "assessedCampaignWorkflowHeadSha": "d" * 40,
                    "discriminationReport": self.reports[case_id].name,
                    "discriminationAttestationVerification": self.report_attestations[
                        case_id
                    ].name,
                }
                for index, case_id in enumerate(selected, 1)
            ],
        }
        self.manifest.write_text(json.dumps(value, indent=2))

    def test_review_outcome_and_process_form_one_scorecard(self) -> None:
        value = SUITE.build_scorecard(self.manifest)
        self.assertEqual(value["denominators"]["caseCount"], 2)
        self.assertEqual(value["denominators"]["qualifiedCaseCount"], 2)
        self.assertEqual(value["denominators"]["validAttemptCount"], 20)
        self.assertTrue(value["qualification"]["suiteMeasurementQualified"])
        self.assertEqual(value["qualification"]["qualifiedCaseRate"], 1.0)
        self.assertFalse(value["qualification"]["benchmarkPopulationQualified"])
        self.assertFalse(value["qualification"]["eligibleForUnseenAgentDiscrimination"])
        self.assertTrue(all(row["reviewQualified"] for row in value["cases"]))
        self.assertTrue(
            all(row["strongestWeakestWilson95Separated"] for row in value["cases"])
        )
        self.assertFalse(
            value["qualification"]["dependencyDiscoveryMeasurementQualified"]
        )
        self.assertFalse(
            value["qualification"]["dependencyDiscoveryCoverageQualified"]
        )
        self.assertFalse(
            value["qualification"]["participantSelfAssessmentMeasurementQualified"]
        )
        self.assertTrue(value["qualification"]["harmonyEndToEndEvidenceQualified"])
        self.assertTrue(
            all(row["harmonyEndToEndEvidenceQualified"] for row in value["cases"])
        )
        self.assertFalse(
            value["qualification"]["capabilityResolutionMeasurementQualified"]
        )
        self.assertEqual(value["denominators"]["participantTierCount"], 2)
        self.assertTrue(all(
            row["capabilityResolution"]["status"]
            == "insufficient-participant-tiers"
            for row in value["cases"]
        ))
        self.assertTrue(
            all(
                not row["participantSelfAssessmentCoverageQualified"]
                for row in value["cases"]
            )
        )
        weak, strong = value["aggregateParticipantProfiles"]
        self.assertEqual(weak["microPassRate"], 0.0)
        self.assertEqual(strong["microPassRate"], 1.0)

    def test_three_predeclared_tiers_require_every_adjacent_pair_to_separate(self) -> None:
        tiers = {
            "weak": [False] * 20,
            "middle": [False] * 10 + [True] * 10,
            "strong": [True] * 20,
        }
        for index, case_id in enumerate(self.source_sets, 1):
            self.reports[case_id] = self.write_discrimination(
                case_id,
                index,
                tier_outcomes=tiers,
            )
            self.write_attestation(
                self.report_attestations[case_id], self.reports[case_id], 2000 + index
            )
        self.write_manifest()
        manifest = json.loads(self.manifest.read_text())
        manifest["participantOrder"] = ["weak", "middle", "strong"]
        self.manifest.write_text(json.dumps(manifest, indent=2))
        value = SUITE.build_scorecard(self.manifest)
        self.assertTrue(
            value["qualification"]["capabilityResolutionMeasurementQualified"]
        )
        self.assertEqual(
            value["denominators"]["capabilityResolutionQualifiedCaseCount"],
            2,
        )
        self.assertTrue(value["aggregateCapabilityResolution"]["qualified"])
        for row in value["cases"]:
            resolution = row["capabilityResolution"]
            self.assertEqual(resolution["status"], "qualified")
            self.assertTrue(row["capabilityResolutionQualified"])
            self.assertEqual(resolution["adjacentPairCount"], 2)
            self.assertTrue(resolution["allAdjacentWilson95Separated"])
            self.assertEqual(resolution["minimumAdjacentPassRateGap"], 0.5)

    def test_extreme_separation_does_not_hide_an_overlapping_middle_tier(self) -> None:
        tiers = {
            "weak": [False] * 20,
            "middle": [False] * 20,
            "strong": [True] * 20,
        }
        for index, case_id in enumerate(self.source_sets, 1):
            self.reports[case_id] = self.write_discrimination(
                case_id,
                index,
                tier_outcomes=tiers,
            )
            self.write_attestation(
                self.report_attestations[case_id], self.reports[case_id], 2000 + index
            )
        self.write_manifest()
        manifest = json.loads(self.manifest.read_text())
        manifest["participantOrder"] = ["weak", "middle", "strong"]
        self.manifest.write_text(json.dumps(manifest, indent=2))
        value = SUITE.build_scorecard(self.manifest)
        self.assertTrue(value["qualification"]["suiteMeasurementQualified"])
        self.assertFalse(
            value["qualification"]["capabilityResolutionMeasurementQualified"]
        )
        self.assertEqual(
            value["denominators"]["capabilityResolutionQualifiedCaseCount"],
            0,
        )
        for row in value["cases"]:
            self.assertTrue(row["strongestWeakestWilson95Separated"])
            self.assertFalse(row["capabilityResolutionQualified"])
            self.assertEqual(
                row["capabilityResolution"]["status"],
                "adjacent-tiers-not-distinct",
            )

    def test_review_failure_keeps_suite_measurement_unqualified(self) -> None:
        self.write_population(unqualified="case-b")
        self.write_attestation(self.population_attestation, self.population, 9001)
        value = SUITE.build_scorecard(self.manifest)
        self.assertEqual(value["denominators"]["qualifiedCaseCount"], 1)
        self.assertFalse(value["qualification"]["suiteMeasurementQualified"])
        failed = next(row for row in value["cases"] if row["caseId"] == "case-b")
        self.assertFalse(failed["reviewQualified"])

    def test_cohort_bound_population_preserves_candidate_yield_in_suite(self) -> None:
        self.source_sets["case-b"] = "a" * 64
        for index, case_id in enumerate(self.source_sets, 1):
            self.reports[case_id] = self.write_discrimination(case_id, index)
            self.write_attestation(
                self.report_attestations[case_id], self.reports[case_id], 2000 + index
            )
        self.write_population()
        self.write_cohort_bound_population()
        self.write_attestation(self.population_attestation, self.population, 9001)
        self.write_manifest()
        value = SUITE.build_scorecard(self.manifest)
        self.assertEqual(value["schema"], "agentlab.agent_suite_scorecard.v2")
        self.assertEqual(value["denominators"]["selectedCandidateCount"], 3)
        self.assertEqual(value["denominators"]["unadjudicatedCandidateCount"], 1)
        self.assertAlmostEqual(value["denominators"]["caseYieldRate"], 2 / 3)
        self.assertEqual(
            [row["candidateId"] for row in value["cases"]],
            ["candidate-a", "candidate-b"],
        )
        self.assertTrue(
            value["reviewPopulation"]["candidateCohortMembershipQualified"]
        )

    def test_participant_self_assessment_coverage_is_separate_and_non_gating(self) -> None:
        for index, case_id in enumerate(self.source_sets, 1):
            self.reports[case_id] = self.write_discrimination(
                case_id, index, self_assessment=True
            )
            self.write_attestation(
                self.report_attestations[case_id], self.reports[case_id], 2000 + index
            )
        self.write_manifest()
        value = SUITE.build_scorecard(self.manifest)
        self.assertTrue(value["qualification"]["suiteMeasurementQualified"])
        self.assertTrue(
            value["qualification"]["participantSelfAssessmentMeasurementQualified"]
        )
        self.assertTrue(
            all(
                row["participantSelfAssessmentCoverageQualified"]
                and row["participantSelfAssessmentAgreementRate"] == 1.0
                and row["participantSelfAssessmentMeanBrierScore"] == 0.04
                for row in value["cases"]
            )
        )

    def test_declared_capability_order_is_not_recovered_from_outcomes(self) -> None:
        self.reports["case-b"] = self.write_discrimination("case-b", 2, reverse=True)
        self.write_attestation(
            self.report_attestations["case-b"], self.reports["case-b"], 2002
        )
        self.write_manifest()
        value = SUITE.build_scorecard(self.manifest)
        failed = next(row for row in value["cases"] if row["caseId"] == "case-b")
        self.assertFalse(failed["expectedCapabilityOrderQualified"])
        self.assertFalse(failed["scorecardQualified"])

    def test_dependency_discovery_is_reported_without_becoming_a_verdict(self) -> None:
        for index, case_id in enumerate(self.source_sets, 1):
            self.reports[case_id] = self.write_discrimination(
                case_id, index, dependency_discovery=True
            )
            self.write_attestation(
                self.report_attestations[case_id], self.reports[case_id], 2000 + index
            )
        self.write_manifest()
        value = SUITE.build_scorecard(self.manifest)
        self.assertTrue(value["qualification"]["suiteMeasurementQualified"])
        self.assertTrue(
            value["qualification"]["dependencyDiscoveryMeasurementQualified"]
        )
        self.assertTrue(
            value["qualification"]["dependencyDiscoveryCoverageQualified"]
        )
        self.assertTrue(all(
            row["dependencyDiscoveryRequiredObligationCoverage"] == 1.0
            and row["dependencyDiscoveryUnadjudicatedClaimCount"] == 0
            for row in value["cases"]
        ))

    def test_missing_process_evidence_is_explicitly_unqualified(self) -> None:
        self.reports["case-b"] = self.write_discrimination(
            "case-b", 2, process_evidence=False
        )
        self.write_attestation(
            self.report_attestations["case-b"], self.reports["case-b"], 2002
        )
        self.write_manifest()
        value = SUITE.build_scorecard(self.manifest)
        failed = next(row for row in value["cases"] if row["caseId"] == "case-b")
        self.assertFalse(failed["processMeasurementCoverageQualified"])
        self.assertFalse(failed["scorecardQualified"])

    def test_static_only_report_cannot_qualify_as_end_to_end_suite(self) -> None:
        report = json.loads(self.reports["case-b"].read_text())
        for profile in report["ranking"][0]["participantProfiles"]:
            profile["processMeasurement"]["harmonyDevice"] = {
                "executedTrials": 0,
                "successfulTrials": profile["passedTrials"],
                "successfulDeviceTrials": 0,
                "profiledSuccessfulDeviceTrials": 0,
                "successfulAttemptDeviceCoverageQualified": False,
                "profiledSuccessCoverageQualified": False,
                "smartPerfSampleCount": 0,
                "authority": "operator-owned-harmony-ui-oracle-with-functional-pass-gated-smartperf",
            }
        harmony = report["ranking"][0]["processMeasurement"]["harmonyDevice"]
        harmony.update(
            {
                "executedAttemptCount": 0,
                "successfulDeviceAttemptCount": 0,
                "profiledSuccessfulAttemptCount": 0,
                "successfulAttemptDeviceCoverageQualified": False,
                "profiledSuccessCoverageQualified": False,
                "endToEndEvidenceQualified": False,
                "smartPerfSampleCount": 0,
            }
        )
        self.reports["case-b"].write_text(json.dumps(report))
        self.write_attestation(
            self.report_attestations["case-b"], self.reports["case-b"], 2002
        )
        self.write_manifest()
        value = SUITE.build_scorecard(self.manifest)
        failed = next(row for row in value["cases"] if row["caseId"] == "case-b")
        self.assertFalse(failed["harmonyEndToEndEvidenceQualified"])
        self.assertFalse(failed["scorecardQualified"])
        self.assertFalse(value["qualification"]["suiteMeasurementQualified"])
        self.assertFalse(value["qualification"]["harmonyEndToEndEvidenceQualified"])

    def write_device_bound_manifest(self) -> Path:
        value = json.loads(self.manifest.read_text())
        value["schema"] = "agentlab.agent_suite_scorecard_manifest.v2"
        for row in value["cases"]:
            row.update(
                {
                    "assessedCampaignWorkflowPath": ".github/workflows/multi-repo-assessed-campaign.yml",
                    "assessedCampaignMethodRevision": "d" * 40,
                    "sourceAssessedCampaignRunId": row["assessedCampaignRunId"],
                    "deviceImportVerification": None,
                    "deviceImportAttestationVerification": None,
                }
            )
        device = value["cases"][1]
        device["assessedCampaignWorkflowPath"] = (
            ".github/workflows/harmony-device-campaign-import.yml"
        )
        device["assessedCampaignWorkflowHeadSha"] = "e" * 40
        device["sourceAssessedCampaignRunId"] = 7777
        verification = self.root / "case-b-import-verification.json"
        verification.write_text(
            json.dumps(
                {
                    "schema": "agentlab.harmony_device_campaign_import_verification.v1",
                    "status": "verified-review-required",
                    "caseId": "case-b",
                    "sourceSetSha256": self.source_sets["case-b"],
                    "sourceMethodRevision": "d" * 40,
                    "verificationMethodRevision": "e" * 40,
                    "sourceAssessedCampaign": {"runId": 7777},
                    "trustedReconstruction": {
                        "discriminationReportSha256": hashlib.sha256(
                            self.reports["case-b"].read_bytes()
                        ).hexdigest()
                    },
                    "harmonyEndToEndEvidenceQualified": True,
                    "automaticPromotion": False,
                }
            )
        )
        verification_attestation = self.root / "case-b-import-attestation.json"
        self.write_attestation(verification_attestation, verification, 2002)
        device["deviceImportVerification"] = verification.name
        device["deviceImportAttestationVerification"] = (
            verification_attestation.name
        )
        self.manifest.write_text(json.dumps(value, indent=2))
        return verification

    def test_attested_device_import_keeps_source_and_verifier_revisions_distinct(self) -> None:
        self.write_device_bound_manifest()
        value = SUITE.build_scorecard(self.manifest)
        device = next(row for row in value["cases"] if row["caseId"] == "case-b")
        self.assertEqual(device["assessedCampaignMethodRevision"], "d" * 40)
        self.assertEqual(device["assessedCampaignWorkflowHeadSha"], "e" * 40)
        self.assertEqual(device["sourceAssessedCampaignRunId"], 7777)
        self.assertIn("deviceImportEvidence", device)
        self.assertTrue(device["scorecardQualified"])

    def test_device_import_receipt_must_bind_reconstructed_report(self) -> None:
        verification = self.write_device_bound_manifest()
        value = json.loads(verification.read_text())
        value["trustedReconstruction"]["discriminationReportSha256"] = "0" * 64
        verification.write_text(json.dumps(value))
        with self.assertRaisesRegex(SUITE.ScorecardError, "report digest differs"):
            SUITE.build_scorecard(self.manifest)

    def test_scorecard_membership_must_equal_reviewed_population(self) -> None:
        self.write_manifest(case_ids=["case-a"])
        with self.assertRaisesRegex(SUITE.ScorecardError, "exactly match"):
            SUITE.build_scorecard(self.manifest)

    def test_source_set_drift_is_rejected(self) -> None:
        report = json.loads(self.reports["case-b"].read_text())
        report["sourceSetSha256"] = "f" * 64
        self.reports["case-b"].write_text(json.dumps(report))
        with self.assertRaisesRegex(SUITE.ScorecardError, "source set differs"):
            SUITE.build_scorecard(self.manifest)

    def test_campaign_revision_must_match_report_method_revision(self) -> None:
        value = json.loads(self.manifest.read_text())
        value["cases"][1]["assessedCampaignWorkflowHeadSha"] = "c" * 40
        self.manifest.write_text(json.dumps(value))
        with self.assertRaisesRegex(SUITE.ScorecardError, "method revision differs"):
            SUITE.build_scorecard(self.manifest)

    def test_attestation_must_bind_exact_subject_and_run(self) -> None:
        value = json.loads(self.population_attestation.read_text())
        value[0]["verificationResult"]["statement"]["predicate"]["runDetails"][
            "metadata"
        ]["invocationId"] = (
            "https://github.com/example/agentlab/actions/runs/9999/attempts/1"
        )
        self.population_attestation.write_text(json.dumps(value))
        with self.assertRaisesRegex(SUITE.ScorecardError, "expected workflow run"):
            SUITE.build_scorecard(self.manifest)

    def test_population_metadata_is_fail_closed(self) -> None:
        value = json.loads(self.population.read_text())
        value["caseMembershipSha256"] = "not-a-digest"
        self.population.write_text(json.dumps(value))
        with self.assertRaisesRegex(SUITE.ScorecardError, "membership digest"):
            SUITE.build_scorecard(self.manifest)

    def test_workflow_freezes_run_ids_order_and_attests_output(self) -> None:
        workflow = (ROOT / ".github/workflows/agent-suite-scorecard.yml").read_text()
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("blind-review-population-report", workflow)
        self.assertIn("multi-repo-assessed-campaign", workflow)
        self.assertIn("harmony-device-assessed-campaign", workflow)
        self.assertIn(".github/workflows/blind-review-population.yml", workflow)
        self.assertIn(".github/workflows/multi-repo-assessed-campaign.yml", workflow)
        self.assertIn(".github/workflows/harmony-device-campaign-import.yml", workflow)
        self.assertIn('run["head_branch"] == "main"', workflow)
        self.assertIn('run["conclusion"] == "success"', workflow)
        self.assertIn("participantOrder", workflow)
        self.assertIn("compose-agent-suite-scorecard.py", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("attestations: write", workflow)
        self.assertIn(
            "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
