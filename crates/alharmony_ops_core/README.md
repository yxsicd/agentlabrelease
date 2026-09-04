# alharmony_ops_core

Rust-owned Harmony engineering atomic-operation core for AgentLab.

This crate is intentionally the **base layer**.  It atomizes basic Harmony
project/build capabilities and emits typed JSON receipts.  Web2Atomic is an
upper pipeline that may call these atoms; it does not define this layer.

## Source absorption boundary

The first implementation absorbs architecture and contract lessons from
`asrelease` rather than copying the full repository:

- source repository: `https://github.com/yxsorg/asrelease.git`
- primary ref: `origin/main`
- observed commit: `374ab3cf2bdd3c31418997adfdd1aaa13ac8f550`
- relevant paths:
  - `web2atomic/crates`
  - `web2atomic/model-templates/shared/website-operation-harness`
  - `web2atomic/model-templates/shared/framework-runtime-profile`
  - `.agents/skills/asrelease-native-framework`
  - `.agents/skills/asrelease-native-content-cache`

No AGC credential, signing key, generated project, device identity, cookie,
session, or `node_modules` content belongs in this crate or public release.

## P0 operations

- `harmony.env.status`
- `harmony.project.create`
- `harmony.project.verify`
- `harmony.ohpm.install`
- `harmony.build.debug`
- `harmony.artifact.inspect`

The first commit implements a deterministic, dependency-free CLI/library
skeleton with non-destructive command planning for build/dependency operations.
Mutating command execution will be added only after receipt gates are stable.

## Service mode

`alharmony-ops serve --bind 127.0.0.1:<port> --workers <N>` exposes the same P0
operations over a preview HTTP loopback transport:

```text
GET /health
GET /v1/ops/harmony.artifact.inspect?artifact=<path>
GET /v1/ops/harmony.project.verify?projectRoot=<path>
GET /v1/ops/harmony.ohpm.install?projectRoot=<path>&harmonyHome=<path>
```

The current transport is intentionally simple: one request per TCP connection,
`Connection: close`, fixed worker pool, no keep-alive, no batching, and no real
`ohpm`/`hvigor` mutation. hwlinux short-run tests reached roughly 85-88k RPS for
health, 74-77k RPS for `artifact.inspect`, about 63k RPS for `project.verify`,
and about 46.9k RPS for `ohpm.install` plan before the close-connection model
entered a long-tail region. Treat those as preview transport measurements, not
production capacity guarantees.

## Task isolation and backpressure

Service mode supports preview task isolation and explicit backpressure:

```text
alharmony-ops serve   --bind 127.0.0.1:<port>   --workers <N>   --queue-capacity <N>   --task-root <dir>   --max-batch <N>
```

When `--task-root` is enabled, path-bearing operations must include `taskId`,
and `projectRoot` / `artifact` paths must stay under `<task-root>/<taskId>`.
The service rejects missing or invalid `taskId`, path traversal, and cross-task
paths before dispatching the operation. Accepted receipts include task evidence.
When all workers plus the bounded accept queue are full, the service returns
HTTP 503 with `queueFull` instead of silently growing an unbounded queue.

Request-level backpressure is enforced with `--max-active-requests`. This is
more reliable than accept-queue-only backpressure because TCP backlog and accept
scheduling may let a client connect before the service has accepted the socket.
When the active request limit is reached, the service returns HTTP 503 with
`activeRequestLimit`.

## Task lifecycle

Task isolation is now a first-class service lifecycle, not only a path check.
Start the service with `--task-root <dir>`, then prepare one sandbox per atomic
unit:

```text
GET /v1/ops/harmony.task.prepare?taskId=<atom-task-id>
```

`harmony.task.prepare` creates:

```text
<task-root>/<taskId>/task.json
<task-root>/<taskId>/workspace/
<task-root>/<taskId>/artifacts/
<task-root>/<taskId>/tmp/
<task-root>/<taskId>/receipts/events.jsonl
```

When the service is started with `--fork-backend sessionfs
--sessionfs-endpoint <url>`, task prepare first calls SessionFS
`session.create`. On a Btrfs-owned SessionFS root this makes the initial task a
subvolume, so later `harmony.task.fork` can use a true CoW snapshot instead of
copying the workspace tree. Prepare/fork receipts expose `backend`, `fallback`,
and `copyOnWrite`; `auto` remains portable and records any directory/copy-tree
fallback rather than presenting it as a snapshot.

