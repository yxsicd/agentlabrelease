# alsessionfsd

Standalone AgentLab SessionFS preview service. This crate owns generic session
storage fork/copy semantics and intentionally does not know Harmony, OHPM,
Hvigor, HAP, or build receipts. The service now has a real Btrfs subvolume
snapshot backend while retaining safe copy-tree compatibility.

```text
alsessionfsd serve --bind 127.0.0.1:19780 --backend auto
GET /health
GET /capabilities
GET /v1/sessions/create?root=...
GET /v1/sessions/fork?parentRoot=...&childRoot=...&include=workspace,artifacts,state,cache&reset=receipts,tmp
```

Backends:

- `auto` (default): attempt the Btrfs create/snapshot primitive directly and
  use safe directory/copy-tree fallback when the storage path is not eligible.
- `btrfs-subvolume`: require a Btrfs subvolume and fail closed if snapshotting
  is unavailable.
- `copy-tree`: force the portable compatibility path.

The Btrfs preview accepts top-level `include`/`reset` names only. `auto` falls
back to copy-tree for a more general nested-path request rather than silently
changing its meaning.

Use `--storage-root PATH` in composed deployments to confine both parent and
child task roots to one owned SessionFS root. The Btrfs path snapshots the task
root copy-on-write, then removes parent-only top-level metadata and resets
`receipts/` and `tmp/` so the externally visible fork contract remains the same
as copy-tree. Harmony still rewrites child lineage/build-state after the fork.

`session.create` closes the fast-fork lifecycle: on a Btrfs-owned storage root
it creates the initial task root as a subvolume, while portable storage creates
a normal directory. `alharmony-ops` calls this during `harmony.task.prepare`
whenever the SessionFS backend is selected, so later pool candidates are
snapshot-ready without an out-of-band promotion step.

## Composition E2E status

hwlinux clean-clone E2E for `db77da4` proved independent composition with
`alharmony-ops`. `alsessionfsd` handled the fork backend, while `alharmony-ops`
refreshed child build-state and delivered an inherited build-cache hit. The
sessionfs fork step copied 82 files / 622,987 bytes in 5,322 us backend time
and 13.912 ms through the Harmony service path; child inherited cache hit was
0.843 ms.

The next Linux acceptance target is the existing AgentLab SessionFS companion
shape: a Docker-owned sparse Btrfs image mounted inside the companion, with
task roots materialized as subvolumes under that owned mount. A disposable
hwlinux acceptance using that exact storage shape passed even though the host
root filesystem is ext4 and has no host `btrfs` command.

Final 2026-09-04 acceptance evidence: `harmony.task.prepare` created a Btrfs
parent subvolume in 2,258 us and `harmony.task.fork` created an independent CoW
child in 8,731 us, with `copiedFiles=0`, `copiedBytes=0`, independent child
receipts, and parent data unchanged after a child write. A 10,000-file x 4 KiB
synthetic fork comparison measured Btrfs at 59,564 / 44,145 / 29,714 us versus
copy-tree at 375,047 / 351,586 / 359,699 us: median 44,145 us versus 359,699 us,
or about 8.15x faster.
