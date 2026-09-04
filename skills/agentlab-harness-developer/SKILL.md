---
name: agentlab-harness-developer
description: Design, run, inspect, checkpoint, fork, and compare Code Agent evaluation campaigns using a released AgentLab Harness. Do not use for maintaining AgentLab source or administering production infrastructure.
---

# AgentLab Harness Developer

Use released AgentLab interfaces and receipts to evaluate replaceable Code
Agents. Never assume access to the maintenance repository or an Agent's private
session implementation.

## Start

1. Read [evaluation-model.md](references/evaluation-model.md) before defining a
   task seed or comparison matrix.
2. Read [checkpoint-and-fork.md](references/checkpoint-and-fork.md) before
   selecting fresh-Agent or native-session continuation.
3. Read [observability-and-sql.md](references/observability-and-sql.md) when
   diagnosing difficulty windows or querying captured runs.
4. Use the TypeScript probe before a real Code Agent when validating a new
   environment, capture boundary, or fork path.

## Invariants

- The Harness owns environment and workspace state; the Code Agent is a
  replaceable participant.
- Capture and restore are separate operations. A checkpoint may capture all
  observable state even when a later fork deliberately starts a fresh Agent.
- Bind every run to exact task, environment, Agent, model, adapter, and source
  identities. Do not compare labels such as `latest`.
- Preserve raw LLM and MCP/tool events as analyzable structured data. Redaction
  may remove secrets but must not turn the evidence stream into opaque
  ciphertext.
- Treat a difficulty point as an analysis result with evidence, not simply a
  failed final answer.
- Keep MCPGit and external Code Agent versions independent from AgentLab.

## Minimal qualification order

For the AIWSL preview, use the immutable alpha.9 environment kit and the fixed
`aldev` composition.

The public Quickstart now self-initializes the immutable Harmony Linux x64
6.1.1.300 SDK volume when `vol-harmony` is absent. The asset is fetched from a
GitHub Release with fixed byte count and SHA256, then extracted into a newly
created Docker volume only after the receipt-bound runtime image is installed.
An already present operator-owned `vol-harmony` remains untouched.

This remains an **AIWSL-oriented target preview**, not yet a generic zero-dependency Linux
bootstrap. A genuinely unrelated Linux host may satisfy Docker/x64 requirements
and download every public asset successfully but still fail the deployment
preflight because the descriptor intentionally expects target-owned dependencies
such as the Harmony SDK volume plus an independently qualified MCPGit/SafeGit
control plane and its private projections. Treat that as an unsupported-target
result, not a download failure, and never synthesize empty volumes or credentials
to make the preflight green.
 Preserve one content-addressed cache across repetitions:
online and offline installation are user-selected modes over the same bytes.
The target needs Docker but does not need host Btrfs tools or a host Btrfs
mount: the SessionFS companion owns an instance-local sparse Btrfs image volume.
The MCPGit and sandbox loopback proxies share the main container lifecycle, so
a main-container restart recreates the exact listeners instead of leaving a
stale sidecar network namespace.

The shortest path from a checkout of this release repository is:

```bash
scripts/agentlab-harness-quickstart.sh online-install
scripts/agentlab-harness-quickstart.sh probe-self-test
```

Without a checkout, download the same script from its immutable Git commit and
verify it before execution:

```bash
curl -fsSL -o agentlab-harness-quickstart.sh \
  https://cdn.jsdelivr.net/gh/yxsicd/agentlabrelease@2fea995e2708d32d3aa4f98ac5487dfba0723fcc/scripts/agentlab-harness-quickstart.sh
printf '%s  %s\n' \
  ab07e95113bd4e96d97005e1ce97ed5a87d01c64a986d7d1979ce8f287123902 \
  agentlab-harness-quickstart.sh | sha256sum -c -
chmod +x agentlab-harness-quickstart.sh
./agentlab-harness-quickstart.sh online-install
./agentlab-harness-quickstart.sh probe-self-test
```

The first command downloads each immutable package once, retains it under
`$HOME/.local/share/agentlab/ald00-alpha9`, installs `ald00`, and requires the
runtime health postcondition. The second runs the downloaded deterministic
TypeScript probe tests with the host's Bun runtime. To rehearse without network
access after the first acquisition, use:

```bash
scripts/agentlab-harness-quickstart.sh offline-install
```

For repeated destructive testing on a host whose immutable assets,
composition receipt, CAS, and external MCPGit/SafeGit control plane have
already been qualified, prefer the narrower instance-only path:

```bash
scripts/agentlab-harness-quickstart.sh reinstall-instance
```

`reinstall-instance` deliberately skips compressed-asset verification,
unpacking, composition fetch, and `composition install-docker`. It is a runtime
recreation, not a data reset: preserve the ALD data volume, SessionFS
image/export/control volumes, the healthy SessionFS companion, and the external
MCPGit/SafeGit control plane; then force-recreate only the main `ald00` runtime.
Verify the retained control-plane qualification and SessionFS health before
mutation, and require main health plus `sandboxrs` readiness afterwards.

Use `reset-instance` only when the task explicitly requires destructive ALD
data and SessionFS reset. That slower path purges the per-instance volumes and
runs the full receipt-bound environment installer. Keep runtime reinstall and
data reset as separate semantics: conflating them increases latency and creates
avoidable Docker volume lifecycle races. Use the narrow reinstall for
repeatability/performance loops, not for proving fresh-host acquisition.

On the AIWSL x64 alpha.9 canary, preserving the healthy SessionFS companion and
recreating only the main runtime reduced three validated reinstall samples to
11.565, 12.764, and 11.806 seconds end-to-end. Before removing the redundant
final generic health pass, five validated samples were 13.263--15.154 seconds.
By contrast, invoking the full environment installer while preserving volumes
was stable at roughly 30.8--31.4 seconds. Treat these as diagnostic baselines,
not SLAs; the key optimization is semantic narrowing, not weakening readiness.

The destructive fast path must use explicit error propagation on every
precondition and uninstall step. Do not rely on Bash `set -e` inside a helper
invoked by a conditional timing wrapper such as `if helper; then ...`: Bash
suppresses errexit semantics in that context. A failed qualification probe must
return before the first destructive operation.

Treat a fresh environment as a **release-locked dependency closure**, not as
"the newest AgentLab container". The environment descriptor, composition lock,
and the MCPGit official-release lock shipped inside the environment kit are
authority for the versions that must work together. A previously running
MCPGit/SafeGit service is not compatible merely because its container is
healthy or because an older AgentLab instance used it successfully. If the
deployment preflight rejects the external MCPGit route, qualify or upgrade that
dependency to the release-pinned version instead of weakening the descriptor.

After unpacking the environment kit, validate its MCPGit lock before repairing
or bootstrapping a fresh external control plane:

```bash
kit=./agentlab-environment-kit
mcpgit_lock="$kit/release/mcpgit/agentlab-dev-official-release.json"
mcpgit_release="$kit/scripts/agentlab-mcpgit-official-release.py"

python3 "$mcpgit_release" validate --lock "$mcpgit_lock"
python3 "$mcpgit_release" fetch \
  --lock "$mcpgit_lock" --platform linux-x64 \
  --cache-dir "$HOME/.cache/agentlab/mcpgit-official"
```

Use `--platform linux-arm64` on an arm64 target. Keep the downloaded official
release cache just like the AgentLab CAS; do not substitute an arbitrary
`latest` MCPGit build. `assemble` is available in the same helper when the
target workflow requires a local Docker image assembled from the verified
official release.

The fail-closed deployment preflight is part of installation, not an optional
diagnostic. In particular:

- regenerate private MCPGit and SessionFS credential projections from the
  declared SafeGit authority with the packaged projector/reconcile tools;
  never copy authorization bytes into a release asset or invent replacements;
- repair a failed endpoint/route qualification at its owning external runtime;
  a stale organization route or stale qualification receipt is not evidence of
  compatibility;
- on Docker Desktop/WSL and other layered hosts, verify a prerequisite path by
  mounting the **exact path used by the descriptor** into a disposable
  container. Do not assume that a similarly named WSL-user, Docker-VM, or host
  namespace path is the one Docker bind mounts will resolve.

For an MCPGit Gateway route, a useful bounded acceptance test is semantic, not
just TCP reachability: the target DNS identity should resolve uniquely; an
upgrade request for the qualified Organization Host without authorization
should reach that route and be rejected as unauthorized; the same request with
the projected authorization should complete the WebSocket upgrade. A route
that resolves but selects an old/shared Gateway is still a failed dependency.

Do not accept `docker ps` health alone as Harness readiness. Installation is
complete only after the installer itself exits successfully and its final
postcondition passes. If containers become healthy while installation is still
running, inspect the bounded startup evidence for MCP seed and sandbox
readiness rather than declaring success. Then run `health` and
`probe-self-test`; only after those surfaces pass should a benchmark or real
Code Agent be attached.

`probe-self-test` proves the controllable probe module and installed tool
surface; it is not a real provider call, checkpoint, Fork, or SQL result. Keep
the explicit commands below as the auditable fallback and troubleshooting
surface.

