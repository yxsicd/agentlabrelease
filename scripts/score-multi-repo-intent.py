#!/usr/bin/env python3
"""Apply a deterministic pre-review quality gate to a constructed semantic intent."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


STOP = {
    "a", "an", "and", "as", "at", "be", "by", "for", "from", "in", "into",
    "is", "it", "of", "on", "or", "the", "to", "with", "without", "its",
}
FORBIDDEN = ("oracle", "reference implementation", "gold patch", "solution patch", "```", "src/")


def load(path: Path):
    return json.loads(path.read_text())


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tokens(value: str):
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 1 and token not in STOP
    }


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--construction-receipt", type=Path, required=True)
    parser.add_argument("--oracle-contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "refusing to overwrite construction quality report")
    intent = load(args.intent)
    receipt = load(args.construction_receipt)
    oracle = load(args.oracle_contract)
    require(intent.get("schema") == "agentlab.multi_repo_case_intent.v1", "unsupported intent schema")
    require(receipt.get("schema") == "agentlab.multi_repo_intent_construction_receipt.v1", "unsupported construction receipt")
    require(oracle.get("schema") == "agentlab.multi_repo_oracle_contract.v1", "unsupported Oracle contract")
    construction = intent.get("construction") or {}
    require(digest(args.construction_receipt) == construction.get("receiptSha256"), "intent construction receipt mismatch")
    require(intent.get("candidateId") == receipt.get("candidateId"), "construction candidate mismatch")
    require(intent.get("sourceSetSha256") == receipt.get("sourceSetSha256"), "construction source set mismatch")

    stages = intent.get("stages") or []
    stage_order = oracle.get("stageOrder") or []
    require([row.get("id") for row in stages] == stage_order, "intent stages differ from Oracle contract")
    checks_by_stage = {stage: [] for stage in stage_order}
    check_ids = set()
    for check in oracle.get("checks", []):
        checks_by_stage[check["stage"]].append(check)
        check_ids.add(check["id"].lower())

    stage_rows = []
    qualified = True
    demand_sets = []
    for stage in stages:
        demand = stage.get("demand", "")
        demand_tokens = tokens(demand)
        behavior_tokens = tokens(" ".join(row["behavior"] for row in checks_by_stage[stage["id"]]))
        coverage = len(demand_tokens & behavior_tokens) / max(1, len(behavior_tokens))
        forbidden_hits = [value for value in FORBIDDEN if value in demand.lower()]
        check_id_hits = [value for value in check_ids if value in demand.lower()]
        length_ok = 80 <= len(demand) <= 1200
        stage_pass = coverage >= 0.55 and length_ok and not forbidden_hits and not check_id_hits
        qualified = qualified and stage_pass
        demand_sets.append(demand_tokens)
        stage_rows.append({
            "id": stage["id"],
            "pass": stage_pass,
            "behaviorTokenCoverage": round(coverage, 6),
            "demandCharacters": len(demand),
            "lengthInRange": length_ok,
            "forbiddenHits": forbidden_hits,
            "checkIdLeaks": check_id_hits,
        })
    similarities = []
    for index in range(1, len(demand_sets)):
        left, right = demand_sets[index - 1], demand_sets[index]
        similarity = len(left & right) / max(1, len(left | right))
        later_unique = len(right - left)
        pair_pass = similarity < 0.8 and later_unique >= 3
        qualified = qualified and pair_pass
        similarities.append({
            "from": stage_order[index - 1],
            "to": stage_order[index],
            "tokenJaccard": round(similarity, 6),
            "laterUniqueTokens": later_unique,
            "pass": pair_pass,
        })

    report = {
        "schema": "agentlab.multi_repo_intent_quality.v1",
        "qualifiedForReview": qualified,
        "candidateId": intent.get("candidateId"),
        "sourceSetSha256": intent.get("sourceSetSha256"),
        "intentSha256": digest(args.intent),
        "constructionReceiptSha256": digest(args.construction_receipt),
        "oracleContractSha256": digest(args.oracle_contract),
        "stages": stage_rows,
        "stageSeparation": similarities,
        "policy": {
            "minimumBehaviorTokenCoverage": 0.55,
            "demandCharacterRange": [80, 1200],
            "maximumAdjacentTokenJaccard": 0.8,
            "minimumLaterUniqueTokens": 3,
            "automaticPromotion": False,
            "boundary": "Lexical behavior coverage and leakage preflight only; not semantic correctness or task discrimination evidence.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": qualified, "qualifiedForReview": qualified, "outputSha256": digest(args.output)}, sort_keys=True))
    if not qualified:
        sys.exit(2)


if __name__ == "__main__":
    main()
