#!/usr/bin/env python3
"""Compare two normalized SmartPerf profiles under explicit relative guardrails."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any


INPUT_SCHEMA = "agentlab.smartperf_summary.v1"
OUTPUT_SCHEMA = "agentlab.smartperf_comparison.v1"


def fail(message: str) -> None:
    raise ValueError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != INPUT_SCHEMA:
        fail(f"unsupported SmartPerf summary: {path}")
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


def build_comparison(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    min_fps_ratio: float,
    max_cpu_regression: float,
    max_pss_regression: float,
    max_jitter_regression: float,
) -> dict[str, Any]:
    for label, value in (("baseline", baseline), ("candidate", candidate)):
        if value.get("schema") != INPUT_SCHEMA:
            fail(f"unsupported {label} SmartPerf summary schema")
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
        if direction == "higher":
            ratio = after / before if before > 0 else None
            passed = ratio is not None and ratio >= threshold
            limit = {"minimumCandidateToBaselineRatio": threshold}
        else:
            ratio = after / before if before > 0 else None
            passed = ratio is not None and ratio <= 1.0 + threshold
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
    regressed = any(row["status"] == "regressed" for row in rows)
    comparable = not reasons and not missing
    if not comparable:
        decision = "insufficient-comparable-evidence"
    elif regressed:
        decision = "performance-regression-candidate"
    else:
        decision = "within-relative-guardrails"
    return {
        "schema": OUTPUT_SCHEMA,
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=pathlib.Path, required=True)
    parser.add_argument("--candidate", type=pathlib.Path, required=True)
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
