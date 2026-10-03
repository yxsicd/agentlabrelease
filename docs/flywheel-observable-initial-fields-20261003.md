# Observable initialization, not construction descriptions

Overall maturity remains 73% (engineering estimate); accepted complete automatic
business loops remain zero. This checkpoint improves source observation mechanics,
not generated-verifier semantic qualification or automated knowledge return.

PR229 merged at `f7e489741b6734708897ff6576fddc85f31f6d88` after all applicable
CI passed. [Action 37146316657](https://github.com/yxsicd/agentlabrelease/actions/runs/37146316657)
ran one fresh root at that exact revision: design-first, one design correction,
zero code repairs. It is terminal; original source and budgets remain unchanged.

## Actual result

The request-bound interface bytes and SHA256 occurred in the captured code prompt;
the exact bytes also occurred in the captured upstream request. Interface SHA256
is `47f2bdc50e0821a427c1b3f37eb3603c9dc297add2fd8ee12f4ad6ef30618e25`.
Design, correction and code completed, and independent participant isolation
passed. The validated design declared eight scenarios, 33 checks and six controls.
Both proposal source paths were loaded, and the verifier explicitly constructed
the source-exported class without duplicating control transformations. A fresh
design means these facts do not prove controlled before/after improvement.

Baseline exited 1 without timeout or check observations. It called
`assertInitialState(id, {file: packet.initialState.file}, '/file')` before creating
the instance. The helper correctly rejected an object versus a string. More
fundamentally, this was copied expected metadata, not actual source state.
The frozen initialState contained only file and construction descriptions.
No wrong controls, complete suite, recovery, semantic admission or knowledge write
executed. Original full capture remains outside Release under
flywheel-verifier-interface-adoption-i7Cyhl/capture.

## Generic change

For source instance data fields, declare concrete source-derived values in
initialState.fields, then call `assertInitialFields(scenarioId, actualInstance)`
after construction and before the tested operation. An optional RFC6901 pointer
selects another field-object subtree. The helper uses only expected field names;
observed values come from actual own data property descriptors. It rejects empty
or non-object field contracts, absent fields, accessors, non-JSON observations and
value mismatches, never assigning expected values into the instance. It returns
the observed projection for callers that need to retain evidence.

Prototype fields and getters need an explicit different source-observation adapter,
not implicit fallback. Other initialization models retain assertInitialState,
whose actual argument must have the selected subtree's shape. Keep setup metadata
in inputs, not in place of observable state. Old design schemas and entrypoints
remain valid; no historical output is rewritten or silently upgraded.

The native interface and generation guidance describe this distinction. Program
analysis Skill records the source-observation lesson without repository-specific
fields. Runtime manifests now use JSON.parse on an encoded JSON string so keys
such as __proto__ retain JSON semantics instead of object-literal prototype behavior.

## Acceptance boundary

Rust-hosted execution checks actual fresh source instances, rejection before a
mutated instance's operation, unchanged actual state, missing/inherited/accessor
fields, escaped pointers and special keys. A native-staged runtime separately
checks preserved special keys and source-derived field observations.
These prove helper mechanics, not model adoption, instance authentication,
mandatory use, complete initialization coverage or Oracle truth. A copied expected
object can still impersonate an instance; independent source review remains required.

All 48 related Rust tests passed (19 diagnostics and 29 source-operation tests),
including actual native staging/repair and historical literal diagnostic fixtures.
The new header is decoded as data only; no JavaScript evaluation is used by native
readback. Formatting, release checksums and Skill validation passed. No new model
experiment or remote knowledge write was performed in this implementation round.

Remaining: successful real adoption and complete calibrated controls, independent
semantic admission, automatic durable return and productive next-round consumption,
repeated measurable benefit, cross-repository transfer and full Harmony execution.
