#!/usr/bin/env python3
"""Report candidate-to-qualified-case yield without merging source lanes or gates."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from case_supply import validate_case_source_classification, validate_case_supply


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rate(numerator: int, denominator: int) -> float:
    return numerator / denominator


def summarize(cohort_path: Path, case_paths: list[Path], method_revision: str) -> dict[str, Any]:
    require(REVISION.fullmatch(method_revision) is not None, "case-supply method revision is invalid")
    cohort = load(cohort_path, "candidate cohort")
    require(cohort.get("schema") == "agentlab.multi_repo_candidate_cohort.v1", "unsupported candidate cohort")
    require(cohort.get("automaticPromotion") is False, "candidate cohort can auto-promote")
    selected = cohort.get("selectedCandidates")
    require(isinstance(selected, list) and len(selected) >= 2, "candidate cohort is too small")
    require(cohort.get("selectedCandidateCount") == len(selected), "candidate cohort count differs")
    selected_by_id: dict[str, dict[str, Any]] = {}
    for row in selected:
        require(isinstance(row, dict), "selected candidate is invalid")
        candidate_id = row.get("id")
        require(isinstance(candidate_id, str) and candidate_id and candidate_id not in selected_by_id, "selected candidate identity is invalid")
        source = row.get("caseSource")
        try:
            validate_case_source_classification(source)
        except ValueError as error:
            raise ValueError(f"selected candidate source classification is invalid: {error}") from error
        selected_by_id[candidate_id] = row

    cases: list[dict[str, Any]] = []
    seen_cases: set[str] = set()
    seen_candidates: set[str] = set()
    cohort_sha256 = digest(cohort_path)
    for path in case_paths:
        case = load(path, "evaluation case")
        supply = validate_case_supply(case)
        case_id = case.get("id")
        candidate_id = case.get("difficultyId")
        require(case_id not in seen_cases, "duplicate case identity")
        require(candidate_id not in seen_candidates, "multiple cases consume one selected candidate")
        require(candidate_id in selected_by_id, "case candidate is outside the selected cohort")
        source = case["caseSource"]
        selected_source = selected_by_id[candidate_id]["caseSource"]
        require(
            {key: source[key] for key in ("lane", "strategy", "authority")} == selected_source,
            "case source differs from selected candidate source",
        )
        require(
            source["evidence"].get("candidateSha256") == selected_by_id[candidate_id].get("candidateSha256"),
            "case source candidate digest differs from cohort",
        )
        lineage = (case.get("lineage") or {}).get("candidateCohort")
        require(isinstance(lineage, dict), "case lacks candidate cohort lineage")
        require(lineage.get("cohortId") == cohort.get("cohortId"), "case cohort identity differs")
        require(lineage.get("cohortSha256") == cohort_sha256, "case cohort digest differs")
        require(lineage.get("candidateId") == candidate_id, "case cohort candidate differs")
        seen_cases.add(case_id)
        seen_candidates.add(candidate_id)
        cases.append(
            {
                "caseId": case_id,
                "candidateId": candidate_id,
                "lane": supply["lane"],
                "strategy": supply["strategy"],
                "caseSha256": digest(path),
                "qualificationReceiptSha256": hashlib.sha256(
                    json.dumps(case["qualificationReceipt"], sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "frozen": case.get("status") == "frozen-calibrated",
                "functionalQualification": supply["functionalQualification"],
                "endToEndQualification": supply["endToEndQualification"],
            }
        )
    cases.sort(key=lambda row: row["caseId"])

    strata = []
    keys = sorted({(row["caseSource"]["lane"], row["caseSource"]["strategy"]) for row in selected})
    for lane, strategy in keys:
        selected_ids = {
            row["id"]
            for row in selected
            if row["caseSource"]["lane"] == lane and row["caseSource"]["strategy"] == strategy
        }
        rows = [row for row in cases if row["lane"] == lane and row["strategy"] == strategy]
        frozen = sum(row["frozen"] for row in rows)
        functional = sum(row["functionalQualification"] for row in rows)
        end_to_end = sum(row["endToEndQualification"] for row in rows)
        strata.append(
            {
                "lane": lane,
                "strategy": strategy,
                "selectedCandidateCount": len(selected_ids),
                "unconvertedCandidateCount": len(selected_ids) - len(rows),
                "frozenCaseCount": frozen,
                "functionalQualifiedCaseCount": functional,
                "endToEndQualifiedCaseCount": end_to_end,
                "frozenCaseYieldRate": rate(frozen, len(selected_ids)),
                "functionalCaseYieldRate": rate(functional, len(selected_ids)),
                "endToEndCaseYieldRate": rate(end_to_end, len(selected_ids)),
            }
        )

    selected_count = len(selected)
    frozen_count = sum(row["frozen"] for row in cases)
    functional_count = sum(row["functionalQualification"] for row in cases)
    end_to_end_count = sum(row["endToEndQualification"] for row in cases)
    observed_lanes = sorted({row["lane"] for row in strata})
    return {
        "schema": "agentlab.case_supply_report.v1",
        "cohortId": cohort["cohortId"],
        "cohortSha256": cohort_sha256,
        "methodRevision": method_revision,
        "denominators": {
            "selectedCandidateCount": selected_count,
            "unconvertedCandidateCount": selected_count - len(cases),
            "frozenCaseCount": frozen_count,
            "functionalQualifiedCaseCount": functional_count,
            "endToEndQualifiedCaseCount": end_to_end_count,
            "frozenCaseYieldRate": rate(frozen_count, selected_count),
            "functionalCaseYieldRate": rate(functional_count, selected_count),
            "endToEndCaseYieldRate": rate(end_to_end_count, selected_count),
        },
        "sourceStrata": strata,
        "cases": cases,
        "laneCoverage": {
            "observedLanes": observed_lanes,
            "unobservedLanes": sorted({"natural", "derived"} - set(observed_lanes)),
            "allPlannedLanesObserved": set(observed_lanes) == {"natural", "derived"},
        },
        "qualificationBoundary": {
            "functionalQualificationIncludes": [
                "repair-and-preservation-calibration",
                "alternative-valid-acceptance",
                "meaningful-wrong-rejection",
            ],
            "endToEndQualificationRequires": ["device", "performance", "freshness"],
            "adjudicationIsNotCaseQualification": True,
        },
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--case", type=Path, action="append", default=[])
    parser.add_argument("--method-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
        value = summarize(args.cohort, args.case, args.method_revision)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "outputSha256": digest(args.output)}, sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"case supply report invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
