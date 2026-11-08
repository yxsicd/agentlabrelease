---
name: agentlab-benchmark-operations
description: Run fixed published task seeds through AgentLab and retain complete operational evaluation evidence.
metadata:
  agentlab-layer: method
  agentlab-role: operations
  agentlab-stage: evaluation
---

# Benchmark operations

Consume a fixed Release composition, Skill-library version and three-table snapshot receipt. Import the snapshot into the evaluation repository using [the existing import command](../../examples/knowledge-seed/README.md). Record imported/source cuts and table digests before starting a campaign. Do not regenerate tasks or reinterpret their grading contract during an active assessment.

Use [AgentLab Harness Developer](../agentlab-harness-developer/SKILL.md) for actual Session, Turn, checkpoint, Fork, execution and capture operations. Follow the [public demos](../../examples/README.md) and their capability receipts. Strong supervisors, scripted supervisors and assessed Agents are different roles; supervisor control is recorded evidence, not participant authority.

Pin the participant implementation, adapter, model, environment and task. Keep Agent runtime dependencies outside the project Workspace. The Harness captures controlled LLM/MCP/tools and workspace outcomes independently; retain complete raw test evidence and failures without redaction or subject-supplied capture claims.

Run frozen acceptance checks. Report task/build outcomes, turn counts, timing and supported process metrics; distinguish failed Agent performance from Harness errors and incomplete observation. Only claim SessionFS checkpoint/Fork restoration where exact receipts prove it. Use generic MCPGit analysis rather than adding an analysis API.

Store operational observations/results in the installed Harness tables and Workspace state in SessionFS. Return evidence-linked findings to maintenance for the next seed/knowledge version; do not rewrite the frozen assessed case or update Release seed files from the running assessment.

### Formal capture admission and recovery

Treat a local forwarding proxy or a JSON receipt as observation, not proof of
durable capture. A formal evaluation requires the selected deployed Harness's
real, Attempt-bound capture admission and live durable sink before provider
dispatch. If that capability is missing, refuse formal admission; a permitted
local run is diagnostic and its reports must say TableGit durability was not
verified. Never count a capture failure as a student failure.

Keep the original attempt immutable. After capture, verify the exact original
exchange inventory and byte hashes against recovered payloads at the committed
revision, using the existing owning TableGit Service and its receipt. The
optional `--audit-gateway-exchanges N` on `examples/tablegit-session/run.py`
adds an exchange-by-exchange byte check after its actual Service readback.
New Participant runs record a producer-count inventory on shutdown; the same
TableGit example consumes a complete inventory automatically after recovery.
Partial capture remains retained and separately marked as a Harness issue.
`scripts/audit-llm-capture.py` can audit private local files, but a matching
directory alone does not establish TableGit provenance or formal admission;
`N` must come from an independently retained producer count. Preserve partial
and unknown operations, reconcile their exact identities before any retry, and
report original local capture separately from later persistence.

Agents initiate and inspect assessments; routine capture, persistence,
readback and completion reporting belong to the selected Harness workflow.
The SWE CI workflow generates a separate system completion report after its
persistence step, including failures and unknowns. Its fixture recovery result
does not qualify deployed Attempt admission. A manual run that bypasses that
workflow does not inherit its automation.

Do not assume one physical storage layout wins: compare single-record Git
history and the existing TableGit object/chunk path using the same captured
bytes, with write/read latency, size, exact history recovery, and operational
limits. `scripts/measure-git-context-history.py` measures only isolated Git;
its output is not TableGit performance, production qualification, or authority.

Produce target-instance guidance for this stage as TableGit Skill rows,
separate from the structured facts/tasks/results. Follow
[the two-layer methodology](../agentlab-skill-methodology/SKILL.md) for
method/source lineage and independent layer/role fields.

### External benchmark execution and budget boundaries

Before spending model budget, prove the participant's isolated launcher can
reach its assigned task container and that the official reference patch passes
the same independent evaluator. Inherited Docker CLI context may disappear
when HOME is isolated; provision only the operator-resolved local endpoint,
without mounting its socket or credentials into the task. Classify launch,
network, TLS and evaluator failures separately from participant ability.
Preserve the invalid attempt rather than converting it into a student failure.

