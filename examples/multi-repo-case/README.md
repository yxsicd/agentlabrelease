# Calibrated multi-repository case generation

This fixture closes one bounded path from program analysis to a valid AgentLab
evaluation case:

```text
exact Git source set
  -> cross-repository module graph
  -> recursive change-impact difficulty
  -> exact affected source + relevant facts
  -> replaceable construction participant
  -> captured semantic-intent candidate
  -> review-required plan proposal
  -> exact proposal review
  -> independent executable Oracle
  -> baseline/reference/wrong-variant calibration
  -> frozen evaluation case
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

## Commands

First run `agentlab-multi-repo-analysis` on exact committed checkouts as
described in [`docs/multi-repository-analysis.md`](../../docs/multi-repository-analysis.md).
Select a dependency-supported candidate and run a construction participant. The
Harness materializes only the affected files from the exact Git revisions,
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
boundary.

Copy the frozen case into campaign evidence as
`multi-repo-evaluation-case.json` and its exact calibration summary as
`multi-repo-calibration.json`. For a constructed case, also copy the exact
receipt as `multi-repo-construction-receipt.json`.
Copy the pre-review report as `multi-repo-construction-quality.json`.
`build-cbgroom-flywheel-transaction.py` validates all
digest/source-set/candidate/participant/Oracle links and writes an
`evaluation_cases` row linked to all retained evidence objects.

## Evidence boundary

The construction participant proposes semantic intent from exact scoped source,
facts and a behavior contract; its output is not semantic truth. The
deterministic proposer derives scope and exposes risks, and an explicit reviewer
must approve the exact proposal before calibration. The included mock proves
the capture/protocol/lineage path, not model quality. The checked fixture
qualifies the executable VM seam only. Harmony compilation, UI behavior,
emulator deployment, performance and assessed-Agent discrimination are
independent later gates.
