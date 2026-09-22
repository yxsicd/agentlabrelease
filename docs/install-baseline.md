# AgentLab installation baseline

AgentLab release artifacts install on an ordinary x86_64 Linux or WSL2 host.
The release contract must not depend on an internal hostname, workspace path,
AIWSL/BlueB identity, private network, source checkout, pre-existing AgentLab
state, or publishing credentials.

## Base runtime

The only always-required host command is Docker with permission to use its
engine. A pre-provisioned `agentlabctl` is a static executable and performs
release verification and zstd extraction itself. Python, zstd, tar, Bun/Node,
Rust/Cargo, Git, and GitHub CLI are not installation prerequisites. An online
bootstrap needs either curl or wget only when the control binary is not
supplied by other media.

The host must provide at least 8 GiB memory, sufficient disk space for the
immutable artifacts and Docker volumes, and the release descriptor's free
ports. Public HTTPS is needed only while fetching artifacts. Runtime
credentials are deployment inputs, not installation prerequisites.

## Native SessionFS boundary

The current native SessionFS projection uses a loopback Btrfs filesystem and a
systemd unit. That mode additionally requires root or passwordless sudo,
systemd, loop and Btrfs kernel support, `btrfs-progs`, and the ordinary
mount/loop utilities enumerated by the target descriptor. These are real
platform requirements and are separate from the base runtime.

Removing this native boundary requires a separately qualified containerized or
pre-provisioned SessionFS implementation. Until that exists, a Docker-only
claim would be incorrect.

## Supported targets

- `generic-linux`: x86_64 Linux satisfying the base runtime and native
  SessionFS boundary.
- `wsl2`: x86_64 WSL2 with Docker engine access, systemd enabled, and the same
  native SessionFS facilities.

Machine names in qualification cases are evidence labels only; they are never
installation selectors or requirements.
