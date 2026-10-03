# Request-bound verifier interface

Overall maturity remains 73% (engineering estimate); accepted complete automatic
business loops remain zero. This removes conflicting guidance and adds a native
interface artifact; real Agent adoption and productive feedback remain unproven.

PR228 merged at `6cb0e507510c4f13ed60e65adcefb71ff2734d05` after all applicable
CI passed. No failed construction's source, contract or budget was rewritten.

## Why this change

Real generation repeatedly confused transformed source with original source,
controlled imports with loaded bodies, module exports with instances, and packet
paths with initialState-relative pointers. The base author prompt additionally
told verifiers to transform source themselves even in design-first mode, while
the appended runtime instructions prohibited duplicate transformation. Correct
runtime APIs and more prose alone had not qualified a generated verifier.

The design-first/frozen-design prompt now selects operator transformation ownership
instead of the legacy self-transformation instruction. Legacy non-design mode
retains its original policy. No checker, source boundary or model budget is relaxed.

## Native interface artifact

`--prepare-source-verifier-interface --author-request REQUEST --design DESIGN
--output NEW_FILE` validates the ordinary live request/design contract, including
source reproduction and frozen edits, then emits
`agentlab.source_verifier_interface.v1` through create-new output semantics.
The packet binds exact request/design SHA256 and embedded runtime source SHA256.

It includes:

- sorted allowed loaded source paths from the existing request inventory;
- source/control/runtime/dependency argument positions;
- transformation ownership, CommonJS exports and pointer-base declarations;
- original ordered scenario IDs and root/top-level initialState/input pointers,
  encoded using RFC6901 escaping.

It does not include expectedObservations, checks or control edits, select which
state subtree is semantically sufficient, construct an instance, infer new
dependencies, or expand source ownership. Nested pointers remain valid even though
the convenience inventory is top-level only. Packet output is bounded to 64 KiB.
Every semantic/execution/promotion flag remains false.

The thin author transport prepares this packet after design validation and before
code generation, preserves native stdout/stderr and original packet bytes, and
puts those exact UTF-8 bytes plus their SHA256 in the code prompt. Native failure
stops before dispatching the code turn; no fallback, retry or invented receipt is
added. Design-only runs do not prepare it or invoke code generation.

## Verification boundaries

Rust regressions exercise exact request/design bindings, deterministic loaded
paths, escaped pointer keys, invalid design rejection, the actual CLI, and refusal
to overwrite an existing interface. Rust-hosted transport tests check exact packet
bytes/digest in the code prompt, preserved error streams, and no code turn after
an interface failure. These are executable interface/launcher proofs, not real
model consumption or behavioral benefit.

Next: CI-gated delivery, one bounded actual constructor using this interface,
complete independent controls/recovery, semantic admission and durable knowledge
return followed by productive next-round consumption. Multi-round benefit,
cross-repository transfer and full Harmony execution remain required.
