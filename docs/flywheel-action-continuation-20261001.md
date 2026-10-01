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

## Operational exchange implementation — 2026-10-02

PR127 merged as `552f94c79745a8333fb43c52f27e1fe8457c3509`.
Overall maturity stays **51%**: evidence export is not yet effective learning.
The Rust `--export-stage-calibration` CLI independently reconstructs raw capture
checks and exports `agentlab.asset_exchange.v1` evaluation-instance tables.
It preserves five original input/derived feedback files with exact hashes,
completed controls and individual checks, while keeping infrastructure failures
separate. No reusable knowledge or formal qualification is updated.

The retained real Linux capture from run 36925772376 successfully exported
one run, one analysis record, three controls, eighteen checks and five evidence
files. All JSONL manifest hashes and raw-file hashes/lengths were checked.
The original capture remains bound to SHA256
`a802d6f381503a983dd1cfa305d4751e4f6c629557e38539e537f8ff10e3c507`.
CLI regression checks two byte-identical fresh-directory exports, manifest
hashes/counts, all raw evidence hashes/lengths, rejection of an existing output
without overwriting it, and invalid capture rejection before directory creation.
The source-bound consumer digest distinguishes interpretations of the same
physical capture; it must not be counted as a fresh execution.

The diagnostic workflow now exports these assets into its existing evidence
artifact. This workflow change has not yet been executed on a hosted runner.
TableGit ingestion/readback/repeat, independently durable raw-file publication,
explicit lesson admission and a changed next knowledge/case cut remain unproven.
Continue there rather than treating successful archival as a completed loop.

Final local verification: `cargo test -p agentlab_code_analysis --quiet`,
`cargo fmt --all -- --check`, `python scripts/validate-release.py`, the asset
Skill validator and `git diff --check` all exited zero. Raw run evidence remains
outside the source repository; only code, method guidance and this evidence
summary are included in the source change.

## Real TableGit persistence and continuation — 2026-10-02

PR128 passed all ten applicable checks and merged as
`995a9216075f3d7603bd163a3c6264893a0172ab`; immutable publishing was skipped.
Maturity stays **51%** until feedback improves a subsequent knowledge/case cut.

Live discovery confirmed the configured MCP destination is
`https://cbgroom-tpc.ru.yxsbase.win/mcp` and its table contracts are version 2.3.0.
The retained real capture was imported into the new independent bare TableGit
repository `agentlabstage-a802d6f38150`. Six typed tables were created with exact
revision fences; one atomic batch inserted 28 analytical rows. Every imported
key was read back at committed revision
`72536b552f030580b5748775de1829829c2b7fe5` and compared with the source export.
Repeat import found zero pending groups, verified the same 28 rows and retained
the identical revision. The existing knowledge repository `agentlabtablegit`
remained at `38fc28d72870b36405287e048a5e6fce41a44b78`, with dirty=false.

The committed analysis feedback was restored through table_rows_get and consumed
by the Rust controller with independently reconstructed retained raw capture.
It returned schedulingAllowed=false, qualified=false and the scoped-domain
review action. This is operator-driven replay of a retained actual Linux run,
not a fresh execution, an assessed Agent run or autonomous learning. Original
raw files remain in local/GitHub artifacts: the new TableGit evidence_files rows
are hashes and paths, not remote byte preservation. A separately durable bundle,
explicit lesson admission and changed next-round knowledge remain outstanding.
Non-secret operation/readback receipts stay in the external local artifact area.

## Scoped experience candidate — 2026-10-02

Hosted run 36929704215 succeeded on PR128's merge revision, including the new
operational export. Its capture SHA256 is
`c59a9c7c48e11d38f91911c4509321a21c33cd2a0f3e4a685c5223e6b96af878`.
PR129 merged as `a60f62d808cc90f971fc0be4065da031789266ef` after seven applicable
checks passed. Overall maturity remains **51%**: effective next-round learning
is still unproven, despite this new promotion-candidate path.

Rust `--export-stage-lesson` consumes a byte-bound explicit interpretation review,
independently reconstructs an accepted control and at least two intended semantic
failures, and exports the existing experiment_lessons/lesson_evidence/
lesson_validations entities. It never runs automatic promotion. The review's
identity is recorded attribution, not authentication; its cause/guidance is an
explicit maintained interpretation, not automatically established causality.

