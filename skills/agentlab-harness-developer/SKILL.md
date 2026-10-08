---
name: agentlab-harness-developer
description: Operate a deployed AgentLab instance's repository-understanding, maintenance-validation and case-evaluation flywheel through its advertised capabilities. Not for deployment or private source maintenance.
metadata:
  agentlab-layer: method
  agentlab-role: operations
  agentlab-stage: harness
---

# AgentLab instance flywheel

Complete the human -> Agent -> AgentLab instance journey. Obtain an instance
SKILL URL and separately configured authorization from the operator. For
installation or historical removal, use [deployment](../agentlab-deployment/SKILL.md).
Do not assume a hostname, port, private repository, host filesystem or framework.

## Discover before acting

Fetch the instance SKILL without credentials and follow its explicit
`service-manifest` URI. Resolve endpoint/catalog/profile URLs relative to the
manifest document, preserving proxy paths. Never guess a fallback endpoint or
forward credentials cross-origin. Read the selected deployed capability contract,
authenticate separately, initialize MCP and inspect the effective capability set.
The [public discovery demo](../../examples/service-protocol/README.md) shows this
protocol; its fixture verdict is not this instance's readiness or full-loop proof.

Require capabilities for each intended stage before dispatch. Missing Session,
repository analysis, participant execution, capture, checkpoint/Fork, independent
evaluation or knowledge return must produce a precise blocked result. Do not
invent tools, fill in private endpoints, read the private source or do decisive
work through an unrecorded host shell. This Skill describes the final contract;
the deployed manifest determines which operations are actually available.

## Select the participant

Read [participant modes](references/participant-modes.md) when choosing A/B,
remote/shared/native, independent model routes or context/environment restoration.
Prefer lightweight A: the supervisor controls an isolated subagent and explicitly
selects its context; the subagent is assessed through Attempt-scoped remote MCP.
Do not inherit the complete supervisor conversation or require a separate model
key for A. B adds an independently model-key-driven assessed Agent. Agent
framework, runtime, provider, credential route and state restoration remain
independent axes. Supported and qualified combinations come from the deployed
adapter, not this vocabulary.

Keep Control and Participant authority separate. A participant cannot read private
checker information or act as its own evaluator. Real provider credentials remain
in the gateway; never insert them into tasks, model context or captured artifacts.

## Bounded local knowledge construction

If the operator explicitly requests the first two knowledge rings locally,
select [codebase analysis](../agentlab-codebase-analysis/SKILL.md) and the existing
`scripts/run-maintainer-skill-local-flywheel.sh`, which reuses the same Agent loop
as the Action's construction path. This is a **maintenance construction Agent**, not an assessed
A/B participant or a replacement for instance Session/Attempt capabilities.

From a pinned public checkout, build the existing Rust
`agentlab-maintainer-skill-flywheel` and install Pi **1.1.0** outside the source
workspace with `examples/real-code-agent/participant/package-lock.json` (`npm ci --ignore-scripts`).
The operator separately configures Gateway URL/key, model and provider route,
TableGit MCP URL/person and a unique `AGENTLAB_RUN_ID`; credentials never enter
the Agent task. Begin with `AGENTLAB_SCOPE_BATCH_SIZE=1` and one round:

```bash
bash scripts/run-maintainer-skill-local-flywheel.sh \
  /absolute/current-knowledge-cut /absolute/fresh-run REPOSITORY_ID 1 /absolute/pi
```

`AGENTLAB_FLYWHEEL_GATE` selects the verified existing executable when its build
location differs. Use an existing private parent outside the input cut and public
checkout for the fresh run. The wrapper admits the exact live TableGit input before model
budget, preserves the input cut, exports to `fresh-run/committed-knowledge` and
plans from that actual readback. Do not choose the historical example default
as current authority or retry a committed transaction because a later stage fails.
Read the preflight, sync, durable-reference and next-round receipts separately.

Shadow case sampling is off by default; `AGENTLAB_SHADOW_SAMPLE=1` spends a
separate model budget and requires an explicitly frozen nonempty case lineage
(`AGENTLAB_SHADOW_LINEAGE_ROOT` if absent from the committed cut). Its proposal
and round files remain run evidence, never edits to the immutable knowledge cut.
Missing case inputs remain a downstream blocker. Use bounded numeric rounds;
the historical `converge` estimate does not prove queue exhaustion or five-ring
convergence. Local construction/readback is not full Harness qualification.

## Pi supervisor and delegated test participant

The public Pi runtime lock installs Pi **1.1.0** and the reviewed
`@bermudi/pi-delegate` **0.4.0** together, outside the evaluated workspace.
Use `npm ci --ignore-scripts`; do not update a shared global Agent or enable
unrelated extensions. Add `--supervisor` to the existing
[`prepare-participant-runtime.py`](../../scripts/prepare-participant-runtime.py)
invocation (exact image, runtime, case input, operator-only forbidden paths and
fresh output). It verifies the actual Pi version and freezes the
[supervisor profile](../../examples/real-code-agent/participant/supervisor-profile.json)
with the complete plugin tree. The existing Participant/Docker launcher loads
only that explicit extension and rechecks its binding before execution.
For a fresh runtime add `--install-native-tools` to that same prepare command:
it installs pinned `rg` and `fd` from public GitHub, verifies archive and binary
digests, and preserves license notices. Platform is selected from the Docker
image's architecture, not the host. Later preparation and dispatch recheck these
immutable binaries; drift or participant-state overrides are refused. No model
starts without these dependencies, and offline execution never downloads tools.

