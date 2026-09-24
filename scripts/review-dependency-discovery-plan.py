#!/usr/bin/env python3
"""Record and compile an explicit review of hidden dependency obligations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")


class ReviewError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ReviewError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def create_decision(
    proposal_path: Path,
    expected_sha256: str,
    reviewer: str,
    acknowledged_risk_ids: str,
    rationale: str,
) -> dict[str, Any]:
    proposal = load(proposal_path, "dependency plan proposal")
    require(
        proposal.get("schema") == "agentlab.dependency_discovery_plan_proposal.v1",
        "unsupported dependency plan proposal",
    )
    require(proposal.get("status") == "review-required", "dependency plan proposal is not review-required")
    require(proposal.get("automaticPromotion") is False, "dependency plan proposal can auto-promote")
    require(proposal.get("status") == "review-required", "dependency plan proposal is not review-required")
    require(SHA256.fullmatch(expected_sha256) is not None, "expected proposal digest is invalid")
    actual = digest(proposal_path)
    require(actual == expected_sha256, "operator-provided digest differs from dependency plan proposal")
    reviewer = reviewer.strip()
    rationale = rationale.strip()
    require(reviewer and rationale, "reviewer and rationale are required")
    acknowledged = sorted(
        {value.strip() for value in acknowledged_risk_ids.split(",") if value.strip()}
    )
    expected_risks = sorted(
        row.get("id")
        for row in proposal.get("risks") or []
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    )
    require(expected_risks and acknowledged == expected_risks, "review must acknowledge every dependency risk exactly")
    return {
        "schema": "agentlab.dependency_discovery_plan_review.v1",
        "proposalSha256": actual,
        "verdict": "approve-for-contract",
        "reviewer": reviewer,
        "acknowledgedRiskIds": acknowledged,
        "rationale": rationale,
        "automaticPromotion": False,
    }


def compile_plan(
    proposal_path: Path, review_path: Path
) -> dict[str, Any]:
    proposal = load(proposal_path, "dependency plan proposal")
    review = load(review_path, "dependency plan review")
    require(
        proposal.get("schema") == "agentlab.dependency_discovery_plan_proposal.v1",
        "unsupported dependency plan proposal",
    )
    require(
        review.get("schema") == "agentlab.dependency_discovery_plan_review.v1",
        "unsupported dependency plan review",
    )
    proposal_sha = digest(proposal_path)
    require(review.get("proposalSha256") == proposal_sha, "review does not bind exact dependency proposal")
    require(review.get("verdict") == "approve-for-contract", "dependency plan was not approved")
    require(review.get("automaticPromotion") is False, "dependency review can auto-promote")
    require(isinstance(review.get("reviewer"), str) and review["reviewer"].strip(), "dependency reviewer is absent")
    require(isinstance(review.get("rationale"), str) and review["rationale"].strip(), "dependency review rationale is absent")
    risk_ids = sorted(
        row.get("id")
        for row in proposal.get("risks") or []
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    )
    require(review.get("acknowledgedRiskIds") == risk_ids, "dependency risk acknowledgements differ")
    return {
        "schema": "agentlab.dependency_discovery_plan.v2",
        "caseId": proposal["caseId"],
        "candidateId": proposal["candidateId"],
        "sourceSetSha256": proposal["sourceSetSha256"],
        "casePlanProposalSha256": proposal["casePlanProposalSha256"],
        "difficultyEvidenceSha256": proposal["difficultyEvidenceSha256"],
        "programFactsSha256": proposal["programFactsSha256"],
        "derivation": proposal["derivation"],
        "stages": proposal["stages"],
        "review": {
            "authority": "explicit-dependency-plan-review",
            "reviewer": review["reviewer"],
            "proposalSha256": proposal_sha,
            "decisionSha256": digest(review_path),
            "acknowledgedRiskIds": risk_ids,
            "verdict": review["verdict"],
        },
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    decide = subparsers.add_parser("decide")
    decide.add_argument("--proposal", type=Path, required=True)
    decide.add_argument("--expected-sha256", required=True)
    decide.add_argument("--reviewer", required=True)
    decide.add_argument("--acknowledged-risk-ids", required=True)
    decide.add_argument("--rationale", required=True)
    decide.add_argument("--output", type=Path, required=True)
    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--proposal", type=Path, required=True)
    compile_parser.add_argument("--review", type=Path, required=True)
    compile_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
        if args.command == "decide":
            value = create_decision(
                args.proposal,
                args.expected_sha256,
                args.reviewer,
                args.acknowledged_risk_ids,
                args.rationale,
            )
        else:
            value = compile_plan(args.proposal, args.review)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "outputSha256": digest(args.output)}, sort_keys=True))
    except (ReviewError, OSError, ValueError) as error:
        print(f"dependency discovery plan review invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
