import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "scope_decomposition_review",
    ROOT / "examples/maintainer-knowledge-gate/scope_decomposition_review.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MaintainerScopeDecompositionReviewTest(unittest.TestCase):
    def test_checked_in_reviews_reduce_structural_candidates_without_losing_files(self):
        root = ROOT / "examples/maintainer-knowledge-gate/first-four/decomposition-reviews"
        reviews = [json.loads(path.read_text()) for path in sorted(root.glob("*.json"))]
        self.assertEqual(len(reviews), 2)
        self.assertEqual(sum(row["verification"]["structuralLeafCount"] for row in reviews), 64)
        self.assertEqual(sum(row["verification"]["semanticGroupCount"] for row in reviews), 11)
        self.assertEqual(sum(row["verification"]["assignedFileCount"] for row in reviews), 415)
        for review in reviews:
            self.assertEqual(review["decision"], "ready-for-atomic-catalog-apply")
            self.assertEqual(review["blockerCode"], "MS-ATOMIC-CATALOG-APPLY-REQUIRED")
            self.assertFalse(review["automaticCatalogApply"])
            self.assertTrue(all(group["sourceFileCount"] <= 80 for group in review["groups"]))
            self.assertTrue(all(len(group["evidence"]) >= 2 for group in review["groups"]))

    def test_review_requires_every_structural_leaf_exactly_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = root / "repository"
            repository.mkdir()
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.name", "test"], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.email", "test@example.com"], check=True)
            for relative in ("large/a/one.rs", "large/a/two.rs", "large/b/three.rs", "large/b/four.rs"):
                path = repository / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative + "\n")
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repository), "commit", "-qm", "fixture"], check=True)
            revision = subprocess.check_output(
                ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
            ).strip()
            tree = subprocess.check_output(
                ["git", "-C", str(repository), "rev-parse", "HEAD^{tree}"], text=True
            ).strip()
            plan = {
                "schema": "agentlab.maintainer_scope_decomposition_plan.v1",
                "repositoryId": "arbitrary", "sourceRevision": revision, "sourceTreeOid": tree,
                "sourceExtensions": ["rs"],
                "maxSourceFilesPerLeaf": 2,
                "parent": {"scopeSkillId": "skill-scope-arbitrary-large", "pathBoundary": "large",
                           "sourceFileCount": 4},
                "leaves": [
                    {"id": "skill-scope-arbitrary-large-a", "sourceFileCount": 2,
                     "selector": {"type": "prefix", "path": "large/a"}},
                    {"id": "skill-scope-arbitrary-large-b", "sourceFileCount": 2,
                     "selector": {"type": "prefix", "path": "large/b"}},
                ],
            }
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan))
            spec = {
                "schema": "agentlab.maintainer_scope_decomposition_review_spec.v1",
                "parentScopeSkillId": "skill-scope-arbitrary-large",
                "groups": [
                    {"id": "skill-scope-arbitrary-a", "responsibility": "Maintain the first bounded source responsibility and its direct behavior.",
                     "rationale": "The first pair shares one exact directory contract and remains separate from the second independently owned source responsibility.",
                     "memberLeafIds": ["skill-scope-arbitrary-large-a"],
                     "evidencePaths": ["large/a/one.rs", "large/a/two.rs"]},
                    {"id": "skill-scope-arbitrary-b", "responsibility": "Maintain the second bounded source responsibility and its direct behavior.",
                     "rationale": "The second pair shares one exact directory contract and remains separate from the first independently owned source responsibility.",
                     "memberLeafIds": ["skill-scope-arbitrary-large-b"],
                     "evidencePaths": ["large/b/three.rs", "large/b/four.rs"]},
                ],
            }
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec))
            review = MODULE.build_review(plan_path, spec_path, repository)
            self.assertEqual(review["verification"]["semanticGroupCount"], 2)
            spec["groups"][1]["memberLeafIds"] = ["skill-scope-arbitrary-large-a"]
            spec["groups"][1]["evidencePaths"] = ["large/a/one.rs", "large/a/two.rs"]
            spec_path.write_text(json.dumps(spec))
            with self.assertRaisesRegex(ValueError, "unassigned"):
                MODULE.build_review(plan_path, spec_path, repository)


if __name__ == "__main__":
    unittest.main()
