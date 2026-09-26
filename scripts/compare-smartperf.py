#!/usr/bin/env python3
"""Compare two normalized SmartPerf profiles under explicit relative guardrails."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from typing import Any


INPUT_SCHEMAS = {"agentlab.smartperf_summary.v1", "agentlab.smartperf_summary.v2"}
OUTPUT_SCHEMA_V1 = "agentlab.smartperf_comparison.v1"
OUTPUT_SCHEMA_V2 = "agentlab.smartperf_comparison.v2"
OUTPUT_SCHEMA_V3 = "agentlab.smartperf_comparison.v3"
RESULT_SCHEMAS = {
    "agentlab.harmony_emulator_case_result.v2",
    "agentlab.harmony_emulator_case_result.v3",
}
HAP_IDENTITY = re.compile(r"artifact-sha256:([0-9a-f]{64})")


def fail(message: str) -> None:
    raise ValueError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") not in INPUT_SCHEMAS:
        fail(f"unsupported SmartPerf summary: {path}")
    return value


def load_result(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") not in RESULT_SCHEMAS:
        fail(f"unsupported Harmony emulator result: {path}")
    return value


def metric(summary: dict[str, Any], name: str, statistic: str) -> float | None:
    row = (summary.get("canonicalMetrics") or {}).get(name)
    if not isinstance(row, dict):
        return None
    value = row.get(statistic)
    return float(value) if isinstance(value, (int, float)) else None


def canonical_digest(value: dict[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def functional_gate(
    label: str, summary: dict[str, Any], result: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    task_id = summary.get("taskId")
    source_identity = summary.get("sourceIdentity")
    match = HAP_IDENTITY.fullmatch(str(source_identity or ""))
    if match is None:
        fail(f"{label} summary requires exact artifact-sha256 HAP identity")
    if result.get("taskId") != task_id:
        fail(f"{label} functional result task differs from SmartPerf summary")
    if result.get("sourceIdentity") != source_identity:
        fail(f"{label} functional result source differs from SmartPerf summary")
    if result.get("hapSha256") != match.group(1):
        fail(f"{label} functional result HAP digest differs from source identity")
    if result.get("powerThermalAuthority") != "unavailable_on_emulator":
        fail(f"{label} functional result overclaims power or thermal authority")
    scenario_id = result.get("scenarioId")
    scenario_sha256 = result.get("scenarioSha256")
    if not isinstance(scenario_id, str) or not scenario_id:
        fail(f"{label} functional result requires scenarioId")
    if not isinstance(scenario_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", scenario_sha256):
        fail(f"{label} functional result requires exact scenarioSha256")
    if result.get("profileRunId") != summary.get("runId"):
        fail(f"{label} functional result profile run differs from SmartPerf summary")
    if result.get("environmentIdentity") != summary.get("environmentIdentity"):
        fail(f"{label} functional result environment differs from SmartPerf summary")
    if result.get("profileStatus") != "collected" or result.get("profileSummaryStatus") != "normalized":
        fail(f"{label} functional result does not bind a normalized SmartPerf profile")
    if summary.get("schema") == "agentlab.smartperf_summary.v2":
        if result.get("schema") != "agentlab.harmony_emulator_case_result.v3":
            fail(f"{label} policy-bound summary requires a v3 functional result")
        policy = summary.get("performancePolicy") or {}
        workload = summary.get("profileWorkload") or {}
        if (
            result.get("performancePolicyId") != policy.get("id")
            or result.get("performancePolicySha256") != policy.get("sha256")
        ):
            fail(f"{label} functional result performance policy differs from summary")
        if (
            result.get("profileWorkloadId") != workload.get("id")
            or result.get("profileWorkloadSha256") != workload.get("sha256")
        ):
            fail(f"{label} functional result profile workload differs from summary")
    assessed = (
        result.get("assessmentStatus") == "assessed"
        and result.get("infrastructureAvailable") is True
        and isinstance(result.get("subjectTaskSucceeded"), bool)
    )
    passed = (
        assessed
        and result.get("subjectTaskSucceeded") is True
        and result.get("status") == "passed"
        and result.get("oracleStatus") == "passed"
        and result.get("failureClass") == "none"
    )
    reasons = []
    if not assessed:
        reasons.append(f"{label}-functional-evidence-unassessed")
    elif not passed:
        reasons.append(f"{label}-functional-gate-failed")
    return (
        {
            "resultSha256": canonical_digest(result),
            "sourceIdentity": source_identity,
            "assessmentStatus": result.get("assessmentStatus"),
            "infrastructureAvailable": result.get("infrastructureAvailable"),
            "subjectTaskSucceeded": result.get("subjectTaskSucceeded"),
            "oracleStatus": result.get("oracleStatus"),
            "scenarioId": scenario_id,
            "scenarioSha256": scenario_sha256,
            "profileRunId": result.get("profileRunId"),
            "environmentIdentity": result.get("environmentIdentity"),
            "passed": passed,
        },
        reasons,
    )


def build_comparison(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    min_fps_ratio: float,
    max_cpu_regression: float,
    max_pss_regression: float,
    max_jitter_regression: float,
    baseline_result: dict[str, Any] | None = None,
    candidate_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    for label, value in (("baseline", baseline), ("candidate", candidate)):
        if value.get("schema") not in INPUT_SCHEMAS:
            fail(f"unsupported {label} SmartPerf summary schema")
    if baseline.get("schema") != candidate.get("schema"):
        fail("baseline and candidate SmartPerf summary schemas differ")
    if not 0 < min_fps_ratio <= 1:
        fail("minimum FPS ratio must be in (0, 1]")
    for label, value in (
        ("CPU regression", max_cpu_regression),
        ("PSS regression", max_pss_regression),
        ("jitter regression", max_jitter_regression),
    ):
        if value < 0:
            fail(f"maximum {label} must be non-negative")

    reasons: list[str] = []
    functional = None
    if (baseline_result is None) != (candidate_result is None):
        fail("baseline and candidate functional results must be supplied together")
    if baseline_result is not None and candidate_result is not None:
        baseline_gate, baseline_reasons = functional_gate(
            "baseline", baseline, baseline_result
        )
        candidate_gate, candidate_reasons = functional_gate(
            "candidate", candidate, candidate_result
        )
        reasons.extend(baseline_reasons)
        reasons.extend(candidate_reasons)
        if (
            baseline_gate["scenarioId"] != candidate_gate["scenarioId"]
            or baseline_gate["scenarioSha256"] != candidate_gate["scenarioSha256"]
        ):
            reasons.append("functional-scenario-mismatch")
        functional = {
            "baseline": baseline_gate,
            "candidate": candidate_gate,
            "passed": baseline_gate["passed"] and candidate_gate["passed"],
        }
    if baseline.get("taskId") != candidate.get("taskId"):
        reasons.append("task-mismatch")
    if baseline.get("environmentIdentity") != candidate.get("environmentIdentity"):
        reasons.append("environment-mismatch")
    if baseline.get("profileValid") is not True:
        reasons.append("baseline-profile-invalid")
    if candidate.get("profileValid") is not True:
        reasons.append("candidate-profile-invalid")
    for label, value in (("baseline", baseline), ("candidate", candidate)):
        authority = (value.get("authority") or {}).get("absolutePowerThermal")
        if authority != "unavailable-on-emulator":
            reasons.append(f"{label}-authority-unsupported")

    policy_identity = None
    workload_identity = None
    if baseline.get("schema") == "agentlab.smartperf_summary.v2":
        baseline_policy = baseline.get("performancePolicy") or {}
        candidate_policy = candidate.get("performancePolicy") or {}
        baseline_workload = baseline.get("profileWorkload") or {}
        candidate_workload = candidate.get("profileWorkload") or {}
        if baseline_policy != candidate_policy:
            reasons.append("performance-policy-mismatch")
        if baseline_workload != candidate_workload:
            reasons.append("profile-workload-mismatch")
        required = candidate_policy.get("requiredMetrics")
        if not isinstance(required, list) or not required:
            fail("policy-bound summary requires requiredMetrics")
        specifications = []
        for row in required:
            if not isinstance(row, dict):
                fail("invalid required performance metric")
            direction = row.get("direction")
            threshold = (
                row.get("minimumCandidateToBaselineRatio")
                if direction == "higher"
                else row.get("maximumRelativeIncrease")
            )
            if (
                not isinstance(row.get("metric"), str)
                or row.get("statistic") not in {"mean", "p50", "p95"}
                or direction not in {"higher", "lower"}
                or not isinstance(threshold, (int, float))
            ):
                fail("invalid required performance metric specification")
            specifications.append((row["metric"], row["statistic"], direction, float(threshold)))
        policy_identity = {
            "id": candidate_policy.get("id"),
            "sha256": candidate_policy.get("sha256"),
        }
        workload_identity = {
            "id": candidate_workload.get("id"),
            "sha256": candidate_workload.get("sha256"),
        }
    else:
        specifications = [
            ("fps", "p50", "higher", min_fps_ratio),
            ("appCpuUsagePercent", "mean", "lower", max_cpu_regression),
            ("appPssKiB", "mean", "lower", max_pss_regression),
            ("frameIntervalMs", "p95", "lower", max_jitter_regression),
        ]
    rows: list[dict[str, Any]] = []
    for name, statistic, direction, threshold in specifications:
        before = metric(baseline, name, statistic)
        after = metric(candidate, name, statistic)
        if before is None or after is None:
            rows.append(
                {
                    "metric": name,
                    "statistic": statistic,
                    "status": "missing",
                    "baseline": before,
                    "candidate": after,
                }
            )
            continue
        if before <= 0:
            rows.append(
                {
                    "metric": name,
                    "statistic": statistic,
                    "status": "unusable-baseline",
                    "baseline": before,
                    "candidate": after,
                    "candidateToBaselineRatio": None,
                }
            )
            continue
        if direction == "higher":
            ratio = after / before
            passed = ratio >= threshold
            limit = {"minimumCandidateToBaselineRatio": threshold}
        else:
            ratio = after / before
            passed = ratio <= 1.0 + threshold
            limit = {"maximumRelativeIncrease": threshold}
        rows.append(
            {
                "metric": name,
                "statistic": statistic,
                "status": "passed" if passed else "regressed",
                "baseline": before,
                "candidate": after,
                "candidateToBaselineRatio": ratio,
                "guardrail": limit,
            }
        )

    missing = any(row["status"] == "missing" for row in rows)
    if missing:
        reasons.append("required-metric-missing")
    unusable = any(row["status"] == "unusable-baseline" for row in rows)
    if unusable:
        reasons.append("required-metric-unusable-baseline")
    regressed = any(row["status"] == "regressed" for row in rows)
    comparable = not reasons
    if not comparable:
        decision = "insufficient-comparable-evidence"
    elif regressed:
        decision = "performance-regression-candidate"
    else:
        decision = "within-relative-guardrails"
    report = {
        "schema": (
            OUTPUT_SCHEMA_V3
            if functional is not None and policy_identity is not None
            else OUTPUT_SCHEMA_V2
            if functional is not None
            else OUTPUT_SCHEMA_V1
        ),
        "taskId": candidate.get("taskId"),
        "baselineRunId": baseline.get("runId"),
        "baselineSourceIdentity": baseline.get("sourceIdentity"),
        "baselineSummarySha256": canonical_digest(baseline),
        "candidateRunId": candidate.get("runId"),
        "candidateSourceIdentity": candidate.get("sourceIdentity"),
        "candidateSummarySha256": canonical_digest(candidate),
        "environmentIdentity": candidate.get("environmentIdentity"),
        "baselineSampleCount": baseline.get("sampleCount"),
        "candidateSampleCount": candidate.get("sampleCount"),
        "comparable": comparable,
        "incomparabilityReasons": reasons,
        "metrics": rows,
        "decision": decision,
        "policy": {
            "automaticPromotion": False,
            "absolutePowerThermalUsed": False,
            "interpretation": "relative emulator regression signal only",
        },
    }
    if functional is not None:
        report["functionalGate"] = functional
    if policy_identity is not None:
        report["performancePolicy"] = policy_identity
        report["profileWorkload"] = workload_identity
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=pathlib.Path, required=True)
    parser.add_argument("--candidate", type=pathlib.Path, required=True)
    parser.add_argument("--baseline-result", type=pathlib.Path)
    parser.add_argument("--candidate-result", type=pathlib.Path)
    parser.add_argument("--min-fps-ratio", type=float, default=0.90)
    parser.add_argument("--max-cpu-regression", type=float, default=0.20)
    parser.add_argument("--max-pss-regression", type=float, default=0.15)
    parser.add_argument("--max-jitter-regression", type=float, default=0.20)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    report = build_comparison(
        load(args.baseline),
        load(args.candidate),
        args.min_fps_ratio,
        args.max_cpu_regression,
        args.max_pss_regression,
        args.max_jitter_regression,
        load_result(args.baseline_result) if args.baseline_result else None,
        load_result(args.candidate_result) if args.candidate_result else None,
    )
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
