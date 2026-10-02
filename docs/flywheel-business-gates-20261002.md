# Existing business gates in the cycle coordinator

Overall maturity remains 62%. This adapter connects real fixed-cut validators to
the coordinator; it does not replace missing producers with successful receipts.

Prepare with `--prepare-business-cycles --knowledge ABS_CUT --guidance-request
ABS_SELECTION --reviewed --output FRESH_ABS_DIRECTORY`, then execute its recipe
with `--execute-flywheel-cycles --recipe PREPARED/recipe.json --output FRESH_ABS_CAPTURE`.
The preparer validates explicitly selected source applicability and pins the
knowledge files, selection and current executable. It leaves operation, behavior
and admission inputs absent until provided as reviewed state. The generated
two-round budget is a ceiling, not a promise of two completed rounds.

The same executable runs every stage through `--run-flywheel-business-stage
--stage-request FILE --output .` in the coordinator's fresh stage directory.

| Stage | Real gate connected | Boundary |
|---|---|---|
| Repository understanding | Source-set binding and existing five-table guidance binder | Validates existing knowledge; no fresh semantic analysis or remote readback |
| Program analysis | Durable assessment resolution and full strict reassessment | Reproduces stored facts/operation evidence; no newly generated program graph |
| Maintenance verification | Reviewed build-only or source-maintenance execution and independent capture qualification | Requires an applicable explicit recipe; build-test/test-only/support-config remain unsupported |
| Case execution | Existing captured participant/behavior loop | Needs reviewed inputs; does not generate a new case or qualify full Harmony |
| Evidence return | Existing raw-evidence lesson reconstruction and admission staging | Needs reviewed committed lesson/proposal; stops before remote atomic admission/readback |

State schema is `agentlab.flywheel_business_state.v1`, with
`automaticPromotion:false`, repositoryId/sourceRevision, `knowledge` containing
absolute directory/cutSha256/revision, and `guidanceSelection` containing absolute
path/SHA256. `stageEvidence` records report paths, exact digests and statuses.
Original declared and recomputed assessment files remain retained even when
their equality gate rejects. Missing materials return a specific review-required
gap; gate rejection does not become an inferred Agent behavior failure.

Optional `operationCapture` supplies directory/executionReceiptSha256/moduleRoot.
Alternatively `operationExecution` supplies reviewed=true, sourceWorktree and
digest-bound path/SHA256 references named before/recipe. Build recipes additionally
require moduleRoot and plan; source recipes follow the
[source-maintenance contract](source-maintenance-operations-20261002.md).
The two inputs are mutually exclusive. Build execution independently reselects
against the fixed scope/fact cut before launching probes, prepares dependencies
and runs two bounded clean builds. Source execution independently revalidates
the strict baseline and selected source-only scope before executing frozen controls.
Raw captures remain in business/operation even when execution or qualification fails;
this does not advance the stored assessment or admit new knowledge automatically.
The default maintenance stage allows 660 seconds around the existing ten-minute
executor ceiling. Case execution allows 720 seconds without changing inner Agent
deadlines; two rounds have a 3600-second total command ceiling.
Optional `behaviorExecution` supplies digest-bound path/SHA256 references for
contract/calibrationCapture/recipe plus state.candidateId. Guided recipes must
bind the same packet as state, not another valid but stale knowledge cut.
Optional `lessonAdmission` supplies proposalDirectory/lessonSourceDirectory/lessonId.
Its original behavior contract/capture must exactly match the current completed
case stage's retained latest attempt, before ordinary admission reconstruction.
An independently recorded failed task is still a completed observation and can
return a reviewed lesson; taskPassed stays false. Infrastructure or incomplete
capture cannot be converted into such an observation.
A borrowed older execution cannot substitute for this round's evidence return.
Admission staging never advances active authority or schedules a fabricated new
knowledge cut. Actual independent commit readback is still a separate integration.

## Local operational checkpoint

External capture `business-gates-local-2539105-v1-capture` ran the built-in public
adapter against actual published knowledge revision
`4327475966e056b4c2d93f0736062656c182728e`, cut SHA256
`a9a8c64f6dda6bc61a9e8d80febdcf352b7c3346626ff55911be0ca1d218535a`.
This used the pending adapter's exact executable digest, not a claim that the
adapter already existed in main 2539105. Source/byte identity is in the retained
recipe and process captures. No model was dispatched and no authority was written.

Knowledge validation and strict assessment reproduction completed. The third
stage stopped for `revision-bound-maintenance-operation-capture-required`;
case execution did not start and completedRounds remained zero. All three stage
process receipts record exit zero; the terminal review-required verdict is a
business boundary, not a successful entire cycle or an infrastructure failure.

The reproduced all-four-repository assessment contains 489 scope Skills:
489 structurally ready, 46 program-bound, 41 semantically ready and 2
maintenance-operation-ready. These are scope-level counts under the strict
standard, not overall maturity or proof of complete maintainer understanding.
They motivate real bounded knowledge expansion and operation verification,
not further protocol-only maturity increments. The retained current cut must
remain unchanged while a later expansion/lesson candidate is being evaluated.

## Real dispatch routing gap

Action 36992821326 on main 253910559bc7c885a8a036e713c0df042bd5d435 failed
before model execution. All 25 code-workshop scopes were semantic-ready: 23 need
operation verification and two are knowledge-ready. The workflow offered only
semantic-refresh, so zero scopes were selected. Its global 401 eligible scopes
belong to other repositories, not the selected repository. The 23 operation gaps
derive into nine build-test, seven source-only, three build-only, two test-only
and two support-config scopes. This is an executor/routing capability gap, not
evidence of a participant failure. Preserve the rejected dispatch; do not weaken
the productive semantic-plan gate or report a different repository's progress as
selected-repository coverage. Build-only is a coarse planner category, not proof
that its scopes produce HAR artifacts. A live HW Linux readback at the clean
7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6 source found hmosword-build is a JavaScript
helper package whose only npm script is a failing placeholder test; products/tv
is an application module. The connected HAR executor cannot be assumed applicable
to any of those three scopes without an actual reviewed operation contract.
Artifact/task-specific adapters are still required; no new operation-ready scope
is claimed from this connection. AWMCP direct-route operations 004b and 004c
retained the exact source identity and inspected configuration at hwlinux/mb.
