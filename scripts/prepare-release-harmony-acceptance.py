#!/usr/bin/env python3
"""Bind an immutable release closure to a fresh Harmony assessed campaign plan."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import re
from typing import Any


CLOSURE_SCHEMA = "agentlab.release_closure.v1"
PLAN_SCHEMA = "agentlab.harmony_assessed_campaign_plan.v1"
ACCEPTANCE_PLAN_SCHEMA = "agentlab.release_harmony_acceptance_plan.v1"
REVISION = re.compile(r"[0-9a-f]{40}")
REQUIRED_ASSET_IDS = (
    "harmony-emulator-linux-x64-26.0.0.821.json",
    "commandline-tools-linux-x64-26.0.0.821.tar.zst",
    "HarmonyOS-7.0.0-phone_all_x86.tar.zst",
    "harmony-cli-archive",
    "harmony-build-kit-archive",
)
PROGRAM_BASENAMES = {
    "build": "build-harmony-assessed-workspace.py",
    "standardTest": "run-harmony-assessed-standard-test.py",
    "loop": "run-harmony-evaluation-loop.py",
    "run": "run-harmony-evaluation-case.py",
    "compose": "compose-harmony-assessed-decision.py",
    "collect": "collect-case-attempts.py",
    "score": "score-case-discrimination.py",
    "feedback": "derive-assessment-feedback.py",
}


class AcceptancePlanError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptancePlanError(message)


def load(path: pathlib.Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptancePlanError(f"cannot load {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def binding(path: pathlib.Path) -> dict[str, str]:
    resolved = path.resolve()
    require(resolved.is_file() and not resolved.is_symlink(), f"bound file is absent or unsafe: {resolved}")
    return {"path": str(resolved), "sha256": sha256(resolved)}


def validate_closure(closure: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    require(closure.get("schema") == CLOSURE_SCHEMA, "unsupported release closure schema")
    require(closure.get("status") == "developer-preview-candidate", "closure is not a developer preview candidate")
    sources = closure.get("sources")
    require(isinstance(sources, dict), "closure sources are required")
    revision = sources.get("releaseGitSha")
    require(isinstance(revision, str) and REVISION.fullmatch(revision) is not None, "closure release source revision is invalid")
    qualification = closure.get("qualificationPlan")
    require(isinstance(qualification, dict), "closure qualification plan is required")
    require(qualification.get("sourceGitSha") == revision, "closure qualification source differs")
    require(qualification.get("linuxEmulatorAcceptanceRequired") is True, "closure does not require Linux emulator acceptance")
    require(qualification.get("automaticPromotion") is False, "closure may not auto-promote")
    assets = closure.get("assets")
    require(isinstance(assets, list), "closure assets are required")
    by_id = {row.get("id"): row for row in assets if isinstance(row, dict)}
    require(len(by_id) == len(assets), "closure asset ids must be unique")
    selected = []
    for asset_id in REQUIRED_ASSET_IDS:
        asset = by_id.get(asset_id)
        require(isinstance(asset, dict), f"closure is missing required Harmony asset: {asset_id}")
        require(re.fullmatch(r"[0-9a-f]{64}", str(asset.get("sha256"))) is not None, f"Harmony asset digest is invalid: {asset_id}")
        require(isinstance(asset.get("bytes"), int) and asset["bytes"] > 0, f"Harmony asset size is invalid: {asset_id}")
        require(isinstance(asset.get("url"), str) and asset["url"].startswith("https://"), f"Harmony asset URL is invalid: {asset_id}")
        selected.append({key: asset[key] for key in ("id", "url", "sha256", "bytes", "immutableRef")})
    return revision, selected


def prepare(
    closure_path: pathlib.Path,
    template_path: pathlib.Path,
    repository_root: pathlib.Path,
    campaign_id: str,
) -> dict[str, Any]:
    closure = load(closure_path, "release closure")
    template = load(template_path, "campaign template")
    revision, assets = validate_closure(closure)
    require(template.get("schema") == PLAN_SCHEMA, "unsupported campaign template schema")
    require(template.get("automaticPromotion") is False, "campaign template may not auto-promote")
    require(re.fullmatch(r"[A-Za-z0-9_.:-]+", campaign_id) is not None, "campaign id is not a safe token")
    root = repository_root.resolve()
    require(root.is_dir(), "repository root is absent")

    plan = copy.deepcopy(template)
    plan["campaignId"] = campaign_id
    plan["methodRevision"] = revision
    plan["automaticPromotion"] = False
    plan["releaseAcceptance"] = {
        "schema": ACCEPTANCE_PLAN_SCHEMA,
        "releaseTag": closure["releaseTag"],
        "releaseVersion": closure["releaseVersion"],
        "releaseGitSha": revision,
        "closure": binding(closure_path),
        "requiredAssets": assets,
        "automaticPromotion": False,
    }

    scripts = root / "scripts"
    plan["programs"] = {
        name: binding(scripts / basename) for name, basename in PROGRAM_BASENAMES.items()
    }
    plan["standardTest"]["sourceExecutor"] = binding(scripts / "run-harmony-source-standard-test.py")
    plan["device"]["runtime"]["runner"] = str((scripts / "agentlab-harmony-emulator.sh").resolve())
    plan["device"]["runtime"]["runnerSha256"] = sha256(scripts / "agentlab-harmony-emulator.sh")

    oracle = plan["device"].get("functionalOracle")
    require(isinstance(oracle, dict), "campaign template functional Oracle is required")
    oracle_name = pathlib.Path(str(oracle.get("path", ""))).name
    require(bool(oracle_name), "campaign template functional Oracle path is invalid")
    current_oracle = root / "examples/harmony-multi-repo" / oracle_name
    oracle.update(binding(current_oracle))
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closure", type=pathlib.Path, required=True)
    parser.add_argument("--template-plan", type=pathlib.Path, required=True)
    parser.add_argument("--repository-root", type=pathlib.Path, required=True)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite acceptance plan: {args.output}")
    try:
        plan = prepare(args.closure, args.template_plan, args.repository_root, args.campaign_id)
    except AcceptancePlanError as error:
        raise SystemExit(f"release Harmony acceptance plan invalid: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"campaignId": plan["campaignId"], "releaseTag": plan["releaseAcceptance"]["releaseTag"], "planSha256": sha256(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
