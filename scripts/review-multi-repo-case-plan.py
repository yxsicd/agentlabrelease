#!/usr/bin/env python3
"""Compile an exact, explicitly reviewed proposal into a calibration plan."""
from __future__ import annotations

import argparse
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proposal = load(args.proposal)
    review = load(args.review)
    require(proposal.get("schema") == "agentlab.multi_repo_case_plan_proposal.v1", "unsupported proposal schema")
    require(proposal.get("status") == "review-required", "proposal is not awaiting review")
    require(proposal.get("automaticPromotion") is False, "proposal must not auto-promote")
    require(review.get("schema") == "agentlab.multi_repo_case_plan_review.v1", "unsupported review schema")
    proposal_sha256 = digest(args.proposal)
    require(review.get("proposalSha256") == proposal_sha256, "review does not bind the exact proposal")
    require(review.get("verdict") == "approve-for-calibration", "review did not approve calibration")
    require(isinstance(review.get("reviewer"), str) and review["reviewer"], "reviewer identity is required")
    risk_ids = {row.get("id") for row in proposal.get("risks", []) if isinstance(row, dict)}
    acknowledged = review.get("acknowledgedRiskIds")
    require(isinstance(acknowledged, list) and set(acknowledged) == risk_ids, "review must acknowledge every proposal risk exactly")
    require(isinstance(review.get("rationale"), str) and review["rationale"], "review rationale is required")

    plan = {
        "schema": "agentlab.multi_repo_case_plan.v2",
        **{key: proposal[key] for key in ("caseId", "candidateId", "sourceSetSha256", "title", "allowedEdits", "stages", "oracle", "calibrationExpectations")},
        "review": {
            "authority": "explicit-proposal-review",
            "reviewer": review["reviewer"],
            "proposalSha256": proposal_sha256,
            "decisionSha256": digest(args.review),
            "acknowledgedRiskIds": sorted(acknowledged),
            "verdict": review["verdict"],
        },
        "automaticPromotion": False,
    }
    require(not args.output.exists(), "refusing to overwrite reviewed plan")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "planSha256": digest(args.output), "verdict": review["verdict"]}, sort_keys=True))


if __name__ == "__main__":
    main()
