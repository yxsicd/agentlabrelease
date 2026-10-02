# Gap-selected source verifier construction

## Bounded review feedback producer

The Rust `--prepare-source-recipe-revision` mode takes `--author-request` for
the current independently prepared request, `--parent-author-request` and
`--proposal` for the exact original generation, and `--review-feedback`.
It emits an exclusive `--output` packet without executing generated code.
The current request must reproduce against current source/knowledge/policy;
the parent must have identical authority, source inventory, loaded content,
semantic facts and selected gap. Fresh host paths and pinned tool policy are
not substituted into the original retained bytes.

Feedback schema `agentlab.source_recipe_review_feedback.v1` has exactly eight
fields: schema, parentRequestSha256, parentProposalSha256, reviewed=true,
reviewer, verdict=revise, automaticPromotion=false, findings. Each of one to
eight findings has exactly id, sourcePaths, observed and requiredChange. Paths
must be loaded owned evidence, and text/input budgets are bounded. Review is
an operator assertion, not authenticated reviewer identity or approval.

`--check-source-recipe-revision --author-request REQUEST --revision-request
PACKET --output RECEIPT` reconstructs the exact packet before model dispatch.
The Python operator's optional `--revision-request` runs this Rust check before
creating a participant, retains original packet/check logs, and supplies prior
proposal plus findings to one fresh contained Agent turn. Existing transport,
generation, proposal and review gates remain unchanged. The packet supports one
revision from an original author request, not nested revisions or an automatic
multi-round reviewer. New output remains unreviewed.

The Action's optional revision_parent_run/revision_feedback inputs are paired
and bounded before model budget. It downloads only a completed constructor
Action from its own repository using a read-only Actions token, refuses a
revision parent, and prepares the packet against fresh live-admitted context.
Invalid hashes, context drift or missing original proposal stop before dispatch.
This is implemented feedback routing, not yet a successful live revised proposal,
approved verifier, formal case or complete business cycle. Maturity remains 63%.

Overall maturity remains 63%. This connects the selected operation gap to a
captured construction Agent and an explicit review boundary. Local arbitrary-source
regressions exercise proposal -> review -> execution -> independent qualification;
they are not real model-generation evidence or completed business cycles.

The Rust CLI `--prepare-source-recipe-author --knowledge CUT --source-worktree
SOURCE --repository SELECTOR --author-policy POLICY --output REQUEST` independently
reassesses the durable strict baseline, selects one source-only operation gap,
verifies the committed five-table cut and clean Git identity, and supplies the
selected scope's complete owned inventory with original digests and Blob IDs.
Full contents are preloaded only for owned evidence anchors from the scope and
its bound semantic facts; remaining inventory rows explicitly have content=null.
The packet is bounded to 80 inventory files, 128 KiB preloaded source contents
and 512 KiB serialized request. A proposed source path without preloaded contents
requires explicit context expansion and cannot be staged. Oversized evidence
anchors stop rather than increasing the context budget or selecting another scope.
The complete plan is represented by its exact digest, summary and
selected gap; the public Action also retains the original complete plan.

The operator policy `agentlab.source_recipe_author_policy.v1` pins an absolute
Node executable by SHA256 and zero to seven methodDependencies {path, sha256}.
Dependency selection and host paths belong to instance policy, not target-name
branches. This first producer authors CommonJS verifiers; other verifier runtimes
remain separate capabilities, not claimed universal language support.

`scripts/run-source-recipe-author.py` reuses the existing captured Pi/Gateway
launcher and requires the contained participant runtime. The construction Agent
receives pinned source context in its prompt, with no mounted source checkout,
evaluator or host credentials. It returns one exact JSON proposal and does not
own file placement. Its bounded turn has zero transport retries; raw events and
failures remain retained. The tool-call ceiling is a runaway guard, not proof of
tool-free execution; container policy provides the actual host boundary.

Proposal schema `agentlab.source_recipe_author_proposal.v1` has exactly seven
fields: schema, scopeSkillId, sourcePaths, verifierSource, rationale, limitations,
contract. The contract contains checks and controls. At least two reference
controls are required to represent independently reviewed valid alternatives.
Declaring roles does not prove distinctness or source-faithful behavior.
The verifier receives sourceWorktree, control ID, then pinned dependencies as
arguments. Controlled seams and in-memory variants are explicit limitations;
the reviewed demand is not proof of an upstream defect.

