# Multi-repository program analysis and difficulty discovery

The design is informed by SWE-bench's hidden repair/preservation tests and
fresh evaluation environments, while explicitly addressing case validity,
contamination, multi-repository scope and device/performance feedback. See the
[SWE-bench strategy comparison](swe-bench-strategy-comparison.md) for the
adopted qualification model and current evidence boundary.

AgentLab can build one revision-fenced program graph from multiple Git
repositories without assuming that a task belongs to a fixed monorepo. The
input is explicit and local checkouts are transport only: committed objects at
the declared revisions are authority.

## Input contract

For a trusted-main run, the portable input is
`agentlab.multi_repo_source_spec.v1`: two to sixteen credential-free public
HTTPS repositories, exact 40-character commits, optional module bindings and
`automaticPromotion: false`. The `Multi-repository exact analysis` workflow
materializes those commits with Git's non-file/non-SSH protocol restrictions,
bounded retries and a metadata-first `blob:none` partial clone. It does not accept a
branch, tag, local path, embedded credential, query string or private IP
literal.

The analyzer then asks Git for only the pinned ArkTS/TypeScript blobs it
consumes. Git verifies them against the commit's tree object IDs and retains
each successful fetch in the local object database. A transport interruption
can therefore resume without redownloading a monolithic source pack or
weakening the exact-revision fence.

Committed blob queries select the strongest protocol the installed Git
supports. Git versions with `cat-file --batch -z` receive NUL-terminated
revision/path queries. Older versions receive line-terminated batches for
ordinary paths, while the uncommon path containing an embedded newline is read
as one argv-bound `cat-file blob` request. Response headers and post-blob
delimiters remain newline-terminated in both batch modes. This preserves
unusual committed paths without requiring either `-z` or the newer uppercase
`-Z` protocol on the older Git shipped on the hwlinux execution host.

The compatibility path was exercised on hwlinux with Git 2.34.1 at AgentLab
commit `0ce25f9`. The retained two-repository Harmony input at
`/home/huawei/.agentlab/evidence/harmony-assessed-ohostest-aa799f9/manifest.json`
completed with source-set SHA-256
`7f96da1f672e7e9286e759cc6c95f29f4b9cc1b50987a53e0d1d465d0c04a8d8`,
167 facts and 22 difficulty candidates. The resulting analysis and candidate
artifacts have SHA-256 digests
`dfea0f4e680f139ab6e483078632dab5f998614054e755e9c42db7b749d58735`
and `a2c220246694376ba07b4f6a3cb63d4173f6c956de86dd902f311cbf3dceb9ad`.

Before analysis, the workflow re-fetches two bounded Git blob-size tiers (8 KiB
and 32 KiB). This coalesces the large population of small source files into a
few resumable packs. Any larger source blobs remain explicit in the transport
receipt and are fetched by Git's promisor path when the analyzer requests them.
Git object IDs remain authority throughout; no provider-specific raw-file API
is trusted.

The workflow converts that portable specification into the analyzer manifest
below. Local absolute roots are transport fields only. It retains the source
specification, manifest, complete native evidence and an
`agentlab.multi_repo_analysis_run.v1` receipt that binds their SHA-256 digests,
the source-set identity, counts and exact AgentLab method revision. A later
candidate-cohort workflow accepts only a successful trusted-main analysis run
ID plus the expected analysis-run digest, then revalidates the downloaded
evidence before sampling.

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
  --cache-dir /path/to/rebuildable-ast-cache \
  --cache-components \
  /path/to/manifest.json /path/to/evidence
