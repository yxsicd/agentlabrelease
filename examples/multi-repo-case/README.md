# Calibrated multi-repository case generation

This fixture closes one bounded path from program analysis to a valid AgentLab
evaluation case:

```text
exact Git source set
  -> cross-repository module graph
  -> recursive change-impact difficulty
  -> exact API-call localization proposal
  -> independent localization review
  -> exact affected source + relevant facts
  -> independent evaluator-authored source surface, Oracle, and calibration variants
  -> exact authoring receipt and draft-manifest revalidation
  -> replaceable construction participant
  -> captured semantic-intent candidate
  -> review-required plan proposal
  -> exact proposal review
  -> independent executable Oracle
  -> baseline/reference/wrong-variant calibration
  -> frozen evaluation case
  -> repeated assessed-Agent attempts and discrimination score
  -> stage/failure-mode feedback candidates for the next maintenance cut
  -> reviewed feedback-to-new-analysis cut
  -> next case construction and independent calibration
  -> TableGit evaluation_cases row
```

Run that complete credential-free protocol proof as one retained evidence chain
instead of inferring integration from separate commands:

```sh
cargo build --locked --release -p agentlab_code_analysis \
  --bin agentlab-multi-repo-analysis
python3 examples/multi-repo-case/run-golden-path.py \
  --analyzer target/release/agentlab-multi-repo-analysis \
  --method-revision "$(git rev-parse HEAD)" \
  --output /tmp/agentlab-multi-repo-golden-path
```

The runner executes 40 fail-closed phases over the same source identity: exact
analysis, reviewed two-member cohort, deep candidate selection, independent
evaluator authoring and revalidation, reviewed construction contract,
deterministic construction participant, reviewed executable calibration bundle,
case/dependency freeze, blind participant cut, baseline/reference assessment,
collection and discrimination scoring. The exact authoring receipt and draft
manifest are bound through both construction and calibration. It keeps every
command's stdout/stderr digest and produces
`agentlab.multi_repo_golden_path.v1`. The expected fixture result is baseline
failure, reference success and discrimination score `1.0` with process-aware
eligibility and full hidden-dependency coverage.

This is a protocol-integration qualification only. The authoring participant is
a deterministic independent-evaluator fixture, not a real model, and its
machine-authored review fixtures are not human semantic approval. Filesystem
isolation, authenticated blind review, Harmony build, emulator execution,
performance and population representativeness remain false in the summary.

The example spans `contracts`, `service` and `app`. Turn 1 adds a premium retry
policy while preserving the standard boundary. Turn 2 updates the application
result contract without moving retry ownership out of the service. The Oracle
executes the submitted JavaScript-compatible TypeScript module bodies through a
supervisor-owned VM module linker.

Calibration includes five explicitly classified variants:

- `baseline` fails both turns;
- `reference` passes both turns;
- `equivalent-policy-loop` uses a lookup-table policy, a `while` loop and a
  destructuring consumer instead of the reference structure, but must pass both
  turns as an independently bound `alternative-valid` implementation;
- `hardcoded-premium` violates the standard policy boundary and fails;
- `stale-consumer` passes turn 1 but fails turn 2.

The alternative-valid variant guards against an implementation-specific Oracle.
The last wrong variant proves the second demand measures retained
cross-repository state rather than merely repeating the first check.

For real shared-external API candidates, do not pass a broad module cluster
directly into intent construction. First select exact target and reference call
facts plus the proposed editable/context paths, then run:

```sh
python3 scripts/propose-api-call-case-localization.py \
  --manifest /tmp/multi-repo-manifest.json \
  --difficulty /tmp/analysis/difficulty_candidates.json \
  --facts /tmp/analysis/workspace_facts.jsonl \
  --candidate-id <shared-external-api-call-candidate-id> \
  --selection /tmp/api-call-selection.json \
  --semantic-packet /tmp/semantic-review/packet.json \
  --semantic-decision /tmp/semantic-review/decision.json \
  --semantic-gate /tmp/semantic-review/gate.json \
  --method-revision <exact-agentlab-commit> \
  --output /tmp/api-call-localization-proposal.json
```

