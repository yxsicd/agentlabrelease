# Scoped partial calibration consumer

The Rust `maintainer_partial_calibration` consumer reconstructs retained JSON
observations using reviewed profile data. Repository names, application identity,
check names, expectations and missing controls are not built into the consumer.
Its explicitly supported extraction adapters are JSON Pointer, attribute
trees with a unique owner/node, and named Hypium native tests. Unsupported formats are errors,
not silent qualification or evidence of an Agent failure.

This capability closes the operator-only readback step from
[the retained audit](flywheel-retained-calibration-readback-20261003.md). It does
not close formal calibration: control roles remain reviewed declarations, not
verified implementation mutations. Runtime identity is recorded profile data,
not attestation of the image that produced a capture. File envelopes are checked
for exact peer/direct route and bytes, not cryptographically authenticated.

## Use

```sh
target/debug/agentlab-maintainer-skill-flywheel \
  --feedback-partial-calibration \
  --readiness CURRENT_READINESS.json \
  --partial-profile REVIEWED_PROFILE.json \
  --capture-root RETAINED_CAPTURE_ROOT \
  --output FRESH_SCOPED_PLAN.json
```

The optional `--previous-feedback-plan` suppresses repeated work only after
reconstructing the current captures and matching owned work. Input envelopes
and profile bytes remain digest-bound in the output. Transport timings, wrapper
formatting and unrelated knowledge-cut advancement do not cause new owned work.
Changed runtime, selectors, expectations, consumer method bytes, source/plan or
formal gate state do replan. A changed profile is never assumed compatible based
on its name. A corrupt prior owned-work digest or contradictory actions fail.

The downstream batch wrapper accepts `AGENTLAB_PARTIAL_CALIBRATION_ROOT`.
Place a profile at `profiles/<candidateId>.json` under that root; profile capture
paths are relative to the same root. The wrapper independently assesses the
construction plan and writes its ordinary `next-actions.json`, then emits
`scoped-next-actions.json` only for a supplied profile. Passing the previous
output directory reuses both scheduling guards. Default behavior is unchanged.
`partial-summary.json` exposes the scoped active cohort separately and excludes
superseded historical candidates. It is not the formal qualification summary.
Fresh-runner history recovery and automatic execution of scoped actions are not
provided by this optional local lane.

## Profile contract

`agentlab.partial_calibration_profile.v1` is a closed typed Rust input:

- `reviewed:true`, `candidateId`, `candidateSha256`, `sourceRevision` and
  `constructionPlanSha256` bind the independently assessed readiness.
- `targetPeerId` and nonempty `runtimeIdentity` declare the captured observation
  environment. They cannot satisfy an exact formal runtime requirement.
- `phases` declare unique IDs and checks. Each check has `id`, `selector` and
  `expected`; the full check ID is `<phase>/<id>`.
- A `json-pointer` selector contains `pointer`; missing pointers fail even when
  the expected value is null. An `attribute-tree` selector contains nonempty
  scalar `owner`/`node` attribute maps and a `field`. The raw tree uses
  `attributes` and `children`. Selection never searches an unrelated owner.
- A `hypium-native-test` selector contains `class` and `test`, selecting an
  exact named result (`passed` or `failed`) from an original Instrument Test
  command-log JSON with `stdout`, `stderr`, `exitCode` and `timedOut`. The lane
  supports status 1/start, 0/pass and -2/assertion failure, one native summary
  and one final code. Matching start/completion, unique names/ordinals and
  consistent nonempty final counts are required. Process errors, incomplete
  reports, error/ignored tests and unsupported aggregate-report markers fail
  extraction, never count as killed implementations. No owner attributes are
  accepted. This is recorded native test status, not independent UI measurement.
- `controls` declare unique IDs, `role:accepted|wrong`, explicit
  `expectedFailedCheckIds`, and one observation for every phase. An accepted
  control expects no failures; a wrong control expects named failing checks.
  Optional `ownerAttributes` adds each isolated control's owner identity without
  changing shared selectors. Conflicting owner fields fail; the pointer adapter
  does not accept unused owner attributes.
- Every observation supplies `phase`, relative `path`, `envelopeSha256`,
  `rawSha256` and `byteLength`. Its exact retained envelope must report a
  successful peer-directed read with UTF-8 `result.content` and matching size.
- `remainingControls` contains reviewed IDs/descriptions for missing scoped work.
  Missing accepted or required wrong controls also produce explicit follow-up;
  one retained positive control is useful evidence, not complete calibration.

The consumer bounds profiles/capture envelopes to 2 MiB, total raw bytes to
32 MiB, phases/controls to 16, checks per phase to 64, and remaining controls to
32. It rejects traversal, symlink roots or in-root path components, nonregular
files, duplicate phases/checks/control captures, mismatching digests/lengths,
failed/wrong-peer reads and ambiguous observables before producing output.

Consistent observations produce `complete-scoped-calibration-control`, missing
positive/wrong controls, or scoped admission review. Contradictory observed
behavior produces `repair-scoped-observation-calibration`. Current knowledge
blockers take priority over both. All actions keep `executionAuthorized:false`.
The unchanged `formalGateActions` remains the separate construction route; this
consumer never marks a gate PASS, freezes a case or dispatches an assessed Agent.

## Verification boundary

Rust regressions cover both adapters, one-control progress, mismatching expected
failures, exact formal-runtime preservation, unchanged repeat suppression,
transport metadata changes, changed runtime/selectors, candidate/source/plan
borrowing, unsafe paths, duplicate captures, digest drift, wrong peers and
ambiguous owned nodes. A wrapper regression consumes a profile through the
actual independently assessed first-four pipeline and checks repeated output.
These arbitrary fixtures are protocol controls, not real cross-repository
application execution or measured knowledge benefit.

