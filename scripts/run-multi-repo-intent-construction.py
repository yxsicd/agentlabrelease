#!/usr/bin/env python3
"""Run a replaceable construction participant against exact multi-repo evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from api_call_localization import localization_summary, validate_reviewed_localization


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


def load(path: Path):
    return json.loads(path.read_text())


def digest_bytes(value: bytes):
    return hashlib.sha256(value).hexdigest()


def digest(path: Path):
    return digest_bytes(path.read_bytes())


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git_show(root: Path, revision: str, path: str):
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{revision}:{path}"],
        capture_output=True,
    )
    require(result.returncode == 0, f"cannot read pinned source {revision}:{path}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--difficulty", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--oracle-contract", type=Path, required=True)
    parser.add_argument("--participant", type=Path, required=True)
    parser.add_argument("--participant-id", required=True)
    parser.add_argument("--localization", type=Path)
    parser.add_argument("--localization-proposal", type=Path)
    parser.add_argument("--localization-review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require(not args.output.exists(), "refusing to overwrite construction evidence")
    manifest = load(args.manifest)
    difficulty = load(args.difficulty)
    oracle = load(args.oracle_contract)
    require(manifest.get("schema") == "agentlab.multi_repo_manifest.v1", "unsupported manifest schema")
    require(difficulty.get("schema") == "agentlab.difficulty_candidates.v2", "unsupported difficulty schema")
    require(oracle.get("schema") == "agentlab.multi_repo_oracle_contract.v1", "unsupported Oracle contract schema")
    require(difficulty.get("automaticPromotion") is False, "difficulty evidence must not auto-promote")
    source_set = difficulty.get("sourceSetSha256")
    require(isinstance(source_set, str) and SHA256.fullmatch(source_set), "difficulty requires sourceSetSha256")
    candidates = {row.get("id"): row for row in difficulty.get("candidates", []) if isinstance(row, dict)}
    require(args.candidate_id in candidates, "candidate is absent from difficulty evidence")
    candidate = candidates[args.candidate_id]
    require(candidate.get("dimensionId") == "multi-repository-change-impact", "construction requires recursive multi-repository impact")
    require(candidate.get("maturityState") == "candidate", "difficulty must still be a candidate")
    require(candidate.get("affectedRepositoryCount", 0) >= 2, "candidate does not cross repositories")
    localization_paths = (
        args.localization,
        args.localization_proposal,
        args.localization_review,
    )
    localization = None
    localization_lineage = None
    if candidate.get("relationType") == "shared-external-api-call-contract":
        require(all(localization_paths), "shared external API-call construction requires reviewed localization evidence")
        localization = validate_reviewed_localization(
            args.localization,
            args.localization_proposal,
            args.localization_review,
            candidate_id=args.candidate_id,
            source_set_sha256=source_set,
        )
        localization_lineage = localization_summary(
            args.localization,
            args.localization_proposal,
            args.localization_review,
            localization,
        )
    else:
        require(not any(localization_paths), "localization evidence is only valid for shared external API-call candidates")

    repositories = {}
    canonical_sources = {}
    for row in manifest.get("repositories", []):
        repository_id = row.get("id")
        revision = row.get("revision")
        require(isinstance(repository_id, str) and repository_id, "manifest repository id is required")
        require(isinstance(revision, str) and REVISION.fullmatch(revision), "manifest revision must be exact")
        require(repository_id not in repositories, "duplicate manifest repository id")
        repositories[repository_id] = {
            "root": Path(row.get("root", "")),
            "revision": revision,
            "repository": row.get("repository"),
        }
        canonical_sources[repository_id] = {"id": repository_id, "repository": row.get("repository"), "revision": revision}
    require(sorted(canonical_sources.values(), key=lambda row: row["id"]) == sorted(difficulty.get("sources", []), key=lambda row: row["id"]), "manifest sources differ from difficulty evidence")

    checks = oracle.get("checks")
    require(isinstance(checks, list) and len(checks) >= 2, "Oracle contract requires checks")
    stage_order = oracle.get("stageOrder")
    require(isinstance(stage_order, list) and len(stage_order) >= 2 and len(stage_order) == len(set(stage_order)), "Oracle contract requires unique stage order")
    expected_checks = {stage: [] for stage in stage_order}
    for check in checks:
        require(isinstance(check, dict), "Oracle check must be an object")
        require(check.get("stage") in expected_checks, "Oracle check names unknown stage")
        require(isinstance(check.get("id"), str) and check["id"], "Oracle check id is required")
        require(isinstance(check.get("behavior"), str) and check["behavior"], "Oracle check behavior is required")
        expected_checks[check["stage"]].append(check["id"])
    require(len({value for values in expected_checks.values() for value in values}) == len(checks), "Oracle check ids must be unique")
    require(all(expected_checks.values()), "each stage requires Oracle checks")
    oracle_sha256 = oracle.get("oracleSha256")
    require(isinstance(oracle_sha256, str) and SHA256.fullmatch(oracle_sha256), "Oracle executable digest is required")
    expectations = oracle.get("calibrationExpectations")
    require(isinstance(expectations, dict) and {"baseline", "reference"}.issubset(expectations), "Oracle contract requires calibration expectations")
    require(all(isinstance(value, dict) and set(value) == set(stage_order) for value in expectations.values()), "calibration expectations must cover every stage")

    workspace = args.output / "workspace"
    sources_root = workspace / "sources"
    evidence = args.output / "evidence"
    workspace.mkdir(parents=True)
    evidence.mkdir()
    if localization is None:
        materialized = [
            {**row, "role": "editable", "editable": True}
            for row in candidate.get("affectedFiles", [])
        ]
    else:
        materialized = [
            {**row, "dependencyDepth": None, "role": "editable", "editable": True}
            for row in localization["editablePaths"]
        ] + [
            {**row, "dependencyDepth": None, "role": "context", "editable": False}
            for row in localization["contextPaths"]
        ]
    affected = sorted(materialized, key=lambda row: (row.get("repositoryId", ""), row.get("path", "")))
    source_rows = []
    affected_keys = set()
    for row in affected:
        repository_id = row.get("repositoryId")
        path = row.get("path")
        require(repository_id in repositories and isinstance(path, str) and path, "affected source identity is invalid")
        key = (repository_id, path)
        require(key not in affected_keys, "duplicate affected source identity")
        affected_keys.add(key)
        raw = git_show(repositories[repository_id]["root"], repositories[repository_id]["revision"], path)
        if localization is not None:
            require(digest_bytes(raw) == row.get("sha256"), "localized source bytes differ from reviewed evidence")
            require(len(raw) == row.get("byteLength"), "localized source length differs from reviewed evidence")
            blob = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repositories[repository_id]["root"]),
                    "rev-parse",
                    f"{repositories[repository_id]['revision']}:{path}",
                ],
                capture_output=True,
                text=True,
            )
            require(blob.returncode == 0, "cannot resolve localized Git blob identity")
            require(blob.stdout.strip() == row.get("gitBlobOid"), "localized Git blob differs from reviewed evidence")
            require(
                row.get("sourceIdentity")
                == f"git:{repositories[repository_id]['repository']}@{repositories[repository_id]['revision']}",
                "localized source identity differs from the manifest",
            )
        target = sources_root / repository_id / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        source_rows.append({
            "repositoryId": repository_id,
            "path": path,
            "dependencyDepth": row.get("dependencyDepth"),
            "role": row.get("role"),
            "editable": row.get("editable"),
            "workspacePath": target.relative_to(workspace).as_posix(),
            "sha256": digest_bytes(raw),
            "byteLength": len(raw),
        })

    relevant_facts = []
    evidence_ids = set(candidate.get("evidenceIds", []))
    for line in args.facts.read_text().splitlines():
        if not line.strip():
            continue
        fact = json.loads(line)
        source_key = (fact.get("repositoryId"), fact.get("path"))
        edge_key = (fact.get("sourceRepositoryId"), fact.get("sourcePath"))
        target_key = (fact.get("targetRepositoryId"), fact.get("targetPath"))
        if source_key in affected_keys or edge_key in affected_keys or target_key in affected_keys or fact.get("id") in evidence_ids:
            relevant_facts.append(fact)
    relevant_facts.sort(key=lambda row: row.get("id", ""))
    facts_path = workspace / "relevant-facts.jsonl"
    facts_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in relevant_facts))

    request = {
        "schema": "agentlab.multi_repo_intent_construction_request.v1",
        "candidateId": args.candidate_id,
        "sourceSetSha256": source_set,
        "candidate": candidate,
        "localization": None if localization is None else {
            "status": localization["status"],
            "hypothesis": localization["hypothesis"],
            "apiContract": localization["apiContract"],
            "targetCallSites": localization["targetCallSites"],
            "referenceCallSites": localization["referenceCallSites"],
            "editablePaths": localization_lineage["editablePaths"],
            "contextPaths": localization_lineage["contextPaths"],
            "proposedChecks": localization["proposedChecks"],
            "boundary": "Reviewed localization authorizes intent construction only; it is not a reference implementation or qualified Oracle.",
        },
        "sources": source_rows,
        "factsPath": facts_path.relative_to(workspace).as_posix(),
        "factCount": len(relevant_facts),
        "oracleContract": {
            "stageOrder": stage_order,
            "checks": checks,
            "assessmentBoundary": oracle.get("assessmentBoundary"),
        },
        "outputContract": {
            "schema": "agentlab.multi_repo_case_intent_draft.v1",
            "requiredFields": ["caseId", "title", "stages"],
            "stageFields": ["id", "demand", "checkIds"],
            "notes": "Use every supplied check exactly once in its fixed stage. Do not include reference code or implementation guidance.",
        },
        "automaticPromotion": False,
    }
    request_path = workspace / "construction-request.json"
    write_json(request_path, request)
    draft_path = workspace / "intent-draft.json"
    participant = args.participant.resolve()
    require(participant.is_file(), "participant executable is absent")
    participant_sha256 = digest(participant)
    command = [sys.executable, str(participant), "--request", request_path.name, "--output", draft_path.name]
    write_json(evidence / "command.json", {
        "participantId": args.participant_id,
        "executableSha256": participant_sha256,
        "argv": ["python3", "<participant>", "--request", request_path.name, "--output", draft_path.name],
    })
    environment = {
        key: os.environ[key]
        for key in (
            "PATH", "LANG", "LC_ALL", "TMPDIR", "AGENTLAB_LM_GATEWAY_URL",
            "AGENTLAB_LM_GATEWAY_KEY", "AGENTLAB_MODEL", "AGENTLAB_PROVIDER_ROUTE",
            "AGENTLAB_PI_BINARY",
        )
        if key in os.environ
    }
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    timed_out = False
    try:
        process = subprocess.run(command, cwd=workspace, env=environment, capture_output=True, timeout=420)
        exit_code = process.returncode
        stdout = process.stdout
        stderr = process.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        exit_code = None
        stdout = error.stdout or b""
        stderr = error.stderr or b""
    (evidence / "stdout.log").write_bytes(stdout)
    (evidence / "stderr.log").write_bytes(stderr)
    write_json(evidence / "lifecycle.json", {
        "schema": "agentlab.construction_participant_lifecycle.v1",
        "startedAt": started_at,
        "endedAt": datetime.now(timezone.utc).isoformat(),
        "durationMs": round((time.monotonic() - started) * 1000),
        "exitCode": exit_code,
        "timedOut": timed_out,
        "draftPresent": draft_path.is_file(),
    })
    require(not timed_out, "construction participant timed out; inspect retained evidence")
    require(exit_code == 0, "construction participant failed; inspect retained evidence")
    require(draft_path.is_file(), "construction participant did not write intent draft")
    draft = load(draft_path)
    require(draft.get("schema") == "agentlab.multi_repo_case_intent_draft.v1", "unsupported construction draft schema")
    require(draft.get("candidateId") == args.candidate_id, "construction draft candidate mismatch")
    require(draft.get("sourceSetSha256") == source_set, "construction draft source set mismatch")
    require(isinstance(draft.get("caseId"), str) and draft["caseId"], "construction draft caseId is required")
    require(isinstance(draft.get("title"), str) and draft["title"], "construction draft title is required")
    stages = draft.get("stages")
    require(isinstance(stages, list) and [row.get("id") for row in stages] == stage_order, "construction stages must follow Oracle contract order")
    for stage in stages:
        require(isinstance(stage.get("demand"), str) and stage["demand"], "construction stage demand is required")
        require(stage.get("checkIds") == expected_checks[stage["id"]], "construction checks differ from Oracle contract")

    participant_evidence_root = workspace / "participant-evidence"
    participant_evidence_files = []
    if participant_evidence_root.is_dir():
        for path in sorted(item for item in participant_evidence_root.rglob("*") if item.is_file()):
            participant_evidence_files.append({
                "path": path.relative_to(participant_evidence_root).as_posix(),
                "sha256": digest(path),
                "byteLength": path.stat().st_size,
            })
    participant_evidence_manifest = json.dumps(
        participant_evidence_files, sort_keys=True, separators=(",", ":")
    ).encode()

    receipt = {
        "schema": "agentlab.multi_repo_intent_construction_receipt.v1",
        "status": "candidate-unverified",
        "participantId": args.participant_id,
        "participantSha256": participant_sha256,
        "sourceSetSha256": source_set,
        "candidateId": args.candidate_id,
        "requestSha256": digest(request_path),
        "draftSha256": digest(draft_path),
        "factsSha256": digest(facts_path),
        "oracleContractSha256": digest(args.oracle_contract),
        "participantEvidenceSha256": digest_bytes(participant_evidence_manifest),
        "participantEvidenceFiles": participant_evidence_files,
        "sourceFiles": source_rows,
        "localization": localization_lineage,
        "semanticKnowledgeVerified": False,
        "automaticPromotion": False,
    }
    receipt_path = args.output / "construction-receipt.json"
    write_json(receipt_path, receipt)
    intent = {
        "schema": "agentlab.multi_repo_case_intent.v1",
        "caseId": draft["caseId"],
        "candidateId": args.candidate_id,
        "sourceSetSha256": source_set,
        "title": draft["title"],
        "stages": stages,
        "oracle": {
            "sha256": oracle_sha256,
            "authority": "independent-executable-oracle",
            "receiptSchema": oracle.get("receiptSchema"),
        },
        "calibrationExpectations": expectations,
        "construction": {
            "status": "candidate-unverified",
            "participantId": args.participant_id,
            "receiptSha256": digest(receipt_path),
            "semanticKnowledgeVerified": False,
            "automaticPromotion": False,
            "localization": localization_lineage,
        },
    }
    intent_path = args.output / "intent.json"
    write_json(intent_path, intent)
    print(json.dumps({"ok": True, "status": "candidate-unverified", "intentSha256": digest(intent_path)}, sort_keys=True))


if __name__ == "__main__":
    main()
