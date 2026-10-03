# Iterative case generation

Use this contract when mining cases from target-repository Maintainer Skills.
The loop improves both the operational knowledge and the case portfolio; it
does not repeatedly sample the same well-known path.

## Readiness ladder

Track each scope through these evidence levels. Higher levels include the lower
ones:

1. **Identity**: repository URL, source revision and path boundary are exact.
2. **Structural**: language, build/test entrypoints and dependency surface are
   inventoried.
3. **Semantic**: responsibility, lifecycle/state behavior and invariants are
   supported by source evidence.
4. **Executable**: editable/context boundaries and an independent Oracle can be
   run in a controlled environment.
5. **Calibrated**: accepted and deliberately wrong variants discriminate the
   intended behavior.
6. **Discriminating**: assessed attempts show useful ability separation without
   leakage, flakiness or infrastructure dependence.

Structural coverage is useful for routing the next analysis round. It MUST NOT
be reported as semantic, executable or calibrated coverage.

## Round loop

### Enter from admitted maintenance evidence

Semantic-refresh loop receipts are not the only input to construction. After
reviewed maintenance results are committed and exported, prepare a scoped input
packet with the Rust bridge:

```sh
agentlab-maintainer-skill-flywheel --prepare-operation-case-inputs \
  --knowledge /absolute/committed-export --scope-id SCOPE \
  --semantic-fact-id ANALYSIS --operation-fact-id VERIFIED_OPERATION \
  --output fresh-operation-case-inputs.json
```

Select both facts explicitly from that cut. The bridge checks all five table
digests, resolves the durable assessment, independently recomputes maintenance
readiness and requires a semantic source Blob matching a retained scope anchor.
Scope anchors are not a complete file inventory; construction must still verify
every selected source Blob against the pinned source checkout.
It preserves the semantic analysis separately from maintenance controls; an
operation receipt alone does not explain a task's responsibility or source paths.
The packet is construction input, not a shadow candidate, bounded-loop receipt,
calibration receipt or frozen case. Do not feed it to a consumer requiring one
of those schemas. Remote commit authenticity and reviewer identity are not
authenticated by this local byte check.

Use its pinned semantic evidence to derive staged demands and a reviewed cohort
through the ordinary construction path below. Retain existing control results
as maintenance evidence, not inherited case calibration: a newly demanded task
still needs an independent Oracle, meaningful wrong implementations, declared
runtime qualification and freeze gates. Repeating preparation under unchanged
inputs yields the same packet and performs no authority writes or executions.

At the admission boundary, compare the complete staged delta with the fixed
committed baseline before writing. Persist an operation fact and its refresh
record atomically; retain the transaction identity before dispatch. On uncertain
completion, reconcile that exact transaction rather than generating another one.
Export only after complete fixed-revision readback agrees with the staged rows,
and retain the original assessment and every inherited operation receipt. The
export may preserve assessed table bytes after payload equality is established;
never turn a staging cut into authority by merely replacing its revision label.
The [real admission replay](../../../release/qualifications/dialog-operation-admission-20261003/summary.json)
exercised this boundary and the Rust input/shadow bridges. It was operator-driven,
not an automatic five-stage round; the shadow request still requires source-Blob
preflight, construction, independent task calibration and runtime qualification.

Translate the packet for the existing shadow constructor with
`--prepare-operation-case-shadow --knowledge /absolute/committed-export
--operation-inputs fresh-operation-case-inputs.json --runtime-target
harmony-emulator --output fresh-shadow-request.json`. This Rust entrypoint
reverifies the entire packet against the current exported cut. The request uses
`agentlab.operation_case_shadow_request.v1`; the existing constructor and
proposal recorder accept that origin explicitly. Candidate lineage retains
`operationInputsSha256`, never a fabricated semantic `loopReceiptSha256`.
Round coverage remains unchanged until new knowledge actually advances.
The constructor checks clean pinned source and every referenced semantic Blob
before launching a participant. This preflight is not process containment.
Retain maintainer-authored drafts separately from captured Agent generation;
neither one sampled draft nor unchanged coverage satisfies cohort breadth.

For an isolated Docker constructor, the source link must name the container's
read-only `/agentlab/case/source` projection, not the host checkout path. The
constructor now prepares that projection from only the semantic fact's exact
Git Blobs, binds its manifest to the request, and rebinds a separate runtime
config without changing the original template. Missing sparse-checkout files
stop before participant dispatch: materialize the pinned files, never substitute
stubs or drop their evidence. Retain the projection, config and runtime receipts;
projection tests are not container execution proof. Constructor transport retries
are explicitly disabled; preserve terminal failures before a fresh attempt.

1. Pin the source set, knowledge cut and latest Maintainer Skill refresh round.
2. Select explicit residual gaps and under-covered scope Skills. Preserve
   diversity across repositories, mechanisms, state/lifecycle boundaries and
   functional versus performance/reliability concerns.
3. Produce a cohort of grounded candidates. Bind every candidate to its scope
   Skills, semantic Skills, program facts and analyses.
4. Construct the task and executable check. Keep the assessed prompt separate
   from reference patches and operator-owned evidence.
5. Calibrate accepted and wrong variants. Record build, environment, Oracle,
   ambiguity and discrimination failures without deleting the candidate.
6. Measure the round, classify gaps, and choose `continue`, `converged` or
   `blocked`. A `continue` decision feeds the next knowledge refresh and/or
   generation round.

## Required measurements

Record at least:

- repository and scope-Skill coverage considered by the round;
- behavior-ready and Oracle-ready scope counts before and after the round;
- generated, retained, rejected and qualified candidate IDs;
- candidate distribution by repository and mechanism;
- construction, build, Oracle and calibration qualification rates;
- rejection reasons and unresolved knowledge/program-analysis/Oracle gaps;
- novelty relative to parent rounds and, once available, ability-separation
  evidence from assessed attempts.

Counts without exact IDs or a bound digest are summaries, not authority.

## Decisions

- `continue`: useful gaps remain and the next round has a concrete objective.
- `converged`: the declared portfolio objective and stop thresholds are met;
  there are no unacknowledged high-priority gaps. Convergence is scoped, never
  a claim that the repository has no more possible cases.
- `blocked`: work cannot advance because a named source, environment, build or
  Oracle dependency is unavailable. Preserve the unblock condition.

`automaticPromotion` remains false in every round. Generation can propose and
rank candidates, but only the existing construction, calibration and freeze
gates can promote a case.
