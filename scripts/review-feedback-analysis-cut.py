#!/usr/bin/env python3
"""Compile an exact reviewed feedback-to-analysis proposal for case construction."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")


def load(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), f"refusing to overwrite reviewed cut: {args.output}")
    proposal = load(args.proposal, "feedback analysis cut proposal")
    review = load(args.review, "feedback analysis cut review")
    require(proposal.get("schema") == "agentlab.feedback_analysis_cut_proposal.v1", "unsupported proposal schema")
    require(proposal.get("status") == "review-required", "proposal is not awaiting review")
    require(proposal.get("automaticPromotion") is False, "proposal must not auto-promote")
    require(review.get("schema") == "agentlab.feedback_analysis_cut_review.v1", "unsupported review schema")
    proposal_sha256 = digest(args.proposal)
    require(review.get("proposalSha256") == proposal_sha256, "review does not bind the exact proposal")
    require(review.get("verdict") == "approve-for-case-construction", "review did not approve case construction")
    require(isinstance(review.get("reviewer"), str) and review["reviewer"], "reviewer identity is required")
    require(isinstance(review.get("rationale"), str) and review["rationale"], "review rationale is required")
    risk_ids = {row.get("id") for row in proposal.get("risks", []) if isinstance(row, dict)}
    acknowledged = review.get("acknowledgedRiskIds")
    require(isinstance(acknowledged, list) and set(acknowledged) == risk_ids, "review must acknowledge every proposal risk exactly")
    require(review.get("automaticPromotion") is False, "review must not auto-promote")
    feedback = proposal.get("feedback")
    require(
        isinstance(feedback, dict)
        and isinstance(feedback.get("dimensionId"), str)
        and bool(feedback["dimensionId"])
        and isinstance(feedback.get("primaryDimension"), str)
        and bool(feedback["primaryDimension"]),
        "proposal feedback dimensions are invalid",
    )
    performance = feedback.get("performanceEvidence")
    if feedback["dimensionId"] == "assessed-agent-performance-separation":
        authority = performance.get("authority") if isinstance(performance, dict) else None
        require(
            feedback.get("primaryDimension") == "performance-feedback"
            and feedback.get("failureMode") == "repeatable-performance-separation"
            and isinstance(performance, dict)
            and performance.get("rangesSeparated") is True
            and isinstance(performance.get("environmentIdentity"), str)
            and bool(performance["environmentIdentity"])
            and all(
                isinstance(performance.get(field), str)
                and SHA256.fullmatch(performance[field])
                for field in ("performancePolicySha256", "profileWorkloadSha256")
            )
            and isinstance(performance.get("metric"), str)
            and bool(performance["metric"])
            and performance.get("statistic") in {"mean", "p50", "p95"}
            and isinstance(performance.get("unit"), str)
            and bool(performance["unit"])
            and performance.get("direction") in {"lower", "higher"}
            and isinstance(performance.get("bestParticipantId"), str)
            and bool(performance["bestParticipantId"])
            and isinstance(performance.get("worstParticipantId"), str)
            and bool(performance["worstParticipantId"])
            and performance["bestParticipantId"] != performance["worstParticipantId"]
            and isinstance(performance.get("meanDifference"), (int, float))
            and not isinstance(performance["meanDifference"], bool)
            and math.isfinite(performance["meanDifference"])
            and performance["meanDifference"] > 0
            and authority
            == {
                "functional": "none",
                "relativePerformance": "smartperf-emulator-proxy",
                "absolutePowerThermal": "unavailable-on-emulator",
            }
            and "independent-performance-calibration"
            in (feedback.get("verificationContract") or {}).get("required", []),
            "proposal performance feedback is invalid",
        )
    else:
        require(performance is None, "non-performance proposal overclaims performance evidence")

    result = {
        "schema": "agentlab.feedback_analysis_cut.v1",
        "status": "reviewed-for-case-construction",
        "cutId": proposal.get("cutId"),
        "priorCase": proposal.get("priorCase"),
        "feedback": feedback,
        "nextAnalysis": proposal.get("nextAnalysis"),
        "change": proposal.get("change"),
        "review": {
            "authority": "independent-maintainer-review",
            "reviewer": review["reviewer"],
            "rationale": review["rationale"],
            "proposalSha256": proposal_sha256,
            "decisionSha256": digest(args.review),
            "acknowledgedRiskIds": sorted(acknowledged),
            "verdict": review["verdict"],
        },
        "automaticPromotion": False,
        "nextGate": "case-intent-construction-and-independent-calibration",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "cutId": result["cutId"], "status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
