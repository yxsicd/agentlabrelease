---
name: agentlab-harness-developer
description: Design, run, inspect, checkpoint, fork, and compare Code Agent evaluation campaigns using a released AgentLab Harness. Do not use for maintaining AgentLab source or administering production infrastructure.
---

# AgentLab Harness Developer

Use released AgentLab interfaces and receipts to evaluate replaceable Code
Agents. Never assume access to the maintenance repository or an Agent's private
session implementation.

## Start

1. Read [evaluation-model.md](references/evaluation-model.md) before defining a
   task seed or comparison matrix.
2. Read [checkpoint-and-fork.md](references/checkpoint-and-fork.md) before
   selecting fresh-Agent or native-session continuation.
3. Read [observability-and-sql.md](references/observability-and-sql.md) when
   diagnosing difficulty windows or querying captured runs.
4. Use the TypeScript probe before a real Code Agent when validating a new
   environment, capture boundary, or fork path.

## Invariants

- The Harness owns environment and workspace state; the Code Agent is a
  replaceable participant.
- Capture and restore are separate operations. A checkpoint may capture all
  observable state even when a later fork deliberately starts a fresh Agent.
- Bind every run to exact task, environment, Agent, model, adapter, and source
  identities. Do not compare labels such as `latest`.
- Preserve raw LLM and MCP/tool events as analyzable structured data. Redaction
  may remove secrets but must not turn the evidence stream into opaque
  ciphertext.
- Treat a difficulty point as an analysis result with evidence, not simply a
  failed final answer.
- Keep MCPGit and external Code Agent versions independent from AgentLab.

## Minimal qualification order

Run the deterministic TypeScript probe through capture, cut, fork, and continue.
Require exact lineage and trace readback. Then repeat the same task seed with a
fresh real Code Agent. Only after that compare native-session preservation or
additional Agents.

The alpha release does not provide one-command environment deployment. Use an
operator-qualified AgentLab environment and retain its composition receipt with
the campaign evidence.
