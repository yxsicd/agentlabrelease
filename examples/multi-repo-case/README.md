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

The example spans `contracts`, `service` and `app`. Turn 1 adds a premium retry
policy while preserving the standard boundary. Turn 2 updates the application
result contract without moving retry ownership out of the service. The Oracle
executes the submitted JavaScript-compatible TypeScript module bodies through a
supervisor-owned VM module linker.

Calibration includes four variants:

- `baseline` fails both turns;
- `reference` passes both turns;
- `hardcoded-premium` violates the standard policy boundary and fails;
- `stale-consumer` passes turn 1 but fails turn 2.

That last variant proves the second demand measures retained cross-repository
state rather than merely repeating the first check.

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
  --output /tmp/api-call-localization.json
```

The resulting artifact
only authorizes intent construction; it does not qualify a case or expose a
reference implementation. The ArkWeb real-source example at
`release/qualifications/harmony-arkweb-lifecycle-localization-6840590/` stops at
this review boundary on purpose.

On trusted `main`, the manual `API-call localization independent review`
workflow performs the same exact-digest operation using the authenticated
GitHub actor as reviewer and retains all three artifacts together. It requires
the reviewer to enter the proposal digest, every risk ID and a rationale; it
has no model or repository-write secret.

For a `shared-external-api-call-contract`, intent construction fails closed
unless all three exact localization artifacts are supplied:

```sh
python3 scripts/run-multi-repo-intent-construction.py \
  --manifest /tmp/multi-repo-manifest.json \
  --difficulty /tmp/analysis/difficulty_candidates.json \
  --facts /tmp/analysis/workspace_facts.jsonl \
  --candidate-id <shared-external-api-call-candidate-id> \
  --localization /tmp/api-call-localization.json \
  --localization-proposal /tmp/api-call-localization-proposal.json \
  --localization-review /tmp/api-call-localization-review.json \
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
After this workflow reaches the trusted default branch, an operator can dispatch
`Multi-repository model construction`. It creates reproducible Git fixture
revisions, runs the real Pi adapter with the repository Gateway secret, applies
this quality gate without the secret, and uploads the complete source, native
model/Gateway, receipt and quality evidence. It also retains the operator-owned
reference, calibration driver and Oracle from that same revision, outside the
participant input. The credential-bearing job is manual and is rejected unless
its ref is exactly `refs/heads/main`; pull requests continue to exercise only
the deterministic mock path.

The trusted-main campaign is deliberately split into three independently
auditable manual runs:

1. `Multi-repository model construction` produces a review-required proposal
   and prints its exact SHA-256.
2. After inspecting that artifact, an operator dispatches
   `Multi-repository case review and freeze` with the source run ID, exact
   proposal digest, every risk ID and a rationale. The workflow accepts only a
   successful construction run from `main`, reruns the retained calibration,
   and freezes the reviewed case. It has no Gateway credential.
3. `Multi-repository assessed-Agent campaign` accepts only a successful freeze
   run from `main`, reconstructs the reviewed sources, and executes two distinct
   model profiles for one or three fresh trials each. It retains every staged
   attempt and emits the v2 collection plus discrimination report.

Freezing and scoring never auto-promote a case. A score is campaign evidence,
not a publication decision. The campaign uses the Oracle retained by the
construction run, so a later change on `main` cannot silently alter the case.

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
  --participant-id pi-glm-5.3-flash \
  --output /tmp/multi-repo-attempt
```

The Pi adapter keeps one participant process and native session across both
stages, while the operator-owned Gateway proxy retains the complete model
exchange. The external Gateway credential is available only to the adapter,
not to Pi. `summary.json` and `decision-package.json` carry the exact
`sourceSetSha256` and are directly consumable by an
`agentlab.case_attempt_collection.v2` campaign. Participant/runtime or Oracle
transport failures produce `infrastructure-unavailable` with a null verdict;
valid runs that fail behavior or edit scope remain assessed failures.

`mock-assessed-agent.py` provides baseline, reference and scope-drift protocol
fixtures for deterministic Harness regression only. Their separation score is
not evidence about a real model. The current local-process adapter also relies
on participant cooperation not to traverse outside the supplied workspace;
formal production isolation requires the released sandbox/SessionFS execution
boundary. The runner therefore records the manifest-bound interface input but
keeps `filesystemIsolationQualified=false` and `blindAssessmentQualified=false`
for its current host-process mode.

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
