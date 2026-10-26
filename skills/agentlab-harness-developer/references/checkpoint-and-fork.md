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
arguments; those historical previews are not the current consumer contract.
Admit only the exact deployed capability contract; a missing supported restore
path blocks continuation rather than selecting an older compatibility path.

Prove a fork with postconditions, not only a successful response: the child
must expose the parent cut state, must exclude parent changes after the cut,
and must continue independently. Record whether the participant was fresh,
native-preserved, or replaced. A successful fresh-Agent fork does not qualify
native Agent session restoration.

Reconcile an uncertain continuation before retrying. A failed mutation can
still advance the child with an audit-only commit, so read the child Git ref and
the expected file at that exact ref first. Retry only from the reconciled head,
then prove the child content and its absence from the exact parent cut.

## Lost response and independent-start qualification

A timed-out Fork response leaves its effect unknown. Preserve the original
request and client correlation; do not repeat creation to obtain another reply.
Use the deployed contract's exact original operation/session readback to prove
its durable child, parent/base binding and Ready revision. A derived name is only
a lookup selector. Never derive it from an unrelated source checkout or treat it
as proof; version and deployment identity must match actual runtime evidence.
A child-list projection is not proof of absence when known existing children are
also missing. Record that reader's coverage limit and retain the unknown until
authoritative operation/resource evidence settles it.

A selected portable source point and the complete parent workspace can contain
different material. Before a fresh independent participant, inventory actual
readable files and native context: old feedback, verification reports, prior
solutions and evaluator assets must not silently travel with a code-only seed.
Keep supplied parser/scaffolding provenance explicit, separate construction help
from new participant assistance, and verify isolation before independent grading.
Use an admitted projection/materialization within the new owned child; preserve
the parent and original evidence. No deletion of unrelated homes or workspaces.
