#!/usr/bin/env python3
"""Turn one newly semantic-ready scope into a non-promoted case hypothesis."""
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


SAFE_ID = re.compile(r"shadow-case-[a-z0-9-]{8,140}")
SHA1 = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
TITLE_MIN_LENGTH = 8
TITLE_MAX_LENGTH = 180
MECHANISM_MIN_LENGTH = 80
MECHANISM_MAX_LENGTH = 1600
STAGED_DEMANDS_LIMITS = (2, 3)
EDITABLE_PATHS_LIMITS = (1, 8)
CONTEXT_PATHS_LIMITS = (0, 12)
OBSERVABLES_LIMITS = (2, 8)
ENVIRONMENT_LIMITS = (1, 8)
WRONG_VARIANTS_LIMITS = (2, 8)
LIMITATIONS_LIMITS = (2, 8)
EMULATOR_MARKERS = ("emulator", "模拟器")
EXTERNAL_HARDWARE_PATTERNS = {
    "serial-peripheral": re.compile(r"\b(?:serial(?: port)?|uart)\b|串口", re.IGNORECASE),
    "usb-peripheral": re.compile(r"\busb\b|USB设备|USB外设", re.IGNORECASE),
    "attached-peripheral": re.compile(
        r"\b(?:attached|external) (?:hardware|peripheral|device)\b|外接(?:硬件|外设|设备)",
        re.IGNORECASE,
    ),
}
HARDWARE_TERM = re.compile(
    r"\b(?:physical[- ]device|serial(?: port)?|uart|usb)\b|"
    r"\b(?:attached|external) (?:hardware|peripheral|device)\b|"
    r"真机|串口|外接(?:硬件|外设|设备)",
    re.IGNORECASE,
)
HARDWARE_NEGATION = re.compile(
    r"\b(?:no|without|does not require|doesn't require|not require|not use)\b|"
    r"无需|不依赖|不使用|不需要",
    re.IGNORECASE,
)
NEGATION_BOUNDARY = re.compile(
    r"(\b(?:but|however|except)\b|但是|但|却|[.;:。；：\n])",
    re.IGNORECASE,
)


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def value_digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def validate_lineage(root: Path) -> tuple[list[dict], list[dict], dict]:
    """Validate the frozen producer inputs before any model budget is spent."""
    parsed, digests = [], {}
    for name in ("case_generation_rounds.jsonl", "case_generation_candidates.jsonl"):
        path = root / name
        require(path.is_file() and not path.is_symlink(), "shadow lineage input is absent or unsafe")
        require(path.stat().st_size <= 1024 * 1024, "shadow lineage input exceeds budget")
        raw = path.read_bytes()
        values = [json.loads(line) for line in raw.split(b"\n") if line.strip()]
        require(len(values) <= 5000, "shadow lineage row budget exceeded")
        require(all(isinstance(row, dict) and isinstance(row.get("id"), str)
                    and 1 <= len(row["id"]) <= 192 for row in values), "shadow lineage row identity is invalid")
        require(len({row["id"] for row in values}) == len(values), "shadow lineage row identity is duplicated")
        parsed.append(values)
        digests[name] = hashlib.sha256(raw).hexdigest()
    rounds, candidates = parsed
    require(rounds, "case generation lineage is empty")
    indices = [row.get("roundIndex") for row in rounds]
    require(all(type(index) is int and index > 0 for index in indices)
            and sorted(indices) == list(range(1, len(indices) + 1)), "shadow lineage round indices are invalid")
    for row in rounds:
        qualification = row.get("qualification", {})
        require(isinstance(qualification, dict), "shadow lineage qualification is invalid")
        qualified = qualification.get("oracleQualifiedIds", [])
        require(isinstance(qualified, list) and all(isinstance(value, str) for value in qualified),
                "shadow lineage Oracle inventory is invalid")
    return rounds, candidates, digests


def verify_lineage_binding(request: dict, root: Path) -> None:
    if "caseLineageInputsSha256" in request:
        _, _, observed = validate_lineage(root)
        require(observed == request["caseLineageInputsSha256"], "frozen shadow lineage changed")


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(canonical(value) + b"\n" for value in values))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def proposal_field_constraints() -> str:
    """Render the same size limits enforced by the shadow proposal gate."""
    return (
        f"- title: concise task title ({TITLE_MIN_LENGTH}-{TITLE_MAX_LENGTH} characters)\n"
        "- mechanism: the concrete state, lifecycle, boundary, or cross-file difficulty "
        f"being tested ({MECHANISM_MIN_LENGTH}-{MECHANISM_MAX_LENGTH} characters)\n"
        f"- stagedDemands: {STAGED_DEMANDS_LIMITS[0]}-{STAGED_DEMANDS_LIMITS[1]} "
        "user-visible requirements whose later stage can expose an earlier design mistake\n"
        f"- editablePaths: {EDITABLE_PATHS_LIMITS[0]}-{EDITABLE_PATHS_LIMITS[1]} evidence "
        "paths inside the selected scope\n"
        f"- contextPaths: {CONTEXT_PATHS_LIMITS[0]}-{CONTEXT_PATHS_LIMITS[1]} other evidence "
        "paths, disjoint from editablePaths"
    )


def path_is_within(path: str, boundary: str) -> bool:
    boundary = boundary.rstrip("/")
    return path == boundary or path.startswith(boundary + "/")


