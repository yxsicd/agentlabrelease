from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/compose-release-closure.py"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


MODULE = load_module("compose_release_closure", SCRIPT)


class ReleaseClosureCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.revision = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        cls.base = json.loads(
            (ROOT / "release/closures/v0.1.0-alpha.11.json").read_text()
        )
        cls.registry_path = ROOT / "release/components/registry.json"
        cls.registry_bytes = cls.registry_path.read_bytes()
        cls.registry = json.loads(cls.registry_bytes)

    def test_composition_reuses_every_asset_without_binary_work(self) -> None:
        value = MODULE.compose(
            self.base,
            self.registry,
            self.registry_bytes,
            "0.1.0-alpha.12",
            self.revision,
        )
        self.assertEqual(value["releaseTag"], "v0.1.0-alpha.12")
        self.assertEqual(value["sources"]["releaseGitSha"], self.revision)
        self.assertEqual(value["assets"], self.base["assets"])
        self.assertEqual(value["reuse"]["newBinaryBuildCount"], 0)
        self.assertEqual(value["reuse"]["newBinaryUploadCount"], 0)
        self.assertEqual(
            value["componentRegistry"]["sha256"],
            hashlib.sha256(self.registry_bytes).hexdigest(),
        )
        self.assertEqual(
            value["developerPreviewScope"]["absolutePowerThermal"],
            "not-qualified",
        )
        self.assertFalse(value["qualificationPlan"]["automaticPromotion"])

    def test_cli_refuses_to_overwrite_closure(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = pathlib.Path(raw) / "closure.json"
            output.write_text("retained\n")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--base", str(ROOT / "release/closures/v0.1.0-alpha.11.json"),
                    "--registry", str(self.registry_path),
                    "--version", "0.1.0-alpha.12",
                    "--release-source-revision", self.revision,
                    "--output", str(output),
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(output.read_text(), "retained\n")

    def test_version_must_advance_base(self) -> None:
        with self.assertRaisesRegex(ValueError, "advance"):
            MODULE.compose(
                self.base,
                self.registry,
                self.registry_bytes,
                "0.1.0-alpha.11",
                self.revision,
            )

    def test_unknown_source_revision_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a local commit"):
            MODULE.compose(
                self.base,
                self.registry,
                self.registry_bytes,
                "0.1.0-alpha.12",
                "f" * 40,
            )


if __name__ == "__main__":
    unittest.main()
