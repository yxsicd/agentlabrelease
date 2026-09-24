#!/usr/bin/env python3
"""Persistent Pi adapter for staged multi-repository assessment."""
import argparse
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import hashlib


def load_blind_input(root_value):
    if not root_value:
        return None
    root = Path(root_value)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "agentlab.blind_case_participant_bundle.v1":
        raise RuntimeError("unsupported blind participant manifest")
    task_rows = [row for row in manifest.get("files", []) if row.get("role") == "task"]
    if len(task_rows) != 1:
        raise RuntimeError("blind participant manifest requires exactly one task")
    task_path = root / task_rows[0]["path"]
    body = task_path.read_bytes()
    if hashlib.sha256(body).hexdigest() != task_rows[0].get("sha256"):
        raise RuntimeError("blind participant task digest differs")
    task = json.loads(body)
    if task.get("schema") != "agentlab.multi_repo_participant_task.v1":
        raise RuntimeError("unsupported blind participant task")
    stages = task.get("stages")
    if not isinstance(stages, list) or not stages:
        raise RuntimeError("blind participant stages are absent")
    stage_map = {row.get("id"): row.get("demand") for row in stages}
    if len(stage_map) != len(stages) or not all(isinstance(key, str) and isinstance(value, str) for key, value in stage_map.items()):
        raise RuntimeError("blind participant stages are invalid")
    allowed = (manifest.get("constraints") or {}).get("allowedEditPaths")
    if not isinstance(allowed, list) or not allowed or not all(isinstance(path, str) for path in allowed):
        raise RuntimeError("blind participant allowed edit paths are absent")
    return {
        "manifestSha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "caseId": task.get("caseId"),
        "sourceSetSha256": task.get("sourceSetSha256"),
        "stages": stage_map,
        "allowedEdits": sorted(allowed),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", action="store_true", required=True)
    parser.parse_args()
    pi = os.environ.get("AGENTLAB_PI_BINARY") or shutil.which("pi")
    if not pi:
        raise RuntimeError("Pi executable is unavailable")
    evidence = Path(os.environ["AGENTLAB_ASSESSMENT_EVIDENCE"])
    blind_input = load_blind_input(os.environ.get("AGENTLAB_CASE_INPUT_ROOT"))
    module_path = Path(__file__).parents[1] / "real-code-agent" / "participant.py"
    spec = importlib.util.spec_from_file_location("agentlab_participant", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    participant = module.Participant(
        evidence,
        evidence.parent / "participant-state",
        Path(pi),
        os.environ["AGENTLAB_LM_GATEWAY_URL"],
        os.environ.get("AGENTLAB_MODEL", "glm-5.3-flash"),
        route=os.environ.get("AGENTLAB_PROVIDER_ROUTE", "glm"),
        implementation="pi",
    )
    try:
        for line in sys.stdin:
            message = json.loads(line)
            if message.get("action") == "close":
                print(json.dumps({"ok": True, "closed": True}), flush=True)
                return
            stage = message["stageId"]
            request = json.loads(Path(message["requestPath"]).read_text())
            demand = request["demand"]
            allowed_edits = sorted(request["allowedEdits"])
            if blind_input is not None:
                if request.get("blindParticipantManifestSha256") != blind_input["manifestSha256"]:
                    raise RuntimeError("stage request blind manifest digest differs")
                if request.get("caseId") != blind_input["caseId"] or request.get("sourceSetSha256") != blind_input["sourceSetSha256"]:
                    raise RuntimeError("stage request blind case identity differs")
                if stage not in blind_input["stages"] or demand != blind_input["stages"][stage]:
                    raise RuntimeError("stage request differs from blind participant task")
                if allowed_edits != blind_input["allowedEdits"]:
                    raise RuntimeError("stage request differs from blind edit constraints")
                demand = blind_input["stages"][stage]
                allowed_edits = blind_input["allowedEdits"]
            prompt = f"""You are the assessed Code Agent. Work only inside the current multi-repository workspace.
Implement this user demand while preserving prior-stage behavior:

{demand}

You may edit only these paths: {', '.join(allowed_edits)}.
Do not inspect parent directories, Harness evidence, Oracle code, reference implementations, or hidden solutions.
Use source inspection and file tools, make the actual edits, and briefly report completion.
"""
            try:
                with contextlib.redirect_stdout(sys.stderr):
                    participant.turn(stage, Path(message["workspace"]), prompt=prompt)
                response = {"ok": True, "stageId": stage}
            except Exception as error:
                response = {"ok": False, "stageId": stage, "error": f"{type(error).__name__}: {error}"}
            print(json.dumps(response), flush=True)
    finally:
        participant.close()


if __name__ == "__main__":
    main()
