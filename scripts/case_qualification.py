#!/usr/bin/env python3
"""Build and semantically validate generated-case qualification matrices."""
from __future__ import annotations

import re
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _check_results(calibration: dict, stages: list[dict]) -> dict[str, dict[str, dict[str, bool]]]:
    variants = calibration.get("variants")
    require(isinstance(variants, dict), "qualification calibration variants are required")
    stage_order = [stage["id"] for stage in stages]
    cumulative: list[str] = []
    normalized: dict[str, dict[str, dict[str, bool]]] = {}
    for variant, variant_result in variants.items():
        require(isinstance(variant, str) and variant, "qualification variant id is required")
        actual_stages = variant_result.get("stages") if isinstance(variant_result, dict) else None
        require(isinstance(actual_stages, dict), f"qualification variant {variant} stages are required")
        normalized[variant] = {}
        seen_results: dict[str, bool] = {}
        cumulative = []
        for stage in stages:
            stage_id = stage["id"]
            cumulative.extend(stage["checkIds"])
            actual = actual_stages.get(stage_id)
            require(isinstance(actual, dict), f"qualification stage {variant}/{stage_id} is required")
            checks = actual.get("checks")
            require(isinstance(checks, list), f"qualification check results are required for {variant}/{stage_id}")
            current: dict[str, bool] = {}
            for row in checks:
                require(isinstance(row, dict), "qualification check result must be an object")
                check_id = row.get("id")
                passed = row.get("pass")
                require(isinstance(check_id, str) and check_id, "qualification check result id is required")
                require(check_id not in current, f"duplicate qualification check {variant}/{stage_id}/{check_id}")
                require(isinstance(passed, bool), f"qualification check verdict must be boolean for {variant}/{stage_id}/{check_id}")
                current[check_id] = passed
            require(set(current) == set(cumulative), f"qualification check results do not match {variant}/{stage_id}")
            require(actual.get("pass") is all(current.values()), f"qualification aggregate verdict mismatch for {variant}/{stage_id}")
            for check_id, passed in current.items():
                if check_id in seen_results:
                    require(seen_results[check_id] is passed, f"qualification check changed across stages for {variant}/{check_id}")
                else:
                    seen_results[check_id] = passed
            normalized[variant][stage_id] = current
        require(set(actual_stages) == set(stage_order), f"qualification variant {variant} stage set mismatch")
    return normalized


def _variant_roles(calibration: dict, variants: set[str]) -> dict[str, str]:
    roles = calibration.get("variantRoles")
    if roles is None:
        return {
            name: (name if name in {"baseline", "reference"} else "wrong")
            for name in variants
        }
    require(
        isinstance(roles, dict)
        and set(roles) == variants
        and set(roles.values()) <= {"baseline", "reference", "wrong", "alternative-valid"},
        "qualification variant roles are invalid",
    )
    require(roles.get("baseline") == "baseline" and roles.get("reference") == "reference", "qualification baseline/reference roles differ")
    return roles


