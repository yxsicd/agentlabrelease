#!/usr/bin/env python3
"""Bind case-source provenance and qualification state without conflating gates."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
LANES = {"natural", "derived"}
STRATEGIES = {
    "historical-repair",
    "operator-reported-failure",
    "semantic-program-analysis",
    "controlled-mutation",
    "participant-failure-feedback",
}


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def derived_program_analysis_source(
    *,
    candidate_id: str,
    source_set_sha256: str,
    difficulty_evidence_sha256: str,
    candidate_sha256: str,
) -> dict[str, Any]:
    """Build the source record for an analyzer-produced difficulty candidate."""
    value = {
        "schema": "agentlab.case_source.v1",
        "lane": "derived",
        "strategy": "semantic-program-analysis",
        "candidateId": candidate_id,
        "sourceSetSha256": source_set_sha256,
        "authority": "exact-difficulty-evidence",
        "evidence": {
            "difficultyEvidenceSha256": difficulty_evidence_sha256,
            "candidateSha256": candidate_sha256,
        },
        "naturalRepresentativenessClaimed": False,
        "automaticPromotion": False,
    }
    validate_case_source(value)
    return value


def validate_case_source(value: dict[str, Any]) -> dict[str, Any]:
    require(isinstance(value, dict), "case source must be an object")
    require(value.get("schema") == "agentlab.case_source.v1", "unsupported case source schema")
    lane = value.get("lane")
    strategy = value.get("strategy")
    require(lane in LANES, "case source lane is invalid")
    require(strategy in STRATEGIES, "case source strategy is invalid")
    if lane == "natural":
        require(
            strategy in {"historical-repair", "operator-reported-failure"},
            "natural case source strategy is invalid",
        )
    else:
        require(
            strategy in {
                "semantic-program-analysis",
                "controlled-mutation",
                "participant-failure-feedback",
            },
            "derived case source strategy is invalid",
        )
    require(isinstance(value.get("candidateId"), str) and value["candidateId"], "case source candidate is required")
    require(
        isinstance(value.get("sourceSetSha256"), str)
        and SHA256.fullmatch(value["sourceSetSha256"]),
        "case source source-set digest is invalid",
    )
    require(isinstance(value.get("authority"), str) and value["authority"], "case source authority is required")
    evidence = value.get("evidence")
    require(isinstance(evidence, dict) and evidence, "case source evidence is required")
    require(
        all(isinstance(digest, str) and SHA256.fullmatch(digest) for digest in evidence.values()),
        "case source evidence digests are invalid",
    )
    require(value.get("naturalRepresentativenessClaimed") is False, "case source cannot claim natural representativeness")
    require(value.get("automaticPromotion") is False, "case source cannot auto-promote")
    return value


def build_qualification_receipt(
    *,
    case_id: str,
    candidate_id: str,
    case_source: dict[str, Any],
    qualification_matrix: dict[str, Any],
    calibration_sha256: str,
) -> dict[str, Any]:
    validate_case_source(case_source)
    require(case_source["candidateId"] == candidate_id, "qualification source candidate differs")
    require(isinstance(calibration_sha256, str) and SHA256.fullmatch(calibration_sha256), "qualification calibration digest is invalid")
    review_qualified = (qualification_matrix.get("review") or {}).get("qualifiedForCalibration") is True
    value = {
        "schema": "agentlab.case_qualification_receipt.v1",
        "caseId": case_id,
        "candidateId": candidate_id,
        "caseSourceSha256": canonical_digest(case_source),
        "lane": case_source["lane"],
        "strategy": case_source["strategy"],
        "qualificationMatrixSha256": canonical_digest(qualification_matrix),
        "calibrationSha256": calibration_sha256,
        "gates": {
            "semanticReview": "qualified" if review_qualified else "legacy-unreviewed",
            "functionalCalibration": "qualified",
            "device": "pending-separate-gate",
            "performance": "pending-separate-gate",
            "freshness": "unqualified-unknown",
        },
        "functionalQualification": review_qualified,
        "endToEndQualification": False,
        "status": (
            "functional-qualified-end-to-end-pending"
            if review_qualified
            else "calibration-qualified-review-pending"
        ),
        "automaticPromotion": False,
    }
    validate_qualification_receipt(value, case_source, qualification_matrix, calibration_sha256)
    return value


def validate_qualification_receipt(
    receipt: dict[str, Any],
    case_source: dict[str, Any],
    qualification_matrix: dict[str, Any],
    calibration_sha256: str,
) -> dict[str, Any]:
    validate_case_source(case_source)
    require(isinstance(receipt, dict), "qualification receipt must be an object")
    require(receipt.get("schema") == "agentlab.case_qualification_receipt.v1", "unsupported qualification receipt schema")
    require(receipt.get("candidateId") == case_source["candidateId"], "qualification receipt candidate differs")
    require(receipt.get("lane") == case_source["lane"], "qualification receipt lane differs")
    require(receipt.get("strategy") == case_source["strategy"], "qualification receipt strategy differs")
    require(receipt.get("caseSourceSha256") == canonical_digest(case_source), "qualification receipt source digest differs")
    require(
        receipt.get("qualificationMatrixSha256") == canonical_digest(qualification_matrix),
        "qualification receipt matrix digest differs",
    )
    require(receipt.get("calibrationSha256") == calibration_sha256, "qualification receipt calibration digest differs")
    review_qualified = (qualification_matrix.get("review") or {}).get("qualifiedForCalibration") is True
    require(
        receipt.get("gates")
        == {
            "semanticReview": "qualified" if review_qualified else "legacy-unreviewed",
            "functionalCalibration": "qualified",
            "device": "pending-separate-gate",
            "performance": "pending-separate-gate",
            "freshness": "unqualified-unknown",
        },
        "qualification receipt gates differ",
    )
    require(receipt.get("functionalQualification") is review_qualified, "functional qualification differs from review gate")
    require(receipt.get("endToEndQualification") is False, "receipt overclaims end-to-end qualification")
    require(
        receipt.get("status")
        == (
            "functional-qualified-end-to-end-pending"
            if review_qualified
            else "calibration-qualified-review-pending"
        ),
        "qualification receipt status differs",
    )
    require(receipt.get("automaticPromotion") is False, "qualification receipt cannot auto-promote")
    return receipt


def validate_case_supply(case: dict[str, Any]) -> dict[str, Any]:
    require(case.get("schema") == "agentlab.multi_repo_evaluation_case.v1", "unsupported evaluation case schema")
    require(case.get("status") == "frozen-calibrated", "case is not frozen and calibrated")
    require(case.get("automaticPromotion") is False, "case can auto-promote")
    matrix = case.get("qualificationMatrix")
    require(isinstance(matrix, dict), "qualification matrix is required")
    require(matrix.get("schema") == "agentlab.case_qualification_matrix.v1", "unsupported qualification matrix schema")
    require(
        matrix.get("status") == "functional-calibration-qualified-runtime-and-freshness-pending",
        "qualification matrix status differs",
    )
    require(matrix.get("automaticPromotion") is False, "qualification matrix can auto-promote")
    require((case.get("calibration") or {}).get("qualified") is True, "case calibration is not qualified")
    source = validate_case_source(case.get("caseSource"))
    receipt = case.get("qualificationReceipt")
    calibration_sha256 = (case.get("calibration") or {}).get("summarySha256")
    validate_qualification_receipt(receipt, source, matrix, calibration_sha256)
    require(receipt.get("caseId") == case.get("id"), "qualification receipt case identity differs")
    require(receipt.get("candidateId") == case.get("difficultyId"), "qualification receipt difficulty identity differs")
    require(source.get("sourceSetSha256") == case.get("sourceSetSha256"), "case source set differs from case")
    return {
        "ok": True,
        "caseId": case["id"],
        "candidateId": case["difficultyId"],
        "lane": source["lane"],
        "strategy": source["strategy"],
        "functionalQualification": receipt["functionalQualification"],
        "endToEndQualification": False,
    }
