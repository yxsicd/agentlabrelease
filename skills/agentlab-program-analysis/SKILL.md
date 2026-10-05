---
name: agentlab-program-analysis
description: Maintain revision-bound program structure and analysis evidence used to generate evaluation seeds.
metadata:
  agentlab-layer: method
  agentlab-role: maintenance
  agentlab-stage: program-analysis
  agentlab-ownership-plane: repository-native
---

# Program analysis maintenance

Analyze the same source commit as semantic knowledge. Record symbols, imports, call candidates, module dependencies, configuration/resource references and available test/build entrypoints as typed `program_facts` rows. Use stable source-derived IDs.

Program analysis MUST NOT form an independent shortcut around maintainer Skills.
Every candidate binding names revision-matched repository-analysis,
program-analysis and seed-extraction instance Skills plus the exact supporting
facts and archived analysis rows. Missing coverage fails closed under
[the maintainer knowledge gate](../../docs/maintainer-skill-gated-case-pipeline.md).

Prefer a language-aware parser/compiler when available. A lexical extractor or name join is useful but must retain its method and unresolved status; a same-name candidate is not resolved dispatch. Record source path/span, analyzer identity and source revision. Keep semantic Skill links explicit.

Run generic MCPGit table programming/search/SQL over fixed input cuts. Archive code, request/bindings, complete typed result and interpretation as analysis rows. Cases reference those analysis IDs. The existing executable SQL example joins call and symbol candidates; it is not a Harmony parser.

Analyze candidate dependency chains and impact surfaces, then hand them to [seed extraction](../agentlab-seed-extraction/SKILL.md). State coverage and gaps such as reflection, dynamic loading, generated code and missing build dependencies only when they affect this source analysis.

Store source/facts/analysis structurally in TableGit. Build trees and temporary binaries belong to SessionFS Workspace snapshots; do not put multi-GB compiler output into Git. Export with [the three-table workflow](../../examples/knowledge-seed/README.md).

Produce target-instance guidance for this stage as TableGit Skill rows,
separate from the structured facts/tasks/results. Follow
[the two-layer methodology](../agentlab-skill-methodology/SKILL.md) for
method/source lineage and independent layer/role fields.

## Current Rust ArkTS analyzer

Use crates/agentlab_code_analysis (agentlab-code-analysis), pinned Tree-sitter
0.27.0 and the AgentLab grammar extension derived from tree-sitter-arkts0.2.0. It lowers CST nodes to module/symbol/call,
assignment/decorator/ArkUI facts with exact source spans. Multiline imports are
AST-derived, not lexical regex matches. Tree-sitter is not a semantic type AST;
calls and assignments remain unresolved. Read the crate README for command and
coverage. The stateStyles object-block gap is fixed by an explicit pair-value grammar
extension with upstream/extended regression tests. All556 fixed code-workshop
files now parse without syntax errors. Retain the original failure evidence and
the exact grammar digest; this does not qualify typing, resolved calls or HAP.
When improving an analyzer, update existing facts and remove obsolete AST rows
using their actual versions; archive old cuts and do not merely insert facts on
the first run. Test fixtures need process-local uniqueness under parallel tests.

When expanding the selected corpus, validate established dependency paths while allowing additional legitimate paths. A fixed result count confuses broader coverage with regression; archive the query/input cut and describe the observed path count without claiming symbol resolution.

When downstream construction readiness finds that an already semantic-ready
fact omitted required implementation or Oracle paths, refresh that same stable
fact instead of inventing another fact or consuming a random unbound scope.
Bind the exact candidate and readiness-plan digests, retain every prior evidence
Blob, require every missing path with its exact source Blob, and independently
reassess the full table. A focused refresh must not increase program-bound or
semantic-ready counts, grant operation readiness, execute the Oracle, or mutate
the frozen candidate. Persist the enhanced fact as one revision-fenced TableGit
transaction; regenerate the downstream candidate only from the later cut.

Distinguish inventoried paths from loaded implementation context when constructing
source-maintenance verifiers. For a small responsibility whose complete UTF-8
source fits the author context budget, include its owned implementation bodies
with exact Blob/digest identities rather than only anchor files; this can expose
real mapping/helper behavior without guessing dependencies. Larger responsibilities
retain bounded anchor context and require explicit decomposition or context refresh.
Binary bodies remain unloaded. Additional context is not semantic verification,
permission to modify another responsibility, or evidence of platform execution.
For control failure attribution, trace field writes through the particular branch
that emits each checked observable. A changed internal field may never reach one
scenario's returned output; do not declare all scenarios failed merely because
they execute that write. Preserve source-correct original oracles and revise an
incorrect failure set through explicit review. Whole-object and overlapping leaf
checks are not independent coverage dimensions. Keep missing dependency source
context distinct from an omitted runtime export binding; one does not prove the
cause or repair of the other.

