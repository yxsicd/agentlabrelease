#!/usr/bin/env python3
"""Construct a review-required case-plan proposal from pinned difficulty evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


SHA256 = re.compile(r"[0-9a-f]{64}")


def load(path: Path):
    return json.loads(path.read_text())


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--difficulty", type=Path, required=True)
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    difficulty = load(args.difficulty)
    intent = load(args.intent)
    require(difficulty.get("schema") == "agentlab.difficulty_candidates.v2", "unsupported difficulty schema")
    require(intent.get("schema") == "agentlab.multi_repo_case_intent.v1", "unsupported intent schema")
    require(difficulty.get("automaticPromotion") is False, "difficulty evidence must not auto-promote")
    source_set = difficulty.get("sourceSetSha256")
    require(isinstance(source_set, str) and SHA256.fullmatch(source_set), "difficulty requires sourceSetSha256")
    require(intent.get("sourceSetSha256") == source_set, "intent source set mismatch")

    candidates = {row.get("id"): row for row in difficulty.get("candidates", []) if isinstance(row, dict)}
    candidate_id = intent.get("candidateId")
    require(candidate_id in candidates, "intent candidateId is absent from difficulty evidence")
    candidate = candidates[candidate_id]
    require(candidate.get("dimensionId") == "multi-repository-change-impact", "only recursive multi-repository impact candidates can be proposed")
    require(candidate.get("maturityState") == "candidate", "difficulty must still be a candidate")
    require(candidate.get("affectedRepositoryCount", 0) >= 2, "candidate must cross repository boundaries")
    affected = candidate.get("affectedFiles")
    require(isinstance(affected, list) and affected, "candidate has no affected files")
    allowed = sorted(
        ({"repositoryId": row.get("repositoryId"), "path": row.get("path")} for row in affected),
        key=lambda row: (row["repositoryId"], row["path"]),
    )
    require(all(row["repositoryId"] and row["path"] for row in allowed), "affected file identity is incomplete")

    stages = intent.get("stages")
    require(isinstance(stages, list) and len(stages) >= 2, "intent requires at least two stages")
    stage_ids = []
    check_ids = set()
    normalized_stages = []
    for stage in stages:
        require(isinstance(stage, dict), "stage must be an object")
        stage_id = stage.get("id")
        demand = stage.get("demand")
        checks = stage.get("checkIds")
        require(isinstance(stage_id, str) and stage_id, "stage id is required")
        require(isinstance(demand, str) and demand, "stage demand is required")
        require(isinstance(checks, list) and checks and all(isinstance(value, str) and value for value in checks), "stage checkIds are required")
        require(not check_ids.intersection(checks), "check ids must be unique across stages")
        stage_ids.append(stage_id)
        check_ids.update(checks)
        normalized_stages.append({"id": stage_id, "demand": demand, "checkIds": checks})
    require(len(stage_ids) == len(set(stage_ids)), "stage ids must be unique")

    oracle = intent.get("oracle") or {}
    require(oracle.get("authority") == "independent-executable-oracle", "intent requires an independent executable Oracle")
    require(isinstance(oracle.get("sha256"), str) and SHA256.fullmatch(oracle["sha256"]), "oracle sha256 is required")
    require(isinstance(oracle.get("receiptSchema"), str) and oracle["receiptSchema"], "oracle receipt schema is required")
    expectations = intent.get("calibrationExpectations")
    require(isinstance(expectations, dict) and {"baseline", "reference"}.issubset(expectations), "baseline and reference expectations are required")
    require(all(isinstance(value, dict) and set(value) == set(stage_ids) for value in expectations.values()), "each expectation must cover every stage")

    proposal = {
        "schema": "agentlab.multi_repo_case_plan_proposal.v1",
        "status": "review-required",
        "caseId": intent.get("caseId"),
        "candidateId": candidate_id,
        "sourceSetSha256": source_set,
        "title": intent.get("title"),
        "allowedEdits": allowed,
        "stages": normalized_stages,
        "oracle": oracle,
        "calibrationExpectations": expectations,
        "constructionEvidence": {
            "mechanism": candidate.get("mechanism"),
            "seed": candidate.get("seed"),
            "affectedRepositoryCount": candidate.get("affectedRepositoryCount"),
            "maxDependencyDepth": candidate.get("maxDependencyDepth"),
            "evidenceIds": candidate.get("evidenceIds"),
        },
        "risks": [
            {"id": "semantic-intent-unverified", "statement": "The semantic intent is supplied input, not a conclusion of dependency analysis."},
            {"id": "oracle-independence-unverified", "statement": "Oracle independence and behavior coverage require reviewer and calibration evidence."},
            {"id": "analysis-boundary", "statement": "The impact graph excludes compiler aliases, types, call targets and dataflow."},
            {"id": "runtime-gates-pending", "statement": "Harmony build, emulator UI and performance remain separate qualification gates."},
        ],
        "lineage": {"difficultyEvidenceSha256": digest(args.difficulty), "intentSha256": digest(args.intent)},
        "reviewPolicy": {
            "requiredDecisionSchema": "agentlab.multi_repo_case_plan_review.v1",
            "requiredVerdict": "approve-for-calibration",
            "mustAcknowledgeEveryRisk": True,
        },
        "automaticPromotion": False,
    }
    require(isinstance(proposal["caseId"], str) and proposal["caseId"], "caseId is required")
    require(isinstance(proposal["title"], str) and proposal["title"], "title is required")
    require(not args.output.exists(), "refusing to overwrite proposal")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proposal, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "proposalSha256": digest(args.output), "status": "review-required"}, sort_keys=True))


if __name__ == "__main__":
    main()
