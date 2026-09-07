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
[`e921d102-linux-x64`](../release/candidates/e921d102-linux-x64/publication.json).
It references the runtime image, runtime pack, developer tools, original Harmony
SDK, Harmony build-kit and installation control binary. It intentionally remains
a **candidate**: formal Harmony Session execution has a known projection defect,
and Fork/restart/parity and clean public bootstrap are not qualified. This
publication does not replace aldev, almain, alprod or alcontrol current.

The environment lock's template digest identifies an external, application-owned
template contract. Organization deployment and credential provisioning remain
separate; a public manifest does not supply private infrastructure access.

GitHub Actions runs only in this public release repository. It validates manifests
and references, tests and builds the small Rust tools already in this repository,
and downloads the pinned control binary plus small build-kit to run pack verify.
The workflow has read-only repository permissions and uses no private source
checkout, application credentials, private Sessions or production deployment.
These checks are packaging evidence, not full runtime acceptance.

Run locally:

```sh
python3 scripts/validate-release.py
python3 -m unittest discover -s tests
python3 scripts/validate-composition-release.py --remote
cargo test --locked --workspace
cargo build --locked --release --workspace
# Linux x64 only:
python3 scripts/validate-composition-release.py --remote --smoke
```
