# Harmony build service and independent SessionFS composition

Goal: keep `alharmony-ops` independently deployable while allowing it to compose with an independently deployed `agentlab-sessionfsd` for fast workspace forks.

Components:

- `agentlab-sessionfsd`: owns storage roots, snapshot/fork, quota, and GC. It does not understand Harmony, OHPM, Hvigor, or build receipts.
- `alharmony-ops`: owns Harmony task receipts, project patch/sync, build-state fingerprints, OHPM/Hvigor execution policy, and artifact inspection. It does not own storage snapshot internals.
- `workspace-pool`: selects a parent task/session by similarity, leases it, forks it, applies deltas, builds the child, then returns the child as a reusable candidate.

Narrow SessionFS contract:

```text
GET  /health
GET  /capabilities
POST /v1/sessions/create
POST /v1/sessions/fork
GET  /v1/sessions/status
POST /v1/sessions/delete
```

Harmony side keeps the stable public atom:

```text
harmony.task.fork?taskId=<child>&parentTaskId=<parent>
```

Backend choice:

1. use `sessionfs` when configured and healthy;
2. use `copy-tree-fallback` when standalone;
3. do not use writable hardlink sharing unless break-link semantics are proven.

After any storage fork, `alharmony-ops` still refreshes child `build-state.json`, input fingerprint, artifact fingerprint, and receipt lineage before admitting cache hits.

Composition flow:

```text
request -> workspace-pool match -> sessionfs fork or copy fallback -> alharmony task bind -> project.patch/project.sync -> build.debug -> candidate retention/GC
```

Independence boundary: `alharmony-ops` must not require the AgentLab main container, MCPGit credentials, native Agent sessions, or SessionFS internals. SessionFS is a composable acceleration service, not the owner of Harmony build semantics.
