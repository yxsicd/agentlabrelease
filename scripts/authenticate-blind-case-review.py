#!/usr/bin/env python3
"""Bind blind-case review decisions to verified GitHub workflow provenance."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any


PROVENANCE_SCHEMA = "agentlab.blind_case_review_provenance.v1"
ADJUDICATION_SCHEMA = "agentlab.blind_case_authenticated_review_adjudication.v1"
ONLINE_VERIFICATION_SCHEMA = "agentlab.blind_case_online_attestation_verification.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
WORKFLOW = re.compile(r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml")
SLSA_PROVENANCE = "https://slsa.dev/provenance/v1"
REVIEW_WORKFLOW_PATH = ".github/workflows/blind-case-independent-review.yml"
ADJUDICATION_WORKFLOW_PATH = ".github/workflows/blind-case-review-adjudication.yml"


class AuthenticationError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise AuthenticationError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, label: str) -> Any:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuthenticationError(f"cannot read {label}: {error}") from error


def write_json(path: Path, value: dict[str, Any]) -> None:
    require(not path.exists(), f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def review_module():
    path = Path(__file__).with_name("review-blind-case-cut.py")
    spec = importlib.util.spec_from_file_location("agentlab_authenticated_blind_review", path)
    require(spec is not None and spec.loader is not None, "blind review module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def attestation_match(
    verification: Any,
    decision_sha256: str,
    run_id: int,
    run_attempt: int,
) -> dict[str, Any]:
    require(isinstance(verification, list) and verification, "GitHub attestation verification is empty")
    expected_suffix = f"/actions/runs/{run_id}/attempts/{run_attempt}"
    for row in verification:
        result = row.get("verificationResult") if isinstance(row, dict) else None
        statement = result.get("statement") if isinstance(result, dict) else None
        if not isinstance(statement, dict) or statement.get("predicateType") != SLSA_PROVENANCE:
            continue
        subjects = statement.get("subject")
        if not isinstance(subjects, list) or not any(
            isinstance(subject, dict)
            and isinstance(subject.get("digest"), dict)
            and subject["digest"].get("sha256") == decision_sha256
            for subject in subjects
        ):
            continue
        predicate = statement.get("predicate") or {}
        invocation = ((predicate.get("runDetails") or {}).get("metadata") or {}).get("invocationId")
        if isinstance(invocation, str) and invocation.endswith(expected_suffix):
            return row
    raise AuthenticationError("attestation does not bind the decision to the expected workflow run")


def authenticate(
    *,
    request_path: Path,
    decision_path: Path,
    run_metadata_path: Path,
    attestation_verification_path: Path,
    repository: str,
    workflow_path: str,
    expected_head_sha: str,
    output: Path,
) -> dict[str, Any]:
    require(REPOSITORY.fullmatch(repository) is not None, "expected repository is invalid")
    require(WORKFLOW.fullmatch(workflow_path) is not None, "expected workflow path is invalid")
    require(REVISION.fullmatch(expected_head_sha) is not None, "expected workflow revision is invalid")
    module = review_module()
    decision = module.validate_decision(decision_path, request_path)
    run = load(run_metadata_path, "GitHub workflow run metadata")
    require(isinstance(run, dict), "GitHub workflow run metadata must be an object")
    run_id = run.get("id")
    run_attempt = run.get("run_attempt")
    require(isinstance(run_id, int) and run_id > 0, "GitHub workflow run id is invalid")
    require(isinstance(run_attempt, int) and run_attempt > 0, "GitHub workflow run attempt is invalid")
    require((run.get("repository") or {}).get("full_name") == repository, "review workflow repository differs")
    require(run.get("path") == workflow_path, "review workflow path differs")
    require(run.get("event") == "workflow_dispatch", "review was not manually dispatched")
    require(run.get("head_branch") == "main", "review workflow did not run on main")
    require(run.get("head_sha") == expected_head_sha, "review workflow revision differs")
    require(run.get("status") == "completed" and run.get("conclusion") == "success", "review workflow did not succeed")
    reviewer = decision["reviewer"]
    require((run.get("actor") or {}).get("login") == reviewer, "review decision does not match the authenticated run actor")
    require((run.get("triggering_actor") or {}).get("login") == reviewer, "review decision does not match the authenticated triggering actor")
    verification = load(attestation_verification_path, "GitHub attestation verification")
    decision_sha256 = digest(decision_path)
    matched = attestation_match(verification, decision_sha256, run_id, run_attempt)
    provenance = {
        "schema": PROVENANCE_SCHEMA,
        "requestSha256": digest(request_path),
        "decisionSha256": decision_sha256,
        "reviewer": reviewer,
        "repository": repository,
        "workflowPath": workflow_path,
        "workflowRunId": run_id,
        "workflowRunAttempt": run_attempt,
        "workflowEvent": "workflow_dispatch",
        "workflowHeadBranch": "main",
        "workflowHeadSha": expected_head_sha,
        "actorAuthenticatedByGitHub": True,
        "attestationVerified": True,
        "attestationPredicateType": SLSA_PROVENANCE,
        "attestationVerificationSha256": digest(attestation_verification_path),
        "matchedAttestationSha256": hashlib.sha256(
            json.dumps(matched, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "verificationPolicy": {
            "repository": repository,
            "signerWorkflow": f"{repository}/{workflow_path}",
            "sourceRef": "refs/heads/main",
            "sourceDigest": expected_head_sha,
            "denySelfHostedRunners": True,
        },
        "automaticPromotion": False,
    }
    write_json(output, provenance)
    return provenance


def validate_provenance(
    path: Path,
    request_path: Path,
    decision_path: Path,
    repository: str,
    workflow_path: str,
    expected_head_sha: str,
) -> dict[str, Any]:
    module = review_module()
    decision = module.validate_decision(decision_path, request_path)
    value = load(path, "blind review provenance")
    require(isinstance(value, dict) and value.get("schema") == PROVENANCE_SCHEMA, "unsupported blind review provenance schema")
    require(value.get("requestSha256") == digest(request_path), "review provenance request digest differs")
    require(value.get("decisionSha256") == digest(decision_path), "review provenance decision digest differs")
    require(value.get("reviewer") == decision.get("reviewer"), "review provenance reviewer differs")
    require(value.get("repository") == repository, "review provenance repository differs")
    require(value.get("workflowPath") == workflow_path, "review provenance workflow differs")
    require(value.get("workflowEvent") == "workflow_dispatch", "review provenance event differs")
    require(value.get("workflowHeadBranch") == "main", "review provenance branch differs")
    require(value.get("workflowHeadSha") == expected_head_sha, "review provenance revision differs")
    require(value.get("actorAuthenticatedByGitHub") is True, "review actor was not authenticated")
    require(value.get("attestationVerified") is True, "review decision attestation was not verified")
    require(value.get("attestationPredicateType") == SLSA_PROVENANCE, "review attestation predicate differs")
    require(isinstance(value.get("workflowRunId"), int) and value["workflowRunId"] > 0, "review provenance run id is invalid")
    require(isinstance(value.get("workflowRunAttempt"), int) and value["workflowRunAttempt"] > 0, "review provenance run attempt is invalid")
    require(isinstance(value.get("attestationVerificationSha256"), str) and SHA256.fullmatch(value["attestationVerificationSha256"]), "review attestation verification digest is invalid")
    require(isinstance(value.get("matchedAttestationSha256"), str) and SHA256.fullmatch(value["matchedAttestationSha256"]), "matched attestation digest is invalid")
    require(value.get("verificationPolicy") == {
        "repository": repository,
        "signerWorkflow": f"{repository}/{workflow_path}",
        "sourceRef": "refs/heads/main",
        "sourceDigest": expected_head_sha,
        "denySelfHostedRunners": True,
    }, "review provenance verification policy differs")
    require(value.get("automaticPromotion") is False, "review provenance cannot auto-promote")
    return value


def build_authenticated_adjudication(
    *,
    cut_root: Path,
    request_path: Path,
    review_paths: list[Path],
    provenance_paths: list[Path],
    repository: str,
    workflow_path: str,
    expected_head_sha: str,
) -> dict[str, Any]:
    require(len(review_paths) == len(provenance_paths), "every review requires one provenance receipt")
    module = review_module()
    with tempfile.TemporaryDirectory(prefix="agentlab-blind-review-") as raw:
        base_path = Path(raw) / "base-adjudication.json"
        base = module.adjudicate(request_path, review_paths, cut_root, base_path)
        provenances = [
            validate_provenance(
                provenance_paths[index],
                request_path,
                review,
                repository,
                workflow_path,
                expected_head_sha,
            )
            for index, review in enumerate(review_paths)
        ]
        run_ids = [value["workflowRunId"] for value in provenances]
        reviewers = [value["reviewer"] for value in provenances]
        require(len(run_ids) == len(set(run_ids)), "authenticated reviews must come from distinct workflow runs")
        require(len(reviewers) == len(set(reviewers)), "authenticated reviewers must be unique")
        return {
            **{
                key: value
                for key, value in base.items()
                if key not in {
                    "schema",
                    "reviewerIdentityAuthenticationQualified",
                    "blindPilotReviewQualified",
                    "nextGate",
                }
            },
            "schema": ADJUDICATION_SCHEMA,
            "baseAdjudicationSha256": digest(base_path),
            "reviewProvenance": sorted(
                [
                    {
                        "reviewer": value["reviewer"],
                        "workflowRunId": value["workflowRunId"],
                        "provenanceSha256": digest(provenance_paths[index]),
                    }
                    for index, value in enumerate(provenances)
                ],
                key=lambda row: row["reviewer"],
            ),
            "reviewerIdentityAuthenticationQualified": True,
            "attestedWorkflowProvenanceQualified": True,
            "blindPilotReviewQualified": base["reviewConsensusQualified"],
            "nextGate": "bind-authenticated-adjudication-to-assessment-runtime",
            "automaticPromotion": False,
        }


def authenticated_adjudicate(
    *,
    cut_root: Path,
    request_path: Path,
    review_paths: list[Path],
    provenance_paths: list[Path],
    repository: str,
    workflow_path: str,
    expected_head_sha: str,
    output: Path,
) -> dict[str, Any]:
    value = build_authenticated_adjudication(
        cut_root=cut_root,
        request_path=request_path,
        review_paths=review_paths,
        provenance_paths=provenance_paths,
        repository=repository,
        workflow_path=workflow_path,
        expected_head_sha=expected_head_sha,
    )
    write_json(output, value)
    return value


def validate_authenticated_adjudication(
    *,
    path: Path,
    cut_root: Path,
    request_path: Path,
    review_paths: list[Path],
    provenance_paths: list[Path],
    repository: str,
    workflow_path: str,
    expected_head_sha: str,
) -> dict[str, Any]:
    actual = load(path, "authenticated blind review adjudication")
    expected = build_authenticated_adjudication(
        cut_root=cut_root,
        request_path=request_path,
        review_paths=review_paths,
        provenance_paths=provenance_paths,
        repository=repository,
        workflow_path=workflow_path,
        expected_head_sha=expected_head_sha,
    )
    require(actual == expected, "authenticated blind review adjudication differs")
    return actual


def validate_authenticated_bundle(
    bundle_root: Path,
    repository: str,
    expected_head_sha: str,
) -> dict[str, Any]:
    bundle_root = bundle_root.resolve(strict=True)
    return validate_authenticated_adjudication(
        path=bundle_root / "authenticated-adjudication.json",
        cut_root=bundle_root / "source/blind-cut",
        request_path=bundle_root / "request.json",
        review_paths=[
            bundle_root / "first/artifact/decision.json",
            bundle_root / "second/artifact/decision.json",
        ],
        provenance_paths=[
            bundle_root / "first/provenance.json",
            bundle_root / "second/provenance.json",
        ],
        repository=repository,
        workflow_path=REVIEW_WORKFLOW_PATH,
        expected_head_sha=expected_head_sha,
    )


def verified_command(arguments: list[str]) -> Any:
    environment = dict(os.environ)
    require(environment.get("GH_TOKEN"), "GH_TOKEN is required for online attestation verification")
    completed = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    require(
        completed.returncode == 0,
        f"GitHub verification command failed: {' '.join(arguments[:3])}: {completed.stderr.strip()}",
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AuthenticationError("GitHub verification command returned invalid JSON") from error


def verify_authenticated_bundle_online(
    bundle_root: Path,
    repository: str,
    adjudication_run_id: int,
    verification_output: Path | None = None,
) -> dict[str, Any]:
    require(REPOSITORY.fullmatch(repository) is not None, "expected repository is invalid")
    require(isinstance(adjudication_run_id, int) and adjudication_run_id > 0, "adjudication run id is invalid")
    run = verified_command(
        ["gh", "api", f"repos/{repository}/actions/runs/{adjudication_run_id}"]
    )
    require(isinstance(run, dict), "adjudication workflow run metadata must be an object")
    require((run.get("repository") or {}).get("full_name") == repository, "adjudication repository differs")
    require(run.get("path") == ADJUDICATION_WORKFLOW_PATH, "adjudication workflow path differs")
    require(run.get("event") == "workflow_dispatch", "adjudication was not manually dispatched")
    require(run.get("head_branch") == "main", "adjudication did not run on main")
    head_sha = run.get("head_sha")
    require(isinstance(head_sha, str) and REVISION.fullmatch(head_sha), "adjudication revision is invalid")
    require(run.get("status") == "completed" and run.get("conclusion") == "success", "adjudication workflow did not succeed")
    run_attempt = run.get("run_attempt")
    require(isinstance(run_attempt, int) and run_attempt > 0, "adjudication run attempt is invalid")
    bundle_root = bundle_root.resolve(strict=True)
    adjudication_path = bundle_root / "authenticated-adjudication.json"
    verification = verified_command(
        [
            "gh",
            "attestation",
            "verify",
            str(adjudication_path),
            "--repo",
            repository,
            "--signer-workflow",
            f"{repository}/{ADJUDICATION_WORKFLOW_PATH}",
            "--source-ref",
            "refs/heads/main",
            "--source-digest",
            head_sha,
            "--deny-self-hosted-runners",
            "--format",
            "json",
        ]
    )
    attestation_match(
        verification,
        digest(adjudication_path),
        adjudication_run_id,
        run_attempt,
    )
    if verification_output is not None:
        write_json(
            verification_output,
            {
                "schema": ONLINE_VERIFICATION_SCHEMA,
                "repository": repository,
                "workflowPath": ADJUDICATION_WORKFLOW_PATH,
                "workflowRunId": adjudication_run_id,
                "workflowRunAttempt": run_attempt,
                "workflowHeadSha": head_sha,
                "policy": {
                    "repository": repository,
                    "signerWorkflow": f"{repository}/{ADJUDICATION_WORKFLOW_PATH}",
                    "sourceRef": "refs/heads/main",
                    "sourceDigest": head_sha,
                    "denySelfHostedRunners": True,
                },
                "subjectPath": adjudication_path.name,
                "subjectSha256": digest(adjudication_path),
                "verification": verification,
            },
        )
    value = validate_authenticated_bundle(bundle_root, repository, head_sha)
    require(value.get("reviewerIdentityAuthenticationQualified") is True, "authenticated reviewer identity is not qualified")
    require(value.get("attestedWorkflowProvenanceQualified") is True, "attested review provenance is not qualified")
    return value


def common_adjudication_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cut", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--review", type=Path, action="append", required=True)
    parser.add_argument("--provenance", type=Path, action="append", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--expected-head-sha", required=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    auth = sub.add_parser("authenticate")
    auth.add_argument("--request", type=Path, required=True)
    auth.add_argument("--decision", type=Path, required=True)
    auth.add_argument("--run-metadata", type=Path, required=True)
    auth.add_argument("--attestation-verification", type=Path, required=True)
    auth.add_argument("--repository", required=True)
    auth.add_argument("--workflow-path", required=True)
    auth.add_argument("--expected-head-sha", required=True)
    auth.add_argument("--output", type=Path, required=True)
    adjudicate_parser = sub.add_parser("adjudicate")
    common_adjudication_arguments(adjudicate_parser)
    adjudicate_parser.add_argument("--output", type=Path, required=True)
    validate_parser = sub.add_parser("validate")
    common_adjudication_arguments(validate_parser)
    validate_parser.add_argument("--adjudication", type=Path, required=True)
    online = sub.add_parser("verify-online")
    online.add_argument("--bundle", type=Path, required=True)
    online.add_argument("--repository", required=True)
    online.add_argument("--run-id", type=int, required=True)
    online.add_argument("--verification-output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "authenticate":
            value = authenticate(
                request_path=args.request,
                decision_path=args.decision,
                run_metadata_path=args.run_metadata,
                attestation_verification_path=args.attestation_verification,
                repository=args.repository,
                workflow_path=args.workflow_path,
                expected_head_sha=args.expected_head_sha,
                output=args.output,
            )
        elif args.command == "adjudicate":
            value = authenticated_adjudicate(
                cut_root=args.cut,
                request_path=args.request,
                review_paths=args.review,
                provenance_paths=args.provenance,
                repository=args.repository,
                workflow_path=args.workflow_path,
                expected_head_sha=args.expected_head_sha,
                output=args.output,
            )
        elif args.command == "validate":
            value = validate_authenticated_adjudication(
                path=args.adjudication,
                cut_root=args.cut,
                request_path=args.request,
                review_paths=args.review,
                provenance_paths=args.provenance,
                repository=args.repository,
                workflow_path=args.workflow_path,
                expected_head_sha=args.expected_head_sha,
            )
        else:
            value = verify_authenticated_bundle_online(
                args.bundle,
                args.repository,
                args.run_id,
                args.verification_output,
            )
    except (AuthenticationError, OSError, ValueError) as error:
        print(f"authenticated blind case review invalid: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "schema": value["schema"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
