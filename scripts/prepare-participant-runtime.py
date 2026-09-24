#!/usr/bin/env python3
"""Freeze the operator-owned configuration for a Docker-isolated Pi runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
FORBIDDEN_ENVIRONMENT_NAMES = {
    "AGENTLAB_LM_GATEWAY_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--pi-runtime", type=Path, required=True)
    parser.add_argument("--case-input", type=Path, required=True)
    parser.add_argument("--forbid", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require(not args.output.exists(), "refusing to overwrite participant runtime config")
    runtime = args.pi_runtime.resolve(strict=True)
    case_input = args.case_input.resolve(strict=True)
    require(runtime.is_dir(), "Pi runtime must be a directory")
    require(case_input.is_dir(), "participant case input must be a directory")
    lock = runtime / "package-lock.json"
    pi = runtime / "node_modules/.bin/pi"
    manifest = case_input / "manifest.json"
    require(lock.is_file(), "Pi runtime package-lock.json is absent")
    require(pi.is_file(), "Pi executable is absent from runtime")
    require(manifest.is_file(), "participant manifest is absent")
    participant_manifest = json.loads(manifest.read_text())
    require(
        participant_manifest.get("schema") == "agentlab.blind_case_participant_bundle.v1",
        "unsupported participant manifest",
    )
    inspected = subprocess.run(
        ["docker", "image", "inspect", args.image],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = json.loads(inspected.stdout)
    require(isinstance(rows, list) and len(rows) == 1, "Docker image identity is ambiguous")
    image_id = rows[0].get("Id")
    require(isinstance(image_id, str) and IMAGE_ID.fullmatch(image_id), "invalid Docker image ID")
    image_environment_names = sorted(
        item.split("=", 1)[0]
        for item in ((rows[0].get("Config") or {}).get("Env") or [])
        if "=" in item
    )
    require(
        not FORBIDDEN_ENVIRONMENT_NAMES.intersection(image_environment_names),
        "Docker image embeds an external credential environment name",
    )

    forbidden = []
    for path in args.forbid:
        resolved = path.resolve(strict=True)
        require(resolved != runtime and resolved != case_input, "visible roots cannot be forbidden")
        require(
            not runtime.is_relative_to(resolved) and not case_input.is_relative_to(resolved),
            "a forbidden root contains a participant-visible root",
        )
        forbidden.append(str(resolved))
    require(forbidden, "at least one operator-only path must be probed")
    require(len(set(forbidden)) == len(forbidden), "duplicate forbidden path")

    value = {
        "schema": "agentlab.participant_docker_runtime.v1",
        "executor": "docker",
        "imageReference": args.image,
        "imageId": image_id,
        "imageEnvironmentNames": image_environment_names,
        "piRuntimeRoot": str(runtime),
        "piPackageLockSha256": digest(lock),
        "caseInputRoot": str(case_input),
        "participantManifestSha256": digest(manifest),
        "forbiddenHostPaths": forbidden,
        "mountPolicy": {
            "workspace": "read-write",
            "participantCase": "read-only",
            "piRuntime": "read-only",
            "participantState": "read-write",
            "rootFilesystem": "read-only",
        },
        "processPolicy": {
            "pidNamespace": "private",
            "capabilities": "drop-all",
            "noNewPrivileges": True,
            "pidsLimit": 256,
        },
        "networkPolicy": "host-network-proxy-reachable-not-egress-isolated",
        "credentialPolicy": "external-operator-proxy-no-external-key-in-container",
        "automaticQualification": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"imageId": image_id, "participantManifestSha256": value["participantManifestSha256"]}, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
