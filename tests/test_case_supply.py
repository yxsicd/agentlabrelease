from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from case_supply import (  # noqa: E402
    build_qualification_receipt,
    derived_program_analysis_source,
    validate_case_source,
    validate_case_supply,
)


SPEC = importlib.util.spec_from_file_location(
    "summarize_case_supply", ROOT / "scripts/summarize-case-supply.py"
)
SUMMARY = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(SUMMARY)


class CaseSupplyTests(unittest.TestCase):
    def source(self, candidate_id: str = "candidate-a") -> dict:
        return derived_program_analysis_source(
            candidate_id=candidate_id,
            source_set_sha256="a" * 64,
            difficulty_evidence_sha256="b" * 64,
            candidate_sha256="c" * 64,
        )

    def case(self, candidate_id: str = "candidate-a", case_id: str = "case-a") -> dict:
        source = self.source(candidate_id)
        matrix = {
            "schema": "agentlab.case_qualification_matrix.v1",
            "caseId": case_id,
            "status": "functional-calibration-qualified-runtime-and-freshness-pending",
            "review": {"qualifiedForCalibration": True},
            "automaticPromotion": False,
        }
        receipt = build_qualification_receipt(
            case_id=case_id,
            candidate_id=candidate_id,
            case_source=source,
            qualification_matrix=matrix,
            calibration_sha256="d" * 64,
        )
        return {
            "schema": "agentlab.multi_repo_evaluation_case.v1",
            "id": case_id,
            "difficultyId": candidate_id,
            "sourceSetSha256": "a" * 64,
            "status": "frozen-calibrated",
            "automaticPromotion": False,
            "caseSource": source,
            "qualificationMatrix": matrix,
            "qualificationReceipt": receipt,
            "calibration": {"qualified": True, "summarySha256": "d" * 64},
            "lineage": {},
        }

    def test_receipt_keeps_functional_and_end_to_end_qualification_distinct(self) -> None:
        case = self.case()
        result = validate_case_supply(case)
        self.assertTrue(result["functionalQualification"])
        self.assertFalse(result["endToEndQualification"])
        self.assertEqual(case["qualificationReceipt"]["gates"]["device"], "pending-separate-gate")
        self.assertEqual(case["qualificationReceipt"]["gates"]["semanticReview"], "qualified")

    def test_legacy_unreviewed_calibration_is_not_functionally_qualified(self) -> None:
        case = self.case()
        case["qualificationMatrix"]["review"] = {
            "status": "legacy-unreviewed",
            "qualifiedForCalibration": False,
        }
        case["qualificationReceipt"] = build_qualification_receipt(
            case_id=case["id"],
            candidate_id=case["difficultyId"],
            case_source=case["caseSource"],
            qualification_matrix=case["qualificationMatrix"],
            calibration_sha256="d" * 64,
        )
        result = validate_case_supply(case)
        self.assertFalse(result["functionalQualification"])
        self.assertEqual(case["qualificationReceipt"]["status"], "calibration-qualified-review-pending")

    def test_source_lane_and_strategy_must_be_coherent(self) -> None:
        source = self.source()
        source["lane"] = "natural"
        with self.assertRaisesRegex(ValueError, "natural case source strategy"):
            validate_case_source(source)

    def test_receipt_rejects_matrix_drift(self) -> None:
        case = self.case()
        case["qualificationMatrix"]["caseId"] = "tampered"
        with self.assertRaisesRegex(ValueError, "matrix digest differs"):
            validate_case_supply(case)

    def test_supply_report_uses_selected_candidates_as_denominator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected_source = {
                "lane": "derived",
                "strategy": "semantic-program-analysis",
                "authority": "exact-difficulty-evidence",
            }
            cohort = {
                "schema": "agentlab.multi_repo_candidate_cohort.v1",
                "cohortId": "cohort-a",
                "selectedCandidates": [
                    {"id": "candidate-a", "candidateSha256": "c" * 64, "caseSource": selected_source},
                    {"id": "candidate-b", "candidateSha256": "e" * 64, "caseSource": selected_source},
                ],
                "selectedCandidateCount": 2,
                "automaticPromotion": False,
            }
            cohort_path = root / "cohort.json"
            cohort_path.write_text(json.dumps(cohort, sort_keys=True) + "\n")
            cohort_sha256 = hashlib.sha256(cohort_path.read_bytes()).hexdigest()
            case = self.case()
            case["lineage"]["candidateCohort"] = {
                "cohortId": "cohort-a",
                "cohortSha256": cohort_sha256,
                "candidateId": "candidate-a",
            }
            case_path = root / "case.json"
            case_path.write_text(json.dumps(case, sort_keys=True) + "\n")
            report = SUMMARY.summarize(cohort_path, [case_path], "f" * 40)
            self.assertEqual(report["denominators"]["selectedCandidateCount"], 2)
            self.assertEqual(report["denominators"]["unconvertedCandidateCount"], 1)
            self.assertEqual(report["denominators"]["functionalCaseYieldRate"], 0.5)
            self.assertEqual(report["denominators"]["endToEndCaseYieldRate"], 0.0)
            self.assertEqual(report["laneCoverage"]["observedLanes"], ["derived"])
            self.assertEqual(report["laneCoverage"]["unobservedLanes"], ["natural"])
            self.assertFalse(report["laneCoverage"]["allPlannedLanesObserved"])
            self.assertTrue(report["qualificationBoundary"]["adjudicationIsNotCaseQualification"])

    def test_schema_files_are_retained(self) -> None:
        for name, expected in (
            ("case-source.schema.json", "agentlab.case_source.v1"),
            ("case-qualification-receipt.schema.json", "agentlab.case_qualification_receipt.v1"),
            ("case-supply-report.schema.json", "agentlab.case_supply_report.v1"),
        ):
            schema = json.loads((ROOT / "schemas" / name).read_text())
            self.assertEqual(schema["properties"]["schema"]["const"], expected)


if __name__ == "__main__":
    unittest.main()
