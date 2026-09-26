#!/usr/bin/env python3
"""Validate and retain one release-bound Linux Harmony emulator acceptance."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from typing import Any


RECEIPT_SCHEMA = "agentlab.release_harmony_acceptance.v1"
PLAN_BINDING_SCHEMA = "agentlab.release_harmony_acceptance_plan.v1"
CAMPAIGN_SUMMARY_SCHEMA = "agentlab.harmony_assessed_campaign_summary.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")


class AcceptanceError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def load(path: pathlib.Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AcceptanceError(f"cannot load {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_binding(binding: Any, path: pathlib.Path, label: str) -> None:
    require(isinstance(binding, dict), f"{label} binding is required")
    require(path.resolve() == pathlib.Path(str(binding.get("path"))).resolve(), f"{label} path differs")
    require(binding.get("sha256") == sha256(path), f"{label} digest differs")


def validate_cleanup(cleanup: dict[str, Any]) -> dict[str, Any]:
    require(cleanup.get("schema") == "agentlab.harmony_emulator_cleanup.v1", "unsupported cleanup evidence schema")
    require(cleanup.get("emulatorProcessCount") == 0, "emulator processes remain after campaign")
    require(cleanup.get("hdcTargets") == [], "HDC targets remain after campaign")
    route = cleanup.get("remoteInspection")
    require(isinstance(route, dict), "cleanup remote inspection is required")
    require(route.get("routeDecision") in {"peer_direct", "upstream_local_peer"}, "cleanup did not use a direct peer route")
    peer = route.get("targetPeerId")
    require(isinstance(peer, str) and peer.startswith("lgw_"), "cleanup target peer is invalid")
    operation_ids = route.get("operationIds")
    require(isinstance(operation_ids, list) and operation_ids and all(isinstance(row, str) and row for row in operation_ids), "cleanup operation ids are required")
    return {"targetPeerId": peer, "routeDecision": route["routeDecision"], "operationIds": operation_ids}


def validate(
    closure_path: pathlib.Path,
    plan_path: pathlib.Path,
    campaign_root: pathlib.Path,
    cleanup_path: pathlib.Path,
) -> dict[str, Any]:
    closure = load(closure_path, "release closure")
    plan = load(plan_path, "campaign plan")
    summary_path = campaign_root / "summary.json"
    summary = load(summary_path, "campaign summary")
    cleanup = load(cleanup_path, "cleanup evidence")
    release = plan.get("releaseAcceptance")
    require(isinstance(release, dict) and release.get("schema") == PLAN_BINDING_SCHEMA, "campaign is not release-bound")
    exact_binding(release.get("closure"), closure_path, "release closure")
    release_revision = (closure.get("sources") or {}).get("releaseGitSha")
    require(release.get("releaseTag") == closure.get("releaseTag"), "release tag differs")
    require(release.get("releaseGitSha") == release_revision == plan.get("methodRevision"), "release method revision differs")
    require(release.get("automaticPromotion") is False and plan.get("automaticPromotion") is False, "acceptance may not auto-promote")
    required_assets = release.get("requiredAssets")
    closure_assets = {row.get("id"): row for row in closure.get("assets", []) if isinstance(row, dict)}
    require(isinstance(required_assets, list) and len(required_assets) == 5, "release-bound Harmony assets are incomplete")
    for bound in required_assets:
        current = closure_assets.get(bound.get("id")) if isinstance(bound, dict) else None
        require(isinstance(current, dict), "release-bound Harmony asset is absent from closure")
        require(all(bound.get(key) == current.get(key) for key in ("url", "sha256", "bytes", "immutableRef")), "release-bound Harmony asset identity differs")

    require(summary.get("schema") == CAMPAIGN_SUMMARY_SCHEMA, "unsupported campaign summary schema")
    require(summary.get("campaignId") == plan.get("campaignId"), "campaign id differs")
    require(summary.get("planSha256") == sha256(plan_path), "campaign plan digest differs")
    require(summary.get("methodRevision") == release_revision, "campaign method revision differs")
    require(summary.get("status") == "assessed-review-required", "campaign is not assessed-review-required")
    require(summary.get("automaticPromotion") is False, "campaign summary may not auto-promote")
    require(summary.get("attemptCount", 0) >= 2 and summary.get("deviceAttemptCount", 0) >= 2, "campaign has insufficient device attempts")
    require(summary.get("eligibleCaseIds") == [summary.get("caseId")], "campaign did not retain one eligible calibrated case")
    require(summary.get("feedbackCandidateCount", 0) >= 1, "campaign produced no recursive feedback candidate")

    attempts = plan.get("attempts")
    require(isinstance(attempts, list) and len(attempts) >= 2, "campaign attempts are invalid")
    rows = []
    passed = 0
    oracle_failed = 0
    for attempt in attempts:
        attempt_id = attempt.get("attemptId") if isinstance(attempt, dict) else None
        require(isinstance(attempt_id, str) and attempt_id, "attempt id is invalid")
        root = campaign_root / "attempts" / attempt_id / "harmony-loop"
        standard_path = root / "standard-test/receipt.json"
        result_path = root / "assessment/execution/result.json"
        standard = load(standard_path, f"{attempt_id} standard test")
        result = load(result_path, f"{attempt_id} device result")
        require(standard.get("framework") == "instrument-test-ohosTest-hypium", f"{attempt_id} did not use ohosTest/Hypium")
        require(standard.get("status") == "passed-review-required" and standard.get("subjectTaskSucceeded") is True, f"{attempt_id} standard tests did not pass")
        require(standard.get("automaticPromotion") is False, f"{attempt_id} standard tests may not auto-promote")
        require(result.get("environmentIdentity") == plan["device"]["runtime"].get("environmentIdentity"), f"{attempt_id} environment identity differs")
        require(result.get("infrastructureAvailable") is True and result.get("assessmentStatus") == "assessed", f"{attempt_id} emulator infrastructure was unavailable")
        require(result.get("powerThermalAuthority") == "unavailable_on_emulator", f"{attempt_id} overclaims power or thermal authority")
        row = {
            "attemptId": attempt_id,
            "standardTest": {"status": standard["status"], "framework": standard["framework"], "sha256": sha256(standard_path)},
            "device": {"status": result.get("status"), "oracleStatus": result.get("oracleStatus"), "failureClass": result.get("failureClass"), "sha256": sha256(result_path)},
        }
        if result.get("status") == "passed" and result.get("oracleStatus") == "passed" and result.get("subjectTaskSucceeded") is True:
            performance_path = root / "assessment/execution/smartperf-summary.json"
            performance = load(performance_path, f"{attempt_id} SmartPerf summary")
            authority = performance.get("authority") or {}
            require(performance.get("profileValid") is True and performance.get("sampleCount", 0) >= 3, f"{attempt_id} SmartPerf profile is invalid")
            require(authority.get("relativePerformance") == "smartperf-emulator-proxy", f"{attempt_id} relative performance authority differs")
            require(authority.get("absolutePowerThermal") == "unavailable-on-emulator", f"{attempt_id} overclaims SmartPerf power authority")
            row["performance"] = {"profileValid": True, "sampleCount": performance["sampleCount"], "sha256": sha256(performance_path)}
            passed += 1
        elif result.get("status") == "failed" and result.get("oracleStatus") == "failed" and result.get("failureClass") == "oracle" and result.get("subjectTaskSucceeded") is False:
            require(result.get("profileStatus") == "not-run" and not (root / "assessment/execution/smartperf-summary.json").exists(), f"{attempt_id} performance was not gated by functional failure")
            row["performance"] = {"status": "not-run", "reason": "functional-oracle-failed"}
            oracle_failed += 1
        else:
            raise AcceptanceError(f"{attempt_id} has unsupported device verdict")
        rows.append(row)
    require(passed >= 1, "campaign has no functional pass with valid SmartPerf evidence")
    require(oracle_failed >= 1, "campaign has no meaningful Oracle failure")
    route = validate_cleanup(cleanup)
    return {
        "schema": RECEIPT_SCHEMA,
        "status": "accepted-developer-preview-review-required",
        "releaseTag": closure["releaseTag"],
        "releaseGitSha": release_revision,
        "closure": {"path": closure_path.as_posix(), "sha256": sha256(closure_path)},
        "campaign": {"campaignId": plan["campaignId"], "planSha256": sha256(plan_path), "summarySha256": sha256(summary_path), "caseId": summary["caseId"], "sourceSetSha256": summary["sourceSetSha256"]},
        "environmentIdentity": plan["device"]["runtime"]["environmentIdentity"],
        "attempts": rows,
        "remoteInspection": {**route, "cleanupEvidenceSha256": sha256(cleanup_path)},
        "qualificationBoundary": {
            "qualified": ["release-bound Linux x86 KVM emulator execution", "source-bound ohosTest/Hypium execution", "functional Oracle pass/fail separation", "functional-pass-gated SmartPerf proxy collection"],
            "notQualified": ["absolute power or thermal measurement", "physical-device behavior", "population-level discrimination confidence", "automatic release promotion"],
        },
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closure", type=pathlib.Path, required=True)
    parser.add_argument("--plan", type=pathlib.Path, required=True)
    parser.add_argument("--campaign-output", type=pathlib.Path, required=True)
    parser.add_argument("--cleanup-evidence", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite acceptance receipt: {args.output}")
    try:
        receipt = validate(args.closure.resolve(), args.plan.resolve(), args.campaign_output.resolve(), args.cleanup_evidence.resolve())
    except AcceptanceError as error:
        raise SystemExit(f"release Harmony acceptance invalid: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"releaseTag": receipt["releaseTag"], "status": receipt["status"], "receiptSha256": sha256(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
