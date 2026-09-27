#!/usr/bin/env python3
"""Independently review a calibrated purchase-data Oracle candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


PLAN_SCHEMA = "agentlab.purchase_data_behavior_oracle_plan.v1"
CALIBRATION_SCHEMA = "agentlab.purchase_data_behavior_oracle_calibration.v1"
SEMANTIC_GATE_SCHEMA = "agentlab.multi_repo_candidate_semantic_gate.v1"
ANSWERS_SCHEMA = "agentlab.purchase_data_behavior_oracle_review_answers.v1"
DECISION_SCHEMA = "agentlab.purchase_data_behavior_oracle_review.v1"
GATE_SCHEMA = "agentlab.purchase_data_behavior_oracle_gate.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[A-Za-z0-9_.:@/-]{1,200}")
ANSWERS = {"yes", "no", "unknown"}
VERDICTS = {
    "approve-for-runtime-calibration",
    "reject-oracle-candidate",
    "defer-for-more-evidence",
}
QUESTION_IDS = [
    "exact-lineage",
    "semantic-gate",
    "behavior-coverage",
    "negative-control-power",
    "boundary-honesty",
    "runtime-calibration-readiness",
]
RISK_IDS = [
    "selected-method-bodies-only",
    "stubbed-external-iap",
    "framework-and-emulator-unexecuted",
    "source-language-transformation",
    "semantic-and-oracle-review-separate",
]


class OracleReviewError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise OracleReviewError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OracleReviewError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_artifacts(
    plan_path: Path,
    calibration_path: Path,
    semantic_gate_path: Path,
    repository_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    plan = load(plan_path, "behavior Oracle plan")
    calibration = load(calibration_path, "behavior Oracle calibration")
    semantic = load(semantic_gate_path, "semantic gate")
    require(plan.get("schema") == PLAN_SCHEMA, "unsupported behavior Oracle plan")
    require(calibration.get("schema") == CALIBRATION_SCHEMA, "unsupported behavior Oracle calibration")
    require(semantic.get("schema") == SEMANTIC_GATE_SCHEMA, "unsupported semantic gate")
    require(REVISION.fullmatch(plan.get("methodRevision") or "") is not None, "method revision is invalid")
    require(calibration.get("methodRevision") == plan["methodRevision"], "calibration method revision differs")
    require(calibration.get("planSha256") == digest(plan_path), "calibration plan digest differs")
    for key in ("candidateId", "sourceSetSha256", "reviewPacketSha256", "controlFlowQualificationSha256", "seamExecutableSha256"):
        require(calibration.get(key) == plan.get(key), f"calibration {key} differs")
    require(
        semantic.get("status") == "approved-for-case-contract-proposal"
        and semantic.get("verdict") == "advance-to-case-contract"
        and semantic.get("allowsCaseContract") is True
        and semantic.get("automaticPromotion") is False,
        "semantic gate is not independently approved",
    )
    require(semantic.get("candidateId") == plan.get("candidateId"), "semantic gate candidate differs")
    require(semantic.get("sourceSetSha256") == plan.get("sourceSetSha256"), "semantic gate source set differs")
    require(semantic.get("packetSha256") == plan.get("reviewPacketSha256"), "semantic gate packet differs")
    semantic_reviewer = semantic.get("reviewer")
    require(
        isinstance(semantic_reviewer, str)
        and semantic_reviewer.startswith("github:")
        and TOKEN.fullmatch(semantic_reviewer) is not None,
        "semantic reviewer identity is invalid",
    )

    seam = repository_root.resolve() / "scripts/purchase-data-behavior-seam.js"
    require(seam.is_file() and not seam.is_symlink(), "behavior seam executable is unavailable")
    require(digest(seam) == plan.get("seamExecutableSha256"), "behavior seam executable digest differs")
    require(calibration.get("status") == "source-seam-calibrated-independent-review-required", "calibration status differs")
    require(calibration.get("sourceSeamCalibrated") is True, "source seam is not calibrated")
    require(calibration.get("semanticAlignmentVerified") is False, "calibration self-approves semantics")
    require(calibration.get("behaviorOracleVerified") is False, "calibration self-approves the Oracle")
    require(calibration.get("allowsCaseContract") is False, "calibration allows a case contract")
    require(calibration.get("automaticPromotion") is False, "calibration can auto-promote")

    repositories = plan.get("repositories")
    methods = plan.get("methods")
    evidence = calibration.get("methodEvidence")
    require(isinstance(repositories, list) and len(repositories) == 2, "repository coverage differs")
    require(isinstance(methods, list) and len(methods) == 5, "method inventory differs")
    require(isinstance(evidence, list) and len(evidence) == len(methods), "method evidence differs")
    planned_methods = {row.get("id"): row for row in methods if isinstance(row, dict)}
    observed_methods = {row.get("id"): row for row in evidence if isinstance(row, dict)}
    require(set(planned_methods) == set(observed_methods) and len(planned_methods) == 5, "method identities differ")
    for method_id, row in planned_methods.items():
        observed = observed_methods[method_id]
        for key in ("runtime", "repositoryId", "path", "methodSha256", "bodySha256"):
            require(observed.get(key) == row.get(key), f"method evidence differs: {method_id}/{key}")

    checks = plan.get("checks")
    observed_checks = calibration.get("checks")
    require(isinstance(checks, list) and len(checks) == 10 and observed_checks == checks, "behavior check inventory differs")
    check_ids = [row.get("id") for row in checks if isinstance(row, dict)]
    require(len(check_ids) == len(set(check_ids)) == 10, "behavior check ids differ")
    variants = plan.get("variants")
    observed_variants = calibration.get("variants")
    require(isinstance(variants, list) and len(variants) == 6, "planned variants differ")
    require(isinstance(observed_variants, list) and len(observed_variants) == len(variants), "calibrated variants differ")
    planned_by_id = {row.get("id"): row for row in variants if isinstance(row, dict)}
    observed_by_id = {row.get("id"): row for row in observed_variants if isinstance(row, dict)}
    require(set(planned_by_id) == set(observed_by_id) and len(planned_by_id) == 6, "variant identities differ")
    exact_count = 0
    negative_count = 0
    for variant_id, planned in planned_by_id.items():
        observed = observed_by_id[variant_id]
        require(observed.get("role") == planned.get("role"), f"variant role differs: {variant_id}")
        require(
            sorted(observed.get("expectedFailedChecks") or [])
            == sorted(planned.get("expectedFailedChecks") or []),
            f"variant expectation differs: {variant_id}",
        )
        require(observed.get("expectationMatched") is True, f"variant expectation did not match: {variant_id}")
        observed_failed = observed.get("observedFailedChecks")
        require(isinstance(observed_failed, list), f"variant failures are absent: {variant_id}")
        observed_check_map = observed.get("checks")
        require(
            isinstance(observed_check_map, dict)
            and set(observed_check_map) == set(check_ids)
            and all(isinstance(value, bool) for value in observed_check_map.values()),
            f"variant check results differ: {variant_id}",
        )
        if planned.get("role") == "exact-source":
            exact_count += 1
            require(not observed_failed and all(observed_check_map.values()), "exact source failed behavior checks")
        else:
            negative_count += 1
            require(planned.get("role") == "meaningful-wrong" and observed_failed, f"negative control was not detected: {variant_id}")
    require(exact_count == 1 and negative_count == 5, "calibration variant roles differ")
    coverage = calibration.get("coverage") or {}
    require(
        coverage
        == {
            "repositoryCount": 2,
            "methodCount": 5,
            "checkCount": 10,
            "negativeControlCount": 5,
            "undetectedNegativeControlCount": 0,
            "exactSourceAllChecksPassed": True,
            "allNegativeControlsDetected": True,
        },
        "calibration coverage summary differs",
    )
    boundary = calibration.get("qualificationBoundary")
    require(boundary == plan.get("qualificationBoundary"), "qualification boundary differs")
    require(
        isinstance(boundary, dict)
        and boundary.get("realSourceMethodsExecuted") is True
        and boundary.get("selectedMethodBodiesOnly") is True
        and boundary.get("externalIapApisStubbed") is True
        and boundary.get("frameworkLifecycleExecuted") is False
        and boundary.get("harmonyCompilerExecuted") is False
        and boundary.get("wholeApplicationExecuted") is False
        and boundary.get("emulatorExecuted") is False
        and boundary.get("semanticAlignmentApproved") is False
        and boundary.get("independentOracleReviewCompleted") is False,
        "qualification boundary overclaims execution",
    )
    return plan, calibration, semantic


def normalize_answers(value: dict[str, Any]) -> list[dict[str, str]]:
    require(value.get("schema") == ANSWERS_SCHEMA, "unsupported Oracle review answers")
    responses = value.get("responses")
    require(isinstance(responses, list), "Oracle review responses must be a list")
    normalized = []
    for row in responses:
        require(isinstance(row, dict) and set(row) == {"id", "answer", "rationale"}, "Oracle answer fields differ")
        question_id = row.get("id")
        answer = row.get("answer")
        rationale = row.get("rationale")
        require(question_id in QUESTION_IDS, "Oracle answer id is invalid")
        require(answer in ANSWERS, f"Oracle answer is invalid: {question_id}")
        require(isinstance(rationale, str) and 20 <= len(rationale.strip()) <= 2000, f"Oracle rationale is invalid: {question_id}")
        normalized.append({"id": question_id, "answer": answer, "rationale": rationale.strip()})
    normalized.sort(key=lambda row: row["id"])
    require([row["id"] for row in normalized] == sorted(QUESTION_IDS), "Oracle answers must cover every question exactly")
    return normalized


def validate_verdict(verdict: str, responses: list[dict[str, str]]) -> None:
    require(verdict in VERDICTS, "Oracle review verdict is invalid")
    answers = {row["answer"] for row in responses}
    if verdict == "approve-for-runtime-calibration":
        require(answers == {"yes"}, "approval requires every Oracle answer to be yes")
    elif verdict == "reject-oracle-candidate":
        require("no" in answers, "rejection requires at least one no answer")
    else:
        require("unknown" in answers and "no" not in answers, "deferral requires unknown answers and no rejection")


def decide(
    plan_path: Path,
    calibration_path: Path,
    semantic_gate_path: Path,
    repository_root: Path,
    expected_plan_sha256: str,
    expected_calibration_sha256: str,
    answers_path: Path,
    reviewer: str,
    acknowledged_risk_ids: str,
    verdict: str,
    rationale: str,
) -> dict[str, Any]:
    plan, calibration, semantic = validate_artifacts(plan_path, calibration_path, semantic_gate_path, repository_root)
    require(SHA256.fullmatch(expected_plan_sha256 or "") is not None and digest(plan_path) == expected_plan_sha256, "expected plan digest differs")
    require(SHA256.fullmatch(expected_calibration_sha256 or "") is not None and digest(calibration_path) == expected_calibration_sha256, "expected calibration digest differs")
    reviewer = reviewer.strip()
    require(reviewer.startswith("github:") and TOKEN.fullmatch(reviewer) is not None, "Oracle reviewer identity is invalid")
    require(reviewer != semantic["reviewer"], "Oracle reviewer must differ from semantic reviewer")
    rationale = rationale.strip()
    require(20 <= len(rationale) <= 2000, "Oracle decision rationale is invalid")
    responses = normalize_answers(load(answers_path, "Oracle review answers"))
    validate_verdict(verdict, responses)
    acknowledged = sorted({value.strip() for value in acknowledged_risk_ids.split(",") if value.strip()})
    require(acknowledged == sorted(RISK_IDS), "Oracle review must acknowledge every risk exactly")
    return {
        "schema": DECISION_SCHEMA,
        "candidateId": plan["candidateId"],
        "sourceSetSha256": plan["sourceSetSha256"],
        "planSha256": expected_plan_sha256,
        "calibrationSha256": expected_calibration_sha256,
        "semanticGateSha256": digest(semantic_gate_path),
        "methodRevision": plan["methodRevision"],
        "semanticReviewer": semantic["reviewer"],
        "oracleReviewer": reviewer,
        "responses": responses,
        "acknowledgedRiskIds": acknowledged,
        "verdict": verdict,
        "rationale": rationale,
        "allowsRuntimeCalibration": verdict == "approve-for-runtime-calibration",
        "allowsCaseContract": False,
        "automaticPromotion": False,
    }


def compile_gate(
    plan_path: Path,
    calibration_path: Path,
    semantic_gate_path: Path,
    decision_path: Path,
    repository_root: Path,
) -> dict[str, Any]:
    plan, _, semantic = validate_artifacts(plan_path, calibration_path, semantic_gate_path, repository_root)
    decision = load(decision_path, "Oracle review decision")
    require(decision.get("schema") == DECISION_SCHEMA, "unsupported Oracle review decision")
    require(decision.get("candidateId") == plan.get("candidateId"), "Oracle decision candidate differs")
    require(decision.get("sourceSetSha256") == plan.get("sourceSetSha256"), "Oracle decision source set differs")
    require(decision.get("planSha256") == digest(plan_path), "Oracle decision plan differs")
    require(decision.get("calibrationSha256") == digest(calibration_path), "Oracle decision calibration differs")
    require(decision.get("semanticGateSha256") == digest(semantic_gate_path), "Oracle decision semantic gate differs")
    require(decision.get("methodRevision") == plan.get("methodRevision"), "Oracle decision method revision differs")
    require(decision.get("semanticReviewer") == semantic.get("reviewer"), "semantic reviewer identity differs")
    oracle_reviewer = decision.get("oracleReviewer")
    require(
        isinstance(oracle_reviewer, str)
        and oracle_reviewer.startswith("github:")
        and TOKEN.fullmatch(oracle_reviewer) is not None
        and oracle_reviewer != semantic.get("reviewer"),
        "Oracle reviewer is not independently identified",
    )
    responses = normalize_answers({"schema": ANSWERS_SCHEMA, "responses": decision.get("responses")})
    require(responses == decision.get("responses"), "Oracle responses are not normalized")
    verdict = decision.get("verdict")
    validate_verdict(verdict, responses)
    require(decision.get("acknowledgedRiskIds") == sorted(RISK_IDS), "Oracle decision risk acknowledgements differ")
    approved = verdict == "approve-for-runtime-calibration"
    require(decision.get("allowsRuntimeCalibration") is approved, "runtime-calibration authority differs")
    require(decision.get("allowsCaseContract") is False, "Oracle decision allows a case contract")
    require(decision.get("automaticPromotion") is False, "Oracle decision can auto-promote")
    statuses = {
        "approve-for-runtime-calibration": "approved-for-runtime-calibration",
        "reject-oracle-candidate": "rejected-oracle-candidate",
        "defer-for-more-evidence": "deferred-for-more-evidence",
    }
    return {
        "schema": GATE_SCHEMA,
        "status": statuses[verdict],
        "candidateId": plan["candidateId"],
        "sourceSetSha256": plan["sourceSetSha256"],
        "methodRevision": plan["methodRevision"],
        "planSha256": digest(plan_path),
        "calibrationSha256": digest(calibration_path),
        "semanticGateSha256": digest(semantic_gate_path),
        "decisionSha256": digest(decision_path),
        "semanticReviewer": semantic["reviewer"],
        "oracleReviewer": oracle_reviewer,
        "verdict": verdict,
        "semanticAlignmentVerified": True,
        "behaviorOracleCandidateReviewed": approved,
        "behaviorOracleVerified": False,
        "allowsRuntimeCalibration": approved,
        "allowsCaseContract": False,
        "automaticPromotion": False,
        "nextGate": (
            "runtime-calibration-and-independent-runtime-oracle-validation"
            if approved
            else "none-rejected"
            if verdict == "reject-oracle-candidate"
            else "additional-oracle-evidence"
        ),
    }


def write(path: Path, value: dict[str, Any]) -> None:
    require(not path.exists(), f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("decide", "compile", "validate"):
        command = commands.add_parser(name)
        command.add_argument("--plan", type=Path, required=True)
        command.add_argument("--calibration", type=Path, required=True)
        command.add_argument("--semantic-gate", type=Path, required=True)
        command.add_argument("--repository-root", type=Path, required=True)
        if name == "decide":
            command.add_argument("--expected-plan-sha256", required=True)
            command.add_argument("--expected-calibration-sha256", required=True)
            command.add_argument("--answers", type=Path, required=True)
            command.add_argument("--reviewer", required=True)
            command.add_argument("--acknowledged-risk-ids", required=True)
            command.add_argument("--verdict", choices=sorted(VERDICTS), required=True)
            command.add_argument("--rationale", required=True)
            command.add_argument("--output", type=Path, required=True)
        else:
            command.add_argument("--decision", type=Path, required=True)
            if name == "compile":
                command.add_argument("--output", type=Path, required=True)
            else:
                command.add_argument("--gate", type=Path, required=True)
    args = parser.parse_args()
    try:
        common = (args.plan, args.calibration, args.semantic_gate)
        if args.command == "decide":
            value = decide(
                *common,
                args.repository_root,
                args.expected_plan_sha256,
                args.expected_calibration_sha256,
                args.answers,
                args.reviewer,
                args.acknowledged_risk_ids,
                args.verdict,
                args.rationale,
            )
            write(args.output, value)
            result = {"ok": True, "decisionSha256": digest(args.output), "verdict": value["verdict"]}
        else:
            value = compile_gate(*common, args.decision, args.repository_root)
            if args.command == "compile":
                write(args.output, value)
                result = {"ok": True, "gateSha256": digest(args.output), "status": value["status"]}
            else:
                actual = load(args.gate, "Oracle review gate")
                require(actual == value, "Oracle review gate differs from exact inputs and decision")
                result = {"ok": True, "gateSha256": digest(args.gate), "status": actual["status"]}
        print(json.dumps(result, sort_keys=True))
    except (OracleReviewError, OSError, json.JSONDecodeError) as error:
        print(f"purchase-data behavior Oracle review invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
