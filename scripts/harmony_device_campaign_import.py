#!/usr/bin/env python3
"""Package and independently verify completed Harmony device campaigns."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from typing import Any
import zipfile


BUNDLE_SCHEMA = "agentlab.harmony_device_campaign_bundle.v1"
VERIFICATION_SCHEMA = "agentlab.harmony_device_campaign_import_verification.v1"
HANDOFF_SCHEMA_V1 = "agentlab.harmony_assessed_campaign_handoff.v1"
HANDOFF_SCHEMA = "agentlab.harmony_assessed_campaign_handoff.v2"
HOST_PROFILE_SCHEMA = "agentlab.harmony_assessed_host_profile.v1"
PLAN_SCHEMA = "agentlab.harmony_assessed_campaign_plan.v1"
SUMMARY_SCHEMA = "agentlab.harmony_assessed_campaign_summary.v1"
STATE_SCHEMA = "agentlab.harmony_assessed_campaign_state.v1"
STATIC_WORKFLOW = ".github/workflows/multi-repo-assessed-campaign.yml"
SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")
MAX_FILES = 100_000
MAX_BYTES = 2 * 1024 * 1024 * 1024


class ImportError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ImportError(message)


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ImportError(f"cannot load {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def safe_relative(value: Any, label: str) -> PurePosixPath:
    require(isinstance(value, str) and value, f"{label} path is required")
    path = PurePosixPath(value)
    require(
        not path.is_absolute()
        and ".." not in path.parts
        and path.as_posix() not in {"", "."},
        f"{label} path is unsafe",
    )
    return path


def source_run_identity(value: dict[str, Any]) -> dict[str, Any]:
    run_id = value.get("id")
    run_attempt = value.get("run_attempt")
    head_sha = value.get("head_sha")
    repository = value.get("repository") or {}
    require(isinstance(run_id, int) and run_id > 0, "source run id is invalid")
    require(isinstance(run_attempt, int) and run_attempt > 0, "source run attempt is invalid")
    require(isinstance(head_sha, str) and REVISION.fullmatch(head_sha), "source run head SHA is invalid")
    require(value.get("path") == STATIC_WORKFLOW, "source run workflow differs")
    require(value.get("event") == "workflow_dispatch", "source run event differs")
    require(value.get("head_branch") == "main", "source run must use main")
    require(value.get("status") == "completed" and value.get("conclusion") == "success", "source run did not succeed")
    repository_name = repository.get("full_name")
    require(isinstance(repository_name, str) and repository_name, "source run repository is absent")
    return {
        "runId": run_id,
        "runAttempt": run_attempt,
        "workflowHeadSha": head_sha,
        "workflowPath": STATIC_WORKFLOW,
        "repository": repository_name,
    }


def regular_tree(root: Path) -> list[tuple[Path, str, int]]:
    require(root.is_dir() and not root.is_symlink(), f"tree root is invalid: {root}")
    rows: list[tuple[Path, str, int]] = []
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), f"tree contains symlink: {path}")
        if path.is_dir():
            continue
        require(path.is_file(), f"tree contains unsupported entry: {path}")
        rows.append((path, path.relative_to(root).as_posix(), stat.S_IMODE(path.stat().st_mode)))
    require(rows, f"tree has no files: {root}")
    return rows


def archive_row(path: Path, name: str, mode: int) -> dict[str, Any]:
    return {
        "path": name,
        "sha256": sha256(path),
        "byteLength": path.stat().st_size,
        "unixMode": mode,
    }


def add_file(archive: zipfile.ZipFile, source: Path, name: str, mode: int) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = ((stat.S_IFREG | mode) & 0xFFFF) << 16
    with source.open("rb") as stream:
        archive.writestr(info, stream.read())


def binding(path: str, source: Path) -> dict[str, Any]:
    return {"path": path, "sha256": sha256(source), "byteLength": source.stat().st_size}


def verify_handoff_identity(
    handoff: dict[str, Any], plan: dict[str, Any], source_run: dict[str, Any]
) -> None:
    require(
        handoff.get("schema") in {HANDOFF_SCHEMA_V1, HANDOFF_SCHEMA},
        "unsupported handoff schema",
    )
    require(plan.get("schema") == PLAN_SCHEMA, "unsupported campaign plan schema")
    require(handoff.get("automaticPromotion") is False and plan.get("automaticPromotion") is False, "campaign inputs cannot auto-promote")
    for field in ("campaignId", "methodRevision"):
        require(plan.get(field) == handoff.get(field), f"plan {field} differs from handoff")
    require(
        plan.get("calibrationAuthoring") == handoff.get("calibrationAuthoring"),
        "plan calibration authoring differs from handoff",
    )
    require(
        handoff.get("methodRevision") == source_run["workflowHeadSha"],
        "handoff method revision differs from source workflow run",
    )
    case_binding = handoff.get("evaluationCase") or {}
    calibration_binding = handoff.get("calibration") or {}
    require((plan.get("evaluationCase") or {}).get("sha256") == case_binding.get("sha256"), "plan evaluation case differs from handoff")
    require((plan.get("calibration") or {}).get("sha256") == calibration_binding.get("sha256"), "plan calibration differs from handoff")
    if handoff.get("schema") == HANDOFF_SCHEMA:
        require(
            (plan.get("participantExperimentPlan") or {}).get("sha256")
            == (handoff.get("participantExperimentPlan") or {}).get("sha256"),
            "plan participant experiment differs from handoff",
        )
    handoff_attempts = handoff.get("attempts")
    plan_attempts = plan.get("attempts")
    require(isinstance(handoff_attempts, list) and isinstance(plan_attempts, list), "campaign attempts are absent")
    require(len(handoff_attempts) == len(plan_attempts) and len(plan_attempts) >= 2, "campaign attempt count differs")
    expected_run_id = source_run["runId"]
    handoff_index = {row.get("attemptId"): row for row in handoff_attempts if isinstance(row, dict)}
    require(len(handoff_index) == len(handoff_attempts), "handoff attempts are invalid or duplicated")
    for row in plan_attempts:
        require(isinstance(row, dict), "plan attempt is invalid")
        attempt_id = row.get("attemptId")
        expected = handoff_index.get(attempt_id)
        require(isinstance(expected, dict), f"plan attempt is absent from handoff: {attempt_id}")
        require(row.get("participantId") == expected.get("participantId"), f"{attempt_id} participant differs")
        require(str(expected.get("producerRun")) == str(expected_run_id), f"{attempt_id} source run differs")
        assessment = expected.get("assessment") or {}
        plan_assessment = row.get("assessment") or {}
        for plan_field, handoff_field in (
            ("summarySha256", "summary"),
            ("decisionPackageSha256", "decisionPackage"),
            ("finalSourceStateSha256", "finalSourceState"),
        ):
            require(
                plan_assessment.get(plan_field) == (assessment.get(handoff_field) or {}).get("sha256"),
                f"{attempt_id} {plan_field} differs from handoff",
            )


def verify_profile_plan(profile: dict[str, Any], plan: dict[str, Any]) -> None:
    require(profile.get("schema") == HOST_PROFILE_SCHEMA, "unsupported host profile schema")
    require(profile.get("automaticPromotion") is False, "host profile cannot auto-promote")
    require(plan.get("sourceMaterialization") == profile.get("sourceMaterialization"), "source materialization differs from host profile")
    require(plan.get("requiredTrials") == profile.get("requiredTrials", 3), "required trials differ from host profile")
    require(float(plan.get("eligibilityThreshold")) == float(profile.get("eligibilityThreshold", 0.6)), "eligibility threshold differs from host profile")
    profile_programs = profile.get("programs") or {}
    plan_programs = plan.get("programs") or {}
    require(set(profile_programs) == set(plan_programs), "controller program set differs from host profile")
    for name, expected in profile_programs.items():
        require((plan_programs.get(name) or {}).get("sha256") == (expected or {}).get("sha256"), f"{name} program digest differs from host profile")
    profile_build = profile.get("build") or {}
    plan_build = plan.get("build") or {}
    require(plan_build.get("executableSha256") == (profile_build.get("executable") or {}).get("sha256"), "build executable differs from host profile")
    for key, value in profile_build.items():
        if key != "executable":
            require(plan_build.get(key) == value, f"build field differs from host profile: {key}")
    profile_device = profile.get("device") or {}
    plan_device = plan.get("device") or {}
    require(plan_device.get("subjectOutcomePolicy") == "retain-assessed-failure", "device outcome policy differs")
    for key, value in profile_device.items():
        if key not in {"functionalOracle", "runtime", "performance"}:
            require(plan_device.get(key) == value, f"device field differs from host profile: {key}")
    functional = profile_device.get("functionalOracle") or {}
    require((plan_device.get("functionalOracle") or {}).get("sha256") == functional.get("sha256"), "functional Oracle differs from host profile")
    profile_runtime = profile_device.get("runtime") or {}
    plan_runtime = plan_device.get("runtime") or {}
    require(plan_runtime.get("runnerSha256") == (profile_runtime.get("runner") or {}).get("sha256"), "device runner differs from host profile")
    for key, value in profile_runtime.items():
        if key not in {"runner", "toolsRoot", "imageRoot", "instancePath"}:
            require(plan_runtime.get(key) == value, f"runtime field differs from host profile: {key}")
    performance = profile_device.get("performance") or {}
    plan_performance = plan_device.get("performance") or {}
    require(plan_performance.get("policySha256") == (performance.get("policy") or {}).get("sha256"), "performance policy differs from host profile")
    require(plan_performance.get("workloadSha256") == (performance.get("workload") or {}).get("sha256"), "performance workload differs from host profile")
    require(plan.get("executionPreflight") == profile.get("executionPreflight"), "execution preflight differs from host profile")


def validate_campaign(
    campaign: Path,
    static_root: Path,
    handoff: dict[str, Any],
    profile: dict[str, Any],
    plan_path: Path,
    plan: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    summary_path = campaign / "summary.json"
    state_path = campaign / "campaign-state.json"
    manifest_path = campaign / "attempts-manifest.json"
    collected_path = campaign / "case-discrimination-input.json"
    report_path = campaign / "case-discrimination-report.json"
    feedback_path = campaign / "assessment-feedback-candidates.json"
    summary = load(summary_path, "campaign summary")
    state = load(state_path, "campaign state")
    attempt_manifest = load(manifest_path, "attempt manifest")
    original_collected = load(collected_path, "original discrimination input")
    original_report = load(report_path, "original discrimination report")
    original_feedback = load(feedback_path, "original assessment feedback")
    require(summary.get("schema") == SUMMARY_SCHEMA, "unsupported campaign summary schema")
    require(state.get("schema") == STATE_SCHEMA, "unsupported campaign state schema")
    require(summary.get("status") == state.get("status") == "assessed-review-required", "campaign is not terminal review-required evidence")
    require(summary.get("automaticPromotion") is False and state.get("automaticPromotion") is False, "campaign cannot auto-promote")
    require(summary.get("nextGate") == state.get("nextGate") == "maintainer-adjudication-and-new-analysis-cut", "campaign next gate differs")
    require(summary.get("planSha256") == state.get("planSha256") == sha256(plan_path), "campaign plan digest differs")
    for field in ("campaignId", "caseId", "sourceSetSha256"):
        expected = handoff.get(field)
        require(summary.get(field) == state.get(field) == expected, f"campaign {field} differs")
    require(summary.get("methodRevision") == handoff.get("methodRevision"), "campaign method revision differs")
    if handoff.get("schema") == HANDOFF_SCHEMA:
        experiment_sha256 = (handoff.get("participantExperimentPlan") or {}).get("sha256")
        require(
            summary.get("participantExperimentPlanSha256") == experiment_sha256,
            "campaign participant experiment plan differs",
        )
        experiment_plan = load(
            static_root
            / safe_relative(
                (handoff.get("participantExperimentPlan") or {}).get("path"),
                "participant experiment plan",
            ),
            "participant experiment plan",
        )
        require(
            summary.get("participantProfileCount")
            == experiment_plan.get("participantProfileCount")
            and summary.get("trialsPerParticipant")
            == experiment_plan.get("trialsPerParticipant"),
            "campaign participant experiment denominators differ",
        )
    require(attempt_manifest.get("schema") == "agentlab.case_attempt_collection.v2", "attempt manifest schema differs")
    require(attempt_manifest.get("sourceSetSha256") == handoff.get("sourceSetSha256"), "attempt manifest source set differs")
    require(attempt_manifest.get("methodRevision") == handoff.get("methodRevision"), "attempt manifest method revision differs")
    expected_run_id = str((handoff.get("attempts") or [{}])[0].get("producerRun"))
    manifest_cases = attempt_manifest.get("cases")
    require(isinstance(manifest_cases, list) and len(manifest_cases) == 1, "attempt manifest case set differs")
    manifest_attempts = manifest_cases[0].get("attempts")
    require(isinstance(manifest_attempts, list), "attempt manifest attempts are absent")
    require(
        all(str(row.get("producerRun")) == expected_run_id for row in manifest_attempts if isinstance(row, dict))
        and len(manifest_attempts) == len(handoff.get("attempts") or []),
        "attempt manifest source run differs",
    )
    attempts = state.get("attempts") or {}
    require(isinstance(attempts, dict) and len(attempts) == len(handoff.get("attempts") or []), "campaign attempt state differs")
    device_attempts = sum((row or {}).get("status") == "device-assessed" for row in attempts.values())
    require(summary.get("deviceAttemptCount") == device_attempts, "device attempt count differs")
    require(summary.get("attemptCount") == len(attempts), "attempt count differs")
    for field, path in (
        ("attemptManifestSha256", manifest_path),
        ("discriminationInputSha256", collected_path),
        ("discriminationReportSha256", report_path),
        ("assessmentFeedbackSha256", feedback_path),
    ):
        require(summary.get(field) == sha256(path), f"campaign {field} differs")

    collect = trusted_module("collect-case-attempts.py", "agentlab_import_collect")
    score = trusted_module("score-case-discrimination.py", "agentlab_import_score")
    feedback = trusted_module("derive-assessment-feedback.py", "agentlab_import_feedback")
    recomputed_collected = collect.build_input(attempt_manifest, manifest_path.parent)
    required_trials = plan.get("requiredTrials", 3)
    threshold = float(plan.get("eligibilityThreshold", 0.6))
    recomputed_report = score.build_report(recomputed_collected, required_trials, threshold)
    static_root = static_root.resolve()
    case_binding = handoff.get("evaluationCase") or {}
    case_path = static_root / safe_relative(case_binding.get("path"), "evaluation case")
    require(sha256(case_path) == case_binding.get("sha256"), "evaluation case differs from handoff")
    evaluation_case = load(case_path, "evaluation case")
    recomputed_feedback = feedback.build_feedback(
        evaluation_case, recomputed_collected, recomputed_report, campaign
    )
    # Reports from an older method remain evidence, but the imported report is
    # always the trusted current-method reconstruction.
    return recomputed_collected, recomputed_report, {
        "value": recomputed_feedback,
        "originalInputMatched": canonical_sha256(original_collected)
        == canonical_sha256(recomputed_collected),
        "originalReportMatched": canonical_sha256(original_report) == canonical_sha256(recomputed_report),
        "originalFeedbackMatched": canonical_sha256(original_feedback) == canonical_sha256(recomputed_feedback),
    }


def trusted_module(filename: str, name: str):
    path = Path(__file__).resolve().with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"trusted module unavailable: {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_bundle(
    campaign: Path,
    handoff_path: Path,
    host_profile_path: Path,
    plan_path: Path,
    source_run_path: Path,
    output: Path,
) -> dict[str, Any]:
    require(not output.exists(), f"refusing to overwrite {output}")
    handoff = load(handoff_path, "campaign handoff")
    profile = load(host_profile_path, "host profile")
    plan = load(plan_path, "campaign plan")
    source_run = source_run_identity(load(source_run_path, "source workflow run"))
    handoff_module = trusted_module(
        "harmony_assessed_handoff.py", "agentlab_prepare_handoff"
    )
    try:
        handoff_module.verify_handoff(handoff_path)
    except handoff_module.HandoffError as error:
        raise ImportError(f"campaign handoff validation failed: {error}") from error
    verify_handoff_identity(handoff, plan, source_run)
    verify_profile_plan(profile, plan)
    validate_campaign(
        campaign.resolve(),
        handoff_path.resolve().parent,
        handoff,
        profile,
        plan_path.resolve(),
        plan,
    )
    members: list[tuple[Path, str, int]] = [
        (host_profile_path.resolve(), "host/host-profile.json", stat.S_IMODE(host_profile_path.stat().st_mode)),
        (plan_path.resolve(), "resolved/campaign-plan.json", stat.S_IMODE(plan_path.stat().st_mode)),
    ]
    members.extend(
        (path, f"campaign/{relative}", mode)
        for path, relative, mode in regular_tree(campaign.resolve())
    )
    rows = [archive_row(path, name, mode) for path, name, mode in members]
    summary = load(campaign / "summary.json", "campaign summary")
    calibration_authoring = handoff.get("calibrationAuthoring")
    require(
        summary.get("calibrationAuthoring") == calibration_authoring,
        "campaign summary calibration authoring differs from handoff",
    )
    manifest = {
        "schema": BUNDLE_SCHEMA,
        "campaignId": summary["campaignId"],
        "caseId": summary["caseId"],
        "sourceSetSha256": summary["sourceSetSha256"],
        "sourceMethodRevision": summary["methodRevision"],
        "sourceAssessedCampaign": source_run,
        "sourceHandoffSha256": sha256(handoff_path),
        "hostProfile": binding("host/host-profile.json", host_profile_path),
        "campaignPlan": binding("resolved/campaign-plan.json", plan_path),
        "campaignSummary": binding("campaign/summary.json", campaign / "summary.json"),
        "files": rows,
        "fileCount": len(rows),
        "byteLength": sum(row["byteLength"] for row in rows),
        "automaticPromotion": False,
        "nextGate": "trusted-main-import-and-attestation",
    }
    if calibration_authoring is not None:
        manifest["calibrationAuthoring"] = calibration_authoring
    if handoff.get("schema") == HANDOFF_SCHEMA:
        manifest["participantExperimentPlanSha256"] = (
            handoff["participantExperimentPlan"]["sha256"]
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name, mode in members:
            add_file(archive, path, name, mode)
        info = zipfile.ZipInfo("bundle-manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = ((stat.S_IFREG | 0o644) & 0xFFFF) << 16
        archive.writestr(info, json_bytes(manifest))
    return manifest


def extract_bundle(archive_path: Path, output: Path) -> dict[str, Any]:
    require(archive_path.is_file() and not archive_path.is_symlink(), "bundle archive must be a regular file")
    require(not output.exists(), f"refusing to overwrite {output}")
    output.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            require(0 < len(infos) <= MAX_FILES + 1, "bundle member count is invalid")
            names: set[str] = set()
            total = 0
            for info in infos:
                relative = safe_relative(info.filename, "archive member")
                require(not info.is_dir(), "bundle must not contain directory entries")
                require(info.filename not in names, "bundle contains duplicate members")
                names.add(info.filename)
                mode_type = (info.external_attr >> 16) & 0o170000
                require(mode_type in {0, stat.S_IFREG}, "bundle contains a non-regular member")
                total += info.file_size
                require(total <= MAX_BYTES, "bundle expands beyond the byte limit")
                target = output.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("xb") as destination:
                    shutil.copyfileobj(source, destination)
                target.chmod((info.external_attr >> 16) & 0o777 or 0o644)
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise
    manifest = load(output / "bundle-manifest.json", "bundle manifest")
    require(manifest.get("schema") == BUNDLE_SCHEMA, "unsupported bundle schema")
    require(manifest.get("automaticPromotion") is False, "bundle cannot auto-promote")
    rows = manifest.get("files")
    require(isinstance(rows, list) and len(rows) == manifest.get("fileCount"), "bundle file index is invalid")
    expected_names = {"bundle-manifest.json"}
    byte_length = 0
    for row in rows:
        require(isinstance(row, dict), "bundle file row is invalid")
        relative = safe_relative(row.get("path"), "bundle file")
        require(relative.as_posix() not in expected_names, "bundle file index is duplicated")
        expected_names.add(relative.as_posix())
        path = output.joinpath(*relative.parts)
        require(path.is_file() and not path.is_symlink(), f"bundle file is absent: {relative}")
        require(path.stat().st_size == row.get("byteLength"), f"bundle file byte length differs: {relative}")
        require(sha256(path) == row.get("sha256"), f"bundle file digest differs: {relative}")
        require(stat.S_IMODE(path.stat().st_mode) == row.get("unixMode"), f"bundle file mode differs: {relative}")
        byte_length += path.stat().st_size
    actual_names = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file()
    }
    require(actual_names == expected_names, "bundle contains unindexed or missing files")
    require(byte_length == manifest.get("byteLength"), "bundle indexed byte length differs")
    return manifest


def verify_bundle(
    archive_path: Path,
    static_root: Path,
    source_run_path: Path,
    output: Path,
    verification_revision: str,
) -> dict[str, Any]:
    require(REVISION.fullmatch(verification_revision) is not None, "verification revision must be exact")
    archive_path = archive_path.resolve()
    static_root = static_root.resolve()
    source_run_path = source_run_path.resolve()
    output = output.resolve()
    manifest = extract_bundle(archive_path, output)
    source_run = source_run_identity(load(source_run_path, "source workflow run"))
    require(manifest.get("sourceAssessedCampaign") == source_run, "source workflow run differs from bundle")
    handoff_path = static_root / "harmony-device-handoff.json"
    handoff = load(handoff_path, "authoritative campaign handoff")
    require(sha256(handoff_path) == manifest.get("sourceHandoffSha256"), "authoritative handoff differs from bundle")
    if handoff.get("schema") == HANDOFF_SCHEMA:
        experiment_binding = handoff.get("participantExperimentPlan") or {}
        experiment_path = static_root / safe_relative(
            experiment_binding.get("path"), "participant experiment plan"
        )
        require(
            experiment_path.is_file() and not experiment_path.is_symlink(),
            "authoritative participant experiment plan is absent or unsafe",
        )
        require(
            sha256(experiment_path) == experiment_binding.get("sha256")
            == manifest.get("participantExperimentPlanSha256"),
            "authoritative participant experiment plan differs from bundle",
        )
    handoff_module = trusted_module(
        "harmony_assessed_handoff.py", "agentlab_import_handoff"
    )
    try:
        handoff_module.verify_handoff(handoff_path)
    except handoff_module.HandoffError as error:
        raise ImportError(f"authoritative handoff validation failed: {error}") from error
    profile_path = output / safe_relative((manifest.get("hostProfile") or {}).get("path"), "host profile")
    plan_path = output / safe_relative((manifest.get("campaignPlan") or {}).get("path"), "campaign plan")
    profile = load(profile_path, "imported host profile")
    plan = load(plan_path, "imported campaign plan")
    summary_path = output / "campaign/summary.json"
    summary = load(summary_path, "imported campaign summary")
    for label, binding_value, path in (
        ("host profile", manifest.get("hostProfile"), profile_path),
        ("campaign plan", manifest.get("campaignPlan"), plan_path),
        ("campaign summary", manifest.get("campaignSummary"), summary_path),
    ):
        require(isinstance(binding_value, dict), f"{label} binding is absent")
        require(binding_value.get("sha256") == sha256(path) and binding_value.get("byteLength") == path.stat().st_size, f"{label} binding differs")
    verify_handoff_identity(handoff, plan, source_run)
    calibration_authoring = handoff.get("calibrationAuthoring")
    require(
        manifest.get("calibrationAuthoring") == calibration_authoring,
        "bundle calibration authoring differs from authoritative handoff",
    )
    require(
        summary.get("calibrationAuthoring") == calibration_authoring,
        "campaign summary calibration authoring differs from authoritative handoff",
    )
    verify_profile_plan(profile, plan)
    collected, report, feedback = validate_campaign(
        output / "campaign", static_root, handoff, profile, plan_path, plan
    )
    result_root = output / "verified"
    result_root.mkdir()
    (result_root / "case-discrimination-input.json").write_bytes(json_bytes(collected))
    (result_root / "case-discrimination-report.json").write_bytes(json_bytes(report))
    (result_root / "assessment-feedback-candidates.json").write_bytes(json_bytes(feedback["value"]))
    ranking = report.get("ranking") or []
    require(len(ranking) == 1 and ranking[0].get("caseId") == manifest.get("caseId"), "imported report case differs")
    harmony = ((ranking[0].get("processMeasurement") or {}).get("harmonyDevice") or {})
    verification = {
        "schema": VERIFICATION_SCHEMA,
        "status": "verified-review-required",
        "bundleSha256": sha256(archive_path),
        "bundleManifestSha256": sha256(output / "bundle-manifest.json"),
        "sourceAssessedCampaign": source_run,
        "sourceHandoffSha256": sha256(handoff_path),
        "campaignId": manifest.get("campaignId"),
        "caseId": manifest.get("caseId"),
        "sourceSetSha256": manifest.get("sourceSetSha256"),
        "sourceMethodRevision": manifest.get("sourceMethodRevision"),
        "verificationMethodRevision": verification_revision,
        "trustedReconstruction": {
            "discriminationInputSha256": sha256(result_root / "case-discrimination-input.json"),
            "discriminationReportSha256": sha256(result_root / "case-discrimination-report.json"),
            "assessmentFeedbackSha256": sha256(result_root / "assessment-feedback-candidates.json"),
            "originalInputMatched": feedback["originalInputMatched"],
            "originalReportMatched": feedback["originalReportMatched"],
            "originalFeedbackMatched": feedback["originalFeedbackMatched"],
        },
        "harmonyEndToEndEvidenceQualified": harmony.get("endToEndEvidenceQualified") is True,
        "automaticPromotion": False,
        "nextGate": "suite-composition-or-maintainer-adjudication",
    }
    if calibration_authoring is not None:
        verification["calibrationAuthoring"] = calibration_authoring
    if handoff.get("schema") == HANDOFF_SCHEMA:
        verification["participantExperimentPlanSha256"] = (
            handoff["participantExperimentPlan"]["sha256"]
        )
    (result_root / "import-verification.json").write_bytes(json_bytes(verification))
    return verification
