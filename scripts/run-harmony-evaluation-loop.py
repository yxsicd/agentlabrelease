#!/usr/bin/env python3
"""Resume a frozen Harmony case through build and emulator assessment gates."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


PLAN_SCHEMA = "agentlab.harmony_evaluation_loop_plan.v1"
TEMPLATE_SCHEMA = "agentlab.harmony_evaluation_run_template.v1"
STATE_SCHEMA = "agentlab.harmony_evaluation_loop_state.v1"
RECEIPT_SCHEMA = "agentlab.harmony_evaluation_loop_receipt.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
TOKEN = re.compile(r"[A-Za-z0-9_.:-]+")


class LoopError(RuntimeError):
    pass


def sha256(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load(path: pathlib.Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LoopError(f"cannot load {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise LoopError(f"{label} must be a JSON object")
    return value


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise LoopError(f"{label} must be an exact SHA256")
    return value


def bound_file(binding: Any, label: str, *, executable: bool = False) -> pathlib.Path:
    if not isinstance(binding, dict):
        raise LoopError(f"{label} binding is required")
    raw = binding.get("path")
    if not isinstance(raw, str) or not raw:
        raise LoopError(f"{label} path is required")
    path = pathlib.Path(raw).resolve()
    if not path.is_file():
        raise LoopError(f"{label} not found: {path}")
    if executable and not os.access(path, os.X_OK):
        raise LoopError(f"{label} is not executable: {path}")
    expected = require_digest(binding.get("sha256"), f"{label} sha256")
    if sha256(path) != expected:
        raise LoopError(f"{label} SHA256 differs from loop plan")
    return path


def validate_plan(plan_path: pathlib.Path) -> dict[str, Any]:
    plan_sha256 = sha256(plan_path)
    plan = load(plan_path, "loop plan")
    if plan.get("schema") != PLAN_SCHEMA:
        raise LoopError("unsupported Harmony evaluation loop plan schema")
    if plan.get("automaticPromotion") is not False:
        raise LoopError("Harmony evaluation loop must set automaticPromotion=false")
    loop_id = plan.get("loopId")
    if not isinstance(loop_id, str) or TOKEN.fullmatch(loop_id) is None:
        raise LoopError("loopId must be a non-empty safe token")

    case_path = bound_file(plan.get("evaluationCase"), "evaluation case")
    case_sha256 = sha256(case_path)
    case = load(case_path, "evaluation case")
    if (
        case.get("schema") != "agentlab.multi_repo_evaluation_case.v1"
        or case.get("status") != "frozen-calibrated"
        or case.get("automaticPromotion") is not False
        or (case.get("calibration") or {}).get("qualified") is not True
    ):
        raise LoopError("loop requires a frozen, calibrated, non-promoted evaluation case")
    case_id = case.get("id")
    source_set_sha256 = case.get("sourceSetSha256")
    if not isinstance(case_id, str) or TOKEN.fullmatch(case_id) is None:
        raise LoopError("evaluation case id must be a non-empty safe token")
    require_digest(source_set_sha256, "evaluation case sourceSetSha256")

    build_plan_path = bound_file(plan.get("buildPlan"), "Harmony build plan")
    build_plan = load(build_plan_path, "Harmony build plan")
    build_case = build_plan.get("evaluationCase") or {}
    if (
        build_plan.get("schema") != "agentlab.harmony_case_build_plan.v1"
        or build_plan.get("automaticPromotion") is not False
        or pathlib.Path(build_case.get("path", "")).resolve() != case_path
        or build_case.get("sha256") != case_sha256
    ):
        raise LoopError("Harmony build plan does not bind the exact frozen case")

    template_path = bound_file(plan.get("runTemplate"), "Harmony run template")
    template = load(template_path, "Harmony run template")
    template_case = template.get("evaluationCase") or {}
    if (
        template.get("schema") != TEMPLATE_SCHEMA
        or template.get("automaticPromotion") is not False
        or pathlib.Path(template_case.get("path", "")).resolve() != case_path
        or template_case.get("sha256") != case_sha256
    ):
        raise LoopError("Harmony run template does not bind the exact frozen case")
    if "buildReceipt" in template or "artifact" in template:
        raise LoopError("run template must leave buildReceipt and artifact to the loop")

    builder = bound_file(plan.get("buildProgram"), "Harmony build program", executable=True)
    runner = bound_file(plan.get("runProgram"), "Harmony run program", executable=True)
    return {
        "planSha256": plan_sha256,
        "loopId": loop_id,
        "casePath": case_path,
        "caseSha256": case_sha256,
        "caseId": case_id,
        "sourceSetSha256": source_set_sha256,
        "buildPlanPath": build_plan_path,
        "buildPlanSha256": sha256(build_plan_path),
        "templatePath": template_path,
        "templateSha256": sha256(template_path),
        "template": template,
        "builder": builder,
        "builderSha256": sha256(builder),
        "runner": runner,
        "runnerSha256": sha256(runner),
    }


def new_state(validated: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "status": "running",
        "loopId": validated["loopId"],
        "planSha256": validated["planSha256"],
        "caseId": validated["caseId"],
        "evaluationCaseSha256": validated["caseSha256"],
        "sourceSetSha256": validated["sourceSetSha256"],
        "stages": {
            "build": {"status": "pending", "attempts": 0},
            "emulatorAssessment": {"status": "pending", "attempts": 0},
        },
        "automaticPromotion": False,
        "nextGate": "independent-harmony-build",
    }


def validate_resume(state: dict[str, Any], validated: dict[str, Any]) -> None:
    expected = {
        "schema": STATE_SCHEMA,
        "loopId": validated["loopId"],
        "planSha256": validated["planSha256"],
        "caseId": validated["caseId"],
        "evaluationCaseSha256": validated["caseSha256"],
        "sourceSetSha256": validated["sourceSetSha256"],
        "automaticPromotion": False,
    }
    for key, value in expected.items():
        if state.get(key) != value:
            raise LoopError(f"existing loop state {key} differs from the exact plan")
    stages = state.get("stages")
    if not isinstance(stages, dict) or set(stages) != {"build", "emulatorAssessment"}:
        raise LoopError("existing loop state has an invalid stage set")


def record_stage_start(output: pathlib.Path, state: dict[str, Any], stage: str, next_gate: str) -> None:
    row = state["stages"][stage]
    row["attempts"] += 1
    row["status"] = "running"
    row["startedAt"] = datetime.now(timezone.utc).isoformat()
    row.pop("error", None)
    state["status"] = "running"
    state["nextGate"] = next_gate
    write_json(output / "loop-state.json", state)


def run_program(program: pathlib.Path, plan: pathlib.Path, output: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(program), "--plan", str(plan), "--output", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )


def retain_command(output: pathlib.Path, stage: str, completed: subprocess.CompletedProcess[str]) -> None:
    (output / f"{stage}.stdout.log").write_text(completed.stdout, encoding="utf-8")
    (output / f"{stage}.stderr.log").write_text(completed.stderr, encoding="utf-8")


def fail_stage(
    output: pathlib.Path,
    state: dict[str, Any],
    stage: str,
    message: str,
    *,
    resumable: bool = True,
) -> None:
    row = state["stages"][stage]
    row["status"] = "failed"
    row["endedAt"] = datetime.now(timezone.utc).isoformat()
    row["error"] = message
    state["status"] = "failed-resumable" if resumable else "failed-integrity"
    state["nextGate"] = stage if resumable else "operator-review-and-new-loop-id"
    write_json(output / "loop-state.json", state)


def completed_build(output: pathlib.Path, state: dict[str, Any]) -> tuple[pathlib.Path, pathlib.Path]:
    build = output / "build"
    receipt_path = build / "build-receipt.json"
    artifact_path = build / "artifact.hap"
    if not receipt_path.is_file() or not artifact_path.is_file():
        raise LoopError("completed build stage evidence is absent")
    receipt = load(receipt_path, "build receipt")
    if (
        receipt.get("schema") != "agentlab.harmony_case_build_receipt.v1"
        or receipt.get("status") != "passed"
        or receipt.get("automaticPromotion") is not False
        or receipt.get("hapSha256") != sha256(artifact_path)
    ):
        raise LoopError("completed build stage evidence is invalid")
    recorded = state["stages"]["build"]
    if recorded.get("receiptSha256") != sha256(receipt_path) or recorded.get("artifactSha256") != sha256(artifact_path):
        raise LoopError("completed build stage evidence drifted after recording")
    return receipt_path, artifact_path


def make_run_plan(validated: dict[str, Any], receipt: pathlib.Path, artifact: pathlib.Path) -> dict[str, Any]:
    run_plan = dict(validated["template"])
    run_plan["schema"] = "agentlab.harmony_evaluation_run_plan.v1"
    run_plan["buildReceipt"] = {"path": str(receipt), "sha256": sha256(receipt)}
    run_plan["artifact"] = {"path": str(artifact), "sha256": sha256(artifact)}
    return run_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        validated = validate_plan(args.plan.resolve())
        if output.exists():
            if not output.is_dir() or not (output / "loop-state.json").is_file():
                raise LoopError("existing output is not a resumable Harmony loop")
            state = load(output / "loop-state.json", "loop state")
            validate_resume(state, validated)
        else:
            output.mkdir(parents=True)
            state = new_state(validated)
            write_json(output / "loop-state.json", state)

        if state["stages"]["build"].get("status") == "passed":
            receipt_path, artifact_path = completed_build(output, state)
        else:
            record_stage_start(output, state, "build", "independent-harmony-build")
            if sha256(validated["builder"]) != validated["builderSha256"]:
                message = "Harmony build program drifted before execution"
                fail_stage(output, state, "build", message)
                raise LoopError(message)
            completed = run_program(validated["builder"], validated["buildPlanPath"], output / "build")
            retain_command(output, "build", completed)
            if completed.returncode != 0:
                message = f"Harmony build program failed with exit {completed.returncode}"
                fail_stage(output, state, "build", message, resumable=not (output / "build").exists())
                raise LoopError(message)
            try:
                if sha256(validated["builder"]) != validated["builderSha256"]:
                    raise LoopError("Harmony build program drifted during execution")
                receipt_path = output / "build/build-receipt.json"
                artifact_path = output / "build/artifact.hap"
                receipt = load(receipt_path, "build receipt")
                if receipt.get("planSha256") != validated["buildPlanSha256"]:
                    raise LoopError("build receipt does not bind the loop's build plan")
                if receipt.get("evaluationCaseSha256") != validated["caseSha256"]:
                    raise LoopError("build receipt does not bind the loop's evaluation case")
                if receipt.get("hapSha256") != sha256(artifact_path):
                    raise LoopError("build receipt does not bind the produced HAP")
            except (LoopError, OSError) as error:
                fail_stage(output, state, "build", str(error), resumable=False)
                raise
            state["stages"]["build"].update({
                "status": "passed",
                "endedAt": datetime.now(timezone.utc).isoformat(),
                "receiptSha256": sha256(receipt_path),
                "artifactSha256": sha256(artifact_path),
            })
            state["nextGate"] = "harmony-emulator-assessment"
            write_json(output / "loop-state.json", state)

        expected_run_plan = make_run_plan(validated, receipt_path, artifact_path)
        run_plan_path = output / "run-plan.json"
        if run_plan_path.exists():
            if load(run_plan_path, "generated run plan") != expected_run_plan:
                raise LoopError("generated run plan drifted; refusing to resume")
        else:
            write_json(run_plan_path, expected_run_plan)

        assessment = output / "assessment"
        if state["stages"]["emulatorAssessment"].get("status") == "passed":
            binding_path = assessment / "evaluation-binding.json"
            if not binding_path.is_file() or state["stages"]["emulatorAssessment"].get("bindingSha256") != sha256(binding_path):
                raise LoopError("completed emulator assessment evidence drifted after recording")
        else:
            record_stage_start(output, state, "emulatorAssessment", "harmony-emulator-assessment")
            if sha256(validated["runner"]) != validated["runnerSha256"]:
                message = "Harmony run program drifted before execution"
                fail_stage(output, state, "emulatorAssessment", message)
                raise LoopError(message)
            completed = run_program(validated["runner"], run_plan_path, assessment)
            retain_command(output, "assessment", completed)
            if completed.returncode != 0:
                message = f"Harmony emulator assessment failed with exit {completed.returncode}"
                fail_stage(
                    output,
                    state,
                    "emulatorAssessment",
                    message,
                    resumable=not assessment.exists(),
                )
                raise LoopError(message)
            try:
                if sha256(validated["runner"]) != validated["runnerSha256"]:
                    raise LoopError("Harmony run program drifted during execution")
                binding_path = assessment / "evaluation-binding.json"
                binding = load(binding_path, "evaluation binding")
                if (
                    binding.get("schema") != "agentlab.harmony_evaluation_binding.v1"
                    or binding.get("status") != "passed-review-required"
                    or binding.get("automaticPromotion") is not False
                    or binding.get("evaluationCaseSha256") != validated["caseSha256"]
                    or binding.get("buildReceiptSha256") != sha256(receipt_path)
                    or binding.get("hapSha256") != sha256(artifact_path)
                ):
                    raise LoopError("emulator assessment binding differs from the loop lineage")
            except (LoopError, OSError) as error:
                fail_stage(output, state, "emulatorAssessment", str(error), resumable=False)
                raise
            state["stages"]["emulatorAssessment"].update({
                "status": "passed",
                "endedAt": datetime.now(timezone.utc).isoformat(),
                "bindingSha256": sha256(binding_path),
            })

        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": "passed-review-required",
            "loopId": validated["loopId"],
            "planSha256": validated["planSha256"],
            "caseId": validated["caseId"],
            "evaluationCaseSha256": validated["caseSha256"],
            "sourceSetSha256": validated["sourceSetSha256"],
            "buildPlanSha256": validated["buildPlanSha256"],
            "runTemplateSha256": validated["templateSha256"],
            "buildProgramSha256": validated["builderSha256"],
            "runProgramSha256": validated["runnerSha256"],
            "buildReceiptSha256": sha256(receipt_path),
            "hapSha256": sha256(artifact_path),
            "runPlanSha256": sha256(run_plan_path),
            "evaluationBindingSha256": sha256(binding_path),
            "automaticPromotion": False,
            "nextGate": "maintainer-adjudication-and-next-analysis-cut",
        }
        receipt_path_final = output / "loop-receipt.json"
        if receipt_path_final.exists() and load(receipt_path_final, "loop receipt") != receipt:
            raise LoopError("existing loop receipt differs from recomputed evidence")
        write_json(receipt_path_final, receipt)
        state["status"] = "passed-review-required"
        state["nextGate"] = receipt["nextGate"]
        write_json(output / "loop-state.json", state)
        print(json.dumps({"ok": True, "output": str(output), "status": receipt["status"], "resumable": True}, sort_keys=True))
        return 0
    except (LoopError, OSError) as error:
        print(json.dumps({"ok": False, "output": str(output), "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
