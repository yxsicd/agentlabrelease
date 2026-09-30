#!/usr/bin/env python3
"""Stage, persist, export, and mirror one Maintainer Skill flywheel cut.

The long-lived TableGit repository is authoritative.  Release JSONL files are
materialized only from one exact committed TableGit revision.  Rows use a
small typed envelope so that the immutable TableGit definition can carry
future versions of the business documents without silently dropping fields.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid


SKILL_VERSION = "2.3.0"
REVISION = re.compile(r"[0-9a-f]{40}")
TABLE_FILES = {
    "maintainer_skills": "maintainer_skills.jsonl",
    "maintainer_scope_skills": "maintainer_scope_skills.jsonl",
    "program_facts": "program_facts.jsonl",
    "maintainer_skill_refresh_rounds": "maintainer_skill_refresh_rounds.jsonl",
    "evaluation_cases": "evaluation_cases.jsonl",
}
DESCRIPTIONS = {
    "maintainer_skills": "Reusable process and repository Maintainer Skills.",
    "maintainer_scope_skills": "Exact-source, scope-level Maintainer Skills.",
    "program_facts": "Revision-bound semantic and program-analysis facts.",
    "maintainer_skill_refresh_rounds": "Multi-round Maintainer Skill refinement lineage.",
    "evaluation_cases": "Independently calibrated evaluation cases.",
}


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def value_sha256(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_uuid(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "agentlab://" + "/".join(parts)))


def load(path: Path):
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jsonl_bytes(rows))


def jsonl_bytes(rows: list[dict]) -> bytes:
    return b"".join(canonical(row) + b"\n" for row in sorted(rows, key=lambda item: item["id"]))


def jsonl_sha256(rows: list[dict]) -> str:
    return hashlib.sha256(jsonl_bytes(rows)).hexdigest()


def envelope(row: dict) -> dict:
    result = {
        "id": row["id"],
        "payload": row,
        "payloadSha256": value_sha256(row),
    }
    for field in ("repositoryId", "sourceRevision", "kind", "schema", "roundIndex"):
        if field in row and row[field] is not None:
            result[field] = row[field]
    return result


def table_definition(table: str) -> dict:
    return {
        "description": DESCRIPTIONS[table],
        "key_field": "id",
        "required_fields": ["id", "payload", "payloadSha256"],
        "fields": {
            "id": {"type": "string", "required": True, "role": "key"},
            "payload": {"type": "object", "required": True},
            "payloadSha256": {"type": "string", "required": True},
            "repositoryId": {"type": "string"},
            "sourceRevision": {"type": "string"},
            "kind": {"type": "string"},
            "schema": {"type": "string"},
            "roundIndex": {"type": "integer"},
        },
        "indexes": [
            {"name": "by_repository", "field": "repositoryId"},
            {"name": "by_kind", "field": "kind"},
            {"name": "by_round", "field": "roundIndex"},
        ],
        "object_indexes": [],
        "prewarm": False,
    }


def producer_record(kind: str, repository: str, run_id: str,
                    run_url: str | None = None,
                    host: str | None = None) -> dict:
    producer = {
        "kind": kind,
        "repository": repository,
        "runId": run_id,
    }
    if run_url:
        producer["runUrl"] = run_url
    elif kind == "github-action":
        producer["runUrl"] = f"https://github.com/{repository}/actions/runs/{run_id}"
    if host:
        producer["host"] = host
    return producer


def build_refresh_round(base: Path, candidate_facts: Path, assessment_path: Path,
                        result: dict, receipt: dict | list[dict], run_id: str,
                        repository: str, producer_kind: str = "github-action",
                        producer_url: str | None = None,
                        producer_host: str | None = None) -> dict:
    assessment = load(assessment_path)
    rounds_path = base / TABLE_FILES["maintainer_skill_refresh_rounds"]
    rounds = load_jsonl(rounds_path)
    previous = max(rounds, key=lambda row: row["roundIndex"])
    after = result["after"]
    receipts = receipt if isinstance(receipt, list) else [receipt]
    accepted = [row["acceptedFactId"] for row in receipts]
    return {
        "id": f"first-four-round-{previous['roundIndex'] + 1}-agent-{run_id}",
        "schema": "agentlab.maintainer_skill_refresh_round.v1",
        "roundIndex": previous["roundIndex"] + 1,
        "parentRoundSha256": value_sha256(previous),
        "automaticPromotion": False,
        "ownershipPlane": "target-operations",
        "decision": result["decision"],
        "changes": {
            "added": [
                f"semantic program fact {row['acceptedFactId']}"
                for row in receipts if row.get("changeKind", "added") == "added"
            ],
            "updated": [
                *[
                    f"semantic program fact {row['acceptedFactId']}"
                    for row in receipts if row.get("changeKind") == "updated"
                ],
                f"{after['programBoundCount']} scopes program-bound",
                f"{after['semanticReadyCount']} scopes semantic-ready",
            ],
            "retired": [],
        },
        "coverage": {
            "processSkillCount": len(load_jsonl(base / TABLE_FILES["maintainer_skills"])),
            "repositoryCount": len({row["repositoryId"] for row in load_jsonl(base / TABLE_FILES["maintainer_scope_skills"])}),
            "scopeSkillCount": after["scopeSkillCount"],
            "programBoundScopeCount": after["programBoundCount"],
            "semanticReadyScopeCount": after["semanticReadyCount"],
            "maintenanceReadyScopeCount": after["maintenanceReadyCount"],
            "trackedFileCount": previous["coverage"]["trackedFileCount"],
        },
        "focus": [
            f"consume {len(accepted)} exact hard-gate gaps with independently validated source-blob evidence",
            "persist accepted knowledge in long-lived TableGit",
            "export a reviewable Release snapshot from one committed revision",
        ],
        "residualGaps": assessment["nextRoundObjectives"],
        "tables": {
            "processSkillsSha256": jsonl_sha256(load_jsonl(base / TABLE_FILES["maintainer_skills"])),
            "scopeSkillsSha256": jsonl_sha256(load_jsonl(base / TABLE_FILES["maintainer_scope_skills"])),
            "programFactsSha256": jsonl_sha256(load_jsonl(candidate_facts)),
        },
        "producer": producer_record(
            producer_kind, repository, run_id, producer_url, producer_host,
        ),
        "assessment": {
            "path": f"assessments/round-{assessment['roundIndex']}-agent-{run_id}.json",
            "sha256": file_sha256(assessment_path),
        },
    }


def command_stage(args) -> None:
    args.output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        args.base / "maintainer-knowledge-cut.json",
        args.output / "maintainer-knowledge-cut.json",
    )
    assessments = args.output / "assessments"
    assessments.mkdir(exist_ok=True)
    base_assessments = args.base / "assessments"
    if base_assessments.is_dir():
        for source in base_assessments.glob("*.json"):
            shutil.copy2(source, assessments / source.name)
    receipt_paths = args.receipt if isinstance(args.receipt, list) else [args.receipt]
    receipts = [load(path) for path in receipt_paths]
    scope_ids = [row.get("scopeSkillId") for row in receipts]
    if len(receipts) > 1 and any(not scope_id for scope_id in scope_ids):
        raise ValueError("proposal batch receipts must identify every scope")
    identified_scope_ids = [scope_id for scope_id in scope_ids if scope_id]
    if len(set(identified_scope_ids)) != len(identified_scope_ids):
        raise ValueError("proposal batch contains duplicate scope receipts")
    assessment_hashes = [row.get("sourceAssessmentSha256") for row in receipts]
    if len(receipts) > 1 and any(not digest for digest in assessment_hashes):
        raise ValueError("proposal batch receipts must identify the source assessment")
    if any(digest != assessment_hashes[0] for digest in assessment_hashes):
        raise ValueError("proposal batch receipts do not share one source assessment")
    for table, filename in TABLE_FILES.items():
        source = args.base / filename
        target = args.output / filename
        if table == "program_facts":
            table_rows = load_jsonl(args.candidate_program_facts)
        elif table == "maintainer_skill_refresh_rounds":
            table_rows = load_jsonl(source)
            table_rows.append(build_refresh_round(
                args.base, args.candidate_program_facts, args.candidate_assessment,
                load(args.result), receipts, args.run_id, args.github_repository,
                getattr(args, "producer_kind", "github-action"),
                getattr(args, "producer_url", None),
                getattr(args, "producer_host", None),
            ))
        else:
            table_rows = load_jsonl(source)
        write_jsonl(target, table_rows)
    assessment = load(args.candidate_assessment)
    assessment_name = f"round-{assessment['roundIndex']}-agent-{args.run_id}.json"
    assessment_path = Path("assessments") / assessment_name
    shutil.copy2(args.candidate_assessment, args.output / assessment_path)
    write_json(args.output / "stage-manifest.json", {
        "schema": "agentlab.maintainer_skill_tablegit_stage.v1",
        "automaticPromotion": False,
        "runId": args.run_id,
        "proposalReceiptCount": len(receipts),
        "acceptedFactIds": sorted(row["acceptedFactId"] for row in receipts),
        "assessment": str(assessment_path),
        "tables": {
            table: {"path": filename, "sha256": file_sha256(args.output / filename)}
            for table, filename in TABLE_FILES.items()
        },
    })


def latest_assessment_path(base: Path) -> Path:
    paths = list((base / "assessments").glob("*.json"))
    if not paths:
        raise ValueError("knowledge cut has no assessment")
    return max(paths, key=lambda path: load(path)["roundIndex"])


def command_stage_scope_rewrite(args) -> None:
    base_scopes = load_jsonl(args.base / TABLE_FILES["maintainer_scope_skills"])
    candidate_scopes = load_jsonl(args.candidate_scope_skills)
    base_by_id = {row["id"]: row for row in base_scopes}
    candidate_by_id = {row["id"]: row for row in candidate_scopes}
    if len(base_by_id) != len(base_scopes) or len(candidate_by_id) != len(candidate_scopes):
        raise ValueError("scope catalog contains duplicate ids")
    removed = sorted(set(base_by_id) - set(candidate_by_id))
    added = sorted(set(candidate_by_id) - set(base_by_id))
    if not removed or not added:
        raise ValueError("scope rewrite must replace parents with reviewed responsibilities")
    changed = [
        key for key in sorted(set(base_by_id) & set(candidate_by_id))
        if value_sha256(base_by_id[key]) != value_sha256(candidate_by_id[key])
    ]
    if changed:
        raise ValueError(f"scope rewrite changes retained rows: {changed}")

    receipts = [load(path) for path in args.rewrite_receipt]
    receipt_parents = sorted(row["parentScopeSkillId"] for row in receipts)
    receipt_children = sorted(
        child for row in receipts for child in row["replacementScopeSkillIds"]
    )
    if receipt_parents != removed or receipt_children != added:
        raise ValueError("scope rewrite differs from reviewed replacement receipts")
    if any(
        row.get("schema") != "agentlab.maintainer_scope_catalog_rewrite_receipt.v1"
        or row.get("automaticAuthorityMutation") is not False
        or row.get("complete") is not True
        or row.get("nonOverlapping") is not True
        or row.get("decision") != "candidate-catalog-ready-for-authoritative-transaction"
        or row.get("replacedTrackedFileCount") != row.get("replacementTrackedFileCount")
        or row.get("replacedSourceFileCount") != row.get("replacementSourceFileCount")
        for row in receipts
    ):
        raise ValueError("scope rewrite receipt is not complete and parity preserving")
    expected_count = len(base_scopes)
    for row in receipts:
        if row.get("catalogScopeCountBefore") != expected_count:
            raise ValueError("scope rewrite receipt chain does not start at the retained catalog")
        expected_count = row.get("catalogScopeCountAfter")
    if expected_count != len(candidate_scopes):
        raise ValueError("scope rewrite receipt chain does not end at the candidate catalog")

    assessment = load(args.candidate_assessment)
    previous_assessment_path = latest_assessment_path(args.base)
    previous_assessment = load(previous_assessment_path)
    if assessment.get("parentAssessmentSha256") != file_sha256(previous_assessment_path):
        raise ValueError("candidate assessment parent differs from latest retained assessment")
    if assessment.get("roundIndex") != previous_assessment["roundIndex"] + 1:
        raise ValueError("candidate assessment round is not the next round")
    if assessment.get("totals", {}).get("scopeSkillCount") != len(candidate_scopes):
        raise ValueError("candidate assessment scope total differs from rewritten catalog")
    totals = assessment["totals"]
    previous_totals = previous_assessment["totals"]
    if totals.get("structuralReadyCount") != len(candidate_scopes):
        raise ValueError("candidate assessment contains structurally invalid replacement scopes")
    for field in ("programBoundCount", "semanticReadyCount", "maintenanceReadyCount"):
        if totals.get(field, -1) < previous_totals.get(field, 0):
            raise ValueError(f"candidate assessment regresses {field}")

    args.output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        args.base / "maintainer-knowledge-cut.json",
        args.output / "maintainer-knowledge-cut.json",
    )
    assessments = args.output / "assessments"
    assessments.mkdir(exist_ok=True)
    for source in (args.base / "assessments").glob("*.json"):
        shutil.copy2(source, assessments / source.name)
    assessment_name = f"round-{assessment['roundIndex']}-scope-rewrite-{args.run_id}.json"
    shutil.copy2(args.candidate_assessment, assessments / assessment_name)

    for table, filename in TABLE_FILES.items():
        if table == "maintainer_scope_skills":
            rows = candidate_scopes
        elif table == "maintainer_skill_refresh_rounds":
            rows = load_jsonl(args.base / filename)
            previous = max(rows, key=lambda row: row["roundIndex"])
            rows.append({
                "id": f"first-four-round-{previous['roundIndex'] + 1}-scope-rewrite-{args.run_id}",
                "schema": "agentlab.maintainer_skill_refresh_round.v1",
                "roundIndex": previous["roundIndex"] + 1,
                "parentRoundSha256": value_sha256(previous),
                "automaticPromotion": False,
                "ownershipPlane": "target-operations",
                "decision": assessment["decision"],
                "changes": {
                    "added": [f"scope skill {key}" for key in added],
                    "updated": [
                        f"{totals['programBoundCount']} scopes program-bound",
                        f"{totals['semanticReadyCount']} scopes semantic-ready",
                        "independent assessment rebound to the reviewed scope catalog",
                    ],
                    "retired": [f"scope skill {key}" for key in removed],
                },
                "coverage": {
                    "processSkillCount": len(load_jsonl(args.base / TABLE_FILES["maintainer_skills"])),
                    "repositoryCount": len({row["repositoryId"] for row in candidate_scopes}),
                    "scopeSkillCount": totals["scopeSkillCount"],
                    "programBoundScopeCount": totals["programBoundCount"],
                    "semanticReadyScopeCount": totals["semanticReadyCount"],
                    "maintenanceReadyScopeCount": totals["maintenanceReadyCount"],
                    "trackedFileCount": previous["coverage"]["trackedFileCount"],
                },
                "focus": [
                    "atomically replace reviewed aggregate scopes with exact composite responsibilities",
                    "rebind independent maturity assessment to the rewritten catalog",
                    "export one exact committed TableGit revision",
                ],
                "residualGaps": assessment["nextRoundObjectives"],
                "tables": {
                    "processSkillsSha256": jsonl_sha256(load_jsonl(args.base / TABLE_FILES["maintainer_skills"])),
                    "scopeSkillsSha256": jsonl_sha256(candidate_scopes),
                    "programFactsSha256": jsonl_sha256(load_jsonl(args.base / TABLE_FILES["program_facts"])),
                },
                "producer": producer_record(
                    args.producer_kind, args.github_repository, args.run_id,
                    args.producer_url, args.producer_host,
                ),
                "assessment": {
                    "path": f"assessments/{assessment_name}",
                    "sha256": file_sha256(args.candidate_assessment),
                },
            })
        else:
            rows = load_jsonl(args.base / filename)
        write_jsonl(args.output / filename, rows)
    write_json(args.output / "stage-manifest.json", {
        "schema": "agentlab.maintainer_skill_tablegit_stage.v1",
        "automaticPromotion": False,
        "runId": args.run_id,
        "assessment": f"assessments/{assessment_name}",
        "scopeRewrite": {
            "removedScopeSkillIds": removed,
            "addedScopeSkillIds": added,
            "receipts": [
                {"path": str(path), "sha256": file_sha256(path)}
                for path in args.rewrite_receipt
            ],
        },
        "tables": {
            table: {"path": filename, "sha256": file_sha256(args.output / filename)}
            for table, filename in TABLE_FILES.items()
        },
    })


class Inspector:
    def __init__(self, endpoint: str, person_id: str):
        self.endpoint = endpoint
        self.person_id = person_id
        self.command = [
            "npx", "--yes", "--package", "node@22.20.0",
            "--package", "@modelcontextprotocol/inspector@2.6.0",
            "mcp-inspector", "--cli", endpoint, "--transport", "http", "--format", "json",
        ]

    def call(self, runner: str, skill: str, operation: str, arguments: dict,
             allow_error: bool = False) -> dict:
        payload = {
            "skill_id": skill,
            "skill_version": SKILL_VERSION,
            "operation": operation,
            "caller_person_id": self.person_id,
            "arguments": arguments,
        }
        proc = subprocess.run(
            self.command + ["--method", "tools/call", "--tool-name", runner,
                            "--tool-args-json", canonical(payload).decode()],
            text=True, capture_output=True,
        )
        try:
            outer = json.loads(proc.stdout) if proc.stdout.strip() else None
        except json.JSONDecodeError:
            outer = None
        # Inspector intentionally exits non-zero when an MCP tool returns
        # isError=true. The JSON envelope is still authoritative and, for
        # probes such as a not-yet-created table, is expected control flow.
        if outer is None and proc.returncode:
            raise RuntimeError(f"MCP inspector failed for {operation}: {proc.stderr.strip()}")
        if outer is None:
            raise RuntimeError(f"MCP inspector returned no JSON for {operation}")
        structured = outer.get("result", {}).get("structuredContent", {})
        if structured.get("outcome") == "error" or outer.get("result", {}).get("isError"):
            if allow_error:
                return structured
            error = structured.get("error", {})
            raise McpError(operation, error)
        if structured.get("outcome") != "executed":
            raise RuntimeError(f"MCP {operation} returned an unexpected envelope")
        return structured["result"]


class McpError(RuntimeError):
    def __init__(self, operation: str, error: dict):
        self.operation = operation
        self.error = error
        super().__init__(f"MCP {operation} failed: {error.get('code')}: {error.get('message')}")


def is_revision_conflict(error: McpError) -> bool:
    text = f"{error.error.get('code', '')} {error.error.get('message', '')}".lower()
    return any(term in text for term in ("stale_revision", "stale revision", "revision conflict", "expected revision"))


def is_missing_table(response: dict, table: str) -> bool:
    error = response.get("error", {})
    return error.get("code") == "validation" and f"table {table} does not exist" in error.get("message", "")


def operation_chunks(table: str, rows: list[dict], run_id: str,
                     max_bytes: int = 70_000,
                     row_versions: dict[str, int] | None = None) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    current: list[dict] = []
    size = 0
    row_versions = row_versions or {}
    for row in rows:
        wrapped = envelope(row)
        if row["id"] in row_versions:
            version = row_versions[row["id"]]
            operation = {
                "op": "upsert",
                "operation_id": stable_uuid(
                    run_id, table, row["id"], f"upsert-{version}"
                ),
                "key": row["id"],
                "expected_row_version": version,
                "row": wrapped,
            }
        else:
            operation = {
                "op": "insert",
                "operation_id": stable_uuid(run_id, table, row["id"], "insert"),
                "key": row["id"],
                "row": wrapped,
            }
        operation_size = len(canonical(operation))
        if operation_size > max_bytes:
            raise ValueError(f"one {table} row exceeds the bounded MCP transaction size")
        if current and size + operation_size > max_bytes:
            chunks.append(current)
            current, size = [], 0
        current.append(operation)
        size += operation_size
    if current:
        chunks.append(current)
    return chunks


def deletion_operations(table: str, keys: list[str], run_id: str,
                        row_versions: dict[str, int]) -> list[dict]:
    operations = []
    for key in keys:
        version = row_versions.get(key)
        if not isinstance(version, int) or version < 1:
            raise ValueError(f"cannot delete {table} row without an exact row version: {key}")
        operations.append({
            "op": "delete",
            "operation_id": stable_uuid(run_id, table, key, f"delete-{version}"),
            "key": key,
            "expected_row_version": version,
        })
    return operations


def query_all(client: Inspector, repo: str, table: str, revision: str) -> list[dict]:
    result = client.call("skill_run_read", "table.query", "table_query", {
        "repo": repo,
        "path": table,
        "view": {"kind": "committed", "revision": revision},
        "order_by": [{"field": "id", "direction": "asc"}],
        "limit": 1000,
        "offset": 0,
    })
    if result["truncated"] or result["returned_count"] != result["row_count"]:
        raise RuntimeError(f"{table} cannot be exported in one bounded exact-revision query")
    if result["revision"] != revision:
        raise RuntimeError(f"{table} query escaped the requested exact revision")
    return result["rows"]


def query_tables(client: Inspector, repo: str, revision: str) -> dict[str, list[dict]]:
    """Read independent tables concurrently while retaining one revision fence."""
    with ThreadPoolExecutor(max_workers=len(TABLE_FILES)) as executor:
        futures = {
            table: executor.submit(query_all, client, repo, table, revision)
            for table in TABLE_FILES
        }
        return {table: futures[table].result() for table in TABLE_FILES}


def unwrap_rows(table: str, rows: list[dict]) -> list[dict]:
    result = []
    for item in rows:
        if item.get("deleted"):
            continue
        row = item["row"]
        payload = row.get("payload")
        if not isinstance(payload, dict) or payload.get("id") != item.get("key"):
            raise RuntimeError(f"{table} row {item.get('key')} has an invalid envelope")
        if row.get("payloadSha256") != value_sha256(payload):
            raise RuntimeError(f"{table} row {item.get('key')} payload digest differs")
        result.append(payload)
    return result


def current_revision(client: Inspector, repo: str, anchor: str) -> str:
    status = client.call("skill_run_read", "table.query", "table_status", {
        "repo": repo, "path": anchor,
    })
    revision = status.get("revision")
    if not isinstance(revision, str) or not REVISION.fullmatch(revision):
        raise RuntimeError("anchor table did not return a committed repository revision")
    if status.get("dirty"):
        raise RuntimeError("TableGit repository is dirty")
    return revision


def create_missing_tables(client: Inspector, repo: str, revision: str) -> str:
    for table in TABLE_FILES:
        status = client.call("skill_run_read", "table.query", "table_status", {
            "repo": repo, "path": table,
            "view": {"kind": "committed", "revision": revision},
        }, allow_error=True)
        if status.get("outcome") != "error":
            continue
        if not is_missing_table(status, table):
            raise RuntimeError(f"cannot inspect {table}: {status.get('error')}")
        for attempt in range(5):
            try:
                created = client.call("skill_run_write", "table.author", "worktree_table_create", {
                    "repo": repo,
                    "path": table,
                    "expected_revision": revision,
                    "definition": table_definition(table),
                    "topic_id": "main",
                    "message": f"Initialize AgentLab {table} authority",
                })
                revision = created["revision"]
                break
            except McpError as error:
                if attempt == 4 or not is_revision_conflict(error):
                    raise
                revision = current_revision(client, repo, "capability_profiles")
    return revision


def apply_transaction(client: Inspector, repo: str, revision: str, tables: list[dict],
                      run_id: str, github_repository: str, label: str,
                      producer_kind: str = "github-action",
                      producer_url: str | None = None,
                      producer_host: str | None = None) -> str:
    chunk_digest = hashlib.sha256(canonical(tables)).hexdigest()
    transaction_id = stable_uuid(run_id, label, chunk_digest, "tablegit-v1")
    for attempt in range(5):
        try:
            written = client.call("skill_run_write", "table.author", "worktree_table_batch_transaction", {
                "repo": repo,
                "expected_revision": revision,
                "transaction_id": transaction_id,
                "idempotency_key": transaction_id,
                "actor": producer_record(
                    producer_kind, github_repository, run_id,
                    producer_url, producer_host,
                ),
                "tables": tables,
                "topic_id": "main",
                "message": f"Persist Maintainer Skill flywheel {run_id} {label}",
            })
            break
        except McpError as error:
            if attempt == 4 or not is_revision_conflict(error):
                raise
            revision = current_revision(client, repo, "capability_profiles")
    if written.get("conflicts"):
        raise RuntimeError(f"{label} transaction conflicted: {written['conflicts']}")
    return written["revision"]


def persist_snapshot(client: Inspector, repo: str, revision: str, base: Path,
                     snapshot: Path, run_id: str, github_repository: str,
                     producer_kind: str = "github-action",
                     producer_url: str | None = None,
                     producer_host: str | None = None) -> str:
    remote_by_table = {}
    remote_versions_by_table = {}
    base_by_table = {}
    desired_by_table = {}
    remote_items_by_table = query_tables(client, repo, revision)
    for table, filename in TABLE_FILES.items():
        base_rows = load_jsonl(base / filename)
        desired = load_jsonl(snapshot / filename)
        remote_items = remote_items_by_table[table]
        remote = {row["id"]: row for row in unwrap_rows(table, remote_items)}
        remote_versions = {
            item["key"]: item.get("row_version")
            for item in remote_items if not item.get("deleted")
        }
        if any(not isinstance(value, int) or value < 1 for value in remote_versions.values()):
            raise RuntimeError(f"{table} remote authority omitted a valid row version")
        base_by_id = {row["id"]: row for row in base_rows}
        desired_by_id = {row["id"]: row for row in desired}
        if len(base_by_id) != len(base_rows):
            raise RuntimeError(f"{table} Release base contains duplicate ids")
        if len(desired_by_id) != len(desired):
            raise RuntimeError(f"{table} snapshot contains duplicate ids")
        for key, row in remote.items():
            if key not in desired_by_id:
                if key not in base_by_id or value_sha256(row) != value_sha256(base_by_id[key]):
                    raise RuntimeError(f"{table} remote row {key} cannot be safely retired")
                continue
            remote_digest = value_sha256(row)
            desired_digest = value_sha256(desired_by_id[key])
            if remote_digest == desired_digest:
                continue
            if key not in base_by_id or remote_digest != value_sha256(base_by_id[key]):
                raise RuntimeError(f"{table} remote row {key} conflicts with the Release snapshot")
        remote_by_table[table] = remote
        remote_versions_by_table[table] = remote_versions
        base_by_table[table] = base_by_id
        desired_by_table[table] = desired_by_id

    # Bootstrap/recover the checked-in base first. These rows are stable across
    # re-runs even when the Agent proposes a different candidate. Large tables
    # are bounded into resumable, content-addressed transactions.
    for table, filename in TABLE_FILES.items():
        base_rows = base_by_table[table]
        missing = [base_rows[key] for key in sorted(set(base_rows) - set(remote_by_table[table]))]
        for index, operations in enumerate(operation_chunks(table, missing, "release-base"), start=1):
            revision = apply_transaction(
                client, repo, revision, [{"path": table, "operations": operations}],
                run_id, github_repository, f"{table} base part {index}",
                producer_kind, producer_url, producer_host,
            )
            for operation in operations:
                remote_by_table[table][operation["key"]] = operation["row"]["payload"]
                remote_versions_by_table[table][operation["key"]] = 1

    # New candidate rows and fenced updates to existing facts share one small
    # atomic batch. This prevents a crash from publishing a fact without its
    # flywheel round and refuses to overwrite a concurrently changed row.
    delta_tables = []
    for table, filename in TABLE_FILES.items():
        delta = [
            desired_by_table[table][key]
            for key in sorted(desired_by_table[table])
            if key not in remote_by_table[table]
            or value_sha256(desired_by_table[table][key])
            != value_sha256(remote_by_table[table][key])
        ]
        operations = [
            operation
            for chunk in operation_chunks(
                table, delta, run_id,
                row_versions=remote_versions_by_table[table],
            )
            for operation in chunk
        ]
        operations.extend(deletion_operations(
            table,
            sorted(set(remote_by_table[table]) - set(desired_by_table[table])),
            run_id,
            remote_versions_by_table[table],
        ))
        if operations:
            delta_tables.append({"path": table, "operations": operations})
    if len(canonical(delta_tables)) > 70_000:
        raise RuntimeError("candidate delta exceeds the atomic TableGit transaction bound")
    if delta_tables:
        revision = apply_transaction(
            client, repo, revision, delta_tables, run_id, github_repository, "candidate delta",
            producer_kind, producer_url, producer_host,
        )
    return revision


def update_cut(export: Path, base: Path, revision: str, repo: str,
               run_id: str, github_repository: str,
               producer_kind: str = "github-action",
               producer_url: str | None = None,
               producer_host: str | None = None) -> None:
    cut = load(base / "maintainer-knowledge-cut.json")
    for table, filename in TABLE_FILES.items():
        entry_name = {
            "maintainer_skills": "maintainerSkills",
            "maintainer_scope_skills": "maintainerScopeSkills",
            "program_facts": "programFacts",
            "maintainer_skill_refresh_rounds": "maintainerSkillRefreshRounds",
            "evaluation_cases": "evaluationCases",
        }[table]
        cut["tables"][entry_name] = {"path": filename, "sha256": file_sha256(export / filename)}
    cut["tableGitAuthority"] = {
        "repo": repo,
        "revision": revision,
        "exportedBy": producer_record(
            producer_kind, github_repository, run_id,
            producer_url, producer_host,
        ),
    }
    cut["automaticPromotion"] = False
    write_json(export / "maintainer-knowledge-cut.json", cut)


def update_catalog_summary(export: Path, base: Path) -> None:
    """Rebind the derived catalog summary to the exact TableGit export."""
    summary_path = base / "maintainer-skill-summary.json"
    if not summary_path.is_file():
        return
    summary = load(summary_path)
    rows = load_jsonl(export / TABLE_FILES["maintainer_scope_skills"])
    by_repository: dict[str, list[dict]] = {}
    for row in rows:
        by_repository.setdefault(row["repositoryId"], []).append(row)

    retained = {row["repositoryId"]: row for row in summary["repositories"]}
    if set(retained) != set(by_repository):
        raise RuntimeError("exact scope export changes the catalog repository set")
    for repository_id, repository_rows in by_repository.items():
        repository = retained[repository_id]
        stable_fields = {
            "revision": "sourceRevision",
            "treeOid": "sourceTreeOid",
            "strategy": "strategy",
        }
        for summary_field, row_field in stable_fields.items():
            values = {row[row_field] for row in repository_rows}
            if values != {repository[summary_field]}:
                raise RuntimeError(
                    f"exact scope export changes {repository_id} {summary_field}"
                )
        aggregate_fields = {
            "trackedFileCount": "trackedFileCount",
            "sourceFileCount": "sourceFileCount",
            "codeLineCount": "codeLineCount",
            "testFileCount": "testFileCount",
        }
        for summary_field, row_field in aggregate_fields.items():
            total = sum(row[row_field] for row in repository_rows)
            if total != repository[summary_field]:
                raise RuntimeError(
                    f"exact scope export changes {repository_id} {summary_field} coverage"
                )
        repository["assignedFileCount"] = repository["trackedFileCount"]
        repository["unassignedFileCount"] = 0
        repository["scopeSkillCount"] = len(repository_rows)

    summary["catalogSha256"] = file_sha256(
        export / TABLE_FILES["maintainer_scope_skills"]
    )
    summary["scopeSkillCount"] = len(rows)
    summary["trackedFilesAssignedExactlyOnce"] = True
    summary["automaticPromotion"] = False
    write_json(export / "maintainer-skill-summary.json", summary)


def operation_evidence_files(snapshot: Path) -> dict[str, bytes]:
    """Validate and retain portable sidecars before any authority mutation."""
    manifest_path = snapshot / "stage-manifest.json"
    if not manifest_path.is_file():
        return {}
    manifest = load(manifest_path)
    if manifest.get("stageKind") != "verified-operation":
        return {}

    def read(relative: str, expected: str | None = None) -> bytes:
        path = Path(relative)
        if path.is_absolute() or not path.parts or any(part in (".", "..") for part in path.parts):
            raise RuntimeError("operation evidence must be contained and relative")
        current = snapshot
        for part in path.parts:
            current = current / part
            if current.is_symlink():
                raise RuntimeError("operation evidence cannot traverse a symlink")
        if not current.is_file() or current.stat().st_size > 2 * 1024 * 1024:
            raise RuntimeError("operation evidence missing or exceeds budget")
        data = current.read_bytes()
        if expected and hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError("operation evidence digest mismatch")
        return data

    evidence = manifest.get("operationEvidence", {})
    for table, filename in TABLE_FILES.items():
        entry = manifest.get("tables", {}).get(table, {})
        if entry.get("path") != filename or not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", "")):
            raise RuntimeError("operation stage table manifest invalid")
        read(filename, entry["sha256"])
    receipts = evidence.get("receipts", [])
    if evidence.get("receiptRoot") != "operation-evidence" or evidence.get("coverage") != "accepted-operation-facts-only":
        raise RuntimeError("operation stage has no portable evidence contract")
    if not 1 <= len(receipts) <= 4 or sorted(row["factId"] for row in receipts) != sorted(manifest["acceptedFactIds"]):
        raise RuntimeError("operation receipt coverage differs from accepted facts")
    files = {"operation-stage-manifest.json": read("stage-manifest.json"),
             "operation-baseline.json": read("operation-baseline.json"),
             "operation-result.json": read("operation-result.json")}
    for receipt in receipts:
        if not receipt["path"].startswith("operation-evidence/") or not re.fullmatch(r"[0-9a-f]{64}", receipt["sha256"]):
            raise RuntimeError("operation receipt reference invalid")
        files[receipt["path"]] = read(receipt["path"], receipt["sha256"])
    facts = {row["id"]: row for row in load_jsonl(snapshot / TABLE_FILES["program_facts"])}
    for receipt in receipts:
        reference = facts.get(receipt["factId"], {}).get("operationEvidence", {})
        if receipt["path"] != "operation-evidence/" + reference.get("path", "") or receipt["sha256"] != reference.get("sha256"):
            raise RuntimeError("portable receipt differs from accepted fact")
    return files


def command_sync(args) -> None:
    portable_evidence = operation_evidence_files(args.snapshot)
    client = Inspector(args.endpoint, args.person_id)
    revision = current_revision(client, args.repo, args.anchor_table)
    revision = create_missing_tables(client, args.repo, revision)
    revision = persist_snapshot(
        client, args.repo, revision, args.base, args.snapshot, args.run_id, args.github_repository,
        args.producer_kind, args.producer_url, args.producer_host,
    )
    exact_items = query_tables(client, args.repo, revision)
    exact_rows = {
        table: unwrap_rows(table, exact_items[table]) for table in TABLE_FILES
    }

    args.export.mkdir(parents=True, exist_ok=True)
    for table, filename in TABLE_FILES.items():
        write_jsonl(args.export / filename, exact_rows[table])
        expected = load_jsonl(args.snapshot / filename)
        if [(row["id"], value_sha256(row)) for row in exact_rows[table]] != [
            (row["id"], value_sha256(row)) for row in sorted(expected, key=lambda item: item["id"])
        ]:
            raise RuntimeError(f"{table} exact-revision export differs from the staged cut")
    update_catalog_summary(args.export, args.base)

    manifest_path = args.snapshot / "stage-manifest.json"
    if manifest_path.is_file():
        assessment = args.snapshot / load(manifest_path)["assessment"]
    elif args.assessment:
        assessment = args.assessment
    else:
        raise RuntimeError("exact export requires a staged or explicitly selected assessment")
    assessments = args.export / "assessments"
    assessments.mkdir(exist_ok=True)
    snapshot_assessments = args.snapshot / "assessments"
    if snapshot_assessments.is_dir():
        for source in snapshot_assessments.glob("*.json"):
            target = assessments / source.name
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
    else:
        assessment_target = assessments / assessment.name
        if assessment.resolve() != assessment_target.resolve():
            shutil.copy2(assessment, assessment_target)
    update_cut(
        args.export, args.base, revision, args.repo, args.run_id,
        args.github_repository, args.producer_kind, args.producer_url,
        args.producer_host,
    )
    for relative, data in portable_evidence.items():
        target = args.export / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    mirror = {"requested": False, "verified": False}
    if args.replicate:
        replicated = client.call("skill_run_publish", "replication", "repo_remote_replicate", {
            "repo": args.repo, "alias": args.remote, "expected_revision": revision,
        })
        if not replicated.get("verified") or replicated.get("conflicts"):
            raise RuntimeError(f"remote replication was not verified: {replicated}")
        remote = client.call("skill_run_publish", "replication", "repo_remote_status", {
            "repo": args.repo, "alias": args.remote, "fetch": True,
        })
        if remote.get("remote_revision") != remote.get("local_revision") or remote.get("behind") not in (0, None):
            raise RuntimeError(f"remote mirror did not converge: {remote}")
        mirror = {
            "requested": True,
            "verified": True,
            "alias": args.remote,
            "revision": remote["remote_revision"],
            "outcome": replicated["outcome"],
        }
    write_json(args.receipt, {
        "schema": "agentlab.maintainer_skill_tablegit_sync_receipt.v1",
        "repo": args.repo,
        "revision": revision,
        "authorityVerified": True,
        "mirror": mirror,
        "runId": args.run_id,
        "tables": {
            table: {"rowCount": len(exact_rows[table]), "sha256": file_sha256(args.export / filename)}
            for table, filename in TABLE_FILES.items()
        },
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage")
    stage.add_argument("--base", type=Path, required=True)
    stage.add_argument("--candidate-program-facts", type=Path, required=True)
    stage.add_argument("--candidate-assessment", type=Path, required=True)
    stage.add_argument("--result", type=Path, required=True)
    stage.add_argument("--receipt", type=Path, action="append", required=True)
    stage.add_argument("--run-id", required=True)
    stage.add_argument("--github-repository", required=True)
    stage.add_argument("--producer-kind", default="github-action")
    stage.add_argument("--producer-url")
    stage.add_argument("--producer-host")
    stage.add_argument("--output", type=Path, required=True)
    stage.set_defaults(handler=command_stage)

    rewrite = commands.add_parser("stage-scope-rewrite")
    rewrite.add_argument("--base", type=Path, required=True)
    rewrite.add_argument("--candidate-scope-skills", type=Path, required=True)
    rewrite.add_argument("--candidate-assessment", type=Path, required=True)
    rewrite.add_argument("--rewrite-receipt", type=Path, action="append", required=True)
    rewrite.add_argument("--run-id", required=True)
    rewrite.add_argument("--github-repository", required=True)
    rewrite.add_argument("--producer-kind", default="github-action")
    rewrite.add_argument("--producer-url")
    rewrite.add_argument("--producer-host")
    rewrite.add_argument("--output", type=Path, required=True)
    rewrite.set_defaults(handler=command_stage_scope_rewrite)

    sync = commands.add_parser("sync")
    sync.add_argument("--base", type=Path, required=True)
    sync.add_argument("--snapshot", type=Path, required=True)
    sync.add_argument("--export", type=Path, required=True)
    sync.add_argument(
        "--assessment", type=Path,
        help="explicit assessment for a recovery export when the snapshot has no stage manifest",
    )
    sync.add_argument("--receipt", type=Path, required=True)
    sync.add_argument("--endpoint", default=os.environ.get("AGENTLAB_TABLEGIT_MCP_URL"))
    sync.add_argument("--person-id", default=os.environ.get("AGENTLAB_TABLEGIT_PERSON_ID"))
    sync.add_argument("--repo", default="agentlabtablegit")
    sync.add_argument("--anchor-table", default="capability_profiles")
    sync.add_argument("--remote", default="origin")
    sync.add_argument(
        "--replicate", action="store_true",
        help="also use the separately authorized MCP publish lane to mirror the committed revision",
    )
    sync.add_argument("--run-id", required=True)
    sync.add_argument("--github-repository", required=True)
    sync.add_argument("--producer-kind", default="github-action")
    sync.add_argument("--producer-url")
    sync.add_argument("--producer-host")
    sync.set_defaults(handler=command_sync)
    args = parser.parse_args()
    if args.command == "sync" and (not args.endpoint or not args.person_id):
        parser.error("sync requires the TableGit MCP endpoint and Person id")
    args.handler(args)


if __name__ == "__main__":
    main()
