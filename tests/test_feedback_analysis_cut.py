from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PROPOSE = ROOT / "scripts/propose-feedback-analysis-cut.py"
REVIEW = ROOT / "scripts/review-feedback-analysis-cut.py"
CASE_PROPOSER = ROOT / "scripts/propose-multi-repo-case-plan.py"
CASE_REVIEW = ROOT / "scripts/review-multi-repo-case-plan.py"
CASE_GENERATE = ROOT / "scripts/generate-multi-repo-case.py"


def canonical_digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FeedbackAnalysisCutTests(unittest.TestCase):
    def write(self, root: pathlib.Path, name: str, value: dict) -> pathlib.Path:
        path = root / name
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        return path

    def performance_calibration(
        self,
        root: pathlib.Path,
        *,
        source_set: str,
        functional_calibration_sha256: str,
        performance_evidence: dict,
    ) -> pathlib.Path:
        decisions = {
            "baseline": "performance-regression-candidate",
            "reference": "within-relative-guardrails",
            "wrong": "performance-regression-candidate",
        }
        variants = []
        for role_index, role in enumerate(("baseline", "reference", "wrong"), 1):
            observations = []
            for ordinal in (1, 2):
                evidence = {}
                for name in (
                    "baselineSummary",
                    "candidateSummary",
                    "baselineResult",
                    "candidateResult",
                    "comparison",
                ):
                    path = root / "performance-evidence" / role / str(ordinal) / f"{name}.json"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        json.dumps(
                            {"role": role, "observation": ordinal, "kind": name},
                            sort_keys=True,
                        )
                        + "\n"
                    )
                    evidence[name] = {
                        "path": path.relative_to(root).as_posix(),
                        "sha256": file_digest(path),
                        "byteLength": path.stat().st_size,
                    }
                observations.append(evidence)
            variants.append(
                {
                    "role": role,
                    "expectedDecision": decisions[role],
                    "candidateSourceIdentity": f"artifact-sha256:{str(role_index) * 64}",
                    "observationCount": len(observations),
                    "observations": observations,
                }
            )
        return self.write(
            root,
            "case-performance-calibration.json",
            {
                "schema": "agentlab.case_performance_calibration.v1",
                "status": "qualified-review-required",
                "caseId": "next-case",
                "sourceSetSha256": source_set,
                "functionalCalibrationSha256": functional_calibration_sha256,
                "feedbackPerformanceEvidence": performance_evidence,
                "baselineSourceIdentity": f"artifact-sha256:{'a' * 64}",
                "variants": variants,
                "functionalOracleQualified": True,
                "repeatabilityQualified": True,
                "authority": {
                    "functional": "independent-harmony-ui-oracle",
                    "relativePerformance": "smartperf-emulator-proxy",
                    "absolutePowerThermal": "unavailable-on-emulator",
                },
                "automaticPromotion": False,
                "nextGate": "maintainer-review-and-case-freeze",
            },
        )

    def fixture(self, root: pathlib.Path, *, performance: bool = False):
        prior_source_set = "a" * 64
        prior_case = {
            "schema": "agentlab.multi_repo_evaluation_case.v1",
            "id": "prior-case",
            "status": "frozen-calibrated",
            "sourceSetSha256": prior_source_set,
            "automaticPromotion": False,
        }
        feedback_candidate_id = "assessment-feedback-prior"
        feedback = {
            "schema": "agentlab.assessment_feedback_candidates.v1",
            "caseId": "prior-case",
            "sourceSetSha256": prior_source_set,
            "methodRevision": "1" * 40,
            "caseSha256": canonical_digest(prior_case),
            "candidates": [
                {
                    "id": feedback_candidate_id,
                    "caseId": "prior-case",
                    "dimensionId": "assessed-agent-stage-failure",
                    "primaryDimension": "evaluation-feedback",
                    "stageId": "turn-2",
                    "failureMode": "oracle-failure",
                    "mechanism": "oracle-failure at frozen stage turn-2",
                    "status": "candidate",
                    "maturityState": "candidate",
                    "verificationContract": {
                        "caseReady": False,
                        "required": [
                            "maintainer-adjudication",
                            "new-source-and-analysis-cut",
                            "independent-oracle-calibration",
                        ],
                    },
                    "automaticPromotion": False,
                }
            ],
            "policy": {"automaticPromotion": False},
        }
        if performance:
            candidate = feedback["candidates"][0]
            candidate.update(
                {
                    "dimensionId": "assessed-agent-performance-separation",
                    "primaryDimension": "performance-feedback",
                    "stageId": "harmony-device",
                    "failureMode": "repeatable-performance-separation",
                    "mechanism": "repeatable non-overlapping application CPU ranges",
                    "performanceEvidence": {
                        "environmentIdentity": "hwlinux:phone-x86",
                        "performancePolicySha256": "7" * 64,
                        "profileWorkloadSha256": "8" * 64,
                        "metric": "appCpuUsagePercent",
                        "statistic": "mean",
                        "unit": "reported-percent",
                        "direction": "lower",
                        "bestParticipantId": "strong",
                        "worstParticipantId": "medium",
                        "meanDifference": 20.0,
                        "rangesSeparated": True,
                        "authority": {
                            "functional": "none",
                            "relativePerformance": "smartperf-emulator-proxy",
                            "absolutePowerThermal": "unavailable-on-emulator",
                        },
                    },
                }
            )
            candidate["verificationContract"]["required"].append(
                "independent-performance-calibration"
            )
        sources = [
            {"id": "contracts", "repository": "https://example.invalid/contracts.git", "revision": "2" * 40},
            {"id": "app", "repository": "https://example.invalid/app.git", "revision": "3" * 40},
        ]
        module_bindings = {
            "@example/contracts": {"repositoryId": "contracts", "path": "src/contracts.ts"}
        }
        source_identity = {
            "schema": "agentlab.multi_repo_source_set.v1",
            "repositories": sources,
            "moduleBindings": module_bindings,
        }
        next_source_set = canonical_digest(source_identity)
        difficulty_candidate_id = "difficulty-next-impact"
        difficulty = {
            "schema": "agentlab.difficulty_candidates.v2",
            "sourceSetSha256": next_source_set,
            "sources": sources,
            "moduleBindings": module_bindings,
            "candidates": [
                {
                    "id": difficulty_candidate_id,
                    "dimensionId": "multi-repository-change-impact",
                    "primaryDimension": "program-analysis",
                    "mechanism": "recursive reverse dependency closure crosses repository boundaries",
                    "status": "candidate",
                    "maturityState": "candidate",
                    "affectedRepositoryCount": 2,
                    "affectedFiles": [
                        {"repositoryId": "contracts", "path": "src/contracts.ts", "dependencyDepth": 0},
                        {"repositoryId": "app", "path": "src/main.ts", "dependencyDepth": 1},
                    ],
                    "evidenceIds": ["module-edge-1"],
                    "verificationContract": {"caseReady": False, "required": ["behavior oracle"]},
                    "automaticPromotion": False,
                }
            ],
            "automaticPromotion": False,
        }
        case_path = self.write(root, "prior-case.json", prior_case)
        feedback_path = self.write(root, "feedback.json", feedback)
        difficulty_path = self.write(root, "difficulty.json", difficulty)
        analysis = {
            "schema": "agentlab.multi_repo_analysis.v1",
            "sourceSetSha256": next_source_set,
            "repositories": sources,
            "difficultyCandidatesSha256": file_digest(difficulty_path),
            "automaticPromotion": False,
        }
        analysis_path = self.write(root, "analysis.json", analysis)
        return {
            "case": case_path,
            "feedback": feedback_path,
            "difficulty": difficulty_path,
            "analysis": analysis_path,
            "feedbackCandidateId": feedback_candidate_id,
            "difficultyCandidateId": difficulty_candidate_id,
            "nextSourceSet": next_source_set,
        }

    def propose(self, fixture: dict, output: pathlib.Path, method_revision: str = "4" * 40):
        return subprocess.run(
            [
                sys.executable,
                str(PROPOSE),
                "--prior-case", str(fixture["case"]),
                "--feedback", str(fixture["feedback"]),
                "--analysis-receipt", str(fixture["analysis"]),
                "--difficulty", str(fixture["difficulty"]),
                "--feedback-candidate-id", fixture["feedbackCandidateId"],
                "--difficulty-candidate-id", fixture["difficultyCandidateId"],
                "--next-method-revision", method_revision,
                "--output", str(output),
            ],
            text=True,
            capture_output=True,
        )

    def test_reviewed_cut_is_accepted_by_case_proposer_and_retained(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            fixture = self.fixture(root, performance=True)
            proposal_path = root / "feedback-cut-proposal.json"
            proposed = self.propose(fixture, proposal_path)
            self.assertEqual(proposed.returncode, 0, proposed.stderr)
            proposal = json.loads(proposal_path.read_text())
            self.assertEqual(proposal["status"], "review-required")
            self.assertTrue(proposal["change"]["sourceSetChanged"])
            self.assertEqual(proposal["priorCase"]["immutability"], "retained-unchanged")
            self.assertEqual(
                proposal["feedback"]["dimensionId"],
                "assessed-agent-performance-separation",
            )
            self.assertEqual(
                proposal["feedback"]["performanceEvidence"]["metric"],
                "appCpuUsagePercent",
            )
            self.assertFalse(proposal["automaticPromotion"])

            review = {
                "schema": "agentlab.feedback_analysis_cut_review.v1",
                "proposalSha256": file_digest(proposal_path),
                "reviewer": "maintainer-a",
                "rationale": "The new dependency impact is a plausible source-level explanation for the observed stage failure.",
                "acknowledgedRiskIds": [row["id"] for row in proposal["risks"]],
                "verdict": "approve-for-case-construction",
                "automaticPromotion": False,
            }
            review_path = self.write(root, "feedback-cut-review.json", review)
            cut_path = root / "feedback-analysis-cut.json"
            reviewed = subprocess.run(
                [sys.executable, str(REVIEW), "--proposal", str(proposal_path), "--review", str(review_path), "--output", str(cut_path)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
            cut = json.loads(cut_path.read_text())
            self.assertEqual(cut["status"], "reviewed-for-case-construction")
            self.assertEqual(
                cut["feedback"]["performanceEvidence"],
                proposal["feedback"]["performanceEvidence"],
            )
            self.assertFalse(cut["automaticPromotion"])

            intent = {
                "schema": "agentlab.multi_repo_case_intent.v1",
                "sourceSetSha256": fixture["nextSourceSet"],
                "candidateId": fixture["difficultyCandidateId"],
                "caseId": "next-case",
                "title": "Next feedback-derived case",
                "stages": [
                    {"id": "turn-1", "demand": "Update the shared contract.", "checkIds": ["repair-contract"]},
                    {"id": "turn-2", "demand": "Preserve the application consumer.", "checkIds": ["preserve-consumer"]},
                ],
                "oracle": {"authority": "independent-executable-oracle", "sha256": "5" * 64, "receiptSchema": "example.oracle.v1"},
                "calibrationExpectations": {
                    "baseline": {"turn-1": False, "turn-2": False},
                    "reference": {"turn-1": True, "turn-2": True},
                    "wrong-later": {"turn-1": True, "turn-2": False},
                },
            }
            intent_path = self.write(root, "intent.json", intent)
            case_proposal_path = root / "case-proposal.json"
            case_proposed = subprocess.run(
                [
                    sys.executable,
                    str(CASE_PROPOSER),
                    "--difficulty", str(fixture["difficulty"]),
                    "--intent", str(intent_path),
                    "--feedback-analysis-cut", str(cut_path),
                    "--feedback-cut-proposal", str(proposal_path),
                    "--feedback-cut-review", str(review_path),
                    "--output", str(case_proposal_path),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(case_proposed.returncode, 0, case_proposed.stderr)
            case_proposal = json.loads(case_proposal_path.read_text())
            self.assertEqual(case_proposal["feedbackAnalysisCut"]["cutId"], cut["cutId"])
            self.assertEqual(case_proposal["feedbackAnalysisCut"]["sha256"], file_digest(cut_path))
            self.assertEqual(
                case_proposal["feedbackAnalysisCut"]["performanceEvidence"],
                cut["feedback"]["performanceEvidence"],
            )

            case_review = {
                "schema": "agentlab.multi_repo_case_plan_review.v1",
                "proposalSha256": file_digest(case_proposal_path),
                "reviewer": "maintainer-b",
                "rationale": "The staged intent is fair enough to enter independent calibration.",
                "acknowledgedRiskIds": [row["id"] for row in case_proposal["risks"]],
                "verdict": "approve-for-calibration",
            }
            case_review_path = self.write(root, "case-review.json", case_review)
            plan_path = root / "case-plan.json"
            planned = subprocess.run(
                [sys.executable, str(CASE_REVIEW), "--proposal", str(case_proposal_path), "--review", str(case_review_path), "--output", str(plan_path)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(planned.returncode, 0, planned.stderr)
            plan = json.loads(plan_path.read_text())
            self.assertEqual(plan["feedbackAnalysisCut"]["cutId"], cut["cutId"])
            self.assertEqual(
                plan["performanceRequirement"]["feedbackPerformanceEvidence"],
                cut["feedback"]["performanceEvidence"],
            )

            def stage(passed, checks):
                return {
                    "pass": passed,
                    "checks": [{"id": identity, "pass": verdict} for identity, verdict in checks],
                    "checkIds": [identity for identity, _ in checks],
                    "checkCount": len(checks),
                    "receiptSha256": "6" * 64,
                }

            calibration = {
                "schema": "agentlab.multi_repo_calibration.v1",
                "candidateId": fixture["difficultyCandidateId"],
                "sourceSetSha256": fixture["nextSourceSet"],
                "oracleSha256": "5" * 64,
                "receiptSchema": "example.oracle.v1",
                "infrastructureAvailable": True,
                "variants": {
                    "baseline": {
                        "sourceSha256": "7" * 64,
                        "stages": {
                            "turn-1": stage(False, [("repair-contract", False)]),
                            "turn-2": stage(False, [("repair-contract", False), ("preserve-consumer", True)]),
                        },
                    },
                    "reference": {
                        "sourceSha256": "8" * 64,
                        "stages": {
                            "turn-1": stage(True, [("repair-contract", True)]),
                            "turn-2": stage(True, [("repair-contract", True), ("preserve-consumer", True)]),
                        },
                    },
                    "wrong-later": {
                        "sourceSha256": "9" * 64,
                        "stages": {
                            "turn-1": stage(True, [("repair-contract", True)]),
                            "turn-2": stage(False, [("repair-contract", True), ("preserve-consumer", False)]),
                        },
                    },
                },
            }
            calibration_path = self.write(root, "calibration.json", calibration)
            performance_calibration_path = self.performance_calibration(
                root,
                source_set=fixture["nextSourceSet"],
                functional_calibration_sha256=file_digest(calibration_path),
                performance_evidence=cut["feedback"]["performanceEvidence"],
            )
            case_path = root / "next-case.json"
            missing_performance = subprocess.run(
                [
                    sys.executable,
                    str(CASE_GENERATE),
                    "--difficulty", str(fixture["difficulty"]),
                    "--plan", str(plan_path),
                    "--proposal", str(case_proposal_path),
                    "--review", str(case_review_path),
                    "--calibration", str(calibration_path),
                    "--output", str(case_path),
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(missing_performance.returncode, 0)
            self.assertIn(
                "performance-derived case requires performance calibration evidence",
                missing_performance.stderr,
            )
            generated = subprocess.run(
                [
                    sys.executable,
                    str(CASE_GENERATE),
                    "--difficulty", str(fixture["difficulty"]),
                    "--plan", str(plan_path),
                    "--proposal", str(case_proposal_path),
                    "--review", str(case_review_path),
                    "--calibration", str(calibration_path),
                    "--performance-calibration", str(performance_calibration_path),
                    "--output", str(case_path),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(generated.returncode, 0, generated.stderr)
            generated_case = json.loads(case_path.read_text())
            self.assertEqual(generated_case["lineage"]["feedbackAnalysisCut"]["cutId"], cut["cutId"])
            self.assertEqual(generated_case["lineage"]["feedbackAnalysisCut"]["priorCaseId"], "prior-case")
            self.assertEqual(generated_case["lineage"]["feedbackAnalysisCut"]["priorCaseSha256"], cut["priorCase"]["caseSha256"])
            self.assertEqual(generated_case["lineage"]["feedbackAnalysisCut"]["feedbackEvidenceSha256"], cut["feedback"]["evidenceSha256"])
            self.assertEqual(generated_case["lineage"]["feedbackAnalysisCut"]["nextAnalysisReceiptSha256"], cut["nextAnalysis"]["analysisReceiptSha256"])
            self.assertEqual(
                generated_case["lineage"]["feedbackAnalysisCut"]["performanceEvidence"],
                cut["feedback"]["performanceEvidence"],
            )
            self.assertEqual(
                generated_case["performanceRequirement"],
                plan["performanceRequirement"],
            )
            self.assertTrue(generated_case["performanceCalibration"]["qualified"])
            self.assertEqual(
                generated_case["performanceCalibration"]["sha256"],
                file_digest(performance_calibration_path),
            )
            self.assertIn(
                "repeatable policy-bound Harmony performance calibration",
                generated_case["assessmentBoundary"],
            )
            self.assertFalse(generated_case["automaticPromotion"])

            retained = next(
                (root / ref["path"])
                for row in json.loads(performance_calibration_path.read_text())["variants"]
                if row["role"] == "wrong"
                for observation in row["observations"]
                for name, ref in observation.items()
                if name == "comparison"
            )
            retained.write_text('{"tampered":true}\n')
            tampered = subprocess.run(
                [
                    sys.executable,
                    str(CASE_GENERATE),
                    "--difficulty", str(fixture["difficulty"]),
                    "--plan", str(plan_path),
                    "--proposal", str(case_proposal_path),
                    "--review", str(case_review_path),
                    "--calibration", str(calibration_path),
                    "--performance-calibration", str(performance_calibration_path),
                    "--output", str(root / "tampered-case.json"),
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(tampered.returncode, 0)
            self.assertIn("evidence digest differs", tampered.stderr)

    def test_rejects_reusing_same_source_and_method_cut(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            fixture = self.fixture(root)
            feedback = json.loads(fixture["feedback"].read_text())
            difficulty = json.loads(fixture["difficulty"].read_text())
            feedback["sourceSetSha256"] = difficulty["sourceSetSha256"]
            prior_case = json.loads(fixture["case"].read_text())
            prior_case["sourceSetSha256"] = difficulty["sourceSetSha256"]
            feedback["caseSha256"] = canonical_digest(prior_case)
            fixture["case"] = self.write(root, "same-case.json", prior_case)
            fixture["feedback"] = self.write(root, "same-feedback.json", feedback)
            result = self.propose(fixture, root / "proposal.json", method_revision="1" * 40)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must change the source set or method revision", result.stderr)

    def test_rejects_difficulty_bytes_not_bound_by_analysis(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            fixture = self.fixture(root)
            difficulty = json.loads(fixture["difficulty"].read_text())
            difficulty["method"] = "tampered"
            fixture["difficulty"].write_text(json.dumps(difficulty) + "\n")
            result = self.propose(fixture, root / "proposal.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exact difficulty bytes", result.stderr)

    def test_review_rejects_changed_proposal(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            fixture = self.fixture(root)
            proposal_path = root / "proposal.json"
            self.assertEqual(self.propose(fixture, proposal_path).returncode, 0)
            proposal = json.loads(proposal_path.read_text())
            review_path = self.write(
                root,
                "review.json",
                {
                    "schema": "agentlab.feedback_analysis_cut_review.v1",
                    "proposalSha256": "f" * 64,
                    "reviewer": "maintainer-a",
                    "rationale": "reviewed",
                    "acknowledgedRiskIds": [row["id"] for row in proposal["risks"]],
                    "verdict": "approve-for-case-construction",
                    "automaticPromotion": False,
                },
            )
            result = subprocess.run(
                [sys.executable, str(REVIEW), "--proposal", str(proposal_path), "--review", str(review_path), "--output", str(root / "cut.json")],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exact proposal", result.stderr)

    def test_performance_cut_rejects_unseparated_ranges(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            fixture = self.fixture(root, performance=True)
            feedback = json.loads(fixture["feedback"].read_text())
            feedback["candidates"][0]["performanceEvidence"]["rangesSeparated"] = False
            fixture["feedback"] = self.write(root, "invalid-performance-feedback.json", feedback)
            result = self.propose(fixture, root / "proposal.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("performance feedback evidence is invalid", result.stderr)

    def test_schema_is_published_for_reviewed_cut(self):
        schema = json.loads((ROOT / "schemas/feedback-analysis-cut.schema.json").read_text())
        self.assertEqual(schema["properties"]["automaticPromotion"]["const"], False)
        self.assertEqual(schema["properties"]["priorCase"]["properties"]["immutability"]["const"], "retained-unchanged")
        self.assertIn(
            "performanceEvidence",
            schema["properties"]["feedback"]["properties"],
        )


if __name__ == "__main__":
    unittest.main()
