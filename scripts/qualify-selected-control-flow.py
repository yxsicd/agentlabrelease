#!/usr/bin/env python3
"""Qualify exact, selected source-level control-flow paths without claiming runtime success."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


SCHEMA = "agentlab.selected_control_flow_qualification.v1"
PLAN_SCHEMA = "agentlab.selected_control_flow_plan.v1"
PROGRAM_SCHEMA = "agentlab.bounded_expression_flow_program_analysis.v1"
OBJECT_SCHEMA = "agentlab.cordova_object_flow_qualification.v1"
REVISION = re.compile(r"[0-9a-f]{40}")
ALLOWED_EDGE_KINDS = {
    "route",
    "lifecycle-callback",
    "ui-event",
    "direct-call",
    "array-callback",
    "promise-fulfillment",
    "promise-rejection",
    "await-fulfillment",
    "await-rejection",
    "guard-true",
    "guard-false",
    "exception",
    "render-binding",
    "recovery-handoff",
}
ASYNC_PAIRS = {
    "promise": {"promise-fulfillment", "promise-rejection"},
    "await": {"await-fulfillment", "await-rejection"},
}


class SelectedControlFlowError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise SelectedControlFlowError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SelectedControlFlowError(f"cannot read {label}: {error}") from error
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


def safe_relative_path(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not value.startswith("/")
        and "\\" not in value
        and all(part not in ("", ".", "..") for part in value.split("/"))
    )


def verify_files(
    repository: Path,
    revision: str,
    entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    require(git(repository, "rev-parse", "HEAD") == revision, "control-flow checkout revision differs")
    receipts: list[dict[str, Any]] = []
    texts: dict[str, str] = {}
    seen: set[str] = set()
    for entry in entries:
        require(isinstance(entry, dict), "control-flow source file is invalid")
        source_path = entry.get("path")
        require(safe_relative_path(source_path) and source_path not in seen, "control-flow source path is unsafe or repeated")
        seen.add(source_path)
        listing = str(git(repository, "ls-tree", revision, "--", source_path)).split()
        require(len(listing) >= 4 and listing[1] == "blob", "control-flow source is not a Git blob")
        require(listing[2] == entry.get("gitBlobOid"), "control-flow Git Blob OID differs")
        content = git(repository, "cat-file", "blob", f"{revision}:{source_path}", binary=True)
        require(isinstance(content, bytes), "control-flow Git blob read failed")
        content_sha256 = digest_bytes(content)
        require(content_sha256 == entry.get("contentSha256"), "control-flow content digest differs")
        text = content.decode("utf-8")
        texts[source_path] = text
        snippets = entry.get("exactSnippets")
        require(isinstance(snippets, list) and snippets, "control-flow exact snippets are absent")
        snippet_receipts = []
        for snippet in snippets:
            require(isinstance(snippet, str) and snippet, "control-flow exact snippet is invalid")
            occurrences = text.count(snippet)
            require(occurrences == 1, f"control-flow exact snippet occurrence differs in {source_path}")
            snippet_receipts.append({"sha256": digest_bytes(snippet.encode()), "occurrences": occurrences})
        receipts.append({
            "path": source_path,
            "sourceRevision": revision,
            "gitBlobOid": listing[2],
            "contentSha256": content_sha256,
            "exactSnippets": snippet_receipts,
        })
    return receipts, texts


def dominators(entry: str, nodes: set[str], predecessors: dict[str, set[str]]) -> dict[str, set[str]]:
    values = {node: ({entry} if node == entry else set(nodes)) for node in nodes}
    changed = True
    while changed:
        changed = False
        for node in sorted(nodes - {entry}):
            parents = predecessors[node]
            updated = {node} | (set.intersection(*(values[parent] for parent in parents)) if parents else set())
            if updated != values[node]:
                values[node] = updated
                changed = True
    return values


def verify_flow(flow: dict[str, Any], texts: dict[str, str], program: dict[str, Any]) -> dict[str, Any]:
    flow_id = flow.get("flowId")
    require(isinstance(flow_id, str) and flow_id, "selected control-flow id is invalid")
    program_flow_id = flow.get("programFlowId")
    program_flows = [row for row in program.get("flows") or [] if isinstance(row, dict) and row.get("flowId") == program_flow_id]
    require(len(program_flows) == 1, f"selected program flow differs: {flow_id}")
    program_flow = program_flows[0]
    require(program_flow.get("repositoryId") == flow.get("repositoryId"), f"selected flow repository differs: {flow_id}")

    nodes_value = flow.get("nodes")
    require(isinstance(nodes_value, list) and len(nodes_value) >= 4, f"selected control-flow nodes are absent: {flow_id}")
    nodes: dict[str, dict[str, Any]] = {}
    for node in nodes_value:
        require(isinstance(node, dict), f"selected control-flow node is invalid: {flow_id}")
        node_id = node.get("id")
        require(isinstance(node_id, str) and node_id and node_id not in nodes, f"selected control-flow node id differs: {flow_id}")
        source_path = node.get("path")
        anchor = node.get("exactSnippet")
        require(source_path in texts and isinstance(anchor, str) and anchor, f"selected control-flow node anchor differs: {node_id}")
        require(texts[source_path].count(anchor) == 1, f"selected control-flow node anchor occurrence differs: {node_id}")
        nodes[node_id] = node

    entry = flow.get("entryNode")
    sink = flow.get("sinkNode")
    require(entry in nodes and sink in nodes and entry != sink, f"selected control-flow endpoints differ: {flow_id}")
    sink_fact_id = nodes[sink].get("factId")
    sink_steps = [
        row for row in program_flow.get("steps") or []
        if isinstance(row, dict) and row.get("kind") == "call-argument-to-sink"
    ]
    require(len(sink_steps) == 1 and sink_steps[0].get("callFactId") == sink_fact_id, f"selected sink fact differs: {flow_id}")

    for region in flow.get("orderedRegions") or []:
        require(isinstance(region, dict) and region.get("path") in texts, f"ordered region path differs: {flow_id}")
        source = texts[region["path"]]
        start = region.get("startSnippet")
        end = region.get("endSnippet")
        ordered = region.get("nodeIds")
        require(isinstance(start, str) and source.count(start) == 1, f"ordered region start differs: {flow_id}")
        require(isinstance(end, str) and source.count(end) == 1, f"ordered region end differs: {flow_id}")
        start_index = source.index(start)
        end_index = source.index(end, start_index) + len(end)
        require(isinstance(ordered, list) and ordered, f"ordered region nodes are absent: {flow_id}")
        offsets = []
        for node_id in ordered:
            require(node_id in nodes and nodes[node_id]["path"] == region["path"], f"ordered region node differs: {flow_id}")
            offset = source.index(nodes[node_id]["exactSnippet"])
            require(start_index <= offset < end_index, f"ordered region node is out of bounds: {node_id}")
            offsets.append(offset)
        require(offsets == sorted(offsets) and len(offsets) == len(set(offsets)), f"ordered region order differs: {flow_id}")

    edges_value = flow.get("edges")
    require(isinstance(edges_value, list) and edges_value, f"selected control-flow edges are absent: {flow_id}")
    successors = {node: set() for node in nodes}
    predecessors = {node: set() for node in nodes}
    edge_kinds: set[str] = set()
    branch_groups: dict[str, set[str]] = {}
    seen_edges: set[tuple[str, str, str]] = set()
    for edge in edges_value:
        require(isinstance(edge, dict), f"selected control-flow edge is invalid: {flow_id}")
        source, target, kind = edge.get("from"), edge.get("to"), edge.get("kind")
        require(source in nodes and target in nodes and source != target, f"selected control-flow edge endpoint differs: {flow_id}")
        require(kind in ALLOWED_EDGE_KINDS, f"selected control-flow edge kind differs: {flow_id}")
        identity = (source, target, kind)
        require(identity not in seen_edges, f"selected control-flow edge is repeated: {flow_id}")
        seen_edges.add(identity)
        successors[source].add(target)
        predecessors[target].add(source)
        edge_kinds.add(kind)
        group = edge.get("branchGroup")
        if group is not None:
            require(isinstance(group, str) and group, f"selected branch group is invalid: {flow_id}")
            branch_groups.setdefault(group, set()).add(kind)

    required_edge_kinds = flow.get("requiredEdgeKinds")
    require(isinstance(required_edge_kinds, list) and set(required_edge_kinds) <= edge_kinds, f"selected edge coverage differs: {flow_id}")
    for group, kinds in branch_groups.items():
        if group.startswith("promise:"):
            require(kinds == ASYNC_PAIRS["promise"], f"promise branch pair differs: {group}")
        elif group.startswith("await:"):
            require(kinds == ASYNC_PAIRS["await"], f"await branch pair differs: {group}")
        elif group.startswith("guard:"):
            require(kinds == {"guard-true", "guard-false"}, f"guard branch pair differs: {group}")
        else:
            raise SelectedControlFlowError(f"unsupported selected branch group: {group}")

    reachable = {entry}
    pending = [entry]
    while pending:
        current = pending.pop()
        for target in successors[current] - reachable:
            reachable.add(target)
            pending.append(target)
    require(reachable == set(nodes), f"selected control-flow has unreachable nodes: {flow_id}")
    require(sink in reachable, f"selected sink is unreachable: {flow_id}")
    values = dominators(entry, set(nodes), predecessors)
    required_dominators = flow.get("requiredSinkDominators")
    require(isinstance(required_dominators, list) and entry in required_dominators, f"selected dominator set differs: {flow_id}")
    require(set(required_dominators) <= values[sink], f"selected sink dominators are not established: {flow_id}")

    terminal_exits = flow.get("terminalExitNodes")
    require(isinstance(terminal_exits, list) and terminal_exits, f"selected terminal exits are absent: {flow_id}")
    for node_id in terminal_exits:
        require(node_id in nodes and not successors[node_id] and node_id != sink, f"selected terminal exit differs: {node_id}")
    recovery_handoffs = flow.get("recoveryHandoffNodes") or []
    require(isinstance(recovery_handoffs, list), f"selected recovery handoffs differ: {flow_id}")
    for node_id in recovery_handoffs:
        require(node_id in nodes and not successors[node_id] and node_id != sink, f"selected recovery handoff differs: {node_id}")

    require(any(kind in edge_kinds for kind in ("promise-fulfillment", "await-fulfillment")), f"selected async success is absent: {flow_id}")
    require(any(kind in edge_kinds for kind in ("promise-rejection", "await-rejection")), f"selected async rejection is absent: {flow_id}")
    require("ui-event" in edge_kinds and "route" in edge_kinds, f"selected entry scheduling is absent: {flow_id}")
    return {
        "flowId": flow_id,
        "repositoryId": flow.get("repositoryId"),
        "programFlowId": program_flow_id,
        "entryNode": entry,
        "sinkNode": sink,
        "nodeCount": len(nodes),
        "edgeCount": len(edges_value),
        "edgeKinds": sorted(edge_kinds),
        "sinkDominators": sorted(values[sink]),
        "requiredSinkDominators": required_dominators,
        "terminalExitNodes": terminal_exits,
        "recoveryHandoffNodes": recovery_handoffs,
        "conditionalSinkReachable": True,
        "selectedSinkDominanceEstablished": True,
        "branchPairCount": len(branch_groups),
        "asyncBranchPairCount": sum(group.startswith(("promise:", "await:")) for group in branch_groups),
        "exceptionalBranchCount": sum(
            edge.get("kind") in {"exception", "promise-rejection", "await-rejection"}
            for edge in edges_value
        ),
    }


def qualify(
    program_path: Path,
    object_path: Path,
    plan_path: Path,
    repositories: dict[str, Path],
) -> dict[str, Any]:
    program = load(program_path, "bounded flow program analysis")
    object_flow = load(object_path, "Cordova object-flow qualification")
    plan = load(plan_path, "selected control-flow plan")
    require(program.get("schema") == PROGRAM_SCHEMA, "unsupported bounded flow program analysis")
    require(object_flow.get("schema") == OBJECT_SCHEMA, "unsupported Cordova object-flow qualification")
    require(plan.get("schema") == PLAN_SCHEMA, "unsupported selected control-flow plan")
    require(object_flow.get("status") == "object-flow-qualified-control-flow-review-required", "object-flow qualification status differs")
    require(object_flow.get("programAnalysisSha256") == digest(program_path), "selected control-flow program analysis differs")
    require(plan.get("programAnalysisSha256") == digest(program_path), "selected control-flow plan program digest differs")
    require(plan.get("objectFlowQualificationSha256") == digest(object_path), "selected control-flow plan object digest differs")
    for key in ("candidateId", "sourceSetSha256"):
        require(plan.get(key) == program.get(key) == object_flow.get(key), f"selected control-flow {key} differs")
    remaining = object_flow.get("remainingUnresolved")
    require(isinstance(remaining, list) and len(remaining) == object_flow.get("remainingUnresolvedCount") == 1, "selected control-flow unresolved accounting differs")
    boundary = plan.get("resolvedBoundary")
    require(isinstance(boundary, dict) and boundary.get("id") == "global:reachability-dominance-exception-flow", "selected control-flow boundary differs")
    require(remaining[0].get("id") == boundary.get("id") and remaining[0].get("class") == boundary.get("class") == "control-flow", "selected control-flow does not resolve the retained boundary")

    repository_plans = plan.get("repositories")
    require(isinstance(repository_plans, list) and len(repository_plans) == 2, "selected control-flow repository set differs")
    require(set(repositories) == {row.get("repositoryId") for row in repository_plans if isinstance(row, dict)}, "selected control-flow checkout set differs")
    all_texts: dict[str, dict[str, str]] = {}
    file_receipts: list[dict[str, Any]] = []
    for repository_plan in repository_plans:
        repository_id = repository_plan.get("repositoryId")
        revision = repository_plan.get("sourceRevision")
        require(isinstance(revision, str) and REVISION.fullmatch(revision), "selected control-flow revision is invalid")
        files = repository_plan.get("files")
        require(isinstance(files, list) and files, "selected control-flow file set is absent")
        receipts, texts = verify_files(repositories[repository_id], revision, files)
        all_texts[repository_id] = texts
        file_receipts.extend({"repositoryId": repository_id, **row} for row in receipts)

    flows = plan.get("flows")
    require(isinstance(flows, list) and len(flows) == 2, "selected control-flow flow set differs")
    require({row.get("repositoryId") for row in flows if isinstance(row, dict)} == set(repositories), "selected control-flow coverage differs")
    flow_receipts = [verify_flow(flow, all_texts[flow["repositoryId"]], program) for flow in flows]
    scope = plan.get("qualificationScope")
    require(isinstance(scope, dict), "selected control-flow scope is absent")
    require(scope.get("selectedSourcePathsOnly") is True, "selected control-flow scope is not bounded")
    require(scope.get("wholeApplicationReachability") is False, "selected control-flow plan claims whole-application reachability")
    require(scope.get("externalApiSuccess") is False, "selected control-flow plan claims external API success")
    require(scope.get("frameworkRuntimeCorrectness") is False, "selected control-flow plan claims framework runtime correctness")
    return {
        "schema": SCHEMA,
        "status": "selected-control-flow-qualified-semantic-review-required",
        "candidateId": program.get("candidateId"),
        "sourceSetSha256": program.get("sourceSetSha256"),
        "reviewPacketSha256": program.get("reviewPacketSha256"),
        "programAnalysisSha256": digest(program_path),
        "objectFlowQualificationSha256": digest(object_path),
        "planSha256": digest(plan_path),
        "resolvedUnresolvedIds": [boundary["id"]],
        "originalUnresolvedCount": 1,
        "remainingUnresolved": [],
        "remainingUnresolvedCount": 0,
        "repositoryCount": len(repository_plans),
        "flowCount": len(flow_receipts),
        "files": file_receipts,
        "flows": flow_receipts,
        "selectedControlFlowResolved": True,
        "conditionalReachabilityEstablished": True,
        "sinkDominanceEstablished": True,
        "exceptionExitsEnumerated": True,
        "callbackSchedulingResolved": True,
        "externalCallContractsResolved": True,
        "typeResolutionComplete": True,
        "aliasResolutionComplete": True,
        "reachabilityAndDominanceResolved": True,
        "qualificationScope": scope,
        "semanticAlignmentVerified": False,
        "behaviorOracleVerified": False,
        "allowsCaseContract": False,
        "automaticPromotion": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--program-analysis", required=True, type=Path)
    parser.add_argument("--object-flow-qualification", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--harmony-repository", required=True, type=Path)
    parser.add_argument("--cordova-repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = qualify(
        args.program_analysis,
        args.object_flow_qualification,
        args.plan,
        {
            "harmony-iap-client": args.harmony_repository,
            "hms-cordova-iap": args.cordova_repository,
        },
    )
    require(not args.output.exists(), "refusing to overwrite selected control-flow qualification")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": SCHEMA,
        "status": result["status"],
        "flowCount": result["flowCount"],
        "remainingUnresolvedCount": result["remainingUnresolvedCount"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
