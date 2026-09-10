# Component references and public CI

Publish each component archive once, with a versioned URL, descriptor and SHA-256.
Environment releases contain only their environment lock and publication status.
Promotion preserves every component URL and digest; it changes the selected
composition and its qualification, without copying or rebuilding payloads.

Existing component URLs under older tier tags remain valid references. Do not
delete those assets while any published lock references them. New component
versions receive their own release tag. Never overwrite a versioned asset with
different bytes. Existing alpha environment kits remain historical previews.

The current example is
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
in this repository, and download the pinned control binary plus small build-kit
to run pack verify. Main-branch and manual runs additionally consume the public
fixed `alprod` lock, install its exact Docker image and component volumes with
the source-matched published `agentlabctl`, deploy the published standalone
SessionFS and Harmony services, then create, verify, Fork and patch a minimal
Harmony project while checking parent isolation. The controller is selected
from the immutable `control-<source>-linux-x64` Release rather than mutable
`alcontrol/current`, so a fixed v3 lock cannot be paired with an older parser.

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
