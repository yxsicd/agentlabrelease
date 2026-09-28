#!/usr/bin/env python3
"""Run one credential-shielded Agent proposal through the Maintainer Skill gate."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


SEMANTIC_DIMENSIONS = {"responsibility", "boundary", "relations", "behavior"}
SHA1 = re.compile(r"[0-9a-f]{40}")
SAFE_ID = re.compile(r"agent-analysis-[a-z0-9-]{8,120}")


def load(path: Path):
    return json.loads(path.read_text())


def rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def select_scope(scope_rows, assessment, repository_id):
    states = {row["skillId"]: row for row in assessment["skills"]}
    eligible = []
    for scope in scope_rows:
        if scope.get("repositoryId") != repository_id:
            continue
        state = states.get(scope.get("id"), {})
        if state.get("maturity") != "L1-structural-ready":
            continue
        source_count = scope.get("sourceFileCount", 0)
        if not isinstance(source_count, int) or source_count < 1 or source_count > 80:
            continue
        if scope.get("pathBoundary") == ".":
            continue
        eligible.append(scope)
    require(eligible, f"no bounded L1 source scope is eligible in {repository_id}")
    eligible.sort(
        key=lambda row: (
            0 if row.get("testFileCount", 0) else 1,
            row.get("sourceFileCount", 0),
            row["id"],
        )
    )
    return eligible[0]


def prepare(args):
    cut = load(args.knowledge / "maintainer-knowledge-cut.json")
    assessment = load(args.assessment)
    scope_rows = rows(args.knowledge / "maintainer_scope_skills.jsonl")
    source = next(
        (row for row in cut["repositories"] if row["id"] == args.repository), None
    )
    require(source is not None, "repository is absent from the knowledge cut")
    scope = select_scope(scope_rows, assessment, args.repository)
    packet = {
        "schema": "agentlab.maintainer_skill_agent_request.v1",
        "automaticPromotion": False,
        "sourceAssessment": {
            "path": str(args.assessment),
            "sha256": digest(args.assessment),
            "roundIndex": assessment["roundIndex"],
        },
        "repository": source,
        "scope": scope,
        "requiredDimensions": sorted(SEMANTIC_DIMENSIONS),
        "forbiddenDimensions": ["operation"],
        "output": "program-fact-proposal.json",
    }
    write(args.output, packet)
    print(scope["id"])


def run_agent(args):
    packet = load(args.request)
    require(packet.get("schema") == "agentlab.maintainer_skill_agent_request.v1", "bad request")
    repository = packet["repository"]
    source_root = args.source.resolve(strict=True)
    head = subprocess.check_output(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True
    ).strip()
    require(head == repository["revision"], "source checkout revision differs")
    workspace = args.output / "workspace"
    evidence = args.output / "evidence"
    workspace.mkdir(parents=True)
    evidence.mkdir()
    shutil.copy2(args.request, workspace / "flywheel-request.json")
    os.symlink(source_root, workspace / "source", target_is_directory=True)

    module_path = Path(__file__).resolve().parents[1] / "real-code-agent" / "participant.py"
    spec = importlib.util.spec_from_file_location("agentlab_participant", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    participant = module.Participant(
        evidence,
        args.output / "participant-state",
        args.pi,
        args.gateway,
        args.model,
        route=args.provider_route,
        implementation="pi",
    )
    scope = packet["scope"]
    prompt = f"""You are a Maintainer Skill construction Agent, not an assessed Agent.
Read flywheel-request.json and inspect the exact Git checkout under source/.
Analyze only scope {scope['id']} at path boundary {scope['pathBoundary']}.
Write exactly one JSON object to program-fact-proposal.json and do not modify source/ or flywheel-request.json.

The object must have exactly these fields:
- schema: agentlab.maintainer_skill_fact_proposal.v1
- id: agent-analysis- followed by a stable lowercase hyphenated mechanism name
- repositoryId and sourceRevision exactly from the request
- scopeSkillIds: an array containing only the selected scope id
- kind: analysis
- dimensions: exactly responsibility, boundary, relations, behavior
- interpretation: a concise evidence-backed maintenance contract
- evidence: at least two objects with repository-relative path and exact 40-hex gitBlobOid
- limitations: at least two concrete unproved claims