```bash
mkdir -p "$HOME/.cache/agentlab/public-cas/downloads"
curl -fsSL -o /tmp/agentlab-bootstrap.sh \
  https://github.com/yxsicd/agentlabrelease/releases/download/alcontrol/agentlab-bootstrap.sh
sh /tmp/agentlab-bootstrap.sh --current --install-dir "$HOME/.local/bin"

curl -fsSL -o agentlab-aldev-environment-lock.json \
  https://github.com/yxsicd/agentlabrelease/releases/download/aldev/agentlab-aldev-environment-lock.json
curl -fsSL -o agentlab-environment-kit-v0.1.0-alpha.9.tar.zst \
  https://github.com/yxsicd/agentlabrelease/releases/download/v0.1.0-alpha.9/agentlab-environment-kit-v0.1.0-alpha.9.tar.zst
curl -fsSL -o agentlab-ts-probe-v0.1.0-alpha.9.tar.zst \
  https://github.com/yxsicd/agentlabrelease/releases/download/v0.1.0-alpha.9/agentlab-ts-probe-v0.1.0-alpha.9.tar.zst
printf '%s  %s\n' \
  fcca40e0858bbbde7620ddec83db0dc525c62d597926dc27ef66b6dd54c27a73 \
  agentlab-environment-kit-v0.1.0-alpha.9.tar.zst | sha256sum -c -
printf '%s  %s\n' \
  029074b412bdaaccd069250949eec459861e685a5ef398fbbc30d4c7cbf4d2d3 \
  agentlab-ts-probe-v0.1.0-alpha.9.tar.zst | sha256sum -c -
zstd -dc agentlab-environment-kit-v0.1.0-alpha.9.tar.zst | tar -xf -
zstd -dc agentlab-ts-probe-v0.1.0-alpha.9.tar.zst | tar -xf -

agentlabctl fetch composition \
  --lock agentlab-aldev-environment-lock.json \
  --platform linux-x64 \
  --out-dir acquired-aldev \
  --cache-dir "$HOME/.cache/agentlab/public-cas"
agentlabctl composition install-docker \
  --dir acquired-aldev --platform linux-x64 \
  --receipt composition-install-receipt.json

./agentlab-environment-kit/agentlab-env install \
  --instance ald00 \
  --composition-receipt composition-install-receipt.json \
  --release-id alpha9
./agentlab-environment-kit/agentlab-env health \
  --instance ald00 \
  --composition-receipt composition-install-receipt.json
```

After the first successful acquisition, retain the lock, acquired directory,
composition receipt, extracted kit, and CAS. An offline repetition starts at
`composition install-docker`; it must not redownload large assets or contact a
package manager.

## Installation timing and safe repetition

A zero-cache portability probe on an unrelated x64 `hwlinux` host reached the
fail-closed target preflight in 50.58 seconds: control acquisition 5.05 seconds,
public composition download 28.14 seconds, Docker admission 15.44 seconds, and
about 1.93 seconds to reject missing target-owned dependencies. This proves the
public download/package path independently of AIWSL while also documenting that
the current descriptor is not a generic Linux bootstrap.


Quickstart emits one `agentlab.quickstart_timing.v1` JSON line per phase and a
total by default; set `AGENTLAB_TIMING=0` only when compact output matters more
than diagnosis. `agentlab-env` also emits `agentlab.environment_timing.v1` when
timing is enabled. Keep these records with the installation receipt.

On the AIWSL x64 canary with all immutable assets already cached, two complete
alpha.8 measurements were 62.94 and 67.00 seconds. The measured decomposition
was 11.81 seconds to re-admit the cached composition, 13.30 seconds for a
standalone qualification, 34.49 seconds for receipt-bound activation, and
3.32 seconds for final health. This is a diagnostic baseline, not an SLA.
Alpha.9 removes the redundant standalone qualification from Quickstart because
`install` runs the same fail-closed preflight immediately before mutation.
The first retained-cache alpha.9 validation measured 58.89 seconds for
`online-install`: 2.335 seconds acquiring the two new small control packages,
9.325 seconds reusing the CAS composition, 12.478 seconds re-admitting Docker
assets, 31.607 seconds activating the fresh environment, and about 3 seconds
for final health. The same destructive rehearsal followed by `offline-install`
measured 50.10 seconds: cached verification 0.032 seconds, unpack 0.043 seconds,
Docker composition admission 12.425 seconds, environment activation 32.560
seconds, and health 4.955 seconds. Preserve these phase boundaries when
comparing future releases; total time alone cannot distinguish network,
verification, activation, and postcondition regressions.

Do not diagnose a roughly one-minute cached install as network download time:
first inspect the timing events and the composition receipt. `status: reused`
for image, Release, and tools means the time is local verification, preflight,
SessionFS/container activation, and health. Only `online-install` may add
variable acquisition time; `offline-install` must not use the network.

For a destructive ALD rehearsal, first run the packaged uninstaller without
`--execute` and inspect its exact plan. Execution must confirm the instance,
data volume, and SessionFS image volume explicitly:

```bash
root="${AGENTLAB_QUICKSTART_ROOT:-$HOME/.local/share/agentlab/ald00-alpha9}"
uninstall="$root/work/agentlab-environment-kit/scripts/agentlab-ald-uninstall.py"
config="$root/work/agentlab-environment-kit/release/agentweb/aiwsl-agentlab.json"

"$uninstall" ald00 --config "$config"
"$uninstall" ald00 --config "$config" \
  --execute --confirm-instance ald00 \
  --purge-data --purge-sessionfs --purge-control \
  --confirm-purge 'PURGE ald00' \
  --confirm-data-volume vol-data-ald00 \
  --confirm-sessionfs-image ald00-sessionfs-image
scripts/agentlab-harness-quickstart.sh offline-install
```

This removes only ALD instance state. Preserve the cache and content-addressed
program volumes. The current preview still qualifies against the retained
ALA00-owned MCPGit dependency; never remove or restart that dependency as part
of an ALD uninstall/reinstall measurement. For a genuinely fresh environment,
however, validate that retained dependency against the environment kit's
MCPGit official-release lock before reuse. "Already running" is not a version
or route-qualification guarantee.

The AIWSL preview inherits the operator-owned `/share/.env` and joins it with
descriptor-owned non-secret MCPGit controller values; installation may verify
the result but must never print or synthesize secret values. A general new
deployment should know only the LLM Gateway endpoint and its gateway
credential; do not fan provider secrets out to every instance.

After health passes, retain the instance. Run the deterministic TypeScript
probe through capture, cut, fork, and continue, then use exact-revision SQL to
derive difficulty windows and the next dispatch. Require exact lineage, trace,
token/tool evidence, query revision, and result receipt. Repeat with the same
seed until recovery and query results are stable. Only then attach a fresh real
Code Agent, beginning with Codex, and compare fresh-Agent continuation before
native-session preservation.

Keep these three qualification surfaces distinct:

- a standalone TS activation proves the real LLM/MCP boundary and emits a
  bounded trace, but does not by itself prove Git-backed recovery;
- a Git-backed control run proves checkpoint/fork/continue semantics;
- revision-pinned Relation SQL proves reproducible analysis only after the
  captured repository and exact revision have been registered in the AgentLab
  experiment index.

For a real external-brain activation, do not give the probe the broad ChatMCP
discovery/control inventory. The owning Harness must provide the attenuated
nine-tool sandbox Participant endpoint and privately inject the authenticated
Owner plus exact Git Session. The result may cross into analysis only after the
Harness independently revalidates operation/request identity, trace context,
provider/model, allowlist, exact probe actions, and budgets. Never persist the
private activation envelope.

On the `aldev` preview, the Harness MCP endpoint is port `18083`. Port `18094`
is the sandbox loopback and is not an LLM endpoint. Discover tools
progressively: request a bounded summary with a narrow query first, then fetch
only the selected schemas. Repeated broad tool-list payloads are part of the
model context and can dominate input-token usage.

Feed every observed installation or flywheel failure back into this Skill only
when it changes the reusable public workflow. Source-maintainer commands,
private credentials, and host-specific repair shortcuts do not belong here.

If a remote build is cancelled, do not assume its compiler descendants exited.
Inspect for processes bound to the exact disposable worktree target, terminate
only those descendants, and remove only that target before retrying with a
shared dependency cache.


## Code-agent volume tools (`altools`)

Code agents are distributed as immutable **volume-tool packs**, never as
install-time npm/curl side effects and never baked into the AgentLab runtime
image. The public `altools` Release channel currently republishes the exact
Linux-x64 executables for:

- OpenCode `1.18.25` -> `/agent-tools/opencode` with READY digest
  `18e1a314e4ee02eee2b911e5666794aed40b147047c362e44647d94e93258773`;
- Codex `0.151.0` -> `/agent-tools/codex` with READY digest
  `a2122b809656b5409d00273377606fe29c9c643eeb12750a7443e632ec32bb6c`.

The release index is `release/altools/agentlab-altools-linux-x64.json`. Each
asset records its upstream npm package and upstream package SHA256, so AgentLab
is only a distribution/repack layer; the upstream project remains authority.
Packs use standard-window `zstd -10`, include `.agentlab-agent-tool/READY` and
`manifest.json`, and materialize into version/digest-specific Docker volumes.
Runtime containers mount those volumes read-only.

