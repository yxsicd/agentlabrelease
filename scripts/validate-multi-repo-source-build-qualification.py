#!/usr/bin/env python3
"""Validate an exact, non-promoting source-build qualification."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "agentlab.multi_repo_source_build_qualification.v1"
PACKET_SCHEMA = "agentlab.multi_repo_candidate_review_packet.v5"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
PEER = re.compile(r"lgw_[0-9a-f]{32}")
ROOT_STATUSES = {"passed", "failed"}


class QualificationError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise QualificationError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QualificationError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def packet_boundaries(packet: dict[str, Any]) -> tuple[dict[str, str], set[tuple[str, str]]]:
    revisions: dict[str, str] = {}
    boundaries: set[tuple[str, str]] = set()
    evidence = packet.get("domainFactEvidence")
    require(isinstance(evidence, list) and evidence, "packet domain fact evidence is absent")
    for fact in evidence:
        require(isinstance(fact, dict), "packet domain fact is invalid")
        repository_id = fact.get("repositoryId")
        source_identity = fact.get("sourceIdentity")
        require(isinstance(repository_id, str) and repository_id, "packet repository id is invalid")
        require(isinstance(source_identity, str) and "@" in source_identity, "packet source identity is invalid")
        revision = source_identity.rsplit("@", 1)[-1]
        require(REVISION.fullmatch(revision), "packet source revision is invalid")
        previous = revisions.setdefault(repository_id, revision)
        require(previous == revision, "packet repository revisions differ")
        candidates = fact.get("projectBoundaryCandidates")
        require(isinstance(candidates, list) and candidates, "packet project boundary candidates are absent")
        for candidate in candidates:
            require(isinstance(candidate, dict), "packet project boundary candidate is invalid")
            path = candidate.get("path")
            require(isinstance(path, str) and path, "packet project boundary path is invalid")
            boundaries.add((repository_id, path))
    return revisions, boundaries


def validate(receipt: dict[str, Any], packet: dict[str, Any], packet_sha256: str) -> None:
    require(receipt.get("schema") == SCHEMA, "unsupported qualification schema")
    require(packet.get("schema") == PACKET_SCHEMA, "unsupported candidate review packet")
    require(receipt.get("candidateId") == packet.get("candidateId"), "qualification candidate differs")
    require(receipt.get("sourceSetSha256") == packet.get("sourceSetSha256"), "qualification source set differs")
    require(receipt.get("reviewPacketSha256") == packet_sha256, "qualification packet digest differs")
    require(receipt.get("status") == "partial-build-qualified-review-required", "qualification status differs")
    require(receipt.get("automaticPromotion") is False, "qualification can auto-promote")
    require(receipt.get("allowsCaseContract") is False, "qualification can authorize a case contract")

    environment = receipt.get("environment")
    require(isinstance(environment, dict), "qualification environment is absent")
    target = environment.get("targetPeerId")
    require(isinstance(target, str) and PEER.fullmatch(target), "qualification target peer is invalid")
    require(environment.get("intendedPeerId") == target, "qualification intended peer differs")
    require(environment.get("routeDecision") == "peer_direct", "qualification route was not peer direct")

    revisions, boundaries = packet_boundaries(packet)
    roots = receipt.get("roots")
    require(isinstance(roots, list) and roots, "qualification roots are absent")
    root_ids: set[str] = set()
    statuses: list[str] = []
    for root in roots:
        require(isinstance(root, dict), "qualification root is invalid")
        root_id = root.get("id")
        require(isinstance(root_id, str) and root_id and root_id not in root_ids, "qualification root id is invalid")
        root_ids.add(root_id)
        repository_id = root.get("repositoryId")
        candidate_path = root.get("candidatePath")
        require((repository_id, candidate_path) in boundaries, "qualification root is not packet-bound")
        require(root.get("sourceRevision") == revisions[repository_id], "qualification source revision differs")
        require(root.get("trackedSourceStatus") == "clean", "qualification changed tracked source")
        status = root.get("status")
        require(status in ROOT_STATUSES, "qualification root status is invalid")
        statuses.append(status)
        install = root.get("install")
        build = root.get("build")
        require(isinstance(install, dict) and isinstance(build, dict), "qualification command evidence is absent")
        for phase_name, phase in (("install", install), ("build", build)):
            require(isinstance(phase.get("command"), list) and phase["command"], f"{phase_name} command is invalid")
            require(isinstance(phase.get("exitCode"), int), f"{phase_name} exit code is invalid")
            require(isinstance(phase.get("durationMs"), int) and phase["durationMs"] >= 0, f"{phase_name} duration is invalid")
            require(isinstance(phase.get("logSha256"), str) and SHA256.fullmatch(phase["logSha256"]), f"{phase_name} log digest is invalid")
        artifacts = root.get("artifacts")
        require(isinstance(artifacts, list), "qualification artifacts are invalid")
        if status == "passed":
            require(install["exitCode"] == build["exitCode"] == 0, "passed root has a failed command")
            require(bool(artifacts), "passed root has no artifact")
            for artifact in artifacts:
                require(isinstance(artifact, dict), "qualification artifact is invalid")
                require(isinstance(artifact.get("sha256"), str) and SHA256.fullmatch(artifact["sha256"]), "artifact digest is invalid")
                require(isinstance(artifact.get("size"), int) and artifact["size"] > 0, "artifact size is invalid")
        else:
            require(build["exitCode"] != 0, "failed root has a successful build")
            require(not artifacts, "failed root claims an artifact")
            classification = root.get("failureClassification")
            require(isinstance(classification, str) and classification, "failed root classification is absent")
    require("passed" in statuses and "failed" in statuses, "partial qualification must retain pass and failure roots")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    args = parser.parse_args()
    packet = load(args.packet, "candidate review packet")
    receipt = load(args.qualification, "source-build qualification")
    validate(receipt, packet, digest(args.packet))
    print(json.dumps({"schema": SCHEMA, "status": receipt["status"], "ok": True}, sort_keys=True))


if __name__ == "__main__":
    main()
