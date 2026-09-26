from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build-harmony-evaluation-artifact.py"


SYNTHETIC_BUILDER = r'''#!/usr/bin/env python3
import argparse
import os
import pathlib

parser = argparse.ArgumentParser()
parser.add_argument("--workspace", required=True)
parser.add_argument("--artifact", required=True)
args = parser.parse_args()
marker = os.environ.get("SYNTHETIC_BUILD_MARKER")
if marker:
    pathlib.Path(marker).write_text("called")
if os.environ.get("SYNTHETIC_BUILD_FAIL"):
    raise SystemExit(23)
workspace = pathlib.Path(args.workspace)
app = (workspace / "app/Index.ets").read_bytes()
contract = (workspace / "shared/contracts/policy.ets").read_bytes()
artifact = pathlib.Path(args.artifact)
artifact.parent.mkdir(parents=True)
artifact.write_bytes(b"synthetic-hap\n" + app + b"\n" + contract)
'''


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HarmonyEvaluationCaseBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.app_repo, self.app_revision = self.make_repo(
            "app-repo",
            "https://example.invalid/app.git",
            {"Index.ets": "import { policy } from '@contracts/policy'\nText(policy)\n"},
        )
        self.contract_repo, self.contract_revision = self.make_repo(
            "contracts-repo",
            "https://example.invalid/contracts.git",
            {"src/policy.ets": "export const policy: string = 'Ready'\n"},
        )
        self.sources = [
            {
                "id": "app",
                "repository": "https://example.invalid/app.git",
                "revision": self.app_revision,
            },
            {
                "id": "contracts",
                "repository": "https://example.invalid/contracts.git",
                "revision": self.contract_revision,
            },
        ]
        source_set = hashlib.sha256(
            json.dumps(self.sources, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.case = self.root / "case.json"
        self.case.write_text(
            json.dumps(
                {
                    "schema": "agentlab.multi_repo_evaluation_case.v1",
                    "id": "synthetic-multi-repo-harmony-case",
                    "status": "frozen-calibrated",
                    "sourceSetSha256": source_set,
                    "sources": self.sources,
                    "oracle": {"authority": "independent-executable-oracle"},
                    "calibration": {"qualified": True},
                    "automaticPromotion": False,
                }
            ),
            encoding="utf-8",
        )
        self.builder = self.root / "builder.py"
        self.builder.write_text(SYNTHETIC_BUILDER, encoding="utf-8")
        self.builder.chmod(0o755)
        self.plan = self.root / "plan.json"
        self.write_plan()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_repo(self, name: str, origin: str, files: dict[str, str]):
        path = self.root / name
        path.mkdir()
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        subprocess.run(["git", "-C", str(path), "config", "user.name", "AgentLab Test"], check=True)
        subprocess.run(["git", "-C", str(path), "config", "user.email", "agentlab@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(path), "remote", "add", "origin", origin], check=True)
        for relative, content in files.items():
            target = path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        subprocess.run(["git", "-C", str(path), "add", "."], check=True)
        subprocess.run(["git", "-C", str(path), "commit", "-qm", "fixture"], check=True)
        revision = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
        ).strip()
        return path, revision

    def write_plan(self, source_materialization=None) -> None:
        mappings = source_materialization or [
            {
                "sourceId": "app",
                "checkout": str(self.app_repo),
                "sourcePath": ".",
                "targetPath": "app",
            },
            {
                "sourceId": "contracts",
                "checkout": str(self.contract_repo),
                "sourcePath": "src",
                "targetPath": "shared/contracts",
            },
        ]
        self.plan.write_text(
            json.dumps(
                {
                    "schema": "agentlab.harmony_case_build_plan.v1",
                    "evaluationCase": {"path": str(self.case), "sha256": digest(self.case)},
                    "sourceMaterialization": mappings,
                    "build": {
                        "executable": str(self.builder),
                        "executableSha256": digest(self.builder),
                        "arguments": [
                            "--workspace", "{workspace}",
                            "--artifact", "{artifact}",
                        ],
                        "workingDirectory": ".",
                        "artifactPath": "build/entry-default-unsigned.hap",
                        "timeoutSeconds": 30,
                        "environment": {"SYNTHETIC_MODE": "offline"},
                    },
                    "automaticPromotion": False,
                }
            ),
            encoding="utf-8",
        )

    def run_builder(self, output: pathlib.Path, env: dict[str, str] | None = None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--plan", str(self.plan), "--output", str(output)],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, **(env or {})},
        )

    def test_pinned_git_sources_materialize_and_build_receipt(self) -> None:
        output = self.root / "build-output"
        completed = self.run_builder(output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads((output / "build-receipt.json").read_text())
        materialization = json.loads((output / "source-materialization.json").read_text())
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["buildAuthority"], "independent-harmony-build")
        self.assertEqual(receipt["hapSha256"], digest(output / "artifact.hap"))
        self.assertEqual(receipt["sourceMaterializationSha256"], digest(output / "source-materialization.json"))
        self.assertFalse(receipt["automaticPromotion"])
        self.assertEqual(materialization["fileCount"], 2)
        self.assertEqual(
            [row["targetPath"] for row in materialization["files"]],
            ["app/Index.ets", "shared/contracts/policy.ets"],
        )
        self.assertFalse((output / "workspace").exists())

    def test_origin_drift_fails_before_build(self) -> None:
        subprocess.run(
            ["git", "-C", str(self.contract_repo), "remote", "set-url", "origin", "https://example.invalid/wrong.git"],
            check=True,
        )
        marker = self.root / "builder-called"
        output = self.root / "build-output"
        completed = self.run_builder(output, {"SYNTHETIC_BUILD_MARKER": str(marker)})
        self.assertEqual(completed.returncode, 1)
        self.assertFalse(marker.exists())
        stage = next(self.root.glob(".build-output.stage-*"))
        failure = json.loads((stage / "failure.json").read_text())
        self.assertIn("origin differs", failure["error"])

    def test_uncommitted_worktree_bytes_are_not_materialized(self) -> None:
        (self.app_repo / "Index.ets").write_text(
            "Text('dirty bytes must be excluded')\n",
            encoding="utf-8",
        )
        output = self.root / "build-output"
        completed = self.run_builder(output)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        artifact = (output / "artifact.hap").read_bytes()
        self.assertIn(b"Text(policy)", artifact)
        self.assertNotIn(b"dirty bytes", artifact)

    def test_materialization_collision_fails_before_build(self) -> None:
        self.write_plan(
            [
                {"sourceId": "app", "checkout": str(self.app_repo), "sourcePath": ".", "targetPath": "shared/contracts"},
                {"sourceId": "app", "checkout": str(self.app_repo), "sourcePath": ".", "targetPath": "shared/contracts"},
                {"sourceId": "contracts", "checkout": str(self.contract_repo), "sourcePath": "src", "targetPath": "other/contracts"},
            ]
        )
        marker = self.root / "builder-called"
        output = self.root / "build-output"
        completed = self.run_builder(output, {"SYNTHETIC_BUILD_MARKER": str(marker)})
        self.assertEqual(completed.returncode, 1)
        self.assertFalse(marker.exists())
        stage = next(self.root.glob(".build-output.stage-*"))
        failure = json.loads((stage / "failure.json").read_text())
        self.assertIn("target collision", failure["error"])

    def test_build_failure_retains_materialized_workspace(self) -> None:
        output = self.root / "build-output"
        completed = self.run_builder(output, {"SYNTHETIC_BUILD_FAIL": "1"})
        self.assertEqual(completed.returncode, 1)
        self.assertFalse(output.exists())
        stage = next(self.root.glob(".build-output.stage-*"))
        failure = json.loads((stage / "failure.json").read_text())
        self.assertIn("exit 23", failure["error"])
        self.assertTrue((stage / "workspace/app/Index.ets").is_file())
        self.assertTrue((stage / "build.stdout.log").is_file())

    def test_existing_output_is_never_overwritten(self) -> None:
        output = self.root / "build-output"
        output.mkdir()
        marker = output / "marker"
        marker.write_text("keep", encoding="utf-8")
        completed = self.run_builder(output)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(marker.read_text(), "keep")
        self.assertEqual(list(self.root.glob(".build-output.stage-*")), [])


if __name__ == "__main__":
    unittest.main()
