#!/usr/bin/env python3
"""Triage every feedback-analysis proposal without silently approving a case."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


QUEUE_SCHEMA = "agentlab.feedback_analysis_proposal_queue.v1"
PROPOSAL_SCHEMA = "agentlab.feedback_analysis_cut_proposal.v1"
REVIEW_SCHEMA = "agentlab.feedback_analysis_proposal_queue_triage_review.v1"
OUTPUT_SCHEMA = "agentlab.feedback_analysis_proposal_queue_triage.v1"
VERDICTS = {
    "shortlist-for-independent-review",
    "reject-semantic-misalignment",
}


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def triage(
    queue_path: Path,
    proposal_root: Path,
    review_path: Path,
) -> dict[str, Any]:
    queue = load(queue_path, "proposal queue")
    review = load(review_path, "triage review")
    require(queue.get("schema") == QUEUE_SCHEMA, "unsupported proposal queue schema")
    require(queue.get("status") == "maintainer-review-required", "queue is not awaiting review")
    require(queue.get("automaticPromotion") is False, "queue may not auto-promote")
    proposals = queue.get("proposals")
    require(isinstance(proposals, list) and proposals, "queue has no proposals")
    require(queue.get("proposalCount") == len(proposals), "queue proposal count differs")

    require(review.get("schema") == REVIEW_SCHEMA, "unsupported triage review schema")
    require(review.get("queueSha256") == digest(queue_path), "review does not bind exact queue")
    reviewer = review.get("reviewer")
    require(isinstance(reviewer, str) and reviewer.strip(), "reviewer identity is required")
    require(review.get("automaticPromotion") is False, "triage review may not auto-promote")
    raw_decisions = review.get("decisions")
    require(isinstance(raw_decisions, list), "triage decisions must be a list")
    require(len(raw_decisions) == len(proposals), "triage must decide every proposal exactly once")
    decisions_by_sha: dict[str, dict[str, Any]] = {}
    for decision in raw_decisions:
        require(isinstance(decision, dict), "triage decision must be an object")
        proposal_sha = decision.get("proposalSha256")
        require(isinstance(proposal_sha, str) and len(proposal_sha) == 64, "triage proposal digest is invalid")
        require(proposal_sha not in decisions_by_sha, "duplicate triage proposal decision")
        decisions_by_sha[proposal_sha] = decision

    normalized = []
    shortlisted = []
    for row in proposals:
        require(isinstance(row, dict), "queue proposal row is invalid")
        proposal_file = row.get("proposalFile")
        require(isinstance(proposal_file, str) and Path(proposal_file).name == proposal_file, "proposal file is invalid")
        proposal_path = proposal_root / proposal_file
        proposal = load(proposal_path, "feedback-analysis proposal")
        proposal_sha = digest(proposal_path)
        require(proposal_sha == row.get("proposalSha256"), "queue proposal digest differs")
        require(proposal.get("schema") == PROPOSAL_SCHEMA, "unsupported feedback-analysis proposal schema")
        require(proposal.get("status") == "review-required", "proposal is not review-required")
        require(proposal.get("automaticPromotion") is False, "proposal may not auto-promote")
        require(proposal.get("cutId") == row.get("cutId"), "proposal cut identity differs")
        next_analysis = proposal.get("nextAnalysis") or {}
        require(next_analysis.get("candidateId") == row.get("difficultyCandidateId"), "proposal candidate identity differs")

        decision = decisions_by_sha.get(proposal_sha)
        require(isinstance(decision, dict), "triage omits an exact queued proposal")
        require(decision.get("cutId") == row.get("cutId"), "triage cut identity differs")
        require(
            decision.get("difficultyCandidateId") == row.get("difficultyCandidateId"),
            "triage difficulty identity differs",
        )
        verdict = decision.get("verdict")
        require(verdict in VERDICTS, "unsupported triage verdict")
        rationale = decision.get("rationale")
        require(isinstance(rationale, str) and len(rationale.strip()) >= 20, "triage rationale is too weak")
        evidence = decision.get("evidence")
        require(
            isinstance(evidence, list)
            and evidence
            and all(isinstance(item, str) and item.strip() for item in evidence),
            "triage evidence is required",
        )
        normalized_row = {
            "rank": row.get("rank"),
            "proposalSha256": proposal_sha,
            "cutId": row.get("cutId"),
            "difficultyCandidateId": row.get("difficultyCandidateId"),
            "mechanism": next_analysis.get("mechanism"),
            "verdict": verdict,
            "rationale": rationale.strip(),
            "evidence": evidence,
        }
        normalized.append(normalized_row)
        if verdict == "shortlist-for-independent-review":
            shortlisted.append(normalized_row)

    require(set(decisions_by_sha) == {row["proposalSha256"] for row in proposals}, "triage includes an unknown proposal")
    require(len(shortlisted) <= 1, "triage may shortlist at most one proposal")
    selected = shortlisted[0] if shortlisted else None
    return {
        "schema": OUTPUT_SCHEMA,
        "status": (
            "one-proposal-shortlisted-review-required"
            if selected
            else "no-semantic-alignment"
        ),
        "queue": {
            "sha256": digest(queue_path),
            "eligibleCandidateCount": queue.get("eligibleCandidateCount"),
            "proposalCount": len(proposals),
        },
        "review": {
            "sha256": digest(review_path),
            "reviewer": reviewer.strip(),
            "authority": "maintainer-triage-not-case-approval",
        },
        "decisions": normalized,
        "denominators": {
            "reviewedProposalCount": len(normalized),
            "shortlistedProposalCount": len(shortlisted),
            "rejectedProposalCount": len(normalized) - len(shortlisted),
        },
        "selectedProposal": selected,
        "semanticAlignmentVerified": False,
        "automaticPromotion": False,
        "nextGate": (
            "independent-maintainer-review-of-shortlisted-proposal"
            if selected
            else "select-semantically-related-source-set-or-enrich-feedback-mechanism"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--proposal-root", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), f"refusing to overwrite triage output: {args.output}")
    result = triage(
        args.queue.resolve(),
        args.proposal_root.resolve(),
        args.review.resolve(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], **result["denominators"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
