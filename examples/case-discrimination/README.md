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
