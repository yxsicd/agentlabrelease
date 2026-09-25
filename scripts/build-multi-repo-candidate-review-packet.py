#!/usr/bin/env python3
"""Materialize exact source evidence for independent candidate review."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


class ReviewPacketError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ReviewPacketError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewPacketError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True)
    if check:
        require(
            result.returncode == 0,
            f"git {' '.join(arguments)} failed: {result.stderr.decode(errors='replace').strip()}",
        )
    return result


def repository_map(manifest: dict[str, Any], difficulty: dict[str, Any]) -> dict[str, dict[str, Any]]:
    require(manifest.get("schema") == "agentlab.multi_repo_manifest.v1", "unsupported manifest schema")
    rows: dict[str, dict[str, Any]] = {}
    projection = []
    for row in manifest.get("repositories") or []:
        require(isinstance(row, dict), "manifest repository is invalid")
        repository_id = row.get("id")
        repository = row.get("repository")
        revision = row.get("revision")
        root = Path(row.get("root", ""))
        require(isinstance(repository_id, str) and repository_id not in rows, "repository id is invalid")
        require(isinstance(repository, str) and repository, f"{repository_id} URL is absent")
        require(isinstance(revision, str) and REVISION.fullmatch(revision), f"{repository_id} revision is invalid")
        require(root.is_dir(), f"{repository_id} root is absent")
        git(root, "cat-file", "-e", f"{revision}^{{commit}}")
        rows[repository_id] = {"repository": repository, "revision": revision, "root": root}
        projection.append({"id": repository_id, "repository": repository, "revision": revision})
    projection.sort(key=lambda row: row["id"])
    require(projection == difficulty.get("sources"), "manifest source projection differs from difficulty evidence")
    return rows


def project_boundaries(repository: dict[str, Any], path: str) -> list[dict[str, Any]]:
    markers = ("build-profile.json5", "hvigorfile.ts", "oh-package.json5")
    parent = PurePosixPath(path).parent
    ancestors = [parent, *parent.parents]
    boundaries = []
    for ancestor in reversed(ancestors):
        if str(ancestor) == ".":
            continue
        present = []
        for marker in markers:
            marker_path = f"{ancestor}/{marker}"
            result = git(
                repository["root"], "cat-file", "-e",
                f"{repository['revision']}:{marker_path}", check=False,
            )
            if result.returncode == 0:
                present.append(marker)
        if present:
            boundaries.append({"path": str(ancestor), "markers": present})
    return boundaries


def source_evidence(
    repository: dict[str, Any], fact: dict[str, Any], context_lines: int
) -> dict[str, Any]:
    path = fact.get("path")
    span = fact.get("span")
    require(isinstance(path, str) and path and not path.startswith("/"), "fact source path is invalid")
    require(isinstance(span, dict), f"{path} fact span is absent")
    start = span.get("startLine")
    end = span.get("endLine")
    require(isinstance(start, int) and start >= 0, f"{path} start line is invalid")
    require(isinstance(end, int) and end >= start, f"{path} end line is invalid")
    raw = git(repository["root"], "show", f"{repository['revision']}:{path}").stdout
    blob = git(repository["root"], "rev-parse", f"{repository['revision']}:{path}").stdout.decode().strip()
    text = raw.decode("utf-8")
    lines = text.splitlines()
    first = max(0, start - context_lines)
    last = min(len(lines), end + context_lines + 1)
    excerpt = [
        {"line": index + 1, "text": lines[index]}
        for index in range(first, last)
    ]
    return {
        "factId": fact["id"],
        "kind": fact.get("kind"),
        "repositoryId": fact.get("repositoryId"),
        "path": path,
        "owner": fact.get("owner"),
        "targetExpression": fact.get("targetExpression"),
        "span": span,
        "sourceIdentity": fact.get("sourceIdentity"),
        "gitBlobOid": blob,
        "sourceSha256": hashlib.sha256(raw).hexdigest(),
        "sourceByteLength": len(raw),
        "excerpt": excerpt,
        "excerptSha256": canonical_digest(excerpt),
        "projectBoundaryCandidates": project_boundaries(repository, path),
    }


def build_packet(
    manifest_path: Path,
    difficulty_path: Path,
    facts_path: Path,
    proposal_path: Path,
    candidate_id: str,
    packet_method_revision: str,
    context_lines: int = 4,
) -> dict[str, Any]:
    require(REVISION.fullmatch(packet_method_revision) is not None, "packet method revision is invalid")
    require(0 <= context_lines <= 20, "context lines must be between zero and twenty")
    manifest = load(manifest_path, "manifest")
    difficulty = load(difficulty_path, "difficulty evidence")
    proposal = load(proposal_path, "current-method proposal")
    require(difficulty.get("schema") == "agentlab.difficulty_candidates.v2", "unsupported difficulty schema")
    require(difficulty.get("automaticPromotion") is False, "difficulty evidence can auto-promote")
    require(
        proposal.get("schema") == "agentlab.real_multi_repo_current_method_proposal.v1",
        "unsupported current-method proposal",
    )
    require(proposal.get("automaticPromotion") is False, "current-method proposal can auto-promote")
    require(proposal.get("sourceSetSha256") == difficulty.get("sourceSetSha256"), "source set differs")
    shortlist = {
        row.get("id"): row
        for row in proposal.get("proposedCandidates") or []
        if isinstance(row, dict)
    }
    require(candidate_id in shortlist, "candidate is not in the frozen review shortlist")
    candidates = {
        row.get("id"): row
        for row in difficulty.get("candidates") or []
        if isinstance(row, dict)
    }
    require(candidate_id in candidates, "candidate is absent from difficulty evidence")
    candidate = candidates[candidate_id]
    require(candidate.get("relationType") == "shared-external-api-call-contract", "candidate is not API-call-specific")
    require(candidate.get("automaticPromotion") is False, "candidate can auto-promote")
    require((candidate.get("verificationContract") or {}).get("caseReady") is False, "candidate unexpectedly claims case readiness")
    require(canonical_digest(candidate) == shortlist[candidate_id].get("candidateSha256"), "candidate digest differs from shortlist")
    repositories = repository_map(manifest, difficulty)

    evidence_ids = candidate.get("evidenceIds")
    require(isinstance(evidence_ids, list) and evidence_ids, "candidate evidence ids are absent")
    selected_facts: dict[str, dict[str, Any]] = {}
    require(facts_path.is_file() and not facts_path.is_symlink(), "workspace facts must be a regular file")
    for line in facts_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("id") in evidence_ids:
            selected_facts[row["id"]] = row
    require(set(selected_facts) == set(evidence_ids), "candidate facts are incomplete")
    seed = candidate.get("seed") or {}
    call_facts = sorted(
        (
            row for row in selected_facts.values()
            if row.get("kind") == "call" and row.get("targetExpression") == seed.get("callTarget")
        ),
        key=lambda row: (row.get("repositoryId", ""), row.get("path", ""), row.get("id", "")),
    )
    require(call_facts, "candidate has no exact call facts")
    require(
        {row.get("repositoryId") for row in call_facts} == {
            row.get("repositoryId") for row in candidate.get("affectedFiles") or []
        },
        "call facts do not cover every affected repository",
    )
    source_rows = [
        source_evidence(repositories[row["repositoryId"]], row, context_lines)
        for row in call_facts
    ]
    project_boundary_status = (
        "review-required" if all(row["projectBoundaryCandidates"] for row in source_rows)
        else "incomplete"
    )
    return {
        "schema": "agentlab.multi_repo_candidate_review_packet.v1",
        "status": "independent-semantic-review-required",
        "candidateId": candidate_id,
        "candidateSha256": canonical_digest(candidate),
        "selectionRoles": shortlist[candidate_id].get("selectionRoles"),
        "packetMethodRevision": packet_method_revision,
        "sourceSetSha256": difficulty.get("sourceSetSha256"),
        "apiContract": seed,
        "mechanism": candidate.get("mechanism"),
        "callSiteEvidence": source_rows,
        "sourceProjectBoundary": {
            "status": project_boundary_status,
            "interpretation": "Marker-bearing ancestors are evidence candidates, not a qualified build root or module.",
        },
        "reviewQuestions": [
            {"id": "shared-behavior", "question": "Do the call sites exercise one coherent cross-repository behavior rather than merely sharing an API name?"},
            {"id": "observable-gap", "question": "Is there an issue-level defect or extension whose pre-change failure is observable in every required repository?"},
            {"id": "prompt-completeness", "question": "Can the participant-facing prompt state every required behavior without revealing the repair?"},
            {"id": "repair-oracle", "question": "Can independent FAIL_TO_PASS checks accept structurally distinct valid repairs?"},
            {"id": "preservation-oracle", "question": "Can independent PASS_TO_PASS checks cover existing repository-specific behavior?"},
            {"id": "environment", "question": "Are exact SDK, build roots, modules and emulator capabilities reproducible for every source?"},
            {"id": "cross-repo-necessity", "question": "Does the task require coordinated multi-repository reasoning, rather than two unrelated single-repository tasks?"},
        ],
        "requiredCalibration": {
            "baseline": "expected issue behavior fails while infrastructure remains available",
            "reference": "known repair passes repair and preservation checks",
            "alternativeValid": "constructor-distinct repair passes the same checks",
            "meaningfulWrong": "plausible incomplete or wrong-boundary repair fails the intended check",
            "environment": "gold/reference execution proves each exact source and runtime before participant grading",
        },
        "sweStyleTaskContract": {
            "required": [
                "exact base source set",
                "participant-visible problem statement",
                "hidden FAIL_TO_PASS repair checks",
                "hidden PASS_TO_PASS preservation checks",
                "exact build and runtime environment identities",
                "reference, alternative-valid and meaningful-wrong calibration receipts",
                "blind participant/evaluator split",
            ],
            "satisfiedByThisPacket": ["exact base source set", "source-localized call evidence"],
        },
        "risks": [
            {"id": "api-name-is-not-semantics", "statement": "A shared call target does not establish a shared behavioral obligation."},
            {"id": "issue-contract-absent", "statement": "No participant-visible issue, repair behavior or preservation behavior has been approved."},
            {"id": "build-boundary-unqualified", "statement": "Marker-bearing ancestors have not been compiled or accepted as exact project/module roots."},
            {"id": "oracle-unqualified", "statement": "No baseline/reference/alternative/wrong calibration has executed for this candidate."},
        ],
        "reviewDecisionContract": {
            "schema": "agentlab.multi_repo_candidate_semantic_review.v1",
            "allowedVerdicts": ["advance-to-case-contract", "reject-as-noncoherent", "defer-for-more-evidence"],
            "requiredQuestionIds": [
                "shared-behavior", "observable-gap", "prompt-completeness", "repair-oracle",
                "preservation-oracle", "environment", "cross-repo-necessity",
            ],
            "requiredRiskIds": [
                "api-name-is-not-semantics", "issue-contract-absent",
                "build-boundary-unqualified", "oracle-unqualified",
            ],
            "reviewerMustBeIndependentOfPacketGenerator": True,
        },
        "lineage": {
            "manifestSha256": file_digest(manifest_path),
            "difficultyEvidenceSha256": file_digest(difficulty_path),
            "workspaceFactsSha256": file_digest(facts_path),
            "currentMethodProposalSha256": file_digest(proposal_path),
            "analysisRunSha256": proposal.get("analysisRunSha256"),
            "proposalMethodRevision": proposal.get("proposalMethodRevision"),
        },
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--difficulty", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--packet-method-revision", required=True)
    parser.add_argument("--context-lines", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
        value = build_packet(
            args.manifest, args.difficulty, args.facts, args.proposal,
            args.candidate_id, args.packet_method_revision, args.context_lines,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "packetSha256": file_digest(args.output), "status": value["status"]}, sort_keys=True))
    except (ReviewPacketError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"candidate review packet invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
