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

Harmony emulator attempts use the same manifest with
`evidenceKind: harmony-emulator-v2`, an exact `sourceIdentity`, and an evidence
directory containing the runner's `result.json`. Only the explicit assessed
UI-oracle verdict is scored. Emulator/HDC infrastructure failures remain null,
excluded verdicts; old results without the explicit assessment fields are not
guessed into a participant outcome.
