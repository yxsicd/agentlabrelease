from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/triage-feedback-analysis-proposal-queue.py"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


TRIAGE = load_module("triage_feedback_analysis_proposal_queue", SCRIPT)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FeedbackAnalysisProposalQueueTriageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.proposal_root = self.root / "proposals"
        self.proposal_root.mkdir()
        rows = []
        for rank in (1, 2):
            proposal = {
                "schema": "agentlab.feedback_analysis_cut_proposal.v1",
                "status": "review-required",
                "cutId": f"feedback-analysis-cut-{rank}",
                "nextAnalysis": {
                    "candidateId": f"difficulty-{rank}",
                    "mechanism": f"cross-repository mechanism {rank}",
                },
                "automaticPromotion": False,
            }
            path = self.write(self.proposal_root / f"proposal-{rank:02d}.json", proposal)
            rows.append(
                {
                    "rank": rank,
                    "proposalFile": path.name,
                    "proposalSha256": digest(path),
                    "cutId": proposal["cutId"],
                    "difficultyCandidateId": proposal["nextAnalysis"]["candidateId"],
                }
            )
        self.queue = self.write(
            self.root / "index.json",
            {
                "schema": "agentlab.feedback_analysis_proposal_queue.v1",
                "status": "maintainer-review-required",
                "eligibleCandidateCount": 12,
                "proposalCount": 2,
                "proposals": rows,
                "automaticPromotion": False,
            },
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, path: pathlib.Path, value: dict) -> pathlib.Path:
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        return path

    def review(self, verdicts: list[str]) -> pathlib.Path:
        queue = json.loads(self.queue.read_text())
        decisions = []
        for row, verdict in zip(queue["proposals"], verdicts, strict=True):
            decisions.append(
                {
                    "proposalSha256": row["proposalSha256"],
                    "cutId": row["cutId"],
                    "difficultyCandidateId": row["difficultyCandidateId"],
                    "verdict": verdict,
                    "rationale": "Exact evidence does not support semantic alignment.",
                    "evidence": ["the observed failure belongs to a different stage"],
                }
            )
        return self.write(
            self.root / "review.json",
            {
                "schema": "agentlab.feedback_analysis_proposal_queue_triage_review.v1",
                "queueSha256": digest(self.queue),
                "reviewer": "maintainer",
                "automaticPromotion": False,
                "decisions": decisions,
            },
        )

    def triage(self, review: pathlib.Path) -> dict:
        return TRIAGE.triage(self.queue, self.proposal_root, review)

    def test_all_rejected_returns_to_semantic_source_selection(self) -> None:
        value = self.triage(
            self.review(["reject-semantic-misalignment", "reject-semantic-misalignment"])
        )
        self.assertEqual(value["status"], "no-semantic-alignment")
        self.assertEqual(value["denominators"]["reviewedProposalCount"], 2)
        self.assertEqual(value["denominators"]["shortlistedProposalCount"], 0)
        self.assertEqual(value["denominators"]["rejectedProposalCount"], 2)
        self.assertIsNone(value["selectedProposal"])
        self.assertFalse(value["semanticAlignmentVerified"])
        self.assertFalse(value["automaticPromotion"])
        self.assertEqual(
            value["nextGate"],
            "select-semantically-related-source-set-or-enrich-feedback-mechanism",
        )

    def test_one_shortlist_still_requires_independent_review(self) -> None:
        value = self.triage(
            self.review(["shortlist-for-independent-review", "reject-semantic-misalignment"])
        )
        self.assertEqual(value["status"], "one-proposal-shortlisted-review-required")
        self.assertEqual(value["selectedProposal"]["rank"], 1)
        self.assertFalse(value["semanticAlignmentVerified"])
        self.assertFalse(value["automaticPromotion"])

    def test_missing_decision_is_rejected(self) -> None:
        review = self.review(["reject-semantic-misalignment", "reject-semantic-misalignment"])
        value = json.loads(review.read_text())
        value["decisions"].pop()
        self.write(review, value)
        with self.assertRaisesRegex(ValueError, "decide every proposal"):
            self.triage(review)

    def test_two_shortlists_are_rejected(self) -> None:
        review = self.review(
            ["shortlist-for-independent-review", "shortlist-for-independent-review"]
        )
        with self.assertRaisesRegex(ValueError, "at most one proposal"):
            self.triage(review)

    def test_tampered_proposal_is_rejected(self) -> None:
        review = self.review(["reject-semantic-misalignment", "reject-semantic-misalignment"])
        proposal = self.proposal_root / "proposal-01.json"
        proposal.write_text(proposal.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "queue proposal digest differs"):
            self.triage(review)

    def test_unknown_proposal_decision_is_rejected(self) -> None:
        review = self.review(["reject-semantic-misalignment", "reject-semantic-misalignment"])
        value = json.loads(review.read_text())
        value["decisions"][1]["proposalSha256"] = "f" * 64
        self.write(review, value)
        with self.assertRaisesRegex(ValueError, "omits an exact queued proposal"):
            self.triage(review)

    def test_schema_keeps_triage_non_promoting(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/feedback-analysis-proposal-queue-triage.schema.json").read_text()
        )
        self.assertFalse(schema["properties"]["semanticAlignmentVerified"]["const"])
        self.assertFalse(schema["properties"]["automaticPromotion"]["const"])
        self.assertEqual(
            schema["properties"]["denominators"]["properties"]["shortlistedProposalCount"]["maximum"],
            1,
        )
        self.assertEqual(schema["properties"]["decisions"]["items"]["$ref"], "#/$defs/decision")

    def test_alpha13_retained_triage_rejects_all_unaligned_candidates(self) -> None:
        qualification = json.loads(
            (
                ROOT
                / "release/qualifications/alpha13-feedback-analysis-triage-b8aadaa/summary.json"
            ).read_text()
        )
        self.assertEqual(qualification["status"], "no-semantic-alignment")
        self.assertEqual(qualification["decision"]["reviewedProposalCount"], 10)
        self.assertEqual(qualification["decision"]["shortlistedProposalCount"], 0)
        self.assertEqual(qualification["decision"]["rejectedProposalCount"], 10)
        self.assertEqual(len(qualification["rejectedCandidates"]), 10)
        self.assertFalse(qualification["decision"]["semanticAlignmentVerified"])
        self.assertFalse(qualification["decision"]["automaticPromotion"])
        self.assertEqual(
            qualification["retention"]["nextGate"],
            "select-semantically-related-source-set-or-enrich-feedback-mechanism",
        )


if __name__ == "__main__":
    unittest.main()
