# Maintainer Skill evidence flywheel

Apply the same evidence standard to every target repository. Repository names,
languages, frameworks and platform test tools are instance facts; they are not
branches in the standard.

## Universal evidence dimensions

- `responsibility`: owned and excluded responsibilities.
- `boundary`: public inputs, outputs, entrypoints and consumers.
- `relations`: cross-file or cross-scope dependencies and impact paths.
- `behavior`: state, lifecycle, invariants, failure and recovery contracts.
- `operation`: build, test, runtime or maintenance verification.

Program facts bind these dimensions to a scope through `scopeSkillIds`. An exact
source evidence path with a Git Blob OID may provide a deterministic provisional
binding to the longest matching scope boundary. Release-artifact paths without
target-source Blob identity never bind implicitly. A filename, import count,
README statement or repository-wide fact does not prove behavior by itself.

Assessment must check the repository and source revision on every bound fact,
including facts reached through `evidenceFactIds`. Preserve stale or mismatched
facts as historical evidence, but exclude their dimensions and report rejected
bindings for targeted refresh. A matching path or Blob does not override a
mismatched source revision. Operation coverage requires an explicit target
`scopeSkillIds` binding: path inference or dependency-fact inheritance may help
semantic analysis, but a successful dependency build does not qualify its
consumer automatically.

An explicit operation dimension is still a claim, not independent execution
proof. Validate the referenced receipt's bytes, qualified verdict, exact source,
scope coverage, environment and limitations before writing that fact. The
legacy assessment's identity/dimension checks do not independently execute or
inspect external receipts; never present its L3 count as end-to-end flywheel
maturity.

### Executable operation receipt verification

Use `agentlab-maintainer-skill-flywheel --operation-receipts-root ROOT` for
strict receipt-content assessment. Each operation fact must carry
`operationEvidence: {path, sha256}`. Paths are relative to the explicit root,
symlinks/traversal are rejected, and the exact original bytes must match before
parsing. Missing, failed, mismatched or unsupported receipts emit
`MS-OPERATION-RECEIPT-UNVERIFIED` and cannot contribute operation maturity.
Keep their semantic dimensions and original evidence; a missing adapter is not
an application failure.

The first adapter accepts `agentlab.maintainer_scope_build_qualification.v1`:
exact repository URL/ID/revision and one scope, clean source, pinned toolchain,
successful dependency preparation, two distinct successful clean build
executions, consistent canonical content and explicit build-only limitations.
This is a Harmony HAR receipt-format adapter, not a repository-name rule.
It validates recorded assertions and content integrity, not receipt authorship,
raw log/artifact bytes, or a fresh build. Report no-type-check builds as not
type-check-qualified. Runtime/test/performance receipts need their own adapters;
never relabel them as build receipts to bypass an unsupported format.

Prepare a deterministic operation fact or combined candidate fact cut without
writing TableGit:

```sh
agentlab-maintainer-skill-flywheel \
  --scope-skills scopes.jsonl --program-facts facts.jsonl \
  --prepare-operation-fact SCOPE_ID \
  --operation-receipts-root ROOT --operation-receipt RELATIVE_PATH \
  --operation-receipt-sha256 EXACT_SHA256 --output candidate-facts.jsonl
```

Omit `--program-facts` to emit only the new fact. Existing IDs must be unique;
conflicting operation IDs fail before creating output. Repeated preparation
into distinct new paths produces identical bytes. Outputs refuse overwrite.
Reassess the candidate with the same receipt root and bind its parent digest.
This produces a proposed knowledge cut only; exact TableGit CAS/import/readback
and case publication remain separate steps.

Pure operation rounds use `--compare-operation-round --before BEFORE --after
AFTER --selected-scope SCOPE_ID --output RESULT` (repeat selected scope for a
batch of up to four). This gate requires contiguous digest-bound strict
assessments, unchanged source catalog and semantic evidence, verified L2-to-L3
transitions for every selected scope, and no changes to unselected scopes.
A no-change replay must preserve the fact cut and yields `no-change`, not
convergence. Mixed policies, partial batches and unrelated changes reject the
result before output. The result retains next-round gaps and never writes
TableGit. Do not send this result to the semantic-only stage as if it were a
new semantic Agent proposal. Prepare a compatible local snapshot with the Rust
operation stager instead:

