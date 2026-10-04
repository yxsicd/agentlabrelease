# Native reviewed-return transport bridge

Maturity remains 75%; accepted complete automatic five-stage loops remain zero.

The reviewed writer now requires lessonSourceReadback {path,sha256}, pointing to
the original agentlab.observation_store_snapshot.v1 capture. It preserves those
bytes, selects exactly the operational tables declared by the lesson export and
passes them to the new Rust --verify-lesson-source-readback CLI. Ordinary original
lesson reconstruction and strict reassessment precede complete source containment
validation. Extra archival tables remain in the original retained capture.

Optional methodSource {path,sha256} retains an exact historical method body;
neither the transport nor native hash comparison authenticates its Git revision.
No historical candidate is rewritten to the current embedded Skill.

After the one confirmed CAS, the first committed query captures a real clean
status before reading. All five complete serial query responses and final clean
status become agentlab.reviewed_lesson_committed_readback.v1. The new native
--verify-committed-lesson-return reconstructs admission again from the original
baseline/proposal/source, then compares all knowledge rows, exact portable cut
bytes and operational source rows. Strong result.json fields are emitted only
after this gate passes. The native APIs do not expose an unchecked staged-directory
return path. Both CLI gates use fresh output directories and retain a native
return-verification.json; --readback names the original capture, with optional
--method-source for exact historical bytes. The committed gate additionally takes
--committed-knowledge. Ordinary lesson admission arguments remain required.

Any failure after commit retains intent, receipt and captures; recovery must be
read-only at the confirmed revision. This implementation does not yet provide a
standalone recovery command, guidance selection, consumer publication or next-round
scheduling. Byte comparison does not authenticate the remote capture or reviewer.

The existing real-lesson integration fixture now exercises both actual Rust CLI
gates under two arbitrary repository identities, including missing source tables,
dirty knowledge brackets and truncated reads. Transport fixtures also retain the
single-write/uncertainty/complete-page regressions. Tests are pending execution;
no real endpoint or participant has been invoked by this change.
