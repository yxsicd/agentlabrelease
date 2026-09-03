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
