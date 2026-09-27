from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
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


CONTRACT = load_module(
    "multi_repo_construction_contract",
    ROOT / "scripts/multi-repo-construction-contract.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MultiRepoConstructionContractTests(unittest.TestCase):
    def fixture(self, root: Path):
        candidate = {
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
        }
        difficulty = root / "difficulty.json"
        difficulty.write_text(json.dumps({
            "schema": "agentlab.difficulty_candidates.v2",
            "sourceSetSha256": "a" * 64,
            "sources": [],
            "candidates": [candidate],
            "automaticPromotion": False,
        }, sort_keys=True) + "\n")
        selection = root / "selection.json"
        selection.write_text(json.dumps({
            "schema": "agentlab.multi_repo_candidate_selection.v2",
            "cohortId": "cohort-1",
            "cohortSha256": "b" * 64,
            "candidateId": candidate["id"],
            "candidateSha256": CONTRACT.canonical_digest(candidate),
            "sourceSetSha256": "a" * 64,
            "difficultyEvidenceSha256": digest(difficulty),
            "methodRevision": "c" * 40,
            "declaredRepresentative": False,
            "automaticPromotion": False,
        }, sort_keys=True) + "\n")
        surface = root / "surface.json"
        surface.write_text(json.dumps({
            "schema": "agentlab.multi_repo_construction_surface.v1",
            "editablePaths": [{"repositoryId": "contracts", "path": "src/policy.ts"}],
            "contextPaths": [{"repositoryId": "service", "path": "src/service.ts"}],
            "automaticPromotion": False,
        }, sort_keys=True) + "\n")
        oracle = root / "oracle.json"
        oracle.write_text((ROOT / "examples/multi-repo-case/oracle-contract.json").read_text())
        return selection, difficulty, surface, oracle

    def test_reviewed_contract_binds_candidate_surface_oracle_and_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selection, difficulty, surface, oracle = self.fixture(root)
            proposal_value = CONTRACT.propose(
                selection, difficulty, surface, oracle, (None, None, None)
            )
            proposal = root / "proposal.json"
            proposal.write_text(json.dumps(proposal_value, indent=2, sort_keys=True) + "\n")
            review_value = CONTRACT.decide(
                proposal,
                digest(proposal),
                "maintainer-a",
                ",".join(sorted(CONTRACT.RISK_IDS)),
                "The exact source surface and behavior checks are suitable for a construction attempt.",
            )
            review = root / "review.json"
            review.write_text(json.dumps(review_value, indent=2, sort_keys=True) + "\n")
            contract_value = CONTRACT.compile_contract(proposal, review)
            contract = root / "contract.json"
            contract.write_text(json.dumps(contract_value, indent=2, sort_keys=True) + "\n")
            validated = CONTRACT.validate(
                contract, proposal, review, selection, difficulty, surface, oracle,
                (None, None, None),
            )
            self.assertEqual(validated["status"], "reviewed-for-model-construction")
            self.assertEqual(validated["candidateId"], "candidate-deep")
            self.assertEqual(validated["sourceSurface"]["editablePaths"], [
                {"repositoryId": "contracts", "path": "src/policy.ts"}
            ])
            self.assertEqual(validated["oracleContractSha256"], digest(oracle))
            self.assertFalse(validated["automaticPromotion"])

    def test_surface_must_be_candidate_grounded_and_cross_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selection, difficulty, surface, oracle = self.fixture(root)
            value = json.loads(surface.read_text())
            value["contextPaths"] = [{"repositoryId": "service", "path": "src/not-affected.ts"}]
            surface.write_text(json.dumps(value) + "\n")
            with self.assertRaisesRegex(CONTRACT.ContractError, "exceeds candidate evidence"):
                CONTRACT.propose(selection, difficulty, surface, oracle, (None, None, None))

            value["contextPaths"] = []
            surface.write_text(json.dumps(value) + "\n")
            with self.assertRaisesRegex(CONTRACT.ContractError, "retain multiple repositories"):
                CONTRACT.propose(selection, difficulty, surface, oracle, (None, None, None))

    def test_contract_tampering_and_partial_risk_review_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selection, difficulty, surface, oracle = self.fixture(root)
            proposal_value = CONTRACT.propose(selection, difficulty, surface, oracle, (None, None, None))
            proposal = root / "proposal.json"
            proposal.write_text(json.dumps(proposal_value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(CONTRACT.ContractError, "acknowledge every"):
                CONTRACT.decide(
                    proposal, digest(proposal), "maintainer", "calibration-pending",
                    "This rationale is deliberately long enough for exact review.",
                )
            value = json.loads(proposal.read_text())
            value["sourceSurface"]["editablePaths"][0]["path"] = "src/other.ts"
            proposal.write_text(json.dumps(value, sort_keys=True) + "\n")
            with self.assertRaisesRegex(CONTRACT.ContractError, "proposal differs"):
                review = root / "review.json"
                review.write_text(json.dumps({
                    "schema": CONTRACT.REVIEW_SCHEMA,
                    "proposalSha256": digest(proposal),
                    "reviewer": "maintainer",
                    "rationale": "The changed proposal should not validate against original inputs.",
                    "verdict": "approve-for-model-construction",
                    "acknowledgedRiskIds": sorted(CONTRACT.RISK_IDS),
                    "automaticPromotion": False,
                }) + "\n")
                contract = root / "contract.json"
                contract.write_text(json.dumps(CONTRACT.compile_contract(proposal, review)) + "\n")
                CONTRACT.validate(
                    contract, proposal, review, selection, difficulty, surface, oracle,
                    (None, None, None),
                )

    def test_construction_materializes_only_reviewed_surface(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selection, difficulty, surface, oracle = self.fixture(root)
            repositories = []
            for index, (repository_id, relative) in enumerate((
                ("app", "src/app.ts"),
                ("contracts", "src/policy.ts"),
                ("service", "src/service.ts"),
            ), start=1):
                repository = root / repository_id
                (repository / Path(relative).parent).mkdir(parents=True)
                (repository / relative).write_text(f"export const value = {index};\n")
                subprocess.run(["git", "init", "-q", str(repository)], check=True)
                subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
                subprocess.run(
                    ["git", "-C", str(repository), "-c", "user.name=AgentLab", "-c", "user.email=agentlab@example.invalid", "commit", "-qm", "fixture"],
                    check=True,
                )
                revision = subprocess.check_output(
                    ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
                ).strip()
                repositories.append({
                    "id": repository_id,
                    "repository": f"https://example.invalid/{repository_id}.git",
                    "revision": revision,
                    "root": str(repository),
                })
            difficulty_value = json.loads(difficulty.read_text())
            difficulty_value["sources"] = [
                {key: row[key] for key in ("id", "repository", "revision")}
                for row in repositories
            ]
            difficulty.write_text(json.dumps(difficulty_value, sort_keys=True) + "\n")
            selection_value = json.loads(selection.read_text())
            selection_value["difficultyEvidenceSha256"] = digest(difficulty)
            selection.write_text(json.dumps(selection_value, sort_keys=True) + "\n")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "schema": "agentlab.multi_repo_manifest.v1",
                "repositories": repositories,
                "moduleBindings": {},
            }, sort_keys=True) + "\n")
            facts = root / "facts.jsonl"
            facts.write_text("")

            proposal_value = CONTRACT.propose(selection, difficulty, surface, oracle, (None, None, None))
            proposal = root / "proposal.json"
            proposal.write_text(json.dumps(proposal_value, indent=2, sort_keys=True) + "\n")
            review_value = CONTRACT.decide(
                proposal, digest(proposal), "maintainer-a", ",".join(sorted(CONTRACT.RISK_IDS)),
                "The exact two-repository surface is sufficient for a bounded construction attempt.",
            )
            review = root / "review.json"
            review.write_text(json.dumps(review_value, indent=2, sort_keys=True) + "\n")
            contract = root / "contract.json"
            contract.write_text(json.dumps(CONTRACT.compile_contract(proposal, review), indent=2, sort_keys=True) + "\n")
            output = root / "construction"
            completed = subprocess.run([
                sys.executable,
                str(ROOT / "scripts/run-multi-repo-intent-construction.py"),
                "--manifest", str(manifest),
                "--difficulty", str(difficulty),
                "--facts", str(facts),
                "--candidate-id", "candidate-deep",
                "--oracle-contract", str(oracle),
                "--construction-contract", str(contract),
                "--participant", str(ROOT / "examples/multi-repo-case/mock-construction-agent.py"),
                "--participant-id", "deterministic-contract-test",
                "--output", str(output),
            ], text=True, capture_output=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            receipt = json.loads((output / "construction-receipt.json").read_text())
            self.assertEqual(receipt["constructionContractSha256"], digest(contract))
            self.assertEqual(len(receipt["sourceFiles"]), 2)
            self.assertEqual(
                {(row["repositoryId"], row["role"]) for row in receipt["sourceFiles"]},
                {("contracts", "editable"), ("service", "context")},
            )

    def test_workflows_split_contract_proposal_review_and_model_use(self):
        proposal = (ROOT / ".github/workflows/multi-repo-construction-contract-proposal.yml").read_text()
        review = (ROOT / ".github/workflows/multi-repo-construction-contract-review.yml").read_text()
        construction = (ROOT / ".github/workflows/multi-repo-model-construction.yml").read_text()
        self.assertNotIn("AGENTLAB_LM_GATEWAY_KEY", proposal + review)
        self.assertIn("expected_proposal_sha256", review)
        self.assertIn("scripts/multi-repo-construction-contract.py validate", review)
        self.assertIn("semantic-packet.json", proposal + review + construction)
        self.assertIn("semantic-decision.json", proposal + review + construction)
        self.assertIn("semantic-gate.json", proposal + review + construction)
        self.assertIn("construction_contract_review_run_id", construction)
        self.assertIn("scripts/prepare-multi-repo-analysis-sources.py", construction)
        self.assertIn("--construction-contract", construction)
        self.assertNotIn("prepare-multi-repo-construction-fixture.py", construction)
        self.assertNotIn("operator-fixture", construction)


if __name__ == "__main__":
    unittest.main()
