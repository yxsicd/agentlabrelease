---
name: agentlab-codebase-analysis
description: Maintain evidence-backed semantic knowledge of a target repository for benchmark construction.
metadata:
  agentlab-layer: method
  agentlab-role: maintenance
  agentlab-stage: repository-analysis
  agentlab-ownership-plane: repository-native
---

# Codebase analysis maintenance

Read the pinned source and its existing maintainer guidance. Identify project boundaries, architecture, build/test entrypoints, behavior contracts, state transitions and cross-file responsibilities. A strong construction Agent may do this work; it is separate from the assessed Agent.

Maintain stable `maintainer_skills` rows containing Markdown guidance and explicit source/fact references. They describe how to maintain the target codebase, not how to administer AgentLab. Revisit the same row when knowledge changes so Git history retains the semantic delta.

This is a hard prerequisite for real-source case mining. Every pinned repository
MUST have revision-matched instance Skills that cover architecture, build/test
entrypoints, behavior contracts, state transitions, cross-file responsibilities
and known gaps. Whole-source parser success alone is not semantic coverage. Use
the executable gate in [the normative pipeline](../../docs/maintainer-skill-gated-case-pipeline.md);
no candidate may enter semantic review without a passing candidate-stage receipt.

Every claim needs a source location or analysis record. Distinguish observed behavior from inferred intent. Use program facts to support the semantic model; do not manufacture dependency edges from prose. Preserve unresolved questions as gaps.

Build knowledge through repeated evidence rounds, not a single repository read.
First freeze the structural scope catalog, then bind revision-matched program
facts, assess universal evidence dimensions, and use the resulting gap queue to
drive the next targeted analysis and Skill refresh. Only an independent
assessment may advance a scope from structural to semantic or maintenance
readiness. Follow [the Maintainer Skill evidence flywheel](references/maintainer-skill-flywheel.md)
and retain every parent assessment digest.

Parallelize bounded scopes, not evidence claims. A batch may share one exact
repository checkout and run up to four scope-isolated construction Agents in
parallel. Each scope keeps its own request, tool budget, proposal, Blob checks
and receipt; the batch advances only when every selected scope passes, one
independent assessment proves the exact aggregate delta, and the resulting
facts can enter the same atomic TableGit transaction. A partial batch writes no
authority rows.

Retain successful independent scope proposals when one peer in a batch fails.
Retry only the failed scopes once, preserve both attempts as evidence, then run
the aggregate hard gate over the successful outputs. If any isolated retry
still fails, stop before the assessment and TableGit transaction; never rerun
successful scopes merely to recover one model or transport tail.
Keep each attempt under a bounded semantic-analysis wall time. The operator
retry replaces any nested transport retry so one unhealthy request cannot
silently consume multiple full time budgets before its peers are released.
Use a shorter operator-proxy request timeout for this bounded semantic lane
than for general assessed runs. It must still retain the upstream response on
normal cancellation, but must not add several hidden minutes after the Agent
supervisor has already terminated an attempt. Enforce both socket-idle timeout
and an absolute upstream deadline; a provider that drips partial bytes must not
reset the total request budget indefinitely.
Before retaining failed or cancelled run evidence, remove transient links to
source checkouts. Preserve prompts, native events, lifecycle receipts and
proposals, but never let an interrupted cleanup cause the artifact uploader to
traverse and package a whole repository.

Spend Agent turns on semantic judgment, not deterministic repository plumbing.
Before each construction turn, the operator must verify the exact HEAD and
provide a complete scope-owned tracked-file inventory with Git Blob identities
and byte counts. The Agent uses that inventory for in-scope discovery and only
invokes Git for a necessary direct cross-boundary relation. Independent tables
at one immutable TableGit revision may be read concurrently; writes, revision
fences, validation and authority promotion remain serialized and atomic.

Use a deep target repository to discover failure modes, then normalize each
verified lesson into the repository-independent method before reusing it. Never
add target repository names, paths, framework commands or special-case scoring
to this method Skill. Require a complete convergence plan, execution-enforced
Agent budgets and an atomic no-write-on-failure boundary as defined by the
flywheel reference. `No eligible scope` is a blocker report, not proof that the
repository is understood.

Route bounded work by capability: source behavior, configuration/asset, or
repository contract. Require only evidence dimensions that the mode can prove;
never fabricate behavior for a non-source scope. Do not solve an oversized
scope by increasing the Agent context budget. Decompose it into complete,
non-overlapping child responsibilities with explicit parent lineage first.
Generate a revision-bound decomposition plan before changing the authoritative
scope catalog. The plan must reconcile the parent's exact Git Tree and source
inventory, assign every tracked file exactly once, cap every candidate leaf,
and retain direct root files through explicit file selectors. Treat generated
directory leaves as structural candidates: merge or rename them only after an
evidence round proves one coherent responsibility. A complete plan changes the
blocker from decomposition work to catalog review; it never promotes the parent
or creates published Maintainer Skills automatically.
The semantic review must assign every structural leaf exactly once, keep each
reviewed responsibility within the same enforced budget, and cite at least two
exact owned Blobs for its responsibility rationale. When one responsibility
combines disjoint selectors, keep `pathBoundary` only as a human navigation
anchor and make `ownershipSelectors` authoritative. Every fact binding, Agent
checkout, candidate path check, materialized Skill and coverage check must use
those selectors; never fake the merge with a common ancestor. Apply a reviewed
replacement first to a new exclusive candidate catalog. Only after exact
revision, Tree, Blob, file-set, count, completeness and overlap checks pass may
an authoritative TableGit transaction replace the parent. Retire every parent
and insert every reviewed child in the same revision-fenced batch, using exact
row versions for deletion. Recompute the independent assessment against the
candidate catalog before that batch; an assessment of the old parent catalog
cannot certify the replacement.
Repository-contract analysis must start from a root-only checkout projection;
the root boundary does not authorize recursively materializing every child.
Treat maturity as evidence composition: a newly accepted semantic fact may move
a scope directly from L1 to L3 when executable operation evidence was already
bound. This is valid assessment convergence, not automatic case promotion.

Use [program analysis](../agentlab-program-analysis/SKILL.md) for structure and [seed extraction](../agentlab-seed-extraction/SKILL.md) to turn grounded knowledge into tasks. Archive searches and generic TableGit analysis requests, exact input cuts and complete results in `program_facts`.

Develop in TableGit. Export a fixed cut with the existing [three-table workflow](../../examples/knowledge-seed/README.md), one stable JSONL per table. Rebuild every non-authoritative catalog summary from that exact export and fail if its repository identity or coverage totals drift; never publish a summary hash carried from the pre-transaction snapshot. Release files are publication snapshots, not a second live authority.

Produce target-instance guidance for this stage as TableGit Skill rows,
separate from the structured facts/tasks/results. Follow
[the two-layer methodology](../agentlab-skill-methodology/SKILL.md) for
method/source lineage and independent layer/role fields.
