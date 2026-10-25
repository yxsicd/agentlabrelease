# Process evidence and adjudication

Run `scripts/enrich-process-audit.py --private-report <canonical-private.json> --public-v3 <reviewed-v3-directory> --scanner <approved-allowlist-scanner.py> --output <new-version-directory>` offline. Output must not exist. The canonical evidence commitment and the 31-operation reviewed population must match; this script is scoped to this reviewed sample, not a generic auto-grader.

Keep native runtime status, historical stage grade, recorded failure attribution, reviewer annotations and independent whole-task verdict separate. Never silently regrade historical stages or remove environment faults from denominators. Missing attribution remains null; false capability-failure attribution is not a pass. Timeout is a budget-conditioned observation, not proof of permanent inability or successful counterfactual.

Tool return flags, command outcome and goal progress are different observations. Publish only reviewed action summaries and request/result commitments. An informative failure or state recovery may advance the task; repeated checks require requirement-level interpretation. A selected review sample cannot establish the global useful-call rate. Hashes bind bytes, not semantic truth.

Publish neither original operation/tool IDs nor private paths/raw traces. Keep explicit public run links. Integrity checks not performed remain not_audited: no inferred clean bill or misconduct. Declared teacher assistance is an evaluation condition and remains part of the student's record. Final reports are produced by the evaluation system/teacher, never a student's self-awarded score.

Use `python3 scripts/test_process_audit.py` for synthetic boundary checks, plus the real reviewed input and public scanner. Preserve immutable old versions and existing task scope. No student execution, HTTP dispatch, infrastructure changes or new permissions are implied.
