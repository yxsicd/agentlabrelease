# Terminal-Bench with operator-owned capture

The optional Harbor 0.25.0 adapter `harbor_agent:HostMini` runs the pinned
mini-SWE-agent 2.4.6 on the operator host. Each command executes inside the
Harbor-assigned Docker task container, at the container's actual workdir. The
operator verifies the container ID, Compose project and service, image ID, and
local Agent version before model dispatch. The task container does not receive
the Docker socket or the upstream Gateway key. The Gateway proxy and raw
capture remain in a private operator-owned attempt directory, outside the task
container mounts.

Before running a participant, freeze the exact benchmark task revision, image
ID and evaluator, and run the official reference solution in a separate fresh
container. The adapter needs explicit `AGENTLAB_ATTEMPT_ROOT` (a new private
empty directory), `AGENTLAB_WORKTREE`, `AGENTLAB_MINI_PYTHON`,
`AGENTLAB_GATEWAY_URL`, `AGENTLAB_LM_GATEWAY_KEY`,
`AGENTLAB_PROVIDER_ROUTE`, `AGENTLAB_EXPECTED_TASK_IMAGE_ID`,
`AGENTLAB_TOKEN_BUDGET`, and `AGENTLAB_WALL_SECONDS` in the operator process.
Select the requested model as `openai/<model>` in Harbor. Do not put Gateway
credentials into the task, arguments, Git or participant environment. Set
Harbor retries to zero and set its Agent timeout above the configured Agent
wall fallback plus the operator's 60-second shutdown allowance. Token budgets
are checked per attempt between requests; the final request may exceed them.
The participant does not get an MCP budget query in this integration.

Use a distinct `--install-only` Harbor trial first to verify the binding without
a model call. It is preflight, not a student evaluation. After any unknown effect,
inspect the original attempt and Gateway capture before starting anything new.
The user-visible Agent gets only the task instruction; never mount the reference
solution or private evaluator in its workspace. A Harbor process exit of zero
alone is not a successful student run: inspect the trial exception, official
verifier, operator lifecycle and complete Gateway usage separately.

`report.py` generates an operator-owned HTML and JSON assessment from the
original student evidence, Harbor trial, and reference qualification. It verifies
reference evidence hashes and exact task/image bindings; incomplete model
capture or a failed operator/Harbor stage leaves the result unscored. It
recomputes tool-error counts from raw events: mini-SWE-agent's `Submitted`
exception is a normal submission signal, not a failure. Preserve the original
lifecycle even when the report corrects its count. A successful outer shell
command can hide an inner Git conflict, so the report also records observed
conflict output; raw tool output is the authority for deeper interpretation.

The task and trial directories must remain private while they contain reference
solutions or model traces. The generated report's evidence paths point to the
original retained files. A single reference pass qualifies only that observed
task/environment; a single participant pass is not a general model ranking,
AgentLab native Session/Fork proof, or an MCP budget-query qualification.

`../benchmark-report/compose.py` also composes retained SWE assessments and
one Terminal attempt into a single view, preserving dataset-specific results
and evidence links. It re-derives both sides from retained evidence; it does not
combine different benchmarks into a single success rate.