An independent maintainer must review the exact proposal digest, the semantic
hypothesis and every path that expands beyond the localized calls. Compile the
decision with:

```sh
python3 scripts/review-api-call-case-localization.py \
  --proposal /tmp/api-call-localization-proposal.json \
  --review /tmp/api-call-localization-review.json \
  --semantic-packet /tmp/semantic-review/packet.json \
  --semantic-decision /tmp/semantic-review/decision.json \
  --semantic-gate /tmp/semantic-review/gate.json \
  --output /tmp/api-call-localization.json
```

The resulting artifact
only authorizes intent construction; it does not qualify a case or expose a
reference implementation. The ArkWeb real-source example at
`release/qualifications/harmony-arkweb-lifecycle-localization-6840590/` stops at
this review boundary on purpose. It predates the mandatory semantic gate and is
not accepted by the current localization-review or construction commands.

On trusted `main`, the manual `API-call localization independent review`
workflow performs the same exact-digest operation using the authenticated
GitHub actor as reviewer and retains the localization chain plus its exact
semantic packet/decision/gate. It requires the trusted-main semantic review run,
approved gate digest, proposal digest, every risk ID and a rationale; it has no
model or repository-write secret.

For a `shared-external-api-call-contract`, intent construction fails closed
unless all three exact localization artifacts and all three semantic artifacts
are supplied:

```sh
python3 scripts/run-multi-repo-intent-construction.py \
  --manifest /tmp/multi-repo-manifest.json \
  --difficulty /tmp/analysis/difficulty_candidates.json \
  --facts /tmp/analysis/workspace_facts.jsonl \
  --candidate-id <shared-external-api-call-candidate-id> \
  --localization /tmp/api-call-localization.json \
  --localization-proposal /tmp/api-call-localization-proposal.json \
  --localization-review /tmp/api-call-localization-review.json \
  --semantic-packet /tmp/semantic-review/packet.json \
  --semantic-decision /tmp/semantic-review/decision.json \
  --semantic-gate /tmp/semantic-review/gate.json \
  --oracle-contract /tmp/operator-owned-oracle-contract.json \
  --participant <construction-adapter.py> \
  --participant-id <construction-participant-id> \
  --output /tmp/intent-construction
```

The Harness materializes reviewed editable paths and read-only context paths,
verifies their pinned bytes, and labels them separately. The downstream case
plan derives `allowedEdits` only from the reviewed editable paths. It neither
silently grants the broad module cluster nor rejects an explicitly reviewed
lifecycle path merely because that path was outside the original call sites.

## Commands

First run `agentlab-multi-repo-analysis` on exact committed checkouts as
described in [`docs/multi-repository-analysis.md`](../../docs/multi-repository-analysis.md).
Select a dependency-supported candidate and run a construction participant. For
a shared external API-call candidate, complete the localization review above
first. The
Harness materializes only the reviewed source surface from the exact Git revisions,
selects the related facts and gives the participant a behavior/check contract
without reference source, calibration variants or Oracle implementation. It
retains the request, participant digest, command, stdout/stderr, draft and
lifecycle evidence. The included participant is a deterministic transport
fixture; replace `--participant` and its identity with an actual construction
Agent adapter for semantic construction:

```sh
python3 scripts/run-multi-repo-intent-construction.py \
  --manifest /tmp/multi-repo-manifest.json \
  --difficulty /tmp/analysis/difficulty_candidates.json \
  --facts /tmp/analysis/workspace_facts.jsonl \
  --candidate-id <difficulty-id> \
  --oracle-contract examples/multi-repo-case/oracle-contract.json \
  --participant examples/multi-repo-case/mock-construction-agent.py \
  --participant-id deterministic-construction-fixture-v1 \
  --output /tmp/intent-construction
```

`pi-construction-agent.py` is the model-backed adapter. It reuses the same
operator-owned forwarding proxy and complete native/gateway capture as the real
Code Agent examples. The outer Harness passes credentials only to this adapter;
Pi receives the local proxy credential rather than the external Gateway key:

