# Curated official SWE seeds

The optional `--catalog examples/swe-bench/catalog-verified-sympy.json`
selects the separately pinned Verified `sympy__sympy-20590` case; without it,
the original Lite catalog and offsets are unchanged. The selected record and
base commit are validated before a participant is dispatched. Its independent
evaluator reads the exact frozen single-row dataset, avoiding dataset drift.

The SWE runner defaults to no model-call step limit and a 1,800-second Agent
wall-clock fallback. Operators may pass `--step-limit` (0 disables it) and
`--wall-time-limit-seconds`. The supervisor watchdog gets an extra 60 seconds.
Each run records these settings, the no-replay transport policy and the native
participant exit status. A time or step limit is not evidence of a model defect.
`--token-budget` optionally enforces an attempt-local input-plus-output budget
at the operator Gateway between model requests. It serializes budgeted requests,
counts cached input and reasoning output only within their parent totals, and
stops further requests if prior usage is missing or incomplete. The final request
can exceed the limit; this is not a strict token cap. The participant watchdog
also stops client-side retry once the gateway records a budget denial or unknown
usage. The default is no token
budget, and the summary records whether the option was enabled. Budget-denial
evidence distinguishes an exhausted balance from unknown usage. The Agent MCP
budget-query interface is not provided by this runner.
`usage-observation.json` summarizes the captured response usage per exchange,
with field coverage and incomplete exchanges. Cached input is a subset of input,
and reasoning output is a subset of output; do not add these subsets again.
For a local mini-SWE-agent using an official task container, the operator
launcher resolves the selected local Docker socket before the model starts and
passes only that endpoint to the isolated participant process. It does not
mount the Docker socket into the task container or copy Docker credentials.
An unavailable or non-local Docker context fails before model dispatch. Tool
errors in the lifecycle include nonzero command exits and explicit exceptions;
they remain distinct from the independent task verdict.

These seeds exercise the imported SWE-bench methodology; they are not the
design ceiling for generated AgentLab cases. The rationale, advantages, gaps
and adopted generalized repair/preservation qualification matrix are recorded
in [the SWE-bench strategy comparison](../../docs/swe-bench-strategy-comparison.md).

Run `swe-campaign.yml` for one seed, including the pinned Verified SymPy case;
`all` retains its original meaning of the four curated Lite cases. Its
`token_budget` input defaults to 500,000 input-plus-output tokens per attempt;
the request-boundary overshoot described above still applies. A capture-only
replay does not dispatch a participant or consume that budget. The catalogs bind full official
SWE-bench records by canonical SHA and base commit. `seeds.py` retains the
complete original task, reference patch, test patch and FAIL_TO_PASS/PASS_TO_PASS.
Only the issue statement enters the subject task. The mini-SWE-agent Python
runtime is outside `/testbed`; the project executes in the official instance
image. The operator captures Gateway exchanges and extracts the actual patch.
The pinned official SWE harness tests that patch in a fresh environment, and
separately tests the official reference patch. Reference failure means the
benchmark/Harness is not qualified. A healthy benchmark with an unresolved Agent
is a valid measured result; the Action can pass while `agentResolved=false`.

The workflow generates `evidence/report/evaluation.html` and `assessment.json`
from operator-owned receipts and the two official evaluator reports. A passing
patch and a normal Agent submission are separate observations; an absent or
failing reference leaves the student result unscored. Missing assistance or
usage is unknown, not zero. Evidence links carry SHA-256 digests. To regenerate
the report without redispatching a model, select a new direct child of the
preserved evidence directory:

```sh
python3 examples/swe-bench/report.py --evidence /path/to/evidence \
  --output /path/to/evidence/report-copy
```

To compare retained assessments without re-running participants, pass each
assessment to `campaign_report.py --assessment /path/to/assessment.json` and
select a fresh `--output` directory. It verifies source evidence digests,
reconstructs the assessment and HTML from those sources, rejects inconsistent
results and semantically duplicated assessments, and groups separately by benchmark,
participant, model, reasoning setting and budget. Its attempt-level resolved
rate excludes Harness failures and unscored attempts; it is not a leaderboard
or a representative estimate from a small sample. Keep the linked evidence
directories alongside the aggregate when moving it. These checks establish
internal consistency, not an authenticated signature of evidence origin. The
current `report.py` must match the version that generated each assessment;
after a report format or interpretation change, regenerate explicitly from
retained evidence rather than silently mixing interpretations.

This public tier records full operator-owned source evidence in TableGit and
proves cold reconstruction. It does not claim formal SessionFS snapshots of the
SWE container or normalized full-whitebox coverage. SessionFS Workspace/Fork
acceptance remains independently covered by the existing public Harness demos.

The dataset pages and exact source records are retained in artifacts. The
catalog is a bounded initial set, not the full SWE-bench suite. The fixed channel
checks are unchanged; a campaign is additional coverage, not automatic promotion.

Official images can add an environment-preparation commit after the task base.
The Harness binds both identities, verifies task-base ancestry, preserves the
preparation diff and image digest, and freezes the prepared execution cut before
launch. Final patch extraction uses that frozen cut even if the Agent commits;
new non-ignored files are included without modifying its Git index. It must not
require task base, prepared HEAD and changing evidence HEAD to be equal.

Set `capture_run_id` to a prior SWE campaign and select the same case(s) to prove
current structured ingestion/cold reconstruction without redispatching the Agent.
Original capture bytes and producer revision remain unchanged. Such a replay is
capture recovery evidence, never a fresh Agent evaluation or a repaired solution.
Seeds, baselines, participant bindings and evaluator reports additionally appear
as method-typed source observations, alongside exact raw file reconstruction.
