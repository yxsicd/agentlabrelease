---
name: agentlab-benchmark-calibration
description: Independently calibrate task seeds and maintain grading quality before operational evaluation.
metadata:
  agentlab-layer: method
  agentlab-role: maintenance
  agentlab-stage: calibration
---

# Benchmark calibration maintenance

Validate the benchmark independently from the assessed Agent. Check source/environment reproducibility, baseline behavior, a reference implementation, meaningful wrong implementations and regressions across turns. Successful compilation alone is not functional correctness.

For stateful UI negative controls, retain per-test failure locations and distinguish
the intended semantic failure from later failures caused by residual UI state.
A passing reference does not prove cleanup after an early assertion failure.
Do not count cascaded failures as independent Oracle coverage. Preserve the frozen
checks during calibration, restore the reference and verify recovery; any cleanup
repair creates a successor test cut requiring fresh positive and negative controls.

The generic frozen-behavior consumer requires a wrong control's observed failed
check set to equal its declared set before scheduling an Agent attempt. Additional
failures route to `review-unexpected-control-failures`; retain them without
assuming whether their cause is cleanup, another defect or an incomplete design.
Do not expand expectations after observing a failure merely to pass this gate.
A genuinely intended multi-failure control needs an explicit frozen declaration.

Use the [native control producer](../../docs/flywheel-native-behavior-calibration-20261003.md)
to execute reviewed source variants through the existing behavior-executor
protocol before bounded repair. Reuse one executor for calibration and attempts;
require fresh accepted-reference recovery under unchanged predicates, without
counting that rerun as another distinct valid implementation. Preserve the
original control declarations when a real run exposes additional failures and
review attribution before issuing a successor contract. A successful host seam
does not restore or qualify a Git workspace, UI state or emulator runtime.

When additional failures appear, first compare earlier declared contracts and
their exact control-source bytes. A translation may have lost failure IDs; do
not infer contamination or rebuild expectations from the latest verdict alone.
Use the native declaration reconciliation/validation path linked above when the
prior recorded source-operation format is supported. Preserve old profiles and
require a reviewed, parent-bound successor with unchanged checks, inputs, task,
source edits and budgets. Recorded-content reconstruction does not prove input
interpretation, intent, ancestry or producer identity. Normal preparation must
validate and pin the reference/parent, not merely trust a reconciliation label.

Inspect the installed framework's failure-path hook order, not just hook names.
The retained Hypium 1.0.19 async runner calls afterEach in the same try block as
the test body; a thrown assertion can skip it. For independent UI test scenarios,
establish and verify clean state before the next test as well as after success.
Use an explicit close action for a non-autoCancel overlay instead of assuming
Back closes it. Preserve all behavioral predicates and compare the same mutation
before/after the cleanup successor, followed by a byte-restored positive control.
Do not reset between phases of one stateful long-horizon scenario or generalize
this hook behavior to an uninspected framework version. Keep skipped-hook and
cleanup failures separate from independent product failures.
See [the controlled UI isolation sequence](../../docs/flywheel-ui-isolation-calibration-20261003.md)
for the preserved failed attempt, same-mutation comparison and recovery boundary.

An evidence file's existence and matching digest do not qualify its contents.
Construction-readiness uses recorded `agentlab.shadow_case_qualification.v1`
receipts: bind candidate ID/digest, source revision, source-set and knowledge-cut
digests, qualification kind and runtime requirement ID where applicable. Require
completed successful runner execution, positive duration and named passing
checks. Calibration additionally retains a passing accepted implementation and
distinct declared wrong variants that completed and failed an intended behavior
check. Reconcile observed wrong-variant IDs with declared counts; infrastructure
errors, empty JSON, duplicate variants and borrowed receipts cannot satisfy this
gate. This is recorded-content checking, not producer authentication, execution
replay, full runtime acceptance or a frozen case. Preserve that boundary in the
readiness result and retain the separate construction/calibration/freeze gates.

