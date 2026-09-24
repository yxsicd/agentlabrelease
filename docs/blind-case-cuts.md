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

python3 scripts/build-blind-case-cut.py stage-participant \
  --cut /private/cuts/case-001 \
  --output /isolated-dispatch/case-001 \
  --receipt /operator-evidence/case-001-dispatch.json

python3 scripts/build-blind-case-cut.py validate-dispatch \
  --participant-root /isolated-dispatch/case-001 \
  --receipt /operator-evidence/case-001-dispatch.json
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

`stage-participant` makes a second immutable projection containing only the
participant manifest and its bound files. Its dispatch receipt must remain
outside that root. The receipt fixes the intended read-only mount target at
`/agentlab/case`. Copying and interface binding alone still report
`filesystemIsolationQualified=false`. The assessed campaign can now add an
independent runtime postcondition: each Pi turn runs in a Docker container with
an immutable image, read-only root, private PID namespace, all capabilities
dropped and exactly four bind mounts—Workspace RW, participant state RW, Pi
runtime RO and `/agentlab/case` RO. Both participant and relay run as the frozen
non-root operator UID/GID; root-owned assessment launch fails closed. The
operator Gateway proxy and external key
remain in the host adapter. A separate no-credential TCP relay joins both a
Docker-internal participant network and the ordinary bridge; the participant
joins only the internal network and can address only that fixed relay. The host
proxy requires a per-attempt local token that is distinct from the external
Gateway key. Raw container/network `docker inspect` evidence and positive/negative
runtime probes stay outside every participant mount; an independent validator
rejects extra mounts, changed identities, host PID access, writable rootfs,
Docker socket exposure, extra participant networks, non-internal topology or
credential environment names before qualifying filesystem, external-credential
and network-egress isolation.

The runtime probe must reach the token-protected operator health route through
the relay while a direct external TCP connection is blocked. The cut still
lacks contamination and semantic-leak qualification, so
`blindAssessmentQualified` remains false. Host-process and mock runs without
validated runtime receipts continue to report filesystem isolation false.

## Independent review and adjudication

The release also provides an immutable multi-reviewer chain for the judgments
that cannot be established by container topology alone. First freeze an exact
request from the already-built cut:

```bash
python3 scripts/review-blind-case-cut.py prepare \
  --cut /private/cuts/case-001 \
  --constructor case-author \
  --output /operator-evidence/case-001-review-request.json
```

Each recorded reviewer must be different from the recorded constructor and must bind the
exact request digest, reviewer-supplied evidence digests and a verdict for all four
dimensions: semantic leakage, contamination risk, specification fairness and
Oracle breadth. Verdicts are `qualified`, `rejected` or `unknown`; omitted or
unknown evidence never passes.

```bash
python3 scripts/review-blind-case-cut.py decide \
  --request /operator-evidence/case-001-review-request.json \
  --expected-request-sha256 '<reviewed digest>' \
  --reviewer reviewer-a \
  --semantic-leakage qualified \
  --contamination-risk qualified \
  --specification-fairness qualified \
  --oracle-breadth qualified \
  --evidence-sha256 '<retained evidence digest>' \
  --rationale '<independent rationale>' \
  --output /operator-evidence/case-001-review-a.json
```

`adjudicate` requires at least two unique recorded reviewer identities, retains
every decision digest, and reports per-dimension unanimity plus an exact
disagreement rate. Review consensus qualifies only when every recorded reviewer
marks every dimension qualified. Any rejection, unknown or disagreement fails
closed.

```bash
python3 scripts/review-blind-case-cut.py adjudicate \
  --cut /private/cuts/case-001 \
  --request /operator-evidence/case-001-review-request.json \
  --review /operator-evidence/case-001-review-a.json \
  --review /operator-evidence/case-001-review-b.json \
  --output /operator-evidence/case-001-adjudication.json
```

The CLI can prove exact lineage, distinct recorded identifiers and consensus;
it cannot authenticate that those identifiers belong to different people.
Every v1 adjudication therefore keeps
`reviewerIdentityAuthenticationQualified=false`,
`blindPilotReviewQualified=false`,
`modelTrainingExclusionQualified=false`,
`eligibleForUnseenAgentDiscrimination=false` and `automaticPromotion=false`.
Its next gate is authenticated reviewer identity plus artifact provenance. The
public fixture has regression coverage for the protocol but no real review
decisions, so its current assessment qualification remains unchanged.

