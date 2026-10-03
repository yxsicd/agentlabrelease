# Source-recipe knowledge consumption and equal-task treatments

Overall maturity remains **74%**, an engineering estimate; accepted complete
automatic five-stage business loops remain **zero**. This implements the missing
source-constructor integration, not a new real Agent run or demonstrated benefit.
PR236 merged as 969f84c71e70f5d33f9b6e0b064901fb0e6f94be after all applicable
checks passed, publishing the admitted b5a07f1b knowledge cut on main.

## Native applicability and task preservation

`--bind-source-recipe-guidance --knowledge CUT --author-request FILE
--guidance-request SELECTION --output NEW_FILE` reuses the existing guidance
binder across all five tables. It requires calibration stage, exact author-cut
digest/revision, source repository/revision and selected scope. The reviewed
selection additionally requires sourceRecipeTarget with exactly scopeSkillId,
sourcePaths (1..16 unique safe paths) and nonempty bounded demand. Every path
must be uniquely loaded with matching original-content SHA256 in the request.
The packet includes sourceRecipeBinding.authorRequestSha256 and the target.
Applicability remains a reviewed decision, not automatically inferred semantic
truth or authenticated reviewer/source provenance.

The constructor now accepts paired --guidance-knowledge / --guidance-selection
and --guidance-mode guided|unguided. It retains all five tables plus cut,
selection and original author request outside the participant workspace, invokes
the Rust binder before participant creation, and supplies the same reviewed
target to both modes. Only guided receives the selected body/provenance/limits.
The complete packet is appended to actual design/code turn prompts; bounded
design/proposal corrections also receive it. Existing no-guidance calls preserve
their original prompt and budgets. Diagnostic fresh repairs inherit the workflow
selection, mode and fixed knowledge directory; old exhausted roots do not reopen.

Ordinary --stage-source-recipe-proposal accepts optional paired source-guidance,
source-guidance-knowledge and source-guidance-selection. It independently rebinds
the packet and rejects changed scope or omission of target paths before creating
staged output. Both treatments use this same target gate. Listing a path does
not prove executable use, correct method selection or semantic approval.

## Original wire-capture completion

`--verify-source-recipe-completion --participant-evidence DIR --guidance-packet
FILE --output NEW_FILE` reconstructs the packet from retained tables/request/
selection before checking original source-recipe-author prompt, intent, lifecycle,
final message and complete upstream request/response/status bytes. It reuses the
existing model/route/reasoning, budget/no-transport-retry and raw semantic-terminal
gates without renaming source captures into author-calibration files.
The optional format-correction turn keeps its own original label. Any retained
correction capture selects that turn, including partial evidence; an incomplete
correction cannot fall back to the first turn's passing lifecycle. Length-limited
generation rejects even if its final-message digest is recomputed.

Guided completion requires the full packet in the actual prompt. Unguided
completion requires the same target, no selected Skills in intent and absence of
selected body bytes (plain or JSON-encoded) from all recorded message history.
This proves the recorded treatment, not absence of general model knowledge.
Both require complete captured transmission and participant completion, not
HTTP 200, a producer success flag or a prompt hash alone. Unguided reports
authorCompletionVerified=true and agentConsumptionVerified=false.
`--verify-source-recipe-guidance-consumption` additionally rejects unguided.
All receipts keep learningBenefitVerified=false and do not qualify cases.

The constructor independently invokes this completion gate after closing its
participant/proxy, before proposal staging. Failed/partial captures remain
retained. This lane currently supports openai-completions; other wire protocols
are rejected before model dispatch rather than misclassified after spending a
budget. The ordinary unguided/no-selection constructor protocol support is
unchanged.

## Action and experiment boundary

Main-only maintainer-source-recipe-author.yml exposes optional checked-in
guidance_selection and guidance_mode. It forbids external URLs/traversal and
requires a bounded regular in-repository file. Blank selection keeps the existing
workflow. A selection is not permission to ignore a different planner-selected
scope: target mismatch remains a pre-inference stop.

The separate Rating source-recipe selection binds the committed b5a07f1b lesson
to its input/display scope and exact RatingDescriptor source. Its demand is the
same in both treatments; it does not include the lesson's detailed observations
as unguided task instructions. Historical Rating selection/packet remain intact.
This fixture target is not a repository-name branch in implementation.

Regressions exercise two unrelated repository identities, source/cut/scope/path
drift, missing/unloaded/duplicate targets, proposal target omission, the actual
CLI and producer prompt helper, original source wire fixtures, incomplete or
hash-only captures, retained-input changes and unguided history contamination.
These are fixture/regression evidence, not cross-repository real-run acceptance.

Local validation: 90 Rust tests passed across the library, guidance, source
operation, source diagnostic and business suites. Cargo formatting, Python
transport syntax, Skill validation, actionlint v1.7.10 and Release checksum/link
validation passed. No real model was dispatched by these checks.

Remaining critical path: merge after CI, dispatch fresh equal-policy guided and
unguided source constructions, inspect their full captures and independently
reconstruct controls before reviewing results. Repeat before attributing benefit.
Before any benefit comparison, freeze an independent common quality/check rubric:
different generated scenario/check sets cannot grade themselves into a shared
score. An initial guided/unguided construction pair can qualify transmission and
integration while still leaving comparative semantic quality unverified.
Source-suite business-return binding, complete automated productive rounds,
cross-repository transfer and Harmony/ohosTest execution remain separate gaps.
