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

The deterministic receipt and `intent.json` remain
`candidate-unverified`; `semanticKnowledgeVerified` and `automaticPromotion`
are false. Construct a proposal; the proposer independently verifies the
construction receipt, derives the allowed edit surface and records analysis
evidence plus known qualification risks:

```sh
python3 scripts/propose-multi-repo-case-plan.py \
  --difficulty /tmp/analysis/difficulty_candidates.json \
  --intent /tmp/intent-construction/intent.json \
  --construction-receipt /tmp/intent-construction/construction-receipt.json \
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
  --calibration /tmp/multi-repo-calibration/summary.json \
  --output /tmp/multi-repo-evaluation-case.json
```

For v2 plans the freezer independently rereads both evidence files, verifies
their digests and confirms every calibrated plan field is identical to the
reviewed proposal. Legacy v1 plans remain accepted without claiming this
stronger review lineage.

Copy the frozen case into campaign evidence as
`multi-repo-evaluation-case.json` and its exact calibration summary as
`multi-repo-calibration.json`. For a constructed case, also copy the exact
receipt as `multi-repo-construction-receipt.json`.
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
