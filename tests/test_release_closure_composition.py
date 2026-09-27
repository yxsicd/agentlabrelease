from __future__ import annotations

import hashlib
import importlib.util
import copy
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

    def test_composition_closes_every_selected_component_asset_without_binary_work(self) -> None:
        value = MODULE.compose(
            self.base,
            self.registry,
            self.registry_bytes,
            "0.1.0-alpha.12",
            self.revision,
        )
        self.assertEqual(value["releaseTag"], "v0.1.0-alpha.12")
        self.assertEqual(value["sources"]["releaseGitSha"], self.revision)
        expected_urls = {
            asset["url"]
            for component in self.registry["components"]
            if component.get("status", "").startswith("selected")
            for asset in component["assets"]
        }
        self.assertEqual({asset["url"] for asset in value["assets"]}, expected_urls)
        self.assertGreater(len(value["assets"]), len(self.base["assets"]))
        self.assertEqual(value["reuse"]["reusedAssetCount"], len(expected_urls))
        self.assertEqual(len(value["assets"]), len(expected_urls))
        self.assertEqual(value["reuse"]["newBinaryBuildCount"], 0)
        self.assertEqual(value["reuse"]["newBinaryUploadCount"], 0)
        self.assertIn(
            "public-install-deploy-smoke-release-closure",
            value["qualificationPlan"]["requiredChecks"],
        )
        self.assertEqual(
            value["componentRegistry"]["sha256"],
            hashlib.sha256(self.registry_bytes).hexdigest(),
        )
        self.assertEqual(
            value["developerPreviewScope"]["absolutePowerThermal"],
            "not-qualified",
        )
        self.assertFalse(value["qualificationPlan"]["automaticPromotion"])

    def test_composition_can_exclude_unrequalified_harmony_execution(self) -> None:
        value = MODULE.compose(
            self.base,
            self.registry,
            self.registry_bytes,
            "0.1.0-alpha.14",
            self.revision,
            linux_emulator_acceptance_required=False,
        )
        self.assertEqual(
            value["developerPreviewScope"]["linuxHarmonyEmulatorExecution"],
            "not-qualified-in-this-release",
        )
        self.assertFalse(
            value["qualificationPlan"]["linuxEmulatorAcceptanceRequired"]
        )

    def test_composition_replaces_one_independently_released_component(self) -> None:
        registry = copy.deepcopy(self.registry)
        component = next(
            item for item in registry["components"]
            if item["id"] == "mcpgit-program-linux-x64"
        )
        old_urls = {
            asset["url"]
            for asset in self.base["assets"]
            if asset["registryComponent"] == component["id"]
        }
        component["immutableRef"] = "mcpgit-git-" + "f" * 40 + "-linux-amd64"
        component["assets"] = [{
            "id": "mcpgit-program-archive",
            "url": "https://github.com/yxsicd/mcpgitrelease/releases/download/"
                   + component["immutableRef"] + "/mcpgit-program-updated.tar.gz",
            "bytes": 43,
            "sha256": "f" * 64,
        }]
        registry_bytes = json.dumps(registry, sort_keys=True).encode()

        value = MODULE.compose(
            self.base,
            registry,
            registry_bytes,
            "0.1.0-alpha.15",
            self.revision,
        )

        selected = [
            asset for asset in value["assets"]
            if asset["registryComponent"] == component["id"]
        ]
        self.assertEqual(selected, [{
            "id": "mcpgit-program-archive",
            "kind": "mcpgit",
            "url": component["assets"][0]["url"],
            "sha256": "f" * 64,
            "bytes": 43,
            "immutableRef": component["immutableRef"],
            "registryComponent": component["id"],
        }])
        self.assertTrue(old_urls.isdisjoint({asset["url"] for asset in value["assets"]}))

    def test_composition_rejects_asset_drift_under_same_immutable_ref(self) -> None:
        registry = copy.deepcopy(self.registry)
        component = next(
            item for item in registry["components"]
            if item["id"] == "agentlab-control-linux-x64"
        )
        component["assets"][0]["sha256"] = "f" * 64
        registry_bytes = json.dumps(registry, sort_keys=True).encode()
        with self.assertRaisesRegex(ValueError, "unchanged component asset identity"):
            MODULE.compose(
                self.base,
                registry,
                registry_bytes,
                "0.1.0-alpha.15",
                self.revision,
            )

    def test_preview_rejects_omitting_one_registered_descriptor(self) -> None:
        value = MODULE.compose(
            self.base,
            self.registry,
            self.registry_bytes,
            "0.1.0-alpha.12",
            self.revision,
        )
        value["assets"] = [
            asset
            for asset in value["assets"]
            if asset["id"] != "harmony-cli-descriptor"
        ]
        value["reuse"]["reusedAssetCount"] -= 1
        with self.assertRaisesRegex(ValueError, "every selected component asset"):
            MODULE.validator_module().validate_closure(
                value,
                self.registry,
                self.registry_bytes,
            )

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
