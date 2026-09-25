# SWE-bench strategy comparison

This comparison records the design decision for AgentLab's generated-case
flywheel. It compares mechanisms, not leaderboard scores. The external
SWE-bench status was reviewed on 2026-09-25; links below are evidence for that
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

## The SWE family contains three different case-source strategies

It is important not to treat every SWE-style dataset as one strategy. They
solve different parts of the case-supply problem:

| Strategy | Representative system | Case source | Main strength | Main limitation |
| --- | --- | --- | --- | --- |
| Historical repair mining | SWE-bench | Resolved issue, associated PR and changed tests | Natural developer intent and an existing human repair | Passive coverage, historical-test bias and public-data contamination |
| Continuously refreshed repair mining | SWE-bench-Live and SWE-rebench | Newly merged issues and PRs, with automated environment construction and filtering | Freshness, repository breadth and a repeatable supply pipeline | Fresh is not automatically fair; noisy specifications and brittle environments remain, and model release date is only a contamination proxy |
| Executable fault synthesis | SWE-smith | Procedural or model-written mutations, PR inversion and combined validated bugs | High-volume generation with an exact source revision and known inverse patch | A test-detectable mutation need not be a realistic maintenance task, and existing test coverage determines what can be generated |

SWE-smith's most reusable mechanism is the validation cut, not any individual
mutation recipe. It first records the original suite's passing tests, applies a
candidate fault, and retains it only when at least one existing test becomes
`FAIL_TO_PASS` while at least one remains `PASS_TO_PASS`. Its generation and
validation phases can run incrementally and skip already processed repositories.
This is a strong production pattern for AgentLab's seed factories.

The limits matter just as much. A synthesized regression can have an exact
executable Oracle yet lack a plausible user-visible scenario. Combining several
single-entity mutations can increase patch size without producing a coherent
dependency problem. Conversely, historical mining supplies realistic intent
but only where humans already reported, fixed and tested a problem. Neither
source strategy discovers by itself the cross-repository semantic obligations
or capability-separating cases that AgentLab targets.

SWE-bench Multimodal also confirms that screenshots and UI context can be part
of the task statement. That is useful input coverage, but it is different from
AgentLab's stronger target: install the produced HAP, drive the application and
grade exact route, visible behavior and bounded performance evidence inside the
runtime environment.

That runtime advantage is valid only when Harmony cases also respect the
platform test boundary. AgentLab now treats `src/ohosTest` Instrument Test with
`@ohos/hypium`, Hypium Local Test and DevEco Testing Hypium UI as standard
lanes. Its compact shell `uitest` scenarios are supplemental product Oracles,
not replacements for standard test sources and reports. A case cannot claim
Harmony standard-test execution without a passing receipt bound to the exact
case, source set and project tree.

### Adopted hybrid supply decision

AgentLab should therefore keep two independent candidate lanes and one shared
qualification gate:

1. a **natural lane** mines fresh issue/PR history and operator-reported failures
   to preserve realistic intent;
2. a **derived lane** uses semantic/program-analysis obligations, controlled
   mutations and prior participant failures to generate targeted difficulty;
3. both lanes must pass the same baseline/reference/alternative-valid/wrong-
   variant calibration, prompt-fairness review, freshness record and executable
   repair/preservation matrix before becoming cases;
4. lane origin remains a scorecard stratum. Natural and derived tasks are never
   silently pooled, because they make different claims about real-world
   representativeness;
5. case selection is based on measured discrimination only after validity is
   established. High separation never rescues an artificial or unfair case.

This hybrid is the clearest strategic advantage over copying one SWE pipeline:
natural tasks anchor realism, derived tasks supply scale and directed coverage,
and runtime qualification supplies the end-to-end behavior boundary. It is
also more expensive, so qualified-case yield and cost per qualified case must
become first-class operating metrics.

The natural lane now has an implemented normalization boundary for coordinated
multi-repository historical repairs and operator-reported failures. It binds
exact repository revisions and content-addressed evidence, then joins the same
reviewed cohort and qualification chain as analyzer-derived candidates. This
closes a mechanism gap relative to SWE-bench-style repair mining, but it is not
yet empirical coverage: no fresh held-out natural record has completed
independent review, calibration, freeze and runtime qualification. The current
proof is a mixed natural/derived fixture, so claims of natural-case yield or
representativeness remain prohibited.