```

AST extraction uses a bounded worker pool. By default it selects the available
parallelism capped at eight workers; operators may select an explicit value
from 1 through 64 with `--jobs N` before the manifest path. Results are joined
in the original repository/path order, so worker scheduling cannot alter any
evidence bytes or digest. The integration suite compares every emitted
artifact between one-worker and four-worker executions.

`--cache-dir PATH` enables exact source-set bundle reuse. Add
`--cache-components` to retain revision-fenced per-repository projections, or
`--cache-files` to opt into revision-safe per-file AST reuse as well. File entries are
content-addressed by the analyzer implementation digest, grammar digest,
normalized source path and SHA-256 of the exact committed blob. Rows stored in
the file cache exclude `sourceRevision`; a hit rematerializes that field from
the currently declared 40-character revision before graph construction. This
permits an unchanged file to survive a repository revision change without
confusing the two source cuts. Entry schema, key, payload digest, parser inputs
and parse-file blob digest are checked before reuse. An absent, malformed or
inconsistent entry is a miss and is rebuilt.

A repository projection is keyed by analyzer and grammar digests plus the
repository ID, repository URL and exact commit. It stores sorted base facts
separately from compact module-reference, call and file-index projections.
Module resolution, dependency edges and difficulty candidates are always
rebuilt against the current complete source set and manifest bindings. Thus a
one-repository revision change can reuse every unchanged repository without
carrying stale cross-repository conclusions forward. Fact rows are merged by
ID through a bounded-memory streaming writer; a projection's fact count and
content digest are checked before it can contribute output. Checkout roots are
excluded, so relocating an exact object database preserves reuse.

The same cache also keeps a source-set bundle keyed by analyzer and grammar
digests plus the portable repository revisions and module bindings. An exact
bundle hit restores the three digest-checked semantic artifacts without AST or
graph reconstruction, then rematerializes `multi_repo_analysis.json` with the
current local manifest digest. Consequently an unchanged aggregate release can
reuse prior analysis even when its checkout roots move, while a changed source
set falls back to repository projections when enabled, then to parsing for
every changed or absent projection. The finer per-file cache remains an
independent opt-in fallback inside a repository miss.

The cache is deliberately outside the evidence contract. It can be deleted at
any time, it is never uploaded as analysis evidence, and it never replaces Git
objects as source authority. Enabling it writes one
`agentlab.analysis_cache_execution.v1` report to stderr with hit, miss, invalid
entry and write counts for all three layers; cache-local state therefore cannot
change any of the four authority artifact bytes. The trusted-main workflow
persists the bundle and repository-projection layers. It leaves the
finer-grained file cache disabled until that layer demonstrates a positive
real-source wall-time result, and retains only the execution report alongside
the source and analysis evidence.

The retained current-method real-source benchmark records one fresh-process
trial per profile on an Apple M4 with a warm Git object database. Across 12,711
files and 31,771,940 committed source bytes, one, four and eight workers took
20.16 s, 15.27 s and 14.12 s respectively. The eight-worker run processed
2.146 source MiB/s (444.4 ns/source byte), a 1.43x wall-time speedup, while all
four evidence artifacts retained identical SHA-256 digests. This is a
machine-local preliminary result without variance or cold-network claims; the
structured record is `release/qualifications/harmony-real-multi-repo-34661ff/parallel-analysis-benchmark.json`.

The exact source-set bundle cache was measured separately on the same 12,711
files, host class and warm Git object database. One fresh-process bundle miss
with eight workers took 16.76 seconds and populated the digest-checked bundle;
the next fresh-process exact hit took 2.31 seconds, a 7.26x speedup, while all
four authority artifact digests stayed byte-identical. The cache contained five
files and 447,965,281 logical bytes. This path used same-filesystem hard links
after streaming digest validation; copy fallback, GitHub Actions restore,
changed-revision file-cache behavior, variance and cross-host performance are
not qualified by that single trial. The structured record is
`release/qualifications/harmony-real-multi-repo-34661ff/aggregate-cache-benchmark.json`.

The repository-projection layer was then measured on an exact changed-revision
pair: the 556-file code-workshop repository changed while the 12,155-file
guide-snippets repository stayed at its prior commit. One fresh component run
hit the unchanged repository and rebuilt the changed one in 15.92 seconds,
versus 21.08 seconds for the uncached control (1.32x wall speedup). User CPU
fell from 19.04 to 9.31 seconds and maximum resident size from 3,038,134,272 to
821,870,592 bytes (72.9% lower). All four authority artifacts were
byte-identical. The initial two-repository component population took 23.75
seconds, so exact bundle reuse remains the preferred unchanged-source-set path.
This is one same-filesystem paired trial, not a population or cross-host claim;
cache eviction and GitHub cache transport remain unqualified. The structured
record is
`release/qualifications/harmony-real-multi-repo-34661ff/component-cache-benchmark.json`.

## Evidence contract

The output directory contains:

- `workspace_facts.jsonl`: repository-namespaced syntax facts plus resolved
  module-dependency edges. Every edge binds both source and target source
  identities.
- `unsupported_sources.jsonl`: exact path, source identity, byte digest and
  rejection location for committed `.ets`/`.ts` files that are not UTF-8.
  These exclusions do not abort the remaining source set and are never parsed
  through a lossy conversion.
- `difficulty_candidates.json`: unresolved module boundaries and recursively
  derived reverse-dependency impact surfaces. It also clusters a non-relative
  unresolved module imported from two or more repositories into a
  `shared-external-module-contract` candidate. This represents a possible
  shared platform/package contract change surface, not a claim that the
  repositories depend on one another. It binds the portable source-set digest,
  not local checkout paths. `automaticPromotion` is false.
- A `shared-external-api-call-contract` candidate is narrower: the analyzer
  binds a named or aliased import to a syntactic call target in the same file,
  normalizes the local alias back to the exported symbol, and requires the same
  module/export/call tuple in at least two repositories. Module-reference and
  call facts are both retained as evidence. This is call-site localization,
  not type resolution or proof that the calls have identical lifecycle needs.
- A `shared-domain-identifier-contract` candidate covers repositories that do
  not share an import graph. Interface/class properties and member accesses
  become explicit AST facts; a candidate requires exact equality after
  deterministic CamelCase/separator tokenization, at least two meaningful
  tokens, and observations in at least two pinned repositories. Every
  observation retains its fact ID, original spelling, repository and path.
  This is conservative lexical localization for semantic review, not proof
  that the types, roles or behaviors are equivalent.
- `multi_repo_analysis.json`: analyzer/grammar identity, exact repository cuts,
  counts and SHA-256 digests for both evidence files.

Resolution is intentionally bounded. Relative `.ets`/`.ts` imports resolve from
committed file paths. Non-relative imports resolve only through
`moduleBindings`. Compiler aliases, package-manager state, dynamic imports,
types, call targets and dataflow remain unresolved unless a later analyzer
provides independently verified evidence.

Shared external-module candidates are grounded in exact import facts but remain
non-ready. Qualification must independently establish the external contract's
version and semantics, repository-specific builds, and a cross-repository
behavior Oracle. This supports real repositories that consume the same Harmony
platform API without inventing a source-to-source import edge. Their
`affectedFiles` identity is unique by repository and path even when one file
contains several imports from the same module; every distinct import fact stays
in `evidenceIds`.

Shared external API-call candidates remain non-ready too. Before seed
extraction, a maintainer must establish the API version and behavioral
contract, lifecycle/error semantics, repository-specific repair and
preservation checks, and a cross-repository Oracle. Alias normalization avoids
splitting the same API merely because repositories use different local names;
namespace/default imports and dynamic property access retain their explicit
coverage limitations.

Shared domain-identifier candidates are also non-ready. A maintainer must
adjudicate role and type compatibility before repository-specific builds and a
cross-repository behavior Oracle can qualify the candidate. Single-token
matches never create this relation, and exact matching deliberately misses
synonyms; later semantic stages may enrich that boundary without weakening the
revision-fenced evidence.

## Predeclare a candidate cohort before construction

Candidate discovery is not case qualification, and choosing one promising row
after seeing participant outcomes would bias the benchmark. The trusted-main
cohort workflow therefore freezes the sampling decision first:

1. `multi-repo-analysis-run.py` first verifies the portable source
   specification, runner-local manifest and every native analyzer evidence
   digest from a separately retained exact-analysis run.
2. `propose-multi-repo-candidate-cohort.py` binds the exact difficulty bytes,
   source-set digest and method revision; retains the eligible denominator and
   every exclusion; and reports relation, repository-count and recursive-depth
   strata. It also reports when a broad module-contract candidate has one or
   more API-call candidates over an equal or smaller file set. These remain in
   the denominator, but the reviewer is told to prefer the narrower evidence
   unless the proposed task genuinely requires module-wide semantics. The
   artifact binds `methodRevision` for the source analysis and a separate
   `proposalMethodRevision` for the sampling/advisory algorithm; both survive
   review, cohort compilation and candidate selection.
3. `review-multi-repo-candidate-cohort.py decide` requires the exact proposal
   digest, at least two eligible IDs, all risk acknowledgements and a reviewer
   rationale. `compile` creates an immutable, non-representative cohort.
4. `select-multi-repo-cohort-candidate.py` permits construction of one reviewed
   member only when the cohort digest and reproduced difficulty bytes match.
5. For an API-call-specific member,
   `multi-repo-candidate-review-packet.yml` recovers that exact reviewed cohort,
   revalidates the original analysis run, rematerializes every public repository
   at its pinned commit, selects the member again and builds source-localized
   semantic evidence. The packet separately binds the original analysis
   manifest and the runner-local materialized manifest, so stale absolute paths
   cannot masquerade as portable source evidence.

The proposal and review workflows carry no model Gateway credential. Model
construction is a later run per selected member. The cohort does not promote a
difficulty point, guarantee that every selected candidate will yield a fair
case, or authorize population claims. Failed specification, Oracle,
calibration, blind-review and runtime cases remain visible as yield losses
rather than being silently removed from the denominator.

Trusted-main case freezing now embeds the exact selection, cohort digest,
candidate digest, difficulty digest and method revision only in evaluator
lineage. The participant projection does not receive that metadata. The v2
blind-review population reporter recovers the attested evaluator case, rejects
candidate substitution or duplicate use, and carries all selected but
unadjudicated candidate IDs into the case-yield denominator. The v2 Agent suite
scorecard preserves that denominator alongside model discrimination evidence.
It now distinguishes extreme weak/strong separation from full capability
resolution: the latter requires a predeclared weak/middle/strong-or-richer
ordering and separately separated Wilson intervals for every adjacent tier.
The assessed campaign now freezes three to eight unique participant/model
profiles, route and trial count in a signed pre-outcome plan; the v3 suite
derives its order from that evidence instead of accepting a post-hoc order.
Harmony imports verify and re-attest the unchanged plan. Two extreme profiles
may still qualify the historical base measurement, but v1/v2 evidence and any
unsigned ordering can no longer be reported as resolving the intermediate
capability frontier.

Candidate adjudication yield is not case qualification yield. Every newly
generated analyzer-backed case now carries an `agentlab.case_source.v1` record
that classifies it as `derived / semantic-program-analysis` and binds the exact
difficulty evidence plus candidate digest. Its separate
`agentlab.case_qualification_receipt.v1` binds the source record, calibration
summary and qualification matrix while keeping semantic review, functional
calibration, device, performance and freshness gates distinct. Functional
qualification requires both review and calibration; device and performance are
separate pending gates and freshness remains unqualified/unknown. The receipt
therefore cannot turn a static frozen case into an end-to-end Harmony case.

`summarize-case-supply.py` joins an exact reviewed cohort to zero or more frozen
cases and reports three non-interchangeable yields: frozen-case, functional-
qualified and end-to-end-qualified. It reports each source lane and strategy as
a separate stratum and explicitly lists unobserved planned lanes.

The natural-source entry is now executable rather than only a planned enum.
`import-natural-case-source.py` accepts either a historical repair or an
operator-reported failure, but only after binding an exact multi-repository
source set and content-addressed evidence. Historical repairs require an Issue
URL, exact fix revision and repair URL for every affected repository. Operator
failures require an incident identity, observation time, reporter authority,
failure report and reproduction evidence. Both forms require explicit observed-
failure and preservation check identities. The importer emits an ordinary
`agentlab.difficulty_candidates.v2` member with `caseReady=false`; source
evidence is not qualification evidence and never auto-promotes a case.

`merge-case-candidate-sources.py` can combine natural and derived candidate
files only when their exact source-set digest, repository revisions and module
bindings agree. The mixed population then uses the same predeclared cohort,
review, one-member selection, construction, calibration and freeze path. A
natural candidate cannot bypass prompt-fairness, alternative-valid,
meaningful-wrong, freshness, device or performance gates. Current tests prove
this fail-closed mechanism and a mixed-source cohort fixture; they do not prove
that a real fresh natural case has been imported or qualified.

Public GitHub history now also has a trusted-main collection boundary.
`github-natural-repair-source.yml` accepts only an explicit
`agentlab.github_natural_repair_spec.v1` record. The collector permits only
credential-free `github.com` Issue and pull-request URLs and uses the GitHub API
token only against `api.github.com`. Every repository must have one merged PR;
its declared fix revision and PR base must equal the exact repair and source
revisions. Declared affected and test paths must occur in the retained patch.
The workflow keeps the selected public Issue fields, complete repair patches,
test-only patch sections, normalized manifest, candidate source and a
digest-bound collection receipt. A second validation pass reconstructs the
candidate from the retained manifest and evidence before artifact upload.

That artifact is still source evidence, not a reviewed cohort or qualified
case. `mixed-case-candidate-cohort.yml` now joins one exact analyzer artifact
and one collected natural artifact only after independently checking both
trusted-main workflow identities, requested receipt digests, source method
revisions and the common pinned source set. `candidate-source-bundle.py`
reconstructs the two source receipts and the merged candidate file, then binds
both run IDs and metadata digests into a non-promoting receipt. The existing
cohort reviewer accepts this exact workflow in addition to the analyzer-only
proposal and revalidates the bundle before a human selection can be compiled.
This closes the local and workflow mechanism; it has not yet executed from
merged trusted `main`, and no fresh natural record has completed independent
review or qualification.

The first real two-repository source qualification is retained at
`release/qualifications/harmony-real-multi-repo-34661ff/summary.json`. It binds
12,711 analyzed files, 881,650 text lines, 404,308 facts, 22 shared-contract
clusters, two audited non-UTF-8 exclusions and the exact evidence digests. Its
status is `analysis-qualified-case-review-required`: the clusters are discovery
evidence, not evaluation cases.

The same source set has now been reproduced locally with the current analyzer
at method revision `6adbbf6a7bc2d4016fe338396737a2ff4b9519d0`. The digest-bound
run produced 404,308 facts and 19,374 candidates; 97 candidates met the
cross-repository sampling-frame rules (22 module-contract and 75 API-call
members). Nineteen module rows point to more specific API-call evidence, while
three have no narrower API candidate. A six-member specificity-aware proposal
was frozen before case construction or participant outcomes at
`release/qualifications/harmony-real-multi-repo-34661ff/current-method-proposal.json`.
It remains non-representative and review-required. Because the workflow exists
only on this unmerged branch, this is not yet a trusted-main run or an
independent cohort decision.

After cohort review, construction input is now a second predeclared boundary.
Inputs may be supplied directly by an operator or drafted by the credential-
bearing `Multi-repository calibration authoring` workflow. The latter gives an
independent evaluator model only the exact candidate files, reviewed API
localization when applicable, and relevant program facts. It must produce a
source surface, Oracle contract, exact Oracle/driver bytes, reference solution,
structurally different alternative-valid solution and meaningful wrong
variants. The resulting `agentlab.multi_repo_calibration_authoring_receipt.v1`
binds every source and draft byte, participant identity, method revision and
model capture, remains `review-required`, and explicitly records machine-
authored executable, product-truth, reference and discrimination risks.

`Multi-repository construction contract proposal` binds one exact cohort member
to either those exact authored bytes or a direct operator-owned source surface
and Oracle contract. A separate review run
requires the exact proposal digest, all risk acknowledgements and a rationale,
then emits `agentlab.multi_repo_construction_contract.v1`. The source surface
must retain at least two repositories, cannot exceed the candidate's affected
files, and separates editable paths from read-only context. API-call candidates
must reproduce an independently reviewed localization exactly. The
credential-bearing model-construction workflow revalidates that contract,
rematerializes the arbitrary exact source set, and exposes only the reviewed
surface to the construction participant.

Arbitrary-source calibration now has its own boundary. A bundle may remain in
this repository, or `Multi-repository calibration bundle source` can fetch a
credential-free public GitHub repository at one exact 40-character commit and
stage a repository-relative bundle as an independently retained artifact. Its
portable-source receipt binds the repository, commit, bundle path, reviewed
construction contract and every staged file byte; symlinks, path escapes,
mutable refs and credential-bearing URLs fail closed. The downstream proposal
workflow accepts either this exact receipt/run pair or a local bundle, never
both, revalidates the complete manifest and carries the source receipt digest
into the proposal and reviewed contract. The source stage cannot approve or
promote a case.

The authored path cannot substitute new bytes after review: construction
proposal, construction review, model construction, calibration proposal,
calibration review and case freeze all revalidate its receipt and manifest.
`Multi-repository calibration bundle proposal` accepts authored, portable-
repository or local input exclusively and binds the reviewed construction contract to exact
driver and Oracle digests, complete reference and alternative-solution tree
manifests, explicit variant roles, and the expected staged verdicts. At least
one structurally distinct `alternative-valid` implementation must pass every
stage, while wrong variants must still include an early-pass/later-fail case.
This rejects an Oracle that merely recognizes the reference implementation.
A separate exact-digest review
produces `agentlab.multi_repo_calibration_bundle.v1`; case review accepts only
that trusted-main artifact, revalidates every byte, executes it against the
materialized baseline and retains `agentlab.multi_repo_calibration_bundle_run.v1`.
The frozen case records the bundle, driver, reference and alternative-tree,
construction-contract and run digests. Oracle, reference and alternative-valid
bytes remain evaluator-only. This closes the portable public-repository intake
mechanism while preserving independent calibration and review. Release CI runs
the entire deterministic protocol as one
38-phase evidence chain and requires baseline failure, reference success, full
hidden-dependency coverage and process-aware discrimination score `1.0`. That
proves cross-phase compatibility, not empirical qualification: the authoring
and portable workflows still need trusted-main runs against real candidates,
and a
representative case population still needs human review, execution and
adjudication. Private calibration repositories remain outside this
credential-free source lane.

The same alternative-valid rule is now exercised by the retained real Harmony
UI calibration, not only by the deterministic protocol fixture. Besides the
one-line page-registration variant, a named-route implementation changes two
ArkTS files, overlaps none of the known-fix paths and leaves the failing
baseline's `main_pages.json` byte-identical. Its exact HAP passes the target
scenario and all eight pre-existing-route preservation scenarios on the same
Linux emulator. Baseline, known-fix and alternative HAPs therefore contribute
24 preservation runs, with four positive visible-semantic assertions. This
qualifies complete existing-route breadth for that controlled calibration; it
does not supply independent fairness review, broader case-population coverage
or a gold repair.

A controlled meaningful negative also demonstrates why the target Oracle must
bind route identity rather than generic content alone. It changes the
`UserAgent_four` button to navigate to `pages/UserAgent_three`; because both
pages render `Example Domain`, the old visible-text-only scenario falsely
passed. The v2 scenario adds an exact `assert-page-path pages/UserAgent_four`
before the visible assertion. A same-environment four-variant replay therefore
produces FAIL/PASS/PASS/FAIL for baseline, known-fix, alternative-valid and
wrong-route HAPs. This is controlled Oracle calibration, not a participant or
unseen-Agent run.

The first call-localization qualification is retained at
`release/qualifications/harmony-arkweb-lifecycle-localization-6840590/`. On the
same frozen source set, it reduces the broad `@kit.ArkWeb` module cluster from
176 files to six exact
`webview.WebviewController.initializeWebEngine` call sites. The retained
selection identifies two cross-repository target calls, four read-only
reference calls, five proposed editable paths and three explicitly expanded
paths. `proposal.json` binds every selected path to its Git blob OID and byte
digest, but remains `review-required`: the syntactic evidence does not prove
the lifecycle hypothesis or authorize intent construction. This retained
artifact predates the semantic-gate requirement and is historical evidence; it
cannot enter the current localization-review or construction chain.

The same directory now retains a Linux-emulator Oracle calibration candidate.
It rejects an initially misleading PASS whose screenshot-space coordinate
actually hit `DomStorage`, then binds the corrected `UserAgent_four` device
coordinate to exact `uitest` bounds. The corrected frozen baseline is an
assessed Oracle failure with infrastructure available and an unchanged Index
layout. This qualifies a candidate `FAIL_TO_PASS` observation, not the
business Oracle itself: independent review, reference repair, preservation and
performance calibration remain explicit later gates.

Use `propose-api-call-case-localization.py` to compile an exact proposal from an
already approved semantic packet/decision/gate triple, then have an independent
maintainer create a decision that binds the proposal SHA-256 and acknowledges
every localization risk. The proposer revalidates the semantic state machine,
candidate digest and source-set identity before writing output. When supplied,
it also binds the exact reviewed-cohort selection so the localization cannot be
reattributed to an unreviewed candidate. The trusted-main
`api-call-localization-proposal.yml` workflow recovers the cohort and semantic
review artifacts, rematerializes the pinned repositories, normalizes the
operator-owned target/reference/edit/context/check selection and produces that
proposal without requiring a retained qualification directory. Only
`review-api-call-case-localization.py` can produce a
`reviewed-for-intent-construction` localization, and it independently
revalidates the same three semantic artifacts. Even that reviewed artifact
retains `automaticPromotion: false`; build, functional, device, performance and
discrimination qualification are later gates.

The intent-construction runner now enforces that boundary. A
`shared-external-api-call-contract` cannot enter construction without the exact
reviewed localization, proposal, localization review and approved semantic
packet/decision/gate. It independently replays both review chains, checks their
digests and reviewed fields, verifies every materialized file against the pinned
byte identity, exposes context paths as read-only, and carries semantic plus
localization lineage into the construction receipt and intent. The plan builder
then derives `allowedEdits` from the reviewed editable paths, not from the broad
candidate cluster. The case freezer rejects any later edit-surface drift.

After these workflows reach trusted `main`, a maintainer can dispatch
`API-call localization independent review`. The job takes exactly one proposal
source: either a retained qualification directory or a successful dynamic
localization-proposal run. It also requires the exact proposal SHA-256, the
trusted-main semantic-review run and approved gate SHA-256, every risk ID and a
rationale. It binds the authenticated GitHub actor as reviewer and uploads the
semantic triple, proposal, decision and compiled reviewed localization together.
It is intentionally secret-free and cannot run from a pull-request ref.

## From difficulty to a valid evaluation case

A recursive impact candidate describes where a change may be discriminating;
it is not yet a task. Promotion requires all of the following:

1. freeze every participating repository revision and the source-set digest;
2. localize exact calls and review any edit or context path that expands beyond
   them;
3. define the intended cross-repository behavior and permitted edit scope;
4. provide repository-specific build or static checks;
5. provide an independent behavior oracle covering the affected boundary;
6. calibrate reference and known-failing variants before ranking Agent attempts.

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

When the Oracle and calibration variants were authored by the independent
evaluator workflow, that identity is not discarded at case freeze. The
calibration run and frozen case retain the exact authoring-receipt digest, draft
manifest, participant adapter digest and method revision. The portable Harmony
handoff, host resolver and assessed-campaign controller independently require
the same lineage and retain it in the final campaign summary. A hand-edited
handoff therefore cannot substitute a different Oracle author before emulator
execution even if the case and HAP files are otherwise present.

Harmony promotion also has a separate standard-test gate. The static
qualification matrix now records accepted `ohosTest`/Hypium Instrument Test,
Hypium Local Test and DevEco Testing Hypium UI lanes, while explicitly limiting
the existing bounded `uitest` script to supplemental Oracle authority.
`harmony-standard-test-contract.py` inventories digest-bound source assets and
requires a passing execution receipt tied to the same case, source set and
project-tree digest before standard-test execution is qualified. The current
custom UI runner remains useful evidence, but it does not close this new gate.
`run-harmony-instrument-test.py` now supplies the first native adapter for that
gate: it installs the exact app/test HAP pair and requires ArkXtest's final
non-empty result plus zero code markers (including worker aggregate markers), retaining digest-bound
logs and a native report. Exit zero without those markers, a failing/error
count, inconsistent totals, target/install failure, or later report tampering
is rejected. Local Test and DevEco Testing Hypium UI still need separate native
execution adapters.

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

## Resume the frozen-case Harmony loop

`run-harmony-evaluation-loop.py` is the control-plane bridge for three ordered
operational gates: assessed-workspace build, source-bound `ohosTest`, then
emulator UI/performance. It accepts an exact `frozen-calibrated` case,
digest-bound build and standard-test plans, a digest-bound run template, and
the exact programs. The UI template uses
`agentlab.harmony_evaluation_run_template.v1`; it contains the same case,
Oracle, runtime and performance bindings as a normal run plan, but deliberately
omits `buildReceipt` and `artifact`. The loop fills those two fields only from
the successful build output and emits the ordinary
`agentlab.harmony_evaluation_run_plan.v1` consumed by the emulator bridge.

```json
{
  "schema": "agentlab.harmony_evaluation_loop_plan.v1",
  "loopId": "case-42-hwlinux-r1",
  "evaluationCase": {"path": "/evidence/case.json", "sha256": "..."},
  "buildPlan": {"path": "/evidence/build-plan.json", "sha256": "..."},
  "standardTestTemplate": {"path": "/evidence/standard-test-template.json", "sha256": "..."},
  "runTemplate": {"path": "/evidence/run-template.json", "sha256": "..."},
  "buildProgram": {"path": "/agentlab/scripts/build-harmony-evaluation-artifact.py", "sha256": "..."},
  "standardTestProgram": {"path": "/agentlab/scripts/run-harmony-assessed-standard-test.py", "sha256": "..."},
  "runProgram": {"path": "/agentlab/scripts/run-harmony-evaluation-case.py", "sha256": "..."},
  "automaticPromotion": false
}
```

Run or resume with the same command:

```sh
python3 scripts/run-harmony-evaluation-loop.py \
  --plan /evidence/loop-plan.json \
  --output /evidence/case-42-hwlinux-r1
