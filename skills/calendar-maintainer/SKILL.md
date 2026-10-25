---
name: calendar-maintainer
description: Understand and maintain the pinned OpenHarmony Calendar recurrence boundary, derive public task seeds, and verify its extracted ArkUI sample without confusing sample results with full Calendar acceptance.
---

# Calendar recurrence maintenance

Read [source contracts](references/recurrence-contract.md) before modifying or
extracting the recurrence logic. The source authority is knowledge.json, not a
moving branch or this Skill's prose. Bind a later code revision explicitly before
reusing these findings after source changes.

Trace an intended change to the actual parser and its callers/tests. Preserve
original bodies when extracting a sample; label adapter corrections separately.
Keep parse semantics, ArkTS compilation, device UI behavior and evidence delivery
as separate acceptance claims. A matching source SHA or successful build is not
proof that a process restart restored state.

Use [the public persistence task](../../cases/calendar-restart/task.md) to extend
the existing sample. It is an end-to-end demand, not a calibrated difficulty score
or a self-contained installation package. Let a student plan its execution; retain
failed/partial attempts, help content/types and later independently observed
passage. Private evaluator assets remain outside this knowledge history.

For UI validation inspect current hierarchy/bounds, verify input -> intended
action -> displayed result, and compare actual process identity across restart.
A correct parser output from an offline reproduction does not establish a real
UI click or restored draft. Follow the separately pinned Release method for
teacher help and system-owned evaluation.

For actual UI command failures or stale summaries, use
[tool feedback and evidence delivery](references/tool-feedback.md). These scoped
lessons are maintained on this same Git history and may be revised by evidence.