Two trusted-main manual workflows implement that next gate without accepting a
self-declared identity as authority:

1. `blind-case-independent-review.yml` recovers an exact successful frozen-case
   run, reconstructs the same request, rejects the recorded constructor as the
   reviewer, binds `github.actor` to the decision, and signs the decision with a
   GitHub OIDC/Sigstore artifact attestation.
2. `blind-case-review-adjudication.yml` requires two different review run IDs,
   downloads their artifacts, verifies each run through the GitHub API, and runs
   `gh attestation verify` against the exact repository, signer workflow, main
   ref and source commit. It then checks that the two authenticated GitHub
   accounts differ and signs the resulting adjudication itself.

The authenticated adjudication retains the raw run metadata, attestation
verification output, decisions and provenance receipts. It may set
`reviewerIdentityAuthenticationQualified=true` and
`blindPilotReviewQualified=true` only when all four review dimensions reached
unanimous qualified consensus. This authenticates distinct GitHub accounts and
workflow provenance, not real-world legal identity or model-training exclusion;
`eligibleForUnseenAgentDiscrimination` therefore remains false.

These workflows become dispatchable only after the workflow files are present
on the repository default branch. Until an actual pair of trusted-main reviews
and the final attestation are produced and independently verified, this is an
implemented protocol rather than completed review evidence.

The assessed-campaign workflow accepts that adjudication by run ID. Before any
model attempt it downloads the exact bundle and re-verifies the final
attestation against the adjudication workflow, repository, main ref, source
commit and GitHub-hosted runner policy. The campaign artifact retains the raw
parsed verification statement together with the exact enforcement policy,
subject digest, workflow run/attempt and source revision. Each assessment
process repeats the online verification and reconstructs the internal
cut/request/decision/provenance lineage. `blindAssessmentQualified` becomes
true only when this
authenticated review boundary and all filesystem, external-credential and
network-egress runtime gates are true. The functional pass/fail verdict remains
separate from that boundary qualification.

## Population-level review evidence

One authenticated case is not evidence that a benchmark population is valid.
`scripts/summarize-blind-review-population.py` accepts a frozen manifest of at
least two adjudication workflow runs. Every listed bundle is recovered by exact
run ID, independently reverified online, and reconstructed before it enters the
denominator. A missing, invalid or identity-mismatched case fails the entire
report instead of being silently excluded after its outcome is known.

For every review dimension, the report retains qualified, rejected, unknown
and disagreement case counts, the exact denominator, the disagreement rate and
a 95% Wilson interval. It also records reviewer reuse across cases, exact case
membership, bundle evidence hashes and the raw final-attestation verification
for each member. `blind-review-population.yml` performs this operation on
trusted `main`, signs the exact report with GitHub OIDC provenance, and uploads
the manifest, report and raw verification evidence together.

The v1 manifest requires `declaredRepresentative=false`. The resulting report
always keeps `populationRepresentativenessQualified=false`,
`modelTrainingExclusionQualified=false` and
`eligibleForUnseenAgentDiscrimination=false`. Population representativeness
requires a later independent sampling-frame review; neither case count nor low
reviewer disagreement can establish it automatically. The public repository
currently contains protocol tests, not a completed real reviewed cohort.

## Evidence boundary

A structurally valid cut is eligible for a blind pilot only. It is not yet
eligible for an unseen-Agent discrimination claim. The receipt labels held-out
status as declaration-only; the builder cannot prove who previously accessed
the source or whether related bytes entered model training. That later gate
requires:

1. completed multi-reviewer semantic-leak review of the participant task and source;
2. completed contamination-risk review for the selected participant/model boundary;
3. independent specification, Oracle breadth and reference review;
4. frozen participant/model/environment identities and repeated valid trials;
5. a new maintenance cut after observing operational outcomes.

The public regression tests use synthetic bytes and prove only the packaging
and fail-closed validation contract. They are not held-out benchmark content.
