# AgentLab public developer entrypoint

This repository contains released AgentLab packages and consumer guidance, not
the private maintenance workspace.

Start with `SKILL.md`, which selects the deployment or deployed-instance journey.
Deployment uses `skills/agentlab-deployment/SKILL.md`; instance operations use
`skills/agentlab-harness-developer/SKILL.md`. Private source is not a prerequisite.
Use `skills/agentlab-skill-methodology/SKILL.md` for method/instance layers.

Select maintenance versus operations via `skills/registry.json`. Maintenance
Skills own benchmark methods and seed publication; operations deploy public
components or consume fixed snapshots and return evidence for the next cut.
Here `maintenance` means maintaining evaluation methods, target-project knowledge
and task seeds while USING AgentLab. It does not mean changing AgentLab platform
implementation. Reusable usage methods belong in this release Skill library;
target-instance Skills and observations follow the methodology's selected authority profile.

For target-specific Git knowledge branches, read
[Git target knowledge and aggregation](skills/agentlab-skill-methodology/references/git-knowledge-branches.md).
The user-selected hub is agentlabrelease: `knowledge/catalog` indexes bindings,
`knowledge/targets/<targetId>` receives each target's independent `al-knowledge`
history. This profile authors reusable target content in Git; AL retains live
execution facts and imports pinned guidance without dual editing. Business
branches remain unchanged. Private evaluator data never enters these public refs.

Use the existing experiment-learning promotion path instead of creating another
knowledge store or treating a platform-maintainer handoff as consumer guidance.

Read `skills/agentlab-harness-developer/SKILL.md` completely before designing or
running an Agent evaluation. Treat manifests and receipts as authority; never
infer a capability from a filename, running container, or unpinned `main`.

```text
Task Seed -> Session -> Turn/Event -> Checkpoint Cut -> Fork Attempt -> Analysis
```

The Harness owns environment, filesystem, LLM/MCP observation, capture, and
lineage. A Code Agent is a replaceable participant and may start fresh after a
fork. Native Agent session restoration is an optional adapter capability, not a
portable baseline.

Never place API keys, Gateway credentials, Agent home directories, or captured
session data in this release repository.
