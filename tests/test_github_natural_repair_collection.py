from __future__ import annotations

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


COLLECT = load_module(
    "github_natural_repair_collection",
    ROOT / "scripts/collect-github-natural-repair.py",
)


def patch(source: str, test: str) -> bytes:
    return (
        f"diff --git a/{source} b/{source}\n"
        f"index 1111111..2222222 100644\n--- a/{source}\n+++ b/{source}\n@@ -1 +1 @@\n-old\n+new\n"
        f"diff --git a/{test} b/{test}\n"
        f"index 3333333..4444444 100644\n--- a/{test}\n+++ b/{test}\n@@ -1 +1 @@\n-fail\n+pass\n"
    ).encode()


class FakeGitHub:
    def __init__(self, *, bad_base: bool = False, missing_affected: bool = False):
        self.bad_base = bad_base
        self.missing_affected = missing_affected

    def json(self, url: str):
        if "/issues/7" in url:
            return {
                "html_url": "https://github.com/acme/app/issues/7",
                "number": 7,
                "title": "Coordinated contract regression",
                "body": "Both repositories need one repair.",
                "state": "closed",
                "created_at": "2026-09-20T10:00:00Z",
                "closed_at": "2026-09-21T11:00:00Z",
            }
        if "/pulls/8" in url:
            return {
                "html_url": "https://github.com/acme/app/pull/8",
                "merged_at": "2026-09-21T10:00:00Z",
                "merge_commit_sha": "3" * 40,
                "base": {"sha": "f" * 40 if self.bad_base else "1" * 40},
            }
        if "/pulls/9" in url:
            return {
                "html_url": "https://github.com/acme/service/pull/9",
                "merged_at": "2026-09-21T11:00:00Z",
                "merge_commit_sha": "4" * 40,
                "base": {"sha": "2" * 40},
            }
        raise AssertionError(url)

    def patch(self, url: str) -> bytes:
        if "/pulls/8" in url:
            source = "src/not-declared.ts" if self.missing_affected else "src/app.ts"
            return patch(source, "tests/app.test.ts")
        if "/pulls/9" in url:
            return patch("src/service.ts", "tests/service.test.ts")
        raise AssertionError(url)


class GitHubNaturalRepairCollectionTests(unittest.TestCase):
    def spec(self) -> dict:
        return {
            "schema": "agentlab.github_natural_repair_spec.v1",
            "id": "github-coordinated-repair",
            "title": "Repair a coordinated public GitHub regression",
            "sources": [
                {"id": "app", "repository": "https://github.com/acme/app.git", "revision": "1" * 40},
                {"id": "service", "repository": "https://github.com/acme/service.git", "revision": "2" * 40},
            ],
            "moduleBindings": {},
            "affectedFiles": [
                {"repositoryId": "app", "path": "src/app.ts", "dependencyDepth": 1},
                {"repositoryId": "service", "path": "src/service.ts", "dependencyDepth": 0},
            ],
            "testFiles": [
                {"repositoryId": "app", "path": "tests/app.test.ts"},
                {"repositoryId": "service", "path": "tests/service.test.ts"},
            ],
            "issueUrls": ["https://github.com/acme/app/issues/7"],
            "repairs": [
                {"repositoryId": "app", "pullRequestUrl": "https://github.com/acme/app/pull/8", "fixRevision": "3" * 40},
                {"repositoryId": "service", "pullRequestUrl": "https://github.com/acme/service/pull/9", "fixRevision": "4" * 40},
            ],
            "testContract": {
                "observedFailureCheckIds": ["contract-fails-before"],
                "preservationCheckIds": ["existing-routes-stay-green"],
            },
            "collectedAt": "2026-09-25T12:00:00Z",
            "automaticPromotion": False,
        }

    def write_spec(self, root: Path, value: dict | None = None) -> Path:
        path = root / "spec.json"
        path.write_text(json.dumps(value or self.spec(), sort_keys=True) + "\n")
        return path

    def test_collects_exact_public_repair_and_normalizes_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            receipt = COLLECT.collect(self.write_spec(root), output, "5" * 40, FakeGitHub())
            self.assertEqual(receipt["repairCount"], 2)
            self.assertFalse(receipt["automaticPromotion"])
            candidate_source = json.loads((output / "difficulty_candidates.json").read_text())
            candidate = candidate_source["candidates"][0]
            self.assertEqual(candidate["caseSource"]["lane"], "natural")
            self.assertEqual(candidate["caseSource"]["strategy"], "historical-repair")
            self.assertFalse(candidate["verificationContract"]["caseReady"])
            tests = (output / "evidence/tests.patch").read_text()
            self.assertIn("tests/app.test.ts", tests)
            self.assertIn("tests/service.test.ts", tests)
            self.assertNotIn("src/app.ts", tests)
            self.assertEqual(
                COLLECT.validate_collection(output, output / "collection-receipt.json"),
                receipt,
            )
            (output / "evidence/tests.patch").write_text("tampered\n")
            with self.assertRaisesRegex(ValueError, "evidence digest differs"):
                COLLECT.validate_collection(output, output / "collection-receipt.json")

    def test_rejects_pr_base_or_patch_that_does_not_match_declared_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "base differs"):
                COLLECT.collect(self.write_spec(root), root / "bad-base", "5" * 40, FakeGitHub(bad_base=True))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "omits declared affected files"):
                COLLECT.collect(self.write_spec(root), root / "bad-patch", "5" * 40, FakeGitHub(missing_affected=True))

    def test_rejects_non_github_or_cross_repository_repair_urls(self) -> None:
        value = self.spec()
        value["issueUrls"] = ["https://example.com/acme/app/issues/7"]
        with self.assertRaisesRegex(ValueError, "public github.com"):
            COLLECT.validate_spec(value)
        value = self.spec()
        value["repairs"][0]["pullRequestUrl"] = "https://github.com/other/app/pull/8"
        with self.assertRaisesRegex(ValueError, "differs from the source"):
            COLLECT.validate_spec(value)

    def test_published_schema_matches_collection_spec(self) -> None:
        schema = json.loads((ROOT / "schemas/github-natural-repair-spec.schema.json").read_text())
        self.assertEqual(schema["properties"]["schema"]["const"], "agentlab.github_natural_repair_spec.v1")

    def test_workflow_is_trusted_main_read_only_and_retains_exact_record(self) -> None:
        workflow = (ROOT / ".github/workflows/github-natural-repair-source.yml").read_text()
        self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("collect-github-natural-repair.py create", workflow)
        self.assertIn("collect-github-natural-repair.py validate", workflow)
        self.assertIn("name: github-natural-repair-source", workflow)
        self.assertNotIn("automaticPromotion: true", workflow)


if __name__ == "__main__":
    unittest.main()
