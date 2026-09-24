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
SCORECARD_SCHEMA = "agentlab.agent_suite_scorecard.v1"
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


def validate_population(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    value = load_object(path, "blind review population report")
    require(value.get("schema") == "agentlab.blind_review_population_report.v1", "population report schema differs")
    require(isinstance(value.get("cohortId"), str) and TOKEN.fullmatch(value["cohortId"]), "population cohort identity is invalid")
    require(isinstance(value.get("methodRevision"), str) and REVISION.fullmatch(value["methodRevision"]), "population method revision is invalid")
    require(isinstance(value.get("caseMembershipSha256"), str) and SHA256.fullmatch(value["caseMembershipSha256"]), "population membership digest is invalid")
    cases = value.get("cases")
    require(isinstance(cases, list) and len(cases) >= 2, "population report requires at least two cases")
    rows: dict[str, dict[str, Any]] = {}
    for row in cases:
        require(isinstance(row, dict), "population case is invalid")
        case_id = row.get("caseId")
        require(isinstance(case_id, str) and TOKEN.fullmatch(case_id), "population case identity is invalid")
        require(case_id not in rows, f"duplicate population case: {case_id}")
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
    qualification = value.get("qualification")
    require(isinstance(qualification, dict), "population qualification is invalid")
    require(qualification.get("allCasesAuthenticatedAndAttested") is True, "population cases are not all authenticated")
    require(qualification.get("populationRepresentativenessQualified") is False, "population report overclaims representativeness")
    require(qualification.get("modelTrainingExclusionQualified") is False, "population report overclaims model-training exclusion")
    require(qualification.get("eligibleForUnseenAgentDiscrimination") is False, "population report overclaims unseen-Agent eligibility")
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
    return value, row


def build_scorecard(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve(strict=True)
    root = manifest_path.parent
    manifest = load_object(manifest_path, "Agent suite scorecard manifest")
    require(manifest.get("schema") == MANIFEST_SCHEMA, "unsupported Agent suite scorecard manifest schema")
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
        require(
            set(case)
            == {
                "caseId",
                "assessedCampaignRunId",
                "assessedCampaignRunAttempt",
                "assessedCampaignWorkflowHeadSha",
                "discriminationReport",
                "discriminationAttestationVerification",
            },
            "scorecard case fields differ",
        )
        case_id = case["caseId"]
        campaign_run_id = case.get("assessedCampaignRunId")
        require(isinstance(campaign_run_id, int) and campaign_run_id > 0, f"{case_id} assessed campaign run id is invalid")
        campaign_run_attempt = case.get("assessedCampaignRunAttempt")
        require(isinstance(campaign_run_attempt, int) and campaign_run_attempt > 0, f"{case_id} assessed campaign run attempt is invalid")
        campaign_head_sha = case.get("assessedCampaignWorkflowHeadSha")
        require(isinstance(campaign_head_sha, str) and REVISION.fullmatch(campaign_head_sha), f"{case_id} assessed campaign revision is invalid")
        population_row = population_cases[case_id]
        report_path = portable_file(root, case.get("discriminationReport"), f"{case_id} discrimination report")
        report, row = validate_discrimination(
            report_path,
            case_id,
            population_row["sourceSetSha256"],
            participant_order,
        )
        require(report["methodRevision"] == campaign_head_sha, f"{case_id} discrimination method revision differs from its workflow run")
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
        profiles = {profile["participantId"]: profile for profile in row["participantProfiles"]}
        rates = [profiles[participant]["passRate"] for participant in participant_order]
        expected_order = all(lower <= upper for lower, upper in zip(rates, rates[1:]))
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
        outcome_qualified = row.get("eligible") is True
        qualified = (
            review_qualified
            and outcome_qualified
            and process_qualified
            and expected_order
            and interval_separated
        )
        case_rows.append(
            {
                "caseId": case_id,
                "sourceSetSha256": population_row["sourceSetSha256"],
                "reviewPopulationAdjudicationRunId": population_row["adjudicationRunId"],
                "assessedCampaignRunId": campaign_run_id,
                "assessedCampaignRunAttempt": campaign_run_attempt,
                "assessedCampaignWorkflowHeadSha": campaign_head_sha,
                "reviewQualified": review_qualified,
                "outcomeDiscriminationEligible": outcome_qualified,
                "processMeasurementCoverageQualified": process_qualified,
                "participantSelfAssessmentCoverageQualified": self_assessment_qualified,
                "participantSelfAssessmentAgreementRate": self_assessment["agreementRate"],
                "participantSelfAssessmentMeanBrierScore": self_assessment["meanBrierScore"],
                "expectedCapabilityOrderQualified": expected_order,
                "strongestMinusWeakestPassRate": strongest["passRate"] - weakest["passRate"],
                "strongestWeakestWilson95Separated": interval_separated,
                "scorecardQualified": qualified,
                "participantProfiles": [profiles[participant] for participant in participant_order],
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
    case_count = len(case_rows)
    measurement_qualified = qualified_count == case_count
    self_assessment_measurement_qualified = all(
        row["participantSelfAssessmentCoverageQualified"] for row in case_rows
    )
    return {
        "schema": SCORECARD_SCHEMA,
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
        },
        "participantOrder": participant_order,
        "denominators": {
            "caseCount": case_count,
            "qualifiedCaseCount": qualified_count,
            "validAttemptCount": sum(row["validTrials"] for row in aggregate_profiles),
            "successEvent": "independent taskPassed verdict from an infrastructure-valid attempt",
        },
        "aggregateParticipantProfiles": aggregate_profiles,
        "cases": case_rows,
        "qualification": {
            "suiteMeasurementQualified": measurement_qualified,
            "participantSelfAssessmentMeasurementQualified": self_assessment_measurement_qualified,
            "qualifiedCaseRate": qualified_count / case_count,
            "qualifiedCaseRateWilson95": scorer.wilson_interval(qualified_count, case_count),
            "populationRepresentativenessQualified": False,
            "modelTrainingExclusionQualified": False,
            "eligibleForUnseenAgentDiscrimination": False,
            "benchmarkPopulationQualified": False,
        },
        "policy": {
            "automaticPromotion": False,
            "nextAction": "independent-sampling-frame-review-and-new-held-out-suite-run",
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
