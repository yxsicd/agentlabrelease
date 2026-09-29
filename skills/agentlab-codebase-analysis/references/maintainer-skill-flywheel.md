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
repository or invoke tools, and must emit the compact JSON directly. Aggregate
both turns' duration and tool counts into one attempt receipt. Do not rerun
source discovery for a serialization defect; if finalization still fails, the
normal single isolated scope retry remains the only semantic retry authority.

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