Acceptance evidence on hwlinux: both packs were materialized from their zstd
archives into fresh Docker volumes, READY digests matched the deployment
descriptor, and the AgentLab runtime image executed `opencode --version` as
`1.18.25` and `codex --version` as `codex-cli 0.151.0` without npm/node_modules
being present at runtime.

Do not substitute whatever OpenCode/Codex happens to be installed on a host.
The AIWSL host observed during this work had older versions (`1.17.11` and
`0.142.3`), which is exactly why code-agent tools belong in the offline release
closure.


## MCPGit distribution mirror (`almcpgit`)

AgentLab MUST NOT change the upstream MCPGit release process. MCPGit upstream
Release remains authoritative. AgentLab may republish a distribution mirror in
`almcpgit` for offline installation and transport optimization.

The mirror keeps four lifecycles physically and semantically separate:

1. stable base runtime image;
2. MCPGit program payload (`mcpgit`, `mcpgitgw`, `mcpgit-safe-recover`);
3. tools volume (Node/Bun/npm and seeds/runtime helpers);
4. instance templates.

The public Linux-x64 index is
`release/almcpgit/agentlab-mcpgit-mirror-linux-x64.json`. Every mirrored asset
records upstream repository/tag, upstream asset SHA256, resolved MCPGit source
revision, repacked SHA256 and byte size. Repacking is a pure
`gzip tar stream -> standard-window zstd -10` transform; acceptance requires
the decompressed tar stream SHA256 to remain identical to upstream.

### Program-volume rule

Do not bake a newly resolved MCPGit program into a new runtime image merely to
upgrade MCPGit. Materialize the program tar into a version/digest-specific
Docker volume and mount it read-only at `/opt/mcpgit/program`. Keep tools as a
separate read-only volume at `/opt/mcpgit/tools`; keep durable MCPGit state only
at `/data`.

The desired runtime topology is therefore:

`stable base image + program volume + tools volume + durable data volume`.

On hwlinux this topology was validated directly using the upstream
`mcpgit-offline-base:bookworm-v1-amd64` image. The mirrored a483 program pack
was materialized into a fresh volume and both `mcpgit --help` and
`mcpgitgw --help` executed successfully without rebuilding the image. The
mirrored tools pack was independently materialized to a second volume; with
both volumes mounted, Node `v24.19.0`, MCPGit and MCPGit Gateway executed from
the stable base image. The tools pack intentionally does not duplicate Git;
Git remains a base-image responsibility.

This separation is a distribution/runtime rule for AgentLab only. It does not
change MCPGit upstream tags, manifests, build jobs, or release formats.


Full hwlinux canary evidence: the live `ala00-mcpgit` and
`ala00-mcpgit-gateway` services were force-recreated with
`mcpgit-offline-base:bookworm-v1-amd64` while the a483 program and 79cf tools
were supplied by separate read-only Docker volumes. Both services became
healthy; `ala00`, `ala00-sessionfs`, `ald00`, and `ald00-sessionfs` remained
healthy; the program/tools mounts reported `RW=false`; and the `ald00`
namespace reached the shared MCPGit loopback health endpoint with HTTP 204.
The durable `ala00-mcpgit-data` volume and private state were not replaced.
This proves program-only refresh can avoid rebuilding/re-downloading the base
image and can preserve MCPGit data/state.


## Offline Closure (`aloffline`)

The Linux-x64 offline distribution is described by
`release/offline/agentlab-offline-linux-x64.json` using
`agentlab.offline_closure.v1`. The closure deliberately separates dynamic
channel references from the immutable local snapshot produced at fetch time.

Online resolution follows this rule:

1. pin direct AgentLab control/environment/composition/runtime assets;
2. resolve the Harmony, `altools`, and `almcpgit` child manifests by their
   manifest SHA256/byte counts;
3. flatten them into `agentlab.offline_closure_resolved.v1` with exact asset
   URL, byte count and SHA256;
4. download/cache that resolved list;
5. perform all later installation from the resolved snapshot without channel
   resolution or network access.

This allows MCPGit program and code-agent channels to evolve independently
without weakening offline reproducibility: each fetched offline snapshot still
pins the exact bytes actually downloaded.

Current Linux-x64 closure resolution contains 19 public assets totaling
1,692,135,254 bytes. It includes control/bootstrap, environment kit/probe,
AgentLab runtime image, release/developer-tools packs, Harmony SDK, OpenCode,
Codex, and the split MCPGit base/program/tools/templates mirror. It explicitly
contains no credentials or private SafeGit/SessionFS projection material.

Use `scripts/agentlab-offline-closure.py resolve` to create a resolved snapshot
and `verify-cache` to fail closed on any missing/changed cached asset. This is a
control-layer resolver; bulk fetch should continue to use AgentLab's resumable
asset fetch primitive rather than ad-hoc unverified curl downloads.


### Release-side offline CLI status

Until the `agentlabctl` source tree is available in the current maintenance
workspace, `scripts/agentlab-offline-closure.py` is the authoritative
release-side compatibility CLI for the offline closure. It now supports:

- `resolve`: flatten the top-level closure plus child manifests into an
  immutable resolved snapshot;
- `fetch`: download all assets into `assets/<group>/<filename>` with bounded
  parallelism, `.part` files, resume, byte-count checks, and SHA256 checks;
- `verify`: fail closed against the grouped cache layout;
- `report`: emit exactly one machine-readable JSON report for operators;
- `stage-quickstart`: create a symlink/copy staging root with `downloads/`,
  `bin/agentlabctl`, auditable wrapper scripts (`install-plan.sh`,
  `offline-install.sh`, `health.sh`, `probe-self-test.sh`), and a README for
  the existing Quickstart offline installer.

Validation on hwlinux used the previously fetched 19-asset Linux-x64 cache. The
new CLI verified all 1,692,135,254 bytes, generated a single JSON report, and
created a seven-item Quickstart staging root without duplicating the large
Harmony asset; the stage now includes an `install-plan.sh` wrapper for read-only
preflight before running `offline-install.sh`. The published `aloffline` script was then downloaded back from
GitHub, verified by SHA/size, and run against the same cache; `resolve`,
`verify`, and `report` passed. A repeat `fetch --root` over the already complete
cache finished in about 2.04 seconds with 19/19 assets OK and no redownload. This fixes the earlier proof-of-concept mismatch where
`verify-cache` assumed a flat directory even though the tested cache layout was
`assets/<group>/...`.

Do not claim `agentlabctl offline ...` exists until the real `agentlabctl` source
is recovered and rebuilt. The release-side CLI is the compatibility bridge and
should later be ported into the Rust binary with the same command semantics.

The offline staging wrappers invoke the Quickstart through `bash` rather than relying on the GitHub-downloaded script retaining executable permissions.

Release-side offline fetch appends the expected SHA256 as a query parameter to GitHub Release URLs. This avoids stale edge-cache bytes after same-name control assets are clobbered; immutable/versioned asset names are still preferred for operator entrypoints.

## Web2Atomic / Harmony atomic-service integration boundary

Reference source: `asrelease` branch `origin/research/web2atomic-nextgen`
(commit `555424b9`) under `web2atomic-kit`. The local `asrelease` main worktree
may be dirty with Peterhof/Harmony edits, so inspect the nextgen branch through
a detached worktree or `git show` instead of switching the operator worktree.
There is no branch literally named `next`; the relevant next-generation branch
is `research/web2atomic-nextgen`, with
`wip/web2atomic-nextgen-semantic-journal` as a related work-in-progress branch.

### What Web2Atomic contributes

Web2Atomic is a standalone Agent harness for generating and operating HarmonyOS
WebUI carriers, not a single HAP-building script. Its public boundary is the
self-contained `web2atomic-kit` tree:

- deterministic packages: contracts, project, detector, workflow, agc,
  operations, installer, release;
- OpenCode adapter and host-side credential shielding;
- two public templates: `webui-as` for `atomicService` and `webui-app` for
  normal `app`;
- public Agent Skills for conversion, diagnosis, signing, and device operation;
- release tooling that sanitizes, signs, verifies, and publishes one capsule;
- workflow operations for DevEco/HDC build, deploy, launch, probe, diagnose,
  configure, rebuild, and retest.

The atomic-service template explicitly sets `bundleType: "atomicService"` and
carries schema-validated parameters for bundle name, version, labels, site URL,
translation, purification, cache mode, isolated translation fallback, and
optional Huawei Account local ID token configuration.

### Evidence from the nextgen branch

A detached M4 worktree at `555424b9` showed the raw Kit is small: about 3.0 MB
and 302 source/template/skill files before dependency installation. `npm ci`
expanded dependencies to about 249 MB, so runtime installation must not depend
on npm/node_modules. The quality smoke passed:

- `npm run test:standalone` passed;
- `npm run test:unit` passed;
- `npm run release:sanitize -- --spec release/opencode.json --out ...` passed;
- `npm run release:verify -- --stage ...` passed.

The sanitized release stage was about 1.8 MB with 127 files: compiled
`dist/plugin.mjs`, `dist/credential-host.mjs`, Skills, both templates, schemas,
`release.json`, `inventory.json`, and `SHA256SUMS`. This is the correct payload
size class for AgentLab distribution.

