#!/usr/bin/env python3
"""Bind a release feedback handoff to the next exact multi-repository analysis."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import re
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


class AnalysisRequestError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AnalysisRequestError(message)


def load(path: pathlib.Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AnalysisRequestError(f"cannot load {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def source_validator() -> Any:
    path = pathlib.Path(__file__).with_name("prepare-multi-repo-analysis-sources.py")
    spec = importlib.util.spec_from_file_location("prepare_multi_repo_analysis_sources", path)
    require(spec is not None and spec.loader is not None, "source validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_spec


def prepare(
    handoff_path: pathlib.Path,
    source_spec_path: pathlib.Path,
    feedback_candidate_id: str,
    next_method_revision: str,
) -> dict[str, Any]:
    require(handoff_path.is_file() and not handoff_path.is_symlink(), "handoff must be a regular file")
    require(source_spec_path.is_file() and not source_spec_path.is_symlink(), "source specification must be a regular file")
    handoff = load(handoff_path, "recursive feedback handoff")
    raw_spec = load(source_spec_path, "source specification")
    try:
        normalized_spec = source_validator()(raw_spec)
    except (ValueError, OSError) as error:
        raise AnalysisRequestError(f"source specification is invalid: {error}") from error

    require(handoff.get("schema") == "agentlab.release_recursive_feedback_handoff.v1", "unsupported feedback handoff schema")
    require(handoff.get("status") == "next-analysis-review-required", "feedback handoff is not review-required")
    require(handoff.get("automaticPromotion") is False, "feedback handoff may not auto-promote")
    campaign = handoff.get("campaign")
    require(isinstance(campaign, dict), "handoff campaign is absent")
    prior_source_set = campaign.get("sourceSetSha256")
    prior_method_revision = campaign.get("methodRevision")
    require(isinstance(prior_source_set, str) and SHA256.fullmatch(prior_source_set), "prior source set is invalid")
    require(isinstance(prior_method_revision, str) and REVISION.fullmatch(prior_method_revision), "prior method revision is invalid")
    require(isinstance(next_method_revision, str) and REVISION.fullmatch(next_method_revision), "next method revision is invalid")
    next_gate = handoff.get("nextAnalysis") or {}
    require(next_gate.get("proposer") == "scripts/propose-feedback-analysis-cut.py", "handoff proposer differs")
    require(next_gate.get("requiredChange") == "new-source-set-or-method-revision", "handoff change policy differs")

    candidates = handoff.get("candidates")
    require(isinstance(candidates, list) and candidates, "handoff has no feedback candidates")
    selected = [row for row in candidates if isinstance(row, dict) and row.get("id") == feedback_candidate_id]
    require(len(selected) == 1, "feedback candidate id is absent or duplicated")
    candidate = selected[0]
    verification = candidate.get("verificationContract") or {}
    require(candidate.get("automaticPromotion") is False, "feedback candidate may not auto-promote")
    require(verification.get("caseReady") is False, "feedback candidate overclaims readiness")
    require("new-source-and-analysis-cut" in verification.get("required", []), "feedback candidate does not require a new analysis cut")

    source_identity = {
        "schema": "agentlab.multi_repo_source_set.v1",
        "repositories": normalized_spec["sources"],
        "moduleBindings": normalized_spec["moduleBindings"],
    }
    next_source_set = canonical_sha256(source_identity)
    source_changed = next_source_set != prior_source_set
    method_changed = next_method_revision != prior_method_revision
    require(source_changed or method_changed, "next analysis changes neither source set nor method revision")

    return {
        "schema": "agentlab.feedback_analysis_request.v1",
        "status": "prepared-review-required",
        "requestId": f"feedback-analysis-request-{canonical_sha256({'handoff': sha256(handoff_path), 'candidate': feedback_candidate_id, 'sourceSet': next_source_set, 'methodRevision': next_method_revision})[:20]}",
        "releaseTag": handoff.get("releaseTag"),
        "releaseGitSha": handoff.get("releaseGitSha"),
        "feedbackHandoff": {
            "sha256": sha256(handoff_path),
            "candidateId": feedback_candidate_id,
            "caseId": campaign.get("caseId"),
            "mechanism": candidate.get("mechanism"),
        },
        "priorAnalysis": {
            "sourceSetSha256": prior_source_set,
            "methodRevision": prior_method_revision,
        },
        "nextAnalysis": {
            "sourceSpecSha256": sha256(source_spec_path),
            "sourceSetSha256": next_source_set,
            "methodRevision": next_method_revision,
            "sourceChanged": source_changed,
            "methodChanged": method_changed,
            "repositories": normalized_spec["sources"],
            "moduleBindings": normalized_spec["moduleBindings"],
            "workflow": ".github/workflows/multi-repo-analysis.yml",
            "nextGate": "exact-analysis-then-feedback-analysis-cut-proposal",
        },
        "policy": {
            "caseReady": False,
            "requiresMaintainerAdjudication": True,
            "requiresIndependentOracleCalibration": True,
            "automaticPromotion": False,
        },
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", type=pathlib.Path, required=True)
    parser.add_argument("--source-spec", type=pathlib.Path, required=True)
    parser.add_argument("--feedback-candidate-id", required=True)
    parser.add_argument("--next-method-revision", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite feedback analysis request: {args.output}")
    try:
        request = prepare(
            args.handoff.resolve(),
            args.source_spec.resolve(),
            args.feedback_candidate_id,
            args.next_method_revision,
        )
    except AnalysisRequestError as error:
        raise SystemExit(f"feedback analysis request invalid: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"requestId": request["requestId"], "status": request["status"], "sourceSetSha256": request["nextAnalysis"]["sourceSetSha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
