# Checkpoint and fork

The portable checkpoint baseline contains Harness-owned state: workspace and
filesystem changes, task state, environment identity and deltas, MCP/LLM trace
references, tool events, budgets, and lineage.

Fork policy is selected independently:

- `fresh-agent`: restore Harness state and attach a new empty Agent session;
- `preserve-native`: also restore the adapter-qualified native Agent session;
- `replace-agent`: restore Harness state and attach a different Agent.

Do not delete unrelated Agent homes merely to obtain isolation. Prefer a new
explicit mount or identity when old state cannot influence the participant.
Native-session restoration must fail closed when version, format, or adapter
qualification does not match.
