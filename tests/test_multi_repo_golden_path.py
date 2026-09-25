import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples/multi-repo-case/run-golden-path.py"
SPEC = importlib.util.spec_from_file_location("multi_repo_golden_path", SCRIPT)
GOLDEN = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GOLDEN)


class MultiRepoGoldenPathTest(unittest.TestCase):
    def test_portable_source_spec_strips_local_roots(self):
        manifest = {
            "repositories": [
                {
                    "id": "a",
                    "repository": "fixture://a",
                    "revision": "1" * 40,
                    "root": "/private/a",
                },
                {
                    "id": "b",
                    "repository": "fixture://b",
                    "revision": "2" * 40,
                    "root": "/private/b",
                },
            ],
            "moduleBindings": {"@demo/a": {"repositoryId": "a", "path": "src/a.ts"}},
        }
        value = GOLDEN.portable_spec(manifest)
        self.assertEqual(value["schema"], "agentlab.multi_repo_source_spec.v1")
        self.assertFalse(value["automaticPromotion"])
        self.assertNotIn("root", json.dumps(value))
        self.assertEqual(value["moduleBindings"], manifest["moduleBindings"])

    def test_invalid_revision_fails_before_creating_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--analyzer",
                    str(Path(directory) / "missing"),
                    "--method-revision",
                    "main",
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("method revision must be exact", completed.stderr)
            self.assertFalse(output.exists())

    def test_release_ci_runs_and_retains_the_integrated_chain(self):
        workflow = (ROOT / ".github/workflows/release-validation.yml").read_text()
        source = SCRIPT.read_text()
        self.assertIn("run-golden-path.py", workflow)
        self.assertIn("name: multi-repo-golden-path", workflow)
        self.assertIn("agentlab.multi_repo_golden_path.v1", source)
        self.assertIn('"protocolIntegrationQualified": True', source)
        self.assertIn('"realModelQualified": False', source)
        self.assertNotIn("AGENTLAB_LM_GATEWAY_KEY", source)


if __name__ == "__main__":
    unittest.main()