```

The output directory is created at the start and contains an atomically updated
`loop-state.json`. A failed build or emulator assessment is marked
`failed-resumable`; repeating the command with the identical plan retries that
stage while validating and reusing any earlier passed stage. Plan drift,
completed-evidence drift, program drift, or a generated run-plan mismatch fails
closed. A command that leaves an invalid final stage directory is marked
`failed-integrity` instead of pretending it can be safely retried; that evidence
requires operator review and a new loop identity. A functionally passing loop
emits `passed-review-required`; a valid device Oracle failure emits
`assessed-failure-review-required` and is terminal evidence rather than a
retryable infrastructure error. Both set `automaticPromotion=false` and stop at
`maintainer-adjudication-and-next-analysis-cut`. It therefore automates the
repeatable operational path without turning runtime feedback into benchmark
truth or silently bypassing the review and recalibration boundary.

An `ohosTest` assertion failure is retained as terminal assessed evidence with
`failureClass=standard-test` and skips UI/performance collection. HDC target,
installation, or tool failures remain resumable infrastructure failures. Only a
lineage-bound passing standard-test receipt can enter emulator performance.
The standard-test emulator is campaign-owned and separate from the subsequent
cold UI/performance lifecycle. `device.runtime.bootTimeoutSeconds` may extend
the default 180-second HDC deadline up to 900 seconds for slow hosts; a timed-out
start is stopped through the exact emulator instance and logged before the
stage is reported as resumable infrastructure failure.

The first complete hwlinux campaign carrying this gate is retained at
`/home/huawei/.agentlab/evidence/harmony-assessed-ohostest-aa799f9/campaign-output`.
Its two exact-revision workspaces both passed static assessment, independent
Harmony build, and source-bound `ohosTest`; only the strong variant passed the
device UI Oracle and therefore entered SmartPerf collection. The report marks
the case `high-discrimination-candidate`, with discrimination score 1.0,
process coverage 1.0, two infrastructure-valid device attempts, one profiled
successful attempt, and no excluded attempts. Summary and report SHA256 values
are respectively `53c68106…4f07` and `1cf515fd…f1be`. The evidence remains
review-required and non-promoting; one trial per profile does not establish a
population confidence claim. A release-controlled digest and scope record is
retained at
`release/qualifications/harmony-assessed-ohostest-hwlinux-aa799f9/summary.json`;
the underlying inputs remain controlled strong/weak fixtures, so this closes
the operational workflow but not unseen-Agent or external-repository
generalization.

### Build the assessed Agent output, not the frozen baseline

For an assessed-Agent campaign, the ordinary Git-object builder is the wrong
producer: it intentionally reconstructs the frozen baseline and therefore
cannot prove that a device ran the Agent's edits.
`build-harmony-assessed-workspace.py` closes that identity gap. Its
`agentlab.harmony_assessed_workspace_build_plan.v1` binds the frozen case plus
the exact Harness `summary.json`, `decision-package.json`,
`final-source-state.json`, assessment workspace, source-to-project mappings and
build tool. It accepts only an infrastructure-valid, independently assessed,
statically passing attempt.

Before building, the producer rejects symlinks and verifies the entire current
workspace bytes and executable modes against the final source-state manifest.
It then copies only manifest-bound bytes into a fresh disposable project,
rather than building the participant-owned directory in place. The resulting ordinary Harmony build
receipt uses
`buildAuthority=independent-harmony-assessed-workspace-build` and additionally
binds participant ID, subject-workspace digest, assessment summary, decision
package and final-source-state digests. The emulator bridge and resumable loop
preserve those fields into their bindings and receipts.

This gate deliberately excludes attempts that already failed the static Oracle:
their independent failure evidence remains valid without spending device
capacity. Passing this build still does not mean the Agent passed the device
gate; it only proves that the HAP submitted to that gate came from the exact
assessed Agent workspace.

### Compose static and device verdicts for discrimination

`compose-harmony-assessed-decision.py` accepts one statically passing assessment
and its exact assessed-workspace Harmony loop. It verifies the participant,
workspace, static decision, HAP, source set, loop receipt, emulator binding and
raw result digests. It then emits a normal
`agentlab.harness_decision_package.v1` whose existing static phases are followed
by `harmony-device`.

A failed UI Oracle becomes `oraclePass=false` for that phase and a false Agent
verdict; it is not rewritten as infrastructure failure. Conversely, unavailable
infrastructure cannot enter the compound decision. The ordinary attempt
collector and discrimination scorer can therefore compare participants across
the complete static-plus-device path, and `derive-assessment-feedback.py` can
turn a repeatable `harmony-device` failure into a non-ready difficulty candidate
for the next maintainer-reviewed analysis cut. The composition receipt remains
review-required and never mutates the frozen case or reusable knowledge.

The collector does not infer this boundary from the workflow name. It preserves
the exact stage IDs and validates the terminal `harmony-device` authority and
device process measurement. Suite qualification then requires at least one
device execution, device verdict coverage for every successful attempt, and
SmartPerf coverage for every successful device attempt. The GitHub-hosted static
campaign and its portable handoff are therefore insufficient by themselves;
only the completed hwlinux compound evidence can satisfy the end-to-end gate.

The trusted emulator wrapper also records an
`agentlab.harmony_device_process_measurement.v1` binding over runner wall time,
retained UI action/check rows, dynamic profile-workload action rows and
SmartPerf sample count. The resumable loop separately retains build and complete
emulator-assessment duration. The compound composer verifies each retained
digest, row count and timing relationship, then folds the complete build/device
stage into the same independently
reconstructable `agentlab.assessment_process_measurement.v1` used by static
multi-repository attempts. A read-only UI scenario may legitimately have zero
UI actions, but it must retain at least one UI check; a passing profiled run
must retain workload actions and samples.

The static participant protocol also accepts an optional pre-Oracle
`selfAssessment` containing `expectedOraclePass` and confidence in `0..1`. The
Harness derives pass probability, agreement and Brier score only after the
independent Oracle runs. Collection reconstructs those fields from retained
stage evidence, and discrimination scoring reports coverage and weighted
calibration at participant, case and suite levels. The claim never changes the
Oracle verdict or promotion eligibility, and adapters must not manufacture a
confidence value from process success.

Dependency discovery now has a separate v2 measurement path. The construction
workflow derives a review-required obligation proposal only from the selected
recursive candidate's native `module-dependency` evidence and groups it by
dependency depth. The case-review workflow requires the operator-provided
digest and risk acknowledgements before compiling a v2 reviewed plan. The
contract builder accepts that plan containing stable program-fact IDs,
independently verifies every fact against the case's exact repository revision,
and derives claim endpoints from `module-dependency` facts. An obligation may
name several accepted fact IDs, so supported alternative dependency routes can
receive credit. The derived case binder freezes the contract and fact-file
digests without changing the original calibrated case artifact.

```sh
python3 scripts/build-dependency-discovery-contract.py \
  --case case.json \
  --program-facts workspace_facts.jsonl \
  --plan dependency-plan.json \
  --output dependency-contract.json
