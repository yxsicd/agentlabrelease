# Bounded flywheel checkpoint — 2026-10-01

Overall maturity: **46%**, an engineering estimate, not a calibrated metric or
proof of whole-repository semantic coverage. Previous estimate: 45%.

## Integrated method and real execution

- PR110 merged as `951268c5e79b043f1fec6861ec240e7be5a3124b`.
- PR111 refreshed the live input and its publication-relative receipt closure;
  merged as `39775bb5ab0cb818007a47587ce5d82e6484b49a` after seven CI checks.
- [Action 36857619983](https://github.com/yxsicd/agentlabrelease/actions/runs/36857619983)
  ran two bounded real Agent rounds on that main revision using the existing
  gateway secret in place. Neither credentials nor captured sessions are
  published in this repository.

Both rounds used generic strict gap selection, exact pinned source evidence,
independent Rust semantic-round comparison and inherited operation receipts.
Round two consumed round one's staged knowledge and assessment; no retry,
timeout or tool-call budget excess was observed.

| Round | Selected scope | Semantic ready | Program bound | Maintenance ready |
| --- | --- | --- | --- | --- |
| 1 | guide-snippets / AbilityStage | 39 → 40 | 44 → 45 | 1 → 1 |
| 2 | guide-snippets / ApplicationContextDemo | 40 → 41 | 45 → 46 | 1 → 1 |

Pinned guide-snippets source: `71bbb3916625c8d9a370b7a1989b3a7f82090525`.
The accepted facts describe environment callback binding and the
ApplicationContext demo scope contract, respectively. These are semantic
knowledge improvements, not new executable benchmark qualifications.

## Authority and publication continuity

Live TableGit revision `0bd73efc7def1c4fb05e8c1544465cbfe9d6be95` was read back
through read-only formal MCP operations, with a final HEAD check. Counts:
12 process skills, 489 scope skills, 60 program facts, 36 refresh rounds and
zero evaluation cases. Remote replication was neither requested nor proved.

The Action's raw export PR112 is diagnostic evidence, **not an integration
candidate as-is**. Its exporter changed Unicode encoding and ordering:

- Original assessed facts SHA256:
  `b9e5309031e4e2a2758d66f283f58476d495d5f9d9982e8d9983f186c814843b`.
- Canonical raw export SHA256:
  `f4ada520e2d3531a6d002035db5c8b7025734e3d2a34aeccb256951bf91195b8`.

Decoded values are equal, but strict next-round assessment identity requires
original bytes. Recovery used the original verified stage, checked all five
live table payloads and restored bound scope/fact bytes without authority
writes, report rewriting or a new baseline. The latest report reproduced
byte-identically as
`d16d28a6393627ddb9e8b6fc3eb5d22181e9f54fa24e20d043bfe60d8b60c783`.
The restored export also passed strict next-round planning and exact semantic
batch preparation; that next batch was not executed in this checkpoint.

Refresh records bind canonical ID-sorted table values. Assessments bind raw
input bytes. Regression validates both separately, including stale/changed
inputs and unsorted Unicode-escaped historical input.

## SkillsGit materialization

Using the same restored cut and SkillsGit revision
`4e691f4f76727d83d6ac37fae663abf3f9999f90`, two private derivative trees passed
`validate-mst.sh`: 11 generated guide-snippets scope skills and 25 generated
code-workshop scope skills. No target repository was modified or promoted.

The generic adapter now consumes durable assessment references, exact input
hashes, source-matched accepted semantic bindings and capability-specific
dimensions. It ignores orphan reports and unassessed stale facts. Structural
facts cannot fill missing semantic dimensions; configuration scopes do not
invent behavioral requirements. SkillsGit structural validity is not runtime
qualification or independent proof that every maintenance contract is correct.

## Boundaries and next loop

The Action retained one AbilityStage shadow proposal without automatic
promotion. Its lineage belongs to the original raw Action knowledge cut; it
has not been silently rebound to this recovered cut. No candidate execution,
oracle discrimination, new maintenance operation, performance or thermal
qualification was completed by these two semantic rounds. Historical runtime
evidence remains separate and must not be mistaken for this new candidate.

Next: review/integrate the continuity fix; use the exact restored cut for
bounded execution; advance maintenance-operation evidence and independently
qualified candidate execution rather than only accumulating semantic facts.
No release tag or channel was published.

Validation: full `agentlab_code_analysis` suite; focused first-four publication
and materialization Rust regression; 47 writer/Agent-loop Python tests and
four existing materializer tests; release validation and diff whitespace check.

## Operation feedback continuation

Overall maturity estimate: **47%** (previous checkpoint 46%). This increment
reflects actual operation-evidence persistence and verified portable continuation,
not a new runtime verdict or a count-based measure of repository completeness.

The reviewed recorded-capture receipt for
`skill-scope-code-workshop-common-module-contract` was revalidated against the
latest two-round knowledge cut. Its original qualification bytes retain SHA256
`027868459b1691fcceccc1cf70ab69e847cb0c68b130f2073f979d0b638d1b7d`.
The current operation round gate proves only that selected scope advances L2 to
L3; all unselected states, the source catalog and semantic knowledge remain
unchanged. Program-bound count stays 46 and semantic-ready count stays 41;
maintenance-ready count advances 1 to 2. This is reuse and feedback of existing
build capture, **not a fresh build or emulator run in this continuation**.

A live five-table admission checked the previous authority
`0bd73efc7def1c4fb05e8c1544465cbfe9d6be95`. A single revision-fenced transaction
inserted exactly one operation fact and one refresh record, with no deletes or
updates to existing rows. New authority:
`4e8868dd7418b13a58cc335b35e5652117e88652`. Exact export and final HEAD readback
succeeded. Repeat import returned that same revision without another commit.
Replication and release publication were not requested.

Durable refresh index 37 references assessment index 35, whose original SHA256 is
`3a0fe3380583525df6d2734c09722a6954727cacea11b7e23e6c4e1e7694d96e`.
Independent assessment from the published portable cut reproduced those bytes
exactly. Both the all-capability gap plan and the semantic-only exact next batch
were prepared successfully; neither proves fresh downstream execution.
The cut now has 61 facts, 37 refresh records and zero evaluation cases.
Public admission and sync receipts are retained under the cut's
`qualification-receipts/common-capture-feedback-{admission,sync}.json`.

This feedback exposed a generic publication defect: new operation facts used a
relative receipt path without declaring its root. The Rust producer now emits
`evidence[].root: operation-receipts`, and the publication gate resolves only
that explicit root against the portable receipt directory, requires equality
with `operationEvidence`, and rejects unknown/escaping roots. Historical
unlabeled references keep their original Release-relative semantics; no file is
copied to an arbitrary repository root to bypass the check. An arbitrary-source
Rust regression verifies the newly produced root and exact path/digest binding.

The method correction is committed as
`094449f` on `work/flywheel-operation-feedback-20261001`, stacked on PR113.
PR113's older authority cut is no longer the latest input for real Agent
dispatch; integrate both reviewed checkpoints before using main-only dispatch.
No captured sessions, raw build archives or credentials enter this export.

Validation: full Rust code-analysis suite after the method correction; focused
publication regression after the new export; byte-identical portable assessment,
strict next-batch preparation, release validation and whitespace checks.
The generic five-ring goal is still incomplete: this operation round qualifies
recorded build content only, not tests, runtime, type checking, performance,
thermal behavior, a calibrated executable candidate or Agent discrimination.

## Oracle failure-control continuation

Overall maturity estimate remains **47%**. This iteration improves generic
false-positive detection, but adds no qualified executable case or runtime run.

The retained Action candidate proposed reusing an existing startup test. An
independent diagnostic executed that original pinned test body with controlled
TestKit startup success and failure, using type erasure only. Both controls
were accepted: the test calls `done()` in both branches without an assertion.
This invalidates using that test's completion as proof of startup, not the
separate untested hilog Oracle hypothesis. The compact probe and original-cut
finding are retained under `first-four/qualification-receipts/abilitystage-*`.
The historical candidate and its knowledge cut were not rebound or rewritten;
no TableGit authority was changed.

The generic trusted-source adapter reads an exact Git Blob, pins its compiler,
preserves partial infrastructure failures and refuses receipt overwrite. A Rust
integration regression uses an arbitrary fixture repository to check vacuous,
sensitive, unsupported and ambiguous tests. These are adapter controls, not
meaningful wrong-implementation calibration on a Harmony emulator. VM/process
deadlines are not a security sandbox. Every diagnostic has `qualified=false`.

The constructor prompt and calibration method now require inspecting actual
assertions/error branches, exposing missing admitted Oracle source, and keeping
cosmetic refactors separate from semantic defects. This is reusable across
repositories; no repository-specific repair enters the generic method.

Next: admit the missing Oracle-source evidence into a new knowledge round,
construct an independently checkable demand, and calibrate accepted/wrong
implementations on the exact required runtime. PR113/114 remain unmerged; no
main-only Agent dispatch or Release publication was performed in this iteration.

Validation: full `agentlab_code_analysis` suite, both new failure-control Rust
tests, 11 shadow-construction Python tests, exact original candidate/cut digest
readback, release checksum validation, Rust formatting and diff whitespace.

## Focused feedback validation continuation

Overall maturity stays **47%**. PR115's ten applicable CI jobs passed; the
immutable component publication job was skipped, not a Release publication.

The next feedback path had two real contract defects: focused-refresh requests
omitted `requiredDimensions`, and the shared proposal validator required exactly
three evidence Blobs even though focused refresh must retain old paths and add
missing Oracle paths. A mocked validation test hid this incompatibility.
The focused path now passes the preserved dimensions and requires exactly the
old-plus-required path union, independently verifying every Blob. It also rejects
a baseline fact changed after request preparation. Ordinary expansion retains
its three-Blob rule. The wrapper selects the latest durable assessment and
supplies portable operation receipts during reassessment.

A new Rust integration test invokes the actual Python CLIs against an arbitrary
Git fixture. It accepts the five-path focused union and rejects omitted
dimensions, extra/missing paths, wrong Blobs and stale baselines; ordinary
expansion still rejects five and accepts three. No validator is mocked.

Actual pinned source review then prepared the original AbilityStage candidate's
missing-test-source request in a private staging projection. Full validation
accepted a four-Blob proposed fact, preserving all three old evidence paths and
adding the exact startup-test Blob. Independent reassessment remained byte-bound
to the prior assessment and retained all totals: 46 program-bound, 41 semantic,
2 maintenance-ready out of 489 scopes. This was operator-reviewed source
knowledge, not a new Agent round or behavior qualification. The original
candidate digest and original knowledge-cut binding remain untouched; no
TableGit write or main dispatch occurred. Compact receipts preserve the result
for later explicit admission, without exporting the private staging projection.

Validation: full Rust code-analysis suite, both unmocked/retained-evidence focused
Rust regressions, 55 focused/Agent/shadow Python tests, release checksum validation,
shell syntax, Rust formatting and diff whitespace checks. Runtime, active authority
admission and a new Secret-backed Agent loop remain unqualified.
