from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/prepare-developer-preview-publication.py"
CLOSURE = ROOT / "release/closures/v0.1.0-alpha.12.json"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


MODULE = load_module("prepare_developer_preview_publication", SCRIPT)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DeveloperPreviewPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        closure = json.loads(CLOSURE.read_text())
        self.qualification = self.root / "qualification.json"
        self.qualification.write_text(
            json.dumps(
                {
                    "schema": "agentlab.developer_preview_qualification.v1",
                    "status": "qualified-developer-preview-review-required",
                    "releaseTag": closure["releaseTag"],
                    "tagGitSha": "a" * 40,
                    "releaseGitSha": closure["sources"]["releaseGitSha"],
                    "closure": {"sha256": digest(CLOSURE)},
                    "github": {
                        "runUrl": "https://github.com/yxsicd/agentlabrelease/actions/runs/424242"
                    },
                    "automaticPromotion": False,
                },
                sort_keys=True,
            )
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_bundle_contains_only_small_aggregate_metadata(self) -> None:
        output = self.root / "bundle"
        publication = MODULE.prepare(CLOSURE, self.qualification, output)
        self.assertEqual(
            set(path.name for path in output.iterdir()),
            {
                "release-closure.json",
                "qualification.json",
                "publication.json",
                "release-notes.md",
                "SHA256SUMS",
            },
        )
        self.assertFalse(publication["componentPayloadsUploaded"])
        self.assertEqual(publication["newBinaryBuildCount"], 0)
        self.assertEqual(publication["newBinaryUploadCount"], 0)
        self.assertEqual(publication["selectedComponentCount"], 14)
        self.assertEqual(publication["referencedAssetCount"], 22)
        self.assertEqual(
            {row["name"] for row in publication["aggregateAssets"]},
            {"release-closure.json", "qualification.json"},
        )
        for line in (output / "SHA256SUMS").read_text().splitlines():
            expected, name = line.split("  ", 1)
            self.assertEqual(digest(output / name), expected)
        notes = (output / "release-notes.md").read_text()
        self.assertIn("No\nunchanged component was rebuilt or uploaded", notes)
        self.assertIn("Absolute power and thermal authority: not-qualified", notes)

    def test_qualification_for_another_closure_is_rejected(self) -> None:
        value = json.loads(self.qualification.read_text())
        value["closure"]["sha256"] = "0" * 64
        self.qualification.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "another closure"):
            MODULE.prepare(CLOSURE, self.qualification, self.root / "bundle")

    def test_unqualified_receipt_is_rejected(self) -> None:
        value = json.loads(self.qualification.read_text())
        value["status"] = "pending"
        self.qualification.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "not qualified"):
            MODULE.prepare(CLOSURE, self.qualification, self.root / "bundle")

    def test_existing_output_is_never_overwritten(self) -> None:
        output = self.root / "bundle"
        output.mkdir()
        marker = output / "keep"
        marker.write_text("retained")
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            MODULE.prepare(CLOSURE, self.qualification, output)
        self.assertEqual(marker.read_text(), "retained")


if __name__ == "__main__":
    unittest.main()
