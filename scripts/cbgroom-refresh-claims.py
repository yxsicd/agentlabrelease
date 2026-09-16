#!/usr/bin/env python3
"""Reconcile current AgentLab research claims from committed structured decisions."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import uuid
import shutil
from typing import Any, Dict, List, Tuple
from pathlib import Path


def stable_uuid(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "agentlab://" + "/".join(parts)))


def inspector(url: str, tool: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    npx = shutil.which("npx") or "/opt/homebrew/bin/npx"
    if not Path(npx).exists():
        raise RuntimeError("npx is required for MCP Inspector transport")
    cmd = [
        npx, "--yes", "--package", "node@22.20.0", "--package", "@modelcontextprotocol/inspector@2.6.0",
        "mcp-inspector", "--cli", url, "--transport", "http", "--format", "json",
        "--method", "tools/call", "--tool-name", tool, "--tool-args-json", json.dumps(payload, separators=(",", ":")),
    ]
    env = os.environ.copy()
    env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "")
    outer = json.loads(subprocess.check_output(cmd, text=True, env=env))
    structured = outer["result"]["structuredContent"]
    if structured.get("outcome") != "executed":
        raise RuntimeError(structured)
    return structured["result"]


def repo_head(url: str, person: str) -> str:
    return inspector(url, "skill_run_read", {
        "skill_id": "repo.read", "skill_version": "2.2.0", "operation": "repo_status",
        "caller_person_id": person, "arguments": {"repo": "agentlabtablegit"},
    })["head"]


def query(url: str, person: str, path: str, revision: str, limit: int = 500) -> Dict[str, Any]:
    result = inspector(url, "skill_run_read", {
        "skill_id": "table.query", "skill_version": "2.2.0", "operation": "table_query",
        "caller_person_id": person,
        "arguments": {"repo": "agentlabtablegit", "path": path, "limit": limit,
                      "view": {"kind": "committed", "revision": revision}},
    })
    if result["revision"] != revision:
        raise RuntimeError("revision drift for %s" % path)
    return result


def target_claims(decisions: List[Dict[str, Any]], revision: str) -> Dict[str, Dict[str, Any]]:
    rows = [r.get("row", r) for r in decisions]
    def split(token: str) -> Tuple[List[str], List[str]]:
        support, contradiction = [], []
        for r in rows:
            if token not in r.get("id", ""):
                continue
            if str(r.get("decision", "")).startswith("accept-"):
                support.append(r["id"])
            else:
                contradiction.append(r["id"])
        return sorted(support), sorted(contradiction)

    compiler_support, compiler_contra = split("compiler-feedback")
    timeout_support, timeout_contra = split("timeout-feedback")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    compiler_status = "strongly-supported-current-scope" if len(compiler_support) >= 3 and not compiler_contra else "supported-with-counterevidence"
    timeout_status = "supported-but-variable" if len(timeout_support) > len(timeout_contra) and timeout_contra else "supported-current-scope" if timeout_support else "insufficient-evidence"
    return {
        "claim-compiler-feedback-focused-repair": {
            "statement": "当业务行为已经正确、只剩明确编译错误时，提供具体编译器证据是一种稳定的局部修复方法。",
            "status": compiler_status,
            "scope": {"taskFamily": "cache-durability", "model": "glm-5.3-flash", "precondition": "behavior-pass-build-fail", "intervention": "compiler-feedback-only"},
            "supportCount": len(compiler_support), "contradictionCount": len(compiler_contra),
            "supportRefs": compiler_support, "contradictionRefs": compiler_contra,
            "independenceSummary": {"status": "pending-explicit-classification", "note": "现有重复实验支持强，但 independenceClass 尚未结构化编码。"},
            "confidenceNote": "当前范围内 %d/%d 完整成功；结论仅适用于行为已经正确、问题明确定位到编译层的局部修复场景。" % (len(compiler_support), len(compiler_support) + len(compiler_contra)),
            "latestEvaluatedRevision": revision, "updatedAt": now,
            "metadata": {"family": "compiler-feedback"},
        },
        "claim-timeout-feedback-action-start": {
            "statement": "超时且未修改源码的反馈能够帮助 Agent 跨过一部分“迟迟不开始行动”的问题，但效果仍然不稳定。",
            "status": timeout_status,
            "scope": {"taskFamily": "cache-durability", "model": "glm-5.3-flash", "failureMode": "timeout-before-source-mutation", "interventionFamily": "timeout-feedback"},
            "supportCount": len(timeout_support), "contradictionCount": len(timeout_contra),
            "supportRefs": timeout_support, "contradictionRefs": timeout_contra,
            "independenceSummary": {"status": "pending-explicit-classification", "note": "当前累计 7/11 行为跨越，且存在 4 条 no-crossing；不同实验批次的独立性尚未统一编码。"},
            "confidenceNote": "证据支持“有明显帮助”，但不支持“已经稳定”；当前完整成功仅 2/11。",
            "latestEvaluatedRevision": revision, "updatedAt": now,
            "metadata": {"family": "timeout-feedback", "legacyCadenceMetadataIncomplete": True},
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcp-url", default=os.environ.get("AGENTLAB_TABLEGIT_MCP_URL"))
    ap.add_argument("--person-id", default=os.environ.get("AGENTLAB_TABLEGIT_PERSON_ID"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.mcp_url or not args.person_id:
        raise SystemExit("MCP URL and Person ID are required")

    for attempt in range(5):
        revision = repo_head(args.mcp_url, args.person_id)
        decisions = query(args.mcp_url, args.person_id, "decisions", revision)["rows"]
        claim_result = query(args.mcp_url, args.person_id, "research_claims", revision, 100)
        event_result = query(args.mcp_url, args.person_id, "claim_events", revision, 500)
        current = {r["key"]: r for r in claim_result["rows"]}
        events = [r.get("row", r) for r in event_result["rows"]]
        targets = target_claims(decisions, revision)
        claim_ops, event_ops = [], []
        summary = []
        for claim_id, target in targets.items():
            existing_wrap = current.get(claim_id)
            if not existing_wrap:
                continue
            old = existing_wrap["row"]
            compare_keys = ["statement", "status", "scope", "supportCount", "contradictionCount", "supportRefs", "contradictionRefs", "independenceSummary", "confidenceNote", "metadata"]
            changed = [k for k in compare_keys if old.get(k) != target.get(k)]
            if not changed:
                continue
            set_values = dict(target)
            set_values["firstSupportedRevision"] = old.get("firstSupportedRevision", revision)
            claim_ops.append({
                "op": "update", "operation_id": stable_uuid("claim-refresh", revision, claim_id),
                "key": claim_id, "expected_row_version": existing_wrap["row_version"], "set": set_values,
            })
            claim_events = [e for e in events if e.get("claimId") == claim_id]
            seq = max([int(e.get("sequence", 0)) for e in claim_events] or [0]) + 1
            support_added = sorted(set(target["supportRefs"]) - set(old.get("supportRefs", [])))
            contradiction_added = sorted(set(target["contradictionRefs"]) - set(old.get("contradictionRefs", [])))
            kind = "status-changed" if old.get("status") != target.get("status") else "evidence-updated"
            event_id = "%s-%06d" % (claim_id, seq)
            event_ops.append({
                "op": "insert", "operation_id": stable_uuid("claim-event", revision, event_id), "key": event_id,
                "row": {"id": event_id, "claimId": claim_id, "sequence": seq, "timestamp": target["updatedAt"],
                        "kind": kind, "fromStatus": old.get("status", "unknown"), "toStatus": target["status"],
                        "sourceRevision": revision, "supportAdded": support_added, "contradictionAdded": contradiction_added,
                        "summary": "新实验改变了该结论的结构化证据集合。" if kind == "evidence-updated" else "新实验导致该结论的状态发生变化。",
                        "metricsBefore": {"supportCount": old.get("supportCount", 0), "contradictionCount": old.get("contradictionCount", 0)},
                        "metricsAfter": {"supportCount": target["supportCount"], "contradictionCount": target["contradictionCount"]},
                        "metadata": {"changedFields": changed}},
            })
            summary.append({"claimId": claim_id, "changed": changed, "supportAdded": support_added, "contradictionAdded": contradiction_added})
        if not claim_ops:
            print(json.dumps({"ok": True, "outcome": "no-change", "revision": revision}, sort_keys=True))
            return
        if args.dry_run:
            print(json.dumps({"ok": True, "outcome": "dry-run", "revision": revision, "changes": summary}, ensure_ascii=False, sort_keys=True))
            return
        payload = {
            "skill_id": "table.author", "skill_version": "2.2.0", "operation": "worktree_table_batch_transaction",
            "caller_person_id": args.person_id,
            "arguments": {"repo": "agentlabtablegit", "topic_id": "main", "expected_revision": revision,
                          "transaction_id": stable_uuid("claim-refresh", revision), "idempotency_key": "claim-refresh-" + revision,
                          "actor": "agentlab-research-claims", "message": "agentlab: refresh research claims from decisions",
                          "tables": [{"path": "research_claims", "operations": claim_ops}, {"path": "claim_events", "operations": event_ops}]},
        }
        try:
            result = inspector(args.mcp_url, "skill_run_write", payload)
            print(json.dumps({"ok": True, "outcome": "updated", "revision": result["revision"], "changes": summary}, ensure_ascii=False, sort_keys=True))
            return
        except Exception:
            if attempt == 4:
                raise
    raise RuntimeError("claim refresh retries exhausted")

if __name__ == "__main__":
    main()
