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
1 through 180000. Commands execute in their fresh stage evidence directory.
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
Do not embed credentials in state. No private environment names are forwarded by
this coordinator; scoped trusted adapters may acquire credentials separately.
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
are transport regressions, not Agent runs or full flywheel acceptance. Next work:
connect the existing semantic/program/operation/case/lesson gates to this envelope,
exercise real bounded rounds, then transfer the same coordinator to another
repository while measuring knowledge coverage, task outcomes and cost.
