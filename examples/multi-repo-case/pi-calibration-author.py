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


def stage_prompt(request: dict, output: Path) -> str:
    context = request["stageContext"]
    return f"""You are a maintenance calibration author, not an assessed task-solving Agent.
Read authoring-request.json and every supplied immutable file under sources/.
Author {output.as_posix()}/proposed-stage-contract.json. Do not modify sources/ or the request.
This is a trusted-source host-dispatch AbilityStage/ApplicationContext seam, not actual Harmony framework, build, emulator, UI or ohosTest qualification.
The contract must use schema agentlab.harmony_stage_control_contract.v1 and reviewed=false. Bind candidateId, candidateSha256, sourceRevision and modulePath exactly to stageContext: {json.dumps(context, sort_keys=True)}.
Use these remaining contract fields only: createMarker, destroyMarker, registrationMarker, configurationPrefix, eventName, configurations, variants. Derive concrete values from the supplied source; do not invent registrations or log markers.
Each configuration has id, language, colorMode. Begin with an initial configuration, then change language and colorMode independently, one dimension per transition. Check IDs are stage-created, stage-destroyed, application-environment-registration and the configuration ids.
Each variant has id, path, from, to, expectedFailedChecks. Use at least two distinct meaningful wrong variants with exact one-occurrence source replacements, including wrong entry binding and wrong environment registration. A wrong entry must select another supplied existing stage, not a missing file. Declare the intended failed checks from observed semantics. Preserve the original accepted source as a passing baseline.
Keep all source paths repository-relative. Do not execute authored code, install dependencies, access network, claim review, or promote any case. This output is only a review-required proposal; the operator independently executes and judges controls later. Finish after writing the JSON file.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    is_stage = request.get("schema") == "agentlab.stage_calibration_authoring_request.v1"
    if not is_stage and request.get("schema") != "agentlab.multi_repo_calibration_authoring_request.v1":
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
    if is_stage:
        prompt = stage_prompt(request, args.output)
    prompt += guidance_prompt(request)
    if "maintainerGuidance" in request:
        (evidence / "guidance-prompt.txt").write_text(prompt, encoding="utf-8")
        (evidence / "guidance-consumption-intent.json").write_text(json.dumps({
            "schema": "agentlab.maintainer_guidance_prompt_intent.v1",
            "requestSha256": hashlib.sha256(args.request.read_bytes()).hexdigest(),
            "promptSha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "knowledgeAuthority": request["maintainerGuidance"]["knowledgeAuthority"],
            "participantIdentity": {"model": participant.model, "providerRoute": participant.route,
                                    "implementation": participant.implementation},
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
    if is_stage:
        proposed = json.loads((args.output / "proposed-stage-contract.json").read_text())
        context = request["stageContext"]
        allowed = {"schema", "reviewed", "candidateId", "candidateSha256", "sourceRevision", "modulePath",
                   "createMarker", "destroyMarker", "registrationMarker", "configurationPrefix", "eventName", "configurations", "variants"}
        if (set(proposed) != allowed or proposed.get("schema") != "agentlab.harmony_stage_control_contract.v1"
                or proposed.get("reviewed") is not False
                or any(proposed.get(k) != context[k] for k in ("candidateId", "candidateSha256", "sourceRevision", "modulePath"))):
            raise ValueError("stage contract proposal changed identity, schema or review boundary")


if __name__ == "__main__":
    main()
