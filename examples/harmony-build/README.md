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
