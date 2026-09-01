# Releases

## v0.1.0-alpha.4

Separates the operator-owned runtime/LLM env from descriptor-owned MCPGit
controller configuration. Direct deployment now renders one private 0600 env
from both sources while authorization bytes remain only in read-only secret
mounts. Alpha.3 stopped at this precondition before any `ald00` mutation, so
its composition receipt and large CAS remain reusable.

This preview is built from AgentLab source commit
`91dc77c3f7cd1a2dffb42ae37cfee75aadfd43fe`.

## v0.1.0-alpha.3

Corrects two zero-context installation failures found against alpha.2. The
environment entrypoint now resolves both its packaged root layout and its
source-tree layout, and AIWSL `ald00` inherits the operator-owned `/share/.env`
instead of requiring a nonexistent per-instance file. Alpha.2 stopped before
runtime mutation; its verified composition receipt and large CAS remain valid
and reusable.

This preview is built from AgentLab source commit
`317c2b210c0d313e322e06068ed633497f5a2dc9`.

## v0.1.0-alpha.2

Adds the first repo-free AIWSL `ald00` environment lifecycle. A small
environment kit exposes no-write qualification, receipt-bound installation,
and read-only health verification after the fixed `aldev` composition has been
downloaded and installed by `agentlabctl`.

The baseline remains Agent-neutral: qualify the Harness with the deterministic
TypeScript probe before installing or attaching Codex/OpenCode. The successful
`ald00` instance is intended to be retained for repeated capture, cut, fork,
continue, SQL-mining, and next-dispatch experiments.

This preview is built from AgentLab source commit
`e068ea9dc25e1618e9b1bdf68eadf9a3f173c953`. It targets the existing AIWSL
AgentLab-owned MCPGit service and does not claim a dedicated per-ALD MCPGit
service, Main/Prod promotion, or a general-purpose host descriptor.

## v0.1.0-alpha.1

First public developer preview of the AgentLab evaluation Harness contract.

It publishes the `agentlab-harness-developer` Skill, task-seed and fork
guidance, observability and SQL-analysis guidance, a deterministic TypeScript
probe package, provenance, checksums, and links to the independently published
`agentlabctl` control channel.

The preview is built from AgentLab source commit
`b556444b1bac902b1fdbf309ab24784087a2486c`. The executable MCPGit SQL/WAsmC
canary used MCPGit source commit
`c0c3a53fe68904e017de7505bf47436d068938e5`.

This alpha does not claim a one-command clean environment deployment, a stable
schema, production promotion, or transparent restoration of every Code Agent's
private native session.
