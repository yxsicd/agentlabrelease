---
name: agentlab-program-analysis
description: Maintain revision-bound program structure and analysis evidence used to generate evaluation seeds.
metadata:
  agentlab-layer: method
  agentlab-role: maintenance
  agentlab-stage: program-analysis
---

# Program analysis maintenance

Analyze the same source commit as semantic knowledge. Record symbols, imports, call candidates, module dependencies, configuration/resource references and available test/build entrypoints as typed `program_facts` rows. Use stable source-derived IDs.

Prefer a language-aware parser/compiler when available. A lexical extractor or name join is useful but must retain its method and unresolved status; a same-name candidate is not resolved dispatch. Record source path/span, analyzer identity and source revision. Keep semantic Skill links explicit.

Run generic MCPGit table programming/search/SQL over fixed input cuts. Archive code, request/bindings, complete typed result and interpretation as analysis rows. Cases reference those analysis IDs. The existing executable SQL example joins call and symbol candidates; it is not a Harmony parser.

Analyze candidate dependency chains and impact surfaces, then hand them to [seed extraction](../agentlab-seed-extraction/SKILL.md). State coverage and gaps such as reflection, dynamic loading, generated code and missing build dependencies only when they affect this source analysis.

Store source/facts/analysis structurally in TableGit. Build trees and temporary binaries belong to SessionFS Workspace snapshots; do not put multi-GB compiler output into Git. Export with [the three-table workflow](../../examples/knowledge-seed/README.md).

Produce target-instance guidance for this stage as TableGit Skill rows,
separate from the structured facts/tasks/results. Follow
[the two-layer methodology](../agentlab-skill-methodology/SKILL.md) for
method/source lineage and independent layer/role fields.

## Current Rust ArkTS analyzer

Use crates/agentlab_code_analysis (agentlab-code-analysis), pinned Tree-sitter
0.27.0 and the AgentLab grammar extension derived from tree-sitter-arkts0.2.0. It lowers CST nodes to module/symbol/call,
assignment/decorator/ArkUI facts with exact source spans. Multiline imports are
AST-derived, not lexical regex matches. Tree-sitter is not a semantic type AST;
calls and assignments remain unresolved. Read the crate README for command and
coverage. The stateStyles object-block gap is fixed by an explicit pair-value grammar
extension with upstream/extended regression tests. All556 fixed code-workshop
files now parse without syntax errors. Retain the original failure evidence and
the exact grammar digest; this does not qualify typing, resolved calls or HAP.
When improving an analyzer, update existing facts and remove obsolete AST rows
using their actual versions; archive old cuts and do not merely insert facts on
the first run. Test fixtures need process-local uniqueness under parallel tests.

When expanding the selected corpus, validate established dependency paths while allowing additional legitimate paths. A fixed result count confuses broader coverage with regression; archive the query/input cut and describe the observed path count without claiming symbol resolution.

### Feedback multi-round instance

Use [the shared subject runner](../../examples/knowledge-seed/subject/README.md)
with the frozen feedback case. Distinguish stage-one failure/retry state from
stage-two duplicate suppression. Verify actual reactive field declarations with
Rust ArkTS property facts; fixture initialization is not proof of submitted
initializers or decorators. Execute submitted methods without reference repair.
Preserve negative calibration for wrong reset, duplicate requests and wrong
initial state, plus raw/normalized source evidence. The demonstration backend is
an explicit Promise seam; full phone compilation and UI rendering are distinct.
Return stage-specific construction/evaluation guidance to instance Skill rows.

### Loading lifecycle and shared-helper analysis

Rust binding facts preserve declaration kind, owner, type, initializer and exact
byte span. Execute submitted top-level delay constants as well as lifecycle
methods; injected reference constants can hide incorrect Agent changes. Execute
the submitted shared BreakpointType implementation with a controlled platform
enum. Preserve source analyses for the lifecycle, helper and caller separately,
even where local fact IDs coincide. An import seam is source evidence, not
executed UI or resolved runtime call coverage. Calibrate wrong cancellation and
unknown fallback before the staged real Agent case. Invalid source and an Agent
that never reaches tools remain valid failed outcomes with empty typed tables.

When changing a shared helper's default return, identify known values that were
implicitly served by that return. Retest every known value at every later turn.
The loading capture's parent lost the lg branch while adding unknown-to-sm
fallback; a fresh branch retained it. Archive both the failed named check and
submitted helper source before drawing this conclusion. Compile success alone
does not detect this semantic regression.
