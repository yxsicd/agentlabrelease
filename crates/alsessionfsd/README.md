# alsessionfsd

Standalone AgentLab SessionFS preview service. This crate owns generic session
storage fork/copy semantics and intentionally does not know Harmony, OHPM,
Hvigor, HAP, or build receipts. The first backend is safe copy-tree; future
backends can use Btrfs/SessionFS snapshots while preserving the same narrow
contract.

```text
alsessionfsd serve --bind 127.0.0.1:19780
GET /health
GET /capabilities
GET /v1/sessions/fork?parentRoot=...&childRoot=...&include=workspace,artifacts,state,cache&reset=receipts,tmp
```

## Composition E2E status

hwlinux clean-clone E2E for `db77da4` proved independent composition with
`alharmony-ops`. `alsessionfsd` handled the fork backend, while `alharmony-ops`
refreshed child build-state and delivered an inherited build-cache hit. The
sessionfs fork step copied 82 files / 622,987 bytes in 5,322 us backend time
and 13.912 ms through the Harmony service path; child inherited cache hit was
0.843 ms.
