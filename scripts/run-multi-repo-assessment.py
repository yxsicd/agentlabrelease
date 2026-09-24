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
            stage_id = stage.get("id")
            demand = stage.get("demand")
            check_ids = stage.get("checkIds")
            require(isinstance(stage_id, str) and stage_id, "stage id is required")
            require(isinstance(demand, str) and demand, "stage demand is required")
            require(isinstance(check_ids, list) and check_ids, "stage checks are required")
            cumulative_checks.extend(check_ids)
            request_path = evidence / f"{stage_id}-request.json"
            write_json(
                request_path,
                {
                    "schema": "agentlab.multi_repo_assessed_stage_request.v1",
                    "caseId": case["id"],
                    "title": case["title"],
                    "stageId": stage_id,
                    "demand": demand,
                    "sourceSetSha256": source_set,
                    "repositories": sorted(case_sources),
                    "allowedEdits": sorted(allowed),
                    "priorStageCount": len(stage_results),
                    "oracleVisibleToParticipant": False,
                    "blindParticipantManifestSha256": (
                        blind_dispatch.get("participantManifestSha256")
                        if blind_dispatch is not None
                        else None
                    ),
                },
            )
            before = tree_state(workspace)
            participant_ok = False
            participant_error = None
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
            after = tree_state(workspace)
            changed = sorted(set(before) | set(after))
            changed = [path for path in changed if before.get(path) != after.get(path)]
            unauthorized = sorted(set(changed) - allowed)

            stdout_path = oracle_evidence / f"{stage_id}.stdout.json"
            stderr_path = oracle_evidence / f"{stage_id}.stderr.log"
            oracle_receipt = None
            oracle_error = None
            if participant_ok:
                completed = subprocess.run(
                    ["node", "--experimental-vm-modules", str(oracle), str(workspace), stage_id],
                    capture_output=True,
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
            stage_results.append(
                {
                    "stageId": stage_id,
                    "participantCompleted": participant_ok,
                    "changedPaths": changed,
                    "unauthorizedPaths": unauthorized,
                    "scopeValid": not unauthorized,
                    "oraclePass": oracle_receipt.get("pass") if oracle_receipt and not oracle_error else None,
                    "oracleReceiptSha256": digest(stdout_path) if stdout_path.stat().st_size else None,
                    "workspaceSha256": tree_digest(after),
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
        "blindDispatch": {
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
            "blindAssessmentQualified": False,
        },
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
