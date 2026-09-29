#!/usr/bin/env python3
"""Apply one reviewed scope replacement to a new, immutable catalog snapshot."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile


SAFE_REVISION = re.compile(r"^[0-9a-f]{40}$")
def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def jsonl_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def language(path: str) -> str:
    name = PurePosixPath(path).name
    if "." not in name or (name.startswith(".") and name.count(".") == 1):
        return "no-extension"
    return name.rsplit(".", 1)[1].lower()


def git_entries(repository: Path, revision: str, boundary: str) -> list[dict]:
    require(SAFE_REVISION.fullmatch(revision) is not None, "source revision must be exact")
    output = subprocess.run(
        ["git", "-C", str(repository), "ls-tree", "-rz", "--full-tree", revision, "--", boundary],
        check=True,
        capture_output=True,
    ).stdout
    entries = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        metadata, path_bytes = raw.split(b"\t", 1)
        _, kind, oid = metadata.decode().split()
        if kind == "blob":
            entries.append({"path": path_bytes.decode(), "gitBlobOid": oid})
    require(entries, "parent boundary has no tracked blobs")
    return sorted(entries, key=lambda row: row["path"])


def selected_paths(selector: dict, entries: list[dict]) -> set[str]:
    if selector.get("type") == "files":
        paths = selector.get("paths")
        require(isinstance(paths, list) and paths, "files selector must name paths")
        require(len(paths) == len(set(paths)), "files selector repeats a path")
        return set(paths)
    require(selector.get("type") == "prefix", "unknown ownership selector type")
    path = selector.get("path")
    require(isinstance(path, str) and path and path != ".", "prefix selector needs a non-root path")
    prefix = path.rstrip("/") + "/"
    return {row["path"] for row in entries if row["path"].startswith(prefix)}


def file_set_digest(entries: list[dict]) -> str:
    payload = "".join(
        f"{row['path']}\0{row['gitBlobOid']}\n" for row in sorted(entries, key=lambda row: row["path"])
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def blob_line_count(repository: Path, revision: str, paths: list[str]) -> int:
    total = 0
    for path in paths:
        content = subprocess.check_output(
            ["git", "-C", str(repository), "show", f"{revision}:{path}"]
        )
        total += len(content.splitlines())
    return total


def is_test(path: str) -> bool:
    lower = path.lower()
    return "/test/" in lower or "/ohostest/" in lower or lower.endswith((".test.ets", ".test.ts", "_test.rs"))


def build_candidate(catalog_path: Path, review_path: Path, repository: Path) -> tuple[list[dict], dict]:
    rows = jsonl_rows(catalog_path)
    review = json.loads(review_path.read_text())
    require(review.get("schema") == "agentlab.maintainer_scope_decomposition_review.v1", "bad review schema")
    require(review.get("automaticCatalogApply") is False, "review cannot authorize automatic catalog apply")
    require(review.get("decision") == "ready-for-atomic-catalog-apply", "review is not ready for catalog apply")
    require(review.get("blockerCode") == "MS-ATOMIC-CATALOG-APPLY-REQUIRED", "review blocker differs")
    source_extensions = review.get("sourceExtensions")
    require(isinstance(source_extensions, list) and source_extensions, "review lacks source extensions")
    require(all(isinstance(item, str) and item for item in source_extensions), "bad source extension")
    require(len(source_extensions) == len(set(source_extensions)), "source extensions repeat")
    source_extensions = {item.lower().lstrip(".") for item in source_extensions}
    verification = review.get("verification", {})
    require(verification.get("complete") is True, "review coverage is incomplete")
    require(verification.get("nonOverlapping") is True, "review coverage overlaps")
    parents = [row for row in rows if row.get("id") == review.get("parentScopeSkillId")]
    require(len(parents) == 1, "review parent must occur exactly once in catalog")
    parent = parents[0]
    require(review.get("repositoryId") == parent.get("repositoryId"), "review repository differs")
    require(review.get("sourceRevision") == parent.get("sourceRevision"), "review revision differs")
    require(review.get("sourceTreeOid") == parent.get("sourceTreeOid"), "review tree differs")
    head = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD^{tree}"], text=True).strip()
    require(head == parent["sourceRevision"], "source checkout revision differs")
    require(tree == parent["sourceTreeOid"], "source checkout tree differs")
    entries = git_entries(repository, head, parent["pathBoundary"])
    by_path = {row["path"]: row for row in entries}
    require(len(entries) == parent["trackedFileCount"], "parent tracked file count differs")

    ownership = Counter()
    child_rows = []
    child_ids: set[str] = set()
    for group in review.get("groups", []):
        child_id = group.get("id")
        require(group.get("reviewStatus") == "semantic-responsibility-proposed",
                f"review group status differs: {child_id}")
        require(isinstance(child_id, str) and child_id not in child_ids, "review group ids must be unique")
        require(all(row.get("id") != child_id for row in rows), f"review group id already exists: {child_id}")
        child_ids.add(child_id)
        paths: set[str] = set()
        selectors = group.get("ownershipSelectors")
        require(isinstance(selectors, list) and selectors, f"review group lacks selectors: {child_id}")
        for selector in selectors:
            selected = selected_paths(selector, entries)
            require(selected, f"ownership selector selects no files: {child_id}")
            require(selected <= by_path.keys(), f"ownership selector escapes parent: {child_id}")
            paths.update(selected)
        for path in paths:
            ownership[path] += 1
        member_entries = [by_path[path] for path in sorted(paths)]
        require(len(member_entries) == group.get("trackedFileCount"), f"tracked count differs: {child_id}")
        require(file_set_digest(member_entries) == group.get("fileSetSha256"), f"file digest differs: {child_id}")
        evidence = group.get("evidence", [])
        require(len(evidence) >= 2, f"insufficient exact evidence: {child_id}")
        require(len({item.get("path") for item in evidence}) == len(evidence),
                f"duplicate evidence path: {child_id}")
        for item in evidence:
            require(by_path.get(item.get("path")) == item and item["path"] in paths,
                    f"evidence differs or is outside group: {child_id}")
        source_paths = [row["path"] for row in member_entries if language(row["path"]) in source_extensions]
        require(len(source_paths) == group.get("sourceFileCount"), f"source count differs: {child_id}")
        languages = dict(sorted(Counter(language(row["path"]) for row in member_entries).items()))
        test_paths = [row["path"] for row in member_entries if is_test(row["path"])]
        child_rows.append({
            **{key: parent[key] for key in (
                "schema", "skillLayer", "stage", "ownershipPlane", "assetClass", "status",
                "repositoryId", "repository", "sourceRevision", "sourceTreeOid", "strategy",
            )},
            "id": child_id,
            "kind": "composite-responsibility",
            "pathBoundary": parent["pathBoundary"],
            "ownershipSelectors": selectors,
            "responsibility": group["responsibility"],
            "documentedTitle": None,
            "documentedPurpose": None,
            "trackedFileCount": len(member_entries),
            "sourceFileCount": len(source_paths),
            "codeLineCount": blob_line_count(repository, head, source_paths),
            "testFileCount": len(test_paths),
            "languages": languages,
            # A composite responsibility remains inside the same module dependency surface.
            "externalDependencyCount": parent["externalDependencyCount"],
            "externalDependencies": parent["externalDependencies"],
            "buildEntrypoints": [path for path in parent["buildEntrypoints"] if path in paths],
            "testEntrypoints": [path for path in parent["testEntrypoints"] if path in paths],
            "evidence": evidence,
            "coverage": "all tracked files selected by this scope are assigned exactly once",
            "automaticPromotion": False,
        })

    missing = sorted(set(by_path) - ownership.keys())
    repeated = sorted(path for path, count in ownership.items() if count != 1)
    require(not missing, "review leaves parent files unassigned")
    require(not repeated, "review assigns parent files more than once")
    require(len(ownership) == verification.get("assignedFileCount"),
            "review assigned file total differs")
    require(sum(row["sourceFileCount"] for row in child_rows) == parent["sourceFileCount"],
            "child source total differs from parent")

    candidate = [row for row in rows if row["id"] != parent["id"]] + child_rows
    candidate.sort(key=lambda row: row["id"])
    require(len({row["id"] for row in candidate}) == len(candidate), "candidate catalog ids collide")
    receipt = {
        "schema": "agentlab.maintainer_scope_catalog_rewrite_receipt.v1",
        "automaticAuthorityMutation": False,
        "repositoryId": parent["repositoryId"],
        "sourceRevision": head,
        "sourceTreeOid": tree,
        "parentScopeSkillId": parent["id"],
        "replacementScopeSkillIds": sorted(child_ids),
        "catalogScopeCountBefore": len(rows),
        "catalogScopeCountAfter": len(candidate),
        "replacedTrackedFileCount": len(entries),
        "replacementTrackedFileCount": sum(row["trackedFileCount"] for row in child_rows),
        "replacedSourceFileCount": parent["sourceFileCount"],
        "replacementSourceFileCount": sum(row["sourceFileCount"] for row in child_rows),
        "complete": True,
        "nonOverlapping": True,
        "decision": "candidate-catalog-ready-for-authoritative-transaction",
    }
    return candidate, receipt


def write_exclusive_atomic(path: Path, rows: list[dict]) -> None:
    require(not path.exists(), "output already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n" for row in rows)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope-skills", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidate, receipt = build_candidate(
        args.scope_skills, args.review, args.repository.resolve(strict=True)
    )
    write_exclusive_atomic(args.output, candidate)
    print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
