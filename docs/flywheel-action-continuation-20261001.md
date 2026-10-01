# Retained Action continuation

Overall maturity remains **50%**, an engineering estimate. This checkpoint closes
a historical-feedback read path locally; it does not qualify a case or complete
autonomous downstream repair.

PR125 merged as `154e702c05cf783ab1eeb76d384757ae7b283348`.
[Linux Action 36923237834](https://github.com/yxsicd/agentlabrelease/actions/runs/36923237834)
succeeded on that revision with the v2 producer and consumer. Downloaded capture
SHA256: `357454d0a5a184e1fcabeb5211640a385fca4cb2efed4ef8902bae567612778c`.
Independent local CLI reconstruction reproduced its stage-next.json byte for byte.
This is real source semantic seam execution, not Harmony framework/API22 behavior.

The read-only history wrapper searches at most ten successful main dispatches from
the same repository and workflow. It independently reconstructs a compatible
predecessor's retained capture before trusting its plan. It copies only the three
self-contained predecessor files, keeps explicit selection provenance and leaves
all formal requirements in the current plan unchanged. Transport failures stop
collection; missing/incompatible artifacts cannot become accepted prior feedback.
History JSON must contain a runs array before selection. There is no recursive
history import or execution of historical sources.

A live local wrapper call downloaded the real Linux artifact and selected run
36923237834. It reconstructed prior observations and returned schedulingAllowed
false, qualified false. This proves live history recovery of a real capture,
not yet automatic history recovery in a new hosted workflow. Captures remain
outside source publication in the local artifact area and GitHub run artifact.

Rust regression runs fresh real workers across two arbitrary fixture repositories,
reconstructs the prior capture, checks repeat suppression and current formal
requirements, and rejects contradictory prior plans and self-rehashed fabricated
observations. These fixture identities do not prove real cross-repository migration.

Next: hosted cross-Action verification, scoped admission of the domain contract,
exact runtime qualification, candidate construction/freeze and actual Agent
assessment. No TableGit mutation, formal evaluation case, emulator verdict,
performance result or Release is added by this checkpoint.
