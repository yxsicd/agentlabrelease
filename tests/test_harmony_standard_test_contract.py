from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


STANDARD = load_module(
    "harmony_standard_test_contract_test",
    ROOT / "scripts/harmony-standard-test-contract.py",
)


class HarmonyStandardTestContractTests(unittest.TestCase):
    def fixture(self, root: Path, *, complete: bool = True) -> Path:
        project = root / "project"
        test_root = project / "entry/src/ohosTest/ets"
        (test_root / "test").mkdir(parents=True)
        (test_root / "test/Case.test.ets").write_text(
            "import { describe, it, expect, TestType, Size, Level } from '@ohos/hypium';\n"
            "export default function caseTest() { describe('caseTest', () => { "
            "it('showsReady', TestType.FUNCTION | Size.SMALLTEST | Level.LEVEL0, () => expect(true).assertTrue()); }); }\n"
        )
        if complete:
            (test_root / "testrunner").mkdir()
            (test_root / "testrunner/OpenHarmonyTestRunner.ets").write_text(
                "import { Hypium, HypiumTestRunner } from '@ohos/hypium';\n"
                "export default class OpenHarmonyTestRunner extends HypiumTestRunner {}\n"
            )
            (project / "entry/build-profile.json5").parent.mkdir(parents=True, exist_ok=True)
            (project / "entry/build-profile.json5").write_text(
                '{ "targets": [{ "name": "default" }, { "name": "ohosTest" }] }\n'
            )
            (project / "oh-package.json5").write_text(
                "{ devDependencies: { '@ohos/hypium': '1.0.21' } }\n"
            )
        return project

    def test_ohos_test_hypium_source_is_standard_but_execution_stays_pending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.fixture(Path(directory))
            custom = Path(directory) / "scenario.ui"
            custom.write_text("check text ready\n")
            value = STANDARD.build_contract(
                project, "case-one", "a" * 64, custom_ui_oracle=custom
            )
            self.assertTrue(value["deviceFunctionalStandardSourceQualified"])
            self.assertFalse(value["deviceFunctionalStandardExecutionQualified"])
            self.assertEqual(
                value["status"], "standard-test-source-qualified-execution-pending"
            )
            self.assertEqual(
                value["customUiOracle"]["authority"],
                "supplemental-only-not-a-Harmony-standard-test-substitute",
            )

    def test_custom_ui_oracle_alone_cannot_claim_harmony_standard_testing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            (project / "module.json5").write_text("{}\n")
            custom = Path(directory) / "scenario.ui"
            custom.write_text("check text ready\n")
            value = STANDARD.build_contract(
                project, "case-one", "a" * 64, custom_ui_oracle=custom
            )
            self.assertFalse(value["deviceFunctionalStandardSourceQualified"])
            self.assertEqual(value["status"], "unqualified-no-device-standard-test")

    def test_bound_passing_execution_receipt_closes_standard_test_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.fixture(root)
            pending = STANDARD.build_contract(project, "case-one", "a" * 64)
            native_report = root / "native-report.json"
            native_report.write_text(json.dumps({
                "schema": "agentlab.harmony_hypium_native_report.v1",
                "processExitCode": 0,
                "timedOut": False,
                "counts": {"total": 1, "failure": 0, "error": 0, "pass": 1, "ignore": 0},
                "nativeFinalCode": 0,
                "passed": True,
                "failureReasons": [],
            }))
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({
                "schema": STANDARD.RECEIPT_SCHEMA,
                "caseId": "case-one",
                "sourceSetSha256": "a" * 64,
                "projectTreeSha256": pending["projectTreeSha256"],
                "framework": "instrument-test-ohosTest-hypium",
                "status": "passed",
                "passed": True,
                "command": ["hdc", "shell", "aa", "test", "-s", "unittest", "OpenHarmonyTestRunner"],
                "report": {
                    "path": "native-report.json",
                    "sha256": STANDARD.digest(native_report),
                    "byteLength": native_report.stat().st_size,
                },
                "automaticPromotion": False,
            }))
            value = STANDARD.build_contract(
                project, "case-one", "a" * 64, execution_receipt=receipt
            )
            self.assertTrue(value["deviceFunctionalStandardExecutionQualified"])
            self.assertEqual(value["status"], "qualified-standard-test-executed")

    def test_tampered_native_report_cannot_close_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.fixture(root)
            pending = STANDARD.build_contract(project, "case-one", "a" * 64)
            native_report = root / "native-report.json"
            native_report.write_text(json.dumps({
                "schema": "agentlab.harmony_hypium_native_report.v1",
                "processExitCode": 0,
                "timedOut": False,
                "counts": {"total": 1, "failure": 0, "error": 0, "pass": 1, "ignore": 0},
                "nativeFinalCode": 0,
                "passed": True,
                "failureReasons": [],
            }))
            receipt = root / "receipt.json"
            receipt.write_text(json.dumps({
                "schema": STANDARD.RECEIPT_SCHEMA,
                "caseId": "case-one",
                "sourceSetSha256": "a" * 64,
                "projectTreeSha256": pending["projectTreeSha256"],
                "framework": "instrument-test-ohosTest-hypium",
                "status": "passed",
                "passed": True,
                "command": ["hdc", "shell", "aa", "test"],
                "report": {"path": "native-report.json", "sha256": "b" * 64, "byteLength": native_report.stat().st_size},
                "automaticPromotion": False,
            }))
            with self.assertRaisesRegex(STANDARD.StandardTestError, "digest differs"):
                STANDARD.build_contract(
                    project, "case-one", "a" * 64, execution_receipt=receipt
                )

    def test_partial_ohos_test_layout_is_not_source_qualified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.fixture(Path(directory), complete=False)
            value = STANDARD.build_contract(project, "case-one", "a" * 64)
            self.assertFalse(value["deviceFunctionalStandardSourceQualified"])
            lane = value["standardTestLanes"][0]
            self.assertIn(
                "OpenHarmonyTestRunner-source-or-Hvigor-generated-template", lane["missing"]
            )
            self.assertIn("ohosTest-build-target", lane["missing"])

    def test_source_migrated_ohos_test_uses_hvigor_generated_runner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.fixture(Path(directory), complete=False)
            module = project / "entry/src/ohosTest/module.json5"
            module.write_text('{ "module": { "name": "entry_test", "type": "feature" } }\n')
            (project / "entry/build-profile.json5").write_text(
                "{ targets: [{ name: 'default' }, { name: 'ohosTest' }] }\n"
            )
            (project / "oh-package.json5").write_text(
                "{ devDependencies: { '@ohos/hypium': '1.0.21' } }\n"
            )
            value = STANDARD.build_contract(project, "case-one", "a" * 64)
            lane = value["standardTestLanes"][0]
            self.assertTrue(lane["sourceContractQualified"])
            self.assertEqual(lane["runnerAuthority"], "hvigor-GenerateOhosTestTemplate")
            self.assertEqual(lane["missing"], [])

    def test_generated_build_outputs_do_not_change_source_contract_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(Path(directory), complete=True)
            before = STANDARD.build_contract(root, "case-one", "a" * 64)
            generated = root / "entry/build/default/outputs/ohosTest"
            generated.mkdir(parents=True)
            (generated / "entry-ohosTest-unsigned.hap").write_bytes(b"generated")
            generated_runner = root / ".test/generated/OpenHarmonyTestRunner.ets"
            generated_runner.parent.mkdir(parents=True)
            generated_runner.write_text("generated\n")
            after = STANDARD.build_contract(root, "case-one", "a" * 64)
            self.assertEqual(after["projectTreeSha256"], before["projectTreeSha256"])
            self.assertEqual(after["standardTestLanes"], before["standardTestLanes"])

    def test_public_schema_matches_contract(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/harmony-standard-test-contract.schema.json").read_text()
        )
        self.assertEqual(schema["properties"]["schema"]["const"], STANDARD.SCHEMA)


if __name__ == "__main__":
    unittest.main()
