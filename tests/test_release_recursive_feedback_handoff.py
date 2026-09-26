from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/prepare-release-recursive-feedback.py"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PREPARE = load_module("prepare_release_recursive_feedback", SCRIPT)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class ReleaseRecursiveFeedbackHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.revision = "4" * 40
        self.source_set = "7" * 64
        self.case_id = "harmony-case"
        self.campaign_id = "alpha12-release"
        self.closure = self.write(
            "closure.json",
            {
                "schema": "agentlab.release_closure.v1",
                "status": "developer-preview-candidate",
                "releaseTag": "v0.1.0-alpha.12",
                "sources": {"releaseGitSha": self.revision},
            },
        )
        self.discrimination_value = {
            "schema": "agentlab.case_discrimination_report.v2",
            "sourceSetSha256": self.source_set,
            "methodRevision": self.revision,
            "ranking": [
                {
                    "caseId": self.case_id,
                    "decision": "high-discrimination-candidate",
                    "eligible": True,
                    "validAttemptCount": 2,
                    "metrics": {
                        "discriminationScore": 1.0,
                        "observedExtremePassRateWilson95Separated": False,
                    },
                    "processMeasurement": {
                        "harmonyDevice": {
                            "performanceObservationCount": 1,
                            "repeatablePerformanceProfileCount": 0,
                            "performanceFeedbackQualified": False,
                            "performanceAuthority": {
                                "relativePerformance": "smartperf-emulator-proxy",
                                "absolutePowerThermal": "unavailable-on-emulator",
                                "functional": "none",
                            },
                        }
                    },
                }
            ],
            "policy": {"automaticPromotion": False},
        }
        self.discrimination = self.write("discrimination.json", self.discrimination_value)
        self.feedback_value = {
            "schema": "agentlab.assessment_feedback_candidates.v1",
            "caseId": self.case_id,
            "sourceSetSha256": self.source_set,
            "methodRevision": self.revision,
            "discriminationReportSha256": canonical_digest(self.discrimination_value),
            "candidateCount": 1,
            "candidates": [
                {
                    "id": "assessment-feedback-case",
                    "caseId": self.case_id,
                    "dimensionId": "assessed-agent-stage-failure",
                    "primaryDimension": "evaluation-feedback",
                    "stageId": "harmony-device",
                    "failureMode": "oracle-failure",
                    "mechanism": "oracle-failure at frozen stage harmony-device",
                    "status": "candidate",
                    "maturityState": "candidate",
                    "validAttemptCount": 2,
                    "failingAttemptCount": 1,
                    "caseSelection": {
                        "decision": "high-discrimination-candidate",
                        "eligible": True,
                        "discriminationScore": 1.0,
                    },
                    "verificationContract": {
                        "caseReady": False,
                        "required": [
                            "maintainer-adjudication",
                            "new-source-and-analysis-cut",
                            "independent-oracle-calibration",
                        ],
                    },
                    "automaticPromotion": False,
                }
            ],
            "policy": {"automaticPromotion": False},
        }
        self.prior_case = self.write(
            "prior-case.json",
            {
                "schema": "agentlab.multi_repo_evaluation_case.v1",
                "status": "frozen-calibrated",
                "id": self.case_id,
                "sourceSetSha256": self.source_set,
                "automaticPromotion": False,
            },
        )
        self.feedback_value["caseSha256"] = canonical_digest(
            json.loads(self.prior_case.read_text())
        )
        self.feedback = self.write("feedback.json", self.feedback_value)
        self.summary = self.write(
            "summary.json",
            {
                "schema": "agentlab.harmony_assessed_campaign_summary.v1",
                "status": "assessed-review-required",
                "campaignId": self.campaign_id,
                "caseId": self.case_id,
                "sourceSetSha256": self.source_set,
                "methodRevision": self.revision,
                "feedbackCandidateCount": 1,
                "assessmentFeedbackSha256": digest(self.feedback),
                "discriminationReportSha256": digest(self.discrimination),
                "automaticPromotion": False,
            },
        )
        self.acceptance = self.write(
            "acceptance.json",
            {
                "schema": "agentlab.release_harmony_acceptance.v1",
                "status": "accepted-developer-preview-review-required",
                "releaseTag": "v0.1.0-alpha.12",
                "releaseGitSha": self.revision,
                "closure": {"sha256": digest(self.closure)},
                "campaign": {
                    "campaignId": self.campaign_id,
                    "summarySha256": digest(self.summary),
                    "caseId": self.case_id,
                    "sourceSetSha256": self.source_set,
                },
                "automaticPromotion": False,
            },
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, value: dict) -> pathlib.Path:
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return path

    def prepare(self):
        return PREPARE.prepare(
            self.closure,
            self.acceptance,
            self.summary,
            self.prior_case,
            self.feedback,
            self.discrimination,
        )

    def test_prepares_exact_review_only_next_analysis_handoff(self) -> None:
        value = self.prepare()
        self.assertEqual(value["schema"], "agentlab.release_recursive_feedback_handoff.v1")
        self.assertEqual(value["status"], "next-analysis-review-required")
        self.assertEqual(value["discrimination"]["score"], 1.0)
        self.assertFalse(value["discrimination"]["wilson95Separated"])
        self.assertEqual(value["performanceBoundary"]["observationCount"], 1)
        self.assertFalse(value["performanceBoundary"]["qualifiedForRecursivePerformanceFeedback"])
        self.assertEqual(value["evidence"]["assessmentFeedback"]["sha256"], digest(self.feedback))
        self.assertEqual(value["portableEvidence"]["priorCase"]["sha256"], digest(self.prior_case))
        self.assertEqual(
            value["portableEvidence"]["assessmentFeedback"]["fileName"],
            "assessment-feedback-candidates.json",
        )
        self.assertEqual(value["nextAnalysis"]["proposer"], "scripts/propose-feedback-analysis-cut.py")
        self.assertFalse(value["automaticPromotion"])

    def test_tampered_feedback_bytes_are_rejected(self) -> None:
        value = json.loads(self.feedback.read_text())
        value["candidates"][0]["mechanism"] = "tampered"
        self.write("feedback.json", value)
        with self.assertRaisesRegex(ValueError, "campaign feedback digest differs"):
            self.prepare()

    def test_acceptance_must_bind_exact_campaign_summary(self) -> None:
        value = json.loads(self.acceptance.read_text())
        value["campaign"]["summarySha256"] = "0" * 64
        self.write("acceptance.json", value)
        with self.assertRaisesRegex(ValueError, "acceptance campaign summary digest differs"):
            self.prepare()

    def test_candidate_cannot_auto_promote(self) -> None:
        value = json.loads(self.feedback.read_text())
        value["candidates"][0]["automaticPromotion"] = True
        self.feedback = self.write("feedback-promoted.json", value)
        summary = json.loads(self.summary.read_text())
        summary["assessmentFeedbackSha256"] = digest(self.feedback)
        self.summary = self.write("summary-promoted.json", summary)
        acceptance = json.loads(self.acceptance.read_text())
        acceptance["campaign"]["summarySha256"] = digest(self.summary)
        self.acceptance = self.write("acceptance-promoted.json", acceptance)
        with self.assertRaisesRegex(ValueError, "may not auto-promote"):
            self.prepare()

    def test_schema_retains_review_and_non_promotion_boundaries(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/release-recursive-feedback-handoff.schema.json").read_text()
        )
        self.assertEqual(
            schema["properties"]["status"]["const"], "next-analysis-review-required"
        )
        self.assertFalse(schema["properties"]["automaticPromotion"]["const"])
        self.assertEqual(
            schema["properties"]["nextAnalysis"]["properties"]["requiredChange"]["const"],
            "new-source-set-or-method-revision",
        )


if __name__ == "__main__":
    unittest.main()
