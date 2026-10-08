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
