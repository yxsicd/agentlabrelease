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

### Asset lifetime is a separate axis

Read [asset modeling](../agentlab-asset-model/SKILL.md). Method versus target
instance is independent from reusable knowledge versus execution-instance assets.
A target-codebase semantic Skill is reusable; a particular campaign's feedback
is operational data. Keep the three knowledge tables separate from concrete run
results, latest-run pointers, calibration output and raw evidence. Operational
ingestion never updates reusable guidance automatically. Promote lessons explicitly.

Use typed analytical entity tables, content-versioned messages and durable context
head Git history. Preserve original files independently; storage chunks are not
business observations. Export each asset class from an exact TableGit cut with
stable row order and demonstrate targeted analysis plus unchanged repeat import.

### Close each experiment into maintained experience

Follow [experiment learning](../agentlab-experiment-learning/SKILL.md): archive
analysis code/input cut/result, maintain evidence-linked lessons and validations
in the instance, then explicitly promote scope-bound verified knowledge. Public
Action exports the candidate from committed TableGit and proves active knowledge
is unchanged; maintenance imports/exports accepted candidates before source Git
publication. Improvements also become executable regressions where applicable.

For a first round without applicable experience, use explicitly reviewed bootstrap
state rather than borrowing another repository's lesson. For later rounds, follow
[committed lesson continuation](../../docs/flywheel-committed-lesson-continuation-20261003.md):
verify complete committed knowledge and operational-source readbacks, select the
admitted guidance explicitly, and retire prior executable inputs before scheduling
new work. State advancement is not fresh analysis, model consumption or benefit.

For maintenance verification, an exact-cut reviewed source-operation catalog can
let the business runner select the next actual capability gap and execute its
matching recipe. Do not substitute another responsibility's recipe when the
selected recipe is absent. Keep captured evidence, direct execution and catalog
selection mutually exclusive. Requalify the fresh capture independently and
retain the resulting knowledge candidate separately from committed active
knowledge. Source-only qualification does not grant build, runtime, performance
or full-loop acceptance; catalog selection is not automatic recipe generation.

Keep original method bytes and analysis projection identity when revalidating older
evidence after a tool upgrade. Record the current validator separately and compare
all reconstructed semantic results; do not rewrite historical rows to match current
IDs or substitute the current method for a frozen historical one. Hash agreement
does not authenticate the declared Git revision or original producer.

For integration delivery, reproduce the workflow's actual preflight gates, not
only its downstream tests. Build native planners before integration tests that
invoke them; an existing local target directory can hide a clean-runner dependency
failure. Preserve those real planner checks rather than skipping them or replacing
them with success fixtures. Formatting and dependency-order repairs improve
delivery reliability, not semantic coverage or completed flywheel-round counts.

When a clean-runner gate exceeds its budget, inspect the individual test and a
completed comparison run before calling it a hang. Repeated exact-byte executable
hashing can dominate debug builds, especially when one platform has a small loader
and another a monolithic runtime. Measure representative byte volumes. Prefer
optimizing the hashing dependency over weakening identity checks, caching by
metadata, skipping negative controls or blindly extending deadlines. Preserve
known-digest and changed-byte regressions; local timing is not cloud acceptance.

For source-rich authoring, distinguish process argument limits from model context
limits. A pre-launch E2BIG is infrastructure failure, not Agent inability. Preserve
the complete prompt and use a supported file/stdin transport rather than trimming
source to make dispatch pass. Verify exact UTF-8 bytes through the actual launcher
and container stdin path; bind the original prompt digest in lifecycle evidence.
Pinned Pi trims outer stdin whitespace, so verify captured request content before
claiming exact model consumption. Transport regression and isolation smoke alone
do not qualify a real construction or completed business round.
See the [prompt transport checkpoint](../../docs/flywheel-prompt-transport-20261003.md).

