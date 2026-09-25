#!/usr/bin/env python3
"""Materialize an exact public multi-repository source specification."""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlsplit


REVISION = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[A-Za-z0-9_.-]{1,80}")


class SourcePreparationError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise SourcePreparationError(message)


def safe_repository(value: Any) -> str:
    require(isinstance(value, str) and len(value) <= 2048, "repository URL is invalid")
    parsed = urlsplit(value)
    require(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and parsed.port in (None, 443)
        and not parsed.query
        and not parsed.fragment,
        "repository must be a credential-free HTTPS URL",
    )
    hostname = parsed.hostname.lower()
    require(hostname not in {"localhost", "localhost.localdomain"} and not hostname.endswith(".local"), "repository host is local")
    try:
        address = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        address = None
    require(address is None or address.is_global, "repository host is not globally routable")
    return value


def safe_binding_path(value: Any) -> str:
    require(isinstance(value, str) and value and "\\" not in value, "module binding path is invalid")
    path = PurePosixPath(value)
    require(
        not path.is_absolute()
        and path.as_posix() == value
        and all(part not in ("", ".", "..") for part in path.parts),
        "module binding path is unsafe",
    )
    return value


def validate_spec(value: Any) -> dict[str, Any]:
    require(isinstance(value, dict), "source specification must be an object")
    require(value.get("schema") == "agentlab.multi_repo_source_spec.v1", "unsupported source specification")
    require(value.get("automaticPromotion") is False, "source specification can auto-promote")
    sources = value.get("sources")
    require(isinstance(sources, list) and 2 <= len(sources) <= 16, "source specification requires two to sixteen repositories")
    normalized_sources = []
    ids: set[str] = set()
    identities: set[tuple[str, str]] = set()
    for row in sources:
        require(isinstance(row, dict) and set(row) == {"id", "repository", "revision"}, "source fields differ")
        source_id = row.get("id")
        repository = safe_repository(row.get("repository"))
        revision = row.get("revision")
        require(isinstance(source_id, str) and TOKEN.fullmatch(source_id) and source_id not in ids, "source id is invalid or duplicated")
        require(isinstance(revision, str) and REVISION.fullmatch(revision), f"{source_id} revision must be an exact commit")
        require((repository, revision) not in identities, "source repository revision is duplicated")
        ids.add(source_id)
        identities.add((repository, revision))
        normalized_sources.append({"id": source_id, "repository": repository, "revision": revision})
    bindings = value.get("moduleBindings")
    require(isinstance(bindings, dict), "moduleBindings must be an object")
    normalized_bindings = {}
    for specifier, binding in sorted(bindings.items()):
        require(isinstance(specifier, str) and specifier and len(specifier) <= 512, "module specifier is invalid")
        require(isinstance(binding, dict) and set(binding) == {"repositoryId", "path"}, f"{specifier} binding fields differ")
        repository_id = binding.get("repositoryId")
        require(repository_id in ids, f"{specifier} binding repository is absent")
        normalized_bindings[specifier] = {
            "repositoryId": repository_id,
            "path": safe_binding_path(binding.get("path")),
        }
    return {
        "schema": "agentlab.multi_repo_source_spec.v1",
        "sources": sorted(normalized_sources, key=lambda row: row["id"]),
        "moduleBindings": normalized_bindings,
        "automaticPromotion": False,
    }


def run_git(*arguments: str, cwd: Path | None = None, attempts: int = 1) -> str:
    require(isinstance(attempts, int) and 1 <= attempts <= 3, "git attempt count is invalid")
    command = [
        "git",
        "-c", "protocol.file.allow=never",
        "-c", "protocol.ext.allow=never",
        "-c", "protocol.ssh.allow=never",
        "-c", "http.version=HTTP/1.1",
        *arguments,
    ]
    errors = []
    for attempt in range(1, attempts + 1):
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            return completed.stdout.strip()
        errors.append(f"attempt {attempt}: {completed.stderr.strip()}")
        if attempt < attempts:
            time.sleep(2 ** (attempt - 1))
    raise SourcePreparationError("git operation failed after bounded retries: " + " | ".join(errors))


def prepare(spec_path: Path, output: Path) -> dict[str, Any]:
    require(spec_path.is_file() and not spec_path.is_symlink(), "source specification must be a regular file")
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SourcePreparationError(f"cannot read source specification: {error}") from error
    spec = validate_spec(raw)
    require(not output.exists(), f"refusing to overwrite output: {output}")
    repositories_root = output / "repositories"
    repositories_root.mkdir(parents=True)
    manifest_sources = []
    for source in spec["sources"]:
        root = repositories_root / source["id"]
        root.mkdir()
        run_git("init", "--quiet", cwd=root)
        run_git("remote", "add", "origin", source["repository"], cwd=root)
        run_git(
            "fetch", "--quiet", "--depth=1", "--filter=blob:none",
            "origin", source["revision"],
            cwd=root, attempts=3,
        )
        fetched = run_git("rev-parse", "FETCH_HEAD^{commit}", cwd=root)
        require(fetched == source["revision"], f"{source['id']} fetched commit differs")
        run_git("update-ref", "HEAD", source["revision"], cwd=root)
        manifest_sources.append({**source, "root": str(root.resolve())})
    (output / "source-spec.json").write_text(
        json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema": "agentlab.multi_repo_manifest.v1",
        "repositories": manifest_sources,
        "moduleBindings": spec["moduleBindings"],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = prepare(args.spec, args.output)
        print(json.dumps({"ok": True, "repositoryCount": len(manifest["repositories"])}, sort_keys=True))
    except (SourcePreparationError, OSError, ValueError) as error:
        print(f"multi-repository source preparation invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