python3 scripts/bind-dependency-discovery-case.py \
  --case case.json \
  --dependency-contract dependency-contract.json \
  --program-facts workspace_facts.jsonl \
  --output dependency-aware-case.json
```

For a dependency-aware case, blind-cut preparation keeps the contract and
program facts in the evaluator bundle. The participant task, participant
manifest and stage requests omit allowed edit paths; the Harness still enforces
the private scope after each turn. Participant `dependencyClaims` identify a
relation plus source/target repository paths and rationale. The Harness matches
them against hidden obligations before reporting required-obligation coverage.
Extra claims are retained as unadjudicated and `precisionClaimed=false`; a gold
patch's touched paths are never treated as the unique answer. Collection,
discrimination and suite composition preserve this metric separately from the
functional Oracle verdict. The assessed Pi adapter extracts claims only from an
explicit marker block in the retained native final assistant message; missing
and malformed submissions are reported separately. The trusted-main campaign
passes the evaluator-only contract and facts from the validated blind cut into
every run. Current evidence is deterministic protocol coverage, not proof that
real Agents are discriminated by it; a real trusted-main campaign is still
required.

### Run the assessed campaign through the device gate

`run-harmony-assessed-campaign.py` makes the device gate part of the trusted
campaign control path instead of a post-processing convention. Its plan binds
the frozen case and calibration, exact method revision, every static attempt's
summary/decision/final-state bytes, source-to-Harmony materialization, build
tool, emulator/runtime/Oracle/performance inputs, and every control program.
The device template must set `subjectOutcomePolicy` to
`retain-assessed-failure`; reserved lineage fields are generated by the
controller and cannot be supplied by the caller.

For each attempt, the controller applies a cost and authority gate:

1. an infrastructure-invalid static attempt is retained and excluded by the
   normal scorer;
2. a statically assessed failure is retained as its terminal Agent verdict and
   consumes no emulator capacity;
3. only a statically passing workspace enters the assessed-workspace HAP build,
   resumable Harmony loop and compound decision;
4. all terminal evidence is collected into one ordinary v2 attempt manifest,
   scored, and converted into review-required feedback candidates.

For a passing device attempt whose normalized profile is SmartPerf v2, the
compound decision now carries a compact performance observation: exact
environment, policy, workload and SmartPerf-summary identities plus the
policy-selected canonical statistic for every required metric. Collection
revalidates that observation against the terminal stage and summary hashes.
Scoring then reports per-participant min/max/mean, sample standard deviation
and coefficient of variation across attempts. It marks the performance feedback
repeatable only when at least two successful attempts have complete observations
under one identical environment/policy/workload identity. These descriptive
metrics never change the functional verdict or discrimination score, and their
authority remains an emulator relative-performance proxy with no absolute power
or thermal claim.

The output contains `campaign-state.json` from the first mutation. Re-running
the identical command resumes a failed Harmony stage and reuses completed
attempts while rechecking frozen inputs and recorded evidence digests. Plan,
program, static-evidence, loop, composition or derived-output drift fails
closed. A successful run emits
`agentlab.harmony_assessed_campaign_summary.v1` with status
`assessed-review-required`, exact derived artifact hashes and the next gate
`maintainer-adjudication-and-new-analysis-cut`.

```sh
python3 scripts/run-harmony-assessed-campaign.py \
  --plan /evidence/harmony-assessed-campaign-plan.json \
  --output /evidence/harmony-assessed-campaign
