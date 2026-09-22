from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate-release-graph.py"
SPEC = importlib.util.spec_from_file_location("validate_release_graph", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def asset(kind: str, tag: str = "runtime-deadbeef") -> dict:
    return {
        "id": kind,
        "kind": kind,
        "url": f"https://github.com/yxsicd/agentlabrelease/releases/download/{tag}/{kind}.bin",
        "sha256": "a" * 64,
        "bytes": 42,
        "immutableRef": tag,
    }


def closure() -> dict:
    return {
        "schema": "agentlab.release_closure.v1",
        "releaseVersion": "0.1.0-alpha.10",
        "releaseTag": "v0.1.0-alpha.10",
        "sources": {"agentlabGitSha": "1" * 40, "llmrsGitSha": "2" * 40},
        "requiredSchemas": {
            "controlApi": "agentlabctl.release.v1",
            "lockSchema": "agentlab.environment_lock.v3",
            "receiptSchema": "agentlab.composition_install_receipt.v4",
            "componentGraphSchema": "agentlab.component_graph.v1",
        },
        "assets": [asset(kind) for kind in ("control", "composition", "runtime", "harmony", "mcpgit", "tools")],
        "contracts": {"mcpgit.session-template-contract": 5},
        "targetCompatibility": {
            "aiwsl": {"status": "qualified", "platform": "linux-x64"},
            "bluebwsl": {"status": "experimental", "platform": "linux-x64"},
        },
    }


class ReleaseGraphTests(unittest.TestCase):
    def test_valid_immutable_closure(self) -> None:
        MODULE.validate_closure(closure())

    def test_mutable_aldev_is_rejected(self) -> None:
        value = closure()
        value["assets"][0]["url"] = (
            "https://github.com/yxsicd/agentlabrelease/releases/download/aldev/control.bin"
        )
        with self.assertRaisesRegex(ValueError, "mutable channel"):
            MODULE.validate_closure(value)

    def test_schema_surface_is_explicit(self) -> None:
        value = closure()
        value["requiredSchemas"].pop("receiptSchema")
        with self.assertRaisesRegex(ValueError, "requiredSchemas"):
            MODULE.validate_closure(value)

    def test_historical_asset_requires_exact_digest(self) -> None:
        value = closure()
        value["assets"][2]["sha256"] = ""
        with self.assertRaisesRegex(ValueError, "sha256"):
            MODULE.validate_closure(value)

    def test_oci_identity_does_not_overload_image_id(self) -> None:
        value = closure()
        value["assets"].append(
            {
                "id": "runtime-image",
                "kind": "image",
                "url": "https://github.com/yxsicd/agentlabrelease/releases/download/image-deadbeef/runtime.tar.zst",
                "sha256": "b" * 64,
                "bytes": 100,
                "immutableRef": "image-deadbeef",
                "identity": {
                    "schema": "agentlab.oci_image_identity.v1",
                    "ociManifestDigest": "sha256:" + "c" * 64,
                    "ociConfigDigest": "sha256:" + "d" * 64,
                },
            }
        )
        MODULE.validate_closure(value)
        value["assets"][-1]["identity"].pop("ociConfigDigest")
        with self.assertRaisesRegex(ValueError, "manifest/config"):
            MODULE.validate_closure(value)

    def test_public_wsl2_target_keeps_blueb_and_self_hosted_isolation(self) -> None:
        value = json.loads((ROOT / "release/targets/wsl2-agentlab.json").read_text())
        MODULE.validate_target(value)
        self.assertEqual(value["qualificationStatus"], "experimental")
        self.assertIn("bluebwsl", value["aliases"])
        self.assertEqual(value["mcpgit"]["defaultMode"], "self-hosted")
        self.assertTrue(value["mcpgit"]["isolatedDataVolumeByDefault"])
        self.assertEqual(value["network"]["defaultBindHost"], "127.0.0.1")
        self.assertIn("wsl-restart", value["restartQualification"])

    def test_generic_linux_target_is_not_aiwsl_alias(self) -> None:
        value = json.loads((ROOT / "release/targets/generic-linux-agentlab.json").read_text())
        MODULE.validate_target(value)
        self.assertEqual(value["id"], "generic-linux")
        self.assertNotIn("aiwsl", value.get("aliases", []))


if __name__ == "__main__":
    unittest.main()
