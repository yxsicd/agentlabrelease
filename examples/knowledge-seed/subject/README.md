# Actual multi-round navigation assessment

The main-only `harmony-navigation-subject.yml` Action uses published AgentLab
SDK/build-kit, Pi 0.73.1 and glm-5.3-flash through the operator-owned gateway proxy.
The participant runtime is outside Workspace and its container mounts only
Workspace, read-only runtime/models and its private native-session directory.
Supervisor evidence, reference implementation, oracle and external credentials
remain outside participant mounts. Native Pi events are adapter observations;
gateway wire bytes and observed source outcomes are supervisor captures.

The frozen TableGit task `case-navigation-subject-v1` extends navigation's existing
seed with a named boolean caller outcome. The independent oracle executes actual
PageContext methods and actual aboutToAppear body using TypeScript transpilation
and an explicit modeled NavPathStack. No reference transform is applied. Original
must fail, reference pass and push-for-replace fail before subject dispatch.
ArkUI rendering and native stack behavior remain unqualified.

Parent receives two demands; a fresh participant receives demand two from the
same observed first-turn source. Four exact selected-source files define this
source-only cut. This comparison does not claim full Workspace/SessionFS snapshots
or formal Harness Fork. Each branch compiles the full phone project offline after
SDK OHPM setup. All successful HAPs publish to independent experiment Releases;
failed/partial events, gateway requests/responses, full build logs and source cuts
are retained. A passing collection job can contain a valid failed Agent outcome;
inspect subjectTaskSucceeded rather than equating infrastructure and task success.

Maintain method Skills in Release, derived instance Skills/facts/cases in live
TableGit, then export one stable JSONL per table. Failed Agent results become
analysis and next-instance guidance; they never trigger supervisor reference
fixes inside the assessed Workspace.

Tracked source deltas are captured against the original PIN, independently of
participant Git commits. Workspace Git objects must be self-contained after
container isolation; do not use alternates pointing outside the mounts.
`ingest.py` stores individual checks, stack calls, stages, gateway/message/tool
indices in `runtime_observations`, and byte-exact content-addressed bytes in
`runtime_payload_chunks`, under this construction fixture namespace. Each
instance stage receives evidence-linked evaluationGuidance after a completed run.

The initial seed remains exactly three stable-order files: `maintainer_skills`,
`program_facts`, `evaluation_cases`. It contains reusable knowledge, task
definitions and compact findings with explicit runtime table/cut/row/archive
references. Full assessment history is a separate TableGit runtime export,
published as an experiment Release asset. It is not silently imported as initial
knowledge. These fixture schemas are owned by AgentLab, not MCPGit.

Use `ingest.py --create-runtime-tables` once for a new construction fixture, then
without that flag for subsequent runs. Every captured file is independently
reconstructed from ordered part rows and payload chunks. `finalize.py` reads back
the full runtime export before relocating duplicate legacy seed rows; historical
cuts and runtime bytes remain available. Export rows in stable key order.

To restore the full runtime evidence (rather than the initial knowledge seed):

```sh
python subject/import-runtime.py --development /path/to/development.json \
  --directory /path/to/extracted/runtime --prefix replay/navigation/ \
  --evidence /path/to/import-evidence --create-tables
```

Run from `examples/knowledge-seed`. On an unchanged repeat, omit
`--create-tables`; no rows or committed revision should change. The runtime
archive manifest includes exact table definitions and SHA-256 for each sorted
JSONL. This construction-fixture export is distinct from the installed Harness
Session table schema.

The first two real successful runs and complete TableGit runtime export are
available in [the experiment Release](https://github.com/yxsicd/agentlabrelease/releases/tag/evidence-navigation-subject-34755514333).
Its `navigation-tablegit-runtime-20260913.tar.zst` contains both runtime tables
and their versioned export manifest; HAPs are separate assets.

## Feedback instance

Dispatch the subject Action with `scenario: feedback` (or pass `--scenario feedback`
to the same local runner). `case-feedback-subject-v1` freezes two staged demands:
first preserve state through failure, expose pending/error state and allow retry;
then suppress duplicate requests while pending. The actual submit/reset methods
execute against an explicitly controlled Promise seam for the existing demonstration
SubmitInfoUtil. This does not create or advertise a real feedback backend.

Rust `agentlab-source-probe` reads exact observed source bytes and emits ArkTS
property facts, including owner, decorators, type and initializer. The oracle
checks actual reactive declarations rather than trusting fixture-assigned values.
Build it with `cargo build --locked -p agentlab_code_analysis --bin agentlab-source-probe`
and set `AGENTLAB_SOURCE_PROBE` to the binary, outside participant Workspace.
Invalid/deleted submitted source is a failed Agent outcome with evidence.

Baseline, reference, wrong-reset, wrong-duplicate and wrong-initializer are calibrated
before dispatch. Duplicate-only failure is intentionally accepted in stage one and
rejected in stage two. Freeze oracle digest and named stage checks in TableGit.
Existing frozen cases and instance guidance are not rewritten by seed creation.
Raw AST output remains recoverable; normalized observed syntax facts link to
the exact source analysis receipt and file cut in runtime tables.

## Completed feedback experiment

[Action 34758919730](https://github.com/yxsicd/agentlabrelease/actions/runs/34758919730)
ran Pi 0.73.1 with glm-5.3-flash against the frozen feedback case: 14 first-turn,
15 parent second-turn and 15 fresh-Agent second-turn checks passed, with three
full phone HAP builds. All 26 controlled gateway requests returned HTTP 200;
32 completed native tools include two reported errors, retained in the raw evidence.
The published HAP asset size and SHA-256 were independently verified. This covers
submitted methods, reactive declarations, controlled Promise outcomes and a
selected-source branch comparison. Formal SessionFS restore, device UI and strict
HarmonyOS 6.0 remain outside this experiment's demonstrated scope.

Runtime JSONL framing uses LF bytes; Unicode separators inside strings are data.
Gateway phase indices link supervisor lifecycle intervals and request receipts.
Historical re-ingestion adds analysis coverage without regressing latest guidance.

The complete [navigation + feedback runtime snapshot](https://github.com/yxsicd/agentlabrelease/releases/download/evidence-feedback-subject-34758919730/harmony-flywheel-runtime-20260913-feedback.tar.zst)
contains export.json with table definitions, committed revision, row counts and
SHA-256, plus one stable-order JSONL per runtime table. Extract it and use
`import-runtime.py` with an explicit new table prefix. The separate three initial
knowledge JSONLs remain the fast campaign bootstrap. Do not interpret this
construction-fixture namespace as the installed Harness canonical session schema.

The historical fresh feedback branch encountered missing Git in the slim Node
image; a second error came from its own Git-index parsing script. Both remain
in that run's native evidence. Future assessments build a Node + Git participant
image with the shared `participant-runtime.sh`; a main Action smoke job records
image identity and verifies Node/Git with networking disabled. This environment
repair does not retroactively change the historical run's participant image.
