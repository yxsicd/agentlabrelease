#!/usr/bin/env python3
"""Run one exact baseline and two candidate Harmony emulator calibrations."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any


PLAN_SCHEMA = "agentlab.harmony_performance_calibration_plan.v1"
CALIBRATION_SCHEMA = "agentlab.performance_calibration.v1"
RECEIPT_SCHEMA = "agentlab.harmony_performance_calibration_run.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[A-Za-z0-9_.:-]+")


class CalibrationError(RuntimeError):
    pass


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_object(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CalibrationError(f"cannot load JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise CalibrationError(f"expected JSON object: {path}")
    return value


def require_path(value: Any, label: str, *, executable: bool = False) -> pathlib.Path:
    if not isinstance(value, str) or not value:
        raise CalibrationError(f"{label} path is required")
    path = pathlib.Path(value).resolve()
    if not path.is_file():
        raise CalibrationError(f"{label} file not found: {path}")
    if executable and not os.access(path, os.X_OK):
        raise CalibrationError(f"{label} is not executable: {path}")
    return path


def require_directory(value: Any, label: str) -> pathlib.Path:
    if not isinstance(value, str) or not value:
        raise CalibrationError(f"{label} path is required")
    path = pathlib.Path(value).resolve()
    if not path.is_dir():
        raise CalibrationError(f"{label} directory not found: {path}")
    return path


def require_token(value: Any, label: str) -> str:
    if not isinstance(value, str) or TOKEN.fullmatch(value) is None:
        raise CalibrationError(f"{label} must be a non-empty safe token")
    return value


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_phase(
    command: list[str], phase: str, stage: pathlib.Path, phases: list[dict[str, Any]]
) -> None:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    stdout_path = stage / f"phase-{phase}.stdout.log"
    stderr_path = stage / f"phase-{phase}.stderr.log"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    phases.append(
        {
            "phase": phase,
            "exitCode": completed.returncode,
            "stdoutSha256": sha256(stdout_path),
            "stderrSha256": sha256(stderr_path),
        }
    )
    if completed.returncode != 0:
        raise CalibrationError(f"phase failed: {phase} (exit {completed.returncode})")


def wait_for_port_release(
    port: int,
    timeout_seconds: int,
    phase: str,
    phases: list[dict[str, Any]],
) -> None:
    started = time.monotonic()
    attempts = 0
    while True:
        attempts += 1
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.25)
            released = probe.connect_ex(("127.0.0.1", port)) != 0
        elapsed = time.monotonic() - started
        if released:
            phases.append(
                {
                    "phase": phase,
                    "exitCode": 0,
                    "attempts": attempts,
                    "elapsedSeconds": round(elapsed, 3),
                }
            )
            return
        if elapsed >= timeout_seconds:
            phases.append(
                {
                    "phase": phase,
                    "exitCode": 1,
                    "attempts": attempts,
                    "elapsedSeconds": round(elapsed, 3),
                }
            )
            raise CalibrationError(
                f"emulator HDC port {port} did not release within {timeout_seconds} seconds"
            )
        time.sleep(1)


def validate_run_output(
    output: pathlib.Path,
    label: str,
    validated: dict[str, Any],
    source_identity: str,
    run_id: str,
) -> None:
    summary = load_object(output / "smartperf-summary.json")
    result = load_object(output / "result.json")
    if summary.get("schema") != "agentlab.smartperf_summary.v2":
        raise CalibrationError(f"{label} requires a policy-bound SmartPerf v2 summary")
    if result.get("schema") != "agentlab.harmony_emulator_case_result.v3":
        raise CalibrationError(f"{label} requires a policy-bound Harmony v3 result")
    exact = {
        "taskId": validated["taskId"],
        "sourceIdentity": source_identity,
        "environmentIdentity": validated["runtime"]["environmentIdentity"],
    }
    for field, expected in exact.items():
        if summary.get(field) != expected or result.get(field) != expected:
            raise CalibrationError(f"{label} {field} differs from the calibration plan")
    if summary.get("runId") != run_id or result.get("profileRunId") != run_id:
        raise CalibrationError(f"{label} run identity differs from the calibration plan")
    if (
        result.get("scenarioId") != validated["scenarioId"]
        or result.get("scenarioSha256") != validated["scenarioSha256"]
    ):
        raise CalibrationError(f"{label} functional Oracle differs from the calibration plan")
    expected_hap = source_identity.removeprefix("artifact-sha256:")
    if result.get("hapSha256") != expected_hap:
        raise CalibrationError(f"{label} HAP digest differs from the calibration plan")
    policy = summary.get("performancePolicy") or {}
    workload = summary.get("profileWorkload") or {}
    if (
        policy.get("id") != validated["policyId"]
        or policy.get("sha256") != validated["policySha256"]
        or result.get("performancePolicyId") != validated["policyId"]
        or result.get("performancePolicySha256") != validated["policySha256"]
    ):
        raise CalibrationError(f"{label} performance policy differs from the calibration plan")
    if (
        workload.get("id") != validated["workloadId"]
        or workload.get("sha256") != validated["workloadSha256"]
        or result.get("profileWorkloadId") != validated["workloadId"]
        or result.get("profileWorkloadSha256") != validated["workloadSha256"]
    ):
        raise CalibrationError(f"{label} profile workload differs from the calibration plan")


def runner_command(
    runner: pathlib.Path,
    runtime: dict[str, Any],
    hap: pathlib.Path,
    source_identity: str,
    output: pathlib.Path,
    scenario: pathlib.Path,
    policy: pathlib.Path,
    workload: pathlib.Path,
    task_id: str,
    profile_run_id: str,
) -> list[str]:
    return [
        str(runner),
        "run-case",
        "--tools-root",
        str(runtime["toolsRoot"]),
        "--image-root",
        str(runtime["imageRoot"]),
        "--instance-path",
        str(runtime["instancePath"]),
        "--instance",
        runtime["instance"],
        "--hdc-port",
        str(runtime["hdcPort"]),
        "--hap",
        str(hap),
        "--bundle",
        runtime["bundle"],
        "--ability",
        runtime["ability"],
        "--output",
        str(output),
        "--ui-scenario",
        str(scenario),
        "--task-id",
        task_id,
        "--source-id",
        source_identity,
        "--profile-run-id",
        profile_run_id,
        "--environment-id",
        runtime["environmentIdentity"],
        "--performance-policy",
        str(policy),
        "--profile-workload",
        str(workload),
        "--boot-mode",
        runtime["bootMode"],
        "--profile-samples",
        str(runtime["profileSamples"]),
        "--reset-app-data",
    ]


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("schema") != PLAN_SCHEMA:
        raise CalibrationError("unsupported calibration plan schema")
    if plan.get("automaticPromotion") is not False:
        raise CalibrationError("calibration plan must set automaticPromotion=false")
    if plan.get("expectedDecision") != "performance-regression-candidate":
        raise CalibrationError("controlled calibration must expect a regression candidate")
    if plan.get("candidateRuns") != 2:
        raise CalibrationError("controlled calibration currently requires exactly two candidate runs")
    harness_revision = plan.get("harnessRevision")
    if not isinstance(harness_revision, str) or REVISION.fullmatch(harness_revision) is None:
        raise CalibrationError("calibration plan requires exact harnessRevision")
    task_id = require_token(plan.get("taskId"), "taskId")
    calibration_id = require_token(plan.get("id"), "calibration id")

    application_source = plan.get("applicationSource") or {}
    if not isinstance(application_source.get("repository"), str) or not application_source["repository"]:
        raise CalibrationError("applicationSource.repository is required")
    if not isinstance(application_source.get("revision"), str) or REVISION.fullmatch(application_source["revision"]) is None:
        raise CalibrationError("applicationSource.revision must be exact")
    if not isinstance(application_source.get("path"), str) or not application_source["path"]:
        raise CalibrationError("applicationSource.path is required")

    baseline = plan.get("baseline") or {}
    candidate = plan.get("candidate") or {}
    baseline_hap = require_path(baseline.get("hap"), "baseline HAP")
    candidate_hap = require_path(candidate.get("hap"), "candidate HAP")
    baseline_identity = f"artifact-sha256:{sha256(baseline_hap)}"
    candidate_identity = f"artifact-sha256:{sha256(candidate_hap)}"
    if baseline.get("sourceIdentity") not in (None, baseline_identity):
        raise CalibrationError("baseline sourceIdentity differs from exact HAP")
    if candidate.get("sourceIdentity") not in (None, candidate_identity):
        raise CalibrationError("candidate sourceIdentity differs from exact HAP")
    if candidate_identity == baseline_identity:
        raise CalibrationError("controlled candidate HAP must differ from baseline")
    mutation = candidate.get("controlledMutation") or {}
    if mutation.get("kind") not in {"retained-memory", "bounded-cpu", "combined-cpu-memory"}:
        raise CalibrationError("unsupported controlled mutation kind")
    if not isinstance(mutation.get("bytes"), int) or mutation["bytes"] <= 0:
        raise CalibrationError("controlled mutation requires positive bytes")
    for field in ("id", "sourcePath"):
        if not isinstance(mutation.get(field), str) or not mutation[field]:
            raise CalibrationError(f"controlled mutation requires {field}")
    for field in ("baseSourceFileSha256", "candidateSourceFileSha256"):
        if not isinstance(mutation.get(field), str) or SHA256.fullmatch(mutation[field]) is None:
            raise CalibrationError(f"controlled mutation requires exact {field}")
    if mutation["baseSourceFileSha256"] == mutation["candidateSourceFileSha256"]:
        raise CalibrationError("controlled mutation source hashes must differ")

    oracle = plan.get("functionalOracle") or {}
    scenario = require_path(oracle.get("path"), "functional Oracle scenario")
    scenario_id = require_token(oracle.get("scenarioId"), "functional Oracle scenarioId")
    scenario_sha = sha256(scenario)
    if oracle.get("scenarioSha256") not in (None, scenario_sha):
        raise CalibrationError("functional Oracle scenarioSha256 differs from file")

    runtime = plan.get("runtime") or {}
    runner = require_path(runtime.get("runner"), "runner", executable=True)
    comparator = require_path(runtime.get("comparator"), "comparator")
    runtime = {
        **runtime,
        "toolsRoot": require_directory(runtime.get("toolsRoot"), "toolsRoot"),
        "imageRoot": require_directory(runtime.get("imageRoot"), "imageRoot"),
        "instancePath": require_directory(runtime.get("instancePath"), "instancePath"),
        "instance": require_token(runtime.get("instance"), "instance"),
        "bundle": require_token(runtime.get("bundle"), "bundle"),
        "ability": require_token(runtime.get("ability"), "ability"),
        "environmentIdentity": require_token(runtime.get("environmentIdentity"), "environmentIdentity"),
        "bootMode": runtime.get("bootMode", "coldboot"),
        "profileSamples": runtime.get("profileSamples", 12),
        "portReleaseTimeoutSeconds": runtime.get("portReleaseTimeoutSeconds", 120),
    }
    if runtime["bootMode"] not in {"coldboot", "reset", "snapshot"}:
        raise CalibrationError("unsupported bootMode")
    if not isinstance(runtime.get("hdcPort"), int) or not 10000 <= runtime["hdcPort"] <= 16555:
        raise CalibrationError("hdcPort must be in 10000..16555")
    if not isinstance(runtime["profileSamples"], int) or not 1 <= runtime["profileSamples"] <= 60:
        raise CalibrationError("profileSamples must be in 1..60")
    if (
        not isinstance(runtime["portReleaseTimeoutSeconds"], int)
        or not 1 <= runtime["portReleaseTimeoutSeconds"] <= 300
    ):
        raise CalibrationError("portReleaseTimeoutSeconds must be in 1..300")
    policy = require_path(plan.get("performancePolicy"), "performance policy")
    policy_value = load_object(policy)
    if policy_value.get("schema") != "agentlab.harmony_performance_policy.v1":
        raise CalibrationError("unsupported performance policy schema")
    policy_id = require_token(policy_value.get("id"), "performance policy id")
    workload = require_path(plan.get("profileWorkload"), "profile workload")
    workload_id = next(
        (
            line.split("\t", 1)[1]
            for line in workload.read_text(encoding="utf-8").splitlines()
            if line.startswith("workload\t")
        ),
        None,
    )
    workload_id = require_token(workload_id, "profile workload id")
    return {
        "id": calibration_id,
        "taskId": task_id,
        "harnessRevision": harness_revision,
        "applicationSource": application_source,
        "baselineHap": baseline_hap,
        "baselineIdentity": baseline_identity,
        "candidateHap": candidate_hap,
        "candidateIdentity": candidate_identity,
        "mutation": mutation,
        "scenario": scenario,
        "scenarioId": scenario_id,
        "scenarioSha256": scenario_sha,
        "runner": runner,
        "comparator": comparator,
        "runtime": runtime,
        "policy": policy,
        "policyId": policy_id,
        "policySha256": sha256(policy),
        "workload": workload,
        "workloadId": workload_id,
        "workloadSha256": sha256(workload),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        print(f"refusing to overwrite existing output: {output}", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = pathlib.Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    phases: list[dict[str, Any]] = []
    try:
        plan = load_object(args.plan.resolve())
        validated = validate_plan(plan)
        raw = stage / "raw"
        raw.mkdir()
        baseline_output = raw / "baseline"
        candidate_outputs = [raw / "candidate-01", raw / "candidate-02"]
        baseline_run_id = f"{validated['taskId']}-baseline-v1"
        candidate_run_ids = [
            f"{validated['taskId']}-candidate-v1",
            f"{validated['taskId']}-candidate-v2",
        ]
        run_phase(
            runner_command(
                validated["runner"], validated["runtime"], validated["baselineHap"],
                validated["baselineIdentity"], baseline_output, validated["scenario"],
                validated["policy"], validated["workload"], validated["taskId"], baseline_run_id,
            ),
            "baseline",
            stage,
            phases,
        )
        wait_for_port_release(
            validated["runtime"]["hdcPort"],
            validated["runtime"]["portReleaseTimeoutSeconds"],
            "port-release-after-baseline",
            phases,
        )
        for index, candidate_output in enumerate(candidate_outputs):
            run_phase(
                runner_command(
                    validated["runner"], validated["runtime"], validated["candidateHap"],
                    validated["candidateIdentity"], candidate_output, validated["scenario"],
                    validated["policy"], validated["workload"], validated["taskId"], candidate_run_ids[index],
                ),
                f"candidate-{index + 1}",
                stage,
                phases,
            )
            if index == 0:
                wait_for_port_release(
                    validated["runtime"]["hdcPort"],
                    validated["runtime"]["portReleaseTimeoutSeconds"],
                    "port-release-after-candidate-1",
                    phases,
                )

        validate_run_output(
            baseline_output,
            "baseline",
            validated,
            validated["baselineIdentity"],
            baseline_run_id,
        )
        for index, candidate_output in enumerate(candidate_outputs):
            validate_run_output(
                candidate_output,
                f"candidate-{index + 1}",
                validated,
                validated["candidateIdentity"],
                candidate_run_ids[index],
            )

        comparison_paths = [stage / "smartperf-comparison.json", stage / "smartperf-repeat-comparison.json"]
        for index, candidate_output in enumerate(candidate_outputs):
            run_phase(
                [
                    sys.executable,
                    str(validated["comparator"]),
                    "--baseline", str(baseline_output / "smartperf-summary.json"),
                    "--candidate", str(candidate_output / "smartperf-summary.json"),
                    "--baseline-result", str(baseline_output / "result.json"),
                    "--candidate-result", str(candidate_output / "result.json"),
                    "--output", str(comparison_paths[index]),
                ],
                f"compare-{index + 1}",
                stage,
                phases,
            )

        comparisons = [load_object(path) for path in comparison_paths]
        if any(value.get("decision") != "performance-regression-candidate" for value in comparisons):
            raise CalibrationError("both candidate comparisons must detect a performance regression")
        if any((value.get("functionalGate") or {}).get("passed") is not True for value in comparisons):
            raise CalibrationError("both candidate comparisons require a passing functional Oracle")
        regressed = [
            {row.get("metric") for row in value.get("metrics", []) if row.get("status") == "regressed"}
            for value in comparisons
        ]
        common_regressions = sorted(regressed[0] & regressed[1])
        if not common_regressions:
            raise CalibrationError("candidate comparisons do not share a regressed metric")

        shutil.copy2(baseline_output / "smartperf-summary.json", stage / "smartperf-baseline-summary.json")
        shutil.copy2(candidate_outputs[0] / "smartperf-summary.json", stage / "smartperf-candidate-summary.json")
        shutil.copy2(candidate_outputs[1] / "smartperf-summary.json", stage / "smartperf-candidate-repeat-summary.json")
        shutil.copy2(baseline_output / "result.json", stage / "harmony-baseline-result.json")
        shutil.copy2(candidate_outputs[0] / "result.json", stage / "harmony-candidate-result.json")
        shutil.copy2(candidate_outputs[1] / "result.json", stage / "harmony-candidate-repeat-result.json")
        shutil.copy2(validated["policy"], stage / "performance-policy.json")
        shutil.copy2(validated["workload"], stage / "profile-workload.tsv")
        write_json(stage / "summary.json", {"taskId": validated["taskId"], "sourceRevision": validated["harnessRevision"]})
        calibration = {
            "schema": CALIBRATION_SCHEMA,
            "id": validated["id"],
            "taskId": validated["taskId"],
            "harnessRevision": validated["harnessRevision"],
            "applicationSource": validated["applicationSource"],
            "baseline": {"sourceIdentity": validated["baselineIdentity"]},
            "candidate": {
                "sourceIdentity": validated["candidateIdentity"],
                "baseSourceIdentity": validated["baselineIdentity"],
                "controlledMutation": validated["mutation"],
            },
            "functionalOracle": {
                "scenarioId": validated["scenarioId"],
                "scenarioSha256": validated["scenarioSha256"],
                "expected": "passed-both",
            },
            "environmentIdentity": validated["runtime"]["environmentIdentity"],
            "performancePolicy": {"id": validated["policyId"], "sha256": validated["policySha256"]},
            "profileWorkload": {"id": validated["workloadId"], "sha256": validated["workloadSha256"]},
            "comparisonSha256": sha256(comparison_paths[0]),
            "expectedDecision": "performance-regression-candidate",
            "repeatability": {
                "status": "reproduced",
                "minimumCandidateRuns": 2,
                "candidateRunIds": candidate_run_ids,
                "comparisonSha256s": [sha256(path) for path in comparison_paths],
                "consistentRegressedMetrics": common_regressions,
            },
            "authority": {
                "relativePerformance": "smartperf-emulator-proxy",
                "absolutePowerThermal": "unavailable-on-emulator",
            },
            "automaticPromotion": False,
        }
        write_json(stage / "performance-calibration.json", calibration)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": "passed",
            "planSha256": sha256(args.plan.resolve()),
            "runnerSha256": sha256(validated["runner"]),
            "comparatorSha256": sha256(validated["comparator"]),
            "baselineSourceIdentity": validated["baselineIdentity"],
            "candidateSourceIdentity": validated["candidateIdentity"],
            "candidateRunIds": candidate_run_ids,
            "consistentRegressedMetrics": common_regressions,
            "phases": phases,
            "automaticPromotion": False,
        }
        write_json(stage / "calibration-run.json", receipt)
        stage.rename(output)
        print(json.dumps({"ok": True, "output": str(output), "consistentRegressedMetrics": common_regressions}, sort_keys=True))
        return 0
    except (CalibrationError, OSError) as error:
        failure = {
            "schema": RECEIPT_SCHEMA,
            "status": "failed",
            "error": str(error),
            "phases": phases,
            "automaticPromotion": False,
        }
        write_json(stage / "failure.json", failure)
        print(json.dumps({"ok": False, "retained": str(stage), "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
