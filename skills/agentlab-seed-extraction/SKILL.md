---
name: agentlab-seed-extraction
description: Generate evidence-linked multi-turn task seeds from semantic Skills and program facts.
metadata:
  agentlab-role: maintenance
  agentlab-stage: seed-extraction
---

# Seed extraction maintenance

Combine repository maintainer Skill rows, typed dependency facts and archived analysis results from fixed cuts. Construct tasks with a concrete requirement, baseline source/environment, cross-file impact, staged user demands and observable acceptance checks.

Write stable `evaluation_cases` task rows with source/knowledge cuts and analysis references. Keep assessed-Agent-visible requirements separate from operator-owned reference patches and grading evidence. Do not disclose a gold implementation as part of the task prompt.

Use a strong construction Agent or deterministic generator as appropriate. Capture construction actions as Harness-owned evidence too. Agent-proposed seeds are candidates until independently calibrated; quality of the construction Agent is not the assessed-Agent score.

Start with dependency-supported scenarios, not arbitrary mutations. A multi-turn seed should include meaningful continuation or changed requirements and regressions that earlier decisions can influence. Preserve exact checkpoints for counterfactual Fork comparisons when the installed Harness supports them.

Send candidates to [benchmark calibration](../agentlab-benchmark-calibration/SKILL.md). Maintain proposed/unbuildable/ambiguous cases with their failure evidence instead of deleting them. Freeze calibrated cases for [operations](../agentlab-benchmark-operations/SKILL.md); feedback creates a later knowledge cut.
