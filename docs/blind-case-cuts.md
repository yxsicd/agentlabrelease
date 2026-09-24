# Blind case cuts

AgentLab blind case cuts separate what an assessed participant may mount from
the grading authority used by the Harness. This is a packaging boundary, not a
claim that a case is fair, uncontaminated or maximally discriminating.

## Source layout

Prepare the source only inside a private maintenance workspace:

```text
case-source/
  case-source.json
  participant/
    task.md
    source-binding.json
  evaluator/
    oracle.ui
    reference.patch
    preservation.ui
```

`case-source.json` uses `agentlab.blind_case_source.v1`. It binds exact method
and source-set identities, SHA-256 inventories for both roots, participant-only
constraints, and a conservative freshness declaration. Participant file roles
are `task`, `source`, `context`, or `constraint`. Evaluator roles are `oracle`,
`reference`, `preservation`, or `review`.

The v1 builder deliberately requires:

- one participant task;
- at least one evaluator Oracle and reference implementation;
- no symlinks, path traversal, unbound files, digest drift, or byte-identical
  files across the two bundles;
- `participantAccessBeforeCut=false`;
- no claim that model-training exclusion is known;
- review-required contamination and semantic-leakage states.

## Build and validation

Build into a new path. Existing output is immutable and never overwritten:

```bash
python3 scripts/build-blind-case-cut.py build \
  --source /private/maintenance/case-source \
  --output /private/cuts/case-001

python3 scripts/build-blind-case-cut.py validate \
  --cut /private/cuts/case-001
```

The result has three siblings:

```text
case-001/
  participant/       # the only root mounted for the assessed Agent
  evaluator/         # mounted only for the independent evaluator
  cut-receipt.json   # binds both manifest and inventory digests
```

Never mount `case-001/` itself into the participant environment. The Harness
must mount only `participant/`; it retains `evaluator/` and `cut-receipt.json`
outside the participant filesystem. The evaluator manifest binds the exact
participant manifest digest, and the outer receipt binds both sides without
placing evaluator inventory or paths in the participant manifest.

## Evidence boundary

A structurally valid cut is eligible for a blind pilot only. It is not yet
eligible for an unseen-Agent discrimination claim. The receipt labels held-out
status as declaration-only; the builder cannot prove who previously accessed
the source or whether related bytes entered model training. That later gate
requires:

1. independent semantic-leak review of the participant task and source;
2. contamination review for the selected participant/model boundary;
3. independent specification, Oracle breadth and reference review;
4. frozen participant/model/environment identities and repeated valid trials;
5. a new maintenance cut after observing operational outcomes.

The public regression tests use synthetic bytes and prove only the packaging
and fail-closed validation contract. They are not held-out benchmark content.
