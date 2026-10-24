# Long-horizon exploration and reusable Skill learning

## Ownership and entry

Use this method to extend a real application case and accumulate reusable
knowledge while USING AgentLab. It composes the existing goal, codebase/program
analysis, seed, calibration, operations, asset-model and experiment-learning Skills
selected through [the registry](../../registry.json); it adds no runtime API,
permission, table, fixed scoring weights or automatic stopping mechanism.

The release `maintenance` role maintains evaluation knowledge. It is not the
role that changes AL's implementation. A platform repair addresses a demonstrated
blocking capability under its separate authority, then returns to the case.

## Accumulation destinations

- General recipes for understanding a project, building its maintainer Skill
  system, deriving seeds, exploring barriers, validating and revising conclusions:
  the owning method Skills in this release repository.
- Target-specific architecture, contracts, verification methods, difficulty
  hypotheses and task-generation guidance: instance Skills in knowledge TableGit
  `maintainer_skills`, bound to object/source/method/fact identities. The table
  name does not restrict the actor role. Preserve the project's code separately.
- Program facts, runnable cases/oracles and execution observations: the existing
  structured knowledge/operational tables and evidence assets. A Skill references
  them; it does not replace their typed content with narrative.
- Candidate lessons: existing `experiment_lessons`, `lesson_evidence` and
  `lesson_validations`; use explicit reviewed promotion before changing active
  knowledge. Release JSONL exports remain fixed-cut snapshots, not another live
  editable authority. Follow [experiment learning](../../agentlab-experiment-learning/SKILL.md).

Skills are the durable home for reusable judgment and actionable guidance, with
references/scripts where useful. Facts and hypotheses support that knowledge;
not every timeout or isolated failure becomes a permanent Skill rule.

## Evaluator owns the assessment; student artifacts are not grades

The student solves the task and may submit code, tests, measurements, logs or
an explanation if these are genuine task deliverables. The evaluation system
independently checks those artifacts against captured execution and the frozen
oracle, attributes assistance, and generates per-case and aggregate reports.
Never accept a student's self-assigned pass, score, help attribution or capability
claim as authoritative evaluation evidence. A teacher assisting execution must
not silently author a student's artifact and credit it to the student.

A measurement summary is a task artifact, not the evaluation report. Distinguish
raw measurements, the student's interpretation, independent recomputation and
the final judgment. A missing summary can fail an explicitly declared delivery
criterion while valid measured progress remains visible; it does not by itself
prove the underlying functionality or measurement ability failed. Do not require
a student to grade itself or narrate teacher help as a substitute for evaluator
instrumentation. Correct future task contracts prospectively; retain original
frozen outcomes and label any posthoc reinterpretation separately.

## Exploration assesses the student while constructing the case

Two uses of the same evidence must remain visible:

| Mode | Purpose and teacher role | Student assessment |
|---|---|---|
| Assisted case exploration | Discover barriers, help across A to expose B/C, retain checkpoint/Fork alternatives and refine a long-horizon task | Assess THIS student before and after help. Assistance dependence counts against independent performance under a separately versioned scoring policy; construction is not an exemption. |
| Frozen hosted evaluation | Give a participant the frozen task/start state and assistance/budget policy; let it plan, execute and verify | Record independent progress and any newly delivered help for THIS run. Prior students' help is construction provenance, not a penalty transferred to a new participant. |

Exploration simultaneously produces a student evaluation and a better case.
Crossing A with help never clears the original deficit or turns teacher work into
student work. Do not stop observing at the first failure: retain assisted passage
so later independent strengths and further help dependence remain measurable.
A teacher-only solution is construction evidence, not a student completion.

A/B/C are discovered difficulty mechanisms, not mandatory learner-visible stages.
The final task may be one complete objective with ordinary acceptance conditions;
let the student choose its plan. Keep internal checkpoints for restoration and
diagnosis without requiring staged release, teacher-led gates or exactly three
phases unless the actual task calls for them. Freeze each exploration attempt's
inputs and preserve versioned case refinements; do not rewrite earlier results.

## Diagnose strengths, weaknesses and causes from the trajectory

For each meaningful demand/barrier, connect the following in the EXISTING
execution, intervention, evidence and learning records (not a new database):

- Demand and conditions: required capability, task/source/start point, actual
  Agent/model/API/runtime, thinking policy, tools, environment and budgets.
- Observed student behavior: original operation/tool references, relevant actions,
  errors, detours, information gained and actual intermediate/final outputs. Link
  independent checks; distinguish no attempt, unknown observation and failed attempt.
