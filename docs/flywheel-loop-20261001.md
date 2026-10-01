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
