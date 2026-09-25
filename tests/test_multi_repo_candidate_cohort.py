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


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PROPOSER = load_module("candidate_cohort_proposer", ROOT / "scripts/propose-multi-repo-candidate-cohort.py")
REVIEW = load_module("candidate_cohort_review", ROOT / "scripts/review-multi-repo-candidate-cohort.py")
SELECT = load_module("candidate_cohort_select", ROOT / "scripts/select-multi-repo-cohort-candidate.py")
CASE_GENERATOR = load_module("candidate_cohort_case_generator", ROOT / "scripts/generate-multi-repo-case.py")


class MultiRepoCandidateCohortTests(unittest.TestCase):
    def fixture(self, root: Path):
        candidates = [
            {
                "id": "candidate-deep",
                "schema": "agentlab.difficulty_point.v1",
                "dimensionId": "multi-repository-change-impact",
                "status": "candidate",
                "maturityState": "candidate",
                "seed": {"repositoryId": "contracts", "path": "src/policy.ts"},
                "affectedFiles": [
                    {"repositoryId": "contracts", "path": "src/policy.ts", "dependencyDepth": 0},
                    {"repositoryId": "service", "path": "src/service.ts", "dependencyDepth": 1},
                    {"repositoryId": "app", "path": "src/app.ts", "dependencyDepth": 2},
                ],
                "affectedRepositoryCount": 3,
                "maxDependencyDepth": 2,
                "automaticPromotion": False,
            },
            {
                "id": "candidate-shared-api",
                "schema": "agentlab.difficulty_point.v1",
                "dimensionId": "multi-repository-change-impact",
                "relationType": "shared-external-api-call-contract",
                "status": "candidate",
                "maturityState": "candidate",
                "seed": {"specifier": "@kit.ArkWeb", "callTarget": "initialize"},
                "affectedFiles": [
                    {"repositoryId": "app", "path": "src/a.ts", "dependencyDepth": 1},
                    {"repositoryId": "service", "path": "src/b.ts", "dependencyDepth": 1},
                ],
                "affectedRepositoryCount": 2,
                "maxDependencyDepth": 1,
                "automaticPromotion": False,
            },
            {
                "id": "candidate-unresolved",
                "schema": "agentlab.difficulty_point.v1",
                "dimensionId": "unresolved-module-boundary",
                "status": "candidate",
                "maturityState": "candidate",
                "automaticPromotion": False,
            },
        ]
        difficulty = root / "difficulty.json"
        difficulty.write_text(json.dumps({
            "schema": "agentlab.difficulty_candidates.v2",
            "sourceSetSha256": "a" * 64,
            "sources": [
                {"id": "app", "repository": "repo-app", "revision": "1" * 40},
                {"id": "service", "repository": "repo-service", "revision": "2" * 40},
                {"id": "contracts", "repository": "repo-contracts", "revision": "3" * 40},
            ],
            "candidates": candidates,
            "automaticPromotion": False,
        }, sort_keys=True) + "\n")
        proposal_value = PROPOSER.propose(difficulty, "cohort-1", "4" * 40)
        proposal = root / "proposal.json"
        proposal.write_text(json.dumps(proposal_value, sort_keys=True) + "\n")
        return difficulty, proposal, candidates

    def reviewed(self, root: Path):
        difficulty, proposal, candidates = self.fixture(root)
        proposal_sha = hashlib.sha256(proposal.read_bytes()).hexdigest()
        review_value = REVIEW.decide(
            proposal,
            proposal_sha,
            "candidate-deep,candidate-shared-api",
            "reviewer-a",
            "candidate-to-case-yield,sampling-frame-coverage,selection-bias",
            "Predeclared diversity across depth and relation strata.",
        )
        review = root / "review.json"
        review.write_text(json.dumps(review_value, sort_keys=True) + "\n")
        cohort_value = REVIEW.compile_cohort(proposal, review)
        cohort = root / "cohort.json"
        cohort.write_text(json.dumps(cohort_value, sort_keys=True) + "\n")
        return difficulty, proposal, review, cohort, candidates

    def test_proposal_retains_denominator_exclusions_and_strata(self):
        with tempfile.TemporaryDirectory() as directory:
            difficulty, proposal, _ = self.fixture(Path(directory))
            value = json.loads(proposal.read_text())
            self.assertEqual(value["samplingFrame"]["eligibleCount"], 2)
            self.assertEqual(value["samplingFrame"]["excludedCount"], 1)
            self.assertEqual(value["excludedCandidates"], [{
                "id": "candidate-unresolved",
                "reason": "outside-multi-repository-change-impact-dimension",
            }])
            self.assertEqual(value["samplingFrame"]["strata"]["maxDependencyDepth"], {"1": 1, "2": 1})
            self.assertFalse(value["samplingFrame"]["declaredRepresentative"])
            self.assertEqual(value["difficultyEvidenceSha256"], hashlib.sha256(difficulty.read_bytes()).hexdigest())

    def test_module_candidate_advises_narrower_api_call_without_changing_denominator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            difficulty, _, candidates = self.fixture(root)
            value = json.loads(difficulty.read_text())
            module = {
                **candidates[1],
                "id": "candidate-shared-module",
                "relationType": "shared-external-module-contract",
                "seed": {"specifier": "@kit.ArkWeb"},
            }
            value["candidates"].append(module)
            difficulty.write_text(json.dumps(value, sort_keys=True) + "\n")
            proposal = PROPOSER.propose(difficulty, "cohort-advisory", "5" * 40)
            rows = {row["id"]: row for row in proposal["eligibleCandidates"]}
            advisory = rows["candidate-shared-module"]["selectionAdvisory"]
            self.assertEqual(advisory["classification"], "prefer-narrower-api-call")
            self.assertEqual(advisory["narrowerApiCandidates"], [{
                "id": "candidate-shared-api",
                "callTarget": "initialize",
                "affectedFileCount": 2,
                "coverage": "equal-file-set",
            }])
            self.assertEqual(proposal["samplingFrame"]["eligibleCount"], 3)
            self.assertEqual(
                proposal["samplingFrame"]["selectionAdvisoryCounts"]["prefer-narrower-api-call"],
                1,
            )
            shortlist = {row["id"]: row for row in proposal["reviewShortlist"]["candidates"]}
            self.assertIn("candidate-shared-api", shortlist)
            self.assertIn(
                "equal-file-set-replacement-for-smallest-deferred-module",
                shortlist["candidate-shared-api"]["selectionRoles"],
            )
            self.assertEqual(proposal["reviewShortlist"]["status"], "review-required")

    def test_reviewed_member_resolves_against_exact_difficulty_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            difficulty, _, _, cohort, _ = self.reviewed(root)
            cohort_sha = hashlib.sha256(cohort.read_bytes()).hexdigest()
            selected = SELECT.select(cohort, difficulty, cohort_sha, "candidate-deep")
            self.assertEqual(selected["schema"], "agentlab.multi_repo_candidate_selection.v2")
            self.assertEqual(selected["candidateId"], "candidate-deep")
            self.assertEqual(selected["proposalMethodRevision"], "4" * 40)
            self.assertEqual(selected["caseSource"]["lane"], "derived")
            self.assertEqual(selected["caseSource"]["strategy"], "semantic-program-analysis")
            self.assertFalse(selected["declaredRepresentative"])

    def test_review_rejects_single_or_unknown_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, proposal, _ = self.fixture(root)
            proposal_sha = hashlib.sha256(proposal.read_bytes()).hexdigest()
            with self.assertRaisesRegex(REVIEW.CohortReviewError, "at least two"):
                REVIEW.decide(proposal, proposal_sha, "candidate-deep", "reviewer", "candidate-to-case-yield,sampling-frame-coverage,selection-bias", "rationale")
            with self.assertRaisesRegex(REVIEW.CohortReviewError, "ineligible or unknown"):
                REVIEW.decide(proposal, proposal_sha, "candidate-deep,unknown", "reviewer", "candidate-to-case-yield,sampling-frame-coverage,selection-bias", "rationale")

    def test_selection_rejects_difficulty_tampering_and_nonmember(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            difficulty, _, _, cohort, candidates = self.reviewed(root)
            cohort_sha = hashlib.sha256(cohort.read_bytes()).hexdigest()
            with self.assertRaisesRegex(SELECT.SelectionError, "not a member"):
                SELECT.select(cohort, difficulty, cohort_sha, "candidate-unresolved")
            value = json.loads(difficulty.read_text())
            value["candidates"][0]["maxDependencyDepth"] = 9
            difficulty.write_text(json.dumps(value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(SELECT.SelectionError, "difficulty evidence digest differs"):
                SELECT.select(cohort, difficulty, cohort_sha, candidates[0]["id"])

    def test_compile_rejects_hand_edited_review_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, proposal, review, _, _ = self.reviewed(root)
            value = json.loads(review.read_text())
            value["reviewer"] = ""
            review.write_text(json.dumps(value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(REVIEW.CohortReviewError, "reviewer is absent"):
                REVIEW.compile_cohort(proposal, review)

    def test_workflows_split_proposal_review_and_secret_bearing_construction(self):
        proposal = (ROOT / ".github/workflows/multi-repo-candidate-cohort.yml").read_text()
        review = (ROOT / ".github/workflows/multi-repo-candidate-cohort-review.yml").read_text()
        construction = (ROOT / ".github/workflows/multi-repo-model-construction.yml").read_text()
        golden = (ROOT / "examples/multi-repo-case/run-golden-path.py").read_text()
        self.assertIn("scripts/propose-multi-repo-candidate-cohort.py", proposal)
        self.assertIn('--proposal-method-revision "$GITHUB_SHA"', proposal)
        self.assertIn('"--proposal-method-revision", args.method_revision', golden)
        self.assertIn("analysis_run_id", proposal)
        self.assertIn("scripts/multi-repo-analysis-run.py validate", proposal)
        self.assertNotIn("prepare-multi-repo-construction-fixture.py", proposal)
        self.assertNotIn("AGENTLAB_LM_GATEWAY_KEY", proposal + review)
        self.assertIn("scripts/review-multi-repo-candidate-cohort.py decide", review)
        self.assertIn("scripts/review-multi-repo-candidate-cohort.py compile", review)
        self.assertIn(".github/workflows/multi-repo-candidate-cohort.yml", review)
        self.assertIn(".github/workflows/multi-repo-candidate-cohort-review.yml", construction)
        self.assertIn("scripts/select-multi-repo-cohort-candidate.py", construction)
        self.assertIn("construction_contract_review_run_id", construction)
        self.assertIn("scripts/multi-repo-construction-contract.py validate", construction)
        self.assertNotIn("prepare-multi-repo-construction-fixture.py", construction)
        self.assertNotIn('row["seed"]["repositoryId"] == "contracts"', construction)
        self.assertEqual(construction.count("secrets.AGENTLAB_LM_GATEWAY_KEY"), 1)

    def test_retained_real_shortlist_is_specificity_aware_and_review_required(self):
        path = (
            ROOT
            / "release/qualifications/harmony-real-multi-repo-34661ff/current-method-proposal.json"
        )
        value = json.loads(path.read_text())
        self.assertEqual(value["status"], "analysis-reproduced-cohort-review-required")
        self.assertNotEqual(value["methodRevision"], value["proposalMethodRevision"])
        advisories = value["samplingFrame"]["selectionAdvisoryCounts"]
        self.assertEqual(sum(advisories.values()), value["samplingFrame"]["eligibleCount"])
        self.assertEqual(advisories["prefer-narrower-api-call"], 19)
        candidates = value["proposedCandidates"]
        self.assertEqual(len(candidates), 6)
        self.assertEqual(len({row["id"] for row in candidates}), 6)
        roles = {role for row in candidates for role in row["selectionRoles"]}
        self.assertIn("equal-file-set-replacement-for-smallest-deferred-module", roles)
        self.assertFalse(value["samplingFrame"]["declaredRepresentative"])
        self.assertFalse(value["automaticPromotion"])

    def test_frozen_case_lineage_binds_exact_selection_and_difficulty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            difficulty, _, _, cohort, _ = self.reviewed(root)
            cohort_sha = hashlib.sha256(cohort.read_bytes()).hexdigest()
            selection_value = SELECT.select(cohort, difficulty, cohort_sha, "candidate-deep")
            selection = root / "selection.json"
            selection.write_text(json.dumps(selection_value, sort_keys=True) + "\n")
            lineage = CASE_GENERATOR.candidate_cohort_lineage(
                selection, difficulty, "candidate-deep", "a" * 64
            )
            self.assertEqual(lineage["cohortSha256"], cohort_sha)
            self.assertEqual(
                lineage["selectionSha256"],
                hashlib.sha256(selection.read_bytes()).hexdigest(),
            )
            value = json.loads(difficulty.read_text())
            value["candidates"][0]["maxDependencyDepth"] = 10
            difficulty.write_text(json.dumps(value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(ValueError, "difficulty evidence differs"):
                CASE_GENERATOR.candidate_cohort_lineage(
                    selection, difficulty, "candidate-deep", "a" * 64
                )


if __name__ == "__main__":
    unittest.main()