- Help and dependence: exact delivered content/type, recipient and time, pre/post
  checkpoint, teacher actions including direct edits/device work, and observed cost
  (time/tokens where available, unknown otherwise). Include help during construction.
- Subsequent behavior: what the student then did independently, whether help
  enabled passage, remaining failure and the next barrier. Claimed success alone
  does not show that the intervention worked.
- Diagnosis: bounded strength/weakness observation, candidate mechanism,
  alternative causes/counterevidence, evidence references, confidence basis and
  the next observation that could discriminate explanations or test transfer.

Useful capability labels include repository understanding, planning/decomposition,
implementation, tool discovery/use, feedback-driven recovery, validation and
final delivery. They are diagnostic vocabulary, not mandatory fixed weights or
evidence that every dimension was measured. Separate task correctness, assisted
reach, tool success, useful progress, completion time and delivery reliability.
Avoid multiplying one shared delivery/lookup failure into many ability deficits.

Help is also a diagnostic probe. If a tool-location hint is followed by successful
student device actions, that supports a tool-discovery/access hypothesis, rather
than proving an inability to operate devices. Without a prior opportunity to act,
record actual help/dependence but leave unaided capability unmeasured. Multiple
simultaneous changes in time, environment, task scope or help confound causal
attribution. Harness/provider/Oracle faults stay distinct from student deficits;
absence of private reasoning is not evidence of a particular thought process.

Reports must present observed strengths, observed weaknesses, assistance
requirements and cause hypotheses WITH supporting/counterevidence and limits,
not just a pass rate. One run supports a context-bound observation; promote a
model-level capability boundary only after relevant repetitions, other barriers
or transfer evidence. Keep raw facts/help types immutable and score weights in a
separate versioned projection, so help can be penalized and rescored without
rewriting execution history. Preserving facts does not mean exempting help from
scoring. Do not invent universal penalty values or silently replace old grades.

## Extend one real path

1. Start with one target and a real task. Freeze source, knowledge and method
   cuts, actual participant/model/runtime, context, thinking policy and budgets.
   A requested policy is distinct from independently observed effective behavior.
2. Let the student act without unplanned semantic help. Capture tool inputs,
   outputs, original outcomes, relevant state and deliverables through the
   admitted Harness. Do not infer private reasoning from silence or elapsed time.
3. Diagnose an observed barrier before helping. Separate tool-call validity and
   execution status from business-check outcome, new task-relevant information
   and later use. A normal compiler diagnostic may be useful despite a failed
   build; a successful command may add no progress. Record unknown benefit as
   unknown. Equivalent retries with unchanged relevant inputs and no new evidence
   are candidates for repetition, not an automatic misconduct verdict.
4. Select waiting, a separately bounded budget probe, or minimal help using the
   observed trajectory. Freeze changed conditions so more time, a thinking change
   and a hint are not all credited as one causal explanation. Record pre/post
   state, exact delivered help/type/recipient, teacher actions and costs. Help
   crosses barrier A so the student can expose B and C; it does not erase A.
5. Retain formal checkpoint/Fork lineage for the meaningful states. Continue the
   same task until another useful barrier or the declared stopping condition.
   Do not rerun a failed task repeatedly just to make a report green. A fresh
   participant receives its declared public task/state, not private judge assets
   or another student's private context by accident.
6. Derive detailed and aggregate reports from the same facts. Keep independent,
   assisted, Host, Harness, environment and provider outcomes distinct. Missing
   artifact sections can share one delivery cause; do not count each missing
   field as an independent capability deficit. Retain time-to-delivery, budget
   termination and stalled/unknown progress alongside final correctness.
7. Close the round through existing experiment learning: observed phenomenon,
   candidate mechanism, tested scope, alternatives/counterevidence, minimal help
   and observable prediction for another context. Validate supported changes,
   promote explicitly and update the smallest owning Skill/script. Preserve
   superseded interpretations and source/method/knowledge lineage. A new task can
   test transfer naturally; do not build a parallel framework to accumulate notes.

## What counts as improvement

A longer attributed case, a new source-grounded barrier, corrected explanation,
reusable verification method or successful continuation by another Agent is an
observable gain. Skill count, prose volume, archival, mechanical schema checks
and candidate export alone are not evidence of better evaluation or transfer.
A supported boundary is limited to its tested context; a single budget timeout
is not a model-wide inability. Score policy may change without changing facts.
Learning benefit requires later admitted use and measured comparison; do not
infer it from writing a Skill. Future independent assessment must disclose its
start point and assistance history, separate from exploration-time passage.

