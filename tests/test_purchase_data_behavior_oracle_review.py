import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/review-purchase-data-behavior-oracle.py"
spec = importlib.util.spec_from_file_location("purchase_data_behavior_oracle_review", SCRIPT)
REVIEW = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(REVIEW)

EVIDENCE = ROOT / "release/qualifications/alpha13-payment-feedback-analysis-165bcbd"
PLAN = EVIDENCE / "purchase-data-behavior-oracle-plan.json"
CALIBRATION = EVIDENCE / "purchase-data-behavior-oracle-calibration.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PurchaseDataBehaviorOracleReviewTests(unittest.TestCase):
    def semantic_gate(self, root: Path, *, approved: bool = True) -> Path:
        plan = json.loads(PLAN.read_text())
        path = root / "semantic-gate.json"
        path.write_text(json.dumps({
            "schema": "agentlab.multi_repo_candidate_semantic_gate.v1",
            "status": "approved-for-case-contract-proposal" if approved else "deferred-for-more-evidence",
            "candidateId": plan["candidateId"],
            "sourceSetSha256": plan["sourceSetSha256"],
            "packetSha256": plan["reviewPacketSha256"],
            "decisionSha256": "d" * 64,
            "reviewer": "github:semantic-reviewer",
            "verdict": "advance-to-case-contract" if approved else "defer-for-more-evidence",
            "responses": [],
            "allowsCaseContract": approved,
            "declaredRepresentative": False,
            "automaticPromotion": False,
        }, sort_keys=True) + "\n")
        return path

    def answers(self, root: Path, answer: str = "yes") -> Path:
        path = root / "answers.json"
        path.write_text(json.dumps({
            "schema": REVIEW.ANSWERS_SCHEMA,
            "responses": [
                {
                    "id": question_id,
                    "answer": answer,
                    "rationale": f"Independent evidence assessment for {question_id} is recorded here.",
                }
                for question_id in REVIEW.QUESTION_IDS
            ],
        }, sort_keys=True) + "\n")
        return path

    def decide(self, root: Path, semantic_gate: Path, calibration: Path = CALIBRATION):
        return REVIEW.decide(
            PLAN,
            calibration,
            semantic_gate,
            ROOT,
            sha(PLAN),
            sha(calibration),
            self.answers(root),
            "github:oracle-reviewer",
            ",".join(REVIEW.RISK_IDS),
            "approve-for-runtime-calibration",
            "The exact bounded evidence is adequate to proceed to isolated runtime calibration.",
        )

    def test_distinct_reviewers_can_approve_only_runtime_calibration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            semantic_gate = self.semantic_gate(root)
            decision_value = self.decide(root, semantic_gate)
            decision = root / "decision.json"
            decision.write_text(json.dumps(decision_value, indent=2, sort_keys=True) + "\n")
            gate = REVIEW.compile_gate(PLAN, CALIBRATION, semantic_gate, decision, ROOT)
            self.assertEqual(gate["status"], "approved-for-runtime-calibration")
            self.assertTrue(gate["semanticAlignmentVerified"])
            self.assertTrue(gate["behaviorOracleCandidateReviewed"])
            self.assertTrue(gate["allowsRuntimeCalibration"])
            self.assertFalse(gate["behaviorOracleVerified"])
            self.assertFalse(gate["allowsCaseContract"])
            self.assertFalse(gate["automaticPromotion"])

    def test_oracle_reviewer_must_differ_from_semantic_reviewer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            semantic_gate = self.semantic_gate(root)
            with self.assertRaisesRegex(REVIEW.OracleReviewError, "must differ"):
                REVIEW.decide(
                    PLAN,
                    CALIBRATION,
                    semantic_gate,
                    ROOT,
                    sha(PLAN),
                    sha(CALIBRATION),
                    self.answers(root),
                    "github:semantic-reviewer",
                    ",".join(REVIEW.RISK_IDS),
                    "approve-for-runtime-calibration",
                    "The review identity deliberately collides with the semantic reviewer identity.",
                )

    def test_unapproved_semantic_gate_cannot_enter_oracle_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            semantic_gate = self.semantic_gate(root, approved=False)
            with self.assertRaisesRegex(REVIEW.OracleReviewError, "not independently approved"):
                self.decide(root, semantic_gate)

    def test_undetected_negative_control_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            semantic_gate = self.semantic_gate(root)
            value = json.loads(CALIBRATION.read_text())
            negative = next(row for row in value["variants"] if row["role"] == "meaningful-wrong")
            negative["observedFailedChecks"] = []
            negative["expectationMatched"] = False
            changed = root / "calibration.json"
            changed.write_text(json.dumps(value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(REVIEW.OracleReviewError, "expectation did not match"):
                self.decide(root, semantic_gate, changed)

    def test_gate_rejects_decision_digest_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            semantic_gate = self.semantic_gate(root)
            decision_value = self.decide(root, semantic_gate)
            decision_value["planSha256"] = "0" * 64
            decision = root / "decision.json"
            decision.write_text(json.dumps(decision_value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(REVIEW.OracleReviewError, "decision plan differs"):
                REVIEW.compile_gate(PLAN, CALIBRATION, semantic_gate, decision, ROOT)

    def test_workflow_is_trusted_main_and_preserves_both_reviewers(self):
        workflow = (ROOT / ".github/workflows/purchase-data-behavior-oracle-review.yml").read_text()
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("multi-repo-candidate-semantic-review.yml", workflow)
        self.assertIn("git merge-base --is-ancestor", workflow)
        self.assertIn("ORACLE_REVIEWER: github:${{ github.actor }}", workflow)
        self.assertIn("purchase-data-behavior-oracle-review", workflow)
        self.assertNotIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
