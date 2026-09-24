#!/usr/bin/env python3
"""Normalize SmartPerf SP_daemon text into bounded relative-performance evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import re
import statistics
from typing import Any


SCHEMA_V1 = "agentlab.smartperf_summary.v1"
SCHEMA_V2 = "agentlab.smartperf_summary.v2"
POLICY_SCHEMA = "agentlab.harmony_performance_policy.v1"
WORKLOAD_SCHEMA = "agentlab.harmony_profile_workload.v1"
ENTRY = re.compile(
    r"order:(\d+)\s+([A-Za-z][A-Za-z0-9_]*)=(.*?)(?=\s+order:\d+\s+|$)"
)
CANONICAL = {
    "fps": ("fps", "frames-per-second"),
    "ProcCpuUsage": ("appCpuUsagePercent", "reported-percent"),
    "pss": ("appPssKiB", "reported-kibibytes"),
    "gpuload": ("gpuLoadPercent", "reported-percent"),
    "gpuLoad": ("gpuLoadPercent", "reported-percent"),
}
NON_GATING_NAMES = {"shell_back", "shell_frame", "shell_front", "soc_thermal", "system_h"}


def fail(message: str) -> None:
    raise ValueError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_policy(path: pathlib.Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or value.get("schema") != POLICY_SCHEMA:
        fail("unsupported Harmony performance policy")
    policy_id = value.get("id")
    required = value.get("requiredMetrics")
    observed = value.get("observedOnlyMetrics")
    if not isinstance(policy_id, str) or not policy_id:
        fail("performance policy id required")
    if value.get("requiresWorkload") is not True:
        fail("performance policy must require an exact workload")
    if not isinstance(required, list) or not required:
        fail("performance policy requires at least one required metric")
    names: set[str] = set()
    for row in required:
        if not isinstance(row, dict):
            fail("invalid performance policy metric")
        name = row.get("metric")
        statistic = row.get("statistic")
        direction = row.get("direction")
        relative = row.get("maximumRelativeIncrease")
        ratio = row.get("minimumCandidateToBaselineRatio")
        if name not in {"fps", "appCpuUsagePercent", "appPssKiB", "gpuLoadPercent", "frameIntervalMs"}:
            fail(f"unsupported required performance metric: {name}")
        if not isinstance(statistic, str) or statistic not in {"mean", "p50", "p95"}:
            fail("unsupported performance policy statistic")
        if direction == "lower" and (not isinstance(relative, (int, float)) or relative < 0 or ratio is not None):
            fail("lower-is-better metric requires non-negative maximumRelativeIncrease")
        if direction == "higher" and (not isinstance(ratio, (int, float)) or not 0 < ratio <= 1 or relative is not None):
            fail("higher-is-better metric requires minimumCandidateToBaselineRatio in (0, 1]")
        if direction not in {"lower", "higher"}:
            fail("unsupported performance metric direction")
        if name in names:
            fail(f"duplicate required performance metric: {name}")
        names.add(name)
    if not isinstance(observed, list) or not all(isinstance(item, str) for item in observed):
        fail("observedOnlyMetrics must be a string list")
    if names.intersection(observed):
        fail("required and observed-only metrics must be disjoint")
    authority = value.get("authority") or {}
    if authority.get("absolutePowerThermal") != "unavailable-on-emulator":
        fail("performance policy overclaims absolute power or thermal authority")
    return value, sha256(raw)


def load_workload(path: pathlib.Path) -> tuple[str, str]:
    raw = path.read_bytes()
    schema = None
    workload_id = None
    actions = 0
    for line in raw.decode("utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if fields[0] == "schema" and len(fields) == 2:
            schema = fields[1]
        elif fields[0] == "workload" and len(fields) == 2:
            workload_id = fields[1]
        else:
            actions += 1
    if schema != WORKLOAD_SCHEMA:
        fail("unsupported Harmony profile workload")
    if not isinstance(workload_id, str) or not workload_id:
        fail("profile workload id required")
    if actions < 1:
        fail("profile workload requires at least one action")
    return workload_id, sha256(raw)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def aggregate(values: list[float], unit: str) -> dict[str, Any]:
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "unit": unit,
    }


def numeric(value: str) -> float | None:
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def is_non_gating_power_thermal(name: str) -> bool:
    lower = name.lower()
    return name in NON_GATING_NAMES or any(
        token in lower for token in ("battery", "current", "voltage", "temp", "thermal")
    )


def parse_samples(text: str) -> list[dict[str, str]]:
    samples: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    mode: str | None = None
    last_order = -1
    for line in text.splitlines():
        if "Print START" in line:
            if current is not None:
                fail("nested SmartPerf sample start")
            if mode == "bare":
                fail("mixed marked and bare SmartPerf samples")
            mode = "marked"
            current = {}
            last_order = -1
            continue
        if "Print END" in line:
            if mode != "marked" or current is None:
                fail("SmartPerf sample end without start")
            if not current:
                fail("empty SmartPerf sample")
            samples.append(current)
            current = None
            last_order = -1
            continue
        matches = list(ENTRY.finditer(line.strip()))
        if not matches:
            continue
        if mode == "marked" and current is None:
            continue
        if mode is None:
            mode = "bare"
        for match in matches:
            order_text, name, value = match.groups()
            order = int(order_text)
            if mode == "bare" and current is None:
                if order != 0:
                    fail("bare SmartPerf sample must start at order:0")
                current = {}
                last_order = -1
            elif mode == "bare" and order <= last_order:
                if order != 0:
                    fail("bare SmartPerf sample order must reset at order:0")
                if not current:
                    fail("empty SmartPerf sample")
                samples.append(current)
                current = {}
                last_order = -1
            if order <= last_order:
                fail("SmartPerf sample order is not strictly increasing")
            assert current is not None
            if name in current:
                fail(f"duplicate SmartPerf field in one sample: {name}")
            current[name] = value.strip()
            last_order = order
    if mode == "marked" and current is not None:
        fail("unterminated SmartPerf sample")
    if mode == "bare" and current:
        samples.append(current)
    if not samples:
        fail("no SmartPerf samples found")
    return samples


def build_summary(
    raw: bytes,
    task_id: str,
    source_identity: str,
    run_id: str,
    environment_identity: str,
    minimum_samples: int,
    performance_policy: dict[str, Any] | None = None,
    performance_policy_sha256: str | None = None,
    workload_id: str | None = None,
    workload_sha256: str | None = None,
) -> dict[str, Any]:
    if minimum_samples < 1:
        fail("minimum samples must be positive")
    for label, value in (
        ("task id", task_id),
        ("source identity", source_identity),
        ("run id", run_id),
        ("environment identity", environment_identity),
    ):
        if not value:
            fail(f"{label} required")
    text = raw.decode("utf-8")
    samples = parse_samples(text)
    raw_numeric: dict[str, list[float]] = {}
    jitters_ms: list[float] = []
    for sample in samples:
        for name, value in sample.items():
            if name == "fpsJitters":
                for item in (item for item in value.split(";;") if item):
                    parsed = numeric(item)
                    if parsed is None or parsed < 0:
                        fail("fpsJitters must contain non-negative nanoseconds")
                    jitters_ms.append(parsed / 1_000_000.0)
                continue
            parsed = numeric(value)
            if parsed is not None:
                raw_numeric.setdefault(name, []).append(parsed)

    canonical: dict[str, dict[str, Any]] = {}
    for raw_name, (name, unit) in CANONICAL.items():
        values = raw_numeric.get(raw_name)
        if values:
            if name in canonical:
                fail(f"multiple SmartPerf fields map to canonical metric: {name}")
            canonical[name] = aggregate(values, unit)
    if jitters_ms:
        canonical["frameIntervalMs"] = aggregate(jitters_ms, "milliseconds")

    non_gating = sorted(
        name for name in raw_numeric if is_non_gating_power_thermal(name)
    )
    unknown = sorted(
        name
        for name in raw_numeric
        if name not in CANONICAL
        and name not in non_gating
        and name not in {"timestamp", "ProcId"}
        and not re.fullmatch(r"cpu\d+.*", name)
    )
    if any(value is not None for value in (performance_policy, performance_policy_sha256, workload_id, workload_sha256)):
        if not all(value is not None for value in (performance_policy, performance_policy_sha256, workload_id, workload_sha256)):
            fail("performance policy and workload identities must be supplied together")
        assert performance_policy is not None
        required_names = [row["metric"] for row in performance_policy["requiredMetrics"]]
        required_available = all(name in canonical for name in required_names)
        schema = SCHEMA_V2
    else:
        required_available = bool(canonical)
        schema = SCHEMA_V1
    result = {
        "schema": schema,
        "taskId": task_id,
        "sourceIdentity": source_identity,
        "runId": run_id,
        "environmentIdentity": environment_identity,
        "input": {"sha256": sha256(raw), "byteLength": len(raw)},
        "sampleCount": len(samples),
        "minimumSampleCount": minimum_samples,
        "profileValid": len(samples) >= minimum_samples and required_available,
        "canonicalMetrics": canonical,
        "rawNumericMetrics": {
            name: aggregate(values, "smartperf-reported")
            for name, values in sorted(raw_numeric.items())
        },
        "unknownNumericMetricNames": unknown,
        "authority": {
            "functional": "none",
            "relativePerformance": "smartperf-emulator-proxy",
            "absolutePowerThermal": "unavailable-on-emulator",
            "nonGatingPowerThermalMetrics": non_gating,
        },
    }
    if schema == SCHEMA_V2:
        assert performance_policy is not None
        result["performancePolicy"] = {
            "id": performance_policy["id"],
            "sha256": performance_policy_sha256,
            "requiredMetrics": performance_policy["requiredMetrics"],
            "observedOnlyMetrics": performance_policy["observedOnlyMetrics"],
        }
        result["profileWorkload"] = {"id": workload_id, "sha256": workload_sha256}
        result["metricAvailability"] = {
            name: name in canonical
            for name in sorted(
                set(required_names).union(performance_policy["observedOnlyMetrics"])
            )
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=pathlib.Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--source-identity", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--environment-identity", required=True)
    parser.add_argument("--minimum-samples", type=int, default=3)
    parser.add_argument("--performance-policy", type=pathlib.Path)
    parser.add_argument("--profile-workload", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    if (args.performance_policy is None) != (args.profile_workload is None):
        fail("--performance-policy and --profile-workload must be supplied together")
    policy = policy_sha = workload_id = workload_sha = None
    if args.performance_policy is not None and args.profile_workload is not None:
        policy, policy_sha = load_policy(args.performance_policy)
        workload_id, workload_sha = load_workload(args.profile_workload)
    summary = build_summary(
        args.input.read_bytes(),
        args.task_id,
        args.source_identity,
        args.run_id,
        args.environment_identity,
        args.minimum_samples,
        policy,
        policy_sha,
        workload_id,
        workload_sha,
    )
    body = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            fail(f"refusing to overwrite existing output: {args.output}")
        args.output.write_text(body, encoding="utf-8")
    else:
        print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
