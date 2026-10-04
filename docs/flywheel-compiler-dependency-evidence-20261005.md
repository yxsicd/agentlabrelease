# Retained compiler dependency checkpoint

This checkpoint records a source-bound diagnostic, not an accepted design,
executed verifier, platform qualification or complete flywheel round.

## Evidence identity

The retained input came from original-source artifact of Action run
[37241175488](https://github.com/yxsicd/agentlabrelease/actions/runs/37241175488).
Its ZIP SHA-256 is
`9ca9a13d11d8ae8b281ea2b428abf7b227077969c0458fc2edbc6a0151844e49`.
The design-review request packet SHA-256 is
`a3b7e0bb85adf7a82359fcda4a1a8f58be925418e077b0fc059651751c15e4ac`.

Source path:
`features/componentlibrary/src/main/ets/componentdetailview/toggleview/viewmodel/ToggleCodeGenerator.ets`.
Source SHA-256:
`4b70bddfae046612e24f0cf73aeb8f58a6be444d41a90146ddfa9377be59c245`.

TypeScript 5.9.3 was taken from the dependency version already pinned in the
subject runtime lockfile. Its compiler JavaScript SHA-256 matches the frozen
runtime policy:
`3ae902c92cc44dace175c0e69e13a4b0899f6983c6121d76b9ab8dd5795e7675`.
The diagnostic used `transpileModule`, CommonJS, ES2020, diagnostics enabled and
the runtime's `.ets` to `.ts` filename mapping. AST inspection of emitted
JavaScript found two require specifiers:

- `../entity/ToggleAttributeMapping`
- `../../common/entity/CommonMapData`

There were no compiler error diagnostics. Emitted JavaScript SHA-256:
`180580324e22fde4ac1945d953dbed398ceee42a7fea0a08e455e6a28a73497c`.
The diagnostic process exited 0 and retained its full emitted output and receipt
in the experiment's separate compiler-inspection artifact directory.

## Decision changed, qualifications unchanged

`OriginAttribute` and `CommonCodeGenerator` appear in the source as type/interface
dependencies but not as emitted runtime imports under these exact options.
Missing their implementation context alone therefore does not establish an
unbound runtime import. This observation does not resolve their types.

The value dependencies still need runtime closure. Static inspection found
top-level enum references and a resource call in mapping initialization; resource
syntax in generated output strings is a separate observable, not necessarily an
executed call. Explicit import/global bindings and actual module execution remain
required before a host-runtime closure claim.

No type checking or source execution was performed by this diagnostic. No
historical reviewer response was changed or admitted. The separately running
experiment 37242417061 was already enrolled and did not receive this new evidence.
Future construction should bind compiler-emitted evidence prospectively, rather
than treating this checkpoint as an implemented producer capability.

## Subsequent experiment outcome

Run 37242417061 subsequently ended in failure at the native design-review
completion gate: `design quality criterion citation differs`. Its retained
original-source ZIP SHA-256 is
`9b03f48f9190734ebf75d30a1f0c57ce86757e88dd85dc5cabc6d2f6a9b08f9f`.
The response had the correct seven root fields. Two criterion citations pointed
to source index 48 although their exact quotes occur at source index 45; a third
pointed to originalRequestUtf8 although its exact quote occurs at design
limitations index 3. The original response remains unchanged and unadmitted.
No verifier execution or knowledge return followed. This identifies evidence
location reliability as a separate next-action gap; it does not contradict the
compiler finding or make the reviewer's unadmitted opinions accepted findings.

The prospective native interface now also accepts criterion source citations as
exact path/quote pairs, using the same unique-source content check as item reviews.
Existing pointer/quote citations remain strict. The prompt's location-only catalog
now includes design strings, including limitations, with correctly escaped JSON
pointers. No historical response is converted to the new form. Rust regressions
cover reordered source context, duplicate paths, wrong paths/quotes, read-only
context and design-pointer escaping; real model reliability remains unverified.
