#!/usr/bin/env python3
"""Build a review-only, bounded syntactic flow proposal from exact AST facts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


SCHEMA = "agentlab.bounded_expression_flow_proposal.v1"
PLAN_SCHEMA = "agentlab.bounded_expression_flow_plan.v1"
PACKET_SCHEMA = "agentlab.multi_repo_candidate_review_packet.v5"
ANALYSIS_SCHEMA = "agentlab.ast_analysis.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


class FlowProposalError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise FlowProposalError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FlowProposalError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def mappings(values: list[str], label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        repository_id, separator, raw_path = value.partition("=")
        require(separator == "=" and repository_id and raw_path, f"invalid {label} mapping")
        require(repository_id not in result, f"duplicate {label} repository id")
        result[repository_id] = Path(raw_path)
    return result


def packet_revisions(packet: dict[str, Any]) -> dict[str, str]:
    require(packet.get("schema") == PACKET_SCHEMA, "unsupported candidate review packet")
    revisions: dict[str, str] = {}
    for fact in packet.get("domainFactEvidence") or []:
        require(isinstance(fact, dict), "invalid packet domain fact")
        repository_id = fact.get("repositoryId")
        identity = fact.get("sourceIdentity")
        require(isinstance(repository_id, str) and repository_id, "invalid packet repository id")
        require(isinstance(identity, str) and "@" in identity, "invalid packet source identity")
        revision = identity.rsplit("@", 1)[-1]
        require(REVISION.fullmatch(revision), "invalid packet source revision")
        require(revisions.setdefault(repository_id, revision) == revision, "packet revisions differ")
    require(len(revisions) >= 2, "packet must span repositories")
    return revisions


def read_facts(path: Path, expected_sha256: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    require(path.is_file() and not path.is_symlink(), "program facts must be a regular file")
    raw = path.read_bytes()
    require(sha256_bytes(raw) == expected_sha256, "program facts digest differs")
    rows: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(raw.splitlines(), 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise FlowProposalError(f"invalid program fact at line {number}: {error}") from error
        require(isinstance(row, dict), f"program fact at line {number} is not an object")
        fact_id = row.get("id")
        require(isinstance(fact_id, str) and fact_id and fact_id not in by_id, "invalid or duplicate fact id")
        rows.append(row)
        by_id[fact_id] = row
    return rows, by_id


def parameter_name(expression: str) -> str:
    expression = expression.strip().removeprefix("...").split("=", 1)[0].strip()
    match = IDENTIFIER.match(expression)
    require(match is not None, f"cannot parse parameter expression: {expression}")
    return match.group(0)


def callable_scope(row: dict[str, Any]) -> str:
    if row.get("kind") == "symbol":
        scope = row.get("qualifiedName")
    else:
        owner, name = row.get("owner"), row.get("name")
        scope = f"{owner}::{name}" if isinstance(owner, str) and isinstance(name, str) else None
    require(isinstance(scope, str) and scope, "callable fact lacks scope")
    return scope


def find_scope(row: dict[str, Any], definitions: list[dict[str, Any]]) -> str:
    row_span = row.get("span") or {}
    start, end = row_span.get("startByte"), row_span.get("endByte")
    candidates = []
    if isinstance(start, int) and isinstance(end, int):
        for definition in definitions:
            if definition.get("path") != row.get("path"):
                continue
            span = definition.get("span") or {}
            if span.get("startByte", start + 1) <= start and span.get("endByte", end - 1) >= end:
                candidates.append(definition)
    if candidates:
        selected = min(candidates, key=lambda item: item["span"]["endByte"] - item["span"]["startByte"])
        return callable_scope(selected)
    owner = row.get("owner")
    require(isinstance(owner, str) and "::" in owner, f"cannot determine callable scope for {row.get('id')}")
    return owner


def contains_expression(container: Any, expression: str) -> bool:
    if isinstance(container, list):
        return any(contains_expression(item, expression) for item in container)
    return isinstance(container, str) and expression in container


def node(scope: str, expression: str) -> str:
    return f"{scope}::{expression}"


def git(repository: Path, *arguments: str, binary: bool = False) -> bytes | str:
    require(repository.is_dir(), f"repository checkout missing: {repository}")
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    require(completed.returncode == 0, f"git {' '.join(arguments)} failed")
    return completed.stdout if binary else completed.stdout.decode("utf-8").strip()


def verify_bridge(
    bridge: dict[str, Any], repository: Path, revision: str, callable_fact: dict[str, Any]
) -> tuple[dict[str, Any], str, str]:
    require(git(repository, "rev-parse", "HEAD") == revision, "bridge checkout revision differs")
    path = bridge.get("path")
    require(isinstance(path, str) and path and not path.startswith("/"), "invalid bridge path")
    listing = git(repository, "ls-tree", revision, "--", path)
    fields = str(listing).split()
    require(len(fields) >= 4 and fields[1] == "blob", "bridge path is not an exact Git blob")
    blob_oid = fields[2]
    require(blob_oid == bridge.get("gitBlobOid"), "bridge Git Blob OID differs")
    content = git(repository, "cat-file", "blob", f"{revision}:{path}", binary=True)
    require(isinstance(content, bytes), "bridge content read failed")
    content_sha256 = sha256_bytes(content)
    require(content_sha256 == bridge.get("contentSha256"), "bridge content digest differs")
    exact = bridge.get("exactExpression")
    require(isinstance(exact, str) and exact, "bridge exact expression is invalid")
    occurrences = content.decode("utf-8").count(exact)
    require(occurrences == bridge.get("occurrences"), "bridge occurrence count differs")
    parameters = callable_fact.get("parameterExpressions") or []
    parameter_index = bridge.get("parameterIndex")
    require(isinstance(parameter_index, int) and 0 <= parameter_index < len(parameters), "invalid bridge parameter index")
    arguments = bridge.get("argumentExpressions")
    require(isinstance(arguments, list) and all(isinstance(item, str) for item in arguments), "invalid bridge arguments")
    argument_index = bridge.get("argumentIndex")
    require(isinstance(argument_index, int) and 0 <= argument_index < len(arguments), "invalid bridge argument index")
    callable_name = callable_fact.get("name")
    require(exact == f"{callable_name}({', '.join(arguments)})", "bridge call expression differs")
    to_expression = parameter_name(parameters[parameter_index])
    require(arguments[argument_index] == bridge.get("fromExpression"), "bridge source argument differs")
    require(argument_index == parameter_index, "bridge argument-to-parameter position differs")
    receipt = {
        "path": path,
        "sourceRevision": revision,
        "gitBlobOid": blob_oid,
        "contentSha256": content_sha256,
        "exactExpression": exact,
        "argumentIndex": argument_index,
        "parameterIndex": parameter_index,
        "occurrences": occurrences,
    }
    return receipt, bridge["fromExpression"], to_expression


def build(
    plan_path: Path,
    packet_path: Path,
    analyses: dict[str, Path],
    facts: dict[str, Path],
    repositories: dict[str, Path],
) -> dict[str, Any]:
    plan = load(plan_path, "flow plan")
    packet = load(packet_path, "candidate review packet")
    require(plan.get("schema") == PLAN_SCHEMA, "unsupported flow plan")
    require(plan.get("candidateId") == packet.get("candidateId"), "plan candidate differs")
    require(plan.get("sourceSetSha256") == packet.get("sourceSetSha256"), "plan source set differs")
    revisions = packet_revisions(packet)
    require(set(analyses) == set(facts) == set(repositories) == set(revisions), "repository mappings differ")

    repository_data: dict[str, dict[str, Any]] = {}
    repository_receipts = []
    for repository_id in sorted(revisions):
        analysis = load(analyses[repository_id], f"{repository_id} analysis")
        require(analysis.get("schema") == ANALYSIS_SCHEMA, "unsupported AST analysis")
        require(analysis.get("sourceRevision") == revisions[repository_id], "analysis revision differs")
        facts_sha256 = analysis.get("sha256")
        require(isinstance(facts_sha256, str) and SHA256.fullmatch(facts_sha256), "invalid facts digest")
        rows, by_id = read_facts(facts[repository_id], facts_sha256)
        require(analysis.get("rows") == len(rows), "analysis row count differs")
        require(git(repositories[repository_id], "rev-parse", "HEAD") == revisions[repository_id], "checkout revision differs")
        definitions = [row for row in rows if row.get("kind") in {"symbol", "property"} and row.get("parameterExpressions") is not None]
        repository_data[repository_id] = {"analysis": analysis, "byId": by_id, "definitions": definitions}
        repository_receipts.append({
            "repositoryId": repository_id,
            "sourceRevision": revisions[repository_id],
            "analysisSha256": sha256_file(analyses[repository_id]),
            "programFactsSha256": facts_sha256,
            "rowCount": len(rows),
        })

    flow_receipts = []
    all_bridge_receipts = []
    for flow in plan.get("flows") or []:
        repository_id = flow.get("repositoryId")
        require(repository_id in repository_data, "flow repository is unknown")
        data = repository_data[repository_id]
        by_id, definitions = data["byId"], data["definitions"]
        edges = []
        for index, step in enumerate(flow.get("steps") or []):
            kind = step.get("kind")
            evidence: dict[str, Any]
            if kind == "call-argument-to-parameter":
                call = by_id.get(step.get("callFactId"))
                target = by_id.get(step.get("callableFactId"))
                require(call and call.get("kind") == "call", "call mapping lacks call fact")
                require(target and target.get("kind") in {"symbol", "property"}, "call mapping lacks callable fact")
                call_scope = find_scope(call, definitions)
                require(call_scope == step.get("callScope"), "call scope differs")
                arguments, parameters = call.get("argumentExpressions") or [], target.get("parameterExpressions") or []
                argument_index, parameter_index = step.get("argumentIndex"), step.get("parameterIndex")
                require(isinstance(argument_index, int) and 0 <= argument_index < len(arguments), "invalid call argument index")
                require(isinstance(parameter_index, int) and 0 <= parameter_index < len(parameters), "invalid parameter index")
                target_name = target.get("symbol") if target.get("kind") == "symbol" else target.get("name")
                require(call.get("targetExpression") == f"this.{target_name}", "local call target is not exact")
                from_scope, from_expression = call_scope, arguments[argument_index]
                to_scope, to_expression = callable_scope(target), parameter_name(parameters[parameter_index])
                evidence = {"callFactId": call["id"], "callableFactId": target["id"], "argumentIndex": argument_index, "parameterIndex": parameter_index}
            elif kind == "binding-dependency":
                fact = by_id.get(step.get("factId"))
                require(fact and fact.get("kind") == "binding", "binding edge lacks binding fact")
                from_scope = to_scope = find_scope(fact, definitions)
                from_expression, to_expression = step.get("dependsOn"), fact.get("name")
                require(isinstance(from_expression, str) and contains_expression(fact.get("initializerExpression"), from_expression), "binding dependency differs")
                evidence = {"factId": fact["id"], "initializerExpression": fact["initializerExpression"]}
            elif kind == "assignment-dependency":
                fact = by_id.get(step.get("factId"))
                require(fact and fact.get("kind") == "assignment", "assignment edge lacks assignment fact")
                from_scope = to_scope = find_scope(fact, definitions)
                from_expression, to_expression = fact.get("rightExpression"), fact.get("leftExpression")
                evidence = {"factId": fact["id"]}
            elif kind == "template-event-bridge":
                target = by_id.get(step.get("callableFactId"))
                require(target and target.get("kind") == "property", "template bridge lacks callable fact")
                receipt, from_expression, to_expression = verify_bridge(step, repositories[repository_id], revisions[repository_id], target)
                from_scope, to_scope = step.get("fromScope"), callable_scope(target)
                require(isinstance(from_scope, str) and from_scope, "template bridge source scope is invalid")
                evidence = {"callableFactId": target["id"], "bridge": receipt}
                all_bridge_receipts.append({"repositoryId": repository_id, **receipt})
            elif kind == "call-argument-to-sink":
                call = by_id.get(step.get("callFactId"))
                require(call and call.get("kind") == "call", "sink edge lacks call fact")
                require(call.get("targetExpression") == step.get("targetExpression"), "sink call target differs")
                call_scope = find_scope(call, definitions)
                require(call_scope == step.get("callScope"), "sink call scope differs")
                argument_index = step.get("argumentIndex")
                arguments = call.get("argumentExpressions") or []
                require(isinstance(argument_index, int) and 0 <= argument_index < len(arguments), "invalid sink argument index")
                from_expression = step.get("dependsOn")
                require(isinstance(from_expression, str) and contains_expression(arguments[argument_index], from_expression), "sink dependency differs")
                object_fact_id = step.get("objectEntryFactId")
                if object_fact_id:
                    object_fact = by_id.get(object_fact_id)
                    require(object_fact and object_fact.get("kind") == "object-entry", "sink object entry is missing")
                    require(object_fact.get("valueExpression") == from_expression, "sink object value differs")
                    require(object_fact.get("keyExpression") == step.get("objectKey"), "sink object key differs")
                    call_span, object_span = call.get("span") or {}, object_fact.get("span") or {}
                    require(call_span.get("startByte") <= object_span.get("startByte") and call_span.get("endByte") >= object_span.get("endByte"), "sink object entry is outside call")
                from_scope = call_scope
                to_scope, to_expression = call_scope, f"sink:{call['targetExpression']}[{argument_index}]"
                evidence = {"callFactId": call["id"], "argumentIndex": argument_index, "objectEntryFactId": object_fact_id}
            else:
                raise FlowProposalError(f"unsupported flow step kind: {kind}")
            edge = {
                "index": index,
                "kind": kind,
                "from": node(from_scope, from_expression),
                "to": node(to_scope, to_expression),
                "evidence": evidence,
            }
            if edges:
                require(edges[-1]["to"] == edge["from"], f"flow {flow.get('flowId')} is not contiguous at step {index}")
            edges.append(edge)
        require(edges, "flow has no steps")
        require(edges[0]["from"] == flow.get("sourceNode"), "flow source differs")
        require(edges[-1]["to"] == flow.get("sinkNode"), "flow sink differs")
        flow_receipts.append({
            "flowId": flow.get("flowId"),
            "repositoryId": repository_id,
            "sourceNode": edges[0]["from"],
            "sinkNode": edges[-1]["to"],
            "edgeCount": len(edges),
            "edges": edges,
            "pathEstablished": True,
        })
    require(len(flow_receipts) >= 2, "at least two repository flows are required")
    require({flow["repositoryId"] for flow in flow_receipts} == set(revisions), "flows do not cover every repository")
    require(all(flow["pathEstablished"] for flow in flow_receipts), "not every bounded path is established")
    return {
        "schema": SCHEMA,
        "status": "bounded-syntactic-flow-proposal-review-required",
        "candidateId": packet.get("candidateId"),
        "sourceSetSha256": packet.get("sourceSetSha256"),
        "reviewPacketSha256": sha256_file(packet_path),
        "planSha256": sha256_file(plan_path),
        "repositoryCount": len(repository_receipts),
        "flowCount": len(flow_receipts),
        "allBoundedPathsEstablished": True,
        "repositories": repository_receipts,
        "sourceBridges": all_bridge_receipts,
        "flows": flow_receipts,
        "coverage": "Plan-bounded syntactic dependencies, exact local argument-to-parameter mappings, and exact Git-blob template bridges only; no type, alias, call-target, reachability, dominance, dataflow, behavioral, or semantic resolution.",
        "interpretation": "The exact revisions contain reviewable syntactic paths from purchase-data observations to purchase completion or consumption calls. The paths are Oracle hypotheses, not evidence of a defect, correct repair, or cross-repository behavioral equivalence.",
        "semanticAlignmentVerified": False,
        "behaviorOracleVerified": False,
        "allowsCaseContract": False,
        "automaticPromotion": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--analysis", action="append", default=[], metavar="REPOSITORY_ID=PATH")
    parser.add_argument("--facts", action="append", default=[], metavar="REPOSITORY_ID=PATH")
    parser.add_argument("--repository", action="append", default=[], metavar="REPOSITORY_ID=PATH")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = build(
        args.plan,
        args.packet,
        mappings(args.analysis, "analysis"),
        mappings(args.facts, "facts"),
        mappings(args.repository, "repository"),
    )
    require(not args.output.exists(), "refusing to overwrite flow proposal")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "status": result["status"], "flowCount": result["flowCount"]}, sort_keys=True))


if __name__ == "__main__":
    main()
