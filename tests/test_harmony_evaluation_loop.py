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
(out / "project").mkdir()
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
receipt = {"schema":"agentlab.harmony_case_build_receipt.v1","status":"passed","caseId":case["id"],
 "evaluationCaseSha256":digest(case_path),"sourceSetSha256":case["sourceSetSha256"],"sources":case["sources"],
 "planSha256":digest(plan_path),"hapSha256":digest(artifact),"buildAuthority":"independent-harmony-build","automaticPromotion":False}
if plan["schema"] == "agentlab.harmony_assessed_workspace_build_plan.v1":
    receipt.update({"buildAuthority":"independent-harmony-assessed-workspace-build","participantId":"agent-profile-a",
      "subjectWorkspaceSha256":"1"*64,"assessmentSummarySha256":"2"*64,
      "assessmentDecisionSha256":"3"*64,"finalSourceStateSha256":"4"*64,
      "materializedProjectPath":"project"})
(out / "build-receipt.json").write_text(json.dumps(receipt))
'''


STANDARD_PROGRAM = r'''#!/usr/bin/env python3
import argparse, hashlib, json, os, pathlib
p = argparse.ArgumentParser(); p.add_argument("--plan", required=True); p.add_argument("--output", required=True); a = p.parse_args()
marker = pathlib.Path(os.environ.get("LOOP_STANDARD_FAIL_MARKER", "/never/fail"))
if os.environ.get("LOOP_STANDARD_FAIL_ONCE") and not marker.exists():
    marker.write_text("failed once"); raise SystemExit(12)
plan = json.loads(pathlib.Path(a.plan).read_text()); build_path = pathlib.Path(plan["buildReceipt"]["path"]); build = json.loads(build_path.read_text())
out = pathlib.Path(a.output); out.mkdir(); digest=lambda path: hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
passed = not os.environ.get("LOOP_STANDARD_SUBJECT_FAIL")
assessed={key:build.get(key) for key in ("participantId","subjectWorkspaceSha256","assessmentSummarySha256","assessmentDecisionSha256","finalSourceStateSha256")}
receipt={"schema":"agentlab.harmony_assessed_standard_test_receipt.v1","status":"passed-review-required" if passed else "assessed-failure-review-required",
 "caseId":"loop-case","evaluationCaseSha256":plan["evaluationCase"]["sha256"],"sourceSetSha256":"a"*64,
 "buildReceiptSha256":digest(build_path),"subjectTaskSucceeded":passed,"failureClass":"none" if passed else "standard-test",
 "assessedWorkspace":assessed,"automaticPromotion":False}
(out / "receipt.json").write_text(json.dumps(receipt))
'''


RUN_PROGRAM = r'''#!/usr/bin/env python3
import argparse, hashlib, json, os, pathlib
p = argparse.ArgumentParser(); p.add_argument("--plan", required=True); p.add_argument("--output", required=True); a = p.parse_args()
marker = pathlib.Path(os.environ.get("LOOP_RUN_FAIL_MARKER", "/never/fail"))
if os.environ.get("LOOP_RUN_FAIL_ONCE") and not marker.exists():
    marker.write_text("failed once"); raise SystemExit(11)
plan = json.loads(pathlib.Path(a.plan).read_text()); build = json.loads(pathlib.Path(plan["buildReceipt"]["path"]).read_text()); out = pathlib.Path(a.output); out.mkdir()
digest = lambda path: hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
binding = {"schema":"agentlab.harmony_evaluation_binding.v1","status":"passed-review-required",
 "evaluationCaseSha256":plan["evaluationCase"]["sha256"],"buildReceiptSha256":digest(plan["buildReceipt"]["path"]),
 "hapSha256":digest(plan["artifact"]["path"]),"buildAuthority":build["buildAuthority"],
 "subjectTaskSucceeded":True,"failureClass":"none","automaticPromotion":False}
if os.environ.get("LOOP_SUBJECT_FAIL"):
    binding.update({"status":"assessed-failure-review-required","subjectTaskSucceeded":False,"failureClass":"oracle"})
