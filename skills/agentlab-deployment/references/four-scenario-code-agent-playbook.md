# AgentLab — Four-Scenario Deployment Playbook for Code Agents

**Purpose:** A fresh Code Agent on a new or existing machine should choose the shortest safe path to a working AgentLab installation. Optimize for real service availability and preservation of useful data, not an elaborate deployment framework.

**Current public capability (2026-10-11):** The selected public release qualifies **component cold installation only**. Its manifest explicitly states **fullInstanceLifecycle: not-published**. S1 on a blank machine must NOT be reported as a working complete AgentLab Harness until a real publicly supported instance bootstrap and functional health check succeed. S2–S4 remain operational reasoning paths, not promises of currently shipped one-command lifecycle APIs.

**中文目标：** 新机器上的 Code Agent 先观察现场，再在四种路径中自主选择：全新安装、兼容升级、保留数据重建、彻底清除重装。以最少必要操作完成任务。版本和资源差异由 Agent 基于证据判断，不使用固定历史版本脚本。

**Entry:** [AgentLab public SKILL](../../../SKILL.md) → [deployment SKILL](../SKILL.md) → this playbook. All public release instructions and binaries come from the same pinned Git commit and its referenced immutable assets. No private maintainer repository, fixed hostname, AWMCP endpoint or pre-existing AgentLab is a prerequisite.

## 1. Choose a path, then act

| Mode | Typical machine state | Agent's fastest safe approach | Data policy |
| --- | --- | --- | --- |
| **S1 — Clean install** | No relevant installation or retained instance state; host meets the chosen release's requirements | Inspect prerequisites once; download exact current release; install and verify the service | New data |
| **S2 — Compatible upgrade** | Existing instance works; service topology and persistent-data format remain compatible | Keep data and stable dependencies; replace only changed programs/config; restart only affected services; verify | Preserve in place |
| **S3 — Incompatible rebuild with data retention** | Old components, controller, layout or runtime contracts cannot be upgraded safely in place | Save data and identities, stop the old *owned* execution, build a fresh instance, restore/import only compatible data | Preserve recoverable data |
| **S4 — Clean reset and reinstall** | The user explicitly chooses to discard the selected instance's old data, or confirms incompatible data should be discarded | Identify exact owned resources, uninstall them, remove the explicitly authorized data set, then follow S1 | Purge only authorized instance data |

These are four **decision paths**, not four permanently hardcoded installers. Version strings are clues; component APIs, actual manifest/schema, data formats, dependency references, operational health and user intent decide compatibility.

**Default priority:** S2 if safe; otherwise S3 if any useful data may remain; S4 only with explicit data deletion authorization. Never equate "reinstall" with "wipe data." If there is genuinely no installed state, S1.

## 2. Minimal discovery — one bounded pass

Before installing or altering resources, answer only the questions necessary for this instance:

1. **What is requested?** New installation, upgrade, rebuild, or wipe? Does the user intend to keep projects, knowledge, Agent histories, MCPGit state, SessionFS state, configurations or credentials?
2. **What host can run this release?** OS/architecture, Docker/runtime availability, disk, ports, network and credentials *present but never printed*. Read the selected release's supported-platform contract; don't assume every Linux/WSL/ARM machine is supported.
3. **What is here already?** Locate relevant service/container/process state, its install root, immutable program version or digest, persistent volumes/paths, live and stopped consumers, and restart policy. Use the shortest relevant inspection; avoid whole-disk searches.
4. **Is this an upgrade or a new layout?** Compare actual schema and compatibility declarations, service interface, selected immutable components, persistence locations and migrations. If uncertain, choose a non-destructive plan.
5. **Can the public release really finish the job?** Read its exact current manifest, deployment SKILL and executable help. Do not invent lifecycle commands or silently substitute an unselected historical controller.

Typical **read-only** observations, use only those relevant and available:

~~~sh
uname -s
uname -m
command -v docker && docker info --format '{{.ServerVersion}}'
df -h
docker ps -a --no-trunc
docker volume ls
~~~

For historical AgentLab installations, prefer the public [resource inventory](../../../scripts/agentlab-resource-inventory.sh), plus targeted service/startup and native mount/loop inspection only when present. Docker volume names, image tags, directory prefixes or Compose names **alone** do not prove ownership. Check relevant running **and stopped** consumers.

