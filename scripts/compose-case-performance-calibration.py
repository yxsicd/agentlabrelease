#!/usr/bin/env python3
"""Compose repeatable case-variant SmartPerf evidence into a frozen calibration."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import pathlib
import re
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
SHA256 = re.compile(r"[0-9a-f]{64}")
MANIFEST_SCHEMA = "agentlab.case_performance_calibration_manifest.v1"
OUTPUT_SCHEMA = "agentlab.case_performance_calibration.v1"
ROLE_DECISIONS = {
    "baseline": "performance-regression-candidate",
    "reference": "within-relative-guardrails",
    "wrong": "performance-regression-candidate",
}


class CalibrationError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise CalibrationError(message)


def load(path: pathlib.Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable_path(root: pathlib.Path, value: Any, label: str) -> pathlib.Path:
    require(isinstance(value, str) and bool(value), f"{label} path is required")
    relative = pathlib.Path(value)
    require(not relative.is_absolute(), f"{label} path must be relative")
    candidate = root / relative
    require(
        candidate.is_file() and not candidate.is_symlink(),
        f"{label} must be a regular file",
    )
    path = candidate.resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise CalibrationError(f"{label} path escapes the manifest directory") from error
    return path


def evidence_ref(path: pathlib.Path, root: pathlib.Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": digest(path),
        "byteLength": path.stat().st_size,
    }


def comparator_module():
    path = ROOT / "scripts/compare-smartperf.py"
    spec = importlib.util.spec_from_file_location("agentlab_case_performance_compare", path)
    require(spec is not None and spec.loader is not None, "SmartPerf comparator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_feedback(value: Any) -> dict[str, Any]:
    require(isinstance(value, dict), "feedbackPerformanceEvidence must be an object")
    authority = value.get("authority")
    require(
        isinstance(value.get("environmentIdentity"), str)
        and bool(value["environmentIdentity"])
        and all(
            isinstance(value.get(field), str) and SHA256.fullmatch(value[field])
            for field in ("performancePolicySha256", "profileWorkloadSha256")
        )
        and isinstance(value.get("metric"), str)
        and bool(value["metric"])
        and value.get("statistic") in {"mean", "p50", "p95"}
        and isinstance(value.get("unit"), str)
        and bool(value["unit"])
        and value.get("direction") in {"lower", "higher"}
        and isinstance(value.get("bestParticipantId"), str)
        and bool(value["bestParticipantId"])
        and isinstance(value.get("worstParticipantId"), str)
        and bool(value["worstParticipantId"])
        and value["bestParticipantId"] != value["worstParticipantId"]
        and isinstance(value.get("meanDifference"), (int, float))
        and not isinstance(value["meanDifference"], bool)
        and math.isfinite(value["meanDifference"])
        and value["meanDifference"] > 0
        and value.get("rangesSeparated") is True
        and authority
        == {
            "functional": "none",
            "relativePerformance": "smartperf-emulator-proxy",
            "absolutePowerThermal": "unavailable-on-emulator",
        },
        "feedback performance evidence is invalid",
    )
    return value


def validate_observation(
    *,
    comparator: Any,
    manifest_root: pathlib.Path,
    row: Any,
    role: str,
    ordinal: int,
    case_id: str,
    feedback: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    label = f"{role} observation {ordinal}"
    require(
        isinstance(row, dict)
        and set(row)
        == {
            "baselineSummary",
            "candidateSummary",
            "baselineResult",
            "candidateResult",
            "comparison",
        },
        f"{label} fields differ",
    )
    paths = {
        name: portable_path(manifest_root, row[name], f"{label} {name}")
        for name in row
    }
    baseline = comparator.load(paths["baselineSummary"])
    candidate = comparator.load(paths["candidateSummary"])
    baseline_result = comparator.load_result(paths["baselineResult"])
    candidate_result = comparator.load_result(paths["candidateResult"])
    retained = load(paths["comparison"], f"{label} comparison")
    require(
        baseline.get("schema") == candidate.get("schema") == "agentlab.smartperf_summary.v2"
        and baseline_result.get("schema")
        == candidate_result.get("schema")
        == "agentlab.harmony_emulator_case_result.v3",
        f"{label} requires policy-bound v3 evidence",
    )
    rebuilt = comparator.build_comparison(
        baseline,
        candidate,
        0.90,
        0.20,
        0.15,
        0.20,
        baseline_result,
        candidate_result,
    )
    require(rebuilt == retained, f"{label} comparison differs from raw evidence")
    expected = ROLE_DECISIONS[role]
    require(retained.get("schema") == "agentlab.smartperf_comparison.v3", f"{label} schema differs")
    require(retained.get("taskId") == case_id, f"{label} task differs")
    require(retained.get("decision") == expected, f"{label} decision differs from role")
    require(retained.get("comparable") is True, f"{label} is not comparable")
    require((retained.get("functionalGate") or {}).get("passed") is True, f"{label} functional gate failed")
    require(retained.get("environmentIdentity") == feedback["environmentIdentity"], f"{label} environment differs")
    require(
        (retained.get("performancePolicy") or {}).get("sha256")
        == feedback["performancePolicySha256"],
        f"{label} performance policy differs",
    )
    require(
        (retained.get("profileWorkload") or {}).get("sha256")
        == feedback["profileWorkloadSha256"],
        f"{label} profile workload differs",
    )
    matching = [
        metric
        for metric in retained.get("metrics", [])
        if isinstance(metric, dict)
        and metric.get("metric") == feedback["metric"]
        and metric.get("statistic") == feedback["statistic"]
    ]
    require(len(matching) == 1, f"{label} selected metric is absent")
    expected_status = "passed" if role == "reference" else "regressed"
    require(matching[0].get("status") == expected_status, f"{label} selected metric status differs")
    baseline_identity = retained.get("baselineSourceIdentity")
    candidate_identity = retained.get("candidateSourceIdentity")
    require(
        isinstance(baseline_identity, str)
        and baseline_identity.startswith("artifact-sha256:")
        and isinstance(candidate_identity, str)
        and candidate_identity.startswith("artifact-sha256:"),
        f"{label} source identities are invalid",
    )
    return (
        {name: evidence_ref(path, manifest_root) for name, path in sorted(paths.items())},
        baseline_identity,
        candidate_identity,
    )


def compose(manifest: dict[str, Any], root: pathlib.Path) -> dict[str, Any]:
    require(manifest.get("schema") == MANIFEST_SCHEMA, "unsupported case performance calibration manifest")
    require(manifest.get("automaticPromotion") is False, "calibration manifest must not auto-promote")
    case_id = manifest.get("caseId")
    source_set = manifest.get("sourceSetSha256")
    functional_sha = manifest.get("functionalCalibrationSha256")
    require(isinstance(case_id, str) and bool(case_id), "caseId is required")
    require(isinstance(source_set, str) and SHA256.fullmatch(source_set), "sourceSetSha256 is invalid")
    require(isinstance(functional_sha, str) and SHA256.fullmatch(functional_sha), "functional calibration digest is invalid")
    feedback = validate_feedback(manifest.get("feedbackPerformanceEvidence"))
    variants = manifest.get("variants")
    require(isinstance(variants, dict) and set(variants) == set(ROLE_DECISIONS), "baseline, reference and wrong performance variants are required")
    comparator = comparator_module()
    baseline_identity = None
    candidate_identities: set[str] = set()
    role_rows = []
    for role in ("baseline", "reference", "wrong"):
        observations = variants[role]
        require(isinstance(observations, list) and len(observations) >= 2, f"{role} requires at least two observations")
        retained = []
        role_candidates: set[str] = set()
        for ordinal, observation in enumerate(observations, 1):
            evidence, observed_baseline, observed_candidate = validate_observation(
                comparator=comparator,
                manifest_root=root,
                row=observation,
                role=role,
                ordinal=ordinal,
                case_id=case_id,
                feedback=feedback,
            )
            if baseline_identity is None:
                baseline_identity = observed_baseline
            require(observed_baseline == baseline_identity, "performance observations use different baseline artifacts")
            role_candidates.add(observed_candidate)
            retained.append(evidence)
        require(len(role_candidates) == 1, f"{role} repeat observations use different candidate artifacts")
        role_candidate = next(iter(role_candidates))
        require(
            role_candidate != baseline_identity,
            f"{role} candidate artifact equals the performance baseline",
        )
        require(role_candidate not in candidate_identities, "performance variant artifacts are not distinct")
        candidate_identities.add(role_candidate)
        role_rows.append(
            {
                "role": role,
                "expectedDecision": ROLE_DECISIONS[role],
                "candidateSourceIdentity": role_candidate,
                "observationCount": len(retained),
                "observations": retained,
            }
        )
    return {
        "schema": OUTPUT_SCHEMA,
        "status": "qualified-review-required",
        "caseId": case_id,
        "sourceSetSha256": source_set,
        "functionalCalibrationSha256": functional_sha,
        "feedbackPerformanceEvidence": feedback,
        "baselineSourceIdentity": baseline_identity,
        "variants": role_rows,
        "functionalOracleQualified": True,
        "repeatabilityQualified": True,
        "authority": {
            "functional": "independent-harmony-ui-oracle",
            "relativePerformance": "smartperf-emulator-proxy",
            "absolutePowerThermal": "unavailable-on-emulator",
        },
        "automaticPromotion": False,
        "nextGate": "maintainer-review-and-case-freeze",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
    manifest_path = args.manifest.resolve(strict=True)
    require(
        args.output.resolve().parent == manifest_path.parent,
        "calibration output must share the manifest directory",
    )
    value = compose(load(manifest_path, "calibration manifest"), manifest_path.parent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "caseId": value["caseId"], "status": value["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
