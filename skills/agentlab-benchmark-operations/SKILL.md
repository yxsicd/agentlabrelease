---
name: agentlab-benchmark-operations
description: Run fixed published task seeds through AgentLab and retain complete operational evaluation evidence.
metadata:
  agentlab-role: operations
  agentlab-stage: evaluation
---

# Benchmark operations

Consume a fixed Release composition, Skill-library version and three-table snapshot receipt. Import the snapshot into the evaluation repository using [the existing import command](../../examples/knowledge-seed/README.md). Record imported/source cuts and table digests before starting a campaign. Do not regenerate tasks or reinterpret their grading contract during an active assessment.

Use [AgentLab Harness Developer](../agentlab-harness-developer/SKILL.md) for actual Session, Turn, checkpoint, Fork, execution and capture operations. Follow the [public demos](../../examples/README.md) and their capability receipts. Strong supervisors, scripted supervisors and assessed Agents are different roles; supervisor control is recorded evidence, not participant authority.

Pin the participant implementation, adapter, model, environment and task. Keep Agent runtime dependencies outside the project Workspace. The Harness captures controlled LLM/MCP/tools and workspace outcomes independently; retain complete raw test evidence and failures without redaction or subject-supplied capture claims.

Run frozen acceptance checks. Report task/build outcomes, turn counts, timing and supported process metrics; distinguish failed Agent performance from Harness errors and incomplete observation. Only claim SessionFS checkpoint/Fork restoration where exact receipts prove it. Use generic MCPGit analysis rather than adding an analysis API.

Store operational observations/results in the installed Harness tables and Workspace state in SessionFS. Return evidence-linked findings to maintenance for the next seed/knowledge version; do not rewrite the frozen assessed case or update Release seed files from the running assessment.