def scope_owns_path(scope: dict, path: str) -> bool:
    selectors = scope.get("ownershipSelectors")
    if not selectors:
        return path_is_within(path, scope["pathBoundary"])
    return any(
        (selector.get("type") == "prefix" and path_is_within(path, selector.get("path", "")))
        or (selector.get("type") == "files" and path in selector.get("paths", []))
        for selector in selectors
    )


def previous_oracle_count(rounds: list[dict]) -> int:
    return len({
        candidate_id
        for row in rounds
        for candidate_id in (row.get("qualification") or {}).get("oracleQualifiedIds", [])
    })


def positive_hardware_requirements(text: str) -> str:
    """Remove negated hardware lists while preserving later contrastive requirements."""
    parts = NEGATION_BOUNDARY.split(text)
    for index in range(0, len(parts), 2):
        part = parts[index]
        negation = HARDWARE_NEGATION.search(part)
        if negation and HARDWARE_TERM.search(part, negation.end()):
            parts[index] = part[:negation.start()]
    return "".join(parts)


def external_hardware_blockers(scope: dict, fact: dict) -> list[str]:
    """Return generic external-hardware signals without repository-specific rules."""
    text_values = [
        scope.get("documentedTitle"), scope.get("documentedPurpose"),
        scope.get("responsibility"), fact.get("id"), fact.get("interpretation"),
        *(fact.get("limitations") or []), *(scope.get("externalDependencies") or []),
    ]
    text = positive_hardware_requirements(
        "\n".join(value for value in text_values if isinstance(value, str))
    )
    return [name for name, pattern in EXTERNAL_HARDWARE_PATTERNS.items() if pattern.search(text)]


def require_emulator_environment(values: list[str]) -> None:
    text = "\n".join(values)
    positive_requirements = positive_hardware_requirements(text)
    blockers = [
        name for name, pattern in EXTERNAL_HARDWARE_PATTERNS.items()
        if pattern.search(positive_requirements)
    ]
    require(not blockers, f"shadow environment requires external hardware: {','.join(blockers)}")
    require(not re.search(r"\bphysical device\b|真机", positive_requirements, re.IGNORECASE),
            "shadow environment requires a physical device")
    require(any(marker in text.lower() for marker in EMULATOR_MARKERS),
            "shadow environment does not require a HarmonyOS emulator")


def runtime_target(policy: dict, scope: dict) -> str:
    target = policy.get("runtimeTarget")
    require(target in ("harmony-emulator", "repository-test"),
            "shadow request runtime target differs")
    require(target == "harmony-emulator" or not any(
        "ohosTest" in path for path in scope.get("testEntrypoints", [])),
        "ohosTest scope requires the Harmony emulator runtime")
    require(policy.get("externalHardwareAllowed") is False,
            "shadow request permits external hardware")
    require(policy.get("physicalDeviceFallbackAllowed") is False,
            "shadow request permits physical-device fallback")
    return target


def oracle_framework(policy: dict, scope: dict) -> str:
    target = runtime_target(policy, scope)
    if "oracleFramework" in policy:
        expected = "ohosTest" if target == "harmony-emulator" else "repository-test"
        require(policy["oracleFramework"] == expected, "shadow Oracle framework conflicts with runtime")
        return expected
    # Retained requests bind the old inference; never silently rewrite their cuts.
    return "ohosTest" if any("ohosTest" in p for p in scope.get("testEntrypoints", [])) else "repository-test"


def select_iteration(loop_receipt: dict, facts: dict[str, dict], existing: list[dict]) -> tuple[dict, dict]:
    iterations = loop_receipt.get("iterations")
    require(isinstance(iterations, list) and iterations, "bounded loop has no completed iterations")
    repository_counts: dict[str, int] = {}
    for row in existing:
        repository_id = row.get("repositoryId")
        if isinstance(repository_id, str):
            repository_counts[repository_id] = repository_counts.get(repository_id, 0) + 1
    eligible = []
    for offset, iteration in enumerate(iterations):
        fact_ids = iteration.get("acceptedFactIds")
        scope_ids = iteration.get("scopeIds")
        if fact_ids is None and scope_ids is None:
            fact_ids = [iteration.get("acceptedFactId")]
            scope_ids = [iteration.get("scope")]
        require(isinstance(fact_ids, list) and fact_ids,
                "loop iteration has no accepted facts")
        require(isinstance(scope_ids, list) and len(scope_ids) == len(fact_ids),
                "loop scope and fact batch sizes differ")
        for batch_offset, (fact_id, scope_id) in enumerate(zip(fact_ids, scope_ids)):
            fact = facts.get(fact_id)
            if not fact:
                continue
            require(fact.get("scopeSkillIds") == [scope_id],
                    "loop scope and fact binding differ")
            require(fact.get("repositoryId") == iteration.get("repository"),
                    "loop repository and fact binding differ")
            selected = dict(iteration)
            selected["scope"] = scope_id
            selected["acceptedFactId"] = fact_id
            eligible.append((repository_counts.get(fact["repositoryId"], 0), offset,
                             batch_offset, selected, fact))
    require(eligible, "bounded loop has no exported accepted fact")
    _, _, _, iteration, fact = min(eligible, key=lambda item: item[:3])
    return iteration, fact


