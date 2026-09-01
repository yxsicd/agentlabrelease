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

## Source authority

Maintain an AgentLab-owned experiment index. After a capture commit has been
read back successfully, register at least its Session/Attempt identity, managed
repository id, exact 40-hex revision, schema generation, trace digest, and fork
lineage. SQL source selection reads this index and binds the recorded exact
revisions.

Key the current-state row by managed Session repository id, not only by logical
Session id. Derived comparison repositories may share a logical seed/Session
identity while remaining distinct SQL sources. A new capture revision updates
that repository's current row; Git history preserves earlier index states.
Derive TableGit transaction and operation UUIDv5 values deterministically from
repository identity and row digest so uncertain retries can replay exactly.

Do not use MCPGit `repository.list` as dynamic Session discovery. It
intentionally exposes a bounded configured repository registry. Do not scan
MCPGit storage directories either: an on-disk directory is not evidence that a
managed repository is active or queryable.

Capture commit and index registration are two idempotent steps, not a claimed
cross-repository transaction. Recover an uncertain outcome by exact readback:
first confirm the captured revision and digest, then confirm or repair the
corresponding index row.

## Query receipt

For every difficulty query retain the selected repository ids and exact
revisions, SQL/query digest, binding count, result count, truncation state,
output bytes, and execution receipt. A query against deterministic TS fixture
data qualifies the analysis boundary; it must not be described as analysis of
a real Gateway LLM trace. The full flywheel is qualified only when the actual
run is captured, indexed, selected, and queried without manual source assembly.

The alpha.5 retained-instance qualification has closed automatic exact capture
readback, idempotent index registration, index-derived source selection, and
cross-repository SQL for both the deterministic real-Bun fixture and a real
Gateway LLM trace bound to a real Git Session. The real trace completed four
rounds, three Participant MCP calls, one provider call, and 14 normalized
events; the indexed SQL query selected three repositories with six exact
bindings and returned three difficulty candidates. Re-registering the live
capture replayed without advancing the index.

This does not yet make difficulty-to-fork dispatch automatic. The selected
window must still resolve an exact Session/workspace cut, be adjudicated, and
feed the fork request without maintainer shell assembly. Keep that distinction
when reporting flywheel completeness.
