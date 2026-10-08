# Portable deployment and component lifecycle

## Consumer contract

GitHub is the only distribution authority. AWMCP is a maintainer's validation
control channel, never a consumer prerequisite. A consumer must not need a
particular hostname, LAN, internal Git service, source checkout, or maintainer
credentials. Resolve a public snapshot once, then verify immutable asset bytes.

Linux x64 and WSL2 x64 are the current scope, not all Linux architectures.
The existing native SessionFS path additionally requires privileged loop/Btrfs
operations and systemd; Docker-only acquisition is not full Harness readiness.

Independent component publication remains mandatory: unchanged Base, Tools,
SDK and emulator assets are reused; an aggregate release references their exact
digests. Updating MCPGit must not rewrite an already published AgentLab closure.

## Selected MCPGit production integration

`release/integrations/mcpgit-prod-linux-x64.json` pins the production pointer
`offline-latest.json` at installer commit
`d32300f6953c57af1323ea71b606b363c4d99a3d`, resolving MCPGit source
`a75b9809857cea23047b61f3acea17bc09b9996c`.
The old `prod/channel.json` is not the current production authority.

The selected entrypoint is `scripts/agentlab-mcpgit-prod-install.sh`:

```sh
sh agentlab-mcpgit-prod-install.sh download --root /absolute/private/agentlab-root
sh agentlab-mcpgit-prod-install.sh check --root /absolute/private/agentlab-root
sh agentlab-mcpgit-prod-install.sh install --root /absolute/private/agentlab-root \
  --instance agentlab-mcpgit-prod --port 18095
```

Obtain this entrypoint from an exact public agentlabrelease commit and verify
its digest before execution. This candidate needs `sh`, `curl`, `python3` and,
except for download, Docker. It forces GitHub-only immutable installer/helper
URLs and the exact production release tag; it does not call GitHub API latest
discovery. Repeat `install` delegates to upstream's verified update planner and
preserves the instance's dedicated data volume. The corrected installer also
reuses a qualified unchanged healthy activation without replacing its container;
changed configuration/credentials/route or unqualified activation requires a
separate activation and receipt. Credentials, configuration,
bundle, tools and receipts stay under the selected private root. No historical
volume is attached or migrated automatically; shared MCPGit services are not
upgraded by this entrypoint. `check` downloads and writes private planning state;
it is not a zero-footprint probe.

This does not yet provide unified full-Harness CRUD or prove compatibility with
AgentLab's person, skill-table, repository and session/fork protocols. Do not
promote the aggregate release solely because MCPGit's health endpoint succeeds.

## Required unified lifecycle

The native controller should own one instance/component registry and expose:

| Operation | Required acceptance |
| --- | --- |
| list / inspect | Real installed identity, desired digest, ownership and all references |
| add / install | GitHub acquisition, checksum verification, dependency plan, readiness receipt |
| update / upgrade | Only changed artifacts, preserved data, compatibility gates and rollback |
| delete / uninstall | Exact ownership, no surviving references, preserve data by default |
| explicit data purge | Separate opt-in, recoverable backup, exact post-delete resource delta |
| repair / rollback | Transaction receipt, last accepted cut and no unrelated resource mutation |

Implement this in the existing Rust controller rather than introducing a second
Python deployment engine. The public release repository currently distributes
controller bytes; its source-of-truth controller lives in the maintenance
workspace. Component acquisition, runtime deployment, protocol acceptance,
SessionFS readiness and Harmony emulator execution are independent gates.

## Two-host retirement evidence, 2026-10-08

Direct human authorization covers historical AgentLab instances and dedicated
data volumes on hwlinux and aiwsl only. Running instances, their references,
shared services and ambiguous resources remain protected. No broad prune,
image purge, network deletion or historical data migration is permitted here.

Each selected stopped container is fenced by its full ID/name/image/state and
ownership evidence, saved via a private `docker commit` rollback image, then
removed without `-v`. Each dedicated volume is rechecked for Docker and host
loop/mount references, archived with sparse/ACL/xattr/numeric-owner preservation,
listed successfully and SHA-256 recorded before exact volume removal.
Sensitive inspect/environment/configuration and data archives stay private on
their original host, never in Git or an uploaded release.

| Host | Container retirement | Volume retirement | Evidence |
| --- | --- | --- | --- |
| hwlinux | 53 removed, recoverable images retained | 71 removed, verified private archives retained | Exact volume delta and protected container identity/state passed |
| aiwsl | 14 removed, recoverable images retained | 152 removed, verified private archives retained, including the old 64 GiB volume | Initial large-volume delta check failed; independent inventory/install reconciliation passed |

Receipts are under the logged-in user's
`.local/share/agentlab/deployment-validation-20261008/` on each host. These are
maintenance receipts, not a required product path or host dependency. Retained
backups mean deletion does not immediately reclaim all archive/image space.
Active native loop files outside Docker volumes are deliberately not deleted.

Initial public probes exposed a missing expected-manifest digest in the new
MCPGit wrapper; it is now passed explicitly to upstream's immutable-tag guard.
The historical composition installer requires Bash: invoking it with `sh`
fails before installation (`pipefail` is not portable to `/bin/sh`). Preserve
that failed probe separately and retry the documented Bash entrypoint.

The corrected public probes completed on both hosts: MCPGit download, first
install, repeat install, status, doctor, HTTP 204 and read-only Agent onboarding
(eight kernel tools, authenticated identity, scoped repository read and offline
WAsmC discovery) all passed. The pinned historical composition installer also
completed with Bash. This installs four component volumes and the runtime image;
it does not start or qualify the full Harness or execute the emulator.
See [the sanitized two-host receipt](evidence/portable-deployment-20261008.json).

The old 64 GiB aiwsl volume was backed up and SHA-256 verified before removal.
Its first strict volume-delta assertion exited 1 because concurrent authorized
composition installation created/recreated dependency volumes. That failure is
preserved. A separate check against the original volume identities, exact retired
set and installation receipts passed: no unapproved missing/added volume,
protected volume identity change or protected container state/identity change.
Future retirement and installation footprint measurements must be serialized.

The adopted Harmony SDK descriptor and archive match on both hosts, including
portable manifest digest `7d01f01c45f328c772ebf0771c2478fcefeedcdab13b54658b0a9464358e3532`.
Installed `manifestSha256` differs; it is not the descriptor's portable identity
and its local provenance remains unclassified. The generic native `pack inspect`
path exits 1 (`manifest.json must be first`) on this adopted historical archive,
whereas the descriptor-aware composition installation passed. Preserve that
unsupported-path receipt without misclassifying it as a failed SDK install.

## Next acceptance gates

1. The pinned candidate's isolated download/install/repeat-install and read-only
   MCP kernel gates passed on both hosts. Next exercise AgentLab session-template,
   checkpoint and fork contracts against this exact MCPGit revision.
2. Select a successor aggregate composition referencing these verified layers;
   do not mutate alpha.15 or its historical mirrors.
3. Extend the Rust controller's component inventory/CRUD/upgrade/uninstall flow,
   including untracked resources, failure recovery and data purge receipts.
4. Run install → inspect → repeat install → changed-component upgrade → rollback
   → uninstall/preserve → explicit purge on both hosts without local artifacts.
5. Independently qualify SessionFS and Harmony emulator deployment/execution.

Flywheel maturity remains the prior 82% estimate, +0 for this deployment work;
no end-to-end flywheel evidence was produced in this stage.
