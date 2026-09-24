#!/usr/bin/env python3
"""Rank calibrated cases by repeatable separation between participant profiles."""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
from typing import Any

INPUT_SCHEMAS = {
    "agentlab.case_discrimination_input.v1": (
        "agentlab.case_discrimination_report.v1",
        "sourceRevision",
        re.compile(r"[0-9a-f]{40}"),
    ),
    "agentlab.case_discrimination_input.v2": (
        "agentlab.case_discrimination_report.v2",
        "sourceSetSha256",
        re.compile(r"[0-9a-f]{64}"),
    ),
}
REVISION = re.compile(r"[0-9a-f]{40}")


def fail(message: str) -> None:
    raise ValueError(message)


def calibration_passed(calibration: Any) -> bool:
    if not isinstance(calibration, dict) or not calibration.get("infrastructureValid"):
        return False
    if calibration.get("baselineExpectedPass") != calibration.get("baselineObservedPass"):
        return False
    if calibration.get("referenceExpectedPass") is not True:
        return False
    if calibration.get("referenceObservedPass") is not True:
        return False
    variants = calibration.get("negativeVariants")
    return (
        isinstance(variants, list)
        and bool(variants)
        and all(
            isinstance(item, dict)
            and item.get("expectedPass") is False
            and item.get("observedPass") is False
            and item.get("infrastructureValid") is True
            for item in variants
        )
    )


def entropy(probability: float) -> float:
    if probability <= 0.0 or probability >= 1.0:
        return 0.0
    return -(probability * math.log2(probability) + (1.0 - probability) * math.log2(1.0 - probability))


def score_case(case: dict[str, Any], required_trials: int, threshold: float) -> dict[str, Any]:
    case_id = case.get("id")
    if not isinstance(case_id, str) or not case_id:
        fail("case id required")
    attempts = case.get("attempts")
    if not isinstance(attempts, list):
        fail(f"{case_id} attempts must be a list")

    profiles: dict[str, list[bool]] = {}
    excluded: list[dict[str, str]] = []
    seen_attempts: set[str] = set()
    for attempt in attempts:
        if not isinstance(attempt, dict):
            fail(f"{case_id} attempt must be object")
        attempt_id = attempt.get("attemptId")
        participant_id = attempt.get("participantId")
        if not isinstance(attempt_id, str) or not attempt_id or attempt_id in seen_attempts:
            fail(f"{case_id} attemptId must be unique")
        seen_attempts.add(attempt_id)
        if not isinstance(participant_id, str) or not participant_id:
            fail(f"{case_id} participantId required")
        if attempt.get("infrastructureValid") is not True:
            excluded.append({"attemptId": attempt_id, "reason": "infrastructure-invalid"})
            continue
        verdict = attempt.get("taskPassed")
        if not isinstance(verdict, bool):
            excluded.append({"attemptId": attempt_id, "reason": "missing-independent-verdict"})
            continue
        profiles.setdefault(participant_id, []).append(verdict)

    profile_rows = []
    for participant_id, verdicts in sorted(profiles.items()):
        passed = sum(verdicts)
        count = len(verdicts)
        rate = passed / count
        profile_rows.append(
            {
                "participantId": participant_id,
                "validTrials": count,
                "passedTrials": passed,
                "passRate": rate,
                "withinProfileDeterminism": abs(2.0 * rate - 1.0),
            }
        )

    rates = [row["passRate"] for row in profile_rows]
    trials = [row["validTrials"] for row in profile_rows]
    separation = max(rates) - min(rates) if len(rates) >= 2 else 0.0
    total = sum(trials)
    overall_rate = (
        sum(row["passedTrials"] for row in profile_rows) / total if total else 0.0
    )
    determinism = (
        sum(row["withinProfileDeterminism"] * row["validTrials"] for row in profile_rows)
        / total
        if total
        else 0.0
    )
    minimum_trials = min(trials) if trials else 0
    confidence = min(1.0, minimum_trials / required_trials)
    score = separation * determinism * confidence
    calibrated = calibration_passed(case.get("calibration"))
    evidence_complete = len(profile_rows) >= 2 and minimum_trials >= required_trials
    eligible = calibrated and evidence_complete and score >= threshold
    if not calibrated:
        decision = "reject-oracle-calibration"
    elif not evidence_complete:
        decision = "collect-more-evidence"
    elif eligible:
        decision = "high-discrimination-candidate"
    else:
        decision = "low-discrimination-candidate"

    return {
        "caseId": case_id,
        "calibrationPassed": calibrated,
        "validAttemptCount": total,
        "excludedAttemptCount": len(excluded),
        "excludedAttempts": excluded,
        "participantProfiles": profile_rows,
        "metrics": {
            "passRateSeparation": separation,
            "withinProfileDeterminism": determinism,
            "trialConfidence": confidence,
            "outcomeEntropy": entropy(overall_rate),
            "discriminationScore": score,
        },
        "evidenceComplete": evidence_complete,
        "eligible": eligible,
        "decision": decision,
    }


def build_report(value: dict[str, Any], required_trials: int, threshold: float) -> dict[str, Any]:
    input_contract = INPUT_SCHEMAS.get(value.get("schema"))
    if input_contract is None:
        fail("unsupported case discrimination input schema")
    output_schema, source_identity_field, source_identity_pattern = input_contract
    source_identity = value.get(source_identity_field)
    if not isinstance(source_identity, str) or not source_identity_pattern.fullmatch(source_identity):
        if source_identity_field == "sourceRevision":
            fail("sourceRevision must be a lowercase 40-character Git revision")
        fail("sourceSetSha256 must be a lowercase 64-character SHA-256 digest")
    method_revision = value.get("methodRevision")
    if not isinstance(method_revision, str) or not REVISION.fullmatch(method_revision):
        fail("methodRevision must be a lowercase 40-character Git revision")
    if required_trials < 1:
        fail("required trials must be positive")
    if not 0.0 <= threshold <= 1.0:
        fail("threshold must be in 0..1")
    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        fail("cases required")
    rows = [score_case(case, required_trials, threshold) for case in cases]
    rows.sort(
        key=lambda row: (
            not row["eligible"],
            -row["metrics"]["discriminationScore"],
            row["caseId"],
        )
    )
    return {
        "schema": output_schema,
        source_identity_field: source_identity,
        "methodRevision": method_revision,
        "denominators": {
            "requiredTrialsPerParticipant": required_trials,
            "minimumParticipantProfiles": 2,
            "eligibilityThreshold": threshold,
            "successEvent": "independent taskPassed verdict from infrastructure-valid attempt",
        },
        "ranking": rows,
        "eligibleCaseIds": [row["caseId"] for row in rows if row["eligible"]],
        "policy": {
            "automaticPromotion": False,
            "nextAction": "maintainer-review-then-freeze-new-case-cut",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--required-trials", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.6)
    args = parser.parse_args()
    value = json.loads(args.input.read_text(encoding="utf-8"))
    report = build_report(value, args.required_trials, args.threshold)
    body = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            fail(f"refusing to overwrite existing output: {args.output}")
        args.output.write_text(body, encoding="utf-8")
    else:
        print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