Distinguish absent execution from evidence that has not been admitted by a
consumer adapter. Before scheduling fresh calibration, inspect retained partial
receipts and reconcile their exact source, plan and environment cuts. A prior
positive control or killed mutation remains scoped evidence even when a newer
readiness plan still reports unqualified. Report missing normal-exit controls,
unsupported receipt formats and incompatible runtime identities separately.
Build-target API, installed SDK API and observed runtime-image API are different
axes; none substitutes for an explicitly required exact runtime version. A
host's device permissions, cold boot and HDC connection qualify environment
availability only, not application behavior or complete case calibration.

An operation ID is a transient execution handle, not a durable evidence archive.
If historical operation lookup is unavailable, recover retained raw files through
the exact target peer, compare their original byte lengths/digests, and reconstruct
the observations before scheduling repeated work. For UI captures, select the
declared application/page owner and unique observable nodes inside it; an unrelated
window's matching text cannot satisfy the Oracle. Keep unsupported formats and
unrecovered build/patch/command captures as explicit gaps. Raw readback does not
authenticate the historical producer or qualify a new runtime execution. See
[the retained-evidence audit](../../docs/flywheel-retained-calibration-readback-20261003.md).

Use `--feedback-partial-calibration` to reconstruct reviewed retained observations
before planning scoped follow-up. Its profile declares source/candidate/plan
bindings, runtime observations, JSON-pointer, attribute-tree or named Hypium-test selectors, shared
checks, accepted/wrong control expectations and missing controls. The consumer
checks exact peer-directed file envelopes and raw bytes; a missing/ambiguous
observable is a readback failure, not a killed wrong implementation. It preserves
formal gate actions separately and never infers build, mutation or runtime
attestation from observed values. Consume `scopedActions` only within their declared
runtime; equal owned evidence suppresses duplicate scoped work, not unrelated
formal qualification. See [the partial consumer](../../docs/flywheel-partial-calibration-consumer-20261003.md).

For retained Instrument Test command logs, select `hypium-native-test` by class
and test name rather than reading aggregate pass counts as behavior coverage.
The supported lane reconstructs matching start/completion records and reconciles
the native summary/final code; incomplete, error or ambiguous reports stop
readback. Keep cascaded test failures explicit in reviewed control expectations
and missing-isolation work. Source/build identities still require independent
admission: named recorded outcomes cannot bind new host/test facts by themselves.

Use the task's actual expected baseline: a bug-fix case may fail before the patch; an extension case may pass old tests but fail new demand checks. Reference passes and targeted wrong-boundary/lost-history variants should fail the intended checks. Save complete output and exact identities in `evaluation_cases` calibration rows, with analysis evidence in `program_facts`.

