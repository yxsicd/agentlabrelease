#!/usr/bin/env python3
"""Bind later exact evidence into a v6 independent semantic-review packet."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "agentlab.multi_repo_candidate_review_packet.v6"
BASE_SCHEMA = "agentlab.multi_repo_candidate_review_packet.v5"
BUILD_SCHEMA = "agentlab.multi_repo_source_build_qualification.v1"
EXPRESSION_SCHEMA = "agentlab.multi_repo_expression_fact_qualification.v1"
FLOW_SCHEMA = "agentlab.bounded_expression_flow_proposal.v1"
DECISION_SCHEMA = "agentlab.multi_repo_candidate_semantic_review.v1"
REVISION = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")


class PacketEnrichmentError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise PacketEnrichmentError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PacketEnrichmentError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_reference(path: Path, evidence_root: Path, label: str) -> str:
    root = evidence_root.resolve()
    require(root.is_dir(), "evidence root must be a directory")
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise PacketEnrichmentError(f"{label} is outside evidence root") from error
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    require(all(part not in ("", ".", "..") for part in relative.parts), f"{label} path is unsafe")
    return relative.as_posix()


def common_lineage(value: dict[str, Any], schema: str, base: dict[str, Any], base_sha256: str, label: str) -> None:
    require(value.get("schema") == schema, f"unsupported {label} schema")
    require(value.get("candidateId") == base.get("candidateId"), f"{label} candidate differs")
    require(value.get("sourceSetSha256") == base.get("sourceSetSha256"), f"{label} source set differs")
    require(value.get("reviewPacketSha256") == base_sha256, f"{label} base packet digest differs")
    require(value.get("allowsCaseContract") is False, f"{label} allows a case contract")
    require(value.get("automaticPromotion") is False, f"{label} can auto-promote")


def enrich(
    base_path: Path,
    build_path: Path,
    expression_path: Path,
    flow_plan_path: Path,
    flow_path: Path,
    method_revision: str,
    evidence_root: Path,
) -> dict[str, Any]:
    base = load(base_path, "base review packet")
    build = load(build_path, "build qualification")
    expression = load(expression_path, "expression qualification")
    flow_plan = load(flow_plan_path, "bounded flow plan")
    flow = load(flow_path, "bounded flow proposal")
    require(base.get("schema") == BASE_SCHEMA, "base packet is not v5")
    require(base.get("status") == "independent-semantic-review-required", "base packet is not review-required")
    require(base.get("allowsCaseContract") is not True and base.get("automaticPromotion") is False, "base packet can promote")
    require(REVISION.fullmatch(method_revision) is not None, "packet method revision is invalid")
    require(SHA256.fullmatch(base.get("candidateSha256", "")) is not None, "base candidate digest is invalid")
    references = {
        "base": relative_reference(base_path, evidence_root, "base review packet"),
        "build": relative_reference(build_path, evidence_root, "build qualification"),
        "expression": relative_reference(expression_path, evidence_root, "expression qualification"),
        "flowPlan": relative_reference(flow_plan_path, evidence_root, "bounded flow plan"),
        "flow": relative_reference(flow_path, evidence_root, "bounded flow proposal"),
    }
    base_sha256 = digest(base_path)
    common_lineage(build, BUILD_SCHEMA, base, base_sha256, "build qualification")
    common_lineage(expression, EXPRESSION_SCHEMA, base, base_sha256, "expression qualification")
    common_lineage(flow, FLOW_SCHEMA, base, base_sha256, "bounded flow proposal")

    roots = build.get("roots")
    require(isinstance(roots, list) and roots, "build roots are absent")
    qualified_root_count = sum(row.get("status") == "passed" for row in roots if isinstance(row, dict))
    failed_root_count = sum(row.get("status") == "failed" for row in roots if isinstance(row, dict))
    interpretation = build.get("interpretation") or {}
    require(build.get("status") == "partial-build-qualified-review-required", "build status differs")
    require(interpretation.get("qualifiedRootCount") == qualified_root_count == 1, "qualified build-root count differs")
    require(interpretation.get("failedRootCount") == failed_root_count == 2, "failed build-root count differs")
    require(interpretation.get("sourceProjectBoundaryStatus") == "partially-build-qualified", "build boundary status differs")

    require(expression.get("status") == "expression-facts-qualified-dataflow-unresolved", "expression status differs")
    require(expression.get("repositoryCount") == 2, "expression repository count differs")
    require(expression.get("selectedExpressionFactCount", 0) > 0, "expression facts are absent")
    require(expression.get("semanticAlignmentVerified") is False, "expression qualification claims semantics")

    require(flow_plan.get("schema") == "agentlab.bounded_expression_flow_plan.v1", "unsupported bounded flow plan")
    require(flow_plan.get("candidateId") == base.get("candidateId"), "flow plan candidate differs")
    require(flow_plan.get("sourceSetSha256") == base.get("sourceSetSha256"), "flow plan source set differs")
    require(flow.get("planSha256") == digest(flow_plan_path), "flow plan digest differs")
    require(flow.get("status") == "bounded-syntactic-flow-proposal-review-required", "flow status differs")
    require(flow.get("repositoryCount") == flow.get("flowCount") == 2, "bounded flow coverage differs")
    require(flow.get("allBoundedPathsEstablished") is True, "bounded paths are incomplete")
    require(flow.get("sourceBridges") and isinstance(flow["sourceBridges"], list), "bounded flow bridge is absent")
    require(flow.get("semanticAlignmentVerified") is False, "flow proposal claims semantics")
    require(flow.get("behaviorOracleVerified") is False, "flow proposal claims an Oracle")
    edge_count = sum(row.get("edgeCount", 0) for row in flow.get("flows") or [] if isinstance(row, dict))
    require(edge_count > 0, "bounded flow edges are absent")

    domain_evidence = base.get("domainFactEvidence") or []
    require(isinstance(domain_evidence, list) and domain_evidence, "base domain evidence is absent")
    packet = {
        "schema": SCHEMA,
        "status": "independent-semantic-review-required",
        "candidateId": base.get("candidateId"),
        "candidateSha256": base.get("candidateSha256"),
        "sourceSetSha256": base.get("sourceSetSha256"),
        "packetMethodRevision": method_revision,
        "basePacket": {
            "schema": BASE_SCHEMA,
            "sha256": base_sha256,
            "relativePath": references["base"],
            "packetMethodRevision": base.get("packetMethodRevision"),
            "status": base.get("status"),
            "domainIdentifierContract": base.get("domainIdentifierContract"),
            "domainFactCount": len(domain_evidence),
            "coveredRepositoryCount": len({row.get("repositoryId") for row in domain_evidence if isinstance(row, dict)}),
        },
        "selectionRoles": base.get("selectionRoles"),
    }
    packet["evidenceAttachments"] = {
        "build-qualification": {
            "schema": BUILD_SCHEMA,
            "sha256": digest(build_path),
            "relativePath": references["build"],
            "status": build["status"],
            "environmentIdentity": (build.get("environment") or {}).get("environmentIdentity"),
            "qualifiedRootCount": qualified_root_count,
            "failedRootCount": failed_root_count,
            "sourceProjectBoundaryStatus": interpretation["sourceProjectBoundaryStatus"],
        },
        "expression-fact-qualification": {
            "schema": EXPRESSION_SCHEMA,
            "sha256": digest(expression_path),
            "relativePath": references["expression"],
            "status": expression["status"],
            "analyzerDigest": expression.get("analyzerDigest"),
            "grammarDigest": expression.get("grammarDigest"),
            "repositoryCount": expression["repositoryCount"],
            "selectedExpressionFactCount": expression["selectedExpressionFactCount"],
        },
        "bounded-expression-flow-proposal": {
            "schema": FLOW_SCHEMA,
            "sha256": digest(flow_path),
            "relativePath": references["flow"],
            "planSha256": flow["planSha256"],
            "planRelativePath": references["flowPlan"],
            "status": flow["status"],
            "repositoryCount": flow["repositoryCount"],
            "flowCount": flow["flowCount"],
            "edgeCount": edge_count,
            "sourceBridgeCount": len(flow["sourceBridges"]),
            "allBoundedPathsEstablished": True,
        },
    }
    packet["reviewQuestions"] = [
        {"id": "shared-behavior", "question": "Do the exact source facts and bounded paths express one coherent cross-repository purchase-data behavior rather than merely sharing an identifier?"},
        {"id": "observable-gap", "question": "Is there an issue-level defect or extension whose pre-change failure is observable in every required repository?"},
        {"id": "prompt-completeness", "question": "Can the participant-facing prompt state every required behavior without revealing the repair?"},
        {"id": "repair-oracle", "question": "Can independent FAIL_TO_PASS checks accept structurally distinct valid repairs?"},
        {"id": "preservation-oracle", "question": "Can independent PASS_TO_PASS checks cover existing repository-specific behavior?"},
        {"id": "environment", "question": "Do the passed Harmony build and the two explicit Cordova build-contract failures define a reproducible environment boundary for the proposed task?"},
        {"id": "cross-repo-necessity", "question": "Does the proposed behavior require coordinated multi-repository reasoning rather than two unrelated single-repository tasks?"},
    ]
    packet["risks"] = [
        {"id": "syntactic-flow-is-not-semantics", "statement": "Contiguous bounded expression paths do not establish compatible types, aliases, reachability, behavior or product intent."},
        {"id": "issue-contract-absent", "statement": "No participant-visible issue, repair behavior or preservation behavior has been approved."},
        {"id": "build-boundary-partially-qualified", "statement": "The Harmony root builds, but the Cordova package and Ionic example retain two exact upstream build-contract failures."},
        {"id": "oracle-unqualified", "statement": "No baseline, reference, alternative or meaningful-wrong calibration has executed for this candidate."},
    ]
    question_ids = [row["id"] for row in packet["reviewQuestions"]]
    risk_ids = [row["id"] for row in packet["risks"]]
    packet["reviewDecisionContract"] = {
        "schema": DECISION_SCHEMA,
        "allowedVerdicts": ["advance-to-case-contract", "defer-for-more-evidence", "reject-as-noncoherent"],
        "requiredQuestionIds": question_ids,
        "requiredRiskIds": risk_ids,
        "requiredEvidenceAttachmentIds": sorted(packet["evidenceAttachments"]),
        "reviewerMustBeIndependentOfPacketGenerator": True,
    }
    packet["semanticAlignmentVerified"] = False
    packet["behaviorOracleVerified"] = False
    packet["allowsCaseContract"] = False
    packet["automaticPromotion"] = False
    return packet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-packet", required=True, type=Path)
    parser.add_argument("--build-qualification", required=True, type=Path)
    parser.add_argument("--expression-qualification", required=True, type=Path)
    parser.add_argument("--flow-plan", required=True, type=Path)
    parser.add_argument("--flow-proposal", required=True, type=Path)
    parser.add_argument("--method-revision", required=True)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = enrich(
        args.base_packet,
        args.build_qualification,
        args.expression_qualification,
        args.flow_plan,
        args.flow_proposal,
        args.method_revision,
        args.evidence_root,
    )
    require(not args.output.exists(), "refusing to overwrite enriched review packet")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "status": result["status"], "attachmentCount": len(result["evidenceAttachments"])}, sort_keys=True))


if __name__ == "__main__":
    main()
