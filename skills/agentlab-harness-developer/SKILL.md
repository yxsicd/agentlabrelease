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
`aldev` composition. Preserve one content-addressed cache across repetitions:
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
unpacking, composition fetch, and `composition install-docker`. It removes only
the ALD instance data, SessionFS instance state, and deployment control state,
then reinstalls from the retained exact composition receipt. Use it for
repeatability and performance loops, not for proving that a fresh host can
acquire the release. If this narrow path fails a deployment preflight or
runtime postcondition, repair the retained external dependency rather than
falling back to an unpinned or weakened configuration.

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
