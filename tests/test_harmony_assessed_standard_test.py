from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run-harmony-assessed-standard-test.py"


SOURCE_EXECUTOR = r'''#!/usr/bin/env python3
import argparse, hashlib, json, os, pathlib
p=argparse.ArgumentParser()
for name in ("project-root","case-id","source-set-sha256","hvigorw","build-module","product","build-mode","app-hap","test-hap","build-timeout-seconds","hdc","target","bundle","test-module","runner","timeout-seconds","case-timeout-ms","output-dir"):
    p.add_argument("--"+name)
p.add_argument("--test-class"); a=p.parse_args(); out=pathlib.Path(a.output_dir); out.mkdir(parents=True)
status=os.environ.get("STANDARD_SOURCE_STATUS","passed"); passed=status == "passed"
receipt={"schema":"agentlab.harmony_source_standard_test_receipt.v1","caseId":a.case_id,
 "sourceSetSha256":a.source_set_sha256,"projectTreeSha256":"9"*64,
 "framework":"instrument-test-ohosTest-hypium","status":status,"passed":passed,"automaticPromotion":False}
(out/"receipt.json").write_text(json.dumps(receipt)); raise SystemExit(0 if passed else 1)
'''


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HarmonyAssessedStandardTestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.case = self.root / "case.json"
        self.case.write_text(json.dumps({"id": "standard-case", "sourceSetSha256": "a" * 64}))
        self.build_root = self.root / "build"
        (self.build_root / "project").mkdir(parents=True)
        self.build = self.build_root / "build-receipt.json"
        self.build.write_text(json.dumps({
            "buildAuthority": "independent-harmony-assessed-workspace-build",
            "evaluationCaseSha256": digest(self.case), "materializedProjectPath": "project",
            "participantId": "agent-a", "subjectWorkspaceSha256": "1" * 64,
            "assessmentSummarySha256": "2" * 64, "assessmentDecisionSha256": "3" * 64,
            "finalSourceStateSha256": "4" * 64,
        }))
        self.executor = self.root / "source.py"
        self.executor.write_text(SOURCE_EXECUTOR); self.executor.chmod(0o755)
        self.tool = self.root / "hvigorw"; self.tool.write_text("#!/bin/sh\n"); self.tool.chmod(0o755)
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps({
            "schema": "agentlab.harmony_assessed_standard_test_plan.v1",
            "evaluationCase": {"path": str(self.case), "sha256": digest(self.case)},
            "buildReceipt": {"path": str(self.build), "sha256": digest(self.build)},
            "projectRoot": str(self.build_root / "project"),
            "sourceExecutor": {"path": str(self.executor), "sha256": digest(self.executor)},
            "configuration": {"hvigorw": str(self.tool), "buildModule": "entry", "appHap": "app.hap",
                              "testHap": "test.hap", "target": "device", "bundle": "com.example",
                              "testModule": "entry_test"},
            "automaticPromotion": False,
        }))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_gate(self, status: str):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--plan", str(self.plan), "--output", str(self.root / "output")],
            text=True, capture_output=True, check=False, env={"PATH": "/usr/bin:/bin", "STANDARD_SOURCE_STATUS": status},
        )

    def test_passed_source_standard_test_is_lineage_bound(self) -> None:
        completed = self.run_gate("passed")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads((self.root / "output/receipt.json").read_text())
        self.assertTrue(receipt["subjectTaskSucceeded"])
        self.assertEqual(receipt["framework"], "instrument-test-ohosTest-hypium")
        self.assertEqual(receipt["assessedWorkspace"]["participantId"], "agent-a")

    def test_native_assertion_failure_is_assessed_not_infrastructure(self) -> None:
        completed = self.run_gate("failed")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads((self.root / "output/receipt.json").read_text())
        self.assertFalse(receipt["subjectTaskSucceeded"])
        self.assertEqual(receipt["failureClass"], "standard-test")

    def test_target_failure_remains_infrastructure_failure(self) -> None:
        completed = self.run_gate("infrastructure-error")
        self.assertEqual(completed.returncode, 1)
        self.assertFalse((self.root / "output/receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