The first automated supply step now collects public GitHub repairs on trusted
main. Unlike permissive URL scraping, it requires each affected repository's
merged PR to bind the declared base and fix commits, verifies declared affected
and test paths against the retained patches, and independently reconstructs
the normalized candidate before preserving the workflow artifact. This gives
AgentLab a reproducible SWE-style mining boundary without treating public
history as a valid benchmark by default. Artifact-to-mixed-cohort automation
now verifies both trusted-main source runs, reconstructs their exact artifacts,
requires a common pinned source set and emits a digest-bound mixed-source
receipt before proposing the shared review-required cohort. The existing
independent reviewer accepts only the original analyzer proposal workflow or
this exact mixed workflow and revalidates the appropriate source receipt. The
mechanism is locally tested but has not run from merged trusted `main`; a
genuinely fresh independently qualified record is still outstanding.

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

One methodological advantage over a single aggregate pass rate is now
executable rather than aspirational: AgentLab signs the ordered three-to-eight
model experiment, route and trial count before attempts, then requires every
adjacent capability tier to separate. This targets the frontier where cases are
informative, while preventing a convenient weak/middle/strong order from being
chosen after outcomes are visible. It complements rather than replaces
SWE-bench's stronger assets: a large recognizable task population, mature
container harnesses, broad model comparisons and extensive external use.

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
   clusters is yet an independently qualified scenario. A new trusted-main
   exact-analysis workflow accepts arbitrary public HTTPS repositories at exact
   commits, retains a digest-bound native analysis run, and makes a separately
   verified run the only input to cohort proposal. A current-method local
   reproduction now freezes a 97-member eligible denominator and a six-member
   specificity-aware proposal before case construction or participant outcomes.
   Metadata-first cloning plus bounded 8/32-KiB Git refetch tiers reduced the
   GitCode transfer boundary to 25 promisor-fetched large blobs. The workflow
   is tested but has not yet run on trusted `main`, and the proposed six still
   require an independent cohort decision.
2. One real Linux Harmony assessed campaign proves the static-to-device path
   and separates a strong and weak participant, but does not establish
   population-level discrimination, variance or repeatability across devices.
   The repository now implements a signed pre-outcome three-to-eight-profile
   campaign and plan-bound v3 suite scorecard, but no real weak/middle/strong
   trusted-main campaign has exercised it yet.
3. The construction participant, deterministic intent checks and maintainer
   review exist. A new exact-digest review protocol now requires at least two
   constructor-distinct reviewer records, four explicit verdict dimensions and
   an adjudicated disagreement rate. Trusted-main workflows now bind decisions
   to distinct GitHub actors and verify GitHub OIDC/Sigstore attestations before
   producing a second attested adjudication. The protocol has not yet produced a
   real reviewed case, and there is still no representative Verified-like
   dataset or measured population-level reviewer disagreement. A trusted-main
   population workflow now freezes multiple adjudication run IDs, reverifies
   every member, reports per-dimension disagreement with Wilson intervals and
   signs the exact cohort report; it has not yet been exercised on a real case
   population and cannot qualify representativeness by itself.
   The discovery-to-construction gap is now closed mechanically: a trusted-main
   proposal freezes all eligible candidates, exclusions and strata; a separate
   exact-digest review predeclares at least two members; and model construction
   accepts only one verified cohort member per run. This imports SWE-bench's
   curation discipline without claiming a Verified-like population. Frozen
   evaluator cases and the v2 population report now bind that cohort end to end,
   reject post-hoc candidate substitution, and retain unadjudicated selections
   in the case-yield denominator. The mechanism has not yet been exercised over
   the 22 real-source clusters, so real selected-to-qualified yield remains
   unmeasured. Generic bounded construction is now mechanically closed: an exact
   proposal/review pair freezes editable and context paths plus an operator-owned
   behavior/Oracle contract before the model runs, and construction rematerializes
   the arbitrary pinned repositories instead of the deterministic fixture. The
   executable calibration boundary is now generic too: a separate proposal and
   exact-digest review bind the driver, Oracle, reference tree and declared
   wrong variants before execution. Case freeze consumes only that reviewed
   bundle and records a run receipt binding all executable inputs. This closes
   the mechanism. Public CI now executes one 38-phase deterministic golden path
   across analysis, cohort, construction, calibration, blind dispatch and
   baseline/reference discrimination, so cross-phase compatibility is directly
   proven rather than inferred from isolated tests. It is still a fixture with
   machine-authored review identities; no arbitrary real-source bundle has yet
   been human-reviewed and executed, so real selected-to-qualified yield remains
   unmeasured.