def build_matrix(
    *,
    case_id: str,
    source_set_sha256: str,
    stages: list[dict],
    oracle: dict,
    calibration: dict,
    calibration_sha256: str,
    review: dict | None,
) -> dict:
    """Derive repair/preservation qualification from per-check calibration evidence."""
    require(isinstance(case_id, str) and case_id, "qualification case id is required")
    require(isinstance(source_set_sha256, str) and SHA256.fullmatch(source_set_sha256), "qualification source set is invalid")
    require(isinstance(calibration_sha256, str) and SHA256.fullmatch(calibration_sha256), "qualification calibration digest is invalid")
    results = _check_results(calibration, stages)
    require("baseline" in results and "reference" in results, "baseline and reference qualification evidence are required")
    roles = _variant_roles(calibration, set(results))
    repair_checks = []
    preservation_checks = []
    stage_checks = []
    cumulative: list[str] = []
    for stage in stages:
        stage_id = stage["id"]
        cumulative.extend(stage["checkIds"])
        stage_checks.append(
            {
                "stageId": stage_id,
                "checkIds": list(stage["checkIds"]),
                "cumulativeCheckIds": list(cumulative),
            }
        )
        for check_id in stage["checkIds"]:
            baseline_pass = results["baseline"][stage_id][check_id]
            reference_pass = results["reference"][stage_id][check_id]
            require(reference_pass is True, f"reference failed qualification check {check_id}")
            row = {
                "id": check_id,
                "stageId": stage_id,
                "baselinePass": baseline_pass,
                "referencePass": reference_pass,
            }
            if baseline_pass:
                preservation_checks.append(row)
            else:
                repair_checks.append(row)
    require(repair_checks, "at least one repair check is required")
    require(preservation_checks, "at least one preservation check is required")
    wrong_variants = [name for name, role in roles.items() if role == "wrong"]
    alternative_variants = [name for name, role in roles.items() if role == "alternative-valid"]
    require(wrong_variants, "at least one wrong qualification variant is required")
    wrong_stage_verdicts = {
        name: [calibration["variants"][name]["stages"][stage["id"]]["pass"] for stage in stages]
        for name in wrong_variants
    }
    require(
        all(not all(verdicts) for verdicts in wrong_stage_verdicts.values()),
        "every wrong qualification variant must fail at least one stage",
    )
    require(
        any(any(verdicts) and not all(verdicts) for verdicts in wrong_stage_verdicts.values()),
        "at least one wrong qualification variant must cross an earlier stage",
    )
    if calibration.get("variantRoles") is not None:
        require(alternative_variants, "explicit qualification roles require an alternative valid solution")
        require(
            all(
                all(calibration["variants"][name]["stages"][stage["id"]]["pass"] for stage in stages)
                for name in alternative_variants
            ),
            "every alternative valid qualification variant must pass every stage",
        )

    if review:
        review_gate = {
            "status": "approved-for-calibration",
            "qualifiedForCalibration": True,
            "authority": review.get("authority"),
            "reviewer": review.get("reviewer"),
            "proposalSha256": review.get("proposalSha256"),
            "decisionSha256": review.get("decisionSha256"),
            "verdict": review.get("verdict"),
        }
    else:
        review_gate = {
            "status": "legacy-unreviewed",
            "qualifiedForCalibration": False,
            "authority": "unavailable",
        }

    variants = []
    for name in sorted(calibration["variants"]):
        stage_verdicts = calibration["variants"][name]["stages"]
        source_sha256 = calibration["variants"][name].get("sourceSha256")
        require(isinstance(source_sha256, str) and SHA256.fullmatch(source_sha256), f"qualification variant source digest is invalid for {name}")
        variants.append(
            {
                "id": name,
                "role": roles[name],
                "sourceSha256": source_sha256,
                "stagePass": {stage["id"]: stage_verdicts[stage["id"]]["pass"] for stage in stages},
            }
        )
    return {
        "schema": "agentlab.case_qualification_matrix.v1",
        "caseId": case_id,
        "sourceSetSha256": source_set_sha256,
        "status": "functional-calibration-qualified-runtime-and-freshness-pending",
        "scope": "static-multi-repository",
        "repairChecks": repair_checks,
        "preservationChecks": preservation_checks,
        "stageChecks": stage_checks,
        "deviceChecks": {
            "status": "separate-gate",
            "checks": [],
        },
        "performanceGuardrails": {
            "status": "separate-gate",
            "checks": [],
        },
        "oracleAuthority": {
            "status": "qualified",
            "authority": oracle.get("authority"),
            "sha256": oracle.get("sha256"),
            "receiptSchema": oracle.get("receiptSchema"),
        },
        "referenceReplay": {
            "status": "qualified",
            "summarySha256": calibration_sha256,
            "infrastructureAvailable": calibration.get("infrastructureAvailable"),
            "alternativeValidCount": len(alternative_variants),
            "alternativeValidQualified": bool(alternative_variants),
            "variants": variants,
        },
        "freshness": {
            "status": "unqualified-unknown",
            "qualified": False,
            "sourceVisibility": "unknown",
            "contaminationReview": "not-performed",
        },
        "review": review_gate,
        "automaticPromotion": False,
    }


