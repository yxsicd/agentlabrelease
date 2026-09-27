# First-four Maintainer Skill baseline

This directory is the revision-pinned, Git-portable staging cut for the first
four source repositories. It contains exactly three instance Maintainer Skills
per repository: `repository-analysis`, `program-analysis`, and
`seed-extraction`.

| Repository | Actual boundary | Current hard fact | Mining implication |
| --- | --- | --- | --- |
| `code-workshop` | One multi-product Harmony application | 1,512 tracked files; 556 analyzed source candidates | Expand beyond the six already selected scenario families |
| `guide-snippets` | A corpus with 410 detected sample-project roots | 39,298 tracked files; 12,155 analyzed source files | Partition by sample root and suppress shared-SDK-import noise |
| `harmony-iap-client` | One small Harmony entry application | 44 tracked files, 9 ArkTS files, no tracked tests | Diversify beyond `purchaseData`; add upstream-aligned ohosTest/device Oracles |
| `hms-cordova-iap` | IAP is a 104-file subtree in a 24-plugin monorepo | TypeScript-to-Cordova-to-Java bridge; upstream package build exits 1 | Mine cross-language bridge contracts only after repairing the build/test contract |

The complete [`maintainer_skus.jsonl`](maintainer_skus.jsonl) catalog is the
maintainable-unit map, not a candidate list. Its 480 leaf SKUs partition every
tracked file exactly once:

| Repository | SKU count | Partition rule |
| --- | ---: | --- |
| `code-workshop` | 16 | shared module, seven feature modules, four product modules, build/support boundaries |
| `guide-snippets` | 416 | 410 independent sample projects plus domain/repository support boundaries |
| `harmony-iap-client` | 14 | nine ArkTS source-owner units plus application, resources, build, documentation, and repository support |
| `hms-cordova-iap` | 34 | 23 non-IAP plugin packages, nine detailed IAP layers, and repository support |

[`maintainer-sku-summary.json`](maintainer-sku-summary.json) binds the catalog
to all four Git Tree OIDs and proves that all 44,567 tracked files are assigned
with zero unassigned files. `agentlab-maintainer-sku-catalog` regenerates the
catalog deterministically from exact checkouts when a source revision changes.
Every SKU follows [`maintainer-sku.schema.json`](../../../schemas/maintainer-sku.schema.json)
and records its stable responsibility boundary, documented purpose, language
composition, source and test inventory, build/test entrypoints, external
dependency surface, and Git Blob evidence. This is the complete structural
maintainer map; deeper behavior facts and executable Oracles remain separate,
revision-bound tables rather than being guessed from paths.

The empty `evaluation_cases.jsonl` is deliberate. These rows are repository
knowledge and candidate-mining policy, not approved cases. A future candidate
must bind the exact Skills, facts, analyses, editable/context paths, and an
independent Oracle through the executable Maintainer knowledge gate.

`source-set.txt` is the canonical source identity input; its SHA-256 is the
`sourceSetSha256` in `maintainer-knowledge-cut.json`. Table hashes make the staging cut
tamper-evident. The cut does **not** claim to be a persistent MCPGit authority:
it is ready to import once the long-lived development instance is selected.

Validate it with:

```bash
cargo test -p agentlab_code_analysis --test first_four_maintainer_skills
cargo test -p agentlab_code_analysis --test maintainer_sku_catalog
```
