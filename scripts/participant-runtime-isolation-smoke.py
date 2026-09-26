#!/usr/bin/env python3
"""Run a secret-free live Docker smoke for the assessed-participant boundary."""
from __future__ import annotations

import http.server
import argparse
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import threading


ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get("AGENTLAB_PARTICIPANT_SMOKE_IMAGE", "node:22-bookworm-slim")
LOCAL_TOKEN = "agentlab-runtime-smoke-local-token"


class ProbeHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path != "/__agentlab_runtime_probe":
            self.send_error(404)
            return
        if self.headers.get("Authorization") != "Bearer " + LOCAL_TOKEN:
            self.send_error(401)
            return
        self.send_response(204)
        self.end_headers()


def run(*arguments, **options):
    return subprocess.run(arguments, check=True, **options)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("refusing to overwrite participant runtime smoke evidence")
    server = http.server.ThreadingHTTPServer(("0.0.0.0", 0), ProbeHandler)
    server.daemon_threads = False
    server.block_on_close = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="agentlab-runtime-smoke-") as raw:
            root = Path(raw)
            runtime = root / "runtime"
            case_input = root / "case"
            forbidden = root / "operator/evaluator"
            workspace = root / "workspace"
            state = root / "state"
            receipts = root / "receipts"
            for path in (
                runtime / "node_modules/.bin",
                case_input,
                forbidden,
                workspace,
                state,
                receipts,
            ):
                path.mkdir(parents=True, exist_ok=True)
            (runtime / "package-lock.json").write_text(
                '{"name":"agentlab-runtime-smoke","lockfileVersion":3,"packages":{}}\n'
            )
            pi = runtime / "node_modules/.bin/pi"
            pi.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' '{\"type\":\"tool_execution_end\",\"result\":{\"isError\":false}}'\n"
            )
            pi.chmod(0o755)
            (case_input / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema": "agentlab.blind_case_participant_bundle.v1",
                        "files": [],
                        "constraints": {},
                    }
                )
                + "\n"
            )
            (forbidden / "oracle.mjs").write_text("throw new Error('hidden');\n")
            (state / "models.json").write_text(
                json.dumps(
                    {
                        "providers": {
                            "agentlab-ci": {
                                "baseUrl": "http://agentlab-gateway:18765/v1",
                                "apiKey": LOCAL_TOKEN,
                            }
                        }
                    }
                )
                + "\n"
            )
            config = root / "runtime.json"
            run(
                "python3",
                str(ROOT / "scripts/prepare-participant-runtime.py"),
                "--image",
                IMAGE,
                "--pi-runtime",
                str(runtime),
                "--case-input",
                str(case_input),
                "--forbid",
                str(forbidden),
                "--output",
                str(config),
                capture_output=True,
            )
            environment = {
                key: os.environ[key]
                for key in ("PATH", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG")
                if key in os.environ
            }
            environment.update(
                PI_CODING_AGENT_DIR=str(state),
                AGENTLAB_PARTICIPANT_RUNTIME_CONFIG=str(config),
                AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT=str(receipts),
                AGENTLAB_PARTICIPANT_RUNTIME_LABEL="smoke",
                AGENTLAB_OPERATOR_GATEWAY_PORT=str(server.server_port),
            )
            completed = run(
                str(ROOT / "scripts/run-pi-in-docker.py"),
                "--print",
                "--session",
                str(state / "session.jsonl"),
                "smoke",
                cwd=workspace,
                env=environment,
                capture_output=True,
                text=True,
            )
            validation_path = root / "validation.json"
            run(
                "python3",
                str(ROOT / "scripts/validate-participant-runtime.py"),
                "--config",
                str(config),
                "--receipt-root",
                str(receipts),
                "--workspace",
                str(workspace),
                "--participant-state",
                str(state),
                "--label",
                "smoke",
                "--output",
                str(validation_path),
                capture_output=True,
            )
            validation = json.loads(validation_path.read_text())
            if not all(
                validation.get(key) is True
                for key in (
                    "filesystemIsolationQualified",
                    "externalCredentialIsolationQualified",
                    "networkEgressIsolationQualified",
                )
            ):
                raise RuntimeError("participant runtime isolation did not qualify")
            receipt = json.loads((receipts / "smoke.json").read_text())
            for command in (
                ["docker", "inspect", receipt["containerId"]],
                ["docker", "inspect", receipt["relayContainerId"]],
                ["docker", "network", "inspect", receipt["internalNetworkId"]],
            ):
                absent = subprocess.run(command, capture_output=True)
                if absent.returncode == 0:
                    raise RuntimeError("participant runtime resource was not cleaned")
            summary = {
                "schema": "agentlab.participant_runtime_isolation_smoke.v1",
                "ok": True,
                "participantStdout": completed.stdout.strip(),
                "imageId": validation["imageId"],
                "filesystemIsolationQualified": True,
                "externalCredentialIsolationQualified": True,
                "networkEgressIsolationQualified": True,
                "resourcesCleaned": True,
            }
            args.output.mkdir(parents=True)
            shutil.copy2(config, args.output / "runtime.json")
            shutil.copytree(receipts, args.output / "receipts")
            shutil.copy2(validation_path, args.output / "validation.json")
            (args.output / "summary.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True) + "\n"
            )
            print(json.dumps(summary, sort_keys=True))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