## Prove execution before interpreting a timeout

Keep request preparation/preflight, request sent, runtime admission, participant
prompt acceptance, observed tool actions and publication as separate milestones.
A Ready workspace or a successful capability discovery is not proof that a new
participant started. Bind observations to the exact new request/operation/base;
never use the previous completed operation or its timeout as the new outcome.
Without admission or prompt-acceptance evidence, retain submission status and
help delivery as unknown; do not add a failed student run, count a delivered
hint or attribute the outer wait to model thinking. Read the original effect
through its declared boundary before a dependent continuation; do not replay it
or widen the task into an infrastructure campaign.

## Attribute passage after help

When an exact late original result proves prompt acceptance and publication,
append that result to the same case; preserve the earlier transport uncertainty
as a historical observation. Do not replay the request to obtain a cleaner run.
A report write followed by independent content checks can distinguish a delivery
barrier from incorrect analysis. Tool success or runtime completion alone cannot.
Record every changed condition, including clarified public contract fields,
alongside semantic/planning help. Assisted passage with those changes supports a
bounded observation, not the isolated causal benefit of one hint or independent
whole-task success. Keep old portable packages tied to their original checkpoints
until the new state is actually captured and restored.

## Report actions and outcomes before event volume

Present execution operations, unique tool calls, help and independently checked
delivery ahead of raw-event totals. Count native tool-call identities once;
streamed message fragments, tool progress and duplicate notifications are not
additional actions. Publish the covered-operation denominator; unextracted legacy
history, missing terminals and conflicting results stay unknown. A normal tool
return is not task progress, while a failed compile can provide useful evidence.
Use source-grounded findings and independent outcomes to describe benefit or
repetition; do not infer either from return status or synthesize a useful-call
score without the needed observations. Keep raw counts in completeness details.

## Preserve partial capability evidence when delivery fails

An empty final report does not erase authenticated tool actions and immutable
intermediate outputs. Compare those outputs independently and name their scope;
do not credit the controller's comparison as the student's reasoning or promote
the entire task to success. Treat absent report fields as one delivery barrier
when they share that cause. Before assigning a navigation failure to the model,
check whether the current project/source entry was clear among historical files.
For late-result recovery use live scoped capsule identity and original-operation
readback, not an old physical root or the previous lease's successful operation.

## Keep declared output and grader constraints aligned

Freeze field meanings and accepted representations from the same declared
contract used by the private checker. A human-readable report reference is not
an executable UI selector: do not silently import a bare-ID dispatch restriction
into a report field that did not declare it. If real output exposes that gap,
retain the original frozen verdict and publish a separately versioned, explicitly
posthoc semantic review. Never edit student bytes or rerun the model merely to
satisfy the hidden restriction; do not present posthoc acceptance as a frozen
pass. Readback settlement, input-integrity checks and assessment may be automated
only after exact original publication binding; settlement itself grants neither
a model retry nor Host/checker-effect authority. Keep native budget and controller
publication/readback time separate.


Use [`assess-declared-report.py`](../../../scripts/assess-declared-report.py)
for a report-content slice: a versioned `agentlab.report_contract.v1` JSON declares
criterion IDs, rule kinds, compared field names/types, report-reference IDs and
field constraints. Expected business values remain in a separate private oracle.
The same contract generates the public guide and drives the checker; do not
hand-maintain a second field guide. The adjacent
[regression examples](../../../scripts/test_declared_report.py) show the minimal
contract/oracle shape and rejection boundaries.

```sh
python3 scripts/assess-declared-report.py describe --contract contract.json --output output-guide.md
python3 scripts/assess-declared-report.py assess --contract contract.json --oracle oracle.private.json --report student.json --timing posthoc --output reassessment.json
```

Freeze the contract, generated guide, checker and private oracle digests BEFORE
an assessed run; publish only the guide/contract to the participant. `--timing
frozen` labels the requested mode, not proof of pre-run freezing: retain the
external freeze receipt. A later correction uses `posthoc`, binds the unchanged
student SHA and original frozen assessment separately, and explains every policy
change. A descriptive report ID is accepted only with exactly one declared token;
ambiguous/unknown tokens, duplicate observations and changed business values fail.
Evidence paths compare the full captured absolute path, not a matching basename.
These content checks do not authenticate evidence, execute selectors, grant
Host effects or establish independent whole-task success. Missing private oracle
inputs are evaluator errors, never student failures or inferred expected values.


## Audit numeric correctness, evidence fidelity and useful progress separately

