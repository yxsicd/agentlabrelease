---
name: agentlab-harness-developer
description: Design, run, inspect, checkpoint, fork, and compare Code Agent evaluation campaigns using a released AgentLab Harness. Do not use for maintaining AgentLab source or administering production infrastructure.
---

# AgentLab Harness Developer

Use released AgentLab interfaces and receipts to evaluate replaceable Code
Agents. Never assume access to the maintenance repository or an Agent's private
session implementation.

## Start

1. Read [evaluation-model.md](references/evaluation-model.md) before defining a
   task seed or comparison matrix.
2. Read [checkpoint-and-fork.md](references/checkpoint-and-fork.md) before
   selecting fresh-Agent or native-session continuation.
3. Read [observability-and-sql.md](references/observability-and-sql.md) when
   diagnosing difficulty windows or querying captured runs.
4. Use the TypeScript probe before a real Code Agent when validating a new
   environment, capture boundary, or fork path.

## Invariants

- The Harness owns environment and workspace state; the Code Agent is a
  replaceable participant.
- Capture and restore are separate operations. A checkpoint may capture all
  observable state even when a later fork deliberately starts a fresh Agent.
- Bind every run to exact task, environment, Agent, model, adapter, and source
  identities. Do not compare labels such as `latest`.
- Preserve raw LLM and MCP/tool events as analyzable structured data. Redaction
  may remove secrets but must not turn the evidence stream into opaque
  ciphertext.
- Treat a difficulty point as an analysis result with evidence, not simply a
  failed final answer.
- Keep MCPGit and external Code Agent versions independent from AgentLab.

## Minimal qualification order

For the AIWSL preview, use the immutable alpha.4 environment kit and the fixed
`aldev` composition. Preserve one content-addressed cache across repetitions:
online and offline installation are user-selected modes over the same bytes.

```bash
mkdir -p "$HOME/.cache/agentlab/public-cas/downloads"
curl -fsSL -o /tmp/agentlab-bootstrap.sh \
  https://github.com/yxsicd/agentlabrelease/releases/download/alcontrol/agentlab-bootstrap.sh
sh /tmp/agentlab-bootstrap.sh --current --install-dir "$HOME/.local/bin"

curl -fsSL -o agentlab-aldev-environment-lock.json \
  https://github.com/yxsicd/agentlabrelease/releases/download/aldev/agentlab-aldev-environment-lock.json
curl -fsSL -o agentlab-environment-kit-v0.1.0-alpha.4.tar.zst \
  https://github.com/yxsicd/agentlabrelease/releases/download/v0.1.0-alpha.4/agentlab-environment-kit-v0.1.0-alpha.4.tar.zst
curl -fsSL -o agentlab-ts-probe-v0.1.0-alpha.4.tar.zst \
  https://github.com/yxsicd/agentlabrelease/releases/download/v0.1.0-alpha.4/agentlab-ts-probe-v0.1.0-alpha.4.tar.zst
printf '%s  %s\n' \
  c723e4d4fb9750f8c11b01dcae183e8bd718dfa9a284ae296a8b06ccb06397e9 \
  agentlab-environment-kit-v0.1.0-alpha.4.tar.zst | sha256sum -c -
printf '%s  %s\n' \
  029074b412bdaaccd069250949eec459861e685a5ef398fbbc30d4c7cbf4d2d3 \
  agentlab-ts-probe-v0.1.0-alpha.4.tar.zst | sha256sum -c -
zstd -dc agentlab-environment-kit-v0.1.0-alpha.4.tar.zst | tar -xf -
zstd -dc agentlab-ts-probe-v0.1.0-alpha.4.tar.zst | tar -xf -

agentlabctl fetch composition \
  --lock agentlab-aldev-environment-lock.json \
  --platform linux-x64 \
  --out-dir acquired-aldev \
  --cache-dir "$HOME/.cache/agentlab/public-cas"
agentlabctl composition install-docker \
  --dir acquired-aldev --platform linux-x64 \
  --receipt composition-install-receipt.json

./agentlab-environment-kit/agentlab-env qualify \
  --instance ald00 \
  --composition-receipt composition-install-receipt.json
./agentlab-environment-kit/agentlab-env install \
  --instance ald00 \
  --composition-receipt composition-install-receipt.json \
  --release-id alpha4
./agentlab-environment-kit/agentlab-env health \
  --instance ald00 \
  --composition-receipt composition-install-receipt.json
```

After the first successful acquisition, retain the lock, acquired directory,
composition receipt, extracted kit, and CAS. An offline repetition starts at
`composition install-docker`; it must not redownload large assets or contact a
package manager.

The AIWSL preview inherits the operator-owned `/share/.env` and joins it with
descriptor-owned non-secret MCPGit controller values; installation may verify
the result but must never print or synthesize secret values. A general new
deployment should know only the LLM Gateway endpoint and its gateway
credential; do not fan provider secrets out to every instance.

After health passes, retain the instance. Run the deterministic TypeScript
probe through capture, cut, fork, and continue, then use exact-revision SQL to
derive difficulty windows and the next dispatch. Require exact lineage, trace,
token/tool evidence, query revision, and result receipt. Repeat with the same
seed until recovery and query results are stable. Only then attach a fresh real
Code Agent, beginning with Codex, and compare fresh-Agent continuation before
native-session preservation.

Feed every observed installation or flywheel failure back into this Skill only
when it changes the reusable public workflow. Source-maintainer commands,
private credentials, and host-specific repair shortcuts do not belong here.