Separate syntactic dependency inventory, compiler-emitted runtime imports and
executed dependency closure. When import erasure affects a runtime claim, inspect
output from the same pinned compiler and options as the frozen evaluator; retain
source, compiler and emitted-output digests plus diagnostics. Use language-aware
inspection of emitted imports, not source-name matching. An erased type/interface
reference is not an unbound runtime import, but its typing may remain unresolved.
Transpilation is neither type checking nor module execution. Trace initialization
through retained value dependencies and explicitly bound globals; distinguish
executable resource calls from resource syntax inside generated string literals.
Do not add implicit platform stubs or call a host seam platform qualification.
Read [the retained compiler checkpoint](../../docs/flywheel-compiler-dependency-evidence-20261005.md)
when interpreting the import-erasure finding; it does not amend a historical review
or supply compiler evidence to an already frozen experiment.

For the explicit TypeScript host adapter, set compilerAnalysisAdapter to
typescript-transpile-v1 in the original author policy with exactly one pinned
compiler dependency. Rust reconstructs sourceCompilerEvidence from loaded script
bodies during request preparation and admission; design reviews receive that same
evidence. It binds executable, compiler, analyzer, runtime-helper and source
digests, options, diagnostics and emitted-output digests. Requests without this
adapter remain unchanged. Require error-free parse/transpile evidence before
using an emitted dependency absence; static require calls remain candidates where
shadowing or dynamic loading is unresolved. This adapter neither checks types nor
executes source, and does not replace maintenance-operation or platform evidence.
Use [the native adapter contract](../../docs/flywheel-native-compiler-evidence-20261005.md)
for activation, capture limits and independently run real-compiler verification.