```sh
export AGENTLAB_LM_GATEWAY_URL=https://gateway.example.invalid
export AGENTLAB_LM_GATEWAY_KEY='<operator credential>'
export AGENTLAB_MODEL=glm-5.3-flash
python3 scripts/run-multi-repo-intent-construction.py \
  --manifest /tmp/multi-repo-manifest.json \
  --difficulty /tmp/analysis/difficulty_candidates.json \
  --facts /tmp/analysis/workspace_facts.jsonl \
  --candidate-id <difficulty-id> \
  --oracle-contract examples/multi-repo-case/oracle-contract.json \
  --participant examples/multi-repo-case/pi-construction-agent.py \
  --participant-id pi-glm-5.3-flash \
  --output /tmp/intent-construction
```

The deterministic receipt and `intent.json` remain
`candidate-unverified`; `semanticKnowledgeVerified` and `automaticPromotion`
are false. Before review, apply the deterministic leakage, behavior-coverage
and stage-separation preflight:

```sh
python3 scripts/score-multi-repo-intent.py \
  --intent /tmp/intent-construction/intent.json \
  --construction-receipt /tmp/intent-construction/construction-receipt.json \
  --oracle-contract examples/multi-repo-case/oracle-contract.json \
  --output /tmp/intent-construction/intent-quality.json
```

This lexical gate is intentionally narrow: it can reject generic, duplicated or
leaking demands, but cannot prove semantic correctness or Agent discrimination.
Before model construction, first dispatch `Multi-repository exact analysis`
with an `agentlab.multi_repo_source_spec.v1` value containing exact public Git
repositories and commits. Inspect its `analysis-run.json` digest, then dispatch
`Multi-repository candidate cohort proposal` with that analysis run ID and
digest. The proposal workflow downloads and revalidates the exact evidence,
records every eligible and excluded candidate, and reports
relation/depth/repository-count strata without claiming representativeness. A
separate `Multi-repository candidate cohort review` run
binds an operator's exact digest, rationale, risk acknowledgements and at least
two predeclared candidate IDs. For each selected member, dispatch the separate
construction-contract proposal and exact-digest review workflows. They freeze
the editable/context surface and operator-owned behavior/Oracle contract before
any model result exists. `Multi-repository model construction` then revalidates
that reviewed contract, rematerializes the exact repositories, and fails if the
cohort, candidate, source surface, Oracle declaration or source evidence drifts.
Only then does it run the real Pi adapter with the repository Gateway secret,
apply the quality gate without the secret, and upload the complete source,
native model/Gateway, receipt and quality evidence. Credential-bearing
construction is manual and is rejected unless its ref is exactly
`refs/heads/main`; proposal and review have no Gateway credential.

The trusted-main campaign is deliberately split into independently
auditable phases, with analysis as the required predecessor:

1. `Multi-repository exact analysis` freezes and verifies the arbitrary public
   source set and native program-analysis evidence.
2. `Multi-repository candidate cohort proposal` freezes the exact eligible
   denominator, exclusions and strata.
3. `Multi-repository candidate cohort review` predeclares at least two members
   for independent construction; it never declares the sample representative.
4. Optional `Multi-repository calibration authoring` runs a distinct evaluator
   model over exact candidate sources and facts to draft the source surface,
   Oracle contract, driver, Oracle, reference, alternative-valid and wrong
   variants. Every byte remains review-required; it cannot qualify a case.
5. `Multi-repository construction contract proposal` binds one selected member
   either to that exact authored receipt or to a directly supplied editable/
   context source surface and behavior/Oracle contract. API-call candidates
   must include their reviewed localization.
6. `Multi-repository construction contract review` binds an authenticated
   maintainer, exact proposal digest, all risks and a rationale before any model
   credential is used.
7. One `Multi-repository model construction` run per selected member reproduces
   its arbitrary exact repositories, exposes only the reviewed source surface,
   and produces a review-required case proposal with its exact SHA-256.
8. As an alternative to authored or local bytes, `Multi-repository calibration
   bundle source` fetches one credential-free public GitHub repository at an
   exact commit and retains a manifest-bound portable source artifact. Local
   fixture bundles may skip this step.
