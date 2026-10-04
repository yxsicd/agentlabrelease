# Source-only runtime closure and immutable repair scope

Engineering maturity remains **79%**; accepted complete automatic rounds remain
**0**. This is failure diagnosis and generic repair guidance, not a successful
construction, platform qualification or measured learning benefit.

PR302 merged as `3a8433b9749829cb7e7eb75fda9cc176f04cca98` after local full
Rust regression and all three exact-head workflows passed. Fresh run
[37234369136](https://github.com/yxsicd/agentlabrelease/actions/runs/37234369136)
passed frozen-target preparation, completed real design and verifier generation,
and staged the unreviewed original proposal. The request-reconstruction blocker
from run37232947775 did not recur.

The original baseline exited 1 with no observations or graded checks. A real
dependency's module initializer invoked a platform resource global `$r` absent
from the explicitly supplied host globals. Native feedback classified this as
`verifier-execution-infrastructure-failure`, not a failed behavioral check. No
wrong controls were executed. One enrolled code repair completed generation but
removed the dependency path from its frozen `sourcePaths` array; native staging
rejected `construction repair changed frozen checks/controls/source paths`.
Checks and control declarations were preserved, but scope preservation was not.
Complete controls, independent review and knowledge commitment did not complete.
The review artifact contains enrollment only, not a reviewer outcome.

Original source ZIP SHA256:
`630bf3b67a56f05bb65a51c1f2f7043c1942dc9748fbc188c5b16cef8f8c9c93`.
All original inputs, captures, design, proposal and exhausted budget remain
unchanged. No repaired execution of this root is claimed.

Generic improvement: expose native-admitted immutable proposal fields directly
in code-repair context, including the complete ordered source-path array. Native
admission retains the same exact equality policy while identifying `/sourcePaths`
specifically when that array differs. This does not authorize dropping dependencies,
rewriting expected results or adding default platform stubs. Runtime closure must
cover transitive module initialization as well as tested methods; declared external
behavior is distinct from real device behavior. A future fresh constructor needs
source-bound explicit environment closure and full original-demand coverage,
including observable state after exceptions, before any benefit claim.

Rust-driven tests exercise the actual prompt helper for two unrelated identities,
preserve parent bytes and dependency-path order, and ensure independently returned
projections cannot mutate the packet. Native repair regressions reject contract,
source and design drift and check the new source-path diagnostic. They do not
prove that an Agent complies with the guidance.
