#!/usr/bin/env python3
"""Run one credential-shielded Agent proposal through the Maintainer Skill gate."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


SEMANTIC_DIMENSIONS = {"responsibility", "boundary", "relations", "behavior"}
CORE_DIMENSIONS = {"responsibility", "boundary", "relations"}
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


def path_is_within(path, boundary):
    boundary = boundary.rstrip("/")
    if boundary == ".":
        return True
    return path == boundary or path.startswith(boundary + "/")


def scope_has_reachable_evidence(scope):
    boundary = scope.get("pathBoundary")
    evidence = scope.get("evidence")
    if not isinstance(boundary, str) or not boundary or not isinstance(evidence, list):
        return False
    return any(
        isinstance(row, dict)
        and isinstance(row.get("path"), str)
        and path_is_within(row["path"], boundary)
        for row in evidence
    )


def analysis_profile(scope):
    source_count = scope.get("sourceFileCount")
    if scope.get("pathBoundary") == ".":
        dimensions = SEMANTIC_DIMENSIONS if isinstance(source_count, int) and source_count > 0 else CORE_DIMENSIONS
        return "repository-contract", dimensions
    if source_count == 0:
        return "configuration-asset", CORE_DIMENSIONS
    return "source-behavior", SEMANTIC_DIMENSIONS


def valid_decomposition_plan(scope, plan, max_source_files=80):
    if not isinstance(plan, dict):
        return False
    parent = plan.get("parent", {})
    verification = plan.get("verification", {})
    leaves = plan.get("leaves", [])
    return (
        plan.get("schema") == "agentlab.maintainer_scope_decomposition_plan.v1"
        and plan.get("automaticPromotion") is False
        and plan.get("repositoryId") == scope.get("repositoryId")
        and plan.get("sourceRevision") == scope.get("sourceRevision")
        and plan.get("sourceTreeOid") == scope.get("sourceTreeOid")
        and plan.get("maxSourceFilesPerLeaf") == max_source_files
        and parent.get("scopeSkillId") == scope.get("id")
        and parent.get("pathBoundary") == scope.get("pathBoundary")
        and parent.get("trackedFileCount") == scope.get("trackedFileCount")
        and parent.get("sourceFileCount") == scope.get("sourceFileCount")
        and verification.get("complete") is True
        and verification.get("nonOverlapping") is True
        and verification.get("unassignedFileCount") == 0
        and verification.get("multiplyAssignedFileCount") == 0
        and len(leaves) >= 2
        and verification.get("assignedFileCount") == scope.get("trackedFileCount")
        and sum(leaf.get("trackedFileCount", -1) for leaf in leaves) == scope.get("trackedFileCount")
        and sum(leaf.get("sourceFileCount", -1) for leaf in leaves) == scope.get("sourceFileCount")
        and all(
            isinstance(leaf.get("trackedFileCount"), int)
            and leaf["trackedFileCount"] >= 1
            and isinstance(leaf.get("sourceFileCount"), int)
            and 0 <= leaf["sourceFileCount"] <= max_source_files
            for leaf in leaves
        )
    )


def valid_decomposition_review(scope, decomposition, review, max_source_files=80):
    if not isinstance(review, dict) or not decomposition:
        return False
    groups = review.get("groups", [])
    verification = review.get("verification", {})
    return (
        review.get("schema") == "agentlab.maintainer_scope_decomposition_review.v1"
        and review.get("automaticCatalogApply") is False
        and review.get("repositoryId") == scope.get("repositoryId")
        and review.get("sourceRevision") == scope.get("sourceRevision")
        and review.get("sourceTreeOid") == scope.get("sourceTreeOid")
        and review.get("parentScopeSkillId") == scope.get("id")
        and review.get("decompositionPlanSha256") == decomposition.get("sha256")
        and review.get("blockerCode") == "MS-COMPOSITE-SELECTOR-NOT-SUPPORTED"
        and review.get("decision") == "blocked-catalog-application"
        and verification.get("complete") is True
        and verification.get("nonOverlapping") is True
        and verification.get("assignedFileCount") == scope.get("trackedFileCount")
        and verification.get("unassignedLeafCount") == 0
        and verification.get("multiplyAssignedLeafCount") == 0
        and verification.get("semanticGroupCount") == len(groups)
        and len(groups) >= 2
        and all(
            isinstance(group.get("trackedFileCount"), int)
            and group["trackedFileCount"] >= 1
            and isinstance(group.get("sourceFileCount"), int)
            and 0 <= group["sourceFileCount"] <= max_source_files
            for group in groups
        )
        and sum(group["trackedFileCount"] for group in groups) == scope.get("trackedFileCount")
        and sum(group["sourceFileCount"] for group in groups) == scope.get("sourceFileCount")
    )


def classify_scope(scope, state, max_source_files=80, decomposition=None, review=None):
    maturity = state.get("maturity", "unknown")
    analysis_mode, _ = analysis_profile(scope)
    base = {
        "skillId": scope.get("id"),
        "pathBoundary": scope.get("pathBoundary"),
        "maturity": maturity,
        "sourceFileCount": scope.get("sourceFileCount"),
        "testFileCount": scope.get("testFileCount"),
        "analysisMode": analysis_mode,
    }
    if maturity in ("L2-semantic-ready", "L3-maintenance-ready"):
        return {**base, "disposition": "already-advanced", "nextAction": "preserve-and-refresh-on-new-evidence"}
    if maturity != "L1-structural-ready":
        return {**base, "disposition": "blocked", "blockerCode": "MS-STRUCTURE-NOT-READY",
                "nextAction": "repair-structural-inventory"}
    source_count = scope.get("sourceFileCount")
    if not isinstance(source_count, int) or source_count < 0:
        return {**base, "disposition": "blocked", "blockerCode": "MS-SOURCE-COUNT-INVALID",
                "nextAction": "repair-structural-inventory"}
    if source_count > max_source_files:
        if decomposition and valid_decomposition_plan(scope, decomposition["plan"], max_source_files):
            plan = decomposition["plan"]
            if review and valid_decomposition_review(
                scope, decomposition, review["review"], max_source_files
            ):
                reviewed = review["review"]
                return {
                    **base,
                    "disposition": "blocked",
                    "blockerCode": "MS-COMPOSITE-SELECTOR-NOT-SUPPORTED",
                    "nextAction": "implement-composite-ownership-selectors-and-atomic-catalog-apply",
                    "decompositionPlan": {
                        "path": decomposition["path"],
                        "sha256": decomposition["sha256"],
                        "leafCount": len(plan["leaves"]),
                        "status": "complete-non-overlapping-candidate",
                    },
                    "decompositionReview": {
                        "path": review["path"],
                        "sha256": review["sha256"],
                        "semanticGroupCount": len(reviewed["groups"]),
                        "status": "complete-non-overlapping-semantic-proposal",
                    },
                }
            return {
                **base,
                "disposition": "blocked",
                "blockerCode": "MS-SCOPE-DECOMPOSITION-REVIEW-REQUIRED",
                "nextAction": "review-and-apply-scope-decomposition",
                "decompositionPlan": {
                    "path": decomposition["path"],
                    "sha256": decomposition["sha256"],
                    "leafCount": len(plan["leaves"]),
                    "status": "complete-non-overlapping-candidate",
                },
            }
        return {**base, "disposition": "blocked", "blockerCode": "MS-SCOPE-DECOMPOSITION-REQUIRED",
                "nextAction": "decompose-scope-by-owned-behavior-boundary"}
    if not scope_has_reachable_evidence(scope):
        return {**base, "disposition": "blocked", "blockerCode": "MS-INVENTORY-EVIDENCE-UNREACHABLE",
                "nextAction": "repair-scope-evidence-paths"}
    return {**base, "disposition": "eligible", "nextAction": f"run-{analysis_mode}-analysis"}


def repository_plan(scope_rows, assessment, repository_id, revision=None,
                    decompositions=None, reviews=None):
    states = {row["skillId"]: row for row in assessment["skills"]}
    decompositions = decompositions or {}
    reviews = reviews or {}
    planned = [
        classify_scope(
            scope,
            states.get(scope.get("id"), {}),
            decomposition=decompositions.get(scope.get("id")),
            review=reviews.get(scope.get("id")),
        )
        for scope in scope_rows
        if scope.get("repositoryId") == repository_id
    ]
    require(planned, f"repository has no scope Skills: {repository_id}")
    eligible = sum(row["disposition"] == "eligible" for row in planned)
    blocked = sum(row["disposition"] == "blocked" for row in planned)
    advanced = sum(row["disposition"] == "already-advanced" for row in planned)
    return {
        "schema": "agentlab.maintainer_skill_convergence_plan.v2",
        "repositoryId": repository_id,
        "sourceRevision": revision,
        "sourceAssessmentSha256": None,
        "selectionPolicy": {
            "maxSourceFilesPerAgentRound": 80,
            "analysisModes": ["configuration-asset", "repository-contract", "source-behavior"],
            "rootScopeRequiresSpecialistMode": True,
            "requiresReachableBlobEvidence": True,
            "repositorySpecificBranches": False,
        },
        "summary": {"scopeCount": len(planned), "eligible": eligible, "blocked": blocked,
                    "alreadyAdvanced": advanced},
        "decision": "advance-eligible-scopes" if eligible else (
            "blocked" if blocked else "semantic-expansion-complete"
        ),
        "scopes": planned,
        "automaticPromotion": False,
    }


def eligible_scopes(scope_rows, assessment, repository_id):
    states = {row["skillId"]: row for row in assessment["skills"]}
    return [
        scope for scope in scope_rows
        if scope.get("repositoryId") == repository_id
        and classify_scope(scope, states.get(scope.get("id"), {}))["disposition"] == "eligible"
    ]


def select_scope(scope_rows, assessment, repository_id):
    eligible = eligible_scopes(scope_rows, assessment, repository_id)
    require(eligible, f"no bounded L1 source scope is eligible in {repository_id}")
    eligible.sort(
        key=lambda row: (
            0 if row.get("testFileCount", 0) else 1,
            row.get("sourceFileCount", 0),
            row["id"],
        )
    )
    return eligible[0]


def select_repository(scope_rows, assessment, repository_ids):
    states = {row["skillId"]: row for row in assessment["skills"]}
    candidates = []
    for repository_id in repository_ids:
        repository_scopes = [
            row for row in scope_rows if row.get("repositoryId") == repository_id
        ]
        eligible = eligible_scopes(scope_rows, assessment, repository_id)
        if not repository_scopes or not eligible:
            continue
        advanced = sum(
            states.get(row.get("id"), {}).get("maturity") != "L1-structural-ready"
            for row in repository_scopes
        )
        candidates.append(
            (Fraction(advanced, len(repository_scopes)), advanced, repository_id)
        )
    require(candidates, "no repository has a reachable bounded L1 source scope")
    return min(candidates)[2]


def prepare(args):
    cut = load(args.knowledge / "maintainer-knowledge-cut.json")
    assessment = load(args.assessment)
    scope_rows = rows(args.knowledge / "maintainer_scope_skills.jsonl")
    repository_id = args.repository
    if repository_id == "auto":
        repository_id = select_repository(
            scope_rows, assessment, [row["id"] for row in cut["repositories"]]
        )
    source = next(
        (row for row in cut["repositories"] if row["id"] == repository_id), None
    )
    require(source is not None, "repository is absent from the knowledge cut")
    scope = select_scope(scope_rows, assessment, repository_id)
    analysis_mode, required_dimensions = analysis_profile(scope)
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
        "analysisMode": analysis_mode,
        "requiredDimensions": sorted(required_dimensions),
        "forbiddenDimensions": ["operation"],
        "output": "program-fact-proposal.json",
    }
    write(args.output, packet)
    print(scope["id"])


def eligible_count(args):
    cut = load(args.knowledge / "maintainer-knowledge-cut.json")
    assessment = load(args.assessment)
    scope_rows = rows(args.knowledge / "maintainer_scope_skills.jsonl")
    require(
        any(row["id"] == args.repository for row in cut["repositories"]),
        "repository is absent from the knowledge cut",
    )
    print(len(eligible_scopes(scope_rows, assessment, args.repository)))


def plan(args):
    cut = load(args.knowledge / "maintainer-knowledge-cut.json")
    assessment = load(args.assessment)
    scope_rows = rows(args.knowledge / "maintainer_scope_skills.jsonl")
    source = next((row for row in cut["repositories"] if row["id"] == args.repository), None)
    require(source is not None, "repository is absent from the knowledge cut")
    decompositions = {}
    decomposition_root = args.knowledge / "decomposition-plans"
    if decomposition_root.is_dir():
        for path in sorted(decomposition_root.glob("*.json")):
            candidate = load(path)
            parent_id = candidate.get("parent", {}).get("scopeSkillId")
            require(parent_id not in decompositions, f"duplicate decomposition plan: {parent_id}")
            decompositions[parent_id] = {
                "path": str(path.relative_to(args.knowledge)),
                "sha256": digest(path),
                "plan": candidate,
            }
    reviews = {}
    review_root = args.knowledge / "decomposition-reviews"
    if review_root.is_dir():
        for path in sorted(review_root.glob("*.json")):
            candidate = load(path)
            parent_id = candidate.get("parentScopeSkillId")
            require(parent_id not in reviews, f"duplicate decomposition review: {parent_id}")
            reviews[parent_id] = {
                "path": str(path.relative_to(args.knowledge)),
                "sha256": digest(path),
                "review": candidate,
            }
    value = repository_plan(
        scope_rows, assessment, args.repository, source["revision"], decompositions, reviews
    )
    value["sourceAssessmentSha256"] = digest(args.assessment)
    write(args.output, value)
    print(json.dumps(value["summary"], separators=(",", ":"), sort_keys=True))


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
    dimensions = packet["requiredDimensions"]
    dimensions_text = ", ".join(dimensions)
    mode_guidance = {
        "source-behavior": "Trace the bounded source responsibility, public boundary, direct relations and observable behavior contract.",
        "configuration-asset": "Inspect configuration, resources or build metadata and their declared consumers. Do not invent runtime behavior for a non-source scope.",
        "repository-contract": "Inspect root manifests, maintainer guidance and declared module/build entrypoints only. Describe repository-wide composition without recursively reading every module.",
    }
    require(packet.get("analysisMode") in mode_guidance, "unsupported analysis mode")
    prompt = f"""You are a Maintainer Skill construction Agent, not an assessed Agent.
