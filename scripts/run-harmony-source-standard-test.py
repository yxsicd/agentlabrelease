#!/usr/bin/env python3
"""Build and run one source-bound Harmony ohosTest/Hypium Instrument Test."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time
from typing import Any


RECEIPT_SCHEMA = "agentlab.harmony_source_standard_test_receipt.v1"
BUILD_SCHEMA = "agentlab.harmony_standard_test_source_build_receipt.v1"
FRAMEWORK = "instrument-test-ohosTest-hypium"
TOKEN = re.compile(r"[A-Za-z0-9_.:@/+\-]{1,200}")


class SourceStandardTestError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise SourceStandardTestError(message)


def load_program(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    require(spec is not None and spec.loader is not None, f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), f"artifact must be a regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def binding(path: Path, display_path: str) -> dict[str, Any]:
    return {
        "path": display_path,
        "sha256": sha256(path),
        "byteLength": path.stat().st_size,
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_relative(value: str, label: str) -> PurePosixPath:
    path = PurePosixPath(value)
    require(
        value and not path.is_absolute() and ".." not in path.parts and str(path) != ".",
        f"{label} must stay within the project",
    )
    return path


def child(root: Path, relative: PurePosixPath) -> Path:
    return root.joinpath(*relative.parts)


def validate_token(value: str, label: str) -> str:
    require(TOKEN.fullmatch(value) is not None, f"{label} is invalid")
    return value


def source_snapshot(root: Path, files: list[Path]) -> dict[str, dict[str, Any]]:
    return {
        path.relative_to(root).as_posix(): {
            "sha256": sha256(path),
            "byteLength": path.stat().st_size,
        }
        for path in files
    }


def verify_source_snapshot(root: Path, snapshot: dict[str, dict[str, Any]]) -> None:
    for relative, expected in snapshot.items():
        path = root.joinpath(*PurePosixPath(relative).parts)
        require(path.is_file() and not path.is_symlink(), f"build removed or replaced source file: {relative}")
        require(
            path.stat().st_size == expected["byteLength"] and sha256(path) == expected["sha256"],
            f"build modified pre-existing source file: {relative}",
        )


def run_build(command: list[str], cwd: Path, timeout: int) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "exitCode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
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


def execute(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    root = args.project_root.resolve(strict=True)
    require(root.is_dir() and not root.is_symlink(), "project root must be a regular directory")
    output = args.output_dir.resolve()
    require(not output.exists(), f"refusing to overwrite output directory: {output}")
    require(root not in output.parents and output != root, "output directory must be outside the project")
    require(output not in root.parents, "project root must not be inside the output directory")
    require(1 <= args.build_timeout_seconds <= 3600, "build timeout must be between 1 and 3600 seconds")
    for value, label in (
        (args.build_module, "build module"),
        (args.product, "product"),
        (args.build_mode, "build mode"),
    ):
        validate_token(value, label)

    app_relative = safe_relative(args.app_hap, "app HAP path")
    test_relative = safe_relative(args.test_hap, "test HAP path")
    hvigorw = args.hvigorw.resolve(strict=True)
    require(
        hvigorw.is_file() and not hvigorw.is_symlink() and os.access(hvigorw, os.X_OK),
        "hvigorw must be an executable regular non-symlink file",
    )

    contract_module = load_program(
        "harmony-standard-test-contract.py", "agentlab_source_standard_contract"
    )
    runner_module = load_program(
        "run-harmony-instrument-test.py", "agentlab_source_standard_runner"
    )
    files = contract_module.project_files(root)
    snapshot = source_snapshot(root, files)
    contract = contract_module.build_contract(root, args.case_id, args.source_set_sha256)
    lane = next(
        (
            row for row in contract["standardTestLanes"]
            if row.get("framework") == FRAMEWORK
            and row.get("sourceContractQualified") is True
            and row.get("deviceCapable") is True
        ),
        None,
    )
    require(lane is not None, "project lacks a qualified ohosTest/Hypium Instrument Test source contract")

    output.mkdir(parents=True)
    source_contract_path = output / "source-contract.json"
    write_json(source_contract_path, contract)
    planner = args.build_planner.resolve(strict=True)
    require(planner.is_file() and not planner.is_symlink() and os.access(planner, os.X_OK),
            "build planner must be an executable regular file")
    plan_path = output / "build-plan.json"
    plan_result = run_build([
        str(planner), "--prepare-harmony-build-plan", "--project-root", str(root),
        "--build-module", args.build_module, "--host-module", args.host_module or args.build_module,
        "--product", args.product, "--build-mode", args.build_mode,
        "--output", str(plan_path),
    ], root, min(args.build_timeout_seconds, 30))
    write_json(output / "build-plan-command.json", plan_result)
    require(not plan_result["timedOut"] and plan_result["exitCode"] == 0,
            "source-bound build planning failed; inspect build-plan-command.json")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    require(plan.get("schema") == "agentlab.harmony_standard_test_build_plan.v1"
            and plan.get("module") == args.build_module
            and plan.get("hostModule") == (args.host_module or args.build_module)
            and plan.get("product") == args.product and plan.get("buildMode") == args.build_mode
            and plan.get("automaticPromotion") is False and plan.get("runtimeQualified") is False,
            "build plan identity differs")
    task = "assembleHap" if plan.get("outputType") == "hap" else "genOnDeviceTestHap"
    require(plan.get("outputType") in {"hap", "har", "hsp"}, "unsupported planned output type")
    expected_steps = [
        {"module": plan["hostModule"], "target": "default", "task": "assembleHap"},
        {"module": args.build_module, "target": "ohosTest", "task": task},
    ]
    require(plan.get("commands") == expected_steps, "planned build commands differ")
    module_relative = safe_relative(plan["modulePath"], "planned module")
    selected_files = [path for path in files
                      if PurePosixPath(path.relative_to(root).as_posix()).is_relative_to(module_relative)
                      or path == root / "oh-package.json5"]
    require(any(item.get("framework") == FRAMEWORK and item.get("sourceContractQualified") is True
                for item in contract_module.inspect_lanes(root, selected_files)),
            "selected module lacks a qualified ohosTest/Hypium source contract")
    require(isinstance(plan.get("sourceBindings"), list) and plan["sourceBindings"],
            "build plan has no source bindings")
    for source in plan["sourceBindings"]:
        relative = safe_relative(source["path"], "planned source")
        require(snapshot.get(relative.as_posix()) == {
            "sha256": source["sha256"], "byteLength": source["byteLength"]},
            "build plan source differs from frozen project")
    for artifact, owner in ((app_relative, plan["hostModulePath"]), (test_relative, plan["modulePath"])):
        prefix = safe_relative(owner, "planned module") / "build"
        require(artifact.is_relative_to(prefix), "HAP output is outside its planned module build directory")
    verify_source_snapshot(root, snapshot)
    # One total timeout for both builds, rather than one full budget per step.
    deadline = time.monotonic() + args.build_timeout_seconds
    steps = []
    for step in expected_steps:
        command = [str(hvigorw), "--mode", "module", "-p",
                   f"module={step['module']}@{step['target']}", "-p", f"product={args.product}",
                   "-p", f"buildMode={args.build_mode}", step["task"], "--no-daemon", "--no-parallel"]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            steps[-1]["timedOut"] = True
            break
        result = run_build(command, root, remaining)
        steps.append(result)
        if result["timedOut"] or result["exitCode"] != 0:
            break
    command = steps[-1]["command"]
    build_result = {**steps[-1], "steps": steps,
                    "startedAt": steps[0]["startedAt"],
                    "stdout": "\n".join(step["stdout"] for step in steps),
                    "stderr": "\n".join(step["stderr"] for step in steps)}
    build_log_path = output / "build-command.json"
    write_json(build_log_path, build_result)

    failure_reasons = []
    if build_result["timedOut"]:
        failure_reasons.append("hvigor-build-timeout")
    if build_result["exitCode"] != 0:
        failure_reasons.append("hvigor-build-nonzero")
    try:
        verify_source_snapshot(root, snapshot)
        source_integrity = True
    except SourceStandardTestError as error:
        source_integrity = False
        failure_reasons.append(str(error))

    app_hap = child(root, app_relative)
    test_hap = child(root, test_relative)
    for path, label in ((app_hap, "app"), (test_hap, "test")):
        if not path.is_file() or path.is_symlink():
            failure_reasons.append(f"{label}-hap-absent")

    packages = None
    if not failure_reasons:
        packages = {
            "app": binding(app_hap, app_relative.as_posix()),
            "test": binding(test_hap, test_relative.as_posix()),
        }
    build_receipt = {
        "schema": BUILD_SCHEMA,
        "caseId": args.case_id,
        "sourceSetSha256": args.source_set_sha256,
        "projectTreeSha256": contract["projectTreeSha256"],
        "framework": FRAMEWORK,
        "status": "passed" if not failure_reasons else "failed",
        "passed": not failure_reasons,
        "failureReasons": failure_reasons,
        "command": command,
        "buildTarget": {
            "module": args.build_module,
            "testTarget": f"{args.build_module}@ohosTest",
            "product": args.product,
            "buildMode": args.build_mode,
            "outputType": plan["outputType"],
            "hostModule": plan["hostModule"],
            "task": task,
        },
        "buildPlan": binding(plan_path, "build-plan.json"),
        "buildPlanner": binding(planner, str(planner)),
        "buildPlanLog": binding(output / "build-plan-command.json", "build-plan-command.json"),
        "buildTool": binding(hvigorw, str(hvigorw)),
        "sourceContract": binding(source_contract_path, "source-contract.json"),
        "sourceIntegrityPreserved": source_integrity,
        "packages": packages,
        "log": binding(build_log_path, "build-command.json"),
        "startedAt": build_result["startedAt"],
        "finishedAt": build_result["finishedAt"],
        "automaticPromotion": False,
    }
    build_receipt_path = output / "build-receipt.json"
    write_json(build_receipt_path, build_receipt)

    execution_receipt = None
    execution_receipt_path = None
    if not failure_reasons:
        runner_args = argparse.Namespace(
            project_root=root,
            case_id=args.case_id,
            source_set_sha256=args.source_set_sha256,
            hdc=args.hdc,
            target=args.target,
            app_hap=app_hap,
            test_hap=test_hap,
            bundle=args.bundle,
            module=args.test_module,
            runner=args.runner,
            test_class=args.test_class,
            timeout_seconds=args.timeout_seconds,
            case_timeout_ms=args.case_timeout_ms,
            output_dir=output / "execution",
        )
        execution_receipt, execution_receipt_path = runner_module.execute(
            runner_args, contract_override=contract
        )

    passed = execution_receipt is not None and execution_receipt["passed"] is True
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "caseId": args.case_id,
        "sourceSetSha256": args.source_set_sha256,
        "projectTreeSha256": contract["projectTreeSha256"],
        "framework": FRAMEWORK,
        "status": (
            "passed" if passed else
            (execution_receipt["status"] if execution_receipt is not None else "build-failed")
        ),
        "passed": passed,
        "buildReceipt": binding(build_receipt_path, "build-receipt.json"),
        "executionReceipt": (
            binding(execution_receipt_path, "execution/receipt.json")
            if execution_receipt_path is not None else None
        ),
        "packages": packages,
        "startedAt": build_result["startedAt"],
        "finishedAt": (
            execution_receipt["finishedAt"] if execution_receipt is not None
            else build_result["finishedAt"]
        ),
        "automaticPromotion": False,
    }
    receipt_path = output / "receipt.json"
    write_json(receipt_path, receipt)
    return receipt, receipt_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--source-set-sha256", required=True)
    parser.add_argument("--hvigorw", type=Path, required=True)
    parser.add_argument("--build-module", required=True)
    parser.add_argument("--host-module", help="Installable HAP host; required for a library test module")
    parser.add_argument("--build-planner", type=Path, required=True,
                        help="Native agentlab-maintainer-skill-flywheel executable")
    parser.add_argument("--product", default="default")
    parser.add_argument("--build-mode", default="debug")
    parser.add_argument("--app-hap", required=True)
    parser.add_argument("--test-hap", required=True)
    parser.add_argument("--build-timeout-seconds", type=int, default=900)
    parser.add_argument("--hdc", default="hdc")
    parser.add_argument("--target", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--test-module", required=True)
    parser.add_argument("--runner", default="OpenHarmonyTestRunner")
    parser.add_argument("--test-class")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--case-timeout-ms", type=int, default=15000)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt, path = execute(args)
        print(json.dumps({"ok": receipt["passed"], "status": receipt["status"], "receipt": str(path)}, sort_keys=True))
        return 0 if receipt["passed"] else 1
    except (
        SourceStandardTestError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"Harmony source standard test invalid: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
