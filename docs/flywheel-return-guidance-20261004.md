# Reviewed guidance after committed return

Overall maturity stays 75%; complete automatic five-stage accepted loops stay zero.

PR275 merged as a1ab68ef8788d578bdbcc8f375e981b67f86af9d after all applicable
Rust, component and public validation checks succeeded. Its complete thin transport
fixture invoked both native gates across two arbitrary source repositories.
This checkpoint extends that bridge, not a real authority or participant run.

The request may supply nextGuidanceIntent {path,sha256}. The referenced JSON uses
agentlab.reviewed_guidance_continuation.v1 with reviewed=true,
automaticPromotion=false, baselineKnowledgeCutSha256, baselineKnowledgeRevision,
stage, sources and skills. Sources and choices use the ordinary fixed-cut guidance
selection contract, including exact rowSha256/objectId/applicabilityReason.
Optional sourceRecipeTarget is retained for the existing later author-target gate;
this continuation does not establish target-source loading or execution.

The original baseline identity is verified and the newly admitted Skill must be
explicitly selected. Before any remote discovery/write, original lesson admission
is reconstructed and every choice is validated through the ordinary guidance
row/fact/source/method checks against that reviewed stage. The internal staged
preview is discarded: it is not an exported committed guidance packet.

After complete committed-return reconstruction and exact readback comparison,
the same intent produces a normal guidance selection bound to the actual new cut
digest/revision. Ordinary committed guidance binding runs again. The CLI writes
guidance-selection.json and guidance-packet.json with exact compact bytes in its
fresh return directory; result.json retains their paths/digests and reports
nextGuidanceBound. It never invents applicability reasons or changes selected
rows to follow a newer revision. No intent means no automatic guidance selection.

The full transport integration fixture now covers committed selection/packet
binding and rejects unreviewed intent, stale baseline, wrong row hash, missing
admitted Skill, wrong stage and borrowed source before any MCP call. These tests
are pending execution. They do not demonstrate fresh repository understanding,
real knowledge return, model consumption, consumer publication, automatic next-round
scheduling, semantic review authentication or learning benefit.
