# Immutable Release Graph

AgentLab separates **release identity**, **composition identity**, **control identity**, and **target qualification**. A tagged developer release must not reconstruct those identities from mutable channels at install time.

## Release closure

A tagged release uses `agentlab.release_closure.v1` as its replay authority. The closure binds:

- exact AgentLab, LLMRS and release-method source revisions;
- immutable control, composition, runtime, Harmony, MCPGit and tools assets;
- SHA-256 and byte size for every asset;
- the required control API, environment-lock, composition-receipt and component-graph schemas;
- contract generations such as `mcpgit.session-template-contract`;
- target support status.

A tagged closure must never reference `aldev`, `almain`, `alprod`, `latest` or `current` payloads. Those names are discovery/development channels, not release authority.

Assets referenced by an immutable closure are retention authority. They must not be deleted merely because a mutable channel no longer uses them.

OCI image identity is explicit: the manifest digest and config digest are different facts. A host-local Docker image ID is not a substitute for either.

## Reference-only preview composition

Create a new preview closure from an already validated closure and the current
component registry with:

```sh
python3 scripts/compose-release-closure.py \
  --base release/closures/v0.1.0-alpha.11.json \
  --registry release/components/registry.json \
  --version 0.1.0-alpha.12 \
  --release-source-revision <exact-40-character-commit> \
  --output release/closures/v0.1.0-alpha.12.json
```

The source revision must resolve to a local commit and the version must advance
the base alpha. The composer first validates the base and then selects the
complete asset set for every component represented by that base from the exact
registry. Existing asset records remain byte-for-byte unchanged. It records zero
new binary builds and uploads, publishes the bounded developer-preview scope,
and leaves automatic promotion disabled. The resulting metadata commit may
follow the source cut it describes; `sources.releaseGitSha` is the exact
implementation cut under qualification, not a self-referential digest of the
JSON commit.

“Entire asset list” means every asset of every selected component, not one
representative archive per component. Runtime, Harmony CLI, build kit, tools,
container image and SessionFS descriptors are installation inputs and must be
present beside their archives. Validation compares the closure URL set with the
complete selected registry URL set and fails if either a payload or descriptor
is omitted. `selectedComponentCount` and `reusedAssetCount` remain separate so
component reuse is not confused with file coverage.

The candidate still requires its declared CI checks, a tagged clean install and
Linux emulator acceptance before it can become a qualified developer preview.
Generating a closure does not create a tag, GitHub Release or channel promotion.

Linux emulator acceptance must be regenerated for the exact closure source cut;
an older successful campaign is not transferable. Start from a retained campaign
template and rebind every executable, the UI Oracle and the five Harmony runtime
assets to the candidate:

```sh
python3 scripts/prepare-release-harmony-acceptance.py \
  --closure release/closures/v0.1.0-alpha.12.json \
  --template-plan /retained/evidence/campaign-plan.json \
  --repository-root "$PWD" \
  --campaign-id alpha12-release-acceptance \
  --output /retained/evidence/alpha12-release-acceptance-plan.json
```

Run that plan with `run-harmony-assessed-campaign.py` under the target host's
active KVM, render and video groups. After the emulator and HDC target have been
stopped, retain cleanup evidence and validate the output:

```sh
python3 scripts/validate-release-harmony-acceptance.py \
  --closure release/closures/v0.1.0-alpha.12.json \
  --plan /retained/evidence/alpha12-release-acceptance-plan.json \
  --campaign-output /retained/evidence/alpha12-release-acceptance/campaign-output \
  --cleanup-evidence /retained/evidence/alpha12-release-acceptance/cleanup.json \
  --output /retained/evidence/alpha12-release-acceptance/acceptance.json
```

The validator requires real ohosTest/Hypium success for both variants, at least
one functional Oracle pass with valid SmartPerf proxy samples, at least one
meaningful Oracle failure whose performance collection was skipped, exact
closure/campaign digests, a direct-peer inspection trail, and zero remaining
emulator processes or HDC targets. It preserves the physical-device and
absolute-power/thermal boundary and never authorizes automatic promotion.

