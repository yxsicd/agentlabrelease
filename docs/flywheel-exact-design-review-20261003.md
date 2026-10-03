# Exact design-review successor protection

Overall maturity remains 73% (engineering estimate); accepted complete automatic
business loops remain zero. This closes a declared-contract admission loophole,
not semantic verification, model convergence or next-round learning benefit.

`agentlab.source_recipe_design_review.v2` extends legacy v1 with required
`checkChanges` and `scenarioChanges` arrays. Empty arrays preserve all parent
checks and complete ordered scenarios. Every change contains exactly `id`,
`before`, `after`, `findingId`; the finding must exist in the source-bound review.
Before must equal the original record (null for additions); after is the exact
replacement (null for removal). Duplicate/no-op changes and borrowed before
records fail. Existing scenario order is retained; additions append in review
order. This reuses the existing proposal-revision exact-change machinery.

The native output gate runs after each design attempt and before code inference.
Final staging independently repeats protection and retains byte-bound parent,
review and output admission. Approval, portable diagnostic preparation and suite
reconstruction reconsume those originals. Observation export includes the review
sidecars, so durable recovery cannot omit the new consumer dependencies.
The Action recognizes v2 without changing inference or repair budgets.
Code-only automatic repair rejects review-bound parents until its lineage can
retain that review; it must not silently drop the protected parent context.

Legacy v1 remains explicitly prose-only. It can be replayed, but its output
receipt has `exactContractProtected=false`. Neither version authenticates the
reviewer, establishes an Oracle's semantic truth, freezes all control edits, or
proves that a generated verifier correctly consumes the protected scenarios.

## Real retained-output regression

The unchanged original request/design of Action 37131931224 and retained child
design of Action 37138587647 were passed to the new native CLI with a separate
v2 regression review authorizing no check/scenario changes. It exited 1 with:

```text
recipe design scenario differs from exact design review at scenario default-state; require scenarioChanges before/after/findingId
```

The same gate accepts the unchanged original design. This is an offline
preservation regression, not another model dispatch, a replacement of the
historical v1 review, or a reopening of the failed child's exhausted allowance.
All historical raw files remain unchanged.

Rust regressions cover unauthorized initialState/inputs/expectedObservations,
check changes, explicit accepted changes, append ordering, borrowed records and
findings, pre-staging rejection, retained-review tampering at approval, portable
comparison with unavailable historical paths, bounded design correction and
v2 Action routing. Remaining work is fresh semantically reviewed construction,
actual verifier correctness, accepted lesson admission and automatic next-round
consumption with measured benefit.
