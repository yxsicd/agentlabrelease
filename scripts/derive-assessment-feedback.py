#!/usr/bin/env python3
"""Derive review-required difficulty candidates from assessed case attempts."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import re
from collections import defaultdict
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


def fail(message: str) -> None:
    raise ValueError(message)


def load(path: pathlib.Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        fail(f"{label} not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def evidence_path(root: pathlib.Path, reference: Any, label: str) -> pathlib.Path:
    if not isinstance(reference, dict):
        fail(f"{label} evidence reference is absent")
    value = reference.get("path")
    expected_digest = reference.get("sha256")
    expected_bytes = reference.get("byteLength")
    if not isinstance(value, str) or not value:
        fail(f"{label} evidence path is absent")
    relative = pathlib.Path(value)
    if relative.is_absolute():
        fail(f"{label} evidence path must be relative")
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        fail(f"{label} evidence path escapes the input directory")
    if not path.is_file():
        fail(f"{label} evidence is absent")
    if not isinstance(expected_digest, str) or not SHA256.fullmatch(expected_digest):
        fail(f"{label} evidence digest is invalid")
    if sha256(path) != expected_digest or path.stat().st_size != expected_bytes:
        fail(f"{label} evidence bytes differ from the collected input")
    return path


def failure_mode(stage: dict[str, Any]) -> str | None:
    scope_valid = stage.get("scopeValid")
    oracle_pass = stage.get("oraclePass")
    if not isinstance(scope_valid, bool) or not isinstance(oracle_pass, bool):
        fail("assessed phase verdict requires boolean scopeValid and oraclePass")
    if scope_valid and oracle_pass:
        return None
    if not scope_valid and not oracle_pass:
        return "scope-drift-and-oracle-failure"
    if not scope_valid:
        return "scope-drift"
    return "oracle-failure"


def performance_separation_candidates(
    rank: dict[str, Any], case_id: str, source_set: str
) -> list[dict[str, Any]]:
    harmony = (rank.get("processMeasurement") or {}).get("harmonyDevice")
    if not isinstance(harmony, dict) or harmony.get("performanceFeedbackQualified") is not True:
        return []
    profiles = rank.get("participantProfiles")
    if not isinstance(profiles, list):
        fail("discrimination report participant profiles are invalid")
    grouped: dict[tuple[str, str, str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for profile in profiles:
        if not isinstance(profile, dict):
            fail("discrimination report participant profile is invalid")
        participant_id = profile.get("participantId")
        valid_trials = profile.get("validTrials")
        passed_trials = profile.get("passedTrials")
        feedback = ((profile.get("processMeasurement") or {}).get("harmonyDevice") or {}).get(
            "performanceFeedback"
        )
        if (
            not isinstance(participant_id, str)
            or not participant_id
            or not isinstance(valid_trials, int)
            or isinstance(valid_trials, bool)
            or valid_trials < 1
            or not isinstance(passed_trials, int)
            or isinstance(passed_trials, bool)
            or not 0 <= passed_trials <= valid_trials
        ):
            fail("discrimination report participant trial counts are invalid")
        if passed_trials == 0:
            continue
        if not isinstance(feedback, dict) or feedback.get("repeatabilityQualified") is not True:
            fail("qualified performance aggregate contains an unqualified successful profile")
        observed_trials = feedback.get("observedTrials")
        identity = feedback.get("identity")
        metrics = feedback.get("metrics")
        authority = feedback.get("authority")
        if (
            not isinstance(observed_trials, int)
            or observed_trials != passed_trials
            or observed_trials < 2
            or feedback.get("successfulTrialCoverageQualified") is not True
            or feedback.get("identityConsistent") is not True
            or not isinstance(identity, dict)
            or set(identity)
            != {"environmentIdentity", "performancePolicySha256", "profileWorkloadSha256"}
            or not all(isinstance(identity.get(field), str) and identity[field] for field in identity)
            or not SHA256.fullmatch(identity["performancePolicySha256"])
            or not SHA256.fullmatch(identity["profileWorkloadSha256"])
            or not isinstance(metrics, dict)
            or not metrics
            or authority
            != {
                "functional": "none",
                "relativePerformance": "smartperf-emulator-proxy",
                "absolutePowerThermal": "unavailable-on-emulator",
            }
        ):
            fail("qualified participant performance feedback is invalid")
        for metric_name, metric in metrics.items():
            if not isinstance(metric_name, str) or not metric_name or not isinstance(metric, dict):
                fail("participant performance metric is invalid")
            statistic = metric.get("statistic")
            unit = metric.get("unit")
            direction = metric.get("direction")
            values = (metric.get("min"), metric.get("max"), metric.get("mean"))
            if (
                statistic not in {"mean", "p50", "p95"}
                or not isinstance(unit, str)
                or not unit
                or direction not in {"lower", "higher"}
                or metric.get("observedTrials") != observed_trials
                or not all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(value)
                    for value in values
                )
                or not values[0] <= values[2] <= values[1]
            ):
                fail("participant performance metric summary is invalid")
            key = (
                identity["environmentIdentity"],
                identity["performancePolicySha256"],
                identity["profileWorkloadSha256"],
                metric_name,
                statistic,
                unit,
                direction,
            )
            grouped[key].append(
                {
                    "participantId": participant_id,
                    "validAttemptCount": valid_trials,
                    "successfulAttemptCount": passed_trials,
                    "observedTrialCount": observed_trials,
                    "min": values[0],
                    "max": values[1],
                    "mean": values[2],
                    "sampleStandardDeviation": metric.get("sampleStandardDeviation"),
                    "coefficientOfVariation": metric.get("coefficientOfVariation"),
                }
            )

    candidates = []
    for key, observations in sorted(grouped.items()):
        if len(observations) < 2:
            continue
        environment, policy, workload, metric_name, statistic, unit, direction = key
        ordered = sorted(
            observations,
            key=lambda row: (row["mean"], row["participantId"]),
            reverse=direction == "higher",
        )
        best = ordered[0]
        worst = ordered[-1]
        ranges_separated = (
            best["max"] < worst["min"]
            if direction == "lower"
            else best["min"] > worst["max"]
        )
        if not ranges_separated:
            continue
        difference = (
            worst["mean"] - best["mean"]
            if direction == "lower"
            else best["mean"] - worst["mean"]
        )
        identity = canonical_sha256(
            {
                "caseId": case_id,
                "sourceSetSha256": source_set,
                "environmentIdentity": environment,
                "performancePolicySha256": policy,
                "profileWorkloadSha256": workload,
                "metric": metric_name,
                "statistic": statistic,
                "direction": direction,
                "participants": [row["participantId"] for row in ordered],
            }
        )[:20]
        candidates.append(
            {
                "id": f"assessment-feedback-{identity}",
                "dimensionId": "assessed-agent-performance-separation",
                "primaryDimension": "performance-feedback",
                "mechanism": (
                    f"repeatable non-overlapping {metric_name} {statistic} ranges "
                    f"under one frozen Harmony performance identity"
                ),
                "status": "candidate",
                "maturityState": "candidate",
                "caseId": case_id,
                "stageId": "harmony-device",
                "failureMode": "repeatable-performance-separation",
                "validAttemptCount": sum(row["validAttemptCount"] for row in observations),
                "participantProfiles": ordered,
                "observations": ordered,
                "performanceEvidence": {
                    "environmentIdentity": environment,
                    "performancePolicySha256": policy,
                    "profileWorkloadSha256": workload,
                    "metric": metric_name,
                    "statistic": statistic,
                    "unit": unit,
                    "direction": direction,
                    "bestParticipantId": best["participantId"],
                    "worstParticipantId": worst["participantId"],
                    "meanDifference": difference,
                    "rangesSeparated": True,
                    "authority": {
                        "functional": "none",
                        "relativePerformance": "smartperf-emulator-proxy",
                        "absolutePowerThermal": "unavailable-on-emulator",
                    },
                },
                "caseSelection": {
                    "decision": rank.get("decision"),
                    "eligible": bool(rank.get("eligible")),
                    "discriminationScore": (rank.get("metrics") or {}).get(
                        "discriminationScore"
                    ),
                },
                "verificationContract": {
                    "caseReady": False,
                    "required": [
                        "maintainer-adjudication",
                        "new-source-and-analysis-cut",
                        "independent-oracle-calibration",
                        "independent-performance-calibration",
                    ],
                },
                "automaticPromotion": False,
            }
        )
    return candidates


def build_feedback(
    case: dict[str, Any], collected: dict[str, Any], report: dict[str, Any], root: pathlib.Path
) -> dict[str, Any]:
    root = root.resolve()
    if case.get("schema") != "agentlab.multi_repo_evaluation_case.v1":
        fail("unsupported evaluation case schema")
    if case.get("status") != "frozen-calibrated" or case.get("automaticPromotion") is not False:
        fail("feedback requires a frozen calibrated non-promoted case")
    if collected.get("schema") != "agentlab.case_discrimination_input.v2":
        fail("feedback requires v2 multi-repository discrimination input")
    if report.get("schema") != "agentlab.case_discrimination_report.v2":
        fail("feedback requires v2 multi-repository discrimination report")

    source_set = case.get("sourceSetSha256")
    method_revision = collected.get("methodRevision")
    if not isinstance(source_set, str) or not SHA256.fullmatch(source_set):
        fail("case sourceSetSha256 is invalid")
    if collected.get("sourceSetSha256") != source_set or report.get("sourceSetSha256") != source_set:
        fail("case, collected input and report source sets differ")
    if not isinstance(method_revision, str) or not REVISION.fullmatch(method_revision):
        fail("collected input methodRevision is invalid")
    if report.get("methodRevision") != method_revision:
        fail("collected input and report method revisions differ")
    input_sha256 = canonical_sha256(collected)
    if report.get("inputSha256") != input_sha256:
        fail("discrimination report does not bind the exact collected input")
    if (collected.get("collectionPolicy") or {}).get("automaticPromotion") is not False:
        fail("collected input must not auto-promote")
    if (report.get("policy") or {}).get("automaticPromotion") is not False:
        fail("discrimination report must not auto-promote")

    case_id = case.get("id")
    input_cases = [row for row in collected.get("cases", []) if row.get("id") == case_id]
    ranking = [row for row in report.get("ranking", []) if row.get("caseId") == case_id]
    if not isinstance(case_id, str) or not case_id or len(input_cases) != 1 or len(ranking) != 1:
        fail("case must have one collected input and one ranking row")
    input_case = input_cases[0]
    rank = ranking[0]

    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    valid_by_participant: dict[str, int] = defaultdict(int)
    failures_by_group: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for attempt in input_case.get("attempts", []):
        attempt_id = attempt.get("attemptId")
        participant_id = attempt.get("participantId")
        if not isinstance(attempt_id, str) or not attempt_id:
            fail("collected attempt id is invalid")
        if not isinstance(participant_id, str) or not participant_id:
            fail(f"{attempt_id} participant id is invalid")
        if attempt.get("verdictSource") != "independent-harness-decision-package":
            fail(f"{attempt_id} is not a Harness-assessed multi-repository attempt")
        if attempt.get("infrastructureValid") is not True:
            continue
        verdict = attempt.get("taskPassed")
        if not isinstance(verdict, bool):
            fail(f"{attempt_id} valid attempt has no boolean verdict")
        valid_by_participant[participant_id] += 1
        decision_path = evidence_path(
            root, (attempt.get("evidence") or {}).get("decisionPackage"), f"{attempt_id} decision package"
        )
        decision = load(decision_path, f"{attempt_id} decision package")
        if (
            decision.get("schema") != "agentlab.harness_decision_package.v1"
            or decision.get("taskId") != case_id
            or decision.get("sourceSetSha256") != source_set
            or decision.get("assessmentStatus") != "assessed"
            or decision.get("infrastructureAvailable") is not True
            or decision.get("subjectTaskSucceeded") is not verdict
            or decision.get("automaticPromotion") is not False
        ):
            fail(f"{attempt_id} decision package contradicts collected evidence")
        phase_verdicts = decision.get("phaseVerdicts")
        if not isinstance(phase_verdicts, list) or not phase_verdicts:
            fail(f"{attempt_id} decision package has no phase verdicts")
        observed_failure = False
        for stage in phase_verdicts:
            if not isinstance(stage, dict):
                fail(f"{attempt_id} phase verdict is invalid")
            stage_id = stage.get("stageId")
            if not isinstance(stage_id, str) or not stage_id:
                fail(f"{attempt_id} phase verdict has no stageId")
            mode = failure_mode(stage)
            if mode is None:
                continue
            observed_failure = True
            key = (stage_id, mode)
            grouped[key].append(
                {
                    "attemptId": attempt_id,
                    "participantId": participant_id,
                    "decisionPackageSha256": sha256(decision_path),
                }
            )
            failures_by_group[key][participant_id] += 1
        if verdict is False and not observed_failure:
            fail(f"{attempt_id} failing verdict has no failing phase")
        if verdict is True and observed_failure:
            fail(f"{attempt_id} passing verdict contains a failing phase")

    candidates = []
    for (stage_id, mode), observations in sorted(grouped.items()):
        identity = canonical_sha256(
            {"caseId": case_id, "sourceSetSha256": source_set, "stageId": stage_id, "failureMode": mode}
        )[:20]
        participant_profiles = []
        for participant_id in sorted(valid_by_participant):
            failed = failures_by_group[(stage_id, mode)].get(participant_id, 0)
            valid = valid_by_participant[participant_id]
            participant_profiles.append(
                {
                    "participantId": participant_id,
                    "validAttemptCount": valid,
                    "failingAttemptCount": failed,
                    "failureRate": failed / valid,
                }
            )
        candidates.append(
            {
                "id": f"assessment-feedback-{identity}",
                "dimensionId": "assessed-agent-stage-failure",
                "primaryDimension": "evaluation-feedback",
                "mechanism": f"{mode} at frozen stage {stage_id}",
                "status": "candidate",
                "maturityState": "candidate",
                "caseId": case_id,
                "stageId": stage_id,
                "failureMode": mode,
                "validAttemptCount": sum(valid_by_participant.values()),
                "failingAttemptCount": len(observations),
                "participantProfiles": participant_profiles,
                "observations": observations,
                "caseSelection": {
                    "decision": rank.get("decision"),
                    "eligible": bool(rank.get("eligible")),
                    "discriminationScore": (rank.get("metrics") or {}).get("discriminationScore"),
                },
                "verificationContract": {
                    "caseReady": False,
                    "required": [
                        "maintainer-adjudication",
                        "new-source-and-analysis-cut",
                        "independent-oracle-calibration",
                    ],
                },
                "automaticPromotion": False,
            }
        )

    candidates.extend(performance_separation_candidates(rank, case_id, source_set))
    candidates.sort(key=lambda row: row["id"])

    return {
        "schema": "agentlab.assessment_feedback_candidates.v1",
        "caseId": case_id,
        "sourceSetSha256": source_set,
        "methodRevision": method_revision,
        "caseSha256": canonical_sha256(case),
        "discriminationInputSha256": input_sha256,
        "discriminationReportSha256": canonical_sha256(report),
        "validAttemptCount": sum(valid_by_participant.values()),
        "candidateCount": len(candidates),
        "candidates": candidates,
        "policy": {
            "automaticPromotion": False,
            "nextAction": "maintainer-adjudicate-for-next-analysis-cut",
            "infrastructureFailuresExcluded": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=pathlib.Path, required=True)
    parser.add_argument("--input", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        fail(f"refusing to overwrite existing output: {args.output}")
    case = load(args.case, "evaluation case")
    collected = load(args.input, "discrimination input")
    report = load(args.report, "discrimination report")
    value = build_feedback(case, collected, report, args.input.resolve().parent)
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "candidateCount": value["candidateCount"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
