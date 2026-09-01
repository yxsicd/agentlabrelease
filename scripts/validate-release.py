#!/usr/bin/env python3
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "manifest.json").read_text())
provenance = json.loads((ROOT / "provenance.json").read_text())
index = json.loads((ROOT / "package-index.json").read_text())

assert manifest["schema"] == "agentlab.developer_release.v1"
assert manifest["version"] == index["latest"] == provenance["version"]
assert re.fullmatch(r"[0-9a-f]{40}", manifest["sourceRevision"])
assert manifest["sourceRevision"] == provenance["source"]["revision"]
assert (ROOT / manifest["entrypoint"]).is_file()

sums = ROOT / "SHA256SUMS"
if sums.exists():
    for line in sums.read_text().splitlines():
        digest, name = line.split("  ", 1)
        path = ROOT / name
        assert path.is_file(), name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name

print(json.dumps({"schema": "agentlab.release_validation.v1", "version": manifest["version"], "ok": True}))
