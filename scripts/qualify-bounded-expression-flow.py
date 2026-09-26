#!/usr/bin/env python3
"""Replay a bounded flow and qualify the program-analysis claims it can support."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from typing import Any


SCHEMA = "agentlab.bounded_expression_flow_program_analysis.v1"
FLOW_SCHEMA = "agentlab.bounded_expression_flow_proposal.v1"
IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")


class ProgramFlowQualificationError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ProgramFlowQualificationError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProgramFlowQualificationError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_flow_builder():
    path = Path(__file__).with_name("build-bounded-expression-flow-proposal.py")
    spec = importlib.util.spec_from_file_location("agentlab_bounded_flow_builder", path)
    require(spec is not None and spec.loader is not None, "cannot load bounded flow builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parameter(expression: str) -> tuple[str, str | None]:
    value = expression.strip().removeprefix("...").split("=", 1)[0].strip()
    match = IDENTIFIER.match(value)
    require(match is not None, f"cannot parse parameter expression: {expression}")
    name = match.group(0)
    suffix = value[match.end():].strip()
    if not suffix:
        return name, None
    require(suffix.startswith(":"), f"unsupported parameter expression: {expression}")
    type_expression = suffix[1:].strip()
    return name, type_expression or None


def expression_references(expression: Any, dependency: Any) -> bool:
    if not isinstance(expression, str) or not isinstance(dependency, str) or not dependency:
        return False
    if expression.strip() == dependency.strip():
        return True
    dependency_tokens = IDENTIFIER.findall(dependency)
    if not dependency_tokens:
        return False
    expression_tokens = IDENTIFIER.findall(expression)
    width = len(dependency_tokens)
    return any(
        expression_tokens[index:index + width] == dependency_tokens
        for index in range(len(expression_tokens) - width + 1)
    )


def callable_name(row: dict[str, Any]) -> Any:
    return row.get("symbol") if row.get("kind") == "symbol" else row.get("name")


def qualify(
    plan_path: Path,
    packet_path: Path,
    flow_path: Path,
    analyses: dict[str, Path],
    facts: dict[str, Path],
    repositories: dict[str, Path],
) -> dict[str, Any]:
    flow_builder = load_flow_builder()
    try:
        replayed = flow_builder.build(plan_path, packet_path, analyses, facts, repositories)
    except Exception as error:
        raise ProgramFlowQualificationError(f"bounded flow replay failed: {error}") from error
    retained = load(flow_path, "bounded flow proposal")
    require(retained.get("schema") == FLOW_SCHEMA, "unsupported bounded flow proposal")
    require(replayed == retained, "retained bounded flow proposal differs from exact replay")
    plan = load(plan_path, "bounded flow plan")

    repository_rows: dict[str, list[dict[str, Any]]] = {}
    repository_by_id: dict[str, dict[str, dict[str, Any]]] = {}
    for repository_id, facts_path in facts.items():
        rows, by_id = flow_builder.read_facts(
            facts_path,
            load(analyses[repository_id], f"{repository_id} analysis")["sha256"],
        )
        repository_rows[repository_id] = rows
        repository_by_id[repository_id] = by_id

    flow_receipts: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    local_call_count = 0
    typed_parameter_count = 0
    untyped_parameter_count = 0
    exact_dependency_count = 0
    template_bridge_count = 0
    external_sink_count = 0

    for flow in plan.get("flows") or []:
        repository_id = flow.get("repositoryId")
        require(repository_id in repository_rows, "flow repository is unknown")
        rows = repository_rows[repository_id]
        by_id = repository_by_id[repository_id]
        step_receipts: list[dict[str, Any]] = []
        for index, step in enumerate(flow.get("steps") or []):
            kind = step.get("kind")
            receipt: dict[str, Any] = {"index": index, "kind": kind, "status": "verified"}
            if kind == "call-argument-to-parameter":
                call = by_id[step["callFactId"]]
                target = by_id[step["callableFactId"]]
                target_name = callable_name(target)
                target_owner = target.get("owner")
                candidates = [
                    row for row in rows
                    if row.get("kind") in {"symbol", "property"}
                    and row.get("path") == call.get("path")
                    and row.get("owner") == target_owner
                    and callable_name(row) == target_name
                    and row.get("parameterExpressions") is not None
                ]
                require(len(candidates) == 1, f"local call target is not unique for {step['callFactId']}")
                require(candidates[0].get("id") == target.get("id"), "local call target differs from unique definition")
                parameter_expression = target["parameterExpressions"][step["parameterIndex"]]
                parameter_name, type_expression = parameter(parameter_expression)
                argument_expression = call["argumentExpressions"][step["argumentIndex"]]
                require(parameter_name == replayed["flows"][len(flow_receipts)]["edges"][index]["to"].rsplit("::", 1)[-1], "replayed parameter differs")
                receipt.update({
                    "callFactId": call["id"],
                    "callableFactId": target["id"],
                    "resolution": "unique-same-file-owner-callable",
                    "argumentExpression": argument_expression,
                    "parameterExpression": parameter_expression,
                    "parameterTypeExpression": type_expression,
                })
                local_call_count += 1
                if type_expression:
                    typed_parameter_count += 1
                else:
                    untyped_parameter_count += 1
                    unresolved.append({
                        "id": f"untyped-parameter:{repository_id}:{target['id']}:{step['parameterIndex']}",
                        "class": "parameter-type",
                        "repositoryId": repository_id,
                        "factId": target["id"],
                        "reason": "The exact local parameter has no source type annotation.",
                    })
            elif kind == "binding-dependency":
                fact = by_id[step["factId"]]
                require(expression_references(fact.get("initializerExpression"), step.get("dependsOn")), "binding dependency is not an exact token sequence")
                receipt.update({
                    "factId": fact["id"],
                    "dependencyExpression": step["dependsOn"],
                    "bindingName": fact["name"],
                    "bindingKind": fact.get("bindingKind"),
                    "declaredTypeExpression": fact.get("typeExpression") or None,
                    "resolution": "exact-identifier-token-dependency",
                })
                exact_dependency_count += 1
            elif kind == "assignment-dependency":
                fact = by_id[step["factId"]]
                require(fact.get("rightExpression") and fact.get("leftExpression"), "assignment dependency is incomplete")
                receipt.update({
                    "factId": fact["id"],
                    "rightExpression": fact["rightExpression"],
                    "leftExpression": fact["leftExpression"],
                    "resolution": "exact-assignment-edge",
                })
                exact_dependency_count += 1
                unresolved.append({
                    "id": f"member-alias:{repository_id}:{fact['id']}",
                    "class": "alias-and-object-identity",
                    "repositoryId": repository_id,
                    "factId": fact["id"],
                    "reason": "A member assignment is exact, but object identity and later aliases are not resolved.",
                })
            elif kind == "template-event-bridge":
                receipt.update({
                    "callableFactId": step["callableFactId"],
                    "path": step["path"],
                    "gitBlobOid": step["gitBlobOid"],
                    "contentSha256": step["contentSha256"],
                    "resolution": "exact-git-blob-positional-template-call",
                })
                template_bridge_count += 1
                unresolved.append({
                    "id": f"template-object-identity:{repository_id}:{step['callableFactId']}",
                    "class": "alias-and-object-identity",
                    "repositoryId": repository_id,
                    "factId": step["callableFactId"],
                    "reason": "The template call is exact, but the rendered object identity is not proven to be the earlier assigned object.",
                })
            elif kind == "call-argument-to-sink":
                call = by_id[step["callFactId"]]
                require(expression_references(call["argumentExpressions"][step["argumentIndex"]], step.get("dependsOn")), "sink dependency is not an exact token sequence")
                receipt.update({
                    "callFactId": call["id"],
                    "targetExpression": call["targetExpression"],
                    "argumentIndex": step["argumentIndex"],
                    "dependencyExpression": step["dependsOn"],
                    "resolution": "exact-external-call-argument-unresolved-signature",
                })
                exact_dependency_count += 1
                external_sink_count += 1
                unresolved.append({
                    "id": f"external-sink-signature:{repository_id}:{call['id']}",
                    "class": "external-call-contract",
                    "repositoryId": repository_id,
                    "factId": call["id"],
                    "reason": "The sink argument is exact, but the external SDK signature and behavior are not resolved from this source cut.",
                })
            else:
                raise ProgramFlowQualificationError(f"unsupported flow step kind: {kind}")
            step_receipts.append(receipt)
        flow_receipts.append({
            "flowId": flow.get("flowId"),
            "repositoryId": repository_id,
            "stepCount": len(step_receipts),
            "steps": step_receipts,
            "boundedProgramEdgesVerified": True,
        })

    unresolved.append({
        "id": "global:reachability-dominance-exception-flow",
        "class": "control-flow",
        "reason": "The bounded facts do not establish runtime reachability, dominance, exception flow, or callback scheduling.",
    })
    require(local_call_count > 0, "no local call targets were qualified")
    require(exact_dependency_count > 0, "no exact dependencies were qualified")
    require(unresolved, "qualification must retain unresolved program-analysis boundaries")
    return {
        "schema": SCHEMA,
        "status": "bounded-program-flow-partially-resolved-review-required",
        "candidateId": retained.get("candidateId"),
        "sourceSetSha256": retained.get("sourceSetSha256"),
        "reviewPacketSha256": retained.get("reviewPacketSha256"),
        "flowPlanSha256": digest(plan_path),
        "flowProposalSha256": digest(flow_path),
        "flowReplayExact": True,
        "repositoryCount": retained.get("repositoryCount"),
        "flowCount": len(flow_receipts),
        "flows": flow_receipts,
        "coverage": {
            "localCallTargetCount": local_call_count,
            "localCallTargetsUniquelyResolved": True,
            "typedParameterMappingCount": typed_parameter_count,
            "untypedParameterMappingCount": untyped_parameter_count,
            "exactDependencyCount": exact_dependency_count,
            "exactDependencyReferencesVerified": True,
            "templateBridgeCount": template_bridge_count,
            "externalSinkCount": external_sink_count,
        },
        "unresolved": unresolved,
        "unresolvedCount": len(unresolved),
        "typeResolutionComplete": untyped_parameter_count == 0 and external_sink_count == 0,
        "aliasResolutionComplete": False,
        "externalCallContractsResolved": False,
        "reachabilityAndDominanceResolved": False,
        "semanticAlignmentVerified": False,
        "behaviorOracleVerified": False,
        "allowsCaseContract": False,
        "automaticPromotion": False,
    }


def mappings(values: list[str], label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        repository_id, separator, raw_path = value.partition("=")
        require(separator == "=" and repository_id and raw_path, f"invalid {label} mapping")
        require(repository_id not in result, f"duplicate {label} repository id")
        result[repository_id] = Path(raw_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--flow-proposal", required=True, type=Path)
    parser.add_argument("--analysis", action="append", default=[], metavar="REPOSITORY_ID=PATH")
    parser.add_argument("--facts", action="append", default=[], metavar="REPOSITORY_ID=PATH")
    parser.add_argument("--repository", action="append", default=[], metavar="REPOSITORY_ID=PATH")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = qualify(
        args.plan,
        args.packet,
        args.flow_proposal,
        mappings(args.analysis, "analysis"),
        mappings(args.facts, "facts"),
        mappings(args.repository, "repository"),
    )
    require(not args.output.exists(), "refusing to overwrite program-flow qualification")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": SCHEMA,
        "status": result["status"],
        "flowCount": result["flowCount"],
        "unresolvedCount": result["unresolvedCount"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