def validate_matrix(case: dict, calibration: dict, calibration_sha256: str) -> dict:
    """Validate matrix structure plus its semantic correspondence to case/calibration."""
    require(case.get("schema") == "agentlab.multi_repo_evaluation_case.v1", "unsupported evaluation case schema")
    require(case.get("status") == "frozen-calibrated", "evaluation case is not frozen and calibrated")
    require(case.get("automaticPromotion") is False, "evaluation case must not auto-promote")
    require(calibration.get("schema") == "agentlab.multi_repo_calibration.v1", "unsupported calibration schema")
    case_calibration = case.get("calibration") or {}
    require(case_calibration.get("qualified") is True, "case calibration is not qualified")
    require(case_calibration.get("summarySha256") == calibration_sha256, "case calibration digest mismatch")
    require(calibration.get("candidateId") == case.get("difficultyId"), "qualification candidate mismatch")
    matrix = case.get("qualificationMatrix")
    require(isinstance(matrix, dict), "case qualificationMatrix is required")
    require(matrix.get("schema") == "agentlab.case_qualification_matrix.v1", "unsupported qualification matrix schema")
    require(matrix.get("caseId") == case.get("id"), "qualification case identity mismatch")
    source_set = case.get("sourceSetSha256")
    require(isinstance(source_set, str) and SHA256.fullmatch(source_set), "case source set is invalid")
    require(matrix.get("sourceSetSha256") == source_set == calibration.get("sourceSetSha256"), "qualification source set mismatch")
    require(matrix.get("scope") == "static-multi-repository", "unsupported qualification scope")
    require(matrix.get("status") == "functional-calibration-qualified-runtime-and-freshness-pending", "invalid qualification status")
    require(matrix.get("automaticPromotion") is False, "qualification must not auto-promote")

    oracle = case.get("oracle") or {}
    oracle_gate = matrix.get("oracleAuthority") or {}
    require(oracle_gate.get("status") == "qualified", "Oracle authority is not qualified")
    require(oracle_gate.get("authority") == oracle.get("authority") == "independent-executable-oracle", "qualification Oracle authority mismatch")
    require(oracle_gate.get("sha256") == oracle.get("sha256") == calibration.get("oracleSha256"), "qualification Oracle digest mismatch")
    require(oracle_gate.get("receiptSchema") == oracle.get("receiptSchema") == calibration.get("receiptSchema"), "qualification Oracle receipt mismatch")

    replay = matrix.get("referenceReplay") or {}
    require(replay.get("status") == "qualified", "reference replay is not qualified")
    require(replay.get("summarySha256") == calibration_sha256, "reference replay calibration digest mismatch")
    require(replay.get("infrastructureAvailable") is True, "reference replay infrastructure was unavailable")
    require(calibration.get("infrastructureAvailable") is True, "calibration infrastructure was unavailable")

    stages = case.get("stages")
    require(isinstance(stages, list) and stages, "case stages are required")
    results = _check_results(calibration, stages)
    expected = build_matrix(
        case_id=case["id"],
        source_set_sha256=source_set,
        stages=stages,
        oracle=oracle,
        calibration=calibration,
        calibration_sha256=calibration_sha256,
        review=(case.get("lineage") or {}).get("review"),
    )
    require(matrix == expected, "qualification matrix differs from calibration-derived authority")
    require(set(results) == {row["id"] for row in replay.get("variants", [])}, "reference replay variants mismatch")

    device = matrix.get("deviceChecks") or {}
    performance = matrix.get("performanceGuardrails") or {}
    freshness = matrix.get("freshness") or {}
    require(device == {"status": "separate-gate", "checks": []}, "device qualification must remain a separate gate")
    require(performance == {"status": "separate-gate", "checks": []}, "performance qualification must remain a separate gate")
    require(freshness.get("status") == "unqualified-unknown" and freshness.get("qualified") is False, "unknown freshness must remain unqualified")
    return {
        "ok": True,
        "caseId": case["id"],
        "repairChecks": len(matrix["repairChecks"]),
        "preservationChecks": len(matrix["preservationChecks"]),
        "runtimeGates": ["device", "performance"],
        "freshnessStatus": freshness["status"],
    }
