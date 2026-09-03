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
