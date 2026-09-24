#!/usr/bin/env python3
"""Prepare and resolve a relocation-safe Harmony assessed campaign handoff."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any


HANDOFF_SCHEMA = "agentlab.harmony_assessed_campaign_handoff.v1"
HOST_PROFILE_SCHEMA = "agentlab.harmony_assessed_host_profile.v1"
PLAN_SCHEMA = "agentlab.harmony_assessed_campaign_plan.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[A-Za-z0-9_.:-]+")


class HandoffError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HandoffError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HandoffError(f"cannot load {label} {path}: {error}") from error
    require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def write_new(path: Path, value: dict[str, Any]) -> None:
    require(not path.exists(), f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


def require_digest(value: Any, label: str) -> str:
    require(isinstance(value, str) and SHA256.fullmatch(value) is not None, f"{label} must be an exact SHA256")
    return value


def require_token(value: Any, label: str) -> str:
    require(isinstance(value, str) and TOKEN.fullmatch(value) is not None, f"{label} must be a safe token")
    return value


def safe_relative(value: Any, label: str) -> PurePosixPath:
    require(isinstance(value, str) and value, f"{label} path is required")
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts, f"{label} must be a safe relative path")
    require(path.as_posix() not in {"", "."}, f"{label} must name an entry")
    return path


def resolve_relative(root: Path, value: Any, label: str) -> Path:
    relative = safe_relative(value, label)
    path = root.joinpath(*relative.parts)
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        require(not cursor.is_symlink(), f"{label} must not traverse a symlink")
    resolved_root = root.resolve()
    resolved = path.resolve()
    require(resolved == resolved_root or resolved_root in resolved.parents, f"{label} escapes its root")
    return resolved


def relative_name(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved = path.resolve()
    require(resolved_root in resolved.parents, f"{path} is outside handoff root")
    return resolved.relative_to(resolved_root).as_posix()


def portable_file(root: Path, path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} is not a regular file")
    return {
        "path": relative_name(root, path),
        "sha256": sha256(path),
        "byteLength": path.stat().st_size,
    }


def verify_portable_file(root: Path, value: Any, label: str) -> Path:
    require(isinstance(value, dict), f"{label} binding is required")
    path = resolve_relative(root, value.get("path"), label)
    require(path.is_file() and not path.is_symlink(), f"{label} is not a regular file")
    require(path.stat().st_size == value.get("byteLength"), f"{label} byte length differs from handoff")
    require(sha256(path) == require_digest(value.get("sha256"), f"{label} sha256"), f"{label} SHA256 differs from handoff")
    return path


def tree_state(root: Path) -> dict[str, dict[str, Any]]:
    require(root.is_dir() and not root.is_symlink(), f"workspace is not a regular directory: {root}")
    rows: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), f"workspace contains symlink: {path}")
        if path.is_dir():
            continue
        require(path.is_file(), f"workspace contains unsupported entry: {path}")
        rows[path.relative_to(root).as_posix()] = {
            "sha256": sha256(path),
            "byteLength": path.stat().st_size,
            "unixMode": stat.S_IMODE(path.stat().st_mode),
        }
    require(rows, f"workspace has no files: {root}")
    return rows


def validate_static_assessment(
    root: Path,
    evidence_path: Any,
    attempt: dict[str, Any],
    case_id: str,
    source_set: str,
) -> dict[str, Any]:
    attempt_id = require_token(attempt.get("attemptId"), "attemptId")
    participant_id = require_token(attempt.get("participantId"), f"{attempt_id} participantId")
    assessment = resolve_relative(root, evidence_path, f"{attempt_id} evidence")
    require(assessment.is_dir() and not assessment.is_symlink(), f"{attempt_id} evidence is not a directory")
    summary_path = assessment / "summary.json"
    decision_path = assessment / "decision-package.json"
    state_path = assessment / "final-source-state.json"
    workspace = assessment / "workspace"
    summary = load(summary_path, f"{attempt_id} summary")
    decision = load(decision_path, f"{attempt_id} decision")
    final_state = load(state_path, f"{attempt_id} final source state")
    common = {"taskId": case_id, "sourceSetSha256": source_set, "participantId": participant_id}
    require(summary.get("schema") == "agentlab.multi_repo_assessment_summary.v1", f"{attempt_id} summary schema is unsupported")
    require(decision.get("schema") == "agentlab.harness_decision_package.v1", f"{attempt_id} decision schema is unsupported")
    require(all(summary.get(key) == value and decision.get(key) == value for key, value in common.items()), f"{attempt_id} static identity differs")
    require(decision.get("automaticPromotion") is False, f"{attempt_id} decision must not auto-promote")
    actual_state = tree_state(workspace)
    require(actual_state == final_state, f"{attempt_id} workspace differs from final source state")
    tree_sha = canonical_sha256(actual_state)
    require(summary.get("finalWorkspaceSha256") == tree_sha, f"{attempt_id} workspace digest differs from summary")
    return {
        "attemptId": attempt_id,
        "participantId": participant_id,
        "producerRun": attempt.get("producerRun"),
        "assessment": {
            "path": relative_name(root, assessment),
            "summary": portable_file(root, summary_path, f"{attempt_id} summary"),
            "decisionPackage": portable_file(root, decision_path, f"{attempt_id} decision package"),
            "finalSourceState": portable_file(root, state_path, f"{attempt_id} final source state"),
            "workspace": {
                "path": relative_name(root, workspace),
                "treeSha256": tree_sha,
                "fileCount": len(actual_state),
            },
        },
    }


def prepare(root: Path, output: Path, campaign_id: str | None = None) -> dict[str, Any]:
    require(not root.is_symlink(), "campaign artifact root must not be a symlink")
    root = root.resolve()
    require(root.is_dir(), "campaign artifact root is invalid")
    require(output.resolve().parent == root, "handoff output must be written directly inside campaign artifact root")
    case_path = root / "multi-repo-evaluation-case.json"
    calibration_path = root / "multi-repo-calibration.json"
    collection_path = root / "attempts.json"
    case = load(case_path, "evaluation case")
    calibration = load(calibration_path, "calibration")
    collection = load(collection_path, "attempt collection")
    require(case.get("schema") == "agentlab.multi_repo_evaluation_case.v1", "unsupported evaluation case schema")
    require(case.get("status") == "frozen-calibrated" and case.get("automaticPromotion") is False, "case is not frozen calibrated and non-promoted")
    require((case.get("calibration") or {}).get("qualified") is True, "case calibration is not qualified")
    case_id = require_token(case.get("id"), "case id")
    source_set = require_digest(case.get("sourceSetSha256"), "case sourceSetSha256")
    require(calibration.get("schema") == "agentlab.multi_repo_calibration.v1", "unsupported calibration schema")
    require(calibration.get("sourceSetSha256") == source_set, "calibration source set differs")
    require(collection.get("schema") == "agentlab.case_attempt_collection.v2", "unsupported attempt collection schema")
    require(collection.get("sourceSetSha256") == source_set, "attempt collection source set differs")
    method_revision = collection.get("methodRevision")
    require(isinstance(method_revision, str) and REVISION.fullmatch(method_revision) is not None, "methodRevision must be exact")
    cases = collection.get("cases")
    require(isinstance(cases, list) and len(cases) == 1 and cases[0].get("id") == case_id, "attempt collection must contain exactly the handoff case")
    case_attempts = cases[0]
    calibration_relative = safe_relative(case_attempts.get("calibration"), "attempt calibration")
    original_calibration = resolve_relative(root, calibration_relative.as_posix(), "attempt calibration")
    require(sha256(original_calibration) == sha256(calibration_path), "stable calibration copy differs from attempt calibration")
    attempts_raw = case_attempts.get("attempts")
    require(isinstance(attempts_raw, list) and len(attempts_raw) >= 2, "handoff requires at least two attempts")
    attempts = [
        validate_static_assessment(root, row.get("evidence"), row, case_id, source_set)
        for row in attempts_raw
        if isinstance(row, dict)
    ]
    require(len(attempts) == len(attempts_raw), "attempt entries must be objects")
    require(len({row["attemptId"] for row in attempts}) == len(attempts), "attemptId values must be unique")
    require(len({row["participantId"] for row in attempts}) >= 2, "handoff requires at least two participant profiles")
    producer_runs = {str(row["producerRun"]) for row in attempts if row.get("producerRun") is not None}
    inferred = f"{case_id}-run-{next(iter(producer_runs))}" if len(producer_runs) == 1 else f"{case_id}-{method_revision[:12]}"
    selected_campaign_id = require_token(campaign_id or inferred, "campaignId")
    value = {
        "schema": HANDOFF_SCHEMA,
        "campaignId": selected_campaign_id,
        "caseId": case_id,
        "sourceSetSha256": source_set,
        "methodRevision": method_revision,
        "evaluationCase": portable_file(root, case_path, "evaluation case"),
        "calibration": portable_file(root, calibration_path, "calibration"),
        "attemptCollection": portable_file(root, collection_path, "attempt collection"),
        "attempts": attempts,
        "automaticPromotion": False,
        "nextGate": "resolve-on-qualified-harmony-host",
    }
    write_new(output, value)
    return value


def host_path(host_root: Path, value: Any, label: str, *, directory: bool = False, executable: bool = False) -> Path:
    path = resolve_relative(host_root, value, label)
    require(path.is_dir() if directory else path.is_file(), f"{label} is absent or has the wrong type")
    if executable:
        require(os.access(path, os.X_OK), f"{label} is not executable")
    return path


def host_file(host_root: Path, value: Any, label: str, *, executable: bool = False) -> Path:
    require(isinstance(value, dict), f"{label} binding is required")
    path = host_path(host_root, value.get("path"), label, executable=executable)
    require(sha256(path) == require_digest(value.get("sha256"), f"{label} sha256"), f"{label} SHA256 differs from host profile")
    return path


def normalize_execution_preflight(value: Any, *, required: bool) -> dict[str, Any] | None:
    if value is None:
        require(not required, "KVM host profile requires executionPreflight")
        return None
    require(isinstance(value, dict), "executionPreflight must be an object")
    groups = value.get("requiredGroups")
    devices = value.get("requiredDevices")
    require(
        isinstance(groups, list)
        and bool(groups)
        and all(isinstance(name, str) and name for name in groups),
        "executionPreflight requiredGroups must be non-empty strings",
    )
    require(isinstance(devices, list) and bool(devices), "executionPreflight requiredDevices must be non-empty")
    for index, row in enumerate(devices):
        require(isinstance(row, dict), f"executionPreflight device {index} must be an object")
        path = row.get("path")
        require(isinstance(path, str) and Path(path).is_absolute(), f"executionPreflight device {index} path must be absolute")
        require(row.get("read") is True and row.get("write") is True, f"executionPreflight device {index} must require read and write access")
    return {"requiredGroups": groups, "requiredDevices": devices}


def verify_handoff(handoff_path: Path) -> tuple[dict[str, Any], Path, list[dict[str, Any]]]:
    handoff = load(handoff_path, "campaign handoff")
    require(handoff.get("schema") == HANDOFF_SCHEMA, "unsupported campaign handoff schema")
    require(handoff.get("automaticPromotion") is False, "handoff must not auto-promote")
    root = handoff_path.resolve().parent
    case_path = verify_portable_file(root, handoff.get("evaluationCase"), "evaluation case")
    calibration_path = verify_portable_file(root, handoff.get("calibration"), "calibration")
    verify_portable_file(root, handoff.get("attemptCollection"), "attempt collection")
    case = load(case_path, "evaluation case")
    case_id = require_token(handoff.get("caseId"), "caseId")
    source_set = require_digest(handoff.get("sourceSetSha256"), "sourceSetSha256")
    require(case.get("id") == case_id and case.get("sourceSetSha256") == source_set, "handoff case identity differs from evaluation case")
    require(isinstance(handoff.get("methodRevision"), str) and REVISION.fullmatch(handoff["methodRevision"]) is not None, "handoff methodRevision is invalid")
    attempts_raw = handoff.get("attempts")
    require(isinstance(attempts_raw, list) and len(attempts_raw) >= 2, "handoff requires at least two attempts")
    attempts: list[dict[str, Any]] = []
    for row in attempts_raw:
        require(isinstance(row, dict), "handoff attempt must be an object")
        attempt_id = require_token(row.get("attemptId"), "attemptId")
        participant_id = require_token(row.get("participantId"), f"{attempt_id} participantId")
        assessment = row.get("assessment")
        require(isinstance(assessment, dict), f"{attempt_id} assessment binding is required")
        assessment_root = resolve_relative(root, assessment.get("path"), f"{attempt_id} assessment")
        require(assessment_root.is_dir() and not assessment_root.is_symlink(), f"{attempt_id} assessment is absent")
        summary = verify_portable_file(root, assessment.get("summary"), f"{attempt_id} summary")
        decision = verify_portable_file(root, assessment.get("decisionPackage"), f"{attempt_id} decision package")
        state_path = verify_portable_file(root, assessment.get("finalSourceState"), f"{attempt_id} final source state")
        workspace_binding = assessment.get("workspace")
        require(isinstance(workspace_binding, dict), f"{attempt_id} workspace binding is required")
        workspace = resolve_relative(root, workspace_binding.get("path"), f"{attempt_id} workspace")
        require(summary == assessment_root / "summary.json", f"{attempt_id} summary path differs from assessment layout")
        require(decision == assessment_root / "decision-package.json", f"{attempt_id} decision path differs from assessment layout")
        require(state_path == assessment_root / "final-source-state.json", f"{attempt_id} final source state path differs from assessment layout")
        require(workspace == assessment_root / "workspace", f"{attempt_id} workspace path differs from assessment layout")
        actual_state = tree_state(workspace)
        require(len(actual_state) == workspace_binding.get("fileCount"), f"{attempt_id} workspace file count differs from handoff")
        require(canonical_sha256(actual_state) == require_digest(workspace_binding.get("treeSha256"), f"{attempt_id} workspace treeSha256"), f"{attempt_id} workspace tree differs from handoff")
        require(load(state_path, f"{attempt_id} final source state") == actual_state, f"{attempt_id} workspace differs from final source state")
        summary_value = load(summary, f"{attempt_id} summary")
        decision_value = load(decision, f"{attempt_id} decision")
        common = {"taskId": case_id, "sourceSetSha256": source_set, "participantId": participant_id}
        require(all(summary_value.get(key) == value and decision_value.get(key) == value for key, value in common.items()), f"{attempt_id} static identity differs from handoff")
        attempts.append({
            "attemptId": attempt_id,
            "participantId": participant_id,
            "producerRun": row.get("producerRun"),
            "assessment": {
                "path": str(assessment_root),
                "summarySha256": sha256(summary),
                "decisionPackageSha256": sha256(decision),
                "finalSourceStateSha256": sha256(state_path),
            },
        })
    require(len({row["attemptId"] for row in attempts}) == len(attempts), "handoff attemptId values must be unique")
    require(len({row["participantId"] for row in attempts}) >= 2, "handoff requires at least two participant profiles")
    return handoff, calibration_path, attempts


def resolve(handoff_path: Path, profile_path: Path, host_root: Path, output: Path) -> dict[str, Any]:
    handoff, calibration_path, attempts = verify_handoff(handoff_path)
    profile = load(profile_path, "host profile")
    require(profile.get("schema") == HOST_PROFILE_SCHEMA, "unsupported host profile schema")
    require(profile.get("automaticPromotion") is False, "host profile must not auto-promote")
    require_token(profile.get("profileId"), "profileId")
    require(not host_root.is_symlink(), "host root must not be a symlink")
    host_root = host_root.resolve()
    require(host_root.is_dir(), "host root is invalid")
    programs_raw = profile.get("programs")
    require(isinstance(programs_raw, dict), "host program bindings are required")
    program_modes = {"build": True, "loop": True, "run": True, "compose": True, "collect": False, "score": False, "feedback": False}
    programs = {}
    for name, executable in program_modes.items():
        path = host_file(host_root, programs_raw.get(name), f"{name} program", executable=executable)
        programs[name] = {"path": str(path), "sha256": sha256(path)}
    build_raw = profile.get("build")
    require(isinstance(build_raw, dict), "host build configuration is required")
    require("executableSha256" not in build_raw, "build executableSha256 is derived from its binding")
    executable = host_file(host_root, build_raw.get("executable"), "build executable", executable=True)
    build = {key: value for key, value in build_raw.items() if key != "executable"}
    build["executable"] = str(executable)
    build["executableSha256"] = sha256(executable)
    device_raw = profile.get("device")
    require(isinstance(device_raw, dict), "host device configuration is required")
    functional_raw = device_raw.get("functionalOracle")
    runtime_raw = device_raw.get("runtime")
    performance_raw = device_raw.get("performance")
    require(isinstance(functional_raw, dict) and isinstance(runtime_raw, dict) and isinstance(performance_raw, dict), "host device bindings are incomplete")
    require("runnerSha256" not in runtime_raw, "runtime runnerSha256 is derived from its binding")
    require(not {"policySha256", "workloadSha256"}.intersection(performance_raw), "performance digests are derived from their bindings")
    oracle = host_file(host_root, functional_raw, "functional Oracle")
    runner_binding = runtime_raw.get("runner")
    runner = host_file(host_root, runner_binding, "runtime runner", executable=True)
    policy = host_file(host_root, performance_raw.get("policy"), "performance policy")
    workload = host_file(host_root, performance_raw.get("workload"), "profile workload")
    runtime = {key: value for key, value in runtime_raw.items() if key not in {"runner", "toolsRoot", "imageRoot", "instancePath"}}
    runtime.update({
        "runner": str(runner),
        "runnerSha256": sha256(runner),
        "toolsRoot": str(host_path(host_root, runtime_raw.get("toolsRoot"), "tools root", directory=True)),
        "imageRoot": str(host_path(host_root, runtime_raw.get("imageRoot"), "image root", directory=True)),
        "instancePath": str(host_path(host_root, runtime_raw.get("instancePath"), "instance path", directory=True)),
    })
    functional = {key: value for key, value in functional_raw.items() if key not in {"path", "sha256"}}
    functional.update({"path": str(oracle), "sha256": sha256(oracle)})
    performance = {"policy": str(policy), "policySha256": sha256(policy), "workload": str(workload), "workloadSha256": sha256(workload)}
    device = {key: value for key, value in device_raw.items() if key not in {"functionalOracle", "runtime", "performance"}}
    device.update({"functionalOracle": functional, "runtime": runtime, "performance": performance})
    environment_identity = runtime.get("environmentIdentity")
    execution_preflight = normalize_execution_preflight(
        profile.get("executionPreflight"),
        required=isinstance(environment_identity, str)
        and "kvm" in environment_identity.split(":"),
    )
    evaluation_case = verify_portable_file(handoff_path.resolve().parent, handoff.get("evaluationCase"), "evaluation case")
    value = {
        "schema": PLAN_SCHEMA,
        "campaignId": require_token(handoff.get("campaignId"), "campaignId"),
        "evaluationCase": {"path": str(evaluation_case), "sha256": sha256(evaluation_case)},
        "calibration": {"path": str(calibration_path), "sha256": sha256(calibration_path)},
        "methodRevision": handoff["methodRevision"],
        "attempts": attempts,
        "sourceMaterialization": profile.get("sourceMaterialization"),
        "build": build,
        "device": device,
        "programs": programs,
        "executionPreflight": execution_preflight,
        "requiredTrials": profile.get("requiredTrials", 3),
        "eligibilityThreshold": profile.get("eligibilityThreshold", 0.6),
        "automaticPromotion": False,
    }
    write_new(output, value)
    return value
