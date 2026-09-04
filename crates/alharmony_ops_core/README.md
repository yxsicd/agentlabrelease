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

Every path-bearing operation must stay under the task sandbox and writes a
compact receipt event to that task's `receipts/events.jsonl`. Batch requests
validate task scope once and log only the final receipt, preserving high
concurrency while still leaving a task-local audit trail.

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
