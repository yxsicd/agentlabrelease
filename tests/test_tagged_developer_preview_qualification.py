from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/qualify-tagged-developer-preview.py"
WORKFLOW = ROOT / ".github/workflows/developer-preview-qualification.yml"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


MODULE = load_module("qualify_tagged_developer_preview", SCRIPT)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TaggedDeveloperPreviewQualificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.lock = self.root / "environment-lock.json"
        self.lock.write_text(json.dumps({"sourceRevision": "runtime-source"}))
        self.closure = self.root / "closure.json"
        closure = json.loads(
            (ROOT / "release/closures/v0.1.0-alpha.12.json").read_text()
        )
        lock_asset = next(
            row for row in closure["assets"] if row["id"] == "environment-lock.json"
        )
        lock_asset["sha256"] = digest(self.lock)
        lock_asset["bytes"] = self.lock.stat().st_size
        self.write(self.closure, closure)
        closure_sha = digest(self.closure)
        self.assets = self.root / "assets.json"
        self.write(
            self.assets,
            {
                "schema": "agentlab.release_graph_validation.v1",
                "remote": True,
                "automaticPromotion": False,
                "closures": [
                    {
                        "sha256": closure_sha,
                        "releaseTag": closure["releaseTag"],
                        "assetCount": len(closure["assets"]),
                        "remoteAssets": [
                            {"url": row["url"], "sha256": row["sha256"]}
                            for row in closure["assets"]
                        ],
                    }
                ],
            },
        )
        self.harmony = self.root / "harmony.json"
        self.write(
            self.harmony,
            {
                "schema": "agentlab.release_harmony_acceptance.v1",
                "status": "accepted-developer-preview-review-required",
                "releaseTag": closure["releaseTag"],
                "releaseGitSha": closure["sources"]["releaseGitSha"],
                "closure": {"sha256": closure_sha},
                "environmentIdentity": "hwlinux:harmonyos-7.0.0:x86:kvm",
                "automaticPromotion": False,
            },
        )
        self.install = self.root / "summary.json"
        self.write(
            self.install,
            {
                "schema": "agentlab.public_install_deploy_smoke.v1",
                "ok": True,
                "sourceRevision": "runtime-source",
                "checks": {"compositionDownloaded": True, "projectVerified": True},
            },
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def write(path: pathlib.Path, value: dict) -> None:
        path.write_text(json.dumps(value, sort_keys=True))

    def qualify(self):
        return MODULE.qualify(
            self.closure,
            self.assets,
            self.harmony,
            self.install,
            self.lock,
            tag="v0.1.0-alpha.12",
            tag_sha="a" * 40,
            repository="yxsicd/agentlabrelease",
            run_id="424242",
            event="workflow_dispatch",
        )

    def test_exact_tag_closes_all_three_release_gates_without_promotion(self) -> None:
        receipt = self.qualify()
        self.assertEqual(
            receipt["status"], "qualified-developer-preview-review-required"
        )
        self.assertEqual(receipt["immutableAssets"]["remoteAssetCount"], 22)
        self.assertEqual(
            receipt["harmonyAcceptance"]["environmentIdentity"],
            "hwlinux:harmonyos-7.0.0:x86:kvm",
        )
        self.assertTrue(
            all(receipt["taggedCleanInstall"]["checks"].values())
        )
        self.assertFalse(receipt["automaticPromotion"])

    def test_branch_or_automatic_event_cannot_qualify(self) -> None:
        with self.assertRaisesRegex(ValueError, "explicitly dispatched"):
            MODULE.qualify(
                self.closure,
                self.assets,
                self.harmony,
                self.install,
                self.lock,
                tag="v0.1.0-alpha.12",
                tag_sha="a" * 40,
                repository="yxsicd/agentlabrelease",
                run_id="424242",
                event="push",
            )

    def test_stale_harmony_receipt_is_rejected(self) -> None:
        value = json.loads(self.harmony.read_text())
        value["closure"]["sha256"] = "0" * 64
        self.write(self.harmony, value)
        with self.assertRaisesRegex(ValueError, "another closure"):
            self.qualify()

    def test_failed_clean_install_check_is_rejected(self) -> None:
        value = json.loads(self.install.read_text())
        value["checks"]["projectVerified"] = False
        self.write(self.install, value)
        with self.assertRaisesRegex(ValueError, "checks are incomplete"):
            self.qualify()

    def test_workflow_requires_tag_ref_and_retains_receipt(self) -> None:
        body = WORKFLOW.read_text()
        self.assertIn("github.ref_type == 'tag'", body)
        self.assertIn("github.ref_name == inputs.release_tag", body)
        self.assertIn('test "$GITHUB_REF" = "refs/tags/$RELEASE_TAG"', body)
        self.assertIn("qualify-tagged-developer-preview.py", body)
        self.assertIn("developer-preview-qualification.json", body)
        self.assertIn("workflow_dispatch:", body)


if __name__ == "__main__":
    unittest.main()
