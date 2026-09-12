# Discover and call a published AgentLab service

```bash
python3 examples/run.py protocol --root "$HOME/agentlab-demo/protocol"
```

The runner downloads the immutable runtime declared in
[`harness-runtime.json`](../../release/ci/harness-runtime.json), verifies its
size/SHA-256, and starts the released `chat-rs`. The demo has a deterministic
Mock backend and an unavailable backend, making success and degradation
repeatable without a paid model. It creates no AgentLab storage Session.

The tested consumer flow is:

1. GET the root `SKILL.md` without credentials.
2. Parse its YAML frontmatter and follow the explicit `service-manifest` URI.
3. Resolve HTTP, MCP, catalog, profile and quickstart relative to the manifest
   document URL, preserving every proxy path segment.
4. With separate authorization, initialize MCP, notify initialized, list tools,
   invoke status/catalog/backend tools and compare with their HTTP counterparts.
5. Exercise write/operation mappings against unavailable storage and verify
   that HTTP and MCP return the same failure. This is not write-success proof.

`verify.py` repeats the flow directly, behind one proxy, behind two serial
proxies, and with a relocated `a/b/custom-manifest.json` and CRLF frontmatter.
It checks catalog navigation, LF/CRLF parsing, missing/invalid discovery data,
unsupported versions, safe YAML and cross-origin authorization handling.
Discovery requests have no credentials and no fallback manifest path is guessed.

For your own service, the consumer itself needs only the SKILL URL:

```bash
python3 examples/service-protocol/client.py --skill-url "$AGENTLAB_SKILL_URL"
# Set AGENTLAB_AUTHORIZATION independently in your environment, then repeat
# the command for the authenticated MCP/HTTP comparison.
```

The demo directory contains `evidence/protocol-*/summary.json`, `run.json`,
the daemon log, and each numbered request, response body and HTTP status.
Test bodies are retained in full. Authentication headers are represented by
an `authorized` flag; real credentials are not included in these artifacts.
