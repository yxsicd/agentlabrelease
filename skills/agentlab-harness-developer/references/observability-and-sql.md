# Observability and SQL

Retain structured records for campaigns, attempts, turns, LLM requests and
responses, token usage, MCP/tool calls, checkpoints, fork lineage, outcomes,
and difficulty adjudications. Large payloads belong in content-addressed
artifacts referenced by typed rows.

A difficulty-window query should identify bounded regions with signals such as
repeated equivalent tool calls, repeated errors, non-progressing workspace
state, budget burn without acceptance progress, or recovery after a fork.

Use revision-pinned TableGit Relation SQL for reproducible joins. Use executable
Rust or WAsmC analysis only when its publication, capability allowlist, input
tables, generation, output schema, and invocation log have all been admitted.
Wait for asynchronous invocation logs to flush before changing route authority.
