# Fresh controls before bounded repair

Overall maturity remains an engineering estimate of **70%**. Accepted complete
automatic business loops remain **0**. This producer removes manual control
dispatch/capture assembly for an existing behavior-executor lane; it does not
generate semantic controls, admit a case or automate the entire flywheel.

## Entry points

```sh
agentlab-maintainer-skill-flywheel --execute-behavior-calibration \
  --contract frozen-checks.json --calibration-recipe reviewed-controls.json \
  --output NEW_EXTERNAL_DIRECTORY

agentlab-maintainer-skill-flywheel --execute-calibrated-behavior-loop \
  --contract frozen-checks.json --calibration-recipe reviewed-controls.json \
  --loop-template reviewed-template.json --output NEW_EXTERNAL_DIRECTORY
```

The calibration recipe has schema `agentlab.behavior_calibration_recipe.v1`,
reviewed=true, automaticPromotion=false, exact contractSha256, sources (id and
complete submittedSource), recoveryControlId, executorCommand and immutableInputs.
The original frozen-check consumer validates all predicates/control identities
before dispatch. Every declared source must match its SHA256; duplicate/missing
sources and Agent-attempt roles reject. Select an accepted source for recovery.
Existing limits remain: 5..32 controls, at most 60s per executor, 256KiB source,
256KiB contract and 4MiB calibration recipe/capture. Dependencies use the existing
regular-file, non-symlink, byte-bound immutable-input contract.

Commands reuse the existing absolute-program/digest/args/cwd/deadline format;
cwd is '.', and exactly one argument is `{request}`. Sources and check IDs/inputs
are supplied through `agentlab.behavior_executor_request.v1`, without expected
answers or other controls. The same process-group/deadline/log-budget primitive
used by the bounded repair loop captures actual stdout/stderr and process results.
No private environment is forwarded to calibration. Commands are trusted reviewed
adapters, not an untrusted-source security sandbox or runtime attestation.

Index-based output directories avoid treating business IDs as filesystem paths.
Each prior completed capture and immutable dependency is rechecked around later
dispatches. A fresh final execution of the same accepted source replaces only its
worker in a separate recovery capture, using unchanged predicates and manifest.
It is not another distinct valid strategy, Git restoration, UI cleanup proof or
additional coverage. Both matrices must independently pass before participation.
Infrastructure failures retain raw captures and a terminal failed result; surviving
or contaminated controls and failed recovery produce review-required feedback.

The combined entry uses `agentlab.calibrated_behavior_loop_template.v1`, with the
existing reviewed loop fields but no captureSha256, plus calibrationRecipeSha256.
It explicitly authorizes binding a newly produced capture, not a fictional
pre-existing one. Calibration and attempt executorCommand must be identical.
The original template, derived loop recipe, calibration files and dependencies
are pinned across the existing repair attempts. Inherited immutable-file and
recipe-size limits still apply; oversized evidence cannot authorize dispatch.
All qualification/promotion/authority boundaries remain false.

## Ordinary Action integration

`prepare-contained-behavior-loop.cjs --flywheel-tool ABS_BINARY` freezes source,
controls and the existing contained-worker descriptor, then invokes the Rust
producer. It emits the ordinary repair recipe only after both calibration and
recovery pass and pins their captures/verdicts into that recipe. Existing callers
without this option retain their legacy preparation path. The existing
maintainer-behavior-loop Action now selects the Rust path explicitly; its later
participant isolation, captured completion and independent runtime checks remain.
This source change has not yet been validated by a fresh cloud Action run.

## Fresh actual-source diagnostic

The existing upload/retention host-seam adapter was executed locally through the
new Rust CLI with six retained source variants and one accepted-reference rerun.
Original source revision stays `7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6`.
The diagnostic contract preserves historical checks/control declarations and
records a new method binding and observed Node v26.5.1 host runtime, not the old
container identity. It is not HAP, Harmony/RDB, emulator or assessed-Agent evidence.

