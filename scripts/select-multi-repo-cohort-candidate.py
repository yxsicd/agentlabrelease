#!/usr/bin/env python3
"""Resolve one reviewed cohort member without changing the sampling frame."""
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


class SelectionError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise SelectionError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SelectionError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def select(cohort_path: Path, difficulty_path: Path, expected_cohort_sha256: str, candidate_id: str) -> dict[str, Any]:
    cohort = load(cohort_path, "reviewed candidate cohort")
    difficulty = load(difficulty_path, "difficulty evidence")
    require(cohort.get("schema") == "agentlab.multi_repo_candidate_cohort.v1", "unsupported candidate cohort")
    require(cohort.get("automaticPromotion") is False and cohort.get("declaredRepresentative") is False, "candidate cohort policy differs")
    require(isinstance(cohort.get("methodRevision"), str) and REVISION.fullmatch(cohort["methodRevision"]), "candidate cohort method revision is invalid")
    require(isinstance(cohort.get("proposalMethodRevision"), str) and REVISION.fullmatch(cohort["proposalMethodRevision"]), "candidate cohort proposal method revision is invalid")
    require(isinstance(cohort.get("sourceSetSha256"), str) and SHA256.fullmatch(cohort["sourceSetSha256"]), "candidate cohort source set is invalid")
    require(isinstance(cohort.get("difficultyEvidenceSha256"), str) and SHA256.fullmatch(cohort["difficultyEvidenceSha256"]), "candidate cohort difficulty digest is invalid")
    frame = cohort.get("samplingFrame")
    require(isinstance(frame, dict) and frame.get("declaredRepresentative") is False, "candidate cohort sampling frame differs")
    review = cohort.get("review")
    require(isinstance(review, dict), "candidate cohort review is absent")
    require(review.get("authority") == "explicit-candidate-cohort-review", "candidate cohort review authority differs")
    require(review.get("verdict") == "approve-for-independent-case-construction", "candidate cohort review verdict differs")
    require(isinstance(review.get("reviewer"), str) and review["reviewer"].strip(), "candidate cohort reviewer is absent")
    for field in ("proposalSha256", "decisionSha256"):
        require(isinstance(review.get(field), str) and SHA256.fullmatch(review[field]), f"candidate cohort review {field} is invalid")
    require(SHA256.fullmatch(expected_cohort_sha256) is not None, "expected cohort digest is invalid")
    require(digest(cohort_path) == expected_cohort_sha256, "reviewed cohort digest differs")
    require(difficulty.get("schema") == "agentlab.difficulty_candidates.v2", "unsupported difficulty schema")
    require(digest(difficulty_path) == cohort.get("difficultyEvidenceSha256"), "difficulty evidence digest differs")
    require(difficulty.get("sourceSetSha256") == cohort.get("sourceSetSha256"), "difficulty source set differs")
    selected = cohort.get("selectedCandidates")
    require(isinstance(selected, list) and len(selected) >= 2, "reviewed cohort is too small")
    require(cohort.get("selectedCandidateCount") == len(selected), "reviewed cohort candidate count differs")
    selected_by_id = {row.get("id"): row for row in selected if isinstance(row, dict)}
    require(len(selected_by_id) == len(selected), "reviewed cohort candidate identities are invalid")
    require(candidate_id in selected_by_id, "candidate is not a member of the reviewed cohort")
    candidates = {row.get("id"): row for row in difficulty.get("candidates") or [] if isinstance(row, dict)}
    require(candidate_id in candidates, "candidate is absent from exact difficulty evidence")
    require(canonical_digest(candidates[candidate_id]) == selected_by_id[candidate_id].get("candidateSha256"), "candidate bytes differ from reviewed cohort")
    case_source = selected_by_id[candidate_id].get("caseSource")
    require(
        case_source
        == {
            "lane": "derived",
            "strategy": "semantic-program-analysis",
            "authority": "exact-difficulty-evidence",
        },
        "selected candidate source classification is invalid",
    )
    return {
        "schema": "agentlab.multi_repo_candidate_selection.v2",
        "cohortId": cohort["cohortId"],
        "cohortSha256": expected_cohort_sha256,
        "candidateId": candidate_id,
        "candidateSha256": selected_by_id[candidate_id]["candidateSha256"],
        "caseSource": case_source,
        "sourceSetSha256": cohort["sourceSetSha256"],
        "difficultyEvidenceSha256": cohort["difficultyEvidenceSha256"],
        "methodRevision": cohort["methodRevision"],
        "proposalMethodRevision": cohort["proposalMethodRevision"],
        "declaredRepresentative": False,
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--difficulty", type=Path, required=True)
    parser.add_argument("--expected-cohort-sha256", required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
        value = select(args.cohort, args.difficulty, args.expected_cohort_sha256, args.candidate_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "selectionSha256": digest(args.output)}, sort_keys=True))
    except (SelectionError, OSError, ValueError) as error:
        print(f"candidate cohort selection invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
