# Rust ArkTS program analysis

`agentlab-code-analysis` parses committed `.ets/.ts` bytes using pinned Rust
Tree-sitter 0.27.0 and an AgentLab extension of ArkTS grammar 0.2.0. No Python runtime is needed for this
analyzer. Tree-sitter provides a concrete syntax tree; this crate lowers it to
structured program facts, not a type-checked semantic AST.

```sh
cargo build --locked -p agentlab_code_analysis
./target/debug/agentlab-code-analysis /path/to/source-repo /tmp/ast-evidence
```

Output is sorted `program_facts.jsonl` plus `analysis.json` with source cut,
parser/grammar versions, counts and exact data digest. It captures multiline
module references, declarations/methods, syntactic call/assignment locations,
decorators, ArkUI nodes and complete parse-error text/spans. Expression-bearing
facts also retain method/function parameter expressions, call argument
expressions, assignment right-hand expressions, object-entry values and return
expressions. These are lossless inputs for a later bounded dataflow stage; they
do not themselves claim call-target, type or dataflow resolution. IDs use
source path, syntax role, scope/name and occurrence rather than byte offsets;
spans still reflect the exact source cut. Calls remain unresolved syntax
observations.

The initial fixed code-workshop run parsed556 files:555 without syntax errors and one
with five recovery/error nodes at `products/tv/src/main/ets/component/BarItem.ets`.
The unsupported form is leading-dot style statements inside `stateStyles` object
value blocks. This was grammar coverage debt, not source/Agent failure; the repair below closes it.
Do not rewrite source with regular expressions to manufacture clean parsing.
The minimal regression fixture and regenerated parser are now committed. Clean syntax does not imply type or runtime correctness.

The knowledge flywheel now invokes this Rust binary and imports selected-scenario
AST facts into TableGit. Its current TableGit orchestration is still Python;
that transport/method-construction code is separate from this Rust analyzer.
Full source syntax facts remain in the captured AST evidence. Type resolution,
resolved calls, control/dataflow and whole-corpus TableGit ingestion are further
capabilities, not claims of this version.

## Revision-fenced multi-repository graph

`agentlab-multi-repo-analysis` accepts two or more repositories in an explicit
manifest. Every repository has a stable source identifier, a local checkout
used only as an object database, and an exact 40-character commit. The analyzer
reads each file with `git show <revision>:<path>`, so dirty and untracked
workspace bytes do not enter the result.

```sh
cargo run --locked -p agentlab_code_analysis \
  --bin agentlab-multi-repo-analysis -- \
  --cache-dir /path/to/rebuildable-ast-cache \
  --cache-components \
  multi-repo-manifest.json /tmp/multi-repo-evidence
```

See [`docs/multi-repository-analysis.md`](../../docs/multi-repository-analysis.md)
for the manifest and evidence contract. Relative ArkTS/TypeScript imports are
resolved within a repository. Non-relative cross-repository imports resolve
only through explicit manifest bindings; the tool does not guess package
manager or compiler configuration. It emits a dependency graph, unresolved
boundary evidence, and recursive reverse-impact difficulty candidates. Those
candidates are not benchmark cases: each remains in candidate state until it
has repository-specific build checks and an independent behavior oracle.

## Purchase-data runtime calibration planning

`agentlab-purchase-data-runtime-plan` keeps the next runtime transition in
Rust. It accepts only an independently approved behavior-Oracle gate, verifies
the exact behavior plan and calibration digests, checks the generic Linux
x86/KVM target, and resolves the three immutable emulator assets through the
release closure and component registry.

```sh
cargo run --locked -p agentlab_code_analysis \
  --bin agentlab-purchase-data-runtime-plan -- \
  --oracle-gate /path/to/approved-gate.json \
  --behavior-plan release/qualifications/alpha13-payment-feedback-analysis-165bcbd/purchase-data-behavior-oracle-plan.json \
  --behavior-calibration release/qualifications/alpha13-payment-feedback-analysis-165bcbd/purchase-data-behavior-oracle-calibration.json \
  --release-closure release/closures/v0.1.0-alpha.13.json \
  --target release/targets/generic-linux-agentlab.json \
  --component-registry release/components/registry.json \
  --output /tmp/purchase-data-runtime-plan.json
```

