# AgentLab Harness releases

Source-free public developer releases for AgentLab, an evaluation Harness for
running, observing, checkpointing, forking, and comparing replaceable Code
Agents.

Current runtime candidate: `candidate-20260912-c22b7bfd-linux-x64`.
The historical environment-kit preview remains `v0.1.0-alpha.9`.

Component-based publication now uses [reference-only environment releases](docs/component-publication.md).
Tagged releases additionally use an [immutable Release Graph](docs/release-graph.md)
to bind exact component bytes, schema compatibility and target qualification
before installation. `generic-linux` and `wsl2` target descriptors live under
`release/targets/`; `bluebwsl` is an explicit WSL2 alias rather than an AIWSL
substitute.
The [c22b7bfd Linux x64 candidate](release/candidates/c22b7bfd-linux-x64/publication.json)
references independently published packages and records its remaining acceptance
gates. It does not supersede the current developer preview or stable channels.

GitHub Actions runs the same [executable demos](examples/README.md) you can run
locally: public component installation, HTTP/MCP/Website Skills discovery and
mapping, real TableGit Session recovery, and a preset Mock Agent campaign on
copy-tree and Btrfs. Each retains its exact evidence and states its coverage;
these separate checks do not qualify the complete whitebox evaluation chain.

- Choose benchmark maintenance or operations using [`skills/registry.json`](skills/registry.json).
- Start with [`skills/agentlab-harness-developer/SKILL.md`](skills/agentlab-harness-developer/SKILL.md).
- On AIWSL, start the current preview with
  `scripts/agentlab-harness-quickstart.sh online-install`.
- Read [`RELEASES.md`](RELEASES.md) for version scope and limitations.
- Verify downloaded files with `manifest.json`, `provenance.json`, and
  `SHA256SUMS`.

AgentLab does not redistribute Codex, Claude Code, OpenCode, DeepSeek Harness,
or MCPGit. Those remain independently versioned dependencies.

`main` is mutable discovery state. Reproducible consumers must pin an immutable
version tag or full Git commit.
