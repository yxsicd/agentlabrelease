# AgentLab Harmony Ops pointer

`alharmony` is the AgentLab channel for Harmony engineering operations.  The
current state is a source pointer, not an executable release payload.

The base layer is **not** Web2Atomic and is **not** the HarmonyOS
`atomicService` carrier.  It is a Rust-owned operation layer over the official
Harmony toolchain:

```text
Rust alharmony-ops-core
  -> DevEco / Hvigor / OHPM / HDC adapters
  -> typed JSON receipts
  -> state transition / nextAction / recovery owner
```

## Source authority

- Rust/native operation and runtime sources:
  `https://github.com/yxsorg/asrelease.git`, `origin/main`, commit
  `374ab3cf2bdd3c31418997adfdd1aaa13ac8f550`.
- Upper Web2Atomic pipe:
  `https://github.com/yxsorg/asrelease.git`,
  `origin/research/web2atomic-nextgen`, commit
  `555424b94a02b408b09a4a138f95b3f002a12a8c`.

## Layering

1. P0 `alharmony-ops-core`: basic project/build atoms.
2. P1 `alharmony-target-ops`: emulator/device/deploy/launch/probe atoms.
3. P2 release/signing/AGC planning behind explicit authority gates.
4. P3 Web2Atomic as an upper pipeline that consumes the lower atoms.

Future Rust service/CLI artifacts must be published through AgentLab release
metadata and then added to the offline closure only after byte/SHA/smoke and
readiness evidence exists.

## Existing alharmony asset clarification

The pre-existing `agentlab-harmony-dev-web2atomic-linux-x64.tgz` asset is
classified by its manifest as `agentlab.harmony-sdk`. It is the current minimal
Harmony CLI/SDK substrate for `/opt/harmony` and `vol-harmony`, with smoke paths
for `hvigorw`, `ohpm`, and `hdc`. Its historical filename mentions Web2Atomic,
but the new Rust operation service is a separate future payload and must publish
through `alharmony-ops-core` metadata before entering `aloffline`.

## Absorbed Rust ops-core crate

AgentLab now owns the P0 Rust crate at `crates/alharmony_ops_core`.  It exposes
`alharmony-ops` as a dependency-free CLI/library skeleton for the basic Harmony
project/build atoms.  The first implementation emits typed JSON receipts and
non-destructive command plans; command mutation is intentionally deferred until
receipt gates are stable.  Platform-specific binaries must be built and
published as separate `alharmony` assets before entering `aloffline`.

## Published P0 Linux-x64 ops asset

The first `alharmony-ops-core` Linux-x64 developer-preview asset is published in
`alharmony` as `alharmony-ops-core-linux-x64-9163f32.tar.zst` with manifest
`alharmony-ops-core-linux-x64-9163f32.json`.  It contains the dependency-free
`alharmony-ops` binary, receipt schema, package manifest, and README.  In this
preview, build/dependency operations emit non-destructive command plans; future
mutating execution requires additional gates.

## Project-root guard fix

`a932f4b` supersedes the first `9163f32` ops-core binary for default/offline use.
The fix adds `projectRootExists` to command-plan receipts and fails closed when
`ohpm.install` or `build.debug` is planned against a missing project directory.
Use `alharmony-ops-core-linux-x64-a932f4b.tar.zst` for the current Linux-x64
preview.

## Service preview asset

`f3b52e3` supersedes `a932f4b` for current Linux-x64 preview use. The new asset
`alharmony-ops-core-linux-x64-f3b52e3.tar.zst` adds HTTP/1.1 keep-alive support
and `/v1/batch/<operation>?n=<count>&...` while preserving the P0 non-destructive
receipt boundary. hwlinux testing showed keep-alive alone did not raise the
close-connection throughput ceiling materially because the implementation is
still worker-per-connection. Batch requests expose the operation-core ceiling:
`project.verify` reached about 549k effective ops/sec in the concurrent batch
matrix, and focused single-request batch measurements showed about 80.8k ops/sec
for `project.verify` and about 268k ops/sec for `ohpm.install` plan. Treat this
as preview transport evidence; no real `ohpm` or `hvigor` mutation is enabled.

## Isolated service preview asset

