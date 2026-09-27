#!/usr/bin/env python3
"""Freeze ordered participant profiles before an assessed campaign starts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


SCHEMA = "agentlab.participant_experiment_plan.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
TOKEN = re.compile(r"[A-Za-z0-9_.:@/+\-]{1,200}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")


class ExperimentPlanError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ExperimentPlanError(message)


def digest(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), f"evidence must be a regular file: {path.name}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def normalize_profiles(value: Any) -> list[dict[str, Any]]:
    require(isinstance(value, list) and 3 <= len(value) <= 8, "participant profiles must contain three to eight ordered tiers")
    participants: set[str] = set()
    models: set[str] = set()
    profiles = []
    for ordinal, row in enumerate(value):
        require(isinstance(row, dict) and set(row) == {"participantId", "model"}, "participant profile fields differ")
        participant = row.get("participantId")
        model = row.get("model")
        require(isinstance(participant, str) and TOKEN.fullmatch(participant), "participant identity is invalid")
        require(isinstance(model, str) and TOKEN.fullmatch(model), "model profile is invalid")
        require(participant not in participants, "participant identity is duplicated")
        require(model not in models, "model profile is duplicated")
        participants.add(participant)
        models.add(model)
        profiles.append({
            "ordinal": ordinal,
            "participantId": participant,
            "model": model,
        })
    return profiles


def build_execution_protocol(
    participant_adapter: Path,
    participant_driver: Path,
    participant_package_lock: Path,
    runtime_config_path: Path,
) -> dict[str, Any]:
    repository_root = Path(__file__).resolve().parents[1]
    try:
        adapter_path = participant_adapter.resolve(strict=True).relative_to(repository_root).as_posix()
        driver_path = participant_driver.resolve(strict=True).relative_to(repository_root).as_posix()
        participant_package_lock.resolve(strict=True).relative_to(repository_root)
    except ValueError as error:
        raise ExperimentPlanError("participant implementation inputs must be repository-owned") from error
    package_lock = load(participant_package_lock, "participant package lock")
    runtime = load(runtime_config_path, "participant runtime config")
    package = (package_lock.get("packages") or {}).get(
        "node_modules/@mariozechner/pi-coding-agent"
    )
    require(isinstance(package, dict), "Pi package is absent from participant lock")
    version = package.get("version")
    require(isinstance(version, str) and TOKEN.fullmatch(version), "Pi package version is invalid")
    require(runtime.get("schema") == "agentlab.participant_docker_runtime.v1", "participant runtime schema differs")
    require(runtime.get("executor") == "docker", "participant runtime executor differs")
    require(isinstance(runtime.get("imageId"), str) and IMAGE_ID.fullmatch(runtime["imageId"]), "participant runtime image ID is invalid")
    lock_digest = digest(participant_package_lock)
    require(runtime.get("piPackageLockSha256") == lock_digest, "participant runtime lock binding differs")
    manifest_digest = runtime.get("participantManifestSha256")
    require(isinstance(manifest_digest, str) and SHA256.fullmatch(manifest_digest), "participant manifest binding is invalid")
    return {
        "schema": "agentlab.participant_execution_protocol.v1",
        "agentImplementation": "pi",
        "agentPackage": "@mariozechner/pi-coding-agent",
        "agentPackageVersion": version,
        "participantAdapter": {
            "path": adapter_path,
            "sha256": digest(participant_adapter),
        },
        "participantDriver": {
            "path": driver_path,
            "sha256": digest(participant_driver),
        },
        "participantPackageLockSha256": lock_digest,
        "participantRuntimeConfigSha256": digest(runtime_config_path),
        "runtimeImageId": runtime["imageId"],
        "participantManifestSha256": manifest_digest,
        "promptAuthority": "digest-bound-adapter-driver-and-blind-case-manifest",
        "sessionPolicy": "fresh-per-attempt-persistent-across-case-stages",
        "thinkingMode": "off",
        "reasoningEffort": None,
        "extensionPolicy": "disabled",
        "skillsPolicy": "disabled",
        "contextFilePolicy": "disabled",
        "turnTimeoutSeconds": 420,
        "samplingPolicy": "provider-default-stochastic-repeated-trials",
        "withinCampaignExecutionProtocolQualified": True,
        "crossCampaignProviderReproducibilityQualified": False,
    }


def validate_execution_protocol(value: Any) -> dict[str, Any]:
    require(isinstance(value, dict), "participant execution protocol must be an object")
    require(set(value) == {
        "schema", "agentImplementation", "agentPackage", "agentPackageVersion",
        "participantAdapter", "participantDriver", "participantPackageLockSha256",
        "participantRuntimeConfigSha256", "runtimeImageId", "participantManifestSha256",
        "promptAuthority", "sessionPolicy", "thinkingMode", "reasoningEffort",
        "extensionPolicy", "skillsPolicy", "contextFilePolicy", "turnTimeoutSeconds",
        "samplingPolicy", "withinCampaignExecutionProtocolQualified",
        "crossCampaignProviderReproducibilityQualified",
    }, "participant execution protocol fields differ")
    require(value.get("schema") == "agentlab.participant_execution_protocol.v1", "participant execution protocol schema differs")
    require(value.get("agentImplementation") == "pi", "participant implementation differs")
    require(value.get("agentPackage") == "@mariozechner/pi-coding-agent", "participant package differs")
    require(isinstance(value.get("agentPackageVersion"), str) and TOKEN.fullmatch(value["agentPackageVersion"]), "participant package version is invalid")
    for label in ("participantAdapter", "participantDriver"):
        binding = value.get(label)
        require(isinstance(binding, dict) and set(binding) == {"path", "sha256"}, f"{label} binding differs")
        require(isinstance(binding.get("path"), str) and TOKEN.fullmatch(binding["path"]), f"{label} path is invalid")
        require(isinstance(binding.get("sha256"), str) and SHA256.fullmatch(binding["sha256"]), f"{label} digest is invalid")
    for label in ("participantPackageLockSha256", "participantRuntimeConfigSha256", "participantManifestSha256"):
        require(isinstance(value.get(label), str) and SHA256.fullmatch(value[label]), f"{label} is invalid")
    require(isinstance(value.get("runtimeImageId"), str) and IMAGE_ID.fullmatch(value["runtimeImageId"]), "runtime image ID is invalid")
    require(value.get("promptAuthority") == "digest-bound-adapter-driver-and-blind-case-manifest", "prompt authority differs")
    require(value.get("sessionPolicy") == "fresh-per-attempt-persistent-across-case-stages", "session policy differs")
    require(value.get("thinkingMode") == "off" and value.get("reasoningEffort") is None, "reasoning policy differs")
    require(all(value.get(field) == "disabled" for field in ("extensionPolicy", "skillsPolicy", "contextFilePolicy")), "participant extension policy differs")
    require(value.get("turnTimeoutSeconds") == 420, "participant turn timeout differs")
    require(value.get("samplingPolicy") == "provider-default-stochastic-repeated-trials", "sampling policy differs")
    require(value.get("withinCampaignExecutionProtocolQualified") is True, "within-campaign execution protocol is not qualified")
    require(value.get("crossCampaignProviderReproducibilityQualified") is False, "provider reproducibility must remain unqualified")
    return value


def derive(
    case_path: Path,
    profiles: Any,
    provider_route: str,
    trials: int,
    method_revision: str,
    case_review_run_id: int,
    execution_protocol: dict[str, Any],
) -> dict[str, Any]:
    case = load(case_path, "evaluation case")
    case_id = case.get("id")
    source_set = case.get("sourceSetSha256")
    require(isinstance(case_id, str) and TOKEN.fullmatch(case_id), "evaluation case identity is invalid")
    require(isinstance(source_set, str) and SHA256.fullmatch(source_set), "evaluation case source set is invalid")
    require(isinstance(provider_route, str) and TOKEN.fullmatch(provider_route), "provider route is invalid")
    require(isinstance(trials, int) and not isinstance(trials, bool) and trials in {3, 5, 10, 20}, "trials per participant must be one of 3, 5, 10 or 20")
    require(isinstance(method_revision, str) and REVISION.fullmatch(method_revision), "method revision is invalid")
    require(isinstance(case_review_run_id, int) and not isinstance(case_review_run_id, bool) and case_review_run_id > 0, "case review run id is invalid")
    normalized = normalize_profiles(profiles)
    protocol = validate_execution_protocol(execution_protocol)
    return {
        "schema": SCHEMA,
        "status": "predeclared-before-attempts",
        "caseId": case_id,
        "sourceSetSha256": source_set,
        "evaluationCaseSha256": digest(case_path),
        "caseReviewRunId": case_review_run_id,
        "methodRevision": method_revision,
        "providerRoute": provider_route,
        "trialsPerParticipant": trials,
        "participantProfileCount": len(normalized),
        "participantProfiles": normalized,
        "executionProtocol": protocol,
        "automaticPromotion": False,
    }


def validate_plan(path: Path) -> dict[str, Any]:
    value = load(path, "participant experiment plan")
    require(value.get("schema") == SCHEMA, "participant experiment plan schema differs")
    require(value.get("status") == "predeclared-before-attempts", "participant experiment plan status differs")
    require(value.get("automaticPromotion") is False, "participant experiment plan can auto-promote")
    require(isinstance(value.get("caseId"), str) and TOKEN.fullmatch(value["caseId"]), "plan case identity is invalid")
    require(isinstance(value.get("sourceSetSha256"), str) and SHA256.fullmatch(value["sourceSetSha256"]), "plan source set is invalid")
    require(isinstance(value.get("evaluationCaseSha256"), str) and SHA256.fullmatch(value["evaluationCaseSha256"]), "plan evaluation case digest is invalid")
    require(isinstance(value.get("caseReviewRunId"), int) and value["caseReviewRunId"] > 0, "plan case review run id is invalid")
    require(isinstance(value.get("methodRevision"), str) and REVISION.fullmatch(value["methodRevision"]), "plan method revision is invalid")
    require(isinstance(value.get("providerRoute"), str) and TOKEN.fullmatch(value["providerRoute"]), "plan provider route is invalid")
    trials = value.get("trialsPerParticipant")
    require(isinstance(trials, int) and not isinstance(trials, bool) and trials in {3, 5, 10, 20}, "plan trials per participant are invalid")
    raw_profiles = value.get("participantProfiles")
    require(isinstance(raw_profiles, list), "plan participant profiles are absent")
    profiles = normalize_profiles([
        {"participantId": row.get("participantId"), "model": row.get("model")}
        if isinstance(row, dict) else row
        for row in raw_profiles
    ])
    require(raw_profiles == profiles, "plan participant profile order or ordinals differ")
    require(value.get("participantProfileCount") == len(profiles), "plan participant profile count differs")
    validate_execution_protocol(value.get("executionProtocol"))
    require(set(value) == {
        "schema", "status", "caseId", "sourceSetSha256", "evaluationCaseSha256",
        "caseReviewRunId", "methodRevision", "providerRoute", "trialsPerParticipant",
        "participantProfileCount", "participantProfiles", "executionProtocol", "automaticPromotion",
    }, "participant experiment plan fields differ")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--case", type=Path, required=True)
    create.add_argument("--profiles-json", required=True)
    create.add_argument("--provider-route", required=True)
    create.add_argument("--trials", type=int, required=True)
    create.add_argument("--method-revision", required=True)
    create.add_argument("--case-review-run-id", type=int, required=True)
    create.add_argument("--participant-adapter", type=Path, required=True)
    create.add_argument("--participant-driver", type=Path, required=True)
    create.add_argument("--participant-package-lock", type=Path, required=True)
    create.add_argument("--runtime-config", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--plan", type=Path, required=True)
    validate.add_argument("--case", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "create":
            require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
            value = derive(
                args.case,
                json.loads(args.profiles_json),
                args.provider_route,
                args.trials,
                args.method_revision,
                args.case_review_run_id,
                build_execution_protocol(
                    args.participant_adapter,
                    args.participant_driver,
                    args.participant_package_lock,
                    args.runtime_config,
                ),
            )
            args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            plan_path = args.output
        else:
            value = validate_plan(args.plan)
            if args.case is not None:
                require(value["caseId"] == load(args.case, "evaluation case").get("id"), "plan case identity differs")
                require(value["sourceSetSha256"] == load(args.case, "evaluation case").get("sourceSetSha256"), "plan source set differs")
                require(value["evaluationCaseSha256"] == digest(args.case), "plan evaluation case digest differs")
            plan_path = args.plan
        print(json.dumps({
            "ok": True,
            "planSha256": digest(plan_path),
            "participantProfileCount": value["participantProfileCount"],
            "trialsPerParticipant": value["trialsPerParticipant"],
        }, sort_keys=True))
    except (ExperimentPlanError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"participant experiment plan invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
