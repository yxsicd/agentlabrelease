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

## Hosted continuation verified — 2026-10-02

Overall maturity estimate: **51%** (previously 50%). The increment reflects real
hosted cross-run recovery and continuation, not full autonomous repair or promotion.
PR126 passed all ten applicable checks and merged as
`85b928c6e29785bfd0e33123eb0ac5042c37a442`; immutable publication was skipped.

Two fresh Linux dispatches on that merge revision completed successfully:

- [36925447893](https://github.com/yxsicd/agentlabrelease/actions/runs/36925447893)
  selected run 36923237834. New raw capture SHA256:
  `d5d3460fdcf3f78a1bf9504b364356980b1bfa7b2196750bdc77c14a6b08b265`.
  Independently reconstructed resumed output matched its complete feedback bytes.
- [36925772376](https://github.com/yxsicd/agentlabrelease/actions/runs/36925772376)
  selected the first fresh dispatch. New raw capture SHA256:
  `a802d6f381503a983dd1cfa305d4751e4f6c629557e38539e537f8ff10e3c507`.
  Its retained predecessor files matched the first dispatch byte for byte.
  Independent predecessor/current reconstruction with the clean d37efa0 consumer
  reproduced the owned semantic task identity and current decision/output;
  history-selection metadata was checked separately.

Both returned schedulingAllowed false, qualified false, and all four unchanged
formal actions. The workflow reexecuted controls before deciding about follow-up
scheduling; this is not a computation cache. Each artifact retained only one
self-contained predecessor. This proves unchanged-evidence continuation, not
automatic repair after new evidence or assessed-Agent progression.

Inspection exposed a generic scheduling gap: the captured Node version was not
included in task identity. The new semantic-work v2 digest includes this declared
runtime and the feedback retains it explicitly. Regressions require replanning on
runtime change, reject missing runtime/prior identity and preserve same-runtime
fresh-capture suppression. Older plans cannot be rewritten into compatibility:
the bounded history wrapper rejects them and selects fresh feedback until a new
compatible plan exists. This correction is locally tested, not yet a new hosted
workflow verdict. Version strings do not authenticate binaries or lock an OS.

Live AWMCP read-only probes exec-01d5/01d6/01d7, each exit zero and peer_direct to
hwlinux/ma, observed only API26 in the explicitly checked image/instance roots.
The checked commandline SDK directory exposed HDC and its dependency library,
not a full SDK or manager. A wider AgentLab-root probe exec-01d8 exited one on
private-directory permission errors; its partial output remains preserved and
does not prove API22 or other SDKs absent from the host. No image acquisition,
emulator launch, global absence claim or runtime substitution occurred.

The next substantive gap remains reviewed domain-contract admission plus exact
runtime and case freeze/execution. No TableGit write, formal evaluation case,
assessed Agent or Release is introduced here.
