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
  /path/to/manifest.json /path/to/evidence
```

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
`Multi-repository construction contract proposal` binds one exact cohort member
to an operator-owned source surface and Oracle contract. A separate review run
requires the exact proposal digest, all risk acknowledgements and a rationale,
then emits `agentlab.multi_repo_construction_contract.v1`. The source surface
must retain at least two repositories, cannot exceed the candidate's affected
files, and separates editable paths from read-only context. API-call candidates
must reproduce an independently reviewed localization exactly. The
credential-bearing model-construction workflow revalidates that contract,
rematerializes the arbitrary exact source set, and exposes only the reviewed
surface to the construction participant.

Arbitrary-source calibration now has its own boundary. `Multi-repository
calibration bundle proposal` binds the reviewed construction contract to exact
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
bytes remain evaluator-only. This closes
the generic protocol. Release CI runs the entire deterministic protocol as one
37-phase evidence chain and requires baseline failure, reference success, full
hidden-dependency coverage and process-aware discrimination score `1.0`. That
proves cross-phase compatibility, not empirical qualification: a real
arbitrary-source bundle and representative case population still need human
review, execution and adjudication.

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
the lifecycle hypothesis or authorize intent construction.

The same directory now retains a Linux-emulator Oracle calibration candidate.
It rejects an initially misleading PASS whose screenshot-space coordinate
actually hit `DomStorage`, then binds the corrected `UserAgent_four` device
coordinate to exact `uitest` bounds. The corrected frozen baseline is an
assessed Oracle failure with infrastructure available and an unchanged Index
layout. This qualifies a candidate `FAIL_TO_PASS` observation, not the
business Oracle itself: independent review, reference repair, preservation and
performance calibration remain explicit later gates.

Use `propose-api-call-case-localization.py` to compile an exact proposal, then
have an independent maintainer create a decision that binds the proposal
SHA-256 and acknowledges every risk. Only
`review-api-call-case-localization.py` can produce a
`reviewed-for-intent-construction` localization. Even that reviewed artifact
retains `automaticPromotion: false`; build, functional, device, performance and
discrimination qualification are later gates.

The intent-construction runner now enforces that boundary. A
`shared-external-api-call-contract` cannot enter construction without the exact
reviewed localization, proposal and review decision. It independently checks
their digests and reviewed fields, verifies every materialized file against the
pinned byte identity, exposes context paths as read-only, and carries the
localization lineage into the construction receipt and intent. The plan builder
then derives `allowedEdits` from the reviewed editable paths, not from the broad
candidate cluster. The case freezer rejects any later edit-surface drift.

After this workflow reaches trusted `main`, a maintainer can dispatch
`API-call localization independent review`. The job takes the retained
qualification directory, exact proposal SHA-256, every risk ID and a rationale;
it binds the authenticated GitHub actor as reviewer and uploads the proposal,
decision and compiled reviewed localization together. It is intentionally
secret-free and cannot run from a pull-request ref.

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

`run-harmony-evaluation-loop.py` is the control-plane bridge for the two
operational gates above. It accepts an exact `frozen-calibrated` case, a
digest-bound build plan, a digest-bound run template, and the exact build and
run programs. The template uses
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
  "runTemplate": {"path": "/evidence/run-template.json", "sha256": "..."},
  "buildProgram": {"path": "/agentlab/scripts/build-harmony-evaluation-artifact.py", "sha256": "..."},
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
if the hwlinux profile no longer matches installed tools. The resolved plan is
still review-required and does not auto-promote a case.

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
drift, campaign-state drift and evidence digest drift. It then reconstructs the
attempt collection, discrimination report and feedback with trusted repository
code. The reconstructed report and import receipt receive separate GitHub OIDC
attestations and are preserved as `harmony-device-assessed-campaign`.

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
and retains the packet, normalized answers, decision and gate together. This is
role/provenance evidence, not proof that the reviewer judgment is correct or
that the candidate is representative.

The two two-file API candidates in the retained shortlist now have exact-source
review packets under
`release/qualifications/harmony-real-multi-repo-34661ff/review-packets/`.
Each packet binds the frozen candidate, facts, source blobs, line-numbered call
context, marker-bearing project-root candidates and the method revision that
materialized the packet. It deliberately does not supply a task prompt or an
Oracle. An independent reviewer must decide whether the call sites express one
coherent cross-repository behavior before any case contract is written.

This gate matters in the real evidence. The two `AlertDialog` sites implement
different product behavior (account logout confirmation versus Web alert result
handling), while the two `call.makeCall` sites pass different inputs and live
behind different lifecycle/capability boundaries. A shared API name is thus
localization evidence, not semantic equivalence. Both packets remain
`independent-semantic-review-required`, acknowledge the same four risks and
state that only the exact base source set and source-localized call evidence
satisfy the SWE-style task contract so far.
