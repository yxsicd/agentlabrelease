from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/prepare-feedback-analysis-request.py"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PREPARE = load_module("prepare_feedback_analysis_request", SCRIPT)


def canonical_digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class FeedbackAnalysisRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.prior_revision = "1" * 40
        self.next_revision = "2" * 40
        self.spec_value = {
            "schema": "agentlab.multi_repo_source_spec.v1",
            "sources": [
                {
                    "id": "app",
                    "repository": "https://github.com/example/app.git",
                    "revision": "3" * 40,
                },
                {
                    "id": "contracts",
                    "repository": "https://github.com/example/contracts.git",
                    "revision": "4" * 40,
                },
            ],
            "moduleBindings": {
                "@example/contracts": {
                    "repositoryId": "contracts",
                    "path": "src/contracts.ts",
                }
            },
            "automaticPromotion": False,
        }
        self.source_identity = {
            "schema": "agentlab.multi_repo_source_set.v1",
            "repositories": self.spec_value["sources"],
            "moduleBindings": self.spec_value["moduleBindings"],
        }
        self.next_source_set = canonical_digest(self.source_identity)
        self.handoff_value = {
            "schema": "agentlab.release_recursive_feedback_handoff.v1",
            "status": "next-analysis-review-required",
            "releaseTag": "v0.1.0-alpha.12",
            "releaseGitSha": self.prior_revision,
            "campaign": {
                "caseId": "prior-case",
                "sourceSetSha256": "a" * 64,
                "methodRevision": self.prior_revision,
            },
            "candidates": [
                {
                    "id": "assessment-feedback-prior",
                    "mechanism": "oracle-failure at frozen stage harmony-device",
                    "automaticPromotion": False,
                    "verificationContract": {
                        "caseReady": False,
                        "required": [
                            "maintainer-adjudication",
                            "new-source-and-analysis-cut",
                            "independent-oracle-calibration",
                        ],
                    },
                }
            ],
            "nextAnalysis": {
                "proposer": "scripts/propose-feedback-analysis-cut.py",
                "requiredChange": "new-source-set-or-method-revision",
            },
            "automaticPromotion": False,
        }
        self.handoff = self.write("handoff.json", self.handoff_value)
        self.source_spec = self.write("source-spec.json", self.spec_value)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, value: dict) -> pathlib.Path:
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return path

    def prepare(self, revision: str | None = None):
        return PREPARE.prepare(
            self.handoff,
            self.source_spec,
            "assessment-feedback-prior",
            revision or self.next_revision,
        )

    def test_binds_feedback_to_new_exact_source_analysis(self) -> None:
        value = self.prepare()
        self.assertEqual(value["schema"], "agentlab.feedback_analysis_request.v1")
        self.assertEqual(value["nextAnalysis"]["sourceSetSha256"], self.next_source_set)
        self.assertTrue(value["nextAnalysis"]["sourceChanged"])
        self.assertTrue(value["nextAnalysis"]["methodChanged"])
        self.assertEqual(
            value["nextAnalysis"]["nextGate"],
            "exact-analysis-then-feedback-analysis-cut-proposal",
        )
        self.assertFalse(value["automaticPromotion"])

    def test_same_source_and_method_are_rejected(self) -> None:
        self.handoff_value["campaign"]["sourceSetSha256"] = self.next_source_set
        self.handoff_value["campaign"]["methodRevision"] = self.next_revision
        self.handoff = self.write("same-handoff.json", self.handoff_value)
        with self.assertRaisesRegex(ValueError, "changes neither source set nor method revision"):
            self.prepare()

    def test_unknown_candidate_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate id is absent"):
            PREPARE.prepare(
                self.handoff,
                self.source_spec,
                "missing-candidate",
                self.next_revision,
            )

    def test_unsafe_source_repository_is_rejected(self) -> None:
        self.spec_value["sources"][0]["repository"] = "file:///tmp/app"
        self.source_spec = self.write("unsafe-source-spec.json", self.spec_value)
        with self.assertRaisesRegex(ValueError, "credential-free HTTPS"):
            self.prepare()

    def test_schema_preserves_review_boundary(self) -> None:
        schema = json.loads((ROOT / "schemas/feedback-analysis-request.schema.json").read_text())
        self.assertEqual(schema["properties"]["status"]["const"], "prepared-review-required")
        self.assertFalse(schema["properties"]["automaticPromotion"]["const"])
        self.assertEqual(
            schema["properties"]["nextAnalysis"]["properties"]["workflow"]["const"],
            ".github/workflows/multi-repo-analysis.yml",
        )

    def test_exact_analysis_workflow_can_bind_optional_feedback(self) -> None:
        workflow = (ROOT / ".github/workflows/multi-repo-analysis.yml").read_text()
        self.assertIn("feedback_handoff_path:", workflow)
        self.assertIn("feedback_candidate_id:", workflow)
        self.assertIn("scripts/prepare-feedback-analysis-request.py", workflow)
        self.assertIn("--next-method-revision \"$GITHUB_SHA\"", workflow)
        self.assertIn("feedback-analysis-request.json", workflow)


if __name__ == "__main__":
    unittest.main()
