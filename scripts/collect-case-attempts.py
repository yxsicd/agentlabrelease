#!/usr/bin/env python3
"""Collect independently assessed run evidence into case discrimination input."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from typing import Any


MANIFEST_SCHEMAS = {
    "agentlab.case_attempt_collection.v1": (
        "agentlab.case_discrimination_input.v1",
        "sourceRevision",
        re.compile(r"[0-9a-f]{40}"),
    ),
    "agentlab.case_attempt_collection.v2": (
        "agentlab.case_discrimination_input.v2",
        "sourceSetSha256",
        re.compile(r"[0-9a-f]{64}"),
    ),
}
DECISION_SCHEMA = "agentlab.harness_decision_package.v1"
EMULATOR_SCHEMA = "agentlab.harmony_emulator_case_result.v2"
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


def normalize_calibration(
    calibration: dict[str, Any], source_identity_field: str, source_identity: str
) -> dict[str, Any]:
    if calibration.get("schema") != "agentlab.multi_repo_calibration.v1":
        return calibration
    if source_identity_field != "sourceSetSha256":
        fail("multi-repository calibration requires sourceSetSha256 collection")
    if calibration.get("sourceSetSha256") != source_identity:
        fail("multi-repository calibration sourceSetSha256 mismatch")
    if calibration.get("infrastructureAvailable") is not True:
        fail("multi-repository calibration infrastructure is unavailable")
    variants = calibration.get("variants")
    if not isinstance(variants, dict) or not {"baseline", "reference"}.issubset(variants):
        fail("multi-repository calibration requires baseline and reference variants")

    def variant_pass(name: str) -> tuple[bool, dict[str, bool]]:
        row = variants.get(name)
        stages = row.get("stages") if isinstance(row, dict) else None
        if not isinstance(stages, dict) or not stages:
            fail(f"multi-repository calibration variant {name} has no stages")
        stage_pass = {}
        for stage_id, stage in stages.items():
            verdict = stage.get("pass") if isinstance(stage, dict) else None
            if not isinstance(stage_id, str) or not stage_id or not isinstance(verdict, bool):
                fail(f"multi-repository calibration variant {name} has invalid stage")
            stage_pass[stage_id] = verdict
        return all(stage_pass.values()), stage_pass

    baseline_pass, baseline_stages = variant_pass("baseline")
    reference_pass, reference_stages = variant_pass("reference")
    negative_variants = []
    for name in sorted(set(variants) - {"baseline", "reference"}):
        observed, stages = variant_pass(name)
        negative_variants.append(
            {
                "id": name,
                "expectedPass": False,
                "observedPass": observed,
                "infrastructureValid": True,
                "stagePass": stages,
            }
        )
    if not negative_variants:
        fail("multi-repository calibration requires negative variants")
    return {
        "schema": "agentlab.case_calibration_summary.v1",
        "sourceSchema": "agentlab.multi_repo_calibration.v1",
        "sourceSetSha256": source_identity,
        "infrastructureValid": True,
        "baselineExpectedPass": False,
        "baselineObservedPass": baseline_pass,
        "baselineStagePass": baseline_stages,
        "referenceExpectedPass": True,
        "referenceObservedPass": reference_pass,
        "referenceStagePass": reference_stages,
        "negativeVariants": negative_variants,
    }


def collect_harness_attempt(
    attempt: dict[str, Any],
    attempt_id: str,
    case_id: str,
    source_identity_field: str,
    source_identity: str,
    evidence_dir: pathlib.Path,
    manifest_dir: pathlib.Path,
) -> tuple[bool, bool | None, str, dict[str, Any]]:
    summary_path = evidence_dir / "summary.json"
    decision_path = evidence_dir / "decision-package.json"
    summary = load_object(summary_path, f"{attempt_id} summary")
    decision = load_object(decision_path, f"{attempt_id} decision package")
    if decision.get("schema") != DECISION_SCHEMA:
        fail(f"{attempt_id} unsupported decision package schema")
    for label, document in (("summary", summary), ("decision package", decision)):
        if document.get("taskId") != case_id:
            fail(f"{attempt_id} {label} taskId does not match {case_id}")
        if document.get(source_identity_field) != source_identity:
            fail(f"{attempt_id} {label} {source_identity_field} mismatch")

    infrastructure_valid = (
        decision.get("assessmentStatus") == "assessed"
        and decision.get("infrastructureAvailable") is True
    )
    verdict = decision.get("subjectTaskSucceeded")
    if infrastructure_valid and not isinstance(verdict, bool):
        fail(f"{attempt_id} assessed run requires boolean subjectTaskSucceeded")
    return (
        infrastructure_valid,
        verdict if infrastructure_valid else None,
        "independent-harness-decision-package",
        {
            "summary": evidence_ref(summary_path, manifest_dir),
            "decisionPackage": evidence_ref(decision_path, manifest_dir),
        },
    )


def collect_emulator_attempt(
    attempt: dict[str, Any],
    attempt_id: str,
    case_id: str,
    evidence_dir: pathlib.Path,
    manifest_dir: pathlib.Path,
) -> tuple[bool, bool | None, str, dict[str, Any]]:
    result_path = evidence_dir / "result.json"
    result = load_object(result_path, f"{attempt_id} emulator result")
    if result.get("schema") != EMULATOR_SCHEMA:
        fail(f"{attempt_id} unsupported emulator result schema")
    if result.get("taskId") != case_id:
        fail(f"{attempt_id} emulator taskId does not match {case_id}")
    expected_identity = attempt.get("sourceIdentity")
    if not isinstance(expected_identity, str) or not expected_identity:
        fail(f"{attempt_id} sourceIdentity required for emulator evidence")
    if result.get("sourceIdentity") != expected_identity:
        fail(f"{attempt_id} emulator sourceIdentity mismatch")
    if result.get("powerThermalAuthority") != "unavailable_on_emulator":
        fail(f"{attempt_id} emulator power/thermal authority is invalid")

    assessment_status = result.get("assessmentStatus")
    infrastructure_available = result.get("infrastructureAvailable")
    verdict = result.get("subjectTaskSucceeded")
    if assessment_status == "assessed" and infrastructure_available is True:
        if not isinstance(verdict, bool):
            fail(f"{attempt_id} assessed emulator run requires boolean verdict")
        if verdict and not (
            result.get("status") == "passed" and result.get("oracleStatus") == "passed"
        ):
            fail(f"{attempt_id} passing emulator verdict contradicts result status")
        if not verdict and not (
            result.get("status") == "failed" and result.get("oracleStatus") == "failed"
        ):
            fail(f"{attempt_id} failing emulator verdict contradicts result status")
        infrastructure_valid = True
    elif (
        assessment_status == "infrastructure-unavailable"
        and infrastructure_available is False
        and verdict is None
    ):
        infrastructure_valid = False
    else:
        fail(f"{attempt_id} emulator assessment fields are inconsistent")
    return (
        infrastructure_valid,
        verdict if infrastructure_valid else None,
        "operator-owned-harmony-ui-oracle",
        {"emulatorResult": evidence_ref(result_path, manifest_dir)},
    )


def build_input(manifest: dict[str, Any], manifest_dir: pathlib.Path) -> dict[str, Any]:
    manifest_contract = MANIFEST_SCHEMAS.get(manifest.get("schema"))
    if manifest_contract is None:
        fail("unsupported case attempt collection schema")
    output_schema, source_identity_field, source_identity_pattern = manifest_contract
    source_identity = manifest.get(source_identity_field)
    method_revision = manifest.get("methodRevision")
    if not isinstance(source_identity, str) or not source_identity_pattern.fullmatch(source_identity):
        fail(f"{source_identity_field} has invalid exact identity")
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
        calibration = normalize_calibration(
            calibration, source_identity_field, source_identity
        )
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
            evidence_kind = attempt.get("evidenceKind", "harness-decision-package")
            if evidence_kind == "harness-decision-package":
                infrastructure_valid, verdict, verdict_source, evidence = (
                    collect_harness_attempt(
                        attempt,
                        attempt_id,
                        case_id,
                        source_identity_field,
                        source_identity,
                        evidence_dir,
                        manifest_dir,
                    )
                )
            elif evidence_kind == "harmony-emulator-v2":
                infrastructure_valid, verdict, verdict_source, evidence = (
                    collect_emulator_attempt(
                        attempt, attempt_id, case_id, evidence_dir, manifest_dir
                    )
                )
            else:
                fail(f"{attempt_id} unsupported evidenceKind: {evidence_kind}")
            output_attempts.append(
                {
                    "attemptId": attempt_id,
                    "participantId": participant_id,
                    "producerRun": attempt.get("producerRun"),
                    "infrastructureValid": infrastructure_valid,
                    "taskPassed": verdict,
                    "verdictSource": verdict_source,
                    "evidence": evidence,
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
        "schema": output_schema,
        source_identity_field: source_identity,
        "methodRevision": method_revision,
        "cases": output_cases,
        "collectionPolicy": {
            "verdictAuthorities": [
                "decision-package.json",
                "operator-owned-harmony-ui-oracle",
            ],
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
