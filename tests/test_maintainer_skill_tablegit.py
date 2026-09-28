import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "maintainer_skill_tablegit", ROOT / "scripts/maintainer-skill-tablegit.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MaintainerSkillTableGitTest(unittest.TestCase):
    def test_expected_mcp_tool_error_is_parsed_even_when_inspector_exits_nonzero(self):
        structured = {
            "outcome": "error",
            "error": {
                "code": "validation",
                "message": "validation error: table program_facts does not exist at " + "a" * 40,
            },
        }
        process = MODULE.subprocess.CompletedProcess(
            args=[], returncode=1,
            stdout=json.dumps({"result": {"structuredContent": structured, "isError": True}}),
            stderr='{"error":{"code":"tool_is_error"}}',
        )
        client = MODULE.Inspector("https://example.invalid/mcp", "person")
        with mock.patch.object(MODULE.subprocess, "run", return_value=process):
            result = client.call(
                "skill_run_read", "table.query", "table_status",
                {"repo": "agentlabtablegit", "path": "program_facts"}, allow_error=True,
            )
        self.assertTrue(MODULE.is_missing_table(result, "program_facts"))

    def test_envelope_round_trip_is_digest_bound(self):
        row = {
            "id": "fact-one",
            "repositoryId": "sample",
            "sourceRevision": "a" * 40,
            "kind": "analysis",
            "newFutureField": {"kept": [1, 2, 3]},
        }
        wrapped = MODULE.envelope(row)
        exported = MODULE.unwrap_rows("program_facts", [{
            "key": row["id"], "row": wrapped, "deleted": False,
        }])
        self.assertEqual(exported, [row])
        wrapped["payload"]["kind"] = "changed"
        with self.assertRaisesRegex(RuntimeError, "payload digest differs"):
            MODULE.unwrap_rows("program_facts", [{
                "key": row["id"], "row": wrapped, "deleted": False,
            }])

    def test_transaction_chunks_are_bounded_and_stable(self):
        rows = [{"id": f"row-{index:03d}", "body": "x" * 4000} for index in range(40)]
        chunks = MODULE.operation_chunks("maintainer_skills", rows, "123", max_bytes=20_000)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(sum(map(len, chunks)), len(rows))
        self.assertEqual(
            chunks[0][0]["operation_id"],
            MODULE.operation_chunks("maintainer_skills", rows, "123", max_bytes=20_000)[0][0]["operation_id"],
        )

    def test_missing_row_chunks_do_not_reuse_a_completed_chunk_receipt(self):
        rows = [{"id": f"row-{index:03d}", "body": "x" * 4000} for index in range(12)]
        chunks = MODULE.operation_chunks("program_facts", rows, "123", max_bytes=20_000)
        first = MODULE.stable_uuid(
            "123", "program_facts", MODULE.hashlib.sha256(MODULE.canonical(chunks[0])).hexdigest(), "tablegit-v1"
        )
        retry_chunks = MODULE.operation_chunks("program_facts", rows[len(chunks[0]):], "123", max_bytes=20_000)
        retry = MODULE.stable_uuid(
            "123", "program_facts", MODULE.hashlib.sha256(MODULE.canonical(retry_chunks[0])).hexdigest(), "tablegit-v1"
        )
        self.assertNotEqual(first, retry)

    def test_stage_appends_one_non_promoted_lineage_round(self):
        source = ROOT / "examples/maintainer-knowledge-gate/first-four"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_facts = root / "candidate.jsonl"
            candidate_facts.write_text((source / "program_facts.jsonl").read_text())
            candidate = {
                "id": "agent-analysis-test-contract",
                "kind": "analysis",
                "repositoryId": "code-workshop",
                "sourceRevision": "a" * 40,
                "scopeSkillIds": ["skill-scope-code-workshop-appscope"],
                "dimensions": ["behavior", "boundary", "relations", "responsibility"],
            }
            with candidate_facts.open("a") as stream:
                stream.write(json.dumps(candidate) + "\n")
            assessment = root / "assessment.json"
            assessment.write_text(json.dumps({
                "roundIndex": 5,
                "nextRoundObjectives": ["continue exact evidence closure"],
            }) + "\n")
            result = root / "result.json"
            result.write_text(json.dumps({
                "decision": "review-proposed-knowledge",
                "after": {
                    "scopeSkillCount": 480, "programBoundCount": 14,
                    "semanticReadyCount": 7, "maintenanceReadyCount": 2,
                },
            }) + "\n")
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({"acceptedFactId": candidate["id"]}) + "\n")
            output = root / "stage"
            MODULE.command_stage(type("Args", (), {
                "base": source,
                "candidate_program_facts": candidate_facts,
                "candidate_assessment": assessment,
                "result": result,
                "receipt": receipt,
                "run_id": "42",
                "github_repository": "owner/repo",
                "output": output,
            }))
            rounds = MODULE.load_jsonl(output / "maintainer_skill_refresh_rounds.jsonl")
            latest = max(rounds, key=lambda row: row["roundIndex"])
            previous = max(
                MODULE.load_jsonl(source / "maintainer_skill_refresh_rounds.jsonl"),
                key=lambda row: row["roundIndex"],
            )
            self.assertEqual(latest["roundIndex"], previous["roundIndex"] + 1)
            self.assertFalse(latest["automaticPromotion"])
            self.assertEqual(latest["producer"]["runId"], "42")
            self.assertEqual(latest["parentRoundSha256"], MODULE.value_sha256(
                previous
            ))
            self.assertEqual(latest["assessment"]["sha256"], MODULE.file_sha256(assessment))
            self.assertEqual(
                latest["tables"]["processSkillsSha256"],
                MODULE.file_sha256(output / "maintainer_skills.jsonl"),
            )
            self.assertEqual(
                latest["tables"]["programFactsSha256"],
                MODULE.file_sha256(output / "program_facts.jsonl"),
            )
            self.assertEqual(
                MODULE.load(output / "stage-manifest.json")["assessment"],
                "assessments/round-5-agent-42.json",
            )
            self.assertTrue((output / "maintainer-knowledge-cut.json").is_file())
            self.assertTrue((output / "assessments/round-5-agent-42.json").is_file())


if __name__ == "__main__":
    unittest.main()
