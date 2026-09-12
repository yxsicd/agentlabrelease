# Create and recover a real TableGit Session

First [install the composition](../README.md#install-the-referenced-components).
Install the small Service readiness client dependency with
`sudo apt-get install python3-websocket`.
Then, from the repository root:

```bash
/usr/bin/python3 examples/tablegit-session/run.py \
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

Startup and restart wait for a real `repository.list` read through the
authenticated Service connection. An open port or accepted WebSocket upgrade
alone does not prove that an organization has a live storage process.

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


To also ingest actual captured source data, add
`--capture-evidence /absolute/path/to/real-agent/evidence` to the existing command.
This uses the released source-observation/chunk tables, makes bounded real
TableGit transactions, restarts storage, and reconstructs exact bytes into
`evidence-*/recovered-capture/`. The capture commit is independent from the
Workspace Lease revision: storing observations does not pretend to change the
Workspace snapshot. Selected external evidence/HAP files are retained; build
Workspace/runtime directories are not selected. This is source capture coverage,
not a claim that all normalized whitebox relations are complete.

The credential-free candidate-copy Action also ingests the actual portable Mock
campaign evidence with `--capture-agent-kind mock`, so PR validation exercises
real TableGit capture/recovery without an external LM credential. Only decisions
are mocked; the captured operator/SessionFS receipts are real observed outputs.

The artifact also contains `tablegit-capture.bundle` and `bundle-recovery.json`.
The collector exports the committed, service-resolved test repository before
cleanup and verifies a fresh clone has the exact capture HEAD. This preserves
TableGit rows and Git history for later restoration into an independently
configured MCPGit instance and generic programming/analysis. A failure after
partial writes still attempts repository export; transport credentials are
not part of the Git bundle. No physical execution directory is modified.
