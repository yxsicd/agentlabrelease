#!/usr/bin/env python3
"""Prepare, but never publish, a revision-fenced Harmony performance review transaction."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any


PLAN_SCHEMA = "agentlab.harmony_performance_review_plan.v1"
RECEIPT_SCHEMA = "agentlab.harmony_performance_review_preparation.v1"
REVISION = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
TOKEN = re.compile(r"[A-Za-z0-9_.:-]+")
REPOSITORY = re.compile(r"[^/\s]+/[^/\s]+")


class PreparationError(RuntimeError):
    pass


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def load_object(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PreparationError(f"cannot load JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise PreparationError(f"expected JSON object: {path}")
    return value


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def require_token(value: Any, label: str) -> str:
    if not isinstance(value, str) or TOKEN.fullmatch(value) is None:
        raise PreparationError(f"{label} must be a non-empty safe token")
    return value


def evidence_manifest(root: pathlib.Path) -> list[dict[str, Any]]:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise PreparationError("evidence directory is empty")
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in files
    ]


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if plan.get("schema") != PLAN_SCHEMA:
        raise PreparationError("unsupported review preparation plan schema")
    if plan.get("automaticPublication") is not False:
        raise PreparationError("review preparation plan must set automaticPublication=false")
    if plan.get("automaticPromotion") is not False:
        raise PreparationError("review preparation plan must set automaticPromotion=false")
    expected_revision = plan.get("expectedRevision")
    if not isinstance(expected_revision, str) or REVISION.fullmatch(expected_revision) is None:
        raise PreparationError("review preparation plan requires exact expectedRevision")
    github_repository = plan.get("githubRepository")
    if not isinstance(github_repository, str) or REPOSITORY.fullmatch(github_repository) is None:
        raise PreparationError("githubRepository must be owner/repository")
    evidence = pathlib.Path(str(plan.get("evidence", ""))).resolve()
    if not evidence.is_dir():
        raise PreparationError(f"evidence directory not found: {evidence}")
    builder = pathlib.Path(str(plan.get("transactionBuilder", ""))).resolve()
    if not builder.is_file():
        raise PreparationError(f"transaction builder not found: {builder}")
    if not os.access(builder, os.R_OK):
        raise PreparationError(f"transaction builder is not readable: {builder}")
    builder_sha256 = plan.get("transactionBuilderSha256")
    if not isinstance(builder_sha256, str) or SHA256.fullmatch(builder_sha256) is None:
        raise PreparationError("review preparation plan requires exact transactionBuilderSha256")
    if sha256(builder) != builder_sha256:
        raise PreparationError("transaction builder SHA256 differs from review preparation plan")
    return {
        "evidence": evidence,
        "builder": builder,
        "builderSha256": builder_sha256,
        "expectedRevision": expected_revision,
        "runId": require_token(plan.get("runId"), "runId"),
        "githubRepository": github_repository,
        "callerPersonId": require_token(plan.get("callerPersonId"), "callerPersonId"),
        "repo": require_token(plan.get("repo", "agentlabtablegit"), "repo"),
    }


def contains_true(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return value.get(key) is True or any(contains_true(child, key) for child in value.values())
    if isinstance(value, list):
        return any(contains_true(child, key) for child in value)
    return False


def validate_transaction(payload: dict[str, Any], validated: dict[str, Any]) -> dict[str, int]:
    if (
        payload.get("skill_id") != "table.author"
        or payload.get("skill_version") != "2.2.0"
        or payload.get("operation") != "worktree_table_batch_transaction"
    ):
        raise PreparationError("prepared transaction has unsupported TableGit operation")
    if payload.get("caller_person_id") != validated["callerPersonId"]:
        raise PreparationError("prepared transaction caller Person differs from plan")
    arguments = payload.get("arguments") or {}
    actor = arguments.get("actor") or {}
    if (
        arguments.get("repo") != validated["repo"]
        or arguments.get("expected_revision") != validated["expectedRevision"]
        or arguments.get("topic_id") != "main"
        or actor.get("repository") != validated["githubRepository"]
        or actor.get("runId") != validated["runId"]
    ):
        raise PreparationError("prepared transaction authority differs from plan")
    tables = arguments.get("tables")
    if not isinstance(tables, list) or not tables:
        raise PreparationError("prepared transaction contains no tables")
    rows = [
        operation.get("row")
        for table in tables
        if isinstance(table, dict)
        for operation in table.get("operations", [])
        if isinstance(operation, dict) and isinstance(operation.get("row"), dict)
    ]
    decisions = [row for row in rows if row.get("schema") == "agentlab.performance_feedback_decision.v1"]
    difficulties = [
        row for row in rows
        if row.get("dimensionId") == "functionally-correct-performance-regression"
    ]
    if len(decisions) != 1 or len(difficulties) != 1:
        raise PreparationError("prepared transaction requires one performance decision and difficulty")
    if contains_true(payload, "automaticPromotion"):
        raise PreparationError("prepared transaction attempts automatic promotion")
    difficulty = difficulties[0]
    verification = difficulty.get("verificationContract") or {}
    if verification.get("caseReady") is not False:
        raise PreparationError("prepared performance difficulty must remain non-ready")
    required = verification.get("required") or []
    if "maintainer-adjudication" not in required:
        raise PreparationError("prepared performance difficulty requires maintainer adjudication")
    receipt_path = validated["evidence"] / "calibration-run.json"
    if not receipt_path.is_file():
        raise PreparationError("automated calibration receipt is missing")
    receipt_sha256 = sha256(receipt_path)
    for row in decisions + difficulties:
        automation = ((row.get("performanceCalibration") or {}).get("automationRun") or {})
        if automation.get("sha256") != receipt_sha256:
            raise PreparationError("prepared transaction calibration receipt binding differs")
    return {
        "tables": len(tables),
        "rows": len(rows),
        "performanceDecisions": len(decisions),
        "performanceDifficulties": len(difficulties),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        print(f"refusing to overwrite existing output: {output}", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = pathlib.Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        plan_path = args.plan.resolve()
        plan_sha256 = sha256(plan_path)
        plan = load_object(plan_path)
        validated = validate_plan(plan)
        manifest = evidence_manifest(validated["evidence"])
        transaction_path = stage / "transaction.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(validated["builder"]),
                "--evidence", str(validated["evidence"]),
                "--revision", validated["expectedRevision"],
                "--run-id", validated["runId"],
                "--github-repository", validated["githubRepository"],
                "--caller-person-id", validated["callerPersonId"],
                "--repo", validated["repo"],
                "--output", str(transaction_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        stdout_path = stage / "builder.stdout.log"
        stderr_path = stage / "builder.stderr.log"
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            raise PreparationError(f"transaction builder failed with exit {completed.returncode}")
        if sha256(plan_path) != plan_sha256:
            raise PreparationError("review preparation plan changed during generation")
        if sha256(validated["builder"]) != validated["builderSha256"]:
            raise PreparationError("transaction builder changed during generation")
        if evidence_manifest(validated["evidence"]) != manifest:
            raise PreparationError("calibration evidence changed during generation")
        payload = load_object(transaction_path)
        counts = validate_transaction(payload, validated)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": "prepared-not-published",
            "planSha256": plan_sha256,
            "transactionBuilderSha256": validated["builderSha256"],
            "evidenceManifestSha256": canonical_sha256(manifest),
            "evidenceFileCount": len(manifest),
            "transactionSha256": sha256(transaction_path),
            "builderStdoutSha256": sha256(stdout_path),
            "builderStderrSha256": sha256(stderr_path),
            "expectedRevision": validated["expectedRevision"],
            "runId": validated["runId"],
            "callerPersonId": validated["callerPersonId"],
            "counts": counts,
            "automaticPublication": False,
            "automaticPromotion": False,
        }
        write_json(stage / "preparation.json", receipt)
        stage.rename(output)
        print(json.dumps({"ok": True, "output": str(output), **counts}, sort_keys=True))
        return 0
    except (PreparationError, OSError) as error:
        write_json(
            stage / "failure.json",
            {
                "schema": RECEIPT_SCHEMA,
                "status": "failed",
                "error": str(error),
                "automaticPublication": False,
                "automaticPromotion": False,
            },
        )
        print(json.dumps({"ok": False, "retained": str(stage), "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
