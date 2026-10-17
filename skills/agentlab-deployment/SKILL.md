---
name: agentlab-deployment
description: Install and manage AgentLab's public GitHub dependency closure, or inventory and safely uninstall historical AgentLab installations. Not for maintaining private source.
metadata:
  agentlab-layer: method
  agentlab-role: operations
  agentlab-stage: deployment
---

# AgentLab deployment

## Current native controller candidate

The [selected candidate](../../release/components/control-candidate-60c81241-native-render-6a69f841-20261017.json)
pins static controller60c and owning renderer6a. Read
[native Host lifecycle](../../docs/native-host-lifecycle.md) for exact acquisition,
actual Host/application permissions, original-operation readback and the new
data-preserving container-retirement command.

Official published manifests bind exact bytes, Source revision and payload URL/
digest. Git wrappers are not claimed to be downloaded Release assets. Both hosts
acquired60c, executed its valid digest command and read existing original
generation4 journals. No retirement/new startup ran. Renderer6a's original
two-host acquisition and actual private render remain separately scoped.

The unchanged [component installer](../../scripts/agentlab-composition-install.sh)
still uses its declared composition/controller. For component-only installation:

    bash scripts/agentlab-composition-install.sh online --cold --root /absolute/new/private/root

This installs components, not a complete Harness. Full running-instance acceptance
still requires genuine private login inputs, independent Owner/Session/Ready and
durable workspace evidence. Do not borrow another instance's secrets, a host env
fallback or repeated cold-bootstrap operation.

Earlier candidate/preparation reports remain [historical evidence](../../docs/archive/native-host-deployment-preface-20261017.md),
not alternate current recipes. Preserve all existing resources and unknown
original effects. Missing complete lifecycle capability is stated precisely;
private maintainer assistance is not public installation acceptance.

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
