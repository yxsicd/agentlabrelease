#!/usr/bin/env python3
"""Run a scripted participant against real standalone Harmony/SessionFS services.

This portable CI tier is NOT the full AgentLab Session/TableGit runtime tier.
"""
import argparse
import hashlib
import json
import pathlib
import selectors
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = "entry/src/main/ets/pages/Index.ets"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Campaign:
    def __init__(self, args):
        self.args = args
        self.root = args.evidence.resolve()
        self.root.mkdir(parents=True, exist_ok=False)
        self.storage = args.storage.resolve()
        self.storage.mkdir(parents=True, exist_ok=True)
        self.tasks = self.storage / "tasks"
        self.tasks.mkdir(exist_ok=True)
        self.processes = []
        self.logs = []
        self.events = []
        self.checks = {}
        self.receipts = []
        self.fs_port, self.ops_port = free_port(), free_port()

    def event(self, kind, **fields):
        row = {"ordinal": len(self.events), "kind": kind, **fields}
        self.events.append(row)
        with (self.root / "events.jsonl").open("a") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    def check(self, name, condition):
        self.checks[name] = bool(condition)
        self.event("evaluation", name=name, passed=bool(condition))
        if not condition:
            raise AssertionError(name)

    def start(self, name, arguments, port):
        log = (self.root / f"{name}.log").open("a")
        self.logs.append(log)
        proc = subprocess.Popen(arguments, stdout=log, stderr=log)
        self.processes.append(proc)
        self.event("service_start", name=name, arguments=arguments, pid=proc.pid)
        for _ in range(100):
            if proc.poll() is not None:
                raise RuntimeError(f"{name} exited {proc.returncode}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as res:
                    if res.status == 200:
                        return proc
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        raise TimeoutError(name)

    def start_services(self):
        self.start("sessionfs", [str(self.args.bin_dir / "alsessionfsd"), "serve",
                   "--bind", f"127.0.0.1:{self.fs_port}", "--backend", self.args.backend,
                   "--storage-root", str(self.storage)], self.fs_port)
        self.start("harmony", [str(self.args.bin_dir / "alharmony-ops"), "serve",
                   "--bind", f"127.0.0.1:{self.ops_port}", "--workers", "2",
                   "--task-root", str(self.tasks), "--fork-backend", "sessionfs",
                   "--sessionfs-endpoint", f"http://127.0.0.1:{self.fs_port}"], self.ops_port)

    def stop_services(self):
        for proc in reversed(self.processes):
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        self.processes.clear()

    def call(self, actor, operation, arguments):
        self.event("http_request", actor=actor, operation=operation, arguments=arguments)
        url = f"http://127.0.0.1:{self.ops_port}/v1/ops/{operation}?" + urllib.parse.urlencode(arguments)
        try:
            with urllib.request.urlopen(url, timeout=15) as res:
                status, raw = res.status, res.read().decode()
        except urllib.error.HTTPError as err:
            status, raw = err.code, err.read().decode()
        self.event("http_response", actor=actor, operation=operation, status=status, raw=raw)
        receipt = json.loads(raw)
        self.receipts.append(receipt)
        return receipt

    def turn(self, turn):
        self.event("participant_turn", turn=turn)
        log = (self.root / "mock-agent.stderr").open("a")
        self.logs.append(log)
        proc = subprocess.Popen([sys.executable, str(ROOT / "examples/mock-agent/agent.py")],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                                text=True, bufsize=1)
        results = []
        try:
            proc.stdin.write(json.dumps(turn) + "\n")
            proc.stdin.flush()
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                while True:
                    if not selector.select(timeout=15):
                        raise TimeoutError("mock agent did not respond")
                    line = proc.stdout.readline()
                    if not line:
                        raise RuntimeError("mock agent exited before final")
                    msg = json.loads(line)
                    self.event("participant_output", turnId=turn["id"], message=msg)
                    if msg["type"] == "final":
                        break
                    if msg["type"] != "tool_call":
                        raise ValueError("unexpected participant message")
                    arguments = {**msg["arguments"], "taskId": turn["task"],
                                 "projectRoot": str(self.tasks / turn["task"] / "workspace/app")}
                    receipt = self.call("mock-agent", msg["operation"], arguments)
                    results.append(receipt)
                    proc.stdin.write(json.dumps({"type": "tool_result", "receipt": receipt}) + "\n")
                    proc.stdin.flush()
            proc.stdin.close()
            if proc.wait(timeout=5) != 0:
                raise RuntimeError("mock agent failed")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            proc.stdout.close()
        return results

    def run(self):
        scenario = json.loads(self.args.scenario.read_text())
        (self.root / "scenario.json").write_bytes(self.args.scenario.read_bytes())
        self.start_services()
        self.check("prepare", self.call("supervisor", "harmony.task.prepare", {"taskId": "parent"})["ok"])
        self.check("mockCreate", all(r["ok"] for r in self.turn(scenario["turns"][0])))
        parent = self.tasks / "parent/workspace/app" / PAGE
        child = self.tasks / "child/workspace/app" / PAGE
        seed = digest(parent)
        self.check("fork", self.call("supervisor", "harmony.task.fork", {
            "taskId": "child", "parentTaskId": "parent"})["ok"])
        self.check("seedInherited", digest(child) == seed)
        self.check("firstEdit", all(r["ok"] for r in self.turn(scenario["turns"][1])))
        edited = digest(child)
        self.check("firstEditObserved", edited != seed and "AgentLab Mock Round One" in child.read_text())
        failure = self.turn(scenario["turns"][2])
        self.check("agentFailureDetectedDespiteSuccessClaim", len(failure) == 1 and failure[0]["ok"] is False)
        self.check("failedEditPreservedState", digest(child) == edited)
        self.stop_services()
        self.start_services()
        self.check("restartPreservedState", digest(parent) == seed and digest(child) == edited)
        self.check("agentRecovery", all(r["ok"] for r in self.turn(scenario["turns"][3])))
        self.check("recoveryObserved", "AgentLab Mock Round Two" in child.read_text() and digest(child) != edited)
        self.check("parentIsolated", digest(parent) == seed)
        self.check("forkAfterRestart", self.call("supervisor", "harmony.task.fork", {
            "taskId": "replay", "parentTaskId": "parent"})["ok"])
        self.check("seedReplay", digest(self.tasks / "replay/workspace/app" / PAGE) == seed)
        if self.args.backend == "btrfs-subvolume":
            for task in ("parent", "child", "replay"):
                res = subprocess.run(["btrfs", "subvolume", "show", str(self.tasks / task)],
                                     capture_output=True, text=True, check=True)
                self.event("btrfs_subvolume", task=task, stdout=res.stdout)
            self.check("realBtrfsSubvolumes", True)
        for task in ("parent", "child", "replay"):
            raw = (self.tasks / task / "receipts/events.jsonl").read_text()
            (self.root / f"{task}-service-receipts.jsonl").write_text(raw)
            rows = [json.loads(line) for line in raw.splitlines()]
            self.check(f"{task}ServiceEvidence", bool(rows))
        self.event("file_identities", parent=seed, child=digest(child))

    def close(self, error):
        self.stop_services()
        for log in self.logs:
            log.close()
        summary = {"schema": "agentlab.mock_agent_ci.v1", "ok": error is None,
                   "backend": self.args.backend, "checks": self.checks,
                   "failure": error, "mocked": ["agent decision-making"],
                   "real": ["published Harmony HTTP operations", "standalone SessionFS", "workspace files", "service receipts"],
                   "notQualified": ["full AgentLab Session/TableGit", "LLM Gateway", "HAP compilation", "fixed-channel promotion"],
                   "binaries": {name: digest(self.args.bin_dir / name) for name in ("alharmony-ops", "alsessionfsd")}}
        (self.root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        files = sorted(p for p in self.root.iterdir() if p.is_file())
        (self.root / "SHA256SUMS").write_text("".join(f"{digest(p)}  {p.name}\n" for p in files))
        print(json.dumps(summary))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", type=pathlib.Path, required=True)
    parser.add_argument("--evidence", type=pathlib.Path, required=True)
    parser.add_argument("--storage", type=pathlib.Path, required=True)
    parser.add_argument("--backend", choices=["copy-tree", "btrfs-subvolume"], default="copy-tree")
    parser.add_argument("--scenario", type=pathlib.Path, default=ROOT / "examples/mock-agent/scenario.json")
    args = parser.parse_args()
    args.bin_dir = args.bin_dir.resolve()
    campaign = Campaign(args)
    error = None
    try:
        campaign.run()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        campaign.event("campaign_failure", error=error)
    finally:
        campaign.close(error)
    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main())