9. `Multi-repository calibration bundle proposal` accepts exactly one local,
   portable-source or evaluator-authored bundle, stages the exact driver,
   Oracle and solution trees against the reviewed construction contract, and
   binds that source identity into its proposal. A separate `Multi-repository
   calibration bundle review` binds every byte, all risks and the reviewer
   rationale.
10. After inspecting each artifact, an operator dispatches
   `Multi-repository case review and freeze` with the construction and reviewed
   calibration-bundle run IDs, their exact digests, every case-plan risk ID and
   a rationale. The workflow accepts only successful runs from `main`, executes
   the reviewed bundle against the exact baseline, retains its run receipt and
   freezes the reviewed case. It has no Gateway credential.
11. `Multi-repository assessed-Agent campaign` accepts only a successful freeze
   run from `main`, reconstructs the reviewed sources, and executes two distinct
   model profiles for one or three fresh trials each. It retains every staged
   attempt and emits the v2 collection plus discrimination report.

The exact-analysis, cohort, bounded model-construction and executable-calibration
phases are generic. The construction contract declares the Oracle behavior; the
separate calibration bundle freezes and reviews the executable, reference and
wrong-variant generator without exposing them to the participant. The included
retry-policy bundle is a deterministic protocol proof, not evidence that an
arbitrary real-source candidate has qualified.

Freezing and scoring never auto-promote a case. A score is campaign evidence,
not a publication decision. The campaign uses the Oracle retained by the
construction run, so a later change on `main` cannot silently alter the case.
The blind-review population workflow now requires the reviewed candidate-cohort
run and exact cohort digest. Frozen cases retain the candidate selection in
evaluator-only lineage, so the population reporter independently proves every
case belongs to the predeclared cohort and exact source set. Selected candidates
that never become authenticated cases remain in the denominator and reduce the
reported case-yield rate; they cannot disappear through post-hoc sample
shrinking.

For a feedback-derived successor, first run a new exact multi-repository
analysis cut, then use `propose-feedback-analysis-cut.py` and
`review-feedback-analysis-cut.py` as documented in
[`docs/multi-repository-analysis.md`](../../docs/multi-repository-analysis.md).
Pass the reviewed cut to the proposer with `--feedback-analysis-cut`. The
resulting frozen case retains the prior case ID, feedback candidate ID, reviewed
cut digest and next method revision in its lineage; it never edits or supersedes
the prior frozen case in place.

Construct a proposal; the proposer independently verifies both construction
receipt and qualified quality report, derives the allowed edit surface and
records analysis evidence plus known qualification risks:

```sh
python3 scripts/propose-multi-repo-case-plan.py \
  --difficulty /tmp/analysis/difficulty_candidates.json \
  --intent /tmp/intent-construction/intent.json \
  --construction-receipt /tmp/intent-construction/construction-receipt.json \
  --quality-report /tmp/intent-construction/intent-quality.json \
  --output /tmp/case-plan-proposal.json
```

The output remains `review-required` and has `automaticPromotion: false`. A
review decision must bind its exact SHA-256, approve only calibration, identify
the reviewer, give a rationale and acknowledge every recorded risk. Compile
that decision into a v2 plan:

```sh
python3 scripts/review-multi-repo-case-plan.py \
  --proposal /tmp/case-plan-proposal.json \
  --review /tmp/case-plan-review.json \
  --output /tmp/case-plan.json
```

A changed proposal invalidates the review. The resulting plan retains both
proposal and decision digests for calibration lineage.

Run the independent calibration:

```sh
python3 examples/multi-repo-case/calibrate.py \
  --baseline examples/multi-repo-case/baseline \
  --reference examples/multi-repo-case/reference \
  --source-set-sha256 <source-set-sha256> \
  --candidate-id <difficulty-id> \
  --output /tmp/multi-repo-calibration
```

Freeze the case only after calibration succeeds:

