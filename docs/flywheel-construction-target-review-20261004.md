# Preserve the original construction target through independent review

Overall engineering maturity remains **79%**. Accepted complete automatic
five-stage rounds remain **0**. This change closes a review-input gap, not an
accepted construction, semantic coverage proof or measured learning benefit.

The current reviewer reconstructed source, design, proposal and raw observations
but did not receive the original explicit construction target. Its historical
six-criterion rubric could assess internally consistent generated checks without
accounting for every requirement in the original demand. Path inclusion in the
guidance gate did not establish that the demanded behavior was exercised.

Fresh targeted author preparation now accepts `--source-construction-selection`.
It validates the reviewed selection against the original knowledge/source cut,
scope, uniquely loaded source paths and source-byte digests, then freezes its
`sourceRecipeTarget` in the author request before inference. Guidance rebinding
requires equality with this frozen target, including the demand. The author
prompt's source context carries the target for both treatments. The ordinary
observation exporter retains the complete original request unchanged.

Independent review validates that original target and conditionally exposes it
as `constructionTarget`. The separate prospective
`examples/maintainer-knowledge-gate/source-target-quality-rubric.json` retains the
six prior criteria and adds `construction-target-coverage`: account for each
explicit demand clause against original source, exercised scenarios and scored
observations. Missing support is fail or unverified, not inferred coverage.
Target and target-coverage criterion require each other at native preparation.
The Action additionally rejects fresh targeted review without that criterion
before constructor inference. Rubric path and digest must be enrolled explicitly;
the historical rubric is not rewritten or silently replaced.

Legacy requests produce no additional review key, including no null placeholder.
Reviewed successors and baseline continuations do not acquire new request fields:
they retain their frozen parent request. When a parent already has a frozen target,
the native restoration gate requires all non-target prepared fields to agree and
returns the exact original parent bytes. Legacy parents cannot gain a new target,
and an existing target cannot be overwritten. The legacy revision, reviewed
successor and baseline-continuation transports invoke this before participant
inference. All previous roots, budgets, expectations,
knowledge cuts and captures remain unchanged. No new model or authority write is
performed by these tests. Source-only review does not qualify Harmony/ohosTest,
a formal case, an authenticated producer or a complete flywheel.

Validation exercises target binding for two unrelated repository identities,
ordinary original-byte export into the real native review packet and canonical
prompt, missing-target and missing-criterion rejection, and absence of a target
key for legacy review. Rust-driven tests execute the actual Action enrollment and
target-preparation argument blocks, testing fresh and retained-parent lanes.
The three affected integration suites passed: 17 guidance, 32 diagnostic and
3 Action tests. Skill validation and formatting passed. One initial test compile
failed due to an incorrect fixture signature; corrected before the passing run.

Next: deliver this method and prospectively enroll a fresh real constructor using
the new frozen rubric, then complete baseline, wrong/reference controls, review
and committed return. Measure repeated outcomes and transfer to another repository
before claiming effectiveness or increasing complete-round counts.