The real reviewed controls were persisted in independent TableGit repository
`agentlabstage-c59a9c7c48e1` at
`c947cde00de38abd68ae01f7aa855da74c318840`. All 32 rows were read back exactly;
repeat import returned zero pending groups and the same revision. From that
confirmed cut, the existing experience promotion command produced a separate
candidate against the actual published first-four baseline. Independent checks
confirmed all twelve old Skill rows and sixty-one old fact rows unchanged,
exactly one added Skill and one added fact, committed lesson provenance, false
formal qualification and no evaluation cases. A second fresh candidate export
matched byte for byte. The method revision is
`dc66c9421172d98929caf0dcb58a531bc0d51d33`.

The first real-baseline promotion failed because program_facts.modules contains
both object and array values. The failed partial export is retained externally.
The shared exporter now represents heterogeneous inferred fields as JSON and
records their observed types without coercing values. Explicitly owned columns
remain strict; tests reject a string-valued boolean check. Tests also exercise
promotion against the actual first-four rows, not only an empty fixture.

No active knowledge admission, next-round effect, formal case or Release is
claimed. Next: admit the reviewed candidate at an exact knowledge cut, export it,
then measure real downstream use and preserved qualification boundaries. Durable
independent raw-byte publication and cross-repository execution remain separate
outstanding requirements.

Local final validation: the full Rust package suite, formatting, release
validation, Skill validation and diff checks passed. Operational review files,
captures, committed readback receipts, failed partial output and separate
promotion candidates remain outside the release source repository.

## Lesson admission identity repair — 2026-10-02

Overall maturity remains **51%**. Active admission and effective next-round
guidance consumption are still incomplete; this change does not count as a
learning round. Live inspection found that the candidate Skill omitted the
target-operations ownership required by the published knowledge gate. The
existing promoter also replaced colliding IDs silently and allowed an empty
validation set or a passing validation belonging to a different lesson.

Promotion now emits ownershipPlane=target-operations, automaticPromotion=false
and sourceRevision on both new rows. Stage lessons retain repositoryId from
the independently byte-bound candidate and promotion propagates it without
inventing a target from an operational repository name. Legacy scenario exports
without a repository retain that explicit absence. Existing target IDs, empty
validation sets and borrowed validations fail before candidate output creation.
The actual CLI regression exercises two arbitrary source identities, unchanged
published baseline rows and these rejection paths. Such fixtures do not prove
real cross-repository learning.

The original hosted capture c59a9c7c48e1 was independently reconstructed into
the external stage-lesson-admission-source-v1 export: nine analytical tables,
qualified=false, with the bound guide-snippets source identity. This is a local
new interpretation of retained evidence, not a fresh execution or a committed
replacement of the previously persisted lesson cut.

The next authority transaction still requires a refresh record binding the
updated Skill/fact hashes and the unchanged scope evidence. Current focused and
semantic Agent refresh paths do not consume newly promoted guidance bodies.
Applicability must be explicit rather than inferred from repository name alone;
active admission, provenance-bound prompt consumption and a measured next-round
improvement remain the critical next actions. No active knowledge write, Agent
run, formal case qualification or new Release is claimed by this repair.

## Explicit admission plan — 2026-10-02

Overall maturity remains **51%**. The Rust CLI now exposes
`--prepare-lesson-admission --knowledge BASE --proposal CANDIDATE --lesson-source
EXPERIENCE --lesson-id ID --expected-knowledge-revision OID --output NEW_FILE`.
It checks all five baseline table bindings, contiguous refresh history and latest
hashes, then independently reconstructs stage lesson entities from the retained
candidate, plan, contract, capture and review. It preserves every baseline row,
allows exactly one reviewed Skill/fact addition and no evaluation-case change,
and binds provenance, guidance, qualifications and method identities.

The result proposes three inserts: Skill, fact and a contiguous refresh row with
updated table hashes, unchanged scope readiness and the reused prior assessment.
The assessment is explicitly marked reused; neither new semantic/maintenance
coverage nor runtime qualification is manufactured. Repeat planning is identical,
and existing outputs are not overwritten. The actual CLI regression also rejects
wrong knowledge revisions, altered guidance and forged qualification. Two
arbitrary fixture source identities exercise the producer and planner; their
declared commit metadata is not evidence of remote persistence or generalization.

The original real committed export at c947cde... fails reconstruction against
the new source-bound interpretation, before output creation. Its older rows omit
the repository identity introduced in the previous repair and bind the earlier
consumer source digest. Preserve that cut;
re-export and persist the new interpretation separately, with exact committed
readback, rather than overwriting historical evidence or weakening reconstruction.

