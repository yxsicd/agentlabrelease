---
name: agentlab-asset-model
description: Maintain analysis-oriented TableGit assets with separate reusable knowledge and evaluation-instance lifecycles.
metadata:
  agentlab-role: maintenance
  agentlab-layer: method
  agentlab-stage: asset-model
---

# Asset modeling and lifetime

Treat lifecycle independently from Skill layer and actor role. A repository-specific
semantic Skill has layer `instance` but is reusable across campaigns. A concrete
campaign result is an evaluation-instance asset. Temporary means scoped to an
execution, not permission to expire or delete evidence.

Maintain reusable `maintainer_skills`, `program_facts`, `evaluation_cases` in a
knowledge TableGit repository. These contain method/target guidance, version-bound
program analysis, oracle code and task/calibration contracts. Export exactly one
stable-order JSONL per table from a committed cut. Specific build/assessment
results, latest-run pointers and operational feedback belong to instance tables.

Create an independent TableGit repository for each operational Session/evaluation,
consuming a fixed knowledge cut. Destination configs are explicit: knowledge and
instances need not share a server or repository. The public development fixture
can verify the separation with distinct namespaces on one owned test repository;
that fixture arrangement is not a production storage requirement.

Use [the Rust normalizer](../../crates/agentlab_code_analysis/src/asset_model.rs)
and [executable import/export](../../examples/knowledge-seed/subject/ASSETS.md).
Model runs, attempts, phases, requests, context versions/changes, message contents,
response events, tool calls/events, source facts, checks and artifacts as separate
analytical tables. Use explicit join identities and schema fields for every retained
column. Do not mix storage block references with observation entities.

Context content versions deduplicate complete structured messages. Context heads
update the same logical message rows per request; preserve the resulting Git cuts
in `context_commits` and verify each historical context. Keep adapter evidence
separate from controlled gateway authority. Input-context appearances of tool calls
are not proof of which request produced a call; response wire events carry the
controlled output evidence.

Retain complete original files in the separately published instance evidence
bundle with path/size/SHA-256 records. Stream rows hold event deltas; cumulative
adapter snapshots remain accessible byte-for-byte in original files. No data is
redacted or discarded. Transient Workspace/build binaries remain SessionFS state;
published HAPs have external asset URI/size/hash records.

Operational ingestion must not mutate reusable knowledge. Promote a general lesson
explicitly after examining source-bound evidence; maintain reusable guidance and
its provenance rather than automatically copying run results into the next seed.

For retained stage calibration, use the Rust flywheel CLI's
`--export-stage-calibration` mode with the selected candidate, downstream plan,
contract, original capture and capture SHA256. It independently reconstructs
observations before exporting typed controls, checks, infrastructure failures and
analysis records. Keep all five input/feedback files with their exact hashes;
the exchange manifest describes analytical JSONLs, not a substitute for raw files.
Use a fresh output directory. Repeat the same inputs into another fresh directory
and compare bytes; an existing destination or invalid capture must be rejected.
The normalized run identity includes the consumer source digest: it identifies a
particular interpretation of retained evidence, not a new physical execution.
Failed workers remain infrastructure observations, never completed wrong variants.
This export alone proves neither TableGit persistence nor knowledge promotion,
Harmony runtime qualification, or a qualified evaluation case.

For MCP ingestion, load the instance's current table-author/query contracts and
resolve an independent operational destination before writing. Verify exchange
and raw-file hashes first, create definitions at exact revisions, and insert
missing analytical rows in a revision-fenced atomic batch. Compare existing rows
exactly; a differing stable identity is a conflict, not permission to overwrite.
Read every imported key from the resulting committed revision and repeat import:
no pending row changes must mean no new transaction or revision. Record the
knowledge repository's before/after cuts independently. Restore feedback from the
committed analysis record and let the Rust consumer reconstruct its original raw
capture before trusting scheduling. This verifies persistence and continuation,
not learning improvement. Remote hash/path rows do not preserve the referenced
raw bytes; separately prove the evidence bundle's durable availability.

Test with real SWE/Harmony evidence plus a small public synthetic fixture. Prove
joins, context changes/history, tool errors, raw-file reconstruction and stable
repeat import, not only successful archival. Preserve release qualification gates.

