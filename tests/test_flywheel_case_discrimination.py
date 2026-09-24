from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FlywheelCaseDiscriminationTests(unittest.TestCase):
    def test_ranked_cases_become_durable_review_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "summary.json").write_text(
                json.dumps(
                    {
                        "schema": "agentlab.subject.v1",
                        "sourceRevision": "1" * 40,
                        "taskId": "campaign",
                    }
                )
            )
            report = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/score-case-discrimination.py"),
                    "--input",
                    str(ROOT / "examples/case-discrimination/fixture.json"),
                ],
                text=True,
                capture_output=True,
                check=True,
            ).stdout
            (evidence / "case-discrimination-report.json").write_text(report)
            output = root / "transaction.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/build-cbgroom-flywheel-transaction.py"),
                    "--evidence",
                    str(evidence),
                    "--revision",
                    "2" * 40,
                    "--run-id",
                    "fixture-run",
                    "--github-repository",
                    "example/agentlab",
                    "--caller-person-id",
                    "00000000-0000-0000-0000-000000000001",
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(output.read_text())
            tables = {
                table["path"]: [operation["row"] for operation in table["operations"]]
                for table in payload["arguments"]["tables"]
            }
            decisions = [
                row
                for row in tables["decisions"]
                if row["schema"] == "agentlab.case_selection_decision.v1"
            ]
            self.assertEqual(len(decisions), 3)
            eligible = [row for row in decisions if row["eligible"]]
            self.assertEqual([row["caseId"] for row in eligible], ["case-strong-separation"])
            self.assertTrue(all(row["automaticPromotion"] is False for row in decisions))
            self.assertTrue(all(row["evidenceIds"] for row in decisions))
            refs = tables["evidence_refs"]
            self.assertTrue(
                any(row["kind"] == "case-discrimination-report" for row in refs)
            )


if __name__ == "__main__":
    unittest.main()
