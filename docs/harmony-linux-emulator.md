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
      --source-set-sha256 <multi-repository-source-set-sha256> \
      --reset-app-data

The tab-separated scenario schema is `agentlab.harmony_ui_scenario.v1`. Its
bounded operations are `wait-text`, `tap`, `swipe`, `key`, `sleep`,
`assert-text` and `assert-no-text`. Text checks are evaluated from pulled
`uitest dumpLayout` artifacts; every action and check is persisted in
`ui-actions.tsv` and `ui-checks.tsv`. `--reset-app-data` uninstalls the
bundle before installation so state from a prior case cannot silently satisfy
the Oracle.

Every HDC subprocess is itself bounded with GNU `timeout`. Connection and UI
readiness use wall-clock deadlines, and successful installation is accepted
only when HDC emits `install bundle successfully`. This prevents an HDC call
that returns zero with a textual `[Fail]` result, or a hung `dumpLayout`,
from being promoted as device or Oracle evidence.

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
Multi-repository runs additionally carry `sourceSetSha256` as a separate field;
the artifact identity is never overloaded to mean the source-set identity.

The output directory is immutable-by-convention: the runner refuses to
overwrite it. `result.json` references the raw install, bundle, launch, process,
screenshot and SmartPerf artifacts and binds the HAP and screenshot SHA-256.
SmartPerf data is a relative emulator regression signal only; the result
explicitly records that absolute power and thermal authority are unavailable.

## Harmony standard-test boundary

The tab-separated `uitest` scenario above is an operator-owned black-box Oracle,
not a substitute for Harmony's standard application-test structure. A Harmony
case should additionally expose at least one official lane:

- Instrument Test under `src/ohosTest`, using `@ohos/hypium`, an
  `ohosTest` build target and either a source-provided `OpenHarmonyTestRunner`
  or the source-migrated `module.json5` form for which Hvigor's
  `GenerateOhosTestTemplate` task creates that runner;
- Local Test under `src/test` for device-independent ArkTS logic; or
- DevEco Testing Hypium UI automation with packaged Python testcases and
  retained reports.