def prepare(args) -> None:
    knowledge = args.knowledge
    cut_path = knowledge / "maintainer-knowledge-cut.json"
    cut = load(cut_path)
    scopes = {row["id"]: row for row in rows(knowledge / "maintainer_scope_skills.jsonl")}
    facts = {row["id"]: row for row in rows(knowledge / "program_facts.jsonl")}
    lineage = getattr(args, "lineage_root", None) or knowledge
    _, existing, lineage_digests = validate_lineage(lineage)
    loop_receipt = load(args.loop_receipt)
    iteration, fact = select_iteration(loop_receipt, facts, existing)
    scope = scopes.get(iteration["scope"])
    require(scope is not None, "selected scope is absent from the exported knowledge cut")
    repository = next(
        (row for row in cut.get("repositories", []) if row.get("id") == fact["repositoryId"]), None
    )
    require(repository is not None, "selected repository is absent from the knowledge cut")
    require(scope.get("sourceRevision") == fact.get("sourceRevision") == repository.get("revision"),
            "shadow input revisions differ")
    latest_refresh = max(rows(knowledge / "maintainer_skill_refresh_rounds.jsonl"),
                         key=lambda row: row["roundIndex"])
    candidate_id = f"shadow-case-{fact['id'].removeprefix('agent-analysis-')}"
    require(SAFE_ID.fullmatch(candidate_id), "derived shadow candidate id is invalid")
    request = {
        "schema": "agentlab.case_generation_shadow_request.v1",
        "automaticPromotion": False,
        "sourceSetSha256": cut["sourceSetSha256"],
        "knowledgeCutSha256": file_digest(cut_path),
        "maintainerSkillRefreshRoundId": latest_refresh["id"],
        "loopReceiptSha256": file_digest(args.loop_receipt),
        "caseLineageInputsSha256": lineage_digests,
        "loopBefore": loop_receipt["iterations"][0]["before"],
        "loopAfter": loop_receipt["iterations"][-1]["after"],
        "repository": repository,
        "scope": scope,
        "fact": fact,
        "candidateId": candidate_id,
        "policy": {
            "candidateLimit": 1,
            "constructionMode": "shadow",
            "candidateGateRequired": True,
            "independentOracleRequired": True,
            "wrongVariantCalibrationRequired": True,
            "runtimeTarget": getattr(args, "runtime_target", "harmony-emulator"),
            "oracleFramework": "ohosTest" if getattr(args, "runtime_target", "harmony-emulator") == "harmony-emulator" else "repository-test",
            "externalHardwareAllowed": False,
            "physicalDeviceFallbackAllowed": False,
            "shadowEligible": not external_hardware_blockers(scope, fact),
            "blockers": external_hardware_blockers(scope, fact),
        },
        "output": "shadow-case-proposal.json",
    }
    runtime_target(request["policy"], scope)
    write_json(args.output, request)


def request_origin(request: dict) -> dict:
    if request.get("schema") == "agentlab.operation_case_shadow_request.v1":
        require("loopReceiptSha256" not in request, "operation request borrows semantic loop lineage")
        digest = request.get("operationInputsSha256", "")
        require(isinstance(digest, str) and SHA256.fullmatch(digest), "operation inputs digest invalid")
        require(request.get("policy", {}).get("caseCalibrationInherited") is False,
                "maintenance proof cannot inherit case calibration")
        origin = {"operationInputsSha256": digest}
        if "successorConstruction" in request:
            bound = request["successorConstruction"]
            require(bound.get("schema") == "agentlab.shadow_case_successor_inputs.v1"
                    and bound.get("calibrationInherited") is False
                    and bound.get("formalCaseQualified") is False
                    and bound.get("automaticPromotion") is False, "invalid successor construction boundary")
            for key, raw in (("parentRequestSha256", "parentRequestUtf8"),
                             ("parentProposalSha256", "parentProposalUtf8"), ("reviewSha256", "reviewUtf8"),
                             ("contextSha256", "contextUtf8"), ("editBoundarySha256", "editBoundaryUtf8")):
                require(isinstance(bound.get(raw), str)
                        and hashlib.sha256(bound[raw].encode()).hexdigest() == bound["bindings"].get(key),
                        "successor original input digest differs")
            require(json.loads(bound["contextUtf8"]) == bound["sourceContext"]
                    and json.loads(bound["editBoundaryUtf8"]) == bound["editBoundary"],
                    "successor parsed construction inputs differ")
            require(bound["bindings"].get("operationInputsSha256") == digest
                    and bound["bindings"].get("runtimeTarget") == request["policy"].get("runtimeTarget"),
                    "successor operation or runtime binding differs")
            # Native packets retain their historical field name. The parent is
            # an unadmitted proposal, not a stored candidate supersession edge.
            parent_id = bound["parentCandidateId"]
            require(SAFE_ID.fullmatch(parent_id) is not None
                    and json.loads(bound["parentProposalUtf8"]).get("id") == parent_id,
                    "successor parent proposal identity differs")
            origin.update({"parentProposalId": parent_id, **bound["bindings"]})
        return origin
    require(request.get("schema") == "agentlab.case_generation_shadow_request.v1", "bad shadow request")
    require("operationInputsSha256" not in request, "semantic loop request borrows operation lineage")
    return {"loopReceiptSha256": request["loopReceiptSha256"]}


