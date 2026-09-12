# Real Code Agent acceptance

The manual **Real Code Agent acceptance** workflow runs trusted `main` with Pi
0.73.1 and the LM Gateway model selected at dispatch (default `glm-5.3-flash`).
Set `AGENTLAB_LM_GATEWAY_KEY` as an Actions Secret and optionally set repository
variable `AGENTLAB_LM_GATEWAY_URL`. This workflow does not run PR code.

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