```sh
agentlab-maintainer-skill-flywheel --stage-operation-round \
  --base EXACT_EXPORTED_CUT --program-facts CANDIDATE_FACTS \
  --before STRICT_BASELINE --after CHILD_ASSESSMENT \
  --operation-receipts-root ROOT --selected-scope SCOPE_ID \
  --run-id SAFE_RUN_ID --output NEW_STAGE_DIRECTORY
```

The stager independently recomputes both assessments, verifies the latest
durable assessment reference and all input digests, preserves existing facts,
and requires exactly one deterministic receipt-qualified fact per selected
scope. A changed semantic fact, forged report, missing receipt, duplicate ID or
no-change round fails before output creation. Preserve the distinct counters:
refresh-round history and assessment history need not have identical indices.
Append one parent-bound refresh round and retain baseline, child and comparison
reports. Method Skills, scope catalog and evaluation cases remain unchanged.

This produces the five-table snapshot and stage manifest consumed by the
existing `scripts/maintainer-skill-tablegit.py sync` path. That separately
authorized step owns revision-fenced atomic persistence, exact committed-cut
readback/export and optional replication. Local staging has no network client
and proves none of those remote postconditions. Review the snapshot and producer
identity before sync; it is not an automatically promoted knowledge cut.
If the recorded assessment predates the exported facts or uses the legacy
operation policy, default staging rejects the changed baseline. Only an explicit
`--allow-baseline-reassessment` permits independently reassessing the current
exact cut; retain both assessment digests and mark that migration as no maturity
gain. The subsequent operation transition still uses two strict assessments.
Operation lineage uses `agentlab.maintainer_operation_refresh_round.v1` in the
existing refresh-round table, preserving historical semantic round formats.

Carry exact original receipt bytes with accepted operation facts. The stager
records their digests and relative paths under `operation-evidence`; never depend
on the originating machine's checkout or mutable filesystem path.
The `receipts` list covers newly accepted facts; `inheritedReceipts` separately
retains existing facts whose operation checks are verified in the child report.
Reverify inherited bindings and preserve original bytes and SHA before staging.
Rejected or unsupported historical claims are not portable proof. The combined
unique receipt payload is bounded to 16 MiB. Older manifests without the
optional inherited list retain their accepted-only compatibility contract.
Before any TableGit mutation, the sync writer checks table digests and portable
receipt bindings; after exact committed-cut export it preserves receipt bytes,
baseline, comparison and the original stage manifest as evidence sidecars.
Verify an accepted fact without its original receipt directory, and reject
tampering. Missing evidence stops ingestion before any authority write.
Regression must cover successive productive fixture rounds on distinct scopes:
use the previous staged cut as the next base, verify cumulative readiness from
each portable bundle, and remove the originating receipt directory before the
final reassessment. This proves transport continuity, not fresh execution or
three productive real-world flywheel rounds.
Remote HEAD equality, exact business-row readback and unchanged repeat import
must be measured independently; a local bundle or a mirrored branch is not proof
of these postconditions. Preserve unrelated remote rows and never bootstrap an
old cut over a newer authority merely to make a smoke run succeed.

`scripts/run-maintainer-operation-receipt-smoke.sh` runs baseline, preparation,
child assessment, operation comparison and unchanged replay using the same
Rust binary locally and in the Rust contract Action, including snapshot staging
and rejection of no-change staging. CI uses immutable public
sample cuts and retains complete experiment outputs. This proves a repeatable
receipt-consumption path, not three productive full-system flywheel rounds,
fresh target execution or durable authority ingestion.

For compatibility, assessment without a receipt root retains historical
explicit-claim scoring and labels it `legacy-explicit-claim`. Strict assessment
labels `verified-receipt-content`. Do not compare their maturity counts as a
quality gain or regression. The semantic execution loop preserves its input
policy: strict cuts supply their portable `operation-evidence` root to the Rust
assessor and carry child-verified operation bytes through semantic staging and
sync export. This is not automatic migration of a legacy cut: first establish a
strict baseline and adapt its existing operation facts, then change the producer
and consumer together. Legacy gains prove no receipt-content qualification.

