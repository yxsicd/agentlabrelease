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

The [control candidate](../../release/components/control-candidate-6bd1df9f-native-render-6b0008c1-20261016.json)
provides the fixed native Host cold-bootstrap CLI. Controller6bd1df9f now prepares
the original declared instance data volume inside the durable one-attempt Host
execution: an absent volume is created once with an operation/UID/nonce receipt,
while existing volumes require the declared exact identity. Both are inspected
again before container use. Lost results, foreign races or drift stop without
retry, adoption or deletion. Source6private controls passed; real startup is
tracked separately from these checks.

An actual new WSL Host operation now returns exit0. Independent readback
confirms the operation-bound data volume and all3original containers running
and healthy. The [runtime receipt](../../docs/evidence/control-6bd1df9f-actual-host-startup-20261016.json)
preserves the old failed operation. This is Host startup using qualified
existing components, not two-host component cold installation or application
Owner/Session/physical Ready/Harmony qualification. Continue from the existing
containers; do not repeat the cold-bootstrap operation.

The earlier69b934a0 candidate provides the fixed native Host cold-bootstrap CLI. Verify the descriptor and
executable sizes and SHA-256 before execution. Anonymous final-URL downloads and
bounded read-only execution passed independently on Linux and WSL2. The static
musl PIE has no ELF interpreter or imported libraries. Publication byte inspection
and subsequent Linux/WSL execution are separately scoped in the sealed receipt.

The new69b934a0 cut closes an actual WSL cold-start refusal by privately reading
Windows IPv4 addresses, active routes and DNS alongside Linux/Docker inventory.
Both hosts independently acquired final public bytes; actual WSL declared-network
observation passes. Missing/denied capture or drift still refuses. This proves
the network observation only; application Owner/Session and actual cold startup
remain independent. Preserve the original5764 failure and never replay it.

Actual startup with the new controller currently refuses the prepared shared
sidecar network declaration before creating resources. The separate
[actual observation](../../docs/evidence/control-69b934a0-actual-cold-refusal-20261016.json)
retains that failure. The network list came from explicit private bindings:
correct those owning inputs and render a new directory with the same unchanged
public producer. Preserve the failed input/bundle; never retry its original
operation or infer application authority from corrected declarations.

Cold physical startup uses actual kernel UID, frozen Unix socket rights and
fresh daemon/resource checks. It does not require logging into an instance that
has not started, and it does not grant application Owner or Session authority.
The commands consume an exact v3 private deployment bundle and qualified
component registry. Initialize a NEW disjoint private journal and original
operation with admit generation0, then execute that SAME operation at generation1.
The intent records input identity only; actual Host admission remains independent:

    /absolute/private/root/agentlabctl-6bd1df9f33de-linux-x64 deploy admit /absolute/private/bundle --registry /absolute/private/component-registry --journal /absolute/private/NEW-operation-journal --operation NEW-original-operation-id --expected-generation 0

    /absolute/private/root/agentlabctl-6bd1df9f33de-linux-x64 deploy cold-bootstrap /absolute/private/bundle --registry /absolute/private/component-registry --journal /absolute/private/NEW-operation-journal --operation NEW-original-operation-id --expected-generation 1

Generation 1 or 2 is accepted only for the matching original operation. Failure
or an unknown result is not retried; read back that original operation. Host and
Owner-bound journals cannot adopt each other even with identical plan bytes.
Do not invent a bundle, accept requested Owner fields as authority, or grant the
workspace a Docker socket. One actual private producer/installed composition integration passed;
real cold startup remains unqualified; this command is not a complete installation
recipe. After startup, actual application login and Session/physical Ready remain
independent requirements.

The existing installer still selects f2e87a57. This candidate has not passed
complete two-platform cold install, full instance lifecycle, Owner/Session, or
Harmony feedback reuse. New Host5 and affected execution13 private controls are
Source evidence. They are not runtime acceptance. Existing component identities
remain selected until separately qualified.

The historical [owned-network receipt](../../docs/evidence/control-64cb772c-owned-network-runtime-20261013.json)
retains generation3, its physical ID and the extra 169.254/16 route refusal.
Do not recreate that network or replay unknown effects. Refresh exact resources
and corresponding Host permission before any actual change.
GitHub reports immutable=false; fixed digests and the no-overwrite policy preserve
this candidate's identity.


### Fixed original-origin credential transport

The selected6b0008c1 producer now rejects redirects in the original shared
SafeGit HTTP client. Four new private controls preserve originalPOST/auth/MCP
Session and JSON/SSE/empty success, while five redirect statuses for each same
and different origin make zero follow-up requests. Both exact hosts acquired
final public bytes, verified all16payload files and passed those4controls against
the actual downloaded projector. Read the [new publication](../../docs/evidence/native-render-6b0008c12214-publication-20261016.json).
The old redirect baseline, corrected MIME fixture failure and output-directory
build refusal remain separate evidence. Existing4aef bundles/instances and all
older assets are unchanged; no new private render, businessAuth or complete
instance/Harmony acceptance is inferred from these private tests.

### Preserve the credential service origin

Read the [actual origin intake and OPEN Source control](../../docs/evidence/credential-origin-and-redirect-open-20261016.json).
A Docker-local Global/Gateway name or application-local forwarding URL is not
a portable cross-host service origin. The inspected existing backend mappings
publish no host ports; obtain a separately qualified origin/configuration for
the intended host before moving or using credentials. Runtime WebSocket routing
and SafeGit HTTP MCP projection are separate transports. Resolve a credential
manifest basename under its owning credential root, not the shell directory.

