#!/usr/bin/env python3
"""Execute a frozen multi-repository case with a replaceable assessed Agent."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone


SHA256 = re.compile(r"[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path: Path):
    value = json.loads(path.read_text())
    require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def digest_bytes(value: bytes):
    return hashlib.sha256(value).hexdigest()


def digest(path: Path):
    return digest_bytes(path.read_bytes())


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def validate_blind_dispatch(participant_root: Path, receipt_path: Path):
    module_path = Path(__file__).with_name("build-blind-case-cut.py")
    spec = importlib.util.spec_from_file_location("agentlab_blind_case_cut", module_path)
    require(spec is not None and spec.loader is not None, "blind dispatch validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_dispatch(participant_root.absolute(), receipt_path.absolute())


def validate_participant_runtime(
    config: Path,
    receipt_root: Path,
    workspace: Path,
    state: Path,
    labels,
):
    module_path = Path(__file__).with_name("validate-participant-runtime.py")
    spec = importlib.util.spec_from_file_location("agentlab_participant_runtime", module_path)
    require(spec is not None and spec.loader is not None, "participant runtime validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_runtime_receipts(
        config.absolute(),
        receipt_root.absolute(),
        workspace.absolute(),
        state.absolute(),
        labels,
    )


def validate_authenticated_review(bundle: Path, repository: str, run_id: int):
    module_path = Path(__file__).with_name("authenticate-blind-case-review.py")
    spec = importlib.util.spec_from_file_location(
        "agentlab_authenticated_blind_review_runtime", module_path
    )
    require(
        spec is not None and spec.loader is not None,
        "authenticated blind review validator is unavailable",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify_authenticated_bundle_online(
        bundle.absolute(), repository, run_id
    )


def blind_dispatch_qualification(blind_dispatch, runtime_validation, authenticated_review):
    return {
        "provided": blind_dispatch is not None,
        "interfaceInputQualified": blind_dispatch is not None,
        "participantManifestSha256": (
            blind_dispatch.get("participantManifestSha256")
            if blind_dispatch is not None
            else None
        ),
        "filesystemIsolationRequired": blind_dispatch is not None,
        "filesystemIsolationQualified": bool(
            runtime_validation
            and runtime_validation.get("filesystemIsolationQualified") is True
        ),
        "externalCredentialIsolationQualified": bool(
            runtime_validation
            and runtime_validation.get("externalCredentialIsolationQualified") is True
        ),
        "networkEgressIsolationQualified": bool(
            runtime_validation
            and runtime_validation.get("networkEgressIsolationQualified") is True
        ),
        "runtimeExecutor": runtime_validation.get("executor") if runtime_validation else None,
        "runtimeImageId": runtime_validation.get("imageId") if runtime_validation else None,
        "authenticatedReviewProvided": authenticated_review is not None,
        "reviewConsensusQualified": bool(
            authenticated_review
            and authenticated_review.get("reviewConsensusQualified") is True
        ),
        "reviewerIdentityAuthenticationQualified": bool(
            authenticated_review
            and authenticated_review.get("reviewerIdentityAuthenticationQualified") is True
        ),
        "attestedWorkflowProvenanceQualified": bool(
            authenticated_review
            and authenticated_review.get("attestedWorkflowProvenanceQualified") is True
        ),
        "semanticLeakReviewQualified": bool(
            authenticated_review
            and authenticated_review.get("semanticLeakReviewConsensusQualified") is True
            and authenticated_review.get("reviewerIdentityAuthenticationQualified") is True
        ),
        "contaminationRiskReviewQualified": bool(
            authenticated_review
            and authenticated_review.get("contaminationRiskReviewConsensusQualified") is True
            and authenticated_review.get("reviewerIdentityAuthenticationQualified") is True
        ),
        "modelTrainingExclusionQualified": bool(
            authenticated_review
            and authenticated_review.get("modelTrainingExclusionQualified") is True
        ),
        "unseenAgentDiscriminationQualified": bool(
            authenticated_review
            and authenticated_review.get("eligibleForUnseenAgentDiscrimination") is True
        ),
        "blindAssessmentQualified": bool(
            blind_dispatch
            and runtime_validation
            and runtime_validation.get("filesystemIsolationQualified") is True
            and runtime_validation.get("externalCredentialIsolationQualified") is True
            and runtime_validation.get("networkEgressIsolationQualified") is True
            and authenticated_review
            and authenticated_review.get("blindPilotReviewQualified") is True
            and authenticated_review.get("reviewerIdentityAuthenticationQualified") is True
            and authenticated_review.get("attestedWorkflowProvenanceQualified") is True
        ),
    }


def process_measurement(stage_results, duration_ms):
    oracle_outcomes = [
        row["oraclePass"]
        for row in stage_results
        if isinstance(row.get("oraclePass"), bool)
    ]
    recovery_count = sum(
        previous is False and current is True
        for previous, current in zip(oracle_outcomes, oracle_outcomes[1:])
    )
    regression_count = sum(
        previous is True and current is False
        for previous, current in zip(oracle_outcomes, oracle_outcomes[1:])
    )
    value = {
        "schema": "agentlab.assessment_process_measurement.v1",
        "stageCount": len(stage_results),
        "participantCompletedStageCount": sum(
            row.get("participantCompleted") is True for row in stage_results
        ),
        "oracleExecutedStageCount": len(oracle_outcomes),
        "oraclePassedStageCount": sum(value is True for value in oracle_outcomes),
        "scopeViolationStageCount": sum(
            row.get("scopeValid") is False for row in stage_results
        ),
        "changedPathCount": sum(row.get("changedPathCount", 0) for row in stage_results),
        "unauthorizedPathCount": sum(
            row.get("unauthorizedPathCount", 0) for row in stage_results
        ),
        "oracleRecoveryCount": recovery_count,
        "oracleRegressionCount": regression_count,
        "participantDurationMs": sum(
            row.get("participantDurationMs", 0) for row in stage_results
        ),
        "oracleDurationMs": sum(row.get("oracleDurationMs", 0) for row in stage_results),
        "stageDurationMs": sum(row.get("stageDurationMs", 0) for row in stage_results),
        "attemptDurationMs": duration_ms,
        "processMeasurementQualified": bool(stage_results),
    }
    self_assessments = [
        row.get("participantSelfAssessment")
        for row in stage_results
        if isinstance(row.get("participantSelfAssessment"), dict)
    ]
    if self_assessments:
        comparable = [
            row for row in self_assessments if isinstance(row.get("agreement"), bool)
        ]
        value["participantSelfAssessment"] = {
            "schema": "agentlab.participant_self_assessment_summary.v1",
            "stageCount": len(stage_results),
            "reportedStageCount": len(self_assessments),
            "comparableStageCount": len(comparable),
            "agreementCount": sum(row["agreement"] for row in comparable),
            "coverageRate": len(self_assessments) / len(stage_results),
            "agreementRate": (
                sum(row["agreement"] for row in comparable) / len(comparable)
                if comparable
                else None
            ),
            "meanBrierScore": (
                sum(row["brierScore"] for row in comparable) / len(comparable)
                if comparable
                else None
            ),
            "coverageQualified": len(comparable) == len(stage_results),
            "authority": "participant-claim-compared-with-operator-oracle-not-a-verdict",
        }
    dependency_rows = [
        row.get("dependencyDiscovery")
        for row in stage_results
        if isinstance(row.get("dependencyDiscovery"), dict)
    ]
    if dependency_rows:
        obligations = sum(row["obligationCount"] for row in dependency_rows)
        covered = sum(row["coveredObligationCount"] for row in dependency_rows)
        value["dependencyDiscovery"] = {
            "schema": "agentlab.dependency_discovery_summary.v1",
            "stageCount": len(stage_results),
            "measuredStageCount": len(dependency_rows),
            "claimCount": sum(row["claimCount"] for row in dependency_rows),
            "obligationCount": obligations,
            "coveredObligationCount": covered,
            "requiredObligationCoverage": covered / obligations if obligations else None,
            "coverageQualified": bool(obligations) and covered == obligations,
            "unadjudicatedClaimCount": sum(
                row["unadjudicatedClaimCount"] for row in dependency_rows
            ),
            "precisionClaimed": False,
            "authority": "hidden-revision-bound-program-fact-obligations-not-gold-path-imitation",
        }
    return value


def participant_self_assessment(response, oracle_pass):
    claim = response.get("selfAssessment")
    if claim is None:
        return None
    require(isinstance(claim, dict), "participant selfAssessment must be an object")
    require(
        set(claim) == {"expectedOraclePass", "confidence"},
        "participant selfAssessment fields differ",
    )
    expected = claim.get("expectedOraclePass")
    confidence = claim.get("confidence")
    require(isinstance(expected, bool), "participant expectedOraclePass must be boolean")
    require(
        isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
        and 0.0 <= confidence <= 1.0,
        "participant selfAssessment confidence must be in 0..1",
    )
    probability = float(confidence) if expected else 1.0 - float(confidence)
    comparable = isinstance(oracle_pass, bool)
    return {
        "schema": "agentlab.participant_self_assessment.v1",
        "expectedOraclePass": expected,
        "confidence": float(confidence),
        "predictedPassProbability": probability,
        "agreement": expected == oracle_pass if comparable else None,
        "brierScore": (probability - float(oracle_pass)) ** 2 if comparable else None,
        "authority": "participant-claim-not-a-verdict",
    }


def dependency_endpoint(value, label):
    require(isinstance(value, dict), f"{label} must be an object")
    require(set(value) == {"repositoryId", "path"}, f"{label} fields differ")
    repository_id = value.get("repositoryId")
    require(isinstance(repository_id, str) and repository_id, f"{label} repository is required")
    return {
        "repositoryId": repository_id,
        "path": safe_source_path(value.get("path")).as_posix(),
    }


def dependency_claim(value, label, *, participant):
    require(isinstance(value, dict), f"{label} must be an object")
    fields = {"relation", "source", "target"}
    if participant:
        fields.add("rationale")
    else:
        fields.add("factIds")
    require(set(value) == fields, f"{label} fields differ")
    relation = value.get("relation")
    require(isinstance(relation, str) and relation, f"{label} relation is required")
    normalized = {
        "relation": relation,
        "source": dependency_endpoint(value.get("source"), f"{label} source"),
        "target": dependency_endpoint(value.get("target"), f"{label} target"),
    }
    if participant:
        rationale = value.get("rationale")
        require(isinstance(rationale, str) and rationale.strip(), f"{label} rationale is required")
        normalized["rationale"] = rationale.strip()
    else:
        fact_ids = value.get("factIds")
        require(
            isinstance(fact_ids, list)
            and fact_ids
            and len(fact_ids) == len(set(fact_ids))
            and all(isinstance(fact_id, str) and fact_id for fact_id in fact_ids),
            f"{label} factIds are invalid",
        )
        normalized["factIds"] = sorted(fact_ids)
    return normalized


def validate_dependency_discovery(case, contract_path, facts_path):
    binding = case.get("dependencyDiscovery")
    supplied = contract_path is not None or facts_path is not None
    if binding is None:
        require(not supplied, "dependency discovery inputs are not bound by the case")
        return None
    require(contract_path is not None and facts_path is not None, "dependency contract and program facts are required")
    require(isinstance(binding, dict), "dependency discovery binding is invalid")
    require(
        binding.get("schema") == "agentlab.dependency_discovery_binding.v1",
        "dependency discovery binding schema differs",
    )
    require(
        binding.get("participantEditScopeVisible") is False,
        "dependency discovery binding must hide participant edit scope",
    )
    require(
        binding.get("precisionClaimed") is False,
        "dependency discovery binding cannot claim precision",
    )
    contract_path = contract_path.resolve()
    facts_path = facts_path.resolve()
    require(contract_path.is_file() and facts_path.is_file(), "dependency discovery evidence is absent")
    require(digest(contract_path) == binding.get("contractSha256"), "dependency contract digest differs")
    require(digest(facts_path) == binding.get("programFactsSha256"), "program facts digest differs")
    fact_rows = []
    for line_number, line in enumerate(facts_path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        require(isinstance(row, dict), f"program fact line {line_number} is invalid")
        fact_rows.append(row)
    fact_index = {row.get("id"): row for row in fact_rows if isinstance(row.get("id"), str)}
    require(len(fact_index) == len(fact_rows) and fact_index, "program fact identities are invalid")
    revisions = {
        row["id"]: row.get("revision") for row in case.get("sources", [])
    }
    contract = load(contract_path)
    require(contract.get("schema") == "agentlab.dependency_discovery_contract.v1", "dependency contract schema differs")
    require(contract.get("caseId") == case.get("id"), "dependency contract case differs")
    require(contract.get("sourceSetSha256") == case.get("sourceSetSha256"), "dependency contract source set differs")
    require(contract.get("programFactsSha256") == digest(facts_path), "dependency contract facts digest differs")
    require(contract.get("automaticPromotion") is False, "dependency contract cannot auto-promote")
    require(
        contract.get("precisionPolicy")
        == "required-obligation-recall-only-extra-claims-unadjudicated",
        "dependency contract precision policy differs",
    )
    require(
        contract.get("authority")
        == "revision-bound-program-facts-reviewed-obligation-plan",
        "dependency contract authority differs",
    )
    stages = contract.get("stages")
    require(isinstance(stages, list) and stages, "dependency contract stages are absent")
    stage_index = {}
    for stage in stages:
        require(isinstance(stage, dict) and set(stage) == {"stageId", "obligations"}, "dependency contract stage fields differ")
        stage_id = stage.get("stageId")
        require(isinstance(stage_id, str) and stage_id not in stage_index, "dependency contract stage identity is invalid")
        obligations = stage.get("obligations")
        require(isinstance(obligations, list) and obligations, f"{stage_id} dependency obligations are absent")
        normalized_obligations = []
        obligation_ids = set()
        for obligation in obligations:
            require(isinstance(obligation, dict) and set(obligation) == {"id", "acceptedClaims"}, f"{stage_id} dependency obligation fields differ")
            obligation_id = obligation.get("id")
            require(isinstance(obligation_id, str) and obligation_id and obligation_id not in obligation_ids, f"{stage_id} dependency obligation identity is invalid")
            obligation_ids.add(obligation_id)
            accepted = obligation.get("acceptedClaims")
            require(isinstance(accepted, list) and accepted, f"{obligation_id} has no accepted claims")
            normalized_claims = []
            for index, claim in enumerate(accepted):
                normalized = dependency_claim(claim, f"{obligation_id} accepted claim {index}", participant=False)
                for endpoint in (normalized["source"], normalized["target"]):
                    require(endpoint["repositoryId"] in revisions, f"{obligation_id} references unknown repository")
                for fact_id in normalized["factIds"]:
                    require(fact_id in fact_index, f"{obligation_id} references unknown program fact")
                    fact = fact_index[fact_id]
                    repository_id = fact.get("repositoryId")
                    require(repository_id in revisions, f"{fact_id} repository identity differs")
                    require(fact.get("sourceRevision") == revisions[repository_id], f"{fact_id} source revision differs")
                    require(
                        fact.get("kind") == normalized["relation"]
                        and fact.get("repositoryId")
                        == normalized["source"]["repositoryId"]
                        and fact.get("path") == normalized["source"]["path"]
                        and fact.get("targetRepositoryId")
                        == normalized["target"]["repositoryId"]
                        and fact.get("targetPath") == normalized["target"]["path"],
                        f"{fact_id} does not support the accepted dependency claim",
                    )
                normalized_claims.append(normalized)
            normalized_obligations.append({"id": obligation_id, "acceptedClaims": normalized_claims})
        stage_index[stage_id] = normalized_obligations
    require(set(stage_index) == {row.get("id") for row in case.get("stages", [])}, "dependency contract stage set differs")
    return stage_index


def participant_dependency_discovery(response, obligations):
    claims = response.get("dependencyClaims")
    if claims is None:
        claims = []
    require(isinstance(claims, list), "participant dependencyClaims must be an array")
    normalized = [
        dependency_claim(claim, f"participant dependency claim {index}", participant=True)
        for index, claim in enumerate(claims)
    ]
    identities = [
        (claim["relation"], tuple(claim["source"].items()), tuple(claim["target"].items()))
        for claim in normalized
    ]
    require(len(identities) == len(set(identities)), "participant dependency claims are duplicated")
    matches = []
    matched_claim_indexes = set()
    for obligation in obligations:
        accepted = {
            (
                claim["relation"],
                tuple(claim["source"].items()),
                tuple(claim["target"].items()),
            )
            for claim in obligation["acceptedClaims"]
        }
        indexes = [index for index, identity in enumerate(identities) if identity in accepted]
        if indexes:
            matched_claim_indexes.add(indexes[0])
        matches.append({"obligationId": obligation["id"], "covered": bool(indexes)})
    covered = sum(row["covered"] for row in matches)
    return {
        "schema": "agentlab.dependency_discovery_stage_measurement.v1",
        "claimCount": len(normalized),
        "obligationCount": len(obligations),
        "coveredObligationCount": covered,
        "requiredObligationCoverage": covered / len(obligations),
        "coverageQualified": covered == len(obligations),
        "unadjudicatedClaimCount": len(normalized) - len(matched_claim_indexes),
        "obligations": matches,
        "participantClaims": normalized,
        "precisionClaimed": False,
        "authority": "hidden-revision-bound-program-fact-obligations-not-gold-path-imitation",
    }


def git(root: Path, *arguments: str, text=False):
    result = subprocess.run(
        ["git", "-C", str(root), *arguments], capture_output=True, text=text
    )
    require(result.returncode == 0, f"git {' '.join(arguments)} failed")
    return result.stdout


def safe_source_path(value: str):
    require(isinstance(value, str) and value, "source path is required")
    path = PurePosixPath(value)
    require(not path.is_absolute() and ".." not in path.parts, "unsafe Git path")
    return path


def materialize_repository(root: Path, revision: str, target: Path):
    raw = git(root, "ls-tree", "-rz", revision)
    entries = [item for item in raw.split(b"\0") if item]
    require(entries, "pinned repository has no files")
    for entry in entries:
        metadata, separator, encoded_path = entry.partition(b"\t")
        fields = metadata.split()
        require(separator and len(fields) == 3, "malformed Git tree entry")
        mode, object_type, _object_id = fields
        require(
            object_type == b"blob", "pinned repository contains a non-blob entry"
        )
        require(
            mode in {b"100644", b"100755"},
            "pinned repository contains an unsupported file mode",
        )
        value = encoded_path.decode("utf-8")
        relative = safe_source_path(value)
        body = git(root, "show", f"{revision}:{value}")
        destination = target.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        destination.chmod(0o755 if mode == b"100755" else 0o644)


def tree_state(root: Path):
    rows = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rows[path.relative_to(root).as_posix()] = {
            "sha256": digest(path),
            "byteLength": path.stat().st_size,
            "unixMode": stat.S_IMODE(path.stat().st_mode),
        }
    return rows


def tree_digest(state):
    canonical = json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
    return digest_bytes(canonical)


class ParticipantProtocol:
    def __init__(
        self,
        participant: Path,
        workspace: Path,
        evidence: Path,
        case_input: Path | None = None,
        runtime_config: Path | None = None,
        runtime_receipts: Path | None = None,
    ):
        environment = {
            key: os.environ[key]
            for key in (
                "PATH",
                "LANG",
                "LC_ALL",
                "TMPDIR",
                "AGENTLAB_LM_GATEWAY_URL",
                "AGENTLAB_LM_GATEWAY_KEY",
                "AGENTLAB_MODEL",
                "AGENTLAB_PROVIDER_ROUTE",
                "AGENTLAB_PI_BINARY",
                "AGENTLAB_MOCK_ASSESSED_PROFILE",
            )
            if key in os.environ
        }
        environment["AGENTLAB_ASSESSMENT_EVIDENCE"] = str(evidence)
        if case_input is not None:
            environment["AGENTLAB_CASE_INPUT_ROOT"] = str(case_input)
        if runtime_config is not None:
            require(runtime_receipts is not None, "runtime receipt root is required")
            environment["AGENTLAB_PARTICIPANT_RUNTIME_CONFIG"] = str(runtime_config)
            environment["AGENTLAB_PARTICIPANT_RUNTIME_RECEIPT_ROOT"] = str(runtime_receipts)
            environment["DOCKER_CONFIG"] = os.environ.get(
                "DOCKER_CONFIG", str(Path.home() / ".docker")
            )
            for key in ("DOCKER_HOST", "DOCKER_CONTEXT"):
                if key in os.environ:
                    environment[key] = os.environ[key]
        self.stderr = (evidence / "participant-stderr.log").open("wb")
        self.process = subprocess.Popen(
            [sys.executable, str(participant.resolve()), "--protocol"],
            cwd=workspace,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.stderr,
            text=True,
            start_new_session=True,
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.transcript = []

    def request(self, value, timeout=480):
        require(self.process.poll() is None, "participant protocol exited")
        self.transcript.append({"direction": "request", "value": value})
        self.process.stdin.write(json.dumps(value, sort_keys=True) + "\n")
        self.process.stdin.flush()
        events = self.selector.select(timeout)
        if not events:
            os.killpg(self.process.pid, signal.SIGTERM)
            raise TimeoutError("participant protocol timed out")
        line = self.process.stdout.readline()
        require(line, "participant protocol closed without response")
        response = json.loads(line)
        require(isinstance(response, dict), "participant response must be an object")
        self.transcript.append({"direction": "response", "value": response})
        return response

    def close(self):
        if self.process.poll() is None:
            try:
                self.request({"action": "close"}, timeout=30)
            except Exception:
                os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()
        self.selector.close()
        self.stderr.close()
        return self.process.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--participant", type=Path, required=True)
    parser.add_argument("--participant-id", required=True)
    parser.add_argument("--blind-participant-root", type=Path)
    parser.add_argument("--blind-dispatch-receipt", type=Path)
    parser.add_argument("--participant-runtime-config", type=Path)
    parser.add_argument("--authenticated-review-bundle", type=Path)
    parser.add_argument("--authenticated-review-repository")
    parser.add_argument("--authenticated-review-run-id", type=int)
    parser.add_argument("--dependency-contract", type=Path)
    parser.add_argument("--program-facts", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    require(not args.output.exists(), "refusing to overwrite assessment evidence")
    case = load(args.case)
    manifest = load(args.manifest)
    require(case.get("schema") == "agentlab.multi_repo_evaluation_case.v1", "unsupported case schema")
    require(case.get("status") == "frozen-calibrated", "case is not frozen and calibrated")
    require(case.get("automaticPromotion") is False, "case must not auto-promote")
    source_set = case.get("sourceSetSha256")
    require(isinstance(source_set, str) and SHA256.fullmatch(source_set), "case source set is invalid")
    dependency_stages = validate_dependency_discovery(
        case, args.dependency_contract, args.program_facts
    )
    require(manifest.get("schema") == "agentlab.multi_repo_manifest.v1", "unsupported manifest schema")
    oracle = args.oracle.resolve()
    require(oracle.is_file() and digest(oracle) == (case.get("oracle") or {}).get("sha256"), "Oracle digest mismatch")
    participant = args.participant.resolve()
    require(participant.is_file(), "participant adapter is absent")
    require(
        (args.blind_participant_root is None) == (args.blind_dispatch_receipt is None),
        "blind participant root and dispatch receipt must be supplied together",
    )
    blind_dispatch = None
    blind_participant_root = None
    if args.blind_participant_root is not None:
        blind_participant_root = args.blind_participant_root.absolute()
        blind_dispatch = validate_blind_dispatch(
            blind_participant_root, args.blind_dispatch_receipt.absolute()
        )
        require(blind_dispatch.get("caseId") == case.get("id"), "blind dispatch case identity differs")
        require(blind_dispatch.get("sourceSetSha256") == source_set, "blind dispatch source set differs")
    review_arguments = (
        args.authenticated_review_bundle,
        args.authenticated_review_repository,
        args.authenticated_review_run_id,
    )
    require(
        all(value is None for value in review_arguments)
        or all(value is not None for value in review_arguments),
        "authenticated review bundle, repository and run id must be supplied together",
    )
    authenticated_review = None
    if args.authenticated_review_bundle is not None:
        require(blind_dispatch is not None, "authenticated review requires a blind dispatch")
        authenticated_review = validate_authenticated_review(
            args.authenticated_review_bundle,
            args.authenticated_review_repository,
            args.authenticated_review_run_id,
        )
        require(authenticated_review.get("caseId") == case.get("id"), "authenticated review case identity differs")
        require(authenticated_review.get("sourceSetSha256") == source_set, "authenticated review source set differs")
        require(
            authenticated_review.get("participantManifestSha256")
            == blind_dispatch.get("participantManifestSha256"),
            "authenticated review participant manifest differs",
        )
    if args.participant_runtime_config is not None:
        require(blind_dispatch is not None, "isolated participant runtime requires a blind dispatch")
        require(args.participant_runtime_config.resolve().is_file(), "participant runtime config is absent")

    case_sources = {row["id"]: row for row in case.get("sources", [])}
    manifest_sources = {row["id"]: row for row in manifest.get("repositories", [])}
    require(set(case_sources) == set(manifest_sources) and len(case_sources) >= 2, "case and manifest source ids differ")
    for repository_id, source in case_sources.items():
        manifest_source = manifest_sources[repository_id]
        require(
            source.get("repository") == manifest_source.get("repository")
            and source.get("revision") == manifest_source.get("revision"),
            f"source identity mismatch for {repository_id}",
        )
        require(REVISION.fullmatch(source["revision"]), "source revision must be exact")

    allowed = {
        f"{row['repositoryId']}/{safe_source_path(row['path']).as_posix()}"
        for row in case.get("allowedEdits", [])
    }
    require(allowed, "case has no allowed edit surface")
    stages = case.get("stages")
    require(isinstance(stages, list) and len(stages) >= 2, "case requires staged demands")

    args.output.mkdir(parents=True)
    if authenticated_review is not None:
        write_json(
            args.output / "authenticated-review-validation.json",
            authenticated_review,
        )
    workspace = args.output / "workspace"
    evidence = args.output / "participant-evidence"
    oracle_evidence = args.output / "oracle"
    workspace.mkdir()
    evidence.mkdir()
    oracle_evidence.mkdir()
    runtime_receipts = evidence / "runtime-isolation"
    if args.participant_runtime_config is not None:
        runtime_receipts.mkdir()
    for repository_id, source in sorted(manifest_sources.items()):
        materialize_repository(
            Path(source["root"]), source["revision"], workspace / repository_id
        )

    initial_state = tree_state(workspace)
    write_json(args.output / "initial-source-state.json", initial_state)
    protocol = ParticipantProtocol(
        participant,
        workspace,
        evidence,
        blind_participant_root,
        args.participant_runtime_config.resolve() if args.participant_runtime_config else None,
        runtime_receipts if args.participant_runtime_config else None,
    )
    stage_results = []
    infrastructure_errors = []
    cumulative_checks = []
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    try:
        for stage in stages:
            stage_started = time.monotonic()
            stage_id = stage.get("id")
            demand = stage.get("demand")
            check_ids = stage.get("checkIds")
            require(isinstance(stage_id, str) and stage_id, "stage id is required")
            require(isinstance(demand, str) and demand, "stage demand is required")
            require(isinstance(check_ids, list) and check_ids, "stage checks are required")
            cumulative_checks.extend(check_ids)
            request_path = evidence / f"{stage_id}-request.json"
            participant_request = {
                    "schema": (
                        "agentlab.multi_repo_assessed_stage_request.v2"
                        if dependency_stages is not None
                        else "agentlab.multi_repo_assessed_stage_request.v1"
                    ),
                    "caseId": case["id"],
                    "title": case["title"],
                    "stageId": stage_id,
                    "demand": demand,
                    "sourceSetSha256": source_set,
                    "repositories": sorted(case_sources),
                    "priorStageCount": len(stage_results),
                    "oracleVisibleToParticipant": False,
                    "blindParticipantManifestSha256": (
                        blind_dispatch.get("participantManifestSha256")
                        if blind_dispatch is not None
                        else None
                    ),
                    "editScopeVisibleToParticipant": dependency_stages is None,
                }
            if dependency_stages is None:
                participant_request["allowedEdits"] = sorted(allowed)
            write_json(request_path, participant_request)
            before = tree_state(workspace)
            participant_ok = False
            participant_error = None
            participant_started = time.monotonic()
            try:
                response = protocol.request(
                    {
                        "action": "stage",
                        "stageId": stage_id,
                        "requestPath": str(request_path),
                        "workspace": str(workspace),
                    }
                )
                participant_ok = response.get("ok") is True and response.get("stageId") == stage_id
                if not participant_ok:
                    participant_error = response.get("error") or "participant rejected stage"
            except Exception as error:
                participant_error = f"{type(error).__name__}: {error}"
            participant_duration_ms = round(
                (time.monotonic() - participant_started) * 1000
            )
            after = tree_state(workspace)
            changed = sorted(set(before) | set(after))
            changed = [path for path in changed if before.get(path) != after.get(path)]
            unauthorized = sorted(set(changed) - allowed)

            stdout_path = oracle_evidence / f"{stage_id}.stdout.json"
            stderr_path = oracle_evidence / f"{stage_id}.stderr.log"
            oracle_receipt = None
            oracle_error = None
            oracle_duration_ms = 0
            if participant_ok:
                oracle_started = time.monotonic()
                completed = subprocess.run(
                    ["node", "--experimental-vm-modules", str(oracle), str(workspace), stage_id],
                    capture_output=True,
                )
                oracle_duration_ms = round(
                    (time.monotonic() - oracle_started) * 1000
                )
                stdout_path.write_bytes(completed.stdout)
                stderr_path.write_bytes(completed.stderr)
                try:
                    require(completed.returncode == 0, "Oracle process failed")
                    oracle_receipt = json.loads(completed.stdout)
                    require(oracle_receipt.get("schema") == (case.get("oracle") or {}).get("receiptSchema"), "Oracle receipt schema mismatch")
                    require(oracle_receipt.get("stage") == stage_id, "Oracle stage mismatch")
                    checks = oracle_receipt.get("checks")
                    require(isinstance(checks, list), "Oracle checks are absent")
                    actual_ids = [row.get("id") for row in checks]
                    require(actual_ids == cumulative_checks, "Oracle checks differ from frozen case")
                    require(oracle_receipt.get("pass") is all(row.get("pass") is True for row in checks), "Oracle aggregate verdict mismatch")
                    claimed = oracle_receipt.get("receiptSha256")
                    unsigned = dict(oracle_receipt)
                    unsigned.pop("receiptSha256", None)
                    canonical = json.dumps(unsigned, separators=(",", ":")).encode()
                    require(claimed == digest_bytes(canonical), "Oracle receipt digest mismatch")
                except Exception as error:
                    oracle_error = f"{type(error).__name__}: {error}"
            else:
                stdout_path.write_bytes(b"")
                stderr_path.write_text(participant_error or "participant failed")

            if participant_error:
                infrastructure_errors.append(
                    {"stageId": stage_id, "source": "participant", "error": participant_error}
                )
            if oracle_error:
                infrastructure_errors.append(
                    {"stageId": stage_id, "source": "oracle", "error": oracle_error}
                )
            stage_duration_ms = round((time.monotonic() - stage_started) * 1000)
            stage_results.append(
                {
                    "stageId": stage_id,
                    "participantCompleted": participant_ok,
                    "changedPaths": changed,
                    "changedPathCount": len(changed),
                    "unauthorizedPaths": unauthorized,
                    "unauthorizedPathCount": len(unauthorized),
                    "scopeValid": not unauthorized,
                    "oraclePass": oracle_receipt.get("pass") if oracle_receipt and not oracle_error else None,
                    "oracleReceiptSha256": digest(stdout_path) if stdout_path.stat().st_size else None,
                    "workspaceSha256": tree_digest(after),
                    "participantDurationMs": participant_duration_ms,
                    "oracleDurationMs": oracle_duration_ms,
                    "stageDurationMs": stage_duration_ms,
                    "cumulativeCheckCount": len(cumulative_checks),
                    "participantSelfAssessment": participant_self_assessment(
                        response if participant_ok else {},
                        oracle_receipt.get("pass")
                        if oracle_receipt and not oracle_error
                        else None,
                    ),
                    "dependencyDiscovery": (
                        participant_dependency_discovery(
                            response if participant_ok else {},
                            dependency_stages[stage_id],
                        )
                        if dependency_stages is not None
                        else None
                    ),
                }
            )
            if participant_error or oracle_error:
                break
    finally:
        participant_exit = protocol.close()
        write_json(args.output / "participant-protocol.json", protocol.transcript)

    runtime_validation = None
    if args.participant_runtime_config is not None:
        try:
            runtime_validation = validate_participant_runtime(
                args.participant_runtime_config,
                runtime_receipts,
                workspace,
                args.output / "participant-state",
                [row["stageId"] for row in stage_results],
            )
            write_json(args.output / "participant-runtime-validation.json", runtime_validation)
        except Exception as error:
            infrastructure_errors.append(
                {"stageId": None, "source": "participant-runtime-isolation", "error": f"{type(error).__name__}: {error}"}
            )

    if participant_exit not in (0, None) and not infrastructure_errors:
        infrastructure_errors.append(
            {"stageId": None, "source": "participant", "error": f"protocol exited {participant_exit}"}
        )
    assessed = not infrastructure_errors and len(stage_results) == len(stages)
    succeeded = (
        all(row["scopeValid"] and row["oraclePass"] is True for row in stage_results)
        if assessed
        else None
    )
    final_state = tree_state(workspace)
    ended_at = datetime.now(timezone.utc).isoformat()
    duration_ms = round((time.monotonic() - started) * 1000)
    process = process_measurement(stage_results, duration_ms)
    summary = {
        "schema": "agentlab.multi_repo_assessment_summary.v1",
        "taskId": case["id"],
        "sourceSetSha256": source_set,
        "participantId": args.participant_id,
        "assessmentStatus": "assessed" if assessed else "infrastructure-unavailable",
        "infrastructureAvailable": assessed,
        "subjectTaskSucceeded": succeeded,
        "stages": stage_results,
        "initialWorkspaceSha256": tree_digest(initial_state),
        "finalWorkspaceSha256": tree_digest(final_state),
        "startedAt": started_at,
        "endedAt": ended_at,
        "durationMs": duration_ms,
        "processMeasurement": process,
        "blindDispatch": blind_dispatch_qualification(
            blind_dispatch,
            runtime_validation,
            authenticated_review,
        ),
        "assessmentBoundary": "Exact committed source materialized without Git metadata and evaluated by the frozen VM-module Oracle; no Harmony build, UI, emulator or performance claim.",
    }
    decision = {
        "schema": "agentlab.harness_decision_package.v1",
        "taskId": case["id"],
        "sourceSetSha256": source_set,
        "participantId": args.participant_id,
        "assessmentStatus": summary["assessmentStatus"],
        "infrastructureAvailable": assessed,
        "subjectTaskSucceeded": succeeded,
        "phaseVerdicts": stage_results,
        "processMeasurement": process,
        "launchErrors": infrastructure_errors,
        "blindDispatch": summary["blindDispatch"],
        "automaticPromotion": False,
        "harnessPolicy": "Participant edits are evidence; only the operator-owned frozen Oracle and scope gate decide the attempt verdict.",
    }
    write_json(args.output / "final-source-state.json", final_state)
    write_json(args.output / "summary.json", summary)
    write_json(args.output / "decision-package.json", decision)
    print(json.dumps({"assessmentStatus": summary["assessmentStatus"], "ok": assessed, "subjectTaskSucceeded": succeeded}, sort_keys=True))
    return 0 if assessed else 2


if __name__ == "__main__":
    raise SystemExit(main())
