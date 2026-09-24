#!/usr/bin/env python3
"""Build and validate physically separated participant/evaluator case bundles."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
from typing import Any


SOURCE_SCHEMA = "agentlab.blind_case_source.v1"
PARTICIPANT_SCHEMA = "agentlab.blind_case_participant_bundle.v1"
EVALUATOR_SCHEMA = "agentlab.blind_case_evaluator_bundle.v1"
RECEIPT_SCHEMA = "agentlab.blind_case_cut_receipt.v1"
DISPATCH_SCHEMA = "agentlab.blind_participant_dispatch.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[A-Za-z0-9_.:-]+")
PARTICIPANT_ROLES = {"task", "source", "context", "constraint"}
EVALUATOR_ROLES = {"oracle", "reference", "preservation", "review"}


class BlindCutError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise BlindCutError(message)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value: Any, label: str) -> str:
    require(isinstance(value, str) and value and "\\" not in value, f"{label} must be a POSIX relative path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and all(part not in ("", ".", "..") for part in path.parts), f"{label} escapes its bundle")
    require(path.as_posix() == value, f"{label} must be normalized")
    return value


def regular_file(root: Path, relative: str, label: str) -> Path:
    path = root.joinpath(*PurePosixPath(relative).parts)
    require(path.is_file() and not path.is_symlink(), f"{label} is not a regular non-symlink file")
    return path


def validate_inventory(root: Path, value: Any, roles: set[str], label: str) -> list[dict[str, Any]]:
    require(isinstance(value, list) and value, f"{label} inventory is required")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        require(isinstance(raw, dict), f"{label} inventory row {index} must be an object")
        relative = safe_relative(raw.get("path"), f"{label} path")
        require(relative not in seen, f"duplicate {label} path: {relative}")
        seen.add(relative)
        role = raw.get("role")
        require(role in roles, f"unsupported {label} role: {role}")
        expected = raw.get("sha256")
        require(isinstance(expected, str) and SHA256.fullmatch(expected), f"{label} SHA256 is required")
        path = regular_file(root, relative, f"{label} {relative}")
        actual = digest_file(path)
        require(actual == expected, f"{label} digest differs: {relative}")
        rows.append({"path": relative, "role": role, "sha256": actual, "bytes": path.stat().st_size})
    return sorted(rows, key=lambda row: row["path"])


def inventory_digest(rows: list[dict[str, Any]]) -> str:
    return digest_bytes(canonical(rows))


def load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BlindCutError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_bytes(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n")


def validate_source(source_root: Path) -> dict[str, Any]:
    require(source_root.is_dir() and not source_root.is_symlink(), "source root must be a non-symlink directory")
    source = load(source_root / "case-source.json", "case source")
    require(source.get("schema") == SOURCE_SCHEMA, "unsupported case source schema")
    for field in ("cutId", "caseId"):
        require(isinstance(source.get(field), str) and TOKEN.fullmatch(source[field]), f"{field} must be a safe token")
    require(isinstance(source.get("methodRevision"), str) and REVISION.fullmatch(source["methodRevision"]), "methodRevision must be exact")
    require(isinstance(source.get("sourceSetSha256"), str) and SHA256.fullmatch(source["sourceSetSha256"]), "sourceSetSha256 must be exact")
    participant_root = source_root / "participant"
    evaluator_root = source_root / "evaluator"
    participant = validate_inventory(participant_root, source.get("participantFiles"), PARTICIPANT_ROLES, "participant")
    evaluator = validate_inventory(evaluator_root, source.get("evaluatorFiles"), EVALUATOR_ROLES, "evaluator")
    require(sum(row["role"] == "task" for row in participant) == 1, "participant bundle requires exactly one task")
    require(sum(row["role"] == "oracle" for row in evaluator) >= 1, "evaluator bundle requires at least one Oracle")
    require(sum(row["role"] == "reference" for row in evaluator) >= 1, "evaluator bundle requires at least one reference")
    overlap = sorted({row["sha256"] for row in participant} & {row["sha256"] for row in evaluator})
    require(not overlap, "participant and evaluator bundles must not contain byte-identical files")
    freshness = source.get("freshness")
    require(isinstance(freshness, dict), "freshness declaration is required")
    require(freshness.get("sourceVisibility") in {"private-maintenance", "held-out-public-revision", "public-fixture"}, "unsupported source visibility")
    require(isinstance(freshness.get("cutConstructedAt"), str) and freshness["cutConstructedAt"], "cutConstructedAt is required")
    require(freshness.get("participantAccessBeforeCut") is False, "participant access before cut must be false")
    require(freshness.get("modelTrainingExclusionKnown") is False, "v1 cannot claim model training exclusion")
    require(freshness.get("contaminationReview") in {"not-performed", "review-required"}, "contamination review must remain pending")
    constraints = source.get("participantConstraints")
    require(isinstance(constraints, dict) and constraints, "participantConstraints are required")
    require(set(constraints) <= {"allowedEditPaths", "budget", "environmentRef", "networkPolicy"}, "participantConstraints contain unsupported fields")
    return {"source": source, "participant": participant, "evaluator": evaluator, "freshness": freshness, "constraints": constraints}


def copy_inventory(source: Path, destination: Path, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        target = destination.joinpath(*PurePosixPath(row["path"]).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(regular_file(source, row["path"], row["path"]), target)


def build_cut(source_root: Path, output_root: Path) -> dict[str, Any]:
    require(not output_root.exists(), f"refusing to overwrite existing output: {output_root}")
    validated = validate_source(source_root)
    source = validated["source"]
    temporary = output_root.parent / f".{output_root.name}.tmp-{os.getpid()}"
    require(not temporary.exists(), f"temporary output already exists: {temporary}")
    participant_root = temporary / "participant"
    evaluator_root = temporary / "evaluator"
    try:
        participant_root.mkdir(parents=True)
        evaluator_root.mkdir()
        copy_inventory(source_root / "participant", participant_root, validated["participant"])
        participant_manifest = {
            "schema": PARTICIPANT_SCHEMA,
            "cutId": source["cutId"],
            "caseId": source["caseId"],
            "methodRevision": source["methodRevision"],
            "sourceSetSha256": source["sourceSetSha256"],
            "files": validated["participant"],
            "constraints": validated["constraints"],
        }
        write_json(participant_root / "manifest.json", participant_manifest)
        participant_manifest_sha = digest_file(participant_root / "manifest.json")
        copy_inventory(source_root / "evaluator", evaluator_root, validated["evaluator"])
        evaluator_manifest = {
            "schema": EVALUATOR_SCHEMA,
            "cutId": source["cutId"],
            "caseId": source["caseId"],
            "methodRevision": source["methodRevision"],
            "sourceSetSha256": source["sourceSetSha256"],
            "participantManifestSha256": participant_manifest_sha,
            "files": validated["evaluator"],
        }
        write_json(evaluator_root / "manifest.json", evaluator_manifest)
        evaluator_manifest_sha = digest_file(evaluator_root / "manifest.json")
        held_out = validated["freshness"]["sourceVisibility"] != "public-fixture"
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "cutId": source["cutId"],
            "caseId": source["caseId"],
            "methodRevision": source["methodRevision"],
            "sourceSetSha256": source["sourceSetSha256"],
            "participantBundle": {
                "manifestSha256": participant_manifest_sha,
                "fileCount": len(validated["participant"]),
                "inventorySha256": inventory_digest(validated["participant"]),
            },
            "evaluatorBundle": {
                "manifestSha256": evaluator_manifest_sha,
                "fileCount": len(validated["evaluator"]),
                "inventorySha256": inventory_digest(validated["evaluator"]),
            },
            "boundary": {
                "physicallySeparatedRoots": True,
                "participantManifestContainsEvaluatorInventory": False,
                "byteIdenticalCrossBundleFiles": False,
                "participantMount": "participant",
                "evaluatorMount": "evaluator",
                "semanticLeakReview": "required",
            },
            "freshness": {
                **validated["freshness"],
                "declaredHeldOutAtCut": held_out,
                "heldOutEvidenceStatus": "declaration-only",
                "eligibleForBlindPilot": True,
                "eligibleForUnseenAgentDiscrimination": False,
            },
            "review": {"independent": False, "status": "required"},
            "automaticPromotion": False,
        }
        write_json(temporary / "cut-receipt.json", receipt)
        temporary.replace(output_root)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    validate_cut(output_root)
    return receipt


def exact_files(root: Path) -> set[str]:
    require(root.is_dir() and not root.is_symlink(), f"bundle root is unsafe: {root}")
    result = set()
    for path in root.rglob("*"):
        require(not path.is_symlink(), f"bundle contains symlink: {path}")
        if path.is_file():
            result.add(path.relative_to(root).as_posix())
    return result


def validate_built_inventory(root: Path, manifest: dict[str, Any], roles: set[str], label: str) -> list[dict[str, Any]]:
    rows = validate_inventory(root, manifest.get("files"), roles, label)
    expected = {"manifest.json", *(row["path"] for row in rows)}
    require(exact_files(root) == expected, f"{label} bundle contains unbound files")
    return rows


def validate_cut(output_root: Path) -> dict[str, Any]:
    require(output_root.is_dir() and not output_root.is_symlink(), "cut root must be a non-symlink directory")
    require(exact_files(output_root) == {
        "cut-receipt.json",
        *(f"participant/{path}" for path in exact_files(output_root / "participant")),
        *(f"evaluator/{path}" for path in exact_files(output_root / "evaluator")),
    }, "cut root contains files outside the two bundles and receipt")
    receipt = load(output_root / "cut-receipt.json", "cut receipt")
    participant_manifest = load(output_root / "participant/manifest.json", "participant manifest")
    evaluator_manifest = load(output_root / "evaluator/manifest.json", "evaluator manifest")
    require(receipt.get("schema") == RECEIPT_SCHEMA, "unsupported cut receipt schema")
    require(participant_manifest.get("schema") == PARTICIPANT_SCHEMA, "unsupported participant manifest schema")
    require(evaluator_manifest.get("schema") == EVALUATOR_SCHEMA, "unsupported evaluator manifest schema")
    require(set(participant_manifest) == {"schema", "cutId", "caseId", "methodRevision", "sourceSetSha256", "files", "constraints"}, "participant manifest contains evaluator or unsupported fields")
    require(set(evaluator_manifest) == {"schema", "cutId", "caseId", "methodRevision", "sourceSetSha256", "participantManifestSha256", "files"}, "evaluator manifest contains unsupported fields")
    identity = ("cutId", "caseId", "methodRevision", "sourceSetSha256")
    require(all(receipt.get(key) == participant_manifest.get(key) == evaluator_manifest.get(key) for key in identity), "bundle identity differs")
    participant = validate_built_inventory(output_root / "participant", participant_manifest, PARTICIPANT_ROLES, "participant")
    evaluator = validate_built_inventory(output_root / "evaluator", evaluator_manifest, EVALUATOR_ROLES, "evaluator")
    participant_manifest_sha = digest_file(output_root / "participant/manifest.json")
    evaluator_manifest_sha = digest_file(output_root / "evaluator/manifest.json")
    require(evaluator_manifest.get("participantManifestSha256") == participant_manifest_sha, "evaluator does not bind participant manifest")
    require((receipt.get("participantBundle") or {}).get("manifestSha256") == participant_manifest_sha, "receipt participant digest differs")
    require((receipt.get("evaluatorBundle") or {}).get("manifestSha256") == evaluator_manifest_sha, "receipt evaluator digest differs")
    require((receipt.get("participantBundle") or {}).get("inventorySha256") == inventory_digest(participant), "receipt participant inventory differs")
    require((receipt.get("evaluatorBundle") or {}).get("inventorySha256") == inventory_digest(evaluator), "receipt evaluator inventory differs")
    require(not ({row["sha256"] for row in participant} & {row["sha256"] for row in evaluator}), "cross-bundle byte overlap detected")
    boundary = receipt.get("boundary") or {}
    require(boundary.get("physicallySeparatedRoots") is True and boundary.get("semanticLeakReview") == "required", "blind boundary differs")
    require((receipt.get("freshness") or {}).get("heldOutEvidenceStatus") == "declaration-only", "held-out evidence must remain declaration-only")
    require((receipt.get("freshness") or {}).get("eligibleForUnseenAgentDiscrimination") is False, "v1 cut cannot claim unseen-Agent discrimination")
    require((receipt.get("review") or {}).get("independent") is False, "unreviewed cut cannot claim independent review")
    require(receipt.get("automaticPromotion") is False, "blind cut cannot auto-promote")
    return receipt


def stage_participant(cut_root: Path, output_root: Path, receipt_path: Path) -> dict[str, Any]:
    require(not output_root.exists(), f"refusing to overwrite existing dispatch: {output_root}")
    require(not receipt_path.exists(), f"refusing to overwrite existing dispatch receipt: {receipt_path}")
    require(output_root != receipt_path and output_root not in receipt_path.parents, "dispatch receipt must remain outside participant root")
    cut = validate_cut(cut_root)
    temporary = output_root.parent / f".{output_root.name}.tmp-{os.getpid()}"
    require(not temporary.exists(), f"temporary dispatch already exists: {temporary}")
    try:
        shutil.copytree(cut_root / "participant", temporary, symlinks=False)
        temporary.replace(output_root)
        dispatch = {
            "schema": DISPATCH_SCHEMA,
            "cutId": cut["cutId"],
            "caseId": cut["caseId"],
            "methodRevision": cut["methodRevision"],
            "sourceSetSha256": cut["sourceSetSha256"],
            "sourceCutReceiptSha256": digest_file(cut_root / "cut-receipt.json"),
            "participantManifestSha256": digest_file(output_root / "manifest.json"),
            "participantInventorySha256": cut["participantBundle"]["inventorySha256"],
            "participantFileCount": cut["participantBundle"]["fileCount"],
            "mount": {"source": str(output_root.resolve()), "target": "/agentlab/case", "readOnly": True},
            "boundary": {
                "evaluatorPathDisclosedToParticipant": False,
                "operatorReceiptOutsideParticipantRoot": True,
                "filesystemIsolationRequired": True,
                "filesystemIsolationQualified": False,
            },
            "automaticPromotion": False,
        }
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(receipt_path, dispatch)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        if output_root.exists():
            shutil.rmtree(output_root)
        if receipt_path.exists():
            receipt_path.unlink()
        raise
    validate_dispatch(output_root, receipt_path)
    return dispatch


def validate_dispatch(participant_root: Path, receipt_path: Path) -> dict[str, Any]:
    require(participant_root.is_dir() and not participant_root.is_symlink(), "participant dispatch root is unsafe")
    require(receipt_path.is_file() and not receipt_path.is_symlink(), "dispatch receipt is unsafe")
    require(participant_root not in receipt_path.resolve().parents, "dispatch receipt must not be participant-visible")
    receipt = load(receipt_path, "dispatch receipt")
    manifest = load(participant_root / "manifest.json", "participant dispatch manifest")
    require(receipt.get("schema") == DISPATCH_SCHEMA, "unsupported dispatch schema")
    require(manifest.get("schema") == PARTICIPANT_SCHEMA, "unsupported dispatch participant schema")
    require(set(manifest) == {"schema", "cutId", "caseId", "methodRevision", "sourceSetSha256", "files", "constraints"}, "dispatch participant manifest contains unsupported fields")
    require(all(receipt.get(key) == manifest.get(key) for key in ("cutId", "caseId", "methodRevision", "sourceSetSha256")), "dispatch identity differs")
    rows = validate_built_inventory(participant_root, manifest, PARTICIPANT_ROLES, "dispatch participant")
    require(receipt.get("participantManifestSha256") == digest_file(participant_root / "manifest.json"), "dispatch participant manifest digest differs")
    require(receipt.get("participantInventorySha256") == inventory_digest(rows), "dispatch participant inventory differs")
    require(receipt.get("participantFileCount") == len(rows), "dispatch participant file count differs")
    mount = receipt.get("mount") or {}
    require(mount == {"source": str(participant_root.resolve()), "target": "/agentlab/case", "readOnly": True}, "dispatch mount contract differs")
    boundary = receipt.get("boundary") or {}
    require(boundary == {
        "evaluatorPathDisclosedToParticipant": False,
        "operatorReceiptOutsideParticipantRoot": True,
        "filesystemIsolationRequired": True,
        "filesystemIsolationQualified": False,
    }, "dispatch boundary differs")
    require(receipt.get("automaticPromotion") is False, "dispatch cannot auto-promote")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--source", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--cut", type=Path, required=True)
    stage = sub.add_parser("stage-participant")
    stage.add_argument("--cut", type=Path, required=True)
    stage.add_argument("--output", type=Path, required=True)
    stage.add_argument("--receipt", type=Path, required=True)
    validate_dispatch_parser = sub.add_parser("validate-dispatch")
    validate_dispatch_parser.add_argument("--participant-root", type=Path, required=True)
    validate_dispatch_parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "build":
            value = build_cut(args.source.absolute(), args.output.absolute())
        elif args.command == "validate":
            value = validate_cut(args.cut.absolute())
        elif args.command == "stage-participant":
            value = stage_participant(args.cut.absolute(), args.output.absolute(), args.receipt.absolute())
        else:
            value = validate_dispatch(args.participant_root.absolute(), args.receipt.absolute())
    except (BlindCutError, OSError) as error:
        print(f"blind case cut invalid: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "cutId": value["cutId"], "caseId": value["caseId"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
