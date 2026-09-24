#!/usr/bin/env python3
"""Rank calibrated cases by repeatable separation between participant profiles."""
from __future__ import annotations

import argparse
import hashlib
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


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


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


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> dict[str, float]:
    if not 0 <= successes <= total or total < 1:
        fail("Wilson interval denominator is invalid")
    probability = successes / total
    denominator = 1.0 + z * z / total
    center = (probability + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            probability * (1.0 - probability) / total
            + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return {
        "confidenceLevel": 0.95,
        "lower": max(0.0, center - margin),
        "upper": min(1.0, center + margin),
    }


def validate_process_measurement(value: Any, case_id: str, attempt_id: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("schema") != "agentlab.assessment_process_measurement.v1":
        fail(f"{case_id} {attempt_id} process measurement schema differs")
    integer_fields = (
        "stageCount",
        "participantCompletedStageCount",
        "oracleExecutedStageCount",
        "oraclePassedStageCount",
        "scopeViolationStageCount",
        "changedPathCount",
        "unauthorizedPathCount",
        "oracleRecoveryCount",
        "oracleRegressionCount",
        "participantDurationMs",
        "oracleDurationMs",
        "stageDurationMs",
        "attemptDurationMs",
    )
    if not all(isinstance(value.get(field), int) and value[field] >= 0 for field in integer_fields):
        fail(f"{case_id} {attempt_id} process measurement is invalid")
    if value.get("processMeasurementQualified") is not True or value["stageCount"] < 1:
        fail(f"{case_id} {attempt_id} process measurement is not qualified")
    if value["participantCompletedStageCount"] > value["stageCount"]:
        fail(f"{case_id} {attempt_id} completed stage count is invalid")
    if value["oraclePassedStageCount"] > value["oracleExecutedStageCount"]:
        fail(f"{case_id} {attempt_id} Oracle stage count is invalid")
    self_assessment = value.get("participantSelfAssessment")
    if self_assessment is not None:
        if (
            not isinstance(self_assessment, dict)
            or self_assessment.get("schema")
            != "agentlab.participant_self_assessment_summary.v1"
            or self_assessment.get("authority")
            != "participant-claim-compared-with-operator-oracle-not-a-verdict"
        ):
            fail(f"{case_id} {attempt_id} participant self-assessment summary is invalid")
        counts = (
            "stageCount",
            "reportedStageCount",
            "comparableStageCount",
            "agreementCount",
        )
        if not all(
            isinstance(self_assessment.get(field), int)
            and self_assessment[field] >= 0
            for field in counts
        ):
            fail(f"{case_id} {attempt_id} participant self-assessment counts are invalid")
        if not (
            self_assessment["stageCount"] == value["stageCount"]
            and self_assessment["agreementCount"]
            <= self_assessment["comparableStageCount"]
            <= self_assessment["reportedStageCount"]
            <= self_assessment["stageCount"]
            and self_assessment.get("coverageRate")
            == self_assessment["reportedStageCount"] / self_assessment["stageCount"]
            and self_assessment.get("coverageQualified")
            is (
                self_assessment["comparableStageCount"]
                == self_assessment["stageCount"]
            )
        ):
            fail(f"{case_id} {attempt_id} participant self-assessment coverage differs")
        comparable = self_assessment["comparableStageCount"]
        expected_agreement = (
            self_assessment["agreementCount"] / comparable if comparable else None
        )
        if self_assessment.get("agreementRate") != expected_agreement:
            fail(f"{case_id} {attempt_id} participant self-assessment agreement differs")
        brier = self_assessment.get("meanBrierScore")
        if comparable and (
            not isinstance(brier, (int, float))
            or isinstance(brier, bool)
            or not 0.0 <= brier <= 1.0
        ):
            fail(f"{case_id} {attempt_id} participant self-assessment Brier score is invalid")
        if not comparable and brier is not None:
            fail(f"{case_id} {attempt_id} participant self-assessment Brier score differs")
    return value


def score_case(case: dict[str, Any], required_trials: int, threshold: float) -> dict[str, Any]:
    case_id = case.get("id")
    if not isinstance(case_id, str) or not case_id:
        fail("case id required")
    attempts = case.get("attempts")
    if not isinstance(attempts, list):
        fail(f"{case_id} attempts must be a list")

    profiles: dict[str, list[dict[str, Any]]] = {}
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
        process = validate_process_measurement(
            attempt.get("processMeasurement"), case_id, attempt_id
        )
        profiles.setdefault(participant_id, []).append(
            {"verdict": verdict, "process": process}
        )

    profile_rows = []
    for participant_id, attempt_rows in sorted(profiles.items()):
        verdicts = [row["verdict"] for row in attempt_rows]
        process_rows = [row["process"] for row in attempt_rows if row["process"] is not None]
        self_assessment_rows = [
            row["participantSelfAssessment"]
            for row in process_rows
            if isinstance(row.get("participantSelfAssessment"), dict)
        ]
        self_assessment_comparable = sum(
            row["comparableStageCount"] for row in self_assessment_rows
        )
        self_assessment_agreement = sum(
            row["agreementCount"] for row in self_assessment_rows
        )
        passed = sum(verdicts)
        count = len(attempt_rows)
        rate = passed / count
        measured = len(process_rows)
        profile_rows.append(
            {
                "participantId": participant_id,
                "validTrials": count,
                "passedTrials": passed,
                "passRate": rate,
                "passRateWilson95": wilson_interval(passed, count),
                "withinProfileDeterminism": abs(2.0 * rate - 1.0),
                "processMeasurement": {
                    "measuredTrials": measured,
                    "coverageRate": measured / count,
                    "coverageQualified": measured == count,
                    "meanAttemptDurationMs": (
                        sum(row["attemptDurationMs"] for row in process_rows) / measured
                        if measured
                        else None
                    ),
                    "meanChangedPathCount": (
                        sum(row["changedPathCount"] for row in process_rows) / measured
                        if measured
                        else None
                    ),
                    "totalOracleRecoveryCount": sum(
                        row["oracleRecoveryCount"] for row in process_rows
                    ),
                    "totalOracleRegressionCount": sum(
                        row["oracleRegressionCount"] for row in process_rows
                    ),
                    "totalScopeViolationStageCount": sum(
                        row["scopeViolationStageCount"] for row in process_rows
                    ),
                    "participantSelfAssessment": {
                        "measuredTrials": len(self_assessment_rows),
                        "coverageRate": len(self_assessment_rows) / count,
                        "coverageQualified": len(self_assessment_rows) == count,
                        "stageCount": sum(
                            row["stageCount"] for row in self_assessment_rows
                        ),
                        "reportedStageCount": sum(
                            row["reportedStageCount"] for row in self_assessment_rows
                        ),
                        "comparableStageCount": sum(
                            row["comparableStageCount"] for row in self_assessment_rows
                        ),
                        "agreementCount": sum(
                            row["agreementCount"] for row in self_assessment_rows
                        ),
                        "agreementRate": (
                            self_assessment_agreement / self_assessment_comparable
                            if self_assessment_comparable
                            else None
                        ),
                        "meanBrierScore": (
                            sum(
                                row["meanBrierScore"] * row["comparableStageCount"]
                                for row in self_assessment_rows
                                if row["meanBrierScore"] is not None
                            )
                            / self_assessment_comparable
                            if self_assessment_comparable
                            else None
                        ),
                        "authority": "participant-claim-compared-with-operator-oracle-not-a-verdict",
                    },
                },
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
    process_measured = sum(
        row["processMeasurement"]["measuredTrials"] for row in profile_rows
    )
    self_assessment_profiles = [
        row["processMeasurement"]["participantSelfAssessment"]
        for row in profile_rows
    ]
    self_assessment_measured = sum(
        row["measuredTrials"] for row in self_assessment_profiles
    )
    self_assessment_comparable = sum(
        row["comparableStageCount"] for row in self_assessment_profiles
    )
    self_assessment_agreement = sum(
        row["agreementCount"] for row in self_assessment_profiles
    )
    process_coverage_qualified = total > 0 and process_measured == total
    if len(profile_rows) >= 2:
        highest = max(profile_rows, key=lambda row: (row["passRate"], row["participantId"]))
        lowest = min(profile_rows, key=lambda row: (row["passRate"], row["participantId"]))
        extreme_intervals_separated = (
            highest["passRateWilson95"]["lower"]
            > lowest["passRateWilson95"]["upper"]
        )
    else:
        extreme_intervals_separated = False
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
            "observedExtremePassRateWilson95Separated": extreme_intervals_separated,
        },
        "processMeasurement": {
            "validAttemptCount": total,
            "measuredAttemptCount": process_measured,
            "coverageRate": process_measured / total if total else 0.0,
            "coverageQualified": process_coverage_qualified,
            "participantSelfAssessment": {
                "measuredAttemptCount": self_assessment_measured,
                "coverageRate": self_assessment_measured / total if total else 0.0,
                "coverageQualified": total > 0 and self_assessment_measured == total,
                "stageCount": sum(row["stageCount"] for row in self_assessment_profiles),
                "reportedStageCount": sum(
                    row["reportedStageCount"] for row in self_assessment_profiles
                ),
                "comparableStageCount": self_assessment_comparable,
                "agreementCount": sum(
                    row["agreementCount"] for row in self_assessment_profiles
                ),
                "agreementRate": (
                    self_assessment_agreement / self_assessment_comparable
                    if self_assessment_comparable
                    else None
                ),
                "meanBrierScore": (
                    sum(
                        row["meanBrierScore"] * row["comparableStageCount"]
                        for row in self_assessment_profiles
                        if row["meanBrierScore"] is not None
                    )
                    / self_assessment_comparable
                    if self_assessment_comparable
                    else None
                ),
                "authority": "participant-claim-compared-with-operator-oracle-not-a-verdict",
            },
            "note": "Operator-owned stage timing, change, scope and Oracle transition evidence. Optional participant self-assessment is a claim compared with the independent Oracle, not a verdict.",
        },
        "evidenceComplete": evidence_complete,
        "eligible": eligible,
        "processAwareEligible": eligible and process_coverage_qualified,
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
        "inputSha256": canonical_sha256(value),
        "denominators": {
            "requiredTrialsPerParticipant": required_trials,
            "minimumParticipantProfiles": 2,
            "eligibilityThreshold": threshold,
            "successEvent": "independent taskPassed verdict from infrastructure-valid attempt",
            "processMeasurementEvent": "operator-owned per-stage timing, changed paths, scope verdict and Oracle transition evidence",
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
