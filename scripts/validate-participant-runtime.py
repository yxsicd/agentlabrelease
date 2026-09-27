#!/usr/bin/env python3
"""Independently validate Docker participant runtime receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    value = json.loads(path.read_text())
    require(isinstance(value, dict), f"{path} must contain an object")
    return value


def validate_runtime_receipts(
    config_path: Path,
    receipt_root: Path,
    workspace: Path,
    participant_state: Path,
    labels: list[str],
):
    config_path = config_path.resolve(strict=True)
    receipt_root = receipt_root.resolve(strict=True)
    workspace = workspace.resolve(strict=True)
    participant_state = participant_state.resolve(strict=True)
    config = load(config_path)
    require(config.get("schema") == "agentlab.participant_docker_runtime.v1", "unsupported runtime config")
    require(config.get("executor") == "docker", "runtime executor differs")
    require(config.get("automaticQualification") is False, "runtime config must not self-qualify")
    require(
        config.get("networkPolicy") == "internal-bridge-with-operator-relay",
        "runtime network policy differs",
    )
    require(
        config.get("credentialPolicy")
        == "external-operator-proxy-no-external-key-in-container",
        "runtime credential policy differs",
    )
    require(labels and len(labels) == len(set(labels)), "runtime labels must be unique")
    expected_user = config.get("runtimeUser")
    require(
        isinstance(expected_user, str)
        and expected_user.count(":") == 1
        and expected_user.split(":", 1)[0] not in {"", "0"},
        "qualified participant runtime requires a non-root user",
    )
    expected_mounts = [
        {"type": "bind", "source": str(participant_state), "destination": "/agent", "rw": True},
        {"type": "bind", "source": str(Path(config["caseInputRoot"]).resolve(strict=True)), "destination": "/agentlab/case", "rw": False},
        {"type": "bind", "source": str(Path(config["piRuntimeRoot"]).resolve(strict=True)), "destination": "/runtime", "rw": False},
        {"type": "bind", "source": str(workspace), "destination": "/workspace", "rw": True},
    ]
    expected_mounts.sort(key=lambda row: row["destination"])
    expected_forbidden = sorted(
        hashlib.sha256(value.encode()).hexdigest()
        for value in config.get("forbiddenHostPaths", [])
    )
    require(expected_forbidden, "runtime config has no forbidden-path probes")
    validated = []
    for label in labels:
        receipt_path = receipt_root / f"{label}.json"
        inspect_path = receipt_root / f"{label}.container-inspect.json"
        final_path = receipt_root / f"{label}.container-final.json"
        relay_inspect_path = receipt_root / f"{label}.relay-inspect.json"
        network_inspect_path = receipt_root / f"{label}.network-inspect.json"
        receipt = load(receipt_path)
        require(receipt.get("schema") == "agentlab.participant_runtime_isolation_receipt.v1", f"{label}: receipt schema differs")
        require(receipt.get("label") == label, f"{label}: receipt label differs")
        require(receipt.get("status") == "completed", f"{label}: runtime did not complete")
        require(receipt.get("exitCode") == 0 and receipt.get("containerStateExitCode") == 0, f"{label}: container failed")
        require(receipt.get("executor") == "docker", f"{label}: executor differs")
        require(receipt.get("runtimeConfigSha256") == digest(config_path), f"{label}: runtime config digest differs")
        require(receipt.get("participantManifestSha256") == config.get("participantManifestSha256"), f"{label}: participant manifest differs")
        require(receipt.get("imageId") == config.get("imageId"), f"{label}: image identity differs")
        require(receipt.get("externalCredentialInjected") is False, f"{label}: external credential reached container")
        require(isinstance(receipt.get("operatorGatewayPort"), int), f"{label}: operator Gateway port is absent")
        require(receipt.get("filesystemIsolationQualified") is False, f"{label}: runtime self-qualified isolation")
        require(receipt.get("networkEgressIsolationQualified") is False, f"{label}: network isolation was overclaimed")
        require(inspect_path.is_file() and digest(inspect_path) == receipt.get("containerInspectSha256"), f"{label}: inspect evidence differs")
        require(final_path.is_file() and digest(final_path) == receipt.get("containerFinalSha256"), f"{label}: final evidence differs")
        require(relay_inspect_path.is_file() and digest(relay_inspect_path) == receipt.get("relayInspectSha256"), f"{label}: relay inspect evidence differs")
        require(network_inspect_path.is_file() and digest(network_inspect_path) == receipt.get("networkInspectSha256"), f"{label}: network inspect evidence differs")
        raw = json.loads(inspect_path.read_text())
        require(isinstance(raw, list) and len(raw) == 1, f"{label}: inspect evidence is malformed")
        row = raw[0]
        host = row.get("HostConfig") or {}
        container_config = row.get("Config") or {}
        mounts = sorted(
            [
                {"type": item.get("Type"), "source": item.get("Source"), "destination": item.get("Destination"), "rw": item.get("RW")}
                for item in row.get("Mounts", [])
            ],
            key=lambda item: item["destination"] or "",
        )
        require(mounts == expected_mounts, f"{label}: container mounts differ from least-mount policy")
        require(row.get("Image") == config.get("imageId"), f"{label}: inspected image differs")
        require(host.get("ReadonlyRootfs") is True, f"{label}: root filesystem is writable")
        require(sorted(host.get("CapDrop") or []) == ["ALL"], f"{label}: capabilities were not dropped")
        require("no-new-privileges" in (host.get("SecurityOpt") or []), f"{label}: no-new-privileges is absent")
        require(host.get("PidsLimit") == 256, f"{label}: PID limit differs")
        require(host.get("PidMode") in ("", None), f"{label}: host PID namespace is visible")
        require(host.get("Privileged") is False, f"{label}: privileged mode is enabled")
        network_raw = json.loads(network_inspect_path.read_text())
        require(isinstance(network_raw, list) and len(network_raw) == 1, f"{label}: network evidence is malformed")
        network = network_raw[0]
        network_name = network.get("Name")
        require(network.get("Id") == receipt.get("internalNetworkId"), f"{label}: internal network identity differs")
        require(network.get("Internal") is True and network.get("Driver") == "bridge", f"{label}: network is not an internal bridge")
        require(
            network.get("Attachable") is False
            and network.get("Ingress") is False
            and network.get("Scope") == "local",
            f"{label}: internal network control flags differ",
        )
        require(network.get("EnableIPv6") is False, f"{label}: IPv6 egress is enabled")
        require(host.get("NetworkMode") == network_name, f"{label}: participant is not attached to the internal network")
        require(host.get("PortBindings") in ({}, None), f"{label}: participant publishes a host port")
        participant_networks = (row.get("NetworkSettings") or {}).get("Networks") or {}
        require(set(participant_networks) == {network_name}, f"{label}: participant has an additional network")
        require((host.get("Tmpfs") or {}).get("/tmp") == "rw,nosuid,nodev,noexec,size=268435456,mode=1777", f"{label}: private tmpfs differs")
        require(container_config.get("Entrypoint") == ["/runtime/node_modules/.bin/pi"], f"{label}: Pi entrypoint differs")
        require(container_config.get("User") == expected_user, f"{label}: participant user differs")
        environment_names = sorted(item.split("=", 1)[0] for item in container_config.get("Env", []) if "=" in item)
        expected_environment_names = sorted(
            set(config.get("imageEnvironmentNames", []))
            | {"HOME", "PATH", "PI_CODING_AGENT_DIR"}
        )
        require(environment_names == expected_environment_names, f"{label}: container environment surface differs")
        probes = receipt.get("probes") or {}
        require(probes.get("caseInputReadable") is True, f"{label}: participant case was not readable")
        require(probes.get("piRuntimeReadable") is True, f"{label}: Pi runtime was not readable")
        require(probes.get("workspaceWritable") is True, f"{label}: workspace was not writable")
        require(probes.get("dockerSocketVisible") is False, f"{label}: Docker socket was visible")
        require(probes.get("operatorGatewayRelayReachable") is True, f"{label}: operator Gateway relay was unavailable")
        require(probes.get("operatorGatewayLocalAuthQualified") is True, f"{label}: operator Gateway local authentication was not proved")
        require(probes.get("externalNetworkConnectBlocked") is True, f"{label}: external network connection was not blocked")
        require(probes.get("externalCredentialNamesVisibleInPidOne") is False, f"{label}: external credential name was visible")
        actual_forbidden = sorted(row.get("pathSha256") for row in probes.get("forbiddenPaths", []) if row.get("visibleAtHostAbsolutePath") is False)
        require(actual_forbidden == expected_forbidden, f"{label}: forbidden path probes differ")
        relay_raw = json.loads(relay_inspect_path.read_text())
        require(isinstance(relay_raw, list) and len(relay_raw) == 1, f"{label}: relay evidence is malformed")
        relay = relay_raw[0]
        relay_host = relay.get("HostConfig") or {}
        relay_config = relay.get("Config") or {}
        require(relay.get("Id") == receipt.get("relayContainerId"), f"{label}: relay identity differs")
        require(relay.get("Image") == config.get("imageId"), f"{label}: relay image differs")
        require(not relay.get("Mounts"), f"{label}: relay has filesystem mounts")
        require(relay_host.get("ReadonlyRootfs") is True, f"{label}: relay root filesystem is writable")
        require(sorted(relay_host.get("CapDrop") or []) == ["ALL"], f"{label}: relay capabilities were not dropped")
        require("no-new-privileges" in (relay_host.get("SecurityOpt") or []), f"{label}: relay no-new-privileges is absent")
        require(relay_host.get("PidsLimit") == 64, f"{label}: relay PID limit differs")
        require(relay_host.get("PidMode") in ("", None), f"{label}: relay sees the host PID namespace")
        require(relay_host.get("Privileged") is False, f"{label}: relay is privileged")
        require(relay_config.get("Entrypoint") == ["/usr/local/bin/node"], f"{label}: relay entrypoint differs")
        require(relay_config.get("User") == expected_user, f"{label}: relay user differs")
        relay_command = relay_config.get("Cmd") or []
        require(len(relay_command) == 2 and relay_command[0] == "-e", f"{label}: relay command differs")
        require(hashlib.sha256(relay_command[1].encode()).hexdigest() == config.get("gatewayRelayProgramSha256"), f"{label}: relay program identity differs")
        relay_environment = dict(
            item.split("=", 1) for item in relay_config.get("Env", []) if "=" in item
        )
        require(relay_environment.get("AGENTLAB_RELAY_TARGET_HOST") == "host.docker.internal", f"{label}: relay target host differs")
        require(relay_environment.get("AGENTLAB_RELAY_TARGET_PORT") == str(receipt.get("operatorGatewayPort")), f"{label}: relay target port differs")
        expected_relay_environment = set(config.get("imageEnvironmentNames", [])) | {
            "AGENTLAB_RELAY_TARGET_HOST",
            "AGENTLAB_RELAY_TARGET_PORT",
        }
        require(
            set(relay_environment) == expected_relay_environment,
            f"{label}: relay environment surface differs",
        )
        require(
            relay_host.get("NetworkMode") == network_name,
            f"{label}: relay primary network differs",
        )
        require(
            relay_host.get("PortBindings") in ({}, None),
            f"{label}: relay publishes a host port",
        )
        relay_networks = (relay.get("NetworkSettings") or {}).get("Networks") or {}
        require(set(relay_networks) == {network_name, "bridge"}, f"{label}: relay network attachments differ")
        network_members = set((network.get("Containers") or {}).keys())
        require(
            network_members == {receipt.get("relayContainerId")},
            f"{label}: pre-start internal network membership differs",
        )
        final = json.loads(final_path.read_text())[0]
        final_state = final.get("State") or {}
        require(final_state.get("ExitCode") == 0 and final_state.get("Status") == "exited", f"{label}: final container state differs")
        validated.append({"label": label, "containerId": receipt.get("containerId"), "receiptSha256": digest(receipt_path)})
    return {
        "schema": "agentlab.participant_runtime_isolation_validation.v1",
        "executor": "docker",
        "imageId": config["imageId"],
        "participantManifestSha256": config["participantManifestSha256"],
        "filesystemIsolationQualified": True,
        "externalCredentialIsolationQualified": True,
        "networkEgressIsolationQualified": True,
        "validatedTurns": validated,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--participant-state", type=Path, required=True)
    parser.add_argument("--label", action="append", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_runtime_receipts(
        args.config,
        args.receipt_root,
        args.workspace,
        args.participant_state,
        args.label,
    )
    body = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        require(not args.output.exists(), "refusing to overwrite runtime validation")
        args.output.write_text(body)
    print(body, end="")


if __name__ == "__main__":
    raise SystemExit(main())
