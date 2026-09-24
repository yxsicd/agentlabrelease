# Calibrated multi-repository case generation

This fixture closes one bounded path from program analysis to a valid AgentLab
evaluation case:

```text
exact Git source set
  -> cross-repository module graph
  -> recursive change-impact difficulty
  -> semantic intent
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
Select a dependency-supported candidate and author an
`agentlab.multi_repo_case_intent.v1` intent. It contains Agent-visible demands,
check IDs, the Oracle digest and expected calibration matrix, but no reference
source. Construct a proposal; the script derives the allowed edit surface and
records analysis evidence plus known qualification risks:

```sh
python3 scripts/propose-multi-repo-case-plan.py \
  --difficulty /tmp/analysis/difficulty_candidates.json \
  --intent /tmp/case-intent.json \
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
`multi-repo-calibration.json`; `build-cbgroom-flywheel-transaction.py` validates
their digest/source-set/candidate/Oracle linkage and writes an
`evaluation_cases` row linked to both evidence objects.

## Evidence boundary

The deterministic proposer derives scope and exposes risks; it does not invent
or prove the semantic requirement. A maintainer or construction Agent must
still supply the intent, and an explicit reviewer must approve the exact
proposal before calibration. The checked fixture qualifies the executable VM
seam only. Harmony compilation, UI behavior, emulator deployment, performance
and assessed-Agent discrimination are independent later gates.