`--stage-source-recipe-proposal --author-request REQUEST --proposal PROPOSAL
--output FRESH_ABSOLUTE_DIRECTORY` regenerates the request from its current exact
inputs, binds only selected owned source files and operator-pinned commands,
retains original request/proposal/verifier bytes, and checks the existing static
recipe contract. No control is executed. Its recipe always has reviewed=false;
the existing executor refuses it. Invalid output may leave partial private
diagnostic artifacts, never an accepted stage receipt or authority rows.

After independently reading the verifier, demand, expected values, source usage,
wrong variants, alternative-valid implementations and execution policy, an
operator can use `--review-source-recipe-proposal --proposal-stage STAGE
--proposal-sha256 EXACT_PROPOSAL_SHA --reviewed --output NEW_RECIPE`. Review
rechecks the exact original request, source, method and executable bindings and
emits a separate reviewed recipe. The explicit flag is an operator assertion,
not authenticated reviewer identity or an automatic model approval.

Only then may the existing reviewed operation executor run controls. Independent
qualification must recompute the frozen checks from original captures before
fact preparation, strict reassessment, portable staging and atomic authority
admission. Static validation cannot detect a verifier that simply hardcodes
expected answers: source-grounded semantic review is indispensable. Never wire
the author Action directly to trusted host execution or authority promotion.

`maintainer-source-recipe-author.yml` offers a main-only, read-only-authority
workflow using the existing gateway credential. It first admits the exact live
knowledge cut, selects and checks out only the chosen scope, freezes compiler
and runtime inputs, and uploads an unreviewed proposal artifact. It does not
publish cases, execute generated controls, write TableGit or certify the loop.
Fresh real Action generation and independent review/execution are the next
acceptance step; no maturity increase follows merely from this workflow existing.

## Real repository request preflight

The native producer prepared the actual next platform-services scope against
clean source revision `7aa95cac4eca15e39fc6638cdf1de7db6fb70ad6` and committed
knowledge revision `ed832d1b7e0e26b040be8cbb54737124027f0a67`, with exit zero.
Its complete inventory has 39 files (140,866 original bytes). Four source-grounded
evidence anchors preload 15,204 bytes; the original pretty-printed request is
34,756 bytes. An initial full-content preflight exceeded the same 128 KiB budget;
the correction separates complete identity inventory from bounded semantic
context instead of enlarging the Agent budget or changing selected scope.
No model, generated verifier, control execution or authority write occurred in
this request preflight. The arbitrary-source Rust regression also rejects an
owned but unloaded path, forged context, unreviewed execution, mismatched review
digest, changed method bytes and output reuse.

## First hosted launch failure

PR #175 merged at `f17d2a53cb5d566485c15ff5178e82f238314c4d` after all
applicable checks passed. Real Action `37007339317` passed live knowledge
preflight, source request preparation and runtime containment preparation, then
failed before Docker/model execution because its operator did not create the
runtime receipt directory. Original stderr records FileNotFoundError from the
shared launcher's strict path resolution. The uploaded artifact retains the
original request and failed participant lifecycle; no model proposal or control
execution occurred. The construction operator now creates its receipt root
before dispatch, preserving the shared launcher's strict existence gate. This
fix does not establish generation quality or raise maturity above 63%.

## First model dispatch and incomplete transport

PR #176 merged at `46df79e6eed9788046d827773cb3fb5502d05de5` after all
applicable checks passed. Action `37008738003` crossed the launch boundary and
retained a real model response with zero tool calls and zero transport retries.
Pi exited zero after 61,643 ms, but its final message contained only thinking.
The original gateway status independently records a 60,033 ms response-body
deadline, upstreamEof=false, semanticComplete=false and
outcome=upstream_deadline_exceeded. The subsequent empty-text JSON error is a
symptom of incomplete transport, not a rejected complete semantic proposal.

Construction now requires every original Gateway status to prove complete
streaming response and clean EOF before serializing or staging any proposal.
Missing, incomplete, timed-out or disconnected exchanges reject and retain a
digest-bound completion report. Pi exit zero cannot override that gate. The
fixed-context source recipe lane requests provider reasoning_effort=none, as
already supported by the existing proxy; it still retains the same 60-second
deadline, strict JSON/schema gates and independent semantic review. Runtime
isolation validation also runs after a failed author step when containment was
prepared, so model/format failures do not suppress its independent evidence.
No complete proposal, generated control execution or maturity gain is claimed.

## Constructor budget and provider capability correction

