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
Supplying an exact performance policy and profile workload upgrades it again to
`agentlab.harmony_emulator_case_result.v3`; the runner hashes and retains both
inputs and executes the workload concurrently with the SmartPerf window.

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

Version 2 results also expose `assessmentStatus`, `infrastructureAvailable`,
`subjectTaskSucceeded` and `failureClass`. A failed bounded UI assertion is an
assessed task failure. Boot, HDC, layout-transfer and input-control failures are
infrastructure failures and carry a null task verdict. This distinction is
preserved when `collect-case-attempts.py` ingests emulator attempts for
cross-participant discrimination scoring. For every v2 run, `--source-id` must
be exactly `artifact-sha256:<actual HAP SHA-256>`; the runner, attempt collector
and evaluation-instance exporter all reject a source/HAP mismatch. Assessed
results must also retain at least one valid `ui-checks.tsv` row, and its aggregate
must equal both `oracleStatus` and `subjectTaskSucceeded`.

The output directory is immutable-by-convention: the runner refuses to
overwrite it. `result.json` references the raw install, bundle, launch, process,
screenshot and SmartPerf artifacts and binds the HAP and screenshot SHA-256.
SmartPerf data is a relative emulator regression signal only; the result
explicitly records that absolute power and thermal authority are unavailable.

## Relative performance feedback

Add stable run and environment identities to normalize SmartPerf automatically:

```sh
scripts/agentlab-harmony-emulator.sh run-case \
  ... \
  --ui-scenario examples/harmony-emulator/tutu-cookie-dismiss.ui \
  --task-id harmony-tutu-cookie-dismiss \
  --source-id artifact-sha256:<hap-sha256> \
  --profile-run-id candidate-001 \
  --environment-id hwlinux:emulator-26.0.0.821:phone-x86-class-a \
  --performance-policy examples/harmony-emulator/emulator-cpu-memory-relative.performance.json \
  --profile-workload examples/harmony-emulator/tutu-scroll.profile \
  --profile-samples 12
```

