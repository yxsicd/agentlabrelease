#!/usr/bin/env python3
"""Run a bound Harmony Instrument Test and emit a conservative Hypium receipt."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any


RECEIPT_SCHEMA = "agentlab.harmony_standard_test_execution_receipt.v1"
REPORT_SCHEMA = "agentlab.harmony_hypium_native_report.v1"
FRAMEWORK = "instrument-test-ohosTest-hypium"
TOKEN = re.compile(r"[A-Za-z0-9_.:@/+\-]{1,200}")
CLASS_FILTER = re.compile(r"[A-Za-z0-9_.#,]{1,1000}")
SUMMARY = re.compile(
    r"OHOS_REPORT_RESULT:\s*stream=Tests run:\s*(\d+),\s*Failure:\s*(\d+),"
    r"\s*Error:\s*(\d+),\s*Pass:\s*(\d+),\s*Ignore:\s*(\d+)"
)
FINAL_CODE = re.compile(r"OHOS_REPORT_CODE:\s*(-?\d+)")
ALL_SUMMARY = re.compile(
    r"OHOS_REPORT_ALL_RESULT:\s*stream=Test run:\s*runTimes:\s*\d+,\s*total:\s*(\d+),"
    r"\s*Failure:\s*(\d+),\s*Error:\s*(\d+),\s*Pass:\s*(\d+),\s*Ignore:\s*(\d+)"
)
ALL_FINAL_CODE = re.compile(r"OHOS_REPORT_ALL_CODE:\s*(-?\d+)")


class InstrumentTestError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise InstrumentTestError(message)


def sha256(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), f"artifact must be a regular file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path: Path, display_path: str | None = None) -> dict[str, Any]:
    return {
        "path": display_path or path.name,
        "sha256": sha256(path),
        "byteLength": path.stat().st_size,
    }


def load_contract_module():
    path = Path(__file__).with_name("harmony-standard-test-contract.py")
    spec = importlib.util.spec_from_file_location("agentlab_harmony_standard_test_contract", path)
    require(spec is not None and spec.loader is not None, "cannot load Harmony standard test contract")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(command: list[str], timeout: int) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timedOut": False,
            "startedAt": started.isoformat(),
            "finishedAt": datetime.now(timezone.utc).isoformat(),
        }
    except subprocess.TimeoutExpired as error:
        return {
            "command": command,
            "exitCode": None,
            "stdout": error.stdout if isinstance(error.stdout, str) else "",
            "stderr": error.stderr if isinstance(error.stderr, str) else "",
            "timedOut": True,
            "startedAt": started.isoformat(),
            "finishedAt": datetime.now(timezone.utc).isoformat(),
        }


def parse_native_report(stdout: str, stderr: str, exit_code: int | None, timed_out: bool) -> dict[str, Any]:
    combined = stdout + "\n" + stderr
    aggregate_summaries = ALL_SUMMARY.findall(combined)
    summaries = aggregate_summaries or SUMMARY.findall(combined)
    aggregate_codes = ALL_FINAL_CODE.findall(combined)
    codes = aggregate_codes or FINAL_CODE.findall(combined)
    reasons: list[str] = []
    counts = None
    final_code = int(codes[-1]) if codes else None
    if timed_out:
        reasons.append("aa-test-timeout")
    if exit_code != 0:
        reasons.append("aa-test-process-nonzero")
    if not summaries:
        reasons.append("native-final-summary-absent")
    else:
        total, failure, error, passed, ignored = map(int, summaries[-1])
        counts = {
            "total": total,
            "failure": failure,
            "error": error,
            "pass": passed,
            "ignore": ignored,
        }
        if total <= 0:
            reasons.append("no-tests-executed")
        if failure != 0:
            reasons.append("test-failures-present")
        if error != 0:
            reasons.append("test-errors-present")
        if passed <= 0:
            reasons.append("no-tests-passed")
        if total != failure + error + passed + ignored:
            reasons.append("native-summary-counts-inconsistent")
    if final_code is None:
        reasons.append("native-final-code-absent")
    elif final_code != 0:
        reasons.append("native-final-code-nonzero")
    return {
        "schema": REPORT_SCHEMA,
        "parserAuthority": {
            "implementation": "OpenHarmony/testfwk_arkxtest",
            "markers": [
                "OHOS_REPORT_RESULT/OHOS_REPORT_CODE",
                "OHOS_REPORT_ALL_RESULT/OHOS_REPORT_ALL_CODE",
            ],
            "policy": "process-zero-and-nonempty-consistent-zero-failure-summary-and-native-code-zero",
        },
        "processExitCode": exit_code,
        "timedOut": timed_out,
        "counts": counts,
        "nativeFinalCode": final_code,
        "passed": not reasons,
        "failureReasons": reasons,
    }


def validate_token(value: str, label: str, pattern: re.Pattern[str] = TOKEN) -> str:
    require(pattern.fullmatch(value) is not None, f"{label} is invalid")
    return value


def execute(
    args: argparse.Namespace,
    contract_override: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Path]:
    require(not args.output_dir.exists(), f"refusing to overwrite output directory: {args.output_dir}")
    validate_token(args.target, "HDC target")
    validate_token(args.bundle, "bundle")
    validate_token(args.module, "test module")
    validate_token(args.runner, "test runner")
    if args.test_class:
        validate_token(args.test_class, "test class filter", CLASS_FILTER)
    require(1 <= args.timeout_seconds <= 3600, "timeout must be between 1 and 3600 seconds")
    require(1000 <= args.case_timeout_ms <= 3_600_000, "case timeout must be between 1000 and 3600000 ms")
    for hap in (args.app_hap, args.test_hap):
        require(hap.suffix == ".hap", f"Harmony package must use .hap: {hap}")
        sha256(hap)

    contract_module = load_contract_module()
    contract = contract_override or contract_module.build_contract(
        args.project_root,
        args.case_id,
        args.source_set_sha256,
    )
    require(
        contract.get("schema") == contract_module.SCHEMA
        and contract.get("caseId") == args.case_id
        and contract.get("sourceSetSha256") == args.source_set_sha256,
        "prevalidated Harmony standard test contract identity differs",
    )
    lane = next(
        (
            item for item in contract["standardTestLanes"]
            if item.get("framework") == FRAMEWORK
            and item.get("sourceContractQualified") is True
            and item.get("deviceCapable") is True
        ),
        None,
    )
    require(lane is not None, "project lacks a qualified ohosTest/Hypium Instrument Test source contract")

    hdc = Path(args.hdc)
    if hdc.parent == Path("."):
        resolved = shutil.which(args.hdc)
        require(resolved is not None, f"HDC executable was not found: {args.hdc}")
        hdc = Path(resolved)
    hdc = hdc.resolve(strict=True)
    require(hdc.is_file() and not hdc.is_symlink(), "HDC executable must be a regular non-symlink file")

    args.output_dir.mkdir(parents=True)
    logs_dir = args.output_dir / "logs"
    logs_dir.mkdir()
    commands: list[dict[str, Any]] = []
    preflight = run([str(hdc), "list", "targets"], min(args.timeout_seconds, 30))
    commands.append(preflight)
    listed_targets = {line.strip().split()[0] for line in preflight["stdout"].splitlines() if line.strip()}
    preflight_ok = not preflight["timedOut"] and preflight["exitCode"] == 0 and args.target in listed_targets

    install_ok = preflight_ok
    if preflight_ok:
        for hap in (args.app_hap, args.test_hap):
            result = run(
                [str(hdc), "-t", args.target, "install", "-r", str(hap.resolve(strict=True))],
                args.timeout_seconds,
            )
            commands.append(result)
            install_ok = install_ok and not result["timedOut"] and result["exitCode"] == 0
            if not install_ok:
                break

    test_command = [
        str(hdc), "-t", args.target, "shell", "aa", "test",
        "-b", args.bundle, "-m", args.module,
        "-s", "unittest", args.runner,
        "-s", "timeout", str(args.case_timeout_ms),
    ]
    if args.test_class:
        test_command += ["-s", "class", args.test_class]
    test_result = None
    if install_ok:
        test_result = run(test_command, args.timeout_seconds)
        commands.append(test_result)

    for index, result in enumerate(commands, start=1):
        (logs_dir / f"{index:02d}.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    if not preflight_ok:
        report = {
            "schema": REPORT_SCHEMA,
            "parserAuthority": None,
            "processExitCode": preflight["exitCode"],
            "timedOut": preflight["timedOut"],
            "counts": None,
            "nativeFinalCode": None,
            "passed": False,
            "failureReasons": ["target-preflight-failed"],
        }
        status = "infrastructure-error"
    elif not install_ok:
        failed_install = commands[-1]
        report = {
            "schema": REPORT_SCHEMA,
            "parserAuthority": None,
            "processExitCode": failed_install["exitCode"],
            "timedOut": failed_install["timedOut"],
            "counts": None,
            "nativeFinalCode": None,
            "passed": False,
            "failureReasons": ["hap-install-failed"],
        }
        status = "infrastructure-error"
    else:
        assert test_result is not None
        report = parse_native_report(
            test_result["stdout"], test_result["stderr"], test_result["exitCode"], test_result["timedOut"]
        )
        status = "passed" if report["passed"] else "failed"

    report_path = args.output_dir / "native-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "caseId": args.case_id,
        "sourceSetSha256": args.source_set_sha256,
        "projectTreeSha256": contract["projectTreeSha256"],
        "framework": FRAMEWORK,
        "status": status,
        "passed": report["passed"],
        "command": test_command,
        "target": args.target,
        "bundle": args.bundle,
        "module": args.module,
        "runner": args.runner,
        "testClass": args.test_class,
        "hdc": binding(hdc, str(hdc)),
        "packages": {
            "app": binding(args.app_hap.resolve(strict=True), args.app_hap.name),
            "test": binding(args.test_hap.resolve(strict=True), args.test_hap.name),
        },
        "report": binding(report_path, "native-report.json"),
        "logs": [binding(path, f"logs/{path.name}") for path in sorted(logs_dir.iterdir())],
        "startedAt": commands[0]["startedAt"],
        "finishedAt": commands[-1]["finishedAt"],
        "automaticPromotion": False,
    }
    receipt_path = args.output_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt, receipt_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--source-set-sha256", required=True)
    parser.add_argument("--hdc", default="hdc")
    parser.add_argument("--target", required=True)
    parser.add_argument("--app-hap", type=Path, required=True)
    parser.add_argument("--test-hap", type=Path, required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--module", required=True)
    parser.add_argument("--runner", default="OpenHarmonyTestRunner")
    parser.add_argument("--test-class")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--case-timeout-ms", type=int, default=15000)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt, receipt_path = execute(args)
        print(json.dumps({"ok": receipt["passed"], "status": receipt["status"], "receipt": str(receipt_path)}, sort_keys=True))
        return 0 if receipt["passed"] else 1
    except (InstrumentTestError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Harmony Instrument Test invalid: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
