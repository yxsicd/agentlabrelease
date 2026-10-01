#!/usr/bin/env python3
"""Refresh one existing semantic fact from a construction-readiness blocker."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import copy
import tempfile


HERE = Path(__file__).resolve().parent


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


BASE = module("agent_flywheel_base", HERE / "agent_flywheel.py")
READINESS = module("shadow_readiness", HERE / "shadow_construction_readiness.py")

INTERPRETATION_MIN = 80
INTERPRETATION_MAX = 1600
INTERPRETATION_TARGET_MIN = 400
INTERPRETATION_TARGET_MAX = 1500
LIMITATION_MIN = 40
LIMITATION_MAX = 300
PROPOSAL_FIELDS = frozenset({
    "schema", "id", "repositoryId", "sourceRevision", "scopeSkillIds", "kind",
    "dimensions", "interpretation", "evidence", "limitations",
})


def interpretation_length_to_repair(proposal: dict) -> int | None:
    """Return the invalid string length, leaving non-length schema errors to validation."""
    value = proposal.get("interpretation")
    if not isinstance(value, str):
        return None
    length = len(value)
    if INTERPRETATION_MIN <= length <= INTERPRETATION_MAX:
        return None
    return length


def proposal_repair_plan(proposal: dict) -> dict:
    missing = sorted(PROPOSAL_FIELDS - set(proposal))
    extras = sorted(set(proposal) - PROPOSAL_FIELDS) if not missing else []
    limitations = proposal.get("limitations")
    limitation_indices = []
    if isinstance(limitations, list) and len(limitations) == 2 and all(
        isinstance(value, str) for value in limitations
    ):
        limitation_indices = [index for index, value in enumerate(limitations)
                              if not LIMITATION_MIN <= len(value.strip()) <= LIMITATION_MAX]
    return {
        "interpretationLength": interpretation_length_to_repair(proposal),
        "extraFields": extras,
        "limitationIndices": limitation_indices,
    }


def validate_bounded_repair(before: dict, after: dict, plan: dict) -> int:
    BASE.require(set(after) == PROPOSAL_FIELDS,
                 "bounded repair did not produce the exact proposal fields")
    mutable = {"interpretation"} if plan["interpretationLength"] is not None else set()
    if plan["limitationIndices"]:
        mutable.add("limitations")
    for key in PROPOSAL_FIELDS - mutable:
        BASE.require(before[key] == after[key],
                     f"bounded repair changed protected field: {key}")
    if plan["limitationIndices"]:
        values = after.get("limitations")
        BASE.require(isinstance(values, list) and len(values) == 2
                     and all(isinstance(value, str)
                             and LIMITATION_MIN <= len(value.strip()) <= LIMITATION_MAX
                             for value in values), "limitations repair did not satisfy the length range")
        for index in set(range(2)) - set(plan["limitationIndices"]):
            BASE.require(values[index] == before["limitations"][index],
                         "bounded repair changed a protected limitation")
    value = after.get("interpretation")
    BASE.require(isinstance(value, str), "interpretation repair produced a non-string value")
    length = len(value)
    if plan["interpretationLength"] is not None:
        BASE.require(
            INTERPRETATION_TARGET_MIN <= length <= INTERPRETATION_TARGET_MAX,
            "interpretation repair did not satisfy the requested length range",
        )
    return length


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
        "requiredDimensions": fact["dimensions"],
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

The object must have exactly these top-level fields and no others: schema, id, repositoryId, sourceRevision, scopeSkillIds, kind, dimensions, interpretation, evidence, limitations. schema must be agentlab.maintainer_skill_fact_proposal.v1. Copy the id, repositoryId, sourceRevision, scopeSkillIds, kind and requiredDimensions from the request's existingFact, but do not copy its derived agentProposal field. Preserve every existing evidence path and add exact Git Blob evidence for every required path: {json.dumps(required)}. Include exactly the union of those paths, with no extras. Update interpretation so it accurately covers the complete implementation/Oracle source surface, and retain exactly two concrete limitations without claiming build, emulator, Oracle, or operation success. Evidence objects contain only path and exact 40-hex gitBlobOid obtained with git rev-parse HEAD:path. Do not add unrelated paths, secrets, generated files, runtime claims, a gold patch, or automatic-promotion fields. Parse the completed JSON once, then finish.

The interpretation is a bounded maintenance contract: it must contain {INTERPRETATION_TARGET_MIN}-{INTERPRETATION_TARGET_MAX} Unicode characters and must never exceed {INTERPRETATION_MAX}. Put detailed uncertainty in limitations rather than expanding interpretation.
Each of the exactly two limitations must contain {LIMITATION_MIN}-{LIMITATION_MAX} Unicode characters after trimming whitespace. Keep uncertainty concrete and do not claim unexecuted validation.
"""
    try:
        participant.turn("maintainer-skill-focused-refresh", workspace, prompt=prompt,
                         wall_time_limit_seconds=720)
        proposal = workspace / "program-fact-proposal.json"
        BASE.require(proposal.is_file() and not proposal.is_symlink(),
                     "Agent did not produce a refresh proposal")
        proposed = BASE.load(proposal)
        repair_plan = proposal_repair_plan(proposed)
        if (repair_plan["interpretationLength"] is not None or repair_plan["extraFields"]
                or repair_plan["limitationIndices"]):
            before_repair = args.output / "pre-repair-program-fact-proposal.json"
            shutil.copy2(proposal, before_repair)
            length_instruction = (
                f"Rewrite interpretation from {repair_plan['interpretationLength']} to "
                f"{INTERPRETATION_TARGET_MIN}-{INTERPRETATION_TARGET_MAX} Unicode characters while preserving "
                "its evidence-backed responsibility, boundary, relations, behavior, and uncertainty."
                if repair_plan["interpretationLength"] is not None
                else "Keep interpretation exactly unchanged."
            )
            repair_prompt = f"""Apply one bounded shape repair to program-fact-proposal.json.
{length_instruction}
Remove only these unsupported top-level fields: {json.dumps(repair_plan['extraFields'])}.
Rewrite only these zero-based limitation indices: {json.dumps(repair_plan['limitationIndices'])}, each to {LIMITATION_MIN}-{LIMITATION_MAX} Unicode characters after trimming whitespace. Preserve their concrete uncertainty and lack of runtime verification; retain exactly two strings. Keep every other limitation byte-for-byte unchanged.
The final object must contain exactly: {json.dumps(sorted(PROPOSAL_FIELDS))}. Keep every protected field and value exactly unchanged. Parse the JSON once, verify the field names and interpretation length, then finish. Do not inspect or modify source/.
"""
            participant.turn(
                "maintainer-skill-focused-refresh-interpretation-repair",
                workspace,
                prompt=repair_prompt,
                wall_time_limit_seconds=360,
            )
            repaired = BASE.load(proposal)
            repaired_length = validate_bounded_repair(proposed, repaired, repair_plan)
            BASE.write(args.output / "bounded-repair-receipt.json", {
                "schema": "agentlab.maintainer_skill_bounded_repair_receipt.v1",
                "automaticPromotion": False,
                "changedFields": (["interpretation"]
                                  if repair_plan["interpretationLength"] is not None else [])
                                 + (["limitations"] if repair_plan["limitationIndices"] else []),
                "repairedLimitationIndices": repair_plan["limitationIndices"],
                "beforeLimitationLengths": ([len(value.strip()) for value in proposed["limitations"]]
                                            if repair_plan["limitationIndices"] else None),
                "afterLimitationLengths": ([len(value.strip()) for value in repaired["limitations"]]
                                           if repair_plan["limitationIndices"] else None),
                "removedFields": repair_plan["extraFields"],
                "beforeLength": (len(proposed["interpretation"])
                                 if isinstance(proposed.get("interpretation"), str) else None),
                "afterLength": repaired_length,
                "beforeSha256": BASE.digest(before_repair),
                "afterSha256": BASE.digest(proposal),
                "decision": "accepted-bounded-agent-repair-for-validation",
            })
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
    existing = READINESS.rows(args.program_facts)
    old = request["existingFact"]
    old_paths = {row["path"] for row in old["evidence"]}
    required_paths = {
        item["path"]
        for field in ("requiredImplementationPaths", "requiredOraclePaths")
        for item in request[field]
    }
    BASE.require(request.get("requiredDimensions") == old.get("dimensions"),
                 "focused request dimensions differ from the existing fact")
    BASE.require(sum(row["id"] == old["id"] for row in existing) == 1,
                 "existing fact is absent or duplicated")
    current = next(row for row in existing if row["id"] == old["id"])
    BASE.require(READINESS.value_digest(current) == READINESS.value_digest(old),
                 "focused refresh baseline fact changed after request preparation")
    fact = BASE.validate_proposal(request, proposal, args.source.resolve(strict=True),
                                  expected_evidence_paths=old_paths | required_paths)
    BASE.require(fact["id"] == old["id"], "focused refresh changed fact identity")
    new_paths = {row["path"] for row in fact["evidence"]}
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