Behavior lesson exports keep actual submissions in `attempts` and link their
typed checks by attemptId, separately from calibration_controls/controlId. Retain
both passing and rejected attempts, source/stdout/capture identities and raw bytes;
do not substitute the calibration verdict map for participant outcomes. Re-export
retained evidence with a changed consumer into a fresh directory: the new run
identity is a projection version, not another execution. Behavior-only reconstruction
does not verify participant completion, authenticate its producer or qualify a case.

Resolve the live transport contract before reusing an ingestion recipe: a legacy
Service WebSocket client is not an MCP Skill-kernel client. Use the instance's
discovered read/write operations, explicit Person and revision fences. Bind the
actual method commit when promoting outside Action; an exported candidate with
null methodRevision is not admissible. Preserve that rejection and regenerate
into a fresh destination with verified method identity, rather than patching the
rejected candidate. Remote analytical readback does not preserve raw evidence
bytes merely because evidence_files hash/path rows were committed.

Archive operational observations without inventing a reviewed lesson. Use
`--export-behavior-observation` with the bound candidate corpus/id and original
contract/capture into a fresh directory. The same Rust reconstruction exports
runs, controls, attempts, checks, analysis and three exact raw files, without
lesson/reviewer/knowledge-target rows. Retain failed calibration as failed;
malformed or incomplete worker captures remain rejected. Review and promotion
are later independent gates, not prerequisites for preserving valid observations.

Connect completed behavior-loop attempts to that exporter in the ordinary Action,
including normally completed rejected tasks. The thin loop transport rechecks
frozen inputs and reconstructs each stored feedback through Rust before exporting
every attempt separately. Preserve raw captures when an incomplete loop cannot
export; do not infer task failure from missing terminal data. Observation exports
create no lesson and perform no remote persistence or knowledge admission.

When an execution repository contains several runs, distinguish a whole-table
export from an explicit runId selection at a committed cut. Record the selection
predicate and compare exactly those rows; a newly appended run's counts cannot
describe all remote rows. A new consumer digest changes the projection identity,
not the physical execution count or learning evidence.

Use the Rust observation-store planner and readback verifier through
[the operator MCP importer](../../scripts/import-behavior-observations.cjs) for
observation-only persistence. Supply an explicit separate repository, fixed
revision and transaction UUID; current tables must already exist. The native
planner reconstructs all rows from original evidence, rejects stable-ID conflicts
and emits inserts only. The verifier reproduces the plan from the original
baseline and compares every prior and new row. No missing rows means no transaction
and no new revision. Authority drift or uncertain writes stop; retain intents and
reconcile instead of rebasing or retrying with another UUID. Current snapshots are
bounded to 1000 rows per table; truncation rejects rather than guessing completeness.

Before connecting an exported knowledge cut to the business runner, verify its
source-set.txt against sourceSetSha256 as well as table and operation sidecars.
A missing portable sidecar is an export defect, not an Agent task failure. Restore
only hash-identical bytes into a fresh derived bundle and keep the rejected cut
unchanged; do not rewrite its manifest or claim another knowledge commit.

Knowledge admission and consumer publication are separate transitions. Before a
new automated round, compare the consumer branch's published cut with live
authority and read back all five tables at that exact revision. If publication
lags, publish the verified portable snapshot, including assessment and operation
receipt dependencies, before spending another Agent budget. Preserve assessed
raw bytes and historical candidate bindings; equivalent canonical rows do not
repair missing sidecars. A pushed branch is not the default-branch consumer:
confirm the merged cut and its admission check before claiming the loop unblocked.

If live committed HEAD differs from a retained cut, separately test exact-cut
readability before calling it data loss. Preserve both identities and reconcile
history and table contents; an accessible historical cut is not current authority.
Resolve literal table paths from evidence/contracts: knowledge root paths and an
operational namespace prefix need not match. A rejected guessed path does not
prove an instance outage. See the [fresh Action checkpoint](../../docs/flywheel-main-action-checkpoint-20261003.md)
for the separate execution, export and authority boundaries.

When ancestry and exact table readbacks prove ordinary forward advancement,
catch up the consumer publication rather than rewinding authority. Reassess the
portable snapshot with its original parent assessment and verify referenced
receipt bytes before selecting new work. A new plan proves input freshness, not
operation execution or a completed round. See the
[knowledge publication checkpoint](../../docs/flywheel-current-knowledge-publication-20261003.md).
