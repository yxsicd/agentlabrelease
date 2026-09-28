# First-four Maintainer Skill baseline

This directory is the revision-pinned, Git-portable staging cut for the first
four source repositories. It has two complementary Maintainer Skill layers:
three process Skills per repository (`repository-analysis`, `program-analysis`,
and `seed-extraction`) plus scope-level Skills for every maintainable source
boundary.

These are all `target-operations` Skills: they maintain knowledge of test-object
repositories. The repository-native method Skills under `skills/` maintain
AgentLab itself and are a separate ownership plane.

| Repository | Actual boundary | Current hard fact | Mining implication |
| --- | --- | --- | --- |
| `code-workshop` | One multi-product Harmony application | 1,512 tracked files; 556 analyzed source candidates | Expand beyond the six already selected scenario families |
| `guide-snippets` | A corpus with 410 detected sample-project roots | 39,298 tracked files; 12,155 analyzed source files | Partition by sample root and suppress shared-SDK-import noise |
| `harmony-iap-client` | One small Harmony entry application | 44 tracked files, 9 ArkTS files, no tracked tests | Diversify beyond `purchaseData`; add upstream-aligned ohosTest/device Oracles |
| `hms-cordova-iap` | IAP is a 104-file subtree in a 24-plugin monorepo | TypeScript-to-Cordova-to-Java bridge; upstream package build exits 1 | Mine cross-language bridge contracts only after repairing the build/test contract |

The complete [`maintainer_scope_skills.jsonl`](maintainer_scope_skills.jsonl)
catalog is the maintainable-unit Skill map, not a candidate list. Its 480
scope-level Maintainer Skills partition every tracked file exactly once:

| Repository | Scope Skill count | Partition rule |
| --- | ---: | --- |
| `code-workshop` | 16 | shared module, seven feature modules, four product modules, build/support boundaries |
| `guide-snippets` | 416 | 410 independent sample projects plus domain/repository support boundaries |
| `harmony-iap-client` | 14 | nine ArkTS source-owner units plus application, resources, build, documentation, and repository support |
| `hms-cordova-iap` | 34 | 23 non-IAP plugin packages, nine detailed IAP layers, and repository support |

[`maintainer-skill-summary.json`](maintainer-skill-summary.json) binds the catalog
to all four Git Tree OIDs and proves that all 44,567 tracked files are assigned
with zero unassigned files. `agentlab-maintainer-skill-catalog` regenerates the
catalog deterministically from exact checkouts when a source revision changes.
Every scope-level Maintainer Skill follows
[`maintainer-scope-skill.schema.json`](../../../schemas/maintainer-scope-skill.schema.json)
and records its stable responsibility boundary, documented purpose, language
composition, source and test inventory, build/test entrypoints, external
dependency surface, and Git Blob evidence. This is the complete structural
maintainer map; deeper behavior facts and executable Oracles remain separate,
revision-bound tables rather than being guessed from paths.

[`maintainer_skill_refresh_rounds.jsonl`](maintainer_skill_refresh_rounds.jsonl)
records the iterative lineage. Round 1 established the structural baseline;
round 2 separated repository-native and target-operations ownership and bound
the refreshed tables; round 3 bound all four seed-extraction Skills to the
iterative generation method; round 4 ran the repository-independent evidence
flywheel and bound existing analysis to exact scope Skills. Its decision
remains `continue`: later rounds must deepen behavior contracts, program
relations, and executable operation evidence rather than treating the first
code read as final. Round 5 consumed that gap queue selectively: evidence was
promoted only when it was exact-revision, scope-bound, and honest about its
limits.

The retained reports under [`assessments/`](assessments/) are the first four
real flywheel passes over all four repositories:

| Pass | Structural ready | Program bound | Semantic ready | Maintenance ready |
| --- | ---: | ---: | ---: | ---: |
| Structural catalog only | 480 | 0 | 0 | 0 |
| Existing 20 program/analysis facts | 480 | 10 | 0 | 0 |
| Explicit universal dimensions and scope bindings | 480 | 11 | 4 | 0 |
| Targeted semantic and executable operation evidence | 480 | 13 | 6 | 2 |

The guide `ArkWeb/SetBasicAttrsEvts` sample and the Harmony IAP consumable page
are now L3 maintenance-ready. Both have complete bounded semantic dimensions
and executable emulator evidence, but neither is automatically an approved
evaluation case: independent Oracle review and case promotion remain separate
gates. The code-workshop `features/devpractices` scope is newly L2 based on
cache/image contracts; the Cordova IAP Ionic, TypeScript and Java bridge layers
remain L2 because their build/runtime contract is still unresolved. The latest
gap queue retains 467 unbound scopes and drives the next targeted round.

[`case_generation_rounds.jsonl`](case_generation_rounds.jsonl) starts the
separate downstream generation lineage. Round 1 is intentionally an honest
readiness baseline: the structural catalog is complete, but behavior-ready and
Oracle-ready classifications have not yet been completed and no candidate was
silently promoted. Its `continue` decision carries the exact gaps into the next
cohort. This table is downstream of the immutable knowledge cut, so each row
binds the cut digest; it is not included inside that cut and cannot create a
hash cycle.

The empty `evaluation_cases.jsonl` is deliberate. These rows are repository
knowledge and candidate-mining policy, not approved cases. A future candidate
must bind the exact Skills, facts, analyses, editable/context paths, and an
independent Oracle through the executable Maintainer knowledge gate.

`source-set.txt` is the canonical source identity input; its SHA-256 is the
`sourceSetSha256` in `maintainer-knowledge-cut.json`. Table hashes make the
staging cut tamper-evident.

The long-lived `agentlabtablegit` TableGit repository is the editable authority.
The Maintainer Skill Agent workflow first passes the proposal through the Rust
hard gate, then inserts the complete business documents through revision-fenced,
idempotent TableGit transactions. It reads every table back from the resulting
exact committed revision, verifies the configured GitHub mirror reached the
same repository revision, and opens a Release pull request containing the
sorted JSONL export. `tableGitAuthority.revision` in the cut binds that export.
The pull request remains a review boundary and `automaticPromotion` stays false.

Tables use a typed `id`/routing/digest envelope around the complete business
document. The envelope keeps the immutable TableGit definition stable while
new schema versions add fields; export verifies the payload digest and unwraps
the original document without loss. A later workflow run fails closed if live
Maintainer rows are absent from or conflict with its staged Release cut, so an
unreviewed earlier run cannot be overwritten by a stale `main` checkout.

Validate it with:

```bash
cargo test -p agentlab_code_analysis --test first_four_maintainer_skills
cargo test -p agentlab_code_analysis --test maintainer_skill_catalog
```
