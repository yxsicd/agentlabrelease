#!/usr/bin/env python3
"""Generate a bounded review queue from feedback and exact analysis evidence."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import pathlib
import re
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")


class ProposalQueueError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProposalQueueError(message)


def load(path: pathlib.Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProposalQueueError(f"cannot load {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proposal_module() -> Any:
    path = pathlib.Path(__file__).with_name("propose-feedback-analysis-cut.py")
    spec = importlib.util.spec_from_file_location("propose_feedback_analysis_cut", path)
    require(spec is not None and spec.loader is not None, "feedback cut proposer is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def eligible_candidates(difficulty: dict[str, Any]) -> list[dict[str, Any]]:
    eligible = []
    for row in difficulty.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        affected = row.get("affectedFiles")
        repositories = {
            item.get("repositoryId")
            for item in affected or []
            if isinstance(item, dict) and isinstance(item.get("repositoryId"), str)
        }
        verification = row.get("verificationContract") or {}
        if (
            row.get("dimensionId") == "multi-repository-change-impact"
            and row.get("status") == "candidate"
            and row.get("maturityState") == "candidate"
            and row.get("automaticPromotion") is False
            and verification.get("caseReady") is False
            and isinstance(affected, list)
            and affected
            and len(repositories) >= 2
            and isinstance(row.get("id"), str)
            and row["id"]
        ):
            eligible.append(row)
    return sorted(
        eligible,
        key=lambda row: (
            -len({item.get("repositoryId") for item in row["affectedFiles"] if isinstance(item, dict)}),
            -len(row["affectedFiles"]),
            -len(row.get("evidenceIds") or []),
            row["id"],
        ),
    )


def prepare(
    request_path: pathlib.Path,
    handoff_path: pathlib.Path,
    prior_case_path: pathlib.Path,
    feedback_path: pathlib.Path,
    analysis_path: pathlib.Path,
    analysis_run_path: pathlib.Path,
    difficulty_path: pathlib.Path,
    output: pathlib.Path,
    max_candidates: int,
) -> dict[str, Any]:
    require(not output.exists(), f"refusing to overwrite proposal queue: {output}")
    require(1 <= max_candidates <= 20, "max candidates must be between one and twenty")
    request = load(request_path, "feedback analysis request")
    handoff = load(handoff_path, "recursive feedback handoff")
    prior_case = load(prior_case_path, "prior case")
    feedback = load(feedback_path, "assessment feedback")
    analysis = load(analysis_path, "analysis receipt")
    analysis_run = load(analysis_run_path, "analysis run")
    difficulty = load(difficulty_path, "difficulty evidence")

    require(request.get("schema") == "agentlab.feedback_analysis_request.v1", "unsupported analysis request schema")
    require(request.get("status") == "prepared-review-required", "analysis request is not review-required")
    require(request.get("automaticPromotion") is False, "analysis request may not auto-promote")
    request_feedback = request.get("feedbackHandoff") or {}
    request_analysis = request.get("nextAnalysis") or {}
    require(request_feedback.get("sha256") == sha256(handoff_path), "request handoff digest differs")
    require(request_feedback.get("priorCaseSha256") == sha256(prior_case_path), "request prior case digest differs")
    require(request_feedback.get("feedbackEvidenceSha256") == sha256(feedback_path), "request feedback digest differs")
    portable = handoff.get("portableEvidence") or {}
    require((portable.get("priorCase") or {}).get("sha256") == sha256(prior_case_path), "handoff prior case digest differs")
    require((portable.get("assessmentFeedback") or {}).get("sha256") == sha256(feedback_path), "handoff feedback digest differs")
    require(request_feedback.get("caseId") == prior_case.get("id") == feedback.get("caseId"), "prior case identity differs")
    require(request_analysis.get("sourceSetSha256") == analysis.get("sourceSetSha256") == difficulty.get("sourceSetSha256"), "request and analysis source sets differ")
    require(analysis.get("difficultyCandidatesSha256") == sha256(difficulty_path), "analysis does not bind difficulty evidence")
    require(analysis_run.get("schema") == "agentlab.multi_repo_analysis_run.v1", "unsupported analysis run schema")
    require(analysis_run.get("sourceSetSha256") == request_analysis.get("sourceSetSha256"), "analysis run source set differs")
    require(analysis_run.get("methodRevision") == request_analysis.get("methodRevision"), "analysis run method revision differs")
    require(analysis_run.get("analysisReceiptSha256") == sha256(analysis_path), "analysis run does not bind analysis receipt")
    require(analysis_run.get("difficultyEvidenceSha256") == sha256(difficulty_path), "analysis run does not bind difficulty evidence")
    require(analysis_run.get("automaticPromotion") is False, "analysis run may not auto-promote")

    candidates = eligible_candidates(difficulty)
    require(candidates, "analysis produced no reviewable cross-repository impact candidates")
    selected = candidates[:max_candidates]
    proposer = proposal_module()
    output.mkdir(parents=True)
    proposals = []
    for ordinal, candidate in enumerate(selected, 1):
        proposal = proposer.build_proposal(
            case=prior_case,
            feedback=feedback,
            analysis=analysis,
            difficulty=difficulty,
            feedback_path=feedback_path,
            analysis_path=analysis_path,
            difficulty_path=difficulty_path,
            feedback_candidate_id=request_feedback["candidateId"],
            difficulty_candidate_id=candidate["id"],
            next_method_revision=request_analysis["methodRevision"],
        )
        target = output / f"proposal-{ordinal:02d}.json"
        target.write_text(json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        repositories = sorted(
            {
                row.get("repositoryId")
                for row in candidate.get("affectedFiles") or []
                if isinstance(row, dict) and isinstance(row.get("repositoryId"), str)
            }
        )
        proposals.append(
            {
                "rank": ordinal,
                "difficultyCandidateId": candidate["id"],
                "cutId": proposal["cutId"],
                "proposalFile": target.name,
                "proposalSha256": sha256(target),
                "affectedRepositoryCount": len(repositories),
                "affectedFileCount": len(candidate["affectedFiles"]),
                "selectionAuthority": "deterministic-review-queue-not-semantic-approval",
            }
        )
    index = {
        "schema": "agentlab.feedback_analysis_proposal_queue.v1",
        "status": "maintainer-review-required",
        "requestSha256": sha256(request_path),
        "feedbackHandoffSha256": sha256(handoff_path),
        "analysisRunSha256": sha256(analysis_run_path),
        "analysisReceiptSha256": sha256(analysis_path),
        "difficultyEvidenceSha256": sha256(difficulty_path),
        "feedbackCandidateId": request_feedback["candidateId"],
        "eligibleCandidateCount": len(candidates),
        "proposalCount": len(proposals),
        "selectionPolicy": {
            "order": [
                "affected-repository-count-desc",
                "affected-file-count-desc",
                "evidence-count-desc",
                "candidate-id-asc",
            ],
            "limit": max_candidates,
            "semanticAlignmentVerified": False,
        },
        "proposals": proposals,
        "automaticPromotion": False,
        "nextGate": "independent-maintainer-review-of-one-proposal",
    }
    (output / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=pathlib.Path, required=True)
    parser.add_argument("--handoff", type=pathlib.Path, required=True)
    parser.add_argument("--prior-case", type=pathlib.Path, required=True)
    parser.add_argument("--feedback", type=pathlib.Path, required=True)
    parser.add_argument("--analysis-receipt", type=pathlib.Path, required=True)
    parser.add_argument("--analysis-run", type=pathlib.Path, required=True)
    parser.add_argument("--difficulty", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--max-candidates", type=int, default=10)
    args = parser.parse_args()
    try:
        index = prepare(
            args.request.resolve(),
            args.handoff.resolve(),
            args.prior_case.resolve(),
            args.feedback.resolve(),
            args.analysis_receipt.resolve(),
            args.analysis_run.resolve(),
            args.difficulty.resolve(),
            args.output.resolve(),
            args.max_candidates,
        )
    except (ProposalQueueError, ValueError, OSError) as error:
        raise SystemExit(f"feedback analysis proposal queue invalid: {error}") from error
    print(json.dumps({"status": index["status"], "proposalCount": index["proposalCount"], "eligibleCandidateCount": index["eligibleCandidateCount"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