Actual retained UIAbility readback, integration results and remaining qualification
gaps are reported separately after executing this consumer on original captures.

## Actual retained-capture integration checkpoint

Overall maturity remains **68%**, not increased for evidence reconstruction or
protocol tests. External `retained-qualification-audit-Ihl5YfXe/generic-downstream-2`
ran the ordinary first-four assessor and Rust router with the reviewed UIAbility
profile and original eight file-read envelopes. The scoped consumer reconstructed
two accepted and two intended rejected observation controls. It selected the
missing normal-exit negative control and original build/mutation/command-capture
reconciliation, explicitly scoped to retained HarmonyOS7 API26 x86_64 observations.

`generic-downstream-3` repeated the same ordinary entrypoint with its predecessor.
Scoped scheduling became false/awaiting-new-evidence; partial-summary active cohort
became empty. Exact API22, independent Oracle, wrong-implementation and recovery
formal action definitions were unchanged. No qualification receipt, active
knowledge or candidate row was edited. The profile and raw captures remain
operational artifacts outside source publication, not a new physical execution.

Seven new Rust regressions and eight downstream regressions passed. Ordinary
`cargo test --locked -p agentlab_code_analysis` also completed with exit zero.
library Clippy completed with four pre-existing warnings; strict `-D warnings`
did not pass the whole library. The new lifetime warning was fixed without
changing unrelated legacy code or lowering any existing production gate.

The optional lane still requires a reviewed profile and retained captures. It
does not discover historical evidence automatically, wire cross-Action capture
history, persist new observations to TableGit, dispatch the missing control or
prove the guidance improves an Agent. Those remain business-loop gaps.

## Native dialog capture integration checkpoint

The named Hypium adapter consumed the original command-log contents from real
dialog runs 6, 7, 8 and 10 reported in
[the runtime calibration](flywheel-real-dialog-controls-20261003.md).
It reconstructs two accepted observation controls and two rejected observation
controls with matching reviewed failure sets. Run 8's later context failure is
explicitly retained as a possible cascade, not independent semantic coverage.
The run-9 log, despite HDC process exit zero, is rejected with
`partial Hypium final summary absent`; no feedback output is created.

This consumer checkpoint used an isolated, unadmitted planning projection. The
retained constructor proposal was reconstructed using its original request and
the existing proposal validator; an operator-declared construction plan kept
Oracle, all five required wrong variants and runtime requirements unqualified.
No active TableGit row, released knowledge snapshot or historical proposal changed.
The source revision remains the original candidate base; the derived reference
commit/source-set is declared separately in the reviewed runtime profile. These
declarations do not authenticate the tested source or its mutation lineage.

The ordinary independent readiness assessor detected five path-binding blockers:
new standard-test source, test registration and the new host page are not bound
in the retained candidate's program facts (two paths also block Oracle binding).
The Rust consumer preserves the exact `focused-knowledge-refresh` action rather
than treating runtime green as admission. Repeating the final same-evidence
input produces `awaiting-new-evidence` and `schedulingAllowed:false`, with formal
gate actions unchanged. The remaining UI isolation and uncovered behavior stay
in the reviewed profile; knowledge repair takes scheduling priority.

Private controlled artifacts are retained under `flywheel-native-feedback-k5jAGTm5`:
original-content readback envelopes, proposal-derived candidate, construction
plan, independently assessed readiness, reviewed profile, final feedback/repeat,
and the interrupted-log rejection. Public source contains protocol code and
arbitrary Rust fixtures, not these raw runtime captures.

Overall maturity remains approximately **69%**. This closes named native-log
consumption and duplicate-work suppression for reviewed captures, not automatic
profile construction, source/patch authentication, knowledge admission,
participant integration or a complete autonomous flywheel. Next, admit an
explicit successor source/knowledge cut for the new host/test facts, repair
failure cleanup in a successor test cut and rerun its controls before assessment.

## Construction-binding correction

The preceding proposed source-refresh step was too broad: new test and host
targets are intentionally absent at the original source revision. Requiring their
old-source facts creates an unsatisfiable refresh loop. The optional native
`--bind-construction-paths` gate now reconstructs the original edit packet against
the clean pinned checkout and knowledge cut, then checks candidate source, packet
digest, selected editable paths and owners. Existing targets retain source-Blob
preconditions; created targets retain absence preconditions. Construction binding
does not change `factEvidenceBound`, semantic readiness or formal qualification.

The ordinary batch supports reviewed profiles under
`AGENTLAB_CONSTRUCTION_BINDING_ROOT/profiles/<candidateId>.json`, with only schema
`agentlab.construction_path_binding_profile.v1`, reviewed=true, candidateId and
absolute sourceWorktree/editBoundary fields. Missing profiles preserve the prior
route. Supplied invalid profiles fail; no source or packet is inferred.

Controlled `flywheel-construction-binding-NseNZyis/batch1` consumed the retained
dialog candidate and original packet. Individual assessment cleared five path
blockers and retained all six qualification blockers. Formal routing and the
partial native-log consumer completed; scoped work now targets missing controls
and isolation rather than the impossible source refresh. However, final batch
summary rejected the isolated projection with `downstream parent absent`.
No successful batch, authority admission, repeat-batch guard or new runtime
execution is claimed. Preserve this failed batch rather than inventing parent
rows or disabling digest-bound lineage. Overall maturity remains **69%**.