Every path-bearing operation must stay under the task sandbox and writes a
compact receipt event to that task's `receipts/events.jsonl`. Batch requests
validate task scope once and log only the final receipt, preserving high
concurrency while still leaving a task-local audit trail.

## AgentLab infrastructure execution mode

`alharmony-ops` remains an independent Harmony domain service, but production
OHPM/Hvigor execution can now reuse AgentLab's bwrap infrastructure instead of
starting toolchain processes directly:

```text
alharmony-ops
  -> agentlab-domain-sandboxd
     -> existing AgentLab bounded bwrap runtime
```

Start `agentlab-domain-sandboxd` with one shared task root:

```text
SANDBOX_DOMAIN_TASK_ROOT=/var/lib/alharmony/tasks \
agentlab-domain-sandboxd
```

Then configure the Harmony service:

```text
alharmony-ops serve \
  --task-root /var/lib/alharmony/tasks \
  --fork-backend agentlab-sessionfs \
  --sandbox-endpoint http://127.0.0.1:18091
```

For authenticated composition, add `SANDBOX_REQUIRE_AUTH=1` and
`SANDBOX_INTERNAL_TOKEN` to the domain sandbox and pass the same credential to
`alharmony-ops` through a mode-0600 `--sandbox-token-file`. The token value is
never placed in the operation receipt.

The private domain endpoint accepts only `taskId`, fixed stage, generated
command, explicit workspace-relative writable paths, and timeout. It never
accepts a physical task root, MCPGit Owner/Session identity, or arbitrary
AgentLab workspace operation. The daemon exposes no file/Git/MCPGit routes and
does not start AgentLab Runtime, Harness, LLMGW, or an Agent brain. Current
stages are:

```text
harmony-ohpm
harmony-build
```

Both stages fail closed without explicit writable paths. `alharmony-ops`
requires `projectRoot` to be below `<task-root>/<taskId>/workspace`, converts
that path to `/workspace/<relative-project>` inside bwrap, and accepts a result
only when the response proves `sandboxed=true` and `executor=bwrap`.

When `--sandbox-endpoint` is configured, service startup performs a bounded
readiness check and requires the exact `agentlab-domain-sandboxd` readiness
contract: bwrap ready, domain task root configured, and MCPGit not required.
With `--fork-backend agentlab-sessionfs`, startup additionally requires
`sessionfsConfigured=true`, `sessionfsReady=true`, and
`storageBackend=agentlab-sessionfs-uds`. Task prepare/fork are then delegated
to the same private infrastructure service; `alharmony-ops` never receives
Session/Attempt/Capsule/fence or prepared-mount identities.
Startup or execution failure never falls back to direct `Command::new`.
Omitting `--sandbox-endpoint` retains the older local-direct path only for
explicit compatibility/developer use.

Hermetic Harmony composition also provides an immutable pnpm 10.28.2 helper
seed at `/opt/harmony-seed/hvigor-wrapper-tools`. Sandboxed builds set
`HVIGOR_USER_HOME=/runtime/deps/hvigor-user-home`, link that user home's
`wrapper/tools` to the immutable seed, and force npm offline. Mutable Hvigor,
pnpm-store, and project caches therefore live in the task's `runtime-deps`
scope and are inherited by SessionFS Fork; helper package installation is not
performed in a build request. Missing or conflicting seed state fails closed.

The first complete hwlinux composition E2E is retained at
`/tmp/alharmony-agentlab-infra-e2e-20260904`. It used a Docker-owned loopback
Btrfs root, standalone `alsessionfsd`, authenticated
`agentlab-domain-sandboxd`, the real Harmony SDK, and `alharmony-ops`.
Unauthenticated readiness returned 401. Parent OHPM and build ran through
bwrap, Btrfs fork copied zero files/bytes, the child inherited the build cache,
a child-only source patch rebuilt through bwrap, and the parent source/HAP
remained unchanged. Observed timings were 1.037 s for OHPM, 9.154 s for the
parent build, 51.560 ms for the Btrfs fork, and 9.142 s for the child rebuild.
Parent and child artifact fingerprints differed only after the child patch.
These are dated developer-preview measurements, not general performance
guarantees. Repeated hermetic acceptance subsequently exposed that a cold
Hvigor user home tries to install `pnpm@10.28.2`; with outer networking disabled
that request correctly timed out. The final corrected evidence at
`/tmp/alharmony-phase1-seeded-e2e-20260904/result.json` uses the immutable seed
above and outer `--network none`: parent/child builds were about 7.06 s each,
Fork was 20.406 ms with zero copied files/bytes, both cache-hit checks passed,
both HAPs were 14,438 bytes, and build stdout contained no runtime pnpm install.
A suspected lingering Hvigor process was also disproven as a `pgrep -f`
self-match by a retained process-tree diagnostic; no Node/Hvigor process
remained after the completed build.

