from __future__ import annotations

import hashlib
import io
import json
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/verify-docker-image-archive.py"
FAST_INSTALL = ROOT / "scripts/ci-fast-subject-install.sh"


class DockerImageArchiveVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.reference = "example/runtime:test"
        self.config = b'{"architecture":"amd64","rootfs":{"diff_ids":[]}}\n'
        self.image_id = "sha256:" + hashlib.sha256(self.config).hexdigest()
        self.archive = self.root / "runtime.docker.tar"
        manifest = json.dumps(
            [{"Config": "config.json", "RepoTags": [self.reference], "Layers": ["layer.tar"]}]
        ).encode()
        with tarfile.open(self.archive, "w") as output:
            for name, content in (
                ("config.json", self.config),
                ("layer.tar", b"layer bytes"),
                ("manifest.json", manifest),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(content)
                output.addfile(info, io.BytesIO(content))
        self.archive_sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.descriptor = self.root / "runtime.docker.tar.json"
        self.descriptor.write_text(
            json.dumps(
                {
                    "schema": "agentlab.docker_image_descriptor.v1",
                    "archive": {
                        "filename": self.archive.name,
                        "bytes": self.archive.stat().st_size,
                        "sha256": self.archive_sha,
                    },
                    "image": {
                        "imageId": self.image_id,
                        "reference": self.reference,
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_verifier(self, image_id: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--archive",
                str(self.archive),
                "--expected-archive-sha256",
                self.archive_sha,
                "--expected-image-id",
                image_id or self.image_id,
                "--expected-reference",
                self.reference,
                "--descriptor",
                str(self.descriptor),
            ],
            text=True,
            capture_output=True,
        )

    def test_matching_archive_descriptor_and_lock_identity_pass(self) -> None:
        completed = self.run_verifier()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads(completed.stdout)
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["image"]["imageId"], self.image_id)
        self.assertEqual(receipt["image"]["configMember"], "config.json")

    def test_wrong_lock_image_id_fails_closed(self) -> None:
        completed = self.run_verifier("sha256:" + "0" * 64)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("image ID mismatch", completed.stderr)

    def test_wrong_descriptor_image_id_fails_closed(self) -> None:
        value = json.loads(self.descriptor.read_text())
        value["image"]["imageId"] = "sha256:" + "f" * 64
        self.descriptor.write_text(json.dumps(value), encoding="utf-8")
        completed = self.run_verifier()
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("descriptor image ID mismatch", completed.stderr)

    def test_archive_path_traversal_fails_closed(self) -> None:
        with tarfile.open(self.archive, "w") as output:
            info = tarfile.TarInfo("../manifest.json")
            content = b"[]"
            info.size = len(content)
            output.addfile(info, io.BytesIO(content))
        self.archive_sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        completed = self.run_verifier()
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("path traversal", completed.stderr)

    def test_oci_manifest_indirection_uses_nested_config_digest_as_image_id(self) -> None:
        config_digest = hashlib.sha256(self.config).hexdigest()
        image_manifest = json.dumps(
            {
                "schemaVersion": 2,
                "config": {
                    "mediaType": "application/vnd.oci.image.config.v1+json",
                    "digest": "sha256:" + config_digest,
                    "size": len(self.config),
                },
                "layers": [],
            },
            separators=(",", ":"),
        ).encode()
        manifest_digest = hashlib.sha256(image_manifest).hexdigest()
        docker_manifest = json.dumps(
            [
                {
                    "Config": "blobs/sha256/" + manifest_digest,
                    "RepoTags": [self.reference],
                    "Layers": [],
                }
            ]
        ).encode()
        with tarfile.open(self.archive, "w") as output:
            for name, content in (
                ("blobs/sha256/" + config_digest, self.config),
                ("blobs/sha256/" + manifest_digest, image_manifest),
                ("manifest.json", docker_manifest),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(content)
                output.addfile(info, io.BytesIO(content))
        self.archive_sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        value = json.loads(self.descriptor.read_text())
        value["archive"]["bytes"] = self.archive.stat().st_size
        value["archive"]["sha256"] = self.archive_sha
        self.descriptor.write_text(json.dumps(value), encoding="utf-8")
        completed = self.run_verifier()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        receipt = json.loads(completed.stdout)
        self.assertEqual(receipt["image"]["imageId"], self.image_id)
        self.assertEqual(receipt["image"]["manifestDigest"], "sha256:" + manifest_digest)
        self.assertEqual(
            receipt["image"]["configMember"], "blobs/sha256/" + config_digest
        )

    def test_fast_install_verifies_archive_before_docker_load(self) -> None:
        source = FAST_INSTALL.read_text(encoding="utf-8")
        verification = source.index("verify-docker-image-archive.py")
        docker_load = source.index("docker load")
        self.assertLess(verification, docker_load)
        self.assertIn('--expected-image-id "${values[2]}"', source)
        self.assertIn('--expected-reference "${values[3]}"', source)


if __name__ == "__main__":
    unittest.main()
