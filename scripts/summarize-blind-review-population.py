#!/usr/bin/env python3
"""Verify a frozen blind-review cohort and report population-level agreement."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any, Callable


MANIFEST_SCHEMA = "agentlab.blind_review_population_manifest.v1"
REPORT_SCHEMA = "agentlab.blind_review_population_report.v1"
DIMENSIONS = (
    "semanticLeakage",
    "contaminationRisk",
    "specificationFairness",
    "oracleBreadth",
)
VERDICTS = {"qualified", "rejected", "unknown"}
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,160}")
Verifier = Callable[[Path, str, int, Path], dict[str, Any]]


class PopulationReviewError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise PopulationReviewError(message)


def load_object(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PopulationReviewError(f"cannot read {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must contain an object")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    require(not path.exists(), f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def portable_directory(root: Path, value: Any, label: str) -> Path:
    require(isinstance(value, str) and value, f"{label} path is required")
    relative = Path(value)
    require(not relative.is_absolute(), f"{label} path must be relative")
    unresolved = root / relative
    require(not unresolved.is_symlink(), f"{label} path must not be a symlink")
    try:
        resolved = unresolved.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise PopulationReviewError(f"{label} path escapes or is absent") from error
    require(resolved.is_dir(), f"{label} path must be a directory")
    return resolved


def evidence_ref(path: Path, root: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"evidence file is absent: {path}")
    try:
        relative = path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise PopulationReviewError(f"evidence file escapes its root: {path}") from error
    return {
        "path": relative.as_posix(),
        "sha256": digest(path),
        "byteLength": path.stat().st_size,
    }


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> dict[str, float]:
    require(0 <= successes <= total and total > 0, "Wilson interval denominator is invalid")
    probability = successes / total
    denominator = 1.0 + z * z / total
    center = (probability + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            probability * (1.0 - probability) / total
            + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return {
        "confidenceLevel": 0.95,
        "lower": max(0.0, center - margin),
        "upper": min(1.0, center + margin),
    }


def authenticated_module():
    path = Path(__file__).with_name("authenticate-blind-case-review.py")
    spec = importlib.util.spec_from_file_location(
        "agentlab_population_authenticated_review", path
    )
    require(spec is not None and spec.loader is not None, "authenticated review verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def online_verifier(
    bundle: Path,
    repository: str,
    run_id: int,
    verification_output: Path,
) -> dict[str, Any]:
    return authenticated_module().verify_authenticated_bundle_online(
        bundle,
        repository,
        run_id,
        verification_output,
    )


def validate_sampling_frame(value: Any) -> dict[str, Any]:
    require(isinstance(value, dict), "samplingFrame must be an object")
    require(set(value) == {"id", "description", "selectionPolicy", "declaredRepresentative"}, "samplingFrame fields differ")
    require(isinstance(value.get("id"), str) and TOKEN.fullmatch(value["id"]), "samplingFrame id is invalid")
    for field in ("description", "selectionPolicy"):
        require(isinstance(value.get(field), str) and value[field].strip(), f"samplingFrame {field} is required")
    require(value.get("declaredRepresentative") is False, "population representativeness requires a separate qualified review")
    return {
        "id": value["id"],
        "description": value["description"].strip(),
        "selectionPolicy": value["selectionPolicy"].strip(),
        "declaredRepresentative": False,
    }


def validate_adjudication(value: dict[str, Any], case_id: str) -> None:
    require(value.get("schema") == "agentlab.blind_case_authenticated_review_adjudication.v1", f"{case_id} adjudication schema differs")
    require(value.get("caseId") == case_id, f"{case_id} adjudication case identity differs")
    require(value.get("reviewerIdentityAuthenticationQualified") is True, f"{case_id} reviewer identity is not authenticated")
    require(value.get("attestedWorkflowProvenanceQualified") is True, f"{case_id} workflow provenance is not attested")
    require(value.get("modelTrainingExclusionQualified") is False, f"{case_id} overclaims model-training exclusion")
    require(value.get("eligibleForUnseenAgentDiscrimination") is False, f"{case_id} overclaims unseen-Agent eligibility")
    require(value.get("automaticPromotion") is False, f"{case_id} adjudication cannot auto-promote")
    require(isinstance(value.get("cutId"), str) and TOKEN.fullmatch(value["cutId"]), f"{case_id} cut identity is invalid")
    for field in ("sourceSetSha256", "participantManifestSha256", "evaluatorManifestSha256"):
        require(isinstance(value.get(field), str) and SHA256.fullmatch(value[field]), f"{case_id} {field} is invalid")
    review_count = value.get("reviewCount")
    require(isinstance(review_count, int) and review_count >= 2, f"{case_id} review count is invalid")
    dimensions = value.get("dimensions")
    require(isinstance(dimensions, dict) and set(dimensions) == set(DIMENSIONS), f"{case_id} review dimensions differ")
    for dimension in DIMENSIONS:
        row = dimensions[dimension]
        require(isinstance(row, dict), f"{case_id} {dimension} result is invalid")
        verdicts = row.get("verdicts")
        require(
            isinstance(verdicts, list)
            and len(verdicts) == review_count
            and verdicts == sorted(verdicts)
            and all(verdict in VERDICTS for verdict in verdicts),
            f"{case_id} {dimension} verdicts are invalid",
        )
        unanimous = len(set(verdicts)) == 1
        qualified = unanimous and verdicts[0] == "qualified"
        require(row.get("unanimous") is unanimous, f"{case_id} {dimension} unanimity differs")
        require(row.get("qualified") is qualified, f"{case_id} {dimension} qualification differs")
    expected_consensus = all(dimensions[dimension]["qualified"] for dimension in DIMENSIONS)
    require(value.get("reviewConsensusQualified") is expected_consensus, f"{case_id} review consensus differs")
    require(value.get("blindPilotReviewQualified") is expected_consensus, f"{case_id} blind-pilot qualification differs")


def validate_online_verification(
    path: Path,
    repository: str,
    run_id: int,
    adjudication_path: Path,
) -> dict[str, Any]:
    value = load_object(path, "online adjudication attestation verification")
    require(value.get("schema") == "agentlab.blind_case_online_attestation_verification.v1", "online verification schema differs")
    require(value.get("repository") == repository, "online verification repository differs")
    require(value.get("workflowPath") == ".github/workflows/blind-case-review-adjudication.yml", "online verification workflow differs")
    require(value.get("workflowRunId") == run_id, "online verification run id differs")
    require(isinstance(value.get("workflowRunAttempt"), int) and value["workflowRunAttempt"] > 0, "online verification run attempt is invalid")
    head_sha = value.get("workflowHeadSha")
    require(isinstance(head_sha, str) and REVISION.fullmatch(head_sha), "online verification revision is invalid")
    require(value.get("subjectPath") == adjudication_path.name, "online verification subject path differs")
    require(value.get("subjectSha256") == digest(adjudication_path), "online verification subject digest differs")
    require(value.get("policy") == {
        "repository": repository,
        "signerWorkflow": f"{repository}/.github/workflows/blind-case-review-adjudication.yml",
        "sourceRef": "refs/heads/main",
        "sourceDigest": head_sha,
        "denySelfHostedRunners": True,
    }, "online verification policy differs")
    require(isinstance(value.get("verification"), list) and value["verification"], "online verification statement is empty")
    return value


def dimension_outcome(row: dict[str, Any]) -> str:
    if not row["unanimous"]:
        return "disagreement"
    return row["verdicts"][0]


def build_report(
    manifest_path: Path,
    evidence_root: Path,
    verifier: Verifier = online_verifier,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve(strict=True)
    manifest_root = manifest_path.parent
    manifest = load_object(manifest_path, "blind review population manifest")
    require(manifest.get("schema") == MANIFEST_SCHEMA, "unsupported blind review population manifest schema")
    cohort_id = manifest.get("cohortId")
    require(isinstance(cohort_id, str) and TOKEN.fullmatch(cohort_id), "cohortId is invalid")
    method_revision = manifest.get("methodRevision")
    require(isinstance(method_revision, str) and REVISION.fullmatch(method_revision), "methodRevision is invalid")
    sampling_frame = validate_sampling_frame(manifest.get("samplingFrame"))
    cases = manifest.get("cases")
    require(isinstance(cases, list) and len(cases) >= 2, "population report requires at least two cases")
    require(len(cases) <= 100, "population report supports at most 100 cases")

    seen_case_ids: set[str] = set()
    seen_run_ids: set[tuple[str, int]] = set()
    seen_bundles: set[Path] = set()
    case_rows = []
    reviewer_case_counts: dict[str, int] = {}
    statistics = {
        dimension: {outcome: 0 for outcome in (*sorted(VERDICTS), "disagreement")}
        for dimension in DIMENSIONS
    }
    review_record_count = 0

    evidence_root.mkdir(parents=True, exist_ok=True)
    verification_root = evidence_root / "verification"
    verification_root.mkdir()

    for case in cases:
        require(isinstance(case, dict), "population case must be an object")
        require(set(case) == {"caseId", "bundle", "repository", "adjudicationRunId"}, "population case fields differ")
        case_id = case.get("caseId")
        repository = case.get("repository")
        run_id = case.get("adjudicationRunId")
        require(isinstance(case_id, str) and TOKEN.fullmatch(case_id), "population caseId is invalid")
        require(case_id not in seen_case_ids, f"duplicate population caseId: {case_id}")
        require(isinstance(repository, str) and REPOSITORY.fullmatch(repository), f"{case_id} repository is invalid")
        require(isinstance(run_id, int) and run_id > 0, f"{case_id} adjudication run id is invalid")
        require((repository, run_id) not in seen_run_ids, f"duplicate adjudication run: {repository}#{run_id}")
        bundle = portable_directory(manifest_root, case.get("bundle"), f"{case_id} bundle")
        require(bundle not in seen_bundles, f"duplicate population bundle: {bundle}")
        seen_case_ids.add(case_id)
        seen_run_ids.add((repository, run_id))
        seen_bundles.add(bundle)

        verification_path = verification_root / f"{case_id}.json"
        adjudication = verifier(bundle, repository, run_id, verification_path)
        validate_adjudication(adjudication, case_id)
        online_verification = validate_online_verification(
            verification_path,
            repository,
            run_id,
            bundle / "authenticated-adjudication.json",
        )
        verification = evidence_ref(verification_path, evidence_root)
        review_count = adjudication["reviewCount"]
        review_record_count += review_count
        reviews = adjudication.get("reviews")
        require(isinstance(reviews, list) and len(reviews) == review_count, f"{case_id} reviewer records differ")
        require(
            all(
                isinstance(review, dict)
                and isinstance(review.get("reviewer"), str)
                and review["reviewer"]
                for review in reviews
            ),
            f"{case_id} reviewer identities are invalid",
        )
        reviewers = sorted(review["reviewer"] for review in reviews)
        require(len(set(reviewers)) == review_count, f"{case_id} reviewers are not distinct")
        for reviewer in reviewers:
            reviewer_case_counts[reviewer] = reviewer_case_counts.get(reviewer, 0) + 1

        outcomes = {}
        for dimension in DIMENSIONS:
            outcome = dimension_outcome(adjudication["dimensions"][dimension])
            statistics[dimension][outcome] += 1
            outcomes[dimension] = outcome

        bundle_files = {
            "adjudication": bundle / "authenticated-adjudication.json",
            "request": bundle / "request.json",
            "cutReceipt": bundle / "source/blind-cut/cut-receipt.json",
            "participantManifest": bundle / "source/blind-cut/participant/manifest.json",
            "evaluatorManifest": bundle / "source/blind-cut/evaluator/manifest.json",
            "firstDecision": bundle / "first/artifact/decision.json",
            "firstProvenance": bundle / "first/provenance.json",
            "secondDecision": bundle / "second/artifact/decision.json",
            "secondProvenance": bundle / "second/provenance.json",
        }
        case_rows.append(
            {
                "caseId": case_id,
                "cutId": adjudication["cutId"],
                "sourceSetSha256": adjudication["sourceSetSha256"],
                "participantManifestSha256": adjudication["participantManifestSha256"],
                "evaluatorManifestSha256": adjudication["evaluatorManifestSha256"],
                "repository": repository,
                "adjudicationRunId": run_id,
                "adjudicationRunAttempt": online_verification["workflowRunAttempt"],
                "adjudicationWorkflowHeadSha": online_verification["workflowHeadSha"],
                "reviewCount": review_count,
                "reviewers": reviewers,
                "dimensionOutcomes": outcomes,
                "reviewConsensusQualified": adjudication.get("reviewConsensusQualified") is True,
                "blindPilotReviewQualified": adjudication.get("blindPilotReviewQualified") is True,
                "modelTrainingExclusionQualified": False,
                "eligibleForUnseenAgentDiscrimination": False,
                "bundleEvidence": {
                    name: evidence_ref(path, bundle)
                    for name, path in sorted(bundle_files.items())
                },
                "onlineAttestationVerification": verification,
            }
        )

    case_rows.sort(key=lambda row: row["caseId"])
    case_count = len(case_rows)
    dimension_statistics = {}
    for dimension in DIMENSIONS:
        counts = statistics[dimension]
        disagreement_count = counts["disagreement"]
        dimension_statistics[dimension] = {
            "caseCount": case_count,
            "qualifiedConsensusCaseCount": counts["qualified"],
            "rejectedConsensusCaseCount": counts["rejected"],
            "unknownConsensusCaseCount": counts["unknown"],
            "disagreementCaseCount": disagreement_count,
            "disagreementRate": disagreement_count / case_count,
            "disagreementRateWilson95": wilson_interval(disagreement_count, case_count),
        }

    membership = [
        {
            "caseId": row["caseId"],
            "repository": row["repository"],
            "adjudicationRunId": row["adjudicationRunId"],
            "adjudicationRunAttempt": row["adjudicationRunAttempt"],
            "adjudicationWorkflowHeadSha": row["adjudicationWorkflowHeadSha"],
            "sourceSetSha256": row["sourceSetSha256"],
            "adjudicationSha256": row["bundleEvidence"]["adjudication"]["sha256"],
        }
        for row in case_rows
    ]
    blind_pilot_count = sum(row["blindPilotReviewQualified"] for row in case_rows)
    repeated_reviewers = sorted(
        reviewer for reviewer, count in reviewer_case_counts.items() if count > 1
    )
    return {
        "schema": REPORT_SCHEMA,
        "cohortId": cohort_id,
        "methodRevision": method_revision,
        "manifestSha256": digest(manifest_path),
        "caseMembershipSha256": canonical_digest(membership),
        "samplingFrame": sampling_frame,
        "denominators": {
            "caseCount": case_count,
            "reviewRecordCount": review_record_count,
            "uniqueAuthenticatedReviewerCount": len(reviewer_case_counts),
            "requiredDimensions": list(DIMENSIONS),
            "invalidCasePolicy": "fail-entire-report",
        },
        "reviewerReuse": {
            "reviewersWithMultipleCases": repeated_reviewers,
            "reviewerCaseCounts": [
                {"reviewer": reviewer, "caseCount": count}
                for reviewer, count in sorted(reviewer_case_counts.items())
            ],
        },
        "dimensionStatistics": dimension_statistics,
        "cases": case_rows,
        "qualification": {
            "allCasesAuthenticatedAndAttested": True,
            "blindPilotReviewQualifiedCaseCount": blind_pilot_count,
            "allCasesBlindPilotReviewQualified": blind_pilot_count == case_count,
            "populationRepresentativenessQualified": False,
            "modelTrainingExclusionQualified": False,
            "eligibleForUnseenAgentDiscrimination": False,
        },
        "policy": {
            "automaticPromotion": False,
            "nextAction": "independent-population-representativeness-review-and-agent-trials",
        },
    }


def produce(manifest: Path, output: Path, verifier: Verifier = online_verifier) -> dict[str, Any]:
    require(not output.exists(), f"refusing to overwrite output: {output}")
    output_parent = output.resolve().parent
    output_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".blind-review-population-", dir=output_parent) as raw:
        stage = Path(raw) / "population"
        stage.mkdir()
        shutil.copy2(manifest, stage / "input-manifest.json")
        report = build_report(manifest, stage, verifier)
        write_json(stage / "report.json", report)
        os.replace(stage, output)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = produce(args.manifest, args.output)
    except (PopulationReviewError, OSError, ValueError) as error:
        print(f"blind review population invalid: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "schema": report["schema"],
                "caseCount": report["denominators"]["caseCount"],
                "allCasesBlindPilotReviewQualified": report["qualification"]["allCasesBlindPilotReviewQualified"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
