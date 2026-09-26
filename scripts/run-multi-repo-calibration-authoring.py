#!/usr/bin/env python3
"""Run and verify a replaceable evaluator that authors a calibration draft."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

from api_call_localization import localization_summary, validate_reviewed_localization


ROOT = Path(__file__).resolve().parents[1]
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
RECEIPT_SCHEMA = "agentlab.multi_repo_calibration_authoring_receipt.v1"


class AuthoringError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise AuthoringError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuthoringError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), f"evidence must be a regular file: {path}")
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot load {name}")
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


CONSTRUCTION = module("agentlab_construction_contract", ROOT / "scripts/multi-repo-construction-contract.py")
CALIBRATION = module("agentlab_calibration_bundle", ROOT / "scripts/multi-repo-calibration-bundle.py")


def write(path: Path, value: dict[str, Any]) -> None:
    require(not path.exists(), f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def copy_regular(source: Path, target: Path, label: str) -> None:
    require(source.is_file() and not source.is_symlink(), f"{label} must be a regular file")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def localization_paths(args: argparse.Namespace) -> tuple[Path | None, ...]:
    return (
        args.localization,
        args.localization_proposal,
        args.localization_review,
        args.semantic_packet,
        args.semantic_decision,
        args.semantic_gate,
    )


def git_show(root: Path, revision: str, relative: str) -> bytes:
    process = subprocess.run(
        ["git", "-C", str(root), "show", f"{revision}:{relative}"],
        capture_output=True,
    )
    require(process.returncode == 0, f"cannot read pinned source {revision}:{relative}")
    return process.stdout


def source_rows(
    manifest: dict[str, Any],
    difficulty: dict[str, Any],
    candidate: dict[str, Any],
    localization: dict[str, Any] | None,
    workspace: Path,
) -> tuple[list[dict[str, Any]], set[tuple[str, str]]]:
    repositories = {}
    identities = []
    for row in manifest.get("repositories") or []:
        repository_id = row.get("id")
        revision = row.get("revision")
        root = Path(row.get("root", ""))
        require(isinstance(repository_id, str) and TOKEN.fullmatch(repository_id), "manifest repository id is invalid")
        require(isinstance(revision, str) and REVISION.fullmatch(revision), "manifest revision is not exact")
        require(root.is_dir() and not root.is_symlink(), "manifest repository root is invalid")
        require(repository_id not in repositories, "manifest repository id is duplicated")
        repositories[repository_id] = {"root": root, "revision": revision, "repository": row.get("repository")}
        identities.append({"id": repository_id, "repository": row.get("repository"), "revision": revision})
    require(
        sorted(identities, key=lambda row: row["id"])
        == sorted(difficulty.get("sources") or [], key=lambda row: row["id"]),
        "manifest source identities differ from difficulty evidence",
    )
    if localization is None:
        paths = [
            {"repositoryId": row.get("repositoryId"), "path": row.get("path"), "suggestedRole": "candidate-affected"}
            for row in candidate.get("affectedFiles") or []
        ]
    else:
        paths = [
            {"repositoryId": row["repositoryId"], "path": row["path"], "suggestedRole": "editable"}
            for row in localization["editablePaths"]
        ] + [
            {"repositoryId": row["repositoryId"], "path": row["path"], "suggestedRole": "context"}
            for row in localization["contextPaths"]
        ]
    keys: set[tuple[str, str]] = set()
    rows = []
    for row in sorted(paths, key=lambda value: (value["repositoryId"], value["path"])):
        repository_id = row["repositoryId"]
        relative = row["path"]
        require(repository_id in repositories and isinstance(relative, str) and relative, "authoring source identity is invalid")
        require("\\" not in relative and not relative.startswith("/") and all(part not in ("", ".", "..") for part in relative.split("/")), "authoring source path is unsafe")
        key = (repository_id, relative)
        require(key not in keys, "authoring source path is duplicated")
        keys.add(key)
        source = repositories[repository_id]
        raw = git_show(source["root"], source["revision"], relative)
        target = workspace / "sources" / repository_id / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        rows.append({
            "repositoryId": repository_id,
            "repository": source["repository"],
            "revision": source["revision"],
            "path": relative,
            "workspacePath": target.relative_to(workspace).as_posix(),
            "suggestedRole": row["suggestedRole"],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        })
    require(len({row["repositoryId"] for row in rows}) >= 2, "authoring source does not span repositories")
    return rows, keys


def relevant_facts(facts_path: Path, keys: set[tuple[str, str]], output: Path) -> tuple[int, str]:
    rows = []
    for line in facts_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        require(isinstance(row, dict), "program fact must be an object")
        identities = {
            (row.get("repositoryId"), row.get("path")),
            (row.get("sourceRepositoryId"), row.get("sourcePath")),
            (row.get("targetRepositoryId"), row.get("targetPath")),
        }
        if identities.intersection(keys):
            rows.append(row)
    rows.sort(key=lambda row: row.get("id", ""))
    output.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    return len(rows), digest(output)


def authority_paths(root: Path) -> tuple[Path, Path, tuple[Path | None, ...]]:
    authority = root / "authority"
    optional = tuple(
        (authority / name if (authority / name).is_file() else None)
        for name in (
            "localization.json", "localization-proposal.json", "localization-review.json",
            "semantic-packet.json", "semantic-decision.json", "semantic-gate.json",
        )
    )
    return authority / "candidate-selection.json", authority / "difficulty.json", optional


def validate_output(root: Path) -> dict[str, Any]:
    receipt_path = root / "authoring-receipt.json"
    receipt = load(receipt_path, "calibration authoring receipt")
    require(receipt.get("schema") == RECEIPT_SCHEMA, "unsupported calibration authoring receipt")
    require(receipt.get("status") == "review-required", "calibration authoring status differs")
    require(receipt.get("automaticPromotion") is False, "calibration authoring can auto-promote")
    selection, difficulty, localization = authority_paths(root)
    require(receipt.get("selectionSha256") == digest(selection), "calibration authoring selection differs")
    require(receipt.get("difficultyEvidenceSha256") == digest(difficulty), "calibration authoring difficulty differs")
    selected, candidate = CONSTRUCTION.selected_candidate(selection, difficulty)
    surface = root / "draft/source-surface.json"
    oracle = root / "draft/oracle-contract.json"
    descriptor = root / "draft/bundle/calibration-bundle.json"
    proposal = CONSTRUCTION.propose(selection, difficulty, surface, oracle, localization)
    CALIBRATION.validate_draft(descriptor.parent, descriptor, proposal["oracleContract"])
    proposal_path = root / "construction-contract-proposal.json"
    require(load(proposal_path, "authored construction proposal") == proposal, "authored construction proposal differs")
    draft_files = CALIBRATION.complete_file_manifest(root / "draft")
    require(receipt.get("draftFiles") == draft_files, "calibration authoring draft manifest differs")
    require(receipt.get("draftManifestSha256") == CALIBRATION.manifest_digest(draft_files), "calibration authoring draft digest differs")
    require(receipt.get("constructionProposalSha256") == digest(proposal_path), "calibration authoring construction proposal differs")
    require(receipt.get("candidateId") == proposal["candidateId"], "calibration authoring candidate differs")
    require(receipt.get("sourceSetSha256") == proposal["sourceSetSha256"], "calibration authoring source set differs")
    request_path = root / "workspace/authoring-request.json"
    request = load(request_path, "calibration authoring request")
    require(receipt.get("requestSha256") == digest(request_path), "calibration authoring request differs")
    require(
        request.get("schema") == "agentlab.multi_repo_calibration_authoring_request.v1"
        and request.get("automaticPromotion") is False,
        "unsupported calibration authoring request",
    )
    require(request.get("candidateId") == proposal["candidateId"], "calibration authoring request candidate differs")
    require(request.get("candidateSha256") == selected["candidateSha256"], "calibration authoring request candidate bytes differ")
    require(request.get("sourceSetSha256") == selected["sourceSetSha256"], "calibration authoring request source set differs")
    require(request.get("candidate") == candidate, "calibration authoring request candidate object differs")
    require(request.get("localization") == proposal.get("localization"), "calibration authoring request localization differs")
    source_files = receipt.get("sourceFiles")
    require(isinstance(source_files, list) and source_files and request.get("sources") == source_files, "calibration authoring request sources differ")
    facts_path = root / "workspace/relevant-facts.jsonl"
    require(receipt.get("factsSha256") == digest(facts_path), "calibration authoring facts differ")
    fact_count = sum(1 for line in facts_path.read_text(encoding="utf-8").splitlines() if line.strip())
    require(request.get("factCount") == fact_count, "calibration authoring fact count differs")
    for row in source_files:
        relative = Path(row.get("workspacePath", ""))
        require(not relative.is_absolute() and all(part not in ("", ".", "..") for part in relative.parts), "retained authoring source path is unsafe")
        path = root / "workspace" / relative
        require(path.is_file() and not path.is_symlink(), "retained authoring source file is absent")
        require(digest(path) == row.get("sha256") and path.stat().st_size == row.get("bytes"), "retained authoring source bytes differ")
    participant = receipt.get("participant") or {}
    participant_path = root / "authority/participant.py"
    require(digest(participant_path) == participant.get("sha256"), "calibration authoring participant differs")
    require(REVISION.fullmatch(participant.get("methodRevision", "")) is not None, "calibration authoring method revision is invalid")
    evidence_files = CALIBRATION.complete_file_manifest(root / "participant-evidence")
    require(participant.get("evidenceFiles") == evidence_files, "calibration authoring participant evidence differs")
    require(participant.get("evidenceManifestSha256") == CALIBRATION.manifest_digest(evidence_files), "calibration authoring participant evidence digest differs")
    return receipt


def run(args: argparse.Namespace) -> dict[str, Any]:
    require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
    require(isinstance(args.participant_id, str) and TOKEN.fullmatch(args.participant_id), "participant id is invalid")
    require(REVISION.fullmatch(args.method_revision) is not None, "method revision must be exact")
    selection, candidate = CONSTRUCTION.selected_candidate(args.selection, args.difficulty)
    difficulty = load(args.difficulty, "difficulty evidence")
    manifest = load(args.manifest, "multi-repository manifest")
    require(manifest.get("schema") == "agentlab.multi_repo_manifest.v1", "unsupported multi-repository manifest")
    loc_paths = localization_paths(args)
    localized = None
    localization_lineage = None
    if candidate.get("relationType") == "shared-external-api-call-contract":
        require(all(loc_paths), "API-call authoring requires reviewed localization")
        localized = validate_reviewed_localization(
            *loc_paths,
            candidate_id=selection["candidateId"],
            source_set_sha256=selection["sourceSetSha256"],
            candidate_sha256=selection["candidateSha256"],
        )
        localization_lineage = localization_summary(loc_paths[0], loc_paths[1], loc_paths[2], localized)
    else:
        require(not any(loc_paths), "localization is valid only for an API-call candidate")

    args.output.mkdir(parents=True)
    workspace = args.output / "workspace"
    workspace.mkdir()
    evidence = args.output / "participant-evidence"
    evidence.mkdir()
    rows, keys = source_rows(manifest, difficulty, candidate, localization_lineage, workspace)
    fact_count, fact_sha = relevant_facts(args.facts, keys, workspace / "relevant-facts.jsonl")
    request = {
        "schema": "agentlab.multi_repo_calibration_authoring_request.v1",
        "candidateId": selection["candidateId"],
        "candidateSha256": selection["candidateSha256"],
        "sourceSetSha256": selection["sourceSetSha256"],
        "candidate": candidate,
        "sources": rows,
        "factsPath": "relevant-facts.jsonl",
        "factCount": fact_count,
        "localization": localization_lineage,
        "requiredOutputs": {
            "sourceSurface": "draft/source-surface.json",
            "oracleContract": "draft/oracle-contract.json",
            "bundleDescriptor": "draft/bundle/calibration-bundle.json",
        },
        "requirements": [
            "The source surface must remain within supplied files and span at least two repositories.",
            "The Oracle digest must match the authored Oracle executable exactly.",
            "Baseline must fail, reference and an alternative-valid solution must pass, and a meaningful wrong variant must pass an earlier stage then fail later.",
            "All executable and solution bytes are review-required and cannot promote a case.",
        ],
        "automaticPromotion": False,
    }
    write(workspace / "authoring-request.json", request)
    participant = args.participant.resolve()
    require(participant.is_file() and not participant.is_symlink(), "authoring participant is absent")
    command = [sys.executable, str(participant), "--request", "authoring-request.json", "--output", "draft"]
    write(evidence / "command.json", {
        "participantId": args.participant_id,
        "participantSha256": digest(participant),
        "argv": ["python3", "<participant>", "--request", "authoring-request.json", "--output", "draft"],
    })
    environment = {
        key: os.environ[key]
        for key in (
            "PATH", "LANG", "LC_ALL", "TMPDIR", "AGENTLAB_LM_GATEWAY_URL",
            "AGENTLAB_LM_GATEWAY_KEY", "AGENTLAB_MODEL", "AGENTLAB_PROVIDER_ROUTE", "AGENTLAB_PI_BINARY",
        )
        if key in os.environ
    }
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        process = subprocess.run(command, cwd=workspace, env=environment, capture_output=True, timeout=900)
        timed_out = False
        stdout, stderr, exit_code = process.stdout, process.stderr, process.returncode
    except subprocess.TimeoutExpired as error:
        timed_out = True
        stdout, stderr, exit_code = error.stdout or b"", error.stderr or b"", None
    (evidence / "stdout.log").write_bytes(stdout)
    (evidence / "stderr.log").write_bytes(stderr)
    write(evidence / "lifecycle.json", {
        "schema": "agentlab.calibration_authoring_participant_lifecycle.v1",
        "startedAt": started_at,
        "endedAt": datetime.now(timezone.utc).isoformat(),
        "durationMs": round((time.monotonic() - started) * 1000),
        "exitCode": exit_code,
        "timedOut": timed_out,
        "draftPresent": (workspace / "draft").is_dir(),
    })
    model_evidence = workspace / "participant-evidence"
    if model_evidence.is_dir():
        shutil.copytree(model_evidence, evidence / "model")
    require(not timed_out and exit_code == 0, "calibration authoring participant failed; inspect retained evidence")
    for row in rows:
        path = workspace / row["workspacePath"]
        require(digest(path) == row["sha256"] and path.stat().st_size == row["bytes"], "authoring participant changed source evidence")
    draft = workspace / "draft"
    surface = draft / "source-surface.json"
    oracle = draft / "oracle-contract.json"
    descriptor = draft / "bundle/calibration-bundle.json"
    proposal = CONSTRUCTION.propose(args.selection, args.difficulty, surface, oracle, loc_paths)
    CALIBRATION.validate_draft(descriptor.parent, descriptor, proposal["oracleContract"])
    shutil.copytree(draft, args.output / "draft")
    write(args.output / "construction-contract-proposal.json", proposal)
    authority = args.output / "authority"
    copy_regular(args.selection, authority / "candidate-selection.json", "candidate selection")
    copy_regular(args.difficulty, authority / "difficulty.json", "difficulty evidence")
    copy_regular(participant, authority / "participant.py", "authoring participant")
    for path, name in zip(loc_paths, (
        "localization.json", "localization-proposal.json", "localization-review.json",
        "semantic-packet.json", "semantic-decision.json", "semantic-gate.json",
    )):
        if path is not None:
            copy_regular(path, authority / name, name)
    participant_files = CALIBRATION.complete_file_manifest(evidence)
    draft_files = CALIBRATION.complete_file_manifest(args.output / "draft")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": "review-required",
        "candidateId": selection["candidateId"],
        "candidateSha256": selection["candidateSha256"],
        "sourceSetSha256": selection["sourceSetSha256"],
        "difficultyEvidenceSha256": digest(args.difficulty),
        "selectionSha256": digest(args.selection),
        "constructionProposalSha256": digest(args.output / "construction-contract-proposal.json"),
        "requestSha256": digest(workspace / "authoring-request.json"),
        "factsSha256": fact_sha,
        "sourceFiles": rows,
        "draftFiles": draft_files,
        "draftManifestSha256": CALIBRATION.manifest_digest(draft_files),
        "participant": {
            "id": args.participant_id,
            "sha256": digest(participant),
            "methodRevision": args.method_revision,
            "evidenceFiles": participant_files,
            "evidenceManifestSha256": CALIBRATION.manifest_digest(participant_files),
        },
        "risks": [
            "machine-authored-executable-untrusted",
            "oracle-product-truth-unverified",
            "reference-correctness-unverified",
            "variant-discrimination-unverified",
        ],
        "automaticPromotion": False,
    }
    write(args.output / "authoring-receipt.json", receipt)
    return validate_output(args.output)


def add_localization(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--localization", type=Path)
    parser.add_argument("--localization-proposal", type=Path)
    parser.add_argument("--localization-review", type=Path)
    parser.add_argument("--semantic-packet", type=Path)
    parser.add_argument("--semantic-decision", type=Path)
    parser.add_argument("--semantic-gate", type=Path)


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    run_command = commands.add_parser("run")
    run_command.add_argument("--selection", type=Path, required=True)
    run_command.add_argument("--difficulty", type=Path, required=True)
    run_command.add_argument("--manifest", type=Path, required=True)
    run_command.add_argument("--facts", type=Path, required=True)
    run_command.add_argument("--participant", type=Path, required=True)
    run_command.add_argument("--participant-id", required=True)
    run_command.add_argument("--method-revision", required=True)
    run_command.add_argument("--output", type=Path, required=True)
    add_localization(run_command)
    validate_command = commands.add_parser("validate")
    validate_command.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = run(args) if args.command == "run" else validate_output(args.root)
        print(json.dumps({"ok": True, "status": receipt["status"], "candidateId": receipt["candidateId"]}, sort_keys=True))
    except (AuthoringError, CALIBRATION.BundleError, CONSTRUCTION.ContractError, OSError, ValueError) as error:
        print(f"multi-repository calibration authoring invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
