#!/usr/bin/env python3
"""Deterministic transport fixture for the replaceable construction participant."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text())
    candidate = request["candidate"]
    stages = []
    for stage_id in request["oracleContract"]["stageOrder"]:
        checks = [row for row in request["oracleContract"]["checks"] if row["stage"] == stage_id]
        stages.append({
            "id": stage_id,
            "demand": " ".join(row["behavior"] for row in checks),
            "checkIds": [row["id"] for row in checks],
        })
    draft = {
        "schema": "agentlab.multi_repo_case_intent_draft.v1",
        "caseId": "case-cross-repo-retry-policy-v1",
        "candidateId": request["candidateId"],
        "sourceSetSha256": request["sourceSetSha256"],
        "title": f"Propagate behavior from {candidate['seed'].get('repositoryId', candidate['seed'].get('specifier', 'the selected contract'))} across {candidate['affectedRepositoryCount']} repositories",
        "stages": stages,
    }
    args.output.write_text(json.dumps(draft, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"draft": args.output.name, "stages": len(stages)}, sort_keys=True))


if __name__ == "__main__":
    main()
