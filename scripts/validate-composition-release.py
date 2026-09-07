#!/usr/bin/env python3
"""Validate reference-only publications; optionally verify GitHub and smoke tools."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO = "yxsicd/agentlabrelease"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def asset_location(url):
    parsed = urllib.parse.urlsplit(url)
    prefix = f"/{REPO}/releases/download/"
    require(parsed.scheme == "https" and parsed.netloc == "github.com"
            and parsed.path.startswith(prefix) and not parsed.query and not parsed.fragment,
            "asset must use a canonical GitHub release URL")
    parts = parsed.path[len(prefix):].split("/")
    require(len(parts) == 2 and all(parts), "invalid asset URL")
    return tuple(parts)


def validate(publication, lock, lock_bytes):
    require(publication["schema"] == "agentlab.reference_publication.v1", "publication schema")
    require(publication["environmentLockSha256"] == sha(lock_bytes), "lock digest drift")
    require(lock["schema"] == "agentlab.environment_lock.v3", "lock schema")
    require(publication["status"] in {"candidate", "qualified"}, "publication status")
    gates = publication["gates"]
    require(gates and all(v in {"passed", "failed", "not_run"} for v in gates.values()), "gate status")
    if publication["status"] == "qualified":
        require(all(v == "passed" for v in gates.values()), "qualified publication has unpassed gates")
    assets = publication["assets"]
    urls = [a["url"] for a in assets]
    require(len(urls) == len(set(urls)), "duplicate reference")
    by_url = {a["url"]: a for a in assets}
    for asset in assets:
        tag, _ = asset_location(asset["url"])
        require(tag != publication["tag"], "composition must not host component payloads")
        require(re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]) is not None, "invalid digest")
        require(type(asset["bytes"]) is int and asset["bytes"] > 0, "invalid size")
    for component in lock["images"] + lock["components"]:
        for field in ("artifact", "descriptor"):
            require(component[field] in by_url, "missing component reference")
        require(by_url[component["artifact"]]["sha256"] == component["archiveSha256"], "archive digest drift")
    graph = lock["componentGraph"]
    require(graph["schema"] == "agentlab.component_graph.v1", "graph schema")
    providers = {}
    for node in graph["nodes"]:
        for contract, version in node.get("provides", {}).items():
            require(type(version) is int and version > 0, "invalid contract generation")
            key = (node["platform"], contract)
            require(key not in providers, "duplicate contract provider")
            providers[key] = version
    actual = {}
    for (platform, contract), version in providers.items():
        actual.setdefault(platform, {})[contract] = version
    require(graph["resolvedContracts"] == actual, "resolved contract drift")
    for node in graph["nodes"]:
        for contract, bounds in node.get("requires", {}).items():
            version = providers.get((node["platform"], contract), -1)
            require(bounds["min"] <= version < bounds["maxExclusive"], "unsatisfied contract")
    return assets


def remote_assets(assets):
    cache = {}
    for asset in assets:
        tag, name = asset_location(asset["url"])
        if tag not in cache:
            headers = {"Accept": "application/vnd.github+json", "User-Agent": "agentlab-release-validation"}
            if os.environ.get("GITHUB_TOKEN"):
                headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
            request = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/tags/{tag}", headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                release = json.load(response)
            require(not release["draft"], "component release is a draft")
            cache[tag] = {a["name"]: a for a in release["assets"]}
        observed = cache[tag].get(name)
        require(observed is not None, "missing public asset: " + name)
        require(observed["size"] == asset["bytes"] and observed["digest"] == "sha256:" + asset["sha256"], "public asset identity drift: " + name)
        require(observed["browser_download_url"] == asset["url"], "download URL drift")


def smoke(publication, assets):
    by_url = {a["url"]: a for a in assets}
    with tempfile.TemporaryDirectory() as directory:
        paths = []
        for key in ("control", "pack"):
            asset = by_url[publication["smoke"][key]]
            require(asset["bytes"] <= 64 * 1024 * 1024, "smoke download exceeds budget")
            # Browser downloads are public. Never forward the API token to redirects.
            with urllib.request.urlopen(asset["url"], timeout=120) as response:
                data = response.read(asset["bytes"] + 1)
            require(len(data) == asset["bytes"] and sha(data) == asset["sha256"], "download digest mismatch")
            path = pathlib.Path(directory) / key
            path.write_bytes(data)
            paths.append(path)
        paths[0].chmod(0o700)
        subprocess.run([str(paths[0]), "pack", "verify", str(paths[1])], check=True, timeout=60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    count = 0
    for path in sorted((ROOT / "release/candidates").glob("*/publication.json")):
        publication = json.loads(path.read_text())
        lock_bytes = (path.parent / "environment-lock.json").read_bytes()
        assets = validate(publication, json.loads(lock_bytes), lock_bytes)
        if args.remote or args.smoke:
            remote_assets(assets)
        if args.smoke:
            smoke(publication, assets)
        count += 1
    require(count > 0, "no publication manifests found")
    print(json.dumps({"ok": True, "publications": count, "remote": args.remote, "smoke": args.smoke}))


if __name__ == "__main__":
    main()