Contract SHA256:
`04a79b38eaf5d796735cbf6715d7dd37719c7bd86be7fcdf89b586f1cfd115a5`.
Artifacts live outside public source in `flywheel-native-calibration-WHUFu6eB`.
Both matrices returned `review-unexpected-control-failures`, qualified=false.
Reference and alternative valid implementations passed; recovery reference also
passed. The delete-before-upload variant failed fulfilled-false, fulfilled-true
and all three rejection boundary checks. Its historical intended-failure set did
not declare all those outcomes. This is an incomplete control declaration, not
independently proven UI contamination. The original declaration/captures were not
rewritten to make this run pass. Producer binary bytes were digest-bound during
dispatch, not archived as a complete historical binary package.

Rust subprocess regressions cover the public CLI's calibration→recovery→two
repair attempts, missing/surviving/extra failures, failed recovery, input drift,
prior capture mutation, terminal infrastructure failure and output reuse. The
executor computes fixture source values; it receives no expected answers. These
are deterministic controller tests, not learning, cross-repository transfer or
formal full-loop acceptance. Next review incomplete real control declarations,
exercise the contained Action, and adapt the same orchestration boundary to
source-bound emulator builds without substituting this host seam for that gate.

## Declaration provenance reconciliation

Overall maturity is now an engineering estimate of **71%**, from 70%, for a
generic source-bound reconciliation path plus fresh actual-source verification
that removes this calibration blocker. Accepted complete automatic business
loops remain **0**; this is not measured Agent benefit or a cloud Action verdict.

The earlier committed source-operation receipt already declared the full failure
sets. A subsequent diagnostic projection narrowed delete-before-upload to one
check; the published behavior profile also narrowed failure-path-overreach to one.
The additional failures were not independent proof of UI contamination: this
adapter creates a fresh TrackManager module/context for each scenario. The prior
recipe declares all five delete-before-upload failures and both failure-path-
overreach failures. Its exact source variant SHA256s match the profile edits.

`--reconcile-control-declarations --profile FILE --control-reference FILE
--source-bytes FILE --output NEW_FILE` reuses the recorded source-operation
consumer to reconstruct original recipe/execution/scope bytes and raw streams.
It matches repository/revision, original source, check IDs/expected values,
control roles and exact-match edited variant SHA256s. Corrections come from the
prior **declared contract**, not the new observed failure set. The proposal is
reviewed=false and preserves parent/reference/source digests. Producer identity,
input interpretation, semantic intent and commit ancestry still require review.

The reviewed successor is
`examples/maintainer-knowledge-gate/reviewed-behavior/telemetry-upload-demand-declarations-v2.json`.
The old profile remains unchanged. Its controlDeclarationReference pins the
reference and parent profile paths/SHA256s. Normal preparation invokes
`--validate-control-declaration-reference` with those files and newly acquired
source bytes. The successor must equal the parent's reconstructed proposal
apart from reviewed=true and reference metadata. Checks, inputs, task identity,
budgets, source edits and adapter selection cannot change through this route.
Reference/parent files are committed-path selected and pinned through execution.
The Action default now selects this successor; a fresh cloud run is not yet proven.

Synthetic arbitrary-repository Rust regressions exercise changed role/source/
variant/predicate, corrupt originals, and the public validator's refusal of changed
inputs or candidate identity even when expected values still match. These fixtures
do not authenticate a producer. Fresh native execution of six real source variants
and reference recovery returns execute-agent-attempt for both matrices and
calibration-passed, qualified=false. Original rejected captures remain retained.
No emulator or participant execution was performed by this new host-seam run.

Artifacts: `flywheel-control-declaration-EafswUEe`; successor contract SHA256:
`74bd5e70f9be91aeb81b463ff146675d619624011a81e8c057d5a8b8723d9df5`.
This run separately retains producer binary, worker, compiler and support bytes;
observed runtime is Node v26.5.1. Next verify a fresh contained participant run
and evidence return, then emulator orchestration and cross-repository multi-round
benefit rather than counting this one scoped calibration as a complete loop.