The output only authorizes a future calibration run. It does not claim that
the source was built, OHOS Test ran, the emulator was launched, the functional
Oracle passed, or SmartPerf evidence exists. Those flags remain false until
independently validated runtime receipts are attached.

After the retained runtime and case-performance evidence is assembled, freeze
the next unseen-Agent transition with the Rust contract producer:

```sh
cargo run --locked -p agentlab_code_analysis \
  --bin agentlab-purchase-data-unseen-agent-cohort-contract -- \
  --packet release/qualifications/alpha13-payment-feedback-analysis-165bcbd/purchase-data-integrated-review-packet-v2.json \
  --expected-packet-sha256 3c8bce352c03b7dde565e3cc1dbe602d817b8e57f13abe5292daee1743248efd \
  --qualification-root release/qualifications/alpha13-payment-feedback-analysis-165bcbd \
  --case-review-workflow .github/workflows/multi-repo-case-review.yml \
  --assessed-campaign-workflow .github/workflows/multi-repo-assessed-campaign.yml \
  --participant-dispatch-source crates/agentlab_code_analysis/src/participant_experiment_dispatch.rs \
  --participant-dispatch-schema schemas/participant-experiment-dispatch.schema.json \
  --exact-patch-publication-source crates/agentlab_code_analysis/src/purchase_data_exact_patch_publication.rs \
  --exact-patch-publication-schema schemas/purchase-data-exact-patch-publication.schema.json \
  --exact-patch-publication-workflow .github/workflows/purchase-data-exact-patch-publication.yml \
  --published-revision-reexecution-source crates/agentlab_code_analysis/src/purchase_data_published_revision_reexecution.rs \
  --published-revision-reexecution-schema schemas/purchase-data-published-revision-reexecution.schema.json \
  --published-revision-runtime-bundle-schema schemas/purchase-data-published-revision-runtime-bundle.schema.json \
  --published-revision-reexecution-workflow .github/workflows/purchase-data-published-revision-reexecution.yml \
  --trusted-case-freeze-source crates/agentlab_code_analysis/src/purchase_data_trusted_case_freeze.rs \
  --trusted-case-freeze-schema schemas/purchase-data-trusted-case-freeze.schema.json \
  --trusted-case-freeze-workflow .github/workflows/purchase-data-trusted-case-freeze.yml \
  --output /tmp/purchase-data-unseen-agent-cohort-contract.json
```

The command verifies and digest-binds those existing execution surfaces. It
does not bypass independent review, upstream revision rebinding, blind-case
freeze or the pre-outcome cohort plan, and it never grants automatic promotion.

After an approved trusted-main integrated-review gate and an actual upstream
publication exist, `agentlab-purchase-data-exact-patch-publication` produces the
first non-fixture publication receipt. It reconstructs the reviewed tree by
applying the retained format-patch to the recorded base through an isolated Git
index, requires that tree to equal the checked-out published revision, and
requires the exact revision to be visible from the packet's upstream origin.
`.github/workflows/purchase-data-exact-patch-publication.yml` admits only the
authenticated successful Oracle-review run, runs this Rust producer from the
immutable analysis-tools component, and attests the resulting receipt. It does
not push or otherwise mutate the upstream repository.

`agentlab-purchase-data-published-revision-reexecution` implements the next
gate without trusting summary booleans. It verifies the attested publication,
an authenticated trusted-main multi-repository analysis whose source spec
names the exact published revision, a digest-bound hwlinux bundle containing a
passing source-to-OHOS-Test build/execution chain, and a case-bound
baseline/reference/meaningful-wrong performance qualification for that same
revision. The trusted-main re-execution workflow imports the exact runtime ZIP,
runs the immutable Rust component, and attests the compiled receipt. GitHub is
the verifier/import authority; the workflow does not claim its hosted runner
executed the Harmony emulator.

