#!/usr/bin/env python3
"""Validate component identities and decide whether a component can be reused."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
from typing import Any

REGISTRY_SCHEMA = "agentlab.component_registry.v1"
INPUT_SCHEMA = "agentlab.component_input.v1"
IDENTITY_MODES = {"git-tree-v1", "external-payload-v1", "legacy-published-v1"}
MUTABLE_REFS = {"aldev", "almain", "alprod", "latest", "current", "main"}


def fail(message: str) -> None:
    raise ValueError(message)


def is_hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and re.fullmatch(r"[0-9a-f]+", value) is not None
    )


def canonical_digest(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def published_asset_basis(component: dict[str, Any]) -> dict[str, Any]:
    assets = [
        {"id": item["id"], "bytes": item["bytes"], "sha256": item["sha256"]}
        for item in component["assets"]
    ]
    return {
        "schema": INPUT_SCHEMA,
        "component": component["id"],
        "platform": component["platform"],
        "publishedAssets": sorted(assets, key=lambda item: item["id"]),
    }


def git_object(repo: pathlib.Path, revision: str, path: str) -> dict[str, str]:
    spec = f"{revision}:{path}"
    oid = subprocess.run(
        ["git", "rev-parse", spec], cwd=repo, text=True, capture_output=True, check=True
    ).stdout.strip()
    kind = subprocess.run(
        ["git", "cat-file", "-t", oid], cwd=repo, text=True, capture_output=True, check=True
    ).stdout.strip()
    return {"path": path, "objectType": kind, "oid": oid}


def git_tree_basis(
    component: dict[str, Any], repo: pathlib.Path, revision: str
) -> dict[str, Any]:
    source = component["source"]
    identity = component["inputIdentity"]
    owned = sorted(set(source.get("ownedPaths") or []))
    recipes = sorted(set(identity.get("buildRecipePaths") or []))
    if not owned:
        fail(f"{component['id']} git-tree-v1 requires ownedPaths")
    if len(owned) != len(source.get("ownedPaths") or []):
        fail(f"{component['id']} ownedPaths must be unique")
    if len(recipes) != len(identity.get("buildRecipePaths") or []):
        fail(f"{component['id']} buildRecipePaths must be unique")
    return {
        "schema": INPUT_SCHEMA,
        "component": component["id"],
        "platform": component["platform"],
        "repository": source["repository"],
        "sourceObjects": [git_object(repo, revision, path) for path in owned],
        "buildRecipeObjects": [git_object(repo, revision, path) for path in recipes],
        "dependencies": identity.get("dependencies") or {},
    }


def validate_asset(component_id: str, asset: Any) -> None:
    if not isinstance(asset, dict):
        fail(f"{component_id} asset must be an object")
    for field in ("id", "url", "bytes", "sha256"):
        if field not in asset:
            fail(f"{component_id} asset missing {field}")
    if not isinstance(asset["url"], str) or not asset["url"].startswith("https://"):
        fail(f"{component_id} asset URL must use https")
    if not isinstance(asset["bytes"], int) or asset["bytes"] <= 0:
        fail(f"{component_id} asset bytes must be positive")
    if not is_hex(asset["sha256"], 64):
        fail(f"{component_id} asset sha256 must be exact")


def validate_component(component: Any) -> None:
    if not isinstance(component, dict):
        fail("component must be an object")
    for field in ("id", "kind", "platform", "status", "immutableRef", "source", "inputIdentity", "assets"):
        if field not in component:
            fail(f"component missing {field}")
    component_id = component["id"]
    if not isinstance(component_id, str) or not component_id:
        fail("component id required")
    if str(component["immutableRef"]).lower() in MUTABLE_REFS:
        fail(f"{component_id} immutableRef must not be mutable")
    if not isinstance(component["assets"], list) or not component["assets"]:
        fail(f"{component_id} assets required")
    asset_ids: set[str] = set()
    for asset in component["assets"]:
        validate_asset(component_id, asset)
        if asset["id"] in asset_ids:
            fail(f"{component_id} has duplicate asset id")
        asset_ids.add(asset["id"])

    source = component["source"]
    if not isinstance(source, dict) or not isinstance(source.get("repository"), str):
        fail(f"{component_id} source repository required")
    revision = source.get("revision")
    if revision is not None and not is_hex(revision, 40):
        fail(f"{component_id} source revision must be exact 40-hex")

    identity = component["inputIdentity"]
    if not isinstance(identity, dict) or identity.get("mode") not in IDENTITY_MODES:
        fail(f"{component_id} has unsupported input identity mode")
    if not is_hex(identity.get("effectiveInputDigest"), 64):
        fail(f"{component_id} effectiveInputDigest must be exact")
    if identity["mode"] in {"external-payload-v1", "legacy-published-v1"}:
        expected = canonical_digest(published_asset_basis(component))
        if identity["effectiveInputDigest"] != expected:
            fail(f"{component_id} published asset identity drift")
    if identity["mode"] == "git-tree-v1":
        if not source.get("ownedPaths"):
            fail(f"{component_id} git-tree-v1 requires ownedPaths")


def validate_registry(value: dict[str, Any]) -> None:
    if value.get("schema") != REGISTRY_SCHEMA:
        fail("unsupported component registry schema")
    if not is_hex(value.get("generatedFromRevision"), 40):
        fail("generatedFromRevision must be exact 40-hex")
    policy = value.get("policy")
    if not isinstance(policy, dict) or policy.get("unchangedAction") != "reuse":
        fail("registry policy must require reuse for unchanged components")
    components = value.get("components")
    if not isinstance(components, list) or not components:
        fail("registry components required")
    ids: set[str] = set()
    for component in components:
        validate_component(component)
        if component["id"] in ids:
            fail("duplicate component id")
        ids.add(component["id"])


def load_registry(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail("registry must contain an object")
    validate_registry(value)
    return value


def find_component(registry: dict[str, Any], component_id: str) -> dict[str, Any]:
    matches = [item for item in registry["components"] if item["id"] == component_id]
    if len(matches) != 1:
        fail(f"component not found: {component_id}")
    return matches[0]


def plan(
    component: dict[str, Any], repo: pathlib.Path | None = None, revision: str | None = None
) -> dict[str, Any]:
    identity = component["inputIdentity"]
    mode = identity["mode"]
    if mode == "git-tree-v1":
        if repo is None or revision is None:
            fail("git-tree-v1 planning requires --repo and --revision")
        basis = git_tree_basis(component, repo, revision)
        actual = canonical_digest(basis)
        action = "reuse" if actual == identity["effectiveInputDigest"] else "rebuild"
        automatic = True
    else:
        basis = published_asset_basis(component)
        actual = canonical_digest(basis)
        action = "reuse"
        automatic = mode == "external-payload-v1"
    return {
        "schema": "agentlab.component_reuse_plan.v1",
        "component": component["id"],
        "auditRevision": revision or component["source"].get("revision"),
        "identityMode": mode,
        "expectedInputDigest": identity["effectiveInputDigest"],
        "actualInputDigest": actual,
        "action": action,
        "automaticSourceImpactDecision": automatic,
        "basis": basis,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--registry", required=True)
    planner = sub.add_parser("plan")
    planner.add_argument("--registry", required=True)
    planner.add_argument("--component", required=True)
    planner.add_argument("--repo")
    planner.add_argument("--revision")
    args = parser.parse_args()

    registry = load_registry(pathlib.Path(args.registry))
    if args.command == "validate":
        print(json.dumps({"schema": "agentlab.component_registry_validation.v1", "ok": True}))
        return 0
    component = find_component(registry, args.component)
    result = plan(
        component,
        pathlib.Path(args.repo) if args.repo else None,
        args.revision,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
