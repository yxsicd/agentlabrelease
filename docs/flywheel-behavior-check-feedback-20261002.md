# Generic recorded behavior feedback

Overall flywheel maturity remains54% until autonomous execution/repair evidence
advances the shared loop. This consumer is repository-independent: the operator
freezes task inputs, expected JSON values and control identities; no repository
name, language, framework or behavior predicate is embedded in the Rust gate.

Run the existing binary:

```sh
agentlab-maintainer-skill-flywheel --verify-behavior-checks \
  --contract frozen-checks.json --capture worker-capture.json \
  --output fresh-feedback.json
```

The contract schema is `agentlab.frozen_behavior_checks.v1`. It binds candidate
ID/value SHA256, source revision, original source SHA256, execution method and
compiler SHA256s, declared runtime, worker deadline, checks and control manifest.
Each check has `id`, `input` and `expected` (arbitrary JSON, including null).
Each control has `id`, `role`, `submittedSourceSha256` and
`expectedFailedCheckIds`. Require one baseline, two distinct accepted sources and
at least two distinct wrong sources. Baseline/wrong controls declare intended
failed checks; accepted controls declare none. Optional `agent-attempt` controls
are recorded outcomes, not authenticated Agent identity.

The capture schema is `agentlab.behavior_worker_capture.v1`. It binds the exact
contract bytes and the same execution identities, plus a `workers` array. Each
worker has its declared `id` and an `execution` containing normal `exitCode:0`,
`timedOut:false`, positive bounded integer `durationMs`, original `stdout` and
`stdoutSha256`. Stdout is JSON containing `id`, original/submitted source digests,
exact `submittedSource` bytes and one observation per frozen check. Observations
have `id`, exact `input` and `actual`. Producer `expected`/`passed` fields do not
control scoring: the Rust consumer recomputes exact JSON equality with the frozen
contract. Missing inputs (including missing versus explicit null), repeated or
unknown checks, changed source, changed bindings and failed worker infrastructure
are rejected before behavioral feedback. Limits are256KiB contract,4MiB capture,
128 checks,32 controls and at most60s declared per worker. This is an input bound,
not enforcement of a runner's total execution budget.

Feedback schema `agentlab.behavior_check_feedback.v1` preserves recomputed checks
and routes baseline disagreement, invalid accepted controls and surviving wrong
controls separately. A completed discriminating calibration requests
`execute-agent-attempt`. Recorded Agent failure requests `repair-agent-behavior`;
success requests `review-agent-outcome`. None grants formal case qualification,
authenticates a producer, proves task intent or source ancestry, replays execution,
modifies authority, or automatically runs the requested action. Callers must bind
the observation to trusted Harness lifecycle/source evidence before stronger
acceptance. Do not pass untrusted executable bytes to this read-only consumer.

## Actual retained-capture consumption

The previous frozen upload-task calibration retains six normal-exit workers and
36 scoped checks. An external projection preserves their raw stdout unchanged
and maps their already declared input/expected truth table into this contract.
It is retrospective serialization of retained evidence, not a new execution or
proof that this new JSON envelope was enrolled before the original execution.
The original requirement and predicates were frozen by that calibration method.

Actual CLI consumption returned `execute-agent-attempt` with `qualified:false`.
Contract SHA256:
`98844816f001bf94c7e2fd082b2f51e329fbf7b44f7f3266cdcdc373596758b6`.
Original calibration receipt SHA256:
`f6a083b31d21bf6580da71e3b830706871807a486cdb5361ceb7a1025aae19c8`.
Complete captures/projection remain outside source Git under
`.artifacts/flywheel-action-continuation-20261001/code-workshop-telemetry-source/`.
No live Agent attempt, semantic repair, emulator/RDB qualification or independent
cross-repository transfer is claimed. Next wire this generic feedback into the
existing replaceable participant/contained executor rather than adding a target
repository branch to the shared controller.
