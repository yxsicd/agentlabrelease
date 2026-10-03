# Exact-review recovery and observable initialization

Overall maturity remains 73% (engineering estimate); accepted complete automatic
business loops remain zero. This checkpoint contains a real reviewed successor
and a reusable initialization assertion, not successful semantic qualification.

PR226 merged at `7b54049f2537f6165f51a32a6f33a06b87101c8c` after all applicable
CI passed. Its capture fix is not part of the historical run described below.

## Recovery evidence

The original Inspector preflight passed locally without changing its transport.
A separate modern sessionless read, using the same Action caller without the
private operator profile, read all five tables at
`da9a10a8049b138738d05aae9b2d47710b6b9a7d` and matched every published payload.
The largest query returned all 489 scope rows in 14787 ms; all five concurrent
queries completed in 14808 ms. These successful point-in-time checks do not
establish the cause of the previous cloud timeout or a transport speed benchmark.

[Action 37142100477, attempt 2](https://github.com/yxsicd/agentlabrelease/actions/runs/37142100477/attempts/2)
recovered the same failed pre-inference job exactly once, retaining source
`db702d8818f284d14a1e64a0d5c344d9aec7271b`, parent 37141430630, the original
review, one design correction allowance and zero code repairs. Attempt 1 remains
a pre-inference failure; no consumed model budget was reopened. Cloud knowledge
preflight, build, review binding, generation, isolation and baseline passed.
The control suite stopped on its first nonbaseline reference with exit 1, not a
timeout. Original capture was uploaded and downloaded outside Release.

The successor retained every complete scenario and check. All seven control IDs,
roles and edits remained unchanged. Only wrong-invert-text-color's expected
failure set changed to the two Button checks as requested. Native exact-contract
protection passed, with successor design SHA256
`f6c9ef946211c1d3b8ac5bf225fd87fc3bb8498ec772dd58142a0ea7a2660f6c`.
This is meaningful contract-preservation evidence, not verifier correctness.

## Executable defects

The generated verifier reconstructed an EDITS map and reapplied edits to
runtime.source(), although the runtime had already applied the selected control.
reference-extract-parse-local consequently threw `edit must match exactly once`.
Its locally edited string was also unused by loadModule(), which consumes the
runtime's own transformed text. Only baseline and that failed reference have
captures; no remaining wrong-control result or reference recovery is claimed.

Constructor fields were read from the actual instance, but differences only set
constructorState.match=false, a flag outside all frozen check pointers. No throw
enforced that comparison before generate(). This fails the review requirement,
even though all eight baseline checks passed. Keep the failed child terminal;
do not rewrite its source or invent a completed suite or accepted lesson.

## Reusable runtime support

The generic runtime adds assertInitialState(scenarioId, actual, pointer=''). It
compares actual JSON-compatible observations with a selected RFC6901 subtree of
frozen initialState, disregards object key order while preserving array order and
object/array identity, and throws on mismatch, absent pointers or unsupported
values. It never assigns expected values into an instance. The caller must let
the error escape before invoking the tested operation.

The author prompt now states transformation ownership at the source/loadModule
entry and offers the assertion rather than an ungraded match flag. Program
analysis guidance records this general lesson without tying it to Toggle or a
particular repository. Existing runtime invocation and scenario schemas remain
compatible. Choosing the observed subtree still requires semantic review; the
API cannot prove complete state coverage, honest observation or mandatory use.

A Rust-hosted runtime regression executes fresh source instances, accepts correct
initial state, rejects a constructor mutation before the method runs, and checks
escaped pointers, missing/null distinctions, object/array distinctions, key order,
extra fields and non-JSON values. It also verifies that source() and loadModule()
see the same once-transformed body. Related native suites passed 48 tests. This
is executable API qualification, not a fresh model's successful adoption.

Remaining work: new bounded construction using the updated method; complete
positive/negative controls and recovery; independent semantic admission;
automatic durable knowledge return and actual later consumption; measured
multi-round benefit, another repository and full Harmony execution qualification.
