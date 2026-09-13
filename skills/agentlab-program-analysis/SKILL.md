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
0.27.0 and tree-sitter-arkts0.2.0. It lowers CST nodes to module/symbol/call,
assignment/decorator/ArkUI facts with exact source spans. Multiline imports are
AST-derived, not lexical regex matches. Tree-sitter is not a semantic type AST;
calls and assignments remain unresolved. Read the crate README for command and
coverage. The fixed code-workshop corpus has one stateStyles grammar gap; save
its full error evidence and adapt grammar rather than rewriting source bytes.
