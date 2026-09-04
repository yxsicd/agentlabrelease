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
GET  /v1/sessions/create
GET  /v1/sessions/fork
GET  /v1/sessions/status
POST /v1/sessions/delete
```

Harmony side keeps the stable public atom:

```text
harmony.task.fork?taskId=<child>&parentTaskId=<parent>
```

Backend choice:

1. use `sessionfs` when configured and healthy;
2. inside `alsessionfsd`, prefer a real Btrfs subvolume snapshot when the
   selected parent task root is a SessionFS-owned subvolume;
3. use `copy-tree-fallback` when standalone or when the parent is not a Btrfs
   subvolume;
4. do not use writable hardlink sharing unless break-link semantics are proven.

The standalone service supports `--backend auto|copy-tree|btrfs-subvolume` and
optional `--storage-root PATH`. Production composition should supply an owned
storage root so arbitrary host paths cannot be admitted. The storage root is
canonicalized at startup and request paths are rejected if they traverse a
symlink. `auto` attempts the Btrfs primitive directly and falls back only after
the operation fails, avoiding probe-process overhead while remaining fail-safe.
A Btrfs snapshot is pruned back to the same public fork contract
(`workspace/artifacts/state/cache` inherited; `receipts/tmp` reset), so
Harmony-side lineage and build-state refresh remain unchanged.
The SessionFS receipt reports both `fallback` and `copyOnWrite`, and
`alharmony-ops` propagates those fields into `harmony.task.fork` evidence so an
operator can distinguish a true snapshot from a compatibility copy.

`harmony.task.prepare` now participates in the same storage lifecycle. With
`--fork-backend sessionfs`, it asks `alsessionfsd` to create the task root
before materializing the Harmony sandbox. A Btrfs storage root therefore makes
the initial task a subvolume; subsequent `harmony.task.fork` can snapshot it
directly. `auto` may fall back to a normal directory and records that fallback
in the prepare receipt rather than pretending the task is snapshot-ready.

On hwlinux, a disposable companion-shaped sparse Btrfs image validated the full
`task.prepare -> workspace write -> task.fork` path. Final measurements were
2,258 us for SessionFS-backed prepare and 8,731 us for fork; both receipts
reported `backend=btrfs-subvolume`, `copyOnWrite=true`, and `fallback=false`.
The child inherited workspace/cache state, did not inherit the parent receipt
log, and remained write-isolated from the parent. A 10,000-file x 4 KiB
synthetic comparison produced median 44,145 us Btrfs versus 359,699 us
copy-tree, about 8.15x faster.

After any storage fork, `alharmony-ops` still refreshes child `build-state.json`, input fingerprint, artifact fingerprint, and receipt lineage before admitting cache hits.

Composition flow:

```text
request -> workspace-pool match -> sessionfs fork or copy fallback -> alharmony task bind -> project.patch/project.sync -> build.debug -> candidate retention/GC
```

Independence boundary: `alharmony-ops` must not require the AgentLab main container, MCPGit credentials, native Agent sessions, or SessionFS internals. SessionFS is a composable acceleration service, not the owner of Harmony build semantics.
