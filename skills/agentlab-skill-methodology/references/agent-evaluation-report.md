# Evidence-backed Agent evaluation reports

An evaluation report describes the evaluated Agent, protocol, observed outcomes
and uncertainty. Participant-authored tests/reports are task artifacts, never the
final grade. Maintain the single-task teacher-assisted exploration scope until a
separate frozen independent cohort exists. Do not copy a leaderboard format that
implies a model ranking from mixed dependent runs.

## Report contract

1. Identify task/corpus/commit, Code Agent/version, model identifier, requested and
   observed thinking, tools/environment, budget, initial-state and assistance.
   Unknown effective provider effort/API/SDK versions stay unknown. The latest
   configuration must not be silently applied to historical rows.
2. Separate whole-task completion, stage checks and native process status. Define
   denominator and unit next to each metric. Preserve old failures and mixed labels;
   a historical failed stage can include an upstream failure, not a capability error.
3. Show independent, assisted, partial, failed and ungraded stage counts, without
   converting continuation counts to whole-task pass rate. pass@k, pass^k and
   confidence intervals require a qualifying frozen repeated-run cohort; they are
   not interchangeable and missing estimates are null, not zero.
4. Explain cost/time scopes. Token usage includes separate input/output/cache
   fields and per-run coverage; partial messages are not a full-run total. Do not
   sum potentially overlapping legacy aggregates. Dollar cost needs actual billing.
   Participant elapsed time includes timeouts and is not application performance.
5. Link strengths, weaknesses and root-cause hypotheses to numbered run evidence.
   Distinguish handled difficulty, blocked difficulty and untested difficulty.
   Separate model behavior, Harness faults, upstream errors and unknown causes.
   Help events and inherited context remain part of the student's assessment;
   post-help progress plus added budget is not a controlled causal effect.
6. Let readers inspect/filter ledger rows, reset to the full population, and open
   evidence links that reveal hidden rows. Clearly scope filters to the ledger;
   report-wide totals stay fixed unless explicitly recalculated from that cohort.
7. Keep private inputs, raw traces, operation/session IDs and credentials private.
   Allowlist public fields and bind input commitments. Preserve immutable report
   versions and the IDE-style reading shell. State remaining measurement gaps.

## Executable current sample

`scripts/enrich-public-evaluation.py` consumes the existing public projection,
its matching private report and `scripts/export-public-evaluation.py`. It requires
the reviewed 31-operation Calendar cut and verifies source commitment, row
correspondence, duration, outcome/tool totals and usage arithmetic before output.
It generates a new immutable report v2 with no network/student dispatch or grade
changes. It is a bounded adapter, not a generic benchmark schema migration.

```sh
python3 scripts/enrich-public-evaluation.py --private-report PRIVATE_JSON \
  --public-report PUBLIC_V1_JSON --exporter scripts/export-public-evaluation.py \
  --output NEW_REPORT_VERSION_DIRECTORY
```

Current coverage: 1 task / 31 dependent operations / 6 retained points. No complete
independent whole-task repeat; no full billing/cost/useful-call-rate comparison.
The v2 adds protocol/config, stage distributions, metric definitions, scoped usage,
run-linked causal alternatives and filtered ledger without new executions.
The next useful evidence is a frozen same-task independent cohort after exploratory
acceptance, not more report decoration or expansion to many tasks prematurely.

## Primary references inspected 2026-10-25

- [SWE-bench](https://www.swebench.com/): task-instance Resolved denominator,
  evaluation subsets and common running environment.
- [OSWorld 2.0](https://osworld-v2.xlang.ai/): binary/partial completion, effort and
  resource context, long-horizon trajectory-linked failure examples.
- [tau-bench](https://taubench.com/): verifiable environment outcomes and repeated
  reliability; task audit corrections are distinct from participant repair.
- [HAL](https://hal.cs.princeton.edu/): cost-controlled evaluation, usage and traces.
  Search-indexed primary text was available; direct fetch returned403. Do not
  claim its current scores were independently fetched or compare our scores.

These are methodological references, not accreditation or equivalent task
populations. Do not import their headline scores into this sample.
