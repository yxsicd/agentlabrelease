---
name: agentlab-deployment
description: Install and manage AgentLab's public GitHub dependency closure, or inventory and safely uninstall historical AgentLab installations. Not for maintaining private source.
metadata:
  agentlab-layer: method
  agentlab-role: operations
  agentlab-stage: deployment
---

# AgentLab deployment

Complete the human -> Agent -> GitHub journey using this public repository and
its referenced public GitHub releases. Do not require AWMCP, a LAN, a particular
hostname, private source, an existing AgentLab instance, or maintainer credentials.

## Select and prepare

1. Pin a full release-repository commit. Read its component descriptors and
   acceptance limits. Resolve mutable channels once, then use exact bytes/digests.
2. Inspect Linux/WSL architecture, Docker access, storage, ports and existing
   installations. Read [historical uninstall](references/historical-uninstall.md)
   before replacing an existing installation. Discovery is not deletion authority.
3. Select a dedicated absolute private root and unique instance/port. Do not
   attach old data automatically. Keep credentials under that root with private
   permissions, never in Git, prompts, receipts or command output.
4. Use the current [component installer](../../scripts/agentlab-composition-install.sh):

   ```bash
   bash scripts/agentlab-composition-install.sh online --plan --root /absolute/private/root
   bash scripts/agentlab-composition-install.sh online --root /absolute/private/root
   bash scripts/agentlab-composition-install.sh inspect --root /absolute/private/root
   ```

   The first command acquires exact public bytes and reports image/volume
   identity plus active/stopped shared references without Docker writes. It
   does write its dedicated acquisition root/cache. `inspect` reads that
   existing root without creating files/resources. Neither plan validates
   installed payloads or template readiness. Install separately verifies actual
   bytes/types/modes/links with read-only no-copy helpers before reusing a pack;
   unknown ownership, writable consumers or drift fail without repair.
   Verified public executables use mode `0555` inside private acquisition
   directories; credentials remain private. This lets a read-only Docker helper
   execute as another UID without adding capabilities or changing shared data.
   It verifies and installs image/program/tool components. **It does not create
   a complete running Harness instance.** Offline acquisition uses the exact
   controller and lock from that same cut; it is not an older-version fallback.
5. For the selected MCPGit component, use the pinned
   [integration](../../release/integrations/mcpgit-prod-linux-x64.json) and
   [installer](../../scripts/agentlab-mcpgit-prod-install.sh). Its isolated
   install/health proof does not qualify AgentLab Session/template/Fork protocols.

## Deployment acceptance

Component admission can be checked with the selected control descriptor's
`qualification.testTool`: a public static Linux-x64 Rust binary, not an
installation dependency. Verify its published size/SHA256 with the host before
execution. Run it with absolute controller and public fixture paths plus the
lock's exact image reference. It checks a cold fixture, active read-only reuse,
stopped writable-consumer denial, preserved drift and exact successful cleanup.
It requires the fixture namespace initially absent and a dedicated serial test;
failed tests retain evidence and need fresh ownership checks before cleanup.
Neither installing nor validating a new machine requires a Rust compiler.

Require an exact installation receipt, instance identity and publicly declared
service SKILL URL. Discover that instance's manifest and effective capabilities.
Require authenticated readiness, successful bounded workspace operation and
independent durable readback before handing it to the flywheel operator.

Current public components and demos do not provide a qualified one-command full
Harness lifecycle. Report `blocked: full-instance-lifecycle-not-published` if no
public, version-bound instance provisioner is available. Do not use the historical
AIWSL quickstart, `/share/.env`, retained control planes or private repair scripts.

## Lifecycle

The controller must expose inspect/list, install, upgrade, rollback and uninstall
from one owned-resource registry. Inspect actual installed identities and shared
references before each change. Upgrade only changed components; qualify the
aggregate closure and preserve data. If an operation is not advertised, stop;
do not invent command names from this target contract.

For uninstall, apply the version-independent
[historical procedure](references/historical-uninstall.md), including orphaned
installations. Preserve data by default. Purge is a separately authorized action,
not an implicit consequence of reinstall or uninstall.

Read [portable lifecycle](../../docs/portable-deployment-lifecycle.md) for current
component evidence and independent outstanding acceptance gates. After complete
instance acceptance, route to [instance operations](../agentlab-harness-developer/SKILL.md).
