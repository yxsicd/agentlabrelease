#!/usr/bin/env python3
"""Build a review-required sampling frame from exact difficulty evidence."""
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
TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,160}")


class CohortProposalError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise CohortProposalError(message)


def load(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), "difficulty evidence must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CohortProposalError(f"cannot read difficulty evidence: {error}") from error
    require(isinstance(value, dict), "difficulty evidence must be an object")
    return value


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    candidate_id = candidate.get("id")
    require(isinstance(candidate_id, str) and TOKEN.fullmatch(candidate_id), "candidate id is invalid")
    affected = candidate.get("affectedFiles")
    repository_count = candidate.get("affectedRepositoryCount")
    depth = candidate.get("maxDependencyDepth")
    require(isinstance(affected, list) and affected, f"{candidate_id} affected files are absent")
    require(isinstance(repository_count, int) and repository_count >= 2, f"{candidate_id} repository count is invalid")
    require(isinstance(depth, int) and depth >= 1, f"{candidate_id} dependency depth is invalid")
    relation_type = candidate.get("relationType") or "recursive-reverse-impact"
    require(isinstance(relation_type, str) and TOKEN.fullmatch(relation_type), f"{candidate_id} relation type is invalid")
    return {
        "id": candidate_id,
        "candidateSha256": canonical_digest(candidate),
        "relationType": relation_type,
        "affectedRepositoryCount": repository_count,
        "maxDependencyDepth": depth,
        "affectedFileCount": len(affected),
    }


def propose(difficulty_path: Path, cohort_id: str, method_revision: str) -> dict[str, Any]:
    difficulty = load(difficulty_path)
    require(difficulty.get("schema") == "agentlab.difficulty_candidates.v2", "unsupported difficulty schema")
    require(difficulty.get("automaticPromotion") is False, "difficulty evidence can auto-promote")
    require(TOKEN.fullmatch(cohort_id) is not None, "cohort id is invalid")
    require(REVISION.fullmatch(method_revision) is not None, "method revision is invalid")
    source_set = difficulty.get("sourceSetSha256")
    require(isinstance(source_set, str) and SHA256.fullmatch(source_set), "source set digest is invalid")
    sources = difficulty.get("sources")
    require(isinstance(sources, list) and len(sources) >= 2, "source set is not multi-repository")
    candidates = difficulty.get("candidates")
    require(isinstance(candidates, list) and candidates, "difficulty candidates are absent")

    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in sorted(candidates, key=lambda row: str(row.get("id"))):
        require(isinstance(candidate, dict), "difficulty candidate is invalid")
        candidate_id = candidate.get("id")
        require(
            isinstance(candidate_id, str)
            and TOKEN.fullmatch(candidate_id)
            and candidate_id not in seen,
            "candidate identity is invalid or duplicated",
        )
        seen.add(candidate_id)
        reason = None
        if candidate.get("dimensionId") != "multi-repository-change-impact":
            reason = "outside-multi-repository-change-impact-dimension"
        elif candidate.get("maturityState") != "candidate" or candidate.get("status") != "candidate":
            reason = "not-an-unpromoted-candidate"
        elif candidate.get("automaticPromotion") is not False:
            reason = "automatic-promotion-policy-differs"
        elif not isinstance(candidate.get("affectedRepositoryCount"), int) or candidate["affectedRepositoryCount"] < 2:
            reason = "fewer-than-two-affected-repositories"
        if reason:
            excluded.append({"id": candidate_id, "reason": reason})
        else:
            eligible.append(candidate_summary(candidate))
    require(len(eligible) >= 2, "sampling frame requires at least two eligible candidates")

    strata: dict[str, dict[str, int]] = {
        "relationType": {},
        "affectedRepositoryCount": {},
        "maxDependencyDepth": {},
    }
    for row in eligible:
        for field in strata:
            key = str(row[field])
            strata[field][key] = strata[field].get(key, 0) + 1
    return {
        "schema": "agentlab.multi_repo_candidate_cohort_proposal.v1",
        "status": "review-required",
        "cohortId": cohort_id,
        "methodRevision": method_revision,
        "sourceSetSha256": source_set,
        "difficultyEvidenceSha256": file_digest(difficulty_path),
        "samplingFrame": {
            "description": "All analyzer-emitted, unpromoted multi-repository change-impact candidates in the exact source set.",
            "selectionPolicy": "Reviewer predeclares at least two unique eligible candidate IDs before case construction or outcome measurement.",
            "declaredRepresentative": False,
            "eligibleCount": len(eligible),
            "excludedCount": len(excluded),
            "strata": strata,
        },
        "eligibleCandidates": eligible,
        "excludedCandidates": excluded,
        "risks": [
            {
                "id": "sampling-frame-coverage",
                "statement": "Analyzer-supported candidates do not establish coverage of the full software-task population.",
            },
            {
                "id": "candidate-to-case-yield",
                "statement": "A selected candidate can still fail independent specification, oracle, calibration, or blind-review gates.",
            },
            {
                "id": "selection-bias",
                "statement": "Reviewer selection may bias relation, repository-count, depth, or file-count strata and must not be called representative.",
            },
        ],
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--difficulty", type=Path, required=True)
    parser.add_argument("--cohort-id", required=True)
    parser.add_argument("--method-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
        value = propose(args.difficulty, args.cohort_id, args.method_revision)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "proposalSha256": file_digest(args.output)}, sort_keys=True))
    except (CohortProposalError, OSError, ValueError) as error:
        print(f"candidate cohort proposal invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
