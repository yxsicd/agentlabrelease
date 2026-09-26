#!/usr/bin/env python3
"""Collect a public GitHub repair into an exact AgentLab natural-source record."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


REVISION = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
ISSUE_PATH = re.compile(r"/([^/]+)/([^/]+)/issues/([1-9][0-9]*)")
PULL_PATH = re.compile(r"/([^/]+)/([^/]+)/pull/([1-9][0-9]*)")
REPOSITORY_PATH = re.compile(r"/([^/]+)/([^/]+?)(?:\.git)?")
MAX_PATCH_BYTES = 50 * 1024 * 1024


def load_importer():
    path = Path(__file__).with_name("import-natural-case-source.py")
    spec = importlib.util.spec_from_file_location("agentlab_natural_case_source_import", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("natural-source importer cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


IMPORTER = load_importer()


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def parse_public_github_url(value: Any, pattern: re.Pattern[str], label: str) -> tuple[str, str, int]:
    require(isinstance(value, str) and value, f"{label} is required")
    parsed = urlsplit(value)
    require(
        parsed.scheme == "https"
        and parsed.hostname == "github.com"
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment,
        f"{label} must be a credential-free public github.com URL",
    )
    match = pattern.fullmatch(parsed.path.rstrip("/"))
    require(match is not None, f"{label} path is invalid")
    return match.group(1), match.group(2), int(match.group(3))


def parse_repository(value: Any) -> tuple[str, str]:
    require(isinstance(value, str) and value, "GitHub source repository is required")
    parsed = urlsplit(value)
    require(
        parsed.scheme == "https"
        and parsed.hostname == "github.com"
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment,
        "natural GitHub source repository must be a credential-free public HTTPS URL",
    )
    match = REPOSITORY_PATH.fullmatch(parsed.path.rstrip("/"))
    require(match is not None, "natural GitHub source repository path is invalid")
    return match.group(1), match.group(2)


def api_url(owner: str, repository: str, kind: str, number: int) -> str:
    return f"https://api.github.com/repos/{owner}/{repository}/{kind}/{number}"


class GitHubClient:
    def __init__(self, token: str | None):
        self.token = token

    def get(self, url: str, accept: str) -> bytes:
        parsed = urlsplit(url)
        require(parsed.scheme == "https" and parsed.hostname == "api.github.com", "GitHub API host is invalid")
        headers = {
            "Accept": accept,
            "User-Agent": "agentlab-natural-repair-collector",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            require(response.geturl() == url, "GitHub API redirected unexpectedly")
            return response.read()

    def json(self, url: str) -> dict[str, Any]:
        value = json.loads(self.get(url, "application/vnd.github+json"))
        require(isinstance(value, dict), "GitHub API response must be an object")
        return value

    def patch(self, url: str) -> bytes:
        value = self.get(url, "application/vnd.github.patch")
        require(len(value) <= MAX_PATCH_BYTES, "GitHub pull request patch exceeds the collection limit")
        require(value.startswith(b"From ") or value.startswith(b"diff --git "), "GitHub pull request patch is invalid")
        return value


def diff_sections(patch: bytes) -> list[tuple[str, bytes]]:
    marker = b"diff --git "
    starts = []
    offset = 0
    while True:
        index = patch.find(marker, offset)
        if index < 0:
            break
        starts.append(index)
        offset = index + len(marker)
    require(starts, "repair patch contains no file diffs")
    sections = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(patch)
        section = patch[start:end]
        header = section.splitlines()[0].decode("utf-8", errors="strict")
        parts = shlex.split(header)
        require(len(parts) == 4 and parts[:2] == ["diff", "--git"], "repair patch diff header is unsupported")
        right = parts[3]
        require(right.startswith("b/") and len(right) > 2, "repair patch destination path is invalid")
        sections.append((right[2:], section))
    return sections


def validate_spec(value: Any) -> dict[str, Any]:
    require(isinstance(value, dict), "GitHub natural repair specification must be an object")
    base_fields = {
        "schema", "id", "title", "sources", "affectedFiles", "testFiles",
        "issueUrls", "repairs", "testContract", "collectedAt", "automaticPromotion",
    }
    require(
        set(value) == base_fields or set(value) == base_fields | {"moduleBindings"},
        "GitHub natural repair specification fields differ",
    )
    require(value.get("schema") == "agentlab.github_natural_repair_spec.v1", "unsupported GitHub natural repair specification")
    require(value.get("automaticPromotion") is False, "GitHub natural repair can auto-promote")
    require(isinstance(value.get("id"), str) and TOKEN.fullmatch(value["id"]), "GitHub natural repair id is invalid")
    require(isinstance(value.get("title"), str) and value["title"].strip(), "GitHub natural repair title is required")
    require(isinstance(value.get("moduleBindings", {}), dict), "GitHub natural repair module bindings are invalid")
    require(isinstance(value.get("collectedAt"), str) and TIMESTAMP.fullmatch(value["collectedAt"]), "GitHub natural repair collectedAt is invalid")

    sources = value.get("sources")
    require(isinstance(sources, list) and len(sources) >= 2, "GitHub natural repair requires at least two sources")
    source_ids: set[str] = set()
    repositories: dict[str, tuple[str, str]] = {}
    for source in sources:
        require(isinstance(source, dict), "GitHub natural repair source is invalid")
        require(set(source) == {"id", "repository", "revision"}, "GitHub natural repair source fields differ")
        source_id = source.get("id")
        require(isinstance(source_id, str) and TOKEN.fullmatch(source_id) and source_id not in source_ids, "GitHub natural repair source id is invalid or duplicated")
        require(isinstance(source.get("revision"), str) and REVISION.fullmatch(source["revision"]), "GitHub natural repair source revision is not exact")
        repositories[source_id] = parse_repository(source.get("repository"))
        source_ids.add(source_id)

    issues = value.get("issueUrls")
    require(isinstance(issues, list) and issues, "GitHub natural repair issue URLs are required")
    parsed_issues = [parse_public_github_url(url, ISSUE_PATH, "GitHub issue URL") for url in issues]
    require(len(parsed_issues) == len(set(parsed_issues)), "GitHub natural repair issue URLs are duplicated")

    repairs = value.get("repairs")
    require(isinstance(repairs, list) and repairs, "GitHub natural repair pull requests are required")
    repaired_ids: set[str] = set()
    for repair in repairs:
        require(isinstance(repair, dict), "GitHub natural repair pull request is invalid")
        require(set(repair) == {"repositoryId", "pullRequestUrl", "fixRevision"}, "GitHub natural repair pull request fields differ")
        source_id = repair.get("repositoryId")
        require(source_id in source_ids and source_id not in repaired_ids, "GitHub natural repair repository is invalid or duplicated")
        owner, repository, _ = parse_public_github_url(repair.get("pullRequestUrl"), PULL_PATH, "GitHub pull request URL")
        require((owner.lower(), repository.lower()) == tuple(part.lower() for part in repositories[source_id]), "GitHub repair URL repository differs from the source")
        require(isinstance(repair.get("fixRevision"), str) and REVISION.fullmatch(repair["fixRevision"]), "GitHub natural repair fix revision is not exact")
        repaired_ids.add(source_id)
    require(repaired_ids == source_ids, "GitHub natural repair does not cover every source repository")

    affected = value.get("affectedFiles")
    require(isinstance(affected, list) and affected, "GitHub natural repair affected files are required")
    require(all(isinstance(row, dict) and set(row) == {"repositoryId", "path", "dependencyDepth"} for row in affected), "GitHub natural repair affected file fields differ")
    require(
        all(
            row["repositoryId"] in source_ids
            and isinstance(row["path"], str)
            and row["path"]
            and isinstance(row["dependencyDepth"], int)
            and row["dependencyDepth"] >= 0
            for row in affected
        ),
        "GitHub natural repair affected file is invalid",
    )
    affected_keys = [(row["repositoryId"], row["path"]) for row in affected]
    require(len(affected_keys) == len(set(affected_keys)), "GitHub natural repair affected files are duplicated")
    affected_ids = {row.get("repositoryId") for row in affected if isinstance(row, dict)}
    require(affected_ids == source_ids, "GitHub natural repair affected files do not cover every source repository")
    tests = value.get("testFiles")
    require(isinstance(tests, list) and tests, "GitHub natural repair test files are required")
    test_keys = []
    for row in tests:
        require(isinstance(row, dict) and set(row) == {"repositoryId", "path"}, "GitHub natural repair test file fields differ")
        require(row.get("repositoryId") in source_ids and isinstance(row.get("path"), str) and row["path"], "GitHub natural repair test file is invalid")
        test_keys.append((row["repositoryId"], row["path"]))
    require(len(test_keys) == len(set(test_keys)), "GitHub natural repair test files are duplicated")
    contract = value.get("testContract")
    require(isinstance(contract, dict) and set(contract) == {"observedFailureCheckIds", "preservationCheckIds"}, "GitHub natural repair test contract is invalid")
    return value


def collect(spec_path: Path, output: Path, method_revision: str, client: Any) -> dict[str, Any]:
    require(spec_path.is_file() and not spec_path.is_symlink(), "GitHub natural repair specification must be a regular file")
    require(not output.exists(), "GitHub natural repair output already exists")
    require(REVISION.fullmatch(method_revision) is not None, "collector method revision is invalid")
    spec = validate_spec(json.loads(spec_path.read_text(encoding="utf-8")))
    output.mkdir(parents=True)
    evidence_root = output / "evidence"
    evidence_root.mkdir()
    (output / "source-spec.json").write_bytes(canonical_bytes(spec))

    problems = []
    opened = []
    for url in spec["issueUrls"]:
        owner, repository, number = parse_public_github_url(url, ISSUE_PATH, "GitHub issue URL")
        issue = client.json(api_url(owner, repository, "issues", number))
        require(issue.get("html_url") == url.rstrip("/"), "GitHub issue identity differs")
        require(issue.get("state") == "closed" and issue.get("closed_at"), "GitHub issue is not closed")
        require(isinstance(issue.get("created_at"), str) and TIMESTAMP.fullmatch(issue["created_at"]), "GitHub issue creation time is invalid")
        problems.append(
            {
                "url": issue["html_url"],
                "number": issue.get("number"),
                "title": issue.get("title"),
                "body": issue.get("body"),
                "createdAt": issue["created_at"],
                "closedAt": issue["closed_at"],
            }
        )
        opened.append(issue["created_at"])
    problem_path = evidence_root / "issues.json"
    problem_path.write_bytes(canonical_bytes({"issues": problems}))

    sources = sorted(spec["sources"], key=lambda row: row["id"])
    sources_by_id = {row["id"]: row for row in sources}
    affected_by_id: dict[str, set[str]] = {source_id: set() for source_id in sources_by_id}
    for row in spec["affectedFiles"]:
        affected_by_id[row["repositoryId"]].add(row["path"])
    tests_by_id: dict[str, set[str]] = {source_id: set() for source_id in sources_by_id}
    for row in spec["testFiles"]:
        tests_by_id[row["repositoryId"]].add(row["path"])

    evidence = [
        {
            "id": "problem",
            "role": "problem-statement",
            "path": "evidence/issues.json",
            "sha256": digest(problem_path),
        }
    ]
    origin_repairs = []
    merged_times = []
    test_sections: list[bytes] = []
    for repair in sorted(spec["repairs"], key=lambda row: row["repositoryId"]):
        source_id = repair["repositoryId"]
        owner, repository, number = parse_public_github_url(repair["pullRequestUrl"], PULL_PATH, "GitHub pull request URL")
        endpoint = api_url(owner, repository, "pulls", number)
        pull = client.json(endpoint)
        require(pull.get("html_url") == repair["pullRequestUrl"].rstrip("/"), "GitHub pull request identity differs")
        require(pull.get("merged_at") and pull.get("merge_commit_sha") == repair["fixRevision"], "GitHub pull request is not merged at the declared fix revision")
        require(pull.get("base", {}).get("sha") == sources_by_id[source_id]["revision"], "GitHub pull request base differs from the pinned source revision")
        require(TIMESTAMP.fullmatch(pull["merged_at"]) is not None, "GitHub pull request merge time is invalid")
        patch = client.patch(endpoint)
        sections = diff_sections(patch)
        changed = {path for path, _ in sections}
        require(affected_by_id[source_id].issubset(changed), f"GitHub repair patch omits declared affected files for {source_id}")
        require(tests_by_id[source_id].issubset(changed), f"GitHub repair patch omits declared test files for {source_id}")
        selected_tests = [section for path, section in sections if path in tests_by_id[source_id]]
        test_sections.extend(selected_tests)
        patch_path = evidence_root / f"repair-{source_id}.patch"
        patch_path.write_bytes(patch)
        evidence.append(
            {
                "id": f"repair-{source_id}",
                "role": "repair-patch",
                "path": f"evidence/{patch_path.name}",
                "sha256": digest(patch_path),
            }
        )
        origin_repairs.append(
            {
                "repositoryId": source_id,
                "repairUrl": pull["html_url"],
                "fixRevision": repair["fixRevision"],
            }
        )
        merged_times.append(pull["merged_at"])
    require(test_sections, "GitHub repair contains no declared test patch")
    tests_path = evidence_root / "tests.patch"
    tests_path.write_bytes(b"".join(test_sections))
    evidence.append(
        {
            "id": "tests",
            "role": "test-patch",
            "path": "evidence/tests.patch",
            "sha256": digest(tests_path),
        }
    )

    source_set_sha256 = canonical_digest(
        {
            "schema": "agentlab.multi_repo_source_set.v1",
            "repositories": sources,
            "moduleBindings": spec.get("moduleBindings", {}),
        }
    )
    manifest = {
        "schema": "agentlab.natural_case_source_manifest.v1",
        "id": spec["id"],
        "strategy": "historical-repair",
        "title": spec["title"].strip(),
        "sourceSetSha256": source_set_sha256,
        "sources": sources,
        "moduleBindings": spec.get("moduleBindings", {}),
        "affectedFiles": spec["affectedFiles"],
        "evidence": evidence,
        "origin": {
            "issueUrls": sorted(url.rstrip("/") for url in spec["issueUrls"]),
            "repairs": origin_repairs,
            "openedAt": min(opened),
            "resolvedAt": max(merged_times),
        },
        "testContract": spec["testContract"],
        "sourceVisibility": "public",
        "collectedAt": spec["collectedAt"],
        "automaticPromotion": False,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_bytes(canonical_bytes(manifest))
    candidates = IMPORTER.build(manifest_path)
    candidates_path = output / "difficulty_candidates.json"
    candidates_path.write_bytes(canonical_bytes(candidates))
    receipt = {
        "schema": "agentlab.github_natural_repair_collection.v1",
        "methodRevision": method_revision,
        "sourceSpecSha256": digest(output / "source-spec.json"),
        "manifestSha256": digest(manifest_path),
        "candidateSourceSha256": digest(candidates_path),
        "sourceSetSha256": source_set_sha256,
        "candidateIds": [spec["id"]],
        "issueCount": len(problems),
        "repairCount": len(origin_repairs),
        "automaticPromotion": False,
    }
    receipt_path = output / "collection-receipt.json"
    receipt_path.write_bytes(canonical_bytes(receipt))
    return receipt


def validate_collection(root: Path, receipt_path: Path) -> dict[str, Any]:
    require(root.is_dir() and not root.is_symlink(), "GitHub natural repair collection root is invalid")
    require(receipt_path.is_file() and not receipt_path.is_symlink(), "GitHub natural repair collection receipt is invalid")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    require(isinstance(receipt, dict) and receipt.get("schema") == "agentlab.github_natural_repair_collection.v1", "unsupported GitHub natural repair collection receipt")
    require(isinstance(receipt.get("methodRevision"), str) and REVISION.fullmatch(receipt["methodRevision"]), "collection method revision is invalid")
    require(receipt.get("automaticPromotion") is False, "GitHub natural repair collection can auto-promote")
    paths = {
        "sourceSpecSha256": root / "source-spec.json",
        "manifestSha256": root / "manifest.json",
        "candidateSourceSha256": root / "difficulty_candidates.json",
    }
    for field, path in paths.items():
        require(path.is_file() and not path.is_symlink(), f"GitHub natural repair collection file is absent: {path.name}")
        require(receipt.get(field) == digest(path), f"GitHub natural repair collection {field} differs")
    validate_spec(json.loads(paths["sourceSpecSha256"].read_text(encoding="utf-8")))
    rebuilt = IMPORTER.build(paths["manifestSha256"])
    candidates = json.loads(paths["candidateSourceSha256"].read_text(encoding="utf-8"))
    require(candidates == rebuilt, "GitHub natural repair candidate source differs from exact manifest evidence")
    require(candidates.get("sourceSetSha256") == receipt.get("sourceSetSha256"), "GitHub natural repair collection source set differs")
    candidate_ids = [row.get("id") for row in candidates.get("candidates", []) if isinstance(row, dict)]
    require(candidate_ids == receipt.get("candidateIds"), "GitHub natural repair collection candidates differ")
    require(
        isinstance(receipt.get("issueCount"), int)
        and receipt["issueCount"] >= 1
        and isinstance(receipt.get("repairCount"), int)
        and receipt["repairCount"] >= 2,
        "GitHub natural repair collection counts are invalid",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--spec", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--method-revision", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--root", type=Path, required=True)
    validate.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            receipt = collect(args.spec, args.output, args.method_revision, GitHubClient(os.environ.get("GITHUB_TOKEN")))
        else:
            receipt = validate_collection(args.root, args.receipt)
        print(json.dumps({"ok": True, **receipt}, sort_keys=True))
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, UnicodeDecodeError, HTTPError, URLError) as error:
        print(f"GitHub natural repair collection failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
