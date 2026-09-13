---
name: agentlab-seed-extraction
description: Generate evidence-linked multi-turn task seeds from semantic Skills and program facts.
metadata:
  agentlab-layer: method
  agentlab-role: maintenance
  agentlab-stage: seed-extraction
---

# Seed extraction maintenance

Combine repository maintainer Skill rows, typed dependency facts and archived analysis results from fixed cuts. Construct tasks with a concrete requirement, baseline source/environment, cross-file impact, staged user demands and observable acceptance checks.

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
