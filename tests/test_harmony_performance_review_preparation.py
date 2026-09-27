from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/prepare-harmony-performance-review.py"
BUILDER = ROOT / "scripts/build-cbgroom-flywheel-transaction.py"
EVIDENCE = ROOT / "release/qualifications/harmony-performance-automated-calibration-v1"


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HarmonyPerformanceReviewPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.plan = self.root / "plan.json"
        self.plan.write_text(
            json.dumps(
                {
                    "schema": "agentlab.harmony_performance_review_plan.v1",
                    "evidence": str(EVIDENCE),
                    "transactionBuilder": str(BUILDER),
                    "transactionBuilderSha256": digest(BUILDER),
                    "expectedRevision": "2" * 40,
                    "runId": "automated-calibration-review",
                    "githubRepository": "example/agentlab",
                    "callerPersonId": "00000000-0000-0000-0000-000000000001",
                    "repo": "agentlabtablegit",
                    "automaticPublication": False,
                    "automaticPromotion": False,
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_preparer(self, output: pathlib.Path):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--plan", str(self.plan), "--output", str(output)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_real_calibration_prepares_review_without_publication(self) -> None:
        output = self.root / "review"
        completed = self.run_preparer(output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads((output / "preparation.json").read_text())
        transaction = json.loads((output / "transaction.json").read_text())
        self.assertEqual(receipt["status"], "prepared-not-published")
        self.assertEqual(receipt["evidenceFileCount"], 13)
        self.assertEqual(receipt["counts"]["performanceDecisions"], 1)
        self.assertEqual(receipt["counts"]["performanceDifficulties"], 1)
        self.assertFalse(receipt["automaticPublication"])
        self.assertFalse(receipt["automaticPromotion"])
        self.assertEqual(receipt["transactionSha256"], digest(output / "transaction.json"))
        self.assertEqual(transaction["arguments"]["expected_revision"], "2" * 40)
        rows = [
            operation["row"]
            for table in transaction["arguments"]["tables"]
            for operation in table["operations"]
        ]
        difficulty = next(
            row for row in rows
            if row.get("dimensionId") == "functionally-correct-performance-regression"
        )
        self.assertFalse(difficulty["verificationContract"]["caseReady"])
        self.assertFalse(difficulty["automaticPromotion"])

    def test_builder_digest_drift_fails_before_transaction_generation(self) -> None:
        plan = json.loads(self.plan.read_text())
        plan["transactionBuilderSha256"] = "f" * 64
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        output = self.root / "review"
        completed = self.run_preparer(output)
        self.assertEqual(completed.returncode, 1)
        self.assertFalse(output.exists())
        stage = next(self.root.glob(".review.stage-*"))
        failure = json.loads((stage / "failure.json").read_text())
        self.assertIn("SHA256 differs", failure["error"])
        self.assertFalse((stage / "transaction.json").exists())

    def test_existing_output_is_never_overwritten(self) -> None:
        output = self.root / "review"
        output.mkdir()
        marker = output / "marker"
        marker.write_text("keep", encoding="utf-8")
        completed = self.run_preparer(output)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(marker.read_text(), "keep")
        self.assertEqual(list(self.root.glob(".review.stage-*")), [])


if __name__ == "__main__":
    unittest.main()
