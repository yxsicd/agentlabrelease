# Telemetry migration: contract correction before case construction

Overall flywheel maturity remains **54%**, an engineering estimate. This is
source-bound behavior characterization in a second repository, not autonomous
cross-repository flywheel qualification, a new formal case or Harmony acceptance.

PR148 merged as `c859ce7e38680db809d7846ff9235b3ba0343d37` after all eight applicable
checks passed. Its method experience is now on main; no new Release was created.

The code-workshop GitCode fetch terminated with curl18/early EOF. Read-only
AWMCP inspection recovered an existing clean checkout on hwlinux/ma:
`/home/huawei/agentlab-source-builds/code-workshop-7aa95cac-operation-v1`.
HEAD is `7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6`; origin is
`https://gitcode.com/HarmonyOS_Samples/sample_in_harmonyos.git`.
Operations exec-01e2 and exec-01e3 read the original source; exec-01e5 retained the
source-byte inventory. All three completed with exit zero and peer_direct routing
to the exact hwlinux/ma peer.

Original tracked source Blobs:

- TrackManager: `f08fe1b07eeacf265e9ba446190e337a76a529fd`.
- TrackTable: `6efc1a886b442fcb8e2a99140e73c02e3e5b6ce2`.
- TrackModel: `9edc9ee35f6dbacaf238d0b94bbbb4c505cfdfea`.
- TrackService: `6db5c78095db995403e1868321805c9b0a87d112`.

The private diagnostic verifies original bytes/SHA256/Git Blob OIDs from the
retained source capture, then executes unchanged TrackManager and TrackModel
bodies with TypeScript5.9.3 type erasure and controlled upload/store/timer seams.
Compiler SHA256 is
`3ae902c92cc44dace175c0e69e13a4b0899f6983c6121d76b9ab8dd5795e7675`.
Probe SHA256 is
`2077e3fbe3aed0333ef253b01960b06ac75c680fc327cab4f9f67f4824514ff0`.
Two local invocations exited zero and matched seven characterization boundaries;
the repeat is consistency evidence, not another productive flywheel round.

| Controlled scenario | Observed result |
| --- | --- |
| Empty queue | No upload or deletion |
| Fulfilled true | Deletes cached records |
| Fulfilled false | Also deletes cached records |
| Rejection below limit | Preserves records |
| Rejection at 1000 | Preserves records |
| Rejection at 1001 | Clears records |
| Insert during successful upload | Later full deletion also removes the new record |

The existing candidate `shadow-case-rdb-preference-telemetry-pipeline` has value
SHA256 `bc676978abcfb563f8d12616075ba05a8cd727a4cc25f24c2d8271002eef3dd9`.
Its migration selection summarized deletion as success-only, which is too broad:
the original implementation deliberately clears on over-limit rejection and does
not inspect a fulfilled boolean. The candidate was not modified, admitted or
frozen. Whether false means business failure and whether concurrent rows must be
retained require an independently reviewed intended contract, not inference from
the implementation or these characterization expectations.

Raw source capture, private probe and terminal execution receipt remain outside
source Git under `.artifacts/flywheel-action-continuation-20261001/`.
The retained execution does not run TrackTable/RDB/taskpool, the real upload
service, actual timers, UI producers or a Harmony framework. It is operator-led,
not an Agent run, independent Oracle calibration or knowledge authority update.

Next: resolve the intended persistence contract, prepare a source-bound focused
knowledge correction or additive candidate successor, and expose this different
async mechanism through the reusable author/executor/feedback interface. Do not
substitute a second handwritten diagnostic for autonomous cross-repository closure.

## Current-authority input continuity

PR149 merged as `2300b34b9e5669f6147591ac4329db18c5dad982` after all eight
applicable checks passed. The published first-four input still referenced
`38fc28d72870b36405287e048a5e6fce41a44b78`, while active knowledge had already
advanced to `368b17895b23633656a26f9f51cb300cb11fa829`. The existing Action's
preflight would therefore refuse to spend an Agent budget on that stale input.

A fresh read-only MCP check selected the configured Person, verified clean HEAD
before and after, and compared all five tables at the exact committed revision
with the retained knowledge export: 13 process Skills, 489 scope Skills, 62 facts,
39 refresh rows and zero evaluation cases. No authority write was attempted.
This continuation imports that already committed export, not another lesson or
coverage round. Nine changed/new export files match their original bytes,
including the portable report/sidecars; missing terminal newlines are preserved
because original-byte digests bind durable assessment references.

The new `construction-plans/telemetry-persistence.json` binds the unchanged
candidate value and requests its original three source paths plus TrackService
and RdbStore. AWMCP exec-01e6 verified the additional RdbStore Blob as
`e02eaa2d7f427ece6cfecf2ec58f6ec25c7852fd` on the same clean source checkout.
Reasons direct the next author toward fulfilled/rejected results, exact threshold
boundaries and snapshot/deletion ordering without asserting a normative answer.
Both runtime requirements, Oracle execution and wrong-variant calibration remain
unqualified; the old candidate and every prior generation row remain unchanged.

The actual durable-reference CLI selected refresh round39 and assessment round37,
whose original SHA256 is
`f255f78aa09a95201309f09c5bd5816369c49df7551bf62fc1366d000929e0b8`.
Focused preparation using that assessment succeeded. A Rust regression invokes
both actual CLIs and checks the original knowledge/candidate/history bytes remain
unchanged, alongside the historical AbilityStage preparation regression.
These two repository inputs prove preparation continuity, not real cross-repo
Agent execution, knowledge correction or an automatic feedback round.

Overall maturity stays **54%**. After integration and another live authority
preflight, run the existing focused-refresh Action with candidate
`shadow-case-rdb-preference-telemetry-pipeline` and this construction plan.
Do not dispatch from an unmerged snapshot, silently adopt a different authority
revision or count publication repair as new semantic coverage.

The actual Action preflight command also completed with `admitted=true` through
its normal Inspector transport and Person context, without injecting the private
maintenance Basic profile. This is live input admission, not a model run. Retain
its original receipt externally as `code-workshop-telemetry-source/action-path-preflight.json`.

Regression initially rejected the imported thirteenth Skill because the old
snapshot test treated every Skill as one of twelve repository process instances.
The check now preserves all twelve instances and independently validates the
additional calibration-method lesson's exact historical method bytes, bound
verified fact, source/lesson provenance and false formal qualifications. The
downstream queue test accounts for the added fourth plan, explicitly checks the
telemetry route remains non-executing/non-promoting, and preserves unchanged
repeat suppression. These are snapshot/test corrections, not relaxed admission.
