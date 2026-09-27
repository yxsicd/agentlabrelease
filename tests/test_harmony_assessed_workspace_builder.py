from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build-harmony-assessed-workspace.py"


BUILDER = r'''#!/usr/bin/env python3
import argparse, pathlib
p = argparse.ArgumentParser(); p.add_argument("--workspace", required=True); p.add_argument("--artifact", required=True); a = p.parse_args()
root = pathlib.Path(a.workspace); artifact = pathlib.Path(a.artifact); artifact.parent.mkdir(parents=True)
artifact.write_bytes(b"hap\n" + (root / "app/Index.ets").read_bytes() + b"\n" + (root / "shared/policy.ets").read_bytes())
'''


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class HarmonyAssessedWorkspaceBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.workspace = self.root / "assessment/workspace"
        (self.workspace / "app").mkdir(parents=True)
        (self.workspace / "contracts/src").mkdir(parents=True)
        (self.workspace / "app/Index.ets").write_text("Text(policy)\n")
        (self.workspace / "contracts/src/policy.ets").write_text("export const policy = 'Agent output'\n")
        self.state = self.root / "assessment/final-source-state.json"
        state = {}
        for path in sorted(item for item in self.workspace.rglob("*") if item.is_file()):
            state[path.relative_to(self.workspace).as_posix()] = {
                "sha256": digest(path),
                "byteLength": path.stat().st_size,
                "unixMode": path.stat().st_mode & 0o777,
            }
        self.state.write_text(json.dumps(state))
        self.case = self.root / "case.json"
        self.case.write_text(json.dumps({
            "schema": "agentlab.multi_repo_evaluation_case.v1",
            "id": "assessed-harmony-case",
            "status": "frozen-calibrated",
            "sourceSetSha256": "a" * 64,
            "sources": [
                {"id": "app", "repository": "https://example.invalid/app", "revision": "b" * 40},
                {"id": "contracts", "repository": "https://example.invalid/contracts", "revision": "c" * 40},
            ],
            "calibration": {"qualified": True},
            "automaticPromotion": False,
        }))
        common = {
            "taskId": "assessed-harmony-case",
            "sourceSetSha256": "a" * 64,
            "participantId": "agent-profile-a",
            "assessmentStatus": "assessed",
            "infrastructureAvailable": True,
            "subjectTaskSucceeded": True,
        }
        self.summary = self.root / "assessment/summary.json"
        self.summary.write_text(json.dumps({
            **common,
            "schema": "agentlab.multi_repo_assessment_summary.v1",
            "finalWorkspaceSha256": canonical(state),
        }))
        self.decision = self.root / "assessment/decision-package.json"
        self.decision.write_text(json.dumps({
            **common,
            "schema": "agentlab.harness_decision_package.v1",
            "automaticPromotion": False,
        }))
        self.builder = self.root / "builder.py"
        self.builder.write_text(BUILDER)
        self.builder.chmod(0o755)
        self.plan = self.root / "plan.json"
        self.write_plan()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def binding(self, path: pathlib.Path) -> dict:
        return {"path": str(path), "sha256": digest(path)}

    def write_plan(self) -> None:
        self.plan.write_text(json.dumps({
            "schema": "agentlab.harmony_assessed_workspace_build_plan.v1",
            "evaluationCase": self.binding(self.case),
            "assessment": {
                "summary": self.binding(self.summary),
                "decisionPackage": self.binding(self.decision),
                "finalSourceState": self.binding(self.state),
                "workspace": str(self.workspace),
            },
            "sourceMaterialization": [
                {"sourceId": "app", "sourcePath": ".", "targetPath": "app"},
                {"sourceId": "contracts", "sourcePath": "src", "targetPath": "shared"},
            ],
            "build": {
                "executable": str(self.builder),
                "executableSha256": digest(self.builder),
                "arguments": ["--workspace", "{workspace}", "--artifact", "{artifact}"],
                "workingDirectory": ".",
                "artifactPath": "build/output.hap",
                "timeoutSeconds": 30,
                "environment": {},
            },
            "automaticPromotion": False,
        }))

    def run_builder(self, output: pathlib.Path):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--plan", str(self.plan), "--output", str(output)],
            text=True, capture_output=True, check=False,
        )

    def test_assessed_agent_workspace_produces_lineage_bound_hap(self) -> None:
        output = self.root / "build-output"
        completed = self.run_builder(output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads((output / "build-receipt.json").read_text())
        materialization = json.loads((output / "source-materialization.json").read_text())
        self.assertEqual(receipt["buildAuthority"], "independent-harmony-assessed-workspace-build")
        self.assertEqual(receipt["participantId"], "agent-profile-a")
        self.assertEqual(receipt["subjectWorkspaceSha256"], canonical(json.loads(self.state.read_text())))
        self.assertEqual(receipt["assessmentDecisionSha256"], digest(self.decision))
        self.assertEqual(receipt["hapSha256"], digest(output / "artifact.hap"))
        self.assertEqual(materialization["fileCount"], 2)
        self.assertFalse(receipt["automaticPromotion"])

    def test_workspace_drift_is_rejected_before_build(self) -> None:
        (self.workspace / "app/Index.ets").write_text("Text('drift')\n")
        output = self.root / "build-output"
        completed = self.run_builder(output)
        self.assertEqual(completed.returncode, 1)
        failure = json.loads(next(self.root.glob(".build-output.stage-*/failure.json")).read_text())
        self.assertIn("differs from final source state", failure["error"])

    def test_static_oracle_failure_cannot_enter_device_build(self) -> None:
        decision = json.loads(self.decision.read_text())
        decision["subjectTaskSucceeded"] = False
        self.decision.write_text(json.dumps(decision))
        self.write_plan()
        output = self.root / "build-output"
        completed = self.run_builder(output)
        self.assertEqual(completed.returncode, 1)
        failure = json.loads(next(self.root.glob(".build-output.stage-*/failure.json")).read_text())
        self.assertIn("passing workspace", failure["error"])

    @unittest.skipIf(os.name == "nt", "symlink behavior differs on Windows")
    def test_symlink_in_agent_workspace_is_rejected(self) -> None:
        os.symlink(self.workspace / "app/Index.ets", self.workspace / "app/link.ets")
        output = self.root / "build-output"
        completed = self.run_builder(output)
        self.assertEqual(completed.returncode, 1)
        failure = json.loads(next(self.root.glob(".build-output.stage-*/failure.json")).read_text())
        self.assertIn("symbolic link", failure["error"])


if __name__ == "__main__":
    unittest.main()