Use git rev-parse HEAD:path to obtain every blob identity. Evidence paths may include direct cross-boundary dependencies when needed, but at least one must be inside the selected scope. Do not claim runtime execution, build success, compiler dataflow, device behavior, performance, an approved Oracle, or operation readiness. Do not copy secrets or generated files. Validate the JSON once, then finish.
"""
    try:
        participant.turn(
            "maintainer-skill-author",
            workspace,
            prompt=prompt,
            wall_time_limit_seconds=720,
        )
    finally:
        participant.close()
    proposal = workspace / "program-fact-proposal.json"
    require(proposal.is_file() and not proposal.is_symlink(), "Agent did not produce a proposal")
    shutil.copy2(proposal, args.output / "program-fact-proposal.json")
    status = subprocess.check_output(
        ["git", "-C", str(source_root), "status", "--porcelain"], text=True
    )
    (args.output / "source-status.txt").write_text(status)
    require(not status, "Agent modified the pinned source checkout")


def validate_proposal(request, proposal, source_root):
    require(proposal.get("schema") == "agentlab.maintainer_skill_fact_proposal.v1", "bad proposal schema")
    require(set(proposal) == {
        "schema", "id", "repositoryId", "sourceRevision", "scopeSkillIds",
        "kind", "dimensions", "interpretation", "evidence", "limitations",
    }, "proposal fields differ")
    require(SAFE_ID.fullmatch(proposal.get("id", "")), "proposal id is invalid")
    require(proposal["repositoryId"] == request["repository"]["id"], "repository differs")
    require(proposal["sourceRevision"] == request["repository"]["revision"], "revision differs")
    require(proposal["scopeSkillIds"] == [request["scope"]["id"]], "scope binding differs")
    require(proposal["kind"] == "analysis", "only analysis proposals are accepted")
    require(set(proposal["dimensions"]) == SEMANTIC_DIMENSIONS and len(proposal["dimensions"]) == 4,
            "semantic dimensions are incomplete or overclaimed")
    require(isinstance(proposal["interpretation"], str) and 80 <= len(proposal["interpretation"]) <= 1600,
            "interpretation length is invalid")
    limitations = proposal["limitations"]
    require(isinstance(limitations, list) and len(limitations) >= 2 and all(isinstance(x, str) and x.strip() for x in limitations),
            "limitations are incomplete")
    evidence = proposal["evidence"]
    require(isinstance(evidence, list) and len(evidence) >= 2, "at least two evidence blobs are required")
    boundary = request["scope"]["pathBoundary"].rstrip("/")
    inside = False
    seen = set()
    clean_evidence = []
    for row in evidence:
        require(isinstance(row, dict) and set(row) == {"path", "gitBlobOid"}, "evidence fields differ")
        path = row["path"]
        oid = row["gitBlobOid"]
        require(isinstance(path, str) and path and not path.startswith("/") and "\\" not in path,
                "evidence path is unsafe")
        require(all(part not in ("", ".", "..") for part in path.split("/")), "evidence path is unsafe")
        require(SHA1.fullmatch(oid or ""), "evidence blob id is invalid")
        require(path not in seen, "evidence paths are duplicated")
        seen.add(path)
        actual = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", f"{proposal['sourceRevision']}:{path}"],
            capture_output=True, text=True,
        )
        require(actual.returncode == 0 and actual.stdout.strip() == oid, f"evidence blob differs: {path}")
        inside = inside or path == boundary or path.startswith(boundary + "/")
        clean_evidence.append({"path": path, "gitBlobOid": oid})
    require(inside, "no evidence path is inside the selected scope")
    return {
        "id": proposal["id"],
        "kind": "analysis",
        "repositoryId": proposal["repositoryId"],
        "sourceRevision": proposal["sourceRevision"],
        "scopeSkillIds": proposal["scopeSkillIds"],
        "dimensions": sorted(SEMANTIC_DIMENSIONS),
        "interpretation": proposal["interpretation"],
        "limitations": limitations,
        "evidence": clean_evidence,
        "agentProposal": {
            "schema": proposal["schema"],
            "automaticPromotion": False,
            "sourceAssessmentSha256": request["sourceAssessment"]["sha256"],
        },
    }


def validate(args):
    request = load(args.request)
    proposal = load(args.proposal)
    fact = validate_proposal(request, proposal, args.source.resolve(strict=True))
    existing = rows(args.program_facts)
    require(fact["id"] not in {row["id"] for row in existing}, "proposal id already exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as target:
        for row in existing + [fact]:
            target.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
    write(args.receipt, {
        "schema": "agentlab.maintainer_skill_agent_proposal_receipt.v1",
        "automaticPromotion": False,
        "acceptedFactId": fact["id"],
        "scopeSkillId": request["scope"]["id"],
        "sourceAssessmentSha256": request["sourceAssessment"]["sha256"],
        "candidateProgramFactsSha256": digest(args.output),
        "decision": "accepted-for-hard-gate-assessment",
    })


def compare(args):
    before = load(args.before)
    after = load(args.after)
    require(after["parentAssessmentSha256"] == digest(args.before), "assessment lineage differs")
    for key in ("scopeSkillCount", "structuralReadyCount"):
        require(after["totals"][key] == before["totals"][key], f"{key} changed")
    require(after["totals"]["programBoundCount"] == before["totals"]["programBoundCount"] + 1,
            "proposal did not bind exactly one new scope")
    require(after["totals"]["semanticReadyCount"] == before["totals"]["semanticReadyCount"] + 1,
            "proposal did not advance exactly one scope to L2")
    require(after["totals"]["maintenanceReadyCount"] == before["totals"]["maintenanceReadyCount"],
            "semantic proposal must not grant operation readiness")
    write(args.output, {
        "schema": "agentlab.maintainer_skill_agent_flywheel_result.v1",
        "automaticPromotion": False,
        "decision": "review-proposed-knowledge",
        "before": before["totals"],
        "after": after["totals"],
        "assessmentSha256": digest(args.after),
    })


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--knowledge", type=Path, required=True)
    p.add_argument("--assessment", type=Path, required=True)
    p.add_argument("--repository", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(handler=prepare)
    p = commands.add_parser("run-agent")
    p.add_argument("--request", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--pi", type=Path, required=True)
    p.add_argument("--gateway", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--provider-route", required=True)
    p.set_defaults(handler=run_agent)
    p = commands.add_parser("validate")
    p.add_argument("--request", type=Path, required=True)
    p.add_argument("--proposal", type=Path, required=True)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--program-facts", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    p.set_defaults(handler=validate)
    p = commands.add_parser("compare")
    p.add_argument("--before", type=Path, required=True)
    p.add_argument("--after", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(handler=compare)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
