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

Use the task's actual expected baseline: a bug-fix case may fail before the patch; an extension case may pass old tests but fail new demand checks. Reference passes and targeted wrong-boundary/lost-history variants should fail the intended checks. Save complete output and exact identities in `evaluation_cases` calibration rows, with analysis evidence in `program_facts`.

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

Reserve the evidence tag at the exact workflow source SHA before a long capture
so advancing main cannot invalidate late Release publication. Always retain full
HAP files as an independent Action artifact, including when Release publication
fails. Build report hashes without retained binaries do not qualify binary restore.
Calibration variants and individual checks are typed queryable rows, linked to
full raw receipts by identity and digest; avoid repeated full AST payloads.