The supervisor must delegate exactly the admitted child task, with `async:false`,
one `explore` task, explicit child-only `systemPrompt`, tools
`read,grep,find,ls`, `cwd:/workspace`, `workspace:shared`, and a **new unique
sessionId per Attempt**. Omit parent history, `brief`, dependencies and
`resumeFrom`. This session path disables whole-task retry and retains the child
JSONL; it does not mean resuming an earlier Attempt. Record parent command,
delegate arguments/result, both native sessions, every Gateway exchange, tool
paths/counts and exact exits before closing the child session.

Here `shared` is the dedicated contained workspace, not shared conversation.
Parent/child share one process and can read the same mounted files; validate
observed child read paths against the admitted public input. Do not claim
parent-context filesystem confidentiality. Parent discovery restrictions are
not inherited by the child: use a fresh empty workspace and Agent state, and
check the child's effective system sections for unadmitted AGENTS, Skills,
append prompts or other context before accepting the result. Child automatic
compaction is still
an upstream default, even with parent compaction disabled: count any extra model
call and reject an unadmitted summary/context change. The outer native watchdog
covers both Agents; tool-count checks are observations, not strict child
pre-dispatch limits. No independent external key enters either Agent.

This profile supports supervised delegation, **not** the missing Attempt-scoped
remote MCP broker. Do not qualify mode A assessment, full Harness readiness or a
five-ring closure from installing a plugin or producing a launch plan. A normal
extension-disabled assessed participant remains a distinct protocol; it rejects
supervisor and synthetic-transport runtime configs rather than mislabeling them.

## One evidence-driven flywheel

Choose any operator-selected repository set from HTTP(S) Git URLs or repository
archives. Read [source material](references/source-material.md) before intake.
Freeze each verified source snapshot; record real Git commits where available,
and initialize/commit a new project-Git baseline for non-Git material. Preserve
archive identity separately from that generated commit; original Git history is
not required for ordinary evaluation. Current intake still requires a qualified
snapshot/initialization bridge before admitting an archive.
Use [the registry](../registry.json) to load methods only for the active stage:

1. **Repository understanding:** select scope, build responsibility/boundary/
   behavior/operation guidance with evidence and explicit unknowns. Consume
   [codebase analysis](../agentlab-codebase-analysis/SKILL.md).
2. **Program-analysis correction:** bind guidance to actual source/facts and
   impact relations; revise it when evidence disagrees. Consume
   [program analysis](../agentlab-program-analysis/SKILL.md).
3. **Maintenance-operation verification:** perform the admitted operation under
   bounds; an independent checker verifies its behavioral contract and meaningful
   wrong controls. Structural coverage alone is not semantic or maintenance maturity.
4. **Case generation and execution:** derive difficulty candidates, independently
   calibrate an executable result checker, freeze blind participant/evaluator cuts,
   then run the selected Agent with fixed budgets. Consume
   [seed extraction](../agentlab-seed-extraction/SKILL.md),
   [calibration](../agentlab-benchmark-calibration/SKILL.md) and
   [evaluation](../agentlab-benchmark-operations/SKILL.md) for those steps.
5. **New evidence return:** archive exact inputs, outputs and failures; admit a
   reviewed lesson to a new knowledge cut, prove committed readback, and verify
   the next round actually consumes it. Consume
   [experiment learning](../agentlab-experiment-learning/SKILL.md).

Fix method/source/knowledge cuts and budgets before a round. Record task, Session,
Attempt, Agent/adapter/model, environment, interventions, tool/provider evidence,
checker verdict, revisions and next action. Instance Skills and facts are
TableGit business data; GitHub exports are fixed snapshots, not a second live DB.
Do not edit exported snapshots to manufacture a passing return.

## Continuation and acceptance

Read [evaluation model](references/evaluation-model.md) before a comparison,
[checkpoint/Fork](references/checkpoint-and-fork.md) before restoration, and
[observability](references/observability-and-sql.md) before trace analysis.
Keep actual LLM/MCP/workspace evidence separate from Mock/protocol fixtures.
Functional, performance, power and thermal claims require their own declared
measurement and environment evidence; emulator success is not real-device power.

An Agent saying done, a successful transport, a stored lesson, a healthy container
or a reference-patch pass is not full-loop acceptance. Prove independent results,
parent/child isolation when Fork is used, committed return and next-round
consumption. Preserve failed/partial evidence and uncertain outcomes; reconcile
durable state before retrying a mutation.

Return a bounded report: stage verdicts, exact evidence identities, remaining
capability/semantic blockers, cost/budget and one next admitted round. Do not
increase maturity merely for new instructions, receipts or asset counts.