### AgentLab fusion model

Do not merge Web2Atomic into the AgentLab runtime image. Treat it as a separate
public tool payload, analogous to `altools` and `almcpgit`:

`AgentLab offline closure -> Web2Atomic capsule/stage -> OpenCode plugin/tools -> DevEco/HDC/Harmony workflow`

The recommended packaging target is one of the following, in this order:

1. **Capsule-first:** preserve Web2Atomic's existing signed capsule model and
   mirror the verified capsule into AgentLab Release as an offline asset. This
   keeps Web2Atomic's signing/trust model intact and lets the existing installer
   consume exactly one local ZIP offline.
2. **Volume-tool wrapper:** materialize the verified capsule or installed
   OpenCode plugin into a read-only Docker/host volume under an AgentLab tools
   mount. Use only if AgentLab needs to run the plugin inside a controlled
   code-agent container rather than installing it into the host OpenCode config.
3. **Do not use npm-at-install:** the 249 MB dependency tree is a build-time
   concern only. Release assets must contain compiled/sanitized payloads or a
   signed capsule, not `node_modules`.

### Reuse of existing AgentLab release pieces

- `vol-harmony` supplies the Harmony/DevEco-adjacent SDK asset layer. Web2Atomic
  should discover DevEco/Harmony via explicit paths or mounted volumes, not by
  downloading SDKs during conversion.
- `altools` supplies OpenCode/Codex as versioned code-agent program volumes.
  Web2Atomic's OpenCode plugin should target those known versions or declare a
  compatibility contract against them.
- `aloffline` should include the Web2Atomic capsule/stage only after its own
  sanitize/verify/public-download acceptance passes.
- `almcpgit` can record generated project/state/evidence, but AGC credentials,
  signing keys, local device identity, cookies, sessions, and profile material
  must remain outside public releases.

### Security and authority boundaries

Web2Atomic has stricter product boundaries than a normal template generator;
keep them intact:

- AGC credentials are injected as opaque refs or local paths and are never
  copied into AgentLab release assets, Skills, templates, prompts, or MCPGit.
- Signing private keys, profiles, certificates, project sessions, website
  cookies, emulator data, and physical-device identifiers are not public release
  content.
- Web2Atomic upstream/capsule remains authority for template/plugin bytes;
  AgentLab may mirror/repack only after byte verification and should record
  upstream revision, capsule digest, and acceptance evidence.
- Generated Harmony projects are workspace artifacts with lockfiles, not
  reusable AgentLab release assets.

### Practical integration phases

P0: Add an AgentLab Web2Atomic mirror manifest, initially pointing at a verified
sanitized stage or signed capsule from `asrelease` commit `555424b9`. Record
source commit, stage file count, stage SHA, capsule SHA if available, templates
included, and tested OpenCode compatibility.

P1: Add the Web2Atomic asset to `aloffline` as an optional `harmony-web2atomic`
group. The closure should fetch it like `altools`: exact URL, bytes, SHA, no
credentials.

P2: Add an AgentLab staging helper that exposes Web2Atomic to code agents:
- host OpenCode path: use Web2Atomic's own installer/capsule offline install;
- container path: mount the verified plugin/templates/skills as read-only tool
  content and bind only explicit DevEco/HDC/Harmony paths.

P3: Reuse AgentLab offline report/install-plan to show Web2Atomic readiness:
OpenCode version, DevEco home, HDC availability, Harmony SDK volume, AGC
credential status as opaque `present/absent/invalid`, and no secret values.

P4: Only after P0-P3, run a true e2e canary: create a generic `webui-as`
project from a public HTTPS URL, build an unsigned debug HAP on emulator, deploy,
launch, and capture page-readiness/navigation probe evidence. Physical-device
or AGC upload flows require explicit external signing/credential setup and are
not part of the default AgentLab public offline install.

## AgentLab Harmony Ops source pointer and release policy

AgentLab now carries an `alharmony` source-pointer channel for the Harmony
engineering atomic-operation layer. This is deliberately separate from both the
HarmonyOS `atomicService` carrier and the upper Web2Atomic pipe.

Machine-readable pointer:

```text
release/alharmony/agentlab-harmony-ops-source-pointer.json
```

Primary source authority:

- `https://github.com/yxsorg/asrelease.git`, `origin/main`, commit
  `374ab3cf2bdd3c31418997adfdd1aaa13ac8f550` for Rust/native Harmony
  engineering operation and runtime sources.
- `https://github.com/yxsorg/asrelease.git`,
  `origin/research/web2atomic-nextgen`, commit
  `555424b94a02b408b09a4a138f95b3f002a12a8c` for the upper Web2Atomic pipeline.

Content pointers include `web2atomic/crates`, the website-operation harness
schema, the framework-runtime-profile generated host APIs, native framework and
native content-cache maintainer Skills, and `web2atomic-kit` as the upper pipe.

Release layering is strict:

1. P0 `alharmony-ops-core`: Rust-owned basic Harmony project/build atoms
   (`env.status`, `project.create`, `project.verify`, `ohpm.install`,
   `build.debug`, `artifact.inspect`).
2. P1 `alharmony-target-ops`: emulator/device/deploy/launch/probe atoms.
3. P2 `alharmony-release-ops`: packaging, signing, AGC planning, and physical
   flows behind explicit authority gates.
4. P3 `alweb2atomic-kit`: upper pipeline that consumes the lower Harmony atoms;
   it must not define or hide the base project/build layer.

Future Rust service or CLI artifacts for this layer must be published through
AgentLab release metadata under `alharmony`, then added to `aloffline` only
after bytes, SHA256, smoke evidence, and a non-destructive readiness or
install-plan check exist. Do not bake these assets into the AgentLab runtime
image, and do not include `node_modules`, generated project outputs, AGC
credentials, signing keys, physical-device identity, cookies, or website
sessions in public release assets.

## Absorbed Harmony ops-core crate

AgentLab now owns `crates/alharmony_ops_core` as the P0 Rust base layer for
Harmony engineering atoms.  It was created from the asrelease architecture and
contract boundary, not by copying the full asrelease repository.  The crate
currently provides the `alharmony-ops` CLI/library skeleton for
`harmony.env.status`, `harmony.project.create`, `harmony.project.verify`,
`harmony.ohpm.install`, `harmony.build.debug`, and
`harmony.artifact.inspect`.  The first implementation is dependency-free,
emits typed `agentlab.harmony_ops.receipt.v1` JSON receipts, and keeps
`ohpm.install` and `build.debug` as non-destructive command plans until command
execution gates are stabilized.  M4 smoke passed `cargo test`, JSON receipt
checks for five commands, and a native release build; do not publish the M4
binary as Linux-x64.  Build platform-specific release assets separately and add
them to `alharmony`/`aloffline` only after exact bytes, SHA256, smoke evidence,
and install-plan/readiness evidence exist.

## Harmony ops-core project-root guard

hwlinux deep testing of `alharmony-ops-core-linux-x64-9163f32` found that
`ohpm-install-plan` and `build-debug-plan` could return `ok=true` when the
Harmony command existed but the project root did not. AgentLab fixed this in
`a932f4b`: command-plan receipts now include `projectRootExists`, and missing
project roots fail closed with `recoveryOwner=agent` and
`nextAction=harmony.project.create`. Publish and offline metadata should prefer
`alharmony-ops-core-linux-x64-a932f4b` over the earlier `9163f32` binary.

## Harmony ops-core hwlinux deep-test checkpoint

hwlinux testing after `d7f4e2c` verified the current `alharmony-ops-core`
release path end to end. The initial `9163f32` release package passed 14/14
receipt/CLI cases across the six P0 operations, including positive and negative
`env.status`, `project.create`, `project.verify`, `ohpm.install`, `build.debug`,
`artifact.inspect`, plus unknown-command behavior. Real Harmony SDK package
compatibility exposed two lessons: the Harmony SDK zstd archive requires
`zstd --long=30` because its frame window is 1 GiB, and the first command-plan
implementation did not reject a missing project root when the command existed.

The project-root issue is fixed by `a932f4b`, then published through AgentLab
metadata commit `d7f4e2c`. The current Linux-x64 asset is
`alharmony-ops-core-linux-x64-a932f4b.tar.zst`, 163,401 bytes, SHA256
`0604bdb2af116642f7127703b093cdecc57162649ecbe71787aaef766b5ae29e`; its
manifest is 949 bytes, SHA256
`844b75e89f55b5eae29648c9e0c822d3d982cc10b5b45d5ad61f16d62ecfaa2f`; the
packaged `bin/alharmony-ops` binary SHA256 is
`60a4407accfb214e5581ba39762c9f736ce7f4ecd91acc8686c1ef693157df47`.

Final hwlinux release smoke downloaded `agentlab-offline-closure-d7f4e2c.py`
and `agentlab-offline-linux-x64-d7f4e2c.json` from GitHub, resolved 21 assets
and 1,692,303,564 bytes, incrementally reused 19 existing cache assets,
downloaded the two current `a932f4b` harmony-ops assets, and verified
`badCount=0`. The unpacked binary produced correct receipts: existing project
`ohpm-install-plan` returned `ok=true` with `projectRootExists=true`; missing
project `ohpm-install-plan` and `build-debug-plan` returned `ok=false`,
`recoveryOwner=agent`, `nextAction=harmony.project.create`, and
`projectRootExists=false`. Keep the next step focused on `project.create`
materializing a tiny valid Harmony template and then gated bounded execution for
`ohpm.install` and `build.debug`.

