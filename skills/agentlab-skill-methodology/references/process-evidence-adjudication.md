# Process evidence and adjudication

Run `scripts/enrich-process-audit.py --private-report <canonical-private.json> --public-v3 <reviewed-v3-directory> --scanner <approved-allowlist-scanner.py> --output <new-version-directory>` offline. Output must not exist. The canonical evidence commitment and the 31-operation reviewed population must match; this script is scoped to this reviewed sample, not a generic auto-grader.

Keep native runtime status, historical stage grade, recorded failure attribution, reviewer annotations and independent whole-task verdict separate. Never silently regrade historical stages or remove environment faults from denominators. Missing attribution remains null; false capability-failure attribution is not a pass. Timeout is a budget-conditioned observation, not proof of permanent inability or successful counterfactual.

Tool return flags, command outcome and goal progress are different observations. Publish only reviewed action summaries and request/result commitments. An informative failure or state recovery may advance the task; repeated checks require requirement-level interpretation. A selected review sample cannot establish the global useful-call rate. Hashes bind bytes, not semantic truth.

Publish neither original operation/tool IDs nor private paths/raw traces. Keep explicit public run links. Integrity checks not performed remain not_audited: no inferred clean bill or misconduct. Declared teacher assistance is an evaluation condition and remains part of the student's record. Final reports are produced by the evaluation system/teacher, never a student's self-awarded score.

Use `python3 scripts/test_process_audit.py` for synthetic boundary checks, plus the real reviewed input and public scanner. Preserve immutable old versions and existing task scope. No student execution, HTTP dispatch, infrastructure changes or new permissions are implied.

## Frozen whole-task repeat, separate from exploration

Use the same existing offline projector with `--frozen-reviews <private-intake.json> --public-v4 <reviewed-v4-directory> --scanner <approved-allowlist-scanner.py> --output <new-version-directory>`. This mode requires `agentlab.frozen-review-intake.v1`, the frozen protocol and both A2/B2 attempts, including pending or failed attempts. It checks task hash, seed commit, fresh context, observed model/thinking, budget, gateway identity, help counts and exact original-operation review binding. These checks validate input consistency, not the truth of all supplied evidence. Keep the original private intake and immutable proof references outside public refs.

The mode preserves historical operations and run records and appends a separate frozen cohort. It rejects student-authored review and whole-pass promotion; qualified original publication and full independent acceptance remain distinct downstream steps. A native assistant error, controller error, WAL runtime_finished and published original fact are separate observations. Unknown publication is read back by its original operation; never rerun the request. Start a separate same-seed repeat only after fresh resource checks prove prior participant/device actions have ended; retain the previous publication unknown.

Count tool invocations separately from streaming updates. Report tool flags, underlying command/test outcomes and goal progress separately. Preserve the first failing test and the student's correction. Passing regressions for supplied code are not coverage of the new feature. Successful stop/relaunch with empty pidof is behavior evidence; do not invent missing numeric process identities or silently weaken a frozen oracle. A stale in-progress student artifact and unsupported forward/signing claims remain explicit, even when later trace evidence supports functional progress. The system/teacher owns the final assessment.

Run `python3 scripts/test_frozen_cohort.py` for new mismatch, privacy, reviewer, no-pass and immutable-population controls, then exercise the real admitted private intake through the approved scanner. n=2 is a same-condition procedural repeat, not statistical stability or a model ranking. No network/dispatch/device effects are implied by report generation.


## Same-task model campaign and qualified whole-task review

Use the same offline projector with `--model-campaign <private-intake.json>
--public-baseline <existing-version-directory> --scanner <approved-scanner.py>
--output <new-version-directory>`. The input schema is
`agentlab.model-campaign-intake.v1`. Preserve every planned model, including
running and incomplete attempts, plus the old frozen cohort and historical
population. A single attempt per model is descriptive evidence, not a ranking,
stability estimate or reason to report a population pass rate.

The projector checks actual native model/thinking/budget, exact qualified
source/recipient/base binding, original operation/request digest/checkpoint and
complete owning-fact tool coverage. A positive teacher verdict also requires
all functional, delivery and context criteria from the exact frozen oracle,
with nonempty independent proof commitments. This validates provenance and
consistency; hashes do not prove semantic truth. The teacher/system must perform
the actual acceptance. Student tests are evidence, never self-awarded grades.
Assisted passing delivery remains explicitly assisted.

Keep all-zero or missing native usage unqualified; do not report free cost or
zero reasoning from absent counters. Retain malformed tool arguments and empty
final responses with unresolved model/provider/adapter attribution. A normal
runtime end before budget expiry is not a timeout or complete delivery. Invalid
configuration trials remain retained and separate; never silently repair their
labels or retry their original operation.

Run `python3 scripts/test_model_campaign.py`, the existing frozen/process tests,
and the real admitted intake through the unchanged privacy scanner. Do not
publish private identifiers, oracle contents, raw traces or reasoning text.
