#!/usr/bin/env python3
"""Calibrate a bounded purchase-data behavior seam over exact Git source bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN_SCHEMA = "agentlab.purchase_data_behavior_oracle_plan.v1"
RESULT_SCHEMA = "agentlab.purchase_data_behavior_oracle_calibration.v1"
SEAM_RESULT_SCHEMA = "agentlab.purchase_data_behavior_seam_result.v1"
PACKET_SCHEMA = "agentlab.multi_repo_candidate_review_packet.v11"
QUALIFICATION_SCHEMA = "agentlab.selected_control_flow_qualification.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,160}")


class CalibrationError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise CalibrationError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CalibrationError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), f"evidence must be a regular file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def git(root: Path, *arguments: str) -> bytes:
    process = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
    )
    require(process.returncode == 0, f"git {' '.join(arguments)} failed for {root}")
    return process.stdout


def repository_arguments(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        repository_id, separator, raw_path = value.partition("=")
        require(separator == "=" and TOKEN.fullmatch(repository_id) is not None, "repository argument is invalid")
        path = Path(raw_path).resolve()
        require(path.is_dir() and not path.is_symlink(), f"repository root is invalid: {repository_id}")
        require(repository_id not in result, f"repository argument is duplicated: {repository_id}")
        result[repository_id] = path
    return result


def extract_method(text: str, start: str) -> tuple[str, str]:
    require(text.count(start) == 1, f"method start must occur exactly once: {start}")
    method_start = text.index(start)
    brace = text.find("{", method_start + len(start) - 1)
    require(brace >= 0, f"method body is absent: {start}")
    depth = 0
    for index in range(brace, len(text)):
        character = text[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[method_start:index + 1], text[brace + 1:index]
    raise CalibrationError(f"method braces are unbalanced: {start}")


def apply_replacements(value: str, replacements: list[dict[str, Any]], label: str) -> str:
    result = value
    for row in replacements:
        require(isinstance(row, dict) and set(row) == {"find", "replace", "occurrences"}, f"{label} replacement fields differ")
        find = row.get("find")
        replace = row.get("replace")
        occurrences = row.get("occurrences")
        require(isinstance(find, str) and find and isinstance(replace, str), f"{label} replacement is invalid")
        require(isinstance(occurrences, int) and occurrences > 0, f"{label} replacement count is invalid")
        require(result.count(find) == occurrences, f"{label} replacement occurrence count differs")
        result = result.replace(find, replace)
    return result


def validate_lineage(
    plan_path: Path,
    packet_path: Path,
    qualification_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    plan = load(plan_path, "behavior Oracle plan")
    packet = load(packet_path, "v11 semantic review packet")
    qualification = load(qualification_path, "selected control-flow qualification")
    require(plan.get("schema") == PLAN_SCHEMA, "unsupported behavior Oracle plan")
    require(REVISION.fullmatch(plan.get("methodRevision") or "") is not None, "method revision is invalid")
    require(packet.get("schema") == PACKET_SCHEMA, "behavior Oracle requires a v11 packet")
    require(qualification.get("schema") == QUALIFICATION_SCHEMA, "unsupported control-flow qualification")
    require(plan.get("candidateId") == packet.get("candidateId") == qualification.get("candidateId"), "candidate lineage differs")
    require(plan.get("sourceSetSha256") == packet.get("sourceSetSha256") == qualification.get("sourceSetSha256"), "source set lineage differs")
    require(plan.get("reviewPacketSha256") == digest(packet_path), "review packet digest differs")
    require(plan.get("controlFlowQualificationSha256") == digest(qualification_path), "control-flow qualification digest differs")
    require(packet.get("status") == "independent-semantic-review-required", "packet is not awaiting independent review")
    require(qualification.get("remainingUnresolvedCount") == 0, "program-analysis boundary is not closed")
    require(qualification.get("reachabilityAndDominanceResolved") is True, "selected control flow is incomplete")
    for value in (packet, qualification):
        require(value.get("semanticAlignmentVerified") is False, "input claims semantic alignment")
        require(value.get("behaviorOracleVerified") is False, "input claims a behavior Oracle")
        require(value.get("allowsCaseContract") is False, "input allows case construction")
        require(value.get("automaticPromotion") is False, "input can auto-promote")
    return plan, packet, qualification


def read_methods(plan: dict[str, Any], roots: dict[str, Path]) -> tuple[dict[str, dict[str, str]], list[dict[str, Any]]]:
    repositories = plan.get("repositories")
    methods = plan.get("methods")
    require(isinstance(repositories, list) and len(repositories) == 2, "plan repositories are invalid")
    require(isinstance(methods, list) and len(methods) == 5, "plan methods are invalid")
    expected_roots = {row.get("id") for row in repositories if isinstance(row, dict)}
    require(set(roots) == expected_roots, "repository arguments differ from the plan")
    source_cache: dict[tuple[str, str], str] = {}
    evidence: list[dict[str, Any]] = []
    repository_by_id = {row["id"]: row for row in repositories}
    for repository_id, row in repository_by_id.items():
        revision = row.get("revision")
        require(REVISION.fullmatch(revision or "") is not None, f"repository revision is invalid: {repository_id}")
        head = git(roots[repository_id], "rev-parse", "HEAD").decode().strip()
        require(head == revision, f"repository checkout differs: {repository_id}")
    bodies: dict[str, dict[str, str]] = {"harmony": {}, "cordova": {}}
    for row in methods:
        require(
            isinstance(row, dict)
            and set(row) == {
                "id", "runtime", "repositoryId", "path", "startSnippet",
                "methodSha256", "bodySha256", "transpileReplacements",
            },
            "method plan fields differ",
        )
        method_id = row["id"]
        runtime = row["runtime"]
        repository_id = row["repositoryId"]
        relative = row["path"]
        require(runtime in bodies and TOKEN.fullmatch(method_id or "") is not None, "method identity is invalid")
        require(repository_id in roots and isinstance(relative, str) and relative, "method source identity is invalid")
        key = (repository_id, relative)
        if key not in source_cache:
            repository = repository_by_id[repository_id]
            raw = git(roots[repository_id], "show", f"{repository['revision']}:{relative}")
            expected_file = next(
                (value for value in repository.get("files") or [] if value.get("path") == relative),
                None,
            )
            require(isinstance(expected_file, dict), f"source file is absent from the plan: {repository_id}:{relative}")
            require(bytes_digest(raw) == expected_file.get("contentSha256"), f"source content differs: {repository_id}:{relative}")
            blob = git(roots[repository_id], "rev-parse", f"{repository['revision']}:{relative}").decode().strip()
            require(blob == expected_file.get("gitBlobOid"), f"source Blob differs: {repository_id}:{relative}")
            source_cache[key] = raw.decode("utf-8")
        method, body = extract_method(source_cache[key], row["startSnippet"])
        require(bytes_digest(method.encode()) == row["methodSha256"], f"method bytes differ: {method_id}")
        require(bytes_digest(body.encode()) == row["bodySha256"], f"method body differs: {method_id}")
        transpiled = apply_replacements(body, row["transpileReplacements"], f"method {method_id}")
        require(method_id not in bodies[runtime], f"method id is duplicated: {method_id}")
        bodies[runtime][method_id] = transpiled
        evidence.append({
            "id": method_id,
            "runtime": runtime,
            "repositoryId": repository_id,
            "revision": repository_by_id[repository_id]["revision"],
            "path": relative,
            "methodSha256": row["methodSha256"],
            "bodySha256": row["bodySha256"],
            "transpiledBodySha256": bytes_digest(transpiled.encode()),
        })
    require(set(bodies["harmony"]) == {"dealPurchaseData", "finishPurchase"}, "Harmony methods differ")
    require(
        set(bodies["cordova"])
        == {"obtainOwnedPurchasesFromType", "createPurchasedProductOnList", "consumeOwnedPurchase"},
        "Cordova methods differ",
    )
    return bodies, evidence


def run_seam(node: str, seam_path: Path, bodies: dict[str, dict[str, str]]) -> tuple[dict[str, bool], str]:
    process = subprocess.run(
        [node, str(seam_path)],
        input=json.dumps({"bodies": bodies}, sort_keys=True),
        text=True,
        capture_output=True,
        timeout=15,
    )
    require(process.returncode == 0, f"behavior seam failed: {process.stderr.strip()}")
    try:
        value = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise CalibrationError(f"behavior seam output is invalid: {error}") from error
    require(isinstance(value, dict) and value.get("schema") == SEAM_RESULT_SCHEMA, "behavior seam schema differs")
    checks = value.get("checks")
    require(isinstance(checks, dict) and all(isinstance(item, bool) for item in checks.values()), "behavior seam checks are invalid")
    return checks, bytes_digest(process.stdout.encode())


def clone_bodies(value: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    return {runtime: dict(methods) for runtime, methods in value.items()}


def execute_variants(
    plan: dict[str, Any],
    bodies: dict[str, dict[str, str]],
    node: str,
    seam_path: Path,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    checks = plan.get("checks")
    variants = plan.get("variants")
    require(isinstance(checks, list) and checks, "plan checks are invalid")
    check_ids = [row.get("id") for row in checks if isinstance(row, dict)]
    require(len(check_ids) == len(checks) == len(set(check_ids)) and all(TOKEN.fullmatch(value or "") for value in check_ids), "plan check ids are invalid")
    require(isinstance(variants, list) and len(variants) >= 2, "plan variants are invalid")
    results = []
    negative_controls = []
    undetected = []
    for row in variants:
        require(isinstance(row, dict) and set(row) == {"id", "role", "mutations", "expectedFailedChecks"}, "variant fields differ")
        variant_id = row["id"]
        role = row["role"]
        require(TOKEN.fullmatch(variant_id or "") is not None and role in {"exact-source", "meaningful-wrong"}, "variant identity is invalid")
        variant_bodies = clone_bodies(bodies)
        for mutation in row["mutations"]:
            require(isinstance(mutation, dict) and set(mutation) == {"runtime", "methodId", "find", "replace", "occurrences"}, "variant mutation fields differ")
            runtime = mutation["runtime"]
            method_id = mutation["methodId"]
            require(runtime in variant_bodies and method_id in variant_bodies[runtime], "variant mutation target is invalid")
            variant_bodies[runtime][method_id] = apply_replacements(
                variant_bodies[runtime][method_id],
                [{key: mutation[key] for key in ("find", "replace", "occurrences")}],
                f"variant {variant_id}",
            )
        observed, output_sha256 = run_seam(node, seam_path, variant_bodies)
        require(set(observed) == set(check_ids), f"variant check inventory differs: {variant_id}")
        observed_failed = sorted(check_id for check_id, passed in observed.items() if not passed)
        expected_failed = sorted(row["expectedFailedChecks"])
        require(set(expected_failed) <= set(check_ids), f"variant expected failure is unknown: {variant_id}")
        expectation_matched = observed_failed == expected_failed
        if role == "meaningful-wrong":
            negative_controls.append(variant_id)
            if not observed_failed:
                undetected.append(variant_id)
        results.append({
            "id": variant_id,
            "role": role,
            "checks": observed,
            "observedFailedChecks": observed_failed,
            "expectedFailedChecks": expected_failed,
            "expectationMatched": expectation_matched,
            "seamOutputSha256": output_sha256,
        })
    exact = [row for row in results if row["role"] == "exact-source"]
    require(len(exact) == 1, "exact-source variant count differs")
    require(all(row["expectationMatched"] for row in results), "variant calibration expectation differs")
    return results, negative_controls, undetected


def qualify(
    plan_path: Path,
    packet_path: Path,
    qualification_path: Path,
    roots: dict[str, Path],
    node: str,
) -> dict[str, Any]:
    plan, packet, qualification = validate_lineage(plan_path, packet_path, qualification_path)
    seam_path = ROOT / "scripts/purchase-data-behavior-seam.js"
    require(digest(seam_path) == plan.get("seamExecutableSha256"), "behavior seam executable digest differs")
    bodies, method_evidence = read_methods(plan, roots)
    variant_results, negative_controls, undetected = execute_variants(plan, bodies, node, seam_path)
    node_process = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=5)
    require(node_process.returncode == 0 and node_process.stdout.strip(), "Node runtime identity is unavailable")
    exact = next(row for row in variant_results if row["role"] == "exact-source")
    return {
        "schema": RESULT_SCHEMA,
        "status": "source-seam-calibrated-independent-review-required",
        "candidateId": plan["candidateId"],
        "sourceSetSha256": plan["sourceSetSha256"],
        "methodRevision": plan["methodRevision"],
        "planSha256": digest(plan_path),
        "reviewPacketSha256": digest(packet_path),
        "controlFlowQualificationSha256": digest(qualification_path),
        "seamExecutableSha256": digest(seam_path),
        "runtime": {"command": node, "version": node_process.stdout.strip()},
        "methodEvidence": method_evidence,
        "checks": plan["checks"],
        "variants": variant_results,
        "coverage": {
            "repositoryCount": len(roots),
            "methodCount": len(method_evidence),
            "checkCount": len(exact["checks"]),
            "negativeControlCount": len(negative_controls),
            "undetectedNegativeControlCount": len(undetected),
            "exactSourceAllChecksPassed": not exact["observedFailedChecks"],
            "allNegativeControlsDetected": not undetected,
        },
        "qualificationBoundary": plan["qualificationBoundary"],
        "sourceSeamCalibrated": not exact["observedFailedChecks"] and not undetected,
        "semanticAlignmentVerified": False,
        "behaviorOracleVerified": False,
        "allowsCaseContract": False,
        "automaticPromotion": False,
        "nextGate": "independent-semantic-review-then-independent-oracle-review-and-runtime-calibration",
    }


def write(path: Path, value: dict[str, Any]) -> None:
    require(not path.exists(), f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--review-packet", type=Path, required=True)
    parser.add_argument("--control-flow-qualification", type=Path, required=True)
    parser.add_argument("--repository", action="append", default=[], metavar="ID=PATH")
    parser.add_argument("--node", default="node")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = qualify(
            args.plan,
            args.review_packet,
            args.control_flow_qualification,
            repository_arguments(args.repository),
            args.node,
        )
        write(args.output, result)
        print(json.dumps({
            "ok": True,
            "status": result["status"],
            "sourceSeamCalibrated": result["sourceSeamCalibrated"],
            "outputSha256": digest(args.output),
        }, sort_keys=True))
    except (CalibrationError, OSError, subprocess.SubprocessError, UnicodeDecodeError) as error:
        print(f"purchase-data behavior Oracle calibration invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
