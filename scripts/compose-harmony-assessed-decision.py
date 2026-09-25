#!/usr/bin/env python3
"""Compose a passing static assessment with its exact Harmony device verdict."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import shutil
import sys
import tempfile
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")


class CompositionError(RuntimeError):
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
        raise CompositionError(f"cannot load {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise CompositionError(f"{label} must be a JSON object")
    return value


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise CompositionError(f"{label} must be an exact SHA256")
    return value


def require_file(path: pathlib.Path, label: str) -> pathlib.Path:
    resolved = path.resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise CompositionError(f"{label} not found or not regular: {resolved}")
    return resolved


def process_measurement(phases: list[dict[str, Any]], duration_ms: int) -> dict[str, Any]:
    oracle_outcomes = [
        row["oraclePass"] for row in phases if isinstance(row.get("oraclePass"), bool)
    ]
    return {
        "schema": "agentlab.assessment_process_measurement.v1",
        "stageCount": len(phases),
        "participantCompletedStageCount": sum(
            row["participantCompleted"] for row in phases
        ),
        "oracleExecutedStageCount": len(oracle_outcomes),
        "oraclePassedStageCount": sum(value is True for value in oracle_outcomes),
        "scopeViolationStageCount": sum(not row["scopeValid"] for row in phases),
        "changedPathCount": sum(row["changedPathCount"] for row in phases),
        "unauthorizedPathCount": sum(row["unauthorizedPathCount"] for row in phases),
        "oracleRecoveryCount": sum(
            previous is False and current is True
            for previous, current in zip(oracle_outcomes, oracle_outcomes[1:])
        ),
        "oracleRegressionCount": sum(
            previous is True and current is False
            for previous, current in zip(oracle_outcomes, oracle_outcomes[1:])
        ),
        "participantDurationMs": sum(row["participantDurationMs"] for row in phases),
        "oracleDurationMs": sum(row["oracleDurationMs"] for row in phases),
        "stageDurationMs": sum(row["stageDurationMs"] for row in phases),
        "attemptDurationMs": duration_ms,
        "processMeasurementQualified": True,
    }


def validate_static_process(
    summary: dict[str, Any], decision: dict[str, Any], phases: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, int | None]:
    process = summary.get("processMeasurement")
    if process is None:
        if decision.get("processMeasurement") is not None:
            raise CompositionError("static process measurement is unbound")
        return None, None
    if process != decision.get("processMeasurement"):
        raise CompositionError("static process measurement differs between authorities")
    duration_ms = summary.get("durationMs")
    if not isinstance(duration_ms, int) or duration_ms < 0:
        raise CompositionError("static process duration is invalid")
    for phase in phases:
        if not isinstance(phase, dict):
            raise CompositionError("static process phase is invalid")
        for field in (
            "participantDurationMs",
            "oracleDurationMs",
            "stageDurationMs",
            "changedPathCount",
            "unauthorizedPathCount",
            "cumulativeCheckCount",
        ):
            if not isinstance(phase.get(field), int) or phase[field] < 0:
                raise CompositionError(f"static process phase {field} is invalid")
        if (
            not isinstance(phase.get("changedPaths"), list)
            or phase["changedPathCount"] != len(phase["changedPaths"])
            or not isinstance(phase.get("unauthorizedPaths"), list)
            or phase["unauthorizedPathCount"] != len(phase["unauthorizedPaths"])
            or not isinstance(phase.get("participantCompleted"), bool)
            or not isinstance(phase.get("scopeValid"), bool)
        ):
            raise CompositionError("static process phase evidence is inconsistent")
    if process != process_measurement(phases, duration_ms):
        raise CompositionError("static process measurement differs from retained phases")
    return process, duration_ms


def validate_device_process(
    root: pathlib.Path, binding: dict[str, Any], device_succeeded: bool
) -> dict[str, Any] | None:
    process = binding.get("deviceProcessMeasurement")
    if process is None:
        return None
    if not isinstance(process, dict) or process.get("schema") != "agentlab.harmony_device_process_measurement.v1":
        raise CompositionError("Harmony device process measurement schema differs")
    integer_fields = (
        "runnerDurationMs",
        "uiActionCount",
        "uiCheckCount",
        "profileWorkloadActionCount",
        "smartPerfSampleCount",
    )
    if not all(isinstance(process.get(field), int) and process[field] >= 0 for field in integer_fields):
        raise CompositionError("Harmony device process measurement is invalid")
    if process.get("functionalOraclePass") is not device_succeeded:
        raise CompositionError("Harmony device process Oracle verdict differs")
    if process.get("profileCollected") is not device_succeeded:
        raise CompositionError("Harmony device process profile verdict differs")
    evidence = process.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {
        "uiActions", "uiChecks", "profileWorkloadActions"
    }:
        raise CompositionError("Harmony device process evidence set differs")
    paths = {
        "uiActions": root / "assessment/execution/ui-actions.tsv",
        "uiChecks": root / "assessment/execution/ui-checks.tsv",
        "profileWorkloadActions": root / "assessment/execution/profile-workload-actions.tsv",
    }
    counts = {
        "uiActions": "uiActionCount",
        "uiChecks": "uiCheckCount",
        "profileWorkloadActions": "profileWorkloadActionCount",
    }
    for name, path in paths.items():
        reference = evidence[name]
        if reference is None:
            if path.exists() or process[counts[name]] != 0:
                raise CompositionError(f"Harmony device {name} absence differs")
            continue
        if not isinstance(reference, dict) or set(reference) != {"sha256", "rowCount"}:
            raise CompositionError(f"Harmony device {name} evidence is invalid")
        retained = require_file(path, f"Harmony device {name} evidence")
        rows = [line for line in retained.read_text(encoding="utf-8").splitlines() if line.strip()]
        if (
            reference.get("sha256") != sha256(retained)
            or reference.get("rowCount") != len(rows)
            or process[counts[name]] != len(rows)
        ):
            raise CompositionError(f"Harmony device {name} evidence differs")
    if process["uiCheckCount"] < 1:
        raise CompositionError("Harmony device process has no UI checks")
    summary_path = root / "assessment/execution/smartperf-summary.json"
    if device_succeeded:
        summary_path = require_file(summary_path, "Harmony SmartPerf summary")
        summary = load(summary_path, "Harmony SmartPerf summary")
        if (
            binding.get("smartperfSummarySha256") != sha256(summary_path)
            or summary.get("profileValid") is not True
            or summary.get("sampleCount") != process["smartPerfSampleCount"]
        ):
            raise CompositionError("Harmony SmartPerf process evidence differs")
    elif (
        summary_path.exists()
        or binding.get("smartperfSummarySha256") is not None
        or process["smartPerfSampleCount"] != 0
    ):
        raise CompositionError("failing Harmony device overclaims SmartPerf process evidence")
    if device_succeeded and (
        process["profileWorkloadActionCount"] < 1
        or process["smartPerfSampleCount"] < 1
    ):
        raise CompositionError("passing Harmony device process evidence is incomplete")
    return process


def validate_static(root: pathlib.Path) -> dict[str, Any]:
    summary_path = require_file(root / "summary.json", "static assessment summary")
    decision_path = require_file(root / "decision-package.json", "static decision package")
    state_path = require_file(root / "final-source-state.json", "static final source state")
    summary = load(summary_path, "static assessment summary")
    decision = load(decision_path, "static decision package")
    final_state = load(state_path, "static final source state")
    if summary.get("schema") != "agentlab.multi_repo_assessment_summary.v1":
        raise CompositionError("unsupported static assessment summary schema")
    if decision.get("schema") != "agentlab.harness_decision_package.v1":
        raise CompositionError("unsupported static decision package schema")
    fields = {
        "taskId": summary.get("taskId"),
        "sourceSetSha256": summary.get("sourceSetSha256"),
        "participantId": summary.get("participantId"),
        "assessmentStatus": "assessed",
        "infrastructureAvailable": True,
        "subjectTaskSucceeded": True,
    }
    if not all(isinstance(fields[key], str) and fields[key] for key in ("taskId", "participantId")):
        raise CompositionError("static task and participant identities are required")
    require_digest(fields["sourceSetSha256"], "static sourceSetSha256")
    for key, expected in fields.items():
        if summary.get(key) != expected or decision.get(key) != expected:
            raise CompositionError("device composition requires one exact statically passing attempt")
    if decision.get("automaticPromotion") is not False:
        raise CompositionError("static decision must not auto-promote")
    phases = decision.get("phaseVerdicts")
    if not isinstance(phases, list) or not phases:
        raise CompositionError("static decision has no phase verdicts")
    if any(
        not isinstance(row, dict)
        or row.get("scopeValid") is not True
        or row.get("oraclePass") is not True
        for row in phases
    ):
        raise CompositionError("static decision phase verdicts contradict its passing result")
    subject_workspace_sha256 = require_digest(
        summary.get("finalWorkspaceSha256"), "static finalWorkspaceSha256"
    )
    if subject_workspace_sha256 != canonical_sha256(final_state):
        raise CompositionError("static summary does not bind the final source state")
    process, duration_ms = validate_static_process(summary, decision, phases)
    return {
        **fields,
        "summaryPath": summary_path,
        "decisionPath": decision_path,
        "statePath": state_path,
        "summarySha256": sha256(summary_path),
        "decisionSha256": sha256(decision_path),
        "stateSha256": sha256(state_path),
        "subjectWorkspaceSha256": subject_workspace_sha256,
        "phases": phases,
        "processMeasurement": process,
        "durationMs": duration_ms,
    }


def validate_loop(root: pathlib.Path, static: dict[str, Any]) -> dict[str, Any]:
    receipt_path = require_file(root / "loop-receipt.json", "Harmony loop receipt")
    receipt = load(receipt_path, "Harmony loop receipt")
    standard_path = require_file(
        root / "standard-test/receipt.json", "Harmony assessed standard-test receipt"
    )
    standard = load(standard_path, "Harmony assessed standard-test receipt")
    assessed = {
        "participantId": static["participantId"],
        "subjectWorkspaceSha256": static["subjectWorkspaceSha256"],
        "assessmentSummarySha256": static["summarySha256"],
        "assessmentDecisionSha256": static["decisionSha256"],
        "finalSourceStateSha256": static["stateSha256"],
    }
    if (
        standard.get("schema") != "agentlab.harmony_assessed_standard_test_receipt.v1"
        or standard.get("caseId") != static["taskId"]
        or standard.get("sourceSetSha256") != static["sourceSetSha256"]
        or standard.get("assessedWorkspace") != assessed
        or standard.get("automaticPromotion") is not False
        or receipt.get("standardTestReceiptSha256") != sha256(standard_path)
    ):
        raise CompositionError("Harmony standard-test evidence differs from static attempt")
    standard_succeeded = standard.get("subjectTaskSucceeded")
    expected_standard_status = (
        "passed-review-required" if standard_succeeded is True else
        "assessed-failure-review-required" if standard_succeeded is False else None
    )
    if standard.get("status") != expected_standard_status:
        raise CompositionError("Harmony standard-test status contradicts its verdict")
    if standard_succeeded is False:
        if (
            receipt.get("schema") != "agentlab.harmony_evaluation_loop_receipt.v1"
            or receipt.get("status") != "assessed-failure-review-required"
            or receipt.get("failureClass") != "standard-test"
            or receipt.get("subjectTaskSucceeded") is not False
            or receipt.get("assessedWorkspace") != assessed
            or receipt.get("automaticPromotion") is not False
        ):
            raise CompositionError("Harmony loop did not retain the standard-test failure")
        return {
            "deviceSucceeded": False,
            "deviceSkipped": True,
            "failureClass": "standard-test",
            "receiptPath": receipt_path,
            "standardPath": standard_path,
            "receiptSha256": sha256(receipt_path),
            "standardSha256": sha256(standard_path),
            "hapSha256": require_digest(receipt.get("hapSha256"), "Harmony HAP sha256"),
            "processMeasurement": None,
            "loopProcessMeasurement": None,
        }
    binding_path = require_file(
        root / "assessment/evaluation-binding.json", "Harmony evaluation binding"
    )
    result_path = require_file(root / "assessment/execution/result.json", "Harmony result")
    binding = load(binding_path, "Harmony evaluation binding")
    result = load(result_path, "Harmony result")
    allowed_statuses = {
        "passed-review-required": True,
        "assessed-failure-review-required": False,
    }
    if receipt.get("schema") != "agentlab.harmony_evaluation_loop_receipt.v1":
        raise CompositionError("unsupported Harmony loop receipt schema")
    if binding.get("schema") != "agentlab.harmony_evaluation_binding.v1":
        raise CompositionError("unsupported Harmony evaluation binding schema")
    if receipt.get("status") not in allowed_statuses or binding.get("status") != receipt.get("status"):
        raise CompositionError("Harmony receipt and binding statuses are inconsistent")
    device_succeeded = allowed_statuses[receipt["status"]]
    expected = {
        "caseId": static["taskId"],
        "sourceSetSha256": static["sourceSetSha256"],
        "buildAuthority": "independent-harmony-assessed-workspace-build",
        "subjectTaskSucceeded": device_succeeded,
        "automaticPromotion": False,
    }
    for key, value in expected.items():
        if receipt.get(key) != value or (key in binding and binding.get(key) != value):
            raise CompositionError(f"Harmony evidence {key} differs from static attempt")
    if receipt.get("evaluationBindingSha256") != sha256(binding_path):
        raise CompositionError("Harmony loop receipt does not bind evaluation binding")
    if binding.get("resultSha256") != sha256(result_path):
        raise CompositionError("Harmony evaluation binding does not bind result")
    if receipt.get("assessedWorkspace") != assessed or binding.get("assessedWorkspace") != assessed:
        raise CompositionError("Harmony evidence does not bind the exact static Agent workspace")
    result_expected = {
        "schema": "agentlab.harmony_emulator_case_result.v3",
        "taskId": static["taskId"],
        "sourceSetSha256": static["sourceSetSha256"],
        "hapSha256": receipt.get("hapSha256"),
        "sourceIdentity": f"artifact-sha256:{receipt.get('hapSha256')}",
        "assessmentStatus": "assessed",
        "infrastructureAvailable": True,
        "subjectTaskSucceeded": device_succeeded,
        "powerThermalAuthority": "unavailable_on_emulator",
    }
    for key, value in result_expected.items():
        if result.get(key) != value:
            raise CompositionError(f"Harmony result {key} differs from compound attempt")
    if device_succeeded:
        if result.get("status") != "passed" or result.get("oracleStatus") != "passed":
            raise CompositionError("passing Harmony result contradicts its Oracle status")
    else:
        if (
            result.get("status") != "failed"
            or result.get("oracleStatus") != "failed"
            or result.get("failureClass") != "oracle"
        ):
            raise CompositionError("failing Harmony result is not an assessed Oracle failure")
    device_process = validate_device_process(root, binding, device_succeeded)
    loop_process = receipt.get("processMeasurement")
    if device_process is not None:
        if (
            not isinstance(loop_process, dict)
            or loop_process.get("schema")
            != "agentlab.harmony_evaluation_loop_process_measurement.v1"
        ):
            raise CompositionError("Harmony loop process measurement is absent")
        for field in (
            "buildDurationMs",
            "standardTestDurationMs",
            "emulatorAssessmentDurationMs",
            "runnerDurationMs",
            "totalDurationMs",
        ):
            if not isinstance(loop_process.get(field), int) or loop_process[field] < 0:
                raise CompositionError(f"Harmony loop process {field} is invalid")
        if (
            loop_process["runnerDurationMs"] != device_process["runnerDurationMs"]
            or loop_process["totalDurationMs"]
            != loop_process["buildDurationMs"]
            + loop_process["standardTestDurationMs"]
            + loop_process["emulatorAssessmentDurationMs"]
            or loop_process["runnerDurationMs"]
            > loop_process["emulatorAssessmentDurationMs"]
        ):
            raise CompositionError("Harmony loop and device process measurements differ")
    elif loop_process is not None:
        raise CompositionError("Harmony loop has an unbound process measurement")
    return {
        "deviceSucceeded": device_succeeded,
        "deviceSkipped": False,
        "failureClass": result.get("failureClass"),
        "receiptPath": receipt_path,
        "bindingPath": binding_path,
        "resultPath": result_path,
        "receiptSha256": sha256(receipt_path),
        "bindingSha256": sha256(binding_path),
        "resultSha256": sha256(result_path),
        "standardPath": standard_path,
        "standardSha256": sha256(standard_path),
        "hapSha256": require_digest(receipt.get("hapSha256"), "Harmony HAP sha256"),
        "environmentIdentity": binding.get("environmentIdentity"),
        "performancePolicySha256": binding.get("performancePolicySha256"),
        "profileWorkloadSha256": binding.get("profileWorkloadSha256"),
        "smartperfSummarySha256": binding.get("smartperfSummarySha256"),
        "processMeasurement": device_process,
        "loopProcessMeasurement": loop_process,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--static-assessment", type=pathlib.Path, required=True)
    parser.add_argument("--harmony-loop", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        print(f"refusing to overwrite existing output: {output}", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = pathlib.Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        static = validate_static(args.static_assessment.resolve())
        device = validate_loop(args.harmony_loop.resolve(), static)
        phase = {
            "stageId": "harmony-standard-test" if device["deviceSkipped"] else "harmony-device",
            "participantCompleted": True,
            "changedPaths": [],
            "unauthorizedPaths": [],
            "scopeValid": True,
            "oraclePass": device["deviceSucceeded"],
            "oracleReceiptSha256": (
                device["standardSha256"]
                if device["deviceSkipped"] else device["resultSha256"]
            ),
            "workspaceSha256": static["subjectWorkspaceSha256"],
            "authority": (
                "source-bound-ohosTest-oracle"
                if device["deviceSkipped"] else "operator-owned-harmony-ui-oracle"
            ),
            "hapSha256": device["hapSha256"],
        }
        if not device["deviceSkipped"]:
            phase["environmentIdentity"] = device["environmentIdentity"]
        if device["processMeasurement"] is not None:
            device_process = device["processMeasurement"]
            loop_process = device["loopProcessMeasurement"]
            phase.update(
                {
                    "changedPathCount": 0,
                    "unauthorizedPathCount": 0,
                    "participantDurationMs": 0,
                    "oracleDurationMs": loop_process["emulatorAssessmentDurationMs"],
                    "stageDurationMs": loop_process["totalDurationMs"],
                    "cumulativeCheckCount": device_process["uiCheckCount"],
                    "deviceProcessMeasurement": device_process,
                }
            )
        phases = [*static["phases"], phase]
        verdict = device["deviceSucceeded"]
        process = None
        duration_ms = None
        if static["processMeasurement"] is not None and device["processMeasurement"] is not None:
            duration_ms = (
                static["durationMs"]
                + device["loopProcessMeasurement"]["totalDurationMs"]
            )
            process = process_measurement(phases, duration_ms)
        summary = {
            "schema": "agentlab.harmony_compound_assessment_summary.v1",
            "taskId": static["taskId"],
            "sourceSetSha256": static["sourceSetSha256"],
            "participantId": static["participantId"],
            "assessmentStatus": "assessed",
            "infrastructureAvailable": True,
            "subjectTaskSucceeded": verdict,
            "stages": phases,
            "subjectWorkspaceSha256": static["subjectWorkspaceSha256"],
            "hapSha256": device["hapSha256"],
            "staticAssessmentSummarySha256": static["summarySha256"],
            "staticDecisionSha256": static["decisionSha256"],
            "harmonyLoopReceiptSha256": device["receiptSha256"],
            "harmonyStandardTestReceiptSha256": device["standardSha256"],
            "assessmentBoundary": "Static frozen Oracle plus exact assessed-workspace source-bound ohosTest; emulator UI and performance run only after the standard-test gate passes.",
        }
        if not device["deviceSkipped"]:
            summary.update({
                "harmonyEvaluationBindingSha256": device["bindingSha256"],
                "harmonyResultSha256": device["resultSha256"],
                "performancePolicySha256": device["performancePolicySha256"],
                "profileWorkloadSha256": device["profileWorkloadSha256"],
                "smartperfSummarySha256": device["smartperfSummarySha256"],
            })
        if process is not None:
            summary["durationMs"] = duration_ms
            summary["processMeasurement"] = process
        decision = {
            "schema": "agentlab.harness_decision_package.v1",
            "taskId": static["taskId"],
            "sourceSetSha256": static["sourceSetSha256"],
            "participantId": static["participantId"],
            "assessmentStatus": "assessed",
            "infrastructureAvailable": True,
            "subjectTaskSucceeded": verdict,
            "phaseVerdicts": phases,
            "launchErrors": [],
            "compoundEvidence": {
                "staticSummarySha256": static["summarySha256"],
                "staticDecisionSha256": static["decisionSha256"],
                "finalSourceStateSha256": static["stateSha256"],
                "harmonyLoopReceiptSha256": device["receiptSha256"],
                "harmonyStandardTestReceiptSha256": device["standardSha256"],
            },
            "automaticPromotion": False,
            "harnessPolicy": "Static scope/Oracle, source-bound ohosTest, and device UI Oracle are ordered independent verdict gates; infrastructure failure is never converted to Agent failure.",
        }
        if not device["deviceSkipped"]:
            decision["compoundEvidence"].update({
                "harmonyEvaluationBindingSha256": device["bindingSha256"],
                "harmonyResultSha256": device["resultSha256"],
            })
        if process is not None:
            decision["processMeasurement"] = process
        write_json(stage / "summary.json", summary)
        write_json(stage / "decision-package.json", decision)
        write_json(
            stage / "composition-receipt.json",
            {
                "schema": "agentlab.harmony_compound_assessment_receipt.v1",
                "status": "assessed-review-required",
                "taskId": static["taskId"],
                "sourceSetSha256": static["sourceSetSha256"],
                "participantId": static["participantId"],
                "subjectTaskSucceeded": verdict,
                "summarySha256": sha256(stage / "summary.json"),
                "decisionPackageSha256": sha256(stage / "decision-package.json"),
                "automaticPromotion": False,
            },
        )
        stage.rename(output)
        print(json.dumps({"ok": True, "output": str(output), "subjectTaskSucceeded": verdict}, sort_keys=True))
        return 0
    except (CompositionError, OSError) as error:
        write_json(
            stage / "failure.json",
            {
                "schema": "agentlab.harmony_compound_assessment_receipt.v1",
                "status": "failed",
                "error": str(error),
                "automaticPromotion": False,
            },
        )
        print(json.dumps({"ok": False, "retained": str(stage), "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
