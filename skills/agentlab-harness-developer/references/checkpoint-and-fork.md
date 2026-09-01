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

For standard sandbox control tools, the outer Harness Session identity is the
authority. Do not send tenant or owner identity inside tool arguments. Older
preview servers may also require the same Session id inside the tool-specific
arguments; treat that as a version-qualified transport compatibility detail,
not a second identity authority.

Prove a fork with postconditions, not only a successful response: the child
must expose the parent cut state, must exclude parent changes after the cut,
and must continue independently. Record whether the participant was fresh,
native-preserved, or replaced. A successful fresh-Agent fork does not qualify
native Agent session restoration.

Reconcile an uncertain continuation before retrying. A failed mutation can
still advance the child with an audit-only commit, so read the child Git ref and
the expected file at that exact ref first. Retry only from the reconciled head,
then prove the child content and its absence from the exact parent cut.
