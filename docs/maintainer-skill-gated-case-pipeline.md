# Maintainer-Skill-gated case pipeline

This contract is mandatory for every real-source AgentLab case. It turns the
maintainer knowledge design into a fail-closed production boundary rather than
an optional knowledge-seed experiment.

## Required order

```text
exact source set
  -> whole-repository inventory and parser receipt
  -> repository maintainer Skills
  -> complete Maintainer SKU partition of the source tree
  -> revision-bound program facts and archived analyses
  -> explicit Skill/fact/analysis candidate binding
  -> reviewed multi-candidate cohort
  -> task construction
  -> independent Oracle and variant calibration
  -> frozen evaluation case
  -> assessed attempts and feedback into a later knowledge cut
```

The order is normative. A feedback signal may choose the next source set or
rank already grounded candidates, but it MUST NOT replace repository knowledge,
program analysis, independent calibration, or cohort review.

## Hard requirements

1. Every repository is pinned by URL and 40-hex Git revision.
2. Every repository has instance Skills for `repository-analysis`,
   `program-analysis`, and `seed-extraction` at that exact revision.
3. Every tracked file belongs to exactly one leaf Maintainer SKU. Each SKU
   binds its repository revision, path boundary, responsibility, language mix,
   build/test entrypoints, and Git Blob evidence. A candidate must name the
   exact SKU or SKUs whose responsibility it exercises.
4. Repository coverage explicitly records architecture, build/test entrypoints,
   behavior contracts, state transitions, cross-file responsibilities, and
   known gaps. A parser inventory alone is not semantic coverage.
5. Program facts and archived analysis records use the same repository revision
   as their linked Skills.
6. Every candidate binds every source repository exactly once and names the
   supporting SKU IDs, Skill IDs, fact IDs, and analysis IDs.
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
[`maintainer-sku.schema.json`](../schemas/maintainer-sku.schema.json), and
[`candidate-knowledge-binding.schema.json`](../schemas/candidate-knowledge-binding.schema.json).

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
