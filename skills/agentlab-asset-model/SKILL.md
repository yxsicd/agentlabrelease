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
Test with real SWE/Harmony evidence plus a small public synthetic fixture. Prove
joins, context changes/history, tool errors, raw-file reconstruction and stable
repeat import, not only successful archival. Preserve release qualification gates.
