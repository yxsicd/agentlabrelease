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
| Component installer | Verified native controller/lock acquisition, stdout-only plan, shared-reference discovery, full read-only reuse and durable current/previous/pending qualification | Full-instance activation, rollback or uninstall; plan is not payload acceptance |
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

The selected [controller component](../release/components/control-f2e87a57-linux-x64.json)
is independent of the unchanged runtime composition. It adds an explicit
all-new component installation policy and the native deployment planner, which
is plan-only and cannot activate an instance. Each changed cut requires a new
GitHub download and cold component installation on independent empty Linux and
WSL2 daemons; reuse is supplementary. Source tests are not that qualification.
The [current cold-component proof](evidence/public-cold-components-20261009.json)
records a released-installer download and new-cache/configuration installation
on empty Linux/WSL2 daemons, independent image/READY/manifest readback, explicit
old-state cold refusals and unchanged protected shared daemons. Linux also
passed exact component removal and another public-download cold reinstall with
a retained synthetic data marker. This does not qualify full-instance uninstall,
an authenticated workspace, a physically blank host or the complete flywheel.
The test daemons are stopped while their private data/receipts are retained.
Immutable component descriptors retain their original publication-time scope;
the aggregate selects this later evidence without rewriting those descriptors.
The [historical warm transaction proof](evidence/component-transactions-20261009.json)
belongs to controller 01b77751 and its original entrypoint. It remains immutable
evidence and is never borrowed to qualify this new controller or wrapper.
It preserves native no-write planning and read-only tree verification with no-copy mounts,
consumer/ownership admission and uniquely fenced fresh-volume cleanup. Its plan
explicitly leaves payload/helper/template qualification unperformed. A real
install must prove its exact static Linux helper can execute through the selected
Docker daemon before volume writes. The earlier 90496dc0 controller at public
cut 54caf08 passed plan, inspect,
existing-pack reuse and cold/RO/RW/drift fixture gates independently on Linux and
WSL2. The evidence receipt preserves the earlier 0700-helper permission failure
and its corrected-entrypoint reruns; complete cold composition and full Harness
remain unqualified. Source tests alone are not deployment acceptance.
The public Rust acceptance uses one initially absent fixture namespace. Success
removes its exact containers and volume. Failure retains diagnostic resources;
inventory and prove ownership/references before an explicitly authorized retry
cleanup. Never delete a same-name volume merely because an earlier check found
it absent: a concurrent install may have won that namespace.

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
   Material intake must accept arbitrary authorized HTTP(S) repository URLs and
   source archives through one verified SourceSnapshot contract. The
   [input contract](../skills/agentlab-harness-developer/references/source-material.md)
   now has pure Rust declaration/inventory gates; actual acquisition, safe
   extraction and existing Git-only consumer migration remain open. This does
   not alter the installed controller, components or full-instance qualification.

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
