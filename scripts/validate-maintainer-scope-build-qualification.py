#!/usr/bin/env python3
"""Validate one exact-revision Maintainer Skill build-only qualification receipt."""
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
    require(
        data.get("schema") == "agentlab.maintainer_scope_build_qualification.v1",
        "unsupported schema",
    )
    require(data.get("status") == "qualified", "qualification status must be qualified")
    require(data.get("automaticPromotion") is False, "automaticPromotion must be false")

    source = data.get("source")
    require(isinstance(source, dict), "source is required")
    require(isinstance(source.get("repositoryId"), str) and source["repositoryId"], "repositoryId is required")
    require(REVISION.fullmatch(str(source.get("revision", ""))) is not None, "source revision must be a full Git commit")
    require(source.get("cleanBefore") is True, "source must be clean before qualification")
    require(source.get("cleanAfter") is True, "source must remain clean after qualification")

    scope = data.get("scope")
    require(isinstance(scope, dict), "scope is required")
    skill_ids = scope.get("scopeSkillIds")
    require(isinstance(skill_ids, list) and len(skill_ids) == 1, "exactly one scopeSkillId is required")
    require(isinstance(skill_ids[0], str) and skill_ids[0], "scopeSkillId is invalid")
    require(scope.get("lane") == "build-only", "qualification lane must be build-only")
    require(isinstance(scope.get("module"), str) and scope["module"], "module is required")
    require(isinstance(scope.get("target"), str) and scope["target"], "target is required")
    require(scope.get("scopeSpecificBinding") is True, "scope-specific binding must be explicit")

    toolchain = data.get("toolchain")
    require(isinstance(toolchain, dict), "toolchain is required")
    require(isinstance(toolchain.get("sdkRelease"), str) and toolchain["sdkRelease"], "sdkRelease is required")
    require(isinstance(toolchain.get("hvigorVersion"), str) and toolchain["hvigorVersion"], "hvigorVersion is required")
    require(isinstance(toolchain.get("ohpmVersion"), str) and toolchain["ohpmVersion"], "ohpmVersion is required")

    dependencies = data.get("dependencyPreparation")
    require(isinstance(dependencies, dict), "dependencyPreparation is required")
    require(dependencies.get("status") == "successful", "dependency preparation must succeed")
    require(dependencies.get("exitCode") == 0, "dependency preparation exitCode must be zero")
    require(isinstance(dependencies.get("durationMs"), int) and dependencies["durationMs"] > 0, "dependency duration must be positive")
    digest(dependencies.get("lockSha256"), "dependency lock")

    build = data.get("build")
    require(isinstance(build, dict), "build is required")
    require(build.get("status") == "successful", "build must be successful")
    require(build.get("task") == "assembleHar", "build-only v1 requires assembleHar")
    attempts = build.get("attempts")
    require(isinstance(attempts, list) and len(attempts) == 2, "exactly two clean build attempts are required")
    canonical = set()
    member_counts = set()
    raw = set()
    for index, attempt in enumerate(attempts):
        require(isinstance(attempt, dict), f"build.attempts[{index}] must be an object")
        require(attempt.get("cleanBuild") is True, "every attempt must be a clean build")
        require(attempt.get("exitCode") == 0, "every build attempt must exit zero")
        require(isinstance(attempt.get("durationMs"), int) and attempt["durationMs"] > 0, "build duration must be positive")
        require(isinstance(attempt.get("artifactBytes"), int) and attempt["artifactBytes"] > 0, "artifact size must be positive")
        raw.add(digest(attempt.get("artifactSha256"), f"build.attempts[{index}].artifactSha256"))
        canonical.add(digest(attempt.get("canonicalMemberSha256"), f"build.attempts[{index}].canonicalMemberSha256"))
        member_counts.add(attempt.get("memberCount"))
        digest(attempt.get("buildLogSha256"), f"build.attempts[{index}].buildLogSha256")
        authority = attempt.get("executionAuthority")
        require(isinstance(authority, dict), "executionAuthority is required")
        require(authority.get("routeDecision") == "peer_direct", "build evidence must use peer_direct routing")
        require(isinstance(authority.get("targetPeerId"), str) and authority["targetPeerId"].startswith("lgw_"), "targetPeerId is required")
        require(isinstance(authority.get("operationId"), str) and authority["operationId"].startswith("exec-"), "operationId is required")
    require(len(canonical) == 1, "clean builds must have identical canonical member content")
    require(len(member_counts) == 1 and next(iter(member_counts)) > 0, "clean builds must have identical positive member counts")
    require(build.get("canonicalContentReproducible") is True, "canonical content reproducibility must be explicit")
    require(build.get("rawArchiveReproducible") is (len(raw) == 1), "raw archive reproducibility flag is inconsistent")

    limits = data.get("qualificationScope")
    require(isinstance(limits, dict), "qualificationScope is required")
    require(limits.get("moduleBuild") is True, "module build must be qualified")
    require(limits.get("runtime") is False, "build-only qualification cannot claim runtime")
    require(limits.get("tests") is False, "build-only qualification cannot claim tests")
    require(limits.get("performance") is False, "build-only qualification cannot claim performance")

    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("qualification", type=Path)
    args = parser.parse_args()
    try:
        value = validate(json.loads(args.qualification.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, QualificationError) as error:
        print(f"maintainer scope build qualification invalid: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "ok": True,
        "repositoryId": value["source"]["repositoryId"],
        "scopeSkillIds": value["scope"]["scopeSkillIds"],
        "status": value["status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
