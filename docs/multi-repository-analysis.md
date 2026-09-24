# Multi-repository program analysis and difficulty discovery

AgentLab can build one revision-fenced program graph from multiple Git
repositories without assuming that a task belongs to a fixed monorepo. The
input is explicit and local checkouts are transport only: committed objects at
the declared revisions are authority.

## Input contract

```json
{
  "schema": "agentlab.multi_repo_manifest.v1",
  "repositories": [
    {
      "id": "application",
      "repository": "https://example.invalid/application.git",
      "root": "/checkouts/application",
      "revision": "1111111111111111111111111111111111111111"
    },
    {
      "id": "contracts",
      "repository": "https://example.invalid/contracts.git",
      "root": "/checkouts/contracts",
      "revision": "2222222222222222222222222222222222222222"
    }
  ],
  "moduleBindings": {
    "@example/contracts": {
      "repositoryId": "contracts",
      "path": "src/contracts.ts"
    }
  }
}
```

The analyzer rejects fewer than two repositories, symbolic revisions, duplicate
IDs, missing commits, missing binding targets and bindings to unsupported file
types. `root` is deliberately excluded from `sourceSetSha256`; repository
identity, exact revision and module bindings form the portable source-set
identity.

Run:

```sh
cargo run --locked -p agentlab_code_analysis \
  --bin agentlab-multi-repo-analysis -- \
  /path/to/manifest.json /path/to/evidence
```

## Evidence contract

The output directory contains:

- `workspace_facts.jsonl`: repository-namespaced syntax facts plus resolved
  module-dependency edges. Every edge binds both source and target source
  identities.
- `difficulty_candidates.json`: unresolved module boundaries and recursively
  derived reverse-dependency impact surfaces. It binds the portable source-set
  digest, not local checkout paths. `automaticPromotion` is false.
- `multi_repo_analysis.json`: analyzer/grammar identity, exact repository cuts,
  counts and SHA-256 digests for both evidence files.

Resolution is intentionally bounded. Relative `.ets`/`.ts` imports resolve from
committed file paths. Non-relative imports resolve only through
`moduleBindings`. Compiler aliases, package-manager state, dynamic imports,
types, call targets and dataflow remain unresolved unless a later analyzer
provides independently verified evidence.

## From difficulty to a valid evaluation case

A recursive impact candidate describes where a change may be discriminating;
it is not yet a task. Promotion requires all of the following:

1. freeze every participating repository revision and the source-set digest;
2. define the intended cross-repository behavior and permitted edit scope;
3. provide repository-specific build or static checks;
4. provide an independent behavior oracle covering the affected boundary;
5. calibrate reference and known-failing variants before ranking Agent attempts.

This separation prevents a large dependency cone or an unresolved import from
being mistaken for a useful benchmark merely because it looks difficult.

The executable [multi-repository case fixture](../examples/multi-repo-case/README.md)
implements the next step: exact affected-source materialization, a captured and
replaceable construction participant, a non-promoted proposal, digest-bound
deterministic pre-review quality report, explicit review, independent runtime
Oracle, four calibration variants, frozen task output and TableGit persistence.
Dependency evidence can derive edit scope and construction risks; neither it,
a lexical quality gate nor an Agent draft establishes semantic truth.

For a frozen case whose reviewed implementation target is Harmony, the next
boundary is now executable rather than implicit. The
[`run-harmony-evaluation-case.py`](../scripts/run-harmony-evaluation-case.py)
bridge accepts only a `frozen-calibrated` multi-repository case plus an
independent `agentlab.harmony_case_build_receipt.v1`. That receipt must bind the
exact case digest, source-set digest, every repository revision, source
materialization digest, build-tool digest and resulting HAP digest. The bridge
then binds those identities to the exact emulator runner, UI Oracle,
environment, performance policy and workload before executing the HAP.

This does not turn an arbitrary multi-repository case into a Harmony case and
does not manufacture build authority. A build receipt must come from an
independent Harmony materialization/build step over the reviewed source set.
Missing or mismatched lineage fails before emulator launch; result or SmartPerf
identity drift retains the failed execution and cannot promote the case.

The corresponding build-side producer is
[`build-harmony-evaluation-artifact.py`](../scripts/build-harmony-evaluation-artifact.py).
It never copies a checkout's current working tree. For every source in the
frozen case, the plan maps a committed directory from the exact revision into a
fresh project workspace. The producer checks the exact `origin`, resolves the
40-character commit, reads only Git tree/blob objects, rejects symlinks,
submodules, traversal and target collisions, then invokes one SHA-bound build
executable without a shell. This makes uncommitted or generated checkout bytes
ineligible for the source lineage.

On success it retains `artifact.hap`, `source-materialization.json`, build logs
and `build-receipt.json`; the disposable workspace is removed because the
pinned repositories plus content manifest are the reproducible authority. A
failure retains the partial workspace and logs. The build receipt is the input
required by the emulator bridge, not an automatic case-promotion decision.

## Close assessed failures into the next analysis cut

The trusted assessed campaign keeps the frozen case unchanged, runs fresh trials
for two exact participant/model identities, and scores only infrastructure-valid
independent verdicts. `derive-assessment-feedback.py` then verifies the frozen
case, collected evidence references, discrimination report and original decision
packages before grouping failure observations by stage and mechanism. Oracle
failure, edit-scope drift, and their intersection stay distinct.

The output is `agentlab.assessment_feedback_candidates.v1`. It binds the exact
source-set digest, method revision and canonical digests of the case, collected
input and score report. These rows are evidence for recursive difficulty
discovery, not automatically generated benchmark truth: infrastructure failures
are excluded, every candidate remains non-ready, and promotion requires a new
maintainer-adjudicated source/analysis cut plus independent calibration. The
flywheel transaction can persist the candidates into `difficulty_points` while
leaving the active `evaluation_cases` and reusable Skills untouched.
