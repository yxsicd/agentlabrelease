#!/usr/bin/env python3
"""Prefetch exact source blobs with resumable partial-clone stages."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


class PrefetchError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise PrefetchError(message)


def git(root: Path, *arguments: str, lazy: bool = True) -> bytes:
    environment = os.environ.copy()
    if not lazy:
        environment["GIT_NO_LAZY_FETCH"] = "1"
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        check=False,
        env=environment,
    )
    if completed.returncode != 0:
        raise PrefetchError(
            f"git {' '.join(arguments)} failed for {root}: "
            f"{completed.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return completed.stdout


def source_blobs(root: Path, revision: str) -> list[tuple[str, str]]:
    rows = []
    for record in git(root, "ls-tree", "-r", "-z", revision).split(b"\0"):
        if not record:
            continue
        metadata, separator, raw_path = record.partition(b"\t")
        parts = metadata.split()
        require(separator == b"\t" and len(parts) == 3 and parts[1] == b"blob", "invalid Git tree row")
        path = raw_path.decode("utf-8")
        if path.endswith((".ets", ".ts")):
            rows.append((parts[2].decode("ascii"), path))
    return rows


def missing_blobs(root: Path, rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    if not rows:
        return []
    completed = subprocess.run(
        ["git", "-C", str(root), "cat-file", "--batch-check=%(objectname) %(objecttype)"],
        input="".join(f"{oid}\n" for oid, _ in rows).encode("ascii"),
        capture_output=True,
        check=False,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    )
    require(completed.returncode == 0, "cannot inspect partial-clone objects")
    states = completed.stdout.decode("ascii").splitlines()
    require(len(states) == len(rows), "partial-clone object inventory differs")
    return [row for row, state in zip(rows, states) if state.endswith(" missing")]


def refetch_small_blobs(root: Path, revision: str) -> None:
    for limit in (8192, 32768):
        errors = []
        for attempt in range(1, 4):
            completed = subprocess.run(
                [
                    "git", "-C", str(root),
                    "-c", "protocol.file.allow=never",
                    "-c", "protocol.ext.allow=never",
                    "-c", "protocol.ssh.allow=never",
                    "-c", "http.version=HTTP/2",
                    "fetch", "--quiet", "--refetch", "--no-write-fetch-head",
                    f"--filter=blob:limit={limit}", "origin", revision,
                ],
                capture_output=True,
                check=False,
            )
            if completed.returncode == 0:
                break
            errors.append(f"attempt {attempt}: {completed.stderr.decode('utf-8', errors='replace').strip()}")
            if attempt < 3:
                time.sleep(2 ** (attempt - 1))
        else:
            raise PrefetchError("filtered Git refetch failed after bounded retries: " + " | ".join(errors))


def prefetch(manifest_path: Path) -> dict[str, Any]:
    require(manifest_path.is_file() and not manifest_path.is_symlink(), "manifest must be a regular file")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("schema") == "agentlab.multi_repo_manifest.v1", "unsupported manifest")
    repositories = manifest.get("repositories")
    require(isinstance(repositories, list) and len(repositories) >= 2, "manifest requires multiple repositories")
    receipt_rows = []
    for repository in repositories:
        require(isinstance(repository, dict), "repository row is invalid")
        root = Path(repository.get("root", ""))
        revision = repository.get("revision")
        source = repository.get("repository")
        require(root.is_dir() and isinstance(revision, str) and isinstance(source, str), "repository row is incomplete")
        remote = git(root, "remote", "get-url", "origin", lazy=False).decode("utf-8").strip()
        commit = git(root, "rev-parse", f"{revision}^{{commit}}", lazy=False).decode("ascii").strip()
        require(remote == source, "repository origin differs from manifest")
        require(commit == revision, "repository commit differs from manifest")
        rows = source_blobs(root, revision)
        initial_missing = missing_blobs(root, rows)
        if len(initial_missing) > 128:
            refetch_small_blobs(root, revision)
        missing = missing_blobs(root, rows)
        remaining = len(missing)
        receipt_rows.append({
            "id": repository.get("id"),
            "sourceBlobs": len(rows),
            "alreadyPresent": len(rows) - len(initial_missing),
            "fetched": len(initial_missing) - remaining,
            "remaining": remaining,
            "transport": "git-filtered-promisor",
        })
    return {
        "schema": "agentlab.multi_repo_blob_prefetch.v1",
        "repositories": receipt_rows,
        "authority": "git-object-id",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
        receipt = prefetch(args.manifest)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "repositories": len(receipt["repositories"])}, sort_keys=True))
    except (PrefetchError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"multi-repository source prefetch invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
