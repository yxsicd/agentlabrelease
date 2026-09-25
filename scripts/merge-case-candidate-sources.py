#!/usr/bin/env python3
"""Merge exact natural and derived candidates only within one pinned source set."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from case_supply import validate_case_source


SHA256 = re.compile(r"[0-9a-f]{64}")


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), "candidate source must be a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "candidate source must be an object")
    require(value.get("schema") == "agentlab.difficulty_candidates.v2", "unsupported candidate source schema")
    require(value.get("automaticPromotion") is False, "candidate source can auto-promote")
    require(isinstance(value.get("sourceSetSha256"), str) and SHA256.fullmatch(value["sourceSetSha256"]), "candidate source set is invalid")
    require(isinstance(value.get("sources"), list) and len(value["sources"]) >= 2, "candidate source repositories are absent")
    require(isinstance(value.get("candidates"), list) and value["candidates"], "candidate source candidates are absent")
    return value


def merge(paths: list[Path]) -> dict[str, Any]:
    require(len(paths) >= 2, "at least two candidate sources are required")
    values = [(path, load(path)) for path in paths]
    first = values[0][1]
    source_set = first["sourceSetSha256"]
    sources = first["sources"]
    bindings = first.get("moduleBindings", {})
    candidates = []
    seen: set[str] = set()
    inputs = []
    for path, value in values:
        require(value["sourceSetSha256"] == source_set, "candidate sources span different source sets")
        require(value["sources"] == sources, "candidate source repository identities differ")
        require(value.get("moduleBindings", {}) == bindings, "candidate source module bindings differ")
        for candidate in value["candidates"]:
            require(isinstance(candidate, dict), "candidate source row is invalid")
            candidate_id = candidate.get("id")
            require(isinstance(candidate_id, str) and candidate_id and candidate_id not in seen, "candidate identity is invalid or duplicated")
            require(candidate.get("schema") == "agentlab.difficulty_point.v1", "candidate schema is invalid")
            require(candidate.get("automaticPromotion") is False, "candidate can auto-promote")
            case_source = candidate.get("caseSource")
            if case_source is not None:
                validate_case_source(case_source)
                require(case_source.get("candidateId") == candidate_id, "candidate source identity differs")
                require(case_source.get("sourceSetSha256") == source_set, "candidate source set differs")
            seen.add(candidate_id)
            candidates.append(candidate)
        inputs.append(
            {
                "sha256": digest(path),
                "method": value.get("method"),
                "candidateIds": sorted(row["id"] for row in value["candidates"]),
            }
        )
    candidates.sort(key=lambda row: row["id"])
    inputs.sort(key=lambda row: row["sha256"])
    return {
        "schema": "agentlab.difficulty_candidates.v2",
        "method": "exact multi-lane candidate-source merge",
        "sourceSetSha256": source_set,
        "sources": sources,
        "moduleBindings": bindings,
        "sourceInputs": inputs,
        "candidates": candidates,
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
        value = merge(args.input)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "candidateCount": len(value["candidates"]), "outputSha256": digest(args.output)}, sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"case candidate source merge invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
