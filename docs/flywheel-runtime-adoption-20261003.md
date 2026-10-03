# Runtime API adoption experiment

Overall maturity remains 73% (engineering estimate); accepted complete automatic
business loops remain zero. Adding a correct helper is not evidence that a
generated verifier correctly uses it.

PR227 merged at `bfcc5208072345c7c6850789d0bfb654c1fb7fb8` after all applicable
CI passed. [Action 37144376165](https://github.com/yxsicd/agentlabrelease/actions/runs/37144376165)
ran one independent root on that exact method: GLM 5.3 flash, thinking disabled,
default reasoning, design-180/code-240, 16384 output tokens, one design correction
allowance and zero code repairs. No previous child or exhausted allowance was
reopened. The fresh design prevents a controlled before/after benefit claim.

Knowledge preflight, build, generation completion and independent isolation
passed. Design/code upstream exchanges completed in 142189/82403 ms. Their
actual completion receipts and raw captures remain outside Release in
flywheel-initial-state-adoption-SAdu9v/capture. No provider-policy effectiveness
or model speedup is inferred from these timings.

The draft contains five scenarios, fifteen checks and five controls. The proposal
preserved all design checks and control declarations. Native staging rejected
`recipe author unowned source`: three proposed sourcePaths are absent from the
loaded inventory. Imported implementations cannot become owned/loaded source
merely because the verifier binds their import specifiers to controlled seams.
Baseline and controls never executed, and no accepted lesson was created.

Static inspection found two additional API defects: loadModule()'s exports object
was treated as a generator instance without constructing the source-exported
class; assertInitialState used /initialState/privateFieldDefaults, although its
pointer is relative to initialState. The helper was mentioned and duplicate source
transformation code was absent, but neither fact proves successful adoption.
Keep the failed original unchanged rather than removing paths or fixing code in
the captured proposal and calling that a successful model result.

## Reusable feedback

Native source-path rejection now reports the exact proposal index and bounded,
JSON-escaped offending path. It retains the loaded-source gate and creates no
stage on rejection. The Rust regression checks the actual rejected operation,
its path diagnosis and absence of output. It does not admit an unloaded dependency.

The author prompt and program-analysis Skill clarify three separate identities:
loaded source versus controlled import seam, module exports versus constructed
instance, and a pointer relative to initialState versus the containing packet.
Examples use generic class/field names; no repository-specific path, class or
expected behavior is added to the method. These are interface corrections, not
static proof of arbitrary verifier correctness or another real construction.

Remaining acceptance: successful new-method adoption; independently calibrated
complete controls/recovery and semantic review; automatic durable knowledge return;
productive next-round consumption; measured multi-round and cross-repository
benefit; full Harmony case deployment/execution and declared performance lanes.