## Harmony ops HTTP service mode and hwlinux performance ceiling

`616a68e` adds an experimental loopback HTTP service mode to the same
`alharmony-ops` binary:

```text
alharmony-ops serve --bind 127.0.0.1:<port> --workers <N>
GET /health
GET /v1/ops/<operation>?projectRoot=...&harmonyHome=...&artifact=...
```

The service is dependency-free and reuses the same P0 receipt dispatch as the
CLI. It is a preview transport: one request per TCP connection, `Connection:
close`, fixed worker pool, no keep-alive, no UDS, no batching, and no real
`ohpm`/`hvigor` mutation yet.

hwlinux source-build deployment at commit `616a68e` used 12 service workers on
`127.0.0.1:19741` and passed health plus HTTP receipt smoke for
`artifact.inspect`, `project.verify`, and `ohpm.install` plan. The benchmark
client was a local Rust close-connection HTTP generator. Stable short-run upper
bounds observed on loopback were approximately: `/health` 85-88k RPS, p99 about
1.8-2.0 ms at 64 client threads; `artifact.inspect` 74-77k RPS, p99 about
2.3-2.8 ms at 64 threads; `project.verify` about 63k RPS, p99 about 3.3 ms at
64 threads. `ohpm.install` plan was stable through the lower concurrency region
and reached about 46.9k RPS at 8 threads, but 12+ threads repeatedly entered a
long-tail/error region in the current close-connection transport. Treat 8-12
concurrent `ohpm` plan requests as the current stability boundary, not as a
production target.

The first full matrix also exposed a benchmark design problem: without client
connect/read/write timeouts, high-concurrency runs can hang while the service is
already saturated. The follow-up timeout and isolated tests confirmed the
throughput shape but also showed that frequent service restart/port churn can
pollute results. Future performance work should add persistent connections or a
Unix-domain-socket transport, bounded queue/backpressure receipts, and a native
batch endpoint before retesting. Current results measure the HTTP transport more
than the Rust operation core.

## Harmony ops keep-alive and batch service preview

`a2183da` added HTTP/1.1 keep-alive to the `alharmony-ops serve` preview, and
`f3b52e3` added `/v1/batch/<operation>?n=<count>&...`. hwlinux keep-alive
smoke proved one TCP connection could serve `/health -> artifact.inspect ->
/health`, but the 96-worker keep-alive matrix did not improve throughput over
the earlier close-connection model: health peaked around 75k RPS, artifact
around 66.8k RPS, and project.verify around 57.4k RPS before the matrix entered
a high-concurrency long-tail region. The reason is architectural: the preview
service remains synchronous worker-per-connection.

Batch testing at `f3b52e3` showed the useful next layer. The partial concurrent
batch matrix reached about 549k effective `project.verify` ops/sec at batch
1000 / 12 client threads. Focused single-request batch checks measured
`project.verify` batch 10000 at about 80.8k internal ops/sec and `ohpm.install`
plan batch 1000 at about 268k internal ops/sec. `ohpm.install` multi-thread
batch matrix still hit a long-tail point, so batch is a preview performance
transport, not a production guarantee. The current published Linux-x64 service
preview asset is `alharmony-ops-core-linux-x64-f3b52e3.tar.zst`.

## Harmony ops task isolation and backpressure preview

The next service-control layer adds `--queue-capacity`, `--max-batch`, and
`--task-root` to `alharmony-ops serve`. When task isolation is enabled,
path-bearing operations require `taskId` and enforce that `projectRoot` and
`artifact` stay under `<task-root>/<taskId>` using lexical normalization before
operation dispatch. The service rejects missing/invalid task IDs, path
traversal, and cross-task paths as HTTP 400 service errors. Accepted operation
receipts include `evidence.task` with `taskId`, task root, and
`pathIsolation=true`. The accept side now uses a bounded sync queue and returns
HTTP 503 `queueFull` instead of letting a saturated service grow an unbounded
connection queue. M4 smoke covered in-scope success, cross-scope rejection,
missing/bad task IDs, and queue-full backpressure.

Batch task isolation was then tightened so `/v1/batch/<operation>` validates the
`taskId` and path scope once at the batch boundary and reuses the validated
scope inside the operation loop. This avoids multiplying lexical path
normalization by `n` while keeping `lastReceipt.evidence.task` intact. M4 smoke
verified in-scope batch success and out-of-scope batch rejection before hwlinux
performance retest.

Accept-queue-only backpressure proved unreliable under hwlinux/M4 smoke because
TCP backlog can let a client connect and then wait for a worker instead of
immediately receiving a 503. The service now also supports request-level
`--max-active-requests` using an atomic active-request guard. A long batch can
occupy the only active slot, and concurrent requests then return HTTP 503
`activeRequestLimit` deterministically. Keep both controls: queue capacity limits
accepted idle connection buildup, while active-request limit protects operation
execution capacity.

## Harmony ops isolated service preview asset

`30f2402` is the current Linux-x64 service preview baseline after task-isolation
performance tuning. It keeps the `f3b52e3` keep-alive and batch endpoints, adds
`--task-root`, `taskId`, `--queue-capacity`, and `--max-active-requests`, and
optimizes batch task isolation by validating scope once and attaching task
evidence only to `lastReceipt`. hwlinux clean-build testing passed scope smoke,
active-request 503 smoke, and batch-10000 performance comparison. Observed
single-request batch wall throughput: no-isolation `project.verify` about
77.1k ops/sec, isolated `project.verify` about 75.1k ops/sec; no-isolation
`ohpm.install` plan about 265.4k ops/sec, isolated `ohpm.install` plan about
260.6k ops/sec. Treat this as preview transport evidence; no real `ohpm` or
`hvigor` mutation is enabled.

## Harmony atom task lifecycle

The service now treats each Harmony atom service call sequence as an isolated
task sandbox. `harmony.task.prepare` requires `--task-root` and `taskId`, creates
`workspace/`, `artifacts/`, `tmp/`, `receipts/`, and a `task.json` manifest under
`<task-root>/<taskId>`, then returns a normal receipt with
`nextAction=harmony.project.create`. Task-scoped operations append compact JSONL
receipt events to `<task-root>/<taskId>/receipts/events.jsonl`; batch requests
validate the scope once and only log the final receipt so batch throughput does
not collapse. M4 smoke verified sandbox creation, manifest creation, receipt log
validity, normal op logging, batch lastReceipt task evidence, and cross-task
path rejection.

## Harmony atom task concurrency checkpoint

`89e25e0` is the current atom-task lifecycle baseline. It adds
`harmony.task.prepare`, one sandbox per atomic task, task-local `task.json`, and
`receipts/events.jsonl`. hwlinux clean-build testing prepared 16 atom tasks in
parallel, created a separate `workspace/project` under every task, rejected a
cross-task path (`atom01` trying to use `atom00` workspace), then ran parallel
batch requests for all 16 tasks. Each task log contained exactly its own
`harmony.task.prepare`, `harmony.project.verify`, and `harmony.ohpm.install`
receipts with no taskId contamination. Effective throughput across isolated
atom tasks was about 437.8k `project.verify` ops/sec and 1.35M `ohpm.install`
plan ops/sec. This proves the desired shape: each atom is a task, each task has
an isolated sandbox and receipt log, and batch/concurrency can still scale.

## Harmony sandbox E2E build checkpoint

`035f27a` promotes the Harmony ops preview beyond planning for task-isolated
E2E testing. `harmony.project.create` supports `materialize=true` inside a task
sandbox and writes a minimal Stage-mode Harmony project with `hvigorfile.ts`,
`hvigor/hvigor-config.json5`, app/module profiles, ETS EntryAbility/Page, and
resources. `harmony.ohpm.install` and `harmony.build.debug` support
`execute=true` only inside task isolation. The build command is intentionally
CI-safe and unsigned: `hvigorw --no-daemon --no-parallel --no-type-check
--analyze=false --mode module -p product=default assembleHap`. Earlier manual
attempts showed why this is necessary: missing `hvigor/hvigor-config.json5`
blocks hvigor, and daemon mode hit `EMFILE` watcher pressure; no-daemon mode
built successfully.

hwlinux service E2E at `/tmp/alharmony-service-e2e-035f27a-20260903235659`
used the real Harmony SDK at `/tmp/alharmony-real-sdk-compat-long30-20260903195333/sdk`
and completed 12 service operations in one task sandbox: task prepare, project
materialization, project verify, real `ohpm install`, real unsigned HAP build,
artifact inspect, then two source edits to `Index.ets` followed by
verify/build/inspect each time. Results: initial full flow wall time 8,299 ms;
first edit verify/build/inspect 6,877 ms; second edit verify/build/inspect
6,942 ms. The three HAP builds produced `entry-default-unsigned.hap`, 14,430
bytes each, with distinct SHA256 values
`623889025c103e24230210e0ffc92623181340dc1f0734c94ad4ea4500565580`,
`b6ae343707cde12192c0d5a95840f93824cda864fe58ba284bef2fea684ec7b4`, and
`03443384c208f1ba0f2d1006f8cb7d4154fcd93672c843a96bfcf280294aff87`. The task
receipt log contained 12 events under the task-local `receipts/events.jsonl`.
Signing was intentionally skipped because no signingConfigs profile was present.
This proves init/create -> verify -> install -> compile/package unsigned ->
inspect -> edit/rebuild loops are viable inside the atom task sandbox. The next
step is to publish a Linux-x64 `035f27a` asset and update `aloffline`, then add
stronger bounded-process controls before treating execute mode as production.

