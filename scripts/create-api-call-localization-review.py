#!/usr/bin/env python3
"""Create an exact-digest API-call localization decision from reviewer input."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


SHA256 = re.compile(r"[0-9a-f]{64}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--rationale", required=True)
    parser.add_argument("--acknowledged-risk-ids", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("refusing to overwrite localization review")
    if not SHA256.fullmatch(args.expected_sha256):
        raise ValueError("expected localization proposal SHA-256 is invalid")
    actual = hashlib.sha256(args.proposal.read_bytes()).hexdigest()
    if actual != args.expected_sha256:
        raise ValueError("reviewer-provided digest does not match exact localization proposal")
    proposal = json.loads(args.proposal.read_text())
    if proposal.get("schema") != "agentlab.api_call_case_localization_proposal.v1":
        raise ValueError("unsupported localization proposal schema")
    if proposal.get("status") != "review-required" or proposal.get("automaticPromotion") is not False:
        raise ValueError("localization proposal is not review-required")
    reviewer = args.reviewer.strip()
    rationale = args.rationale.strip()
    if not reviewer or not rationale:
        raise ValueError("reviewer and rationale are required")
    acknowledged = sorted(
        {value.strip() for value in args.acknowledged_risk_ids.split(",") if value.strip()}
    )
    expected_risks = sorted(
        row.get("id")
        for row in proposal.get("risks", [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    )
    if not expected_risks or acknowledged != expected_risks:
        raise ValueError("acknowledged risk ids must exactly match localization proposal risks")
    decision = {
        "schema": "agentlab.api_call_case_localization_review.v1",
        "proposalSha256": actual,
        "verdict": "approve-for-intent-construction",
        "reviewer": reviewer,
        "acknowledgedRiskIds": acknowledged,
        "rationale": rationale,
        "automaticPromotion": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "proposalSha256": actual, "reviewer": reviewer}, sort_keys=True))


if __name__ == "__main__":
    main()
