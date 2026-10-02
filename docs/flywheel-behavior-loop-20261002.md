# Generic bounded diagnostic repair controller

The Rust controller connects reviewed participant and executor adapters to the
independent recorded behavior consumer. Repository/framework selection belongs
to the adapter and frozen inputs, not the scheduling implementation.

```sh
agentlab-maintainer-skill-flywheel --execute-behavior-loop \
  --contract frozen-checks.json --capture calibration-capture.json \
  --recipe reviewed-loop-recipe.json --output NEW_EXTERNAL_DIRECTORY
```

The recipe schema is `agentlab.behavior_loop_recipe.v1`, with `reviewed:true`,
`automaticPromotion:false`, exact `contractSha256` and `captureSha256`, a nonempty
`taskDemand`, `maximumAttempts` from 1 to 3, `immutableInputs` (absolute paths and
SHA256s), `participantCommand` and `executorCommand`. Commands use the existing
operation capture format: absolute `program`, exact `programSha256`, string
`args`, `cwd:"."`, bounded `timeoutMs`. Exactly one argument must be `{request}`;
the controller substitutes the absolute request file. No shell is implicitly
added. Script/compiler/source dependency files must be enumerated in
`immutableInputs`; a program digest does not transitively pin its dependencies.
Participant time is bounded to 180s per attempt; executor time is bounded by
the frozen worker deadline, at most 60s. There are no transport retries.

Participant adapters read `agentlab.behavior_participant_request.v1` containing
the demand, original/current submitted source and previous recomputed feedback.
Return one stdout JSON object with nonempty `submittedSource` (at most 256KiB).
Executor adapters read `agentlab.behavior_executor_request.v1`, execute the
submitted source and return the original worker JSON format described in
[behavior feedback](flywheel-behavior-check-feedback-20261002.md). Checks supplied
to the executor contain only IDs and frozen inputs, not expected answers.
Every observed check must remain present, including checks that passed before.

Each attempt derives a contract by appending exactly its source identity to the
unchanged calibration controls and frozen checks. This is a new byte identity,
not rewriting or claiming the original contract contained an unknown Agent
source. Actual executor stdout/process evidence is combined with the retained
calibration and independently recomputed. A failed behavioral attempt delivers
feedback to the next participant; success stops for review. Identical repeated
failed source suppresses further executor dispatch. Infrastructure failure stops
without behavioral repair and preserves existing raw process files. Earlier
completed attempts and immutable input bytes are checked before/after subsequent
dispatch; existing output directories are never overwritten.

Calibration sources must be distinct, but a participant may legitimately submit
the same bytes as an accepted implementation. That does not authenticate its
identity or prove learning. Each attempt captures raw stdout/stderr, bounded
process lifecycle, derived contract, combined capture and reconstructed feedback.
Partial failure files stay retained even when no final loop result is emitted.

This is an **operator-selected trusted diagnostic command boundary**, not an
untrusted-code security sandbox, formal Harness Session/Fork or authenticated
Agent lifecycle. The adapter must supply actual platform isolation and existing
trusted Gateway/participant capture before live assessment. The controller
clears inherited process environment using the existing capture primitive;
credentials must remain private to the owning adapter, never in recipe arguments,
stdout, source Git or released examples. `reviewed:true` records a selection,
not cryptographic authentication or permission inferred from untrusted content.

Rust integration tests run real deterministic subprocesses through two attempts:
behavior failure, delivered feedback, revised source and passing recomputation.
Additional cases stop executor infrastructure failures, unchanged attempts and
attempted frozen-input mutation. These are controller regressions, **not live
model success**. Overall maturity remains 54% pending actual authenticated Agent
repair, complete target runtime acceptance, automatic knowledge feedback and
cross-repository transfer with the same controller.
