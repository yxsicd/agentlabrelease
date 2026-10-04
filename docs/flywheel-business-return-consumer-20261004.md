# Native business consumption of reviewed return

Maturity remains 75%; accepted full automatic five-stage rounds remain zero.
PR276 merged as 96c1b1abc70a684b74b29c79728d6df9d6ebc5ab after all applicable
Rust, component and public workflows passed.

`--consume-reviewed-return --return-request FILE --output FRESH_ABSOLUTE_DIR`
accepts agentlab.reviewed_return_consumer_request.v1 with reviewed=true,
automaticPromotion=false, round (0..7), inputState {path,sha256} and
transportResult {path,sha256}. Original state must retain lessonAdmission but
must not already contain committedReturn; an existing return cannot be overwritten.

The input references are verified and preserved byte-exact. The consumer attaches
only the transport's existing committedReturn references in a separate input
state, then invokes ordinary native evidence-return. Producer success flags are
preconditions, not admission evidence: this gate reconsumes current-round original
capture, lesson provenance/raw reconstruction, complete source/knowledge readback
and explicit admitted guidance. Its ordinary successful transition retires old
executable inputs and retains priorRoundEvidence. Original inputs remain unchanged.

Output retains original inputs, consumer/business requests, business report/state
and consumption-receipt.json. A rejected or review-required business envelope may
still have process exit zero; inspect businessResult.status and
committedReturnConsumed. Failed reconstruction cannot advance knowledge.
The consumer performs no remote transaction, participant execution or next-round
dispatch. Returned state still requires new producer inputs rather than recycled
captures; storage reassessment is not fresh understanding or program analysis.

The behavior-lesson integration fixture exercises the actual consumer CLI through
ordinary lesson staging and business state advancement, verifies guidance/cut
binding and retirement of old inputs, then requires fresh maintenance evidence.
Dirty readback, wrong round, unreviewed input, changed reference digest and existing
return replacement are rejected. Tests are pending execution; synthetic committed
metadata is not live authority, a real participant or a successful business loop.
