#!/usr/bin/env python3
"""Propose a review-required next analysis cut from assessed failure evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


def load(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def select(rows: Any, identity: str, label: str) -> dict[str, Any]:
    matches = [row for row in rows or [] if isinstance(row, dict) and row.get("id") == identity]
    require(len(matches) == 1, f"{label} must identify exactly one row")
    return matches[0]


def validate_sources(sources: Any) -> list[dict[str, str]]:
    require(isinstance(sources, list) and len(sources) >= 2, "next analysis requires at least two sources")
    normalized = []
    for source in sources:
        require(isinstance(source, dict), "next source must be an object")
        source_id = source.get("id")
        repository = source.get("repository")
        revision = source.get("revision")
        require(isinstance(source_id, str) and source_id, "next source id is required")
        require(isinstance(repository, str) and repository, "next source repository is required")
        require(isinstance(revision, str) and REVISION.fullmatch(revision), "next source revision must be exact")
        normalized.append({"id": source_id, "repository": repository, "revision": revision})
    require(len({row["id"] for row in normalized}) == len(normalized), "next source ids must be unique")
    return normalized


def build_proposal(
    *,
    case: dict[str, Any],
    feedback: dict[str, Any],
    analysis: dict[str, Any],
    difficulty: dict[str, Any],
    feedback_path: Path,
    analysis_path: Path,
    difficulty_path: Path,
    feedback_candidate_id: str,
    difficulty_candidate_id: str,
    next_method_revision: str,
) -> dict[str, Any]:
    require(case.get("schema") == "agentlab.multi_repo_evaluation_case.v1", "unsupported prior case schema")
    require(case.get("status") == "frozen-calibrated", "prior case must remain frozen and calibrated")
    require(case.get("automaticPromotion") is False, "prior case must not auto-promote")
    case_id = case.get("id")
    prior_source_set = case.get("sourceSetSha256")
    require(isinstance(case_id, str) and case_id, "prior case id is required")
    require(isinstance(prior_source_set, str) and SHA256.fullmatch(prior_source_set), "prior source set is invalid")

    require(feedback.get("schema") == "agentlab.assessment_feedback_candidates.v1", "unsupported feedback schema")
    require(feedback.get("caseId") == case_id, "feedback case identity mismatch")
    require(feedback.get("sourceSetSha256") == prior_source_set, "feedback prior source set mismatch")
    require(feedback.get("caseSha256") == canonical_digest(case), "feedback does not bind the exact prior case")
    prior_method_revision = feedback.get("methodRevision")
    require(isinstance(prior_method_revision, str) and REVISION.fullmatch(prior_method_revision), "feedback method revision is invalid")
    require((feedback.get("policy") or {}).get("automaticPromotion") is False, "feedback must not auto-promote")
    feedback_candidate = select(feedback.get("candidates"), feedback_candidate_id, "feedback candidate id")
    require(feedback_candidate.get("caseId") == case_id, "feedback candidate case identity mismatch")
    require(feedback_candidate.get("status") == "candidate", "feedback candidate is not reviewable")
    require(feedback_candidate.get("maturityState") == "candidate", "feedback candidate maturity changed")
    require(feedback_candidate.get("automaticPromotion") is False, "feedback candidate must not auto-promote")
    feedback_verification = feedback_candidate.get("verificationContract") or {}
    require(feedback_verification.get("caseReady") is False, "feedback candidate must remain non-ready")
    require(
        "new-source-and-analysis-cut" in feedback_verification.get("required", []),
        "feedback candidate does not require a new source and analysis cut",
    )

    require(analysis.get("schema") == "agentlab.multi_repo_analysis.v1", "unsupported next analysis receipt schema")
    require(analysis.get("automaticPromotion") is False, "next analysis must not auto-promote")
    require(difficulty.get("schema") == "agentlab.difficulty_candidates.v2", "unsupported next difficulty schema")
    require(difficulty.get("automaticPromotion") is False, "next difficulty evidence must not auto-promote")
    next_source_set = difficulty.get("sourceSetSha256")
    require(isinstance(next_source_set, str) and SHA256.fullmatch(next_source_set), "next source set is invalid")
    require(analysis.get("sourceSetSha256") == next_source_set, "analysis and difficulty source sets differ")
    require(analysis.get("difficultyCandidatesSha256") == digest(difficulty_path), "analysis does not bind exact difficulty bytes")
    sources = validate_sources(difficulty.get("sources"))
    receipt_sources = [
        {"id": row.get("id"), "repository": row.get("repository"), "revision": row.get("revision")}
        for row in analysis.get("repositories", [])
        if isinstance(row, dict)
    ]
    require(receipt_sources == sources, "analysis receipt sources differ from difficulty evidence")
    source_identity = {
        "schema": "agentlab.multi_repo_source_set.v1",
        "repositories": sources,
        "moduleBindings": difficulty.get("moduleBindings") or {},
    }
    require(canonical_digest(source_identity) == next_source_set, "next source-set digest is not reproducible")
    require(isinstance(next_method_revision, str) and REVISION.fullmatch(next_method_revision), "next method revision must be exact")
    source_changed = next_source_set != prior_source_set
    method_changed = next_method_revision != prior_method_revision
    require(source_changed or method_changed, "next analysis cut must change the source set or method revision")

    difficulty_candidate = select(difficulty.get("candidates"), difficulty_candidate_id, "difficulty candidate id")
    require(
        difficulty_candidate.get("dimensionId") == "multi-repository-change-impact",
        "next candidate must be a recursive multi-repository impact",
    )
    require(difficulty_candidate.get("status") == "candidate", "next difficulty is not a candidate")
    require(difficulty_candidate.get("maturityState") == "candidate", "next difficulty maturity changed")
    require(difficulty_candidate.get("automaticPromotion") is False, "next difficulty must not auto-promote")
    verification = difficulty_candidate.get("verificationContract") or {}
    require(verification.get("caseReady") is False, "next difficulty must remain non-ready")
    affected = difficulty_candidate.get("affectedFiles")
    require(isinstance(affected, list) and affected, "next difficulty has no affected files")
    affected_repositories = {row.get("repositoryId") for row in affected if isinstance(row, dict)}
    require(len(affected_repositories) >= 2, "next difficulty does not cross repository boundaries")

    transition_identity = {
        "priorCaseSha256": canonical_digest(case),
        "feedbackCandidateId": feedback_candidate_id,
        "feedbackEvidenceSha256": digest(feedback_path),
        "nextSourceSetSha256": next_source_set,
        "nextMethodRevision": next_method_revision,
        "analysisReceiptSha256": digest(analysis_path),
        "difficultyEvidenceSha256": digest(difficulty_path),
        "difficultyCandidateId": difficulty_candidate_id,
    }
    return {
        "schema": "agentlab.feedback_analysis_cut_proposal.v1",
        "status": "review-required",
        "cutId": f"feedback-analysis-cut-{canonical_digest(transition_identity)[:20]}",
        "priorCase": {
            "caseId": case_id,
            "caseSha256": canonical_digest(case),
            "sourceSetSha256": prior_source_set,
            "methodRevision": prior_method_revision,
            "immutability": "retained-unchanged",
        },
        "feedback": {
            "evidenceSha256": digest(feedback_path),
            "candidateId": feedback_candidate_id,
            "stageId": feedback_candidate.get("stageId"),
            "failureMode": feedback_candidate.get("failureMode"),
            "mechanism": feedback_candidate.get("mechanism"),
            "verificationContract": feedback_verification,
        },
        "nextAnalysis": {
            "sourceSetSha256": next_source_set,
            "methodRevision": next_method_revision,
            "sources": sources,
            "analysisReceiptSha256": digest(analysis_path),
            "difficultyEvidenceSha256": digest(difficulty_path),
            "candidateId": difficulty_candidate_id,
            "dimensionId": difficulty_candidate.get("dimensionId"),
            "mechanism": difficulty_candidate.get("mechanism"),
            "evidenceIds": difficulty_candidate.get("evidenceIds"),
            "verificationContract": verification,
        },
        "change": {
            "sourceSetChanged": source_changed,
            "methodRevisionChanged": method_changed,
        },
        "risks": [
            {
                "id": "feedback-mechanism-alignment-unverified",
                "statement": "A maintainer must judge whether the new program-analysis candidate explains the assessed failure mechanism.",
            },
            {
                "id": "semantic-intent-unverified",
                "statement": "Program impact evidence does not establish a fair participant-visible behavior contract.",
            },
            {
                "id": "oracle-and-calibration-pending",
                "statement": "An independent Oracle and repair/preservation calibration are still required.",
            },
            {
                "id": "freshness-and-contamination-pending",
                "statement": "Freshness and contamination evidence remain separate qualification gates.",
            },
        ],
        "reviewPolicy": {
            "requiredDecisionSchema": "agentlab.feedback_analysis_cut_review.v1",
            "requiredVerdict": "approve-for-case-construction",
            "mustAcknowledgeEveryRisk": True,
        },
        "automaticPromotion": False,
        "nextGate": "independent-maintainer-review",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior-case", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--analysis-receipt", type=Path, required=True)
    parser.add_argument("--difficulty", type=Path, required=True)
    parser.add_argument("--feedback-candidate-id", required=True)
    parser.add_argument("--difficulty-candidate-id", required=True)
    parser.add_argument("--next-method-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), f"refusing to overwrite proposal: {args.output}")
    proposal = build_proposal(
        case=load(args.prior_case, "prior case"),
        feedback=load(args.feedback, "assessment feedback"),
        analysis=load(args.analysis_receipt, "next analysis receipt"),
        difficulty=load(args.difficulty, "next difficulty evidence"),
        feedback_path=args.feedback,
        analysis_path=args.analysis_receipt,
        difficulty_path=args.difficulty,
        feedback_candidate_id=args.feedback_candidate_id,
        difficulty_candidate_id=args.difficulty_candidate_id,
        next_method_revision=args.next_method_revision,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "cutId": proposal["cutId"], "status": proposal["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
