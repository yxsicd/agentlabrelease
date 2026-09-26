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
  --base release/closures/v0.1.0-alpha.12.json \
  --registry release/components/registry.json \
  --version 0.1.0-alpha.13 \
  --release-source-revision <exact-40-character-commit> \
  --output release/closures/v0.1.0-alpha.13.json
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

Every current-candidate CI validation supplies `--git-root`. The validator
requires that full source SHA to resolve to an exact commit in the checkout and
to be an ancestor of the metadata/tag checkout. A syntactically valid but
invented 40-hex value therefore cannot pass release validation again.

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
  --closure release/closures/v0.1.0-alpha.13.json \
  --template-plan /retained/evidence/campaign-plan.json \
  --repository-root "$PWD" \
  --campaign-id alpha13-release-acceptance \
  --output /retained/evidence/alpha13-release-acceptance-plan.json
```

Run that plan with `run-harmony-assessed-campaign.py` under the target host's
active KVM, render and video groups. After the emulator and HDC target have been
stopped, retain cleanup evidence and validate the output:

```sh
python3 scripts/validate-release-harmony-acceptance.py \
  --closure release/closures/v0.1.0-alpha.13.json \
  --plan /retained/evidence/alpha13-release-acceptance-plan.json \
  --campaign-output /retained/evidence/alpha13-release-acceptance/campaign-output \
  --cleanup-evidence /retained/evidence/alpha13-release-acceptance/cleanup.json \
  --output /retained/evidence/alpha13-release-acceptance/acceptance.json
```

The validator requires real ohosTest/Hypium success for both variants, at least
one functional Oracle pass with valid SmartPerf proxy samples, at least one
meaningful Oracle failure whose performance collection was skipped, exact
closure/campaign digests, a direct-peer inspection trail, and zero remaining
emulator processes or HDC targets. It preserves the physical-device and
absolute-power/thermal boundary and never authorizes automatic promotion.

The Alpha.12 run against source cut `4a36510` is retained at
`release/qualifications/alpha12-harmony-acceptance-4a36510/summary.json`. This
historical receipt is not transferable to Alpha.13. It
records two source-bound ohosTest/Hypium passes, a positive UI Oracle with three
valid SmartPerf samples, a negative Oracle whose performance stage was skipped,
direct `hwlinux` peer identity, and post-run emulator/HDC cleanup. This closes
the candidate's Linux-emulator gate but not its tagged clean-install gate.

The acceptance verdict is also an input to the recursive analysis loop. Retain
that transition separately from release qualification with:

```sh
python3 scripts/prepare-release-recursive-feedback.py \
  --closure release/closures/v0.1.0-alpha.13.json \
  --acceptance release/qualifications/alpha12-harmony-acceptance-4a36510/summary.json \
  --campaign-summary /retained/campaign-output/summary.json \
  --prior-case /retained/campaign/case.json \
  --feedback /retained/campaign-output/assessment-feedback-candidates.json \
  --discrimination-report /retained/campaign-output/case-discrimination-report.json \
  --output /retained/alpha12-recursive-feedback.json
```

The handoff verifies the exact release source, closure, acceptance receipt,
campaign summary and raw feedback/report bytes. It records the functional
discrimination result and the measured performance boundary, then points to
`propose-feedback-analysis-cut.py` as the next executable gate. A single
SmartPerf observation remains useful retained evidence but cannot produce a
performance-derived difficulty candidate. The handoff never invents a new
source set, never changes the frozen case and never authorizes promotion.
The Alpha.12 result is retained at
`release/qualifications/alpha12-recursive-feedback-4a36510/summary.json`.
Its directory also retains the exact `prior-case.json` and
`assessment-feedback-candidates.json` bytes required to reproduce a successor
proposal without access to the original execution host.
That committed handoff can be supplied directly to the optional feedback inputs
of `multi-repo-analysis.yml`; the workflow emits an exact
`feedback-analysis-request.json` before analyzing the caller-selected new source
revisions. After analysis it deterministically ranks only non-ready impact
candidates spanning at least two repositories and emits at most ten independent
feedback-cut proposal files plus a queue index. Ranking creates a bounded review
queue; it explicitly does not establish semantic alignment or approve a case.

After an authorized merge and immutable tag are present, dispatch **Qualify
tagged developer preview** with the workflow ref set to that exact tag. The
workflow refuses branch refs and tag/closure mismatches, checks out full history,
validates the release graph, installs the closure on a fresh runner, and combines
the remote-asset, Harmony and clean-install evidence with:

```sh
python3 scripts/qualify-tagged-developer-preview.py \
  --closure release/closures/v0.1.0-alpha.13.json \
  --asset-receipt release/qualifications/alpha13-immutable-assets/summary.json \
  --harmony-receipt release/qualifications/alpha13-harmony-acceptance/summary.json \
  --install-summary /fresh-runner/summary.json \
  --environment-lock /fresh-runner/closure-materialized/environment-lock.json \
  --tag v0.1.0-alpha.13 --tag-sha <exact-tag-commit> \
  --repository yxsicd/agentlabrelease --run-id <github-run-id> \
  --event workflow_dispatch --git-root "$PWD" \
  --output /fresh-runner/developer-preview-qualification.json
```

The resulting Actions artifact is the final input to release publication. It is
review-required and cannot move a channel or create a GitHub Release by itself.
The same workflow feeds that receipt into
`prepare-developer-preview-publication.py`, producing exactly five small files:
`release-closure.json`, `qualification.json`, `publication.json`,
`release-notes.md` and `SHA256SUMS`. The GitHub Release uploads only the three
JSON files plus the checksum and uses the Markdown file as its notes; it never recopies
the 22 component assets or the multi-gigabyte emulator archives.

Before proposing a tag, independently verify that every referenced GitHub
Release asset still exists with the closure's exact server-reported size and
SHA-256, including assets hosted by another repository:

```sh
python3 scripts/validate-release-graph.py \
  --closure release/closures/v0.1.0-alpha.13.json \
  --registry release/components/registry.json \
  --remote \
  --git-root "$PWD" \
  --receipt release/qualifications/alpha13-immutable-assets/summary.json
```

Remote verification reads Release metadata and never downloads the multi-GB
emulator archives. A receipt is write-once, binds the closure and registry
digests, and records every observed GitHub asset ID, repository, tag, size and
SHA-256 without authorizing promotion.

To exercise installation from the closure rather than a mutable channel, first
materialize its small bootstrap pair:

```sh
python3 scripts/materialize-release-closure.py \
  --closure release/closures/v0.1.0-alpha.13.json \
  --registry release/components/registry.json \
  --output /tmp/agentlab-alpha13-bootstrap
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
