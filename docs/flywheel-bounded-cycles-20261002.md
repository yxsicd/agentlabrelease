# Bounded multi-round coordinator

The Rust CLI adds `--execute-flywheel-cycles --recipe FILE --output FRESH_ABSOLUTE_DIR`.
It transports fixed state through repository understanding, program analysis,
maintenance verification, case execution and evidence return, then supplies the
returned state to the next round. This is a generic trusted adapter boundary,
not completed business-stage integration or evidence of learning. Maturity stays
62% until actual integrations and repeated real execution establish more.

Recipe schema `agentlab.flywheel_cycles_recipe.v1` requires `reviewed:true`,
`automaticPromotion:false`, `maximumRounds` 1 through 8, `initialState` with an
absolute regular-file path and exact SHA256, `immutableInputs`, and exactly five
ordered `stages`: `repository-understanding`, `program-analysis`,
`maintenance-verification`, `case-execution`, `evidence-return`.
Each stage selects the existing operation command format: absolute `program`,
`programSha256`, `args` with exactly one `{request}`, `cwd:"."`, `timeoutMs`
1 through 900000. The sum of stage command deadlines times maximumRounds must
not exceed 3600000 ms. This is a composite-stage allowance, not a change to
existing individual Agent/operation/behavior-attempt deadlines. Commands execute
in their fresh stage evidence directory.
Use narrow adapters around existing gates; commands must not reinterpret a zero
exit code as business success. Pin their script/dependency files explicitly in
`immutableInputs`. Executable digests do not transitively bind dependencies.

Each `agentlab.flywheel_stage_request.v1` contains `round`, `stage`,
`recipeSha256`, `inputState` (path/SHA256), `previousStage` and
`automaticPromotion:false`. The previous stage envelope includes captured
execution and original result, including a previous round's evidence-return.
State is an opaque, bounded 16 MiB artifact: business adapters own its source,
knowledge, case, feedback and authority-revision schema and independent checks.
The case-execution adapter must include evidence-backed candidate generation,
independent calibration and execution; repeatedly running a fixed reviewed task
alone cannot qualify the case-generation part of the full flywheel. Evidence
return must preserve reviewed lesson admission and exact committed cut readback,
not substitute a JSON status for those existing gates.
Do not embed credentials in state. Each stage may explicitly select
`environmentNames` from the existing Gateway/model/Pi/runtime/Docker names plus
`AGENTLAB_TABLEGIT_MCP_URL` and `AGENTLAB_TABLEGIT_PERSON_ID`. Values come from the
operator's environment, are never recipe/request/receipt fields, and are forwarded
only to the selected stage. Duplicate, unknown or absent names fail preflight.
An empty selection preserves the default of no private environment forwarding.
Scoped trusted adapters may acquire their own credentials separately.
This is not an untrusted-code sandbox or credential-access isolation guarantee.

The adapter emits one stdout JSON `agentlab.flywheel_stage_result.v1` containing
the exact `round`, `stage`, `requestSha256`, `inputStateSha256`,
`automaticPromotion:false`, and `status`:

- `completed`: requires `outputState` with a stage-relative regular-file path
  and exact SHA256. Its bytes become the next stage input.
- `review-required`, `rejected`, `no-change`: preserve the original response and
  stop without running later stages or another round.

The existing process capture records commands, exit status, duration and original
stdout/stderr. Infrastructure/capture failure stops as `adapter-failed`, retains
its failure file and does not become participant behavior failure. Invalid
responses, input drift and altered earlier evidence are terminal errors with
partial raw files preserved. Every completed stage's entire evidence tree is
frozen before the next command. Existing output directories are never replaced.
All adapters have their own deadline; at most 40 stage commands execute, with no
transport retry. A repeated evidence-return state digest stops as `no-change`.
A changed digest is only transport progress, not independently verified knowledge
gain: timestamp churn must not be counted as maturation by business gates.

`cycles-result.json` records completed rounds, stage lineage, latest state and
stop reason. Adapter claims are not independently qualified. Authority writes
are not independently verified, qualification stays false and automatic promotion
stays false. A reviewed adapter can perform an explicitly authorized transaction;
the coordinator neither grants that authority nor supplies an admission bypass.
It must preserve the existing review and fixed-baseline drift stops.

Rust integration tests compile a Rust fixture adapter and execute two rounds,
checking state lineage, review/rejection/no-change/infrastructure stops,
borrowed-response rejection, input mutation and fresh-output constraints. These
also verify stage-only environment forwarding and the aggregate deadline budget;
a separate regression retains the ordinary operation deadline ceiling. These
are transport regressions, not Agent runs or full flywheel acceptance. Next work:
connect the existing semantic/program/operation/case/lesson gates to this envelope,
exercise real bounded rounds, then transfer the same coordinator to another
repository while measuring knowledge coverage, task outcomes and cost.

## Completed-boundary continuation

Optional `maximumStagesPerInvocation` (1–40, default 40) bounds dispatches in
one invocation without changing the recipe's overall round/deadline budget.
Each completed stage writes a fresh `checkpoint-N.json` binding the exact recipe,
ordered history, latest state, seen return states and frozen evidence inventory.
A chunk with remaining stages stops as `checkpoint-ready`; completedRounds counts
only complete five-stage rounds, including rounds spanning multiple invocations.

Continue with the same recipe and a fresh absolute output directory:

```sh
agentlab-maintainer-skill-flywheel --execute-flywheel-cycles \
  --recipe reviewed-recipe.json --cycle-checkpoint /absolute/capture/checkpoint-3.json \
  --cycle-checkpoint-sha256 VERIFIED_SHA256 --output /absolute/fresh-continuation
```

The caller explicitly binds the retained checkpoint bytes. The coordinator verifies
the recipe, prior frozen evidence and state before any dispatch, carries the
original history forward and starts at the next stage. A create-new
`continuation-claim.json` in the prior capture permits only one continuation
claim from that capture, including concurrent requests. Completed stages are not
rerun; checkpoint hashes or claims are not authenticated producer identities.
Require the matching final `cycles-result.json` with status `checkpoint-ready`
and the selected latest checkpoint; intermediate checkpoints in a still-running
capture are not continuation authority. Unsealed process-crash captures require
independent reconciliation, not automatic recovery through this entrypoint.

A later `round-*` directory in the checkpoint's capture means dispatch may have
started, even if no result was retained. Refuse continuation in that case. An
existing claim, changed recipe/input/evidence, rejected or review-required stage
must not become an automatic retry. If a process dies after claiming or during
an external mutation, preserve everything and independently reconcile the exact
transaction before constructing a reviewed successor. Never delete a claim or
partial stage to make an uncertain write retryable. This is safe boundary
continuation, not exactly-once external execution or rollback.

Rust subprocess regressions run two rounds in four chunks, verify CLI binding,
preserved lineage and single-use claims, and reject drift and a real failed
dispatch. These tests do not establish real Agent rounds or automatic business
admission. Overall maturity remains 66% based on the separate actual guided
consumption and outcome-return evidence, not on these transport regressions.
