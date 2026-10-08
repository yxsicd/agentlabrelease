# Version-independent AgentLab uninstall

This procedure applies even when an old installer, registry or receipt is missing.
It does not require running or supporting the old version. It never assumes an
instance prefix, volume prefix, installation directory or Compose project name
is proof of exclusive ownership.

## 1. Discover without mutation

Run the public read-only inventory:

```bash
bash scripts/agentlab-resource-inventory.sh
```

It emits JSONL Docker identity/mount metadata, not environment variables or raw
configuration. Store its output privately. Inspect operator-selected installation
roots, startup services and processes separately; there is no recursive home or
whole-disk scan. Paths are evidence locations, never permission to delete them.

For each candidate, reconcile receipt/configuration, immutable binary or image
identity, Compose labels, process command and mounted data. Names are hints only.
Missing or conflicting ownership leaves the resource `unknown`, not removable.
Classify:

- instance-owned processes/containers and startup/recovery rules;
- durable data: projects, workspaces, knowledge, Agent context, configuration,
  MCPGit state, SessionFS images/snapshots/exports and logs;
- immutable program/tool/SDK/emulator supply and caches, possibly shared;
- external or shared dependencies, including other AgentLab instances;
- sensitive credentials and backups, kept private even after uninstall.

Docker inventory does not discover native systemd units, WSL startup commands,
host loop/mount references or containers in another Docker context. Explicitly
check those relevant surfaces before declaring the inventory complete.

## 2. Produce an exact plan

List full container IDs, image identities, unit/process identities, exact paths
and named volumes; explain ownership for each. Join **all** container mounts,
including stopped containers, and native mount/loop/process references. A volume
with another consumer remains shared. A name-matching but unattached volume
remains unknown unless independent ownership evidence identifies it.

Default plan: remove only selected owned execution/startup resources; retain all
durable data, credentials, backups and immutable/shared supply. Do not upgrade or
migrate historical data as part of removal. Retain a private rollback record.

## 3. Execute the reviewed scope

Disable only the selected startup/recovery rules, then stop its processes. For
each Docker container, recheck its full ID, image and state immediately before
removal; use `docker stop <full-id>` and `docker rm <full-id>` **without `-v`**.
Do not use broad prune, Compose `down -v`, image purge or recursive deletion of
an installation root. Do not stop a shared MCPGit/SessionFS service.

For native SessionFS, quiesce the exact owning instance first and inspect mounted
exports and loop devices. An image file may still be live after its Docker
container has stopped. Do not delete/unmount/detach a referenced image or a
shared filesystem merely because the instance name matches.

## 4. Optional purge, separate from uninstall

Require explicit data-purge authorization and an exact data set. Back up selected
data privately, preserving sparse files, modes, symlinks, owners, ACLs and xattrs;
verify archive readability and checksums, and record the restore procedure.
Recheck all consumers/mounts/loops immediately before exact resource removal.
Unknown references, failed backup or changed identity stops the purge.

Do not run installation and retirement concurrently: new dependency volumes can
invalidate before/after footprint comparisons. Secrets and data archives never
become public GitHub evidence.

## 5. Verify independently

Prove selected processes/containers/startup rules no longer run, default-retained
data still exists, and protected/shared resources retain their identities and
health. For authorized purge, reconcile exact removed and retained resource sets;
unexpected deltas fail acceptance. Report what was removed, what remains, where
private recovery material is kept, and whether recovery was actually tested.