The production storage migration is closed. `--fork-backend agentlab-sessionfs`
uses `agentlab-domain-sandboxd` as the private facade over mature
`agentlab-sessionfsd` UDS. Root task prepare performs Create+Prepare; child Fork
performs Snapshot+Verify+Clone+Prepare. The prepared SessionFS mounts are
projected into the stable task-relative filesystem contract and are also used
directly by bwrap. No copy-tree or HTTP SessionFS fallback is allowed in this
mode.

Final real-SDK evidence is
`/tmp/alharmony-mature-uds-e2e-20260904/result.json`: parent prepare 148.668 ms,
mature UDS Fork 280.213 ms with zero files/bytes copied, OHPM 1.245 s, parent
build 8.614 s, child rebuild 7.872 s, parent and inherited-child cache hits,
independent receipts, parent isolation, and exact Btrfs ancestry
parent->snapshot->child. Parent/child HAPs were 14,404 / 14,403 bytes with
distinct SHA256 after the child-only patch. The outer container used
`--network none`, no request-time pnpm installation occurred, and no
`alsessionfsd` preview process was present.

## Task-isolated E2E build preview

Inside service task isolation, `harmony.project.create` can materialize a minimal
Harmony Stage-mode project when called with `materialize=true`, and
`harmony.ohpm.install` / `harmony.build.debug` can execute with `execute=true`.
`build.debug` uses unsigned CI-style packaging:

```text
hvigorw --no-daemon --no-parallel --no-type-check --analyze=false   --mode module -p product=default assembleHap
```

A hwlinux E2E run using the real Harmony SDK completed task prepare, project
create, verify, `ohpm install`, unsigned HAP build, artifact inspect, then two
source edits and rebuilds. Timings were about 8.30 s for the initial full flow,
6.88 s for edit-1 verify/build/inspect, and 6.94 s for edit-2
verify/build/inspect. This remains developer preview: execute mode is allowed
only in task isolation and still needs stronger process timeout/resource
controls before production use.

## Memory-backed task roots

Task roots can be placed on tmpfs, for example `/dev/shm`, to keep the generated
project, build outputs, task temp directory, and receipt log memory-backed. A
hwlinux A/B test showed this is viable but not a major win for the minimal E2E
project: `/dev/shm` saved about 1.3% on one edit/build loop and about 0.15% on
the next, while the initial full flow was about 0.2% slower. Use tmpfs as an
optional per-task policy when the host disk is slow or projects are IO-heavy;
for the current minimal project, Hvigor/ArkTS/Node execution dominates.

## Build optimization notes

For the minimal task-isolated E2E project, moving only the task root to tmpfs is
not enough. Measured no-op rebuilds are about 1.86 s, while source-edit rebuilds
are about 6.9 s. `--parallel` does not help no-op rebuilds, and
`--optimization-strategy performance` did not improve source-edit rebuilds in
hwlinux tests. Daemon mode would be attractive for hot builds, but it currently
fails with Node/chokidar `EMFILE` watcher pressure, so the safe execution default
stays `--no-daemon --no-parallel --no-type-check --analyze=false`.

## Task-local build cache

`harmony.build.debug execute=true` now computes a conservative task-local build
input fingerprint before launching Hvigor. The fingerprint covers the generated
project configuration, `AppScope`, `entry/src`, package/profile files, and the
SDK wrapper/version inputs used by the build. After a successful unsigned HAP
build, the service writes `<task-root>/<taskId>/state/build-state.json` with the
input fingerprint and last artifact fingerprint. A later unchanged build can
return a read-only cache-hit receipt pointing to the existing unsigned HAP
instead of starting Hvigor. Any source/config/SDK-wrapper/artifact mismatch falls
back to the real no-daemon build.

## Project patch atom

`harmony.project.patch` applies a precise task-scoped text delta to an existing
project workspace instead of re-materializing the project. It requires
`projectRoot`, project-relative `path`, non-empty `find`, and optional
`replace`/`replaceAll=true`. The target path must remain under the task-owned
project root. Receipts report whether the file changed, occurrence count,
project partition (`arkts`, `resources`, `profile`, `dependencies`,
`build-script`, or `other`), and before/after file fingerprints. This gives
upper agents a stable delta channel for preserving Hvigor incremental state.

## Incremental delta strategy

