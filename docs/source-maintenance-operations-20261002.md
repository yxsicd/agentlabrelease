# Source-maintenance operation contracts

Overall flywheel maturity remains 62%. This adapter is source-maintenance
verification, not a formal case, framework runtime, build, performance or Agent
evaluation. A reviewed operator contract is not authenticated reviewer identity.
No repository or path names occur in its acceptance rules.

The Rust CLI runs `--execute-source-operation` with --scope-skills,
--program-facts, --operation-receipts-root, --before, --operation-recipe,
--source-worktree and a fresh --output outside the source checkout. It independently
reproduces the strict baseline, requires the exact selected source scope to be
semantic-ready and source-only, checks clean HEAD/origin, verifies owned original
source bytes and Git Blobs, pins method files/executables and runs bounded controls.
Selection is an explicit reviewed scope, not an asserted scheduler-plan selection.
Automatic recipe production and workflow routing remain separate missing producers.

`agentlab.maintainer_source_operation_recipe.v1` contains:

- reviewed=true, automaticPromotion=false, operationKind=source-only, scopeSkillId;
- source: repositoryId, repository URL, exact revision;
- sourceInputs: one to sixteen owned relative paths with sha256 and gitBlobOid;
- methodInputs: one to eight absolute file paths with sha256;
- checks: one to 64 unique id/pointer/expected triples; pointer is a JSON pointer
  into the control's original JSON stdout and expected is a frozen JSON value;
- controls: three to eight unique safe IDs, with role baseline/reference/wrong,
  command and expectedFailedCheckIds. Exactly one baseline is required, at least
  one reference must pass every check, and at least one wrong control must fail
  declared named checks. A known-failing baseline remains explicit, not repaired
  by the operator or mistaken for an infrastructure failure.

Commands reuse the existing bounded Unix process-group executor: absolute program,
programSha256, args, contained cwd, timeoutMs at most 180000. The sum of control
deadlines is at most 600000. This is reviewed trusted execution, not a sandbox;
credentials or private Agent environment are not injected. Preserve the complete
available raw failure capture and do not rerun a successful control to manufacture
missing evidence. Original source and method bytes are retained independently.

Execution emits unqualified `agentlab.maintainer_source_operation_execution.v1`.
Use `--qualify-source-operation --execution-root ROOT
--execution-receipt-sha256 SHA --output NEW_FILE` for independent qualification.
It reads original recipe/scope/baseline, source/method copies, process captures
and stdout/stderr. It rejects missing/changed streams, reused processes, nonzero
exits, incomplete capture, missing checks or outcomes differing from the frozen
named failures. Producer pass flags have no grading role.

The portable `agentlab.maintainer_scope_source_qualification.v1` retains original
recipe/execution/scope JSON bytes and complete bounded UTF-8 stdout/stderr (at
most 256 KiB per stream and 2 MiB total). Strict assessment rechecks byte lineage
and recomputes observed failures itself. Its qualificationScope declares only
sourceMaintenance=true; build/runtime/tests/performance remain false. Raw producer
authenticity and full-scope source coverage are not proven. Source/method copies
remain in the private execution capture; the portable verifier does not reread
them or replay the target. Never strengthen this boundary during publication.

The existing --prepare-operation-fact emits source-maintenance-verification with
a distinct stable operation-source ID, and the ordinary operation round gate and
stager remain responsible for exact selected transitions and portable knowledge.
No live authority mutation follows from execution, qualification or local staging.
The five-stage business adapter accepts the same recipe through operationExecution:
reviewed=true, sourceWorktree, digest-bound before/recipe references. Build recipes
still require their original plan and moduleRoot; source recipes do not borrow HAR
qualification or claim build/test capability. Missing later inputs stop the cycle.
