from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/prepare-feedback-semantic-source-selection.py"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PREPARE = load_module("prepare_feedback_semantic_source_selection", SCRIPT)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class FeedbackSemanticSourceSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.app = self.root / "app"
        self.contracts = self.root / "contracts"
        (self.app / "src").mkdir(parents=True)
        (self.contracts / "src").mkdir(parents=True)
        (self.app / "src/PaymentPage.ets").write_text(
            "export function bindPaymentAuthority() { return PaymentReady; }\n"
        )
        (self.contracts / "src/PaymentAuthority.ts").write_text(
            "export interface PaymentAuthority { policy: string }\n"
        )
        app_revision = self.commit(self.app)
        contracts_revision = self.commit(self.contracts)
        self.prior_case = self.write(
            "prior-case.json",
            {
                "schema": "agentlab.multi_repo_evaluation_case.v1",
                "id": "payment-case",
                "title": "Harmony device Oracle separates payment readiness",
                "stages": [
                    {
                        "id": "turn-1",
                        "demand": "Understand and preserve the cross-repository payment authority binding.",
                    },
                    {
                        "id": "turn-2",
                        "demand": "Keep the application ready for the device-visible workflow.",
                    },
                ],
                "automaticPromotion": False,
            },
        )
        self.feedback = self.write(
            "feedback.json",
            {
                "schema": "agentlab.assessment_feedback_candidates.v1",
                "caseId": "payment-case",
                "candidates": [
                    {
                        "id": "feedback-1",
                        "mechanism": "oracle-failure at frozen stage harmony-device",
                        "automaticPromotion": False,
                    }
                ],
                "policy": {"automaticPromotion": False},
            },
        )
        self.handoff = self.write(
            "handoff.json",
            {
                "schema": "agentlab.release_recursive_feedback_handoff.v1",
                "portableEvidence": {
                    "priorCase": {"sha256": digest(self.prior_case)},
                    "assessmentFeedback": {"sha256": digest(self.feedback)},
                },
                "automaticPromotion": False,
            },
        )
        repositories = [
            {
                "id": "app",
                "repository": "https://example.invalid/app.git",
                "revision": app_revision,
                "root": str(self.app),
            },
            {
                "id": "contracts",
                "repository": "https://example.invalid/contracts.git",
                "revision": contracts_revision,
                "root": str(self.contracts),
            },
        ]
        self.manifest = self.write(
            "manifest.json",
            {
                "schema": "agentlab.multi_repo_manifest.v1",
                "repositories": repositories,
                "moduleBindings": {
                    "@demo/payment": {
                        "repositoryId": "contracts",
                        "path": "src/PaymentAuthority.ts",
                    }
                },
            },
        )
        self.source_set = canonical_digest(
            {
                "schema": "agentlab.multi_repo_source_set.v1",
                "repositories": [
                    {key: row[key] for key in ("id", "repository", "revision")}
                    for row in repositories
                ],
                "moduleBindings": json.loads(self.manifest.read_text())["moduleBindings"],
            }
        )
        self.claim_value = {
            "schema": "agentlab.feedback_semantic_source_selection_claim.v1",
            "sourceSetSha256": self.source_set,
            "priorCaseSha256": digest(self.prior_case),
            "feedbackEvidenceSha256": digest(self.feedback),
            "feedbackCandidateId": "feedback-1",
            "reviewer": "maintainer",
            "claims": [
                {
                    "caseAnchor": "Understand and preserve the cross-repository payment authority binding.",
                    "repositoryId": "contracts",
                    "path": "src/PaymentAuthority.ts",
                    "sourceSymbol": "PaymentAuthority",
                    "rationale": "This exact contract symbol carries the authority boundary named by the case.",
                },
                {
                    "caseAnchor": "Keep the application ready for the device-visible workflow.",
                    "repositoryId": "app",
                    "path": "src/PaymentPage.ets",
                    "sourceSymbol": "bindPaymentAuthority",
                    "rationale": "This exact application symbol binds the contract into the device-visible state.",
                },
            ],
            "automaticPromotion": False,
        }
        self.claim = self.write("claim.json", self.claim_value)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, value: dict) -> pathlib.Path:
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return path

    def commit(self, root: pathlib.Path) -> str:
        subprocess.run(["git", "init", "--quiet", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C", str(root),
                "-c", "user.name=AgentLab Test",
                "-c", "user.email=agentlab@example.invalid",
                "commit", "--quiet", "-m", "fixture",
            ],
            check=True,
        )
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def prepare(self):
        return PREPARE.prepare(
            self.handoff,
            self.prior_case,
            self.feedback,
            self.manifest,
            self.claim,
        )

    def test_binds_prior_case_anchors_to_exact_multi_repo_source_bytes(self) -> None:
        value = self.prepare()
        self.assertEqual(value["schema"], "agentlab.feedback_semantic_source_selection.v1")
        self.assertEqual(value["sourceSetSha256"], self.source_set)
        self.assertEqual(value["denominators"]["claimCount"], 2)
        self.assertEqual(value["denominators"]["coveredRepositoryCount"], 2)
        self.assertTrue(value["sourceRelevanceEvidenceBound"])
        self.assertFalse(value["semanticAlignmentVerified"])
        self.assertFalse(value["automaticPromotion"])
        self.assertEqual({row["sourceLine"] for row in value["claims"]}, {1})
        self.assertTrue(all(len(row["sourceBlobOid"]) == 40 for row in value["claims"]))

    def test_missing_exact_source_symbol_is_rejected(self) -> None:
        self.claim_value["claims"][0]["sourceSymbol"] = "MissingAuthority"
        self.claim = self.write("missing-symbol.json", self.claim_value)
        with self.assertRaisesRegex(ValueError, "source symbol is absent"):
            self.prepare()

    def test_uncommitted_worktree_text_is_not_accepted_as_evidence(self) -> None:
        target = self.contracts / "src/PaymentAuthority.ts"
        target.write_text(target.read_text() + "const UncommittedAuthority = true;\n")
        self.claim_value["claims"][0]["sourceSymbol"] = "UncommittedAuthority"
        self.claim = self.write("uncommitted-symbol.json", self.claim_value)
        with self.assertRaisesRegex(ValueError, "source symbol is absent"):
            self.prepare()

    def test_free_form_case_anchor_is_rejected(self) -> None:
        self.claim_value["claims"][0]["caseAnchor"] = "payment-ish"
        self.claim = self.write("free-form-anchor.json", self.claim_value)
        with self.assertRaisesRegex(ValueError, "not exact prior-case language"):
            self.prepare()

    def test_single_repository_claims_are_rejected(self) -> None:
        self.claim_value["claims"][1].update(
            {
                "repositoryId": "contracts",
                "path": "src/PaymentAuthority.ts",
                "sourceSymbol": "PaymentAuthority",
            }
        )
        self.claim = self.write("single-repository.json", self.claim_value)
        with self.assertRaisesRegex(ValueError, "cover at least two repositories"):
            self.prepare()

    def test_tampered_prior_case_is_rejected(self) -> None:
        self.prior_case.write_text(self.prior_case.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "handoff prior case digest differs"):
            self.prepare()

    def test_schemas_preserve_review_only_boundary(self) -> None:
        claim_schema = json.loads(
            (ROOT / "schemas/feedback-semantic-source-selection-claim.schema.json").read_text()
        )
        receipt_schema = json.loads(
            (ROOT / "schemas/feedback-semantic-source-selection.schema.json").read_text()
        )
        self.assertFalse(claim_schema["properties"]["automaticPromotion"]["const"])
        self.assertTrue(receipt_schema["properties"]["sourceRelevanceEvidenceBound"]["const"])
        self.assertFalse(receipt_schema["properties"]["semanticAlignmentVerified"]["const"])
        self.assertFalse(receipt_schema["properties"]["automaticPromotion"]["const"])


if __name__ == "__main__":
    unittest.main()
