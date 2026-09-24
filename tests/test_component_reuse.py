from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "component_reuse", ROOT / "scripts/component-reuse.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class ComponentReuseTests(unittest.TestCase):
    def git(self, repo: pathlib.Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, text=True, capture_output=True, check=True
        ).stdout.strip()

    def commit(self, repo: pathlib.Path, message: str) -> str:
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-m", message)
        return self.git(repo, "rev-parse", "HEAD")

    def test_unrelated_monorepo_change_reuses_owned_component(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw)
            self.git(repo, "init")
            self.git(repo, "config", "user.name", "AgentLab Test")
            self.git(repo, "config", "user.email", "agentlab@example.invalid")
            (repo / "component").mkdir()
            (repo / "build").mkdir()
            (repo / "unrelated").mkdir()
            (repo / "component/source.txt").write_text("v1\n")
            (repo / "build/component.sh").write_text("build-v1\n")
            (repo / "unrelated/note.txt").write_text("one\n")
            first = self.commit(repo, "initial")

            component = {
                "id": "sample",
                "kind": "runtime",
                "platform": "linux-x64",
                "status": "current",
                "immutableRef": "sample-v1",
                "source": {
                    "repository": "https://example.invalid/mono.git",
                    "revision": first,
                    "ownedPaths": ["component"],
                },
                "inputIdentity": {
                    "mode": "git-tree-v1",
                    "effectiveInputDigest": "0" * 64,
                    "buildRecipePaths": ["build/component.sh"],
                    "dependencies": {"toolchain": "sha256:test"},
                },
                "assets": [
                    {
                        "id": "sample",
                        "url": "https://example.invalid/releases/download/sample-v1/sample.bin",
                        "bytes": 1,
                        "sha256": "a" * 64,
                    }
                ],
            }
            basis = MODULE.git_tree_basis(component, repo, first)
            component["inputIdentity"]["effectiveInputDigest"] = MODULE.canonical_digest(basis)

            (repo / "unrelated/note.txt").write_text("two\n")
            unrelated = self.commit(repo, "unrelated")
            self.assertEqual(MODULE.plan(component, repo, unrelated)["action"], "reuse")

            (repo / "component/source.txt").write_text("v2\n")
            owned = self.commit(repo, "owned")
            self.assertEqual(MODULE.plan(component, repo, owned)["action"], "rebuild")

    def test_build_recipe_change_requires_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = pathlib.Path(raw)
            self.git(repo, "init")
            self.git(repo, "config", "user.name", "AgentLab Test")
            self.git(repo, "config", "user.email", "agentlab@example.invalid")
            (repo / "component").mkdir()
            (repo / "build").mkdir()
            (repo / "component/source.txt").write_text("v1\n")
            (repo / "build/component.sh").write_text("build-v1\n")
            first = self.commit(repo, "initial")
            component = {
                "id": "sample",
                "kind": "runtime",
                "platform": "linux-x64",
                "status": "current",
                "immutableRef": "sample-v1",
                "source": {
                    "repository": "https://example.invalid/mono.git",
                    "revision": first,
                    "ownedPaths": ["component"],
                },
                "inputIdentity": {
                    "mode": "git-tree-v1",
                    "effectiveInputDigest": "0" * 64,
                    "buildRecipePaths": ["build/component.sh"],
                    "dependencies": {},
                },
                "assets": [
                    {
                        "id": "sample",
                        "url": "https://example.invalid/releases/download/sample-v1/sample.bin",
                        "bytes": 1,
                        "sha256": "a" * 64,
                    }
                ],
            }
            component["inputIdentity"]["effectiveInputDigest"] = MODULE.canonical_digest(
                MODULE.git_tree_basis(component, repo, first)
            )
            (repo / "build/component.sh").write_text("build-v2\n")
            second = self.commit(repo, "recipe")
            self.assertEqual(MODULE.plan(component, repo, second)["action"], "rebuild")

    def test_checked_in_registry_is_valid_and_external_assets_reuse(self) -> None:
        registry = MODULE.load_registry(ROOT / "release/components/registry.json")
        component = MODULE.find_component(registry, "harmony-emulator-command-line-tools")
        result = MODULE.plan(component)
        self.assertEqual(result["action"], "reuse")
        self.assertTrue(result["automaticSourceImpactDecision"])

    def test_duplicate_component_is_rejected(self) -> None:
        registry = json.loads((ROOT / "release/components/registry.json").read_text())
        registry["components"].append(registry["components"][0])
        with self.assertRaisesRegex(ValueError, "duplicate component"):
            MODULE.validate_registry(registry)


if __name__ == "__main__":
    unittest.main()
