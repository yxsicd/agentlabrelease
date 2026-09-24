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


SCHEMA = "agentlab.smartperf_summary.v1"
ENTRY = re.compile(
    r"order:\d+\s+([A-Za-z][A-Za-z0-9_]*)=(.*?)(?=\s+order:\d+\s+|$)"
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
    for line in text.splitlines():
        if "Print START" in line:
            if current is not None:
                fail("nested SmartPerf sample start")
            current = {}
            continue
        if "Print END" in line:
            if current is None:
                fail("SmartPerf sample end without start")
            if not current:
                fail("empty SmartPerf sample")
            samples.append(current)
            current = None
            continue
        if current is None:
            continue
        for match in ENTRY.finditer(line.strip()):
            name, value = match.groups()
            if name in current:
                fail(f"duplicate SmartPerf field in one sample: {name}")
            current[name] = value.strip()
    if current is not None:
        fail("unterminated SmartPerf sample")
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
                for item in value.split(";;"):
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
    return {
        "schema": SCHEMA,
        "taskId": task_id,
        "sourceIdentity": source_identity,
        "runId": run_id,
        "environmentIdentity": environment_identity,
        "input": {"sha256": hashlib.sha256(raw).hexdigest(), "byteLength": len(raw)},
        "sampleCount": len(samples),
        "minimumSampleCount": minimum_samples,
        "profileValid": len(samples) >= minimum_samples and bool(canonical),
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=pathlib.Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--source-identity", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--environment-identity", required=True)
    parser.add_argument("--minimum-samples", type=int, default=3)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    summary = build_summary(
        args.input.read_bytes(),
        args.task_id,
        args.source_identity,
        args.run_id,
        args.environment_identity,
        args.minimum_samples,
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
