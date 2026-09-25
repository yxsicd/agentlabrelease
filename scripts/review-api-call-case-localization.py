#!/usr/bin/env python3
"""Compile an independent review into an immutable API-call localization cut."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from api_call_localization import validate_semantic_authorization


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
    parser.add_argument("--semantic-packet", type=Path, required=True)
    parser.add_argument("--semantic-decision", type=Path, required=True)
    parser.add_argument("--semantic-gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "refusing to overwrite reviewed localization")
    proposal = load(args.proposal)
    review = load(args.review)
    require(proposal.get("schema") == "agentlab.api_call_case_localization_proposal.v1", "unsupported proposal schema")
    require(proposal.get("status") == "review-required", "proposal is not review-required")
    require(proposal.get("automaticPromotion") is False, "proposal must not auto-promote")
    semantic = validate_semantic_authorization(
        args.semantic_packet,
        args.semantic_decision,
        args.semantic_gate,
        candidate_id=proposal.get("candidateId"),
        source_set_sha256=proposal.get("sourceSetSha256"),
    )
    require(proposal.get("semanticAuthorization") == semantic, "proposal semantic authorization differs")
    require(review.get("schema") == "agentlab.api_call_case_localization_review.v1", "unsupported review schema")
    require(review.get("proposalSha256") == digest(args.proposal), "review proposal digest mismatch")
    require(review.get("verdict") == "approve-for-intent-construction", "localization is not approved for intent construction")
    require(isinstance(review.get("reviewer"), str) and review["reviewer"], "reviewer is required")
    require(isinstance(review.get("rationale"), str) and review["rationale"], "review rationale is required")
    risk_ids = {row.get("id") for row in proposal.get("risks", []) if isinstance(row, dict)}
    require(set(review.get("acknowledgedRiskIds", [])) == risk_ids, "review must acknowledge every proposal risk")
    require(review.get("automaticPromotion") is False, "review must not auto-promote")
    reviewed = {
        **proposal,
        "schema": "agentlab.api_call_case_localization.v1",
        "status": "reviewed-for-intent-construction",
        "review": {
            "authority": "independent-maintainer-review",
            "reviewer": review["reviewer"],
            "rationale": review["rationale"],
            "verdict": review["verdict"],
            "acknowledgedRiskIds": sorted(risk_ids),
            "proposalSha256": digest(args.proposal),
            "decisionSha256": digest(args.review),
        },
        "automaticPromotion": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reviewed, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "status": reviewed["status"], "localizationSha256": digest(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
