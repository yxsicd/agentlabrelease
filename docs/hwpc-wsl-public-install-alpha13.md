# hwpc WSL2 public-install evidence for v0.1.0-alpha.13

This record describes a consumer-side installation and deployment smoke of
the published `v0.1.0-alpha.13` release on the `hwpc` evidence host. The host
name is an evidence label, not an installation selector or product
requirement.

## Result

The second, corrected run passed on 2026-09-27. It downloaded the four
aggregate GitHub Release files, verified every checksum in `SHA256SUMS`,
checked out the exact release tag, materialized its immutable component
closure, installed the selected Docker composition, and completed the public
SessionFS/Harmony project smoke.

- release tag: `v0.1.0-alpha.13`
- tag commit: `635701706b45dd083539ebf329f79d0379aacd8a`
- aggregate closure: 14 selected components and 22 referenced assets
- rebuilt/re-uploaded component payloads: 0/0
- installed environment-lock SHA-256:
  `dcb27623ef9f3f5a92c0eb759120989cafcf25ace8873945a043242cb41fd1eb`
- installed composition source revision:
  `24fb4ec0beaff395b790bf4d1678f7f2a9c76a3c`
- total scheduled validation: 316,953 ms
- public smoke body: 315,654 ms
- composition fetch: 144,184 ms
- Docker composition install: 124,656 ms

All ten checks in `agentlab.public_install_deploy_smoke.v1` passed:

- aggregate admission and component download;
- Docker composition installation;
- standalone SessionFS and Harmony service deployment;
- project creation and verification;
- task fork, child patch, and parent isolation.

The host had seven unrelated containers before the run and the same seven
container rows after it. There was no container-list diff. The bounded smoke
cleaned up its own processes and released TCP ports 19731 and 19780.

The retained operator evidence is under:

```text
D:\agentlab-validation\v0.1.0-alpha.13-hwpc-20260927-run1
D:\agentlab-validation\v0.1.0-alpha.13-hwpc-20260927-run2
```

The first directory is intentionally retained because it contains useful
failed-attempt evidence. The second contains the passing receipts, aggregate
files, logs, timing table, install receipts, and before/after container lists.

## Host observations

The consumer environment was Ubuntu 24.04.4 under WSL2 on x86-64, with 10
virtual CPUs, about 39 GiB memory, 17 GiB swap, and about 969 GB initially
available in the WSL filesystem. Docker client and server 29.1.3 were healthy.
The user belonged to both the `docker` and `kvm` groups, and `/dev/kvm` was
present and accessible. `/dev/dri/renderD128` and `/dev/dri/card0` were not
present.

`zstd` was initially missing. Installing Ubuntu's Zstandard CLI 1.5.5 took
12,266 ms; the following prerequisite replay observed it and completed in 4
ms. This package was needed by the repository's full public smoke because that
flow also expands the separately pinned standalone Harmony archive. It does
not change the narrower base-install contract for a pre-provisioned
`agentlabctl`, which performs its own zstd extraction.

## Reusable WSL control pattern

The AWMCP manager on this Windows host runs as LocalSystem. Calling `wsl.exe`
directly from that account fails with `WSL_E_LOCAL_SYSTEM_NOT_SUPPORTED`, even
though the user's WSL distribution is healthy. The working control path was:

1. resolve the active console user (`HWPC\yxsicd`);
2. register a transient Scheduled Task for that user with `Interactive` logon
   type and highest run level;
3. have the task invoke `wsl.exe -d Ubuntu-24.04 --exec /bin/bash`;
4. keep complex Bash in a standalone `.sh` file on the mounted `D:` drive;
5. write primary evidence from Bash directly as UTF-8;
6. poll the Scheduled Task and read durable receipts rather than treating task
   launch as completion proof;
7. remove the transient task definition after evidence collection.

Avoid passing a complex `bash -lc` program inline through PowerShell and
`wsl.exe`; quoting was corrupted during the preflight attempts. Also avoid
using PowerShell redirection as the authoritative Linux evidence stream: it
can produce UTF-16 or mixed-encoding output. Wrapper stdout/stderr is still
useful diagnostic evidence, but JSON receipts and primary logs should be
written by the Linux process.

## Aggregate schema lesson

The first install run stopped before materialization because its local
admission snippet assumed old field names. In the alpha.13 aggregate format:

- the closure uses `releaseTag`, not `tag`;
- the immutable tag commit is `qualification.tagGitSha` and
  `publication.tagGitSha`, not `release-closure.tagCommit`;
- the closure has a flat 22-row `assets` array;
- selected component count is recorded in `closure.reuse` and publication;
- qualification status is
  `qualified-developer-preview-review-required`;
- publication status is `prepared-review-required`.

Consumers should validate the declared `schema` before selecting fields. They
must not infer publication readiness from a filename or translate a review
boundary into automatic promotion.

## Qualification boundary

This run proves public aggregate acquisition, immutable identity checks,
Docker composition installation, analysis of the installed graph, and the
standalone SessionFS/Harmony project workflow on WSL2. It does not prove a
Harmony emulator boot or graphics acceleration on this host. KVM is available,
but the missing `/dev/dri` render node means emulator display/GPU behavior must
be qualified separately. It also does not establish absolute device power or
thermal authority, and automatic promotion remains disabled.
