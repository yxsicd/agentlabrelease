#!/usr/bin/env python3
"""Fail-closed construction readiness for retained shadow case candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


SHA256 = re.compile(r"[0-9a-f]{64}")


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def value_digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require(condition, message: str) -> None:
    if not condition:
        raise ValueError(message)


def strings(value, label: str, minimum: int = 1) -> list[str]:
    require(isinstance(value, list) and len(value) >= minimum, f"{label} is incomplete")
    require(all(isinstance(item, str) and item.strip() for item in value), f"{label} has invalid values")
    require(len(value) == len(set(value)), f"{label} contains duplicates")
    return value


def safe_path(value: str, label: str) -> str:
    path = PurePosixPath(value)
    require(value == path.as_posix() and not path.is_absolute(), f"{label} is not a safe relative path")
    require(all(part not in ("", ".", "..") for part in path.parts), f"{label} is not a safe relative path")
    return value


def within(path: str, boundary: str) -> bool:
    return path == boundary or path.startswith(boundary.rstrip("/") + "/")


def scope_owns_path(scope: dict, path: str) -> bool:
    selectors = scope.get("ownershipSelectors")
    if not selectors:
        return within(path, scope["pathBoundary"])
    return any(
        (selector.get("type") == "prefix" and within(path, selector.get("path", "")))
        or (selector.get("type") == "files" and path in selector.get("paths", []))
        for selector in selectors
    )


def validate_evidence(root: Path, evidence, label: str) -> list[dict]:
    require(isinstance(evidence, list), f"{label} evidence must be an array")
    result = []
    for offset, item in enumerate(evidence):
        require(isinstance(item, dict) and set(item) == {"path", "sha256"},
                f"{label} evidence {offset} fields differ")
        relative = safe_path(item["path"], f"{label} evidence path")
        path = root / relative
        require(path.is_file() and not path.is_symlink(), f"{label} evidence is not a regular file: {relative}")
        require(SHA256.fullmatch(item["sha256"]) is not None, f"{label} evidence digest is invalid")
        require(file_digest(path) == item["sha256"], f"{label} evidence digest differs: {relative}")
        result.append(item)
    return result


def validate_qualification(root: Path, value, label: str) -> dict:
    require(isinstance(value, dict), f"{label} must be an object")
    require(value.get("status") in ("qualified", "unqualified"), f"{label} status is invalid")
    evidence = validate_evidence(root, value.get("evidence"), label)
    require(value["status"] != "qualified" or evidence, f"{label} has no qualifying evidence")
    return {"status": value["status"], "evidence": evidence}


def assess(knowledge: Path, candidate_id: str, plan_path: Path, evidence_root: Path) -> dict:
    cut_path = knowledge / "maintainer-knowledge-cut.json"
    cut = load(cut_path)
    candidates = [row for row in rows(knowledge / "case_generation_candidates.jsonl") if row["id"] == candidate_id]
    require(len(candidates) == 1, "shadow candidate is absent or duplicated")
    candidate = candidates[0]
    plan = load(plan_path)
    require(plan.get("schema") == "agentlab.shadow_case_construction_plan.v1", "bad construction plan schema")
    require(plan.get("automaticPromotion") is False, "construction plan can auto-promote")
    require(plan.get("candidateId") == candidate_id, "construction plan candidate differs")
    candidate_sha = value_digest(candidate)
    require(plan.get("candidateSha256") == candidate_sha, "construction plan candidate digest differs")
    require(candidate.get("sourceSetSha256") == cut.get("sourceSetSha256"), "candidate source set differs")
    require(SHA256.fullmatch(candidate.get("knowledgeCutSha256", "")) is not None,
            "candidate knowledge cut digest is invalid")
    refresh_rounds = {
        row["id"]: row for row in rows(knowledge / "maintainer_skill_refresh_rounds.jsonl")
    }
    require(candidate.get("maintainerSkillRefreshRoundId") in refresh_rounds,
            "candidate Maintainer Skill refresh round is absent")

    scopes = {row["id"]: row for row in rows(knowledge / "maintainer_scope_skills.jsonl")}
    facts = {row["id"]: row for row in rows(knowledge / "program_facts.jsonl")}
    scope_rows = []
    for scope_id in strings(candidate.get("scopeSkillIds"), "candidate scopeSkillIds"):
        require(scope_id in scopes, f"unknown candidate scope Skill {scope_id}")
        scope = scopes[scope_id]
        require(scope.get("repositoryId") == candidate.get("repositoryId"), f"scope {scope_id} repository differs")
        require(scope.get("sourceRevision") == candidate.get("sourceRevision"), f"scope {scope_id} revision differs")
        scope_rows.append(scope)
    evidence_paths = set()
    for fact_id in strings(candidate.get("factIds"), "candidate factIds"):
        require(fact_id in facts, f"unknown candidate fact {fact_id}")
        fact = facts[fact_id]
        require(fact.get("repositoryId") == candidate.get("repositoryId"), f"fact {fact_id} repository differs")
        require(fact.get("sourceRevision") == candidate.get("sourceRevision"), f"fact {fact_id} revision differs")
        evidence_paths.update(
            row["path"] for row in fact.get("evidence", [])
            if isinstance(row, dict) and isinstance(row.get("path"), str)
        )

    required_fields = {
        "schema", "candidateId", "candidateSha256", "requiredImplementationPaths",
        "requiredOraclePaths", "runtimeRequirements", "oracleExecution",
        "wrongVariantCalibration", "automaticPromotion",
    }
    require(set(plan) == required_fields, "construction plan fields differ")
    editable = set(strings(candidate.get("editablePaths"), "candidate editablePaths"))
    context = set(candidate.get("contextPaths") or [])

    def path_checks(field: str, permitted: set[str], permission_name: str) -> list[dict]:
        values = plan.get(field)
        require(isinstance(values, list) and values, f"{field} is incomplete")
        seen = set()
        checks = []
        for item in values:
            require(isinstance(item, dict) and set(item) == {"path", "reason"}, f"{field} item fields differ")
            path = safe_path(item.get("path"), field)
            require(path not in seen, f"{field} duplicates {path}")
            seen.add(path)
            require(isinstance(item.get("reason"), str) and item["reason"].strip(), f"{field} reason is empty")
            in_scope = any(scope_owns_path(scope, path) for scope in scope_rows)
            checks.append({
                "path": path,
                "reason": item["reason"],
                "inCandidateScope": in_scope,
                "factEvidenceBound": path in evidence_paths,
                permission_name: path in permitted,
            })
        return checks

    implementation = path_checks("requiredImplementationPaths", editable, "editable")
    oracle_paths = path_checks("requiredOraclePaths", editable | context, "candidateVisible")

    runtime = plan.get("runtimeRequirements")
    require(isinstance(runtime, list) and runtime, "runtimeRequirements is incomplete")
    runtime_checks = []
    runtime_ids = set()
    for item in runtime:
        require(isinstance(item, dict) and set(item) == {"id", "description", "status", "evidence"},
                "runtime requirement fields differ")
        require(isinstance(item["id"], str) and item["id"] and item["id"] not in runtime_ids,
                "runtime requirement id is invalid or duplicated")
        runtime_ids.add(item["id"])
        require(isinstance(item["description"], str) and item["description"].strip(),
                "runtime requirement description is empty")
        qualification = validate_qualification(evidence_root, item, f"runtime requirement {item['id']}")
        runtime_checks.append({"id": item["id"], "description": item["description"], **qualification})

    oracle = validate_qualification(evidence_root, plan.get("oracleExecution"), "oracleExecution")
    variants = plan.get("wrongVariantCalibration")
    require(isinstance(variants, dict) and set(variants) == {"status", "evidence", "requiredCount", "executedCount"},
            "wrongVariantCalibration fields differ")
    variant_qualification = validate_qualification(evidence_root, variants, "wrongVariantCalibration")
    require(isinstance(variants["requiredCount"], int) and variants["requiredCount"] >= 2,
            "wrongVariantCalibration requiredCount is invalid")
    require(isinstance(variants["executedCount"], int) and variants["executedCount"] >= 0,
            "wrongVariantCalibration executedCount is invalid")
    require(variants["executedCount"] <= len(candidate["oracleHypothesis"]["wrongVariants"]),
            "wrongVariantCalibration executedCount exceeds the candidate variants")
    require(variants["status"] != "qualified" or variants["executedCount"] >= variants["requiredCount"],
            "wrongVariantCalibration claims qualification below the required count")

    knowledge_blockers = []
    for row in implementation:
        if not row["inCandidateScope"]:
            knowledge_blockers.append(f"implementation path escapes candidate scope: {row['path']}")
        if not row["factEvidenceBound"]:
            knowledge_blockers.append(f"implementation path is absent from bound fact evidence: {row['path']}")
        if not row["editable"]:
            knowledge_blockers.append(f"implementation path is absent from candidate editablePaths: {row['path']}")
    for row in oracle_paths:
        if not row["inCandidateScope"]:
            knowledge_blockers.append(f"Oracle path escapes candidate scope: {row['path']}")
        if not row["factEvidenceBound"]:
            knowledge_blockers.append(f"Oracle path is absent from bound fact evidence: {row['path']}")
        if not row["candidateVisible"]:
            knowledge_blockers.append(f"Oracle path is absent from candidate editable/context paths: {row['path']}")
    qualification_blockers = [
        f"runtime requirement is unqualified: {row['id']}" for row in runtime_checks if row["status"] != "qualified"
    ]
    if oracle["status"] != "qualified":
        qualification_blockers.append("independent Oracle has not executed successfully")
    if variant_qualification["status"] != "qualified":
        qualification_blockers.append(
            f"wrong-variant calibration is incomplete: {variants['executedCount']}/{variants['requiredCount']}"
        )
    if knowledge_blockers:
        decision = "blocked-knowledge-refresh"
        next_gate = "refresh-program-facts-and-shadow-candidate"
    elif qualification_blockers:
        decision = "blocked-qualification"
        next_gate = "implement-and-calibrate-independent-oracle"
    else:
        decision = "ready-for-construction"
        next_gate = "maintainer-knowledge-gate-construction"
    return {
        "schema": "agentlab.shadow_case_construction_readiness_receipt.v1",
        "candidateId": candidate_id,
        "candidateSha256": candidate_sha,
        "sourceRevision": candidate["sourceRevision"],
        "sourceSetSha256": candidate["sourceSetSha256"],
        "knowledgeCutSha256": candidate["knowledgeCutSha256"],
        "currentKnowledgeCutSha256": file_digest(cut_path),
        "planSha256": file_digest(plan_path),
        "checks": {
            "implementationPaths": implementation,
            "oraclePaths": oracle_paths,
            "runtimeRequirements": runtime_checks,
            "oracleExecution": oracle,
            "wrongVariantCalibration": {
                **variant_qualification,
                "requiredCount": variants["requiredCount"],
                "executedCount": variants["executedCount"],
            },
        },
        "knowledgeBlockers": knowledge_blockers,
        "qualificationBlockers": qualification_blockers,
        "decision": decision,
        "nextGate": next_gate,
        "automaticPromotion": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--knowledge", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.knowledge, args.candidate_id, args.plan, args.evidence_root)
    require(not args.output.exists(), "readiness output already exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