In pre-execution design reviews, prefer criterion source citations as exact
path/quote pairs against uniquely loaded frozen context; source-array positions
are not stable identities. Cite design statements through their actual /design
string pointers, not original-request text. Native location validation establishes
content binding only, not whether a citation supports the reviewer's conclusion.
Never relocate a rejected historical response into acceptance.
For prospectively enrolled early-review protocol correction, freeze
`reviewRepairLimit` before the first constructor turn (default 0; at most 1).
Use the native attempt prompt and retained complete original capture; do not
append a policy to an old capture or reopen an exhausted root. Keep source,
design, rubric and participant model/route/effort unchanged. Syntax and citation
correction is distinct from a completed `revise`/`unverified` semantic decision:
the latter requires a reviewed design successor, not another protocol attempt.
For the native negative-review bridge, reconsume the original captured early
review before preparing an exact-change review. Preserve every negative row's
ID and rationale; do not replace or omit findings to fit a budget. A v3 change
review binds exact ancestor records, owned source paths and finding IDs. Derive
the candidate from those changes, preserving unrelated records. Verify its own
distinct-phase capture, then require another quality review and ordinary runtime
calibration. Native preparation/content checks alone do not authorize dispatch;
enroll a separate bounded semantic-stage budget before the original run. This
bridge has bounded coordinator integration under validation, not real convergence
evidence. When automatic revision selects a candidate, carry the unchanged
ancestor and exact v3 feedback into native final staging, not only the selected
design. Native staging must rederive that successor through the same exact-change
gate used by manual revisions. Retain the initial design separately; a successor
marker routes evidence and records consumed allowance, never semantic approval.
Before a semantic revision model call, compare model/route/reasoning identity
with the original captured review and run native dispatch admission. Recheck
identity at completion. Consume Rust-emitted candidate bytes without host JSON
reserialization; equivalent values need not have identical bytes or digests.
Keep immutable finding provenance separate from model-owned change judgments.
A retained real revision omitted an aggregate criterion finding and shortened
three original rationales. Overlapping criterion/control findings are distinct
bound rows, not permission to deduplicate. The reference-response lane under
validation requires every original ID exactly once; Rust restores observed text
and ordinary v3 admission checks changes, owned paths and protected ancestors.
Keep original reference response and reconstructed v3 feedback as separate
digest-bound artifacts. Reconstruction is not reviewer approval or a repair of
historical output; legacy captures must retain their original protocol.
Exact change entries replace complete records, not a nested field's text.
Use `responseContract.changeRecordShapes` to locate parent checks, scenarios and
controls; copy the entire before record and include unchanged fields in after.
A retained real revision supplied observation-adapter strings as scenario records
and was correctly rejected. Record-shape guidance does not repair that response,
relax exact ancestor equality or reopen its consumed semantic budget.
Retain both responses and let ordinary completion/content gates derive the
corrected decision; a correction may still be negative. Read
[the early-review contract](../../docs/flywheel-design-quality-review-20261005.md)
for the bounded transport and its evidence limits.
Review delivery and review interpretation are separate evidence: a real reviewer
received compiler output yet treated an erased interface import as a runtime
dependency. Use the compiler import navigation to find the original per-file
status, diagnostics and emitted candidates; cite original evidence, not the
projection. Empty candidates establish no runtime-closure verdict, especially
when compilation failed. Source-citation diagnostics locate the response row,
declared path and matching quote paths without editing the response or approving
its conclusion. A matching quote elsewhere is repair guidance, not acceptance.
Compare claimed ordered/exception behavior with the actual scenario input
sequence; prose about an omitted operation does not exercise that operation.
For criterion pointer citations, native diagnostics distinguish absent pointers,
non-string targets and quotes absent from the declared target. Inspect the exact
response item and bounded matching packet-string pointers: a retained reviewer
kept quoting array item zero through item one's pointer after its protocol repair.
Both pointer/quote and uniquely bound source path/quote forms remain supported.
Navigation does not relocate citations, coerce booleans or qualify semantic support.
Report all detected citation defects together within a bounded feedback budget,
with total/reported counts and visible truncation; one repair must not discover
defects serially. A real bounded reviewer consumed exact navigation but replaced
an object citation with a null-valued field and an empty quote. Distinguish empty,
non-string and oversized citation fields; never stringify values or raise retry
allowances to conceal failed convergence. Native regression is not real repair proof.
Real-response replay also exposed source-citation shape defects hidden behind the
first packet citation; keep packet pointer evidence distinct from source path evidence.
For pure source/design review, remove tool capabilities at participant dispatch,
not only in prose. A real reviewer invoked bash and issued a second model exchange
despite zero transport retries; the single isolated-exchange gate correctly refused
it. Use the pinned adapter's zero-tool mode and check captured command, lifecycle
and actual wire tool surface. Keep tool-enabled development roles unchanged; never
discard an exchange or reopen a spent review to manufacture independent completion.
For an admitted oversized negative review, preserve every aggregate/detail row
and its rationale. Use native read-only decomposition planning to retain complete
ID coverage; all grouped exact before records bind the same original ancestor.
Reject cross-group record conflicts and validate coupled changes atomically,
not through sequential unreviewed rebases. Planning/content validation grants no
dispatch. For fresh automatic trials, enroll decomposition before inference via
the versioned semantic policy and use original-wire revision completion admission;
legacy captures cannot acquire this lane retroactively. Keep raw reference replies
separate from Rust-reconstructed batch feedback, and independently review the
whole successor before code generation. Real v2 cycle qualification remains pending.
Read the [decomposition and real-capture checkpoint](../../docs/flywheel-design-quality-review-20261005.md)
before planning a successor. Original-capture admission verifies retained delivery,
not a reviewer's interpretation of compiler output or pre-execution requirements.

Separate pre-execution design adequacy from post-execution proof. An early pass
means source-grounded setup and predictions are adequate to attempt calibration,
not that execution or runtime closure has been verified. Missing explicit bindings
for transitive module initializers remain blockers; absence of execution alone is
not a defect in a pre-execution baseline/reference design. Inspect top-level enum
reads and resource calls in retained dependencies, even if generate never uses
those exports. Require a proposed binding/seam with its source-only limitation;
never infer implicit platform defaults or waive a failed baseline.
Audit each control against every scored check. Compare the complete predicted
failure set with its declaration, including overlapping whole-object field checks
and return checks. Detecting a mutation with one check does not justify omitting
another predicted failure. The native control/check navigation is exhaustive
inventory, not execution evidence or a predicted verdict; cite original records.

