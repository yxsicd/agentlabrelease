from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


CONTRACT = load_module(
    "dependency_contract",
    ROOT / "scripts/build-dependency-discovery-contract.py",
)
PROPOSER = load_module(
    "dependency_plan_proposal",
    ROOT / "scripts/propose-dependency-discovery-plan.py",
)
REVIEW = load_module(
    "dependency_plan_review",
    ROOT / "scripts/review-dependency-discovery-plan.py",
)
BINDER = load_module(
    "dependency_case_binding",
    ROOT / "scripts/bind-dependency-discovery-case.py",
)
RUNNER = load_module(
    "dependency_assessment_runner",
    ROOT / "scripts/run-multi-repo-assessment.py",
)


class DependencyDiscoveryContractTests(unittest.TestCase):
    def fixture(self, root: Path):
        case = root / "case.json"
        case.write_text(json.dumps({
            "schema": "agentlab.multi_repo_evaluation_case.v1",
            "id": "dependency-case",
            "difficultyId": "candidate-a",
            "status": "frozen-calibrated",
            "sourceSetSha256": "a" * 64,
            "sources": [
                {"id": "app", "repository": "repo-app", "revision": "1" * 40},
                {"id": "contracts", "repository": "repo-contracts", "revision": "2" * 40},
            ],
            "stages": [{"id": "repair", "demand": "Repair it.", "checkIds": ["check"]}],
            "automaticPromotion": False,
            "lineage": {
                "difficultyEvidenceSha256": "6" * 64,
                "review": {"proposalSha256": "7" * 64},
            },
        }))
        facts = root / "facts.jsonl"
        facts.write_text("".join(json.dumps(row) + "\n" for row in [
            {
                "id": "fact-direct",
                "kind": "module-dependency",
                "sourceRepositoryId": "app",
                "sourcePath": "src/feature.ts",
                "sourceIdentity": "git:repo-app@" + "1" * 40,
                "targetRepositoryId": "contracts",
                "targetPath": "src/policy.ts",
                "targetIdentity": "git:repo-contracts@" + "2" * 40,
            },
            {
                "id": "fact-equivalent",
                "kind": "module-dependency",
                "sourceRepositoryId": "app",
                "sourcePath": "src/alternate.ts",
                "sourceIdentity": "git:repo-app@" + "1" * 40,
                "targetRepositoryId": "contracts",
                "targetPath": "src/policy.ts",
                "targetIdentity": "git:repo-contracts@" + "2" * 40,
            },
        ]))
        plan = root / "plan.json"
        plan.write_text(json.dumps({
            "schema": "agentlab.dependency_discovery_plan.v2",
            "caseId": "dependency-case",
            "candidateId": "candidate-a",
            "sourceSetSha256": "a" * 64,
            "casePlanProposalSha256": "7" * 64,
            "difficultyEvidenceSha256": "6" * 64,
            "programFactsSha256": hashlib.sha256(facts.read_bytes()).hexdigest(),
            "stages": [{
                "stageId": "repair",
                "obligations": [{
                    "id": "policy-consumer",
                    "acceptedFactIds": ["fact-direct", "fact-equivalent"],
                }],
            }],
            "review": {
                "authority": "explicit-dependency-plan-review",
                "reviewer": "reviewer-a",
                "proposalSha256": "4" * 64,
                "decisionSha256": "5" * 64,
                "acknowledgedRiskIds": ["dependency-obligation-fairness"],
                "verdict": "approve-for-contract",
            },
            "automaticPromotion": False,
        }))
        return case, facts, plan

    def test_builds_alternative_revision_bound_claims_and_binds_derived_case(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case, facts, plan = self.fixture(root)
            contract = CONTRACT.build(case, facts, plan)
            self.assertEqual(
                contract["precisionPolicy"],
                "required-obligation-recall-only-extra-claims-unadjudicated",
            )
            accepted = contract["stages"][0]["obligations"][0]["acceptedClaims"]
            self.assertEqual(len(accepted), 2)
            self.assertEqual(
                {row["source"]["path"] for row in accepted},
                {"src/feature.ts", "src/alternate.ts"},
            )
            contract_path = root / "contract.json"
            contract_path.write_text(json.dumps(contract))
            bound = BINDER.bind(case, contract_path, facts)
            self.assertFalse(
                bound["dependencyDiscovery"]["participantEditScopeVisible"]
            )
            self.assertFalse(bound["dependencyDiscovery"]["precisionClaimed"])
            self.assertEqual(
                bound["dependencyDiscovery"]["programFactsSha256"],
                hashlib.sha256(facts.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                bound["lineage"]["dependencyDiscovery"]["baseCaseSha256"],
                hashlib.sha256(case.read_bytes()).hexdigest(),
            )
            measurement = RUNNER.participant_dependency_discovery(
                {
                    "dependencyClaims": [
                        {
                            "relation": "module-dependency",
                            "source": {"repositoryId": "app", "path": "src/alternate.ts"},
                            "target": {"repositoryId": "contracts", "path": "src/policy.ts"},
                            "rationale": "The alternate consumer reaches the same policy boundary.",
                        },
                        {
                            "relation": "module-dependency",
                            "source": {"repositoryId": "app", "path": "src/extra.ts"},
                            "target": {"repositoryId": "contracts", "path": "src/policy.ts"},
                            "rationale": "An additional hypothesis retained for later adjudication.",
                        },
                    ]
                },
                contract["stages"][0]["obligations"],
            )
            self.assertTrue(measurement["coverageQualified"])
            self.assertEqual(measurement["unadjudicatedClaimCount"], 1)
            self.assertFalse(measurement["precisionClaimed"])
            missing = RUNNER.participant_dependency_discovery(
                {}, contract["stages"][0]["obligations"]
            )
            self.assertEqual(missing["submissionStatus"], "missing")
            self.assertFalse(missing["measurementQualified"])
            self.assertFalse(missing["coverageQualified"])
            invalid = RUNNER.participant_dependency_discovery(
                {
                    "dependencyClaimSubmission": {
                        "status": "invalid",
                        "source": "native-final-assistant-message",
                        "error": "malformed marker",
                    }
                },
                contract["stages"][0]["obligations"],
            )
            self.assertEqual(invalid["submissionStatus"], "invalid")
            self.assertEqual(invalid["validationError"], "malformed marker")
            self.assertFalse(invalid["measurementQualified"])

    def test_rejects_program_fact_revision_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case, facts, plan = self.fixture(root)
            rows = [json.loads(line) for line in facts.read_text().splitlines()]
            rows[0]["sourceIdentity"] = "git:repo-app@" + "f" * 40
            facts.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with self.assertRaisesRegex(CONTRACT.ContractError, "source revision differs"):
                CONTRACT.build(case, facts, plan)

    def test_recursive_evidence_becomes_explicitly_reviewed_stage_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proposal = root / "case-plan-proposal.json"
            proposal.write_text(json.dumps({
                "schema": "agentlab.multi_repo_case_plan_proposal.v1",
                "status": "review-required",
                "caseId": "dependency-case",
                "candidateId": "candidate-three-repo",
                "sourceSetSha256": "a" * 64,
                "stages": [
                    {"id": "turn-1", "demand": "Change service behavior.", "checkIds": ["one"]},
                    {"id": "turn-2", "demand": "Update the consumer.", "checkIds": ["two"]},
                ],
                "automaticPromotion": False,
            }))
            difficulty = root / "difficulty.json"
            difficulty.write_text(json.dumps({
                "schema": "agentlab.difficulty_candidates.v2",
                "sourceSetSha256": "a" * 64,
                "sources": [
                    {"id": "app", "repository": "repo-app", "revision": "1" * 40},
                    {"id": "service", "repository": "repo-service", "revision": "2" * 40},
                    {"id": "contracts", "repository": "repo-contracts", "revision": "3" * 40},
                ],
                "candidates": [{
                    "id": "candidate-three-repo",
                    "dimensionId": "multi-repository-change-impact",
                    "maturityState": "candidate",
                    "affectedFiles": [
                        {"repositoryId": "contracts", "path": "src/policy.ts", "dependencyDepth": 0},
                        {"repositoryId": "service", "path": "src/reservation.ts", "dependencyDepth": 1},
                        {"repositoryId": "app", "path": "src/checkout.ts", "dependencyDepth": 2},
                    ],
                    "evidenceIds": ["edge-service", "edge-app"],
                }],
            }))
            facts = root / "facts.jsonl"
            facts.write_text("".join(json.dumps(row) + "\n" for row in [
                {
                    "id": "edge-service", "kind": "module-dependency",
                    "sourceRepositoryId": "service", "sourcePath": "src/reservation.ts",
                    "sourceIdentity": "git:repo-service@" + "2" * 40,
                    "targetRepositoryId": "contracts", "targetPath": "src/policy.ts",
                    "targetIdentity": "git:repo-contracts@" + "3" * 40,
                },
                {
                    "id": "edge-app", "kind": "module-dependency",
                    "sourceRepositoryId": "app", "sourcePath": "src/checkout.ts",
                    "sourceIdentity": "git:repo-app@" + "1" * 40,
                    "targetRepositoryId": "service", "targetPath": "src/reservation.ts",
                    "targetIdentity": "git:repo-service@" + "2" * 40,
                },
            ]))
            proposed = PROPOSER.propose(proposal, difficulty, facts)
            self.assertEqual(
                [row["stageId"] for row in proposed["stages"]],
                ["turn-1", "turn-2"],
            )
            self.assertEqual(
                proposed["stages"][0]["obligations"][0]["acceptedFactIds"],
                ["edge-service"],
            )
            proposed_path = root / "dependency-plan-proposal.json"
            proposed_path.write_text(json.dumps(proposed, sort_keys=True))
            risk_ids = ",".join(row["id"] for row in proposed["risks"])
            decision = REVIEW.create_decision(
                proposed_path,
                hashlib.sha256(proposed_path.read_bytes()).hexdigest(),
                "reviewer-a",
                risk_ids,
                "Every edge is inferable from imports in participant-visible source.",
            )
            decision_path = root / "dependency-plan-review.json"
            decision_path.write_text(json.dumps(decision, sort_keys=True))
            plan = REVIEW.compile_plan(proposed_path, decision_path)
            self.assertEqual(plan["schema"], "agentlab.dependency_discovery_plan.v2")
            self.assertEqual(
                plan["review"]["authority"], "explicit-dependency-plan-review"
            )


if __name__ == "__main__":
    unittest.main()
