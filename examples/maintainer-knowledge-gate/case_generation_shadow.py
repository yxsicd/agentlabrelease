#!/usr/bin/env python3
"""Turn one newly semantic-ready scope into a non-promoted case hypothesis."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
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
    existing = rows(knowledge / "case_generation_candidates.jsonl")
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
            "externalHardwareAllowed": False,
            "physicalDeviceFallbackAllowed": False,
            "shadowEligible": not external_hardware_blockers(scope, fact),
            "blockers": external_hardware_blockers(scope, fact),
        },
        "output": "shadow-case-proposal.json",
    }
    runtime_target(request["policy"], scope)
    write_json(args.output, request)


def run_agent(args) -> None:
    request = load(args.request)
    require(request.get("schema") == "agentlab.case_generation_shadow_request.v1", "bad shadow request")
    require(request["policy"].get("shadowEligible") is True,
            "shadow input is not eligible for the declared runtime")
    target = runtime_target(request["policy"], request["scope"])
    source_root = args.source.resolve(strict=True)
    head = subprocess.check_output(["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True).strip()
    require(head == request["repository"]["revision"], "source checkout revision differs")
    workspace = args.output / "workspace"
    evidence = args.output / "evidence"
    workspace.mkdir(parents=True)
    evidence.mkdir()
    shutil.copy2(args.request, workspace / "shadow-request.json")
    source_link = workspace / "source"
    source_link.symlink_to(source_root, target_is_directory=True)
    participant_path = Path(__file__).resolve().parents[1] / "real-code-agent" / "participant.py"
    spec = importlib.util.spec_from_file_location("agentlab_participant", participant_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    participant = module.Participant(
        evidence, args.output / "participant-state", args.pi, args.gateway, args.model,
        route=args.provider_route, implementation="pi",
    )
    scope = request["scope"]
    fact = request["fact"]
    framework = "ohosTest" if any("ohosTest" in path for path in scope.get("testEntrypoints", [])) else "repository-test"
    environment_instruction = (
        "The complete functional Oracle must be executable on a HarmonyOS emulator with no physical-device fallback and no attached USB, serial, or other external hardware; name the emulator image/device type in requiredEnvironment."
        if target == "harmony-emulator" else
        "The complete functional Oracle must use the pinned repository's test runner in a controlled host or container, without external hardware or physical-device fallback; name the required runner and environment in requiredEnvironment."
    )
    prompt = f"""You are constructing one shadow evaluation-case hypothesis, not assessing an Agent.
Read shadow-request.json and the exact read-only source/ checkout. Use only scope {scope['id']} and semantic fact {fact['id']}.
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

Give at least two observables and two meaningful wrong variants. {environment_instruction} Validate every field type against the exact shape above, and parse the completed JSON once before finishing. The Oracle remains operator-owned: do not include a gold patch, claim build/runtime success, or claim approval. Use only paths present in the fact evidence. Prefer a mechanism supported by the semantic interpretation rather than a generic build task.
An existing test name, done() callback, or successful runner exit is not a behavior assertion. If proposing reuse of an existing test, inspect its actual assertions and error branches at the pinned source; if the necessary test source is not in fact evidence, record that knowledge gap instead of inventing support. Require independently controlled success/failure checks before runtime calibration. A swallowed failure is an Oracle defect, while an unsupported adapter, timeout, or build fault is infrastructure failure, never a killed wrong variant. Define each wrong variant as one meaningful semantic change; do not assume a cosmetic rename is invalid. Record these as unresolved qualification requirements, not completed experiments.
"""
    try:
        participant.turn("shadow-case-constructor", workspace, prompt=prompt, wall_time_limit_seconds=720)
    finally:
        participant.close()
        source_link.unlink(missing_ok=True)
    proposal = workspace / "shadow-case-proposal.json"
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
    require(proposal["scopeSkillIds"] == fact["scopeSkillIds"] == [scope["id"]], "shadow scope binding differs")
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
    require(set(editable + context).issubset(evidence_paths), "shadow paths are not fact evidence")
    require(not set(editable).intersection(context), "editable and context paths overlap")
    require(all(scope_owns_path(scope, path) for path in editable),
            "editable path escapes the selected scope")
    oracle = proposal["oracleHypothesis"]
    require(isinstance(oracle, dict) and set(oracle) == {
        "framework", "observables", "requiredEnvironment", "wrongVariants", "status",
    }, "oracle hypothesis fields differ")
    expected_framework = "ohosTest" if any("ohosTest" in path for path in scope.get("testEntrypoints", [])) else "repository-test"
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
        "lineage": {"loopReceiptSha256": request["loopReceiptSha256"],
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
    return {
        "schema": "agentlab.case_generation_round.v1",
        "id": f"first-four-case-generation-round-{previous['roundIndex'] + 1}-shadow-{run_id}",
        "roundIndex": previous["roundIndex"] + 1,
        "parentRoundSha256": value_digest(previous),
        "sourceSetSha256": request["sourceSetSha256"],
        "knowledgeCutSha256": request["knowledgeCutSha256"],
        "maintainerSkillRefreshRoundId": request["maintainerSkillRefreshRoundId"],
        "objectives": [
            "sample one newly semantic-ready scope without slowing the knowledge flywheels",
            "test whether revision-bound Maintainer Skill evidence can produce a grounded case hypothesis",
            "return construction and Oracle gaps to the next knowledge round",
        ],
        "coverage": {
            "repositoryIds": [request["repository"]["id"]],
            "scopeSkillCount": 1,
            "behaviorReadyBefore": request["loopBefore"]["semanticReadyCount"],
            "behaviorReadyAfter": request["loopAfter"]["semanticReadyCount"],
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
            ],
            "programAnalysisGaps": limitations[:2],
            "oracleGaps": [
                f"independently implement and execute the proposed Oracle for {candidate_id}",
                f"calibrate at least two meaningful wrong variants for {candidate_id}",
            ],
        },
        "decision": "continue",
        "decisionEvidence": [
            "the knowledge flywheel advanced semantic coverage in this exact bounded loop",
            "the shadow candidate remains non-promoted and has no independent Oracle or calibration receipt",
        ],
        "automaticPromotion": False,
    }


def record_success(args) -> None:
    request = load(args.request)
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