```sh
python3 scripts/generate-multi-repo-case.py \
  --difficulty /tmp/analysis/difficulty_candidates.json \
  --plan /tmp/case-plan.json \
  --proposal /tmp/case-plan-proposal.json \
  --review /tmp/case-plan-review.json \
  --construction-quality /tmp/intent-construction/intent-quality.json \
  --calibration /tmp/multi-repo-calibration/summary.json \
  --output /tmp/multi-repo-evaluation-case.json
```

The freezer now derives an embedded
`agentlab.case_qualification_matrix.v1` from the per-check calibration
receipts. A check that fails on the baseline and passes on the reference is a
`repairCheck`; a check that passes on both is a `preservationCheck`. Freezing
fails unless both classes exist, the reference passes every check, repeated
check verdicts remain stable across cumulative stages, and the aggregate stage
verdict agrees with its individual checks. Validate the retained matrix again
from the independent calibration bytes with:

```sh
python3 scripts/validate-case-qualification.py \
  --case /tmp/multi-repo-evaluation-case.json \
  --calibration /tmp/multi-repo-calibration/summary.json
```

The JSON shape is published at
`schemas/case-qualification-matrix.schema.json`. Device checks, performance
guardrails and freshness/contamination review remain explicit pending gates;
static calibration cannot silently qualify them.

Before operational assessment, project the frozen case into separate blind
participant/evaluator roots, then stage only the participant root:

```sh
python3 scripts/prepare-multi-repo-blind-cut.py \
  --case /tmp/multi-repo-evaluation-case.json \
  --oracle examples/multi-repo-case/oracle.mjs \
  --reference-root examples/multi-repo-case/reference \
  --calibration /tmp/multi-repo-calibration/summary.json \
  --review /tmp/case-plan-review.json \
  --method-revision <release-commit> \
  --constructed-at <utc-rfc3339> \
  --output /tmp/multi-repo-blind-cut

python3 scripts/build-blind-case-cut.py stage-participant \
  --cut /tmp/multi-repo-blind-cut \
  --output /tmp/multi-repo-participant-input \
  --receipt /tmp/multi-repo-dispatch-receipt.json
```

The participant projection contains stage IDs and demands but no check IDs,
Oracle path, reference source, calibration or review bytes.
The Pi adapter revalidates the participant task digest and rejects any stage
demand or allowed-edit surface that differs from that staged projection.

For v2 plans the freezer independently rereads both evidence files, verifies
their digests and confirms every calibrated plan field is identical to the
reviewed proposal. Legacy v1 plans remain accepted without claiming this
stronger review lineage.

## Assessed-Agent execution

Run the frozen case with a persistent, replaceable assessed-participant adapter.
The Harness materializes the complete committed source set without Git metadata,
sends only the staged demand and allowed edit surface, retains one workspace
across stages, rejects changes outside that surface, and invokes the frozen
Oracle independently after every participant turn:

```sh
python3 scripts/run-multi-repo-assessment.py \
  --case /tmp/multi-repo-evaluation-case.json \
  --manifest /tmp/multi-repo-manifest.json \
  --oracle examples/multi-repo-case/oracle.mjs \
  --participant examples/multi-repo-case/pi-assessed-agent.py \
  --blind-participant-root /tmp/multi-repo-participant-input \
  --blind-dispatch-receipt /tmp/multi-repo-dispatch-receipt.json \
  --participant-runtime-config /tmp/participant-runtime.json \
  --participant-id pi-glm-5.3-flash \
  --output /tmp/multi-repo-attempt
```

The Pi adapter keeps one trusted protocol process and native session across both
stages, while the operator-owned Gateway proxy retains the complete model
exchange. Each Pi turn is a fresh least-mounted container over the same
Workspace and participant-state mounts. The external Gateway credential is
available only to the host adapter, not to Pi or its PID namespace.
`summary.json` and `decision-package.json` carry the exact
`sourceSetSha256` and are directly consumable by an
`agentlab.case_attempt_collection.v2` campaign. Participant/runtime or Oracle
transport failures produce `infrastructure-unavailable` with a null verdict;
valid runs that fail behavior or edit scope remain assessed failures.
For a dependency-aware v2 task, the native final assistant message must contain
exactly one `<agentlab_dependency_claims>` JSON-array block. The adapter retains
the complete native message and its digest, reports `reported`, `missing` or
`invalid`, and never manufactures dependency claims from exit status or changed
paths. Missing or malformed claims remain a process-measurement failure while
the independent functional Oracle still owns the task verdict.

