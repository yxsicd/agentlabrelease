#!/usr/bin/env python3
"""Create exact, reproducible Git inputs for multi-repository construction."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


REPOSITORIES = ("app", "contracts", "service")
FIXED_DATE = "2026-01-01T00:00:00Z"


def run_git(root: Path, *arguments: str) -> str:
    environment = dict(os.environ)
    environment.update(
        {
            "GIT_AUTHOR_NAME": "AgentLab fixture",
            "GIT_AUTHOR_EMAIL": "fixture@agentlab.invalid",
            "GIT_AUTHOR_DATE": FIXED_DATE,
            "GIT_COMMITTER_NAME": "AgentLab fixture",
            "GIT_COMMITTER_EMAIL": "fixture@agentlab.invalid",
            "GIT_COMMITTER_DATE": FIXED_DATE,
        }
    )
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        raise ValueError("refusing to overwrite fixture output")
    missing = [name for name in REPOSITORIES if not (args.source / name).is_dir()]
    if missing:
        raise ValueError(f"missing fixture repositories: {', '.join(missing)}")

    args.output.mkdir(parents=True)
    repositories = []
    for name in REPOSITORIES:
        root = args.output / "repositories" / name
        shutil.copytree(args.source / name, root)
        run_git(root, "init", "--quiet")
        run_git(root, "add", ".")
        run_git(root, "commit", "--quiet", "--message", "pinned baseline")
        revision = run_git(root, "rev-parse", "HEAD")
        repositories.append(
            {
                "id": name,
                "repository": f"fixture://multi-repo-case/{name}",
                "root": str(root.resolve()),
                "revision": revision,
            }
        )

    manifest = {
        "schema": "agentlab.multi_repo_manifest.v1",
        "repositories": repositories,
        "moduleBindings": {
            "@demo/contracts": {
                "repositoryId": "contracts",
                "path": "src/policy.ts",
            },
            "@demo/service": {
                "repositoryId": "service",
                "path": "src/reservation.ts",
            },
        },
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"schema": "agentlab.multi_repo_fixture.v1", "repositories": repositories}))


if __name__ == "__main__":
    main()
