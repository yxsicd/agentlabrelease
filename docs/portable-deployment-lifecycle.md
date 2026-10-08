# Public distribution and lifecycle

## One current product contract

[manifest.json](../manifest.json) selects one component graph, one deployment
journey and the default remote participant model. The containing public Git
commit is its authority. Read [SKILL.md](../SKILL.md) before executing that cut.

GitHub is the only distribution dependency. AWMCP is a maintainer's test transport,
not a consumer requirement. A consumer must not need private source, a particular
host, a LAN, retained credentials or a pre-existing installation.

Unchanged Base, Tools, SDK, emulator and Program artifacts retain their immutable
identities. Only changed components are published; the aggregate graph references
their exact digests. Historical releases remain evidence, not installation
alternatives or compatibility fallbacks.

## Executable scope

| Surface | What is executable now | What it does not prove |
| --- | --- | --- |
| Component installer | Verified native controller/lock acquisition, component volumes and runtime image installation | Running authenticated full Harness |
| Selected MCPGit installer | Dedicated loopback instance, private credentials, verified unchanged activation reuse and authenticated read-only kernel checks | AgentLab Session/template/Fork integration |
| Resource inventory | Bounded, read-only Docker-context JSONL without credential/environment contents | Complete native/systemd/loop ownership or deletion authority |
| Historical uninstall | Version-independent, exact-target procedure with data preservation | A published native one-command lifecycle API |

The [deployment Skill](../skills/agentlab-deployment/SKILL.md) owns the commands
and preflight; do not duplicate them with host-specific recipes. The selected
MCPGit dependency is [this integration descriptor](../release/integrations/mcpgit-prod-linux-x64.json).
Its installer and Program identities are independent: installer safety fixes do
not force a Program, Base or Tools rebuild.

A successful exit or health endpoint alone is insufficient. Require the selected
artifact identity, actual authenticated operation, independent readback and
resource delta. Repeat-install acceptance includes unchanged container identity,
configuration/credential bytes and modes, data identity and activation receipt.
Changed or unqualified activation must not be silently recorded as unchanged.
Credentials and raw private receipts remain on the selected private root.

Current-cut MCPGit unchanged activation and exact-ID uninstall/preserve passed on
both hosts. The current component wrapper passed on aiwsl with no selected asset
references. On hwlinux, artifact preflight passed but execution was held because
the tools volume is used by an active protected instance: this controller has no
independently established no-write shared-volume reuse proof. Neither matching
labels nor a historical `reused` receipt resolves that gate. Do not overwrite or
repair an active shared supply to make installation pass.

## Remaining product closures

1. **Existing native controller -> durable full instance.** Extend the Rust
   controller/provisioner with one owned-resource registry connecting acquisition
   to MCPGit template qualification, SessionFS, persistent runtime configuration,
   authenticated discovery/readiness and recovery. Verify install, inspect,
   repeat install, changed-component upgrade, rollback, uninstall-preserve and
   separately authorized purge. Do not relabel a disposable SDK probe as a
   production provisioner or introduce a second deployment engine.
2. **Existing Harness -> generic Attempt-scoped remote participant.** Bind the
   supervisor's explicitly isolated subagent to one Attempt and frozen context
   cut; issue/revoke restricted participant credentials; enforce budget,
   cancellation and cross-Attempt/Control/checker denial; capture actions and
   independently seal/read back evaluation results. The preferred model requires
   no second provider key. A context artifact digest does not prove model context
   consumption.
3. **Real five-ring acceptance.** Qualify Session/template/checkpoint/Fork with
   the selected MCPGit cut, then repository understanding -> program correction ->
   maintenance verification -> case generation/execution -> reviewed evidence
   consumed by the next round. Qualify Harmony emulator/ohosTest and performance
   independently when the selected scenario requires them.

These are code and execution gates. More instructions, fixture passes or retained
containers cannot change them to PASS. Current manifest limits remain explicit.

## Evidence and historical retirement

Use [the sanitized qualification receipt](evidence/portable-deployment-20261008.json)
for exact source cuts, artifact identities, two-host operations and preserved
failures. It separates current consumer qualification from earlier component and
retirement evidence. Native SessionFS needs its own loop/Btrfs/systemd readiness;
Docker acquisition does not establish it.

For any historical installation use
[the ownership/reference-based uninstall procedure](../skills/agentlab-deployment/references/historical-uninstall.md).
Preserve data by default. Purge requires separate authorization and exact checked
targets; never prune shared resources. Earlier retirement receipts and verified
private backups remain retained. The prior detailed maintenance narrative is
[immutable history](https://github.com/yxsicd/agentlabrelease/blob/41b447895cd7c357470d261e465e5a9f0e8a6eeb/docs/portable-deployment-lifecycle.md),
not the current installation route.

Flywheel maturity remains the historical **82%** estimate, not a newly measured
whole-system score. Component/deployment work does not independently raise it.
