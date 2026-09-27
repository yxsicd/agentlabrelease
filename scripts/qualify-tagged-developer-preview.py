#!/usr/bin/env python3
"""Close a developer preview only after an exact tagged clean install."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


class QualificationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise QualificationError(message)


def load(path: pathlib.Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QualificationError(f"cannot load {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(root: pathlib.Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise QualificationError(
            f"git {' '.join(args)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def validate_tag(root: pathlib.Path, tag: str, tag_sha: str, source_sha: str) -> None:
    require(REVISION.fullmatch(tag_sha) is not None, "tag SHA is invalid")
    require(git(root, "rev-parse", "HEAD") == tag_sha, "checkout is not the declared tag commit")
    require(
        git(root, "rev-parse", f"refs/tags/{tag}^{{commit}}") == tag_sha,
        "immutable tag does not resolve to the checkout",
    )
    completed = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", source_sha, tag_sha],
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, "release source is not an ancestor of the tag")


def qualify(
    closure_path: pathlib.Path,
    asset_receipt_path: pathlib.Path,
    harmony_receipt_path: pathlib.Path,
    install_summary_path: pathlib.Path,
    environment_lock_path: pathlib.Path,
    *,
    tag: str,
    tag_sha: str,
    repository: str,
    run_id: str,
    event: str,
) -> dict[str, Any]:
    closure = load(closure_path, "release closure")
    asset_receipt = load(asset_receipt_path, "immutable asset receipt")
    harmony_receipt = load(harmony_receipt_path, "Harmony acceptance receipt")
    install = load(install_summary_path, "clean install summary")
    lock = load(environment_lock_path, "materialized environment lock")
    closure_sha = sha256(closure_path)

    require(closure.get("schema") == "agentlab.release_closure.v1", "unsupported closure schema")
    require(closure.get("status") == "developer-preview-candidate", "closure is not a developer preview candidate")
    require(closure.get("releaseTag") == tag, "workflow tag differs from closure")
    require(event == "workflow_dispatch", "qualification must be explicitly dispatched")
    require(REVISION.fullmatch(tag_sha) is not None, "tag SHA is invalid")
    require(isinstance(run_id, str) and run_id.isdigit() and int(run_id) > 0, "GitHub run id is invalid")
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is not None, "repository is invalid")
    source_sha = (closure.get("sources") or {}).get("releaseGitSha")
    require(isinstance(source_sha, str) and REVISION.fullmatch(source_sha) is not None, "release source revision is invalid")
    qualification_plan = closure.get("qualificationPlan") or {}
    require(qualification_plan.get("taggedCleanInstallRequired") is True, "closure does not require tagged clean install")
    require(qualification_plan.get("linuxEmulatorAcceptanceRequired") is True, "closure does not require Harmony acceptance")
    require(qualification_plan.get("automaticPromotion") is False, "closure may not auto-promote")

    require(asset_receipt.get("schema") == "agentlab.release_graph_validation.v1", "unsupported asset receipt")
    require(asset_receipt.get("remote") is True and asset_receipt.get("automaticPromotion") is False, "asset receipt is not a remote non-promoting verification")
    asset_closures = asset_receipt.get("closures")
    require(isinstance(asset_closures, list) and len(asset_closures) == 1, "asset receipt closure count differs")
    asset_closure = asset_closures[0]
    require(asset_closure.get("sha256") == closure_sha and asset_closure.get("releaseTag") == tag, "asset receipt is bound to another closure")
    require(asset_closure.get("assetCount") == len(closure.get("assets") or []), "asset receipt count differs")
    require(len(asset_closure.get("remoteAssets") or []) == len(closure.get("assets") or []), "not every closure asset was observed remotely")

    require(harmony_receipt.get("schema") == "agentlab.release_harmony_acceptance.v1", "unsupported Harmony receipt")
    require(harmony_receipt.get("status") == "accepted-developer-preview-review-required", "Harmony acceptance did not pass")
    require(harmony_receipt.get("releaseTag") == tag and harmony_receipt.get("releaseGitSha") == source_sha, "Harmony receipt release identity differs")
    require((harmony_receipt.get("closure") or {}).get("sha256") == closure_sha, "Harmony receipt is bound to another closure")
    require(harmony_receipt.get("automaticPromotion") is False, "Harmony receipt may not auto-promote")

    assets = {row.get("id"): row for row in closure.get("assets", []) if isinstance(row, dict)}
    lock_asset = assets.get("environment-lock.json")
    require(isinstance(lock_asset, dict), "closure environment lock asset is absent")
    require(sha256(environment_lock_path) == lock_asset.get("sha256"), "materialized environment lock differs from closure")
    require(install.get("schema") == "agentlab.public_install_deploy_smoke.v1", "unsupported clean install summary")
    require(install.get("ok") is True, "tagged clean install did not pass")
    checks = install.get("checks")
    require(isinstance(checks, dict) and checks and all(value is True for value in checks.values()), "tagged clean install checks are incomplete")
    require(install.get("sourceRevision") == lock.get("sourceRevision"), "clean install source differs from the materialized lock")

    return {
        "schema": "agentlab.developer_preview_qualification.v1",
        "status": "qualified-developer-preview-review-required",
        "releaseTag": tag,
        "tagGitSha": tag_sha,
        "releaseGitSha": source_sha,
        "closure": {"sha256": closure_sha, "assetCount": len(closure["assets"])},
        "immutableAssets": {"receiptSha256": sha256(asset_receipt_path), "remoteAssetCount": len(asset_closure["remoteAssets"])},
        "harmonyAcceptance": {"receiptSha256": sha256(harmony_receipt_path), "environmentIdentity": harmony_receipt["environmentIdentity"]},
        "taggedCleanInstall": {"summarySha256": sha256(install_summary_path), "environmentLockSha256": sha256(environment_lock_path), "checks": checks},
        "github": {"repository": repository, "runId": run_id, "event": event, "runUrl": f"https://github.com/{repository}/actions/runs/{run_id}"},
        "qualificationBoundary": {
            "qualified": ["exact immutable tag checkout", "all closure assets observed on immutable GitHub releases", "release-bound Linux Harmony emulator acceptance", "fresh-runner closure installation and basic deployment"],
            "notQualified": ["stable API compatibility", "absolute power or thermal measurement", "physical-device behavior", "automatic channel promotion"],
        },
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closure", type=pathlib.Path, required=True)
    parser.add_argument("--asset-receipt", type=pathlib.Path, required=True)
    parser.add_argument("--harmony-receipt", type=pathlib.Path, required=True)
    parser.add_argument("--install-summary", type=pathlib.Path, required=True)
    parser.add_argument("--environment-lock", type=pathlib.Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--tag-sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--git-root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite qualification receipt: {args.output}")
    try:
        closure = load(args.closure, "release closure")
        source_sha = (closure.get("sources") or {}).get("releaseGitSha")
        require(isinstance(source_sha, str), "release source revision is absent")
        validate_tag(args.git_root.resolve(), args.tag, args.tag_sha, source_sha)
        receipt = qualify(
            args.closure.resolve(), args.asset_receipt.resolve(), args.harmony_receipt.resolve(),
            args.install_summary.resolve(), args.environment_lock.resolve(), tag=args.tag,
            tag_sha=args.tag_sha, repository=args.repository, run_id=args.run_id,
            event=args.event,
        )
    except QualificationError as error:
        raise SystemExit(f"developer preview qualification invalid: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"releaseTag": receipt["releaseTag"], "status": receipt["status"], "receiptSha256": sha256(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
