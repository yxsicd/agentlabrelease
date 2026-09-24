from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run-multi-repo-assessment.py"
PREPARE = ROOT / "scripts/prepare-multi-repo-construction-fixture.py"
PARTICIPANT = ROOT / "examples/multi-repo-case/mock-assessed-agent.py"
ORACLE = ROOT / "examples/multi-repo-case/oracle.mjs"


class MultiRepoAssessmentTests(unittest.TestCase):
    source_set = "a" * 64

    def prepare(self, root: pathlib.Path):
        subprocess.run(
            [
                "python3",
                str(PREPARE),
                "--source",
                str(ROOT / "examples/multi-repo-case/baseline"),
                "--output",
                str(root / "input"),
            ],
            check=True,
            capture_output=True,
        )
        manifest_path = root / "input/manifest.json"
        manifest = json.loads(manifest_path.read_text())
        contract = json.loads(
            (ROOT / "examples/multi-repo-case/oracle-contract.json").read_text()
        )
        case = {
            "schema": "agentlab.multi_repo_evaluation_case.v1",
            "id": "multi-repo-retry-policy",
            "status": "frozen-calibrated",
            "title": "Preserve retry ownership across repositories",
            "sourceSetSha256": self.source_set,
            "sources": [
                {
                    "id": row["id"],
                    "repository": row["repository"],
                    "revision": row["revision"],
                }
                for row in manifest["repositories"]
            ],
            "allowedEdits": [
                {"repositoryId": "contracts", "path": "src/policy.ts"},
                {"repositoryId": "service", "path": "src/reservation.ts"},
                {"repositoryId": "app", "path": "src/checkout.ts"},
            ],
            "stages": [
                {
                    "id": stage,
                    "demand": "Implement the frozen behavior for " + stage,
                    "checkIds": [
                        row["id"] for row in contract["checks"] if row["stage"] == stage
                    ],
                }
                for stage in contract["stageOrder"]
            ],
            "oracle": {
                "sha256": hashlib.sha256(ORACLE.read_bytes()).hexdigest(),
                "receiptSchema": "agentlab.multi_repo_oracle_receipt.v1",
            },
            "automaticPromotion": False,
        }
        case_path = root / "case.json"
        case_path.write_text(json.dumps(case))
        return manifest_path, case_path

    def run_attempt(
        self,
        root: pathlib.Path,
        manifest: pathlib.Path,
        case: pathlib.Path,
        profile: str,
    ):
        output = root / "runs" / profile
        environment = dict(os.environ)
        environment["AGENTLAB_MOCK_ASSESSED_PROFILE"] = profile
        completed = subprocess.run(
            [
                "python3",
                str(RUNNER),
                "--case",
                str(case),
                "--manifest",
                str(manifest),
                "--oracle",
                str(ORACLE),
                "--participant",
                str(PARTICIPANT),
                "--participant-id",
                "mock-" + profile,
                "--output",
                str(output),
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            preexec_fn=(lambda: os.umask(0o002)) if os.name == "posix" else None,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return output, json.loads((output / "summary.json").read_text())

    def test_staged_attempts_flow_into_v2_discrimination(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            manifest, case = self.prepare(root)
            baseline, baseline_summary = self.run_attempt(
                root, manifest, case, "baseline"
            )
            reference, reference_summary = self.run_attempt(
                root, manifest, case, "reference"
            )
            self.assertFalse(baseline_summary["subjectTaskSucceeded"])
            self.assertTrue(reference_summary["subjectTaskSucceeded"])
            self.assertEqual(len(reference_summary["stages"]), 2)
            self.assertTrue(
                all(row["scopeValid"] for row in reference_summary["stages"])
            )
            final_state = json.loads(
                (reference / "final-source-state.json").read_text()
            )
            self.assertTrue(final_state)
            self.assertTrue(
                all(
                    row["unixMode"] in {0o644, 0o755}
                    for row in final_state.values()
                )
            )

            calibration = root / "calibration"
            subprocess.run(
                [
                    "python3",
                    str(ROOT / "examples/multi-repo-case/calibrate.py"),
                    "--baseline",
                    str(ROOT / "examples/multi-repo-case/baseline"),
                    "--reference",
                    str(ROOT / "examples/multi-repo-case/reference"),
                    "--source-set-sha256",
                    self.source_set,
                    "--candidate-id",
                    "fixture-candidate",
                    "--output",
                    str(calibration),
                ],
                check=True,
                capture_output=True,
            )
            collection = {
                "schema": "agentlab.case_attempt_collection.v2",
                "sourceSetSha256": self.source_set,
                "methodRevision": "2" * 40,
                "cases": [
                    {
                        "id": "multi-repo-retry-policy",
                        "calibration": "calibration/summary.json",
                        "attempts": [
                            {
                                "attemptId": "baseline-1",
                                "participantId": "mock-baseline",
                                "evidence": baseline.relative_to(root).as_posix(),
                            },
                            {
                                "attemptId": "reference-1",
                                "participantId": "mock-reference",
                                "evidence": reference.relative_to(root).as_posix(),
                            },
                        ],
                    }
                ],
            }
            collection_path = root / "attempts.json"
            collection_path.write_text(json.dumps(collection))
            discrimination_input = root / "discrimination-input.json"
            subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts/collect-case-attempts.py"),
                    "--manifest",
                    str(collection_path),
                    "--output",
                    str(discrimination_input),
                ],
                check=True,
                capture_output=True,
            )
            report_path = root / "report.json"
            subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts/score-case-discrimination.py"),
                    "--input",
                    str(discrimination_input),
                    "--output",
                    str(report_path),
                    "--required-trials",
                    "1",
                ],
                check=True,
                capture_output=True,
            )
            report = json.loads(report_path.read_text())
            self.assertEqual(report["sourceSetSha256"], self.source_set)
            self.assertEqual(report["eligibleCaseIds"], ["multi-repo-retry-policy"])
            self.assertEqual(
                report["ranking"][0]["metrics"]["discriminationScore"], 1.0
            )

    def test_scope_drift_is_an_assessed_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            manifest, case = self.prepare(root)
            output, summary = self.run_attempt(root, manifest, case, "scope-drift")
            self.assertEqual(summary["assessmentStatus"], "assessed")
            self.assertFalse(summary["subjectTaskSucceeded"])
            self.assertIn(
                "participant-note.txt", summary["stages"][0]["unauthorizedPaths"]
            )
            decision = json.loads((output / "decision-package.json").read_text())
            self.assertTrue(decision["infrastructureAvailable"])
            self.assertFalse(decision["subjectTaskSucceeded"])


if __name__ == "__main__":
    unittest.main()