## Closed-loop maturity qualification

Scope maturity and system maturity are separate axes. Qualify a local flywheel
with three distinct bounded responsibilities at one pinned repository revision,
then retain three consecutive rounds. For each round retain the method/source
cut, parent assessment digest, accepted and rejected evidence, applicable
operation receipts, calibrated case outcomes, exact TableGit readback/export,
next-round objectives, wall time and human interventions. New facts or generated
prose alone do not count as improvement.

Measure whether missing dimensions decrease, meaningful wrong implementations
are rejected, alternative-valid implementations are accepted, and feedback
actually changes the next knowledge cut or analysis objectives. A no-change
replay should not advance authority. Missing tools or telemetry must be reported
as infrastructure/capability gaps rather than application failures. No eligible
work, no new facts or a successful Action is not a convergence verdict.

After local closure, repeat on a structurally different repository without
target-name branches or changes to the core acceptance rules. Keep reference
and mutation calibration distinct from assessed Agent runs. Do not claim that
better Skills improve Agent discrimination until a comparable before/after
cohort demonstrates it. Build-only evidence proves neither runtime behavior nor
performance; emulator power/thermal limits remain explicit instance facts.

## Maturity

1. `L0-discovered`: a scope exists but its exact identity or structural receipt
   is incomplete.
2. `L1-structural-ready`: revision, Git evidence, file partition,
   responsibility placeholder and structural inventory are valid.
3. `L2-semantic-ready`: bound facts prove responsibility, boundary and
   relations; source-bearing scopes also require behavior evidence.
4. `L3-maintenance-ready`: semantic readiness plus executable operation
   evidence.

The default repository-ready rule is intentionally strict: every declared scope
must reach L3. A future policy may distinguish non-critical scope thresholds,
but it must remain capability-based and revision-bound rather than naming a
repository.

## Loop

### Remote execution preflight

Resolve and verify the exact execution peer before preparing an isolated,
revision-pinned workspace. Do not update an old primary checkout merely to run
the next experiment. Fetch each immutable external input explicitly: fetching
the method branch does not imply that unrelated qualification commits exist in
the remote object database. Verify source and input identities before dispatch.

Resolve tool executables in the actual executor environment. An interactive
login shell's PATH is not evidence that a direct remote executor can spawn the
same command; use the verified absolute executable when those environments
differ. Preserve a failed spawn as infrastructure evidence, then correct the
invocation rather than count it as a target or Agent failure.

Check model configuration and credential presence without printing values.
A cached participant that starts, a successfully compiled gate, and receipt
replay do not prove model access or a productive Agent round. Keep preparation,
recorded-evidence replay, fresh target execution and feedback qualification
separate. Missing model configuration blocks Agent dispatch, not safe offline
qualification or implementation of the generic scheduler.

### Scope-exact semantic round gate

Use `--compare-semantic-round --before BEFORE --after AFTER --selected-scope ID
--output RESULT`, repeating selected scope for one to four distinct scopes.
The existing construction loop uses this Rust gate instead of treating equal
aggregate deltas as proof that the requested scopes advanced. A sibling gain
cannot substitute for a selected failure. Require exact parent SHA, contiguous
rounds, unchanged scope catalog and policy, totals reconciled to scope rows,
unchanged unselected rows, and complete selected L1-to-L2 closure. A scope may
reach L3 only by composing its unchanged prebound operation evidence with new
semantic dimensions; semantic rounds cannot introduce or replace operation
checks. Mixed source revisions, partial batches and forged totals reject before
result creation. Unchanged replay yields no-change, not a fresh authority round.

This gate compares independently produced assessments; it does not discover
semantic truth, authenticate Agent authorship or re-execute the target. Source
Blob validation, bounded Agent lifecycle and operator-owned candidate validation
must precede it. Legacy-policy results remain labeled legacy and must not be
presented as strict operation qualification.

