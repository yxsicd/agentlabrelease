import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "maintainer_skill_tablegit", ROOT / "scripts/maintainer-skill-tablegit.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MaintainerSkillTableGitTest(unittest.TestCase):
    def test_exact_revision_table_reads_are_bounded_and_parallel(self):
        barrier = threading.Barrier(len(MODULE.TABLE_FILES))

        def query(_client, _repo, table, revision):
            self.assertEqual(revision, "a" * 40)
            barrier.wait(timeout=2)
            return [{"table": table}]

        with mock.patch.object(MODULE, "query_all", side_effect=query):
            result = MODULE.query_tables(object(), "repo", "a" * 40)
        self.assertEqual(list(result), list(MODULE.TABLE_FILES))
        self.assertEqual(
            {table: rows[0]["table"] for table, rows in result.items()},
            {table: table for table in MODULE.TABLE_FILES},
        )

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

    def test_existing_row_uses_full_digest_bound_upsert(self):
        row = {"id": "fact-one", "body": "refreshed"}
        operation = MODULE.operation_chunks(
            "program_facts", [row], "123", row_versions={"fact-one": 7}
        )[0][0]
        self.assertEqual(operation["op"], "upsert")
        self.assertEqual(operation["expected_row_version"], 7)
        self.assertEqual(operation["row"], MODULE.envelope(row))

    def test_delete_is_row_version_fenced_and_stable(self):
        operation = MODULE.deletion_operations(
            "maintainer_scope_skills", ["scope-parent"], "run", {"scope-parent": 9}
        )[0]
        self.assertEqual(operation["op"], "delete")
        self.assertEqual(operation["expected_row_version"], 9)
        self.assertEqual(
            operation,
            MODULE.deletion_operations(
                "maintainer_scope_skills", ["scope-parent"], "run", {"scope-parent": 9}
            )[0],
        )

    def test_persist_accepts_base_to_snapshot_update_and_fences_remote_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base"
            snapshot = root / "snapshot"
            base.mkdir(); snapshot.mkdir()
            base_rows = {}
            snapshot_rows = {}
            remote_items = {}
            for table, filename in MODULE.TABLE_FILES.items():
                row = {"id": f"{table}-row", "value": "base"}
                desired = dict(row)
                if table == "program_facts":
                    desired["value"] = "refreshed"
                base_rows[table] = row
                snapshot_rows[table] = desired
                MODULE.write_jsonl(base / filename, [row])
                MODULE.write_jsonl(snapshot / filename, [desired])
                remote_items[table] = [{
                    "key": row["id"], "row": MODULE.envelope(row),
                    "row_version": 3, "deleted": False,
                }]

            transactions = []
            def query(_client, _repo, table, _revision):
                return remote_items[table]
            def apply(_client, _repo, _revision, tables, *_args):
                transactions.append(tables)
                return "b" * 40

            with mock.patch.object(MODULE, "query_all", side_effect=query), \
                    mock.patch.object(MODULE, "apply_transaction", side_effect=apply):
                revision = MODULE.persist_snapshot(
                    object(), "repo", "a" * 40, base, snapshot, "run", "owner/repo"
                )
            self.assertEqual(revision, "b" * 40)
            operations = transactions[0][0]["operations"]
            self.assertEqual(len(operations), 1)
            self.assertEqual(operations[0]["op"], "upsert")
            self.assertEqual(operations[0]["expected_row_version"], 3)

            remote_items["program_facts"][0] = {
                "key": "program_facts-row",
                "row": MODULE.envelope({"id": "program_facts-row", "value": "concurrent"}),
                "row_version": 4,
                "deleted": False,
            }
            with mock.patch.object(MODULE, "query_all", side_effect=query):
                with self.assertRaisesRegex(RuntimeError, "conflicts with the Release snapshot"):
                    MODULE.persist_snapshot(
                        object(), "repo", "c" * 40, base, snapshot, "run-2", "owner/repo"
                    )

    def test_persist_replaces_parent_with_children_in_one_atomic_delta(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base"
            snapshot = root / "snapshot"
            base.mkdir(); snapshot.mkdir()
            remote_items = {}
            for table, filename in MODULE.TABLE_FILES.items():
                parent = {"id": f"{table}-parent", "value": "base"}
                desired = [parent]
                if table == "maintainer_scope_skills":
                    desired = [
                        {"id": "scope-child-a", "value": "reviewed"},
                        {"id": "scope-child-b", "value": "reviewed"},
                    ]
                MODULE.write_jsonl(base / filename, [parent])
                MODULE.write_jsonl(snapshot / filename, desired)
                remote_items[table] = [{
                    "key": parent["id"], "row": MODULE.envelope(parent),
                    "row_version": 4, "deleted": False,
                }]

            transactions = []
            def query(_client, _repo, table, _revision):
                return remote_items[table]
            def apply(_client, _repo, _revision, tables, *_args):
                transactions.append(tables)
                return "b" * 40

            with mock.patch.object(MODULE, "query_all", side_effect=query), \
                    mock.patch.object(MODULE, "apply_transaction", side_effect=apply):
                MODULE.persist_snapshot(
                    object(), "repo", "a" * 40, base, snapshot, "run", "owner/repo"
                )
            self.assertEqual(len(transactions), 1)
            scope_delta = next(
                row for row in transactions[0] if row["path"] == "maintainer_scope_skills"
            )
            self.assertEqual(
                sorted(operation["op"] for operation in scope_delta["operations"]),
                ["delete", "insert", "insert"],
            )
            deletion = next(
                operation for operation in scope_delta["operations"] if operation["op"] == "delete"
            )
            self.assertEqual(deletion["expected_row_version"], 4)

    def test_exact_export_rebinds_catalog_summary_without_changing_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base"
            export = root / "export"
            base.mkdir(); export.mkdir()
            summary = {
                "schema": "agentlab.maintainer_skill_catalog_summary.v1",
                "catalogSha256": "stale",
                "repositoryCount": 1,
                "scopeSkillCount": 1,
                "repositories": [{
                    "repositoryId": "sample",
                    "revision": "a" * 40,
                    "treeOid": "b" * 40,
                    "strategy": "generic",
                    "trackedFileCount": 3,
                    "sourceFileCount": 2,
                    "codeLineCount": 10,
                    "testFileCount": 1,
                    "externalDependencyCount": 4,
                    "assignedFileCount": 3,
                    "unassignedFileCount": 0,
                    "scopeSkillCount": 1,
                    "sampleProjectRootCount": 0,
                }],
                "trackedFilesAssignedExactlyOnce": True,
                "automaticPromotion": False,
            }
            MODULE.write_json(base / "maintainer-skill-summary.json", summary)
            rows = [
                {
                    "id": "scope-a", "repositoryId": "sample",
                    "sourceRevision": "a" * 40, "sourceTreeOid": "b" * 40,
                    "strategy": "generic", "trackedFileCount": 1,
                    "sourceFileCount": 1, "codeLineCount": 4, "testFileCount": 0,
                },
                {
                    "id": "scope-b", "repositoryId": "sample",
                    "sourceRevision": "a" * 40, "sourceTreeOid": "b" * 40,
                    "strategy": "generic", "trackedFileCount": 2,
                    "sourceFileCount": 1, "codeLineCount": 6, "testFileCount": 1,
                },
            ]
            catalog = export / MODULE.TABLE_FILES["maintainer_scope_skills"]
            MODULE.write_jsonl(catalog, rows)

            MODULE.update_catalog_summary(export, base)

            refreshed = MODULE.load(export / "maintainer-skill-summary.json")
            self.assertEqual(refreshed["catalogSha256"], MODULE.file_sha256(catalog))
            self.assertEqual(refreshed["scopeSkillCount"], 2)
            self.assertEqual(refreshed["repositories"][0]["scopeSkillCount"], 2)
            self.assertEqual(refreshed["repositories"][0]["externalDependencyCount"], 4)

            rows[0]["trackedFileCount"] = 2
            MODULE.write_jsonl(catalog, rows)
            with self.assertRaisesRegex(RuntimeError, "trackedFileCount coverage"):
                MODULE.update_catalog_summary(export, base)

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

    def test_stage_records_one_atomic_round_for_multiple_scope_receipts(self):
        source = ROOT / "examples/maintainer-knowledge-gate/first-four"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assessment = root / "assessment.json"
            assessment.write_text(json.dumps({
                "roundIndex": 31,
                "nextRoundObjectives": ["continue exact evidence closure"],
            }) + "\n")
            result = root / "result.json"
            result.write_text(json.dumps({
                "decision": "review-proposed-knowledge",
                "after": {
                    "scopeSkillCount": 489, "programBoundCount": 36,
                    "semanticReadyCount": 31, "maintenanceReadyCount": 3,
                },
            }) + "\n")
            receipts = []
            for index in range(2):
                receipt = root / f"receipt-{index}.json"
                receipt.write_text(json.dumps({
                    "acceptedFactId": f"agent-analysis-batch-{index}",
                    "scopeSkillId": f"scope-{index}",
                    "sourceAssessmentSha256": "a" * 64,
                }) + "\n")
                receipts.append(receipt)
            output = root / "stage"
            MODULE.command_stage(type("Args", (), {
                "base": source,
                "candidate_program_facts": source / "program_facts.jsonl",
                "candidate_assessment": assessment,
                "result": result,
                "receipt": receipts,
                "run_id": "batch-42",
                "github_repository": "owner/repo",
                "producer_kind": "github-action",
                "producer_url": None,
                "producer_host": None,
                "output": output,
            }))
            latest = max(
                MODULE.load_jsonl(output / "maintainer_skill_refresh_rounds.jsonl"),
                key=lambda row: row["roundIndex"],
            )
            self.assertEqual(latest["changes"]["added"], [
                "semantic program fact agent-analysis-batch-0",
                "semantic program fact agent-analysis-batch-1",
            ])
            manifest = MODULE.load(output / "stage-manifest.json")
            self.assertEqual(manifest["proposalReceiptCount"], 2)
            self.assertEqual(manifest["acceptedFactIds"], [
                "agent-analysis-batch-0", "agent-analysis-batch-1",
            ])

    def test_focused_refresh_is_recorded_as_an_update_not_a_new_fact(self):
        source = ROOT / "examples/maintainer-knowledge-gate/first-four"
        with tempfile.TemporaryDirectory() as directory:
            assessment = Path(directory) / "assessment.json"
            assessment.write_text(json.dumps({
                "roundIndex": 16,
                "nextRoundObjectives": ["re-run candidate construction readiness"],
            }) + "\n")
            fact_id = "agent-analysis-uiability-backup-restore-state-recovery"
            row = MODULE.build_refresh_round(
                source,
                source / "program_facts.jsonl",
                assessment,
                {
                    "decision": "review-proposed-knowledge-refresh",
                    "after": {
                        "scopeSkillCount": 480, "programBoundCount": 24,
                        "semanticReadyCount": 17, "maintenanceReadyCount": 2,
                    },
                },
                {"acceptedFactId": fact_id, "changeKind": "updated"},
                "43",
                "owner/repo",
            )
            self.assertEqual(row["changes"]["added"], [])
            self.assertIn(f"semantic program fact {fact_id}", row["changes"]["updated"])
            self.assertEqual(row["decision"], "review-proposed-knowledge-refresh")

    def test_local_producer_has_host_without_fabricated_action_url(self):
        producer = MODULE.producer_record(
            "hwlinux-local", "owner/repo", "local-42", host="hwlinux",
        )
        self.assertEqual(producer, {
            "kind": "hwlinux-local",
            "repository": "owner/repo",
            "runId": "local-42",
            "host": "hwlinux",
        })

    def test_scope_rewrite_stage_binds_receipts_and_new_assessment(self):
        source = ROOT / "examples/maintainer-knowledge-gate/first-four"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scopes = MODULE.load_jsonl(source / "maintainer_scope_skills.jsonl")
            parent = scopes.pop(0)
            children = []
            for suffix in ("a", "b"):
                child = dict(parent)
                child["id"] = f"skill-scope-arbitrary-{suffix}"
                children.append(child)
            candidate_scopes = root / "candidate-scopes.jsonl"
            MODULE.write_jsonl(candidate_scopes, scopes + children)

            previous_path = MODULE.latest_assessment_path(source)
            previous = MODULE.load(previous_path)
            assessment = root / "assessment.json"
            assessment.write_text(json.dumps({
                "roundIndex": previous["roundIndex"] + 1,
                "parentAssessmentSha256": MODULE.file_sha256(previous_path),
                "decision": "continue",
                "totals": {
                    "scopeSkillCount": len(scopes) + len(children),
                    "structuralReadyCount": len(scopes) + len(children),
                    "programBoundCount": previous["totals"]["programBoundCount"],
                    "semanticReadyCount": previous["totals"]["semanticReadyCount"],
                    "maintenanceReadyCount": previous["totals"]["maintenanceReadyCount"],
                },
                "nextRoundObjectives": ["continue exact evidence closure"],
            }) + "\n")
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({
                "schema": "agentlab.maintainer_scope_catalog_rewrite_receipt.v1",
                "automaticAuthorityMutation": False,
                "parentScopeSkillId": parent["id"],
                "replacementScopeSkillIds": [child["id"] for child in children],
                "catalogScopeCountBefore": len(scopes) + 1,
                "catalogScopeCountAfter": len(scopes) + len(children),
                "replacedTrackedFileCount": parent["trackedFileCount"],
                "replacementTrackedFileCount": parent["trackedFileCount"],
                "replacedSourceFileCount": parent["sourceFileCount"],
                "replacementSourceFileCount": parent["sourceFileCount"],
                "complete": True,
                "nonOverlapping": True,
                "decision": "candidate-catalog-ready-for-authoritative-transaction",
            }) + "\n")
            output = root / "stage"
            MODULE.command_stage_scope_rewrite(type("Args", (), {
                "base": source,
                "candidate_scope_skills": candidate_scopes,
                "candidate_assessment": assessment,
                "rewrite_receipt": [receipt],
                "run_id": "rewrite-42",
                "github_repository": "owner/repo",
                "producer_kind": "github-action",
                "producer_url": None,
                "producer_host": None,
                "output": output,
            }))
            manifest = MODULE.load(output / "stage-manifest.json")
            self.assertEqual(manifest["scopeRewrite"]["removedScopeSkillIds"], [parent["id"]])
            self.assertEqual(
                manifest["scopeRewrite"]["addedScopeSkillIds"],
                sorted(child["id"] for child in children),
            )
            staged_rounds = MODULE.load_jsonl(output / "maintainer_skill_refresh_rounds.jsonl")
            latest = max(staged_rounds, key=lambda row: row["roundIndex"])
            self.assertIn(f"scope skill {parent['id']}", latest["changes"]["retired"])
            self.assertEqual(latest["coverage"]["scopeSkillCount"], len(scopes) + len(children))


if __name__ == "__main__":
    unittest.main()
