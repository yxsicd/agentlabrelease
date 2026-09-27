#!/usr/bin/env python3
"""Create or validate a portable exact-evidence multi-repository analysis run."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
SCHEMA = "agentlab.multi_repo_analysis_run.v1"


class AnalysisRunError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise AnalysisRunError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AnalysisRunError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), f"evidence must be a regular file: {path.name}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analysis_tools_execution(root: Path) -> dict[str, Any] | None:
    execution_path = root / "analysis-tools-execution.json"
    runtime_path = root / "analysis-component-runtime.json"
    lock_path = root / "analysis-composition-environment-lock.json"
    present = [path.exists() for path in (execution_path, runtime_path, lock_path)]
    require(all(present) or not any(present), "analysis component evidence is incomplete")
    if not any(present):
        return None
    execution = load(execution_path, "analysis tools execution receipt")
    runtime = load(runtime_path, "analysis component runtime")
    lock_bytes = lock_path.read_bytes()
    lock = load(lock_path, "analysis composition environment lock")
    require(
        execution.get("schema") == "agentlab.analysis_tools_execution.v1",
        "analysis tools execution schema differs",
    )
    require(execution.get("status") == "passed", "analysis tools execution did not pass")
    require(execution.get("tool") == "agentlab-multi-repo-analysis", "analysis tool identity differs")
    require(execution.get("exitCode") == 0, "analysis tool exit code differs")
    require(execution.get("automaticPromotion") is False, "analysis tools execution can auto-promote")
    for field in (
        "toolSha256",
        "componentManifestSha256",
        "componentInventorySha256",
        "argumentsSha256",
    ):
        require(SHA256.fullmatch(str(execution.get(field, ""))) is not None, f"analysis execution {field} is invalid")
    require(
        isinstance(execution.get("argumentCount"), int) and execution["argumentCount"] >= 2,
        "analysis tool argument count is invalid",
    )
    require(
        runtime.get("schema") == "agentlab.analysis_tools_component_runtime.v1",
        "analysis component runtime schema differs",
    )
    require(runtime.get("automaticPromotion") is False, "analysis component runtime can auto-promote")
    component_revision = runtime.get("expectedComponentSourceRevision")
    require(REVISION.fullmatch(str(component_revision or "")) is not None, "analysis component revision is invalid")
    require(
        execution.get("componentSourceRevision") == component_revision,
        "analysis execution component revision differs",
    )
    lock_sha256 = hashlib.sha256(lock_bytes).hexdigest()
    require(runtime.get("environmentLockSha256") == lock_sha256, "analysis composition lock digest differs")
    require(lock.get("schema") == "agentlab.environment_lock.v3", "analysis composition lock schema differs")
    components = [
        row for row in lock.get("components") or []
        if isinstance(row, dict) and row.get("enabled", True) and row.get("slot") == "analysis-tools"
    ]
    images = [row for row in lock.get("images") or [] if isinstance(row, dict) and row.get("enabled", True)]
    require(len(components) == 1 and images, "analysis composition runtime selection is invalid")
    component = components[0]
    image = images[0]
    require(component.get("version") == runtime.get("componentVersion"), "analysis component version differs")
    require(component_revision.startswith(str(component.get("version", ""))), "analysis component version is not source-derived")
    require(component.get("archiveSha256") == runtime.get("componentArchiveSha256"), "analysis component archive differs")
    require(component.get("mountTarget") == runtime.get("componentMountTarget"), "analysis component mount differs")
    require(component.get("volume") == runtime.get("componentVolume"), "analysis component volume differs")
    require(image.get("reference") == runtime.get("runtimeImageReference"), "analysis runtime image reference differs")
    require(image.get("imageId") == runtime.get("runtimeImageId"), "analysis runtime image identity differs")
    return {
        "componentSourceRevision": component_revision,
        "componentVersion": runtime["componentVersion"],
        "componentArchiveSha256": runtime["componentArchiveSha256"],
        "runtimeImageId": runtime["runtimeImageId"],
        "compositionTag": runtime["compositionTag"],
        "environmentLockSha256": lock_sha256,
        "executionReceiptSha256": digest(execution_path),
        "runtimeReceiptSha256": digest(runtime_path),
        "toolSha256": execution["toolSha256"],
        "argumentsSha256": execution["argumentsSha256"],
    }


def derive(root: Path, method_revision: str) -> dict[str, Any]:
    require(REVISION.fullmatch(method_revision) is not None, "method revision is invalid")
    spec_path = root / "source-spec.json"
    manifest_path = root / "manifest.json"
    analysis_root = root / "analysis"
    receipt_path = analysis_root / "multi_repo_analysis.json"
    difficulty_path = analysis_root / "difficulty_candidates.json"
    facts_path = analysis_root / "workspace_facts.jsonl"
    unsupported_path = analysis_root / "unsupported_sources.jsonl"
    spec = load(spec_path, "source specification")
    manifest = load(manifest_path, "analysis manifest")
    receipt = load(receipt_path, "analysis receipt")
    difficulty = load(difficulty_path, "difficulty evidence")
    require(spec.get("schema") == "agentlab.multi_repo_source_spec.v1", "source specification schema differs")
    require(spec.get("automaticPromotion") is False, "source specification can auto-promote")
    require(manifest.get("schema") == "agentlab.multi_repo_manifest.v1", "analysis manifest schema differs")
    require(receipt.get("schema") == "agentlab.multi_repo_analysis.v1", "analysis receipt schema differs")
    require(receipt.get("automaticPromotion") is False, "analysis receipt can auto-promote")
    require(difficulty.get("schema") == "agentlab.difficulty_candidates.v2", "difficulty schema differs")
    require(difficulty.get("automaticPromotion") is False, "difficulty evidence can auto-promote")
    portable_manifest_sources = [
        {key: row.get(key) for key in ("id", "repository", "revision")}
        for row in manifest.get("repositories") or []
        if isinstance(row, dict)
    ]
    require(portable_manifest_sources == spec.get("sources"), "analysis manifest sources differ from source specification")
    require(manifest.get("moduleBindings") == spec.get("moduleBindings"), "analysis manifest bindings differ from source specification")
    require(receipt.get("manifestSha256") == digest(manifest_path), "analysis manifest digest differs")
    require(receipt.get("difficultyCandidatesSha256") == digest(difficulty_path), "difficulty evidence digest differs")
    require(receipt.get("workspaceFactsSha256") == digest(facts_path), "program facts digest differs")
    require(receipt.get("unsupportedSourcesSha256") == digest(unsupported_path), "unsupported-source digest differs")
    require(receipt.get("sourceSetSha256") == difficulty.get("sourceSetSha256"), "analysis source set differs")
    require(difficulty.get("sources") == spec.get("sources"), "difficulty sources differ from source specification")
    require(difficulty.get("moduleBindings") == spec.get("moduleBindings"), "difficulty bindings differ from source specification")
    for field in ("facts", "difficultyCandidates", "unsupportedSources"):
        require(isinstance(receipt.get(field), int) and receipt[field] >= 0, f"analysis {field} count is invalid")
    result = {
        "schema": SCHEMA,
        "methodRevision": method_revision,
        "sourceSetSha256": receipt["sourceSetSha256"],
        "sourceSpecSha256": digest(spec_path),
        "manifestSha256": digest(manifest_path),
        "analysisReceiptSha256": digest(receipt_path),
        "difficultyEvidenceSha256": digest(difficulty_path),
        "programFactsSha256": digest(facts_path),
        "unsupportedSourcesSha256": digest(unsupported_path),
        "counts": {
            "repositories": len(spec["sources"]),
            "facts": receipt["facts"],
            "difficultyCandidates": receipt["difficultyCandidates"],
            "unsupportedSources": receipt["unsupportedSources"],
            "sharedExternalModuleContracts": receipt.get("sharedExternalModuleContracts", 0),
            "sharedExternalApiCallContracts": receipt.get("sharedExternalApiCallContracts", 0),
            "sharedDomainIdentifierContracts": receipt.get("sharedDomainIdentifierContracts", 0),
        },
        "automaticPromotion": False,
    }
    execution = analysis_tools_execution(root)
    if execution is not None:
        result["analysisToolsExecution"] = execution
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--method-revision", required=True)
    create.add_argument("--output", type=Path, required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--root", type=Path, required=True)
    validate.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
            value = derive(args.root, args.method_revision)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            run_path = args.output
        else:
            actual = load(args.run, "analysis run")
            require(actual.get("schema") == SCHEMA, "analysis run schema differs")
            expected = derive(args.root, actual.get("methodRevision", ""))
            require(actual == expected, "analysis run differs from exact evidence")
            value = actual
            run_path = args.run
        print(json.dumps({"ok": True, "runSha256": digest(run_path), "sourceSetSha256": value["sourceSetSha256"]}, sort_keys=True))
    except (AnalysisRunError, OSError, ValueError) as error:
        print(f"multi-repository analysis run invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
