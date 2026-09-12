#!/usr/bin/env python3
"""Create real AgentLab tables and Session, then recover after process/projection loss."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import uuid

from fixture import init_volume, write_agent_config

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("demo", REPO / "examples/run.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image", required=True, help="image reference from installed composition")
    p.add_argument("--runtime-volume", required=True, help="runtime volume from installed composition")
    p.add_argument("--root", required=True, type=Path)
    args = p.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    state = root / ("state-" + run_id)
    state.mkdir(mode=0o700)
    evidence = root / ("evidence-" + run_id)
    evidence.mkdir()
    prefix = "al-demo-" + run_id
    network, volume = prefix, prefix + "-data"
    gateway, agent = prefix + "-gateway", prefix + "-store"
    made_containers, made_volumes, made_network = [], [], False
    summary = {"schema":"agentlab.public_tablegit_session_demo.v1", "ok":False,
               "scope":"released-session-provisioner-tablegit-lease-projection-recovery",
               "fixedChannelPromoted":False,"fullWhiteboxQualified":False,
               "agentTurnExecuted":False,"sessionfsSnapshotQualified":False,"checks":{}}

    def save(path, value):
        path.write_text(json.dumps(value, indent=2) + "\n")
        return value

    def run(command, label=None):
        r = subprocess.run(command, capture_output=True, timeout=180)
        if label:
            (evidence / (label + ".stdout")).write_bytes(r.stdout)
            (evidence / (label + ".stderr")).write_bytes(r.stderr)
        if r.returncode:
            raise RuntimeError(f"{label or command[1]} failed ({r.returncode}); {r.stderr.decode()}")
        return r.stdout.decode().strip()

    def docker(*arguments, label=None):
        return run(["docker", *arguments], label)

    def wait_route(label):
        from websocket import create_connection
        port = docker("inspect", "--format", '{{(index (index .NetworkSettings.Ports "8002/tcp") 0).HostPort}}', gateway)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            connection = None
            try:
                connection = create_connection(
                    "ws://127.0.0.1:"+port+"/__mcpgit/service-ws", timeout=3,
                    host="gateway", subprotocols=["mcpgit.service.ws.v1"],
                    header={"Authorization":(state / "caller.authorization").read_text().strip()})
                request_id = str(uuid.uuid4())
                connection.send_binary(json.dumps({"kind":"request","message":{
                    "protocol":"mcpgit.service.v2","request_id":request_id,
                    "invocation_id":str(uuid.uuid4()),"method":"repository.list",
                    "deadline_unix_ms":None,"payload":{}}}).encode())
                response = json.loads(connection.recv())
                with (evidence / (label+".jsonl")).open("a") as log:
                    log.write(json.dumps(response)+"\n")
                message = response["message"]
                if (message["request_id"] == request_id and message["outcome"] == "success"
                    and {"owner-template","session-template"}.issubset(
                        {item["id"] for item in message["payload"]["repositories"]})):
                    return
            except Exception as error:
                with (evidence / (label+".log")).open("a") as log:
                    log.write(str(error)+"\n")
            finally:
                if connection is not None:
                    connection.close()
            time.sleep(.25)
        raise RuntimeError(label+" repository read did not become ready; see readiness evidence")

    def probe(mode, extra, label):
        values = {"MCPGIT_PROVISION_PROBE_MODE":mode,
                  "MCPGIT_PROBE_URL":"ws://127.0.0.1:8002/__mcpgit/service-ws",
                  "MCPGIT_PROBE_HOST":"gateway",
                  "MCPGIT_PROBE_CALLER_PROFILE":"demo",
                  "MCPGIT_PROBE_CREDENTIAL_GENERATION":"1",
                  "MCPGIT_PROBE_AUTHORIZATION_FILE":"/demo/caller.authorization", **extra}
        env = [part for key,value in values.items() for part in ("--env", key+"="+value)]
        result = docker("run", "--rm", "--network", "container:"+gateway,
                        "--mount", f"type=bind,src={state},dst=/demo,readonly",
                        "--mount", f"type=volume,src={args.runtime_volume},dst=/agentlab-release,readonly",
                        *env, "--entrypoint", "/agentlab-release/bin/agentlab-mcpgit-template-probe",
                        args.image, label=label)
        return save(evidence / (label + ".json"), json.loads(result))

    try:
        lock = demo.acquire(REPO / "release/ci/mcpgit-program.json", root / "downloads/mcpgit.tar.gz")
        summary["mcpgit"] = lock
        program = root / "program"
        program.mkdir(exist_ok=True)
        run(["tar", "-xzf", str(root / "downloads/mcpgit.tar.gz"), "-C", str(program)], "extract")
        binary = next(program.rglob("bin/mcpgit"))
        bin_dir = binary.parent
        summary["mcpgitBinarySha256"] = demo.sha256(binary)
        caller_token, agent_token = secrets.token_hex(32), secrets.token_hex(32)
        save(state / "gateway.json", {"gateway_id":"public-demo","bind":"0.0.0.0:8002",
            "allowed_organizations":["org:demo"],"default_organization_id":"org:demo",
            "lease_ttl_ms":30000,"heartbeat_interval_ms":5000,"max_frame_payload_bytes":262144,
            "max_concurrent_streams":64,"required_capabilities":{},
            "required_organization_capabilities":{"org:demo":{"workspace":"v1"}}})
        save(state / "credentials.json", {"agents":[{"agent_id":"demo","bearer_token":agent_token}],
            "callers":[{"bearer_token":caller_token,"organizations":["org:demo"],"provider_id":"public-demo",
                        "subject_fingerprint":"hmac-sha256:"+"a"*64,
                        "person_id":"11111111-1111-4111-8111-111111111111","actor_id":None}]})
        (state / "caller.authorization").write_text("Bearer "+caller_token+"\n")
        (state / "agent.authorization").write_text("Bearer "+agent_token+"\n")
        for name in ("credentials.json", "caller.authorization", "agent.authorization"):
            (state / name).chmod(0o600)
        write_agent_config(state / "mcpgit.toml")
        docker("network", "create", network); made_network = True
        docker("volume", "create", volume); made_volumes.append(volume)
        revisions = save(evidence / "empty-repository-revisions.json", init_volume(args.image, volume))
        common = ["--network",network,"--mount",f"type=bind,src={bin_dir},dst=/demo-bin,readonly",
                  "--mount",f"type=bind,src={state},dst=/demo,readonly"]
        docker("run","-d","--name",gateway,"--network-alias","gateway","-p","127.0.0.1::8002",*common,
               "--entrypoint","/demo-bin/mcpgitgw",args.image,
               "--config","/demo/gateway.json","--credentials","/demo/credentials.json")
        made_containers.append(gateway)
        docker("run","-d","--name",agent,*common,"--mount",f"type=volume,src={volume},dst=/data",
               "--env","MCPGIT_AGENT_GATEWAY_URL=ws://gateway:8002",
               "--env","MCPGIT_AGENT_ID=demo","--env","MCPGIT_AGENT_ORG_ID=org:demo",
               "--env","MCPGIT_MANAGED_REPOSITORY_ROOT=/data/managed",
               "--env","MCPGIT_DATA_FORMAT=agentlab-e2e-v1","--entrypoint","/bin/sh",args.image,"-lc",
               'export MCPGIT_AGENT_AUTHORIZATION="$(cat /demo/agent.authorization)"; '
               'exec /demo-bin/mcpgit --config /demo/mcpgit.toml --transport streamable-http --bind 0.0.0.0:8001')
        made_containers.append(agent)
        wait_route("initial-route")
        template = probe("bootstrap-templates", {
            "MCPGIT_PROBE_OWNER_TEMPLATE_REPO":"owner-template",
            "MCPGIT_PROBE_OWNER_TEMPLATE_REVISION":revisions["ownerTemplate"],
            "MCPGIT_PROBE_SESSION_TEMPLATE_REPO":"session-template",
            "MCPGIT_PROBE_SESSION_TEMPLATE_REVISION":revisions["sessionTemplate"]}, "template-lock")
        save(state / "template-lock.json", template)
        qualification = probe("verify-templates", {"MCPGIT_PROBE_TEMPLATE_LOCK_FILE":"/demo/template-lock.json"}, "qualification")
        save(state / "qualification.json", {"schema":"agentlab.mcpgit.template-qualification-set.v2",
            "status":"qualified",
            "templateContractDigest":template["contractDigest"],"organizations":[qualification]})
        settings = {"MCPGIT_PROBE_TEMPLATE_LOCK_FILE":"/demo/template-lock.json",
                    "MCPGIT_PROBE_TEMPLATE_QUALIFICATION_FILE":"/demo/qualification.json",
                    "MCPGIT_PROBE_PROJECTION_ROOT":"/tmp/agentlab-mcpgit-e2e-public-demo"}
        first = probe("provision", settings, "session-created")
        docker("restart",agent,label="restart-store")
        docker("restart",gateway,label="restart-gateway")
        wait_route("restarted-route")
        second = probe("restart-readback", settings, "session-recovered")
        checks = summary["checks"]
        checks["template_qualification"] = qualification["status"] == "qualified"
        checks["concurrent_session_creation_replayed"] = first["concurrentReplay"] is True
        checks["projection_removed_after_publication"] = first["projectionPurgedAfterSeed"] is True
        checks["cold_recovery_without_local_projection"] = second["projectionAbsentAtStart"] is True
        checks["same_session_binding"] = first["binding"] == second["binding"]
        checks["exact_workspace_revision_recovered"] = first["exactMaterializedRevision"] == second["exactMaterializedRevision"]
        checks["exact_file_content_recovered"] = first["exactProjectionDigest"] == second["exactProjectionDigest"]
        checks["lease_revision_recovered"] = first["leaseRevision"] == second["leaseRevision"]
        checks["projection_state_in_table"] = second["projectionState"]["exactCommittedReadback"] is True
        checks["operation_prestate_recovered"] = second["persistedPreStateReadback"] is True
        summary["sessionTables"] = len(template["session"]["tables"])
        summary["ownerTables"] = len(template["ownerGlobal"]["tables"])
        summary["ok"] = all(checks.values())
    except Exception as error:
        summary["error"] = str(error)
        raise
    finally:
        for container in made_containers:
            r = subprocess.run(["docker","logs",container],capture_output=True)
            (evidence / (container+".stdout")).write_bytes(r.stdout)
            (evidence / (container+".stderr")).write_bytes(r.stderr)
            subprocess.run(["docker","rm","-f",container],check=False,stdout=subprocess.DEVNULL)
        for item in made_volumes:
            subprocess.run(["docker","volume","rm",item],check=False,stdout=subprocess.DEVNULL)
        if made_network:
            subprocess.run(["docker","network","rm",network],check=False,stdout=subprocess.DEVNULL)
        save(evidence / "summary.json", summary)
        print(json.dumps(summary,indent=2))
        print("Evidence:",evidence)
    raise SystemExit(0 if summary["ok"] else 1)


if __name__ == "__main__":
    main()
