#!/usr/bin/env python3
"""Review and validate candidate-bound inputs for model case construction."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from api_call_localization import localization_summary, validate_reviewed_localization


SHA256 = re.compile(r"[0-9a-f]{64}")
TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
PROPOSAL_SCHEMA = "agentlab.multi_repo_construction_contract_proposal.v1"
REVIEW_SCHEMA = "agentlab.multi_repo_construction_contract_review.v1"
CONTRACT_SCHEMA = "agentlab.multi_repo_construction_contract.v1"
RISK_IDS = {
    "semantic-contract-unverified",
    "oracle-executable-unverified",
    "source-surface-coverage",
    "calibration-pending",
}


class ContractError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ContractError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), f"evidence must be a regular file: {path.name}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def selected_candidate(selection_path: Path, difficulty_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    selection = load(selection_path, "candidate selection")
    difficulty = load(difficulty_path, "difficulty evidence")
    require(selection.get("schema") == "agentlab.multi_repo_candidate_selection.v2", "unsupported candidate selection")
    require(selection.get("automaticPromotion") is False, "candidate selection can auto-promote")
    require(difficulty.get("schema") == "agentlab.difficulty_candidates.v2", "unsupported difficulty evidence")
    require(difficulty.get("automaticPromotion") is False, "difficulty evidence can auto-promote")
    require(digest(difficulty_path) == selection.get("difficultyEvidenceSha256"), "difficulty evidence differs from selection")
    require(difficulty.get("sourceSetSha256") == selection.get("sourceSetSha256"), "difficulty source set differs from selection")
    candidates = {
        row.get("id"): row
        for row in difficulty.get("candidates") or []
        if isinstance(row, dict)
    }
    candidate_id = selection.get("candidateId")
    require(candidate_id in candidates, "selected candidate is absent from difficulty evidence")
    candidate = candidates[candidate_id]
    require(canonical_digest(candidate) == selection.get("candidateSha256"), "selected candidate bytes differ")
    require(candidate.get("dimensionId") == "multi-repository-change-impact", "candidate is outside multi-repository impact")
    require(candidate.get("maturityState") == "candidate", "candidate maturity differs")
    require(candidate.get("affectedRepositoryCount", 0) >= 2, "candidate does not cross repositories")
    return selection, candidate


def normalize_path_rows(value: Any, label: str) -> list[dict[str, str]]:
    require(isinstance(value, list), f"{label} must be a list")
    rows = []
    for row in value:
        require(isinstance(row, dict) and set(row) == {"repositoryId", "path"}, f"{label} fields differ")
        repository_id = row.get("repositoryId")
        path = row.get("path")
        require(isinstance(repository_id, str) and TOKEN.fullmatch(repository_id), f"{label} repository is invalid")
        require(
            isinstance(path, str)
            and path
            and len(path) <= 4096
            and "\\" not in path
            and not path.startswith("/")
            and all(part not in ("", ".", "..") for part in path.split("/")),
            f"{label} path is unsafe",
        )
        rows.append({"repositoryId": repository_id, "path": path})
    rows.sort(key=lambda row: (row["repositoryId"], row["path"]))
    require(len({(row["repositoryId"], row["path"]) for row in rows}) == len(rows), f"{label} contains duplicates")
    return rows


def validate_oracle(value: dict[str, Any]) -> dict[str, Any]:
    require(value.get("schema") == "agentlab.multi_repo_oracle_contract.v1", "unsupported Oracle contract")
    stage_order = value.get("stageOrder")
    require(
        isinstance(stage_order, list)
        and len(stage_order) >= 2
        and len(stage_order) == len(set(stage_order))
        and all(isinstance(stage, str) and TOKEN.fullmatch(stage) for stage in stage_order),
        "Oracle stage order is invalid",
    )
    checks = value.get("checks")
    require(isinstance(checks, list) and len(checks) >= 2, "Oracle checks are invalid")
    check_ids = set()
    seen_stages = set()
    for check in checks:
        require(isinstance(check, dict) and set(check) == {"id", "stage", "behavior"}, "Oracle check fields differ")
        check_id = check.get("id")
        stage = check.get("stage")
        behavior = check.get("behavior")
        require(isinstance(check_id, str) and TOKEN.fullmatch(check_id) and check_id not in check_ids, "Oracle check id is invalid or duplicated")
        require(stage in stage_order, "Oracle check stage is absent")
        require(isinstance(behavior, str) and 20 <= len(behavior.strip()) <= 2000, "Oracle check behavior is invalid")
        check_ids.add(check_id)
        seen_stages.add(stage)
    require(seen_stages == set(stage_order), "every Oracle stage requires a check")
    expectations = value.get("calibrationExpectations")
    require(isinstance(expectations, dict) and {"baseline", "reference"}.issubset(expectations), "Oracle baseline/reference expectations are required")
    for name, row in expectations.items():
        require(isinstance(name, str) and TOKEN.fullmatch(name), "Oracle expectation id is invalid")
        require(isinstance(row, dict) and set(row) == set(stage_order), "Oracle expectation stages differ")
        require(all(isinstance(result, bool) for result in row.values()), "Oracle expectation verdicts must be boolean")
    require(isinstance(value.get("assessmentBoundary"), str) and value["assessmentBoundary"].strip(), "Oracle assessment boundary is required")
    require(isinstance(value.get("oracleSha256"), str) and SHA256.fullmatch(value["oracleSha256"]), "Oracle executable digest is invalid")
    require(isinstance(value.get("receiptSchema"), str) and TOKEN.fullmatch(value["receiptSchema"]), "Oracle receipt schema is invalid")
    return value


def localization_for_candidate(
    candidate: dict[str, Any],
    source_set_sha256: str,
    paths: tuple[Path | None, Path | None, Path | None],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    required = candidate.get("relationType") == "shared-external-api-call-contract"
    if required:
        require(all(paths), "API-call candidate requires reviewed localization evidence")
        localization = validate_reviewed_localization(
            paths[0], paths[1], paths[2],
            candidate_id=candidate["id"],
            source_set_sha256=source_set_sha256,
        )
        return localization, localization_summary(paths[0], paths[1], paths[2], localization)
    require(not any(paths), "localization evidence is valid only for an API-call candidate")
    return None, None


def propose(
    selection_path: Path,
    difficulty_path: Path,
    surface_path: Path,
    oracle_path: Path,
    localization_paths: tuple[Path | None, Path | None, Path | None],
) -> dict[str, Any]:
    selection, candidate = selected_candidate(selection_path, difficulty_path)
    surface = load(surface_path, "construction source surface")
    oracle = validate_oracle(load(oracle_path, "Oracle contract"))
    require(surface.get("schema") == "agentlab.multi_repo_construction_surface.v1", "unsupported construction source surface")
    require(surface.get("automaticPromotion") is False, "construction source surface can auto-promote")
    editable = normalize_path_rows(surface.get("editablePaths"), "editable paths")
    context = normalize_path_rows(surface.get("contextPaths"), "context paths")
    require(editable, "construction source surface requires editable paths")
    editable_keys = {(row["repositoryId"], row["path"]) for row in editable}
    context_keys = {(row["repositoryId"], row["path"]) for row in context}
    require(not editable_keys.intersection(context_keys), "editable and context paths overlap")
    require(len({repository_id for repository_id, _ in editable_keys | context_keys}) >= 2, "construction source surface must retain multiple repositories")
    localization, localization_lineage = localization_for_candidate(
        candidate, selection["sourceSetSha256"], localization_paths
    )
    if localization is None:
        affected = {
            (row.get("repositoryId"), row.get("path"))
            for row in candidate.get("affectedFiles") or []
            if isinstance(row, dict)
        }
        require(editable_keys | context_keys <= affected, "construction source surface exceeds candidate evidence")
    else:
        localized_editable = {(row["repositoryId"], row["path"]) for row in localization_lineage["editablePaths"]}
        localized_context = {(row["repositoryId"], row["path"]) for row in localization_lineage["contextPaths"]}
        require(editable_keys == localized_editable and context_keys == localized_context, "construction source surface differs from reviewed localization")
    normalized_surface = {
        "schema": "agentlab.multi_repo_construction_surface.v1",
        "editablePaths": editable,
        "contextPaths": context,
        "automaticPromotion": False,
    }
    return {
        "schema": PROPOSAL_SCHEMA,
        "status": "review-required",
        "candidateId": selection["candidateId"],
        "candidateSha256": selection["candidateSha256"],
        "cohortId": selection["cohortId"],
        "cohortSha256": selection["cohortSha256"],
        "sourceSetSha256": selection["sourceSetSha256"],
        "difficultyEvidenceSha256": selection["difficultyEvidenceSha256"],
        "methodRevision": selection["methodRevision"],
        "sourceSurface": normalized_surface,
        "sourceSurfaceSha256": digest(surface_path),
        "oracleContract": oracle,
        "oracleContractSha256": digest(oracle_path),
        "localization": localization_lineage,
        "risks": [
            {"id": "semantic-contract-unverified", "statement": "Review authorizes model construction but does not prove the proposed behavior contract is product truth."},
            {"id": "oracle-executable-unverified", "statement": "The Oracle executable digest is declared but its bytes and independence are not qualified by this review."},
            {"id": "source-surface-coverage", "statement": "The reviewed source surface may omit required implementation or preservation paths."},
            {"id": "calibration-pending", "statement": "Baseline, reference and meaningful wrong variants still require independent execution before case freezing."},
        ],
        "reviewPolicy": {
            "requiredDecisionSchema": REVIEW_SCHEMA,
            "requiredVerdict": "approve-for-model-construction",
            "mustAcknowledgeEveryRisk": True,
        },
        "automaticPromotion": False,
    }


def decide(
    proposal_path: Path,
    expected_sha256: str,
    reviewer: str,
    acknowledged_risk_ids: str,
    rationale: str,
) -> dict[str, Any]:
    proposal = load(proposal_path, "construction contract proposal")
    require(proposal.get("schema") == PROPOSAL_SCHEMA and proposal.get("status") == "review-required", "construction proposal is not review-required")
    require(SHA256.fullmatch(expected_sha256) is not None and digest(proposal_path) == expected_sha256, "construction proposal digest differs")
    require(isinstance(reviewer, str) and reviewer.strip(), "reviewer is required")
    require(isinstance(rationale, str) and len(rationale.strip()) >= 20, "review rationale is too short")
    acknowledged = {value.strip() for value in acknowledged_risk_ids.split(",") if value.strip()}
    risks = {row.get("id") for row in proposal.get("risks") or [] if isinstance(row, dict)}
    require(risks == RISK_IDS == acknowledged, "review must acknowledge every construction risk exactly")
    return {
        "schema": REVIEW_SCHEMA,
        "proposalSha256": expected_sha256,
        "reviewer": reviewer.strip(),
        "rationale": rationale.strip(),
        "verdict": "approve-for-model-construction",
        "acknowledgedRiskIds": sorted(acknowledged),
        "automaticPromotion": False,
    }


def compile_contract(proposal_path: Path, review_path: Path) -> dict[str, Any]:
    proposal = load(proposal_path, "construction contract proposal")
    review = load(review_path, "construction contract review")
    require(proposal.get("schema") == PROPOSAL_SCHEMA and proposal.get("status") == "review-required", "construction proposal is not review-required")
    require(review.get("schema") == REVIEW_SCHEMA, "unsupported construction contract review")
    require(review.get("proposalSha256") == digest(proposal_path), "construction review proposal digest differs")
    require(review.get("verdict") == "approve-for-model-construction", "construction review verdict differs")
    require(isinstance(review.get("reviewer"), str) and review["reviewer"], "construction reviewer is absent")
    require(isinstance(review.get("rationale"), str) and review["rationale"], "construction review rationale is absent")
    risks = {row.get("id") for row in proposal.get("risks") or [] if isinstance(row, dict)}
    require(set(review.get("acknowledgedRiskIds") or []) == risks == RISK_IDS, "construction review risk acknowledgements differ")
    require(review.get("automaticPromotion") is False and proposal.get("automaticPromotion") is False, "construction review can auto-promote")
    return {
        **proposal,
        "schema": CONTRACT_SCHEMA,
        "status": "reviewed-for-model-construction",
        "review": {
            "authority": "explicit-maintainer-construction-review",
            "reviewer": review["reviewer"],
            "rationale": review["rationale"],
            "verdict": review["verdict"],
            "acknowledgedRiskIds": sorted(risks),
            "proposalSha256": digest(proposal_path),
            "decisionSha256": digest(review_path),
        },
        "automaticPromotion": False,
    }


def validate(
    contract_path: Path,
    proposal_path: Path,
    review_path: Path,
    selection_path: Path,
    difficulty_path: Path,
    surface_path: Path,
    oracle_path: Path,
    localization_paths: tuple[Path | None, Path | None, Path | None],
) -> dict[str, Any]:
    actual = load(contract_path, "reviewed construction contract")
    expected_proposal = propose(selection_path, difficulty_path, surface_path, oracle_path, localization_paths)
    proposal = load(proposal_path, "construction contract proposal")
    require(proposal == expected_proposal, "construction proposal differs from exact inputs")
    expected_contract = compile_contract(proposal_path, review_path)
    require(actual == expected_contract, "reviewed construction contract differs from exact review")
    require(actual.get("status") == "reviewed-for-model-construction", "construction contract status differs")
    return actual


def write(path: Path, value: dict[str, Any]) -> None:
    require(not path.exists(), f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def add_exact_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--difficulty", type=Path, required=True)
    parser.add_argument("--surface", type=Path, required=True)
    parser.add_argument("--oracle-contract", type=Path, required=True)
    parser.add_argument("--localization", type=Path)
    parser.add_argument("--localization-proposal", type=Path)
    parser.add_argument("--localization-review", type=Path)


def localization_args(args: argparse.Namespace) -> tuple[Path | None, Path | None, Path | None]:
    return args.localization, args.localization_proposal, args.localization_review


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    proposal_command = commands.add_parser("propose")
    add_exact_inputs(proposal_command)
    proposal_command.add_argument("--output", type=Path, required=True)
    decision_command = commands.add_parser("decide")
    decision_command.add_argument("--proposal", type=Path, required=True)
    decision_command.add_argument("--expected-sha256", required=True)
    decision_command.add_argument("--reviewer", required=True)
    decision_command.add_argument("--acknowledged-risk-ids", required=True)
    decision_command.add_argument("--rationale", required=True)
    decision_command.add_argument("--output", type=Path, required=True)
    compile_command = commands.add_parser("compile")
    compile_command.add_argument("--proposal", type=Path, required=True)
    compile_command.add_argument("--review", type=Path, required=True)
    compile_command.add_argument("--output", type=Path, required=True)
    validate_command = commands.add_parser("validate")
    add_exact_inputs(validate_command)
    validate_command.add_argument("--proposal", type=Path, required=True)
    validate_command.add_argument("--review", type=Path, required=True)
    validate_command.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "propose":
            value = propose(args.selection, args.difficulty, args.surface, args.oracle_contract, localization_args(args))
            write(args.output, value)
            result = {"ok": True, "proposalSha256": digest(args.output), "status": value["status"]}
        elif args.command == "decide":
            value = decide(args.proposal, args.expected_sha256, args.reviewer, args.acknowledged_risk_ids, args.rationale)
            write(args.output, value)
            result = {"ok": True, "reviewSha256": digest(args.output), "verdict": value["verdict"]}
        elif args.command == "compile":
            value = compile_contract(args.proposal, args.review)
            write(args.output, value)
            result = {"ok": True, "contractSha256": digest(args.output), "status": value["status"]}
        else:
            value = validate(
                args.contract, args.proposal, args.review, args.selection,
                args.difficulty, args.surface, args.oracle_contract, localization_args(args),
            )
            result = {"ok": True, "contractSha256": digest(args.contract), "status": value["status"]}
        print(json.dumps(result, sort_keys=True))
    except (ContractError, OSError, ValueError) as error:
        print(f"multi-repository construction contract invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
