#!/usr/bin/env python3
"""Deterministic protocol fixture for calibration-authoring tests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    if request.get("schema") != "agentlab.multi_repo_calibration_authoring_request.v1":
        raise ValueError("unsupported authoring request")
    sources = request["sources"]
    localization = request.get("localization")
    if localization is None:
        repositories = []
        for row in sources:
            if row["repositoryId"] not in repositories:
                repositories.append(row["repositoryId"])
        if len(repositories) < 2:
            raise ValueError("fixture requires multiple repositories")
        editable = next(row for row in sources if row["repositoryId"] == repositories[0])
        context = next(row for row in sources if row["repositoryId"] == repositories[1])
        editable_rows = [{"repositoryId": editable["repositoryId"], "path": editable["path"]}]
        context_rows = [{"repositoryId": context["repositoryId"], "path": context["path"]}]
    else:
        editable_rows = [
            {"repositoryId": row["repositoryId"], "path": row["path"]}
            for row in localization["editablePaths"]
        ]
        context_rows = [
            {"repositoryId": row["repositoryId"], "path": row["path"]}
            for row in localization["contextPaths"]
        ]
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "source-surface.json").write_text(json.dumps({
        "schema": "agentlab.multi_repo_construction_surface.v1",
        "editablePaths": editable_rows,
        "contextPaths": context_rows,
        "automaticPromotion": False,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    fixture = Path(__file__).resolve().parent
    shutil.copyfile(fixture / "oracle-contract.json", args.output / "oracle-contract.json")
    bundle = args.output / "bundle"
    bundle.mkdir()
    for name in ("calibrate.py", "oracle.mjs", "calibration-bundle.json"):
        shutil.copyfile(fixture / name, bundle / name)
    shutil.copytree(fixture / "reference", bundle / "reference")
    shutil.copytree(fixture / "alternatives", bundle / "alternatives")


if __name__ == "__main__":
    main()