A participant can compute the correct aggregate while corrupting a copied raw
record. Independently compare the selected original tool IDs, timestamps,
metric definitions, units and samples; recompute the aggregate; then compare
claimed verbatim content with the original bytes. Keep these separate findings.
A changed unused column still invalidates a verbatim claim without making an
unchanged aggregate numerically wrong. Preserve the original and student bytes;
never repair the submission and credit the correction to the participant.

Prefer exact captured blobs plus references/digests over manually reconstructing
raw output. Declare excerpts and any whitespace normalization. An accurate
excerpt is different from invented data; record a misleading verbatim label
without multiplying it into several numeric failures. Observation by mtime or
nominal UI input supports a narrower claim than unchanged source hashes or a
verified semantic interaction. Keep unsupported claims and missing evidence
visible at that narrower scope.

Use the same captured tool records to annotate task-relevant benefit separately
from reported tool status: an initial failed probe may discover a useful
constraint; repeating the same refuted filter may add no observable information.
Retain what changed, the counterexample available then and later use of the
result. A participant's self-correction is counterevidence to a blanket inability
claim, even if another defect survives. Counts of normal returns and checker
criteria are neither usefulness scores nor participant pass rates. Keep weights
separate and unknown causal benefit explicitly unknown.

For offline retention, freeze the chosen tool-record oracle and evaluator code
outside the restored participant workspace. Bind their digests to the exact
original operation/checkpoint and preserve the declared semantic outcome across
hosts, including its failures. Exclude nondeterministic annotation timestamps
only through an explicit comparison projection. An excerpt's hash identifies
that excerpt; independently retained original-fact provenance establishes its
source. Omitted Agent context means a post-state grading replay, not automatic
qualification to resume a prompt that depends on that private context. Stop once
the selected code/evidence and independent outcome reproduce; return to the
application's next meaningful barrier.

## Reproduce retained outcomes before expanding the case

Use the existing patch/case restore path and an externally retained case digest.
Declare the selected source slice separately from inherited baseline files; a
synthetic offline baseline file is not necessarily a published Session artifact.
When constructing a new patch from a shared Git bundle, explicitly select the
registered immutable base commit in a fresh disposable working source. A successful
clone may have no checked-out HEAD; never infer its branch from the source name.
Read back partial generations before correcting a rejected capture.

Consume the case's confined logical mappings instead of hardcoding historical
artifact directories. Keep controller-private oracles out of the restored student
workspace. Test both exact file/tree identity and the actual evaluator outcome on
another host; preserve failures and help attribution across points. Keep original
frozen grades and corrected posthoc grades separate even when both reproduce.
Report archive bytes AND shared baseline/patch bytes, omitted caches/SDK/context,
and the selected-code scope. Small compressed evidence is not full-machine restore
or proof that future branches have constant cost. Stop portability repair once
this case's declared scope restores; return to evaluation and difficulty discovery.


## Bind editable UI actions to actual state

Evaluate the chain independently: intended test value -> observed editable-field
value -> actual submitted action -> observed application result. A text-input
command may append instead of replace. A soft keyboard or modal can move the
viewport and hide controls, so a previously valid coordinate is not a durable
selector. Refresh the actual hierarchy/bounds after state changes and verify the
field contains the intended value before interpreting a business result. Failed
input setup does not establish a parser defect; a successful positive case does
not establish the unexecuted negative cases.

Read the actual representation of interface metadata. Bounds encoded as a string
are not nested numeric arrays. Keep repeated assumptions, their diagnostics and
any eventual schema correction visible in the same trajectory. A shell pipeline
or wrapper may report zero while its output contains an exception or rejected
device command. Tool status, domain outcome, information gained and later use
remain separate; do not derive a useful-call rate from exit codes alone.

Freeze input-method readiness and allowed system-dialog interactions as part of
the environment contract before an app-only assessment. A first-use keyboard
consent/setup screen is a distinct operator decision, not authority implied by
asking the student to type. Missing preflight is a Harness finding; student
interaction outside the frozen scope is still recorded separately. Never grant
consent, infer OS permissions or alter another environment merely to clear this
gate. Record precisely what changed and leave unobserved permission effects
unknown. Do not retroactively expand the allowed scope or erase the original run.

Preserve intermediate code, compiler output, artifact identity and verified UI
states when final task files are empty. Treat the missing final delivery as one
barrier, while distinguishing successful implementation/build/deployment from
unexecuted business checks. Time to first edit is observable preparation, not by
itself proof of wasted thinking. Freeze a narrowly attributable continuation only
after the original operation is resolved; help can cross a barrier to expose the
next one without replacing the earlier outcome.
