#!/usr/bin/env python3
"""Run source-bound ohosTest for one exact assessed Harmony build."""
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


PLAN_SCHEMA = "agentlab.harmony_assessed_standard_test_plan.v1"
RECEIPT_SCHEMA = "agentlab.harmony_assessed_standard_test_receipt.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")


class StandardGateError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StandardGateError(f"cannot load {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise StandardGateError(f"{label} must be a JSON object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bound_file(value: Any, label: str, *, executable: bool = False) -> Path:
    if not isinstance(value, dict) or not isinstance(value.get("path"), str):
        raise StandardGateError(f"{label} binding is required")
    path = Path(value["path"]).resolve()
    expected = value.get("sha256")
    if not path.is_file() or path.is_symlink():
        raise StandardGateError(f"{label} must be a regular file: {path}")
    if executable and not os.access(path, os.X_OK):
        raise StandardGateError(f"{label} is not executable: {path}")
    if not isinstance(expected, str) or SHA256.fullmatch(expected) is None or sha256(path) != expected:
        raise StandardGateError(f"{label} SHA256 differs from plan")
    return path


def target_connected(hdc: Path, target: str) -> bool:
    completed = subprocess.run(
        [str(hdc), "list", "targets"], text=True, capture_output=True,
        timeout=15, check=False,
    )
    return completed.returncode == 0 and target in completed.stdout.split()


def wait_target(hdc: Path, target: str, *, present: bool, timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if target_connected(hdc, target) is present:
                return True
        except subprocess.TimeoutExpired:
            pass
        time.sleep(1)
    return False


def start_emulator(config: dict[str, Any], output: Path, hdc: Path) -> dict[str, Any]:
    required = ("toolsRoot", "imageRoot", "instancePath", "instance", "hdcPort", "bootMode")
    if any(key not in config for key in required):
        raise StandardGateError("emulator lifecycle configuration is incomplete")
    tools_root = Path(config["toolsRoot"]).resolve()
    image_root = Path(config["imageRoot"]).resolve()
    instance_path = Path(config["instancePath"]).resolve()
    instance = config["instance"]
    port = config["hdcPort"]
    boot_mode = config["bootMode"]
    if (
        not isinstance(instance, str) or not instance
        or not isinstance(port, int) or not 10000 <= port <= 16555
        or boot_mode not in {"coldboot", "reset", "snapshot"}
    ):
        raise StandardGateError("emulator lifecycle identity is invalid")
    emulator = tools_root / "bin/Emulator"
    if not emulator.is_file() or not os.access(emulator, os.X_OK):
        raise StandardGateError(f"emulator executable is absent: {emulator}")
    if not image_root.is_dir() or not (instance_path / f"{instance}.ini").is_file():
        raise StandardGateError("emulator image or instance is absent")
    target = f"127.0.0.1:{port}"
    if target_connected(hdc, target):
        stopped = subprocess.run(
            [str(emulator), "-stop", instance, "-instancePath", str(instance_path)],
            text=True, capture_output=True, timeout=30, check=False,
        )
        (output / "emulator-prestop.log").write_text(
            stopped.stdout + stopped.stderr, encoding="utf-8"
        )
        if stopped.returncode != 0 or not wait_target(hdc, target, present=False, timeout=30):
            raise StandardGateError("pre-existing emulator target could not be stopped")
    command = [
        str(emulator), "-start", instance, "-instancePath", str(instance_path),
        "-imageRoot", str(image_root), "-bootMode", boot_mode, "-noWindow",
        "-hdcPort", str(port),
    ]
    log = (output / "emulator-start.log").open("w", encoding="utf-8")
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
    if not wait_target(hdc, target, present=True, timeout=180):
        log.close()
        process.poll()
        raise StandardGateError("emulator did not expose the standard-test HDC target")
    log.close()
    return {
        "emulator": emulator,
        "instancePath": instance_path,
        "instance": instance,
        "target": target,
        "process": process,
        "command": command,
    }


def stop_emulator(lifecycle: dict[str, Any], output: Path, hdc: Path) -> None:
    completed = subprocess.run(
        [str(lifecycle["emulator"]), "-stop", lifecycle["instance"],
         "-instancePath", str(lifecycle["instancePath"])],
        text=True, capture_output=True, timeout=30, check=False,
    )
    (output / "emulator-stop.log").write_text(
        completed.stdout + completed.stderr, encoding="utf-8"
    )
    if completed.returncode != 0 or not wait_target(
        hdc, lifecycle["target"], present=False, timeout=30
    ):
        raise StandardGateError("standard-test emulator did not stop cleanly")
    process = lifecycle["process"]
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        plan_path = args.plan.resolve()
        plan = load(plan_path, "standard-test plan")
        if plan.get("schema") != PLAN_SCHEMA or plan.get("automaticPromotion") is not False:
            raise StandardGateError("unsupported or promotable standard-test plan")
        case_path = bound_file(plan.get("evaluationCase"), "evaluation case")
        build_path = bound_file(plan.get("buildReceipt"), "build receipt")
        executor = bound_file(plan.get("sourceExecutor"), "source standard-test executor", executable=True)
        case = load(case_path, "evaluation case")
        build = load(build_path, "build receipt")
        if build.get("buildAuthority") != "independent-harmony-assessed-workspace-build":
            raise StandardGateError("standard test requires an assessed-workspace build")
        if build.get("evaluationCaseSha256") != sha256(case_path):
            raise StandardGateError("build receipt does not bind the evaluation case")
        project = Path(plan.get("projectRoot", "")).resolve()
        expected_project = build_path.parent / build.get("materializedProjectPath", "")
        if project != expected_project.resolve() or not project.is_dir() or project.is_symlink():
            raise StandardGateError("projectRoot is not the retained assessed build project")
        config = plan.get("configuration")
        if not isinstance(config, dict):
            raise StandardGateError("standard-test configuration is required")
        required = ("hvigorw", "buildModule", "appHap", "testHap", "target", "bundle", "testModule")
        if any(not isinstance(config.get(key), str) or not config[key] for key in required):
            raise StandardGateError("standard-test configuration is incomplete")
        if output.exists():
            raise StandardGateError(f"refusing to overwrite output: {output}")
        output.mkdir(parents=True)
        source_output = output / "source-standard-test"
        command = [
            str(executor), "--project-root", str(project), "--case-id", case["id"],
            "--source-set-sha256", case["sourceSetSha256"], "--hvigorw", config["hvigorw"],
            "--build-module", config["buildModule"], "--product", config.get("product", "default"),
            "--build-mode", config.get("buildMode", "debug"), "--app-hap", config["appHap"],
            "--test-hap", config["testHap"], "--build-timeout-seconds", str(config.get("buildTimeoutSeconds", 900)),
            "--hdc", config.get("hdc", "hdc"), "--target", config["target"],
            "--bundle", config["bundle"], "--test-module", config["testModule"],
            "--runner", config.get("runner", "OpenHarmonyTestRunner"),
            "--timeout-seconds", str(config.get("timeoutSeconds", 300)),
            "--case-timeout-ms", str(config.get("caseTimeoutMs", 15000)),
            "--output-dir", str(source_output),
        ]
        if config.get("testClass"):
            command.extend(["--test-class", config["testClass"]])
        emulator_config = plan.get("emulator")
        lifecycle = None
        lifecycle_receipt_path = None
        hdc = Path(config.get("hdc", "hdc")).resolve()
        if emulator_config is not None:
            if not isinstance(emulator_config, dict):
                raise StandardGateError("emulator lifecycle must be an object")
            if not hdc.is_file() or not os.access(hdc, os.X_OK):
                raise StandardGateError(f"HDC executable is absent: {hdc}")
            expected_target = f"127.0.0.1:{emulator_config.get('hdcPort')}"
            if config["target"] != expected_target:
                raise StandardGateError("standard-test target differs from emulator lifecycle")
            lifecycle = start_emulator(emulator_config, output, hdc)
        try:
            completed = subprocess.run(command, text=True, capture_output=True, check=False)
        finally:
            if lifecycle is not None:
                stop_emulator(lifecycle, output, hdc)
                lifecycle_receipt_path = output / "emulator-lifecycle.json"
                write_json(lifecycle_receipt_path, {
                    "schema": "agentlab.harmony_standard_test_emulator_lifecycle.v1",
                    "status": "stopped-cleanly",
                    "target": lifecycle["target"],
                    "instance": lifecycle["instance"],
                    "command": lifecycle["command"],
                    "startLogSha256": sha256(output / "emulator-start.log"),
                    "stopLogSha256": sha256(output / "emulator-stop.log"),
                    "automaticPromotion": False,
                })
        (output / "executor.stdout.log").write_text(completed.stdout, encoding="utf-8")
        (output / "executor.stderr.log").write_text(completed.stderr, encoding="utf-8")
        source_receipt_path = source_output / "receipt.json"
        if not source_receipt_path.is_file():
            raise StandardGateError(f"standard-test executor failed without a receipt (exit {completed.returncode})")
        source = load(source_receipt_path, "source standard-test receipt")
        if (
            source.get("schema") != "agentlab.harmony_source_standard_test_receipt.v1"
            or source.get("caseId") != case.get("id")
            or source.get("sourceSetSha256") != case.get("sourceSetSha256")
            or source.get("automaticPromotion") is not False
        ):
            raise StandardGateError("source standard-test receipt differs from assessed lineage")
        if source.get("status") == "infrastructure-error":
            raise StandardGateError("source standard test reported infrastructure-error")
        passed = source.get("passed") is True
        if completed.returncode not in ({0} if passed else {1}):
            raise StandardGateError("source standard-test exit code contradicts its receipt")
        assessed = {
            key: build.get(key) for key in (
                "participantId", "subjectWorkspaceSha256", "assessmentSummarySha256",
                "assessmentDecisionSha256", "finalSourceStateSha256",
            )
        }
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": "passed-review-required" if passed else "assessed-failure-review-required",
            "caseId": case["id"],
            "evaluationCaseSha256": sha256(case_path),
            "sourceSetSha256": case["sourceSetSha256"],
            "buildReceiptSha256": sha256(build_path),
            "projectTreeSha256": source.get("projectTreeSha256"),
            "framework": source.get("framework"),
            "sourceStandardTestReceiptSha256": sha256(source_receipt_path),
            "emulatorLifecycleSha256": (
                sha256(lifecycle_receipt_path)
                if lifecycle_receipt_path is not None else None
            ),
            "subjectTaskSucceeded": passed,
            "failureClass": "none" if passed else "standard-test",
            "assessedWorkspace": assessed,
            "automaticPromotion": False,
        }
        write_json(output / "receipt.json", receipt)
        print(json.dumps({"ok": True, "status": receipt["status"], "output": str(output)}, sort_keys=True))
        return 0
    except (StandardGateError, OSError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error), "output": str(output)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