```

Run the controller on the qualified Linux Harmony emulator host. A
GitHub-hosted static campaign success is not device evidence. The trusted
workflow now creates `harmony-device-handoff.json` before uploading the complete
campaign artifact. That manifest contains only relocation-safe relative paths
and binds the frozen case, calibration, attempt collection, every static
summary/decision/final-state file, and the complete assessed workspace tree.
It can therefore move as one directory without weakening identity.

On the qualified emulator host, keep mutable host topology out of that portable
artifact. Declare it separately as an
`agentlab.harmony_assessed_host_profile.v1`: source materialization, independent
build command, runtime/instance directories, functional Oracle, performance
policy/workload and all controller program files. All file paths in this profile
are relative to an explicit host root and carry exact SHA256 values. Resolve the
two authorities into the existing path-bound campaign plan, then execute it:

```sh
python3 scripts/resolve-harmony-assessed-handoff.py \
  --handoff /evidence/static/harmony-device-handoff.json \
  --host-profile /home/huawei/agentlab/hwlinux-host-profile.json \
  --host-root /home/huawei \
  --output /evidence/harmony-assessed-campaign-plan.json

python3 scripts/run-harmony-assessed-campaign.py \
  --plan /evidence/harmony-assessed-campaign-plan.json \
  --output /evidence/harmony-assessed-campaign
