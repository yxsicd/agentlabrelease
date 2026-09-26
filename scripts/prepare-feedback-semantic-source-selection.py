#!/usr/bin/env python3
"""Bind prior-case language to exact symbols in a proposed source set."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
MAX_SOURCE_BYTES = 2 * 1024 * 1024
CLAIM_SCHEMA = "agentlab.feedback_semantic_source_selection_claim.v1"
OUTPUT_SCHEMA = "agentlab.feedback_semantic_source_selection.v1"


class SemanticSourceSelectionError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise SemanticSourceSelectionError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SemanticSourceSelectionError(f"cannot load {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def safe_relative_path(value: Any) -> str:
    require(isinstance(value, str) and value and "\\" not in value, "claim path is invalid")
    path = PurePosixPath(value)
    require(
        not path.is_absolute()
        and path.as_posix() == value
        and all(part not in ("", ".", "..") for part in path.parts),
        "claim path is unsafe",
    )
    return value


def source_set_identity(manifest: dict[str, Any]) -> tuple[str, dict[str, dict[str, Any]]]:
    repositories = manifest.get("repositories")
    require(isinstance(repositories, list) and len(repositories) >= 2, "manifest repositories are invalid")
    by_id: dict[str, dict[str, Any]] = {}
    portable = []
    for row in repositories:
        require(isinstance(row, dict), "manifest repository row is invalid")
        source_id = row.get("id")
        require(isinstance(source_id, str) and source_id and source_id not in by_id, "manifest source id is invalid")
        require(all(isinstance(row.get(key), str) and row[key] for key in ("repository", "revision", "root")), "manifest source fields are invalid")
        by_id[source_id] = row
        portable.append({key: row[key] for key in ("id", "repository", "revision")})
    bindings = manifest.get("moduleBindings")
    require(isinstance(bindings, dict), "manifest module bindings are invalid")
    identity = {
        "schema": "agentlab.multi_repo_source_set.v1",
        "repositories": sorted(portable, key=lambda row: row["id"]),
        "moduleBindings": bindings,
    }
    return canonical_digest(identity), by_id


def case_anchors(prior_case: dict[str, Any], mechanism: str) -> tuple[set[str], set[str]]:
    all_anchors = {mechanism}
    demand_anchors: set[str] = set()
    title = prior_case.get("title")
    if isinstance(title, str) and title.strip():
        all_anchors.add(title.strip())
    stages = prior_case.get("stages")
    require(isinstance(stages, list) and stages, "prior case stages are absent")
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        demand = stage.get("demand")
        if isinstance(demand, str) and demand.strip():
            demand_anchors.add(demand.strip())
            all_anchors.add(demand.strip())
    require(demand_anchors, "prior case has no stage demand anchors")
    return all_anchors, demand_anchors


def prepare(
    handoff_path: Path,
    prior_case_path: Path,
    feedback_path: Path,
    manifest_path: Path,
    claim_path: Path,
) -> dict[str, Any]:
    handoff = load(handoff_path, "recursive feedback handoff")
    prior_case = load(prior_case_path, "prior case")
    feedback = load(feedback_path, "assessment feedback")
    manifest = load(manifest_path, "source manifest")
    claim = load(claim_path, "semantic source selection claim")

    require(handoff.get("schema") == "agentlab.release_recursive_feedback_handoff.v1", "unsupported feedback handoff schema")
    require(handoff.get("automaticPromotion") is False, "feedback handoff may auto-promote")
    portable = handoff.get("portableEvidence") or {}
    require((portable.get("priorCase") or {}).get("sha256") == digest(prior_case_path), "handoff prior case digest differs")
    require((portable.get("assessmentFeedback") or {}).get("sha256") == digest(feedback_path), "handoff feedback digest differs")
    require(prior_case.get("id") == feedback.get("caseId"), "prior case and feedback identities differ")
    require(prior_case.get("automaticPromotion") is False, "prior case may auto-promote")
    require(feedback.get("policy", {}).get("automaticPromotion") is False, "feedback may auto-promote")

    source_set_sha256, sources = source_set_identity(manifest)
    require(claim.get("schema") == CLAIM_SCHEMA, "unsupported semantic source selection claim schema")
    require(claim.get("automaticPromotion") is False, "semantic source selection claim may auto-promote")
    require(claim.get("sourceSetSha256") == source_set_sha256, "claim source set digest differs")
    require(claim.get("priorCaseSha256") == digest(prior_case_path), "claim prior case digest differs")
    require(claim.get("feedbackEvidenceSha256") == digest(feedback_path), "claim feedback digest differs")
    reviewer = claim.get("reviewer")
    require(isinstance(reviewer, str) and reviewer.strip(), "claim reviewer is required")

    feedback_candidate_id = claim.get("feedbackCandidateId")
    candidates = feedback.get("candidates")
    require(isinstance(candidates, list), "feedback candidates are invalid")
    selected = [row for row in candidates if isinstance(row, dict) and row.get("id") == feedback_candidate_id]
    require(len(selected) == 1, "claim feedback candidate is absent or duplicated")
    candidate = selected[0]
    require(candidate.get("automaticPromotion") is False, "feedback candidate may auto-promote")
    mechanism = candidate.get("mechanism")
    require(isinstance(mechanism, str) and mechanism, "feedback candidate mechanism is invalid")
    allowed_anchors, demand_anchors = case_anchors(prior_case, mechanism)

    raw_claims = claim.get("claims")
    require(isinstance(raw_claims, list) and 2 <= len(raw_claims) <= 32, "two to thirty-two semantic claims are required")
    normalized = []
    seen: set[tuple[str, str, str, str]] = set()
    covered_repositories: set[str] = set()
    covered_anchors: set[str] = set()
    for row in raw_claims:
        require(isinstance(row, dict), "semantic claim row must be an object")
        require(
            set(row) == {"caseAnchor", "repositoryId", "path", "sourceSymbol", "rationale"},
            "semantic claim fields differ",
        )
        anchor = row.get("caseAnchor")
        require(isinstance(anchor, str) and anchor in allowed_anchors, "semantic claim anchor is not exact prior-case language")
        repository_id = row.get("repositoryId")
        require(repository_id in sources, "semantic claim repository is absent")
        relative_path = safe_relative_path(row.get("path"))
        symbol = row.get("sourceSymbol")
        require(isinstance(symbol, str) and 3 <= len(symbol) <= 256 and "\n" not in symbol, "semantic claim source symbol is invalid")
        rationale = row.get("rationale")
        require(isinstance(rationale, str) and len(rationale.strip()) >= 30, "semantic claim rationale is too weak")
        identity = (anchor, repository_id, relative_path, symbol)
        require(identity not in seen, "semantic claim is duplicated")
        seen.add(identity)

        root = Path(sources[repository_id]["root"]).resolve()
        require(root.is_dir(), "semantic claim repository root is absent")
        target = root / relative_path
        require(target.is_file() and not target.is_symlink(), "semantic claim source file is absent or symbolic")
        resolved = target.resolve()
        require(resolved.is_relative_to(root), "semantic claim source path escapes repository")
        require(resolved.stat().st_size <= MAX_SOURCE_BYTES, "semantic claim source file exceeds bounded size")
        try:
            text = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise SemanticSourceSelectionError("semantic claim source file is not UTF-8 text") from error
        require(symbol in text, "semantic claim source symbol is absent from exact source bytes")
        line = text[: text.index(symbol)].count("\n") + 1
        normalized.append(
            {
                "caseAnchor": anchor,
                "repositoryId": repository_id,
                "path": relative_path,
                "sourceSymbol": symbol,
                "sourceLine": line,
                "sourceFileSha256": digest(resolved),
                "rationale": rationale.strip(),
            }
        )
        covered_repositories.add(repository_id)
        covered_anchors.add(anchor)

    require(len(covered_repositories) >= 2, "semantic claims must cover at least two repositories")
    require(len(covered_anchors) >= 2, "semantic claims must cover at least two prior-case anchors")
    require(covered_anchors & demand_anchors, "semantic claims must cover a prior-case stage demand")
    normalized.sort(key=lambda row: (row["repositoryId"], row["path"], row["sourceLine"], row["caseAnchor"]))
    return {
        "schema": OUTPUT_SCHEMA,
        "status": "source-relevance-evidence-bound-review-required",
        "feedbackCandidateId": feedback_candidate_id,
        "sourceSetSha256": source_set_sha256,
        "priorCaseSha256": digest(prior_case_path),
        "feedbackEvidenceSha256": digest(feedback_path),
        "claimSha256": digest(claim_path),
        "reviewer": reviewer.strip(),
        "claims": normalized,
        "denominators": {
            "claimCount": len(normalized),
            "coveredRepositoryCount": len(covered_repositories),
            "coveredCaseAnchorCount": len(covered_anchors),
        },
        "sourceRelevanceEvidenceBound": True,
        "semanticAlignmentVerified": False,
        "automaticPromotion": False,
        "nextGate": "exact-analysis-then-candidate-semantic-triage",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--prior-case", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--claim", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), f"refusing to overwrite semantic source selection: {args.output}")
        result = prepare(
            args.handoff.resolve(),
            args.prior_case.resolve(),
            args.feedback.resolve(),
            args.manifest.resolve(),
            args.claim.resolve(),
        )
    except (SemanticSourceSelectionError, OSError) as error:
        raise SystemExit(f"feedback semantic source selection invalid: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], **result["denominators"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
