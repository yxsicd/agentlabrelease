from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/materialize-release-closure.py"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


MODULE = load_module("materialize_release_closure", SCRIPT)


class ReleaseClosureMaterializationTests(unittest.TestCase):
    def fixture(self):
        registry_bytes = (ROOT / "release/components/registry.json").read_bytes()
        registry = json.loads(registry_bytes)
        closure_bytes = (ROOT / "release/closures/v0.1.0-alpha.12.json").read_bytes()
        closure = json.loads(closure_bytes)
        by_kind = {asset["kind"]: asset for asset in closure["assets"]}
        lock = {
            "schema": "agentlab.environment_lock.v3",
            "sourceRevision": "1" * 40,
            "images": [],
            "components": [
                {
                    "slot": "release",
                    "artifact": next(
                        asset["url"]
                        for asset in closure["assets"]
                        if asset["id"] == "agentlab-runtime-archive"
                    ),
                    "descriptor": next(
                        asset["url"]
                        for asset in closure["assets"]
                        if asset["id"] == "agentlab-runtime-descriptor"
                    ),
                    "archiveSha256": next(
                        asset["sha256"]
                        for asset in closure["assets"]
                        if asset["id"] == "agentlab-runtime-archive"
                    ),
                }
            ],
        }
        lock_bytes = json.dumps(lock, sort_keys=True).encode()
        control_bytes = b"synthetic-control"
        lock_asset = by_kind["composition"]
        control_asset = by_kind["control"]
        lock_asset["bytes"] = len(lock_bytes)
        lock_asset["sha256"] = hashlib.sha256(lock_bytes).hexdigest()
        control_asset["bytes"] = len(control_bytes)
        control_asset["sha256"] = hashlib.sha256(control_bytes).hexdigest()
        for component in registry["components"]:
            for asset in component["assets"]:
                if asset["url"] == lock_asset["url"]:
                    asset["bytes"] = lock_asset["bytes"]
                    asset["sha256"] = lock_asset["sha256"]
                if asset["url"] == control_asset["url"]:
                    asset["bytes"] = control_asset["bytes"]
                    asset["sha256"] = control_asset["sha256"]
        return closure, closure_bytes, registry, registry_bytes, lock_bytes, control_bytes

    def test_materialization_binds_bootstrap_and_complete_lock_inputs(self) -> None:
        values = self.fixture()
        closure, _, registry, _, lock_bytes, control_bytes = values
        registry_bytes = json.dumps(registry, sort_keys=True).encode()
        closure["componentRegistry"]["sha256"] = hashlib.sha256(registry_bytes).hexdigest()
        closure_bytes = json.dumps(closure, sort_keys=True).encode()
        with tempfile.TemporaryDirectory() as raw:
            output = pathlib.Path(raw) / "materialized"
            receipt = MODULE.materialize(
                closure,
                closure_bytes,
                registry,
                registry_bytes,
                lock_bytes,
                control_bytes,
                output,
            )
            self.assertEqual(receipt["requiredCompositionAssetCount"], 2)
            self.assertEqual((output / "environment-lock.json").read_bytes(), lock_bytes)
            self.assertEqual((output / "agentlabctl").read_bytes(), control_bytes)
            self.assertEqual((output / "agentlabctl").stat().st_mode & 0o777, 0o755)
            self.assertFalse(receipt["automaticPromotion"])

    def test_missing_descriptor_is_rejected(self) -> None:
        closure, closure_bytes, registry, registry_bytes, lock_bytes, control_bytes = self.fixture()
        lock = json.loads(lock_bytes)
        lock["components"][0]["descriptor"] = "https://example.invalid/missing.json"
        changed_lock = json.dumps(lock, sort_keys=True).encode()
        lock_asset = next(asset for asset in closure["assets"] if asset["kind"] == "composition")
        lock_asset["bytes"] = len(changed_lock)
        lock_asset["sha256"] = hashlib.sha256(changed_lock).hexdigest()
        for component in registry["components"]:
            for asset in component["assets"]:
                if asset["url"] == lock_asset["url"]:
                    asset["bytes"] = lock_asset["bytes"]
                    asset["sha256"] = lock_asset["sha256"]
        registry_bytes = json.dumps(registry, sort_keys=True).encode()
        closure["componentRegistry"]["sha256"] = hashlib.sha256(registry_bytes).hexdigest()
        closure_bytes = json.dumps(closure, sort_keys=True).encode()
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(ValueError, "omits lock descriptor"):
                MODULE.materialize(
                    closure,
                    closure_bytes,
                    registry,
                    registry_bytes,
                    changed_lock,
                    control_bytes,
                    pathlib.Path(raw) / "materialized",
                )

    def test_public_ci_installs_alpha12_from_the_closure(self) -> None:
        workflow = (ROOT / ".github/workflows/release-validation.yml").read_text()
        smoke = (ROOT / "scripts/ci-public-install-deploy-smoke.sh").read_text()
        self.assertIn("target: release-closure", workflow)
        self.assertIn("closure: release/closures/v0.1.0-alpha.12.json", workflow)
        self.assertIn("AGENTLAB_RELEASE_CLOSURE: ${{ matrix.closure }}", workflow)
        self.assertIn('release_closure="${AGENTLAB_RELEASE_CLOSURE:-}"', smoke)
        self.assertIn("scripts/materialize-release-closure.py", smoke)
        self.assertIn(
            '"${parent_project}" "${child_project}" "${lock}"', smoke
        )
        self.assertNotIn('root / "downloads/environment-lock.json"', smoke)


if __name__ == "__main__":
    unittest.main()
