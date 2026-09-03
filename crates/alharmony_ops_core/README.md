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
