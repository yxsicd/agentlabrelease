#!/usr/bin/env python3
"""Build one revision-fenced TableGit transaction from AgentLab run evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text()) if path.is_file() else None


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_uuid(*parts: str):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "agentlab://" + "/".join(parts)))


def phase_metrics(evidence: Path, summary: dict, phase: str):
    row = summary.get("phases", {}).get(phase, {})
    lifecycle = load(evidence / "parent-agent" / f"{phase}-lifecycle.json") or {}
    edit = load(evidence / f"{phase}-edit-timing.json") or {}
    scope = row.get("scope") or load(evidence / f"{phase}-scope.json") or {}
    return {
        "behaviorPass": bool((row.get("behavior") or {}).get("pass")),
        "buildPass": bool(row.get("build")),
        "scopeDrift": bool(scope.get("drift")),
        "timedOut": bool(lifecycle.get("timedOut")),
        "durationMs": lifecycle.get("durationMs") or row.get("repairLatencyMs"),
        "firstMutationMs": edit.get("firstSourceMutationMs"),
        "gatewayRequests": row.get("gatewayRequests"),
        "changedPaths": scope.get("changedPaths", []),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--github-repository", required=True)
    parser.add_argument("--caller-person-id", required=True)
    parser.add_argument("--repo", default="agentlabtablegit")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    evidence = args.evidence.resolve()
    summary = load(evidence / "summary.json") or {}
    decision = load(evidence / "decision-package.json") or {}
    difficulty = load(evidence / "difficulty-candidates.json") or {}
    groups = {name: [] for name in (
        "difficulty_points", "checkpoints", "interventions", "crossings",
        "decisions", "capability_profiles", "evidence_refs", "execution_environments",
    )}

    def insert(path, row):
        groups[path].append({
            "op": "insert",
            "operation_id": stable_uuid(args.run_id, path, row["id"], "operation"),
            "key": row["id"],
            "row": row,
        })

    action_uri = f"https://github.com/{args.github_repository}/actions/runs/{args.run_id}"
    for filename, kind in (
        ("summary.json", "subject-summary"),
        ("decision-package.json", "harness-decision-package"),
        ("difficulty-candidates.json", "difficulty-candidates"),
        ("environment-fingerprint.json", "environment-fingerprint"),
    ):
        path = evidence / filename
        if path.is_file():
            insert("evidence_refs", {
                "id": f"evidence-{args.run_id}-{filename[:-5]}",
                "schema": "agentlab.evidence_ref.v1",
                "kind": kind,
                "uri": action_uri + "#" + filename,
                "sha256": sha256(path),
                "byteLength": path.stat().st_size,
                "sourceRevision": summary.get("sourceRevision"),
                "producerRun": args.run_id,
                "public": True,
                "metadata": {"scenario": decision.get("scenario"), "taskId": summary.get("taskId")},
            })

    environment = load(evidence / "environment-fingerprint.json") or {}
    if environment:
        runner_name = environment.get("runnerName") or "unknown-runner"
        runner_os = environment.get("runnerOs") or "unknown-os"
        runner_arch = environment.get("runnerArch") or environment.get("machine") or "unknown-arch"
        runner_identity = "|".join([str(runner_name), str(runner_os), str(runner_arch), str(environment.get("machine") or "unknown-machine")])
        insert("execution_environments", {
            "id": f"environment-{args.run_id}",
            "runId": args.run_id,
            "runnerIdentity": runner_identity,
            "runnerName": runner_name,
            "runnerOs": runner_os,
            "runnerArch": runner_arch,
            "platform": environment.get("platform"),
            "machine": environment.get("machine"),
            "executionMode": environment.get("executionMode"),
            "fingerprintSha256": sha256(evidence / "environment-fingerprint.json"),
            "sourceRevision": summary.get("sourceRevision") or "unknown",
            "evidenceRef": f"evidence-{args.run_id}-environment-fingerprint",
            "metadata": {
                "schema": environment.get("schema"),
                "docker": environment.get("docker"),
                "node": environment.get("node"),
                "python": environment.get("python"),
                "git": environment.get("git"),
            },
        })

    checkpoint_ids = []
    for file in sorted((evidence / "difficulty-checkpoints").glob("*/checkpoint.json")):
        checkpoint = load(file) or {}
        native = checkpoint.get("nativeSession") or {}
        checkpoint_id = f"checkpoint-{args.run_id}-{file.parent.name}"
        checkpoint_ids.append(checkpoint_id)
        insert("checkpoints", {
            "id": checkpoint_id,
            "schema": "agentlab.difficulty_checkpoint.v1",
            "taskId": checkpoint.get("taskId") or summary.get("taskId"),
            "sourceRevision": checkpoint.get("sourceRevision") or summary.get("sourceRevision"),
            "sourceCut": checkpoint.get("sourceCut"),
            "checkpointDigest": sha256(file),
            "nativeAgent": native.get("agent"),
            "nativeVersion": native.get("packageVersion"),
            "nativeThreadId": native.get("threadId"),
            "nativeSessionSha256": native.get("sha256"),
            "formalSessionFsSnapshot": bool(checkpoint.get("formalSessionFsSnapshot")),
            "readyForControlledFork": bool(checkpoint.get("readyForControlledFork")),
            "admittedState": {
                "phase": checkpoint.get("phase"),
                "behaviorPass": checkpoint.get("behaviorPass"),
                "buildPass": checkpoint.get("buildPass"),
                "semanticRehydrationEligible": checkpoint.get("semanticRehydrationEligible"),
            },
        })

    intervention = None
    if summary.get("timeoutFeedbackOnly", {}).get("enabled"):
        timeout_info = summary["timeoutFeedbackOnly"]
        timeout_variable = (
            "timeoutFeedbackWithVerificationCadence"
            if timeout_info.get("verificationCadenceGuidance")
            else "timeoutFeedbackOnly"
        )
        intervention = ("timeout-feedback", timeout_variable, "turn-1", "timeout-feedback-repair", timeout_info)
    elif summary.get("compilerFeedbackOnly", {}).get("enabled"):
        intervention = ("compiler-feedback", "compilerEvidenceOnly", "turn-1", "compiler-feedback-repair", summary["compilerFeedbackOnly"])

    if intervention:
        label, variable, control_phase, variant_phase, info = intervention
        intervention_id = f"intervention-{args.run_id}-{label}"
        difficulty_id = f"difficulty-{args.run_id}-{label}"
        checkpoint_id = f"checkpoint-{args.run_id}-{control_phase}"
        insert("interventions", {
            "id": intervention_id,
            "schema": "agentlab.difficulty_intervention.v1",
            "difficultyId": difficulty_id,
            "checkpointId": checkpoint_id,
            "variable": variable,
            "controlValue": {
                "evidence": "none",
                **({"verificationCadenceGuidance": False} if label == "timeout-feedback" else {}),
            },
            "variantValue": {
                "evidence": label,
                **({"verificationCadenceGuidance": bool(info.get("verificationCadenceGuidance"))} if label == "timeout-feedback" else {}),
            },
            "model": "glm-5.3-flash",
            "agentKind": "pi",
            "frozen": ["native-session-lineage", "task-demand", "provider-reasoning", "behavior-oracle", "tool-policy"],
            "status": "completed",
        })
        for arm, phase in (("control", control_phase), (label, variant_phase)):
            row = phase_metrics(evidence, summary, phase)
            row.update({
                "id": f"crossing-{args.run_id}-{phase}",
                "schema": "agentlab.difficulty_crossing.v1",
                "interventionId": intervention_id,
                "difficultyId": difficulty_id,
                "checkpointId": checkpoint_id,
                "arm": arm,
                "outputSessionSha256": info.get("inputSessionSha256") if arm == "control" else info.get("outputSessionSha256"),
            })
            insert("crossings", {key: value for key, value in row.items() if value is not None})
        variant = phase_metrics(evidence, summary, variant_phase)
        full = variant["behaviorPass"] and variant["buildPass"] and not variant["scopeDrift"]
        upstream = variant["behaviorPass"] and not variant["scopeDrift"]
        insert("decisions", {
            "id": f"decision-{args.run_id}-{label}",
            "schema": "agentlab.difficulty_decision.v1",
            "difficultyId": difficulty_id,
            "interventionId": intervention_id,
            "decision": "accept-full-crossing" if full else "accept-upstream-crossing-route-downstream-repair" if upstream else "no-crossing",
            "reason": f"{label}: behaviorPass={variant['behaviorPass']}, buildPass={variant['buildPass']}, scopeDrift={variant['scopeDrift']}; preserve independent gates and exact output session.",
            "preferredArm": label if upstream else "control",
            "nextExperiment": "repeat-for-robustness" if full else "compiler-evidence-only" if upstream and not variant["buildPass"] else "design-next-experiment",
            "nextCheckpointBoundary": "post-" + label,
            "holdConstant": ["model", "provider-reasoning", "task", "behavior-oracle", "tool-policy"],
            "measure": ["latency", "gateway-requests", "behavior", "build", "scope-drift"],
        })

    for candidate in difficulty.get("candidates", []):
        dimension = candidate.get("dimensionId") or candidate.get("dimension")
        primary = candidate.get("primaryDimension") or candidate.get("category")
        mechanism = candidate.get("mechanism") or candidate.get("signature")
        if not all(isinstance(value, str) and value for value in (dimension, primary, mechanism)):
            continue
        candidate_id = f"difficulty-{args.run_id}-{hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest()[:16]}"
        insert("difficulty_points", {
            "id": candidate_id,
            "schema": "agentlab.difficulty_point.v1",
            "taskId": summary.get("taskId"),
            "dimensionId": dimension,
            "primaryDimension": primary,
            "mechanism": mechanism,
            "signature": candidate.get("signature"),
            "status": candidate.get("status", "candidate"),
            "maturityState": candidate.get("maturityState", "candidate"),
            "sourceRevision": summary.get("sourceRevision"),
            "checkpointIds": checkpoint_ids,
            "evidenceIds": [f"evidence-{args.run_id}-difficulty-candidates"],
            "observation": {"producerRun": args.run_id, "reproducible": candidate.get("reproducible")},
        })

    tables = [{"path": path, "operations": operations} for path, operations in groups.items() if operations]
    if not tables:
        raise SystemExit("no durable rows derived from run")
    transaction_id = stable_uuid(args.run_id, "cbgroom-flywheel-v1")
    payload = {
        "skill_id": "table.author",
        "skill_version": "2.2.0",
        "operation": "worktree_table_batch_transaction",
        "caller_person_id": args.caller_person_id,
        "arguments": {
            "repo": args.repo,
            "expected_revision": args.revision,
            "transaction_id": transaction_id,
            "idempotency_key": transaction_id,
            "actor": {"kind": "github-action", "repository": args.github_repository, "runId": args.run_id},
            "tables": tables,
            "topic_id": "main",
            "message": f"Persist AgentLab flywheel run {args.run_id}",
        },
    }
    args.output.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    print(json.dumps({"ok": True, "tables": {entry["path"]: len(entry["operations"]) for entry in tables}, "transactionId": transaction_id}, sort_keys=True))


if __name__ == "__main__":
    main()
