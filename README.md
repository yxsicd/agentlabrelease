# AgentLab

Public distribution and Agent-consumable instructions for deploying AgentLab and
operating its repository-understanding/evaluation flywheel.

**Start at [SKILL.md](SKILL.md).** A consumer never needs the private AgentLab
maintenance repository, a specific host, a LAN, or maintainer credentials.

| Human request | Agent entry |
| --- | --- |
| Deploy, inspect, upgrade, roll back or uninstall | [Deployment Skill](skills/agentlab-deployment/SKILL.md) |
| Understand repositories, correct analysis, validate maintenance operations, generate/evaluate cases, return evidence | [Instance flywheel Skill](skills/agentlab-harness-developer/SKILL.md) |

The current [manifest](manifest.json) is the one machine-readable distribution
contract, not an old alpha-version catalogue. Its component graph, installers,
Skills and acceptance limits are checked together by the release validation gate.

Pin a full Git commit before running its scripts. GitHub distributes immutable
components and public contracts; the instance owns authenticated state/evidence.
Unchanged components are reused, not rebuilt for each knowledge or method change.

## Current acceptance boundary

The public component installer prepares the declared Docker image and component
volumes. The selected MCPGit component has separate installation/kernel evidence. Neither
is proof of a fully provisioned AgentLab Harness or a completed real flywheel.
The full-instance lifecycle, Session/template/Fork integration and unified
component CRUD still require independent qualification. Missing capability is a
blocker, never a reason to use a private maintainer shortcut.

- [Component lifecycle and two-host evidence](docs/portable-deployment-lifecycle.md)
- [Generic historical uninstall](skills/agentlab-deployment/references/historical-uninstall.md)
- [Public methods registry](skills/registry.json)
- [Executable verification examples and their limits](examples/README.md)
- [Immutable release graph](docs/release-graph.md)

The active consumer route has no historical installer compatibility fallback.
Old releases, source cuts and failed experiments remain immutable audit evidence.
Historical prose is retained under `docs/archive/`, not loaded as current Skills.
Never publish keys, private Agent homes, user data or evaluator answers.
