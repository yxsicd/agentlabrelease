#!/usr/bin/env python3
"""Retain release-bound assessed feedback as input to the next analysis cut."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


class RecursiveFeedbackError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RecursiveFeedbackError(message)


def load(path: pathlib.Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RecursiveFeedbackError(f"cannot load {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def binding(path: pathlib.Path) -> dict[str, Any]:
    return {"sha256": sha256(path), "byteLength": path.stat().st_size}


def validate_candidate(candidate: Any, case_id: str) -> dict[str, Any]:
    require(isinstance(candidate, dict), "feedback candidate is invalid")
    candidate_id = candidate.get("id")
    require(isinstance(candidate_id, str) and candidate_id, "feedback candidate id is invalid")
    require(candidate.get("caseId") == case_id, f"{candidate_id} case identity differs")
    require(candidate.get("status") == "candidate", f"{candidate_id} is not a candidate")
    require(candidate.get("maturityState") == "candidate", f"{candidate_id} maturity changed")
    require(candidate.get("automaticPromotion") is False, f"{candidate_id} may not auto-promote")
    verification = candidate.get("verificationContract")
    require(isinstance(verification, dict), f"{candidate_id} verification contract is absent")
    required = verification.get("required")
    require(verification.get("caseReady") is False, f"{candidate_id} overclaims case readiness")
    require(isinstance(required, list), f"{candidate_id} required gates are invalid")
    for gate in (
        "maintainer-adjudication",
        "new-source-and-analysis-cut",
        "independent-oracle-calibration",
    ):
        require(gate in required, f"{candidate_id} omits required gate {gate}")
    selection = candidate.get("caseSelection")
    require(isinstance(selection, dict), f"{candidate_id} case selection is absent")
    score = selection.get("discriminationScore")
    require(
        isinstance(score, (int, float)) and not isinstance(score, bool) and 0 <= score <= 1,
        f"{candidate_id} discrimination score is invalid",
    )
    return {
        "id": candidate_id,
        "dimensionId": candidate.get("dimensionId"),
        "primaryDimension": candidate.get("primaryDimension"),
        "stageId": candidate.get("stageId"),
        "failureMode": candidate.get("failureMode"),
        "mechanism": candidate.get("mechanism"),
        "validAttemptCount": candidate.get("validAttemptCount"),
        "failingAttemptCount": candidate.get("failingAttemptCount"),
        "caseSelection": selection,
        "verificationContract": verification,
        "automaticPromotion": False,
    }


def prepare(
    closure_path: pathlib.Path,
    acceptance_path: pathlib.Path,
    campaign_summary_path: pathlib.Path,
    feedback_path: pathlib.Path,
    discrimination_path: pathlib.Path,
) -> dict[str, Any]:
    closure = load(closure_path, "release closure")
    acceptance = load(acceptance_path, "release Harmony acceptance")
    summary = load(campaign_summary_path, "campaign summary")
    feedback = load(feedback_path, "assessment feedback")
    discrimination = load(discrimination_path, "discrimination report")

    require(closure.get("schema") == "agentlab.release_closure.v1", "unsupported release closure schema")
    require(closure.get("status") == "developer-preview-candidate", "closure is not a developer preview candidate")
    release_revision = (closure.get("sources") or {}).get("releaseGitSha")
    require(isinstance(release_revision, str) and REVISION.fullmatch(release_revision), "release revision is invalid")
    require(acceptance.get("schema") == "agentlab.release_harmony_acceptance.v1", "unsupported acceptance schema")
    require(acceptance.get("status") == "accepted-developer-preview-review-required", "Harmony acceptance is not qualified")
    require(acceptance.get("releaseTag") == closure.get("releaseTag"), "acceptance release tag differs")
    require(acceptance.get("releaseGitSha") == release_revision, "acceptance release revision differs")
    require((acceptance.get("closure") or {}).get("sha256") == sha256(closure_path), "acceptance closure digest differs")
    require(acceptance.get("automaticPromotion") is False, "acceptance may not auto-promote")

    require(summary.get("schema") == "agentlab.harmony_assessed_campaign_summary.v1", "unsupported campaign summary schema")
    require(summary.get("status") == "assessed-review-required", "campaign is not assessed-review-required")
    require(summary.get("automaticPromotion") is False, "campaign may not auto-promote")
    campaign = acceptance.get("campaign") or {}
    require(campaign.get("campaignId") == summary.get("campaignId"), "acceptance campaign id differs")
    require(campaign.get("summarySha256") == sha256(campaign_summary_path), "acceptance campaign summary digest differs")
    require(campaign.get("caseId") == summary.get("caseId"), "acceptance campaign case differs")
    require(campaign.get("sourceSetSha256") == summary.get("sourceSetSha256"), "acceptance source set differs")
    require(summary.get("methodRevision") == release_revision, "campaign method revision differs from release")
    require(summary.get("assessmentFeedbackSha256") == sha256(feedback_path), "campaign feedback digest differs")
    require(summary.get("discriminationReportSha256") == sha256(discrimination_path), "campaign discrimination digest differs")

    case_id = summary.get("caseId")
    source_set = summary.get("sourceSetSha256")
    require(isinstance(case_id, str) and case_id, "campaign case id is invalid")
    require(isinstance(source_set, str) and SHA256.fullmatch(source_set), "campaign source set is invalid")
    require(feedback.get("schema") == "agentlab.assessment_feedback_candidates.v1", "unsupported feedback schema")
    require(feedback.get("caseId") == case_id, "feedback case differs")
    require(feedback.get("sourceSetSha256") == source_set, "feedback source set differs")
    require(feedback.get("methodRevision") == release_revision, "feedback method revision differs")
    require((feedback.get("policy") or {}).get("automaticPromotion") is False, "feedback may not auto-promote")
    require(discrimination.get("schema") == "agentlab.case_discrimination_report.v2", "unsupported discrimination schema")
    require(discrimination.get("sourceSetSha256") == source_set, "discrimination source set differs")
    require(discrimination.get("methodRevision") == release_revision, "discrimination method revision differs")
    require((discrimination.get("policy") or {}).get("automaticPromotion") is False, "discrimination may not auto-promote")
    require(feedback.get("discriminationReportSha256") == canonical_sha256(discrimination), "feedback does not bind exact discrimination report")

    raw_candidates = feedback.get("candidates")
    require(isinstance(raw_candidates, list) and raw_candidates, "feedback has no candidates")
    require(feedback.get("candidateCount") == len(raw_candidates), "feedback candidate count differs")
    require(summary.get("feedbackCandidateCount") == len(raw_candidates), "campaign feedback candidate count differs")
    candidates = [validate_candidate(row, case_id) for row in raw_candidates]
    rank_rows = [row for row in discrimination.get("ranking", []) if isinstance(row, dict) and row.get("caseId") == case_id]
    require(len(rank_rows) == 1, "discrimination report must contain one case ranking")
    rank = rank_rows[0]
    require(rank.get("eligible") is True and rank.get("decision") == "high-discrimination-candidate", "case is not an eligible high-discrimination candidate")
    metrics = rank.get("metrics") or {}
    harmony = (rank.get("processMeasurement") or {}).get("harmonyDevice") or {}
    performance_observations = harmony.get("performanceObservationCount")
    repeatable_profiles = harmony.get("repeatablePerformanceProfileCount")
    require(isinstance(performance_observations, int) and performance_observations >= 0, "performance observation count is invalid")
    require(isinstance(repeatable_profiles, int) and repeatable_profiles >= 0, "repeatable performance profile count is invalid")
    performance_qualified = harmony.get("performanceFeedbackQualified") is True
    performance_candidates = [row for row in candidates if row["primaryDimension"] == "performance-feedback"]
    require(bool(performance_candidates) == performance_qualified, "performance feedback qualification and candidates differ")

    return {
        "schema": "agentlab.release_recursive_feedback_handoff.v1",
        "status": "next-analysis-review-required",
        "releaseTag": closure["releaseTag"],
        "releaseGitSha": release_revision,
        "closure": binding(closure_path),
        "harmonyAcceptance": binding(acceptance_path),
        "campaign": {
            "campaignId": summary["campaignId"],
            "caseId": case_id,
            "sourceSetSha256": source_set,
            "methodRevision": release_revision,
            "summary": binding(campaign_summary_path),
        },
        "evidence": {
            "assessmentFeedback": binding(feedback_path),
            "discriminationReport": binding(discrimination_path),
        },
        "discrimination": {
            "decision": rank["decision"],
            "eligible": True,
            "score": metrics.get("discriminationScore"),
            "validAttemptCount": rank.get("validAttemptCount"),
            "wilson95Separated": metrics.get("observedExtremePassRateWilson95Separated"),
        },
        "candidates": candidates,
        "performanceBoundary": {
            "observationCount": performance_observations,
            "repeatableProfileCount": repeatable_profiles,
            "qualifiedForRecursivePerformanceFeedback": performance_qualified,
            "authority": harmony.get("performanceAuthority"),
        },
        "nextAnalysis": {
            "proposer": "scripts/propose-feedback-analysis-cut.py",
            "requiredChange": "new-source-set-or-method-revision",
            "requiredArtifacts": [
                "prior-frozen-case",
                "new-multi-repository-analysis-receipt",
                "new-difficulty-candidates",
                "maintainer-feedback-analysis-cut-review",
            ],
            "nextGate": "maintainer-adjudication-and-new-analysis-cut",
        },
        "qualificationBoundary": {
            "qualified": [
                "release-bound functional pass/fail feedback",
                "high-discrimination recursive difficulty candidate",
                "exact evidence handoff to the next analysis cut",
            ],
            "notQualified": [
                "population-level discrimination confidence",
                "repeatable relative-performance separation",
                "absolute power or thermal behavior",
                "automatic case generation or promotion",
            ],
        },
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closure", type=pathlib.Path, required=True)
    parser.add_argument("--acceptance", type=pathlib.Path, required=True)
    parser.add_argument("--campaign-summary", type=pathlib.Path, required=True)
    parser.add_argument("--feedback", type=pathlib.Path, required=True)
    parser.add_argument("--discrimination-report", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite recursive feedback handoff: {args.output}")
    try:
        handoff = prepare(
            args.closure.resolve(),
            args.acceptance.resolve(),
            args.campaign_summary.resolve(),
            args.feedback.resolve(),
            args.discrimination_report.resolve(),
        )
    except RecursiveFeedbackError as error:
        raise SystemExit(f"release recursive feedback handoff invalid: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"releaseTag": handoff["releaseTag"], "status": handoff["status"], "handoffSha256": sha256(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
