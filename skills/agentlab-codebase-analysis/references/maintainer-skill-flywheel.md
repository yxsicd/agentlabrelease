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
Regenerate the independent assessment from the candidate catalog first; never
carry forward the aggregate parents' maturity by assumption. A shared ancestor is not an acceptable approximation
because it would silently reclaim sibling files.

Agent budgets are execution contracts, not prompt advice. The operator must
enforce wall time and tool-call limits, retain partial native events on breach,
and bind actual counts and the limit into the round receipt. A proposal created
outside those limits cannot advance the knowledge cut.

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
