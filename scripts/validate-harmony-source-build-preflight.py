#!/usr/bin/env python3
"""Validate a source-build preflight without confusing it with a build receipt."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_STATUS = {"build-ready", "blocked-missing-toolchain"}


class PreflightError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PreflightError(message)


def validate(value: object) -> dict:
    require(isinstance(value, dict), "preflight must be a JSON object")
    data = value
    require(data.get("schema") == "agentlab.harmony_source_build_preflight.v1", "unsupported schema")
    require(data.get("status") in ALLOWED_STATUS, "unsupported status")
    require(data.get("automaticPromotion") is False, "automaticPromotion must be false")

    authority = data.get("executionAuthority")
    require(isinstance(authority, dict), "executionAuthority is required")
    require(authority.get("routeDecision") == "peer_direct", "remote evidence must use peer_direct routing")
    require(isinstance(authority.get("targetPeerId"), str) and authority["targetPeerId"].startswith("lgw_"), "exact targetPeerId is required")
    require(isinstance(authority.get("traceIds"), list) and authority["traceIds"], "at least one traceId is required")

    tools = data.get("toolchain")
    require(isinstance(tools, list) and tools, "toolchain probes are required")
    missing = []
    names = set()
    for index, tool in enumerate(tools):
        require(isinstance(tool, dict), f"toolchain[{index}] must be an object")
        name = tool.get("name")
        require(isinstance(name, str) and name, f"toolchain[{index}].name is required")
        require(name not in names, f"duplicate toolchain probe: {name}")
        names.add(name)
        require(isinstance(tool.get("required"), bool), f"toolchain[{index}].required must be boolean")
        require(isinstance(tool.get("available"), bool), f"toolchain[{index}].available must be boolean")
        if tool["required"] and not tool["available"]:
            missing.append(name)

    projects = data.get("projects")
    require(isinstance(projects, list) and projects, "at least one source project is required")
    project_ids = set()
    for index, project in enumerate(projects):
        require(isinstance(project, dict), f"projects[{index}] must be an object")
        project_id = project.get("repositoryId")
        require(isinstance(project_id, str) and project_id, f"projects[{index}].repositoryId is required")
        require(project_id not in project_ids, f"duplicate repositoryId: {project_id}")
        project_ids.add(project_id)
        require(REVISION.fullmatch(str(project.get("revision", ""))) is not None, f"projects[{index}].revision must be a full Git commit")
        require(isinstance(project.get("projectRoot"), str) and project["projectRoot"], f"projects[{index}].projectRoot is required")
        require(isinstance(project.get("buildModule"), str) and project["buildModule"], f"projects[{index}].buildModule is required")
        bindings = project.get("sourceBindings")
        require(isinstance(bindings, list) and bindings, f"projects[{index}].sourceBindings are required")
        for binding_index, binding in enumerate(bindings):
            require(isinstance(binding, dict), f"projects[{index}].sourceBindings[{binding_index}] must be an object")
            require(isinstance(binding.get("path"), str) and binding["path"], "source binding path is required")
            require(SHA256.fullmatch(str(binding.get("sha256", ""))) is not None, "source binding SHA256 is invalid")

    if data["status"] == "build-ready":
        require(not missing, "build-ready cannot have missing required tools")
    else:
        require(bool(missing), "blocked-missing-toolchain requires a missing required tool")
    require(data.get("qualified") is (data["status"] == "build-ready"), "qualified must match status")
    require(data.get("buildReceipt") is None, "preflight must not claim a build receipt")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("preflight", type=Path)
    args = parser.parse_args()
    try:
        value = validate(json.loads(args.preflight.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, PreflightError) as error:
        print(f"source build preflight invalid: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "status": value["status"], "qualified": value["qualified"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
