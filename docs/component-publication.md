# Component references and public CI

Current candidate: [40ecdf4b / SDKc075105a](../release/candidates/40ecdf4b-linux-x64/publication.json).
Channel policy and implementation boundaries are in [channel-validation.md](channel-validation.md).
Promote selectively from aldev to almain to alprod, preserving component bytes.
The dev/main/prod fixed channels now select runtime40ecdf4b and SDKc075105a,
with identical immutable component references. All three GitHub qualification
tiers and explicit activation have passed. D is optional local quick testing;
D/A/B/C and device deployment do not gate these public channels.
The material below is historical context.

Historical runtime candidate:
[`26008e36-linux-x64`](../release/candidates/26008e36-linux-x64/publication.json).
Its environment release references component archives; it uploads no duplicate
payloads. The new runtime and previously unpublished `fa05788f` base image have
their own immutable component Releases. Existing tools, Harmony SDK and build
kit packages retain their published URLs and bytes. The controller is the
independently pinned `control-ea25616d-linux-x64`.

The Actions matrix installs both the fixed composition and the new candidate.
It runs a [preset Mock Agent](../examples/mock-agent/README.md) against real
standalone Harmony/SessionFS services on copy-tree and Btrfs. Agent success
claims are deliberately unreliable: file hashes and service receipts decide
the verdict. Both successful and failed runs upload raw protocol events,
service logs and evaluation summaries. Negative regression proves an incorrect
edit cannot turn the job green. This portable tier does not claim full
Session/TableGit activation or HAP compilation.

The candidate separately records a real Pi/GLM SWE run on D with 10/10 evaluator
tests, complete reconstruction of 1,348 runtime observations, and 20 context
revisions on one stable document. Full normalized whitebox coverage remains
incomplete. Runtime and session-template contract 6 must be installed together;
there is no automatic compatibility migration. A/B/C and fixed-channel
promotion remain pending their existing gates.

Publish each component archive once, with a versioned URL, descriptor and SHA-256.
Environment releases contain only their environment lock and publication status.
Promotion preserves every component URL and digest; it changes the selected
composition and its qualification, without copying or rebuilding payloads.

Existing component URLs under older tier tags remain valid references. Do not
delete those assets while any published lock references them. New component
versions receive their own release tag. Never overwrite a versioned asset with
different bytes. Existing alpha environment kits remain historical previews.

An earlier example is
[`08f839f6-linux-x64`](../release/candidates/08f839f6-linux-x64/publication.json).
It replaces only the runtime component and preserves every other component URL
and digest from the previous candidate. The runtime adds the public HTTP + MCP +
Website Skills surface while preserving the qualified Harmony cold build,
patch/rebuild, process restart, checkpoint Fork,
independent HAP inspection and ordinary Session exec. Lease, checkpoint and actual
execution projection convergence now pass. Earlier candidates and their failed
evidence remain historical. This is still a **candidate**: native/remote comparative parity,
clean public bootstrap and cross-environment promotion are not qualified. It does
not replace aldev, almain, alprod or alcontrol current.

The environment lock's template digest identifies an external, application-owned
template contract. Organization deployment and credential provisioning remain
separate; a public manifest does not supply private infrastructure access.

GitHub Actions runs only in this public release repository. Pull requests
validate manifests and references, test and build the small Rust tools already
in this repository. Same-repository pull requests, main-branch pushes and manual
runs additionally consume the public fixed `alprod` lock, install its exact
Docker image and component volumes with the source-matched published
`agentlabctl`, deploy the published standalone SessionFS and Harmony services,
then create, verify, Fork and patch a minimal Harmony project while checking
parent isolation. The controller is selected from the immutable
`control-<source>-linux-x64` Release rather than mutable `alcontrol/current`, so
a fixed v3 lock cannot be paired with an older parser.

The workflow has read-only repository permissions and uses no private source
checkout, application credentials, private Sessions or production deployment.
It proves public acquisition, Docker installation and the credential-free basic
use case. Full AgentLab activation remains a D/A/B/C release gate because it
requires the independently authorized MCPGit/SafeGit control plane.

Run locally:

```sh
python3 scripts/validate-release.py
python3 -m unittest discover -s tests
python3 scripts/validate-composition-release.py --remote
cargo test --locked --workspace
cargo build --locked --release --workspace
# Linux x64 only:
python3 scripts/validate-composition-release.py --remote --smoke
scripts/ci-public-install-deploy-smoke.sh
```

## Routine single-component upgrade

Run **Compose single-component upgrade** with a published `base_release`, a
published `donor_release` containing the new component, and one `component`:
`session-sdk`, `control`, `pack:<slot>` or `image:<slot>`. The donor is an
existing versioned composition, not a request to select “latest”. This produces
`candidate-component-<run-id>` with metadata only. Unchanged component references
and base deployment bindings are retained. Real contract mismatches stop
composition; explicitly prepare a coordinated composition when needed.

Next run **Freeze channel validation plan**, target `aldev`, setting
`candidate_release` to that tag. After qualification, use the existing explicit
prepare/activate workflow. Selectively promote the same composition to `almain`
and `alprod`; each tier executes its own checks. No D/A/B/C dependency is added.
The upgrade receipt records the base and donor identities and before/after
component data. Old qualification is removed, all new candidate checks start
`not_run`, and an unchanged replacement creates no release.

Local equivalent:

```sh
python3 scripts/component-upgrade.py --base release/channels/aldev \
  --donor /path/to/published-composition --component session-sdk \
  --tag candidate-sdk-upgrade --output /tmp/agentlab-sdk-upgrade
```

A newly released component does **not** require a donor solution. Its producer
publishes an `agentlab.component_update.v1` JSON descriptor alongside its own
package. Set `replacement_url` instead of `donor_release`. The descriptor has
`component`, `value` (one SDK/controller/image/pack identity), and `assets`
(published URL/bytes/SHA references). Packs and images also declare `graphNode`
with their binding, platform, provided and required contracts. Runtime pack
updates declare `sourceRevision`. The producer owns these declarations;
the composition tool resolves the resulting whole graph. Deployment bindings
remain owned by the base. The executable SDK example is
[`session-sdk-c075105a.json`](../release/components/session-sdk-c075105a.json).
Use `--replacement <descriptor.json>` instead of `--donor` locally.

Pass `--replacement-url <original-url>` for locally downloaded descriptors with
relative metadata references. The workflow supplies this automatically. Relative
metadata follows the descriptor URL, and the receipt preserves its exact source
digest. Auxiliary template inventory is metadata, not a duplicated component
archive.