Record each attempt's fixed token budget, exact input/output usage, cache and
reasoning subsets, incomplete-usage status and termination reason. Enforce at
the available request boundary and disclose any last-request overshoot. After a
confirmed budget denial, stop the participant's client-side retries; never
replay an upstream request of unknown outcome. Preserve and independently grade
the actual workspace patch even if the participant did not submit normally.
Report a passing patch and normal autonomous submission as separate facts.
Do not infer that an Agent queried a budget MCP tool when its adapter did not
expose it, or treat raw tool success as proof of useful progress.
For aggregate reports, verify retained evidence digests and regenerate each
assessment and linked view before counting it. Reject inconsistent or duplicate
results. A self-consistent digest does not authenticate the evidence producer.
When a participant framework raises a normal submission signal as an
exception, retain the raw event but do not count it as a failed tool call.
An outer shell exit code can conceal an inner failing command; inspect retained
output for relevant diagnostics before interpreting tool success as progress.
Separate a pre-dispatch Agent setup timeout from student reasoning and scoring.

### Mature benchmark to Harmony transfer

Use a pinned mature task to test the evaluation process before transferring it
to a Harmony task. Record repeated reference results and a separate no-solution
negative control; neither is a participant attempt or a model score. Preserve
per-trial identities and state precisely which task and image identities were
observed. Use the comparison in `examples/benchmark-report/harmony_alignment.py`
to keep historical Harmony observations separate from fresh instance readiness.
System-operated device checks are system evidence, not student device actions;
record teacher assistance without inferring that every hint was consumed or
caused an outcome. Resolve the exact previous operation before any recovery,
and only then freeze a new attempt with independent build, device and verdict
evidence. Do not transfer success rates between unlike datasets or environments.

For device tasks that require the participant to verify an outcome, report the
independent final-state check and the participant's verification separately.
An intention to inspect or capture a screen is not evidence of that action; use
the retained tool event and result. If verification is required by the frozen
task and is not evidenced, do not mark the whole task passed solely because the
independent final state is correct. Preserve any incomplete observation or
Harness failure rather than converting it into a participant failure.

When a participant-created verification script reports unexpected device
behavior, inspect both the retained device observations and the script's actual
input construction before attributing the result to the application or device.
For coordinate-based interactions, preserve the submitted arguments, parsing
rules, resulting coordinates and layout observations when available; do not
assume that a successful shell exit means the intended touch occurred. A failed
call that narrows the cause can be useful progress, while a successful call may
provide no valid test result. Keep observations, student hypotheses and
independently confirmed causes separate. A targeted diagnostic hint is teacher
assistance: retain its exact content and timing, count it against the assisted
result, and preserve the earlier independent result. Do not silently promote a
single trajectory to a general model ranking. If the student prints values,
independently compare retained raw observations against the frozen expectations;
reading those observations is not a separate device replay.

Do not infer that a participant did not inspect an image merely because its
native event log lacks a separate image-tool item. Reconcile the captured model
response's tool calls, the subsequent request's image inputs and their identities,
and the independent screenshot or layout. A request forwarded to an intermediate
gateway does not by itself prove delivery to the ultimate model provider. If a
later audit corrects a finding that prompted teacher help, retain and count the
actual help, record its cause, and reassess the independent result against the
original frozen criteria rather than silently rewriting history.
Use the [image evidence reconciler](../../examples/benchmark-report/image_evidence.py)
for captured `view_image` responses and subsequent request outputs; its
intermediate-gateway result does not establish provider delivery or comprehension.
The real-code-agent capture proxy also writes `gateway-image-evidence.json`
on shutdown for Responses captures. Consume it with the producer inventory:
an incomplete capture, unsupported protocol, analysis error or missing receipt
is an observation limit, not proof that the participant did not inspect an image.
The receipt is a derived operator observation; durable storage still requires
the selected Harness's own capture and readback.

### Actual staged navigation assessment

