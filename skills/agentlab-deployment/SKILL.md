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
   Apply the inventory-first network policy below; never guess a fixed subnet.
4. Use the current [component installer](../../scripts/agentlab-composition-install.sh):

   Its [immutable installer release](../../release/components/installer-eee1e1e-linux-x64.json)
   binds the downloadable shell file, controller and environment lock. Download
   the declared GitHub asset into the fresh private acquisition directory and
   verify its declared size/SHA256 with a host checksum tool before execution.
   It is the same bytes as this pinned repository's script, not another installer.

   ```bash
   bash scripts/agentlab-composition-install.sh online --cold --root /absolute/new/private/root
   bash scripts/agentlab-composition-install.sh inspect --root /absolute/private/root
   bash scripts/agentlab-composition-install.sh inspect-registry --root /absolute/private/root
   ```

   Primary acceptance for every changed published cut is a new GitHub download
   and `online --cold` installation. Its dedicated root/cache and registry must
   be absent; every selected image and component volume must be absent on the
   explicitly selected local daemon. Keep an operator-supplied Docker endpoint
   private and never switch the caller's default Docker context. The installer
   refuses existing state and any raced reuse; it does not delete old resources
   or retry as warm. This is component cold installation, not whole-host or
   full-Harness qualification. Uninstall-preserve/reinstall is an independent
   gate; existing verified reuse is supplementary, never the primary evidence.
   Optional `online --plan` acquires exact public bytes and reports image/volume
   identity plus active/stopped shared references without Docker writes. It
   does write its dedicated acquisition root/cache. `inspect` reads that
   existing root without creating files/resources. Neither plan validates
   installed payloads or template readiness. Install separately verifies actual
   bytes/types/modes/links with read-only no-copy helpers before reusing a pack;
   unknown ownership, writable consumers or drift fail without repair.
   Install keeps a private durable `component-registry` with current, previous
   and pending qualifications. Interrupted targets retry only against the same
   Docker daemon/platform/lock with full verification; repeated exact reuse
   retains the generation. Registered installation freezes a local Unix Docker
   endpoint; remote TCP is not supported by this component cut. `inspect-registry`
   reads historical records without Docker, writes or repair. It is not live
   health, full-instance activation, rollback, uninstall or deletion authority.
   A receipt-export failure after commit explicitly reports
   `qualificationCommitted=true; receiptExportFailed=true`; inspect the durable
   record rather than assuming the prior selection is still current.
   The [historical transaction evidence](../../docs/evidence/component-transactions-20261009.json)
   qualifies two unchanged online-wrapper runs and no-write history inspection
   on Linux and WSL2 for controller 01b77751, not the selected f2e87a57 cut.
   It is warm reuse with a fresh registry, not cold package
   installation or a complete runtime upgrade/rollback/uninstall qualification.
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

### Inventory-first network selection

Before choosing `armnet`, retain current host interface IPs/prefixes, gateways,
DNS resolver addresses, all IPv4 route tables, VPN routes and Docker IPAM. On
WSL include the Windows host's LAN/VPN/virtual-switch routes and DNS, not only
Linux's view. Default routes are not an overlap veto. Match an existing bridge
to its exact network/interface before excluding that bridge's own route; do not
exclude unrelated LAN/VPN routes merely because they share its subnet.

Prefer preserving an existing usable network when identity, attachment policy,
address capacity and absence of **external** conflicts are verified. Otherwise
rank RFC1918 candidates against that inventory and declared service constraints,
avoiding common LAN/virtualization defaults. `192.168.0.0/16` is a fallback pool,
not a mandatory address or fixed /24; `192.0.0.0/8` is not private. Reject a
candidate overlapping host/LAN/VPN/Docker prefixes or containing an upstream
gateway/DNS resolver. Try the next ranked candidate and retain each rejection
reason; missing required inventory or exhausted candidates means blocked.

Recheck immediately before creation. Record the chosen CIDR, observed network
ID, inventory identity, decision and alternatives in the owned-resource receipt.
Existing shared networks are never automatically removed or renumbered. A
conflict produces a migration plan identifying affected consumers, ownership
and rollback; adjusting a running network is a separate admitted change.
This is the provisioner's required policy, not qualification of the still-missing
public full-instance lifecycle or proof that a candidate is safe on every host.

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
