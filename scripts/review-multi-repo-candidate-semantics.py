#!/usr/bin/env python3
"""Record and compile an exact semantic decision for a candidate review packet."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[A-Za-z0-9_.:@/-]{1,200}")
PACKET_SCHEMA = "agentlab.multi_repo_candidate_review_packet.v1"
PACKET_SCHEMA_V2 = "agentlab.multi_repo_candidate_review_packet.v2"
PACKET_SCHEMA_V3 = "agentlab.multi_repo_candidate_review_packet.v3"
PACKET_SCHEMA_V4 = "agentlab.multi_repo_candidate_review_packet.v4"
PACKET_SCHEMAS = {PACKET_SCHEMA, PACKET_SCHEMA_V2, PACKET_SCHEMA_V3, PACKET_SCHEMA_V4}
ANSWERS_SCHEMA = "agentlab.multi_repo_candidate_semantic_answers.v1"
DECISION_SCHEMA = "agentlab.multi_repo_candidate_semantic_review.v1"
GATE_SCHEMA = "agentlab.multi_repo_candidate_semantic_gate.v1"
ANSWERS = {"yes", "no", "unknown"}
VERDICTS = {
    "advance-to-case-contract",
    "reject-as-noncoherent",
    "defer-for-more-evidence",
}


class SemanticReviewError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise SemanticReviewError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SemanticReviewError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_packet(packet: dict[str, Any]) -> None:
    require(packet.get("schema") in PACKET_SCHEMAS, "unsupported candidate review packet")
    if packet.get("schema") in {PACKET_SCHEMA_V2, PACKET_SCHEMA_V3, PACKET_SCHEMA_V4}:
        handle_evidence = packet.get("callResultHandleEvidence")
        handle_coverage = packet.get("callResultHandleCoverage")
        require(isinstance(handle_evidence, list), "v2 call-result handle evidence is absent")
        require(isinstance(handle_coverage, dict), "v2 call-result handle coverage is absent")
        require(
            handle_coverage.get("selectedCallCount") == len(handle_evidence) > 0,
            "v2 call-result handle evidence count differs",
        )
    if packet.get("schema") in {PACKET_SCHEMA_V3, PACKET_SCHEMA_V4}:
        control_evidence = packet.get("callControlContextEvidence")
        control_coverage = packet.get("callControlContextCoverage")
        require(isinstance(control_evidence, list), "v3 call-control evidence is absent")
        require(isinstance(control_coverage, dict), "v3 call-control coverage is absent")
        require(
            control_coverage.get("selectedCallCount") == len(control_evidence) > 0,
            "v3 call-control evidence count differs",
        )
    if packet.get("schema") == PACKET_SCHEMA_V4:
        cleanup_evidence = packet.get("callCleanupPairingEvidence")
        cleanup_coverage = packet.get("callCleanupPairingCoverage")
        require(isinstance(cleanup_evidence, list), "v4 cleanup-pairing evidence is absent")
        require(isinstance(cleanup_coverage, dict), "v4 cleanup-pairing coverage is absent")
        require(
            cleanup_coverage.get("selectedCallCount") == len(cleanup_evidence) > 0,
            "v4 cleanup-pairing evidence count differs",
        )
        require(
            cleanup_coverage.get("directReleaseCount")
            == sum(len(row.get("releasePairings") or []) for row in cleanup_evidence),
            "v4 cleanup-pairing release count differs",
        )
    require(
        packet.get("status") == "independent-semantic-review-required",
        "candidate packet is not awaiting semantic review",
    )
    require(packet.get("automaticPromotion") is False, "candidate packet can auto-promote")
    candidate_id = packet.get("candidateId")
    require(isinstance(candidate_id, str) and TOKEN.fullmatch(candidate_id), "candidate id is invalid")
    method_revision = packet.get("packetMethodRevision")
    require(
        isinstance(method_revision, str) and REVISION.fullmatch(method_revision),
        "packet method revision is invalid",
    )
    contract = packet.get("reviewDecisionContract")
    require(isinstance(contract, dict), "packet review decision contract is absent")
    require(contract.get("schema") == DECISION_SCHEMA, "packet decision schema differs")
    require(set(contract.get("allowedVerdicts") or []) == VERDICTS, "packet verdict set differs")
    questions = packet.get("reviewQuestions")
    require(isinstance(questions, list) and questions, "packet review questions are absent")
    question_ids = [row.get("id") for row in questions if isinstance(row, dict)]
    require(
        len(question_ids) == len(questions) == len(set(question_ids))
        and all(isinstance(value, str) and TOKEN.fullmatch(value) for value in question_ids),
        "packet question ids are invalid",
    )
    require(contract.get("requiredQuestionIds") == question_ids, "packet required questions differ")
    risks = packet.get("risks")
    require(isinstance(risks, list) and risks, "packet risks are absent")
    risk_ids = [row.get("id") for row in risks if isinstance(row, dict)]
    require(
        len(risk_ids) == len(risks) == len(set(risk_ids))
        and all(isinstance(value, str) and TOKEN.fullmatch(value) for value in risk_ids),
        "packet risk ids are invalid",
    )
    require(contract.get("requiredRiskIds") == risk_ids, "packet required risks differ")
    require(
        contract.get("reviewerMustBeIndependentOfPacketGenerator") is True,
        "packet does not require reviewer independence",
    )


def normalize_answers(answers: dict[str, Any], required_ids: list[str]) -> list[dict[str, str]]:
    require(answers.get("schema") == ANSWERS_SCHEMA, "unsupported semantic answers schema")
    responses = answers.get("responses")
    require(isinstance(responses, list), "semantic answers responses must be a list")
    normalized = []
    for row in responses:
        require(isinstance(row, dict) and set(row) == {"id", "answer", "rationale"}, "semantic answer fields differ")
        question_id = row.get("id")
        answer = row.get("answer")
        rationale = row.get("rationale")
        require(isinstance(question_id, str) and TOKEN.fullmatch(question_id), "semantic answer id is invalid")
        require(answer in ANSWERS, f"semantic answer is invalid for {question_id}")
        require(
            isinstance(rationale, str) and 20 <= len(rationale.strip()) <= 2000,
            f"semantic answer rationale is invalid for {question_id}",
        )
        normalized.append({"id": question_id, "answer": answer, "rationale": rationale.strip()})
    normalized.sort(key=lambda row: row["id"])
    require(
        [row["id"] for row in normalized] == sorted(required_ids),
        "semantic answers must cover every required question exactly",
    )
    return normalized


def validate_verdict(verdict: str, responses: list[dict[str, str]]) -> None:
    require(verdict in VERDICTS, "semantic review verdict is invalid")
    by_id = {row["id"]: row["answer"] for row in responses}
    values = set(by_id.values())
    if verdict == "advance-to-case-contract":
        require(values == {"yes"}, "advance verdict requires every semantic answer to be yes")
    elif verdict == "reject-as-noncoherent":
        require("no" in values, "reject verdict requires at least one no answer")
    else:
        require("unknown" in values, "defer verdict requires at least one unknown answer")
        require(
            by_id.get("shared-behavior") != "no" and by_id.get("cross-repo-necessity") != "no",
            "noncoherent shared behavior or cross-repository necessity must be rejected, not deferred",
        )


def decide(
    packet_path: Path,
    expected_sha256: str,
    answers_path: Path,
    reviewer: str,
    acknowledged_risk_ids: str,
    verdict: str,
    rationale: str,
) -> dict[str, Any]:
    packet = load(packet_path, "candidate review packet")
    validate_packet(packet)
    require(SHA256.fullmatch(expected_sha256) is not None, "expected packet digest is invalid")
    require(digest(packet_path) == expected_sha256, "candidate packet digest differs")
    reviewer = reviewer.strip()
    require(reviewer.startswith("github:") and TOKEN.fullmatch(reviewer), "reviewer must be a GitHub actor identity")
    generator = f"git:{packet['packetMethodRevision']}"
    require(reviewer != generator, "semantic reviewer is not independent of packet generator")
    rationale = rationale.strip()
    require(20 <= len(rationale) <= 2000, "semantic decision rationale is invalid")
    required_questions = packet["reviewDecisionContract"]["requiredQuestionIds"]
    responses = normalize_answers(load(answers_path, "semantic answers"), required_questions)
    validate_verdict(verdict, responses)
    acknowledged = sorted({value.strip() for value in acknowledged_risk_ids.split(",") if value.strip()})
    require(
        acknowledged == sorted(packet["reviewDecisionContract"]["requiredRiskIds"]),
        "semantic review must acknowledge every packet risk exactly",
    )
    return {
        "schema": DECISION_SCHEMA,
        "candidateId": packet["candidateId"],
        "packetSha256": expected_sha256,
        "packetGenerator": generator,
        "reviewer": reviewer,
        "responses": responses,
        "acknowledgedRiskIds": acknowledged,
        "verdict": verdict,
        "rationale": rationale,
        "allowsCaseContract": verdict == "advance-to-case-contract",
        "automaticPromotion": False,
    }


def compile_gate(packet_path: Path, decision_path: Path) -> dict[str, Any]:
    packet = load(packet_path, "candidate review packet")
    decision = load(decision_path, "candidate semantic decision")
    validate_packet(packet)
    require(decision.get("schema") == DECISION_SCHEMA, "unsupported candidate semantic decision")
    require(decision.get("packetSha256") == digest(packet_path), "semantic decision packet digest differs")
    require(decision.get("candidateId") == packet.get("candidateId"), "semantic decision candidate differs")
    require(decision.get("packetGenerator") == f"git:{packet['packetMethodRevision']}", "packet generator identity differs")
    reviewer = decision.get("reviewer")
    require(isinstance(reviewer, str) and reviewer.startswith("github:") and TOKEN.fullmatch(reviewer), "semantic reviewer is invalid")
    require(reviewer != decision["packetGenerator"], "semantic reviewer is not independent")
    responses = decision.get("responses")
    require(isinstance(responses, list), "semantic decision responses are absent")
    normalized = normalize_answers(
        {"schema": ANSWERS_SCHEMA, "responses": responses},
        packet["reviewDecisionContract"]["requiredQuestionIds"],
    )
    require(responses == normalized, "semantic decision responses are not normalized")
    verdict = decision.get("verdict")
    validate_verdict(verdict, responses)
    require(
        decision.get("allowsCaseContract") is (verdict == "advance-to-case-contract"),
        "semantic decision case-contract authority differs",
    )
    require(
        decision.get("acknowledgedRiskIds")
        == sorted(packet["reviewDecisionContract"]["requiredRiskIds"]),
        "semantic decision risk acknowledgements differ",
    )
    require(decision.get("automaticPromotion") is False, "semantic decision can auto-promote")
    statuses = {
        "advance-to-case-contract": "approved-for-case-contract-proposal",
        "reject-as-noncoherent": "rejected-as-noncoherent",
        "defer-for-more-evidence": "deferred-for-more-evidence",
    }
    return {
        "schema": GATE_SCHEMA,
        "status": statuses[verdict],
        "candidateId": packet["candidateId"],
        "candidateSha256": packet["candidateSha256"],
        "sourceSetSha256": packet["sourceSetSha256"],
        "packetMethodRevision": packet["packetMethodRevision"],
        "packetSha256": digest(packet_path),
        "decisionSha256": digest(decision_path),
        "reviewer": reviewer,
        "verdict": verdict,
        "responses": responses,
        "allowsCaseContract": verdict == "advance-to-case-contract",
        "declaredRepresentative": False,
        "automaticPromotion": False,
    }


def validate_gate(packet_path: Path, decision_path: Path, gate_path: Path) -> dict[str, Any]:
    actual = load(gate_path, "candidate semantic gate")
    expected = compile_gate(packet_path, decision_path)
    require(actual == expected, "candidate semantic gate differs from exact packet and decision")
    return actual


def write(path: Path, value: dict[str, Any]) -> None:
    require(not path.exists(), f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    decision = commands.add_parser("decide")
    decision.add_argument("--packet", type=Path, required=True)
    decision.add_argument("--expected-sha256", required=True)
    decision.add_argument("--answers", type=Path, required=True)
    decision.add_argument("--reviewer", required=True)
    decision.add_argument("--acknowledged-risk-ids", required=True)
    decision.add_argument("--verdict", choices=sorted(VERDICTS), required=True)
    decision.add_argument("--rationale", required=True)
    decision.add_argument("--output", type=Path, required=True)
    compile_command = commands.add_parser("compile")
    compile_command.add_argument("--packet", type=Path, required=True)
    compile_command.add_argument("--decision", type=Path, required=True)
    compile_command.add_argument("--output", type=Path, required=True)
    validate_command = commands.add_parser("validate")
    validate_command.add_argument("--packet", type=Path, required=True)
    validate_command.add_argument("--decision", type=Path, required=True)
    validate_command.add_argument("--gate", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "decide":
            value = decide(
                args.packet, args.expected_sha256, args.answers, args.reviewer,
                args.acknowledged_risk_ids, args.verdict, args.rationale,
            )
            write(args.output, value)
            result = {"ok": True, "decisionSha256": digest(args.output), "verdict": value["verdict"]}
        elif args.command == "compile":
            value = compile_gate(args.packet, args.decision)
            write(args.output, value)
            result = {"ok": True, "gateSha256": digest(args.output), "status": value["status"]}
        else:
            value = validate_gate(args.packet, args.decision, args.gate)
            result = {"ok": True, "gateSha256": digest(args.gate), "status": value["status"]}
        print(json.dumps(result, sort_keys=True))
    except (SemanticReviewError, OSError, json.JSONDecodeError) as error:
        print(f"candidate semantic review invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
