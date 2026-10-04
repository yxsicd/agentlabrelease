# Parameterized reviewed knowledge return

Maturity remains 75%; complete automatic five-stage loops remain zero.

The previous operator-coordinated reviewed knowledge transaction used a strict
private transport with fixed paths/revisions. The ordinary TableGit writer may
bootstrap tables and retry revision conflicts; those behaviors must not become
implicit authority in an autonomous reviewed-lesson return.

`python3 scripts/commit-reviewed-knowledge.py --request ABSOLUTE_JSON
--credentials ABSOLUTE_PRIVATE_ENV` now parameterizes that boundary. It first
invokes Rust `--stage-lesson-admission`, then reuses existing delta, envelope,
portable-sidecar and committed-export logic behind a strict serial transport.
It admits exactly one inserted Skill/fact/refresh row, never updates/deletes,
never creates tables and never rebases or dispatches a second transaction.
Every paged read owns its capture identity and verifies complete unique coverage
at the fixed revision; the current 1000-row/table bound is preserved explicitly.
Transaction intent precedes dispatch, including uncertain failures. Native tool,
writer dependency and reconstructed staged/baseline bytes are fenced before write.

Request schema `agentlab.reviewed_knowledge_store_request.v1` requires reviewed=true,
automaticPromotion=false, endpoint, knowledgeRepository, expectedKnowledgeRevision,
knowledgeDirectory, proposalDirectory, lessonSourceDirectory, lessonId,
flywheelTool, flywheelToolSha256, tablegitWriterSha256, outputDirectory, runId and
githubRepository. Optional personShowname overrides the private default Person;
producerUrl supplies provenance. Credentials are supplied separately and never
written in request/captures. Output must be a fresh private directory, not Release.

Isolated transport fixtures passed through the system Python interpreter with
exit zero: one successful CAS, uncertainty/conflict/unchanged-revision retention,
update/bootstrap/duplicate/drift rejection, and complete/duplicate/revision/
truncated/over-budget paged reads. No real endpoint was invoked. The Rust test
wrapper and real coordinator integration remain unverified.

This is an unqualified transport implementation pending full regressions and real
coordinator integration. It does not authenticate review semantics, publish a
consumer snapshot to GitHub, schedule another round, or support replacing existing
knowledge. Historical-method lessons still require their pinned validator; no
historical method identity is silently rewritten. No remote write has been run.

## Prospective construction evidence

Run 37186335352 at method 4437f017f5a25e2d4e9c18467f0a8619437d985d passed
fresh dependency acquisition, initial design plus one actual design-correction
turn, code construction and independent participant isolation. It failed baseline
diagnostics with code repair budget exhausted, before control-suite/review/return.
Retain both design attempts and every code diagnostic; this terminal run cannot
reopen its allowance. Original ZIP inspection found an initial missing constructor
adapter (`CommonBoolMapping is not a constructor`). One real code repair removed
the execution exception, but two of twelve frozen checks still rejected baseline
observations; no wrong controls executed. This is a completed rejected baseline,
not an application defect verdict or accepted Oracle. The design correction
repaired the declared seam inventory, not the prior cohort's numeric check IDs.
Constructor artifact 11297208127 has SHA256
d793b29e8a0985f04f991a068fdac9d624e98e89be92e321a23e3bc09ac508f7.
The separate reviewer artifact contains enrollment only, not a completed review.
