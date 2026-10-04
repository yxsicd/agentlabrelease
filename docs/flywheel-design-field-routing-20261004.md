# Design-local field diagnostics

Maturity remains 75%; accepted complete automatic five-stage loops remain zero.

Original run 37185115883 at method 903ed24019e03277502680f9db792c3c212ed063
completed its model design turn, then terminated before code construction with
`recipe author id absent`. The retained original design used numeric IDs for all
13 checks. Its attempts receipt declares one maximum revision but records only
attempt zero with repairable=false. No authority write or case acceptance occurred.

The native design validator now reports local nonempty-string failures with the
scenario/check/control/edit kind and exact JSON pointer. Existing orchestration
recognizes those design-local categories; generic request/author identity errors
remain terminal. No input coercion, repair-budget increase or old-run restart is
introduced. Native regressions reject numeric, null, empty and array values at
each affected field and verify original bytes remain unchanged.

These diagnostics enable future bounded correction, not proof that a real Agent
will correct its design or that the automatic feedback coordinator is complete.

Release checksum validation, Skill Creator validation and diff checks passed.
The two original local regression processes remain live without terminal results.
A read-only sample of the bounded-correction test process found its main thread
at `_dyld_start`, with a 96 KiB physical footprint and no test execution stack.
This is local startup evidence, not a failed assertion or a completed test gate.
Do not restart those original processes merely because observation timed out.
