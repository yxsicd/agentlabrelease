# Gap-selected reviewed source-operation loop

Overall flywheel maturity remains 63%. This producer removes manual chaining
between reviewed source-maintenance operations; it does not generate recipes,
call a model, write TableGit, generate/calibrate cases or execute the full five-stage
business cycle. Two productive arbitrary-source fixture rounds demonstrate the
algorithm, not two productive real-repository flywheel rounds.

The CLI was also exercised against the exact committed four-repository cut
`131613e12afee0311238e35cf9eee5c604ace2f2` (cut SHA256
`a2055aec99f3247447493add5d1cf8bef7219f0b041ea82db8c00b8f4ce55431`).
With no reviewed recipes enrolled, its actual plan selected the next
code-workshop persistence/telemetry scope and returned
selected-source-operation-recipe-required with zero productive operation rounds.
This is a real routing-gap receipt, not a target execution or authority gain.

Run the Rust CLI with `--execute-source-operation-loop --knowledge ABS_CUT
--operation-catalog ABS_CATALOG --iterations 1..3 --output FRESH_ABS_DIRECTORY`.
It first verifies the exact initial knowledge-cut digest and all five table
digests, then resolves the baseline through durable refresh history. Each round
independently reassesses and plans one source-only operation gap, selects only
that scope's reviewed recipe, executes original controls, independently qualifies
the capture, prepares a deterministic fact, compares strict assessments, and
stages a parent-bound portable candidate. The next iteration consumes that staged
cut, including inherited receipt bytes. It does not continue selecting the old
baseline or borrow another scope when its selected recipe is absent.

The catalog schema is `agentlab.reviewed_source_operation_catalog.v1` with
reviewed=true, automaticPromotion=false, knowledgeCutSha256, repositorySelector
(`auto` or an exact repository ID), and entries (zero to 64 unique scopes).
Each entry contains scopeSkillId, an absolute sourceWorktree, and recipe
{absolute path, sha256}. Recipes retain the existing source-only contract and
must be reviewed individually. All recipe byte bindings are checked before
output creation and again before the selected execution. Catalog review is an
operator assertion, not authenticated authorship. Commands are trusted reviewed
operations, not sandboxed Agent-produced programs.

An absent selected recipe produces status=review-required with a named scope,
the complete plan and no command capture. No source-only selection is also
review-required, not convergence: other capabilities and downstream work remain
in the plan. Exhausting the requested one-to-three iteration ceiling yields
bounded-round-limit, never complete. A failed operation preserves its original
process streams and a terminal failed loop receipt; the CLI exits nonzero. A
partially productive run retains its last independently staged candidate and
does not mutate authority. Output reuse and changed cut/recipe bindings reject.

`productiveOperationRounds` counts scoped candidate transitions only.
`closedLoopQualified`, `authorityWritePerformed`, `automaticPromotion`,
`recipeGenerationPerformed` and `agentExecutionPerformed` remain false. The
existing reviewed atomic writer may admit an independently accepted candidate
and read it back, but this loop does not perform or certify that separate step.
Private captures stay outside the release repository. Store maintenance
next-round plans separately from candidate construction plans; their schemas
and consumers are different. When a new committed cut is selected, create a new
guidance selection rather than rewriting the original historical request/run.
