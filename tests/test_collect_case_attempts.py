from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


COLLECTOR = load_module("collect_case_attempts", ROOT / "scripts/collect-case-attempts.py")
SCORER = load_module("score_collected_cases", ROOT / "scripts/score-case-discrimination.py")


class CollectCaseAttemptsTests(unittest.TestCase):
    source_revision = "1" * 40
    method_revision = "2" * 40
    case_id = "case-separates-participants"

    def write_json(self, path: pathlib.Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def write_attempt(
        self,
        root: pathlib.Path,
        attempt_id: str,
        passed: bool | None,
        *,
        assessed: bool = True,
        infrastructure: bool = True,
        source_revision: str | None = None,
    ) -> None:
        evidence = root / "runs" / attempt_id
        revision = source_revision or self.source_revision
        self.write_json(
            evidence / "summary.json",
            {"taskId": self.case_id, "sourceRevision": revision},
        )
        self.write_json(
            evidence / "decision-package.json",
            {
                "schema": "agentlab.harness_decision_package.v1",
                "taskId": self.case_id,
                "sourceRevision": revision,
                "assessmentStatus": "assessed" if assessed else "infrastructure-unavailable",
                "infrastructureAvailable": infrastructure,
                "subjectTaskSucceeded": passed,
            },
        )

    def manifest(self, attempts: list[dict]) -> dict:
        return {
            "schema": "agentlab.case_attempt_collection.v1",
            "sourceRevision": self.source_revision,
            "methodRevision": self.method_revision,
            "cases": [
                {
                    "id": self.case_id,
                    "calibration": "calibration.json",
                    "attempts": attempts,
                }
            ],
        }

    def write_calibration(self, root: pathlib.Path) -> None:
        self.write_json(
            root / "calibration.json",
            {
                "infrastructureValid": True,
                "baselineExpectedPass": False,
                "baselineObservedPass": False,
                "referenceExpectedPass": True,
                "referenceObservedPass": True,
                "negativeVariants": [
                    {
                        "id": "wrong-boundary",
                        "expectedPass": False,
                        "observedPass": False,
                        "infrastructureValid": True,
                    }
                ],
            },
        )

    def test_collected_evidence_flows_into_eligible_score(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_calibration(root)
            attempts = []
            for participant, passed in (("strong", True), ("baseline", False)):
                for trial in range(1, 4):
                    attempt_id = f"{participant}-{trial}"
                    self.write_attempt(root, attempt_id, passed)
                    attempts.append(
                        {
                            "attemptId": attempt_id,
                            "participantId": participant,
                            "producerRun": f"run-{attempt_id}",
                            "evidence": f"runs/{attempt_id}",
                        }
                    )
            collected = COLLECTOR.build_input(self.manifest(attempts), root.resolve())
            report = SCORER.build_report(collected, 3, 0.6)
            row = report["ranking"][0]
            self.assertTrue(row["eligible"])
            self.assertEqual(row["metrics"]["discriminationScore"], 1.0)
            self.assertFalse(collected["collectionPolicy"]["automaticPromotion"])
            evidence = collected["cases"][0]["attempts"][0]["evidence"]
            self.assertEqual(len(evidence["summary"]["sha256"]), 64)
            self.assertEqual(len(evidence["decisionPackage"]["sha256"]), 64)

    def test_infrastructure_unavailable_attempt_has_no_failure_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_calibration(root)
            self.write_attempt(
                root,
                "infra-1",
                False,
                assessed=False,
                infrastructure=False,
            )
            collected = COLLECTOR.build_input(
                self.manifest(
                    [
                        {
                            "attemptId": "infra-1",
                            "participantId": "candidate",
                            "evidence": "runs/infra-1",
                        }
                    ]
                ),
                root.resolve(),
            )
            attempt = collected["cases"][0]["attempts"][0]
            self.assertFalse(attempt["infrastructureValid"])
            self.assertIsNone(attempt["taskPassed"])
            row = SCORER.build_report(collected, 3, 0.6)["ranking"][0]
            self.assertEqual(row["excludedAttemptCount"], 1)
            self.assertEqual(row["validAttemptCount"], 0)

    def test_source_revision_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            self.write_calibration(root)
            self.write_attempt(root, "drifted", True, source_revision="3" * 40)
            with self.assertRaisesRegex(ValueError, "sourceRevision mismatch"):
                COLLECTOR.build_input(
                    self.manifest(
                        [
                            {
                                "attemptId": "drifted",
                                "participantId": "candidate",
                                "evidence": "runs/drifted",
                            }
                        ]
                    ),
                    root.resolve(),
                )


if __name__ == "__main__":
    unittest.main()
