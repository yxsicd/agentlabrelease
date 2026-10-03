# Native original-export preservation and real remote recovery

Overall engineering maturity remains **74%**; accepted complete automatic business
loops remain **zero**. This closes complete operational export preservation and
recovery, not automatic semantic review, active knowledge admission or benefit.
PR233 merged at `dee1a26` after all applicable checks passed.

The ordinary observation destination accepts explicit preserveRawFiles=true for
reconstructed source suites. The Rust planner independently rebuilds the original
analytical rows, selects only the exact evidence_files inventory plus the original
typed export.json and table JSONL files, and deterministically compresses their
byte-exact records. Surrounding files, Agent homes, credentials and the separate
full failed-baseline/participant repair history are not implicitly archived.

`--describe-observation-archive --source DIR --output NEW_FILE` returns the native
raw_archive_chunks definition and bounded inventory. Provision that table through
the normal live TableGit author contract. Then use the existing importer with
preserveRawFiles=true. It retains one native planned cross-table transaction,
complete fixed-cut readback and recovery into an exclusively new directory.

`--recover-observation-export --plan FILE --remote-snapshot FILE --output NEW_DIR`
validates all expected rows, archive/chunk identities, exact member inventory and
bytes before creating output. It does not authenticate the supplied plan or prove
the snapshot was freshly fetched: the normal import workflow supplies the separately
verified commit receipt and exact remote queries. Recovered export metadata stays
byte-exact; do not relabel it as a committed export by editing its original manifest.

Budgets: 32 MiB total selected file bytes, at most 1000 files and 1000 compressed
chunks, 24 KiB chunk bodies encoded as lowercase hex (below deferred-string bounds),
bounded expansion and at most 1 MiB serialized insert groups per transaction.
Larger archives stop before mutation, rather than dropping evidence or pretending
the transaction was split atomically. Missing/changed chunks, unsafe or duplicate
members, symlinks, existing output and trailing gzip bytes reject. These limits
are an initial bounded adapter, not arbitrary-size evidence support.

## Real retained source-suite export

Independent operational repository: agentlabsourcesuite-37147845918.
Prefix: assets/observations/source-suite/.
Original reviewed lesson: lesson-rating-convert-source-seam-37147845918.

The retained real Action 37147845918 export contains **91 selected files,
689449 original bytes**, compressed to **153860 bytes in seven chunks**.
After table creation at ede78697deae64c6c85143528f009e9821cce49e, one native
transaction inserted seven rows and preserved all prior 207 analytical rows.
Exact committed readback at **9dbe415dbfc44acedeed3b639a661c60149ac9b3** passed
allRowsExact=true and remoteRawBytesPreserved=true. Archive identity:
95accd6008e6dc289355b914699dfb52ef83c6c4a9fbaed82f6d2d24de9996f0.

The Rust recovery read only committed snapshot chunks and restored all 91 files.
Using that recovered directory as source, the native planner exactly reproduced
the original plan, including independently reconstructed controls and reviewed
lesson rows. No Agent/worker rerun or operator source repair occurred.
An unchanged repeat used the recovered directory, queried that exact committed
baseline and inserted zero rows with no transaction and no revision advancement.
Complete native readback again reported remoteRawBytesPreserved=true.
External intents, commit/readback/recovery receipts and original/recovered plans
remain under flywheel-raw-evidence-recovery-OeN9Mn outside Release.

First provisioning discovery stopped before saving a write intent because its
Accept header omitted text/event-stream. Read-only authority inspection confirmed
the table absent; the corrected transport then created it once. No uncertain write
was retried. Authentication remains in the private Home Skill only.

Regression validation covers byte-exact recovery, deterministic planning, unchanged
repeat, unowned-file exclusion, pre-output rejection and rehashed unsafe archives.
Active knowledge, formal cases, Harmony execution and guidance benefit remain
unchanged/unqualified. Next: use the recovered and committed analytical source to
prepare explicit promotion/admission against a fixed knowledge baseline, then
prove actual later-round consumption and repeated benefit.
