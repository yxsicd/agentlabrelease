# Action design-review continuation

Overall maturity remains **72%**, an engineering estimate. Complete automatic
business loops remain **0**. This connects an existing source-bound review gate
to Action; it is not automatic semantic review or successful design correction.

[Run 37128777539](https://github.com/yxsicd/agentlabrelease/actions/runs/37128777539)
used main b713cb97b4dc79b540e4bedea915bca20307fbbc. Code first content arrived
at 171427ms and semantic terminal at 206422ms; the exchange completed at 206450ms
with clean EOF under the explicitly selected code-240/design-180 policy. All three
captured turns completed and independent filesystem/network/credential isolation
passed. This proves this cohort completed beyond 180 seconds, not causal speed,
default-policy effectiveness, semantic correctness or a useful case.

Staging rejected `recipe proposal changed frozen design contract`: the proposal
changed check pointers/values and two wrong-control failure sets. Independent
source review also rejected the frozen descriptor baseline: catching an invalid
parse resets the value to the default and allows later attributes to execute,
whereas the design and proposal expected an earlier value and skipped updates.
No baseline, control calibration or knowledge admission followed.

Design SHA256: 542ec9b11ceff39ad6df49b6fd22694f2ab8ae7a2a8a314ac2dfd78f5a9d3d53.
Proposal SHA256: cd47c4cc6616ae320cb56f5d90ef8fdaa0315def12c3595515f21362c6490bbb.
Code status SHA256: 666436a7b01192041c3a01836d08a4e05ac2198660a907b546e3a7bb6444df16.
Original private captures and source review remain outside Release.

The existing `revision_parent_run` and `revision_feedback` Action inputs now
also accept `agentlab.source_recipe_design_review.v1`. Select design_first=true
and code_revisions=0; do not reopen a previous automatic repair budget. The
transport helper requires byte-identical current/original author requests,
rejects review/diagnostic child roots and invokes the existing native review
validator before retaining exact parent design bytes. Native admission reproduces
current source/knowledge and checks review digests and loaded owned source paths.
The author independently repeats admission before its first model turn. Proposal
review retains its previous path and exact parent protections.

Request drift stops before inference; feedback must be based on the original
request/design bytes, not silently rebound to a newer source cut. Design-only
review is an explicit request to revise and cannot approve a semantic Oracle.
The new design and any generated verifier remain unreviewed until independently
reviewed and calibrated. Rejection remains terminal; this helper adds no network
retry, budget reset, automatic knowledge promotion or authority write.
