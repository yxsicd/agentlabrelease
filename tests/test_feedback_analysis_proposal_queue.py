from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/prepare-feedback-analysis-proposals.py"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PREPARE = load_module("prepare_feedback_analysis_proposals", SCRIPT)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class FeedbackAnalysisProposalQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.prior_source = "a" * 64
        self.prior_revision = "1" * 40
        self.next_revision = "2" * 40
        self.sources = [
            {"id": "app", "repository": "https://example.invalid/app.git", "revision": "3" * 40},
            {"id": "contracts", "repository": "https://example.invalid/contracts.git", "revision": "4" * 40},
        ]
        self.bindings = {"@example/contracts": {"repositoryId": "contracts", "path": "src/contracts.ts"}}
        self.next_source = canonical_digest(
            {
                "schema": "agentlab.multi_repo_source_set.v1",
                "repositories": self.sources,
                "moduleBindings": self.bindings,
            }
        )
        self.prior_case_value = {
            "schema": "agentlab.multi_repo_evaluation_case.v1",
            "status": "frozen-calibrated",
            "id": "prior-case",
            "sourceSetSha256": self.prior_source,
            "automaticPromotion": False,
        }
        self.prior_case = self.write("prior-case.json", self.prior_case_value)
        self.feedback_value = {
            "schema": "agentlab.assessment_feedback_candidates.v1",
            "caseId": "prior-case",
            "sourceSetSha256": self.prior_source,
            "methodRevision": self.prior_revision,
            "caseSha256": canonical_digest(self.prior_case_value),
            "candidates": [
                {
                    "id": "feedback-1",
                    "caseId": "prior-case",
                    "dimensionId": "assessed-agent-stage-failure",
                    "primaryDimension": "evaluation-feedback",
                    "stageId": "harmony-device",
                    "failureMode": "oracle-failure",
                    "mechanism": "oracle-failure at frozen stage harmony-device",
                    "status": "candidate",
                    "maturityState": "candidate",
                    "verificationContract": {
                        "caseReady": False,
                        "required": ["new-source-and-analysis-cut"],
                    },
                    "automaticPromotion": False,
                }
            ],
            "policy": {"automaticPromotion": False},
        }
        self.feedback = self.write("assessment-feedback-candidates.json", self.feedback_value)
        self.handoff_value = {
            "schema": "agentlab.release_recursive_feedback_handoff.v1",
            "portableEvidence": {
                "priorCase": {"fileName": "prior-case.json", "sha256": digest(self.prior_case), "byteLength": self.prior_case.stat().st_size},
                "assessmentFeedback": {"fileName": "assessment-feedback-candidates.json", "sha256": digest(self.feedback), "byteLength": self.feedback.stat().st_size},
            },
        }
        self.handoff = self.write("summary.json", self.handoff_value)
        self.difficulty_value = {
            "schema": "agentlab.difficulty_candidates.v2",
            "sourceSetSha256": self.next_source,
            "sources": self.sources,
            "moduleBindings": self.bindings,
            "candidates": [
                self.candidate("difficulty-small", 2),
                self.candidate("difficulty-large", 4),
                {
                    **self.candidate("difficulty-single-repo", 5),
                    "affectedFiles": [
                        {"repositoryId": "app", "path": f"src/{index}.ts", "dependencyDepth": index}
                        for index in range(5)
                    ],
                },
            ],
            "automaticPromotion": False,
        }
        self.difficulty = self.write("difficulty.json", self.difficulty_value)
        self.analysis = self.write(
            "analysis.json",
            {
                "schema": "agentlab.multi_repo_analysis.v1",
                "sourceSetSha256": self.next_source,
                "repositories": self.sources,
                "difficultyCandidatesSha256": digest(self.difficulty),
                "automaticPromotion": False,
            },
        )
        self.analysis_run = self.write(
            "analysis-run.json",
            {
                "schema": "agentlab.multi_repo_analysis_run.v1",
                "sourceSetSha256": self.next_source,
                "methodRevision": self.next_revision,
                "analysisReceiptSha256": digest(self.analysis),
                "difficultyEvidenceSha256": digest(self.difficulty),
                "automaticPromotion": False,
            },
        )
        self.request_value = {
            "schema": "agentlab.feedback_analysis_request.v1",
            "status": "prepared-review-required",
            "feedbackHandoff": {
                "sha256": digest(self.handoff),
                "candidateId": "feedback-1",
                "caseId": "prior-case",
                "priorCaseSha256": digest(self.prior_case),
                "feedbackEvidenceSha256": digest(self.feedback),
            },
            "nextAnalysis": {
                "sourceSetSha256": self.next_source,
                "methodRevision": self.next_revision,
            },
            "automaticPromotion": False,
        }
        self.request = self.write("request.json", self.request_value)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, value: dict) -> pathlib.Path:
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return path

    def candidate(self, identity: str, file_count: int) -> dict:
        return {
            "id": identity,
            "dimensionId": "multi-repository-change-impact",
            "mechanism": "recursive reverse dependency closure crosses repository boundaries",
            "status": "candidate",
            "maturityState": "candidate",
            "affectedFiles": [
                {
                    "repositoryId": "app" if index % 2 == 0 else "contracts",
                    "path": f"src/{index}.ts",
                    "dependencyDepth": index,
                }
                for index in range(file_count)
            ],
            "evidenceIds": [f"evidence-{index}" for index in range(file_count)],
            "verificationContract": {"caseReady": False, "required": ["behavior oracle"]},
            "automaticPromotion": False,
        }

    def prepare(self, output_name: str = "queue", limit: int = 10):
        return PREPARE.prepare(
            self.request,
            self.handoff,
            self.prior_case,
            self.feedback,
            self.analysis,
            self.analysis_run,
            self.difficulty,
            self.root / output_name,
            limit,
        )

    def test_creates_ranked_review_only_proposal_queue(self) -> None:
        value = self.prepare()
        self.assertEqual(value["schema"], "agentlab.feedback_analysis_proposal_queue.v1")
        self.assertEqual(value["proposalCount"], 2)
        self.assertEqual(value["eligibleCandidateCount"], 2)
        self.assertEqual(value["proposals"][0]["difficultyCandidateId"], "difficulty-large")
        self.assertEqual(value["proposals"][1]["difficultyCandidateId"], "difficulty-small")
        self.assertFalse(value["selectionPolicy"]["semanticAlignmentVerified"])
        self.assertFalse(value["automaticPromotion"])
        for row in value["proposals"]:
            proposal = self.root / "queue" / row["proposalFile"]
            self.assertEqual(digest(proposal), row["proposalSha256"])
            self.assertEqual(json.loads(proposal.read_text())["status"], "review-required")

    def test_limit_bounds_review_queue(self) -> None:
        value = self.prepare("bounded", 1)
        self.assertEqual(value["eligibleCandidateCount"], 2)
        self.assertEqual(value["proposalCount"], 1)

    def test_v2_request_carries_exact_semantic_source_selection_into_queue(self) -> None:
        selection = self.write(
            "semantic-selection.json",
            {
                "schema": "agentlab.feedback_semantic_source_selection.v1",
                "sourceRelevanceEvidenceBound": True,
                "semanticAlignmentVerified": False,
                "automaticPromotion": False,
            },
        )
        request = json.loads(self.request.read_text())
        request["schema"] = "agentlab.feedback_analysis_request.v2"
        request["semanticSourceSelection"] = {"sha256": digest(selection)}
        self.request = self.write("request-v2.json", request)
        value = PREPARE.prepare(
            self.request,
            self.handoff,
            self.prior_case,
            self.feedback,
            self.analysis,
            self.analysis_run,
            self.difficulty,
            self.root / "queue-v2",
            10,
            selection,
        )
        self.assertEqual(value["semanticSourceSelectionSha256"], digest(selection))

    def test_tampered_prior_case_is_rejected(self) -> None:
        self.prior_case.write_text(self.prior_case.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "request prior case digest differs"):
            self.prepare()

    def test_analysis_must_bind_exact_difficulty_bytes(self) -> None:
        value = json.loads(self.analysis.read_text())
        value["difficultyCandidatesSha256"] = "0" * 64
        self.analysis = self.write("wrong-analysis.json", value)
        with self.assertRaisesRegex(ValueError, "does not bind difficulty evidence"):
            self.prepare()

    def test_analysis_run_must_bind_requested_method_revision(self) -> None:
        value = json.loads(self.analysis_run.read_text())
        value["methodRevision"] = "9" * 40
        self.analysis_run = self.write("wrong-analysis-run.json", value)
        with self.assertRaisesRegex(ValueError, "analysis run method revision differs"):
            self.prepare()

    def test_schema_marks_semantic_alignment_unverified(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/feedback-analysis-proposal-queue.schema.json").read_text()
        )
        self.assertFalse(
            schema["properties"]["selectionPolicy"]["properties"]["semanticAlignmentVerified"]["const"]
        )
        self.assertFalse(schema["properties"]["automaticPromotion"]["const"])

    def test_alpha13_retained_qualification_binds_successor_analysis_queue(self) -> None:
        qualification = json.loads(
            (
                ROOT
                / "release/qualifications/alpha13-feedback-analysis-proposals-b8aadaa/summary.json"
            ).read_text()
        )
        handoff = (
            ROOT
            / "release/qualifications/alpha13-recursive-feedback-4f24f9a/summary.json"
        )
        prior_case = handoff.parent / "prior-case.json"
        feedback = handoff.parent / "assessment-feedback-candidates.json"

        self.assertEqual(
            qualification["schema"],
            "agentlab.feedback_analysis_proposal_qualification.v1",
        )
        self.assertEqual(
            qualification["source"]["methodRevision"],
            "b8aadaadc0739c0ffac9a57717c42c7bf0e2a9b0",
        )
        self.assertEqual(qualification["inputs"]["feedbackHandoffSha256"], digest(handoff))
        self.assertEqual(qualification["inputs"]["priorCaseSha256"], digest(prior_case))
        self.assertEqual(qualification["inputs"]["feedbackEvidenceSha256"], digest(feedback))
        self.assertEqual(qualification["analysis"]["counts"]["facts"], 404308)
        self.assertEqual(
            qualification["analysis"]["counts"]["difficultyCandidates"], 19374
        )
        self.assertEqual(qualification["proposalQueue"]["eligibleCandidateCount"], 97)
        self.assertEqual(qualification["proposalQueue"]["proposalCount"], 10)
        self.assertEqual(
            [row["rank"] for row in qualification["proposalQueue"]["topProposals"]],
            [1, 2, 3],
        )
        self.assertEqual(qualification["transport"]["authority"], "git-object-id")
        self.assertTrue(qualification["transport"]["remainingBlobsResolvedByAnalyzer"])
        self.assertEqual(
            qualification["reviewBoundary"]["status"],
            "triaged-no-semantic-alignment",
        )
        self.assertEqual(qualification["reviewBoundary"]["reviewedProposalCount"], 10)
        self.assertEqual(qualification["reviewBoundary"]["shortlistedProposalCount"], 0)
        self.assertEqual(qualification["reviewBoundary"]["rejectedProposalCount"], 10)
        self.assertFalse(qualification["reviewBoundary"]["semanticAlignmentVerified"])
        self.assertFalse(qualification["reviewBoundary"]["automaticPromotion"])

    def test_exact_analysis_workflow_generates_bounded_review_queue(self) -> None:
        workflow = (ROOT / ".github/workflows/multi-repo-analysis.yml").read_text()
        self.assertIn("scripts/prepare-feedback-analysis-proposals.py", workflow)
        self.assertIn("--prior-case \"$qualification_root/prior-case.json\"", workflow)
        self.assertIn("--analysis-run \"$AGENTLAB_ROOT/source/analysis-run.json\"", workflow)
        self.assertIn("--max-candidates 10", workflow)
        self.assertIn("feedback-analysis-proposals/", workflow)


if __name__ == "__main__":
    unittest.main()
