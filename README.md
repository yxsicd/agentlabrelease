# AgentLab Harness releases

Source-free public developer releases for AgentLab, an evaluation Harness for
running, observing, checkpointing, forking, and comparing replaceable Code
Agents.

Current runtime candidate: `candidate-20260912-26008e36-linux-x64`.
The historical environment-kit preview remains `v0.1.0-alpha.9`.

Component-based publication now uses [reference-only environment releases](docs/component-publication.md).
The [26008e36 Linux x64 candidate](release/candidates/26008e36-linux-x64/publication.json)
references independently published packages and records its remaining acceptance
gates. It does not supersede the current developer preview or stable channels.

GitHub Actions verifies public installation and a [preset Mock Agent campaign](examples/mock-agent/README.md):
multi-turn changes, failure detection, recovery after service restart, seed Fork
and parent isolation, on copy-tree and Btrfs. This portable CI tier is distinct
from full Session/TableGit qualification and real-agent SWE evaluation.

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
