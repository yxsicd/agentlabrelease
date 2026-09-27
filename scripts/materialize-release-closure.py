#!/usr/bin/env python3
"""Materialize the small bootstrap inputs of an immutable release closure."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import urllib.request
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]


class MaterializationError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise MaterializationError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: pathlib.Path, label: str) -> tuple[dict[str, Any], bytes]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    raw = path.read_bytes()
    value = json.loads(raw)
    require(isinstance(value, dict), f"{label} must be an object")
    return value, raw


def validator_module():
    path = ROOT / "scripts/validate-release-graph.py"
    spec = importlib.util.spec_from_file_location("agentlab_materialize_release_graph", path)
    require(spec is not None and spec.loader is not None, "release graph validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch(asset: dict[str, Any]) -> bytes:
    headers = {"User-Agent": "agentlab-release-closure-materializer"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(asset["url"], headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read(asset["bytes"] + 1)
    require(len(data) == asset["bytes"], f"downloaded size differs for {asset['id']}")
    require(digest(data) == asset["sha256"], f"downloaded digest differs for {asset['id']}")
    return data


def exactly_one(assets: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    matches = [asset for asset in assets if asset.get("kind") == kind]
    require(len(matches) == 1, f"closure requires exactly one {kind} bootstrap asset")
    return matches[0]


def materialize(
    closure: dict[str, Any],
    closure_bytes: bytes,
    registry: dict[str, Any],
    registry_bytes: bytes,
    lock_bytes: bytes,
    control_bytes: bytes,
    output: pathlib.Path,
) -> dict[str, Any]:
    validator_module().validate_closure(closure, registry, registry_bytes)
    assets = closure["assets"]
    lock_asset = exactly_one(assets, "composition")
    control_asset = exactly_one(assets, "control")
    require(
        len(lock_bytes) == lock_asset["bytes"] and digest(lock_bytes) == lock_asset["sha256"],
        "environment lock bytes differ from closure",
    )
    require(
        len(control_bytes) == control_asset["bytes"]
        and digest(control_bytes) == control_asset["sha256"],
        "control bytes differ from closure",
    )
    lock = json.loads(lock_bytes)
    require(lock.get("schema") == "agentlab.environment_lock.v3", "unsupported environment lock")
    by_url = {asset["url"]: asset for asset in assets}
    required = []
    for component in lock.get("images", []) + lock.get("components", []):
        require(isinstance(component, dict), "environment lock component must be an object")
        artifact_url = component.get("artifact")
        descriptor_url = component.get("descriptor")
        require(artifact_url in by_url, f"closure omits lock artifact for {component.get('slot')}")
        require(descriptor_url in by_url, f"closure omits lock descriptor for {component.get('slot')}")
        artifact = by_url[artifact_url]
        descriptor = by_url[descriptor_url]
        require(
            component.get("archiveSha256") == artifact["sha256"],
            f"lock archive digest differs for {component.get('slot')}",
        )
        required.extend(
            [
                {"slot": component.get("slot"), "role": "artifact", **artifact},
                {"slot": component.get("slot"), "role": "descriptor", **descriptor},
            ]
        )
    require(required, "environment lock contains no installable components")
    require(not output.exists(), f"refusing to overwrite materialization: {output}")
    output.mkdir(parents=True)
    lock_path = output / "environment-lock.json"
    control_path = output / "agentlabctl"
    lock_path.write_bytes(lock_bytes)
    control_path.write_bytes(control_bytes)
    control_path.chmod(0o755)
    receipt = {
        "schema": "agentlab.release_closure_materialization.v1",
        "releaseTag": closure["releaseTag"],
        "releaseGitSha": closure["sources"]["releaseGitSha"],
        "closureSha256": digest(closure_bytes),
        "registrySha256": digest(registry_bytes),
        "environmentLock": {
            "path": lock_path.name,
            "sha256": digest(lock_bytes),
            "bytes": len(lock_bytes),
            "sourceRevision": lock["sourceRevision"],
        },
        "control": {
            "path": control_path.name,
            "sha256": digest(control_bytes),
            "bytes": len(control_bytes),
        },
        "requiredCompositionAssets": required,
        "requiredCompositionAssetCount": len(required),
        "automaticPromotion": False,
        "nextGate": "clean-composition-fetch-install-and-runtime-smoke",
    }
    (output / "materialization.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closure", type=pathlib.Path, required=True)
    parser.add_argument("--registry", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    closure, closure_bytes = load(args.closure, "release closure")
    registry, registry_bytes = load(args.registry, "component registry")
    assets = closure.get("assets") if isinstance(closure, dict) else None
    require(isinstance(assets, list), "release closure assets are required")
    lock_asset = exactly_one(assets, "composition")
    control_asset = exactly_one(assets, "control")
    receipt = materialize(
        closure,
        closure_bytes,
        registry,
        registry_bytes,
        fetch(lock_asset),
        fetch(control_asset),
        args.output,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "releaseTag": receipt["releaseTag"],
                "requiredCompositionAssetCount": receipt[
                    "requiredCompositionAssetCount"
                ],
                "output": args.output.as_posix(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
