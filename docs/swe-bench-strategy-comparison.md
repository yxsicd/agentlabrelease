# SWE-bench strategy comparison

This comparison records the design decision for AgentLab's generated-case
flywheel. It compares mechanisms, not leaderboard scores. The external
SWE-bench status was reviewed on 2026-09-24; links below are evidence for that
snapshot and are not mutable release inputs.

## What SWE-bench gets right

SWE-bench turns a resolved GitHub issue and its pull request into a task at the
pre-fix commit. The participant sees the issue statement and repository, but
not the evaluation tests. A patch resolves the task only when both classes of
hidden tests pass:

- `FAIL_TO_PASS` tests demonstrate the requested behavior that was broken at
  the base revision;
- `PASS_TO_PASS` tests demonstrate preservation of previously working
  behavior.

The official harness applies the submitted patch and runs those tests in a
per-instance container. It can separately run the gold patch to qualify the
task and environment. Evaluation outputs retain per-instance reports and test
logs rather than only an aggregate score.

These are strong, reusable principles:

1. freeze a source revision before the fix;
2. keep the solution and grading evidence hidden from the participant;
3. require both behavior repair and regression preservation;
4. execute candidate and reference solutions in fresh, reproducible
   environments;
5. distinguish an unresolved participant from an invalid benchmark or broken
   environment;
6. preserve enough evidence to re-derive every verdict.

AgentLab's curated SWE campaign already follows these principles for four
official SWE-bench Lite seeds. It binds the full official record, task base,
environment-preparation commit and image digest; tests the actual extracted
participant patch and official reference patch independently; and treats a
reference failure as benchmark/Harness failure rather than participant
failure.

## What SWE-bench does not solve

SWE-bench's original dataset is a useful source of methodology, but not a safe
template for automatically accepting generated cases.

SWE-bench Verified was created after professional developers found frequent
underspecified issue statements, unfair tests and unreliable environments in
the original dataset. Three annotators reviewed each sample and the
conservative filter removed 68.3% of reviewed samples; only 500 became the
Verified set. This demonstrates that a mined issue plus a passing historical
PR is not sufficient evidence of a fair case.

The remaining limits are structural:

- a hidden test may be too narrow and reject a behaviorally valid alternative,
  too broad and require behavior absent from the prompt, or too weak and admit
  an incomplete fix;
- public historical issues, patches, tests and release notes can enter model
  training data, so success can measure recall rather than engineering;
- a fixed, mostly Python, single-repository patch benchmark covers only a
  narrow portion of software work;
- the final verdict mainly observes repository tests. It does not normally
  require installation, UI behavior, real device execution, sustained
  performance, power or thermal evidence;
- a binary resolved rate does not expose the sequence of decisions, dependency
  discoveries, deviations and recoveries that made one participant stronger
  than another;
- post-hoc historical tasks inherit the product team's chosen fix and tests;
  that does not prove the task maximally discriminates current agents.

OpenAI reported in February 2026 that SWE-bench Verified was increasingly
contaminated and no longer a reliable frontier signal. A July 2026 audit also
estimated that roughly 30% of SWE-Bench Pro tasks were broken, chiefly because
of overly strict tests, underspecified prompts, low coverage or misleading
prompts. The lesson is not to abandon executable tests; it is to make case
qualification, freshness and independent review first-class, continuously
rechecked artifacts.

## AgentLab advantage

AgentLab is designed around a broader unit of work than a historical patch:

| Dimension | SWE-bench pattern | AgentLab current direction |
| --- | --- | --- |
| Source scope | One repository at one base commit | Explicit source set spanning arbitrary pinned repositories |
| Candidate discovery | Mine resolved issue/PR pairs | Semantic inventory plus program graph and recursive impact discovery |
| Intended difficulty | Historical issue complexity | Select for measured participant discrimination and feed failures into a new analysis cut |
| Interaction | Produce one final patch | Preserve multi-stage and multi-turn execution evidence |
| Functional oracle | Hidden `FAIL_TO_PASS` and `PASS_TO_PASS` tests | Independent staged Oracle with exact receipt and permitted edit scope |
| Runtime boundary | Containerized repository tests | Static gate, assessed-workspace build, Linux Harmony emulator install/launch/UI Oracle |
| Non-functional signal | Normally outside the verdict | Bounded workload and SmartPerf feedback after functional success |
| Failure attribution | Resolved or unresolved plus harness logs | Separate participant, Oracle, scope and infrastructure failures |
| Evolution | Static public dataset variants | Immutable case cuts plus review-required feedback into the next source/analysis cut |
| Publication | Dataset and leaderboard artifacts | Independently versioned components plus lightweight qualified composition |

The strongest advantages are therefore not “more tests.” They are multi-repo
source authority, automatically discovered dependency-aware difficulty,
device-visible behavior, non-functional feedback, and a recursive evidence
loop that can search for cases which separate participant capabilities.