`agentlab-purchase-data-trusted-case-freeze` then reopens the authenticated
re-execution receipt and the exact successful `multi-repo-case-review`
artifact. It validates the published repository/revision and semantic source
set, recalculates every participant/evaluator inventory and manifest digest,
rejects symlinks, unbound files and cross-boundary byte overlap, and requires
the evaluator's frozen case to be the exact reviewed case. The trusted-main
workflow runs this Rust producer from the immutable component and attests the
resulting case-freeze receipt. A held-out declaration permits the next dispatch
gate; it does not claim model-training exclusion or unseen-Agent results.

Once those external gates actually exist, compile their exact byte chain into
an operator-gated dispatch decision with the Rust readiness validator:

```sh
agentlab-purchase-data-unseen-agent-readiness \
  --contract purchase-data-unseen-agent-cohort-contract.json \
  --review-gate approved-integrated-review-gate.json \
  --publication exact-patch-publication.json \
  --reexecution published-revision-reexecution.json \
  --reexecution-attestation-verification reexecution-attestation-verification.json \
  --case-freeze trusted-case-freeze.json \
  --case-freeze-attestation-verification case-freeze-attestation-verification.json \
  --participant-dispatch participant-experiment-dispatch.json \
  --dispatch-attestation-verification dispatch-attestation-verification.json \
  --output unseen-agent-dispatch-readiness.json
```

The compiler accepts only the real approved gate status emitted by the
integrated reviewer, two distinct GitHub reviewer identities, an exact patch
publication bound to the reviewed candidate, semantic/OHOS Test/performance
re-execution on the published revision, a trusted-main held-out case freeze,
and a 3–8-profile pre-outcome portable dispatch whose exact subject and workflow
run/attempt occur in raw `gh attestation verify --format json` output. The
certificate identity must also bind the exact repository, main ref, source
revision, signer workflow and GitHub-hosted runner. The re-execution,
case-freeze and participant-dispatch receipts all require raw attestation
verification. It binds all nine inputs by raw-byte SHA-256 and length. Success permits only
explicit dispatch of that declared cohort: execution and Harmony feedback
remain false, and automatic dispatch/promotion remain forbidden.

## Independent component packaging

`agentlab-analysis-tools-pack` packages the complete Linux x64 Rust binary
inventory as an optional immutable component. A producer supplies the static
musl release directory, exact source revision and its source-derived version:

```sh
target/x86_64-unknown-linux-musl/release/agentlab-analysis-tools-pack \
  --binary-dir target/x86_64-unknown-linux-musl/release \
  --source-revision <exact-40-hex-revision> \
  --version <8-to-40-character-revision-prefix> \
  --output /tmp/analysis-tools-component
```

The output contains the deterministic `.tar.zst`, capability-pack descriptor,
binary manifest and relative-URL component-update descriptor. Creation alone is
not publication or aggregate promotion; the dedicated workflow keeps those as
separate explicit operations.

The first selection of a newly published optional pack uses the Rust-native
`agentlab-component-introduce` coordinator:

```sh
agentlab-component-introduce \
  --base-publication release/channels/aldev/publication.json \
  --base-lock release/channels/aldev/environment-lock.json \
  --component-update analysis-tools-<revision>-linux-x64.json \
  --component-update-url https://github.com/yxsicd/agentlabrelease/releases/download/analysis-tools-<revision>-linux-x64/analysis-tools-<revision>-linux-x64.json \
  --tag candidate-analysis-tools-<revision>-linux-x64 \
  --output /tmp/analysis-tools-coordinated-candidate
```

It accepts only a new enabled-but-optional pack slot from a canonical immutable
Release, preserves every existing component and aggregate source revision,
recomputes the contract graph, and resets qualification gates. Reusing it for
an existing slot fails closed; later revisions use the ordinary independent
component-upgrade path.

