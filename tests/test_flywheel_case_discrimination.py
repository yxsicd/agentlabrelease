from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FlywheelCaseDiscriminationTests(unittest.TestCase):
    def run_builder(self, evidence: pathlib.Path, output: pathlib.Path):
        return subprocess.run(
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
        )

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
            completed = self.run_builder(evidence, output)
            self.assertEqual(completed.returncode, 0, completed.stderr)
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

    def test_report_from_another_source_revision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "summary.json").write_text(
                json.dumps({"sourceRevision": "3" * 40, "taskId": "campaign"})
            )
            report = json.loads(
                subprocess.run(
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
            )
            (evidence / "case-discrimination-report.json").write_text(json.dumps(report))
            completed = self.run_builder(evidence, root / "transaction.json")
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("does not match run summary", completed.stderr)

    def test_multi_repo_report_retains_source_set_identity(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            evidence = root / "evidence"
            evidence.mkdir()
            source_set = "a" * 64
            (evidence / "summary.json").write_text(
                json.dumps(
                    {
                        "schema": "agentlab.multi_repo_assessment_summary.v1",
                        "sourceSetSha256": source_set,
                        "taskId": "campaign",
                    }
                )
            )
            value = json.loads(
                (ROOT / "examples/case-discrimination/fixture.json").read_text()
            )
            value["schema"] = "agentlab.case_discrimination_input.v2"
            value.pop("sourceRevision")
            value["sourceSetSha256"] = source_set
            input_path = root / "input.json"
            input_path.write_text(json.dumps(value))
            report = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/score-case-discrimination.py"),
                    "--input",
                    str(input_path),
                ],
                text=True,
                capture_output=True,
                check=True,
            ).stdout
            (evidence / "case-discrimination-report.json").write_text(report)
            output = root / "transaction.json"
            completed = self.run_builder(evidence, output)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output.read_text())
            decisions = [
                operation["row"]
                for table in payload["arguments"]["tables"]
                if table["path"] == "decisions"
                for operation in table["operations"]
                if operation["row"]["schema"] == "agentlab.case_selection_decision.v1"
            ]
            self.assertEqual(len(decisions), 3)
            self.assertTrue(all(row["sourceSetSha256"] == source_set for row in decisions))
            self.assertTrue(all("sourceRevision" not in row for row in decisions))


if __name__ == "__main__":
    unittest.main()
