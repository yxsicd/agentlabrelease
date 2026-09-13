# Reusable knowledge and evaluation-instance assets

`skillLayer: instance` describes target-specific knowledge; it can be a long-term
asset. `assetClass` independently distinguishes `reusable-knowledge` and
`evaluation-instance`. Instance evidence is retained until explicitly managed;
there is no automatic deletion or redaction.

The reusable snapshot stays three files: maintainer_skills, program_facts,
evaluation_cases. Concrete compiler/assessment results and Skill feedback are
separate construction-instance tables. Oracle code and calibration expectations
remain reusable; actual calibration output stays with construction evidence.

Each evaluation exports its own tables. Common join keys are runId, attemptId,
phaseId, requestId, contextVersionId, toolCallId and sourceAnalysisId. A file row
identifies a whole raw evidence file; no 3-KiB block references appear in analytical
tables. Raw evidence bundles retain all bytes, including cumulative adapter
snapshots. The immutable earlier chunk-based archive remains historical evidence.

```sh
cargo build --locked -p agentlab_code_analysis --bin agentlab-asset-model
target/debug/agentlab-asset-model /path/to/fixed-knowledge /path/to/new-exchange \
  https://example/instance-raw.tar.zst run-id=/path/to/captured-evidence
python examples/knowledge-seed/subject/import-assets.py \
  --development /path/to/instance-development.json \
  --directory /path/to/new-exchange/instances/run-id \
  --prefix assets/instances/run-id/ --evidence /path/to/new-import \
  --create-tables --replay-context
```

`development.json` explicitly supplies url, repo and authorizationFile; credentials
are independently authorized and are not exported. Use a separate config/repository
for knowledge maintenance. To import knowledge, select the exchange's `knowledge`
directory and knowledge destination; omit `--replay-context`. Repeat instance import
without `--create-tables` to prove unchanged rows/cut. The ingestion wrapper imports
only the evaluation instance and leaves reusable knowledge unchanged.

Context versions reference content-addressed complete messages. `context_changes`
records additions/replacements/removals. Replay updates `context_heads` by stable
logical position in an attempt/direction and records each durable Git cut in
`context_commits`; import verifies every historical cut, not only the last context.
The position is an observation slot, not a claim about private Agent message IDs.

Export a committed asset class independently:

```sh
python examples/knowledge-seed/subject/finalize.py \
  --development /path/to/instance-development.json \
  --directory /path/to/new-exchange/instances/run-id \
  --prefix assets/instances/run-id/ --root /path/to/new-export \
  --include-context-history
```

Definitions declare all actual columns with bounded explicit indexes. Select only
the instance and entities needed by a query: raw-file storage relationships no
longer consume the relation input budget. `llm_tool_calls` describes appearances
in request context; `tool_calls` aggregates adapter-observed execution and exposes
full arguments/result/errors. Controlled responses are structured wire frames in
`llm_response_events`. These authority/scope distinctions remain explicit.

[The synthetic fixture](fixture/README.md) demonstrates the same normalizer and
is imported/replayed twice on the public main knowledge Action. It is a transport/
model demo, not evidence of real Agent success, builds, SessionFS or device UI.

Historical source head/commit maps export as `source_context_heads` and
`source_context_commits`. They preserve source provenance; a new repository
replays context versions into its own heads/commits rather than treating foreign
commit IDs as local history. Repeated import reuses only that target's own maps.
