#!/usr/bin/env python3
"""Model-backed evaluator adapter for review-required calibration drafts."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import hashlib


def guidance_prompt(request: dict) -> str:
    packet = request.get("maintainerGuidance")
    if packet is None:
        return ""
    if (packet.get("schema") != "agentlab.maintainer_guidance_packet.v1"
            or packet.get("stage") != "calibration"
            or packet.get("automaticPromotion") is not False):
        raise ValueError("invalid bound guidance packet")
    sources = {(r["repositoryId"], r["revision"]) for r in request["sources"]}
    if not packet.get("sources") or any(
        (r["repositoryId"], r["sourceRevision"]) not in sources for r in packet["sources"]
    ):
        raise ValueError("guidance differs from exact authoring sources")
    if not packet.get("guidance"):
        raise ValueError("empty selected guidance")
    for row in packet["guidance"]:
        skill = row["skill"]
        encoded = json.dumps(skill, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        if (hashlib.sha256(encoded).hexdigest() != row["rowSha256"]
                or hashlib.sha256(skill["body"].encode()).hexdigest() != row["bodySha256"]
                or skill["stage"] != "calibration"
                or (skill["repositoryId"], skill["sourceRevision"]) not in sources):
            raise ValueError("guidance row bytes or applicability differ")
    return "\nExplicitly selected maintenance guidance follows, with its fixed-cut provenance and qualification limits.\nUse the guidance body when authoring this calibration, but do not treat it as task scoring, proof of runtime success, permission to change immutable sources, or authority to promote. Preserve contradictory observations.\n" + json.dumps(packet, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    if request.get("schema") != "agentlab.multi_repo_calibration_authoring_request.v1":
        raise ValueError("unsupported calibration authoring request")
    pi = os.environ.get("AGENTLAB_PI_BINARY") or shutil.which("pi")
    if not pi:
        raise RuntimeError("Pi executable is unavailable")
    module_path = Path(__file__).parents[1] / "real-code-agent" / "participant.py"
    spec = importlib.util.spec_from_file_location("agentlab_participant", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    evidence = Path.cwd() / "participant-evidence"
    evidence.mkdir()
    participant = module.Participant(
        evidence,
        Path.cwd() / "participant-state",
        Path(pi),
        os.environ["AGENTLAB_LM_GATEWAY_URL"],
        os.environ.get("AGENTLAB_MODEL", "glm-5.3-flash"),
        route=os.environ.get("AGENTLAB_PROVIDER_ROUTE", "glm"),
        implementation="pi",
    )
    prompt = f"""You are an independent benchmark evaluator-author, not the assessed Agent and not the task-intent constructor.
Read authoring-request.json, relevant-facts.jsonl, and every immutable source file under sources/.
Create a complete review-required draft under {args.output.as_posix()} with exactly these authorities:
- source-surface.json using schema agentlab.multi_repo_construction_surface.v1;
- oracle-contract.json using schema agentlab.multi_repo_oracle_contract.v1;
- bundle/calibration-bundle.json using schema agentlab.multi_repo_calibration_bundle_source.v1;
- a Python calibration driver, an independently executable Oracle, a reference solution tree, at least one structurally distinct alternative-valid solution tree, and meaningful wrong variants.
The oracle-contract oracleSha256 must be the SHA-256 of the exact authored Oracle file. Its receiptSchema, stage order, checks, variant names and expected verdicts must agree with the bundle and driver.
Baseline must fail. Reference and every alternative-valid variant must pass every stage. Every wrong variant must fail, and at least one wrong variant must pass an earlier stage before failing a later stage.
Never modify sources/. Do not expose evaluator files outside {args.output.as_posix()}. Do not claim product truth, qualification, review, or promotion. Do not access the network or install dependencies. Finish only after writing all files; your prose is not an artifact.
"""
    prompt += guidance_prompt(request)
    if "maintainerGuidance" in request:
        (evidence / "guidance-prompt.txt").write_text(prompt, encoding="utf-8")
        (evidence / "guidance-consumption-intent.json").write_text(json.dumps({
            "schema": "agentlab.maintainer_guidance_prompt_intent.v1",
            "requestSha256": hashlib.sha256(args.request.read_bytes()).hexdigest(),
            "promptSha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "knowledgeAuthority": request["maintainerGuidance"]["knowledgeAuthority"],
            "selectedSkills": [{"id": r["skill"]["id"], "rowSha256": r["rowSha256"],
                                "bodySha256": r["bodySha256"]}
                               for r in request["maintainerGuidance"]["guidance"]],
            "agentConsumptionVerified": False, "learningBenefitVerified": False,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        participant.turn("author-calibration", Path.cwd(), prompt=prompt)
    finally:
        participant.close()
    if not args.output.is_dir():
        raise RuntimeError("Pi completed without writing the calibration draft")


if __name__ == "__main__":
    main()
