#!/usr/bin/env python3
"""Record an exact candidate-cohort choice and compile its immutable contract."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


class CohortReviewError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise CohortReviewError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CohortReviewError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_values(raw: str) -> list[str]:
    values = sorted({value.strip() for value in raw.split(",") if value.strip()})
    require(values, "comma-separated values are absent")
    return values


def validate_proposal(proposal: dict[str, Any]) -> None:
    require(proposal.get("schema") == "agentlab.multi_repo_candidate_cohort_proposal.v1", "unsupported cohort proposal")
    require(proposal.get("status") == "review-required", "cohort proposal is not review-required")
    require(proposal.get("automaticPromotion") is False, "cohort proposal can auto-promote")
    require(
        isinstance(proposal.get("proposalMethodRevision"), str)
        and REVISION.fullmatch(proposal["proposalMethodRevision"]),
        "cohort proposal method revision is invalid",
    )
    frame = proposal.get("samplingFrame")
    require(isinstance(frame, dict) and frame.get("declaredRepresentative") is False, "cohort proposal overclaims representativeness")
    rows = proposal.get("eligibleCandidates")
    require(isinstance(rows, list) and len(rows) >= 2, "cohort proposal has fewer than two eligible candidates")
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    require(len(ids) == len(rows) == len(set(ids)), "eligible candidate identities are invalid")
    require(
        all(
            row.get("caseSource")
            == {
                "lane": "derived",
                "strategy": "semantic-program-analysis",
                "authority": "exact-difficulty-evidence",
            }
            for row in rows
        ),
        "eligible candidate source classification is invalid",
    )


def decide(proposal_path: Path, expected_sha256: str, selected_raw: str, reviewer: str, acknowledged_raw: str, rationale: str) -> dict[str, Any]:
    proposal = load(proposal_path, "candidate cohort proposal")
    validate_proposal(proposal)
    require(SHA256.fullmatch(expected_sha256) is not None, "expected proposal digest is invalid")
    actual = digest(proposal_path)
    require(actual == expected_sha256, "operator-provided digest differs from candidate cohort proposal")
    selected = csv_values(selected_raw)
    require(len(selected) >= 2, "candidate cohort requires at least two selected candidates")
    eligible = {row["id"] for row in proposal["eligibleCandidates"]}
    require(set(selected).issubset(eligible), "selection contains an ineligible or unknown candidate")
    expected_risks = sorted(row["id"] for row in proposal.get("risks") or [])
    acknowledged = csv_values(acknowledged_raw)
    require(acknowledged == expected_risks, "review must acknowledge every cohort risk exactly")
    reviewer = reviewer.strip()
    rationale = rationale.strip()
    require(reviewer and rationale, "reviewer and rationale are required")
    return {
        "schema": "agentlab.multi_repo_candidate_cohort_review.v1",
        "proposalSha256": actual,
        "verdict": "approve-for-independent-case-construction",
        "selectedCandidateIds": selected,
        "reviewer": reviewer,
        "acknowledgedRiskIds": acknowledged,
        "rationale": rationale,
        "declaredRepresentative": False,
        "automaticPromotion": False,
    }


def compile_cohort(proposal_path: Path, review_path: Path) -> dict[str, Any]:
    proposal = load(proposal_path, "candidate cohort proposal")
    review = load(review_path, "candidate cohort review")
    validate_proposal(proposal)
    require(review.get("schema") == "agentlab.multi_repo_candidate_cohort_review.v1", "unsupported cohort review")
    require(review.get("proposalSha256") == digest(proposal_path), "review does not bind exact cohort proposal")
    require(review.get("verdict") == "approve-for-independent-case-construction", "candidate cohort was not approved")
    require(review.get("declaredRepresentative") is False, "cohort review overclaims representativeness")
    require(review.get("automaticPromotion") is False, "cohort review can auto-promote")
    require(isinstance(review.get("reviewer"), str) and review["reviewer"].strip(), "cohort reviewer is absent")
    require(isinstance(review.get("rationale"), str) and review["rationale"].strip(), "cohort review rationale is absent")
    risks = sorted(row["id"] for row in proposal.get("risks") or [])
    require(review.get("acknowledgedRiskIds") == risks, "cohort risk acknowledgements differ")
    selected_ids = review.get("selectedCandidateIds")
    require(isinstance(selected_ids, list) and len(selected_ids) >= 2 and selected_ids == sorted(set(selected_ids)), "reviewed candidate selection is invalid")
    candidates = {row["id"]: row for row in proposal["eligibleCandidates"]}
    require(set(selected_ids).issubset(candidates), "reviewed candidate is outside proposal")
    selected = [candidates[candidate_id] for candidate_id in selected_ids]
    return {
        "schema": "agentlab.multi_repo_candidate_cohort.v1",
        "cohortId": proposal["cohortId"],
        "methodRevision": proposal["methodRevision"],
        "proposalMethodRevision": proposal["proposalMethodRevision"],
        "sourceSetSha256": proposal["sourceSetSha256"],
        "difficultyEvidenceSha256": proposal["difficultyEvidenceSha256"],
        "samplingFrame": proposal["samplingFrame"],
        "selectedCandidates": selected,
        "selectedCandidateCount": len(selected),
        "review": {
            "authority": "explicit-candidate-cohort-review",
            "reviewer": review["reviewer"],
            "proposalSha256": digest(proposal_path),
            "decisionSha256": digest(review_path),
            "acknowledgedRiskIds": risks,
            "verdict": review["verdict"],
        },
        "declaredRepresentative": False,
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    decision = subparsers.add_parser("decide")
    decision.add_argument("--proposal", type=Path, required=True)
    decision.add_argument("--expected-sha256", required=True)
    decision.add_argument("--selected-candidate-ids", required=True)
    decision.add_argument("--reviewer", required=True)
    decision.add_argument("--acknowledged-risk-ids", required=True)
    decision.add_argument("--rationale", required=True)
    decision.add_argument("--output", type=Path, required=True)
    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--proposal", type=Path, required=True)
    compile_parser.add_argument("--review", type=Path, required=True)
    compile_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
        if args.command == "decide":
            value = decide(args.proposal, args.expected_sha256, args.selected_candidate_ids, args.reviewer, args.acknowledged_risk_ids, args.rationale)
        else:
            value = compile_cohort(args.proposal, args.review)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "outputSha256": digest(args.output)}, sort_keys=True))
    except (CohortReviewError, OSError, ValueError) as error:
        print(f"candidate cohort review invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