Read flywheel-request.json and inspect the exact Git checkout under source/.
Analyze only scope {scope['id']} at path boundary {scope['pathBoundary']}.
Analysis mode is {packet['analysisMode']}. {mode_guidance[packet['analysisMode']]}
Write exactly one JSON object to program-fact-proposal.json and do not modify source/ or flywheel-request.json.

The object must have exactly these fields:
- schema: agentlab.maintainer_skill_fact_proposal.v1
- id: agent-analysis- followed by a stable lowercase hyphenated mechanism name
- repositoryId and sourceRevision exactly from the request
- scopeSkillIds: an array containing only the selected scope id
- kind: analysis
- dimensions: exactly {dimensions_text}
- interpretation: a concise evidence-backed maintenance contract of 400-1200 Unicode characters
- evidence: at least two objects with exactly the keys path and gitBlobOid, for example
  {{"path":"relative/file.ets","gitBlobOid":"<exact 40-hex blob>"}}; the key is path,
  never repositoryPath, and no other evidence fields are allowed
- limitations: at least two concrete unproved claims

Use git rev-parse HEAD:path to obtain every blob identity. Evidence paths may include direct cross-boundary dependencies when needed, but at least one must be inside the selected scope. Do not claim runtime execution, build success, compiler dataflow, device behavior, performance, an approved Oracle, or operation readiness. Do not copy secrets or generated files. Validate the JSON once, then finish.

