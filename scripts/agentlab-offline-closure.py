#!/usr/bin/env python3
"""Resolve, fetch, verify, report, and stage AgentLab offline closure assets.

This is a release-side compatibility CLI until the same commands are embedded
inside agentlabctl. It is deliberately credential-free: it only handles public
immutable assets and never stores SafeGit/SessionFS/MCPGit authorization.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

DEFAULT_CLOSURE_URL = (
    "https://github.com/yxsicd/agentlabrelease/releases/download/aloffline/"
    "agentlab-offline-linux-x64.json"
)
DEFAULT_RESOLVER_URL = (
    "https://github.com/yxsicd/agentlabrelease/releases/download/aloffline/"
    "agentlab-offline-closure.py"
)
BASE_RELEASE_URL = "https://github.com/yxsicd/agentlabrelease/releases/download"
RESOLVED_SCHEMA = "agentlab.offline_closure_resolved.v1"
FETCH_REPORT_SCHEMA = "agentlab.offline_fetch_report.v1"


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_url(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "agentlab-offline-closure/1"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def validate_blob(blob: bytes, meta: dict, label: str) -> None:
    if len(blob) != meta["bytes"]:
        raise SystemExit(f"{label}: byte count mismatch: got {len(blob)}, expected {meta['bytes']}")
    got = hashlib.sha256(blob).hexdigest()
    if got != meta["sha256"]:
        raise SystemExit(f"{label}: sha256 mismatch: got {got}, expected {meta['sha256']}")


def load_json_source(value: str | pathlib.Path) -> tuple[dict, bytes]:
    text = str(value)
    if urllib.parse.urlsplit(text).scheme in {"http", "https"}:
        blob = read_url(text)
        return json.loads(blob), blob
    path = pathlib.Path(text)
    blob = path.read_bytes()
    return json.loads(blob), blob


def resolve_closure(source: str | pathlib.Path) -> dict:
    closure, closure_blob = load_json_source(source)
    if closure.get("schema") != "agentlab.offline_closure.v1":
        raise SystemExit("unsupported closure schema")
    assets = list(closure["directAssets"])
    manifests = []
    for ref in closure["manifestRefs"]:
        meta = ref["manifest"]
        blob = read_url(meta["url"])
        validate_blob(blob, meta, ref["group"] + " manifest")
        manifest = json.loads(blob)
        manifests.append({"group": ref["group"], **meta})
        if ref["adapter"] == "single-artifact-v1":
            rows = [manifest]
        elif ref["adapter"] == "assets-array-v1":
            rows = manifest["assets"]
        else:
            raise SystemExit(f"unsupported manifest adapter: {ref['adapter']}")
        for row in rows:
            assets.append(
                {
                    "group": ref["group"],
                    "filename": row["filename"],
                    "url": f"{BASE_RELEASE_URL}/{ref['releaseTag']}/{row['filename']}",
                    "bytes": row["bytes"],
                    "sha256": row["sha256"],
                }
            )
    seen = set()
    for asset in assets:
        key = (asset["url"], asset["sha256"])
        if key in seen:
            raise SystemExit("duplicate resolved asset: " + asset["filename"])
        seen.add(key)
    return {
        "schema": RESOLVED_SCHEMA,
        "platform": closure["platform"],
        "sourceClosureSha256": hashlib.sha256(closure_blob).hexdigest(),
        "assets": assets,
        "manifests": manifests,
        "totalBytes": sum(item["bytes"] for item in assets),
        "credentialsIncluded": False,
    }


def asset_path(root: pathlib.Path, asset: dict) -> pathlib.Path:
    group = asset["group"]
    filename = asset["filename"]
    if "/" in group or ".." in pathlib.PurePosixPath(group).parts:
        raise SystemExit("invalid asset group: " + group)
    if pathlib.PurePosixPath(filename).name != filename:
        raise SystemExit("invalid asset filename: " + filename)
    return root / "assets" / group / filename


def asset_status(root: pathlib.Path, asset: dict, check_hash: bool) -> dict:
    path = asset_path(root, asset)
    partial = pathlib.Path(str(path) + ".part")
    result = {
        "group": asset["group"],
        "filename": asset["filename"],
        "expectedBytes": asset["bytes"],
        "path": str(path),
    }
    if path.is_file():
        result["bytes"] = path.stat().st_size
        if result["bytes"] != asset["bytes"]:
            result["status"] = "size_mismatch"
            return result
        if check_hash:
            got = sha256_file(path)
            result["sha256"] = got
            result["status"] = "ok" if got == asset["sha256"] else "sha_mismatch"
        else:
            result["status"] = "present"
        return result
    if partial.is_file():
        result["bytes"] = partial.stat().st_size
        result["status"] = "partial"
        return result
    result["bytes"] = 0
    result["status"] = "missing"
    return result


def write_meta(root: pathlib.Path, closure: dict, resolved: dict, closure_blob: bytes | None = None) -> None:
    meta = root / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    if closure_blob is not None:
        (meta / "closure.json").write_bytes(closure_blob)
    (meta / "resolved.json").write_text(json.dumps(resolved, indent=2, sort_keys=True) + "\n")
    with (meta / "assets.tsv").open("w", encoding="utf-8") as handle:
        for asset in resolved["assets"]:
            handle.write(
                "\t".join(
                    [
                        asset["group"],
                        asset["filename"],
                        asset["url"],
                        str(asset["bytes"]),
                        asset["sha256"],
                    ]
                )
                + "\n"
            )


def curl_fetch(asset: dict, output: pathlib.Path) -> tuple[str, int]:
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = pathlib.Path(str(output) + ".part")
    command = [
        "curl",
        "-fL",
        "--retry",
        "5",
        "--retry-all-errors",
        "--connect-timeout",
        "20",
        "-C",
        "-",
        "-o",
        str(partial),
        asset["url"],
    ]
    proc = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if proc.returncode:
        return f"curl={proc.returncode}", partial.stat().st_size if partial.exists() else 0
    if partial.stat().st_size != asset["bytes"]:
        return "size_mismatch", partial.stat().st_size
    got = sha256_file(partial)
    if got != asset["sha256"]:
        return "sha_mismatch", partial.stat().st_size
    partial.replace(output)
    return "ok", asset["bytes"]


def fetch_assets(root: pathlib.Path, resolved: dict, jobs: int) -> dict:
    start = time.time()
    results = []

    def one(asset: dict) -> dict:
        output = asset_path(root, asset)
        status = asset_status(root, asset, check_hash=True)
        if status["status"] == "ok":
            return {**status, "action": "reused"}
        state, bytes_done = curl_fetch(asset, output)
        return {
            "group": asset["group"],
            "filename": asset["filename"],
            "status": state,
            "action": "downloaded" if state == "ok" else "failed",
            "bytes": bytes_done,
            "expectedBytes": asset["bytes"],
            "path": str(output),
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = [executor.submit(one, asset) for asset in resolved["assets"]]
        for future in concurrent.futures.as_completed(futures):
            item = future.result()
            results.append(item)
            print(f"{item['group']}\t{item['filename']}\t{item['status']}\t{item.get('bytes', 0)}", flush=True)
    bad = [item for item in results if item["status"] != "ok"]
    report = {
        "schema": FETCH_REPORT_SCHEMA,
        "ok": not bad,
        "assetCount": len(results),
        "badCount": len(bad),
        "totalBytes": resolved["totalBytes"],
        "onDiskBytes": sum(
            asset_path(root, asset).stat().st_size
            for asset in resolved["assets"]
            if asset_path(root, asset).is_file()
        ),
        "elapsedSeconds": round(time.time() - start, 3),
        "results": sorted(results, key=lambda row: (row["group"], row["filename"])),
    }
    (root / "meta").mkdir(parents=True, exist_ok=True)
    (root / "meta" / "fetch-report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if bad:
        raise SystemExit(1)
    return report


def verify_assets(root: pathlib.Path, resolved: dict, check_hash: bool = True, emit: bool = True) -> dict:
    results = [asset_status(root, asset, check_hash=check_hash) for asset in resolved["assets"]]
    bad = [item for item in results if item["status"] not in {"ok", "present"}]
    by_group = {}
    for item in results:
        entry = by_group.setdefault(item["group"], {"assetCount": 0, "bytes": 0, "badCount": 0})
        entry["assetCount"] += 1
        entry["bytes"] += item.get("bytes") or 0
        entry["badCount"] += 0 if item["status"] in {"ok", "present"} else 1
    report = {
        "schema": "agentlab.offline_verify_report.v1",
        "ok": not bad,
        "assetCount": len(results),
        "badCount": len(bad),
        "totalBytes": resolved["totalBytes"],
        "onDiskBytes": sum(item.get("bytes") or 0 for item in results if item["status"] in {"ok", "present"}),
        "groups": by_group,
        "bad": bad,
    }
    if emit:
        print(json.dumps({k: report[k] for k in ("schema", "ok", "assetCount", "badCount", "totalBytes", "onDiskBytes")}, sort_keys=True))
    if bad:
        raise SystemExit(1)
    return report


def report(root: pathlib.Path, resolved: dict) -> dict:
    verify = verify_assets(root, resolved, check_hash=False, emit=False)
    files = []
    for asset in resolved["assets"]:
        path = asset_path(root, asset)
        files.append({"group": asset["group"], "filename": asset["filename"], "bytes": path.stat().st_size if path.exists() else 0})
    result = {
        "schema": "agentlab.offline_report.v1",
        "platform": resolved["platform"],
        "credentialsIncluded": resolved.get("credentialsIncluded", False),
        "verify": verify,
        "files": sorted(files, key=lambda row: (row["group"], row["filename"])),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


def load_resolved(root: pathlib.Path, lock: pathlib.Path | None) -> dict:
    path = lock or (root / "meta" / "resolved.json")
    return json.loads(path.read_text())


def stage_quickstart(root: pathlib.Path, destination: pathlib.Path, copy: bool) -> dict:
    resolved = load_resolved(root, None)
    required = {
        "agentlab-bootstrap.sh",
        "agentlabctl-e611c39bab87-linux-x64",
        "agentlab-harness-quickstart.sh",
        "agentlab-environment-kit-v0.1.0-alpha.9.tar.zst",
        "agentlab-ts-probe-v0.1.0-alpha.9.tar.zst",
        "agentlab-aldev-environment-lock.json",
        "harmony-linux-x64-6.1.1.300.tar.zst",
    }
    by_name = {asset["filename"]: asset for asset in resolved["assets"]}
    downloads = destination / "downloads"
    bin_dir = destination / "bin"
    downloads.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)
    linked = []
    for name in sorted(required):
        asset = by_name[name]
        source = asset_path(root, asset)
        target = (bin_dir if name.startswith("agentlabctl-") else downloads) / name
        if target.exists() or target.is_symlink():
            target.unlink()
        if copy:
            shutil.copy2(source, target)
        else:
            os.symlink(source, target)
        if name.startswith("agentlabctl-"):
            alias = bin_dir / "agentlabctl"
            if alias.exists() or alias.is_symlink():
                alias.unlink()
            os.symlink(target.name if copy else target, alias)
            target.chmod(0o755)
        linked.append({"source": str(source), "target": str(target), "mode": "copy" if copy else "symlink"})
    result = {"schema": "agentlab.offline_quickstart_stage.v1", "root": str(destination), "items": linked}
    (destination / "offline-stage.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": True, "root": str(destination), "items": len(linked)}, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(prog="agentlab-offline-closure")
    sub = parser.add_subparsers(dest="cmd", required=True)
    resolve_p = sub.add_parser("resolve")
    resolve_p.add_argument("--closure", default=DEFAULT_CLOSURE_URL)
    resolve_p.add_argument("--out", type=pathlib.Path, required=True)
    fetch_p = sub.add_parser("fetch")
    fetch_p.add_argument("--closure", default=DEFAULT_CLOSURE_URL)
    fetch_p.add_argument("--root", type=pathlib.Path, required=True)
    fetch_p.add_argument("--jobs", type=int, default=6)
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("--root", type=pathlib.Path, required=True)
    verify_p.add_argument("--lock", type=pathlib.Path)
    report_p = sub.add_parser("report")
    report_p.add_argument("--root", type=pathlib.Path, required=True)
    stage_p = sub.add_parser("stage-quickstart")
    stage_p.add_argument("--root", type=pathlib.Path, required=True)
    stage_p.add_argument("--destination", type=pathlib.Path, required=True)
    stage_p.add_argument("--copy", action="store_true")
    args = parser.parse_args()

    if args.cmd == "resolve":
        resolved = resolve_closure(args.closure)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(resolved, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"ok": True, "assetCount": len(resolved["assets"]), "totalBytes": resolved["totalBytes"]}, sort_keys=True))
    elif args.cmd == "fetch":
        closure, blob = load_json_source(args.closure)
        resolved = resolve_closure(args.closure)
        write_meta(args.root, closure, resolved, blob if not pathlib.Path(str(args.closure)).exists() else None)
        result = fetch_assets(args.root, resolved, jobs=max(1, min(args.jobs, 16)))
        print(json.dumps({"ok": result["ok"], "assetCount": result["assetCount"], "totalBytes": result["totalBytes"], "onDiskBytes": result["onDiskBytes"], "elapsedSeconds": result["elapsedSeconds"]}, sort_keys=True))
    elif args.cmd == "verify":
        verify_assets(args.root, load_resolved(args.root, args.lock), check_hash=True)
    elif args.cmd == "report":
        report(args.root, load_resolved(args.root, None))
    elif args.cmd == "stage-quickstart":
        stage_quickstart(args.root, args.destination, args.copy)


if __name__ == "__main__":
    main()
