#!/usr/bin/env python3
"""Derive an immutable evaluation case bound to hidden dependency evidence."""
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


class BindingError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise BindingError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BindingError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def validate_binding(case: dict[str, Any], contract_path: Path, facts_path: Path) -> None:
    runner_path = Path(__file__).with_name("run-multi-repo-assessment.py")
    spec = importlib.util.spec_from_file_location(
        "agentlab_dependency_binding_validator", runner_path
    )
    require(spec is not None and spec.loader is not None, "dependency binding validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate_dependency_discovery(case, contract_path, facts_path)


def bind(case_path: Path, contract_path: Path, facts_path: Path) -> dict[str, Any]:
    case = load(case_path, "evaluation case")
    contract = load(contract_path, "dependency discovery contract")
    require(case.get("schema") == "agentlab.multi_repo_evaluation_case.v1", "unsupported evaluation case")
    require(case.get("status") == "frozen-calibrated", "evaluation case is not frozen")
    require(case.get("automaticPromotion") is False, "evaluation case can auto-promote")
    require("dependencyDiscovery" not in case, "evaluation case already has dependency discovery binding")
    require(contract.get("schema") == "agentlab.dependency_discovery_contract.v1", "unsupported dependency contract")
    require(contract.get("caseId") == case.get("id"), "dependency contract case differs")
    require(contract.get("sourceSetSha256") == case.get("sourceSetSha256"), "dependency contract source set differs")
    facts_sha = digest(facts_path)
    require(isinstance(facts_sha, str) and SHA256.fullmatch(facts_sha), "program facts digest is invalid")
    require(contract.get("programFactsSha256") == facts_sha, "dependency contract program facts differ")
    require(contract.get("automaticPromotion") is False, "dependency contract can auto-promote")
    output = dict(case)
    output["dependencyDiscovery"] = {
        "schema": "agentlab.dependency_discovery_binding.v1",
        "contractSha256": digest(contract_path),
        "programFactsSha256": facts_sha,
        "participantEditScopeVisible": False,
        "precisionClaimed": False,
    }
    lineage = dict(output.get("lineage") or {})
    lineage["dependencyDiscovery"] = {
        "baseCaseSha256": digest(case_path),
        "contractSha256": digest(contract_path),
        "programFactsSha256": facts_sha,
    }
    output["lineage"] = lineage
    validate_binding(output, contract_path, facts_path)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--dependency-contract", type=Path, required=True)
    parser.add_argument("--program-facts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
        value = bind(args.case, args.dependency_contract, args.program_facts)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "caseSha256": digest(args.output)}, sort_keys=True))
    except (BindingError, OSError, ValueError) as error:
        print(f"dependency discovery case binding invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
