#!/usr/bin/env python3
"""Resume a trusted assessed campaign through Harmony device and feedback gates."""
from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


PLAN_SCHEMA = "agentlab.harmony_assessed_campaign_plan.v1"
STATE_SCHEMA = "agentlab.harmony_assessed_campaign_state.v1"
SUMMARY_SCHEMA = "agentlab.harmony_assessed_campaign_summary.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[A-Za-z0-9_.:-]+")


class CampaignError(RuntimeError):
    pass


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: pathlib.Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CampaignError(f"cannot load {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise CampaignError(f"{label} must be a JSON object")
    return value


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_or_verify(path: pathlib.Path, value: dict[str, Any], label: str) -> None:
    if path.exists():
        if load(path, label) != value:
            raise CampaignError(f"existing {label} differs from the exact campaign plan")
        return
    write_json(path, value)


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise CampaignError(f"{label} must be an exact SHA256")
    return value


def require_token(value: Any, label: str) -> str:
    if not isinstance(value, str) or TOKEN.fullmatch(value) is None:
        raise CampaignError(f"{label} must be a non-empty safe token")
    return value


def calibration_authoring_from_case(case: dict[str, Any]) -> dict[str, str] | None:
    executable = (case.get("calibration") or {}).get("executableBundle") or {}
    value = executable.get("calibrationAuthoring")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CampaignError("case calibration authoring lineage must be an object")
    for field in ("receiptSha256", "draftManifestSha256", "participantSha256"):
        require_digest(value.get(field), f"case calibration authoring {field}")
    participant_id = require_token(value.get("participantId"), "case calibration authoring participantId")
    method_revision = value.get("methodRevision")
    if not isinstance(method_revision, str) or REVISION.fullmatch(method_revision) is None:
        raise CampaignError("case calibration authoring methodRevision must be exact")
    return {
        "receiptSha256": value["receiptSha256"],
        "draftManifestSha256": value["draftManifestSha256"],
        "participantId": participant_id,
        "participantSha256": value["participantSha256"],
        "methodRevision": method_revision,
    }


def bound_file(binding: Any, label: str, *, executable: bool = False) -> pathlib.Path:
    if not isinstance(binding, dict):
        raise CampaignError(f"{label} binding is required")
    raw = binding.get("path")
    if not isinstance(raw, str) or not raw:
        raise CampaignError(f"{label} path is required")
    path = pathlib.Path(raw).resolve()
    if not path.is_file() or path.is_symlink():
        raise CampaignError(f"{label} is not a regular file: {path}")
    if executable and not os.access(path, os.X_OK):
        raise CampaignError(f"{label} is not executable: {path}")
    if sha256(path) != require_digest(binding.get("sha256"), f"{label} sha256"):
        raise CampaignError(f"{label} SHA256 differs from campaign plan")
    return path


def require_directory(value: Any, label: str) -> pathlib.Path:
    if not isinstance(value, str) or not value:
        raise CampaignError(f"{label} path is required")
    path = pathlib.Path(value).resolve()
    if not path.is_dir() or path.is_symlink():
        raise CampaignError(f"{label} is not a regular directory: {path}")
    return path


def validate_execution_preflight(
    plan: dict[str, Any], device: dict[str, Any]
) -> dict[str, Any] | None:
    runtime = device.get("runtime")
    environment_identity = (
        runtime.get("environmentIdentity") if isinstance(runtime, dict) else None
    )
    preflight = plan.get("executionPreflight")
    kvm_environment = isinstance(environment_identity, str) and "kvm" in environment_identity.split(":")
    if preflight is None:
        if kvm_environment:
            raise CampaignError("KVM campaign requires executionPreflight")
        return None
    if not isinstance(preflight, dict):
        raise CampaignError("executionPreflight must be an object")
    groups = preflight.get("requiredGroups")
    devices = preflight.get("requiredDevices")
    if not isinstance(groups, list) or not groups or not all(
        isinstance(name, str) and name for name in groups
    ):
        raise CampaignError("executionPreflight requiredGroups must be non-empty strings")
    if not isinstance(devices, list) or not devices:
        raise CampaignError("executionPreflight requiredDevices must be non-empty")
    active_groups = set(os.getgroups()) | {os.getegid()}
    for name in groups:
        try:
            group_id = grp.getgrnam(name).gr_gid
        except KeyError as error:
            raise CampaignError(f"required execution group is absent: {name}") from error
        if group_id not in active_groups:
            raise CampaignError(
                f"current execution identity has not activated required group: {name}"
            )
    normalized_devices = []
    for index, row in enumerate(devices):
        if not isinstance(row, dict):
            raise CampaignError(f"executionPreflight device {index} must be an object")
        raw_path = row.get("path")
        if not isinstance(raw_path, str) or not pathlib.Path(raw_path).is_absolute():
            raise CampaignError(
                f"executionPreflight device {index} path must be absolute"
            )
        if row.get("read") is not True or row.get("write") is not True:
            raise CampaignError(
                f"executionPreflight device {index} must require read and write access"
            )
        path = pathlib.Path(raw_path)
        if not path.exists() or path.is_symlink():
            raise CampaignError(f"required execution device is absent or unsafe: {path}")
        if not os.access(path, os.R_OK) or not os.access(path, os.W_OK):
            raise CampaignError(
                f"current execution identity cannot read and write required device: {path}"
            )
        normalized_devices.append({"path": str(path), "read": True, "write": True})
    return {"requiredGroups": groups, "requiredDevices": normalized_devices}


def binding(path: pathlib.Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256(path)}


def validate_assessment(
    row: dict[str, Any], case_id: str, source_set: str
) -> dict[str, Any]:
    attempt_id = require_token(row.get("attemptId"), "attemptId")
    participant_id = require_token(row.get("participantId"), f"{attempt_id} participantId")
    assessment = row.get("assessment")
    if not isinstance(assessment, dict):
        raise CampaignError(f"{attempt_id} assessment binding is required")
    root = require_directory(assessment.get("path"), f"{attempt_id} assessment")
    summary_path = root / "summary.json"
    decision_path = root / "decision-package.json"
    state_path = root / "final-source-state.json"
    workspace = root / "workspace"
    for path, field, label in (
        (summary_path, "summarySha256", "summary"),
        (decision_path, "decisionPackageSha256", "decision package"),
        (state_path, "finalSourceStateSha256", "final source state"),
    ):
        if not path.is_file() or path.is_symlink():
            raise CampaignError(f"{attempt_id} {label} is not a regular file")
        if sha256(path) != require_digest(
            assessment.get(field), f"{attempt_id} {label} sha256"
        ):
            raise CampaignError(f"{attempt_id} {label} differs from campaign plan")
    if not workspace.is_dir() or workspace.is_symlink():
        raise CampaignError(f"{attempt_id} assessment workspace is absent")
    summary = load(summary_path, f"{attempt_id} static summary")
    decision = load(decision_path, f"{attempt_id} static decision")
    common = {
        "taskId": case_id,
        "sourceSetSha256": source_set,
        "participantId": participant_id,
    }
    if summary.get("schema") != "agentlab.multi_repo_assessment_summary.v1":
        raise CampaignError(f"{attempt_id} has unsupported static summary schema")
    if decision.get("schema") != "agentlab.harness_decision_package.v1":
        raise CampaignError(f"{attempt_id} has unsupported static decision schema")
    if any(summary.get(key) != value or decision.get(key) != value for key, value in common.items()):
        raise CampaignError(f"{attempt_id} static identity differs from campaign plan")
    if decision.get("automaticPromotion") is not False:
        raise CampaignError(f"{attempt_id} static decision must not auto-promote")
    infrastructure = (
        decision.get("assessmentStatus") == "assessed"
        and decision.get("infrastructureAvailable") is True
    )
    verdict = decision.get("subjectTaskSucceeded")
    if infrastructure and not isinstance(verdict, bool):
        raise CampaignError(f"{attempt_id} assessed static decision requires boolean verdict")
    return {
        "attemptId": attempt_id,
        "participantId": participant_id,
        "producerRun": row.get("producerRun"),
        "root": root,
        "summaryPath": summary_path,
        "decisionPath": decision_path,
        "statePath": state_path,
        "workspace": workspace,
        "staticInfrastructureValid": infrastructure,
        "staticVerdict": verdict if infrastructure else None,
    }


def validate_plan(plan_path: pathlib.Path) -> dict[str, Any]:
    plan = load(plan_path, "campaign plan")
    if plan.get("schema") != PLAN_SCHEMA:
        raise CampaignError("unsupported Harmony assessed campaign plan schema")
    if plan.get("automaticPromotion") is not False:
        raise CampaignError("Harmony assessed campaign must set automaticPromotion=false")
    campaign_id = require_token(plan.get("campaignId"), "campaignId")
    case_path = bound_file(plan.get("evaluationCase"), "evaluation case")
    case = load(case_path, "evaluation case")
    if (
        case.get("schema") != "agentlab.multi_repo_evaluation_case.v1"
        or case.get("status") != "frozen-calibrated"
        or case.get("automaticPromotion") is not False
        or (case.get("calibration") or {}).get("qualified") is not True
    ):
        raise CampaignError("campaign requires a frozen calibrated non-promoted case")
    case_id = require_token(case.get("id"), "case id")
    source_set = require_digest(case.get("sourceSetSha256"), "case sourceSetSha256")
    calibration_authoring = calibration_authoring_from_case(case)
    if plan.get("calibrationAuthoring") != calibration_authoring:
        raise CampaignError("campaign calibration authoring lineage differs from frozen case")
    calibration_path = bound_file(plan.get("calibration"), "calibration")
    method_revision = plan.get("methodRevision")
    if not isinstance(method_revision, str) or REVISION.fullmatch(method_revision) is None:
        raise CampaignError("methodRevision must be an exact Git revision")
    attempts_raw = plan.get("attempts")
    if not isinstance(attempts_raw, list) or len(attempts_raw) < 2:
        raise CampaignError("campaign requires at least two attempts")
    attempts = [validate_assessment(row, case_id, source_set) for row in attempts_raw]
    ids = [row["attemptId"] for row in attempts]
    if len(set(ids)) != len(ids):
        raise CampaignError("campaign attemptId values must be unique")
    if len({row["participantId"] for row in attempts}) < 2:
        raise CampaignError("campaign requires at least two participant profiles")
    required_trials = plan.get("requiredTrials", 3)
    threshold = plan.get("eligibilityThreshold", 0.6)
    if not isinstance(required_trials, int) or required_trials < 1:
        raise CampaignError("requiredTrials must be positive")
    if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        raise CampaignError("eligibilityThreshold must be in 0..1")
    experiment_plan_path = None
    experiment_plan = None
    experiment_binding = plan.get("participantExperimentPlan")
    if experiment_binding is not None:
        experiment_plan_path = bound_file(
            experiment_binding, "participant experiment plan"
        )
        experiment_plan = load(experiment_plan_path, "participant experiment plan")
        if (
            experiment_plan.get("schema")
            != "agentlab.participant_experiment_plan.v1"
            or experiment_plan.get("status") != "predeclared-before-attempts"
            or experiment_plan.get("automaticPromotion") is not False
            or experiment_plan.get("caseId") != case_id
            or experiment_plan.get("sourceSetSha256") != source_set
            or experiment_plan.get("methodRevision") != method_revision
        ):
            raise CampaignError("participant experiment plan identity differs")
        profiles = experiment_plan.get("participantProfiles")
        if (
            not isinstance(profiles, list)
            or len(profiles) < 2
            or experiment_plan.get("participantProfileCount") != len(profiles)
            or experiment_plan.get("trialsPerParticipant") != required_trials
        ):
            raise CampaignError("participant experiment plan denominators differ")
        profile_index = {
            row.get("participantId"): row
            for row in profiles
            if isinstance(row, dict)
        }
        if len(profile_index) != len(profiles) or any(
            row.get("ordinal") != ordinal
            for ordinal, row in enumerate(profiles)
        ):
            raise CampaignError("participant experiment profile order differs")
        attempt_counts = {
            participant_id: sum(
                attempt["participantId"] == participant_id for attempt in attempts
            )
            for participant_id in profile_index
        }
        if (
            set(attempt["participantId"] for attempt in attempts) != set(profile_index)
            or any(count != required_trials for count in attempt_counts.values())
        ):
            raise CampaignError("campaign attempts differ from participant experiment plan")
        if len({str(attempt["root"]) for attempt in attempts}) != len(attempts):
            raise CampaignError("predeclared attempts must bind distinct assessment roots")
        if (
            len({str(attempt.get("producerRun")) for attempt in attempts}) != 1
            or any(
                not str(attempt.get("producerRun")).isdigit()
                or int(str(attempt.get("producerRun"))) < 1
                for attempt in attempts
            )
        ):
            raise CampaignError("predeclared attempts require one positive producerRun")
        experiment_sha256 = sha256(experiment_plan_path)
        for attempt in attempts:
            summary = load(attempt["summaryPath"], f"{attempt['attemptId']} static summary")
            decision = load(attempt["decisionPath"], f"{attempt['attemptId']} static decision")
            evidence = summary.get("participantExperiment")
            profile = profile_index[attempt["participantId"]]
            if (
                not isinstance(evidence, dict)
                or decision.get("participantExperiment") != evidence
                or evidence.get("planSha256") != experiment_sha256
                or evidence.get("participantId") != attempt["participantId"]
                or evidence.get("participantOrdinal") != profile.get("ordinal")
                or evidence.get("model") != profile.get("model")
                or evidence.get("providerRoute") != experiment_plan.get("providerRoute")
                or evidence.get("executionProtocol")
                != experiment_plan.get("executionProtocol")
                or not isinstance(evidence.get("nativeParticipantEvidence"), dict)
                or evidence["nativeParticipantEvidence"].get("identityQualified")
                is not True
            ):
                raise CampaignError(
                    f"{attempt['attemptId']} participant experiment evidence differs"
                )
    programs_raw = plan.get("programs")
    if not isinstance(programs_raw, dict):
        raise CampaignError("program bindings are required")
    program_names = {
        "build": True,
        "standardTest": True,
        "loop": True,
        "run": True,
        "compose": True,
        "collect": False,
        "score": False,
        "feedback": False,
    }
    programs = {
        name: bound_file(programs_raw.get(name), f"{name} program", executable=executable)
        for name, executable in program_names.items()
    }
    device = plan.get("device")
    if not isinstance(device, dict):
        raise CampaignError("device run template fields are required")
    reserved_device_fields = {
        "schema",
        "evaluationCase",
        "runId",
        "buildReceipt",
        "artifact",
        "automaticPromotion",
    }
    if reserved_device_fields.intersection(device):
        raise CampaignError("device fields must not override campaign-generated bindings")
    if device.get("subjectOutcomePolicy") != "retain-assessed-failure":
        raise CampaignError("campaign device policy must retain assessed failures")
    runtime = device.get("runtime")
    emulator_fields = (
        "toolsRoot", "imageRoot", "instancePath", "instance", "hdcPort", "bootMode"
    )
    if not isinstance(runtime, dict) or any(key not in runtime for key in emulator_fields):
        raise CampaignError("device runtime must define the standard-test emulator lifecycle")
    execution_preflight = validate_execution_preflight(plan, device)
    standard_test = plan.get("standardTest")
    if not isinstance(standard_test, dict):
        raise CampaignError("standardTest configuration is required")
    source_executor = bound_file(
        standard_test.get("sourceExecutor"),
        "source standard-test executor",
        executable=True,
    )
    standard_configuration = standard_test.get("configuration")
    if not isinstance(standard_configuration, dict):
        raise CampaignError("standardTest.configuration is required")
    mappings = plan.get("sourceMaterialization")
    build = plan.get("build")
    if not isinstance(mappings, list) or not mappings or not isinstance(build, dict):
        raise CampaignError("sourceMaterialization and build configuration are required")
    return {
        "plan": plan,
        "planSha256": sha256(plan_path),
        "campaignId": campaign_id,
        "casePath": case_path,
        "caseSha256": sha256(case_path),
        "caseId": case_id,
        "sourceSetSha256": source_set,
        "calibrationPath": calibration_path,
        "calibrationAuthoring": calibration_authoring,
        "methodRevision": method_revision,
        "attempts": attempts,
        "requiredTrials": required_trials,
        "threshold": float(threshold),
        "experimentPlanPath": experiment_plan_path,
        "experimentPlan": experiment_plan,
        "programs": programs,
        "device": device,
        "sourceStandardTestExecutor": source_executor,
        "standardTestConfiguration": standard_configuration,
        "mappings": mappings,
        "build": build,
        "executionPreflight": execution_preflight,
    }


def initial_state(validated: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "status": "running",
        "campaignId": validated["campaignId"],
        "planSha256": validated["planSha256"],
        "caseId": validated["caseId"],
        "sourceSetSha256": validated["sourceSetSha256"],
        "attempts": {
            row["attemptId"]: {"status": "pending", "participantId": row["participantId"]}
            for row in validated["attempts"]
        },
        "automaticPromotion": False,
    }


def validate_state(state: dict[str, Any], validated: dict[str, Any]) -> None:
    expected = {
        "schema": STATE_SCHEMA,
        "campaignId": validated["campaignId"],
        "planSha256": validated["planSha256"],
        "caseId": validated["caseId"],
        "sourceSetSha256": validated["sourceSetSha256"],
        "automaticPromotion": False,
    }
    if any(state.get(key) != value for key, value in expected.items()):
        raise CampaignError("existing campaign state differs from the exact plan")
    if set((state.get("attempts") or {})) != {row["attemptId"] for row in validated["attempts"]}:
        raise CampaignError("existing campaign state has a different attempt set")


def run(command: list[str], label: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise CampaignError(
            f"{label} failed with exit {completed.returncode}: {completed.stderr.strip()}"
        )
    return completed


def copy_static_evidence(attempt: dict[str, Any], destination: pathlib.Path) -> pathlib.Path:
    destination.mkdir(parents=True, exist_ok=True)
    for name, source in (
        ("summary.json", attempt["summaryPath"]),
        ("decision-package.json", attempt["decisionPath"]),
    ):
        target = destination / name
        if target.exists():
            if sha256(target) != sha256(source):
                raise CampaignError(f"retained static evidence drifted for {attempt['attemptId']}")
        else:
            shutil.copyfile(source, target)
    return destination


def generated_plans(
    validated: dict[str, Any], attempt: dict[str, Any], root: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    root.mkdir(parents=True, exist_ok=True)
    build_plan = {
        "schema": "agentlab.harmony_assessed_workspace_build_plan.v1",
        "evaluationCase": binding(validated["casePath"]),
        "assessment": {
            "summary": binding(attempt["summaryPath"]),
            "decisionPackage": binding(attempt["decisionPath"]),
            "finalSourceState": binding(attempt["statePath"]),
            "workspace": str(attempt["workspace"]),
        },
        "sourceMaterialization": validated["mappings"],
        "build": validated["build"],
        "automaticPromotion": False,
    }
    build_path = root / "build-plan.json"
    write_or_verify(build_path, build_plan, "generated build plan")
    run_template = {
        "schema": "agentlab.harmony_evaluation_run_template.v1",
        "evaluationCase": binding(validated["casePath"]),
        "runId": f"{validated['campaignId']}.{attempt['attemptId']}",
        **validated["device"],
        "automaticPromotion": False,
    }
    run_path = root / "run-template.json"
    write_or_verify(run_path, run_template, "generated run template")
    emulator = {
        key: validated["device"]["runtime"][key]
        for key in (
            "toolsRoot", "imageRoot", "instancePath", "instance", "hdcPort", "bootMode"
        )
    }
    if "bootTimeoutSeconds" in validated["device"]["runtime"]:
        emulator["bootTimeoutSeconds"] = validated["device"]["runtime"]["bootTimeoutSeconds"]
    standard_template = {
        "schema": "agentlab.harmony_assessed_standard_test_template.v1",
        "evaluationCase": binding(validated["casePath"]),
        "sourceExecutor": binding(validated["sourceStandardTestExecutor"]),
        "configuration": validated["standardTestConfiguration"],
        "emulator": emulator,
        "automaticPromotion": False,
    }
    standard_path = root / "standard-test-template.json"
    write_or_verify(standard_path, standard_template, "generated standard-test template")
    loop_plan = {
        "schema": "agentlab.harmony_evaluation_loop_plan.v1",
        "loopId": f"{validated['campaignId']}.{attempt['attemptId']}",
        "evaluationCase": binding(validated["casePath"]),
        "buildPlan": binding(build_path),
        "standardTestTemplate": binding(standard_path),
        "runTemplate": binding(run_path),
        "buildProgram": binding(validated["programs"]["build"]),
        "standardTestProgram": binding(validated["programs"]["standardTest"]),
        "runProgram": binding(validated["programs"]["run"]),
        "automaticPromotion": False,
    }
    loop_path = root / "loop-plan.json"
    write_or_verify(loop_path, loop_plan, "generated loop plan")
    return build_path, run_path, loop_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        validated = validate_plan(args.plan.resolve())
        if output.exists():
            if not output.is_dir() or not (output / "campaign-state.json").is_file():
                raise CampaignError("existing output is not a resumable assessed campaign")
            state = load(output / "campaign-state.json", "campaign state")
            validate_state(state, validated)
        else:
            output.mkdir(parents=True)
            state = initial_state(validated)
            write_json(output / "campaign-state.json", state)

        evidence_rows = []
        for attempt in validated["attempts"]:
            attempt_id = attempt["attemptId"]
            attempt_root = output / "attempts" / attempt_id
            row_state = state["attempts"][attempt_id]
            if not attempt["staticInfrastructureValid"] or attempt["staticVerdict"] is False:
                evidence = copy_static_evidence(attempt, attempt_root / "evidence")
                row_state.update(
                    {
                        "status": "static-terminal",
                        "staticInfrastructureValid": attempt["staticInfrastructureValid"],
                        "subjectTaskSucceeded": attempt["staticVerdict"],
                        "evidenceDecisionSha256": sha256(evidence / "decision-package.json"),
                    }
                )
            else:
                recorded_composition_sha256 = row_state.get("compositionReceiptSha256")
                _, _, loop_plan = generated_plans(validated, attempt, attempt_root / "plans")
                loop_output = attempt_root / "harmony-loop"
                row_state.update({"status": "device-running", "startedAt": datetime.now(timezone.utc).isoformat()})
                write_json(output / "campaign-state.json", state)
                run(
                    [sys.executable, str(validated["programs"]["loop"]), "--plan", str(loop_plan), "--output", str(loop_output)],
                    f"{attempt_id} Harmony loop",
                )
                compound = attempt_root / "evidence"
                if not compound.exists():
                    run(
                        [
                            sys.executable,
                            str(validated["programs"]["compose"]),
                            "--static-assessment",
                            str(attempt["root"]),
                            "--harmony-loop",
                            str(loop_output),
                            "--output",
                            str(compound),
                        ],
                        f"{attempt_id} compound composition",
                    )
                receipt = load(compound / "composition-receipt.json", f"{attempt_id} composition receipt")
                composition_sha256 = sha256(compound / "composition-receipt.json")
                if (
                    recorded_composition_sha256 is not None
                    and recorded_composition_sha256 != composition_sha256
                ):
                    raise CampaignError(f"{attempt_id} completed composition evidence drifted")
                if receipt.get("status") != "assessed-review-required" or receipt.get("automaticPromotion") is not False:
                    raise CampaignError(f"{attempt_id} compound receipt is invalid")
                row_state.update(
                    {
                        "status": "device-assessed",
                        "subjectTaskSucceeded": receipt.get("subjectTaskSucceeded"),
                        "compositionReceiptSha256": composition_sha256,
                        "endedAt": datetime.now(timezone.utc).isoformat(),
                    }
                )
                evidence = compound
            write_json(output / "campaign-state.json", state)
            evidence_rows.append(
                {
                    "attemptId": attempt_id,
                    "participantId": attempt["participantId"],
                    "producerRun": attempt["producerRun"],
                    "evidence": evidence.relative_to(output).as_posix(),
                }
            )

        calibration_target = output / "calibration.json"
        if calibration_target.exists():
            if sha256(calibration_target) != sha256(validated["calibrationPath"]):
                raise CampaignError("retained calibration evidence drifted")
        else:
            shutil.copyfile(validated["calibrationPath"], calibration_target)
        manifest = {
            "schema": "agentlab.case_attempt_collection.v2",
            "sourceSetSha256": validated["sourceSetSha256"],
            "methodRevision": validated["methodRevision"],
            "cases": [
                {
                    "id": validated["caseId"],
                    "calibration": "calibration.json",
                    "attempts": evidence_rows,
                }
            ],
        }
        manifest_path = output / "attempts-manifest.json"
        write_or_verify(manifest_path, manifest, "attempt collection manifest")
        collected = output / "case-discrimination-input.json"
        if not collected.exists():
            run(
                [sys.executable, str(validated["programs"]["collect"]), "--manifest", str(manifest_path), "--output", str(collected)],
                "attempt collection",
            )
        report = output / "case-discrimination-report.json"
        if not report.exists():
            run(
                [
                    sys.executable,
                    str(validated["programs"]["score"]),
                    "--input",
                    str(collected),
                    "--required-trials",
                    str(validated["requiredTrials"]),
                    "--threshold",
                    str(validated["threshold"]),
                    "--output",
                    str(report),
                ],
                "case discrimination scoring",
            )
        feedback = output / "assessment-feedback-candidates.json"
        if not feedback.exists():
            run(
                [
                    sys.executable,
                    str(validated["programs"]["feedback"]),
                    "--case",
                    str(validated["casePath"]),
                    "--input",
                    str(collected),
                    "--report",
                    str(report),
                    "--output",
                    str(feedback),
                ],
                "assessment feedback derivation",
            )
        report_value = load(report, "case discrimination report")
        feedback_value = load(feedback, "assessment feedback")
        summary = {
            "schema": SUMMARY_SCHEMA,
            "status": "assessed-review-required",
            "campaignId": validated["campaignId"],
            "planSha256": validated["planSha256"],
            "caseId": validated["caseId"],
            "sourceSetSha256": validated["sourceSetSha256"],
            "methodRevision": validated["methodRevision"],
            **(
                {
                    "participantExperimentPlanSha256": sha256(
                        validated["experimentPlanPath"]
                    ),
                    "participantProfileCount": validated["experimentPlan"][
                        "participantProfileCount"
                    ],
                    "trialsPerParticipant": validated["experimentPlan"][
                        "trialsPerParticipant"
                    ],
                }
                if validated["experimentPlan"] is not None
                else {}
            ),
            **(
                {"calibrationAuthoring": validated["calibrationAuthoring"]}
                if validated["calibrationAuthoring"] is not None
                else {}
            ),
            "attemptCount": len(validated["attempts"]),
            "deviceAttemptCount": sum(
                row["status"] == "device-assessed" for row in state["attempts"].values()
            ),
            "eligibleCaseIds": report_value.get("eligibleCaseIds"),
            "feedbackCandidateCount": feedback_value.get("candidateCount"),
            "attemptManifestSha256": sha256(manifest_path),
            "discriminationInputSha256": sha256(collected),
            "discriminationReportSha256": sha256(report),
            "assessmentFeedbackSha256": sha256(feedback),
            "automaticPromotion": False,
            "nextGate": "maintainer-adjudication-and-new-analysis-cut",
        }
        write_or_verify(output / "summary.json", summary, "campaign summary")
        state["status"] = summary["status"]
        state["nextGate"] = summary["nextGate"]
        state["summarySha256"] = sha256(output / "summary.json")
        state.pop("error", None)
        write_json(output / "campaign-state.json", state)
        print(json.dumps({"ok": True, "output": str(output), "status": summary["status"]}, sort_keys=True))
        return 0
    except (CampaignError, OSError, ValueError) as error:
        if output.is_dir() and (output / "campaign-state.json").is_file():
            try:
                state = load(output / "campaign-state.json", "campaign state")
                state["status"] = "failed-resumable"
                state["error"] = str(error)
                write_json(output / "campaign-state.json", state)
            except Exception:
                pass
        print(json.dumps({"ok": False, "output": str(output), "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
