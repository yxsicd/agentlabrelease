#!/usr/bin/env python3
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "manifest.json").read_text())
provenance = json.loads((ROOT / "provenance.json").read_text())
index = json.loads((ROOT / "package-index.json").read_text())

assert manifest["schema"] == "agentlab.public_distribution.v1"
assert provenance["schema"] == "agentlab.public_distribution_provenance.v1"
assert index["schema"] == "agentlab.public_package_index.v1"
assert manifest["contractVersion"] == index["contractVersion"] == provenance["contractVersion"] == 1
assert manifest["entrypoint"] == "SKILL.md" and (ROOT / manifest["entrypoint"]).is_file()
assert index["current"] == "manifest.json"
assert provenance["source"]["repository"] == "https://github.com/yxsicd/agentlabrelease"
assert provenance["privateSourceRequiredForInstallation"] is False
assert manifest["acceptance"]["legacyFallback"] is False
assert manifest["acceptance"]["automaticPromotion"] is False
assert index["fullInstanceReleaseQualified"] is False
assert manifest["defaultParticipant"] == {
    "topology": "supervisor-managed-isolated-subagent",
    "execution": "attempt-scoped-remote-mcp",
    "context": "explicit-task-only-cut",
    "independentProviderKeyRequired": False,
    "qualification": "pending-real-instance-assessment",
}
for name in ("inventory", "uninstall", "methodRegistry"):
    assert (ROOT / manifest[name]).is_file(), name
for journey in manifest["journeys"].values():
    assert (ROOT / journey).is_file(), journey
composition = manifest["components"]["composition"]
mcpgit = manifest["components"]["mcpgit"]
assert index["defaultComposition"] == composition["publication"]
assert index["defaultMcpGit"] == mcpgit["descriptor"]
for component in (composition, mcpgit):
    for relative in component.values():
        assert (ROOT / relative).is_file(), relative
publication = json.loads((ROOT / composition["publication"]).read_text())
lock_bytes = (ROOT / composition["lock"]).read_bytes()
lock = json.loads(lock_bytes)
assert publication["environmentLockSha256"] == hashlib.sha256(lock_bytes).hexdigest()
assert publication["sourceRevision"] == lock["sourceRevision"]
installer = (ROOT / composition["installer"]).read_text()
control_descriptor = json.loads((ROOT / composition["control"]).read_text())
assert control_descriptor["schema"] == "agentlab.component_update.v1" and control_descriptor["component"] == "control"
assert control_descriptor["contracts"]["planWrites"] is False
assert control_descriptor["contracts"]["planVerifiesInstalledBytes"] is False
assert control_descriptor["contracts"]["fullHarnessReady"] is False
assert control_descriptor["value"]["platform"] == "linux-x64"
assert re.fullmatch(r"[0-9a-f]{40}", control_descriptor["value"]["sourceRevision"])
controller = {"url": control_descriptor["value"]["artifact"], **control_descriptor["value"]}
assert controller["url"].startswith("https://github.com/yxsicd/agentlabrelease/releases/download/")
fixture = ROOT / control_descriptor["qualification"]["fixture"]
assert hashlib.sha256(fixture.read_bytes()).hexdigest() == control_descriptor["qualification"]["fixtureSha256"]
for key, value in {
    "control_url": controller["url"], "control_sha256": controller["sha256"],
    "control_bytes": controller["bytes"], "lock_sha256": publication["environmentLockSha256"],
    "lock_bytes": len(lock_bytes),
    "lock_url": "https://github.com/yxsicd/agentlabrelease/releases/download/" + publication["tag"] + "/environment-lock.json",
}.items():
    assert f'{key}="{value}"' in installer, f"installer drift: {key}"
integration = json.loads((ROOT / mcpgit["descriptor"]).read_text())
upstream_installer = (ROOT / mcpgit["installer"]).read_text()
for pin in (integration["installerRevision"], integration["releaseTag"], integration["manifest"]["sha256"]):
    assert pin in upstream_installer, "MCPGit installer drift"

sums = ROOT / "SHA256SUMS"
if sums.exists():
    for line in sums.read_text().splitlines():
        digest, name = line.split("  ", 1)
        path = ROOT / name
        assert path.is_file(), name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name

registry = json.loads((ROOT / "skills/registry.json").read_text())
assert registry["schema"] == "agentlab.skill_registry.v1"
assert set(registry["roles"]) == {"maintenance", "operations"}
seen = set()
for skill in registry["skills"]:
    assert skill["id"] not in seen, skill["id"]
    seen.add(skill["id"])
    assert skill["role"] in registry["roles"], skill["id"]
    assert skill["layer"] in registry["layers"], skill["id"]
    path = ROOT / skill["path"]
    assert path.name == "SKILL.md" and path.is_file(), skill["path"]
    body = path.read_text()
    assert re.search(r"^name: " + re.escape(skill["id"]) + r"$", body, re.M), skill["id"]
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", body):
        if "://" in target or target.startswith("#"):
            continue
        assert (path.parent / target.split("#", 1)[0]).is_file(), (skill["id"], target)
assert {s["stage"] for s in registry["skills"] if s["role"] == "maintenance"} == {
    "methodology", "goal", "repository-analysis", "program-analysis", "seed-extraction", "calibration", "asset-model", "experiment-learning"
}

print(json.dumps({"schema": "agentlab.release_validation.v2", "contractVersion": manifest["contractVersion"], "ok": True,
                  "coverage": "public-distribution-contract-not-runtime-acceptance"}))
