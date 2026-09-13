---
name: agentlab-codebase-analysis
description: Maintain evidence-backed semantic knowledge of a target repository for benchmark construction.
metadata:
  agentlab-role: maintenance
  agentlab-stage: repository-analysis
---

# Codebase analysis maintenance

Read the pinned source and its existing maintainer guidance. Identify project boundaries, architecture, build/test entrypoints, behavior contracts, state transitions and cross-file responsibilities. A strong construction Agent may do this work; it is separate from the assessed Agent.

Maintain stable `maintainer_skills` rows containing Markdown guidance and explicit source/fact references. They describe how to maintain the target codebase, not how to administer AgentLab. Revisit the same row when knowledge changes so Git history retains the semantic delta.

Every claim needs a source location or analysis record. Distinguish observed behavior from inferred intent. Use program facts to support the semantic model; do not manufacture dependency edges from prose. Preserve unresolved questions as gaps.

Use [program analysis](../agentlab-program-analysis/SKILL.md) for structure and [seed extraction](../agentlab-seed-extraction/SKILL.md) to turn grounded knowledge into tasks. Archive searches and generic TableGit analysis requests, exact input cuts and complete results in `program_facts`.

Develop in TableGit. Export a fixed cut with the existing [three-table workflow](../../examples/knowledge-seed/README.md), one stable JSONL per table. Release files are publication snapshots, not a second live authority.
