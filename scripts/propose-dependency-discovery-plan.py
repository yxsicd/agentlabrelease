#!/usr/bin/env python3
"""Propose stage dependency obligations from recursive analyzer evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


class ProposalError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ProposalError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProposalError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def safe_path(value: Any, label: str) -> str:
    require(isinstance(value, str) and value and "\\" not in value, f"{label} is invalid")
    path = PurePosixPath(value)
    require(
        not path.is_absolute()
        and all(part not in ("", ".", "..") for part in path.parts)
        and path.as_posix() == value,
        f"{label} is unsafe",
    )
    return value


def load_fact_index(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ProposalError(f"cannot read program facts: {error}") from error
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ProposalError(f"program fact line {number} is invalid: {error}") from error
        require(isinstance(row, dict), f"program fact line {number} is not an object")
        fact_id = row.get("id")
        require(isinstance(fact_id, str) and fact_id and fact_id not in rows, "program fact identity is invalid")
        rows[fact_id] = row
    require(rows, "program facts are empty")
    return rows


def propose(
    proposal_path: Path, difficulty_path: Path, facts_path: Path
) -> dict[str, Any]:
    case = load_object(proposal_path, "case-plan proposal")
    difficulty = load_object(difficulty_path, "difficulty evidence")
    require(
        case.get("schema") == "agentlab.multi_repo_case_plan_proposal.v1",
        "unsupported case-plan proposal",
    )
    require(case.get("status") == "review-required", "case-plan proposal is not review-required")
    require(case.get("automaticPromotion") is False, "case-plan proposal can auto-promote")
    require(difficulty.get("schema") == "agentlab.difficulty_candidates.v2", "unsupported difficulty evidence")
    source_set = case.get("sourceSetSha256")
    require(isinstance(source_set, str) and SHA256.fullmatch(source_set), "case source set is invalid")
    require(difficulty.get("sourceSetSha256") == source_set, "difficulty source set differs")
    sources: dict[str, dict[str, str]] = {}
    for row in difficulty.get("sources") or []:
        require(isinstance(row, dict), "difficulty source is invalid")
        repository_id = row.get("id")
        repository = row.get("repository")
        revision = row.get("revision")
        require(isinstance(repository_id, str) and repository_id not in sources, "source identity is invalid")
        require(isinstance(repository, str) and repository, "source repository is invalid")
        require(isinstance(revision, str) and REVISION.fullmatch(revision), "source revision is invalid")
        sources[repository_id] = {"repository": repository, "revision": revision}
    require(len(sources) >= 2, "proposal is not multi-repository")
    candidates = {
        row.get("id"): row
        for row in difficulty.get("candidates") or []
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    candidate_id = case.get("candidateId")
    require(candidate_id in candidates, "case candidate is absent from difficulty evidence")
    candidate = candidates[candidate_id]
    require(
        candidate.get("dimensionId") == "multi-repository-change-impact",
        "candidate is not recursive multi-repository impact",
    )
    require(candidate.get("maturityState") == "candidate", "candidate was already promoted")
    facts = load_fact_index(facts_path)
    affected_depths: dict[tuple[str, str], int] = {}
    for row in candidate.get("affectedFiles") or []:
        require(isinstance(row, dict), "affected file is invalid")
        repository_id = row.get("repositoryId")
        path = safe_path(row.get("path"), "affected path")
        depth = row.get("dependencyDepth")
        require(repository_id in sources, "affected repository is outside source set")
        require(isinstance(depth, int) and depth >= 0, "affected dependency depth is invalid")
        affected_depths[(repository_id, path)] = depth
    require(affected_depths, "candidate has no affected files")
    grouped: dict[int, list[str]] = {}
    evidence_ids = candidate.get("evidenceIds")
    require(isinstance(evidence_ids, list) and evidence_ids, "candidate has no dependency evidence")
    require(len(evidence_ids) == len(set(evidence_ids)), "candidate dependency evidence is duplicated")
    for fact_id in evidence_ids:
        require(fact_id in facts, f"candidate references unknown fact {fact_id}")
        fact = facts[fact_id]
        require(fact.get("kind") == "module-dependency", f"{fact_id} is not a module dependency")
        source_id = fact.get("sourceRepositoryId")
        target_id = fact.get("targetRepositoryId")
        source_path = safe_path(fact.get("sourcePath"), f"{fact_id} source path")
        target_path = safe_path(fact.get("targetPath"), f"{fact_id} target path")
        require(source_id in sources and target_id in sources, f"{fact_id} crosses outside the source set")
        require(
            fact.get("sourceIdentity")
            == f"git:{sources[source_id]['repository']}@{sources[source_id]['revision']}",
            f"{fact_id} source identity differs",
        )
        require(
            fact.get("targetIdentity")
            == f"git:{sources[target_id]['repository']}@{sources[target_id]['revision']}",
            f"{fact_id} target identity differs",
        )
        source_depth = affected_depths.get((source_id, source_path))
        target_depth = affected_depths.get((target_id, target_path))
        require(source_depth is not None and target_depth is not None, f"{fact_id} is outside affected files")
        require(source_depth == target_depth + 1, f"{fact_id} is not one recursive depth step")
        grouped.setdefault(source_depth, []).append(fact_id)
    stages = case.get("stages")
    require(isinstance(stages, list) and stages, "case stages are absent")
    depths = sorted(grouped)
    require(
        len(depths) == len(stages),
        "recursive dependency depths do not map one-to-one to case stages",
    )
    planned_stages = []
    for stage, depth in zip(stages, depths):
        stage_id = stage.get("id") if isinstance(stage, dict) else None
        require(isinstance(stage_id, str) and stage_id, "case stage identity is invalid")
        obligations = [
            {
                "id": f"recursive-depth-{depth}-edge-{index}",
                "acceptedFactIds": [fact_id],
            }
            for index, fact_id in enumerate(sorted(grouped[depth]), 1)
        ]
        planned_stages.append({"stageId": stage_id, "obligations": obligations})
    return {
        "schema": "agentlab.dependency_discovery_plan_proposal.v1",
        "status": "review-required",
        "caseId": case["caseId"],
        "candidateId": candidate_id,
        "sourceSetSha256": source_set,
        "casePlanProposalSha256": digest(proposal_path),
        "difficultyEvidenceSha256": digest(difficulty_path),
        "programFactsSha256": digest(facts_path),
        "derivation": "candidate-module-dependency-evidence-grouped-by-recursive-depth",
        "stages": planned_stages,
        "risks": [
            {
                "id": "dependency-obligation-fairness",
                "statement": "Reviewer must confirm every hidden dependency obligation is reasonably inferable from participant-visible source.",
            },
            {
                "id": "dependency-route-completeness",
                "statement": "Analyzer evidence may omit legitimate alternative dependency routes; extra participant claims remain unadjudicated.",
            },
        ],
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-plan-proposal", type=Path, required=True)
    parser.add_argument("--difficulty", type=Path, required=True)
    parser.add_argument("--program-facts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
        value = propose(args.case_plan_proposal, args.difficulty, args.program_facts)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "proposalSha256": digest(args.output)}, sort_keys=True))
    except (ProposalError, OSError, ValueError) as error:
        print(f"dependency discovery plan proposal invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
