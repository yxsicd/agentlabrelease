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

For the existing Pi/Gateway adapter, select
`examples/real-code-agent/behavior-participant.py` as an explicit argument to a
pinned Python executable and set `participantCompletionRequired:true`. The
controller independently verifies its recorded prompt, request, native lifecycle,
final message and raw completed Gateway exchange before behavior execution. It
also binds the adapter-retained submitted source bytes to the returned proposal.
This reuses the recorded-exchange consumer; producer authentication remains a
separate trust assertion. The adapter uses a 120s native-process watchdog, 60s
Gateway deadline, 12 tool calls, no transport retry, and a fresh state each round.
Set the outer participant command deadline to 180s for capture/cleanup margin.

`participantEnvironmentNames` may explicitly select only Gateway URL/key, Pi
binary, model, provider route and reasoning effort under their existing
`AGENTLAB_*` names. Values are resolved from the operator process at dispatch and
never included in command receipts. No selected environment is forwarded to the
behavior executor. The existing Pi launcher strips the upstream key from its
native child; only its operator proxy receives it. Pin adapter/runtime dependency
files in `immutableInputs`, not credentials. Nested regular capture directories
are retained and checked across rounds; symlinks, excessive nesting, oversized
files and excessive file counts are rejected.

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
the explicit participant-only selection above is the narrow exception.
Credentials must remain private to the owning adapter, never in recipe arguments,
stdout, source Git or released examples. `reviewed:true` records a selection,
not cryptographic authentication or permission inferred from untrusted content.

The recipe optionally accepts `maintainerGuidance` with absolute
`knowledgeDirectory`, `selectionPath`, exact `selectionSha256`, explicit
`repositoryId` and `stage`. The existing Rust binder reconstructs the committed
five-table knowledge cut and selected Skill/fact lineage, requiring exactly the
declared repository at the frozen contract's source revision and stage. All six
knowledge files and the selection are pinned across attempts; the assembled
packet is limited to 128 KiB and retained in operator evidence. Guided execution
requires captured completion. The request retains the same demand/checks/feedback
and includes the same packet each attempt. Pi appends the complete packet to its
prompt, with unchanged 120-second native budget and zero transport retries.
The independent consumer binds guidance intent to that exact request and verifies
full-prompt transmission and final raw completion. It does not prove learning,
provider authenticity or absence of other context in an unguided arm.

The preparer accepts `--guidance-knowledge`, `--guidance-selection` and
`--guidance-stage` together, retaining an external copy for reconstruction.
The main-only Action exposes corresponding optional committed-path inputs; empty
paths preserve the unguided treatment. Applicability is reviewed selection, not
automatic discovery. Fresh guided/unguided runs must use the same source/checks,
model/policy, attempts and total budgets before comparing outcomes. These added
paths have protocol/binding regressions, not a new live guided behavior verdict.

Rust integration tests run real deterministic subprocesses through two attempts:
behavior failure, delivered feedback, revised source and passing recomputation.
Additional cases stop executor infrastructure failures, unchanged attempts and
attempted frozen-input mutation. These are controller regressions, **not live
model success**. Overall maturity remains 54% pending actual authenticated Agent
repair, complete target runtime acceptance, automatic knowledge feedback and
cross-repository transfer with the same controller.
