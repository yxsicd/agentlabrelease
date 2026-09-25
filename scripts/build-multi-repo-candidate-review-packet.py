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


def owner_contexts(
    repositories: dict[str, dict[str, Any]],
    call_facts: list[dict[str, Any]],
    all_facts: list[dict[str, Any]],
    max_owner_lines: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    symbols = {
        (row.get("repositoryId"), row.get("path"), row.get("qualifiedName")): row
        for row in all_facts
        if row.get("kind") == "symbol" and isinstance(row.get("qualifiedName"), str)
    }
    calls_by_owner: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = {}
    for row in all_facts:
        if row.get("kind") != "call":
            continue
        key = (row.get("repositoryId"), row.get("path"), row.get("owner"))
        calls_by_owner.setdefault(key, []).append(row)
    keys = sorted({
        (row.get("repositoryId"), row.get("path"), row.get("owner"))
        for row in call_facts
    })
    contexts = []
    counts = {"complete": 0, "bounded-excerpt": 0, "unresolved-owner": 0}
    for repository_id, path, owner in keys:
        owner_calls = sorted(
            calls_by_owner.get((repository_id, path, owner), []),
            key=lambda row: (
                (row.get("span") or {}).get("startLine", -1),
                row.get("targetExpression", ""),
                row.get("id", ""),
            ),
        )
        call_rows = []
        for row in owner_calls:
            call_row = {
                "factId": row.get("id"),
                "targetExpression": row.get("targetExpression"),
                "span": row.get("span"),
            }
            if isinstance(row.get("controlContext"), dict):
                call_row["controlContext"] = row["controlContext"]
            call_rows.append(call_row)
        base = {
            "repositoryId": repository_id,
            "path": path,
            "owner": owner,
            "callFacts": call_rows,
        }
        symbol = symbols.get((repository_id, path, owner))
        if symbol is None:
            contexts.append({
                **base,
                "status": "unresolved-owner",
                "symbolFactId": None,
                "ownerSpan": None,
                "ownerLineCount": None,
                "ownerSourceSha256": None,
                "ownerSourceByteLength": None,
                "excerpt": [],
                "excerptSha256": canonical_digest([]),
            })
            counts["unresolved-owner"] += 1
            continue
        repository = repositories[repository_id]
        raw = git(repository["root"], "show", f"{repository['revision']}:{path}").stdout
        text = raw.decode("utf-8")
        lines = text.splitlines()
        span = symbol.get("span") or {}
        start_line = span.get("startLine")
        end_line = span.get("endLine")
        start_byte = span.get("startByte")
        end_byte = span.get("endByte")
        require(
            isinstance(start_line, int) and isinstance(end_line, int)
            and 0 <= start_line <= end_line < len(lines),
            f"owner span is invalid for {repository_id}:{path}:{owner}",
        )
        require(
            isinstance(start_byte, int) and isinstance(end_byte, int)
            and 0 <= start_byte <= end_byte <= len(raw),
            f"owner byte span is invalid for {repository_id}:{path}:{owner}",
        )
        owner_line_count = end_line - start_line + 1
        if owner_line_count <= max_owner_lines:
            selected_lines = range(start_line, end_line + 1)
            status = "complete"
        else:
            selected = set(range(start_line, min(end_line + 1, start_line + 12)))
            selected.update(range(max(start_line, end_line - 11), end_line + 1))
            for call in owner_calls:
                call_line = (call.get("span") or {}).get("startLine")
                if isinstance(call_line, int):
                    selected.update(
                        range(max(start_line, call_line - 4), min(end_line + 1, call_line + 5))
                    )
            selected_lines = sorted(selected)
            status = "bounded-excerpt"
        excerpt = [{"line": index + 1, "text": lines[index]} for index in selected_lines]
        owner_raw = raw[start_byte:end_byte]
        contexts.append({
            **base,
            "status": status,
            "symbolFactId": symbol.get("id"),
            "ownerSpan": span,
            "ownerLineCount": owner_line_count,
            "ownerSourceSha256": hashlib.sha256(owner_raw).hexdigest(),
            "ownerSourceByteLength": len(owner_raw),
            "excerpt": excerpt,
            "excerptSha256": canonical_digest(excerpt),
        })
        counts[status] += 1
    return contexts, counts


def call_result_handles(
    call_facts: list[dict[str, Any]],
    all_facts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Relate selected calls to syntactic result handles without claiming dataflow."""
    facts_by_owner: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = {}
    for row in all_facts:
        key = (row.get("repositoryId"), row.get("path"), row.get("owner"))
        facts_by_owner.setdefault(key, []).append(row)

    counts = {
        "binding-initializer": 0,
        "assignment": 0,
        "unbound-result": 0,
        "ambiguous-container": 0,
    }
    member_counts: dict[str, int] = {}
    evidence = []
    for factory in call_facts:
        factory_span = factory.get("span") or {}
        factory_start = factory_span.get("startByte")
        factory_end = factory_span.get("endByte")
        require(
            isinstance(factory_start, int) and isinstance(factory_end, int)
            and 0 <= factory_start <= factory_end,
            f"selected call span is invalid: {factory.get('id')}",
        )
        key = (factory.get("repositoryId"), factory.get("path"), factory.get("owner"))
        owner_facts = facts_by_owner.get(key, [])
        containers = []
        for row in owner_facts:
            if row.get("kind") not in {"binding", "assignment"}:
                continue
            row_span = row.get("span") or {}
            start = row_span.get("startByte")
            end = row_span.get("endByte")
            if (
                isinstance(start, int) and isinstance(end, int)
                and start <= factory_start and factory_end <= end
            ):
                containers.append((end - start, row.get("id", ""), row))
        containers.sort(key=lambda item: (item[0], item[1]))
        smallest = []
        if containers:
            width = containers[0][0]
            smallest = [row for candidate_width, _, row in containers if candidate_width == width]

        defining = smallest[0] if len(smallest) == 1 else None
        if defining is None:
            status = "ambiguous-container" if containers else "unbound-result"
            handle = None
        elif defining.get("kind") == "binding":
            status = "binding-initializer"
            handle = defining.get("name")
        else:
            status = "assignment"
            handle = defining.get("leftExpression")
        if not isinstance(handle, str) or not handle:
            if defining is not None:
                status = "ambiguous-container"
            handle = None
        counts[status] += 1

        direct_calls = []
        reassignments = []
        if handle is not None:
            direct_member = re.compile(
                rf"^{re.escape(handle)}(?:\.|\?\.)([A-Za-z_$][A-Za-z0-9_$]*)$"
            )
            for row in owner_facts:
                row_span = row.get("span") or {}
                start = row_span.get("startByte")
                if row.get("kind") == "call":
                    target = row.get("targetExpression")
                    match = direct_member.fullmatch(target) if isinstance(target, str) else None
                    if match:
                        member = match.group(1)
                        direct_call = {
                            "factId": row.get("id"),
                            "member": member,
                            "targetExpression": target,
                            "span": row.get("span"),
                            "afterSelectedCall": isinstance(start, int) and start >= factory_end,
                        }
                        if isinstance(row.get("controlContext"), dict):
                            direct_call["controlContext"] = row["controlContext"]
                        direct_calls.append(direct_call)
                        member_counts[member] = member_counts.get(member, 0) + 1
                elif (
                    row.get("kind") == "assignment"
                    and row.get("id") != (defining or {}).get("id")
                    and row.get("leftExpression") == handle
                ):
                    reassignments.append({
                        "factId": row.get("id"),
                        "span": row.get("span"),
                        "afterSelectedCall": isinstance(start, int) and start >= factory_end,
                    })
        direct_calls.sort(key=lambda row: (
            (row.get("span") or {}).get("startByte", -1), row.get("factId", "")
        ))
        reassignments.sort(key=lambda row: (
            (row.get("span") or {}).get("startByte", -1), row.get("factId", "")
        ))
        evidence.append({
            "selectedCallFactId": factory.get("id"),
            "repositoryId": factory.get("repositoryId"),
            "path": factory.get("path"),
            "owner": factory.get("owner"),
            "status": status,
            "handleExpression": handle,
            "definingFactId": defining.get("id") if defining else None,
            "definingFactKind": defining.get("kind") if defining else None,
            "directMemberCalls": direct_calls,
            "sameHandleReassignments": reassignments,
        })

    evidence.sort(key=lambda row: (
        row.get("repositoryId", ""), row.get("path", ""),
        row.get("owner", ""), row.get("selectedCallFactId", ""),
    ))
    coverage = {
        "selectedCallCount": len(call_facts),
        "bindingInitializerCount": counts["binding-initializer"],
        "assignmentCount": counts["assignment"],
        "unboundResultCount": counts["unbound-result"],
        "ambiguousContainerCount": counts["ambiguous-container"],
        "directMemberNameCounts": dict(sorted(member_counts.items())),
        "interpretation": (
            "Containment can associate a selected call with one lexical binding or assignment and "
            "enumerate exact direct-member call spellings on that handle. It does not prove aliases, "
            "escapes, receiver types, control-flow coverage, exception safety or runtime release."
        ),
    }
    return evidence, coverage


def call_control_contexts(
    call_facts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    kinds: dict[str, int] = {}
    awaited = 0
    callback = 0
    for fact in call_facts:
        context = fact.get("controlContext")
        require(isinstance(context, dict), f"control context is absent: {fact.get('id')}")
        await_count = context.get("awaitAncestorCount")
        callback_depth = context.get("callbackDepth")
        regions = context.get("controlRegions")
        enclosing = context.get("enclosingCalls")
        require(isinstance(await_count, int) and await_count >= 0, "await context is invalid")
        require(isinstance(callback_depth, int) and callback_depth >= 0, "callback context is invalid")
        require(isinstance(regions, list), "control regions are invalid")
        require(isinstance(enclosing, list), "enclosing calls are invalid")
        awaited += int(await_count > 0)
        callback += int(callback_depth > 0)
        for region in regions:
            require(isinstance(region, dict), "control region is invalid")
            kind = region.get("syntaxKind")
            require(isinstance(kind, str) and kind, "control region kind is invalid")
            kinds[kind] = kinds.get(kind, 0) + 1
        rows.append({
            "factId": fact.get("id"),
            "repositoryId": fact.get("repositoryId"),
            "path": fact.get("path"),
            "owner": fact.get("owner"),
            "targetExpression": fact.get("targetExpression"),
            "span": fact.get("span"),
            "controlContext": context,
        })
    rows.sort(key=lambda row: (
        row.get("repositoryId", ""), row.get("path", ""),
        row.get("owner", ""), row.get("factId", ""),
    ))
    return rows, {
        "selectedCallCount": len(rows),
        "awaitedCallCount": awaited,
        "callbackNestedCallCount": callback,
        "controlRegionKindCounts": dict(sorted(kinds.items())),
        "interpretation": (
            "Ancestor syntax identifies lexical await, callback and control regions only. It does not "
            "prove reachability, branch coverage, dominance, post-dominance or exception-safe cleanup."
        ),
    }


def build_packet(
    manifest_path: Path,
    difficulty_path: Path,
    facts_path: Path,
    proposal_path: Path,
    candidate_id: str,
    packet_method_revision: str,
    context_lines: int = 4,
    max_owner_lines: int = 240,
    context_facts_path: Path | None = None,
    context_method_revision: str | None = None,
) -> dict[str, Any]:
    require(REVISION.fullmatch(packet_method_revision) is not None, "packet method revision is invalid")
    require(0 <= context_lines <= 20, "context lines must be between zero and twenty")
    require(40 <= max_owner_lines <= 1000, "max owner lines must be between forty and one thousand")
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
    require(
        file_digest(difficulty_path) == proposal.get("difficultyEvidenceSha256"),
        "difficulty evidence differs from current-method proposal",
    )
    require(
        file_digest(facts_path) == proposal.get("programFactsSha256"),
        "workspace facts differ from current-method proposal",
    )
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
    all_facts: list[dict[str, Any]] = []
    require(facts_path.is_file() and not facts_path.is_symlink(), "workspace facts must be a regular file")
    for line in facts_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        all_facts.append(row)
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
    using_context_facts = context_facts_path is not None or context_method_revision is not None
    require(
        (context_facts_path is None) == (context_method_revision is None),
        "context facts and context method revision must be supplied together",
    )
    analysis_facts = all_facts
    context_facts_sha256 = None
    if using_context_facts:
        require(
            isinstance(context_method_revision, str)
            and REVISION.fullmatch(context_method_revision) is not None,
            "context method revision is invalid",
        )
        require(
            context_facts_path is not None
            and context_facts_path.is_file()
            and not context_facts_path.is_symlink(),
            "context workspace facts must be a regular file",
        )
        context_facts = [
            json.loads(line)
            for line in context_facts_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        context_by_id = {
            row.get("id"): row for row in context_facts if row.get("id") in evidence_ids
        }
        require(set(context_by_id) == set(evidence_ids), "context facts omit candidate calls")
        stable_fields = (
            "id", "kind", "repositoryId", "path", "owner",
            "targetExpression", "sourceIdentity", "span",
        )
        for fact_id in evidence_ids:
            require(
                {key: selected_facts[fact_id].get(key) for key in stable_fields}
                == {key: context_by_id[fact_id].get(key) for key in stable_fields},
                f"context fact stable projection differs: {fact_id}",
            )
        analysis_facts = context_facts
        call_facts = sorted(
            (context_by_id[fact_id] for fact_id in evidence_ids),
            key=lambda row: (row.get("repositoryId", ""), row.get("path", ""), row.get("id", "")),
        )
        context_facts_sha256 = file_digest(context_facts_path)
    source_rows = [
        source_evidence(repositories[row["repositoryId"]], row, context_lines)
        for row in call_facts
    ]
    owner_rows, owner_counts = owner_contexts(
        repositories, call_facts, analysis_facts, max_owner_lines
    )
    handle_rows, handle_coverage = call_result_handles(call_facts, analysis_facts)
    control_rows = None
    control_coverage = None
    if using_context_facts:
        control_rows, control_coverage = call_control_contexts(call_facts)
    project_boundary_status = (
        "review-required" if all(row["projectBoundaryCandidates"] for row in source_rows)
        else "incomplete"
    )
    risks = [
        {"id": "api-name-is-not-semantics", "statement": "A shared call target does not establish a shared behavioral obligation."},
        {"id": "issue-contract-absent", "statement": "No participant-visible issue, repair behavior or preservation behavior has been approved."},
        {"id": "build-boundary-unqualified", "statement": "Marker-bearing ancestors have not been compiled or accepted as exact project/module roots."},
        {"id": "oracle-unqualified", "statement": "No baseline/reference/alternative/wrong calibration has executed for this candidate."},
    ]
    if owner_counts["bounded-excerpt"] or owner_counts["unresolved-owner"]:
        risks.append({
            "id": "owner-context-incomplete",
            "statement": "At least one owner is unresolved or represented by a bounded excerpt rather than its complete source span.",
        })
    packet = {
        "schema": (
            "agentlab.multi_repo_candidate_review_packet.v3"
            if using_context_facts else "agentlab.multi_repo_candidate_review_packet.v2"
        ),
        "status": "independent-semantic-review-required",
        "candidateId": candidate_id,
        "candidateSha256": canonical_digest(candidate),
        "selectionRoles": shortlist[candidate_id].get("selectionRoles"),
        "packetMethodRevision": packet_method_revision,
        "sourceSetSha256": difficulty.get("sourceSetSha256"),
        "apiContract": seed,
        "mechanism": candidate.get("mechanism"),
        "callSiteEvidence": source_rows,
        "ownerContextEvidence": owner_rows,
        "ownerEvidenceCoverage": {
            "ownerCount": len(owner_rows),
            "completeOwnerCount": owner_counts["complete"],
            "boundedExcerptOwnerCount": owner_counts["bounded-excerpt"],
            "unresolvedOwnerCount": owner_counts["unresolved-owner"],
            "maxOwnerLines": max_owner_lines,
            "interpretation": "Owner spans and same-owner calls are syntactic evidence; they do not resolve receiver types, dataflow or behavioral intent.",
        },
        "callResultHandleEvidence": handle_rows,
        "callResultHandleCoverage": handle_coverage,
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
            "satisfiedByThisPacket": [
                "exact base source set",
                "source-localized call evidence",
                "owner-scoped call-neighborhood evidence",
            ],
        },
        "risks": risks,
        "reviewDecisionContract": {
            "schema": "agentlab.multi_repo_candidate_semantic_review.v1",
            "allowedVerdicts": ["advance-to-case-contract", "reject-as-noncoherent", "defer-for-more-evidence"],
            "requiredQuestionIds": [
                "shared-behavior", "observable-gap", "prompt-completeness", "repair-oracle",
                "preservation-oracle", "environment", "cross-repo-necessity",
            ],
            "requiredRiskIds": [row["id"] for row in risks],
            "reviewerMustBeIndependentOfPacketGenerator": True,
        },
        "lineage": {
            "manifestSha256": file_digest(manifest_path),
            "difficultyEvidenceSha256": file_digest(difficulty_path),
            "workspaceFactsSha256": file_digest(facts_path),
            "currentMethodProposalSha256": file_digest(proposal_path),
            "analysisRunSha256": proposal.get("analysisRunSha256"),
            "proposalMethodRevision": proposal.get("proposalMethodRevision"),
            "contextWorkspaceFactsSha256": context_facts_sha256,
            "contextMethodRevision": context_method_revision,
        },
        "automaticPromotion": False,
    }
    if using_context_facts:
        packet["callControlContextEvidence"] = control_rows
        packet["callControlContextCoverage"] = control_coverage
        packet["sweStyleTaskContract"]["satisfiedByThisPacket"].append(
            "syntactic async and control-region evidence"
        )
    return packet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--difficulty", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--packet-method-revision", required=True)
    parser.add_argument("--context-lines", type=int, default=4)
    parser.add_argument("--max-owner-lines", type=int, default=240)
    parser.add_argument("--context-facts", type=Path)
    parser.add_argument("--context-method-revision")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
        value = build_packet(
            args.manifest, args.difficulty, args.facts, args.proposal,
            args.candidate_id, args.packet_method_revision, args.context_lines,
            args.max_owner_lines,
            args.context_facts,
            args.context_method_revision,
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
