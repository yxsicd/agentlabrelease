#!/usr/bin/env python3
"""Validate a controlled Harmony UI FAIL_TO_PASS calibration receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")


class CalibrationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CalibrationError(message)


def digest(value: object, label: str) -> str:
    text = str(value or "")
    require(SHA256.fullmatch(text) is not None, f"{label} must be a SHA-256 digest")
    return text


def revision(value: object, label: str) -> str:
    text = str(value or "")
    require(REVISION.fullmatch(text) is not None, f"{label} must be a full Git commit")
    return text


def validate_authority(value: object, label: str) -> None:
    require(isinstance(value, dict), f"{label} executionAuthority is required")
    require(value.get("routeDecision") == "peer_direct", f"{label} must use peer_direct routing")
    require(str(value.get("targetPeerId", "")).startswith("lgw_"), f"{label} targetPeerId is required")
    require(str(value.get("operationId", "")).startswith("exec-"), f"{label} operationId is required")
    require(isinstance(value.get("traceIds"), list) and value["traceIds"], f"{label} traceIds are required")


def validate_result(
    attempt: object,
    label: str,
    *,
    hap_sha: str,
    scenario_sha: str,
    passed: bool,
    check_field: str = "repairCheckPassed",
) -> None:
    require(isinstance(attempt, dict), f"{label} is required")
    validate_authority(attempt.get("executionAuthority"), label)
    result = attempt.get("result")
    require(isinstance(result, dict), f"{label} result is required")
    require(result.get("schema") == "agentlab.harmony_emulator_case_result.v2", f"{label} must use result v2")
    expected = "passed" if passed else "failed"
    require(result.get("status") == expected, f"{label} status must be {expected}")
    require(result.get("oracleStatus") == expected, f"{label} Oracle status must be {expected}")
    require(result.get("assessmentStatus") == "assessed", f"{label} must be assessed")
    require(result.get("infrastructureAvailable") is True, f"{label} infrastructure must be available")
    require(result.get("subjectTaskSucceeded") is passed, f"{label} task verdict differs")
    require(result.get("failureClass") == ("none" if passed else "oracle"), f"{label} failure class differs")
    require(result.get("hapSha256") == hap_sha, f"{label} HAP differs")
    require(result.get("scenarioSha256") == scenario_sha, f"{label} scenario differs")
    require(attempt.get(check_field) is passed, f"{label} {check_field} differs")
    for field in ("resultSha256", "actionsSha256", "checksSha256", "layoutBeforeSha256", "layoutAfterSha256"):
        digest(attempt.get(field), f"{label} {field}")


def scenario_contract(path: Path) -> tuple[str, tuple[int, int], str, str]:
    case_ids: list[str] = []
    taps: list[tuple[int, int]] = []
    assertions: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        fields = raw.split("\t")
        if fields[0] == "case" and len(fields) == 2:
            case_ids.append(fields[1])
        elif fields[0] == "tap" and len(fields) == 3:
            try:
                taps.append((int(fields[1]), int(fields[2])))
            except ValueError as error:
                raise CalibrationError("scenario tap coordinates must be integers") from error
        elif fields[0] in ("assert-text", "assert-no-text") and len(fields) == 3:
            assertions.append((fields[0], fields[2]))
    require(len(case_ids) == 1 and len(taps) == 1 and len(assertions) == 1, "scenario must have one case, tap and assertion")
    return case_ids[0], taps[0], assertions[0][0], assertions[0][1]


def validate_scenario_descriptor(value: object, label: str, base_dir: Path | None) -> tuple[dict, str]:
    require(isinstance(value, dict), f"{label} is required")
    descriptor = value
    scenario_sha = digest(descriptor.get("sha256"), label)
    require(descriptor.get("assertionKind") in ("assert-text", "assert-no-text"), f"{label} assertionKind differs")
    require(isinstance(descriptor.get("assertionText"), str) and descriptor["assertionText"], f"{label} assertionText is required")
    require(str(descriptor.get("expectedPagePath", "")).startswith("pages/"), f"{label} expectedPagePath is required")
    if base_dir is not None:
        path = base_dir / str(descriptor.get("path", ""))
        require(path.is_file(), f"{label} file is missing")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == scenario_sha, f"{label} file digest differs")
        case_id, tap, assertion_kind, assertion = scenario_contract(path)
        require(case_id == descriptor.get("id"), f"{label} case id differs")
        require(list(tap) == descriptor.get("tap"), f"{label} tap differs")
        require(assertion_kind == descriptor.get("assertionKind"), f"{label} assertion kind differs")
        require(assertion == descriptor.get("assertionText"), f"{label} assertion text differs")
    return descriptor, scenario_sha


def validate(value: object, base_dir: Path | None = None) -> dict:
    require(isinstance(value, dict), "calibration must be a JSON object")
    data = value
    require(data.get("schema") == "agentlab.harmony_ui_known_fix_calibration.v2", "unsupported schema")
    require(data.get("status") == "controlled-fail-to-pass-observed", "unsupported status")
    require(data.get("automaticPromotion") is False, "automaticPromotion must be false")

    baseline = data.get("baselineSource")
    require(isinstance(baseline, dict), "baselineSource is required")
    baseline_revision = revision(baseline.get("revision"), "baseline revision")
    baseline_hap = digest(baseline.get("hapSha256"), "baseline HAP")
    require(baseline.get("sourceIdentity") == f"artifact-sha256:{baseline_hap}", "baseline source identity differs")

    known = data.get("knownFix")
    require(isinstance(known, dict), "knownFix is required")
    require(known.get("classification") == "controlled-calibration-variant-not-gold", "known fix must not be gold")
    revision(known.get("revision"), "known-fix revision")
    require(revision(known.get("parentRevision"), "known-fix parent") == baseline_revision, "known fix must descend from baseline")
    require(known.get("changedFiles") == 1 and known.get("insertions") == 1 and known.get("deletions") == 0, "known fix must remain one insertion in one file")
    require(str(known.get("path", "")).endswith("/main_pages.json"), "known fix must identify the page profile")
    for field in ("patchSha256", "beforeFileSha256", "afterFileSha256"):
        digest(known.get(field), f"known fix {field}")
    if base_dir is not None:
        patch_path = base_dir / str(known.get("patchPath", ""))
        require(patch_path.is_file(), "known-fix patch file is missing")
        require(hashlib.sha256(patch_path.read_bytes()).hexdigest() == known.get("patchSha256"), "known-fix patch digest differs")
    known_hap = digest(known.get("hapSha256"), "known-fix HAP")
    require(known_hap != baseline_hap, "known-fix and baseline HAPs must differ")
    require(known.get("sourceIdentity") == f"artifact-sha256:{known_hap}", "known-fix source identity differs")
    require(isinstance(known.get("hapBytes"), int) and known["hapBytes"] > 0, "known-fix HAP bytes are required")

    alternative = data.get("alternativeValid")
    require(isinstance(alternative, dict), "alternativeValid is required")
    require(alternative.get("id") == "named-route", "alternative-valid id differs")
    require(
        alternative.get("classification") == "controlled-alternative-valid-not-gold",
        "alternative-valid solution must not be gold",
    )
    require(
        revision(alternative.get("sourceRevision"), "alternative-valid source revision") == baseline_revision,
        "alternative-valid solution must start from baseline",
    )
    paths = alternative.get("paths")
    require(isinstance(paths, list) and len(paths) == 2 and len(set(paths)) == 2, "alternative-valid solution must change exactly two distinct paths")
    require(known.get("path") not in paths, "alternative-valid solution must not overlap the known-fix path")
    require(alternative.get("referenceOverlapPaths") == [], "alternative-valid solution must declare zero reference path overlap")
    require(
        alternative.get("changedFiles") == 2
        and alternative.get("insertions") == 5
        and alternative.get("deletions") == 5,
        "alternative-valid diff statistics differ",
    )
    alternative_patch_sha = digest(alternative.get("patchSha256"), "alternative-valid patch")
    if base_dir is not None:
        patch_path = base_dir / str(alternative.get("patchPath", ""))
        require(patch_path.is_file(), "alternative-valid patch file is missing")
        require(hashlib.sha256(patch_path.read_bytes()).hexdigest() == alternative_patch_sha, "alternative-valid patch digest differs")
    require(alternative.get("routeMechanism") == "ArkUI named route", "alternative-valid route mechanism differs")
    baseline_main_pages = digest(alternative.get("baselineMainPagesSha256"), "alternative-valid baseline main_pages")
    alternative_main_pages = digest(alternative.get("alternativeMainPagesSha256"), "alternative-valid main_pages")
    require(
        baseline_main_pages == alternative_main_pages == known.get("beforeFileSha256"),
        "alternative-valid main_pages must remain byte-identical to baseline",
    )
    after_files = alternative.get("afterFileSha256")
    require(isinstance(after_files, dict) and set(after_files) == set(paths), "alternative-valid after-file identities differ")
    for path, sha in after_files.items():
        digest(sha, f"alternative-valid after file {path}")
    alternative_hap = digest(alternative.get("hapSha256"), "alternative-valid HAP")
    require(alternative_hap not in (baseline_hap, known_hap), "alternative-valid HAP must differ from baseline and known fix")
    require(alternative.get("sourceIdentity") == f"artifact-sha256:{alternative_hap}", "alternative-valid source identity differs")
    require(isinstance(alternative.get("hapBytes"), int) and alternative["hapBytes"] > 0, "alternative-valid HAP bytes are required")
    build = alternative.get("build")
    require(isinstance(build, dict) and build.get("status") == "successful", "alternative-valid build must be successful")
    alternative_transfer = alternative.get("transfer")
    require(isinstance(alternative_transfer, dict), "alternative-valid transfer is required")
    require(alternative_transfer.get("transport") == "AWMCP RGW HTTP binary stream", "alternative-valid transfer transport differs")
    require(str(alternative_transfer.get("fromPeerId", "")).startswith("lgw_"), "alternative-valid source peer is required")
    require(str(alternative_transfer.get("toPeerId", "")).startswith("lgw_"), "alternative-valid target peer is required")
    require(alternative_transfer.get("verifiedSha256") == alternative_hap, "alternative-valid transferred HAP digest differs")
    require(alternative_transfer.get("verifiedBytes") == alternative.get("hapBytes"), "alternative-valid transferred HAP bytes differ")

    transfer = data.get("transfer")
    require(isinstance(transfer, dict), "transfer is required")
    require(transfer.get("transport") == "LAN HTTP", "known-fix transfer must use LAN HTTP")
    require(transfer.get("verifiedSha256") == known_hap, "transferred HAP digest differs")
    require(transfer.get("verifiedBytes") == known.get("hapBytes"), "transferred HAP bytes differ")

    scenario = data.get("scenario")
    require(isinstance(scenario, dict), "scenario is required")
    scenario_sha = digest(scenario.get("sha256"), "scenario")
    require(scenario.get("repairAssertion") == "Example Domain is visible after selecting UserAgent_four.", "repair assertion differs")
    if base_dir is not None:
        path = base_dir / str(scenario.get("path", ""))
        require(path.is_file(), "scenario file is missing")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == scenario_sha, "scenario file digest differs")
        case_id, tap, assertion_kind, assertion = scenario_contract(path)
        require(case_id == scenario.get("id"), "scenario case id differs")
        require(list(tap) == scenario.get("tap"), "scenario tap differs")
        require(assertion_kind == "assert-text" and assertion == "Example Domain", "scenario must assert target-page visible semantics")

    preservation_scenario, preservation_sha = validate_scenario_descriptor(
        data.get("preservationScenario"), "preservation scenario", base_dir
    )
    require(
        preservation_scenario.get("assertionKind") == "assert-no-text"
        and preservation_scenario.get("assertionText") == "Cache_two"
        and preservation_scenario.get("expectedPagePath") == "pages/DomStorage",
        "preservation scenario must bind the DomStorage route and absent Index control",
    )

    superseded = data.get("supersededOracleFinding")
    require(isinstance(superseded, dict), "supersededOracleFinding is required")
    require(superseded.get("falseFailure") is True, "superseded Oracle must retain the false failure")
    require(superseded.get("observedPagePath") == "pages/UserAgent_four", "superseded Oracle must retain target page evidence")
    require(superseded.get("observedVisibleText") == "Example Domain", "superseded Oracle must retain visible target semantics")
    require("pagePath=" in str(superseded.get("cause", "")), "superseded Oracle cause must identify metadata matching")
    digest(superseded.get("scenarioSha256"), "superseded scenario")
    digest(superseded.get("knownFixResultSha256"), "superseded result")

    rejected_preservation = data.get("rejectedPreservationAttempt")
    require(isinstance(rejected_preservation, dict), "rejectedPreservationAttempt is required")
    require(rejected_preservation.get("status") == "failed" and rejected_preservation.get("infrastructureAvailable") is True, "rejected preservation attempt must retain an assessed failure")
    require(rejected_preservation.get("observedPagePath") == "pages/DomStorage", "rejected preservation attempt must retain the successful route")
    require("environment-sensitive" in str(rejected_preservation.get("rejectionReason", "")), "rejected preservation reason must identify environment sensitivity")
    digest(rejected_preservation.get("scenarioSha256"), "rejected preservation scenario")
    digest(rejected_preservation.get("resultSha256"), "rejected preservation result")

    validate_result(data.get("baselineAttempt"), "baseline attempt", hap_sha=baseline_hap, scenario_sha=scenario_sha, passed=False)
    validate_result(data.get("knownFixAttempt"), "known-fix attempt", hap_sha=known_hap, scenario_sha=scenario_sha, passed=True)
    validate_result(data.get("alternativeValidAttempt"), "alternative-valid attempt", hap_sha=alternative_hap, scenario_sha=scenario_sha, passed=True)
    require(data["baselineAttempt"].get("observedPagePathAfter") == "pages/Index", "baseline must remain on Index")
    require(data["knownFixAttempt"].get("observedPagePathAfter") == "pages/UserAgent_four", "known fix must reach target page")
    require(data["knownFixAttempt"].get("observedVisibleTextAfter") == "Example Domain", "known fix target semantics differ")
    require(data["alternativeValidAttempt"].get("observedPagePathAfter") == "pages/UserAgent_four", "alternative-valid solution must reach target page")
    require(data["alternativeValidAttempt"].get("observedVisibleTextAfter") == "Example Domain", "alternative-valid target semantics differ")
    validate_result(data.get("baselinePreservationAttempt"), "baseline preservation attempt", hap_sha=baseline_hap, scenario_sha=preservation_sha, passed=True, check_field="preservationCheckPassed")
    validate_result(data.get("knownFixPreservationAttempt"), "known-fix preservation attempt", hap_sha=known_hap, scenario_sha=preservation_sha, passed=True, check_field="preservationCheckPassed")
    validate_result(data.get("alternativeValidPreservationAttempt"), "alternative-valid preservation attempt", hap_sha=alternative_hap, scenario_sha=preservation_sha, passed=True, check_field="preservationCheckPassed")
    require(data["baselinePreservationAttempt"].get("observedPagePathAfter") == "pages/DomStorage", "baseline preservation must reach DomStorage")
    require(data["knownFixPreservationAttempt"].get("observedPagePathAfter") == "pages/DomStorage", "known-fix preservation must reach DomStorage")
    require(data["alternativeValidPreservationAttempt"].get("observedPagePathAfter") == "pages/DomStorage", "alternative-valid preservation must reach DomStorage")

    additional = data.get("additionalPreservationCases")
    require(isinstance(additional, list) and len(additional) == 2, "exactly two additional preservation cases are required")
    preservation_ids = [preservation_scenario.get("id")]
    positive_visible_semantic_cases = 0
    for index, item in enumerate(additional):
        label = f"additional preservation case {index + 1}"
        require(isinstance(item, dict), f"{label} is required")
        descriptor, descriptor_sha = validate_scenario_descriptor(item.get("scenario"), f"{label} scenario", base_dir)
        require(item.get("id") == descriptor.get("id"), f"{label} id differs")
        preservation_ids.append(str(item.get("id")))
        baseline_attempt = item.get("baselineAttempt")
        fixed_attempt = item.get("knownFixAttempt")
        alternative_attempt = item.get("alternativeValidAttempt")
        validate_result(baseline_attempt, f"{label} baseline", hap_sha=baseline_hap, scenario_sha=descriptor_sha, passed=True, check_field="preservationCheckPassed")
        validate_result(fixed_attempt, f"{label} known fix", hap_sha=known_hap, scenario_sha=descriptor_sha, passed=True, check_field="preservationCheckPassed")
        validate_result(alternative_attempt, f"{label} alternative valid", hap_sha=alternative_hap, scenario_sha=descriptor_sha, passed=True, check_field="preservationCheckPassed")
        expected_page = descriptor.get("expectedPagePath")
        require(baseline_attempt.get("observedPagePathAfter") == expected_page, f"{label} baseline page differs")
        require(fixed_attempt.get("observedPagePathAfter") == expected_page, f"{label} known-fix page differs")
        require(alternative_attempt.get("observedPagePathAfter") == expected_page, f"{label} alternative-valid page differs")
        if descriptor.get("assertionKind") == "assert-text":
            positive_visible_semantic_cases += 1
            expected_text = descriptor.get("assertionText")
            require(baseline_attempt.get("observedVisibleTextAfter") == expected_text, f"{label} baseline visible text differs")
            require(fixed_attempt.get("observedVisibleTextAfter") == expected_text, f"{label} known-fix visible text differs")
            require(alternative_attempt.get("observedVisibleTextAfter") == expected_text, f"{label} alternative-valid visible text differs")
    require(len(set(preservation_ids)) == len(preservation_ids), "preservation case ids must be unique")

    freshness = data.get("freshness")
    require(isinstance(freshness, dict), "freshness declaration is required")
    require(freshness.get("schema") == "agentlab.case_freshness.v1", "unsupported freshness schema")
    require(freshness.get("constructionMode") == "synthetic-controlled-calibration", "freshness construction mode differs")
    require(freshness.get("sourceRepositoryVisibility") == "public", "source visibility must remain public")
    require(freshness.get("historicalIssueMined") is False and freshness.get("historicalFixMined") is False, "controlled calibration must not claim historical mining")
    require(freshness.get("controlledFixCreatedForCalibration") is True, "controlled fix provenance is required")
    require(freshness.get("controlledFixPublishedInReleasePr") is True, "publication boundary is required")
    require(freshness.get("assessedParticipantRun") is False, "calibration must not claim a participant run")
    require(freshness.get("hiddenOracleDuringCalibration") is True, "calibration Oracle must be hidden during execution")
    require(freshness.get("modelTrainingExclusionKnown") is False, "training exclusion must not be claimed")
    require(freshness.get("contaminationRisk") == "unknown-after-publication", "contamination risk must remain conservative")
    require(freshness.get("eligibleForUnseenAgentDiscrimination") is False, "public calibration cannot claim unseen-Agent discrimination")

    matrix = data.get("qualificationMatrix")
    require(isinstance(matrix, dict), "qualificationMatrix is required")
    repairs = matrix.get("repairChecks")
    require(isinstance(repairs, dict) and all(repairs.get(key) is True for key in ("failToPassObserved", "sameScenario", "sameEnvironment")), "repair checks must bind the controlled comparison")
    preservation = matrix.get("preservationChecks")
    require(isinstance(preservation, dict) and all(preservation.get(key) is True for key in ("defined", "passToPassObserved", "sameScenario", "sameEnvironment")), "preservation checks must bind the controlled comparison")
    require(preservation.get("caseCount") == 3, "preservation matrix case count differs")
    require(preservation.get("positiveVisibleSemanticCaseCount") == positive_visible_semantic_cases == 2, "preservation semantic case count differs")
    require(preservation.get("caseIds") == preservation_ids, "preservation matrix case ids differ")
    breadth = matrix.get("oracleBreadth")
    require(isinstance(breadth, dict), "oracle breadth qualification is required")
    for field in (
        "alternativeValidDefined",
        "structurallyDistinctFromKnownFix",
        "baselineMainPagesUnchanged",
        "repairPassed",
        "preservationPassed",
        "allFourDeviceScenariosPassed",
    ):
        require(breadth.get(field) is True, f"oracle breadth {field} must be observed")
    require(breadth.get("referenceOverlapPathCount") == 0, "oracle breadth reference overlap count differs")
    require(breadth.get("preservationCaseCount") == 3, "oracle breadth preservation case count differs")
    review = matrix.get("review")
    require(isinstance(review, dict) and review.get("independent") is False and review.get("knownFixAcceptedAsReference") is False, "known fix must remain unreviewed and non-reference")

    scope = data.get("qualificationScope")
    require(isinstance(scope, dict), "qualificationScope is required")
    for field in ("controlledKnownFix", "businessSemanticAssertionObserved", "candidateFailToPass", "preservationPassToPass", "alternativeValidQualified", "freshnessDeclared"):
        require(scope.get(field) is True, f"{field} must be observed")
    for field in ("businessUiOracleQualified", "independentReview", "referenceRepair", "unseenAgentDiscrimination", "performanceComparison"):
        require(scope.get(field) is False, f"{field} must remain unqualified")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("calibration", type=Path)
    args = parser.parse_args()
    try:
        value = validate(json.loads(args.calibration.read_text(encoding="utf-8")), args.calibration.parent)
    except (OSError, json.JSONDecodeError, CalibrationError) as error:
        print(f"Harmony UI known-fix calibration invalid: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "status": value["status"], "scenarioId": value["scenario"]["id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