4. The independent Oracle is digest-bound. One real Harmony UI candidate now
   has a controlled `FAIL_TO_PASS` replay: the frozen baseline stays on
   `pages/Index`, while a one-line page-registration variant reaches
   `pages/UserAgent_four` and renders `Example Domain` under the exact same
   scenario. All eight pre-existing Index routes now supply real `PASS_TO_PASS`
   preservation checks on baseline, known-fix and alternative HAPs: 24 device
   runs in total, with four routes binding positive visible semantics. A second,
   structurally distinct named-route implementation changes two ArkTS files,
   shares no changed path
   with the page-registration variant, leaves `main_pages.json` byte-identical
   to the failing baseline, and passes the same target plus all eight
   preservation scenarios on the same Linux emulator. This is direct evidence
   that the UI Oracle is not merely recognizing the known-fix implementation.
   A meaningful wrong implementation then kept the registered page set but
   routed the `UserAgent_four` control to `pages/UserAgent_three`. Both pages
   render `Example Domain`, so the earlier visible-text-only Oracle falsely
   passed it. Scenario v2 now asserts the exact active `pagePath` before visible
   semantics. On one four-HAP replay the route-aware verdicts were baseline
   FAIL, known-fix PASS, alternative-valid PASS and wrong-route FAIL, all with
   infrastructure available. This adds a real negative discrimination point
   and closes pre-existing-route coverage for this sample, but independent
   review, reference/gold acceptance and unseen-Agent evidence remain absent.
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
   `hwlinux`. A completed-device-evidence importer now binds every bundle member,
   independently recovers the authoritative static handoff, reconstructs the
   discrimination report under trusted-main code, attests the report and import
   receipt separately, and lets the suite preserve source-method versus import-
   workflow revisions. The mechanism has tamper and lineage-drift regression
   coverage, but the retained historical canary has not yet passed through a
   merged trusted-main import run, and there is still one real campaign rather
   than cross-host repeatability evidence.
8. Assessed feedback can now enter a separately reviewed new source/analysis
   cut and survive into successor-case lineage. It has deterministic regression
   coverage, but has not yet been exercised on a representative real source
   update with several candidate cases.
9. Multi-repository assessment now emits operator-owned per-stage timing,
   changed/unauthorized paths, scope verdicts and Oracle recovery/regression.
   Collection independently reconstructs that process aggregate, discrimination
   reports retain process coverage and participant Wilson intervals, and a
   trusted-main suite composer joins those results to the authenticated review
   population. The assessed Harmony campaign now adds independently bound
   build/emulator duration, UI action/check, workload-action and SmartPerf-sample
   evidence to the same process contract. The multi-repository protocol can
   now capture a participant's pre-verdict prediction and confidence, then
   independently report Oracle agreement and Brier score. This closes the
   mechanism for subjective/objective consistency, but the shipped mock is not
   evidence about a real model and adapters must not synthesize an unreported
   claim. A new dependency-discovery v2 path removes the allowed-edit surface
   from the participant task, manifest and stage request. Hidden obligations
   are derived from exact-revision program facts, may accept several supported
   dependency relations, score required-obligation recall, and leave extra
   claims unadjudicated instead of inventing precision. Native Pi final messages
   now carry a strict structured claim block; missing and invalid submissions
   remain distinct from reported claims, and trusted-main review/campaign
   workflows carry the explicitly reviewed contract and evaluator-only facts
   end to end. This closes the mechanism and deterministic fixture, not
   real-model evidence: no repeated real Agent campaign has yet established
   dependency-discovery discrimination.
   Historical/gold touched paths remain explicitly ineligible as a unique
   answer. Equivalent coverage for standalone or non-emulator device adapters
   also remains open.
