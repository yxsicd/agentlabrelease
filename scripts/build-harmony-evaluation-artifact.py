#!/usr/bin/env python3
"""Materialize pinned Git sources and build one receipt-bound Harmony evaluation HAP."""
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


PLAN_SCHEMA = "agentlab.harmony_case_build_plan.v1"
RECEIPT_SCHEMA = "agentlab.harmony_case_build_receipt.v1"
MATERIALIZATION_SCHEMA = "agentlab.harmony_source_materialization.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


class BuildError(RuntimeError):
    pass


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def load_object(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BuildError(f"cannot load JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise BuildError(f"expected JSON object: {path}")
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
    if not path.is_file():
        raise BuildError(f"{label} file not found: {path}")
    if executable and not os.access(path, os.X_OK):
        raise BuildError(f"{label} is not executable: {path}")
    return path


def require_directory(value: Any, label: str) -> pathlib.Path:
    if not isinstance(value, str) or not value:
        raise BuildError(f"{label} path is required")
    path = pathlib.Path(value).resolve()
    if not path.is_dir():
        raise BuildError(f"{label} directory not found: {path}")
    return path


def safe_relative(value: Any, label: str, *, dot: bool = True) -> pathlib.PurePosixPath:
    if not isinstance(value, str) or not value:
        raise BuildError(f"{label} is required")
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "" in path.parts:
        raise BuildError(f"{label} must stay within the materialized workspace")
    if str(path) == "." and not dot:
        raise BuildError(f"{label} must name a path")
    return path


def git(checkout: pathlib.Path, args: list[str], *, binary: bool = False) -> bytes | str:
    completed = subprocess.run(
        ["git", "-C", str(checkout), *args],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise BuildError(f"git {' '.join(args)} failed for {checkout}: {message}")
    return completed.stdout if binary else completed.stdout.decode("utf-8").strip()


def validate_sources(sources: Any) -> list[dict[str, str]]:
    if not isinstance(sources, list) or len(sources) < 2:
        raise BuildError("frozen evaluation case requires at least two sources")
    normalized = []
    for source in sources:
        if not isinstance(source, dict):
            raise BuildError("evaluation source must be an object")
        source_id = source.get("id")
        repository = source.get("repository")
        revision = source.get("revision")
        if not isinstance(source_id, str) or not source_id:
            raise BuildError("evaluation source id is required")
        if not isinstance(repository, str) or not repository:
            raise BuildError("evaluation source repository is required")
        if not isinstance(revision, str) or REVISION.fullmatch(revision) is None:
            raise BuildError("evaluation source revision must be exact")
        normalized.append({"id": source_id, "repository": repository, "revision": revision})
    if len({row["id"] for row in normalized}) != len(normalized):
        raise BuildError("evaluation source ids must be unique")
    return sorted(normalized, key=lambda row: row["id"])


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("schema") != PLAN_SCHEMA:
        raise BuildError("unsupported Harmony case build plan schema")
    if plan.get("automaticPromotion") is not False:
        raise BuildError("Harmony case build plan must set automaticPromotion=false")

    case_binding = plan.get("evaluationCase") or {}
    case_path = require_file(case_binding.get("path"), "evaluation case")
    case_sha256 = sha256(case_path)
    if case_binding.get("sha256") != case_sha256:
        raise BuildError("evaluation case SHA256 differs from build plan")
    case = load_object(case_path)
    if case.get("schema") != "agentlab.multi_repo_evaluation_case.v1":
        raise BuildError("unsupported multi-repository evaluation case schema")
    if case.get("status") != "frozen-calibrated":
        raise BuildError("evaluation case is not frozen and calibrated")
    if case.get("automaticPromotion") is not False:
        raise BuildError("evaluation case must not claim automatic promotion")
    if (case.get("calibration") or {}).get("qualified") is not True:
        raise BuildError("evaluation case calibration is not qualified")
    if (case.get("oracle") or {}).get("authority") != "independent-executable-oracle":
        raise BuildError("evaluation case requires an independent executable Oracle")
    case_id = case.get("id")
    if not isinstance(case_id, str) or not case_id:
        raise BuildError("evaluation case id is required")
    source_set_sha256 = case.get("sourceSetSha256")
    if not isinstance(source_set_sha256, str) or SHA256.fullmatch(source_set_sha256) is None:
        raise BuildError("evaluation case sourceSetSha256 is invalid")
    sources = validate_sources(case.get("sources"))
    source_by_id = {row["id"]: row for row in sources}

    mappings = plan.get("sourceMaterialization")
    if not isinstance(mappings, list) or not mappings:
        raise BuildError("sourceMaterialization mappings are required")
    normalized_mappings = []
    mapped_ids = set()
    for index, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            raise BuildError("sourceMaterialization mapping must be an object")
        source_id = mapping.get("sourceId")
        if source_id not in source_by_id:
            raise BuildError(f"sourceMaterialization[{index}] references an unknown source")
        checkout = require_directory(mapping.get("checkout"), f"sourceMaterialization[{index}].checkout")
        if not (checkout / ".git").exists() and git(checkout, ["rev-parse", "--is-inside-work-tree"]) != "true":
            raise BuildError(f"sourceMaterialization[{index}] checkout is not a Git worktree")
        source = source_by_id[source_id]
        origin = git(checkout, ["remote", "get-url", "origin"])
        if origin != source["repository"]:
            raise BuildError(f"source {source_id} origin differs from frozen evaluation case")
        resolved_revision = git(checkout, ["rev-parse", f"{source['revision']}^{{commit}}"])
        if resolved_revision != source["revision"]:
            raise BuildError(f"source {source_id} revision is unavailable")
        source_path = safe_relative(mapping.get("sourcePath", "."), "sourcePath")
        target_path = safe_relative(mapping.get("targetPath", "."), "targetPath")
        tree_spec = f"{source['revision']}^{{tree}}" if str(source_path) == "." else f"{source['revision']}:{source_path.as_posix()}"
        if git(checkout, ["cat-file", "-t", tree_spec]) != "tree":
            raise BuildError(f"source {source_id} sourcePath is not a committed directory")
        normalized_mappings.append(
            {
                "sourceId": source_id,
                "checkout": checkout,
                "sourcePath": source_path,
                "targetPath": target_path,
                "revision": source["revision"],
                "repository": source["repository"],
                "gitTree": git(checkout, ["rev-parse", tree_spec]),
            }
        )
        mapped_ids.add(source_id)
    if mapped_ids != set(source_by_id):
        raise BuildError("every frozen evaluation source must be materialized")

    build = plan.get("build") or {}
    executable = require_file(build.get("executable"), "build executable", executable=True)
    executable_sha256 = sha256(executable)
    if build.get("executableSha256") != executable_sha256:
        raise BuildError("build executable SHA256 differs from build plan")
    arguments = build.get("arguments")
    if not isinstance(arguments, list) or not all(isinstance(value, str) and "\0" not in value for value in arguments):
        raise BuildError("build arguments must be a string list")
    working_directory = safe_relative(build.get("workingDirectory", "."), "build workingDirectory")
    artifact_path = safe_relative(build.get("artifactPath"), "build artifactPath", dot=False)
    timeout_seconds = build.get("timeoutSeconds", 900)
    if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 3600:
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
        "sourceSetSha256": source_set_sha256,
        "sources": sources,
        "mappings": normalized_mappings,
        "executable": executable,
        "executableSha256": executable_sha256,
        "arguments": arguments,
        "workingDirectory": working_directory,
        "artifactPath": artifact_path,
        "timeoutSeconds": timeout_seconds,
        "environment": environment,
    }


def materialize(validated: dict[str, Any], workspace: pathlib.Path) -> dict[str, Any]:
    files = []
    occupied = set()
    for mapping in validated["mappings"]:
        source_path = mapping["sourcePath"]
        pathspec = [] if str(source_path) == "." else [source_path.as_posix()]
        raw = git(
            mapping["checkout"],
            ["ls-tree", "-r", "-z", mapping["revision"], "--", *pathspec],
            binary=True,
        )
        entries = [entry for entry in raw.split(b"\0") if entry]
        if not entries:
            raise BuildError(f"source {mapping['sourceId']} materialization is empty")
        for entry in entries:
            metadata, raw_path = entry.split(b"\t", 1)
            mode, kind, _object_id = metadata.decode().split(" ")
            source_name = raw_path.decode("utf-8")
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise BuildError(f"unsupported Git entry {source_name}: {mode} {kind}")
            source_name_path = pathlib.PurePosixPath(source_name)
            relative = source_name_path if str(source_path) == "." else source_name_path.relative_to(source_path)
            target = mapping["targetPath"] / relative
            target_name = target.as_posix()
            if target_name in occupied:
                raise BuildError(f"source materialization target collision: {target_name}")
            occupied.add(target_name)
            destination = workspace / pathlib.Path(*target.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = git(
                mapping["checkout"],
                ["show", f"{mapping['revision']}:{source_name}"],
                binary=True,
            )
            destination.write_bytes(content)
            destination.chmod(0o755 if mode == "100755" else 0o644)
            files.append(
                {
                    "sourceId": mapping["sourceId"],
                    "sourcePath": source_name,
                    "targetPath": target_name,
                    "gitMode": mode,
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
    files.sort(key=lambda row: row["targetPath"])
    return {
        "schema": MATERIALIZATION_SCHEMA,
        "caseId": validated["caseId"],
        "evaluationCaseSha256": validated["caseSha256"],
        "sourceSetSha256": validated["sourceSetSha256"],
        "sources": validated["sources"],
        "mappings": [
            {
                "sourceId": row["sourceId"],
                "repository": row["repository"],
                "revision": row["revision"],
                "gitTree": row["gitTree"],
                "sourcePath": row["sourcePath"].as_posix(),
                "targetPath": row["targetPath"].as_posix(),
            }
            for row in validated["mappings"]
        ],
        "files": files,
        "fileCount": len(files),
        "byteCount": sum(row["bytes"] for row in files),
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
        plan = load_object(plan_path)
        validated = validate_plan(plan)
        materialization = materialize(validated, workspace)
        materialization_path = stage / "source-materialization.json"
        write_json(materialization_path, materialization)

        working_directory = workspace / pathlib.Path(*validated["workingDirectory"].parts)
        if not working_directory.is_dir():
            raise BuildError(f"build working directory was not materialized: {working_directory}")
        artifact_in_workspace = workspace / pathlib.Path(*validated["artifactPath"].parts)
        replacements = {
            "{workspace}": str(workspace),
            "{artifact}": str(artifact_in_workspace),
        }
        command = [str(validated["executable"])]
        for argument in validated["arguments"]:
            for marker, value in replacements.items():
                argument = argument.replace(marker, value)
            command.append(argument)
        command_binding = {
            "executableSha256": validated["executableSha256"],
            "arguments": validated["arguments"],
            "workingDirectory": validated["workingDirectory"].as_posix(),
            "artifactPath": validated["artifactPath"].as_posix(),
            "timeoutSeconds": validated["timeoutSeconds"],
            "environmentKeys": sorted(validated["environment"]),
            "environmentSha256": canonical_sha256(validated["environment"]),
        }
        exit_code, stdout, stderr, timed_out = run_build(
            command,
            working_directory,
            validated["environment"],
            validated["timeoutSeconds"],
        )
        stdout_path = stage / "build.stdout.log"
        stderr_path = stage / "build.stderr.log"
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        if timed_out:
            raise BuildError(f"Harmony build timed out after {validated['timeoutSeconds']} seconds")
        if exit_code != 0:
            raise BuildError(f"Harmony build failed with exit {exit_code}")
        if not artifact_in_workspace.is_file():
            raise BuildError("Harmony build did not produce the declared HAP artifact")
        if artifact_in_workspace.is_symlink():
            raise BuildError("Harmony build artifact must not be a symbolic link")
        artifact = stage / "artifact.hap"
        shutil.copyfile(artifact_in_workspace, artifact)
        hap_sha256 = sha256(artifact)

        if sha256(plan_path) != plan_sha256:
            raise BuildError("Harmony case build plan changed during execution")
        if sha256(validated["casePath"]) != validated["caseSha256"]:
            raise BuildError("frozen evaluation case changed during execution")
        if sha256(validated["executable"]) != validated["executableSha256"]:
            raise BuildError("build executable changed during execution")

        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": "passed",
            "caseId": validated["caseId"],
            "evaluationCaseSha256": validated["caseSha256"],
            "sourceSetSha256": validated["sourceSetSha256"],
            "sources": validated["sources"],
            "sourceMaterializationSha256": sha256(materialization_path),
            "sourceMaterializationContentSha256": canonical_sha256(materialization),
            "buildToolSha256": validated["executableSha256"],
            "buildCommandSha256": canonical_sha256(command_binding),
            "planSha256": plan_sha256,
            "hapSha256": hap_sha256,
            "hapBytes": artifact.stat().st_size,
            "buildExitCode": exit_code,
            "buildTimedOut": False,
            "buildStdoutSha256": sha256(stdout_path),
            "buildStderrSha256": sha256(stderr_path),
            "buildAuthority": "independent-harmony-build",
            "automaticPromotion": False,
        }
        write_json(stage / "build-receipt.json", receipt)
        shutil.rmtree(workspace)
        stage.rename(output)
        print(
            json.dumps(
                {
                    "ok": True,
                    "output": str(output),
                    "caseId": validated["caseId"],
                    "fileCount": materialization["fileCount"],
                    "hapSha256": hap_sha256,
                    "hapBytes": receipt["hapBytes"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (BuildError, OSError) as error:
        write_json(
            stage / "failure.json",
            {
                "schema": RECEIPT_SCHEMA,
                "status": "failed",
                "error": str(error),
                "automaticPromotion": False,
            },
        )
        print(
            json.dumps({"ok": False, "retained": str(stage), "error": str(error)}, sort_keys=True),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
