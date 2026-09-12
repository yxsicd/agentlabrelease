#!/usr/bin/env python3
"""Run the same published-package demonstrations locally and in GitHub Actions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time

REPO = Path(__file__).resolve().parent.parent


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def acquire(lock_path, destination):
    lock = json.loads(lock_path.read_text())
    destination.parent.mkdir(parents=True, exist_ok=True)
    def valid():
        return (destination.is_file() and destination.stat().st_size == lock["bytes"]
                and sha256(destination) == lock["sha256"])
    if not valid():
        partial = destination.with_suffix(".partial")
        subprocess.run(["curl", "-fL", "--retry", "3", "--connect-timeout", "20",
                        "--output", str(partial), lock["artifact"]], check=True)
        if partial.stat().st_size != lock["bytes"] or sha256(partial) != lock["sha256"]:
            raise RuntimeError("download does not match the committed dependency lock")
        partial.replace(destination)
    return lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=["protocol"])
    parser.add_argument("--root", type=Path, required=True,
                        help="dedicated demo directory; archives remain cached here")
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        parser.error("this published runtime is Linux x64; use a Linux x64 host or CI")
    root = args.root.expanduser().resolve()
    evidence = root / "evidence" / (args.scenario + "-" + str(time.time_ns()))
    evidence.mkdir(parents=True)
    receipt = {"schema":"agentlab.public_demo_run.v1", "scenario":args.scenario,
               "ok":False,"evidence":str(evidence),"fixedChannelPromoted":False}
    try:
        lock = acquire(REPO / "release/ci/harness-runtime.json", root / "downloads/runtime.tar.zst")
        receipt["runtime"] = lock
        runtime = root / "runtime"
        runtime.mkdir(exist_ok=True)
        subprocess.run(["tar", "--zstd", "-xf", str(root / "downloads/runtime.tar.zst"),
                        "-C", str(runtime)], check=True)
        binary = runtime / "payload/bin/chat-rs"
        receipt["binarySha256"] = sha256(binary)
        env = {**os.environ, "AGENTLAB_DEMO_EVIDENCE":str(evidence),
               "AGENTLAB_SERVICE_INTERFACE_CHAT_RS_BIN":str(binary)}
        command = ["python3", str(REPO / "examples/service-protocol/verify.py")]
        with (evidence / "verification.log").open("wb") as log:
            result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        print((evidence / "verification.log").read_text())
        receipt["exitCode"] = result.returncode
        receipt["ok"] = result.returncode == 0
    except Exception as error:
        receipt["error"] = str(error)
        raise
    finally:
        (evidence / "run.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print("Evidence:", evidence)
    raise SystemExit(0 if receipt["ok"] else 1)


if __name__ == "__main__":
    main()