```

Resolution fails before emulator use if transfer omitted a file, changed bytes
or modes, introduced a symlink, escaped either root, changed static identity, or
if the hwlinux profile no longer matches installed tools. The v2 handoff also
requires the signed pre-outcome participant experiment plan, exact planned
profile membership and repeat cardinality, and the plan-bound model/runtime
identity carried by every static assessment. The resolved plan is still
review-required and does not auto-promote a case.

For KVM-backed profiles, declare an `executionPreflight` with the required
group and character device. The campaign controller checks the active process
identity and device access before creating output or building a HAP. Membership
in `/etc/group` alone is insufficient for a long-lived service whose process
groups have not been refreshed.

The first real portable-handoff qualification is retained at
`release/qualifications/harmony-portable-handoff-hwlinux-2be1911/summary.json`.
It records a fail-closed KVM permission attempt, successful resumable execution
under the active `kvm` group, a 134 ms evidence-only replay, two device attempts,
strong pass versus weak Oracle failure, SmartPerf collection on the passing arm,
and discrimination score 1.0. It binds the complete 202-file remote evidence
tree while leaving promotion review-required.

### Import completed device evidence into the trusted scorecard path

Device execution and GitHub provenance are separate authorities. The emulator
host cannot turn a locally written report into trusted-main evidence merely by
uploading that report. After a campaign reaches `assessed-review-required`, use
the release import tool to create one deterministic ZIP containing the complete
campaign tree, resolved plan and host profile. The bundle manifest indexes every
member by path, byte length, Unix mode and SHA256, and binds the exact successful
static workflow run and its portable handoff:

```sh
gh api repos/yxsicd/agentlabrelease/actions/runs/$STATIC_RUN_ID \
  > /evidence/source-run.json
python3 scripts/import-harmony-device-campaign.py prepare \
  --campaign /evidence/harmony-assessed-campaign \
  --handoff /evidence/static/harmony-device-handoff.json \
  --host-profile /home/huawei/agentlab/hwlinux-host-profile.json \
  --plan /evidence/harmony-assessed-campaign-plan.json \
  --source-run /evidence/source-run.json \
  --output /evidence/harmony-device-campaign.zip
