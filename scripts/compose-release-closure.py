#!/usr/bin/env python3
"""Compose a source-bound release closure by reusing an exact component set."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import pathlib
import re
import subprocess
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION = re.compile(r"0\.1\.0-alpha\.(\d+)")
REVISION = re.compile(r"[0-9a-f]{40}")


class ClosureError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ClosureError(message)


def load(path: pathlib.Path, label: str) -> tuple[dict[str, Any], bytes]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    raw = path.read_bytes()
    value = json.loads(raw)
    require(isinstance(value, dict), f"{label} must be an object")
    return value, raw


def validator_module():
    path = ROOT / "scripts/validate-release-graph.py"
    spec = importlib.util.spec_from_file_location("agentlab_release_graph_validator", path)
    require(spec is not None and spec.loader is not None, "release graph validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def alpha_ordinal(version: Any, label: str) -> int:
    require(isinstance(version, str), f"{label} version is required")
    match = VERSION.fullmatch(version)
    require(match is not None, f"{label} version must use 0.1.0-alpha.N")
    return int(match.group(1))


def require_local_commit(revision: str) -> None:
    require(REVISION.fullmatch(revision) is not None, "release source revision is invalid")
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", f"{revision}^{{commit}}"],
        text=True,
        capture_output=True,
        check=False,
    )
    require(completed.returncode == 0, "release source revision is not a local commit")


def compose(
    base: dict[str, Any],
    registry: dict[str, Any],
    registry_bytes: bytes,
    version: str,
    revision: str,
) -> dict[str, Any]:
    validator = validator_module()
    validator.validate_closure(base)
    base_ordinal = alpha_ordinal(base.get("releaseVersion"), "base")
    next_ordinal = alpha_ordinal(version, "new")
    require(next_ordinal > base_ordinal, "new release version must advance the base alpha")
    require_local_commit(revision)
    registry_sha = hashlib.sha256(registry_bytes).hexdigest()
    reuse = base.get("reuse") or {}
    require(
        reuse.get("newBinaryBuildCount") == 0
        and reuse.get("newBinaryUploadCount") == 0,
        "base closure is not reference-only",
    )
    selected_components = [
        component
        for component in registry.get("components", [])
        if isinstance(component, dict)
        and str(component.get("status", "")).startswith("selected")
    ]
    require(selected_components, "component registry has no selected components")
    registered_by_url = {
        asset["url"]: (component, asset)
        for component in selected_components
        for asset in component.get("assets", [])
        if isinstance(asset, dict) and isinstance(asset.get("url"), str)
    }
    for retained in base.get("assets", []):
        registered = registered_by_url.get(retained.get("url"))
        require(registered is not None, "base asset is absent from the new registry")
        component, asset = registered
        require(
            retained.get("registryComponent") == component.get("id")
            and retained.get("sha256") == asset.get("sha256")
            and retained.get("bytes") == asset.get("bytes"),
            "base asset identity differs from the new registry",
        )
    assets = []
    asset_ids: set[str] = set()
    asset_urls: set[str] = set()
    for component in selected_components:
        component_assets = component.get("assets")
        require(
            isinstance(component_assets, list) and component_assets,
            f"selected component {component.get('id')} has no assets",
        )
        for asset in component_assets:
            asset_id = asset.get("id") if isinstance(asset, dict) else None
            url = asset.get("url") if isinstance(asset, dict) else None
            require(
                isinstance(asset_id, str)
                and bool(asset_id)
                and asset_id not in asset_ids,
                "registered component asset IDs must be unique",
            )
            require(
                isinstance(url, str) and bool(url) and url not in asset_urls,
                "registered component asset URLs must be unique",
            )
            asset_ids.add(asset_id)
            asset_urls.add(url)
            assets.append(
                {
                    "id": asset_id,
                    "kind": component["kind"],
                    "url": url,
                    "sha256": asset["sha256"],
                    "bytes": asset["bytes"],
                    "immutableRef": component["immutableRef"],
                    "registryComponent": component["id"],
                }
            )
    result = copy.deepcopy(base)
    result["releaseVersion"] = version
    result["releaseTag"] = f"v{version}"
    result["status"] = "developer-preview-candidate"
    result["sources"]["releaseGitSha"] = revision
    result["componentRegistry"] = {
        "schema": registry["schema"],
        "path": "release/components/registry.json",
        "sha256": registry_sha,
    }
    result["assets"] = assets
    result["reuse"] = {
        **reuse,
        "selectedComponentCount": len(selected_components),
        "reusedAssetCount": len(assets),
        "newBinaryBuildCount": 0,
        "newBinaryUploadCount": 0,
        "largeAssetsReused": sorted(
            asset["id"] for asset in assets if asset["bytes"] >= 256 * 1024 * 1024
        ),
    }
    result["developerPreviewScope"] = {
        "multiRepositorySemanticAndProgramAnalysis": "included",
        "recursiveDifficultyFeedback": "included",
        "reviewedCalibratedCaseGeneration": "included",
        "linuxHarmonyEmulatorExecution": "experimental",
        "relativePerformanceFeedback": "experimental",
        "absolutePowerThermal": "not-qualified",
        "automaticPromotion": False,
    }
    result["qualificationPlan"] = {
        "sourceGitSha": revision,
        "requiredChecks": [
            "validate",
            "service-protocol-demo",
            "participant-runtime-isolation",
            "rust-local-contract",
            "pinned-harmony-syntax-coverage",
            "public-install-deploy-smoke-alprod-copy-tree",
            "public-install-deploy-smoke-candidate-copy",
            "public-install-deploy-smoke-candidate-btrfs",
            "public-install-deploy-smoke-release-closure",
        ],
        "taggedCleanInstallRequired": True,
        "linuxEmulatorAcceptanceRequired": True,
        "automaticPromotion": False,
    }
    validator.validate_closure(result, registry, registry_bytes)
    require(
        all(
            asset["url"] in asset_urls
            and asset["sha256"]
            == next(
                registered["sha256"]
                for component in selected_components
                for registered in component["assets"]
                if registered["url"] == asset["url"]
            )
            for asset in result["assets"]
        ),
        "reference-only composition changed component asset identity",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=pathlib.Path, required=True)
    parser.add_argument("--registry", type=pathlib.Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--release-source-revision", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
    base, _ = load(args.base, "base closure")
    registry, registry_bytes = load(args.registry, "component registry")
    result = compose(
        base,
        registry,
        registry_bytes,
        args.version,
        args.release_source_revision,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "ok": True,
                "releaseTag": result["releaseTag"],
                "reusedComponents": result["reuse"]["selectedComponentCount"],
                "reusedAssets": result["reuse"]["reusedAssetCount"],
                "newBinaryBuildCount": 0,
                "newBinaryUploadCount": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
