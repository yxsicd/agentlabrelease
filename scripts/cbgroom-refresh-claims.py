#!/usr/bin/env python3
"""Reconcile current AgentLab research claims from committed structured decisions."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
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


def classify_evidence(claim_id: str, support_refs: List[str], contradiction_refs: List[str], checkpoints: List[Dict[str, Any]], environments: List[Dict[str, Any]], revision: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    checkpoint_rows = [r.get("row", r) for r in checkpoints]
    by_id = {r.get("id"): r for r in checkpoint_rows}
    environment_rows = [r.get("row", r) for r in environments]
    environment_by_run: Dict[str, List[Dict[str, Any]]] = {}
    for environment in environment_rows:
        metadata = environment.get("metadata") if isinstance(environment.get("metadata"), dict) else {}
        if metadata.get("claimIndependenceEligible") is False:
            continue
        environment_by_run.setdefault(str(environment.get("runId")), []).append(environment)
    for run_environments in environment_by_run.values():
        run_environments.sort(key=lambda environment: str(environment.get("id", "")))
    refs = [(r, "support") for r in support_refs] + [(r, "contradiction") for r in contradiction_refs]
    def run_id(ref: str) -> int:
        match = re.search(r"decision-(\d+)", ref)
        return int(match.group(1)) if match else 0
    refs.sort(key=lambda item: run_id(item[0]))
    seen_cuts, seen_sessions, seen_runners = set(), set(), set()
    unique_cuts, unique_sessions, unique_runners = set(), set(), set()
    classes, runner_classes, rows = [], [], []
    basis_map = {
        "anchor-checkpoint": "First structured evidence for this claim; establishes the reference lineage.",
        "independent-source-cut": "Source cut differs from every earlier evidence item for this claim.",
        "independent-checkpoint": "Source cut is shared, but native session/checkpoint lineage differs from earlier evidence.",
        "same-checkpoint-new-rollout": "Source cut and native session lineage match an earlier evidence item; this is a new rollout, not a new checkpoint.",
        "unknown-lineage": "Required checkpoint lineage fields are unavailable; independence is not inferred.",
    }
    for index, (ref, polarity) in enumerate(refs):
        rid = str(run_id(ref))
        checkpoint_id = "checkpoint-%s-turn-1" % rid
        checkpoint = by_id.get(checkpoint_id, {})
        source_cut = checkpoint.get("sourceCut")
        session = checkpoint.get("nativeSessionSha256")
        thread = checkpoint.get("nativeThreadId")
        run_environments = environment_by_run.get(rid, [])
        runner_identities: List[str] = []
        for environment in run_environments:
            runner_identity = str(environment.get("runnerIdentity") or "")
            if runner_identity and runner_identity not in runner_identities:
                runner_identities.append(runner_identity)
        if not checkpoint or not source_cut or not session:
            independence = "unknown-lineage"
        elif index == 0:
            independence = "anchor-checkpoint"
        elif source_cut not in seen_cuts:
            independence = "independent-source-cut"
        elif session not in seen_sessions:
            independence = "independent-checkpoint"
        else:
            independence = "same-checkpoint-new-rollout"
        if source_cut:
            seen_cuts.add(source_cut); unique_cuts.add(source_cut)
        if session:
            seen_sessions.add(session); unique_sessions.add(session)
        new_runner_identities = [identity for identity in runner_identities if identity not in seen_runners]
        if not runner_identities:
            runner_class = "unknown-not-encoded"
        elif not seen_runners and len(runner_identities) > 1:
            runner_class = "multiple-environments-on-evidence"
        elif not seen_runners:
            runner_class = "anchor-runner"
        elif new_runner_identities:
            runner_class = "independent-runner"
        else:
            runner_class = "same-runner"
        for runner_identity in runner_identities:
            seen_runners.add(runner_identity); unique_runners.add(runner_identity)
        classes.append(independence); runner_classes.append(runner_class)
        metadata = {"runId": rid}
        if runner_identities:
            metadata["runnerIdentities"] = runner_identities
            metadata["executionEnvironmentIds"] = [str(environment.get("id")) for environment in run_environments]
        if len(run_environments) == 1 and runner_identities:
            environment = run_environments[0]
            metadata.update({
                "runnerIdentity": runner_identities[0],
                "runnerName": environment.get("runnerName"),
                "runnerOs": environment.get("runnerOs"),
                "runnerArch": environment.get("runnerArch"),
            })
        rows.append({
            "id": "independence-%s-%s" % (claim_id, rid), "claimId": claim_id, "decisionRef": ref,
            "polarity": polarity, "checkpointId": checkpoint_id, "sourceCut": source_cut,
            "nativeThreadId": thread, "nativeSessionSha256": session, "independenceClass": independence,
            "lineageGroup": (source_cut or "unknown") + "|" + (session or "unknown"),
            "runnerIndependence": runner_class, "taskIndependence": "same-task-family-current-scope",
            "basis": basis_map[independence], "sourceRevision": revision, "metadata": metadata,
        })
    class_counts = {}
    for value in classes:
        class_counts[value] = class_counts.get(value, 0) + 1
    runner_class_counts = {}
    for value in runner_classes:
        runner_class_counts[value] = runner_class_counts.get(value, 0) + 1
    if not unique_runners:
        runner_status = "unknown-not-encoded"
    elif len(unique_runners) == 1:
        runner_status = "single-recorded-runner-environment"
    else:
        runner_status = "multiple-recorded-runner-environments"
    summary = {
        "status": "classified-from-checkpoint-lineage", "evidenceCount": len(refs),
        "uniqueSourceCuts": len(unique_cuts), "uniqueNativeSessions": len(unique_sessions),
        "classCounts": class_counts, "uniqueExecutionEnvironments": len(unique_runners),
        "runnerClassCounts": runner_class_counts, "runnerIndependence": runner_status,
        "taskIndependence": "same-task-family-current-scope",
        "note": "Code/session diversity is derived from checkpoint lineage. Runner diversity is counted from every explicit, claim-eligible execution_environments row linked to an evidence run; one evidence run may be independently reproduced in multiple environments.",
    }
    return summary, rows


def target_claims(decisions: List[Dict[str, Any]], checkpoints: List[Dict[str, Any]], environments: List[Dict[str, Any]], revision: str) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    rows = [r.get("row", r) for r in decisions]
    def split(token: str, require_full: bool = False) -> Tuple[List[str], List[str]]:
        support, contradiction = [], []
        for r in rows:
            if token not in r.get("id", ""):
                continue
            decision = str(r.get("decision", ""))
            accepted = decision == "accept-full-crossing" if require_full else decision.startswith("accept-")
            if accepted:
                support.append(r["id"])
            else:
                contradiction.append(r["id"])
        return sorted(support), sorted(contradiction)

    compiler_support, compiler_contra = split("compiler-feedback", require_full=True)
    timeout_support, timeout_contra = split("timeout-feedback")
    compiler_independence, compiler_rows = classify_evidence("claim-compiler-feedback-focused-repair", compiler_support, compiler_contra, checkpoints, environments, revision)
    timeout_independence, timeout_rows = classify_evidence("claim-timeout-feedback-action-start", timeout_support, timeout_contra, checkpoints, environments, revision)
    timeout_full_count = sum(1 for r in rows if "timeout-feedback" in r.get("id", "") and r.get("decision") == "accept-full-crossing")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    compiler_diverse = compiler_independence.get("uniqueSourceCuts", 0) >= 2 and compiler_independence.get("uniqueNativeSessions", 0) >= 3
    compiler_status = "strongly-supported-current-scope" if len(compiler_support) >= 3 and not compiler_contra and compiler_diverse else "supported-with-counterevidence" if compiler_support else "insufficient-evidence"
    timeout_status = "supported-but-variable" if len(timeout_support) > len(timeout_contra) and timeout_contra else "supported-current-scope" if timeout_support else "insufficient-evidence"
    claims = {
        "claim-compiler-feedback-focused-repair": {
            "statement": "当业务行为已经正确、只剩明确编译错误时，提供具体编译器证据是一种稳定的局部修复方法。",
            "status": compiler_status,
            "scope": {"taskFamily": "cache-durability", "model": "glm-5.3-flash", "precondition": "behavior-pass-build-fail", "intervention": "compiler-feedback-only"},
            "supportCount": len(compiler_support), "contradictionCount": len(compiler_contra),
            "supportRefs": compiler_support, "contradictionRefs": compiler_contra,
            "independenceSummary": compiler_independence,
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
            "independenceSummary": timeout_independence,
            "confidenceNote": "证据支持“有明显帮助”，但不支持“已经稳定”；当前完整成功仅 %d/%d。" % (timeout_full_count, len(timeout_support) + len(timeout_contra)),
            "latestEvaluatedRevision": revision, "updatedAt": now,
            "metadata": {"family": "timeout-feedback", "legacyCadenceMetadataIncomplete": True},
        },
    }
    return claims, compiler_rows + timeout_rows


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
        checkpoints = query(args.mcp_url, args.person_id, "checkpoints", revision, 500)["rows"]
        environments = query(args.mcp_url, args.person_id, "execution_environments", revision, 500)["rows"]
        claim_result = query(args.mcp_url, args.person_id, "research_claims", revision, 100)
        event_result = query(args.mcp_url, args.person_id, "claim_events", revision, 500)
        independence_result = query(args.mcp_url, args.person_id, "claim_evidence_independence", revision, 1000)
        current = {r["key"]: r for r in claim_result["rows"]}
        events = [r.get("row", r) for r in event_result["rows"]]
        existing_independence = {r["key"]: r for r in independence_result["rows"]}
        targets, desired_independence = target_claims(decisions, checkpoints, environments, revision)
        claim_ops, event_ops, independence_ops = [], [], []
        for desired in desired_independence:
            existing = existing_independence.get(desired["id"])
            compare = {k: v for k, v in desired.items() if v is not None}
            if existing is None:
                independence_ops.append({"op": "insert", "operation_id": stable_uuid("claim-independence", revision, desired["id"]), "key": desired["id"], "row": compare})
            else:
                current_row = existing["row"]
                changed_fields = {k: v for k, v in compare.items() if k != "sourceRevision" and current_row.get(k) != v}
                if changed_fields:
                    independence_ops.append({"op": "update", "operation_id": stable_uuid("claim-independence-update", revision, desired["id"]), "key": desired["id"], "expected_row_version": existing["row_version"], "set": changed_fields})
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
            if old.get("status") != target.get("status"):
                kind = "status-changed"
                event_summary = "新实验导致该结论的状态发生变化。"
            elif support_added or contradiction_added:
                kind = "evidence-updated"
                event_summary = "新实验改变了该结论的结构化支持/反例集合。"
            elif changed == ["independenceSummary"]:
                kind = "independence-updated"
                event_summary = "已有实验的独立性信息得到更完整的结构化刻画；支持/反例集合未变化。"
            else:
                kind = "claim-metadata-updated"
                event_summary = "结论元数据发生变化；支持/反例集合未变化。"
            event_id = "%s-%06d" % (claim_id, seq)
            event_ops.append({
                "op": "insert", "operation_id": stable_uuid("claim-event", revision, event_id), "key": event_id,
                "row": {"id": event_id, "claimId": claim_id, "sequence": seq, "timestamp": target["updatedAt"],
                        "kind": kind, "fromStatus": old.get("status", "unknown"), "toStatus": target["status"],
                        "sourceRevision": revision, "supportAdded": support_added, "contradictionAdded": contradiction_added,
                        "summary": event_summary,
                        "metricsBefore": {"supportCount": old.get("supportCount", 0), "contradictionCount": old.get("contradictionCount", 0)},
                        "metricsAfter": {"supportCount": target["supportCount"], "contradictionCount": target["contradictionCount"]},
                        "metadata": {"changedFields": changed}},
            })
            summary.append({"claimId": claim_id, "changed": changed, "supportAdded": support_added, "contradictionAdded": contradiction_added})
        if not claim_ops and not independence_ops:
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
                          "tables": ([{"path": "claim_evidence_independence", "operations": independence_ops}] if independence_ops else []) + ([{"path": "research_claims", "operations": claim_ops}, {"path": "claim_events", "operations": event_ops}] if claim_ops else [])},
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
