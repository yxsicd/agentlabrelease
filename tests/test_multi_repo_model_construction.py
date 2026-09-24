import hashlib
import json
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class MultiRepoModelConstructionTest(unittest.TestCase):
    def test_fixture_git_revisions_are_reproducible(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = pathlib.Path(temporary)
            revisions = []
            for name in ("first", "second"):
                output = temporary / name
                subprocess.run(
                    [
                        "python3",
                        str(ROOT / "scripts/prepare-multi-repo-construction-fixture.py"),
                        "--source",
                        str(ROOT / "examples/multi-repo-case/baseline"),
                        "--output",
                        str(output),
                    ],
                    check=True,
                    capture_output=True,
                )
                manifest = json.loads((output / "manifest.json").read_text())
                revisions.append({row["id"]: row["revision"] for row in manifest["repositories"]})
            self.assertEqual(revisions[0], revisions[1])
            self.assertEqual(set(revisions[0]), {"app", "contracts", "service"})
            self.assertTrue(all(len(value) == 40 for value in revisions[0].values()))

    def test_workflow_keeps_gateway_secret_on_trusted_main_step(self):
        workflow = (ROOT / ".github/workflows/multi-repo-model-construction.yml").read_text()
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
        self.assertEqual(workflow.count("secrets.AGENTLAB_LM_GATEWAY_KEY"), 1)
        self.assertIn("if: always()", workflow)
        self.assertIn("multi-repo-model-construction", workflow)

    def test_fixture_script_is_release_manifested(self):
        expected = hashlib.sha256(
            (ROOT / "scripts/prepare-multi-repo-construction-fixture.py").read_bytes()
        ).hexdigest()
        entries = {
            path: digest
            for digest, path in (
                line.split("  ", 1)
                for line in (ROOT / "SHA256SUMS").read_text().splitlines()
            )
        }
        self.assertEqual(
            entries.get("scripts/prepare-multi-repo-construction-fixture.py"), expected
        )


if __name__ == "__main__":
    unittest.main()
