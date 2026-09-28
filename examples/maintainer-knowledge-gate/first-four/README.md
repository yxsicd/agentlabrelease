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
exact committed revision and opens a Release pull request containing the sorted
JSONL export. `tableGitAuthority.revision` in the cut binds that export. The pull
request remains a review boundary and `automaticPromotion` stays false.

The workflow can run one to three iterations as one bounded loop. Each
iteration consumes the assessment produced by the immediately preceding
iteration, adds exactly one previously unbound semantic fact, and must increase
both `programBoundCount` and `semanticReadyCount` by exactly one without
increasing `maintenanceReadyCount`. All iterations are staged locally first;
TableGit receives the successful batch only after every requested iteration has
passed source-Blob verification and the Rust maturity gate. Therefore a later
failed iteration cannot leave a partially published loop. The final exact
TableGit revision is exported in one review PR.

`repository=auto` is the standard unattended policy. It considers only bounded
L1 scopes whose own inventory evidence is reachable inside their declared path
boundary, then chooses the repository with the lowest normalized semantic
coverage. This prevents a large repository from monopolizing the loop and
prevents impossible generated scopes from consuming an Agent turn. Explicit
repository selection remains available for diagnosis. A loop stops without a
TableGit write on an invalid proposal, duplicate fact id, source revision or
Blob mismatch, zero/multiple-scope gain, attempted L3 promotion, or exhaustion
of reachable L1 scopes. The hard maximum of three iterations limits model cost
and the size of one atomic authority transaction.

After the exact TableGit revision has been exported, each successful bounded
knowledge loop samples at most one newly semantic-ready scope into the third
flywheel. The construction Agent receives only the selected scope Skill, its
new exact-revision semantic fact, and the pinned source checkout. A successful
proposal is retained in `case_generation_candidates.jsonl` as a
`shadow-proposal`; it is not an evaluation case. A failed or hard-gate-rejected
proposal still appends a case-generation round with its rejection reason and
feedback gaps. Shadow generation therefore measures whether better repository
knowledge can be converted into a grounded staged task and Oracle hypothesis,
without blocking the first two knowledge flywheels or granting automatic
promotion. Candidate-stage binding, independent Oracle execution, wrong-variant
calibration and freeze remain separate mandatory gates.

Retained shadow proposals now also pass through an explicit construction-
readiness plan before the system spends emulator or Oracle capacity. The plan
names every implementation and Oracle source path, runtime capability, Oracle
execution receipt and wrong-variant calibration receipt. The generic
`shadow_construction_readiness.py` evaluator binds the exact candidate and
knowledge-cut digests, rejects unbound evidence bytes, and routes the result to
either a knowledge refresh, qualification, or the construction gate. It never
promotes a candidate.

The first retained UIAbility recovery plan demonstrates the intended feedback
loop. Round 18 refreshed the stable program fact and rebound `Index.ets` plus
the existing `Ability.test.ets` into the candidate's exact editable/context
surface. Its reproducible decision is now `blocked-qualification`: the
knowledge blockers are empty, while API 22 emulator build/deploy, the
abnormal-stop recovery cycle, independent Oracle execution and at least two
wrong variants remain unqualified. The candidate is not automatically promoted.

The Rust-native `agentlab-uiability-recovery-oracle-plan` command freezes that
next gate in
[`qualification-plans/uiability-backup-restore-oracle.json`](qualification-plans/uiability-backup-restore-oracle.json).
It binds the exact candidate and construction-plan digests, the source commit,
Tree and three Git Blobs, and the evaluator-owned
[`uiability-backup-restore-reference.patch`](calibration-patches/uiability-backup-restore-reference.patch).
The reference patch is calibration material, not an Agent answer or an approved
upstream change. It extends the existing `ohosTest` lane with cold-default,
dynamic-state seeding, recovery and normal-exit negative assertions and declares
three meaningful wrong variants.

The reference positive control was calibrated on the Linux x86_64 emulator by
an external host supervisor. It launches the normal app, creates the dynamic
`Recovered Twice` state, verifies the pre-trigger launch reason is `NORMAL`,
clicks the evaluator-only recovery control that calls `appRecovery.saveAppState`
and `appRecovery.restartApp`, and then requires both the retained text and the
`APP_RECOVERY` launch reason in a fresh layout dump. The paired layout hashes,
HAP hashes, route identity and exact runtime are retained in
[`qualification-receipts/uiability-backup-restore-reference-runtime.json`](qualification-receipts/uiability-backup-restore-reference-runtime.json)
under the public runtime-receipt schema. The observed runtime is API 26 x86_64;
it proves the API-22-compatible build on that runtime, not an exact API 22 image.

Killing the bundle from inside its own `ohosTest` process remains rejected
because it can kill the Oracle itself, and the emulator shell is not assumed to
have application-process signal authority. The static plan therefore names the
calibrated trigger but still requires the separately bound runtime receipt.
Until at least two wrong variants are built and killed by the independent
Oracle, the plan remains
`reference-positive-control-calibrated-wrong-variants-required`, grants no case
contract, and keeps `automaticPromotion=false`.

The Maintainer Skill Agent Action has two explicit transaction modes. `expand`
retains the existing balanced selection of previously unbound L1 scopes and may
run one to three atomic iterations. `focused-refresh` consumes one retained
candidate plus its repository-owned construction plan, updates exactly one
existing fact, retains all prior evidence, and requires every missing
implementation/Oracle path by exact Git Blob. The independent maturity
assessment must keep all counts and the selected scope's L2 status unchanged.
The refreshed fact is committed once to TableGit and exported through a review
PR; it does not rewrite the candidate or run the emulator. A later generation
round must rebind the candidate to the new knowledge cut before qualification.

The unattended third flywheel is emulator-first. Before spending a construction
Agent turn, it rejects a newly analyzed scope whose revision-bound structural
or semantic evidence requires a serial, USB, or other attached peripheral. A
retained proposal must name a HarmonyOS emulator environment and the hard gate
rejects physical-device fallback or external-hardware requirements. This does
not suppress hardware-related repository knowledge from the first two
flywheels: such facts remain useful Maintainer Skills and their blocked shadow
attempts remain explicit feedback. Hardware-dependent cases may later use a
separate, explicitly selected real-device campaign, but they cannot enter the
default scalable emulator cohort.

TableGit authoring and Git remote publication are intentionally separate
authority lanes. The public Action needs `table.write`; it does not receive or
attempt to bypass `mcp.publish`. An authenticated operator may separately run
the same sync command with `--replicate`, which revision-fences the configured
remote push and verifies remote convergence. Mirror lag never changes which
TableGit revision is the knowledge authority or the source of a Release export.

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
