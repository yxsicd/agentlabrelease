#!/usr/bin/env python3
"""Execute baseline/reference/wrong variants with the independent multi-repo oracle."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def tree_digest(root: Path):
    value = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        value.update(path.relative_to(root).as_posix().encode())
        value.update(b"\0")
        value.update(path.read_bytes())
        value.update(b"\0")
    return value.hexdigest()


def replace(path: Path, before: str, after: str):
    body = path.read_text()
    if body.count(before) != 1:
        raise RuntimeError(f"mutation anchor is not unique in {path}")
    path.write_text(body.replace(before, after))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--source-set-sha256", required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    variants_root = args.output / "variants"
    variants_root.mkdir()
    variants = {}
    for name, source in (("baseline", args.baseline), ("reference", args.reference)):
        target = variants_root / name
        shutil.copytree(source, target)
        variants[name] = target
    hardcoded = variants_root / "hardcoded-premium"
    shutil.copytree(args.reference, hardcoded)
    replace(
        hardcoded / "service/src/reservation.ts",
        "const policy = policyFor(tier);",
        "const policy = {...policyFor(tier), maxAttempts: 3};",
    )
    variants["hardcoded-premium"] = hardcoded
    stale = variants_root / "stale-consumer"
    shutil.copytree(args.reference, stale)
    shutil.copyfile(args.baseline / "app/src/checkout.ts", stale / "app/src/checkout.ts")
    variants["stale-consumer"] = stale

    oracle = Path(__file__).with_name("oracle.mjs")
    results = {}
    for name, root in variants.items():
        stages = {}
        for stage in ("turn-1", "turn-2"):
            process = subprocess.run(
                ["node", "--experimental-vm-modules", str(oracle), str(root), stage],
                text=True,
                capture_output=True,
            )
            (args.output / f"{name}-{stage}.stdout.json").write_text(process.stdout)
            (args.output / f"{name}-{stage}.stderr.log").write_text(process.stderr)
            if process.returncode != 0:
                raise RuntimeError(f"oracle infrastructure failed for {name}/{stage}: {process.stderr}")
            receipt = json.loads(process.stdout)
            if receipt.get("schema") != "agentlab.multi_repo_oracle_receipt.v1":
                raise RuntimeError("unexpected oracle receipt schema")
            stages[stage] = {
                "pass": receipt["pass"],
                "receiptSha256": hashlib.sha256(process.stdout.encode()).hexdigest(),
                "checkCount": len(receipt["checks"]),
                "checkIds": [row["id"] for row in receipt["checks"]],
            }
        results[name] = {"sourceSha256": tree_digest(root), "stages": stages}

    summary = {
        "schema": "agentlab.multi_repo_calibration.v1",
        "candidateId": args.candidate_id,
        "sourceSetSha256": args.source_set_sha256,
        "oracleSha256": hashlib.sha256(oracle.read_bytes()).hexdigest(),
        "receiptSchema": "agentlab.multi_repo_oracle_receipt.v1",
        "infrastructureAvailable": True,
        "variants": results,
        "coverage": "Executable JavaScript-compatible TypeScript module bodies through a supervisor-owned VM module linker; no Harmony compiler, UI or emulator claim.",
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