The plan itself does not authenticate its declared source commit. Remote source
readback and full staged knowledge-cut validation remain prerequisites before
the authority transaction. The current planner does not yet assemble that full
publication snapshot or invoke the writer. Effective downstream consumption and
measured next-round benefit remain incomplete; no authority write, new Agent run,
qualified case or Release is claimed here.

Verification: full Rust package tests, formatting, release validation, Skill
validation and diff checks exited zero. The real old-export rejection exited
one with no admission-plan output. PR131's previous identity repair passed all
ten applicable hosted checks before merging; immutable publication was skipped.

## Real source persistence and full admission staging — 2026-10-02

Overall maturity stays **51%**. The updated interpretation was persisted in the
independent bare TableGit repository `agentlabstage-48eb54481017`, committed at
`3a9d8a4fc7a720e13741da1b70f3bc96c2636568`. Nine typed tables contain 32 rows;
every key was read back at that exact revision. Repeat import found zero pending
groups and retained the same revision. The previous interpretation was preserved,
and active knowledge remained at `38fc28d72870b36405287e048a5e6fce41a44b78`.
Remote evidence-file rows still contain only hashes and paths, not raw bytes.

Promotion from that read-back cut against the real first-four baseline succeeded
with method revision `3e289ca9b7866458d71ee758034dd78c3920523f`. The real admission
plan then succeeded, with exactly one Skill/fact and a refresh insert proposed.
The unchanged-scope candidate was independently reassessed: program-bound 46,
semantic-ready 41, maintenance-ready 2, total scopes 489. Its program-facts input
hash changed, so reusing the original assessment as its evaluator would be wrong.

Rust `--stage-lesson-admission` now independently reproduces the prior strict
assessment and evaluates the new facts, requires equal totals/policy/scope
verdicts, preserves baseline files and operation receipts, and binds the new
assessment and updated table hashes to the refresh history. It produces a fresh
full staging directory; a partial filesystem failure is retained as failed output,
never represented as a committed snapshot. The existing writer explicitly
accepts reviewed-lesson sidecar contracts and rejects readiness overclaims.

The real staging path succeeded and the writer's portable-evidence check verified
five sidecars including both inherited operation receipts. Rust CLI integration
tests exercise the same adapter and reject a forged advanced-scope result; fixture
identities remain fixture evidence, not real cross-repository generalization.
Raw source/readback receipts, candidates, plans and staged snapshots stay outside
source Git. Active knowledge admission, fixed-cut guidance consumption and actual
next-round improvement remain outstanding. No new assessed Agent run, qualified
case or Release is claimed by persistence and staging.

## Active admission and scoped guidance consumption — 2026-10-02

Maturity remains **51%**. The reviewed real lesson was admitted into active
agentlabtablegit at `368b17895b23633656a26f9f51cb300cb11fa829`, from the exact
`38fc28d72870b36405287e048a5e6fce41a44b78` baseline. The existing writer's delta
computation proposed only three inserts: Skill, fact and refresh round 39.
All five remote baseline tables were compared exactly before mutation; nine source
entity tables were read back again at their recorded committed revision. Owned
Rust staging was reproduced and compared before one atomic transaction. The cold
export preserved baseline files and five portable operation sidecars. Exact
committed readback confirmed 13 Skills, 62 facts, 489 scopes, 39 refresh records
and zero evaluation cases. Two repeat synchronizations attempted no write and
retained that revision. No readiness or qualification was advanced. The private
authentication bridge loaded credentials in memory; the generic writer's
refreshed-revision retry was not used for this admission.

PR133 passed all ten applicable hosted checks and merged as
`8c344a80b71f238af778e6990accd4844682153d`; immutable publication was skipped.

The next implementation binds explicitly selected lesson guidance to a committed
export, exact source set, stage, row digest and object applicability. The Rust CLI
rejects changed cut/table/row/source/stage bindings and carries body, method/lesson
provenance and unchanged qualifications. The existing multi-repository calibration
authoring runner retains and independently rebinds inputs; its Pi adapter puts
the packet in the turn prompt and retains prompt bytes plus a consumption intent.
Tests with arbitrary fixture identities demonstrate protocol invariants, not
real cross-repository learning. Guidance is not applied globally by repo name.

Admission/readback/export/repeat receipts and operational bytes remain in the
external flywheel-action-continuation-20261001 artifact directory. Actual model
request capture verification, improved next-round results, autonomous multi-round
continuation, durable remote raw bytes, exact Harmony runtime and real second-repo
migration remain outstanding. No learning benefit, new assessed Agent run,
qualified case or Release is claimed by prompt assembly.
