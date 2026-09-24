from __future__ import annotations

import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "case_discrimination", ROOT / "scripts/score-case-discrimination.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class CaseDiscriminationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.value = json.loads(
            (ROOT / "examples/case-discrimination/fixture.json").read_text()
        )

    def test_repeatable_separation_ranks_first(self) -> None:
        report = MODULE.build_report(self.value, 3, 0.6)
        first = report["ranking"][0]
        self.assertEqual(first["caseId"], "case-strong-separation")
        self.assertEqual(first["metrics"]["passRateSeparation"], 1.0)
        self.assertEqual(first["metrics"]["withinProfileDeterminism"], 1.0)
        self.assertEqual(first["metrics"]["trialConfidence"], 1.0)
        self.assertEqual(first["metrics"]["discriminationScore"], 1.0)
        self.assertTrue(first["eligible"])
        self.assertFalse(report["policy"]["automaticPromotion"])

    def test_everyone_passing_is_not_discriminating(self) -> None:
        report = MODULE.build_report(self.value, 3, 0.6)
        row = next(r for r in report["ranking"] if r["caseId"] == "case-everyone-passes")
        self.assertEqual(row["metrics"]["passRateSeparation"], 0.0)
        self.assertFalse(row["eligible"])
        self.assertEqual(row["decision"], "low-discrimination-candidate")

    def test_infrastructure_failure_is_excluded_not_scored_as_inability(self) -> None:
        report = MODULE.build_report(self.value, 3, 0.6)
        row = next(r for r in report["ranking"] if r["caseId"] == "case-infrastructure-excluded")
        self.assertEqual(row["excludedAttemptCount"], 1)
        self.assertEqual(row["validAttemptCount"], 2)
        self.assertEqual(row["decision"], "collect-more-evidence")

    def test_failed_negative_calibration_rejects_case(self) -> None:
        case = self.value["cases"][0]
        case["calibration"]["negativeVariants"][0]["observedPass"] = True
        row = MODULE.score_case(case, 3, 0.6)
        self.assertFalse(row["calibrationPassed"])
        self.assertFalse(row["eligible"])
        self.assertEqual(row["decision"], "reject-oracle-calibration")

    def test_duplicate_attempt_identity_is_rejected(self) -> None:
        case = self.value["cases"][0]
        case["attempts"][1]["attemptId"] = case["attempts"][0]["attemptId"]
        with self.assertRaisesRegex(ValueError, "attemptId must be unique"):
            MODULE.score_case(case, 3, 0.6)


if __name__ == "__main__":
    unittest.main()