## Harmony E2E memory / tmpfs acceleration checkpoint

A hwlinux A/B run at `/tmp/alharmony-memory-e2e-20260904051145` compared the same
`035f27a` service binary and real Harmony SDK with task sandbox and `TMPDIR` on
root ext4 `/tmp` versus tmpfs `/dev/shm` (16 GiB). Both variants completed the
same task-isolated service E2E: `harmony.task.prepare`, materialized project
create, verify, real `ohpm install`, unsigned `hvigor` build/package, artifact
inspect, then two `Index.ets` edits with verify/build/inspect each. HAP SHA256
changed on every build in both variants.

Observed timings: ext4 `/tmp` initial full flow 8,180 ms, edit1 7,047 ms, edit2
6,958 ms; tmpfs `/dev/shm` initial full flow 8,197 ms, edit1 6,956 ms, edit2
6,948 ms. Savings were -17 ms (-0.21%) initial, +91 ms (+1.29%) edit1, and +10
ms (+0.15%) edit2. Conclusion: moving only the task sandbox/build output/TMPDIR
to tmpfs is viable but not material for this small project. The current bottleneck
is Hvigor/ArkTS/Node execution and SDK/toolchain reads, not task-directory disk
I/O. Do not make tmpfs the default optimization yet; expose it as an optional
per-task policy for large projects or slow disks, with memory/quota accounting.
Further no-IO gains must come from Rust-side in-memory templates, receipt buffering,
persistent hot build service/caches, or a ram-backed SDK/cache strategy, but real
Hvigor builds cannot be completely no-IO because they must read source/toolchain
files and write build artifacts.

## Harmony E2E build optimization analysis checkpoint

A follow-up hwlinux optimization probe decomposed the sandbox E2E build into
fixed no-op rebuild cost, source-edit rebuild cost, daemon viability, parallel
mode, and tmpfs impact. The project payload remains tiny (`project` about
0.74 MB, `entry/build` about 0.41 MB), while the SDK/toolchain side is large
(`sdk/default` about 9.1 GB, `hvigor` about 232 MB, `tool/node` about 154 MB),
which explains why task-root tmpfs produced only 0-1.3% improvement.

Measured facts: safe no-daemon no-op rebuild was 1,825-1,874 ms wall with
Hvigor-reported build time around 1.2 s; a source edit rebuild was about 6,897
ms wall with Hvigor-reported 4,596 ms, `CompileArkTS` about 3,143 ms, and
`PackageHap` about 261 ms. `--optimization-strategy performance` did not improve
the edit rebuild (about 6,984 ms wall, `CompileArkTS` about 3,215 ms). True
no-op `--parallel` was effectively the same as no-parallel (1,863 ms vs 1,874
ms). Daemon mode remains blocked on hwlinux by `EMFILE` from Node/chokidar
watchers; current sysctls were `max_user_watches=65536`, `max_user_instances=128`,
`max_queued_events=16384`. Therefore daemon/hot-process is still the most
promising class of optimization, but it first needs watcher/inotify containment
or an SDK-supported non-watch daemon path. Current default should remain
`--no-daemon --no-parallel --no-type-check --analyze=false`.

Optimization plan: P0 keep task isolation and no-daemon CI safety; P1 add task
cache policy and skip/short-circuit rules for no-source-change builds, since a
no-op rebuild still costs ~1.86 s; P2 investigate a persistent build worker only
after solving EMFILE/inotify, because that could attack the 2.3 s wall-vs-Hvigor
wrapper gap and repeated Node/plugin startup; P3 make tmpfs optional per task for
large projects/slow disks; P4 consider SDK/toolchain hot placement only with
memory quota because the unpacked SDK is multi-GB. Rust-side template and receipt
buffering remain useful for concurrency jitter but will not materially reduce
the 6.9 s source-edit build dominated by ArkTS/Hvigor.

## Harmony task-local build cache checkpoint

The next P1 optimization adds a conservative no-op short-circuit to
`harmony.build.debug execute=true`. Before launching Hvigor, the service hashes
the project build inputs (`hvigorfile.ts`, `hvigor/hvigor-config.json5`,
`build-profile.json5`, `oh-package*.json5`, `AppScope`, `entry` profile/package
files, `entry/src`) plus small SDK wrapper/version inputs (`version.txt`,
`bin/hvigorw`, `bin/ohpm`). A successful real build records
`state/build-state.json` under the task sandbox with input fingerprint,
artifact path/bytes, and artifact fingerprint. If a later build sees the same
input and the previous unsigned artifact still matches, it returns a read-only
`cacheHit=true` receipt and skips Hvigor. Any mismatch, missing state, missing
artifact, or changed source falls back to the real no-daemon unsigned build.
This targets the measured ~1.86 s no-op rebuild cost while preserving real
rebuilds for source changes.

## Harmony build-cache release checkpoint

`37ddae9` is the current build-cache preview baseline. It records
`state/build-state.json` after successful task-isolated unsigned builds and can
short-circuit unchanged `harmony.build.debug execute=true` calls. hwlinux
real-SDK E2E measured first build 7,159.790 ms, no-change cache hit 0.883 ms,
source-edit rebuild 7,024.604 ms, and second no-change cache hit 0.888 ms. HAP
SHA remained stable across cache hits and changed after the source edit.

## Harmony project patch atom checkpoint

`harmony.project.patch` is now the stable delta lane for task-owned workspaces.
It applies exact text replacements to one project-relative file, refuses path
traversal or cross-task paths, records `changed`, `occurrences`, classified
partition, and before/after fingerprints, then appends the receipt to the
current task log. M4 smoke verified ArkTS and resource patches, task-local log
emission, and path traversal rejection. Use this instead of re-running
`project.create materialize=true` when an Agent only needs to change generated
or user code.

## Harmony incremental delta analysis checkpoint

YXS correctly identified that random task/project regeneration destroys useful
incremental build state. A hwlinux change-impact probe at
`/tmp/alharmony-incremental-map-37ddae9-20260904090015` kept one stable task
workspace and changed only targeted files. Results showed current no-daemon
Hvigor does not yet provide strong file-type savings for the minimal project:
resource string rebuild 7,001 ms, resource color rebuild 6,853 ms, ETS page
rebuild 6,942 ms, and EntryAbility rebuild 6,890 ms; all were real rebuilds and
all produced different HAP hashes. No-change cache hits around those changes
remained sub-millisecond.

To make delta explicit, AgentLab commit `11defe1` adds `harmony.project.patch`.
It applies exact task-scoped text replacements to one project-relative file,
refuses path traversal/cross-task paths, and records changed status, occurrence
count, classified partition, and before/after fingerprints. hwlinux real-SDK
E2E at `/tmp/alharmony-project-patch-e2e-11defe1-20260904090239` verified the
flow: initial build 7,194 ms, no-change cache hit 0.916 ms, `project.patch` on
`entry/src/main/ets/pages/Index.ets` 0.518 ms with `partition=arkts`, patch
rebuild 7,096 ms, second no-change cache hit 0.910 ms, and path traversal
rejection. HAP SHA stayed stable across cache hits and changed after patch.

Conclusion: the immediate architectural gain is stable task affinity plus a
precise delta lane, not expecting no-daemon Hvigor to infer a tiny affected set.
Next implementation should split build fingerprints by partition (`arkts`,
`resources`, `profile`, `dependencies`, `build-script`, SDK wrappers), record
last changed partitions in task state, and let the scheduler decide: no source
change -> cache hit; harmless metadata/resource-only change -> optionally defer
or batch; ArkTS/build-script/dependency change -> real build; repeated changes
inside one task -> coalesce patches before build. This preserves sandbox
isolation while avoiding random full regeneration.

## Harmony Session Fork workspace-pool checkpoint

YXS identified the right architecture for cross-task incremental builds:
workspace reuse should be modeled as AgentLab Session Fork, not an ad-hoc shared
directory. `harmony.task.fork` now creates a child atom task from a parent task
cut. It copies parent `workspace/`, `artifacts/`, `state/`, and `cache/` into a
fresh child sandbox, creates an independent `receipts/` log, rewrites
`state/build-state.json` paths from parent to child, and records fork evidence.
M4 smoke proved child sees parent cut state, parent stays unchanged after a
child `harmony.project.patch`, repeated fork to an existing child fails closed,
and child receipt log is independent. Current implementation uses safe
copy-tree fallback because hwlinux ext4 does not support reflink; future
SessionFS/Btrfs should provide the real fast fork backend while preserving the
same operation contract.

## Harmony Session Fork E2E checkpoint

