#!/usr/bin/env python3
"""Freeze one independently calibrated case from multi-repository difficulty evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


def load(path: Path):
    return json.loads(path.read_text())


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_sources(sources):
    require(isinstance(sources, list) and len(sources) >= 2, "at least two pinned sources are required")
    ids = []
    for source in sources:
        require(isinstance(source, dict), "source must be an object")
        require(isinstance(source.get("id"), str) and source["id"], "source id is required")
        require(isinstance(source.get("repository"), str) and source["repository"], "source repository is required")
        require(isinstance(source.get("revision"), str) and REVISION.fullmatch(source["revision"]), "source revision must be exact")
        ids.append(source["id"])
    require(len(ids) == len(set(ids)), "source ids must be unique")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--difficulty", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--construction-quality", type=Path)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    difficulty = load(args.difficulty)
    plan = load(args.plan)
    calibration = load(args.calibration)
    require(difficulty.get("schema") == "agentlab.difficulty_candidates.v2", "unsupported difficulty schema")
    require(plan.get("schema") in {"agentlab.multi_repo_case_plan.v1", "agentlab.multi_repo_case_plan.v2"}, "unsupported case plan schema")
    require(calibration.get("schema") == "agentlab.multi_repo_calibration.v1", "unsupported calibration schema")
    if plan.get("schema") == "agentlab.multi_repo_case_plan.v2":
        review = plan.get("review") or {}
        require(review.get("authority") == "explicit-proposal-review", "v2 plan requires explicit proposal review")
        require(review.get("verdict") == "approve-for-calibration", "v2 plan was not approved for calibration")
        require(isinstance(review.get("reviewer"), str) and review["reviewer"], "v2 plan reviewer is required")
        require(plan.get("automaticPromotion") is False, "v2 plan must not auto-promote")
        require(args.proposal is not None and args.review is not None, "v2 plan requires proposal and review evidence")
        proposal = load(args.proposal)
        decision = load(args.review)
        require(proposal.get("schema") == "agentlab.multi_repo_case_plan_proposal.v1", "unsupported proposal evidence")
        require(decision.get("schema") == "agentlab.multi_repo_case_plan_review.v1", "unsupported review evidence")
        require(digest(args.proposal) == review.get("proposalSha256") == decision.get("proposalSha256"), "proposal evidence digest mismatch")
        require(digest(args.review) == review.get("decisionSha256"), "review evidence digest mismatch")
        require(decision.get("verdict") == review.get("verdict"), "review verdict mismatch")
        require(decision.get("reviewer") == review.get("reviewer"), "reviewer mismatch")
        require(sorted(decision.get("acknowledgedRiskIds", [])) == review.get("acknowledgedRiskIds"), "review risk acknowledgements mismatch")
        reviewed_fields = ("caseId", "candidateId", "sourceSetSha256", "title", "allowedEdits", "stages", "oracle", "calibrationExpectations", "construction", "constructionQuality")
        require(all(plan.get(key) == proposal.get(key) for key in reviewed_fields), "v2 plan differs from reviewed proposal")
        if plan.get("construction") is not None:
            require(args.construction_quality is not None, "constructed v2 plan requires construction quality evidence")
            quality = load(args.construction_quality)
            quality_summary = plan.get("constructionQuality") or {}
            require(quality.get("schema") == "agentlab.multi_repo_intent_quality.v1", "unsupported construction quality evidence")
            require(quality.get("qualifiedForReview") is True and quality_summary.get("qualifiedForReview") is True, "construction intent did not qualify for review")
            require(digest(args.construction_quality) == quality_summary.get("reportSha256"), "construction quality evidence digest mismatch")
            require(quality.get("candidateId") == plan.get("candidateId") and quality.get("sourceSetSha256") == plan.get("sourceSetSha256"), "construction quality lineage mismatch")
            require(quality.get("constructionReceiptSha256") == (plan.get("construction") or {}).get("receiptSha256"), "construction quality receipt mismatch")
            require((quality.get("policy") or {}).get("automaticPromotion") is False, "construction quality must not auto-promote")
        else:
            require(args.construction_quality is None, "construction quality evidence requires constructed plan")
    else:
        require(args.proposal is None and args.review is None and args.construction_quality is None, "proposal, review and construction quality evidence require a v2 plan")
    source_set = difficulty.get("sourceSetSha256")
    require(isinstance(source_set, str) and SHA256.fullmatch(source_set), "difficulty requires sourceSetSha256")
    validate_sources(difficulty.get("sources"))
    require(difficulty.get("automaticPromotion") is False, "difficulty evidence must not auto-promote")

    candidate_id = plan.get("candidateId")
    candidates = {
        row.get("id"): row
        for row in difficulty.get("candidates", [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    require(candidate_id in candidates, "plan candidateId is absent from difficulty evidence")
    candidate = candidates[candidate_id]
    require(candidate.get("maturityState") == "candidate", "difficulty must still be a candidate")
    require((candidate.get("verificationContract") or {}).get("caseReady") is False, "difficulty is already marked case-ready")
    require(plan.get("sourceSetSha256") == source_set, "plan source set mismatch")

    case_id = plan.get("caseId")
    title = plan.get("title")
    require(isinstance(case_id, str) and case_id, "caseId is required")
    require(isinstance(title, str) and title, "title is required")
    stages = plan.get("stages")
    require(isinstance(stages, list) and len(stages) >= 2, "at least two task stages are required")
    stage_ids = []
    all_checks = set()
    for stage in stages:
        require(isinstance(stage, dict), "stage must be an object")
        stage_id = stage.get("id")
        demand = stage.get("demand")
        checks = stage.get("checkIds")
        require(isinstance(stage_id, str) and stage_id, "stage id is required")
        require(isinstance(demand, str) and demand, "stage demand is required")
        require(isinstance(checks, list) and checks and all(isinstance(value, str) and value for value in checks), "stage checkIds are required")
        require(not all_checks.intersection(checks), "check ids must be unique across stages")
        stage_ids.append(stage_id)
        all_checks.update(checks)
    require(len(stage_ids) == len(set(stage_ids)), "stage ids must be unique")

    affected = {
        (row.get("repositoryId"), row.get("path"))
        for row in candidate.get("affectedFiles", [])
        if isinstance(row, dict)
    }
    allowed = plan.get("allowedEdits")
    require(isinstance(allowed, list) and allowed, "allowedEdits are required")
    for edit in allowed:
        identity = (edit.get("repositoryId"), edit.get("path")) if isinstance(edit, dict) else None
        require(identity in affected, f"allowed edit {identity!r} is outside the analyzed impact surface")

    oracle = plan.get("oracle") or {}
    oracle_digest = oracle.get("sha256")
    require(isinstance(oracle_digest, str) and SHA256.fullmatch(oracle_digest), "oracle sha256 is required")
    require(oracle.get("authority") == "independent-executable-oracle", "oracle must be independently executable")
    require(isinstance(oracle.get("receiptSchema"), str) and oracle["receiptSchema"], "oracle receipt schema is required")
    require(calibration.get("candidateId") == candidate_id, "calibration candidate mismatch")
    require(calibration.get("sourceSetSha256") == source_set, "calibration source set mismatch")
    require(calibration.get("oracleSha256") == oracle_digest, "calibration oracle mismatch")
    require(calibration.get("receiptSchema") == oracle["receiptSchema"], "calibration receipt schema mismatch")
    require(calibration.get("infrastructureAvailable") is True, "calibration infrastructure was unavailable")

    expectations = plan.get("calibrationExpectations")
    results = calibration.get("variants")
    require(isinstance(expectations, dict) and len(expectations) >= 3, "baseline, reference and wrong variants are required")
    require(isinstance(results, dict) and set(results) == set(expectations), "calibration variants do not match plan")
    require("baseline" in expectations and "reference" in expectations, "baseline and reference variants are required")
    cumulative_checks = {}
    seen_checks = []
    for stage in stages:
        seen_checks.extend(stage["checkIds"])
        cumulative_checks[stage["id"]] = set(seen_checks)
    for variant, expected_stages in expectations.items():
        require(isinstance(expected_stages, dict) and set(expected_stages) == set(stage_ids), f"variant {variant} must cover every stage")
        actual = results[variant].get("stages") if isinstance(results[variant], dict) else None
        require(isinstance(actual, dict) and set(actual) == set(stage_ids), f"variant {variant} calibration is incomplete")
        for stage_id in stage_ids:
            require(isinstance(expected_stages[stage_id], bool), "expected calibration verdict must be boolean")
            require(actual[stage_id].get("pass") is expected_stages[stage_id], f"calibration mismatch for {variant}/{stage_id}")
            require(isinstance(actual[stage_id].get("receiptSha256"), str) and SHA256.fullmatch(actual[stage_id]["receiptSha256"]), "calibration receipt digest is required")
            actual_checks = actual[stage_id].get("checkIds")
            require(isinstance(actual_checks, list) and set(actual_checks) == cumulative_checks[stage_id], f"oracle checks do not match plan for {variant}/{stage_id}")
            require(actual[stage_id].get("checkCount") == len(actual_checks), "oracle check count mismatch")
    require(all(expectations["reference"].values()), "reference must pass every stage")
    require(not all(expectations["baseline"].values()), "baseline must fail at least one stage")
    wrong_variants = [name for name in expectations if name not in {"baseline", "reference"}]
    require(wrong_variants and all(not all(expectations[name].values()) for name in wrong_variants), "every wrong variant must fail at least one stage")
    require(any(any(expectations[name].values()) and not all(expectations[name].values()) for name in wrong_variants), "at least one wrong variant must cross an earlier stage and fail a later stage")

    plan_sha256 = digest(args.plan)
    calibration_sha256 = digest(args.calibration)
    output = {
        "schema": "agentlab.multi_repo_evaluation_case.v1",
        "id": case_id,
        "kind": "task",
        "assetClass": "reusable-knowledge",
        "status": "frozen-calibrated",
        "title": title,
        "difficultyId": candidate_id,
        "sourceSetSha256": source_set,
        "sources": difficulty["sources"],
        "allowedEdits": allowed,
        "stages": stages,
        "oracle": {
            "sha256": oracle_digest,
            "authority": oracle["authority"],
            "receiptSchema": oracle.get("receiptSchema"),
            "checkIds": sorted(all_checks),
        },
        "calibration": {
            "qualified": True,
            "summarySha256": calibration_sha256,
            "expectations": expectations,
            "variantSourceSha256": {
                name: row.get("sourceSha256") for name, row in results.items()
            },
        },
        "construction": plan.get("construction"),
        "constructionQuality": plan.get("constructionQuality"),
        "lineage": {
            "difficultyEvidenceSha256": digest(args.difficulty),
            "planSha256": plan_sha256,
            "calibrationSha256": calibration_sha256,
        },
        "automaticPromotion": False,
        "assessmentBoundary": "Exact pinned source set and executable fixture oracle; Harmony build, emulator rendering and device performance remain separate gates.",
    }
    require(not args.output.exists(), "refusing to overwrite frozen case")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "caseId": case_id, "stages": len(stages), "variants": len(results), "outputSha256": digest(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
