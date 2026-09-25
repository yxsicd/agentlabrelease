#!/usr/bin/env python3
"""Run the credential-free multi-repository protocol as one evidence chain."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any


REVISION = re.compile(r"[0-9a-f]{40}")
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "examples/multi-repo-case"
REVIEWER = "deterministic-golden-path-review-fixture"


class GoldenPathError(RuntimeError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise GoldenPathError(message)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def write(path: Path, value: Any) -> None:
    require(not path.exists(), f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


class Runner:
    def __init__(self, evidence: Path):
        self.evidence = evidence
        self.evidence.mkdir(parents=True)
        self.phases: list[dict[str, Any]] = []

    def run(self, phase: str, argv: list[str], env: dict[str, str] | None = None) -> None:
        index = len(self.phases) + 1
        started = time.monotonic()
        completed = subprocess.run(
            argv,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
        )
        prefix = self.evidence / f"{index:02d}-{phase}"
        stdout_path = prefix.with_suffix(".stdout.log")
        stderr_path = prefix.with_suffix(".stderr.log")
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        receipt = {
            "phase": phase,
            "argv": argv,
            "returnCode": completed.returncode,
            "durationMs": round((time.monotonic() - started) * 1000),
            "stdoutSha256": digest(stdout_path),
            "stderrSha256": digest(stderr_path),
        }
        self.phases.append(receipt)
        if completed.returncode != 0:
            raise GoldenPathError(
                f"{phase} failed with {completed.returncode}: {completed.stderr[-2000:]}"
            )


def script(name: str) -> str:
    return str(ROOT / "scripts" / name)


def python(name: str, *arguments: Any) -> list[str]:
    return [sys.executable, script(name), *(str(value) for value in arguments)]


def risk_ids(path: Path) -> str:
    return ",".join(sorted(row["id"] for row in load(path)["risks"]))


def portable_spec(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "agentlab.multi_repo_source_spec.v1",
        "sources": [
            {key: row[key] for key in ("id", "repository", "revision")}
            for row in manifest["repositories"]
        ],
        "moduleBindings": manifest["moduleBindings"],
        "automaticPromotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analyzer", type=Path, required=True)
    parser.add_argument("--method-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(REVISION.fullmatch(args.method_revision) is not None, "method revision must be exact")
        require(args.analyzer.is_file() and not args.analyzer.is_symlink(), "analyzer must be a regular file")
        require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
        args.output.mkdir(parents=True)
        runner = Runner(args.output / "commands")

        source = args.output / "source"
        runner.run(
            "prepare-source",
            python(
                "prepare-multi-repo-construction-fixture.py",
                "--source", FIXTURE / "baseline",
                "--output", source,
            ),
        )
        manifest_path = source / "manifest.json"
        manifest = load(manifest_path)
        write(source / "source-spec.json", portable_spec(manifest))
        analysis = source / "analysis"
        runner.run("analyze", [str(args.analyzer.resolve()), str(manifest_path), str(analysis)])
        analysis_run = source / "analysis-run.json"
        runner.run(
            "analysis-run-create",
            python(
                "multi-repo-analysis-run.py", "create",
                "--root", source,
                "--method-revision", args.method_revision,
                "--output", analysis_run,
            ),
        )
        runner.run(
            "analysis-run-validate",
            python("multi-repo-analysis-run.py", "validate", "--root", source, "--run", analysis_run),
        )

        difficulty_path = analysis / "difficulty_candidates.json"
        facts_path = analysis / "workspace_facts.jsonl"
        difficulty = load(difficulty_path)
        candidates = difficulty.get("candidates") or []
        require(len(candidates) >= 2, "golden path requires at least two candidates")
        candidate = max(
            candidates,
            key=lambda row: (
                row.get("maxDependencyDepth", -1),
                row.get("affectedRepositoryCount", -1),
                row.get("id", ""),
            ),
        )
        candidate_id = candidate["id"]

        cohort_root = args.output / "cohort"
        cohort_proposal = cohort_root / "proposal.json"
        cohort_review = cohort_root / "review.json"
        cohort = cohort_root / "cohort.json"
        selected_ids = ",".join(sorted(row["id"] for row in candidates))
        runner.run(
            "cohort-propose",
            python(
                "propose-multi-repo-candidate-cohort.py",
                "--difficulty", difficulty_path,
                "--cohort-id", "deterministic-multi-repo-golden-path",
                "--method-revision", args.method_revision,
                "--proposal-method-revision", args.method_revision,
                "--output", cohort_proposal,
            ),
        )
        runner.run(
            "cohort-review",
            python(
                "review-multi-repo-candidate-cohort.py", "decide",
                "--proposal", cohort_proposal,
                "--expected-sha256", digest(cohort_proposal),
                "--selected-candidate-ids", selected_ids,
                "--reviewer", REVIEWER,
                "--acknowledged-risk-ids", risk_ids(cohort_proposal),
                "--rationale", "This deterministic review exercises exact cohort binding without claiming representative sampling.",
                "--output", cohort_review,
            ),
        )
        runner.run(
            "cohort-compile",
            python(
                "review-multi-repo-candidate-cohort.py", "compile",
                "--proposal", cohort_proposal,
                "--review", cohort_review,
                "--output", cohort,
            ),
        )
        selection = cohort_root / "selection.json"
        runner.run(
            "cohort-select",
            python(
                "select-multi-repo-cohort-candidate.py",
                "--cohort", cohort,
                "--difficulty", difficulty_path,
                "--expected-cohort-sha256", digest(cohort),
                "--candidate-id", candidate_id,
                "--output", selection,
            ),
        )

        authoring = args.output / "calibration-authoring"
        runner.run(
            "calibration-authoring",
            python(
                "run-multi-repo-calibration-authoring.py", "run",
                "--selection", selection,
                "--difficulty", difficulty_path,
                "--manifest", manifest_path,
                "--facts", facts_path,
                "--participant", FIXTURE / "mock-calibration-author.py",
                "--participant-id", "deterministic-golden-path-independent-evaluator-fixture",
                "--method-revision", args.method_revision,
                "--output", authoring,
            ),
        )
        runner.run(
            "calibration-authoring-validate",
            python(
                "run-multi-repo-calibration-authoring.py", "validate",
                "--root", authoring,
            ),
        )
        authoring_receipt = authoring / "authoring-receipt.json"
        authored_proposal = authoring / "construction-contract-proposal.json"

        construction_contract_root = args.output / "construction-contract"
        surface = authoring / "draft/source-surface.json"
        contract_proposal = construction_contract_root / "proposal.json"
        contract_review = construction_contract_root / "review.json"
        construction_contract = construction_contract_root / "contract.json"
        oracle_contract = authoring / "draft/oracle-contract.json"
        runner.run(
            "construction-contract-propose",
            python(
                "multi-repo-construction-contract.py", "propose",
                "--selection", selection,
                "--difficulty", difficulty_path,
                "--surface", surface,
                "--oracle-contract", oracle_contract,
                "--authoring-receipt", authoring_receipt,
                "--authoring-proposal", authored_proposal,
                "--output", contract_proposal,
            ),
        )
        runner.run(
            "construction-contract-review",
            python(
                "multi-repo-construction-contract.py", "decide",
                "--proposal", contract_proposal,
                "--expected-sha256", digest(contract_proposal),
                "--reviewer", REVIEWER,
                "--acknowledged-risk-ids", risk_ids(contract_proposal),
                "--rationale", "This exact source surface and Oracle declaration are approved only for deterministic construction testing.",
                "--output", contract_review,
            ),
        )
        runner.run(
            "construction-contract-compile",
            python(
                "multi-repo-construction-contract.py", "compile",
                "--proposal", contract_proposal,
                "--review", contract_review,
                "--output", construction_contract,
            ),
        )
        runner.run(
            "construction-contract-validate",
            python(
                "multi-repo-construction-contract.py", "validate",
                "--selection", selection,
                "--difficulty", difficulty_path,
                "--surface", surface,
                "--oracle-contract", oracle_contract,
                "--authoring-receipt", authoring_receipt,
                "--authoring-proposal", authored_proposal,
                "--proposal", contract_proposal,
                "--review", contract_review,
                "--contract", construction_contract,
            ),
        )

        construction = args.output / "construction"
        runner.run(
            "construct-intent",
            python(
                "run-multi-repo-intent-construction.py",
                "--manifest", manifest_path,
                "--difficulty", difficulty_path,
                "--facts", facts_path,
                "--candidate-id", candidate_id,
                "--oracle-contract", oracle_contract,
                "--construction-contract", construction_contract,
                "--participant", FIXTURE / "mock-construction-agent.py",
                "--participant-id", "deterministic-golden-path-construction-fixture",
                "--output", construction,
            ),
        )
        quality = construction / "intent-quality.json"
        runner.run(
            "score-intent",
            python(
                "score-multi-repo-intent.py",
                "--intent", construction / "intent.json",
                "--construction-receipt", construction / "construction-receipt.json",
                "--oracle-contract", oracle_contract,
                "--output", quality,
            ),
        )
        case_root = args.output / "case"
        case_proposal = case_root / "case-plan-proposal.json"
        runner.run(
            "case-plan-propose",
            python(
                "propose-multi-repo-case-plan.py",
                "--difficulty", difficulty_path,
                "--intent", construction / "intent.json",
                "--construction-receipt", construction / "construction-receipt.json",
                "--quality-report", quality,
                "--output", case_proposal,
            ),
        )
        dependency_proposal = case_root / "dependency-plan-proposal.json"
        runner.run(
            "dependency-plan-propose",
            python(
                "propose-dependency-discovery-plan.py",
                "--case-plan-proposal", case_proposal,
                "--difficulty", difficulty_path,
                "--program-facts", facts_path,
                "--output", dependency_proposal,
            ),
        )
        case_review = case_root / "case-plan-review.json"
        case_plan = case_root / "case-plan.json"
        runner.run(
            "case-plan-review",
            python(
                "create-multi-repo-review-decision.py",
                "--proposal", case_proposal,
                "--expected-sha256", digest(case_proposal),
                "--reviewer", REVIEWER,
                "--acknowledged-risk-ids", risk_ids(case_proposal),
                "--rationale", "The deterministic task semantics and staged checks are approved only for protocol calibration.",
                "--output", case_review,
            ),
        )
        runner.run(
            "case-plan-compile",
            python(
                "review-multi-repo-case-plan.py",
                "--proposal", case_proposal,
                "--review", case_review,
                "--output", case_plan,
            ),
        )
        dependency_review = case_root / "dependency-plan-review.json"
        dependency_plan = case_root / "dependency-plan.json"
        runner.run(
            "dependency-plan-review",
            python(
                "review-dependency-discovery-plan.py", "decide",
                "--proposal", dependency_proposal,
                "--expected-sha256", digest(dependency_proposal),
                "--reviewer", REVIEWER,
                "--acknowledged-risk-ids", risk_ids(dependency_proposal),
                "--rationale", "The hidden dependency obligations are directly inferable from this deterministic source fixture.",
                "--output", dependency_review,
            ),
        )
        runner.run(
            "dependency-plan-compile",
            python(
                "review-dependency-discovery-plan.py", "compile",
                "--proposal", dependency_proposal,
                "--review", dependency_review,
                "--output", dependency_plan,
            ),
        )

        bundle_root = args.output / "calibration-authority"
        authored_bundle = authoring / "draft/bundle"
        bundle_proposal = bundle_root / "proposal.json"
        bundle_review = bundle_root / "review.json"
        bundle_contract = bundle_root / "contract.json"
        staged_bundle = bundle_root / "bundle"
        runner.run(
            "calibration-bundle-propose",
            python(
                "multi-repo-calibration-bundle.py", "propose",
                "--bundle-root", authored_bundle,
                "--descriptor", authored_bundle / "calibration-bundle.json",
                "--construction-contract", construction_contract,
                "--authoring-receipt", authoring_receipt,
                "--authoring-root", authoring,
                "--output", bundle_proposal,
            ),
        )
        runner.run(
            "calibration-bundle-review",
            python(
                "multi-repo-calibration-bundle.py", "decide",
                "--proposal", bundle_proposal,
                "--expected-sha256", digest(bundle_proposal),
                "--reviewer", REVIEWER,
                "--acknowledged-risk-ids", risk_ids(bundle_proposal),
                "--rationale", "The exact fixture driver, Oracle and reference tree are approved only for golden-path calibration.",
                "--output", bundle_review,
            ),
        )
        runner.run(
            "calibration-bundle-compile",
            python(
                "multi-repo-calibration-bundle.py", "compile",
                "--proposal", bundle_proposal,
                "--review", bundle_review,
                "--output", bundle_contract,
            ),
        )
        runner.run(
            "calibration-bundle-stage",
            python(
                "multi-repo-calibration-bundle.py", "stage",
                "--bundle-root", authored_bundle,
                "--descriptor", authored_bundle / "calibration-bundle.json",
                "--construction-contract", construction_contract,
                "--proposal", bundle_proposal,
                "--authoring-receipt", authoring_receipt,
                "--authoring-root", authoring,
                "--output", staged_bundle,
            ),
        )
        runner.run(
            "calibration-bundle-validate",
            python(
                "multi-repo-calibration-bundle.py", "validate",
                "--bundle-root", staged_bundle,
                "--descriptor", staged_bundle / "descriptor.json",
                "--construction-contract", staged_bundle / "construction-contract.json",
                "--proposal", bundle_proposal,
                "--review", bundle_review,
                "--contract", bundle_contract,
                "--authoring-receipt", authoring_receipt,
                "--authoring-root", authoring,
            ),
        )
        calibration = args.output / "calibration"
        runner.run(
            "calibration-execute",
            python(
                "multi-repo-calibration-bundle.py", "run",
                "--bundle-root", staged_bundle,
                "--contract", bundle_contract,
                "--proposal", bundle_proposal,
                "--review", bundle_review,
                "--construction-contract", construction_contract,
                "--baseline", source / "repositories",
                "--authoring-receipt", authoring_receipt,
                "--authoring-root", authoring,
                "--output", calibration,
            ),
        )

        base_case = case_root / "base-evaluation-case.json"
        runner.run(
            "case-freeze",
            python(
                "generate-multi-repo-case.py",
                "--difficulty", difficulty_path,
                "--plan", case_plan,
                "--proposal", case_proposal,
                "--review", case_review,
                "--construction-quality", quality,
                "--candidate-selection", selection,
                "--calibration", calibration / "summary.json",
                "--calibration-run", calibration / "calibration-run.json",
                "--output", base_case,
            ),
        )
        dependency_contract = case_root / "dependency-contract.json"
        runner.run(
            "dependency-contract-build",
            python(
                "build-dependency-discovery-contract.py",
                "--case", base_case,
                "--program-facts", facts_path,
                "--plan", dependency_plan,
                "--output", dependency_contract,
            ),
        )
        evaluation_case = case_root / "evaluation-case.json"
        runner.run(
            "dependency-contract-bind",
            python(
                "bind-dependency-discovery-case.py",
                "--case", base_case,
                "--dependency-contract", dependency_contract,
                "--program-facts", facts_path,
                "--output", evaluation_case,
            ),
        )
        runner.run(
            "case-qualification-validate",
            python(
                "validate-case-qualification.py",
                "--case", evaluation_case,
                "--calibration", calibration / "summary.json",
            ),
        )
        case_supply_report = case_root / "case-supply-report.json"
        runner.run(
            "case-supply-summarize",
            python(
                "summarize-case-supply.py",
                "--cohort", cohort,
                "--case", evaluation_case,
                "--method-revision", args.method_revision,
                "--output", case_supply_report,
            ),
        )

        blind_cut = args.output / "blind-cut"
        runner.run(
            "blind-cut-build",
            python(
                "prepare-multi-repo-blind-cut.py",
                "--case", evaluation_case,
                "--oracle", staged_bundle / "oracle.mjs",
                "--reference-root", staged_bundle / "reference",
                "--calibration", calibration / "summary.json",
                "--review", case_review,
                "--dependency-contract", dependency_contract,
                "--program-facts", facts_path,
                "--method-revision", args.method_revision,
                "--constructed-at", "2026-01-01T00:00:00Z",
                "--source-visibility", "held-out-public-revision",
                "--output", blind_cut,
            ),
        )
        runner.run("blind-cut-validate", python("build-blind-case-cut.py", "validate", "--cut", blind_cut))
        participant_cut = args.output / "participant-cut"
        dispatch_receipt = args.output / "blind-dispatch-receipt.json"
        runner.run(
            "blind-cut-stage-participant",
            python(
                "build-blind-case-cut.py", "stage-participant",
                "--cut", blind_cut,
                "--output", participant_cut,
                "--receipt", dispatch_receipt,
            ),
        )

        attempts = args.output / "attempts"
        attempt_rows = []
        for profile in ("baseline", "reference"):
            attempt = attempts / profile
            environment = dict(os.environ)
            environment["AGENTLAB_MOCK_ASSESSED_PROFILE"] = profile
            participant_id = f"mock-{profile}"
            runner.run(
                f"assess-{profile}",
                python(
                    "run-multi-repo-assessment.py",
                    "--case", evaluation_case,
                    "--manifest", manifest_path,
                    "--oracle", staged_bundle / "oracle.mjs",
                    "--participant", FIXTURE / "mock-assessed-agent.py",
                    "--participant-id", participant_id,
                    "--blind-participant-root", participant_cut,
                    "--blind-dispatch-receipt", dispatch_receipt,
                    "--dependency-contract", dependency_contract,
                    "--program-facts", facts_path,
                    "--output", attempt,
                ),
                environment,
            )
            attempt_rows.append({
                "attemptId": f"{profile}-1",
                "participantId": participant_id,
                "evidence": attempt.relative_to(args.output).as_posix(),
            })

        collection_manifest = args.output / "attempt-collection.json"
        case = load(evaluation_case)
        write(collection_manifest, {
            "schema": "agentlab.case_attempt_collection.v2",
            "sourceSetSha256": case["sourceSetSha256"],
            "methodRevision": args.method_revision,
            "cases": [{
                "id": case["id"],
                "calibration": (calibration / "summary.json").relative_to(args.output).as_posix(),
                "attempts": attempt_rows,
            }],
        })
        discrimination_input = args.output / "discrimination-input.json"
        discrimination_report = args.output / "discrimination-report.json"
        runner.run(
            "attempts-collect",
            python(
                "collect-case-attempts.py",
                "--manifest", collection_manifest,
                "--output", discrimination_input,
            ),
        )
        runner.run(
            "discrimination-score",
            python(
                "score-case-discrimination.py",
                "--input", discrimination_input,
                "--output", discrimination_report,
                "--required-trials", "1",
            ),
        )
        report = load(discrimination_report)
        ranking = report["ranking"][0]
        baseline_summary = load(attempts / "baseline/summary.json")
        reference_summary = load(attempts / "reference/summary.json")
        case_authoring = (
            ((case.get("calibration") or {}).get("executableBundle") or {}).get("calibrationAuthoring")
        )
        require(
            case_authoring == load(calibration / "calibration-run.json").get("calibrationAuthoring"),
            "frozen case lost calibration authoring lineage",
        )
        require(baseline_summary["subjectTaskSucceeded"] is False, "baseline unexpectedly passed")
        require(reference_summary["subjectTaskSucceeded"] is True, "reference unexpectedly failed")
        require(ranking["eligible"] is True, "case is not discrimination-eligible")
        require(ranking["metrics"]["discriminationScore"] == 1.0, "fixture discrimination score differs")
        require(ranking["processAwareEligible"] is True, "process-aware discrimination is not eligible")
        require(
            reference_summary["processMeasurement"]["dependencyDiscovery"]["coverageQualified"] is True,
            "reference dependency discovery did not cover the hidden obligations",
        )
        require(
            reference_summary["blindDispatch"]["interfaceInputQualified"] is True
            and reference_summary["blindDispatch"]["filesystemIsolationQualified"] is False,
            "blind dispatch boundary differs",
        )
        require(
            (case.get("calibration") or {}).get("executableBundle")
            == (case.get("lineage") or {}).get("calibrationBundleRun"),
            "frozen case calibration-bundle lineage differs",
        )
        replay = (case.get("qualificationMatrix") or {}).get("referenceReplay") or {}
        require(
            replay.get("alternativeValidQualified") is True
            and replay.get("alternativeValidCount") == 1,
            "alternative-valid Oracle breadth qualification differs",
        )
        authoring_receipt_value = load(authoring_receipt)
        construction_authoring = load(construction_contract).get("calibrationAuthoring") or {}
        calibration_authoring = load(bundle_contract).get("calibrationAuthoring") or {}
        require(
            construction_authoring.get("receiptSha256")
            == calibration_authoring.get("receiptSha256")
            == digest(authoring_receipt),
            "construction and calibration authoring receipt lineage differs",
        )
        require(
            construction_authoring.get("draftManifestSha256")
            == calibration_authoring.get("draftManifestSha256")
            == authoring_receipt_value.get("draftManifestSha256"),
            "construction and calibration authoring draft lineage differs",
        )
        supply = load(case_supply_report)
        require(
            supply["denominators"]["functionalQualifiedCaseCount"] == 1
            and supply["denominators"]["endToEndQualifiedCaseCount"] == 0,
            "case supply qualification tiers differ",
        )
        require(
            supply["laneCoverage"]["observedLanes"] == ["derived"]
            and supply["laneCoverage"]["unobservedLanes"] == ["natural"],
            "case supply lane coverage differs",
        )

        summary = {
            "schema": "agentlab.multi_repo_golden_path.v1",
            "status": "passed",
            "methodRevision": args.method_revision,
            "sourceSetSha256": case["sourceSetSha256"],
            "analysisRunSha256": digest(analysis_run),
            "candidateCount": len(candidates),
            "reviewedCohortSha256": digest(cohort),
            "selectedCandidateId": candidate_id,
            "calibrationAuthoringReceiptSha256": digest(authoring_receipt),
            "calibrationAuthoringDraftManifestSha256": authoring_receipt_value["draftManifestSha256"],
            "constructionContractSha256": digest(construction_contract),
            "calibrationBundleSha256": digest(bundle_contract),
            "calibrationRunSha256": digest(calibration / "calibration-run.json"),
            "evaluationCaseSha256": digest(evaluation_case),
            "caseSupplyReportSha256": digest(case_supply_report),
            "blindCutReceiptSha256": digest(blind_cut / "cut-receipt.json"),
            "attempts": {
                "baseline": {"subjectTaskSucceeded": False, "summarySha256": digest(attempts / "baseline/summary.json")},
                "reference": {"subjectTaskSucceeded": True, "summarySha256": digest(attempts / "reference/summary.json")},
            },
            "discrimination": {
                "eligible": True,
                "score": ranking["metrics"]["discriminationScore"],
                "processAwareEligible": ranking["processAwareEligible"],
                "reportSha256": digest(discrimination_report),
            },
            "oracleBreadth": {
                "alternativeValidQualified": True,
                "alternativeValidCount": replay["alternativeValidCount"],
                "variantRoles": (case.get("calibration") or {}).get("variantRoles"),
            },
            "phaseCount": len(runner.phases),
            "phases": runner.phases,
            "qualificationBoundary": {
                "protocolIntegrationQualified": True,
                "independentEvaluatorAuthoringProtocolQualified": True,
                "realModelQualified": False,
                "filesystemIsolationQualified": False,
                "authenticatedBlindReviewQualified": False,
                "harmonyBuildQualified": False,
                "emulatorQualified": False,
                "performanceQualified": False,
                "representativePopulationQualified": False,
            },
            "automaticPromotion": False,
        }
        write(args.output / "summary.json", summary)
        print(json.dumps({
            "ok": True,
            "status": summary["status"],
            "candidateId": candidate_id,
            "discriminationScore": summary["discrimination"]["score"],
            "summarySha256": digest(args.output / "summary.json"),
        }, sort_keys=True))
        return 0
    except (GoldenPathError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"multi-repository golden path failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
