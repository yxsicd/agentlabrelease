#!/usr/bin/env python3
"""Join authenticated case validity and measured Agent separation into one suite."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any


MANIFEST_SCHEMA = "agentlab.agent_suite_scorecard_manifest.v1"
DEVICE_BOUND_MANIFEST_SCHEMA = "agentlab.agent_suite_scorecard_manifest.v2"
PREDECLARED_MANIFEST_SCHEMA = "agentlab.agent_suite_scorecard_manifest.v3"
SCORECARD_SCHEMA = "agentlab.agent_suite_scorecard.v1"
COHORT_BOUND_SCORECARD_SCHEMA = "agentlab.agent_suite_scorecard.v2"
PREDECLARED_SCORECARD_SCHEMA = "agentlab.agent_suite_scorecard.v3"
REVISION = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
TOKEN = re.compile(r"[A-Za-z0-9_.:@/-]{1,200}")
SLSA_PROVENANCE = "https://slsa.dev/provenance/v1"


class ScorecardError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ScorecardError(message)


def load_object(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ScorecardError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must contain an object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def portable_file(root: Path, value: Any, label: str) -> Path:
    require(isinstance(value, str) and value, f"{label} path is required")
    relative = Path(value)
    require(not relative.is_absolute(), f"{label} path must be relative")
    unresolved = root / relative
    require(not unresolved.is_symlink(), f"{label} path must not be a symlink")
    try:
        resolved = unresolved.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ScorecardError(f"{label} path escapes or is absent") from error
    require(resolved.is_file(), f"{label} path must be a file")
    return resolved


def validate_attestation_verification(
    path: Path,
    subject_path: Path,
    run_id: int,
    run_attempt: int,
    label: str,
) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ScorecardError(f"cannot read {label}: {error}") from error
    require(isinstance(value, list) and value, f"{label} is empty")
    expected_digest = digest(subject_path)
    expected_suffix = f"/actions/runs/{run_id}/attempts/{run_attempt}"
    for item in value:
        result = item.get("verificationResult") if isinstance(item, dict) else None
        statement = result.get("statement") if isinstance(result, dict) else None
        if not isinstance(statement, dict) or statement.get("predicateType") != SLSA_PROVENANCE:
            continue
        subjects = statement.get("subject")
        subject_matches = isinstance(subjects, list) and any(
            isinstance(subject, dict)
            and isinstance(subject.get("digest"), dict)
            and subject["digest"].get("sha256") == expected_digest
            for subject in subjects
        )
        predicate = statement.get("predicate") or {}
        invocation = ((predicate.get("runDetails") or {}).get("metadata") or {}).get("invocationId")
        if subject_matches and isinstance(invocation, str) and invocation.endswith(expected_suffix):
            return {
                "path": path,
                "sha256": digest(path),
                "subjectSha256": expected_digest,
            }
    raise ScorecardError(f"{label} does not bind the subject to the expected workflow run")


def scorer_module():
    path = Path(__file__).with_name("score-case-discrimination.py")
    spec = importlib.util.spec_from_file_location("agentlab_suite_discrimination", path)
    require(spec is not None and spec.loader is not None, "discrimination scorer is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def experiment_plan_module():
    path = Path(__file__).with_name("participant-experiment-plan.py")
    spec = importlib.util.spec_from_file_location("agentlab_suite_experiment_plan", path)
    require(spec is not None and spec.loader is not None, "participant experiment plan validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def capability_resolution(
    profiles: list[dict[str, Any]],
    rate_field: str,
    interval_field: str,
) -> dict[str, Any]:
    pairs = []
    for lower, higher in zip(profiles, profiles[1:]):
        gap = higher[rate_field] - lower[rate_field]
        separated = (
            higher[interval_field]["lower"]
            > lower[interval_field]["upper"]
        )
        pairs.append(
            {
                "lowerParticipantId": lower["participantId"],
                "higherParticipantId": higher["participantId"],
                "lowerPassRate": lower[rate_field],
                "higherPassRate": higher[rate_field],
                "passRateGap": gap,
                "strictlyOrdered": gap > 0.0,
                "wilson95Separated": separated,
            }
        )
    enough_tiers = len(profiles) >= 3
    nondecreasing = all(row["passRateGap"] >= 0.0 for row in pairs)
    strictly_increasing = all(row["strictlyOrdered"] for row in pairs)
    all_separated = all(row["wilson95Separated"] for row in pairs)
    qualified = enough_tiers and strictly_increasing and all_separated
    if not enough_tiers:
        status = "insufficient-participant-tiers"
    elif not nondecreasing:
        status = "capability-order-violation"
    elif not strictly_increasing:
        status = "adjacent-tiers-not-distinct"
    elif not all_separated:
        status = "collect-more-adjacent-trials"
    else:
        status = "qualified"
    return {
        "status": status,
        "participantTierCount": len(profiles),
        "adjacentPairCount": len(pairs),
        "minimumAdjacentPassRateGap": min(
            (row["passRateGap"] for row in pairs),
            default=None,
        ),
        "expectedCapabilityOrderQualified": nondecreasing,
        "strictlyIncreasing": strictly_increasing,
        "allAdjacentWilson95Separated": all_separated,
        "qualified": qualified,
        "adjacentPairs": pairs,
        "authority": "predeclared-weakest-to-strongest-order-with-adjacent-wilson-intervals",
    }


def validate_population(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    value = load_object(path, "blind review population report")
    population_schema = value.get("schema")
    require(
        population_schema
        in {
            "agentlab.blind_review_population_report.v1",
            "agentlab.blind_review_population_report.v2",
        },
        "population report schema differs",
    )
    cohort_bound = population_schema == "agentlab.blind_review_population_report.v2"
    require(isinstance(value.get("cohortId"), str) and TOKEN.fullmatch(value["cohortId"]), "population cohort identity is invalid")
    require(isinstance(value.get("methodRevision"), str) and REVISION.fullmatch(value["methodRevision"]), "population method revision is invalid")
    require(isinstance(value.get("caseMembershipSha256"), str) and SHA256.fullmatch(value["caseMembershipSha256"]), "population membership digest is invalid")
    cases = value.get("cases")
    require(isinstance(cases, list) and len(cases) >= 2, "population report requires at least two cases")
    rows: dict[str, dict[str, Any]] = {}
    candidate_ids: set[str] = set()
    for row in cases:
        require(isinstance(row, dict), "population case is invalid")
        case_id = row.get("caseId")
        require(isinstance(case_id, str) and TOKEN.fullmatch(case_id), "population case identity is invalid")
        require(case_id not in rows, f"duplicate population case: {case_id}")
        if cohort_bound:
            candidate_id = row.get("candidateId")
            require(isinstance(candidate_id, str) and TOKEN.fullmatch(candidate_id), f"{case_id} population candidate identity is invalid")
            require(candidate_id not in candidate_ids, f"duplicate population candidate: {candidate_id}")
            candidate_ids.add(candidate_id)
        require(isinstance(row.get("sourceSetSha256"), str) and SHA256.fullmatch(row["sourceSetSha256"]), f"{case_id} population source set is invalid")
        require(isinstance(row.get("adjudicationRunId"), int) and row["adjudicationRunId"] > 0, f"{case_id} population adjudication run is invalid")
        require(isinstance(row.get("blindPilotReviewQualified"), bool), f"{case_id} population review qualification is invalid")
        require(row.get("modelTrainingExclusionQualified") is False, f"{case_id} population overclaims model-training exclusion")
        require(row.get("eligibleForUnseenAgentDiscrimination") is False, f"{case_id} population overclaims unseen-Agent eligibility")
        bundle_evidence = row.get("bundleEvidence")
        adjudication = bundle_evidence.get("adjudication") if isinstance(bundle_evidence, dict) else None
        require(
            isinstance(adjudication, dict)
            and isinstance(adjudication.get("sha256"), str)
            and SHA256.fullmatch(adjudication["sha256"]),
            f"{case_id} population adjudication evidence is invalid",
        )
        rows[case_id] = row
    denominators = value.get("denominators")
    require(isinstance(denominators, dict), "population denominators are invalid")
    require(denominators.get("caseCount") == len(rows), "population case denominator differs")
    if cohort_bound:
        selected_count = denominators.get("selectedCandidateCount")
        adjudicated_count = denominators.get("adjudicatedCandidateCount")
        unadjudicated_count = denominators.get("unadjudicatedCandidateCount")
        require(isinstance(selected_count, int) and selected_count >= 2, "population selected candidate denominator is invalid")
        require(adjudicated_count == len(rows) == len(candidate_ids), "population adjudicated candidate denominator differs")
        require(unadjudicated_count == selected_count - adjudicated_count, "population unadjudicated candidate denominator differs")
        require(denominators.get("caseYieldRate") == adjudicated_count / selected_count, "population case yield differs")
    qualification = value.get("qualification")
    require(isinstance(qualification, dict), "population qualification is invalid")
    require(qualification.get("allCasesAuthenticatedAndAttested") is True, "population cases are not all authenticated")
    require(qualification.get("populationRepresentativenessQualified") is False, "population report overclaims representativeness")
    require(qualification.get("modelTrainingExclusionQualified") is False, "population report overclaims model-training exclusion")
    require(qualification.get("eligibleForUnseenAgentDiscrimination") is False, "population report overclaims unseen-Agent eligibility")
    if cohort_bound:
        require(qualification.get("candidateCohortMembershipQualified") is True, "population candidate cohort membership is not qualified")
        cohort = value.get("candidateCohort")
        require(isinstance(cohort, dict), "population candidate cohort evidence is absent")
        cohort_source_set = cohort.get("sourceSetSha256")
        require(isinstance(cohort_source_set, str) and SHA256.fullmatch(cohort_source_set), "population candidate cohort source set is invalid")
        require(all(row["sourceSetSha256"] == cohort_source_set for row in rows.values()), "population case source set differs from candidate cohort")
        require(cohort.get("declaredRepresentative") is False, "population candidate cohort overclaims representativeness")
        selected_ids = cohort.get("selectedCandidateIds")
        adjudicated_ids = cohort.get("adjudicatedCandidateIds")
        unadjudicated_ids = cohort.get("unadjudicatedCandidateIds")
        require(isinstance(selected_ids, list) and selected_ids == sorted(set(selected_ids)), "population selected candidate index is invalid")
        require(adjudicated_ids == sorted(candidate_ids), "population adjudicated candidate index differs")
        require(isinstance(unadjudicated_ids, list) and unadjudicated_ids == sorted(set(selected_ids) - candidate_ids), "population unadjudicated candidate index differs")
        evidence = cohort.get("evidence")
        require(isinstance(evidence, dict), "population candidate cohort evidence reference is invalid")
        evidence_path = portable_file(path.parent, evidence.get("path"), "population candidate cohort evidence")
        require(digest(evidence_path) == evidence.get("sha256"), "population candidate cohort evidence digest differs")
    policy = value.get("policy")
    require(isinstance(policy, dict) and policy.get("automaticPromotion") is False, "population report cannot auto-promote")
    return value, rows


def validate_discrimination(
    path: Path,
    case_id: str,
    source_set: str,
    participant_order: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    value = load_object(path, f"{case_id} discrimination report")
    require(value.get("schema") == "agentlab.case_discrimination_report.v2", f"{case_id} discrimination schema differs")
    require(value.get("sourceSetSha256") == source_set, f"{case_id} discrimination source set differs")
    require(isinstance(value.get("methodRevision"), str) and REVISION.fullmatch(value["methodRevision"]), f"{case_id} discrimination method revision is invalid")
    ranking = value.get("ranking")
    require(isinstance(ranking, list) and ranking, f"{case_id} discrimination ranking is absent")
    rows = [row for row in ranking if isinstance(row, dict) and row.get("caseId") == case_id]
    require(len(rows) == 1, f"{case_id} discrimination row is not unique")
    require(len({row.get("caseId") for row in ranking if isinstance(row, dict)}) == len(ranking), f"{case_id} discrimination ranking has duplicate cases")
    expected_eligible = sorted(
        row["caseId"] for row in ranking if isinstance(row, dict) and row.get("eligible") is True
    )
    require(sorted(value.get("eligibleCaseIds") or []) == expected_eligible, f"{case_id} eligible case index differs")
    require((value.get("policy") or {}).get("automaticPromotion") is False, f"{case_id} discrimination report cannot auto-promote")
    row = rows[0]
    profiles = row.get("participantProfiles")
    require(isinstance(profiles, list), f"{case_id} participant profiles are invalid")
    profile_index = {
        profile.get("participantId"): profile
        for profile in profiles
        if isinstance(profile, dict) and isinstance(profile.get("participantId"), str)
    }
    require(len(profile_index) == len(profiles), f"{case_id} participant profiles are duplicated")
    require(set(profile_index) == set(participant_order), f"{case_id} participant profiles differ from the frozen order")
    scorer = scorer_module()
    for participant_id, profile in profile_index.items():
        valid = profile.get("validTrials")
        passed = profile.get("passedTrials")
        require(isinstance(valid, int) and valid > 0, f"{case_id} {participant_id} trial denominator is invalid")
        require(isinstance(passed, int) and 0 <= passed <= valid, f"{case_id} {participant_id} passed trials are invalid")
        require(profile.get("passRate") == passed / valid, f"{case_id} {participant_id} pass rate differs")
        require(profile.get("passRateWilson95") == scorer.wilson_interval(passed, valid), f"{case_id} {participant_id} Wilson interval differs")
        profile_process = profile.get("processMeasurement")
        profile_harmony = (
            profile_process.get("harmonyDevice")
            if isinstance(profile_process, dict)
            else None
        )
        require(isinstance(profile_harmony, dict), f"{case_id} {participant_id} Harmony device measurement is absent")
        require(
            profile_harmony.get("successfulTrials") == passed
            and isinstance(profile_harmony.get("executedTrials"), int)
            and 0 <= profile_harmony["executedTrials"] <= valid
            and isinstance(profile_harmony.get("successfulDeviceTrials"), int)
            and 0 <= profile_harmony["successfulDeviceTrials"] <= passed
            and isinstance(profile_harmony.get("profiledSuccessfulDeviceTrials"), int)
            and 0
            <= profile_harmony["profiledSuccessfulDeviceTrials"]
            <= profile_harmony["successfulDeviceTrials"]
            and isinstance(profile_harmony.get("smartPerfSampleCount"), int)
            and profile_harmony["smartPerfSampleCount"] >= 0,
            f"{case_id} {participant_id} Harmony device counts are invalid",
        )
        require(
            profile_harmony.get("successfulAttemptDeviceCoverageQualified")
            is (
                passed > 0
                and profile_harmony["successfulDeviceTrials"] == passed
            )
            and profile_harmony.get("profiledSuccessCoverageQualified")
            is (
                passed > 0
                and profile_harmony["profiledSuccessfulDeviceTrials"] == passed
            )
            and profile_harmony.get("authority")
            == "operator-owned-harmony-ui-oracle-with-functional-pass-gated-smartperf",
            f"{case_id} {participant_id} Harmony device qualification differs",
        )
        performance = profile_harmony.get("performanceFeedback")
        require(
            isinstance(performance, dict)
            and isinstance(performance.get("observedTrials"), int)
            and 0 <= performance["observedTrials"] <= profile_harmony["successfulDeviceTrials"]
            and performance.get("successfulTrialCoverageQualified")
            is (passed > 0 and performance["observedTrials"] == passed)
            and isinstance(performance.get("identityConsistent"), bool)
            and performance.get("repeatabilityQualified")
            is (
                performance["successfulTrialCoverageQualified"]
                and performance["identityConsistent"]
                and performance["observedTrials"] >= 2
                and bool(performance.get("metrics"))
            )
            and performance.get("authority")
            == {
                "functional": "none",
                "relativePerformance": "smartperf-emulator-proxy",
                "absolutePowerThermal": "unavailable-on-emulator",
            },
            f"{case_id} {participant_id} Harmony performance feedback differs",
        )
    process = row.get("processMeasurement")
    require(isinstance(process, dict), f"{case_id} process measurement is absent")
    require(isinstance(process.get("validAttemptCount"), int) and process["validAttemptCount"] > 0, f"{case_id} process denominator is invalid")
    require(isinstance(process.get("measuredAttemptCount"), int) and 0 <= process["measuredAttemptCount"] <= process["validAttemptCount"], f"{case_id} process measured count is invalid")
    require(process.get("coverageRate") == process["measuredAttemptCount"] / process["validAttemptCount"], f"{case_id} process coverage differs")
    require(process.get("coverageQualified") is (process["measuredAttemptCount"] == process["validAttemptCount"]), f"{case_id} process qualification differs")
    require(row.get("processAwareEligible") is (row.get("eligible") is True and process["coverageQualified"] is True), f"{case_id} process-aware eligibility differs")
    self_assessment = process.get("participantSelfAssessment")
    require(isinstance(self_assessment, dict), f"{case_id} participant self-assessment measurement is absent")
    require(isinstance(self_assessment.get("measuredAttemptCount"), int) and 0 <= self_assessment["measuredAttemptCount"] <= process["validAttemptCount"], f"{case_id} participant self-assessment denominator is invalid")
    require(self_assessment.get("coverageRate") == self_assessment["measuredAttemptCount"] / process["validAttemptCount"], f"{case_id} participant self-assessment coverage differs")
    require(self_assessment.get("coverageQualified") is (self_assessment["measuredAttemptCount"] == process["validAttemptCount"]), f"{case_id} participant self-assessment qualification differs")
    comparable = self_assessment.get("comparableStageCount")
    agreement = self_assessment.get("agreementCount")
    require(isinstance(comparable, int) and comparable >= 0 and isinstance(agreement, int) and 0 <= agreement <= comparable, f"{case_id} participant self-assessment comparison counts are invalid")
    require(self_assessment.get("agreementRate") == (agreement / comparable if comparable else None), f"{case_id} participant self-assessment agreement differs")
    brier = self_assessment.get("meanBrierScore")
    require((comparable == 0 and brier is None) or (comparable > 0 and isinstance(brier, (int, float)) and not isinstance(brier, bool) and 0.0 <= brier <= 1.0), f"{case_id} participant self-assessment Brier score is invalid")
    require(self_assessment.get("authority") == "participant-claim-compared-with-operator-oracle-not-a-verdict", f"{case_id} participant self-assessment authority differs")
    dependency = process.get("dependencyDiscovery")
    require(isinstance(dependency, dict), f"{case_id} dependency discovery measurement is absent")
    require(isinstance(dependency.get("measuredAttemptCount"), int) and 0 <= dependency["measuredAttemptCount"] <= process["validAttemptCount"], f"{case_id} dependency discovery denominator is invalid")
    require(dependency.get("coverageRate") == dependency["measuredAttemptCount"] / process["validAttemptCount"], f"{case_id} dependency discovery measurement coverage differs")
    require(dependency.get("measurementCoverageQualified") is (dependency["measuredAttemptCount"] == process["validAttemptCount"]), f"{case_id} dependency discovery measurement qualification differs")
    require(isinstance(dependency.get("missingStageCount"), int) and dependency["missingStageCount"] >= 0 and isinstance(dependency.get("invalidStageCount"), int) and dependency["invalidStageCount"] >= 0, f"{case_id} dependency discovery submission counts are invalid")
    obligation_count = dependency.get("obligationCount")
    covered_count = dependency.get("coveredObligationCount")
    require(isinstance(obligation_count, int) and obligation_count >= 0 and isinstance(covered_count, int) and 0 <= covered_count <= obligation_count, f"{case_id} dependency discovery obligation counts are invalid")
    require(dependency.get("requiredObligationCoverage") == (covered_count / obligation_count if obligation_count else None), f"{case_id} dependency discovery obligation coverage differs")
    require(dependency.get("coverageQualified") is (bool(obligation_count) and covered_count == obligation_count), f"{case_id} dependency discovery qualification differs")
    require(dependency.get("precisionClaimed") is False, f"{case_id} dependency discovery cannot claim precision")
    require(dependency.get("authority") == "hidden-revision-bound-program-fact-obligations-not-gold-path-imitation", f"{case_id} dependency discovery authority differs")
    harmony = process.get("harmonyDevice")
    require(isinstance(harmony, dict), f"{case_id} Harmony device measurement is absent")
    harmony_counts = (
        "executedAttemptCount",
        "successfulAttemptCount",
        "successfulDeviceAttemptCount",
        "profiledSuccessfulAttemptCount",
        "smartPerfSampleCount",
        "performanceObservationCount",
        "repeatablePerformanceProfileCount",
    )
    require(
        all(
            isinstance(harmony.get(field), int) and harmony[field] >= 0
            for field in harmony_counts
        ),
        f"{case_id} Harmony device denominators are invalid",
    )
    require(
        harmony["executedAttemptCount"] <= process["validAttemptCount"]
        and harmony["successfulDeviceAttemptCount"]
        <= harmony["successfulAttemptCount"]
        and harmony["profiledSuccessfulAttemptCount"]
        <= harmony["successfulDeviceAttemptCount"],
        f"{case_id} Harmony device counts are inconsistent",
    )
    require(
        harmony["executedAttemptCount"]
        == sum(
            profile["processMeasurement"]["harmonyDevice"]["executedTrials"]
            for profile in profiles
        )
        and harmony["successfulAttemptCount"]
        == sum(profile["passedTrials"] for profile in profiles)
        and harmony["successfulDeviceAttemptCount"]
        == sum(
            profile["processMeasurement"]["harmonyDevice"][
                "successfulDeviceTrials"
            ]
            for profile in profiles
        )
        and harmony["profiledSuccessfulAttemptCount"]
        == sum(
            profile["processMeasurement"]["harmonyDevice"][
                "profiledSuccessfulDeviceTrials"
            ]
            for profile in profiles
        )
        and harmony["smartPerfSampleCount"]
        == sum(
            profile["processMeasurement"]["harmonyDevice"][
                "smartPerfSampleCount"
            ]
            for profile in profiles
        )
        and harmony["performanceObservationCount"]
        == sum(
            profile["processMeasurement"]["harmonyDevice"]["performanceFeedback"]["observedTrials"]
            for profile in profiles
        )
        and harmony["repeatablePerformanceProfileCount"]
        == sum(
            profile["processMeasurement"]["harmonyDevice"]["performanceFeedback"]["repeatabilityQualified"]
            for profile in profiles
        ),
        f"{case_id} Harmony device aggregate differs from participant profiles",
    )
    successful_device_qualified = (
        harmony["successfulAttemptCount"] > 0
        and harmony["successfulDeviceAttemptCount"]
        == harmony["successfulAttemptCount"]
    )
    profiled_success_qualified = (
        harmony["successfulAttemptCount"] > 0
        and harmony["profiledSuccessfulAttemptCount"]
        == harmony["successfulAttemptCount"]
    )
    require(
        harmony.get("successfulAttemptDeviceCoverageQualified")
        is successful_device_qualified
        and harmony.get("profiledSuccessCoverageQualified")
        is profiled_success_qualified
        and harmony.get("endToEndEvidenceQualified")
        is (
            harmony["executedAttemptCount"] > 0
            and successful_device_qualified
            and profiled_success_qualified
        ),
        f"{case_id} Harmony device qualification differs",
    )
    require(
        harmony.get("authority")
        == "operator-owned-harmony-ui-oracle-with-functional-pass-gated-smartperf",
        f"{case_id} Harmony device authority differs",
    )
    successful_performance_profiles = [
        profile["processMeasurement"]["harmonyDevice"]["performanceFeedback"]
        for profile in profiles
        if profile["passedTrials"] > 0
    ]
    require(
        harmony.get("performanceFeedbackQualified")
        is (
            bool(successful_performance_profiles)
            and all(
                feedback["repeatabilityQualified"]
                for feedback in successful_performance_profiles
            )
        )
        and harmony.get("performanceAuthority")
        == {
            "functional": "none",
            "relativePerformance": "smartperf-emulator-proxy",
            "absolutePowerThermal": "unavailable-on-emulator",
        },
        f"{case_id} Harmony performance aggregate differs",
    )
    return value, row


def build_scorecard(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve(strict=True)
    root = manifest_path.parent
    manifest = load_object(manifest_path, "Agent suite scorecard manifest")
    manifest_schema = manifest.get("schema")
    require(
        manifest_schema in {
            MANIFEST_SCHEMA,
            DEVICE_BOUND_MANIFEST_SCHEMA,
            PREDECLARED_MANIFEST_SCHEMA,
        },
        "unsupported Agent suite scorecard manifest schema",
    )
    suite_id = manifest.get("suiteId")
    require(isinstance(suite_id, str) and TOKEN.fullmatch(suite_id), "suiteId is invalid")
    method_revision = manifest.get("methodRevision")
    require(isinstance(method_revision, str) and REVISION.fullmatch(method_revision), "methodRevision is invalid")
    participant_order = manifest.get("participantOrder")
    require(
        isinstance(participant_order, list)
        and len(participant_order) >= 2
        and len(participant_order) == len(set(participant_order))
        and all(isinstance(value, str) and TOKEN.fullmatch(value) for value in participant_order),
        "participantOrder must contain at least two unique identities from weakest to strongest",
    )
    plan_validator = experiment_plan_module()
    if manifest_schema == PREDECLARED_MANIFEST_SCHEMA:
        participant_profiles = manifest.get("participantProfiles")
        require(isinstance(participant_profiles, list), "participantProfiles must be a predeclared ordered list")
        normalized_profiles = plan_validator.normalize_profiles([
            {"participantId": row.get("participantId"), "model": row.get("model")}
            if isinstance(row, dict) else row
            for row in participant_profiles
        ])
        require(participant_profiles == normalized_profiles, "participantProfiles order or ordinals differ")
        require(
            participant_order == [row["participantId"] for row in participant_profiles],
            "participantOrder differs from the predeclared experiment profiles",
        )
        participant_execution_protocol = plan_validator.validate_execution_protocol(
            manifest.get("participantExecutionProtocol")
        )
    else:
        require(manifest.get("participantProfiles") is None, "legacy scorecard manifest cannot claim predeclared participant profiles")
        require(manifest.get("participantExecutionProtocol") is None, "legacy scorecard manifest cannot claim a predeclared execution protocol")
        participant_profiles = []
        participant_execution_protocol = None
    population_source = manifest.get("reviewPopulation")
    require(
        isinstance(population_source, dict)
        and set(population_source)
        == {
            "workflowRunId",
            "workflowRunAttempt",
            "workflowHeadSha",
            "report",
            "attestationVerification",
        },
        "reviewPopulation source fields differ",
    )
    require(
        isinstance(population_source.get("workflowRunId"), int)
        and population_source["workflowRunId"] > 0,
        "review population run id is invalid",
    )
    require(
        isinstance(population_source.get("workflowRunAttempt"), int)
        and population_source["workflowRunAttempt"] > 0,
        "review population run attempt is invalid",
    )
    require(
        isinstance(population_source.get("workflowHeadSha"), str)
        and REVISION.fullmatch(population_source["workflowHeadSha"]),
        "review population workflow revision is invalid",
    )
    population_path = portable_file(root, population_source.get("report"), "review population report")
    population, population_cases = validate_population(population_path)
    require(population.get("methodRevision") == population_source["workflowHeadSha"], "review population method revision differs from its workflow run")
    population_attestation_path = portable_file(
        root,
        population_source.get("attestationVerification"),
        "review population attestation verification",
    )
    population_attestation = validate_attestation_verification(
        population_attestation_path,
        population_path,
        population_source["workflowRunId"],
        population_source["workflowRunAttempt"],
        "review population attestation verification",
    )
    cases = manifest.get("cases")
    require(isinstance(cases, list), "scorecard cases must be a list")
    manifest_case_ids = [case.get("caseId") for case in cases if isinstance(case, dict)]
    require(len(manifest_case_ids) == len(cases) and len(set(manifest_case_ids)) == len(cases), "scorecard case identities are invalid or duplicated")
    require(set(manifest_case_ids) == set(population_cases), "scorecard cases must exactly match the reviewed population")
    campaign_run_ids = [
        case.get("assessedCampaignRunId") for case in cases if isinstance(case, dict)
    ]
    require(
        all(isinstance(run_id, int) and run_id > 0 for run_id in campaign_run_ids)
        and len(campaign_run_ids) == len(set(campaign_run_ids)),
        "assessed campaign run IDs must be positive and unique",
    )

    case_rows = []
    profile_totals = {
        participant: {"validTrials": 0, "passedTrials": 0}
        for participant in participant_order
    }
    for case in cases:
        legacy_fields = {
                "caseId",
                "assessedCampaignRunId",
                "assessedCampaignRunAttempt",
                "assessedCampaignWorkflowHeadSha",
                "discriminationReport",
                "discriminationAttestationVerification",
        }
        device_bound_fields = legacy_fields | {
            "assessedCampaignWorkflowPath",
            "assessedCampaignMethodRevision",
            "sourceAssessedCampaignRunId",
            "deviceImportVerification",
            "deviceImportAttestationVerification",
        }
        predeclared_fields = device_bound_fields | {
            "participantExperimentPlan",
            "participantExperimentPlanAttestationVerification",
        }
        require(
            set(case)
            == (
                predeclared_fields
                if manifest_schema == PREDECLARED_MANIFEST_SCHEMA
                else (
                    device_bound_fields
                    if manifest_schema == DEVICE_BOUND_MANIFEST_SCHEMA
                    else legacy_fields
                )
            ),
            "scorecard case fields differ",
        )
        case_id = case["caseId"]
        campaign_run_id = case.get("assessedCampaignRunId")
        require(isinstance(campaign_run_id, int) and campaign_run_id > 0, f"{case_id} assessed campaign run id is invalid")
        campaign_run_attempt = case.get("assessedCampaignRunAttempt")
        require(isinstance(campaign_run_attempt, int) and campaign_run_attempt > 0, f"{case_id} assessed campaign run attempt is invalid")
        campaign_head_sha = case.get("assessedCampaignWorkflowHeadSha")
        require(isinstance(campaign_head_sha, str) and REVISION.fullmatch(campaign_head_sha), f"{case_id} assessed campaign revision is invalid")
        if manifest_schema in {
            DEVICE_BOUND_MANIFEST_SCHEMA,
            PREDECLARED_MANIFEST_SCHEMA,
        }:
            campaign_workflow = case.get("assessedCampaignWorkflowPath")
            require(
                campaign_workflow
                in {
                    ".github/workflows/multi-repo-assessed-campaign.yml",
                    ".github/workflows/harmony-device-campaign-import.yml",
                },
                f"{case_id} assessed campaign workflow is invalid",
            )
            campaign_method_revision = case.get("assessedCampaignMethodRevision")
            require(
                isinstance(campaign_method_revision, str)
                and REVISION.fullmatch(campaign_method_revision),
                f"{case_id} assessed campaign method revision is invalid",
            )
            source_campaign_run_id = case.get("sourceAssessedCampaignRunId")
            require(
                isinstance(source_campaign_run_id, int)
                and source_campaign_run_id > 0,
                f"{case_id} source assessed campaign run id is invalid",
            )
        else:
            campaign_workflow = ".github/workflows/multi-repo-assessed-campaign.yml"
            campaign_method_revision = campaign_head_sha
            source_campaign_run_id = campaign_run_id
        population_row = population_cases[case_id]
        report_path = portable_file(root, case.get("discriminationReport"), f"{case_id} discrimination report")
        report, row = validate_discrimination(
            report_path,
            case_id,
            population_row["sourceSetSha256"],
            participant_order,
        )
        require(report["methodRevision"] == campaign_method_revision, f"{case_id} discrimination method revision differs from its declared method")
        discrimination_attestation_path = portable_file(
            root,
            case.get("discriminationAttestationVerification"),
            f"{case_id} discrimination attestation verification",
        )
        discrimination_attestation = validate_attestation_verification(
            discrimination_attestation_path,
            report_path,
            campaign_run_id,
            campaign_run_attempt,
            f"{case_id} discrimination attestation verification",
        )
        plan_evidence = None
        plan_qualified = False
        if manifest_schema == PREDECLARED_MANIFEST_SCHEMA:
            plan_path = portable_file(
                root,
                case.get("participantExperimentPlan"),
                f"{case_id} participant experiment plan",
            )
            plan = plan_validator.validate_plan(plan_path)
            require(
                plan["caseId"] == case_id
                and plan["sourceSetSha256"] == population_row["sourceSetSha256"]
                and plan["methodRevision"] == campaign_method_revision
                and plan["participantProfiles"] == participant_profiles,
                f"{case_id} participant experiment plan identity differs",
            )
            require(
                plan["executionProtocol"] == participant_execution_protocol,
                f"{case_id} participant execution protocol differs",
            )
            require(
                report["denominators"]["requiredTrialsPerParticipant"]
                == plan["trialsPerParticipant"],
                f"{case_id} planned trial denominator differs",
            )
            require(
                all(
                    profile["validTrials"] <= plan["trialsPerParticipant"]
                    for profile in row["participantProfiles"]
                ),
                f"{case_id} valid trials exceed the predeclared plan",
            )
            plan_attestation_path = portable_file(
                root,
                case.get("participantExperimentPlanAttestationVerification"),
                f"{case_id} participant experiment plan attestation verification",
            )
            plan_attestation = validate_attestation_verification(
                plan_attestation_path,
                plan_path,
                campaign_run_id,
                campaign_run_attempt,
                f"{case_id} participant experiment plan attestation verification",
            )
            plan_evidence = {
                "path": plan_path.relative_to(root).as_posix(),
                "sha256": digest(plan_path),
                "attestationVerificationPath": plan_attestation_path.relative_to(root).as_posix(),
                "attestationVerificationSha256": plan_attestation["sha256"],
                "status": plan["status"],
                "trialsPerParticipant": plan["trialsPerParticipant"],
            }
            plan_qualified = True
        device_import_evidence = None
        if campaign_workflow == ".github/workflows/harmony-device-campaign-import.yml":
            import_path = portable_file(
                root,
                case.get("deviceImportVerification"),
                f"{case_id} device import verification",
            )
            imported = load_object(import_path, f"{case_id} device import verification")
            require(
                imported.get("schema")
                == "agentlab.harmony_device_campaign_import_verification.v1"
                and imported.get("status") == "verified-review-required",
                f"{case_id} device import verification status differs",
            )
            require(
                imported.get("caseId") == case_id
                and imported.get("sourceSetSha256")
                == population_row["sourceSetSha256"]
                and imported.get("sourceMethodRevision")
                == campaign_method_revision
                and imported.get("verificationMethodRevision") == campaign_head_sha
                and (imported.get("sourceAssessedCampaign") or {}).get("runId")
                == source_campaign_run_id
                and imported.get("automaticPromotion") is False,
                f"{case_id} device import identity differs",
            )
            reconstruction = imported.get("trustedReconstruction") or {}
            require(
                reconstruction.get("discriminationReportSha256")
                == digest(report_path),
                f"{case_id} device import report digest differs",
            )
            import_attestation_path = portable_file(
                root,
                case.get("deviceImportAttestationVerification"),
                f"{case_id} device import attestation verification",
            )
            import_attestation = validate_attestation_verification(
                import_attestation_path,
                import_path,
                campaign_run_id,
                campaign_run_attempt,
                f"{case_id} device import attestation verification",
            )
            device_import_evidence = {
                "verificationPath": import_path.relative_to(root).as_posix(),
                "verificationSha256": digest(import_path),
                "attestationVerificationPath": import_attestation_path.relative_to(root).as_posix(),
                "attestationVerificationSha256": import_attestation["sha256"],
            }
        else:
            require(
                campaign_method_revision == campaign_head_sha
                and source_campaign_run_id == campaign_run_id
                and case.get("deviceImportVerification") is None
                and case.get("deviceImportAttestationVerification") is None,
                f"{case_id} static campaign provenance differs",
            )
        profiles = {profile["participantId"]: profile for profile in row["participantProfiles"]}
        ordered_profiles = [profiles[participant] for participant in participant_order]
        rates = [profile["passRate"] for profile in ordered_profiles]
        expected_order = all(lower <= upper for lower, upper in zip(rates, rates[1:]))
        resolution = capability_resolution(
            ordered_profiles,
            "passRate",
            "passRateWilson95",
        )
        weakest = profiles[participant_order[0]]
        strongest = profiles[participant_order[-1]]
        interval_separated = (
            strongest["passRateWilson95"]["lower"]
            > weakest["passRateWilson95"]["upper"]
        )
        for participant, profile in profiles.items():
            profile_totals[participant]["validTrials"] += profile["validTrials"]
            profile_totals[participant]["passedTrials"] += profile["passedTrials"]
        review_qualified = population_row.get("blindPilotReviewQualified") is True
        process_qualified = row["processMeasurement"]["coverageQualified"] is True
        self_assessment = row["processMeasurement"]["participantSelfAssessment"]
        self_assessment_qualified = self_assessment["coverageQualified"] is True
        dependency = row["processMeasurement"]["dependencyDiscovery"]
        dependency_measurement_qualified = (
            dependency["measurementCoverageQualified"] is True
        )
        harmony = row["processMeasurement"]["harmonyDevice"]
        harmony_end_to_end_qualified = harmony["endToEndEvidenceQualified"] is True
        if device_import_evidence is not None:
            require(
                imported.get("harmonyEndToEndEvidenceQualified")
                is harmony_end_to_end_qualified,
                f"{case_id} device import Harmony qualification differs",
            )
        outcome_qualified = row.get("eligible") is True
        qualified = (
            review_qualified
            and outcome_qualified
            and process_qualified
            and harmony_end_to_end_qualified
            and expected_order
            and interval_separated
        )
        case_rows.append(
            {
                "caseId": case_id,
                **(
                    {"candidateId": population_row["candidateId"]}
                    if population.get("schema") == "agentlab.blind_review_population_report.v2"
                    else {}
                ),
                "sourceSetSha256": population_row["sourceSetSha256"],
                "reviewPopulationAdjudicationRunId": population_row["adjudicationRunId"],
                "assessedCampaignRunId": campaign_run_id,
                "assessedCampaignRunAttempt": campaign_run_attempt,
                "assessedCampaignWorkflowPath": campaign_workflow,
                "assessedCampaignWorkflowHeadSha": campaign_head_sha,
                "assessedCampaignMethodRevision": campaign_method_revision,
                "sourceAssessedCampaignRunId": source_campaign_run_id,
                "reviewQualified": review_qualified,
                "outcomeDiscriminationEligible": outcome_qualified,
                "processMeasurementCoverageQualified": process_qualified,
                "participantSelfAssessmentCoverageQualified": self_assessment_qualified,
                "participantSelfAssessmentAgreementRate": self_assessment["agreementRate"],
                "participantSelfAssessmentMeanBrierScore": self_assessment["meanBrierScore"],
                "dependencyDiscoveryMeasurementCoverageQualified": dependency_measurement_qualified,
                "dependencyDiscoveryCoverageQualified": dependency["coverageQualified"],
                "dependencyDiscoveryRequiredObligationCoverage": dependency["requiredObligationCoverage"],
                "dependencyDiscoveryUnadjudicatedClaimCount": dependency["unadjudicatedClaimCount"],
                "dependencyDiscoveryMissingStageCount": dependency["missingStageCount"],
                "dependencyDiscoveryInvalidStageCount": dependency["invalidStageCount"],
                "harmonyDeviceExecutedAttemptCount": harmony["executedAttemptCount"],
                "harmonySuccessfulAttemptDeviceCoverageQualified": harmony["successfulAttemptDeviceCoverageQualified"],
                "harmonyProfiledSuccessCoverageQualified": harmony["profiledSuccessCoverageQualified"],
                "harmonyEndToEndEvidenceQualified": harmony_end_to_end_qualified,
                "harmonySmartPerfSampleCount": harmony["smartPerfSampleCount"],
                "expectedCapabilityOrderQualified": expected_order,
                "strongestMinusWeakestPassRate": strongest["passRate"] - weakest["passRate"],
                "strongestWeakestWilson95Separated": interval_separated,
                "capabilityResolution": resolution,
                "scorecardQualified": qualified,
                "participantExperimentPlanQualified": plan_qualified,
                "capabilityResolutionQualified": qualified and plan_qualified and resolution["qualified"],
                "participantProfiles": ordered_profiles,
                "reviewEvidence": {
                    "populationReportSha256": digest(population_path),
                    "adjudicationSha256": population_row["bundleEvidence"]["adjudication"]["sha256"],
                },
                "discriminationEvidence": {
                    "reportPath": report_path.relative_to(root).as_posix(),
                    "reportSha256": digest(report_path),
                    "methodRevision": report["methodRevision"],
                    "attestationVerificationPath": discrimination_attestation_path.relative_to(root).as_posix(),
                    "attestationVerificationSha256": discrimination_attestation["sha256"],
                },
                **(
                    {"participantExperimentPlanEvidence": plan_evidence}
                    if plan_evidence is not None
                    else {}
                ),
                **(
                    {"deviceImportEvidence": device_import_evidence}
                    if device_import_evidence is not None
                    else {}
                ),
            }
        )
    case_rows.sort(key=lambda row: row["caseId"])
    qualified_count = sum(row["scorecardQualified"] for row in case_rows)
    scorer = scorer_module()
    aggregate_profiles = []
    for participant in participant_order:
        totals = profile_totals[participant]
        valid = totals["validTrials"]
        passed = totals["passedTrials"]
        aggregate_profiles.append(
            {
                "participantId": participant,
                "validTrials": valid,
                "passedTrials": passed,
                "microPassRate": passed / valid,
                "microPassRateWilson95": scorer.wilson_interval(passed, valid),
            }
        )
    aggregate_resolution = capability_resolution(
        aggregate_profiles,
        "microPassRate",
        "microPassRateWilson95",
    )
    case_count = len(case_rows)
    measurement_qualified = qualified_count == case_count
    capability_resolution_qualified_count = sum(
        row["capabilityResolutionQualified"] for row in case_rows
    )
    capability_resolution_measurement_qualified = (
        measurement_qualified
        and all(row["participantExperimentPlanQualified"] for row in case_rows)
        and capability_resolution_qualified_count == case_count
        and aggregate_resolution["qualified"]
    )
    self_assessment_measurement_qualified = all(
        row["participantSelfAssessmentCoverageQualified"] for row in case_rows
    )
    dependency_discovery_measurement_qualified = all(
        row["dependencyDiscoveryMeasurementCoverageQualified"] for row in case_rows
    )
    dependency_discovery_coverage_qualified = all(
        row["dependencyDiscoveryCoverageQualified"] for row in case_rows
    )
    harmony_end_to_end_qualified = all(
        row["harmonyEndToEndEvidenceQualified"] for row in case_rows
    )
    return {
        "schema": (
            PREDECLARED_SCORECARD_SCHEMA
            if manifest_schema == PREDECLARED_MANIFEST_SCHEMA
            else (
                COHORT_BOUND_SCORECARD_SCHEMA
                if population.get("schema") == "agentlab.blind_review_population_report.v2"
                else SCORECARD_SCHEMA
            )
        ),
        "suiteId": suite_id,
        "methodRevision": method_revision,
        "manifestSha256": digest(manifest_path),
        "reviewPopulation": {
            "cohortId": population["cohortId"],
            "workflowRunId": population_source["workflowRunId"],
            "workflowRunAttempt": population_source["workflowRunAttempt"],
            "workflowHeadSha": population_source["workflowHeadSha"],
            "reportSha256": digest(population_path),
            "attestationVerificationPath": population_attestation_path.relative_to(root).as_posix(),
            "attestationVerificationSha256": population_attestation["sha256"],
            "caseMembershipSha256": population["caseMembershipSha256"],
            "populationRepresentativenessQualified": False,
            **(
                {
                    "candidateCohortMembershipQualified": True,
                    "candidateCohortSha256": population["candidateCohort"]["evidence"]["sha256"],
                }
                if population.get("schema") == "agentlab.blind_review_population_report.v2"
                else {}
            ),
        },
        "participantOrder": participant_order,
        "participantProfiles": participant_profiles,
        "participantExecutionProtocol": participant_execution_protocol,
        "denominators": {
            "caseCount": case_count,
            "qualifiedCaseCount": qualified_count,
            "participantTierCount": len(participant_order),
            "adjacentCapabilityPairCount": len(participant_order) - 1,
            "capabilityResolutionQualifiedCaseCount": capability_resolution_qualified_count,
            "validAttemptCount": sum(row["validTrials"] for row in aggregate_profiles),
            **(
                {
                    "selectedCandidateCount": population["denominators"]["selectedCandidateCount"],
                    "adjudicatedCandidateCount": population["denominators"]["adjudicatedCandidateCount"],
                    "unadjudicatedCandidateCount": population["denominators"]["unadjudicatedCandidateCount"],
                    "caseYieldRate": population["denominators"]["caseYieldRate"],
                }
                if population.get("schema") == "agentlab.blind_review_population_report.v2"
                else {}
            ),
            "successEvent": "independent taskPassed verdict from an infrastructure-valid attempt",
        },
        "aggregateParticipantProfiles": aggregate_profiles,
        "aggregateCapabilityResolution": aggregate_resolution,
        "cases": case_rows,
        "qualification": {
            "suiteMeasurementQualified": measurement_qualified,
            "participantExperimentPlanQualified": all(
                row["participantExperimentPlanQualified"] for row in case_rows
            ),
            "capabilityResolutionMeasurementQualified": capability_resolution_measurement_qualified,
            "capabilityResolutionQualifiedCaseRate": capability_resolution_qualified_count / case_count,
            "capabilityResolutionQualifiedCaseRateWilson95": scorer.wilson_interval(
                capability_resolution_qualified_count,
                case_count,
            ),
            "participantSelfAssessmentMeasurementQualified": self_assessment_measurement_qualified,
            "dependencyDiscoveryMeasurementQualified": dependency_discovery_measurement_qualified,
            "dependencyDiscoveryCoverageQualified": dependency_discovery_coverage_qualified,
            "harmonyEndToEndEvidenceQualified": harmony_end_to_end_qualified,
            "qualifiedCaseRate": qualified_count / case_count,
            "qualifiedCaseRateWilson95": scorer.wilson_interval(qualified_count, case_count),
            "populationRepresentativenessQualified": False,
            "modelTrainingExclusionQualified": False,
            "eligibleForUnseenAgentDiscrimination": False,
            "benchmarkPopulationQualified": False,
        },
        "policy": {
            "automaticPromotion": False,
            "nextAction": "independent-sampling-frame-review-and-held-out-three-tier-suite-run",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        value = build_scorecard(args.manifest)
        body = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output:
            require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(body, encoding="utf-8")
        else:
            print(body, end="")
    except (ScorecardError, OSError, ValueError) as error:
        print(f"Agent suite scorecard invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
