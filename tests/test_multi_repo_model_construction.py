import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class MultiRepoModelConstructionTest(unittest.TestCase):
    def test_fixture_git_revisions_are_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = pathlib.Path(temporary)
            revisions = []
            for name in ("first", "second"):
                output = temporary / name
                subprocess.run(
                    [
                        "python3",
                        str(ROOT / "scripts/prepare-multi-repo-construction-fixture.py"),
                        "--source",
                        str(ROOT / "examples/multi-repo-case/baseline"),
                        "--output",
                        str(output),
                    ],
                    check=True,
                    capture_output=True,
                )
                manifest = json.loads((output / "manifest.json").read_text())
                revisions.append({row["id"]: row["revision"] for row in manifest["repositories"]})
            self.assertEqual(revisions[0], revisions[1])
            self.assertEqual(set(revisions[0]), {"app", "contracts", "service"})
            self.assertTrue(all(len(value) == 40 for value in revisions[0].values()))

    def test_workflow_keeps_gateway_secret_on_trusted_main_step(self):
        workflow = (ROOT / ".github/workflows/multi-repo-model-construction.yml").read_text()
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
        self.assertEqual(workflow.count("secrets.AGENTLAB_LM_GATEWAY_KEY"), 1)
        self.assertIn("if: always()", workflow)
        self.assertIn("multi-repo-model-construction", workflow)
        self.assertIn("construction_contract_review_run_id", workflow)
        self.assertIn("expected_construction_contract_sha256", workflow)
        self.assertIn("scripts/multi-repo-construction-contract.py validate", workflow)
        self.assertIn("scripts/prepare-multi-repo-analysis-sources.py", workflow)
        self.assertNotIn("operator-fixture", workflow)
        self.assertNotIn("prepare-multi-repo-construction-fixture.py", workflow)
        self.assertIn("scripts/propose-dependency-discovery-plan.py", workflow)
        self.assertIn("dependency-discovery-plan-proposal.json", workflow)
        self.assertIn("cohort_review_run_id", workflow)
        self.assertIn("expected_cohort_sha256", workflow)
        self.assertIn("scripts/select-multi-repo-cohort-candidate.py", workflow)
        self.assertNotIn('row["seed"]["repositoryId"] == "contracts"', workflow)

    def test_review_and_campaign_workflows_preserve_trusted_boundaries(self):
        review = (ROOT / ".github/workflows/multi-repo-case-review.yml").read_text()
        campaign = (ROOT / ".github/workflows/multi-repo-assessed-campaign.yml").read_text()
        for workflow in (review, campaign):
            self.assertIn("github.ref == 'refs/heads/main'", workflow)
            self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
            self.assertIn('[[ "$SOURCE_RUN_ID" =~ ^[0-9]+$ ]]', workflow)
        self.assertNotIn("secrets.AGENTLAB_LM_GATEWAY_KEY", review)
        self.assertEqual(campaign.count("secrets.AGENTLAB_LM_GATEWAY_KEY"), 1)
        self.assertIn(".github/workflows/multi-repo-model-construction.yml", review)
        self.assertIn(".github/workflows/multi-repo-case-review.yml", campaign)
        self.assertIn('--expected-sha256 "$EXPECTED_PROPOSAL_SHA256"', review)
        self.assertIn('--expected-sha256 "$EXPECTED_DEPENDENCY_PLAN_SHA256"', review)
        self.assertIn('--rationale "$REVIEW_RATIONALE"', review)
        self.assertNotIn("--rationale '${{ inputs.rationale }}'", review)
        self.assertIn("source/operator-fixture/calibrate.py", review)
        self.assertIn("case/source/operator-fixture/oracle.mjs", campaign)
        self.assertIn('[[ "$MODEL_A" != "$MODEL_B" ]]', campaign)
        self.assertIn('--required-trials "$REQUIRED_TRIALS"', campaign)
        self.assertIn("scripts/derive-assessment-feedback.py", campaign)
        self.assertIn("assessment-feedback-candidates.json", campaign)
        self.assertIn("multi-repo-evaluation-case.json", campaign)
        self.assertIn("scripts/prepare-harmony-assessed-handoff.py", campaign)
        self.assertIn("harmony-device-handoff.json", campaign)
        self.assertIn("validate-case-qualification.py", review)
        self.assertIn("scripts/review-dependency-discovery-plan.py decide", review)
        self.assertIn("scripts/review-dependency-discovery-plan.py compile", review)
        self.assertIn("scripts/build-dependency-discovery-contract.py", review)
        self.assertIn("scripts/bind-dependency-discovery-case.py", review)
        self.assertIn("scripts/prepare-multi-repo-blind-cut.py", review)
        self.assertIn('--candidate-selection "$AGENTLAB_ROOT/source/candidate-selection.json"', review)
        self.assertIn('scripts/build-blind-case-cut.py validate', review)
        self.assertIn('scripts/build-blind-case-cut.py stage-participant', campaign)
        self.assertIn('--blind-participant-root "$RUNNER_TEMP/agentlab-blind-participant"', campaign)
        self.assertIn('--blind-dispatch-receipt "$AGENTLAB_ROOT/blind-dispatch-receipt.json"', campaign)
        self.assertIn("scripts/prepare-participant-runtime.py", campaign)
        self.assertIn("scripts/run-pi-in-docker.py", campaign)
        self.assertIn('--participant-runtime-config "$AGENTLAB_ROOT/participant-runtime.json"', campaign)
        self.assertIn('--dependency-contract "$AGENTLAB_ROOT/case/blind-cut/evaluator/dependency-discovery-contract.json"', campaign)
        self.assertIn('--program-facts "$AGENTLAB_ROOT/case/blind-cut/evaluator/program-facts.jsonl"', campaign)
        self.assertIn('--forbid "$AGENTLAB_ROOT/case"', campaign)

    def test_fixture_script_is_release_manifested(self):
        expected = hashlib.sha256(
            (ROOT / "scripts/prepare-multi-repo-construction-fixture.py").read_bytes()
        ).hexdigest()
        entries = {
            path: digest
            for digest, path in (
                line.split("  ", 1)
                for line in (ROOT / "SHA256SUMS").read_text().splitlines()
            )
        }
        self.assertEqual(
            entries.get("scripts/prepare-multi-repo-construction-fixture.py"), expected
        )


if __name__ == "__main__":
    unittest.main()
