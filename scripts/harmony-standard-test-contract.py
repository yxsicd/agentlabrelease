#!/usr/bin/env python3
"""Inventory Harmony standard test lanes without treating custom UI scripts as substitutes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any


SCHEMA = "agentlab.harmony_standard_test_contract.v1"
RECEIPT_SCHEMA = "agentlab.harmony_standard_test_execution_receipt.v1"
SHA256 = re.compile(r"[0-9a-f]{64}")
TOKEN = re.compile(r"[A-Za-z0-9_.:@/+\-]{1,200}")


class StandardTestError(ValueError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise StandardTestError(message)


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), f"test evidence must be a regular file: {path}")
    return digest_bytes(path.read_bytes())


def load(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"{label} must be a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def project_files(root: Path) -> list[Path]:
    root = root.resolve(strict=True)
    require(root.is_dir(), "Harmony project root must be a directory")
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise StandardTestError(f"Harmony test source cannot contain symlinks: {path.relative_to(root)}")
        if path.is_file():
            files.append(path)
    require(files, "Harmony project is empty")
    return files


def tree_digest(root: Path, files: list[Path]) -> str:
    rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": digest(path),
            "byteLength": path.stat().st_size,
        }
        for path in files
    ]
    return digest_bytes(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode())


def text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


def evidence(root: Path, paths: list[Path]) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": digest(path),
            "byteLength": path.stat().st_size,
        }
        for path in sorted(set(paths))
    ]


def inspect_lanes(root: Path, files: list[Path]) -> list[dict[str, Any]]:
    instrument_sources = [
        path for path in files
        if "ohosTest" in path.relative_to(root).parts and path.suffix in {".ets", ".ts"}
    ]
    instrument_tests = [
        path for path in instrument_sources
        if "@ohos/hypium" in text(path) and "describe(" in text(path) and "it(" in text(path)
    ]
    instrument_runners = [
        path for path in instrument_sources
        if "OpenHarmonyTestRunner" in text(path) and "Hypium" in text(path)
    ]
    generated_runner_modules = [
        path for path in files
        if path.name == "module.json5"
        and "ohosTest" in path.relative_to(root).parts
        and re.search(r"[\"']?module[\"']?\s*:", text(path))
        and not re.search(r"[\"']?srcEntry[\"']?\s*:", text(path))
    ]
    build_profiles = [path for path in files if path.name == "build-profile.json5"]
    ohos_test_targets = [
        path for path in build_profiles
        if re.search(r"[\"']?name[\"']?\s*:\s*['\"]ohosTest['\"]", text(path))
    ]
    package_manifests = [path for path in files if path.name == "oh-package.json5"]
    hypium_dependencies = [path for path in package_manifests if "@ohos/hypium" in text(path)]

    local_sources = [
        path for path in files
        if "test" in path.relative_to(root).parts
        and "ohosTest" not in path.relative_to(root).parts
        and path.suffix in {".ets", ".ts"}
        and "@ohos/hypium" in text(path)
        and "describe(" in text(path)
        and "it(" in text(path)
    ]
    python_cases = [
        path for path in files
        if "testcases" in path.relative_to(root).parts
        and path.suffix == ".py"
        and "hypium" in text(path)
        and "Step" in text(path)
    ]
    python_configs = [
        path for path in files
        if path.name in {"setup-regression.py", "MANIFEST.in", "user_config.xml"}
    ]

    lanes = []
    if instrument_sources or ohos_test_targets or hypium_dependencies:
        runner_authority = (
            "source-provided-OpenHarmonyTestRunner"
            if instrument_runners
            else (
                "hvigor-GenerateOhosTestTemplate"
                if generated_runner_modules
                else None
            )
        )
        qualified = bool(
            instrument_tests and runner_authority and ohos_test_targets and hypium_dependencies
        )
        lanes.append({
            "framework": "instrument-test-ohosTest-hypium",
            "sourceContractQualified": qualified,
            "deviceCapable": True,
            "executionInterface": "hdc-shell-aa-test-OpenHarmonyTestRunner",
            "runnerAuthority": runner_authority,
            "evidence": evidence(
                root,
                instrument_tests + instrument_runners + generated_runner_modules
                + ohos_test_targets + hypium_dependencies,
            ),
            "missing": [
                label for present, label in (
                    (instrument_tests, "hypium-test-source"),
                    (
                        instrument_runners or generated_runner_modules,
                        "OpenHarmonyTestRunner-source-or-Hvigor-generated-template",
                    ),
                    (ohos_test_targets, "ohosTest-build-target"),
                    (hypium_dependencies, "@ohos/hypium-dependency"),
                ) if not present
            ],
        })
    if local_sources:
        lanes.append({
            "framework": "local-test-hypium",
            "sourceContractQualified": True,
            "deviceCapable": False,
            "executionInterface": "deveco-local-test-or-hvigor-command-line",
            "evidence": evidence(root, local_sources + hypium_dependencies),
            "missing": [],
        })
    if python_cases or python_configs:
        qualified = bool(python_cases and {"setup-regression.py", "MANIFEST.in"} <= {path.name for path in python_configs})
        lanes.append({
            "framework": "deveco-testing-hypium-ui",
            "sourceContractQualified": qualified,
            "deviceCapable": True,
            "executionInterface": "deveco-testing-run-command",
            "evidence": evidence(root, python_cases + python_configs),
            "missing": [
                label for present, label in (
                    (python_cases, "Hypium-Python-testcase-with-Step"),
                    ([path for path in python_configs if path.name == "setup-regression.py"], "setup-regression.py"),
                    ([path for path in python_configs if path.name == "MANIFEST.in"], "MANIFEST.in"),
                ) if not present
            ],
        })
    return lanes


def validate_receipt(
    path: Path | None,
    case_id: str,
    source_set: str,
    project_sha: str,
    qualified_frameworks: set[str],
) -> dict[str, Any] | None:
    if path is None:
        return None
    value = load(path, "Harmony standard test execution receipt")
    require(value.get("schema") == RECEIPT_SCHEMA, "Harmony standard test receipt schema differs")
    require(value.get("caseId") == case_id and value.get("sourceSetSha256") == source_set, "Harmony standard test receipt identity differs")
    require(value.get("projectTreeSha256") == project_sha, "Harmony standard test receipt project differs")
    require(value.get("framework") in qualified_frameworks, "Harmony standard test receipt framework was not source-qualified")
    require(value.get("status") == "passed" and value.get("passed") is True, "Harmony standard test execution did not pass")
    require(value.get("automaticPromotion") is False, "Harmony standard test receipt can auto-promote")
    require(isinstance(value.get("command"), list) and value["command"], "Harmony standard test command is absent")
    report = value.get("report")
    require(isinstance(report, dict) and set(report) == {"path", "sha256", "byteLength"}, "Harmony standard test report binding differs")
    require(isinstance(report.get("sha256"), str) and SHA256.fullmatch(report["sha256"]), "Harmony standard test report digest is invalid")
    report_relative = PurePosixPath(report.get("path", ""))
    require(not report_relative.is_absolute() and ".." not in report_relative.parts, "Harmony standard test report path escapes its receipt")
    report_path = path.parent.joinpath(*report_relative.parts)
    require(report_path.is_file() and not report_path.is_symlink(), "Harmony standard test report is absent")
    require(digest(report_path) == report["sha256"], "Harmony standard test report digest differs")
    require(report_path.stat().st_size == report.get("byteLength"), "Harmony standard test report length differs")
    native = load(report_path, "Harmony native test report")
    require(native.get("schema") == "agentlab.harmony_hypium_native_report.v1", "Harmony native test report schema differs")
    require(native.get("passed") is True and native.get("failureReasons") == [], "Harmony native test report did not pass")
    counts = native.get("counts")
    require(isinstance(counts, dict) and counts.get("total", 0) > 0 and counts.get("pass", 0) > 0, "Harmony native test report ran no passing tests")
    require(counts.get("failure") == 0 and counts.get("error") == 0, "Harmony native test report contains failures")
    require(native.get("nativeFinalCode") == 0 and native.get("processExitCode") == 0 and native.get("timedOut") is False, "Harmony native test completion differs")
    return value


def build_contract(
    project_root: Path,
    case_id: str,
    source_set: str,
    custom_ui_oracle: Path | None = None,
    execution_receipt: Path | None = None,
) -> dict[str, Any]:
    require(isinstance(case_id, str) and TOKEN.fullmatch(case_id), "Harmony case identity is invalid")
    require(isinstance(source_set, str) and SHA256.fullmatch(source_set), "Harmony source set is invalid")
    root = project_root.resolve(strict=True)
    files = project_files(root)
    project_sha = tree_digest(root, files)
    lanes = inspect_lanes(root, files)
    qualified_device_frameworks = {
        lane["framework"] for lane in lanes
        if lane["sourceContractQualified"] and lane["deviceCapable"]
    }
    receipt = validate_receipt(
        execution_receipt,
        case_id,
        source_set,
        project_sha,
        qualified_device_frameworks,
    )
    custom = None
    if custom_ui_oracle is not None:
        custom = {
            "path": custom_ui_oracle.name,
            "sha256": digest(custom_ui_oracle),
            "byteLength": custom_ui_oracle.stat().st_size,
            "authority": "supplemental-only-not-a-Harmony-standard-test-substitute",
        }
    source_qualified = bool(qualified_device_frameworks)
    execution_qualified = receipt is not None
    return {
        "schema": SCHEMA,
        "caseId": case_id,
        "sourceSetSha256": source_set,
        "projectTreeSha256": project_sha,
        "standardTestLanes": lanes,
        "deviceFunctionalStandardSourceQualified": source_qualified,
        "deviceFunctionalStandardExecutionQualified": execution_qualified,
        "status": (
            "qualified-standard-test-executed"
            if execution_qualified
            else (
                "standard-test-source-qualified-execution-pending"
                if source_qualified
                else "unqualified-no-device-standard-test"
            )
        ),
        "executionReceipt": receipt,
        "customUiOracle": custom,
        "policy": {
            "acceptedFrameworks": [
                "instrument-test-ohosTest-hypium",
                "local-test-hypium",
                "deveco-testing-hypium-ui",
            ],
            "deviceQualificationRequires": [
                "device-capable-standard-source-contract",
                "passing-bound-execution-receipt",
            ],
            "customUiOracleAuthority": "supplemental-only",
        },
        "automaticPromotion": False,
    }


def validate_contract(path: Path) -> dict[str, Any]:
    value = load(path, "Harmony standard test contract")
    require(value.get("schema") == SCHEMA, "Harmony standard test contract schema differs")
    require(value.get("automaticPromotion") is False, "Harmony standard test contract can auto-promote")
    require(isinstance(value.get("caseId"), str) and TOKEN.fullmatch(value["caseId"]), "Harmony case identity is invalid")
    require(isinstance(value.get("sourceSetSha256"), str) and SHA256.fullmatch(value["sourceSetSha256"]), "Harmony source set is invalid")
    require(isinstance(value.get("projectTreeSha256"), str) and SHA256.fullmatch(value["projectTreeSha256"]), "Harmony project digest is invalid")
    lanes = value.get("standardTestLanes")
    require(isinstance(lanes, list), "Harmony standard test lanes are absent")
    source_qualified = any(lane.get("sourceContractQualified") is True and lane.get("deviceCapable") is True for lane in lanes if isinstance(lane, dict))
    execution_qualified = value.get("executionReceipt") is not None
    require(value.get("deviceFunctionalStandardSourceQualified") is source_qualified, "Harmony standard test source qualification differs")
    require(value.get("deviceFunctionalStandardExecutionQualified") is execution_qualified, "Harmony standard test execution qualification differs")
    require((value.get("customUiOracle") or {}).get("authority", "supplemental-only-not-a-Harmony-standard-test-substitute") == "supplemental-only-not-a-Harmony-standard-test-substitute", "custom UI Oracle authority differs")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--project-root", type=Path, required=True)
    inspect.add_argument("--case-id", required=True)
    inspect.add_argument("--source-set-sha256", required=True)
    inspect.add_argument("--custom-ui-oracle", type=Path)
    inspect.add_argument("--execution-receipt", type=Path)
    inspect.add_argument("--output", type=Path, required=True)
    inspect.add_argument("--require-device-standard-source", action="store_true")
    validate = commands.add_parser("validate")
    validate.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            require(not args.output.exists(), f"refusing to overwrite output: {args.output}")
            value = build_contract(
                args.project_root,
                args.case_id,
                args.source_set_sha256,
                args.custom_ui_oracle,
                args.execution_receipt,
            )
            args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if args.require_device_standard_source:
                require(value["deviceFunctionalStandardSourceQualified"], "device-capable Harmony standard test source is absent")
        else:
            value = validate_contract(args.contract)
        print(json.dumps({
            "ok": True,
            "status": value["status"],
            "sourceQualified": value["deviceFunctionalStandardSourceQualified"],
            "executionQualified": value["deviceFunctionalStandardExecutionQualified"],
        }, sort_keys=True))
    except (StandardTestError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Harmony standard test contract invalid: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
