# Maintainer-Skill-gated case pipeline

This contract is mandatory for every real-source AgentLab case. It turns the
maintainer knowledge design into a fail-closed production boundary rather than
an optional knowledge-seed experiment.

## Required order

```text
exact source set
  -> whole-repository inventory and parser receipt
  -> repository process Maintainer Skills
  -> complete scope-level Maintainer Skill partition of the source tree
  -> revision-bound program facts and archived analyses
  -> explicit Skill/fact/analysis candidate binding
  -> reviewed multi-candidate cohort
  -> task construction
  -> independent Oracle and variant calibration
  -> frozen evaluation case
  -> assessed attempts and round assessment
  -> feedback into a later knowledge cut and generation round
  -> repeat until an evidenced scoped convergence or blocker
```

The order is normative. A feedback signal may choose the next source set or
rank already grounded candidates, but it MUST NOT replace repository knowledge,
program analysis, independent calibration, or cohort review.

Case generation is therefore a lineage, not a one-shot job. Every pass writes a
`case_generation_rounds.jsonl` row conforming to
[`case-generation-round.schema.json`](../schemas/case-generation-round.schema.json).
The row binds its exact knowledge cut and latest Maintainer Skill refresh,
measures behavior/Oracle readiness, preserves candidate outcomes and returns
gaps to the next round. An empty or unsuccessful first cohort is retained as a
baseline and MUST NOT be called convergence.

## Ownership planes and refresh rounds

Repository-native Maintainer Skills live under `skills/` and maintain AgentLab
itself. They are reviewed and released with this repository. Target-operations
Maintainer Skills describe repositories used as test objects. They live in a
revision-bound knowledge cut and must not be mistaken for instructions that
govern AgentLab source maintenance.

Target-operations knowledge is iterative. A first read establishes a structural
baseline; later rounds revisit weak behavior contracts, cross-file or
cross-language relations, state transitions, build/test evidence, and Oracles.
Each row in `maintainer_skill_refresh_rounds.jsonl` binds the exact output table
hashes, its parent round, coverage, changes, residual gaps, and a
`continue | converged | blocked` decision. New rounds append to the lineage;
they do not silently rewrite the prior round. The hard gate accepts only a
contiguous lineage whose latest round binds the current Skill and fact tables.

## SkillsGit materialization boundary

The target-operations JSONL tables are the evidence and lineage authority; they
are not, by themselves, a repository-native Maintainer Skill Tree. Final
materialization follows one pinned SkillsGit revision and produces `AGENTS.md`,
`.agents/HANDOFF.md`, `.agents/skills.registry.yaml`, and
`.agents/skills/*/SKILL.md`. A materialized path Skill must contain a trigger,
purpose, repeatable workflow, exact source authority, residual gaps,
verification, and governance boundary. Static L2 semantic evidence must not be
presented as build, emulator, device, performance, or runtime proof.

Materialization is a rebuildable derivative of one exact knowledge cut and one
exact SkillsGit commit. TableGit remains the mutable authority for facts and
refresh lineage. The materialization receipt binds both revisions, enumerates
file digests, records SkillsGit validation, and keeps automatic promotion off.

## Hard requirements

1. Every repository is pinned by URL and 40-hex Git revision.
2. Every repository has instance Skills for `repository-analysis`,
   `program-analysis`, and `seed-extraction` at that exact revision.
3. Every tracked file belongs to exactly one scope-level Maintainer Skill. Each
   scope Skill binds its repository revision, path boundary, responsibility,
   language mix, build/test entrypoints, and Git Blob evidence. A candidate
   must name the exact scope Skill or Skills whose responsibility it exercises.
4. Repository coverage explicitly records architecture, build/test entrypoints,
   behavior contracts, state transitions, cross-file responsibilities, and
   known gaps. A parser inventory alone is not semantic coverage.
5. Program facts and archived analysis records use the same repository revision
   as their linked Skills.
6. Every candidate binds every source repository exactly once and names the
   supporting scope Skill IDs, Skill IDs, fact IDs, and analysis IDs.
7. Every candidate defines responsibilities, state transitions, independently
   observable acceptance behavior, and unresolved risks before semantic review.
8. Construction adds staged demands, editable and context-only paths, and
   Oracle requirements. Calibration binds the resulting case back to the same
   knowledge cut. Freeze requires independently reviewed accepted and rejected
   variants.