The frozen source runtime owns control transformations: source() and loadModule()
already consume the selected edits. Do not apply the design's edits a second time
in generated verifiers. For initialization claims, compare source-observed state
with the relevant frozen initialState subtree through assertInitialState; allow
mismatches to fail before the tested operation. An ungraded match flag cannot
establish verification. Choosing that subtree still requires source review, and
the helper neither establishes complete state coverage nor approves an Oracle.
Its pointer is relative to initialState (for example /fields, not
/initialState/fields). loadModule returns exports, not a constructed instance;
instantiate the source-exported class explicitly before observing fields or calls.
Keep proposal sourcePaths limited to loaded implementation bodies; binding an
import specifier to a controlled seam does not load that dependency's source.
Before verifier generation, use the Rust-produced source_verifier_interface.v2
packet bound to the exact request and validated design. It enumerates allowed
loaded paths, argument positions and initial-state-relative top-level pointers;
nested pointers remain supported. Preserve its bytes in generation evidence.
In design-first/frozen-design mode, transformation belongs only to the operator
runtime; do not carry legacy self-transformation instructions into that mode.
This packet is interface data, not proof of model compliance or semantic truth.
Keep construction/path descriptors separate from concrete observable initial
state. For source instances, declare relevant own data values in initialState.fields
and call assertInitialFields(scenarioId, actualInstance) after construction and
before the tested operation; it reads fields rather than copying expectations.
Missing own fields, accessors and mismatches fail closed. For other state, use an
explicit source observation with assertInitialState: actual must be the selected
subtree value, not a wrapper. Neither helper authenticates an instance or proves
state coverage; copied expected objects cannot establish source initialization.
When these assertions fail, use initialStateDiagnostic (schema
agentlab.source_initial_state_error.v1) to locate the scenario and escaped pointer
relative to initialState, with the reason and actual/expected types. Diagnostics
contain no observed or expected values and do not qualify a check. Trace the
identified field through source constructors, retained dependencies and explicit
global bindings; repair missing initialization from source evidence, never by
copying frozen expectations into the instance. Preserve the failed baseline and
rerun it before interpreting negative controls. The diagnostic traversal does not
add another observation of source getters; assertInitialFields rejects accessors
without invoking them.
For operation/exception effects, use observeFields(actualInstance, fieldNames)
to read explicitly selected own data fields before or after the operation. It
rejects missing fields and accessors, accepts no expected-state input and returns
raw values; nested references are not deep snapshots and non-JSON observations
need an explicit reviewed representation. Native inaccessible private slots stay
inaccessible; a TypeScript private modifier alone does not prove invisibility in
the pinned host output. Early reviews receive the same digest-bound verifier
interface used by generation. Require actual ordered inputs and scored state
checks for demanded earlier writes and later skipped writes; a throw/no-return
check or limitation prose cannot substitute. Interface availability proves
neither that source was executed nor that the generated verifier uses it.

Use the constructor's `--design-first --design-only` mode when a new behavior
surface needs independent semantic review before verifier generation. The retained
design/validation digests bind an unreviewed draft, not an approved Oracle. Review
source-derived return shapes, synchronous versus Promise seams, initialization,
and the actual branch affected by each wrong control; structural validation cannot
prove those semantics. Preserve complete design failures and partial generation
captures. A generation deadline is not permission to stage incomplete output or
to treat isolation validation as behavioral qualification.

For a design-level revision, pair `--parent-design` with
`--design-review-feedback` and retain `--design-first --design-only`. Rust binds
the original request/design hashes, checks that the source/knowledge request still
reproduces, and limits findings to loaded owned paths before model dispatch.
Feedback requests revision; it cannot approve the parent or successor. This path
does not require inventing a completed verifier proposal after an earlier code
generation failure. Keep design feedback separate from executable-proposal review.

Keep repair feedback actionable: distinguish schema/scope mismatches from invariant
byte limits and limitation counts, report the observed value, and retain unchanged
acceptance limits.
For exact source edits, use native `source_edit_match_diagnostic.v1` navigation:
bind the rejected edit pointer, requested-text digest and current control-body
digest; inspect literal byte offsets and bounded verbatim source windows. Match
against the body after earlier edits in that same control, not always the original
file. Line anchors help locate source but do not establish a complete edit match.
A real two-attempt constructor changed an ambiguous match into absent text; both
were correctly rejected. Copy enough exact source context to identify one match,
without fuzzy replacement, first-occurrence selection or whitespace normalization.
Keep raw stderr and every response unchanged; decoded native feedback is only
navigation. Budget exhaustion closes the root. Diagnostic regressions do not prove
that a fresh Agent repairs its design or that resulting controls are meaningful.
For rejected control contracts, use the native field pointer and rule to distinguish
object shape, invalid ID and duplicate ID. Control IDs remain 1..64 ASCII letters,
digits or hyphens; an underscore is not silently normalized. Request the smallest
source-preserving correction within the existing attempt budget and retain every
original response. A protocol repair does not establish design semantics or reset
review/execution budgets.
Draft state must use strict JSON; undefined source behavior needs
an explicit observation representation, not an illegal literal or a source rewrite
to null. Constructor lookup sequences and real method argument shapes are execution
inputs, not facts established by prose descriptions of initial state.

