#!/usr/bin/env python3
"""Project a frozen multi-repository case into a blind participant/evaluator cut."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


class ProjectionError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ProjectionError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectionError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def regular(path: Path, label: str) -> Path:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular non-symlink file")
    return path.resolve()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def blind_module():
    path = Path(__file__).with_name("build-blind-case-cut.py")
    spec = importlib.util.spec_from_file_location("agentlab_blind_case_cut_projection", path)
    require(spec is not None and spec.loader is not None, "blind cut builder is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project(
    *,
    case_path: Path,
    oracle_path: Path,
    reference_root: Path,
    calibration_path: Path,
    review_path: Path,
    output: Path,
    method_revision: str,
    constructed_at: str,
    source_visibility: str,
) -> dict[str, Any]:
    require(REVISION.fullmatch(method_revision) is not None, "method revision must be exact")
    require(constructed_at, "constructed-at is required")
    require(not output.exists(), f"refusing to overwrite existing output: {output}")
    case_path = regular(case_path, "evaluation case")
    oracle_path = regular(oracle_path, "Oracle")
    calibration_path = regular(calibration_path, "calibration")
    review_path = regular(review_path, "review")
    require(reference_root.is_dir() and not reference_root.is_symlink(), "reference root must be a non-symlink directory")
    reference_root = reference_root.resolve()
    case = load(case_path, "evaluation case")
    require(case.get("schema") == "agentlab.multi_repo_evaluation_case.v1", "unsupported evaluation case schema")
    require(case.get("status") == "frozen-calibrated" and case.get("automaticPromotion") is False, "case is not frozen and non-promoted")
    case_id = case.get("id")
    source_set = case.get("sourceSetSha256")
    require(isinstance(case_id, str) and case_id, "case id is required")
    require(isinstance(source_set, str) and SHA256.fullmatch(source_set), "source set is invalid")
    oracle = case.get("oracle") or {}
    require(digest(oracle_path) == oracle.get("sha256"), "Oracle digest differs from frozen case")
    sources = case.get("sources")
    allowed = case.get("allowedEdits")
    stages = case.get("stages")
    require(isinstance(sources, list) and len(sources) >= 2, "multi-repository sources are required")
    require(isinstance(allowed, list) and allowed, "allowed edit surface is required")
    require(isinstance(stages, list) and stages, "participant stages are required")
    participant_task = {
        "schema": "agentlab.multi_repo_participant_task.v1",
        "caseId": case_id,
        "title": case.get("title"),
        "sourceSetSha256": source_set,
        "sources": sources,
        "allowedEdits": allowed,
        "stages": [{"id": row.get("id"), "demand": row.get("demand")} for row in stages],
        "oracleVisibleToParticipant": False,
    }
    require(all(isinstance(row["id"], str) and isinstance(row["demand"], str) for row in participant_task["stages"]), "participant stage projection is invalid")
    with tempfile.TemporaryDirectory(prefix="agentlab-blind-projection-") as raw:
        source_root = Path(raw)
        participant_root = source_root / "participant"
        evaluator_root = source_root / "evaluator"
        participant_root.mkdir()
        evaluator_root.mkdir()
        write_json(participant_root / "task.json", participant_task)
        write_json(participant_root / "source-bindings.json", {"schema": "agentlab.multi_repo_source_bindings.v1", "sourceSetSha256": source_set, "sources": sources})
        shutil.copyfile(case_path, evaluator_root / "evaluation-case.json")
        shutil.copyfile(oracle_path, evaluator_root / "oracle.mjs")
        shutil.copyfile(calibration_path, evaluator_root / "calibration.json")
        shutil.copyfile(review_path, evaluator_root / "review.json")
        evaluator_reference = evaluator_root / "reference"
        evaluator_reference.mkdir()
        reference_files = []
        for source in sorted(reference_root.rglob("*")):
            require(not source.is_symlink(), f"reference contains symlink: {source}")
            if not source.is_file():
                continue
            relative = source.relative_to(reference_root)
            target = evaluator_reference / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            reference_files.append(target)
        require(reference_files, "reference root has no files")
        participant_files = [
            {"path": name, "role": role, "sha256": digest(participant_root / name)}
            for name, role in (("task.json", "task"), ("source-bindings.json", "source"))
        ]
        evaluator_files = [
            {"path": "evaluation-case.json", "role": "review", "sha256": digest(evaluator_root / "evaluation-case.json")},
            {"path": "oracle.mjs", "role": "oracle", "sha256": digest(evaluator_root / "oracle.mjs")},
            {"path": "calibration.json", "role": "review", "sha256": digest(evaluator_root / "calibration.json")},
            {"path": "review.json", "role": "review", "sha256": digest(evaluator_root / "review.json")},
            *[
                {"path": path.relative_to(evaluator_root).as_posix(), "role": "reference", "sha256": digest(path)}
                for path in reference_files
            ],
        ]
        source_manifest = {
            "schema": "agentlab.blind_case_source.v1",
            "cutId": f"{case_id}-blind-v1",
            "caseId": case_id,
            "methodRevision": method_revision,
            "sourceSetSha256": source_set,
            "participantFiles": participant_files,
            "evaluatorFiles": evaluator_files,
            "participantConstraints": {
                "allowedEditPaths": sorted(f"{row['repositoryId']}/{row['path']}" for row in allowed),
                "budget": {"stages": len(stages)},
                "environmentRef": "release-locked-multi-repo-assessment",
                "networkPolicy": "operator-gateway-only",
            },
            "freshness": {
                "sourceVisibility": source_visibility,
                "cutConstructedAt": constructed_at,
                "participantAccessBeforeCut": False,
                "modelTrainingExclusionKnown": False,
                "contaminationReview": "review-required",
            },
        }
        write_json(source_root / "case-source.json", source_manifest)
        return blind_module().build_cut(source_root, output.resolve())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--method-revision", required=True)
    parser.add_argument("--constructed-at", required=True)
    parser.add_argument("--source-visibility", choices=("private-maintenance", "held-out-public-revision"), default="held-out-public-revision")
    args = parser.parse_args()
    try:
        receipt = project(
            case_path=args.case,
            oracle_path=args.oracle,
            reference_root=args.reference_root,
            calibration_path=args.calibration,
            review_path=args.review,
            output=args.output,
            method_revision=args.method_revision,
            constructed_at=args.constructed_at,
            source_visibility=args.source_visibility,
        )
    except (ProjectionError, OSError, ValueError) as error:
        print(f"multi-repository blind cut invalid: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "cutId": receipt["cutId"], "caseId": receipt["caseId"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
