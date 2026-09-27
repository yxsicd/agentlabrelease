# Case execution state and derived-case bridge

AgentLab keeps reusable case knowledge separate from concrete execution
instances. An Attempt result never mutates `evaluation_cases` and a captured
checkpoint never becomes a runnable case merely because its bytes exist.

The additive bridge has twelve explicit artifacts:

- `agentlab.case_execution_state.v1` binds an existing frozen case, participant
  experiment plan, assessed Attempt, Agent context evidence, captured source
  tree and environment identity without changing any producer contract;
- `agentlab.case_derivation.v1` binds one assessed difficulty observation to
  one source state and declares a requested fork policy. It is always
  `review-required`, `caseReady=false` and `automaticPromotion=false`;
- `agentlab.case_model_graph.v1` joins those derivations into an immutable
  directed acyclic graph. It distinguishes a difficulty-only candidate from a
  frozen, independently calibrated case and records both branch depth and the
  deepest qualified prefix;
- `agentlab.case_edge_qualification.v1` is the independent Harness receipt that
  proves the selected Agent/workspace fork policy actually restored the parent
  cut, excluded later parent changes and produced an independently continuing
  child. Case calibration alone cannot substitute for this receipt;
- `agentlab.case_path_inputs.v1` binds one ready graph terminal to exactly one
  existing blind participant/evaluator cut per path node;
- `agentlab.case_path_execution_plan.v1` freezes those nodes and qualified
  transitions into an ordered execution plan without copying evaluator-only
  material into the participant view;
- `agentlab.case_path_participant_matrix.v1` predeclares Agent, model and
  environment configurations as independent dimensions, then names the exact
  cells and single-variable comparison pairs before outcome data exists;
- `agentlab.case_path_dispatch_plan.v1` digest-binds the frozen path and matrix,
  computes expected attempt/stage counts and records the remaining runtime and
  blind-dispatch qualification gates;
- `agentlab.case_path_dispatch_qualification.v1` records independent, exact
  per-cell runtime and blind-boundary evidence;
- `agentlab.case_path_qualified_dispatch.v1` binds that evidence to the frozen
  dispatch and is the first artifact allowed to state `readyForDispatch=true`;
- `agentlab.case_path_attempt_input.v1` records one completed, qualified
  participant/trial path prefix with exact pre/post state, check, transition and
  optional performance/power/thermal evidence per stage;
- `agentlab.case_path_attempt_record.v1` independently derives the overall
  verdict and, at the first failed stage, emits a review-only next-difficulty
  candidate bound to that stage's post-state.

The schemas are
[`case-execution-state.schema.json`](../schemas/case-execution-state.schema.json),
[`case-derivation.schema.json`](../schemas/case-derivation.schema.json),
[`case-model-graph.schema.json`](../schemas/case-model-graph.schema.json),
[`case-edge-qualification.schema.json`](../schemas/case-edge-qualification.schema.json),
[`case-path-inputs.schema.json`](../schemas/case-path-inputs.schema.json), and
[`case-path-execution-plan.schema.json`](../schemas/case-path-execution-plan.schema.json),
[`case-path-participant-matrix.schema.json`](../schemas/case-path-participant-matrix.schema.json),
[`case-path-dispatch-plan.schema.json`](../schemas/case-path-dispatch-plan.schema.json),
[`case-path-dispatch-qualification.schema.json`](../schemas/case-path-dispatch-qualification.schema.json),
[`case-path-qualified-dispatch.schema.json`](../schemas/case-path-qualified-dispatch.schema.json),
[`case-path-attempt-input.schema.json`](../schemas/case-path-attempt-input.schema.json),
and [`case-path-attempt-record.schema.json`](../schemas/case-path-attempt-record.schema.json).

## Existing authority remains unchanged

The sidecars reference existing files by relocation-safe path, byte length and
SHA-256. They do not replace these authorities:

- the frozen `agentlab.multi_repo_evaluation_case.v1` remains the case contract;
- `agentlab.participant_experiment_plan.v1` remains the pre-outcome Agent and
  runtime configuration;
- the Harness decision package remains the Attempt verdict;
- SessionFS receipts remain the workspace snapshot/fork authority;
- assessment feedback and the reviewed feedback-analysis cut remain the route
  into a later maintenance cut.

Native Agent session bytes and captured workspaces are execution-instance
evidence. They must not be committed to this release repository. The sidecar
may travel with an evidence artifact and refers to those bytes by digest.

## Restore capability is a vector