sha256sum /evidence/harmony-device-campaign.zip
```

Publish that exact ZIP under a new evidence release tag; do not replace an
existing asset. This lane is for controlled benchmark evidence only: inspect
the indexed file set before publication and never include Gateway credentials,
private Agent homes, unrelated user data or production captures. Dispatch
`harmony-device-campaign-import.yml` with the static
run ID, release tag, asset name and SHA256. The trusted-main workflow downloads
the original static artifact independently, rejects archive traversal,
symlinks, unindexed files, source-run or handoff substitution, plan/profile
drift, participant-experiment substitution, campaign-state drift and evidence
digest drift. It then reconstructs the
attempt collection, discrimination report and feedback with trusted repository
code. The bundle and trusted import receipt also retain the independently
authored calibration receipt, draft manifest, participant identity and exact
authoring revision; substitution at the handoff, plan, campaign summary or
bundle boundary fails closed. The reconstructed report and import receipt
receive separate GitHub OIDC attestations and are preserved as
`harmony-device-assessed-campaign`.

`agent-suite-scorecard.yml` accepts either the original static campaign run or
this device-import run. It keeps the source assessment method revision distinct
from the later import workflow revision and requires both device-import and
report attestations. A static run remains explicitly unqualified for Harmony
end-to-end coverage; an imported run is still review-required and qualifies
only when its reconstructed stage/process evidence satisfies the device and
SmartPerf gates.

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

For a release-bound Harmony campaign,
`prepare-release-recursive-feedback.py` adds the missing portable boundary
between the runtime result and that next-cut bridge. It verifies the immutable
release closure, retained Harmony acceptance, campaign summary, raw feedback
and discrimination report together, then emits
`agentlab.release_recursive_feedback_handoff.v1`. The output preserves the
candidate mechanism, discrimination score, Wilson-confidence boundary,
SmartPerf observation/repeatability boundary and exact evidence hashes. It is
explicitly `next-analysis-review-required`; it does not fabricate the new
source set or substitute for `propose-feedback-analysis-cut.py` and its
maintainer review.

The existing **Multi-repository exact analysis** workflow accepts that handoff
as an optional trigger context. Supply the committed qualification summary
path, one candidate id, a two-to-sixteen-repository source specification and an
`agentlab.feedback_semantic_source_selection_claim.v1`. Each claim must quote an
exact prior-case title, stage demand or observed failure mechanism and map it to
an exact file and source symbol in the pinned source set, with a rationale.
`prepare-feedback-semantic-source-selection.py` reads each exact
`revision:path` Git Blob directly from the materialized object database, records
its Blob OID and content SHA-256, and rejects missing symbols, free-form case
anchors, path escapes, oversized or non-UTF-8 evidence blobs, duplicate claims,
or evidence that covers fewer than two repositories and two case anchors. This proves that source selection has
inspectable relevance evidence; it deliberately does not prove that a later
difficulty candidate explains the failure.

Before analysis, `prepare-feedback-analysis-request.py` validates the portable
prior case and feedback bytes, the source-selection receipt, public HTTPS
repository identities and exact 40-character revisions. It reproduces the next
source-set digest and rejects a request where neither the source set nor method
revision changed. The resulting `agentlab.feedback_analysis_request.v2` travels
in the analysis artifact beside the source-selection claim and receipt,
normalized source specification and exact analysis receipt. It schedules
analysis only: case readiness, candidate semantic alignment, Oracle calibration
and promotion remain separate review gates.

The claim is explicit and reviewable rather than a keyword list:

```json
{
  "schema": "agentlab.feedback_semantic_source_selection_claim.v1",
  "sourceSetSha256": "<canonical source-set SHA-256>",
  "priorCaseSha256": "<exact retained prior-case SHA-256>",
  "feedbackEvidenceSha256": "<exact retained feedback SHA-256>",
  "feedbackCandidateId": "assessment-feedback-a6a1b3d8a4ce4835db0c",
  "reviewer": "maintainer identity",
  "claims": [
    {
      "caseAnchor": "Understand and preserve the cross-repository payment authority binding.",
      "repositoryId": "application",
      "path": "src/payment/PaymentPage.ets",
      "sourceSymbol": "bindPaymentAuthority",
      "rationale": "This exact application symbol binds the authority contract into the device-visible payment state."
    },
    {
      "caseAnchor": "Keep the composed application ready for the device-visible workflow and its Harmony ohosTest gate.",
      "repositoryId": "contracts",
      "path": "src/payment/PaymentAuthority.ts",
      "sourceSymbol": "PaymentAuthority",
      "rationale": "This exact contract symbol defines the authority boundary consumed by the application repository."
    }
  ],
  "automaticPromotion": false
}
```

The release handoff directory carries the exact prior frozen case and assessment
feedback bytes, both bound in the handoff and request. Once exact analysis
finishes, `prepare-feedback-analysis-proposals.py` rechecks those bytes, the
method-revision-bound analysis run, analysis receipt and difficulty evidence, filters for non-ready impact
candidates that actually span at least two repositories, and creates a bounded
queue of at most ten ordinary feedback-cut proposals. Ordering is deterministic
by affected repository count, affected file count, evidence count and candidate
id. The queue records `semanticAlignmentVerified=false`; every proposal still
requires an independent maintainer to decide whether its program-analysis
mechanism explains the observed assessment failure.

```sh
gh workflow run multi-repo-analysis.yml --ref main \
  -f source_spec_json="$(jq -c . /next/source-spec.json)" \
  -f feedback_handoff_path=release/qualifications/alpha13-recursive-feedback-4f24f9a/summary.json \
  -f feedback_candidate_id=assessment-feedback-a6a1b3d8a4ce4835db0c \
  -f feedback_semantic_selection_json="$(jq -c . /next/semantic-source-selection-claim.json)"
```

The same feedback pass now closes repeatable Harmony performance separation
into this recursive path without treating performance as a functional failure.
It emits a performance candidate only when at least two functionally successful
participant profiles each have two or more complete observations, share the
exact environment/policy/workload identity, and have non-overlapping observed
ranges for the same policy-selected metric and statistic. Overlapping ranges,
single runs, partial coverage and identity drift produce no candidate. The row
retains the best/worst profile, range summaries and emulator-only authority,
remains `caseReady=false`, and additionally requires independent performance
calibration before it can become a benchmark case.

The Alpha.13 functional-feedback successor was replayed locally with the same
workflow programs over exact `code-workshop` and `guide-snippets` commits. Its
compact qualification is retained at
`release/qualifications/alpha13-feedback-analysis-proposals-b8aadaa/summary.json`.
The source set and method revision both changed relative to the device case;
404,308 facts yielded 19,374 difficulty candidates, 97 eligible cross-repository
impact candidates and a bounded queue of ten review proposals. The retained
summary binds the request, handoff, Git-object prefetch receipt, analysis run,
native evidence and queue index. Full replay evidence remains a workflow/local
artifact rather than being committed into the lightweight release repository.

The bounded queue must be triaged as a whole before any proposal proceeds.
`triage-feedback-analysis-proposal-queue.py` binds the exact queue and every
proposal digest, requires one evidence-backed decision per proposal, permits at
most one shortlist, and never verifies semantic alignment or promotes a case.
An all-rejected queue returns the loop to source selection or feedback-mechanism
enrichment instead of forcing a false match. Alpha.13 exercised that path: all
ten proposals were broad PerformanceAnalysisKit, ArkUI, AbilityKit, Hypium or
hvigor contracts. Both device attempts had already passed ohosTest/Hypium and
only the weak attempt failed the payment-authority UI Oracle, so all ten were
rejected as semantically unaligned. The compact result is retained at
`release/qualifications/alpha13-feedback-analysis-triage-b8aadaa/summary.json`.

```sh
python3 scripts/triage-feedback-analysis-proposal-queue.py \
  --queue /next-analysis/feedback-analysis-proposals/index.json \
  --proposal-root /next-analysis/feedback-analysis-proposals \
  --review /next-analysis/feedback-analysis-proposals/triage-review.json \
  --output /next-analysis/feedback-analysis-proposals/triage.json
