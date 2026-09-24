"""Validation helpers for reviewed API-call localization evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text())


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_reviewed_localization(
    localization_path: Path,
    proposal_path: Path,
    review_path: Path,
    *,
    candidate_id: str,
    source_set_sha256: str,
):
    localization = load(localization_path)
    proposal = load(proposal_path)
    decision = load(review_path)
    require(
        localization.get("schema") == "agentlab.api_call_case_localization.v1",
        "unsupported reviewed localization schema",
    )
    require(
        localization.get("status") == "reviewed-for-intent-construction",
        "API-call localization is not reviewed for intent construction",
    )
    require(localization.get("automaticPromotion") is False, "localization must not auto-promote")
    require(
        proposal.get("schema") == "agentlab.api_call_case_localization_proposal.v1",
        "unsupported localization proposal schema",
    )
    require(proposal.get("status") == "review-required", "localization proposal is not review-required")
    require(proposal.get("automaticPromotion") is False, "localization proposal must not auto-promote")
    require(
        decision.get("schema") == "agentlab.api_call_case_localization_review.v1",
        "unsupported localization review schema",
    )
    require(decision.get("automaticPromotion") is False, "localization review must not auto-promote")
    require(
        localization.get("candidateId") == proposal.get("candidateId") == candidate_id,
        "localization candidate mismatch",
    )
    require(
        localization.get("sourceSetSha256") == proposal.get("sourceSetSha256") == source_set_sha256,
        "localization source set mismatch",
    )
    review = localization.get("review") or {}
    proposal_sha256 = digest(proposal_path)
    decision_sha256 = digest(review_path)
    require(
        review.get("authority") == "independent-maintainer-review",
        "localization review authority is invalid",
    )
    require(
        review.get("verdict") == decision.get("verdict") == "approve-for-intent-construction",
        "localization review did not approve intent construction",
    )
    require(
        review.get("proposalSha256") == decision.get("proposalSha256") == proposal_sha256,
        "localization proposal digest mismatch",
    )
    require(review.get("decisionSha256") == decision_sha256, "localization review digest mismatch")
    require(
        isinstance(review.get("reviewer"), str)
        and review["reviewer"]
        and review.get("reviewer") == decision.get("reviewer"),
        "localization reviewer mismatch",
    )
    require(
        isinstance(review.get("rationale"), str)
        and review["rationale"]
        and review.get("rationale") == decision.get("rationale"),
        "localization review rationale mismatch",
    )
    risk_ids = {
        row.get("id")
        for row in proposal.get("risks", [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    require(risk_ids, "localization proposal risks are required")
    require(
        set(review.get("acknowledgedRiskIds", []))
        == set(decision.get("acknowledgedRiskIds", []))
        == risk_ids,
        "localization review must acknowledge every proposal risk",
    )
    reviewed_fields = (
        "candidateId",
        "sourceSetSha256",
        "methodRevision",
        "title",
        "hypothesis",
        "apiContract",
        "targetCallSites",
        "referenceCallSites",
        "editablePaths",
        "contextPaths",
        "expandedPaths",
        "proposedChecks",
        "risks",
        "lineage",
        "reviewPolicy",
    )
    require(
        all(localization.get(key) == proposal.get(key) for key in reviewed_fields),
        "reviewed localization differs from its proposal",
    )
    editable = localization.get("editablePaths")
    context = localization.get("contextPaths")
    require(isinstance(editable, list) and editable, "reviewed localization requires editable paths")
    require(isinstance(context, list), "reviewed localization context paths must be a list")
    editable_keys = [(row.get("repositoryId"), row.get("path")) for row in editable]
    context_keys = [(row.get("repositoryId"), row.get("path")) for row in context]
    require(len(editable_keys) == len(set(editable_keys)), "localization editable paths must be unique")
    require(len(context_keys) == len(set(context_keys)), "localization context paths must be unique")
    require(not set(editable_keys).intersection(context_keys), "localization editable and context paths overlap")
    return localization


def localization_summary(localization_path: Path, proposal_path: Path, review_path: Path, localization):
    return {
        "status": localization["status"],
        "candidateId": localization["candidateId"],
        "sourceSetSha256": localization["sourceSetSha256"],
        "methodRevision": localization["methodRevision"],
        "sha256": digest(localization_path),
        "proposalSha256": digest(proposal_path),
        "reviewSha256": digest(review_path),
        "reviewer": localization["review"]["reviewer"],
        "hypothesis": localization["hypothesis"],
        "apiContract": localization["apiContract"],
        "targetCallSites": localization["targetCallSites"],
        "referenceCallSites": localization["referenceCallSites"],
        "editablePaths": [
            {"repositoryId": row["repositoryId"], "path": row["path"]}
            for row in localization["editablePaths"]
        ],
        "contextPaths": [
            {"repositoryId": row["repositoryId"], "path": row["path"]}
            for row in localization["contextPaths"]
        ],
        "proposedChecks": localization["proposedChecks"],
        "automaticPromotion": False,
    }
