# Case discrimination scoring fixture

This fixture demonstrates ranking already-calibrated cases from repeated,
independently graded attempts. It is synthetic method evidence, not a claim
about any real Agent or model.

```sh
python3 scripts/score-case-discrimination.py \
  --input examples/case-discrimination/fixture.json
```

The score multiplies three inspectable quantities:

1. separation between the highest and lowest participant pass rates;
2. within-participant determinism, so random/noisy outcomes do not look useful;
3. trial confidence, capped when every participant reaches the declared trial
   denominator.

A case is eligible only when the independent oracle calibration proves the
declared baseline, reference and meaningful negative variants, at least two
participant profiles have enough valid trials, and the score crosses the
declared threshold. Infrastructure-invalid attempts are retained but excluded
from ability scoring. The report never promotes a case automatically.

For multi-stage Harness attempts, the operator now records one
`agentlab.assessment_process_measurement.v1` object in both the summary and
decision package. It is reconstructed from retained stages and covers
participant/Oracle/stage duration, changed and unauthorized path counts, scope
violations, and Oracle false-to-true recovery or true-to-false regression. The
collector rejects summary/decision or aggregate/stage disagreement. The scorer
reports process coverage per participant and case, plus a 95% Wilson interval
for every participant pass rate. Legacy or standalone emulator evidence without
this contract remains outcome-scoreable but has `processAwareEligible=false`.
Assessed Harmony campaigns now close that gap: the trusted emulator wrapper
binds runner duration, UI action/check rows, profile-workload actions and
SmartPerf sample count; the loop adds independent build and assessment wall
time, and the compound composer rechecks those retained bytes before appending
a measured `harmony-device` stage to the static process evidence.

`scripts/compose-agent-suite-scorecard.py` then joins an authenticated blind
review population to exactly one discrimination report per reviewed case. The
manifest freezes the expected participant capability order before inspecting
the outcomes. A case-level scorecard qualifies only when review, outcome,
process coverage, declared ordering and strongest-versus-weakest Wilson
separation all pass. Aggregate micro pass rates retain their trial denominators.
The resulting suite measurement still cannot establish representative sampling,
model-training exclusion or unseen-Agent eligibility and never auto-promotes.

Real run evidence enters the same scorer through a revision-fenced collection
manifest:

```sh
python3 scripts/collect-case-attempts.py \
  --manifest campaign/attempts.json \
  --output campaign/discrimination-input.json
python3 scripts/score-case-discrimination.py \
  --input campaign/discrimination-input.json \
  --output campaign/case-discrimination-report.json
```

The collection manifest uses schema `agentlab.case_attempt_collection.v1` and
binds one exact `sourceRevision` and `methodRevision`. Each case names a
calibration JSON file and each attempt names a participant plus an evidence
directory containing `summary.json` and `decision-package.json`. Paths are
relative to the manifest so the campaign remains portable. The collector
hashes both evidence files, accepts task success only from an independently
produced assessed decision package, and records infrastructure-unavailable
runs with a null verdict so they cannot become false Agent failures.

Multi-repository cases use `agentlab.case_attempt_collection.v2`: replace the
single-repository `sourceRevision` with the frozen case's exact
`sourceSetSha256`. The collector emits `agentlab.case_discrimination_input.v2`,
the scorer emits `agentlab.case_discrimination_report.v2`, and the TableGit
decision row retains that source-set identity rather than inventing a synthetic
Git revision. Attempt summaries and decision packages must carry the same
source-set digest; mixed or drifted source sets fail closed. The collector also
normalizes an exact `agentlab.multi_repo_calibration.v1` summary into the common
baseline/reference/negative-variant scoring contract while retaining per-stage
verdicts and the calibration file's digest as evidence.

Harmony emulator attempts use the same manifest with
`evidenceKind: harmony-emulator-v2`, an exact `sourceIdentity`, and an evidence
directory containing the runner's `result.json`. Only the explicit assessed
UI-oracle verdict is scored. Emulator/HDC infrastructure failures remain null,
excluded verdicts; old results without the explicit assessment fields are not
guessed into a participant outcome.
