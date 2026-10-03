# Bounded design correction checkpoint

Overall maturity remains **72%**, an engineering estimate. Accepted complete
automatic business loops remain **0**. Improving diagnostics does not prove a
model correction, a qualified case, or feedback benefit.

## Observed failure and repair

[Action 37111329948](https://github.com/yxsicd/agentlabrelease/actions/runs/37111329948)
ran main 0e936163a8fd474e0a97e3c623c6ceba58e6ecdf. Both completed design
turns failed with `recipe design scenario seam fields`; independent runtime
isolation validation passed. The retained designs contain empty named seams.
The original prompt already specified outcome sequences and repeatLast, but
feedback did not identify the rejected field or distinguish a dependency from
the tested method. No proposal was admitted or executed.

The native validator now returns the exact scenario/seam JSON pointer and
required shape. Outcome errors include their sequence index. Empty dependency
inventories remain valid; empty named dependencies remain invalid. Valid kinds,
field counts, budgets, frozen checks and semantic review are unchanged. Feedback
does not copy arbitrary submitted values. Error prefixes remain compatible with
the existing bounded controller's repairability classification.

Rust regressions cover the real failure structure, the public design consumer,
all six supported outcome kinds, wrong types, missing/extra fields, empty
sequences and escaped dependency IDs. These establish static diagnostics only.
Next: integrate and run a fresh constructor with the same bounded policy, then
independently review any proposed verifier before controlled execution.

## Separate observation-store progress

Operator follow-up persisted the safe structured export from successful Action
37108595501 into independent bare TableGit repository
`agentlabtelemetry-37108595501` on cbgroomtpc. Six tables contain 54 rows with
exact native reconstruction/readback, committed at
2442e47040a53f96f946fd48ff30dba228b62500. Repeat import inserted zero rows and
retained the same revision. The original Action index remains unchanged.

This proves structured operator persistence and idempotence, not automatic
feedback admission. Raw remote bytes remain unpreserved; reusable knowledge did
not change, and no next round consumed these observations. Complete raw archival,
admitted useful knowledge, automatic next-round consumption, productive repeated
rounds and cross-repository benefit remain explicit gaps.
