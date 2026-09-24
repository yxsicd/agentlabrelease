# Curated official SWE seeds

These seeds exercise the imported SWE-bench methodology; they are not the
design ceiling for generated AgentLab cases. The rationale, advantages, gaps
and adopted generalized repair/preservation qualification matrix are recorded
in [the SWE-bench strategy comparison](../../docs/swe-bench-strategy-comparison.md).

Run `swe-campaign.yml` for one seed or all four. The catalog binds full official
SWE-bench Lite records by canonical SHA and base commit. `seeds.py` retains the
complete original task, reference patch, test patch and FAIL_TO_PASS/PASS_TO_PASS.
Only the issue statement enters the subject task. The mini-SWE-agent Python
runtime is outside `/testbed`; the project executes in the official instance
image. The operator captures Gateway exchanges and extracts the actual patch.
The pinned official SWE harness tests that patch in a fresh environment, and
separately tests the official reference patch. Reference failure means the
benchmark/Harness is not qualified. A healthy benchmark with an unresolved Agent
is a valid measured result; the Action can pass while `agentResolved=false`.

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