The runner retains `smartperf.txt` and creates `smartperf-summary.json`. The
normalizer follows the [official SP_daemon command format](https://gitee.com/openharmony/developtools_smartperf_host/blob/master/smartperf_device/device_command/README_zh.md),
including both marker-delimited samples and device streams whose
`order:n key=value` sequence starts a new sample whenever `order:0` recurs,
retains unknown numeric fields, converts `fpsJitters` nanoseconds to frame
interval milliseconds, and reports FPS, application CPU, PSS and GPU load as
canonical relative metrics. Current, voltage and thermal fields remain raw,
non-gating emulator evidence. An empty `fpsJitters` field is retained as an
unavailable frame metric; it is never converted into a fabricated zero. A zero
baseline for a ratio guardrail is likewise unusable evidence, not a regression.

Compare a candidate only with a baseline from the same task and exact
environment identity:

```sh
python3 scripts/compare-smartperf.py \
  --baseline baseline/smartperf-summary.json \
  --candidate candidate/smartperf-summary.json \
  --baseline-result baseline/result.json \
  --candidate-result candidate/result.json \
  --output candidate/smartperf-comparison.json
```

Legacy v1/v2 summaries use the original fixed FPS, CPU, PSS and frame-interval
guardrails. Policy-bound v2 summaries and v3 comparisons instead use only the
exact policy's `requiredMetrics`. The checked-in emulator policy requires mean
CPU (maximum 20% increase) and mean PSS (maximum 15% increase); FPS,
frame interval and GPU load remain observed-only because the current Linux
emulator/SP_daemon combination has not produced usable frame telemetry. This is
capability scoping, not a claim that missing frame, power or thermal data passed.
Missing policy-required metrics or an environment, policy or workload mismatch
is insufficient evidence, not a pass or failure. A detected regression is a
review candidate and never an automatic case rejection or release decision. The function-bound comparison
requires both exact Harmony results to describe assessed, infrastructure-valid,
UI-Oracle-passing runs for the same task and HAP identities as the performance
summaries. If either functional gate fails, the profiles are not comparable and
cannot become a performance-regression difficulty.

Before flywheel persistence,
retain the exact inputs as `smartperf-baseline-summary.json` and
`smartperf-candidate-summary.json`, plus the two results as
`harmony-baseline-result.json` and `harmony-candidate-result.json`, beside
`smartperf-comparison.json`. The transaction builder recomputes all canonical
digests and rejects any task, run, environment, HAP identity, functional verdict
or authority drift. For v3, also retain `performance-policy.json` and
`profile-workload.tsv`; the builder verifies their raw SHA-256 identities against
both summaries, results and the comparison. A functionally passing v2/v3 regression becomes a non-ready,
non-promoted `difficulty_point` for maintainer adjudication and repeated
calibration; a legacy v1 profile-only comparison remains a decision record only.

### hwlinux function-bound static-page canary

The first real v2 paired canary for this contract is retained on `hwlinux` at
`/home/huawei/agentlab-canary-3c97b38`. Two fresh cold boots ran the same
Tutu HAP (`df057e…e148`), UI scenario (`f5b7d6…0afb`), emulator instance and
environment identity. Both functional results were assessed and Oracle-passing,
and both normalized five markerless device samples. The final comparison is
`smartperf-comparison-v2.json`, 3,414 bytes, SHA256
`96d304d64f658d9358e9a75a1724b2cd31162121b8cde93dfba9a3ec035d7305`.

This is deliberately a fail-closed result, not a performance pass. The page was
static during the SmartPerf window, so both runs reported zero FPS and no frame
interval samples. The functional gate passed, CPU and PSS guardrails passed,
but the comparison returned `insufficient-comparable-evidence` with
`required-metric-missing` and `required-metric-unusable-baseline`. A future
performance qualification must execute a bounded repeatable dynamic workload
during the profiling window; it must not reinterpret a static zero-FPS sample
as either a pass or a regression.

A follow-up 12-sample probe executed ten alternating deterministic swipes during
the profiling window. Application CPU reacted (mean about 5.83%), proving that
the workload was active, but all twelve FPS values remained zero and every
`fpsJitters` field remained empty. Therefore the public v3 contract binds this
exact workload while gating only CPU/PSS. Frame metrics stay observed-only until
a separately evidenced environment or instrumentation path makes them usable.

The first full v3 paired canary is retained beside the earlier evidence as
`baseline-v3-r2`, `candidate-v3` and `smartperf-comparison-v3.json`. Both cold
boots passed the functional Oracle, retained 21 workload action rows and
normalized 12 samples under policy SHA256 `667c5704…77ef9` and workload SHA256
`86a52cb8…2e4c5`. Baseline/candidate mean CPU were 6.4297%/6.2624%; mean PSS
were 172674/172003 KiB. The comparison is genuinely comparable and reports
`within-relative-guardrails`; its 3,245-byte SHA256 is
`bb3ad5cd3e6a84405dee9119c97af8d74a6968181c941b600cc58ea3ed21c7e5`.
This qualifies the policy-bound CPU/PSS emulator lane only; it does not qualify
FPS, frame interval, GPU fidelity, absolute power or thermal measurement.
Case-discrimination collection accepts this evidence only as
`harmony-emulator-v3` and independently rechecks the retained policy, workload,
normalized summary and executed-action hashes before carrying the functional
verdict into scoring.

### Controlled-regression calibration

Use `scripts/run-harmony-performance-calibration.py` to reproduce a controlled
calibration as one fail-closed operation instead of manually joining five
commands. Its `agentlab.harmony_performance_calibration_plan.v1` input binds the
exact harness and application revisions, baseline and candidate HAPs, controlled
source mutation, UI Oracle, emulator environment, performance policy and
workload. The current protocol deliberately requires one baseline and two
candidate cold runs:

```sh
python3 scripts/run-harmony-performance-calibration.py \
  --plan /absolute/path/calibration-plan.json \
  --output /absolute/path/new-calibration-evidence
```

On `hwlinux`, invoke this command from a session that already has both KVM and
render-device access, for example under the same outer `sg kvm` / inner
`sg render` context used by the emulator runner. The output path must not exist.
The orchestrator derives both `artifact-sha256:` identities from the HAP bytes,
runs the functional Oracle and bound SmartPerf workload three times, validates
every task/source/run/environment/Oracle/policy/workload identity, compares both
candidates to the same baseline, and accepts the calibration only when both
comparisons expose at least one common regressed metric. A success is atomically
published at the requested output path with the raw runs, comparisons,
`performance-calibration.json` and `calibration-run.json`.

Between cold runs, the orchestrator also waits for the configured HDC port to
be released (120 seconds by default, bounded to at most 300). This prevents a
stopped instance that is still draining from being mistaken for the next fresh
instance; a release timeout is retained as its own failed phase.

The first real orchestrated replay ran on `hwlinux` from harness revision
`c40d90fd7da93d01eb6aab3212e81c23ef615e86`. It completed all seven recorded
phases in 270.566 seconds. Both one-second port-release phases required two
probes, all three UI Oracles passed, and both independent comparisons reported
`appPssKiB` regression. Baseline/candidate/repeat mean PSS were
173344/239498/239810 KiB; mean CPU was 5.8048%/6.1168%/5.3576%. The run receipt
is retained as `automated-calibration-run.json`, SHA256
`9cd7c9e0673a15b0f4d016e5621fb03710d57cde4cd1b59c93f5915eb55cc3bb`.
The full raw result remains on the execution host at
`performance-regression-calibration/automated-calibration-c40d90f-v3`.

If any phase or identity check fails, the final output is not created. The
adjacent hidden `.stage-*` directory is retained with phase logs, partial raw
evidence and `failure.json` for diagnosis. Neither success nor failure permits
automatic case promotion: the generated records always state
`automaticPromotion=false`, and maintainer adjudication plus independent
calibration remain mandatory.

The first positive calibration of the regression detector is checked in at
`release/qualifications/harmony-performance-controlled-regression-v1`. Baseline
and candidate were built from the same generated Tutu project rooted at exact
ASRelease revision `71fa3710a9e31af33ffb90d031270c11a1dbaab3`. The candidate
changed only `Template.ets`: it retains and touches 64 MiB while leaving the UI
and independent cookie-dismiss Oracle unchanged. The calibration manifest binds
both HAP identities, both source-file digests, that controlled mutation, the
Oracle, environment, policy, workload and raw comparison digest.

Both fresh cold-boot runs passed the same function gate and normalized 12
samples. Mean CPU changed from 6.5085% to 7.2289% (+11.07%, within the 20%
guardrail). Mean PSS changed from 170392 to 239204 KiB (+40.38%, beyond the 15%
guardrail). The exact comparison SHA256 is
`eb875ee462cfc3ce6cac1dcf73a35cbf1e509f8c14d3e3579c02819e056cee10`
and its decision is `performance-regression-candidate`.

The same candidate HAP was then rerun from another cold boot with the same
Oracle, environment, policy, workload and 12-sample contract. The function gate
passed again; mean PSS was 236526 KiB (+38.81% over the same baseline), so
`appPssKiB` independently regressed in both candidate runs. CPU was 5.1621% in
the repeat and remained within its guardrail. The retained repeat comparison is
`smartperf-repeat-comparison.json`, SHA256
`707432cefa5db06b5642bb52ace25f68c5e5edeb4c0e33e8025154da27188097`.

When `performance-calibration.json` is present, the flywheel transaction builder
fails closed on any drift in HAPs, application/harness revisions, source-file
mutation, functional Oracle, environment, policy, workload, comparison digest,
expected decision or measurement authority. A valid package adds the calibration
and any repeat run as evidence references and binds them into both the
review-only decision and the non-ready difficulty. Repeatability is marked
verified only when both exact comparisons independently identify at least one
common regressed metric. It still sets `automaticPromotion=false` and
`caseReady=false`; repeatability does not replace maintainer adjudication or an
independent functional/performance calibration and does not authorize TableGit
publication.

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
the declarative UI action/layout-text Oracle path, Tutu cookie-dismiss functional
calibration, controlled CPU/PSS regression detection, and evaluation-instance
export have been qualified on `hwlinux`; the controlled PSS signal has also been
reproduced across two cold-boot candidate runs on that host. General
application-specific semantic Oracle calibration, cross-host repeatability, live
TableGit import/replay, host graphics coverage and real-device power/thermal
calibration remain separate gates.
