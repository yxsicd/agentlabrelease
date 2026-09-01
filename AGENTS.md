# AgentLab public developer entrypoint

This repository contains released AgentLab packages and consumer guidance, not
the private maintenance workspace.

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
