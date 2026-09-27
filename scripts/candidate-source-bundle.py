#!/usr/bin/env python3
"""Bind exact natural and analyzer runs into one non-promoting candidate source."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
SCHEMA = "agentlab.candidate_source_bundle.v1"
ROOT = Path(__file__).resolve().parent


class CandidateSourceBundleError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise CandidateSourceBundleError(message)


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    require(spec is not None and spec.loader is not None, f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ANALYSIS = load_module("agentlab_candidate_bundle_analysis", "multi-repo-analysis-run.py")
NATURAL = load_module("agentlab_candidate_bundle_natural", "collect-github-natural-repair.py")
MERGE = load_module("agentlab_candidate_bundle_merge", "merge-case-candidate-sources.py")


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), f"evidence must be a regular file: {path.name}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workflow_run(path: Path, expected_workflow: str, expected_method_revision: str) -> dict[str, Any]:
    value = load(path, "workflow run metadata")
    require(isinstance(value.get("id"), int) and value["id"] > 0, "workflow run id is invalid")
    require(value.get("head_branch") == "main", "workflow run is not from main")
    require(value.get("path") == expected_workflow, "workflow run path differs")
    require(value.get("event") == "workflow_dispatch", "workflow run event differs")
    require(value.get("conclusion") == "success", "workflow run did not succeed")
    require(value.get("head_sha") == expected_method_revision, "workflow run revision differs from source receipt")
    return value


def source_input(
    *,
    kind: str,
    workflow_path: str,
    metadata_path: Path,
    metadata: dict[str, Any],
    method_revision: str,
    receipt_path: Path,
    receipt_schema: str,
    candidate_path: Path,
    candidate_ids: list[str],
) -> dict[str, Any]:
    return {
        "kind": kind,
        "workflowPath": workflow_path,
        "workflowRunId": metadata["id"],
        "workflowRunHeadSha": metadata["head_sha"],
        "workflowRunMetadataSha256": digest(metadata_path),
        "methodRevision": method_revision,
        "receiptSchema": receipt_schema,
        "receiptSha256": digest(receipt_path),
        "candidateSourceSha256": digest(candidate_path),
        "candidateIds": sorted(candidate_ids),
    }


def derive(root: Path, method_revision: str) -> dict[str, Any]:
    require(root.is_dir() and not root.is_symlink(), "candidate bundle root is invalid")
    require(REVISION.fullmatch(method_revision) is not None, "bundle method revision is invalid")

    analysis_root = root / "analysis-source"
    analysis_run_path = analysis_root / "analysis-run.json"
    analysis_run = load(analysis_run_path, "analysis run")
    require(analysis_run.get("schema") == ANALYSIS.SCHEMA, "analysis run schema differs")
    expected_analysis = ANALYSIS.derive(analysis_root, analysis_run.get("methodRevision", ""))
    require(analysis_run == expected_analysis, "analysis run differs from exact evidence")
    analysis_metadata_path = root / "analysis-source-run.json"
    analysis_workflow = ".github/workflows/multi-repo-analysis.yml"
    analysis_metadata = workflow_run(
        analysis_metadata_path,
        analysis_workflow,
        analysis_run["methodRevision"],
    )

    natural_root = root / "natural-source"
    natural_receipt_path = natural_root / "collection-receipt.json"
    natural_receipt = NATURAL.validate_collection(natural_root, natural_receipt_path)
    natural_metadata_path = root / "natural-source-run.json"
    natural_workflow = ".github/workflows/github-natural-repair-source.yml"
    natural_metadata = workflow_run(
        natural_metadata_path,
        natural_workflow,
        natural_receipt["methodRevision"],
    )

    require(
        analysis_run["sourceSetSha256"] == natural_receipt["sourceSetSha256"],
        "natural and analyzer runs span different source sets",
    )
    analysis_candidates_path = analysis_root / "analysis/difficulty_candidates.json"
    natural_candidates_path = natural_root / "difficulty_candidates.json"
    merged_path = root / "difficulty_candidates.json"
    merged = load(merged_path, "merged candidate source")
    expected_merged = MERGE.merge([analysis_candidates_path, natural_candidates_path])
    require(merged == expected_merged, "merged candidate source differs from exact inputs")
    require(merged.get("sourceSetSha256") == analysis_run["sourceSetSha256"], "merged source set differs")
    candidate_ids = sorted(row["id"] for row in merged["candidates"])

    return {
        "schema": SCHEMA,
        "methodRevision": method_revision,
        "sourceSetSha256": analysis_run["sourceSetSha256"],
        "mergedCandidateSourceSha256": digest(merged_path),
        "candidateCount": len(candidate_ids),
        "candidateIds": candidate_ids,
        "inputs": [
            source_input(
                kind="derived-analysis",
                workflow_path=analysis_workflow,
                metadata_path=analysis_metadata_path,
                metadata=analysis_metadata,
                method_revision=analysis_run["methodRevision"],
                receipt_path=analysis_run_path,
                receipt_schema=ANALYSIS.SCHEMA,
                candidate_path=analysis_candidates_path,
                candidate_ids=[row["id"] for row in load(analysis_candidates_path, "analysis candidates")["candidates"]],
            ),
            source_input(
                kind="natural-github-repair",
                workflow_path=natural_workflow,
                metadata_path=natural_metadata_path,
                metadata=natural_metadata,
                method_revision=natural_receipt["methodRevision"],
                receipt_path=natural_receipt_path,
                receipt_schema="agentlab.github_natural_repair_collection.v1",
                candidate_path=natural_candidates_path,
                candidate_ids=natural_receipt["candidateIds"],
            ),
        ],
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--method-revision", required=True)
    create.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--root", type=Path, required=True)
    validate.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
            value = derive(args.root, args.method_revision)
            args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            bundle_path = args.output
        else:
            actual = load(args.bundle, "candidate source bundle")
            require(actual.get("schema") == SCHEMA, "candidate source bundle schema differs")
            require(actual.get("automaticPromotion") is False, "candidate source bundle can auto-promote")
            expected = derive(args.root, actual.get("methodRevision", ""))
            require(actual == expected, "candidate source bundle differs from exact evidence")
            value = actual
            bundle_path = args.bundle
        print(json.dumps({
            "ok": True,
            "bundleSha256": digest(bundle_path),
            "candidateCount": value["candidateCount"],
            "sourceSetSha256": value["sourceSetSha256"],
        }, sort_keys=True))
    except (CandidateSourceBundleError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"candidate source bundle invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
