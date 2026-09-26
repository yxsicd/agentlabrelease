#!/usr/bin/env python3
"""Qualify bounded-flow sink contracts from exact source-controlled declarations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


SCHEMA = "agentlab.external_sink_contract_qualification.v1"
PLAN_SCHEMA = "agentlab.external_sink_contract_plan.v1"
PROGRAM_SCHEMA = "agentlab.bounded_expression_flow_program_analysis.v1"
REVISION = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")


class ExternalSinkContractError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ExternalSinkContractError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExternalSinkContractError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def git(repository: Path, *arguments: str, binary: bool = False) -> str | bytes:
    require(repository.is_dir(), f"repository checkout missing: {repository}")
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    require(completed.returncode == 0, f"git {' '.join(arguments)} failed")
    return completed.stdout if binary else completed.stdout.decode("utf-8").strip()


def mappings(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        repository_id, separator, raw_path = value.partition("=")
        require(separator == "=" and repository_id and raw_path, "invalid repository mapping")
        require(repository_id not in result, "duplicate repository mapping")
        result[repository_id] = Path(raw_path)
    return result


def sink_steps(program: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for flow in program.get("flows") or []:
        require(isinstance(flow, dict), "invalid program-analysis flow")
        repository_id = flow.get("repositoryId")
        require(isinstance(repository_id, str) and repository_id, "program flow repository is invalid")
        for step in flow.get("steps") or []:
            if not isinstance(step, dict) or step.get("kind") != "call-argument-to-sink":
                continue
            fact_id = step.get("callFactId")
            require(isinstance(fact_id, str) and fact_id, "sink call fact id is invalid")
            key = (repository_id, fact_id)
            require(key not in result, "duplicate sink call fact")
            result[key] = step
    return result


def verify_git_blob_set(
    repository: Path,
    repository_id: str,
    authority: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
    require(authority.get("kind") == "git-blob-set", "unsupported contract authority")
    revision = authority.get("sourceRevision")
    require(isinstance(revision, str) and REVISION.fullmatch(revision), "contract revision is invalid")
    require(git(repository, "rev-parse", "HEAD") == revision, "contract checkout revision differs")
    files = authority.get("files")
    require(isinstance(files, list) and files, "contract authority files are absent")
    receipts: list[dict[str, Any]] = []
    exact_snippets: list[str] = []
    for entry in files:
        require(isinstance(entry, dict), "contract authority file is invalid")
        path = entry.get("path")
        require(
            isinstance(path, str)
            and path
            and not path.startswith("/")
            and "\\" not in path
            and all(part not in ("", ".", "..") for part in path.split("/")),
            "contract authority path is unsafe",
        )
        listing = str(git(repository, "ls-tree", revision, "--", path)).split()
        require(len(listing) >= 4 and listing[1] == "blob", "contract authority path is not a Git blob")
        blob_oid = listing[2]
        require(blob_oid == entry.get("gitBlobOid"), "contract Git Blob OID differs")
        content = git(repository, "cat-file", "blob", f"{revision}:{path}", binary=True)
        require(isinstance(content, bytes), "contract Git blob read failed")
        content_sha256 = digest_bytes(content)
        require(content_sha256 == entry.get("contentSha256"), "contract content digest differs")
        text = content.decode("utf-8")
        snippets = entry.get("exactSnippets")
        require(isinstance(snippets, list) and snippets, "contract exact snippets are absent")
        snippet_receipts = []
        for snippet in snippets:
            require(isinstance(snippet, str) and snippet, "contract exact snippet is invalid")
            occurrences = text.count(snippet)
            require(occurrences == 1, f"contract exact snippet occurrence differs in {path}")
            snippet_receipts.append({
                "sha256": digest_bytes(snippet.encode("utf-8")),
                "occurrences": occurrences,
            })
            exact_snippets.append(snippet)
        receipts.append({
            "repositoryId": repository_id,
            "path": path,
            "sourceRevision": revision,
            "gitBlobOid": blob_oid,
            "contentSha256": content_sha256,
            "exactSnippets": snippet_receipts,
        })
    return revision, receipts, exact_snippets


def qualify(
    program_path: Path,
    plan_path: Path,
    repositories: dict[str, Path],
) -> dict[str, Any]:
    program = load(program_path, "bounded flow program analysis")
    plan = load(plan_path, "external sink contract plan")
    require(program.get("schema") == PROGRAM_SCHEMA, "unsupported bounded flow program analysis")
    require(
        program.get("status") == "bounded-program-flow-partially-resolved-review-required",
        "bounded flow program analysis is not review-required",
    )
    require(plan.get("schema") == PLAN_SCHEMA, "unsupported external sink contract plan")
    for key in ("candidateId", "sourceSetSha256"):
        require(plan.get(key) == program.get(key), f"external sink contract {key} differs")
    require(program.get("flowReplayExact") is True, "bounded flow was not replayed")
    coverage = program.get("coverage") or {}
    external_sink_count = coverage.get("externalSinkCount")
    require(isinstance(external_sink_count, int) and external_sink_count > 0, "external sink count is invalid")
    sinks = sink_steps(program)
    require(len(sinks) == external_sink_count, "external sink steps differ from coverage")
    unresolved = program.get("unresolved")
    require(isinstance(unresolved, list) and len(unresolved) == program.get("unresolvedCount"), "program unresolved set differs")
    unresolved_by_id = {
        row.get("id"): row
        for row in unresolved
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }

    contracts = plan.get("contracts")
    require(isinstance(contracts, list) and contracts, "external sink contracts are absent")
    receipts: list[dict[str, Any]] = []
    resolved_unresolved_ids: set[str] = set()
    seen_contract_ids: set[str] = set()
    for contract in contracts:
        require(isinstance(contract, dict), "external sink contract is invalid")
        contract_id = contract.get("contractId")
        repository_id = contract.get("repositoryId")
        sink_fact_id = contract.get("sinkCallFactId")
        require(isinstance(contract_id, str) and contract_id and contract_id not in seen_contract_ids, "contract id is invalid or duplicate")
        seen_contract_ids.add(contract_id)
        require(repository_id in repositories, "contract repository mapping is absent")
        sink = sinks.get((repository_id, sink_fact_id))
        require(sink is not None, "contract sink call is absent from program analysis")
        require(sink.get("targetExpression") == contract.get("targetExpression"), "contract sink target differs")
        unresolved_id = f"external-sink-signature:{repository_id}:{sink_fact_id}"
        require(unresolved_id in unresolved_by_id, "contract sink is not an unresolved external signature")
        require(unresolved_id not in resolved_unresolved_ids, "contract sink is resolved twice")
        revision, files, exact_snippets = verify_git_blob_set(
            repositories[repository_id],
            repository_id,
            contract.get("authority") or {},
        )
        source_type = contract.get("sourceType")
        request_field = contract.get("requestField")
        signature = contract.get("signature")
        receiver = contract.get("receiverBinding")
        require(
            isinstance(source_type, dict)
            and isinstance(source_type.get("interface"), str)
            and isinstance(source_type.get("field"), str)
            and isinstance(source_type.get("typeExpression"), str),
            "source type contract is invalid",
        )
        require(
            isinstance(request_field, dict)
            and isinstance(request_field.get("interface"), str)
            and isinstance(request_field.get("field"), str)
            and isinstance(request_field.get("typeExpression"), str),
            "request field contract is invalid",
        )
        require(
            isinstance(signature, dict)
            and isinstance(signature.get("callable"), str)
            and isinstance(signature.get("parameterName"), str)
            and isinstance(signature.get("parameterType"), str)
            and isinstance(signature.get("returnType"), str),
            "sink signature contract is invalid",
        )
        require(
            isinstance(receiver, dict)
            and receiver.get("property") == contract["targetExpression"].split(".")[-2]
            and isinstance(receiver.get("typeExpression"), str),
            "sink receiver binding is invalid",
        )
        source_value_type = source_type["typeExpression"].removesuffix("[]")
        require(source_type["typeExpression"].endswith("[]"), "source contract must select an array element")
        require(source_value_type == request_field["typeExpression"], "source and request field types differ")
        require(signature["parameterType"] == request_field["interface"], "signature request type differs")
        require(signature["callable"] == contract["targetExpression"].split(".")[-1], "signature callable differs")
        require(
            any(
                source_type["interface"] in snippet
                and f'{source_type["field"]}: {source_type["typeExpression"]};' in snippet
                for snippet in exact_snippets
            ),
            "source type metadata is not bound by one exact snippet",
        )
        require(
            any(
                request_field["interface"] in snippet
                and f'{request_field["field"]}: {request_field["typeExpression"]};' in snippet
                for snippet in exact_snippets
            ),
            "request field metadata is not bound by one exact snippet",
        )
        require(
            any(
                signature["callable"] in snippet
                and f'{signature["parameterName"]}: {signature["parameterType"]}' in snippet
                and signature["returnType"] in snippet
                for snippet in exact_snippets
            ),
            "signature metadata is not bound by one exact snippet",
        )
        require(
            any(
                receiver["property"] in snippet
                and receiver["typeExpression"] in snippet
                for snippet in exact_snippets
            ),
            "receiver metadata is not bound by one exact snippet",
        )
        resolved_unresolved_ids.add(unresolved_id)
        receipts.append({
            "contractId": contract_id,
            "repositoryId": repository_id,
            "sourceRevision": revision,
            "sinkCallFactId": sink_fact_id,
            "targetExpression": contract["targetExpression"],
            "authority": "exact-git-blob-set",
            "files": files,
            "receiverBinding": receiver,
            "sourceType": source_type,
            "requestField": request_field,
            "signature": signature,
            "selectedSourceElementType": source_value_type,
            "sourceToRequestTypeCompatible": True,
            "externalSinkContractResolved": True,
        })

    remaining = [row for row in unresolved if row.get("id") not in resolved_unresolved_ids]
    remaining_external = [row for row in remaining if row.get("class") == "external-call-contract"]
    require(len(remaining) + len(resolved_unresolved_ids) == len(unresolved), "unresolved accounting differs")
    return {
        "schema": SCHEMA,
        "status": "external-sink-contracts-partially-qualified-review-required",
        "candidateId": program.get("candidateId"),
        "sourceSetSha256": program.get("sourceSetSha256"),
        "reviewPacketSha256": program.get("reviewPacketSha256"),
        "programAnalysisSha256": digest(program_path),
        "planSha256": digest(plan_path),
        "externalSinkCount": external_sink_count,
        "resolvedExternalSinkCount": len(receipts),
        "remainingExternalSinkCount": len(remaining_external),
        "contracts": receipts,
        "originalUnresolvedCount": len(unresolved),
        "resolvedUnresolvedIds": sorted(resolved_unresolved_ids),
        "remainingUnresolved": remaining,
        "remainingUnresolvedCount": len(remaining),
        "externalCallContractsResolved": len(remaining_external) == 0,
        "typeResolutionComplete": False,
        "aliasResolutionComplete": False,
        "reachabilityAndDominanceResolved": False,
        "semanticAlignmentVerified": False,
        "behaviorOracleVerified": False,
        "allowsCaseContract": False,
        "automaticPromotion": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--program-analysis", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--repository", action="append", default=[], metavar="REPOSITORY_ID=PATH")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = qualify(args.program_analysis, args.plan, mappings(args.repository))
    require(not args.output.exists(), "refusing to overwrite external sink qualification")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": SCHEMA,
        "status": result["status"],
        "resolvedExternalSinkCount": result["resolvedExternalSinkCount"],
        "remainingUnresolvedCount": result["remainingUnresolvedCount"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
