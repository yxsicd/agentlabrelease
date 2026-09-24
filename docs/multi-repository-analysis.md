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
