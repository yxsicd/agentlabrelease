# Session-scoped scratch continuity

The calculator evaluation's ad hoc participant runner used a fresh Docker
`--tmpfs /tmp` on each container run.  Once that container exits, its `/tmp`
contents cannot be recovered from the native Agent session.  An Agent session,
its workspace and its temporary files are separate state; do not describe an
Agent-only resume as a complete filesystem restoration.

`scripts/agentlab-session-tmp.py` provides an opt-in, private same-host backing
directory for a **new** session. Its `init` creates a fresh private directory
and binds an opaque session identity; `mount` verifies the identity and emits
one argument for Docker's `--mount`. Pass that output as one argv element; do
not evaluate it as shell. The launcher must reuse this same backing store for
the exact session, ensure no other writer is active, and record its policy and
identity in the operator-side receipt. Do not mount it into another Attempt.

The backing directory has owner-only traversal, while the container-visible
scratch directory has sticky `1777` permissions. Contents may include secrets,
screenshots, cache and student files: keep them private, apply a storage quota
and the task retention policy, and remove only after the session is closed and
its evidence has been captured. Unlike the previous size-limited `tmpfs`, this
bind mount is backed by disk and does **not** automatically provide tmpfs
`nosuid`, `nodev`, `noexec`, size limits, or a portable snapshot. The operator
must verify the host mount and container security policy and provision a quota;
this helper does not enforce them. It does not manage ownership locks, restore
old vanished data, produce SessionFS checkpoints, or prove cross-host recovery.

The calculator H01 temporary directory already disappeared. The preserved event
stream can support a separately labeled, partial reconstruction of selected
files, but it is not evidence of a complete or byte-exact `/tmp` snapshot.
Any such restoration must be recorded as Harness activity, with missing state
and uncertainty disclosed to the student rather than counted as teacher help.
No test result is implied by creating a mount.
