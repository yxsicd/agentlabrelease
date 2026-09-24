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
            "status": "frozen-calibrated",
            "sourceSetSha256": "a" * 64,
            "sources": [
                {"id": "app", "repository": "repo-app", "revision": "1" * 40},
                {"id": "contracts", "repository": "repo-contracts", "revision": "2" * 40},
            ],
            "stages": [{"id": "repair", "demand": "Repair it.", "checkIds": ["check"]}],
            "automaticPromotion": False,
        }))
        facts = root / "facts.jsonl"
        facts.write_text("".join(json.dumps(row) + "\n" for row in [
            {
                "id": "fact-direct",
                "kind": "module-dependency",
                "repositoryId": "app",
                "path": "src/feature.ts",
                "sourceRevision": "1" * 40,
                "targetRepositoryId": "contracts",
                "targetPath": "src/policy.ts",
            },
            {
                "id": "fact-equivalent",
                "kind": "module-dependency",
                "repositoryId": "app",
                "path": "src/alternate.ts",
                "sourceRevision": "1" * 40,
                "targetRepositoryId": "contracts",
                "targetPath": "src/policy.ts",
            },
        ]))
        plan = root / "plan.json"
        plan.write_text(json.dumps({
            "schema": "agentlab.dependency_discovery_plan.v1",
            "caseId": "dependency-case",
            "sourceSetSha256": "a" * 64,
            "stages": [{
                "stageId": "repair",
                "obligations": [{
                    "id": "policy-consumer",
                    "acceptedFactIds": ["fact-direct", "fact-equivalent"],
                }],
            }],
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

    def test_rejects_program_fact_revision_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case, facts, plan = self.fixture(root)
            rows = [json.loads(line) for line in facts.read_text().splitlines()]
            rows[0]["sourceRevision"] = "f" * 40
            facts.write_text("".join(json.dumps(row) + "\n" for row in rows))
            with self.assertRaisesRegex(CONTRACT.ContractError, "source revision differs"):
                CONTRACT.build(case, facts, plan)


if __name__ == "__main__":
    unittest.main()