def constructor_evidence(request: dict) -> list[dict]:
    evidence = list(request["fact"].get("evidence", []))
    bound = request.get("successorConstruction")
    if bound:
        for context in (bound["sourceContext"], bound["editBoundary"]["sourceContext"]):
            for item in context["selectedFiles"]:
                prior = next((row for row in evidence if row["path"] == item["path"]), None)
                require(prior is None or prior["gitBlobOid"] == item["gitBlobOid"],
                        "successor context contradicts semantic Blob")
                if prior is None:
                    evidence.append(item)
    return evidence


def constructor_source_bytes(source: Path, item: dict) -> bytes:
    # Native preflight binds context text to committed Blobs even for sparse
    # checkouts; avoid requiring an unrelated full checkout projection.
    return item["contentUtf8"].encode() if "contentUtf8" in item else (source / item["path"]).read_bytes()


def verify_fact_source(request: dict, source: Path) -> None:
    """Verify actual fact-referenced bytes before any constructor can launch."""
    revision = request["repository"]["revision"]
    require(SHA1.fullmatch(revision), "source revision invalid")
    require(subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() == revision,
            "source checkout revision differs")
    require(not subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True),
            "source checkout is dirty before construction")
    evidence = constructor_evidence(request)
    require(isinstance(evidence, list) and evidence, "semantic source evidence absent")
    seen = set()
    for item in evidence:
        relative = item.get("path", "")
        path = Path(relative)
        require(isinstance(relative, str) and relative and not path.is_absolute()
                and all(part not in (".", "..") for part in relative.split("/"))
                and relative not in seen, "semantic evidence path unsafe or duplicated")
        seen.add(relative)
        current = source
        for part in path.parts:
            current = current / part
            require(not current.is_symlink(), "semantic source symlink rejected")
        require("contentUtf8" in item or current.is_file() and current.stat().st_size <= 16 * 1024 * 1024,
                "semantic source is not a bounded file")
        data = constructor_source_bytes(source, item)
        require(len(data) <= 16 * 1024 * 1024, "constructor source exceeds budget")
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        committed = subprocess.check_output(["git", "-C", str(source), "rev-parse", f"{revision}:{relative}"], text=True).strip()
        require(blob == committed == item.get("gitBlobOid"), "semantic source Blob differs")