For repository-independent diagnostic repair, use the
[bounded behavior controller](../../docs/flywheel-behavior-loop-20261002.md).
Freeze checks and calibration first; adapters execute submitted source while
Rust independently compares actual values with those frozen expectations.
Deliver failure feedback to a new bounded attempt without replacing earlier
checks, and stop on infrastructure failure, unchanged failed source or budget.
Distinct calibration controls do not require an Agent to avoid a legitimate
accepted source. Deterministic adapter regressions prove controller mechanics,
not model learning, authenticated Agent completion or platform qualification.
Keep reviewed command adapters separate from security isolation and trusted
Gateway capture; generic scheduling alone does not provide either boundary.
For generated source, use an explicitly contained executor and keep evaluator
references outside participant mounts. The
[contained Action recipe](../../docs/flywheel-contained-behavior-20261002.md)
uses exact source/Blob and compiler/image identities, preserving frozen checks
before execution. Pin preparation method bytes before lengthy acquisition and
reject mid-round changes; hashing the final file alone can misidentify the code
that actually ran. Preserve acquisition failures separately from subject verdicts.
Create fresh attempt-owned receipt directories before invoking a runtime that
strictly resolves them; exercise that setup in adapter regressions, not only the
non-isolated path. A pre-launch missing directory is a Harness failure, not an
Agent result.
Archive the non-secret runtime configuration and manifests whose digests bind
container receipts, then run the independent runtime consumer against actual
inspect/probe records before accepting the run. A launcher report alone is not
independent validation; portable artifact readback and live-path validation are
separate capabilities.
When a completed participant submits syntactically invalid source, retain exact
source-bound compiler diagnostics as rejected task observations and route them
through the existing bounded repair feedback. Do not classify every nonzero
worker exit as Agent failure: compiler configuration, unbound diagnostics,
unsupported imports/loaders and container failures remain infrastructure errors.
Validate frozen inputs before emitting a source rejection and retain all check
IDs; a rejection cannot bypass calibration or make any behavior check pass.
For repository transfer, retain the shared controller and grading protocol,
change reviewed profile data and select an explicit framework adapter. Freeze
state-transition checks including create, release, recreate and failure retry;
test boundary identifiers from the task demand and preserve unrelated callbacks.
Different valid strategies may satisfy the same observable contract. Calibrating
a second adapter is not yet a real participant transfer or knowledge benefit.
After real transfer, report which controller/capture components were reused and
which reviewed semantic adapter remained operator-supplied. Passing tasks on two
adapters does not establish automatic adapter discovery or Skills improvement.
Measure knowledge treatment with equal task checks, model/policy and budgets;
do not count separate first-attempt successes as failure-feedback learning.
The behavior controller can consume an explicitly selected fixed-cut guidance
packet through its existing knowledge binder. Require exact task-source/stage
applicability, immutable knowledge/selection bytes and captured completion bound
to each attempt request. Keep evaluator references outside participant mounts.
Use equal-budget unguided/guided arms, preserve contradictory outcomes and admit
new lessons to a later cut only; verified transmission alone is not benefit.

An explicit frozen task demand can define new behavior even when the repository's
original intent is unknown. Bind that demand before calibration and distinguish
task-baseline failure from a claim of a defect in the upstream project. Require
structurally different valid controls as well as meaningful wrong controls, all
under unchanged predicates. Keep behavior with no established task expectation
as unscored characterization; do not silently add it to the Oracle after seeing
the baseline. Partial host-seam calibration leaves the full task's runtime and
uncovered observables unqualified until the Agent execution/feedback loop proves
them separately.

Before spending runtime budget on a reused test, inspect its pinned source body,
assertions and failure branches. A test name, `done()` callback or normal exit
does not establish the expected behavior. Independently inject success and
failure at the declared seam and check whether the same test discriminates.
Use `scripts/probe-hypium-failure-controls.cjs` for the explicitly supported
single-call TestKit startup seam on trusted sources; pin the Git Blob and any
TypeScript erasure compiler. This diagnostic is not a security sandbox, ArkTS
type check, device test or qualification receipt. Preserve partial adapter
failures separately; never count unsupported imports or timeouts as rejected
implementations. A sensitive seam still requires runtime calibration against an
accepted implementation and meaningful wrong variants. A vacuous reused test
does not invalidate a separate, untested behavior Oracle hypothesis.

Use the bounded Rust downstream bridge when turning this diagnostic into the next
maintenance action. `agentlab-maintainer-skill-flywheel` supports
`--prepare-downstream-probe`, `--execute-downstream-probe` and
`--feedback-downstream-probe`; see
[the execution recipe](../../docs/flywheel-downstream-execution-20261001.md).
The supported adapter is an explicitly selected trusted Hypium startup seam,
not a repository-specific hardcoded task or arbitrary Agent-generated command.
Bind the reviewed recipe to the candidate/plan, exact test Git Blob, Node and
optional type-erasure compiler. Capture outside a clean revision-pinned source
worktree using the existing process-group/deadline/log-budget primitive. Keep
spawn failures, timeouts and unsupported adapters separate from a vacuous Oracle.
Reconstruct feedback from all byte-bound raw inputs/results/logs without a new
execution. A repeated identical feedback plan stops scheduling. Sensitive controls
only select continued calibration; they never qualify meaningful wrong variants,
emulator execution or a frozen case. The read-only main-only downstream Action
can execute this same bridge without a provider Secret or TableGit writes.