`mock-assessed-agent.py` provides baseline, reference and scope-drift protocol
fixtures for deterministic Harness regression only. It also emits an optional
pre-Oracle `selfAssessment` with `expectedOraclePass` and `confidence`; the
Harness compares that claim with the independent Oracle and derives agreement
and Brier score without changing the verdict. Its separation or calibration is
not evidence about a real model. A run without `--participant-runtime-config`
is host-process compatibility mode and keeps
`filesystemIsolationQualified=false`. The assessed workflow freezes an exact
container image/runtime/case configuration, probes evaluator and operator paths
as unreachable, retains Docker lifecycle evidence outside participant mounts,
and independently validates the exact four-mount policy before setting
filesystem and external-credential isolation true. Pi joins only a fresh
Docker-internal network; a separate immutable relay with no external credential
connects that network to the token-protected operator proxy. Raw network and
relay inspection, exact membership, a successful authenticated health probe and
a blocked direct external connection are required before
`networkEgressIsolationQualified=true`. Freshness, semantic leakage and
contamination remain review-required, so `blindAssessmentQualified` stays false.

### Hidden dependency-discovery protocol

Do not evaluate dependency discovery while revealing `allowedEdits`. Build a
hidden contract from exact analyzer facts and an explicitly reviewed obligation
plan, then derive a new immutable case binding. The trusted construction path
first groups the selected recursive candidate's native `module-dependency`
evidence by dependency depth; this remains a review proposal rather than an
automatic Oracle:

```sh
python3 scripts/propose-dependency-discovery-plan.py \
  --case-plan-proposal /tmp/case-plan-proposal.json \
  --difficulty /tmp/analysis/difficulty_candidates.json \
  --program-facts /tmp/analysis/workspace_facts.jsonl \
  --output /tmp/dependency-plan-proposal.json
python3 scripts/review-dependency-discovery-plan.py decide \
  --proposal /tmp/dependency-plan-proposal.json \
  --expected-sha256 "$REVIEWED_DEPENDENCY_PLAN_SHA256" \
  --reviewer "$REVIEWER" \
  --acknowledged-risk-ids dependency-obligation-fairness,dependency-route-completeness \
  --rationale "$DEPENDENCY_PLAN_RATIONALE" \
  --output /tmp/dependency-plan-review.json
python3 scripts/review-dependency-discovery-plan.py compile \
  --proposal /tmp/dependency-plan-proposal.json \
  --review /tmp/dependency-plan-review.json \
  --output /tmp/dependency-discovery-plan.json
python3 scripts/build-dependency-discovery-contract.py \
  --case /tmp/multi-repo-evaluation-case.json \
  --program-facts /tmp/analysis/workspace_facts.jsonl \
  --plan /tmp/dependency-discovery-plan.json \
  --output /tmp/dependency-discovery-contract.json
python3 scripts/bind-dependency-discovery-case.py \
  --case /tmp/multi-repo-evaluation-case.json \
  --dependency-contract /tmp/dependency-discovery-contract.json \
  --program-facts /tmp/analysis/workspace_facts.jsonl \
  --output /tmp/dependency-aware-case.json
```

Pass the same hidden contract and facts to blind-cut preparation and assessment
with `--dependency-contract` and `--program-facts`. The v2 participant bundle
and stage request omit the allowed edit surface, while the Harness privately
enforces it. Each participant may return `dependencyClaims` containing
`relation`, `source`, `target` and `rationale`. Scoring measures recall of
hidden required obligations; alternative reviewed fact routes are accepted and
extra claims remain unadjudicated. It never claims precision or substitutes for
the independent functional Oracle.

