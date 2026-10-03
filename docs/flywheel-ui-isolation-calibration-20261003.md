# Failure-path UI isolation calibration

Overall flywheel maturity is an engineering estimate of **70%**, increased from
69% for a real, controlled failure-isolation improvement, not added test counts.
Accepted complete automatic business loops remain **0**. The operator still
authored cleanup, dispatched controls and reviewed the partial profile. This is
not an automatically generated/admitted case or cross-repository acceptance.

## Controlled sequence

The original source base remains `7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6`.
The operator host/test reference is `1e3fc380198f3c2f51f183ad6f6cee4bf318fefe`.
Two local-only derived test commits preserve it:

- `e254fecd13b4d0bb8e78eb75a67715878ed800d4`: explicitly select an existing
  sheet item rather than assuming Back dismisses a non-autoCancel sheet; verify
  overlay absence in afterEach. This attempt did **not** fix failure isolation.
- `8ee64b5775b4615f338429a7a87b9a7992ac5417`: register the same reset beforeEach
  as well as afterEach. All four behavioral test bodies remain byte-identical to
  the original reference; no production behavior was repaired in the reference.

The actual installed Hypium 1.0.19 `SuiteService.asyncRunSpecs` places the test
body and afterEach in the same try block. A thrown assertion skips the latter.
Its original service bytes are retained privately. This is inspected behavior
of that dependency cut, not a rule for all framework versions.

| Test cut/control | Pass | Assertion failures | Errors | Observation |
| --- | ---: | ---: | ---: | --- |
| afterEach-only reference | 4 | 0 | 0 | Positive control |
| afterEach-only fixed menu | 2 | 2 | 0 | Intended menu failure and later context failure |
| beforeEach+afterEach reference | 4 | 0 | 0 | New positive control |
| beforeEach+afterEach fixed menu | 3 | 1 | 0 | Only intended menu failure; context check passes |
| byte-restored beforeEach+afterEach recovery | 4 | 0 | 0 | New recovery positive control |

The mutation fixes only the production `sheets` option to `SHEET_ALPHA`; patch
application additionally added an EOF newline. That formatting difference is
retained, not represented as another semantic mutation. Recovery reverses the
mutation and mechanically restores the original EOF; `git diff --exit-code HEAD`
passes. The first test cut's expected result was not rewritten after its failure.

Reference/recovery source-set SHA256 is
`098068e1aa7f7e939d41df75e8f0599858d84d753deefcd71d77aeebd437656c`;
wrong-menu SHA256 is
`04f4b7b5608a75be2f4736747814414d1cd067b1afcb858b57ab89a1bb05ec16`.
Both positive runs use native final code 0; the negative uses -1 with HDC process
exit 0. Complete named native status records, not transport exit, distinguish
these results. All five builds/installations use the existing source-standard
executor at `e1ad41b`, SDK 6.1.1.300 and the owned Linux KVM emulator. The emulator
was stopped afterward; its original launcher completed with exit 0.

## Generic feedback and preserved boundary

Controlled artifacts live outside public source in
`flywheel-dialog-cleanup-4GtCkk8w` locally and
`/tmp/agentlab-dialog-cleanup-20261003-e254fec` on the exact HW Linux peer. They
retain original-content file-read envelopes, source versions, patches, command
handles, native logs/reports and build/execution receipts. No upstream subject
push, active TableGit mutation, assessed Agent run or Release occurred.

The generic Rust partial-calibration consumer reconstructed the new cut's two
accepted controls and one rejected control with exactly the intended failed check.
An unchanged repeat returned `awaiting-new-evidence`, schedulingAllowed=false.
The reviewed profile no longer lists the resolved cleanup action, but this is
explicit operator review, not automatic discovery of the repair. Its remaining
work includes uncovered behavior and four of five declared negative controls.
Old-cut controls were not inherited. All formal construction qualification
actions remain unchanged and qualified=false.

The first profile reconstruction accidentally used an unsorted candidate-value
digest and was rejected before output. Correcting it to the existing canonical
value digest did not alter the candidate or readiness. File-byte and canonical
value identities remain distinct. Retained readbacks and declared method/runtime
identity are not cryptographic producer or runtime attestations.

The reusable lesson is to inspect dependency failure-path hook ordering and
verify pre-test state for independent scenarios. Do not reset between phases of
one long-horizon scenario, which would erase the state being tested. Next work
must automate reviewed control construction/dispatch and source/patch admission,
extend uncalibrated observables, and connect formal qualification to the complete
execution/feedback loop rather than repeat these original captures.

## Executable method follow-up

The generic frozen-behavior consumer previously accepted a wrong control when
its intended failures were merely a subset of all observed failures. It now
requires equality before allowing the ordinary behavior controller to dispatch
an Agent. Extra failures remain visible and route to
`review-unexpected-control-failures`; missing intended failures keep the existing
Oracle/control repair route. This does not infer that every extra failure is a
cleanup cascade. Explicitly frozen multi-failure controls remain supported.

Rust regressions demonstrate that an extra failure blocks dispatch before an
output directory is created, and that a digest-bound lesson review cannot admit
such a capture. Original raw captures and historical contracts are unchanged.
This is a generic consumer/controller correction inspired by the real isolation
experiment, not a new emulator execution, automatic control producer or accepted
business loop. Overall maturity remains **70%**.