10. Real-source candidate precision remains uneven. The largest module-level
    clusters span 1,567 to 3,018 files, far wider than SWE-bench's issue-level
    repair contracts. The new API-call pass proves that one `@kit.ArkWeb`
    surface can shrink from 176 files to six exact call sites, then to two
    proposed cross-repository targets. That is useful localization evidence,
    not yet semantic proof: the lifecycle hypothesis, five-file edit surface,
    repair/preservation checks and Oracle still require independent review and
    calibration. Current-method proposal now makes this precision distinction
    explicit: 19 of 22 module-contract candidates have an API-call-specific
    candidate over an equal or subset file set. They remain visible in the
    denominator, while selection advice prevents the broader row from consuming
    review budget by default. For example, the two-file `@kit.TelephonyKit`
    module row points to the same two files' narrower `call.makeCall` row. This
    is a proposal-quality improvement, not semantic qualification of that call
    contract. The two source projects now have revision-bound project roots
    and build modules. The API 20 guide project has two clean, member-equivalent
    baseline HAP builds; one exact HAP also installs, launches and retains a live
    process on `hwlinux`. A stronger visible-text Oracle then exposed an
    important calibration failure: the earlier `assert-no-text UserAgent_four`
    searched serialized layout metadata and falsely failed a successful route
    because `pagePath=pages/UserAgent_four` contained the same substring. The
    replacement Oracle first asserted visible `Example Domain`; it fails on the
    exact baseline HAP and passes on a controlled one-line page-registration
    variant. A later wrong-route calibration showed that this text is shared by
    `UserAgent_three` and `UserAgent_four`, so visible text alone produced a
    false pass. The target scenario now requires both exact
    `pages/UserAgent_four` route identity and the visible semantic text.

    The real-candidate semantic review protocol is now mechanically upstream of
    case localization: only an exact `approved-for-case-contract-proposal` gate
    can produce a localization proposal. The packet, decision and gate are
    revalidated again during localization review, construction-contract
    validation and model construction. This matches SWE-bench Verified's
    conservative curation principle while preserving rejected/deferred rows in
    the denominator. It closes the bypass mechanism, not the empirical gap: no
    real candidate has yet received that independent approval or completed
    baseline/reference/alternative-valid/meaningful-wrong calibration.
    A separate DomStorage scenario passes before and after the variant, closing
    the first real `PASS_TO_PASS` device check. Its first form—requiring remote
    Web content within two seconds—was rejected after a route-success/content-
    delay failure; the retained form checks that an Index-only control is absent
    and separately binds the observed `pages/DomStorage` path. Two more
    preservation routes bind `pages/UserAgent_one` plus visible `getUserAgent`,
    and `pages/Cache_two` plus visible `removeCache`. Five further scenarios
    close the remaining UserAgent_two, UserAgent_three, CookieManagement,
    Cache_one and UseMotionDirSensor routes. Baseline, known-fix and a
    structurally distinct named-route HAP pass all eight preservation routes,
    yielding 24 preservation runs; the latter also passes the target without
    changing the known-fix file. The nine-scenario breadth replay qualifies a
    stronger implementation-independent repair/preservation Oracle. A fourth
    wrong-route HAP is rejected while the baseline fails and both valid
    implementations pass, yielding direct route-specificity evidence and an
    Oracle-design lesson—not a reviewed reference repair, exhaustive regression suite,
    business UI case or unseen Agent benchmark. The API 23/24 code-workshop
    build remains unqualified because matching DevEco 6.1 tooling is absent, and
    the exact `hwlinux` host still has only the emulator/runtime substrate rather
    than a source-build SDK.
11. The richer API-localizing full run now uses bounded deterministic parallel
   AST extraction. On one fresh-process Apple M4 measurement with a warm Git
   object database, the exact 12,711-file cut improved from 20.16 seconds with
   one worker to 14.12 seconds with eight workers (1.43x); all emitted evidence
   digests remained byte-identical. The 31,771,940 source bytes produced
   421,973,776 bytes of fact rows and 25,987,457 bytes of difficulty candidates.
   This is one machine-local trial per profile, not a population result. Graph
   and candidate aggregation remain serial, and there is still no
   revision-aware incremental cache or early candidate prefilter.

Until these gaps close, AgentLab can claim a richer executable architecture and
one real closed-path proof, not a large, statistically qualified benchmark.

The Harmony gap is now narrower but still explicit. A source/project-tree-bound
standard-test contract recognizes `ohosTest`/Hypium Instrument Test, Local Test
and DevEco Testing Hypium UI, while the first native executor implements the
Instrument Test path. It requires ArkXtest's native final summary/code rather
than treating process success or the custom black-box UI Oracle as equivalent
to a standard test. We still lack Local Test and DevEco Testing execution
adapters and a real retained Instrument Test replay on `hwlinux`, so this is a
mechanically enforced lane, not yet corpus-scale Harmony validation.

