#!/usr/bin/env python3
"""Validate public AgentLab immutable release closure and target metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from typing import Any

CLOSURE_SCHEMA = "agentlab.release_closure.v1"
TARGET_SCHEMA = "agentlab.target_descriptor.v1"
MUTABLE_REFS = {"aldev", "almain", "alprod", "latest", "current", "main"}
MUTABLE_URL_FRAGMENTS = (
    "/releases/download/aldev/",
    "/releases/download/almain/",
    "/releases/download/alprod/",
    "/releases/latest/",
    "/latest/",
    "/current/",
)
REQUIRED_ASSET_KINDS = {"control", "composition", "runtime", "harmony", "mcpgit", "tools"}
SUPPORTED_TARGET_STATUS = {"qualified", "experimental", "unsupported"}
SUPPORTED_CLOSURE_STATUS = {
    "assembly-candidate-unqualified",
    "developer-preview-candidate",
    "qualified-developer-preview",
}
DEVELOPER_PREVIEW_CHECKS = {
    "validate",
    "service-protocol-demo",
    "participant-runtime-isolation",
    "rust-local-contract",
    "pinned-harmony-syntax-coverage",
    "public-install-deploy-smoke-alprod-copy-tree",
    "public-install-deploy-smoke-candidate-copy",
    "public-install-deploy-smoke-candidate-btrfs",
}


def fail(message: str) -> None:
    raise ValueError(message)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{path} must contain an object")
    return value


def hex_value(value: Any, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and re.fullmatch(r"[0-9a-fA-F]+", value) is not None


def validate_asset(asset: Any) -> None:
    if not isinstance(asset, dict):
        fail("release asset must be object")
    for field in ("id", "kind", "url", "sha256", "bytes", "immutableRef"):
        if field not in asset:
            fail(f"release asset missing {field}")
    if not isinstance(asset["url"], str) or not asset["url"].startswith("https://"):
        fail("release asset URL must use https")
    if any(fragment in asset["url"].lower() for fragment in MUTABLE_URL_FRAGMENTS):
        fail("tagged release may not reference a mutable channel")
    if str(asset["immutableRef"]).lower() in MUTABLE_REFS:
        fail("release asset immutableRef must be immutable")
    if not hex_value(asset["sha256"], 64):
        fail("release asset sha256 must be exact")
    if not isinstance(asset["bytes"], int) or asset["bytes"] <= 0:
        fail("release asset bytes must be positive")
    if asset["kind"] == "image":
        identity = asset.get("identity")
        if not isinstance(identity, dict) or identity.get("schema") != "agentlab.oci_image_identity.v1":
            fail("image asset requires explicit OCI identity")
        manifest = str(identity.get("ociManifestDigest", "")).removeprefix("sha256:")
        config = str(identity.get("ociConfigDigest", "")).removeprefix("sha256:")
        if not hex_value(manifest, 64) or not hex_value(config, 64):
            fail("image identity requires distinct manifest/config SHA-256 digests")


def validate_registry_binding(
    value: dict[str, Any], registry: dict[str, Any], registry_bytes: bytes
) -> None:
    binding = value.get("componentRegistry")
    if not isinstance(binding, dict):
        fail("componentRegistry binding required")
    if binding.get("schema") != "agentlab.component_registry.v1":
        fail("componentRegistry schema mismatch")
    if binding.get("path") != "release/components/registry.json":
        fail("componentRegistry path mismatch")
    if hashlib.sha256(registry_bytes).hexdigest() != binding.get("sha256"):
        fail("componentRegistry digest mismatch")
    if registry.get("schema") != binding["schema"]:
        fail("loaded component registry schema mismatch")

    components = registry.get("components")
    if not isinstance(components, list):
        fail("component registry entries required")
    by_id = {item.get("id"): item for item in components if isinstance(item, dict)}
    selected = {item_id for item_id, item in by_id.items() if item.get("status", "").startswith("selected")}
    referenced: set[str] = set()
    for asset in value["assets"]:
        component_id = asset.get("registryComponent")
        if not isinstance(component_id, str) or component_id not in by_id:
            fail("release asset must reference a registered component")
        referenced.add(component_id)
        candidates = by_id[component_id].get("assets") or []
        if not any(
            item.get("url") == asset["url"]
            and item.get("bytes") == asset["bytes"]
            and item.get("sha256") == asset["sha256"]
            for item in candidates
        ):
            fail(f"release asset differs from registry component {component_id}")
    if referenced != selected:
        fail("closure selection differs from selected component registry entries")

    reuse = value.get("reuse")
    if not isinstance(reuse, dict) or reuse.get("selectedComponentCount") != len(selected):
        fail("reuse summary selected component count mismatch")
    if reuse.get("newBinaryBuildCount") != 0 or reuse.get("newBinaryUploadCount") != 0:
        fail("reference-only aggregate may not claim new binary builds or uploads")


def validate_closure(
    value: dict[str, Any], registry: dict[str, Any] | None = None, registry_bytes: bytes = b""
) -> None:
    if value.get("schema") != CLOSURE_SCHEMA:
        fail("unsupported release closure schema")
    if not isinstance(value.get("releaseVersion"), str) or not value["releaseVersion"]:
        fail("releaseVersion required")
    if not isinstance(value.get("releaseTag"), str) or not value["releaseTag"]:
        fail("releaseTag required")
    if value["releaseTag"] != f"v{value['releaseVersion']}":
        fail("releaseTag must exactly match releaseVersion")
    if value["releaseTag"].lower() in MUTABLE_REFS:
        fail("releaseTag must be immutable")
    status = value.get("status")
    if status is not None and status not in SUPPORTED_CLOSURE_STATUS:
        fail("unsupported release closure status")
    sources = value.get("sources")
    if not isinstance(sources, dict):
        fail("sources required")
    if not hex_value(sources.get("agentlabGitSha"), 40) or not hex_value(sources.get("llmrsGitSha"), 40):
        fail("source revisions must be exact 40-hex")
    if status is not None and not hex_value(sources.get("releaseGitSha"), 40):
        fail("current release closure requires exact releaseGitSha")

    schemas = value.get("requiredSchemas")
    required_schema_fields = {"controlApi", "lockSchema", "receiptSchema", "componentGraphSchema"}
    if not isinstance(schemas, dict) or set(schemas) != required_schema_fields:
        fail("requiredSchemas must declare exact release compatibility surface")

    assets = value.get("assets")
    if not isinstance(assets, list) or not assets:
        fail("assets required")
    ids = set()
    kinds = set()
    for asset in assets:
        validate_asset(asset)
        if asset["id"] in ids:
            fail("duplicate release asset id")
        ids.add(asset["id"])
        kinds.add(asset["kind"])
    missing = REQUIRED_ASSET_KINDS - kinds
    if missing:
        fail(f"closure missing required asset kinds: {sorted(missing)}")

    contracts = value.get("contracts")
    if not isinstance(contracts, dict):
        fail("contracts required")
    for name, generation in contracts.items():
        if not isinstance(name, str) or not name or not isinstance(generation, int) or generation < 1:
            fail("contracts must map names to positive generations")

    targets = value.get("targetCompatibility")
    if not isinstance(targets, dict) or not targets:
        fail("targetCompatibility required")
    for name, target in targets.items():
        if not isinstance(name, str) or not name or not isinstance(target, dict):
            fail("invalid target compatibility entry")
        if target.get("status") not in SUPPORTED_TARGET_STATUS:
            fail("invalid target compatibility status")
        if not isinstance(target.get("platform"), str) or not target["platform"]:
            fail("target compatibility platform required")
    if registry is not None:
        validate_registry_binding(value, registry, registry_bytes)
    if status == "developer-preview-candidate":
        scope = value.get("developerPreviewScope")
        expected_scope = {
            "multiRepositorySemanticAndProgramAnalysis": "included",
            "recursiveDifficultyFeedback": "included",
            "reviewedCalibratedCaseGeneration": "included",
            "linuxHarmonyEmulatorExecution": "experimental",
            "relativePerformanceFeedback": "experimental",
            "absolutePowerThermal": "not-qualified",
            "automaticPromotion": False,
        }
        if scope != expected_scope:
            fail("developer preview scope differs")
        plan = value.get("qualificationPlan")
        if not isinstance(plan, dict):
            fail("developer preview qualification plan required")
        checks = plan.get("requiredChecks")
        if (
            plan.get("sourceGitSha") != sources.get("releaseGitSha")
            or not isinstance(checks, list)
            or len(checks) != len(set(checks))
            or set(checks) != DEVELOPER_PREVIEW_CHECKS
            or plan.get("taggedCleanInstallRequired") is not True
            or plan.get("linuxEmulatorAcceptanceRequired") is not True
            or plan.get("automaticPromotion") is not False
        ):
            fail("developer preview qualification plan differs")


def validate_target(value: dict[str, Any]) -> None:
    if value.get("schema") != TARGET_SCHEMA:
        fail("unsupported target descriptor schema")
    if not isinstance(value.get("id"), str) or not value["id"]:
        fail("target id required")
    if value.get("qualificationStatus") not in SUPPORTED_TARGET_STATUS:
        fail("invalid target qualificationStatus")
    if not isinstance(value.get("platform"), str) or not value["platform"]:
        fail("target platform required")
    modes = value.get("supportedDeploymentModes")
    if not isinstance(modes, list) or not modes:
        fail("target supportedDeploymentModes required")
    if value.get("defaultDeploymentMode") not in modes:
        fail("target defaultDeploymentMode must be supported")
    if value.get("id") == "wsl2":
        aliases = set(value.get("aliases") or [])
        if "bluebwsl" not in aliases:
            fail("wsl2 target must preserve bluebwsl alias")
        mcpgit = value.get("mcpgit") or {}
        if mcpgit.get("defaultMode") != "self-hosted":
            fail("wsl2 target must default to self-hosted MCPGit")
        if not mcpgit.get("isolatedDataVolumeByDefault"):
            fail("wsl2 target must isolate MCPGit data by default")
        network = value.get("network") or {}
        if network.get("defaultBindHost") != "127.0.0.1":
            fail("wsl2 target must default to loopback")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--closure", action="append", default=[])
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--registry")
    args = parser.parse_args()
    registry_bytes = b""
    registry = None
    if args.registry:
        registry_path = pathlib.Path(args.registry)
        registry_bytes = registry_path.read_bytes()
        registry = json.loads(registry_bytes)
    for raw in args.closure:
        validate_closure(load(pathlib.Path(raw)), registry, registry_bytes)
    for raw in args.target:
        validate_target(load(pathlib.Path(raw)))
    if not args.closure and not args.target:
        parser.error("at least one --closure or --target is required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