def prepare_isolated_source(request: dict, source: Path, output: Path, template: Path) -> Path:
    """Rebind the existing isolated runtime to exactly the semantic source bytes."""
    require(template.is_file() and not template.is_symlink(), "runtime template must be a regular file")
    config = load(template)
    require(config.get("schema") == "agentlab.participant_docker_runtime.v1"
            and config.get("executor") == "docker", "unsupported isolated runtime")
    verify_fact_source(request, source)
    case = output / "case-input"
    case.mkdir(parents=True, exist_ok=False)
    inventory = []
    for item in constructor_evidence(request):
        relative = item["path"]
        data = constructor_source_bytes(source, item)
        require(hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
                == item["gitBlobOid"], "projected source Blob differs")
        target = case / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        inventory.append({**item, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    verify_fact_source(request, source)
    write_json(case / "manifest.json", {
        "schema": "agentlab.shadow_constructor_source_input.v1",
        "requestValueSha256": value_digest(request),
        "sourceRevision": request["repository"]["revision"],
        "files": inventory,
        "automaticQualification": False,
    })
    config["caseInputRoot"] = str(case.resolve())
    config["participantManifestSha256"] = file_digest(case / "manifest.json")
    config["forbiddenHostPaths"] = list(dict.fromkeys([
        *config.get("forbiddenHostPaths", []), str(source.resolve()),
    ]))
    runtime = output / "runtime-config.json"
    write_json(runtime, config)
    return runtime


def run_agent(args) -> None:
    verify_lineage_binding(load(args.request), args.request.parent)
    revision = getattr(args, "revision_request", None)
    successor = "successorConstruction" in load(args.request)
    require(not (revision is not None and successor), "draft revision and successor are exclusive")
    if successor:
        require(all(getattr(args, name, None) is not None
                    for name in ("flywheel_tool", "knowledge", "operation_inputs")),
                "successor requires native tool, knowledge and operation inputs")
        args.output.mkdir(parents=True, exist_ok=False)
        subprocess.run([str(args.flywheel_tool), "--validate-operation-case-successor",
                        "--knowledge", str(args.knowledge), "--operation-inputs", str(args.operation_inputs),
                        "--source-worktree", str(args.source.resolve(strict=True)),
                        "--shadow-request", str(args.request),
                        "--output", str(args.output / "successor-validation.json")], check=True)
    elif revision is not None:
        require(all(getattr(args, name, None) is not None
                    for name in ("flywheel_tool", "knowledge", "operation_inputs")),
                "shadow revision requires native tool, knowledge and operation inputs")
        args.output.mkdir(parents=True, exist_ok=False)
        subprocess.run([str(args.flywheel_tool), "--validate-shadow-case-revision",
                        "--knowledge", str(args.knowledge), "--operation-inputs", str(args.operation_inputs),
                        "--shadow-request", str(args.request), "--revision-request", str(revision),
                        "--output", str(args.output / "revision-validation.json")], check=True)
    else:
        require(not any(getattr(args, name, None) is not None
                        for name in ("flywheel_tool", "knowledge", "operation_inputs")),
                "shadow revision dependencies require a revision request")
    template = os.environ.get("AGENTLAB_PARTICIPANT_RUNTIME_CONFIG")
    if not template:
        return run_agent_inner(args)
    runtime = prepare_isolated_source(load(args.request), args.source.resolve(strict=True),
                                      args.output, Path(template))
    os.environ["AGENTLAB_PARTICIPANT_RUNTIME_CONFIG"] = str(runtime.resolve())
    try:
        return run_agent_inner(args)
    finally:
        os.environ["AGENTLAB_PARTICIPANT_RUNTIME_CONFIG"] = template


def participant_options(args) -> dict:
    effort = getattr(args, "reasoning_effort", "default")
    require(effort in ("default", "low", "medium", "high", "max"), "invalid constructor reasoning effort")
    tokens = getattr(args, "max_output_tokens", None)
    require(tokens is None or type(tokens) is int and tokens in (8192, 16384),
            "invalid constructor output token bound")
    return {"reasoning_effort": None if effort == "default" else effort,
            "max_output_tokens": tokens}


def run_agent_inner(args) -> None:
    request = load(args.request)
    request_origin(request)
    require(request["policy"].get("shadowEligible") is True,
            "shadow input is not eligible for the declared runtime")
    target = runtime_target(request["policy"], request["scope"])
    require(not external_hardware_blockers(request["scope"], request["fact"]),
            "shadow input requires external hardware")
    source_root = args.source.resolve(strict=True)
    verify_fact_source(request, source_root)
    workspace = args.output / "workspace"
    evidence = args.output / "evidence"
    workspace.mkdir(parents=True)
    evidence.mkdir()
    shutil.copy2(args.request, workspace / "shadow-request.json")
    frozen_request_sha = file_digest(workspace / "shadow-request.json")
    successor = request.get("successorConstruction")
    if successor:
        require(frozen_request_sha == load(args.output / "successor-validation.json")["requestSha256"],
                "successor request changed after native preflight")
    revision = getattr(args, "revision_request", None)
    if revision is not None:
        shutil.copy2(revision, args.output / "revision-request.json")
        bound = load(args.output / "revision-request.json")
        require(file_digest(args.output / "revision-request.json")
                == load(args.output / "revision-validation.json")["revisionRequestSha256"],
                "shadow revision changed after preflight")
        require(frozen_request_sha == load(args.output / "revision-validation.json")["currentRequestSha256"],
                "shadow request changed after revision preflight")
        (workspace / "parent-proposal.json").write_text(bound["parentProposalUtf8"], encoding="utf-8")
        (workspace / "review-feedback.json").write_text(bound["reviewUtf8"], encoding="utf-8")
    source_link = workspace / "source"
    # Host absolute paths are intentionally absent in the isolated namespace.
    source_link.symlink_to(Path("/agentlab/case/source")
                          if os.environ.get("AGENTLAB_PARTICIPANT_RUNTIME_CONFIG")
                          else source_root, target_is_directory=True)
    participant_path = Path(__file__).resolve().parents[1] / "real-code-agent" / "participant.py"
    spec = importlib.util.spec_from_file_location("agentlab_participant", participant_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    participant = module.Participant(
        evidence, args.output / "participant-state", args.pi, args.gateway, args.model,
        route=args.provider_route, implementation="pi", **participant_options(args),
    )
    scope = request["scope"]
    fact = request["fact"]
    framework = oracle_framework(request["policy"], scope)
    environment_instruction = (
        "The complete functional Oracle must be executable on a HarmonyOS emulator with no physical-device fallback and no attached USB, serial, or other external hardware; name the emulator image/device type in requiredEnvironment."
        if target == "harmony-emulator" else
        "The complete functional Oracle must use the pinned repository's test runner in a controlled host or container, without external hardware or physical-device fallback; name the required runner and environment in requiredEnvironment."
    )
    source_instruction = (
        "Use the primary semantic fact and the successor's explicitly bound owner scopes. "
        "Use only loaded constructor source paths for context and explicitly selected edit paths for changes."
        if successor else
        f"Use only scope {scope['id']} and semantic fact {fact['id']}. Use only paths present in the fact evidence."
    )
    prompt = f"""You are constructing one shadow evaluation-case hypothesis, not assessing an Agent.
Read shadow-request.json and the exact read-only source/ checkout. {source_instruction}
Write exactly one JSON object to shadow-case-proposal.json. Do not modify source/ or the request.

The object must have exactly these fields:
- schema: agentlab.shadow_case_candidate.v1
- id: exactly {request['candidateId']}
- repositoryId, sourceRevision, scopeSkillIds and factIds copied exactly from the request
{proposal_field_constraints()}
- oracleHypothesis: exactly {{"framework": {framework!r}, "observables": ["observable one", "observable two"], "requiredEnvironment": ["environment requirement"], "wrongVariants": ["wrong variant one", "wrong variant two"], "status": "hypothesis-unqualified"}}; observables, requiredEnvironment, and wrongVariants must each be JSON arrays of strings, never a single string; use {OBSERVABLES_LIMITS[0]}-{OBSERVABLES_LIMITS[1]} observables, {ENVIRONMENT_LIMITS[0]}-{ENVIRONMENT_LIMITS[1]} environment requirements, and {WRONG_VARIANTS_LIMITS[0]}-{WRONG_VARIANTS_LIMITS[1]} wrong variants
- limitations: {LIMITATIONS_LIMITS[0]}-{LIMITATIONS_LIMITS[1]} concrete unresolved qualification gaps
- status: shadow-proposal
- automaticPromotion: false

Give at least two observables and two meaningful wrong variants. {environment_instruction} Validate every field type against the exact shape above, and parse the completed JSON once before finishing. The Oracle remains operator-owned: do not include a gold patch, claim build/runtime success, or claim approval. Prefer a mechanism supported by the semantic interpretation rather than a generic build task.
Keep source build-target/compatible SDK, installed build tools, and observed runtime-image versions as distinct axes. Do not require identical versions without an explicit task constraint or compatibility evidence. Likewise, do not invent a signing requirement from a packaging convention: identify the required install policy and retain unsupported signing or installation as a gap, not as a proven prerequisite. Inspect loaded lifecycle entrypoints and initialization/error branches before claiming state initialization is absent. Distinguish missing construction context from missing source behavior, and source-established initialization from runtime readiness or deterministic failure reproduction.
An existing test name, done() callback, or successful runner exit is not a behavior assertion. If proposing reuse of an existing test, inspect its actual assertions and error branches at the pinned source; if the necessary test source is not in fact evidence, record that knowledge gap instead of inventing support. Require independently controlled success/failure checks before runtime calibration. A swallowed failure is an Oracle defect, while an unsupported adapter, timeout, or build fault is infrastructure failure, never a killed wrong variant. Define each wrong variant as one meaningful semantic change; do not assume a cosmetic rename is invalid. Record these as unresolved qualification requirements, not completed experiments.
The required framework is a proposed test contract, not evidence that the repository already contains that test harness. Missing entrypoints are construction gaps, not permission to select an incompatible runner. Distinguish mutations to an old instance's fields from effects on a freshly constructed instance; source assignment alone does not prove a resource leak, runtime cleanup, or causal discrimination. Staged demands must describe one evolving implementation task rather than independent baseline smoke-test descriptions.
"""
    if revision is not None:
        prompt += "\nRevise the retained proposal rather than sampling an unrelated task. Address every finding, preserving request identity and unqualified status. Review is not an approved Oracle. Original rejected proposal bytes:\n" + bound["parentProposalUtf8"] + "\nExact source-review feedback:\n" + bound["reviewUtf8"]
    if successor:
        prompt += "\nConstruct an additive successor of the retained parent, not an unrelated sample. scopeSkillIds must equal " + json.dumps(request["candidateScopeSkillIds"]) + ". editablePaths may use only successorConstruction.editBoundary.edits paths, including explicitly selected create paths; contextPaths may use only loaded constructor source paths and must remain disjoint. All source is still read-only during hypothesis construction. Inspect the bound ownerKnowledge and preserve its limitations; no build, runtime or calibration proof is inherited. Address every review finding. Exact parent proposal:\n" + successor["parentProposalUtf8"] + "\nExact review:\n" + successor["reviewUtf8"]
    try:
        participant.turn("shadow-case-constructor", workspace, prompt=prompt,
                         wall_time_limit_seconds=720, transport_retry_limit=0)
    finally:
        participant.close()
        source_link.unlink(missing_ok=True)
    proposal = workspace / "shadow-case-proposal.json"
    require(file_digest(workspace / "shadow-request.json") == frozen_request_sha,
            "Agent modified the frozen shadow request")
    if revision is not None:
        require((workspace / "parent-proposal.json").read_bytes() == bound["parentProposalUtf8"].encode()
                and (workspace / "review-feedback.json").read_bytes() == bound["reviewUtf8"].encode(),
                "Agent modified retained revision inputs")
    require(proposal.is_file() and not proposal.is_symlink(), "Agent did not produce a shadow proposal")
    shutil.copy2(proposal, args.output / "shadow-case-proposal.json")
    status = subprocess.check_output(["git", "-C", str(source_root), "status", "--porcelain"], text=True)
    (args.output / "source-status.txt").write_text(status, encoding="utf-8")
    require(not status, "Agent modified the pinned source checkout")


def strings(value, name: str, minimum: int = 1, maximum: int | None = None) -> list[str]:
    require(isinstance(value, list) and len(value) >= minimum, f"{name} is incomplete")
    require(maximum is None or len(value) <= maximum, f"{name} is too large")
    require(all(isinstance(item, str) and item.strip() for item in value), f"{name} has invalid values")
    require(len(value) == len(set(value)), f"{name} contains duplicates")
    return value


def validate_proposal(request: dict, proposal: dict) -> dict:
    origin = request_origin(request)
    require(proposal.get("schema") == "agentlab.shadow_case_candidate.v1", "bad shadow proposal schema")
    expected_fields = {
        "schema", "id", "repositoryId", "sourceRevision", "scopeSkillIds", "factIds", "title",
        "mechanism", "stagedDemands", "editablePaths", "contextPaths", "oracleHypothesis",
        "limitations", "status", "automaticPromotion",
    }
    require(set(proposal) == expected_fields, "shadow proposal fields differ")
    require(SAFE_ID.fullmatch(proposal.get("id", "")), "shadow candidate id is invalid")
    require(proposal["id"] == request["candidateId"], "shadow candidate identity differs")
    fact = request["fact"]
    scope = request["scope"]
    require(proposal["repositoryId"] == fact["repositoryId"], "shadow repository differs")
    require(proposal["sourceRevision"] == fact["sourceRevision"] and SHA1.fullmatch(proposal["sourceRevision"]),
            "shadow revision differs")
    require(fact["scopeSkillIds"] == [scope["id"]]
            and proposal["scopeSkillIds"] == request.get("candidateScopeSkillIds", fact["scopeSkillIds"]), "shadow scope binding differs")
    require(proposal["factIds"] == [fact["id"]], "shadow fact binding differs")
    require(isinstance(proposal["title"], str)
            and TITLE_MIN_LENGTH <= len(proposal["title"]) <= TITLE_MAX_LENGTH,
            "shadow title is invalid")
    require(isinstance(proposal["mechanism"], str)
            and MECHANISM_MIN_LENGTH <= len(proposal["mechanism"]) <= MECHANISM_MAX_LENGTH,
            "shadow mechanism is invalid")
    strings(proposal["stagedDemands"], "stagedDemands", *STAGED_DEMANDS_LIMITS)
    editable = strings(proposal["editablePaths"], "editablePaths", *EDITABLE_PATHS_LIMITS)
    context = strings(proposal["contextPaths"], "contextPaths", *CONTEXT_PATHS_LIMITS)
    evidence_paths = {row["path"] for row in fact.get("evidence", []) if isinstance(row, dict)}
    if "successorConstruction" in request:
        allowed_edits = {row["path"] for row in request["successorConstruction"]["editBoundary"]["edits"]}
        require(set(editable).issubset(allowed_edits), "successor editable path not selected")
        require(set(context).issubset({row["path"] for row in constructor_evidence(request)}),
                "successor context path not loaded")
    else:
        require(set(editable + context).issubset(evidence_paths), "shadow paths are not fact evidence")
    require(not set(editable).intersection(context), "editable and context paths overlap")
    require("successorConstruction" in request or all(scope_owns_path(scope, path) for path in editable),
            "editable path escapes the selected scope")
    oracle = proposal["oracleHypothesis"]
    require(isinstance(oracle, dict) and set(oracle) == {
        "framework", "observables", "requiredEnvironment", "wrongVariants", "status",
    }, "oracle hypothesis fields differ")
    expected_framework = oracle_framework(request["policy"], scope)
    require(oracle["framework"] == expected_framework, "oracle framework differs")
    require(oracle["status"] == "hypothesis-unqualified", "oracle status overclaims qualification")
    strings(oracle["observables"], "oracle observables", *OBSERVABLES_LIMITS)
    environment = strings(oracle["requiredEnvironment"], "oracle requiredEnvironment", *ENVIRONMENT_LIMITS)
    target = runtime_target(request["policy"], scope)
    if target == "harmony-emulator":
        require_emulator_environment(environment)
    else:
        positive_requirements = positive_hardware_requirements("\n".join(environment))
        require(not any(pattern.search(positive_requirements)
                        for pattern in EXTERNAL_HARDWARE_PATTERNS.values())
                and not re.search(r"\bphysical device\b|真机", positive_requirements, re.IGNORECASE),
                "repository-test environment requires external hardware")
    strings(oracle["wrongVariants"], "oracle wrongVariants", *WRONG_VARIANTS_LIMITS)
    strings(proposal["limitations"], "limitations", *LIMITATIONS_LIMITS)
    require(proposal["status"] == "shadow-proposal" and proposal["automaticPromotion"] is False,
            "shadow proposal can promote itself")
    result = dict(proposal)
    result.update({
        "sourceSetSha256": request["sourceSetSha256"],
        "knowledgeCutSha256": request["knowledgeCutSha256"],
        "maintainerSkillRefreshRoundId": request["maintainerSkillRefreshRoundId"],
        "lineage": {**origin,
                    "shadowRequestValueSha256": value_digest(request),
                    "runtimeTarget": target},
    })
    return result


def build_round(request: dict, rounds_before: list[dict], candidate_id: str,
                retained: bool, rejection_reason: str | None, run_id: str) -> dict:
    previous = max(rounds_before, key=lambda row: row["roundIndex"])
    oracle_count = previous_oracle_count(rounds_before)
    fact = request["fact"]
    limitations = strings(fact.get("limitations"), "fact limitations", 2)
    operation_origin = "operationInputsSha256" in request_origin(request)
    before = request["knowledgeCoverage"] if operation_origin else request["loopBefore"]
    after = request["knowledgeCoverage"] if operation_origin else request["loopAfter"]
    return {
        "schema": "agentlab.case_generation_round.v1",
        "id": f"first-four-case-generation-round-{previous['roundIndex'] + 1}-shadow-{run_id}",
        "roundIndex": previous["roundIndex"] + 1,
        "parentRoundSha256": value_digest(previous),
        "sourceSetSha256": request["sourceSetSha256"],
        "knowledgeCutSha256": request["knowledgeCutSha256"],
        "maintainerSkillRefreshRoundId": request["maintainerSkillRefreshRoundId"],
        "objectives": [
            ("derive a case hypothesis from admitted maintenance evidence without inheriting calibration"
             if operation_origin else "sample one newly semantic-ready scope without slowing the knowledge flywheels"),
            "test whether revision-bound Maintainer Skill evidence can produce a grounded case hypothesis",
            "return construction and Oracle gaps to the next knowledge round",
        ],
        "coverage": {
            "repositoryIds": [request["repository"]["id"]],
            "scopeSkillCount": len(request.get("candidateScopeSkillIds", fact["scopeSkillIds"])),
            "behaviorReadyBefore": before["semanticReadyCount"],
            "behaviorReadyAfter": after["semanticReadyCount"],
            "oracleReadyBefore": oracle_count,
            "oracleReadyAfter": oracle_count,
        },
        "candidates": {
            "generatedIds": [candidate_id],
            "retainedIds": [candidate_id] if retained else [],
            "rejected": [] if retained else [{"candidateId": candidate_id, "reason": rejection_reason}],
        },
        "qualification": {
            "constructedIds": [], "oracleQualifiedIds": [], "calibratedIds": [], "qualifiedCaseIds": [],
        },
        "feedback": {
            "maintainerSkillGaps": [
                f"bind {candidate_id} through the candidate-stage Maintainer knowledge gate before construction",
                *(["single maintenance-origin sample does not satisfy the diverse cohort requirement; add distinct contract and lifecycle candidates"] if operation_origin else []),
            ],
            "programAnalysisGaps": limitations[:2],
            "oracleGaps": [
                f"independently implement and execute the proposed Oracle for {candidate_id}",
                f"calibrate at least two meaningful wrong variants for {candidate_id}",
            ],
        },
        "decision": "continue",
        "decisionEvidence": [
            ("case construction consumed admitted maintenance evidence without claiming a new semantic gain"
             if operation_origin else "the knowledge flywheel advanced semantic coverage in this exact bounded loop"),
            "the shadow candidate remains non-promoted and has no independent Oracle or calibration receipt",
        ],
        "automaticPromotion": False,
    }


def record_success(args) -> None:
    request = load(args.request)
    verify_lineage_binding(request, args.rounds.parent)
    candidate = validate_proposal(request, load(args.proposal))
    candidate_rows = rows(args.candidates)
    require(candidate["id"] not in {row["id"] for row in candidate_rows}, "shadow candidate already exists")
    candidate_rows.append(candidate)
    candidate_rows.sort(key=lambda row: row["id"])
    round_rows = rows(args.rounds)
    require(round_rows, "case generation lineage is empty")
    round_row = build_round(request, round_rows, candidate["id"], True, None, args.run_id)
    write_jsonl(args.candidates, candidate_rows)
    write_jsonl(args.rounds, round_rows + [round_row])
    write_json(args.receipt, {
        "schema": "agentlab.case_generation_shadow_receipt.v1",
        "status": "retained-shadow-proposal",
        "candidateId": candidate["id"],
        "candidateSha256": value_digest(candidate),
        "roundId": round_row["id"],
        "roundSha256": value_digest(round_row),
        "automaticPromotion": False,
    })


def record_failure(args) -> None:
    request = load(args.request)
    verify_lineage_binding(request, args.rounds.parent)
    round_rows = rows(args.rounds)
    require(round_rows, "case generation lineage is empty")
    candidate_id = request["candidateId"]
    require(SAFE_ID.fullmatch(candidate_id), "derived shadow attempt id is invalid")
    round_row = build_round(request, round_rows, candidate_id, False, args.reason, args.run_id)
    write_jsonl(args.rounds, round_rows + [round_row])
    write_json(args.receipt, {
        "schema": "agentlab.case_generation_shadow_receipt.v1",
        "status": "rejected-shadow-attempt",
        "candidateId": candidate_id,
        "reason": args.reason,
        "roundId": round_row["id"],
        "roundSha256": value_digest(round_row),
        "automaticPromotion": False,
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("prepare")
    command.add_argument("--knowledge", type=Path, required=True)
    command.add_argument("--loop-receipt", type=Path, required=True)
    command.add_argument("--lineage-root", type=Path)
    command.add_argument("--runtime-target", choices=["harmony-emulator", "repository-test"],
                         default="harmony-emulator")
    command.add_argument("--output", type=Path, required=True)
    command.set_defaults(handler=prepare)
    command = commands.add_parser("run-agent")
    command.add_argument("--request", type=Path, required=True)
    command.add_argument("--source", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--pi", type=Path, required=True)
    command.add_argument("--gateway", required=True)
    command.add_argument("--model", required=True)
    command.add_argument("--provider-route", required=True)
    command.add_argument("--reasoning-effort", choices=["default", "low", "medium", "high", "max"], default="default")
    command.add_argument("--max-output-tokens", type=int, choices=[8192, 16384])
    command.add_argument("--revision-request", type=Path)
    command.add_argument("--flywheel-tool", type=Path)
    command.add_argument("--knowledge", type=Path)
    command.add_argument("--operation-inputs", type=Path)
    command.set_defaults(handler=run_agent)
    command = commands.add_parser("record-success")
    command.add_argument("--request", type=Path, required=True)
    command.add_argument("--proposal", type=Path, required=True)
    command.add_argument("--rounds", type=Path, required=True)
    command.add_argument("--candidates", type=Path, required=True)
    command.add_argument("--receipt", type=Path, required=True)
    command.add_argument("--run-id", required=True)
    command.set_defaults(handler=record_success)
    command = commands.add_parser("record-failure")
    command.add_argument("--request", type=Path, required=True)
    command.add_argument("--rounds", type=Path, required=True)
    command.add_argument("--receipt", type=Path, required=True)
    command.add_argument("--run-id", required=True)
    command.add_argument("--reason", choices=["shadow-construction-agent-failed", "shadow-proposal-hard-gate-rejected", "shadow-input-requires-external-hardware"], required=True)
    command.set_defaults(handler=record_failure)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