Strict semantic stages use `stageKind: verified-semantic`, a mandatory
`inheritedReceipts` list and `verified-child-operation-facts-only` coverage.
Preserve the exact assessed scope/fact bytes, bind proposal scope IDs to the
gate's selected and advanced scopes, and retain baseline/result plus every
child-verified operation receipt. The existing writer validates portable hashes
and complete inherited coverage before connecting to TableGit. An unsupported
strict stage without this contract fails closed instead of discarding evidence.
Test mixed operation -> semantic -> operation cuts with arbitrary scope names,
then remove all earlier receipt/cut directories and independently reassess the
final portable cut. This verifies inter-ring continuity, not fresh Agent or
emulator execution or downstream case qualification.

### Evidence-driven next-round proposals

Use the Rust `--plan-next-round` mode to reassess exact scope/fact bytes with an
explicit receipt root before proposing the next bounded batch. Do not feed a
caller-authored ready verdict or legacy operation claims into scheduling.

```sh
agentlab-maintainer-skill-flywheel --plan-next-round \
  --scope-skills scopes.jsonl --program-facts facts.jsonl \
  --operation-receipts-root operation-evidence --round-index 1 \
  --available-lane semantic-refresh --available-lane operation-verification \
  --batch-size 4 --max-source-files 80 --output next-round-plan.json
```

For later assessment rounds supply their original parent assessment SHA. This
mode plans from the same cut; it does not append a round or count as a gain.
The report embeds the independent assessment and its canonical JSON-value SHA,
which is not the SHA of an independently formatted assessment file.
Every scope is accounted for as eligible, capability-blocked or knowledge-ready.
Structural gaps route to inventory repair, oversized pre-semantic scopes to
decomposition, missing semantic evidence to refresh, and missing or rejected
strict operation evidence to operation verification. Selection is deterministic
and bounded to one repository URL/ID, source revision, lane and analysis mode;
root contract and child source projections cannot share a batch.

Available lanes are explicit operator capability declarations, not proof that
an adapter has executed or an Agent has passed. No declarations means no
executable proposal, not convergence. A selected proposal still needs the
existing isolated execution, exact candidate validation, aggregate assessment
and revision-fenced persistence gates. Planning performs none of those writes.
When all scopes are knowledge-ready, require downstream calibrated cases,
execution, feedback into the next cut and cross-repository transfer. The plan
always reports `closedLoopQualified: false`: scope readiness alone cannot
certify the five-ring flywheel. Unsupported downstream evidence must remain an
explicit requirement, not be fabricated as a successful run.

1. Assess the structural catalog without program facts to freeze the baseline.
2. Bind revision-matched program facts and reassess.
3. Use the emitted gap codes as the next analysis objectives.
4. Refresh facts and Skills, append a child assessment using the parent report
   digest, and repeat.
5. Enter case generation only when the independent assessment says `ready`.

Throughput comes from bounded parallelism. Deterministically select at most
four eligible scopes from one repository and source revision, materialize the
union of their exact ownership selectors once, and give each scope an isolated
Agent request and proposal. Validate every proposal separately, then run one
aggregate assessment whose semantic-ready delta must equal the selected scope
count. One failure rejects the entire batch before TableGit mutation. Do not
combine repository-contract root analysis with child scopes, and do not let a
shared checkout imply shared evidence ownership.

Treat scope execution as independently retryable even though promotion is
atomic. Keep successful first-attempt proposals, retry only failed scopes once
in separate evidence directories, and feed the selected successful attempt for
each scope into the aggregate validator. A surviving failure rejects the whole
batch before assessment or TableGit mutation. Record the retried scope indices
in the loop receipt so long-tail recovery remains measurable. Bound each
attempt separately and disable nested participant retries in this lane; the
operator-level isolated retry is the sole retry authority.
Bound the lane-specific operator-proxy request below the general harness
default as well as bounding the Agent process. Otherwise a terminated Agent can
remain hidden behind the proxy's upstream-response retention window and defeat
the visible attempt budget. A socket timeout alone is insufficient because
partial streaming bytes reset its idle clock; retain an absolute monotonic
deadline for the whole upstream exchange.

