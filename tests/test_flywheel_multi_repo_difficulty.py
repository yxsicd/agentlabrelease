import json
import hashlib
import subprocess
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build-cbgroom-flywheel-transaction.py"


class MultiRepoDifficultyFlywheelTests(unittest.TestCase):
    def run_builder(self, evidence, output):
        return subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--evidence",
                str(evidence),
                "--revision",
                "f" * 40,
                "--run-id",
                "run-multi-repo",
                "--github-repository",
                "example/agentlab",
                "--caller-person-id",
                "person-test",
                "--output",
                str(output),
            ],
            text=True,
            capture_output=True,
        )

    def evidence(self, automatic_promotion=False):
        sources = [
            {
                "id": "app",
                "repository": "https://example.invalid/app.git",
                "revision": "2" * 40,
            },
            {
                "id": "shared",
                "repository": "https://example.invalid/shared.git",
                "revision": "3" * 40,
            },
        ]
        module_bindings = {
            "@example/shared": {"repositoryId": "shared", "path": "src/shared.ts"}
        }
        source_set = {
            "schema": "agentlab.multi_repo_source_set.v1",
            "repositories": sources,
            "moduleBindings": module_bindings,
        }
        source_set_sha256 = hashlib.sha256(
            json.dumps(source_set, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "schema": "agentlab.difficulty_candidates.v2",
            "sourceSetSha256": source_set_sha256,
            "sources": sources,
            "moduleBindings": module_bindings,
            "automaticPromotion": automatic_promotion,
            "candidates": [
                {
                    "id": "difficulty-stable",
                    "dimensionId": "multi-repository-change-impact",
                    "primaryDimension": "program-analysis",
                    "mechanism": "recursive reverse dependency closure crosses repository boundaries",
                    "status": "candidate",
                    "maturityState": "candidate",
                    "seed": {"repositoryId": "shared", "path": "src/shared.ts"},
                    "affectedFiles": [
                        {"repositoryId": "shared", "path": "src/shared.ts", "dependencyDepth": 0},
                        {"repositoryId": "app", "path": "src/main.ts", "dependencyDepth": 1},
                    ],
                    "evidenceIds": ["module-edge-1"],
                    "verificationContract": {
                        "caseReady": False,
                        "required": ["behavior oracle"],
                    },
                    "automaticPromotion": False,
                }
            ],
        }

    def test_persists_source_set_without_collapsing_to_one_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "evidence"
            evidence.mkdir()
            (evidence / "difficulty-candidates.json").write_text(
                json.dumps(self.evidence())
            )
            calibration = {
                "schema": "agentlab.multi_repo_calibration.v1",
                "candidateId": "difficulty-stable",
                "sourceSetSha256": self.evidence()["sourceSetSha256"],
                "oracleSha256": "4" * 64,
                "infrastructureAvailable": True,
                "variants": {},
            }
            calibration_bytes = json.dumps(calibration).encode()
            (evidence / "multi-repo-calibration.json").write_bytes(calibration_bytes)
            construction = {
                "schema": "agentlab.multi_repo_intent_construction_receipt.v1",
                "status": "candidate-unverified",
                "participantId": "builder-fixture-v1",
                "participantSha256": "5" * 64,
                "sourceSetSha256": self.evidence()["sourceSetSha256"],
                "candidateId": "difficulty-stable",
                "semanticKnowledgeVerified": False,
                "automaticPromotion": False,
            }
            construction_bytes = json.dumps(construction).encode()
            (evidence / "multi-repo-construction-receipt.json").write_bytes(
                construction_bytes
            )
            quality = {
                "schema": "agentlab.multi_repo_intent_quality.v1",
                "qualifiedForReview": True,
                "candidateId": "difficulty-stable",
                "sourceSetSha256": self.evidence()["sourceSetSha256"],
                "constructionReceiptSha256": hashlib.sha256(
                    construction_bytes
                ).hexdigest(),
                "policy": {"automaticPromotion": False},
            }
            quality_bytes = json.dumps(quality).encode()
            (evidence / "multi-repo-construction-quality.json").write_bytes(
                quality_bytes
            )
            case = {
                "schema": "agentlab.multi_repo_evaluation_case.v1",
                "id": "case-multi-repo",
                "difficultyId": "difficulty-stable",
                "kind": "task",
                "status": "frozen-calibrated",
                "sourceSetSha256": self.evidence()["sourceSetSha256"],
                "sources": self.evidence()["sources"],
                "stages": [{"id": "turn-1"}, {"id": "turn-2"}],
                "oracle": {
                    "authority": "independent-executable-oracle",
                    "sha256": "4" * 64,
                },
                "calibration": {
                    "qualified": True,
                    "summarySha256": hashlib.sha256(calibration_bytes).hexdigest(),
                },
                "construction": {
                    "status": "candidate-unverified",
                    "participantId": "builder-fixture-v1",
                    "receiptSha256": hashlib.sha256(construction_bytes).hexdigest(),
                    "semanticKnowledgeVerified": False,
                    "automaticPromotion": False,
                },
                "constructionQuality": {
                    "qualifiedForReview": True,
                    "reportSha256": hashlib.sha256(quality_bytes).hexdigest(),
                    "policy": {"automaticPromotion": False},
                },
                "automaticPromotion": False,
            }
            (evidence / "multi-repo-evaluation-case.json").write_text(json.dumps(case))
            output = Path(tmp) / "transaction.json"
            result = self.run_builder(evidence, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text())
            expected_source_set = self.evidence()["sourceSetSha256"]
            tables = {
                row["path"]: row["operations"]
                for row in payload["arguments"]["tables"]
            }
            point = tables["difficulty_points"][0]["row"]
            self.assertNotIn("sourceRevision", point)
            self.assertEqual(point["sourceSetSha256"], expected_source_set)
            self.assertEqual(len(point["sources"]), 2)
            self.assertEqual(point["analysisCandidateId"], "difficulty-stable")
            self.assertFalse(point["verificationContract"]["caseReady"])
            ref = next(
                operation["row"]
                for operation in tables["evidence_refs"]
                if operation["row"]["kind"] == "difficulty-candidates"
            )
            self.assertNotIn("sourceRevision", ref)
            self.assertEqual(ref["sourceSetSha256"], expected_source_set)
            persisted_case = tables["evaluation_cases"][0]["row"]
            self.assertEqual(persisted_case["id"], "case-multi-repo")
            self.assertEqual(persisted_case["sourceSetSha256"], expected_source_set)
            self.assertTrue(persisted_case["calibration"]["qualified"])
            self.assertEqual(
                persisted_case["evidenceIds"],
                [
                    "evidence-run-multi-repo-multi-repo-evaluation-case",
                    "evidence-run-multi-repo-multi-repo-calibration",
                    "evidence-run-multi-repo-multi-repo-construction-receipt",
                    "evidence-run-multi-repo-multi-repo-construction-quality",
                ],
            )
            construction_ref = next(
                operation["row"]
                for operation in tables["evidence_refs"]
                if operation["row"]["kind"]
                == "multi-repo-construction-receipt"
            )
            self.assertEqual(
                construction_ref["sourceSetSha256"], expected_source_set
            )

    def test_rejects_automatic_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "evidence"
            evidence.mkdir()
            (evidence / "difficulty-candidates.json").write_text(
                json.dumps(self.evidence(automatic_promotion=True))
            )
            result = self.run_builder(evidence, Path(tmp) / "transaction.json")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must not auto-promote", result.stderr)


if __name__ == "__main__":
    unittest.main()
