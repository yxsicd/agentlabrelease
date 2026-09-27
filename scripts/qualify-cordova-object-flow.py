#!/usr/bin/env python3
"""Qualify the selected Cordova value/object path across TypeScript and template scope."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


SCHEMA = "agentlab.cordova_object_flow_qualification.v1"
PLAN_SCHEMA = "agentlab.cordova_object_flow_plan.v1"
PROGRAM_SCHEMA = "agentlab.bounded_expression_flow_program_analysis.v1"
EXTERNAL_SCHEMA = "agentlab.external_sink_contract_qualification.v2"
REVISION = re.compile(r"[0-9a-f]{40}")


class CordovaObjectFlowError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise CordovaObjectFlowError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CordovaObjectFlowError(f"cannot read {label}: {error}") from error
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


def verify_files(
    repository: Path,
    revision: str,
    entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    require(git(repository, "rev-parse", "HEAD") == revision, "object-flow checkout revision differs")
    receipts = []
    texts = {}
    for entry in entries:
        require(isinstance(entry, dict), "object-flow source file is invalid")
        path = entry.get("path")
        require(
            isinstance(path, str)
            and path
            and not path.startswith("/")
            and "\\" not in path
            and all(part not in ("", ".", "..") for part in path.split("/")),
            "object-flow source path is unsafe",
        )
        listing = str(git(repository, "ls-tree", revision, "--", path)).split()
        require(len(listing) >= 4 and listing[1] == "blob", "object-flow source is not a Git blob")
        require(listing[2] == entry.get("gitBlobOid"), "object-flow Git Blob OID differs")
        content = git(repository, "cat-file", "blob", f"{revision}:{path}", binary=True)
        require(isinstance(content, bytes), "object-flow Git blob read failed")
        content_sha256 = digest_bytes(content)
        require(content_sha256 == entry.get("contentSha256"), "object-flow content digest differs")
        text = content.decode("utf-8")
        texts[path] = text
        snippet_receipts = []
        snippets = entry.get("exactSnippets")
        require(isinstance(snippets, list) and snippets, "object-flow exact snippets are absent")
        for snippet in snippets:
            require(isinstance(snippet, str) and snippet, "object-flow exact snippet is invalid")
            occurrences = text.count(snippet)
            require(occurrences == 1, f"object-flow exact snippet occurrence differs in {path}")
            snippet_receipts.append({
                "sha256": digest_bytes(snippet.encode("utf-8")),
                "occurrences": occurrences,
            })
        receipts.append({
            "path": path,
            "sourceRevision": revision,
            "gitBlobOid": listing[2],
            "contentSha256": content_sha256,
            "exactSnippets": snippet_receipts,
        })
    return receipts, texts


def flow_by_id(program: dict[str, Any], flow_id: str) -> dict[str, Any]:
    matches = [row for row in program.get("flows") or [] if isinstance(row, dict) and row.get("flowId") == flow_id]
    require(len(matches) == 1, "selected object flow occurrence differs")
    return matches[0]


def step_by_index(flow: dict[str, Any], index: int, kind: str) -> dict[str, Any]:
    matches = [row for row in flow.get("steps") or [] if isinstance(row, dict) and row.get("index") == index]
    require(len(matches) == 1 and matches[0].get("kind") == kind, f"object-flow step {index} differs")
    require(matches[0].get("status") == "verified", f"object-flow step {index} is not verified")
    return matches[0]


def qualify(
    program_path: Path,
    external_path: Path,
    plan_path: Path,
    repository: Path,
) -> dict[str, Any]:
    program = load(program_path, "bounded flow program analysis")
    external = load(external_path, "external sink qualification")
    plan = load(plan_path, "Cordova object-flow plan")
    require(program.get("schema") == PROGRAM_SCHEMA, "unsupported bounded flow program analysis")
    require(external.get("schema") == EXTERNAL_SCHEMA, "unsupported external sink qualification")
    require(plan.get("schema") == PLAN_SCHEMA, "unsupported Cordova object-flow plan")
    require(external.get("status") == "external-sink-contracts-qualified-review-required", "external sink contracts are not qualified")
    require(external.get("externalCallContractsResolved") is True, "external sink contracts remain unresolved")
    require(external.get("programAnalysisSha256") == digest(program_path), "object-flow program analysis differs")
    for key in ("candidateId", "sourceSetSha256"):
        require(plan.get(key) == program.get(key) == external.get(key), f"object-flow {key} differs")
    require(plan.get("programAnalysisSha256") == digest(program_path), "object-flow plan program digest differs")
    require(plan.get("externalSinkQualificationSha256") == digest(external_path), "object-flow plan external digest differs")
    repository_id = plan.get("repositoryId")
    require(repository_id == "hms-cordova-iap", "object-flow repository differs")
    revision = plan.get("sourceRevision")
    require(isinstance(revision, str) and REVISION.fullmatch(revision), "object-flow source revision is invalid")
    files = plan.get("files")
    require(isinstance(files, list) and len(files) == 2, "object-flow source file set differs")
    file_receipts, texts = verify_files(repository, revision, files)

    flow = flow_by_id(program, plan.get("flowId"))
    require(flow.get("repositoryId") == repository_id and flow.get("stepCount") == 4, "selected Cordova flow differs")
    parameter = plan.get("parameterFlow") or {}
    parameter_step = step_by_index(flow, 0, "call-argument-to-parameter")
    for key in ("callFactId", "callableFactId", "argumentExpression"):
        require(parameter_step.get(key) == parameter.get(key), f"object-flow parameter {key} differs")
    require(parameter_step.get("parameterExpression") == parameter.get("parameterName"), "object-flow parameter name differs")
    require(parameter_step.get("parameterTypeExpression") is None, "selected source parameter is unexpectedly annotated")
    require(parameter.get("argumentIndex") == parameter.get("parameterIndex") == 1, "object-flow parameter position differs")
    source_contract_id = parameter.get("sourceContractId")
    contracts = [row for row in external.get("contracts") or [] if isinstance(row, dict) and row.get("contractId") == source_contract_id]
    require(len(contracts) == 1, "object-flow source contract occurrence differs")
    source_type = contracts[0].get("sourceType") or {}
    require(source_type.get("typeExpression") == f'{parameter.get("effectiveType")}[]', "object-flow effective parameter type differs")

    assignment = plan.get("memberAssignment") or {}
    assignment_step = step_by_index(flow, 1, "assignment-dependency")
    require(assignment_step.get("factId") == assignment.get("factId"), "object-flow assignment fact differs")
    require(assignment_step.get("leftExpression") == assignment.get("leftExpression"), "object-flow assignment target differs")
    require(assignment_step.get("rightExpression") == assignment.get("rightExpression"), "object-flow assignment source differs")

    source_path = plan.get("sourcePath")
    template_path = plan.get("templatePath")
    require(source_path in texts and template_path in texts, "object-flow source binding is absent")
    source_text = texts[source_path]
    creator = plan.get("creatorFlow") or {}
    creator_signature = creator.get("signature")
    require(isinstance(creator_signature, str) and source_text.count(creator_signature) == 1, "object-flow creator signature differs")
    creator_start = source_text.index(creator_signature)
    sink_signature = (plan.get("sinkFlow") or {}).get("signature")
    require(isinstance(sink_signature, str) and source_text.count(sink_signature) == 1, "object-flow sink signature differs")
    sink_start = source_text.index(sink_signature)
    require(creator_start < sink_start, "object-flow callable order differs")
    creator_text = source_text[creator_start:sink_start]
    object_binding = creator.get("objectBinding")
    binding_expression = creator.get("bindingExpression")
    require(
        creator_text.count(f"let {object_binding} = {binding_expression};") == 1,
        "object-flow object binding differs",
    )
    require(creator_text.count(f'{assignment["leftExpression"]} = {assignment["rightExpression"]};') == 1, "object-flow member assignment differs")
    require(len(re.findall(rf"\b{re.escape(object_binding)}\s*=", creator_text)) == 1, "object-flow binding is reassigned")
    push_targets = creator.get("pushTargets")
    require(isinstance(push_targets, list) and len(push_targets) == 3 and len(set(push_targets)) == 3, "object-flow push targets differ")
    for target in push_targets:
        require(creator_text.count(f"{target}.push({object_binding});") == 1, f"object-flow push target differs: {target}")

    template_step = step_by_index(flow, 2, "template-event-bridge")
    require(template_step.get("path") == template_path, "object-flow template path differs")
    require(template_step.get("gitBlobOid") == next(row["gitBlobOid"] for row in file_receipts if row["path"] == template_path), "object-flow template Blob differs")
    bindings = plan.get("templateBindings")
    require(isinstance(bindings, list) and len(bindings) == 2, "object-flow template bindings differ")
    template_text = texts[template_path]
    for binding in bindings:
        variable = binding.get("variable")
        collection = binding.get("collection")
        call_expression = binding.get("callExpression")
        require(all(isinstance(value, str) and value for value in (variable, collection, call_expression)), "object-flow template binding metadata differs")
        pattern = re.compile(
            rf'<ion-item\s+\*ngFor="let\s+{re.escape(variable)}\s+of\s+{re.escape(collection)}">(?P<body>.*?)</ion-item>',
            re.DOTALL,
        )
        matches = list(pattern.finditer(template_text))
        require(len(matches) == 1, f"object-flow template collection occurrence differs: {collection}")
        require(matches[0].group("body").count(f'(click)="{call_expression}"') == 1, f"object-flow template call differs: {collection}")
        require(f"{variable}.{binding.get('member')}" in call_expression, f"object-flow template member identity differs: {collection}")

    sink = plan.get("sinkFlow") or {}
    sink_step = step_by_index(flow, 3, "call-argument-to-sink")
    require(sink_step.get("callFactId") == sink.get("sinkCallFactId"), "object-flow sink fact differs")
    require(sink_step.get("dependencyExpression") == sink.get("parameterName"), "object-flow sink parameter differs")
    sink_text = source_text[sink_start:]
    require(sink_text.count(sink.get("requestFieldExpression")) == 1, "object-flow sink request field differs")

    resolved = plan.get("resolvedBoundaries")
    require(isinstance(resolved, list) and len(resolved) == 3, "object-flow resolved boundary set differs")
    resolved_ids = [row.get("id") for row in resolved if isinstance(row, dict)]
    require(len(resolved_ids) == len(set(resolved_ids)) == 3, "object-flow resolved boundary ids differ")
    remaining = external.get("remainingUnresolved")
    require(isinstance(remaining, list) and len(remaining) == external.get("remainingUnresolvedCount") == 4, "external unresolved accounting differs")
    remaining_by_id = {row.get("id"): row for row in remaining if isinstance(row, dict)}
    for row in resolved:
        boundary = remaining_by_id.get(row.get("id"))
        require(boundary is not None, "object-flow resolved boundary was not unresolved")
        require(boundary.get("class") == row.get("class") and boundary.get("factId") == row.get("factId"), "object-flow boundary metadata differs")
    residual = [row for row in remaining if row.get("id") not in set(resolved_ids)]
    require(len(residual) == 1 and residual[0].get("class") == "control-flow", "object-flow residual boundary differs")
    return {
        "schema": SCHEMA,
        "status": "object-flow-qualified-control-flow-review-required",
        "candidateId": program.get("candidateId"),
        "sourceSetSha256": program.get("sourceSetSha256"),
        "reviewPacketSha256": program.get("reviewPacketSha256"),
        "programAnalysisSha256": digest(program_path),
        "externalSinkQualificationSha256": digest(external_path),
        "planSha256": digest(plan_path),
        "repositoryId": repository_id,
        "sourceRevision": revision,
        "files": file_receipts,
        "selectedFlowId": flow.get("flowId"),
        "effectiveParameterType": parameter.get("effectiveType"),
        "sourceParameterAnnotated": False,
        "selectedFlowParameterTypeResolved": True,
        "memberObjectIdentityResolved": True,
        "templateObjectIdentityResolved": True,
        "resolvedUnresolvedIds": sorted(resolved_ids),
        "originalUnresolvedCount": len(remaining),
        "remainingUnresolved": residual,
        "remainingUnresolvedCount": len(residual),
        "externalCallContractsResolved": True,
        "typeResolutionComplete": True,
        "aliasResolutionComplete": True,
        "reachabilityAndDominanceResolved": False,
        "semanticAlignmentVerified": False,
        "behaviorOracleVerified": False,
        "allowsCaseContract": False,
        "automaticPromotion": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--program-analysis", required=True, type=Path)
    parser.add_argument("--external-sink-qualification", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = qualify(
        args.program_analysis,
        args.external_sink_qualification,
        args.plan,
        args.repository,
    )
    require(not args.output.exists(), "refusing to overwrite Cordova object-flow qualification")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": SCHEMA,
        "status": result["status"],
        "resolvedBoundaryCount": len(result["resolvedUnresolvedIds"]),
        "remainingUnresolvedCount": result["remainingUnresolvedCount"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
