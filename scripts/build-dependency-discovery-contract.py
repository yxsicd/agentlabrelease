#!/usr/bin/env python3
"""Build hidden dependency obligations from revision-bound program facts."""
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
TOKEN = re.compile(r"[A-Za-z0-9_.:-]+")


class ContractError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ContractError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read {label}: {error}") from error
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


def load_facts(
    path: Path, sources: dict[str, dict[str, str]]
) -> dict[str, dict[str, Any]]:
    rows = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ContractError(f"cannot read program facts: {error}") from error
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ContractError(f"program fact line {number} is invalid: {error}") from error
        require(isinstance(row, dict), f"program fact line {number} is not an object")
        fact_id = row.get("id")
        require(isinstance(fact_id, str) and fact_id and fact_id not in rows, "program fact identity is invalid")
        if row.get("kind") == "module-dependency":
            source_repository_id = row.get("sourceRepositoryId")
            target_repository_id = row.get("targetRepositoryId")
            require(
                source_repository_id in sources,
                f"{fact_id} source repository is outside the source set",
            )
            require(
                target_repository_id in sources,
                f"{fact_id} target repository is outside the source set",
            )
            source = sources[source_repository_id]
            target = sources[target_repository_id]
            require(
                row.get("sourceIdentity")
                == f"git:{source['repository']}@{source['revision']}",
                f"{fact_id} source revision differs",
            )
            require(
                row.get("targetIdentity")
                == f"git:{target['repository']}@{target['revision']}",
                f"{fact_id} target revision differs",
            )
        rows[fact_id] = row
    require(rows, "program facts are empty")
    return rows


def claim_from_fact(row: dict[str, Any]) -> dict[str, Any]:
    fact_id = row["id"]
    relation = row.get("kind")
    require(relation == "module-dependency", f"{fact_id} is not a supported dependency fact")
    target_repository = row.get("targetRepositoryId")
    require(isinstance(target_repository, str) and target_repository, f"{fact_id} target repository is absent")
    return {
        "relation": relation,
        "source": {
            "repositoryId": row["sourceRepositoryId"],
            "path": safe_path(row.get("sourcePath"), f"{fact_id} source path"),
        },
        "target": {
            "repositoryId": target_repository,
            "path": safe_path(row.get("targetPath"), f"{fact_id} target path"),
        },
        "factIds": [fact_id],
    }


