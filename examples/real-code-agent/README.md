# Real Code Agent acceptance

The manual **Real Code Agent acceptance** workflow runs trusted `main` with Pi
0.73.1 and the LM Gateway model selected at dispatch (default `glm-5.3-flash`).
Set `AGENTLAB_LM_GATEWAY_KEY` as an Actions Secret and optionally set repository
variable `AGENTLAB_LM_GATEWAY_URL`. This workflow does not run PR code.
Choose the explicit Gateway provider route too (default `glm`). Model and provider
are separate: a bare model ID must not accidentally select the Gateway's default
provider. Evidence retains both Pi's original payload and the upstream payload
with the operator-selected `providerId`.

The runner installs the referenced AgentLab image, original Harmony SDK and
build-kit. Pi's locked npm runtime is outside the project Workspace. A control
process owns gateway forwarding and retains full request/response bodies;
external authentication stays in that process, not Pi's environment or project.

Pi edits the real ArkTS page twice using native tools. The independent compiler
builds each iteration and verifies actual HAP module, bytecode markers and
artifact identity. The operator injects invalid syntax and confirms failure;
Pi then repairs it and the compiler independently verifies recovery. Native
events, multi-turn session, prompts, actual edited files, gateway traffic,
compiler logs, reports and HAP binaries remain in the uploaded artifact.

To reproduce on Linux after installing the composition:

```sh
mkdir -p /tmp/agentlab-pi-runtime
cp examples/real-code-agent/participant/package*.json /tmp/agentlab-pi-runtime/
npm ci --prefix /tmp/agentlab-pi-runtime
# Provide AGENTLAB_LM_GATEWAY_KEY independently, without putting it in the project.
python3 examples/harmony-build/run.py \
  --install-root "$AGENTLAB_CI_ROOT" --root /tmp/agentlab-real-agent-fresh \
  --agent-bin /tmp/agentlab-pi-runtime/node_modules/.bin/pi \
  --gateway-url "$AGENTLAB_LM_GATEWAY_URL" --model glm-5.3-flash
```

This is real participant/remote-inference/native-tool/Harmony compiler
acceptance. It does not claim formal Harness TableGit persistence, SessionFS
checkpoint/Fork parity, device installation or fixed-channel promotion. A model
failure is retained and distinguished from installation/compiler failures.


## Real capture in TableGit

The same manual Action now starts the pinned disposable MCPGit Gateway/store,
uses the released AgentLab template/provisioner to create a real Session, and
imports the actual operator-captured evidence into existing
`runtime_observations` / `runtime_payload_chunks` tables. Native Pi events and
Gateway request/SSE events are individually addressable; original JSONL, SSE,
compiler logs, source and selected HAP bytes remain exactly reconstructable.
Only the evidence directory is selected: project build trees and Agent runtime
are not copied into Git. The external Gateway key is not supplied to the
TableGit step. Collection also runs after a failed model/build step so partial
or failed test data is preserved rather than discarded.

The Action restarts the real storage processes, reads every committed source row
at the capture revision, reconstructs each payload and file, and compares sizes,
hashes and inventory with the actual producer data. Inspect
`real-tablegit/evidence-*/capture-commit-manifest.json`, `capture-recovery.json`,
raw RPC requests/receipts and `recovered-capture/` in the artifact. The local
MemoryService regressions test collector logic only; the Action's MCPGit
transactions and immutable-revision reads provide real persistence evidence.

This qualifies actual CI source-data capture/recovery. The Harmony project is
the public demo project; it is not the Workspace of the provisioner fixture.
It does not establish formal production Attempt admission, SessionFS project
snapshots or normalized Sandbox/permission/causal/evaluator completeness.
Native tool reports remain observed Participant data, not trusted side effects.
Use MCPGit generic programming/analysis over the captured data; no analysis API
is introduced by this demo.

The artifact also contains `tablegit-capture.bundle` and `bundle-recovery.json`.
The collector exports the committed, service-resolved test repository before
cleanup and verifies a fresh clone has the exact capture HEAD. This preserves
TableGit rows and Git history for later restoration into an independently
configured MCPGit instance and generic programming/analysis. A failure after
partial writes still attempts repository export; transport credentials are
not part of the Git bundle. No physical execution directory is modified.
