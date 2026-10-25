# Difficulty evidence and comparable Agent runs

Maintain this method while USING AgentLab. Keep platform implementation separate.
The unit of formal comparison is a frozen task attempt; exploration turns, Fork
points, tool events and reviewed difficulties have different denominators.
Teacher-assisted task exploration also assesses its student: assistance is part
of the assessment, even when provided to reach a later difficulty. A final hosted
task can run as one continuous task without exposing exploration stages.

## Difficulty review contract

Use stable item IDs and a versioned reviewer record, bound to the exact report
input commitment. Each observed item links numbered original executions and
separates observed facts, demonstrated strengths, barriers, interpretation and
alternative explanations. Exposure/reached and handling/outcome are separate:

- local_autonomy: a bounded behavior was performed autonomously in the observed
  phase. Inherited assistance still applies; never upgrade this to whole-task pass.
- assisted_progress: help/context preceded observed progress. Preserve recipient
  bindings and added budget/context; temporal order is not causal proof.
- unfinished: the specific independent closure remains unestablished. Timeouts,
  Harness faults and scope changes limit explanations; do not infer global inability.
- not_assessed: the current slice lacks a qualifying measurement. Bind its scope
  to an explicit dimension/contract; missing evidence is not model failure.

These are qualitative review states, not preset numeric scores. A count of seven
reviewed items is neither seven tasks nor a student pass-rate denominator. Keep
score weights in a separate versioned policy and retain the original facts.
Preserve original task outcomes, including legacy failed-stage labels that may
include upstream errors; interpretation must not silently rewrite grades.

## Assistance ledger

Retain one row per event, with multi-valued original types, public summary, exact
recipient-run links where available, and null weights until a scoring policy is
frozen. A scope/restoration notice is not automatically equivalent to a solution
hint. Missing types or exact delivery links remain explicit. Do not interpret an
empty list of bound help events as zero assistance or publish raw prompts/paths.
The public H-number is a report-local reference, not a native operation identity.

## Comparable run inputs

Export run records separately from presentation: task identity, stage, original
model declaration/label, native status, stage outcome, duration, tool coverage,
help binding coverage and input provenance. Missing model IDs remain null even
when a display label exists. Freeze these inputs before a formal comparison:

- task definition and initial state revisions;
- Agent build, model version, thinking policy;
- budget/stop conditions and tool/SDK/device environment;
- independent oracle revision and assistance/inherited-context audit;
- repeat-group identity and run selection rule (all, best, or otherwise).

`readiness()` checks reporting metadata only. It does not authenticate inputs,
permit dispatch, validate an oracle or grade a student. A fully populated metadata
object cannot convert an exploration continuation into an independent task or
remove inherited assistance. The caller still needs qualified original evidence
and separate actual execution admission. Do not populate frozen fields from a
name, retrospective prose or an unevidenced intent.

## Maintained current adapter

`scripts/build-difficulty-report.py` extends the current Calendar v2 public report
using the matching private report and versioned reviewed item JSON. It uses an
explicit allowlist, verifies input commitment and evidence/help references,
preserves legacy nulls and exports static HTML, public JSON, run JSONL and reviewed
item JSON. It is a current-cut adapter; it does not dispatch, install or regrade.
Run `python3 scripts/test_difficulty_report.py` for the nine metadata/evidence
boundary controls. Test fixtures are synthetic and never actual execution proof.

Preserve old report versions. Browser acceptance includes a populated difficulty
filter, unmeasured subset, reset, and help-event→recipient-run navigation. Scope
filters explicitly: the ledger/card filter must not silently alter campaign-wide
metrics. Source checks and browser observations are separate qualifications.

## Benchmark methodology mapping

Use Terminal-Bench for model/Agent/resource disclosure, OSWorld for reached
long-horizon difficulties, TheAgentCompany for checkpoint versus full completion,
tau-bench for repeat reliability, WebArena for environment-state validation,
GAIA for difficulty and run-selection disclosure, and SWE-bench for code regression
checks. HAL provides cross-benchmark cost/trace considerations, but published
leaderboards still require denominator, caching and deduplication checks. Do not
copy other benchmarks' scores or treat this representative selection as a measured
popularity ranking. Each target keeps its own task and oracle contracts.
