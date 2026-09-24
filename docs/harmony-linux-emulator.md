# HarmonyOS Linux emulator integration

AgentLab can use the Huawei HarmonyOS emulator on a Linux x86-64 host with KVM.
The emulator and system-image bytes remain vendor-owned dependencies; this
internal-use release is authorized to publish the two exact verified archives
described below.

The verified local bundle consists of:

- command-line tools 26.0.0.821 repacked as
  `commandline-tools-linux-x64-26.0.0.821.tar.zst`;
- HarmonyOS 7.0.0 phone x86 image repacked as
  `HarmonyOS-7.0.0-phone_all_x86.tar.zst`.

Exact byte counts, SHA-256 values and validation results are in
`release/alharmony/harmony-emulator-linux-x64-26.0.0.821.json`.

## Distribution boundary

Huawei authorization for this internal-use GitHub release was confirmed by the
operator on 2026-09-24. Publication remains exact-asset scoped: only the two
filenames, byte counts and SHA-256 identities recorded in the manifest are
authorized by this release record. AgentLab still does not automate agreement
acceptance or infer authorization for other SDK/image versions.

## Installation

The installer accepts only the two byte-identical, already verified `.tar.zst`
files described by the manifest:

```sh
scripts/agentlab-harmony-emulator.sh preflight
scripts/agentlab-harmony-emulator.sh verify-assets \
  /path/to/commandline-tools-linux-x64-26.0.0.821.tar.zst \
  /path/to/HarmonyOS-7.0.0-phone_all_x86.tar.zst
scripts/agentlab-harmony-emulator.sh install \
  --tools /path/to/commandline-tools-linux-x64-26.0.0.821.tar.zst \
  --image /path/to/HarmonyOS-7.0.0-phone_all_x86.tar.zst \
  --root "$HOME/.local/share/agentlab/harmony-emulator-26.0.0.821" \
  --acknowledge-vendor-agreements
```

Installation is fail-closed: architecture, KVM, byte count, SHA-256, zstd long
window integrity and expected payload paths are checked before the staging
directory is atomically promoted. An existing install root is never overwritten.
After adding an operator to the `kvm` or `render` group, start a fresh login
session before running the preflight; an already-open service session does not
inherit newly granted supplementary groups.

## One-command functional case

Prepare an emulator instance with the vendor CLI, then run a bounded case. The
runner starts the named instance, waits for its exact HDC target, installs the
HAP, queries the bundle, launches the Ability, requires a live process, captures
a screenshot and SmartPerf proxy samples, writes
`agentlab.harmony_emulator_case_result.v1`, and stops the instance unless
`--keep-running` is explicit. Supplying a bounded UI scenario upgrades the
result to `agentlab.harmony_emulator_case_result.v2` and records task/source
identity, scenario identity, actions and Oracle checks.

Example:

    scripts/agentlab-harmony-emulator.sh run-case \
      --root "$HOME/.local/share/agentlab/harmony-emulator-26.0.0.821" \
      --image-root "$HOME/.local/share/agentlab/harmony-emulator-26.0.0.821/images" \
      --instance-path "$HOME/.local/share/agentlab/harmony-emulator-instances" \
      --instance agentlab-case-01 \
      --hdc-port 10100 \
      --hap /workspace/app/entry-default-unsigned.hap \
      --bundle com.example.app \
      --ability EntryAbility \
      --output /workspace/evidence/case-01

For deterministic UI cases, add `--ui-scenario`, `--task-id`,
`--source-id` and `--reset-app-data`:

    scripts/agentlab-harmony-emulator.sh run-case \
      ... \
      --output /workspace/evidence/case-01 \
      --ui-scenario examples/harmony-emulator/tutu-cookie-dismiss.ui \
      --task-id harmony-tutu-cookie-dismiss \
      --source-id artifact-sha256:<hap-sha256> \
      --reset-app-data

The tab-separated scenario schema is `agentlab.harmony_ui_scenario.v1`. Its
bounded operations are `wait-text`, `tap`, `swipe`, `key`, `sleep`,
`assert-text` and `assert-no-text`. Text checks are evaluated from pulled
`uitest dumpLayout` artifacts; every action and check is persisted in
`ui-actions.tsv` and `ui-checks.tsv`. `--reset-app-data` uninstalls the
bundle before installation so state from a prior case cannot silently satisfy
the Oracle.

The output directory is immutable-by-convention: the runner refuses to
overwrite it. `result.json` references the raw install, bundle, launch, process,
screenshot and SmartPerf artifacts and binds the HAP and screenshot SHA-256.
SmartPerf data is a relative emulator regression signal only; the result
explicitly records that absolute power and thermal authority are unavailable.

## Evaluation-instance export

Build the normalizer and convert an immutable case directory:

    cargo build --locked -p agentlab_code_analysis --bin agentlab-asset-model
    target/debug/agentlab-asset-model \
      examples/knowledge-seed/seeds/harmony-code-workshop \
      /workspace/evidence/export \
      file:///workspace/evidence/case-01 \
      case-01=/workspace/evidence/case-01

The export is an `agentlab.asset_exchange.v1` evaluation instance with `runs`,
`device_assessments`, `checks` and `evidence_files` tables. Device-runner
checks and UI Oracle checks retain distinct authority labels. The exporter
hashes every raw evidence file; it does not replace or mutate the device
evidence directory. Import into a live TableGit deployment remains a separate
operator-owned step.

## Qualified scope

On `hwlinux`, the Linux x86-64 emulator 26.0.0.400 booted the HarmonyOS
7.0.0(26.0.0) x86 phone image to the lock screen, accepted emulator control and
produced a screenshot. Two concurrent instances are the recommended configuration
on the tested i7-8700/32 GiB host; three are a throughput mode; four exhausted
swap and are not a steady-state recommendation.

This establishes Linux emulator availability for the toolchain. It does not
establish ARM-native application compatibility. The current image declares
`abi: x86`; an application containing only ARM native libraries remains outside
the supported scope unless an independently qualified translation layer exists.
The bounded `run-case` install/deploy/launch/process/screenshot/profile path,
the declarative UI action/layout-text Oracle path, and evaluation-instance
export have been qualified on `hwlinux`. Application-specific semantic Oracle
calibration, live TableGit import/replay, host graphics coverage and real-device
power/thermal calibration remain separate gates.
