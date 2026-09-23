from __future__ import annotations

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "release/alharmony/harmony-emulator-linux-x64-26.0.0.821.json"
INSTALLER = ROOT / "scripts/agentlab-harmony-emulator.sh"


class HarmonyEmulatorReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.value = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_external_vendor_assets_fail_closed_for_publication(self) -> None:
        self.assertEqual(
            self.value["schema"], "agentlab.harmony_emulator_external_bundle.v1"
        )
        distribution = self.value["distribution"]
        self.assertFalse(distribution["publicBinaryRedistribution"])
        self.assertEqual(
            distribution["status"], "blocked-without-vendor-written-permission"
        )
        self.assertEqual(self.value["publicationMode"], "bring-your-own-vendor-assets")

    def test_verified_asset_identities_are_exact(self) -> None:
        assets = {item["id"]: item for item in self.value["assets"]}
        self.assertEqual(assets["command-line-tools"]["bytes"], 932070897)
        self.assertEqual(
            assets["command-line-tools"]["sha256"],
            "ad1eb9a255b6fc6f022a646bd536ef230d66e47aea1f9177a793924b83ebb649",
        )
        self.assertEqual(assets["phone-system-image"]["bytes"], 1568108769)
        self.assertEqual(
            assets["phone-system-image"]["sha256"],
            "75c537cb6dc62291f96f0f247c148de653c9c6633c4dc5b0c34cc254909ae671",
        )
        for asset in assets.values():
            self.assertIn("--long=31", asset["compression"])
            self.assertNotIn("url", asset)

    def test_scope_is_x86_kvm_and_does_not_claim_arm_translation(self) -> None:
        self.assertEqual(self.value["platform"], "linux-x64")
        self.assertEqual(self.value["capabilities"]["imageAbi"], "x86")
        self.assertEqual(self.value["capabilities"]["acceleration"], "KVM")
        limitations = " ".join(self.value["limitations"])
        self.assertIn("ARM native", limitations)
        self.assertIn("hidden application-specific Oracle", limitations)
        self.assertIn("Absolute power and thermal", limitations)

    def test_installer_is_fail_closed(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("zstd -t --long=31", source)
        self.assertIn("--acknowledge-vendor-agreements", source)
        self.assertIn("refusing to overwrite existing install root", source)
        self.assertIn("/dev/kvm", source)

    def test_run_case_emits_functional_and_profile_evidence(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("agentlab.harmony_emulator_case_result.v1", source)
        self.assertIn("shell uitest dumpLayout", source)
        self.assertIn('! grep -iF "failed"', source)
        self.assertIn('install -r "$hap"', source)
        self.assertIn('shell bm dump -n "$bundle"', source)
        self.assertIn("shell uitest uiInput swipe 630 2400 630 600 1000", source)
        self.assertIn('shell aa start -a "$ability" -b "$bundle"', source)
        self.assertIn('grep -F "start ability successfully"', source)
        self.assertIn('shell ps -A', source)
        self.assertIn('process_hint=${bundle#com.}', source)
        self.assertIn('process_attempt" -le 15', source)
        self.assertIn("-screenshot", source)
        self.assertIn('screenshot_attempt" -le 10', source)
        self.assertIn("SP_daemon", source)
        self.assertIn('"powerThermalAuthority":"unavailable_on_emulator"', source)
        self.assertIn("refusing to overwrite existing output", source)

    def test_manifest_claims_only_the_newly_qualified_case_scope(self) -> None:
        operations = self.value["capabilities"]["validatedOperations"]
        for operation in [
            "hdc-connect",
            "hap-install",
            "bundle-query",
            "ability-launch",
            "process-check",
            "screenshot",
            "smartperf-proxy-profile",
        ]:
            self.assertIn(operation, operations)
        self.assertNotIn("absolute-power", operations)
        self.assertNotIn("thermal", operations)


if __name__ == "__main__":
    unittest.main()
