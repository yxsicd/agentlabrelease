---
name: agentlab-seed-extraction
description: Generate evidence-linked multi-turn task seeds from semantic Skills and program facts.
metadata:
  agentlab-layer: method
  agentlab-role: maintenance
  agentlab-stage: seed-extraction
  agentlab-ownership-plane: repository-native
---

# Seed extraction maintenance

Combine repository maintainer Skill rows, typed dependency facts and archived analysis results from fixed cuts. Construct tasks with a concrete requirement, baseline source/environment, cross-file impact, staged user demands and observable acceptance checks.

Treat case generation as an iterative search over a revision-bound knowledge
cut, never as a one-pass export. A scope Skill that only names files,
languages, build entrypoints or imports is routing evidence; it is not yet a
behavior-ready seed. Generate a candidate only after binding a semantic
responsibility, a program relation or state transition, and an executable
Oracle hypothesis to the same source revision.

For every generation round, preserve the parent round, objectives, exact
knowledge cut, coverage before and after, generated/retained/rejected
candidates, Oracle and calibration outcomes, and feedback gaps. Use failures
and uncovered responsibilities to select the next Maintainer Skill refresh,
program-analysis expansion, or candidate cohort. A first round, an empty
cohort, or zero qualified cases is a baseline result, not convergence. Stop
only with an explicit `converged` or `blocked` decision and its evidence. Follow
[the iterative generation contract](references/iterative-case-generation.md)
and validate round records against
[`case-generation-round.schema.json`](../../schemas/case-generation-round.schema.json).

This ordering is mandatory. Feedback may rank grounded candidates but MUST NOT
create a case directly from shared names, imports or failure prose. Candidate,
construction, calibration and freeze transitions each require a passing receipt
from [the maintainer knowledge gate](../../docs/maintainer-skill-gated-case-pipeline.md).

Declare runtime routing independently of repository identity. The shadow
constructor accepts `--runtime-target harmony-emulator|repository-test`; its
existing wrapper uses `AGENTLAB_SHADOW_RUNTIME_TARGET` and retains the historical
Harmony default when unset. The repository-test lane proposes a controlled
repository runner rather than requiring an unrelated emulator. A scope with an
`ohosTest` entrypoint still requires the Harmony emulator lane. Both routes keep
external hardware and physical-device fallback disabled, retain unqualified
Oracle hypotheses, and require the same source/scope/knowledge and later
calibration gates. Operator routing declarations are not execution proof. Do
not infer a platform from a repository name or count a valid proposal as a
calibrated case. Unsupported or hardware-dependent proposals return explicit
failure feedback rather than silently falling back to another runtime.
New proposals retain the runtime target and canonical request-value SHA in
lineage so later consumers can distinguish routing cuts without rewriting
historical candidates. The value digest is not the original request-file SHA.

Fresh shadow requests declare `oracleFramework` from their runtime contract:
`ohosTest` on the Harmony emulator, `repository-test` on the host repository
lane. An empty test inventory is a harness-construction gap, not evidence for
a different framework. Retained requests keep their historical inference and
bytes; regenerate a new request rather than relabeling a completed proposal.
Independent source review must separate old-instance field cleanup from resource
leak claims, single-change negative controls from confounded mutations, and an
evolving implementation task from several unrelated smoke tests. Shape validity
and isolated Agent completion do not establish these semantic properties.

Before implementing an Oracle, reconcile the demands with the pinned module
kind, supported SDK, registered tests, installable host and permitted edits.
Framework selection does not establish any of these. If a demand needs a new
host page, test registration or cross-scope dependency absent from the bound
evidence, return a focused knowledge/construction gap with the owning scopes;
do not invent installation commands or silently grant those paths for editing.
After refreshing the supporting facts, create separate successor inputs and
calibrate the actual host/test combination. Keep a passing proposal-shape check
separate from this source review and from baseline/wrong-variant execution.

For a rejected, unpublished operation-origin draft, prepare
`--prepare-shadow-case-revision` with the committed knowledge, operation inputs,
current shadow request, original parent request/proposal and source-review feedback.
Rust reproduces the current request, preserves parent identity except the explicit
framework-policy correction, and bounds findings to the semantic source evidence.
The packet retains original UTF-8 bytes and digests, not an approved replacement.
Pass it to `case_generation_shadow.py run-agent --revision-request` together with
`--flywheel-tool`, `--knowledge` and `--operation-inputs`; native revalidation runs
before dispatch. Each fresh attempt receives the original proposal and feedback,
keeps them unchanged, and disables transport retries. This is a revision input
handoff, not successful semantic repair, calibrated-case admission or a full loop.

The shadow constructor accepts explicit `--reasoning-effort` and
`--max-output-tokens` through the existing captured participant adapter; defaults
remain unchanged. Consult the selected provider's supported values, freeze source,
task, feedback and deadlines, then inspect the actual upstream request before
attributing a timing change to configuration. Keep incomplete terminal streams and
missing proposals as transport/construction failures, not semantic repair results.
A faster completed draft still needs independent review and calibration; historical
runs with different method cuts are exploratory controls, not a causal paired test.

