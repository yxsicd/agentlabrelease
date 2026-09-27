#!/usr/bin/env python3
"""Validate one source-build-to-Linux-emulator qualification receipt."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")


class QualificationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise QualificationError(message)


def digest(value: object, label: str) -> str:
    text = str(value or "")
    require(SHA256.fullmatch(text) is not None, f"{label} must be a SHA-256 digest")
    return text


def validate(value: object) -> dict:
    require(isinstance(value, dict), "qualification must be a JSON object")
    data = value
    require(data.get("schema") == "agentlab.harmony_source_build_runtime_qualification.v1", "unsupported schema")
    require(data.get("status") == "baseline-build-runtime-qualified", "unsupported status")
    require(data.get("automaticPromotion") is False, "automaticPromotion must be false")

    source = data.get("source")
    require(isinstance(source, dict), "source is required")
    require(REVISION.fullmatch(str(source.get("revision", ""))) is not None, "source revision must be a full Git commit")
    require(isinstance(source.get("projectRoot"), str) and source["projectRoot"], "projectRoot is required")
    require(isinstance(source.get("buildModule"), str) and source["buildModule"], "buildModule is required")

    build = data.get("build")
    require(isinstance(build, dict), "build is required")
    require(build.get("status") == "successful", "build must be successful")
    require(build.get("cleanBuilds") == 2, "exactly two clean builds are required")
    attempts = build.get("attempts")
    require(isinstance(attempts, list) and len(attempts) == 2, "two build attempts are required")
    raw_digests = set()
    canonical_digests = set()
    member_counts = set()
    retained_logs = 0
    for index, attempt in enumerate(attempts):
        require(isinstance(attempt, dict), f"build.attempts[{index}] must be an object")
        raw_digests.add(digest(attempt.get("hapSha256"), f"build.attempts[{index}].hapSha256"))
        canonical_digests.add(digest(attempt.get("canonicalMemberSha256"), f"build.attempts[{index}].canonicalMemberSha256"))
        require(isinstance(attempt.get("hapBytes"), int) and attempt["hapBytes"] > 0, "HAP byte count must be positive")
        require(isinstance(attempt.get("memberCount"), int) and attempt["memberCount"] > 0, "memberCount must be positive")
        member_counts.add(attempt["memberCount"])
        if attempt.get("buildLogSha256") is not None:
            digest(attempt["buildLogSha256"], f"build.attempts[{index}].buildLogSha256")
            retained_logs += 1
    require(retained_logs >= 1, "at least one clean build log must be retained by digest")
    require(len(canonical_digests) == 1 and len(member_counts) == 1, "clean builds must have identical member content")
    require(build.get("memberContentReproducible") is True, "member content reproducibility must be explicit")
    require(build.get("rawArchiveReproducible") is (len(raw_digests) == 1), "raw archive reproducibility does not match HAP digests")

    runtime = data.get("linuxRuntime")
    require(isinstance(runtime, dict), "linuxRuntime is required")
    authority = runtime.get("executionAuthority")
    require(isinstance(authority, dict), "runtime executionAuthority is required")
    require(authority.get("routeDecision") == "peer_direct", "runtime evidence must use peer_direct routing")
    require(isinstance(authority.get("targetPeerId"), str) and authority["targetPeerId"].startswith("lgw_"), "exact runtime targetPeerId is required")
    require(isinstance(authority.get("operationId"), str) and authority["operationId"].startswith("exec-"), "runtime operationId is required")
    require(isinstance(authority.get("traceIds"), list) and authority["traceIds"], "runtime traceIds are required")
    result = runtime.get("result")
    require(isinstance(result, dict), "runtime result is required")
    require(result.get("schema") == "agentlab.harmony_emulator_case_result.v1", "unsupported runtime result schema")
    require(result.get("status") == "passed", "runtime smoke must pass")
    require(digest(result.get("hapSha256"), "runtime HAP") in raw_digests, "runtime HAP must be one of the clean-build artifacts")
    digest(result.get("resultSha256"), "runtime result receipt")
    digest(result.get("screenshotSha256"), "runtime screenshot")
    require(result.get("installSucceeded") is True, "install evidence is required")
    require(result.get("launchSucceeded") is True, "launch evidence is required")
    require(result.get("processAlive") is True, "live process evidence is required")

    scope = data.get("qualificationScope")
    require(isinstance(scope, dict), "qualificationScope is required")
    require(scope.get("baselineBuild") is True, "baseline build must be qualified")
    require(scope.get("linuxInstallLaunchProcess") is True, "Linux runtime smoke must be qualified")
    require(scope.get("businessUiOracle") is False, "v1 runtime smoke cannot qualify a business UI Oracle")
    require(scope.get("referenceRepair") is False, "baseline evidence cannot qualify a reference repair")
    require(scope.get("performanceComparison") is False, "single-run smoke cannot qualify performance comparison")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("qualification", type=Path)
    args = parser.parse_args()
    try:
        value = validate(json.loads(args.qualification.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, QualificationError) as error:
        print(f"source build/runtime qualification invalid: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "status": value["status"], "repositoryId": value["source"]["repositoryId"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
