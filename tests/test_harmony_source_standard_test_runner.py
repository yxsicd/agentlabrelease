from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


RUNNER = load_module(
    "harmony_source_standard_test_runner_test",
    ROOT / "scripts/run-harmony-source-standard-test.py",
)


class HarmonySourceStandardTestRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        test_root = self.project / "entry/src/ohosTest/ets"
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
        (self.project / "entry/build-profile.json5").write_text(
            "{ targets: [{ name: 'ohosTest' }] }\n"
        )
        (self.project / "oh-package.json5").write_text(
            "{ devDependencies: { '@ohos/hypium': '1.0.21' } }\n"
        )
        (self.project / "entry/src/main.ets").write_text("export const value = 1\n")
        self.hvigorw = self.executable(
            "hvigorw",
            "#!/usr/bin/env python3\n"
            "import os, pathlib\n"
            "root=pathlib.Path.cwd(); mode=os.environ.get('FAKE_HVIGOR_MODE', 'pass')\n"
            "if mode == 'fail': raise SystemExit(7)\n"
            "if mode == 'mutate': (root/'entry/src/main.ets').write_text('changed\\n')\n"
            "out=root/'build'; out.mkdir(exist_ok=True)\n"
            "(out/'app.hap').write_bytes(b'app-hap')\n"
            "(out/'app-ohosTest.hap').write_bytes(b'test-hap')\n",
        )
        self.hdc = self.executable(
            "hdc",
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "if sys.argv[1:] == ['list', 'targets']: print('emulator-1'); raise SystemExit(0)\n"
            "if 'install' in sys.argv: print('install bundle successfully'); raise SystemExit(0)\n"
            "print('OHOS_REPORT_RESULT: stream=Tests run: 1, Failure: 0, Error: 0, Pass: 1, Ignore: 0')\n"
            "print('OHOS_REPORT_CODE: 0')\n",
        )

    def executable(self, name: str, content: str) -> Path:
        path = self.root / name
        path.write_text(content)
        path.chmod(0o755)
        return path

    def args(self) -> argparse.Namespace:
        return argparse.Namespace(
            project_root=self.project,
            case_id="source-case",
            source_set_sha256="a" * 64,
            hvigorw=self.hvigorw,
            build_module="entry",
            product="default",
            build_mode="debug",
            app_hap="build/app.hap",
            test_hap="build/app-ohosTest.hap",
            build_timeout_seconds=30,
            hdc=str(self.hdc),
            target="emulator-1",
            bundle="com.example.agentlab",
            test_module="entry_test",
            runner="OpenHarmonyTestRunner",
            test_class=None,
            timeout_seconds=5,
            case_timeout_ms=15000,
            output_dir=self.root / "result",
        )

    def test_source_build_install_and_native_test_are_one_bound_receipt(self) -> None:
        receipt, path = RUNNER.execute(self.args())
        self.assertTrue(receipt["passed"])
        self.assertEqual(receipt["status"], "passed")
        build = json.loads((path.parent / "build-receipt.json").read_text())
        execution = json.loads((path.parent / "execution/receipt.json").read_text())
        self.assertEqual(build["buildTarget"]["testTarget"], "entry@ohosTest")
        self.assertTrue(build["sourceIntegrityPreserved"])
        self.assertEqual(
            build["projectTreeSha256"], execution["projectTreeSha256"]
        )
        self.assertEqual(build["packages"]["test"]["sha256"], execution["packages"]["test"]["sha256"])
        command = json.loads((path.parent / "build-command.json").read_text())["command"]
        self.assertIn("module=entry@ohosTest", command)

    def test_repeated_build_ignores_prior_generated_outputs(self) -> None:
        first, _ = RUNNER.execute(self.args())
        self.assertTrue(first["passed"])
        args = self.args()
        args.output_dir = self.root / "second-result"
        second, _ = RUNNER.execute(args)
        self.assertTrue(second["passed"])
        self.assertEqual(second["projectTreeSha256"], first["projectTreeSha256"])

    def test_build_failure_is_retained_and_does_not_run_device(self) -> None:
        with mock.patch.dict(os.environ, {"FAKE_HVIGOR_MODE": "fail"}):
            receipt, path = RUNNER.execute(self.args())
        self.assertFalse(receipt["passed"])
        self.assertEqual(receipt["status"], "build-failed")
        self.assertIsNone(receipt["executionReceipt"])
        build = json.loads((path.parent / "build-receipt.json").read_text())
        self.assertIn("hvigor-build-nonzero", build["failureReasons"])
        self.assertFalse((path.parent / "execution").exists())

    def test_build_cannot_silently_modify_preexisting_source(self) -> None:
        with mock.patch.dict(os.environ, {"FAKE_HVIGOR_MODE": "mutate"}):
            receipt, path = RUNNER.execute(self.args())
        self.assertFalse(receipt["passed"])
        build = json.loads((path.parent / "build-receipt.json").read_text())
        self.assertFalse(build["sourceIntegrityPreserved"])
        self.assertTrue(
            any("modified pre-existing source file" in reason for reason in build["failureReasons"])
        )
        self.assertFalse((path.parent / "execution").exists())

    def test_output_inside_project_is_rejected_before_build(self) -> None:
        args = self.args()
        args.output_dir = self.project / "evidence"
        with self.assertRaisesRegex(RUNNER.SourceStandardTestError, "outside the project"):
            RUNNER.execute(args)
        self.assertFalse(args.output_dir.exists())

    def test_public_receipt_schemas_match_runner(self) -> None:
        receipt_schema = json.loads(
            (ROOT / "schemas/harmony-source-standard-test-receipt.schema.json").read_text()
        )
        build_schema = json.loads(
            (ROOT / "schemas/harmony-standard-test-source-build-receipt.schema.json").read_text()
        )
        self.assertEqual(receipt_schema["properties"]["schema"]["const"], RUNNER.RECEIPT_SCHEMA)
        self.assertEqual(build_schema["properties"]["schema"]["const"], RUNNER.BUILD_SCHEMA)


if __name__ == "__main__":
    unittest.main()