For a staged Oracle repair, use `--compare-oracle-repair` with exact before/after
execution roots and SHA256s plus the clean successor source worktree. Preserve
the parent failure; give the staged successor an `oracleRepairParent` binding
the parent candidate ID/value digest and original execution digest. The comparison
reconstructs both captures, preserves candidate demands, test selector, compiler,
launcher and deadline, and checks one additive source commit changed only the
selected test path. It rejects implementation changes and changed controls.
Only an accepted success control and rejected failure control select continued
runtime calibration. A still-vacuous or infrastructure-failed repair remains
unvalidated. This is not semantic proof of an entire test-file edit, wrong-variant
calibration or authority admission: derived source/knowledge identities must be
admitted separately before freezing a benchmark. Never publish staging rows as
active TableGit snapshots. See [the repair evidence](../../docs/flywheel-oracle-repair-20261001.md).

Keep diagnostic findings bound to the original candidate digest and knowledge
cut; feed gaps into a new construction round rather than rewriting history.
If the Oracle source is missing from admitted fact evidence, first replenish
that evidence. Keep generic lessons here and concrete candidate findings in
instance records. Separate harmless refactors from semantic defects: a renamed
class with the same default export is not automatically a wrong implementation.

Calibrate the actual demanded behavior, not merely a prerequisite such as startup.
For the explicitly supported trusted AbilityStage/ApplicationContext seam, use
`scripts/calibrate-harmony-stage-controls.cjs` with a reviewed, byte-pinned
contract. Paths, log predicates, input configurations and exact-match semantic
mutations belong to that instance contract, not the runner. Execute the selected
module's real type-erased default-export body; keep independent baseline and
negative controls on the same checks. Change language and colorMode separately.
Retain original and transformed sources and failed intended check IDs. Cosmetic
variants surviving the oracle invalidate that calibration; missing/ambiguous
mutations, unsupported loaders and worker deadlines are infrastructure failures.
This operator dispatch seam does not qualify actual framework delivery, ArkTS,
HAP, API-specific emulator execution or the whole candidate. The main-only
diagnostic Action binds the contract to the selected candidate value and source;
its semantic controls stay separate from the original startup feedback and from
formal construction-plan qualification. See [the lifecycle evidence](../../docs/flywheel-lifecycle-calibration-20261001.md).

