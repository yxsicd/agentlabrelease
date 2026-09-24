#!/usr/bin/env python3
"""Launch one Pi turn in a least-mounted container and retain operator receipts."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
import uuid


SHA256 = re.compile(r"[0-9a-f]{64}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
LABEL = re.compile(r"[A-Za-z0-9_.-]{1,96}")
SECRET_NAMES = {
    "AGENTLAB_LM_GATEWAY_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
}
CONTAINER_GATEWAY_PORT = 18765
GATEWAY_RELAY = r"""
const net = require('node:net');
const targetHost = process.env.AGENTLAB_RELAY_TARGET_HOST;
const targetPort = Number(process.env.AGENTLAB_RELAY_TARGET_PORT);
const server = net.createServer(client => {
  const upstream = net.createConnection({host: targetHost, port: targetPort});
  client.pipe(upstream);
  upstream.pipe(client);
  const close = () => { client.destroy(); upstream.destroy(); };
  client.on('error', close);
  upstream.on('error', close);
});
server.listen(%d, '0.0.0.0');
server.on('error', error => { console.error(error); process.exit(125); });
""" % CONTAINER_GATEWAY_PORT


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest_bytes(value: bytes):
    return hashlib.sha256(value).hexdigest()


def digest(path: Path):
    return digest_bytes(path.read_bytes())


def load_config(path: Path):
    require(path.is_file() and not path.is_symlink(), "runtime config must be a regular non-symlink file")
    value = json.loads(path.read_text())
    require(value.get("schema") == "agentlab.participant_docker_runtime.v1", "unsupported runtime config")
    require(value.get("executor") == "docker", "runtime executor must be Docker")
    require(IMAGE_ID.fullmatch(value.get("imageId", "")), "runtime image ID is invalid")
    require(value.get("networkPolicy") == "internal-bridge-with-operator-relay", "runtime network policy differs")
    require(value.get("credentialPolicy") == "external-operator-proxy-no-external-key-in-container", "runtime credential policy differs")
    require(
        value.get("runtimeUser") == f"{os.getuid()}:{os.getgid()}" and os.getuid() != 0,
        "runtime user differs from the non-root operator",
    )
    require(
        value.get("gatewayRelayProgramSha256") == digest_bytes(GATEWAY_RELAY.encode()),
        "runtime Gateway relay program differs",
    )
    return value


def mount(source: Path, destination: str, readonly=False):
    option = f"type=bind,src={source},dst={destination}"
    if readonly:
        option += ",readonly"
    return ["--mount", option]


def docker_base(config, workspace: Path, state: Path, network_name: str):
    runtime = Path(config["piRuntimeRoot"]).resolve(strict=True)
    case_input = Path(config["caseInputRoot"]).resolve(strict=True)
    require(digest(runtime / "package-lock.json") == config["piPackageLockSha256"], "Pi runtime lock digest drifted")
    require(digest(case_input / "manifest.json") == config["participantManifestSha256"], "participant manifest digest drifted")
    require(workspace.is_dir() and state.is_dir(), "workspace and participant state must exist")
    return [
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=256",
        f"--network={network_name}",
        "--user", config["runtimeUser"],
        "--workdir", "/workspace",
        "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=268435456,mode=1777",
        *mount(workspace, "/workspace"),
        *mount(runtime, "/runtime", readonly=True),
        *mount(case_input, "/agentlab/case", readonly=True),
        *mount(state, "/agent"),
        "--env", "HOME=/agent",
        "--env", "PI_CODING_AGENT_DIR=/agent",
        "--env", "PATH=/runtime/node_modules/.bin:/usr/local/bin:/usr/bin:/bin",
        config["imageId"],
    ]


def run_probe(base, config, workspace: Path):
    sentinel = f".agentlab-write-probe-{uuid.uuid4().hex}"
    forbidden = config["forbiddenHostPaths"]
    script = r'''
set -eux
test -r /agentlab/case/manifest.json
test -x /runtime/node_modules/.bin/pi
node -e "const n=require('node:net').createConnection({host:'agentlab-gateway',port:18765});n.setTimeout(5000);n.on('connect',()=>{n.end();process.exit(0)});n.on('timeout',()=>process.exit(72));n.on('error',()=>process.exit(73))"
node -e "const fs=require('node:fs'),http=require('node:http');const m=JSON.parse(fs.readFileSync('/agent/models.json'));const k=m.providers['agentlab-ci'].apiKey;const q=http.get({host:'agentlab-gateway',port:18765,path:'/__agentlab_runtime_probe',headers:{Authorization:'Bearer '+k}},r=>process.exit(r.statusCode===204?0:75));q.setTimeout(5000,()=>process.exit(76));q.on('error',()=>process.exit(77))"
node -e "const n=require('node:net').createConnection({host:'1.1.1.1',port:443});n.setTimeout(2000);n.on('connect',()=>process.exit(74));n.on('timeout',()=>process.exit(0));n.on('error',()=>process.exit(0))"
test -w /workspace
touch "/workspace/$1"
rm "/workspace/$1"
test ! -e /var/run/docker.sock
if tr '\0' '\n' </proc/1/environ | grep -Eq '^(AGENTLAB_LM_GATEWAY_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY)='; then
  exit 71
fi
shift
for forbidden_path in "$@"; do
  test ! -e "$forbidden_path"
done
'''
    completed = subprocess.run(
        ["docker", "run", "--rm", *base[:-1], "--entrypoint", "/bin/sh", base[-1], "-c", script, "probe", sentinel, *forbidden],
        capture_output=True,
        text=True,
    )
    require(
        completed.returncode == 0,
        f"container isolation probe failed ({completed.returncode}): "
        f"stdout={completed.stdout.strip()} stderr={completed.stderr.strip()}",
    )
    require(not (workspace / sentinel).exists(), "workspace probe sentinel was not cleaned")
    return {
        "caseInputReadable": True,
        "piRuntimeReadable": True,
        "workspaceWritable": True,
        "dockerSocketVisible": False,
        "operatorGatewayRelayReachable": True,
        "operatorGatewayLocalAuthQualified": True,
        "externalNetworkConnectBlocked": True,
        "externalCredentialNamesVisibleInPidOne": False,
        "forbiddenPaths": [
            {"pathSha256": digest_bytes(value.encode()), "visibleAtHostAbsolutePath": False}
            for value in forbidden
        ],
    }


def inspect_projection(raw):
    require(isinstance(raw, list) and len(raw) == 1, "container inspect must contain one row")
    row = raw[0]
    host = row.get("HostConfig") or {}
    config = row.get("Config") or {}
    mounts = sorted(
        [
            {
                "type": item.get("Type"),
                "source": item.get("Source"),
                "destination": item.get("Destination"),
                "rw": item.get("RW"),
            }
            for item in row.get("Mounts", [])
        ],
        key=lambda item: item["destination"] or "",
    )
    environment_names = sorted(
        item.split("=", 1)[0] for item in config.get("Env", []) if "=" in item
    )
    return {
        "imageId": row.get("Image"),
        "mounts": mounts,
        "readOnlyRootfs": host.get("ReadonlyRootfs"),
        "capDrop": sorted(host.get("CapDrop") or []),
        "securityOpt": sorted(host.get("SecurityOpt") or []),
        "pidsLimit": host.get("PidsLimit"),
        "pidMode": host.get("PidMode"),
        "privileged": host.get("Privileged"),
        "networkMode": host.get("NetworkMode"),
        "user": config.get("User"),
        "environmentNames": environment_names,
        "secretEnvironmentNames": sorted(SECRET_NAMES.intersection(environment_names)),
    }


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main():
    config_path = Path(os.environ["AGENTLAB_PARTICIPANT_RUNTIME_CONFIG"]).resolve(strict=True)
    receipt_root = Path(os.environ["AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT"]).resolve(strict=True)
    label = os.environ["AGENTLAB_PARTICIPANT_RUNTIME_LABEL"]
    require(LABEL.fullmatch(label), "unsafe runtime receipt label")
    config = load_config(config_path)
    workspace = Path.cwd().resolve(strict=True)
    state = Path(os.environ["PI_CODING_AGENT_DIR"]).resolve(strict=True)
    gateway_port = int(os.environ["AGENTLAB_OPERATOR_GATEWAY_PORT"])
    require(1 <= gateway_port <= 65535, "operator Gateway port is invalid")
    receipt_path = receipt_root / f"{label}.json"
    inspect_path = receipt_root / f"{label}.container-inspect.json"
    require(receipt_root.is_dir() and not receipt_path.exists() and not inspect_path.exists(), "runtime receipt already exists")
    require(state != workspace and not state.is_relative_to(workspace), "participant state must be outside workspace")

    arguments = list(sys.argv[1:])
    require("--session" in arguments, "Pi session argument is required")
    session_index = arguments.index("--session") + 1
    original_session = Path(arguments[session_index]).resolve()
    require(original_session.is_relative_to(state), "Pi session must stay in participant state")
    arguments[session_index] = "/agent/" + original_session.relative_to(state).as_posix()
    runtime_id = uuid.uuid4().hex[:12]
    network_name = f"agentlab-net-{runtime_id}"
    relay_name = f"agentlab-relay-{runtime_id}"
    base = docker_base(config, workspace, state, network_name)
    started = time.monotonic()
    receipt = {
        "schema": "agentlab.participant_runtime_isolation_receipt.v1",
        "label": label,
        "status": "starting",
        "executor": "docker",
        "runtimeConfigSha256": digest(config_path),
        "participantManifestSha256": config["participantManifestSha256"],
        "imageId": config["imageId"],
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "externalCredentialInjected": False,
        "operatorGatewayPort": gateway_port,
        "filesystemIsolationQualified": False,
        "networkEgressIsolationQualified": False,
    }
    container_id = None
    relay_id = None
    network_id = None
    start_process = None

    def cleanup(*_unused):
        if container_id:
            subprocess.run(["docker", "kill", container_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["docker", "rm", "-f", container_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if relay_id:
            subprocess.run(["docker", "kill", relay_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["docker", "rm", "-f", relay_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if network_id:
            subprocess.run(["docker", "network", "rm", network_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    previous_term = signal.signal(signal.SIGTERM, cleanup)
    previous_int = signal.signal(signal.SIGINT, cleanup)
    try:
        network = subprocess.run(
            ["docker", "network", "create", "--internal", "--driver", "bridge", network_name],
            check=True,
            capture_output=True,
            text=True,
        )
        network_id = network.stdout.strip()
        require(re.fullmatch(r"[0-9a-f]{64}", network_id) is not None, "invalid Docker network ID")
        relay = subprocess.run(
            [
                "docker", "create", "--name", relay_name,
                "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                "--pids-limit=64", f"--network={network_name}",
                "--user", config["runtimeUser"],
                "--network-alias=agentlab-gateway",
                "--add-host=host.docker.internal:host-gateway",
                "--env", "AGENTLAB_RELAY_TARGET_HOST=host.docker.internal",
                "--env", f"AGENTLAB_RELAY_TARGET_PORT={gateway_port}",
                "--entrypoint", "/usr/local/bin/node", config["imageId"],
                "-e", GATEWAY_RELAY,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        relay_id = relay.stdout.strip()
        require(re.fullmatch(r"[0-9a-f]{64}", relay_id) is not None, "invalid Gateway relay container ID")
        subprocess.run(["docker", "network", "connect", "bridge", relay_id], check=True, capture_output=True)
        subprocess.run(["docker", "start", relay_id], check=True, capture_output=True)
        receipt["probes"] = run_probe(base, config, workspace)
        name = f"agentlab-{re.sub(r'[^a-z0-9_.-]', '-', label.lower())}-{uuid.uuid4().hex[:12]}"
        created = subprocess.run(
            [
                "docker", "create", "--name", name, *base[:-1],
                "--entrypoint", "/runtime/node_modules/.bin/pi", base[-1],
                *arguments,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        container_id = created.stdout.strip()
        require(re.fullmatch(r"[0-9a-f]{64}", container_id) is not None, "invalid Docker container ID")
        inspected = subprocess.run(["docker", "inspect", container_id], check=True, capture_output=True)
        inspect_path.write_bytes(inspected.stdout)
        relay_inspect_path = receipt_root / f"{label}.relay-inspect.json"
        network_inspect_path = receipt_root / f"{label}.network-inspect.json"
        require(
            not relay_inspect_path.exists() and not network_inspect_path.exists(),
            "runtime topology evidence already exists",
        )
        relay_inspect = subprocess.run(
            ["docker", "inspect", relay_id], check=True, capture_output=True
        )
        network_inspect = subprocess.run(
            ["docker", "network", "inspect", network_id], check=True, capture_output=True
        )
        relay_inspect_path.write_bytes(relay_inspect.stdout)
        network_inspect_path.write_bytes(network_inspect.stdout)
        raw_inspect = json.loads(inspected.stdout)
        receipt["containerInspectSha256"] = digest(inspect_path)
        receipt["container"] = inspect_projection(raw_inspect)
        receipt["containerId"] = container_id
        receipt["relayContainerId"] = relay_id
        receipt["internalNetworkId"] = network_id
        receipt["relayInspectSha256"] = digest(relay_inspect_path)
        receipt["networkInspectSha256"] = digest(network_inspect_path)
        write_json(receipt_path, receipt)
        start_process = subprocess.Popen(["docker", "start", "-a", container_id])
        return_code = start_process.wait()
        final_inspect = subprocess.run(["docker", "inspect", container_id], check=True, capture_output=True)
        final_path = receipt_root / f"{label}.container-final.json"
        require(not final_path.exists(), "final container receipt already exists")
        final_path.write_bytes(final_inspect.stdout)
        final_row = json.loads(final_inspect.stdout)[0]
        state_row = final_row.get("State") or {}
        receipt.update(
            status="completed" if return_code == 0 else "participant-exited-nonzero",
            exitCode=return_code,
            containerStateExitCode=state_row.get("ExitCode"),
            containerStateStatus=state_row.get("Status"),
            containerFinalSha256=digest(final_path),
        )
        return return_code
    except Exception as error:
        receipt.update(status="isolation-error", errorClass=type(error).__name__, error=str(error), exitCode=None)
        return 125
    finally:
        cleanup()
        receipt.update(
            endedAt=datetime.now(timezone.utc).isoformat(),
            durationMs=round((time.monotonic() - started) * 1000),
        )
        write_json(receipt_path, receipt)
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)


if __name__ == "__main__":
    raise SystemExit(main())
