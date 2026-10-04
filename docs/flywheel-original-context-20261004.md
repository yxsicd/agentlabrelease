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
