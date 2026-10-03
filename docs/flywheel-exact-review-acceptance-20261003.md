# Real source construction and exact-review continuation

Overall maturity remains 73% (engineering estimate); accepted complete automatic
business loops remain zero. Complete cloud control execution is new evidence,
not semantic qualification or productive knowledge feedback.

PR225 merged at `db702d8818f284d14a1e64a0d5c344d9aec7271b` after all applicable
CI passed. [Root Action 37141430630](https://github.com/yxsicd/agentlabrelease/actions/runs/37141430630)
used that method with GLM 5.3 flash, thinking disabled, default reasoning,
design-180/code-240, 16384 output tokens, one design revision and two frozen
code-repair allowances. No prior terminal experiment was reset.

Design and code completed semantically with HTTP 200 and upstream EOF at
138469 ms and 99652 ms. Recorded participant isolation passed. The initial
verifier baseline passed without consuming a code repair. The cloud scheduler
then ran all seven declared controls and fresh accepted-reference recovery.
Baseline, three references, wrong-button-vs-checkbox, wrong-remove-parse-throw
and recovery matched their frozen declarations. The Action failed on the one
remaining wrong control's declared failure-set disagreement, not infrastructure.
Native readback of the downloaded cloud evidence independently reconstructed all
seven controls and recovery with completeInventoryReconstructed=true and the same
review-declaration-mismatch status. It did not rerun a model or worker.

Bindings:

- request: `e6c86e30cd0bc360669f77f602a6143e0bd524fe4916f15faf465457a44d803a`
- design: `821610e581ccb38cbdc248af01b741ac2db4e3158f46de66ff7429624ebf1684`
- proposal: `dea014e533aac9afec772c1800e46c27783b512cd8aac8f0fd9cc0055b669e88`
- suite: `81fd4869f063f25c056cbf0826594578a09e0744cff39bf205701a61eb7c6cc1`

## Source-grounded review, not expectation rewriting

The exercised source is ToggleCodeGenerator.generate, not the earlier descriptor
convert body. It interpolates textColor only in the Button return branch. The
Checkbox else branch does not read that field. Accordingly, wrong-invert-text-color
failed check-button-branch-full and check-button-branch-text-color, while the
two Checkbox checks still passed. Preserve those original oracles; correct the
control failure attribution through a reviewed successor rather than rewriting
the recorded result or declaring the mutant unexecuted.

The verifier also omitted verification of the four declared constructor fields,
hardcoded promiseReturned=false, and did not clearly disclose that imported
mapping tables were controlled adapters. The request contains the mapping source
but not the CommonMapData implementation. Missing implementation context and
an omitted export binding are separate defects; this experiment does not prove
that loading more source would itself repair an adapter.

The review requires checking actual constructor state without overwriting it,
observing actual return nature, and accurately declaring controlled-mapping and
non-platform scope. It authorizes no check or scenario changes. Legacy frozen
records and failed originals remain intact.

One `agentlab.source_recipe_design_review.v2` child,
[37142100477](https://github.com/yxsicd/agentlabrelease/actions/runs/37142100477),
was dispatched on the same method with checkChanges=[] and scenarioChanges=[],
one design correction allowance and zero code repairs. Review SHA256:
`b33fea8847474d7cf927224c7f47decf3d298c3c2b663af50c4c4776b83c1fd2`.
Portable binding passed before dispatch; current live request reproduction is a
separate Action gate. This child terminated before building or model dispatch:
the live knowledge preflight's MCP inspector table_query returned Request timed
out. No successor design, exact-output protection or semantic correction was
executed. Its frozen allowance remains unchanged; no rerun is claimed.

The preflight failure happened before recipe-author was created, so the always
artifact upload also failed with no files found. The workflow now creates that
exact evidence root before preflight and saves original stdout/stderr there while
preserving command failure. It does not add a transport retry, fabricate an
admission receipt, bypass knowledge matching or grant a model budget on failure.
This is a capture repair, not live transport recovery or a successful child.

The current native reader also successfully reconstructed the older exact-commit
TableGit recovery: six controls and accepted-reference recovery, complete
inventory and declarations-matched, semanticQualified=false. That was historical
readback, not another model or worker run.

Remaining acceptance: complete child contract preservation, correct executable
consumption, independent semantic admission, durable operational/knowledge
publication and actual next-round consumption with measured benefit. Cloud
execution alone still does not qualify HAP, ohosTest, emulator performance or
cross-repository generalization.
