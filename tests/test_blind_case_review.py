from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


CUT = load_module("blind_case_cut_for_review", ROOT / "scripts/build-blind-case-cut.py")
REVIEW = load_module("blind_case_review", ROOT / "scripts/review-blind-case-cut.py")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_cut(root: Path) -> Path:
    source = root / "source"
    participant = source / "participant"
    evaluator = source / "evaluator"
    participant.mkdir(parents=True)
    evaluator.mkdir()
    (participant / "task.md").write_text("Repair the missing route without changing existing behavior.\n")
    (participant / "source.json").write_text('{"revision":"baseline"}\n')
    (evaluator / "oracle.ui").write_text("assert-text\ttarget\tExample Domain\n")
    (evaluator / "reference.patch").write_text("+pages/UserAgent_four\n")
    manifest = {
        "schema": "agentlab.blind_case_source.v1",
        "cutId": "review-cut-001",
        "caseId": "review-case-001",
        "methodRevision": "1" * 40,
        "sourceSetSha256": "2" * 64,
        "participantFiles": [
            {"path": "task.md", "role": "task", "sha256": sha(participant / "task.md")},
            {"path": "source.json", "role": "source", "sha256": sha(participant / "source.json")},
        ],
        "evaluatorFiles": [
            {"path": "oracle.ui", "role": "oracle", "sha256": sha(evaluator / "oracle.ui")},
            {"path": "reference.patch", "role": "reference", "sha256": sha(evaluator / "reference.patch")},
        ],
        "participantConstraints": {
            "allowedEditPaths": ["entry/src/main/resources/base/profile/main_pages.json"],
            "budget": {"turns": 8},
            "environmentRef": "harmony-linux-x86-pinned",
            "networkPolicy": "operator-gateway-only",
        },
        "freshness": {
            "sourceVisibility": "private-maintenance",
            "cutConstructedAt": "2026-09-25T00:00:00Z",
            "participantAccessBeforeCut": False,
            "modelTrainingExclusionKnown": False,
            "contaminationReview": "review-required",
        },
    }
    (source / "case-source.json").write_text(json.dumps(manifest))
    cut = root / "cut"
    CUT.build_cut(source, cut)
    return cut


def qualified_verdicts() -> dict[str, str]:
    return {field: "qualified" for field in REVIEW.DIMENSIONS}


