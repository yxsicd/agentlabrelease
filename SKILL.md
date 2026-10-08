---
name: agentlab
description: Deploy AgentLab from GitHub or operate a deployed instance's repository-understanding and evaluation flywheel.
---

# AgentLab public entry

There are two consumer journeys. Select one; private source access is never a
prerequisite.

- **Human -> Agent -> GitHub -> deployment:** read
  [deployment](skills/agentlab-deployment/SKILL.md). This includes historical
  installation discovery and data-preserving uninstall.
- **Human -> Agent -> AgentLab instance -> flywheel:** read
  [instance operations](skills/agentlab-harness-developer/SKILL.md). Start from
  the operator-supplied instance SKILL URL, not an assumed hostname or port.
  Prefer supervisor-managed, context-isolated subagents assessed through remote
  Participant MCP; no independently configured second model key is required.

Read [manifest.json](manifest.json) for the single current component graph,
participant default and acceptance limits. Do not select an installation from
historical root versions or experiment notes.

Pin this repository to a full Git commit before executing its scripts. GitHub
distributes public instructions, executables, templates and immutable manifests;
the deployed instance owns runtime state and authenticated evidence. Credentials
and private evaluator answers are never public assets.

Use the [registry](skills/registry.json) for progressive method selection. There
is one current consumer contract, not a compatibility matrix of old installers.
Historical releases remain immutable evidence, not current installation recipes.

Report component acquisition, instance readiness, functional evaluation,
checkpoint/Fork and learning benefit separately. Unsupported operations stop
with the missing capability and its owning component; never borrow a private
maintainer script or a pre-existing host configuration to claim a public pass.