```

The next-cut bridge is executable and fail-closed. Rerun multi-repository
analysis over a new exact source set, a new method revision, or both, then bind
one assessed feedback candidate to one new recursive impact candidate:

```sh
python3 scripts/propose-feedback-analysis-cut.py \
  --prior-case /evidence/multi-repo-evaluation-case.json \
  --feedback /evidence/assessment-feedback-candidates.json \
  --analysis-receipt /next-analysis/multi_repo_analysis.json \
  --difficulty /next-analysis/difficulty_candidates.json \
  --feedback-candidate-id <assessment-feedback-id> \
  --difficulty-candidate-id <next-difficulty-id> \
  --next-method-revision <exact-40-character-release-revision> \
  --output /next-analysis/feedback-analysis-cut-proposal.json
```

The proposer re-derives the prior case identity, verifies the exact feedback,
analysis receipt and difficulty bytes, reproduces the next source-set digest,
and rejects a transition where neither source set nor method revision changed.
For `assessed-agent-performance-separation`, it also revalidates and carries the
exact emulator environment, performance-policy digest, workload digest, metric,
statistic, direction, separated-range result and emulator-only authority. The
independent review must acknowledge the additional performance-calibration and
authority risk. The reviewed cut, case proposal, approved plan and generated
case lineage all preserve this performance evidence; substitution or removal at
any boundary fails closed. Thus a recursive case can be traced back to the
specific repeatable performance signal without reclassifying that signal as a
functional Oracle verdict.

That preserved reason is now an executable case-construction gate. The plan
adds `agentlab.case_performance_requirement.v1`; the freezer will not accept the
derived case until `compose-case-performance-calibration.py` has independently
rebuilt at least two policy-bound SmartPerf comparisons for each baseline,
reference and deliberately wrong artifact. All observations must share the
feedback cut's environment, policy, workload, metric and statistic; functional
Oracle results must pass before performance is considered. Baseline and wrong
must repeatedly regress while the reference remains within the same relative
guardrails. The resulting `agentlab.case_performance_calibration.v1` binds all
raw summaries, Harmony results and comparisons by SHA-256 and byte length, and
the freezer rechecks those files before retaining its digest. This closes the
previous gap where a performance-derived case could preserve its reason in
lineage but qualify only a functional Oracle. It remains review-only and does
not claim absolute device power or thermal authority.

It deliberately does not claim that the two mechanisms are semantically
aligned. An independent maintainer must review that judgment, acknowledge all
remaining semantic, Oracle, calibration and freshness risks, and bind the exact
proposal digest:

```sh
python3 scripts/review-feedback-analysis-cut.py \
  --proposal /next-analysis/feedback-analysis-cut-proposal.json \
  --review /next-analysis/feedback-analysis-cut-review.json \
  --output /next-analysis/feedback-analysis-cut.json
```

The reviewed output conforms to
`schemas/feedback-analysis-cut.schema.json`. Supplying it through
`propose-multi-repo-case-plan.py --feedback-analysis-cut ...` together with
`--feedback-cut-proposal ... --feedback-cut-review ...` makes the proposer
independently recheck all three exact artifacts and makes the transition survive
proposal review, calibration and final frozen-case lineage.
It authorizes only construction of a new candidate. The old case stays frozen,
the new difficulty stays non-ready, and every artifact keeps
`automaticPromotion: false`.

## Real-source semantic review packets

The review decision is executable rather than a free-form approval. Supply one
answer and evidence rationale for every packet question to
`review-multi-repo-candidate-semantics.py`. The state transition is fail-closed:

- `advance-to-case-contract` requires every answer to be `yes`;
- `reject-as-noncoherent` requires at least one `no`;
- `defer-for-more-evidence` requires at least one `unknown`, and cannot hide a
  `no` for shared behavior or genuine cross-repository necessity.

The compiler binds the exact packet and decision digests into an immutable
semantic gate. Only an approved gate carries `allowsCaseContract: true`; reject
and defer gates remain useful denominator evidence but cannot authorize case
construction. `multi-repo-candidate-semantic-review.yml` exposes this protocol
as a secret-free trusted-`main` manual workflow, binds the GitHub actor identity
and retains the packet, normalized answers, decision and gate together. It
accepts exactly one source: either a retained qualification packet or a
successful trusted-main `multi-repo-candidate-review-packet.yml` run. Dynamic
packets are therefore first-class inputs rather than files that must be manually
copied into the repository. This is role/provenance evidence, not proof that the
reviewer judgment is correct or that the candidate is representative.

Three API candidates in the retained shortlist now have exact-source review
packets under
`release/qualifications/harmony-real-multi-repo-34661ff/review-packets/`.
Each packet binds the frozen candidate, facts, source blobs, line-numbered call
context, marker-bearing project-root candidates and the method revision that
materialized the packet. It deliberately does not supply a task prompt or an
Oracle. An independent reviewer must decide whether the call sites express one
coherent cross-repository behavior before any case contract is written.

New packets also bind the complete enclosing symbol when it is at most 240
lines, plus every analyzer-observed call in that same owner. Larger owners use a
bounded head/tail/call-neighborhood excerpt, and unresolved or bounded owners
add a mandatory `owner-context-incomplete` risk. This lets a reviewer compare
behavioral neighborhoods rather than isolated API spellings while preserving
the boundary: owner spans and neighboring calls are syntactic evidence, not
receiver-type, dataflow or intent proof.

This gate matters in the real evidence. The two `AlertDialog` sites implement
different product behavior (account logout confirmation versus Web alert result
handling), while the two `call.makeCall` sites pass different inputs and live
behind different lifecycle/capability boundaries. A shared API name is thus
localization evidence, not semantic equivalence. Both packets remain
`independent-semantic-review-required`, acknowledge the same four risks and
remain unapproved.

The third packet covers `image.createImagePacker`: 12 exact call sites across
seven files and two repositories, with complete owner context for all 12. The
handle-aware v4 packet relates 10 calls to lexical binding initializers and two
to assignments, with no unresolved or ambiguous result handles. Exact
same-handle member spellings comprise six `packToData`, five `packToFile`, one
`packing` and six `release` calls; six handles have no direct `release` spelling.
Supplemental facts are generated from the same exact sources by a separately
revision-bound analyzer without replacing the proposal-bound base facts. The
v4 packet pairs every exact same-handle `release` back to its factory call: two
share the same `try` and execute lexically inside its `finally`, one factory
precedes a later `try/finally`, one release is inside a Promise `.finally`
callback, and two are ordinary calls in the same `try` rather than finalizers.
Six handles still have no direct release spelling. The 12 factory calls
themselves span five `try` regions, five conditional regions and two callbacks.
That split is useful lifecycle-review evidence, but it is deliberately not
classified as a defect: the exact SDK contract, escape/dataflow behavior,
observable failure and acceptable repairs still require independent review and
runtime calibration. Exact receiver spelling, byte order and shared ancestor
spans do not prove alias completeness, reachability, dominance, post-dominance
or exception-safe cleanup. The packet therefore adds owner-scoped
call-neighborhood, syntactic control-region and cleanup-pairing evidence to the
SWE-style contract but does not advance to case construction.

The approved state is now a consumed authority rather than advisory metadata.
API-call localization proposal, localization review, construction-contract
proposal/validation and model construction all require the same exact packet,
decision and gate. Each stage replays semantic validation and binds the three
digests. A deferred/rejected gate, substituted reviewer, changed candidate,
changed source set, missing artifact or byte-level gate tamper fails before a
construction participant runs.
