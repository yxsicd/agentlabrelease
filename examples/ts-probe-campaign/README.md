# TypeScript probe campaign

The release asset `agentlab-ts-probe-v0.1.0-alpha.1.tar.zst` contains the
deterministic external-brain source package used to validate LLM, MCP, trace,
activation, budget, and fork boundaries without depending on a real Code Agent.

After extracting it on a machine with Bun:

```bash
bun install --frozen-lockfile
bun test
```

The ordinary prompt loop accepts the LM Gateway and MCP Gateway endpoints from
environment variables documented in the packaged README. Do not place real
keys in fixtures or commit them with campaign evidence.
