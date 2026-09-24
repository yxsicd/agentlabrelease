#!/usr/bin/env python3
"""Collect independently assessed run evidence into case discrimination input."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from typing import Any


MANIFEST_SCHEMA = "agentlab.case_attempt_collection.v1"
OUTPUT_SCHEMA = "agentlab.case_discrimination_input.v1"
DECISION_SCHEMA = "agentlab.harness_decision_package.v1"
REVISION = re.compile(r"[0-9a-f]{40}")


def fail(message: str) -> None:
    raise ValueError(message)


def load_object(path: pathlib.Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        fail(f"{label} not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_path(root: pathlib.Path, value: Any, label: str) -> pathlib.Path:
    if not isinstance(value, str) or not value:
        fail(f"{label} path required")
    relative = pathlib.Path(value)
    if relative.is_absolute():
        fail(f"{label} path must be relative to the manifest")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        fail(f"{label} path escapes the manifest directory")
    return resolved


def evidence_ref(path: pathlib.Path, root: pathlib.Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256(path),
        "byteLength": path.stat().st_size,
    }


def build_input(manifest: dict[str, Any], manifest_dir: pathlib.Path) -> dict[str, Any]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        fail("unsupported case attempt collection schema")
    source_revision = manifest.get("sourceRevision")
    method_revision = manifest.get("methodRevision")
    if not isinstance(source_revision, str) or not REVISION.fullmatch(source_revision):
        fail("sourceRevision must be a lowercase 40-character Git revision")
    if not isinstance(method_revision, str) or not REVISION.fullmatch(method_revision):
        fail("methodRevision must be a lowercase 40-character Git revision")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        fail("cases required")

    output_cases: list[dict[str, Any]] = []
    seen_cases: set[str] = set()
    seen_attempts: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            fail("case must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id or case_id in seen_cases:
            fail("case id must be present and unique")
        seen_cases.add(case_id)
        calibration_path = portable_path(
            manifest_dir, case.get("calibration"), f"{case_id} calibration"
        )
        calibration = load_object(calibration_path, f"{case_id} calibration")
        attempts = case.get("attempts")
        if not isinstance(attempts, list) or not attempts:
            fail(f"{case_id} attempts required")

        output_attempts: list[dict[str, Any]] = []
        for attempt in attempts:
            if not isinstance(attempt, dict):
                fail(f"{case_id} attempt must be an object")
            attempt_id = attempt.get("attemptId")
            participant_id = attempt.get("participantId")
            if (
                not isinstance(attempt_id, str)
                or not attempt_id
                or attempt_id in seen_attempts
            ):
                fail("attemptId must be present and globally unique")
            seen_attempts.add(attempt_id)
            if not isinstance(participant_id, str) or not participant_id:
                fail(f"{attempt_id} participantId required")

            evidence_dir = portable_path(
                manifest_dir, attempt.get("evidence"), f"{attempt_id} evidence"
            )
            summary_path = evidence_dir / "summary.json"
            decision_path = evidence_dir / "decision-package.json"
            summary = load_object(summary_path, f"{attempt_id} summary")
            decision = load_object(decision_path, f"{attempt_id} decision package")
            if decision.get("schema") != DECISION_SCHEMA:
                fail(f"{attempt_id} unsupported decision package schema")
            for label, document in (("summary", summary), ("decision package", decision)):
                if document.get("taskId") != case_id:
                    fail(f"{attempt_id} {label} taskId does not match {case_id}")
                if document.get("sourceRevision") != source_revision:
                    fail(f"{attempt_id} {label} sourceRevision mismatch")

            infrastructure_valid = (
                decision.get("assessmentStatus") == "assessed"
                and decision.get("infrastructureAvailable") is True
            )
            verdict = decision.get("subjectTaskSucceeded")
            if infrastructure_valid and not isinstance(verdict, bool):
                fail(f"{attempt_id} assessed run requires boolean subjectTaskSucceeded")
            output_attempts.append(
                {
                    "attemptId": attempt_id,
                    "participantId": participant_id,
                    "producerRun": attempt.get("producerRun"),
                    "infrastructureValid": infrastructure_valid,
                    "taskPassed": verdict if infrastructure_valid else None,
                    "verdictSource": "independent-harness-decision-package",
                    "evidence": {
                        "summary": evidence_ref(summary_path, manifest_dir),
                        "decisionPackage": evidence_ref(decision_path, manifest_dir),
                    },
                }
            )
        output_cases.append(
            {
                "id": case_id,
                "calibration": calibration,
                "calibrationEvidence": evidence_ref(calibration_path, manifest_dir),
                "attempts": output_attempts,
            }
        )

    return {
        "schema": OUTPUT_SCHEMA,
        "sourceRevision": source_revision,
        "methodRevision": method_revision,
        "cases": output_cases,
        "collectionPolicy": {
            "verdictAuthority": "decision-package.json",
            "infrastructureFailureIsAgentFailure": False,
            "automaticPromotion": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    manifest = load_object(manifest_path, "collection manifest")
    result = build_input(manifest, manifest_path.parent)
    body = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            fail(f"refusing to overwrite existing output: {args.output}")
        args.output.write_text(body, encoding="utf-8")
    else:
        print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