def rebind_candidate(args) -> None:
    """Compatibility command: derive a successor, never rewrite its parent."""
    knowledge = args.knowledge
    BASE.require(not args.output.exists(), "successor receipt already exists")
    candidates_path = knowledge / "case_generation_candidates.jsonl"
    original_candidates_bytes = candidates_path.read_bytes()
    original_plan_bytes = args.plan.read_bytes()
    facts = {row["id"]: row for row in READINESS.rows(knowledge / "program_facts.jsonl")}
    candidates = READINESS.rows(candidates_path)
    matches = [row for row in candidates if row["id"] == args.candidate_id]
    BASE.require(len(matches) == 1, "focused candidate is absent or duplicated")
    before = matches[0]
    BASE.require(before.get("status") == "shadow-proposal" and before.get("automaticPromotion") is False,
                 "only non-promoted shadow parents can derive a successor")
    refresh = BASE.load(args.focused_receipt)
    fact_id = refresh.get("acceptedFactId")
    BASE.require(refresh.get("changeKind") == "updated" and fact_id in facts,
                 "focused receipt does not identify an updated fact")
    fact = facts[fact_id]
    BASE.require(refresh.get("candidateId") == before["id"], "refresh receipt candidate differs")
    BASE.require(refresh.get("acceptedFactSha256") == READINESS.value_digest(fact),
                 "refresh receipt accepted fact digest differs")
    BASE.require(before.get("factIds") == [fact_id], "candidate fact binding differs")
    BASE.require(before.get("scopeSkillIds") == fact.get("scopeSkillIds"),
                 "candidate scope binding differs")
    BASE.require(before.get("repositoryId") == fact.get("repositoryId")
                 and before.get("sourceRevision") == fact.get("sourceRevision"),
                 "candidate source binding differs")
    plan = BASE.load(args.plan)
    BASE.require(plan.get("candidateId") == args.candidate_id, "construction plan candidate differs")
    BASE.require(plan.get("candidateSha256") == READINESS.value_digest(before),
                 "parent construction plan digest differs")
    evidence_paths = {row["path"] for row in fact.get("evidence", [])}
    implementation_paths = [row["path"] for row in plan["requiredImplementationPaths"]]
    oracle_paths = [row["path"] for row in plan["requiredOraclePaths"]]
    BASE.require(set(implementation_paths + oracle_paths).issubset(evidence_paths),
                 "refreshed fact still omits construction paths")

    editable = list(dict.fromkeys([*before["editablePaths"], *implementation_paths]))
    context = [
        path for path in dict.fromkeys([*before.get("contextPaths", []), *oracle_paths])
        if path not in editable
    ]
    BASE.require(set(editable + context).issubset(evidence_paths),
                 "candidate rebind exposes paths outside refreshed fact evidence")
    limitations = fact.get("limitations")
    BASE.require(isinstance(limitations, list) and len(limitations) >= 2,
                 "refreshed fact has insufficient limitations")
    rounds = READINESS.rows(knowledge / "maintainer_skill_refresh_rounds.jsonl")
    latest = max(rounds, key=lambda row: row["roundIndex"])
    cut = BASE.load(knowledge / "maintainer-knowledge-cut.json")
    BASE.require(before["sourceSetSha256"] == cut["sourceSetSha256"], "source set changed")
    fact_table = cut.get("tables", {}).get("programFacts", {})
    BASE.require(fact_table.get("path") == "program_facts.jsonl"
                 and fact_table.get("sha256") == BASE.digest(knowledge / "program_facts.jsonl"),
                 "refreshed facts are not bound to the current exported knowledge cut")
    parent_sha = READINESS.value_digest(before)
    cut_sha = BASE.digest(knowledge / "maintainer-knowledge-cut.json")
    fact_sha = READINESS.value_digest(fact)
    refresh_sha = BASE.digest(args.focused_receipt)
    successor_id = "shadow-case-refresh-" + READINESS.value_digest(
        {"parent": parent_sha, "cut": cut_sha, "fact": fact_sha, "refresh": refresh_sha}
    )[:32]
    lineage = dict(before.get("lineage") or {})
    lineage.update({"focusedRefreshReceiptSha256": refresh_sha,
                    "parentCandidateId": before["id"], "parentCandidateSha256": parent_sha,
                    "parentKnowledgeCutSha256": before["knowledgeCutSha256"],
                    "refreshedFactSha256": fact_sha})
    after = {
        **before,
        "id": successor_id,
        "editablePaths": editable,
        "contextPaths": context,
        "limitations": limitations,
        "knowledgeCutSha256": cut_sha,
        "maintainerSkillRefreshRoundId": latest["id"],
        "lineage": lineage,
    }
    successor_plan = copy.deepcopy(plan)
    successor_plan["candidateId"] = successor_id
    successor_plan["candidateSha256"] = READINESS.value_digest(after)
    # Old receipts bind the parent identity, never the successor.
    for requirement in successor_plan["runtimeRequirements"]:
        requirement.update({"status": "unqualified", "evidence": []})
    for field in ("oracleExecution", "wrongVariantCalibration"):
        successor_plan[field].update({"status": "unqualified", "evidence": []})
    successor_plan["wrongVariantCalibration"]["executedCount"] = 0
    successor_plan_path = knowledge / "construction-plans" / (successor_id + ".json")
    existing_successors = [row for row in candidates if row["id"] == successor_id]
    BASE.require(len(existing_successors) <= 1, "successor identity is duplicated")
    if existing_successors:
        BASE.require(existing_successors[0] == after and successor_plan_path.is_file()
                     and BASE.load(successor_plan_path) == successor_plan,
                     "successor conflicts with retained history")
    else:
        BASE.require(not successor_plan_path.exists()
                     or (successor_plan_path.is_file() and BASE.load(successor_plan_path) == successor_plan),
                     "successor plan conflicts with interrupted publication")
    appended = candidates if existing_successors else [*candidates, after]
    encoded = b"".join(READINESS.canonical(row) + b"\n"
                       for row in sorted(appended, key=lambda row: row["id"]))
    # Validate in an isolated projection before changing any retained input.
    with tempfile.TemporaryDirectory(prefix="agentlab-successor-check-") as directory:
        trial = Path(directory) / "knowledge"
        shutil.copytree(knowledge, trial)
        (trial / candidates_path.name).write_bytes(encoded)
        trial_plan = trial / "construction-plans" / successor_plan_path.name
        BASE.write(trial_plan, successor_plan)
        readiness = READINESS.assess(trial, successor_id, trial_plan, args.evidence_root)
    BASE.require(readiness["decision"] == "blocked-qualification",
                 "successor did not clear only the knowledge blockers")
    BASE.require(candidates_path.read_bytes() == original_candidates_bytes
                 and args.plan.read_bytes() == original_plan_bytes
                 and BASE.digest(knowledge / "maintainer-knowledge-cut.json") == cut_sha
                 and BASE.digest(knowledge / "program_facts.jsonl") == fact_table["sha256"],
                 "successor inputs changed during validation")
    if not existing_successors:
        if not successor_plan_path.exists():
            BASE.write(successor_plan_path, successor_plan)
        candidates_path.write_bytes(encoded)
    BASE.write(args.output, {
        "schema": "agentlab.focused_candidate_successor_receipt.v1",
        "automaticPromotion": False,
        "candidateId": successor_id,
        "parentCandidateId": args.candidate_id,
        "parentPreserved": True,
        "parentPlanPreserved": True,
        "unchangedRepeat": bool(existing_successors),
        "successorPlan": str(successor_plan_path.relative_to(knowledge)),
        "beforeSha256": parent_sha,
        "afterSha256": READINESS.value_digest(after),
        "focusedRefreshReceiptSha256": BASE.digest(args.focused_receipt),
        "knowledgeCutSha256": after["knowledgeCutSha256"],
        "maintainerSkillRefreshRoundId": latest["id"],
        "addedEditablePaths": sorted(set(editable) - set(before["editablePaths"])),
        "addedContextPaths": sorted(set(context) - set(before.get("contextPaths", []))),
        "readinessDecision": readiness["decision"],
        "nextGate": readiness["nextGate"],
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
    p = commands.add_parser("rebind-candidate")
    p.add_argument("--knowledge", type=Path, required=True); p.add_argument("--candidate-id", required=True)
    p.add_argument("--plan", type=Path, required=True); p.add_argument("--focused-receipt", type=Path, required=True)
    p.add_argument("--evidence-root", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    p.set_defaults(handler=rebind_candidate)
    p = commands.add_parser("compare")
    p.add_argument("--before", type=Path, required=True); p.add_argument("--after", type=Path, required=True)
    p.add_argument("--scope-id", required=True); p.add_argument("--output", type=Path, required=True)
    p.set_defaults(handler=compare)
    args = parser.parse_args(); args.handler(args)


if __name__ == "__main__":
    main()
