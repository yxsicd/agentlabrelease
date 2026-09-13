# Real Harmony compilation demo

Install the [candidate composition](../README.md#install-the-referenced-components), then run:

```sh
python3 examples/harmony-build/run.py \
  --install-root "$AGENTLAB_CI_ROOT" \
  --root "$HOME/agentlab-demo/harmony-build-$(date +%s)"
```

Use a fresh demo root. The runner initializes an isolated project from the
included minimal Stage/ArkTS seed, compiles it, changes its page twice and
recompiles each version. It checks the actual unsigned HAP ZIP, module,
bytecode marker, size and SHA-256 against the compiler receipt. Each edit must
change the compiled artifact. It then introduces invalid ArkTS, requires a
compiler failure despite the previous HAP, repairs the source and builds again.

The commands run in the installed release image with the original published
Harmony SDK and build-kit mounted read-only. Compilation has no network and
requires no model, signing credentials or device. The SDK is not republished.
Full build logs, commands, compiler receipts, iteration sources and successful
HAP files are preserved in `evidence/`, including on failure. GitHub Actions runs
this same command in its candidate-copy installation job and uploads evidence.

This proves native unsigned HAP compilation of a project without external OHPM
dependencies. It does not prove device installation, atomic-service deployment,
formal Harness Session execution, SessionFS checkpoint/Fork parity or fixed-channel
promotion. Those scopes have their own tests.

## Generated requirements and oracle design

Three initial families (`hello`, `counter`, `form`) derive from a deterministic
Stage project. Each records the initial source SHA and two explicit demand deltas.
`scenarios.py` provides reference renders only for qualifying the case generator;
real participants receive requirements and edit their own Workspace. Source
contracts tolerate whitespace; actual HAP compilation/hashes and failure/recovery
checks supplement them. Injected syntax failure preserves the Participant's last
successful source. Repair must retain all stage-two features.

Next families should add one capability at a time: component extraction/navigation,
local persistence/restart, mock HTTP loading/error/retry, resources/localization,
and Native/atomic-service lifecycle. Generate bounded combinations of family,
parameters and fault type rather than unrestricted random projects. Every family
needs a reference implementation that passes independent tests before Agent
results are interpreted. Device interaction/lifecycle oracles are a separate
acceptance tier; source-pattern checks alone cannot prove click behavior.

SWE seeds retain official provenance. Generated Harmony seeds retain AgentLab
provenance and never claim to be official benchmark problems. Formal seed/Fork
qualification must bind TableGit seed/demand identities and SessionFS Workspace
cuts before claiming complete replay or causal failure attribution.

## Fixed-source original controller probe

The `harmony-controllers.yml` Action uses the independently updated build-kit v6
composition. Rust materializes patches against the pinned code-workshop source.
The runner calls SDK OHPM `install --all --lockfile_stable_order` with network
available, then probes the declared phone module with Docker network disabled.
It retains package-manager logs/manifests/locks, full-source compiler failures,
and separate typed-slice/invalid-type/recovery verdicts. A green slice job does
not qualify the full original project: inspect `fullSourceBuildQualified`.

Compiler evidence is maintained in the development TableGit with
`examples/knowledge-seed/flywheel/ingest-controller-build.py`, then exported in
three stable per-table snapshots. Dependency manifests remain lossless evidence;
vendor caches and intermediate build binaries are excluded from this export.