## Adopted qualification model

Every newly generated multi-repository case now carries a qualification matrix
plus digest-bound source and qualification receipts. The receipts retain the
natural/derived source stratum and prevent functional calibration from being
reported as end-to-end qualification. The matrix generalizes the SWE-bench
split without copying its single-repository assumptions:

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
- `referenceReplay` proves both that the reference and at least one structurally
  different behaviorally valid implementation pass, while deliberately wrong
  variants fail in fresh environments. This is the executable guard against an
  implementation-specific Oracle, not a claim that every valid solution is covered.
- `freshness` records source visibility, issue/fix dates, case construction
  mode, leakage review and the model/tool knowledge boundary.
- `review` records specification fairness, Oracle breadth, coverage and
  difficulty judgments independently of the case constructor.

The release now provides a fail-closed blind-cut builder that turns one private
maintenance source into sibling participant and evaluator bundles plus an outer
digest-bound receipt. The participant manifest cannot enumerate evaluator
files, the evaluator binds the exact participant manifest, and validation
rejects extra files, symlinks, digest drift and byte-identical cross-bundle
content. This closes the structural hidden-Oracle packaging gap. It does not
automatically perform semantic-leak or contamination review. The separate
review protocol freezes the exact cut identities, rejects a reviewer identifier
equal to the recorded constructor, requires at least two unique decision
records, and fails closed on unknowns or disagreement. The local CLI records
consensus without qualifying identity. The trusted-main workflow path upgrades
that boundary only after GitHub run metadata and signed artifact attestations
bind two distinct GitHub actors, an exact workflow, main ref and source commit.
It still cannot prove model-training exclusion; every v1 adjudication therefore
remains ineligible for unseen-Agent discrimination.
The assessed campaign consumes only a run-addressed adjudication, independently
re-verifies its final attestation online, reconstructs all internal digests and
retains the raw final verification statement plus its exact enforcement policy.
It requires the three runtime isolation dimensions before reporting a qualified
blind-assessment boundary.
The reviewed multi-repository workflow now produces that cut, stages only its
participant projection, and binds the exact participant manifest into every
stage request and attempt decision. Assessed Pi turns now execute in a
least-mounted Docker runtime whose raw inspect and negative-path probes are
validated independently. Only this path may report
`filesystemIsolationQualified=true` and
`externalCredentialIsolationQualified=true`; host-process compatibility runs
remain false. The participant now joins only a fresh Docker-internal network and
uses a fixed no-credential relay to the token-protected external operator proxy.
Exact network membership, raw relay/network inspection, authenticated proxy
health and a blocked direct external connection are required before
`networkEgressIsolationQualified=true`. Runtime isolation and interface
non-disclosure still do not substitute for contamination/semantic-leak review.

No aggregate difficulty score may compensate for a failed qualification
dimension. In particular, high participant separation cannot promote an
underspecified or contaminated case.

Three current-method API candidates now have digest-bound semantic-review
packets with exact source excerpts and all marker-bearing project-boundary
candidates. They expose why API-call equality alone is not a SWE-style task:
the `AlertDialog` sites cover logout confirmation and Web alert result handling,
while the `call.makeCall` sites cover an empty-number capability path and a
`tel://` interception path. The new `image.createImagePacker` packet goes one
level deeper: it binds the complete enclosing owner and every same-owner call
for 12 call sites across seven files. It also resolves all 12 selected call
results to their lexical handles (10 binding initializers and two assignments),
then separates exact same-handle calls from lookalike names. Six handles show a
direct `release` spelling and six do not, but that syntactic split is a review
hypothesis, not a defect label. The v4 packet pairs those releases to their
factory sites: two are matching `try/finally` shapes, one factory precedes a
later `try/finally`, one uses a Promise `.finally` callback, and two are
same-`try` calls that are not finalizers. This is closer to SWE-style issue
localization, while aliases, escapes, reachability, dominance, exception safety
and runtime release remain unresolved. The packets require an independent answer on shared
behavior, observable failure, prompt completeness, repair/preservation Oracles,
environment reproducibility and genuine cross-repository necessity. They are
review aids, not approved cases.

## Ordered implementation consequences

