#!/usr/bin/env python3
"""Fail-closed construction readiness for retained shadow case candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile


SHA256 = re.compile(r"[0-9a-f]{64}")


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def value_digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require(condition, message: str) -> None:
    if not condition:
        raise ValueError(message)


def strings(value, label: str, minimum: int = 1) -> list[str]:
    require(isinstance(value, list) and len(value) >= minimum, f"{label} is incomplete")
    require(all(isinstance(item, str) and item.strip() for item in value), f"{label} has invalid values")
    require(len(value) == len(set(value)), f"{label} contains duplicates")
    return value


def safe_path(value: str, label: str) -> str:
    path = PurePosixPath(value)
    require(value == path.as_posix() and not path.is_absolute(), f"{label} is not a safe relative path")
    require(all(part not in ("", ".", "..") for part in path.parts), f"{label} is not a safe relative path")
    return value


def within(path: str, boundary: str) -> bool:
    return path == boundary or path.startswith(boundary.rstrip("/") + "/")


def scope_owns_path(scope: dict, path: str) -> bool:
    selectors = scope.get("ownershipSelectors")
    if not selectors:
        return within(path, scope["pathBoundary"])
    return any(
        (selector.get("type") == "prefix" and within(path, selector.get("path", "")))
        or (selector.get("type") == "files" and path in selector.get("paths", []))
        for selector in selectors
    )


def validate_evidence(root: Path, evidence, label: str) -> list[dict]:
    require(isinstance(evidence, list), f"{label} evidence must be an array")
    result = []
    for offset, item in enumerate(evidence):
        require(isinstance(item, dict) and set(item) == {"path", "sha256"},
                f"{label} evidence {offset} fields differ")
        relative = safe_path(item["path"], f"{label} evidence path")
        path = root / relative
        cursor = root
        require(root.is_dir() and not root.is_symlink(), f"{label} evidence root is invalid")
        for part in PurePosixPath(relative).parts:
            cursor = cursor / part
            require(not cursor.is_symlink(), f"{label} evidence symlink rejected")
        require(path.is_file() and not path.is_symlink(), f"{label} evidence is not a regular file: {relative}")
        require(path.stat().st_size <= 2 * 1024 * 1024, f"{label} evidence exceeds budget")
        require(SHA256.fullmatch(item["sha256"]) is not None, f"{label} evidence digest is invalid")
        require(file_digest(path) == item["sha256"], f"{label} evidence digest differs: {relative}")
        result.append(item)
    return result


def validate_qualification(root: Path, value, label: str, candidate: dict,
                           kind: str, requirement_id: str | None = None) -> dict:
    require(isinstance(value, dict), f"{label} must be an object")
    require(value.get("status") in ("qualified", "unqualified"), f"{label} status is invalid")
    evidence = validate_evidence(root, value.get("evidence"), label)
    require(value["status"] != "qualified" or evidence, f"{label} has no qualifying evidence")
    rejected_variants = set()
    accepted_variants = set()
    if value["status"] == "qualified":
        for ref in evidence:
            original = (root / ref["path"]).read_bytes()
            require(len(original) <= 2 * 1024 * 1024
                    and hashlib.sha256(original).hexdigest() == ref["sha256"],
                    f"{label} qualification receipt changed during validation")
            receipt = json.loads(original)
            require(isinstance(receipt, dict)
                    and receipt.get("schema") == "agentlab.shadow_case_qualification.v1",
                    f"{label} qualification receipt adapter unavailable")
            require(receipt.get("kind") == kind and receipt.get("status") == "qualified"
                    and receipt.get("automaticPromotion") is False,
                    f"{label} qualification receipt failed or overclaimed")
            for key, expected in {
                "candidateId": candidate["id"], "candidateSha256": value_digest(candidate),
                "sourceRevision": candidate["sourceRevision"],
                "sourceSetSha256": candidate["sourceSetSha256"],
                "knowledgeCutSha256": candidate["knowledgeCutSha256"],
            }.items():
                require(receipt.get(key) == expected, f"{label} qualification {key} differs")
            execution = receipt.get("execution") or {}
            require(execution.get("status") == "completed"
                    and type(execution.get("exitCode")) is int and execution["exitCode"] == 0
                    and type(execution.get("durationMs")) is int and execution["durationMs"] > 0,
                    f"{label} qualification execution is incomplete")
            if kind == "runtime-requirement":
                require(receipt.get("requirementId") == requirement_id,
                        f"{label} qualification requirement differs")
            checks = receipt.get("checks")
            require(isinstance(checks, list) and checks, f"{label} has no observed checks")
            require(all(isinstance(check, dict) and isinstance(check.get("id"), str)
                        and check["id"] and check.get("passed") is True for check in checks)
                    and len({check["id"] for check in checks}) == len(checks),
                    f"{label} observed checks failed or duplicated")
            if kind == "wrong-variant-calibration":
                variants = receipt.get("variants")
                require(isinstance(variants, list) and variants, f"{label} variants missing")
                for variant in variants:
                    require(isinstance(variant, dict) and isinstance(variant.get("id"), str)
                            and variant["id"] and variant.get("completed") is True,
                            f"{label} variant did not complete")
                    variant_checks = variant.get("checks")
                    require(isinstance(variant_checks, list) and variant_checks
                            and all(isinstance(c, dict) and isinstance(c.get("id"), str)
                                    and c["id"] and type(c.get("passed")) is bool
                                    and isinstance(c.get("observable"), str) for c in variant_checks)
                            and len({c["id"] for c in variant_checks}) == len(variant_checks)
                            and {c["observable"] for c in variant_checks}
                            == set(candidate["oracleHypothesis"]["observables"]),
                            f"{label} variant checks missing or duplicated")
                    role = variant.get("role")
                    if role == "accepted":
                        require(variant.get("expectedVerdict") == variant.get("observedVerdict") == "accept"
                                and all(c["passed"] for c in variant_checks),
                                f"{label} valid variant was not accepted")
                        require(variant["id"] not in accepted_variants | rejected_variants,
                                f"{label} duplicate variant")
                        accepted_variants.add(variant["id"])
                    else:
                        require(role == "wrong" and variant.get("expectedVerdict")
                                == variant.get("observedVerdict") == "reject"
                                and any(not c["passed"] for c in variant_checks)
                                and variant["id"] in candidate["oracleHypothesis"]["wrongVariants"],
                                f"{label} wrong variant did not discriminate the declared behavior")
                        require(variant["id"] not in accepted_variants | rejected_variants,
                                f"{label} duplicate variant")
                        rejected_variants.add(variant["id"])
        if kind == "wrong-variant-calibration":
            require(accepted_variants and len(rejected_variants) == value["executedCount"],
                    f"{label} observed variants differ from declared count")
    return {"status": value["status"], "evidence": evidence,
            "verificationBoundary": "recorded receipt content only; no execution replay or producer authentication"}


def construction_bindings(knowledge: Path, candidate: dict, edit_boundary: Path | None,
                          source_worktree: Path | None, flywheel_tool: Path | None) -> dict | None:
    supplied = (edit_boundary, source_worktree, flywheel_tool)
    if not any(value is not None for value in supplied):
        return None
    require(all(value is not None for value in supplied), "construction binding requires packet, source and native tool")
    require(edit_boundary.is_file() and not edit_boundary.is_symlink()
            and edit_boundary.stat().st_size <= 1024 * 1024, "construction packet is not a bounded regular file")
    packet_sha = file_digest(edit_boundary)
    require(packet_sha == candidate.get("lineage", {}).get("editBoundarySha256"),
            "construction packet differs from candidate lineage")
    require(flywheel_tool.is_file() and not flywheel_tool.is_symlink(), "construction native tool invalid")
    tool_sha = file_digest(flywheel_tool)
    with tempfile.TemporaryDirectory(prefix="agentlab-path-binding-") as directory:
        root = Path(directory)
        candidate_path = root / "candidate.json"
        candidate_path.write_bytes(canonical(candidate))
        output = root / "binding.json"
        command = [str(flywheel_tool.resolve()), "--bind-construction-paths",
                   "--knowledge", str(knowledge.absolute()), "--source-worktree", str(source_worktree.absolute()),
                   "--edit-boundary", str(edit_boundary.absolute()), "--candidate", str(candidate_path),
                   "--output", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        require(result.returncode == 0, f"construction native binding failed: {result.stderr}")
        require(file_digest(flywheel_tool) == tool_sha and file_digest(edit_boundary) == packet_sha,
                "construction binding input changed during validation")
        binding = load(output)
    require(binding.get("schema") == "agentlab.case_construction_path_binding.v1"
            and binding.get("candidateId") == candidate["id"]
            and binding.get("candidateSha256") == value_digest(candidate)
            and binding.get("editBoundarySha256") == packet_sha
            and all(binding.get(key) is False for key in (
                "qualified", "automaticPromotion", "authorityWritePerformed", "grantsEditablePaths", "calibrationInherited")),
            "construction native binding receipt differs")
    binding["validatorExecutableSha256"] = tool_sha
    binding["validatorStdout"] = result.stdout
    binding["validatorStderr"] = result.stderr
    binding["validatorExitCode"] = result.returncode
    return binding


def assess(knowledge: Path, candidate_id: str, plan_path: Path, evidence_root: Path,
           edit_boundary: Path | None = None, source_worktree: Path | None = None,
           flywheel_tool: Path | None = None) -> dict:
    cut_path = knowledge / "maintainer-knowledge-cut.json"
    cut = load(cut_path)
    candidates = [row for row in rows(knowledge / "case_generation_candidates.jsonl") if row["id"] == candidate_id]
    require(len(candidates) == 1, "shadow candidate is absent or duplicated")
    candidate = candidates[0]
    plan = load(plan_path)
    require(plan.get("schema") == "agentlab.shadow_case_construction_plan.v1", "bad construction plan schema")
    require(plan.get("automaticPromotion") is False, "construction plan can auto-promote")
    require(plan.get("candidateId") == candidate_id, "construction plan candidate differs")
    candidate_sha = value_digest(candidate)
    require(plan.get("candidateSha256") == candidate_sha, "construction plan candidate digest differs")
    require(candidate.get("sourceSetSha256") == cut.get("sourceSetSha256"), "candidate source set differs")
    require(SHA256.fullmatch(candidate.get("knowledgeCutSha256", "")) is not None,
            "candidate knowledge cut digest is invalid")
    refresh_rounds = {
        row["id"]: row for row in rows(knowledge / "maintainer_skill_refresh_rounds.jsonl")
    }
    require(candidate.get("maintainerSkillRefreshRoundId") in refresh_rounds,
            "candidate Maintainer Skill refresh round is absent")

    scopes = {row["id"]: row for row in rows(knowledge / "maintainer_scope_skills.jsonl")}
    facts = {row["id"]: row for row in rows(knowledge / "program_facts.jsonl")}
    scope_rows = []
    for scope_id in strings(candidate.get("scopeSkillIds"), "candidate scopeSkillIds"):
        require(scope_id in scopes, f"unknown candidate scope Skill {scope_id}")
        scope = scopes[scope_id]
        require(scope.get("repositoryId") == candidate.get("repositoryId"), f"scope {scope_id} repository differs")
        require(scope.get("sourceRevision") == candidate.get("sourceRevision"), f"scope {scope_id} revision differs")
        scope_rows.append(scope)
    evidence_paths = set()
    evidence_blobs: dict[str, set[str]] = {}
    for fact_id in strings(candidate.get("factIds"), "candidate factIds"):
        require(fact_id in facts, f"unknown candidate fact {fact_id}")
        fact = facts[fact_id]
        require(fact.get("repositoryId") == candidate.get("repositoryId"), f"fact {fact_id} repository differs")
        require(fact.get("sourceRevision") == candidate.get("sourceRevision"), f"fact {fact_id} revision differs")
        evidence_paths.update(
            row["path"] for row in fact.get("evidence", [])
            if isinstance(row, dict) and isinstance(row.get("path"), str)
        )
        for item in fact.get("evidence", []):
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                oid = item.get("gitBlobOid")
                evidence_blobs.setdefault(item["path"], set()).add(
                    oid if isinstance(oid, str) else ""
                )

    required_fields = {
        "schema", "candidateId", "candidateSha256", "requiredImplementationPaths",
        "requiredOraclePaths", "runtimeRequirements", "oracleExecution",
        "wrongVariantCalibration", "automaticPromotion",
    }
    require(set(plan) == required_fields, "construction plan fields differ")
    editable = set(strings(candidate.get("editablePaths"), "candidate editablePaths"))
    context = set(candidate.get("contextPaths") or [])
    binding = construction_bindings(knowledge, candidate, edit_boundary, source_worktree, flywheel_tool)
    selected = {row["path"]: row for row in binding["paths"]} if binding else {}

    def path_checks(field: str, permitted: set[str], permission_name: str) -> list[dict]:
        values = plan.get(field)
        require(isinstance(values, list) and values, f"{field} is incomplete")
        seen = set()
        checks = []
        for item in values:
            require(isinstance(item, dict) and set(item) == {"path", "reason"}, f"{field} item fields differ")
            path = safe_path(item.get("path"), field)
            require(path not in seen, f"{field} duplicates {path}")
            seen.add(path)
            require(isinstance(item.get("reason"), str) and item["reason"].strip(), f"{field} reason is empty")
            in_scope = any(scope_owns_path(scope, path) for scope in scope_rows)
            owners = sorted(
                scope["id"] for scope in scopes.values()
                if scope.get("repositoryId") == candidate.get("repositoryId")
                and scope.get("sourceRevision") == candidate.get("sourceRevision")
                and scope_owns_path(scope, path)
            )
            readonly_context = (
                not in_scope and path in context and path not in editable
                and len(owners) == 1 and len(evidence_blobs.get(path, set())) == 1
                and all(re.fullmatch(r"[0-9a-f]{40}", oid)
                        for oid in evidence_blobs.get(path, set()))
            )
            checks.append({
                "path": path,
                "reason": item["reason"],
                "inCandidateScope": in_scope,
                "factEvidenceBound": path in evidence_paths,
                permission_name: path in permitted,
                "readOnlyContextBound": readonly_context,
                "contextOwnerScopeSkillIds": owners if readonly_context else [],
                **({"constructionSelectionBound": path in selected,
                    "constructionPrecondition": selected[path]["precondition"] if path in selected else None}
                   if binding else {}),
            })
        return checks

    implementation = path_checks("requiredImplementationPaths", editable, "editable")
    oracle_paths = path_checks("requiredOraclePaths", editable | context, "candidateVisible")

    runtime = plan.get("runtimeRequirements")
    require(isinstance(runtime, list) and runtime, "runtimeRequirements is incomplete")
    runtime_checks = []
    runtime_ids = set()
    for item in runtime:
        require(isinstance(item, dict) and set(item) == {"id", "description", "status", "evidence"},
                "runtime requirement fields differ")
        require(isinstance(item["id"], str) and item["id"] and item["id"] not in runtime_ids,
                "runtime requirement id is invalid or duplicated")
        runtime_ids.add(item["id"])
        require(isinstance(item["description"], str) and item["description"].strip(),
                "runtime requirement description is empty")
        qualification = validate_qualification(evidence_root, item, f"runtime requirement {item['id']}",
                                               candidate, "runtime-requirement", item["id"])
        runtime_checks.append({"id": item["id"], "description": item["description"], **qualification})

    oracle = validate_qualification(evidence_root, plan.get("oracleExecution"), "oracleExecution",
                                    candidate, "oracle-execution")
    variants = plan.get("wrongVariantCalibration")
    require(isinstance(variants, dict) and set(variants) == {"status", "evidence", "requiredCount", "executedCount"},
            "wrongVariantCalibration fields differ")
    variant_qualification = validate_qualification(evidence_root, variants, "wrongVariantCalibration",
                                                   candidate, "wrong-variant-calibration")
    require(type(variants["requiredCount"]) is int and variants["requiredCount"] >= 2,
            "wrongVariantCalibration requiredCount is invalid")
    require(type(variants["executedCount"]) is int and variants["executedCount"] >= 0,
            "wrongVariantCalibration executedCount is invalid")
    require(variants["executedCount"] <= len(candidate["oracleHypothesis"]["wrongVariants"]),
            "wrongVariantCalibration executedCount exceeds the candidate variants")
    require(variants["status"] != "qualified" or variants["executedCount"] >= variants["requiredCount"],
            "wrongVariantCalibration claims qualification below the required count")

    knowledge_blockers = []
    for row in implementation:
        if not row["inCandidateScope"]:
            knowledge_blockers.append(f"implementation path escapes candidate scope: {row['path']}")
        if not row["factEvidenceBound"] and not row.get("constructionSelectionBound", False):
            knowledge_blockers.append(f"implementation path is absent from bound fact evidence: {row['path']}")
        if not row["editable"]:
            knowledge_blockers.append(f"implementation path is absent from candidate editablePaths: {row['path']}")
    for row in oracle_paths:
        if not row["inCandidateScope"] and not row["readOnlyContextBound"]:
            knowledge_blockers.append(f"Oracle path escapes candidate scope: {row['path']}")
        if not row["factEvidenceBound"] and not row.get("constructionSelectionBound", False):
            knowledge_blockers.append(f"Oracle path is absent from bound fact evidence: {row['path']}")
        if not row["candidateVisible"]:
            knowledge_blockers.append(f"Oracle path is absent from candidate editable/context paths: {row['path']}")
    qualification_blockers = [
        f"runtime requirement is unqualified: {row['id']}" for row in runtime_checks if row["status"] != "qualified"
    ]
    if oracle["status"] != "qualified":
        qualification_blockers.append("independent Oracle has not executed successfully")
    if variant_qualification["status"] != "qualified":
        qualification_blockers.append(
            f"wrong-variant calibration is incomplete: {variants['executedCount']}/{variants['requiredCount']}"
        )
    if knowledge_blockers:
        decision = "blocked-knowledge-refresh"
        next_gate = "refresh-program-facts-and-shadow-candidate"
    elif qualification_blockers:
        decision = "blocked-qualification"
        next_gate = "implement-and-calibrate-independent-oracle"
    else:
        decision = "ready-for-construction"
        next_gate = "maintainer-knowledge-gate-construction"
    return {
        "schema": "agentlab.shadow_case_construction_readiness_receipt.v1",
        "candidateId": candidate_id,
        "candidateSha256": candidate_sha,
        "sourceRevision": candidate["sourceRevision"],
        "sourceSetSha256": candidate["sourceSetSha256"],
        "knowledgeCutSha256": candidate["knowledgeCutSha256"],
        "currentKnowledgeCutSha256": file_digest(cut_path),
        "planSha256": file_digest(plan_path),
        "checks": {
            "implementationPaths": implementation,
            "oraclePaths": oracle_paths,
            "runtimeRequirements": runtime_checks,
            "oracleExecution": oracle,
            "wrongVariantCalibration": {
                **variant_qualification,
                "requiredCount": variants["requiredCount"],
                "executedCount": variants["executedCount"],
            },
        },
        "knowledgeBlockers": knowledge_blockers,
        "qualificationBlockers": qualification_blockers,
        "decision": decision,
        "nextGate": next_gate,
        "automaticPromotion": False,
        **({"constructionPathBinding": binding} if binding else {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--knowledge", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--edit-boundary", type=Path)
    parser.add_argument("--source-worktree", type=Path)
    parser.add_argument("--flywheel-tool", type=Path)
    args = parser.parse_args()
    result = assess(args.knowledge, args.candidate_id, args.plan, args.evidence_root,
                    args.edit_boundary, args.source_worktree, args.flywheel_tool)
    require(not args.output.exists(), "readiness output already exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
