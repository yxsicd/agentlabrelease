import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class MultiRepoReviewDecisionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.proposal = self.root / "proposal.json"
        self.proposal.write_text(
            json.dumps(
                {
                    "schema": "agentlab.multi_repo_case_plan_proposal.v1",
                    "risks": [{"id": "risk-a"}, {"id": "risk-b"}],
                },
                sort_keys=True,
            )
            + "\n"
        )
        self.digest = hashlib.sha256(self.proposal.read_bytes()).hexdigest()

    def tearDown(self):
        self.temporary.cleanup()

    def run_decision(self, digest=None, risks="risk-b,risk-a"):
        return subprocess.run(
            [
                "python3",
                str(ROOT / "scripts/create-multi-repo-review-decision.py"),
                "--proposal",
                str(self.proposal),
                "--expected-sha256",
                digest or self.digest,
                "--reviewer",
                "reviewer-a",
                "--acknowledged-risk-ids",
                risks,
                "--rationale",
                "Exact source and risks inspected.",
                "--output",
                str(self.root / "nested/review.json"),
            ],
            text=True,
            capture_output=True,
        )

    def test_exact_digest_and_all_risks_create_review(self):
        result = self.run_decision()
        self.assertEqual(result.returncode, 0, result.stderr)
        review = json.loads((self.root / "nested/review.json").read_text())
        self.assertEqual(review["proposalSha256"], self.digest)
        self.assertEqual(review["acknowledgedRiskIds"], ["risk-a", "risk-b"])
        self.assertEqual(review["verdict"], "approve-for-calibration")

    def test_digest_mismatch_is_rejected(self):
        result = self.run_decision(digest="0" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match exact proposal", result.stderr)

    def test_incomplete_risk_acknowledgement_is_rejected(self):
        result = self.run_decision(risks="risk-a")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must exactly match proposal risks", result.stderr)


if __name__ == "__main__":
    unittest.main()
