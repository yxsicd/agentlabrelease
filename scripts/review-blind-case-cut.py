#!/usr/bin/env python3
"""Create and validate independent multi-reviewer blind-case decisions."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any


REQUEST_SCHEMA = "agentlab.blind_case_review_request.v1"
DECISION_SCHEMA = "agentlab.blind_case_review_decision.v1"
ADJUDICATION_SCHEMA = "agentlab.blind_case_review_adjudication.v1"
DIMENSIONS = (
    "semanticLeakage",
    "contaminationRisk",
    "specificationFairness",
    "oracleBreadth",
)
VERDICTS = {"qualified", "rejected", "unknown"}
SHA256 = re.compile(r"[0-9a-f]{64}")
IDENTITY = re.compile(r"[A-Za-z0-9_.:@/-]{1,160}")


class BlindReviewError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise BlindReviewError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BlindReviewError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must contain an object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    require(not path.exists(), f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def safe_identity(value: str, label: str) -> str:
    require(isinstance(value, str), f"{label} is invalid")
    normalized = value.strip()
    require(IDENTITY.fullmatch(normalized) is not None, f"{label} is invalid")
    return normalized


def blind_module():
    module_path = Path(__file__).with_name("build-blind-case-cut.py")
    spec = importlib.util.spec_from_file_location("agentlab_blind_case_review_cut", module_path)
    require(spec is not None and spec.loader is not None, "blind cut validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_request(path: Path, cut_root: Path | None = None) -> dict[str, Any]:
    request = load(path, "blind review request")
    require(request.get("schema") == REQUEST_SCHEMA, "unsupported blind review request schema")
    require(request.get("status") == "review-required", "blind review request status differs")
    require(request.get("requiredDimensions") == list(DIMENSIONS), "blind review dimensions differ")
    require(request.get("modelTrainingExclusionKnown") is False, "review request overclaims model-training exclusion")
    require(request.get("automaticPromotion") is False, "blind review request cannot auto-promote")
    safe_identity(request.get("constructor", ""), "constructor identity")
    for field in (
        "cutReceiptSha256",
        "participantManifestSha256",
        "evaluatorManifestSha256",
        "sourceSetSha256",
    ):
        require(isinstance(request.get(field), str) and SHA256.fullmatch(request[field]), f"{field} is invalid")
    if cut_root is not None:
        cut_root = cut_root.resolve(strict=True)
        cut = blind_module().validate_cut(cut_root)
        require(request.get("cutId") == cut.get("cutId") and request.get("caseId") == cut.get("caseId"), "review request cut identity differs")
        require(request.get("sourceSetSha256") == cut.get("sourceSetSha256"), "review request source set differs")
        require(request.get("cutReceiptSha256") == digest(cut_root / "cut-receipt.json"), "review request cut receipt differs")
        require(request.get("participantManifestSha256") == digest(cut_root / "participant/manifest.json"), "review request participant manifest differs")
        require(request.get("evaluatorManifestSha256") == digest(cut_root / "evaluator/manifest.json"), "review request evaluator manifest differs")
    return request


def prepare_request(cut_root: Path, constructor: str, output: Path) -> dict[str, Any]:
    cut_root = cut_root.resolve(strict=True)
    cut = blind_module().validate_cut(cut_root)
    request = {
        "schema": REQUEST_SCHEMA,
        "cutId": cut["cutId"],
        "caseId": cut["caseId"],
        "sourceSetSha256": cut["sourceSetSha256"],
        "cutReceiptSha256": digest(cut_root / "cut-receipt.json"),
        "participantManifestSha256": digest(cut_root / "participant/manifest.json"),
        "evaluatorManifestSha256": digest(cut_root / "evaluator/manifest.json"),
        "constructor": safe_identity(constructor, "constructor identity"),
        "requiredDimensions": list(DIMENSIONS),
        "modelTrainingExclusionKnown": False,
        "status": "review-required",
        "automaticPromotion": False,
    }
    write_json(output, request)
    validate_request(output, cut_root)
    return request


def validate_decision(path: Path, request_path: Path) -> dict[str, Any]:
    request = validate_request(request_path)
    decision = load(path, "blind review decision")
    require(decision.get("schema") == DECISION_SCHEMA, "unsupported blind review decision schema")
    require(decision.get("requestSha256") == digest(request_path), "blind review decision request digest differs")
    reviewer = safe_identity(decision.get("reviewer", ""), "reviewer identity")
    require(reviewer != request.get("constructor"), "blind review must be independent from the constructor")
    verdicts = decision.get("verdicts")
    require(
        isinstance(verdicts, dict) and set(verdicts) == set(DIMENSIONS),
        "blind review verdict dimensions differ",
    )
    require(all(verdicts.get(field) in VERDICTS for field in DIMENSIONS), "blind review verdict is invalid")
    require(isinstance(decision.get("rationale"), str) and decision["rationale"].strip(), "blind review rationale is required")
    evidence = decision.get("evidenceSha256")
    require(isinstance(evidence, list) and evidence, "blind review evidence digests are required")
    require(evidence == sorted(set(evidence)), "blind review evidence digests must be unique and sorted")
    require(all(isinstance(value, str) and SHA256.fullmatch(value) for value in evidence), "blind review evidence digest is invalid")
    require(decision.get("modelTrainingExclusionQualified") is False, "review decision overclaims model-training exclusion")
    require(decision.get("automaticPromotion") is False, "blind review decision cannot auto-promote")
    return decision


def create_decision(
    request_path: Path,
    expected_request_sha256: str,
    reviewer: str,
    verdicts: dict[str, str],
    rationale: str,
    evidence_sha256: list[str],
    output: Path,
) -> dict[str, Any]:
    request = validate_request(request_path)
    require(SHA256.fullmatch(expected_request_sha256) is not None, "expected request SHA-256 is invalid")
    require(digest(request_path) == expected_request_sha256, "reviewer-provided digest does not match exact review request")
    reviewer = safe_identity(reviewer, "reviewer identity")
    require(reviewer != request.get("constructor"), "blind review must be independent from the constructor")
    require(set(verdicts) == set(DIMENSIONS), "all blind review dimensions are required")
    require(all(verdicts[field] in VERDICTS for field in DIMENSIONS), "blind review verdict is invalid")
    rationale = rationale.strip()
    require(rationale, "blind review rationale is required")
    evidence = sorted(set(evidence_sha256))
    require(
        evidence
        and all(isinstance(value, str) and SHA256.fullmatch(value) for value in evidence),
        "blind review evidence digest is invalid",
    )
    decision = {
        "schema": DECISION_SCHEMA,
        "requestSha256": expected_request_sha256,
        "reviewer": reviewer,
        "verdicts": {field: verdicts[field] for field in DIMENSIONS},
        "rationale": rationale,
        "evidenceSha256": evidence,
        "modelTrainingExclusionQualified": False,
        "automaticPromotion": False,
    }
    write_json(output, decision)
    validate_decision(output, request_path)
    return decision


def validate_adjudication(
    path: Path,
    request_path: Path,
    review_paths: list[Path],
    cut_root: Path,
) -> dict[str, Any]:
    request = validate_request(request_path, cut_root)
    adjudication = load(path, "blind review adjudication")
    require(adjudication.get("schema") == ADJUDICATION_SCHEMA, "unsupported blind review adjudication schema")
    require(adjudication.get("requestSha256") == digest(request_path), "blind adjudication request digest differs")
    reviews = [validate_decision(review, request_path) for review in review_paths]
    require(len(reviews) >= 2, "blind adjudication requires at least two independent reviews")
    reviewers = [row["reviewer"] for row in reviews]
    require(len(reviewers) == len(set(reviewers)), "blind adjudication reviewers must be unique")
    expected_reviews = sorted(
        [
            {
                "reviewer": value["reviewer"],
                "decisionSha256": digest(review_paths[index]),
            }
            for index, value in enumerate(reviews)
        ],
        key=lambda row: row["reviewer"],
    )
    require(adjudication.get("reviews") == expected_reviews, "blind adjudication review lineage differs")
    expected_dimensions = {}
    disagreement_count = 0
    for field in DIMENSIONS:
        values = [review["verdicts"][field] for review in reviews]
        unanimous = len(set(values)) == 1
        qualified = unanimous and values[0] == "qualified"
        disagreement_count += int(not unanimous)
        expected_dimensions[field] = {
            "verdicts": sorted(values),
            "unanimous": unanimous,
            "qualified": qualified,
        }
    require(adjudication.get("dimensions") == expected_dimensions, "blind adjudication dimension result differs")
    require(adjudication.get("reviewCount") == len(reviews), "blind adjudication review count differs")
    require(adjudication.get("disagreementRate") == disagreement_count / len(DIMENSIONS), "blind adjudication disagreement rate differs")
    review_qualified = all(value["qualified"] for value in expected_dimensions.values())
    require(adjudication.get("distinctReviewerRecordsQualified") is True, "distinct reviewer record qualification differs")
    require(adjudication.get("semanticLeakReviewConsensusQualified") is expected_dimensions["semanticLeakage"]["qualified"], "semantic-leak consensus differs")
    require(adjudication.get("contaminationRiskReviewConsensusQualified") is expected_dimensions["contaminationRisk"]["qualified"], "contamination review consensus differs")
    require(adjudication.get("reviewConsensusQualified") is review_qualified, "review consensus qualification differs")
    require(adjudication.get("reviewerIdentityAuthenticationQualified") is False, "adjudication overclaims reviewer identity authentication")
    require(adjudication.get("blindPilotReviewQualified") is False, "adjudication overclaims blind-pilot review qualification")
    require(adjudication.get("modelTrainingExclusionQualified") is False, "adjudication overclaims model-training exclusion")
    require(adjudication.get("eligibleForUnseenAgentDiscrimination") is False, "adjudication overclaims unseen-Agent discrimination")
    require(adjudication.get("nextGate") == "authenticated-reviewer-identity-and-artifact-provenance", "blind adjudication next gate differs")
    require(adjudication.get("automaticPromotion") is False, "blind adjudication cannot auto-promote")
    for field in ("cutId", "caseId", "sourceSetSha256", "participantManifestSha256", "evaluatorManifestSha256"):
        require(adjudication.get(field) == request.get(field), f"blind adjudication {field} differs")
    return adjudication


def adjudicate(
    request_path: Path,
    review_paths: list[Path],
    cut_root: Path,
    output: Path,
) -> dict[str, Any]:
    request = validate_request(request_path, cut_root)
    reviews = [validate_decision(path, request_path) for path in review_paths]
    require(len(reviews) >= 2, "blind adjudication requires at least two independent reviews")
    reviewers = [row["reviewer"] for row in reviews]
    require(len(reviewers) == len(set(reviewers)), "blind adjudication reviewers must be unique")
    dimensions = {}
    disagreement_count = 0
    for field in DIMENSIONS:
        values = [review["verdicts"][field] for review in reviews]
        unanimous = len(set(values)) == 1
        qualified = unanimous and values[0] == "qualified"
        disagreement_count += int(not unanimous)
        dimensions[field] = {
            "verdicts": sorted(values),
            "unanimous": unanimous,
            "qualified": qualified,
        }
    review_qualified = all(value["qualified"] for value in dimensions.values())
    adjudication = {
        "schema": ADJUDICATION_SCHEMA,
        "requestSha256": digest(request_path),
        "cutId": request["cutId"],
        "caseId": request["caseId"],
        "sourceSetSha256": request["sourceSetSha256"],
        "participantManifestSha256": request["participantManifestSha256"],
        "evaluatorManifestSha256": request["evaluatorManifestSha256"],
        "reviews": sorted(
            [
                {"reviewer": review["reviewer"], "decisionSha256": digest(review_paths[index])}
                for index, review in enumerate(reviews)
            ],
            key=lambda row: row["reviewer"],
        ),
        "reviewCount": len(reviews),
        "dimensions": dimensions,
        "disagreementRate": disagreement_count / len(DIMENSIONS),
        "distinctReviewerRecordsQualified": True,
        "semanticLeakReviewConsensusQualified": dimensions["semanticLeakage"]["qualified"],
        "contaminationRiskReviewConsensusQualified": dimensions["contaminationRisk"]["qualified"],
        "reviewConsensusQualified": review_qualified,
        "reviewerIdentityAuthenticationQualified": False,
        "blindPilotReviewQualified": False,
        "modelTrainingExclusionQualified": False,
        "eligibleForUnseenAgentDiscrimination": False,
        "nextGate": "authenticated-reviewer-identity-and-artifact-provenance",
        "automaticPromotion": False,
    }
    write_json(output, adjudication)
    validate_adjudication(output, request_path, review_paths, cut_root)
    return adjudication


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--cut", type=Path, required=True)
    prepare.add_argument("--constructor", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    decide = sub.add_parser("decide")
    decide.add_argument("--request", type=Path, required=True)
    decide.add_argument("--expected-request-sha256", required=True)
    decide.add_argument("--reviewer", required=True)
    for field in DIMENSIONS:
        decide.add_argument("--" + re.sub(r"([A-Z])", lambda match: "-" + match.group(1).lower(), field), choices=sorted(VERDICTS), required=True)
    decide.add_argument("--rationale", required=True)
    decide.add_argument("--evidence-sha256", action="append", required=True)
    decide.add_argument("--output", type=Path, required=True)
    adjudication = sub.add_parser("adjudicate")
    adjudication.add_argument("--cut", type=Path, required=True)
    adjudication.add_argument("--request", type=Path, required=True)
    adjudication.add_argument("--review", type=Path, action="append", required=True)
    adjudication.add_argument("--output", type=Path, required=True)
    validation = sub.add_parser("validate")
    validation.add_argument("--cut", type=Path, required=True)
    validation.add_argument("--request", type=Path, required=True)
    validation.add_argument("--review", type=Path, action="append", required=True)
    validation.add_argument("--adjudication", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            value = prepare_request(args.cut, args.constructor, args.output)
        elif args.command == "decide":
            value = create_decision(
                args.request,
                args.expected_request_sha256,
                args.reviewer,
                {field: getattr(args, re.sub(r"([A-Z])", lambda match: "_" + match.group(1).lower(), field)) for field in DIMENSIONS},
                args.rationale,
                args.evidence_sha256,
                args.output,
            )
        elif args.command == "adjudicate":
            value = adjudicate(args.request, args.review, args.cut, args.output)
        else:
            value = validate_adjudication(
                args.adjudication,
                args.request,
                args.review,
                args.cut,
            )
    except (BlindReviewError, OSError) as error:
        print(f"blind case review invalid: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "schema": value["schema"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
