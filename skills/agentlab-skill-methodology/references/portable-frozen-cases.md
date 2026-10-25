# Portable frozen cases

Use the maintained offline `scripts/git_patch_bundle.py` and `scripts/restore_retained_case.py`. Their mechanical implementations were promoted unchanged from the existing checkpoint/Fork workflow. Git and Python3 standard library suffice for selected-code restoration; no platform source checkout, SDK or Agent runtime is required. These helpers grant no Host/Owner/Session authority.

Capture admitted selected files against an exact locally available Git base. Preserve a shared base bundle plus per-point binary-safe Git patches and trusted manifests. Keep the formal native Fork, original operation/request binding, workspace checkpoint and owning artifact-readback revision distinct. Read actual final bytes from the exact authenticated immutable artifact revision; never replace it with moving HEAD or the latest Session state. Small binary source assets belong to code and must be byte-verified, not UTF8-decoded or confused with screenshots. Exclude build outputs, SDK/cache and Agent context from this selected semantic profile.

A private case can contain raw compressed facts, the original frozen task and private oracle, model/Agent/native thinking/budget/environment receipts, assistance audit and system/teacher reviews in controller assets. The restore helper verifies the separately trusted case digest, member digests, point manifest and target Git tree before exposing the declared logical paths. Controller assets and the oracle remain outside the restored participant workspace. Only the clean seed is an independent comparison start; retained poststates may inherit work and must be labeled accordingly.

```sh
python3 scripts/git_patch_bundle.py capture --repo ADMITTED_LOCAL_REPO \
  --repository-id REGISTERED_CODE_ID --output NEW_POINT_DIRECTORY
python3 scripts/restore_retained_case.py --package PRIVATE_CASE_DIRECTORY \
  --point POINT_NAME --destination NEW_DESTINATION \
  --trusted-case-sha256 EXTERNALLY_RETAINED_CASE_SHA256
```

Never self-read an untrusted case digest as its own authorization. Preserve partial output after rejection; inspect it before any new generation. Verify the SAME archive on both machines, matching target Git trees and actual selected-file hashes. Report archive bytes, shared base, patch bytes and evidence separately. This is selected-code/evidence semantic restoration, not whole Capsule, SDK/device state, fresh-agent execution or a new functional pass.

Use the existing `enrich-process-audit.py --frozen-reviews ...` report mode after independent original-operation qualification. It validates metric operation/session/request/checkpoint binding and complete trace results, retains native cache/input/output/reasoning fields without double counting, and never turns tool flags into global useful-call rate or billing. Publish only allowlisted projections; raw native traces, private oracles and portable private archives never enter public Pages. Native high is an Agent setting; disclose any unaudited upstream effort and unexposed vendor weight revision.
