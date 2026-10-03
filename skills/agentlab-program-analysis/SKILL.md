---
name: agentlab-program-analysis
description: Maintain revision-bound program structure and analysis evidence used to generate evaluation seeds.
metadata:
  agentlab-layer: method
  agentlab-role: maintenance
  agentlab-stage: program-analysis
  agentlab-ownership-plane: repository-native
---

# Program analysis maintenance

Analyze the same source commit as semantic knowledge. Record symbols, imports, call candidates, module dependencies, configuration/resource references and available test/build entrypoints as typed `program_facts` rows. Use stable source-derived IDs.

Program analysis MUST NOT form an independent shortcut around maintainer Skills.
Every candidate binding names revision-matched repository-analysis,
program-analysis and seed-extraction instance Skills plus the exact supporting
facts and archived analysis rows. Missing coverage fails closed under
[the maintainer knowledge gate](../../docs/maintainer-skill-gated-case-pipeline.md).

Prefer a language-aware parser/compiler when available. A lexical extractor or name join is useful but must retain its method and unresolved status; a same-name candidate is not resolved dispatch. Record source path/span, analyzer identity and source revision. Keep semantic Skill links explicit.

Run generic MCPGit table programming/search/SQL over fixed input cuts. Archive code, request/bindings, complete typed result and interpretation as analysis rows. Cases reference those analysis IDs. The existing executable SQL example joins call and symbol candidates; it is not a Harmony parser.

Analyze candidate dependency chains and impact surfaces, then hand them to [seed extraction](../agentlab-seed-extraction/SKILL.md). State coverage and gaps such as reflection, dynamic loading, generated code and missing build dependencies only when they affect this source analysis.

Store source/facts/analysis structurally in TableGit. Build trees and temporary binaries belong to SessionFS Workspace snapshots; do not put multi-GB compiler output into Git. Export with [the three-table workflow](../../examples/knowledge-seed/README.md).

Produce target-instance guidance for this stage as TableGit Skill rows,
separate from the structured facts/tasks/results. Follow
[the two-layer methodology](../agentlab-skill-methodology/SKILL.md) for
method/source lineage and independent layer/role fields.

## Current Rust ArkTS analyzer

Use crates/agentlab_code_analysis (agentlab-code-analysis), pinned Tree-sitter
0.27.0 and the AgentLab grammar extension derived from tree-sitter-arkts0.2.0. It lowers CST nodes to module/symbol/call,
assignment/decorator/ArkUI facts with exact source spans. Multiline imports are
AST-derived, not lexical regex matches. Tree-sitter is not a semantic type AST;
calls and assignments remain unresolved. Read the crate README for command and
coverage. The stateStyles object-block gap is fixed by an explicit pair-value grammar
extension with upstream/extended regression tests. All556 fixed code-workshop
files now parse without syntax errors. Retain the original failure evidence and
the exact grammar digest; this does not qualify typing, resolved calls or HAP.
When improving an analyzer, update existing facts and remove obsolete AST rows
using their actual versions; archive old cuts and do not merely insert facts on
the first run. Test fixtures need process-local uniqueness under parallel tests.

When expanding the selected corpus, validate established dependency paths while allowing additional legitimate paths. A fixed result count confuses broader coverage with regression; archive the query/input cut and describe the observed path count without claiming symbol resolution.

When downstream construction readiness finds that an already semantic-ready
fact omitted required implementation or Oracle paths, refresh that same stable
fact instead of inventing another fact or consuming a random unbound scope.
Bind the exact candidate and readiness-plan digests, retain every prior evidence
Blob, require every missing path with its exact source Blob, and independently
reassess the full table. A focused refresh must not increase program-bound or
semantic-ready counts, grant operation readiness, execute the Oracle, or mutate
the frozen candidate. Persist the enhanced fact as one revision-fenced TableGit
transaction; regenerate the downstream candidate only from the later cut.

Distinguish inventoried paths from loaded implementation context when constructing
source-maintenance verifiers. For a small responsibility whose complete UTF-8
source fits the author context budget, include its owned implementation bodies
with exact Blob/digest identities rather than only anchor files; this can expose
real mapping/helper behavior without guessing dependencies. Larger responsibilities
retain bounded anchor context and require explicit decomposition or context refresh.
Binary bodies remain unloaded. Additional context is not semantic verification,
permission to modify another responsibility, or evidence of platform execution.

Use the constructor's `--design-first --design-only` mode when a new behavior
surface needs independent semantic review before verifier generation. The retained
design/validation digests bind an unreviewed draft, not an approved Oracle. Review
source-derived return shapes, synchronous versus Promise seams, initialization,
and the actual branch affected by each wrong control; structural validation cannot
prove those semantics. Preserve complete design failures and partial generation
captures. A generation deadline is not permission to stage incomplete output or
to treat isolation validation as behavioral qualification.

For a design-level revision, pair `--parent-design` with
`--design-review-feedback` and retain `--design-first --design-only`. Rust binds
the original request/design hashes, checks that the source/knowledge request still
reproduces, and limits findings to loaded owned paths before model dispatch.
Feedback requests revision; it cannot approve the parent or successor. This path
does not require inventing a completed verifier proposal after an earlier code
generation failure. Keep design feedback separate from executable-proposal review.

Keep repair feedback actionable: distinguish schema/scope mismatches from invariant
byte limits and limitation counts, report the observed value, and retain unchanged
acceptance limits. Draft state must use strict JSON; undefined source behavior needs
an explicit observation representation, not an illegal literal or a source rewrite
to null. Constructor lookup sequences and real method argument shapes are execution
inputs, not facts established by prose descriptions of initial state.

Separate modification ownership from read-only source context. A construction
Oracle may inspect a path outside its editable responsibility only when the
candidate explicitly lists it as context, a bound fact cites its exact Blob,
and exactly one scope in the same repository/source cut owns it. Report that
owner without expanding the candidate's editable selectors or claiming a
resolved dependency edge. Missing, conflicting or revision-mismatched context
bindings remain knowledge blockers; runtime and Oracle qualification stay
independent. A failure after knowledge persistence must recover the committed
cut and retained proposal, not rerun the successful Agent or overwrite history.

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

### Loading lifecycle and shared-helper analysis

Rust binding facts preserve declaration kind, owner, type, initializer and exact
byte span. Execute submitted top-level delay constants as well as lifecycle
methods; injected reference constants can hide incorrect Agent changes. Execute
the submitted shared BreakpointType implementation with a controlled platform
enum. Preserve source analyses for the lifecycle, helper and caller separately,
even where local fact IDs coincide. An import seam is source evidence, not
executed UI or resolved runtime call coverage. Calibrate wrong cancellation and
unknown fallback before the staged real Agent case. Invalid source and an Agent
that never reaches tools remain valid failed outcomes with empty typed tables.

When changing a shared helper's default return, identify known values that were
implicitly served by that return. Retest every known value at every later turn.
The loading capture's parent lost the lg branch while adding unknown-to-sm
fallback; a fresh branch retained it. Archive both the failed named check and
submitted helper source before drawing this conclusion. Compile success alone
does not detect this semantic regression.