For a private or held-out cut, `scripts/review-blind-case-cut.py` can freeze the
exact participant/evaluator identities, collect at least two
constructor-distinct reviewer records and adjudicate semantic leakage,
contamination risk, specification fairness and Oracle breadth. Unknowns and
reviewer disagreement fail closed. The CLI records distinct identities but does
not authenticate them. The trusted-main review and adjudication workflows bind
two distinct GitHub actors to OIDC/Sigstore-attested decisions before identity
qualification can become true. This review chain still does not establish
model-training exclusion or unseen-Agent eligibility, and the public fixture
ships no real review decisions.

When an authenticated adjudication exists, pass its workflow run ID to the
assessed campaign as `authenticated_review_run_id`. The campaign downloads and
re-verifies the signed adjudication before model execution, retains that raw
verification and exact policy in the campaign artifact, and every assessment
process reconstructs its cut, decision and provenance lineage. Review consensus
alone cannot set `blindAssessmentQualified`; the authenticated identity,
attested provenance, filesystem, credential and network gates must all pass.

After at least two authenticated adjudications exist, freeze their exact run
IDs together with the reviewed candidate-cohort artifact in an
`agentlab.blind_review_population_manifest.v2` manifest and run
`scripts/summarize-blind-review-population.py`. The trusted-main
`Blind review population report` workflow automates recovery, online
reverification, per-dimension agreement/disagreement statistics, raw evidence
retention and signing of the resulting report. It reads the evaluator-only
frozen case from each attested bundle, verifies candidate ID, source set and
cohort lineage, rejects duplicate/substituted candidates, and reports selected,
adjudicated and unadjudicated denominators plus case yield. This still measures
the chosen cohort only: v2 deliberately refuses a representative-population
declaration, model-training exclusion or unseen-Agent eligibility. Legacy v1
manifests remain readable but do not receive candidate-membership qualification.

Once every reviewed case has an assessed campaign, the trusted-main
`Agent suite scorecard` workflow accepts the population run, one campaign run
per case, and a participant ID order declared weakest-to-strongest. It validates
the exact producing workflows and revisions, joins case/source identities,
requires complete operator-owned stage-process evidence, and reports both
per-case and aggregate participant pass-rate Wilson intervals. A scorecard can
qualify the measurement procedure; it cannot promote the selected cohort into
a representative or unseen-Agent benchmark. For a v2 population it also carries
the original candidate denominator and case-yield rate, so later discrimination
scores cannot hide failed case construction or review yield.

Copy the frozen case into campaign evidence as
`multi-repo-evaluation-case.json` and its exact calibration summary as
`multi-repo-calibration.json`. For a constructed case, also copy the exact
receipt as `multi-repo-construction-receipt.json`.
Copy the pre-review report as `multi-repo-construction-quality.json`.
`build-cbgroom-flywheel-transaction.py` validates all
digest/source-set/candidate/participant/Oracle links and writes an
`evaluation_cases` row linked to all retained evidence objects.

After collecting repeated attempts and scoring discrimination, derive the next
maintenance input without mutating the frozen case:

```sh
python3 scripts/derive-assessment-feedback.py \
  --case /tmp/multi-repo-evaluation-case.json \
  --input /tmp/case-discrimination-input.json \
  --report /tmp/case-discrimination-report.json \
  --output /tmp/assessment-feedback-candidates.json
```

The derivation rereads every infrastructure-valid Harness decision package by
its collected byte count and SHA-256, groups independent Oracle failures and
scope drift by frozen stage, and excludes infrastructure failures from Agent
capability evidence. Its candidates remain `caseReady=false` and
`automaticPromotion=false`; a maintainer must adjudicate them into a new source,
analysis and calibration cut. When all four canonical files are retained, the
flywheel transaction persists these observations as evidence-linked
`difficulty_points` rather than rewriting reusable guidance or the active case.

## Evidence boundary

The construction participant proposes semantic intent from exact scoped source,
facts and a behavior contract; its output is not semantic truth. The
deterministic proposer derives scope and exposes risks, and an explicit reviewer
must approve the exact proposal before calibration. The included mock proves
the capture/protocol/lineage path, not model quality. The checked fixture
qualifies the executable VM seam only. Harmony compilation, UI behavior,
emulator deployment, performance and assessed-Agent discrimination are
independent later gates.