`74be098` introduced `harmony.task.fork` and `5ed2026` fixed forked
`build-state.json` by refreshing the child input/artifact fingerprints after
path rewrite. This implements the Harmony-side version of AgentLab Session Fork:
a parent atom task is kept as a cut, a child task inherits parent
`workspace/`, `artifacts/`, `state/`, and `cache/`, then child-only deltas are
applied with `harmony.project.patch` before build. The child has an independent
receipt log and must not mutate the parent cut.

hwlinux real-SDK E2E at `/tmp/alharmony-session-fork-e2e-5ed2026-20260904101352`
proved the sequence: parent prepare/create/ohpm/build, parent no-op cache hit,
fork child, child inherited-cache build, child patch, child rebuild, child cache
hit, parent cache hit after child. Timings: parent build 7,149 ms; parent cache
hit 0.815 ms; fork child 13.522 ms for 82 files / 618,477 bytes using
copy-tree fallback; child inherited build cache hit 0.974 ms; child patch 0.473
ms; child real rebuild 7,258 ms; child cache hit 0.772 ms; parent final cache
hit 0.742 ms. Parent HAP SHA stayed unchanged; child HAP matched parent before
patch and changed after patch. This proves the desired high-level model:
workspace pool selection should produce a parent task, `task.fork` creates the
new child task, deltas are applied into the child, and build cache/compile state
is inherited without cross-task contamination.

Current backend caveat: hwlinux ext4 did not support reflink, so this preview
uses safe copy-tree fallback. Do not use hardlinks for writable build trees
unless every write path performs break-link semantics, because otherwise child
builds can mutate parent inodes. The future production backend should call the
existing AgentLab SessionFS/Btrfs fork path when available, with copy-tree only
as compatibility fallback. The workspace pool above this atom should maintain
manifest/fingerprint indexes, active leases, LRU/space GC, and similarity
ranking; it should not share a mutable workspace directly between tasks.

## Harmony + independent SessionFS composition design

YXS clarified that SessionFS can itself be an independent owned service composed with the Rust build ops. The target is two atomic services: `agentlab-sessionfsd` for forkable storage sessions and `alharmony-ops` for Harmony build semantics. The build service stays independently shippable; SessionFS is a fast fork backend selected by configuration/capability, with copy-tree fallback retained. Workspace-pool should match parent sessions, fork child sessions, apply delta patch/sync, then build and retain candidates. Do not share writable hardlinks or require AgentLab main-container state for the build service.

## Independent SessionFS service implementation checkpoint

AgentLab now has an independent `alsessionfsd` Rust preview service plus a
Harmony-side adapter. `alsessionfsd` owns generic session storage fork/copy
semantics and exposes `/health`, `/capabilities`, and
`/v1/sessions/fork?parentRoot=...&childRoot=...&include=workspace,artifacts,state,cache&reset=receipts,tmp`.
It deliberately does not understand Harmony, OHPM, Hvigor, HAP, or build
receipts. `alharmony-ops` remains the owner of `harmony.task.fork` semantics and
can use `--fork-backend copy-tree|sessionfs|auto` plus `--sessionfs-endpoint`.
M4 composition smoke proved explicit `sessionfs` backend invocation, child
path/state rewrite, child patch independence, and `auto` fallback to copy-tree
when no SessionFS endpoint is configured. This preserves standalone deployment
while enabling fast-fork backend replacement.

## Independent SessionFS composition E2E checkpoint

`db77da4` adds the standalone Rust `alsessionfsd` preview service and wires
`alharmony-ops` to it through `--fork-backend sessionfs --sessionfs-endpoint`.
The SessionFS service exposes generic storage operations only and currently uses
safe `copy-tree-preview`; it deliberately does not know Harmony/Hvigor/HAP. The
Harmony service remains the owner of `harmony.task.fork`, path/state rewrite,
build-state refresh, project patch, build cache, and receipts.

hwlinux clean-clone real-SDK E2E ran at
`/tmp/alharmony-sessionfs-compose-e2e-db77da4-20260904132912`. It built both
binaries from source, started independent `alsessionfsd` and `alharmony-ops`,
then executed parent prepare/create/ohpm/build, parent cache hit, sessionfs fork
to child, child inherited cache hit, child patch, child rebuild, child cache
hit, and parent cache hit after child. Timings: parent build 7,125.630 ms,
parent cache hit 0.941 ms, sessionfs fork 13.912 ms wall / 5,322 us backend for
82 files and 622,987 bytes, child inherited cache hit 0.843 ms, child patch
0.588 ms, child rebuild 7,233.675 ms, child cache hit 0.834 ms, parent final
cache hit 0.724 ms. Binary SHA256: `alharmony-ops`
`2f5df6ddc5cbc18914df91cd515989b15cc83dd7ff0f7c6065b2e6847e2cdc84`,
`alsessionfsd` `679a1dc31816417ca9c930baf8c196a0fc28d034dbeb73af381aa1d4be3d01d2`.
This proves two independent owned services can compose while preserving Session
Fork semantics and build-cache inheritance.

## Real Btrfs SessionFS fast-fork checkpoint

The independent `alsessionfsd` path now has a real Btrfs subvolume backend in
addition to portable copy-tree compatibility. The public storage lifecycle is
`session.create` plus `session.fork`: `harmony.task.prepare` asks SessionFS to
create the initial task root, so a Btrfs-backed task is born as a subvolume and
is immediately eligible to become a workspace-pool parent. `harmony.task.fork`
then snapshots that parent, prunes parent-only top-level metadata, resets
`receipts/` and `tmp/`, and lets Harmony rewrite child lineage/build-state.
Both prepare and fork receipts propagate `backend`, `fallback`, and
`copyOnWrite` so callers can distinguish a true CoW fork from compatibility
copying.

The service supports `--backend auto|copy-tree|btrfs-subvolume` and
`--storage-root`. The owned storage root is canonicalized and request paths are
rejected if they leave it or traverse a symlink. `auto` is fail-safe: it
attempts the Btrfs primitive directly and falls back on failure. In particular,
an already-existing non-empty ordinary task directory on a Btrfs filesystem is
never deleted during promotion; hwlinux smoke preserved a sentinel file and
returned `directory-fallback`, while a new sibling task became a real Btrfs
subvolume. Explicit `btrfs-subvolume` remains fail-closed.

hwlinux acceptance used a disposable Docker-owned sparse Btrfs image, matching
the existing AgentLab SessionFS companion storage shape while keeping the host
ext4 filesystem untouched. Final composed E2E started independent
`alsessionfsd` and `alharmony-ops`, prepared a parent, wrote workspace/cache
state, forked a child, verified both roots with `btrfs subvolume show`, verified
the child receipt log did not inherit the parent prepare event, mutated the
child, and rechecked the parent. SessionFS prepare was 2,258 us; fork was 8,731
us with `copiedFiles=0` and `copiedBytes=0`; both receipts reported
`backend=btrfs-subvolume`, `copyOnWrite=true`, `fallback=false`.

A scale comparison used 10,000 files of 4 KiB each. Three Btrfs forks measured
59,564 / 44,145 / 29,714 us (median 44,145 us); three copy-tree forks measured
375,047 / 351,586 / 359,699 us (median 359,699 us), giving about 8.15x median
speedup. The remaining release work is composition/deployment rather than the
fork primitive: wire the combined release to a persistent companion-owned
Btrfs image/export, add one-command start/install handling, and then run the
same acceptance against that packaged topology and real retained Harmony
workspace-pool candidates.

## Harmony project sync atom checkpoint

`harmony.project.sync` now supports complete-package delta merge into a stable
child workspace. It requires task isolation for both `projectRoot` and
`sourceRoot`, rejects cross-task sources, skips generated build/dependency/cache
directories, uses content fingerprints for cross-directory comparison, copies
only changed bytes, and optionally prunes target-only files with
`deleteMissing=true`. M4 smoke staged an 18-file package, changed two existing
files, added one ArkTS file, and omitted one resource file; sync skipped 15
files, copied 3 files / 602 bytes, deleted 1 file / 143 bytes, wrote
`dirty-partitions.json` with `arkts=2` and `resources=2`, and completed in
3,840 us. A second identical sync was read-only with 18 skipped files in
1,349 us. This is the bottom atom for full new-package diff-and-merge after a
Session Fork.

## Harmony workspace index/match checkpoint

`harmony.workspace.index` and `harmony.workspace.match` now provide the minimal
service-side workspace-pool discovery layer. The index scans task candidates
with `state/build-state.json`; match ranks candidates for an `inputFingerprint`
plus optional file-count/byte hints and returns the best parent for
`harmony.task.fork`. M4 smoke proved a two-candidate pool returns the exact
fingerprint parent first. This is intentionally a preview: it is exact-fingerprint
first and should later grow partition/manifests and LRU/lease/GC, but it already
prevents relying on external shell directory discovery.

## Harmony sync + workspace-pool preview checkpoint

`8501c3d` adds `harmony.project.sync`, the byte-level full-package delta merge
atom. Both `projectRoot` and `sourceRoot` must be task-scoped. It skips generated
build/cache/dependency directories, compares content fingerprints across staging
paths, copies only changed files, optionally deletes target-only files with
`deleteMissing=true`, and writes `state/dirty-partitions.json`. M4 smoke copied
3 changed files / 602 bytes, deleted 1 stale file / 143 bytes, skipped 15 files,
and finished in 3,840 us; repeated identical sync was read-only in 1,349 us.

