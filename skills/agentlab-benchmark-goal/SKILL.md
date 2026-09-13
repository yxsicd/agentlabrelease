---
name: agentlab-benchmark-goal
description: Translate a benchmark challenge into maintained objectives and measurable acceptance criteria.
metadata:
  agentlab-layer: method
  agentlab-role: maintenance
  agentlab-stage: goal
---

# Benchmark goal maintenance

Convert the supplied challenge into objectives, acceptance evidence and a capability-gap list. Keep this goal separate from any particular Agent implementation or benchmark corpus.

For the Harmony challenge, preserve these requirements:
- Automatically identify dependent functions/modules and cross-file complex tasks in a Harmony project of at least 20k code lines; identify at least five candidate scenarios.
- Provide the construction method and runnable code, plus an automated multi-turn evaluation workflow.
- Measure per-turn behavior, dependency/deviation between turns and the effect of key decisions on final results.
- Report task success, compilation success, interaction rounds, elapsed time and evidence-backed process scores; include subjective and objective consistency checks.

The two recommended source repositories are input corpora, not two ready-made tasks. Bind source commits and actual project/SDK boundaries. Counting the entire guide collection does not prove one qualifying 20k-line project. Current code-workshop source requires 6.1 SDK; record that difference from the challenge's 6.0 rather than silently changing the target.

Maintain goal criteria and repository-specific guidance as stable `maintainer_skills` rows. Put measured inventory, analysis code/results and gap observations in `program_facts`; put candidate tasks and calibration in `evaluation_cases`. Label proposed, source-supported and experimentally calibrated claims separately.

Follow the codebase-analysis, program-analysis, seed-extraction and benchmark-calibration routes in [the registry](../registry.json). Their outputs support this goal; fixture CI success alone does not satisfy it.

Produce target-instance guidance for this stage as TableGit Skill rows,
separate from the structured facts/tasks/results. Follow
[the two-layer methodology](../agentlab-skill-methodology/SKILL.md) for
method/source lineage and independent layer/role fields.
