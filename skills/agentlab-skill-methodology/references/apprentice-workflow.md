# New maintainer: reproduce, extend, return evidence

Start from Release AGENTS.md and the Skill registry. Use this route when taking
over benchmark construction; operational assessment follows its own fixed inputs.

## Knowledge layers

- Method Skills in Release explain how to analyze, derive, calibrate and evaluate.
- Target-instance Skills are TableGit rows bound to an object, source cut, method
  revision/digest and facts/cases. Maintenance and operations are separate roles
  within these layers, not extra layers.
- Program facts, analysis code/results, task fixtures and outcome records stay
  structured in their respective tables. Skills explain and reference them.
- Lesson updates change a reusable method only when the evidence supports a
  general rule. Repository-specific observations change the instance rows.

## First reproducible round

1. Read the method Skills for goal, codebase analysis, program analysis, seed
   extraction and calibration from the registry, then the real Harmony example.
2. Select a fixed source and exported knowledge cut. The code-workshop example
   uses commit `7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6`; its SDK6.1 target
   differs from the challenge6.0 target. Keep this gap visible.
3. Run the same Rust contract and fixed-source extractor used in CI:

   ```sh
   cargo test --locked -p agentlab_code_analysis
   cargo run --locked -p agentlab_code_analysis -- "$PINNED_SOURCE" "$AST_OUTPUT"
   ```

4. Run the construction/calibration proposal without a service, or continue a
   development TableGit using the operator-provided connection file:

   ```sh
   python3 examples/knowledge-seed/flywheel/run.py --source "$PINNED_SOURCE" --root "$ROUND_ROOT"
   python3 examples/knowledge-seed/flywheel/run.py --source "$PINNED_SOURCE" --root "$ROUND_ROOT" --development "$DEVELOPMENT_JSON"
   ```

   Python currently orchestrates TableGit; source program extraction is Rust.
   Reuse a development round root to preserve authority and archive older rounds.
   Connection setup/import/export commands are in the knowledge example.

5. Inspect original/reference/wrong-variant outputs and the summary. A reference
   pass must accompany meaningful rejected variants. Read adapter limits before
   promoting a candidate. Image classification invokes source-verified consumer
   seams, not full ArkUI consumer bodies; method tests are not HAP acceptance.
6. Analyze committed facts through generic TableGit SQL/programming, archive the
   exact query/input cut/results and derive the next demand from those records.
7. Update instance Skills with concrete files, contract, commands, expected
   outcomes, failure interpretation, evidence IDs and one next action. Preserve
   unknowns; do not turn guesses into observed contracts.
8. Export one sorted JSONL per table from the final cut. Verify repeat export and
   unchanged re-import, then publish the snapshot with method/source lineage.

## Submit an incremental improvement

Dispatch `knowledge-seed.yml` on Release main with `source=harmony`, `builder=mock`
for the independent construction/storage route. It does not run an assessed Agent.
Inspect artifact receipts as well as the run verdict. A real subject run needs
the operations Skill, fixed demands, Harness-owned capture, stage checkpoints,
functional grading and eventual real Harmony build checks.

Every handoff leaves: exact source/method/TableGit cuts, changed Skill IDs,
analysis/oracle code and full results, failed variants, acceptance boundary,
reproduction commands and the next concrete task. Keep generated data canonical
in TableGit; do not independently edit its exported JSONLs.

## Challenge backlog

The current five candidates are feedback, delayed loading, navigation, image URL
classification and independent click throttling. Extend functional calibration
for feedback/navigation, then full consumer behavior and real build coverage for
all five. Next establish a genuine multi-round subject run and checkpoint/Fork
counterfactual comparison. Finally repeat on an independent Harmony project,
measure scoring agreement and assemble the method/report delivery.

Read [the runnable knowledge example](../../../examples/knowledge-seed/README.md)
for actual coverage and [the Skill registry](../../registry.json) for stage routing.