Before negative calibration, execute unchanged source and behavior-preserving
controls against the frozen scenario/check contract. A baseline check failure
invalidates that contract even if a wrong control matches its declared failure
set; do not count inherited baseline failures as mutation detection. Retain raw
initialized state, emitted results and ordered seam arguments separately from
expected values. Re-derive contradicted expectations from source causality in a
new reviewed design cut, preserving the original failure. With shared sequential
seams, an edit that removes a lookup may shift later consumers without changing
their returned values: trace each edited control rather than inferring impact
from the unmodified call graph. Controlled source probes are diagnostic evidence,
not admitted Oracles, Agent evaluations or platform execution.

After reviewing a retained design, use `--frozen-design` paired with its exact
`--frozen-design-sha256` to continue verifier generation without another design
model call. The constructor preserves original design bytes and revalidates
them against the current reproducible author request before participant dispatch.
Do not mix this continuation with design regeneration or design-review revision.
A digest-bound `--revision-request` may revise verifier code while retaining the
same frozen design; both native preflights must pass before participant dispatch.
This freezes
the intended contract, not approval: independently inspect and calibrate generated
code before execution qualification or knowledge promotion.

For complete constructor responses rejected only by strict JSON parsing, an
explicit `--proposal-format-revisions 1` permits one same-session protocol
correction. Preserve every original response and completion receipt. Do not strip
Markdown fences into an accepted proposal, retry incomplete/truncated transport,
reset the budget, or treat a repaired format as source-semantic approval. A valid
JSON object with an invalid proposal contract goes to the existing native gate,
not this format loop. Frozen seam call records expose arguments, not return
values: absent record fields cannot establish undefined source behavior.

Use the optimized native producer for operational construction and calibration,
not a debug executable by default. Full-cut reassessment and repeated executable
hashing can dominate the fixed native-gate deadline. Compare retained input,
design-validation and helper digests when measuring build-profile changes; do not
skip identity checks, cache an unbound verdict or restart a completed Agent to
recover a static-stage timeout. Keep original timeout evidence and recover only
the same frozen output with a fresh native-stage destination. Faster gates do
not certify behavioral benefit or an automatic end-to-end recovery.

Separate modification ownership from read-only source context. A construction
Oracle may inspect a path outside its editable responsibility only when the
candidate explicitly lists it as context, a bound fact cites its exact Blob,
and exactly one scope in the same repository/source cut owns it. Report that
owner without expanding the candidate's editable selectors or claiming a
resolved dependency edge. Missing, conflicting or revision-mismatched context
bindings remain knowledge blockers; runtime and Oracle qualification stay
independent. A failure after knowledge persistence must recover the committed
cut and retained proposal, not rerun the successful Agent or overwrite history.
Do not assume empty constructor export seams preserve a dependency's field
initialization. Prefer available read-only source when its behavior is required,
or verify the controlled seam against actual initial-state observations. A
source-bound review opinion cannot waive a failed baseline or initialize missing
fields from expected values.

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

### Loading lifecycle and shared-helper analysis

Rust binding facts preserve declaration kind, owner, type, initializer and exact
byte span. Execute submitted top-level delay constants as well as lifecycle
methods; injected reference constants can hide incorrect Agent changes. Execute
the submitted shared BreakpointType implementation with a controlled platform
enum. Preserve source analyses for the lifecycle, helper and caller separately,
even where local fact IDs coincide. An import seam is source evidence, not
executed UI or resolved runtime call coverage. Calibrate wrong cancellation and
unknown fallback before the staged real Agent case. Invalid source and an Agent
that never reaches tools remain valid failed outcomes with empty typed tables.

When changing a shared helper's default return, identify known values that were
implicitly served by that return. Retest every known value at every later turn.
The loading capture's parent lost the lg branch while adding unknown-to-sm
fallback; a fresh branch retained it. Archive both the failed named check and
submitted helper source before drawing this conclusion. Compile success alone
does not detect this semantic regression.
