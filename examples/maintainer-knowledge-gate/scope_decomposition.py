#!/usr/bin/env python3
"""Build an exact, reviewable leaf partition for one oversized Maintainer Skill."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


SAFE_REVISION = re.compile(r"^[0-9a-f]{40}$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def jsonl_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def git_entries(repository: Path, revision: str, boundary: str) -> list[dict]:
    require(SAFE_REVISION.fullmatch(revision) is not None, "source revision must be exact")
    result = subprocess.run(
        ["git", "-C", str(repository), "ls-tree", "-rz", "--full-tree", revision, "--", boundary],
        check=True,
        capture_output=True,
    )
    entries = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        metadata, path_bytes = raw.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        path = path_bytes.decode()
        if kind == "blob":
            entries.append({"path": path, "gitBlobOid": oid, "mode": mode})
    require(entries, "parent boundary has no tracked blobs")
    return sorted(entries, key=lambda row: row["path"])


def language(path: str) -> str:
    name = PurePosixPath(path).name
    if "." not in name or name.startswith(".") and name.count(".") == 1:
        return "no-extension"
    return name.rsplit(".", 1)[1].lower()


def is_source(path: str, extensions: set[str]) -> bool:
    return language(path) in extensions


def file_set_digest(entries: list[dict]) -> str:
    payload = "".join(f"{row['path']}\0{row['gitBlobOid']}\n" for row in entries)
    return hashlib.sha256(payload.encode()).hexdigest()


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "root"


def summarize(entries: list[dict], extensions: set[str]) -> dict:
    languages: dict[str, int] = {}
    for row in entries:
        key = language(row["path"])
        languages[key] = languages.get(key, 0) + 1
    source_count = sum(is_source(row["path"], extensions) for row in entries)
    return {
        "trackedFileCount": len(entries),
        "sourceFileCount": source_count,
        "languages": dict(sorted(languages.items())),
        "fileSetSha256": file_set_digest(entries),
    }


def make_leaf(parent_id: str, parent_boundary: str, selector: dict,
              entries: list[dict], extensions: set[str], label_hint: str | None = None) -> dict:
    if label_hint is not None:
        label = label_hint
    elif selector["type"] == "prefix":
        label = selector["path"][len(parent_boundary):].strip("/")
    else:
        common_parent = str(PurePosixPath(selector["paths"][0]).parent)
        label = f"{common_parent[len(parent_boundary):].strip('/')}-files"
    stats = summarize(entries, extensions)
    return {
        "id": f"{parent_id}-{slug(label)}",
        "parentScopeSkillId": parent_id,
        "selector": selector,
        "analysisMode": "source-behavior" if stats["sourceFileCount"] else "configuration-asset",
        "responsibilityStatus": "requires-evidence-round",
        **stats,
    }


def partition_node(parent_id: str, parent_boundary: str, node: str,
                   entries: list[dict], extensions: set[str], maximum: int) -> list[dict]:
    source_count = sum(is_source(row["path"], extensions) for row in entries)
    if node != parent_boundary and source_count <= maximum:
        return [make_leaf(parent_id, parent_boundary, {"type": "prefix", "path": node}, entries, extensions)]

    direct: list[dict] = []
    groups: dict[str, list[dict]] = {}
    prefix = node.rstrip("/") + "/"
    for row in entries:
        relative = row["path"][len(prefix):]
        if "/" not in relative:
            direct.append(row)
            continue
        child = relative.split("/", 1)[0]
        groups.setdefault(child, []).append(row)

    leaves: list[dict] = []
    if direct:
        direct_source = [row for row in direct if is_source(row["path"], extensions)]
        direct_other = [row for row in direct if not is_source(row["path"], extensions)]
        source_chunks = [
            direct_source[offset:offset + maximum]
            for offset in range(0, len(direct_source), maximum)
        ] or [[]]
        for index, source_chunk in enumerate(source_chunks, start=1):
            chunk = source_chunk + (direct_other if index == 1 else [])
            if not chunk:
                continue
            relative_node = node[len(parent_boundary):].strip("/") or "root"
            leaves.append(make_leaf(
                parent_id, parent_boundary,
                {"type": "files", "paths": [row["path"] for row in sorted(chunk, key=lambda row: row["path"])]},
                chunk, extensions, f"{relative_node}-files-{index}",
            ))
    require(groups or leaves, f"scope cannot be split: {node}")
    for child, child_entries in sorted(groups.items()):
        child_path = f"{node.rstrip('/')}/{child}"
        leaves.extend(partition_node(
            parent_id, parent_boundary, child_path, child_entries, extensions, maximum
        ))
    return leaves


def selected_paths(leaf: dict, all_entries: list[dict]) -> set[str]:
    selector = leaf["selector"]
    if selector["type"] == "files":
        return set(selector["paths"])
    prefix = selector["path"].rstrip("/") + "/"
    return {row["path"] for row in all_entries if row["path"].startswith(prefix)}


def build_plan(parent: dict, repository: Path, maximum: int,
               extensions: set[str]) -> dict:
    require(maximum > 0, "maximum source files must be positive")
    require(extensions, "at least one source extension is required")
    actual_tree = subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", f"{parent['sourceRevision']}^{{tree}}"],
        text=True,
    ).strip()
    require(actual_tree == parent["sourceTreeOid"], "parent source tree oid differs from exact Git tree")
    entries = git_entries(repository, parent["sourceRevision"], parent["pathBoundary"])
    parent_summary = summarize(entries, extensions)
    require(parent_summary["trackedFileCount"] == parent["trackedFileCount"],
            "parent tracked file count differs from exact Git tree")
    require(parent_summary["sourceFileCount"] == parent["sourceFileCount"],
            "source extension policy differs from parent inventory")
    require(parent_summary["sourceFileCount"] > maximum, "parent scope is already bounded")

    leaves = partition_node(
        parent["id"], parent["pathBoundary"], parent["pathBoundary"],
        entries, extensions, maximum,
    )
    require(len({row["id"] for row in leaves}) == len(leaves), "generated leaf ids collide")
    counts = {row["path"]: 0 for row in entries}
    for leaf in leaves:
        require(leaf["sourceFileCount"] <= maximum, "leaf exceeds source budget")
        for path in selected_paths(leaf, entries):
            require(path in counts, f"selector escaped parent boundary: {path}")
            counts[path] += 1
    unassigned = sorted(path for path, count in counts.items() if count == 0)
    multiply_assigned = sorted(path for path, count in counts.items() if count > 1)
    require(not unassigned, "decomposition leaves unassigned files")
    require(not multiply_assigned, "decomposition assigns files more than once")

    return {
        "schema": "agentlab.maintainer_scope_decomposition_plan.v1",
        "automaticPromotion": False,
        "repositoryId": parent["repositoryId"],
        "repository": parent["repository"],
        "sourceRevision": parent["sourceRevision"],
        "sourceTreeOid": parent["sourceTreeOid"],
        "sourceExtensions": sorted(extensions),
        "maxSourceFilesPerLeaf": maximum,
        "parent": {
            "scopeSkillId": parent["id"],
            "pathBoundary": parent["pathBoundary"],
            **parent_summary,
        },
        "leaves": leaves,
        "verification": {
            "complete": True,
            "nonOverlapping": True,
            "assignedFileCount": len(entries),
            "unassignedFileCount": 0,
            "multiplyAssignedFileCount": 0,
        },
        "decision": "ready-for-scope-catalog-review",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope-skills", type=Path, required=True)
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--max-source-files", type=int, default=80)
    parser.add_argument("--source-extensions", default="c,cc,cpp,css,ets,h,hpp,html,java,js,kt,rs,swift,ts")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    parent = next((row for row in jsonl_rows(args.scope_skills) if row["id"] == args.scope_id), None)
    require(parent is not None, "scope id is absent from catalog")
    extensions = {item.strip().lstrip(".").lower() for item in args.source_extensions.split(",") if item.strip()}
    plan = build_plan(parent, args.repository.resolve(strict=True), args.max_source_files, extensions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "scopeSkillId": parent["id"],
        "leafCount": len(plan["leaves"]),
        "sourceFileCount": plan["parent"]["sourceFileCount"],
        **plan["verification"],
    }, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
