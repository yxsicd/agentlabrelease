#!/usr/bin/env python3
"""Validate semantic grouping of exact decomposition leaves without mutating the catalog."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


SAFE_REVISION = re.compile(r"^[0-9a-f]{40}$")
SAFE_SCOPE_ID = re.compile(r"^skill-scope-[a-z0-9]+(?:-[a-z0-9]+)*$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_entries(repository: Path, revision: str, boundary: str) -> list[dict]:
    require(SAFE_REVISION.fullmatch(revision) is not None, "source revision must be exact")
    output = subprocess.run(
        ["git", "-C", str(repository), "ls-tree", "-rz", "--full-tree", revision, "--", boundary],
        check=True,
        capture_output=True,
    ).stdout
    result = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        metadata, path_bytes = raw.split(b"\t", 1)
        _, kind, oid = metadata.decode().split()
        if kind == "blob":
            result.append({"path": path_bytes.decode(), "gitBlobOid": oid})
    return sorted(result, key=lambda row: row["path"])


def selected_paths(selector: dict, entries: list[dict]) -> set[str]:
    if selector["type"] == "files":
        return set(selector["paths"])
    prefix = selector["path"].rstrip("/") + "/"
    return {row["path"] for row in entries if row["path"].startswith(prefix)}


def file_set_digest(entries: list[dict]) -> str:
    payload = "".join(f"{row['path']}\0{row['gitBlobOid']}\n" for row in entries)
    return hashlib.sha256(payload.encode()).hexdigest()


def build_review(plan_path: Path, spec_path: Path, repository: Path) -> dict:
    plan = load(plan_path)
    spec = load(spec_path)
    require(plan.get("schema") == "agentlab.maintainer_scope_decomposition_plan.v1", "bad plan schema")
    require(spec.get("schema") == "agentlab.maintainer_scope_decomposition_review_spec.v1", "bad review spec schema")
    require(spec.get("parentScopeSkillId") == plan["parent"]["scopeSkillId"], "review parent differs")
    head = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    require(head == plan["sourceRevision"], "source checkout revision differs")
    require(tree == plan["sourceTreeOid"], "source checkout tree differs")
    entries = git_entries(repository, head, plan["parent"]["pathBoundary"])
    by_path = {row["path"]: row for row in entries}
    leaves = {row["id"]: row for row in plan["leaves"]}
    assigned = {leaf_id: 0 for leaf_id in leaves}
    group_ids: set[str] = set()
    groups = []
    for group in spec.get("groups", []):
        require(SAFE_SCOPE_ID.fullmatch(group["id"]) is not None, f"invalid group id: {group['id']}")
        require(group["id"] not in group_ids, f"duplicate group id: {group['id']}")
        group_ids.add(group["id"])
        require(len(group["responsibility"].strip()) >= 40, f"responsibility too short: {group['id']}")
        require(len(group["rationale"].strip()) >= 80, f"rationale too short: {group['id']}")
        member_ids = group["memberLeafIds"]
        require(len(member_ids) == len(set(member_ids)) and member_ids, f"bad members: {group['id']}")
        selectors = []
        paths: set[str] = set()
        for leaf_id in member_ids:
            require(leaf_id in leaves, f"unknown leaf: {leaf_id}")
            assigned[leaf_id] += 1
            selector = leaves[leaf_id]["selector"]
            selectors.append(selector)
            paths.update(selected_paths(selector, entries))
        member_entries = [by_path[path] for path in sorted(paths)]
        source_count = sum(leaves[leaf_id]["sourceFileCount"] for leaf_id in member_ids)
        require(source_count <= plan["maxSourceFilesPerLeaf"], f"review group exceeds source budget: {group['id']}")
        evidence = []
        evidence_paths = group["evidencePaths"]
        require(len(evidence_paths) == len(set(evidence_paths)), f"duplicate evidence path: {group['id']}")
        for path in evidence_paths:
            require(path in paths, f"evidence path is outside review group: {path}")
            evidence.append(by_path[path])
        require(len(evidence) >= 2, f"review group needs two exact evidence paths: {group['id']}")
        groups.append({
            "id": group["id"],
            "responsibility": group["responsibility"],
            "rationale": group["rationale"],
            "memberLeafIds": member_ids,
            "ownershipSelectors": selectors,
            "trackedFileCount": len(member_entries),
            "sourceFileCount": source_count,
            "fileSetSha256": file_set_digest(member_entries),
            "evidence": evidence,
            "reviewStatus": "semantic-responsibility-proposed",
        })
    unassigned = sorted(leaf_id for leaf_id, count in assigned.items() if count == 0)
    multiply_assigned = sorted(leaf_id for leaf_id, count in assigned.items() if count > 1)
    require(not unassigned, "review leaves structural candidates unassigned")
    require(not multiply_assigned, "review assigns structural candidates more than once")
    require(sum(group["trackedFileCount"] for group in groups) == len(entries), "review file totals differ")
    require(sum(group["sourceFileCount"] for group in groups) == plan["parent"]["sourceFileCount"],
            "review source totals differ")
    return {
        "schema": "agentlab.maintainer_scope_decomposition_review.v1",
        "automaticCatalogApply": False,
        "repositoryId": plan["repositoryId"],
        "sourceRevision": head,
        "sourceTreeOid": tree,
        "decompositionPlanSha256": digest(plan_path),
        "parentScopeSkillId": plan["parent"]["scopeSkillId"],
        "groups": groups,
        "verification": {
            "complete": True,
            "nonOverlapping": True,
            "structuralLeafCount": len(leaves),
            "semanticGroupCount": len(groups),
            "assignedFileCount": len(entries),
            "unassignedLeafCount": 0,
            "multiplyAssignedLeafCount": 0,
        },
        "blockerCode": "MS-COMPOSITE-SELECTOR-NOT-SUPPORTED",
        "nextAction": "implement-composite-ownership-selectors-and-atomic-catalog-apply",
        "decision": "blocked-catalog-application",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review = build_review(args.plan, args.spec, args.repository.resolve(strict=True))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(review, indent=2, sort_keys=True) + "\n")
    print(json.dumps(review["verification"], separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