Cancellation must remain evidence-bounded. Immediately before artifact
retention, delete only the known transient `workspace/source` symlinks under
the run root. This cleanup runs even after failure or cancellation so an
uploader cannot follow a live checkout and retain repository contents as Agent
evidence.

Remove deterministic discovery from the Agent loop. The operator verifies the
checkout HEAD and supplies every owned tracked path with its exact Blob OID and
byte count before the turn. The Agent must not spend calls rediscovering that
inventory and uses Git only for a direct dependency outside the scope packet.
This packet is an acceleration input, not semantic evidence by itself: accepted
claims still require proposal validation against the exact checkout. Read-only
TableGit projections for different tables may run concurrently only when every
query carries the same immutable revision; transactions remain single and
revision-fenced.

## Repository transfer contract

Treat one deeply analyzed repository as a calibration specimen, never as a
branch in the method. Promote an observation into this method layer only after
expressing it as a repository-independent invariant and covering it with a
fixture whose repository and paths are arbitrary. Keep framework commands,
module names, directory conventions and target-specific thresholds in the
instance layer.

Before each run, emit a convergence plan that accounts for every declared
scope as `eligible`, `already-advanced`, or `blocked`. A blocked scope must
carry a machine-readable reason and next action. In particular, large scopes
need decomposition, zero-source configuration/asset scopes need a specialist
analysis mode, root scopes need repository-contract analysis, and unreachable
evidence needs inventory repair. Zero eligible scopes is not convergence.

Select analysis mode from scope capability rather than repository identity:

- `source-behavior` proves responsibility, boundary, relations and behavior
  for a bounded source-bearing scope.
- `configuration-asset` proves responsibility, boundary and relations for
  manifests, resources and build metadata without inventing runtime behavior.
- `repository-contract` proves repository composition and root-level contracts
  from a root-only checkout projection and direct declarations without
  recursively materializing or reading all child scopes. Child source remains
  available only through a separately selected bounded scope.

All modes use the same revision, Blob, lineage and independent-assessment gates.
Large source scopes remain blocked until a child partition proves complete,
non-overlapping coverage and stable parent/child responsibility lineage.

Build that partition in two phases. First generate a reviewable plan against
one exact source revision and Tree OID. It must reproduce the parent's tracked
and source counts, cover every tracked path exactly once, report zero overlap,
and keep every leaf within the enforced source-file budget. Prefix selectors
cover directory-owned responsibilities; explicit file selectors preserve root
manifests and other files that do not belong to a child directory. Second, run
evidence rounds over the candidates to establish responsibility boundaries and
only then replace the aggregate parent in one atomic catalog update. Directory
shape is a safe structural partition, not semantic proof: reviewers may merge
candidate leaves when exact evidence proves one bounded responsibility, but
must rerun the same completeness and overlap checks. Until that review and
atomic rewrite finish, the parent remains blocked and no generated leaf is a
published Maintainer Skill.

A semantic review is itself machine-verifiable. It assigns every structural
leaf to exactly one proposed responsibility, retains the exact selectors and
file-set digest, cites multiple owned source Blobs, and rechecks the per-Agent
source budget after grouping. A review may reduce mechanical directory leaves
into fewer coherent responsibilities. If a reviewed responsibility owns
multiple disjoint prefixes or exact-file sets, those selectors are the
ownership authority for fact binding, Agent checkout projection, candidate
path validation, materialization and coverage verification. `pathBoundary` is
only a human navigation anchor. Generate a complete replacement catalog with
an exclusive atomic write before requesting the separate authoritative
TableGit transaction. The transaction must combine row-version-fenced parent
deletes and reviewed child inserts, then export the exact committed revision.
After export, regenerate derived catalog summaries from the exported rows and
verify repository identity plus tracked/source/code/test coverage before
publication. A stale pre-transaction count or digest is a failed export even
when the TableGit transaction itself succeeded.
Regenerate the independent assessment from the candidate catalog first; never
carry forward the aggregate parents' maturity by assumption. A shared ancestor is not an acceptable approximation
because it would silently reclaim sibling files.

