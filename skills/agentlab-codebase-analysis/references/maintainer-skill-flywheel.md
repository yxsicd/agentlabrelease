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

Do not treat a higher number of prose fields as progress. A round advances only
when a missing evidence dimension closes, a stale or contradictory binding is
removed, or a scope advances maturity with revision-bound evidence.
