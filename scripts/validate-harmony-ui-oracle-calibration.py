#!/usr/bin/env python3
"""Validate a coordinate-calibrated Harmony UI Oracle candidate receipt."""
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


def point(value: object, label: str) -> tuple[int, int]:
    require(isinstance(value, list) and len(value) == 2, f"{label} must be [x,y]")
    require(all(isinstance(item, int) for item in value), f"{label} coordinates must be integers")
    return value[0], value[1]


def bounds(value: object, label: str) -> tuple[int, int, int, int]:
    require(isinstance(value, list) and len(value) == 4, f"{label} must be [left,top,right,bottom]")
    require(all(isinstance(item, int) for item in value), f"{label} values must be integers")
    left, top, right, bottom = value
    require(left < right and top < bottom, f"{label} must have positive area")
    return left, top, right, bottom


def contains(rect: tuple[int, int, int, int], location: tuple[int, int]) -> bool:
    left, top, right, bottom = rect
    x, y = location
    return left <= x <= right and top <= y <= bottom


def scenario_tap(path: Path) -> tuple[int, int]:
    taps = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        fields = raw.split("\t")
        if fields[0] == "tap":
            require(len(fields) == 3, "scenario tap row must contain x and y")
            try:
                taps.append((int(fields[1]), int(fields[2])))
            except ValueError as error:
                raise CalibrationError("scenario tap coordinates must be integers") from error
    require(len(taps) == 1, "scenario must contain exactly one tap")
    return taps[0]


def validate(value: object, base_dir: Path | None = None) -> dict:
    require(isinstance(value, dict), "calibration must be a JSON object")
    data = value
    require(data.get("schema") == "agentlab.harmony_ui_oracle_calibration.v1", "unsupported schema")
    require(data.get("status") == "candidate-baseline-failure-observed", "unsupported status")
    require(data.get("automaticPromotion") is False, "automaticPromotion must be false")

    source = data.get("source")
    require(isinstance(source, dict), "source is required")
    require(REVISION.fullmatch(str(source.get("revision", ""))) is not None, "source revision must be a full Git commit")
    hap_sha = digest(source.get("hapSha256"), "source HAP")
    require(source.get("sourceIdentity") == f"artifact-sha256:{hap_sha}", "source identity must bind the exact HAP")

    scenario = data.get("scenario")
    require(isinstance(scenario, dict), "scenario is required")
    scenario_sha = digest(scenario.get("sha256"), "scenario")
    expected_tap = point(scenario.get("tap"), "scenario tap")
    if base_dir is not None:
        path = base_dir / str(scenario.get("path", ""))
        require(path.is_file(), "scenario file is missing")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == scenario_sha, "scenario file digest differs")
        require(scenario_tap(path) == expected_tap, "scenario file tap differs")

    layout = data.get("layoutCalibration")
    require(isinstance(layout, dict), "layoutCalibration is required")
    controls = layout.get("controls")
    require(isinstance(controls, list) and len(controls) >= 2, "at least two calibrated controls are required")
    by_label = {}
    for index, control in enumerate(controls):
        require(isinstance(control, dict), f"controls[{index}] must be an object")
        label = control.get("label")
        require(isinstance(label, str) and label and label not in by_label, "control labels must be unique")
        by_label[label] = bounds(control.get("bounds"), f"controls[{index}].bounds")
    intended = str(scenario.get("intendedControl", ""))
    decoy = str(layout.get("decoyControl", ""))
    require(intended in by_label and decoy in by_label and intended != decoy, "intended and decoy controls must be calibrated")
    require(contains(by_label[intended], expected_tap), "scenario tap does not hit intended control")
    require(not contains(by_label[decoy], expected_tap), "scenario tap also hits decoy control")

    rejected = data.get("rejectedAttempt")
    require(isinstance(rejected, dict), "rejectedAttempt is required")
    rejected_tap = point(rejected.get("tap"), "rejected tap")
    require(contains(by_label[decoy], rejected_tap), "rejected tap must hit the decoy control")
    require(not contains(by_label[intended], rejected_tap), "rejected tap must not hit the intended control")
    require(rejected.get("observedPagePath") == "pages/DomStorage", "rejected attempt must retain the observed decoy page")
    require(rejected.get("runnerVerdict") == "passed", "rejected attempt must expose the misleading runner verdict")
    require(rejected.get("qualificationAccepted") is False, "rejected attempt must not qualify")
    digest(rejected.get("resultSha256"), "rejected result")
    digest(rejected.get("layoutBeforeSha256"), "rejected layout before")
    digest(rejected.get("layoutAfterSha256"), "rejected layout after")

    corrected = data.get("correctedBaselineAttempt")
    require(isinstance(corrected, dict), "correctedBaselineAttempt is required")
    authority = corrected.get("executionAuthority")
    require(isinstance(authority, dict), "corrected executionAuthority is required")
    require(authority.get("routeDecision") == "peer_direct", "corrected attempt must use peer_direct routing")
    require(isinstance(authority.get("targetPeerId"), str) and authority["targetPeerId"].startswith("lgw_"), "exact targetPeerId is required")
    require(isinstance(authority.get("operationId"), str) and authority["operationId"].startswith("exec-"), "operationId is required")
    require(isinstance(authority.get("traceIds"), list) and authority["traceIds"], "traceIds are required")
    result = corrected.get("result")
    require(isinstance(result, dict), "corrected result is required")
    require(result.get("schema") == "agentlab.harmony_emulator_case_result.v2", "corrected result must use v2")
    require(result.get("status") == "failed" and result.get("oracleStatus") == "failed", "corrected baseline must fail the Oracle")
    require(result.get("assessmentStatus") == "assessed", "corrected baseline must be assessed")
    require(result.get("infrastructureAvailable") is True, "corrected baseline infrastructure must be available")
    require(result.get("subjectTaskSucceeded") is False, "corrected baseline task must fail")
    require(result.get("failureClass") == "oracle", "corrected baseline failure must be an Oracle failure")
    require(result.get("hapSha256") == hap_sha, "corrected result HAP differs")
    require(result.get("scenarioSha256") == scenario_sha, "corrected result scenario differs")
    digest(corrected.get("resultSha256"), "corrected result receipt")
    before = digest(corrected.get("layoutBeforeSha256"), "corrected layout before")
    after = digest(corrected.get("layoutAfterSha256"), "corrected layout after")
    require(before == after, "corrected baseline must retain the same Index layout after the tap")

    scope = data.get("qualificationScope")
    require(isinstance(scope, dict), "qualificationScope is required")
    require(scope.get("coordinateCalibration") is True, "coordinate calibration must be qualified")
    require(scope.get("candidateFailToPass") is True, "candidate FAIL_TO_PASS must be observed")
    for field in ("businessUiOracle", "independentReview", "referenceRepair", "performanceComparison"):
        require(scope.get(field) is False, f"{field} must remain unqualified")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("calibration", type=Path)
    args = parser.parse_args()
    try:
        value = validate(json.loads(args.calibration.read_text(encoding="utf-8")), args.calibration.parent)
    except (OSError, json.JSONDecodeError, CalibrationError) as error:
        print(f"Harmony UI Oracle calibration invalid: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "status": value["status"], "scenarioId": value["scenario"]["id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
