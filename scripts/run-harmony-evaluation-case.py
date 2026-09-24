#!/usr/bin/env python3
"""Run one frozen multi-repository case through a receipt-bound Harmony emulator artifact."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any


PLAN_SCHEMA = "agentlab.harmony_evaluation_run_plan.v1"
BUILD_SCHEMA = "agentlab.harmony_case_build_receipt.v1"
RESULT_SCHEMA = "agentlab.harmony_emulator_case_result.v3"
BINDING_SCHEMA = "agentlab.harmony_evaluation_binding.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[A-Za-z0-9_.:-]+")


class EvaluationRunError(RuntimeError):
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
        raise EvaluationRunError(f"cannot load JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise EvaluationRunError(f"expected JSON object: {path}")
    return value


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def require_file(value: Any, label: str, *, executable: bool = False) -> pathlib.Path:
    if not isinstance(value, str) or not value:
        raise EvaluationRunError(f"{label} path is required")
    path = pathlib.Path(value).resolve()
    if not path.is_file():
        raise EvaluationRunError(f"{label} file not found: {path}")
    if executable and not os.access(path, os.X_OK):
        raise EvaluationRunError(f"{label} is not executable: {path}")
    return path


def require_directory(value: Any, label: str) -> pathlib.Path:
    if not isinstance(value, str) or not value:
        raise EvaluationRunError(f"{label} path is required")
    path = pathlib.Path(value).resolve()
    if not path.is_dir():
        raise EvaluationRunError(f"{label} directory not found: {path}")
    return path


def require_token(value: Any, label: str) -> str:
    if not isinstance(value, str) or TOKEN.fullmatch(value) is None:
        raise EvaluationRunError(f"{label} must be a non-empty safe token")
    return value


def validate_sources(sources: Any) -> list[dict[str, str]]:
    if not isinstance(sources, list) or len(sources) < 2:
        raise EvaluationRunError("frozen evaluation case requires at least two sources")
    normalized = []
    for source in sources:
        if not isinstance(source, dict):
            raise EvaluationRunError("evaluation source must be an object")
        source_id = source.get("id")
        repository = source.get("repository")
        revision = source.get("revision")
        if not isinstance(source_id, str) or not source_id:
            raise EvaluationRunError("evaluation source id is required")
        if not isinstance(repository, str) or not repository:
            raise EvaluationRunError("evaluation source repository is required")
        if not isinstance(revision, str) or REVISION.fullmatch(revision) is None:
            raise EvaluationRunError("evaluation source revision must be exact")
        normalized.append({"id": source_id, "repository": repository, "revision": revision})
    if len({row["id"] for row in normalized}) != len(normalized):
        raise EvaluationRunError("evaluation source ids must be unique")
    return sorted(normalized, key=lambda row: row["id"])


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise EvaluationRunError(f"{label} must be an exact SHA256")
    return value


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("schema") != PLAN_SCHEMA:
        raise EvaluationRunError("unsupported Harmony evaluation run plan schema")
    if plan.get("automaticPromotion") is not False:
        raise EvaluationRunError("Harmony evaluation run plan must set automaticPromotion=false")
    subject_outcome_policy = plan.get("subjectOutcomePolicy", "require-pass")
    if subject_outcome_policy not in {"require-pass", "retain-assessed-failure"}:
        raise EvaluationRunError("unsupported subjectOutcomePolicy")

    case_binding = plan.get("evaluationCase") or {}
    case_path = require_file(case_binding.get("path"), "evaluation case")
    case_sha256 = sha256(case_path)
    if require_digest(case_binding.get("sha256"), "evaluation case sha256") != case_sha256:
        raise EvaluationRunError("evaluation case SHA256 differs from run plan")
    case = load_object(case_path)
    if case.get("schema") != "agentlab.multi_repo_evaluation_case.v1":
        raise EvaluationRunError("unsupported multi-repository evaluation case schema")
    if case.get("status") != "frozen-calibrated":
        raise EvaluationRunError("evaluation case is not frozen and calibrated")
    if case.get("automaticPromotion") is not False:
        raise EvaluationRunError("evaluation case must not claim automatic promotion")
    if (case.get("calibration") or {}).get("qualified") is not True:
        raise EvaluationRunError("evaluation case calibration is not qualified")
    if (case.get("oracle") or {}).get("authority") != "independent-executable-oracle":
        raise EvaluationRunError("evaluation case requires an independent executable Oracle")
    case_id = require_token(case.get("id"), "evaluation case id")
    source_set_sha256 = require_digest(case.get("sourceSetSha256"), "sourceSetSha256")
    sources = validate_sources(case.get("sources"))

    build_binding = plan.get("buildReceipt") or {}
    build_path = require_file(build_binding.get("path"), "Harmony build receipt")
    build_sha256 = sha256(build_path)
    if require_digest(build_binding.get("sha256"), "Harmony build receipt sha256") != build_sha256:
        raise EvaluationRunError("Harmony build receipt SHA256 differs from run plan")
    build = load_object(build_path)
    if build.get("schema") != BUILD_SCHEMA or build.get("status") != "passed":
        raise EvaluationRunError("Harmony build receipt did not pass")
    if build.get("automaticPromotion") is not False:
        raise EvaluationRunError("Harmony build receipt must not auto-promote")
    build_authority = build.get("buildAuthority")
    if build_authority not in {
        "independent-harmony-build",
        "independent-harmony-assessed-workspace-build",
    }:
        raise EvaluationRunError("Harmony build receipt authority is unsupported")
    if (
        build.get("caseId") != case_id
        or build.get("evaluationCaseSha256") != case_sha256
        or build.get("sourceSetSha256") != source_set_sha256
        or validate_sources(build.get("sources")) != sources
    ):
        raise EvaluationRunError("Harmony build receipt lineage differs from evaluation case")
    require_digest(build.get("buildToolSha256"), "Harmony build tool sha256")
    require_digest(build.get("sourceMaterializationSha256"), "source materialization sha256")
    assessed_workspace = None
    if build_authority == "independent-harmony-assessed-workspace-build":
        participant_id = require_token(build.get("participantId"), "assessment participantId")
        assessed_workspace = {
            "participantId": participant_id,
            "subjectWorkspaceSha256": require_digest(
                build.get("subjectWorkspaceSha256"), "subject workspace sha256"
            ),
            "assessmentSummarySha256": require_digest(
                build.get("assessmentSummarySha256"), "assessment summary sha256"
            ),
            "assessmentDecisionSha256": require_digest(
                build.get("assessmentDecisionSha256"), "assessment decision sha256"
            ),
            "finalSourceStateSha256": require_digest(
                build.get("finalSourceStateSha256"), "final source state sha256"
            ),
        }

    artifact = plan.get("artifact") or {}
    hap = require_file(artifact.get("path"), "HAP artifact")
    hap_sha256 = sha256(hap)
    if require_digest(artifact.get("sha256"), "HAP artifact sha256") != hap_sha256:
        raise EvaluationRunError("HAP SHA256 differs from run plan")
    if build.get("hapSha256") != hap_sha256:
        raise EvaluationRunError("HAP SHA256 differs from build receipt")

    oracle = plan.get("functionalOracle") or {}
    scenario = require_file(oracle.get("path"), "functional Oracle scenario")
    scenario_sha256 = sha256(scenario)
    if require_digest(oracle.get("sha256"), "functional Oracle sha256") != scenario_sha256:
        raise EvaluationRunError("functional Oracle SHA256 differs from run plan")
    scenario_id = require_token(oracle.get("scenarioId"), "functional Oracle scenarioId")

    runtime = plan.get("runtime") or {}
    runner = require_file(runtime.get("runner"), "Harmony emulator runner", executable=True)
    runner_sha256 = sha256(runner)
    if require_digest(runtime.get("runnerSha256"), "Harmony emulator runner sha256") != runner_sha256:
        raise EvaluationRunError("Harmony emulator runner SHA256 differs from run plan")
    runtime = {
        "runner": runner,
        "runnerSha256": runner_sha256,
        "toolsRoot": require_directory(runtime.get("toolsRoot"), "toolsRoot"),
        "imageRoot": require_directory(runtime.get("imageRoot"), "imageRoot"),
        "instancePath": require_directory(runtime.get("instancePath"), "instancePath"),
        "instance": require_token(runtime.get("instance"), "instance"),
        "bundle": require_token(runtime.get("bundle"), "bundle"),
        "ability": require_token(runtime.get("ability"), "ability"),
        "environmentIdentity": require_token(runtime.get("environmentIdentity"), "environmentIdentity"),
        "bootMode": runtime.get("bootMode", "coldboot"),
        "profileSamples": runtime.get("profileSamples", 3),
        "hdcPort": runtime.get("hdcPort"),
    }
    if runtime["bootMode"] not in {"coldboot", "reset", "snapshot"}:
        raise EvaluationRunError("unsupported bootMode")
    if not isinstance(runtime["hdcPort"], int) or not 10000 <= runtime["hdcPort"] <= 16555:
        raise EvaluationRunError("hdcPort must be in 10000..16555")
    if not isinstance(runtime["profileSamples"], int) or not 1 <= runtime["profileSamples"] <= 60:
        raise EvaluationRunError("profileSamples must be in 1..60")

    performance = plan.get("performance") or {}
    policy = require_file(performance.get("policy"), "performance policy")
    workload = require_file(performance.get("workload"), "profile workload")
    policy_sha256 = sha256(policy)
    workload_sha256 = sha256(workload)
    if require_digest(performance.get("policySha256"), "performance policy sha256") != policy_sha256:
        raise EvaluationRunError("performance policy SHA256 differs from run plan")
    if require_digest(performance.get("workloadSha256"), "profile workload sha256") != workload_sha256:
        raise EvaluationRunError("profile workload SHA256 differs from run plan")

    return {
        "case": case,
        "casePath": case_path,
        "caseSha256": case_sha256,
        "caseId": case_id,
        "sourceSetSha256": source_set_sha256,
        "sources": sources,
        "buildPath": build_path,
        "buildSha256": build_sha256,
        "build": build,
        "buildAuthority": build_authority,
        "assessedWorkspace": assessed_workspace,
        "hap": hap,
        "hapSha256": hap_sha256,
        "scenario": scenario,
        "scenarioId": scenario_id,
        "scenarioSha256": scenario_sha256,
        "runtime": runtime,
        "policy": policy,
        "policySha256": policy_sha256,
        "workload": workload,
        "workloadSha256": workload_sha256,
        "runId": require_token(plan.get("runId"), "runId"),
        "subjectOutcomePolicy": subject_outcome_policy,
    }


def runner_command(validated: dict[str, Any], execution: pathlib.Path) -> list[str]:
    runtime = validated["runtime"]
    return [
        str(runtime["runner"]),
        "run-case",
        "--tools-root", str(runtime["toolsRoot"]),
        "--image-root", str(runtime["imageRoot"]),
        "--instance-path", str(runtime["instancePath"]),
        "--instance", runtime["instance"],
        "--hdc-port", str(runtime["hdcPort"]),
        "--hap", str(validated["hap"]),
        "--bundle", runtime["bundle"],
        "--ability", runtime["ability"],
        "--output", str(execution),
        "--ui-scenario", str(validated["scenario"]),
        "--task-id", validated["caseId"],
        "--source-id", f"artifact-sha256:{validated['hapSha256']}",
        "--source-set-sha256", validated["sourceSetSha256"],
        "--profile-run-id", validated["runId"],
        "--environment-id", runtime["environmentIdentity"],
        "--performance-policy", str(validated["policy"]),
        "--profile-workload", str(validated["workload"]),
        "--boot-mode", runtime["bootMode"],
        "--profile-samples", str(runtime["profileSamples"]),
        "--reset-app-data",
    ]


def validate_result(
    result: dict[str, Any], validated: dict[str, Any], execution: pathlib.Path
) -> bool:
    runtime = validated["runtime"]
    expected = {
        "schema": RESULT_SCHEMA,
        "taskId": validated["caseId"],
        "sourceIdentity": f"artifact-sha256:{validated['hapSha256']}",
        "sourceSetSha256": validated["sourceSetSha256"],
        "hapSha256": validated["hapSha256"],
        "scenarioId": validated["scenarioId"],
        "scenarioSha256": validated["scenarioSha256"],
        "assessmentStatus": "assessed",
        "infrastructureAvailable": True,
        "profileRunId": validated["runId"],
        "environmentIdentity": runtime["environmentIdentity"],
        "powerThermalAuthority": "unavailable_on_emulator",
        "performancePolicySha256": validated["policySha256"],
        "profileWorkloadSha256": validated["workloadSha256"],
    }
    for field, value in expected.items():
        if result.get(field) != value:
            raise EvaluationRunError(f"Harmony result {field} differs from bound run plan")
    subject_succeeded = result.get("subjectTaskSucceeded")
    if subject_succeeded is True:
        passing = {
            "status": "passed",
            "oracleStatus": "passed",
            "failureClass": "none",
            "profileStatus": "collected",
            "profileSummaryStatus": "normalized",
        }
        for field, value in passing.items():
            if result.get(field) != value:
                raise EvaluationRunError(f"passing Harmony result {field} is invalid")
        return True
    if subject_succeeded is not False:
        raise EvaluationRunError("Harmony result has no boolean subject verdict")
    if validated["subjectOutcomePolicy"] != "retain-assessed-failure":
        raise EvaluationRunError("Harmony subject failed but run plan requires pass")
    failing = {
        "status": "failed",
        "oracleStatus": "failed",
        "failureClass": "oracle",
        "profileStatus": "not-run",
        "profileSummaryStatus": "not-run",
    }
    for field, value in failing.items():
        if result.get(field) != value:
            raise EvaluationRunError(f"assessed failing Harmony result {field} is invalid")
    checks_path = execution / "ui-checks.tsv"
    if not checks_path.is_file():
        raise EvaluationRunError("assessed failing Harmony result has no UI check evidence")
    verdicts = []
    for line in checks_path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t", 3)
        if len(fields) != 4 or fields[1] not in {"true", "false"}:
            raise EvaluationRunError("assessed failing Harmony result has malformed UI checks")
        verdicts.append(fields[1] == "true")
    if not verdicts or all(verdicts):
        raise EvaluationRunError("assessed failing Harmony result is not supported by a failed UI check")
    return False


def validate_summary(summary: dict[str, Any], validated: dict[str, Any]) -> None:
    runtime = validated["runtime"]
    expected = {
        "schema": "agentlab.smartperf_summary.v2",
        "taskId": validated["caseId"],
        "sourceIdentity": f"artifact-sha256:{validated['hapSha256']}",
        "runId": validated["runId"],
        "environmentIdentity": runtime["environmentIdentity"],
        "sampleCount": runtime["profileSamples"],
        "profileValid": True,
    }
    for field, value in expected.items():
        if summary.get(field) != value:
            raise EvaluationRunError(f"SmartPerf summary {field} differs from bound run plan")
    if (summary.get("performancePolicy") or {}).get("sha256") != validated["policySha256"]:
        raise EvaluationRunError("SmartPerf summary performance policy differs from bound run plan")
    if (summary.get("profileWorkload") or {}).get("sha256") != validated["workloadSha256"]:
        raise EvaluationRunError("SmartPerf summary profile workload differs from bound run plan")
    if (summary.get("authority") or {}).get("absolutePowerThermal") != "unavailable-on-emulator":
        raise EvaluationRunError("SmartPerf summary overstates emulator power or thermal authority")


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
    try:
        plan_path = args.plan.resolve()
        plan_sha256 = sha256(plan_path)
        plan = load_object(plan_path)
        validated = validate_plan(plan)
        execution = stage / "execution"
        completed = subprocess.run(
            runner_command(validated, execution),
            text=True,
            capture_output=True,
            check=False,
        )
        stdout_path = stage / "runner.stdout.log"
        stderr_path = stage / "runner.stderr.log"
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        if sha256(plan_path) != plan_sha256:
            raise EvaluationRunError("Harmony evaluation run plan changed during execution")
        if sha256(validated["casePath"]) != validated["caseSha256"]:
            raise EvaluationRunError("frozen evaluation case changed during execution")
        if sha256(validated["buildPath"]) != validated["buildSha256"]:
            raise EvaluationRunError("Harmony build receipt changed during execution")
        if sha256(validated["hap"]) != validated["hapSha256"]:
            raise EvaluationRunError("HAP artifact changed during execution")
        if sha256(validated["scenario"]) != validated["scenarioSha256"]:
            raise EvaluationRunError("functional Oracle changed during execution")
        if sha256(validated["runtime"]["runner"]) != validated["runtime"]["runnerSha256"]:
            raise EvaluationRunError("Harmony emulator runner changed during execution")
        if sha256(validated["policy"]) != validated["policySha256"]:
            raise EvaluationRunError("performance policy changed during execution")
        if sha256(validated["workload"]) != validated["workloadSha256"]:
            raise EvaluationRunError("profile workload changed during execution")

        result_path = execution / "result.json"
        result = load_object(result_path)
        subject_succeeded = validate_result(result, validated, execution)
        if completed.returncode != 0 and subject_succeeded:
            raise EvaluationRunError(f"Harmony emulator runner failed with exit {completed.returncode}")
        summary_path = execution / "smartperf-summary.json"
        if subject_succeeded:
            if not summary_path.is_file():
                raise EvaluationRunError("Harmony execution did not retain SmartPerf summary")
            summary = load_object(summary_path)
            validate_summary(summary, validated)
            summary_sha256 = sha256(summary_path)
        else:
            if summary_path.exists():
                raise EvaluationRunError("functionally failing Harmony run must not claim a profile summary")
            summary_sha256 = None
        binding = {
            "schema": BINDING_SCHEMA,
            "status": (
                "passed-review-required"
                if subject_succeeded
                else "assessed-failure-review-required"
            ),
            "planSha256": plan_sha256,
            "caseId": validated["caseId"],
            "evaluationCaseSha256": validated["caseSha256"],
            "sourceSetSha256": validated["sourceSetSha256"],
            "sources": validated["sources"],
            "buildReceiptSha256": validated["buildSha256"],
            "buildAuthority": validated["buildAuthority"],
            "hapSha256": validated["hapSha256"],
            "runnerSha256": validated["runtime"]["runnerSha256"],
            "functionalOracleSha256": validated["scenarioSha256"],
            "performancePolicySha256": validated["policySha256"],
            "profileWorkloadSha256": validated["workloadSha256"],
            "resultSha256": sha256(result_path),
            "smartperfSummarySha256": summary_sha256,
            "subjectTaskSucceeded": subject_succeeded,
            "failureClass": result.get("failureClass"),
            "runnerStdoutSha256": sha256(stdout_path),
            "runnerStderrSha256": sha256(stderr_path),
            "environmentIdentity": validated["runtime"]["environmentIdentity"],
            "runId": validated["runId"],
            "automaticPromotion": False,
            "nextGate": "maintainer-adjudication-and-independent-case-calibration",
        }
        if validated["assessedWorkspace"] is not None:
            binding["assessedWorkspace"] = validated["assessedWorkspace"]
        write_json(stage / "evaluation-binding.json", binding)
        stage.rename(output)
        print(
            json.dumps(
                {
                    "ok": True,
                    "output": str(output),
                    "caseId": validated["caseId"],
                    "sourceSetSha256": validated["sourceSetSha256"],
                    "hapSha256": validated["hapSha256"],
                    "status": binding["status"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (EvaluationRunError, OSError) as error:
        failure = {
            "schema": BINDING_SCHEMA,
            "status": "failed",
            "error": str(error),
            "automaticPromotion": False,
        }
        write_json(stage / "failure.json", failure)
        print(
            json.dumps({"ok": False, "retained": str(stage), "error": str(error)}, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
