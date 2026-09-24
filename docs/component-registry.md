# Immutable component registry and aggregate releases

AgentLab publishes a component only when its effective build input changes.
An aggregate version selects already-published immutable components; it does
not copy or rebuild their payloads.

`release/components/registry.json` is the current machine-readable inventory.
Every entry binds an immutable Release tag, exact asset bytes and SHA-256,
source provenance, and an input identity. A source commit is retained for
audit, but a monorepo commit alone is not the rebuild key.

Three input modes are supported:

- `git-tree-v1` hashes the Git object IDs for the component's owned source
  paths and build-recipe paths together with declared dependency identities.
  A commit that changes only unrelated paths therefore reuses the component.
- `external-payload-v1` treats exact externally supplied payload identities as
  the input. The two Harmony emulator archives use this mode.
- `legacy-published-v1` preserves an already-published component by exact
  bytes/SHA while its source-path and build-recipe ownership is migrated. It
  is reusable, but does not claim an automatic source-impact decision.

Run:

```sh
python3 scripts/component-reuse.py validate \
  --registry release/components/registry.json

python3 scripts/component-reuse.py plan \
  --registry release/components/registry.json \
  --component <component-id> \
  --repo <source-checkout> --revision <commit>
```

The planner returns `reuse` only when the effective input digest is unchanged;
otherwise it returns `rebuild`. Build recipes and dependency identities are
part of the digest, so a path-only optimization cannot silently reuse a stale
binary.

Aggregate closures remain immutable, small JSON documents. They reference
component assets by URL, byte count, SHA-256 and immutable tag. Promotion and
new aggregate versions may reuse those references indefinitely. A no-op
component change must not create a new component Release.
