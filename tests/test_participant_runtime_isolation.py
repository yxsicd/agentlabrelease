from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/validate-participant-runtime.py"
SPEC = importlib.util.spec_from_file_location("participant_runtime_validator", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ParticipantRuntimeIsolationTests(unittest.TestCase):
    def prepare(self, root: Path):
        runtime = root / "pi-runtime"
        case = root / "participant-case"
        workspace = root / "attempt/workspace"
        state = root / "attempt/participant-state"
        receipts = root / "attempt/participant-evidence/runtime-isolation"
        forbidden = root / "operator/evaluator"
        for path in (runtime / "node_modules/.bin", case, workspace, state, receipts, forbidden):
            path.mkdir(parents=True, exist_ok=True)
        (runtime / "package-lock.json").write_text("fixture lock\n")
        (runtime / "node_modules/.bin/pi").write_text("fixture pi\n")
        (case / "manifest.json").write_text("{}\n")
        (forbidden / "oracle.mjs").write_text("hidden\n")
        image = "sha256:" + "1" * 64
        config = {
            "schema": "agentlab.participant_docker_runtime.v1",
            "executor": "docker",
            "automaticQualification": False,
            "imageId": image,
            "imageEnvironmentNames": ["NODE_VERSION", "PATH"],
            "piRuntimeRoot": str(runtime),
            "caseInputRoot": str(case),
            "participantManifestSha256": sha(case / "manifest.json"),
            "forbiddenHostPaths": [str(forbidden)],
        }
        config_path = root / "runtime.json"
        config_path.write_text(json.dumps(config))
        label = "stage-one"
        inspect = [{
            "Image": image,
            "Mounts": [
                {"Type": "bind", "Source": str(workspace.resolve()), "Destination": "/workspace", "RW": True},
                {"Type": "bind", "Source": str(runtime.resolve()), "Destination": "/runtime", "RW": False},
                {"Type": "bind", "Source": str(case.resolve()), "Destination": "/agentlab/case", "RW": False},
                {"Type": "bind", "Source": str(state.resolve()), "Destination": "/agent", "RW": True},
            ],
            "HostConfig": {
                "ReadonlyRootfs": True,
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges"],
                "PidsLimit": 256,
                "PidMode": "",
                "Privileged": False,
                "NetworkMode": "host",
                "Tmpfs": {"/tmp": "rw,nosuid,nodev,noexec,size=268435456,mode=1777"},
            },
            "Config": {
                "Entrypoint": ["/runtime/node_modules/.bin/pi"],
                "Env": ["NODE_VERSION=22", "PATH=/runtime/node_modules/.bin:/usr/local/bin:/usr/bin:/bin", "HOME=/agent", "PI_CODING_AGENT_DIR=/agent"],
            },
        }]
        inspect_path = receipts / f"{label}.container-inspect.json"
        final_path = receipts / f"{label}.container-final.json"
        inspect_path.write_text(json.dumps(inspect))
        final_path.write_text(json.dumps([{"State": {"ExitCode": 0, "Status": "exited"}}]))
        receipt = {
            "schema": "agentlab.participant_runtime_isolation_receipt.v1",
            "label": label,
            "status": "completed",
            "executor": "docker",
            "exitCode": 0,
            "containerStateExitCode": 0,
            "runtimeConfigSha256": sha(config_path),
            "participantManifestSha256": config["participantManifestSha256"],
            "imageId": image,
            "externalCredentialInjected": False,
            "filesystemIsolationQualified": False,
            "networkEgressIsolationQualified": False,
            "containerInspectSha256": sha(inspect_path),
            "containerFinalSha256": sha(final_path),
            "containerId": "2" * 64,
            "probes": {
                "caseInputReadable": True,
                "piRuntimeReadable": True,
                "workspaceWritable": True,
                "dockerSocketVisible": False,
                "externalCredentialNamesVisibleInPidOne": False,
                "forbiddenPaths": [{
                    "pathSha256": hashlib.sha256(str(forbidden).encode()).hexdigest(),
                    "visibleAtHostAbsolutePath": False,
                }],
            },
        }
        receipt_path = receipts / f"{label}.json"
        receipt_path.write_text(json.dumps(receipt))
        return config_path, receipts, workspace, state, label, inspect_path

    def test_independent_validator_qualifies_filesystem_but_not_network(self):
        with tempfile.TemporaryDirectory() as directory:
            args = self.prepare(Path(directory))
            result = MODULE.validate_runtime_receipts(*args[:4], [args[4]])
            self.assertTrue(result["filesystemIsolationQualified"])
            self.assertTrue(result["externalCredentialIsolationQualified"])
            self.assertFalse(result["networkEgressIsolationQualified"])

    def test_rejects_an_extra_host_mount_even_if_receipt_claims_success(self):
        with tempfile.TemporaryDirectory() as directory:
            config, receipts, workspace, state, label, inspect_path = self.prepare(Path(directory))
            inspect = json.loads(inspect_path.read_text())
            inspect[0]["Mounts"].append({
                "Type": "bind", "Source": "/", "Destination": "/host", "RW": False,
            })
            inspect_path.write_text(json.dumps(inspect))
            receipt_path = receipts / f"{label}.json"
            receipt = json.loads(receipt_path.read_text())
            receipt["containerInspectSha256"] = sha(inspect_path)
            receipt_path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "least-mount policy"):
                MODULE.validate_runtime_receipts(config, receipts, workspace, state, [label])

    def test_rejects_external_key_environment_name(self):
        with tempfile.TemporaryDirectory() as directory:
            config, receipts, workspace, state, label, inspect_path = self.prepare(Path(directory))
            inspect = json.loads(inspect_path.read_text())
            inspect[0]["Config"]["Env"].append("AGENTLAB_LM_GATEWAY_KEY=leaked")
            inspect_path.write_text(json.dumps(inspect))
            receipt_path = receipts / f"{label}.json"
            receipt = json.loads(receipt_path.read_text())
            receipt["containerInspectSha256"] = sha(inspect_path)
            receipt_path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "environment surface differs"):
                MODULE.validate_runtime_receipts(config, receipts, workspace, state, [label])


if __name__ == "__main__":
    unittest.main()
