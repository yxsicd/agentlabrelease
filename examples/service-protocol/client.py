#!/usr/bin/env python3
"""Credential-free explicit discovery and curl-only business acceptance."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import yaml

class ContractError(Exception):
    pass

def url(base, ref):
    if not isinstance(ref, str) or not ref or any(c.isspace() for c in ref):
        raise ContractError("invalid_uri")
    value = urljoin(base, ref)
    p = urlsplit(value)
    if p.scheme not in ("http", "https") or not p.hostname or p.username is not None or p.password is not None or p.query or p.fragment:
        raise ContractError("invalid_uri")
    try:
        p.port
    except ValueError:
        raise ContractError("invalid_port") from None
    return value

def origin(value):
    p = urlsplit(value)
    return p.scheme, p.hostname, p.port or (443 if p.scheme == "https" else 80)

def manifest_ref(text):
    if len(text.encode()) > 65536:
        raise ContractError("skill_too_large")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ContractError("missing_frontmatter")
    try:
        end = lines.index("---", 1)
        raw = "\n".join(lines[1:end])
        # Reject aliases, anchors, explicit tags and duplicate keys.
        if any(isinstance(t, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken, yaml.tokens.TagToken)) for t in yaml.scan(raw)):
            raise ContractError("unsafe_yaml")
        class UniqueLoader(yaml.SafeLoader):
            pass
        def unique(loader, node, deep=False):
            out = {}
            for key, value in node.value:
                k = loader.construct_object(key, deep=deep)
                if not isinstance(k, str) or k in out:
                    raise ContractError("duplicate_or_invalid_yaml_key")
                out[k] = loader.construct_object(value, deep=deep)
            return out
        UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique)
        data = yaml.load(raw, Loader=UniqueLoader)
        meta = data.get("metadata") if isinstance(data, dict) else None
        if not isinstance(meta, dict) or meta.get("service-discovery-version") != "1":
            raise ContractError("unsupported_discovery")
        ref = meta.get("service-manifest")
        if not isinstance(ref, str) or not ref:
            raise ContractError("missing_manifest_uri")
        return ref
    except (ValueError, yaml.YAMLError, TypeError):
        raise ContractError("invalid_frontmatter") from None

def curl(target, method="GET", payload=None, authorization=None, version=None):
    headers = ["Accept: application/json, text/event-stream"]
    if authorization:
        if any(c in authorization for c in "\r\n"):
            raise ContractError("invalid_authorization")
        headers.append("Authorization: " + authorization)
    if payload is not None:
        headers.append("Content-Type: application/json")
    if version:
        headers.append("MCP-Protocol-Version: " + version)
    def quoted(value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    config = "\n".join("header = " + quoted(h) for h in headers) + "\n"
    with tempfile.TemporaryDirectory(prefix="agentlab-curl-") as directory:
        output = Path(directory) / "response"
        command = ["curl", "--silent", "--show-error", "--max-time", "12",
                   "--max-filesize", "131072", "--proto", "=http,https",
                   "--config", "-", "--request", method, "--output", str(output),
                   "--write-out", "%{http_code}", target]
        if payload is not None:
            # Public test payload only; credentials are always stdin config.
            command += ["--data-binary", json.dumps(payload)]
        r = subprocess.run(command, input=config, text=True, capture_output=True)
        if r.returncode or not r.stdout.isdigit():
            raise ContractError("transport_failed")
        status = int(r.stdout)
        if 300 <= status < 400:
            raise ContractError("redirect_rejected")
        body = output.read_text()
        return status, body

def get_document(target):
    status, body = curl(target)
    if status != 200:
        raise ContractError("discovery_failed")
    return body

def discover(root):
    root = url(root, root)
    manifest_url = url(root, manifest_ref(get_document(root)))
    manifest = json.loads(get_document(manifest_url))
    if manifest.get("schema") != "agentlab.service-interfaces.v1" or manifest.get("urlResolution") != "document-relative":
        raise ContractError("unsupported_descriptor")
    for key in ("profile", "quickstart", "catalog"):
        get_document(url(manifest_url, manifest["discovery"][key]))
    return root, manifest_url, manifest

def run(root, authorization):
    root, manifest_url, manifest = discover(root)
    if not authorization:
        return {"discovery":"passed","business":"separate_authorization_required"}
    mcp = url(manifest_url, manifest["transports"]["mcp"]["endpoint"])
    cap = next(c for c in manifest["capabilities"] if c["id"] == "agentlab_service_status")
    http = url(manifest_url, cap["http"]["path"])
    # Check BOTH business targets before sending any credential.
    if any(origin(t) != origin(root) for t in (mcp, http)):
        raise ContractError("cross_origin_authorization_requires_separate_grant")
    protocol = manifest["transports"]["mcp"]["protocolVersions"][0]
    def rpc(message, version=None):
        status, body = curl(mcp, "POST", message, authorization, version)
        if "id" not in message:
            if status != 202 or body:
                raise ContractError("notification_contract_failed")
            return None
        result = json.loads(body) if status == 200 else {}
        if "result" not in result or result.get("id") != message["id"]:
            raise ContractError("rpc_failed")
        return result["result"]
    initialized = rpc({"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":protocol,"capabilities":{},"clientInfo":{"name":"fresh-agent","version":"1"}}})
    version = initialized["protocolVersion"]
    if version not in manifest["transports"]["mcp"]["protocolVersions"]:
        raise ContractError("unsupported_negotiation")
    rpc({"jsonrpc":"2.0","method":"notifications/initialized"}, version)
    listed = rpc({"jsonrpc":"2.0","id":2,"method":"tools/list"}, version)
    if {t["name"] for t in listed["tools"]} != {c["mcp"]["tool"] for c in manifest["capabilities"]}:
        raise ContractError("catalog_mismatch")
    call = rpc({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":cap["mcp"]["tool"],"arguments":{}}},version)
    status, body = curl(http, authorization=authorization)
    if status != 200 or call.get("isError") or call["structuredContent"] != json.loads(body):
        raise ContractError("http_mcp_parity_failed")
    return {"discovery":"passed","initialize":"passed","notification":"passed","tools":len(listed["tools"]),"httpMcpParity":"passed"}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-url", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.skill_url, os.environ.get("AGENTLAB_AUTHORIZATION"))))
    except Exception:
        # Never echo a response, URL containing credentials, or submitted secret.
        print(json.dumps({"ok":False,"code":"service_acceptance_failed"}))
        sys.exit(1)