The semantic review state machine is now executable. A candidate can advance
only when every required semantic, prompt, Oracle, environment and cross-repo
question is answered `yes`; a noncoherent shared behavior or unnecessary
cross-repository composition must be rejected, while missing evidence is
retained as an explicit defer. The compiled gate is digest-bound and only the
advance verdict sets `allowsCaseContract: true`. This imports the conservative
SWE-bench Verified curation principle before task construction instead of
waiting for an invalid task to fail during Agent evaluation.

1. Use the implemented blind-cut, least-mounted participant runtime and
   multi-reviewer adjudication on a new private or held-out case set; execute
   and independently verify the implemented authenticated reviewer/artifact
   provenance, while retaining model-training exclusion as unknown unless
   separately evidenced.
2. Carry the now-complete eight-route `PASS_TO_PASS` matrix into independent
   fairness review and additional held-out cases. The static calibration
   protocol requires a digest-bound alternative-valid implementation in
   addition to the reference and wrong
   variants; the real Harmony UI Oracle now exercises that breadth rule with a
   non-overlapping named-route implementation across all nine device scenarios.
   Independently review fairness, expand the case population, and only then
   accept a reference repair. The device campaign must extend, rather than
   overwrite, the static repair/preservation matrix with exact UI and
   performance receipts.
3. Exercise the reviewed feedback-to-analysis bridge on a real source update
   and prove that the successor case retains prior failure lineage without
   mutating the old case.
4. Exercise the implemented candidate-cohort proposal/review over the real
   22-cluster source cut, predeclare at least five localized candidates, and run
   one independent construction/review chain per member. Report every exclusion
   and the selected-to-qualified yield.
5. Exercise the multi-reviewer adjudication and population reporter across that
   predeclared case sample; interpret the retained per-dimension counts, Wilson
   intervals and reviewer reuse. Default unknown evidence to review-required,
   never qualified.
6. Localize at least five of the 22 real shared-contract clusters into narrow
   change hypotheses, then add repair/preservation checks and independent
   review before running repeated strong/weak/middle participant trials.
   Report confidence intervals, exclusions and infrastructure failures.
7. Exercise the implemented suite scorecard on real reviewed static-plus-Harmony
   campaigns using the signed pre-outcome weak/middle/strong-or-richer plan.
   Require every adjacent tier's Wilson intervals to separate before claiming
   capability resolution; extreme-only separation remains a weaker base
   measurement. Extend the
   process contract beyond the assessed emulator adapter, and add dependency-
   discovery plus subjective/objective consistency without replacing raw
   trajectories or independently executable verdict evidence.

The suite scorer now fails closed on that first distinction: static-only
discrimination evidence cannot qualify as a Harmony end-to-end result. It
requires a retained terminal device stage for every successful attempt and
workload-bound SmartPerf samples for every successful device execution. Real
reviewed campaign imports and population-scale execution remain outstanding.

This ordering copies SWE-bench's most valuable discipline—hidden executable
repair and preservation evidence—while addressing the two failure modes that
now dominate public coding benchmarks: case invalidity and contamination.

## External references

- [SWE-bench paper](https://arxiv.org/abs/2310.06770)
- [Official evaluation guide](https://github.com/SWE-bench/SWE-bench/blob/main/docs/guides/evaluation.md)
- [Official harness reference](https://github.com/SWE-bench/SWE-bench/blob/main/docs/reference/harness.md)
- [SWE-smith instance creation](https://swesmith.com/guides/create_instances/)
- [SWE-smith validation and evaluation](https://swesmith.com/guides/harnesses/)
- [SWE-bench-Live](https://github.com/microsoft/SWE-bench-Live)
- [SWE-rebench methodology](https://swe-rebench.com/about)
- [SWE-bench Multimodal](https://www.swebench.com/multimodal)
- [Introducing SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/)
- [Why SWE-bench Verified no longer measures frontier coding capabilities](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)
- [Separating signal from noise in coding evaluations](https://openai.com/index/separating-signal-from-noise-coding-evaluations/)
- [GitHub artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations)
- [Using artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
- [HarmonyOS image API common mistakes](https://developer.huawei.com/consumer/cn/doc/doccenter-capabilities/image-common-mistakes)
- [Using ImagePacker to encode pictures](https://developer.huawei.com/consumer/en/doc/harmonyos-guides-V13/image-picture-encoding-V13)
- [Native ImagePacker guide](https://developer.huawei.com/consumer/en/doc/harmonyos-guides-V13/image-packer-c-V13)
