#!/usr/bin/env python3
"""Freeze one independently calibrated case from multi-repository difficulty evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from case_qualification import build_matrix, validate_matrix
from case_supply import (
    build_qualification_receipt,
    derived_program_analysis_source,
    validate_case_supply,
)


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


def load(path: Path):
    return json.loads(path.read_text())


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_sources(sources):
    require(isinstance(sources, list) and len(sources) >= 2, "at least two pinned sources are required")
    ids = []
    for source in sources:
        require(isinstance(source, dict), "source must be an object")
        require(isinstance(source.get("id"), str) and source["id"], "source id is required")
        require(isinstance(source.get("repository"), str) and source["repository"], "source repository is required")
        require(isinstance(source.get("revision"), str) and REVISION.fullmatch(source["revision"]), "source revision must be exact")
        ids.append(source["id"])
    require(len(ids) == len(set(ids)), "source ids must be unique")


def candidate_cohort_lineage(selection_path, difficulty_path, candidate_id, source_set):
    selection = load(selection_path)
    difficulty = load(difficulty_path)
    require(
        selection.get("schema") == "agentlab.multi_repo_candidate_selection.v2",
        "unsupported candidate cohort selection",
    )
    require(selection.get("candidateId") == candidate_id, "candidate cohort selection differs from plan")
    require(selection.get("sourceSetSha256") == source_set, "candidate cohort selection source set differs")
    require(
        selection.get("difficultyEvidenceSha256") == digest(difficulty_path),
        "candidate cohort selection difficulty evidence differs",
    )
    candidates = {
        row.get("id"): row
        for row in difficulty.get("candidates") or []
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    require(candidate_id in candidates, "candidate cohort selection is absent from difficulty evidence")
    require(
        selection.get("candidateSha256") == canonical_digest(candidates[candidate_id]),
        "candidate cohort selection candidate bytes differ",
    )
    require(selection.get("declaredRepresentative") is False, "candidate cohort selection overclaims representativeness")
    require(selection.get("automaticPromotion") is False, "candidate cohort selection can auto-promote")
    for field in ("cohortSha256", "candidateSha256", "difficultyEvidenceSha256"):
        require(
            isinstance(selection.get(field), str) and SHA256.fullmatch(selection[field]),
            f"candidate cohort selection {field} is invalid",
        )
    require(
        isinstance(selection.get("methodRevision"), str)
        and REVISION.fullmatch(selection["methodRevision"]),
        "candidate cohort selection method revision is invalid",
    )
    require(isinstance(selection.get("cohortId"), str) and selection["cohortId"], "candidate cohort identity is invalid")
    require(
        selection.get("caseSource")
        == {
            "lane": "derived",
            "strategy": "semantic-program-analysis",
            "authority": "exact-difficulty-evidence",
        },
        "candidate cohort source classification is invalid",
    )
    return {
        "cohortId": selection["cohortId"],
        "cohortSha256": selection["cohortSha256"],
        "candidateId": selection["candidateId"],
        "candidateSha256": selection["candidateSha256"],
        "difficultyEvidenceSha256": selection["difficultyEvidenceSha256"],
        "methodRevision": selection["methodRevision"],
        "selectionSha256": digest(selection_path),
        "caseSource": selection["caseSource"],
        "declaredRepresentative": False,
        "automaticPromotion": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--difficulty", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--construction-quality", type=Path)
    parser.add_argument("--candidate-selection", type=Path)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--calibration-run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    difficulty = load(args.difficulty)
    plan = load(args.plan)
    calibration = load(args.calibration)
    require(difficulty.get("schema") == "agentlab.difficulty_candidates.v2", "unsupported difficulty schema")
    require(plan.get("schema") in {"agentlab.multi_repo_case_plan.v1", "agentlab.multi_repo_case_plan.v2"}, "unsupported case plan schema")
    require(calibration.get("schema") == "agentlab.multi_repo_calibration.v1", "unsupported calibration schema")
    if plan.get("schema") == "agentlab.multi_repo_case_plan.v2":
        review = plan.get("review") or {}
        require(review.get("authority") == "explicit-proposal-review", "v2 plan requires explicit proposal review")
        require(review.get("verdict") == "approve-for-calibration", "v2 plan was not approved for calibration")
        require(isinstance(review.get("reviewer"), str) and review["reviewer"], "v2 plan reviewer is required")
        require(plan.get("automaticPromotion") is False, "v2 plan must not auto-promote")
        require(args.proposal is not None and args.review is not None, "v2 plan requires proposal and review evidence")
        proposal = load(args.proposal)
        decision = load(args.review)
        require(proposal.get("schema") == "agentlab.multi_repo_case_plan_proposal.v1", "unsupported proposal evidence")
        require(decision.get("schema") == "agentlab.multi_repo_case_plan_review.v1", "unsupported review evidence")
        require(digest(args.proposal) == review.get("proposalSha256") == decision.get("proposalSha256"), "proposal evidence digest mismatch")
        require(digest(args.review) == review.get("decisionSha256"), "review evidence digest mismatch")
        require(decision.get("verdict") == review.get("verdict"), "review verdict mismatch")
        require(decision.get("reviewer") == review.get("reviewer"), "reviewer mismatch")
        require(sorted(decision.get("acknowledgedRiskIds", [])) == review.get("acknowledgedRiskIds"), "review risk acknowledgements mismatch")
        reviewed_fields = ("caseId", "candidateId", "sourceSetSha256", "title", "allowedEdits", "stages", "oracle", "calibrationExpectations", "construction", "constructionQuality", "feedbackAnalysisCut")
        require(all(plan.get(key) == proposal.get(key) for key in reviewed_fields), "v2 plan differs from reviewed proposal")
        if plan.get("construction") is not None:
            require(args.construction_quality is not None, "constructed v2 plan requires construction quality evidence")
            quality = load(args.construction_quality)
            quality_summary = plan.get("constructionQuality") or {}
            require(quality.get("schema") == "agentlab.multi_repo_intent_quality.v1", "unsupported construction quality evidence")
            require(quality.get("qualifiedForReview") is True and quality_summary.get("qualifiedForReview") is True, "construction intent did not qualify for review")
            require(digest(args.construction_quality) == quality_summary.get("reportSha256"), "construction quality evidence digest mismatch")
            require(quality.get("candidateId") == plan.get("candidateId") and quality.get("sourceSetSha256") == plan.get("sourceSetSha256"), "construction quality lineage mismatch")
            require(quality.get("constructionReceiptSha256") == (plan.get("construction") or {}).get("receiptSha256"), "construction quality receipt mismatch")
            require((quality.get("policy") or {}).get("automaticPromotion") is False, "construction quality must not auto-promote")
        else:
            require(args.construction_quality is None, "construction quality evidence requires constructed plan")
    else:
        require(args.proposal is None and args.review is None and args.construction_quality is None, "proposal, review and construction quality evidence require a v2 plan")
    source_set = difficulty.get("sourceSetSha256")
    require(isinstance(source_set, str) and SHA256.fullmatch(source_set), "difficulty requires sourceSetSha256")
    validate_sources(difficulty.get("sources"))
    require(difficulty.get("automaticPromotion") is False, "difficulty evidence must not auto-promote")

    candidate_id = plan.get("candidateId")
    candidates = {
        row.get("id"): row
        for row in difficulty.get("candidates", [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    require(candidate_id in candidates, "plan candidateId is absent from difficulty evidence")
    candidate = candidates[candidate_id]
    require(candidate.get("maturityState") == "candidate", "difficulty must still be a candidate")
    require((candidate.get("verificationContract") or {}).get("caseReady") is False, "difficulty is already marked case-ready")
    require(plan.get("sourceSetSha256") == source_set, "plan source set mismatch")
    cohort_lineage = (
        candidate_cohort_lineage(
            args.candidate_selection,
            args.difficulty,
            candidate_id,
            source_set,
        )
        if args.candidate_selection is not None
        else None
    )

    case_id = plan.get("caseId")
    title = plan.get("title")
    require(isinstance(case_id, str) and case_id, "caseId is required")
    require(isinstance(title, str) and title, "title is required")
    stages = plan.get("stages")
    require(isinstance(stages, list) and len(stages) >= 2, "at least two task stages are required")
    stage_ids = []
    all_checks = set()
    for stage in stages:
        require(isinstance(stage, dict), "stage must be an object")
        stage_id = stage.get("id")
        demand = stage.get("demand")
        checks = stage.get("checkIds")
        require(isinstance(stage_id, str) and stage_id, "stage id is required")
        require(isinstance(demand, str) and demand, "stage demand is required")
        require(isinstance(checks, list) and checks and all(isinstance(value, str) and value for value in checks), "stage checkIds are required")
        require(not all_checks.intersection(checks), "check ids must be unique across stages")
        stage_ids.append(stage_id)
        all_checks.update(checks)
    require(len(stage_ids) == len(set(stage_ids)), "stage ids must be unique")

    affected = {
        (row.get("repositoryId"), row.get("path"))
        for row in candidate.get("affectedFiles", [])
        if isinstance(row, dict)
    }
    allowed = plan.get("allowedEdits")
    require(isinstance(allowed, list) and allowed, "allowedEdits are required")
    allowed_identities = [
        (row.get("repositoryId"), row.get("path"))
        for row in allowed
        if isinstance(row, dict)
    ]
    require(len(allowed_identities) == len(allowed), "allowed edit identity is invalid")
    require(all(repository_id and path for repository_id, path in allowed_identities), "allowed edit identity is incomplete")
    require(len(allowed_identities) == len(set(allowed_identities)), "allowed edits must be unique")
    localization = (plan.get("construction") or {}).get("localization")
    if candidate.get("relationType") == "shared-external-api-call-contract":
        require(isinstance(localization, dict), "shared external API-call case requires reviewed localization lineage")
        require(localization.get("status") == "reviewed-for-intent-construction", "API-call localization was not reviewed")
        require(localization.get("candidateId") == candidate_id, "API-call localization candidate mismatch")
        require(localization.get("sourceSetSha256") == source_set, "API-call localization source set mismatch")
        require(localization.get("automaticPromotion") is False, "API-call localization must not auto-promote")
        localized_allowed = {
            (row.get("repositoryId"), row.get("path"))
            for row in localization.get("editablePaths", [])
            if isinstance(row, dict)
        }
        require(localized_allowed, "API-call localization has no editable paths")
        require(
            set(allowed_identities) == localized_allowed,
            "allowed edits differ from the reviewed API-call localization",
        )
    else:
        require(localization is None, "non-API case must not carry API-call localization")
        for edit in allowed:
            identity = (edit.get("repositoryId"), edit.get("path")) if isinstance(edit, dict) else None
            require(identity in affected, f"allowed edit {identity!r} is outside the analyzed impact surface")

    oracle = plan.get("oracle") or {}
    oracle_digest = oracle.get("sha256")
    require(isinstance(oracle_digest, str) and SHA256.fullmatch(oracle_digest), "oracle sha256 is required")
    require(oracle.get("authority") == "independent-executable-oracle", "oracle must be independently executable")
    require(isinstance(oracle.get("receiptSchema"), str) and oracle["receiptSchema"], "oracle receipt schema is required")
    require(calibration.get("candidateId") == candidate_id, "calibration candidate mismatch")
    require(calibration.get("sourceSetSha256") == source_set, "calibration source set mismatch")
    require(calibration.get("oracleSha256") == oracle_digest, "calibration oracle mismatch")
    require(calibration.get("receiptSchema") == oracle["receiptSchema"], "calibration receipt schema mismatch")
    require(calibration.get("infrastructureAvailable") is True, "calibration infrastructure was unavailable")

    expectations = plan.get("calibrationExpectations")
    results = calibration.get("variants")
    require(isinstance(expectations, dict) and len(expectations) >= 3, "baseline, reference and wrong variants are required")
    require(isinstance(results, dict) and set(results) == set(expectations), "calibration variants do not match plan")
    require("baseline" in expectations and "reference" in expectations, "baseline and reference variants are required")
    roles = calibration.get("variantRoles")
    if roles is None:
        roles = {
            name: (name if name in {"baseline", "reference"} else "wrong")
            for name in expectations
        }
    require(
        isinstance(roles, dict)
        and set(roles) == set(expectations)
        and set(roles.values()) <= {"baseline", "reference", "wrong", "alternative-valid"},
        "calibration variant roles are invalid",
    )
    require(roles.get("baseline") == "baseline" and roles.get("reference") == "reference", "baseline/reference calibration roles differ")
    cumulative_checks = {}
    seen_checks = []
    for stage in stages:
        seen_checks.extend(stage["checkIds"])
        cumulative_checks[stage["id"]] = set(seen_checks)
    for variant, expected_stages in expectations.items():
        require(isinstance(expected_stages, dict) and set(expected_stages) == set(stage_ids), f"variant {variant} must cover every stage")
        actual = results[variant].get("stages") if isinstance(results[variant], dict) else None
        require(isinstance(actual, dict) and set(actual) == set(stage_ids), f"variant {variant} calibration is incomplete")
        for stage_id in stage_ids:
            require(isinstance(expected_stages[stage_id], bool), "expected calibration verdict must be boolean")
            require(actual[stage_id].get("pass") is expected_stages[stage_id], f"calibration mismatch for {variant}/{stage_id}")
            require(isinstance(actual[stage_id].get("receiptSha256"), str) and SHA256.fullmatch(actual[stage_id]["receiptSha256"]), "calibration receipt digest is required")
            actual_checks = actual[stage_id].get("checkIds")
            require(isinstance(actual_checks, list) and set(actual_checks) == cumulative_checks[stage_id], f"oracle checks do not match plan for {variant}/{stage_id}")
            require(actual[stage_id].get("checkCount") == len(actual_checks), "oracle check count mismatch")
    require(all(expectations["reference"].values()), "reference must pass every stage")
    require(not all(expectations["baseline"].values()), "baseline must fail at least one stage")
    wrong_variants = [name for name, role in roles.items() if role == "wrong"]
    alternative_variants = [name for name, role in roles.items() if role == "alternative-valid"]
    require(wrong_variants and all(not all(expectations[name].values()) for name in wrong_variants), "every wrong variant must fail at least one stage")
    require(any(any(expectations[name].values()) and not all(expectations[name].values()) for name in wrong_variants), "at least one wrong variant must cross an earlier stage and fail a later stage")
    if calibration.get("variantRoles") is not None:
        require(alternative_variants, "explicit calibration roles require an alternative valid solution")
        require(all(all(expectations[name].values()) for name in alternative_variants), "every alternative valid solution must pass every stage")

    plan_sha256 = digest(args.plan)
    calibration_sha256 = digest(args.calibration)
    calibration_run_binding = None
    if args.calibration_run is not None:
        calibration_run = load(args.calibration_run)
        require(calibration_run.get("schema") == "agentlab.multi_repo_calibration_bundle_run.v1", "unsupported calibration bundle run")
        require(calibration_run.get("status") == "passed", "calibration bundle run did not pass")
        require(calibration_run.get("automaticPromotion") is False, "calibration bundle run can auto-promote")
        require(calibration_run.get("candidateId") == candidate_id, "calibration bundle run candidate mismatch")
        require(calibration_run.get("sourceSetSha256") == source_set, "calibration bundle run source set mismatch")
        require(calibration_run.get("oracleSha256") == oracle_digest, "calibration bundle run Oracle mismatch")
        require(calibration_run.get("summarySha256") == calibration_sha256, "calibration bundle run summary mismatch")
        if calibration_run.get("variantRoles") is not None:
            require(calibration_run["variantRoles"] == roles, "calibration bundle run variant roles differ")
        for field in ("calibrationBundleSha256", "constructionContractSha256", "descriptorSha256", "driverSha256", "referenceTreeSha256"):
            require(isinstance(calibration_run.get(field), str) and SHA256.fullmatch(calibration_run[field]), f"calibration bundle run requires exact {field}")
        alternative_trees = calibration_run.get("alternativeTrees")
        if calibration.get("variantRoles") is not None:
            alternative_ids = sorted(name for name, role in roles.items() if role == "alternative-valid")
            require(
                isinstance(alternative_trees, list)
                and sorted(row.get("id") for row in alternative_trees if isinstance(row, dict)) == alternative_ids
                and all(
                    isinstance(row, dict)
                    and isinstance(row.get("root"), str)
                    and row["root"]
                    and isinstance(row.get("treeSha256"), str)
                    and SHA256.fullmatch(row["treeSha256"])
                    for row in alternative_trees
                ),
                "calibration bundle run alternative trees are invalid",
            )
        calibration_run_binding = {
            "runSha256": digest(args.calibration_run),
            "bundleSha256": calibration_run["calibrationBundleSha256"],
            "constructionContractSha256": calibration_run["constructionContractSha256"],
            "descriptorSha256": calibration_run["descriptorSha256"],
            "driverSha256": calibration_run["driverSha256"],
            "referenceTreeSha256": calibration_run["referenceTreeSha256"],
            **(
                {
                    "alternativeTrees": alternative_trees,
                    "variantRoles": roles,
                }
                if calibration.get("variantRoles") is not None
                else {}
            ),
        }
    qualification_matrix = build_matrix(
        case_id=case_id,
        source_set_sha256=source_set,
        stages=stages,
        oracle=oracle,
        calibration=calibration,
        calibration_sha256=calibration_sha256,
        review=plan.get("review"),
    )
    case_source = derived_program_analysis_source(
        candidate_id=candidate_id,
        source_set_sha256=source_set,
        difficulty_evidence_sha256=digest(args.difficulty),
        candidate_sha256=canonical_digest(candidate),
    )
    qualification_receipt = build_qualification_receipt(
        case_id=case_id,
        candidate_id=candidate_id,
        case_source=case_source,
        qualification_matrix=qualification_matrix,
        calibration_sha256=calibration_sha256,
    )
    output = {
        "schema": "agentlab.multi_repo_evaluation_case.v1",
        "id": case_id,
        "kind": "task",
        "assetClass": "reusable-knowledge",
        "status": "frozen-calibrated",
        "title": title,
        "difficultyId": candidate_id,
        "sourceSetSha256": source_set,
        "sources": difficulty["sources"],
        "allowedEdits": allowed,
        "stages": stages,
        "oracle": {
            "sha256": oracle_digest,
            "authority": oracle["authority"],
            "receiptSchema": oracle.get("receiptSchema"),
            "checkIds": sorted(all_checks),
        },
        "calibration": {
            "qualified": True,
            "summarySha256": calibration_sha256,
            "expectations": expectations,
            "variantSourceSha256": {
                name: row.get("sourceSha256") for name, row in results.items()
            },
            "variantRoles": roles,
            **({"executableBundle": calibration_run_binding} if calibration_run_binding else {}),
        },
        "construction": plan.get("construction"),
        "constructionQuality": plan.get("constructionQuality"),
        "caseSource": case_source,
        "qualificationMatrix": qualification_matrix,
        "qualificationReceipt": qualification_receipt,
        "lineage": {
            "difficultyEvidenceSha256": digest(args.difficulty),
            "planSha256": plan_sha256,
            "calibrationSha256": calibration_sha256,
            **({"calibrationBundleRun": calibration_run_binding} if calibration_run_binding else {}),
            "review": plan.get("review"),
            "feedbackAnalysisCut": plan.get("feedbackAnalysisCut"),
            "apiCallLocalization": localization,
            **({"candidateCohort": cohort_lineage} if cohort_lineage is not None else {}),
        },
        "automaticPromotion": False,
        "assessmentBoundary": "Exact pinned source set and executable fixture oracle; Harmony build, emulator rendering and device performance remain separate gates.",
    }
    validate_matrix(output, calibration, calibration_sha256)
    validate_case_supply(output)
    require(not args.output.exists(), "refusing to overwrite frozen case")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "caseId": case_id, "stages": len(stages), "variants": len(results), "outputSha256": digest(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