## AgentLab disadvantage and current evidence boundary

The architecture is broader, but its present empirical coverage is much
smaller than SWE-bench's:

1. The multi-repository path is proven on a controlled fixture, not yet on the
   benchmark goal of a representative Harmony source set of at least 20,000
   lines with at least five independently qualified candidate scenarios.
2. One real Linux Harmony assessed campaign proves the static-to-device path
   and separates a strong and weak participant, but does not establish
   population-level discrimination, variance or repeatability across devices.
3. The construction participant, deterministic intent checks and maintainer
   review exist, but there is no Verified-like multi-reviewer qualification
   dataset or measured inter-reviewer disagreement.
4. The independent Oracle is digest-bound, but cases do not yet expose a
   uniform repair-versus-preservation classification equivalent to
   `FAIL_TO_PASS` and `PASS_TO_PASS` across static, device and performance
   gates.
5. Freshness and contamination are not yet explicit case fields. Private
   repositories reduce public leakage but do not prove that a model has not
   seen related code, issues or fixes.
6. SmartPerf currently supplies useful relative CPU and PSS observations on
   the emulator. Absolute power and thermal authority remain unavailable, and
   emulator results are not substitutes for calibrated real-device energy
   measurements.
7. The GitHub static campaign to Linux emulator handoff still needs a portable,
   generated plan; the successful real campaign used an operator-resolved host
   plan.
8. Process-level scoring—per-turn dependency discovery, deviations, recovery,
   decision impact, elapsed time and subjective/objective consistency—is not
   yet one uniform scorecard for every case.

Until these gaps close, AgentLab can claim a richer executable architecture and
one real closed-path proof, not a large, statistically qualified benchmark.

## Adopted qualification model

Every newly generated multi-repository case now carries a qualification matrix
that generalizes the SWE-bench split without copying its single-repository
assumptions:

```json
{
  "schema": "agentlab.case_qualification_matrix.v1",
  "repairChecks": [],
  "preservationChecks": [],
  "stageChecks": [],
  "deviceChecks": [],
  "performanceGuardrails": [],
  "oracleAuthority": {},
  "referenceReplay": {},
  "freshness": {},
  "review": {}
}
```

- `repairChecks` are the generalized `FAIL_TO_PASS`: they fail on the frozen
  baseline and pass on a qualified reference.
- `preservationChecks` are the generalized `PASS_TO_PASS`: they pass before
  and after the reference change.
- `stageChecks` state what must become true after each participant-visible turn
  without exposing the implementation or hidden Oracle.
- `deviceChecks` bind install, launch, UI and state assertions to the exact HAP
  and emulator environment.
- `performanceGuardrails` run only after functional success and must declare
  baseline, repetitions, workload, metric authority and variance policy.
- `oracleAuthority` binds executable bytes, receipt schema and independence
  from the construction participant.
- `referenceReplay` proves the reference passes and deliberately wrong variants
  fail in fresh environments.
- `freshness` records source visibility, issue/fix dates, case construction
  mode, leakage review and the model/tool knowledge boundary.
- `review` records specification fairness, Oracle breadth, coverage and
  difficulty judgments independently of the case constructor.

No aggregate difficulty score may compensate for a failed qualification
dimension. In particular, high participant separation cannot promote an
underspecified or contaminated case.

## Ordered implementation consequences

1. Extend the implemented qualification matrix with evidence-backed
   freshness/contamination declarations and a stronger independent review
   receipt; unknown evidence already remains review-required, never qualified.
2. Generate a portable device-handoff bundle from the static campaign, then
   resolve only host-specific emulator/build paths on the qualified Linux host.
3. Require the device campaign to extend, rather than overwrite, the static
   repair/preservation matrix with exact UI and performance gate receipts.
4. Add independent multi-reviewer adjudication and disagreement measurement;
   default unknown evidence to review-required, never qualified.
5. Run repeated strong/weak/middle participant trials on at least five cases
   from a representative 20,000-line Harmony source set and report confidence
   intervals, exclusions and infrastructure failures.
6. Unify outcome and process measurements into a per-turn scorecard while
   retaining raw trajectories and independently executable verdict evidence.

This ordering copies SWE-bench's most valuable discipline—hidden executable
repair and preservation evidence—while addressing the two failure modes that
now dominate public coding benchmarks: case invalidity and contamination.

## External references

- [SWE-bench paper](https://arxiv.org/abs/2310.06770)
- [Official evaluation guide](https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/evaluation.md)
- [Official harness reference](https://github.com/SWE-bench/SWE-bench/blob/main/docs/reference/harness.md)
- [Introducing SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/)
- [Why SWE-bench Verified no longer measures frontier coding capabilities](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)
- [Separating signal from noise in coding evaluations](https://openai.com/index/separating-signal-from-noise-coding-evaluations/)
