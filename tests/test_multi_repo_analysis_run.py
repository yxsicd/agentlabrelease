from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PREPARE = load_module(
    "multi_repo_source_preparation",
    ROOT / "scripts/prepare-multi-repo-analysis-sources.py",
)
RUN = load_module(
    "multi_repo_analysis_run",
    ROOT / "scripts/multi-repo-analysis-run.py",
)


class MultiRepoAnalysisRunTests(unittest.TestCase):
    def source_spec(self):
        return {
            "schema": "agentlab.multi_repo_source_spec.v1",
            "sources": [
                {
                    "id": "service",
                    "repository": "https://example.com/org/service.git",
                    "revision": "2" * 40,
                },
                {
                    "id": "app",
                    "repository": "https://example.com/org/app.git",
                    "revision": "1" * 40,
                },
            ],
            "moduleBindings": {
                "@demo/service": {
                    "repositoryId": "service",
                    "path": "src/service.ts",
                }
            },
            "automaticPromotion": False,
        }

    def evidence(self, root: Path):
        spec = PREPARE.validate_spec(self.source_spec())
        (root / "analysis").mkdir(parents=True)
        (root / "source-spec.json").write_text(json.dumps(spec, sort_keys=True) + "\n")
        manifest = {
            "schema": "agentlab.multi_repo_manifest.v1",
            "repositories": [
                {**row, "root": f"/checkout/{row['id']}"} for row in spec["sources"]
            ],
            "moduleBindings": spec["moduleBindings"],
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
        facts = root / "analysis/workspace_facts.jsonl"
        unsupported = root / "analysis/unsupported_sources.jsonl"
        difficulty = root / "analysis/difficulty_candidates.json"
        facts.write_text('{"id":"fact-a","kind":"call"}\n')
        unsupported.write_text("")
        difficulty.write_text(json.dumps({
            "schema": "agentlab.difficulty_candidates.v2",
            "sourceSetSha256": "a" * 64,
            "sources": spec["sources"],
            "moduleBindings": spec["moduleBindings"],
            "candidates": [],
            "automaticPromotion": False,
        }, sort_keys=True) + "\n")
        receipt = {
            "schema": "agentlab.multi_repo_analysis.v1",
            "manifestSha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "sourceSetSha256": "a" * 64,
            "facts": 1,
            "difficultyCandidates": 0,
            "unsupportedSources": 0,
            "sharedExternalModuleContracts": 0,
            "sharedExternalApiCallContracts": 0,
            "workspaceFactsSha256": hashlib.sha256(facts.read_bytes()).hexdigest(),
            "difficultyCandidatesSha256": hashlib.sha256(difficulty.read_bytes()).hexdigest(),
            "unsupportedSourcesSha256": hashlib.sha256(unsupported.read_bytes()).hexdigest(),
            "automaticPromotion": False,
        }
        (root / "analysis/multi_repo_analysis.json").write_text(
            json.dumps(receipt, sort_keys=True) + "\n"
        )
        return spec

    def test_source_spec_is_canonical_and_revision_fenced(self):
        value = PREPARE.validate_spec(self.source_spec())
        self.assertEqual([row["id"] for row in value["sources"]], ["app", "service"])
        self.assertEqual(value["moduleBindings"]["@demo/service"]["path"], "src/service.ts")

    def test_source_spec_rejects_credentials_local_hosts_and_symbolic_revisions(self):
        for repository, revision, message in (
            ("https://token@example.com/org/app.git", "1" * 40, "credential-free"),
            ("https://127.0.0.1/org/app.git", "1" * 40, "globally routable"),
            ("https://example.com/org/app.git", "main", "exact commit"),
        ):
            value = self.source_spec()
            value["sources"][1]["repository"] = repository
            value["sources"][1]["revision"] = revision
            with self.assertRaisesRegex(PREPARE.SourcePreparationError, message):
                PREPARE.validate_spec(value)

    def test_analysis_run_binds_all_native_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.evidence(root)
            run = RUN.derive(root, "f" * 40)
            self.assertEqual(run["counts"]["repositories"], 2)
            self.assertEqual(run["counts"]["facts"], 1)
            self.assertEqual(run["sourceSetSha256"], "a" * 64)
            self.assertFalse(run["automaticPromotion"])
            (root / "analysis/workspace_facts.jsonl").write_text("tampered\n")
            with self.assertRaisesRegex(RUN.AnalysisRunError, "program facts digest differs"):
                RUN.derive(root, "f" * 40)

    def test_exact_git_fetch_retries_transient_transport_failures(self):
        results = [
            SimpleNamespace(returncode=1, stderr="early EOF", stdout=""),
            SimpleNamespace(returncode=1, stderr="disconnect", stdout=""),
            SimpleNamespace(returncode=0, stderr="", stdout="ok\n"),
        ]
        with mock.patch.object(PREPARE.subprocess, "run", side_effect=results) as run:
            with mock.patch.object(PREPARE.time, "sleep") as sleep:
                output = PREPARE.run_git("fetch", "origin", "1" * 40, attempts=3)
        self.assertEqual(output, "ok")
        self.assertEqual(run.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])
        self.assertIn("http.version=HTTP/1.1", run.call_args.args[0])

    def test_materialization_uses_bounded_blob_filter_without_checkout(self):
        source = (ROOT / "scripts/prepare-multi-repo-analysis-sources.py").read_text()
        self.assertIn('"--filter=blob:limit=1048576"', source)
        self.assertIn('run_git("update-ref", "HEAD"', source)
        self.assertNotIn('run_git("checkout"', source)

    def test_workflows_use_run_addressed_analysis_not_fixture(self):
        analysis = (ROOT / ".github/workflows/multi-repo-analysis.yml").read_text()
        cohort = (ROOT / ".github/workflows/multi-repo-candidate-cohort.yml").read_text()
        self.assertIn("github.ref == 'refs/heads/main'", analysis)
        self.assertIn("scripts/prepare-multi-repo-analysis-sources.py", analysis)
        self.assertIn("scripts/multi-repo-analysis-run.py create", analysis)
        self.assertIn("name: multi-repo-analysis", analysis)
        self.assertIn("analysis_run_id", cohort)
        self.assertIn("expected_analysis_run_sha256", cohort)
        self.assertIn(".github/workflows/multi-repo-analysis.yml", cohort)
        self.assertIn("scripts/multi-repo-analysis-run.py validate", cohort)
        self.assertNotIn("prepare-multi-repo-construction-fixture.py", cohort)


if __name__ == "__main__":
    unittest.main()