if build["buildAuthority"] == "independent-harmony-assessed-workspace-build":
    binding["assessedWorkspace"] = {key: build[key] for key in ("participantId","subjectWorkspaceSha256",
      "assessmentSummarySha256","assessmentDecisionSha256","finalSourceStateSha256")}
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
        self.standard_program = self.executable("standard.py", STANDARD_PROGRAM)
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
        self.standard_template = self.root / "standard-template.json"
        self.standard_template.write_text(json.dumps({
            "schema": "agentlab.harmony_assessed_standard_test_template.v1",
            "evaluationCase": {"path": str(self.case), "sha256": digest(self.case)},
            "automaticPromotion": False,
        }))
        self.plan = self.root / "loop-plan.json"
        self.plan.write_text(json.dumps({
            "schema": "agentlab.harmony_evaluation_loop_plan.v1",
            "loopId": "synthetic-loop",
            "evaluationCase": {"path": str(self.case), "sha256": digest(self.case)},
            "buildPlan": {"path": str(self.build_plan), "sha256": digest(self.build_plan)},
            "standardTestTemplate": {"path": str(self.standard_template), "sha256": digest(self.standard_template)},
            "runTemplate": {"path": str(self.template), "sha256": digest(self.template)},
            "buildProgram": {"path": str(self.build_program), "sha256": digest(self.build_program)},
            "standardTestProgram": {"path": str(self.standard_program), "sha256": digest(self.standard_program)},
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
        self.assertEqual(state["stages"]["standardTest"]["attempts"], 1)
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

    def test_assessed_workspace_lineage_survives_the_resumable_loop(self) -> None:
        build_plan = json.loads(self.build_plan.read_text())
        build_plan["schema"] = "agentlab.harmony_assessed_workspace_build_plan.v1"
        self.build_plan.write_text(json.dumps(build_plan))
        loop_plan = json.loads(self.plan.read_text())
        loop_plan["buildPlan"]["sha256"] = digest(self.build_plan)
        self.plan.write_text(json.dumps(loop_plan))
        output = self.root / "loop-output"
        completed = self.run_loop(output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads((output / "loop-receipt.json").read_text())
        self.assertEqual(
            receipt["buildAuthority"],
            "independent-harmony-assessed-workspace-build",
        )
        self.assertEqual(receipt["assessedWorkspace"]["participantId"], "agent-profile-a")
        self.assertEqual(receipt["assessedWorkspace"]["subjectWorkspaceSha256"], "1" * 64)

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
        self.assertEqual(resumed["stages"]["standardTest"]["attempts"], 1)
        self.assertEqual(resumed["stages"]["emulatorAssessment"]["attempts"], 2)

    def test_standard_test_failure_is_terminal_and_skips_device_performance(self) -> None:
        output = self.root / "loop-output"
        completed = self.run_loop(output, {"LOOP_STANDARD_SUBJECT_FAIL": "1"})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads((output / "loop-receipt.json").read_text())
        state = json.loads((output / "loop-state.json").read_text())
        self.assertEqual(receipt["failureClass"], "standard-test")
        self.assertFalse(receipt["subjectTaskSucceeded"])
        self.assertEqual(state["stages"]["standardTest"]["status"], "assessed-failure")
        self.assertEqual(state["stages"]["emulatorAssessment"]["status"], "pending")
        self.assertFalse((output / "assessment").exists())

    def test_assessed_device_failure_is_terminal_evidence_not_retryable_infrastructure(self) -> None:
        output = self.root / "loop-output"
        completed = self.run_loop(output, {"LOOP_SUBJECT_FAIL": "1"})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads((output / "loop-receipt.json").read_text())
        state = json.loads((output / "loop-state.json").read_text())
        self.assertEqual(receipt["status"], "assessed-failure-review-required")
        self.assertFalse(receipt["subjectTaskSucceeded"])
        self.assertEqual(state["stages"]["emulatorAssessment"]["status"], "assessed-failure")
        repeated = self.run_loop(output, {"LOOP_SUBJECT_FAIL": "1"})
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        state = json.loads((output / "loop-state.json").read_text())
        self.assertEqual(state["stages"]["emulatorAssessment"]["attempts"], 1)


if __name__ == "__main__":
    unittest.main()
