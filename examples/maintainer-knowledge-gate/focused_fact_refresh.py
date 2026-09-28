#!/usr/bin/env python3
"""Refresh one existing semantic fact from a construction-readiness blocker."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess


HERE = Path(__file__).resolve().parent


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


BASE = module("agent_flywheel_base", HERE / "agent_flywheel.py")
READINESS = module("shadow_readiness", HERE / "shadow_construction_readiness.py")


def prepare(args) -> None:
    plan_root = (args.knowledge / "construction-plans").resolve(strict=True)
    plan_path = args.plan.resolve(strict=True)
    BASE.require(plan_path.is_relative_to(plan_root),
                 "focused refresh plan must be under the knowledge construction-plans directory")
    receipt = READINESS.assess(
        args.knowledge, args.candidate_id, plan_path, args.evidence_root.resolve(strict=True)
    )
    BASE.require(receipt["decision"] == "blocked-knowledge-refresh",
                 "focused refresh requires a blocked-knowledge-refresh receipt")
    candidate = next(
        row for row in READINESS.rows(args.knowledge / "case_generation_candidates.jsonl")
        if row["id"] == args.candidate_id
    )
    fact_id = candidate["factIds"]
    BASE.require(len(fact_id) == 1, "focused refresh currently requires exactly one bound fact")
    facts = {row["id"]: row for row in READINESS.rows(args.knowledge / "program_facts.jsonl")}
    scopes = {row["id"]: row for row in READINESS.rows(args.knowledge / "maintainer_scope_skills.jsonl")}
    fact = facts[fact_id[0]]
    BASE.require(candidate["scopeSkillIds"] == fact["scopeSkillIds"] and len(fact["scopeSkillIds"]) == 1,
                 "candidate, fact and scope binding differ")
    scope = scopes[fact["scopeSkillIds"][0]]
    cut = READINESS.load(args.knowledge / "maintainer-knowledge-cut.json")
    repository = next(row for row in cut["repositories"] if row["id"] == candidate["repositoryId"])
    assessment = READINESS.load(args.assessment)
    plan = READINESS.load(plan_path)
    packet = {
        "schema": "agentlab.maintainer_skill_focused_refresh_request.v1",
        "automaticPromotion": False,
        "sourceAssessment": {
            "path": str(args.assessment),
            "sha256": BASE.digest(args.assessment),
            "roundIndex": assessment["roundIndex"],
        },
        "candidateId": args.candidate_id,
        "candidateSha256": receipt["candidateSha256"],
        "knowledgeCutSha256": receipt["knowledgeCutSha256"],
        "constructionPlanSha256": receipt["planSha256"],
        "repository": repository,
        "scope": scope,
        "existingFact": fact,
        "requiredImplementationPaths": plan["requiredImplementationPaths"],
        "requiredOraclePaths": plan["requiredOraclePaths"],
        "readinessDecision": receipt["decision"],
        "output": "program-fact-proposal.json",
    }
    BASE.write(args.output, packet)


def run_agent(args) -> None:
    request = BASE.load(args.request)
    BASE.require(request.get("schema") == "agentlab.maintainer_skill_focused_refresh_request.v1",
                 "bad focused-refresh request")
    source_root = args.source.resolve(strict=True)
    head = subprocess.check_output(["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True).strip()
    BASE.require(head == request["repository"]["revision"], "source checkout revision differs")
    workspace = args.output / "workspace"
    evidence = args.output / "evidence"
    workspace.mkdir(parents=True)
    evidence.mkdir()
    shutil.copy2(args.request, workspace / "focused-refresh-request.json")
    (workspace / "source").symlink_to(source_root, target_is_directory=True)
    participant_path = HERE.parent / "real-code-agent" / "participant.py"
    participant_module = module("agentlab_participant_focused", participant_path)
    participant = participant_module.Participant(
        evidence, args.output / "participant-state", args.pi, args.gateway, args.model,
        route=args.provider_route, implementation="pi",
    )
    fact = request["existingFact"]
    required = sorted({
        item["path"]
        for field in ("requiredImplementationPaths", "requiredOraclePaths")
        for item in request[field]
    })
    prompt = f"""You are refreshing one existing Maintainer Skill program fact, not assessing an Agent.
Read focused-refresh-request.json and inspect the exact read-only source checkout. Update fact {fact['id']} only.
Write exactly one JSON object to program-fact-proposal.json. Do not modify source/ or the request.