When reusing source context across design and code turns, verify the actual
upstream history retains the complete original source message and the new turn
does not duplicate it; a reuse receipt alone is insufficient. Report request
volume separately from generation completion and latency. A real reduced-context
code turn still reached its deadline with reasoning only: transport savings do
not establish provider-policy effectiveness, useful code or a successful loop.
Retain a validated design as unreviewed evidence, not semantic approval or a
license to reset an exhausted repair budget.
For incomplete generation, separate proxy-observed response-header/body arrival,
first parsed protocol event, first reasoning/text delta and semantic terminal.
Keep-alive bytes are not model output; an unobserved stage is null, not zero.
These timings locate waiting versus observed output, not provider queue or compute
causality. Provider-created timestamps and model catalogs cannot replace arrival
measurements or demonstrate that a reasoning policy was honored.
If code text starts near the observed deadline, test a separately
recorded code-phase budget rather than extending every stage. Keep design limits,
repair counts, transport retry policy and semantic admission unchanged; propagate
the selected budget to bounded code repairs. A longer deadline is a controlled
completion experiment, not a speed improvement. Compare useful completed output
and total cost before making it the default.

For bounded design correction, return the failing scenario's JSON pointer and
the exact required shape, not only a generic contract label. A real constructor
repeated an empty named seam after one correction despite initial schema guidance.
Distinguish an unresolved check pointer from a mismatched expected value. Report
the check index, exact pointer and available scenario IDs: a constructor kept
abbreviated IDs after generic feedback and changed business expectations instead.
For resolved mismatches, show bounded declared values without silently correcting
either side or treating internal consistency as semantic truth.
Distinguish controlled external dependency outcomes from the tested method and
its expected observations: no external dependencies may use an empty seam
inventory, but a declared dependency needs its frozen outcome sequence. Keep
rejected originals and unchanged admission rules; do not fill in Agent output
or move expected results into dependency inputs to obtain a pass. Diagnostic
regressions establish feedback mechanics, not successful model correction or
semantic qualification.

After static correction succeeds, review executable source contracts separately.
For the compiler-backed frozen-runtime protocol, the explicit
`fromCompilerInvocation(process.argv)` entry loads the supplied compiler at
argument four; it does not search for dependencies or repair legacy null callers.
Keep text/JSON-only invocation separate and retain dependency identity checking
in the outer executor. After feedback fixes a scenario, also trace newly added
requirements to the exact tested body: a real successor borrowed a nearby UI
builder's styling requirement for a code generator that never emitted it.
Match explicit import-map keys to original specifiers, including relative depth.
For each mutation, trace every scenario through both the changed operation and
later operations skipped by an early exception; a mutation may fail more checks
than its named target scenario. Record those findings before executing a reviewed
successor, not by expanding expectations after observing failures. Distinct
source text is insufficient for independent valid controls when only comments,
whitespace or erased type annotations differ. A live corrected design plus
unreviewed staging proves bounded construction, not maintenance qualification.
When review corrects mutation failure attribution, preserve the original baseline
demands unless independent review explicitly rejects that oracle. A wrong-control
exception may skip later updates; that does not mean the normal caught-exception
path skips them. Compare parent and successor checks before execution. Prompt
guidance alone is not an enforced parent-contract gate or semantic convergence proof.
For proposal-review revisions, use the native parent-check admission in the
linked checkpoint: v1 protects all parent checks; v2 permits only explicitly
reviewed exact before/after changes tied to source-grounded findings. Revalidate
the retained parent packet and admission on final staging and operator approval.
When an original design exists, bind its exact bytes using a v3 review and v2
revision packet. Preserve complete scenario records by default, including initial
state, ordered inputs/dependency outcomes and expected observations; authorize
changes only through exact source-finding-bound scenarioChanges. Require the
successor design at staging and revalidate it at approval. Check-only legacy
packets cannot establish scenario preservation, and equal design records cannot
prove the generated verifier actually interprets them correctly. These gates do
not authenticate reviewers or establish a reviewed Oracle's semantic truth.
When a completed code turn is rejected for changing frozen checks, first review
the design's source semantics. If the design is wrong, use an explicit
source-bound design-review successor rather than teaching code to emit false
expectations or weakening contract preservation. The Action accepts the existing
design-review schema through its parent/review inputs and revalidates unchanged
original request bytes before inference; reviewed children cannot reopen this
lane. This transports operator findings, not automatic semantic review or proof
that the successor fixed them.
See the [design feedback checkpoint](../../docs/flywheel-design-feedback-20261003.md).
For exact design-review successors, use `source_recipe_design_review.v2` with
explicit checkChanges and scenarioChanges arrays (empty means preserve all).
Every edit binds exact before/after records to an existing source-bound finding.
The authoring gate, final stage, approval and portable diagnostic reader reconsume
the original review; legacy v1 remains prose-only and cannot establish preservation.
Equal frozen records still do not prove correct verifier execution or Oracle truth.