class BlindCaseReviewTests(unittest.TestCase):
    def prepare(self, root: Path):
        cut = build_cut(root)
        request = root / "review-request.json"
        REVIEW.prepare_request(cut, "constructor-a", request)
        return cut, request

    def decision(
        self,
        root: Path,
        request: Path,
        reviewer: str,
        verdicts: dict[str, str] | None = None,
    ) -> Path:
        output = root / f"{reviewer}.json"
        REVIEW.create_decision(
            request,
            sha(request),
            reviewer,
            verdicts or qualified_verdicts(),
            "Reviewed exact participant and evaluator projections against retained evidence.",
            [hashlib.sha256((reviewer + "-evidence").encode()).hexdigest()],
            output,
        )
        return output

    def test_two_distinct_unanimous_records_qualify_consensus_not_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cut, request = self.prepare(root)
            first = self.decision(root, request, "reviewer-a")
            second = self.decision(root, request, "reviewer-b")
            output = root / "adjudication.json"
            result = REVIEW.adjudicate(request, [first, second], cut, output)
            self.assertEqual(
                REVIEW.validate_adjudication(output, request, [first, second], cut),
                result,
            )
            self.assertTrue(result["distinctReviewerRecordsQualified"])
            self.assertTrue(result["semanticLeakReviewConsensusQualified"])
            self.assertTrue(result["contaminationRiskReviewConsensusQualified"])
            self.assertTrue(result["reviewConsensusQualified"])
            self.assertFalse(result["reviewerIdentityAuthenticationQualified"])
            self.assertFalse(result["blindPilotReviewQualified"])
            self.assertEqual(result["disagreementRate"], 0.0)
            self.assertFalse(result["modelTrainingExclusionQualified"])
            self.assertFalse(result["eligibleForUnseenAgentDiscrimination"])
            self.assertEqual(result["participantManifestSha256"], sha(cut / "participant/manifest.json"))

    def test_constructor_cannot_review_own_cut(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cut, request = self.prepare(root)
            with self.assertRaisesRegex(REVIEW.BlindReviewError, "independent from the constructor"):
                self.decision(root, request, "constructor-a")

    def test_reviewer_must_bind_the_exact_request_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cut, request = self.prepare(root)
            with self.assertRaisesRegex(REVIEW.BlindReviewError, "does not match exact"):
                REVIEW.create_decision(
                    request,
                    "f" * 64,
                    "reviewer-a",
                    qualified_verdicts(),
                    "Exact review.",
                    ["e" * 64],
                    root / "review.json",
                )

    def test_disagreement_is_measured_and_blocks_qualification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cut, request = self.prepare(root)
            first = self.decision(root, request, "reviewer-a")
            verdicts = qualified_verdicts()
            verdicts["oracleBreadth"] = "unknown"
            second = self.decision(root, request, "reviewer-b", verdicts)
            output = root / "adjudication.json"
            result = REVIEW.adjudicate(request, [first, second], cut, output)
            self.assertFalse(result["dimensions"]["oracleBreadth"]["unanimous"])
            self.assertFalse(result["reviewConsensusQualified"])
            self.assertFalse(result["blindPilotReviewQualified"])
            self.assertEqual(result["disagreementRate"], 0.25)

    def test_duplicate_reviewer_cannot_satisfy_multi_reviewer_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cut, request = self.prepare(root)
            first = self.decision(root, request, "reviewer-a")
            duplicate = root / "duplicate.json"
            duplicate.write_bytes(first.read_bytes())
            with self.assertRaisesRegex(REVIEW.BlindReviewError, "reviewers must be unique"):
                REVIEW.adjudicate(
                    request,
                    [first, duplicate],
                    cut,
                    root / "adjudication.json",
                )

    def test_adjudication_revalidates_the_exact_cut(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cut, request = self.prepare(root)
            first = self.decision(root, request, "reviewer-a")
            second = self.decision(root, request, "reviewer-b")
            (cut / "participant/task.md").write_text("tampered after review request\n")
            with self.assertRaisesRegex(ValueError, "digest differs"):
                REVIEW.adjudicate(
                    request,
                    [first, second],
                    cut,
                    root / "adjudication.json",
                )

    def test_tampered_decision_breaks_adjudication_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cut, request = self.prepare(root)
            first = self.decision(root, request, "reviewer-a")
            second = self.decision(root, request, "reviewer-b")
            output = root / "adjudication.json"
            REVIEW.adjudicate(request, [first, second], cut, output)
            decision = json.loads(first.read_text())
            decision["rationale"] = "tampered"
            first.write_text(json.dumps(decision))
            with self.assertRaisesRegex(REVIEW.BlindReviewError, "review lineage differs"):
                REVIEW.validate_adjudication(output, request, [first, second], cut)

    def test_cli_round_trip_preserves_exact_review_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cut = build_cut(root)
            request = root / "request.json"
            subprocess.run(
                [
                    "python3", str(ROOT / "scripts/review-blind-case-cut.py"),
                    "prepare", "--cut", str(cut), "--constructor", "constructor-a",
                    "--output", str(request),
                ],
                check=True,
                capture_output=True,
            )
            reviews = []
            for reviewer, evidence in (("reviewer-a", "a" * 64), ("reviewer-b", "b" * 64)):
                review = root / f"{reviewer}.json"
                subprocess.run(
                    [
                        "python3", str(ROOT / "scripts/review-blind-case-cut.py"),
                        "decide", "--request", str(request),
                        "--expected-request-sha256", sha(request),
                        "--reviewer", reviewer,
                        "--semantic-leakage", "qualified",
                        "--contamination-risk", "qualified",
                        "--specification-fairness", "qualified",
                        "--oracle-breadth", "qualified",
                        "--rationale", "Exact independent review.",
                        "--evidence-sha256", evidence,
                        "--output", str(review),
                    ],
                    check=True,
                    capture_output=True,
                )
                reviews.append(review)
            output = root / "adjudication.json"
            subprocess.run(
                [
                    "python3", str(ROOT / "scripts/review-blind-case-cut.py"),
                    "adjudicate", "--cut", str(cut), "--request", str(request),
                    "--review", str(reviews[0]), "--review", str(reviews[1]),
                    "--output", str(output),
                ],
                check=True,
                capture_output=True,
            )
            result = json.loads(output.read_text())
            self.assertTrue(result["reviewConsensusQualified"])
            self.assertFalse(result["blindPilotReviewQualified"])
            self.assertFalse(result["eligibleForUnseenAgentDiscrimination"])


if __name__ == "__main__":
    unittest.main()
