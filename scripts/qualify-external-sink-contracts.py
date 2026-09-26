#!/usr/bin/env python3
"""Qualify bounded-flow sink contracts from exact source-controlled declarations."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
from typing import Any


SCHEMA = "agentlab.external_sink_contract_qualification.v1"
SCHEMA_V2 = "agentlab.external_sink_contract_qualification.v2"
PLAN_SCHEMA = "agentlab.external_sink_contract_plan.v1"
PLAN_SCHEMA_V2 = "agentlab.external_sink_contract_plan.v2"
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


def safe_archive_member(value: Any) -> str:
    require(isinstance(value, str) and value, "contract archive member path is invalid")
    normalized = value.removeprefix("./")
    require(
        normalized
        and not normalized.startswith("/")
        and "\\" not in normalized
        and all(part not in ("", ".", "..") for part in normalized.split("/")),
        "contract archive member path is unsafe",
    )
    return normalized


def archive_member_contents(
    archive: Path,
    archive_format: str,
    member_paths: list[str],
) -> dict[str, bytes]:
    if archive_format == "tar":
        result: dict[str, bytes] = {}
        try:
            with tarfile.open(archive, mode="r:") as bundle:
                for member_path in member_paths:
                    member = bundle.getmember(member_path)
                    require(member.isfile(), f"contract archive member is not a regular file: {member_path}")
                    stream = bundle.extractfile(member)
                    require(stream is not None, f"cannot read contract archive member: {member_path}")
                    result[member_path] = stream.read()
        except (KeyError, OSError, tarfile.TarError) as error:
            raise ExternalSinkContractError(f"cannot read contract archive: {error}") from error
        return result
    require(archive_format == "tar-zstd-long31", "unsupported contract archive format")
    with tempfile.TemporaryDirectory(prefix="agentlab-sdk-contract-") as directory:
        completed = subprocess.run(
            [
                "tar",
                "--use-compress-program=zstd -d --long=31",
                "-xf",
                str(archive),
                "-C",
                directory,
                *member_paths,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(completed.returncode == 0, "contract SDK archive extraction failed")
        root = Path(directory).resolve()
        result = {}
        for member_path in member_paths:
            candidate = (root / safe_archive_member(member_path)).resolve()
            require(candidate.is_relative_to(root), "contract archive member escaped extraction root")
            require(candidate.is_file() and not candidate.is_symlink(), f"contract archive member is not a regular file: {member_path}")
            result[member_path] = candidate.read_bytes()
        return result


def verify_sdk_archive_member_set(
    archive: Path,
    asset_id: str,
    authority: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    require(authority.get("kind") == "sdk-archive-member-set", "unsupported contract authority")
    require(archive.is_file() and not archive.is_symlink(), "contract SDK archive must be a regular file")
    require(authority.get("assetId") == asset_id, "contract SDK asset id differs")
    archive_sha256 = authority.get("archiveSha256")
    require(isinstance(archive_sha256, str) and SHA256.fullmatch(archive_sha256), "contract SDK archive digest is invalid")
    require(digest(archive) == archive_sha256, "contract SDK archive digest differs")
    archive_format = authority.get("archiveFormat")
    require(isinstance(archive_format, str), "contract SDK archive format is invalid")
    members = authority.get("members")
    require(isinstance(members, list) and members, "contract SDK archive members are absent")
    member_paths = [entry.get("path") if isinstance(entry, dict) else None for entry in members]
    require(len(set(member_paths)) == len(member_paths), "duplicate contract SDK archive member")
    for member_path in member_paths:
        safe_archive_member(member_path)
    contents = archive_member_contents(archive, archive_format, member_paths)
    receipts: list[dict[str, Any]] = []
    texts: dict[str, str] = {}
    for entry in members:
        path = entry["path"]
        content = contents[path]
        content_sha256 = digest_bytes(content)
        require(content_sha256 == entry.get("contentSha256"), "contract SDK member digest differs")
        text = content.decode("utf-8")
        texts[path] = text
        snippets = entry.get("exactSnippets")
        require(isinstance(snippets, list) and snippets, "contract SDK exact snippets are absent")
        snippet_receipts = []
        for snippet in snippets:
            require(isinstance(snippet, str) and snippet, "contract SDK exact snippet is invalid")
            occurrences = text.count(snippet)
            require(occurrences == 1, f"contract SDK exact snippet occurrence differs in {path}")
            snippet_receipts.append({
                "sha256": digest_bytes(snippet.encode("utf-8")),
                "occurrences": occurrences,
            })
        receipts.append({
            "path": path,
            "contentSha256": content_sha256,
            "exactSnippets": snippet_receipts,
        })
    asset = {
        "assetId": asset_id,
        "archiveFormat": archive_format,
        "archiveSha256": archive_sha256,
        "releaseTag": authority.get("releaseTag"),
        "releaseUrl": authority.get("releaseUrl"),
    }
    require(isinstance(asset["releaseTag"], str) and asset["releaseTag"], "contract SDK release tag is invalid")
    require(isinstance(asset["releaseUrl"], str) and asset["releaseUrl"].startswith("https://"), "contract SDK release URL is invalid")
    return asset, receipts, texts


def interface_body(text: str, interface_name: str) -> str:
    pattern = re.compile(
        rf"^[ \t]*interface[ \t]+{re.escape(interface_name)}[ \t]*\{{(?P<body>.*?)(?=^[ \t]*\}})",
        re.MULTILINE | re.DOTALL,
    )
    matches = list(pattern.finditer(text))
    require(len(matches) == 1, "contract SDK request interface occurrence differs")
    return matches[0].group("body")


def verify_sdk_contract_metadata(
    contract: dict[str, Any],
    sink: dict[str, Any],
    texts: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    binding = contract.get("moduleBinding")
    request_type = contract.get("requestType")
    signature = contract.get("signature")
    require(isinstance(binding, dict), "SDK module binding is invalid")
    require(isinstance(request_type, dict), "SDK request type is invalid")
    require(isinstance(signature, dict), "SDK sink signature is invalid")
    kit_path = binding.get("kitDeclarationMember")
    config_path = binding.get("kitConfigMember")
    source_path = binding.get("sourceDeclarationMember")
    require(kit_path in texts and config_path in texts and source_path in texts, "SDK module binding member is absent")
    symbol = binding.get("symbol")
    source_module = binding.get("sourceModule")
    source_declaration = binding.get("sourceDeclaration")
    require(
        isinstance(symbol, str)
        and symbol == contract["targetExpression"].split(".")[-2]
        and isinstance(source_module, str)
        and isinstance(source_declaration, str),
        "SDK module binding metadata differs",
    )
    require(f"import {symbol} from '{source_module}';" in texts[kit_path], "SDK kit import binding differs")
    require(re.search(rf"export\s*\{{[^}}]*\b{re.escape(symbol)}\b[^}}]*\}}", texts[kit_path]) is not None, "SDK kit export binding differs")
    try:
        config = json.loads(texts[config_path])
    except json.JSONDecodeError as error:
        raise ExternalSinkContractError(f"SDK kit config is invalid: {error}") from error
    require(
        config.get("symbols", {}).get(symbol) == {"source": source_declaration, "bindings": "default"},
        "SDK kit config binding differs",
    )
    require(Path(safe_archive_member(source_path)).name == source_declaration, "SDK source declaration path differs")
    interface_name = request_type.get("interface")
    fields = request_type.get("fields")
    require(isinstance(interface_name, str) and isinstance(fields, list) and fields, "SDK request type metadata differs")
    body = interface_body(texts[source_path], interface_name)
    seen_fields: set[str] = set()
    for field in fields:
        require(isinstance(field, dict), "SDK request field is invalid")
        name = field.get("field")
        type_expression = field.get("typeExpression")
        require(isinstance(name, str) and name not in seen_fields and isinstance(type_expression, str), "SDK request field metadata differs")
        seen_fields.add(name)
        require(re.search(rf"^[ \t]*{re.escape(name)}[ \t]*:[ \t]*{re.escape(type_expression)}[ \t]*;", body, re.MULTILINE) is not None, f"SDK request field differs: {name}")
    callable_name = signature.get("callable")
    context_type = signature.get("contextType")
    parameter_name = signature.get("parameterName")
    parameter_type = signature.get("parameterType")
    return_type = signature.get("returnType")
    parameter_index = signature.get("parameterIndex")
    require(
        callable_name == contract["targetExpression"].split(".")[-1]
        and isinstance(context_type, str)
        and isinstance(parameter_name, str)
        and parameter_type == interface_name
        and isinstance(return_type, str)
        and parameter_index == sink.get("argumentIndex"),
        "SDK sink signature metadata differs",
    )
    signature_text = (
        f"function {callable_name}(context: {context_type}, {parameter_name}: {parameter_type}): {return_type};"
    )
    require(texts[source_path].count(signature_text) == 1, "SDK sink signature occurrence differs")
    return binding, request_type, signature


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
    archives: dict[str, Path] | None = None,
) -> dict[str, Any]:
    archives = archives or {}
    program = load(program_path, "bounded flow program analysis")
    plan = load(plan_path, "external sink contract plan")
    require(program.get("schema") == PROGRAM_SCHEMA, "unsupported bounded flow program analysis")
    require(
        program.get("status") == "bounded-program-flow-partially-resolved-review-required",
        "bounded flow program analysis is not review-required",
    )
    plan_schema = plan.get("schema")
    require(plan_schema in (PLAN_SCHEMA, PLAN_SCHEMA_V2), "unsupported external sink contract plan")
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
        sink = sinks.get((repository_id, sink_fact_id))
        require(sink is not None, "contract sink call is absent from program analysis")
        require(sink.get("targetExpression") == contract.get("targetExpression"), "contract sink target differs")
        unresolved_id = f"external-sink-signature:{repository_id}:{sink_fact_id}"
        require(unresolved_id in unresolved_by_id, "contract sink is not an unresolved external signature")
        require(unresolved_id not in resolved_unresolved_ids, "contract sink is resolved twice")
        authority = contract.get("authority") or {}
        if authority.get("kind") == "sdk-archive-member-set":
            require(plan_schema == PLAN_SCHEMA_V2, "SDK archive contracts require a v2 plan")
            asset_id = authority.get("assetId")
            require(asset_id in archives, "contract SDK archive mapping is absent")
            asset, members, texts = verify_sdk_archive_member_set(
                archives[asset_id],
                asset_id,
                authority,
            )
            binding, request_type, signature = verify_sdk_contract_metadata(contract, sink, texts)
            resolved_unresolved_ids.add(unresolved_id)
            receipts.append({
                "contractId": contract_id,
                "repositoryId": repository_id,
                "sinkCallFactId": sink_fact_id,
                "targetExpression": contract["targetExpression"],
                "authority": "exact-sdk-archive-member-set",
                "asset": asset,
                "members": members,
                "moduleBinding": binding,
                "requestType": request_type,
                "signature": signature,
                "externalSinkContractResolved": True,
            })
            continue
        require(repository_id in repositories, "contract repository mapping is absent")
        revision, files, exact_snippets = verify_git_blob_set(
            repositories[repository_id], repository_id, authority
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
    status = (
        "external-sink-contracts-qualified-review-required"
        if not remaining_external
        else "external-sink-contracts-partially-qualified-review-required"
    )
    return {
        "schema": SCHEMA_V2 if plan_schema == PLAN_SCHEMA_V2 else SCHEMA,
        "status": status,
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
    parser.add_argument("--archive", action="append", default=[], metavar="ASSET_ID=PATH")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = qualify(
        args.program_analysis,
        args.plan,
        mappings(args.repository),
        mappings(args.archive),
    )
    require(not args.output.exists(), "refusing to overwrite external sink qualification")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": result["schema"],
        "status": result["status"],
        "resolvedExternalSinkCount": result["resolvedExternalSinkCount"],
        "remainingUnresolvedCount": result["remainingUnresolvedCount"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
