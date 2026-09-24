#!/usr/bin/env python3
"""Resume a trusted assessed campaign through Harmony device and feedback gates."""
from __future__ import annotations

import argparse
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
    programs_raw = plan.get("programs")
    if not isinstance(programs_raw, dict):
        raise CampaignError("program bindings are required")
    program_names = {
        "build": True,
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
        "methodRevision": method_revision,
        "attempts": attempts,
        "requiredTrials": required_trials,
        "threshold": float(threshold),
        "programs": programs,
        "device": device,
        "mappings": mappings,
        "build": build,
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
    loop_plan = {
        "schema": "agentlab.harmony_evaluation_loop_plan.v1",
        "loopId": f"{validated['campaignId']}.{attempt['attemptId']}",
        "evaluationCase": binding(validated["casePath"]),
        "buildPlan": binding(build_path),
        "runTemplate": binding(run_path),
        "buildProgram": binding(validated["programs"]["build"]),
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