The state records semantic, Agent configuration, Agent context, workspace,
environment and verification capabilities separately, then provides a derived
profile for convenience. A captured native session is only
`native-session-candidate`; it is not qualified for restoration until the same
adapter/version restores it and the Harness revalidates the postconditions.
Likewise, an uploaded source tree is captured evidence, not a formal SessionFS
snapshot.

Fork policy is independent from capture:

- `fresh-agent-continuation` restores the captured world and attaches an empty
  Agent context;
- `same-agent-continuation` requests `preserve-native` and therefore adds a
  native-session compatibility and restoration gate;
- `replace-agent` and `semantic-transfer` retain lineage while changing the
  participant boundary;
- `minimal-reproduction` and `compound-extension` create reviewed candidate
  reductions or longer paths.

## Commands

Build the Rust tool:

```sh
cargo build --locked --release -p agentlab_code_analysis \
  --bin agentlab-case-state
```

Compose one state from existing evidence:

```sh
target/release/agentlab-case-state compose \
  --root /evidence \
  --case /evidence/case/evaluation-case.json \
  --experiment-plan /evidence/participant-experiment-plan.json \
  --attempt-summary /evidence/runs/tier-00-1/summary.json \
  --decision-package /evidence/runs/tier-00-1/decision-package.json \
  --initial-state /evidence/runs/tier-00-1/initial-source-state.json \
  --final-state /evidence/runs/tier-00-1/final-source-state.json \
  --workspace /evidence/runs/tier-00-1/workspace \
  --event-log /evidence/runs/tier-00-1/participant-protocol.json \
  --native-session /evidence/runs/tier-00-1/participant-state/pi-session.jsonl \
  --attempt-id tier-00-1 \
  --output /evidence/execution-states/tier-00-1.json
```

Propose a child without promoting it:

```sh
target/release/agentlab-case-state derive \
  --root /evidence \
  --state /evidence/execution-states/tier-00-1.json \
  --feedback /evidence/assessment-feedback-candidates.json \
  --candidate-id assessment-feedback-0123456789abcdef0123 \
  --mode fresh-agent-continuation \
  --output /evidence/case-derivations/proposal.json
```

Add the proposal to a case graph:

```sh
target/release/agentlab-case-state graph \
  --root /evidence \
  --parent-case /evidence/case/evaluation-case.json \
  --derivation /evidence/case-derivations/proposal.json \
  --output /evidence/case-model-graphs/0001.json
```

To extend a path, the candidate must first complete normal maintainer authoring,
independent Oracle calibration, freezing and independent restore verification.
The graph node identity remains stable independently of the final case identity.
The resulting evaluation case may retain the proposed `candidateCaseId`, or it
may use the existing case construction identity when its
`lineage.feedbackAnalysisCut.feedbackCandidateId` binds the original derivation
difficulty. Qualify the exact node and incoming edge as a separate immutable
graph revision:

```sh
target/release/agentlab-case-state qualify \
  --root /evidence \
  --graph /evidence/case-model-graphs/0001.json \
  --qualified-case /evidence/qualified-cases/child.json \
  --edge-qualification /evidence/qualifications/edge-0001.json \
  --output /evidence/case-model-graphs/0002.json
```

The edge receipt binds the exact predecessor graph, edge, derivation, fork
policy and final case bytes. It must carry independent Harness evidence for the
portable fork postconditions. In particular, `preserve-native` also requires a
qualified native-session restoration; merely retaining native session bytes is
insufficient. Only after `qualify` succeeds can another state-derived difficulty
be appended:

```sh
target/release/agentlab-case-state graph \
  --root /evidence \
  --graph /evidence/case-model-graphs/0002.json \
  --parent-case /evidence/qualified-cases/case-candidate-....json \
  --derivation /evidence/case-derivations/next.json \
  --output /evidence/case-model-graphs/0002.json
```

This rule is what makes a depth-N graph a sequence of verified cases rather
than a list of increasingly speculative prompts. Branches may share a qualified
parent; every outgoing edge still carries its own difficulty evidence and fork
policy.

Freeze one ready path after preparing a normal blind cut for every node:

```sh
target/release/agentlab-case-state freeze-path \
  --root /evidence \
  --graph /evidence/case-model-graphs/ready.json \
  --path-inputs /evidence/case-path-inputs.json \
  --output /evidence/case-path-execution-plan.json
```

`case-path-inputs.json` binds the exact graph ID/digest, one
`readyPathNodeId`, and the cut receipt plus participant/evaluator manifests for
every root-to-terminal node. The command reconstructs the unique path, checks
every node and transition, recomputes every blind bundle file digest, rejects
unbound files and path traversal, and rejects byte-identical files across the
participant/evaluator boundary. It also requires an Oracle and reference in
every evaluator bundle.

