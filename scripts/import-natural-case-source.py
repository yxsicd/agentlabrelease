#!/usr/bin/env python3
"""Normalize exact natural maintenance evidence into the shared candidate pipeline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any
from urllib.parse import urlsplit

from case_supply import validate_case_source


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
ROLES = {
    "problem-statement",
    "repair-patch",
    "test-patch",
    "failure-report",
    "reproduction",
    "discussion",
    "runtime-log",
}


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def https_url(value: Any, label: str) -> str:
    require(isinstance(value, str) and value, f"{label} is required")
    parsed = urlsplit(value)
    require(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment,
        f"{label} must be a credential-free HTTPS URL without a fragment",
    )
    return value


def timestamp(value: Any, label: str) -> str:
    require(isinstance(value, str) and TIMESTAMP.fullmatch(value), f"{label} must be an exact UTC timestamp")
    return value


def artifact_path(root: Path, relative: Any) -> Path:
    require(isinstance(relative, str) and relative, "natural evidence path is required")
    pure = PurePosixPath(relative)
    require(not pure.is_absolute() and ".." not in pure.parts and "." not in pure.parts, "natural evidence path is unsafe")
    path = root.joinpath(*pure.parts)
    require(path.is_file() and not path.is_symlink(), f"natural evidence is not a regular file: {relative}")
    require(path.resolve().is_relative_to(root.resolve()), "natural evidence escapes the manifest directory")
    return path


def string_ids(value: Any, label: str) -> list[str]:
    require(isinstance(value, list) and value, f"{label} are required")
    require(
        all(isinstance(item, str) and TOKEN.fullmatch(item) for item in value)
        and len(value) == len(set(value)),
        f"{label} are invalid or duplicated",
    )
    return sorted(value)


def build(manifest_path: Path) -> dict[str, Any]:
    require(manifest_path.is_file() and not manifest_path.is_symlink(), "natural source manifest must be a regular file")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(isinstance(manifest, dict), "natural source manifest must be an object")
    require(manifest.get("schema") == "agentlab.natural_case_source_manifest.v1", "unsupported natural source manifest")
    require(manifest.get("automaticPromotion") is False, "natural source manifest can auto-promote")
    candidate_id = manifest.get("id")
    strategy = manifest.get("strategy")
    require(isinstance(candidate_id, str) and TOKEN.fullmatch(candidate_id), "natural candidate id is invalid")
    require(strategy in {"historical-repair", "operator-reported-failure"}, "natural source strategy is invalid")
    require(isinstance(manifest.get("title"), str) and manifest["title"].strip(), "natural source title is required")

    sources = manifest.get("sources")
    require(isinstance(sources, list) and len(sources) >= 2, "natural source requires at least two repositories")
    normalized_sources = []
    source_ids: set[str] = set()
    for row in sources:
        require(isinstance(row, dict), "natural repository source is invalid")
        source_id = row.get("id")
        require(isinstance(source_id, str) and TOKEN.fullmatch(source_id) and source_id not in source_ids, "natural repository id is invalid or duplicated")
        require(isinstance(row.get("repository"), str) and row["repository"], f"natural repository identity is absent for {source_id}")
        require(isinstance(row.get("revision"), str) and REVISION.fullmatch(row["revision"]), f"natural repository revision is not exact for {source_id}")
        source_ids.add(source_id)
        normalized_sources.append({key: row[key] for key in ("id", "repository", "revision")})
    normalized_sources.sort(key=lambda row: row["id"])
    bindings = manifest.get("moduleBindings", {})
    require(isinstance(bindings, dict), "natural source module bindings are invalid")
    source_set = {
        "schema": "agentlab.multi_repo_source_set.v1",
        "repositories": normalized_sources,
        "moduleBindings": bindings,
    }
    source_set_sha256 = canonical_digest(source_set)
    require(manifest.get("sourceSetSha256") == source_set_sha256, "natural source-set digest differs")

    affected = manifest.get("affectedFiles")
    require(isinstance(affected, list) and affected, "natural source affected files are required")
    normalized_affected = []
    affected_ids: set[tuple[str, str]] = set()
    affected_repositories: set[str] = set()
    for row in affected:
        require(isinstance(row, dict), "natural affected file is invalid")
        repository_id = row.get("repositoryId")
        path = row.get("path")
        depth = row.get("dependencyDepth")
        pure_path = PurePosixPath(path) if isinstance(path, str) else None
        require(repository_id in source_ids, "natural affected file repository is outside the source set")
        require(
            isinstance(path, str)
            and path
            and pure_path is not None
            and pure_path.parts
            and not pure_path.is_absolute()
            and ".." not in pure_path.parts,
            "natural affected file path is invalid",
        )
        require(isinstance(depth, int) and depth >= 0, "natural affected file dependency depth is invalid")
        identity = (repository_id, path)
        require(identity not in affected_ids, "natural affected file is duplicated")
        affected_ids.add(identity)
        affected_repositories.add(repository_id)
        normalized_affected.append({"repositoryId": repository_id, "path": path, "dependencyDepth": depth})
    require(len(affected_repositories) >= 2, "natural source must affect at least two repositories")
    max_depth = max(row["dependencyDepth"] for row in normalized_affected)
    require(max_depth >= 1, "natural source requires an explicit cross-repository dependency depth")
    normalized_affected.sort(key=lambda row: (row["repositoryId"], row["path"]))

    evidence = manifest.get("evidence")
    require(isinstance(evidence, list) and evidence, "natural source evidence is required")
    evidence_digests = {"manifestSha256": digest(manifest_path)}
    evidence_roles: set[str] = set()
    evidence_ids: list[str] = []
    for row in evidence:
        require(isinstance(row, dict), "natural source evidence entry is invalid")
        evidence_id = row.get("id")
        role = row.get("role")
        require(isinstance(evidence_id, str) and TOKEN.fullmatch(evidence_id) and evidence_id not in evidence_ids, "natural evidence id is invalid or duplicated")
        require(evidence_id != "manifestSha256", "natural evidence id is reserved")
        require(role in ROLES, "natural evidence role is invalid")
        path = artifact_path(manifest_path.parent, row.get("path"))
        expected = row.get("sha256")
        require(isinstance(expected, str) and SHA256.fullmatch(expected), "natural evidence digest is invalid")
        require(digest(path) == expected, f"natural evidence digest differs: {evidence_id}")
        evidence_ids.append(evidence_id)
        evidence_roles.add(role)
        evidence_digests[evidence_id] = expected
    required_roles = (
        {"problem-statement", "repair-patch", "test-patch"}
        if strategy == "historical-repair"
        else {"failure-report", "reproduction"}
    )
    require(required_roles.issubset(evidence_roles), "natural source required evidence roles are absent")

    origin = manifest.get("origin")
    require(isinstance(origin, dict), "natural source origin is required")
    if strategy == "historical-repair":
        issue_urls = origin.get("issueUrls")
        require(isinstance(issue_urls, list) and issue_urls, "natural issue URLs are required")
        normalized_issue_urls = sorted({https_url(value, "natural issue URL") for value in issue_urls})
        require(len(normalized_issue_urls) == len(issue_urls), "natural issue URLs are duplicated")
        repairs = origin.get("repairs")
        require(isinstance(repairs, list) and repairs, "natural coordinated repairs are required")
        normalized_repairs = []
        repaired_repositories: set[str] = set()
        for repair in repairs:
            require(isinstance(repair, dict), "natural repair entry is invalid")
            repository_id = repair.get("repositoryId")
            require(repository_id in affected_repositories and repository_id not in repaired_repositories, "natural repair repository is invalid or duplicated")
            fix_revision = repair.get("fixRevision")
            require(isinstance(fix_revision, str) and REVISION.fullmatch(fix_revision), "natural fix revision is not exact")
            normalized_repairs.append(
                {
                    "repositoryId": repository_id,
                    "repairUrl": https_url(repair.get("repairUrl"), "natural repair URL"),
                    "fixRevision": fix_revision,
                }
            )
            repaired_repositories.add(repository_id)
        require(repaired_repositories == affected_repositories, "natural coordinated repairs do not cover every affected repository")
        normalized_repairs.sort(key=lambda row: row["repositoryId"])
        normalized_origin = {
            "issueUrls": normalized_issue_urls,
            "repairs": normalized_repairs,
            "openedAt": timestamp(origin.get("openedAt"), "natural issue openedAt"),
            "resolvedAt": timestamp(origin.get("resolvedAt"), "natural repair resolvedAt"),
        }
        require(normalized_origin["resolvedAt"] >= normalized_origin["openedAt"], "natural repair predates issue opening")
    else:
        normalized_origin = {
            "incidentId": origin.get("incidentId"),
            "observedAt": timestamp(origin.get("observedAt"), "natural incident observedAt"),
            "reporterAuthority": origin.get("reporterAuthority").strip()
            if isinstance(origin.get("reporterAuthority"), str)
            else origin.get("reporterAuthority"),
        }
        require(isinstance(normalized_origin["incidentId"], str) and TOKEN.fullmatch(normalized_origin["incidentId"]), "natural incident id is invalid")
        require(isinstance(normalized_origin["reporterAuthority"], str) and normalized_origin["reporterAuthority"], "natural incident reporter authority is required")

    test_contract = manifest.get("testContract")
    require(isinstance(test_contract, dict), "natural source test contract is required")
    normalized_tests = {
        "observedFailureCheckIds": string_ids(test_contract.get("observedFailureCheckIds"), "natural observed-failure checks"),
        "preservationCheckIds": string_ids(test_contract.get("preservationCheckIds"), "natural preservation checks"),
    }
    require(not set(normalized_tests["observedFailureCheckIds"]).intersection(normalized_tests["preservationCheckIds"]), "natural test contract check classes overlap")
    visibility = manifest.get("sourceVisibility")
    require(visibility in {"public", "internal", "private-held-out"}, "natural source visibility is invalid")
    collected_at = timestamp(manifest.get("collectedAt"), "natural source collectedAt")
    terminal_origin_time = normalized_origin["resolvedAt"] if strategy == "historical-repair" else normalized_origin["observedAt"]
    require(collected_at >= terminal_origin_time, "natural source collection predates its terminal origin event")

    case_source = {
        "schema": "agentlab.case_source.v1",
        "lane": "natural",
        "strategy": strategy,
        "candidateId": candidate_id,
        "sourceSetSha256": source_set_sha256,
        "authority": "exact-natural-source-manifest",
        "evidence": evidence_digests,
        "naturalRepresentativenessClaimed": False,
        "automaticPromotion": False,
    }
    validate_case_source(case_source)
    candidate = {
        "id": candidate_id,
        "schema": "agentlab.difficulty_point.v1",
        "dimensionId": "multi-repository-change-impact",
        "primaryDimension": "natural-maintenance-source",
        "relationType": f"natural-{strategy}",
        "mechanism": "exact historical repair evidence" if strategy == "historical-repair" else "exact operator-reported failure evidence",
        "status": "candidate",
        "maturityState": "candidate",
        "title": manifest["title"].strip(),
        "seed": {
            "originId": (
                normalized_origin["issueUrls"][0]
                if strategy == "historical-repair"
                else normalized_origin["incidentId"]
            )
        },
        "affectedFiles": normalized_affected,
        "affectedRepositoryCount": len(affected_repositories),
        "maxDependencyDepth": max_depth,
        "evidenceIds": sorted(evidence_ids),
        "caseSource": case_source,
        "naturalOrigin": {
            "strategy": strategy,
            "origin": normalized_origin,
            "testContract": normalized_tests,
            "sourceVisibility": visibility,
            "collectedAt": collected_at,
        },
        "verificationContract": {
            "caseReady": False,
            "required": [
                "independent specification and prompt-fairness review",
                "reference and alternative-valid calibration",
                "meaningful-wrong rejection",
                "freshness and contamination review",
                "runtime gates required by the target scope",
            ],
        },
        "automaticPromotion": False,
    }
    return {
        "schema": "agentlab.difficulty_candidates.v2",
        "method": "exact natural maintenance source normalization",
        "sourceSetSha256": source_set_sha256,
        "sources": normalized_sources,
        "moduleBindings": bindings,
        "candidates": [candidate],
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
        value = build(args.manifest)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "candidateId": value["candidates"][0]["id"], "outputSha256": digest(args.output)}, sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"natural case source invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
