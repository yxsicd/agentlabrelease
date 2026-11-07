# Create and recover a real TableGit Session

First [install the composition](../README.md#install-the-referenced-components).
Install the small Service readiness client dependency with
`sudo apt-get install python3-websocket`.
Then, from the repository root:

```bash
/usr/bin/python3 examples/tablegit-session/run.py \
  --image chatproxy-agentlab:git-fa05788f-linux-x64 \
  --runtime-volume vol-agentlab-pack-agentlab-release-c22b7bfd-linux-x64-f5605170494f \
  --root "$HOME/agentlab-demo/tablegit"
```

The example creates an isolated Docker network, MCPGit Gateway and organization,
and empty repositories with a disposable test operator. `fixture.py` seeds only
infrastructure repositories and this test identity. AgentLab's business tables,
Session binding, operation pre-state, Lease and projection state are created by
the **independently released Session SDK program**, using AgentLab's production
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

When the original capture has a separately retained trustworthy exchange
count, add `--audit-gateway-exchanges N`. New operator-owned Participant runs
automatically write `gateway-capture-inventory.json` on shutdown; when its
producer count is complete, this example uses that count automatically. An
incomplete or invalid inventory is a capture problem, not a student failure;
older captures without this file remain supported and unqualified by this
additional check. After the actual committed-revision
Service readback and storage restart, it checks that the original and recovered
gateway request, forwarded request, response and status files for each of the
N exchanges have identical lengths and SHA-256 digests. It preserves a
`gateway-byte-audit.json` receipt and refuses a mismatch. This opt-in check is
in addition to existing exact-row and full-inventory recovery, and is not a
pre-dispatch admission check or proof of complete provider-wire capture.
Standalone `scripts/audit-llm-capture.py` is a private byte audit only: even
matching local directories cannot prove their origin or TableGit authority.

The current demo uses source observation and payload chunk rows. It does not
qualify a single-record history layout. Compare alternative layouts using the
same inputs and exact readback rather than assuming either is smaller or faster.

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

The SDK program is selected by `release/ci/session-sdk.json`, independently of
the runtime pack. The same resolved Session Binding selects capture writes and
history export. The demo checks all46 Session/12 Owner definitions and their
schema inventory digest, so an older helper cannot silently qualify the new candidate.

`contractDigest` identifies a deployment lock including repository IDs and exact
commits. It is qualified within that environment. `templateInventoryDigest`
identifies only sorted table paths and definitions, so new repositories can
use the same schemas without a false cross-environment mismatch. The complete
portable inventory is published at `release/ci/session-template-inventory.json`.
