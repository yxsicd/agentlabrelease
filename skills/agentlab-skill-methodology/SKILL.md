---
name: agentlab-skill-methodology
description: Maintain the two-layer Skill methodology across codebase analysis, seed construction, calibration and evaluation.
metadata:
  agentlab-role: maintenance
  agentlab-layer: method
  agentlab-stage: methodology
---

# Two-layer Skill methodology

Every stage has two layers, independent from maintenance/operations roles:

| Stage | Method Skill | Target instance Skill |
|---|---|---|
| Goal | Translate a challenge into evidence-backed acceptance | Maintain this challenge's scope, source corpus and remaining acceptance gaps |
| Semantic analysis | Learn responsibilities and behavior contracts | Explain how to maintain this codebase's concrete contracts |
| Program analysis | Extract structure and analyze coverage | Guide analysis of this codebase's actual symbols, imports and impact paths |
| Seed extraction | Derive demands from semantics and facts | Explain how to derive this codebase's tasks and multi-turn variants |
| Calibration | Independently validate oracles and references | Explain calibration of this task, its environment and failure variants |
| Evaluation | Run fixed inputs and capture/attribute outcomes | Explain execution and grading of this exact task |

Method Skills are reusable recipes maintained in Release. Instance Skills are
business rows in TableGit `maintainer_skills`, even when their role is operations.
The table name describes the maintained knowledge library, not a role restriction.
Program graphs/facts, task parameters, oracles and results remain structured rows
in `program_facts`/`evaluation_cases`; Skills reference them instead of replacing
them with prose. A task demand is not itself a runnable calibrated case.

Use `skillLayer` (method/instance), `role` (maintenance/operations), `stage` and
`objectId` independently. An instance records `methodSkillId`, `methodRevision`,
`methodDigest`, `sourceRevision`, `factIds` and task/evidence references. Method
revision is the Release commit containing the recipe, digest binds its exact
bytes. IDs remain stable as guidance improves. Source revision and TableGit
analysis input revision are distinct identities.

For each round:
1. Freeze method/source cuts and analyze with the available tools.
2. Maintain instance Skills and structured evidence in TableGit.
3. Derive candidates and independently calibrate runnable cases.
4. Freeze operational inputs; Harness owns execution/capture, regardless of
   scripted or intelligent supervisor and replaceable assessed Agent.
5. Archive results, use generic MCPGit analysis and improve a later instance cut.
6. Improve the method only when evidence supports a general lesson, preserving
   the method/instance lineage that explains older rounds.

Development TableGit is live instance authority. Export one sorted JSONL per
business table from a fixed cut; Release snapshots are imports, not a second
editable authority. Retain failed/partial controlled-test evidence without
redaction. Workspace/build binary snapshots use SessionFS. Do not add business
knowledge to MCPGit source or invent analysis endpoints.

Read [the registry](../registry.json) to select a method stage and role. The
[real Harmony demo](../../examples/knowledge-seed/README.md) produces instances;
its limited lexical/method calibration is not full HAP, Fork or Agent acceptance.

For a new maintainer, follow [the apprentice workflow](references/apprentice-workflow.md)
to reproduce a round, update the correct layer and leave a usable handoff. Each
round accumulates executable guidance and evidence references, not a second
copy of structured results in prose.

Independent compiler evidence stays in structured compilationEvidenceIds and
compilationGuidance on instance rows. Generated guidance references those fields.
When an analysis flow owns only some fields, compare/update that projection and
skip empty patches; whole-row inequality can be caused by another owned producer's
fields. This keeps ordinary analysis and compiler capture internally consistent.

Original Harmony compilation separates published SDK OHPM dependency preparation
from network-disabled builds. Archive preparation commands, logs, manifests and
locks; resolve module outputs through build-profile srcPath. A prepared dependency
is not a full-project compiler verdict, and a slice pass cannot overwrite it.

Store structured compiler elapsed time as integer wallMs. Raw JSON/log files
retain exact producer bytes. Floating elapsed seconds drifted on serialization,
causing repeat capture to advance a commit without semantic changes. Normalize
our compiler history consistently and prove the same producer capture twice
returns the same TableGit revision, not only identical exported rows.

### Knowledge and operational evidence remain separate

Keep reusable method guidance in Release and source/case-specific guidance in
TableGit instance rows, with independent method revision, source revision, role
and stage. Record findings for goal, repository semantics, program analysis,
seed extraction, calibration and evaluation separately.

The three initial knowledge snapshots contain Skills, analysis facts and frozen
tasks; full historical gateway/native/source/build captures belong in runtime
observation and payload tables. Preserve every raw byte. Return compact findings
and explicit table/cut/row plus published archive references to the knowledge
seed. Publish the complete runtime export independently when reproducible raw
evidence is needed. Never inflate the seed with repeated cumulative event payloads.
Use stable IDs and stable export order; prove file reconstruction and unchanged
repeat import before publishing. See [the executable experiment](../../examples/knowledge-seed/subject/README.md).

Choose explicit indexes for actual queries (run, phase, kind, tool, file, cut and
ordinal); do not auto-index every scalar field. Structured retention and indexing
are different concerns. Keep full data while selecting useful query projections.
