# Native compiler evidence for construction and review

## Purpose

Source import inventory is syntactic. A type/interface import may disappear in
the host compiler's emitted output and therefore is not sufficient evidence of
an unbound runtime dependency. This capability turns the retained diagnostic
lesson into source-bound construction data, without executing submitted source
or supplying implicit framework bindings.

## Explicit activation and identity

An author policy may set `compilerAnalysisAdapter` to
`typescript-transpile-v1`, with exactly one existing `methodDependencies` entry
for the pinned compiler. Rust uses the policy's exact executable and dependency;
it does not discover either from PATH. Both identities are checked before and
after the bounded child process. Unknown adapters fail closed. Policies without
the adapter preserve existing request bytes and do not invoke it.

The child has an empty inherited environment, a 30-second deadline, bounded input
and captures, and only the committed analysis script. It parses and transpiles
source strings; it does not require modules from the target source or evaluate
emitted output. CommonJS, ES2020 and the evaluator's `.ets` filename mapping are
fixed. Original parse, transpile and emitted-parse diagnostics remain visible.

`sourceCompilerEvidence` records source revision, input-manifest identity,
executable/compiler/analyzer/runtime-helper digests, compiler version/options,
per-file source and emitted-output digests, diagnostics and static emitted
require-call candidates. Loaded supported script-language bodies are included;
binary, unloaded and other-language sources are not claimed as analyzed. Duplicate
source paths fail rather than selecting an arbitrary owner.

## Pipeline integration

Original author-request preparation generates the evidence. Request admission
reconstructs it from the same source and policy; changing retained evidence cannot
pass by copying a receipt. Supplemental read-only context causes reconstruction
of the extended inventory without expanding editable paths. Revision admission
keeps parent/current compiler evidence bound. Early design-review packets carry
it and expose its actual string locations for citations. The Harmony source
construction Action explicitly enables the adapter before construction budget.

This does not modify an already enrolled experiment. Run 37243930947 remains
frozen at method e3ddce7565854296a9a43e153a62a03c46c90391 and has no new compiler
evidence injected. Future real-model experiments need a newly qualified method
and enrollment.

## Evidence and limits

A separate Rust test uses the locked real TypeScript 5.9.3 compiler, SHA-256
`3ae902c92cc44dace175c0e69e13a4b0899f6983c6121d76b9ab8dd5795e7675`.
It covers unrelated source paths, erased type imports, retained value require
calls, parse errors in read-only context, deterministic reconstruction, identity
drift rejection and top-level throwing source that is never evaluated. The Rust
CI installs the locked dependency and explicitly runs this test; normal unit tests
do not infer its prerequisite from the environment.

Successful transpilation does not resolve types, shadowed/dynamic require calls,
platform globals or transitive initialization. It does not establish an Oracle,
Agent benefit or complete automatic flywheel. Actual emitted bytes are represented
by digests here; a separate retained-output diagnostic is needed when reviewing
the detailed generated code itself.

## Concurrent older-method experiment

[Run 37243930947](https://github.com/yxsicd/agentlabrelease/actions/runs/37243930947)
finished with failure. Its original-source artifact SHA-256 is
`afcc8275eaa08850efa14005c943d0c21e45d377e8a670380a9a6640256aaee0`.
The early review used path-based source citations and actual design-string
pointers; native content binding and recorded completion passed, with opinion
`ready-for-execution`. Semantic qualification remained false.

The first generated verifier failed module initialization with `$r is not
defined`. Its single code repair added that explicit global but then failed
`non-JSON observed initial state` before scoring any check. The repaired verifier
used empty CommonBoolMapping/CommonColorMapping constructor seams; the source
mapping reads their instances' code properties. This is not preserved dependency
initialization. All attempts remain unchanged, the root is closed, and there was
no wrong-control execution, final review or knowledge commit.

This result crosses the prior citation-admission blocker but also demonstrates
why admitted pre-execution opinions are not runtime-closure proof. The new
compiler evidence was not part of that frozen method and cannot retroactively
qualify it or, on its own, fix these runtime bindings.
