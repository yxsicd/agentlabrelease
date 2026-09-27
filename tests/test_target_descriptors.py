import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "release" / "targets" / name).read_text())


class TargetDescriptorTests(unittest.TestCase):
    def test_portable_targets_require_only_docker_for_base_runtime(self):
        for name in ("generic-linux-agentlab.json", "wsl2-agentlab.json"):
            target = load(name)
            host = target["hostPrerequisites"]
            self.assertEqual(host["requiredCommands"], ["docker"])
            self.assertLessEqual(
                {"python3", "zstd", "tar", "bun", "node", "rustc", "cargo", "git", "gh"},
                set(host["notRequiredCommands"]),
            )
            self.assertEqual(host["onlineBootstrapAcquisition"]["oneOfCommands"], ["curl", "wget"])
            self.assertEqual(
                host["onlineBootstrapAcquisition"]["oneOfIntegrityCommands"],
                ["sha256sum", "shasum", "openssl"],
            )


    def test_native_sessionfs_requirements_are_explicit_not_machine_specific(self):
        forbidden = ("aiwsl", "/home/", "hostname")
        for name in ("generic-linux-agentlab.json", "wsl2-agentlab.json"):
            target = load(name)
            native = target["hostPrerequisites"]["nativeSessionFs"]
            self.assertEqual(native["privilege"], "root-or-passwordless-sudo")
            self.assertIs(native["systemdRequired"], True)
            self.assertLessEqual({"loop", "btrfs"}, set(native["requiredKernelFeatures"]))
            serialized = json.dumps(target).lower()
            for value in forbidden:
                self.assertNotIn(value, serialized)
