from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from unittest import mock
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


RUNNER = load_module(
    "harmony_instrument_test_runner_test",
    ROOT / "scripts/run-harmony-instrument-test.py",
)


class HarmonyInstrumentTestRunnerTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        project = root / "project"
        test_root = project / "entry/src/ohosTest/ets"
        (test_root / "test").mkdir(parents=True)
        (test_root / "test/Case.test.ets").write_text(
            "import { describe, it, expect } from '@ohos/hypium';\n"
            "export default function caseTest() { describe('caseTest', () => { "
            "it('works', 0, () => expect(true).assertTrue()); }); }\n"
        )
        (test_root / "testrunner").mkdir()
        (test_root / "testrunner/OpenHarmonyTestRunner.ets").write_text(
            "import { Hypium, HypiumTestRunner } from '@ohos/hypium';\n"
            "export default class OpenHarmonyTestRunner extends HypiumTestRunner {}\n"
        )
        (project / "entry/build-profile.json5").write_text(
            "{ targets: [{ name: 'ohosTest' }] }\n"
        )
        (project / "oh-package.json5").write_text(
            "{ devDependencies: { '@ohos/hypium': '1.0.21' } }\n"
        )
        app_hap = root / "app.hap"
        test_hap = root / "app-ohosTest.hap"
        app_hap.write_bytes(b"app")
        test_hap.write_bytes(b"test")
        hdc = root / "hdc"
        hdc.write_text(
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            "mode = os.environ.get('FAKE_HDC_MODE', 'pass')\n"
            "if sys.argv[1:] == ['list', 'targets']:\n"
            "    if mode == 'missing-target': print('other-target')\n"
            "    else: print('emulator-1')\n"
            "    raise SystemExit(0)\n"
            "if 'install' in sys.argv:\n"
            "    if mode == 'install-fail': raise SystemExit(1)\n"
            "    print('Install successfully')\n"
            "    raise SystemExit(0)\n"
            "if mode == 'pass':\n"
            "    print('OHOS_REPORT_RESULT: stream=Tests run: 2, Failure: 0, Error: 0, Pass: 2, Ignore: 0')\n"
            "    print('OHOS_REPORT_CODE: 0')\n"
            "elif mode == 'failure':\n"
            "    print('OHOS_REPORT_RESULT: stream=Tests run: 2, Failure: 1, Error: 0, Pass: 1, Ignore: 0')\n"
            "    print('OHOS_REPORT_CODE: -1')\n"
            "elif mode == 'exit-zero-only':\n"
            "    print('aa test completed')\n"
            "raise SystemExit(0)\n"
        )
        hdc.chmod(0o755)
        return project, app_hap, test_hap, hdc

    def args(self, root: Path, mode: str = "pass") -> argparse.Namespace:
        project, app_hap, test_hap, hdc = self.fixture(root)
        return argparse.Namespace(
            project_root=project,
            case_id="case-one",
            source_set_sha256="a" * 64,
            hdc=str(hdc),
            target="emulator-1",
            app_hap=app_hap,
            test_hap=test_hap,
            bundle="com.example.agentlab",
            module="entry_test",
            runner="OpenHarmonyTestRunner",
            test_class=None,
            timeout_seconds=5,
            case_timeout_ms=15000,
            output_dir=root / "result",
        )

    def run_mode(self, mode: str) -> tuple[dict, Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        with mock.patch.dict(os.environ, {"FAKE_HDC_MODE": mode}):
            return RUNNER.execute(self.args(root))

    def test_pass_requires_native_summary_and_code(self) -> None:
        receipt, path = self.run_mode("pass")
        self.assertTrue(receipt["passed"])
        self.assertEqual(receipt["status"], "passed")
        report = json.loads((path.parent / "native-report.json").read_text())
        self.assertEqual(report["counts"]["total"], 2)
        self.assertEqual(report["nativeFinalCode"], 0)

    def test_native_failure_is_task_failure(self) -> None:
        receipt, path = self.run_mode("failure")
        self.assertFalse(receipt["passed"])
        self.assertEqual(receipt["status"], "failed")
        report = json.loads((path.parent / "native-report.json").read_text())
        self.assertIn("test-failures-present", report["failureReasons"])
        self.assertIn("native-final-code-nonzero", report["failureReasons"])

    def test_process_zero_without_native_markers_cannot_pass(self) -> None:
        receipt, path = self.run_mode("exit-zero-only")
        self.assertFalse(receipt["passed"])
        report = json.loads((path.parent / "native-report.json").read_text())
        self.assertIn("native-final-summary-absent", report["failureReasons"])
        self.assertIn("native-final-code-absent", report["failureReasons"])

    def test_missing_target_is_infrastructure_error(self) -> None:
        receipt, path = self.run_mode("missing-target")
        self.assertFalse(receipt["passed"])
        self.assertEqual(receipt["status"], "infrastructure-error")
        report = json.loads((path.parent / "native-report.json").read_text())
        self.assertEqual(report["failureReasons"], ["target-preflight-failed"])

    def test_summary_count_mismatch_cannot_pass(self) -> None:
        report = RUNNER.parse_native_report(
            "OHOS_REPORT_RESULT: stream=Tests run: 3, Failure: 0, Error: 0, Pass: 2, Ignore: 0\n"
            "OHOS_REPORT_CODE: 0\n",
            "",
            0,
            False,
        )
        self.assertFalse(report["passed"])
        self.assertIn("native-summary-counts-inconsistent", report["failureReasons"])

    def test_official_worker_aggregate_markers_can_pass(self) -> None:
        report = RUNNER.parse_native_report(
            "OHOS_REPORT_ALL_RESULT: stream=Test run: runTimes: 2,total: 4, Failure: 0, Error: 0, Pass: 4, Ignore: 0\n"
            "OHOS_REPORT_ALL_CODE: 0\n",
            "",
            0,
            False,
        )
        self.assertTrue(report["passed"])
        self.assertEqual(report["counts"]["total"], 4)

    def test_public_receipt_schema_matches_runner(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/harmony-standard-test-execution-receipt.schema.json").read_text()
        )
        self.assertEqual(schema["properties"]["schema"]["const"], RUNNER.RECEIPT_SCHEMA)


if __name__ == "__main__":
    unittest.main()
