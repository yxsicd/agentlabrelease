#!/usr/bin/env python3
"""Bind a narrow API-call case surface to exact multi-repository evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from api_call_localization import validate_semantic_authorization


SHA256 = re.compile(r"[0-9a-f]{64}")


def load(path: Path):
    return json.loads(path.read_text())


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_bytes(value: bytes):
    return hashlib.sha256(value).hexdigest()


def canonical_digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True
    )
    require(
        result.returncode == 0,
        f"git {' '.join(args)} failed for {root}: {result.stderr.decode(errors='replace').strip()}",
    )
    return result.stdout


def source_path(repositories, row, role):
    require(isinstance(row, dict), f"{role} path must be an object")
    repository_id = row.get("repositoryId")
    path = row.get("path")
    reason = row.get("reason")
    require(repository_id in repositories, f"{role} path names unknown repository")
    require(isinstance(path, str) and path and not path.startswith("/"), f"{role} path is invalid")
    require(isinstance(reason, str) and reason, f"{role} path requires a reason")
    repository = repositories[repository_id]
    raw = git(repository["root"], "show", f"{repository['revision']}:{path}")
    object_id = git(repository["root"], "rev-parse", f"{repository['revision']}:{path}").decode().strip()
    return {
        "repositoryId": repository_id,
        "path": path,
        "reason": reason,
        "sourceIdentity": f"git:{repository['repository']}@{repository['revision']}",
        "gitBlobOid": object_id,
        "sha256": digest_bytes(raw),
        "byteLength": len(raw),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--difficulty", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--semantic-packet", type=Path, required=True)
    parser.add_argument("--semantic-decision", type=Path, required=True)
    parser.add_argument("--semantic-gate", type=Path, required=True)
    parser.add_argument("--method-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "refusing to overwrite localization proposal")
    require(re.fullmatch(r"[0-9a-f]{40}", args.method_revision), "method revision must be an exact Git commit")

    manifest = load(args.manifest)
    difficulty = load(args.difficulty)
    selection = load(args.selection)
    require(manifest.get("schema") == "agentlab.multi_repo_manifest.v1", "unsupported manifest schema")
    require(difficulty.get("schema") == "agentlab.difficulty_candidates.v2", "unsupported difficulty schema")
    require(selection.get("schema") == "agentlab.api_call_case_localization_selection.v1", "unsupported selection schema")
    require(selection.get("candidateId") == args.candidate_id, "selection candidate mismatch")
    require(difficulty.get("automaticPromotion") is False, "difficulty must not auto-promote")
    require(selection.get("automaticPromotion") is False, "selection must not auto-promote")

    candidates = {
        row.get("id"): row
        for row in difficulty.get("candidates", [])
        if isinstance(row, dict)
    }
    require(args.candidate_id in candidates, "candidate is absent from difficulty evidence")
    candidate = candidates[args.candidate_id]
    require(candidate.get("relationType") == "shared-external-api-call-contract", "candidate is not an API-call contract")
    require(candidate.get("affectedRepositoryCount", 0) >= 2, "candidate must span repositories")
    require((candidate.get("verificationContract") or {}).get("caseReady") is False, "candidate must remain non-ready")
    require(candidate.get("automaticPromotion") is False, "candidate must not auto-promote")
    semantic = validate_semantic_authorization(
        args.semantic_packet,
        args.semantic_decision,
        args.semantic_gate,
        candidate_id=args.candidate_id,
        source_set_sha256=difficulty.get("sourceSetSha256"),
        candidate_sha256=canonical_digest(candidate),
    )

    repositories = {}
    source_projection = []
    for row in manifest.get("repositories", []):
        repository_id = row.get("id")
        repository = row.get("repository")
        revision = row.get("revision")
        root = Path(row.get("root", ""))
        require(isinstance(repository_id, str) and repository_id, "repository id is required")
        require(isinstance(repository, str) and repository, "repository URL is required")
        require(isinstance(revision, str) and re.fullmatch(r"[0-9a-f]{40}", revision), "repository revision must be exact")
        require(root.is_dir(), f"repository root is absent for {repository_id}")
        git(root, "cat-file", "-e", f"{revision}^{{commit}}")
        repositories[repository_id] = {
            "repository": repository,
            "revision": revision,
            "root": root,
        }
        source_projection.append({"id": repository_id, "repository": repository, "revision": revision})
    source_projection.sort(key=lambda row: row["id"])
    require(source_projection == difficulty.get("sources"), "manifest source projection differs from difficulty evidence")

    evidence_ids = set(candidate.get("evidenceIds", []))
    facts = {}
    for line in args.facts.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("id") in evidence_ids:
            facts[row["id"]] = row
    require(set(facts) == evidence_ids, "candidate evidence facts are incomplete")
    seed = candidate.get("seed") or {}
    call_facts = {
        identity: row
        for identity, row in facts.items()
        if row.get("kind") == "call" and row.get("targetExpression") == seed.get("callTarget")
    }
    require(call_facts, "candidate has no exact call facts")

    target_ids = selection.get("targetCallFactIds")
    reference_ids = selection.get("referenceCallFactIds")
    require(isinstance(target_ids, list) and target_ids, "target call facts are required")
    require(isinstance(reference_ids, list) and reference_ids, "reference call facts are required")
    require(len(target_ids) == len(set(target_ids)), "target call facts must be unique")
    require(len(reference_ids) == len(set(reference_ids)), "reference call facts must be unique")
    require(not set(target_ids).intersection(reference_ids), "target and reference call facts must be disjoint")
    require(set(target_ids).issubset(call_facts), "target call fact is outside the candidate")
    require(set(reference_ids).issubset(call_facts), "reference call fact is outside the candidate")
    require(
        len({call_facts[identity]["repositoryId"] for identity in target_ids}) >= 2,
        "target call facts must span at least two repositories",
    )

    def call_site(identity, role):
        row = call_facts[identity]
        return {
            "role": role,
            "factId": identity,
            "repositoryId": row.get("repositoryId"),
            "path": row.get("path"),
            "owner": row.get("owner"),
            "span": row.get("span"),
            "targetExpression": row.get("targetExpression"),
            "sourceIdentity": row.get("sourceIdentity"),
        }

    target_sites = [call_site(identity, "target") for identity in target_ids]
    reference_sites = [call_site(identity, "reference") for identity in reference_ids]
    editable = [source_path(repositories, row, "editable") for row in selection.get("editablePaths", [])]
    context = [source_path(repositories, row, "context") for row in selection.get("contextPaths", [])]
    require(editable, "at least one editable path is required")
    editable_keys = [(row["repositoryId"], row["path"]) for row in editable]
    context_keys = [(row["repositoryId"], row["path"]) for row in context]
    require(len(editable_keys) == len(set(editable_keys)), "editable paths must be unique")
    require(len(context_keys) == len(set(context_keys)), "context paths must be unique")
    require(not set(editable_keys).intersection(context_keys), "editable and context paths must be disjoint")
    require(
        all((site["repositoryId"], site["path"]) in editable_keys for site in target_sites),
        "every target call site must be editable",
    )

    checks = selection.get("proposedChecks") or {}
    for kind in ("repair", "preservation"):
        rows = checks.get(kind)
        require(isinstance(rows, list) and rows, f"{kind} checks are required")
        require(
            all(isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"] and isinstance(row.get("behavior"), str) and row["behavior"] for row in rows),
            f"{kind} checks require id and behavior",
        )
    all_check_ids = [row["id"] for rows in checks.values() if isinstance(rows, list) for row in rows if isinstance(row, dict) and "id" in row]
    require(len(all_check_ids) == len(set(all_check_ids)), "proposed check ids must be unique")
    title = selection.get("title")
    hypothesis = selection.get("hypothesis")
    require(isinstance(title, str) and title, "selection title is required")
    require(isinstance(hypothesis, str) and hypothesis, "selection hypothesis is required")

    affected_keys = {
        (row.get("repositoryId"), row.get("path"))
        for row in candidate.get("affectedFiles", [])
    }
    expansion = [
        {"repositoryId": row["repositoryId"], "path": row["path"], "reason": row["reason"]}
        for row in editable + context
        if (row["repositoryId"], row["path"]) not in affected_keys
    ]
    risks = [
        {
            "id": "semantic-hypothesis-unverified",
            "statement": "The lifecycle hypothesis is maintainer-supplied and is not proven by syntactic call localization.",
        },
        {
            "id": "reference-sites-not-gold",
            "statement": "Observed reference call sites demonstrate an existing pattern but do not prove the correct implementation.",
        },
        {
            "id": "expanded-impact-surface",
            "statement": "Additional editable or context paths require independent review because they are outside the localized call candidate.",
        },
        {
            "id": "runtime-oracle-pending",
            "statement": "Build, emulator UI, startup performance and power or thermal authority remain separate qualification gates.",
        },
    ]
    proposal = {
        "schema": "agentlab.api_call_case_localization_proposal.v1",
        "status": "review-required",
        "candidateId": args.candidate_id,
        "sourceSetSha256": difficulty.get("sourceSetSha256"),
        "methodRevision": args.method_revision,
        "title": title,
        "hypothesis": hypothesis,
        "apiContract": seed,
        "semanticAuthorization": semantic,
        "targetCallSites": target_sites,
        "referenceCallSites": reference_sites,
        "editablePaths": editable,
        "contextPaths": context,
        "expandedPaths": expansion,
        "proposedChecks": checks,
        "risks": risks,
        "lineage": {
            "manifestSha256": digest(args.manifest),
            "difficultyEvidenceSha256": digest(args.difficulty),
            "workspaceFactsSha256": digest(args.facts),
            "selectionSha256": digest(args.selection),
            "semanticPacketSha256": semantic["packetSha256"],
            "semanticDecisionSha256": semantic["decisionSha256"],
            "semanticGateSha256": semantic["gateSha256"],
        },
        "reviewPolicy": {
            "requiredDecisionSchema": "agentlab.api_call_case_localization_review.v1",
            "requiredVerdict": "approve-for-intent-construction",
            "mustAcknowledgeEveryRisk": True,
        },
        "automaticPromotion": False,
    }
    require(isinstance(proposal["sourceSetSha256"], str) and SHA256.fullmatch(proposal["sourceSetSha256"]), "source set digest is invalid")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proposal, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "status": "review-required", "proposalSha256": digest(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