Use at most 24 shell tool calls. Start from the declared scope evidence and
entrypoints, inspect only the direct files needed for the required dimensions, and
do not enumerate or read the whole repository. Once two or more exact blobs
support a bounded contract, stop exploring. Reserve the final two tool calls to
write program-fact-proposal.json and parse it once before finishing.
"""
    try:
        participant.turn(
            "maintainer-skill-author",
            workspace,
            prompt=prompt,
            wall_time_limit_seconds=720,
            tool_call_limit=24,
        )
    finally:
        participant.close()
        # The Agent needs a read-only view while it runs, but the evidence
        # artifact must never follow this link and copy the whole repository.
        (workspace / "source").unlink(missing_ok=True)
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
    required_dimensions = set(request.get("requiredDimensions", []))
    require(required_dimensions.issubset(SEMANTIC_DIMENSIONS) and len(required_dimensions) in (3, 4),
            "request semantic dimensions are invalid")
    require(set(proposal["dimensions"]) == required_dimensions
            and len(proposal["dimensions"]) == len(required_dimensions),
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
        inside = inside or path_is_within(path, boundary)
        clean_evidence.append({"path": path, "gitBlobOid": oid})
    require(inside, "no evidence path is inside the selected scope")
    return {
        "id": proposal["id"],
        "kind": "analysis",
        "repositoryId": proposal["repositoryId"],
        "sourceRevision": proposal["sourceRevision"],
        "scopeSkillIds": proposal["scopeSkillIds"],
        "dimensions": sorted(required_dimensions),
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
    program_bound_delta = (
        after["totals"]["programBoundCount"] - before["totals"]["programBoundCount"]
    )
    require(program_bound_delta in (0, 1),
            "proposal changed program binding for more than one scope or removed a binding")
    require(after["totals"]["semanticReadyCount"] == before["totals"]["semanticReadyCount"] + 1,
            "proposal did not advance exactly one scope to L2")
    maintenance_ready_delta = (
        after["totals"]["maintenanceReadyCount"] - before["totals"]["maintenanceReadyCount"]
    )
    require(maintenance_ready_delta in (0, 1),
            "proposal changed operation readiness for more than the selected scope or removed readiness")
    write(args.output, {
        "schema": "agentlab.maintainer_skill_agent_flywheel_result.v1",
        "automaticPromotion": False,
        "decision": "review-proposed-knowledge",
        "before": before["totals"],
        "after": after["totals"],
        "maintenanceReadyDelta": maintenance_ready_delta,
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
    p = commands.add_parser("eligible-count")
    p.add_argument("--knowledge", type=Path, required=True)
    p.add_argument("--assessment", type=Path, required=True)
    p.add_argument("--repository", required=True)
    p.set_defaults(handler=eligible_count)
    p = commands.add_parser("plan")
    p.add_argument("--knowledge", type=Path, required=True)
    p.add_argument("--assessment", type=Path, required=True)
    p.add_argument("--repository", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(handler=plan)
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
