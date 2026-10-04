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

The exact-head full Rust CI 37231794116 subsequently failed at
`maintainer_baseline_action`: an older transport fixture used non-JSON strings
as the author request, so the new target lookup rejected it before the expected
mocked continuation path. The failed CI is retained. Its fixture now uses valid
original JSON and additionally exercises actual native target restoration through
the real baseline acquisition adapter, including non-target and existing-target
drift rejection before claims/dispatch. Both baseline Action tests passed locally.
This exposes an omitted caller in the earlier targeted regression scope; it is
not a reason to skip the full suite or relax target validation.
Public validation 37231794102 reported the same baseline-fixture failure;
the analysis component 37231794142 passed. A subsequent full local Rust run
identified two more transport-test gaps: missing original parent request in a
revision mock and inherited `GITHUB_OUTPUT`/`GITHUB_ENV` in a preflight test.
They now supply complete structured parent inputs and isolated output paths;
the revision test also runs actual native target restoration. Both individual
regressions passed without changing production admission or frozen captures.
The repaired full `cargo test --locked --offline -p agentlab_code_analysis` run
then exited **0**, with **423 passed tests** and no failed or ignored tests.
Its retained stdout SHA256 is
`5e4d2453f8b1e53cd5ca2383c489c6f5280ee623ad0848afdd8f8d939ae3f926`;
stderr SHA256 is
`870968191369c7cc97e4343cb4c1af3be3c332bd8699bfdd02ff0535ddce412a`.
This is full local regression evidence, not exact-head CI or an Agent outcome.

Next: deliver this method and prospectively enroll a fresh real constructor using
the new frozen rubric, then complete baseline, wrong/reference controls, review
and committed return. Measure repeated outcomes and transfer to another repository
before claiming effectiveness or increasing complete-round counts.