The frozen plan uses `sequential-qualified-path`: stage zero starts at the root
case and each later stage carries its exact incoming fork policy and edge
qualification. The participant receives only the current stage participant
bundle. Evaluation cases, evaluator manifests, Oracle/reference inventory,
edge qualifications and operator evidence remain outside that mount.

Structural freezing deliberately leaves `readyForExecution=false`. Runtime
filesystem/network isolation and authenticated blind review remain operational
facts that a structural plan must not manufacture.

Predeclare the orthogonal participant matrix and bind it to the frozen path:

```sh
target/release/agentlab-case-state predeclare-path \
  --root /evidence \
  --path-plan /evidence/case-path-execution-plan.json \
  --participant-matrix /evidence/case-path-participant-matrix.json \
  --output /evidence/case-path-dispatch-plan.json
```

The input defines independent `agentConfigurations`, `modelConfigurations` and
`environmentConfigurations`; cells reference one ID from each collection. This
avoids treating a model name as the Agent identity or hiding runtime changes in
a participant label. Every predeclared cell must be covered by at least one
comparison pair, and each pair must change exactly its declared dimension:
Agent, model or environment. Adapter, driver and environment-lock bytes are
recalculated under `--root`; the runtime image and method revision use immutable
identities. The matrix must exist before attempts and cannot be inferred from
their outcomes.

The resulting dispatch plan calculates trials, attempts and stage executions,
but deliberately remains `readyForDispatch=false`. It does not claim that the
runtime image is portable, that current-stage-only mounts/network controls were
observed, or that the evaluator received its separate authenticated bundle.
Those per-cell runtime and blind-dispatch receipts are the next qualification
gate.

After an independent Harness has produced evidence for every predeclared cell,
compile the qualification without changing the matrix:

```sh
target/release/agentlab-case-state qualify-dispatch \
  --root /evidence \
  --dispatch-plan /evidence/case-path-dispatch-plan.json \
  --dispatch-qualification /evidence/case-path-dispatch-qualification.json \
  --output /evidence/case-path-qualified-dispatch.json
```

Every qualification row must match the cell's environment and immutable runtime
image, bind distinct runtime and blind-dispatch evidence bytes, and affirm the
portable startup, current-stage-only participant mount, evaluator separation,
network policy and fresh-trial boundary postconditions. Missing, duplicate,
drifted or mismatched cells fail closed. The qualified dispatch authorizes only
the predeclared attempts; it still has `automaticPromotion=false`, and observed
stage verdicts remain execution-instance state rather than reusable case truth.

Record one completed attempt only under the exact qualified dispatch:

```sh
target/release/agentlab-case-state record-attempt \
  --root /evidence \
  --qualified-dispatch /evidence/case-path-qualified-dispatch.json \
  --attempt-input /evidence/attempts/participant-a-trial-1.json \
  --output /evidence/attempt-records/participant-a-trial-1.json
```

The executed stages must be a contiguous prefix of the frozen path. Each stage
binds its pre/post state, independent checks and transition evidence. Functional
verdicts are recalculated from checks rather than trusted as labels. Resource
observations are orthogonal: performance, power and thermal can be absent,
within-envelope or violations, but measured outcomes require exact evidence.
Execution stops at the first functional, execution or resource failure; a
passing Attempt must reach the terminal stage.

A failure creates only `case-difficulty-candidate-*`, bound to the failing
stage and its post-state with `caseReady=false`. It can feed the existing review
and derivation loop, but cannot become a reusable case without the normal
semantic review, Oracle calibration, freeze and restore qualification gates.

The multi-repository assessed campaign currently runs all three operations in
shadow mode. It emits each immutable graph revision plus a final convenience
copy. Sidecar failure does not change the established campaign verdict or
publication gates. Promotion to a required gate should happen only after
retained Action evidence proves stable composition and restore qualification.

## Long-horizon evolution

The graph is an index, never a second case authority. It binds exact derivation,
case and edge-qualification bytes, carries a predecessor-graph digest, and
derives node/edge counts, leaf identities, maximum depth and maximum qualified
depth. `readyPathNodeIds` lists every depth-two-or-greater terminal whose entire
root-to-node path has executable calibrated cases and restore-qualified edges.
`longHorizonReady` means at least one such path exists; a pending sibling branch
does not invalidate an already qualified path. The all-nodes/all-edges fields
remain stricter whole-graph diagnostics.

Only a reviewed, independently calibrated child is imported into reusable
`evaluation_cases`; edge qualification and raw execution evidence remain in the
evaluation-instance repository. All raw states, rejected proposals and partial
failures are retained.