The preserved4aef producer has the following historical OPEN transport issue: a private
loopback control reproduces automatic303 redirect of an authenticatedPOST into
a different-originGET with its dummy authorization. No real credential was used.
Redirect refusal is not yet qualified; do not treat this producer as an origin
qualification or automatically relocate an endpoint. The next owning Source
fix must preserve the original endpoint/context and reject redirects, with new
private controls and a separately published immutable producer. Existing bytes
and the original failure remain preserved; no Source fix or realAuth is claimed.

### Prepare the selected local network

Use the [native preparation contract](../../docs/deploy-network-preparation.md)
with the fixed public controller, exact qualified registry and separately
authorized local Host caller. It captures fresh inventory and journals a single
creation attempt; an intent or supplied target does not grant permission.
An [actual isolated Linux operation](../../docs/evidence/hwlinux-isolated-network-prepared-20261016.json)
now reaches generation4 with independent physical ID/bridge/routes readback.
The old default-daemon network and generation3/extra route remain unchanged.
This is one network prerequisite, not full-instance or Owner/Session readiness.

### Actual native Linux physical storage

The fixed public producer also has [real native Linux storage evidence](../../docs/evidence/hwlinux-actual-storage-preparation-20261016.json): its original
Linux preparation script created a task-owned32GiB sparse Btrfs image, mounted
root0700, enabled the canonical systemd mount unit and made quotas readable.
Independent readback preserves the existing network/generation3 journal and
old isolated Docker daemon. This qualifies that storage slice only. Export,
control, credential projections, complete instance, application Owner/Session
and physical Ready still need independent evidence; do not replay the original
storage operation or recreate its now-present image.

### Supply application login before complete-instance acceptance

The native Host bootstrap prepares physical resources; it does not invent a
login credential. Provide nonempty `basicAuthUser` and `basicAuthPassword` in
the intended deployment or its private `defaults` configuration before the
original render/start workflow. Keep that file private and outside Git, and
never put the password in commands, evidence or a public example. Use an
independently authorized credential source; do not reuse fixture/example
passwords or another service profile. Existing `AL_OWNER_*` declarations and
Host Root rights are separate from real application Owner authentication.

The [actual configuration read](../../docs/evidence/original-instance-auth-configuration-gap-20261016.json)
shows why this matters: three healthy containers and anonymous discovery200
coexist with business status503 `authentication_unconfigured` when both Basic
fields are empty. This is missing configuration, not a wrong-password result
or an authenticated Owner/Session. The existing producer preserves the supplied
inputs; no new renderer defect is claimed. Correct an existing instance only
through its owning admitted reconfiguration/reinstall workflow. The public
once-only cold command is not a reconfigure or restart operation; never replay
it, inject an environment through Docker exec, or fabricate Owner admission.

### Render the native bundle

The earlier4aef783e producer requires an existing toolchains.json bind
source. Its actual WSL bundle passes all9normalized bind-source checks and6Host
identities. An initialized original Host operation reached execution but returned
exit1; independent readback finds no instance containers/data volume. Preserve
that generation4 operation without retry. Complete startup remains unqualified.

The same public4b8c210e producer now has an actual private positive render on
WSL2:16configuration byte identities and6physical participant identities were
independently verified. Acquire the program and prepare private inputs under
the intended renderer/Host caller UID; Root execution requires Root-owned
public helper files and private runtime projections. Preserve failed attempts
and never relax ownership checks. Instance startup and Owner/Session remain
separate gates; private configuration and credential bytes are not published.

The fixed public producer now converges the verified existing Btrfs root to
0700 after mount validation. Actual WSL2 readback preserves mount/image/unit
identities and earlier0755/failure journals. This closes that directory mode
gap; full private bundle, Owner/Session and complete instance readiness remain
independent requirements.

The fixed 4b8c210e producer validates the canonical systemd mount-unit roundtrip
for supported hyphenated instance names. The earlier real prepare rejection is
preserved; use this new fixed package and a newly admitted operation after
reading back the original effect. Existing producer and component bytes remain
available under their original identities.

The [fixed standalone producer](../../release/components/native-render-6b0008c12214.json)
packages the same owning renderer with its exact templates and helpers. Download
the declared archive, verify size/SHA-256, and extract it into a new private
directory. Read its README and native-render-producer.json; private maintenance
source is not required. Explicit actual local deployment configuration, installed
composition receipt and deploy_bindings.v2 are still required. No host config,
env file or credential is included.

From the extracted directory, render into an existing caller-owned mode0700 parent:

    python3 scripts/agentlab-native-render.py own-instance --config /absolute/private/config.json --composition-receipt /absolute/private/install.json --native-plan-bindings /absolute/private/bindings.json --output-dir /absolute/private/rendered

The entry forces render-only and rejects execution, transport and auth switches.
It does not retry or remove partial output. Linux/WSL anonymous download,
all16 payload hashes and standalone help/missing-input/effect-denial checks passed.
Actual private positive rendering passed on WSL2; cold startup and actual
Owner/Session remain unqualified. The producer is not a substitute for authentication or fresh
physical resource checks.

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
   The [current cold-component evidence](../../docs/evidence/public-cold-components-20261009.json)
   binds the independently downloaded installer Release and controller to two
   initially empty Linux/WSL2 daemons, fresh caches/configuration, all-new
   installation and actual image/READY/manifest readback. Both cold refusals
   preserve existing state. Linux additionally passed exact component removal,
   another public download/cold reinstall and a retained synthetic data marker.
   These are component gates, not authenticated workspace or full-instance
   lifecycle acceptance. Test daemons are stopped; private data/evidence remains.
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
