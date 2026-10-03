# Frozen source-control diagnostic entry

Overall maturity is 73% (engineering estimate), with zero accepted complete
automatic business loops. The constructor Action currently returns after a
passing baseline: it does not execute the full frozen control matrix or admit
knowledge. This change adds the native execution-input and readback entry needed
for that next integration, not a claim that the full integration exists.

Use the same exact staged design, verifier, runtime, compiler and contained worker:

```sh
agentlab-maintainer-skill-flywheel --prepare-source-recipe-control-diagnostic \
  --stage STAGE --control-id CONTROL_ID --typescript PINNED_COMPILER \
  --worker scripts/source-recipe-diagnostic-worker.cjs \
  --image-id sha256:EXACT_IMAGE_ID --output NEW_INPUTS
(cd NEW_INPUTS && python3 /ABSOLUTE_RELEASE_ROOT/scripts/run-contained-behavior-worker.py descriptor.json request.json)
agentlab-maintainer-skill-flywheel --feedback-source-recipe-diagnostic \
  --diagnostic-inputs NEW_INPUTS --worker-capture EXACT_CONTAINED_CAPTURE \
  --output NEW_FEEDBACK
```

The compiler and worker are explicit current dependencies; retained source bytes
do not authenticate historical revision ancestry or restore the original runner.
The selected control must occur exactly once and use a recognized role. Wrong
controls require known unique failed-check IDs; accepted controls require none.
The selected role and failure declaration are bound into retained support bytes
and independently checked on feedback. Normal worker exit does not establish a
declaration match: Rust compares each actual JSON-pointer value under the unchanged
frozen predicates and compares the complete failed-check set. Missing expected
failures and unexpected failures stay separate. Infrastructure faults report null
observed failure sets, not successful negative controls.

The control diagnostic has a separate intent/feedback schema. The unchanged
baseline reconstruction used by automatic repair rejects it. No code, check,
scenario or declaration is modified; no new repair allowance, semantic approval,
formal isolation qualification, knowledge admission or authority write follows.

Local Rust regressions cover matched controls, surviving wrong controls, additional
failures, accepted controls, infrastructure faults, declaration drift, absent and
invalid control selection alongside the prior baseline/repair regressions. Synthetic
capture reconstruction is not real container or generated-Agent calibration.
Next integration must execute all frozen controls and a fresh accepted-reference
recovery, preserve disagreements for source-bound review, and only then connect
independent admission and later-round consumption.

## Real bounded repair and retained-control execution

[Action 37131931224](https://github.com/yxsicd/agentlabrelease/actions/runs/37131931224)
ran main 3d696b906374df0bb8179ca78d1ddf55b6903bf3 and succeeded. The initial
verifier used the explicit compiler initializer but failed on an unbound import;
repair one fixed that binding and failed on an absent Observed global. Repair two
supplied that explicit scope-limited identity decorator and passed all 20 baseline
checks. It did not erase decorators from source. Independent participant isolation
passed for original construction and both repairs. All three designs have identical
SHA256 fd4067600682743e6bbdc63d82fa7e47dad86a2be003dc7848b8f1d6b5cb6268.
Selected verifier SHA256 is
6f27b47e77a5360ef439bb6b649236b70412d11703837150fb4bd7eb4cb6de5b.
The original two failures and all generation captures remain retained.

Operator source review traced the parse catch/continuation, map fallback and
ordered attribute effects to the exact original ToggleDescriptor/ToggleAttributeMapping
bodies. A separate local contained diagnostic used the unchanged selected verifier,
design/runtime and matching compiler bytes with image
sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553.
Its actual runtime was Node v24.21.0 arm64, not the original Action's Node v24.19.0
x64; no historical environment equivalence is claimed.

Seven contained executions reconstructed exact declaration matches: baseline,
ref-01, ref-02, wrong-01, wrong-02, wrong-03, and fresh baseline recovery. Wrong-01
failed c-throw-bg and c-throw-completed, wrong-02 failed c-unknown-type, and wrong-03
failed c-throw-is-on, with no additional or missing failures. Neither accepted
control nor recovery failed a check. This is real retained-source diagnostic
coverage, not automatic semantic review or formal case admission.

The first local worker succeeded but its capture was created in the operator's
working directory, so feedback initially failed to locate it. Its exact request
identity was reconciled and the original capture moved intact into its owned
artifact directory; no worker rerun or synthetic replacement occurred. Subsequent
invocations set cwd to the exclusive input directory. Keep this launcher detail
in scheduling integration and preserve the initial collection failure.

The +1 estimate reflects demonstrated Agent-owned bounded repair and real generic
control diagnostics. The Action still stops at baseline, control selection here
was operator-scheduled, and no knowledge promotion or later-round benefit occurred.
JSON parse and the decorator are explicit host seams; Harmony framework delivery,
ArkTS/HAP/emulator execution and full scope coverage remain unqualified.
