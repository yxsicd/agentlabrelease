# Executable experiment learning

The public main knowledge Action now executes:

1. A pinned original Harmony loading lifecycle, reference cancellation and a
   wrong-cancellation variant, under an operator-owned timer/breakpoint scheduler.
2. The released AgentLab Session/TableGit fixture and normalized synthetic tool
   observation, with context history and unchanged repeat import.
3. Generic TableGit SQL over tool execution errors, preserving request/input cut
   and complete typed result in analysis_records.
4. experiment_lessons, lesson_evidence and lesson_validations import/readback,
   committed export and unchanged repeat.
5. Explicit loading lesson promotion into a separate reusable candidate,
   imported and exported from TableGit. The active published knowledge remains
   identical. Candidate exports remain sorted one file per reusable table.

Rust owns normalization, calibration invocation, lesson construction and promotion.
The existing Python bridge only orchestrates released TableGit and executes SQL;
it does not parse ArkTS or infer causes from tool errors.

```sh
cargo build --locked -p agentlab_code_analysis --bins
target/debug/agentlab-experience calibrate \
  examples/knowledge-seed/experience/fixture/DelayedLoadingView.ets \
  examples/knowledge-seed/experience/fixture/source.json \
  examples/knowledge-seed/flywheel/loading.js /path/to/new-calibration
python examples/knowledge-seed/experience/run.py \
  --development /path/to/explicit-instance-config.json \
  --instance /path/to/normalized-instance \
  --instance-prefix assets/instances/run-id/ \
  --lesson-prefix assets/experiences/run-id/ \
  --knowledge-prefix assets/promotion-candidates/run-id/ \
  --knowledge /path/to/clean-knowledge \
  --binary target/debug/agentlab-experience \
  --calibration /path/to/new-calibration --root /path/to/new-experience
```

The source fixture is the unmodified Apache-2.0 file from the recommended
code-workshop commit; source.json binds its path and SHA-256. This is executed
lifecycle code with explicit operator stubs, not a full HAP or UI run. Tool
observations in default main CI are synthetic. A tool error is retained as
observed/unknown; the explicitly calibrated lifecycle lesson may become verified.
Negative tests prove an observation or failed negative validation cannot promote.

Artifacts include analysis, RPC receipts, calibration raw output, committed lesson
cut and reusable promotion-export. Operational data stays outside source Git.
Maintain accepted reusable candidates in the knowledge TableGit repository,
export its exact committed cut and submit the three snapshots to Release. Never
use Action automation to change active knowledge without an explicit maintenance
step. Keep evidence Release references with the maintenance checkpoint.

Next real experiment: derive a staged loading task from target Skills and program
dependencies, independently calibrate actual submitted methods, assess a replaceable
Agent and compile all phases, then analyze/persist its own lessons. These additional
qualifications are not claimed by this method-calibration demo.
