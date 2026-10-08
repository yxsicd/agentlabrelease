#!/usr/bin/env python3
"""Freeze the operator-owned configuration for a Docker-isolated Pi runtime."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess


IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
ROOT = Path(__file__).resolve().parents[1]
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


def gateway_relay_digest():
    module_path = Path(__file__).with_name("run-pi-in-docker.py")
    spec = importlib.util.spec_from_file_location("agentlab_pi_docker_runtime", module_path)
    require(spec is not None and spec.loader is not None, "participant runtime launcher is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return hashlib.sha256(module.GATEWAY_RELAY.encode()).hexdigest()


def supervisor_profile(runtime: Path):
    """Bind the sole reviewed extension and its complete installed package tree."""
    profile = json.loads((ROOT / "examples/real-code-agent/participant/supervisor-profile.json").read_text())
    plugin = runtime / "node_modules" / profile["pluginPackage"]
    require(plugin.is_dir() and not plugin.is_symlink(), "delegate package is absent or unsafe")
    require(plugin.resolve().is_relative_to(runtime.resolve()), "delegate package escapes runtime")
    metadata = plugin / "package.json"
    require(metadata.is_file() and not metadata.is_symlink(), "delegate package metadata is unsafe")
    package = json.loads(metadata.read_text())
    require(package.get("name") == profile["pluginPackage"] and package.get("version") == profile["pluginVersion"],
            "delegate package identity differs")
    inventory = []
    for path in sorted(plugin.rglob("*")):
        require(not path.is_symlink(), "delegate package contains an unsafe link")
        require(path.is_dir() or path.is_file(), "delegate package contains an unsafe file type")
        if path.is_file():
            inventory.append({"path": path.relative_to(plugin).as_posix(), "sha256": digest(path)})
    require(0 < len(inventory) <= 5000, "delegate package inventory is invalid")
    profile["packageTreeSha256"] = hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    profile["extensionSha256"] = digest(runtime / profile["extensionRelativePath"])
    return profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--pi-runtime", type=Path, required=True)
    parser.add_argument("--case-input", type=Path, required=True)
    parser.add_argument("--forbid", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--supervisor", action="store_true", help="Explicitly allow the pinned Pi delegate supervisor profile")
    parser.add_argument("--synthetic-isolation-fixture", action="store_true", help="Diagnostic transport fixture only; never a qualified Pi participant")
    args = parser.parse_args()

    require(not args.output.exists(), "refusing to overwrite participant runtime config")
    require(os.getuid() != 0, "participant runtime must be prepared by a non-root operator")
    runtime = args.pi_runtime.resolve(strict=True)
    case_input = args.case_input.resolve(strict=True)
    require(runtime.is_dir(), "Pi runtime must be a directory")
    require(case_input.is_dir(), "participant case input must be a directory")
    lock = runtime / "package-lock.json"
    pi = runtime / "node_modules/.bin/pi"
    manifest = case_input / "manifest.json"
    require(lock.is_file(), "Pi runtime package-lock.json is absent")
    require(pi.is_file(), "Pi executable is absent from runtime")
    require(pi.resolve().is_relative_to(runtime), "Pi executable redirects outside runtime")
    require(not args.synthetic_isolation_fixture or not args.supervisor, "a synthetic fixture cannot be a delegate supervisor")
    version_digest = None
    if not args.synthetic_isolation_fixture:
        public_lock = ROOT / "examples/real-code-agent/participant/package-lock.json"
        require(digest(lock) == digest(public_lock), "Pi runtime does not use the exact public lock")
        locked_pi = json.loads(lock.read_text())["packages"]["node_modules/@earendil-works/pi-coding-agent"]
        require(locked_pi.get("version") == "1.1.0", "Pi runtime version differs")
        version_probe = subprocess.run([str(pi), "--no-extensions", "--no-skills", "--no-context-files", "--no-mcp", "--offline", "--version"],
                                      capture_output=True, timeout=30,
                                      env={key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR") if key in os.environ})
        require(version_probe.returncode == 0 and b"1.1.0" in (version_probe.stdout + version_probe.stderr).splitlines(),
                "actual Pi version preflight failed")
        version_digest = hashlib.sha256(version_probe.stdout + b"\0" + version_probe.stderr).hexdigest()
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
        "runtimeUser": f"{os.getuid()}:{os.getgid()}",
        "imageEnvironmentNames": image_environment_names,
        "piRuntimeRoot": str(runtime),
        "piPackageLockSha256": digest(lock),
        "piPackageName": None if args.synthetic_isolation_fixture else "@earendil-works/pi-coding-agent",
        "piPackageVersion": None if args.synthetic_isolation_fixture else "1.1.0",
        "piVersionProbeSha256": version_digest,
        "runtimePurpose": "synthetic-transport-only" if args.synthetic_isolation_fixture else "delegate-supervisor" if args.supervisor else "assessed-participant",
        "caseInputRoot": str(case_input),
        "participantManifestSha256": digest(manifest),
        "gatewayRelayProgramSha256": gateway_relay_digest(),
        "forbiddenHostPaths": forbidden,
        "mountPolicy": {
            "workspace": "read-write",
            "participantCase": "read-only",
            "piRuntime": "read-only",
            "participantState": "read-write",
            "operatorGatewayRelay": "separate-no-credential-container",
            "rootFilesystem": "read-only",
        },
        "processPolicy": {
            "pidNamespace": "private",
            "capabilities": "drop-all",
            "noNewPrivileges": True,
            "pidsLimit": 256,
        },
        "networkPolicy": "internal-bridge-with-operator-relay",
        "credentialPolicy": "external-operator-proxy-no-external-key-in-container",
        "automaticQualification": False,
    }
    if args.supervisor:
        value["piSupervisor"] = supervisor_profile(runtime)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"imageId": image_id, "participantManifestSha256": value["participantManifestSha256"]}, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