For an unreviewed generated verifier, diagnose the unchanged accepted baseline
inside a contained executor before spending budget on its wrong controls. Bind
the original verifier, frozen runtime and retained source inventory; distinguish
recorded source reconstruction from restoring the original runner. An unbound
import before observation output is a verifier-adapter execution failure, not
a rejected implementation or a failed behavior check. Retain the failure for
Agent-owned repair without editing the draft, expanding failed-check declarations
or resetting an exhausted review budget. A compatible compiler digest with a
different Node/architecture remains a new diagnostic environment, not historical
runtime equivalence. Use the Rust `--prepare-source-recipe-diagnostic` and
`--feedback-source-recipe-diagnostic` bridge with the existing contained launcher;
normal exit still requires independent frozen-check comparison. The constructor
Action invokes this diagnostic after staging a design-first proposal and retains
failures. Its default `code_revisions=0` stops there. A fresh design-first root may
explicitly freeze `code_revisions=1` or `2` before the first model turn to feed
diagnostics into unreviewed code-only repairs. Rust reconstructs original captures,
binds the complete design bytes, checks/controls/source paths and inherited budget,
and rejects unchanged code, timeouts, log growth, uncertain cleanup and chain reset.
Each repair uses a fresh contained participant with the same model policy and
independent isolation validation; the frozen design is not regenerated. Review
children and older roots without pre-generation budget receipts cannot enter this
automatic path. Raw diagnostics are data, not trusted instructions or behavior
verdicts. Baseline success alone leaves independent references, wrong controls,
semantic review, knowledge admission and useful next-round consumption unproved.
When a generated verifier fails before any observations, compare its runtime
constructor and dependency arguments with the exact supplied adapter API before
changing task expectations. A real author passed null despite receiving an
explicit pinned compiler and compiler-binding prompt. More prose is not evidence
of compliance. Route the captured interface failure through a parent-bound review
revision with unchanged checks/scenarios; the Agent owns the successor code.
Do not silently inject a missing compiler, execute repaired source on the host,
or treat the generated verifier's startup error as an upstream product defect.
A real reviewed child repaired the compiler binding while preserving all original
checks/scenarios/controls, then failed at an absent decorator global. Inspect the
whole supplied runtime interface, including dependency imports and declared
globals, rather than assuming the first fixed error completes the environment.
Do not remove decorators from submitted source to hide unsupported platform
behavior; any controlled seam needs an explicit scope limitation and calibration.
See [the original-verifier execution checkpoint](../../docs/flywheel-design-feedback-20261003.md#unchanged-original-verifier-execution)
and its native diagnostic continuation for commands and supported boundaries.

To avoid refetching an entire repository for retained-source diagnostics, the same
runner accepts --source-binding FILE and --source-workspace DIR instead of
--source-repo. Verify every retained inventory row's revision, relative paths,
byte count, SHA256 and Git Blob OID before any worker; reject symlinks, duplicate
paths and ambiguous repositories. Blob-byte verification does not authenticate
commit ancestry: the receipt explicitly keeps revisionAuthenticated=false.
Use --diagnostic-unreviewed only for operator-selected trusted author drafts with
reviewed=false, without changing the original contract bytes. Such receipts are
diagnosticOnly and the Rust reviewed-stage consumer rejects them, even if their
controls pass. Baseline failures are evidence for Agent-owned repair, not permission
to change predicates as the operator or admit a case.

Consume `agentlab.harmony_stage_control_calibration.v2` with the Rust
`--feedback-stage-calibration` CLI before routing follow-up work. Supply the exact
candidate, downstream plan, contract, raw receipt digest and optional prior feedback.
Reconstruct named checks from creation/configuration/destruction log ranges and
registrations; verify the raw worker stdout and pinned original/mutated sources.
Do not trust a producer's boolean, normal exit or self-updated digest alone.
Partial infrastructure failures select environment repair; surviving controls
select Oracle/control repair. Complete successful semantic controls select scoped
review/admission, leaving every formal downstream requirement unchanged. Same owned
evidence stops repeat scheduling. Historical v1 receipts lack these phase/capture
fields and are not silently upgraded. Keep them as earlier scoped evidence, not a
v2 readback. A successful collection Action is not a successful case qualification.

For cross-Action continuation, use `scripts/resume-maintainer-stage-feedback.sh`
with the current capture and downstream plan. It searches at most ten successful
main dispatches of the same repository/workflow, requires the same contract bytes,
and uses `--previous-stage-calibration` plus its digest to reconstruct the prior
capture before accepting `--previous-feedback-plan`. A plan hash alone is not
evidence for suppression. Preserve the selected predecessor's capture, contract
and plan without recursively copying history. Transport failures are collection
failures, not proof of no history. Incompatible or unavailable artifacts remain
explicit observations; no compatible predecessor schedules fresh feedback.
Only unchanged owned semantic work suppresses scheduling: formal requirements
come from the current downstream plan. This is not execution caching, authority
admission, automatic repair or completion of the full flywheel.
Include the recorded Node runtime identity in the owned semantic-work digest;
equal checks under a different declared runtime must replan. Require that identity
in reconstructed prior plans. Older feedback omitting it stays preserved but is
incompatible with this consumer; collect fresh feedback rather than rewriting it.
Runtime version strings are observations, not binary attestation or a complete
environment lock. Raw timing changes alone do not reset owned semantic work.

Define metric denominators and event sources: task success, build success, user rounds versus model/tool turns, monotonic execution time, and evidence-backed behavior scoring. Keep proposed process metrics explicitly unvalidated until agreement and repeatability are measured. Separate Harness malfunction from valid Agent inability.

Use [the knowledge experiment](../../examples/knowledge-seed/README.md) as the runnable fixture calibration/SQL/history/import demo; [SWE](../../examples/swe-bench/README.md) and [Harmony](../../examples/harmony-build/README.md) provide existing campaign examples. Record each demo's actual coverage.

Publish calibrated seeds from a fixed TableGit cut, one deterministically ordered JSONL per table. Do not alter active assessment inputs after seeing a subject outcome. Operational results become feedback for a new maintenance cut.

For shared predicates, specify expected input labels independently of the
reference implementation and test a stale consumer variant. Verify real source
call sites, while recording whether whole consumer bodies actually execute.
An isolated seam test can expose inconsistent routing but does not qualify the
platform URL parser, UI lifecycle or build. Keep these boundaries in the target
calibration/evaluation Skills; the image URL oracle is a concrete example.

Produce target-instance guidance for this stage as TableGit Skill rows,
separate from the structured facts/tasks/results. Follow
[the two-layer methodology](../agentlab-skill-methodology/SKILL.md) for
method/source lineage and independent layer/role fields.

For asynchronous submission, independently control deferred resolution/rejection;
check duplicate requests while pending, retained state on failure, observable
failure, release/retry and success reset. Observe rejected chains without turning
an unhandled rejection into an apparent pass. Preserve exact operator seams.
For singleton or module-owned pending state, reload the real source module
between scenarios, not between concurrent calls or retry phases of one scenario.
Otherwise fresh instances can hide stale cached work or invalidate deduplication
checks. Observe held permission and downstream completion separately; a call
count or normal process exit alone cannot establish awaiting and rejection
containment. Retain raw rejected-chain observations without repairing source in
the observer. New task demands require fresh calibration even when original
maintenance controls were verified; use the shared frozen-check consumer and
keep platform, cohort, freeze and assessed-Agent gates separate.
When promoting a trusted calibration adapter to assessed-source execution, do
not mount its all-control manifest or frozen expected answers. Reuse the
contained launcher with a request containing only submitted source and check
IDs/inputs; retain references and independent comparison outside that container.
Validate every input before executing source or returning syntax rejection.
Identical control verdicts across this boundary qualify adapter compatibility,
not complete Oracle coverage or a new Agent outcome.
Do not assert demanded payload correctness inside a host seam by throwing into
submitted code: its catch handler can hide the violation and the observer changes
the behavior being measured. Record bounded payload values for independent checks.
Grade failure visibility separately from rejection containment, with a clean
success control; silent catch-and-resolve can satisfy containment alone. Hold
each demanded asynchronous stage independently before claiming single-flight
coverage. Freeze additive predicates in a successor cut and preserve old results.
For navigation outcome extensions, validate stack and animation behavior as well
as success/failure returns. A wrong push-for-replace variant can pass return tests
while corrupting the stack. Source-verifying a caller is not implementing or
executing its outcome mapping; leave that turn explicitly unqualified.

Typed controller integration uses the Rust materializer and harmony-controllers
Action documented in the knowledge example. Preserve original-source patches and
SDK targets, probe the full project, then use an explicitly derived slice when
the environment cannot yet build its dependencies. Real compiler receipts/HAP
checks, invalid-type rejection and repair qualify the slice only. Keep dependency
seed gaps and replaced host/backend/UI behavior in structured records and instance
Skills; a passing derived build never overwrites the full-project failure.

### Actual staged navigation assessment

Use [the subject experiment](../../examples/knowledge-seed/subject/README.md).
Calibrate actual submitted methods/caller bodies without applying reference
transforms to subject code. Freeze the operational contract in TableGit before
assessment; use an explicit named outcome field if required by the independent
oracle. Preserve baseline/reference/wrong-stack outputs. Keep reference/oracle
and trusted gateway capture outside the participant filesystem mounts. Pi native
events are adapter observations, distinct from supervisor-owned gateway bytes
and source cuts. Separate valid Agent inability from Harness launch/build faults.
An exact selected-source cut and fresh-Agent branch comparison is source-only
lineage; it does not qualify formal SessionFS binary restore or device rendering.
Maintain generic method lessons and derived case instance Skills independently.

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

### Feedback multi-round instance

Use [the shared subject runner](../../examples/knowledge-seed/subject/README.md)
with the frozen feedback case. Distinguish stage-one failure/retry state from
stage-two duplicate suppression. Verify actual reactive field declarations with
Rust ArkTS property facts; fixture initialization is not proof of submitted
initializers or decorators. Execute submitted methods without reference repair.
Preserve negative calibration for wrong reset, duplicate requests and wrong
initial state, plus raw/normalized source evidence. The demonstration backend is
an explicit Promise seam; full phone compilation and UI rendering are distinct.
Return stage-specific construction/evaluation guidance to instance Skill rows.

### Independent clicks and image-resource dispatch

Use `subject/calibrate-utilities.cjs` locally or the `utility-calibration` job in
`knowledge-seed.yml`. Rust AST spans select actual ComponentBaseView click
methods and actual ImageUtil.getImgResource; TypeScript erases types without
repairing submitted bodies. The Date seam supports both constructor time and
Date.now. Test first call at zero, independent closures, default/exact wait,
suppressed-click window extension and real event payload forwarding. The existing
function is named debounce but the task explicitly requires a leading accepted-
click window; do not silently infer trailing debounce behavior from its name.

For image URLs, independently label fixtures and execute the shared predicate
plus resource dispatch. Network query/fragment strings must remain unchanged.
The Node URL model represents only the @kit.ArkTS parser seam. ImageComponent and
ImagePreview call-site checks do not execute their platform/UI bodies. Preserve
baseline/reference/wrong-protocol/wrong-dispatch and stage-specific checks.

Derive operational tasks with `subject/seed.py --scenario debounce` or
`--scenario image-url`: archive TableGit dependency queries, maintain corresponding
instance Skill rows, freeze demands/oracle digests, and export a new immutable
knowledge cut. Full phone builds and live Agent results qualify separate runtime
instances. Never label utility evidence with the calibrated loading-timer lesson;
scenario-specific lesson extraction must use the observed contract.


The real utility subject runner invokes the same `calibrate-utilities.cjs` recipe
as local/CI calibration, selecting its scenario. Keep mutation definitions and
source selection in that single implementation. Missing files/parser/runtime
errors are Harness calibration failures, never successful negative verdicts.
Preserve partial calibration receipts before propagating a failed recipe.

### Streaming and publication qualification

HTTP 200 and transport EOF do not qualify completed inference. The trusted
capture records semanticComplete and streamError independently from native
Agent stop events. Accept a non-null finish_reason or [DONE]; preserve truncated
reasoning and classify missing terminal frames as Harness/provider interruption.
Do not infer Agent inability from these exchanges.
For repeated deadline-before-mutation results, preserve interrupted captures and
compare an explicit participant/provider policy in a new cohort under unchanged
task checks and budgets. Bind the selected policy to actual Gateway requests;
an operator override or one later success alone does not prove upstream policy
application, causal improvement or knowledge-guidance benefit.

Reserve the evidence tag at the exact workflow source SHA before a long capture
so advancing main cannot invalidate late Release publication. Always retain full
HAP files as an independent Action artifact, including when Release publication
fails. Build report hashes without retained binaries do not qualify binary restore.
Calibration variants and individual checks are typed queryable rows, linked to
full raw receipts by identity and digest; avoid repeated full AST payloads.
