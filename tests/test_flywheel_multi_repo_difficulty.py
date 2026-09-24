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