At the end of discovery, make one compact choice:

~~~text
MODE: S1 | S2 | S3 | S4
WHY: key host/compatibility/ownership evidence (2–4 facts)
KEEP: exact useful data and shared services
CHANGE: exact program/service resources, in execution order
DATA: keep | backup+restore | explicitly purge selected set
BACKOUT: how to recover if verification fails
BLOCKER: only a genuinely missing capability, permission or destructive scope
~~~

Do not ask the user to fill a large checklist. Ask only when a missing destructive-data decision or credential genuinely blocks execution. A clear "wipe this AgentLab instance including its data" instruction already establishes the intended data-loss scope; do not repeatedly ask for confirmation of every normal step.

## 3. Execute the selected path

### S1 — Clean installation

1. Inspect prerequisites once. Select a private installation root and available ports; use existing compatible shared dependencies if they are explicitly allowed and do not modify unrelated services.
2. Resolve the current public release to a **full Git commit**; follow that exact manifest, verified assets and installer. Prefer its documented installer over manually reconstructing Docker/Compose commands.
3. Install only what is missing. For the current public **component-only** installer, the supported cold entry is:

~~~sh
# From an exact-commit checkout of yxsicd/agentlabrelease.
# INSTALL_ROOT must not exist yet; the chosen Docker daemon must be an
# explicitly selected environment in which the selected components are absent.
bash scripts/agentlab-composition-install.sh online --cold --root "$INSTALL_ROOT"
bash scripts/agentlab-composition-install.sh inspect --root "$INSTALL_ROOT"
bash scripts/agentlab-composition-install.sh inspect-registry --root "$INSTALL_ROOT"
~~~

The optional online --plan is a preview and **can create its own acquisition/cache files**. If used, give it a **different** disposable plan root; never assume a prior preview root remains eligible for --cold.

4. If the selected release exposes an independently qualified complete-instance start/activation path, execute its real contract, then check authenticated service health and one representative task. Otherwise report the achieved **component installation** separately from **complete instance availability**.

**Current release limitation (2026-10-11):** The public manifest declares component cold-install qualification, but complete AgentLab Harness lifecycle is **not published**. A Code Agent can complete the published component path, but must not claim that S1 delivered a working full Harness unless an actual public, pinned, qualifying provisioner/runtime path is available. Report the exact missing part rather than inventing private commands.

### S2 — Compatible, data-preserving upgrade (the common fast path)

Use this when old and new service/data contracts are compatible, or there is a specifically supported in-place migration. **Avoid reinstalling unchanged images, volumes, SDKs and dependencies.**

1. Identify the current instance's owned services and persistent data. Record the currently working version/digests and one short restore point, especially if a data schema migration is involved.
2. Resolve the destination release and compare changed components, configuration schema, interfaces, data layout and reversible migration capability.
3. Stage/verify changed binaries or images; retain existing data mounts, credentials and unchanged dependent services.
4. Stop or restart **only affected** services in the order required by the actual dependency graph. Do not rebuild SessionFS or MCPGit state just because a program binary changed.
5. Verify version, authenticated health, one real operation and unchanged data identity/contents. If the update fails, return to the previous compatible program cut without rolling back incompatible data blindly.

Use the selected public release's documented upgrade command **if it actually exists**. The present public component installer uses --cold for a new component installation; **do not run that against an existing instance as an upgrade shortcut**. If no compatible supported upgrade route exists, choose S3 or return a precise unsupported-capability result; do not guess a deploy upgrade CLI.

### S3 — Rebuild incompatible programs while retaining data

Use when a major layout/runtime/API change makes S2 riskier or slower but projects, knowledge, histories or other data might remain valuable.

1. Map **only this instance's** execution resources and useful data. Classify external/shared or unknown resources as **keep**. Preserve configuration needed to read old data, plus rollback evidence.
2. Create a readable recovery copy/export of important data before tearing down old execution. For schema conversion, verify a small representative item and the selected migration's real support; do not force incompatible records into the new schema.
3. Quiesce/disable old **instance-owned** process and startup resources; remove only exclusive outdated execution artifacts. Old data and backups remain untouched. Inspect SessionFS mounts/loop users and stopped Docker consumers if present.
4. Provision a **new isolated instance root** using S1. Connect/import compatible data **selectively**; keep incompatible originals offline for later recovery.
5. Verify real service/business readiness and recovered data before retiring the old runtime further.

