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


BUNDLE = load_module("candidate_source_bundle_test", ROOT / "scripts/candidate-source-bundle.py")
COLLECT = load_module("candidate_source_bundle_collect", ROOT / "scripts/collect-github-natural-repair.py")
ANALYSIS = load_module("candidate_source_bundle_analysis_test", ROOT / "scripts/multi-repo-analysis-run.py")
MERGE = load_module("candidate_source_bundle_merge_test", ROOT / "scripts/merge-case-candidate-sources.py")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch(source: str, test: str) -> bytes:
    return (
        f"diff --git a/{source} b/{source}\n"
        f"--- a/{source}\n+++ b/{source}\n@@ -1 +1 @@\n-old\n+new\n"
        f"diff --git a/{test} b/{test}\n"
        f"--- a/{test}\n+++ b/{test}\n@@ -1 +1 @@\n-fail\n+pass\n"
    ).encode()


class FakeGitHub:
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
                "base": {"sha": "1" * 40},
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
            return patch("src/app.ts", "tests/app.test.ts")
        if "/pulls/9" in url:
            return patch("src/service.ts", "tests/service.test.ts")
        raise AssertionError(url)


class CandidateSourceBundleTests(unittest.TestCase):
    def sources(self) -> list[dict]:
        return [
            {"id": "app", "repository": "https://github.com/acme/app.git", "revision": "1" * 40},
            {"id": "service", "repository": "https://github.com/acme/service.git", "revision": "2" * 40},
        ]

    def natural_spec(self) -> dict:
        return {
            "schema": "agentlab.github_natural_repair_spec.v1",
            "id": "github-coordinated-repair",
            "title": "Repair a coordinated public GitHub regression",
            "sources": self.sources(),
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

    def fixture(self, root: Path) -> tuple[Path, dict]:
        root.mkdir()
        spec_path = root / "natural-spec.json"
        spec_path.write_text(json.dumps(self.natural_spec(), sort_keys=True) + "\n")
        natural_root = root / "natural-source"
        natural_receipt = COLLECT.collect(spec_path, natural_root, "5" * 40, FakeGitHub())
        (root / "natural-source-run.json").write_text(json.dumps({
            "id": 202,
            "head_branch": "main",
            "head_sha": "5" * 40,
            "path": ".github/workflows/github-natural-repair-source.yml",
            "event": "workflow_dispatch",
            "conclusion": "success",
        }, sort_keys=True) + "\n")

        analysis_root = root / "analysis-source"
        output = analysis_root / "analysis"
        output.mkdir(parents=True)
        (analysis_root / "source-spec.json").write_text(json.dumps({
            "schema": "agentlab.multi_repo_source_spec.v1",
            "sources": self.sources(),
            "moduleBindings": {},
            "automaticPromotion": False,
        }, sort_keys=True) + "\n")
        (analysis_root / "manifest.json").write_text(json.dumps({
            "schema": "agentlab.multi_repo_manifest.v1",
            "repositories": self.sources(),
            "moduleBindings": {},
        }, sort_keys=True) + "\n")
        analysis_candidates = {
            "schema": "agentlab.difficulty_candidates.v2",
            "method": "fixture analyzer",
            "sourceSetSha256": natural_receipt["sourceSetSha256"],
            "sources": self.sources(),
            "moduleBindings": {},
            "candidates": [{
                "id": "derived-contract-impact",
                "schema": "agentlab.difficulty_point.v1",
                "dimensionId": "multi-repository-change-impact",
                "relationType": "recursive-reverse-impact",
                "status": "candidate",
                "maturityState": "candidate",
                "affectedFiles": [
                    {"repositoryId": "app", "path": "src/app.ts", "dependencyDepth": 1},
                    {"repositoryId": "service", "path": "src/service.ts", "dependencyDepth": 0},
                ],
                "affectedRepositoryCount": 2,
                "maxDependencyDepth": 1,
                "automaticPromotion": False,
            }],
            "automaticPromotion": False,
        }
        difficulty_path = output / "difficulty_candidates.json"
        difficulty_path.write_text(json.dumps(analysis_candidates, sort_keys=True) + "\n")
        facts_path = output / "workspace_facts.jsonl"
        unsupported_path = output / "unsupported_sources.jsonl"
        facts_path.write_text("")
        unsupported_path.write_text("")
        receipt_path = output / "multi_repo_analysis.json"
        receipt_path.write_text(json.dumps({
            "schema": "agentlab.multi_repo_analysis.v1",
            "sourceSetSha256": natural_receipt["sourceSetSha256"],
            "manifestSha256": digest(analysis_root / "manifest.json"),
            "difficultyCandidatesSha256": digest(difficulty_path),
            "workspaceFactsSha256": digest(facts_path),
            "unsupportedSourcesSha256": digest(unsupported_path),
            "facts": 0,
            "difficultyCandidates": 1,
            "unsupportedSources": 0,
            "sharedExternalModuleContracts": 0,
            "sharedExternalApiCallContracts": 0,
            "automaticPromotion": False,
        }, sort_keys=True) + "\n")
        analysis_run = ANALYSIS.derive(analysis_root, "6" * 40)
        (analysis_root / "analysis-run.json").write_text(json.dumps(analysis_run, indent=2, sort_keys=True) + "\n")
        (root / "analysis-source-run.json").write_text(json.dumps({
            "id": 101,
            "head_branch": "main",
            "head_sha": "6" * 40,
            "path": ".github/workflows/multi-repo-analysis.yml",
            "event": "workflow_dispatch",
            "conclusion": "success",
        }, sort_keys=True) + "\n")
        merged = MERGE.merge([difficulty_path, natural_root / "difficulty_candidates.json"])
        (root / "difficulty_candidates.json").write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
        return root, natural_receipt

    def test_bundle_reconstructs_both_exact_source_histories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.fixture(Path(directory) / "bundle")
            value = BUNDLE.derive(root, "7" * 40)
            self.assertEqual(value["candidateCount"], 2)
            self.assertEqual([row["kind"] for row in value["inputs"]], [
                "derived-analysis",
                "natural-github-repair",
            ])
            self.assertEqual([row["workflowRunId"] for row in value["inputs"]], [101, 202])
            self.assertEqual(value["mergedCandidateSourceSha256"], digest(root / "difficulty_candidates.json"))
            self.assertFalse(value["automaticPromotion"])

    def test_bundle_rejects_run_identity_and_merged_source_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.fixture(Path(directory) / "bundle")
            metadata = json.loads((root / "natural-source-run.json").read_text())
            metadata["head_branch"] = "feature"
            (root / "natural-source-run.json").write_text(json.dumps(metadata) + "\n")
            with self.assertRaisesRegex(BUNDLE.CandidateSourceBundleError, "not from main"):
                BUNDLE.derive(root, "7" * 40)
        with tempfile.TemporaryDirectory() as directory:
            root, _ = self.fixture(Path(directory) / "bundle")
            merged = json.loads((root / "difficulty_candidates.json").read_text())
            merged["candidates"][0]["maxDependencyDepth"] = 99
            (root / "difficulty_candidates.json").write_text(json.dumps(merged) + "\n")
            with self.assertRaisesRegex(BUNDLE.CandidateSourceBundleError, "differs from exact inputs"):
                BUNDLE.derive(root, "7" * 40)

    def test_schema_and_workflows_preserve_review_required_mixed_lineage(self) -> None:
        schema = json.loads((ROOT / "schemas/candidate-source-bundle.schema.json").read_text())
        self.assertEqual(schema["properties"]["schema"]["const"], BUNDLE.SCHEMA)
        mixed = (ROOT / ".github/workflows/mixed-case-candidate-cohort.yml").read_text()
        review = (ROOT / ".github/workflows/multi-repo-candidate-cohort-review.yml").read_text()
        self.assertIn("scripts/multi-repo-analysis-run.py validate", mixed)
        self.assertIn("scripts/collect-github-natural-repair.py validate", mixed)
        self.assertIn("scripts/candidate-source-bundle.py validate", mixed)
        self.assertIn("--method-revision \"$GITHUB_SHA\"", mixed)
        self.assertIn("name: multi-repo-candidate-cohort-proposal", mixed)
        self.assertIn(".github/workflows/multi-repo-candidate-cohort.yml", review)
        self.assertIn(".github/workflows/mixed-case-candidate-cohort.yml", review)
        self.assertIn("scripts/candidate-source-bundle.py validate", review)
        self.assertNotIn("automaticPromotion: true", mixed + review)


if __name__ == "__main__":
    unittest.main()
