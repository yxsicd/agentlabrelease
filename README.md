# AgentLab Harness releases

Source-free public developer releases for AgentLab, an evaluation Harness for
running, observing, checkpointing, forking, and comparing replaceable Code
Agents.

Current runtime candidate: `candidate-20260912-c22b7bfd-linux-x64`.
The historical environment-kit preview remains `v0.1.0-alpha.9`.

The current lightweight aggregate candidate is `v0.1.0-alpha.12`. It binds
release-method source commit `4a365104cfd74af4c648f83ecb21d87ea3a9e787`
to 14 already-published immutable components and all 22 registered payload and
descriptor assets without rebuilding or uploading any unchanged binary. It
remains a developer-preview candidate until tagged clean-install and
release-bound Linux-emulator acceptance are retained. The acceptance plan and
receipt workflow is documented in [the immutable Release Graph](docs/release-graph.md);
older emulator evidence cannot qualify a newer closure.

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
- Use [revision-fenced multi-repository analysis](docs/multi-repository-analysis.md)
  to derive explicit dependency graphs and non-promoted difficulty candidates.
- Use the [calibrated multi-repository case pipeline](examples/multi-repo-case/README.md)
  to capture a replaceable construction participant, construct a review-required
  proposal, apply a leakage/coverage/stage-separation preflight, bind an explicit
  review, and turn the approved plan into a frozen task with an executable Oracle.
- Use [blind case cuts](docs/blind-case-cuts.md) to create physically separate
  participant and evaluator bundles without publishing private task content.
- Use the [Linux emulator integration](docs/harmony-linux-emulator.md) for the operator-supplied HarmonyOS x86 emulator path.
- Verify downloaded files with `manifest.json`, `provenance.json`, and
  `SHA256SUMS`.

AgentLab does not redistribute Codex, Claude Code, OpenCode, DeepSeek Harness,
or MCPGit. Those remain independently versioned dependencies.

`main` is mutable discovery state. Reproducible consumers must pin an immutable
version tag or full Git commit.
