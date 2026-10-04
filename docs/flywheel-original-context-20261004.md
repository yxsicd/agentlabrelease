# Original-context continuation checkpoint

Overall maturity remains **75%**, an engineering estimate. Accepted automatic
five-stage rounds remain **0**. Dependency recovery is not a completed round.

## Real observations

The retained constructor run is `37212274329`, producer method
`6ee9e6b966ac0d7c72eb90667c3691a2658f3972`. No new model call or claim reset
was performed. The original candidate already passed native original-wire and
frozen repair-output requalification, but host staging rejected executable drift.

The original runner's software inventory identifies Node 22.23.3. Its author-host
binary is distinct from the participant's Node Docker image. Recovery on hwlinux
used the official Node archive and TypeScript 5.9.3 package, then compared the
actual extracted bytes with the unchanged original request:

| Dependency | Original and recovered SHA256 |
| --- | --- |
| Host Node executable | `fde6a4bf8d0562f7751d1a2d6cb9b417c4cfe107bbcb0aa3e9a24e125e348f48` |
| TypeScript compiler | `3ae902c92cc44dace175c0e69e13a4b0899f6983c6121d76b9ab8dd5795e7675` |

Dependency recovery operation `exec-00000000000002ba` returned exit 0 with both
`matchesOriginalRequest: true`. Exact target peer was
`lgw_60b9b37d14c4447f919196105a1a8b8a`, route `peer_direct`.

Source commit `7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6` was restored from
existing Git objects into a separate clean checkout. The original published
knowledge cut `f41c1bdfa145bacbe28f445e35707c0b2b1772ec` was taken from the
producer's Release commit. Their original paths and the recovered dependencies
were mounted in a network-disabled, read-only-root, capability-dropped container;
the host's global Node and original request were not changed.

This static staging uses exact local image
`sha256:9a73a5088750b4c95158ab26629c854c3d6fc4b173cb7bc8079ad252d8ed7bfa`
and native validator SHA256
`0770fa49cbecff7f71516b9fa1725e51e294026461b429b34ad45d3b1c5e8226`.
It is not claimed to recreate the original participant image or authenticate
producer effects. It executes the trusted native validator, not Agent verifier code.

Operation `exec-00000000000002c0` returned exit 1 with
`construction repair loop intent missing`, without timeout. Original request SHA256
remained `6de35b3f778c1dd5e39b2f2510460c5d57e16ff9a64ca520aa8f29db78d4041d`.
This exposes a consumer mismatch, not a semantic rejection: repair packet v2
requires a null inherited loop intent and exact one-successor enrollment, while
the staging adapter still required a string intent after admitting that packet.

## Narrow repair and acceptance

Keep native repair-output reconstruction first. Only the admitted v2 continuation
lane omits inherited loop intent at staging. Legacy v1 still requires its original
intent. The staged repair packet retains the full enrollment and original failure,
and later diagnostic preparation and approval reconsume it.

The native regression crosses preparation, staging, diagnostic preparation and
approval. It checks exact request/design bytes, absence of fabricated old intent,
and rejection of extended successor budget, inherited intent in v2 and null intent
in v1. Fixture approval is explicitly static API testing, not real Oracle approval.

Native regression operation `exec-00000000000002c5` passed on hwlinux, exit 0:
`diagnostic_code_repair_staging_and_approval_recheck_real_source_and_frozen_parent ... ok`.
The first new fixture failed because it supplied an infrastructure-error capture
to a lane that requires completed baseline observations. It was replaced by a
separate explicitly synthetic complete-baseline capture; neither original real
evidence nor continuation admission was changed.

Post-fix operation `exec-00000000000002c6` ran the same real candidate through
the restored isolated namespace and returned exit 0, without timeout. Validator
was a local debug candidate, SHA256
`1b4a330867e8e86f125f154cfd8ced025f391fc8ccc27d1ec489fb5eb5e211c3`,
not a published Release. Native stage receipt retained the original request,
proposal, design and repair packet digests and reported `reviewed: false`,
`executionPerformed: false`, `automaticPromotion: false`.