The service now has a precise delta lane via `harmony.project.patch`, but real
hwlinux tests show no-daemon Hvigor still rebuilds the minimal project in about
6.85-7.10 s after resource or ETS changes. Use stable task/workspace affinity,
patch coalescing, and build-cache short-circuiting as the first line of defense.
Future work should partition build fingerprints into ArkTS, resources, profiles,
dependencies, build scripts, and SDK wrappers so the scheduler can batch or skip
builds based on what actually changed.

## Task fork atom

`harmony.task.fork` adapts the AgentLab Session Fork idea to Harmony workspaces.
It takes `parentTaskId` and child `taskId`, copies the parent task's
`workspace/`, `artifacts/`, `state/`, and `cache/` into a new child sandbox,
creates a fresh child `receipts/` log, and rewrites task-local build-state paths
from the parent root to the child root. The child can then apply
`harmony.project.patch` deltas and reuse inherited build fingerprints/artifacts
without mutating the parent. The current fallback strategy is normal copy-tree;
future SessionFS/Btrfs fork should replace the copy implementation where
available.

## Session Fork workspace reuse

The preferred reuse model is Session Fork, not direct mutable sharing. A pool
selects a parent task whose workspace/build state is closest to the incoming
request, then `harmony.task.fork` creates a child task from that parent cut.
The child inherits workspace, artifacts, state, and cache; `harmony.project.patch`
applies the new delta; `harmony.build.debug` then either hits inherited cache or
performs a real rebuild and updates child state. hwlinux E2E proved inherited
build cache hit at about 0.974 ms after fork, while parent remained unchanged.
The current backend is copy-tree fallback; SessionFS/Btrfs fork should replace
it when available.

## Independent SessionFS composition

SessionFS should be composed as an independent service, not embedded as a required AgentLab Harness instance. `agentlab-sessionfsd` owns storage fork/snapshot/quota/GC. `alharmony-ops` owns Harmony project/build atoms, receipts, build-state, and artifact inspection. `harmony.task.fork` remains stable and can use `sessionfs` when configured or `copy-tree-fallback` when standalone.

## SessionFS backend adapter

`harmony.task.fork` now supports a pluggable fork backend. The standalone mode
uses `copy-tree`; composition mode can call an independent `alsessionfsd` through
`--fork-backend sessionfs --sessionfs-endpoint http://127.0.0.1:<port>`. The
public Harmony atom remains `harmony.task.fork`; after the storage fork,
`alharmony-ops` still rewrites paths and refreshes child build-state/fingerprints
before allowing inherited cache hits.

## Project sync atom

`harmony.project.sync` is the byte-level delta lane for full staged project
packages. Both `projectRoot` and `sourceRoot` must stay inside the same task
sandbox. The operation scans `sourceRoot`, skips build/cache directories, uses
content fingerprints so staging paths do not cause false positives, copies only
changed files, optionally deletes target-only files with `deleteMissing=true`,
and writes `state/dirty-partitions.json` for scheduler policy. It preserves
build outputs, `.hvigor`, `oh_modules`, `node_modules`, and `.git` by default.

## Workspace index and match preview

`harmony.workspace.index` scans the task root for reusable candidates with
`state/build-state.json`. `harmony.workspace.match` ranks candidates for a given
`inputFingerprint`, with optional `inputFileCount` and `inputBytes` hints. This
is the first service-side workspace pool index: exact fingerprint matches are
preferred, and the result points the scheduler to `harmony.task.fork`.

## Sync + pool E2E status

`harmony.project.sync` plus independent SessionFS composition was verified on
hwlinux with the real Harmony SDK: forked child inherited parent cache in 0.835
ms, full staged-package sync copied 3 files, deleted 1 stale file, skipped 16
files, and completed in 1.501 ms wall time before a real child rebuild. The
first `harmony.workspace.index/match` preview was also Linux-smoked and selected
an exact fingerprint parent from a two-candidate pool.

## Pool safety preview

Workspace reuse now has three safety layers: partition-aware `workspace.match`, short-lived `workspace.lease` before fork, and `workspace.gc` that protects leased tasks and the newest `keepLast` candidates. Dry-run GC is read-only; destructive GC requires `execute=true`.

## Workspace GC quota

`harmony.workspace.gc` supports `maxBytes` in addition to `keepLast` and `maxDelete`. It computes total candidate bytes, plans oldest unleased deletions outside the newest keep window, reports `plannedFreedBytes` and `projectedBytesAfterPlan`, and only deletes with `execute=true`.
