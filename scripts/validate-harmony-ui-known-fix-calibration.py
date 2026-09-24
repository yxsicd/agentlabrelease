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


def validate(value: object, base_dir: Path | None = None) -> dict:
    require(isinstance(value, dict), "calibration must be a JSON object")
    data = value
    require(data.get("schema") == "agentlab.harmony_ui_known_fix_calibration.v1", "unsupported schema")
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

    preservation_scenario = data.get("preservationScenario")
    require(isinstance(preservation_scenario, dict), "preservationScenario is required")
    preservation_sha = digest(preservation_scenario.get("sha256"), "preservation scenario")
    if base_dir is not None:
        path = base_dir / str(preservation_scenario.get("path", ""))
        require(path.is_file(), "preservation scenario file is missing")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == preservation_sha, "preservation scenario file digest differs")
        case_id, tap, assertion_kind, assertion = scenario_contract(path)
        require(case_id == preservation_scenario.get("id"), "preservation scenario case id differs")
        require(list(tap) == preservation_scenario.get("tap"), "preservation scenario tap differs")
        require(assertion_kind == "assert-no-text" and assertion == "Cache_two", "preservation scenario must assert the Index control is absent")

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
    require(data["baselineAttempt"].get("observedPagePathAfter") == "pages/Index", "baseline must remain on Index")
    require(data["knownFixAttempt"].get("observedPagePathAfter") == "pages/UserAgent_four", "known fix must reach target page")
    require(data["knownFixAttempt"].get("observedVisibleTextAfter") == "Example Domain", "known fix target semantics differ")
    validate_result(data.get("baselinePreservationAttempt"), "baseline preservation attempt", hap_sha=baseline_hap, scenario_sha=preservation_sha, passed=True, check_field="preservationCheckPassed")
    validate_result(data.get("knownFixPreservationAttempt"), "known-fix preservation attempt", hap_sha=known_hap, scenario_sha=preservation_sha, passed=True, check_field="preservationCheckPassed")
    require(data["baselinePreservationAttempt"].get("observedPagePathAfter") == "pages/DomStorage", "baseline preservation must reach DomStorage")
    require(data["knownFixPreservationAttempt"].get("observedPagePathAfter") == "pages/DomStorage", "known-fix preservation must reach DomStorage")

    matrix = data.get("qualificationMatrix")
    require(isinstance(matrix, dict), "qualificationMatrix is required")
    repairs = matrix.get("repairChecks")
    require(isinstance(repairs, dict) and all(repairs.get(key) is True for key in ("failToPassObserved", "sameScenario", "sameEnvironment")), "repair checks must bind the controlled comparison")
    preservation = matrix.get("preservationChecks")
    require(isinstance(preservation, dict) and all(preservation.get(key) is True for key in ("defined", "passToPassObserved", "sameScenario", "sameEnvironment")), "preservation checks must bind the controlled comparison")
    review = matrix.get("review")
    require(isinstance(review, dict) and review.get("independent") is False and review.get("knownFixAcceptedAsReference") is False, "known fix must remain unreviewed and non-reference")

    scope = data.get("qualificationScope")
    require(isinstance(scope, dict), "qualificationScope is required")
    for field in ("controlledKnownFix", "businessSemanticAssertionObserved", "candidateFailToPass", "preservationPassToPass"):
        require(scope.get(field) is True, f"{field} must be observed")
    for field in ("businessUiOracleQualified", "independentReview", "referenceRepair", "performanceComparison"):
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
