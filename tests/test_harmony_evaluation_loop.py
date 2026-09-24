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
SCRIPT = ROOT / "scripts/run-harmony-evaluation-loop.py"


BUILD_PROGRAM = r'''#!/usr/bin/env python3
import argparse, hashlib, json, os, pathlib
p = argparse.ArgumentParser(); p.add_argument("--plan", required=True); p.add_argument("--output", required=True); a = p.parse_args()
marker = pathlib.Path(os.environ.get("LOOP_FAIL_MARKER", "/never/fail"))
if os.environ.get("LOOP_FAIL_ONCE") and not marker.exists():
    marker.write_text("failed once"); raise SystemExit(9)
plan_path = pathlib.Path(a.plan); plan = json.loads(plan_path.read_text()); case_path = pathlib.Path(plan["evaluationCase"]["path"])
case = json.loads(case_path.read_text()); out = pathlib.Path(a.output); out.mkdir()
artifact = out / "artifact.hap"; artifact.write_bytes(b"loop-bound-hap")
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
receipt = {"schema":"agentlab.harmony_case_build_receipt.v1","status":"passed","caseId":case["id"],
 "evaluationCaseSha256":digest(case_path),"sourceSetSha256":case["sourceSetSha256"],"sources":case["sources"],
 "planSha256":digest(plan_path),"hapSha256":digest(artifact),"automaticPromotion":False}
(out / "build-receipt.json").write_text(json.dumps(receipt))
'''