hwlinux real-SDK composition E2E at
`/tmp/alharmony-sync-compose-e2e-8501c3d-20260904133931` proved the full path:
independent `alsessionfsd`, `alharmony-ops --fork-backend sessionfs`, parent
build 7,179.277 ms, parent cache hit 0.903 ms, sessionfs fork 7.061 ms wall /
5,309 us backend for 82 files and 618,489 bytes, child inherited cache hit
0.835 ms, staged-package `project.sync` 1.501 ms wall / 1,031 us core with 3
copied files, 1 deleted stale file, and 16 skipped files, child rebuild
7,136.378 ms, child cache hit 0.877 ms, and parent final cache hit 0.809 ms.
Parent HAP stayed unchanged; child HAP changed after sync/build.

`28b026c` adds the first service-side workspace-pool discovery preview:
`harmony.workspace.index` scans task candidates with `state/build-state.json`,
and `harmony.workspace.match` ranks candidates by `inputFingerprint` plus
optional file-count/byte hints before `harmony.task.fork`. M4 and hwlinux smoke
both proved a two-candidate pool returns the exact fingerprint parent first.
This is exact-fingerprint-first only; next work should add partition manifests,
lease/GC, and similarity scoring for non-exact packages.

## Harmony pool safety checkpoint

`2dca2dd` adds partition-aware matching and `735dff7` adds pool leases plus GC. Use `workspace.match` to select a parent, `workspace.lease` to protect it before `task.fork`, then `workspace.release` after fork. `workspace.gc` skips active leases and protects the newest `keepLast` candidates; dry-run is read-only and deletion requires `execute=true`. hwlinux smoke verified leased A was protected, B was reclaimed first, and A was reclaimable only after release.

## Harmony workspace GC quota checkpoint

`harmony.workspace.gc` now supports `maxBytes`. It still protects active leases and newest `keepLast` candidates, and dry-run remains read-only. M4 smoke: total 12,616 bytes, `maxBytes=7000`, leased oldest A and newest D protected; GC planned and deleted B/C, freed 5,808 bytes, projected 6,808 bytes, leaving A/D.

## Harmony combined GitHub release checkpoint

`63973cc` added the `24b65cb` combined release metadata/package, `3c99d7f` added current aliases, and `af40102` added immutable channel/offline snapshots. GitHub Release `alharmony` now contains `alharmony-combined-linux-x64-24b65cb.tar.zst/json`, `alharmony-combined-linux-x64-current.tar.zst/json`, `agentlab-harmony-channel-index.json`, and `agentlab-harmony-channel-index-3c99d7f.json`. GitHub Release `aloffline` now contains `agentlab-offline-linux-x64.json` and `agentlab-offline-linux-x64-3c99d7f.json`. Linux download-back smoke at `/tmp/alharmony-github-release-smoke-linux-20260904142714` downloaded current assets from GitHub, verified manifest/SHA, extracted both binaries, started independent `alsessionfsd` and `alharmony-ops`, and proved partition match, lease, and GC dry-run.

## Real Btrfs fast-fork GitHub release checkpoint

`218ce52` implements the real SessionFS Btrfs create/fork lifecycle and Harmony
prepare integration. `2b544d5` publishes
`alharmony-combined-linux-x64-218ce52.tar.zst/json` and advances the current
Harmony/offline indexes; `d155fad` freezes those indexes as immutable
`*-2b544d5.json` snapshots. GitHub Releases `alharmony` and `aloffline` contain
the new immutable assets plus refreshed current aliases/indexes. The immutable
package is 389,602 bytes with SHA256
`0d854c293f76ea3f16c55c61091fc817523a2e574c38e0516e5dea0280010352`.

Do not treat upload success as closure. The authoritative download-back smoke
is `/tmp/alharmony-github-release-smoke-linux-20260904134339` on hwlinux. It
downloaded current package/manifest/channel/offline assets from GitHub, matched
package size/SHA and both current pointers, extracted the package, and passed
every embedded payload checksum. The downloaded stripped binaries then ran a
fresh companion-shaped Btrfs E2E: `harmony.task.prepare` 2,194 us,
`harmony.task.fork` 8,523 us, `copiedFiles=0`, `copiedBytes=0`,
`backend=btrfs-subvolume`, `copyOnWrite=true`, `fallback=false`, independent
child receipts, and parent state unchanged after child mutation. This closes
the real fast-fork primitive and GitHub binary distribution loop; remaining
work is persistent companion/start-install integration and acceptance against
retained production Harmony workspace-pool candidates.

## Harmony ops on AgentLab infrastructure checkpoint

The independent `alharmony-ops` service now has an AgentLab infrastructure
execution mode rather than copying bwrap or joining AgentLab Runtime. Configure
`--sandbox-endpoint` and optional `--sandbox-token-file`; service startup must
receive the exact `agentlab-domain-sandboxd` readiness contract proving
`executor=bwrap`, a configured domain task root, and `mcpGitRequired=false`.
After that, `harmony.ohpm.install` and `harmony.build.debug` use fixed
`harmony-ohpm` / `harmony-build` stages. The project must be below the current
task's `workspace/`, writable paths are explicit and relative, the toolchain is
under `/opt/harmony`, and the returned receipt is accepted only with
`sandboxed=true` plus `executor=bwrap`. A configured sandbox error never falls
back to direct `Command::new`; the direct path remains compatibility-only when
no sandbox endpoint is configured.

The matching AgentLab source adds the separate
`agentlab-domain-sandboxd` binary. It exposes only health/readiness/metrics and
`POST /v1/domain-tasks/:taskId/{prepare|fork|exec}`. Production prepare/fork is
backed by mature `agentlab-sessionfsd` UDS; the wire never exposes Owner,
Session, Attempt, Capsule, fence, snapshot, prepared-mount handle, or physical
storage paths. Exec consumes the authoritative prepared mount plan through
bwrap. The service does not initialize MCPGit Session backends, Agent Runtime,
Harness, LLMGW, or a brain. `sandproto` owns the strict private DTOs.

HW Linux validation passed four existing Harmony library tests, eight
sandbox-client tests, three domain endpoint tests, thirteen sandbox policy
tests, mature `agentlab-sessionfs --features transport-uds` 15/15, the domain
sandbox/sessionfs daemon builds, and formatting/diff gates. The endpoint
matrix includes a bearer-auth fail-closed regression: the reduced axum Router
must explicitly project `AppState` into request extensions because
`with_state` alone does not feed the shared pre-handler/rate-limit middleware.

The earlier retained real E2E at
`/tmp/alharmony-agentlab-infra-e2e-20260904` used Docker-owned loopback Btrfs,
the real Harmony SDK, authenticated `agentlab-domain-sandboxd`, and
`alharmony-ops`. It measured OHPM 1.037 s, parent bwrap build 9.154 s, Btrfs
Fork 51.560 ms with zero copied files/bytes, inherited parent and child cache
hits, and child patch/rebuild through bwrap in 9.142 s. Parent source/HAP stayed
unchanged, child artifact identity changed after the patch, and child receipts
were independently verified.

The storage migration is now closed in production mode. Use
`--fork-backend agentlab-sessionfs`; `harmony.task.prepare` calls domain
`/prepare`, and `harmony.task.fork` calls domain `/fork`. The AgentLab facade
owns mature Create/Prepare and Snapshot/Verify/Clone/Prepare against
`agentlab-sessionfsd`, projects stable private task aliases, resets child
tmp/receipts, and preserves workspace/cache/artifacts/state through Btrfs COW.
Standalone `alsessionfsd` remains compatibility/test-only. Final evidence at
`/tmp/alharmony-mature-uds-e2e-20260904/result.json` proves parent prepare
148.668 ms, Fork 280.213 ms / zero files / zero bytes, OHPM 1.245 s, parent
build 8.614 s, child rebuild 7.872 s, inherited cache hit, independent receipts,
parent isolation, exact parent->snapshot->child Btrfs UUID ancestry, and no
preview `alsessionfsd` process.

Repeated network-disabled acceptance corrected an earlier lifecycle diagnosis.
The raw failure was a cold Hvigor user home attempting
`Installing pnpm@10.28.2...`, not a completed build whose Node process needed to
be killed. Production composition now mounts an immutable pnpm helper seed at
`/opt/harmony-seed/hvigor-wrapper-tools`; sandboxed Harmony builds set
`HVIGOR_USER_HOME=/runtime/deps/hvigor-user-home`, force npm offline, and keep
mutable package/build caches in the task `runtime-deps` scope. Final evidence
at `/tmp/alharmony-phase1-seeded-e2e-20260904/result.json` proves parent/child
bwrap builds around 7.06 s, Btrfs Fork 20.406 ms / zero files / zero bytes,
parent and child cache hits, no request-time pnpm installation, 14,438-byte HAP
artifacts, Bearer fail-closed behavior, and no real lingering Hvigor process.
Do not reintroduce a terminal-marker/kill supervisor for this issue.
