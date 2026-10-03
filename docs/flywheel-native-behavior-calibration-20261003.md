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
