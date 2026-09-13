# TableGit engineering knowledge development

TableGit is the current development authority. Released snapshots contain three
JSONL files, one row per line and one file per business table:

- `maintainer_skills.jsonl`: maintainer Markdown knowledge and evidence references.
- `program_facts.jsonl`: typed symbols, calls, links and archived analysis records.
- `evaluation_cases.jsonl`: typed tasks and calibration results.

Rows have stable IDs; export sorts IDs and JSON fields, adds no volatile timestamps
and retains all content. `export.json` binds the three data files to an exact
repository cut and records counts/digests. No mutable file/DB dual authority.

## Local development

Use an existing MCPGit Service repository and operator authorization file. The
Service client is the same released WebSocket adapter used by the public demo.

```sh
python3 examples/knowledge-seed/store.py import --url "$SERVICE_URL" \
  --authorization-file "$AUTH_FILE" --repo "$REPO_ID" --topic "$TOPIC_ID" \
  --directory ./seed-snapshot --create-tables
python3 examples/knowledge-seed/store.py analyze --url "$SERVICE_URL" \
  --authorization-file "$AUTH_FILE" --repo "$REPO_ID" --topic "$TOPIC_ID" \
  --revision "$KNOWLEDGE_CUT" --directory /tmp/knowledge-analysis
python3 examples/knowledge-seed/store.py export --url "$SERVICE_URL" \
  --authorization-file "$AUTH_FILE" --repo "$REPO_ID" \
  --revision "$FINAL_CUT" --directory ./seed-snapshot
```

Omit `--create-tables` for imports into established tables. Import reads committed
rows and actual row versions, then batches inserts, field updates and deletions.
Identical snapshots do not create a new commit. Direct TableGit transactions are
used for development edits; JSONL is exported only from a fixed publication cut.
Keep authorization and raw Session evidence outside the release checkout.

## Executable experiment

`knowledge-seed.yml` bootstraps a deterministic two-file Python fixture into real
AgentLab Session tables, revises stable Skill rows and proves both cuts after
storage restart. It executes read-only `table.relations.query` SQL over the
program facts, archives the request, code, input revision and complete typed result
as an analysis row, and links task records to that row. Name-matched call candidates
remain syntactic candidates, not proven runtime dispatch.

Then it exports three JSONL files, imports them to fresh tables, independently
compares rows, repeats the import with zero operations, and re-exports the original
cut byte-stably. Compiler/test failures and full source capture are retained.
`builder=mini` is an optional captured Agent builder; semantic draft correctness
is separate from submission. The current fixture is not real Harmony analysis,
qualified complex-task generation or full Workspace SessionFS capture.

The builder seed pins the two HarmonyOS_Samples repositories and vocabulary.
Next source adapters must generate actual ArkTS facts; task construction must
consume archived analysis before independently calibrating reference and wrong
implementations. Feedback revises subsequent knowledge cuts; assessment inputs
stay frozen. MCPGit remains generic infrastructure; all three schemas are AL-owned.

## Verified local TableGit development

`local.py` creates an independent real MCPGit Service using a locally installed
ARM64 image, maintains the three tables, restarts storage, archives SQL analysis
and performs export/reimport. This is TableGit development validation, separate
from the release-pinned AL Session qualification Action.

```sh
python3 -m venv /tmp/knowledge-runtime
/tmp/knowledge-runtime/bin/pip install websocket-client==1.8.0
/tmp/knowledge-runtime/bin/python examples/knowledge-seed/local.py \
  --image "$LOCAL_MCPGIT_IMAGE" --root /tmp/knowledge-development --keep
```

`--keep` retains the development containers/volume. Connection details and the
operator authorization file remain in the private local state directory. Without
it, the test removes its own infrastructure after preserving evidence. Startup
and post-restart use one route discovery/readiness function, including refreshing
dynamically allocated Docker ports. No existing AL instance is modified.

[The initial fixture snapshot](seeds/fixture/export.json) was exported from real
TableGit after archived SQL analysis, not hand-edited. It contains13 rows in three
JSONL files. This is a small Python fixture; it does not claim real Harmony tasks.

## Maintained process Skills versus runtime knowledge

[The Release Skill registry](../../skills/registry.json) separates maintenance
(goal, semantic analysis, program analysis, seed extraction and calibration)
from operations (fixed-snapshot evaluation). These are reusable process recipes.
The target codebase maintainer Skills are business rows in `maintainer_skills`;
the three JSONL files remain exported data snapshots, not copies of the process
library or a second editable authority. Assessment feedback informs a later
maintenance cut, preserving the current assessment inputs.

## First real Harmony construction round

`seeds/harmony-code-workshop/` is a three-table snapshot exported from real
TableGit namespace `flywheel/harmony-v2/`: 26 instance Skills, 123 program/analysis
facts and seven task/calibration rows. Previous namespace cuts are archived evidence;
this snapshot is the current instance authority export. Source is pinned to code-workshop commit
`7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6`. Imports are lexical paths in 19 selected
files. Two local common-package bindings are checked against package dependency
files and entry metadata; external aliases and symbol/runtime calls remain
unresolved. A SQL join archives four possible consumer/barrel/export paths,
without claiming four resolved imported-symbol calls.

Five candidates cover feedback, delayed loading, navigation, image URLs and
independent click handlers. Click-handler behavior has an isolated-method
oracle: original shared state fails independence, per-handler reference passes,
and a wrong boundary fails. It executes an explicitly type-erased original
method in Node, not an ArkTS build, emulator or full assessed-Agent run. Delayed-loading lifecycle also has an isolated original/reference/wrong-cancel
oracle with explicit scheduler/breakpoint stubs. Three other tasks remain
candidates without functional calibration. Complete results
and fixed-cut SQL dependency query/results are stored as TableGit rows.

Run a development round against a retained local service (all evidence and
credentials stay outside the checkout):

```sh
python3 examples/knowledge-seed/flywheel/run.py --source "$PINNED_SOURCE" \
  --root "$ROUND_ROOT" --development "$DEVELOPMENT_JSON"
```

Omit `--development` to construct a captured proposal for the released Session
fixture. Dispatch `knowledge-seed.yml` with `source=harmony`, `builder=mock` to
fetch the exact source, independently calibrate it, and verify released TableGit
history, analysis archive and export/import on a fresh runner. Mock identifies
the construction route; the subject Code Agent is not run by this experiment.
The existing fixture SQL is a generic call-candidate join, not Harmony import
resolution; the development round separately archives the import-path query.

Feedback improves the next knowledge cut, preserving the original cut. Keep
source, semantic knowledge, calibration and assessment identities separate.
SDK/HAP, real subject behavior and formal SessionFS Fork remain independent
acceptance steps. This round does not claim the full challenge is solved.

## Method and instance layers

Read [the methodology Skill](../../skills/agentlab-skill-methodology/SKILL.md).
Each of five scenarios has semantic, program-analysis, seed-extraction,
calibration and evaluation instance Skills, plus one challenge-goal instance.
The 26 rows carry skillLayer, role, stage, objectId, methodSkillId, exact Release
methodRevision/methodDigest, sourceRevision and evidence/case references.
Evaluation rows have role=operations; they are still instance Skills maintained
in the same business table. Release method recipes remain a separate layer.

The two method oracles independently calibrate construction demands. They do
not execute a real assessed Agent, render ArkUI or qualify HAP/SessionFS. The
first pre-v2 real Harmony Action34749535447 passed released Session history and
104-row export/import; v2 coverage requires its own fresh Action verdict.