No baseline, complete control suite, independent review or committed return is claimed.
Remaining priority is actual candidate execution and acceptance, followed by the
existing knowledge writer/readback/next-round interfaces, then multiple rounds
and cross-repository transfer.

## Follow-up: actual baseline and complete controls

PR #292 merged as `c5c8a89b12b9991a13ce97a9e445c87432420451` after all
head checks passed: Rust and Harmony run `37216339629`, component run
`37216339601`, and all eight public validation jobs in run `37216339592`.
This is a source merge, not a formal Release.

The original registry index from the producer pull log is
`sha256:a9f5f7c91a432850b2a8a7797adf5eadb6c733ceed61167806cee7ea7fbc29df`.
Its linux/amd64 platform manifest is
`sha256:e5a8dee7bc1e6a215d224a7ef8206f7e77271bc3cabd5febf2beafac0674f174`,
which references original config
`sha256:622f209f6c16ba5af4d9a337cae6577d096f17174b904cfc6a5b0c81a2679c24`.
hwlinux's current Docker store reports the index as its local image ID, unlike
the original runner's config ID. The first literal comparison stopped before
execution. The follow-up preserved that failure, checked platform manifest raw
bytes against its digest, matched its config to the original, and retained the
full inspect output and explicit identity mapping. The new diagnostic descriptor
pins the actual local index identity; no original participant receipt was edited.

Baseline operation `exec-00000000000002cd` returned exit 0: all **12/12** frozen
checks passed. The earlier ancestor had **4/12**; no checks or design expectations
were weakened, no new author turn or code repair was performed. Feedback SHA256:
`81b039208c285cd3f29697fbe9c108d8d41b2350b36b254cd146a4c5a2e7a7f8`.

Complete suite operation `exec-00000000000002ce` returned exit 0. Native readback
reconstructed all six controls plus one fresh reference recovery, with status
`declarations-matched`, `completeInventoryReconstructed: true` and
`acceptedReferenceRecoveryReconstructed: true`:

| Control | Observed outcome |
| --- | --- |
| Original baseline | All frozen checks pass |
| `ref-color-ternary` | Valid alternative passes |
| `ref-for-of-loop` | Second valid alternative passes |
| `wrong-button-branch` | Exactly three declared failures |
| `wrong-ison-parse` | Exactly two declared failures |
| `wrong-switch-codeone` | Exactly four declared failures |
| Fresh `ref-color-ternary` recovery | Passes after wrong controls |

Suite result SHA256:
`976c7e626f15acbaf13ec9897b2517624cc44b37e5a11ff703ad0fea66c827dc`.
Observation export SHA256:
`136a0ec6baec61b1c5c6ecfe2e02a27b54fa1224c0c9e54a34ce76a164f47e4f`.

Native review preflight operation `exec-00000000000002d1` returned exit 0 and
`reviewPreparedOnly: true`, `reviewerExecuted: false`, `qualified: false`.
It reconstructed the exported suite against the independent clean source checkout
and frozen generic rubric. It is **not** a reviewer verdict.

Overall engineering maturity is now **76% (+1)** for real candidate behavioral
calibration and recovery evidence; accepted automatic five-stage rounds remain
**0**. Diagnostic feedback still reports `formalIsolationQualified: false` and
`semanticQualified: false`: practical network-disabled containment must not be
reported as formal isolation or independent semantic acceptance. No HAP/emulator,
performance, accepted knowledge write, committed return or next-round execution
is established by these source-only observations.

The next integration gap is reception of this post-generation evidence by the
review/return lane. The current review Action requires an original constructor
Action artifact; the original failed run cannot contain this later local suite.
Do not relabel the local ZIP as that original artifact or dispatch the old
incomplete artifact. Preserve producer and current-validator identities separately
and bridge retained completion to execution/review without another author budget.