Use [the subject experiment](../../examples/knowledge-seed/subject/README.md).
Calibrate actual submitted methods/caller bodies without applying reference
transforms to subject code. Freeze the operational contract in TableGit before
assessment; use an explicit named outcome field if required by the independent
oracle. Preserve baseline/reference/wrong-stack outputs. Keep reference/oracle
and trusted gateway capture outside the participant filesystem mounts. Pi native
events are adapter observations, distinct from supervisor-owned gateway bytes
and source cuts. Separate valid Agent inability from Harness launch/build faults.
An exact selected-source cut and fresh-Agent branch comparison is source-only
lineage; it does not qualify formal SessionFS binary restore or device rendering.
Maintain generic method lessons and derived case instance Skills independently.

### Knowledge and operational evidence remain separate

Keep reusable method guidance in Release and source/case-specific guidance in
TableGit instance rows, with independent method revision, source revision, role
and stage. Record findings for goal, repository semantics, program analysis,
seed extraction, calibration and evaluation separately.

The three initial knowledge snapshots contain Skills, analysis facts and frozen
tasks; full historical gateway/native/source/build captures belong in runtime
observation and payload tables. Preserve every raw byte. Return compact findings
and explicit table/cut/row plus published archive references to the knowledge
seed. Publish the complete runtime export independently when reproducible raw
evidence is needed. Never inflate the seed with repeated cumulative event payloads.
Use stable IDs and stable export order; prove file reconstruction and unchanged
repeat import before publishing. See [the executable experiment](../../examples/knowledge-seed/subject/README.md).

### Feedback multi-round instance

Use [the shared subject runner](../../examples/knowledge-seed/subject/README.md)
with the frozen feedback case. Distinguish stage-one failure/retry state from
stage-two duplicate suppression. Verify actual reactive field declarations with
Rust ArkTS property facts; fixture initialization is not proof of submitted
initializers or decorators. Execute submitted methods without reference repair.
Preserve negative calibration for wrong reset, duplicate requests and wrong
initial state, plus raw/normalized source evidence. The demonstration backend is
an explicit Promise seam; full phone compilation and UI rendering are distinct.
Return stage-specific construction/evaluation guidance to instance Skill rows.

### Reliable history framing and phase attribution

Read JSONL using LF record boundaries, accepting CRLF as JSON whitespace.
Unicode U+0085/U+2028/U+2029 inside strings remain payload; text splitlines()
can invent malformed records. Preserve original bytes and use the shared
store.jsonl_rows reader for snapshot analysis/import verification.

Attribute controlled gateway exchanges using supervisor lifecycle time intervals
and record the exact status/lifecycle receipts. Retain explicit unmatched or
ambiguous attribution rather than guessing from message content. Re-ingesting
an older campaign preserves historical rows but must not replace latest instance
guidance from a newer campaign. Prove unchanged repeat import at the committed cut.

### Participant dependency floor

For an offline Harmony project with locked OHPM dependencies, prepare the
fresh workspace before participant dispatch. Use the existing build kit's
verified seed consumer with the project's actual manifest and lockfile; do not
substitute placeholder packages. The bounded helper
[`prepare-harmony-locked-deps.py`](../../scripts/prepare-harmony-locked-deps.py)
binds a separately acquired seed to the fresh project's manifest hashes, then
invokes the selected build kit's `deps --ohpm-seed` verifier. It requires a new
seed output and refuses a workspace that already contains `oh_modules`.
Retain the verifier result and run the baseline/reference build before model
budget. A missing seed or failed integrity check is a Harness preparation
failure, not student performance; retain it and do not dispatch. The helper is
an operator preflight, not proof of deployment or automatic integration into a
selected instance's Attempt workflow.

An assessed Agent may fail normally; a missing standard project tool is an
operator environment deficiency. Feedback's fresh branch recorded missing Git
and a separate Agent-authored Git-index parser bounds error. Preserve both raw
failures and their distinct attribution. Provision Node, Git and HTTPS trust in
the participant image, outside project files; use the shared participant-runtime.sh
preflight in local development, every main knowledge Action and real assessment.
Retain resolved image identity and tool versions. Do not retroactively relabel
an already assessed participant environment or repair its submitted code.

Initial assessment guidance must include its summary reference on the first
write. Repeating the same campaign preserves archived cut references and
subsequent evidence-linked maintainer findings; replaying older campaigns keeps
the newer latest summary. The shared guidance builder has first-write, same-run,
archived-reference and older-run regression coverage.
