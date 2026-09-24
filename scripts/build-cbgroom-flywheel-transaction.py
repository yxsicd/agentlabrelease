#!/usr/bin/env python3
"""Build one revision-fenced TableGit transaction from AgentLab run evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from pathlib import Path


REVISION = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")


def load(path: Path):
    return json.loads(path.read_text()) if path.is_file() else None


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_sha256(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def stable_uuid(*parts: str):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "agentlab://" + "/".join(parts)))


def phase_metrics(evidence: Path, summary: dict, phase: str):
    row = summary.get("phases", {}).get(phase, {})
    lifecycle = load(evidence / "parent-agent" / f"{phase}-lifecycle.json") or {}
    edit = load(evidence / f"{phase}-edit-timing.json") or {}
    scope = row.get("scope") or load(evidence / f"{phase}-scope.json") or {}
    return {
        "behaviorPass": bool((row.get("behavior") or {}).get("pass")),
        "buildPass": bool(row.get("build")),
        "scopeDrift": bool(scope.get("drift")),
        "timedOut": bool(lifecycle.get("timedOut")),
        "durationMs": lifecycle.get("durationMs") or row.get("repairLatencyMs"),
        "firstMutationMs": edit.get("firstSourceMutationMs"),
        "gatewayRequests": row.get("gatewayRequests"),
        "changedPaths": scope.get("changedPaths", []),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--github-repository", required=True)
    parser.add_argument("--caller-person-id", required=True)
    parser.add_argument("--repo", default="agentlabtablegit")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    evidence = args.evidence.resolve()
    summary = load(evidence / "summary.json") or {}
    decision = load(evidence / "decision-package.json") or {}
    difficulty = load(evidence / "difficulty-candidates.json") or {}
    multi_repo_case = load(evidence / "multi-repo-evaluation-case.json") or {}
    multi_repo_calibration = load(evidence / "multi-repo-calibration.json") or {}
    multi_repo_construction = load(evidence / "multi-repo-construction-receipt.json") or {}
    multi_repo_construction_quality = load(evidence / "multi-repo-construction-quality.json") or {}
    multi_repo_difficulty = difficulty.get("schema") == "agentlab.difficulty_candidates.v2"
    if multi_repo_difficulty:
        source_set_sha256 = difficulty.get("sourceSetSha256")
        sources = difficulty.get("sources")
        if not isinstance(source_set_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_set_sha256):
            raise SystemExit("multi-repository difficulty evidence requires sourceSetSha256")
        if difficulty.get("automaticPromotion") is not False:
            raise SystemExit("multi-repository difficulty evidence must not auto-promote")
        if not isinstance(sources, list) or len(sources) < 2:
            raise SystemExit("multi-repository difficulty evidence requires at least two sources")
        if not all(
            isinstance(source, dict)
            and isinstance(source.get("id"), str) and source["id"]
            and isinstance(source.get("repository"), str) and source["repository"]
            and isinstance(source.get("revision"), str) and REVISION.fullmatch(source["revision"])
            for source in sources
        ):
            raise SystemExit("invalid multi-repository difficulty source identity")
        source_set = {
            "schema": "agentlab.multi_repo_source_set.v1",
            "repositories": sources,
            "moduleBindings": difficulty.get("moduleBindings") or {},
        }
        calculated_source_set = hashlib.sha256(
            json.dumps(source_set, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if calculated_source_set != source_set_sha256:
            raise SystemExit("multi-repository difficulty sourceSetSha256 mismatch")
    groups = {name: [] for name in (
        "difficulty_points", "checkpoints", "interventions", "crossings",
        "decisions", "capability_profiles", "evidence_refs", "execution_environments",
        "evaluation_cases",
    )}

    def insert(path, row):
        groups[path].append({
            "op": "insert",
            "operation_id": stable_uuid(args.run_id, path, row["id"], "operation"),
            "key": row["id"],
            "row": row,
        })

    action_uri = f"https://github.com/{args.github_repository}/actions/runs/{args.run_id}"
    for filename, kind in (
        ("summary.json", "subject-summary"),
        ("decision-package.json", "harness-decision-package"),
        ("difficulty-candidates.json", "difficulty-candidates"),
        ("multi-repo-evaluation-case.json", "multi-repo-evaluation-case"),
        ("multi-repo-calibration.json", "multi-repo-calibration"),
        ("multi-repo-construction-receipt.json", "multi-repo-construction-receipt"),
        ("multi-repo-construction-quality.json", "multi-repo-construction-quality"),
        ("case-discrimination-report.json", "case-discrimination-report"),
        ("smartperf-baseline-summary.json", "smartperf-baseline-summary"),
        ("smartperf-candidate-summary.json", "smartperf-candidate-summary"),
        ("smartperf-comparison.json", "smartperf-comparison"),
        ("environment-fingerprint.json", "environment-fingerprint"),
    ):
        path = evidence / filename
        if path.is_file():
            evidence_row = {
                "id": f"evidence-{args.run_id}-{filename[:-5]}",
                "schema": "agentlab.evidence_ref.v1",
                "kind": kind,
                "uri": action_uri + "#" + filename,
                "sha256": sha256(path),
                "byteLength": path.stat().st_size,
                "sourceRevision": summary.get("sourceRevision"),
                "producerRun": args.run_id,
                "public": True,
                "metadata": {"scenario": decision.get("scenario"), "taskId": summary.get("taskId")},
            }
            if filename == "difficulty-candidates.json" and multi_repo_difficulty:
                evidence_row["sourceSetSha256"] = difficulty["sourceSetSha256"]
                evidence_row["sources"] = difficulty["sources"]
                evidence_row.pop("sourceRevision", None)
            if filename == "multi-repo-evaluation-case.json" and multi_repo_case:
                evidence_row["sourceSetSha256"] = multi_repo_case.get("sourceSetSha256")
                evidence_row["sources"] = multi_repo_case.get("sources")
                evidence_row.pop("sourceRevision", None)
            if filename == "multi-repo-calibration.json" and multi_repo_calibration:
                evidence_row["sourceSetSha256"] = multi_repo_calibration.get("sourceSetSha256")
                evidence_row["sources"] = multi_repo_case.get("sources") or difficulty.get("sources")
                evidence_row.pop("sourceRevision", None)
            if filename == "multi-repo-construction-receipt.json" and multi_repo_construction:
                evidence_row["sourceSetSha256"] = multi_repo_construction.get("sourceSetSha256")
                evidence_row["sources"] = multi_repo_case.get("sources") or difficulty.get("sources")
                evidence_row.pop("sourceRevision", None)
            if filename == "multi-repo-construction-quality.json" and multi_repo_construction_quality:
                evidence_row["sourceSetSha256"] = multi_repo_construction_quality.get("sourceSetSha256")
                evidence_row["sources"] = multi_repo_case.get("sources") or difficulty.get("sources")
                evidence_row.pop("sourceRevision", None)
            insert("evidence_refs", evidence_row)

    if multi_repo_case:
        if multi_repo_case.get("schema") != "agentlab.multi_repo_evaluation_case.v1":
            raise SystemExit("unsupported multi-repository evaluation case schema")
        case_id = multi_repo_case.get("id")
        case_source_set = multi_repo_case.get("sourceSetSha256")
        oracle = multi_repo_case.get("oracle") or {}
        calibration = multi_repo_case.get("calibration") or {}
        if not isinstance(case_id, str) or not case_id:
            raise SystemExit("multi-repository evaluation case requires id")
        if multi_repo_case.get("status") != "frozen-calibrated":
            raise SystemExit("multi-repository evaluation case is not frozen and calibrated")
        if multi_repo_case.get("automaticPromotion") is not False:
            raise SystemExit("multi-repository evaluation case must not claim automatic promotion")
        if not isinstance(case_source_set, str) or not re.fullmatch(r"[0-9a-f]{64}", case_source_set):
            raise SystemExit("multi-repository evaluation case requires sourceSetSha256")
        if multi_repo_difficulty and case_source_set != difficulty["sourceSetSha256"]:
            raise SystemExit("multi-repository evaluation case source set differs from difficulty evidence")
        if oracle.get("authority") != "independent-executable-oracle" or not re.fullmatch(r"[0-9a-f]{64}", str(oracle.get("sha256", ""))):
            raise SystemExit("multi-repository evaluation case requires an independent oracle")
        if calibration.get("qualified") is not True or not re.fullmatch(r"[0-9a-f]{64}", str(calibration.get("summarySha256", ""))):
            raise SystemExit("multi-repository evaluation case requires qualified calibration")
        calibration_path = evidence / "multi-repo-calibration.json"
        if multi_repo_calibration.get("schema") != "agentlab.multi_repo_calibration.v1":
            raise SystemExit("multi-repository evaluation case requires retained calibration evidence")
        if sha256(calibration_path) != calibration["summarySha256"]:
            raise SystemExit("multi-repository calibration evidence digest mismatch")
        if multi_repo_calibration.get("candidateId") != multi_repo_case.get("difficultyId"):
            raise SystemExit("multi-repository calibration candidate differs from frozen case")
        if multi_repo_calibration.get("sourceSetSha256") != case_source_set:
            raise SystemExit("multi-repository calibration source set differs from frozen case")
        if multi_repo_calibration.get("oracleSha256") != oracle["sha256"]:
            raise SystemExit("multi-repository calibration oracle differs from frozen case")
        construction = multi_repo_case.get("construction")
        construction_evidence_id = None
        if construction is not None:
            construction_path = evidence / "multi-repo-construction-receipt.json"
            if multi_repo_construction.get("schema") != "agentlab.multi_repo_intent_construction_receipt.v1":
                raise SystemExit("constructed multi-repository case requires retained construction evidence")
            if sha256(construction_path) != construction.get("receiptSha256"):
                raise SystemExit("multi-repository construction evidence digest mismatch")
            if multi_repo_construction.get("status") != construction.get("status") or construction.get("status") != "candidate-unverified":
                raise SystemExit("multi-repository construction status mismatch")
            if multi_repo_construction.get("participantId") != construction.get("participantId"):
                raise SystemExit("multi-repository construction participant differs from frozen case")
            if multi_repo_construction.get("candidateId") != multi_repo_case.get("difficultyId"):
                raise SystemExit("multi-repository construction candidate differs from frozen case")
            if multi_repo_construction.get("sourceSetSha256") != case_source_set:
                raise SystemExit("multi-repository construction source set differs from frozen case")
            if multi_repo_construction.get("semanticKnowledgeVerified") is not False or multi_repo_construction.get("automaticPromotion") is not False:
                raise SystemExit("multi-repository construction evidence overclaims qualification")
            construction_evidence_id = f"evidence-{args.run_id}-multi-repo-construction-receipt"
            construction_quality = multi_repo_case.get("constructionQuality") or {}
            quality_path = evidence / "multi-repo-construction-quality.json"
            if multi_repo_construction_quality.get("schema") != "agentlab.multi_repo_intent_quality.v1":
                raise SystemExit("constructed multi-repository case requires retained construction quality")
            if sha256(quality_path) != construction_quality.get("reportSha256"):
                raise SystemExit("multi-repository construction quality digest mismatch")
            if multi_repo_construction_quality.get("qualifiedForReview") is not True or construction_quality.get("qualifiedForReview") is not True:
                raise SystemExit("multi-repository construction did not qualify for review")
            if multi_repo_construction_quality.get("candidateId") != multi_repo_case.get("difficultyId") or multi_repo_construction_quality.get("sourceSetSha256") != case_source_set:
                raise SystemExit("multi-repository construction quality lineage mismatch")
            if multi_repo_construction_quality.get("constructionReceiptSha256") != construction.get("receiptSha256"):
                raise SystemExit("multi-repository construction quality receipt mismatch")
            if (multi_repo_construction_quality.get("policy") or {}).get("automaticPromotion") is not False:
                raise SystemExit("multi-repository construction quality must not auto-promote")
            construction_quality_evidence_id = f"evidence-{args.run_id}-multi-repo-construction-quality"
        else:
            construction_quality_evidence_id = None
        case_row = dict(multi_repo_case)
        case_row["evidenceIds"] = [
            f"evidence-{args.run_id}-multi-repo-evaluation-case",
            f"evidence-{args.run_id}-multi-repo-calibration",
        ]
        if construction_evidence_id:
            case_row["evidenceIds"].append(construction_evidence_id)
            case_row["evidenceIds"].append(construction_quality_evidence_id)
        insert("evaluation_cases", case_row)

    environment = load(evidence / "environment-fingerprint.json") or {}
    if environment:
        runner_name = environment.get("runnerName") or "unknown-runner"
        runner_os = environment.get("runnerOs") or "unknown-os"
        runner_arch = environment.get("runnerArch") or environment.get("machine") or "unknown-arch"
        runner_identity = "|".join([str(runner_name), str(runner_os), str(runner_arch), str(environment.get("machine") or "unknown-machine")])
        insert("execution_environments", {
            "id": f"environment-{args.run_id}",
            "runId": args.run_id,
            "runnerIdentity": runner_identity,
            "runnerName": runner_name,
            "runnerOs": runner_os,
            "runnerArch": runner_arch,
            "platform": environment.get("platform"),
            "machine": environment.get("machine"),
            "executionMode": environment.get("executionMode"),
            "fingerprintSha256": sha256(evidence / "environment-fingerprint.json"),
            "sourceRevision": summary.get("sourceRevision") or "unknown",
            "evidenceRef": f"evidence-{args.run_id}-environment-fingerprint",
            "metadata": {
                "schema": environment.get("schema"),
                "docker": environment.get("docker"),
                "node": environment.get("node"),
                "python": environment.get("python"),
                "git": environment.get("git"),
            },
        })

    checkpoint_ids = []
    for file in sorted((evidence / "difficulty-checkpoints").glob("*/checkpoint.json")):
        checkpoint = load(file) or {}
        native = checkpoint.get("nativeSession") or {}
        checkpoint_id = f"checkpoint-{args.run_id}-{file.parent.name}"
        checkpoint_ids.append(checkpoint_id)
        insert("checkpoints", {
            "id": checkpoint_id,
            "schema": "agentlab.difficulty_checkpoint.v1",
            "taskId": checkpoint.get("taskId") or summary.get("taskId"),
            "sourceRevision": checkpoint.get("sourceRevision") or summary.get("sourceRevision"),
            "sourceCut": checkpoint.get("sourceCut"),
            "checkpointDigest": sha256(file),
            "nativeAgent": native.get("agent"),
            "nativeVersion": native.get("packageVersion"),
            "nativeThreadId": native.get("threadId"),
            "nativeSessionSha256": native.get("sha256"),
            "formalSessionFsSnapshot": bool(checkpoint.get("formalSessionFsSnapshot")),
            "readyForControlledFork": bool(checkpoint.get("readyForControlledFork")),
            "admittedState": {
                "phase": checkpoint.get("phase"),
                "behaviorPass": checkpoint.get("behaviorPass"),
                "buildPass": checkpoint.get("buildPass"),
                "semanticRehydrationEligible": checkpoint.get("semanticRehydrationEligible"),
            },
        })

    intervention = None
    if summary.get("timeoutFeedbackOnly", {}).get("enabled"):
        timeout_info = summary["timeoutFeedbackOnly"]
        timeout_variable = (
            "timeoutFeedbackWithVerificationCadence"
            if timeout_info.get("verificationCadenceGuidance")
            else "timeoutFeedbackOnly"
        )
        intervention = ("timeout-feedback", timeout_variable, "turn-1", "timeout-feedback-repair", timeout_info)
    elif summary.get("compilerFeedbackOnly", {}).get("enabled"):
        intervention = ("compiler-feedback", "compilerEvidenceOnly", "turn-1", "compiler-feedback-repair", summary["compilerFeedbackOnly"])

    if intervention:
        label, variable, control_phase, variant_phase, info = intervention
        intervention_id = f"intervention-{args.run_id}-{label}"
        difficulty_id = f"difficulty-{args.run_id}-{label}"
        checkpoint_id = f"checkpoint-{args.run_id}-{control_phase}"
        insert("interventions", {
            "id": intervention_id,
            "schema": "agentlab.difficulty_intervention.v1",
            "difficultyId": difficulty_id,
            "checkpointId": checkpoint_id,
            "variable": variable,
            "controlValue": {
                "evidence": "none",
                **({"verificationCadenceGuidance": False} if label == "timeout-feedback" else {}),
            },
            "variantValue": {
                "evidence": label,
                **({"verificationCadenceGuidance": bool(info.get("verificationCadenceGuidance"))} if label == "timeout-feedback" else {}),
            },
            "model": "glm-5.3-flash",
            "agentKind": "pi",
            "frozen": ["native-session-lineage", "task-demand", "provider-reasoning", "behavior-oracle", "tool-policy"],
            "status": "completed",
        })
        for arm, phase in (("control", control_phase), (label, variant_phase)):
            row = phase_metrics(evidence, summary, phase)
            row.update({
                "id": f"crossing-{args.run_id}-{phase}",
                "schema": "agentlab.difficulty_crossing.v1",
                "interventionId": intervention_id,
                "difficultyId": difficulty_id,
                "checkpointId": checkpoint_id,
                "arm": arm,
                "outputSessionSha256": info.get("inputSessionSha256") if arm == "control" else info.get("outputSessionSha256"),
            })
            insert("crossings", {key: value for key, value in row.items() if value is not None})
        variant = phase_metrics(evidence, summary, variant_phase)
        full = variant["behaviorPass"] and variant["buildPass"] and not variant["scopeDrift"]
        upstream = variant["behaviorPass"] and not variant["scopeDrift"]
        insert("decisions", {
            "id": f"decision-{args.run_id}-{label}",
            "schema": "agentlab.difficulty_decision.v1",
            "difficultyId": difficulty_id,
            "interventionId": intervention_id,
            "decision": "accept-full-crossing" if full else "accept-upstream-crossing-route-downstream-repair" if upstream else "no-crossing",
            "reason": f"{label}: behaviorPass={variant['behaviorPass']}, buildPass={variant['buildPass']}, scopeDrift={variant['scopeDrift']}; preserve independent gates and exact output session.",
            "preferredArm": label if upstream else "control",
            "nextExperiment": "repeat-for-robustness" if full else "compiler-evidence-only" if upstream and not variant["buildPass"] else "design-next-experiment",
            "nextCheckpointBoundary": "post-" + label,
            "holdConstant": ["model", "provider-reasoning", "task", "behavior-oracle", "tool-policy"],
            "measure": ["latency", "gateway-requests", "behavior", "build", "scope-drift"],
        })

    for candidate in difficulty.get("candidates", []):
        dimension = candidate.get("dimensionId") or candidate.get("dimension")
        primary = candidate.get("primaryDimension") or candidate.get("category")
        mechanism = candidate.get("mechanism") or candidate.get("signature")
        if not all(isinstance(value, str) and value for value in (dimension, primary, mechanism)):
            continue
        if multi_repo_difficulty:
            verification = candidate.get("verificationContract") or {}
            if not isinstance(candidate.get("id"), str) or not candidate["id"]:
                raise SystemExit("multi-repository difficulty candidate requires a stable id")
            if candidate.get("automaticPromotion") is not False:
                raise SystemExit("multi-repository difficulty candidate must not auto-promote")
            if candidate.get("maturityState") != "candidate" or verification.get("caseReady") is not False:
                raise SystemExit("multi-repository difficulty must remain a non-ready candidate")
        candidate_id = f"difficulty-{args.run_id}-{hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest()[:16]}"
        difficulty_row = {
            "id": candidate_id,
            "schema": "agentlab.difficulty_point.v1",
            "taskId": summary.get("taskId"),
            "dimensionId": dimension,
            "primaryDimension": primary,
            "mechanism": mechanism,
            "signature": candidate.get("signature"),
            "status": candidate.get("status", "candidate"),
            "maturityState": candidate.get("maturityState", "candidate"),
            "sourceRevision": summary.get("sourceRevision"),
            "checkpointIds": checkpoint_ids,
            "evidenceIds": [f"evidence-{args.run_id}-difficulty-candidates"],
            "observation": {"producerRun": args.run_id, "reproducible": candidate.get("reproducible")},
        }
        if multi_repo_difficulty:
            difficulty_row.pop("sourceRevision", None)
            difficulty_row.update({
                "analysisCandidateId": candidate.get("id"),
                "sourceSetSha256": difficulty["sourceSetSha256"],
                "sources": difficulty["sources"],
                "seed": candidate.get("seed"),
                "affectedFiles": candidate.get("affectedFiles", []),
                "verificationContract": candidate.get("verificationContract"),
                "automaticPromotion": False,
            })
        insert("difficulty_points", difficulty_row)

    discrimination = load(evidence / "case-discrimination-report.json") or {}
    if discrimination:
        discrimination_schema = discrimination.get("schema")
        if discrimination_schema not in {
            "agentlab.case_discrimination_report.v1",
            "agentlab.case_discrimination_report.v2",
        }:
            raise SystemExit("unsupported case discrimination report schema")
        multi_repo_discrimination = (
            discrimination_schema == "agentlab.case_discrimination_report.v2"
        )
        source_identity_field = (
            "sourceSetSha256" if multi_repo_discrimination else "sourceRevision"
        )
        discrimination_source = discrimination.get(source_identity_field)
        method_revision = discrimination.get("methodRevision")
        source_pattern = SHA256 if multi_repo_discrimination else REVISION
        if not isinstance(discrimination_source, str) or not source_pattern.fullmatch(discrimination_source):
            raise SystemExit(f"case discrimination {source_identity_field} has invalid exact identity")
        if not isinstance(method_revision, str) or not REVISION.fullmatch(method_revision):
            raise SystemExit("case discrimination methodRevision must be an exact Git revision")
        summary_source = summary.get(source_identity_field)
        if summary_source and discrimination_source != summary_source:
            raise SystemExit(
                f"case discrimination {source_identity_field} does not match run summary"
            )
        policy = discrimination.get("policy") or {}
        if policy.get("automaticPromotion") is not False:
            raise SystemExit("case discrimination report must not auto-promote")
        for row in discrimination.get("ranking") or []:
            case_id = row.get("caseId")
            decision = row.get("decision")
            if not isinstance(case_id, str) or not case_id or not isinstance(decision, str):
                raise SystemExit("invalid case discrimination ranking row")
            suffix = hashlib.sha256(case_id.encode()).hexdigest()[:16]
            decision_row = {
                "id": f"decision-{args.run_id}-case-{suffix}",
                "schema": "agentlab.case_selection_decision.v1",
                "caseId": case_id,
                "taskId": case_id,
                "methodRevision": method_revision,
                "decision": decision,
                "eligible": bool(row.get("eligible")),
                "calibrationPassed": bool(row.get("calibrationPassed")),
                "evidenceComplete": bool(row.get("evidenceComplete")),
                "metrics": row.get("metrics") or {},
                "denominators": discrimination.get("denominators") or {},
                "evidenceIds": [f"evidence-{args.run_id}-case-discrimination-report"],
                "automaticPromotion": False,
                "nextAction": policy.get("nextAction"),
            }
            decision_row[source_identity_field] = discrimination_source
            insert("decisions", decision_row)

    performance = load(evidence / "smartperf-comparison.json") or {}
    if performance:
        if performance.get("schema") != "agentlab.smartperf_comparison.v1":
            raise SystemExit("unsupported SmartPerf comparison schema")
        policy = performance.get("policy") or {}
        if policy.get("automaticPromotion") is not False:
            raise SystemExit("SmartPerf comparison must not auto-promote")
        if policy.get("absolutePowerThermalUsed") is not False:
            raise SystemExit("emulator SmartPerf comparison must not claim absolute power or thermal")
        task_id = performance.get("taskId")
        decision = performance.get("decision")
        metrics = performance.get("metrics")
        comparable = performance.get("comparable")
        if not isinstance(task_id, str) or not task_id or not isinstance(metrics, list):
            raise SystemExit("invalid SmartPerf comparison identity or metrics")
        baseline_summary = load(evidence / "smartperf-baseline-summary.json")
        candidate_summary = load(evidence / "smartperf-candidate-summary.json")
        if not isinstance(baseline_summary, dict) or not isinstance(candidate_summary, dict):
            raise SystemExit("SmartPerf comparison requires retained baseline and candidate summaries")
        for label, profile in (
            ("baseline", baseline_summary),
            ("candidate", candidate_summary),
        ):
            if profile.get("schema") != "agentlab.smartperf_summary.v1":
                raise SystemExit(f"unsupported {label} SmartPerf summary schema")
            source_identity = profile.get("sourceIdentity")
            if not isinstance(source_identity, str) or not re.fullmatch(
                r"artifact-sha256:[0-9a-f]{64}", source_identity
            ):
                raise SystemExit(f"{label} SmartPerf summary requires exact HAP identity")
            if profile.get("taskId") != task_id:
                raise SystemExit(f"{label} SmartPerf summary task differs from comparison")
            if profile.get("environmentIdentity") != performance.get("environmentIdentity"):
                raise SystemExit(f"{label} SmartPerf summary environment differs from comparison")
            if (profile.get("authority") or {}).get("absolutePowerThermal") != "unavailable-on-emulator":
                raise SystemExit(f"{label} SmartPerf summary overclaims power or thermal authority")
        for label, profile in (
            ("baseline", baseline_summary),
            ("candidate", candidate_summary),
        ):
            if profile.get("runId") != performance.get(f"{label}RunId"):
                raise SystemExit(f"{label} SmartPerf summary run differs from comparison")
            if profile.get("sourceIdentity") != performance.get(f"{label}SourceIdentity"):
                raise SystemExit(f"{label} SmartPerf summary source differs from comparison")
            if canonical_json_sha256(profile) != performance.get(f"{label}SummarySha256"):
                raise SystemExit(f"{label} SmartPerf summary digest differs from comparison")
        source_revision = summary.get("sourceRevision")
        if not isinstance(source_revision, str) or not REVISION.fullmatch(source_revision):
            raise SystemExit("SmartPerf feedback requires exact run sourceRevision")
        for field in ("baselineSummarySha256", "candidateSummarySha256"):
            digest = performance.get(field)
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise SystemExit(f"SmartPerf comparison requires exact {field}")
        if not metrics or not all(
            isinstance(row, dict)
            and isinstance(row.get("metric"), str)
            and row.get("status") in {"passed", "regressed", "missing"}
            for row in metrics
        ):
            raise SystemExit("invalid SmartPerf comparison metric row")
        if comparable is True:
            if any(row["status"] == "missing" for row in metrics):
                raise SystemExit("comparable SmartPerf report contains missing metric")
            expected = (
                "performance-regression-candidate"
                if any(row["status"] == "regressed" for row in metrics)
                else "within-relative-guardrails"
            )
        elif comparable is False:
            expected = "insufficient-comparable-evidence"
        else:
            raise SystemExit("SmartPerf comparable must be boolean")
        if decision != expected:
            raise SystemExit("SmartPerf decision contradicts comparison metrics")
        suffix = hashlib.sha256(
            f"{task_id}|{performance.get('candidateRunId')}|{performance.get('environmentIdentity')}".encode()
        ).hexdigest()[:16]
        insert("decisions", {
            "id": f"decision-{args.run_id}-performance-{suffix}",
            "schema": "agentlab.performance_feedback_decision.v1",
            "taskId": task_id,
            "sourceRevision": source_revision,
            "baselineRunId": performance.get("baselineRunId"),
            "baselineSourceIdentity": performance.get("baselineSourceIdentity"),
            "candidateRunId": performance.get("candidateRunId"),
            "candidateSourceIdentity": performance.get("candidateSourceIdentity"),
            "baselineSummarySha256": performance.get("baselineSummarySha256"),
            "candidateSummarySha256": performance.get("candidateSummarySha256"),
            "environmentIdentity": performance.get("environmentIdentity"),
            "comparable": comparable,
            "decision": decision,
            "metrics": metrics,
            "evidenceIds": [
                f"evidence-{args.run_id}-smartperf-baseline-summary",
                f"evidence-{args.run_id}-smartperf-candidate-summary",
                f"evidence-{args.run_id}-smartperf-comparison",
            ],
            "automaticPromotion": False,
            "absolutePowerThermalUsed": False,
            "nextAction": "maintainer-review-performance-feedback",
        })

    tables = [{"path": path, "operations": operations} for path, operations in groups.items() if operations]
    if not tables:
        raise SystemExit("no durable rows derived from run")
    transaction_id = stable_uuid(args.run_id, "cbgroom-flywheel-v1")
    payload = {
        "skill_id": "table.author",
        "skill_version": "2.2.0",
        "operation": "worktree_table_batch_transaction",
        "caller_person_id": args.caller_person_id,
        "arguments": {
            "repo": args.repo,
            "expected_revision": args.revision,
            "transaction_id": transaction_id,
            "idempotency_key": transaction_id,
            "actor": {"kind": "github-action", "repository": args.github_repository, "runId": args.run_id},
            "tables": tables,
            "topic_id": "main",
            "message": f"Persist AgentLab flywheel run {args.run_id}",
        },
    }
    args.output.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    print(json.dumps({"ok": True, "tables": {entry["path"]: len(entry["operations"]) for entry in tables}, "transactionId": transaction_id}, sort_keys=True))


if __name__ == "__main__":
    main()