Before the runtime plan can advance,
`agentlab-purchase-data-ohostest-proposal` reads the selected source directly
from its exact Git revision and combines content-addressed identity with Rust
Tree-sitter facts. It verifies the platform lane (`ohosTest` target and Hypium
dependency), inventories existing test sources and decides whether the five
Harmony behavior checks have a deterministic testability seam. The current
exact source is intentionally rejected for authoring: it has no test source,
keeps `ConsumablesPage` non-exported and directly binds the decoder and IAP
finish sink. Its retained output specifies the bounded refactor required
before source-bound OHOS Test can be generated.

```sh
cargo run --locked -p agentlab_code_analysis \
  --bin agentlab-purchase-data-ohostest-proposal -- \
  --behavior-plan /path/to/purchase-data-behavior-oracle-plan.json \
  --build-qualification /path/to/build-qualification.json \
  --repository harmony-iap-client=/path/to/exact/git-checkout-or-bare-repository \
  --output /tmp/purchase-data-ohostest-proposal.json
```

The optional cache is a derivative, never source authority. By default an
exact analyzer/grammar/source-set bundle hit bypasses both parsing and graph
reconstruction and restores the previously digest-checked authority artifacts;
the local manifest receipt is rematerialized so checkout roots never enter the
portable cache identity. Add `--cache-files` when deliberately testing the
finer-grained cache: each entry is addressed by analyzer and grammar digests,
source path and the committed blob SHA-256, so unchanged files can survive a
repository revision change while changed files are reparsed. That mode is not
the workflow default because its current large-source wall-time benefit is not
yet established. `--cache-components` instead retains one revision-fenced
repository projection: sorted base facts plus the compact module, call and
file-index data needed to rebuild cross-repository edges and candidates. A
source-set change can therefore reanalyze only changed repositories without
trusting stale cross-repository resolution. This mode is enabled in the
trusted-main workflow after a positive real-source changed-revision benchmark.
Missing or corrupt entries are rebuilt. Cached and uncached runs emit
byte-identical authority artifacts; a separate
`agentlab.analysis_cache_execution.v1` line on stderr reports only
execution-local hit/miss/repair counts.

## Local iteration and public Action

Run the same checks used by `rust-code-analysis.yml`:

```sh
cargo fmt --all --check
cargo test --locked -p agentlab_code_analysis
cargo run --locked -p agentlab_code_analysis -- /path/to/source-repo /tmp/ast-evidence
```

Tests cover syntax extraction plus real Git/CLI execution: multiline
imports/ArkUI, comment exclusion and method ownership, whitespace-stable IDs,
fixed committed source independent from dirty/untracked Workspace files,
byte-identical repeated exports and retained invalid-syntax evidence. The
multi-repository integration tests additionally construct three real Git
repositories, prove direct and transitive cross-repository impact, retain an
unresolved import as a difficulty candidate, and reject symbolic revisions and
missing bound targets.

The independent Rust Action runs on main pushes, relevant pull requests and
manual dispatch. After Rust tests it fetches the fixed public Harmony source,
runs this CLI directly with no Python and retains complete facts/coverage.
The separate knowledge-seed Action tests TableGit/history/import integration;
run34750910500 passed733-row roundtrip and recovered17 files/9640588 bytes.
A successful syntax-coverage job can contain declared grammar gaps. Inspect
analysis.json; it is not a claim of full ArkTS or HAP qualification.

## stateStyles grammar repair

The explicit grammar extension under grammar/ resolves the earlier stateStyles
object-value leading-dot blocks. Original upstream still fails the minimal
fixture; the extension passes, ordinary objects stay valid and malformed style
syntax stays reported. Fixed code-workshop now has556/556 syntax-clean files,
17188 facts and no parse-error nodes. The original failure artifacts are retained.
The receipt includes a digest of grammar/scanner source. This corpus result is
not universal ArkTS, type/call/dataflow, HAP or subject-Agent qualification.
The public Action regenerates the committed parser with pinned tools and checks
it has no diff. Six Rust tests now pass including the baseline/extension check.
Parallel CLI fixtures use a process-local counter as well as time/PID so tests
do not race over the same Git directory on hosts with coarse clocks.
