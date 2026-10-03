# Durable source evidence and rejected correction

Overall maturity remains 73% (engineering estimate); accepted complete automatic
business loops remain zero. Operator archival closes a concrete preservation
gap, not semantic admission, automatic next-round consumption or learning benefit.

## Exact original suite preservation

PR223 merged at `989e658f8ac00587def2660e16b3358653fd6903` after all applicable
CI checks passed. Its new scenarioInputs API does not rewrite historical runtime
bytes or establish correct consumption by an arbitrary verifier.

The complete retained local suite associated with Action 37131931224 was exported
through the native Rust observation adapter and committed to the separate bare
TableGit repository `agentlabsourcesuite-37131931224` on `cbgroomtpc`.
The exact committed cut is `814d0ba33208eb78bc54089fce97a1d38e1763fc`, with
table prefix `assets/observations/local-source-suite/`.

Five native tables contain 221 rows: runs 1, analysis_records 1,
calibration_controls 7, checks 140 and evidence_files 72. A separate raw_chunks
table contains 69 bounded chunks preserving all 72 selected necessary files,
535268 bytes in total, including zero-byte streams through their file inventory.
No participant homes, Gateway credentials or unrelated capture files are copied.

Every native table was queried at that exact committed revision. Canonical JSONL
digests matched the original native export; every raw file was reconstructed from
remote chunks with exact offsets, lengths and SHA256. The native suite consumer
then read the reconstructed snapshot and independently reproduced six controls
plus accepted-reference recovery, with declarations-matched status and semantic
qualification still false. No worker/model was rerun for this recovery.

The reusable knowledge repository `agentlabtablegit` remained at
`da9a10a8049b138738d05aae9b2d47710b6b9a7d` before and after archival.
Twenty fenced data transactions followed table creation. This is manual operator
archival and exact committed recovery, not unchanged repeat-import qualification,
original cloud runtime restoration, producer authentication or remote replication.

## Real correction result

[Action 37138587647](https://github.com/yxsicd/agentlabrelease/actions/runs/37138587647)
used the merged method and one reviewed child of original Action 37131931224.
The original request/design were digest-bound before inference. Both Gateway
exchanges completed semantically: design 51722 ms, code 128449 ms. Independent
participant isolation passed. The zero code-repair allowance was not reset.

Baseline execution exited 1 before behavior observations:
`TypeError: CommonMapData_1.CommonBoolMapping is not a constructor`.
The mapping source constructs CommonBoolMapping/CommonColorMapping, but the
generated import adapter supplied only DEFAULT_KEY. No wrong controls executed;
this is verifier wiring failure, not a product invariant failure.

Source inspection additionally found all 20 checks and six controls preserved,
but all six scenario initialState/expectedObservations records changed without
approval, and one parser exception sequence changed. The verifier computed a
partial initialStateMatches flag without enforcing it, then overwrote fields
with declared state. Reading scenarioInputs does not establish valid constructor
verification or parent-scenario preservation. The legacy design-review lane's
prose did not enforce those complete records.

Keep the failed child and original suite intact. Use existing exact scenario-change
admission when a separately authorized successor needs controlled input changes;
do not fabricate lesson approval or reopen this child's exhausted allowance.
Real semantic correction, reviewed lesson admission, committed knowledge,
productive next-round consumption and cross-repository benefit remain missing.