Use `scripts/harmony-standard-test-contract.py inspect` to inventory those
assets. The contract deliberately separates a source-qualified standard lane
from a passing execution receipt bound to the same case, source set and project
tree. Only the latter closes the standard-test execution gate. A custom `.ui`
Oracle is recorded as `supplemental-only`; it can add exact product behavior but
cannot by itself claim Harmony standard-test compliance. This follows Huawei's
[developer testing service](https://developer.huawei.com/consumer/cn/testing/get-started/),
which distinguishes Instrument Test, Local Test and Hypium UI automation, and
keeps compatibility, stability, performance, power, security and UX as
separate quality dimensions.

For the normal source-to-device path, use the combined executor so the two
HAPs cannot be substituted between build and execution:

```sh
python3 scripts/run-harmony-source-standard-test.py \
  --project-root /absolute/path/to/materialized-project \
  --case-id case-42 \
  --source-set-sha256 <frozen-source-set-sha256> \
  --hvigorw /absolute/path/to/hvigorw \
  --build-module entry \
  --product default \
  --build-mode debug \
  --app-hap entry/build/default/outputs/default/entry-default-unsigned.hap \
  --test-hap entry/build/default/outputs/ohosTest/entry-ohosTest-unsigned.hap \
  --hdc /absolute/path/to/hdc \
  --target <exact-hdc-target> \
  --bundle com.example.app \
  --test-module entry_test \
  --output-dir /absolute/new/evidence-directory
```

It runs the fixed argument-vector Hvigor target
`module=<module>@ohosTest ... assembleHap --no-daemon`, retains the build
command and output, binds both generated packages, verifies that every
pre-existing source/configuration file stayed byte-identical, and then invokes
the device executor below. Generated dependency and build directories
(`build`, `.test`, `.hvigor`, `node_modules`, `oh_modules` and `.git`) are
excluded from the source-tree identity so repeated builds of the same source
remain the same case. A build failure or source mutation stops before device
installation and is retained in `build-receipt.json`; `receipt.json` binds the
build receipt to the nested native execution receipt.

For an `ohosTest` Instrument Test, run the app HAP and its test HAP against an
already booted emulator target with the bounded executor:

```sh
python3 scripts/run-harmony-instrument-test.py \
  --project-root /absolute/path/to/materialized-project \
  --case-id case-42 \
  --source-set-sha256 <frozen-source-set-sha256> \
  --hdc /absolute/path/to/hdc \
  --target <exact-hdc-target> \
  --app-hap /absolute/path/to/app.hap \
  --test-hap /absolute/path/to/app-ohosTest.hap \
  --bundle com.example.app \
  --module entry_test \
  --runner OpenHarmonyTestRunner \
  --output-dir /absolute/new/evidence-directory
```

The executor verifies that the target is present, installs both exact HAPs,
uses an argument-vector `hdc shell aa test` invocation, and retains all command
logs. It accepts a pass only when ArkXtest emits a non-empty, internally
consistent `OHOS_REPORT_RESULT` with zero failures/errors and a final
`OHOS_REPORT_CODE: 0` (or ArkXtest's worker aggregate `OHOS_REPORT_ALL_*`
equivalents); process exit zero alone is insufficient. `receipt.json`
binds the case, source set, project tree, HDC binary, both HAPs, command, native
report and logs. Re-run `harmony-standard-test-contract.py inspect` with
`--execution-receipt .../receipt.json` to close the gate; the validator reads
and hashes the retained native report instead of trusting receipt claims.

This executor currently closes the Instrument Test lane only. Local Test and
DevEco Testing Hypium UI remain recognized source contracts but need their own
native execution adapters before they may produce passing receipts. The
ArkXtest command and result markers follow the official
[ArkXtest guide](https://gitee.com/openharmony/docs/blob/master/en/application-dev/application-test/arkxtest-guidelines.md)
and the upstream
[ArkXtest implementation](https://github.com/openharmony/testfwk_arkxtest/blob/master/jsunit/src/module/report/OhReport.js).

### hwlinux real ohosTest canary

The first real standard-test closure is retained on `hwlinux` at
`/home/huawei/.agentlab/evidence/harmony-standard-real-20260925`. The source is
the preserved `hmos-code-workshop` cut at revision
`7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6`; its revision-derived source-set
identity is `acf288df…e002` and its source-only project-tree SHA256 is
`b0c7a6f3…3349`. Harmony SDK 6.1.1.125 / Hvigor 6.24.4 built the phone
`ohosTest` target in 23.122 seconds. The build log executed
`GenerateOhosTestTemplate` and generated `OpenHarmonyTestRunner.ets`, proving
the source-migrated layout is a real standard path rather than a missing-runner
error.

The Linux x86 emulator accepted both exact unsigned debug artifacts: the
393,655,699-byte app HAP (`a55f0f06…9285`) and 393,653,849-byte test HAP
(`c513d81c…1b45`). `hdc shell aa test` then ran `phone_test` through
`OpenHarmonyTestRunner`: one test ran and passed, with zero failures, zero
errors, process exit zero and `OHOS_REPORT_CODE: 0`. The bound native report is
SHA256 `8fc99273…4908`; reinspection of the receipt returned
`qualified-standard-test-executed`. This qualifies this exact emulator,
project, package pair and test run. It does not imply that unsigned packages
are installable on production devices, nor does one passing test establish
suite breadth or application-wide quality.

The combined source executor was then exercised against the same retained
project and emulator as a separate evidence cut at
`/home/huawei/.agentlab/evidence/harmony-source-standard-real-20260925`.
One invocation bound the pre-build source contract, ran
`phone@ohosTest`, verified every pre-existing source/configuration byte,
installed both generated HAPs and executed the native test module. The warmed
Hvigor rebuild took 2.701 seconds; the app and test package digests remained
`a55f0f06…9285` and `c513d81c…1b45`, while the source-only project identity
remained `b0c7a6f3…3349`. The nested native report again recorded one pass,
zero failures/errors and final code zero. The top-level source-to-test receipt
is SHA256 `87e16027…61d9`. This closes the operational gap between the prior
source build and prebuilt-package executor for this exact canary; campaign-wide
`run-harmony-assessed-standard-test.py` now binds that source receipt to the
exact assessed workspace and build receipt. The assessed campaign executes it
between build and UI/performance for every statically passing attempt. Native
assertion failures become `failureClass=standard-test`; infrastructure failures
remain retryable and cannot be counted against the Agent. The campaign owns a
separate cold emulator lifecycle for this gate, records its start/stop identity,
and requires it to stop cleanly before the UI/performance runner starts its own
measurement lifecycle; the gate therefore does not depend on a manually
pre-started HDC target or contaminate the subsequent cold-run timing window.
Hosts whose cold boot exceeds the default 180 seconds may set
`runtime.bootTimeoutSeconds` (maximum 900). A boot that still misses its HDC
deadline is an infrastructure failure: the gate invokes the exact instance's
official stop command, waits for the launcher process to exit, and retains the
failure-stop log instead of leaking an emulator into a later retry.

The integrated hwlinux canary at
`/home/huawei/.agentlab/evidence/harmony-assessed-ohostest-aa799f9/campaign-output`
then exercised this complete ordering against method revision
`d788ac47b9989f7f57d8250acc087b55beb6e2d0`. Both strong and weak assessed
workspaces built their application and `ohosTest` HAPs and passed the native
Hypium runner. The strong variant passed the independent UI Oracle and retained
three SmartPerf samples (mean application CPU 2.542 reported percent and mean
PSS 33,011 KiB); the weak variant passed the same static and native standard
tests but failed the device-visible text Oracle as intended. The campaign
summary SHA256 is `53c68106…4f07`, its discrimination report SHA256 is
`1cf515fd…f1be`, and the resulting score is 1.0 with both attempts covered.
The run ended with no HDC target or emulator process. Absolute power and
thermal authority remains unavailable on this emulator. The compact immutable
qualification record is checked in at
`release/qualifications/harmony-assessed-ohostest-hwlinux-aa799f9/summary.json`;
it explicitly classifies the two inputs as controlled fixture variants rather
than external Agent submissions and retains the one-trial and emulator-only
limits.

That run also exposed an important host preflight requirement. A long-lived
service may not inherit group membership added after it started. The emulator
process must have all of `kvm`, `render`, and `video`, with read/write access to
`/dev/kvm`, `/dev/vhost-net`, `/dev/dri/card1`, and `/dev/dri/renderD128`.
KVM-only execution produced EGL permission errors and never exposed HDC;
refreshing all three groups removed the errors and reduced standard-test cold
startup to the ordinary tens-of-seconds range. These devices and groups belong
in `executionPreflight`, not in an undocumented operator workaround.

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

### hwlinux assessed-campaign canary

The first real assessed-Agent campaign for this lane is retained on `hwlinux`
at `/home/huawei/.agentlab/evidence/harmony-assessed-campaign-c34095d`. It ran
from method revision `b6de366b61674c1b58a686e4ffa5187c4d011414` against two
exact local Git source revisions and the source-set SHA256
`a18237a4e8f541b423cd9283743ca1da5f18efbf54250403a782bfd114976b14`.
Both participants passed the independent static Oracle. The weak participant
then changed only the device-visible text from `Multi Repo Ready` to
`Multi Repo Missing`, a behavior intentionally outside that static Oracle.

The campaign completed two sequential cold-boot builds and device assessments
in 188.817 seconds. The strong attempt passed the device Oracle and retained a
normalized three-sample SmartPerf profile: mean application CPU was 2.3655%
and mean application PSS was 33,296 KiB. The weak attempt reached the same
emulator infrastructure but failed the bounded UI Oracle, so its result is an
assessed Agent failure (`failureClass=oracle`) rather than an infrastructure
failure; performance sampling correctly remained `not-run` behind the failed
functional gate. The resulting discrimination score is 1.0 with no excluded
attempts. One review-only `harmony-device` feedback candidate was derived and
automatic promotion remained false.

Current scoring also preserves policy-selected SmartPerf observations through
the compound device stage. When a participant has at least two successful
attempts under the same environment, performance policy and workload, the
report computes the cross-attempt min/max/mean, sample standard deviation and
coefficient of variation and marks that profile's performance feedback
repeatable. A single passing run, including this historical canary, remains an
observation rather than repeatability evidence. Functional Oracle authority is
unchanged; emulator measurements remain relative CPU/PSS feedback and do not
claim absolute power or thermal qualification.

The campaign summary SHA256 is
`13e3fe304d29a7434a8d0af87e316ac45579e46f40975561f8643f2745cdcb8b`;
the discrimination-report SHA256 is
`40efda306ac46448742449b353662961d8b7b8fc8ef03ccc3a7fc9aca4d81fc1`.

Completed campaigns now have a fail-closed route back into trusted-main suite
composition. `scripts/import-harmony-device-campaign.py prepare` packages the
complete device campaign, resolved plan and host profile while binding the
original static workflow run and handoff. The trusted
`harmony-device-campaign-import.yml` workflow independently recovers that
static artifact, verifies the complete ZIP member index, reconstructs scoring
from raw attempt evidence and separately attests the reconstructed report and
import receipt. It does not attest that arbitrary uploaded JSON is true, and it
does not turn an emulator into power or thermal authority. The mechanism has
deterministic tamper and lineage-drift coverage; the retained historical canary
has not yet been repackaged and processed by a merged trusted-main import run.
The run also exposed and fixed a Linux portability defect: assessed Git blobs
previously inherited the host `umask` and could become mode `0664`, while the
downstream builder accepts only Git-representable `0644` and `0755`. Revision
`b6de366` now materializes and verifies the exact mode from each Git tree entry.
The preserved pre-fix and instance-path configuration failures remain beside
the successful campaign and are not counted as participant attempts.

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
is retained under
`release/qualifications/harmony-performance-automated-calibration-v1` as
`calibration-run.json`, SHA256
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

### Review-transaction preparation

After a calibration succeeds, use
`scripts/prepare-harmony-performance-review.py` to prepare the revision-fenced
TableGit transaction without publishing it. Its plan binds the immutable
calibration directory, the exact transaction-builder SHA, the current expected
TableGit revision, the selected caller Person, repository and run identity:

```json
{
  "schema": "agentlab.harmony_performance_review_plan.v1",
  "evidence": "/absolute/path/calibration-evidence",
  "transactionBuilder": "/absolute/path/build-cbgroom-flywheel-transaction.py",
  "transactionBuilderSha256": "<64 lowercase hex>",
  "expectedRevision": "<40 lowercase hex>",
  "runId": "controlled-performance-review-v1",
  "githubRepository": "owner/repository",
  "callerPersonId": "<selected-person-id>",
  "repo": "agentlabtablegit",
  "automaticPublication": false,
  "automaticPromotion": false
}
```

Run it with a new output path:

```sh
python3 scripts/prepare-harmony-performance-review.py \
  --plan /absolute/path/review-plan.json \
  --output /absolute/path/prepared-review
```

The operation hashes every evidence file, invokes the exact bound builder,
revalidates transaction authority, requires exactly one performance decision and
one non-ready performance difficulty, and rejects any automatic-promotion bit.
Success atomically emits `transaction.json`, builder logs and
`preparation.json` with status `prepared-not-published`. It never contacts or
mutates TableGit. Publication remains a separate operator-owned action against
the still-current expected revision; a prepared transaction is not publication
evidence.

### Frozen multi-repository case execution

First produce a HAP and independent build receipt from exact Git objects using
`scripts/build-harmony-evaluation-artifact.py`. Its
`agentlab.harmony_case_build_plan.v1` input binds the frozen case, one or more
source-directory mappings for every repository, and a build contract containing
the executable SHA256, argument vector, working directory, relative HAP path,
bounded timeout and explicit non-secret environment:

```sh
python3 scripts/build-harmony-evaluation-artifact.py \
  --plan /absolute/path/harmony-case-build-plan.json \
  --output /absolute/path/new-harmony-build
```

The producer resolves every mapping from the case's exact Git revision and
`origin`; it reads committed blobs rather than working-tree files. It invokes
the builder without a shell in its own process group and terminates that group
on timeout. Success emits `artifact.hap`, `source-materialization.json`, build
logs and an `agentlab.harmony_case_build_receipt.v1` with
`buildAuthority=independent-harmony-build` and `automaticPromotion=false`.
Failure keeps the hidden staging workspace and logs. Plans must not contain
credentials; secret-bearing signing and AGC flows remain outside this unsigned
emulator-build lane.

Use `scripts/run-harmony-evaluation-case.py` when a reviewed, calibrated
multi-repository case has been independently materialized and built as a
Harmony HAP. Its `agentlab.harmony_evaluation_run_plan.v1` plan binds:

- the frozen case path and SHA256;
- an `agentlab.harmony_case_build_receipt.v1` path and SHA256;
- the exact HAP path and SHA256;
- the UI Oracle path, identity and SHA256;
- the executable emulator runner and SHA256;
- exact runtime directories, emulator instance, port, bundle, ability and
  environment identity;
- exact performance policy and profile workload digests; and
- `automaticPromotion=false`.

The independent build receipt must have `status=passed`,
`buildAuthority=independent-harmony-build` (or the separately validated
`independent-harmony-assessed-workspace-build` authority), and bind the case ID/digest,
source-set digest, complete pinned source list, HAP digest, build-tool digest
and source-materialization digest. It is evidence supplied by the build owner;
the emulator bridge does not synthesize it.

The assessed-workspace authority is produced only by
`scripts/build-harmony-assessed-workspace.py`. In addition to the common receipt
contract it binds the exact successful Harness decision, participant identity,
final source-state and subject-workspace digest. Those identities are copied to
`evaluation-binding.json`, so a device result cannot be silently attributed to
the frozen baseline or to another Agent attempt.

For an assessed Agent workspace, set
`subjectOutcomePolicy=retain-assessed-failure`. A runner exit caused by a
well-formed UI Oracle failure is then retained as
`assessed-failure-review-required`, with a boolean false subject verdict and the
failed UI-check evidence. Infrastructure-unavailable output, malformed failure
evidence or identity drift still fails the bridge. The default policy remains
`require-pass` for qualification and reference runs.

For multi-attempt assessed campaigns, use
`scripts/run-harmony-assessed-campaign.py`. It skips the device gate for
already-failed static attempts, runs only statically passing Agent workspaces
through the resumable HAP/emulator path, composes static and device verdicts,
and invokes the ordinary discrimination and feedback tools. This controller is
sequential for one declared emulator instance; multi-instance scheduling is a
separate resource-allocation layer and must preserve one exact runtime and HDC
binding per attempt.

The trusted static workflow emits a portable
`agentlab.harmony_assessed_campaign_handoff.v2` beside its retained evidence.
Use `scripts/resolve-harmony-assessed-handoff.py` on hwlinux with an
`agentlab.harmony_assessed_host_profile.v1` and an explicit `--host-root` to
create the absolute campaign plan. The portable side binds every static file
and the complete workspace tree. It also binds the pre-outcome participant
experiment plan and rejects missing tiers, missing repeats, model/profile
substitution, execution-protocol drift, or an unqualified native participant
identity before emulator capacity is spent. The host side binds build, runner,
Oracle, SmartPerf policy/workload and controller programs. Keeping these
authorities separate lets the same immutable static artifact be replayed after
relocation without recording one machine's paths in GitHub evidence. Legacy v1
handoffs remain readable as historical evidence but do not gain this
predeclared-experiment qualification.

KVM profiles must also bind an execution preflight, for example:

```json
{
  "executionPreflight": {
    "requiredGroups": ["kvm"],
    "requiredDevices": [{"path": "/dev/kvm", "read": true, "write": true}]
  }
}
```

The group must be active in the exact process launching the campaign. A user
listed in the `kvm` group can still lack access when a long-running AgentWeb or
systemd process predates that membership. The controller rejects this condition
before creating campaign output or spending build/emulator capacity.

```sh
python3 scripts/run-harmony-evaluation-case.py \
  --plan /absolute/path/harmony-evaluation-run-plan.json \
  --output /absolute/path/new-evaluation-evidence
```

Completed assessment atomically retains the raw emulator execution, runner logs
and `evaluation-binding.json` with either `passed-review-required` or
`assessed-failure-review-required`. The bridge
rechecks every input after execution, then verifies functional result,
source-set identity, HAP, Oracle, run/environment identity, normalized
SmartPerf sample contract, policy/workload identity and the emulator-only
power/thermal authority boundary. A failed runner or any identity drift keeps
the hidden staging directory and `failure.json`; it never creates the requested
final output. Even a successful binding remains review-required and cannot
promote an evaluation case automatically.

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