After focused knowledge refresh, derive a stable successor candidate instead of
rewriting the original candidate or construction plan. Bind the parent candidate
ID/value digest, parent knowledge cut, refreshed fact digest and refresh receipt
digest in lineage. Require the refreshed fact to match the current exported cut.
Keep the old candidate and plan intact, and create a separate child plan. Clear
inherited runtime, Oracle and wrong-variant receipts because they bind the parent,
not the child; a knowledge-only successor remains unqualified. Validate the child
in an isolated projection before publication, and prove an unchanged repeat does
not append another candidate or alter any retained parent. The historical
`focused_fact_refresh.py rebind-candidate` command now performs this additive
derivation; its returned `candidateId` and `successorPlan` identify the child.

After candidate generation or refresh, run
`bash scripts/plan-maintainer-downstream.sh KNOWLEDGE EVIDENCE_ROOT FRESH_OUTPUT`
with the built `agentlab-maintainer-skill-flywheel` binary. The bridge independently
reassesses each retained construction plan, then routes exact gate gaps in Rust:
knowledge refresh, Oracle implementation/calibration, declared wrong variants,
or exact runtime requirements. Calibration depends on the independent Oracle;
construction readiness still requires constructing/freezing an operational case,
not direct assessed-Agent dispatch. The batch validates parent value digests,
retains historical audits, schedules only unsuperseded candidates and reports
candidates missing plans. Consume batch `activeCandidateIds`, not every individual
historical plan. No authority, execution or qualification is created by routing.
For bounded local repetitions, pass the previous output directory as argument
four: unchanged gate evidence stops scheduling even if unrelated knowledge cuts
or JSON formatting change. Cross-Action history reuse is not yet wired; retaining
an artifact alone does not prove this guard applies across fresh runners.

For retained partial captures, the same bridge optionally reads profiles from
`AGENTLAB_PARTIAL_CALIBRATION_ROOT/profiles/<candidateId>.json` and emits a separate
`scoped-next-actions.json`. Keep raw envelopes under that root. This lane does not
replace `next-actions.json`, change the candidate or qualify the construction
plan. Unsupported profiles/readback failures stop the batch explicitly. Missing
profiles retain the normal formal route; never interpret their absence as proof
that no historical experiment exists. Follow the calibration Skill to consume
and scope that evidence before spending another diagnostic turn.

When replacing an invalid raw knowledge export with a reviewed snapshot, reconcile
independently retained candidate and generation-round records too. Verify their
original value digests and parent-round link before restoring them; keep original
knowledge-cut bindings and unqualified status. Restoring a historical proposal is
not new knowledge coverage, a new Agent run, or permission to merge the invalid
authority export. Prove the restored input can prepare the next gated refresh
without changing any authority table.

Write stable `evaluation_cases` task rows with source/knowledge cuts and analysis references. Keep assessed-Agent-visible requirements separate from operator-owned reference patches and grading evidence. Do not disclose a gold implementation as part of the task prompt.

Use a strong construction Agent or deterministic generator as appropriate. Capture construction actions as Harness-owned evidence too. Agent-proposed seeds are candidates until independently calibrated; quality of the construction Agent is not the assessed-Agent score.

Start with dependency-supported scenarios, not arbitrary mutations. A multi-turn seed should include meaningful continuation or changed requirements and regressions that earlier decisions can influence. Preserve exact checkpoints for counterfactual Fork comparisons when the installed Harness supports them.

Send candidates to [benchmark calibration](../agentlab-benchmark-calibration/SKILL.md). Maintain proposed/unbuildable/ambiguous cases with their failure evidence instead of deleting them. Freeze calibrated cases for [operations](../agentlab-benchmark-operations/SKILL.md); feedback creates a later knowledge cut.

Produce target-instance guidance for this stage as TableGit Skill rows,
separate from the structured facts/tasks/results. Follow
[the two-layer methodology](../agentlab-skill-methodology/SKILL.md) for
method/source lineage and independent layer/role fields.

### Cross-file durability candidate

`subject/cache-durability.cjs` executes submitted PreferenceManager,
PreferenceCacheHelper, SampleService and SampleModel modules with controlled
Preferences and network seams. `subject/calibrate-cache.cjs` compares baseline,
Rust-materialized reference, lost-flush and lost-model-await variants. Archive
full sources, AST rows and ordered settlement events. The contract separates
network failure fallback from persistence failure: await the write outcome, log
a failed write, retain fresh network data. A helper must expose write failures.
The candidate and its frozen operational child are separate rows. A new frozen operational contract and actual subject execution are separate.
Full phone compilation and archived TableGit program/semantic queries are now
verified for the reference; preserve their exact receipts.
Do not promote it based on JavaScript seam execution alone.

`agentlab-cache-seed` prepares the committed four-module candidate in Rust.
`subject/maintain-cache.py` owns development TableGit import/update, generic
program and semantic SQL, and committed three-table export. With unchanged
prepared rows reuse existing analysis records; do not create a revision feedback
loop by re-querying and writing a new cut into otherwise unchanged rows.
Staged calibration has8 checks in turn1 and10 in turn2. Missing model await is
a turn2 negative and must pass turn1; preserve network fallback, synchronous
put failure propagation and neighboring record entries alongside durability.

The frozen `case-cache-durability-subject-v1` consumes demands/paths from the
TableGit export directly; the runner has no second hand-maintained cache
contract. Local, CI and real runs share staged calibration. Operational evidence
returns through captured runtime/context and calibrated lesson tables; it does
not rewrite the frozen candidate or method inputs.
