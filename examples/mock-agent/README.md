# Deterministic basic-capability campaign

`agent.py` is a fresh process on every turn. It receives preset actions from
`scenario.json`, proposes tool calls over JSONL, and consumes their results.
It intentionally claims success even when a call failed. The CI supervisor
executes the real HTTP operations, records requests/responses, controls Fork and
restart, and independently checks service receipts and actual file hashes.

The scenario creates a Harmony project seed, forks a child, modifies it, tries
an invalid edit, restarts both services, corrects the edit with a fresh Agent,
and forks the unchanged seed again. The same scenario runs on copy-tree and
real Btrfs subvolumes. No LLM credentials or Agent-specific runtime are needed.

```sh
cargo build --locked --release --workspace
python3 scripts/ci-mock-agent-smoke.py --bin-dir target/release \
  --storage /tmp/agentlab-mock-storage --evidence /tmp/agentlab-mock-evidence
```

Use fresh evidence/storage directories for each run. `--scenario` accepts a
replacement fixture for regression/fault tests. JSONL events, raw HTTP replies,
Agent output, service logs, file/binary hashes and evaluation results remain
available on success or failure. Agent output never decides the result.

This portable tier uses the published **standalone** Harmony/SessionFS services.
It does not validate full AgentLab Session/TableGit activation, LLM Gateway
capture, HAP compilation or fixed-channel qualification. The composition
installation step separately downloads and installs the selected main-runtime
package. Real-agent SWE qualification is recorded separately in the candidate
publication. These evidence scopes must remain explicit.
