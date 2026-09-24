#!/usr/bin/env python3
"""Verify that a Docker save archive, descriptor, and lock identity agree."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import tarfile
from typing import BinaryIO


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_file(path: pathlib.Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def hash_member(handle: BinaryIO, capture: bool = False) -> tuple[str, bytes | None]:
    digest = hashlib.sha256()
    content = bytearray() if capture else None
    while chunk := handle.read(1024 * 1024):
        digest.update(chunk)
        if content is not None:
            content.extend(chunk)
    return digest.hexdigest(), bytes(content) if content is not None else None


def inspect_tar(
    stream: BinaryIO,
) -> tuple[list[dict[str, object]], dict[str, str], dict[str, bytes]]:
    manifests: list[dict[str, object]] | None = None
    member_digests: dict[str, str] = {}
    metadata_members: dict[str, bytes] = {}
    captured_bytes = 0
    with tarfile.open(fileobj=stream, mode="r|") as archive:
        for member in archive:
            require(not member.name.startswith("/"), "archive contains an absolute path")
            require(".." not in pathlib.PurePosixPath(member.name).parts,
                    "archive contains path traversal")
            if not member.isfile():
                continue
            handle = archive.extractfile(member)
            require(handle is not None, f"cannot read archive member: {member.name}")
            capture = (
                member.name == "manifest.json"
                or member.name.endswith(".json")
                or member.name.startswith("blobs/sha256/")
            ) and member.size <= 4 * 1024 * 1024
            if capture:
                require(captured_bytes + member.size <= 64 * 1024 * 1024,
                        "archive metadata capture exceeds safety limit")
            digest, content = hash_member(handle, capture)
            member_digests[member.name] = digest
            if content is not None:
                metadata_members[member.name] = content
                captured_bytes += len(content)
            if member.name == "manifest.json" and content is not None:
                parsed = json.loads(content)
                require(isinstance(parsed, list), "manifest.json must be an array")
                manifests = parsed
    require(manifests is not None, "archive does not contain manifest.json")
    return manifests, member_digests, metadata_members


def inspect_archive(
    path: pathlib.Path,
) -> tuple[list[dict[str, object]], dict[str, str], dict[str, bytes]]:
    if path.name.endswith(".zst"):
        process = subprocess.Popen(
            ["zstd", "-dc", "--long=31", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        require(process.stdout is not None and process.stderr is not None,
                "cannot open zstd stream")
        try:
            result = inspect_tar(process.stdout)
        finally:
            process.stdout.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace")
        return_code = process.wait()
        require(return_code == 0, f"zstd decode failed: {stderr.strip()}")
        return result
    with path.open("rb") as stream:
        return inspect_tar(stream)


def verify(
    archive: pathlib.Path,
    expected_archive_sha256: str,
    expected_image_id: str,
    expected_reference: str,
    descriptor_path: pathlib.Path | None,
) -> dict[str, object]:
    require(archive.is_file(), f"archive not found: {archive}")
    archive_bytes, archive_sha256 = sha256_file(archive)
    require(archive_sha256 == expected_archive_sha256,
            "archive SHA-256 does not match the expected identity")

    manifests, member_digests, metadata_members = inspect_archive(archive)
    matches = [
        row for row in manifests
        if isinstance(row, dict)
        and expected_reference in row.get("RepoTags", [])
    ]
    require(len(matches) == 1,
            "archive must contain exactly one manifest entry for the expected reference")
    config_path = matches[0].get("Config")
    require(isinstance(config_path, str) and config_path,
            "matching manifest entry does not declare Config")
    require(config_path in member_digests,
            "manifest Config member is missing from the archive")
    archive_manifest_digest = "sha256:" + member_digests[config_path]
    actual_image_id = archive_manifest_digest
    actual_config_path = config_path
    config_content = metadata_members.get(config_path)
    if config_content is not None:
        candidate = json.loads(config_content)
        nested = candidate.get("config") if isinstance(candidate, dict) else None
        nested_digest = nested.get("digest") if isinstance(nested, dict) else None
        if isinstance(nested_digest, str) and nested_digest.startswith("sha256:"):
            nested_hex = nested_digest.removeprefix("sha256:")
            require(len(nested_hex) == 64 and all(c in "0123456789abcdef" for c in nested_hex),
                    "OCI manifest config digest is invalid")
            actual_config_path = "blobs/sha256/" + nested_hex
            require(member_digests.get(actual_config_path) == nested_hex,
                    "OCI config blob is missing or does not match its digest")
            actual_image_id = nested_digest
    require(actual_image_id == expected_image_id,
            f"image ID mismatch: expected {expected_image_id}, got {actual_image_id}")

    descriptor_sha256 = None
    if descriptor_path is not None:
        require(descriptor_path.is_file(), f"descriptor not found: {descriptor_path}")
        descriptor_bytes = descriptor_path.read_bytes()
        descriptor_sha256 = hashlib.sha256(descriptor_bytes).hexdigest()
        descriptor = json.loads(descriptor_bytes)
        require(descriptor.get("schema") == "agentlab.docker_image_descriptor.v1",
                "unsupported descriptor schema")
        declared_archive = descriptor.get("archive", {})
        declared_image = descriptor.get("image", {})
        require(declared_archive.get("bytes") == archive_bytes,
                "descriptor archive byte count mismatch")
        require(declared_archive.get("sha256") == archive_sha256,
                "descriptor archive SHA-256 mismatch")
        require(declared_archive.get("filename") == archive.name,
                "descriptor archive filename mismatch")
        require(declared_image.get("imageId") == actual_image_id,
                "descriptor image ID mismatch")
        require(declared_image.get("reference") == expected_reference,
                "descriptor image reference mismatch")

    return {
        "schema": "agentlab.docker_image_archive_verification.v1",
        "status": "passed",
        "archive": {
            "path": str(archive),
            "bytes": archive_bytes,
            "sha256": archive_sha256,
        },
        "image": {
            "reference": expected_reference,
            "imageId": actual_image_id,
            "manifestDigest": archive_manifest_digest,
            "manifestMember": config_path,
            "configMember": actual_config_path,
        },
        "descriptorSha256": descriptor_sha256,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=pathlib.Path)
    parser.add_argument("--expected-archive-sha256", required=True)
    parser.add_argument("--expected-image-id", required=True)
    parser.add_argument("--expected-reference", required=True)
    parser.add_argument("--descriptor", type=pathlib.Path)
    parser.add_argument("--receipt", type=pathlib.Path)
    args = parser.parse_args()
    try:
        receipt = verify(
            args.archive,
            args.expected_archive_sha256,
            args.expected_image_id,
            args.expected_reference,
            args.descriptor,
        )
        rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        if args.receipt:
            if args.receipt.exists():
                require(args.receipt.read_text(encoding="utf-8") == rendered,
                        f"refusing to replace different receipt: {args.receipt}")
            else:
                args.receipt.write_text(rendered, encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError, tarfile.TarError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(rendered, end="")


if __name__ == "__main__":
    main()
