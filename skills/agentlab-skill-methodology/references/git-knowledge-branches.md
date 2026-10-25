# Target knowledge branches and the Release aggregation hub

Use this profile when maintaining a target's reusable Skills and public cases in
Git without changing its business branch. The user-selected hub is this SAME
agentlabrelease repository; do not create another aggregation repository.

## Authority and discovery

- Target repository: independent-root `al-knowledge`, containing target Skills,
  public task seeds/cases and small evidence references. A controlled fork can
  host it when upstream is read-only; retain the upstream URL and exact code SHA.
- Release hub: `knowledge/targets/<targetId>` is the SAME commit history under a
  different ref. Improvements may originate at either endpoint. Ordinary Git
  merges resolve concurrent edits; synchronization never force-pushes or rewrites.
- Release `knowledge/catalog`: independent-root catalog with admitted bindings
  and pinned knowledge heads. The default Release branch remains the product
  and reusable-method entry. General lessons are reviewed into method Skills,
  separately from receiving a target branch.
- The admitted `knowledge.json` is a small binding, not a capability grant.
  Fetch it from a separately pinned catalog commit, verify identity and use that
  trusted local file for synchronization. Pin the independently admitted knowledge
  root separately with `--expected-root`; keeping it outside knowledge.json avoids
  a self-referential root-commit hash. Never admit a branch's self-declaration
  as proof of the intended target or of upstream write permission.

For this Git profile, Skills, scripts and public case definitions are authored
in the knowledge history. AL/TableGit keeps structured observations, live run
state, assessments and explicit source/knowledge/method commit references. A
TableGit import of Git-authored guidance pins its commit and must not become a
second independently editable copy. Existing TableGit-authored projects remain
on their current profile until explicitly migrated. No business-table or runtime
API changes are implied by this profile.

## Layout and material limits

```text
AGENTS.md                       Target knowledge entrypoint
knowledge.json                  Sources + exact commits + endpoint/ref mapping
skills/<target-maintainer>/      Target maintenance and verification knowledge
cases/<case-id>/                 Public task/inputs/capture contracts
evidence/                      Small public references or curated observations
```

Keep SDKs, repository clones, build/cache trees, credentials, Agent homes, raw
captured sessions, and private evaluator answers outside PUBLIC branches. A Git
branch is not an access-control boundary. Retain large evidence in the existing
asset store and bind its immutable identity. The script enforces a text-only
layout, 256KiB/file and 2MiB/tree bounds; this is not automatic secret detection
or semantic approval of a case. Curate public material before publication.

## Create one independent-root target history

Use a NEW isolated worktree under the user's configured worktree root. Do not
switch an existing business checkout. With Git supporting worktree `--orphan`,
create it directly. With older Git, add a detached `--no-checkout` worktree at the
verified source commit, then `git switch --orphan al-knowledge` ONLY inside that
new empty worktree. Commit the public layout there. The first knowledge commit
has no parent and no business-code history. Merely creating another ordinary
branch at the source commit does not satisfy this profile.

Publish `al-knowledge` to the separately authorized target/fork endpoint once.
If a push times out, read that exact ref/commit before any fresh operation. A
missing response is not permission to repeat. Root identity and source code SHA
are different facts; check both and preserve the source binding in every case.

## Synchronize and independently read back

Pin this Release method commit first. Requires Git and Python3 standard library;
no Python packages, model invocation, installation or AL business HTTP is used.
Obtain the admitted binding from the pinned catalog, then use NEW receipt paths:

```bash
python3 skills/agentlab-skill-methodology/scripts/knowledge-branch.py sync \
  --binding /operator/admitted-calendar.json --expected-root KNOWLEDGE_ROOT_SHA --from target \
  --create-destination --receipt /operator/target-to-hub.json

python3 skills/agentlab-skill-methodology/scripts/knowledge-branch.py sync \
  --binding /operator/admitted-calendar.json --expected-root KNOWLEDGE_ROOT_SHA --from hub \
  --receipt /operator/hub-to-target.json

python3 skills/agentlab-skill-methodology/scripts/knowledge-branch.py verify \
  --binding /operator/admitted-calendar.json --expected-root KNOWLEDGE_ROOT_SHA --from target \
  --receipt /operator/exact-readback.json
```

`--create-destination` is only for the first known-absent destination. No
wildcards, business refs, branch aliases, automatic retry or force push are used.
A sync reads both actual refs, checks ancestry and exact binding, saves intent,
performs at most ONE ordinary push, then fetches the destination in another fresh
bare repository and reads every file. Identical heads cause zero pushes.
Divergence stops before a push; merge in the owning knowledge worktree, review,
and issue a fresh synchronization with its own receipt. A receipt recording an
unknown push effect requires exact readback, never automatic replay.

## Consume with a target without changing its code

At run enrollment freeze the code repository/commit independently from the
knowledge repository/commit and method commit. Check out the knowledge commit
in a separate directory; supply its AGENTS/selected Skills as declared maintenance
context through the existing caller's context input. Do not merge the knowledge
branch into the business branch or silently place files in the target project.
Record which documents the Agent actually received. This Git sync helper does
NOT install an AL adapter, inject context automatically, authenticate a runtime
Owner, dispatch a participant, or qualify a checkpoint/Fork.

Knowledge must not leak private checks to an assessed student. The maintenance
construction Agent may consume the public target Skills; a frozen assessment
receives only its admitted public inputs. Preserve the teacher-assistance policy,
independent grading and exact source/knowledge lineage from the existing method.

## Calendar pilot

The catalog target `openharmony-applications-calendar` binds the original
Calendar commit `a44b0ad503f69e50943520a0ea569c9cfcb09a57` and its controlled fork.
Its public restart-verification case is the existing extracted ArkUI sample,
not full Calendar acceptance. The pilot proves root separation, real bidirectional
Git transfer, retained commit IDs/bytes and unchanged business master. It does
not prove automatic next-run context consumption or multi-target generalization.
