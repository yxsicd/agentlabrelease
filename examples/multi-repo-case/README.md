# Calibrated multi-repository case generation

This fixture closes one bounded path from program analysis to a valid AgentLab
evaluation case:

```text
exact Git source set
  -> cross-repository module graph
  -> recursive change-impact difficulty
  -> semantic case plan
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
Select a dependency-supported candidate and author a
`agentlab.multi_repo_case_plan.v1` plan. The plan contains Agent-visible demands,
allowed edit paths, check IDs, the Oracle digest and expected calibration
matrix. It does not contain reference source.

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
  --calibration /tmp/multi-repo-calibration/summary.json \
  --output /tmp/multi-repo-evaluation-case.json
```

Copy the frozen case into campaign evidence as
`multi-repo-evaluation-case.json` and its exact calibration summary as
`multi-repo-calibration.json`; `build-cbgroom-flywheel-transaction.py` validates
their digest/source-set/candidate/Oracle linkage and writes an
`evaluation_cases` row linked to both evidence objects.

## Evidence boundary

The deterministic generator validates lineage and calibration; it does not
invent the semantic requirement. A maintainer or construction Agent must still
produce and review the semantic plan. The checked fixture qualifies the
executable VM seam only. Harmony compilation, UI behavior, emulator deployment,
performance and assessed-Agent discrimination are independent later gates.
