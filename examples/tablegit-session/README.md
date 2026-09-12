# Create and recover a real TableGit Session

First [install the composition](../README.md#install-the-referenced-components).
Then, from the repository root:

```bash
python3 examples/tablegit-session/run.py \
  --image chatproxy-agentlab:git-fa05788f-linux-x64 \
  --runtime-volume vol-agentlab-pack-agentlab-release-26008e36-linux-x64-5ba5d112eec0 \
  --root "$HOME/agentlab-demo/tablegit"
```

The example creates an isolated Docker network, MCPGit Gateway and organization,
and empty repositories with a disposable test operator. `fixture.py` seeds only
infrastructure repositories and this test identity. AgentLab's business tables,
Session binding, operation pre-state, Lease and projection state are created by
the **released `agentlab-mcpgit-template-probe`**, using AgentLab's production
provisioner and the normal MCPGit Service SDK.

MCPGit is independently downloaded from its original immutable release and
verified using [`mcpgit-program.json`](../../release/ci/mcpgit-program.json).
No MCPGit source or implementation of AgentLab business tables is added here.

The workflow bootstraps and qualifies the runtime's actual template inventory,
creates the same logical Session through concurrent provisioner calls, verifies
the committed binding and Lease, removes the generated local projection, then
restarts both MCPGit processes. A fresh process reconstructs the Session and
checks the exact materialized revision, file digest, Lease revision and
structured projection state against the first receipt.

Read `template-lock.json`, `qualification.json`, `session-created.json` and
`session-recovered.json` in the generated `evidence-*` directory. They contain
the actual repository IDs, table definitions, revision fences and readback
results. Failed commands retain full stdout/stderr. The run removes only its
own named containers, volume and network. `state-*` contains disposable service
credentials and is deliberately outside the CI artifact paths.

This is a Session **control/state recovery** demo. It does not execute an Agent
turn, run LLM/MCP Gateway observation capture or prove a mature SessionFS binary
snapshot. Those need the complete Harness campaign; see the explicit
[coverage boundary](../README.md#coverage-boundary).
