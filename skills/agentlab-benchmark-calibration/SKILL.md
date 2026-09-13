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

Use the task's actual expected baseline: a bug-fix case may fail before the patch; an extension case may pass old tests but fail new demand checks. Reference passes and targeted wrong-boundary/lost-history variants should fail the intended checks. Save complete output and exact identities in `evaluation_cases` calibration rows, with analysis evidence in `program_facts`.

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