PR #177 merged at `4976cce1a745227fbbd8f01d127582fcc9c8088c` after all
applicable checks passed. Action `37010428172` transmitted reasoning_effort=none
but again retained only thinking until the 60,046 ms upstream deadline. The
completion gate correctly rejected it before serialization, while independent
runtime isolation validation passed after the failed author step. There was no
valid proposal or control execution.

The [official provider capability documentation](https://docs.z.ai/guides/capabilities/thinking)
states GLM-5.3 and GLM-5.3-FLASH cannot disable thinking; API efforts are low,
high and max, and Coding Plan maps none/minimal to low. The earlier description
of reasoning_effort=none as an effective no-thinking mode was incorrect for this
model. An operator-side request field is not proof of upstream behavior.

Executable-verifier synthesis is also materially different from a short semantic
summary. Its operator now exposes reasoning effort and an absolute 30..180-second
response budget, with Action choices 60/120/180 and defaults low/180. This uses
the existing Participant bounds and leaves the semantic-analysis lane unchanged.
The source constructor keeps its existing native supervisor, zero transport
retries, bounded source/proposal sizes, complete-stream gate and independent
review before execution. The deadline increase is explicit experiment policy,
not another hidden retry or a maturity gain. Fresh completion still requires an
original complete response, strict proposal staging and independent semantic
and behavior review; a longer budget alone proves none of those.

## Live deployment catalog and optional reasoning policy

An authenticated read of the actual Action Gateway `/v1/models` returned HTTP
200 and eight admitted text model identities: deepseek-v4.1-flash,
gpt-5.6-luna, nvidia/nemotron-3-ultra-550b-a55b:free, MiniMax-M3,
glm-5.3-flash, mimo-v2.6-flash,
nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free and glm-5.3.
The authenticated `/v1/health/providers` read independently returned seven
configured route IDs, including opencode-go and opencode-go-responses. Catalog
membership is not proof that an arbitrary explicit route accepts a model.
The advertised gpt-5.6-luna endpoint link returned HTTP 404; its model description
names OpenCode Go, while the current local container catalog binds it to
opencode-go-responses. Neither the broken link nor local configuration may be
presented as successful live endpoint-route admission.

The admitted mimo-v2.6-flash model advertises tools, tool_choice and
response_format, not reasoning_effort. The constructor previously always sent
an effort value, which prevented a clean provider-default experiment. It now
accepts `--reasoning-effort default` and passes None to the existing participant,
so its proxy omits the field. This differs from the explicit string none and
does not claim disabled thinking. Existing low default and explicit values
remain unchanged. The Rust-driven dispatcher regression exercises default
omission as well as low/high values and unchanged zero-retry policy. No live
construction success follows from catalog discovery or this option alone.
The next same-method candidate experiment is mimo-v2.6-flash/opencode-go with
provider default settings; actual Gateway admission, complete response and
unreviewed recipe staging remain required. Secrets stayed in the operator;
no credentials, native sessions or raw captures were committed to source Git.

## Admitted-model dispatch evidence

PR #178 merged at `2e72a386920fbd22067e60c8e11f1108fa8fa1cb` after all
applicable checks passed. Public validation `37011190812` first failed only the
alprod installation with a network connection error after composition and
client checksum admission; its failed-only second attempt passed on the same
source head. The original failure is retained, not rewritten as first-pass success.

Action `37012567460` used that exact method commit with GLM-5.3-FLASH,
reasoning_effort=low and the explicit 180-second response budget. Its original
Gateway receipt records 180,222 ms, responseBytes=1,913,415, upstreamEof=false,
semanticComplete=false and upstream_deadline_exceeded in response_body. Pi's
retained final message contains only 37,251 characters of thinking and no text.
The completion gate rejected it before proposal serialization; independent
filesystem, network and external-credential isolation validation passed.
Increasing the response budget therefore did not produce a complete proposal.
The original artifact is retained outside source Git; its roughly 30 MB size
reflects captured events, not a valid proposal or new knowledge gain.

A separate same-method experiment `37013702330` requested GLM-5.2 with none/180.
The operator received `400 model glm-5.2 is not admitted on route glm` before
model execution. Provider documentation support is not deployment admission.
No shared Gateway policy was changed, no hidden retry occurred, and neither
experiment produced generated controls, a formal case or authority rows.
Maturity remains 63%; complete five-stage cycles remain zero. The next useful
action is authenticated read-only discovery of the deployment's admitted model
and route catalog, then a capability-compatible construction strategy, not
another blind model-name trial or deadline increase. Current local Gateway
source exposes authenticated `/v1/models` plus advertised model endpoint links;
that source contract is not proof of the deployed catalog contents or of an
effective upstream reasoning setting. No live catalog read is claimed here.

## Complete transport but token-truncated generation

PR #180 merged at `ec1ca33ac8967067c0c45b16feb7320615dab716`. Its exact-head
public validation first failed during release download with repeated HTTP 500,
before Btrfs installation; failed-only attempt two passed on the same source.
Action `37017038649` then used MiMo-V2.6-FLASH / opencode-go, provider-default
reasoning and the unchanged 180-second response budget. Original Gateway capture
shows HTTP 200, clean EOF, semanticComplete=true, completed outcome and 153032 ms.
The native final message nevertheless records stopReason=length, output=8192,
36065 thinking characters and no text. The actual wire has max_completion_tokens
8192 and neither reasoning_effort nor thinking. Independent runtime isolation
passed; no proposal, source control, fact or formal case was produced.

The construction gate now separately requires native stopReason=stop before
proposal staging and retains generation-completion.json. A clean SSE end is
transport completion, not proof that model synthesis finished. It is not eligible
for format-only finalization when generation was token-truncated.

An optional --thinking-type default/enabled/disabled independently controls the
explicit thinking.type field at the operator proxy. Default omits it and keeps
all historical callers unchanged. No model-name dispatch or shared Gateway
policy change is introduced. [MiMo's official documentation](https://mimo.mi.com/docs/en-US/quick-start/usage-guide/other/deep-thinking)
documents this separate enabled/disabled switch; that does not prove the deployed
OpenCode route honors it. A fresh captured disabled-policy experiment must prove
actual behavior. Do not raise token/deadline budgets or claim disabled thinking
from the participant's --thinking off flag alone. Maturity remains 63% and
complete five-stage cycles remain zero.

A fresh small-budget live proxy probe on the same MiMo/opencode-go route sent
thinking.type=disabled and max_completion_tokens=512. It returned 14 final-text
characters, zero reasoning-content characters and finish_reason=stop. Original
request/response/status bytes are retained outside source Git. This proves that
this route accepted the switch and produced final text for the tiny probe, not
that source-verifier synthesis will succeed or that all future thinking is absent.
The next full construction experiment must use the unchanged selected source gap,
original bounded context and independent review/execution requirements.

## First complete proposal and independent rejection

Action `37019616832` ran exact method `55976d785e8b43aea64c82e354a0e7a01070de20`
with explicit thinking.type=disabled. Its original Gateway capture completed in
94296 ms; native stopReason=stop, 7019 output tokens and 25579 final-text characters
passed both completion checks. The operator serialized the original proposal,
then Rust staging rejected `source operation id missing`: checks were strings,
not frozen id/pointer/expected objects. Independent runtime validation passed.
This is the first complete real proposal, not an approved verifier or formal case.

Independent source review also rejected the semantics and execution policy:
the rationale reverses original subscription ordering; reference controls remove
or duplicate required subscription; some transformations do not match original
declarations; many spelling checks read unchanged source rather than variants;
the verifier writes and deletes temporary compiler files. No generated code ran.
Original proposal, request, logs and response remain outside source Git; they
were not repaired or relabeled as reviewed. The next construction prompt gives
an exact oracle-object example, raw observation rules, direct source ordering,
invariant-preserving alternatives and explicit in-memory-only execution policy.
An early Rust shape check now rejects malformed oracle objects before stage
directory creation with a useful error; semantic truth still requires review.
Maturity remains 63%, strict maintenance-ready scopes remain four, formal cases
and complete five-stage cycles remain zero.

## Normal stop with malformed JSON and invalid reference expectations

Action `37021506945` ran method `1c28f8484d26f883612b1e36a55dc56914e5b51f`
with the same selected gap and explicit disabled thinking. Its final message had
stopReason=stop, 4257 output tokens and 16880 text characters, but JSON parsing
failed at character 16880 because the top-level object was not closed. Original
text also assigns nonempty expectedFailedCheckIds to reference controls, contrary
to the shared oracle contract. No punctuation was repaired, code executed or
authority promoted. Raw native output remains retained outside source Git.

Construction now offers optional --response-format json-object, forwarded as
response_format.type=json_object by the operator proxy; historical callers omit
it by default. Explicit provider capability and a fresh live probe precede full
dispatch. The prompt reinforces common raw observation shape, one frozen check
set and empty reference failures. Provider JSON mode cannot certify semantic
correctness. This candidate has semantic defects as well as malformed serialization
and therefore must not enter format-only repair. Maturity remains 63%; zero
formal cases and complete five-stage cycles remain unchanged.

A fresh 512-token live probe through the same route explicitly sent disabled
thinking and JSON-object response mode. The original response parsed directly
as an object with checks and a quoted-code verifierSource, 255 text characters,
zero reasoning characters and finish_reason=stop. This confirms the tiny request's
mode behavior, not schema guarantees or source-verifier quality. No returned code
was executed; raw request/response/status remain outside the source repository.

## JSON-mode limitations and native protocol capability

Action `37023684774` ran method `0ac5c8739be4c6321a5e3eb18a2385c45b7bbc9f`.
The wire explicitly carried JSON-object output mode and disabled thinking.
Transport completed in 40925 ms; native stopReason=stop, 2103 output tokens and
8241 text characters. Strict parsing refused trailing `<|im_end|>` after the
object. Diagnostic-only prefix reading did not serialize or approve a proposal.
Source review also found untranspiled ArkTS passed to JavaScript evaluation,
invalid array /length pointers and already-cleared initial account fields that
cannot distinguish missing-clear mutations. Runtime isolation passed; no generated
controls or authority rows were produced. Provider JSON mode is not a guarantee.

A tiny GPT-5.6-LUNA / opencode-go-responses probe through Chat Completions returned
400 invalid_model_route: no qualified upstream mapping for OpenAiChatCompletions.
A distinct native /v1/responses probe reached response.created followed by an
upstream rate-limit error. Its HTTP 200 is failure evidence, not successful model
execution. Neither changed shared Gateway routing or retried automatically.

The participant now supports an explicit --api openai-responses option while
preserving the default openai-completions API. Pi's model configuration selects
that native API; reasoning uses reasoning.effort and JSON mode uses text.format.
The isolated proxy permits only the selected protocol path. Responses completion
requires a completed status event without error/incomplete details and clean EOF;
DONE alone, response.created, incomplete and rate-limit events cannot qualify.
The current adapter is Pi-only; mini-swe-agent and thinking.type combinations
with Responses fail before model dispatch. No protocol is inferred from a model name.

A fresh explicit 512-token probe with the new native proxy reached this actual
route successfully: HTTP 200, 4037 ms, 102 final-text characters, directly parseable
checks/verifierSource object, response.completed status=completed, clean EOF and
no stream error. Raw request/response/status remain private retained evidence.
This is wire-level route proof, not a real Pi construction turn or source-verifier
qualification. The next hosted experiment must select native Responses explicitly
with the same bounded source context and independent review requirements.
Maturity remains 63%; formal cases and complete five-stage cycles remain zero.

## Full native Responses construction and rejected control contract

After PR #184 merged as `6f979ebcb66df9d8c4f1c4725ea518e6c50560fc`,
Action `37027636128` used the pinned contained Pi runtime and explicit native
Responses with none reasoning and JSON-object mode. The original Gateway capture
completed in 9729 ms with HTTP 200, semantic completion, clean EOF and no stream
error. Native stopReason was stop; output was 930 tokens. Strict JSON parsing
succeeded and the original proposal was serialized. Independent filesystem,
network and external-credential isolation validation passed. This is full native
construction transport evidence, not merely the earlier tiny probe.

Rust staging rejected `recipe author alternative-valid control required` because
the proposal put prose in role fields. The prompt did not state the exact role
enum; it now explicitly requires baseline/reference/wrong, and early control
shape validation rejects unknown roles, extra fields and non-string failure
arrays before creating a stage directory.

Independent source review also rejects the unchanged proposal. Both reference
IDs fall through to the original source, not distinct valid implementations.
The wrong disabled-gate replacement expects six spaces where the source has
four and therefore changes nothing. Both executed scenarios successfully enable
notifications; neither exercises rejection or disabled enablement, so even a
matching gate mutation would not be exposed. Shared event expectations read the
second scenario but use indices associated with a different sequence. These
defects are not eligible for role-only or format-only repair. No generated code
was executed or approved, and no authority row was written. Generalized lessons
are retained in the method reference; the next producer improvement must support
bounded source-grounded review feedback rather than silently fixing a rejected
proposal. Overall maturity remains 63%; formal cases and complete business cycles
remain zero.
