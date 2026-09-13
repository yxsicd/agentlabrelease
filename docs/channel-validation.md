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
`Freeze channel validation plan` freezes candidate/upstream metadata, checks the
promotion path and retains original inputs. It does not run the listed checks
or activate a channel. Existing public/basic and real-Agent workflows remain
actual acceptance evidence until their jobs consume this plan directly.

Next connect those executable demos to the frozen plan, collect one target-bound
qualification receipt, and activate only the selected channel after its checks
pass. Publish immutable lock/qualification metadata before changing a single
channel pointer, so readers cannot combine a new publication with an old lock.
Rollback selects a previously qualified composition without rebuilding it.
Public fresh-runner qualification and actual host/device deployment evidence
remain distinct; this plan does not silently clear D/A/B/C or fixed gates.
