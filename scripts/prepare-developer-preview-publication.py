#!/usr/bin/env python3
"""Prepare a metadata-only GitHub developer preview publication bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import shutil
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")


class PublicationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PublicationError(message)


def load(path: pathlib.Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublicationError(f"cannot load {label}: {error}") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset(path: pathlib.Path) -> dict[str, Any]:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}


def validate(closure: dict[str, Any], closure_sha: str, qualification: dict[str, Any]) -> None:
    require(closure.get("schema") == "agentlab.release_closure.v1", "unsupported closure schema")
    require(closure.get("status") == "developer-preview-candidate", "closure is not a developer preview candidate")
    require(qualification.get("schema") == "agentlab.developer_preview_qualification.v1", "unsupported qualification schema")
    require(qualification.get("status") == "qualified-developer-preview-review-required", "developer preview is not qualified")
    require(qualification.get("releaseTag") == closure.get("releaseTag"), "qualification tag differs from closure")
    require(qualification.get("releaseGitSha") == (closure.get("sources") or {}).get("releaseGitSha"), "qualification source differs from closure")
    require((qualification.get("closure") or {}).get("sha256") == closure_sha, "qualification is bound to another closure")
    require(qualification.get("automaticPromotion") is False, "qualification may not auto-promote")
    require((closure.get("reuse") or {}).get("newBinaryBuildCount") == 0, "aggregate closure unexpectedly built binaries")
    require((closure.get("reuse") or {}).get("newBinaryUploadCount") == 0, "aggregate closure unexpectedly uploaded binaries")
    assets = closure.get("assets")
    require(isinstance(assets, list) and assets, "closure assets are required")
    require(len({row.get("id") for row in assets if isinstance(row, dict)}) == len(assets), "closure asset ids are invalid")
    for row in assets:
        require(isinstance(row, dict), "closure asset is invalid")
        require(isinstance(row.get("url"), str) and "/releases/download/" in row["url"], "component asset is not an immutable release reference")
        require(SHA256.fullmatch(str(row.get("sha256"))) is not None, "component asset digest is invalid")


def notes(closure: dict[str, Any], qualification: dict[str, Any]) -> str:
    scope = closure["developerPreviewScope"]
    return f"""# AgentLab {closure['releaseTag']} developer preview

This is a metadata-only aggregate of {closure['reuse']['selectedComponentCount']} independently
versioned components and {len(closure['assets'])} immutable payload/descriptor assets. No
unchanged component was rebuilt or uploaded for this release.

## Included

- Multi-repository semantic and program analysis
- Recursive difficulty feedback and reviewed calibrated case generation
- Linux x86/KVM Harmony emulator execution with ohosTest/Hypium
- Functional Oracle pass/fail separation and SmartPerf relative feedback
- Immutable closure installation on a fresh tagged GitHub Actions runner

## Qualification

- Closure SHA-256: `{qualification['closure']['sha256']}`
- Tag commit: `{qualification['tagGitSha']}`
- Release-method source: `{qualification['releaseGitSha']}`
- Qualification run: {qualification['github']['runUrl']}

## Boundaries

- Linux Harmony emulator execution: {scope['linuxHarmonyEmulatorExecution']}
- Relative performance feedback: {scope['relativePerformanceFeedback']}
- Absolute power and thermal authority: {scope['absolutePowerThermal']}
- Physical-device behavior and stable API compatibility are not qualified
- Automatic promotion remains disabled

Installers must verify `SHA256SUMS` and use `release-closure.json` as the
composition authority. Component payloads remain at their immutable component
Release URLs inside the closure.
"""


def prepare(closure_path: pathlib.Path, qualification_path: pathlib.Path, output: pathlib.Path) -> dict[str, Any]:
    require(not output.exists(), f"refusing to overwrite publication directory: {output}")
    closure = load(closure_path, "release closure")
    qualification = load(qualification_path, "developer preview qualification")
    closure_sha = sha256(closure_path)
    validate(closure, closure_sha, qualification)
    output.mkdir(parents=True)
    closure_target = output / "release-closure.json"
    qualification_target = output / "qualification.json"
    shutil.copyfile(closure_path, closure_target)
    shutil.copyfile(qualification_path, qualification_target)
    publication = {
        "schema": "agentlab.developer_preview_publication.v1",
        "status": "prepared-review-required",
        "releaseTag": closure["releaseTag"],
        "releaseVersion": closure["releaseVersion"],
        "tagGitSha": qualification["tagGitSha"],
        "releaseGitSha": qualification["releaseGitSha"],
        "closureSha256": closure_sha,
        "qualificationSha256": sha256(qualification_target),
        "selectedComponentCount": closure["reuse"]["selectedComponentCount"],
        "referencedAssetCount": len(closure["assets"]),
        "componentPayloadsUploaded": False,
        "newBinaryBuildCount": 0,
        "newBinaryUploadCount": 0,
        "aggregateAssets": [asset(closure_target), asset(qualification_target)],
        "automaticPromotion": False,
    }
    publication_path = output / "publication.json"
    publication_path.write_text(json.dumps(publication, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    notes_path = output / "release-notes.md"
    notes_path.write_text(notes(closure, qualification), encoding="utf-8")
    sums = [closure_target, qualification_target, publication_path]
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="utf-8"
    )
    return publication


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closure", type=pathlib.Path, required=True)
    parser.add_argument("--qualification", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        publication = prepare(args.closure.resolve(), args.qualification.resolve(), args.output.resolve())
    except PublicationError as error:
        raise SystemExit(f"developer preview publication invalid: {error}") from error
    print(json.dumps({"releaseTag": publication["releaseTag"], "status": publication["status"], "componentPayloadsUploaded": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
