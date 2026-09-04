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
