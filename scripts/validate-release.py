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
assert manifest["newInstanceNetwork"] == {
    "name": "armnet", "selection": "inventory-first-ranked-non-overlapping-private-ipv4",
    "inventory": ["host-addresses", "all-route-tables", "gateways", "dns-resolvers", "docker-ipam", "wsl-host-network"],
    "existingNetwork": "preserve-if-admitted", "fallbackPrivateIPv4Range": "192.168.0.0/16",
    "avoidCommonLanAndVirtualizationDefaults": True, "recheckBeforeCreation": True,
    "wslHostRoutesRequired": True, "existingNetworkMigration": "never-automatic",
    "provisioningQualified": False,
}, "new-instance-network-policy"
assert index["fullInstanceReleaseQualified"] is False
agent = manifest["referenceAgent"]
assert agent["piPackage"] == "@earendil-works/pi-coding-agent" and agent["piVersion"] == "1.1.0"
assert agent["delegatePackage"] == "@bermudi/pi-delegate" and agent["delegateVersion"] == "0.4.0"
for key in ("packageLock", "supervisorProfile", "prepare", "launcher"):
    assert (ROOT / agent[key]).is_file(), key
agent_lock = json.loads((ROOT / agent["packageLock"]).read_text())
for package, version in ((agent["piPackage"], agent["piVersion"]), (agent["delegatePackage"], agent["delegateVersion"])):
    assert agent_lock["packages"]["node_modules/" + package]["version"] == version
assert agent["supervisedDelegationQualified"] is False and agent["attemptRemoteBindingQualified"] is False
supervisor = json.loads((ROOT / agent["supervisorProfile"]).read_text())
assert supervisor["pluginPackage"] == agent["delegatePackage"] and supervisor["pluginVersion"] == agent["delegateVersion"]
assert supervisor["childPolicy"]["parentChildFilesystemIsolationQualified"] is False
assert supervisor["childPolicy"]["remoteAttemptBindingQualified"] is False
assert supervisor["childPolicy"]["automaticCompaction"] == "upstream-default-observe-not-disabled"
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
material = manifest["evaluationMaterial"]
for key in ("requestSchema", "guidance", "validatorSource"):
    assert (ROOT / material[key]).is_file(), key
assert material["inputKinds"] == ["git-http", "archive"]
assert material["archiveBaselineMode"] == "initialize-project-git-and-commit-source-baseline"
assert material["targetRepositoryHostRestriction"] is None
assert material["qualification"] == "contract-only-not-runtime-intake"
assert all(material[key] is False for key in ("acquisitionQualified", "snapshotConsumerBridgeQualified", "automaticGitBaselineQualified", "sessionImportQualified"))
material_schema = json.loads((ROOT / material["requestSchema"]).read_text())
assert material_schema["properties"]["schema"]["const"] == "agentlab.source_material_request.v1"
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
test_tool = control_descriptor["qualification"]["testTool"]
assert test_tool["role"] == "validation-only-not-installation-dependency"
assert test_tool["platform"] == "linux-x64" and test_tool["static"] is True
assert re.fullmatch(r"[0-9a-f]{40}", test_tool["sourceRevision"])
assert re.fullmatch(r"[0-9a-f]{64}", test_tool["sha256"]) and test_tool["bytes"] > 0
assert test_tool["artifact"].startswith("https://github.com/yxsicd/agentlabrelease/releases/download/")
assert hashlib.sha256((ROOT / control_descriptor["qualification"]["rustGate"]).read_bytes()).hexdigest() == test_tool["sourceSha256"]
qualification = control_descriptor["qualification"]
if qualification["status"] == "passed-two-host-component-admission-not-full-harness":
    receipt = json.loads((ROOT / qualification["receipt"]).read_text())["currentConsumerQualification"]
    assert receipt["status"] == "passed-native-component-admission-not-full-harness"
    assert receipt["sourceRevision"] == qualification["entrypointSourceRevision"]
    entrypoint_sha = hashlib.sha256((ROOT / composition["installer"]).read_bytes()).hexdigest()
    assert entrypoint_sha == qualification["entrypointSha256"] == receipt["executedEntrypoint"]["sha256"]
    assert receipt["controller"]["sha256"] == controller["sha256"]
    assert receipt["controller"]["bytes"] == controller["bytes"]
    assert receipt["controller"]["sourceRevision"] == controller["sourceRevision"]
    assert receipt["controller"]["artifact"] == controller["url"]
    for key in ("sourceRevision", "sourceSha256", "artifact", "bytes", "sha256", "role"):
        assert receipt["testTool"][key] == test_tool[key]
    assert qualification["fullHarnessReady"] is False
    assert receipt["acceptanceLimits"]["fullInstanceLifecycleQualified"] is False
    assert receipt["acceptanceLimits"]["attemptScopedRemoteSubagentQualified"] is False
    assert receipt["acceptanceLimits"]["fullFlywheelAndNextRoundConsumptionQualified"] is False
    # Qualify portable platform coverage, never require particular hostnames/peers.
    assert len(receipt["nativeTargets"]) >= 2
    assert {"linux-x64", "wsl2-linux-x64"} <= {target["platform"] for target in receipt["nativeTargets"]}
    for target in receipt["nativeTargets"]:
        assert target["sourceRevision"] == qualification["entrypointSourceRevision"]
        assert target["fullHarnessReady"] is False and target["allFourPacksAndRuntimeImageReused"] is True
        assert all(op["exit"] == 0 for op in target["operations"].values())
        assert target["fixture"]["toolSourceSha256"] == test_tool["sourceSha256"]
        if target["fixture"]["executedReleasedStaticTool"]:
            assert target["fixture"]["executedToolSha256"] == test_tool["sha256"]
        else:
            assert target["fixture"]["toolCompiledFromPinnedPublicRustSource"] is True
            assert re.fullmatch(r"[0-9a-f]{64}", target["fixture"]["executedToolSha256"])
        for gate in ("coldInstall", "activeReadOnlyReuse", "stoppedWritableConsumerDenied", "driftDeniedWithoutRepair", "exactCleanup"):
            assert target["fixture"][gate] is True
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