def build(case_path: Path, facts_path: Path, plan_path: Path) -> dict[str, Any]:
    case = load_object(case_path, "evaluation case")
    require(case.get("schema") == "agentlab.multi_repo_evaluation_case.v1", "unsupported evaluation case")
    require(case.get("status") == "frozen-calibrated", "evaluation case is not frozen")
    source_set = case.get("sourceSetSha256")
    require(isinstance(source_set, str) and SHA256.fullmatch(source_set), "case source set is invalid")
    sources = {}
    for source in case.get("sources") or []:
        require(isinstance(source, dict), "case source is invalid")
        repository_id = source.get("id")
        revision = source.get("revision")
        repository = source.get("repository")
        require(isinstance(repository_id, str) and repository_id not in sources, "case source identity is invalid")
        require(isinstance(repository, str) and repository, "case source repository is invalid")
        require(isinstance(revision, str) and REVISION.fullmatch(revision), "case source revision is invalid")
        sources[repository_id] = {"repository": repository, "revision": revision}
    require(len(sources) >= 2, "case is not multi-repository")
    facts = load_facts(facts_path, sources)
    plan = load_object(plan_path, "dependency discovery plan")
    require(
        plan.get("schema") == "agentlab.dependency_discovery_plan.v2",
        "unsupported dependency discovery plan",
    )
    review = plan.get("review") or {}
    require(
        review.get("authority") == "explicit-dependency-plan-review",
        "dependency plan lacks explicit review authority",
    )
    require(
        review.get("verdict") == "approve-for-contract",
        "dependency plan was not approved for contract construction",
    )
    require(
        isinstance(review.get("reviewer"), str) and review["reviewer"],
        "dependency plan reviewer is absent",
    )
    require(
        isinstance(review.get("proposalSha256"), str)
        and SHA256.fullmatch(review["proposalSha256"])
        and isinstance(review.get("decisionSha256"), str)
        and SHA256.fullmatch(review["decisionSha256"]),
        "dependency plan review digests are invalid",
    )
    require(plan.get("caseId") == case.get("id"), "dependency plan case differs")
    require(plan.get("candidateId") == case.get("difficultyId"), "dependency plan candidate differs")
    require(plan.get("sourceSetSha256") == source_set, "dependency plan source set differs")
    case_lineage = case.get("lineage") or {}
    case_review = case_lineage.get("review") or {}
    require(
        plan.get("casePlanProposalSha256") == case_review.get("proposalSha256"),
        "dependency plan case-plan proposal differs",
    )
    require(
        plan.get("difficultyEvidenceSha256")
        == case_lineage.get("difficultyEvidenceSha256"),
        "dependency plan difficulty evidence differs",
    )
    require(
        plan.get("programFactsSha256") == digest(facts_path),
        "dependency plan program facts differ",
    )
    require(plan.get("automaticPromotion") is False, "dependency plan cannot auto-promote")
    case_stage_ids = [row.get("id") for row in case.get("stages") or []]
    plan_stages = plan.get("stages")
    require(isinstance(plan_stages, list) and plan_stages, "dependency plan stages are absent")
    stages = []
    seen_stages = set()
    for stage in plan_stages:
        require(isinstance(stage, dict) and set(stage) == {"stageId", "obligations"}, "dependency plan stage fields differ")
        stage_id = stage.get("stageId")
        require(stage_id in case_stage_ids and stage_id not in seen_stages, "dependency plan stage identity is invalid")
        seen_stages.add(stage_id)
        obligations = []
        seen_obligations = set()
        for obligation in stage.get("obligations") or []:
            require(isinstance(obligation, dict) and set(obligation) == {"id", "acceptedFactIds"}, f"{stage_id} obligation fields differ")
            obligation_id = obligation.get("id")
            require(isinstance(obligation_id, str) and TOKEN.fullmatch(obligation_id) and obligation_id not in seen_obligations, f"{stage_id} obligation identity is invalid")
            seen_obligations.add(obligation_id)
            fact_ids = obligation.get("acceptedFactIds")
            require(isinstance(fact_ids, list) and fact_ids and len(fact_ids) == len(set(fact_ids)), f"{obligation_id} accepted facts are invalid")
            accepted = []
            identities = set()
            for fact_id in fact_ids:
                require(fact_id in facts, f"{obligation_id} references unknown fact {fact_id}")
                claim = claim_from_fact(facts[fact_id])
                require(claim["target"]["repositoryId"] in sources, f"{fact_id} target repository is outside the source set")
                identity = json.dumps({key: claim[key] for key in ("relation", "source", "target")}, sort_keys=True)
                if identity not in identities:
                    accepted.append(claim)
                    identities.add(identity)
            obligations.append({"id": obligation_id, "acceptedClaims": accepted})
        require(obligations, f"{stage_id} has no dependency obligations")
        stages.append({"stageId": stage_id, "obligations": obligations})
    require(set(seen_stages) == set(case_stage_ids), "dependency plan must cover every case stage")
    return {
        "schema": "agentlab.dependency_discovery_contract.v1",
        "caseId": case["id"],
        "sourceSetSha256": source_set,
        "programFactsSha256": digest(facts_path),
        "obligationPlanSha256": digest(plan_path),
        "obligationPlanReview": plan.get("review"),
        "stages": stages,
        "precisionPolicy": "required-obligation-recall-only-extra-claims-unadjudicated",
        "authority": "revision-bound-program-facts-reviewed-obligation-plan",
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--program-facts", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
        value = build(args.case, args.program_facts, args.plan)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "contractSha256": digest(args.output)}, sort_keys=True))
    except (ContractError, OSError, ValueError) as error:
        print(f"dependency discovery contract invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
