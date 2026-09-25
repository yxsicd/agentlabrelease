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
SCRIPT = ROOT / "scripts/run-multi-repo-calibration-authoring.py"
PARTICIPANT = ROOT / "examples/multi-repo-case/mock-calibration-author.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


CONSTRUCTION = load_module(
    "authoring_test_construction",
    ROOT / "scripts/multi-repo-construction-contract.py",
)
CALIBRATION = load_module(
    "authoring_test_calibration",
    ROOT / "scripts/multi-repo-calibration-bundle.py",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MultiRepoCalibrationAuthoringTests(unittest.TestCase):
    def fixture(self, root: Path):
        sources = []
        affected = []
        repositories = []
        for index, repository_id in enumerate(("app", "contracts", "service"), start=1):
            repository = root / repository_id
            relative = f"src/{repository_id}.ts"
            (repository / "src").mkdir(parents=True)
            (repository / relative).write_text(f"export const value = {index};\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(repository), "-c", "user.name=AgentLab", "-c", "user.email=agentlab@example.invalid", "commit", "-qm", "fixture"],
                check=True,
            )
            revision = subprocess.check_output(
                ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
            ).strip()
            url = f"https://github.com/acme/{repository_id}.git"
            sources.append({"id": repository_id, "repository": url, "revision": revision})
            repositories.append({"id": repository_id, "repository": url, "revision": revision, "root": str(repository)})
            affected.append({"repositoryId": repository_id, "path": relative, "dependencyDepth": index - 1})
        candidate = {
            "id": "candidate-authored",
            "schema": "agentlab.difficulty_point.v1",
            "dimensionId": "multi-repository-change-impact",
            "relationType": "shared-module-contract",
            "status": "candidate",
            "maturityState": "candidate",
            "seed": {"repositoryId": "contracts", "path": "src/contracts.ts"},
            "affectedFiles": affected,
            "affectedRepositoryCount": 3,
            "maxDependencyDepth": 2,
            "automaticPromotion": False,
        }
        difficulty = root / "difficulty.json"
        difficulty.write_text(json.dumps({
            "schema": "agentlab.difficulty_candidates.v2",
            "sourceSetSha256": "a" * 64,
            "sources": sources,
            "candidates": [candidate],
            "automaticPromotion": False,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        selection = root / "selection.json"
        selection.write_text(json.dumps({
            "schema": "agentlab.multi_repo_candidate_selection.v2",
            "cohortId": "cohort-authoring",
            "cohortSha256": "b" * 64,
            "candidateId": candidate["id"],
            "candidateSha256": CONSTRUCTION.canonical_digest(candidate),
            "sourceSetSha256": "a" * 64,
            "difficultyEvidenceSha256": digest(difficulty),
            "methodRevision": "c" * 40,
            "declaredRepresentative": False,
            "automaticPromotion": False,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({
            "schema": "agentlab.multi_repo_manifest.v1",
            "repositories": repositories,
            "moduleBindings": {},
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        facts = root / "facts.jsonl"
        facts.write_text(json.dumps({
            "id": "fact-1",
            "repositoryId": "contracts",
            "path": "src/contracts.ts",
            "kind": "declaration",
        }, sort_keys=True) + "\n", encoding="utf-8")
        return selection, difficulty, manifest, facts

    def test_mock_evaluator_authors_digest_bound_review_required_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selection, difficulty, manifest, facts = self.fixture(root)
            output = root / "output"
            process = subprocess.run([
                sys.executable, str(SCRIPT), "run",
                "--selection", str(selection),
                "--difficulty", str(difficulty),
                "--manifest", str(manifest),
                "--facts", str(facts),
                "--participant", str(PARTICIPANT),
                "--participant-id", "mock-independent-evaluator",
                "--method-revision", "d" * 40,
                "--output", str(output),
            ], text=True, capture_output=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            receipt = json.loads((output / "authoring-receipt.json").read_text())
            self.assertEqual(receipt["status"], "review-required")
            self.assertFalse(receipt["automaticPromotion"])
            self.assertIn("machine-authored-executable-untrusted", receipt["risks"])
            self.assertEqual(len(receipt["sourceFiles"]), 3)
            self.assertTrue((output / "draft/bundle/oracle.mjs").is_file())
            self.assertTrue((output / "construction-contract-proposal.json").is_file())

            surface = output / "draft/source-surface.json"
            oracle = output / "draft/oracle-contract.json"
            authoring_receipt = output / "authoring-receipt.json"
            authored_proposal = output / "construction-contract-proposal.json"
            bound_proposal_value = CONSTRUCTION.propose(
                selection, difficulty, surface, oracle,
                (None, None, None, None, None, None),
                authoring_receipt, authored_proposal,
            )
            self.assertEqual(
                bound_proposal_value["calibrationAuthoring"]["receiptSha256"],
                digest(authoring_receipt),
            )
            bound_proposal = root / "bound-construction-proposal.json"
            bound_proposal.write_text(json.dumps(bound_proposal_value, indent=2, sort_keys=True) + "\n")
            review = root / "construction-review.json"
            review.write_text(json.dumps(CONSTRUCTION.decide(
                bound_proposal,
                digest(bound_proposal),
                "maintainer-independent",
                ",".join(sorted(CONSTRUCTION.RISK_IDS)),
                "The authored bytes remain untrusted but may enter independent calibration.",
            ), indent=2, sort_keys=True) + "\n")
            contract = root / "construction-contract.json"
            contract.write_text(json.dumps(
                CONSTRUCTION.compile_contract(bound_proposal, review), indent=2, sort_keys=True
            ) + "\n")
            calibration_proposal = CALIBRATION.propose(
                output / "draft/bundle",
                output / "draft/bundle/calibration-bundle.json",
                contract,
                None,
                authoring_receipt,
                output,
            )
            self.assertEqual(
                calibration_proposal["calibrationAuthoring"]["draftManifestSha256"],
                receipt["draftManifestSha256"],
            )

            verify = subprocess.run([
                sys.executable, str(SCRIPT), "validate", "--root", str(output)
            ], text=True, capture_output=True)
            self.assertEqual(verify.returncode, 0, verify.stderr)

    def test_authored_oracle_and_retained_source_tampering_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selection, difficulty, manifest, facts = self.fixture(root)
            output = root / "output"
            command = [
                sys.executable, str(SCRIPT), "run",
                "--selection", str(selection), "--difficulty", str(difficulty),
                "--manifest", str(manifest), "--facts", str(facts),
                "--participant", str(PARTICIPANT), "--participant-id", "mock-evaluator",
                "--method-revision", "d" * 40, "--output", str(output),
            ]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            (output / "draft/bundle/oracle.mjs").write_text("tampered\n", encoding="utf-8")
            failed = subprocess.run([
                sys.executable, str(SCRIPT), "validate", "--root", str(output)
            ], text=True, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("Oracle bytes differ", failed.stderr)

            self.assertEqual(subprocess.run(command[:-2] + ["--output", str(root / "second")], capture_output=True).returncode, 0)
            second = root / "second"
            source = next((second / "workspace/sources").rglob("*.ts"))
            source.write_text("tampered source\n", encoding="utf-8")
            failed = subprocess.run([
                sys.executable, str(SCRIPT), "validate", "--root", str(second)
            ], text=True, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("source bytes differ", failed.stderr)

            third = root / "third"
            self.assertEqual(
                subprocess.run(command[:-2] + ["--output", str(third)], capture_output=True).returncode,
                0,
            )
            request_path = third / "workspace/authoring-request.json"
            request = json.loads(request_path.read_text())
            request["candidate"]["maxDependencyDepth"] = 99
            request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n")
            receipt_path = third / "authoring-receipt.json"
            receipt = json.loads(receipt_path.read_text())
            receipt["requestSha256"] = digest(request_path)
            receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            failed = subprocess.run([
                sys.executable, str(SCRIPT), "validate", "--root", str(third)
            ], text=True, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("candidate object differs", failed.stderr)

    def test_workflows_keep_authoring_review_calibration_and_assessment_separate(self):
        authoring = (ROOT / ".github/workflows/multi-repo-calibration-authoring.yml").read_text()
        construction = (ROOT / ".github/workflows/multi-repo-construction-contract-proposal.yml").read_text()
        construction_review = (ROOT / ".github/workflows/multi-repo-construction-contract-review.yml").read_text()
        calibration = (ROOT / ".github/workflows/multi-repo-calibration-bundle-proposal.yml").read_text()
        calibration_review = (ROOT / ".github/workflows/multi-repo-calibration-bundle-review.yml").read_text()
        freeze = (ROOT / ".github/workflows/multi-repo-case-review.yml").read_text()
        self.assertIn("AGENTLAB_LM_GATEWAY_KEY", authoring)
        self.assertNotIn(
            "AGENTLAB_LM_GATEWAY_KEY",
            construction + construction_review + calibration + calibration_review + freeze,
        )
        self.assertIn("refs/heads/main", authoring)
        self.assertIn("pi-calibration-author.py", authoring)
        self.assertIn("run-multi-repo-calibration-authoring.py validate", authoring)
        self.assertIn("calibration_authoring_run_id", construction)
        self.assertIn("--authoring-receipt", construction)
        self.assertIn("--authoring-receipt", construction_review)
        self.assertIn("calibration_authoring_run_id", calibration)
        self.assertIn("--authoring-root", calibration)
        self.assertIn("--authoring-root", calibration_review)
        self.assertIn("--authoring-root", freeze)


if __name__ == "__main__":
    unittest.main()
