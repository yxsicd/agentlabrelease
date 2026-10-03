# Real Harmony dialog control calibration

## Scope and identities

This is operator-owned runtime calibration, not an assessed Agent result or an
automatically admitted benchmark. The original repository is
`HarmonyOS_Samples/sample_in_harmonyos` at
`7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6`.
The isolated six-file host/test integration is the local derived commit
`1e3fc380198f3c2f51f183ad6f6cee4bf318fefe`; it was not pushed upstream.
The two production behavior bodies were unchanged in the accepted reference.

The reference source-set SHA256 is
`56e6868b7bdc9dcc7ee60e9b510468175468237a1777307c4fab1d10243b28ce`.
The executor was pinned to AgentLab method commit
`e1ad41ba6914cc6a1f8e8b3ef1f595df2b565652`, using the real host and
component-library ohosTest build targets, HDC installation and Hypium native
reports on a Linux-hosted emulator. SDK `6.1.1.300`, target build API and observed
guest image are separate environment axes, not an exact runtime qualification.

## Frozen checks and observations

| Run | Source/control | Pass | Failure | Error | Qualification |
| --- | --- | ---: | ---: | ---: | --- |
| 6 | Original behavior with operator host/tests | 4 | 0 | 0 | Scoped positive control |
| 7 | Reverse only the dialog style equality branch | 2 | 2 | 0 | Intended style failure observed |
| 8 | Replace descriptor menu entries with a fixed menu | 2 | 2 | 0 | Intended descriptor failure observed; later failure not independently attributed |
| 9 | Semantically restored behavior, with added EOF newlines | — | — | — | Interrupted native report; emulator launcher reached its deadline |
| 10 | Byte-restored reference on a fresh emulator launch | 4 | 0 | 0 | Scoped recovery positive control |

Run 7 fails `descriptor_style_selects_real_dialog_content` and
`progress_back_and_outside_dismiss_independently` at `assertProgress`.
The sheet and missing-context checks pass. Wrong source-set digest:
`fc6bc2076e2c4605c2b6cdd9f0e77b80651b451732a0d290551e380c65372289`.

Run 8 fails `descriptor_sheet_entries_and_autocancel` at `assertSheet`.
`missing_context_is_noop_and_restores` also fails afterward; retained UI state is
a possible cascade, not independently proven missing-context discrimination.
The two dialog checks pass. Wrong source-set digest:
`52bf192edcc7891dd78490db90f924ae6ae244a3a493e6366c67640a23957f57`.
Patch application also added EOF newlines; these are preserved formatting
differences, not additional semantic mutations. Both wrong controls complete
with HDC exit zero but native final code `-1`; transport exit alone is inadequate.

Run 9 has neither native final counts nor a final code. The emulator launcher
operation independently reached its 900-second deadline. This is interrupted
infrastructure evidence, not a killed wrong control or a reference pass.
The two EOF differences were subsequently mechanically removed, and
`git diff --exit-code` confirmed the reference source was byte-restored.
Run 10 completes successfully with the exact run-6 source-set digest, native final
code zero and all four checks passing. A fresh cold boot was required after the
launcher deadline; this is recovery evidence, not proof of uninterrupted longevity.

## Retained evidence

Original producer receipts, native reports and command logs remain in the
controlled experiment archive. File readbacks bind the exact HW Linux peer;
local envelopes preserve original UTF-8 contents and their byte lengths.
Receipt-to-execution-to-report/log SHA256 bindings and independent native
report reparsing agree for runs 6, 7, 8 and 10. Readback consistency does not
authenticate historical producers or establish a full environment lock.

The accepted run's HAPs were retained independently before wrong controls:

- App: `54587d6de98f986b7f18b5935e055af77cd58858b350e0886757eaa945aabc23`
- Test: `f923bdd2ef64b780a5117b596065b3182aed56bc234efe160cd14277db956dab`

Transient operation handles are retained for correlation, not used as the durable
archive: reference freeze `028c`, style `028d`, menu `028e`, interrupted recovery
`028f`, each with the `exec-000000000000` prefix.
Successful recovery is `0294`; the owned emulator was stopped after calibration.

## General method corrections

1. Cross-module host construction must bind both exports and the importing
   module's direct dependencies. Transitive access was insufficient here.
2. Build actual target-language tests before calibration. Host-seam JavaScript
   success does not qualify ArkTS helper syntax.
3. Preserve intended failure sites and potential stateful cascades separately.
   Cleanup after a passing reference does not prove cleanup after failed checks.
4. The installation receipt now reports `packagesInstalled=false` when target
   preflight or either installation fails. The older run-5 receipt remains
   preserved with its contradiction; it is not retroactively rewritten.

## Remaining gates

The host/test fixture is operator-authored. This does not admit a complete case,
qualify all declared negative controls, prove automatic host/test discovery,
freeze an operational benchmark, assess an Agent or update active TableGit
knowledge. UI failure cleanup needs a successor cut and fresh controls. Tip
buttons, transition behavior, performance/power, cohort repeatability and exact
runtime requirements remain outside these four checks.

Overall flywheel maturity remains an engineering estimate of **69%**; accepted
complete automatic business loops remain **0**. Next steps are reliable cleanup,
formal consumption of the bound calibration, automatic participant integration,
multi-round feedback benefit and cross-repository transfer under the same gates.