RUN_PROGRAM = r'''#!/usr/bin/env python3
import argparse, hashlib, json, os, pathlib
p = argparse.ArgumentParser(); p.add_argument("--plan", required=True); p.add_argument("--output", required=True); a = p.parse_args()
marker = pathlib.Path(os.environ.get("LOOP_RUN_FAIL_MARKER", "/never/fail"))
if os.environ.get("LOOP_RUN_FAIL_ONCE") and not marker.exists():
    marker.write_text("failed once"); raise SystemExit(11)
plan = json.loads(pathlib.Path(a.plan).read_text()); out = pathlib.Path(a.output); out.mkdir()
digest = lambda path: hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
binding = {"schema":"agentlab.harmony_evaluation_binding.v1","status":"passed-review-required",
 "evaluationCaseSha256":plan["evaluationCase"]["sha256"],"buildReceiptSha256":digest(plan["buildReceipt"]["path"]),
 "hapSha256":digest(plan["artifact"]["path"]),"automaticPromotion":False}
(out / "evaluation-binding.json").write_text(json.dumps(binding))
'''


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HarmonyEvaluationLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.case = self.root / "case.json"
        self.case.write_text(json.dumps({
            "schema": "agentlab.multi_repo_evaluation_case.v1",
            "id": "loop-case",
            "status": "frozen-calibrated",
            "sourceSetSha256": "a" * 64,
            "sources": [
                {"id": "app", "repository": "https://example.invalid/app", "revision": "b" * 40},
                {"id": "shared", "repository": "https://example.invalid/shared", "revision": "c" * 40},
            ],
            "calibration": {"qualified": True},
            "automaticPromotion": False,
        }))
        self.build_program = self.executable("build.py", BUILD_PROGRAM)
        self.run_program = self.executable("run.py", RUN_PROGRAM)
        self.build_plan = self.root / "build-plan.json"
        self.build_plan.write_text(json.dumps({
            "schema": "agentlab.harmony_case_build_plan.v1",
            "evaluationCase": {"path": str(self.case), "sha256": digest(self.case)},
            "automaticPromotion": False,
        }))
        self.template = self.root / "run-template.json"
        self.template.write_text(json.dumps({
            "schema": "agentlab.harmony_evaluation_run_template.v1",
            "evaluationCase": {"path": str(self.case), "sha256": digest(self.case)},
            "runId": "loop-run",
            "automaticPromotion": False,
        }))
        self.plan = self.root / "loop-plan.json"
        self.plan.write_text(json.dumps({
            "schema": "agentlab.harmony_evaluation_loop_plan.v1",
            "loopId": "synthetic-loop",
            "evaluationCase": {"path": str(self.case), "sha256": digest(self.case)},
            "buildPlan": {"path": str(self.build_plan), "sha256": digest(self.build_plan)},
            "runTemplate": {"path": str(self.template), "sha256": digest(self.template)},
            "buildProgram": {"path": str(self.build_program), "sha256": digest(self.build_program)},
            "runProgram": {"path": str(self.run_program), "sha256": digest(self.run_program)},
            "automaticPromotion": False,
        }))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def executable(self, name: str, source: str) -> pathlib.Path:
        path = self.root / name
        path.write_text(source)
        path.chmod(0o755)
        return path

    def run_loop(self, output: pathlib.Path, env=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--plan", str(self.plan), "--output", str(output)],
            text=True, capture_output=True, check=False, env={**os.environ, **(env or {})},
        )

    def test_build_and_assessment_are_bound_in_one_review_required_receipt(self) -> None:
        output = self.root / "loop-output"
        completed = self.run_loop(output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads((output / "loop-receipt.json").read_text())
        state = json.loads((output / "loop-state.json").read_text())
        generated = json.loads((output / "run-plan.json").read_text())
        self.assertEqual(receipt["status"], "passed-review-required")
        self.assertEqual(receipt["nextGate"], "maintainer-adjudication-and-next-analysis-cut")
        self.assertEqual(state["stages"]["build"]["attempts"], 1)
        self.assertEqual(state["stages"]["emulatorAssessment"]["attempts"], 1)
        self.assertEqual(generated["schema"], "agentlab.harmony_evaluation_run_plan.v1")
        self.assertFalse(receipt["automaticPromotion"])

    def test_failed_build_is_resumable_without_replaying_passed_stages(self) -> None:
        output = self.root / "loop-output"
        marker = self.root / "failed-once"
        env = {"LOOP_FAIL_ONCE": "1", "LOOP_FAIL_MARKER": str(marker)}
        first = self.run_loop(output, env)
        self.assertEqual(first.returncode, 1)
        failed = json.loads((output / "loop-state.json").read_text())
        self.assertEqual(failed["status"], "failed-resumable")
        self.assertEqual(failed["stages"]["build"]["attempts"], 1)
        second = self.run_loop(output, env)
        self.assertEqual(second.returncode, 0, second.stderr)
        resumed = json.loads((output / "loop-state.json").read_text())
        self.assertEqual(resumed["stages"]["build"]["attempts"], 2)
        self.assertEqual(resumed["stages"]["emulatorAssessment"]["attempts"], 1)

    def test_resume_rejects_plan_drift(self) -> None:
        output = self.root / "loop-output"
        self.assertEqual(self.run_loop(output).returncode, 0)
        plan = json.loads(self.plan.read_text())
        plan["loopId"] = "changed-loop"
        self.plan.write_text(json.dumps(plan))
        changed = self.run_loop(output)
        self.assertEqual(changed.returncode, 1)
        self.assertIn("existing loop state", changed.stderr)

    def test_failed_assessment_resumes_without_rebuilding(self) -> None:
        output = self.root / "loop-output"
        marker = self.root / "assessment-failed-once"
        env = {"LOOP_RUN_FAIL_ONCE": "1", "LOOP_RUN_FAIL_MARKER": str(marker)}
        first = self.run_loop(output, env)
        self.assertEqual(first.returncode, 1)
        failed = json.loads((output / "loop-state.json").read_text())
        self.assertEqual(failed["stages"]["build"]["status"], "passed")
        self.assertEqual(failed["stages"]["build"]["attempts"], 1)
        self.assertEqual(failed["stages"]["emulatorAssessment"]["attempts"], 1)
        second = self.run_loop(output, env)
        self.assertEqual(second.returncode, 0, second.stderr)
        resumed = json.loads((output / "loop-state.json").read_text())
        self.assertEqual(resumed["stages"]["build"]["attempts"], 1)
        self.assertEqual(resumed["stages"]["emulatorAssessment"]["attempts"], 2)


if __name__ == "__main__":
    unittest.main()
