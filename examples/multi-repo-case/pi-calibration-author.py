#!/usr/bin/env python3
"""Model-backed evaluator adapter for review-required calibration drafts."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil


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
    try:
        participant.turn("author-calibration", Path.cwd(), prompt=prompt)
    finally:
        participant.close()
    if not args.output.is_dir():
        raise RuntimeError("Pi completed without writing the calibration draft")


if __name__ == "__main__":
    main()
