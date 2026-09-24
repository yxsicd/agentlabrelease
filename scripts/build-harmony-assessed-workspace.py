#!/usr/bin/env python3
"""Build a Harmony HAP from one exact, independently assessed Agent workspace."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from typing import Any


PLAN_SCHEMA = "agentlab.harmony_assessed_workspace_build_plan.v1"
RECEIPT_SCHEMA = "agentlab.harmony_case_build_receipt.v1"
MATERIALIZATION_SCHEMA = "agentlab.harmony_assessed_source_materialization.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


class BuildError(RuntimeError):
    pass


def sha256(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def load(path: pathlib.Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BuildError(f"cannot load {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise BuildError(f"{label} must be a JSON object")
    return value


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def require_file(value: Any, label: str, *, executable: bool = False) -> pathlib.Path:
    if not isinstance(value, str) or not value:
        raise BuildError(f"{label} path is required")
    path = pathlib.Path(value).resolve()
    if not path.is_file() or path.is_symlink():
        raise BuildError(f"{label} must be a regular file: {path}")
    if executable and not os.access(path, os.X_OK):
        raise BuildError(f"{label} is not executable: {path}")
    return path


def require_directory(value: Any, label: str) -> pathlib.Path:
    if not isinstance(value, str) or not value:
        raise BuildError(f"{label} path is required")
    path = pathlib.Path(value).resolve()
    if not path.is_dir() or path.is_symlink():
        raise BuildError(f"{label} must be a regular directory: {path}")
    return path


def bound_file(binding: Any, label: str) -> pathlib.Path:
    if not isinstance(binding, dict):
        raise BuildError(f"{label} binding is required")
    path = require_file(binding.get("path"), label)
    expected = binding.get("sha256")
    if not isinstance(expected, str) or SHA256.fullmatch(expected) is None:
        raise BuildError(f"{label} SHA256 is invalid")
    if sha256(path) != expected:
        raise BuildError(f"{label} SHA256 differs from build plan")
    return path


def safe_relative(value: Any, label: str, *, dot: bool = True) -> pathlib.PurePosixPath:
    if not isinstance(value, str) or not value:
        raise BuildError(f"{label} is required")
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "" in path.parts:
        raise BuildError(f"{label} must stay within the workspace")
    if not dot and str(path) == ".":
        raise BuildError(f"{label} must name a path")
    return path


def validate_sources(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) < 2:
        raise BuildError("evaluation case requires at least two exact sources")
    rows = []
    for row in value:
        if not isinstance(row, dict):
            raise BuildError("evaluation source must be an object")
        if not isinstance(row.get("id"), str) or not row["id"]:
            raise BuildError("evaluation source id is required")
        if not isinstance(row.get("repository"), str) or not row["repository"]:
            raise BuildError("evaluation source repository is required")
        if not isinstance(row.get("revision"), str) or REVISION.fullmatch(row["revision"]) is None:
            raise BuildError("evaluation source revision must be exact")
        rows.append({key: row[key] for key in ("id", "repository", "revision")})
    if len({row["id"] for row in rows}) != len(rows):
        raise BuildError("evaluation source ids must be unique")
    return sorted(rows, key=lambda row: row["id"])


def validate_state(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    normalized = {}
    for name, row in value.items():
        path = safe_relative(name, "final source state path", dot=False).as_posix()
        if path != name or not isinstance(row, dict):
            raise BuildError("final source state contains a non-canonical path")
        digest = row.get("sha256")
        length = row.get("byteLength")
        unix_mode = row.get("unixMode")
        if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
            raise BuildError(f"final source state digest is invalid for {name}")
        if not isinstance(length, int) or length < 0:
            raise BuildError(f"final source state byteLength is invalid for {name}")
        if not isinstance(unix_mode, int) or unix_mode not in {0o644, 0o755}:
            raise BuildError(f"final source state unixMode is invalid for {name}")
        normalized[name] = {"sha256": digest, "byteLength": length, "unixMode": unix_mode}
    if not normalized:
        raise BuildError("final source state is empty")
    return normalized


def inspect_workspace(root: pathlib.Path) -> dict[str, dict[str, Any]]:
    rows = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise BuildError(f"assessed workspace contains a symbolic link: {path.relative_to(root)}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        rows[relative] = {
            "sha256": sha256(path),
            "byteLength": path.stat().st_size,
            "unixMode": path.stat().st_mode & 0o777,
        }
    return rows


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("schema") != PLAN_SCHEMA:
        raise BuildError("unsupported assessed-workspace build plan schema")
    if plan.get("automaticPromotion") is not False:
        raise BuildError("assessed-workspace build plan must set automaticPromotion=false")

    case_path = bound_file(plan.get("evaluationCase"), "evaluation case")
    case_sha256 = sha256(case_path)
    case = load(case_path, "evaluation case")
    if (
        case.get("schema") != "agentlab.multi_repo_evaluation_case.v1"
        or case.get("status") != "frozen-calibrated"
        or case.get("automaticPromotion") is not False
        or (case.get("calibration") or {}).get("qualified") is not True
    ):
        raise BuildError("build requires a frozen calibrated non-promoted case")
    case_id = case.get("id")
    source_set = case.get("sourceSetSha256")
    if not isinstance(case_id, str) or not case_id:
        raise BuildError("evaluation case id is invalid")
    if not isinstance(source_set, str) or SHA256.fullmatch(source_set) is None:
        raise BuildError("evaluation case sourceSetSha256 is invalid")
    sources = validate_sources(case.get("sources"))
    source_ids = {row["id"] for row in sources}

    assessment = plan.get("assessment") or {}
    summary_path = bound_file(assessment.get("summary"), "assessment summary")
    decision_path = bound_file(assessment.get("decisionPackage"), "assessment decision package")
    state_path = bound_file(assessment.get("finalSourceState"), "final source state")
    workspace = require_directory(assessment.get("workspace"), "assessed workspace")
    summary = load(summary_path, "assessment summary")
    decision = load(decision_path, "assessment decision package")
    final_state = validate_state(load(state_path, "final source state"))
    participant_id = summary.get("participantId")
    common = {
        "taskId": case_id,
        "sourceSetSha256": source_set,
        "assessmentStatus": "assessed",
        "infrastructureAvailable": True,
        "subjectTaskSucceeded": True,
    }
    if summary.get("schema") != "agentlab.multi_repo_assessment_summary.v1":
        raise BuildError("unsupported assessment summary schema")
    if decision.get("schema") != "agentlab.harness_decision_package.v1":
        raise BuildError("unsupported assessment decision schema")
    if any(summary.get(key) != value or decision.get(key) != value for key, value in common.items()):
        raise BuildError("only an independently assessed passing workspace can enter Harmony build")
    if not isinstance(participant_id, str) or not participant_id or decision.get("participantId") != participant_id:
        raise BuildError("assessment participant identity mismatch")
    if decision.get("automaticPromotion") is not False:
        raise BuildError("assessment decision must not auto-promote")
    if summary.get("finalWorkspaceSha256") != canonical_sha256(final_state):
        raise BuildError("assessment summary does not bind final source state")
    if inspect_workspace(workspace) != final_state:
        raise BuildError("assessed workspace differs from final source state")

    mappings = plan.get("sourceMaterialization")
    if not isinstance(mappings, list) or not mappings:
        raise BuildError("sourceMaterialization mappings are required")
    normalized_mappings = []
    mapped_ids = set()
    for index, mapping in enumerate(mappings):
        if not isinstance(mapping, dict) or mapping.get("sourceId") not in source_ids:
            raise BuildError(f"sourceMaterialization[{index}] sourceId is invalid")
        source_id = mapping["sourceId"]
        source_path = safe_relative(mapping.get("sourcePath", "."), "sourcePath")
        target_path = safe_relative(mapping.get("targetPath", "."), "targetPath")
        prefix = source_id if str(source_path) == "." else f"{source_id}/{source_path.as_posix()}"
        if not any(name == prefix or name.startswith(prefix + "/") for name in final_state):
            raise BuildError(f"sourceMaterialization[{index}] selects no assessed files")
        normalized_mappings.append(
            {"sourceId": source_id, "sourcePath": source_path, "targetPath": target_path}
        )
        mapped_ids.add(source_id)
    if mapped_ids != source_ids:
        raise BuildError("every frozen evaluation source must be materialized")

    build = plan.get("build") or {}
    executable = require_file(build.get("executable"), "build executable", executable=True)
    if build.get("executableSha256") != sha256(executable):
        raise BuildError("build executable SHA256 differs from build plan")
    arguments = build.get("arguments")
    if not isinstance(arguments, list) or not all(isinstance(value, str) and "\0" not in value for value in arguments):
        raise BuildError("build arguments must be a string list")
    working_directory = safe_relative(build.get("workingDirectory", "."), "build workingDirectory")
    artifact_path = safe_relative(build.get("artifactPath"), "build artifactPath", dot=False)
    timeout = build.get("timeoutSeconds", 900)
    if not isinstance(timeout, int) or not 1 <= timeout <= 3600:
        raise BuildError("build timeoutSeconds must be in 1..3600")
    environment = build.get("environment", {})
    if not isinstance(environment, dict) or not all(
        isinstance(key, str) and key and "=" not in key and "\0" not in key
        and isinstance(value, str) and "\0" not in value
        for key, value in environment.items()
    ):
        raise BuildError("build environment must contain valid string keys and values")
    return {
        "casePath": case_path,
        "caseSha256": case_sha256,
        "caseId": case_id,
        "sourceSetSha256": source_set,
        "sources": sources,
        "summaryPath": summary_path,
        "summarySha256": sha256(summary_path),
        "decisionPath": decision_path,
        "decisionSha256": sha256(decision_path),
        "statePath": state_path,
        "stateSha256": sha256(state_path),
        "workspace": workspace,
        "finalState": final_state,
        "participantId": participant_id,
        "mappings": normalized_mappings,
        "executable": executable,
        "executableSha256": sha256(executable),
        "arguments": arguments,
        "workingDirectory": working_directory,
        "artifactPath": artifact_path,
        "timeout": timeout,
        "environment": environment,
    }


def materialize(validated: dict[str, Any], destination: pathlib.Path) -> dict[str, Any]:
    files = []
    occupied = set()
    for mapping in validated["mappings"]:
        source_root = pathlib.PurePosixPath(mapping["sourceId"]) / mapping["sourcePath"]
        for name, identity in sorted(validated["finalState"].items()):
            source = pathlib.PurePosixPath(name)
            try:
                relative = source.relative_to(source_root)
            except ValueError:
                continue
            target = mapping["targetPath"] / relative
            target_name = target.as_posix()
            if target_name in occupied:
                raise BuildError(f"assessed source target collision: {target_name}")
            occupied.add(target_name)
            original = validated["workspace"] / pathlib.Path(*source.parts)
            raw = original.read_bytes()
            if hashlib.sha256(raw).hexdigest() != identity["sha256"] or len(raw) != identity["byteLength"]:
                raise BuildError(f"assessed source changed during materialization: {name}")
            output = destination / pathlib.Path(*target.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(raw)
            output.chmod(identity["unixMode"])
            files.append(
                {
                    "sourceId": mapping["sourceId"],
                    "sourcePath": name,
                    "targetPath": target_name,
                    "sha256": identity["sha256"],
                    "byteLength": identity["byteLength"],
                    "unixMode": identity["unixMode"],
                }
            )
    return {
        "schema": MATERIALIZATION_SCHEMA,
        "caseId": validated["caseId"],
        "evaluationCaseSha256": validated["caseSha256"],
        "sourceSetSha256": validated["sourceSetSha256"],
        "participantId": validated["participantId"],
        "subjectWorkspaceSha256": canonical_sha256(validated["finalState"]),
        "assessmentSummarySha256": sha256(validated["summaryPath"]),
        "assessmentDecisionSha256": sha256(validated["decisionPath"]),
        "finalSourceStateSha256": sha256(validated["statePath"]),
        "mappings": [
            {
                "sourceId": row["sourceId"],
                "sourcePath": row["sourcePath"].as_posix(),
                "targetPath": row["targetPath"].as_posix(),
            }
            for row in validated["mappings"]
        ],
        "files": sorted(files, key=lambda row: row["targetPath"]),
        "fileCount": len(files),
        "byteCount": sum(row["byteLength"] for row in files),
        "automaticPromotion": False,
    }


def run_build(command: list[str], cwd: pathlib.Path, environment: dict[str, str], timeout: int):
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env={**os.environ, **environment},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode, stdout, stderr, False
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return process.returncode, stdout, stderr, True


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
    workspace = stage / "workspace"
    workspace.mkdir()
    try:
        plan_path = args.plan.resolve()
        plan_sha256 = sha256(plan_path)
        validated = validate_plan(load(plan_path, "assessed-workspace build plan"))
        materialization = materialize(validated, workspace)
        materialization_path = stage / "source-materialization.json"
        write_json(materialization_path, materialization)
        working_directory = workspace / pathlib.Path(*validated["workingDirectory"].parts)
        if not working_directory.is_dir():
            raise BuildError("build working directory was not materialized")
        artifact_in_workspace = workspace / pathlib.Path(*validated["artifactPath"].parts)
        replacements = {"{workspace}": str(workspace), "{artifact}": str(artifact_in_workspace)}
        command = [str(validated["executable"])]
        for argument in validated["arguments"]:
            for marker, replacement in replacements.items():
                argument = argument.replace(marker, replacement)
            command.append(argument)
        command_binding = {
            "executableSha256": validated["executableSha256"],
            "arguments": validated["arguments"],
            "workingDirectory": validated["workingDirectory"].as_posix(),
            "artifactPath": validated["artifactPath"].as_posix(),
            "timeoutSeconds": validated["timeout"],
            "environmentKeys": sorted(validated["environment"]),
            "environmentSha256": canonical_sha256(validated["environment"]),
        }
        exit_code, stdout, stderr, timed_out = run_build(
            command, working_directory, validated["environment"], validated["timeout"]
        )
        stdout_path = stage / "build.stdout.log"
        stderr_path = stage / "build.stderr.log"
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        if timed_out:
            raise BuildError(f"Harmony build timed out after {validated['timeout']} seconds")
        if exit_code != 0:
            raise BuildError(f"Harmony build failed with exit {exit_code}")
        if not artifact_in_workspace.is_file() or artifact_in_workspace.is_symlink():
            raise BuildError("Harmony build did not produce a regular declared HAP artifact")
        artifact = stage / "artifact.hap"
        shutil.copyfile(artifact_in_workspace, artifact)
        immutable = (
            (plan_path, plan_sha256, "build plan"),
            (validated["casePath"], validated["caseSha256"], "evaluation case"),
            (validated["summaryPath"], validated["summarySha256"], "assessment summary"),
            (validated["decisionPath"], validated["decisionSha256"], "assessment decision"),
            (validated["statePath"], validated["stateSha256"], "final source state"),
            (validated["executable"], validated["executableSha256"], "build executable"),
        )
        for path, expected, label in immutable:
            if sha256(path) != expected:
                raise BuildError(f"{label} changed during execution")
        if inspect_workspace(validated["workspace"]) != validated["finalState"]:
            raise BuildError("assessed workspace changed during execution")
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": "passed",
            "caseId": validated["caseId"],
            "evaluationCaseSha256": validated["caseSha256"],
            "sourceSetSha256": validated["sourceSetSha256"],
            "sources": validated["sources"],
            "participantId": validated["participantId"],
            "subjectWorkspaceSha256": materialization["subjectWorkspaceSha256"],
            "assessmentSummarySha256": materialization["assessmentSummarySha256"],
            "assessmentDecisionSha256": materialization["assessmentDecisionSha256"],
            "finalSourceStateSha256": materialization["finalSourceStateSha256"],
            "sourceMaterializationSha256": sha256(materialization_path),
            "sourceMaterializationContentSha256": canonical_sha256(materialization),
            "buildToolSha256": validated["executableSha256"],
            "buildCommandSha256": canonical_sha256(command_binding),
            "planSha256": plan_sha256,
            "hapSha256": sha256(artifact),
            "hapBytes": artifact.stat().st_size,
            "buildExitCode": exit_code,
            "buildTimedOut": False,
            "buildStdoutSha256": sha256(stdout_path),
            "buildStderrSha256": sha256(stderr_path),
            "buildAuthority": "independent-harmony-assessed-workspace-build",
            "automaticPromotion": False,
        }
        write_json(stage / "build-receipt.json", receipt)
        shutil.rmtree(workspace)
        stage.rename(output)
        print(json.dumps({"ok": True, "output": str(output), "participantId": validated["participantId"], "hapSha256": receipt["hapSha256"]}, sort_keys=True))
        return 0
    except (BuildError, OSError) as error:
        write_json(stage / "failure.json", {"schema": RECEIPT_SCHEMA, "status": "failed", "error": str(error), "automaticPromotion": False})
        print(json.dumps({"ok": False, "retained": str(stage), "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
