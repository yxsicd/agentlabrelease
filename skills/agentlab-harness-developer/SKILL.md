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

## One evidence-driven flywheel

Choose any operator-selected repository set and pin each full source commit.
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
