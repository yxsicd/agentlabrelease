import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "apply_scope_decomposition_review",
    ROOT / "examples/maintainer-knowledge-gate/apply_scope_decomposition_review.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ApplyScopeDecompositionReviewTest(unittest.TestCase):
    def fixture(self, root):
        repository = root / "repository"
        repository.mkdir()
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.name", "test"], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.email", "test@example.com"], check=True)
        for relative in ("large/root.json", "large/a/one.rs", "large/a/two.rs", "large/b/three.rs", "large/b/four.rs"):
            path = repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative + "\n")
        subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repository), "commit", "-qm", "fixture"], check=True)
        revision = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
        tree = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD^{tree}"], text=True).strip()
        entries = MODULE.git_entries(repository, revision, "large")
        by_path = {row["path"]: row for row in entries}
        parent = {
            "schema": "agentlab.maintainer_scope_skill.v1", "id": "skill-scope-arbitrary-large",
            "skillLayer": "instance", "stage": "repository-scope", "ownershipPlane": "target-operations",
            "assetClass": "reusable-knowledge", "status": "source-supported", "repositoryId": "arbitrary",
            "repository": repository.as_uri(), "sourceRevision": revision, "sourceTreeOid": tree,
            "strategy": "generic", "kind": "module", "pathBoundary": "large",
            "responsibility": "Maintain the large fixture.", "documentedTitle": None, "documentedPurpose": None,
            "trackedFileCount": 5, "sourceFileCount": 4, "codeLineCount": 4, "testFileCount": 0,
            "languages": {"json": 1, "rs": 4}, "externalDependencyCount": 0, "externalDependencies": [],
            "buildEntrypoints": [], "testEntrypoints": [], "evidence": [by_path["large/root.json"]],
            "coverage": "all tracked files under this leaf boundary are assigned exactly once",
            "automaticPromotion": False,
        }
        catalog = root / "catalog.jsonl"
        catalog.write_text(json.dumps(parent) + "\n")
        groups = []
        for suffix, paths, selectors in (
            ("a", ["large/root.json", "large/a/one.rs", "large/a/two.rs"], [
                {"type": "files", "paths": ["large/root.json"]}, {"type": "prefix", "path": "large/a"}
            ]),
            ("b", ["large/b/three.rs", "large/b/four.rs"], [{"type": "prefix", "path": "large/b"}]),
        ):
            member_entries = [by_path[path] for path in paths]
            evidence = member_entries[:2]
            groups.append({
                "id": f"skill-scope-arbitrary-{suffix}",
                "responsibility": f"Maintain arbitrary responsibility {suffix} with its exact source and configuration contract.",
                "ownershipSelectors": selectors,
                "trackedFileCount": len(paths),
                "sourceFileCount": sum(path.endswith(".rs") for path in paths),
                "fileSetSha256": MODULE.file_set_digest(member_entries),
                "evidence": evidence,
                "reviewStatus": "semantic-responsibility-proposed",
            })
        review = {
            "schema": "agentlab.maintainer_scope_decomposition_review.v1", "automaticCatalogApply": False,
            "repositoryId": "arbitrary", "decision": "ready-for-atomic-catalog-apply",
            "blockerCode": "MS-ATOMIC-CATALOG-APPLY-REQUIRED",
            "sourceExtensions": ["rs"],
            "sourceRevision": revision, "sourceTreeOid": tree, "parentScopeSkillId": parent["id"],
            "groups": groups, "verification": {"assignedFileCount": 5, "complete": True, "nonOverlapping": True},
        }
        review_path = root / "review.json"
        review_path.write_text(json.dumps(review))
        return repository, catalog, review_path, review

    def test_composite_replacement_is_exact_and_candidate_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, catalog, review_path, _ = self.fixture(root)
            rows, receipt = MODULE.build_candidate(catalog, review_path, repository)
            self.assertEqual([row["id"] for row in rows], ["skill-scope-arbitrary-a", "skill-scope-arbitrary-b"])
            self.assertEqual(sum(row["trackedFileCount"] for row in rows), 5)
            self.assertEqual(sum(row["sourceFileCount"] for row in rows), 4)
            self.assertTrue(all(row["kind"] == "composite-responsibility" for row in rows))
            self.assertFalse(receipt["automaticAuthorityMutation"])
            self.assertEqual(receipt["decision"], "candidate-catalog-ready-for-authoritative-transaction")
            output = root / "candidate.jsonl"
            MODULE.write_exclusive_atomic(output, rows)
            with self.assertRaisesRegex(ValueError, "already exists"):
                MODULE.write_exclusive_atomic(output, rows)

    def test_overlap_fails_before_output_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, catalog, review_path, review = self.fixture(root)
            review["groups"][1]["ownershipSelectors"] = [{"type": "prefix", "path": "large/a"}]
            review_path.write_text(json.dumps(review))
            output = root / "candidate.jsonl"
            with self.assertRaises(ValueError):
                rows, _ = MODULE.build_candidate(catalog, review_path, repository)
                MODULE.write_exclusive_atomic(output, rows)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
