from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.test_blind_case_review import build_cut, qualified_verdicts


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "yxsicd/agentlabrelease"
WORKFLOW = ".github/workflows/blind-case-independent-review.yml"
HEAD_SHA = "a" * 40


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


REVIEW = load_module("authenticated_review_base", ROOT / "scripts/review-blind-case-cut.py")
AUTH = load_module("authenticated_review", ROOT / "scripts/authenticate-blind-case-review.py")
ASSESSMENT = load_module(
    "authenticated_review_assessment", ROOT / "scripts/run-multi-repo-assessment.py"
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_metadata(reviewer: str, run_id: int, attempt: int = 1) -> dict:
    return {
        "id": run_id,
        "run_attempt": attempt,
        "repository": {"full_name": REPOSITORY},
        "path": WORKFLOW,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": HEAD_SHA,
        "status": "completed",
        "conclusion": "success",
        "actor": {"login": reviewer},
        "triggering_actor": {"login": reviewer},
    }


def attestation(decision_path: Path, run_id: int, attempt: int = 1) -> list[dict]:
    return [
        {
            "verificationResult": {
                "statement": {
                    "predicateType": "https://slsa.dev/provenance/v1",
                    "subject": [
                        {
                            "name": decision_path.name,
                            "digest": {"sha256": sha(decision_path)},
                        }
                    ],
                    "predicate": {
                        "runDetails": {
                            "metadata": {
                                "invocationId": (
                                    f"https://github.com/{REPOSITORY}/actions/runs/"
                                    f"{run_id}/attempts/{attempt}"
                                )
                            }
                        }
                    },
                }
            }
        }
    ]


class AuthenticatedBlindCaseReviewTests(unittest.TestCase):
    def test_workflows_require_oidc_attestation_and_exact_main_revision(self):
        review = (
            ROOT / ".github/workflows/blind-case-independent-review.yml"
        ).read_text()
        adjudication = (
            ROOT / ".github/workflows/blind-case-review-adjudication.yml"
        ).read_text()
        action = "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6"
        for workflow in (review, adjudication):
            self.assertIn("id-token: write", workflow)
            self.assertIn("attestations: write", workflow)
            self.assertIn("artifact-metadata: write", workflow)
            self.assertIn("github.ref == 'refs/heads/main'", workflow)
            self.assertIn(action, workflow)
        self.assertIn("--reviewer \"$GITHUB_ACTOR\"", review)
        self.assertIn("test \"$GITHUB_ACTOR\" != \"$CONSTRUCTOR\"", review)
        self.assertIn("gh attestation verify", adjudication)
        self.assertIn("--signer-workflow", adjudication)
        self.assertIn("--source-ref refs/heads/main", adjudication)
        self.assertIn("--source-digest \"$GITHUB_SHA\"", adjudication)
        self.assertIn("--deny-self-hosted-runners", adjudication)
        self.assertIn("test \"$FIRST_RUN_ID\" != \"$SECOND_RUN_ID\"", adjudication)
        campaign = (
            ROOT / ".github/workflows/multi-repo-assessed-campaign.yml"
        ).read_text()
        self.assertIn("authenticated_review_run_id:", campaign)
        self.assertIn("attestations: write", campaign)
        self.assertIn("artifact-metadata: write", campaign)
        self.assertIn("id-token: write", campaign)
        self.assertIn(action, campaign)
        self.assertIn("case-discrimination-report.json", campaign)
        self.assertIn("authenticate-blind-case-review.py verify-online", campaign)
        self.assertIn("--verification-output", campaign)
        self.assertIn("--authenticated-review-bundle", campaign)

    def test_assessment_requires_runtime_and_authenticated_review_gates(self):
        blind = {"participantManifestSha256": "a" * 64}
        runtime = {
            "filesystemIsolationQualified": True,
            "externalCredentialIsolationQualified": True,
            "networkEgressIsolationQualified": True,
            "executor": "docker",
            "imageId": "sha256:" + "b" * 64,
        }
        review = {
            "reviewConsensusQualified": True,
            "reviewerIdentityAuthenticationQualified": True,
            "attestedWorkflowProvenanceQualified": True,
            "semanticLeakReviewConsensusQualified": True,
            "contaminationRiskReviewConsensusQualified": True,
            "blindPilotReviewQualified": True,
            "modelTrainingExclusionQualified": False,
            "eligibleForUnseenAgentDiscrimination": False,
        }
        qualified = ASSESSMENT.blind_dispatch_qualification(blind, runtime, review)
        self.assertTrue(qualified["blindAssessmentQualified"])
        self.assertTrue(qualified["semanticLeakReviewQualified"])
        self.assertTrue(qualified["contaminationRiskReviewQualified"])
        self.assertFalse(qualified["unseenAgentDiscriminationQualified"])
        for field in (
            "filesystemIsolationQualified",
            "externalCredentialIsolationQualified",
            "networkEgressIsolationQualified",
        ):
            changed = dict(runtime)
            changed[field] = False
            self.assertFalse(
                ASSESSMENT.blind_dispatch_qualification(
                    blind, changed, review
                )["blindAssessmentQualified"]
            )
        for field in (
            "blindPilotReviewQualified",
            "reviewerIdentityAuthenticationQualified",
            "attestedWorkflowProvenanceQualified",
        ):
            changed = dict(review)
            changed[field] = False
            self.assertFalse(
                ASSESSMENT.blind_dispatch_qualification(
                    blind, runtime, changed
                )["blindAssessmentQualified"]
            )

    def prepare(self, root: Path):
        cut = build_cut(root)
        request = root / "request.json"
        REVIEW.prepare_request(cut, "constructor-a", request)
        rows = []
        for index, reviewer in enumerate(("reviewer-a", "reviewer-b"), start=1):
            decision = root / f"{reviewer}.json"
            REVIEW.create_decision(
                request,
                sha(request),
                reviewer,
                qualified_verdicts(),
                "Reviewed exact cut evidence independently.",
                [hashlib.sha256((reviewer + "-evidence").encode()).hexdigest()],
                decision,
            )
            run_id = 1000 + index
            metadata = root / f"{reviewer}-run.json"
            verification = root / f"{reviewer}-attestation.json"
            metadata.write_text(json.dumps(run_metadata(reviewer, run_id)))
            verification.write_text(json.dumps(attestation(decision, run_id)))
            rows.append((reviewer, decision, metadata, verification, run_id))
        return cut, request, rows

    def authenticate_row(self, root: Path, request: Path, row):
        reviewer, decision, metadata, verification, _run_id = row
        output = root / f"{reviewer}-provenance.json"
        AUTH.authenticate(
            request_path=request,
            decision_path=decision,
            run_metadata_path=metadata,
            attestation_verification_path=verification,
            repository=REPOSITORY,
            workflow_path=WORKFLOW,
            expected_head_sha=HEAD_SHA,
            output=output,
        )
        return output

    def test_verified_runs_and_attestations_qualify_reviewer_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cut, request, rows = self.prepare(root)
            provenances = [self.authenticate_row(root, request, row) for row in rows]
            output = root / "authenticated-adjudication.json"
            result = AUTH.authenticated_adjudicate(
                cut_root=cut,
                request_path=request,
                review_paths=[row[1] for row in rows],
                provenance_paths=provenances,
                repository=REPOSITORY,
                workflow_path=WORKFLOW,
                expected_head_sha=HEAD_SHA,
                output=output,
            )
            self.assertEqual(
                AUTH.validate_authenticated_adjudication(
                    path=output,
                    cut_root=cut,
                    request_path=request,
                    review_paths=[row[1] for row in rows],
                    provenance_paths=provenances,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    expected_head_sha=HEAD_SHA,
                ),
                result,
            )
            self.assertTrue(result["reviewerIdentityAuthenticationQualified"])
            self.assertTrue(result["attestedWorkflowProvenanceQualified"])
            self.assertTrue(result["blindPilotReviewQualified"])
            self.assertFalse(result["eligibleForUnseenAgentDiscrimination"])

    def test_online_consumer_reverifies_final_adjudication_attestation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cut, request, rows = self.prepare(root)
            provenances = [self.authenticate_row(root, request, row) for row in rows]
            bundle = root / "bundle"
            (bundle / "source").mkdir(parents=True)
            shutil.copytree(cut, bundle / "source/blind-cut")
            shutil.copy2(request, bundle / "request.json")
            for label, row, provenance in zip(("first", "second"), rows, provenances):
                (bundle / f"{label}/artifact").mkdir(parents=True)
                shutil.copy2(row[1], bundle / f"{label}/artifact/decision.json")
                shutil.copy2(provenance, bundle / f"{label}/provenance.json")
            final_path = bundle / "authenticated-adjudication.json"
            AUTH.authenticated_adjudicate(
                cut_root=bundle / "source/blind-cut",
                request_path=bundle / "request.json",
                review_paths=[
                    bundle / "first/artifact/decision.json",
                    bundle / "second/artifact/decision.json",
                ],
                provenance_paths=[
                    bundle / "first/provenance.json",
                    bundle / "second/provenance.json",
                ],
                repository=REPOSITORY,
                workflow_path=WORKFLOW,
                expected_head_sha=HEAD_SHA,
                output=final_path,
            )
            final_run_id = 2001
            final_run = run_metadata("adjudicator", final_run_id)
            final_run["path"] = AUTH.ADJUDICATION_WORKFLOW_PATH
            final_verification = attestation(final_path, final_run_id)
            verification_output = root / "online-verification.json"
            with patch.object(
                AUTH,
                "verified_command",
                side_effect=[final_run, final_verification],
            ) as verified:
                result = AUTH.verify_authenticated_bundle_online(
                    bundle,
                    REPOSITORY,
                    final_run_id,
                    verification_output,
                )
            self.assertEqual(verified.call_count, 2)
            self.assertTrue(result["blindPilotReviewQualified"])
            self.assertTrue(result["reviewerIdentityAuthenticationQualified"])
            retained = json.loads(verification_output.read_text())
            self.assertEqual(
                retained["schema"],
                "agentlab.blind_case_online_attestation_verification.v1",
            )
            self.assertEqual(retained["workflowRunId"], final_run_id)
            self.assertEqual(retained["subjectSha256"], sha(final_path))
            self.assertTrue(retained["policy"]["denySelfHostedRunners"])
            self.assertEqual(retained["verification"], final_verification)

    def test_run_actor_must_equal_the_decision_reviewer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _cut, request, rows = self.prepare(root)
            row = rows[0]
            metadata = json.loads(row[2].read_text())
            metadata["actor"]["login"] = "someone-else"
            row[2].write_text(json.dumps(metadata))
            with self.assertRaisesRegex(AUTH.AuthenticationError, "authenticated run actor"):
                self.authenticate_row(root, request, row)

    def test_attestation_must_bind_the_exact_run_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _cut, request, rows = self.prepare(root)
            row = rows[0]
            row[3].write_text(json.dumps(attestation(row[1], row[4] + 1)))
            with self.assertRaisesRegex(AUTH.AuthenticationError, "expected workflow run"):
                self.authenticate_row(root, request, row)

    def test_authenticated_reviews_require_distinct_workflow_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cut, request, rows = self.prepare(root)
            second_metadata = run_metadata("reviewer-b", rows[0][4])
            rows[1][2].write_text(json.dumps(second_metadata))
            rows[1][3].write_text(json.dumps(attestation(rows[1][1], rows[0][4])))
            provenances = [self.authenticate_row(root, request, row) for row in rows]
            with self.assertRaisesRegex(AUTH.AuthenticationError, "distinct workflow runs"):
                AUTH.authenticated_adjudicate(
                    cut_root=cut,
                    request_path=request,
                    review_paths=[row[1] for row in rows],
                    provenance_paths=provenances,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    expected_head_sha=HEAD_SHA,
                    output=root / "adjudication.json",
                )

    def test_review_workflow_revision_is_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _cut, request, rows = self.prepare(root)
            metadata = json.loads(rows[0][2].read_text())
            metadata["head_sha"] = "b" * 40
            rows[0][2].write_text(json.dumps(metadata))
            with self.assertRaisesRegex(AUTH.AuthenticationError, "revision differs"):
                self.authenticate_row(root, request, rows[0])

    def test_tampered_provenance_breaks_authenticated_adjudication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cut, request, rows = self.prepare(root)
            provenances = [self.authenticate_row(root, request, row) for row in rows]
            output = root / "authenticated-adjudication.json"
            AUTH.authenticated_adjudicate(
                cut_root=cut,
                request_path=request,
                review_paths=[row[1] for row in rows],
                provenance_paths=provenances,
                repository=REPOSITORY,
                workflow_path=WORKFLOW,
                expected_head_sha=HEAD_SHA,
                output=output,
            )
            value = json.loads(provenances[0].read_text())
            value["workflowRunId"] += 99
            provenances[0].write_text(json.dumps(value))
            with self.assertRaisesRegex(AUTH.AuthenticationError, "authenticated blind review adjudication differs"):
                AUTH.validate_authenticated_adjudication(
                    path=output,
                    cut_root=cut,
                    request_path=request,
                    review_paths=[row[1] for row in rows],
                    provenance_paths=provenances,
                    repository=REPOSITORY,
                    workflow_path=WORKFLOW,
                    expected_head_sha=HEAD_SHA,
                )


if __name__ == "__main__":
    unittest.main()
