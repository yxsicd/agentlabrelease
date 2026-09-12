# Run AgentLab's public verification as a demo

These commands are the commands used by [GitHub Actions](../.github/workflows/release-validation.yml).
Use a Linux x64 machine, Python 3.11+, curl, zstd and Docker. The protocol demo
also needs PyYAML (`sudo apt-get install python3-yaml`). No model subscription,
private source checkout, existing AgentLab instance, or production credentials
are required.

Start with the small protocol demo, then install the composition and run the
stateful examples. Pin this repository to the full commit you intend to test.

| Demo | What you do | What the result proves |
|---|---|---|
| [HTTP + MCP + Website Skills](service-protocol/README.md) | Discover from one SKILL URL, initialize MCP, list and call tools, compare HTTP | The published service implements its discovery and mapping contracts, including proxies and unavailable dependencies |
| [TableGit Session recovery](tablegit-session/README.md) | Bootstrap business tables, create a Session, publish Lease/projection state, restart storage, reconstruct | The released provisioner recovers the same Session, file digest and Lease from real committed TableGit data |
| [Mock Agent campaign](mock-agent/README.md) | Create a Harmony seed, Fork, edit, make a mistake, restart, correct and replay | A separate evaluator detects actual service outcomes and parent isolation, despite an optimistic participant |

The test operator controls the Harness. The Mock Agent is a replaceable
participant. A participant's success claim is retained as evidence and never
used as the evaluator's verdict. A failed Agent task can be a successful
Harness test when the independent evaluator correctly identifies the failure.

## Install the referenced components

Run from the repository root:

```bash
export AGENTLAB_CI_ROOT="$HOME/agentlab-demo/install"
export AGENTLAB_RELEASE_CHANNEL=candidate-20260912-26008e36-linux-x64
export AGENTLAB_COMPOSITION_DIR=release/candidates/26008e36-linux-x64
bash scripts/ci-public-install-deploy-smoke.sh
```

This verifies the composition lock and publication, downloads the existing
component packages, installs their Docker image/volumes, and runs a portable
Harmony/SessionFS smoke case. The SDK accounts for most download space. The
composition receipt and component identities remain under `$AGENTLAB_CI_ROOT`.
Unchanged components are referenced from their existing releases.

## Read the evidence

Each demo writes a machine-readable `summary.json` and raw service outputs.
Protocol requests and complete responses are paired by numbered filenames;
the Mock campaign records JSONL events and service receipts; TableGit recovery
records template qualification and before/after Session state. Failed runs keep
their evidence. Disposable containers are removed; installed component images,
volumes and cached downloads are retained for reuse.

GitHub Actions uploads these directories even on failure. Open a job's summary
for the tested scope, then download its artifact to inspect the original
requests, responses, exact revisions and failures.

## Coverage boundary

These examples exercise different parts of the product. They do not yet form
one public end-to-end campaign through Chat Harness, a participant, LLM/MCP
Gateway capture, TableGit and the mature SessionFS companion. The TableGit demo
uses the released provisioning SDK tool; the Mock campaign uses the standalone
storage service. Their passing results cannot be combined into a claim that
this complete chain passed.

Still separate: a real-agent SWE benchmark, complete normalized whitebox
relations, HAP compilation/device acceptance, mature SessionFS exact snapshots
with Fork/restart parity, and D/A/B/C fixed-channel promotion. CI does not alter
fixed channels or publish component packages.
