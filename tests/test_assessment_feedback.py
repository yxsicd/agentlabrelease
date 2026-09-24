from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


FEEDBACK = load_module(
    "derive_assessment_feedback", ROOT / "scripts/derive-assessment-feedback.py"
)


class AssessmentFeedbackTests(unittest.TestCase):
    source_set = "a" * 64
    method_revision = "2" * 40
    case_id = "multi-repo-retry-policy"

    def write_json(self, path: pathlib.Path, value: dict) -> dict:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n")
        return {
            "path": path.relative_to(path.parents[2]).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "byteLength": path.stat().st_size,
        }

    def fixture(self, root: pathlib.Path):
        calibration = {
            "schema": "agentlab.multi_repo_calibration.v1",
            "candidateId": "difficulty-retry-policy",
            "sourceSetSha256": self.source_set,
            "oracleSha256": "6" * 64,
            "infrastructureAvailable": True,
            "variants": {},
        }
        calibration_bytes = json.dumps(calibration).encode()
        case = {
            "schema": "agentlab.multi_repo_evaluation_case.v1",
            "id": self.case_id,
            "status": "frozen-calibrated",
            "sourceSetSha256": self.source_set,
            "difficultyId": "difficulty-retry-policy",
            "sources": [
                {"id": "contracts", "repository": "https://example.invalid/contracts.git", "revision": "3" * 40},
                {"id": "app", "repository": "https://example.invalid/app.git", "revision": "4" * 40},
            ],
            "oracle": {
                "authority": "independent-executable-oracle",
                "sha256": "6" * 64,
            },
            "calibration": {
                "qualified": True,
                "summarySha256": hashlib.sha256(calibration_bytes).hexdigest(),
            },
            "automaticPromotion": False,
        }
        attempts = []
        for attempt_id, participant, infrastructure, passed, stages in (
            (
                "weak-1",
                "weak",
                True,
                False,
                [
                    {"stageId": "turn-1", "scopeValid": True, "oraclePass": True},
                    {"stageId": "turn-2", "scopeValid": True, "oraclePass": False},
                ],
            ),
            (
                "strong-1",
                "strong",
                True,
                True,
                [
                    {"stageId": "turn-1", "scopeValid": True, "oraclePass": True},
                    {"stageId": "turn-2", "scopeValid": True, "oraclePass": True},
                ],
            ),
            ("infra-1", "weak", False, None, []),
        ):
            decision = {
                "schema": "agentlab.harness_decision_package.v1",
                "taskId": self.case_id,
                "sourceSetSha256": self.source_set,
                "participantId": participant,
                "assessmentStatus": "assessed" if infrastructure else "infrastructure-unavailable",
                "infrastructureAvailable": infrastructure,
                "subjectTaskSucceeded": passed,
                "phaseVerdicts": stages,
                "automaticPromotion": False,
            }
            path = root / "runs" / attempt_id / "decision-package.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(decision, indent=2) + "\n")
            attempts.append(
                {
                    "attemptId": attempt_id,
                    "participantId": participant,
                    "infrastructureValid": infrastructure,
                    "taskPassed": passed,
                    "verdictSource": "independent-harness-decision-package",
                    "evidence": {
                        "decisionPackage": {
                            "path": path.relative_to(root).as_posix(),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "byteLength": path.stat().st_size,
                        }
                    },
                }
            )
        collected = {
            "schema": "agentlab.case_discrimination_input.v2",
            "sourceSetSha256": self.source_set,
            "methodRevision": self.method_revision,
            "cases": [{"id": self.case_id, "attempts": attempts}],
            "collectionPolicy": {"automaticPromotion": False},
        }
        report = {
            "schema": "agentlab.case_discrimination_report.v2",
            "sourceSetSha256": self.source_set,
            "methodRevision": self.method_revision,
            "inputSha256": FEEDBACK.canonical_sha256(collected),
            "ranking": [
                {
                    "caseId": self.case_id,
                    "decision": "high-discrimination-candidate",
                    "eligible": True,
                    "metrics": {"discriminationScore": 1.0},
                }
            ],
            "policy": {"automaticPromotion": False},
        }
        return case, collected, report, calibration

    def test_derives_stage_failure_and_excludes_infrastructure(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            case, collected, report, _ = self.fixture(root)
            result = FEEDBACK.build_feedback(case, collected, report, root)
            self.assertEqual(result["candidateCount"], 1)
            candidate = result["candidates"][0]
            self.assertEqual(candidate["stageId"], "turn-2")
            self.assertEqual(candidate["failureMode"], "oracle-failure")
            self.assertEqual(candidate["validAttemptCount"], 2)
            self.assertEqual(candidate["failingAttemptCount"], 1)
            self.assertFalse(candidate["automaticPromotion"])
            self.assertFalse(candidate["verificationContract"]["caseReady"])
            weak = next(row for row in candidate["participantProfiles"] if row["participantId"] == "weak")
            self.assertEqual(weak["validAttemptCount"], 1)
            self.assertEqual(weak["failureRate"], 1.0)

    def test_rejects_tampered_decision_package(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            case, collected, report, _ = self.fixture(root)
            path = root / collected["cases"][0]["attempts"][0]["evidence"]["decisionPackage"]["path"]
            path.write_text("{}\n")
            with self.assertRaisesRegex(ValueError, "bytes differ"):
                FEEDBACK.build_feedback(case, collected, report, root)

    def test_rejects_report_for_another_attempt_set(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            case, collected, report, _ = self.fixture(root)
            report["inputSha256"] = "f" * 64
            with self.assertRaisesRegex(ValueError, "exact collected input"):
                FEEDBACK.build_feedback(case, collected, report, root)

    def test_flywheel_persists_feedback_as_non_ready_difficulty(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            case, collected, report, calibration = self.fixture(root)
            evidence = root / "evidence"
            evidence.mkdir()
            # Rebase the retained decision paths under the evidence root.
            for attempt in collected["cases"][0]["attempts"]:
                reference = attempt["evidence"]["decisionPackage"]
                source = root / reference["path"]
                target = evidence / reference["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            feedback = FEEDBACK.build_feedback(case, collected, report, evidence)
            (evidence / "summary.json").write_text(
                json.dumps({"taskId": self.case_id, "sourceSetSha256": self.source_set})
            )
            (evidence / "multi-repo-evaluation-case.json").write_text(json.dumps(case))
            (evidence / "multi-repo-calibration.json").write_text(json.dumps(calibration))
            (evidence / "case-discrimination-input.json").write_text(json.dumps(collected))
            (evidence / "case-discrimination-report.json").write_text(json.dumps(report))
            (evidence / "assessment-feedback-candidates.json").write_text(json.dumps(feedback))
            output = root / "transaction.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/build-cbgroom-flywheel-transaction.py"),
                    "--evidence", str(evidence),
                    "--revision", "5" * 40,
                    "--run-id", "feedback-run",
                    "--github-repository", "example/agentlab",
                    "--caller-person-id", "person-test",
                    "--output", str(output),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(output.read_text())
            rows = [
                operation["row"]
                for table in payload["arguments"]["tables"]
                if table["path"] == "difficulty_points"
                for operation in table["operations"]
            ]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["failureMode"], "oracle-failure")
            self.assertFalse(rows[0]["verificationContract"]["caseReady"])
            self.assertFalse(rows[0]["automaticPromotion"])


if __name__ == "__main__":
    unittest.main()
