import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "scope_decomposition", ROOT / "examples/maintainer-knowledge-gate/scope_decomposition.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MaintainerScopeDecompositionTest(unittest.TestCase):
    def test_checked_in_code_workshop_plans_are_bounded_review_artifacts(self):
        plan_root = ROOT / "examples/maintainer-knowledge-gate/first-four/decomposition-plans"
        plans = [json.loads(path.read_text()) for path in sorted(plan_root.glob("*.json"))]
        self.assertEqual(len(plans), 2)
        self.assertEqual(sum(plan["parent"]["trackedFileCount"] for plan in plans), 415)
        self.assertEqual(sum(len(plan["leaves"]) for plan in plans), 64)
        for plan in plans:
            self.assertFalse(plan["automaticPromotion"])
            self.assertEqual(plan["decision"], "ready-for-scope-catalog-review")
            self.assertTrue(plan["verification"]["complete"])
            self.assertTrue(plan["verification"]["nonOverlapping"])
            self.assertEqual(plan["verification"]["unassignedFileCount"], 0)
            self.assertEqual(plan["verification"]["multiplyAssignedFileCount"], 0)
            self.assertEqual(
                sum(leaf["trackedFileCount"] for leaf in plan["leaves"]),
                plan["parent"]["trackedFileCount"],
            )
            self.assertTrue(all(
                leaf["sourceFileCount"] <= plan["maxSourceFilesPerLeaf"]
                for leaf in plan["leaves"]
            ))
            self.assertEqual(
                len({leaf["id"] for leaf in plan["leaves"]}), len(plan["leaves"])
            )

    def test_arbitrary_repository_partition_is_complete_non_overlapping_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            repository.mkdir()
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.name", "test"], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.email", "test@example.com"], check=True)
            for relative in ("large/root.json", "large/a/one.rs", "large/a/two.rs",
                             "large/a/three.rs", "large/b/four.rs", "large/b/readme.md"):
                path = repository / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative + "\n")
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repository), "commit", "-qm", "fixture"], check=True)
            revision = subprocess.check_output(
                ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
            ).strip()
            tree = subprocess.check_output(
                ["git", "-C", str(repository), "rev-parse", f"{revision}^{{tree}}"], text=True
            ).strip()
            parent = {
                "id": "skill-scope-arbitrary-large", "repositoryId": "arbitrary",
                "repository": repository.as_uri(), "sourceRevision": revision,
                "sourceTreeOid": tree, "pathBoundary": "large",
                "trackedFileCount": 6, "sourceFileCount": 4,
            }
            plan = MODULE.build_plan(parent, repository, 2, {"rs"})
            self.assertTrue(plan["verification"]["complete"])
            self.assertTrue(plan["verification"]["nonOverlapping"])
            self.assertEqual(plan["verification"]["assignedFileCount"], 6)
            self.assertTrue(all(leaf["sourceFileCount"] <= 2 for leaf in plan["leaves"]))
            self.assertEqual(sum(leaf["trackedFileCount"] for leaf in plan["leaves"]), 6)
            self.assertEqual(len({leaf["id"] for leaf in plan["leaves"]}), len(plan["leaves"]))
            self.assertTrue(any(leaf["selector"]["type"] == "files" for leaf in plan["leaves"]))
            schema = json.loads(
                (ROOT / "schemas/maintainer-scope-decomposition-plan.schema.json").read_text()
            )
            self.assertEqual(schema["properties"]["schema"]["const"], plan["schema"])

    def test_parent_inventory_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            repository.mkdir()
            subprocess.run(["git", "init", "-q", str(repository)], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.name", "test"], check=True)
            subprocess.run(["git", "-C", str(repository), "config", "user.email", "test@example.com"], check=True)
            (repository / "large").mkdir()
            (repository / "large/one.rs").write_text("one\n")
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repository), "commit", "-qm", "fixture"], check=True)
            revision = subprocess.check_output(
                ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
            ).strip()
            tree = subprocess.check_output(
                ["git", "-C", str(repository), "rev-parse", f"{revision}^{{tree}}"], text=True
            ).strip()
            parent = {
                "id": "skill-scope-arbitrary-large", "repositoryId": "arbitrary",
                "repository": repository.as_uri(), "sourceRevision": revision,
                "sourceTreeOid": tree, "pathBoundary": "large",
                "trackedFileCount": 2, "sourceFileCount": 1,
            }
            with self.assertRaisesRegex(ValueError, "tracked file count differs"):
                MODULE.build_plan(parent, repository, 1, {"rs"})


if __name__ == "__main__":
    unittest.main()
