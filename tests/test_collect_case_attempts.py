from __future__ import annotations

import importlib.util
import hashlib
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


COLLECTOR = load_module("collect_case_attempts", ROOT / "scripts/collect-case-attempts.py")
SCORER = load_module("score_collected_cases", ROOT / "scripts/score-case-discrimination.py")


class CollectCaseAttemptsTests(unittest.TestCase):
    source_revision = "1" * 40
    source_set_sha256 = "a" * 64
    method_revision = "2" * 40
    case_id = "case-separates-participants"

    def write_json(self, path: pathlib.Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def write_attempt(
        self,
        root: pathlib.Path,
        attempt_id: str,
        passed: bool | None,
        *,
        assessed: bool = True,
        infrastructure: bool = True,
        source_revision: str | None = None,
    ) -> None:
        evidence = root / "runs" / attempt_id
        revision = source_revision or self.source_revision
        self.write_json(
            evidence / "summary.json",
            {"taskId": self.case_id, "sourceRevision": revision},
        )
        self.write_json(
            evidence / "decision-package.json",
            {
                "schema": "agentlab.harness_decision_package.v1",
                "taskId": self.case_id,
                "sourceRevision": revision,
                "assessmentStatus": "assessed" if assessed else "infrastructure-unavailable",
                "infrastructureAvailable": infrastructure,
                "subjectTaskSucceeded": passed,
            },
        )

    def manifest(self, attempts: list[dict]) -> dict:
        return {
            "schema": "agentlab.case_attempt_collection.v1",
            "sourceRevision": self.source_revision,
            "methodRevision": self.method_revision,
            "cases": [
                {
                    "id": self.case_id,
                    "calibration": "calibration.json",
                    "attempts": attempts,
                }
            ],
        }

    def multi_repo_manifest(self, attempts: list[dict]) -> dict:
        value = self.manifest(attempts)
        value["schema"] = "agentlab.case_attempt_collection.v2"
        value.pop("sourceRevision")
        value["sourceSetSha256"] = self.source_set_sha256
        return value

    def write_multi_repo_attempt(
        self, root: pathlib.Path, attempt_id: str, passed: bool
    ) -> None:
        evidence = root / "runs" / attempt_id
        common = {
            "taskId": self.case_id,
            "sourceSetSha256": self.source_set_sha256,
        }
        self.write_json(evidence / "summary.json", common)
        self.write_json(
            evidence / "decision-package.json",
            {
                **common,
                "schema": "agentlab.harness_decision_package.v1",
                "assessmentStatus": "assessed",
                "infrastructureAvailable": True,
                "subjectTaskSucceeded": passed,
            },
        )

    def write_calibration(self, root: pathlib.Path) -> None:
        self.write_json(
            root / "calibration.json",
            {
                "infrastructureValid": True,
                "baselineExpectedPass": False,
                "baselineObservedPass": False,
                "referenceExpectedPass": True,
                "referenceObservedPass": True,
                "negativeVariants": [
                    {
                        "id": "wrong-boundary",
                        "expectedPass": False,
                        "observedPass": False,
                        "infrastructureValid": True,
                    }
                ],
            },
        )

    def write_multi_repo_calibration(self, root: pathlib.Path) -> None:
        def variant(*verdicts: bool) -> dict:
            return {
                "sourceSha256": "f" * 64,
                "stages": {
                    f"turn-{index}": {"pass": verdict}
                    for index, verdict in enumerate(verdicts, 1)
                },
            }

        self.write_json(
            root / "calibration.json",
            {
                "schema": "agentlab.multi_repo_calibration.v1",
                "sourceSetSha256": self.source_set_sha256,
                "infrastructureAvailable": True,
                "variants": {
                    "baseline": variant(False, False),
                    "reference": variant(True, True),
                    "wrong-boundary": variant(False, False),
                    "stale-consumer": variant(True, False),
                },
            },
        )

    def write_emulator_result(
        self,
        root: pathlib.Path,
        attempt_id: str,
        *,
        passed: bool | None,
        infrastructure: bool,
        v3: bool = False,
    ) -> str:
        source_identity = f"artifact-sha256:{'a' * 64}"
        assessed = infrastructure and isinstance(passed, bool)
        evidence = root / "runs" / attempt_id
        policy_raw = json.dumps(
            {
                "schema": "agentlab.harmony_performance_policy.v1",
                "id": "cpu-memory-v1",
            },
            sort_keys=True,
        ).encode()
        workload_raw = b"schema\tagentlab.harmony_profile_workload.v1\nworkload\tscroll-v1\nswipe\t1\t2\t3\t4\t5\n"
        policy_sha = hashlib.sha256(policy_raw).hexdigest()
        workload_sha = hashlib.sha256(workload_raw).hexdigest()
        self.write_json(
            evidence / "result.json",
            {
                "schema": (
                    "agentlab.harmony_emulator_case_result.v3"
                    if v3
                    else "agentlab.harmony_emulator_case_result.v2"
                ),
                "status": "passed" if passed is True else "failed",
                "taskId": self.case_id,
                "sourceSetSha256": self.source_set_sha256,
                "sourceIdentity": source_identity,
                "hapSha256": "a" * 64,
                "scenarioId": "bounded-ui-case",
                "scenarioSha256": "b" * 64,
                "oracleStatus": (
                    "passed" if passed is True else "failed" if assessed else "not-run"
                ),
                "assessmentStatus": "assessed" if assessed else "infrastructure-unavailable",
                "infrastructureAvailable": infrastructure,
                "subjectTaskSucceeded": passed if assessed else None,
                "failureClass": "none" if passed is True else "oracle" if assessed else "infrastructure",
                "powerThermalAuthority": "unavailable_on_emulator",
                **(
                    {
                        "profileStatus": "collected",
                        "profileSummaryStatus": "normalized",
                        "profileRunId": attempt_id,
                        "environmentIdentity": "hwlinux:emulator:class-a",
                        "performancePolicyId": "cpu-memory-v1",
                        "performancePolicySha256": policy_sha,
                        "profileWorkloadId": "scroll-v1",
                        "profileWorkloadSha256": workload_sha,
                    }
                    if v3
                    else {}
                ),
            },
        )
        if v3:
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / "performance-policy.json").write_bytes(policy_raw)
            (evidence / "profile-workload.tsv").write_bytes(workload_raw)
            (evidence / "profile-workload-actions.tsv").write_text(
                "1\tswipe\t1,2,3,4,5\n"
            )
            self.write_json(
                evidence / "smartperf-summary.json",
                {
                    "schema": "agentlab.smartperf_summary.v2",
                    "taskId": self.case_id,
                    "sourceIdentity": source_identity,
                    "runId": attempt_id,
                    "environmentIdentity": "hwlinux:emulator:class-a",
                    "performancePolicy": {"id": "cpu-memory-v1", "sha256": policy_sha},
                    "profileWorkload": {"id": "scroll-v1", "sha256": workload_sha},
                },
            )
        if assessed:
            (root / "runs" / attempt_id / "ui-checks.tsv").write_text(
                f"visible\t{'true' if passed else 'false'}\tassert-text\tExpected\n"
            )
        return source_identity

    def test_collected_evidence_flows_into_eligible_score(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_calibration(root)
            attempts = []
            for participant, passed in (("strong", True), ("baseline", False)):
                for trial in range(1, 4):
                    attempt_id = f"{participant}-{trial}"
                    self.write_attempt(root, attempt_id, passed)
                    attempts.append(
                        {
                            "attemptId": attempt_id,
                            "participantId": participant,
                            "producerRun": f"run-{attempt_id}",
                            "evidence": f"runs/{attempt_id}",
                        }
                    )
            collected = COLLECTOR.build_input(self.manifest(attempts), root.resolve())
            report = SCORER.build_report(collected, 3, 0.6)
            row = report["ranking"][0]
            self.assertTrue(row["eligible"])
            self.assertEqual(row["metrics"]["discriminationScore"], 1.0)
            self.assertFalse(collected["collectionPolicy"]["automaticPromotion"])
            evidence = collected["cases"][0]["attempts"][0]["evidence"]
            self.assertEqual(len(evidence["summary"]["sha256"]), 64)
            self.assertEqual(len(evidence["decisionPackage"]["sha256"]), 64)

    def test_multi_repo_source_set_flows_into_v2_score(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_multi_repo_calibration(root)
            attempts = []
            for participant, passed in (("strong", True), ("baseline", False)):
                for trial in range(1, 4):
                    attempt_id = f"{participant}-{trial}"
                    self.write_multi_repo_attempt(root, attempt_id, passed)
                    attempts.append(
                        {
                            "attemptId": attempt_id,
                            "participantId": participant,
                            "evidence": f"runs/{attempt_id}",
                        }
                    )
            collected = COLLECTOR.build_input(
                self.multi_repo_manifest(attempts), root.resolve()
            )
            self.assertEqual(collected["schema"], "agentlab.case_discrimination_input.v2")
            self.assertEqual(collected["sourceSetSha256"], self.source_set_sha256)
            self.assertNotIn("sourceRevision", collected)
            calibration = collected["cases"][0]["calibration"]
            self.assertEqual(
                calibration["sourceSchema"], "agentlab.multi_repo_calibration.v1"
            )
            self.assertFalse(calibration["baselineObservedPass"])
            self.assertTrue(calibration["referenceObservedPass"])
            self.assertEqual(len(calibration["negativeVariants"]), 2)
            report = SCORER.build_report(collected, 3, 0.6)
            self.assertEqual(report["schema"], "agentlab.case_discrimination_report.v2")
            self.assertEqual(report["sourceSetSha256"], self.source_set_sha256)
            self.assertTrue(report["ranking"][0]["eligible"])

    def test_operator_process_measurement_is_bound_and_collected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_multi_repo_calibration(root)
            evidence = root / "runs/measured-1"
            stages = [
                {
                    "stageId": "turn-1",
                    "participantCompleted": True,
                    "changedPaths": ["app/src/example.ts"],
                    "changedPathCount": 1,
                    "unauthorizedPaths": [],
                    "unauthorizedPathCount": 0,
                    "scopeValid": True,
                    "oraclePass": True,
                    "participantDurationMs": 12,
                    "oracleDurationMs": 3,
                    "stageDurationMs": 17,
                    "cumulativeCheckCount": 2,
                    "participantSelfAssessment": {
                        "schema": "agentlab.participant_self_assessment.v1",
                        "expectedOraclePass": True,
                        "confidence": 0.8,
                        "predictedPassProbability": 0.8,
                        "agreement": True,
                        "brierScore": 0.03999999999999998,
                        "authority": "participant-claim-not-a-verdict",
                    },
                    "dependencyDiscovery": {
                        "schema": "agentlab.dependency_discovery_stage_measurement.v1",
                        "submissionStatus": "reported",
                        "measurementQualified": True,
                        "validationError": None,
                        "claimCount": 1,
                        "obligationCount": 1,
                        "coveredObligationCount": 1,
                        "requiredObligationCoverage": 1.0,
                        "coverageQualified": True,
                        "unadjudicatedClaimCount": 0,
                        "obligations": [{"obligationId": "dependency-one", "covered": True}],
                        "participantClaims": [{
                            "relation": "module-dependency",
                            "source": {"repositoryId": "app", "path": "src/app.ts"},
                            "target": {"repositoryId": "contracts", "path": "src/policy.ts"},
                            "rationale": "The app consumes the shared policy.",
                        }],
                        "precisionClaimed": False,
                        "authority": "hidden-revision-bound-program-fact-obligations-not-gold-path-imitation",
                    },
                }
            ]
            process = {
                "schema": "agentlab.assessment_process_measurement.v1",
                "stageCount": 1,
                "participantCompletedStageCount": 1,
                "oracleExecutedStageCount": 1,
                "oraclePassedStageCount": 1,
                "scopeViolationStageCount": 0,
                "changedPathCount": 1,
                "unauthorizedPathCount": 0,
                "oracleRecoveryCount": 0,
                "oracleRegressionCount": 0,
                "participantDurationMs": 12,
                "oracleDurationMs": 3,
                "stageDurationMs": 17,
                "attemptDurationMs": 20,
                "processMeasurementQualified": True,
                "participantSelfAssessment": {
                    "schema": "agentlab.participant_self_assessment_summary.v1",
                    "stageCount": 1,
                    "reportedStageCount": 1,
                    "comparableStageCount": 1,
                    "agreementCount": 1,
                    "coverageRate": 1.0,
                    "agreementRate": 1.0,
                    "meanBrierScore": 0.03999999999999998,
                    "coverageQualified": True,
                    "authority": "participant-claim-compared-with-operator-oracle-not-a-verdict",
                },
                "dependencyDiscovery": {
                    "schema": "agentlab.dependency_discovery_summary.v1",
                    "stageCount": 1,
                    "measuredStageCount": 1,
                    "missingStageCount": 0,
                    "invalidStageCount": 0,
                    "claimCount": 1,
                    "obligationCount": 1,
                    "coveredObligationCount": 1,
                    "requiredObligationCoverage": 1.0,
                    "coverageQualified": True,
                    "unadjudicatedClaimCount": 0,
                    "precisionClaimed": False,
                    "authority": "hidden-revision-bound-program-fact-obligations-not-gold-path-imitation",
                },
            }
            common = {
                "taskId": self.case_id,
                "sourceSetSha256": self.source_set_sha256,
                "participantId": "candidate",
                "assessmentStatus": "assessed",
                "infrastructureAvailable": True,
                "subjectTaskSucceeded": True,
                "processMeasurement": process,
            }
            self.write_json(
                evidence / "summary.json",
                {**common, "stages": stages, "durationMs": 20},
            )
            self.write_json(
                evidence / "decision-package.json",
                {
                    **common,
                    "schema": "agentlab.harness_decision_package.v1",
                    "phaseVerdicts": stages,
                },
            )
            attempt = {
                "attemptId": "measured-1",
                "participantId": "candidate",
                "evidence": "runs/measured-1",
            }
            collected = COLLECTOR.build_input(
                self.multi_repo_manifest([attempt]), root.resolve()
            )
            self.assertEqual(
                collected["cases"][0]["attempts"][0]["processMeasurement"],
                process,
            )

            tampered = json.loads((evidence / "summary.json").read_text())
            tampered["stages"][0]["participantSelfAssessment"]["brierScore"] = 0.4
            self.write_json(evidence / "summary.json", tampered)
            with self.assertRaisesRegex(ValueError, "self-assessment derivation differs"):
                COLLECTOR.build_input(
                    self.multi_repo_manifest([attempt]), root.resolve()
                )
            self.write_json(
                evidence / "summary.json",
                {**common, "stages": stages, "durationMs": 20},
            )

            decision = json.loads((evidence / "decision-package.json").read_text())
            decision["processMeasurement"]["attemptDurationMs"] = 21
            self.write_json(evidence / "decision-package.json", decision)
            with self.assertRaisesRegex(ValueError, "differs between summary and decision"):
                COLLECTOR.build_input(
                    self.multi_repo_manifest([attempt]), root.resolve()
                )

    def test_multi_repo_attempt_from_another_source_set_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_multi_repo_calibration(root)
            self.write_multi_repo_attempt(root, "drifted-set", True)
            summary = root / "runs/drifted-set/summary.json"
            value = json.loads(summary.read_text())
            value["sourceSetSha256"] = "b" * 64
            self.write_json(summary, value)
            with self.assertRaisesRegex(ValueError, "sourceSetSha256 mismatch"):
                COLLECTOR.build_input(
                    self.multi_repo_manifest(
                        [
                            {
                                "attemptId": "drifted-set",
                                "participantId": "candidate",
                                "evidence": "runs/drifted-set",
                            }
                        ]
                    ),
                    root.resolve(),
                )

    def test_infrastructure_unavailable_attempt_has_no_failure_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_calibration(root)
            self.write_attempt(
                root,
                "infra-1",
                False,
                assessed=False,
                infrastructure=False,
            )
            collected = COLLECTOR.build_input(
                self.manifest(
                    [
                        {
                            "attemptId": "infra-1",
                            "participantId": "candidate",
                            "evidence": "runs/infra-1",
                        }
                    ]
                ),
                root.resolve(),
            )
            attempt = collected["cases"][0]["attempts"][0]
            self.assertFalse(attempt["infrastructureValid"])
            self.assertIsNone(attempt["taskPassed"])
            row = SCORER.build_report(collected, 3, 0.6)["ranking"][0]
            self.assertEqual(row["excludedAttemptCount"], 1)
            self.assertEqual(row["validAttemptCount"], 0)

    def test_source_revision_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_calibration(root)
            self.write_attempt(root, "drifted", True, source_revision="3" * 40)
            with self.assertRaisesRegex(ValueError, "sourceRevision mismatch"):
                COLLECTOR.build_input(
                    self.manifest(
                        [
                            {
                                "attemptId": "drifted",
                                "participantId": "candidate",
                                "evidence": "runs/drifted",
                            }
                        ]
                    ),
                    root.resolve(),
                )

    def test_emulator_oracle_result_becomes_scored_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_calibration(root)
            identity = self.write_emulator_result(
                root, "emulator-pass", passed=True, infrastructure=True
            )
            collected = COLLECTOR.build_input(
                self.manifest(
                    [
                        {
                            "attemptId": "emulator-pass",
                            "participantId": "candidate",
                            "evidenceKind": "harmony-emulator-v2",
                            "sourceIdentity": identity,
                            "evidence": "runs/emulator-pass",
                        }
                    ]
                ),
                root.resolve(),
            )
            attempt = collected["cases"][0]["attempts"][0]
            self.assertTrue(attempt["infrastructureValid"])
            self.assertTrue(attempt["taskPassed"])
            self.assertEqual(
                attempt["verdictSource"], "operator-owned-harmony-ui-oracle"
            )
            self.assertEqual(
                len(attempt["evidence"]["emulatorResult"]["sha256"]), 64
            )

    def test_emulator_infrastructure_failure_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_calibration(root)
            identity = self.write_emulator_result(
                root, "emulator-infra", passed=None, infrastructure=False
            )
            collected = COLLECTOR.build_input(
                self.manifest(
                    [
                        {
                            "attemptId": "emulator-infra",
                            "participantId": "candidate",
                            "evidenceKind": "harmony-emulator-v2",
                            "sourceIdentity": identity,
                            "evidence": "runs/emulator-infra",
                        }
                    ]
                ),
                root.resolve(),
            )
            attempt = collected["cases"][0]["attempts"][0]
            self.assertFalse(attempt["infrastructureValid"])
            self.assertIsNone(attempt["taskPassed"])

    def test_v3_emulator_attempt_retains_policy_workload_and_profile_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_calibration(root)
            identity = self.write_emulator_result(
                root, "emulator-v3", passed=True, infrastructure=True, v3=True
            )
            collected = COLLECTOR.build_input(
                self.manifest(
                    [
                        {
                            "attemptId": "emulator-v3",
                            "participantId": "candidate",
                            "evidenceKind": "harmony-emulator-v3",
                            "sourceIdentity": identity,
                            "evidence": "runs/emulator-v3",
                        }
                    ]
                ),
                root.resolve(),
            )
            evidence = collected["cases"][0]["attempts"][0]["evidence"]
            self.assertEqual(
                set(evidence),
                {
                    "emulatorResult",
                    "uiChecks",
                    "performancePolicy",
                    "profileWorkload",
                    "smartperfSummary",
                    "profileWorkloadActions",
                },
            )
            self.assertTrue(all(len(row["sha256"]) == 64 for row in evidence.values()))

    def test_multi_repo_emulator_attempt_binds_source_set_and_hap(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_multi_repo_calibration(root)
            identity = self.write_emulator_result(
                root, "multi-repo-emulator", passed=True, infrastructure=True, v3=True
            )
            collected = COLLECTOR.build_input(
                self.multi_repo_manifest(
                    [
                        {
                            "attemptId": "multi-repo-emulator",
                            "participantId": "candidate",
                            "evidenceKind": "harmony-emulator-v3",
                            "sourceIdentity": identity,
                            "evidence": "runs/multi-repo-emulator",
                        }
                    ]
                ),
                root.resolve(),
            )
            attempt = collected["cases"][0]["attempts"][0]
            self.assertTrue(attempt["taskPassed"])
            result = root / attempt["evidence"]["emulatorResult"]["path"]
            value = json.loads(result.read_text())
            value["sourceSetSha256"] = "b" * 64
            result.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "sourceSetSha256 mismatch"):
                COLLECTOR.build_input(
                    self.multi_repo_manifest(
                        [
                            {
                                "attemptId": "multi-repo-emulator",
                                "participantId": "candidate",
                                "evidenceKind": "harmony-emulator-v3",
                                "sourceIdentity": identity,
                                "evidence": "runs/multi-repo-emulator",
                            }
                        ]
                    ),
                    root.resolve(),
                )
    def test_emulator_source_identity_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_calibration(root)
            self.write_emulator_result(
                root, "emulator-drift", passed=True, infrastructure=True
            )
            with self.assertRaisesRegex(ValueError, "sourceIdentity mismatch"):
                COLLECTOR.build_input(
                    self.manifest(
                        [
                            {
                                "attemptId": "emulator-drift",
                                "participantId": "candidate",
                                "evidenceKind": "harmony-emulator-v2",
                                "sourceIdentity": "artifact-sha256:" + "c" * 64,
                                "evidence": "runs/emulator-drift",
                            }
                        ]
                    ),
                    root.resolve(),
                )

    def test_emulator_source_identity_must_bind_hap_digest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_calibration(root)
            identity = self.write_emulator_result(
                root, "emulator-hap-drift", passed=True, infrastructure=True
            )
            result_path = root / "runs/emulator-hap-drift/result.json"
            result = json.loads(result_path.read_text())
            result["hapSha256"] = "d" * 64
            self.write_json(result_path, result)
            with self.assertRaisesRegex(ValueError, "not bound to hapSha256"):
                COLLECTOR.build_input(
                    self.manifest(
                        [
                            {
                                "attemptId": "emulator-hap-drift",
                                "participantId": "candidate",
                                "evidenceKind": "harmony-emulator-v2",
                                "sourceIdentity": identity,
                                "evidence": "runs/emulator-hap-drift",
                            }
                        ]
                    ),
                    root.resolve(),
                )

    def test_emulator_verdict_must_match_retained_ui_checks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_calibration(root)
            identity = self.write_emulator_result(
                root, "emulator-oracle-drift", passed=True, infrastructure=True
            )
            (root / "runs/emulator-oracle-drift/ui-checks.tsv").write_text(
                "visible\tfalse\tassert-text\tExpected\n"
            )
            with self.assertRaisesRegex(ValueError, "contradicts retained UI checks"):
                COLLECTOR.build_input(
                    self.manifest(
                        [
                            {
                                "attemptId": "emulator-oracle-drift",
                                "participantId": "candidate",
                                "evidenceKind": "harmony-emulator-v2",
                                "sourceIdentity": identity,
                                "evidence": "runs/emulator-oracle-drift",
                            }
                        ]
                    ),
                    root.resolve(),
                )


if __name__ == "__main__":
    unittest.main()