If ownership is unclear, preserve the object and continue with an isolated new root where feasible. If data cannot be migrated, report **"new service running; old data retained, migration incomplete"** rather than destroying it or reporting full success.

### S4 — Full selected-instance removal and fresh installation

Use only when the user has explicitly authorized discarding the selected AgentLab instance's data. This is **not** permission to wipe the machine or other applications.

1. Identify exact instance-owned startup/process/container/network and data resources. Show the final deletion scope and distinguish shared/foreign/unknown objects. The user may explicitly waive a backup; record that decision, and give a concise irreversible-loss warning before the destructive step if the scope was not already explicit.
2. Stop only the selected instance and disable its owned recovery/startup paths. Recheck currently referenced volumes, native mounts, active loop devices and foreign consumers immediately before deletion.
3. Remove only **verified exclusive** execution resources and the **explicitly authorized** persistent data set. Retain shared MCPGit, global Docker, external applications, unknown resources, and any still-referenced mounts. Never use broad Docker/system/volume prune, wildcard host deletion or blanket Compose down -v as a substitute for ownership reasoning.
4. Follow S1 with a new private root; verify a fresh instance and report which old data was permanently discarded.

If a supposedly owned resource has an unexpected consumer, **do not force-remove it**. Finish everything that is safely attributable, then report the one blocked object with its real conflicting reference. No need for a global rollback engine.

## 4. How an Agent should generalize instead of memorizing scripts

- **Discover, compare, execute, verify.** A name or version number is not a state machine. Use actual service/API/schema/mount evidence and the public release's offered commands.
- **Change as little as possible.** A compatible upgrade should not rebuild a data volume, and an incompatible rebuild should not delete all data.
- **Follow immutable selections, not historical examples.** Read manifest.json and selected descriptors at the checked-out Git SHA. An inspector candidate is not the selected controller; an older qualification does not prove the current full Harness works.
- **Use tools proportionally.** A fresh Code Agent with shell/Git/Docker access may issue normal documented installation commands. In a discovery-only task, it should use only read tools. Switch to effectful tools when the selected path is admitted; do not demand a complex policy engine first.
- **Prefer progressive diagnosis.** On failure, inspect the failed step and its immediate dependencies once. Reattempt only if idempotency or exact-state readback makes replay safe. Do not repeatedly reprovision everything.
- **Separate data ownership from program ownership.** An executable may belong to an instance while its storage is shared or irreplaceable. Preserve unknown things.
- **Keep secrets private.** Use host credential files or an operator mechanism that scopes access to the intended user/process; never paste tokens into prompts, public Git, logs or receipts.
- **No phantom functionality.** Do not claim a command or full-instance capability is present merely because this playbook describes its desired behavior.

For old installations whose receipt is missing, consult the [version-independent uninstall reference](historical-uninstall.md), but use its **principles** and observed ownership graph, not a fixed script for one old version.

## 5. Completion means the user's service actually works

A normal Code Agent should leave a concise operator receipt:

~~~text
PATH: S1/S2/S3/S4 and why
RESULT: complete | partial | blocked
SOURCE: pinned release commit, selected program version/digest
CHANGED: instance-owned programs/services/resources touched
DATA: retained/migrated/purged exact categories; unresolved old data identified
VERIFIED: service health + one real representative operation + retained data readback
RECOVERY: previous version, retained backup/root or precise recovery action
NEXT: one concrete remaining action only if not complete
~~~

Do not equate "downloaded", "container running", "component installed" or "plan emitted" with a functioning AgentLab business instance. If the release doesn't supply complete bootstrap, report **blocked: full-instance-lifecycle-not-published** (or the precise newly observed gap) and direct the operator to an already available authorized instance or separate business-pilot route, rather than inventing an unofficial full installer.

**Success target:** get the requested machine to a verifiably usable state with the fewest reasonable steps and the least unnecessary data loss. More exhaustive release engineering and multi-host B0–B6 qualification can happen later; they are not prerequisites for an ordinary permitted single-machine install or upgrade.