`30f2402` supersedes `f3b52e3` for current Linux-x64 preview use. The new asset
`alharmony-ops-core-linux-x64-30f2402.tar.zst` adds `--task-root`, `taskId`,
`--queue-capacity`, and request-level `--max-active-requests`. Batch endpoints
validate task scope once at the batch boundary and attach task evidence only to
the final receipt, avoiding repeated path-normalization overhead. hwlinux tests
showed task isolation overhead was reduced to roughly 2.6% for `project.verify`
batch-10000 and 1.9% for `ohpm.install` plan batch-10000; active-request
backpressure returned HTTP 503 `activeRequestLimit` deterministically while a
long batch occupied the only active slot.

## Atom task lifecycle preview asset

`89e25e0` supersedes `30f2402` for current Linux-x64 preview use. The new asset
`alharmony-ops-core-linux-x64-89e25e0.tar.zst` adds `harmony.task.prepare`,
which creates one sandbox per atomic task under `<task-root>/<taskId>` with
`task.json`, `workspace/`, `artifacts/`, `tmp/`, and `receipts/events.jsonl`.
Task-scoped operations append compact receipt events to the task-local JSONL
log; batch requests validate scope once and log only the final receipt. hwlinux
16-task concurrency testing verified independent sandboxes and logs, cross-task
path rejection, and parallel batch execution: `project.verify` reached about
437.8k effective ops/sec and `ohpm.install` plan reached about 1.35M effective
ops/sec across 16 isolated atom tasks. No real `ohpm` or `hvigor` mutation is
enabled in this preview.

## Build-cache preview asset

`37ddae9` supersedes `89e25e0` for current Linux-x64 preview use. It keeps the
atom task sandbox and adds task-local `state/build-state.json` for unsigned HAP
build caching. hwlinux real-SDK E2E showed first build 7.16 s, no-change cache
hit 0.883 ms, source-edit rebuild 7.02 s, and second no-change cache hit
0.888 ms. Cache hits return read-only receipts and skip Hvigor; source changes
fall back to the real no-daemon build.

## Combined SessionFS + Harmony ops preview (24b65cb)

`alharmony-combined-linux-x64-24b65cb.tar.zst` contains both `alharmony-ops` and `alsessionfsd`. It is the current developer preview for standalone SessionFS composition, partition-aware workspace match, workspace leases, `project.sync`, task-local build cache, and `workspace.gc maxBytes` quota.

### GitHub release validation

The current combined Linux asset was download-back validated from GitHub Release on hwlinux: SHA matched the manifest, both binaries extracted and started, and workspace partition match plus lease/GC dry-run succeeded.

## Combined real Btrfs SessionFS fast-fork preview (218ce52)

`alharmony-combined-linux-x64-218ce52.tar.zst` supersedes `24b65cb` as the
current combined Linux-x64 developer preview. `alsessionfsd` now owns a real
Btrfs subvolume `session.create` / `session.fork` lifecycle plus explicit
portable fallback, while `alharmony-ops` prepares initial task roots through
SessionFS and propagates `backend`, `fallback`, and `copyOnWrite` evidence.

The stripped release binaries were rebuilt from a clean GitHub clone at
`218ce52f27ce6b1a629fe95c2f680bdd309d284d`. A disposable Docker-owned Btrfs
image proved `harmony.task.prepare -> harmony.task.fork` with prepare 2,247 us
and fork 8,727 us, `copiedFiles=0`, `copiedBytes=0`, child receipt isolation,
and parent/child write isolation. A 10,000-file x 4 KiB comparison measured
median 44,143 us for Btrfs versus 343,540 us for copy-tree, about 7.78x faster.
Portable ext4 fallback and storage-root symlink confinement were also validated
against the same stripped release binary.

### GitHub release validation for 218ce52

The immutable package/manifest, current aliases, and `2b544d5` immutable
channel/offline indexes were published to GitHub Releases `alharmony` and
`aloffline`. hwlinux then downloaded the current package, manifest, channel
index, and offline index only from GitHub into
`/tmp/alharmony-github-release-smoke-linux-20260904134339`. The package was
389,602 bytes with SHA256
`0d854c293f76ea3f16c55c61091fc817523a2e574c38e0516e5dea0280010352`;
the manifest, channel current asset, offline current asset, and all five
embedded payload checksums agreed. The binaries extracted from that downloaded
package then passed the real Btrfs composed E2E again: prepare 2,194 us, fork
8,523 us, `copiedFiles=0`, `copiedBytes=0`, CoW true, no fallback, independent
child receipts, and parent state unchanged after a child write.
