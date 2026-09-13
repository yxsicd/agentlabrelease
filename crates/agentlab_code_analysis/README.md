# Rust ArkTS program analysis

`agentlab-code-analysis` parses committed `.ets/.ts` bytes using pinned Rust
Tree-sitter 0.27.0 and ArkTS grammar 0.2.0. No Python runtime is needed for this
analyzer. Tree-sitter provides a concrete syntax tree; this crate lowers it to
structured program facts, not a type-checked semantic AST.

```sh
cargo build --locked -p agentlab_code_analysis
./target/debug/agentlab-code-analysis /path/to/source-repo /tmp/ast-evidence
```

Output is sorted `program_facts.jsonl` plus `analysis.json` with source cut,
parser/grammar versions, counts and exact data digest. It captures multiline
module references, declarations/methods, syntactic call/assignment locations,
decorators, ArkUI nodes and complete parse-error text/spans. IDs use source path,
syntax role, scope/name and occurrence rather than byte offsets; spans still
reflect the exact source cut. Calls are unresolved syntax observations.

First fixed code-workshop run parses556 files:555 without syntax errors and one
with five recovery/error nodes at `products/tv/src/main/ets/component/BarItem.ets`.
The unsupported form is leading-dot style statements inside `stateStyles` object
value blocks. Preserve this as grammar coverage debt, not source/Agent failure.
Do not rewrite source with regular expressions to manufacture clean parsing.
Adapt the grammar with a minimal regression fixture and regenerated parser when
this gap is addressed. Clean syntax does not imply type or runtime correctness.

The knowledge flywheel now invokes this Rust binary and imports selected-scenario
AST facts into TableGit. Its current TableGit orchestration is still Python;
that transport/method-construction code is separate from this Rust analyzer.
Full source syntax facts remain in the captured AST evidence. Type resolution,
resolved calls, control/dataflow and whole-corpus TableGit ingestion are further
capabilities, not claims of this version.
