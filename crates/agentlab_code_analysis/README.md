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
