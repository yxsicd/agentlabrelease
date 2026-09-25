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
    return {
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
        },
        "automaticPromotion": False,
    }


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
