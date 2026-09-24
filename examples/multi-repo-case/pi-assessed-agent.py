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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", action="store_true", required=True)
    parser.parse_args()
    pi = os.environ.get("AGENTLAB_PI_BINARY") or shutil.which("pi")
    if not pi:
        raise RuntimeError("Pi executable is unavailable")
    evidence = Path(os.environ["AGENTLAB_ASSESSMENT_EVIDENCE"])
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
            prompt = f"""You are the assessed Code Agent. Work only inside the current multi-repository workspace.
Implement this user demand while preserving prior-stage behavior:

{request['demand']}

You may edit only these paths: {', '.join(request['allowedEdits'])}.
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
