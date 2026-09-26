from __future__ import annotations

import importlib.util
import hashlib
import json
import pathlib
import sys
import subprocess
import tempfile
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

    def test_alpha11_closure_remains_a_structurally_valid_historical_candidate(self) -> None:
        closure_value = json.loads(
            (ROOT / "release/closures/v0.1.0-alpha.11.json").read_text()
        )
        MODULE.validate_closure(closure_value)

    def test_alpha12_is_source_bound_reference_only_preview_candidate(self) -> None:
        alpha11 = json.loads(
            (ROOT / "release/closures/v0.1.0-alpha.11.json").read_text()
        )
        alpha12 = json.loads(
            (ROOT / "release/closures/v0.1.0-alpha.12.json").read_text()
        )
        registry_path = ROOT / "release/components/registry.json"
        registry_bytes = registry_path.read_bytes()
        registry = json.loads(registry_bytes)
        MODULE.validate_closure(alpha12, registry, registry_bytes)
        self.assertTrue(
            {asset["url"] for asset in alpha11["assets"]}.issubset(
                {asset["url"] for asset in alpha12["assets"]}
            )
        )
        self.assertEqual(
            alpha12["sources"]["releaseGitSha"],
            "4a365104cfd74af4c648f83ecb21d87ea3a9e787",
        )
        self.assertEqual(len(alpha12["assets"]), 22)
        self.assertEqual(alpha12["reuse"]["newBinaryBuildCount"], 0)
        self.assertEqual(alpha12["reuse"]["newBinaryUploadCount"], 0)
        self.assertEqual(alpha12["status"], "developer-preview-candidate")
        self.assertFalse(alpha12["developerPreviewScope"]["automaticPromotion"])

    def test_alpha13_source_cut_resolves_and_is_ancestor_of_checkout(self) -> None:
        alpha13 = json.loads(
            (ROOT / "release/closures/v0.1.0-alpha.13.json").read_text()
        )
        registry_path = ROOT / "release/components/registry.json"
        registry_bytes = registry_path.read_bytes()
        MODULE.validate_closure(alpha13, json.loads(registry_bytes), registry_bytes)
        head = MODULE.validate_release_source_git(alpha13, ROOT)
        self.assertEqual(len(head), 40)
        self.assertEqual(
            alpha13["sources"]["releaseGitSha"],
            "4f24f9a7eb1de98cbb0b695f02cf01da03ae26fb",
        )

    def test_unresolvable_release_source_is_rejected_by_git_validation(self) -> None:
        value = json.loads(
            (ROOT / "release/closures/v0.1.0-alpha.13.json").read_text()
        )
        value["sources"]["releaseGitSha"] = "f" * 40
        value["qualificationPlan"]["sourceGitSha"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "not a commit"):
            MODULE.validate_release_source_git(value, ROOT)

    def test_release_validation_fetches_history_for_source_ancestry(self) -> None:
        workflow = (ROOT / ".github/workflows/release-validation.yml").read_text()
        validate_job = workflow.split("\n  validate:\n", 1)[1].split("\n  participant-runtime-isolation:\n", 1)[0]
        self.assertIn("fetch-depth: 0", validate_job)
        self.assertIn('--git-root "$GITHUB_WORKSPACE"', validate_job)

    def test_alpha12_remote_asset_receipt_matches_closure(self) -> None:
        closure_path = ROOT / "release/closures/v0.1.0-alpha.12.json"
        closure_value = json.loads(closure_path.read_text())
        receipt = json.loads(
            (
                ROOT
                / "release/qualifications/alpha12-immutable-assets/summary.json"
            ).read_text()
        )
        self.assertEqual(receipt["schema"], "agentlab.release_graph_validation.v1")
        self.assertTrue(receipt["remote"])
        self.assertFalse(receipt["automaticPromotion"])
        self.assertEqual(len(receipt["closures"]), 1)
        retained = receipt["closures"][0]
        self.assertEqual(
            retained["sha256"], hashlib.sha256(closure_path.read_bytes()).hexdigest()
        )
        self.assertEqual(retained["releaseTag"], closure_value["releaseTag"])
        observed = {row["url"]: row for row in retained["remoteAssets"]}
        self.assertEqual(set(observed), {row["url"] for row in closure_value["assets"]})
        for asset in closure_value["assets"]:
            row = observed[asset["url"]]
            self.assertEqual(row["bytes"], asset["bytes"])
            self.assertEqual(row["sha256"], asset["sha256"])
            self.assertIsInstance(row["assetId"], int)
            self.assertGreater(row["assetId"], 0)

    def test_alpha12_harmony_acceptance_is_bound_to_exact_closure(self) -> None:
        closure_path = ROOT / "release/closures/v0.1.0-alpha.12.json"
        closure_value = json.loads(closure_path.read_text())
        receipt = json.loads(
            (
                ROOT
                / "release/qualifications/alpha12-harmony-acceptance-4a36510/summary.json"
            ).read_text()
        )
        self.assertEqual(receipt["schema"], "agentlab.release_harmony_acceptance.v1")
        self.assertEqual(
            receipt["closure"]["sha256"],
            hashlib.sha256(closure_path.read_bytes()).hexdigest(),
        )
        self.assertEqual(receipt["releaseTag"], closure_value["releaseTag"])
        self.assertEqual(
            receipt["releaseGitSha"], closure_value["sources"]["releaseGitSha"]
        )
        self.assertEqual(
            {row["device"]["oracleStatus"] for row in receipt["attempts"]},
            {"passed", "failed"},
        )
        positive = next(
            row for row in receipt["attempts"] if row["device"]["oracleStatus"] == "passed"
        )
        negative = next(
            row for row in receipt["attempts"] if row["device"]["oracleStatus"] == "failed"
        )
        self.assertTrue(positive["performance"]["profileValid"])
        self.assertGreaterEqual(positive["performance"]["sampleCount"], 3)
        self.assertEqual(negative["performance"]["status"], "not-run")
        self.assertEqual(receipt["remoteInspection"]["routeDecision"], "peer_direct")
        self.assertFalse(receipt["automaticPromotion"])

    def test_alpha12_registry_asset_drift_is_rejected(self) -> None:
        closure_value = json.loads(
            (ROOT / "release/closures/v0.1.0-alpha.12.json").read_text()
        )
        registry_path = ROOT / "release/components/registry.json"
        registry_bytes = registry_path.read_bytes()
        registry = json.loads(registry_bytes)
        closure_value["assets"][-1]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "differs from registry"):
            MODULE.validate_closure(closure_value, registry, registry_bytes)

    def test_current_closure_requires_release_source_identity(self) -> None:
        value = closure()
        value["status"] = "developer-preview-candidate"
        with self.assertRaisesRegex(ValueError, "releaseGitSha"):
            MODULE.validate_closure(value)
        value["sources"]["releaseGitSha"] = "3" * 40
        value["status"] = "assembly-candidate-unqualified"
        MODULE.validate_closure(value)

    def test_release_tag_must_match_version(self) -> None:
        value = closure()
        value["releaseTag"] = "v0.1.0-alpha.99"
        with self.assertRaisesRegex(ValueError, "exactly match"):
            MODULE.validate_closure(value)

    def test_preview_candidate_requires_exact_scope_and_plan(self) -> None:
        registry_path = ROOT / "release/components/registry.json"
        registry_bytes = registry_path.read_bytes()
        registry = json.loads(registry_bytes)
        value = json.loads(
            (ROOT / "release/closures/v0.1.0-alpha.12.json").read_text()
        )
        value.pop("developerPreviewScope")
        with self.assertRaisesRegex(ValueError, "scope"):
            MODULE.validate_closure(value, registry, registry_bytes)

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

    def test_public_asset_url_resolves_repository_tag_and_name(self) -> None:
        self.assertEqual(
            MODULE.github_asset_location(
                "https://github.com/yxsicd/agentlabrelease/releases/download/runtime-deadbeef/runtime.bin"
            ),
            ("yxsicd/agentlabrelease", "runtime-deadbeef", "runtime.bin"),
        )
        with self.assertRaisesRegex(ValueError, "canonical"):
            MODULE.github_asset_location(
                "https://github.com/yxsicd/agentlabrelease/releases/latest/runtime.bin"
            )

    def test_receipt_requires_remote_registry_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            receipt = pathlib.Path(raw) / "receipt.json"
            receipt.write_text("retained\n")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--closure", str(ROOT / "release/closures/v0.1.0-alpha.12.json"),
                    "--registry", str(ROOT / "release/components/registry.json"),
                    "--remote",
                    "--receipt", str(receipt),
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(receipt.read_text(), "retained\n")

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
