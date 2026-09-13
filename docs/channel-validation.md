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

Required baseline sets are executable in `scripts/channel-plan.py`. Feature
checks add to a selected dev plan; they do not substitute for its baseline.
`Freeze channel validation plan` now downloads its frozen input artifact on a
separate fresh runner and executes clean install, protocol discovery, copy-tree
Mock and real TableGit recovery. Runtime and provisioning SDK are selected from
that artifact, never from the current global demo pins. Each check retains its
log and verdict, including failures; the qualification receipt is bound to the
composition identity and GitHub run. Cached reinstall, Harmony and repeated
cold recovery adapters are also connected. Btrfs, dedicated parity and real
Agent tier adapters are still pending; their checks remain `not_run`, so deeper
tiers cannot qualify accidentally. This workflow does not activate channels.

Next complete the dedicated deeper-tier adapters and activate only the selected
channel after its required checks pass. Publish immutable lock/qualification metadata before changing a single
channel pointer, so readers cannot combine a new publication with an old lock.
Rollback selects a previously qualified composition without rebuilding it.
Public fresh-runner qualification and actual host/device deployment evidence
remain distinct; this plan does not silently clear D/A/B/C or fixed gates.