9. A candidate-specific program, workflow, or schema is not a substitute for a
   generic case manifest. Candidate-specific code is allowed only as a declared
   adapter when a reusable interface cannot express a target boundary.
10. Controlled fixtures, generated demos, imported benchmarks, and real-source
   mined cases remain distinct populations.
11. No gate may infer success from filenames, prose, a running service, or a
    previous source revision.
12. A target repository Maintainer Skill export must pin the SkillsGit commit
    used to generate and validate its repository-native tree.

## Executable gate

The Rust gate validates all identities, table digests, repository coverage,
knowledge references, and stage-specific fields:

```sh
cargo run --locked -p agentlab_code_analysis \
  --bin agentlab-maintainer-knowledge-gate -- \
  --stage candidate \
  --source-spec source-spec.json \
  --difficulty difficulty-candidates.json \
  --knowledge-cut maintainer-knowledge-cut.json \
  --binding candidate-knowledge-binding.json \
  --candidate-id difficulty-example \
  --output maintainer-knowledge-gate-receipt.json
```

Stages are `candidate`, `construction`, `calibration`, and `freeze`. Later
stages include every earlier requirement. The gate refuses an output overwrite
so a retained receipt cannot be silently replaced. The evaluation-case table
may be empty at `candidate` and `construction`; `calibration` requires the
binding's exact case row, and `freeze` adds accepted/rejected variants plus
independent approval.

The authoritative schemas are
[`maintainer-knowledge-cut.schema.json`](../schemas/maintainer-knowledge-cut.schema.json),
[`maintainer-scope-skill.schema.json`](../schemas/maintainer-scope-skill.schema.json),
[`maintainer-skill-refresh-round.schema.json`](../schemas/maintainer-skill-refresh-round.schema.json),
[`maintainer-skill-convergence-plan.schema.json`](../schemas/maintainer-skill-convergence-plan.schema.json),
[`maintainer-scope-decomposition-plan.schema.json`](../schemas/maintainer-scope-decomposition-plan.schema.json),
[`maintainer-scope-decomposition-review.schema.json`](../schemas/maintainer-scope-decomposition-review.schema.json),
[`maintainer-scope-catalog-rewrite-receipt.schema.json`](../schemas/maintainer-scope-catalog-rewrite-receipt.schema.json),
[`case-generation-round.schema.json`](../schemas/case-generation-round.schema.json), and
[`candidate-knowledge-binding.schema.json`](../schemas/candidate-knowledge-binding.schema.json).

An oversized structural scope remains blocked. Its decomposition plan is a
revision-bound review artifact, not a catalog row: it must prove exact parent
inventory, complete and non-overlapping file assignment, and bounded candidate
leaves. The convergence plan distinguishes a missing decomposition from a
complete candidate awaiting semantic review. Only an atomic catalog rewrite
may replace the aggregate parent with reviewed child responsibilities.
Semantic review assigns every structural leaf exactly once and binds each
proposed responsibility to exact owned Blobs. A responsibility spanning
disjoint selectors uses those selectors as its ownership authority across fact
binding, checkout projection, candidate validation, materialization and
coverage verification; the common ancestor is only a navigation anchor. The
reviewed replacement is first written as a new immutable candidate catalog.
The original parent remains authoritative until a separate TableGit transaction
imports that candidate, so validation failure cannot leave a partial catalog.
That transaction retires every reviewed parent and inserts every replacement
with one revision fence; delete operations also carry exact row versions. An
independent assessment generated from the candidate catalog belongs to the same
staged cut. The exact committed revision, not the pre-transaction candidate, is
the only Release export source.

## Migration rule for existing evidence

Existing `purchase-data` evidence remains immutable historical evidence. It is
not grandfathered into a trusted case. Its current review, publication, freeze,
or unseen-Agent workflows MUST NOT advance until the two pinned source
repositories have a valid maintainer knowledge cut and the candidate has a
passing gate receipt.

The current `harmony-code-workshop` snapshot is a useful partial migration
source: it has exact Skills, facts, analyses, and cases, but its detailed facts
cover selected scenario paths rather than complete repository semantics. Its
known coverage gaps must remain explicit when a v1 knowledge cut is authored.

## Portfolio rule

One deeply processed candidate is not a portfolio. Each mining round advances a
reviewed cohort with at least three structurally different candidates when the
source corpus supplies them: a local behavioral/state case, a cross-module or
cross-repository contract case, and a lifecycle/UI/performance case. A smaller
cohort needs an explicit retained insufficiency result; it does not silently
collapse to a single case.
