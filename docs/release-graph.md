# Immutable Release Graph

AgentLab separates **release identity**, **composition identity**, **control identity**, and **target qualification**. A tagged developer release must not reconstruct those identities from mutable channels at install time.

## Release closure

A tagged release uses `agentlab.release_closure.v1` as its replay authority. The closure binds:

- exact AgentLab and LLMRS source revisions;
- immutable control, composition, runtime, Harmony, MCPGit and tools assets;
- SHA-256 and byte size for every asset;
- the required control API, environment-lock, composition-receipt and component-graph schemas;
- contract generations such as `mcpgit.session-template-contract`;
- target support status.

A tagged closure must never reference `aldev`, `almain`, `alprod`, `latest` or `current` payloads. Those names are discovery/development channels, not release authority.

Assets referenced by an immutable closure are retention authority. They must not be deleted merely because a mutable channel no longer uses them.

OCI image identity is explicit: the manifest digest and config digest are different facts. A host-local Docker image ID is not a substitute for either.

## Target descriptors

Public target descriptors live in `release/targets/`.

`generic-linux` and `wsl2` are explicit targets. `bluebwsl` is an alias of the WSL2 target and is not treated as AIWSL. WSL2 is currently **experimental** and defaults to:

- self-hosted MCPGit;
- isolated MCPGit data and SafeGit credentials;
- loopback-only initial exposure;
- explicit host dependency, memory and port preflight;
- independent SessionFS lifecycle;
- ordered MCPGit -> SafeGit -> SessionFS -> main-runtime deployment;
- cold/Docker/WSL restart qualification.

A target becomes `qualified` only after those gates pass against the exact immutable release closure.

## Compatibility before install

Installation begins with a compatibility handshake, not download or mutation. The control must prove it understands the closure's lock, receipt and component-graph schemas before acquisition starts. Unknown schema generations fail closed with the exact unsupported identity.

The normal lifecycle is:

```text
install-plan -> qualify -> install -> layered health -> rollback
```

Layered health is stronger than a single process `/health`; target metadata enumerates the dependency planes that must be checked.

## Historical BlueB regressions

Public release validation permanently covers the failure classes discovered by the BlueB deployment:

1. mutable-channel dependency from a tagged release;
2. controller/receipt schema drift discovered only during deployment;
3. deletion of an immutable historical asset;
4. ambiguous Docker/OCI image identity.

These are release-system failures, not one-off deployment quirks. New release tooling must keep them fail-closed.
