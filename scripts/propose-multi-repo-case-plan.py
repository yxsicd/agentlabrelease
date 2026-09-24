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
    parser.add_argument("--construction-receipt", type=Path)
    parser.add_argument("--quality-report", type=Path)
    parser.add_argument("--feedback-analysis-cut", type=Path)
    parser.add_argument("--feedback-cut-proposal", type=Path)
    parser.add_argument("--feedback-cut-review", type=Path)
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
    construction = intent.get("construction")
    if construction is not None:
        require(args.construction_receipt is not None and args.quality_report is not None, "constructed intent requires construction receipt and quality report")
        construction_receipt = load(args.construction_receipt)
        quality = load(args.quality_report)
        require(construction_receipt.get("schema") == "agentlab.multi_repo_intent_construction_receipt.v1", "unsupported construction receipt schema")
        require(digest(args.construction_receipt) == construction.get("receiptSha256"), "construction receipt digest mismatch")
        require(construction_receipt.get("status") == construction.get("status") == "candidate-unverified", "construction must remain an unverified candidate")
        require(construction_receipt.get("participantId") == construction.get("participantId"), "construction participant mismatch")
        require(construction_receipt.get("sourceSetSha256") == source_set, "construction source set mismatch")
        require(construction_receipt.get("candidateId") == intent.get("candidateId"), "construction candidate mismatch")
        require(construction_receipt.get("semanticKnowledgeVerified") is False and construction.get("semanticKnowledgeVerified") is False, "construction must not claim verified semantics")
        require(construction_receipt.get("automaticPromotion") is False and construction.get("automaticPromotion") is False, "construction must not auto-promote")
        require(quality.get("schema") == "agentlab.multi_repo_intent_quality.v1", "unsupported construction quality schema")
        require(quality.get("qualifiedForReview") is True, "construction intent did not qualify for review")
        require(quality.get("intentSha256") == digest(args.intent), "construction quality intent mismatch")
        require(quality.get("constructionReceiptSha256") == digest(args.construction_receipt), "construction quality receipt mismatch")
        require(quality.get("candidateId") == intent.get("candidateId") and quality.get("sourceSetSha256") == source_set, "construction quality lineage mismatch")
        require((quality.get("policy") or {}).get("automaticPromotion") is False, "construction quality must not auto-promote")
        construction_quality = {
            "qualifiedForReview": True,
            "reportSha256": digest(args.quality_report),
            "policy": quality.get("policy"),
        }
    else:
        require(args.construction_receipt is None and args.quality_report is None, "construction evidence requires constructed intent")
        construction_quality = None

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

    feedback_analysis_cut = None
    if args.feedback_analysis_cut is not None:
        require(args.feedback_cut_proposal is not None and args.feedback_cut_review is not None, "reviewed feedback cut requires proposal and review evidence")
        reviewed_cut = load(args.feedback_analysis_cut)
        cut_proposal = load(args.feedback_cut_proposal)
        cut_decision = load(args.feedback_cut_review)
        require(reviewed_cut.get("schema") == "agentlab.feedback_analysis_cut.v1", "unsupported feedback analysis cut schema")
        require(reviewed_cut.get("status") == "reviewed-for-case-construction", "feedback analysis cut is not reviewed for construction")
        require(reviewed_cut.get("automaticPromotion") is False, "feedback analysis cut must not auto-promote")
        require(cut_proposal.get("schema") == "agentlab.feedback_analysis_cut_proposal.v1", "unsupported feedback cut proposal evidence")
        require(cut_decision.get("schema") == "agentlab.feedback_analysis_cut_review.v1", "unsupported feedback cut review evidence")
        require(cut_proposal.get("status") == "review-required" and cut_proposal.get("automaticPromotion") is False, "feedback cut proposal is not review-required")
        require(cut_decision.get("automaticPromotion") is False, "feedback cut review must not auto-promote")
        require((reviewed_cut.get("priorCase") or {}).get("immutability") == "retained-unchanged", "feedback analysis cut does not preserve its prior case")
        require(all(reviewed_cut.get(key) == cut_proposal.get(key) for key in ("cutId", "priorCase", "feedback", "nextAnalysis", "change")), "reviewed feedback cut differs from its proposal")
        next_analysis = reviewed_cut.get("nextAnalysis") or {}
        require(next_analysis.get("sourceSetSha256") == source_set, "feedback analysis cut source set mismatch")
        require(next_analysis.get("candidateId") == candidate_id, "feedback analysis cut candidate mismatch")
        require(next_analysis.get("difficultyEvidenceSha256") == digest(args.difficulty), "feedback analysis cut difficulty digest mismatch")
        review = reviewed_cut.get("review") or {}
        require(review.get("authority") == "independent-maintainer-review", "feedback analysis cut review authority is invalid")
        require(review.get("verdict") == "approve-for-case-construction", "feedback analysis cut was not approved for construction")
        require(review.get("proposalSha256") == digest(args.feedback_cut_proposal) == cut_decision.get("proposalSha256"), "feedback cut proposal digest mismatch")
        require(review.get("decisionSha256") == digest(args.feedback_cut_review), "feedback cut review digest mismatch")
        require(review.get("reviewer") == cut_decision.get("reviewer"), "feedback cut reviewer mismatch")
        require(review.get("verdict") == cut_decision.get("verdict"), "feedback cut verdict mismatch")
        risk_ids = {row.get("id") for row in cut_proposal.get("risks", []) if isinstance(row, dict)}
        require(set(review.get("acknowledgedRiskIds", [])) == risk_ids == set(cut_decision.get("acknowledgedRiskIds", [])), "feedback cut risk acknowledgements mismatch")
        feedback_analysis_cut = {
            "cutId": reviewed_cut.get("cutId"),
            "sha256": digest(args.feedback_analysis_cut),
            "priorCaseId": (reviewed_cut.get("priorCase") or {}).get("caseId"),
            "priorCaseSha256": (reviewed_cut.get("priorCase") or {}).get("caseSha256"),
            "priorSourceSetSha256": (reviewed_cut.get("priorCase") or {}).get("sourceSetSha256"),
            "feedbackCandidateId": (reviewed_cut.get("feedback") or {}).get("candidateId"),
            "feedbackEvidenceSha256": (reviewed_cut.get("feedback") or {}).get("evidenceSha256"),
            "nextSourceSetSha256": next_analysis.get("sourceSetSha256"),
            "nextMethodRevision": next_analysis.get("methodRevision"),
            "nextAnalysisReceiptSha256": next_analysis.get("analysisReceiptSha256"),
            "review": review,
        }
    else:
        require(args.feedback_cut_proposal is None and args.feedback_cut_review is None, "feedback cut evidence requires a reviewed feedback analysis cut")

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
        "construction": construction,
        "constructionQuality": construction_quality,
        "feedbackAnalysisCut": feedback_analysis_cut,
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
