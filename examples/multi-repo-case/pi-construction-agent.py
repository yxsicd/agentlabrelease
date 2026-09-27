#!/usr/bin/env python3
"""Model-backed construction adapter using the operator-owned Pi gateway capture."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    gateway = os.environ["AGENTLAB_LM_GATEWAY_URL"]
    model = os.environ.get("AGENTLAB_MODEL", "glm-5.3-flash")
    route = os.environ.get("AGENTLAB_PROVIDER_ROUTE", "glm")
    pi = os.environ.get("AGENTLAB_PI_BINARY") or shutil.which("pi")
    if not pi:
        raise RuntimeError("Pi executable is unavailable")
    request = json.loads(args.request.read_text())
    if request.get("schema") != "agentlab.multi_repo_intent_construction_request.v1":
        raise ValueError("unsupported construction request")

    module_path = Path(__file__).parents[1] / "real-code-agent" / "participant.py"
    spec = importlib.util.spec_from_file_location("agentlab_participant", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    evidence = Path.cwd() / "participant-evidence"
    evidence.mkdir()
    participant = module.Participant(
        evidence,
        Path.cwd() / "participant-state",
        Path(pi),
        gateway,
        model,
        route=route,
        implementation="pi",
    )
    stage_contract = json.dumps(request["oracleContract"], indent=2, sort_keys=True)
    prompt = f"""You are the benchmark construction Agent, not the assessed Agent.
Read construction-request.json, relevant-facts.jsonl and every file listed under sources/.
Infer a concise cross-repository task title and staged user demands grounded in the actual source.
Use the fixed stage and check mapping below exactly; check identifiers are Harness metadata and must not appear inside demand prose.
Do not reveal an Oracle, reference implementation, patch, code solution or implementation recipe.
Write only the required JSON object to {args.output.name}; do not modify any input file.

Fixed behavior contract:
{stage_contract}

The output must use schema agentlab.multi_repo_case_intent_draft.v1 and include candidateId and sourceSetSha256 exactly as supplied, plus non-empty caseId, title and ordered stages with id, demand and checkIds.
"""
    try:
        participant.turn("construct-intent", Path.cwd(), prompt=prompt)
    finally:
        participant.close()
    if not args.output.is_file():
        raise RuntimeError("Pi completed without writing the intent draft")


if __name__ == "__main__":
    main()
