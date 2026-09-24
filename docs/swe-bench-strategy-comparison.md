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

1. The multi-repository path now has a real fixed-revision Harmony source run:
   12,711 analyzed files and 881,650 text lines across two repositories yielded
   404,308 facts and 22 shared external-contract clusters. This clears the
   source-volume and raw-candidate discovery threshold, but none of those
   clusters is yet an independently qualified scenario.
2. One real Linux Harmony assessed campaign proves the static-to-device path
   and separates a strong and weak participant, but does not establish
   population-level discrimination, variance or repeatability across devices.
3. The construction participant, deterministic intent checks and maintainer
   review exist, but there is no Verified-like multi-reviewer qualification
   dataset or measured inter-reviewer disagreement.
4. The independent Oracle is digest-bound. One real Harmony UI candidate now
   has a controlled `FAIL_TO_PASS` replay: the frozen baseline stays on
   `pages/Index`, while a one-line page-registration variant reaches
   `pages/UserAgent_four` and renders `Example Domain` under the exact same
   scenario. Three independent routes now supply real `PASS_TO_PASS`
   preservation checks on both HAPs: DomStorage binds route identity plus an
   absent Index control, while UserAgent_one and Cache_two each bind route
   identity plus positive visible semantics. This is still not a uniform
   contract: full pre-existing-route coverage, independent review and
   reference/gold acceptance remain absent.
5. Freshness and contamination are now explicit case fields. The controlled
   calibration truthfully records that it was synthesized from public source,
   published in the release PR and is therefore ineligible for future claims
   of unseen-Agent discrimination. A new private or held-out case cut is still
   required for comparative evaluation; private source alone would not prove
   training exclusion.
6. SmartPerf currently supplies useful relative CPU and PSS observations on
   the emulator. Absolute power and thermal authority remain unavailable, and
   emulator results are not substitutes for calibrated real-device energy
   measurements.
7. The portable static-to-Linux handoff is now implemented and qualified on
   `hwlinux`, but it has one real campaign rather than cross-host repeatability
   evidence.
8. Assessed feedback can now enter a separately reviewed new source/analysis
   cut and survive into successor-case lineage. It has deterministic regression
   coverage, but has not yet been exercised on a representative real source
   update with several candidate cases.
9. Process-level scoring—per-turn dependency discovery, deviations, recovery,
   decision impact, elapsed time and subjective/objective consistency—is not
   yet one uniform scorecard for every case.
10. Real-source candidate precision remains uneven. The largest module-level
    clusters span 1,567 to 3,018 files, far wider than SWE-bench's issue-level
    repair contracts. The new API-call pass proves that one `@kit.ArkWeb`
    surface can shrink from 176 files to six exact call sites, then to two
    proposed cross-repository targets. That is useful localization evidence,
    not yet semantic proof: the lifecycle hypothesis, five-file edit surface,
    repair/preservation checks and Oracle still require independent review and
    calibration. The two source projects now have revision-bound project roots
    and build modules. The API 20 guide project has two clean, member-equivalent
    baseline HAP builds; one exact HAP also installs, launches and retains a live
    process on `hwlinux`. A stronger visible-text Oracle then exposed an
    important calibration failure: the earlier `assert-no-text UserAgent_four`
    searched serialized layout metadata and falsely failed a successful route
    because `pagePath=pages/UserAgent_four` contained the same substring. The
    replacement Oracle asserts visible `Example Domain`; it fails on the exact
    baseline HAP and passes on a controlled one-line page-registration variant.
    A separate DomStorage scenario passes before and after the variant, closing
    the first real `PASS_TO_PASS` device check. Its first form—requiring remote
    Web content within two seconds—was rejected after a route-success/content-
    delay failure; the retained form checks that an Index-only control is absent
    and separately binds the observed `pages/DomStorage` path. Two more
    preservation routes now bind `pages/UserAgent_one` plus visible
    `getUserAgent`, and `pages/Cache_two` plus visible `removeCache`, on both
    baseline and known-fix HAPs. The three-route matrix qualifies a stronger
    candidate repair/preservation pair and Oracle-design lesson, not a reviewed
    reference repair, exhaustive regression suite, business UI case or unseen
    Agent benchmark. The API 23/24 code-workshop
    build remains unqualified because matching DevEco 6.1 tooling is absent, and
    the exact `hwlinux` host still has only the emulator/runtime substrate rather
    than a source-build SDK.
11. The richer API-localizing full run takes 257.65 seconds and emits roughly
    297 MiB of fact rows plus 25 MiB of difficulty candidates. Git blob reads
    are batched, but AST analysis is still single-process and there is no
    revision-aware incremental cache or early candidate prefilter.

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

1. Cut a new private or held-out case set with the implemented
   freshness/contamination declaration, keep participant runs blind, and add a
   stronger independent review receipt; unknown evidence remains
   review-required, never qualified.
2. Broaden `PASS_TO_PASS` coverage beyond the candidate's three qualified
   routes, independently review Oracle breadth/fairness, and only then accept a
   reference repair. The device campaign must extend, rather than
   overwrite, the static repair/preservation matrix with exact UI and
   performance receipts.
3. Exercise the reviewed feedback-to-analysis bridge on a real source update
   and prove that the successor case retains prior failure lineage without
   mutating the old case.
4. Add independent multi-reviewer adjudication and disagreement measurement;
   default unknown evidence to review-required, never qualified.
5. Localize at least five of the 22 real shared-contract clusters into narrow
   change hypotheses, then add repair/preservation checks and independent
   review before running repeated strong/weak/middle participant trials.
   Report confidence intervals, exclusions and infrastructure failures.
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
