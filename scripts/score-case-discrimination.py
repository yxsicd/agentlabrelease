#!/usr/bin/env python3
"""Rank calibrated cases by repeatable separation between participant profiles."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import re
import statistics
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
    negative_valid = (
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
    alternatives = calibration.get("alternativeValidVariants")
    alternative_valid = alternatives is None or (
        isinstance(alternatives, list)
        and bool(alternatives)
        and all(
            isinstance(item, dict)
            and item.get("expectedPass") is True
            and item.get("observedPass") is True
            and item.get("infrastructureValid") is True
            for item in alternatives
        )
    )
    return negative_valid and alternative_valid


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
    dependency = value.get("dependencyDiscovery")
    if dependency is not None:
        if (
            not isinstance(dependency, dict)
            or dependency.get("schema") != "agentlab.dependency_discovery_summary.v1"
            or dependency.get("authority")
            != "hidden-revision-bound-program-fact-obligations-not-gold-path-imitation"
            or dependency.get("precisionClaimed") is not False
        ):
            fail(f"{case_id} {attempt_id} dependency discovery summary is invalid")
        counts = (
            "stageCount",
            "measuredStageCount",
            "missingStageCount",
            "invalidStageCount",
            "claimCount",
            "obligationCount",
            "coveredObligationCount",
            "unadjudicatedClaimCount",
        )
        if not all(
            isinstance(dependency.get(field), int) and dependency[field] >= 0
            for field in counts
        ):
            fail(f"{case_id} {attempt_id} dependency discovery counts are invalid")
        obligations = dependency["obligationCount"]
        covered = dependency["coveredObligationCount"]
        if not (
            dependency["stageCount"] == value["stageCount"]
            and dependency["measuredStageCount"] <= dependency["stageCount"]
            and dependency["measuredStageCount"]
            + dependency["missingStageCount"]
            + dependency["invalidStageCount"]
            == dependency["stageCount"]
            and covered <= obligations
            and dependency["unadjudicatedClaimCount"] <= dependency["claimCount"]
            and dependency.get("requiredObligationCoverage")
            == (covered / obligations if obligations else None)
            and dependency.get("coverageQualified")
            is (
                dependency["measuredStageCount"] == dependency["stageCount"]
                and bool(obligations)
                and covered == obligations
            )
        ):
            fail(f"{case_id} {attempt_id} dependency discovery derivation differs")
    return value


def validate_stage_coverage(
    value: Any,
    process: dict[str, Any] | None,
    verdict: bool,
    case_id: str,
    attempt_id: str,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if process is None:
        fail(f"{case_id} {attempt_id} stage coverage lacks process evidence")
    if (
        not isinstance(value, dict)
        or value.get("schema") != "agentlab.assessment_stage_coverage.v1"
    ):
        fail(f"{case_id} {attempt_id} stage coverage schema differs")
    stage_ids = value.get("stageIds")
    if (
        not isinstance(stage_ids, list)
        or len(stage_ids) != process["stageCount"]
        or len(stage_ids) != len(set(stage_ids))
        or not all(isinstance(stage_id, str) and stage_id for stage_id in stage_ids)
    ):
        fail(f"{case_id} {attempt_id} stage coverage differs from process evidence")
    device = value.get("harmonyDevice")
    if device is None:
        if "harmony-device" in stage_ids:
            fail(f"{case_id} {attempt_id} harmony-device coverage is absent")
        return value
    required_device_keys = {
        "executed", "oraclePass", "profileCollected", "smartPerfSampleCount"
    }
    if (
        not isinstance(device, dict)
        or not required_device_keys.issubset(device)
        or not set(device) <= required_device_keys.union({"performanceObservation"})
        or device.get("executed") is not True
        or not isinstance(device.get("oraclePass"), bool)
        or device["oraclePass"] is not verdict
        or device.get("profileCollected") is not device["oraclePass"]
        or not isinstance(device.get("smartPerfSampleCount"), int)
        or device["smartPerfSampleCount"] < 0
        or stage_ids[-1:] != ["harmony-device"]
        or (
            device["oraclePass"]
            and device["smartPerfSampleCount"] < 1
        )
        or (
            not device["oraclePass"]
            and device["smartPerfSampleCount"] != 0
        )
    ):
        fail(f"{case_id} {attempt_id} harmony-device coverage is invalid")
    observation = device.get("performanceObservation")
    if observation is not None:
        metrics = observation.get("metricValues") if isinstance(observation, dict) else None
        authority = observation.get("authority") if isinstance(observation, dict) else None
        digests = (
            observation.get("performancePolicySha256"),
            observation.get("profileWorkloadSha256"),
            observation.get("smartperfSummarySha256"),
        ) if isinstance(observation, dict) else ()
        valid_metrics = isinstance(metrics, dict) and bool(metrics)
        if valid_metrics:
            for name, metric in metrics.items():
                valid_metrics = (
                    isinstance(name, str)
                    and bool(name)
                    and isinstance(metric, dict)
                    and set(metric) == {"statistic", "value", "unit", "direction"}
                    and metric.get("statistic") in {"mean", "p50", "p95"}
                    and isinstance(metric.get("value"), (int, float))
                    and not isinstance(metric.get("value"), bool)
                    and math.isfinite(metric["value"])
                    and isinstance(metric.get("unit"), str)
                    and bool(metric["unit"])
                    and metric.get("direction") in {"lower", "higher"}
                )
                if not valid_metrics:
                    break
        if (
            not isinstance(observation, dict)
            or set(observation)
            != {
                "schema",
                "environmentIdentity",
                "performancePolicySha256",
                "profileWorkloadSha256",
                "smartperfSummarySha256",
                "sampleCount",
                "metricValues",
                "authority",
            }
            or observation.get("schema")
            != "agentlab.harmony_performance_observation.v1"
            or not isinstance(observation.get("environmentIdentity"), str)
            or not observation["environmentIdentity"]
            or len(digests) != 3
            or not all(
                isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
                for value in digests
            )
            or observation.get("sampleCount") != device["smartPerfSampleCount"]
            or not valid_metrics
            or authority
            != {
                "functional": "none",
                "relativePerformance": "smartperf-emulator-proxy",
                "absolutePowerThermal": "unavailable-on-emulator",
            }
            or device["oraclePass"] is not True
        ):
            fail(f"{case_id} {attempt_id} performance observation is invalid")
    return value


def summarize_performance_observations(
    device_rows: list[dict[str, Any]], successful_attempts: int
) -> dict[str, Any]:
    observations = [
        row["performanceObservation"]
        for row in device_rows
        if isinstance(row.get("performanceObservation"), dict)
    ]
    identities = {
        (
            row["environmentIdentity"],
            row["performancePolicySha256"],
            row["profileWorkloadSha256"],
        )
        for row in observations
    }
    identity_consistent = len(identities) <= 1
    metric_name_sets = {frozenset(row["metricValues"]) for row in observations}
    if len(metric_name_sets) > 1:
        identity_consistent = False
    coverage_qualified = (
        successful_attempts > 0 and len(observations) == successful_attempts
    )
    metric_names = (
        set.intersection(*(set(row["metricValues"]) for row in observations))
        if observations
        else set()
    )
    metrics: dict[str, Any] = {}
    for name in sorted(metric_names):
        definitions = {
            (
                row["metricValues"][name]["statistic"],
                row["metricValues"][name]["unit"],
                row["metricValues"][name]["direction"],
            )
            for row in observations
        }
        if len(definitions) != 1:
            identity_consistent = False
            continue
        statistic, unit, direction = next(iter(definitions))
        values = [float(row["metricValues"][name]["value"]) for row in observations]
        mean = statistics.fmean(values)
        deviation = statistics.stdev(values) if len(values) >= 2 else None
        metrics[name] = {
            "statistic": statistic,
            "unit": unit,
            "direction": direction,
            "observedTrials": len(values),
            "min": min(values),
            "max": max(values),
            "mean": mean,
            "sampleStandardDeviation": deviation,
            "coefficientOfVariation": (
                deviation / abs(mean)
                if deviation is not None and mean != 0.0
                else None
            ),
        }
    repeatability_qualified = (
        coverage_qualified
        and identity_consistent
        and len(observations) >= 2
        and bool(metrics)
    )
    identity = None
    if len(identities) == 1:
        environment, policy, workload = next(iter(identities))
        identity = {
            "environmentIdentity": environment,
            "performancePolicySha256": policy,
            "profileWorkloadSha256": workload,
        }
    return {
        "observedTrials": len(observations),
        "successfulTrialCoverageQualified": coverage_qualified,
        "identityConsistent": identity_consistent,
        "repeatabilityQualified": repeatability_qualified,
        "identity": identity,
        "metrics": metrics,
        "authority": {
            "functional": "none",
            "relativePerformance": "smartperf-emulator-proxy",
            "absolutePowerThermal": "unavailable-on-emulator",
        },
    }


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
        stage_coverage = validate_stage_coverage(
            attempt.get("stageCoverage"), process, verdict, case_id, attempt_id
        )
        profiles.setdefault(participant_id, []).append(
            {
                "verdict": verdict,
                "process": process,
                "stageCoverage": stage_coverage,
            }
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
        dependency_rows = [
            row["dependencyDiscovery"]
            for row in process_rows
            if isinstance(row.get("dependencyDiscovery"), dict)
        ]
        dependency_measured_rows = [
            row
            for row in dependency_rows
            if row["measuredStageCount"] == row["stageCount"]
        ]
        dependency_obligations = sum(
            row["obligationCount"] for row in dependency_rows
        )
        dependency_covered = sum(
            row["coveredObligationCount"] for row in dependency_rows
        )
        device_rows = [
            row["stageCoverage"]["harmonyDevice"]
            for row in attempt_rows
            if isinstance(row.get("stageCoverage"), dict)
            and isinstance(row["stageCoverage"].get("harmonyDevice"), dict)
        ]
        successful_attempts = sum(row["verdict"] for row in attempt_rows)
        successful_device_rows = sum(row["oraclePass"] for row in device_rows)
        profiled_successful_device_rows = sum(
            row["oraclePass"] and row["profileCollected"]
            for row in device_rows
        )
        performance_feedback = summarize_performance_observations(
            device_rows, successful_attempts
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
                    "dependencyDiscovery": {
                        "measuredTrials": len(dependency_measured_rows),
                        "coverageRate": len(dependency_measured_rows) / count,
                        "measurementCoverageQualified": len(dependency_measured_rows) == count,
                        "missingStageCount": sum(
                            row["missingStageCount"] for row in dependency_rows
                        ),
                        "invalidStageCount": sum(
                            row["invalidStageCount"] for row in dependency_rows
                        ),
                        "claimCount": sum(row["claimCount"] for row in dependency_rows),
                        "obligationCount": dependency_obligations,
                        "coveredObligationCount": dependency_covered,
                        "requiredObligationCoverage": (
                            dependency_covered / dependency_obligations
                            if dependency_obligations
                            else None
                        ),
                        "coverageQualified": len(dependency_measured_rows) == count
                        and bool(dependency_obligations)
                        and dependency_covered == dependency_obligations,
                        "unadjudicatedClaimCount": sum(
                            row["unadjudicatedClaimCount"] for row in dependency_rows
                        ),
                        "precisionClaimed": False,
                        "authority": "hidden-revision-bound-program-fact-obligations-not-gold-path-imitation",
                    },
                    "harmonyDevice": {
                        "executedTrials": len(device_rows),
                        "successfulTrials": successful_attempts,
                        "successfulDeviceTrials": successful_device_rows,
                        "profiledSuccessfulDeviceTrials": profiled_successful_device_rows,
                        "successfulAttemptDeviceCoverageQualified": (
                            successful_attempts > 0
                            and successful_device_rows == successful_attempts
                        ),
                        "profiledSuccessCoverageQualified": (
                            successful_attempts > 0
                            and profiled_successful_device_rows == successful_attempts
                        ),
                        "smartPerfSampleCount": sum(
                            row["smartPerfSampleCount"] for row in device_rows
                        ),
                        "performanceFeedback": performance_feedback,
                        "authority": "operator-owned-harmony-ui-oracle-with-functional-pass-gated-smartperf",
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
    dependency_profiles = [
        row["processMeasurement"]["dependencyDiscovery"]
        for row in profile_rows
    ]
    dependency_measured = sum(row["measuredTrials"] for row in dependency_profiles)
    dependency_obligations = sum(
        row["obligationCount"] for row in dependency_profiles
    )
    dependency_covered = sum(
        row["coveredObligationCount"] for row in dependency_profiles
    )
    harmony_profiles = [
        row["processMeasurement"]["harmonyDevice"] for row in profile_rows
    ]
    harmony_executed = sum(row["executedTrials"] for row in harmony_profiles)
    successful_attempts = sum(row["successfulTrials"] for row in harmony_profiles)
    successful_device_attempts = sum(
        row["successfulDeviceTrials"] for row in harmony_profiles
    )
    profiled_successful_attempts = sum(
        row["profiledSuccessfulDeviceTrials"] for row in harmony_profiles
    )
    performance_profiles = [row["performanceFeedback"] for row in harmony_profiles]
    successful_performance_profiles = [
        feedback
        for row, feedback in zip(harmony_profiles, performance_profiles)
        if row["successfulTrials"] > 0
    ]
    performance_feedback_qualified = (
        bool(successful_performance_profiles)
        and all(row["repeatabilityQualified"] for row in successful_performance_profiles)
    )
    successful_device_coverage_qualified = (
        successful_attempts > 0
        and successful_device_attempts == successful_attempts
    )
    profiled_success_coverage_qualified = (
        successful_attempts > 0
        and profiled_successful_attempts == successful_attempts
    )
    harmony_end_to_end_qualified = (
        harmony_executed > 0
        and successful_device_coverage_qualified
        and profiled_success_coverage_qualified
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
            "dependencyDiscovery": {
                "measuredAttemptCount": dependency_measured,
                "coverageRate": dependency_measured / total if total else 0.0,
                "measurementCoverageQualified": total > 0
                and dependency_measured == total,
                "missingStageCount": sum(
                    row["missingStageCount"] for row in dependency_profiles
                ),
                "invalidStageCount": sum(
                    row["invalidStageCount"] for row in dependency_profiles
                ),
                "claimCount": sum(row["claimCount"] for row in dependency_profiles),
                "obligationCount": dependency_obligations,
                "coveredObligationCount": dependency_covered,
                "requiredObligationCoverage": (
                    dependency_covered / dependency_obligations
                    if dependency_obligations
                    else None
                ),
                "coverageQualified": total > 0
                and dependency_measured == total
                and bool(dependency_obligations)
                and dependency_covered == dependency_obligations,
                "unadjudicatedClaimCount": sum(
                    row["unadjudicatedClaimCount"] for row in dependency_profiles
                ),
                "precisionClaimed": False,
                "authority": "hidden-revision-bound-program-fact-obligations-not-gold-path-imitation",
            },
            "harmonyDevice": {
                "executedAttemptCount": harmony_executed,
                "successfulAttemptCount": successful_attempts,
                "successfulDeviceAttemptCount": successful_device_attempts,
                "profiledSuccessfulAttemptCount": profiled_successful_attempts,
                "successfulAttemptDeviceCoverageQualified": successful_device_coverage_qualified,
                "profiledSuccessCoverageQualified": profiled_success_coverage_qualified,
                "endToEndEvidenceQualified": harmony_end_to_end_qualified,
                "smartPerfSampleCount": sum(
                    row["smartPerfSampleCount"] for row in harmony_profiles
                ),
                "performanceObservationCount": sum(
                    row["observedTrials"] for row in performance_profiles
                ),
                "repeatablePerformanceProfileCount": sum(
                    row["repeatabilityQualified"] for row in performance_profiles
                ),
                "performanceFeedbackQualified": performance_feedback_qualified,
                "performanceAuthority": {
                    "functional": "none",
                    "relativePerformance": "smartperf-emulator-proxy",
                    "absolutePowerThermal": "unavailable-on-emulator",
                },
                "authority": "operator-owned-harmony-ui-oracle-with-functional-pass-gated-smartperf",
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
