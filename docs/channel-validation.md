# Channel validation and selective promotion

`aldev → almain → alprod` are independently selected release references.
The Git maintenance branch `main` is separate from the `almain` release channel.
A passing dev is not automatically promoted to main; a passing main is not
automatically promoted to prod. New candidate components are published once.
Promotion reuses their URLs, hashes and independently pinned SDK/control tools.

Every validation starts from a frozen composition on a fresh GitHub runner.
The channel can advance later without changing that run's selected bytes.
Source cut, target channel, qualification run and previous channel reference
must remain inspectable for promotion and rollback.

| Channel | Required coverage |
|---|---|
| aldev | Clean installation, protocol discovery, copy-tree Mock, TableGit recovery; feature-specific regression for the selected changes |
| almain | Dev baseline plus cached reinstall, Btrfs Mock, Harmony iterations, restart/Fork parity |
| alprod | Main baseline plus real Agent execution and repeated cold recovery |

Required baseline sets are executable in `scripts/channel-plan.py`. Feature-specific regressions remain additional evidence; they do not substitute
for the baseline.
`Freeze channel validation plan` now downloads its frozen input artifact on a
separate fresh runner and executes clean install, protocol discovery, copy-tree
Mock and real TableGit recovery. Runtime and provisioning SDK are selected from
that artifact, never from the current global demo pins. Each check retains its
log and verdict, including failures; the qualification receipt is bound to the
composition identity and GitHub run. Cached reinstall, Harmony and repeated
cold recovery adapters are also connected. Btrfs and a separate Mock restart/Fork parity campaign are connected too.
Parity here means the public standalone campaign, not formal device parity.
For prod, the reusable real-Agent workflow consumes the same frozen artifact
on its own fresh runner. Pi uses the configured LM Gateway; independent Harmony
compilation and TableGit persistence/cold recovery must both succeed. A final
job closes all required checks against the same composition identity. A missing
or failed real-Agent check leaves prod unqualified. Recovered prior capture does
not substitute for fresh real-Agent execution in this check.

Select and promote explicitly:

```bash
# Daily candidate validation.
gh workflow run channel-plan.yml --ref main -f target=aldev -f candidate=40ecdf4b-linux-x64
# After that run succeeds, prepare an immutable qualified dev cut.
gh workflow run channel-promotion.yml --ref main -f qualification_run_id=<dev-run-id> -f activate=false
# Independently select that dev cut for deeper main validation.
gh workflow run channel-plan.yml --ref main -f target=almain -f upstream_release=qualified-aldev-<dev-run-id>
# Prepare main from its successful run, then select it for prod.
gh workflow run channel-promotion.yml --ref main -f qualification_run_id=<main-run-id> -f activate=false
gh workflow run channel-plan.yml --ref main -f target=alprod -f upstream_release=qualified-almain-<main-run-id>
```

Qualified cuts contain only lock/publication/qualification metadata. Original
component URLs, hashes, images, SDK and controller identities remain unchanged.
Standalone Harmony/SessionFS and MCPGit validation dependencies are frozen
separately with `validationDependenciesSha256`, carried through selected upstream
cuts, and checked when closing results. TableGit capture context records these
identities plus target channel and source publication/lock digests.
An older qualified upstream cut can be selected even if the fixed channel has
advanced. Qualification is distinct from activating the fixed channel.

`activate=true` explicitly requests a fixed-pointer switch. Retained
`dActivation`, `formalHarmonyHapRestartParity` and `aBCPromotion` deployment
gates must have passed; full normalized whitebox coverage is not an extra
public-release prerequisite. Unpassed deployment gates remain visible in the
qualified publication. This preserves the existing formal gates while allowing
public fresh-runner validation to proceed.

Immutable lock/qualification assets are published before a single channel
publication pointer changes. The pointer explicitly references the immutable
lock URI and digest; consumers read the pointer first, then that lock. They do
not combine two mutable channel assets. Old lock assets remain available for
existing references. Before switching, activation saves the previous pointer as a content-addressed
Release asset and declares its explicit URI/hash for rollback. Repeated execution
checks already-active metadata or an already-uploaded snapshot before proceeding.
Activation reads the pointer back to verify the exact selected metadata. Rollback explicitly selects a previously qualified cut
without rebuilding components. Public standalone parity and actual host/device
deployment evidence remain distinct.