The object must use the same exact schema, id, repositoryId, sourceRevision, scopeSkillIds, kind and four semantic dimensions as existingFact. Preserve every existing evidence path and add exact Git Blob evidence for every required path: {json.dumps(required)}. Update interpretation so it accurately covers the complete implementation/Oracle source surface, and retain at least two concrete limitations without claiming build, emulator, Oracle, or operation success. Evidence objects contain only path and exact 40-hex gitBlobOid obtained with git rev-parse HEAD:path. Do not add unrelated paths, secrets, generated files, runtime claims, a gold patch, or automatic-promotion fields. Parse the completed JSON once, then finish.
"""
    try:
        participant.turn("maintainer-skill-focused-refresh", workspace, prompt=prompt,
                         wall_time_limit_seconds=720)
    finally:
        participant.close()
        (workspace / "source").unlink(missing_ok=True)
    proposal = workspace / "program-fact-proposal.json"
    BASE.require(proposal.is_file() and not proposal.is_symlink(), "Agent did not produce a refresh proposal")
    shutil.copy2(proposal, args.output / "program-fact-proposal.json")
    status = subprocess.check_output(["git", "-C", str(source_root), "status", "--porcelain"], text=True)
    (args.output / "source-status.txt").write_text(status)
    BASE.require(not status, "Agent modified the pinned source checkout")


def validate(args) -> None:
    request = BASE.load(args.request)
    proposal = BASE.load(args.proposal)
    fact = BASE.validate_proposal(request, proposal, args.source.resolve(strict=True))
    existing = READINESS.rows(args.program_facts)
    old = request["existingFact"]
    BASE.require(fact["id"] == old["id"], "focused refresh changed fact identity")
    old_paths = {row["path"] for row in old["evidence"]}
    new_paths = {row["path"] for row in fact["evidence"]}
    required_paths = {
        item["path"]
        for field in ("requiredImplementationPaths", "requiredOraclePaths")
        for item in request[field]
    }
    BASE.require(old_paths.issubset(new_paths), "focused refresh removed existing evidence")
    BASE.require(required_paths.issubset(new_paths), "focused refresh omitted required readiness paths")
    BASE.require(READINESS.value_digest(old) != READINESS.value_digest(fact),
                 "focused refresh did not change the fact")
    replaced = [fact if row["id"] == fact["id"] else row for row in existing]
    BASE.require(sum(row["id"] == fact["id"] for row in existing) == 1,
                 "existing fact is absent or duplicated")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(b"".join(
        READINESS.canonical(row) + b"\n" for row in sorted(replaced, key=lambda row: row["id"])
    ))
    BASE.write(args.receipt, {
        "schema": "agentlab.maintainer_skill_agent_proposal_receipt.v1",
        "automaticPromotion": False,
        "changeKind": "updated",
        "acceptedFactId": fact["id"],
        "scopeSkillId": request["scope"]["id"],
        "candidateId": request["candidateId"],
        "sourceAssessmentSha256": request["sourceAssessment"]["sha256"],
        "previousFactSha256": READINESS.value_digest(old),
        "acceptedFactSha256": READINESS.value_digest(fact),
        "candidateProgramFactsSha256": BASE.digest(args.output),
        "addedEvidencePaths": sorted(new_paths - old_paths),
        "decision": "accepted-focused-refresh-for-hard-gate-assessment",
    })


def compare(args) -> None:
    before = BASE.load(args.before)
    after = BASE.load(args.after)
    BASE.require(after["parentAssessmentSha256"] == BASE.digest(args.before), "assessment lineage differs")
    BASE.require(after["totals"] == before["totals"], "focused refresh changed maturity totals")
    before_state = next(row for row in before["skills"] if row["skillId"] == args.scope_id)
    after_state = next(row for row in after["skills"] if row["skillId"] == args.scope_id)
    BASE.require(before_state["maturity"] == after_state["maturity"] == "L2-semantic-ready",
                 "focused refresh changed scope maturity")
    BASE.write(args.output, {
        "schema": "agentlab.maintainer_skill_agent_flywheel_result.v1",
        "automaticPromotion": False,
        "decision": "review-proposed-knowledge-refresh",
        "before": before["totals"],
        "after": after["totals"],
        "scopeSkillId": args.scope_id,
        "maturity": after_state["maturity"],
        "assessmentSha256": BASE.digest(args.after),
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--knowledge", type=Path, required=True); p.add_argument("--assessment", type=Path, required=True)
    p.add_argument("--candidate-id", required=True); p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--evidence-root", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    p.set_defaults(handler=prepare)
    p = commands.add_parser("run-agent")
    p.add_argument("--request", type=Path, required=True); p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True); p.add_argument("--pi", type=Path, required=True)
    p.add_argument("--gateway", required=True); p.add_argument("--model", required=True); p.add_argument("--provider-route", required=True)
    p.set_defaults(handler=run_agent)
    p = commands.add_parser("validate")
    p.add_argument("--request", type=Path, required=True); p.add_argument("--proposal", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True); p.add_argument("--program-facts", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True); p.add_argument("--receipt", type=Path, required=True)
    p.set_defaults(handler=validate)
    p = commands.add_parser("compare")
    p.add_argument("--before", type=Path, required=True); p.add_argument("--after", type=Path, required=True)
    p.add_argument("--scope-id", required=True); p.add_argument("--output", type=Path, required=True)
    p.set_defaults(handler=compare)
    args = parser.parse_args(); args.handler(args)


if __name__ == "__main__":
    main()
