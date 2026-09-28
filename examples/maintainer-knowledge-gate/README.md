# Maintainer knowledge gate examples

[`repository-portfolio.json`](repository-portfolio.json) inventories the real
repositories already evidenced by this Release checkout and assigns each a
specific qualification role. It deliberately separates AgentLab-mined source
repositories from imported SWE-bench controls.

[`candidate-specific-migration.json`](candidate-specific-migration.json)
classifies the existing 20 `purchase-data` Rust programs and seven advancing
workflows. They remain immutable-evidence adapters during migration; they are
not the generic case architecture, and no new candidate-specific stage may be
added in their place.

[`first-four/`](first-four/) is the first formal four-repository Maintainer
Skill staging cut. It records three revision-bound instance Skills per
repository, their source evidence, repository-specific coverage limits, and a
deliberately empty case table. It is Git-portable import material, not a claim
that a persistent development MCPGit instance currently exists.

The first-four staging cut now establishes the minimum repository knowledge.
The next qualification work should proceed in this order:

1. expand whole-repository semantic coverage for `code-workshop` and migrate
   its six case families through the executable gate;
2. diversify Harmony IAP candidate mining beyond `purchase-data`, and repair
   the Cordova IAP build/test contract before either repository advances;
3. exercise the `guide-snippets` project partition against scale and
   false-positive suppression, not as a source of high-cardinality SDK-import
   cases;
4. onboard `asrelease` only after its repository boundaries and public/private
   release responsibilities have explicit maintainer Skills.

Do not copy the portfolio into mutable runtime state. TableGit remains the live
knowledge authority; this file is a Release-pinned sampling plan.