The Alpha.12 run against source cut `4a36510` is retained at
`release/qualifications/alpha12-harmony-acceptance-4a36510/summary.json`. It
records two source-bound ohosTest/Hypium passes, a positive UI Oracle with three
valid SmartPerf samples, a negative Oracle whose performance stage was skipped,
direct `hwlinux` peer identity, and post-run emulator/HDC cleanup. This closes
the candidate's Linux-emulator gate but not its tagged clean-install gate.

After an authorized merge and immutable tag are present, dispatch **Qualify
tagged developer preview** with the workflow ref set to that exact tag. The
workflow refuses branch refs and tag/closure mismatches, checks out full history,
validates the release graph, installs the closure on a fresh runner, and combines
the remote-asset, Harmony and clean-install evidence with:

```sh
python3 scripts/qualify-tagged-developer-preview.py \
  --closure release/closures/v0.1.0-alpha.12.json \
  --asset-receipt release/qualifications/alpha12-immutable-assets/summary.json \
  --harmony-receipt release/qualifications/alpha12-harmony-acceptance-4a36510/summary.json \
  --install-summary /fresh-runner/summary.json \
  --environment-lock /fresh-runner/closure-materialized/environment-lock.json \
  --tag v0.1.0-alpha.12 --tag-sha <exact-tag-commit> \
  --repository yxsicd/agentlabrelease --run-id <github-run-id> \
  --event workflow_dispatch --git-root "$PWD" \
  --output /fresh-runner/developer-preview-qualification.json
```

The resulting Actions artifact is the final input to release publication. It is
review-required and cannot move a channel or create a GitHub Release by itself.

Before proposing a tag, independently verify that every referenced GitHub
Release asset still exists with the closure's exact server-reported size and
SHA-256, including assets hosted by another repository:

```sh
python3 scripts/validate-release-graph.py \
  --closure release/closures/v0.1.0-alpha.12.json \
  --registry release/components/registry.json \
  --remote \
  --receipt release/qualifications/alpha12-immutable-assets/summary.json
```

Remote verification reads Release metadata and never downloads the multi-GB
emulator archives. A receipt is write-once, binds the closure and registry
digests, and records every observed GitHub asset ID, repository, tag, size and
SHA-256 without authorizing promotion.

To exercise installation from the closure rather than a mutable channel, first
materialize its small bootstrap pair:

```sh
python3 scripts/materialize-release-closure.py \
  --closure release/closures/v0.1.0-alpha.12.json \
  --registry release/components/registry.json \
  --output /tmp/agentlab-alpha12-bootstrap
```

The materializer validates the closure and registry, downloads and verifies the
environment lock and controller, and proves that every artifact and descriptor
required by the lock is in the closure. It does not download the large payloads
or promote the candidate. Public CI passes this closure to
`ci-public-install-deploy-smoke.sh`, which uses the verified bootstrap pair to
fetch, install and run the same basic use case as the channel-based lanes.

## Target descriptors

Public target descriptors live in `release/targets/`.

`generic-linux` and `wsl2` are explicit targets. `bluebwsl` is an alias of the WSL2 target and is not treated as AIWSL. WSL2 is currently **experimental** and defaults to:

- self-hosted MCPGit;
- isolated MCPGit data and SafeGit credentials;
- loopback-only initial exposure;
- explicit host dependency, memory and port preflight;
- independent SessionFS lifecycle;
- ordered MCPGit -> SafeGit -> SessionFS -> main-runtime deployment;
- cold/Docker/WSL restart qualification.

A target becomes `qualified` only after those gates pass against the exact immutable release closure.

## Compatibility before install

Installation begins with a compatibility handshake, not download or mutation. The control must prove it understands the closure's lock, receipt and component-graph schemas before acquisition starts. Unknown schema generations fail closed with the exact unsupported identity.

The normal lifecycle is:

```text
install-plan -> qualify -> install -> layered health -> rollback
```

Layered health is stronger than a single process `/health`; target metadata enumerates the dependency planes that must be checked.

## Historical BlueB regressions

Public release validation permanently covers the failure classes discovered by the BlueB deployment:

1. mutable-channel dependency from a tagged release;
2. controller/receipt schema drift discovered only during deployment;
3. deletion of an immutable historical asset;
4. ambiguous Docker/OCI image identity.

These are release-system failures, not one-off deployment quirks. New release tooling must keep them fail-closed.
