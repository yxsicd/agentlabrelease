import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / "release" / "targets" / name).read_text())


def test_portable_targets_require_only_docker_for_base_runtime():
    for name in ("generic-linux-agentlab.json", "wsl2-agentlab.json"):
        target = load(name)
        host = target["hostPrerequisites"]
        assert host["requiredCommands"] == ["docker"]
        assert {"python3", "zstd", "tar", "bun", "node", "rustc", "cargo", "git", "gh"} <= set(
            host["notRequiredCommands"]
        )
        assert host["onlineBootstrapAcquisition"]["oneOfCommands"] == ["curl", "wget"]


def test_native_sessionfs_requirements_are_explicit_not_machine_specific():
    forbidden = ("aiwsl", "/home/", "hostname")
    for name in ("generic-linux-agentlab.json", "wsl2-agentlab.json"):
        target = load(name)
        native = target["hostPrerequisites"]["nativeSessionFs"]
        assert native["privilege"] == "root-or-passwordless-sudo"
        assert native["systemdRequired"] is True
        assert {"loop", "btrfs"} <= set(native["requiredKernelFeatures"])
        serialized = json.dumps(target).lower()
        for value in forbidden:
            assert value not in serialized
