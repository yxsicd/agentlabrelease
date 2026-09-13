---
name: agentlab-benchmark-calibration
description: Independently calibrate task seeds and maintain grading quality before operational evaluation.
metadata:
  agentlab-layer: method
  agentlab-role: maintenance
  agentlab-stage: calibration
---

# Benchmark calibration maintenance

Validate the benchmark independently from the assessed Agent. Check source/environment reproducibility, baseline behavior, a reference implementation, meaningful wrong implementations and regressions across turns. Successful compilation alone is not functional correctness.

Use the task's actual expected baseline: a bug-fix case may fail before the patch; an extension case may pass old tests but fail new demand checks. Reference passes and targeted wrong-boundary/lost-history variants should fail the intended checks. Save complete output and exact identities in `evaluation_cases` calibration rows, with analysis evidence in `program_facts`.

Define metric denominators and event sources: task success, build success, user rounds versus model/tool turns, monotonic execution time, and evidence-backed behavior scoring. Keep proposed process metrics explicitly unvalidated until agreement and repeatability are measured. Separate Harness malfunction from valid Agent inability.

Use [the knowledge experiment](../../examples/knowledge-seed/README.md) as the runnable fixture calibration/SQL/history/import demo; [SWE](../../examples/swe-bench/README.md) and [Harmony](../../examples/harmony-build/README.md) provide existing campaign examples. Record each demo's actual coverage.

Publish calibrated seeds from a fixed TableGit cut, one deterministically ordered JSONL per table. Do not alter active assessment inputs after seeing a subject outcome. Operational results become feedback for a new maintenance cut.

For shared predicates, specify expected input labels independently of the
reference implementation and test a stale consumer variant. Verify real source
call sites, while recording whether whole consumer bodies actually execute.
An isolated seam test can expose inconsistent routing but does not qualify the
platform URL parser, UI lifecycle or build. Keep these boundaries in the target
calibration/evaluation Skills; the image URL oracle is a concrete example.

Produce target-instance guidance for this stage as TableGit Skill rows,
separate from the structured facts/tasks/results. Follow
[the two-layer methodology](../agentlab-skill-methodology/SKILL.md) for
method/source lineage and independent layer/role fields.
