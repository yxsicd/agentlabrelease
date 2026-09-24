import copy
import hashlib
import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "case_qualification", ROOT / "scripts/case_qualification.py"
)
QUALIFICATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QUALIFICATION)


class CaseQualificationTest(unittest.TestCase):
    def setUp(self):
        self.stages = [
            {"id": "turn-1", "checkIds": ["repair", "preserve"]},
            {"id": "turn-2", "checkIds": ["later"]},
        ]
        self.calibration = {
            "schema": "agentlab.multi_repo_calibration.v1",
            "candidateId": "difficulty-1",
            "sourceSetSha256": "1" * 64,
            "oracleSha256": "2" * 64,
            "receiptSchema": "agentlab.multi_repo_oracle_receipt.v1",
            "infrastructureAvailable": True,
            "variants": {
                "baseline": {
                    "sourceSha256": "3" * 64,
                    "stages": {
                        "turn-1": {
                            "pass": False,
                            "checks": [
                                {"id": "repair", "pass": False},
                                {"id": "preserve", "pass": True},
                            ],
                        },
                        "turn-2": {
                            "pass": False,
                            "checks": [
                                {"id": "repair", "pass": False},
                                {"id": "preserve", "pass": True},
                                {"id": "later", "pass": False},
                            ],
                        },
                    },
                },
                "reference": {
                    "sourceSha256": "4" * 64,
                    "stages": {
                        "turn-1": {
                            "pass": True,
                            "checks": [
                                {"id": "repair", "pass": True},
                                {"id": "preserve", "pass": True},
                            ],
                        },
                        "turn-2": {
                            "pass": True,
                            "checks": [
                                {"id": "repair", "pass": True},
                                {"id": "preserve", "pass": True},
                                {"id": "later", "pass": True},
                            ],
                        },
                    },
                },
                "wrong-later": {
                    "sourceSha256": "5" * 64,
                    "stages": {
                        "turn-1": {
                            "pass": True,
                            "checks": [
                                {"id": "repair", "pass": True},
                                {"id": "preserve", "pass": True},
                            ],
                        },
                        "turn-2": {
                            "pass": False,
                            "checks": [
                                {"id": "repair", "pass": True},
                                {"id": "preserve", "pass": True},
                                {"id": "later", "pass": False},
                            ],
                        },
                    },
                },
            },
        }
        self.calibration_sha256 = hashlib.sha256(
            (json.dumps(self.calibration, sort_keys=True) + "\n").encode()
        ).hexdigest()
        self.oracle = {
            "authority": "independent-executable-oracle",
            "sha256": "2" * 64,
            "receiptSchema": "agentlab.multi_repo_oracle_receipt.v1",
        }
        self.review = {
            "authority": "explicit-proposal-review",
            "reviewer": "maintainer",
            "proposalSha256": "6" * 64,
            "decisionSha256": "7" * 64,
            "verdict": "approve-for-calibration",
        }

    def make_case(self):
        matrix = QUALIFICATION.build_matrix(
            case_id="case-1",
            source_set_sha256="1" * 64,
            stages=self.stages,
            oracle=self.oracle,
            calibration=self.calibration,
            calibration_sha256=self.calibration_sha256,
            review=self.review,
        )
        return {
            "schema": "agentlab.multi_repo_evaluation_case.v1",
            "id": "case-1",
            "status": "frozen-calibrated",
            "automaticPromotion": False,
            "difficultyId": "difficulty-1",
            "sourceSetSha256": "1" * 64,
            "stages": self.stages,
            "oracle": self.oracle,
            "calibration": {
                "qualified": True,
                "summarySha256": self.calibration_sha256,
            },
            "lineage": {"review": self.review},
            "qualificationMatrix": matrix,
        }

    def test_matrix_derives_repair_and_preservation_without_claiming_runtime(self):
        case = self.make_case()
        result = QUALIFICATION.validate_matrix(
            case, self.calibration, self.calibration_sha256
        )
        self.assertEqual(result["repairChecks"], 2)
        self.assertEqual(result["preservationChecks"], 1)
        self.assertEqual(
            case["qualificationMatrix"]["deviceChecks"]["status"], "separate-gate"
        )
        self.assertFalse(case["qualificationMatrix"]["freshness"]["qualified"])

    def test_tampered_classification_is_rejected(self):
        case = self.make_case()
        case["qualificationMatrix"]["repairChecks"][0]["baselinePass"] = True
        with self.assertRaisesRegex(ValueError, "differs from calibration-derived"):
            QUALIFICATION.validate_matrix(
                case, self.calibration, self.calibration_sha256
            )

    def test_cross_stage_check_drift_is_rejected(self):
        calibration = copy.deepcopy(self.calibration)
        calibration["variants"]["baseline"]["stages"]["turn-2"]["checks"][0][
            "pass"
        ] = True
        with self.assertRaisesRegex(ValueError, "changed across stages"):
            QUALIFICATION.build_matrix(
                case_id="case-1",
                source_set_sha256="1" * 64,
                stages=self.stages,
                oracle=self.oracle,
                calibration=calibration,
                calibration_sha256=self.calibration_sha256,
                review=self.review,
            )

    def test_wrong_variant_that_passes_every_stage_is_rejected(self):
        calibration = copy.deepcopy(self.calibration)
        calibration["variants"]["wrong-later"]["stages"]["turn-2"]["pass"] = True
        calibration["variants"]["wrong-later"]["stages"]["turn-2"]["checks"][2][
            "pass"
        ] = True
        with self.assertRaisesRegex(ValueError, "must fail at least one stage"):
            QUALIFICATION.build_matrix(
                case_id="case-1",
                source_set_sha256="1" * 64,
                stages=self.stages,
                oracle=self.oracle,
                calibration=calibration,
                calibration_sha256=self.calibration_sha256,
                review=self.review,
            )

    def test_schema_is_valid_json_and_release_validator_is_executable(self):
        schema = json.loads(
            (ROOT / "schemas/case-qualification-matrix.schema.json").read_text()
        )
        self.assertEqual(
            schema["properties"]["schema"]["const"],
            "agentlab.case_qualification_matrix.v1",
        )
        self.assertTrue((ROOT / "scripts/validate-case-qualification.py").is_file())


if __name__ == "__main__":
    unittest.main()
