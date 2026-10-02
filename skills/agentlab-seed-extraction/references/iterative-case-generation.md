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
