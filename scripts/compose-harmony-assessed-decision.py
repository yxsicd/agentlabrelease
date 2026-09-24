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
    }


def validate_loop(root: pathlib.Path, static: dict[str, Any]) -> dict[str, Any]:
    receipt_path = require_file(root / "loop-receipt.json", "Harmony loop receipt")
    binding_path = require_file(
        root / "assessment/evaluation-binding.json", "Harmony evaluation binding"
    )
    result_path = require_file(root / "assessment/execution/result.json", "Harmony result")
    receipt = load(receipt_path, "Harmony loop receipt")
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
    assessed = {
        "participantId": static["participantId"],
        "subjectWorkspaceSha256": static["subjectWorkspaceSha256"],
        "assessmentSummarySha256": static["summarySha256"],
        "assessmentDecisionSha256": static["decisionSha256"],
        "finalSourceStateSha256": static["stateSha256"],
    }
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
    return {
        "deviceSucceeded": device_succeeded,
        "failureClass": result.get("failureClass"),
        "receiptPath": receipt_path,
        "bindingPath": binding_path,
        "resultPath": result_path,
        "receiptSha256": sha256(receipt_path),
        "bindingSha256": sha256(binding_path),
        "resultSha256": sha256(result_path),
        "hapSha256": require_digest(receipt.get("hapSha256"), "Harmony HAP sha256"),
        "environmentIdentity": binding.get("environmentIdentity"),
        "performancePolicySha256": binding.get("performancePolicySha256"),
        "profileWorkloadSha256": binding.get("profileWorkloadSha256"),
        "smartperfSummarySha256": binding.get("smartperfSummarySha256"),
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
            "stageId": "harmony-device",
            "participantCompleted": True,
            "changedPaths": [],
            "unauthorizedPaths": [],
            "scopeValid": True,
            "oraclePass": device["deviceSucceeded"],
            "oracleReceiptSha256": device["resultSha256"],
            "workspaceSha256": static["subjectWorkspaceSha256"],
            "authority": "operator-owned-harmony-ui-oracle",
            "hapSha256": device["hapSha256"],
            "environmentIdentity": device["environmentIdentity"],
        }
        phases = [*static["phases"], phase]
        verdict = device["deviceSucceeded"]
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
            "harmonyEvaluationBindingSha256": device["bindingSha256"],
            "harmonyResultSha256": device["resultSha256"],
            "performancePolicySha256": device["performancePolicySha256"],
            "profileWorkloadSha256": device["profileWorkloadSha256"],
            "smartperfSummarySha256": device["smartperfSummarySha256"],
            "assessmentBoundary": "Static frozen Oracle plus exact assessed-workspace Harmony HAP and operator-owned emulator UI Oracle; absolute device power and thermal remain unavailable.",
        }
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
                "harmonyEvaluationBindingSha256": device["bindingSha256"],
                "harmonyResultSha256": device["resultSha256"],
            },
            "automaticPromotion": False,
            "harnessPolicy": "Static scope/Oracle and device UI Oracle are independent verdict gates; infrastructure failure is never converted to Agent failure.",
        }
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