Agent budgets are execution contracts, not prompt advice. The operator must
enforce wall time and tool-call limits, retain partial native events on breach,
and bind actual counts and the limit into the round receipt. A proposal created
outside those limits cannot advance the knowledge cut.

The operator-owned model gateway must also enforce an absolute upstream
deadline independently of HTTP header and SSE framing. Bound response-header
acquisition as total elapsed time, then read and forward the body in available
chunks while checking the same deadline between chunks; accumulate a separate
buffer to recognize complete semantic lines. Idle socket timeouts and
line-oriented reads do not satisfy this contract because periodic partial
header bytes or one unterminated body line can stay alive indefinitely. Test
both failure modes directly and retain a receipt that distinguishes the expiry
phase from EOF and semantic completion.

Precomputed source context must be bounded before it is computed, not merely
filtered afterward. Derive Git pathspecs from each scope's prefix and exact-file
ownership selectors and query only those paths. For a root-only repository
contract query the root tree non-recursively. Running a recursive, size-bearing
whole-tree inventory independently for every parallel Agent converts context
optimization into object-database contention and can consume the entire Agent
budget before a prompt is dispatched. Exact tracked-file reconciliation remains
mandatory for every narrowed query.

Separate semantic authorship from proposal persistence. Require the Agent's
final response to be exactly one JSON object and forbid Agent-owned file writes.
The operator parses that response without extracting from prose or repairing
fences, validates the complete schema and exact revision-bound Blob evidence,
and only then writes the proposal artifact. Invalid final output fails only that
scope attempt and may use the one isolated retry; it never reaches the aggregate
assessment or TableGit. A model thinking through a valid contract but forgetting
to create a file is an orchestration defect, not a reason to rerun repository
discovery or loosen the evidence standard.
Keep that JSON packet small enough to finish reliably: require one bounded
contract, exactly three representative revision-bound Blob citations and exactly
two concrete limitations. More cited files are not stronger proof once the four
required dimensions are grounded; they increase truncation risk and confuse
scope understanding with exhaustive summarization. Apply the same hard text and
cardinality limits in the validator rather than relying on prompt wording.
When a completed semantic turn leaves only thinking, malformed JSON, or a
proposal rejected by this validator, permit one format-only continuation in the
same model session. It receives the exact validation error, may not inspect the
repository or invoke tools, uses no provider reasoning, targets the middle of
each allowed size range, and must emit the compact JSON directly. Aggregate both
turns' duration and tool counts into one attempt receipt. Do not rerun source
discovery for a serialization defect; if finalization still fails, the normal
single isolated scope retry remains the only semantic retry authority.
Set prose limits from the serialized envelope rather than intuition. With
exactly three Blob citations and two bounded limitations, an interpretation up
to 1800 Unicode characters still keeps the proposal in a small transport-safe
envelope and avoids wasting a semantic retry on harmless compression variance.

The semantic turn is a bounded evidence sample, not a file census. Start from
the scope's precomputed evidence anchors, add only direct siblings or
dependencies needed for uncovered dimensions, and batch related reads into one
tool call. A small prompt budget drives behavior; a larger enforced ceiling is
only a runaway guard and must not be described as the available budget.

The durable round receipt binds source and method revisions, parent assessment,
scope-selection policy, eligible and blocked counts, Agent execution counts,
hard-gate decision, TableGit transaction, SkillsGit materialization and the
downstream shadow outcome. TableGit updates remain atomic; a failed Agent,
budget breach, invalid schema or failed hard gate writes no knowledge rows.

Maturity dimensions compose regardless of arrival order. If operation evidence
is already bound to an L1 scope, closing its semantic dimensions may make the
same independent assessment report it as L3. Accept at most one such L3 delta
for the selected scope; do not reject it as automatic promotion. Case
publication and benchmark promotion remain separate downstream decisions.

Do not treat a higher number of prose fields as progress. A round advances only
when a missing evidence dimension closes, a stale or contradictory binding is
removed, or a scope advances maturity with revision-bound evidence.
