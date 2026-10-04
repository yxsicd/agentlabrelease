# Pre-execution source design quality review

Overall engineering maturity remains **79%**; accepted complete automatic rounds
remain **0**. Native input/content validation is implemented here, not a completed
automatic reviewer, enforced Action gate or successful flywheel round.

Retained run37234369136 exposed more than an undeclared platform resource global:
its exception scenario observed only the thrown exception despite the original
demand requiring earlier effects and skipped later effects. Its wrong-fallback
control replaced the default fallback with the existing field value, but the
declared unknown-input scenario started at that same default. This is a static
discrimination concern, not an executed control verdict. Fixing verifier execution
alone cannot establish a good Oracle or task coverage.

The separate repository-agnostic design rubric requires original-demand coverage,
state observation, control discrimination and runtime-environment closure. Native
preparation calls the actual reproducible author design gate, requires an original
frozen target, preserves exact request/design bytes and includes all owned source
and declared read-only context. No proposal, worker execution or passing suite is
fabricated to make early design review possible. The final suite-review contract
and historical rubrics/captures remain unchanged.

Prepare a packet:

```sh
agentlab-maintainer-skill-flywheel --prepare-source-design-quality-review \
  --author-request request.json --design design.json \
  --quality-rubric examples/maintainer-knowledge-gate/source-design-quality-rubric.json \
  --output design-review-request.json
```

Validate an opinion against the same original inputs:

```sh
agentlab-maintainer-skill-flywheel --validate-source-design-quality-review \
  --author-request request.json --design design.json \
  --quality-rubric examples/maintainer-knowledge-gate/source-design-quality-rubric.json \
  --review-response response.json --output design-review-content-validation.json
```

Every criterion, scenario, check and control must appear exactly once. Pass/fail
requires exact original citations; pass item rows require valid scenario links,
and passed checks must link the scenario addressed by their frozen pointer.
Read-only dependency quotations are allowed only from the bound original context.
Unknown IDs, omitted inventories, invalid quotes and unresolved all-pass opinions
are rejected. Rust derives `revise`, `unverified` or `ready-for-execution`; it does
not trust a model-emitted verdict or permission field. Exact quote existence and
valid links do not establish that an argument is sound or a mutation distinguishable.

All reports explicitly leave reviewer execution/authentication, source-producer
authentication, semantic qualification, execution permission, learning benefit and
authority writes unestablished. CLI output is create-new only. Preparation consumes
the current reproducible source/knowledge paths; it is not a portable admission of
historical runner paths. Never edit a historical request to make it reproducible.

Next integration must prospectively enroll the rubric and reviewer budget before
inference, bind the canonical review packet/prompt to independently captured
reviewer wire, and stop code generation on revise or unverified. Reviewed changes
must use the existing exact design-review successor gates, preserving original
failed evidence. This feature is not yet wired into Action, and content-only
ready-for-execution must not be used as that gate. Real complete controls and
final suite review remain mandatory even after a future authenticated early review.

The follow-up adds `--source-design-quality-review-prompt` and
`--verify-source-design-quality-review-completion` (the latter also requires
`--evidence` and `--review-response`). Both reconstruct the same live native packet.
The capture intent is `agentlab.independent_source_design_review_intent.v1`,
using `reviewRequestSha256`, `qualityRubricSha256`, `promptSha256`, bounded
`participantBudgetSeconds`, zero `transportRetryLimit` and participant identity.
Capture label is `source-design-review`, not `source-suite-review`. The existing
isolated original-wire verifier checks exact prompt/history, one exchange,
lifecycle, complete upstream response and participant final message. Design review
has no enrolled repair lane. Completion records reviewer execution and recorded
context separation only; authentication, semantic qualification and execution
permission remain false. This adds no model dispatch or Action gate by itself.
Synthetic Rust capture tests reject a different phase intent, changed prompt
digest, changed actual upstream prompt, malformed response and missing lifecycle.
These transport fixtures are not a real independent reviewer outcome.

Local validation: two Rust content-contract tests exercise unrelated identities,
rejection precedence, missing/duplicate IDs, invalid citations and scenario links,
read-only citations and whole-scenario pointers. The actual source/knowledge
integration fixture exercises both native CLI preparation and response validation,
preserves original bytes and keeps synthetic all-pass unqualified. An earlier
overlapping integration run failed at its existing later source-operation baseline:
the original process reached 30014 ms against 30000 ms, with empty stdout/stderr.
Its capture is retained; another fresh fixture completed successfully. The exact
cause of the first deadline is not established, and no timeout was increased.
Full regression and exact-head CI remain separate delivery gates.

The subsequent complete local package regression exited **0**. A final focused
Rust run including the whole-scenario pointer compatibility case also exited
**0** with both design-quality tests passing. Formatting, Skill validation,
release checksums and diff checks passed. Exact-head cloud CI and real reviewer
capture are not established by these local results.
