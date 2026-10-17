import ast
import copy
import hashlib
import json
import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
nodes = ast.parse((ROOT / "scripts/validate-release.py").read_text())
names = {"validate_published_manifest", "validate_native_render_integration"}
scope = dict(hashlib=hashlib, json=json, pathlib=pathlib, re=re)
exec(compile(ast.Module(body=[n for n in nodes.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[]), "published_manifest_functions", "exec"), scope)
check = scope["validate_published_manifest"]
integration_check = scope["validate_native_render_integration"]

class PublishedManifestBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.control = json.loads((ROOT / "release/components/control-60c81241-linux-x64.json").read_text())
        self.assets = json.loads((ROOT / "docs/evidence/control-60c81241-publication-20261017.json").read_text())["assets"]
        self.producer = json.loads((ROOT / "release/components/native-render-6a69f84123c9.json").read_text())
        self.producer_assets = json.loads((ROOT / "docs/evidence/native-render-6a69f84123c9-publication-20261017.json").read_text())["selectedAssets"]
        for c in (self.control, self.producer):
            p = self.root / c["publishedManifest"]["path"]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes((ROOT / c["publishedManifest"]["path"]).read_bytes())

    def rewritten_public_bytes(self, component, assets, change):
        ref = component["publishedManifest"]
        p = self.root / ref["path"]
        raw = json.loads(p.read_bytes())
        change(raw)
        b = (json.dumps(raw) + "\n").encode()
        p.write_bytes(b)
        ref.update(bytes=len(b), sha256=hashlib.sha256(b).hexdigest())
        found = next(a for a in assets if a["url"] == ref["artifact"])
        found.update(bytes=len(b), sha256=ref["sha256"])

    def test_exact_published_control_and_producer_manifests(self):
        check(self.control, self.assets, self.root)
        check(self.producer, self.producer_assets, self.root)

    def test_rehashed_wrong_source_is_still_rejected(self):
        self.rewritten_public_bytes(self.control, self.assets, lambda d: d.update(sourceRevision="f" * 40))
        with self.assertRaises(AssertionError):
            check(self.control, self.assets, self.root)

    def test_rehashed_wrong_binary_is_still_rejected(self):
        self.rewritten_public_bytes(self.control, self.assets, lambda d: d["assets"][0].update(sha256="f" * 64))
        with self.assertRaises(AssertionError):
            check(self.control, self.assets, self.root)

    def test_manifest_url_or_receipt_digest_cannot_substitute(self):
        for field in ("artifact", "sha256"):
            c, assets = copy.deepcopy(self.control), copy.deepcopy(self.assets)
            if field == "artifact":
                old = c["publishedManifest"]["artifact"]
                c["publishedManifest"]["artifact"] = "https://example.invalid/manifest.json"
                next(a for a in assets if a["url"] == old)["url"] = c["publishedManifest"]["artifact"]
            else:
                next(a for a in assets if a["url"] == c["publishedManifest"]["artifact"])["sha256"] = "f" * 64
            with self.subTest(field=field), self.assertRaises(AssertionError):
                check(c, assets, self.root)

    def test_wrapper_path_escape_and_symlink_are_rejected(self):
        c = copy.deepcopy(self.control)
        c["publishedManifest"]["path"] = "../outside.json"
        with self.assertRaises(AssertionError):
            check(c, self.assets, self.root)
        p = self.root / self.control["publishedManifest"]["path"]
        p.unlink()
        p.symlink_to(ROOT / self.control["publishedManifest"]["path"])
        with self.assertRaises(AssertionError):
            check(self.control, self.assets, self.root)

    def test_producer_manifest_cannot_grant_owner(self):
        self.rewritten_public_bytes(self.producer, self.producer_assets, lambda d: d.update(applicationOwnerGrant=True))
        with self.assertRaises(AssertionError):
            check(self.producer, self.producer_assets, self.root)

    def test_real_render_receipt_stays_source_bound_and_not_permission(self):
        d = json.loads((ROOT / "docs/evidence/native-render-6a69f84123c9-original-render-20261017.json").read_text())
        integration_check(self.producer, d)
        for field, value in [("sourceRevision", "f" * 40), ("applicationOwnerGrant", True), ("fullInstanceQualified", True)]:
            changed = copy.deepcopy(d)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                integration_check(self.producer, changed)

if __name__ == "__main__":
    unittest.main()
